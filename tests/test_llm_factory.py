import os
import unittest
from unittest.mock import patch

from utils.llm import build_ollama_chat_model


class ModelFactoryTests(unittest.TestCase):
    def test_riverai_configuration_uses_openai_compatible_client(self):
        env = {
            "RIVERAI_API_KEY": "secret",
            "RIVERAI_BASE_URL": "https://api.river.ai/v1",
        }
        with patch.dict(os.environ, env, clear=True), patch("utils.llm.ChatOpenAI") as client:
            build_ollama_chat_model("provider/model")
        client.assert_called_once_with(
            model="provider/model",
            api_key="secret",
            base_url="https://api.river.ai/v1",
        )

    def test_ollama_configuration_remains_supported(self):
        env = {"OLLAMA_BASE_URL": "http://localhost:11434/v1", "OLLAMA_API_KEY": "ollama"}
        with patch.dict(os.environ, env, clear=True), patch("utils.llm.ChatOllama") as client:
            build_ollama_chat_model("local-model")
        client.assert_called_once_with(model="local-model", base_url="http://localhost:11434", client_kwargs={})


if __name__ == "__main__":
    unittest.main()
