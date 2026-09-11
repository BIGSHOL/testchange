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

# `mj_attr` — 「이 라벨을 `data-mj` 로 실을 수 있나」의 규칙은 검사기와 **한 곳**에
# 있어야 한다. 못 실을 글에 붙이면 안전 검사가 그림 전체를 죽인다.
from core.figure_quality import mj_attr
from core.figure_svg import angle_arc, circle_pt, isect
from core.label_markup import (LabelMarkupError, label_pieces_svg,
                               label_width_em)


Number = int | float
Box = tuple[float, float, float, float]
_EPS = 1.0e-9

# 붙은 변들의 단위벡터 합이 이보다 짧으면 **바깥이 정의되지 않는다**(선분 위의 점·
# 교점). 억지로 방향을 정하지 않고 옛 순서로 물러선다 — `_outward_vector` 참조.
_OUTWARD_MIN = 0.30

# 🔴 **꼭짓점 이름표는 «옆»에 붙는다** — 이등분선 방향을 그대로 쓰지 않는다.
#
# 원장님 지시 2026-08-28: 「A B C 라벨 같은거 위치가 제일 중요해. **꼭짓점의 위치에
# 따라 적절하게 있어야 한단 말야.** 그걸 RPM에서 학습하란 얘기야」.
#
# RPM 정본 6권 · 꼭짓점 이름표 **8,880개**를 벡터로 재니(`measure-rpm-label-placement.py`)
# 라벨이 앉는 8방위가 **축(E·W·N·S) 71.3% 대 대각선 28.7%** 였다. 이등분선을 그대로
# 쓰면 그 분포가 고르게 나온다 — 우리 엔진이 실제로 그랬다(대각선 47.7%).
#
# 확대해 보면 이유가 보인다. 2-2 p.45 평행사변형 실측:
#     A 이등분선 125° → 실제 159.8°   B 215° → 189.8°
#     C 305° → 343.2°                D  35° →  12.1°
# 넷 다 **수평 쪽으로 23~38° 당겨져** 있다. **글자는 가로로 쓴다** — 옆에 붙이면
# 읽기 좋고 지면도 덜 먹는다.
#
# 그래서 세로 성분만 이만큼으로 눌러 다시 정규화한 방향으로 후보를 정렬한다.
# 값은 **정본에서 맞췄다**(`scripts/qa/fit-label-direction.py`) — 두 자가 같은 답이다:
#   ⑴ 8방위 분포가 RPM 과 겹치는 값 = **0.4**(축 71.2% vs 정본 71.3%)
#   ⑵ 각도 오차 중앙이 가장 작은 값 = 0.4~0.5 (전체) · 0.40 (변 3개 이상)
# 순수 수직(90°)은 안 움직이고, 45° 대각선이 21.8° 로 눕는다.
_LABEL_PULL = 0.4
_SAFE_PAINT_NAMES = {
    "black", "white", "gray", "grey", "red", "green", "blue", "yellow",
    "orange", "purple", "brown", "pink", "navy", "teal", "maroon",
    "silver", "lime", "aqua", "fuchsia",
}
# 영역(region) 채색은 **연한 색만** — 본문 잉크(선·라벨·치수)가 채색 위에서도
# 또렷해야 한다.  RPM 실측 지면색은 0.85~0.90 (#f2d5c8 살구 0.855 · #f5e6b8 노랑
# 0.90 · #d5e8f0 하늘 0.88).  0.78 은 그 무리 아래·중간톤 위의 빈 틈이다.
REGION_MIN_LUMINANCE = 0.78
# 호 하나를 충돌 검사용 폴리라인으로 다듬는 표본 수.  33이면 360° 호에서도
# 이웃 표본 간 11.25° — 반지름 100 기준 시위 오차 0.5px 미만이다.
_ARC_SAMPLE_COUNT = 33

# ── 같음(tick)·평행(»)·직각 마크 상수 ──────────────────────────────────────
# RPM 2-2 합동 단원 지면(p12~18) 벡터 실측(2026-08-23, 좌표·수치는 베끼지 않고
# **비율만** 본다): 본선 0.80pt · 보조선 0.50pt · 마크(틱/각 호/직각기호) 0.30pt.
# 마크는 각 호와 **같은 굵기**다 — 그래서 여기서도 style.mark_width 를 그대로 쓴다.
# tick 전장 4.25pt ≈ 직각기호 한 변(4.0~4.7pt) ≈ 각 호 반지름(8~11pt)의 절반.
# 우리 지면 척도(변 ~150px · angle_radius 15px)로 옮기면 tick 전장 8px 이 같은 비율.
_TICK_HALF = 4.0            # tick 절반 길이 — 전장 8px
_MARK_GAP = 3.0             # 이중·삼중 tick 사이 / 이중 호 반지름 차 (계획 지침 3px)
_CHEVRON_ARM = 6.5          # 평행 » 한 획 길이 (RPM 화살촉 5.4×3.4pt 비율에 맞춤)
_CHEVRON_HALF_ANGLE_DEG = 30.0
_CHEVRON_GAP = 4.0          # 이중 » 사이 간격
_RIGHT_ANGLE_SCALE = 0.55   # 직각기호 한 변 = 호 반지름 × 0.55 (실측 0.45~0.55)
# 짧은 변에 맞춰 줄일 때의 비율과, 「이보다 작아지면 못 읽는다」는 바닥 (2026-09-02).
# 0.85 는 기호가 변 끝을 안 넘게 하는 값이고, 6.0px 는 지면 등급 240px 에서 눈에 보이는 하한이다.
_RIGHT_ANGLE_FIT = 0.85
_RIGHT_ANGLE_MIN_SIDE = 6.0
# 치수 값 글자의 하한. 지면 등급 240px · viewBox 220 안팎에서 10 단위는 약 11px 이라
# 본문(12.5px) 아래다 — 그래서 «더 줄이지 말고 던진다» 는 뜻의 바닥이다.
_DIMENSION_MIN_FONT = 10.0
_BOTH_MARKS_SHIFT = 6.0     # 한 선분에 tick·» 둘 다면 중점에서 서로 반대로 비킨다
# 직각 마크는 검산을 겸한다 — 두 변이 90°±0.5° 밖이면 그림이 거짓말이므로 던진다.
_RIGHT_ANGLE_COS_TOL = math.cos(math.radians(89.5))


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
    # 🔴 **RPM 원본 실측에 맞췄다** (2026-08-28, 원장님 확정 「동일하게」).
    #    배율은 함께 움직이므로 **도형 선 길이를 1 로 둔 비율**로 재서 맞췄다.
    #    원본(1-2 p.16 · 0080): 선 길이 78.3pt · 선 굵기 0.80pt · 호 굵기 0.30pt
    #                          · 라벨 글자 8.00pt
    #      → 선/길이 1.02%  ·  호/선 0.375배  ·  글자/길이 10.2%
    #    우리 그림은 보통 180~200 단위를 쓰므로 그 비율을 그대로 옮겼다.
    #    ⚠️ **호를 도형 선보다 가늘게** — 같은 굵기면 호가 도형의 일부처럼 보인다.
    circle_width: float = 1.9
    segment_width: float = 1.9
    mark_width: float = 0.72
    point_radius: float = 2.1
    show_points: bool = False
    # 🔴 **RPM 그림 글꼴을 찾아서 맞췄다** (2026-08-28).
    #    원본에 박힌 글꼴(`EHsang-Plain`·`EHhabu-Plain`)은 **부분집합이라 이름이
    #    지워져 있고 `cmap` 도 없다** — 이름으로는 못 찾는다. 그래서 원본 지면에서
    #    글자를 오려 내고 설치 글꼴 12종으로 같은 글자를 그려 **겹치는 넓이(IoU)**
    #    로 쟀다(`scripts/qa/rpm_font_match.py`):
    #      HancomEQN **0.814** · HyhwpEQ 0.649 · Batang 0.628 · Times 0.558
    #    숫자·소문자만 보면 0.87~0.97 로 **사실상 같은 글꼴**이다(`A`·`B`·`C` 가
    #    낮은 것은 오려낸 원본에 윗줄이 딸려 왔기 때문이지 글꼴 차이가 아니다).
    #    `EHsang`/`EHhabu` 는 한컴 수식 글꼴 식구다 — RPM 이 HWP 로 조판되니 맞다.
    #    ⚠️ HancomEQN 에 없는 글자가 셋 있다(`□`·`∥`·`∽`) — 뒤 글꼴이 받는다.
    font_family: str = "Cambria Math, HancomEQN, Times New Roman, serif"
    #: 이탤릭 조각(변수)에만 쓰는 글꼴. 수식 글꼴에는 이탤릭 판이 없어서
    #: 그대로 두면 브라우저가 기울기를 흉내 낸다 — 진짜 이탤릭을 따로 준다.
    font_family_italic: str = "Cambria, Times New Roman, serif"
    # RPM 실측: 숫자 잉크 높이 0.659em x 8pt = 5.27pt = **밑변(56.4pt)의 9.34%**.
    #           우리 도형은 180 단위이므로 잉크 16.8 → Cambria Math(0.690em) 에서 24.
    #
    # 🔴 **원장님 확정 2026-08-29 — 글자를 «70%» 로** (D-07 · 절대 규칙 1).
    #    위 유도는 「우리 도형은 180 단위」를 전제했는데 **실제 도형은 그보다 크다.**
    #    그래서 상수는 옳게 유도됐는데 산출물은 라벨이 컸다 — 「상수만 보고 적지 말고
    #    산출물을 다시 재라」는 바로 아래 경고가 이 자리에서 그대로 실현된 것이다.
    #
    #    산출물 실측(중등 v2 도형 200장, `measure-rpm-weight-ratio.py` 「도형 대각 ÷ 라벨」):
    #        100% → **8.072**  ·  90% → 8.742  ·  80% → 9.785  ·  **70% → 11.182**
    #    정본(RPM 6권) 은 **11.88** 이다. 즉 옛 값은 라벨이 **47% 컸고**, 70% 가
    #    정본과 6% 차로 붙는다. 시안 넷을 실물로 내어 원장님이 70% 를 고르셨다
    #    (「rpm처럼 깔끔한 비율로」·「앞으로 엔진이 내는 모든 것에 일률 적용」).
    #
    #    ⚠️ **여기만 고치면 된다** — 호출하는 쪽이 배율을 넘기지 않는다. 그래야
    #       앞으로 나오는 그림도 자동으로 같은 비율이다(규칙을 두 벌로 두지 않는다).
    #    ⚠️ 글자와 **글자가 차지하는 여백**만 줄인다. 도형 선 굵기(`dimension_width`)와
    #       각 호 반지름(`angle_radius`)은 그대로다 — 실측에서 이미 정본과 같다
    #       (치수 점선 0.72 / 도형 선 1.9 = 0.379, 정본 0.375).
    font_size: float = 16.8
    angle_font_size: float = 16.8
    # 글자가 커지면 닻점에서 더 멀리 놓아야 표시 위에 안 앉는다 (글자 24 기준).
    #
    # 🔴 **원장님 확정 2026-08-28 — 「라벨 거리는 RPM 만큼으로」** (D-07 · 절대 규칙 1).
    #    RPM 정본 6권의 꼭짓점 이름표는 꼭짓점에서 글자 중심까지 **글자 크기의 0.61배**
    #    (25% 0.55 · 중앙 0.61 · 75% 0.71)인데 우리는 **1.05배**였다 — **1.7배 멀었다.**
    #    이 값은 부분집합을 갈라도 안 흔들린다(변 2개 0.61 · 변 3개 이상 0.60).
    #    시안 넷(1.04 / 0.87 / 0.75 / 0.64)을 실물 HTML 로 내어 원장님이 고르셨다.
    #
    #    ⚠️ **여기 적는 값이 곧 거리가 아니다.** 실제 거리는 아래 `_place_labels` 에서
    #       `label_offset + 0.18*fs + 자리순위 * max(3.5, 0.55*fs)` 다. 글자 24 에서
    #       1순위 자리가 `11 + 4.32 = 15.32` → **0.64배**. 21 이던 옛 값은 1.06배였다.
    #       그러니 이 상수를 고쳤으면 **산출물을 다시 재라** — 상수만 보고 적지 말 것.
    #    ⚠️ 70% 로 줄일 때 **글자와 같은 비율로** 줄인다(11 → 7.7). 그래야
    #       위 「0.61배」가 보존된다: `7.7 + 0.18*16.8 = 10.72` → **0.638배**.
    #       글자만 줄이면 거리가 상대적으로 멀어져 원장님 확정이 깨진다.
    label_offset: float = 7.7
    padding: float = 12.0
    # RPM 실측: 각 호 반지름이 밑변의 **14%** 다(우리 옛 값은 8.3%).
    # ⚠️ 이것은 **도형 표시**이지 글자가 아니다 — 70% 축소에서 건드리지 않는다.
    angle_radius: float = 22.0
    angle_label_distance: float = 17.5
    # RPM 실측: 치수 점선은 굵기 0.30pt — 도형 선(0.80)의 **0.375배**이고,
    #           글자는 도형 라벨과 **같은 8pt** 다. 점선은 `[1.5 1]`(짧고 촘촘).
    # ⚠️ 굵기는 **선**이라 안 줄인다 — 실측 0.72/1.9 = 0.379 로 이미 정본(0.375)이다.
    dimension_width: float = 0.72
    dimension_font_size: float = 16.8
    # 🔴 **이 값은 70% 로 안 줄인다.** 글자 크기가 아니라 **선에서 떨어지는 간격**이다.
    #    9.8 로 줄였더니 치수 곡선이 도형 쪽으로 파고들어
    #    `dimension 'd_AB' has no collision-free layout` 로 **그림이 통째로 안 나왔다**
    #    (3-2 삼각비의 활용 09·10 실측 5건 — `middleFigureRenderable.test.ts` 가 잡았다).
    #    글자를 줄이면 라벨 상자가 작아져 여유가 생기지만, **간격까지 줄이면 그 여유를
    #    도로 까먹는다.** 줄이려면 그 시험을 먼저 통과시키고 산출물을 다시 재라.
    dimension_offset: float = 14.0
    dimension_dash: str = "5 3"
    # ⚠️ halo 는 글자 뒤 흰 바탕이라 글자와 함께 줄인다. 아래 검증이 **3.0 이상**을
    #    요구하므로 `4.5 * 0.7 = 3.15` 가 하한에 바짝 붙는다 — 여기서 더 줄이려면
    #    그 검증부터 봐야 한다(줄이면 «허용되지 않은 값» 으로 그림이 통째로 안 나온다).
    dimension_halo_width: float = 5.6
    halo_color: str = "#ffffff"
    halo_width: float = 3.15

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
    """A named circle whose center is a named point.

    ``draw=False`` keeps the circle as pure construction geometry: points can
    still be placed on it and arcs/regions can still reference it, but no full
    circumference is inked, it contributes nothing to bounds, and labels or
    dimension curves may cross it freely.  Sector and shaded-region figures
    need this — the printed page shows only arc pieces, never the full circle.
    """

    name: str
    center: str
    radius: float
    draw: bool = True


