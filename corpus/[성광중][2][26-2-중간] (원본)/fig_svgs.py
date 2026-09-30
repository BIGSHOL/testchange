# -*- coding: utf-8 -*-
"""성광중2 26-2-중간 — 그림 21개 작도(정의값 기하).

기하 도형은 FigureSpec v2(core.figure_scene.render_figure_spec)로 엔진이 라벨을
배치하게 하고, 스펙이 표현 못 하는 인쇄 요소(각 안의 점 표시·짙은 음영 쐐기·
찢어진 종이 가장자리 등)만 core.figure_svg 프리미티브로 덧그린다(extras).
입체(q17)·등대(q18)는 프리미티브로 작도한다.

좌표는 전부 문제 조건에서 유도한다(눈대중 금지) — verify_figure 로 재측정.
"""
import math
import os
import re
import sys
import tempfile

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from core.figure_scene import render_figure_spec  # noqa: E402
from core.figure_quality import sanitize_svg  # noqa: E402
from core.figure_svg import (FONT, arc, bisect_pt, curve_path, dot, eq_tick,  # noqa: E402
                             isect, line, lint_svg, ray_angle, txt, unverified,
                             verify_figure)

OUT = os.environ.get(
    "FIG_SVG_OUT",
    str(Path(tempfile.gettempdir()) / "exam_figure_svg" / "seonggwang2"),
)
os.makedirs(OUT, exist_ok=True)
S = {}


# ── 공용 헬퍼 ────────────────────────────────────────────────────────────
def add(p, q):
    return (p[0] + q[0], p[1] + q[1])


def sub(p, q):
    return (p[0] - q[0], p[1] - q[1])


def mul(p, k):
    return (p[0] * k, p[1] * k)


def mid(p, q):
    return ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)


def dist(p, q):
    return math.hypot(q[0] - p[0], q[1] - p[1])


def unit(p, q):
    d = dist(p, q)
    return ((q[0] - p[0]) / d, (q[1] - p[1]) / d)


def foot(p, a, b):
    """점 p 에서 직선 ab 에 내린 수선의 발."""
    ux, uy = unit(a, b)
    t = (p[0] - a[0]) * ux + (p[1] - a[1]) * uy
    return (a[0] + ux * t, a[1] + uy * t)


def dirv(deg):
    """수학각(도) → 화면 단위벡터(y 아래)."""
    return (math.cos(math.radians(deg)), -math.sin(math.radians(deg)))


def ang(v, p1, p2):
    a0 = ray_angle(v[0], v[1], *p1)
    a1 = ray_angle(v[0], v[1], *p2)
    return abs((a1 - a0 + 180.0) % 360.0 - 180.0)


def incenter(A, B, C):
    a, b, c = dist(B, C), dist(C, A), dist(A, B)
    s = a + b + c
    return ((a * A[0] + b * B[0] + c * C[0]) / s, (a * A[1] + b * B[1] + c * C[1]) / s)


def circumcenter(A, B, C):
    ax, ay = A
    bx, by = B
    cx, cy = C
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay)
          + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx)
          + (cx * cx + cy * cy) * (bx - ax)) / d
    return (ux, uy)


def P(**pts):
    return {k: [float(v[0]), float(v[1])] for k, v in pts.items()}


def wedge(v, p1, p2, r, fill="#8a8a8a"):
    """짙은 음영 각(원본 인쇄의 채운 쐐기) — 스펙 region 은 옅은 색만 허용."""
    a0 = ray_angle(v[0], v[1], *p1)
    a1 = ray_angle(v[0], v[1], *p2)
    d = arc(v[0], v[1], r, a0, a1)
    return f'<path d="M {v[0]:.1f} {v[1]:.1f} L {d[2:]} Z" fill="{fill}" stroke="none"/>'


def half_dot(v, p1, p2, d=24, r=2.1):
    """각을 이등분한 반쪽 각 안의 점(•) 표시."""
    return dot(*bisect_pt(v[0], v[1], p1, p2, d), r)


def alabel(v, p1, p2, content, d=26, fs=15):
    """각 라벨을 손으로 — 엔진 자동배치가 각 밖으로 밀어낸 경우만(halo_angle 은
    두 변을 침범하지 않을 만큼 이등분선을 따라 스스로 민다)."""
    from core.figure_svg import halo_angle
    return halo_angle(v[0], v[1], p1, p2, d, content, fs)


_IT = '<tspan font-style="italic">{}</tspan>'


_LBL_RE = re.compile(r'data-px="([-\d.]+)" data-py="([-\d.]+)" data-mj="([^"]+)"')


def spec_svg(spec, extras=None, pad=(0, 0, 0, 0)):
    """스펙 렌더 + (선택) 덧그림. 엔진이 캔버스를 평행이동하므로 라벨의 data-px 로
    이동량을 되찾아 덧그림 좌표에 같은 이동을 준다. pad=(좌,위,우,아래)는 덧그림이
    엔진 캔버스 밖으로 나갈 때 여백을 넓힌다(엔진 내용은 translate 로 옮김)."""
    svg = render_figure_spec(spec)
    l, t, r, b = pad
    if extras:
        pts = spec["points"]
        shift = None
        for m in _LBL_RE.finditer(svg):
            name = m.group(3)
            if name in pts and isinstance(pts[name], list):
                shift = (float(m.group(1)) - pts[name][0] + l,
                         float(m.group(2)) - pts[name][1] + t)
                break
        if shift is None:
            raise RuntimeError("덧그림 기준점(라벨) 없음")
    if any(pad):
        mv = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
        W, H = float(mv.group(1)) + l + r, float(mv.group(2)) + t + b
        head_end = svg.index(">", svg.index("<svg")) + 1
        inner = svg[head_end:svg.rindex("</svg>")]
        svg = (f'<svg viewBox="0 0 {W:.3f} {H:.3f}" xmlns="http://www.w3.org/2000/svg">'
               f'<rect width="{W:.3f}" height="{H:.3f}" fill="#ffffff"/>'
               f'<g transform="translate({l} {t})">{inner}</g></svg>')
    if extras:
        body = extras(lambda p: (p[0] + shift[0], p[1] + shift[1]))
        svg = svg.replace("</svg>", body + "\n</svg>")
    return sanitize_svg(svg)


# ══ q2: 이등변삼각형 ABC, AD 는 ∠A 의 이등분선 ═════════════════════════
A2, B2, C2 = (110, 10), (25, 165), (195, 165)
D2 = (110, 165)
verify_figure("q2-BD", lengths=[(1, B2, D2), (1, D2, C2)])
verify_figure("q2", lengths=[(1, A2, B2), (1, A2, C2)],
              angles=[(ang(A2, B2, D2), A2, D2, C2), (90, D2, A2, C2)])
