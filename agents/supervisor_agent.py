import os

from langgraph_supervisor import create_supervisor

from utils.llm import build_ollama_chat_model

SUPERVISOR_MODEL_NAME = os.getenv("SUPERVISOR_MODEL_NAME", "gemma4:31b-cloud")

_PROMPT = (
    "You are a supervisor managing three specialized agents:\n"
    "- research_agent: handles research tasks using arxiv and wikipedia\n"
    "- vision_agent: handles visual tasks such as describing images and detecting objects\n\n"
    "- geometry_agent: extracts typed geometry/function constructions for interactive GeoGebra figures\n\n"
    "INSTRUCTIONS:\n"
    "- Route each user request to the appropriate agent based on the task type\n"
    "- For research or information lookup tasks, delegate to research_agent\n"
    "- For image analysis or object detection tasks, delegate to vision_agent\n"
    "- For geometry construction or function plotting tasks, delegate to geometry_agent\n"
    "- Synthesize the agent's response and return a clear final answer to the user\n"
    "- You have access to the full conversation history — use it to answer follow-up questions\n"
    "RULES:\n"
    "- Never make up information or guess\n"
    "- Do NOT perform any tasks yourself, always delegate to the appropriate agent\n"
    "- If the user's request is unclear, ask a short clarification question\n"
    "- Respond in the same language as the user"
)


def build_supervisor(checkpointer=None, model=None, agents=None):
    """
    Compile the supervisor graph.
    Pass a checkpointer (AsyncRedisSaver or MemorySaver) for conversation memory.
    Called once at startup from api.py lifespan.
    """
    if agents is None:
        from agents.geometry_agent import build_geometry_agent
        from agents.research_agent import research_agent
        from agents.vision_agent import vision_agent

        agents = [research_agent, vision_agent, build_geometry_agent()]
    return create_supervisor(
        model=model or build_ollama_chat_model(SUPERVISOR_MODEL_NAME),
        agents=agents,
        prompt=_PROMPT,
        add_handoff_back_messages=True,
        output_mode="full_history",
    ).compile(checkpointer=checkpointer)
