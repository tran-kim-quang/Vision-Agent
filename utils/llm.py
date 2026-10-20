import os

from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI


def _ollama_base_url() -> str:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    if base_url.endswith("/v1"):
        base_url = base_url[:-3]
    return base_url


def build_ollama_chat_model(model: str) -> ChatOllama | ChatOpenAI:
    river_key = os.getenv("RIVERAI_API_KEY", "").strip()
    river_base_url = os.getenv("RIVERAI_BASE_URL", "").strip()
    if river_key and river_base_url:
        return ChatOpenAI(model=model, api_key=river_key, base_url=river_base_url.rstrip("/"))

    api_key = os.getenv("OLLAMA_API_KEY", "")
    client_kwargs = {}
    if api_key and api_key != "ollama":
        client_kwargs["headers"] = {"Authorization": f"Bearer {api_key}"}

    return ChatOllama(
        model=model,
        base_url=_ollama_base_url(),
        client_kwargs=client_kwargs,
    )
