# -*- coding: utf-8 -*-
"""Declarative, validated scene graph for textbook geometry SVG figures.

The v1 :mod:`core.figure_svg` module intentionally consists of small SVG
string helpers.  This module adds a deterministic scene layer on top of those
helpers: named geometry, semantic validation, automatic point-label placement,
and automatic canvas fitting.  Coordinates follow SVG's convention (``y``
increases downwards), while angles passed to :meth:`FigureScene.point_on_circle`
are mathematical angles (positive counter-clockwise).

Only the Python standard library and ``core.figure_svg`` are used here.  The
resulting SVG therefore remains usable by the existing resvg/lint pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from html import escape
import math
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from core.figure_svg import angle_arc, circle_pt, isect


Number = int | float
Box = tuple[float, float, float, float]
_EPS = 1.0e-9
_SAFE_PAINT_NAMES = {
    "black", "white", "gray", "grey", "red", "green", "blue", "yellow",
    "orange", "purple", "brown", "pink", "navy", "teal", "maroon",
    "silver", "lime", "aqua", "fuchsia",
}


class GeometryValidationError(ValueError):
    """Raised when a scene is geometrically invalid or internally inconsistent."""


class FigureSpecError(ValueError):
    """Raised when a declarative FigureSpec is malformed or has unknown refs."""


@dataclass(frozen=True, slots=True)
class Point:
    """A resolved named point.

    ``kind`` is one of ``raw``, ``on_circle``, or ``intersection``.  The
    reference metadata is retained so :meth:`FigureScene.validate` can verify
    the construction instead of trusting its cached coordinates.
    """

    name: str
    x: float
    y: float
    kind: str = "raw"
    circle_ref: str | None = None
    angle_deg: float | None = None
    segment_refs: tuple[str, str] | None = None

    def as_tuple(self) -> tuple[float, float]:
        """Return ``(x, y)`` for compatibility with ``core.figure_svg`` helpers."""

        return (self.x, self.y)

    def __iter__(self):
        # Lets existing helpers accept Point anywhere they accept a two-tuple.
        yield self.x
        yield self.y


@dataclass(frozen=True, slots=True)
class StyleProfile:
    """Visual constants for a figure scene.

    ``exam-thin`` is calibrated for compact black-and-white Korean exam
    figures: restrained strokes, serif labels, and white text halos only where
    an angle label may cross geometry.
    """

    name: str = "exam-thin"
    stroke: str = "#111111"
    text_color: str = "#111111"
    circle_width: float = 1.35
    segment_width: float = 1.25
    mark_width: float = 1.0
    point_radius: float = 1.65
    show_points: bool = False
    font_family: str = "Times New Roman, Batang, serif"
    font_size: float = 13.0
    angle_font_size: float = 12.0
    label_offset: float = 11.5
    padding: float = 12.0
    angle_radius: float = 15.0
    angle_label_distance: float = 25.0
    dimension_width: float = 1.4        # figure_svg.meas 와 동일 규격
    dimension_font_size: float = 15.0   # figure_svg.dim_label 과 동일
    dimension_offset: float = 14.0
    dimension_dash: str = "6 4"         # figure_svg.meas 와 동일
    dimension_halo_width: float = 7.0
    halo_color: str = "#ffffff"
    halo_width: float = 4.5

    @classmethod
    def exam_thin(cls) -> "StyleProfile":
        """Return the built-in high-quality thin exam style."""

        return cls()

    @classmethod
    def from_theme(cls, theme: str) -> "StyleProfile":
        """Resolve a built-in theme name, rejecting silent fallbacks."""

        normalized = str(theme).strip().lower().replace("_", "-")
        if normalized != "exam-thin":
            raise FigureSpecError(f"unknown theme {theme!r}; expected 'exam-thin'")
        return cls.exam_thin()


@dataclass(frozen=True, slots=True)
class Canvas:
    """Optional fixed SVG canvas.  Omit it to auto-fit scene content."""

    width: float
    height: float


@dataclass(frozen=True, slots=True)
class Circle:
    """A named circle whose center is a named point."""

    name: str
    center: str
    radius: float


@dataclass(frozen=True, slots=True)
class Segment:
    """A named finite segment between two named points."""

    name: str
    p1: str
    p2: str
    dashed: str | None = None


@dataclass(frozen=True, slots=True)
class AngleMark:
    """A small-angle arc and optional text label."""

    name: str
    vertex: str
    p1: str
    p2: str
    radius: float | None = None
    label: str | None = None
    label_distance: float | None = None


@dataclass(frozen=True, slots=True)
class DimensionMark:
    """A curved dashed measurement mark attached to two named points.

    ``side`` is relative to the directed ``p1 -> p2`` segment in SVG
    coordinates.  ``left`` uses the positive cross-product normal and
    ``right`` the opposite normal; ``auto`` evaluates both sides.
    """

    name: str
    p1: str
    p2: str
    label: str
    side: str = "auto"
    offset: float | None = None
    # 인셋 기본 0 = 치수 양끝이 **잰 두 점에 정확히 닿는다**(figure_svg.meas 참고).
    # 3.0 은 짧은 구간에서 19% 를 깎아 '길이가 짧아 보인다' 지적을 받았다.
    inset: float = 0.0
    font_size: float | None = None


@dataclass(frozen=True, slots=True)
class DimensionLayout:
    """Resolved geometry for one :class:`DimensionMark`."""

    name: str
    side: str
    start: Point
    control: Point
    end: Point
    label_position: tuple[float, float]
    label_box: Box
    path_samples: tuple[Point, ...]
    font_size: float


@dataclass(frozen=True, slots=True)
class PointLabel:
    """A label attached to a named point."""

    point: str
    text: str
    position: str = "auto"
    dx: float | None = None
    dy: float | None = None
    font_size: float | None = None
    italic: bool = False


@dataclass(frozen=True, slots=True)
class ResolvedScene:
    """Inspectable layout result returned by :meth:`FigureScene.resolve`.

    Positions and boxes remain in scene coordinates.  ``translation`` is the
    offset applied during SVG emission; ``view_box`` is always ``(0, 0, w, h)``.
    """

    points: Mapping[str, Point]
    label_positions: Mapping[str, tuple[float, float]]
    label_boxes: Mapping[str, Box]
    dimension_layouts: Mapping[str, DimensionLayout]
    view_box: tuple[float, float, float, float]
    translation: tuple[float, float]
    content_bounds: Box

    @property
    def width(self) -> float:
        """Resolved canvas width."""

        return self.view_box[2]

    @property
    def height(self) -> float:
        """Resolved canvas height."""

        return self.view_box[3]


def _finite(value: Any, what: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise GeometryValidationError(f"{what} must be a finite number") from exc
    if not math.isfinite(number):
        raise GeometryValidationError(f"{what} must be finite, got {value!r}")
    return number


def _name(value: Any, what: str = "name") -> str:
    if not isinstance(value, str) or not value.strip():
        raise GeometryValidationError(f"{what} must be a non-empty string")
    return value.strip()


def _safe_paint(value: Any, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GeometryValidationError(f"{what} must be a non-empty safe color")
    color = value.strip()
    if (color.lower() not in _SAFE_PAINT_NAMES
            and not re.fullmatch(r"#[0-9A-Fa-f]{3,4}|#[0-9A-Fa-f]{6}|#[0-9A-Fa-f]{8}", color)):
        raise GeometryValidationError(
            f"{what} must be a named or hexadecimal color without references")
    return color


def _fmt(value: float) -> str:
    if abs(value) < 0.0000005:
        value = 0.0
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return text or "0"


def _distance_point_line(point: Point, a: Point, b: Point) -> float:
    length = math.hypot(b.x - a.x, b.y - a.y)
    if length <= _EPS:
        return math.inf
    return abs((b.x - a.x) * (a.y - point.y) - (a.x - point.x) * (b.y - a.y)) / length


def _point_within_segment(point: Point, a: Point, b: Point, tolerance: float) -> bool:
    """Return whether ``point`` lies within the finite extent of ``a``--``b``."""

    dx, dy = b.x - a.x, b.y - a.y
    length_sq = dx * dx + dy * dy
    if length_sq <= _EPS * _EPS:
        return False
    parameter = ((point.x - a.x) * dx + (point.y - a.y) * dy) / length_sq
    parameter_tolerance = tolerance / math.sqrt(length_sq)
    return -parameter_tolerance <= parameter <= 1.0 + parameter_tolerance


def _text_box(x: float, baseline_y: float, text: str, font_size: float) -> Box:
    # Deliberately a little conservative; this is collision/layout geometry,
    # not a font renderer.  CJK glyphs are approximately one em wide.
    width_units = sum(1.0 if ord(ch) > 0x2FF else 0.61 for ch in text)
    width = max(0.62, width_units) * font_size
    return (x - width / 2.0, baseline_y - 0.83 * font_size,
            x + width / 2.0, baseline_y + 0.25 * font_size)


def _boxes_overlap(a: Box, b: Box, gap: float = 0.0) -> bool:
    return not (a[2] + gap <= b[0] or b[2] + gap <= a[0]
                or a[3] + gap <= b[1] or b[3] + gap <= a[1])


def _point_in_box(x: float, y: float, box: Box, margin: float = 0.0) -> bool:
    return (box[0] - margin <= x <= box[2] + margin
            and box[1] - margin <= y <= box[3] + margin)


def _orientation(ax: float, ay: float, bx: float, by: float,
                 cx: float, cy: float) -> float:
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)


def _segment_intersects_box(a: Point, b: Point, box: Box) -> bool:
    if _point_in_box(a.x, a.y, box) or _point_in_box(b.x, b.y, box):
        return True
    x0, y0, x1, y1 = box
    edges = (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)),
             ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0)))

    def crosses(c: tuple[float, float], d: tuple[float, float]) -> bool:
        o1 = _orientation(a.x, a.y, b.x, b.y, *c)
        o2 = _orientation(a.x, a.y, b.x, b.y, *d)
        o3 = _orientation(*c, *d, a.x, a.y)
        o4 = _orientation(*c, *d, b.x, b.y)
        return ((o1 <= _EPS and o2 >= -_EPS) or (o2 <= _EPS and o1 >= -_EPS)) and \
               ((o3 <= _EPS and o4 >= -_EPS) or (o4 <= _EPS and o3 >= -_EPS))

    return any(crosses(c, d) for c, d in edges)


def _expand_box(box: Box, amount: float) -> Box:
    return (box[0] - amount, box[1] - amount,
            box[2] + amount, box[3] + amount)


def _segments_intersect(a: Point, b: Point, c: Point, d: Point,
                        tolerance: float = 1.0e-8) -> bool:
    """Return whether two finite segments intersect, including tangency."""

    def orient(p: Point, q: Point, r: Point) -> float:
        return _orientation(p.x, p.y, q.x, q.y, r.x, r.y)

    def on_segment(p: Point, q: Point, r: Point) -> bool:
        return (min(p.x, r.x) - tolerance <= q.x <= max(p.x, r.x) + tolerance
                and min(p.y, r.y) - tolerance <= q.y <= max(p.y, r.y) + tolerance)

    o1, o2 = orient(a, b, c), orient(a, b, d)
    o3, o4 = orient(c, d, a), orient(c, d, b)
    if ((o1 > tolerance and o2 < -tolerance)
            or (o1 < -tolerance and o2 > tolerance)) and \
       ((o3 > tolerance and o4 < -tolerance)
            or (o3 < -tolerance and o4 > tolerance)):
        return True
    return ((abs(o1) <= tolerance and on_segment(a, c, b))
            or (abs(o2) <= tolerance and on_segment(a, d, b))
            or (abs(o3) <= tolerance and on_segment(c, a, d))
            or (abs(o4) <= tolerance and on_segment(c, b, d)))


def _distance_xy_to_segment(x: float, y: float, a: Point, b: Point) -> float:
    dx, dy = b.x - a.x, b.y - a.y
    length_sq = dx * dx + dy * dy
    if length_sq <= _EPS * _EPS:
        return math.hypot(x - a.x, y - a.y)
    t = max(0.0, min(1.0, ((x - a.x) * dx + (y - a.y) * dy) / length_sq))
    return math.hypot(x - (a.x + t * dx), y - (a.y + t * dy))


def _quadratic_samples(name: str, start: Point, control: Point, end: Point,
                       count: int = 25) -> tuple[Point, ...]:
    """Sample a quadratic Bezier deterministically for collision/layout QA."""

    samples: list[Point] = []
    for index in range(count):
        t = index / (count - 1)
        mt = 1.0 - t
        x = mt * mt * start.x + 2.0 * mt * t * control.x + t * t * end.x
        y = mt * mt * start.y + 2.0 * mt * t * control.y + t * t * end.y
        samples.append(Point(f"{name}@{index}", x, y))
    return tuple(samples)


def _lerp_point(name: str, first: Point, second: Point, t: float) -> Point:
    return Point(name, first.x + (second.x - first.x) * t,
                 first.y + (second.y - first.y) * t)


def _dimension_gapped_path(layout: DimensionLayout, tx: float, ty: float) -> str:
    """Return two smooth quadratic subpaths with a real label-width gap.

    Relying only on a white halo can leave a clipped dash looking like a comma
    beside ``7 cm``.  De Casteljau subdivision removes the covered middle of
    the curve while preserving exact quadratic smoothness on both sides.
    """

    if not _polyline_intersects_box(layout.path_samples, layout.label_box):
        return (
            f"M {_fmt(layout.start.x + tx)} {_fmt(layout.start.y + ty)} "
            f"Q {_fmt(layout.control.x + tx)} {_fmt(layout.control.y + ty)} "
            f"{_fmt(layout.end.x + tx)} {_fmt(layout.end.y + ty)}"
        )

    dx, dy = layout.end.x - layout.start.x, layout.end.y - layout.start.y
    visible_length = max(_EPS, math.hypot(dx, dy))
    ux, uy = dx / visible_length, dy / visible_length
    box_width = layout.label_box[2] - layout.label_box[0]
    box_height = layout.label_box[3] - layout.label_box[1]
    half_projection = (abs(ux) * box_width + abs(uy) * box_height) / 2.0
    delta = min(0.42, max(0.04, half_projection / visible_length + 0.015))
    left_t, right_t = 0.5 - delta, 0.5 + delta

    left_01 = _lerp_point("left:01", layout.start, layout.control, left_t)
    left_12 = _lerp_point("left:12", layout.control, layout.end, left_t)
    left_gap = _lerp_point("left:gap", left_01, left_12, left_t)

    right_01 = _lerp_point("right:01", layout.start, layout.control, right_t)
    right_12 = _lerp_point("right:12", layout.control, layout.end, right_t)
    right_gap = _lerp_point("right:gap", right_01, right_12, right_t)

    return (
        f"M {_fmt(left_gap.x + tx)} {_fmt(left_gap.y + ty)} "
        f"Q {_fmt(left_01.x + tx)} {_fmt(left_01.y + ty)} "
        f"{_fmt(layout.start.x + tx)} {_fmt(layout.start.y + ty)} "
        f"M {_fmt(right_gap.x + tx)} {_fmt(right_gap.y + ty)} "
        f"Q {_fmt(right_12.x + tx)} {_fmt(right_12.y + ty)} "
        f"{_fmt(layout.end.x + tx)} {_fmt(layout.end.y + ty)}"
    )


def _polyline_intersects_box(samples: Sequence[Point], box: Box) -> bool:
    return any(_segment_intersects_box(a, b, box)
               for a, b in zip(samples, samples[1:]))


def _polylines_intersect(first: Sequence[Point], second: Sequence[Point]) -> bool:
    return any(_segments_intersect(a, b, c, d)
               for a, b in zip(first, first[1:])
               for c, d in zip(second, second[1:]))


def _polyline_intersects_segment(samples: Sequence[Point], a: Point, b: Point) -> bool:
    return any(_segments_intersect(p, q, a, b)
               for p, q in zip(samples, samples[1:]))


def _box_intersects_circle(box: Box, center: Point, radius: float,
                           padding: float = 0.0) -> bool:
    """Conservative rectangle/circumference intersection test."""

    x0, y0, x1, y1 = _expand_box(box, padding)
    nearest_x = max(x0, min(center.x, x1))
    nearest_y = max(y0, min(center.y, y1))
    minimum = math.hypot(nearest_x - center.x, nearest_y - center.y)
    maximum = max(math.hypot(x - center.x, y - center.y)
                  for x in (x0, x1) for y in (y0, y1))
    return minimum <= radius + padding and maximum >= radius - padding


def _merge_bounds(boxes: Iterable[Box]) -> Box:
    materialized = list(boxes)
    if not materialized:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(box[0] for box in materialized), min(box[1] for box in materialized),
            max(box[2] for box in materialized), max(box[3] for box in materialized))


@dataclass
class FigureScene:
    """Mutable builder for an otherwise value-oriented geometry scene.

    All stored primitives are frozen dataclasses.  ``add_*`` methods mutate the
    scene and return ``self`` for fluent construction; callers that require a
    stable hand-off can use :meth:`copy`.
    """

    style: StyleProfile = field(default_factory=StyleProfile.exam_thin)
    canvas: Canvas | tuple[Number, Number] | None = None
    background: str = "white"
    points: dict[str, Point] = field(default_factory=dict, init=False)
    circles: dict[str, Circle] = field(default_factory=dict, init=False)
    segments: dict[str, Segment] = field(default_factory=dict, init=False)
    angles: dict[str, AngleMark] = field(default_factory=dict, init=False)
    dimensions: dict[str, DimensionMark] = field(default_factory=dict, init=False)
    labels: dict[str, PointLabel] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.style, StyleProfile):
            raise TypeError("style must be a StyleProfile")
        if self.canvas is not None and not isinstance(self.canvas, Canvas):
            if (isinstance(self.canvas, Sequence) and not isinstance(self.canvas, (str, bytes))
                    and len(self.canvas) == 2):
                self.canvas = Canvas(float(self.canvas[0]), float(self.canvas[1]))
            else:
                raise TypeError("canvas must be Canvas, (width, height), or None")
        normalized = self.background.strip().lower() if isinstance(self.background, str) else ""
        if normalized in {"none", "transparent"}:
            self.background = "transparent"
        elif normalized in {"white", "#fff", "#ffffff"}:
            self.background = "white"
        else:
            raise GeometryValidationError("background must be 'white' or 'transparent'")

    @property
    def theme(self) -> str:
        """Theme identifier exposed for declarative-tooling inspection."""

        return self.style.name

    def copy(self) -> "FigureScene":
        """Return an independent shallow-value copy of this scene."""

        scene = FigureScene(style=self.style, canvas=self.canvas, background=self.background)
        scene.points.update(self.points)
        scene.circles.update(self.circles)
        scene.segments.update(self.segments)
        scene.angles.update(self.angles)
        scene.dimensions.update(self.dimensions)
        scene.labels.update(self.labels)
        return scene

    def _ensure_global_new(self, name: str, kind: str) -> None:
        """Keep geometry names unambiguous across all primitive namespaces."""

        for existing_kind, collection in (
                ("point", self.points), ("circle", self.circles),
                ("segment", self.segments), ("angle", self.angles),
                ("dimension", self.dimensions)):
            if name in collection:
                raise GeometryValidationError(
                    f"duplicate geometry name {name!r}: new {kind} conflicts with {existing_kind}")

    def add_point(self, name: str, x: Number, y: Number) -> "FigureScene":
        """Add a free point and return this scene."""

        name = _name(name, "point name")
        self._ensure_global_new(name, "point")
        self.points[name] = Point(name, float(x), float(y))
        return self

    def add_circle(self, name: str, center: str | Point | Sequence[Number],
                   radius: Number) -> "FigureScene":
        """Add a circle.

        ``center`` normally names a point.  A :class:`Point` or ``(x, y)`` is
        accepted for compatibility with v1 tuple-based helper code; an internal
        named center point is created when necessary.
        """

        name = _name(name, "circle name")
        self._ensure_global_new(name, "circle")
        if isinstance(center, Point):
            center_name = center.name
            if center_name in self.points and self.points[center_name] != center:
                raise GeometryValidationError(f"conflicting center point {center_name!r}")
            self.points.setdefault(center_name, center)
        elif isinstance(center, str):
            center_name = _name(center, "circle center ref")
        elif (isinstance(center, Sequence) and not isinstance(center, (str, bytes))
              and len(center) == 2):
            base = f"__{name}_center"
            center_name = base
            suffix = 2
            while center_name in self.points:
                center_name = f"{base}_{suffix}"
                suffix += 1
            self.add_point(center_name, center[0], center[1])
        else:
            raise GeometryValidationError("circle center must be a point ref or (x, y)")
        self.circles[name] = Circle(name, center_name, float(radius))
        return self

    def point_on_circle(self, name: str, circle: str, angle: Number) -> "FigureScene":
        """Construct a point on ``circle`` at a mathematical angle in degrees."""

        name = _name(name, "point name")
        self._ensure_global_new(name, "point")
        circle_name = _name(circle, "circle ref")
        if circle_name not in self.circles:
            raise GeometryValidationError(f"unknown circle ref {circle_name!r}")
        circle_obj = self.circles[circle_name]
        if circle_obj.center not in self.points:
            raise GeometryValidationError(
                f"circle {circle_name!r} has unknown center {circle_obj.center!r}")
        center = self.points[circle_obj.center]
        angle_value = _finite(angle, f"point {name!r} angle")
        x, y = circle_pt(center.x, center.y, angle_value, circle_obj.radius)
        self.points[name] = Point(name, x, y, "on_circle", circle_name, angle_value)
        return self

    def add_segment(self, name: str, p1: str, p2: str | None = None,
                    *, dashed: str | None = None) -> "FigureScene":
        """Add a named segment.

        Both ``add_segment('AC', 'A', 'C')`` and the compact
        ``add_segment('A', 'C')`` form are supported.  The compact form assigns
        the deterministic name ``A--C``.
        """

        if p2 is None:
            endpoint1, endpoint2 = _name(name, "segment endpoint"), _name(p1, "segment endpoint")
            segment_name = f"{endpoint1}--{endpoint2}"
        else:
            segment_name = _name(name, "segment name")
            endpoint1, endpoint2 = _name(p1, "segment endpoint"), _name(p2, "segment endpoint")
        self._ensure_global_new(segment_name, "segment")
        self.segments[segment_name] = Segment(segment_name, endpoint1, endpoint2, dashed)
        return self

    def intersection(self, name: str, segment1: str, segment2: str) -> "FigureScene":
        """Construct the intersection of two named finite segments."""

        name = _name(name, "point name")
        self._ensure_global_new(name, "point")
        s1_name, s2_name = _name(segment1, "segment ref"), _name(segment2, "segment ref")
        for ref in (s1_name, s2_name):
            if ref not in self.segments:
                raise GeometryValidationError(f"unknown segment ref {ref!r}")
        s1, s2 = self.segments[s1_name], self.segments[s2_name]
        for ref in (s1.p1, s1.p2, s2.p1, s2.p2):
            if ref not in self.points:
                raise GeometryValidationError(f"segment endpoint ref {ref!r} is unknown")
        a, b, c, d = (self.points[s1.p1], self.points[s1.p2],
                      self.points[s2.p1], self.points[s2.p2])
        length1 = math.hypot(b.x - a.x, b.y - a.y)
        length2 = math.hypot(d.x - c.x, d.y - c.y)
        den = ((a.x - b.x) * (c.y - d.y) - (a.y - b.y) * (c.x - d.x))
        scale = max(length1, length2)
        if length1 <= _EPS or length2 <= _EPS:
            raise GeometryValidationError("intersection segments must have non-zero length")
        if abs(den) <= _EPS * length1 * length2:
            raise GeometryValidationError(
                f"segments {s1_name!r} and {s2_name!r} are parallel or coincident")
        x, y = isect(a.as_tuple(), b.as_tuple(), c.as_tuple(), d.as_tuple())
        constructed = Point(name, x, y, "intersection",
                            segment_refs=(s1_name, s2_name))
        tolerance = max(1.0e-12, scale * 1.0e-7)
        if (not _point_within_segment(constructed, a, b, tolerance)
                or not _point_within_segment(constructed, c, d, tolerance)):
            raise GeometryValidationError(
                f"segments {s1_name!r} and {s2_name!r} intersect only on their supporting lines")
        self.points[name] = constructed
        return self

    def add_angle(self, name: str, vertex: str, p1: str, p2: str,
                  *, radius: Number | None = None, label: str | None = None,
                  label_distance: Number | None = None) -> "FigureScene":
        """Add a small-angle arc between rays ``vertex->p1`` and ``vertex->p2``."""

        name = _name(name, "angle name")
        self._ensure_global_new(name, "angle")
        if label is not None and not isinstance(label, str):
            raise GeometryValidationError("angle label must be text or None")
        self.angles[name] = AngleMark(
            name, _name(vertex, "angle vertex"), _name(p1, "angle ray ref"),
            _name(p2, "angle ray ref"), None if radius is None else float(radius),
            label, None if label_distance is None else float(label_distance))
        return self

    def add_dimension(self, name: str, p1: str, p2: str, label: str,
                      *, side: str = "auto", offset: Number | None = None,
                      curvature: Number | None = None, inset: Number = 0.0,
                      font_size: Number | None = None) -> "FigureScene":
        """Attach a collision-aware curved dashed length mark.

        ``side='auto'`` evaluates both normals and several increasing offsets,
        preferring the shortest collision-free curve.  ``curvature`` is a
        backwards-friendly alias for ``offset``; supplying both is rejected so
        ambiguous model output cannot silently win by argument order.
        """

        dimension_name = _name(name, "dimension name")
        self._ensure_global_new(dimension_name, "dimension")
        if not isinstance(label, str) or not label.strip():
            raise GeometryValidationError("dimension label must be non-empty text")
        normalized_side = str(side).strip().lower()
        if normalized_side not in {"auto", "left", "right"}:
            raise GeometryValidationError(
                "dimension side must be 'auto', 'left', or 'right'")
        if offset is not None and curvature is not None:
            raise GeometryValidationError(
                "dimension provides both offset and curvature; use only one")
        chosen_offset = offset if offset is not None else curvature
        self.dimensions[dimension_name] = DimensionMark(
            dimension_name, _name(p1, "dimension endpoint"),
            _name(p2, "dimension endpoint"), label,
            normalized_side,
            None if chosen_offset is None else float(chosen_offset),
            float(inset), None if font_size is None else float(font_size))
        return self

    def add_point_label(self, point: str, text: str | None = None,
                        *, position: str = "auto", dx: Number | None = None,
                        dy: Number | None = None, font_size: Number | None = None,
                        italic: bool = False) -> "FigureScene":
        """Attach one explicit or automatically placed label to ``point``.

        ``position`` accepts ``auto``, ``radial``, and the eight compass names
        (``N``, ``NE``, ..., ``NW``).  ``dx``/``dy`` override automatic offsets.
        """

        point_name = _name(point, "label point ref")
        if point_name in self.labels:
            raise GeometryValidationError(f"duplicate label for point {point_name!r}")
        content = point_name if text is None else text
        if not isinstance(content, str) or not content:
            raise GeometryValidationError("point label text must be non-empty")
        self.labels[point_name] = PointLabel(
            point_name, content, str(position), None if dx is None else float(dx),
            None if dy is None else float(dy),
            None if font_size is None else float(font_size), bool(italic))
        return self

    def validate(self) -> None:
        """Validate numeric values, references, and construction residuals."""

        owner_by_name: dict[str, str] = {}
        for kind, collection in (("point", self.points), ("circle", self.circles),
                                 ("segment", self.segments), ("angle", self.angles),
                                 ("dimension", self.dimensions)):
            for geometry_name in collection:
                if geometry_name in owner_by_name:
                    raise GeometryValidationError(
                        f"duplicate geometry name {geometry_name!r} across "
                        f"{owner_by_name[geometry_name]} and {kind}")
                owner_by_name[geometry_name] = kind

        numeric_style = {
            "circle_width": self.style.circle_width,
            "segment_width": self.style.segment_width,
            "mark_width": self.style.mark_width,
            "point_radius": self.style.point_radius,
            "font_size": self.style.font_size,
            "angle_font_size": self.style.angle_font_size,
            "label_offset": self.style.label_offset,
            "padding": self.style.padding,
            "angle_radius": self.style.angle_radius,
            "angle_label_distance": self.style.angle_label_distance,
            "dimension_width": self.style.dimension_width,
            "dimension_font_size": self.style.dimension_font_size,
            "dimension_offset": self.style.dimension_offset,
            "dimension_halo_width": self.style.dimension_halo_width,
            "halo_width": self.style.halo_width,
        }
        for key, value in numeric_style.items():
            number = _finite(value, f"style.{key}")
            if number < 0 or (key not in {"padding"} and number == 0):
                raise GeometryValidationError(f"style.{key} must be positive")
        _safe_paint(self.style.stroke, "style.stroke")
        _safe_paint(self.style.text_color, "style.text_color")
        _safe_paint(self.style.halo_color, "style.halo_color")
        if not (3.0 <= self.style.halo_width
                <= min(12.0, 0.8 * self.style.angle_font_size)):
            raise GeometryValidationError(
                "style.halo_width must be between 3 and min(12, 0.8 * angle_font_size)")
        if not (3.0 <= self.style.dimension_halo_width
                <= min(12.0, 0.8 * self.style.dimension_font_size)):
            raise GeometryValidationError(
                "style.dimension_halo_width must be between 3 and "
                "min(12, 0.8 * dimension_font_size)")
        try:
            dimension_dash = [float(part) for part in
                              str(self.style.dimension_dash).replace(",", " ").split()]
        except ValueError as exc:
            raise GeometryValidationError(
                "style.dimension_dash must be a numeric list") from exc
        if (not dimension_dash or any(not math.isfinite(value) or value < 0
                                      for value in dimension_dash)
                or not any(value > 0 for value in dimension_dash)):
            raise GeometryValidationError(
                "style.dimension_dash must contain non-negative lengths and "
                "at least one positive length")
        if (not isinstance(self.style.font_family, str) or not self.style.font_family.strip()
                or any(char in self.style.font_family for char in ";{}()<>\\")):
            raise GeometryValidationError("style.font_family contains unsafe syntax")
        if self.canvas is not None:
            if _finite(self.canvas.width, "canvas.width") <= 0:
                raise GeometryValidationError("canvas.width must be positive")
            if _finite(self.canvas.height, "canvas.height") <= 0:
                raise GeometryValidationError("canvas.height must be positive")

        for point in self.points.values():
            _finite(point.x, f"point {point.name!r}.x")
            _finite(point.y, f"point {point.name!r}.y")
            if point.kind not in {"raw", "on_circle", "intersection"}:
                raise GeometryValidationError(
                    f"point {point.name!r} has unknown construction {point.kind!r}")

        for circle_obj in self.circles.values():
            if circle_obj.center not in self.points:
                raise GeometryValidationError(
                    f"circle {circle_obj.name!r} has unknown center ref {circle_obj.center!r}")
            radius = _finite(circle_obj.radius, f"circle {circle_obj.name!r}.radius")
            if radius <= 0:
                raise GeometryValidationError(
                    f"circle {circle_obj.name!r} radius must be positive")

        for segment in self.segments.values():
            for ref in (segment.p1, segment.p2):
                if ref not in self.points:
                    raise GeometryValidationError(
                        f"segment {segment.name!r} has unknown point ref {ref!r}")
            a, b = self.points[segment.p1], self.points[segment.p2]
            if math.hypot(a.x - b.x, a.y - b.y) <= _EPS:
                raise GeometryValidationError(f"segment {segment.name!r} has zero length")
            if segment.dashed is not None:
                try:
                    dash_values = [float(part) for part in str(segment.dashed).replace(",", " ").split()]
                except ValueError as exc:
                    raise GeometryValidationError(
                        f"segment {segment.name!r} dash must be a numeric list") from exc
                if (not dash_values or any(not math.isfinite(value) or value < 0
                                           for value in dash_values)
                        or not any(value > 0 for value in dash_values)):
                    raise GeometryValidationError(
                        f"segment {segment.name!r} dash must contain non-negative lengths "
                        "and at least one positive length")

        for point in self.points.values():
            if point.kind == "on_circle":
                if point.circle_ref not in self.circles:
                    raise GeometryValidationError(
                        f"point {point.name!r} has unknown circle ref {point.circle_ref!r}")
                circle_obj = self.circles[point.circle_ref]
                center = self.points[circle_obj.center]
                residual = abs(math.hypot(point.x - center.x, point.y - center.y)
                               - circle_obj.radius)
                tolerance = max(1.0e-12, abs(circle_obj.radius) * 1.0e-7)
                if residual > tolerance:
                    raise GeometryValidationError(
                        f"point {point.name!r} on-circle residual {residual:.6g} exceeds {tolerance:.6g}")
            elif point.kind == "intersection":
                if not point.segment_refs or any(ref not in self.segments
                                                 for ref in point.segment_refs):
                    raise GeometryValidationError(
                        f"point {point.name!r} has invalid intersection refs")
                for ref in point.segment_refs:
                    segment = self.segments[ref]
                    endpoint1, endpoint2 = self.points[segment.p1], self.points[segment.p2]
                    residual = _distance_point_line(
                        point, endpoint1, endpoint2)
                    scale = math.hypot(endpoint2.x - endpoint1.x,
                                       endpoint2.y - endpoint1.y)
                    tolerance = max(1.0e-12, scale * 1.0e-7)
                    if residual > tolerance:
                        raise GeometryValidationError(
                            f"point {point.name!r} intersection residual on {ref!r} "
                            f"is {residual:.6g}")
                    if not _point_within_segment(point, endpoint1, endpoint2, tolerance):
                        raise GeometryValidationError(
                            f"point {point.name!r} lies outside finite segment {ref!r}")

        for angle in self.angles.values():
            for ref in (angle.vertex, angle.p1, angle.p2):
                if ref not in self.points:
                    raise GeometryValidationError(
                        f"angle {angle.name!r} has unknown point ref {ref!r}")
            vertex, p1, p2 = (self.points[angle.vertex], self.points[angle.p1],
                              self.points[angle.p2])
            v1 = (p1.x - vertex.x, p1.y - vertex.y)
            v2 = (p2.x - vertex.x, p2.y - vertex.y)
            l1, l2 = math.hypot(*v1), math.hypot(*v2)
            if l1 <= _EPS or l2 <= _EPS:
                raise GeometryValidationError(f"angle {angle.name!r} has a zero-length ray")
            cross = abs(v1[0] * v2[1] - v1[1] * v2[0])
            if cross <= 1.0e-8 * l1 * l2:
                raise GeometryValidationError(
                    f"angle {angle.name!r} is degenerate (collinear rays)")
            for ray_name, ray_point in ((angle.p1, p1), (angle.p2, p2)):
                ray_is_drawn = False
                for segment in self.segments.values():
                    start, end = self.points[segment.p1], self.points[segment.p2]
                    scale = math.hypot(end.x - start.x, end.y - start.y)
                    tolerance = max(1.0e-12, scale * 1.0e-7)
                    if (_distance_point_line(vertex, start, end) <= tolerance
                            and _distance_point_line(ray_point, start, end) <= tolerance
                            and _point_within_segment(vertex, start, end, tolerance)
                            and _point_within_segment(ray_point, start, end, tolerance)):
                        ray_is_drawn = True
                        break
                if not ray_is_drawn:
                    raise GeometryValidationError(
                        f"angle {angle.name!r} ray to {ray_name!r} is not covered "
                        "by a rendered segment")
            radius = self.style.angle_radius if angle.radius is None else _finite(
                angle.radius, f"angle {angle.name!r}.radius")
            if radius <= 0:
                raise GeometryValidationError(f"angle {angle.name!r} radius must be positive")
            if angle.label_distance is not None and _finite(
                    angle.label_distance, f"angle {angle.name!r}.label_distance") <= 0:
                raise GeometryValidationError(
                    f"angle {angle.name!r} label_distance must be positive")

        for dimension in self.dimensions.values():
            for ref in (dimension.p1, dimension.p2):
                if ref not in self.points:
                    raise GeometryValidationError(
                        f"dimension {dimension.name!r} has unknown point ref {ref!r}")
            if dimension.side not in {"auto", "left", "right"}:
                raise GeometryValidationError(
                    f"dimension {dimension.name!r} has invalid side {dimension.side!r}")
            if not isinstance(dimension.label, str) or not dimension.label.strip():
                raise GeometryValidationError(
                    f"dimension {dimension.name!r} label must be non-empty")
            first, second = self.points[dimension.p1], self.points[dimension.p2]
            length = math.hypot(second.x - first.x, second.y - first.y)
            if length <= _EPS:
                raise GeometryValidationError(
                    f"dimension {dimension.name!r} has zero-length endpoints")
            inset = _finite(dimension.inset, f"dimension {dimension.name!r}.inset")
            if inset < 0 or 2.0 * inset >= length:
                raise GeometryValidationError(
                    f"dimension {dimension.name!r} inset must be non-negative and "
                    "leave a visible curve")
            if dimension.offset is not None and _finite(
                    dimension.offset, f"dimension {dimension.name!r}.offset") <= 0:
                raise GeometryValidationError(
                    f"dimension {dimension.name!r} offset must be positive")
            if dimension.font_size is not None and _finite(
                    dimension.font_size, f"dimension {dimension.name!r}.font_size") <= 0:
                raise GeometryValidationError(
                    f"dimension {dimension.name!r} font_size must be positive")
            if (dimension.font_size is not None
                    and self.style.dimension_halo_width > 0.8 * dimension.font_size):
                raise GeometryValidationError(
                    f"dimension {dimension.name!r} font_size is too small for "
                    "the configured halo")

        valid_positions = {"AUTO", "RADIAL", "N", "NE", "E", "SE",
                           "S", "SW", "W", "NW"}
        for label in self.labels.values():
            if label.point not in self.points:
                raise GeometryValidationError(
                    f"label has unknown point ref {label.point!r}")
            if label.position.strip().upper() not in valid_positions:
                raise GeometryValidationError(
                    f"label {label.point!r} has unknown position {label.position!r}")
            for key, value in (("dx", label.dx), ("dy", label.dy)):
                if value is not None:
                    _finite(value, f"label {label.point!r}.{key}")
            if label.font_size is not None and _finite(
                    label.font_size, f"label {label.point!r}.font_size") <= 0:
                raise GeometryValidationError(
                    f"label {label.point!r} font_size must be positive")

    def _angle_label_layout(self, angle: AngleMark) -> tuple[tuple[float, float], Box] | None:
        if not angle.label:
            return None
        vertex, p1, p2 = (self.points[angle.vertex], self.points[angle.p1],
                          self.points[angle.p2])
        a0 = math.atan2(p1.y - vertex.y, p1.x - vertex.x)
        a1 = math.atan2(p2.y - vertex.y, p2.x - vertex.x)
        delta = (a1 - a0 + math.pi) % (2.0 * math.pi) - math.pi
        mid = a0 + delta / 2.0
        distance = (self.style.angle_label_distance if angle.label_distance is None
                    else angle.label_distance)
        fs = self.style.angle_font_size
        x = vertex.x + distance * math.cos(mid)
        y = vertex.y + distance * math.sin(mid) + 0.32 * fs
        return (x, y), _text_box(x, y, angle.label, fs)

    def _label_vectors(self, label: PointLabel) -> list[tuple[float, float]]:
        point = self.points[label.point]
        compass = {
            "N": (0.0, -1.0), "NE": (math.sqrt(0.5), -math.sqrt(0.5)),
            "E": (1.0, 0.0), "SE": (math.sqrt(0.5), math.sqrt(0.5)),
            "S": (0.0, 1.0), "SW": (-math.sqrt(0.5), math.sqrt(0.5)),
            "W": (-1.0, 0.0), "NW": (-math.sqrt(0.5), -math.sqrt(0.5)),
        }
        requested = label.position.strip().upper()
        radial: tuple[float, float] | None = None
        if point.kind == "on_circle" and point.circle_ref in self.circles:
            circle_obj = self.circles[point.circle_ref]
            center = self.points[circle_obj.center]
            length = math.hypot(point.x - center.x, point.y - center.y)
            if length > _EPS:
                radial = ((point.x - center.x) / length, (point.y - center.y) / length)
        if requested in compass:
            return [compass[requested]]
        if requested == "RADIAL":
            if radial is None:
                raise GeometryValidationError(
                    f"radial label position requires on-circle point {point.name!r}")
            return [radial]
        base = [compass[key] for key in ("N", "NE", "E", "SE", "S", "SW", "W", "NW")]
        endpoint_vectors: list[tuple[float, float]] = []
        for dimension_name in sorted(self.dimensions):
            dimension = self.dimensions[dimension_name]
            if label.point not in {dimension.p1, dimension.p2}:
                continue
            other_name = dimension.p2 if label.point == dimension.p1 else dimension.p1
            if other_name not in self.points:
                continue
            other = self.points[other_name]
            length = math.hypot(point.x - other.x, point.y - other.y)
            if length > _EPS:
                endpoint_vectors.append(
                    ((point.x - other.x) / length, (point.y - other.y) / length))
        if radial is None:
            # Intersections look most natural below-left unless occupied; raw
            # points prefer north.  Costs still decide among all candidates.
            if point.kind == "intersection":
                ordered = [compass[key] for key in
                           ("SW", "SE", "NW", "NE", "S", "N", "W", "E")]
            else:
                ordered = base
            return endpoint_vectors + [vector for vector in ordered
                                       if vector not in endpoint_vectors]
        # For circle points, the exact outward radial candidate is deliberately
        # first, followed by small rotations before generic compass fallbacks.
        angle = math.atan2(radial[1], radial[0])
        candidates = [radial]
        for degrees in (-24.0, 24.0, -45.0, 45.0):
            theta = angle + math.radians(degrees)
            candidates.append((math.cos(theta), math.sin(theta)))
        candidates.extend(endpoint_vectors)
        candidates.extend(base)
        return candidates

    def _candidate_cost(self, point_name: str, box: Box, occupied: Iterable[Box],
                        rank: int, distance_rank: int = 0) -> tuple[int, float]:
        hard = 0
        cost = rank * 0.25 + distance_rank * 0.4
        for other in occupied:
            if _boxes_overlap(box, other, gap=1.0):
                ix = max(0.0, min(box[2], other[2]) - max(box[0], other[0]))
                iy = max(0.0, min(box[3], other[3]) - max(box[1], other[1]))
                hard += 1
                cost += ix * iy * 50.0
        for name, point in self.points.items():
            if name != point_name and _point_in_box(point.x, point.y, box, 1.5):
                hard += 1
                cost += 100.0
        for segment in self.segments.values():
            if _segment_intersects_box(self.points[segment.p1], self.points[segment.p2], box):
                hard += 1
                cost += 20.0
        cx, cy = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0
        half_diag = math.hypot(box[2] - box[0], box[3] - box[1]) / 2.0
        for circle_name in sorted(self.circles):
            circle_obj = self.circles[circle_name]
            center = self.points[circle_obj.center]
            if abs(math.hypot(cx - center.x, cy - center.y) - circle_obj.radius) < half_diag + 0.75:
                hard += 1
                cost += 15.0
        return hard, cost

    def _dimension_layout(self, dimension: DimensionMark, occupied: Sequence[Box],
                          earlier: Sequence[DimensionLayout]) -> DimensionLayout:
        """Choose the shortest collision-free side/curvature candidate."""

        first, second = self.points[dimension.p1], self.points[dimension.p2]
        dx, dy = second.x - first.x, second.y - first.y
        length = math.hypot(dx, dy)
        ux, uy = dx / length, dy / length
        nx, ny = -uy, ux
        start = Point(f"{dimension.name}:start",
                      first.x + ux * dimension.inset,
                      first.y + uy * dimension.inset)
        end = Point(f"{dimension.name}:end",
                    second.x - ux * dimension.inset,
                    second.y - uy * dimension.inset)
        midpoint_x = (first.x + second.x) / 2.0
        midpoint_y = (first.y + second.y) / 2.0
        if dimension.font_size is None:
            width_units = max(0.62, sum(
                1.0 if ord(char) > 0x2FF else 0.61 for char in dimension.label))
            available = max(1.0, length - 2.0 * dimension.inset)
            font_size = min(
                self.style.dimension_font_size,
                max(10.0, 0.82 * available / width_units),
            )
        else:
            font_size = dimension.font_size
        base_offset = (self.style.dimension_offset if dimension.offset is None
                       else dimension.offset)
        offset_step = max(4.0, 0.55 * font_size)
        offsets = [base_offset + index * offset_step for index in range(6)]
        sides = ([dimension.side] if dimension.side != "auto"
                 else ["left", "right"])

        candidates: list[tuple[tuple[int, int, int, int, int, int,
                                          float, float, int, int],
                               DimensionLayout]] = []
        for offset_rank, offset in enumerate(offsets):
            for side_rank, side in enumerate(sides):
                sign = 1.0 if side == "left" else -1.0
                control = Point(
                    f"{dimension.name}:control",
                    midpoint_x + nx * sign * 2.0 * offset,
                    midpoint_y + ny * sign * 2.0 * offset,
                )
                samples = _quadratic_samples(dimension.name, start, control, end)
                apex = samples[len(samples) // 2]
                label_position = (apex.x, apex.y + 0.32 * font_size)
                label_box = _expand_box(
                    _text_box(*label_position, dimension.label, font_size),
                    self.style.dimension_halo_width / 2.0 + 0.5,
                )
                projected_label_width = (
                    abs(ux) * (label_box[2] - label_box[0])
                    + abs(uy) * (label_box[3] - label_box[1])
                )
                visible_chord = math.hypot(end.x - start.x, end.y - start.y)
                if projected_label_width > 0.72 * visible_chord:
                    # A long value on a short side cannot leave meaningful
                    # curve fragments around an inline gap.  Move it just
                    # beyond the apex and keep the complete dashed curve.
                    for factor in (0.75, 1.0, 1.3, 1.65, 2.0,
                                   2.5, 3.1, 3.8, 4.6):
                        shift = factor * font_size + self.style.dimension_halo_width / 2.0
                        moved = (
                            apex.x + nx * sign * shift,
                            apex.y + ny * sign * shift + 0.32 * font_size,
                        )
                        moved_box = _expand_box(
                            _text_box(*moved, dimension.label, font_size),
                            self.style.dimension_halo_width / 2.0 + 0.5,
                        )
                        label_position, label_box = moved, moved_box
                        if not _polyline_intersects_box(samples, moved_box):
                            break
                layout = DimensionLayout(
                    dimension.name, side, start, control, end,
                    label_position, label_box, samples, font_size,
                )

                curve_box = _expand_box(_merge_bounds(
                    (sample.x, sample.y, sample.x, sample.y) for sample in samples
                ), self.style.dimension_width / 2.0 + 0.75)
                clipped = 0
                if self.canvas is not None:
                    for box in (curve_box, label_box):
                        if (box[0] < 0 or box[1] < 0
                                or box[2] > self.canvas.width
                                or box[3] > self.canvas.height):
                            clipped += 1

                text_collisions = sum(
                    1 for box in occupied
                    if (_boxes_overlap(label_box, box, gap=1.0)
                        or _polyline_intersects_box(samples, _expand_box(box, 1.0)))
                )
                point_collisions = 0
                for point_name, point in self.points.items():
                    if point_name in {dimension.p1, dimension.p2}:
                        continue
                    if not self.style.show_points:
                        # Unmarked construction points (notably a circle's
                        # center O) have no visible ink.  Their labels are
                        # already represented by `occupied`, and rendered
                        # segments/circles are checked separately below.
                        continue
                    if (_point_in_box(point.x, point.y, label_box, 1.0)
                            or min(_distance_xy_to_segment(
                                point.x, point.y, a, b)
                                   for a, b in zip(samples, samples[1:])) < 2.25):
                        point_collisions += 1

                geometry_crossings = 0
                near_geometry = 0
                endpoint_pair = {dimension.p1, dimension.p2}
                for segment in self.segments.values():
                    if {segment.p1, segment.p2} == endpoint_pair:
                        # A one-sided quadratic meets its measured chord only
                        # at the deliberately inset start/end points.  The
                        # value label itself still needs genuine clearance.
                        a, b = self.points[segment.p1], self.points[segment.p2]
                        label_clearance = _expand_box(
                            label_box,
                            self.style.segment_width / 2.0 + 0.5,
                        )
                        if _segment_intersects_box(a, b, label_clearance):
                            geometry_crossings += 1
                        continue
                    a, b = self.points[segment.p1], self.points[segment.p2]
                    if (_polyline_intersects_segment(samples, a, b)
                            or _segment_intersects_box(a, b, label_box)):
                        geometry_crossings += 1
                    else:
                        clearance = min(
                            _distance_xy_to_segment(sample.x, sample.y, a, b)
                            for sample in samples)
                        if clearance < 3.0:
                            near_geometry += 1

                circle_crossings = 0
                for circle_obj in self.circles.values():
                    center = self.points[circle_obj.center]
                    if _box_intersects_circle(label_box, center, circle_obj.radius, 0.75):
                        circle_crossings += 1
                    else:
                        residuals = [
                            math.hypot(sample.x - center.x, sample.y - center.y)
                            - circle_obj.radius for sample in samples
                        ]
                        # A chord dimension begins inside the circle near both
                        # endpoints.  Only a real inside/outside transition is
                        # a circumference crossing; mere endpoint proximity is
                        # expected and must not reject the clean inner arc.
                        if min(residuals) < -0.75 and max(residuals) > 0.75:
                            circle_crossings += 1

                earlier_collisions = 0
                for other in earlier:
                    if (_boxes_overlap(label_box, other.label_box, gap=1.0)
                            or _polyline_intersects_box(samples,
                                                        _expand_box(other.label_box, 1.0))
                            or _polyline_intersects_box(other.path_samples,
                                                        _expand_box(label_box, 1.0))
                            or _polylines_intersect(samples, other.path_samples)):
                        earlier_collisions += 1

                side_crowding = 0
                for point_name, point in self.points.items():
                    if point_name in {dimension.p1, dimension.p2}:
                        continue
                    along = (point.x - first.x) * ux + (point.y - first.y) * uy
                    normal = ((point.x - first.x) * nx
                              + (point.y - first.y) * ny) * sign
                    if -0.15 * length <= along <= 1.15 * length and normal > 2.0:
                        side_crowding += 1

                score = (
                    clipped, text_collisions, point_collisions,
                    geometry_crossings, circle_crossings, earlier_collisions,
                    float(side_crowding), float(near_geometry),
                    offset_rank, side_rank,
                )
                candidates.append((score, layout))

        score, layout = min(candidates, key=lambda item: item[0])
        if any(score[:6]):
            raise GeometryValidationError(
                f"dimension {dimension.name!r} has no collision-free layout "
                f"(clip/text/point/geometry/circle/dimension={score[:6]})")
        return layout

    def resolve(self) -> ResolvedScene:
        """Validate and resolve label placement, bounds, and canvas translation."""

        self.validate()
        label_positions: dict[str, tuple[float, float]] = {}
        label_boxes: dict[str, Box] = {}
        occupied: list[Box] = []

        # Angle labels are fixed by the angle bisector and reserve their space
        # before automatic point labels are evaluated.
        for angle_name in sorted(self.angles):
            angle = self.angles[angle_name]
            laid_out = self._angle_label_layout(angle)
            if laid_out:
                pos, box = laid_out
                key = f"angle:{angle.name}"
                label_positions[key], label_boxes[key] = pos, box
                occupied.append(box)

        for point_name in sorted(self.labels):
            label = self.labels[point_name]
            point = self.points[label.point]
            fs = self.style.font_size if label.font_size is None else label.font_size
            if label.dx is not None or label.dy is not None:
                dx = 0.0 if label.dx is None else label.dx
                dy = 0.0 if label.dy is None else label.dy
                x, y = point.x + dx, point.y + dy + 0.32 * fs
                box = _text_box(x, y, label.text, fs)
                candidates = [((x, y), box,
                               self._candidate_cost(label.point, box, occupied, 0, 0))]
            else:
                candidates = []
                for rank, (ux, uy) in enumerate(self._label_vectors(label)):
                    for distance_rank in range(5):
                        # Multiple radii make label/line avoidance a hard
                        # invariant instead of accepting the least-bad overlap.
                        distance = (self.style.label_offset + 0.18 * fs
                                    + distance_rank * max(3.5, 0.55 * fs))
                        x = point.x + ux * distance
                        y = point.y + uy * distance + 0.32 * fs
                        box = _text_box(x, y, label.text, fs)
                        candidates.append((
                            (x, y), box,
                            self._candidate_cost(
                                label.point, box, occupied, rank, distance_rank)))
            pos, box, cost = min(candidates, key=lambda item: item[2])
            if cost[0]:
                raise GeometryValidationError(
                    f"label {label.point!r} has no line/circle/label-free position")
            label_positions[label.point], label_boxes[label.point] = pos, box
            occupied.append(box)

        dimension_layouts: dict[str, DimensionLayout] = {}
        for dimension_name in sorted(self.dimensions):
            dimension = self.dimensions[dimension_name]
            layout = self._dimension_layout(
                dimension, occupied, list(dimension_layouts.values()))
            dimension_layouts[dimension.name] = layout
            key = f"dimension:{dimension.name}"
            label_positions[key] = layout.label_position
            label_boxes[key] = layout.label_box
            occupied.append(layout.label_box)

        bounds: list[Box] = []
        stroke_pad = max(self.style.circle_width, self.style.segment_width,
                         self.style.mark_width) / 2.0
        for circle_obj in self.circles.values():
            center = self.points[circle_obj.center]
            r = circle_obj.radius + stroke_pad
            bounds.append((center.x - r, center.y - r, center.x + r, center.y + r))
        for segment_name in sorted(self.segments):
            segment = self.segments[segment_name]
            a, b = self.points[segment.p1], self.points[segment.p2]
            bounds.append((min(a.x, b.x) - stroke_pad, min(a.y, b.y) - stroke_pad,
                           max(a.x, b.x) + stroke_pad, max(a.y, b.y) + stroke_pad))
        for layout in dimension_layouts.values():
            dimension_pad = self.style.dimension_width / 2.0 + 0.75
            bounds.append(_expand_box(_merge_bounds(
                (sample.x, sample.y, sample.x, sample.y)
                for sample in layout.path_samples), dimension_pad))
        for point in self.points.values():
            r = self.style.point_radius if self.style.show_points else stroke_pad
            bounds.append((point.x - r, point.y - r, point.x + r, point.y + r))
        for angle in self.angles.values():
            vertex = self.points[angle.vertex]
            r = self.style.angle_radius if angle.radius is None else angle.radius
            bounds.append((vertex.x - r - stroke_pad, vertex.y - r - stroke_pad,
                           vertex.x + r + stroke_pad, vertex.y + r + stroke_pad))
        bounds.extend(label_boxes.values())
        content = _merge_bounds(bounds)

        if self.canvas is None:
            padding = self.style.padding
            width = max(1.0, content[2] - content[0] + 2.0 * padding)
            height = max(1.0, content[3] - content[1] + 2.0 * padding)
            translation = (padding - content[0], padding - content[1])
        else:
            width, height = self.canvas.width, self.canvas.height
            translation = (0.0, 0.0)
            tolerance = max(width, height, 1.0) * 1.0e-9
            if (content[0] < -tolerance or content[1] < -tolerance
                    or content[2] > width + tolerance or content[3] > height + tolerance):
                raise GeometryValidationError(
                    "fixed canvas clips scene content: "
                    f"content=({_fmt(content[0])}, {_fmt(content[1])}, "
                    f"{_fmt(content[2])}, {_fmt(content[3])}), "
                    f"canvas=(0, 0, {_fmt(width)}, {_fmt(height)})")
        return ResolvedScene(
            MappingProxyType(dict(self.points)), MappingProxyType(label_positions),
            MappingProxyType(label_boxes), MappingProxyType(dimension_layouts),
            (0.0, 0.0, width, height), translation, content)

    def render_svg(self) -> str:
        """Render a standalone SVG with deterministic main/marks/labels layers."""

        resolved = self.resolve()
        _, _, width, height = resolved.view_box
        style = self.style
        main: list[str] = []
        marks: list[str] = []
        labels: list[str] = []
        tx, ty = resolved.translation

        for circle_obj in self.circles.values():
            center = self.points[circle_obj.center]
            main.append(
                f'<circle cx="{_fmt(center.x + tx)}" cy="{_fmt(center.y + ty)}" '
                f'r="{_fmt(circle_obj.radius)}" fill="none" '
                f'stroke="{escape(style.stroke, quote=True)}" '
                f'stroke-width="{_fmt(style.circle_width)}"/>')
        for segment in self.segments.values():
            a, b = self.points[segment.p1], self.points[segment.p2]
            dash = (f' stroke-dasharray="{escape(segment.dashed, quote=True)}"'
                    if segment.dashed else "")
            main.append(
                f'<line x1="{_fmt(a.x + tx)}" y1="{_fmt(a.y + ty)}" '
                f'x2="{_fmt(b.x + tx)}" y2="{_fmt(b.y + ty)}" '
                f'stroke="{escape(style.stroke, quote=True)}" '
                f'stroke-width="{_fmt(style.segment_width)}"{dash}/>' )

        for angle_name in sorted(self.angles):
            angle = self.angles[angle_name]
            vertex, p1, p2 = (self.points[angle.vertex], self.points[angle.p1],
                              self.points[angle.p2])
            radius = style.angle_radius if angle.radius is None else angle.radius
            path_data = angle_arc(
                vertex.x + tx, vertex.y + ty,
                (p1.x + tx, p1.y + ty), (p2.x + tx, p2.y + ty), radius)
            marks.append(
                f'<path d="{path_data}" fill="none" '
                f'stroke="{escape(style.stroke, quote=True)}" '
                f'stroke-width="{_fmt(style.mark_width)}"/>')
        for dimension_name in sorted(self.dimensions):
            dimension = self.dimensions[dimension_name]
            layout = resolved.dimension_layouts[dimension.name]
            path_data = _dimension_gapped_path(layout, tx, ty)
            marks.append(
                f'<path d="{path_data}" '
                f'fill="none" stroke="{escape(style.stroke, quote=True)}" '
                f'stroke-width="{_fmt(style.dimension_width)}" '
                f'stroke-dasharray="{escape(style.dimension_dash, quote=True)}" '
                f'stroke-linecap="round"/>')
        if style.show_points:
            referenced = {ref for segment in self.segments.values()
                          for ref in (segment.p1, segment.p2)}
            referenced.update(angle.vertex for angle in self.angles.values())
            for name in sorted(referenced):
                point = self.points[name]
                marks.append(
                    f'<circle cx="{_fmt(point.x + tx)}" cy="{_fmt(point.y + ty)}" '
                    f'r="{_fmt(style.point_radius)}" fill="{escape(style.stroke, quote=True)}"/>')

        font_family = escape(style.font_family, quote=True)
        for angle_name in sorted(self.angles):
            angle = self.angles[angle_name]
            if not angle.label:
                continue
            x, y = resolved.label_positions[f"angle:{angle.name}"]
            labels.append(
                f'<text x="{_fmt(x + tx)}" y="{_fmt(y + ty)}" '
                f'font-family="{font_family}" font-size="{_fmt(style.angle_font_size)}" '
                f'font-style="italic" text-anchor="middle" '
                f'fill="{escape(style.text_color, quote=True)}" paint-order="stroke" '
                f'stroke="{escape(style.halo_color, quote=True)}" '
                f'stroke-width="{_fmt(style.halo_width)}" stroke-linejoin="round">'
                f'{escape(angle.label)}</text>')
        for dimension_name in sorted(self.dimensions):
            dimension = self.dimensions[dimension_name]
            layout = resolved.dimension_layouts[dimension.name]
            x, y = layout.label_position
            fs = layout.font_size
            labels.append(
                f'<text x="{_fmt(x + tx)}" y="{_fmt(y + ty)}" '
                f'font-family="{font_family}" font-size="{_fmt(fs)}" '
                f'text-anchor="middle" fill="{escape(style.text_color, quote=True)}" '
                f'paint-order="stroke fill" stroke="{escape(style.halo_color, quote=True)}" '
                f'stroke-width="{_fmt(style.dimension_halo_width)}" '
                f'stroke-linejoin="round">{escape(dimension.label)}</text>')
        for point_name in sorted(self.labels):
            label = self.labels[point_name]
            x, y = resolved.label_positions[point_name]
            fs = style.font_size if label.font_size is None else label.font_size
            italic = ' font-style="italic"' if label.italic else ""
            labels.append(
                f'<text x="{_fmt(x + tx)}" y="{_fmt(y + ty)}" '
                f'font-family="{font_family}" font-size="{_fmt(fs)}"{italic} '
                f'text-anchor="middle" fill="{escape(style.text_color, quote=True)}">'
                f'{escape(label.text)}</text>')

        background = (f'\n  <rect width="{_fmt(width)}" height="{_fmt(height)}" fill="#ffffff"/>'
                      if self.background == "white" else "")
        main_body = "\n    ".join(main)
        marks_body = "\n    ".join(marks)
        labels_body = "\n    ".join(labels)
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {_fmt(width)} {_fmt(height)}">{background}\n'
            f'  <g>\n    {main_body}\n  </g>\n'
            f'  <g>\n    {marks_body}\n  </g>\n'
            f'  <g>\n    {labels_body}\n  </g>\n'
            f'</svg>')
        # Public scene rendering is a security boundary too: callers may use
        # FigureScene directly rather than passing through figure_generator.
        # Rebuild through the same reference-free allowlist used for model SVG.
        try:
            from core.figure_quality import sanitize_svg

            return sanitize_svg(svg)
        except Exception as exc:  # noqa: BLE001 - normalize validator boundary
            raise GeometryValidationError(f"scene SVG safety validation failed: {exc}") from exc

    def to_svg(self) -> str:
        """Alias for :meth:`render_svg`."""

        return self.render_svg()

    def render(self) -> str:
        """Short alias for :meth:`render_svg`."""

        return self.render_svg()

    @classmethod
    def from_spec(cls, spec: Mapping[str, Any] | "FigureSpec") -> "FigureScene":
        """Compile a strict v2 dictionary FigureSpec into a scene."""

        return compile_figure_spec(spec)


@dataclass(frozen=True)
class FigureSpec:
    """Immutable-ish wrapper around a v2 dictionary specification."""

    data: Mapping[str, Any]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FigureSpec":
        """Wrap a mapping after checking its top-level type."""

        if not isinstance(data, Mapping):
            raise FigureSpecError("FigureSpec must be a mapping")
        return cls(MappingProxyType(dict(data)))

    def compile(self) -> FigureScene:
        """Compile this specification to a validated scene."""

        return compile_figure_spec(self.data)

    def render_svg(self) -> str:
        """Compile and render this specification."""

        return self.compile().render_svg()


def _strict_keys(obj: Mapping[str, Any], allowed: set[str], path: str) -> None:
    unknown = set(obj) - allowed
    if unknown:
        raise FigureSpecError(f"{path}: unknown field(s): {', '.join(sorted(map(str, unknown)))}")


def _named_records(value: Any, path: str) -> list[tuple[str, Any]]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return [(str(key), item) for key, item in value.items()]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        records: list[tuple[str, Any]] = []
        for index, item in enumerate(value):
            if not isinstance(item, Mapping):
                raise FigureSpecError(f"{path}[{index}] must be an object")
            if "name" not in item:
                raise FigureSpecError(f"{path}[{index}] requires 'name'")
            copied = dict(item)
            name = str(copied.pop("name"))
            records.append((name, copied))
        return records
    raise FigureSpecError(f"{path} must be an object or list")


def _spec_number(value: Any, path: str) -> float:
    if isinstance(value, bool):
        raise FigureSpecError(f"{path} must be a finite number, not boolean")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise FigureSpecError(f"{path} must be a finite number") from exc
    if not math.isfinite(result):
        raise FigureSpecError(f"{path} must be finite")
    return result


def _pair(value: Any, path: str) -> tuple[str, str]:
    if (not isinstance(value, Sequence) or isinstance(value, (str, bytes))
            or len(value) != 2):
        raise FigureSpecError(f"{path} must contain exactly two refs")
    return str(value[0]), str(value[1])


def _style_from_spec(theme: Any, overrides: Any) -> StyleProfile:
    style = StyleProfile.from_theme("exam-thin" if theme is None else str(theme))
    if overrides is None:
        return style
    if not isinstance(overrides, Mapping):
        raise FigureSpecError("style must be an object")
    allowed = {field_name for field_name in StyleProfile.__dataclass_fields__ if field_name != "name"}
    _strict_keys(overrides, allowed, "style")
    values: dict[str, Any] = {}
    for key, value in overrides.items():
        if key == "show_points":
            if not isinstance(value, bool):
                raise FigureSpecError("style.show_points must be boolean")
            values[key] = value
        elif key in {"stroke", "text_color", "font_family", "halo_color",
                     "dimension_dash"}:
            if not isinstance(value, str) or not value:
                raise FigureSpecError(f"style.{key} must be non-empty text")
            values[key] = value
        else:
            values[key] = _spec_number(value, f"style.{key}")
    return replace(style, **values)


def compile_figure_spec(spec: Mapping[str, Any] | FigureSpec) -> FigureScene:
    """Compile a strict declarative v2 FigureSpec mapping.

    Supported construction objects are deliberately small and deterministic::

        {
          "version": 2,
          "theme": "exam-thin",
          "points": {
            "O": {"type": "raw", "x": 94, "y": 78},
            "A": {"type": "on_circle", "circle": "omega", "angle": 130},
            "P": {"type": "intersection", "segments": ["AC", "BD"]}
          },
          "circles": {"omega": {"center": "O", "radius": 68}},
          "segments": {"AC": ["A", "C"], "BD": ["B", "D"]},
          "angles": {"x": {"vertex": "P", "points": ["D", "C"],
                              "label": "x°"}},
          "dimensions": {"AC_len": {"points": ["A", "C"],
                                       "label": "12 cm", "side": "auto"}},
          "labels": {"A": "A", "B": "B"}
        }

    Unknown fields and references are errors; no placeholder geometry is made.
    """

    if isinstance(spec, FigureSpec):
        spec = spec.data
    if not isinstance(spec, Mapping):
        raise FigureSpecError("FigureSpec must be a mapping")
    allowed_top = {"version", "theme", "canvas", "background", "style",
                   "points", "circles", "segments", "angles", "dimensions",
                   "labels"}
    _strict_keys(spec, allowed_top, "FigureSpec")
    if "version" not in spec:
        raise FigureSpecError("FigureSpec requires version: 2")
    version = spec["version"]
    if isinstance(version, bool) or version not in (2, 2.0, "2", "2.0"):
        raise FigureSpecError(f"unsupported FigureSpec version {version!r}; expected 2")

    style = _style_from_spec(spec.get("theme"), spec.get("style"))
    background = spec.get("background", "white")
    canvas_value = spec.get("canvas")
    canvas: Canvas | None = None
    if canvas_value is not None:
        if isinstance(canvas_value, Mapping):
            _strict_keys(canvas_value, {"width", "height", "background"}, "canvas")
            if "width" not in canvas_value or "height" not in canvas_value:
                raise FigureSpecError("canvas requires width and height")
            canvas = Canvas(_spec_number(canvas_value["width"], "canvas.width"),
                            _spec_number(canvas_value["height"], "canvas.height"))
            if "background" in canvas_value:
                if "background" in spec and spec["background"] != canvas_value["background"]:
                    raise FigureSpecError("background conflicts with canvas.background")
                background = canvas_value["background"]
        elif (isinstance(canvas_value, Sequence)
              and not isinstance(canvas_value, (str, bytes)) and len(canvas_value) == 2):
            canvas = Canvas(_spec_number(canvas_value[0], "canvas[0]"),
                            _spec_number(canvas_value[1], "canvas[1]"))
        else:
            raise FigureSpecError("canvas must be {width, height} or [width, height]")
    try:
        scene = FigureScene(style=style, canvas=canvas, background=str(background))
    except (GeometryValidationError, TypeError) as exc:
        raise FigureSpecError(str(exc)) from exc

    point_records = _named_records(spec.get("points"), "points")
    circle_records = _named_records(spec.get("circles"), "circles")
    segment_records = _named_records(spec.get("segments"), "segments")
    angle_records = _named_records(spec.get("angles"), "angles")
    dimension_records = _named_records(spec.get("dimensions"), "dimensions")

    raw_points: list[tuple[str, Any]] = []
    constructed_points: list[tuple[str, Mapping[str, Any], str]] = []
    for name, item in point_records:
        if isinstance(item, Sequence) and not isinstance(item, (str, bytes)):
            if len(item) != 2:
                raise FigureSpecError(f"points.{name} coordinate pair must have length 2")
            raw_points.append((name, {"x": item[0], "y": item[1]}))
            continue
        if not isinstance(item, Mapping):
            raise FigureSpecError(f"points.{name} must be an object or [x, y]")
        kind = str(item.get("type", item.get("kind", "raw"))).lower().replace("-", "_")
        if kind == "raw":
            _strict_keys(item, {"type", "kind", "x", "y"}, f"points.{name}")
            if "x" not in item or "y" not in item:
                raise FigureSpecError(f"points.{name} raw point requires x and y")
            raw_points.append((name, item))
        elif kind in {"on_circle", "intersection"}:
            constructed_points.append((name, item, kind))
        else:
            raise FigureSpecError(f"points.{name} has unknown type {kind!r}")

    try:
        for name, item in raw_points:
            scene.add_point(name, _spec_number(item["x"], f"points.{name}.x"),
                            _spec_number(item["y"], f"points.{name}.y"))

        for name, item in circle_records:
            if not isinstance(item, Mapping):
                raise FigureSpecError(f"circles.{name} must be an object")
            _strict_keys(item, {"center", "radius"}, f"circles.{name}")
            if "center" not in item or "radius" not in item:
                raise FigureSpecError(f"circles.{name} requires center and radius")
            scene.add_circle(name, str(item["center"]),
                             _spec_number(item["radius"], f"circles.{name}.radius"))

        for name, item, kind in constructed_points:
            if kind == "on_circle":
                _strict_keys(item, {"type", "kind", "circle", "angle", "angle_deg"},
                             f"points.{name}")
                if "circle" not in item or ("angle" not in item and "angle_deg" not in item):
                    raise FigureSpecError(
                        f"points.{name} on_circle requires circle and angle")
                if "angle" in item and "angle_deg" in item:
                    raise FigureSpecError(
                        f"points.{name} provides both angle and angle_deg")
                angle_value = item.get("angle", item.get("angle_deg"))
                scene.point_on_circle(name, str(item["circle"]),
                                      _spec_number(angle_value, f"points.{name}.angle"))

        for name, item in segment_records:
            if isinstance(item, Sequence) and not isinstance(item, (str, bytes)):
                p1, p2 = _pair(item, f"segments.{name}")
                scene.add_segment(name, p1, p2)
                continue
            if not isinstance(item, Mapping):
                raise FigureSpecError(f"segments.{name} must be an object or [p1, p2]")
            _strict_keys(item, {"points", "p1", "p2", "dash", "dashed"},
                         f"segments.{name}")
            if "points" in item:
                if "p1" in item or "p2" in item:
                    raise FigureSpecError(f"segments.{name}: use points or p1/p2, not both")
                p1, p2 = _pair(item["points"], f"segments.{name}.points")
            else:
                if "p1" not in item or "p2" not in item:
                    raise FigureSpecError(f"segments.{name} requires p1 and p2")
                p1, p2 = str(item["p1"]), str(item["p2"])
            dash = item.get("dash", item.get("dashed"))
            scene.add_segment(name, p1, p2, dashed=None if dash is None else str(dash))

        for name, item, kind in constructed_points:
            if kind == "intersection":
                _strict_keys(item, {"type", "kind", "segments", "segment1", "segment2"},
                             f"points.{name}")
                if "segments" in item:
                    if "segment1" in item or "segment2" in item:
                        raise FigureSpecError(
                            f"points.{name}: use segments or segment1/segment2, not both")
                    segment1, segment2 = _pair(item["segments"], f"points.{name}.segments")
                else:
                    if "segment1" not in item or "segment2" not in item:
                        raise FigureSpecError(
                            f"points.{name} intersection requires two segments")
                    segment1, segment2 = str(item["segment1"]), str(item["segment2"])
                scene.intersection(name, segment1, segment2)

        for name, item in angle_records:
            if not isinstance(item, Mapping):
                raise FigureSpecError(f"angles.{name} must be an object")
            _strict_keys(item, {"vertex", "points", "p1", "p2", "radius", "label",
                                "label_distance"}, f"angles.{name}")
            if "vertex" not in item:
                raise FigureSpecError(f"angles.{name} requires vertex")
            if "points" in item:
                if "p1" in item or "p2" in item:
                    raise FigureSpecError(f"angles.{name}: use points or p1/p2, not both")
                p1, p2 = _pair(item["points"], f"angles.{name}.points")
            else:
                if "p1" not in item or "p2" not in item:
                    raise FigureSpecError(f"angles.{name} requires two ray points")
                p1, p2 = str(item["p1"]), str(item["p2"])
            scene.add_angle(
                name, str(item["vertex"]), p1, p2,
                radius=None if item.get("radius") is None else _spec_number(
                    item["radius"], f"angles.{name}.radius"),
                label=item.get("label"),
                label_distance=None if item.get("label_distance") is None else _spec_number(
                    item["label_distance"], f"angles.{name}.label_distance"))

        for name, item in dimension_records:
            if not isinstance(item, Mapping):
                raise FigureSpecError(f"dimensions.{name} must be an object")
            _strict_keys(item, {"points", "p1", "p2", "label", "side",
                                "offset", "curvature", "inset", "font_size"},
                         f"dimensions.{name}")
            if "label" not in item:
                raise FigureSpecError(f"dimensions.{name} requires label")
            if "points" in item:
                if "p1" in item or "p2" in item:
                    raise FigureSpecError(
                        f"dimensions.{name}: use points or p1/p2, not both")
                p1, p2 = _pair(item["points"], f"dimensions.{name}.points")
            else:
                if "p1" not in item or "p2" not in item:
                    raise FigureSpecError(
                        f"dimensions.{name} requires two endpoint refs")
                p1, p2 = str(item["p1"]), str(item["p2"])
            offset = (None if item.get("offset") is None else
                      _spec_number(item["offset"], f"dimensions.{name}.offset"))
            curvature = (None if item.get("curvature") is None else
                         _spec_number(item["curvature"],
                                      f"dimensions.{name}.curvature"))
            scene.add_dimension(
                name, p1, p2, item["label"],
                side=str(item.get("side", "auto")),
                offset=offset,
                curvature=curvature,
                inset=_spec_number(item.get("inset", 3.0),
                                    f"dimensions.{name}.inset"),
                font_size=None if item.get("font_size") is None else _spec_number(
                    item["font_size"], f"dimensions.{name}.font_size"))

        labels_value = spec.get("labels")
        if labels_value is not None:
            if isinstance(labels_value, Mapping):
                label_records = [(str(key), value) for key, value in labels_value.items()]
            elif isinstance(labels_value, Sequence) and not isinstance(labels_value, (str, bytes)):
                label_records = []
                for index, item in enumerate(labels_value):
                    if not isinstance(item, Mapping) or "point" not in item:
                        raise FigureSpecError(f"labels[{index}] requires point")
                    label_records.append((str(item["point"]), item))
            else:
                raise FigureSpecError("labels must be an object or list")
            for point_name, item in label_records:
                if isinstance(item, str):
                    scene.add_point_label(point_name, item)
                    continue
                if item is None:
                    scene.add_point_label(point_name)
                    continue
                if not isinstance(item, Mapping):
                    raise FigureSpecError(f"label {point_name!r} must be text or object")
                _strict_keys(item, {"point", "text", "position", "dx", "dy",
                                    "font_size", "italic"}, f"labels.{point_name}")
                if "point" in item and str(item["point"]) != point_name:
                    raise FigureSpecError(f"labels.{point_name}.point conflicts with its key")
                italic = item.get("italic", False)
                if not isinstance(italic, bool):
                    raise FigureSpecError(f"labels.{point_name}.italic must be boolean")
                scene.add_point_label(
                    point_name, item.get("text"), position=str(item.get("position", "auto")),
                    dx=None if item.get("dx") is None else _spec_number(
                        item["dx"], f"labels.{point_name}.dx"),
                    dy=None if item.get("dy") is None else _spec_number(
                        item["dy"], f"labels.{point_name}.dy"),
                    font_size=None if item.get("font_size") is None else _spec_number(
                        item["font_size"], f"labels.{point_name}.font_size"),
                    italic=italic)
        scene.validate()
    except FigureSpecError:
        raise
    except GeometryValidationError as exc:
        raise FigureSpecError(str(exc)) from exc
    return scene


def render_figure_spec(spec: Mapping[str, Any] | FigureSpec) -> str:
    """Compile and render a dictionary FigureSpec in one call."""

    return compile_figure_spec(spec).render_svg()


def intersecting_chords_template(*, width: Number = 187, height: Number = 171,
                                 background: str = "white",
                                 angle_label: str = "x°") -> FigureScene:
    """Build the clean four-point intersecting-chords figure used as v2's benchmark.

    The geometry matches the user's reference structure: A/B/C/D lie exactly on
    one circle, chords AC and BD meet at P, and the right-hand angle DPC is
    marked.  The fixed 187×171 canvas mirrors the source aspect ratio.
    """

    width_value = _finite(width, "template width")
    height_value = _finite(height, "template height")
    if width_value <= 0 or height_value <= 0:
        raise GeometryValidationError("template width and height must be positive")
    sx, sy = width_value / 187.0, height_value / 171.0
    scale = min(sx, sy)
    cx, cy, radius = 94.0 * sx, 78.0 * sy, 69.0 * scale
    style = replace(StyleProfile.exam_thin(),
                    font_size=13.0 * scale, angle_font_size=12.0 * scale,
                    label_offset=11.5 * scale, angle_radius=15.0 * scale,
                    angle_label_distance=25.0 * scale,
                    circle_width=max(0.8, 1.35 * scale),
                    segment_width=max(0.8, 1.25 * scale),
                    mark_width=max(0.7, 1.0 * scale))
    scene = FigureScene(style=style, canvas=Canvas(width_value, height_value),
                        background=background)
    scene.add_point("O", cx, cy)
    scene.add_circle("omega", "O", radius)
    for name, angle in (("A", 134.0), ("B", 204.0), ("C", 308.0), ("D", 36.0)):
        scene.point_on_circle(name, "omega", angle)
    scene.add_segment("AC", "A", "C")
    scene.add_segment("BD", "B", "D")
    scene.intersection("P", "AC", "BD")
    scene.add_angle("DPC", "P", "D", "C", label=angle_label)
    # Explicit compass hints reproduce the reference typography; the engine's
    # automatic collision scorer remains available when specs omit positions.
    for point_name, position in (("A", "NW"), ("B", "W"), ("C", "SE"),
                                 ("D", "NE"), ("P", "W")):
        scene.add_point_label(point_name, position=position)
    scene.validate()
    return scene


__all__ = [
    "AngleMark", "Canvas", "Circle", "DimensionLayout", "DimensionMark",
    "FigureScene", "FigureSpec",
    "FigureSpecError", "GeometryValidationError", "Point", "PointLabel",
    "ResolvedScene", "Segment", "StyleProfile", "compile_figure_spec",
    "intersecting_chords_template", "render_figure_spec",
]
