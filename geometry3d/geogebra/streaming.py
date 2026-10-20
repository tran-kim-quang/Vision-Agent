"""Validation boundary for executable geometry artifacts carried over SSE."""

from __future__ import annotations

import json
from uuid import UUID

from pydantic import ValidationError

from .compiler import GeometryArtifact, compile_construction
from .validation import SpecError, validate_spec


def artifact_event(
    tool_name: str,
    content: str,
    tool_call_id: str,
    session_id: str,
    request_id: str,
    seen: set[str],
) -> dict | None:
    if tool_name != "prepare_geometry" or tool_call_id in seen:
        return None
    try:
        envelope = json.loads(content)
        if not isinstance(envelope, dict) or envelope.get("status") != "prepared":
            return None
        artifact = GeometryArtifact.model_validate(envelope.get("artifact"))
        UUID(artifact.id)
        rebuilt = compile_construction(validate_spec(artifact.spec.model_dump(mode="json")))
        supplied = artifact.model_dump(mode="json", exclude={"id"})
        expected = rebuilt.model_dump(mode="json", exclude={"id"})
        if supplied != expected:
            return None
    except (json.JSONDecodeError, TypeError, ValueError, ValidationError, SpecError):
        return None
    seen.add(tool_call_id)
    return {
        "type": "geometry_artifact",
        "session_id": session_id,
        "request_id": request_id,
        "artifact": artifact.model_dump(mode="json"),
    }
