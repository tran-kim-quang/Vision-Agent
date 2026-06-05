import base64
import os
from typing import Optional

import magic
import requests
from langchain.output_parsers import PydanticOutputParser
from langchain_core.callbacks import AsyncCallbackManagerForToolRun, CallbackManagerForToolRun
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import BaseTool
from langchain_core.tools.base import ArgsSchema
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
_OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "ollama")

_llm = ChatOpenAI(model="gemma4:31b-cloud", base_url=_OLLAMA_BASE_URL, api_key=_OLLAMA_API_KEY)


# ── Image path extractor ───────────────────────────────────────────────────────
class _ImageInput(BaseModel):
    image_path: str = Field(..., description="The path or URL of the image to be processed.")

_path_parser = PydanticOutputParser(pydantic_object=_ImageInput)
_path_extractor = (
    ChatPromptTemplate.from_template(
        "Extract the image path or URL from the following input:\n\n"
        "{input}\n\n{format_instructions}"
    ).partial(format_instructions=_path_parser.get_format_instructions())
    | _llm
    | _path_parser
)


# ── Image encoding ─────────────────────────────────────────────────────────────
def _encode_image(image_path: str) -> tuple[str | None, str | None]:
    """Return (base64_string, mime_type) or (None, None) on failure."""
    if image_path.startswith("http"):
        try:
            resp = requests.get(image_path, stream=True, timeout=15)
            if resp.status_code != 200:
                return None, None
            mime = resp.headers.get("Content-Type")
            return base64.b64encode(resp.content).decode(), mime
        except requests.RequestException as exc:
            print(f"Failed to download image: {exc}")
            return None, None
    else:
        if not os.path.exists(image_path):
            return None, None
        mime = magic.Magic(mime=True).from_file(image_path)
        if not mime.startswith("image/"):
            return None, None
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode(), mime


# ── Describer chain ────────────────────────────────────────────────────────────
class _ImageDescription(BaseModel):
    image_description: str = Field(..., description="A detailed description of the image content.")

_desc_parser = PydanticOutputParser(pydantic_object=_ImageDescription)


def _build_describer_prompt(inputs: dict):
    b64, mime = _encode_image(inputs["image_path"])
    if not b64:
        return "Failed to encode the image. Please check the path and try again."
    return [
        SystemMessage(content=(
            "You are an image analysis assistant. Analyze the image and describe it in detail.\n"
            f"Image MIME type: {mime}\n"
            "Focus on: objects and positions, colors/lighting/textures, actions, context. "
            "Transcribe any visible text accurately.\n"
            f"{_desc_parser.get_format_instructions()}"
        )),
        HumanMessage(content=[
            {"type": "text", "text": "Please analyze the image and provide a detailed description."},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]),
    ]

_describer_chain = _build_describer_prompt | _llm | _desc_parser


# ── LangChain tool ─────────────────────────────────────────────────────────────
class _ImageDescriberInput(BaseModel):
    text: str = Field(..., description="Text input that may contain an image path or URL.")


class ImageDescriberTool(BaseTool):
    name: str = "image_describer"
    description: str = (
        "Analyze and describe the content of an image. "
        "Input should be text containing an image path or URL."
    )
    args_schema: Optional[ArgsSchema] = _ImageDescriberInput
    return_direct: bool = True

    def _run(self, text: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        try:
            parsed = _path_extractor.invoke({"input": text})
        except Exception as exc:
            return f"Failed to extract image path: {exc}"
        if not parsed.image_path:
            return "No image path found in the input."
        try:
            result = _describer_chain.invoke({"image_path": parsed.image_path})
        except Exception as exc:
            return f"Failed to analyze the image: {exc}"
        return result.image_description

    async def _arun(self, text: str, run_manager: Optional[AsyncCallbackManagerForToolRun] = None) -> str:
        return self._run(text)


image_describer_tool = ImageDescriberTool()
