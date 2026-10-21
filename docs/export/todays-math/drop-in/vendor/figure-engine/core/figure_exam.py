# -*- coding: utf-8 -*-
"""기출 그림 재작도 공용 도구 — 세션 변환 `fig_svgs.py` 들이 복사해 쓰던 관용구를 한 곳에.

세션 변환(사대부중·오성중·제일고 …)은 시험지마다 `corpus/<시험지>/fig_svgs.py` 에서 그림을
**문제 조건으로 계산한 좌표**로 다시 그린다. 그 스크립트들 머리에 같은 헬퍼(라벨 조판·바깥
치수·사투영·viewBox 맞춤·스펙 조립·빌드 루프)가 거의 그대로 복사돼 있었다. 복사본은 한
곳을 고쳐도 다른 시험지에 안 퍼지고, 엔진만 옮겨 간 곳(todays-math `vendor/figure-engine`)
에서는 이 방법을 아예 쓸 수 없다. 그래서 2026-10-21 이 모듈로 모았다(구현은 제일고 고2
기하 25-2-기말·오성중 중2 25-2-기말 스크립트와 **출력이 바이트 단위로 같다** —
`tests/test_figure_exam.py`).

작업 순서(기출 그림 한 장)
    1. 원본을 확대해 **인쇄된 것만** 센다 — 선분(실선·점선)·보조선·라벨. 학생 필기는 뺀다.
    2. 좌표는 **조건에서 계산**한다(눈대중 금지). 입체는 3D 좌표 → `figure_solid`/`oblique`.
    3. 검산: `figure_svg.verify_figure`(길이·각·접선·점이 선/원 위) / `figure_solid.verify_solid`.
    4. 작도: 평면 도형은 `FigureSet.spec`(FigureSpec v2 — 라벨 자동 배치)부터, 스펙이 못 그리는
       것은 `pre`/`post` 덧그림 또는 `FigureSet.raw` 로 프리미티브 직접 작도.
    5. `build_figures` — 검산 누락(`unverified`) 차단 → 픽셀 검수(`lint_svg`) → PNG.
    6. 지면 폭 = viewBox 폭 × 0.17mm(상한 68mm, `width_mm`) — 모든 그림의 글자·선이 같은
       크기로 인쇄된다(글자 16.8 → 약 8pt, 본선 1.9 → 0.32mm).

표준 라이브러리 + 엔진 모듈(`figure_svg`·`figure_scene`·`figure_quality`·`label_markup`)만
최상단에서 import 한다 — numpy·PIL 은 래스터 보조 함수 **안**에서만(엔진과 같은 규칙).
"""
from __future__ import annotations

import math
import os
import re
import sys
from typing import Callable, Iterable, Mapping, Sequence

from core.figure_quality import sanitize_svg
from core.figure_scene import compile_figure_spec
from core.figure_svg import curve_path, isect, line, lint_svg, meas, svg_to_png_bytes, unverified
from core.label_markup import label_pieces_svg, label_width_em

__all__ = [
    "FS", "SPEC_FONT", "ITALIC_FONT", "LIGHT", "DARK", "HIDDEN", "WIDTH_K_MM", "WIDTH_CAP_MM",
    "P", "add", "dist", "unit", "off", "polar", "isect", "foot", "bis_pt", "angle_at", "frame", "sss",
    "ltext", "rtext", "pt_label", "curve_pt", "adim", "dots", "poly",
    "oblique", "fit", "box", "box_parts",
    "seg", "ang", "dim", "spec_svg", "raw_svg", "viewbox", "width_mm",
    "FigureSet", "build_figures", "flatten_white",
]

Pt = tuple[float, float]

FS = 16.8   # 덧그림 글자 크기 = FigureSpec 라벨(렌더 SVG font-size 실측) — 두 갈래가 같은 크기로 보인다
SPEC_FONT = 'font-family="Cambria Math, HancomEQN, Times New Roman, serif"'
ITALIC_FONT = "Cambria, Times New Roman, serif"   # StyleProfile.font_family_italic 과 같다
LIGHT, DARK = "#ececec", "#c6c6c6"                 # 입체 앞면(옅은 음영) · 옆면(진한 음영)
HIDDEN = {"w": 1.0, "dash": "5 4"}                  # 숨은 모서리 — line(p, q, **HIDDEN)
WIDTH_K_MM = 0.17                                   # viewBox 1 단위 = 0.17mm
WIDTH_CAP_MM = 68                                   # 2단 시험지 한 단 안쪽


