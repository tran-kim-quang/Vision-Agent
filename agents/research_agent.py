from .module.import_deps import *
from .tools_research.tools_rs_agent import arxiv, wikipedia
from pretty_print.pretty_print import pretty_print_messages
research_agent = create_react_agent(
    model = ChatOpenAI(
        model="gpt-oss:120b-cloud",
        base_url="http://localhost:11434/v1",
        api_key="ollama",
    ),
    tools = [arxiv, wikipedia],
    prompt = (
        "You are a research assistant. You can use the following tools to help you find information and research papers on various topics.\n"
        "When you want to use a tool, please use the following format:\n"
        "Tool name: <tool_name>\n"
        "Input: <input_for_the_tool>\n"
        "After you get the results from the tool, you can use the results to answer the user's question or to do further research.\n"
        "If you don't need to use any tools, you can directly answer the user's question.\n"
        "Remember to always use the tools when you need to find information or research papers, and always provide a clear and concise answer to the user's question.\n"
        "INSTRUCTIONS:\n"
        "- Assist ONLY with research-related task. DO NOT do anything else.\n"
        "- After you are dont with your tasks, respond to the supervisor directly\n"
        "- Respond ONLY with the results of your work, do NOT include any other text."
    ),
    name="research_agent",
)
config = {"recursion_limit": 50}
for chunk in research_agent.stream(
    {"messages": [{"role": "user", "content": "Machine Learning"}]},
    config=config,
):
    pretty_print_messages(chunk)