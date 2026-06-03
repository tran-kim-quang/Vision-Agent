from ..module.import_deps import *
from typing import Annotated
from functools import lru_cache
from langchain.output_parsers import PydanticOutputParser

llm = ChatOpenAI(
    model="gemma4:31b-cloud",
    base_url="http://localhost:11434/v1",
    api_key="ollama",
)


@lru_cache(maxsize=1)
def get_yolo_model():
    from ultralytics import YOLO

    return YOLO("yolo11x.pt")

# path = "/home/meocon/work/Visual-Agent/663194457_122119841253180261_8059969371422744300_n.jpg"
# result = yolo_model(path)

# annotated_bgr = result[0].plot()

# cv2.imshow("YOLO Detection", annotated_bgr)
# cv2.waitKey(0)
# cv2.destroyAllWindows()

class ImageInput(BaseModel):
    image_path: str = Field(..., description="The path or URL of the image to be processed.")

parser = PydanticOutputParser(pydantic_object=ImageInput)
prompt = ChatPromptTemplate.from_template(
    "Extract the image path or URL from the following input:\n\n"
    "{input}\n\n{format_instructions}"
).partial(format_instructions=parser.get_format_instructions())

extractor_chain = prompt | llm | parser

class ObjectDetectionAndCounting(BaseModel):
    text: str = Field(..., description="Text that contains an image path or URL for object detection and counting.")

@tool(
    "object_detection_and_counting",
    description="Detect and count objects within the image. The return will be a dictionary containing the counting dictionary (how many instances of each class) and a list of dictionaries with object names, confidence scores, and bbox localtions in (x1, y1, x2, y2) format.",
    args_schema=ObjectDetectionAndCounting
)
def detect_and_count_tool(
    text: Annotated[str, "Text that may contain an image path or URL for object detection and counting."]
):
    try:
        parsed: ImageInput = extractor_chain.invoke({"input": text})
    except Exception as e:
        return f"Failed to extract image path: {e}"

    image_path = parsed.image_path
    if not image_path:
        return "No image path found in the input."
    
    try:
        yolo_model = get_yolo_model()
        results = yolo_model(image_path, verbose=False)
    except Exception as e:
        return f"Failed to perform object detection: {e}"

    detections, counts = [], {}
    for result in results:
        for box in result.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            class_name = yolo_model.names[cls_id]
            detections.append({
                "class": class_name,
                "confidence": conf,
                "bbox": [x1, y1, x2, y2]
            })
            counts[class_name] = counts.get(class_name, 0) + 1
    return {
        "counts": counts,
        "detections": detections
    }

# print(detect_and_count_tool.invoke(path))
