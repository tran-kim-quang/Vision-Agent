import json
import unittest
from pathlib import Path

from geometry3d.geogebra import compile_construction, validate_spec


FIXTURES = Path(__file__).parent / "fixtures" / "geogebra"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class CompilerTests(unittest.TestCase):
    def test_midpoint_depends_on_source_points(self):
        artifact = compile_construction(validate_spec(fixture("tetrahedron.json")))
        self.assertEqual(artifact.title, "Tứ diện ABCD")
        self.assertEqual(artifact.steps[-2].commands, ["M=Midpoint(A,B)"])
        self.assertEqual(artifact.steps[-2].expected_labels, ["M"])

    def test_goals_never_compile_to_constraints(self):
        artifact = compile_construction(validate_spec(fixture("tetrahedron.json")))
        commands = "\n".join(command for step in artifact.steps for command in step.commands)
        self.assertNotIn("Parallel", commands)
        self.assertEqual(artifact.goals, ["MN song song BC"])

    def test_surface_renames_variables_to_u_v(self):
        raw = fixture("surface.json")
        raw["steps"][0]["expression"] = "exp(x)+log(y)"
        command = compile_construction(validate_spec(raw)).steps[0].commands[0]
        self.assertEqual(command, "s=Surface(u,v,(exp(u) + ln(v)),u,-3.0,3.0,v,-3.0,3.0)")

    def test_function_uses_graphing_app_supported_domain_guard(self):
        command = compile_construction(validate_spec(fixture("function2d.json"))).steps[0].commands[0]
        self.assertEqual(command, "f(x)=If(-6.0<=x<=6.0,sin(x))")

    def test_projection_emits_supported_perpendicular_construction(self):
        artifact = compile_construction(validate_spec(fixture("projection.json")))
        projection = artifact.steps[-1]
        self.assertEqual(projection.commands, ["ggbAux6=PerpendicularLine(A,base)", "H=Intersect(ggbAux6,base)"])
        self.assertEqual(projection.expected_labels, ["ggbAux6", "H"])


if __name__ == "__main__":
    unittest.main()
