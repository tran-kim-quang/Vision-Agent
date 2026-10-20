"""Interactive 3D geometry: semantic spec -> kernel -> validation gate -> render data.

Rule of the house: coordinates are computed by the kernel, never taken from
an LLM or from raw client input. A spec names a solid kind + parameters (and
optionally geometric claims); this package builds exact vertices/edges/faces,
validates them, verifies the claims, and only then hands data to the viewer.
"""

from .kernel import PRESETS, build_solid, validate_solid, verify_claims

__all__ = ["PRESETS", "build_solid", "validate_solid", "verify_claims"]