S["q2"] = spec_svg({
    "version": 2,
    "points": P(A=A2, B=B2, C=C2, D=D2),
    "segments": {"AB": {"points": ["A", "B"], "ticks": 2},
                 "AC": {"points": ["A", "C"], "ticks": 2},
                 "BC": ["B", "C"], "AD": ["A", "D"]},
    "labels": {"A": "A", "B": "B", "C": "C", "D": "D"},
}, extras=lambda T: half_dot(T(A2), T(B2), T(D2), 28) + half_dot(T(A2), T(D2), T(C2), 28))

# ══ q3: ∠C=90°, BD 는 ∠B 의 이등분선, AB=16·CD=5 ══════════════════════
# 조건 AB=16·CD=5 는 동시에 만족하는 직각삼각형이 없다(CD 최댓값 ≈4.80 at ∠B≈51.8°).
# CD/AB 가 최대(가장 근접, 오차 4%)인 ∠B 로 작도한다.
_th = max((t / 1000 for t in range(1, 785)),
          key=lambda t: math.cos(2 * t) * math.tan(t))
k3 = 11.0
B3 = (18, 190)
C3 = (B3[0] + 16 * k3 * math.cos(2 * _th), 190)
A3 = (C3[0], 190 - 16 * k3 * math.sin(2 * _th))
D3 = (C3[0], 190 - (C3[0] - B3[0]) * math.tan(_th))
verify_figure("q3", lengths=[(16, B3, A3), (5, D3, C3)],
              angles=[(90, C3, A3, B3), (math.degrees(_th), B3, A3, D3),
                      (math.degrees(_th), B3, D3, C3)])
S["q3"] = spec_svg({
    "version": 2,
    "points": P(A=A3, B=B3, C=C3, D=D3),
    "segments": {"AB": ["A", "B"], "BC": ["B", "C"], "AD": ["A", "D"],
                 "DC": ["D", "C"], "BD": ["B", "D"]},
    "angles": {"rC": {"vertex": "C", "points": ["D", "B"], "right": True}},
    "dimensions": {"dimAB": {"points": ["B", "A"], "label": "16 cm"},
                   "dimDC": {"points": ["D", "C"], "label": "5 cm"}},
    "labels": {"A": "A", "B": "B", "C": "C", "D": "D"},
}, extras=lambda T: half_dot(T(B3), T(A3), T(D3), 30) + half_dot(T(B3), T(D3), T(C3), 30))

# ══ q4: 종이 테이프 접기, ∠DAB=77° → ∠ACB=26° ══════════════════════════
w4 = 70.0
yT, yB = 40.0, 40.0 + w4
A4 = (190.0, yT)
B4 = (A4[0] + w4 / math.tan(math.radians(77)), yB)
u4 = dirv(-154)                    # AD(0°)를 AB(−77°)에 대해 접어 올린 방향
C4 = (A4[0] + u4[0] * w4 / u4[1], yB)
XL, XR = C4[0] - 30, 380.0          # 왼쪽 찢어진 끝, 오른쪽(점선) 끝
D4 = (XR - 22, yT)
LB = 150.0
LA = LB - ((A4[0] - B4[0]) * u4[0] + (A4[1] - B4[1]) * u4[1])   # 찢어진 끝을 띠에 수직으로
A4e, B4e = add(A4, mul(u4, LA)), add(B4, mul(u4, LB))
verify_figure("q4", angles=[(77, A4, (XR, yT), B4), (26, C4, A4, B4)],
              on_line=[(C4, A4, A4e)])


def _torn(p, q, n=7, amp=3.0):
    """찢어진 종이 가장자리(지그재그 곡선)."""
    ux, uy = unit(p, q)
    nx, ny = -uy, ux
    L = dist(p, q)
    pts = []
    for i in range(n * 4 + 1):
        t = i / (n * 4)
        off = amp * math.sin(t * n * 2 * math.pi) * (1 if i % 8 < 4 else 0.6)
        pts.append((p[0] + ux * L * t + nx * off, p[1] + uy * L * t + ny * off))
    return pts


S["q4"] = f'''<svg viewBox="0 0 400 225" xmlns="http://www.w3.org/2000/svg">
<rect width="400" height="225" fill="#ffffff"/>
<polygon points="{XL:.1f},{yT} {A4[0]:.1f},{yT} {B4[0]:.1f},{yB} {XL:.1f},{yB}" fill="#ededed" stroke="none"/>
<polygon points="{A4[0]:.1f},{A4[1]:.1f} {B4[0]:.1f},{B4[1]:.1f} {C4[0]:.1f},{C4[1]:.1f}" fill="#c4c4c4" stroke="none"/>
<polygon points="{C4[0]:.1f},{C4[1]:.1f} {B4[0]:.1f},{B4[1]:.1f} {B4e[0]:.1f},{B4e[1]:.1f} {A4e[0]:.1f},{A4e[1]:.1f}" fill="#efefef" stroke="none"/>
{line((XL, yT), A4, 1.9)}
{line(A4, (XR, yT), 1.4, dash="5 3")}
{line((XL, yB), C4, 1.9)}
{line(C4, (XR, yB), 1.4, dash="5 3")}
{curve_path(_torn((XL, yT), (XL, yB), 3), 1.9)}
{curve_path(_torn((XR, yT), (XR, yB), 3, 2.5), 1.4, dash="3 2.5")}
{line(A4, B4, 1.9)}
{line(A4, A4e, 1.9)}
{line(B4, B4e, 1.9)}
{curve_path(_torn(A4e, B4e, 4), 1.9)}
<path d="{arc(A4[0], A4[1], 17, 0, -77)}" fill="none" stroke="#111" stroke-width="0.9"/>
<text x="{A4[0] + 25:.1f}" y="{A4[1] + 27:.1f}" font-size="15" {FONT}>77°</text>
{txt(A4[0], A4[1] - 9, "A", 16)}{txt(D4[0], D4[1] - 9, "D", 16)}
{txt(C4[0] - 17, C4[1] - 7, "C", 16)}{txt(B4[0] + 8, B4[1] + 22, "B", 16)}
</svg>'''

# ══ q5: 이등변삼각형 ABC(∠B=∠C=71°)에 정삼각형 DEF 내접 ══════════════
# ∠AFE=63°, ∠CED=41° → ∠A=38°, ∠B=∠C=71°, ∠BFD=57°, ∠BDF=52°
B5, C5 = (20.0, 290.0), (220.0, 290.0)
A5 = (120.0, 290.0 - 100.0 * math.tan(math.radians(71)))
uBA, uBC = unit(B5, A5), unit(B5, C5)


