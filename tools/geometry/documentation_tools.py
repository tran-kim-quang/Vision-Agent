"""Read-only tools for retrieving a bounded portion of the official manual."""

from langchain_core.tools import StructuredTool

from geometry3d.geogebra.documentation import get_command_docs, search_geogebra_docs


search_geogebra_docs_tool = StructuredTool.from_function(
    search_geogebra_docs,
    name="search_geogebra_docs",
    description="Search the local official GeoGebra manual by English command names or concepts. Translate the user's intent into a concise English query. Returns up to five summaries with source URLs and a pinned commit, not full pages. Search again with narrower terms if irrelevant.",
)
get_command_docs_tool = StructuredTool.from_function(
    get_command_docs,
    name="get_command_docs",
    description="Read the exact signatures, examples and notes of one GeoGebra command, named by a search result. Returns at most 4000 characters of original AsciiDoc. Use next_offset to continue. Mathematical commands with documented signatures can use prepare_geometry's general command step with structured arguments; GeoGebra validates support at execution.",
)
