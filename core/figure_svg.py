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

import math

FONT = 'font-family="Times New Roman, Batang, serif"'
IT = f'{FONT} font-style="italic"'


def pt(x: float, y: float) -> str:
    return f"{x:.1f},{y:.1f}"


def arc(cx, cy, r, a0, a1, sweep=None, large_ok=False) -> str:
    """중심 (cx,cy)·반지름 r, 수학각 a0→a1(도)의 원호 path(SVG y-down 보정).

    각 표시용이면 a0·a1 은 꼭짓점에서 본 **두 변의 실제 방향각**이어야 한다.
    sweep 미지정 시 방향에서 자동 결정(감소 방향 반전).
    """
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


def meas(px_, py_, qx_, qy_, off=10.0, ins_p=3.0, ins_q=3.0) -> str:
    """길이 치수 점선 — 끝은 꼭짓점 옆(법선 3px·접선 ins)에 감겨 붙고 가운데만
    |off| 만큼 볼록. off 부호로 쪽 선택(법선 n=(-uy,ux): 수평 좌→우 +off=아래)."""
    L = math.hypot(qx_ - px_, qy_ - py_)
    ux_, uy_ = (qx_ - px_) / L, (qy_ - py_) / L
    nx_, ny_ = -uy_, ux_
    end = 3.0 * (1.0 if off >= 0 else -1.0)
    sx_, sy_ = px_ + ux_ * ins_p + nx_ * end, py_ + uy_ * ins_p + ny_ * end
    ex_, ey_ = qx_ - ux_ * ins_q + nx_ * end, qy_ - uy_ * ins_q + ny_ * end
    c_lat = 2.0 * off - end
    cx_, cy_ = (px_ + qx_) / 2 + nx_ * c_lat, (py_ + qy_) / 2 + ny_ * c_lat
    return (f'<path d="M {sx_:.1f} {sy_:.1f} Q {cx_:.1f} {cy_:.1f} {ex_:.1f} {ey_:.1f}" '
            f'fill="none" stroke="#000" stroke-width="1" stroke-dasharray="4 3"/>')


def dim_label(px_, py_, qx_, qy_, off, txt, fs=13) -> str:
    """meas() 곡선 정점 위 라벨 — 흰 halo 로 점선이 라벨 뒤에서 끊긴다."""
    L = math.hypot(qx_ - px_, qy_ - py_)
    nx_, ny_ = -(qy_ - py_) / L, (qx_ - px_) / L
    mx_, my_ = (px_ + qx_) / 2 + nx_ * off, (py_ + qy_) / 2 + ny_ * off
    return (f'<text x="{mx_:.1f}" y="{my_ + 0.35 * fs:.1f}" font-size="{fs}" {FONT} '
            f'text-anchor="middle" paint-order="stroke" stroke="#fff" '
            f'stroke-width="{fs * 0.5:.0f}" stroke-linejoin="round">{txt}</text>')


def measured(px_, py_, qx_, qy_, off, txt, fs=13, ins_p=3.0, ins_q=3.0) -> str:
    """치수 점선 + halo 라벨 한 번에 — 길이 표기의 표준형."""
    return (meas(px_, py_, qx_, qy_, off, ins_p, ins_q)
            + "\n" + dim_label(px_, py_, qx_, qy_, off, txt, fs))


def rangle(x, y, ux, uy, vx, vy, s=11) -> str:
    """직각 표시 — 점 (x,y)에서 단위방향 u·v 가 이루는 작은 사각형."""
    return (f'<path d="M {x + ux * s:.1f} {y + uy * s:.1f} '
            f'L {x + (ux + vx) * s:.1f} {y + (uy + vy) * s:.1f} '
            f'L {x + vx * s:.1f} {y + vy * s:.1f}" '
            f'fill="none" stroke="#000" stroke-width="1"/>')


def eq_tick(p, q, ln=6.0, w=1.6) -> str:
    """같음 표시 — 선분 p–q 중점에 변과 **수직**인 짧은 선분(사선 금지)."""
    mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
    dx, dy = q[0] - p[0], q[1] - p[1]
    L = math.hypot(dx, dy)
    nx, ny = -dy / L, dx / L
    return (f'<line x1="{mx - ln * nx:.1f}" y1="{my - ln * ny:.1f}" '
            f'x2="{mx + ln * nx:.1f}" y2="{my + ln * ny:.1f}" '
            f'stroke="#000" stroke-width="{w}"/>')