@dataclass(frozen=True, slots=True)
class ArcStroke:
    """A stroked circular arc from one named point to another along a circle.

    ``direction`` is the mathematical sense (``ccw`` = counter-clockwise as
    seen on screen, matching :meth:`FigureScene.point_on_circle` angles).
    """

    name: str
    circle: str
    p1: str
    p2: str
    direction: str = "ccw"
    dash: str | None = None


@dataclass(frozen=True, slots=True)
class RegionPiece:
    """One boundary piece of a filled region: a segment or a circular arc.

    ``start``/``end`` are named points.  Arc pieces additionally reference a
    named circle and a traversal ``direction`` (same convention as
    :class:`ArcStroke`).
    """

    kind: str                    # "seg" | "arc"
    start: str
    end: str
    circle: str | None = None
    direction: str = "ccw"


@dataclass(frozen=True, slots=True)
class Region:
    """A closed filled region bounded by an ordered chain of pieces.

    The chain must close piece-to-piece **by point name** — piece *i* must end
    exactly where piece *i+1* starts and the last piece must end at the first
    piece's start.  A broken chain is an error, never silently filled.
    """

    name: str
    boundary: tuple[RegionPiece, ...]
    fill: str


@dataclass(frozen=True, slots=True)
class Segment:
    """A named finite segment between two named points.

    ``ticks`` (0~3) draws equal-length tick marks perpendicular to the segment
    at its midpoint; ``parallel`` (0~2) draws » chevrons pointing from ``p1``
    toward ``p2``.  Both may appear on one segment (they shift apart along the
    segment so neither overlaps the other).
    """

    name: str
    p1: str
    p2: str
    dashed: str | None = None
    ticks: int = 0
    parallel: int = 0


@dataclass(frozen=True, slots=True)
class AngleMark:
    """A small-angle arc and optional text label.

    ``arcs=2`` draws a second concentric arc just inside the first (각의
    이등분선의 «같은 각» 표시).  ``right=True`` replaces the arc with the small
    square right-angle mark and doubles as a check: the two rays must actually
    be perpendicular (90°±0.5°) or the scene refuses to render.
    """

    name: str
    vertex: str
    p1: str
    p2: str
    radius: float | None = None
    label: str | None = None
    label_distance: float | None = None
    arcs: int = 1
    right: bool = False


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
    # 값이 곡선 위 **어디에** 앉았나(0~1). 점선의 틈을 그 자리에 낸다 —
    # 종전에는 틈이 늘 한가운데라, 값을 옆으로 옮기면 틈과 값이 갈라졌다.
    label_t: float = 0.5


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
    #: 각 이름 → (호 위 시작점, 라벨 자리). **도형 밖으로 끌어낸 각만** 들어간다.
    #: 좁은 각은 라벨이 안쪽에 못 들어가므로(배율로 안 풀린다) 밖에 놓고 지시선으로
    #: 임자를 밝힌다 — 원장님 지시 2026-08-27.
    angle_leaders: Mapping[str, tuple[tuple[float, float], tuple[float, float]]] =         field(default_factory=dict)

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