def _e_of(t):
    F = add(B5, mul(uBA, t))
    BD = t * math.sin(math.radians(57)) / math.sin(math.radians(52))
    D = add(B5, mul(uBC, BD))
    # E = D 를 F 중심으로 60° 회전(삼각형 안쪽)
    vx, vy = D[0] - F[0], D[1] - F[1]
    c, s = math.cos(math.radians(-60)), math.sin(math.radians(-60))
    E = (F[0] + vx * c - vy * s, F[1] + vx * s + vy * c)
    return F, D, E


def _side(E):   # E 가 AC 의 어느 쪽인가
    return (C5[0] - A5[0]) * (E[1] - A5[1]) - (C5[1] - A5[1]) * (E[0] - A5[0])


lo, hi = 1.0, dist(B5, A5) - 1
for _ in range(80):
    m_ = (lo + hi) / 2
    if _side(_e_of(lo)[2]) * _side(_e_of(m_)[2]) <= 0:
        hi = m_
    else:
        lo = m_
F5, D5, E5 = _e_of((lo + hi) / 2)
verify_figure("q5", angles=[(63, F5, A5, E5), (41, E5, C5, D5), (52, D5, B5, F5),
                            (71, B5, A5, C5), (60, F5, D5, E5)],
              on_line=[(E5, A5, C5), (F5, A5, B5), (D5, B5, C5)])
S["q5"] = spec_svg({
    "version": 2,
    "points": P(A=A5, B=B5, C=C5, D=D5, E=E5, F=F5),
    "segments": {"AB": ["A", "B"], "AC": ["A", "C"], "BC": ["B", "C"],
                 "DE": ["D", "E"], "EF": ["E", "F"], "FD": ["F", "D"]},
    "angles": {"angF": {"vertex": "F", "points": ["A", "E"]},
               "angE": {"vertex": "E", "points": ["C", "D"]}},
    "labels": {"A": "A", "B": "B", "C": "C", "D": "D", "E": "E", "F": "F"},
}, extras=lambda T: alabel(T(F5), T(A5), T(E5), "63°", 30)
   + alabel(T(E5), T(C5), T(D5), "41°", 32))

# ══ q6: ∠B=90°, O 는 빗변 AC 의 중점, ∠AOB=52° → ∠C=26° ═════════════
B6 = (20.0, 140.0)
C6 = (250.0, 140.0)
A6 = (20.0, 140.0 - 230.0 * math.tan(math.radians(26)))
O6 = mid(A6, C6)
verify_figure("q6", angles=[(52, O6, A6, B6), (26, C6, A6, B6), (90, B6, A6, C6)],
              lengths=[(1, A6, O6), (1, O6, C6), (1, O6, B6)])
S["q6"] = spec_svg({
    "version": 2,
    "points": P(A=A6, B=B6, C=C6, O=O6),
    "segments": {"AB": ["A", "B"], "BC": ["B", "C"],
                 "AO": {"points": ["A", "O"], "ticks": 2},
                 "OC": {"points": ["O", "C"], "ticks": 2}, "BO": ["B", "O"]},
    "angles": {"rB": {"vertex": "B", "points": ["A", "C"], "right": True},
               "angO": {"vertex": "O", "points": ["A", "B"], "label": "52°", "label_distance": 34}},
    "labels": {"A": "A", "B": "B", "C": "C", "O": "O"},
}, extras=lambda T: wedge(T(C6), T(B6), T(A6), 20) + dot(*T(O6), 2.6))

# ══ q7: 내접원, AB=7·BC=10·CA=9 ════════════════════════════════════════
k7 = 22.0
B7 = (20.0, 190.0)
C7 = (B7[0] + 10 * k7, 190.0)
_ax = (49 - 81 + 100) / 20
A7 = (B7[0] + _ax * k7, 190.0 - math.sqrt(49 - _ax * _ax) * k7)
I7 = incenter(A7, B7, C7)
r7 = abs(190.0 - I7[1])
D7 = add(A7, mul(unit(A7, B7), 3 * k7))     # AD = s − BC = 3
E7 = add(B7, mul(unit(B7, C7), 4 * k7))     # BE = s − CA = 4
F7 = add(A7, mul(unit(A7, C7), 3 * k7))     # AF = 3
verify_figure("q7", lengths=[(7, A7, B7), (10, B7, C7), (9, C7, A7), (3, A7, D7),
                             (6, C7, E7)],
              tangents=[(A7, B7, *I7, r7), (A7, C7, *I7, r7), (B7, C7, *I7, r7)])
S["q7"] = spec_svg({
    "version": 2,
    "points": P(A=A7, B=B7, C=C7, I=I7, D=D7, E=E7, F=F7),
    "circles": {"inc": {"center": "I", "radius": round(r7, 3)}},
    "segments": {"AB": ["A", "B"], "BC": ["B", "C"], "CA": ["C", "A"]},
    "dimensions": {"dimAB": {"points": ["B", "A"], "label": "7 cm"},
                   "dimCA": {"points": ["A", "C"], "label": "9 cm"},
                   "dimBC": {"points": ["B", "C"], "label": "10 cm"}},
    "labels": {"A": "A", "B": "B", "C": "C", "D": "D", "E": "E", "F": "F"},
})

# ══ q8: 내심 I·외심 O, ∠BIC=110° → ∠A=40°, ∠C=62°, ∠B=78° ══════════
B8, C8 = (20.0, 290.0), (230.0, 290.0)
_h8 = 210.0 / (1 / math.tan(math.radians(78)) + 1 / math.tan(math.radians(62)))
A8 = (20.0 + _h8 / math.tan(math.radians(78)), 290.0 - _h8)
I8 = incenter(A8, B8, C8)
O8 = circumcenter(A8, B8, C8)
verify_figure("q8", angles=[(110, I8, B8, C8), (62, C8, B8, A8), (40, A8, B8, C8),
                            (8, A8, I8, O8)],
              lengths=[(1, O8, A8), (1, O8, B8), (1, O8, C8)])
S["q8"] = spec_svg({
    "version": 2,
    "points": P(A=A8, B=B8, C=C8, I=I8, O=O8),
    "segments": {"AB": ["A", "B"], "AC": ["A", "C"], "BC": ["B", "C"],
                 "AI": ["A", "I"], "AO": ["A", "O"], "BI": ["B", "I"], "BO": ["B", "O"],
                 "CI": ["C", "I"], "CO": ["C", "O"]},
    "angles": {"angI": {"vertex": "I", "points": ["B", "C"]},
               "angC": {"vertex": "C", "points": ["B", "A"], "label": "62°"}},
    "labels": {"A": "A", "B": "B", "C": "C", "I": "I", "O": "O"},
}, extras=lambda T: alabel(T(I8), T(B8), T(C8), "110°", 27))

