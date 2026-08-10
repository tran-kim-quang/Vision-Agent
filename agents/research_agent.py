import os

from langgraph.prebuilt import create_react_agent

from tools.research.search_tools import arxiv, wikipedia
from utils.llm import build_ollama_chat_model

RESEARCH_MODEL_NAME = os.getenv("RESEARCH_MODEL_NAME", "gpt-oss:120b-cloud")

research_agent = create_react_agent(
    model=build_ollama_chat_model(RESEARCH_MODEL_NAME),
    tools=[arxiv, wikipedia],
    prompt=(
        "You are a research assistant. Use the provided tools to find information and research papers.\n\n"
        "INSTRUCTIONS:\n"
        "- Assist ONLY with research-related tasks. DO NOT do anything else.\n"
        "- Use tools to look up information; do not guess or fabricate facts.\n"
        "- After completing your task, respond to the supervisor directly.\n"
        "- Respond ONLY with the results of your work, do NOT include any other text."
    ),
    name="research_agent",
)
