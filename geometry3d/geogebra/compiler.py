"""Deterministic compiler from validated constructions to GeoGebra commands."""

from __future__ import annotations

from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .expressions import ExpressionNode, parse_expression
from .schema import ConstructionSpec, Given
from .validation import ValidatedConstruction


class CommandStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_step_id: str
    commands: list[str]
    expected_labels: list[str]


class GeometryArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(default_factory=lambda: str(uuid4()))
    version: Literal[1] = 1
    app: Literal["graphing", "3d"]
    title: str
    givens: list[Given]
    goals: list[str]
    display_choices: list[str]
    steps: list[CommandStep]
    spec: ConstructionSpec


def _number(value: float) -> str:
    return repr(float(value))


def _expression(node: ExpressionNode, rename: dict[str, str] | None = None) -> str:
    rename = rename or {}
    if node.kind == "number":
        return repr(node.value)
    if node.kind == "name":
        return rename.get(str(node.value), str(node.value))
    if node.kind == "binary":
        return f"({_expression(node.children[0], rename)} {node.value} {_expression(node.children[1], rename)})"
    if node.kind == "unary":
        return f"({node.value}{_expression(node.children[0], rename)})"
    if node.kind == "call":
        name = "ln" if node.value == "log" else node.value
        return f"{name}({_expression(node.children[0], rename)})"
    raise ValueError(f"unknown expression node {node.kind!r}")


def compile_construction(validated: ValidatedConstruction) -> GeometryArtifact:
    command_steps: list[CommandStep] = []
    for step in validated.steps:
        commands: list[str]
        expected = [step.id]
        if step.op == "point":
            commands = [f"{step.id}=({_number(step.coords[0])},{_number(step.coords[1])},{_number(step.coords[2])})"]
        elif step.op == "segment":
            commands = [f"{step.id}=Segment({step.a},{step.b})"]
        elif step.op == "line":
            commands = [f"{step.id}=Line({step.a},{step.b})"]
        elif step.op == "polygon":
            commands = [f"{step.id}=Polygon({','.join(step.points)})"]
        elif step.op == "plane":
            commands = [f"{step.id}=Plane({','.join(step.points)})"]
        elif step.op == "midpoint":
            commands = [f"{step.id}=Midpoint({step.a},{step.b})"]
        elif step.op == "intersection":
            commands = [f"{step.id}=Intersect({step.a},{step.b})"]
        elif step.op == "projection":
            target_kind = validated.kinds[step.target]
            if target_kind == "line":
                commands = [f"{step.id}=ClosestPoint({step.target},{step.point})"]
            else:
                helper = f"ggbAux{len(command_steps) + 1}"
                commands = [f"{helper}=PerpendicularLine({step.point},{step.target})", f"{step.id}=Intersect({helper},{step.target})"]
                expected = [helper, step.id]
        elif step.op == "function2d":
            expression = _expression(parse_expression(step.expression, frozenset({"x"})))
            start, end = (_number(step.domain[0]), _number(step.domain[1]))
            commands = [f"{step.id}(x)=If({start}<=x<={end},{expression})"]
        elif step.op == "surface_explicit":
            expression = _expression(parse_expression(step.expression, frozenset({"x", "y"})), {"x": "u", "y": "v"})
            commands = [f"{step.id}=Surface(u,v,{expression},u,{_number(step.x_domain[0])},{_number(step.x_domain[1])},v,{_number(step.y_domain[0])},{_number(step.y_domain[1])})"]
        else:  # validated schemas make this unreachable
            raise ValueError(f"unsupported operation {step.op!r}")
        command_steps.append(CommandStep(source_step_id=step.id, commands=commands, expected_labels=expected))

    spec = validated.spec
    return GeometryArtifact(app=spec.app, title=spec.title, givens=spec.givens, goals=spec.goals, display_choices=spec.display_choices, steps=command_steps, spec=spec)