# ══ q9: 평행사변형 ABCD, BC=8·BD=14·∠BCD=120° ═════════════════════════
k9 = 17.0
_cd = (-8 + math.sqrt(64 + 4 * 132)) / 2        # CD² + 8CD − 132 = 0
B9 = (90.0, 195.0)
C9 = (B9[0] + 8 * k9, 195.0)
D9 = add(C9, mul(dirv(60), _cd * k9))
A9 = add(B9, sub(D9, C9))
O9 = mid(B9, D9)
verify_figure("q9", lengths=[(8, B9, C9), (14, B9, D9), (8, A9, D9), (7, B9, O9)],
              angles=[(120, C9, B9, D9), (60, D9, A9, C9)])
def _q9_extras(T):
    from core.figure_svg import dim_label, leader, meas
    b, o, d = T(B9), T(O9), T(D9)
    # BO: BD 위쪽 치수 점선 + 바깥 라벨에서 화살표(원본 인쇄 그대로)
    bo = meas(*b, *o, -9)
    L = dist(b, o)
    nx, ny = (o[1] - b[1]) / L, -(o[0] - b[0]) / L     # 위쪽 법선
    tip = (mid(b, o)[0] + nx * 9, mid(b, o)[1] + ny * 9)
    lab = (b[0] - 22, tip[1] - 52)
    txt_bo = (f'<text x="{lab[0]:.1f}" y="{lab[1]:.1f}" font-size="15" {FONT} '
              f'text-anchor="middle">(2<tspan font-style="italic">y</tspan>−5) cm</text>')
    # BD: 아래쪽 치수 점선, 라벨은 O–D 사이(원본 위치)
    bd = meas(*b, *d, 11) + dim_label(*b, *d, 11, "14 cm", 15, t=0.6)
    return "\n".join([wedge(T(D9), T(A9), T(C9), 16), bo,
                      alabel(T(C9), T(B9), T(A9), "120°", 30),
                      alabel(T(D9), T(A9), T(B9), _IT.format("z") + "°", 30),
                      leader((lab[0] + 8, lab[1] + 6), tip, head=5.5, gap=6,
                             end_dir=(0.55, 0.83)), txt_bo, bd])


S["q9"] = spec_svg({
    "version": 2,
    "canvas": [335, 240],
    "points": P(A=A9, B=B9, C=C9, D=D9, O=O9),
    "segments": {"AB": ["A", "B"], "BC": ["B", "C"], "CD": ["C", "D"], "DA": ["D", "A"],
                 "AC": ["A", "C"], "BD": ["B", "D"]},
    "angles": {"angC": {"vertex": "C", "points": ["B", "D"]}},
    "dimensions": {"dimAD": {"points": ["A", "D"], "label": "(x+2) cm"},
                   "dimBC": {"points": ["B", "C"], "label": "8 cm"}},
    "labels": {"A": "A", "B": "B", "C": {"text": "C", "dx": 13, "dy": 12},
               "D": {"text": "D", "dx": 15, "dy": -9}, "O": {"text": "O", "dx": 6, "dy": -24}},
}, extras=lambda T: _q9_extras(T))

# ══ q10: □ABCD 와 두 대각선의 교점 O ═══════════════════════════════════
A10, D10, B10, C10 = (55.0, 20.0), (255.0, 20.0), (20.0, 130.0), (220.0, 130.0)
O10 = isect(A10, C10, B10, D10)
verify_figure("q10", on_line=[(O10, A10, C10), (O10, B10, D10)],
              lengths=[(1, A10, D10), (1, B10, C10)])
S["q10"] = spec_svg({
    "version": 2,
    "points": P(A=A10, B=B10, C=C10, D=D10, O=O10),
    "segments": {"AB": ["A", "B"], "BC": ["B", "C"], "CD": ["C", "D"], "DA": ["D", "A"],
                 "AC": ["A", "C"], "BD": ["B", "D"]},
    "labels": {"A": "A", "B": "B", "C": "C", "D": "D", "O": "O"},
})

# ══ q11: 평행사변형 ABCD, AP=CQ, ∠PQD=75°, ∠DPQ:∠BPQ=2:3 ══════════════
# PBQD 는 평행사변형 → ∠BPQ=∠PQD=75°, ∠DPQ=50°, ∠PDQ=55°, ∠PBQ=55°
p11 = 1.0
_pd = 2 * p11 * math.sin(math.radians(75)) / math.sin(math.radians(55))
_P, _Q = (-p11, 0.0), (p11, 0.0)
_D = add(_P, mul(dirv(50), _pd))          # 위쪽(화면 y 음수)
_B = (-_D[0], -_D[1])
a11 = p11 / 0.76
_A, _C = (-a11, 0.0), (a11, 0.0)
_rot = -math.atan2(_D[1] - _A[1], _D[0] - _A[0])   # AD 를 수평으로


def _tf(p, s=95.0, o=(135.0, 105.0)):
    c, sn = math.cos(_rot), math.sin(_rot)
    return (o[0] + s * (p[0] * c - p[1] * sn), o[1] + s * (p[0] * sn + p[1] * c))


A11, B11, C11, D11, P11, Q11 = map(_tf, (_A, _B, _C, _D, _P, _Q))
verify_figure("q11", angles=[(75, Q11, P11, D11), (50, P11, D11, Q11),
                             (75, P11, B11, Q11), (55, B11, P11, Q11)],
              lengths=[(1, A11, P11), (1, C11, Q11)],
              on_line=[(P11, A11, C11), (Q11, A11, C11)])
S["q11"] = spec_svg({
    "version": 2,
    "points": P(A=A11, B=B11, C=C11, D=D11, P=P11, Q=Q11),
    "segments": {"AB": ["A", "B"], "BC": ["B", "C"], "CD": ["C", "D"], "DA": ["D", "A"],
                 "AP": {"points": ["A", "P"], "ticks": 2}, "PQ": ["P", "Q"],
                 "QC": {"points": ["Q", "C"], "ticks": 2},
                 "BP": ["B", "P"], "PD": ["P", "D"], "BQ": ["B", "Q"], "QD": ["Q", "D"]},
    "angles": {"angQ": {"vertex": "Q", "points": ["P", "D"], "label": "75°", "label_distance": 30}},
    "labels": {"A": "A", "B": "B", "C": "C", "D": "D", "P": "P", "Q": "Q"},
}, extras=lambda T: wedge(T(B11), T(P11), T(Q11), 17))

