"""Bounded geometry agent that prepares, but never executes, GeoGebra artifacts."""

from __future__ import annotations

import json
import os
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from tools.geometry.construction_tool import prepare_geometry, prepare_geometry_tool


MAX_PREPARATION_ATTEMPTS = 3

_PROMPT = """You are a geometry construction agent. Extract source-backed givens,
construction steps, display choices, and goals separately. Call prepare_geometry with
the typed construction. Never turn a requested conclusion into an input constraint,
silently invent a substantive hypothesis, emit raw GeoGebra commands, or claim that a
figure ran or a goal was proved. If the tool reports an invalid spec, correct it at
most twice. If information is genuinely ambiguous, submit unresolved_issues."""


class GeometryState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    geometry_request_id: str
    geometry_attempts: int
    geometry_stop: bool


def _error(code: str, message: str) -> dict:
    return {"status": "invalid_spec", "issues": [{"code": code, "step_id": None, "message": message}]}


def build_geometry_agent(model=None):
    if model is None:
        from utils.llm import build_ollama_chat_model

        model_name = os.getenv("GEOMETRY_MODEL_NAME") or os.getenv("SUPERVISOR_MODEL_NAME", "gemma4:31b-cloud")
        model = build_ollama_chat_model(model_name)
    bound_model = model.bind_tools([prepare_geometry_tool])

    def model_node(state: GeometryState, config: RunnableConfig):
        request_id = str(config.get("configurable", {}).get("geometry_request_id", ""))
        attempts = state.get("geometry_attempts", 0) if state.get("geometry_request_id") == request_id else 0
        response = bound_model.invoke([SystemMessage(content=_PROMPT), *state.get("messages", [])], config=config)
        return {"messages": [response], "geometry_request_id": request_id, "geometry_attempts": attempts, "geometry_stop": False}

    def tool_node(state: GeometryState):
        message = state["messages"][-1]
        attempts = state.get("geometry_attempts", 0)
        outputs: list[ToolMessage] = []
        stop = False
        for tool_call in getattr(message, "tool_calls", []):
            name = tool_call.get("name", "")
            call_id = tool_call.get("id", "")
            if name != "prepare_geometry":
                result = _error("unknown_tool", f"tool {name!r} is not available")
                stop = True
            elif attempts >= MAX_PREPARATION_ATTEMPTS:
                result = _error("attempt_limit", "geometry preparation attempt limit reached")
                stop = True
            else:
                attempts += 1
                args = tool_call.get("args")
                try:
                    if not isinstance(args, dict):
                        raise TypeError("tool arguments must be an object")
                    result = prepare_geometry(**args)
                except (TypeError, ValueError) as exc:
                    result = _error("invalid_tool_input", str(exc))
                if result.get("status") in {"prepared", "needs_clarification", "unsupported"}:
                    stop = True
            outputs.append(ToolMessage(content=json.dumps(result, ensure_ascii=False), name=name or "unknown", tool_call_id=call_id))
        return {"messages": outputs, "geometry_attempts": attempts, "geometry_stop": stop or attempts >= MAX_PREPARATION_ATTEMPTS}

    def after_model(state: GeometryState):
        last = state["messages"][-1]
        return "tools" if isinstance(last, AIMessage) and last.tool_calls else END

    def after_tools(state: GeometryState):
        return END if state.get("geometry_stop") else "model"

    graph = StateGraph(GeometryState)
    graph.add_node("model", model_node)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "model")
    graph.add_conditional_edges("model", after_model, {"tools": "tools", END: END})
    graph.add_conditional_edges("tools", after_tools, {"model": "model", END: END})
    return graph.compile(name="geometry_agent")


geometry_agent = None  # The supervisor builds this lazily with the application model.
