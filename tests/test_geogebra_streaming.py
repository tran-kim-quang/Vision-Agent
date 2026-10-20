import json
import unittest

from langchain_core.messages import ToolMessage

from geometry3d.geogebra.streaming import artifact_event
from tools.geometry.construction_tool import prepare_geometry


SPEC = {
    "version": 1, "title": "Điểm", "app": "3d",
    "givens": [{"text": "A là điểm", "source_text": "A" * 1500}],
    "goals": [], "display_choices": [],
    "steps": [{"id": "A", "op": "point", "coords": [0, 0, 0]}],
}


def prepared():
    return json.dumps(prepare_geometry(SPEC), ensure_ascii=False)


def decode_sse(chunks):
    events = []
    for chunk in chunks:
        if chunk.startswith("data: "):
            events.append(json.loads(chunk[6:].strip()))
    return events


class ArtifactEventTests(unittest.TestCase):
    def test_complete_large_artifact_and_deduplication(self):
        content = prepared()
        self.assertGreater(len(content), 1000)
        seen = set()
        event = artifact_event("prepare_geometry", content, "call-1", "session", "request", seen)
        self.assertEqual(event["type"], "geometry_artifact")
        self.assertEqual(event["artifact"]["title"], "Điểm")
        self.assertIsNone(artifact_event("prepare_geometry", content, "call-1", "session", "request", seen))
        self.assertIsNotNone(artifact_event("prepare_geometry", content, "call-1", "session", "request", set()))

    def test_invalid_unsuccessful_and_fabricated_payloads_are_not_artifacts(self):
        self.assertIsNone(artifact_event("research", prepared(), "x", "s", "r", set()))
        self.assertIsNone(artifact_event("prepare_geometry", "not-json", "x", "s", "r", set()))
        self.assertIsNone(artifact_event("prepare_geometry", json.dumps({"status":"invalid_spec","issues":[]}), "x", "s", "r", set()))
        payload = json.loads(prepared())
        payload["artifact"]["steps"][0]["commands"] = ["Delete(A)"]
        self.assertIsNone(artifact_event("prepare_geometry", json.dumps(payload), "x", "s", "r", set()))


class FakeSupervisor:
    def __init__(self, content, fail=True):
        self.content = content
        self.fail = fail
        self.config = None

    async def astream(self, state, config, stream_mode):
        self.config = config
        yield ("messages", (ToolMessage(content=self.content, name="prepare_geometry", tool_call_id="tool-1"), {"langgraph_checkpoint_ns":"geometry_agent:abc"}))
        yield ("messages", (ToolMessage(content="R" * 1400, name="wikipedia", tool_call_id="research-1"), {"langgraph_checkpoint_ns":"research_agent:abc"}))
        if self.fail:
            raise RuntimeError("stream broke")


class StreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_start_artifact_error_and_done_are_emitted(self):
        from api import event_stream

        supervisor = FakeSupervisor(prepared())
        chunks = [chunk async for chunk in event_stream("draw", "session-1", supervisor)]
        events = decode_sse(chunks)
        self.assertEqual(events[0]["type"], "request_start")
        request_id = events[0]["request_id"]
        self.assertEqual(supervisor.config["configurable"]["geometry_request_id"], request_id)
        artifact = next(event for event in events if event["type"] == "geometry_artifact")
        self.assertEqual((artifact["session_id"], artifact["request_id"]), ("session-1", request_id))
        self.assertIn("error", [event["type"] for event in events])
        self.assertEqual(events[-1]["type"], "done")
        research = next(event for event in events if event.get("tool") == "wikipedia")
        self.assertEqual(len(research["content"]), 1000)


if __name__ == "__main__":
    unittest.main()
