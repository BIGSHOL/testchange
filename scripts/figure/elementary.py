# -*- coding: utf-8 -*-
"""초등 교재 그림 — FigureSpec v2 에 없는 상자·수 모형·수 카드.

버전은 `elem-1`. 기하 작도(각·원·치수선)는 여기 넣지 않는다 — 그건 엔진 A.
허용 종류 밖·모르는 키는 예외. 빈 SVG 로 통과시키지 않는다.

같은 그림이 두 번 나오면 좌표 일회성으로 맞추지 말고 kind 를 추가한다 (D-61, 09 §2.1).
재발 금지: 사다리꼴 두 대각선, FigureSpec labels 로 가/나, 표 viewBox 키우기,
피자 오림, 치수 손 곡선, 점격자 진한 점선, 원기둥 전개도 떠 있는 원, 원뿔 삼각형+타원 — 09 §4-6~4-13.
"""
from __future__ import annotations

import io as io
import json as _json
import math
import os as _os
import re
from html import escape
from typing import Any, Mapping

INK = "#111111"
PAPER = "#ffffff"
FAINT = "#f4f4f2"
# 점격자 바탕선. 교재 모눈은 연한 청색 — #7aa0c4·1.05px 는 발문 대비 진했다.
GRID = "#c8d7e4"
GRID_SW = 0.7
# 표 viewBox 를 이보다 키우면 화면에서 숫자가 본문보다 작아진다 (09 §4-8).
TABLE_VIEWBOX_MAX = 240.0
# 치수 점선이 도형에서 벌어지는 거리. 한 값만 쓴다 — 도형마다 다르면 같은 시험지에서
# 삼각형 치수는 붙어 있고 직육면체 치수만 붕 뜬다 (09 §4-16).
DIM_OFF = 12.0
# 그린 것과 viewBox 사이 최소 여유. 획 굵기 절반 + 반올림.
FIT_PAD = 2.0
KIND_FIELDS: dict[str, frozenset[str]] = {
    "numberCards": frozenset({"cards"}),
    # ② 도형 위 표시 — 성질 문항. 고르기(`namedShapes`)와 **모양 목록을 공유**한다.
    "markedShape": frozenset({"shape"}),
    # ③ 두 직선의 관계 — 수직·평행(+ 평행선 사이 거리). 초4 2-4-1·2·3.
    "lineRelation": frozenset({"relation"}),
    # ⑥ 조각과 목표를 나란히 — **채운 모습은 안 그린다**(답이 샌다). 초4 2-6-4.
    "tiling": frozenset({"piece", "target"}),
    # ① 원과 그 부분 — 초3 2-3. **용어 라벨은 안 그린다**(그 용어가 답이다).
    "circleParts": frozenset(),
    "placeValue": frozenset({"hundreds", "tens", "ones"}),
    "base10": frozenset({"rows"}),
    "opBox": frozenset({"input", "op"}),
    "sumBox": frozenset({"left", "right"}),
    "opTree": frozenset({"start", "ops"}),
    "boxChain": frozenset({"start", "steps"}),
    "columnOp": frozenset({"top", "op", "bottom"}),
    "numberLine": frozenset({"max"}),
    "clocks": frozenset({"items"}),
    "table": frozenset({"headers", "rows"}),
    "tape": frozenset({"length", "label"}),
    "dotGrid": frozenset({"rows", "cols"}),
    "boxedList": frozenset({"items"}),
    "pills": frozenset({"items"}),
    "geoLine": frozenset(),
    "anglePick": frozenset(),
    "timeAdd": frozenset({"start", "add"}),
    "pointGrid": frozenset({"cols", "rows", "dots"}),
    "divideTriangle": frozenset({"n"}),
    "fracPie": frozenset({"n", "filled"}),
    "triRow": frozenset({"n", "filled"}),
    "trapFour": frozenset({"filled"}),
    "namedShapes": frozenset({"items"}),
}
OPTIONAL: dict[str, frozenset[str]] = {
    "base10": frozenset({"equation"}),
    "markedShape": frozenset({"sides", "angles", "equal", "right", "diagonals"}),
    "lineRelation": frozenset({"labels", "distance", "marks", "perpCount"}),
    "tiling": frozenset({"pieceSide", "targetSide", "labels"}),
    "circleParts": frozenset({"radius", "diameter", "center", "show"}),
    "opBox": frozenset({"output"}),
    "columnOp": frozenset({"result", "highlight"}),
    "numberLine": frozenset({"min", "step", "hops", "barTo", "tick", "blanks"}),
    "tape": frozenset({"unit", "segments"}),
    "boxedList": frozenset({"marks"}),
    "pointGrid": frozenset({"lines", "square"}),
    "fracPie": frozenset({"start", "fill"}),
    "triRow": frozenset({"fill"}),
    "trapFour": frozenset({"fill"}),
    # `align` — 칸 정렬("center" 기본 / "left"). 줄기와 잎의 **잎**이 왼쪽이어야 한다.
    "table": frozenset({"align"}),
}


def validate_elementary(spec: Mapping[str, Any]) -> str:
    """스펙을 검증하고 kind 를 돌려준다. **검증은 한 벌뿐이다.**

    `chartPair` 는 안쪽 그래프를 «좁게» 그려야 해서 렌더 함수를 직접 부르는데,
    그때도 이 검증을 그대로 탄다 — 안 그러면 짝 안에서만 오타 키가 통과한다.
    """
    if not isinstance(spec, Mapping):
        raise ValueError("초등 스펙이 객체가 아닙니다")
    if spec.get("version") != "elem-1":
        raise ValueError("초등 스펙 version 은 elem-1 이어야 합니다")
    kind = spec.get("kind")
    if not isinstance(kind, str) or kind not in KIND_FIELDS:
        raise ValueError(f"모르는 초등 그림 종류입니다: {kind}")
    allowed = {"version", "kind"} | KIND_FIELDS[kind] | OPTIONAL.get(kind, frozenset())
    extra = set(spec) - allowed
    if extra:
        raise ValueError(f"허용되지 않은 키: {', '.join(sorted(str(k) for k in extra))}")
    missing = KIND_FIELDS[kind] - set(spec)
    if missing:
        raise ValueError(f"빠진 키: {', '.join(sorted(missing))}")
    return kind


def render_elementary(spec: Mapping[str, Any]) -> str:
    return _RENDER[validate_elementary(spec)](spec)


def _svg(w: float, h: float, body: str) -> str:
    """viewBox 는 **그린 것을 모두 담는다** (09 §4-14).

    kind 마다 여백을 손으로 맞추면 도형이 조금만 달라져도 같은 결함이 다시 난다 —
    오각기둥 전개도에서 위·아래 꼭짓점이 잘려 나갔다(원장님 2026-08-22). 문항마다
    좌표를 고치지 말고(D-61) 여기 한 곳에서 맞춘다: 몸통의 경계 상자를 재서
    음수 쪽으로 나가면 **내용을 밀고**, 모자라면 viewBox 를 **넓힌다**.

    ⚠️ `<g transform>` 로 못 민다 — `sanitize_svg` 가 `transform` 을 막는다.
       그래서 좌표 숫자를 직접 옮긴다. 모르는 그리기 태그나 상대 경로 명령이 오면
       **조용히 지나가지 않고 예외**를 낸다(못 옮긴 것이 잘려도 아무도 모른다).
    """
    box = _body_bbox(body)
    # 🔴 **글자는 따로 본다.** `_body_bbox` 는 `<text>` 를 닻점 하나로 세므로,
    #    글자가 지면 밖으로 나가도 viewBox 가 안 넓어지고 **에러도 안 난다** —
    #    실측으로 `12 cm` 의 `1` 이 왼쪽으로 5.24단위 잘려 나가고 있었다
    #    (원장님 지적 2026-08-28, `netCuboid` 계열).
    #
    #    ⚠️ 다만 글자에는 **여백(FIT_PAD)을 요구하지 않는다.** 요구하면 가장자리에
    #       딱 붙여 놓은 축 이름표(x=0)가 밀려 그림 전체가 넓어지고, 폭을 박는
    #       kind(통계·좌표평면)가 「폭이 벌어졌다」로 던진다(실측 240 → 243).
    #       글자에 필요한 것은 **안 잘리는 것**이지 여백이 아니다.
    tbox = _text_extent(body)
    if box is not None or tbox is not None:
        gx0, gy0, gx1, gy1 = box if box is not None else (FIT_PAD, FIT_PAD, 0.0, 0.0)
        tx0, ty0, tx1, ty1 = tbox if tbox is not None else (0.0, 0.0, 0.0, 0.0)
        dx = max(0.0, FIT_PAD - gx0, -tx0)
        dy = max(0.0, FIT_PAD - gy0, -ty0)
        if dx or dy:
            body = _shift_body(body, dx, dy)
        w = max(w + dx, gx1 + dx + FIT_PAD, tx1 + dx)
        h = max(h + dy, gy1 + dy + FIT_PAD, ty1 + dy)
    return _svg_raw(w, h, body)


def _svg_raw(w: float, h: float, body: str) -> str:
    return (
        f'<svg viewBox="0 0 {_n(w)} {_n(h)}" xmlns="http://www.w3.org/2000/svg">'
        f"{body}</svg>"
    )


_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
_TAG_RE = re.compile(r"<([a-zA-Z][\w:-]*)((?:\s+[\w:-]+=\"[^\"]*\")*)\s*/?>")
_ATTR_RE = re.compile(r"([\w:-]+)=\"([^\"]*)\"")
_PATH_TOKEN_RE = re.compile(rf"[A-Za-z]|{_NUM}")
_NUM_PAIR_RE = re.compile(rf"({_NUM})[ ,]+({_NUM})")
# 좌표를 갖는 태그. `text` 는 **닻점만** 센다 — 글꼴 폭은 여기서 알 수 없다.
# 라벨은 measured() 가 스스로 바깥으로 밀고, kind 가 그만큼 여백을 잡는다.
_GEOM_TAGS = frozenset({"rect", "circle", "ellipse", "line", "polygon", "polyline", "path", "text"})
_IGNORED_TAGS = frozenset({"svg", "g", "defs", "title", "desc", "tspan"})
# 절대 명령만 쓴다. 상대(소문자)는 안 만들고, 오면 예외로 드러낸다.
_PATH_ARGC = {"M": 2, "L": 2, "T": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "A": 7, "Z": 0}


def _body_bbox(body: str) -> tuple[float, float, float, float] | None:
    pts: list[tuple[float, float]] = []
    for tag, attrs in _iter_tags(body):
        pts.extend(_tag_points(tag, attrs))
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _text_extent(body: str) -> tuple[float, float, float, float] | None:
    """그려진 글자 전체의 경계. 자는 `_text_bboxes` **하나**뿐이다."""
    rows = _text_bboxes(body)
    if not rows:
        return None
    return (
        min(r[0] for r in rows),
        min(r[1] for r in rows),
        max(r[2] for r in rows),
        max(r[3] for r in rows),
    )


def _iter_tags(body: str):
    for m in _TAG_RE.finditer(body):
        tag = m.group(1)
        if tag in _IGNORED_TAGS:
            continue
        if tag not in _GEOM_TAGS:
            raise ValueError(f"경계 상자를 잴 수 없는 태그입니다: {tag}")
        yield tag, dict(_ATTR_RE.findall(m.group(2)))


def _f(attrs: Mapping[str, str], key: str, default: float = 0.0) -> float:
    raw = attrs.get(key)
    return default if raw is None else float(raw)


def _tag_points(tag: str, attrs: Mapping[str, str]) -> list[tuple[float, float]]:
    if tag == "rect":
        x, y = _f(attrs, "x"), _f(attrs, "y")
        return [(x, y), (x + _f(attrs, "width"), y + _f(attrs, "height"))]
    if tag in ("circle", "ellipse"):
        cx, cy = _f(attrs, "cx"), _f(attrs, "cy")
        rx = _f(attrs, "r") or _f(attrs, "rx")
        ry = _f(attrs, "r") or _f(attrs, "ry")
        return [(cx - rx, cy - ry), (cx + rx, cy + ry)]
    if tag == "line":
        return [
            (_f(attrs, "x1"), _f(attrs, "y1")),
            (_f(attrs, "x2"), _f(attrs, "y2")),
        ]
    if tag in ("polygon", "polyline"):
        return [
            (float(a), float(b)) for a, b in _NUM_PAIR_RE.findall(attrs.get("points", ""))
        ]
    if tag == "path":
        return _path_points(attrs.get("d", ""))
    return [(_f(attrs, "x"), _f(attrs, "y"))]


def _bezier_extrema(p0: float, ctrl: list[float], p1: float) -> list[float]:
    """한 축의 베지에 극값 — 제어점을 그대로 담으면 measured() 곡선이 실제보다
    두 배 부풀어 쓸데없는 여백이 생긴다(제어점은 곡선이 닿지 않는 자리다)."""
    out = [p0, p1]
    if len(ctrl) == 1:
        den = p0 - 2 * ctrl[0] + p1
        ts = [] if abs(den) < 1e-12 else [(p0 - ctrl[0]) / den]
        for t in ts:
            if 0 < t < 1:
                out.append((1 - t) ** 2 * p0 + 2 * (1 - t) * t * ctrl[0] + t * t * p1)
        return out
    c0, c1 = ctrl
    a = -p0 + 3 * c0 - 3 * c1 + p1
    b = 2 * (p0 - 2 * c0 + c1)
    c = c0 - p0
    roots: list[float] = []
    if abs(a) < 1e-12:
        if abs(b) > 1e-12:
            roots.append(-c / b)
    else:
        disc = b * b - 4 * a * c
        if disc >= 0:
            sq = math.sqrt(disc)
            roots += [(-b + sq) / (2 * a), (-b - sq) / (2 * a)]
    for t in roots:
        if 0 < t < 1:
            out.append(
                (1 - t) ** 3 * p0
                + 3 * (1 - t) ** 2 * t * c0
                + 3 * (1 - t) * t * t * c1
                + t**3 * p1
            )
    return out


def _arc_points(
    p0: tuple[float, float], rx: float, ry: float, large: float, sweep: float, p1: tuple[float, float]
) -> list[tuple[float, float]]:
    """호의 극값. 우리는 회전 없는 **정원** 호만 그린다 — 그 경우만 정확히 풀고,
    그 밖은 반지름만큼 넉넉히 잡는다(넘치는 쪽이 잘리는 쪽보다 낫다)."""
    if abs(rx - ry) > 1e-9 or rx <= 0:
        return [
            (p0[0] - rx, p0[1] - ry),
            (p0[0] + rx, p0[1] + ry),
            (p1[0] - rx, p1[1] - ry),
            (p1[0] + rx, p1[1] + ry),
        ]
    mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
    dx, dy = (p1[0] - p0[0]) / 2, (p1[1] - p0[1]) / 2
    d2 = dx * dx + dy * dy
    hh = max(0.0, rx * rx - d2)
    k = math.sqrt(hh / d2) if d2 > 0 else 0.0
    # SVG 끝점→중심 변환: c' = ±(y', −x'), x'y' 는 (p0−p1)/2 다. (p1−p0) 로 잡으면
    # 부호가 통째로 뒤집혀 중심이 반대편에 앉는다 — 분수 원 viewBox 가 112 → 264 가 됐다.
    sign = 1.0 if (large != sweep) else -1.0
    cx, cy = mx - sign * k * dy, my + sign * k * dx
    a0 = math.atan2(p0[1] - cy, p0[0] - cx)
    a1 = math.atan2(p1[1] - cy, p1[0] - cx)
    if sweep:
        while a1 < a0:
            a1 += 2 * math.pi
    else:
        while a1 > a0:
            a1 -= 2 * math.pi
    out = [p0, p1]
    for q in range(-4, 9):
        ang = q * math.pi / 2
        if min(a0, a1) - 1e-9 <= ang <= max(a0, a1) + 1e-9:
            out.append((cx + rx * math.cos(ang), cy + rx * math.sin(ang)))
    return out


