# -*- coding: utf-8 -*-
"""수학 도형 SVG 작도 엔진 — 교과서 규격 프리미티브(운암중3 25-2 사용자 검수로 확정).

세션/자동 변환에서 그림을 **정의값 기하**(각도·비율 실계산)로 작도할 때 쓴다.
tkz-euclide(LaTeX) 관행을 파이썬-SVG 로 옮긴 것 — 의존성 0, 렌더는
`core.figure_generator._svg_to_png_bytes`(resvg). 규격(전부 사용자 확정 2026-08-11):

1. **각 호(arc)** 는 두 변의 실제 방향각 사이에만 — 눈대중 각도로 그리면 변 밖으로
   삐져나온다(운암중 q9 120°). 방향각 감소면 sweep 자동 반전(q2 45° 뒤집힘).
2. **치수 점선(meas)** 은 끝이 꼭짓점 옆 3px 에 감겨 붙고 가운데만 볼록 — 일정
   오프셋을 끝까지 유지하면 예각 꼭짓점에서 모서리를 지나친다(q2 C 45°).
   길이 라벨이 있는 구간은 **빠짐없이** 점선을 단다(s1 3cm 누락 지적).
3. **라벨(dim_label)** 은 점선 곡선 정점 위, 흰 halo(paint-order stroke)로
   배경처리되어 점선이 라벨 뒤에서 끊긴다(알지오매스 관행).
4. **근호(sqrt_label)** 는 유니코드 √ 글리프 금지(vinculum 없음) — 선으로 작도.
5. **같음 표시(eq_tick)** 는 변에 수직인 짧은 선분(사선 금지, q7).
6. 본선 2px 검정 / 보조선·축·점선 1px / 배경 투명 / 라벨 Times+Batang serif.
7. 축은 원점을 지나 튀어나가지 않는다(q3). 라벨은 선·호·직각표시와 겹침 금지.
8. 사진 문항은 재작도하지 않는다 — 원본 크롭 + 노이즈/채점기호 정리(s2).
9. **각 라벨 = halo_angle**(이등분선 위 halo) — 좁은 각은 어디 놓아도 두 변에
   닿는다(오성중 q4 54°·왕선중 q5 20°). **호·지름 길이 라벨 = 곡선 위 halo_text**.
10. **직각 표시 = rangle_at**(두 참조점에서 방향 계산) — 단위벡터 눈대중 하드코딩이
   왕선중 q5 E 직각을 어긋나게 했다.
11. 축을 옮기면 **눈금 라벨도 함께**(왕선중 q18: 축만 +14 내려 12개 라벨이 축을 관통).
12. arc() 를 ray_angle 결과로 직접 부를 땐 랩어라운드 자동 정규화가 있지만, 대원호가
   필요하면 large_ok=True 를 명시한다.

**완성 판정 = lint_svg() 통과(빈 리스트)** — 잘림·라벨-선 겹침·라벨-라벨 겹침·떠 있는
길이 라벨을 실제 렌더 픽셀로 검사한다. 렌더가 안 깨졌다고, 몽타주가 그럴듯하다고
'완성'이라 부르지 않는다(사용자 2026-08-12 두 차례 반려 실측). 시험지 스크립트는
기하 헬퍼(circle_pt/seci/isect/tangent_isect/line/txt/dot/circ)를 여기서 import
한다 — 복붙 금지(같은 버그가 시험지마다 재발한다).

⚠️ SVG 문자열 치환으로 그림을 고칠 때는 **반드시 assert** — 조용한 불발이 라벨
실종을 만든다(s1 실측).
"""
from __future__ import annotations

from dataclasses import dataclass
import sys as _sys  # noqa: F401  (스코프 판별용)
from html import escape as _escape
import io as _io
import math
import re as _re
from typing import Sequence

FONT = 'font-family="Times New Roman, Batang, serif"'
IT = f'{FONT} font-style="italic"'
_EPS = 1e-9


@dataclass(frozen=True, slots=True)
class SVGTextRun:
    """A safe structured text run for the few SVG labels needing emphasis."""

    text: str
    italic: bool = False
    bold: bool = False


def _text_runs_markup(runs: Sequence[SVGTextRun]) -> str:
    if isinstance(runs, (str, bytes)) or not runs:
        raise ValueError("text runs: SVGTextRun 목록이 필요함")
    rendered: list[str] = []
    for run in runs:
        if not isinstance(run, SVGTextRun):
            raise TypeError("text runs: SVGTextRun만 허용")
        if not isinstance(run.text, str) or not run.text:
            raise ValueError("text runs: 빈 문자열은 허용하지 않음")
        attrs = []
        if run.italic:
            attrs.append('font-style="italic"')
        if run.bold:
            attrs.append('font-weight="bold"')
        if not attrs:
            _no_preescape(run.text, "SVGTextRun")
            rendered.append(_escape(run.text))
        else:
            attr_text = " " + " ".join(attrs)
            _no_preescape(run.text, "SVGTextRun")
            rendered.append(f"<tspan{attr_text}>{_escape(run.text)}</tspan>")
    return "".join(rendered)


_ENTITY_RE = _re.compile(r"&(?:[A-Za-z][A-Za-z0-9]{1,9}|#\d{1,6}|#[xX][0-9A-Fa-f]{1,6});")
_TSPAN_RE = _re.compile(r"</?tspan(?:\s[^<>]*)?/?>")


def _no_preescape(text: str, what: str) -> None:
    """이미 escape 된 문자열이 다시 들어오는 것을 입구에서 막는다.

    호출부가 "&lt; 보 기 &gt;" 처럼 미리 escape 해서 넘기면 엔진이 한 번 더
    escape 해 **화면에 '&lt; 보 기 &gt;' 가 그대로 인쇄**된다(오성중 q16 실측).
    라벨은 언제나 원문("<보기>")으로 넘기고 escape 는 엔진에 맡긴다.
    """
    hit = _ENTITY_RE.search(text)
    if hit:
        raise ValueError(
            f"{what}: 이미 escape 된 XML 엔티티 {hit.group(0)!r} 가 들어왔다 — "
            "원문 그대로(예: '<보기>') 넘길 것. 엔진이 한 번만 escape 한다")


def _plain(value, what: str) -> str:
    """평문 라벨 → 안전한 XML 텍스트(이중 escape 차단 포함)."""
    text = str(value)
    _no_preescape(text, what)
    return _escape(text)


def _markup(content, what: str) -> str:
    """<tspan> 만 허용하는 원시 마크업 검증 — 그 외 '<'/'>' 는 XML 을 깨뜨린다."""
    text = str(content)
    _no_preescape(text, what)
    residue = _TSPAN_RE.sub("", text)
    if "<" in residue or ">" in residue:
        raise ValueError(
            f"{what}: 원문 '<'/'>' 는 XML 을 깨뜨린다 — runs=[SVGTextRun('<보기>')] "
            "로 넘기거나 txt() 를 쓸 것")
    return text


def _finite(*values: float, what: str = "기하값") -> None:
    """NaN/무한대가 SVG 좌표로 새지 않게 공개 프리미티브 입구에서 차단."""
    if not all(math.isfinite(float(v)) for v in values):
        raise ValueError(f"{what}: 유한한 수만 허용")


def _nonzero_segment(px: float, py: float, qx: float, qy: float,
                     what: str) -> float:
    _finite(px, py, qx, qy, what=what)
    length = math.hypot(qx - px, qy - py)
    if length <= _EPS:
        raise ValueError(f"{what}: 두 점이 같아 방향을 정할 수 없음")
    return length


def pt(x: float, y: float) -> str:
    _finite(x, y, what="pt")
    return f"{x:.1f},{y:.1f}"


def arc(cx, cy, r, a0, a1, sweep=None, large_ok=False) -> str:
    """중심 (cx,cy)·반지름 r, 수학각 a0→a1(도)의 원호 path(SVG y-down 보정).

    각 표시용이면 a0·a1 은 꼭짓점에서 본 **두 변의 실제 방향각**이어야 한다.
    sweep 미지정 시 방향에서 자동 결정(감소 방향 반전).
    """
    _finite(cx, cy, r, a0, a1, what="arc")
    if r <= 0:
        raise ValueError("arc: 반지름은 양수여야 함")
    span = abs(a1 - a0)
    if span <= _EPS or abs(span % 360.0) <= _EPS:
        raise ValueError("arc: 시작각과 끝각은 서로 다른 방향이어야 함")
    if abs(a1 - a0) > 180 and not large_ok:
        # ray_angle 이 (−180,180] 을 주므로 감산이 랩어라운드하면 대원호가 된다
        # (왕선중 q7 호 '30' 이 330° 대원호로 렌더). 대원호가 진짜 필요하면 large_ok=True.
        a1 = a0 + ((a1 - a0 + 180.0) % 360.0 - 180.0)
    if sweep is None:
        sweep = 0 if a1 > a0 else 1
    x0, y0 = cx + r * math.cos(math.radians(a0)), cy - r * math.sin(math.radians(a0))
    x1, y1 = cx + r * math.cos(math.radians(a1)), cy - r * math.sin(math.radians(a1))
    large = 1 if abs(a1 - a0) > 180 else 0
    return f"M {x0:.1f} {y0:.1f} A {r} {r} 0 {large} {sweep} {x1:.1f} {y1:.1f}"


def ray_angle(vx, vy, px, py) -> float:
    """꼭짓점 v 에서 점 p 를 향한 수학각(도) — 각 호의 a0/a1 로 쓴다."""
    _nonzero_segment(vx, vy, px, py, "ray_angle")
    return math.degrees(math.atan2(-(py - vy), px - vx))


