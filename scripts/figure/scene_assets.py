# -*- coding: utf-8 -*-
"""FigureSpec(v2·graph-1)에 실물 그림 조각(assets/*.svg)을 얹는다 — math-figure-editor 2026-10-21.

건물·집·등대가 그려진 문장제 그림(삼수선·올려본각 …)을 기하 골격만으로 그리면 원본과 멀어진다.
엔진은 그대로 두고, 엔진이 그린 SVG 의 **맨 뒤 층**(배경·모눈 바로 위)에 `<g data-asset="slug" transform=…>` 로
덧붙인다 — 수학 선·라벨이 그 위에 그려진다. 스펙의 최상위 `assets`:

    {"asset": "building", "from": "D", "to": "C"}
        에셋의 바닥(base)을 D 에, 꼭대기(top)를 C 에 — 크기는 두 점이 정한다. 12° 안쪽 기울기는 똑바로 세우고
        (서 있는 건물·탑), 더 기울면 그만큼 돌린다(벽에 기댄 사다리).
    {"asset": "house", "at": "A", "anchor": "base", "width": 40, "flip": false}
    {"asset": "airplane", "at": [x, y], "anchor": "center", "width": 60}

점은 v2 점 이름 또는 좌표 — v2 는 화면 좌표(y 아래), graph-1 은 수학 좌표. width 는 같은 좌표 단위.
기준점(base·top·center)은 assets/anchors.json(잉크로 잰 값), 없으면 틀의 아래 가운데·위 가운데·가운데.
선 굵기는 배율과 무관하게 윤곽 1.1 · 세부 0.8 로 맞춘다(도형 선 1.9 보다 약하게 — 수학이 앞에 보이게).

틀: 정제기는 viewBox 가 (0,0) 에서 시작해야 받는다. v2 는 에셋을 감싸는 **보이지 않는 점 두 개**를 장면에 더해
엔진이 틀을 잡게 한다(배치 계산은 한 번). graph-1 은 오른쪽·아래로만 넓히고, 왼쪽·위로 나가면 던진다.
틀린 스펙은 던진다(조용한 폴백 금지) — 다시 그리기가 그 사유로 명세를 고친다.
"""
from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping

import figure_assets

MAX_ITEMS = 12
ITEM_KEYS = frozenset({"asset", "from", "to", "at", "anchor", "width", "flip"})
ANCHORS = ("base", "top", "center")
STROKE_OUT = 1.1 / 1.4          # 에셋 파일 굵기(윤곽 1.4 · 세부 1) → 그림에서 1.1 · 0.8
UPRIGHT_DEG = 12.0              # from·to 기울기가 이 안쪽이면 똑바로 세운다
FRAME_PAD = 6.0
BOUND_POINTS = ("assetFrameLo", "assetFrameHi")
MAX_SIDE = 640.0                # 정제기 viewBox 한도(figure_quality.MAX_VIEWBOX_SIDE) — 조각 때문에 넘지 않게
LABEL_ROOM = 40.0               # 라벨·틀 여백 어림(배치 전이라 정확히는 모른다)

Point = tuple[float, float]
_anchor_cache: dict[str, Any] | None = None
_picture_cache: frozenset[str] | None = None


def picture_assets() -> frozenset[str]:
    """명세에서 쓸 수 있는 조각 — 도형으로 못 그리는 실물만(assets/picture-assets.json, 지시문과 같은 파일)."""
    global _picture_cache
    if _picture_cache is None:
        with open(os.path.join(figure_assets.ASSET_DIR, "picture-assets.json"), encoding="utf-8") as f:
            _picture_cache = frozenset(json.load(f)["picture"])
    return _picture_cache


def _anchors() -> dict[str, Any]:
    global _anchor_cache
    if _anchor_cache is None:
        try:
            with open(os.path.join(figure_assets.ASSET_DIR, "anchors.json"), encoding="utf-8") as f:
                _anchor_cache = json.load(f)
        except FileNotFoundError:
            _anchor_cache = {}
    return _anchor_cache


def asset_anchor(slug: str, kind: str, vb_w: float, vb_h: float) -> Point:
    value = (_anchors().get(slug) or {}).get(kind)
    if isinstance(value, list) and len(value) == 2 and all(isinstance(v, (int, float)) for v in value):
        return float(value[0]), float(value[1])
    return {"base": (vb_w / 2, vb_h), "top": (vb_w / 2, 0.0), "center": (vb_w / 2, vb_h / 2)}[kind]


