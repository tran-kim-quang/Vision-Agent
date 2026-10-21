"""Versioned schema for model-proposed GeoGebra constructions."""

from __future__ import annotations

import math
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints, field_validator, model_validator


Id = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,31}$")]
Domain = tuple[float, float]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Given(StrictModel):
    text: Annotated[str, Field(min_length=1, max_length=1000)]
    source_text: Annotated[str, Field(min_length=1, max_length=2000)]


class ConstructionStep(StrictModel):
    caption: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)] | None = None
    fill_opacity: Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)] | None = None


class PointStep(ConstructionStep):
    id: Id
    op: Literal["point"]
    coords: tuple[float, float] | tuple[float, float, float]

    @field_validator("coords", mode="before")
    @classmethod
    def strict_coords(cls, value):
        if not isinstance(value, (list, tuple)) or len(value) not in (2, 3) or any(type(x) not in (int, float) for x in value):
            raise ValueError("coordinates must contain two or three real numbers")
        try:
            finite = all(math.isfinite(float(x)) for x in value)
        except OverflowError:
            finite = False
        if not finite:
            raise ValueError("coordinates must be finite")
        return value


class PairStep(ConstructionStep):
    id: Id
    a: Id
    b: Id


class SegmentStep(PairStep): op: Literal["segment"]
class LineStep(PairStep): op: Literal["line"]
class MidpointStep(PairStep): op: Literal["midpoint"]
class IntersectionStep(PairStep): op: Literal["intersection"]


class PolygonStep(ConstructionStep):
    id: Id
    op: Literal["polygon"]
    points: Annotated[list[Id], Field(min_length=3, max_length=100)]


class PlaneStep(ConstructionStep):
    id: Id
    op: Literal["plane"]
    points: tuple[Id, Id, Id]


class ProjectionStep(ConstructionStep):
    id: Id
    op: Literal["projection"]
    point: Id
    target: Id


class Function2DStep(ConstructionStep):
    id: Id
    op: Literal["function2d"]
    expression: str
    domain: Domain


class SurfaceStep(ConstructionStep):
    id: Id
    op: Literal["surface_explicit"]
    expression: str
    x_domain: Domain
    y_domain: Domain


class SphereStep(ConstructionStep):
    id: Id
    op: Literal["sphere"]
    center: Id
    radius: Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)] | None = None
    through: Id | None = None

    @model_validator(mode="after")
    def radius_or_point(self):
        if (self.radius is None) == (self.through is None):
            raise ValueError("sphere requires exactly one of radius or through")
        return self


class ReferenceArgument(StrictModel):
    ref: Id


class NumberArgument(StrictModel):
    number: Annotated[float, Field(strict=True, allow_inf_nan=False)]


class BooleanArgument(StrictModel):
    boolean: StrictBool


class ExpressionArgument(StrictModel):
    expression: Annotated[str, Field(min_length=1, max_length=500)]


class ListArgument(StrictModel):
    items: Annotated[list["CommandArgument"], Field(max_length=100)]


CommandArgument = Union[ReferenceArgument, NumberArgument, BooleanArgument, ExpressionArgument, ListArgument]
ListArgument.model_rebuild()


class DocumentedCommandStep(ConstructionStep):
    id: Id
    op: Literal["command"]
    name: Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,63}$")]
    args: Annotated[list[CommandArgument], Field(max_length=32)]


Step = Annotated[Union[PointStep, SegmentStep, LineStep, PolygonStep, PlaneStep, MidpointStep, IntersectionStep, ProjectionStep, Function2DStep, SurfaceStep, SphereStep, DocumentedCommandStep], Field(discriminator="op")]


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
        for step in self.steps:
            if self.app == "graphing" and step.op in {"plane", "surface_explicit", "sphere"}:
                raise ValueError(f"{step.op} requires the 3d app")
            if step.op == "point":
                if self.app == "3d" and len(step.coords) != 3:
                    raise ValueError("3d points require coords:[x,y,z]")
                if self.app == "graphing" and len(step.coords) == 3 and step.coords[2] != 0:
                    raise ValueError("graphing points require coords:[x,y] or [x,y,0]; use 3d for spatial points")
        return self