def sqrt_label(x, y, num="2", fs=15) -> str:
    """근호를 선으로 그린 √num 라벨(가로줄 포함) — 유니코드 √ 는 희미해 금지."""
    w = 0.62 * fs * len(num)
    bar_y = y - 0.82 * fs
    return (f'<path d="M {x:.1f} {y - 0.38 * fs:.1f} L {x + 0.16 * fs:.1f} {y - 0.46 * fs:.1f} '
            f'L {x + 0.34 * fs:.1f} {y - 0.06 * fs:.1f} L {x + 0.58 * fs:.1f} {bar_y:.1f} '
            f'L {x + 0.58 * fs + w:.1f} {bar_y:.1f}" fill="none" stroke="#000" stroke-width="1.2"/>'
            f'<text x="{x + 0.62 * fs:.1f}" y="{y:.1f}" font-size="{fs}" {FONT}>{num}</text>')


def halo_text(x, y, content, fs=12, anc="middle") -> str:
    """흰 halo 라벨 — **선 밀집 지역의 모든 라벨은 이걸로**(왕선중 q11 x°/y° 매몰).

    content 에는 <tspan> 마크업 허용.
    """
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{fs}" {FONT} text-anchor="{anc}" '
            f'paint-order="stroke" stroke="#fff" stroke-width="{max(4.0, fs * 0.45):.0f}" '
            f'stroke-linejoin="round">{content}</text>')


def halo_angle(vx, vy, p1, p2, d, content, fs=12) -> str:
    """각 라벨 표준형 — 꼭짓점 v 의 두 변(v→p1·v→p2) **이등분선 위** d 만큼 나가
    halo 로 얹는다. 좁은 각은 라벨이 두 변에 반드시 닿으므로 halo 필수
    (오성중 q4 54°·왕선중 q5 20° 실측)."""
    a0 = ray_angle(vx, vy, *p1)
    da = (ray_angle(vx, vy, *p2) - a0 + 180.0) % 360.0 - 180.0
    mid = math.radians(a0 + da / 2.0)
    return halo_text(vx + d * math.cos(mid), vy - d * math.sin(mid) + 0.3 * fs,
                     content, fs)


def rangle_at(vx, vy, p1, p2, s=9) -> str:
    """직각 표시 — 방향을 **실제 기하**(v→p1·v→p2)에서 계산. 단위벡터 눈대중
    하드코딩 금지(왕선중 q5 E 직각이 어긋난 실측 원인)."""
    l1 = math.hypot(p1[0] - vx, p1[1] - vy)
    l2 = math.hypot(p2[0] - vx, p2[1] - vy)
    return rangle(vx, vy, (p1[0] - vx) / l1, (p1[1] - vy) / l1,
                  (p2[0] - vx) / l2, (p2[1] - vy) / l2, s)


# ── 기하 헬퍼(시험지 스크립트마다 복붙 금지 — 여기서 import) ──────────────

def circle_pt(cx, cy, ang, r):
    """원 위 점(수학각 도, SVG y-down 보정)."""
    return (cx + r * math.cos(math.radians(ang)), cy - r * math.sin(math.radians(ang)))


C = circle_pt


def seci(P, ang_deg, cx, cy, r):
    """P 에서 수학각 방향 반직선이 원과 만나는 두 점(가까운 것, 먼 것).

    ⚠️ 외부점에서는 반직선이 P→중심 방향 ±asin(r/d) 안에 있어야 한다 —
    벗어나면 math domain error 대신 한계각을 알려주는 ValueError.
    """
    ux, uy = math.cos(math.radians(ang_deg)), -math.sin(math.radians(ang_deg))
    fx, fy = P[0] - cx, P[1] - cy
    b = fx * ux + fy * uy
    disc = b * b - (fx * fx + fy * fy - r * r)
    if disc < 0:
        d = math.hypot(fx, fy)
        lim = math.degrees(math.asin(min(1.0, r / d)))
        toc = ray_angle(P[0], P[1], cx, cy)
        raise ValueError(
            f"seci: 반직선이 원을 비껴감 — P→중심 {toc:.1f}° 기준 ±{lim:.1f}° 안의 각만 가능"
        )
    dq = math.sqrt(disc)
    return ((P[0] + (-b - dq) * ux, P[1] + (-b - dq) * uy),
            (P[0] + (-b + dq) * ux, P[1] + (-b + dq) * uy))


