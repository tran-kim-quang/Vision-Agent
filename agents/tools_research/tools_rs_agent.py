from ..module.import_deps import *
import wikipedia as _wiki_pkg

# print(llm.invoke("Hello").content)

arxiv_wrapper = ArxivAPIWrapper(
    top_k_results=2,
    doc_content_chars_max=1000,
)

arxiv = ArxivQueryRun(
    api_wrapper=arxiv_wrapper,
    description="Useful for searching for research papers on arXiv. Input should be a search query, and the output will be a list of relevant papers with their titles, authors, and summaries.",
)
# print(arxiv.invoke("deep learning for computer vision"))

# Wikipedia search
_wiki_pkg.set_user_agent("LiAn-Visual-Agent/0.1 (contact: trankimquang1603@gmail.com)")

wikipedia_wrapper = WikipediaAPIWrapper(
    top_k_results=2,
    doc_content_chars_max=2000,
)
wikipedia = WikipediaQueryRun(
    api_wrapper=wikipedia_wrapper,
    description="Useful for searching for information on Wikipedia. Input should be a search query, and the output will be a list of relevant Wikipedia articles with their titles and summaries.",
)
# print(wikipedia.invoke("Artificial Intelligence"))
