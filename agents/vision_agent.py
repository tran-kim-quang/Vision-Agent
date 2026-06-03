import os

from .module.import_deps import *
from .tools_vision.tools_vs_agent import image_describer_tool
from .tools_vision.object_detection import detect_and_count_tool
from pretty_print.pretty_print import pretty_print_messages

_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")

vision_agent = create_react_agent(
    model=ChatOpenAI(
        model="gemma4:31b-cloud",
        base_url=_OLLAMA_BASE_URL,
        api_key="ollama",
    ),
    tools=[image_describer_tool, detect_and_count_tool],
    prompt=(
        "You are a vision agent.\n\n"
        "INSTRUCTIONS:\n"
        "- Assist ONLY with visual tasks (e.g., describing images, detecting and counting objects)\n"
        "- Use only the tools provided to analyze visual inputs\n"
        "- After completing your task, respond to the supervisor directly\n"
        "- Respond ONLY with the results of your work, do NOT include ANY other text."
    ),
    name="vision_agent",
)

# config = {"recursion_limit": 50}
# for chunk in vision_agent.stream(
#     {"messages": [{"role": "user", "content": "how many person in image: /home/meocon/work/Visual-Agent/663194457_122119841253180261_8059969371422744300_n.jpg"}]},
#     config=config,
# ):
#     pretty_print_messages(chunk)