def angle_arc(vx, vy, p1, p2, r=26) -> str:
    """꼭짓점 v 의 각 표시 호 — 변 v→p1 에서 v→p2 까지 **작은 쪽**으로 정확히.

    ⚠️ atan2 랩어라운드 정규화 필수 — 206.5° 가 −153.5° 로 나오면 |Δ|>180 이 되어
    반대쪽 큰 호가 그려진다(오성중 q7 53° 가 307° 호로 렌더된 실측 버그).
    """
    a0 = ray_angle(vx, vy, *p1)
    a1 = ray_angle(vx, vy, *p2)
    da = (a1 - a0 + 180.0) % 360.0 - 180.0
    return arc(vx, vy, r, a0, a0 + da)


def meas(px_, py_, qx_, qy_, off=10.0, ins_p=0.0, ins_q=0.0) -> str:
    """길이 치수 점선 — **양끝이 잰 두 점에 정확히 닿고** 가운데만 |off| 볼록.

    off 부호로 쪽 선택(법선 n=(-uy,ux): 수평 좌→우 +off=아래).

    ⚠️ 접선방향 인셋(ins_p/ins_q)의 기본값은 **0** 이다. 예전 기본 3px 는 긴
    구간에선 안 보이지만 짧은 구간(오성중 q2 의 P→B = 32px)에서는 19% 를 깎아
    "길이 표현이 짧아 보인다"는 지적을 받았다 — 원본은 점선이 점 P 에서 시작해
    점 B 에서 끝난다(고배율 실측). 치수는 **잰 두 점을 그대로 잇는다**.
    끝을 일부러 띄워야 하는 특수한 경우에만 ins 를 준다."""
    L = _nonzero_segment(px_, py_, qx_, qy_, "meas")
    ux_, uy_ = (qx_ - px_) / L, (qy_ - py_) / L
    nx_, ny_ = -uy_, ux_
    end = 1.5 * (1.0 if off >= 0 else -1.0)   # 끝의 법선 방향 살짝 감김
    sx_, sy_ = px_ + ux_ * ins_p + nx_ * end, py_ + uy_ * ins_p + ny_ * end
    ex_, ey_ = qx_ - ux_ * ins_q + nx_ * end, qy_ - uy_ * ins_q + ny_ * end
    c_lat = 2.0 * off - end
    cx_, cy_ = (px_ + qx_) / 2 + nx_ * c_lat, (py_ + qy_) / 2 + ny_ * c_lat
    return (f'<path d="M {sx_:.1f} {sy_:.1f} Q {cx_:.1f} {cy_:.1f} {ex_:.1f} {ey_:.1f}" '
            f'fill="none" stroke="#000" stroke-width="1.4" stroke-dasharray="6 4"/>')


_LABEL_CLEAR = 1.5      # 라벨 상자(+halo)와 실선 사이 최소 여유(SVG 단위)


def _label_push(nx_, ny_, off, text_len, fs):
    """축정렬 텍스트 상자가 잰 선분을 침범하지 않도록 라벨을 더 밀 거리.

    상자 반폭 w·반높이 h 의 **법선 방향 최대 도달거리**는 |w·n_x| + |h·n_y| 다.
    기울어진 선분에서 이 값이 off 를 넘으면 halo 가 실선을 지운다(실측: 37° 에서
    reach 13.7 > off 10 → 오성중 s1 의 변 AD 절단). 필요한 만큼만 바깥으로 민다.
    """
    w = 0.30 * fs * max(1, text_len)          # 반폭(Times 근사 0.60em/글자)
    h = 0.38 * fs                              # 반높이(대문자 높이 ~0.7em)
    halo = 0.5 * (fs * 0.5)                    # halo stroke 의 절반
    reach = abs(w * nx_) + abs(h * ny_) + halo + _LABEL_CLEAR
    return max(0.0, reach - abs(off))


def _dim_label_content(px_, py_, qx_, qy_, off, content, fs=13,
                       text_len=None, t=0.5) -> str:
    L = _nonzero_segment(px_, py_, qx_, qy_, "dim_label")
    _finite(off, fs, what="dim_label")
    if fs <= 0:
        raise ValueError("dim_label: 글자 크기는 양수여야 함")
    nx_, ny_ = -(qy_ - py_) / L, (qx_ - px_) / L
    if text_len is None:
        text_len = len(_re.sub(r"<[^>]+>", "", content))
    push = _label_push(nx_, ny_, off, text_len, fs)
    off = off + (push if off >= 0 else -push)
    if not 0.0 <= t <= 1.0:
        raise ValueError('dim_label: t 는 0~1 (선분 위 위치)')
    bx_, by_ = px_ + (qx_ - px_) * t, py_ + (qy_ - py_) * t
    mx_, my_ = bx_ + nx_ * off, by_ + ny_ * off
    return (f'<text x="{mx_:.1f}" y="{my_ + 0.35 * fs:.1f}" font-size="{fs}" {FONT} '
            f'text-anchor="middle" paint-order="stroke" stroke="#fff" '
            f'stroke-width="{fs * 0.5:.0f}" stroke-linejoin="round">{content}</text>')


def dim_label(px_, py_, qx_, qy_, off, txt, fs=15, t=0.5) -> str:
    """meas() 곡선 위 **plain text** 라벨(XML은 항상 escape).

    t 는 선분 위 위치(0=시작점, 0.5=중점, 1=끝점). 꼭짓점에서 여러 선이 모여
    중점 배치가 다른 선을 가리는 경우에만 조정한다(오성중 q5 '4cm').
    """

    return _dim_label_content(px_, py_, qx_, qy_, off, _plain(txt, "dim_label"),
                              fs, t=t)


def dim_label_runs(px_, py_, qx_, qy_, off,
                   runs: Sequence[SVGTextRun], fs=15) -> str:
    """Structured-run variant of :func:`dim_label` without raw XML input."""

    return _dim_label_content(
        px_, py_, qx_, qy_, off, _text_runs_markup(runs), fs)


def measured(px_, py_, qx_, qy_, off, txt, fs=15, ins_p=0.0, ins_q=0.0,
             t=0.5) -> str:
    """치수 점선 + halo 라벨 한 번에 — 길이 표기의 표준형.

    인셋 기본 0 = **양끝이 잰 두 점에 정확히 닿는다**(meas 참고).
    """
    return (meas(px_, py_, qx_, qy_, off, ins_p, ins_q)
            + "\n" + dim_label(px_, py_, qx_, qy_, off, txt, fs, t=t))


def measured_runs(px_, py_, qx_, qy_, off, runs: Sequence[SVGTextRun],
                  fs=15, ins_p=0.0, ins_q=0.0) -> str:
    """Safe structured-run dimension curve + label."""

    return (meas(px_, py_, qx_, qy_, off, ins_p, ins_q)
            + "\n" + dim_label_runs(px_, py_, qx_, qy_, off, runs, fs))


def arc_measured(cx, cy, r, a0, a1, txt=None, runs=None, end_off=3.0,
                 bow=15.0, label_gap=12.0, fs=15) -> str:
    """호(arc)의 길이 치수 — 양 끝은 원주에 붙고 가운데만 볼록한 점선 + 바깥 라벨.

    원호와 **같은 곡률의 동심호로 그리면 안 된다** — 원본 인쇄는 끝이 원에 감기고
    가운데가 더 벌어져야 "이 호의 길이"로 읽힌다(사용자 2026-08-13: "곡선과 같은
    기울어짐으로 하지말고 더 기울여야 표현가능하지 원본처럼"). 직선 치수 meas() 의
    벌어짐 규격을 호에 옮긴 것.

    ⚠️ 2차 베지에 하나로 그리면 **넓은 호에서 곡선이 원 안으로 들어간다**(s2 13π
    130° 실측). 그래서 반지름 오프셋을 sin 으로 주고 호를 따라 샘플링한다 —
    각도가 얼마든 항상 원 밖.

    txt(평문) 또는 runs(SVGTextRun 목록, 이탤릭 x 등) 중 하나를 준다.
    """
    if (txt is None) == (runs is None):
        raise ValueError("arc_measured: txt 또는 runs 중 하나만 지정")
    _finite(cx, cy, r, end_off, bow, what="arc_measured")
    if r <= 0:
        raise ValueError("arc_measured: 반지름은 양수여야 함")
    da = (a1 - a0 + 180.0) % 360.0 - 180.0
    if abs(da) <= _EPS:
        raise ValueError("arc_measured: 시작각과 끝각이 같음")
    steps = max(12, int(abs(da) / 3.0))
    pts = []
    for i in range(steps + 1):
        t = i / steps
        rr = r + end_off + bow * math.sin(math.pi * t)
        pts.append(circle_pt(cx, cy, a0 + da * t, rr))
    d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts)
    mid = a0 + da / 2.0
    lx, ly = circle_pt(cx, cy, mid, r + end_off + bow + label_gap)
    content = _escape(str(txt)) if runs is None else _text_runs_markup(runs)
    path = (f'<path d="{d}" fill="none" stroke="#000" stroke-width="1.4" '
            f'stroke-dasharray="6 4"/>')
    label = (f'<text x="{lx:.1f}" y="{ly + 0.35 * fs:.1f}" font-size="{fs}" {FONT} '
             f'text-anchor="middle" paint-order="stroke" stroke="#fff" '
             f'stroke-width="{max(4.0, fs * 0.45):.0f}" '
             f'stroke-linejoin="round">{content}</text>')
    return path + chr(10) + label


def bisect_pt(vx, vy, p1, p2, d):
    """꼭짓점 v 의 두 변(v→p1·v→p2) **이등분선 위** d 만큼 떨어진 점.

    각 라벨(halo_angle)과 이등분 표시 점(오성중 q9 P 의 · ·)이 같은 계산이다.
    """
    a0 = ray_angle(vx, vy, *p1)
    da = (ray_angle(vx, vy, *p2) - a0 + 180.0) % 360.0 - 180.0
    return circle_pt(vx, vy, a0 + da / 2.0, d)