def edge_anchor(slug: str, kind: str, vb_w: float, vb_h: float) -> Point:
    """from·to 가 쓰는 기준점. 건물처럼 잰 선(높이 CD)이 그림의 **모서리**인 조각은 anchors.json 의 edgeBase·edgeTop
    (원본 삼수선 그림은 CD 가 건물 앞 모서리이고 건물이 그 옆에 선다 — 가운데 축에 세우면 건물이 선을 가로지른다).
    없으면 base·top(탑·등대·사람·나무는 가운데 축이 그 선이다)."""
    value = (_anchors().get(slug) or {}).get({"base": "edgeBase", "top": "edgeTop"}[kind])
    if isinstance(value, list) and len(value) == 2 and all(isinstance(v, (int, float)) for v in value):
        return float(value[0]), float(value[1])
    return asset_anchor(slug, kind, vb_w, vb_h)


def _pair(value: Any, what: str) -> Point:
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in value)):
        raise ValueError(f"{what} 는 [x, y] 수 두 개여야 합니다")
    return float(value[0]), float(value[1])


def _num(v: float) -> str:
    text = f"{v:.3f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


@dataclass(frozen=True)
class Placed:
    slug: str
    body: str
    at: Point            # 기준점이 놓일 자리(장면 좌표)
    anchor: Point        # 에셋 좌표의 기준점
    scale: float
    angle: float         # 도
    flip: bool
    box: tuple[float, float, float, float]   # 장면 좌표 상자

    def transform(self, dx: float = 0.0, dy: float = 0.0) -> str:
        parts = [f"translate({_num(self.at[0] + dx)} {_num(self.at[1] + dy)})"]
        if abs(self.angle) > 1e-6:
            parts.append(f"rotate({_num(self.angle)})")
        parts.append(f"scale({_num(-self.scale if self.flip else self.scale)} {_num(self.scale)})")
        parts.append(f"translate({_num(-self.anchor[0])} {_num(-self.anchor[1])})")
        return " ".join(parts)


def plan_assets(items: Any, point: Callable[[Any], Point], length: Callable[[float], float],
                shrink: float = 1.0) -> list[Placed]:
    """스펙 assets → 놓을 자리(장면 좌표). 에셋 파일은 figure_assets 가 프로세스당 한 번 읽는다."""
    if not isinstance(items, list) or not items:
        raise ValueError("assets 는 비어 있지 않은 목록이어야 합니다")
    if len(items) > MAX_ITEMS:
        raise ValueError(f"assets 는 {MAX_ITEMS}개까지입니다")
    placed: list[Placed] = []
    for i, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise ValueError(f"assets[{i}] 는 객체여야 합니다")
        extra = set(item) - ITEM_KEYS
        if extra:
            raise ValueError(f"assets[{i}] 에 모르는 필드가 있습니다: {', '.join(sorted(extra))}")
        slug = item.get("asset")
        if not isinstance(slug, str):
            raise ValueError(f"assets[{i}].asset 은 에셋 이름이어야 합니다")
        vb_w, vb_h, body = figure_assets._asset_body(slug)
        if slug not in picture_assets():
            raise ValueError(f"assets: {slug} 는 도형으로 그릴 수 있는 물체라 그림 조각으로 쓰지 않습니다 — "
                             "원기둥·직육면체·원 같은 엔진 도형으로 그려 주세요")
        flip = item.get("flip", False)
        if not isinstance(flip, bool):
            raise ValueError("assets: flip 은 참/거짓이어야 합니다")
        fx = -1.0 if flip else 1.0
        if "from" in item or "to" in item:
            if "from" not in item or "to" not in item or "at" in item or "width" in item:
                raise ValueError("assets: from·to 는 둘 다 적고 at·width 와 섞지 않습니다")
            base, top = edge_anchor(slug, "base", vb_w, vb_h), edge_anchor(slug, "top", vb_w, vb_h)
            ax, ay = fx * (top[0] - base[0]), top[1] - base[1]
            p0, p1 = point(item["from"]), point(item["to"])
            bx, by = p1[0] - p0[0], p1[1] - p0[1]
            a_len, b_len = math.hypot(ax, ay), math.hypot(bx, by)
            if a_len < 1e-6 or b_len < 1e-6:
                raise ValueError(f"assets: {slug} 의 from 과 to 가 같은 점입니다")
            angle = math.degrees(math.atan2(by, bx) - math.atan2(ay, ax))
            angle = (angle + 180.0) % 360.0 - 180.0
            if abs(angle) <= UPRIGHT_DEG and abs(ay) > 1e-6:
                angle, scale = 0.0, abs(by) / abs(ay)      # 똑바로 세우고 높이를 맞춘다
            else:
                scale = b_len / a_len
            anchor, at = base, p0
        else:
            if "at" not in item or "width" not in item:
                raise ValueError("assets: at 과 width 를 적거나 from·to 를 적어 주세요")
            kind = item.get("anchor", "base")
            if kind not in ANCHORS:
                raise ValueError(f"assets: anchor 는 {'·'.join(ANCHORS)} 중 하나입니다")
            width = item["width"]
            if isinstance(width, bool) or not isinstance(width, (int, float)) or not math.isfinite(width) or width <= 0:
                raise ValueError("assets: width 는 양수여야 합니다")
            # 틀 한도 때문에 줄일 때는 한 점에 놓은 조각만(두 점에 맞춘 조각은 그 두 점이 크기다)
            scale = length(float(width)) / vb_w * shrink
            angle, anchor, at = 0.0, asset_anchor(slug, kind, vb_w, vb_h), point(item["at"])
        if not (0.02 <= scale <= 40):
            raise ValueError(f"assets: {slug} 크기가 지나칩니다(배율 {scale:.3g})")
        cos, sin = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        corners = []
        for x, y in ((0, 0), (vb_w, 0), (0, vb_h), (vb_w, vb_h)):
            lx, ly = (x - anchor[0]) * fx * scale, (y - anchor[1]) * scale
            corners.append((at[0] + lx * cos - ly * sin, at[1] + lx * sin + ly * cos))
        xs, ys = [c[0] for c in corners], [c[1] for c in corners]
        placed.append(Placed(slug, body.strip(), at, anchor, scale, angle, flip, (min(xs), min(ys), max(xs), max(ys))))
    return placed


