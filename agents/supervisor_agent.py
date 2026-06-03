from langgraph_supervisor import create_supervisor
from langchain.chat_models import init_chat_model

from .vision_agent import vision_agent
from .research_agent import research_agent

supervisor = create_supervisor(
    model=init_chat_model(
        model="kimi-k2.5:cloud",
        model_provider="openai",
        base_url="http://localhost:11434/v1",
        api_key="ollama",
    ),
    agents=[research_agent, vision_agent],
    prompt=(
        "You are a supervisor managing two specialized agents:\n"
        "- research_agent: handles research tasks using arxiv and wikipedia\n"
        "- vision_agent: handles visual tasks such as describing images and detecting objects\n\n"
        "INSTRUCTIONS:\n"
        "- Route each user request to the appropriate agent based on the task type\n"
        "- For research or information lookup tasks, delegate to research_agent\n"
        "- For image analysis or object detection tasks, delegate to vision_agent\n"
        "- Synthesize the agent's response and return a clear final answer to the user\n"
        "RULES:\n"
        "- Always follow the instructions above\n"
        "- Never make up information or guess\n"
        "- Do NOT perform any tasks yourself, always delegate to the appropriate agent\n"
        "- If you are unsure, ask the user for clarification\n"
        "- If the user's request is unclear, ask the user a short clarification question before choosing an agent.\n"
        "- Respond in the same language as the user."
    ),
    add_handoff_back_messages=True,
    output_mode="full_history"
).compile()