# ══ q12: AB=13·AD=16 평행사변형을 B 가 CD 의 중점 M 에 오도록 접기 ═════
k12 = 11.0
_ux = (169 - 256 - 42.25) / 16                  # |AM|=13 에서 유도: u_x=−8.078
_uy = math.sqrt(169 - _ux * _ux)
A12 = (125.0, 30.0)
B12 = (A12[0] + _ux * k12, A12[1] + _uy * k12)
D12 = (A12[0] + 16 * k12, A12[1])
C12 = (B12[0] + 16 * k12, B12[1])
M12 = mid(C12, D12)
# E: BC 위, EB = EM
_s = ((M12[0] - B12[0]) ** 2 + (M12[1] - B12[1]) ** 2) / (2 * (M12[0] - B12[0]))
E12 = (B12[0] + _s, B12[1])
F12 = isect(A12, E12, D12, C12)
verify_figure("q12", lengths=[(13, A12, B12), (16, A12, D12), (13, A12, M12),
                              (6.5, M12, C12), (6.5, C12, F12)],
              on_line=[(F12, D12, C12)])
S["q12"] = spec_svg({
    "version": 2,
    "points": P(A=A12, B=B12, C=C12, D=D12, M=M12, E=E12, F=F12),
    "segments": {"AD": ["A", "D"], "DM": ["D", "M"], "MC": ["M", "C"], "CF": ["C", "F"],
                 "AE": ["A", "E"], "EF": ["E", "F"], "AM": ["A", "M"], "EM": ["E", "M"],
                 "EC": ["E", "C"],
                 "AB": {"points": ["A", "B"], "dash": "5 3"},
                 "BE": {"points": ["B", "E"], "dash": "5 3"}},
    "regions": {"paper": {"boundary": [{"seg": ["A", "E"]}, {"seg": ["E", "C"]},
                                       {"seg": ["C", "D"]}, {"seg": ["D", "A"]}],
                          "fill": "#e8e8e8"},
                "flap": {"boundary": [{"seg": ["A", "E"]}, {"seg": ["E", "M"]},
                                      {"seg": ["M", "A"]}],
                         "fill": "#c9c9c9"}},
    "dimensions": {"dimAD": {"points": ["A", "D"], "label": "16 cm"},
                   "dimAB": {"points": ["B", "A"], "label": "13 cm"}},
    "labels": {"A": "A", "B": "B", "C": "C", "D": "D", "M": "M", "E": "E", "F": "F"},
})

# ══ q13: 정삼각형 DBA·EBC·FAC, ∠BAC=100° → ∠EDA=40° ═══════════════════
B13, C13 = (60.0, 230.0), (300.0, 230.0)


def _apex_angle(xa, h):
    A = (xa, 230.0 - h)
    return ang(A, B13, C13)


_xa = B13[0] + 0.33 * (C13[0] - B13[0])
lo, hi = 5.0, 300.0
for _ in range(80):
    m_ = (lo + hi) / 2
    if _apex_angle(_xa, m_) > 100:
        lo = m_
    else:
        hi = m_
A13 = (_xa, 230.0 - (lo + hi) / 2)


def _rot60(center, p, sign):
    vx, vy = p[0] - center[0], p[1] - center[1]
    c, s = math.cos(math.radians(60 * sign)), math.sin(math.radians(60 * sign))
    return (center[0] + vx * c - vy * s, center[1] + vx * s + vy * c)


D13 = _rot60(B13, A13, -1)     # BA 바깥(C 반대쪽)
E13 = _rot60(B13, C13, -1)     # BC 위쪽(A 쪽)
F13 = _rot60(A13, C13, -1)     # AC 바깥
for nm, (V, X, Y) in {"D": (D13, B13, A13), "E": (E13, B13, C13), "F": (F13, A13, C13)}.items():
    assert abs(dist(V, X) - dist(X, Y)) < 1e-6 and abs(dist(V, Y) - dist(X, Y)) < 1e-6, nm
_side_d = (A13[0] - B13[0]) * (D13[1] - B13[1]) - (A13[1] - B13[1]) * (D13[0] - B13[0])
_side_c = (A13[0] - B13[0]) * (C13[1] - B13[1]) - (A13[1] - B13[1]) * (C13[0] - B13[0])
assert _side_d * _side_c < 0 and E13[1] < 230 and F13[0] > A13[0]
verify_figure("q13", angles=[(100, A13, B13, C13), (40, D13, E13, A13),
                             (60, B13, D13, A13), (60, B13, E13, C13), (60, A13, F13, C13)],
              lengths=[(1, D13, B13), (1, B13, A13)])
verify_figure("q13-EBC", lengths=[(1, E13, B13), (1, B13, C13)])
S["q13"] = spec_svg({
    "version": 2,
    "points": P(A=A13, B=B13, C=C13, D=D13, E=E13, F=F13),
    "segments": {"DE": ["D", "E"], "EF": ["E", "F"], "FC": ["F", "C"], "BC": ["B", "C"],
                 "DB": ["D", "B"], "DA": ["D", "A"], "AB": ["A", "B"], "AC": ["A", "C"],
                 "AF": ["A", "F"], "EB": ["E", "B"], "EC": ["E", "C"]},
    "labels": {"A": "A", "B": "B", "C": "C", "D": "D", "E": "E", "F": "F"},
})

# ══ q14: 마름모 ABCD, AF⊥BC, ∠ADB=33° → x=∠ACB=57°, y=∠AED=57° ═══════
O14 = (150.0, 100.0)
OD14 = 115.0
OA14 = OD14 * math.tan(math.radians(33))
A14, C14 = (O14[0], O14[1] - OA14), (O14[0], O14[1] + OA14)
B14, D14 = (O14[0] - OD14, O14[1]), (O14[0] + OD14, O14[1])
F14 = foot(A14, B14, C14)
E14 = isect(A14, F14, B14, D14)
verify_figure("q14", angles=[(33, D14, A14, B14), (90, F14, A14, C14), (57, E14, A14, D14),
                             (57, C14, A14, B14), (90, O14, A14, B14)],
              lengths=[(1, A14, B14), (1, B14, C14), (1, C14, D14), (1, D14, A14)])
S["q14"] = spec_svg({
    "version": 2,
    "points": P(A=A14, B=B14, C=C14, D=D14, O=O14, E=E14, F=F14),
    "segments": {"AB": ["A", "B"], "BC": ["B", "C"], "CD": ["C", "D"],
                 "DA": ["D", "A"], "AC": ["A", "C"], "BD": ["B", "D"], "AF": ["A", "F"]},
    "angles": {"rO": {"vertex": "O", "points": ["A", "B"], "right": True},
               "rF": {"vertex": "F", "points": ["A", "B"], "right": True},
               "angD": {"vertex": "D", "points": ["A", "B"], "label": "33°"},
               "angy": {"vertex": "E", "points": ["A", "D"]},
               "angx": {"vertex": "C", "points": ["A", "B"]}},
    "labels": {"A": "A", "B": "B", "C": "C", "D": "D", "O": "O",
               "E": {"text": "E", "position": "SE"}, "F": "F"},
}, extras=lambda T: alabel(T(E14), T(A14), T(D14), _IT.format("y"), 36)
   + alabel(T(C14), T(A14), T(B14), _IT.format("x"), 34))