def isect(p1, p2, p3, p4):
    """직선 p1p2 와 p3p4 의 교점."""
    x1, y1 = p1; x2, y2 = p2; x3, y3 = p3; x4, y4 = p4
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / den
    py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / den
    return (px, py)


def tangent_isect(cx, cy, r, t1, t2):
    """두 접점 각도 t1·t2(도)에서 그은 접선의 교점(외부점)."""
    half = abs((t2 - t1 + 180) % 360 - 180) / 2.0
    mid = t1 + ((t2 - t1 + 180) % 360 - 180) / 2.0
    d = r / math.cos(math.radians(half))
    return circle_pt(cx, cy, mid, d)


def line(p, q, w=2, dash=None):
    da = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{p[0]:.1f}" y1="{p[1]:.1f}" x2="{q[0]:.1f}" y2="{q[1]:.1f}" '
            f'stroke="#000" stroke-width="{w}"{da}/>')


def txt(x, y, t, fs=15, anc="middle", it=False):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{fs}" {IT if it else FONT} '
            f'text-anchor="{anc}">{t}</text>')


def dot(x, y, r=2.4):
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="#000"/>'


def circ(cx, cy, r, w=2):
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#000" stroke-width="{w}"/>'


# ── 완성 판정 자동 검수(픽셀 단위) ────────────────────────────────────────

import io as _io
import re as _re

_LEN_RE = _re.compile(r"^\s*(?:\d+(?:\.\d+)?|[a-z])\s*(?:π\s*)?(?:cm|mm|m|km|kg|g|L|mL)\s*$")
_TEXT_RE = _re.compile(r"<text [^>]*>.*?</text>", _re.S)
_PAD = 24.0


def _ink(svg_str, w_px):
    """resvg 렌더 → 잉크 마스크(불투명 & 비백색). halo 흰 stroke 는 잉크가 아니다."""
    import numpy as np
    from PIL import Image

    from core.figure_generator import _svg_to_png_bytes

    png = _svg_to_png_bytes(svg_str, width=w_px)
    if png is None:
        raise RuntimeError("resvg 렌더 실패 — lint_svg 는 픽셀 검수라 resvg 필수")
    a = np.asarray(Image.open(_io.BytesIO(png)).convert("RGBA")).astype(int)
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

    반환 [] 이 곧 완성 판정. tol 은 안티앨리어싱 허용 픽셀(scale=2 기준).
    """
    import numpy as np
    from PIL import Image, ImageFilter

    mvb = _re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    if not mvb:
        return ["viewBox 파싱 실패 — lint 불가"]
    vw, vh = float(mvb.group(1)), float(mvb.group(2))
    open_end = svg.index(">", svg.index("<svg")) + 1
    body = svg[open_end:svg.rindex("</svg>")]
    head = (f'<svg viewBox="-{_PAD} -{_PAD} {vw + 2 * _PAD} {vh + 2 * _PAD}" '
            f'xmlns="http://www.w3.org/2000/svg">')
    w_px = int(round((vw + 2 * _PAD) * scale))

    def render(content):
        return _ink(head + content + "</svg>", w_px)

    out: list[str] = []
    full = render(body)
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

    texts = [(m.group(0), _re.sub(r"<[^>]+>", "", m.group(0)).strip(),
              "paint-order" in m.group(0)) for m in _TEXT_RE.finditer(body)]
    strokes = render(_TEXT_RE.sub("", body))
    masks = [render(el) for el, _, _ in texts]

    grow = ImageFilter.MaxFilter(int(2 * 8 * scale) + 1)   # 근접 판정 반경 8(svg px)
    near = np.asarray(
        Image.fromarray(strokes.astype("uint8") * 255).filter(grow)) > 0

    for (el, label, halo), mk in zip(texts, masks):
        if not halo and int((mk & strokes).sum()) > tol:
            out.append(f"라벨-선 겹침: '{label}' ({int((mk & strokes).sum())}px)")
        if _LEN_RE.match(label) and not halo and mk.any() and not (mk & near).any():
            out.append(f"떠 있는 길이 라벨: '{label}' — measured()/halo_text 규격")
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            ov = int((masks[i] & masks[j]).sum())
            if ov > tol:
                out.append(f"라벨-라벨 겹침: '{texts[i][1]}' × '{texts[j][1]}' ({ov}px)")
    return out
