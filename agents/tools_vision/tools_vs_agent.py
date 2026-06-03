import os
from langchain.output_parsers import PydanticOutputParser
from ..module.import_deps import *

llm = ChatOpenAI(
    model="gemma4:31b-cloud",
    base_url="http://localhost:11434/v1",
    api_key="ollama",
)

# Define a Pydantic model for the expected output
class ImageInput(BaseModel):
    image_path: str = Field(..., description="The path or URL of the image to be processed.")

parser = PydanticOutputParser(pydantic_object=ImageInput)
prompt = ChatPromptTemplate.from_template(
    "Extract the image path or URL from the following input:\n\n"
    "{input}\n\n{format_instructions}"
).partial(format_instructions=parser.get_format_instructions())

extractor_chain = prompt | llm | parser

# Function to encode image to base64 string
def encode_img(image_path: str, get_mime_type: bool = False):
    """
    Encode an image to a base64 string.
    Return tuple (base61, mime) if get_mime_type is True, otherwise return base64 string only.
    """
    def _fail():
        if get_mime_type:
            return None, None
        return None
    if image_path.startswith("http"):
        try:
            response = requests.get(image_path, stream=True, timeout=15)
            if response.status_code != 200:
                return _fail()
            mime_type = response.headers.get("Content-Type", None)
            b64=base64.b64encode(response.content).decode("utf-8")
            return (b64, mime_type) if get_mime_type else b64
        except requests.exceptions.RequestException as e:
            print(f"Failed to download image from {image_path}: {e}")
            return _fail()

    else:
        if not os.path.exists(image_path):
            return _fail()
        mime_type = magic.Magic(mime=True).from_file(image_path)
        if not mime_type.startswith("image/"):
            return _fail()
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
            return (b64, mime_type) if get_mime_type else b64


# Image describer
class ImageDescription(BaseModel):
    image_description: str = Field(..., description="A detailed description of the image content.")

class ImageDescriberInput(BaseModel):
    text: str = Field(..., description="The text input that may contain an image path or URL.")

image_desc_parser = PydanticOutputParser(pydantic_object=ImageDescription)

def image_describer_prompt_func(inputs: dict):
    image_path = inputs.get("image_path")
    if not image_path:
        return "No image path provided."

    b64, mime_type = encode_img(image_path, get_mime_type=True)
    if not b64:
        return "Failed to encode the image. Please check the image path and try again."

    return [
        SystemMessage(content=(
            "You are an image analysis assistant. Analyze the image and describe it in detail.\n"
            f"Image MIME type: {mime_type}\n"
            "Focus on: objects and their positions, colors/lighting/textures, "
            "actions or dynamics, and contextual information. "
            "If text appears in the image, transcribe it accurately.\n"
            f"{image_desc_parser.get_format_instructions()}"
        )),
        HumanMessage(content=[
            {"type": "text", "text": "Please analyze the image and provide a detailed description."},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{b64}",
                    # "detail": "high"
                }
            }
        ])
    ]

image_describer_agent = (
    image_describer_prompt_func | llm | image_desc_parser
)

class ImageDescriberTool(BaseTool):
    name: str = "image_describer"
    description: str = "A tool to analyze and describe the content of an image. Input should be a text that may contain an image path or URL, and the output will be a detailed description of the image content."
    args_schema: Optional[ArgsSchema] = ImageDescriberInput

    return_direct: bool = True

    def _run(self,
            text: str,
            run_manager: Optional[CallbackManagerForToolRun] = None
        ) -> str:

        try:
            parsed: ImageInput = extractor_chain.invoke({"input": text})
        except Exception as e:
            return f"Failed to extract image path: {e}"

        image_path = parsed.image_path
        if not image_path:
            return "No image path found in the input."

        try:
            output = image_describer_agent.invoke({"image_path": image_path})

        except Exception as e:
            return f"Failed to analyze the image: {e}"
        return output.image_description

    async def _arun(self,
            text: str,
            run_manager: Optional[AsyncCallbackManagerForToolRun] = None
        ) -> str:
        return self._run(text, run_manager=run_manager)

image_describer_tool = ImageDescriberTool()
# print(image_describer_tool.invoke('/home/meocon/work/Visual-Agent/663194457_122119841253180261_8059969371422744300_n.jpg'))
