import unittest

from geometry3d.geogebra import ExpressionError, emit_expression, parse_expression


class ExpressionTests(unittest.TestCase):
    def parse(self, text, variables=frozenset({"x", "y"})):
        return parse_expression(text, variables)

    def test_caret_and_python_power_normalize_identically(self):
        self.assertEqual(emit_expression(self.parse("x^2-y^2")), emit_expression(self.parse("x**2-y**2")))
        self.assertEqual(emit_expression(self.parse("x^2-y^2")), "((x ^ 2) - (y ^ 2))")

    def test_rejects_statements_code_access_and_unknown_names(self):
        bad = ["x;Delete(A)", "x=1", "__import__('os')", "x.real", "x[0]", "q+1", "Infinity"]
        for expression in bad:
            with self.subTest(expression=expression), self.assertRaises(ExpressionError):
                self.parse(expression)

    def test_constants_and_functions_are_explicit(self):
        self.assertEqual(emit_expression(self.parse("log(e)+sqrt(pi)")), "(log(e) + sqrt(pi))")
        with self.assertRaises(ExpressionError):
            self.parse("tau+x")

    def test_depth_bound_is_enforced(self):
        with self.assertRaises(ExpressionError) as caught:
            self.parse("(" * 33 + "x" + "+1)" * 33)
        self.assertEqual(caught.exception.code, "expression_too_deep")

    def test_emit_can_rename_variables_without_text_replacement(self):
        tree = self.parse("exp(x)+y")
        self.assertEqual(emit_expression(tree, {"x":"u", "y":"v"}), "(exp(u) + v)")


if __name__ == "__main__":
    unittest.main()