def emit_assets(svg: str, placed: list[Placed], dx: float = 0.0, dy: float = 0.0) -> str:
    """에셋 층을 배경·모눈 바로 위(수학 선·라벨 아래)에 넣는다. 굵기는 배율과 무관하게 맞춘다."""
    layers = []
    for p in placed:
        k = STROKE_OUT / p.scale
        body = re.sub(r'stroke-width="([\d.]+)"', lambda m: f'stroke-width="{_num(float(m.group(1)) * k)}"', p.body)
        layers.append(f'<g data-asset="{p.slug}" transform="{p.transform(dx, dy)}">{body}</g>')
    pos = re.search(r"<svg\b[^>]*>", svg).end()
    while True:
        rest = svg[pos:]
        m = re.match(r'\s*<rect\b[^>]*\bwidth="(?:100%|[\d.]+)"[^>]*/>', rest)
        if m and "stroke=" not in m.group(0):           # 엔진 배경 사각형
            pos += m.end()
            continue
        if re.match(r"\s*<g\b[^>]*\bdata-grid=", rest):  # 모눈 층
            pos = svg.index("</g>", pos) + len("</g>")
            continue
        break
    return svg[:pos] + "".join(layers) + svg[pos:]


def render_v2_with_assets(spec: Mapping[str, Any], items: Any) -> str:
    """v2: 컴파일 한 번 → 에셋 자리 → 틀을 넓힐 보이지 않는 점 둘 → 배치 한 번 → 그리기.

    고정 캔버스 크기(canvas.width·height)는 뺀다 — 조각이 그 밖으로 나가면 엔진이 «fixed canvas clips»로 거부한다.
    도형+조각이 정제기 한도(640)를 넘으면 조각만 조금씩 줄인다(도형 좌표는 건드리지 않는다).
    """
    from core.figure_scene import compile_figure_spec

    spec = dict(spec)
    canvas = spec.get("canvas")
    if isinstance(canvas, Mapping) and ({"width", "height"} & set(canvas)):
        rest = {k: v for k, v in canvas.items() if k not in ("width", "height")}
        if rest:
            spec["canvas"] = rest
        else:
            spec.pop("canvas")
    scene = compile_figure_spec(spec)

    def point(ref: Any) -> Point:
        if isinstance(ref, str):
            p = scene.points.get(ref)
            if p is None:
                raise ValueError(f"assets: 없는 점 이름입니다: {ref}")
            return float(p.x), float(p.y)
        return _pair(ref, "assets 좌표")

    xs = [float(p.x) for p in scene.points.values()]
    ys = [float(p.y) for p in scene.points.values()]
    limit = MAX_SIDE - 2 * FRAME_PAD - LABEL_ROOM

    def fits(boxes: list[Placed]) -> bool:
        lo_x = min([p.box[0] for p in boxes] + xs) - FRAME_PAD
        lo_y = min([p.box[1] for p in boxes] + ys) - FRAME_PAD
        hi_x = max([p.box[2] for p in boxes] + xs) + FRAME_PAD
        hi_y = max([p.box[3] for p in boxes] + ys) + FRAME_PAD
        return max(hi_x - lo_x, hi_y - lo_y) <= limit

    shrink = 1.0
    placed = plan_assets(items, point, lambda u: u, shrink)
    # 한 점에 놓은 조각은 **줄여서 맞출 수 있을 때만** 줄인다 — 도형·두 점 조각만으로 이미 넘치면 줄여도 소용없이
    # 조각만 쪼그라든다(제일고 2026-10-21: 집이 원래의 14%). 그때는 그대로 두고 틀 거절로 명세 전체를 줄이게 한다.
    fixed = [p for p, item in zip(placed, items) if "from" in item]
    if fits(fixed):
        for _ in range(11):
            if fits(placed):
                break
            shrink *= 0.85
            placed = plan_assets(items, point, lambda u: u, shrink)
    scene.add_point(BOUND_POINTS[0], min(p.box[0] for p in placed) - FRAME_PAD, min(p.box[1] for p in placed) - FRAME_PAD)
    scene.add_point(BOUND_POINTS[1], max(p.box[2] for p in placed) + FRAME_PAD, max(p.box[3] for p in placed) + FRAME_PAD)
    resolved = scene.resolve()
    scene.resolve = lambda: resolved        # render_svg 가 배치를 다시 계산하지 않게(같은 장면 — 결과가 같다)
    tx, ty = resolved.translation
    return emit_assets(scene.render_svg(), placed, tx, ty)