def rangle(x, y, ux, uy, vx, vy, s=11) -> str:
    """직각 표시 — 점 (x,y)에서 단위방향 u·v 가 이루는 작은 사각형."""
    _finite(x, y, ux, uy, vx, vy, s, what="rangle")
    if s <= 0:
        raise ValueError("rangle: 크기는 양수여야 함")
    return (f'<path d="M {x + ux * s:.1f} {y + uy * s:.1f} '
            f'L {x + (ux + vx) * s:.1f} {y + (uy + vy) * s:.1f} '
            f'L {x + vx * s:.1f} {y + vy * s:.1f}" '
            f'fill="none" stroke="#000" stroke-width="1"/>')


def angle_mark(vx, vy, p1, p2, r=20, n=1, gap=5, dash=True, w=1.4) -> str:
    """각 표시 호 — **점선이 기본**이고 완성된 요소를 돌려준다.

    원본 인쇄의 각 호는 점선이다(오성중 13그림 전수 대조). 호출부가 매번
    `<path d="{angle_arc(...)}" .../>` 를 손으로 쓰면 굵기·대시가 그림마다
    달라지고, 무엇보다 **묻는 각에 호를 빠뜨린다**(13그림 중 6개 누락 실측).
    문항이 묻는 각에는 예외 없이 이걸 붙인다.
    """
    dash_attr = ' stroke-dasharray="4 3"' if dash else ""
    return "".join(
        f'<path d="{angle_arc(vx, vy, p1, p2, r + i * gap)}" fill="none" '
        f'stroke="#000" stroke-width="{w}"{dash_attr}/>'
        for i in range(n))


def eq_angle(vx, vy, p1, p2, r=22, n=1, gap=5) -> str:
    """같은 각 표시 — 꼭짓점 v 의 두 변 사이에 호를 n 개(간격 gap) 겹쳐 그린다.

    등변사다리꼴 ∠B=∠C, 이등변삼각형 밑각처럼 원본에 인쇄된 등각 기호는
    반드시 재현한다(오성중 q3 에서 빠뜨려 레퍼런스보다 정보가 적었던 실측).
    """
    return angle_mark(vx, vy, p1, p2, r=r, n=n, gap=gap, dash=False)


def arc_tick(cx, cy, r, a0, a1, n=1, ln=7.0, gap=4.0, w=1.6) -> str:
    """호 위 **같은 호 표시**(반지름 방향 눈금) — 호 AB=호 BP 같은 조건의 인쇄 기호.

    원본이 조건을 그림에 눈금으로 새겨 두는데(왕선중 q6 실측) 우리가 빠뜨리면
    학생은 조건을 발문에서만 읽어야 한다 — 정보량이 원본보다 적어진다.
    """
    _finite(cx, cy, r, ln, gap, what="arc_tick")
    if r <= 0 or ln <= 0:
        raise ValueError("arc_tick: 반지름과 눈금 길이는 양수여야 함")
    da = (a1 - a0 + 180.0) % 360.0 - 180.0
    mid = a0 + da / 2.0
    out = []
    span = gap * (n - 1) / max(r, 1.0) * 57.2957795
    for i in range(n):
        ang = mid - span / 2.0 + (span * i / (n - 1) if n > 1 else 0.0)
        x0, y0 = circle_pt(cx, cy, ang, r - ln / 2.0)
        x1, y1 = circle_pt(cx, cy, ang, r + ln / 2.0)
        out.append(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" '
                   f'stroke="#000" stroke-width="{w}"/>')
    return "".join(out)


def eq_tick(p, q, ln=6.0, w=1.6) -> str:
    """같음 표시 — 선분 p–q 중점에 변과 **수직**인 짧은 선분(사선 금지)."""
    mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
    dx, dy = q[0] - p[0], q[1] - p[1]
    L = _nonzero_segment(p[0], p[1], q[0], q[1], "eq_tick")
    _finite(ln, w, what="eq_tick")
    if ln <= 0 or w <= 0:
        raise ValueError("eq_tick: 길이와 선 굵기는 양수여야 함")
    nx, ny = -dy / L, dx / L
    return (f'<line x1="{mx - ln * nx:.1f}" y1="{my - ln * ny:.1f}" '
            f'x2="{mx + ln * nx:.1f}" y2="{my + ln * ny:.1f}" '
            f'stroke="#000" stroke-width="{w}"/>')


def sqrt_label(x, y, num="2", fs=15) -> str:
    """근호를 선으로 그린 √num 라벨(가로줄 포함) — 유니코드 √ 는 희미해 금지."""
    _finite(x, y, fs, what="sqrt_label")
    if fs <= 0:
        raise ValueError("sqrt_label: 글자 크기는 양수여야 함")
    raw_num = str(num)
    w = 0.62 * fs * len(raw_num)
    num = _escape(raw_num)
    bar_y = y - 0.82 * fs
    return (f'<path d="M {x:.1f} {y - 0.38 * fs:.1f} L {x + 0.16 * fs:.1f} {y - 0.46 * fs:.1f} '
            f'L {x + 0.34 * fs:.1f} {y - 0.06 * fs:.1f} L {x + 0.58 * fs:.1f} {bar_y:.1f} '
            f'L {x + 0.58 * fs + w:.1f} {bar_y:.1f}" fill="none" stroke="#000" stroke-width="1.2"/>'
            f'<text x="{x + 0.62 * fs:.1f}" y="{y:.1f}" font-size="{fs}" {FONT}>{num}</text>')


_VAR_SPLIT_RE = _re.compile(r"[A-Za-z]+|[^A-Za-z]+")


def auto_runs(value) -> tuple[SVGTextRun, ...]:
    """라틴 문자(변수)는 이탤릭, 숫자·기호는 정자로 쪼갠 텍스트 런.

    그림 안 라벨도 본문 수식과 같은 조판 규칙을 따라야 한다 — 변수는 기울이고
    숫자는 세운다(2026-08-18 대진고 q16 `g(x)=2/a` 의 분모 a 가 정자로 나가
    사용자 지적). 한글·기호는 그대로 정자로 남는다.
    """
    text = str(value)
    if not text:
        raise ValueError("auto_runs: 빈 문자열은 허용하지 않음")
    # 쪼개고 나면 조각('&' + 'lt' + ';')이 엔티티로 안 보여 런 단위 검사를 빠져나간다
    # → 자르기 **전** 통째로 이중 escape 를 막는다.
    _no_preescape(text, "auto_runs")
    return tuple(SVGTextRun(m.group(0), italic=m.group(0).isalpha())
                 for m in _VAR_SPLIT_RE.finditer(text))


def runs_text(x, y, value, fs=13, anc="middle") -> str:
    """auto_runs 조판(변수 이탤릭)으로 찍는 한 줄 텍스트."""
    _finite(x, y, fs, what="runs_text")
    if fs <= 0:
        raise ValueError("runs_text: 글자 크기는 양수여야 함")
    if anc not in {"start", "middle", "end"}:
        raise ValueError("runs_text: text-anchor는 start/middle/end만 허용")
    body = _text_runs_markup(auto_runs(value))
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{fs}" {FONT} '
            f'text-anchor="{anc}">{body}</text>')


def frac_label(x, y, num, den, fs=13, w=None) -> str:
    """작은 분수 라벨(1/2 · 2/a) — 가로줄 + 위/아래 항, (x, y)는 가로줄 중앙.

    분자·분모의 **변수는 이탤릭, 숫자는 정자**(auto_runs). 시험지 스크립트마다
    분수를 복붙해 만들면 같은 조판 버그가 재발하므로 여기 하나만 쓴다.
    """
    _finite(x, y, fs, what="frac_label")
    if fs <= 0:
        raise ValueError("frac_label: 글자 크기는 양수여야 함")
    num_s, den_s = str(num), str(den)
    if not num_s.strip() or not den_s.strip():
        raise ValueError("frac_label: 분자와 분모는 비울 수 없음")
    if w is None:
        w = fs * 0.42 * max(len(num_s), len(den_s)) + 3
    _finite(w, what="frac_label")
    if w <= 0:
        raise ValueError("frac_label: 가로줄 반폭은 양수여야 함")
    return "\n".join([
        runs_text(x, y - 3, num_s, fs),
        f'<line x1="{x - w:.1f}" y1="{y:.1f}" x2="{x + w:.1f}" y2="{y:.1f}" '
        f'stroke="#000" stroke-width="1.2"/>',
        runs_text(x, y + fs, den_s, fs),
    ])


def halo_text(x, y, content=None, fs=12, anc="middle", runs=None) -> str:
    """흰 halo 라벨 — **선 밀집 지역의 모든 라벨은 이걸로**(왕선중 q11 x°/y° 매몰).

    content 는 평문(escape)·<tspan> 마크업만 허용. '<보기>' 처럼 원문 부등호가
    필요하면 runs=[SVGTextRun("<보기>")] 로 넘긴다.
    """
    if (content is None) == (runs is None):
        raise ValueError("halo_text: content 또는 runs 중 하나만 지정")
    body = _text_runs_markup(runs) if runs is not None else _markup(content, "halo_text")
    _finite(x, y, fs, what="halo_text")
    if fs <= 0:
        raise ValueError("halo_text: 글자 크기는 양수여야 함")
    if anc not in {"start", "middle", "end"}:
        raise ValueError("halo_text: text-anchor는 start/middle/end만 허용")
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{fs}" {FONT} text-anchor="{anc}" '
            f'paint-order="stroke" stroke="#fff" stroke-width="{max(4.0, fs * 0.45):.0f}" '
            f'stroke-linejoin="round">{body}</text>')


