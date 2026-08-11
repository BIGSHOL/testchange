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

⚠️ SVG 문자열 치환으로 그림을 고칠 때는 **반드시 assert** — 조용한 불발이 라벨
실종을 만든다(s1 실측).
"""
from __future__ import annotations

import math

FONT = 'font-family="Times New Roman, Batang, serif"'
IT = f'{FONT} font-style="italic"'


def pt(x: float, y: float) -> str:
    return f"{x:.1f},{y:.1f}"


def arc(cx, cy, r, a0, a1, sweep=None) -> str:
    """중심 (cx,cy)·반지름 r, 수학각 a0→a1(도)의 원호 path(SVG y-down 보정).

    각 표시용이면 a0·a1 은 꼭짓점에서 본 **두 변의 실제 방향각**이어야 한다.
    sweep 미지정 시 방향에서 자동 결정(감소 방향 반전).
    """
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
    """꼭짓점 v 의 각 표시 호 — 변 v→p1 에서 v→p2 까지 정확히."""
    return arc(vx, vy, r, ray_angle(vx, vy, *p1), ray_angle(vx, vy, *p2))


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