def _path_points(d: str) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    cur = (0.0, 0.0)
    for cmd, args in _walk_path(d):
        if cmd == "Z":
            continue
        if cmd == "H":
            cur = (args[0], cur[1])
            out.append(cur)
        elif cmd == "V":
            cur = (cur[0], args[0])
            out.append(cur)
        elif cmd in ("M", "L", "T"):
            for i in range(0, len(args), 2):
                cur = (args[i], args[i + 1])
                out.append(cur)
        elif cmd in ("Q", "S", "C"):
            cx_ctrl = [args[0]] if cmd != "C" else [args[0], args[2]]
            cy_ctrl = [args[1]] if cmd != "C" else [args[1], args[3]]
            end = (args[2], args[3]) if cmd != "C" else (args[4], args[5])
            # 축마다 따로 극값을 낸다 — 상자는 x·y 를 독립으로 합치므로 짝은 상관없다.
            xs = _bezier_extrema(cur[0], cx_ctrl, end[0])
            ys = _bezier_extrema(cur[1], cy_ctrl, end[1])
            out += [(x, cur[1]) for x in xs] + [(cur[0], y) for y in ys]
            cur = end
        elif cmd == "A":
            end = (args[5], args[6])
            out += _arc_points(cur, args[0], args[1], args[3], args[4], end)
            cur = end
    return out


def _walk_path(d: str):
    tokens = _PATH_TOKEN_RE.findall(d)
    i = 0
    cmd = ""
    while i < len(tokens):
        tok = tokens[i]
        if tok.isalpha():
            cmd = tok
            i += 1
            if cmd not in _PATH_ARGC:
                raise ValueError(f"모르는 경로 명령입니다: {cmd}")
        if not cmd:
            raise ValueError("경로가 명령 없이 시작합니다")
        argc = _PATH_ARGC[cmd]
        if argc == 0:
            yield cmd, []
            continue
        args = [float(t) for t in tokens[i : i + argc]]
        if len(args) < argc:
            raise ValueError(f"경로 명령 {cmd} 의 인자가 모자랍니다")
        i += argc
        yield cmd, args
        if cmd == "M":
            cmd = "L"


def _shift_body(body: str, dx: float, dy: float) -> str:
    def repl(m: re.Match[str]) -> str:
        tag = m.group(1)
        if tag in _IGNORED_TAGS:
            return m.group(0)
        if tag not in _GEOM_TAGS:
            raise ValueError(f"옮길 수 없는 태그입니다: {tag}")
        attrs = m.group(2)

        def one(a: re.Match[str]) -> str:
            key, val = a.group(1), a.group(2)
            if key in ("x", "x1", "x2", "cx"):
                return f'{key}="{_n(float(val) + dx)}"'
            if key in ("y", "y1", "y2", "cy"):
                return f'{key}="{_n(float(val) + dy)}"'
            if key == "points":
                moved = _NUM_PAIR_RE.sub(
                    lambda p: f"{_n(float(p.group(1)) + dx)},{_n(float(p.group(2)) + dy)}", val
                )
                return f'{key}="{moved}"'
            if key == "d":
                return f'{key}="{_shift_path(val, dx, dy)}"'
            return a.group(0)

        return m.group(0).replace(attrs, _ATTR_RE.sub(one, attrs), 1) if attrs else m.group(0)

    return _TAG_RE.sub(repl, body)


def _shift_path(d: str, dx: float, dy: float) -> str:
    out: list[str] = []
    for cmd, args in _walk_path(d):
        moved: list[float] = []
        if cmd == "H":
            moved = [args[0] + dx]
        elif cmd == "V":
            moved = [args[0] + dy]
        elif cmd == "A":
            moved = args[:5] + [args[5] + dx, args[6] + dy]
        else:
            moved = [a + (dx if i % 2 == 0 else dy) for i, a in enumerate(args)]
        out.append(cmd + " " + " ".join(_n(v) for v in moved) if moved else cmd)
    return " ".join(out)


