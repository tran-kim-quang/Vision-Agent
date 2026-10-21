import json
import unittest
from pathlib import Path

from tools.geometry.construction_tool import prepare_geometry


FIXTURES = Path(__file__).parent / "fixtures" / "geogebra"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class ToolTests(unittest.TestCase):
    def test_sphere_returns_an_executable_surface_artifact(self):
        result = prepare_geometry(fixture("sphere.json"))
        self.assertEqual(result["status"], "prepared")
        sphere = next(s for s in result["artifact"]["steps"] if s["source_step_id"] == "ball")
        self.assertEqual(sphere["commands"], ["ball=Sphere(O,2.0)"])

    def test_tool_returns_structured_errors(self):
        result = prepare_geometry({"version": 1, "title": "broken", "app": "3d", "givens": [], "goals": [], "display_choices": [], "steps": [{"id":"M","op":"midpoint","a":"A","b":"B"}]})
        self.assertEqual(result["status"], "invalid_spec")
        self.assertEqual(result["issues"][0]["code"], "missing_reference")

    def test_unresolved_issues_require_clarification(self):
        result = prepare_geometry(fixture("tetrahedron.json"), ["Điểm D nằm ở nửa không gian nào?"])
        self.assertEqual(result["status"], "needs_clarification")
        self.assertNotIn("artifact", result)

    def test_rejects_oversized_utf8_artifact(self):
        raw = fixture("tetrahedron.json")
        raw["goals"] = ["đ" * 1000 for _ in range(40)]
        result = prepare_geometry(raw)
        self.assertEqual(result["status"], "invalid_spec")
        self.assertEqual(result["issues"][0]["code"], "artifact_too_large")

    def test_vietnamese_round_trips_in_prepared_artifact(self):
        result = prepare_geometry(fixture("tetrahedron.json"))
        self.assertEqual(result["status"], "prepared")
        encoded = json.dumps(result, ensure_ascii=False)
        self.assertIn("Tứ diện ABCD", encoded)


if __name__ == "__main__":
    unittest.main()
