import os
from functools import lru_cache
from typing import Annotated

from langchain.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
_OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "ollama")
_YOLO_MODEL_PATH = os.getenv("YOLO_MODEL_PATH", "models/yolo11x.pt")

_llm = ChatOpenAI(model="gemma4:31b-cloud", base_url=_OLLAMA_BASE_URL, api_key=_OLLAMA_API_KEY)


# ── YOLO model (loaded once) ───────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _get_yolo():
    from ultralytics import YOLO
    return YOLO(_YOLO_MODEL_PATH)


# ── Image path extractor ───────────────────────────────────────────────────────
class _ImageInput(BaseModel):
    image_path: str = Field(..., description="The path or URL of the image to be processed.")

_parser = PydanticOutputParser(pydantic_object=_ImageInput)
_extractor = (
    ChatPromptTemplate.from_template(
        "Extract the image path or URL from the following input:\n\n"
        "{input}\n\n{format_instructions}"
    ).partial(format_instructions=_parser.get_format_instructions())
    | _llm
    | _parser
)


# ── Tool ───────────────────────────────────────────────────────────────────────
class _DetectionInput(BaseModel):
    text: str = Field(..., description="Text that contains an image path or URL for object detection.")


@tool("object_detection_and_counting", args_schema=_DetectionInput)
def detect_and_count_tool(
    text: Annotated[str, "Text that may contain an image path or URL."]
) -> dict | str:
    """Detect and count objects in an image. Returns counts per class and bounding boxes."""
    try:
        parsed = _extractor.invoke({"input": text})
    except Exception as exc:
        return f"Failed to extract image path: {exc}"

    if not parsed.image_path:
        return "No image path found in the input."

    try:
        model = _get_yolo()
        results = model(parsed.image_path, verbose=False)
    except Exception as exc:
        return f"Failed to perform object detection: {exc}"

    detections, counts = [], {}
    for result in results:
        for box in result.boxes:
            cls_id = int(box.cls[0])
            name = model.names[cls_id]
            detections.append({
                "class": name,
                "confidence": round(float(box.conf[0]), 3),
                "bbox": list(map(int, box.xyxy[0])),
            })
            counts[name] = counts.get(name, 0) + 1

    return {"counts": counts, "detections": detections}