def halo_angle(vx, vy, p1, p2, d, content=None, fs=12, runs=None,
               clear=True) -> str:
    """각 라벨 표준형 — 꼭짓점 v 의 두 변(v→p1·v→p2) **이등분선 위**에 halo 로 얹는다.

    d 는 최소 거리이고, 라벨 상자(+halo)가 두 변을 침범하지 않도록 **필요하면 더
    민다**(clear=True). 안 그러면 흰 halo 가 각의 변(실선)을 지워 도형이 끊긴다
    — lint 규칙 7. 이등분선 위 거리 d 에서 변까지의 수직거리는 d·sin(반각) 이라
    좁은 각일수록 멀리 밀어야 한다.

    clear=False 는 기하적으로 회피 불가능한 자리(쐐기 안)에서만, 이유를 적고 쓴다.
    """
    bx, by = _angle_label_pos(vx, vy, p1, p2, d, fs, content, runs, clear)
    return halo_text(bx, by + 0.3 * fs, content, fs, runs=runs)


def _label_halfsize(content, runs, fs) -> tuple[float, float]:
    """라벨 상자의 반폭·반높이(여유 포함) — 배치 판정과 렌더가 **같은 수**를 써야 한다."""
    plain = content if runs is None else "".join(r.text for r in runs)
    n = max(1, len(_re.sub(r"<[^>]+>", "", str(plain or ""))))
    # ⚠️ 이 근사가 실제 글리프보다 작으면 배치가 "안 겹친다"고 판정한 자리를
    # 픽셀 lint 가 겹침으로 잡는다 — 그림마다 gap 을 손보게 되는 원인이었다.
    # 세로는 어센더+디센더(약 1em), 가로는 세리프 평균 자폭(약 0.64em)을 잡는다.
    return 0.32 * fs * n + _LABEL_CLEAR, 0.46 * fs + _LABEL_CLEAR


def _angle_label_pos(vx, vy, p1, p2, d, fs, content=None, runs=None,
                     clear=True) -> tuple[float, float]:
    """`halo_angle` 이 라벨을 놓을 좌표.

    ⚠️ 이 계산을 호출부가 **다시 구현하거나 마크업을 정규식으로 파싱하면** 두 값이
    갈라져 판정과 렌더가 어긋난다. 자리 판정(`angle_label`)도 이 함수를 쓴다.
    """
    if clear:
        a0 = ray_angle(vx, vy, *p1)
        da = (ray_angle(vx, vy, *p2) - a0 + 180.0) % 360.0 - 180.0
        half = math.radians(abs(da) / 2.0)
        if math.sin(half) > 1e-3:
            w, h = _label_halfsize(content, runs, fs)
            reach = math.hypot(w, h) + 0.5 * max(4.0, fs * 0.45)
            d = max(d, reach / math.sin(half))
    return bisect_pt(vx, vy, p1, p2, d)


def _arrow_head(tip, ux, uy, head) -> str:
    bx, by = tip[0] - ux * head, tip[1] - uy * head
    nx, ny = -uy, ux
    return (f'<path d="M {tip[0]:.1f} {tip[1]:.1f} '
            f'L {bx + nx * head * 0.36:.1f} {by + ny * head * 0.36:.1f} '
            f'L {bx - nx * head * 0.36:.1f} {by - ny * head * 0.36:.1f} Z" fill="#000"/>')


def leader(frm, to, arrow=True, w=1.0, head=6.5, gap=4.0, end_dir=None,
           bow=0.55) -> str:
    """지시선 — 라벨(frm)에서 가리킬 곳(to)까지 얇은 선 + 화살촉.

    ``end_dir`` 을 주면 **곡선(2차 베지에)** 으로 그리고 그 방향으로 **도착**한다.
    직선 지시선은 라벨이 각의 반대편에 놓였을 때 화살표가 각이 열린 방향과 거꾸로
    들어가 어색하다(사용자 2026-08-13 왕선중 q11 의 70°·80°: "각의 방향과 반대라서
    어색"). 도착 접선을 각 쪽으로 맞추면 어디에 적든 화살표가 각을 향해 들어온다.

    라벨 쪽은 gap 만큼 띄워 글자에 닿지 않게 한다.
    """
    L = _nonzero_segment(frm[0], frm[1], to[0], to[1], "leader")
    _finite(w, head, gap, what="leader")
    if w <= 0 or head <= 0:
        raise ValueError("leader: 굵기와 화살촉 크기는 양수여야 함")
    ux, uy = (to[0] - frm[0]) / L, (to[1] - frm[1]) / L
    # 라벨이 대상에 바짝 붙으면 gap+화살촉이 선 길이를 넘어 선이 뒤집힌다.
    gap = max(0.0, min(gap, L - (head if arrow else 0.0) - 2.0))
    sx, sy = frm[0] + ux * gap, frm[1] + uy * gap

    if end_dir is None:
        tip_u, tip_v = ux, uy
        bx, by = (to[0] - ux * head, to[1] - uy * head) if arrow else to
        path = (f'<line x1="{sx:.1f}" y1="{sy:.1f}" x2="{bx:.1f}" y2="{by:.1f}" '
                f'stroke="#000" stroke-width="{w}"/>')
    else:
        ex, ey = end_dir
        n = math.hypot(ex, ey)
        if n <= _EPS:
            raise ValueError("leader: end_dir 은 영벡터일 수 없음")
        tip_u, tip_v = ex / n, ey / n
        # 제어점을 도착점 뒤에 두면 끝 접선이 end_dir 이 된다. 다만 너무 멀리 두면
        # 곡선이 크게 부풀어 다른 요소를 가로지른다 — 길이에 비례해 묶는다.
        reach = min(bow * L, 0.6 * L, 72.0)
        cx_, cy_ = to[0] - tip_u * reach, to[1] - tip_v * reach
        bx, by = ((to[0] - tip_u * head, to[1] - tip_v * head) if arrow else to)
        path = (f'<path d="M {sx:.1f} {sy:.1f} Q {cx_:.1f} {cy_:.1f} {bx:.1f} {by:.1f}" '
                f'fill="none" stroke="#000" stroke-width="{w}"/>')

    return path + (_arrow_head(to, tip_u, tip_v, head) if arrow else "")


def _box_hits_segment(box, a, b) -> bool:
    """축정렬 상자와 선분이 만나는가(Liang-Barsky 클리핑)."""
    x0, y0, x1, y1 = box
    dx, dy = b[0] - a[0], b[1] - a[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]),
                 (-dy, a[1] - y0), (dy, y1 - a[1])):
        if abs(p) < _EPS:
            if q < 0:
                return False
            continue
        t = q / p
        if p < 0:
            if t > t1:
                return False
            t0 = max(t0, t)
        else:
            if t < t0:
                return False
            t1 = min(t1, t)
    return t0 <= t1


def _box_hits_circle(box, cx, cy, r) -> bool:
    """상자가 원주(테두리)와 만나는가 — 원 안에 통째로 들어간 경우는 아니다."""
    x0, y0, x1, y1 = box
    near = math.hypot(max(x0 - cx, 0, cx - x1), max(y0 - cy, 0, cy - y1))
    far = max(math.hypot(cx - x0, cy - y0), math.hypot(cx - x1, cy - y0),
              math.hypot(cx - x0, cy - y1), math.hypot(cx - x1, cy - y1))
    return near <= r <= far