# ══ q15: 정사각형 ABCD, AD=AE, ∠ADE=80° → ∠ABE=35° ═════════════════════
s15 = 150.0
A15, D15 = (30.0, 70.0), (30.0 + s15, 70.0)
B15, C15 = (30.0, 70.0 + s15), (30.0 + s15, 70.0 + s15)
E15 = add(A15, mul(dirv(20), s15))
verify_figure("q15", angles=[(80, D15, A15, E15), (35, B15, A15, E15), (90, A15, B15, D15)],
              lengths=[(1, A15, D15), (1, A15, E15), (1, A15, B15), (1, B15, C15)])
S["q15"] = spec_svg({
    "version": 2,
    "points": P(A=A15, B=B15, C=C15, D=D15, E=E15),
    "segments": {"AB": ["A", "B"], "BC": ["B", "C"], "CD": ["C", "D"],
                 "AD": {"points": ["A", "D"], "ticks": 2},
                 "AE": {"points": ["A", "E"], "ticks": 2},
                 "ED": ["E", "D"], "BE": ["B", "E"]},
    "angles": {"angD": {"vertex": "D", "points": ["A", "E"], "radius": 10}},
    "labels": {"A": "A", "B": "B", "C": "C", "D": "D", "E": "E"},
}, extras=lambda T: wedge(T(B15), T(A15), T(E15), 18)
   + txt(T(D15)[0] - 19, T(D15)[1] - 9, "80°", 13))

# ══ q16: 평행사변형 네 내각의 이등분선 → 직사각형 EFGH ═══════════════════
A16, D16 = (95.0, 20.0), (375.0, 20.0)
B16 = (46.0, 215.0)
C16 = add(B16, sub(D16, A16))


def _bis(v, p1, p2):
    return bisect_pt(v[0], v[1], p1, p2, 50.0)


bA, bB, bC, bD = (_bis(A16, B16, D16), _bis(B16, A16, C16), _bis(C16, B16, D16),
                  _bis(D16, A16, C16))
E16 = isect(A16, bA, B16, bB)
F16 = isect(A16, bA, D16, bD)
G16 = isect(C16, bC, D16, bD)
H16 = isect(B16, bB, C16, bC)
O16 = isect(E16, G16, H16, F16)
verify_figure("q16", angles=[(90, E16, H16, F16), (90, F16, E16, G16), (90, G16, F16, H16)],
              on_line=[(E16, A16, F16), (E16, B16, H16), (G16, C16, H16), (G16, D16, F16)])


def _q16_marks(T):
    out = []
    for v, p1, p2, kind in ((A16, B16, D16, "x"), (B16, A16, C16, "o"),
                            (C16, B16, D16, "t"), (D16, A16, C16, "d")):
        b = bisect_pt(v[0], v[1], p1, p2, 10)
        for q in (p1, p2):
            x, y = T(bisect_pt(v[0], v[1], q, b, 19))
            if kind == "x":
                out.append(f'<path d="M {x-2.6:.1f} {y-2.6:.1f} L {x+2.6:.1f} {y+2.6:.1f} '
                           f'M {x-2.6:.1f} {y+2.6:.1f} L {x+2.6:.1f} {y-2.6:.1f}" '
                           f'stroke="#111" stroke-width="1"/>')
            elif kind == "o":
                out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.4" fill="none" '
                           f'stroke="#111" stroke-width="0.9"/>')
            elif kind == "t":
                out.append(f'<path d="M {x:.1f} {y-3:.1f} L {x+3:.1f} {y+2.2:.1f} '
                           f'L {x-3:.1f} {y+2.2:.1f} Z" fill="none" stroke="#111" '
                           f'stroke-width="0.9"/>')
            else:
                out.append(dot(x, y, 2.3))
    # O 는 좁은 마름모 안이라 원본처럼 왼쪽 아래 바깥에 두고 짧은 지시선으로 잇는다
    from core.figure_svg import leader
    o = T(O16)
    lab = (T(E16)[0] - 4, T(F16)[1] + 4)
    out.append(leader((lab[0] + 5, lab[1] - 8), o, arrow=False, w=0.9, gap=5))
    out.append(txt(lab[0], lab[1] + 6, "O", 16))
    return "".join(out)


S["q16"] = spec_svg({
    "version": 2,
    "points": P(A=A16, B=B16, C=C16, D=D16, E=E16, F=F16, G=G16, H=H16, O=O16),
    "segments": {"AB": ["A", "B"], "BC": ["B", "C"], "CD": ["C", "D"], "DA": ["D", "A"],
                 "AF": ["A", "F"], "BH": ["B", "H"], "CH": ["C", "H"], "DF": ["D", "F"],
                 "EG": ["E", "G"], "HF": ["H", "F"]},
    "labels": {"A": "A", "B": "B", "C": "C", "D": "D", "E": "E", "F": "F", "G": "G",
               "H": "H"},
}, extras=_q16_marks)

# ══ q17: 닮은 두 삼각기둥(닮음비 2:3) ════════════════════════════════════
# 밑면 삼각형 ABC: AC=4(=GI 6), AB=4(=GH 6), BC=2(=HI 3), 높이 6(=9)
_bx = (16 - 4 + 16) / 8
_by = math.sqrt(16 - _bx * _bx)
k17, dxy = 12.0, (-0.30, 0.55)


def _prj(X, Y, Z, s, o):
    return (o[0] + k17 * s * (X + dxy[0] * Y), o[1] - k17 * s * Z + k17 * s * dxy[1] * Y)


def _prism(s, o, names):
    tri = [(0, 0), (_bx, _by), (4, 0)]           # A, B, C (Y=깊이, 앞쪽 +)
    top = [_prj(x, y, 6, s, o) for x, y in tri]
    bot = [_prj(x, y, 0, s, o) for x, y in tri]
    return dict(zip(names, top + bot))


V1 = _prism(1.0, (40.0, 205.0), "ABCDEF")
V2 = _prism(1.5, (190.0, 205.0), "GHIJKL")
verify_figure("q17", lengths=[(4, V1["A"], V1["C"]), (6, V1["A"], V1["D"])])
verify_figure("q17-큰", lengths=[(6, V2["G"], V2["I"]), (9, V2["G"], V2["J"])])
verify_figure("q17-닮음비-밑", lengths=[(2, V1["A"], V1["C"]), (3, V2["G"], V2["I"])])
verify_figure("q17-닮음비-높이", lengths=[(2, V1["A"], V1["D"]), (3, V2["G"], V2["J"])])