# ── 2D 기하(화면 좌표, y 아래로 증가) ─────────────────────────────────────────
def P(x, y) -> Pt:
    return (float(x), float(y))


def add(p, q, t=1.0) -> Pt:
    """p 에서 q 쪽으로 t 만큼(t=1 이면 q, 0.5 면 중점)."""
    return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)


def dist(p, q) -> float:
    return math.hypot(q[0] - p[0], q[1] - p[1])


def unit(p, q) -> Pt:
    L = dist(p, q)
    return ((q[0] - p[0]) / L, (q[1] - p[1]) / L)


def off(p, dx, dy) -> Pt:
    return (p[0] + dx, p[1] + dy)


def polar(p, ang_deg, r) -> Pt:
    """수학각(반시계, y 위) → 화면 좌표."""
    a = math.radians(ang_deg)
    return (p[0] + r * math.cos(a), p[1] - r * math.sin(a))


def foot(p, a, b) -> Pt:
    """p 에서 직선 ab 에 내린 수선의 발."""
    ux, uy = b[0] - a[0], b[1] - a[1]
    t = ((p[0] - a[0]) * ux + (p[1] - a[1]) * uy) / (ux * ux + uy * uy)
    return (a[0] + ux * t, a[1] + uy * t)


def bis_pt(v, p1, p2, d) -> Pt:
    """∠p1·v·p2 의 이등분선 위, v 에서 d 만큼 떨어진 점."""
    u1, u2 = unit(v, p1), unit(v, p2)
    bx, by = u1[0] + u2[0], u1[1] + u2[1]
    L = math.hypot(bx, by)
    return (v[0] + bx / L * d, v[1] + by / L * d)


def angle_at(v, p1, p2) -> float:
    """∠p1·v·p2 (도)."""
    u1, u2 = unit(v, p1), unit(v, p2)
    return math.degrees(math.acos(max(-1.0, min(1.0, u1[0] * u2[0] + u1[1] * u2[1]))))


def frame(ox, oy, s) -> Callable[[float, float], Pt]:
    """수학 좌표(y 위, 단위) → 화면 좌표. ⚠️ 그래프는 x·y 축 단위를 **같게** 둔다(등방)."""
    return lambda x, y: P(ox + x * s, oy - y * s)


def sss(a, b, c) -> Pt:
    """밑변 c(B=(0,0), C=(c,0)), AB=a, AC=b 인 삼각형의 A(수학 좌표)."""
    x = (a * a + c * c - b * b) / (2 * c)
    return (x, math.sqrt(a * a - x * x))


# ── 덧그림 조판(스펙 라벨과 같은 글꼴·크기) ──────────────────────────────────
def ltext(x, y, label, fs=FS, anc="middle") -> str:
    """(x, y) 를 세로 중심으로 하는 라벨 — 변수 이탤릭·숫자 정자·° 위첨자(label_markup)."""
    return (f'<text x="{x:.2f}" y="{y + 0.35 * fs:.2f}" {SPEC_FONT} font-size="{fs}" '
            f'text-anchor="{anc}" fill="#111111">{label_pieces_svg(label, fs, ITALIC_FONT)}</text>')


def rtext(x, y, s, fs=FS, anc="middle") -> str:
    """전부 정자인 라벨 — 점 이름, '30 m' 처럼 단위가 붙은 수치.

    ⚠️ `ltext("m")` 은 한 글자 m 을 **변수로 보고 기울인다**. 단위 m·g 는 이걸로 쓴다.
    """
    return (f'<text x="{x:.2f}" y="{y + 0.35 * fs:.2f}" {SPEC_FONT} font-size="{fs}" '
            f'text-anchor="{anc}" font-style="normal" fill="#111111">{s}</text>')


def pt_label(p, name, dx, dy) -> str:
    """점 이름(정자)을 p 에서 (dx, dy) 떨어진 곳에. 선·면 밖에 둘 것 — halo 로 선을 끊으면 안 된다."""
    return rtext(p[0] + dx, p[1] + dy, name)