def angle_label_leader(vx, vy, p1, p2, content=None, runs=None, fs=12,
                       arc_r=20.0, out=64.0, side=1, margin_deg=26.0,
                       arrow=True, avoid=(), circles=(), keep_out=(),
                       curve_deg=40.0) -> str:
    """**좁은 각** 라벨 — 각 바깥에 적고 지시선으로 각 호를 가리킨다.

    좁은 각(≲25°)에서는 라벨을 각 안에 둘 자리가 없다. `halo_angle` 은 변을 안
    지우려고 이등분선을 따라 멀리 미는데(clear), 그러면 "이 라벨이 어느 각인지"
    가 흐려진다(사용자 2026-08-13, 왕선중 q5 의 20° "너무 아래쪽"). 인쇄 원본도
    이럴 때 **밖에 적고 선을 긋는다**.

    side=+1/-1 로 어느 변 쪽으로 뺄지 고른다. margin_deg 는 변을 넘어 얼마나
    더 벌릴지. 라벨은 빈 공간에 놓이므로 halo 를 쓰지 않는다(halo 가 실선을
    지우는 lint 규칙 7 을 애초에 피한다).

    ⚠️ **arc_r 은 같이 그리는 `angle_mark` 의 r 과 같아야 한다** — 다르면 화살촉이
    호에서 살짝 뜬 허공을 가리켜 어긋나 보인다(기본값은 둘 다 20).
    """
    a0 = ray_angle(vx, vy, *p1)
    da = (ray_angle(vx, vy, *p2) - a0 + 180.0) % 360.0 - 180.0
    mid = a0 + da / 2.0
    anchor = circle_pt(vx, vy, mid, arc_r)

    hw, hh = _label_halfsize(content, runs, fs)
    head = max(6.0, 0.42 * fs)          # 화살촉도 글자와 함께 커져야 균형이 맞는다

    def _box(px, py):
        return (px - hw, py - hh, px + hw, py + hh)

    def _clear(px, py) -> bool:
        """라벨 상자와 지시선이 도형 선·원을 건드리지 않는가."""
        box = _box(px, py)
        if any(_box_hits_segment(box, a, b) for a, b in avoid):
            return False
        if any(_box_hits_circle(box, *c) for c in circles):
            return False
        # 이미 놓인 라벨(점 이름 등) 과도 겹치면 안 된다 — lint 규칙 3.
        for kx, ky, kr in keep_out:
            near = math.hypot(max(box[0] - kx, 0, kx - box[2]),
                              max(box[1] - ky, 0, ky - box[3]))
            if near <= kr:
                return False
        return True

    # 손으로 고른 방향은 자주 선을 밟는다(실측: q5 20°·q11 x°/y°/70°/80° 전부 겹침).
    # 지시선이 있으니 라벨은 **어디든 빈 곳**이면 된다 — 각 바깥 전 방향을 훑되
    # 원하는 쪽(side)에 가까운 후보를 먼저 본다. 결정적 탐색이라 렌더마다 같다.
    base_side = 1 if side >= 0 else -1
    prefer = mid + base_side * (abs(da) / 2.0 + margin_deg)
    cands = []
    for step in range(24):                    # 15° 간격 전 방향
        ang = prefer + step * 15.0
        if abs((ang - mid + 180.0) % 360.0 - 180.0) < abs(da) / 2.0 + 8.0:
            continue                          # 각 안쪽은 제외(라벨이 변을 밟는다)
        for k in (1.0, 1.22, 1.5, 0.84):
            cands.append((step, circle_pt(vx, vy, ang, out * k)))
    lx, ly = None, None
    for _, (px, py) in cands:
        if _clear(px, py):
            lx, ly = px, py
            break
    if lx is None:                            # 전부 막히면 요청값 그대로(작도자 판단)
        lx, ly = circle_pt(vx, vy, prefer, out)

    body = (txt(lx, ly + 0.35 * fs, content, fs) if runs is None
            else f'<text x="{lx:.1f}" y="{ly + 0.35 * fs:.1f}" font-size="{fs}" {FONT} '
                 f'text-anchor="middle">{_text_runs_markup(runs)}</text>')
    # ⚠️ 지시선 시작점은 **라벨 상자 밖**이어야 한다. 고정 gap 을 쓰면 선이 글자를
    # 관통해 lint 규칙 2(라벨-선 겹침)에 걸린다(실측 8~9px).
    dx, dy = anchor[0] - lx, anchor[1] - ly
    L = math.hypot(dx, dy) or 1.0
    ux, uy = dx / L, dy / L
    reach = min(hw / abs(ux) if abs(ux) > 1e-6 else 1e9,
                hh / abs(uy) if abs(uy) > 1e-6 else 1e9)
    gap = min(L * 0.7, reach + 3.0)

    # 화살표는 **각이 열린 쪽에서** 들어와야 자연스럽다 — 도착 접선을 꼭짓점
    # 방향(= 이등분선 반대)으로 맞춘다. 직선으로도 그 방향이면 그냥 직선을 쓰고,
    # 라벨이 옆이나 반대편에 놓여 방향이 많이 틀어졌을 때만 곡선으로 감아 들어온다.
    ex, ey = vx - anchor[0], vy - anchor[1]
    en = math.hypot(ex, ey) or 1.0
    ex, ey = ex / en, ey / en
    deviation = math.degrees(math.acos(max(-1.0, min(1.0, ux * ex + uy * ey))))
    end_dir = (ex, ey) if deviation > curve_deg else None
    return leader((lx, ly), anchor, arrow=arrow, gap=gap, head=head,
                  end_dir=end_dir, bow=min(0.85, 0.30 + deviation / 180.0)) + body


def point_labels(items, avoid=(), curves=(), circles=(), fs=15, gap=13.0,
                 occupied=(), italic=()) -> str:
    """점 이름 라벨 **자동 배치** — 선·곡선·서로와 안 겹치는 방향을 골라 한 번에 낸다.

    손으로 dx·dy 를 적으면 그림을 조금만 고쳐도 라벨이 선을 밟는다. 이 세션에서만
    같은 수정을 열 번 넘게 반복했다(사용자 2026-08-13 "정교하게 꽉 쪼아서 어색하고
    어긋나지 않도록"). 배치는 결정적이라 렌더마다 같다.

    items:    (x, y, 이름) 목록 — 화면(SVG) 좌표
    avoid:    도형 선분 [(p, q), …]
    curves:   샘플 점열 [[(x, y), …], …] — 타원·원뿔곡선처럼 곡선인 요소
    circles:  (cx, cy, r) 목록 — 원주
    occupied: 이미 자리를 차지한 상자 [(x0, y0, x1, y1), …]
    italic:   이탤릭으로 낼 이름 집합
    """
    segs = [tuple(s) for s in avoid]
    for pts in curves:
        segs.extend(zip(pts, pts[1:]))
    taken = [tuple(b) for b in occupied]
    out = []
    for x, y, name in items:
        hw, hh = _label_halfsize(str(name), None, fs)
        best, far = None, False
        near_tiers = (gap, gap * 1.45, gap * 2.0, gap * 2.7)
        for dist in near_tiers + (gap * 3.6, gap * 4.8):
            for k in range(24):
                a = math.radians(k * 15.0)
                px, py = x + dist * math.cos(a), y - dist * math.sin(a)
                box = (px - hw, py - hh, px + hw, py + hh)
                if any(_box_hits_segment(box, s, e) for s, e in segs):
                    continue
                if any(_box_hits_circle(box, *c) for c in circles):
                    continue
                if any(not (box[2] < b[0] or b[2] < box[0]
                            or box[3] < b[1] or b[3] < box[1]) for b in taken):
                    continue
                best, far = (px, py, box), dist > near_tiers[-1] + 1e-9
                break
            if best:
                break
        if best is None:                       # 전부 막히면 오른쪽 위(관례)로 둔다
            px, py = x + gap * 0.8, y - gap * 0.8
            best = (px, py, (px - hw, py - hh, px + hw, py + hh))
        taken.append(best[2])
        # 가까이엔 자리가 없어 멀리 밀린 라벨은 **지시선으로 묶는다** — 안 그러면
        # 어느 점의 이름인지 알 수 없다(각 라벨과 같은 원칙).
        if far:
            dx, dy = x - best[0], y - best[1]
            L = math.hypot(dx, dy) or 1.0
            ux, uy = dx / L, dy / L
            reach = min(hw / abs(ux) if abs(ux) > 1e-6 else 1e9,
                        hh / abs(uy) if abs(uy) > 1e-6 else 1e9)
            out.append(leader((best[0], best[1]), (x, y), arrow=False, w=0.9,
                              gap=min(L * 0.6, reach + 3.0)))
        out.append(txt(best[0], best[1] + 0.35 * fs, str(name), fs,
                       it=name in italic))
    return "\n".join(out)


def angle_label(vx, vy, p1, p2, content=None, runs=None, fs=12, d=30.0,
                arc_r=20.0, out=58.0, wide_deg=30.0, avoid=(), circles=(),
                keep_out=(), **leader_kw) -> str:
    """각 라벨 **표준 진입점** — 안에 쓸 수 있으면 안에, 아니면 지시선으로 뺀다.

    사용자 2026-08-13: "너무 다 화살표로 땅길 필요없고, 적기 힘든곳, 아주 작은곳들만."
    넓은 각은 종전처럼 `halo_angle` 이 읽기 좋다. 좁거나(<wide_deg) 자리가 막힌
    각만 `angle_label_leader` 로 뺀다 — 판정은 눈대중이 아니라 라벨 상자와 도형
    선·원·기존 라벨의 실제 충돌로 한다.
    """
    a0 = ray_angle(vx, vy, *p1)
    da = abs((ray_angle(vx, vy, *p2) - a0 + 180.0) % 360.0 - 180.0)
    if da >= wide_deg:
        px, py = _angle_label_pos(vx, vy, p1, p2, d, fs, content, runs)
        hw, hh = _label_halfsize(content, runs, fs)
        box = (px - hw, py - hh, px + hw, py + hh)
        blocked = (any(_box_hits_segment(box, a, b) for a, b in avoid)
                   or any(_box_hits_circle(box, *c) for c in circles)
                   or any(math.hypot(max(box[0] - kx, 0, kx - box[2]),
                                     max(box[1] - ky, 0, ky - box[3])) <= kr
                          for kx, ky, kr in keep_out))
        if not blocked:
            return halo_angle(vx, vy, p1, p2, d, content, fs, runs=runs)
    return angle_label_leader(vx, vy, p1, p2, content, runs, fs, arc_r=arc_r,
                              out=out, avoid=avoid, circles=circles,
                              keep_out=keep_out, **leader_kw)


def rangle_at(vx, vy, p1, p2, s=9) -> str:
    """직각 표시 — 방향을 **실제 기하**(v→p1·v→p2)에서 계산. 단위벡터 눈대중
    하드코딩 금지(왕선중 q5 E 직각이 어긋난 실측 원인)."""
    l1 = _nonzero_segment(vx, vy, p1[0], p1[1], "rangle_at")
    l2 = _nonzero_segment(vx, vy, p2[0], p2[1], "rangle_at")
    return rangle(vx, vy, (p1[0] - vx) / l1, (p1[1] - vy) / l1,
                  (p2[0] - vx) / l2, (p2[1] - vy) / l2, s)


# ── 기하 헬퍼(시험지 스크립트마다 복붙 금지 — 여기서 import) ──────────────

def circle_pt(cx, cy, ang, r):
    """원 위 점(수학각 도, SVG y-down 보정)."""
    _finite(cx, cy, ang, r, what="circle_pt")
    if r < 0:
        raise ValueError("circle_pt: 반지름은 음수일 수 없음")
    return (cx + r * math.cos(math.radians(ang)), cy - r * math.sin(math.radians(ang)))


C = circle_pt


