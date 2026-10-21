"""Model-facing tool that validates and prepares a GeoGebra artifact."""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from geometry3d.geogebra.compiler import compile_construction
from geometry3d.geogebra.validation import SpecError, validate_spec


MAX_ARTIFACT_BYTES = 64 * 1024
SUPPORTED_OPS = {"point", "segment", "line", "polygon", "plane", "midpoint", "intersection", "projection", "function2d", "surface_explicit", "sphere", "command"}

CONSTRUCTION_SPEC_GUIDE = """spec fields: version=1; title; app='graphing' or '3d';
givens=[{text,source_text}]; goals=[text]; display_choices=[text]; steps (1..100).
Every step has a unique id and op. Each step may also have caption: a short
descriptive display label in the user's language (1..80 characters), such as
'Tâm O', 'Mặt cầu (S)', 'Tiếp tuyến d'. Use captions to clarify object roles.
Do not put equations or coordinate values into captions; those belong in the
explanation and algebra panel. Keep ids unchanged for construction references.
Use a concise descriptive title for the figure, rather than its full equations.
Shapes:
- command {name:documented_command_name,args:[typed_arguments]}: use this for
  mathematical constructions described in the retrieved manual without adding
  a dedicated operation. Argument forms: {ref:object_id}, {number:finite_number},
  {boolean:true/false}, {expression:restricted_math}, {items:[typed_arguments]}.
  Expressions allow x,y,z,u,v, pi,e and basic arithmetic/functions as in
  function2d, not raw commands. Put nested constructions in their own steps.
  All refs must name steps in this artifact. Scripting commands are excluded.
  GeoGebra checks command signatures at execution. Command outputs have dynamic
  type; use command again when operating on them, rather than typed operations
  that require a statically known kind.
- Every step may have fill_opacity in [0,1]. For a shaded region, create its
  actual geometry and set a positive fill_opacity (e.g. 0.5). Boundary curves
  alone and prose about shading do not constitute a shaded-region construction.
- point {coords:[x,y]} in graphing, or {coords:[x,y,z]} in 3d.
  graphing also accepts [x,y,0], but never a nonzero z.
- segment/line/midpoint/intersection {a:id,b:id}
- polygon/plane {points:[ids]} (plane requires exactly three points)
- projection {point:id,target:id}: target is a line or a plane
- function2d {expression,domain:[min,max]} means y=f(x)
- surface_explicit {expression,x_domain:[min,max],y_domain:[min,max]} means z=f(x,y).
- sphere {center:id,radius:positive_number} OR {center:id,through:point_id}.
  Use exactly one of radius or through. A sphere requires app='3d'.
Define ALL referenced objects in this artifact, including helper points for axes.

Choose app for EACH current request, using history only to resolve references:
- graphing for Oxy, plane geometry, 2D points/lines/polygons and y=f(x) plots.
  It supports point, segment, line, polygon, midpoint, line-line intersection,
  projection onto a line, and function2d, including combinations in one figure.
- 3d for Oxyz, spatial geometry, solids, planes, nonzero z or explicit surfaces.
  plane, sphere and surface_explicit require 3d. 3d points must have three coordinates.
Respect an explicit 2D/3D request; switch freely between turns. Do not switch a
planar construction to 3d merely because it contains a vertical line.

Example of a filled region between f(x)=x^2+1 and g(x)=x+3 on [-1,2]:
define f and g as function2d steps, then add
{id:'region',op:'command',name:'IntegralBetween',args:[{ref:'g'},{ref:'f'},
{number:-1},{number:2}],caption:'Miền cần tính diện tích',fill_opacity:0.5}.
Read the manual for signatures. IntegralBetween integrates the signed difference;
for geometric area choose upper minus lower and split at crossings when needed.
Do not substitute a polygon down to Ox for a region bounded by two curves.

A vertical line x=c is supported: use op='line' through TWO DISTINCT points
(c,0) and (c,1). It is parallel to Oy and intersects Ox at (c,0).
It is NOT y=f(x), so never encode it as function2d, a constant y=c, or Line(A,A).
An auxiliary point along a given direction is a construction choice, not an
additional hypothesis; record that choice in display_choices. Do not give two
different ids identical coordinates when they define a line.
When a user asks for any illustrative member of an unspecified family, a
representative choice may be recorded in display_choices, not in givens.
Ask for clarification if missing data is needed to determine a requested unique
figure or could change the mathematical problem.

For a sphere request, include a sphere step: point samples alone do NOT draw its
surface. A whole sphere is not a single-valued z=f(x,y) graph; use sphere rather
than approximating it with point samples or one hemisphere.
If asked for any example of a tangent to a sphere with a given direction, choose
a concrete consistent example and record chosen values in display_choices.
In 3d use a direction vector, not one scalar slope. Example: sphere centered at
O(0,0,0), radius 2, tangent at M(2,0,0) with direction (0,1,0): define Q(2,1,0),
then sphere {id:'ball',op:'sphere',center:'O',radius:2} and line
{id:'tangent',op:'line',a:'M',b:'Q'}. OM is perpendicular to that direction.
Tiếp tuyến means a tangent LINE; do not replace it with a tangent plane unless
the user explicitly asks for tiếp diện or mặt phẳng tiếp xúc.
Return the sphere and tangent equations as mathematical explanation, but do not
claim the viewer has executed them or that a geometric goal was tool-verified.

Example for 'd qua A(2,0) song song Oy, tìm giao điểm với Ox':
{"version":1,"title":"Đường thẳng đứng trong Oxy","app":"graphing",
"givens":[{"text":"d qua A(2,0) song song Oy","source_text":"d qua A(2,0) song song Oy"}],
"goals":["Giao điểm I với Ox"],
"display_choices":["B(2,1) xác định hướng Oy; O và X xác định Ox"],
"steps":[{"id":"A","op":"point","coords":[2,0]},
{"id":"B","op":"point","coords":[2,1]},
{"id":"O","op":"point","coords":[0,0]},
{"id":"X","op":"point","coords":[1,0]},
{"id":"d","op":"line","a":"A","b":"B"},
{"id":"ox","op":"line","a":"O","b":"X"},
{"id":"I","op":"intersection","a":"d","b":"ox"}]}"""


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
