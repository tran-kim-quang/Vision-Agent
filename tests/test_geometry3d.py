"""Plain-python tests for the geometry kernel (no pytest needed).

Run:  python tests/test_geometry3d.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geometry3d import PRESETS, build_solid, validate_solid
from geometry3d.kernel import _cube


def test_presets_all_pass_gate():
    for preset in PRESETS:
        result = build_solid(preset["spec"])
        assert result["ok"], f"preset {preset['id']} failed: {result['checks']}"
        assert result["checks"]["structure"] == []
        assert all(c["ok"] for c in result["checks"]["claims"])


def test_cuboid_m_above_d():
    """Regression: in OADB.CFME the topology forces M above D (and E above B)."""
    result = build_solid({"kind": "cuboid", "params": {"a": 3.0, "b": 4.0, "c": 2.5}})
    v = result["vertices"]
    assert v["M"][:2] == v["D"][:2] and v["M"][2] == 2.5 and v["D"][2] == 0.0
    assert v["E"][:2] == v["B"][:2] and v["E"][2] == 2.5
    assert v["F"][:2] == v["A"][:2]


def test_gate_rejects_wrong_claim():
    spec = {
        "kind": "cuboid",
        "params": {"a": 3.0, "b": 4.0, "c": 2.5},
        "claims": [{"type": "distance", "a": "O", "b": "B", "expect": 6.0}],  # really 5.0
    }
    result = build_solid(spec)
    assert result["ok"] is False
    assert result["checks"]["claims"][0]["ok"] is False


def test_validator_catches_inward_face():
    vertices, faces, _, _ = _cube(2.0)
    faces = [list(f) for f in faces]
    faces[0] = list(reversed(faces[0]))  # flip base -> normal points inward
    problems = validate_solid(vertices, faces)
    assert any("inward" in p for p in problems), problems


def test_unknown_kind_is_an_error_not_a_crash():
    result = build_solid({"kind": "hypercube", "params": {}})
    assert result["ok"] is False and "error" in result


if __name__ == "__main__":
    test_presets_all_pass_gate()
    test_cuboid_m_above_d()
    test_gate_rejects_wrong_claim()
    test_validator_catches_inward_face()
    test_unknown_kind_is_an_error_not_a_crash()
    print("geometry3d: all tests passed")
