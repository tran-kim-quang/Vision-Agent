import json
import unittest

from geometry3d.geogebra.documentation import get_command_docs, search_geogebra_docs


class DocumentationTests(unittest.TestCase):
    def test_digit_leading_search_results_can_be_read(self):
        result = search_geogebra_docs("3D_Commands")
        self.assertEqual(result["results"][0]["command"], "3D_Commands")
        for item in result["results"]:
            self.assertEqual(get_command_docs(item["command"])["status"], "ok")

    def test_exact_command_and_concept_search_retrieve_related_pages(self):
        for query, expected in (("Cone", "Cone"), ("sphere center radius", "Sphere"), ("perpendicular line point plane", "PerpendicularLine")):
            with self.subTest(query=query):
                result = search_geogebra_docs(query)
                self.assertEqual(result["status"], "ok")
                self.assertIn(expected, [item["command"] for item in result["results"][:3]])
                self.assertLessEqual(len(result["results"]), 5)
                self.assertLess(len(json.dumps(result)), 6000)
                self.assertEqual(len(result["revision"]), 40)

    def test_read_preserves_argument_syntax_and_source(self):
        result = get_command_docs("Cone")
        self.assertEqual(result["status"], "ok")
        self.assertIn("Cone( <Point>, <Point>, <Radius> )", result["content"])
        self.assertTrue(result["source_url"].endswith("/commands/Cone/"))
        self.assertIn(result["revision"], result["source_file_url"])

    def test_missing_commands_and_unmatched_queries_do_not_invent_results(self):
        self.assertEqual(get_command_docs("MadeUpShapeXYZ")["status"], "not_found")
        self.assertEqual(search_geogebra_docs("zzzzzzunknownshapezzzzzz")["results"], [])

    def test_command_lookup_cannot_read_arbitrary_files(self):
        for name in ("../../.env", "/etc/passwd", "Sphere.adoc"):
            self.assertEqual(get_command_docs(name)["status"], "not_found")

    def test_invalid_queries_and_offsets_return_structured_errors(self):
        for query in ("", " ", "x" * 501):
            self.assertEqual(search_geogebra_docs(query)["status"], "invalid_query")
        for offset in (-1, True, "1"):
            self.assertEqual(get_command_docs("Cone", offset=offset)["status"], "invalid_offset")

    def test_large_pages_are_read_in_bounded_chunks(self):
        result = get_command_docs("Angle")
        self.assertEqual(result["status"], "ok")
        self.assertLessEqual(len(result["content"]), 4000)
        self.assertIsNotNone(result["next_offset"])
        continuation = get_command_docs("Angle", offset=result["next_offset"])
        self.assertEqual(continuation["status"], "ok")
        self.assertNotEqual(result["content"], continuation["content"])
        self.assertEqual(result["revision"], continuation["revision"])


if __name__ == "__main__":
    unittest.main()