def _n(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _esc(v: Any) -> str:
    return escape(str(v), quote=True)


def _dashed_polyline(
    pts: list[tuple[float, float]],
    dash: str,
    *,
    stroke: str = INK,
    sw: float = 1.3,
) -> str:
    """치수가 아닌 점선을 짧은 실선 조각으로 그린다.

    `measured()` 의 inline `stroke-dasharray` 는 치수 판정기의 식별자다. 숨은 모서리·
    보조선까지 같은 표식을 쓰면 판정기가 둘을 구별할 수 없으므로, 보이는 무늬는
    유지하되 구조용 점선은 명시적인 조각들로 낸다.
    """
    pattern = [float(v) for v in dash.split()]
    if not pattern or any(v <= 0 for v in pattern):
        raise ValueError("dash 는 양수 길이 목록이어야 합니다")
    if len(pattern) % 2:
        pattern *= 2
    out: list[str] = []
    pi = 0
    remain = pattern[0]
    drawing = True
    for a, b in zip(pts, pts[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length <= 1e-9:
            continue
        at = 0.0
        while at < length - 1e-9:
            take = min(remain, length - at)
            if drawing and take > 1e-9:
                t0, t1 = at / length, (at + take) / length
                x0, y0 = a[0] + dx * t0, a[1] + dy * t0
                x1, y1 = a[0] + dx * t1, a[1] + dy * t1
                out.append(
                    f'<line x1="{_n(x0)}" y1="{_n(y0)}" x2="{_n(x1)}" y2="{_n(y1)}" '
                    f'stroke="{_esc(stroke)}" stroke-width="{_n(sw)}"/>'
                )
            at += take
            remain -= take
            if remain <= 1e-9:
                pi = (pi + 1) % len(pattern)
                remain = pattern[pi]
                drawing = pi % 2 == 0
    return "".join(out)


def _rect(
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    rx: float = 0,
    fill: str = PAPER,
    stroke: str = INK,
    sw: float = 1.3,
    dash: str | None = None,
) -> str:
    d = f' stroke-dasharray="{_esc(dash)}"' if dash else ""
    return (
        f'<rect x="{_n(x)}" y="{_n(y)}" width="{_n(w)}" height="{_n(h)}" '
        f'rx="{_n(rx)}" fill="{fill}" stroke="{stroke}" stroke-width="{_n(sw)}"{d}/>'
    )


def _text(
    x: float,
    y: float,
    t: Any,
    *,
    size: float = 14,
    anchor: str = "middle",
    weight: str = "700",
) -> str:
    return (
        f'<text x="{_n(x)}" y="{_n(y)}" fill="{INK}" font-size="{_n(size)}" '
        f'font-family="Batang, serif" font-weight="{weight}" text-anchor="{anchor}" '
        f'dominant-baseline="middle">{_esc(t)}</text>'
    )


# 13pt 글자 폭 **상한** — 실측 「바닐라」 39.72/3 = 13.24(한글), 숫자 7.99.
# 라틴·괄호는 숫자보다도 좁아서(「(개)」 23.54 = 한글 13.24 + 괄호 둘 10.3) 8.0 이면 넉넉하다.
# 잘림을 막는 용도라 **상한이면 맞다** — 다만 너무 헐거우면 배치에서 폭을 낭비하므로
# 한글과 나머지를 나눈다(모두 한글로 치면 「(개)」가 39.7 로 16단위 부풀었다).
#
# ⚠️ **여기가 한 곳이다.** 표 열 폭(`_table`)과 그래프 라벨(`elem_advanced`)이 같은 자를
#    써야 한다 — 두 벌이 되면 한쪽만 고쳐진다(2026-08-18 「같은 규칙을 쓰는 자리가 둘이면
#    한 숫자를 두 곳이 쓰게 하라」). elem_advanced 는 이것을 import 한다.
HANGUL_W_13 = 13.24
ASCII_W_13 = 8.0

# ── 글자 폭 표는 **MathJax 에서 뽑는다** (2026-08-28) ───────────────────────
#
# 🔴 위 `ASCII_W_13 = 8.0`(= 0.6154em) 은 **한 값**이었다. 그런데 지면을 그리는
#    것은 이제 MathJax 이고, 그 글꼴에서 **34종이 그 값보다 넓다** — `M` 1.71배 ·
#    `m` 1.43배 · `+` 1.26배. 어림이 실제보다 좁으면 배치기는 「자리가 남는다」고
#    판단하고 지면에서는 라벨이 **잘린다**(실측: `12 cm` 의 `1` 이 왼쪽으로
#    5.24단위 나갔다 — 원장님 지적 2026-08-28).
#
#    그래서 손으로 정한 한 값을 버리고 **정본에서 뽑은 표**를 쓴다
#    (`scripts/qa/build-label-width-table.ts` 가 굽는다). 표를 못 읽으면 옛 값으로
#    물러서되 **조용히 넘어가지 않는다** — 그 자리가 곧 잘림이기 때문이다.
_WIDTHS_PATH = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                            "label-widths.json")
_WIDTH_TABLE: dict | None = None


def _width_table() -> dict:
    global _WIDTH_TABLE
    if _WIDTH_TABLE is None:
        try:
            with io.open(_WIDTHS_PATH, encoding="utf-8") as fh:
                _WIDTH_TABLE = _json.load(fh)
        except Exception:  # 표가 없으면 옛 어림 — 다만 상한이 아니다.
            _WIDTH_TABLE = {}
    return _WIDTH_TABLE


def _label_w_max(text: str, size: float = 13.0) -> float:
    """글자 폭 **상한**. 지면을 그리는 MathJax 에서 뽑은 표로 잰다.

    ⚠️ 「가운데 낀 이항 연산자」는 앞뒤에 여백을 얻는다(TeX 규칙) — 그 항이 없으면
       `x°-9°` 가 16.3% 좁게 나온다. 표에 실린 `opSpace` 를 그대로 쓴다.
    """
    # 🔴 **한글이 한 글자라도 있으면 MathJax 가 그 라벨을 조판하지 않는다** —
    #    TeX 글꼴에 글리프가 없어서다(`mathjaxLabel.ts` 의 `CJK_RE` 와 같은 규칙).
    #    그러면 지면을 그리는 것은 브라우저의 Batang 이므로 **MathJax 표를 대면
    #    엉뚱한 자로 재는 것**이다. 실측으로 `A반` 이 1.8단위 부풀어 상자그림이
    #    240 한계를 넘고 던졌다(2026-08-28). 그 라벨은 옛 실측 어림 그대로 잰다.
    #
    #    ⚠️ 「조판되나」의 판정이 여기와 `mathjaxLabel.ts` 두 곳에 있다. 한쪽만
    #       바꾸면 자와 그림이 갈라진다 — 바꿀 때는 둘 다 본다.
    table = _width_table()
    widths = table.get("widths")
    if not widths or any(ord(ch) >= 0x1100 for ch in text):
        scale = size / 13.0
        return scale * sum(
            HANGUL_W_13 if ord(ch) >= 0x1100 else ASCII_W_13 for ch in text
        )
    default = float(table.get("default", ASCII_W_13 / 13.0))
    ops = set(table.get("operators", ()))
    op_space = float(table.get("opSpace", 0.0))
    chars = list(text)
    total = 0.0
    for ch in chars:
        total += float(widths.get(ch, default))
    for i in range(1, len(chars) - 1):
        if chars[i] in ops:
            total += op_space
    return total * size * float(table.get("safety", 1.0))


_TEXT_TAG_RE = re.compile(r"<text\b([^>]*)>(.*?)</text>", re.S)


def _text_bboxes(body: str) -> list[tuple[float, float, float, float, str]]:
    """그려진 `<text>` 의 **경계 상자**들. `_body_bbox` 는 닻점만 세므로 여기가 그 몫이다.

    🔴 이것이 「그림이 잘린다」의 뿌리다 — `_svg` 는 글자를 **점 하나**로 보고
       viewBox 를 맞춘다(그 함수 위 `_GEOM_TAGS` 주석이 그렇게 적어 두었다).
       그래서 축 단위 이름표(`(점)`)가 프레임 밖으로 반쯤 나가도 **아무 에러가 안 난다**
       (원장님 지적 2026-08-25, `J30702-A03-002`·`A04-002`).

    폭은 `_label_w_max`(상한)를 쓴다 — 자리를 미리 빼는 부르는 쪽과 **같은 자**여야
    「부르는 쪽은 넉넉히 뺐는데 검사는 좁게 재서 통과」가 안 생긴다.
    """
    out: list[tuple[float, float, float, float, str]] = []
    for match in _TEXT_TAG_RE.finditer(body):
        attrs = dict(_ATTR_RE.findall(match.group(1)))
        text = re.sub(r"<[^>]+>", "", match.group(2))
        if not text.strip():
            continue
        size = float(attrs.get("font-size", 13.0))
        x = float(attrs.get("x", 0.0))
        y = float(attrs.get("y", 0.0))
        width = _label_w_max(text, size)
        anchor = attrs.get("text-anchor", "start")
        x0 = x - width if anchor == "end" else x - width / 2.0 if anchor == "middle" else x
        if attrs.get("dominant-baseline") in ("middle", "central"):
            y0, y1 = y - size * 0.56, y + size * 0.56
        else:
            y0, y1 = y - size * 0.85, y + size * 0.25
        out.append((x0, y0, x0 + width, y1, text))
    return out


def _arrow_down(x: float, y0: float, y1: float) -> str:
    return (
        f'<line x1="{_n(x)}" y1="{_n(y0)}" x2="{_n(x)}" y2="{_n(y1 - 4)}" '
        f'stroke="{INK}" stroke-width="1.2"/>'
        f'<polygon points="{_n(x - 3.5)},{_n(y1 - 6)} {_n(x + 3.5)},{_n(y1 - 6)} '
        f'{_n(x)},{_n(y1)}" fill="{INK}"/>'
    )


def _arrow_up(x: float, y_from: float, y_to: float) -> str:
    """아래 상자(y_from)에서 위 상자(y_to)로. 꼭짓점 y 가 더 작다."""
    return (
        f'<line x1="{_n(x)}" y1="{_n(y_from)}" x2="{_n(x)}" y2="{_n(y_to + 4)}" '
        f'stroke="{INK}" stroke-width="1.2"/>'
        f'<polygon points="{_n(x - 3.5)},{_n(y_to + 6)} {_n(x + 3.5)},{_n(y_to + 6)} '
        f'{_n(x)},{_n(y_to)}" fill="{INK}"/>'
    )


def _arrow_right(x0: float, x1: float, y: float) -> str:
    return (
        f'<line x1="{_n(x0)}" y1="{_n(y)}" x2="{_n(x1 - 4)}" y2="{_n(y)}" '
        f'stroke="{INK}" stroke-width="1.2"/>'
        f'<polygon points="{_n(x1 - 6)},{_n(y - 3.5)} {_n(x1 - 6)},{_n(y + 3.5)} '
        f'{_n(x1)},{_n(y)}" fill="{INK}"/>'
    )


def _length_mark(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    label: str,
    *,
    off: float = -10.0,
    fs: float = 11,
    t: float = 0.5,
) -> str:
    """길이 치수 — 도형 엔진 `measured()` 와 같다.

    점선(`6 4`)이 잰 두 점에 닿고, 라벨은 곡선 정점에서 흰 halo 로 배경 처리한다
    (`core.figure_svg.measured` / `dim_label`). 여기서 다시 그리지 않는다.
    t 는 선분 위 위치(0.5=중점). 교차점에 묻히면 밖으로 빼거나 t 를 옮긴다.
    """
    from core.figure_svg import measured

    return measured(x0, y0, x1, y1, off, str(label), fs=fs, t=t)


def _number_cards(spec: Mapping[str, Any]) -> str:
    cards = spec["cards"]
    if not isinstance(cards, list) or not cards:
        raise ValueError("cards 는 비어 있지 않은 배열이어야 합니다")
    w, h, gap = 36, 42, 10
    pad = 4
    total = pad * 2 + len(cards) * w + (len(cards) - 1) * gap
    parts = []
    x = pad
    for c in cards:
        parts.append(_rect(x, pad, w, h, rx=5, sw=1.6))
        parts.append(_text(x + w / 2, pad + h / 2, c, size=18))
        x += w + gap
    return _svg(total, h + pad * 2, "".join(parts))


def _place_value(spec: Mapping[str, Any]) -> str:
    counts = {
        "100": _count(spec["hundreds"]),
        "10": _count(spec["tens"]),
        "1": _count(spec["ones"]),
    }
    cw, ch, gap = 28, 22, 5
    rows = []
    y = 4
    max_w = 0
    for label, n in counts.items():
        x = 4
        row = []
        for _ in range(n):
            row.append(_rect(x, y, cw, ch, rx=3, sw=1.2))
            row.append(_text(x + cw / 2, y + ch / 2, label, size=10))
            x += cw + gap
        max_w = max(max_w, x)
        rows.extend(row)
        y += ch + gap
    return _svg(max(max_w, 40), y, "".join(rows))


def _count(v: Any) -> int:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError("개수는 정수여야 합니다")
    n = int(v)
    if n < 0 or n > 20:
        raise ValueError("개수는 0 이상 20 이하여야 합니다")
    return n


def _hundred_grid(x: float, y: float, cell: float = 2.2) -> str:
    s = cell * 10
    parts = [_rect(x, y, s, s, sw=1.1, fill=FAINT)]
    for i in range(11):
        d = i * cell
        parts.append(
            f'<line x1="{_n(x + d)}" y1="{_n(y)}" x2="{_n(x + d)}" y2="{_n(y + s)}" '
            f'stroke="{INK}" stroke-width="0.5"/>'
        )
        parts.append(
            f'<line x1="{_n(x)}" y1="{_n(y + d)}" x2="{_n(x + s)}" y2="{_n(y + d)}" '
            f'stroke="{INK}" stroke-width="0.5"/>'
        )
    return "".join(parts)


def _ten_rod(x: float, y: float, cell: float = 2.2) -> str:
    return _rect(x, y, cell, cell * 10, sw=1.0, fill=FAINT)


def _one(x: float, y: float, cell: float = 2.2) -> str:
    return _rect(x, y, cell, cell, sw=0.9, fill=FAINT)


def _base10(spec: Mapping[str, Any]) -> str:
    rows = spec["rows"]
    if not isinstance(rows, list) or not rows:
        raise ValueError("rows 는 비어 있지 않은 배열이어야 합니다")
    cell = 2.4
    pad = 8
    row_h = cell * 10 + 12
    boxes: list[str] = []
    bits: list[str] = []
    y = pad
    width = 120.0
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("rows 항목은 객체여야 합니다")
        h = _count(row.get("hundreds", 0))
        t = _count(row.get("tens", 0))
        o = _count(row.get("ones", 0))
        x = pad + 10
        gy = y + 6
        for _ in range(h):
            bits.append(_hundred_grid(x, gy, cell))
            x += cell * 10 + 6
        x += 4
        for _ in range(t):
            bits.append(_ten_rod(x, gy, cell))
            x += cell + 4
        x += 6
        for i in range(o):
            bits.append(_one(x, gy + i * (cell + 2), cell))
        width = max(width, x + 18)
        boxes.append(_rect(pad, y, width - pad, row_h, rx=6, sw=1.2, fill=PAPER))
        y += row_h + 8
    # 상자 폭을 최종 width 에 맞춘다 — 행마다 다시 그린다.
    y = pad
    boxes = []
    for _row in rows:
        boxes.append(_rect(pad, y, width - pad, row_h, rx=6, sw=1.2, fill=PAPER))
        y += row_h + 8
    parts = boxes + bits
    eq = spec.get("equation")
    if eq:
        parts.append(_text(width / 2, y + 10, eq, size=14))
        y += 24
    return _svg(width + pad, y + pad, "".join(parts))


def _op_box(spec: Mapping[str, Any]) -> str:
    inp = spec["input"]
    op = spec["op"]
    w, cx = 140, 70
    op_s = str(op)
    # 숫자만 감싼다. 예전 100×36 막대는 발문 대비 쓸데없이 컸다.
    pw = min(64.0, max(48.0, 9.0 * len(op_s) + 20))
    ph = 22.0
    px = cx - pw / 2
    ew, eh = 36.0, 18.0
    parts = [
        _text(cx, 13, inp, size=14),
        _arrow_down(cx, 22, 34),
        _rect(px, 34, pw, ph, rx=ph / 2, fill="#f3e6e4", sw=1.3, stroke="#b45a55"),
        _text(cx, 34 + ph / 2, op, size=14),
        _arrow_down(cx, 34 + ph, 70),
        _rect(cx - ew / 2, 70, ew, eh, rx=3, sw=1.2),
    ]
    return _svg(w, 70 + eh + 8, "".join(parts))


def _sum_box(spec: Mapping[str, Any]) -> str:
    left, right = spec["left"], spec["right"]
    cw, ch = 70, 28
    parts = [
        _rect(2, 2, cw, ch, sw=1.3, fill="#d7e4df"),
        _rect(2 + cw, 2, cw, ch, sw=1.3, fill="#d7e4df"),
        _rect(2, 2 + ch, cw * 2, ch + 6, sw=1.3),
        _text(2 + cw / 2, 2 + ch / 2, left, size=15),
        _text(2 + cw + cw / 2, 2 + ch / 2, right, size=15),
    ]
    return _svg(cw * 2 + 4, ch * 2 + 10, "".join(parts))


def _op_arch(x0: float, y0: float, x1: float, y1: float) -> str:
    """상자 위 → 타원 아래, 또는 타원 아래 → 상자 위. 끝점에서 수직."""
    dy = abs(y1 - y0) * 0.55
    c1y = y0 + (dy if y1 > y0 else -dy)
    c2y = y1 + (dy if y0 > y1 else -dy)
    return (
        f'<path d="M{_n(x0)} {_n(y0)} C{_n(x0)} {_n(c1y)} {_n(x1)} {_n(c2y)} '
        f'{_n(x1)} {_n(y1)}" fill="none" stroke="{INK}" stroke-width="1.2"/>'
    )


def _op_tree(spec: Mapping[str, Any]) -> str:
    ops = spec["ops"]
    if not isinstance(ops, list) or len(ops) != 2:
        raise ValueError("ops 는 길이 2 배열이어야 합니다")
    start = spec["start"]
    bw, bh, gap, pad = 60, 32, 52, 10
    oval_rx, oval_ry = 32, 15
    n = 3
    box_y = pad + oval_ry * 2 + 30
    xs = [pad + i * (bw + gap) for i in range(n)]
    parts: list[str] = []
    labels = [start, "", ""]
    for i, label in enumerate(labels):
        filled = bool(label)
        parts.append(
            _rect(
                xs[i],
                box_y,
                bw,
                bh,
                rx=5,
                fill="#f3ead4" if filled else PAPER,
                sw=1.3,
            )
        )
        if label:
            parts.append(_text(xs[i] + bw / 2, box_y + bh / 2, label, size=14))
    for i, op in enumerate(ops):
        left = xs[i] + bw / 2
        right = xs[i + 1] + bw / 2
        cx = (left + right) / 2
        cy = pad + oval_ry
        oval_bottom = cy + oval_ry
        parts.append(
            f'<ellipse cx="{_n(cx)}" cy="{_n(cy)}" rx="{_n(oval_rx)}" '
            f'ry="{_n(oval_ry)}" fill="#f3ead4" stroke="{INK}" stroke-width="1.2"/>'
        )
        parts.append(_text(cx, cy, op, size=12))
        parts.append(_op_arch(left, box_y, cx, oval_bottom))
        tip = box_y - 2
        parts.append(_op_arch(cx, oval_bottom, right, tip - 6))
        parts.append(
            f'<polygon points="{_n(right - 3.5)},{_n(tip - 6)} {_n(right + 3.5)},'
            f'{_n(tip - 6)} {_n(right)},{_n(tip)}" fill="{INK}"/>'
        )
    width = pad * 2 + n * bw + (n - 1) * gap
    height = box_y + bh + pad
    return _svg(width, height, "".join(parts))


def _box_chain(spec: Mapping[str, Any]) -> str:
    steps = spec["steps"]
    if not isinstance(steps, list) or not steps:
        raise ValueError("steps 는 비어 있지 않은 배열이어야 합니다")
    start = spec["start"]
    n = len(steps)
    bw, bh = 58, 30
    gap_x, gap_y = 24, 24
    pad = 10

    def xy(col: int, row: int) -> tuple[float, float]:
        return pad + col * (bw + gap_x), pad + (n - row) * (bh + gap_y)

    parts: list[str] = []

    def cell(col: int, row: int, label: str | None) -> None:
        x, y = xy(col, row)
        filled = label is not None
        parts.append(
            _rect(
                x,
                y,
                bw,
                bh,
                rx=5,
                fill="#f3ead4" if filled else PAPER,
                sw=1.3,
            )
        )
        if label:
            parts.append(_text(x + bw / 2, y + bh / 2, label, size=13))

    def right(col: int, row: int) -> None:
        x0, y0 = xy(col, row)
        x1, _ = xy(col + 1, row)
        parts.append(_arrow_right(x0 + bw, x1, y0 + bh / 2))

    def up(col: int, row: int) -> None:
        x0, y_low = xy(col, row)
        _, y_up = xy(col, row + 1)
        parts.append(_arrow_up(x0 + bw / 2, y_low, y_up + bh))

    cell(0, 0, str(start))
    right(0, 0)
    for i, step in enumerate(steps):
        cell(i + 1, i, str(step))
        cell(i + 1, i + 1, None)
        up(i + 1, i)
        if i + 1 < n:
            right(i + 1, i + 1)
    cols = n + 1
    rows = n + 1
    width = pad * 2 + cols * bw + (cols - 1) * gap_x
    height = pad * 2 + rows * bh + (rows - 1) * gap_y
    return _svg(width, height, "".join(parts))


def _column_op(spec: Mapping[str, Any]) -> str:
    top, bottom = str(spec["top"]), str(spec["bottom"])
    op = str(spec["op"])
    result = spec.get("result")
    result_s = None if result is None else str(result)
    hi = spec.get("highlight")
    # 자릿수와 무관하게 같은 viewBox·같은 글자 크기. 칸만 4자리로 고정한다.
    slots = 4
    dw, dh = 18.0, 22.0
    box_pad = 12.0
    x0 = box_pad + 22
    y_top = box_pad + 8
    inner_w = x0 + slots * dw + 10
    inner_h = box_pad * 2 + dh * 3 + 16
    parts = [_rect(6, 6, inner_w - 12, inner_h - 12, rx=6, sw=1.2)]

    def digits(s: str, y: float, key: str) -> None:
        raw = s
        s = s.rjust(slots)
        shift = slots - len(raw)
        for i, ch in enumerate(s):
            if ch == " ":
                continue
            cx = x0 + i * dw + dw / 2
            if hi == f"{key}{i - shift}":
                bs = 15.0
                parts.append(
                    _rect(cx - bs / 2, y - bs / 2, bs, bs, rx=1.5, sw=1.1, stroke="#b45a55")
                )
            parts.append(
                f'<text x="{_n(cx)}" y="{_n(y)}" fill="{INK}" font-size="15" '
                f'font-family="Batang, serif" font-weight="700" text-anchor="middle" '
                f'dominant-baseline="central">{_esc(ch)}</text>'
            )

    digits(top, y_top + 8, "t")
    parts.append(_text(x0 - 12, y_top + dh + 8, op, size=15))
    digits(bottom, y_top + dh + 8, "b")
    y_line = y_top + dh * 2 + 2
    parts.append(
        f'<line x1="{_n(x0 - 16)}" y1="{_n(y_line)}" x2="{_n(x0 + slots * dw)}" '
        f'y2="{_n(y_line)}" stroke="{INK}" stroke-width="1.3"/>'
    )
    if result_s:
        digits(result_s, y_line + 16, "r")
    else:
        parts.append(_rect(x0, y_line + 6, slots * dw, 18, rx=2, sw=1.1))
    return _svg(inner_w, inner_h, "".join(parts))


def _fmt_tick(v: float) -> str:
    if abs(v - round(v)) < 1e-8:
        return str(int(round(v)))
    return f"{v:.4f}".rstrip("0").rstrip(".")


def _number_line(spec: Mapping[str, Any]) -> str:
    lo = float(spec.get("min", 0))
    hi = float(spec["max"])
    step = float(spec.get("step", 5))
    tick = float(spec.get("tick", 1))
    hops = spec.get("hops") or []
    blanks = spec.get("blanks") or []
    if hi <= lo:
        raise ValueError("max 는 min 보다 커야 합니다")
    if tick <= 0 or step <= 0:
        raise ValueError("step·tick 은 양수여야 합니다")
    blank_vals = []
    if not isinstance(blanks, list):
        raise ValueError("blanks 는 배열이어야 합니다")
    for item in blanks:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError("blanks 항목은 수여야 합니다")
        blank_vals.append(float(item))
    pad, y = 16.0, 48.0
    span = 220.0
    x0 = pad + 8

    def xp(v: float) -> float:
        return x0 + (v - lo) / (hi - lo) * span

    def on_step(v: float) -> bool:
        q = (v - lo) / step
        return abs(q - round(q)) < 1e-6

    def is_blank(v: float) -> bool:
        return any(abs(v - b) < 1e-6 for b in blank_vals)

    parts = [
        f'<line x1="{_n(xp(lo))}" y1="{_n(y)}" x2="{_n(xp(hi))}" y2="{_n(y)}" '
        f'stroke="{INK}" stroke-width="1.4"/>'
    ]
    v = lo
    n_ticks = 0
    while v <= hi + 1e-8:
        x = xp(v)
        parts.append(
            f'<line x1="{_n(x)}" y1="{_n(y - 5)}" x2="{_n(x)}" y2="{_n(y + 5)}" '
            f'stroke="{INK}" stroke-width="1.1"/>'
        )
        if is_blank(v):
            parts.append(_rect(x - 8, y + 10, 16, 14, rx=2, sw=1.05))
        elif on_step(v):
            parts.append(_text(x, y + 16, _fmt_tick(v), size=11, weight="600"))
        n_ticks += 1
        if n_ticks > 40:
            raise ValueError("눈금이 너무 많습니다")
        v += tick
    if isinstance(hops, list):
        for a, b in hops:
            xa, xb = xp(float(a)), xp(float(b))
            mx = (xa + xb) / 2
            parts.append(
                f'<path d="M{_n(xa)} {_n(y - 2)} Q{_n(mx)} {_n(y - 22)} {_n(xb)} {_n(y - 2)}" '
                f'fill="none" stroke="{INK}" stroke-width="1.1" stroke-dasharray="3 2"/>'
            )
    bar_to = spec.get("barTo")
    if bar_to is not None:
        x1 = xp(float(bar_to))
        parts.append(_rect(xp(lo), y - 28, x1 - xp(lo), 12, rx=2, fill="#e8d3a8", sw=1.1))
    return _svg(span + pad * 2 + 16, 78, "".join(parts))


def _clock_face(cx: float, cy: float, r: float, hour: int, minute: int, second: int | None) -> str:
    parts = [
        f'<circle cx="{_n(cx)}" cy="{_n(cy)}" r="{_n(r)}" fill="{PAPER}" '
        f'stroke="{INK}" stroke-width="2"/>',
        f'<circle cx="{_n(cx)}" cy="{_n(cy)}" r="{_n(r + 4)}" fill="none" '
        f'stroke="#7a9e86" stroke-width="5"/>',
    ]
    for i in range(12):
        ang = math.radians(i * 30 - 90)
        inner, outer = r - 7, r - 2
        parts.append(
            f'<line x1="{_n(cx + inner * math.cos(ang))}" y1="{_n(cy + inner * math.sin(ang))}" '
            f'x2="{_n(cx + outer * math.cos(ang))}" y2="{_n(cy + outer * math.sin(ang))}" '
            f'stroke="{INK}" stroke-width="1.2"/>'
        )
        lab = 12 if i == 0 else i
        lx = cx + (r - 14) * math.cos(ang)
        ly = cy + (r - 14) * math.sin(ang)
        parts.append(_text(lx, ly, lab, size=8, weight="600"))

    def hand(deg: float, length: float, sw: float, color: str) -> str:
        ang = math.radians(deg - 90)
        return (
            f'<line x1="{_n(cx)}" y1="{_n(cy)}" x2="{_n(cx + length * math.cos(ang))}" '
            f'y2="{_n(cy + length * math.sin(ang))}" stroke="{color}" stroke-width="{_n(sw)}" '
            f'stroke-linecap="round"/>'
        )

    h = hour % 12
    m = minute
    parts.append(hand(30 * h + 0.5 * m, r * 0.45, 2.4, INK))
    parts.append(hand(6 * m, r * 0.68, 1.8, INK))
    if second is not None:
        parts.append(hand(6 * second, r * 0.72, 1.0, "#c04545"))
    parts.append(f'<circle cx="{_n(cx)}" cy="{_n(cy)}" r="2.2" fill="{INK}"/>')
    return "".join(parts)


def _clocks(spec: Mapping[str, Any]) -> str:
    items = spec["items"]
    if not isinstance(items, list) or not items:
        raise ValueError("items 는 비어 있지 않은 배열이어야 합니다")
    r, gap, pad = 42.0, 28.0, 12.0
    parts: list[str] = []
    for i, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise ValueError("clocks items 는 객체여야 합니다")
        cx = pad + r + 8 + i * (2 * r + gap + 16)
        cy = pad + r + 22
        lab = item.get("label")
        if lab:
            parts.append(_text(cx, pad + 8, lab, size=11, weight="600"))
        parts.append(
            _clock_face(
                cx,
                cy,
                r,
                int(item["hour"]),
                int(item["minute"]),
                None if item.get("second") is None else int(item["second"]),
            )
        )
        if i + 1 < len(items):
            mx = cx + r + gap / 2 + 4
            parts.append(_text(mx, cy, "→", size=14))
    n = len(items)
    width = pad * 2 + n * (2 * r + 16) + (n - 1) * gap
    return _svg(width, pad + 2 * r + 36, "".join(parts))


# 표 칸의 좌우 여백(한쪽). 글자와 세로줄 사이 최소 틈.
TABLE_CELL_PAD = 5.0
# 열 최소 폭. 숫자 한 칸짜리 열이 실보다 좁아지지 않게.
TABLE_MIN_CW = 24.0


def _table_widths(cells_by_col: list[list[str]], fs: float, usable: float, base: float) -> list[float]:
    """열 폭을 **내용에 비례해** 나눈다. 못 담으면 **던진다** (D-70).

    옛 규칙은 `cw = min(56, usable/cols)` 균등이었다. 그러면 「10이상~20미만」 같은
    8자 계급 라벨이 든 열과 「5」 한 자짜리 도수 열이 **같은 폭**이라 긴 쪽 첫 글자가
    열 밖으로 나갔다(실렌더 확인, `C:/tmp/wave3-probe.png`). 잘린 그림은 지면에서
    티가 안 나고 에러도 안 난다 — 그래서 **조용히 자르지 않고 던진다.**

    ## 총 폭은 «오늘의 지면»을 바닥으로 깐다

    `base`(= 옛 규칙이 내던 총 폭) 보다 **모자라면 base 를 그대로 쓰고 배분만 바꾼다.**
    그래야 지금 잘 나오는 표가 **viewBox 폭이 한 단위도 안 바뀐다** — 폭 하나로 지면
    등급(140/240px)이 갈리므로, 안 그러면 멀쩡한 표의 글자 크기까지 같이 뒤집힌다
    (CLAUDE.md 2026-08-23). 필요 폭이 base 를 넘을 때에만 넓히고, 상한(`usable`)을
    넘으면 던진다.
    """
    need = [
        max(TABLE_MIN_CW, max(_label_w_max(c, fs) for c in col) + TABLE_CELL_PAD * 2)
        for col in cells_by_col
    ]
    total_need = sum(need)
    if total_need > usable:
        widest = max(range(len(need)), key=lambda i: need[i])
        raise ValueError(
            f"표가 지면 폭을 넘습니다 (필요 {total_need:.0f} > {usable:.0f}단위, "
            f"가장 넓은 열 {widest + 1}번 {need[widest]:.0f}). 라벨을 줄이거나 열을 나누십시오"
        )
    total = max(base, total_need)
    return [w * total / total_need for w in need]


def _table_align(spec: Mapping[str, Any], cols: int) -> list[str]:
    """칸 정렬. 문자열이면 모든 열에, 배열이면 열마다.

    줄기와 잎 그림은 **잎이 왼쪽 정렬**이라야 자릿수가 세로로 맞는다 — 가운데 정렬이면
    행마다 잎의 시작 x 가 달라져 「몇 번째 잎인가」를 셀 수 없다.
    """
    raw = spec.get("align", "center")
    vals = raw if isinstance(raw, list) else [raw] * cols
    if len(vals) != cols:
        raise ValueError(f"align 배열은 열 수({cols})와 같아야 합니다")
    for v in vals:
        if v not in ("center", "left"):
            raise ValueError('align 은 "center" 또는 "left" 여야 합니다')
    return list(vals)


def _table(spec: Mapping[str, Any]) -> str:
    headers = spec["headers"]
    rows = spec["rows"]
    if not isinstance(headers, list) or not isinstance(rows, list):
        raise ValueError("headers 와 rows 는 배열이어야 합니다")
    cols = len(headers)
    if cols < 1:
        raise ValueError("headers 는 비어 있지 않아야 합니다")
    for row in rows:
        if not isinstance(row, list) or len(row) != cols:
            raise ValueError("행 칸 수가 머리와 같아야 합니다")
    align = _table_align(spec, cols)
    pad, rh = 8.0, 24.0
    usable = TABLE_VIEWBOX_MAX - pad * 2
    # 옛 균등 규칙이 내던 총 폭 — 이보다 좁히지 않는다(지금 지면을 그대로 둔다).
    base = min(56.0, usable / cols) * cols
    cells_by_col = [
        [str(headers[i])] + [str(row[i]) for row in rows] for i in range(cols)
    ]
    widths = _table_widths(cells_by_col, 13.0, usable, base)
    # 글자 크기는 **가장 좁은 열**이 정한다 — 균등이던 시절과 같은 규칙이라
    # 폭이 안 바뀐 표는 크기도 그대로다.
    fs = 13 if min(widths) >= 36 else 12
    xs = [pad]
    for w in widths:
        xs.append(xs[-1] + w)
    total_w = xs[-1] - pad

    def cell_x(i: int) -> tuple[float, str]:
        return (
            (xs[i] + TABLE_CELL_PAD, "start")
            if align[i] == "left"
            else (xs[i] + widths[i] / 2, "middle")
        )

    parts = [
        _rect(pad, pad, total_w, rh, sw=1.2, fill="#d7e0e8"),
    ]
    for i, h in enumerate(headers):
        parts.append(_text(xs[i] + widths[i] / 2, pad + rh / 2, h, size=fs))
        if i:
            x = xs[i]
            parts.append(
                f'<line x1="{_n(x)}" y1="{_n(pad)}" x2="{_n(x)}" y2="{_n(pad + rh * (1 + len(rows)))}" '
                f'stroke="{INK}" stroke-width="1"/>'
            )
    for r, row in enumerate(rows):
        y = pad + rh * (r + 1)
        parts.append(_rect(pad, y, total_w, rh, sw=1.2))
        for i, cell in enumerate(row):
            cx, anchor = cell_x(i)
            parts.append(
                _text(cx, y + rh / 2, cell, size=fs, anchor=anchor, weight="600")
            )
    return _svg(pad * 2 + total_w, pad * 2 + rh * (1 + len(rows)), "".join(parts))


def _tape(spec: Mapping[str, Any]) -> str:
    length = float(spec["length"])
    label = str(spec["label"])
    segs = int(spec.get("segments", 1))
    w, h, pad = 200.0, 18.0, 16.0
    bar_y = 26.0
    parts = [
        _rect(pad, bar_y, w, h, rx=2, fill="#e8d3a8", sw=1.2),
        _length_mark(pad, bar_y, pad + w, bar_y, label),
    ]
    if segs > 1:
        for i in range(1, segs):
            x = pad + w * i / segs
            parts.append(
                f'<line x1="{_n(x)}" y1="{_n(bar_y)}" x2="{_n(x)}" y2="{_n(bar_y + h)}" '
                f'stroke="{INK}" stroke-width="1"/>'
            )
    return _svg(w + pad * 2, bar_y + h + 8, "".join(parts))


def _dot_grid(spec: Mapping[str, Any]) -> str:
    rows, cols = int(spec["rows"]), int(spec["cols"])
    if rows < 1 or cols < 1 or rows > 12 or cols > 12:
        raise ValueError("rows·cols 는 1 이상 12 이하여야 합니다")
    gap, r, pad = 16.0, 5.0, 10.0
    parts = []
    for y in range(rows):
        for x in range(cols):
            cx = pad + r + x * gap
            cy = pad + r + y * gap
            parts.append(
                f'<circle cx="{_n(cx)}" cy="{_n(cy)}" r="{_n(r)}" fill="#c4a574" '
                f'stroke="{INK}" stroke-width="0.8"/>'
            )
    return _svg(pad * 2 + (cols - 1) * gap + r * 2, pad * 2 + (rows - 1) * gap + r * 2, "".join(parts))


def _boxed_list(spec: Mapping[str, Any]) -> str:
    items = spec["items"]
    if not isinstance(items, list) or not items:
        raise ValueError("items 는 비어 있지 않은 배열이어야 합니다")
    marks = spec.get("marks") or [f"{i + 1}" for i in range(len(items))]
    pad, rh, w = 10.0, 22.0, 200.0
    parts = [_rect(pad, pad, w, rh * len(items) + 10, rx=4, sw=1.3)]
    for i, item in enumerate(items):
        y = pad + 8 + i * rh
        label = f"{marks[i]}  {item}".strip() if str(marks[i]).strip() else str(item)
        parts.append(_text(pad + 16, y + 8, label, size=12, anchor="start", weight="600"))
    return _svg(w + pad * 2, rh * len(items) + pad * 2 + 8, "".join(parts))


def _pills(spec: Mapping[str, Any]) -> str:
    items = spec["items"]
    if not isinstance(items, list) or len(items) < 2:
        raise ValueError("items 는 2개 이상이어야 합니다")
    bw, bh, gap, pad = 88.0, 28.0, 26.0, 10.0
    parts: list[str] = []
    for i, item in enumerate(items):
        x = pad + i * (bw + gap)
        parts.append(_rect(x, pad, bw, bh, rx=6, fill="#e4eee6", sw=1.2))
        parts.append(_text(x + bw / 2, pad + bh / 2, item, size=12))
        if i + 1 < len(items):
            parts.append(_arrow_right(x + bw, x + bw + gap, pad + bh / 2))
    n = len(items)
    return _svg(pad * 2 + n * bw + (n - 1) * gap, pad * 2 + bh, "".join(parts))


def _geo_line(_spec: Mapping[str, Any]) -> str:
    y, x0, x1 = 36.0, 18.0, 200.0
    parts = [
        f'<line x1="{_n(x0)}" y1="{_n(y)}" x2="{_n(x1)}" y2="{_n(y)}" '
        f'stroke="{INK}" stroke-width="1.6"/>',
        f'<polygon points="{_n(x0)},{_n(y)} {_n(x0 + 10)},{_n(y - 4)} {_n(x0 + 10)},{_n(y + 4)}" fill="{INK}"/>',
        f'<polygon points="{_n(x1)},{_n(y)} {_n(x1 - 10)},{_n(y - 4)} {_n(x1 - 10)},{_n(y + 4)}" fill="{INK}"/>',
        f'<circle cx="70" cy="{_n(y)}" r="2.4" fill="{INK}"/>',
        f'<circle cx="148" cy="{_n(y)}" r="2.4" fill="{INK}"/>',
    ]
    return _svg(220, 56, "".join(parts))


def _angle_pick(_spec: Mapping[str, Any]) -> str:
    """원본 50쪽 03: L · 만나지 않는 두 선 · 각 · 곡선."""
    parts: list[str] = []
    # L
    parts += [
        f'<polyline points="16,70 16,30 56,30" fill="none" stroke="{INK}" stroke-width="1.6"/>',
    ]
    # 두 선 (각 아님)
    parts += [
        f'<line x1="78" y1="28" x2="98" y2="70" stroke="{INK}" stroke-width="1.6"/>',
        f'<line x1="108" y1="70" x2="128" y2="28" stroke="{INK}" stroke-width="1.6"/>',
    ]
    # >
    parts += [
        f'<polyline points="150,28 178,50 150,72" fill="none" stroke="{INK}" stroke-width="1.6"/>',
    ]
    # 곡선
    parts.append(
        f'<path d="M200 70 Q214 20 228 70" fill="none" stroke="{INK}" stroke-width="1.6"/>'
    )
    return _svg(244, 88, "".join(parts))


def _time_add(spec: Mapping[str, Any]) -> str:
    start, add = spec["start"], spec["add"]
    if not isinstance(start, Mapping) or not isinstance(add, Mapping):
        raise ValueError("start 와 add 는 객체여야 합니다")

    def cell(v: Any, blank: bool) -> str:
        return "" if blank or v is None else str(v)

    rows = [
        (cell(start.get("h"), False), cell(start.get("m"), False), cell(start.get("s"), False), False),
        (cell(add.get("h"), False), cell(add.get("m"), False), cell(add.get("s"), False), False),
        ("", "", "", True),
    ]
    units = ["시", "분", "초"]
    cw, rh, pad = 48.0, 22.0, 12.0
    parts = [_text(pad + cw * i + cw / 2, 10, u, size=11, weight="600") for i, u in enumerate(units)]
    y0 = 18.0
    for r, (a, b, c, blank) in enumerate(rows):
        y = y0 + r * rh
        vals = [a, b, c]
        if r == 1:
            parts.append(_text(pad - 2, y + rh / 2, "+", size=14, anchor="end"))
        for i, v in enumerate(vals):
            x = pad + i * cw
            if blank:
                parts.append(_rect(x + 6, y + 2, cw - 12, rh - 4, rx=2, sw=1.1))
            else:
                parts.append(_text(x + cw / 2, y + rh / 2, v, size=13))
        if r == 1:
            parts.append(
                f'<line x1="{_n(pad)}" y1="{_n(y + rh)}" x2="{_n(pad + 3 * cw)}" '
                f'y2="{_n(y + rh)}" stroke="{INK}" stroke-width="1.3"/>'
            )
    return _svg(pad * 2 + 3 * cw, y0 + 3 * rh + 8, "".join(parts))


def _grid_xy(c: float, r: float, pad: float, cell: float) -> tuple[float, float]:
    return pad + c * cell, pad + r * cell


def _pair_cr(value: Any, path: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{path} 는 [열, 행] 이어야 합니다")
    if isinstance(value[0], bool) or isinstance(value[1], bool):
        raise ValueError(f"{path} 좌표는 수여야 합니다")
    if not isinstance(value[0], (int, float)) or not isinstance(value[1], (int, float)):
        raise ValueError(f"{path} 좌표는 수여야 합니다")
    return float(value[0]), float(value[1])


def _point_grid(spec: Mapping[str, Any]) -> str:
    cols, rows = int(spec["cols"]), int(spec["rows"])
    if cols < 1 or cols > 10 or rows < 1 or rows > 10:
        raise ValueError("cols·rows 는 1 이상 10 이하여야 합니다")
    dots = spec["dots"]
    if not isinstance(dots, list) or not dots:
        raise ValueError("dots 는 비어 있지 않은 배열이어야 합니다")
    cell, pad = 22.0, 18.0
    parts: list[str] = []
    for i in range(cols + 1):
        x0, y0 = _grid_xy(i, 0, pad, cell)
        x1, y1 = _grid_xy(i, rows, pad, cell)
        parts.append(
            f'<line x1="{_n(x0)}" y1="{_n(y0)}" x2="{_n(x1)}" y2="{_n(y1)}" '
            f'stroke="{GRID}" stroke-width="{_n(GRID_SW)}" stroke-dasharray="4 3"/>'
        )
    for j in range(rows + 1):
        x0, y0 = _grid_xy(0, j, pad, cell)
        x1, y1 = _grid_xy(cols, j, pad, cell)
        parts.append(
            f'<line x1="{_n(x0)}" y1="{_n(y0)}" x2="{_n(x1)}" y2="{_n(y1)}" '
            f'stroke="{GRID}" stroke-width="{_n(GRID_SW)}" stroke-dasharray="4 3"/>'
        )
    for i, line in enumerate(spec.get("lines") or []):
        if not isinstance(line, list) or len(line) != 2:
            raise ValueError("lines 항목은 두 점이어야 합니다")
        c0, r0 = _pair_cr(line[0], f"lines[{i}][0]")
        c1, r1 = _pair_cr(line[1], f"lines[{i}][1]")
        x0, y0 = _grid_xy(c0, r0, pad, cell)
        x1, y1 = _grid_xy(c1, r1, pad, cell)
        parts.append(
            f'<line x1="{_n(x0)}" y1="{_n(y0)}" x2="{_n(x1)}" y2="{_n(y1)}" '
            f'stroke="{INK}" stroke-width="1.6"/>'
        )
    square = spec.get("square")
    if square is not None:
        if not isinstance(square, Mapping):
            raise ValueError("square 는 객체여야 합니다")
        sc, sr = float(square["c"]), float(square["r"])
        dx, dy = float(square["dx"]), float(square["dy"])
        sx = -1.0 if dx < 0 else 1.0
        sy = -1.0 if dy < 0 else 1.0
        x, y = _grid_xy(sc, sr, pad, cell)
        s = 7.0
        parts.append(
            f'<polyline points="{_n(x + s * sx)},{_n(y)} {_n(x + s * sx)},{_n(y + s * sy)} '
            f'{_n(x)},{_n(y + s * sy)}" fill="none" stroke="{INK}" stroke-width="1.2"/>'
        )
    side_off = {
        "up": (0.0, -10.0),
        "down": (0.0, 11.0),
        "left": (-11.0, 0.0),
        "right": (11.0, 0.0),
    }
    for i, dot in enumerate(dots):
        if not isinstance(dot, Mapping):
            raise ValueError("dots 항목은 객체여야 합니다")
        c, r = float(dot["c"]), float(dot["r"])
        label = str(dot["label"])
        x, y = _grid_xy(c, r, pad, cell)
        parts.append(f'<circle cx="{_n(x)}" cy="{_n(y)}" r="2.5" fill="{INK}"/>')
        side = str(dot.get("side") or "up")
        if side not in side_off:
            raise ValueError(f"dots[{i}].side 는 up·down·left·right 여야 합니다")
        ox, oy = side_off[side]
        parts.append(_text(x + ox, y + oy, label, size=11, weight="700"))
    return _svg(pad * 2 + cols * cell, pad * 2 + rows * cell, "".join(parts))


def _divide_triangle(spec: Mapping[str, Any]) -> str:
    n = spec["n"]
    if isinstance(n, bool) or not isinstance(n, (int, float)) or int(n) != n:
        raise ValueError("n 은 정수여야 합니다")
    n = int(n)
    if n < 2 or n > 12:
        raise ValueError("n 은 2 이상 12 이하여야 합니다")
    bw, bh = 36.0, 22.0
    parts = [
        _rect(8, 48, bw, bh, rx=6, fill="#f4ead8", sw=1.1, stroke="#c4a574"),
        _text(8 + bw / 2, 48 + bh / 2, n, size=14),
        _arrow_right(8 + bw, 56, 59),
    ]
    ax, ay = 72.0, 18.0
    bx, by = 72.0, 110.0
    cx, cy = 168.0, 110.0
    parts.append(
        f'<polygon points="{_n(ax)},{_n(ay)} {_n(bx)},{_n(by)} {_n(cx)},{_n(cy)}" '
        f'fill="#c5d6c2" stroke="{INK}" stroke-width="1.5"/>'
    )
    mx, my = ax, (ay + by) / 2
    px, py = ax + 48.0, my
    qx, qy = px, by
    parts.append(
        f'<line x1="{_n(mx)}" y1="{_n(my)}" x2="{_n(px)}" y2="{_n(py)}" '
        f'stroke="{INK}" stroke-width="1.15" stroke-dasharray="5 4"/>'
    )
    parts.append(
        f'<line x1="{_n(px)}" y1="{_n(py)}" x2="{_n(qx)}" y2="{_n(qy)}" '
        f'stroke="{INK}" stroke-width="1.15" stroke-dasharray="5 4"/>'
    )
    return _svg(180, 124, "".join(parts))


def _frac_filled(filled: Any, n: int) -> set[int]:
    if isinstance(filled, bool) or (
        not isinstance(filled, (int, float, list))
    ):
        raise ValueError("filled 는 개수 또는 조각 번호 배열이어야 합니다")
    if isinstance(filled, (int, float)):
        if int(filled) != filled:
            raise ValueError("filled 개수는 정수여야 합니다")
        count = int(filled)
        if count < 0 or count > n:
            raise ValueError("filled 개수는 0 이상 n 이하여야 합니다")
        return set(range(count))
    out: set[int] = set()
    for item in filled:
        if isinstance(item, bool) or not isinstance(item, (int, float)) or int(item) != item:
            raise ValueError("filled 조각 번호는 정수여야 합니다")
        idx = int(item)
        if idx < 0 or idx >= n:
            raise ValueError("filled 조각 번호는 0 이상 n 미만이어야 합니다")
        out.add(idx)
    return out


def _frac_pie(spec: Mapping[str, Any]) -> str:
    n = spec["n"]
    if isinstance(n, bool) or not isinstance(n, (int, float)) or int(n) != n:
        raise ValueError("n 은 정수여야 합니다")
    n = int(n)
    if n < 2 or n > 16:
        raise ValueError("n 은 2 이상 16 이하여야 합니다")
    filled = _frac_filled(spec["filled"], n)
    start = float(spec.get("start", -90))
    r, pad = 48.0, 8.0
    cx = cy = pad + r
    step = 360.0 / n
    leftover, eaten = str(spec.get("fill") or "#e2b48a"), "#f4efe6"
    parts: list[str] = []
    for i in range(n):
        a0 = math.radians(start + i * step)
        a1 = math.radians(start + (i + 1) * step)
        x0, y0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
        x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
        fill = leftover if i in filled else eaten
        parts.append(
            f'<path d="M{_n(cx)} {_n(cy)} L{_n(x0)} {_n(y0)} '
            f'A{_n(r)} {_n(r)} 0 0 1 {_n(x1)} {_n(y1)} Z" '
            f'fill="{fill}" stroke="none"/>'
        )
    for i in range(n):
        ang = math.radians(start + i * step)
        x1, y1 = cx + r * math.cos(ang), cy + r * math.sin(ang)
        parts.append(
            f'<line x1="{_n(cx)}" y1="{_n(cy)}" x2="{_n(x1)}" y2="{_n(y1)}" '
            f'stroke="{INK}" stroke-width="1.05" stroke-dasharray="5 4"/>'
        )
    parts.append(
        f'<circle cx="{_n(cx)}" cy="{_n(cy)}" r="{_n(r)}" fill="none" '
        f'stroke="{INK}" stroke-width="1.5"/>'
    )
    size = pad * 2 + r * 2
    return _svg(size, size, "".join(parts))


def _tri_row(spec: Mapping[str, Any]) -> str:
    n = spec["n"]
    if isinstance(n, bool) or not isinstance(n, (int, float)) or int(n) != n:
        raise ValueError("n 은 정수여야 합니다")
    n = int(n)
    if n < 2 or n > 8:
        raise ValueError("n 은 2 이상 8 이하여야 합니다")
    filled = _frac_filled(spec["filled"], n)
    w, h, pad = 32.0, 46.0, 8.0
    lo_y, hi_y = pad + h, pad
    fill_on, fill_off = str(spec.get("fill") or "#d7c2e4"), PAPER
    parts: list[str] = []
    for i in range(n):
        x0 = pad + i * w
        x1 = x0 + w
        xm = (x0 + x1) / 2
        if i % 2 == 0:
            pts = f"{_n(x0)},{_n(lo_y)} {_n(xm)},{_n(hi_y)} {_n(x1)},{_n(lo_y)}"
        else:
            pts = f"{_n(x0)},{_n(hi_y)} {_n(xm)},{_n(lo_y)} {_n(x1)},{_n(hi_y)}"
        fill = fill_on if i in filled else fill_off
        parts.append(
            f'<polygon points="{pts}" fill="{fill}" stroke="{INK}" stroke-width="1.2"/>'
        )
    return _svg(pad * 2 + n * w, pad * 2 + h, "".join(parts))


def _trap_four(spec: Mapping[str, Any]) -> str:
    """이등변사다리꼴 = 합동인 직각삼각형 넷.

    두 대각선으로 나누면 위·아래 삼각형 넓이가 달라 분수에 못 쓴다.
    원본(큐브 3-1 145쪽): 아랫변 3칸·윗변 1칸, 칸 한 변이 높이.
    0 왼쪽 · 1 가운데 위 · 2 가운데 아래 · 3 오른쪽.
    """
    filled = _frac_filled(spec["filled"], 4)
    u, pad = 36.0, 8.0
    y_top, y_bot = pad, pad + u
    bl = (pad, y_bot)
    b1 = (pad + u, y_bot)
    b2 = (pad + 2 * u, y_bot)
    br = (pad + 3 * u, y_bot)
    tl = (pad + u, y_top)
    tr = (pad + 2 * u, y_top)
    tris = ((bl, b1, tl), (tl, b1, tr), (b1, b2, tr), (tr, b2, br))
    fill_on = str(spec.get("fill") or "#d7c2e4")
    parts: list[str] = []

    def _pts(tri: tuple[tuple[float, float], ...]) -> str:
        return " ".join(f"{_n(x)},{_n(y)}" for x, y in tri)

    for i, tri in enumerate(tris):
        fill = fill_on if i in filled else PAPER
        parts.append(f'<polygon points="{_pts(tri)}" fill="{fill}"/>')
    parts.append(
        f'<polygon points="{_pts((bl, tl, tr, br))}" fill="none" '
        f'stroke="{INK}" stroke-width="1.3"/>'
    )
    for a, b in ((tl, b1), (tr, b2), (b1, tr)):
        parts.append(_dashed_polyline([a, b], "4 3", sw=1.15))
    return _svg(pad * 2 + 3 * u, pad * 2 + u, "".join(parts))


# 정n각형 — **② `markedShape` 전용**이다. ⑧ `namedShapes`(고르기)에는 **넣지 않는다.**
#
# 🔴 이유는 취향이 아니라 **실측**이다 (2026-08-23, `measure-shape-distance.py --all`,
#    슬롯 44). 정n각형을 ⑧ 목록에 넣으면 **7쌍이 문턱(6px) 아래**로 떨어진다:
#
#      heptagon ↔ octagon   2.18px      ← 바닥
#      heptagon ↔ hexagon   2.89px
#      hexagon  ↔ octagon   2.95px
#      heptagon ↔ pentagon  4.12px
#      hexagon  ↔ pentagon  4.20px
#      octagon  ↔ pentagon  4.20px
#      diamond  ↔ hexagon   5.72px      ← 기존 도형까지 같이 좁아진다
#
#    변 수만 다르고 윤곽이 **원에 수렴**하니 「이 중에서 고르시오」가 성립하지 않는다.
#    ⑧ 만 두면 바닥은 `para↔rect` 7.92px(여유 +1.92px)로 지금 그대로다.
#    반면 성질 문항(「정팔각형의 한 변이 4 cm 이면 둘레는?」)은 **도형이 하나뿐**이라
#    잴 쌍이 없다. 초4 2-6 발문 전수(씨앗 200)가 전부 그 부류였다.
#
# ⚠️ 「그럼 목록이 두 벌 아닌가」 — 아니다. `_MARKED_KINDS` 가 `_SHAPE_KINDS` 를
#    **포함**하므로 ⑧ 에 도형을 더하면 ② 는 자동으로 따라온다. 한 방향 의존이다.
_NGON_SIDES: dict[str, int] = {
    "pentagon": 5,
    "hexagon": 6,
    "heptagon": 7,
    "octagon": 8,
    "nonagon": 9,
}
_NGON_KINDS = frozenset(_NGON_SIDES)
_SHAPE_KINDS = frozenset(
    {
        "square",
        "rect",
        "rightTri",
        "isoTri",
        "wideTri",
        "eqTri",
        "diamond",
        "tallDiamond",
        "trap",
        "para",
        "irregQuad",
    }
)
# **모든 변이 정의상 같은** 도형 — `sides` 를 줘도 비율이 이미 맞다.
# 실측(슬롯 100)으로 정했다: square 100×4 · diamond 71×4 · tallDiamond 55×4 ·
# 정n각형 n개가 전부 같다. 「한 변이 5 cm 인 마름모의 네 변의 합은?」이 이 자리다.
# ⚠️ 목록을 손으로 적지 않고 **좌표에서 확인**할 수도 있지만, 그러면 렌더할 때마다
#    재게 된다. 대신 시험이 「이 목록의 도형은 정말 변이 다 같은가」를 잰다.
_EQUILATERAL = frozenset({"square", "diamond", "tallDiamond"}) | _NGON_KINDS
_MARKED_KINDS = _SHAPE_KINDS | _NGON_KINDS
# 도형 항목의 허용 키. 오타(`mark`)가 조용히 무시되면 「옵션을 껐는데 왜 그대로냐」가 된다.
_SHAPE_ITEM_KEYS = frozenset({"shape", "label", "marks"})
# 이등변삼각형 밑변 (슬롯 한 변 대비). 정삼각형과 **윤곽으로** 갈려야 한다 — 09 §4-19.
ISO_TRI_BASE = 0.58
# 서로 다른 kind 의 윤곽이 이보다 가까우면 「이 중에서 고르시오」가 성립하지 않는다.
# 실측 바닥은 para↔rect 7.92px 이고 결함이던 eqTri↔isoTri 는 3.93px 이었다.
SHAPE_MIN_DISTANCE = 6.0


def _poly_pts(pts: list[tuple[float, float]], sw: float = 1.5) -> str:
    s = " ".join(f"{_n(x)},{_n(y)}" for x, y in pts)
    return f'<polygon points="{s}" fill="none" stroke="{INK}" stroke-width="{_n(sw)}"/>'


def _tick_at(a: tuple[float, float], b: tuple[float, float], length: float = 3.4) -> str:
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    dx, dy = b[0] - a[0], b[1] - a[1]
    hyp = math.hypot(dx, dy) or 1.0
    nx, ny = (-dy / hyp) * length, (dx / hyp) * length
    return (
        f'<line x1="{_n(mx - nx)}" y1="{_n(my - ny)}" x2="{_n(mx + nx)}" y2="{_n(my + ny)}" '
        f'stroke="{INK}" stroke-width="1.2"/>'
    )


def _right_mark(
    corner: tuple[float, float],
    p: tuple[float, float],
    q: tuple[float, float],
    size: float = 7.0,
) -> str:
    def unit(dst: tuple[float, float]) -> tuple[float, float]:
        dx, dy = dst[0] - corner[0], dst[1] - corner[1]
        hyp = math.hypot(dx, dy) or 1.0
        return dx / hyp * size, dy / hyp * size

    ux, uy = unit(p)
    vx, vy = unit(q)
    a = (corner[0] + ux, corner[1] + uy)
    c = (corner[0] + vx, corner[1] + vy)
    b = (corner[0] + ux + vx, corner[1] + uy + vy)
    return (
        f'<polyline points="{_n(a[0])},{_n(a[1])} {_n(b[0])},{_n(b[1])} {_n(c[0])},{_n(c[1])}" '
        f'fill="none" stroke="{INK}" stroke-width="1.15"/>'
    )


def _ngon_points(n: int, ox: float, oy: float, s: float) -> list[tuple[float, float]]:
    """정n각형 — 슬롯에 내접. 꼭짓점 하나를 **맨 위**에 둔다(교과서 배치).

    변 길이·내각이 모두 같은 것은 「정n각형」의 정의라 **좌표에서 자동으로 참**이다 —
    시험이 그것을 재서 확인한다(지어낸 좌표를 넣으면 빨개진다).
    """
    cx, cy, r = ox + s / 2, oy + s / 2, s / 2
    return [
        (
            cx + r * math.sin(2 * math.pi * i / n),
            cy - r * math.cos(2 * math.pi * i / n),
        )
        for i in range(n)
    ]


def _shape_points(kind: str, ox: float, oy: float, s: float) -> list[tuple[float, float]]:
    """도형의 **꼭짓점**을 그리는 순서대로.

    🔴 **`namedShapes`(고르기)와 `markedShape`(성질)가 이 하나를 쓴다.** 모양 목록이
    두 벌이 되면 한쪽만 늘어나도 아무도 모른다 — 오늘 `allow_unknown` 이 정확히 그
    모양이었다(막대에만 있고 꺾은선에는 없었다, CLAUDE.md 2026-08-18).

    ⚠️ `square`·`rect` 는 지면에 여전히 `<rect>` 로 나간다(아래 `_draw_named_shape`).
    여기서 점을 내는 것은 **재기 위해서**이지 그리는 방식을 바꾸려는 게 아니다.
    """
    if kind in _NGON_SIDES:
        return _ngon_points(_NGON_SIDES[kind], ox, oy, s)
    if kind == "square":
        return [(ox, oy), (ox + s, oy), (ox + s, oy + s), (ox, oy + s)]
    if kind == "rect":
        x0, w = ox + s * 0.18, s * 0.64
        return [(x0, oy), (x0 + w, oy), (x0 + w, oy + s), (x0, oy + s)]
    if kind == "rightTri":
        return [(ox, oy + s), (ox, oy), (ox + s, oy + s)]
    if kind == "isoTri":
        # 밑변을 좁힌다. 밑변 s·높이 s 이면 정삼각형(밑변 s·높이 0.866s)과 윤곽 거리가
        # **3.93px** 뿐이라 tick 없이는 둘을 못 가른다 — 등변 표시를 옵트인으로 돌린
        # 순간(원장님 결함 ⑤) 세 세션이 같은 자리에서 막혔다. 0.58s 로 좁히면 9.45px 가
        # 되어 나머지 짝들(최소 7.92px) 사이에 묻힌다. 변 길이 비 1.12 → 1.80 (09 §4-19).
        half = s * ISO_TRI_BASE / 2
        return [(ox + s / 2 - half, oy + s), (ox + s / 2, oy), (ox + s / 2 + half, oy + s)]
    if kind == "wideTri":
        return [(ox, oy + s), (ox + s / 2, oy + s * 0.42), (ox + s, oy + s)]
    if kind == "eqTri":
        h = s * math.sqrt(3) / 2
        y0 = oy + (s - h) / 2
        return [(ox, y0 + h), (ox + s / 2, y0), (ox + s, y0 + h)]
    if kind == "diamond":
        return [(ox + s / 2, oy), (ox + s, oy + s / 2), (ox + s / 2, oy + s), (ox, oy + s / 2)]
    if kind == "tallDiamond":
        return [
            (ox + s / 2, oy),
            (ox + s * 0.72, oy + s / 2),
            (ox + s / 2, oy + s),
            (ox + s * 0.28, oy + s / 2),
        ]
    if kind == "trap":
        return [
            (ox + s * 0.2, oy + s * 0.12),
            (ox + s * 0.8, oy + s * 0.12),
            (ox + s, oy + s),
            (ox, oy + s),
        ]
    if kind == "para":
        return [
            (ox + s * 0.28, oy),
            (ox + s, oy),
            (ox + s * 0.72, oy + s),
            (ox, oy + s),
        ]
    return [
        (ox + s * 0.08, oy + s * 0.22),
        (ox + s * 0.92, oy),
        (ox + s, oy + s * 0.62),
        (ox + s * 0.18, oy + s),
    ]


def _draw_named_shape(kind: str, ox: float, oy: float, s: float, marks: bool = False) -> str:
    """`marks` 는 **등변 tick·직각 기호**를 그릴지다. 기본은 끈 쪽이다.

    「세 변의 길이가 모두 같은 삼각형의 기호를 쓰시오」인데 가에 tick 이 찍혀 있으면
    문제가 성립하지 않는다(원장님 2026-08-22). 그림이 묻는 것을 답해 주면 안 되므로
    안전한 쪽을 기본값으로 두고, 성질을 **주고** 푸는 문항만 켠다. 도형 자체는 여전히
    정확한 정삼각형·직각삼각형이라 재면 알 수 있다.
    """
    pts = _shape_points(kind, ox, oy, s)
    if kind in ("square", "rect"):
        # 지면은 그대로 `<rect>` 다 — 점으로 가른 것은 재기 위해서다.
        x0 = min(p[0] for p in pts)
        y0 = min(p[1] for p in pts)
        return _rect(x0, y0, max(p[0] for p in pts) - x0, max(p[1] for p in pts) - y0, sw=1.5)
    if kind == "rightTri":
        mark = _right_mark(pts[0], pts[1], pts[2]) if marks else ""
        return _poly_pts(pts) + mark
    if kind == "eqTri":
        ticks = "".join(_tick_at(pts[i], pts[(i + 1) % 3]) for i in range(3)) if marks else ""
        return _poly_pts(pts) + ticks
    return _poly_pts(pts)


def _named_shapes(spec: Mapping[str, Any]) -> str:
    """도형 여러 개. 라벨은 항상 각 도형 아래 같은 높이.

    FigureSpec `labels` 는 점 옆에 붙어 y 가 제각각이다 — 쓰지 않는다 (09 §4-7).
    """
    items = spec["items"]
    if not isinstance(items, list) or not items:
        raise ValueError("items 는 비어 있지 않은 배열이어야 합니다")
    if len(items) > 12:
        raise ValueError("items 는 12개 이하여야 합니다")
    slot, size, gap, pad, lab = 58.0, 44.0, 10.0, 8.0, 16.0
    cols = min(3, len(items))
    rows = (len(items) + cols - 1) // cols
    parts: list[str] = []
    for i, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise ValueError("namedShapes items 는 객체여야 합니다")
        extra = set(item) - _SHAPE_ITEM_KEYS
        if extra:
            raise ValueError(f"허용되지 않은 도형 키: {', '.join(sorted(str(k) for k in extra))}")
        kind = str(item.get("shape", ""))
        if kind not in _SHAPE_KINDS:
            raise ValueError(f"모르는 도형입니다: {kind}")
        marks = item.get("marks", False)
        if not isinstance(marks, bool):
            raise ValueError("marks 는 참·거짓이어야 합니다")
        label = str(item.get("label", ""))
        col, row = i % cols, i // cols
        ox = pad + col * (slot + gap)
        oy = pad + row * (slot + lab + gap)
        parts.append(_draw_named_shape(kind, ox + (slot - size) / 2, oy, size, marks))
        if label:
            parts.append(_text(ox + slot / 2, oy + size + 12, label, size=13, weight="700"))
    width = pad * 2 + cols * slot + (cols - 1) * gap
    height = pad * 2 + rows * (slot + lab) + (rows - 1) * gap
    return _svg(width, height, "".join(parts))


def _side_index(v: Any, name: str, n: int) -> int:
    """변·꼭짓점 번호. 범위를 벗어나면 **던진다** — 조용히 감싸면 엉뚱한 변에 표시된다."""
    if isinstance(v, bool) or not isinstance(v, int):
        raise ValueError(f"{name} 의 번호는 정수여야 합니다: {v!r}")
    if not 0 <= v < n:
        raise ValueError(f"{name} 의 번호가 범위를 벗어났습니다: {v} (0~{n - 1})")
    return v


# 같은 무리의 변에 찍는 tick 개수. 무리가 둘이면 ‖ 와 ‖‖ 로 갈린다 — 개수가 곧 「무리」다.
_EQUAL_TICKS = (1, 2, 3)


_NUM_IN_LABEL = re.compile(r"[-+]?\d+(?:\.\d+)?")


def _side_nums(labels: list[Any]) -> list[float | None]:
    r"""라벨에서 **수**를 뽑는다. 「7 cm」→ 7 · 「$4\,\mathrm{cm}$」→ 4 · 수가 없으면 None.

    라벨은 지면에 적히는 글자이고 여기서 필요한 것은 **비율**이라 수만 본다.
    수가 없는 라벨(「가」 같은)은 비율에 안 쓴다 — 그건 배반할 값이 없다.
    """
    out: list[float | None] = []
    for v in labels:
        m = None if v is None else _NUM_IN_LABEL.search(str(v))
        out.append(float(m.group()) if m else None)
    return out


def _angle_nums(labels: list[Any]) -> list[float | None]:
    return _side_nums(labels)


def _fit(pts: list[tuple[float, float]], pad: float, size: float) -> list[tuple[float, float]]:
    """슬롯에 맞춰 키우고 가운데로. **비는 안 바뀐다** — 절대 크기는 원래 안 지킨다."""
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    w = max(xs) - min(xs) or 1.0
    h = max(ys) - min(ys) or 1.0
    k = size / max(w, h)
    ox = pad + (size - w * k) / 2 - min(xs) * k
    oy = pad + (size - h * k) / 2 - min(ys) * k
    return [(x * k + ox, y * k + oy) for x, y in pts]


def _triangle_points(
    sides: list[float | None], angles: list[float | None], pad: float, size: float
) -> list[tuple[float, float]] | None:
    """적힌 값대로 삼각형을 잡는다. 값이 없으면 `None`(부르는 쪽이 관례 도형을 쓴다).

    변 `i` 는 꼭짓점 `i`→`i+1`, 각 `i` 는 꼭짓점 `i` 다.
    """
    known_s = [v for v in sides if v is not None]
    known_a = [v for v in angles if v is not None]
    if not known_s and not known_a:
        return None

    # 🔴 **모순·불가능만 던진다.**
    if len(known_a) == 3 and abs(sum(known_a) - 180.0) > 0.5:
        raise ValueError(
            f"세 각의 합이 {sum(known_a):g}° 입니다 — 삼각형은 180° 여야 합니다"
        )
    if len(known_s) == 3:
        a, b, c = known_s
        if a + b <= c or b + c <= a or c + a <= b:
            raise ValueError(
                f"세 변 {a:g}·{b:g}·{c:g} 로는 삼각형이 만들어지지 않습니다 "
                f"(두 변의 합이 나머지 한 변보다 커야 합니다)"
            )
        # SSS — s0 를 밑변으로 놓고 셋째 꼭짓점을 푼다.
        s0, s1, s2 = sides[0], sides[1], sides[2]
        x = (s2 * s2 + s0 * s0 - s1 * s1) / (2 * s0)
        y = math.sqrt(max(s2 * s2 - x * x, 1e-9))
        return _fit([(0.0, 0.0), (s0, 0.0), (x, -y)], pad, size)

    if len(known_a) >= 2:
        # AA — 세 각이 정해지면 모양이 정해진다(크기는 자유). 사인법칙으로 변을 낸다.
        aa = list(angles)
        miss = [i for i, v in enumerate(aa) if v is None]
        if len(miss) == 1:
            aa[miss[0]] = 180.0 - sum(v for v in aa if v is not None)
        if any(v is None or v <= 0 for v in aa):
            return None
        if abs(sum(aa) - 180.0) > 0.5:
            raise ValueError(
                f"세 각의 합이 {sum(aa):g}° 입니다 — 삼각형은 180° 여야 합니다"
            )
        # 변 i(=꼭짓점 i→i+1)는 그 둘이 아닌 **나머지 꼭짓점**의 각과 마주 본다.
        s = [math.sin(math.radians(aa[(i + 2) % 3])) for i in range(3)]
        x = (s[2] * s[2] + s[0] * s[0] - s[1] * s[1]) / (2 * s[0])
        y = math.sqrt(max(s[2] * s[2] - x * x, 1e-9))
        return _fit([(0.0, 0.0), (s[0], 0.0), (x, -y)], pad, size)

    if len(known_s) == 2:
        # 적힌 둘의 비만 지키면 된다 — 셋째는 관례값(지금 도형의 비를 쓴다).
        i0 = sides.index(known_s[0])
        i1 = len(sides) - 1 - sides[::-1].index(known_s[1])
        base = [1.0, 1.0, ISO_TRI_BASE]
        base[i0], base[i1] = known_s[0], known_s[1]
        third = [i for i in range(3) if i not in (i0, i1)][0]
        # 남은 변은 두 변 사이 어딘가 — 삼각부등식을 만족하는 값으로 둔다.
        base[third] = (base[i0] + base[i1]) * 0.62
        s0, s1, s2 = base
        x = (s2 * s2 + s0 * s0 - s1 * s1) / (2 * s0)
        y = math.sqrt(max(s2 * s2 - x * x, 1e-9))
        return _fit([(0.0, 0.0), (s0, 0.0), (x, -y)], pad, size)
    return None


# 평행사변형의 관례 각 — 「이웃한 두 변이 4·6」처럼 **각이 안 적힌** 판에서 쓴다.
# ⚠️ 너무 납작하면 지면에서 「이게 정말 4:6인가」가 안 읽힌다(리드 지적). 시험이 잠근다.
PARA_DEFAULT_DEG = 65.0


def _para_points(
    sides: list[float | None],
    angles: list[float | None],
    pad: float,
    size: float,
    right: bool = False,
) -> list[tuple[float, float]] | None:
    """평행사변형·직사각형 — 이웃한 두 변의 비와 한 각을 반영한다. 둘 다 없으면 `None`.

    `right` 면 각을 **늘 90°** 로 둔다(직사각형은 각이 자유롭지 않다). 그래서 `rect` 는
    적힌 각이 90° 가 아니면 **모순**이다 — 조용히 90° 로 그리지 않고 던진다.
    """
    known_s = [v for v in sides if v is not None]
    known_a = [v for v in angles if v is not None]
    if not known_s and not known_a:
        return None
    if right and known_a and abs(known_a[0] - 90.0) > 0.5:
        raise ValueError(
            f"직사각형의 각은 90° 인데 {known_a[0]:g}° 가 적혔습니다"
        )
    if known_a and (known_a[0] <= 0 or known_a[0] >= 180):
        raise ValueError(f"각 {known_a[0]:g}° 로는 평행사변형이 만들어지지 않습니다")
    a = known_s[0] if known_s else 1.4
    b = known_s[1] if len(known_s) > 1 else 1.0
    deg = 90.0 if right else (known_a[0] if known_a else PARA_DEFAULT_DEG)
    t = math.radians(deg)
    return _fit(
        [
            (0.0, 0.0),
            (a, 0.0),
            (a + b * math.cos(t), -b * math.sin(t)),
            (b * math.cos(t), -b * math.sin(t)),
        ],
        pad,
        size,
    )


def _marked_shape(spec: Mapping[str, Any]) -> str:
    """도형 **하나** 위에 각도·변 길이·등변 tick·직각 기호를 얹는다.

    `namedShapes`(고르기)와 나누는 축은 「**도형이 몇 개인가**」가 아니라
    「**무엇을 지키는 불변식인가**」다. 고르기는 도형 쌍이 윤곽으로 갈려야 하고
    (`SHAPE_MIN_DISTANCE`, 09 §4-19), 성질 문항은 도형이 하나라 잴 쌍이 없다.
    한 kind 에 두 규칙이 살면 가드 절반이 늘 헛돈다.

    모양은 `_shape_points` 하나에서 온다 — 목록을 두 벌로 만들지 않는다.
    치수는 전부 `_length_mark`(=`measured()`) 다 (09 §4-16).
    """
    # ⚠️ 키 검사를 여기서 **다시 하지 않는다.** `validate_elementary` 가 `KIND_FIELDS`·
    #    `OPTIONAL` 로 이미 거른다("검증은 한 벌뿐이다"). 여기 목록을 하나 더 두면
    #    필드를 늘릴 때 **한쪽만 늘어나고** 아무도 모른다 — 변이 시험이 그것을 잡았다
    #    (「모르는 키 검사 끄기」가 초록이었다 = 그 검사는 아무것도 안 지켰다).
    kind = str(spec.get("shape", ""))
    # `areaPoly` 는 마름모를 `rhombus` 라 부르고 도형 목록은 `diamond` 라 부른다 —
    # **이름이 두 벌**이라 학년 세션이 헷갈린다(elem-g4 가 `rhombus` 로 넣어 막혔다).
    # 여기서 받아 준다. 이름을 통일하는 것이 옳지만 그건 `areaPoly` 까지 걸린 별건이다.
    kind = {"rhombus": "diamond"}.get(kind, kind)
    if kind not in _MARKED_KINDS:
        raise ValueError(f"모르는 도형입니다: {kind}")

    # 바깥 치수 라벨의 halo 상자까지 담는다. 30px 에서는 기울어진 변의 긴 라벨이
    # `measured()` 의 법선 방향 push 뒤 viewBox 가장자리에 닿았다.
    # 폭 184px 는 figureSvgFrame 의 같은 mid 등급(161~320)을 유지한다.
    pad, size = 40.0, 104.0
    pts = _shape_points(kind, pad, pad, size)
    n = len(pts)

    def _seq(name: str, limit: int) -> list[Any]:
        raw = spec.get(name)
        if raw is None:
            return [None] * limit
        if not isinstance(raw, list):
            raise ValueError(f"{name} 은 배열이어야 합니다")
        if len(raw) > limit:
            raise ValueError(f"{name} 이 꼭짓점 수({limit})보다 깁니다")
        return list(raw) + [None] * (limit - len(raw))

    sides = _seq("sides", n)
    angles = _seq("angles", n)

    # ── 적힌 값을 그림에 반영한다 (2026-08-23 비율 수리) ──────────────────────
    #
    # **적힌 값은 반드시 그림에 반영한다. 안 적힌 것은 관례값으로 둔다.
    #  적힌 값들이 서로 모순이거나 기하적으로 불가능할 때만 던진다.**
    #
    # 종전에는 `sides`·`angles` 를 **라벨로만** 얹고 도형은 고정이었다 — 「5,5,9」의
    # 밑변을 제일 짧게 그렸다. **값은 맞고 그림이 그 값을 배반**했고, 09 §4-21 과 같은
    # 부류라 스스로 신고하지 않았다(elem-g4 가 배선하며 렌더해 보고 찾았다).
    #
    # ⚠️ 「모양이 유일하게 안 정해지면 던진다」로 잡았다가 **되물렀다.** 실제 발문은
    #    변만 주거나 각만 준다(초4 2-4-5) — 안 적힌 것까지 문제 삼으면 그 갈래를
    #    통째로 막는다. 안 적힌 것은 배반할 것이 없으므로 관례값으로 둔다.
    nums = _side_nums(sides)
    angs = _angle_nums(angles)
    if n == 3:
        pts = _triangle_points(nums, angs, pad, size) or pts
    elif kind in ("para", "rect"):
        # 이웃한 두 변의 비 + 한 각. `rect` 는 각이 늘 90° 라 변만 본다.
        pts = _para_points(nums, angs, pad, size, right=(kind == "rect")) or pts
    elif kind in _EQUILATERAL:
        # 🔴 **이미 모든 변이 같은 도형** — `sides` 를 줘도 비율이 이미 맞다(실측).
        #    「한 변이 5 cm 인 마름모의 네 변의 합은?」류가 이 자리다. 던질 이유가 없다.
        #    다만 **서로 다른 값**을 적었으면 그건 모순이라 던진다.
        vals = [v for v in nums if v is not None]
        if len(set(vals)) > 1:
            raise ValueError(
                f"«{kind}» 는 모든 변이 같은 도형인데 서로 다른 값이 적혔습니다: "
                f"{' · '.join(f'{v:g}' for v in sorted(set(vals)))}"
            )
    elif any(v is not None for v in nums) or any(v is not None for v in angs):
        # 아직 비율을 못 맞추는 도형 — 조용히 배반하느니 던진다.
        raise ValueError(
            f"«{kind}» 는 아직 sides·angles 를 그림에 반영하지 못합니다 — "
            f"값을 빼고 모양·표시만 쓰거나 그 수를 발문에 적으십시오"
        )
    cxr = sum(p[0] for p in pts) / n
    cyr = sum(p[1] for p in pts) / n

    parts: list[str] = []
    if kind in ("square", "rect"):
        x0 = min(p[0] for p in pts)
        y0 = min(p[1] for p in pts)
        parts.append(
            _rect(x0, y0, max(p[0] for p in pts) - x0, max(p[1] for p in pts) - y0, sw=1.5)
        )
    else:
        parts.append(_poly_pts(pts))

    # 등변 tick — 무리마다 개수를 달리해 «어느 변끼리 같은가»가 보이게 한다.
    equal = spec.get("equal")
    if equal is not None:
        if not isinstance(equal, list):
            raise ValueError("equal 은 배열이어야 합니다")
        for g, group in enumerate(equal):
            if not isinstance(group, list) or len(group) < 2:
                raise ValueError("equal 의 각 무리는 변 번호 2개 이상이어야 합니다")
            count = _EQUAL_TICKS[min(g, len(_EQUAL_TICKS) - 1)]
            for si in group:
                i = _side_index(si, "equal", n)
                a, b = pts[i], pts[(i + 1) % n]
                for k in range(count):
                    # 여러 개면 중점 둘레로 살짝 벌린다.
                    parts.append(_tick_span(a, b, 0.5 + (k - (count - 1) / 2) * 0.055))

    # 대각선 — **이웃하지 않은** 꼭짓점만 잇는다. 그은 개수가 발문의 답과 같아야 하므로
    # 「n(n-3)/2」가 좌표에서 **자동으로** 나오게 둔다(손으로 세지 않는다).
    # 값을 묻는 문항(「팔각형에 그을 수 있는 대각선은 몇 개?」)이 이 그림을 쓴다.
    if spec.get("diagonals"):
        if spec["diagonals"] is not True:
            raise ValueError("diagonals 는 참·거짓이어야 합니다")
        if n < 4:
            raise ValueError("삼각형에는 대각선이 없습니다")
        for i in range(n):
            for j in range(i + 2, n):
                if i == 0 and j == n - 1:
                    continue  # 이웃(첫 점과 끝 점)
                parts.append(_seg(pts[i], pts[j], sw=1.0, dash="4 3"))

    # 직각 기호 — **작은 정사각형**이다. 엔진 A 는 이 자리를 호로 그린다(09 §2.1 주).
    right = spec.get("right")
    if right is not None:
        if not isinstance(right, list):
            raise ValueError("right 는 배열이어야 합니다")
        for ri in right:
            i = _side_index(ri, "right", n)
            parts.append(_right_mark(pts[i], pts[(i - 1) % n], pts[(i + 1) % n]))

    # 변 길이 — `measured()`. 도형 **바깥**으로 벌린다.
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n
    for i, label in enumerate(sides):
        if label is None:
            continue
        a, b = pts[i], pts[(i + 1) % n]
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        # 무게중심 반대쪽이 바깥이다 — `measured` 의 off 부호로 정한다.
        nx, ny = -(b[1] - a[1]), b[0] - a[0]
        outward = (mx - cx) * nx + (my - cy) * ny
        parts.append(
            _length_mark(a[0], a[1], b[0], b[1], str(label), off=11.0 if outward > 0 else -11.0)
        )

    # 각 — 꼭짓점에서 **안쪽**으로 들여 적는다.
    for i, label in enumerate(angles):
        if label is None:
            continue
        px, py = pts[i]
        dx, dy = cx - px, cy - py
        hyp = math.hypot(dx, dy) or 1.0
        parts.append(_text(px + dx / hyp * 22, py + dy / hyp * 22 + 4, str(label), size=12))

    return _svg(pad * 2 + size, pad * 2 + size, "".join(parts))


def _seg(
    a: tuple[float, float],
    b: tuple[float, float],
    *,
    sw: float = 1.2,
    dash: str | None = None,
) -> str:
    """두 점을 잇는 선 하나. `elementary.py` 에는 범용 선 함수가 없어 kind 마다
    `<line>` 을 손으로 조립하고 있었다 — 대각선처럼 **여러 개**를 긋는 자리에는 둔다."""
    d = f' stroke-dasharray="{_esc(dash)}"' if dash else ""
    return (
        f'<line x1="{_n(a[0])}" y1="{_n(a[1])}" x2="{_n(b[0])}" y2="{_n(b[1])}" '
        f'stroke="{INK}" stroke-width="{_n(sw)}"{d}/>'
    )


def _tick_span(
    a: tuple[float, float], b: tuple[float, float], t: float, length: float = 3.4
) -> str:
    """변 `a→b` 의 위치 `t` 에 수직 tick 하나. `_tick_at` 의 t 를 옮길 수 있는 판."""
    mx, my = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
    dx, dy = b[0] - a[0], b[1] - a[1]
    hyp = math.hypot(dx, dy) or 1.0
    nx, ny = (-dy / hyp) * length, (dx / hyp) * length
    return (
        f'<line x1="{_n(mx - nx)}" y1="{_n(my - ny)}" x2="{_n(mx + nx)}" y2="{_n(my + ny)}" '
        f'stroke="{INK}" stroke-width="1.2"/>'
    )


# 평행 표시(겹화살표)의 크기 — 두 직선에 **같은 개수**를 찍어 「이 둘이 평행」을 말한다.
_PARA_MARK = 5.0


def _para_mark(mx: float, my: float, dx: float, dy: float, k: int) -> str:
    """평행 표시 — 진행 방향으로 벌어진 「>」 를 `k` 개. 두 직선에 **같은 수**를 찍는다."""
    out: list[str] = []
    for i in range(k):
        ox = mx + (i - (k - 1) / 2) * _PARA_MARK * 1.3 * dx
        oy = my + (i - (k - 1) / 2) * _PARA_MARK * 1.3 * dy
        # 「>」 = 뒤로 벌어진 두 선분. 화살촉을 채우지 않는다(직각 기호와 헷갈리지 않게).
        nx, ny = -dy, dx
        out.append(
            f'<polyline points="{_n(ox - _PARA_MARK * dx + nx * _PARA_MARK * 0.7)},'
            f'{_n(oy - _PARA_MARK * dy + ny * _PARA_MARK * 0.7)} {_n(ox)},{_n(oy)} '
            f'{_n(ox - _PARA_MARK * dx - nx * _PARA_MARK * 0.7)},'
            f'{_n(oy - _PARA_MARK * dy - ny * _PARA_MARK * 0.7)}" '
            f'fill="none" stroke="{INK}" stroke-width="1.15"/>'
        )
    return "".join(out)


def _line_relation(spec: Mapping[str, Any]) -> str:
    """두 직선의 관계 — **수직**·**평행**(+ 평행선 사이 거리). 초4 2-4-1·2·3.

    ## 왜 `parallel` 뿐인가 (2026-08-24)

    처음에 `perpendicular`·`bothPerpendicular` 도 만들었다가 **지웠다.** 초4 2-4-1·2 의
    발문을 다시 보니 **묻는 것이 곧 그림이 보여 주는 것**이었다:

    | 발문 | 답 | 그림이 그리면 |
    |---|---|---|
    | 「수선은 몇 도를 이루며 만나는가」 | 90° | 직각 기호가 **답을 말한다** |
    | 「두 직선이 직각일 때 서로 무엇인가」 | 수직 | 〃 |
    | 「한 직선에 수직인 두 직선은 어떤 관계인가」 | 평행 | 평행하게 그리면 **답을 말한다** |

    D-66 ⑺ 의 그 자리다. 게다가 그 두 갈래는 **스펙 값을 하나도 안 받아**(좌표가 전부
    상수) 씨앗이 달라도 그림이 한 픽셀도 안 바뀐다(R9-b). 그리고 g4 가 2-4-1·2 를
    **글로 된 사다리**(꺾인 횟수의 홀짝)로 세우기로 해 **부를 갈래도 없다.**

    → 값을 싣고 답을 안 보이는 쓰임이 생기면 그때 되살린다. 「직사각형에서 한 변에
      수직인 변은 몇 개」류는 **도형 위**라 `markedShape`(②) 쪽이지 여기가 아니다.

    🔴 **「표시가 있다」가 아니라 「정말 그러한가」가 불변식이다.** 수직은 두 방향 벡터의
    내적이 0, 평행은 외적이 0 — 시험이 그린 좌표에서 그것을 잰다. 표시는 그 사실을
    **보여 주는** 것이지 그것을 대신하지 않는다.

    ⚠️ 엔진 A(FigureSpec v2)로 그리면 **직각이 호**가 된다(09 §2.1 주). 초등 교과서의
       직각은 **작은 정사각형**이라 여기서 `_right_mark` 로 그린다.
    """
    rel = str(spec.get("relation", ""))
    if rel != "parallel":
        raise ValueError(
            f"모르는 관계입니다: {rel} — 지금은 parallel 뿐입니다"
        )
    labels = spec.get("labels")
    if labels is not None and (not isinstance(labels, list) or len(labels) != 2):
        raise ValueError("labels 는 직선 이름 2개여야 합니다")
    dist = spec.get("distance")

    pad, w, h = 26.0, 150.0, 110.0
    parts: list[str] = []
    y0 = pad + h * 0.3
    y1 = pad + h * 0.72
    parts.append(_seg((pad, y0), (pad + w, y0), sw=1.4))
    parts.append(_seg((pad, y1), (pad + w, y1), sw=1.4))
    # 평행 표시 — **두 직선에 같은 개수**. 그것이 「이 둘이 평행」을 말한다.
    k = _side_index(spec.get("marks", 1), "marks", 4) or 1
    parts.append(_para_mark(pad + w * 0.62, y0, 1.0, 0.0, k))
    parts.append(_para_mark(pad + w * 0.62, y1, 1.0, 0.0, k))
    # 수선 여러 개 — 「수선을 5개 그었습니다. 길이는 서로 어떠한가?」(초4 2-4-3).
    # **길이가 같다는 것이 답**이므로 정말 같게 그린다(세로선이라 자동으로 같다).
    #
    # ⚠️ **이 「같게 그린다」는 «만드는 쪽» 규칙이다 — «붙이는 쪽»에서는 부호가 뒤집힌다.**
    #    여기서는 「그림이 답과 어긋나면 안 된다」가 맞다. 그런데 답이 **「모두 같다」**인
    #    발문(초4 2-4-3, 실측 50/200)에 이 그림을 붙이면 **학생이 보고 쓴다** — 그림이
    #    답을 말한다(09 §2.2 규칙 ②). 같은 문장이 층이 바뀌면 결함이 된다.
    #    그 발문에는 **붙이지 않는다**(2026-08-24). 붙일 수 있는 것은
    #    「수선을 그었더니 $10$ cm, 거리는?」쪽이고 그때도 **치수는 안 적는다**
    #    (답이 준 값과 같아서 적으면 곧 답이다).
    npp = _side_index(spec.get("perpCount", 0), "perpCount", 9)
    for i in range(npp):
        x = pad + w * (0.18 + 0.64 * (i / max(npp - 1, 1)))
        parts.append(_seg((x, y0), (x, y1), sw=1.05))
        parts.append(_right_mark((x, y0), (pad + w, y0), (x, y1), size=5.0))
    if dist is not None:
        # 평행선 사이 거리는 **수선으로만** 잰다 — 비스듬한 선분이 아니다.
        mx = pad + w * 0.3
        parts.append(_length_mark(mx, y0, mx, y1, str(dist), off=-11.0))
    name_at = [(pad, y0), (pad, y1)]  # **서로 다른** 두 직선의 왼끝

    if labels:
        # 🔴 **갈래마다 «두 직선의 대표점»이 다르다.** 조건 하나로 뒤집으면 틀린다 —
        #    실제로 `parallel` 은 한 직선의 양 끝에, `bothPerpendicular` 은 세로선 하나와
        #    밑선에 이름이 붙어 있었다(리드가 좌표로 잡았다). 「직선 가와 나는 평행하다」와
        #    **정면으로 어긋나는** 그림이었고, 기하 축(내적·외적)은 그것을 못 본다.
        #    그래서 이름 자리는 **갈래마다 `name_at` 으로 따로 정한다** — 네 끝점을 한
        #    목록에 쌓아 두고 「앞 둘」을 쓰는 식으로 하면, 갈래가 늘 때 그 순서가 조용히
        #    어긋난다(그렇게 짰다가 틀렸다. 지금은 쓰지 않는 `ends` 를 지웠다).
        for (lx, ly), t in zip(name_at, labels):
            parts.append(_text(lx, ly - 8, str(t), size=12))
    return _svg(pad * 2 + w, pad * 2 + h, "".join(parts))


def _num_or(v: Any, default: float) -> float:
    """수면 그 값, 없으면 기본값. 문자열이면 수를 뽑는다(「5 cm」→ 5)."""
    if v is None:
        return default
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    got = _side_nums([v])[0]
    if got is None:
        raise ValueError(f"수를 읽지 못했습니다: {v!r}")
    return got


def _tiling(spec: Mapping[str, Any]) -> str:
    """조각과 목표 도형을 **나란히** 놓는다 — 초4 2-6-4 「모양 만들기와 채우기」.

    ## 🔴 채운 모습을 그리지 않는다 — 그러면 **답이 샌다**

    발문 셋이 전부 「조각이 **몇 개** 필요한가」다(씨앗 200 전수). 조각을 다 그리면
    **세면 답이 나온다**(D-66 ⑺) — ③ 에서 `perpendicular` 을 지운 것과 같은 자리다.

    그래서 **조각 하나와 목표 하나만** 나란히 놓고, **크기 비**를 발문의 값대로 그린다.
    「한 변 5 조각으로 한 변 10 을 채우려면」이면 1:2 로 그려지고, 학생은 그 비에서
    넓이비 4 를 구한다. **그림은 견줄 것을 주지 답을 주지 않는다.**

    ⚠️ 「정육각형을 정삼각형 몇 개로」는 크기가 아니라 **배치**라 이 그림이 답을 못
       준다 — 해롭지도 않다(조각과 목표가 무엇인지는 보여 준다). 배치를 보여 주는
       그림은 곧 답이므로 만들지 않는다.
    """
    piece = str(spec.get("piece", ""))
    target = str(spec.get("target", ""))
    for k in (piece, target):
        if k not in _MARKED_KINDS:
            raise ValueError(f"모르는 도형입니다: {k}")
    ps = _num_or(spec.get("pieceSide"), 1.0)
    ts = _num_or(spec.get("targetSide"), 2.0)
    if ps <= 0 or ts <= 0:
        raise ValueError("pieceSide·targetSide 는 0보다 커야 합니다")
    if ps > ts:
        raise ValueError(
            f"조각({ps:g})이 목표({ts:g})보다 큽니다 — 채울 수 없습니다"
        )

    pad, big, gap = 22.0, 86.0, 26.0
    small = big * ps / ts  # **크기 비가 발문의 값과 같다** — 시험이 이것을 잰다
    parts: list[str] = []
    py = pad + (big - small) / 2
    parts.append(_poly_pts(_shape_points(piece, pad, py, small)))
    parts.append(_poly_pts(_shape_points(target, pad + small + gap, pad, big)))
    if spec.get("labels") is not False:
        parts.append(_text(pad + small / 2, pad + big + 14, "조각", size=12))
        parts.append(_text(pad + small + gap + big / 2, pad + big + 14, "만들 모양", size=12))
    return _svg(pad * 2 + small + gap + big, pad * 2 + big + 18, "".join(parts))


def _circle_parts(spec: Mapping[str, Any]) -> str:
    """원과 그 부분 — 중심 · 반지름 · 지름. 초3 2-3.

    ## 🔴 **용어를 적지 않는다** — 2-3-1 이 그 용어를 묻는다

    발문 셋이 「원의 중심과 원 위의 한 점을 이은 선분을 **무엇이라고 하는지**」다.
    그림에 「반지름」이라 적으면 **그것이 곧 답**이다(D-66 ⑺). 그래서 용어 라벨은
    **아예 안 그린다** — 옵션으로도 두지 않는다. 「끄면 되지」로 두면 켠 채 나간다.

    ## 🔴 **주어진 값만 적는다** — 묻는 값은 부르는 쪽이 안 넘긴다

    2-3-2 는 「지름 10 인 원의 **반지름**은?」이고 2-3-3 은 「컴퍼스를 8 벌려 그렸다,
    **지름**은?」이다. 둘 다 적으면 답이 지면에 있다. 엔진은 **받은 것만** 그리고,
    무엇을 넘길지는 갈래가 정한다 — 다만 **둘 다 값을 주면 던진다**(그 조합은
    「구하라」 문항이 될 수 없다).

    그린 것이 값을 배반하지 않게 **지름 = 반지름 × 2 를 좌표에서** 지킨다.
    """
    r_lab = spec.get("radius")
    d_lab = spec.get("diameter")
    if r_lab is not None and d_lab is not None:
        raise ValueError(
            "radius 와 diameter 를 **둘 다** 적으면 그림이 답을 말합니다 — "
            "주어진 쪽만 넘기십시오"
        )
    pad, rad = 26.0, 62.0
    cx, cy = pad + rad, pad + rad
    parts: list[str] = [
        f'<circle cx="{_n(cx)}" cy="{_n(cy)}" r="{_n(rad)}" '
        f'fill="none" stroke="{INK}" stroke-width="1.5"/>'
    ]
    # 중심점 — 「무엇에서 잰 길이인가」가 보이려면 점이 있어야 한다(09 §4-16).
    if spec.get("center", True):
        parts.append(
            f'<circle cx="{_n(cx)}" cy="{_n(cy)}" r="2.2" fill="{INK}"/>'
        )
    # `show` — **치수 없이 선분만** 그린다. 2-3-1 이 「이 선분을 무엇이라 하는지」를
    # 묻는데, 그 선분이 지면에 없으면 그림이 아무 말도 안 한다. 답은 **낱말**이라
    # 선분을 그려도 새지 않는다 — 오히려 안 그리는 쪽이 문항을 약하게 만든다.
    #
    # 🔴 **여기서 「그린다」와 「적는다」가 갈라진다.** 그전에는 둘이 묶여 있어서
    #    「용어를 안 그린다」가 **공짜로** 지켜졌다. 푸는 순간 그것을 지킬 사람이
    #    새로 필요하다 — `show` 만 준 그림에 `<text>` 가 하나라도 있으면 안 된다.
    #    시험이 그 축을 따로 문다(리드 지적, 2026-08-24).
    show = spec.get("show")
    if show is not None and show not in ("radius", "diameter"):
        raise ValueError('show 는 "radius" 또는 "diameter" 여야 합니다')
    if show == "radius" and r_lab is not None:
        raise ValueError("show 와 radius 를 같이 주지 마십시오 — radius 가 이미 선분을 그립니다")
    if show == "diameter" and d_lab is not None:
        raise ValueError("show 와 diameter 를 같이 주지 마십시오 — diameter 가 이미 선분을 그립니다")

    if r_lab is not None or show == "radius":
        # 반지름 — 중심에서 원 위 한 점까지. 비스듬히 그어 지름과 눈으로 갈리게.
        ang = math.radians(-35.0)
        ex, ey = cx + rad * math.cos(ang), cy + rad * math.sin(ang)
        parts.append(_seg((cx, cy), (ex, ey), sw=1.3))
        if r_lab is not None:
            parts.append(_length_mark(cx, cy, ex, ey, str(r_lab), off=-10.0))
    if d_lab is not None or show == "diameter":
        # 지름 — **중심을 지나는** 현. 좌표가 대칭이라 그 성질이 자동으로 참이다.
        parts.append(_seg((cx - rad, cy), (cx + rad, cy), sw=1.3))
        if d_lab is not None:
            parts.append(_length_mark(cx - rad, cy, cx + rad, cy, str(d_lab), off=12.0))
    return _svg(pad * 2 + rad * 2, pad * 2 + rad * 2, "".join(parts))


_RENDER = {
    "numberCards": _number_cards,
    "circleParts": _circle_parts,
    "tiling": _tiling,
    "lineRelation": _line_relation,
    "markedShape": _marked_shape,
    "placeValue": _place_value,
    "base10": _base10,
    "opBox": _op_box,
    "sumBox": _sum_box,
    "opTree": _op_tree,
    "boxChain": _box_chain,
    "columnOp": _column_op,
    "numberLine": _number_line,
    "clocks": _clocks,
    "table": _table,
    "tape": _tape,
    "dotGrid": _dot_grid,
    "boxedList": _boxed_list,
    "pills": _pills,
    "geoLine": _geo_line,
    "anglePick": _angle_pick,
    "timeAdd": _time_add,
    "pointGrid": _point_grid,
    "divideTriangle": _divide_triangle,
    "fracPie": _frac_pie,
    "triRow": _tri_row,
    "trapFour": _trap_four,
    "namedShapes": _named_shapes,
}

# 후반 학년 kind. 이 파일 아래에서 import 해야 _svg 등이 이미 있다.
from elem_advanced import ADV_FIELDS, ADV_OPTIONAL, ADV_RENDER  # noqa: E402

KIND_FIELDS.update(ADV_FIELDS)
OPTIONAL.update(ADV_OPTIONAL)
_RENDER.update(ADV_RENDER)

# 실물 에셋 합성 kind (assetScene) — 규격·검증은 figure_assets.py 한 곳에.
from figure_assets import ASSET_FIELDS, ASSET_OPTIONAL, ASSET_RENDER  # noqa: E402

KIND_FIELDS.update(ASSET_FIELDS)
OPTIONAL.update(ASSET_OPTIONAL)
_RENDER.update(ASSET_RENDER)