def seci(P, ang_deg, cx, cy, r):
    """P 에서 수학각 방향 반직선이 원과 만나는 두 점(가까운 것, 먼 것).

    ⚠️ 외부점에서는 반직선이 P→중심 방향 ±asin(r/d) 안에 있어야 한다 —
    벗어나면 math domain error 대신 한계각을 알려주는 ValueError.
    """
    _finite(P[0], P[1], ang_deg, cx, cy, r, what="seci")
    if r <= 0:
        raise ValueError("seci: 반지름은 양수여야 함")
    ux, uy = math.cos(math.radians(ang_deg)), -math.sin(math.radians(ang_deg))
    fx, fy = P[0] - cx, P[1] - cy
    b = fx * ux + fy * uy
    disc = b * b - (fx * fx + fy * fy - r * r)
    if disc < -_EPS:
        d = math.hypot(fx, fy)
        lim = math.degrees(math.asin(min(1.0, r / d)))
        toc = ray_angle(P[0], P[1], cx, cy)
        raise ValueError(
            f"seci: 반직선이 원을 비껴감 — P→중심 {toc:.1f}° 기준 ±{lim:.1f}° 안의 각만 가능"
        )
    dq = math.sqrt(max(0.0, disc))
    return ((P[0] + (-b - dq) * ux, P[1] + (-b - dq) * uy),
            (P[0] + (-b + dq) * ux, P[1] + (-b + dq) * uy))


def isect(p1, p2, p3, p4):
    """직선 p1p2 와 p3p4 의 교점."""
    x1, y1 = p1; x2, y2 = p2; x3, y3 = p3; x4, y4 = p4
    l1 = _nonzero_segment(x1, y1, x2, y2, "isect")
    l2 = _nonzero_segment(x3, y3, x4, y4, "isect")
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) <= _EPS * l1 * l2:
        raise ValueError("isect: 두 직선이 평행하거나 거의 평행함")
    px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / den
    py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / den
    return (px, py)


def tangent_isect(cx, cy, r, t1, t2):
    """두 접점 각도 t1·t2(도)에서 그은 접선의 교점(외부점)."""
    _finite(cx, cy, r, t1, t2, what="tangent_isect")
    if r <= 0:
        raise ValueError("tangent_isect: 반지름은 양수여야 함")
    half = abs((t2 - t1 + 180) % 360 - 180) / 2.0
    mid = t1 + ((t2 - t1 + 180) % 360 - 180) / 2.0
    den = math.cos(math.radians(half))
    if abs(den) <= _EPS:
        raise ValueError("tangent_isect: 두 접선이 평행해 유한 교점이 없음")
    d = r / den
    return circle_pt(cx, cy, mid, d)


def tangent_dir(cx, cy, r, ang) -> tuple[float, float]:
    """접점(각 ang)에서의 **단위 접선 방향**(각이 커지는 쪽).

    접선을 그릴 때 방향벡터를 손으로 적으면 부호를 틀린다 — 왕선중 q11 의 T 가
    `(sin, -cos)` 로 적혀 반지름과 70°(90° 여야 접선)를 이뤄 접선이 접점 D 를
    10px 비껴갔다(실측 2026-08-13, 사용자 "D는 딱봐도 접점인것같은데").
    접선은 **접점을 기준으로** 이 함수에서 뽑는다.
    """
    _finite(cx, cy, r, ang, what="tangent_dir")
    if r <= 0:
        raise ValueError("tangent_dir: 반지름은 양수여야 함")
    a = math.radians(ang)
    return (-math.sin(a), -math.cos(a))


def tangent_seg(cx, cy, r, ang, back=40.0, fwd=40.0):
    """접점 양옆으로 뻗은 접선 **선분의 두 끝점** — 접점을 반드시 지난다."""
    _finite(back, fwd, what="tangent_seg")
    px, py = circle_pt(cx, cy, ang, r)
    ux, uy = tangent_dir(cx, cy, r, ang)
    return ((px - ux * back, py - uy * back), (px + ux * fwd, py + uy * fwd))


def tangent_beyond(cx, cy, r, ang, through, extra=40.0):
    """접점에서 `through`(보통 두 접선의 교점) **반대쪽**으로 extra 만큼 나간 점.

    ``line(through, tangent_beyond(...))`` 이면 접점을 지나는 접선이 자동으로
    보장된다(접점 기준 작도).
    """
    px, py = circle_pt(cx, cy, ang, r)
    L = _nonzero_segment(through[0], through[1], px, py, "tangent_beyond")
    return (px + (px - through[0]) / L * extra, py + (py - through[1]) / L * extra)


def line(p, q, w=2, dash=None):
    _nonzero_segment(p[0], p[1], q[0], q[1], "line")
    _finite(w, what="line")
    if w <= 0:
        raise ValueError("line: 선 굵기는 양수여야 함")
    da = ""
    if dash is not None:
        try:
            values = [float(part) for part in str(dash).replace(",", " ").split()]
        except ValueError as exc:
            raise ValueError("line: dash는 음이 아닌 숫자 목록이어야 함") from exc
        if not values or any(not math.isfinite(v) or v < 0 for v in values) or not any(values):
            raise ValueError("line: dash는 양수 하나 이상을 포함해야 함")
        da = ' stroke-dasharray="' + " ".join(f"{v:g}" for v in values) + '"'
    return (f'<line x1="{p[0]:.1f}" y1="{p[1]:.1f}" x2="{q[0]:.1f}" y2="{q[1]:.1f}" '
            f'stroke="#000" stroke-width="{w}"{da}/>')


_MAX_ATTR = 2000          # figure_quality.MAX_ATTRIBUTE_CHARS(2048) 안쪽


def curve_path(points, w=2, dash=None, close=False, fill="none") -> str:
    """샘플 점열을 곡선(polyline path)으로 — 3D 에서 투영한 타원·원뿔곡선용.

    ⚠️ 촘촘히 뽑은 점열은 속성 길이 한도(2048자)를 바로 넘긴다(201점 = 2.4KB).
    한도 안에 들어올 때까지 **균등하게 솎아낸다** — 곡선이라 시각차가 없다.
    """
    pts = [(float(x), float(y)) for x, y in points]
    if len(pts) < 2:
        raise ValueError("curve_path: 점이 2개 이상이어야 함")
    for x, y in pts:
        _finite(x, y, what="curve_path")
    while True:
        d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts) + (" Z" if close else "")
        if len(d) <= _MAX_ATTR or len(pts) < 24:
            break
        pts = pts[::2] + [pts[-1]]
    da = ""
    if dash is not None:
        values = [float(v) for v in str(dash).replace(",", " ").split()]
        if not values or any(v < 0 for v in values) or not any(values):
            raise ValueError("curve_path: dash 는 양수 하나 이상을 포함해야 함")
        da = ' stroke-dasharray="' + " ".join(f"{v:g}" for v in values) + '"'
    return (f'<path d="{d}" fill="{fill}" stroke="#000" stroke-width="{w}"'
            f'{da} stroke-linejoin="round"/>')


def txt(x, y, t, fs=15, anc="middle", it=False):
    _finite(x, y, fs, what="txt")
    if fs <= 0:
        raise ValueError("txt: 글자 크기는 양수여야 함")
    if anc not in {"start", "middle", "end"}:
        raise ValueError("txt: text-anchor는 start/middle/end만 허용")
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{fs}" {IT if it else FONT} '
            f'text-anchor="{anc}">{_plain(t, "txt")}</text>')


def dot(x, y, r=2.4):
    _finite(x, y, r, what="dot")
    if r <= 0:
        raise ValueError("dot: 반지름은 양수여야 함")
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="#000"/>'


def shaded_sphere(cx, cy, r, ident="sphereShade", w=1.6, light=(0.35, 0.32),
                  inner="#ffffff", outer="#b9b9b9") -> str:
    """구 음영 — 참조 기반 SVG 중 **유일하게 허용된** 경우(사용자 승인 2026-08-13).

    `figure_quality` 는 원래 url() 참조를 통째로 막는다. 구를 입체로 보이게 하는
    방사형 그라데이션만 좁게 열었고(로컬 `url(#id)` + `<defs>` 안 그라데이션 한정),
    pattern·filter·clip-path·외부 URL 은 여전히 차단이다. 그래서 **직접 defs 를
    쓰지 말고 이 함수를 통해서만** 음영을 넣는다 — 허용 형태가 한 곳에 모인다.

    light 는 하이라이트 위치(0~1, 원 상자 기준). 흑백 인쇄를 감안해 밝은 회색까지만.
    """
    _finite(cx, cy, r, w, what="shaded_sphere")
    if r <= 0 or w <= 0:
        raise ValueError("shaded_sphere: 반지름과 선 굵기는 양수여야 함")
    if not _re.fullmatch(r"[A-Za-z][\w.:-]*", str(ident)):
        raise ValueError("shaded_sphere: ident 는 XML id 규칙을 따라야 함")
    lx, ly = float(light[0]), float(light[1])
    if not (0.0 <= lx <= 1.0 and 0.0 <= ly <= 1.0):
        raise ValueError("shaded_sphere: light 는 0~1 이어야 함")
    for c in (inner, outer):
        if not _re.fullmatch(r"#[0-9A-Fa-f]{6}", str(c)):
            raise ValueError("shaded_sphere: 색은 #rrggbb 형식")
    return (f'<defs><radialGradient id="{ident}" cx="{lx:g}" cy="{ly:g}" r="0.78">'
            f'<stop offset="0" stop-color="{inner}"/>'
            f'<stop offset="1" stop-color="{outer}"/></radialGradient></defs>'
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" '
            f'fill="url(#{ident})" stroke="#000" stroke-width="{w}"/>')


def circ(cx, cy, r, w=2):
    _finite(cx, cy, r, w, what="circ")
    if r <= 0 or w <= 0:
        raise ValueError("circ: 반지름과 선 굵기는 양수여야 함")
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#000" stroke-width="{w}"/>'