def curve_pt(p, q, o, t) -> tuple[Pt, Pt]:
    """`meas()` 치수 곡선 위의 점과 바깥쪽 단위 법선."""
    ux, uy = unit(p, q)
    nx, ny = -uy, ux
    end = 1.5 * (1.0 if o >= 0 else -1.0)
    s = (p[0] + nx * end, p[1] + ny * end)
    e = (q[0] + nx * end, q[1] + ny * end)
    c_lat = 2.0 * o - end
    c = ((p[0] + q[0]) / 2 + nx * c_lat, (p[1] + q[1]) / 2 + ny * c_lat)
    x = (1 - t) ** 2 * s[0] + 2 * t * (1 - t) * c[0] + t * t * e[0]
    y = (1 - t) ** 2 * s[1] + 2 * t * (1 - t) * c[1] + t * t * e[1]
    sg = 1.0 if o >= 0 else -1.0
    return (x, y), (nx * sg, ny * sg)


def adim(p, q, o, label, t=0.5, gap=3.5, fs=FS, upright=False, width_em=None) -> str:
    """치수 점선(양끝이 p·q 에 닿음) + 곡선 **바깥**에 붙인 라벨.

    o 부호 = 볼록한 쪽. 법선은 p→q 의 ``(-uy, ux)`` — 부호를 반대로 주면 치수선이 도형
    **안쪽**으로 들어간다(오성중 q2 에서 여러 번). upright=True 면 '30 m' 처럼 전부 정자.
    """
    (x, y), (nx, ny) = curve_pt(p, q, o, t)
    hw = (width_em if width_em is not None else label_width_em(label)) * fs / 2
    hh = 0.36 * fs
    d = gap + abs(hw * nx) + abs(hh * ny)
    lab = rtext(x + nx * d, y + ny * d, label, fs) if upright else ltext(x + nx * d, y + ny * d, label, fs)
    return meas(p[0], p[1], q[0], q[1], o) + lab


def dots(*ps, r=2.3) -> str:
    """점 표시(채운 원)."""
    return "".join(f'<circle cx="{p[0]:.2f}" cy="{p[1]:.2f}" r="{r}" fill="#111111"/>' for p in ps)


def poly(pts, fill) -> str:
    """선 없이 채운 다각형(면 음영). 외곽선은 따로 `line` 으로 긋는다."""
    return curve_path(pts, w=0.01, close=True, fill=fill)


# ── 입체(사투영) ──────────────────────────────────────────────────────────────
def oblique(origin, s, depth_ratio, depth_deg, zs=1.0) -> Callable[[Sequence[float]], Pt]:
    """사투영 — x 오른쪽, y 깊이(뒤), z 위. `figure_solid.View` 와 같은 식에 높이 배율 zs.

    zs 는 원본 그림이 높이를 과장해 그렸을 때(제일고 서술형 4: AE=1 을 2배) 따라가는 용도.
    아랫면(z=0)의 비례는 그대로라 그 위의 점(수선의 발 등) 위치는 정확하다 — 쓰면 기록할 것.
    """
    a = math.radians(depth_deg)

    def f(p):
        x, y, z = p
        return (origin[0] + s * (x + depth_ratio * y * math.cos(a)),
                origin[1] - s * (zs * z + depth_ratio * y * math.sin(a)))
    return f


def fit(pts: Iterable[Pt], pad=(24, 24, 24, 24)) -> tuple[Pt, Pt]:
    """점들의 범위 + 여백(왼·위·오른·아래) → (이동량, viewBox 크기). 잘림 방지.

    사용: ``org, wh = fit([proj0(v) for v in verts]); proj = oblique(org, …); raw_svg(k, *wh, …)``
    """
    pts = list(pts)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    dx, dy = pad[0] - min(xs), pad[1] - min(ys)
    return (dx, dy), (max(xs) - min(xs) + pad[0] + pad[2], max(ys) - min(ys) + pad[1] + pad[3])


def box(xw, yd, zh) -> dict[str, tuple[float, float, float]]:
    """직육면체 ABCD-EFGH(윗면 ABCD: A 앞 왼쪽, B 앞 오른쪽, C 뒤 오른쪽, D 뒤 왼쪽)."""
    return {"A": (0, 0, zh), "B": (xw, 0, zh), "C": (xw, yd, zh), "D": (0, yd, zh),
            "E": (0, 0, 0), "F": (xw, 0, 0), "G": (xw, yd, 0), "H": (0, yd, 0)}


