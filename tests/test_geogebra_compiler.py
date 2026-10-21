import json
import unittest
from pathlib import Path

from geometry3d.geogebra import compile_construction, validate_spec


FIXTURES = Path(__file__).parent / "fixtures" / "geogebra"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class CompilerTests(unittest.TestCase):
    def test_display_captions_preserve_object_ids_and_commands(self):
        raw = fixture("sphere.json")
        raw["steps"][0]["caption"] = "Tâm O"
        raw["steps"][3]["caption"] = "Mặt cầu (S)"
        raw["steps"][4]["caption"] = "Tiếp tuyến d"
        artifact = compile_construction(validate_spec(raw))
        captions = {step.id: step.caption for step in artifact.spec.steps}
        self.assertEqual(captions["ball"], "Mặt cầu (S)")
        self.assertEqual(captions["tangent"], "Tiếp tuyến d")
        commands = {step.source_step_id: step.commands for step in artifact.steps}
        self.assertEqual(commands["ball"], ["ball=Sphere(O,2.0)"])
        self.assertEqual(commands["tangent"], ["tangent=Line(M,Q)"])

    def test_sphere_compiles_to_a_real_sphere_not_point_samples(self):
        raw = fixture("sphere.json")
        artifact = compile_construction(validate_spec(raw))
        sphere = next(step for step in artifact.steps if step.source_step_id == "ball")
        self.assertEqual(sphere.commands, ["ball=Sphere(O,2.0)"])
        self.assertEqual(sphere.expected_labels, ["ball"])
        raw["steps"][3] = {"id":"ball", "op":"sphere", "center":"O", "through":"M"}
        artifact = compile_construction(validate_spec(raw))
        self.assertEqual(next(s.commands for s in artifact.steps if s.source_step_id == "ball"), ["ball=Sphere(O,M)"])

    def test_planar_points_compile_to_2d_and_vertical_line_stays_a_line(self):
        for coords in ([2, 0], [2, 0, 0]):
            with self.subTest(coords=coords):
                raw = fixture("vertical2d.json")
                raw["steps"][0]["coords"] = coords
                artifact = compile_construction(validate_spec(raw))
                commands = {step.source_step_id: step.commands for step in artifact.steps}
                self.assertEqual(artifact.app, "graphing")
                self.assertEqual(commands["A"], ["A=(2.0,0.0)"])
                self.assertEqual(commands["d"], ["d=Line(A,B)"])
                self.assertEqual(commands["I"], ["I=Intersect(d,ox)"])
                self.assertEqual(commands["H"], ["H=ClosestPoint(ox,B)"])

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
