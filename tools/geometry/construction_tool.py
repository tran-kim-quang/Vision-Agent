"""Model-facing tool that validates and prepares a GeoGebra artifact."""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from geometry3d.geogebra.compiler import compile_construction
from geometry3d.geogebra.validation import SpecError, validate_spec


MAX_ARTIFACT_BYTES = 64 * 1024
SUPPORTED_OPS = {"point", "segment", "line", "polygon", "plane", "midpoint", "intersection", "projection", "function2d", "surface_explicit"}

CONSTRUCTION_SPEC_GUIDE = """spec fields: version=1; title; app='graphing' or '3d'; givens=[{text,source_text}]; goals=[text]; display_choices=[text]; steps (1..100). Every step has a unique id and op. Shapes: point {coords:[x,y,z]}; segment/line/midpoint/intersection {a:id,b:id}; polygon/plane {points:[ids]}; projection {point:id,target:id}; function2d {expression,domain:[min,max]}; surface_explicit {expression,x_domain:[min,max],y_domain:[min,max]}. Define referenced objects first. graphing accepts only function2d; surfaces require 3d. Example: {"version":1,"title":"Trung điểm","app":"3d","givens":[{"text":"A(0,0,0), B(4,0,0)","source_text":"A(0,0,0), B(4,0,0)"}],"goals":["Quan sát M"],"display_choices":[],"steps":[{"id":"A","op":"point","coords":[0,0,0]},{"id":"B","op":"point","coords":[4,0,0]},{"id":"M","op":"midpoint","a":"A","b":"B"}]}"""


class PrepareGeometryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    spec: dict = Field(description=CONSTRUCTION_SPEC_GUIDE)
    unresolved_issues: list[str] | None = Field(default=None, max_length=10)


def _issue(code: str, message: str, step_id: str | None = None) -> dict:
    return {"code": code, "step_id": step_id, "message": message}


def prepare_geometry(spec: dict, unresolved_issues: list[str] | None = None) -> dict:
    try:
        envelope = PrepareGeometryInput.model_validate({"spec": spec, "unresolved_issues": unresolved_issues})
        if envelope.unresolved_issues:
            if any(not isinstance(value, str) or not value.strip() or len(value) > 500 for value in envelope.unresolved_issues):
                return {"status": "invalid_spec", "issues": [_issue("invalid_unresolved_issue", "unresolved issues must be non-empty strings of at most 500 characters")]}
            return {"status": "needs_clarification", "issues": [_issue("unresolved", value) for value in envelope.unresolved_issues]}

        raw_steps = spec.get("steps", []) if isinstance(spec, dict) else []
        for raw_step in raw_steps if isinstance(raw_steps, list) else []:
            op = raw_step.get("op") if isinstance(raw_step, dict) else None
            if isinstance(op, str) and op not in SUPPORTED_OPS:
                return {"status": "unsupported", "issues": [_issue("unsupported_operation", f"operation {op!r} is not supported", raw_step.get("id"))]}

        artifact = compile_construction(validate_spec(envelope.spec))
        result = {"status": "prepared", "artifact": artifact.model_dump(mode="json")}
        payload = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(payload) > MAX_ARTIFACT_BYTES:
            return {"status": "invalid_spec", "issues": [_issue("artifact_too_large", f"artifact exceeds {MAX_ARTIFACT_BYTES} UTF-8 bytes")]}
        return result
    except SpecError as exc:
        return {"status": "invalid_spec", "issues": [_issue(exc.code, str(exc), exc.step_id)]}
    except ValidationError as exc:
        return {"status": "invalid_spec", "issues": [_issue("invalid_tool_input", str(exc))]}


try:
    from langchain_core.tools import StructuredTool

    prepare_geometry_tool = StructuredTool.from_function(
        func=prepare_geometry,
        name="prepare_geometry",
        description=f"Validate a typed geometry construction and compile deterministic GeoGebra commands. {CONSTRUCTION_SPEC_GUIDE}",
        args_schema=PrepareGeometryInput,
    )
except ImportError:  # Pure compiler tests do not require the agent dependency stack.
    prepare_geometry_tool = None