def box_parts(p: Mapping[str, Pt], light=LIGHT, dark=DARK) -> list[str]:
    """투영된 직육면체 꼭짓점 → 음영 두 면 + 보이는 모서리 실선 + 숨은 모서리 점선."""
    A, B, C, D, E, F, G, H = (p[k] for k in "ABCDEFGH")
    out = [poly([A, B, F, E], light), poly([B, C, G, F], dark)]
    out += [line(D, H, **HIDDEN), line(H, E, **HIDDEN), line(H, G, **HIDDEN)]
    out += [line(a, b, w=1.9) for a, b in ((A, B), (B, C), (C, D), (D, A), (A, E), (B, F), (C, G),
                                           (E, F), (F, G))]
    return out


# ── FigureSpec 조립 ──────────────────────────────────────────────────────────
def seg(p, q, dash=None, ticks=0, parallel=0) -> dict:
    d = {"points": [p, q]}
    if dash:
        d["dash"] = dash
    if ticks:
        d["ticks"] = ticks
    if parallel:
        d["parallel"] = parallel
    return d


def ang(v, p1, p2, label=None, **kw) -> dict:
    d = {"vertex": v, "points": [p1, p2]}
    if label is not None:
        d["label"] = label
    d.update(kw)
    return d


def dim(p1, p2, label, side="auto", **kw) -> dict:
    """⚠️ 스펙 치수는 **한 선분**에만 걸린다 — 점이 끼어 나뉜 구간은 `post` 에서 `adim` 으로."""
    d = {"points": [p1, p2], "label": label, "side": side}
    d.update(kw)
    return d


def spec_svg(pts, segs, angles=None, dims=None, labels=None, regions=None,
             circles=None, pre=None, post=None) -> tuple[str, dict]:
    """FigureSpec v2 → (정제된 SVG, 스펙). 라벨은 엔진이 자동 배치한다.

    pre/post 는 ``(sh) -> str`` — 스펙이 못 그리는 덧그림. ``sh(p)`` 는 스펙 좌표를 렌더
    좌표로 옮긴다(엔진이 여백을 위해 캔버스를 평행이동하므로 **반드시 sh 를 거칠 것**).
    pre 는 배경 rect 바로 뒤(잉크 아래), post 는 맨 위.
    """
    spec = {"version": 2,
            "points": {k: [round(v[0], 3), round(v[1], 3)] for k, v in pts.items()},
            "segments": segs}
    if angles:
        spec["angles"] = angles
    if dims:
        spec["dimensions"] = dims
    if regions:
        spec["regions"] = regions
    if circles:
        spec["circles"] = circles
    spec["labels"] = labels if labels is not None else {
        k: k for k in pts if len(k) == 1 and k.isupper()}
    scene = compile_figure_spec(spec)
    tx, ty = scene.resolve().translation
    svg = scene.render_svg()

    def sh(p):
        return (p[0] + tx, p[1] + ty)

    if pre:
        i = svg.index("/>", svg.index("<rect")) + 2
        svg = svg[:i] + "\n" + pre(sh) + svg[i:]
    if post:
        i = svg.rindex("</svg>")
        svg = svg[:i] + post(sh) + "\n" + svg[i:]
    return sanitize_svg(svg), spec


def raw_svg(w, h, *parts) -> str:
    """프리미티브 조각들 → 정제된 SVG(viewBox 0 0 w h)."""
    return sanitize_svg(f'<svg viewBox="0 0 {w:.0f} {h:.0f}" xmlns="http://www.w3.org/2000/svg">\n'
                        + "\n".join(parts) + "\n</svg>")


_VIEWBOX_RE = re.compile(r'viewBox="0 0 ([\d.]+) ([\d.]+)"')


def viewbox(svg: str) -> tuple[float, float]:
    m = _VIEWBOX_RE.search(svg)
    if not m:
        raise ValueError("viewBox 를 읽지 못함")
    return float(m.group(1)), float(m.group(2))


def width_mm(svg: str, k: float = WIDTH_K_MM, cap: float = WIDTH_CAP_MM) -> float:
    """지면 삽입 폭(mm) = viewBox 폭 × k, 상한 cap. 높이는 비율대로."""
    return min(cap, round(viewbox(svg)[0] * k))


