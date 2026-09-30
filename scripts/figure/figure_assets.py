# -*- coding: utf-8 -*-
"""실물 에셋 + 엔진 합성 — `assetScene` kind (elem-1 확장).

RPM 지면의 실물 맥락 그림(기차·터널·가로등·수조 …)은 순수 작도 엔진으로 못
그린다(mid1-stat-figure-feasibility.md ❌ 부류의 이웃). 대신 **에셋(자작 SVG
조각) 을 좌표에 배치하고 그 위에 치수 화살표·선분·라벨을 엔진이 얹는다** —
원본 지면의 「기차/터널 그림 + ↔ 터널의 길이」 구조가 정확히 이 모양이다
(RPM 1-1 p118 유형 UP 22 개념 상자, 실측 2026-08-23).

## 에셋 규격 (scripts/figure/assets/*.svg + manifest.json)

- 루트: `<svg viewBox="0 0 W H">` 하나. `width/height` 속성 금지(배치가 scale 로 정한다).
- 내용: 순수 도형 태그만 — script/style/외부 참조(href·url())/id/텍스트 금지.
  글자가 필요한 자리는 에셋이 아니라 **장면의 label** 로 얹는다(지면 글꼴과 한 벌).
- 선화: stroke 는 잉크색 계열(#222~#555), fill 은 옅은 채움. 지면 인쇄에서 뭉개지지
  않아야 한다(가는 회색 금지 — §4-11 점격자 교훈의 반대 방향).
- manifest.json: {"assets": [{"slug","label","file","viewBox":[w,h],"tags":[...]}]}
  슬러그는 kebab-case 영문. **로더가 manifest 에 없는 파일·규격 위반을 던진다.**

## 스펙

    {"version":"elem-1","kind":"assetScene",
     "items":[{"asset":"train-side","x":40,"y":30,"w":120}],
     "dims":[{"x1":10,"y1":80,"x2":90,"y2":80,"label":"400 m"}],
     "segments":[[10,20,90,20,"dash"]],
     "labels":[{"x":50,"y":10,"text":"터널"}],
     "canvas":[240,120]}

검증 실패는 전부 **던진다** — 조용한 폴백 금지(브리프 계약).
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Mapping

ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
# manifest 는 여러 조각(manifest*.json)을 병합한다 — 병렬 세션이 서로 다른 조각을
# 소유해 같은 파일을 만지지 않게. slug 가 조각끼리 겹치면 던진다.

INK = "#333"

# 에셋 내용에서 허용하는 태그만 — 이 밖이 나오면 로더가 던진다.
_ALLOWED_TAGS = frozenset(
    {"g", "rect", "circle", "ellipse", "line", "polygon", "polyline", "path"}
)
_FORBIDDEN_RE = re.compile(
    r"<\s*(script|style|image|foreignObject|use|text)\b|href\s*=|url\s*\(|\bid\s*=",
    re.IGNORECASE,
)

_manifest_cache: dict[str, dict[str, Any]] | None = None
_body_cache: dict[str, tuple[float, float, str]] = {}


def _load_manifest() -> dict[str, dict[str, Any]]:
    global _manifest_cache
    if _manifest_cache is not None:
        return _manifest_cache
    import glob
    files = sorted(glob.glob(os.path.join(ASSET_DIR, "manifest*.json")))
    if not files:
        raise ValueError("에셋 manifest 가 없습니다: scripts/figure/assets/manifest*.json")
    rows: list[dict[str, Any]] = []
    for fp in files:
        with open(fp, encoding="utf-8") as f:
            rows.extend(json.load(f).get("assets", []))
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        slug = row.get("slug")
        if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug):
            raise ValueError(f"에셋 slug 가 kebab-case 가 아닙니다: {slug!r}")
        if slug in out:
            raise ValueError(f"에셋 slug 가 겹칩니다: {slug}")
        vb = row.get("viewBox")
        if (
            not isinstance(vb, list)
            or len(vb) != 2
            or not all(isinstance(v, (int, float)) and v > 0 for v in vb)
        ):
            raise ValueError(f"에셋 {slug} 의 viewBox 는 [w,h] 양수여야 합니다")
        out[slug] = row
    _manifest_cache = out
    return out


def _asset_body(slug: str) -> tuple[float, float, str]:
    """에셋 SVG 파일 → (vb_w, vb_h, 내부 마크업). 규격 위반은 던진다."""
    if slug in _body_cache:
        return _body_cache[slug]
    row = _load_manifest().get(slug)
    if row is None:
        raise ValueError(f"manifest 에 없는 에셋입니다: {slug}")
    path = os.path.join(ASSET_DIR, row["file"])
    if not os.path.exists(path):
        raise ValueError(f"에셋 파일이 없습니다: {row['file']}")
    with open(path, encoding="utf-8") as f:
        svg = f.read()
    if _FORBIDDEN_RE.search(svg):
        raise ValueError(f"에셋 {slug} 에 금지 태그/속성이 있습니다 (script·image·use·text·id·href·url)")
    m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    if not m:
        raise ValueError(f"에셋 {slug} 루트에 viewBox=\"0 0 W H\" 가 없습니다")
    vb_w, vb_h = float(m.group(1)), float(m.group(2))
    mv = row["viewBox"]
    if abs(vb_w - mv[0]) > 0.01 or abs(vb_h - mv[1]) > 0.01:
        raise ValueError(f"에셋 {slug} 의 viewBox 가 manifest 와 다릅니다: 파일 {vb_w}x{vb_h} vs manifest {mv}")
    inner = re.sub(r"^.*?<svg[^>]*>", "", svg, count=1, flags=re.DOTALL)
    inner = re.sub(r"</svg>\s*$", "", inner)
    for tag in re.findall(r"<\s*([a-zA-Z][a-zA-Z0-9]*)", inner):
        if tag not in _ALLOWED_TAGS:
            raise ValueError(f"에셋 {slug} 에 허용 밖 태그: <{tag}>")
    _body_cache[slug] = (vb_w, vb_h, inner)
    return _body_cache[slug]


def list_assets() -> list[dict[str, Any]]:
    return list(_load_manifest().values())


def _n(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s if s else "0"


def _num(v: Any, what: str) -> float:
    if not isinstance(v, (int, float)):
        raise ValueError(f"{what} 는 수여야 합니다")
    return float(v)


def _dim_arrow(x1: float, y1: float, x2: float, y2: float, label: str) -> str:
    """원본 지면의 «↔ 길이» 치수 — 양끝 화살촉 + 가운데 라벨."""
    import math

    dx, dy = x2 - x1, y2 - y1
    L = math.hypot(dx, dy)
    if L < 8:
        raise ValueError("치수 화살표가 너무 짧습니다 (8 미만)")
    ux, uy = dx / L, dy / L
    px, py = -uy, ux
    a = 4.5
    parts = [
        f'<line x1="{_n(x1)}" y1="{_n(y1)}" x2="{_n(x2)}" y2="{_n(y2)}" stroke="{INK}" stroke-width="1.1"/>'
    ]
    for (bx, by), s in (((x1, y1), 1), ((x2, y2), -1)):
        tipx, tipy = bx, by
        b1x = bx + s * ux * a + px * a * 0.6
        b1y = by + s * uy * a + py * a * 0.6
        b2x = bx + s * ux * a - px * a * 0.6
        b2y = by + s * uy * a - py * a * 0.6
        parts.append(
            f'<polygon points="{_n(tipx)},{_n(tipy)} {_n(b1x)},{_n(b1y)} {_n(b2x)},{_n(b2y)}" fill="{INK}"/>'
        )
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    if label:
        parts.append(
            f'<text x="{_n(mx)}" y="{_n(my - 4)}" font-size="11" text-anchor="middle" fill="{INK}">{label}</text>'
        )
    return "".join(parts)


def render_asset_scene(spec: Mapping[str, Any]) -> str:
    items = spec.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("items 는 비어 있지 않은 배열이어야 합니다")
    canvas = spec.get("canvas", [240, 140])
    if not isinstance(canvas, list) or len(canvas) != 2:
        raise ValueError("canvas 는 [w,h] 여야 합니다")
    cw, ch = _num(canvas[0], "canvas[0]"), _num(canvas[1], "canvas[1]")
    if not (40 <= cw <= 480 and 30 <= ch <= 360):
        raise ValueError("canvas 는 40~480 x 30~360 안이어야 합니다")

    parts: list[str] = []
    for i, it in enumerate(items):
        if not isinstance(it, Mapping):
            raise ValueError(f"items[{i}] 는 객체여야 합니다")
        vb_w, vb_h, body = _asset_body(str(it.get("asset")))
        x = _num(it.get("x"), f"items[{i}].x")
        y = _num(it.get("y"), f"items[{i}].y")
        w = _num(it.get("w"), f"items[{i}].w")
        if w <= 0:
            raise ValueError(f"items[{i}].w 는 양수여야 합니다")
        s = w / vb_w
        flip = bool(it.get("flip"))
        tf = f"translate({_n(x)},{_n(y)}) scale({_n(s)})"
        if flip:
            tf += f" translate({_n(vb_w)},0) scale(-1,1)"
        parts.append(f'<g transform="{tf}">{body}</g>')

    for j, seg in enumerate(spec.get("segments") or []):
        if not isinstance(seg, list) or len(seg) not in (4, 5):
            raise ValueError(f"segments[{j}] 는 [x1,y1,x2,y2(,\"dash\")] 여야 합니다")
        dash = ' stroke-dasharray="5 4"' if len(seg) == 5 and seg[4] == "dash" else ""
        parts.append(
            f'<line x1="{_n(_num(seg[0], "x1"))}" y1="{_n(_num(seg[1], "y1"))}" '
            f'x2="{_n(_num(seg[2], "x2"))}" y2="{_n(_num(seg[3], "y2"))}" '
            f'stroke="{INK}" stroke-width="1.1"{dash}/>'
        )

    for k, d in enumerate(spec.get("dims") or []):
        if not isinstance(d, Mapping):
            raise ValueError(f"dims[{k}] 는 객체여야 합니다")
        parts.append(
            _dim_arrow(
                _num(d.get("x1"), "x1"),
                _num(d.get("y1"), "y1"),
                _num(d.get("x2"), "x2"),
                _num(d.get("y2"), "y2"),
                str(d.get("label", "")),
            )
        )

    for m, lab in enumerate(spec.get("labels") or []):
        if not isinstance(lab, Mapping) or "text" not in lab:
            raise ValueError(f"labels[{m}] 는 {{x,y,text}} 여야 합니다")
        parts.append(
            f'<text x="{_n(_num(lab.get("x"), "x"))}" y="{_n(_num(lab.get("y"), "y"))}" '
            f'font-size="11" text-anchor="middle" fill="{INK}">{lab["text"]}</text>'
        )

    return (
        f'<svg viewBox="0 0 {_n(cw)} {_n(ch)}" xmlns="http://www.w3.org/2000/svg">'
        f'<rect width="{_n(cw)}" height="{_n(ch)}" fill="#fff"/>' + "".join(parts) + "</svg>"
    )


ASSET_FIELDS: dict[str, frozenset[str]] = {
    "assetScene": frozenset({"items"}),
}
ASSET_OPTIONAL: dict[str, frozenset[str]] = {
    "assetScene": frozenset({"canvas", "dims", "segments", "labels"}),
}
ASSET_RENDER = {
    "assetScene": render_asset_scene,
}