# ── 검산 게이트(라벨값 ↔ 실제 작도) ───────────────────────────────────────

_VERIFIED: dict[tuple[str, str], int] = {}


def _caller_scope(depth: int = 2) -> str:
    """호출한 시험지 스크립트의 파일 경로 — 검산 등록부의 이름공간.

    이름만으로 키를 잡으면 시험지끼리 'q1' 이 겹쳐 **남의 검산을 자기 것으로**
    센다(실측 오탐). 모듈 단위로 갈라 놓는다.
    """
    try:
        frame = _sys._getframe(depth)
    except ValueError:
        return "<unknown>"
    return str(frame.f_globals.get("__file__", frame.f_globals.get("__name__", "?")))
_NUM_LABEL_RE = _re.compile(r"\d")
_MEASURE_LABEL_RE = _re.compile(
    r"(?:\d+(?:\.\d+)?|[a-z])\s*(?:π\s*)?(?:cm|mm|m|km|kg|g|L|mL|°)")


def type_scale(vb_w, vb_h, role="label") -> float:
    """그림 크기에 맞춘 **표준 글자 크기** — 점 이름과 수치를 한 크기로 통일한다.

    ⚠️ 크기를 호출부마다 손으로 적으면 한 그림 안에서 점 이름 15 · 각도 11 ·
    치수 12.5 처럼 제각각이 된다(사용자 2026-08-13 "숫자에 비해 문자들이 크기가
    큰것 같으니까 폰트 사이즈 통일시켜야된다"). 게다가 그림마다 viewBox 가 달라
    같은 15 라도 큰 그림에선 작아 보인다 — 그래서 **짧은 변에 비례**시킨다.

    role: ``label``(점 이름·각도·치수 공용, 기본) · ``tick``(축 눈금처럼 수가
    많아 작아야 하는 것) · ``small``(보조 주석).
    """
    _finite(vb_w, vb_h, what="type_scale")
    if vb_w <= 0 or vb_h <= 0:
        raise ValueError("type_scale: viewBox 크기는 양수여야 함")
    base = max(13.0, min(22.0, 0.072 * min(float(vb_w), float(vb_h))))
    factor = {"label": 1.0, "tick": 0.78, "small": 0.68}
    if role not in factor:
        raise ValueError(f"type_scale: role 은 {sorted(factor)} 중 하나")
    return round(base * factor[role], 1)


def verify_figure(name, lengths=(), arcs=(), angles=(), tangents=(), on_line=(),
                  on_circle=(), tol=0.06, tol_deg=2.0, tol_px=1.0):
    """**라벨에 적은 값과 실제 작도가 맞는지 재측정해 대조**한다 — 안 맞으면 예외.

    lint_svg 는 "보기 좋은가"(겹침·잘림)만 본다. 라벨이 15:17 인데 그림이 1:3 이면
    lint 는 통과하고 학생은 틀린 그림으로 문제를 푼다(오성중 q2·q8·s2 실측).
    비율 붕괴는 육안으로도 안 잡히므로 **기계 검산이 유일한 방어선**이다.

    lengths: (라벨값, 점p, 점q)                 — 그림 안 상대 비율만 본다
    arcs:    (라벨값, cx, cy, r, 시작각, 끝각)   — 호 길이 = r·θ, 길이와 같은 척도
    angles:  (라벨각도, 꼭짓점, 변끝1, 변끝2)    — 절대값(도)
    tangents:  (p, q, cx, cy, r)                — 선분 pq 가 원에 **접하는가**
    on_line:   (점, a, b)                       — 점이 직선 ab **위**인가
    on_circle: (점, cx, cy, r)                  — 점이 원 위인가

    ⚠️ tangents/on_line/on_circle 은 **픽셀 절대오차**(tol_px)로 본다. 길이·각처럼
    비율이 아니라 "닿는가/지나는가"라는 이산 명제라 비율 허용오차로는 못 잡는다.
    이 셋이 없어서 왕선중 q11 의 접선이 접점 D 를 10px 비껴간 채 lint CLEAN 으로
    통과했다(2026-08-13 사용자 지적).

    길이·호는 그림마다 척도 k(px/단위)가 하나뿐이라는 성질로 검사한다. k 는 비율의
    **중앙값**으로 잡아 한 항목이 틀려도 나머지가 끌려가지 않게 한다.

    ⚠️ lengths 와 arcs 는 **같은 척도 풀**이다 — 단위를 섞지 말 것.
    호를 '도'로 주면서 길이를 'cm'로 주면 척도가 하나일 수 없어 멀쩡한
    그림이 거짓 실패한다(왕선중 q5 실측). 단위계가 다르면 이름을 나눠
    ("q5", "q5-지름") 따로 호출한다.
    """
    items = []
    for value, p, q in lengths:
        items.append((f"길이 {value}", float(value),
                      math.hypot(q[0] - p[0], q[1] - p[1])))
    for value, cx, cy, r, a0, a1 in arcs:
        span = abs((float(a1) - float(a0) + 180.0) % 360.0 - 180.0)
        items.append((f"호 {value}", float(value), float(r) * math.radians(span)))

    problems = []
    if items:
        ratios = sorted(m / v for _, v, m in items if v > _EPS)
        if not ratios:
            raise ValueError(f"{name} 검산: 라벨값은 양수여야 함")
        mid = len(ratios) // 2
        k = ratios[mid] if len(ratios) % 2 else 0.5 * (ratios[mid - 1] + ratios[mid])
        for desc, value, measured_px in items:
            want = k * value
            if want <= _EPS:
                continue
            err = abs(measured_px - want) / want
            if err > tol:
                problems.append(
                    f"  {desc}: 그려진 크기가 라벨 대비 {measured_px / want:.2f}배"
                    f" (오차 {err * 100:.0f}% > 허용 {tol * 100:.0f}%)")

    for value, vtx, p1, p2 in angles:
        a0 = ray_angle(vtx[0], vtx[1], p1[0], p1[1])
        a1 = ray_angle(vtx[0], vtx[1], p2[0], p2[1])
        drawn = abs((a1 - a0 + 180.0) % 360.0 - 180.0)
        if abs(drawn - float(value)) > tol_deg:
            problems.append(
                f"  각 {value}°: 실제로 그려진 각은 {drawn:.1f}°"
                f" (차 {abs(drawn - float(value)):.1f}° > 허용 {tol_deg}°)")

    for p, q, cx, cy, r in tangents:
        L = _nonzero_segment(p[0], p[1], q[0], q[1], "verify_figure.tangents")
        d = abs((q[0] - p[0]) * (p[1] - cy) - (p[0] - cx) * (q[1] - p[1])) / L
        if abs(d - float(r)) > tol_px:
            problems.append(
                f"  접선: 중심에서 선까지 {d:.2f}px 인데 반지름은 {float(r):.2f}px"
                f" — {'원을 자른다(할선)' if d < r else '원에 닿지 않는다'}"
                f" (차 {abs(d - float(r)):.2f}px). 접점 기준으로 그을 것"
                f"(tangent_seg/tangent_beyond).")

    for pt_, a, b in on_line:
        L = _nonzero_segment(a[0], a[1], b[0], b[1], "verify_figure.on_line")
        d = abs((b[0] - a[0]) * (a[1] - pt_[1]) - (a[0] - pt_[0]) * (b[1] - a[1])) / L
        if d > tol_px:
            problems.append(f"  점이 직선 위에 없음: {d:.2f}px 벗어남")

    for pt_, cx, cy, r in on_circle:
        d = abs(math.hypot(pt_[0] - cx, pt_[1] - cy) - float(r))
        if d > tol_px:
            problems.append(f"  점이 원 위에 없음: 반지름과 {d:.2f}px 차이")

    if problems:
        raise ValueError(
            f"[{name}] 검산 실패 — 라벨과 작도가 모순된다. 좌표를 조건에서 유도할 것:\n"
            + "\n".join(problems))
    _VERIFIED[(_caller_scope(), str(name))] = (
        len(items) + len(angles) + len(tangents) + len(on_line) + len(on_circle))


def unverified(svgs: dict) -> list[str]:
    """수치 라벨이 있는데 verify_figure 를 안 부른 그림 — 검산 누락 적발용.

    게이트를 만들어도 **부르지 않으면 없는 것과 같다**. 빌드 하네스가 이걸로
    누락을 막는다.
    """
    scope = _caller_scope()
    missing = []
    for key, svg in svgs.items():
        if (scope, str(key)) in _VERIFIED:
            continue
        texts = "".join(_TEXT_RE.findall(str(svg)))
        if _MEASURE_LABEL_RE.search(_re.sub(r"<[^>]+>", "", texts)):
            missing.append(str(key))
    return missing


# ── 완성 판정 자동 검수(픽셀 단위) ────────────────────────────────────────

_DASHED_EL_RE = _re.compile(r"<(?:path|line)\b[^>]*stroke-dasharray[^>]*/>")
_HALO_ERASE_TOL = 12          # scale=2 기준 허용 픽셀(안티앨리어싱 여유)
_POINT_LABEL_RE = _re.compile(r"^[A-Z][A-Z]?['\u2032]?$")
_LEN_RE = _re.compile(r"^\s*(?:\d+(?:\.\d+)?|[a-z])\s*(?:π\s*)?(?:cm|mm|m|km|kg|g|L|mL)\s*$")
_TEXT_RE = _re.compile(r"<text\b[^>]*>.*?</text>", _re.S)
_PAD = 24.0


