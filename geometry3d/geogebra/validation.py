"""Reference, dependency and kind validation for construction specs."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError

from .expressions import ExpressionError, parse_expression
from .schema import ConstructionSpec, PointStep, Step
from .commands import command_references, validate_command


RESERVED = frozenset({"x", "y", "z", "u", "v", "e", "pi", "sin", "cos", "tan", "exp", "log", "sqrt", "abs", "point", "segment", "line", "polygon", "plane", "midpoint", "intersection", "projection", "function2d", "surface_explicit", "sphere"})


class SpecError(ValueError):
    def __init__(self, code: str, step_id: str | None, message: str):
        super().__init__(message)
        self.code = code
        self.step_id = step_id


@dataclass(frozen=True)
class ValidatedConstruction:
    spec: ConstructionSpec
    steps: tuple[Step, ...]
    kinds: dict[str, str]


def _references(step: Step) -> tuple[str, ...]:
    if step.op == "command":
        return command_references(step)
    if step.op in {"segment", "line", "midpoint", "intersection"}:
        return (step.a, step.b)
    if step.op in {"polygon", "plane"}:
        return tuple(step.points)
    if step.op == "projection":
        return (step.point, step.target)
    if step.op == "sphere":
        return (step.center, step.through) if step.through is not None else (step.center,)
    return ()


def _output_kind(step: Step, kinds: dict[str, str]) -> str:
    if step.op == 'command':
        return 'object'  # GeoGebra validates the dynamic output type at execution.
    if step.op in {"point", "midpoint", "projection"}:
        return "point"
    if step.op in {"segment", "line"}:
        return step.op
    if step.op in {"polygon", "plane", "function2d", "surface_explicit", "sphere"}:
        return step.op
    pair = {kinds[step.a], kinds[step.b]}
    if pair == {"plane"}:
        return "line"
    return "point"


def _require(step: Step, kinds: dict[str, str], ref: str, allowed: set[str]):
    if kinds[ref] not in allowed:
        raise SpecError("wrong_kind", step.id, f"{ref!r} has kind {kinds[ref]!r}, expected one of {sorted(allowed)}")


def validate_spec(raw: dict) -> ValidatedConstruction:
    raw_steps = raw.get("steps", []) if isinstance(raw, dict) else []
    if isinstance(raw_steps, list):
        for item in raw_steps:
            raw_id = item.get("id") if isinstance(item, dict) else None
            if isinstance(raw_id, str) and raw_id.startswith("ggbAux"):
                raise SpecError("reserved_id", raw_id, f"reserved step id {raw_id!r}")
    try:
        spec = ConstructionSpec.model_validate(raw)
    except ValidationError as exc:
        code = "invalid_spec"
        for error in exc.errors():
            if error.get("type") == "too_long" and tuple(error.get("loc", ())) == ("steps",):
                code = "invalid_spec"
        raise SpecError(code, None, str(exc)) from exc

    by_id: dict[str, Step] = {}
    for step in spec.steps:
        if step.id in by_id:
            raise SpecError("duplicate_id", step.id, f"duplicate step id {step.id!r}")
        if step.id in RESERVED or step.id.startswith("ggbAux"):
            raise SpecError("reserved_id", step.id, f"reserved step id {step.id!r}")
        if step.op == 'command':
            try:
                validate_command(step)
            except (OSError, ValueError, KeyError) as exc:
                raise SpecError('invalid_command', step.id, str(exc)) from exc
        by_id[step.id] = step

    dependencies: dict[str, set[str]] = {}
    for step in spec.steps:
        refs = set(_references(step))
        missing = sorted(refs - by_id.keys())
        if missing:
            raise SpecError("missing_reference", step.id, f"unknown references: {missing}")
        dependencies[step.id] = refs

    ordered: list[Step] = []
    remaining = {key: set(value) for key, value in dependencies.items()}
    while remaining:
        ready = [step.id for step in spec.steps if step.id in remaining and not remaining[step.id]]
        if not ready:
            raise SpecError("cycle", None, "construction dependencies contain a cycle")
        for step_id in ready:
            ordered.append(by_id[step_id])
            remaining.pop(step_id)
            for refs in remaining.values():
                refs.discard(step_id)

    kinds: dict[str, str] = {}
    for step in ordered:
        if step.op in {"segment", "line", "midpoint"}:
            _require(step, kinds, step.a, {"point"})
            _require(step, kinds, step.b, {"point"})
            if step.op == "line":
                a, b = by_id[step.a], by_id[step.b]
                same_coords = (
                    isinstance(a, PointStep) and isinstance(b, PointStep)
                    and (*a.coords[:2], a.coords[2] if len(a.coords) == 3 else 0)
                    == (*b.coords[:2], b.coords[2] if len(b.coords) == 3 else 0)
                )
                if step.a == step.b or same_coords:
                    raise SpecError("degenerate_line", step.id, "a line requires two distinct points; choose a second point along its direction")
        elif step.op in {"polygon", "plane"}:
            for ref in step.points:
                _require(step, kinds, ref, {"point"})
        elif step.op == "projection":
            _require(step, kinds, step.point, {"point"})
            _require(step, kinds, step.target, {"line", "plane"})
        elif step.op == "sphere":
            _require(step, kinds, step.center, {"point"})
            if step.through is not None:
                _require(step, kinds, step.through, {"point"})
                center, through = by_id[step.center], by_id[step.through]
                if step.center == step.through or (
                    isinstance(center, PointStep) and isinstance(through, PointStep)
                    and center.coords == through.coords
                ):
                    raise SpecError("degenerate_sphere", step.id, "the point on a sphere must differ from its center")
        elif step.op == "intersection":
            pair = {kinds[step.a], kinds[step.b]}
            if pair not in ({"line"}, {"line", "plane"}, {"plane"}):
                raise SpecError("wrong_kind", step.id, f"unsupported intersection kinds {sorted(pair)}")
        elif step.op == "function2d":
            try:
                parse_expression(step.expression, frozenset({"x"}))
            except ExpressionError as exc:
                raise SpecError(exc.code, step.id, str(exc)) from exc
            if not step.domain[0] < step.domain[1]:
                raise SpecError("invalid_domain", step.id, "domain start must be less than end")
        elif step.op == "surface_explicit":
            try:
                parse_expression(step.expression, frozenset({"x", "y"}))
            except ExpressionError as exc:
                raise SpecError(exc.code, step.id, str(exc)) from exc
            if not step.x_domain[0] < step.x_domain[1] or not step.y_domain[0] < step.y_domain[1]:
                raise SpecError("invalid_domain", step.id, "surface domains must be increasing")
        kinds[step.id] = _output_kind(step, kinds)

    return ValidatedConstruction(spec=spec, steps=tuple(ordered), kinds=kinds)
