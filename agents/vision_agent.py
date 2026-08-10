import os

from langgraph.prebuilt import create_react_agent

from tools.vision.describe_tool import image_describer_tool
from tools.vision.detect_tool import detect_and_count_tool
from utils.llm import build_ollama_chat_model

VISION_MODEL_NAME = os.getenv("VISUAL_MODEL_NAME", "gemma4:31b-cloud")

vision_agent = create_react_agent(
    model=build_ollama_chat_model(VISION_MODEL_NAME),
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