def _prism_svg(V, n, lab):
    a, b, c, d, e, f = (V[x] for x in n)
    pg = lambda *ps: " ".join(f"{p[0]:.1f},{p[1]:.1f}" for p in ps)   # noqa: E731
    return "\n".join([
        f'<polygon points="{pg(a, b, e, d)}" fill="#ebebeb" stroke="none"/>',
        f'<polygon points="{pg(b, c, f, e)}" fill="#f4f4f4" stroke="none"/>',
        f'<polygon points="{pg(a, b, c)}" fill="#efefef" stroke="none"/>',
        line(d, f, 1.2, dash="4 3"),
        line(a, c, 1.9), line(a, b, 1.9), line(b, c, 1.9),
        line(a, d, 1.9), line(b, e, 1.9), line(c, f, 1.9),
        line(d, e, 1.9), line(e, f, 1.9),
    ])


def _dim(p, q, off, content):
    """치수 점선(볼록) + halo 라벨 — content 는 tspan 마크업."""
    from core.figure_svg import meas
    L = dist(p, q)
    nx, ny = -(q[1] - p[1]) / L, (q[0] - p[0]) / L
    mx, my = mid(p, q)
    lx, ly = mx + nx * (off * 2 + 9 * (1 if off > 0 else -1)), my + ny * (off * 2 + 9 * (1 if off > 0 else -1))
    return (meas(*p, *q, off) + "\n" +
            f'<text x="{lx:.1f}" y="{ly + 5:.1f}" font-size="14" {FONT} text-anchor="middle" '
            f'paint-order="stroke" stroke="#fff" stroke-width="4" stroke-linejoin="round">'
            f'{content}</text>')


V = {**V1, **V2}
S["q17"] = f'''<svg viewBox="0 0 330 270" xmlns="http://www.w3.org/2000/svg">
<rect width="330" height="270" fill="#ffffff"/>
{_prism_svg(V1, "ABCDEF", None)}
{_prism_svg(V2, "GHIJKL", None)}
{_dim(V["A"], V["C"], -8, "4 cm")}
{_dim(V["D"], V["A"], -8, "6 cm")}
{_dim(V["D"], V["E"], 8, "4 cm")}
{_dim(V["E"], V["F"], 8, _IT.format("x") + " cm")}
{_dim(V["G"], V["I"], -8, _IT.format("z") + " cm")}
{_dim(V["J"], V["G"], -8, _IT.format("y") + " cm")}
{_dim(V["J"], V["K"], 8, "6 cm")}
{_dim(V["K"], V["L"], 9, "3 cm")}
{txt(V["A"][0] - 9, V["A"][1] - 5, "A", 15)}{txt(V["C"][0] + 9, V["C"][1] - 5, "C", 15)}
{txt(V["B"][0] - 9, V["B"][1] + 16, "B", 15)}
{txt(V["D"][0] - 10, V["D"][1] + 5, "D", 15)}{txt(V["E"][0] + 1, V["E"][1] + 19, "E", 15)}
{txt(V["F"][0] + 10, V["F"][1] + 3, "F", 15)}
{txt(V["G"][0] - 9, V["G"][1] - 5, "G", 15)}{txt(V["I"][0] + 9, V["I"][1] - 5, "I", 15)}
{txt(V["H"][0] - 11, V["H"][1] + 18, "H", 15)}
{txt(V["J"][0] - 10, V["J"][1] + 5, "J", 15)}{txt(V["K"][0] + 1, V["K"][1] + 19, "K", 15)}
{txt(V["L"][0] + 11, V["L"][1] + 3, "L", 15)}
</svg>'''

# ══ q18: 모양이 같은 두 등대(높이 8 m · 12 m) ═══════════════════════════
k18 = 13.0


def _lighthouse(xc, base, H):
    s = H * k18 / 200.0
    tb, tt = 38 * s, 29 * s                 # 몸통 아래·위 반폭
    ty = base - 140 * s                     # 몸통 윗변
    by = ty - 18 * s                        # 띠 윗변
    r = 30 * s
    top = by - r
    return "\n".join([
        f'<polygon points="{xc + 30 * s:.1f},{by - 10 * s:.1f} {xc + 128 * s:.1f},{by - 42 * s:.1f} '
        f'{xc + 128 * s:.1f},{by + 26 * s:.1f}" fill="#d6d6d6" stroke="none"/>',
        f'<polygon points="{xc - tb:.1f},{base:.1f} {xc + tb:.1f},{base:.1f} {xc + tt:.1f},{ty:.1f} '
        f'{xc - tt:.1f},{ty:.1f}" fill="#8f8f8f" stroke="#111" stroke-width="1.3"/>',
        f'<path d="M {xc - r:.1f} {by:.1f} A {r:.1f} {r:.1f} 0 0 1 {xc + r:.1f} {by:.1f} Z" '
        f'fill="#8f8f8f" stroke="#111" stroke-width="1.3"/>',
        f'<rect x="{xc - 40 * s:.1f}" y="{by:.1f}" width="{80 * s:.1f}" height="{18 * s:.1f}" '
        f'fill="#8f8f8f" stroke="#111" stroke-width="1.3"/>',
        dot(xc, top - 3 * s, max(1.6, 4 * s)),
    ]), base - H * k18


def _hdim(x, top, base, label):
    mid_y = (top + base) / 2
    gap = 11
    ah = 6
    return "\n".join([
        line((x - 8, top), (x + 8, top), 1.2), line((x - 8, base), (x + 8, base), 1.2),
        line((x, top + ah), (x, mid_y - gap), 1.2), line((x, mid_y + gap), (x, base - ah), 1.2),
        f'<path d="M {x:.1f} {top:.1f} L {x - 3:.1f} {top + ah:.1f} L {x + 3:.1f} {top + ah:.1f} Z" fill="#111"/>',
        f'<path d="M {x:.1f} {base:.1f} L {x - 3:.1f} {base - ah:.1f} L {x + 3:.1f} {base - ah:.1f} Z" fill="#111"/>',
        txt(x, mid_y + 5, label, 15),
    ])


_b18 = 180.0
_L1, _t1 = _lighthouse(75.0, _b18, 8)
_L2, _t2 = _lighthouse(240.0, _b18, 12)
verify_figure("q18", lengths=[(8, (35, _t1), (35, _b18)), (12, (165, _t2), (165, _b18))])
S["q18"] = f'''<svg viewBox="0 0 350 195" xmlns="http://www.w3.org/2000/svg">
<rect width="350" height="195" fill="#ffffff"/>
{_L1}
{_L2}
{_hdim(35.0, _t1, _b18, "8 m")}
{_hdim(165.0, _t2, _b18, "12 m")}
</svg>'''