# ── 빌드(검산 누락 차단 → 픽셀 검수 → PNG) ─────────────────────────────────
def build_figures(svgs: Mapping[str, str], out_dir: str, *, scope: str,
                  lint_exempt: Mapping[str, Sequence[str]] | None = None,
                  only: Sequence[str] = (), png_width: int | Mapping[str, int] = 900,
                  strict: bool = True) -> dict[str, dict]:
    """그림 묶음을 검사하고 PNG 로 굽는다. ``{key: {"png": 경로, "issues": [...]}}`` 를 돌려준다.

    scope: `verify_figure`/`verify_solid` 를 부른 **시험지 스크립트의 경로**(보통 ``__file__``).
    lint_exempt: ``{key: ("라벨-선 겹침: 'B'", …)}`` — 의도한 예외만, 이유를 주석으로 남길 것.
    strict: lint 위반이 남으면 ValueError(종전 스크립트의 SystemExit 자리).
    """
    miss = unverified(svgs, scope=scope)
    if miss:
        raise ValueError(f"검산 누락(verify_figure/verify_solid 미호출): {miss}")
    exempt = lint_exempt or {}
    os.makedirs(out_dir, exist_ok=True)
    report: dict[str, dict] = {}
    bad = []
    for k, svg in svgs.items():
        if only and k not in only:
            continue
        issues = [i for i in lint_svg(svg) if not any(i.startswith(x) for x in exempt.get(k, ()))]
        if issues:
            bad.append(f"{k}: {'; '.join(issues)}")
        w = png_width.get(k, 900) if isinstance(png_width, Mapping) else png_width
        png = svg_to_png_bytes(svg, width=w)
        if not png:
            raise RuntimeError(f"{k} PNG 렌더 실패(resvg_py 필요)")
        path = os.path.join(out_dir, f"{k}.png")
        with open(path, "wb") as f:
            f.write(png)
        report[k] = {"png": path, "issues": issues}
    if bad and strict:
        raise ValueError("lint 실패:\n" + "\n".join(bad))
    return report


def flatten_white(png: bytes) -> bytes:
    """투명 배경 PNG → 흰 배경 PNG. ⚠️ 문서(HWP 등)에 넣기 전 필수 — 투명이 검게 변한다."""
    import io

    from PIL import Image

    with Image.open(io.BytesIO(png)) as im0:
        rgba = im0.convert("RGBA")
    bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    buf = io.BytesIO()
    Image.alpha_composite(bg, rgba).convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


class FigureSet:
    """시험지 하나의 그림 묶음. 만든 스크립트의 경로를 기억해 검산 등록부와 맞춘다.

    ::

        figs = FigureSet()
        verify_figure("q3", lengths=[(5, A, B), (12, B, C)])
        figs.spec("q3", pts, [seg("A", "B"), seg("B", "C")], dims={"dAB": dim("A", "B", "5")})
        figs.raw("q7", *wh, *parts)
        if __name__ == "__main__":
            figs.build(OUT, lint_exempt=LINT_EXEMPT)
    """

    def __init__(self, scope: str | None = None) -> None:
        if scope is None:
            g = sys._getframe(1).f_globals
            scope = str(g.get("__file__", g.get("__name__", "?")))
        self.scope = scope
        self.svgs: dict[str, str] = {}

    def spec(self, key, pts, segs, **kw) -> dict:
        svg, spec = spec_svg(pts, segs, **kw)
        self.svgs[key] = svg
        return spec

    def raw(self, key, w, h, *parts) -> str:
        self.svgs[key] = raw_svg(w, h, *parts)
        return self.svgs[key]

    def widths(self, keys: Mapping[str, str] | None = None, k: float = WIDTH_K_MM,
               cap: float = WIDTH_CAP_MM) -> dict[str, dict]:
        """``{문항: {"key": 그림키, "width_mm": 폭}}`` — keys 는 ``{문항: 그림키}``(없으면 그림키 그대로)."""
        keys = keys or {key: key for key in self.svgs}
        return {q: {"key": fk, "width_mm": width_mm(self.svgs[fk], k, cap)} for q, fk in keys.items()}

    def build(self, out_dir: str, **kw) -> dict[str, dict]:
        return build_figures(self.svgs, out_dir, scope=self.scope, **kw)