def _ink(svg_str, w_px):
    """resvg 렌더 → 잉크 마스크(불투명 & 비백색). halo 흰 stroke 는 잉크가 아니다."""
    import numpy as np
    from PIL import Image

    from core.figure_generator import _svg_to_png_bytes

    png = _svg_to_png_bytes(svg_str, width=w_px)
    if png is None:
        raise RuntimeError("resvg 렌더 실패 — lint_svg 는 픽셀 검수라 resvg 필수")
    # Keep uint8.  The previous int64 conversion multiplied peak memory by 8
    # immediately before pixel lint, which made large-but-valid SVGs an easy
    # memory exhaustion vector.
    a = np.asarray(Image.open(_io.BytesIO(png)).convert("RGBA"))
    return (a[..., 3] > 60) & (a[..., :3].min(axis=-1) < 235)


def lint_svg(svg: str, tol: int = 6, scale: float = 2.0) -> list[str]:
    """그림 완성 판정 — **통과 전에는 '완성'이라 부르지 않는다**(사용자 2026-08-12
    '이걸 왜 완성되었다고 하나' / '아주 철저히 쪼으란 말야'). 글꼴 근사가 아니라
    실제 렌더 픽셀로 검사한다:

    1. **잘림** — viewBox 밖 잉크(운암중 q6 C·오성중 q9 P 이탈 계열)
    2. **라벨-선 겹침** — halo 없는 텍스트 글리프가 선 잉크와 겹침(왕선중 q1 6cm)
    3. **라벨-라벨 겹침** — 텍스트끼리 겹침(오성중 q9 56° 뭉개짐)
    4. **떠 있는 맨 길이 라벨** — 선 근처(8px)도 아닌 길이 표기는 measured() 규격
       위반(오성중 15·17cm). halo(dim_label/halo_text)는 점선 위 배치가 정상이라 제외.
    7. **halo 가 실선을 지움** — 흰 halo 는 자기 치수 점선만 지울 수 있다. 도형의
       **실선(구조선)** 을 지우면 위반이다(사용자 2026-08-13 "배경처리해버리면 도형
       읽는데 애로사항 있음"의 치수 라벨판). 점선 요소를 뺀 렌더와 최종 렌더를
       비교해 사라진 실선 잉크를 센다. 규칙 2 는 halo 가 있으면 통째로 건너뛰므로
       이 규칙이 없으면 **halo 만 씌우면 실선을 얼마든 지워도 통과**한다(실측:
       41장이 전부 lint OK 인데 11그림 15라벨이 실선을 지우고 있었다).
    5. **선을 가린 점 라벨** — A·B·O 같은 점 이름이 선 잉크와 겹침. halo 로 흰
       테두리를 씌워 선을 끊어 놓는 것도 **위반**이다(사용자 2026-08-13: "선위에
       겹쳐서 배경처리해버리면 도형 읽는데 애로사항 있음"). 점 라벨은 선 밖에 둔다.
       halo 는 치수·각 라벨용(점선 위 배치가 정상)이고 점 이름용이 아니다.

    반환 [] 이 곧 완성 판정. tol 은 안티앨리어싱 허용 픽셀(scale=2 기준).
    """
    import numpy as np
    from PIL import Image, ImageFilter

    mvb = _re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    if not mvb:
        return ["viewBox 파싱 실패 — lint 불가"]
    vw, vh = float(mvb.group(1)), float(mvb.group(2))
    if vw <= 0 or vh <= 0:
        return ["viewBox 폭과 높이는 양수여야 함"]
    if max(vw, vh) > 640:
        return ["viewBox가 픽셀 검수 안전 한도(640)를 초과함"]
    if max(vw / vh, vh / vw) > 20:
        return ["viewBox 종횡비가 픽셀 검수 안전 한도(20:1)를 초과함"]
    open_end = svg.index(">", svg.index("<svg")) + 1
    body = svg[open_end:svg.rindex("</svg>")]
    head = (f'<svg viewBox="-{_PAD} -{_PAD} {vw + 2 * _PAD} {vh + 2 * _PAD}" '
            f'xmlns="http://www.w3.org/2000/svg">')
    w_px = int(round((vw + 2 * _PAD) * scale))

    def render(content):
        return _ink(head + content + "</svg>", w_px)

    out: list[str] = []
    full = render(body)
    if not full.any():
        return ["보이는 잉크 없음 — 완전 투명·흰색 또는 퇴화 도형"]
    sy, sx = full.shape
    px = w_px / (vw + 2 * _PAD)          # svg 1단위당 픽셀
    x0, y0 = int(_PAD * px), int(_PAD * px)
    x1, y1 = int((_PAD + vw) * px), int((_PAD + vh) * px)
    outside = full.copy()
    outside[max(0, y0 - 1):y1 + 1, max(0, x0 - 1):x1 + 1] = False
    if outside.sum() > tol:
        ys, xs = np.nonzero(outside)
        out.append(f"잘림: viewBox 밖 잉크 {int(outside.sum())}px "
                   f"(svg좌표 x≈{xs.mean() / px - _PAD:.0f}, y≈{ys.mean() / px - _PAD:.0f})")

    def has_real_halo(element):
        paint = _re.search(r'paint-order="([^"]+)"', element)
        stroke = _re.search(r'stroke="([^"]+)"', element)
        width_match = _re.search(r'stroke-width="([\d.]+)"', element)
        font_match = _re.search(r'font-size="([\d.]+)"', element)
        if not paint or not stroke or not width_match or not font_match:
            return False
        order = paint.group(1).strip().lower().split()
        stroke_color = stroke.group(1).strip().lower()
        try:
            width_value = float(width_match.group(1))
            font_value = float(font_match.group(1))
        except ValueError:
            return False
        return (
            order and order[0] == "stroke"
            and stroke_color in {"white", "#fff", "#ffffff", "#ffffffff"}
            and 3.0 <= width_value <= min(12.0, 0.8 * font_value)
        )

    texts = [(m.group(0), _re.sub(r"<[^>]+>", "", m.group(0)).strip(),
              has_real_halo(m.group(0))) for m in _TEXT_RE.finditer(body)]
    if len(texts) > 40:
        return [f"텍스트가 픽셀 검수 안전 한도(40)를 초과함: {len(texts)}"]
    strokes = render(_TEXT_RE.sub("", body))

    # Store only each label's tight mask instead of a full-canvas bitmap per
    # label.  This changes pairwise overlap memory from O(labels × canvas) to
    # O(total glyph area), while preserving the same pixel comparisons.
    def cropped(mask):
        ys, xs = np.nonzero(mask)
        if not len(xs):
            return (0, 0, 0, 0, np.zeros((0, 0), dtype=bool))
        x0_, x1_ = int(xs.min()), int(xs.max()) + 1
        y0_, y1_ = int(ys.min()), int(ys.max()) + 1
        return (x0_, y0_, x1_, y1_, mask[y0_:y1_, x0_:x1_].copy())

    masks = [cropped(render(el)) for el, _, _ in texts]

    def overlap_count(first, second):
        ax0, ay0, ax1, ay1, am = first
        bx0, by0, bx1, by1, bm = second
        ox0, oy0 = max(ax0, bx0), max(ay0, by0)
        ox1, oy1 = min(ax1, bx1), min(ay1, by1)
        if ox0 >= ox1 or oy0 >= oy1:
            return 0
        av = am[oy0 - ay0:oy1 - ay0, ox0 - ax0:ox1 - ax0]
        bv = bm[oy0 - by0:oy1 - by0, ox0 - bx0:ox1 - bx0]
        return int((av & bv).sum())

    grow = ImageFilter.MaxFilter(int(2 * 8 * scale) + 1)   # 근접 판정 반경 8(svg px)
    near = np.asarray(
        Image.fromarray(strokes.astype("uint8") * 255).filter(grow)) > 0

    for (el, label, halo), mk in zip(texts, masks):
        x0_, y0_, x1_, y1_, cropped_mask = mk
        if not cropped_mask.size:
            out.append(f"라벨이 viewBox 밖이거나 보이지 않음: '{label}'")
            stroke_overlap = 0
            touches_near = False
        else:
            stroke_overlap = int(
                (cropped_mask & strokes[y0_:y1_, x0_:x1_]).sum()
            )
            touches_near = bool(
                (cropped_mask & near[y0_:y1_, x0_:x1_]).any()
            )
        if not halo and stroke_overlap > tol:
            out.append(f"라벨-선 겹침: '{label}' ({stroke_overlap}px)")
        elif _POINT_LABEL_RE.match(label) and stroke_overlap > tol:
            # halo 로 선을 지워 통과시키던 구멍 — 점 이름은 선 밖에 둔다
            out.append(f"점 라벨이 선을 가림: '{label}' ({stroke_overlap}px) "
                       f"— halo 로 덮지 말고 선 밖으로 옮길 것")
        if _LEN_RE.match(label) and not halo and cropped_mask.size and not touches_near:
            out.append(f"떠 있는 길이 라벨: '{label}' — measured()/halo_text 규격")
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            ov = overlap_count(masks[i], masks[j])
            if ov > tol:
                out.append(f"라벨-라벨 겹침: '{texts[i][1]}' × '{texts[j][1]}' ({ov}px)")

    # 규칙 7 — halo 가 '실선'을 지웠는가(점선 위 halo 는 정상)
    solid_only = _DASHED_EL_RE.sub("", _TEXT_RE.sub("", body))
    if solid_only.strip():
        solid = render(solid_only)
        erased = int((solid & ~full).sum())
        if erased > _HALO_ERASE_TOL:
            ys, xs = np.nonzero(solid & ~full)
            out.append(
                f"halo 가 실선을 지움: {erased}px "
                f"(svg좌표 x≈{xs.mean() / px - _PAD:.0f}, y≈{ys.mean() / px - _PAD:.0f}) "
                f"— 라벨을 선 밖으로 옮기거나 치수 오프셋을 키울 것")
    return out
