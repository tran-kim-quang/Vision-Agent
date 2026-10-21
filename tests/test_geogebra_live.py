"""Opt-in real-model regression: GEOGEBRA_LIVE_TESTS=1 python -m unittest discover -s tests -p test_geogebra_live.py."""

import json
import math
import os
import unittest
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agents.geometry_agent import build_geometry_agent
from utils.llm import build_ollama_chat_model


@unittest.skipUnless(os.getenv("GEOGEBRA_LIVE_TESTS") == "1", "requires an explicitly enabled live model")
class LiveGeometryTests(unittest.TestCase):
    def test_integral_region_is_prepared_for_actual_shading(self):
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        name = os.getenv("GEOMETRY_MODEL_NAME") or os.getenv("SUPERVISOR_MODEL_NAME", "gemma4:31b-cloud")
        model = build_ollama_chat_model(name)
        model.request_timeout = 60
        model.max_retries = 0
        from agents.supervisor_agent import build_supervisor
        graph = build_supervisor(model=model, agents=[build_geometry_agent(model)])
        state = graph.invoke({'messages':[HumanMessage(content=
            'Tính diện tích hình phẳng giữa y=x^2+1 và y=x+3, giao điểm x=-1 và x=2. Vẽ hình và tô rõ miền cần tính trên đoạn [-1,2].'
        )]}, {'recursion_limit':50,'configurable':{'geometry_request_id':'live-integral-region'}})
        results = [json.loads(m.content) for m in state['messages'] if isinstance(m, ToolMessage) and m.name == 'prepare_geometry']
        artifacts = [r['artifact'] for r in results if r.get('status') == 'prepared']
        self.assertEqual(len(artifacts), 1, results)
        artifact = artifacts[0]
        self.assertEqual(artifact['app'], 'graphing')
        regions = [s for s in artifact['spec']['steps'] if s['op'] == 'command' and s['name'] == 'IntegralBetween']
        self.assertEqual(len(regions), 1, artifact['spec']['steps'])
        self.assertGreater(regions[0].get('fill_opacity') or 0, 0)
        self.assertEqual([a.get('number') for a in regions[0]['args'][2:]], [-1, 2])
        output = os.getenv('GEOGEBRA_REGION_ARTIFACT')
        if output:
            Path(output).write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print('live integral: supervisor returned a real IntegralBetween command with positive filling', flush=True)

    def test_vietnamese_request_retrieves_unfamiliar_command_without_full_manual(self):
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        name = os.getenv("GEOMETRY_MODEL_NAME") or os.getenv("SUPERVISOR_MODEL_NAME", "gemma4:31b-cloud")
        model = build_ollama_chat_model(name)
        model.request_timeout = 60
        model.max_retries = 0
        state = build_geometry_agent(model).invoke({"messages": [HumanMessage(content=
            "Trong không gian Oxyz, dựng hình nón có đáy tâm O(0,0,0), đỉnh S(0,0,4) và bán kính đáy 2."
        )]}, {"configurable": {"geometry_request_id": "live-docs-cone"}})
        tools = [m for m in state["messages"] if isinstance(m, ToolMessage)]
        self.assertTrue(any(m.name == "search_geogebra_docs" for m in tools))
        read = [json.loads(m.content) for m in tools if m.name == "get_command_docs"]
        self.assertTrue(any(r.get("command") == "Cone" and "<Radius>" in r.get("content", "") for r in read), read)
        self.assertLessEqual(state["geometry_docs_calls"], 8)
        for message in tools:
            if message.name == "prepare_geometry":
                result = json.loads(message.content)
                if result.get("status") == "prepared":
                    self.assertTrue(any(s['op'] == 'command' and s['name'] == 'Cone' for s in result['artifact']['spec']['steps']),
                                    'a cone must be created by a real command, not just point samples')
        print(f"live documentation: Vietnamese cone request retrieved Cone with {state['geometry_docs_calls']} bounded lookup(s)", flush=True)

    def test_sphere_example_includes_a_surface_and_tangent(self):
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        name = os.getenv("GEOMETRY_MODEL_NAME") or os.getenv("SUPERVISOR_MODEL_NAME", "gemma4:31b-cloud")
        model = build_ollama_chat_model(name)
        model.request_timeout = 60
        model.max_retries = 0
        from agents.supervisor_agent import build_supervisor
        graph = build_supervisor(model=model, agents=[build_geometry_agent(model)])
        state = graph.invoke({"messages": [
            HumanMessage(content="ví dụ phương trình tiếp tuyến với đường tròn hình cầu"),
            AIMessage(content="Bạn muốn đường tròn 2D hay mặt cầu 3D, phương trình nào, tiếp tuyến theo phương nào, và viết phương trình hay vẽ hình?"),
            HumanMessage(content="bài toán mặt cầu, giúp mình tạo ra 1 phương trình ví dụ nào cũng được, tiếp tuyến có hệ số góc, phương cho trước, mục tiêu là cả 2"),
        ]}, {"recursion_limit": 50, "configurable": {"geometry_request_id": "live-sphere-example"}})
        results = [json.loads(m.content) for m in state["messages"] if isinstance(m, ToolMessage) and m.name == "prepare_geometry"]
        artifacts = [r["artifact"] for r in results if r.get("status") == "prepared"]
        self.assertEqual(len(artifacts), 1, results)
        artifact = artifacts[0]
        self.assertEqual(artifact["app"], "3d")
        self.assertTrue({"sphere", "line"} <= {step["op"] for step in artifact["spec"]["steps"]})
        steps = artifact["spec"]["steps"]
        points = {s["id"]: s["coords"] for s in steps if s["op"] == "point"}
        sphere = next(s for s in steps if s["op"] == "sphere")
        center = points[sphere["center"]]
        radius = sphere.get("radius") or math.dist(center, points[sphere["through"]])
        tangent_lines = []
        for step in steps:
            if step["op"] != "line" or step["a"] not in points or step["b"] not in points:
                continue
            a, b = points[step["a"]], points[step["b"]]
            direction = [b[i] - a[i] for i in range(3)]
            offset = [center[i] - a[i] for i in range(3)]
            length_squared = sum(v*v for v in direction)
            if length_squared == 0:
                continue
            parameter = sum(direction[i]*offset[i] for i in range(3)) / length_squared
            nearest = [a[i] + parameter*direction[i] for i in range(3)]
            if math.isclose(math.dist(center, nearest), radius, rel_tol=1e-8, abs_tol=1e-8):
                tangent_lines.append(step["id"])
        self.assertTrue(tangent_lines, "a coordinate axis or a tangent plane cannot replace the requested tangent line")
        output = os.getenv("GEOGEBRA_SPHERE_ARTIFACT")
        if output:
            Path(output).write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"live sphere: supervisor preserved tangent line(s) {tangent_lines}", flush=True)

    def assert_vertical_intersection(self, spec, x):
        points = {s["id"]: s["coords"] for s in spec["steps"] if s["op"] == "point"}
        verticals, axes = set(), set()
        for step in spec["steps"]:
            if step["op"] != "line":
                continue
            a, b = points[step["a"]], points[step["b"]]
            if a[0] == b[0] == x and a[1] != b[1]:
                verticals.add(step["id"])
            if a[1] == b[1] == 0 and a[0] != b[0]:
                axes.add(step["id"])
        self.assertTrue(verticals, f"missing vertical line x={x}: {spec['steps']}")
        self.assertTrue(axes, "missing construction of Ox")
        self.assertTrue(any(
            step["op"] == "intersection" and (
                step["a"] in verticals and step["b"] in axes
                or step["b"] in verticals and step["a"] in axes
            ) for step in spec["steps"]
        ), "intersection must reference the vertical line and Ox")

    def test_one_conversation_switches_from_2d_to_3d_and_back(self):
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        name = os.getenv("GEOMETRY_MODEL_NAME") or os.getenv("SUPERVISOR_MODEL_NAME", "gemma4:31b-cloud")
        model = build_ollama_chat_model(name)
        model.request_timeout = 60
        model.max_retries = 0
        graph = build_geometry_agent(model)
        state = {"messages": []}
        artifacts = []
        requests = [
            ("Vẽ trong mặt phẳng Oxy đường thẳng d qua A(2,0), song song trục tung; đánh dấu giao điểm với Ox.", "graphing", {"point", "line", "intersection"}),
            ("Giờ chuyển sang hình học không gian Oxyz. Dựng tứ diện A(0,0,0), B(4,0,0), C(0,4,0), D(0,0,4); dựng M trung điểm AB và tam giác BCD.", "3d", {"point", "midpoint", "polygon"}),
            ("Quay lại mặt phẳng Oxy: vẽ y=x^2 trên [-3,3] và đường thẳng x=-1; đánh dấu giao điểm của đường thẳng với Ox.", "graphing", {"point", "line", "intersection", "function2d"}),
        ]
        for index, (prompt, app, operations) in enumerate(requests):
            with self.subTest(turn=index + 1, app=app):
                before = len(state["messages"])
                state = graph.invoke(
                    {**state, "messages": [*state["messages"], HumanMessage(content=prompt)]},
                    {"configurable": {"geometry_request_id": f"live-switch-{index}"}},
                )
                results = [json.loads(m.content) for m in state["messages"][before:] if isinstance(m, ToolMessage)]
                prepared = [r["artifact"] for r in results if r.get("status") == "prepared"]
                self.assertEqual(len(prepared), 1, results)
                artifact = prepared[0]
                artifacts.append(artifact)
                self.assertEqual(artifact["app"], app)
                self.assertTrue(operations <= {s["op"] for s in artifact["spec"]["steps"]})
                spec = artifact["spec"]
                if index in (0, 2):
                    self.assert_vertical_intersection(spec, 2 if index == 0 else -1)
                if index == 1:
                    points = {s["id"]: s["coords"] for s in spec["steps"] if s["op"] == "point"}
                    self.assertEqual({k: points[k] for k in ("A", "B", "C", "D")}, {
                        "A": [0, 0, 0], "B": [4, 0, 0], "C": [0, 4, 0], "D": [0, 0, 4],
                    })
                    self.assertTrue(any(s["op"] == "midpoint" and {s["a"], s["b"]} == {"A", "B"} for s in spec["steps"]))
                    self.assertTrue(any(s["op"] == "polygon" and set(s["points"]) == {"B", "C", "D"} for s in spec["steps"]))
                if index == 2:
                    functions = [s for s in spec["steps"] if s["op"] == "function2d"]
                    self.assertEqual(len(functions), 1)
                    self.assertEqual(functions[0]["domain"], [-3, 3])
                print(f"live geometry turn {index + 1}: {app}, {state['geometry_attempts']} preparation attempt(s)", flush=True)
        output = os.getenv("GEOGEBRA_LIVE_ARTIFACTS")
        if output:
            Path(output).write_text(json.dumps(artifacts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