def _mark_count(value: Any, maximum: int, what: str) -> int:
    """Validate a 0..maximum mark-repeat count.  Booleans are refused —
    ``ticks: true`` from model output must fail loudly, not count as 1."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise GeometryValidationError(f"{what} must be an integer (0~{maximum})")
    if not 0 <= value <= maximum:
        raise GeometryValidationError(f"{what} must be between 0 and {maximum}")
    return value


def _safe_paint(value: Any, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GeometryValidationError(f"{what} must be a non-empty safe color")
    color = value.strip()
    if (color.lower() not in _SAFE_PAINT_NAMES
            and not re.fullmatch(r"#[0-9A-Fa-f]{3,4}|#[0-9A-Fa-f]{6}|#[0-9A-Fa-f]{8}", color)):
        raise GeometryValidationError(
            f"{what} must be a named or hexadecimal color without references")
    return color


def _region_fill_color(value: Any, what: str) -> str:
    """Validate a region fill: opaque hex (or ``white``) and **light**.

    Fills sit underneath every stroke and label, so a dark fill would bury
    the black exam ink.  Named dark colors and alpha channels are rejected
    outright — luminance under alpha compositing depends on what is behind,
    which this validator cannot know.
    """

    color = _safe_paint(value, what)
    lowered = color.lower()
    if lowered == "white":
        return color
    match = re.fullmatch(r"#([0-9a-f]{3}|[0-9a-f]{6})", lowered)
    if not match:
        raise GeometryValidationError(
            f"{what} must be 'white' or an opaque hex color (#rgb/#rrggbb)")
    digits = match.group(1)
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    red, green, blue = (int(digits[i:i + 2], 16) for i in (0, 2, 4))
    luminance = (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255.0
    if luminance < REGION_MIN_LUMINANCE:
        raise GeometryValidationError(
            f"{what} must be a light color: relative luminance "
            f"{luminance:.3f} < {REGION_MIN_LUMINANCE}")
    return color


def _validate_dash(value: Any, what: str) -> None:
    """Reject dash arrays without at least one positive finite length."""

    try:
        dash_values = [float(part) for part in str(value).replace(",", " ").split()]
    except ValueError as exc:
        raise GeometryValidationError(f"{what} must be a numeric list") from exc
    if (not dash_values or any(not math.isfinite(item) or item < 0
                               for item in dash_values)
            or not any(item > 0 for item in dash_values)):
        raise GeometryValidationError(
            f"{what} must contain non-negative lengths and at least one "
            "positive length")


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


#: 기준선 **아래로** 잉크가 내려가는 글자. 없으면 상자 아래끝이 기준선이다.
_DESCENDERS = set("gjpqy,;()[]{}/")

def _text_box(x: float, baseline_y: float, text: str, font_size: float,
               metrics: Mapping[str, tuple[float, float, float]] | None = None
               ) -> Box:
    # Deliberately a little conservative; this is collision/layout geometry,
    # not a font renderer.  CJK glyphs are approximately one em wide.
    # 🔴 **재는 쪽과 그리는 쪽이 같은 자를 써야 한다.** 라벨은 `label_markup`
    #    이 조판하므로(첨자는 작고 연산 앞뒤에 여백이 붙는다) 글자 수를 그대로
    #    세면 상자가 어긋난다. 조판을 못 하는 글은 예전 어림으로 둔다
    #    (그 글은 `render_svg` 도 그리기 전에 던진다).
    # 🔴 **잰 값이 있으면 그것만 쓴다.**  라벨은 MathJax 가 조판하므로 폭·높이도
    #    MathJax 가 잰 것이 참이다.  여기서 따로 어림하면 조판과 갈라지고,
    #    갈라진 만큼 라벨이 엉뚱한 자리에 앉는다(실측: 어림이 두 배였을 때
    #    라벨이 두 배 멀리 밀려났다).
    if metrics is not None and text in metrics:
        width_em, ascent_em, descent_em = metrics[text]
        half = max(0.31, width_em / 2.0) * font_size
        return (x - half, baseline_y - ascent_em * font_size,
                x + half, baseline_y + descent_em * font_size)
    try:
        width_units = label_width_em(text)
    except LabelMarkupError:
        width_units = sum(1.0 if ord(ch) > 0x2FF else 0.61 for ch in text)
    width = max(0.62, width_units) * font_size
    # 🔴 **em 상자가 아니라 «잉크 상자»다.**
    #
    #    종전에는 기준선 위 0.83em·아래 0.25em(= 1.08em)을 잡았다. 그런데 실제로
    #    그려지는 잉크는 브라우저 실측으로 **위 0.75em**이고, 내림 글자(g·j·p·q·y)
    #    가 없으면 **아래는 0**이다. 30% 높은 상자는 비스듬한 선과 더 일찍
    #    부딪히고, 그만큼 라벨이 멀리 밀려난다 — RPM 실측 18% 자리에 우리는 34%
    #    였다(`1-2 p.16 · 0080` 의 `3x°+5°`).
    #
    #    ⚠️ 판정기(`probe-figure-label-collisions.mjs`)도 같은 자리에서 틀렸었다 —
    #    `getBBox()` 가 em 상자를 돌려준다. **재는 쪽과 그리는 쪽이 같이** 잉크로
    #    옮겨야 한다. 한쪽만 옮기면 갈라져도 아무도 모른다.
    ascent = 0.75 * font_size
    descent = 0.22 * font_size if any(ch in _DESCENDERS for ch in text) else 0.0
    return (x - width / 2.0, baseline_y - ascent,
            x + width / 2.0, baseline_y + descent)


def _circle_intersects_box(cx: float, cy: float, radius: float, box: Box) -> bool:
    """원 **둘레**가 이 상자를 지나가는가 (안쪽만 겹치는 것은 아니다).

    둘레가 상자를 지나려면 상자에서 중심까지 **가장 가까운 거리 ≤ r ≤ 가장 먼 거리**
    여야 한다. `_candidate_cost` 는 «상자 중심과 반지름의 차 < 반대각선» 이라는
    어림을 쓰는데, 그 어림은 옆으로 긴 상자에서 **넉넉히 과보고**한다(라벨 상자가
    딱 그 모양이다). 여기서는 정확히 잰다.
    """
    nx = min(max(cx, box[0]), box[2])
    ny = min(max(cy, box[1]), box[3])
    near = math.hypot(cx - nx, cy - ny)
    far = max(math.hypot(cx - x, cy - y)
              for x in (box[0], box[2]) for y in (box[1], box[3]))
    return near <= radius <= far


def _leader_stop_radius(label: str, font_size: float, halo_width: float,
                        ux: float = 0.0, uy: float = 0.0) -> float:
    """지시선이 글자 앞에서 끊기는 거리 — 글자 상자 **경계까지** + 여백 + halo 반폭.

    halo 까지 안 비키면 지시선 끝이 흰 테두리에 먹혀 «끊긴 선»로 보인다
    (실측 0.2단위 침범, lint_svg 규칙 7 과 같은 자리).

    ⚠️ 종전에는 `max(반폭, 반높이)` **한 값**을 썼다 — 상자를 감싸는 **원**이다.
       그러면 위·아래에서 다가오는 지시선이 반**폭**만큼 떨어져 끊긴다: `25°` 는
       반폭 11·반높이 6.5 라 **4.5단위가 빈다**(실측 `m3-diameter-cross`). 지면에서
       지시선과 글자가 따로 노는 것처럼 보였다. 이제 다가오는 **방향으로** 상자
       경계를 찾는다(ux,uy 를 안 주면 옛 동작 — 가장 먼 쪽).
    """
    box = _text_box(0.0, 0.0, label, font_size)
    half_w = (box[2] - box[0]) / 2.0
    half_h = (box[3] - box[1]) / 2.0
    margin = 2.0 + halo_width / 2.0
    if ux == 0.0 and uy == 0.0:
        return max(half_w, half_h) + margin
    # 중심에서 (ux,uy) 방향으로 상자 경계까지 — 두 축의 문턱 중 **먼저 닿는** 쪽.
    tx = half_w / abs(ux) if ux else float("inf")
    ty = half_h / abs(uy) if uy else float("inf")
    return min(tx, ty) + margin


def _leader_is_drawable(anchor: tuple[float, float], pos: tuple[float, float],
                        label: str, font_size: float, halo_width: float) -> bool:
    """이 지시선이 **그릴 값어치가 있는 길이**인가.

    🔴 **짧은 지시선은 없느니만 못하다.** 호와 라벨이 가까우면 실제로 그려지는
    길이가 몇 단위뿐이라, 변을 가로지르는 **같음 표시(tick)로 읽힌다** — 그 순간
    문항의 뜻이 달라진다(합동 근거가 하나 더 생긴 것처럼 보인다). 실측
    `2-2|삼각형의 성질|06` 40° 판에서 8단위짜리 막대가 그랬고, **그 8 이 곧
    tick 전장**(`_TICK_HALF*2`)이다 — 우연이 아니다.

    그래서 문턱을 글자 크기가 아니라 **tick 전장**에 맨다: 그려지는 길이가 tick
    두 개분보다 길어야 한다. 지어낸 수가 아니라 «무엇으로 오해받는가»의 치수다.
    (`_TICK_HALF` 를 바꾸면 이 문턱도 같이 움직인다 — 한 숫자를 두 곳이 쓴다.)

    ⚠️ **이 판단은 «그릴 때»가 아니라 «고를 때» 해야 한다.** 그리기 단계에서만
    걸렀더니 라벨은 밖(=각의 바깥, 변 너머)에 선 채로 지시선만 사라져,
    **어느 각의 값인지 아무것도 말해 주지 않는 라벨**이 됐다 — 실측
    `m3-diameter-cross` 의 `25°` 가 제 쐐기를 떠나 AB 아래에 홀로 앉았다.
    밖에 세우는 것과 지시선을 긋는 것은 **한 결정**이다. 그래서 고르는 쪽과
    그리는 쪽이 이 함수 **하나**를 부른다.
    """
    dx = pos[0] - anchor[0]
    dy = pos[1] - 0.32 * font_size - anchor[1]
    length = math.hypot(dx, dy)
    if length == 0.0:
        return False
    stop_r = _leader_stop_radius(label, font_size, halo_width,
                                 dx / length, dy / length)
    return length - stop_r > 2.0 * (_TICK_HALF * 2.0)


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


def _arc_point_samples(name: str, center: Point, radius: float, start_deg: float,
                       signed_sweep_deg: float,
                       count: int = _ARC_SAMPLE_COUNT) -> tuple[Point, ...]:
    """Sample an arc as a deterministic polyline for collision and QA checks.

    Angles are mathematical degrees with the engine's SVG y-down correction
    (``y = cy - r*sin``), identical to ``core.figure_svg.circle_pt``.
    """

    samples: list[Point] = []
    for index in range(count):
        t = index / (count - 1)
        theta = math.radians(start_deg + signed_sweep_deg * t)
        samples.append(Point(f"{name}@{index}",
                             center.x + radius * math.cos(theta),
                             center.y - radius * math.sin(theta)))
    return tuple(samples)


def _arc_bbox(center: Point, radius: float, start_deg: float,
              signed_sweep_deg: float) -> Box:
    """Exact bounding box of an arc: endpoints plus covered axis extrema."""

    def covered(angle_deg: float) -> bool:
        if signed_sweep_deg >= 0:
            return (angle_deg - start_deg) % 360.0 <= signed_sweep_deg
        return (start_deg - angle_deg) % 360.0 <= -signed_sweep_deg

    xs: list[float] = []
    ys: list[float] = []
    for angle in (start_deg, start_deg + signed_sweep_deg):
        theta = math.radians(angle)
        xs.append(center.x + radius * math.cos(theta))
        ys.append(center.y - radius * math.sin(theta))
    # Math angle 0/180 are x extrema; 90/270 are **screen** y extrema (y-down).
    for quadrant in (0.0, 90.0, 180.0, 270.0):
        if covered(quadrant):
            theta = math.radians(quadrant)
            xs.append(center.x + radius * math.cos(theta))
            ys.append(center.y - radius * math.sin(theta))
    return (min(xs), min(ys), max(xs), max(ys))


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
    # 틈은 **값이 앉은 자리**에 낸다 — 한가운데로 박아 두면 값을 옆으로 옮겼을 때
    # 틈과 값이 갈라져, 값 밑에는 점선이 그대로 지나가고 엉뚱한 데가 비어 있다.
    centre = min(1.0 - delta, max(delta, layout.label_t))
    left_t, right_t = centre - delta, centre + delta

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


def _convex_hull(points: Sequence[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
    """Convex hull (monotone chain), counter-clockwise in screen coordinates.

    Fewer than three distinct points yields an empty hull — there is no interior
    to speak of, and callers must treat that as "everything is outside".
    """

    unique = sorted({(round(x, 6), round(y, 6)) for x, y in points})
    if len(unique) < 3:
        return ()

    def cross(o: tuple[float, float], a: tuple[float, float],
              b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def chain(sequence: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
        stack: list[tuple[float, float]] = []
        for point in sequence:
            while len(stack) >= 2 and cross(stack[-2], stack[-1], point) <= 0:
                stack.pop()
            stack.append(point)
        return stack

    lower = chain(unique)
    upper = chain(unique[::-1])
    hull = lower[:-1] + upper[:-1]
    return tuple(hull) if len(hull) >= 3 else ()


def _hull_depth(hull: Sequence[tuple[float, float]], x: float, y: float) -> float:
    """Signed distance from the hull boundary — **positive inside**.

    The chain above is built in one consistent orientation, but the figure's own
    coordinate handedness is not ours to assume, so both signs are tried and the
    larger taken.  Getting this backwards would silently invert the whole
    penalty: every dimension outside the shape would look like it is inside.
    """

    if len(hull) < 3:
        return -math.inf
    best = math.inf
    flipped = math.inf
    for index in range(len(hull)):
        ax, ay = hull[index]
        bx, by = hull[(index + 1) % len(hull)]
        ex, ey = bx - ax, by - ay
        length = math.hypot(ex, ey) or 1.0
        side = ((x - ax) * ey - (y - ay) * ex) / length
        best = min(best, side)
        flipped = min(flipped, -side)
    return max(best, flipped)


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
    arcs: dict[str, ArcStroke] = field(default_factory=dict, init=False)
    regions: dict[str, Region] = field(default_factory=dict, init=False)
    angles: dict[str, AngleMark] = field(default_factory=dict, init=False)
    dimensions: dict[str, DimensionMark] = field(default_factory=dict, init=False)
    labels: dict[str, PointLabel] = field(default_factory=dict, init=False)
    #: 라벨 → (폭em, 밑선 위em, 밑선 아래em).  **TS 가 MathJax 로 잰 값**이다.
    #: 비어 있으면 예전 어림으로 물러선다(파이썬만 직접 부르는 QA 도구용).
    label_metrics: dict[str, tuple[float, float, float]] = field(
        default_factory=dict, init=False)

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
        scene.arcs.update(self.arcs)
        scene.regions.update(self.regions)
        scene.angles.update(self.angles)
        scene.dimensions.update(self.dimensions)
        scene.labels.update(self.labels)
        scene.label_metrics.update(self.label_metrics)
        return scene

    def _ensure_global_new(self, name: str, kind: str) -> None:
        """Keep geometry names unambiguous across all primitive namespaces."""

        for existing_kind, collection in (
                ("point", self.points), ("circle", self.circles),
                ("segment", self.segments), ("arc", self.arcs),
                ("region", self.regions), ("angle", self.angles),
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
                   radius: Number, *, draw: bool = True) -> "FigureScene":
        """Add a circle.

        ``center`` normally names a point.  A :class:`Point` or ``(x, y)`` is
        accepted for compatibility with v1 tuple-based helper code; an internal
        named center point is created when necessary.  ``draw=False`` keeps the
        circle as construction geometry only (see :class:`Circle`).
        """

        if not isinstance(draw, bool):
            raise GeometryValidationError(f"circle {name!r} draw must be boolean")

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
        self.circles[name] = Circle(name, center_name, float(radius), draw)
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
                    *, dashed: str | None = None, ticks: int = 0,
                    parallel: int = 0) -> "FigureScene":
        """Add a named segment.

        Both ``add_segment('AC', 'A', 'C')`` and the compact
        ``add_segment('A', 'C')`` form are supported.  The compact form assigns
        the deterministic name ``A--C``.  ``ticks`` (0~3) draws equal-length
        marks at the midpoint; ``parallel`` (0~2) draws » chevrons pointing
        from ``p1`` toward ``p2``.
        """

        if p2 is None:
            endpoint1, endpoint2 = _name(name, "segment endpoint"), _name(p1, "segment endpoint")
            segment_name = f"{endpoint1}--{endpoint2}"
        else:
            segment_name = _name(name, "segment name")
            endpoint1, endpoint2 = _name(p1, "segment endpoint"), _name(p2, "segment endpoint")
        self._ensure_global_new(segment_name, "segment")
        self.segments[segment_name] = Segment(
            segment_name, endpoint1, endpoint2, dashed,
            _mark_count(ticks, 3, f"segment {segment_name!r} ticks"),
            _mark_count(parallel, 2, f"segment {segment_name!r} parallel"))
        return self

    def add_arc(self, name: str, circle: str, p1: str, p2: str,
                *, direction: str = "ccw", dash: str | None = None) -> "FigureScene":
        """Add a stroked arc along ``circle`` from point ``p1`` to ``p2``.

        ``direction`` is ``ccw`` (mathematical, counter-clockwise on screen)
        or ``cw``.  Both endpoints must lie exactly on the circle — use
        ``on_circle`` points; hand-rounded coordinates are rejected.
        """

        arc_name = _name(name, "arc name")
        self._ensure_global_new(arc_name, "arc")
        self.arcs[arc_name] = ArcStroke(
            arc_name, _name(circle, "arc circle ref"),
            _name(p1, "arc endpoint"), _name(p2, "arc endpoint"),
            str(direction).strip().lower(),
            None if dash is None else str(dash))
        return self

    def add_region(self, name: str, boundary: Sequence[RegionPiece],
                   fill: str) -> "FigureScene":
        """Add a filled region bounded by a closed chain of pieces.

        ``boundary`` is an ordered sequence of :class:`RegionPiece`.  The chain
        must connect end-to-start by point name and close back onto the first
        piece; ``fill`` must be a light opaque color (see
        :data:`REGION_MIN_LUMINANCE`).  All structural checks run again in
        :meth:`validate` so cached values are never trusted.
        """

        region_name = _name(name, "region name")
        self._ensure_global_new(region_name, "region")
        pieces = tuple(boundary)
        if not pieces or any(not isinstance(piece, RegionPiece) for piece in pieces):
            raise GeometryValidationError(
                f"region {region_name!r} boundary must be RegionPiece items")
        color = _region_fill_color(fill, f"region {region_name!r} fill")
        self.regions[region_name] = Region(region_name, pieces, color)
        return self

    def _arc_geometry(self, circle_name: str, start_name: str, end_name: str,
                      direction: str, what: str) -> tuple[Point, float, float, float]:
        """Resolve one arc to ``(center, radius, start_deg, signed_sweep_deg)``.

        Raises when an endpoint is off the circle or the sweep is degenerate.
        Positive sweep is counter-clockwise on screen (math angles, y-down
        corrected) and maps to SVG sweep-flag 0.
        """

        circle_obj = self.circles[circle_name]
        center = self.points[circle_obj.center]
        start, end = self.points[start_name], self.points[end_name]
        tolerance = max(1.0e-12, abs(circle_obj.radius) * 1.0e-7)
        for role, point in (("start", start), ("end", end)):
            residual = abs(math.hypot(point.x - center.x, point.y - center.y)
                           - circle_obj.radius)
            if residual > tolerance:
                raise GeometryValidationError(
                    f"{what} {role} point {point.name!r} is not on circle "
                    f"{circle_name!r} (residual {residual:.6g}); "
                    "construct it with on_circle")
        start_deg = math.degrees(math.atan2(-(start.y - center.y),
                                            start.x - center.x))
        end_deg = math.degrees(math.atan2(-(end.y - center.y),
                                          end.x - center.x))
        if direction == "ccw":
            sweep = (end_deg - start_deg) % 360.0
        elif direction == "cw":
            sweep = (start_deg - end_deg) % 360.0
        else:
            raise GeometryValidationError(
                f"{what} direction must be 'ccw' or 'cw', got {direction!r}")
        if sweep <= 1.0e-6 or sweep >= 360.0 - 1.0e-6:
            raise GeometryValidationError(
                f"{what} sweep is degenerate ({sweep:.6g}°): endpoints must be "
                "two distinct positions on the circle")
        return center, circle_obj.radius, start_deg, (
            sweep if direction == "ccw" else -sweep)

    def _segment_mark_lines(
            self, segment: Segment) -> list[tuple[tuple[float, float], tuple[float, float]]]:
        """Stroke endpoints for one segment's tick/» marks, scene coordinates.

        렌더와 경계 계산이 **같은 좌표**를 쓴다 — 두 벌이 되면 한쪽만 고쳐져도
        아무도 모른다.  마크가 선분 밖으로 비어져 나가면(짧은 선분) 던진다.
        """

        if not segment.ticks and not segment.parallel:
            return []
        a, b = self.points[segment.p1], self.points[segment.p2]
        length = math.hypot(b.x - a.x, b.y - a.y)
        ux, uy = (b.x - a.x) / length, (b.y - a.y) / length
        nx, ny = -uy, ux
        # 🔴 **선분 한복판에 다른 점이 얹혀 있으면 마크를 비킨다.**
        #    실측 `1-2|위치 관계|12`: 평행 표시 » 가 t 와의 교점 바로 위에 앉아
        #    **t 의 화살촉처럼** 읽혔다. 중점 표시(M)·교점은 흔히 한복판에 있다.
        #    비키는 자리는 「가장 넓은 빈 구간의 한복판」이다 — 문턱을 지어내지 않는다.
        center = self._segment_mark_center(segment, a, length, ux, uy, nx, ny)
        mid_x, mid_y = a.x + center * ux, a.y + center * uy
        both = bool(segment.ticks) and bool(segment.parallel)
        lines: list[tuple[tuple[float, float], tuple[float, float]]] = []

        if segment.ticks:
            shift = -_BOTH_MARKS_SHIFT if both else 0.0
            for index in range(segment.ticks):
                offset = shift + (index - (segment.ticks - 1) / 2.0) * _MARK_GAP
                cx_, cy_ = mid_x + offset * ux, mid_y + offset * uy
                lines.append(((cx_ - _TICK_HALF * nx, cy_ - _TICK_HALF * ny),
                              (cx_ + _TICK_HALF * nx, cy_ + _TICK_HALF * ny)))

        if segment.parallel:
            half = math.radians(_CHEVRON_HALF_ANGLE_DEG)
            depth = _CHEVRON_ARM * math.cos(half)
            wing = _CHEVRON_ARM * math.sin(half)
            shift = _BOTH_MARKS_SHIFT if both else 0.0
            for index in range(segment.parallel):
                tip_off = (shift + depth / 2.0
                           + (index - (segment.parallel - 1) / 2.0) * _CHEVRON_GAP)
                tip_x, tip_y = mid_x + tip_off * ux, mid_y + tip_off * uy
                back_x, back_y = tip_x - depth * ux, tip_y - depth * uy
                lines.append(((back_x + wing * nx, back_y + wing * ny),
                              (tip_x, tip_y)))
                lines.append(((tip_x, tip_y),
                              (back_x - wing * nx, back_y - wing * ny)))

        # 마크가 선분 **밖으로** 비어져 나가면 던진다. 마크 자리를 비켰을 수 있으므로
        # 「한복판에서 얼마나 뻗나」가 아니라 **선분 위 좌표**로 잰다.
        spans = [(x - a.x) * ux + (y - a.y) * uy for line in lines for x, y in line]
        if min(spans) < 2.0 or max(spans) > length - 2.0:
            raise GeometryValidationError(
                f"segment {segment.name!r} is too short ({length:.4g}px) for its "
                "tick/parallel marks — marks may not spill past the endpoints")
        return lines

    def _segment_mark_center(self, segment: Segment, a: Point, length: float,
                             ux: float, uy: float, nx: float,
                             ny: float) -> float:
        """마크가 앉을 자리 — 선분 **위에 얹힌 다른 점**을 피한 가장 넓은 빈 구간의 한복판.

        얹힌 점이 없으면 한복판(`length/2`)이라 옛 동작 그대로다.
        """
        cuts = [0.0, length]
        for name in sorted(self.points):
            if name in (segment.p1, segment.p2):
                continue
            point = self.points[name]
            along = (point.x - a.x) * ux + (point.y - a.y) * uy
            if along <= 0.0 or along >= length:
                continue
            if abs((point.x - a.x) * nx + (point.y - a.y) * ny) > 0.6:
                continue  # 선분에서 벗어난 점은 얹힌 것이 아니다.
            cuts.append(along)
        if len(cuts) == 2:
            return length / 2.0
        cuts.sort()
        best, widest = length / 2.0, -1.0
        for low, high in zip(cuts, cuts[1:]):
            if high - low > widest:
                widest, best = high - low, (low + high) / 2.0
        return best

    def _arc_stroke_samples(self, arc: ArcStroke) -> tuple[Point, ...]:
        center, radius, start_deg, signed = self._arc_geometry(
            arc.circle, arc.p1, arc.p2, arc.direction, f"arc {arc.name!r}")
        return _arc_point_samples(arc.name, center, radius, start_deg, signed)

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
                  label_distance: Number | None = None, arcs: int = 1,
                  right: bool = False) -> "FigureScene":
        """Add a small-angle arc between rays ``vertex->p1`` and ``vertex->p2``.

        ``arcs=2`` draws a double arc; ``right=True`` draws the square
        right-angle mark instead of an arc (and requires the rays to actually
        be perpendicular).  The two options exclude each other.
        """

        name = _name(name, "angle name")
        self._ensure_global_new(name, "angle")
        if label is not None and not isinstance(label, str):
            raise GeometryValidationError("angle label must be text or None")
        if not isinstance(right, bool):
            raise GeometryValidationError(f"angle {name!r} right must be boolean")
        arcs_value = _mark_count(arcs, 2, f"angle {name!r} arcs")
        if arcs_value == 0:
            raise GeometryValidationError(f"angle {name!r} arcs must be 1 or 2")
        if right and arcs_value != 1:
            raise GeometryValidationError(
                f"angle {name!r}: right=True replaces the arc; arcs must stay 1")
        self.angles[name] = AngleMark(
            name, _name(vertex, "angle vertex"), _name(p1, "angle ray ref"),
            _name(p2, "angle ray ref"), None if radius is None else float(radius),
            label, None if label_distance is None else float(label_distance),
            arcs_value, right)
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
                                 ("segment", self.segments), ("arc", self.arcs),
                                 ("region", self.regions), ("angle", self.angles),
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
            # 값이 add_segment 를 거치지 않고 들어와도 같은 규칙이 다시 돈다.
            _mark_count(segment.ticks, 3, f"segment {segment.name!r} ticks")
            _mark_count(segment.parallel, 2, f"segment {segment.name!r} parallel")
            # 마크가 선분 길이를 넘치면 여기서 던진다 (렌더와 같은 좌표 계산).
            self._segment_mark_lines(segment)

        for circle_obj in self.circles.values():
            if not isinstance(circle_obj.draw, bool):
                raise GeometryValidationError(
                    f"circle {circle_obj.name!r} draw must be boolean")

        for arc in self.arcs.values():
            if arc.circle not in self.circles:
                raise GeometryValidationError(
                    f"arc {arc.name!r} has unknown circle ref {arc.circle!r}")
            for ref in (arc.p1, arc.p2):
                if ref not in self.points:
                    raise GeometryValidationError(
                        f"arc {arc.name!r} has unknown point ref {ref!r}")
            if arc.p1 == arc.p2:
                raise GeometryValidationError(
                    f"arc {arc.name!r} endpoints must be two different points")
            if arc.dash is not None:
                _validate_dash(arc.dash, f"arc {arc.name!r} dash")
            # Raises on off-circle endpoints, bad direction, degenerate sweep.
            self._arc_geometry(arc.circle, arc.p1, arc.p2, arc.direction,
                               f"arc {arc.name!r}")

        for region in self.regions.values():
            _region_fill_color(region.fill, f"region {region.name!r} fill")
            if len(region.boundary) < 2:
                raise GeometryValidationError(
                    f"region {region.name!r} boundary needs at least two pieces")
            for index, piece in enumerate(region.boundary):
                what = f"region {region.name!r} boundary[{index}]"
                if piece.kind not in {"seg", "arc"}:
                    raise GeometryValidationError(
                        f"{what} has unknown piece kind {piece.kind!r}")
                for ref in (piece.start, piece.end):
                    if ref not in self.points:
                        raise GeometryValidationError(
                            f"{what} has unknown point ref {ref!r}")
                if piece.start == piece.end:
                    raise GeometryValidationError(
                        f"{what} endpoints must be two different points")
                if piece.kind == "seg":
                    a, b = self.points[piece.start], self.points[piece.end]
                    if math.hypot(a.x - b.x, a.y - b.y) <= _EPS:
                        raise GeometryValidationError(f"{what} has zero length")
                else:
                    if piece.circle is None or piece.circle not in self.circles:
                        raise GeometryValidationError(
                            f"{what} has unknown circle ref {piece.circle!r}")
                    self._arc_geometry(piece.circle, piece.start, piece.end,
                                       piece.direction, what)
            # 닫힘 검사 — 조각 끝점이 이어지지 않으면 던진다(조용히 채우기 금지).
            for index, piece in enumerate(region.boundary):
                following = region.boundary[(index + 1) % len(region.boundary)]
                if piece.end != following.start:
                    raise GeometryValidationError(
                        f"region {region.name!r} boundary does not connect: "
                        f"piece {index} ends at {piece.end!r} but the next "
                        f"piece starts at {following.start!r}")

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
            if _mark_count(angle.arcs, 2, f"angle {angle.name!r} arcs") == 0:
                raise GeometryValidationError(f"angle {angle.name!r} arcs must be 1 or 2")
            if angle.arcs == 2 and radius <= _MARK_GAP:
                raise GeometryValidationError(
                    f"angle {angle.name!r} radius {radius:.4g} leaves no room "
                    "for the inner arc")
            if not isinstance(angle.right, bool):
                raise GeometryValidationError(f"angle {angle.name!r} right must be boolean")
            if angle.right:
                if angle.arcs != 1:
                    raise GeometryValidationError(
                        f"angle {angle.name!r}: right=True replaces the arc; arcs must stay 1")
                # 직각 마크는 검산을 겸한다 — 90°±0.5° 밖이면 그림이 거짓말이다.
                cos_value = abs(v1[0] * v2[0] + v1[1] * v2[1]) / (l1 * l2)
                if cos_value > _RIGHT_ANGLE_COS_TOL:
                    actual = math.degrees(math.acos(
                        max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (l1 * l2)))))
                    raise GeometryValidationError(
                        f"angle {angle.name!r} is marked right but measures "
                        f"{actual:.2f}° — fix the geometry, not the mark")
                # 🔴 직각기호 크기가 **고정**이라 짧은 변에서 그림을 통째로 던졌다
                #    (2026-09-02). `radius(22.0) × 0.55 = 12.10px` 를 짧은 변과 견주는데,
                #    「수선의 발 H 와 가까운 꼭짓점」 사이 토막은 실측 8.5~10.2px 라
                #    발문 값 그대로 축척해 그리면 쪼그라든다. 그러면 **그림이 아예 안 나가고**
                #    지면에 「그림과 같이」만 남는다.
                #    이제 기호를 **짧은 변에 맞춰 줄이고**(아래 `side` 참조), 읽을 수 없을
                #    만큼 작아질 때만 던진다. 실측 3,140개 직각 중 클램프가 건드리는 자리는
                #    18개(0.57%)이고, 260표본 전후 대조에서 **성공→실패 0**이었다.
                if _RIGHT_ANGLE_FIT * min(l1, l2) < _RIGHT_ANGLE_MIN_SIDE:
                    raise GeometryValidationError(
                        f"angle {angle.name!r} right-angle square does not fit "
                        "inside its rays")

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

    def _angle_mark_polylines(self, angle: AngleMark) -> list[tuple[Point, ...]]:
        """각 표시(호 또는 직각 사각형)의 **잉크**를 폴리라인으로 돌려준다.

        렌더·경계·충돌이 **한 좌표**를 쓰게 하려는 것이다(`_segment_mark_lines` 와
        같은 무늬).  이것이 없던 동안 각 표시는 라벨 배치에 **보이지 않는 잉크**였고,
        그래서 직각기호 위에 `H` 가 그대로 앉았다(원장님 지적 2026-08-25,
        `J30503-A06-002`·`A07-002`).
        """
        vertex, p1, p2 = (self.points[angle.vertex], self.points[angle.p1],
                          self.points[angle.p2])
        radius = self.style.angle_radius if angle.radius is None else angle.radius
        if angle.right:
            length1 = math.hypot(p1.x - vertex.x, p1.y - vertex.y)
            length2 = math.hypot(p2.x - vertex.x, p2.y - vertex.y)
            if length1 <= _EPS or length2 <= _EPS:
                return []
            # 짧은 변을 넘지 않게 **줄인다** — 넘으면 기호가 도형 밖으로 튀어나온다.
            side = min(radius * _RIGHT_ANGLE_SCALE,
                       _RIGHT_ANGLE_FIT * min(length1, length2))
            u1x, u1y = (p1.x - vertex.x) / length1, (p1.y - vertex.y) / length1
            u2x, u2y = (p2.x - vertex.x) / length2, (p2.y - vertex.y) / length2
            return [(
                Point(f"{angle.name}@0", vertex.x + side * u1x, vertex.y + side * u1y),
                Point(f"{angle.name}@1", vertex.x + side * (u1x + u2x),
                      vertex.y + side * (u1y + u2y)),
                Point(f"{angle.name}@2", vertex.x + side * u2x, vertex.y + side * u2y),
            )]
        a0 = math.atan2(p1.y - vertex.y, p1.x - vertex.x)
        a1 = math.atan2(p2.y - vertex.y, p2.x - vertex.x)
        delta = (a1 - a0 + math.pi) % (2.0 * math.pi) - math.pi
        out: list[tuple[Point, ...]] = []
        for arc_index in range(angle.arcs):
            r = radius - arc_index * _MARK_GAP
            if r <= 0:
                continue
            out.append(tuple(
                Point(f"{angle.name}@{arc_index}:{i}",
                      vertex.x + r * math.cos(a0 + delta * i / 16.0),
                      vertex.y + r * math.sin(a0 + delta * i / 16.0))
                for i in range(17)))
        return out

    def _angle_label_layout(
            self, angle: AngleMark, occupied: Sequence[Box] = ()
    ) -> tuple[tuple[float, float], Box, tuple[float, float] | None] | None:
        """각 라벨 자리 — 이등분선 위에서 **비켜설 수 있는 만큼** 비켜선다.

        ⚠️ 종전에는 `angle_label_distance`(25) 한 값에 **무조건** 놓았다.  그 거리는
        직각쯤에서만 맞는다 — 반각 φ 에서 이등분선 위 점과 두 변 사이 거리는
        `d·sin φ` 라, $30^\\circ$ 각에서는 `25·sin 15° = 6.5` 로 글자 반높이(6.5)와
        **같아진다.**  그래서 `45°`·`30°` 가 변 위에 앉고 흰 halo 가 실선을 지웠다
        (원장님 지적 2026-08-25 「텍스트가 선을 침범한다」).

        문턱을 옮기지 않는다 — **각이 좁으면 그만큼 멀리 놓는다**.  그리고 그 거리도
        어림이 아니라 `_candidate_cost` 로 **실제 잉크와 견주어** 고른다.  못 비키면
        던지지 않고 가장 덜 나쁜 자리를 쓴다(각 라벨은 늘 그려져야 한다).
        """
        if not angle.label:
            return None
        vertex, p1, p2 = (self.points[angle.vertex], self.points[angle.p1],
                          self.points[angle.p2])
        a0 = math.atan2(p1.y - vertex.y, p1.x - vertex.x)
        a1 = math.atan2(p2.y - vertex.y, p2.x - vertex.x)
        delta = (a1 - a0 + math.pi) % (2.0 * math.pi) - math.pi
        mid = a0 + delta / 2.0
        fs = self.style.angle_font_size
        base = self.style.angle_label_distance
        if angle.label_distance is not None:
            # 부르는 쪽이 못 박았으면 그대로 둔다 — 스펙이 이긴다.
            distances = [angle.label_distance]
        else:
            # 좁은 각일수록 멀리 나가야 두 변 사이에 들어간다 — 필요한 거리는 대략
            # «글자 반폭 / sin(반각)» 이라 $30^\circ$ 에서 벌써 25 의 두 배가 넘는다
            # (실측: 반각 15°·「30°」 상자에서 58 이 필요했다).
            #
            # 🔴 **그런데 무작정 밀면 안 된다.** 각 값은 «제 꼭짓점의 값»으로 읽혀야 하는데,
            #    옆 꼭짓점 쪽으로 넘어가는 순간 **그 각의 값으로 읽힌다** — 그림이
            #    거짓말을 한다. 실측: 원주각 그림(`J30604-A12-001`)에서 `44°`·`40°` 가
            #    각각 A·C 를 떠나 가운데 교점 T 옆에 나란히 서 버렸다.
            #
            #    그래서 사다리를 **「가장 가까운 다른 이름 붙은 점까지의 절반」**에서 끊는다.
            #    문턱을 지어낸 것이 아니라 «어느 꼭짓점 것인가»가 갈리는 자리다.
            #    그 안에서 못 비키면 **가장 덜 나쁜 자리**를 쓴다(각 라벨은 늘 그려진다).
            named = {name for name in self.labels}
            named.update(angle_obj.vertex for angle_obj in self.angles.values())
            gaps = [
                math.hypot(self.points[name].x - vertex.x,
                           self.points[name].y - vertex.y)
                for name in sorted(named)
                if name != angle.vertex and name in self.points
            ]
            reach = min(gaps) / 2.0 if gaps else float("inf")
            step = max(3.5, 0.45 * fs)
            distances = [base + index * step for index in range(10)]
            distances = [d for d in distances if d <= reach] or [base]
        # ⚠️ 견주는 상자는 **halo 까지** 넓힌 것이다. 흰 halo 는 잉크를 더하지 않지만
        #    **밑의 실선을 지운다** — 글자 상자만 보면 「안 겹친다」인데 지면에서는
        #    선이 끊긴다(lint_svg 규칙 7). 경계(viewBox)에는 안 넓힌 상자를 쓴다.
        pad = self.style.halo_width / 2.0 + 0.5
        best: tuple[tuple[int, int, float], tuple[float, float], Box] | None = None
        for rank, distance in enumerate(distances):
            x = vertex.x + distance * math.cos(mid)
            y = vertex.y + distance * math.sin(mid) + 0.32 * fs
            box = _text_box(x, y, angle.label, fs, self.label_metrics)
            # 🔴 **고르는 자와 «밖으로 뺄까»를 판정하는 자가 같은 것을 봐야 한다.**
            #
            # 종전에는 `_candidate_cost` 로 고르고 `_label_hits_geometry` 로 판정했다.
            # 그 둘은 **다른 것을 본다** — cost 는 먼저 놓인 라벨·다른 각 표시까지
            # 세고, hits 는 오직 잉크만 본다. 그래서 **잉크를 안 밟는 후보가 있는데도**
            # cost 가 다른 것을 골라, 「안에 자리가 없다」로 밖으로 끌려 나갔다.
            # 실측 `3-2|삼각비의 활용|04`: 거리 후보 [17.5, 25.1, **32.6**] 중
            # 32.6 은 잉크를 안 밟는데(hits=0) 밖으로 나갔다 — 원장님 지적 2026-08-30
            # 「도형 내부에 60도를 적어도 충분한데 굳이 밖으로 뺌」.
            #
            # 그래서 **「잉크를 밟나」를 첫째 항으로** 올린다. 안 밟는 후보가 하나라도
            # 있으면 그것이 이기고, 그러면 아래 판정도 자연히 「안에 남는다」가 된다.
            # (같은 값을 두 번 재지 않도록 그 결과를 `best` 에 함께 싣는다.)
            hits = self._label_hits_geometry(box)
            cost = (1 if hits else 0,) + self._candidate_cost(
                "", _expand_box(box, pad), occupied, rank, 0, own_angle=angle.name)
            if best is None or cost < best[0]:
                best = (cost, (x, y), box)
            if cost[0] == 0 and cost[1] == 0:
                break
        assert best is not None
        # 🔴 **끌어낼지 말지의 열쇠는 «이 상자가 정말 잉크를 밟는가»다.**
        #
        # ⚠️ `cost[0]`(hard) 로 재면 안 된다. 그 수는 «먼저 놓인 라벨과 겹침»·«다른
        #    각 표시»까지 세므로 넉넉한 각에서도 0이 아니다. 그걸 열쇠로 썼다가
        #    **7장 전부를 밖으로 끌어냈다**(2026-08-27 첫 판). 원장님이 화면에서
        #    바로 잡아 주셨다 — 「완전 이상한데?」.
        # `best[0][0]` 이 곧 «이 상자가 잉크를 밟나»다 — 위에서 이미 쟀다.
        # 다시 부르면 두 자가 갈라질 자리를 또 만든다.
        if best[0][0] == 0:
            return best[1], best[2], None

        # ── 안쪽에 자리가 없다 → **밖으로 끌어내고 지시선을 긋는다** ──────────
        #
        # 원장님 지시 2026-08-27: 「적당한 크기로 구현했을때도 라벨 표현이 힘들면,
        # 화살표로 각을 도형 밖으로 끌어내서 표현해.」
        #
        # 🔴 **키운다고 들어가지 않는다.** 반각 φ 에서 이등분선 위 거리 d 의 여유는
        #    `d·sin φ` 이므로, 글자 반높이를 확보하려면 `d ≥ (fs/2)/sin φ` 다.
        #    $30^\circ$ 각이면 $d \ge 23.2$ 인데 그 삼각형의 **세로가 41** 이다 —
        #    각 안쪽이 아니라 도형 한복판이 된다. 이 비율은 **배율에 안 변한다.**
        #
        # ⚠️ **이등분선을 따라 더 밀면 안 된다.** 좁은 각의 이등분선은 도형 **안쪽**을
        #    향하므로, 밀면 라벨이 도형을 가로질러 반대편으로 나간다(첫 판이 그랬다 —
        #    원장님 「다른 도형도 가로질러 가고」).
        #
        # 나가는 곳은 **이등분선의 반대쪽**이다 — 원장님 지시 2026-08-27:
        # 「각의 중심에서 그냥 밖으로 선을 빼면 되잖아.」 그 방향은 각의 바깥이므로
        # 꼭짓점을 벗어나는 순간 도형 밖이고, 지시선은 **꼭짓점을 곧게 가리킨다**
        # (어느 각의 값인지 선 하나로 말한다). 그리고 **바로 근처**에 둔다 —
        # 자리를 못 얻을 때만 조금씩 넓힌다.
        radius = self.style.angle_radius if angle.radius is None else angle.radius
        # 지시선은 **각의 호에서** 시작한다 — 원장님 지시: 「각의 중심에서 그냥 밖으로
        # 선을 빼면 되잖아.」 이등분선 위 호의 한복판이라 「이 각의 값」임을 선 하나가
        # 말한다. (꼭짓점에서 시작하면 변에서 뻗은 또 하나의 반직선처럼 읽히고,
        # 이등분선 **반대쪽**으로 라벨을 두면 그 선이 꼭짓점을 뚫고 지나간다.)
        anchor = (vertex.x + radius * math.cos(mid),
                  vertex.y + radius * math.sin(mid))
        # 라벨은 **두 변 중 하나 바로 바깥**에 둔다 — 변을 한 번만 가로지르는 짧은
        # 지시선이 되어 도형을 안 가로지른다(원장님 「다른 도형도 가로질러 가고」).
        sign = 1.0 if delta >= 0 else -1.0
        best_out: tuple[float, tuple[float, float], Box, tuple[float, float]] | None
        best_out = None
        # 🔴 **먼저 되는 자리를 그냥 쓰면 안 된다 — 어느 팔로 나갈지가 «순서»로 정해진다.**
        #
        # 종전에는 첫 통과 후보에서 `break` 했다(first-fit). 그러면 나가는 팔이
        # `angle.p1`·`p2` 를 **스펙이 어느 차례로 적었는가**로 정해진다. 실측
        # `2-2|여러 가지 사각형|08`: 후보 **24개가 전부 통과**하는데 첫째(=`p1` 쪽,
        # 곧 $\overline{AB}$ 쪽)를 써서, 그 변의 `4 cm` 치수가 밀려났다.
        # 원장님 지적 2026-08-30 — 「60도를 아래쪽으로 해야 4cm 의 치수가 여유로워짐」.
        #
        # 그래서 **치수가 달린 팔을 피한다.** 각 라벨은 치수보다 먼저 놓이므로 치수가
        # «어디에» 올지는 모르지만, `self.dimensions` 를 보면 «어느 변을 잴지»는 안다.
        # 그 한 가지가 원장님이 말씀하신 바로 그 축이다.
        arm_taken = []
        for arm_point in (p1, p2):
            taken = False
            for dimension in self.dimensions.values():
                ends = (self.points[dimension.p1], self.points[dimension.p2])
                # 그 치수의 두 끝이 **이 팔 위**에 있나 (변 전체든 토막이든).
                if all(_distance_point_line(end, vertex, arm_point) <= 0.25
                       and _point_within_segment(end, vertex, arm_point, 0.25)
                       for end in ends):
                    taken = True
                    break
            arm_taken.append(taken)

        scored: list[tuple[tuple[int, int, int, int],
                           tuple[float, tuple[float, float], Box,
                                 tuple[float, float]]]] = []
        for far_rank, far in enumerate((1.2, 1.7, 2.3, 3.0)):
            distance = radius + fs * far
            for arm_rank, (arm, turn) in enumerate(((a0, -sign), (a1, sign))):
                for turn_rank, turn_deg in enumerate((30.0, 48.0, 66.0)):
                    direction = arm + turn * math.radians(turn_deg)
                    x = vertex.x + distance * math.cos(direction)
                    y = vertex.y + distance * math.sin(direction) + 0.32 * fs
                    box = _text_box(x, y, angle.label, fs, self.label_metrics)
                    if self._label_hits_geometry(box):
                        continue
                    grown = _expand_box(box, pad)
                    if any(_boxes_overlap(grown, other, gap=1.0) for other in occupied):
                        continue
                    # 밖에 세우는 것과 지시선을 긋는 것은 **한 결정**이다 — 지시선을
                    # 못 그을 자리면 라벨도 여기 세우면 안 된다(주석은 그 함수에).
                    if not _leader_is_drawable(anchor, (x, y), angle.label, fs,
                                               self.style.halo_width):
                        continue
                    scored.append((
                        # 치수가 달린 팔을 피하는 것이 먼저, 그다음이 «가까이».
                        (1 if arm_taken[arm_rank] else 0,
                         far_rank, turn_rank, arm_rank),
                        (distance, (x, y), box, anchor),
                    ))
        if scored:
            best_out = min(scored, key=lambda item: item[0])[1]
        if best_out is None:
            # 밖에서도 못 비켰다 — 옛 동작(가장 덜 나쁜 자리)으로 물러선다.
            # 지시선을 그으면 그 선이 또 잉크를 얹으므로 여기서는 긋지 않는다.
            return best[1], best[2], None
        return best_out[1], best_out[2], best_out[3]

    def _label_hits_geometry(self, box: Box) -> bool:
        """이 글자 상자가 **실선·꼭짓점을 밟는가.**

        각 표시(호·직각 사각형)는 안 센다 — 각 라벨은 제 호의 설명이라 호 곁에
        앉는 것이 정상이다. 먼저 놓인 라벨(`occupied`)도 여기서 안 센다(그건
        부르는 쪽이 따로 본다). **오직 잉크로 그려진 도형만** 본다.
        """
        for point in self.points.values():
            if _point_in_box(point.x, point.y, box, 1.5):
                return True
        for segment in self.segments.values():
            if _segment_intersects_box(
                    self.points[segment.p1], self.points[segment.p2], box):
                return True
            # 같음 표시·평행 표시도 잉크다 — `_candidate_cost` 와 **같은 것**을 본다.
            for (mx1, my1), (mx2, my2) in self._segment_mark_lines(segment):
                if _segment_intersects_box(
                        Point(name="", x=mx1, y=my1),
                        Point(name="", x=mx2, y=my2), box):
                    return True
        for arc_name in sorted(self.arcs):
            if _polyline_intersects_box(
                    self._arc_stroke_samples(self.arcs[arc_name]), box):
                return True
        # 🔴 **원을 빠뜨리면 안 된다.** 첫 판이 그랬고, 밖으로 끌어낸 라벨이
        #    하필 **원 둘레 위에** 앉았다(실측 `m3-chord-cross`·`m3-inscribed-iso`
        #    ·`m3-semicircle` — 셋 다). 판정기(브라우저)도 같은 자리에서 눈이 멀어
        #    「깨끗」이라 했다. 세는 쪽과 고치는 쪽이 **같이** 눈이 먼 그 자리다.
        for circle_name in sorted(self.circles):
            circle_obj = self.circles[circle_name]
            if not circle_obj.draw:
                continue  # 작도용 원은 잉크를 안 남긴다.
            center = self.points[circle_obj.center]
            if _circle_intersects_box(center.x, center.y, circle_obj.radius, box):
                return True
        return False

    def _outward_vector(self, point: Point) -> tuple[float, float] | None:
        """이 꼭짓점의 **바깥** — 붙은 변들의 반대 방향(외각 이등분선).

        ## 왜 필요한가

        종전에는 꼭짓점 라벨의 방향 후보가 «N, NE, E, SE, S, SW, W, NW» **고정
        순서**였고, 비용은 잉크를 밟을 때만 올랐다. 도형 **안쪽은 대개 비어
        있으므로** 아래쪽 꼭짓점의 라벨은 잉크를 안 밟는 `N`(rank 0)을 그대로
        집었다 — 즉 **안으로 들어갔다.**

        가장 단순한 삼각형에서도 그랬다(실측 2026-08-28): 위 꼭짓점 `A` 는 5.2°
        로 바깥인데 `B` 121.7° · `C` 116.6° 로 **셋 중 둘이 안쪽**이었다.
        원장님이 짚으신 구각형의 `D`·`E`, 오각형의 `C`·`D`, 사각형의 `B` 가 전부
        이 자리다.

        ## 바깥을 어떻게 정하나 — 정본에서 뽑았다

        RPM 지면을 벡터로 훑어 라벨 위치를 실측했다
        (`scripts/qa/measure-rpm-label-placement.py`). **덩어리 중심의 반대쪽**
        으로 재면 28.3% 가 «안쪽»으로 나온다 — 교재가 그럴 리 없고, 그 축이
        오목한 도형·겹친 그림에서 바깥을 못 가리는 것이다.

        바깥은 **국소적**이다. 꼭짓점 `V` 에 변 `V→N1 … V→Nk` 가 붙어 있으면
        `−normalize(Σ normalize(Ni − V))` 가 외각 이등분선이고, 그 자로 다시 재니
        RPM 은 **안쪽이 6.7%** 였다(그 6.7% 도 대부분 각 크기를 적는 `x`·`y` 라
        도형 안쪽이 제자리다).

        ⚠️ **합이 0에 가까우면 바깥이 없다.** 선분 위의 점(양쪽으로 뻗는다)·
           두 현의 교점이 그렇다. 그때는 억지로 정하지 않고 `None` 을 돌려
           옛 순서로 물러선다 — 못 가르는 것을 가른 척하면 **틀린 자리를
           «근거 있는 자리»로 만든다.**
        """
        sx = sy = 0.0
        incident = 0
        for segment in self.segments.values():
            if segment.p1 == point.name:
                other = self.points[segment.p2]
            elif segment.p2 == point.name:
                other = self.points[segment.p1]
            else:
                continue
            length = math.hypot(other.x - point.x, other.y - point.y)
            if length > _EPS:
                sx += (other.x - point.x) / length
                sy += (other.y - point.y) / length
                incident += 1
        if incident == 0:
            return None
        length = math.hypot(sx, sy)
        if length < _OUTWARD_MIN:
            return None
        return (-sx / length, -sy / length)

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
            outward = self._outward_vector(point)
            if outward is not None:
                # 🔴 **여덟 방향 그대로 두고 «순서»만 바깥 기준으로 다시 매긴다.**
                #    새 각도를 만들면 이미 옳던 라벨까지 조금씩 움직여 지면 전체가
                #    흔들린다. 자리 집합은 그대로 두고 순서만 바꾸면, 바깥을 이미
                #    보던 라벨은 **같은 칸**을 그대로 집는다(실측: 안 움직였다).
                # 세로 성분을 눌러 **수평 쪽으로 당긴다**(`_LABEL_PULL` 주석 참조).
                target = math.atan2(_LABEL_PULL * outward[1], outward[0])

                def _turn(vector: tuple[float, float]) -> float:
                    delta = math.atan2(vector[1], vector[0]) - target
                    return abs(math.atan2(math.sin(delta), math.cos(delta)))

                ordered = sorted(base, key=_turn)
            elif point.kind == "intersection":
                # Intersections look most natural below-left unless occupied.
                ordered = [compass[key] for key in
                           ("SW", "SE", "NW", "NE", "S", "N", "W", "E")]
            else:
                # 바깥을 못 정하는 raw 점 — 옛 순서(북쪽 먼저)로 물러선다.
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
                        rank: int, distance_rank: int = 0,
                        curves: Sequence[Sequence[Point]] = (),
                        own_angle: str | None = None) -> tuple[int, float]:
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
            # 🔴 **같음 표시(tick)·평행 표시(»)도 잉크다.**
            #
            # 여기 없던 동안 라벨은 그것을 **못 봤고**, `2-2|삼각형의 성질|06` 의
            # `64°` 가 $\overline{CA}$ 의 이중 tick 을 통째로 덮었다(실측: 글자 상자
            # x 63.8~83.8, tick x 83.08~91.08 — 겹친다). 지면에서는 «표시가 없는
            # 변»으로 읽히므로 **문항이 달라진다** — RHS 합동의 근거가 사라진다.
            # 원장님과 RPM 원본을 1:1 로 견주다 드러났다(2026-08-28).
            for (mx1, my1), (mx2, my2) in self._segment_mark_lines(segment):
                if _segment_intersects_box(
                        Point(name="", x=mx1, y=my1), Point(name="", x=mx2, y=my2), box):
                    hard += 1
                    cost += 20.0
                    break
        for arc_name in sorted(self.arcs):
            if _polyline_intersects_box(
                    self._arc_stroke_samples(self.arcs[arc_name]), box):
                hard += 1
                cost += 20.0
        # 각 표시(호·직각 사각형)도 잉크다. 여기 없던 동안 라벨은 그것을 **못 봤고**
        # 직각기호 위에 `H` 가 그대로 앉았다 (원장님 지적 2026-08-25).
        #
        # ⚠️ **자기 각의 표시는 뺀다.** 각 라벨은 그 호의 «설명»이라 호 바로 바깥에
        #    앉는 것이 정상이다. 안 빼면 라벨이 제 호를 피하려고 꼭짓점에서 멀어지고,
        #    그러면 어느 각의 값인지 알 수 없게 된다 (실측: `x` 가 25 → 62.8 로 밀렸다).
        for angle_name in sorted(self.angles):
            if angle_name == own_angle:
                continue
            for polyline in self._angle_mark_polylines(self.angles[angle_name]):
                if _polyline_intersects_box(polyline, box):
                    hard += 1
                    cost += 20.0
        # 치수 점선도 잉크다 — 치수를 먼저 놓고 점 이름을 나중에 놓기 때문에
        # (자유도가 적은 것부터) 점 이름이 그 곡선을 피할 수 있어야 한다.
        for samples in curves:
            if _polyline_intersects_box(samples, box):
                hard += 1
                cost += 20.0
        cx, cy = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0
        half_diag = math.hypot(box[2] - box[0], box[3] - box[1]) / 2.0
        for circle_name in sorted(self.circles):
            circle_obj = self.circles[circle_name]
            if not circle_obj.draw:
                # Construction circles leave no ink — nothing to collide with.
                continue
            center = self.points[circle_obj.center]
            if abs(math.hypot(cx - center.x, cy - center.y) - circle_obj.radius) < half_diag + 0.75:
                hard += 1
                cost += 15.0
        return hard, cost

    def _shape_hull(self) -> tuple[tuple[float, float], ...]:
        """**그려지는 잉크**의 볼록 껍질 — 「도형 몸통」의 대용.

        🔴 보조점(`self.points`)이 아니라 **잉크**로 만든다. 교점·수선의 발처럼
           그리지 않는 점까지 넣으면 껍질이 도형보다 커져, 실제로는 바깥인
           치수가 「안쪽」으로 찍힌다 — 벌점이 거꾸로 걸린다.

        오목한 도형(접은 종이 등)에서는 껍질이 실제 도형보다 넓다. 그래도
        「껍질 안」은 「도형 바로 곁」이라 벌점을 줄 자리는 맞다. 여기서 재는
        것은 **금지**가 아니라 **선호**이므로, 바깥이 다 막히면 안쪽이 이긴다.
        """

        cached = getattr(self, "_shape_hull_cache", None)
        if cached is not None:
            return cached
        ink: list[tuple[float, float]] = []
        for segment in self.segments.values():
            for ref in (segment.p1, segment.p2):
                point = self.points[ref]
                ink.append((point.x, point.y))
        for arc in self.arcs.values():
            try:
                ink.extend((s.x, s.y) for s in self._arc_stroke_samples(arc))
            except GeometryValidationError:
                continue
        for circle_obj in self.circles.values():
            if not circle_obj.draw:
                continue
            center = self.points[circle_obj.center]
            for step in range(16):
                theta = step * math.tau / 16.0
                ink.append((center.x + circle_obj.radius * math.cos(theta),
                            center.y + circle_obj.radius * math.sin(theta)))
        hull = _convex_hull(ink)
        self._shape_hull_cache = hull
        return hull

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
                max(_DIMENSION_MIN_FONT, 0.82 * available / width_units),
            )
            # 도형 **안**을 지나는 짧은 변(수선 등)은 옆으로 난 통로가 좁아, 값이
            # 커서 안 들어가는 일이 있다. 그때는 곡선을 도형에서 멀리 밀어내는
            # 것보다 값을 **조금 줄이는** 편이 낫다 — 다만 아래 하한 밑으로는 안
            # 줄인다(지면에서 본문보다 작아지면 그건 결함이다, 09 §4-25).
            fonts = [font_size]
            smaller = max(_DIMENSION_MIN_FONT, 0.85 * font_size)
            if smaller < font_size - 0.05:
                fonts.append(smaller)
        else:
            font_size = dimension.font_size
            fonts = [font_size]
        base_offset = (self.style.dimension_offset if dimension.offset is None
                       else dimension.offset)
        # 벌어짐 사다리는 **기본 글꼴**로 한 번만 만든다 — 글꼴 후보마다 다르게
        # 만들면 `offset_rank` 가 후보끼리 다른 것을 가리켜 비교가 안 된다.
        offset_step = max(4.0, 0.55 * font_size)
        offsets = [base_offset + index * offset_step for index in range(6)]
        sides = ([dimension.side] if dimension.side != "auto"
                 else ["left", "right"])

        candidates: list[tuple[tuple[int, int, int, int, int, int,
                                          float, float, float, int, int, int, int],
                               DimensionLayout]] = []
        for font_rank, font_size in enumerate(fonts):
            for offset_rank, offset in enumerate(offsets):
                for side_rank, side in enumerate(sides):
                    sign = 1.0 if side == "left" else -1.0
                    # 🔴 **치수는 도형 «밖» 으로 나가야 한다.**
                    #
                    # 원장님이 지면에서 찾으셨다(2026-08-30): 등변사다리꼴의 `9 cm`
                    # 가 도형 **안쪽**으로 크게 휘어 들어와 있었다.
                    #
                    # 뿌리는 「안쪽인가」를 세는 축이 **아예 없었다**는 것이다.
                    # 대리로 쓰던 `side_crowding` 은 창이 `along ∈ [-15%, 115%]` 라
                    # 눈이 먼다 — 사다리꼴은 아랫변이 윗변보다 길어 B·C 가 **둘 다
                    # 창 밖**으로 나가고 붐빔이 0이 된다. 그러면 두 쪽 점수가
                    # **완전히 같아져** `side_rank` 가 갈랐고, 목록이
                    # `["left","right"]` 라 **늘 left** 였다 — 동전 던지기였다.
                    #
                    # ⚠️ **곡선이 아니라 «쪽» 을 본다.** 처음에는 곡선 샘플 중 안쪽인
                    #    것을 셌는데, 그러면 벌어짐이 클수록 점수가 좋아져 치수가
                    #    도형에서 **더 멀리 밀려났다** — 원장님이 같은 날 지적하신
                    #    「크게 휜 치수선」을 되레 키운다. 쪽만 보면 안쪽밖에 없는
                    #    도형(평행선 사이 · 접힌 종이)에서는 두 쪽이 **동점**이 되어
                    #    `offset_rank` 가 갈라 **가장 얕은** 벌어짐이 이긴다.
                    #
                    # 「금지」가 아니라 「벌점」이다 — 여섯째 항이라 충돌 여섯 가지가
                    # 먼저다. 바깥이 다 막힌 자리에서는 안쪽이 그대로 이긴다.
                    inside_probe_x = midpoint_x + nx * sign * 2.0
                    inside_probe_y = midpoint_y + ny * sign * 2.0
                    inside_shape = (
                        1 if _hull_depth(self._shape_hull(),
                                         inside_probe_x, inside_probe_y) > 0.0
                        else 0
                    )
                    control = Point(
                        f"{dimension.name}:control",
                        midpoint_x + nx * sign * 2.0 * offset,
                        midpoint_y + ny * sign * 2.0 * offset,
                    )
                    samples = _quadratic_samples(dimension.name, start, control, end)

                    def anchor_at(t: float) -> tuple[tuple[float, float], Box]:
                        index = min(len(samples) - 1,
                                    max(0, round(t * (len(samples) - 1))))
                        on_curve = samples[index]
                        position = (on_curve.x, on_curve.y + 0.32 * font_size)
                        return position, _expand_box(
                            _text_box(*position, dimension.label, font_size, self.label_metrics),
                            self.style.dimension_halo_width / 2.0 + 0.5,
                        )

                    apex = samples[len(samples) // 2]
                    label_position, label_box = anchor_at(0.5)
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
                                _text_box(*moved, dimension.label, font_size, self.label_metrics),
                                self.style.dimension_halo_width / 2.0 + 0.5,
                            )
                            label_position, label_box = moved, moved_box
                            if not _polyline_intersects_box(samples, moved_box):
                                break
                        anchors = [(0.5, label_position, label_box)]
                    else:
                        # 🔴 **값은 제 곡선 위 아무 데나 앉을 수 있다.** 가운데가 첫째지만,
                        #    좁은 자리(도형 «안»을 지나는 수선 등)에서는 가운데가 두 변
                        #    사이에 안 들어간다 — 그때 옆으로 미끄러지면 들어간다.
                        #    종전에는 가운데 하나뿐이라 그런 치수를 **통째로 던졌고**,
                        #    부르는 쪽은 치수를 포기하고 날 `<text>` 를 얹었다.
                        #    틈은 `label_t` 를 따라가므로 값 밑에 정확히 난다.
                        anchors = [(0.5, label_position, label_box)]
                        for slide in (0.35, 0.65, 0.25, 0.75):
                            anchors.append((slide, *anchor_at(slide)))
                    for anchor_rank, (label_t, label_position, label_box) in enumerate(anchors):
                        layout = DimensionLayout(
                            dimension.name, side, start, control, end,
                            label_position, label_box, samples, font_size, label_t,
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
                            a, b = self.points[segment.p1], self.points[segment.p2]
                            chord_scale = math.hypot(b.x - a.x, b.y - a.y)
                            # 🔴 **부동소수 오차가 아니라 «좌표 반올림»을 견뎌야 한다.**
                            #
                            # 종전 문턱은 `chord_scale * 1e-7` (175px 짜리 변에서
                            # 0.0000175px) 이었다. 그런데 스펙의 점 좌표는 소수 둘째
                            # 자리로 **반올림돼 들어온다** — 「AB 를 1:3 으로 나누는
                            # 점 D」는 실제로 AB 에서 0.0013px 어긋나 있고, 그건 옛
                            # 문턱의 **75배**다. 그래서 「D 와 B 는 둘 다 AB 위」라는
                            # 사실이 성립하지 않아, 바깥으로 나가는 치수 곡선이
                            # **제 현과 교차한다**고 세어졌다. 바깥이 통째로 막히니
                            # 치수가 도형 **안쪽**으로 가거나(원장님 지적 2026-08-30)
                            # 아예 **떨어져 나갔다**(실측 33자리 중 12자리가 이것).
                            #
                            # 문턱은 손으로 고르지 않고 **분포에서** 골랐다
                            # (`.tmp-orca/chordgap.ts`, 등록 v2 치수 496자리):
                            #   ㉠ 「반올림으로 어긋난 것」 91건 — 최대 **0.0045px**
                            #   ㉡ 「정말 선분 옆인 것」 55건 — 최소 **3.39px**
                            # 사이 [0.0045, 3.39] 는 **비어 있다.** 0.25 는 ㉠ 최대의
                            # 55배이고 ㉡ 최소의 1/13.5 라 두 무리 어디에도 안 닿는다.
                            # 지면으로는 0.05mm — 도형 선(1.9px)의 1/8 이다.
                            chord_tolerance = max(0.25, chord_scale * 1.0e-7)
                            own_chord = {segment.p1, segment.p2} == endpoint_pair or (
                                # 긴 변의 **일부**를 재는 치수(반지름 4 cm 가 지름 선분
                                # 위에 있는 부채꼴 고리 등): 두 끝점이 같은 선분 위에
                                # 있으면 곡선은 그 선분과 끝점에서만 닿는다 — 교차가
                                # 아니라 자기 현이다.  이 배치는 종전에는 모든 오프셋
                                # 후보가 «교차»로 죽어 아예 그릴 수 없었다.
                                _distance_point_line(first, a, b) <= chord_tolerance
                                and _distance_point_line(second, a, b) <= chord_tolerance
                                and _point_within_segment(first, a, b, chord_tolerance)
                                and _point_within_segment(second, a, b, chord_tolerance)
                            )
                            if own_chord:
                                # A one-sided quadratic meets its measured chord only
                                # at the deliberately inset start/end points.  The
                                # value label itself still needs genuine clearance.
                                label_clearance = _expand_box(
                                    label_box,
                                    self.style.segment_width / 2.0 + 0.5,
                                )
                                if _segment_intersects_box(a, b, label_clearance):
                                    geometry_crossings += 1
                                continue
                            if (_polyline_intersects_segment(samples, a, b)
                                    or _segment_intersects_box(a, b, label_box)):
                                geometry_crossings += 1
                            else:
                                clearance = min(
                                    _distance_xy_to_segment(sample.x, sample.y, a, b)
                                    for sample in samples)
                                if clearance < 3.0:
                                    near_geometry += 1

                        # 🔴 **각 표시(호·직각 사각형)도 잉크다.**
                        #
                        # 여기 없던 동안 치수는 그것을 **못 봤다** — 목록에 없으니
                        # 구조적으로 0이다. 원장님이 지면에서 찾으셨다(2026-08-30,
                        # `2-2|삼각형의 성질|12`): 「치수선과 각도가 매우 겹치기
                        # 때문에…」. 겹친 것은 곡선끼리가 아니라 **값 글자와 각 호**
                        # 다 — 실측 `6 cm` 상자와 60° 호 사이 **8.25px**(곡선끼리는
                        # 10.08px 라 그것만 보면 「안 겹친다」로 읽힌다). 그래서
                        # 여기서 `label_box` 도 함께 본다. 고친 뒤 56.36px.
                        # 라벨 배치는 이미 `_angle_mark_polylines` 로 이것을 보고
                        # 있었다 — 치수만 두 벌 중 한쪽에서 빠져 있었다.
                        for angle_name in sorted(self.angles):
                            for polyline in self._angle_mark_polylines(
                                    self.angles[angle_name]):
                                if (_polylines_intersect(samples, polyline)
                                        or _polyline_intersects_box(
                                            polyline, _expand_box(label_box, 1.0))):
                                    geometry_crossings += 1
                                    break

                        for arc_name in sorted(self.arcs):
                            arc_samples = self._arc_stroke_samples(self.arcs[arc_name])
                            if (_polylines_intersect(samples, arc_samples)
                                    or _polyline_intersects_box(arc_samples,
                                                                _expand_box(label_box, 1.0))):
                                geometry_crossings += 1
                            else:
                                clearance = min(
                                    _distance_xy_to_segment(sample.x, sample.y, a, b)
                                    for sample in samples
                                    for a, b in zip(arc_samples, arc_samples[1:]))
                                if clearance < 3.0:
                                    near_geometry += 1

                        circle_crossings = 0
                        for circle_obj in self.circles.values():
                            if not circle_obj.draw:
                                # No ink on construction circles; dimension curves may
                                # cross their circumference freely.
                                continue
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
                            # 「도형 안을 지나나」가 「그 쪽이 붐비나」보다 앞이다 —
                            # 지면에서 훨씬 나쁘고, 붐빔은 그것의 흐린 대용이었다.
                            float(inside_shape), float(side_crowding), float(near_geometry),
                            # 곡선을 변에 **가깝게** 두는 것이 먼저고, 그다음이
                            # 「값은 가운데」다 — 값을 옮겨서 될 일을 오프셋으로 풀면
                            # 치수선이 도형에서 멀어져 무엇을 잰 것인지 흐려진다.
                            font_rank, offset_rank, anchor_rank, side_rank,
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
        # 각 이름 → (호 위 시작점, 라벨 자리). 라벨을 도형 밖으로 끌어낸 각만 들어간다.
        angle_leaders: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {}

        # 🔴 **자리를 잡는 순서는 «자유도가 적은 것부터»다.**
        #
        #   각 라벨(이등분선 위 — 방향이 하나) → 치수(제 현을 붙들어야 한다,
        #   쪽 2 × 벌어짐 6) → 점 이름(8방향 × 5거리 = 40).
        #
        # 종전에는 점 이름이 **둘째**였다. 점 이름은 늘 「그 꼭짓점 바로 바깥」을
        # 집는데, 그 자리가 곧 치수 곡선이 지나갈 자리다. 그래서 삼각형에 치수를
        # 둘 달면 `dimension … has no collision-free layout` 으로 **거의 늘 던졌고**,
        # 그 때문에 `m3Trig.ts` 는 치수를 통째로 포기하고 날 `<text>` 를 얹고 있었다
        # (그 파일의 `build()` 주석이 실측 19/60 실패를 적어 두었다).
        # 원장님 지적 2026-08-25 「길이를 표현하는 치수선이 렌더링 안 된다」의 뿌리다.
        #
        # 자유도가 큰 쪽을 나중에 놓으면 둘 다 자리를 얻는다.
        for angle_name in sorted(self.angles):
            angle = self.angles[angle_name]
            laid_out = self._angle_label_layout(angle, occupied)
            if laid_out:
                pos, box, leader = laid_out
                key = f"angle:{angle.name}"
                label_positions[key], label_boxes[key] = pos, box
                occupied.append(box)
                # 밖으로 끌어낸 라벨은 **지시선이 임자를 말한다** — 그 선을 그리려면
                # 호 위의 시작점을 여기서 챙겨 둬야 한다(각 순서가 자리를 정한다).
                if leader is not None:
                    angle_leaders[angle.name] = (leader, pos)

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

        dimension_curves = [layout.path_samples
                            for layout in dimension_layouts.values()]

        for point_name in sorted(self.labels):
            label = self.labels[point_name]
            point = self.points[label.point]
            fs = self.style.font_size if label.font_size is None else label.font_size
            if label.dx is not None or label.dy is not None:
                dx = 0.0 if label.dx is None else label.dx
                dy = 0.0 if label.dy is None else label.dy
                x, y = point.x + dx, point.y + dy + 0.32 * fs
                box = _text_box(x, y, label.text, fs, self.label_metrics)
                candidates = [((x, y), box,
                               self._candidate_cost(label.point, box, occupied, 0, 0,
                                                    dimension_curves))]
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
                        box = _text_box(x, y, label.text, fs, self.label_metrics)
                        candidates.append((
                            (x, y), box,
                            self._candidate_cost(
                                label.point, box, occupied, rank, distance_rank,
                                dimension_curves)))
            pos, box, cost = min(candidates, key=lambda item: item[2])
            if cost[0]:
                raise GeometryValidationError(
                    f"label {label.point!r} has no line/circle/label-free position")
            label_positions[label.point], label_boxes[label.point] = pos, box
            occupied.append(box)

        bounds: list[Box] = []
        stroke_pad = max(self.style.circle_width, self.style.segment_width,
                         self.style.mark_width) / 2.0
        for circle_obj in self.circles.values():
            if not circle_obj.draw:
                # No ink — a construction circle must not inflate the canvas.
                continue
            center = self.points[circle_obj.center]
            r = circle_obj.radius + stroke_pad
            bounds.append((center.x - r, center.y - r, center.x + r, center.y + r))
        for segment_name in sorted(self.segments):
            segment = self.segments[segment_name]
            a, b = self.points[segment.p1], self.points[segment.p2]
            bounds.append((min(a.x, b.x) - stroke_pad, min(a.y, b.y) - stroke_pad,
                           max(a.x, b.x) + stroke_pad, max(a.y, b.y) + stroke_pad))
            # tick/» 마크는 선분 밖(수직 방향)으로도 잉크가 나간다 — 렌더와
            # 같은 좌표를 경계에 넣는다.
            for (x1, y1), (x2, y2) in self._segment_mark_lines(segment):
                bounds.append((min(x1, x2) - stroke_pad, min(y1, y2) - stroke_pad,
                               max(x1, x2) + stroke_pad, max(y1, y2) + stroke_pad))
        for arc_name in sorted(self.arcs):
            arc = self.arcs[arc_name]
            center, radius, start_deg, signed = self._arc_geometry(
                arc.circle, arc.p1, arc.p2, arc.direction, f"arc {arc.name!r}")
            bounds.append(_expand_box(
                _arc_bbox(center, radius, start_deg, signed), stroke_pad))
        for region_name in sorted(self.regions):
            # A fill is visible ink even where no stroke follows the boundary —
            # the bulge of an arc piece must stay inside the canvas.
            for index, piece in enumerate(self.regions[region_name].boundary):
                if piece.kind != "arc":
                    continue
                center, radius, start_deg, signed = self._arc_geometry(
                    piece.circle, piece.start, piece.end, piece.direction,
                    f"region {region_name!r} boundary[{index}]")
                bounds.append(_arc_bbox(center, radius, start_deg, signed))
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
            (0.0, 0.0, width, height), translation, content,
            MappingProxyType(angle_leaders))

    def render_svg(self) -> str:
        """Render a standalone SVG with deterministic main/marks/labels layers."""

        resolved = self.resolve()
        _, _, width, height = resolved.view_box
        style = self.style
        fills: list[str] = []
        main: list[str] = []
        marks: list[str] = []
        labels: list[str] = []
        tx, ty = resolved.translation

        def arc_fragment(circle_name: str, start_name: str, end_name: str,
                         direction: str, what: str) -> str:
            """SVG ``A`` command for one validated arc, ending exactly on the
            named end point so chained region pieces stay byte-continuous."""

            _, radius, _, signed = self._arc_geometry(
                circle_name, start_name, end_name, direction, what)
            end = self.points[end_name]
            large = 1 if abs(signed) > 180.0 else 0
            sweep_flag = 0 if signed > 0 else 1
            return (f'A {_fmt(radius)} {_fmt(radius)} 0 {large} {sweep_flag} '
                    f'{_fmt(end.x + tx)} {_fmt(end.y + ty)}')

        # 영역 채색은 모든 잉크(선·호·마크·라벨)보다 **아래**에 깔린다 —
        # 채색이 라벨·치수를 가리면 안 된다.  순서는 스펙에 적힌 순서다
        # (흰 채움으로 앞 영역을 도려내는 지면이 있다).
        for region in self.regions.values():
            first = region.boundary[0]
            start_point = self.points[first.start]
            parts = [f'M {_fmt(start_point.x + tx)} {_fmt(start_point.y + ty)}']
            for index, piece in enumerate(region.boundary):
                end_point = self.points[piece.end]
                if piece.kind == "seg":
                    parts.append(
                        f'L {_fmt(end_point.x + tx)} {_fmt(end_point.y + ty)}')
                else:
                    parts.append(arc_fragment(
                        piece.circle, piece.start, piece.end, piece.direction,
                        f"region {region.name!r} boundary[{index}]"))
            parts.append("Z")
            fills.append(
                f'<path d="{" ".join(parts)}" '
                f'fill="{escape(region.fill, quote=True)}" stroke="none" '
                f'data-region="{escape(region.name, quote=True)}"/>')

        for circle_obj in self.circles.values():
            if not circle_obj.draw:
                continue
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
        for arc_name in sorted(self.arcs):
            arc = self.arcs[arc_name]
            start_point = self.points[arc.p1]
            dash = (f' stroke-dasharray="{escape(arc.dash, quote=True)}"'
                    if arc.dash else "")
            main.append(
                f'<path d="M {_fmt(start_point.x + tx)} {_fmt(start_point.y + ty)} '
                f'{arc_fragment(arc.circle, arc.p1, arc.p2, arc.direction, f"arc {arc.name!r}")}" '
                f'fill="none" stroke="{escape(style.stroke, quote=True)}" '
                f'stroke-width="{_fmt(style.segment_width)}"{dash}/>')

        for segment_name in sorted(self.segments):
            segment = self.segments[segment_name]
            for (x1, y1), (x2, y2) in self._segment_mark_lines(segment):
                marks.append(
                    f'<line x1="{_fmt(x1 + tx)}" y1="{_fmt(y1 + ty)}" '
                    f'x2="{_fmt(x2 + tx)}" y2="{_fmt(y2 + ty)}" '
                    f'stroke="{escape(style.stroke, quote=True)}" '
                    f'stroke-width="{_fmt(style.mark_width)}" '
                    f'stroke-linecap="round"/>')
        for angle_name in sorted(self.angles):
            angle = self.angles[angle_name]
            vertex, p1, p2 = (self.points[angle.vertex], self.points[angle.p1],
                              self.points[angle.p2])
            radius = style.angle_radius if angle.radius is None else angle.radius
            if angle.right:
                # 직각기호 — 호 대신, 두 변 방향으로 놓인 작은 사각형의 두 변.
                # ⚠️ 좌표는 `_angle_mark_polylines` 가 정한다 — 충돌 판정과 **같은 값**을
                #    써야 한다(`_segment_mark_lines` 와 같은 무늬). 두 벌이 되면
                #    「비켰다」고 판정한 자리에 다른 것이 그려진다.
                square = self._angle_mark_polylines(angle)
                if not square:
                    continue
                corner_a, corner_b, corner_c = square[0]
                marks.append(
                    f'<path d="M {_fmt(corner_a.x + tx)} '
                    f'{_fmt(corner_a.y + ty)} '
                    f'L {_fmt(corner_b.x + tx)} '
                    f'{_fmt(corner_b.y + ty)} '
                    f'L {_fmt(corner_c.x + tx)} '
                    f'{_fmt(corner_c.y + ty)}" fill="none" '
                    f'stroke="{escape(style.stroke, quote=True)}" '
                    f'stroke-width="{_fmt(style.mark_width)}"/>')
                continue
            for arc_index in range(angle.arcs):
                path_data = angle_arc(
                    vertex.x + tx, vertex.y + ty,
                    (p1.x + tx, p1.y + ty), (p2.x + tx, p2.y + ty),
                    radius - arc_index * _MARK_GAP)
                marks.append(
                    f'<path d="{path_data}" fill="none" '
                    f'stroke="{escape(style.stroke, quote=True)}" '
                    f'stroke-width="{_fmt(style.mark_width)}"/>')
        # ── 밖으로 끌어낸 각 라벨의 **지시선** ────────────────────────────────
        #
        # 원장님 지시 2026-08-27: 「화살표로 각을 도형 밖으로 끌어내서 표현해.」
        # 좁은 각은 라벨이 안쪽에 못 들어간다(배율로 안 풀린다 — `_angle_label_layout`
        # 의 주석 참조). 그때 라벨은 밖에 서고, **어느 꼭짓점의 값인지는 이 선이 말한다.**
        #
        # ⚠️ 선을 글자 **밑까지** 긋지 않는다 — 글자 상자 앞에서 끊는다. 끝까지 그으면
        #    halo 가 그 선을 지워 «끊긴 선»으로 보인다(lint_svg 규칙 7 과 같은 자리).
        for angle_name in sorted(resolved.angle_leaders):
            (ax, ay), (lx, ly) = resolved.angle_leaders[angle_name]
            label_text = self.angles[angle_name].label
            dx, dy = lx - ax, ly - 0.32 * style.angle_font_size - ay
            length = math.hypot(dx, dy)
            # 고르는 쪽(`_angle_label_layout`)이 이미 같은 함수로 걸렀다. 여기서 또
            # 보는 것은 **두 벌이 갈라지지 않게** 하기 위해서다 — 규칙은 그 함수 하나다.
            if not _leader_is_drawable((ax, ay), (lx, ly), label_text,
                                       style.angle_font_size, style.halo_width):
                continue
            ux, uy = dx / length, dy / length
            stop_r = _leader_stop_radius(
                label_text, style.angle_font_size, style.halo_width, ux, uy)
            ex = lx - ux * stop_r
            ey = ly - 0.32 * style.angle_font_size - uy * stop_r
            # 살짝 휘게 — 곧은 선은 도형의 변으로 읽힌다(원장님 스케치도 곡선이다).
            bow = 0.18 * (length - stop_r)
            cx = (ax + ex) / 2.0 - uy * bow
            cy = (ay + ey) / 2.0 + ux * bow
            marks.append(
                f'<path d="M {_fmt(ax + tx)} {_fmt(ay + ty)} '
                f'Q {_fmt(cx + tx)} {_fmt(cy + ty)} '
                f'{_fmt(ex + tx)} {_fmt(ey + ty)}" fill="none" '
                f'stroke="{escape(style.stroke, quote=True)}" '
                f'stroke-width="{_fmt(style.mark_width)}" stroke-linecap="round"/>')
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
                f'stroke-width="{_fmt(style.halo_width)}" stroke-linejoin="round" '
                f'{mj_attr(angle.label)}>'
                f'{label_pieces_svg(angle.label, style.angle_font_size, style.font_family_italic)}</text>')
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
                f'stroke-linejoin="round" '
                f'{mj_attr(dimension.label)}>'
                f'{label_pieces_svg(dimension.label, fs, style.font_family_italic)}</text>')
        for point_name in sorted(self.labels):
            label = self.labels[point_name]
            x, y = resolved.label_positions[point_name]
            fs = style.font_size if label.font_size is None else label.font_size
            italic = ' font-style="italic"' if label.italic else ""
            # 🔴 **임자 꼭짓점을 적는다.** 안 적으면 판정기가 「가장 가까운 끝점」으로
            #    임자를 **추측**하는데, 라벨이 두 꼭짓점 사이에 앉으면 엉뚱한 쪽을
            #    집는다 — 실측 2026-08-28: 사각형 안 삼각형에서 `A` 의 이름표가
            #    제 꼭짓점(25.3)보다 `F`(24.7)에 가까워, 멀쩡한 자리를 **178° 안쪽**
            #    으로 판정했다. 하마터면 맞는 자리를 고치러 갈 뻔했다.
            owner = self.points[label.point]
            labels.append(
                f'<text x="{_fmt(x + tx)}" y="{_fmt(y + ty)}" '
                f'font-family="{font_family}" font-size="{_fmt(fs)}"{italic} '
                f'text-anchor="middle" fill="{escape(style.text_color, quote=True)}" '
                f'data-px="{_fmt(owner.x + tx)}" data-py="{_fmt(owner.y + ty)}" '
                f'{mj_attr(label.text)}>'
                f'{label_pieces_svg(label.text, fs, style.font_family_italic)}</text>')

        background = (f'\n  <rect width="{_fmt(width)}" height="{_fmt(height)}" fill="#ffffff"/>'
                      if self.background == "white" else "")
        # 영역이 없으면 그룹도 없다 — 기존 지면의 SVG 가 한 바이트도 안 변한다.
        fills_group = (f'  <g>\n    ' + "\n    ".join(fills) + '\n  </g>\n'
                       if fills else "")
        main_body = "\n    ".join(main)
        marks_body = "\n    ".join(marks)
        labels_body = "\n    ".join(labels)
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {_fmt(width)} {_fmt(height)}">{background}\n'
            f'{fills_group}'
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

    Mark grammar (합동·평행·직각 표기)::

        "segments": {
          "AB": ["A", "B"],                              // 기존 배열형 그대로
          "AC": {"points": ["A", "C"], "ticks": 2},      // 같음 표시 1~3
          "l1": {"points": ["P", "Q"], "parallel": 1}    // 평행 » 1~2 (p1→p2 방향)
        },
        "angles": {
          "a": {"vertex": "C", "points": ["A", "D"], "arcs": 2},   // 이중 호
          "r": {"vertex": "T", "points": ["O", "P"], "right": true} // 직각기호
        }

    ``right: true`` replaces the arc with the small square (호와 함께 못 쓴다)
    and doubles as a check — the rays must actually be perpendicular.
          "dimensions": {"AC_len": {"points": ["A", "C"],
                                       "label": "12 cm", "side": "auto"}},
          "labels": {"A": "A", "B": "B"}
        }

    Shaded-region figures add ``arcs`` (stroked arc pieces), ``regions``
    (light fills bounded by a closed seg/arc chain), and construction circles
    with ``draw: false``::

        {
          "circles": {"c": {"center": "O", "radius": 60, "draw": false}},
          "arcs": {"arcAB": {"circle": "c", "from": "A", "to": "B",
                             "dir": "ccw"}},
          "regions": {"shade": {"boundary": [
              {"seg": ["O", "A"]},
              {"arc": {"circle": "c", "from": "A", "to": "B", "dir": "ccw"}},
              {"seg": ["B", "O"]}],
            "fill": "#f2d5c8"}}
        }

    Region boundaries must connect end-to-start by point name and close; a
    broken chain raises.  Fills must be light (:data:`REGION_MIN_LUMINANCE`).
    Unknown fields and references are errors; no placeholder geometry is made.
    """

    if isinstance(spec, FigureSpec):
        spec = spec.data
    if not isinstance(spec, Mapping):
        raise FigureSpecError("FigureSpec must be a mapping")
    allowed_top = {"version", "theme", "canvas", "background", "style",
                   "points", "circles", "segments", "arcs", "regions",
                   "angles", "dimensions", "labels", "label_metrics"}
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

    # TS 가 MathJax 로 잰 라벨 치수 — 배치는 **이 값만** 쓴다(없으면 어림).
    raw_metrics = spec.get("label_metrics")
    if raw_metrics is not None:
        if not isinstance(raw_metrics, Mapping):
            raise FigureSpecError("label_metrics must be a mapping")
        for key, value in raw_metrics.items():
            if (not isinstance(key, str) or not isinstance(value, Sequence)
                    or isinstance(value, (str, bytes)) or len(value) != 3):
                raise FigureSpecError(
                    "label_metrics values must be [width, ascent, descent]")
            try:
                scene.label_metrics[key] = (
                    float(value[0]), float(value[1]), float(value[2]))
            except (TypeError, ValueError) as exc:
                raise FigureSpecError("label_metrics must be numbers") from exc

    point_records = _named_records(spec.get("points"), "points")
    circle_records = _named_records(spec.get("circles"), "circles")
    segment_records = _named_records(spec.get("segments"), "segments")
    arc_records = _named_records(spec.get("arcs"), "arcs")
    region_records = _named_records(spec.get("regions"), "regions")
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
            _strict_keys(item, {"center", "radius", "draw"}, f"circles.{name}")
            if "center" not in item or "radius" not in item:
                raise FigureSpecError(f"circles.{name} requires center and radius")
            draw = item.get("draw", True)
            if not isinstance(draw, bool):
                raise FigureSpecError(f"circles.{name}.draw must be boolean")
            scene.add_circle(name, str(item["center"]),
                             _spec_number(item["radius"], f"circles.{name}.radius"),
                             draw=draw)

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
            _strict_keys(item, {"points", "p1", "p2", "dash", "dashed",
                                "ticks", "parallel"}, f"segments.{name}")
            if "points" in item:
                if "p1" in item or "p2" in item:
                    raise FigureSpecError(f"segments.{name}: use points or p1/p2, not both")
                p1, p2 = _pair(item["points"], f"segments.{name}.points")
            else:
                if "p1" not in item or "p2" not in item:
                    raise FigureSpecError(f"segments.{name} requires p1 and p2")
                p1, p2 = str(item["p1"]), str(item["p2"])
            dash = item.get("dash", item.get("dashed"))
            scene.add_segment(name, p1, p2, dashed=None if dash is None else str(dash),
                              ticks=item.get("ticks", 0),
                              parallel=item.get("parallel", 0))

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
                                "label_distance", "arcs", "right"}, f"angles.{name}")
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
            right_value = item.get("right", False)
            if not isinstance(right_value, bool):
                raise FigureSpecError(f"angles.{name}.right must be boolean")
            if right_value and "arcs" in item:
                raise FigureSpecError(
                    f"angles.{name}: right:true replaces the arc — do not give arcs")
            scene.add_angle(
                name, str(item["vertex"]), p1, p2,
                radius=None if item.get("radius") is None else _spec_number(
                    item["radius"], f"angles.{name}.radius"),
                label=item.get("label"),
                label_distance=None if item.get("label_distance") is None else _spec_number(
                    item["label_distance"], f"angles.{name}.label_distance"),
                arcs=item.get("arcs", 1),
                right=right_value)

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

        for name, item in arc_records:
            if not isinstance(item, Mapping):
                raise FigureSpecError(f"arcs.{name} must be an object")
            _strict_keys(item, {"circle", "from", "to", "dir", "dash"},
                         f"arcs.{name}")
            for required in ("circle", "from", "to"):
                if required not in item:
                    raise FigureSpecError(
                        f"arcs.{name} requires circle, from, and to")
            scene.add_arc(
                name, str(item["circle"]), str(item["from"]), str(item["to"]),
                direction=str(item.get("dir", "ccw")),
                dash=None if item.get("dash") is None else str(item["dash"]))

        for name, item in region_records:
            if not isinstance(item, Mapping):
                raise FigureSpecError(f"regions.{name} must be an object")
            _strict_keys(item, {"boundary", "fill"}, f"regions.{name}")
            if "boundary" not in item or "fill" not in item:
                raise FigureSpecError(f"regions.{name} requires boundary and fill")
            boundary_value = item["boundary"]
            if (not isinstance(boundary_value, Sequence)
                    or isinstance(boundary_value, (str, bytes))):
                raise FigureSpecError(f"regions.{name}.boundary must be a list")
            pieces: list[RegionPiece] = []
            for index, piece_value in enumerate(boundary_value):
                piece_path = f"regions.{name}.boundary[{index}]"
                if not isinstance(piece_value, Mapping):
                    raise FigureSpecError(f"{piece_path} must be an object")
                keys = set(piece_value)
                if keys == {"seg"}:
                    p1, p2 = _pair(piece_value["seg"], f"{piece_path}.seg")
                    pieces.append(RegionPiece("seg", p1, p2))
                elif keys == {"arc"}:
                    arc_value = piece_value["arc"]
                    if not isinstance(arc_value, Mapping):
                        raise FigureSpecError(f"{piece_path}.arc must be an object")
                    _strict_keys(arc_value, {"circle", "from", "to", "dir"},
                                 f"{piece_path}.arc")
                    for required in ("circle", "from", "to"):
                        if required not in arc_value:
                            raise FigureSpecError(
                                f"{piece_path}.arc requires circle, from, and to")
                    pieces.append(RegionPiece(
                        "arc", str(arc_value["from"]), str(arc_value["to"]),
                        str(arc_value["circle"]),
                        str(arc_value.get("dir", "ccw")).strip().lower()))
                else:
                    raise FigureSpecError(
                        f"{piece_path} must have exactly one of 'seg' or 'arc'")
            if not isinstance(item["fill"], str):
                raise FigureSpecError(f"regions.{name}.fill must be text")
            scene.add_region(name, pieces, item["fill"])

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
    "AngleMark", "ArcStroke", "Canvas", "Circle", "DimensionLayout",
    "DimensionMark", "FigureScene", "FigureSpec",
    "FigureSpecError", "GeometryValidationError", "Point", "PointLabel",
    "Region", "RegionPiece", "REGION_MIN_LUMINANCE",
    "ResolvedScene", "Segment", "StyleProfile", "compile_figure_spec",
    "intersecting_chords_template", "render_figure_spec",
]
