"""Versioned schema for model-proposed GeoGebra constructions."""

from __future__ import annotations

import math
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Id = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,31}$")]
Domain = tuple[float, float]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Given(StrictModel):
    text: Annotated[str, Field(min_length=1, max_length=1000)]
    source_text: Annotated[str, Field(min_length=1, max_length=2000)]


class PointStep(StrictModel):
    id: Id
    op: Literal["point"]
    coords: tuple[float, float, float]

    @field_validator("coords", mode="before")
    @classmethod
    def strict_coords(cls, value):
        if not isinstance(value, (list, tuple)) or len(value) != 3 or any(type(x) not in (int, float) for x in value):
            raise ValueError("coordinates must contain exactly three real numbers")
        try:
            finite = all(math.isfinite(float(x)) for x in value)
        except OverflowError:
            finite = False
        if not finite:
            raise ValueError("coordinates must be finite")
        return value


class PairStep(StrictModel):
    id: Id
    a: Id
    b: Id


class SegmentStep(PairStep): op: Literal["segment"]
class LineStep(PairStep): op: Literal["line"]
class MidpointStep(PairStep): op: Literal["midpoint"]
class IntersectionStep(PairStep): op: Literal["intersection"]


class PolygonStep(StrictModel):
    id: Id
    op: Literal["polygon"]
    points: Annotated[list[Id], Field(min_length=3, max_length=100)]


class PlaneStep(StrictModel):
    id: Id
    op: Literal["plane"]
    points: tuple[Id, Id, Id]


class ProjectionStep(StrictModel):
    id: Id
    op: Literal["projection"]
    point: Id
    target: Id


class Function2DStep(StrictModel):
    id: Id
    op: Literal["function2d"]
    expression: str
    domain: Domain


class SurfaceStep(StrictModel):
    id: Id
    op: Literal["surface_explicit"]
    expression: str
    x_domain: Domain
    y_domain: Domain


Step = Annotated[Union[PointStep, SegmentStep, LineStep, PolygonStep, PlaneStep, MidpointStep, IntersectionStep, ProjectionStep, Function2DStep, SurfaceStep], Field(discriminator="op")]


class ConstructionSpec(StrictModel):
    version: Literal[1]
    title: Annotated[str, Field(min_length=1, max_length=500)]
    app: Literal["graphing", "3d"]
    givens: list[Given] = Field(default_factory=list, max_length=100)
    goals: list[Annotated[str, Field(min_length=1, max_length=1000)]] = Field(default_factory=list, max_length=100)
    display_choices: list[Annotated[str, Field(min_length=1, max_length=1000)]] = Field(default_factory=list, max_length=100)
    steps: list[Step] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def app_supports_steps(self):
        if self.app == "graphing" and any(step.op != "function2d" for step in self.steps):
            raise ValueError("graphing app only supports function2d steps")
        if any(step.op == "surface_explicit" for step in self.steps) and self.app != "3d":
            raise ValueError("surface_explicit requires the 3d app")
        return self
