import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agents.geometry_agent import _PROMPT, build_geometry_agent
from tools.geometry.construction_tool import PrepareGeometryInput


VALID_SPEC = {
    "version": 1, "title": "Point", "app": "3d", "givens": [], "goals": [], "display_choices": [],
    "steps": [{"id": "A", "op": "point", "coords": [0, 0, 0]}],
}


class FakeModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def bind_tools(self, tools):
        return self

    def invoke(self, messages, config=None):
        response = self.responses[self.calls]
        self.calls += 1
        return response


def call(call_id, args, name="prepare_geometry"):
    return {"id": call_id, "name": name, "args": args, "type": "tool_call"}


def invoke(model, request_id="req-1"):
    graph = build_geometry_agent(model)
    return graph.invoke(
        {"messages": [HumanMessage(content="draw")], "geometry_attempts": 0, "geometry_request_id": ""},
        {"configurable": {"geometry_request_id": request_id}},
    )


class GeometryAgentTests(unittest.TestCase):
    def test_model_receives_the_construction_contract(self):
        description = PrepareGeometryInput.model_json_schema()["properties"]["spec"]["description"]
        for term in ("surface_explicit", "function2d", "coords", "source_text"):
            self.assertIn(term, description)
            self.assertIn(term, _PROMPT)

    def test_valid_tool_invocation_produces_prepared_tool_message(self):
        model = FakeModel([AIMessage(content="", tool_calls=[call("one", {"spec": VALID_SPEC})])])
        state = invoke(model)
        tools = [m for m in state["messages"] if isinstance(m, ToolMessage)]
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0].name, "prepare_geometry")
        self.assertEqual(json.loads(tools[0].content)["status"], "prepared")
        self.assertEqual(state["geometry_attempts"], 1)

    def test_invalid_then_corrected_invocation(self):
        bad = {**VALID_SPEC, "steps": [{"id":"M","op":"midpoint","a":"A","b":"B"}]}
        model = FakeModel([
            AIMessage(content="", tool_calls=[call("bad", {"spec": bad})]),
            AIMessage(content="", tool_calls=[call("good", {"spec": VALID_SPEC})]),
        ])
        state = invoke(model)
        statuses = [json.loads(m.content)["status"] for m in state["messages"] if isinstance(m, ToolMessage)]
        self.assertEqual(statuses, ["invalid_spec", "prepared"])
        self.assertEqual(model.calls, 2)

    def test_third_failed_submission_ends_without_fourth_call(self):
        bad = {**VALID_SPEC, "steps": [{"id":"M","op":"midpoint","a":"A","b":"B"}]}
        model = FakeModel([AIMessage(content="", tool_calls=[call(str(i), {"spec": bad})]) for i in range(4)])
        state = invoke(model)
        self.assertEqual(model.calls, 3)
        self.assertEqual(state["geometry_attempts"], 3)

    def test_multiple_calls_count_and_all_ids_receive_responses(self):
        bad = {**VALID_SPEC, "steps": [{"id":"M","op":"midpoint","a":"A","b":"B"}]}
        model = FakeModel([AIMessage(content="", tool_calls=[call("a", {"spec": bad}), call("b", {}), call("c", {"spec": bad}), call("d", {"spec": VALID_SPEC})])])
        state = invoke(model)
        tools = [m for m in state["messages"] if isinstance(m, ToolMessage)]
        self.assertEqual([m.tool_call_id for m in tools], ["a", "b", "c", "d"])
        self.assertEqual(state["geometry_attempts"], 3)
        self.assertEqual(json.loads(tools[-1].content)["status"], "invalid_spec")

    def test_success_or_clarification_stops_later_calls_in_same_message(self):
        model = FakeModel([AIMessage(content="", tool_calls=[
            call("clarify", {"spec": VALID_SPEC, "unresolved_issues": ["Thiếu vị trí của A"]}),
            call("guessed", {"spec": VALID_SPEC}),
        ])])
        state = invoke(model)
        tools = [m for m in state["messages"] if isinstance(m, ToolMessage)]
        self.assertEqual([m.tool_call_id for m in tools], ["clarify", "guessed"])
        self.assertEqual(json.loads(tools[0].content)["status"], "needs_clarification")
        self.assertEqual(json.loads(tools[1].content)["issues"][0]["code"], "request_already_finished")
        self.assertEqual(state["geometry_attempts"], 1)

    def test_unknown_tool_is_bounded_error(self):
        model = FakeModel([AIMessage(content="", tool_calls=[call("x", {}, "delete_everything")])])
        state = invoke(model)
        tool = next(m for m in state["messages"] if isinstance(m, ToolMessage))
        self.assertEqual(json.loads(tool.content)["issues"][0]["code"], "unknown_tool")

    def test_request_ids_are_isolated(self):
        first = invoke(FakeModel([AIMessage(content="", tool_calls=[call("one", {"spec": VALID_SPEC})])]), "r1")
        second = invoke(FakeModel([AIMessage(content="", tool_calls=[call("two", {"spec": VALID_SPEC})])]), "r2")
        self.assertEqual((first["geometry_request_id"], first["geometry_attempts"]), ("r1", 1))
        self.assertEqual((second["geometry_request_id"], second["geometry_attempts"]), ("r2", 1))

    def test_simultaneous_invocations_do_not_share_attempts(self):
        class ConcurrentModel:
            def bind_tools(self, tools): return self
            def invoke(self, messages, config=None):
                request_id = config["configurable"]["geometry_request_id"]
                return AIMessage(content="", tool_calls=[call(request_id, {"spec": VALID_SPEC})])

        graph = build_geometry_agent(ConcurrentModel())
        def run(request_id):
            return graph.invoke(
                {"messages": [HumanMessage(content="draw")], "geometry_attempts": 0, "geometry_request_id": ""},
                {"configurable": {"geometry_request_id": request_id}},
            )
        with ThreadPoolExecutor(max_workers=2) as pool:
            states = list(pool.map(run, ["parallel-a", "parallel-b"]))
        self.assertEqual([(s["geometry_request_id"], s["geometry_attempts"]) for s in states], [("parallel-a", 1), ("parallel-b", 1)])

    def test_supervisor_accepts_geometry_agent_without_importing_defaults(self):
        from agents import supervisor_agent
        sentinel = object()
        compiled = object()
        with patch.object(supervisor_agent, "create_supervisor") as create:
            create.return_value.compile.return_value = compiled
            result = supervisor_agent.build_supervisor(model=sentinel, agents=["research", "vision", "geometry"])
        self.assertIs(result, compiled)
        self.assertEqual(create.call_args.kwargs["agents"], ["research", "vision", "geometry"])
        self.assertIn("geometry_agent", create.call_args.kwargs["prompt"])


if __name__ == "__main__":
    unittest.main()