# ══ s1(서술형1): ∠A=90°, AB=15·BC=17·CA=8, 내접원 I(r=3) ═════════════════
k19 = 14.0
B19 = (20.0, 150.0)
C19 = (B19[0] + 17 * k19, 150.0)
_ax19 = (225 + 289 - 64) / 34
A19 = (B19[0] + _ax19 * k19, 150.0 - math.sqrt(225 - _ax19 ** 2) * k19)
I19 = incenter(A19, B19, C19)
r19 = 3 * k19
verify_figure("s1", lengths=[(15, A19, B19), (17, B19, C19), (8, C19, A19)],
              angles=[(90, A19, B19, C19)],
              tangents=[(A19, B19, *I19, r19), (A19, C19, *I19, r19), (B19, C19, *I19, r19)])
S["s1"] = spec_svg({
    "version": 2,
    "points": P(A=A19, B=B19, C=C19, I=I19),
    "circles": {"inc": {"center": "I", "radius": round(r19, 3)}},
    "segments": {"AB": ["A", "B"], "BC": ["B", "C"], "CA": ["C", "A"]},
    "angles": {"rA": {"vertex": "A", "points": ["B", "C"], "right": True}},
    "dimensions": {"dimAB": {"points": ["B", "A"], "label": "15 cm"},
                   "dimCA": {"points": ["A", "C"], "label": "8 cm"},
                   "dimBC": {"points": ["B", "C"], "label": "17 cm"}},
    "labels": {"A": "A", "B": "B", "C": "C", "I": "I"},
}, extras=lambda T: dot(*T(I19), 2.6))

# ══ s2(서술형2): 삼각형 ABC 와 내부의 점 P, ∠x·∠y·∠z ════════════════════
A20, B20, C20 = (125.0, 15.0), (20.0, 190.0), (230.0, 190.0)
P20 = incenter(A20, B20, C20)
verify_figure("s2", angles=[(ang(A20, B20, P20), A20, P20, C20),
                            (ang(B20, C20, P20), B20, P20, A20)],
              on_line=[])
S["s2"] = spec_svg({
    "version": 2,
    "points": P(A=A20, B=B20, C=C20, P=P20),
    "segments": {"AB": ["A", "B"], "BC": ["B", "C"], "CA": ["C", "A"],
                 "PA": ["P", "A"], "PB": ["P", "B"], "PC": ["P", "C"]},
    "angles": {"angx": {"vertex": "A", "points": ["B", "P"], "label": "x"},
               "angy": {"vertex": "B", "points": ["C", "P"], "label": "y"},
               "angz": {"vertex": "C", "points": ["A", "P"], "label": "z"}},
    "labels": {"A": "A", "B": "B", "C": "C", "P": "P"},
}, extras=lambda T: dot(*T(P20), 2.6))

# ══ s3(서술형3): 평행사변형 ABCD, CE=ED, AF:FE=2:1, □OCEF ═════════════════
A21, D21 = (60.0, 15.0), (300.0, 15.0)
B21 = (15.0, 165.0)
C21 = add(B21, sub(D21, A21))
O21 = mid(A21, C21)
E21 = mid(C21, D21)
F21 = isect(A21, E21, B21, D21)
verify_figure("s3-CE", lengths=[(1, C21, E21), (1, E21, D21)])
verify_figure("s3", lengths=[(2, A21, F21), (1, F21, E21)],
              on_line=[(O21, B21, D21), (F21, A21, E21)])
S["s3"] = spec_svg({
    "version": 2,
    "points": P(A=A21, B=B21, C=C21, D=D21, O=O21, E=E21, F=F21),
    "segments": {"AB": ["A", "B"], "BC": ["B", "C"], "DA": ["D", "A"],
                 "CE": {"points": ["C", "E"], "ticks": 2},
                 "ED": {"points": ["E", "D"], "ticks": 2},
                 "AC": ["A", "C"], "BD": ["B", "D"], "AE": ["A", "E"]},
    "regions": {"OCEF": {"boundary": [{"seg": ["O", "C"]}, {"seg": ["C", "E"]},
                                      {"seg": ["E", "F"]}, {"seg": ["F", "O"]}],
                         "fill": "#cfcfcf"}},
    "labels": {"A": "A", "B": "B", "C": "C", "D": "D", "O": "O", "E": "E", "F": "F"},
})

# ══ s4(서술형4): 평행사변형 ABCD 각 변의 연장선 위 AP=BQ=CR=DS ═══════════
A22, D22 = (110.0, 35.0), (320.0, 60.0)
B22 = (45.0, 170.0)
C22 = add(B22, sub(D22, A22))
k22 = 36.0
P22 = add(A22, mul(unit(D22, A22), k22))
Q22 = add(B22, mul(unit(A22, B22), k22))
R22 = add(C22, mul(unit(B22, C22), k22))
S22 = add(D22, mul(unit(C22, D22), k22))
verify_figure("s4", lengths=[(1, A22, P22), (1, B22, Q22), (1, C22, R22), (1, D22, S22)],
              on_line=[(P22, D22, A22), (Q22, A22, B22), (R22, B22, C22), (S22, C22, D22)])
S["s4"] = spec_svg({
    "version": 2,
    "points": P(A=A22, B=B22, C=C22, D=D22, P=P22, Q=Q22, R=R22, S=S22),
    "segments": {"PD": ["P", "D"], "QA": ["Q", "A"], "RB": ["R", "B"], "SC": ["S", "C"],
                 "PQ": ["P", "Q"], "QR": ["Q", "R"], "RS": ["R", "S"], "SP": ["S", "P"]},
    "labels": {"A": {"text": "A", "position": "SE"}, "B": {"text": "B", "position": "NE"},
               "C": {"text": "C", "position": "NW"}, "D": {"text": "D", "position": "SW"},
               "P": {"text": "P", "position": "NW"}, "Q": {"text": "Q", "position": "SW"},
               "R": {"text": "R", "position": "SE"}, "S": {"text": "S", "position": "NE"}},
})

if __name__ == "__main__":
    from core.figure_generator import _svg_to_png_bytes
    miss = unverified(S)
    if miss:
        raise SystemExit(f"검산 누락(verify_figure 미호출): {miss}")
    only = sys.argv[1:]
    bad = []
    for k, svg in S.items():
        if only and k not in only:
            continue
        issues = lint_svg(svg)
        if issues:
            bad.append(k)
            print(k, "LINT:", "; ".join(issues))
        vb = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
        png = _svg_to_png_bytes(svg, width=int(float(vb.group(1)) * 3))
        if not png:
            print(k, "PNG FAIL")
            bad.append(k)
            continue
        open(os.path.join(OUT, f"{k}.png"), "wb").write(png)
        print(k, "ok")
    if bad:
        raise SystemExit(f"lint 실패: {bad}")