def render_graph_with_assets(spec: Mapping[str, Any], svg: str, items: Any) -> str:
    """graph-1: render_graph 와 같은 식(여백 48, 수학 y 위)으로 좌표를 옮긴다. 틀은 오른쪽·아래로만 넓힌다."""
    m = re.search(r'<svg\b[^>]*\bviewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    if not m:
        raise ValueError("assets: 그래프 틀을 읽지 못했습니다")
    w, h = float(m.group(1)), float(m.group(2))
    xlo, xhi = _pair(spec.get("xRange"), "xRange")
    ylo, yhi = _pair(spec.get("yRange"), "yRange")
    pad = 48.0
    sx, sy = (w - 2 * pad) / (xhi - xlo), (h - 2 * pad) / (yhi - ylo)

    def point(ref: Any) -> Point:
        if isinstance(ref, str):
            raise ValueError("assets: graph-1 은 점 이름이 없습니다 — [x, y] 수학 좌표로 적어 주세요")
        x, y = _pair(ref, "assets 좌표")
        return pad + (x - xlo) * sx, h - pad - (y - ylo) * sy

    placed = plan_assets(items, point, lambda u: u * sx)
    if min(p.box[0] for p in placed) < 0 or min(p.box[1] for p in placed) < 0:
        raise ValueError("assets: 그림 조각이 그래프 틀 왼쪽·위로 나갑니다 — xRange·yRange 를 넓히거나 크기를 줄여 주세요")
    nw = max(w, max(p.box[2] for p in placed) + FRAME_PAD)
    nh = max(h, max(p.box[3] for p in placed) + FRAME_PAD)
    svg = emit_assets(svg, placed)
    if (nw, nh) != (w, h):
        svg = re.sub(r'(<svg\b[^>]*\bviewBox=")0 0 [\d.]+ [\d.]+(")', rf"\g<1>0 0 {_num(nw)} {_num(nh)}\g<2>", svg, count=1)
        svg = re.sub(r'(<svg\b[^>]*\bwidth=")[\d.]+(")', rf"\g<1>{_num(nw)}\g<2>", svg, count=1)
        svg = re.sub(r'(<svg\b[^>]*\bheight=")[\d.]+(")', rf"\g<1>{_num(nh)}\g<2>", svg, count=1)
    return svg


def split_assets(spec: Any) -> tuple[Any, Any]:
    """스펙에서 assets 를 떼어 낸다(엔진은 모르는 필드를 거부한다). 없으면 (스펙 그대로, None)."""
    if isinstance(spec, dict) and "assets" in spec:
        return {k: v for k, v in spec.items() if k != "assets"}, spec["assets"]
    return spec, None
