import json
import math
import unittest
from pathlib import Path

from geometry3d.geogebra import SpecError, validate_spec


FIXTURES = Path(__file__).parent / "fixtures" / "geogebra"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def base(steps):
    return {"version": 1, "title": "test", "app": "3d", "givens": [], "goals": [], "display_choices": [], "steps": steps}


class SchemaTests(unittest.TestCase):
    def assert_code(self, code, raw):
        with self.assertRaises(SpecError) as caught:
            validate_spec(raw)
        self.assertEqual(caught.exception.code, code)

    def test_accepts_tetrahedron_fixture(self):
        value = validate_spec(fixture("tetrahedron.json"))
        self.assertEqual([step.id for step in value.steps], ["A", "B", "C", "D", "M", "N"])
        self.assertEqual(value.kinds["M"], "point")

    def test_rejects_duplicate_and_reserved_ids(self):
        self.assert_code("duplicate_id", base([{"id": "A", "op": "point", "coords": [0,0,0]}, {"id": "A", "op": "point", "coords": [1,0,0]}]))
        self.assert_code("reserved_id", base([{"id": "x", "op": "point", "coords": [0,0,0]}]))
        self.assert_code("reserved_id", base([{"id": "ggbAux1", "op": "point", "coords": [0,0,0]}]))

    def test_sorts_dependencies_stably(self):
        raw = base([
            {"id": "M", "op": "midpoint", "a": "A", "b": "B"},
            {"id": "C", "op": "point", "coords": [0,1,0]},
            {"id": "A", "op": "point", "coords": [0,0,0]},
            {"id": "B", "op": "point", "coords": [1,0,0]},
        ])
        self.assertEqual([s.id for s in validate_spec(raw).steps], ["C", "A", "B", "M"])

    def test_rejects_cycle_missing_reference_and_wrong_kind(self):
        self.assert_code("cycle", base([{"id":"a","op":"line","a":"b","b":"p"},{"id":"b","op":"line","a":"a","b":"p"},{"id":"p","op":"point","coords":[0,0,0]}]))
        self.assert_code("missing_reference", base([{"id":"m","op":"midpoint","a":"A","b":"B"}]))
        self.assert_code("wrong_kind", base([{"id":"A","op":"point","coords":[0,0,0]},{"id":"B","op":"point","coords":[1,0,0]},{"id":"l","op":"line","a":"A","b":"B"},{"id":"m","op":"midpoint","a":"A","b":"l"}]))

    def test_rejects_nonfinite_numbers_and_reversed_domains(self):
        for value in (math.inf, math.nan, True):
            self.assert_code("invalid_spec", base([{"id":"A","op":"point","coords":[value,0,0]}]))
        self.assert_code("invalid_domain", {**base([{"id":"f","op":"function2d","expression":"x","domain":[2,1]}]), "app":"graphing"})

    def test_limits_100_steps_500_chars_and_depth_32(self):
        steps = [{"id": f"P{i}", "op":"point", "coords":[i,0,0]} for i in range(100)]
        self.assertEqual(len(validate_spec(base(steps)).steps), 100)
        self.assert_code("invalid_spec", base(steps + [{"id":"TooMany","op":"point","coords":[0,0,0]}]))
        self.assert_code("expression_too_long", {**base([{"id":"f","op":"function2d","expression":"x+"*250+"x","domain":[0,1]}]), "app":"graphing"})


if __name__ == "__main__":
    unittest.main()
