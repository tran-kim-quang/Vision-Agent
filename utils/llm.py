import os

from langchain_ollama import ChatOllama


def _ollama_base_url() -> str:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    if base_url.endswith("/v1"):
        base_url = base_url[:-3]
    return base_url


def build_ollama_chat_model(model: str) -> ChatOllama:
    api_key = os.getenv("OLLAMA_API_KEY", "")
    client_kwargs = {}
    if api_key and api_key != "ollama":
        client_kwargs["headers"] = {"Authorization": f"Bearer {api_key}"}

    return ChatOllama(
        model=model,
        base_url=_ollama_base_url(),
        client_kwargs=client_kwargs,
    )
