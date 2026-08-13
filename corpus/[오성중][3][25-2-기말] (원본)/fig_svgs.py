# -*- coding: utf-8 -*-
"""오성중3 25-2-기말 — 그림 13개 core.figure_svg 엔진 작도(정의값 기하)."""
import math
import os
import sys
import tempfile

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from core.figure_svg import (C, FONT, IT, SVGTextRun, angle_arc, angle_mark, arc, arc_measured, bisect_pt, circ, circle_pt, dim_label, dot, eq_angle, eq_tick, halo_angle, halo_text, isect, line, lint_svg, meas, measured, measured_runs, pt, rangle, rangle_at, ray_angle, seci, txt, unverified, verify_figure)

OUT = os.environ.get(
    "FIG_SVG_OUT",
    str(Path(tempfile.gettempdir()) / "exam_figure_svg" / "oseong"),
)
os.makedirs(OUT, exist_ok=True)
S = {}


# ── q1: 원 O, 평행현 AB·CD=24cm, 지름 30cm ──────────────────────────
cx, cy, r = 118, 118, 93          # r=15cm → 6.2px/cm
h = 12 / 15 * r                    # 반현 24/2=12cm
d9 = 9 / 15 * r                    # 중심거리 9cm
A1, B1 = (cx - h, cy - d9), (cx + h, cy - d9)
C1, D1 = (cx - h, cy + d9), (cx + h, cy + d9)
dia1, dia2 = C(cx, cy, 205, r), C(cx, cy, 25, r)
# 검산: 평행현 24cm 두 개 + 지름 30cm(=A–D, 12²+9²=15²)
verify_figure("q1", lengths=[(24, A1, B1), (24, C1, D1), (30, A1, D1)])
S["q1"] = f'''<svg viewBox="0 0 245 245" xmlns="http://www.w3.org/2000/svg">
{circ(cx, cy, r)}{dot(cx, cy)}
{line(A1, B1)}{line(C1, D1)}
{line(A1, D1)}
{txt(cx - 16, cy + 16, "O", anc="end")}
{txt(A1[0] - 8, A1[1] - 6, "A", anc="end")}{txt(B1[0] + 8, B1[1] - 6, "B")}
{txt(C1[0] - 8, C1[1] + 16, "C", anc="end")}{txt(D1[0] + 8, D1[1] + 16, "D")}
{measured(*A1, *B1, -9, "24cm", 12)}
{measured(*C1, *D1, 9, "24cm", 12)}
{halo_text(A1[0] + 0.42 * (cx - A1[0]) + 16, A1[1] + 0.42 * (cy - A1[1]) - 6, "30cm", 13)}
</svg>'''

# ── q2: 외부점 A 의 두 접선(P·Q) + 접선 BC(접점 D), PB=15·BA=17 ──────
# 조건 유도: 대칭이므로 BD=BP=15, CD=CQ=15, BC⊥OA 이고 D 는 OA 위.
# 직각 △ABD 에서 AD=√(17²−15²)=8. 접선길이 AP=15+17=32.
# AP²=OA²−r², OA=r+8 → 1024=16r+64 → r=60. 즉 **OA:r=68:60** — A 는 원 바로 옆.
# (기존 작도는 OA/r=3.11 로 A 를 멀리 뒀다 — 라벨 15:17 과 모순이었다.)
cx, cy = 152, 150
r = 130
k2 = r / 60.0                                   # px per cm
A2 = (cx + 68 * k2, cy)
al2 = math.degrees(math.acos(60.0 / 68.0))
P2, Qt2 = C(cx, cy, al2, r), C(cx, cy, -al2, r)
D2 = (cx + r, cy)
tAB = 17.0 / 32.0
B2 = (A2[0] + (P2[0] - A2[0]) * tAB, A2[1] + (P2[1] - A2[1]) * tAB)
C2 = (A2[0] + (Qt2[0] - A2[0]) * tAB, A2[1] + (Qt2[1] - A2[1]) * tAB)
Pe2 = (A2[0] + (P2[0] - A2[0]) * 2.2, A2[1] + (P2[1] - A2[1]) * 2.2)
Qe2 = (A2[0] + (Qt2[0] - A2[0]) * 2.2, A2[1] + (Qt2[1] - A2[1]) * 2.2)
verify_figure("q2", lengths=[(15, P2, B2), (17, B2, A2), (32, P2, A2),
                             (60, (cx, cy), D2), (8, D2, A2)])
S["q2"] = f'''<svg viewBox="0 0 340 312" xmlns="http://www.w3.org/2000/svg">
{circ(cx, cy, r)}{dot(cx, cy)}
{line(Pe2, A2)}{line(Qe2, A2)}{line(B2, C2)}{line((cx, cy), A2, 1)}
{txt(cx - 11, cy - 5, "O", 14, anc="end")}
{txt(A2[0] + 9, A2[1] + 6, "A")}
{txt(P2[0] + 6, P2[1] - 11, "P", 14)}{txt(Qt2[0] + 4, Qt2[1] + 20, "Q", 14)}
{txt(B2[0] + 6.9, B2[1] - 1.2, "B", 14, anc="start")}
{txt(C2[0] + 4, C2[1] + 16, "C", 14)}
{txt(D2[0] - 7, D2[1] - 7, "D", 14, anc="end")}
{measured(*P2, *B2, -19, "15cm", 12)}
{measured(*B2, *A2, -19, "17cm", 12)}
</svg>'''

# ── q3: 원 O 에 외접하는 등변사다리꼴 AD=5·BC=20 ─────────────────────
sc = 14
B3, C3 = (22, 192), (22 + 20 * sc / 14 * 14, 192)
C3 = (22 + 280, 192)
A3, D3 = (22 + 105, 52), (22 + 175, 52)
ox3, oy3, r3 = (B3[0] + C3[0]) / 2, 122, 70
# 검산: AD=5·BC=20, 외접 사다리꼴이면 AB=DC=(5+20)/2=12.5, 높이 10, 내접원 r=5
verify_figure("q3", lengths=[(5, A3, D3), (20, B3, C3), (12.5, A3, B3),
                             (5, (ox3, oy3), (ox3, oy3 + r3))])
S["q3"] = f'''<svg viewBox="0 0 325 245" xmlns="http://www.w3.org/2000/svg">
<polygon points="{pt(*A3)} {pt(*D3)} {pt(*C3)} {pt(*B3)}" fill="none" stroke="#000" stroke-width="2"/>
{circ(ox3, oy3, r3)}{dot(ox3, oy3)}
{txt(ox3 + 10, oy3 + 5, "O")}
{txt(A3[0] - 8, A3[1] - 8, "A", anc="end")}{txt(D3[0] + 8, D3[1] - 8, "D")}
{txt(B3[0] - 8, B3[1] + 14, "B", anc="end")}{txt(C3[0] + 8, C3[1] + 14, "C")}
{eq_angle(*B3, C3, A3, 26, 2)}{eq_angle(*C3, D3, B3, 26, 2)}
{measured(*A3, *D3, -10, "5cm")}
{measured(*B3, *C3, 12, "20cm")}
</svg>'''

# ── q4: 지름 AB, ∠APQ=54°(점선 호) → 구하는 ∠QRB=36°(점선 호) ────────
# 조건 유도: ∠APQ=54° 는 호 AQ 의 원주각 → 호 AQ=108° → Q=180°+108°=288°.
# 그러면 호 QB=72° → ∠QRB=36°(정답 ①). P·R 위치는 각과 무관하나 원본을 따름.
# ⚠️ 원본의 P–B 선은 **연필**(회색·물결)이라 그리지 않는다.
cx, cy, r = 130, 122, 95
A4, B4 = (cx - r, cy), (cx + r, cy)
P4, R4, Qt4 = C(cx, cy, 122, r), C(cx, cy, 62, r), C(cx, cy, 288, r)
verify_figure("q4", angles=[(54, P4, A4, Qt4), (36, R4, Qt4, B4)])
S["q4"] = f'''<svg viewBox="0 0 260 250" xmlns="http://www.w3.org/2000/svg">
{circ(cx, cy, r)}{dot(cx, cy)}
{line(A4, B4)}
{line(P4, A4)}{line(P4, Qt4)}{line(R4, Qt4)}{line(R4, B4)}
{angle_mark(*P4, A4, Qt4, r=21)}
{halo_angle(*P4, A4, Qt4, 36, "54°", 13)}
{angle_mark(*R4, Qt4, B4, r=19)}
{txt(cx - 3, cy - 8, "O", 14)}
{txt(A4[0] - 9, A4[1] + 5, "A", anc="end")}{txt(B4[0] + 9, B4[1] + 5, "B")}
{txt(P4[0] - 6, P4[1] - 8, "P", anc="end")}{txt(R4[0] + 6, R4[1] - 6, "R")}
{txt(Qt4[0] - 2, Qt4[1] + 18, "Q")}
</svg>'''

# ── q5: 외접원·내심 I, ∠B=45°, AI=4·ID=11 ───────────────────────────
cx, cy, r = 132, 132, 100
A5, B5, C5 = C(cx, cy, 100, r), C(cx, cy, 205, r), C(cx, cy, 10, r)
D5 = C(cx, cy, 287.5, r)
I5 = (A5[0] + 4 / 15 * (D5[0] - A5[0]), A5[1] + 4 / 15 * (D5[1] - A5[1]))
# 검산: AI=4·ID=11(AD=15) + ∠B=45°(호 AC=90°)
verify_figure("q5", lengths=[(4, A5, I5), (11, I5, D5)],
              angles=[(45, B5, A5, C5)])
S["q5"] = f'''<svg viewBox="0 0 265 265" xmlns="http://www.w3.org/2000/svg">
{circ(cx, cy, r)}
{line(A5, B5)}{line(A5, C5)}{line(B5, C5)}
{line(A5, D5)}{line(C5, D5)}{line(I5, C5)}
{dot(*I5, 2.2)}
<path d="{angle_arc(*B5, A5, C5, 22)}" fill="none" stroke="#000" stroke-width="1"/>
{halo_angle(*B5, A5, C5, 38, "45°", 12)}
{txt(A5[0], A5[1] - 9, "A")}{txt(B5[0] - 9, B5[1] + 10, "B", anc="end")}
{txt(C5[0] + 9, C5[1] + 4, "C")}{txt(D5[0] + 4, D5[1] + 16, "D")}
{txt(I5[0] + 9, I5[1] - 2, "I")}
{measured(*A5, *I5, -11, "4cm", 11, t=0.62)}
{measured(*I5, *D5, -12, "11cm", 11)}
</svg>'''

# ── q6: 두 원 교점 E·F, 직선 AED·BFC, 사각형 ─────────────────────────
o1, o2 = (95, 122), (200, 122)
r1, r2 = 78, 85
dd = o2[0] - o1[0]
ix = (dd * dd + r1 * r1 - r2 * r2) / (2 * dd)
iy = math.sqrt(r1 * r1 - ix * ix)
E6, F6 = (o1[0] + ix, o1[1] - iy), (o1[0] + ix, o1[1] + iy)
A6 = C(*o1, 150, r1)
_, D6 = seci(A6, ray_angle(*A6, *E6), *o2, r2)
B6 = C(*o1, 215, r1)
_, C6 = seci(B6, ray_angle(*B6, *F6), *o2, r2)
S["q6"] = f'''<svg viewBox="0 0 300 245" xmlns="http://www.w3.org/2000/svg">
{circ(*o1, r1)}{circ(*o2, r2)}{dot(*o1)}{dot(*o2)}
{line(A6, D6)}{line(B6, C6)}{line(A6, B6)}{line(D6, C6)}{line(E6, F6)}
{txt(o1[0] - 2, o1[1] + 18, "O")}{txt(o2[0] + 4, o2[1] + 18, "O′")}
{txt(A6[0] - 8, A6[1] - 4, "A", anc="end")}{txt(D6[0] + 6, D6[1] - 4, "D")}
{txt(B6[0] - 8, B6[1] + 12, "B", anc="end")}{txt(C6[0] + 6, C6[1] + 12, "C")}
{txt(E6[0] - 3, E6[1] - 9, "E")}{txt(F6[0] - 3, F6[1] + 19, "F")}
</svg>'''

# ── q7: 원 위 5점, 두 할선이 P(53°)에서 만남 ─────────────────────────
cx, cy, r = 115, 125, 88
P7 = (265, 126)
E7, A7 = seci(P7, 153.5, cx, cy, r)
D7, C7 = seci(P7, 206.5, cx, cy, r)
B7 = C(cx, cy, 172, r)
# 검산: 두 할선이 이루는 ∠APC=53°
verify_figure("q7", angles=[(53, P7, A7, C7)])
S["q7"] = f'''<svg viewBox="0 0 310 255" xmlns="http://www.w3.org/2000/svg">
{circ(cx, cy, r)}{dot(cx, cy)}
{line(A7, P7)}{line(C7, P7)}{line(B7, A7)}{line(B7, D7)}{line(A7, C7)}{line(E7, D7)}
<path d="{angle_arc(*P7, A7, C7, 26)}" fill="none" stroke="#000" stroke-width="1"/>
{txt(P7[0] - 32, P7[1] + 4, "53°", 12, anc="end")}
{txt(cx - 8, cy + 8, "O", 15)}
{txt(A7[0] - 2, A7[1] - 9, "A")}{txt(E7[0] + 5, E7[1] - 7, "E")}
{txt(D7[0] + 6, D7[1] + 16, "D")}{txt(C7[0] - 4, C7[1] + 17, "C")}
{txt(B7[0] - 9, B7[1] + 5, "B", anc="end")}{txt(P7[0] + 8, P7[1] + 5, "P")}
</svg>'''

# ── q8: 내접 사각형 ABCD + 접선 BT, 호AB:호BC=5:3, ∠CBT=48° ─────────
# 조건 유도: ∠CBT=48° 는 접현각 → 호 BC=96°. 호AB:호BC=5:3 → 호 AB=160°.
# B 를 아래(270°)에 두면 A=270°+160°=110°(좌상), C=270°+96°=366°→6°(우).
# D 는 A·C 사이 호 위(원본 위치 58°). 구하는 ∠ABC=52°(호 AC=104°).
cx, cy, r = 150, 118, 90
B8 = (cx, cy + r)
A8, D8, C8 = C(cx, cy, 110, r), C(cx, cy, 58, r), C(cx, cy, 6, r)
T8 = (315, cy + r)
verify_figure("q8", angles=[(48, B8, T8, C8), (52, B8, A8, C8)],
              arcs=[(5, cx, cy, r, 110, 270), (3, cx, cy, r, 270, 366)])
S["q8"] = f'''<svg viewBox="0 0 345 250" xmlns="http://www.w3.org/2000/svg">
{circ(cx, cy, r)}{dot(cx, cy)}
{line((35, B8[1]), (330, B8[1]))}
{line(A8, B8)}{line(B8, C8)}{line(C8, D8)}{line(D8, A8)}
{dot(*T8, 2.4)}
{angle_mark(*B8, C8, T8, r=25, dash=False)}
{halo_angle(*B8, C8, T8, 40, "48°", 12.5)}
{angle_mark(*B8, A8, C8, r=32, n=2, gap=6)}
{txt(cx + 2, cy + 5, "O", 14, anc="start")}
{txt(A8[0] - 9, A8[1] - 2, "A", anc="end")}{txt(D8[0] + 2, D8[1] - 8, "D")}
{txt(C8[0] + 9, C8[1] + 2, "C")}{txt(B8[0] - 4, B8[1] + 20, "B")}
{txt(T8[0], T8[1] + 20, "T")}
</svg>'''

# ── q9: 내접 △ABC, 접선·BC연장 교점 P, ∠APB 이등분선↔AC=Q, ∠BAC=56° ─
cx, cy, r = 245, 128, 72
A9 = C(cx, cy, 110, r)
B9, C9 = C(cx, cy, 205, r), C(cx, cy, 317, r)
ub = (B9[0] - C9[0], B9[1] - C9[1])
Lb = math.hypot(*ub)
ub = (ub[0] / Lb, ub[1] / Lb)
tx, ty = A9[0] - cx, A9[1] - cy
tv = (-ty / r, tx / r)
den = ub[0] * tv[1] - ub[1] * tv[0]
s9 = ((A9[0] - C9[0]) * tv[1] - (A9[1] - C9[1]) * tv[0]) / den
P9 = (C9[0] + s9 * ub[0], C9[1] + s9 * ub[1])
u1 = ((A9[0] - P9[0]), (A9[1] - P9[1]))
L1 = math.hypot(*u1)
u2 = ((B9[0] - P9[0]), (B9[1] - P9[1]))
L2 = math.hypot(*u2)
bis = (u1[0] / L1 + u2[0] / L2, u1[1] / L1 + u2[1] / L2)
ua = (C9[0] - A9[0], C9[1] - A9[1])
den2 = bis[0] * ua[1] - bis[1] * ua[0]
t9 = ((A9[0] - P9[0]) * ua[1] - (A9[1] - P9[1]) * ua[0]) / den2
Q9 = (P9[0] + t9 * bis[0], P9[1] + t9 * bis[1])
tanA = (A9[0] + tv[0] * 50, A9[1] + tv[1] * 50)
verify_figure("q9", angles=[(56, A9, B9, C9)])
S["q9"] = f'''<svg viewBox="0 0 350 225" xmlns="http://www.w3.org/2000/svg">
{circ(cx, cy, r)}
{line(P9, tanA)}
{line(P9, C9)}{line(A9, B9)}{line(A9, C9)}{line(P9, Q9)}
{angle_mark(*A9, B9, C9, r=22, dash=False)}
{angle_mark(*Q9, A9, P9, r=17)}
{dot(*bisect_pt(*P9, A9, Q9, 42), 1.9)}{dot(*bisect_pt(*P9, Q9, B9, 42), 1.9)}
{txt(A9[0] + 4, A9[1] + 42, "56°", 11.5)}
{txt(P9[0] - 9, P9[1] + 5, "P", anc="end")}{txt(A9[0] - 2, A9[1] - 9, "A")}
{txt(Q9[0] + 9, Q9[1] - 2, "Q")}
{txt(B9[0] - 4, B9[1] + 18, "B")}{txt(C9[0] + 8, C9[1] + 12, "C")}
</svg>'''

# ── q15: 산점도(말하기·쓰기 0~10, 20점) ──────────────────────────────
pts = [(1, 1), (3, 2), (4, 2), (5, 2), (5, 3), (3, 4), (5, 4), (7, 4), (3, 5),
       (6, 5), (7, 6), (8, 6), (5, 7), (9, 7), (6, 8), (7, 8), (9, 8), (7, 9),
       (9, 9), (10, 10)]
ox, oy, s15 = 64, 252, 21
grid = "".join(f'<line x1="{ox + i * s15}" y1="{oy}" x2="{ox + i * s15}" y2="{oy - 10 * s15}" stroke="#bbb" stroke-width="0.7"/>'
               for i in range(1, 11)) + "".join(
    f'<line x1="{ox}" y1="{oy - j * s15}" x2="{ox + 10 * s15}" y2="{oy - j * s15}" stroke="#bbb" stroke-width="0.7"/>'
    for j in range(1, 11))
dots15 = "".join(dot(ox + x * s15, oy - y * s15, 3.4) for x, y in pts)
xt = "".join(txt(ox + i * s15, oy + 17, str(i), 11.5) for i in range(1, 11))
yt = "".join(txt(ox - 7, oy - j * s15 + 4, str(j), 11.5, anc="end") for j in range(1, 11))
ylab = "".join(f'<tspan x="20" dy="{"0" if i == 0 else "14"}">{ch}</tspan>'
               for i, ch in enumerate("쓰기점수"))
S["q15"] = f'''<svg viewBox="0 0 320 300" xmlns="http://www.w3.org/2000/svg">
{grid}
<line x1="{ox}" y1="{oy}" x2="{ox + 10 * s15 + 14}" y2="{oy}" stroke="#000" stroke-width="1.3"/>
<path d="M {ox + 10 * s15 + 10} {oy - 4} L {ox + 10 * s15 + 18} {oy} L {ox + 10 * s15 + 10} {oy + 4} Z" fill="#000"/>
<line x1="{ox}" y1="{oy}" x2="{ox}" y2="{oy - 10 * s15 - 14}" stroke="#000" stroke-width="1.3"/>
<path d="M {ox - 4} {oy - 10 * s15 - 10} L {ox} {oy - 10 * s15 - 18} L {ox + 4} {oy - 10 * s15 - 10} Z" fill="#000"/>
{dots15}{xt}{yt}
{txt(ox - 7, oy + 17, "0", 11.5, anc="end")}
<text x="20" y="60" font-size="12" {FONT}>{ylab}<tspan x="20" dy="14">(점)</tspan></text>
{txt(ox + 5 * s15, oy + 40, "말하기 점수(점)", 12)}
</svg>'''

# ── q16: <보기> 산점도 7개(ㄱ~ㅅ) — 3열×3행, 조밀한 점구름 ─────────────
import random

_rnd16 = random.Random(20260813)
CW16, CH16 = 150, 112                                   # 셀(축 포함) 크기
IT_X16 = '<tspan font-style="italic">x</tspan>'
IT_Y16 = '<tspan font-style="italic">y</tspan>'


def _cloud16(x0, y0, cxr, cyr, ar, br, rot, density=1190):
    """셀 안 회전 타원에 **균일 밀도**로 점을 뿌린다(원본은 stipple 점구름).

    밀도를 상수로 둬야 '좁게 모일수록 강한 상관'이 점 개수가 아니라 **띠의 폭**
    으로 읽힌다 — 이 문항의 정답 ①(ㄷ이 ㄹ보다 강함)이 바로 그 폭 비교다.
    """
    n = max(24, int(round(density * math.pi * ar * br)))
    ca, sa = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    out = []
    while len(out) < n:
        u, v = _rnd16.uniform(-1, 1), _rnd16.uniform(-1, 1)
        if u * u + v * v > 1:              # 단위원 기각표집 → 타원 안 균일분포
            continue
        ex, ey = u * ar, v * br
        rx, ry = cxr + ex * ca - ey * sa, cyr + ex * sa + ey * ca
        out.append(dot(x0 + rx * CW16, y0 + CH16 - ry * CH16, 1.0))
    return "".join(out)


def _axes16(x0, y0, lab):
    """점선 축 + 화살촉 + O·x·y 라벨 — 원본 셀의 고정 서식(21개 전부 누락이었음)."""
    ox, oy = x0 + 40, y0 + CH16 - 12      # 항목라벨 자리를 왼쪽에 비운다
    tx, ty = x0 + CW16 - 2, y0 + 3
    d = 'stroke="#000" stroke-width="1.1" stroke-dasharray="1.4 2.2"'
    return "".join([
        f'<line x1="{ox}" y1="{oy}" x2="{tx - 7}" y2="{oy}" {d}/>',
        f'<line x1="{ox}" y1="{oy}" x2="{ox}" y2="{ty + 7}" {d}/>',
        f'<path d="M {tx} {oy} L {tx - 7} {oy - 2.8} L {tx - 7} {oy + 2.8} Z" fill="#000"/>',
        f'<path d="M {ox} {ty} L {ox - 2.8} {ty + 7} L {ox + 2.8} {ty + 7} Z" fill="#000"/>',
        halo_text(x0 + 2, y0 + 15, lab + ".", 13, anc="start"),
        halo_text(ox - 6, ty + 12, IT_Y16, 12, anc="end"),
        halo_text(tx + 2, oy + 14, IT_X16, 12, anc="middle"),
        txt(ox - 10, oy + 14, "O", 12.5),
    ])


# (중심x, 중심y, 긴반지름, 짧은반지름, 기울기°) — 셀 정규좌표(원점 좌하단)
SHAPE16 = {
    "ㄱ": (0.56, 0.60, 0.30, 0.075, 48),     # 강한 양 — 좁은 띠
    "ㄴ": (0.56, 0.60, 0.29, 0.165, 45),     # 약한 양 — 넓은 띠
    "ㄷ": (0.58, 0.58, 0.31, 0.050, -44),    # 강한 음 — 가장 좁음(정답 ①의 근거)
    "ㄹ": (0.52, 0.57, 0.30, 0.155, -40),    # 약한 음 — 넓은 띠
    "ㅁ": (0.52, 0.52, 0.185, 0.185, 0),     # 상관 없음 — 원형
    "ㅂ": (0.56, 0.48, 0.30, 0.088, 0),      # x 변해도 y 일정 — 가로로 납작
    "ㅅ": (0.42, 0.55, 0.070, 0.265, 0),     # y 변해도 x 일정 — 세로로 길쭉
}
cells16 = []
for _i16, _lab16 in enumerate("ㄱㄴㄷㄹㅁㅂㅅ"):
    _gx16, _gy16 = 26 + (_i16 % 3) * 160, 40 + (_i16 // 3) * 120
    cells16.append(_axes16(_gx16, _gy16, _lab16)
                   + _cloud16(_gx16, _gy16, *SHAPE16[_lab16]))
BW16, BH16 = 510, 404
S["q16"] = f'''<svg viewBox="0 0 {BW16} {BH16}" xmlns="http://www.w3.org/2000/svg">
<path d="M 5 22 L 196 22" stroke="#000" stroke-width="1.4" fill="none"/>
<path d="M 314 22 L {BW16 - 5} 22" stroke="#000" stroke-width="1.4" fill="none"/>
<path d="M 5 22 L 5 {BH16 - 5} L {BW16 - 5} {BH16 - 5} L {BW16 - 5} 22" stroke="#000" stroke-width="1.4" fill="none"/>
{txt(255, 27, "< 보 기 >", 14)}
{"".join(cells16)}
</svg>'''

# ── s1: 반원 O 위 사다리꼴 ABCD, DC=8·AD=10(접점 P) ─────────────────
sc = 22
B_1, C_1 = (80, 215), (256, 215)
O_1 = ((B_1[0] + C_1[0]) / 2, 215)
r_1 = 88
A_1 = (80, 215 - 2 * sc)
D_1 = (256, 215 - 8 * sc)
ad = (D_1[0] - A_1[0], D_1[1] - A_1[1])
Lad = math.hypot(*ad)
tP = ((O_1[0] - A_1[0]) * ad[0] + (O_1[1] - A_1[1]) * ad[1]) / (Lad * Lad)
P_1 = (A_1[0] + tP * ad[0], A_1[1] + tP * ad[1])
# 검산: AD=10·DC=8 → AP=AB=2, BC=√(10²−6²)=8, 반원 r=4
verify_figure("s1", lengths=[(10, A_1, D_1), (8, D_1, C_1), (8, B_1, C_1),
                             (2, A_1, B_1), (4, O_1, C_1)])
S["s1"] = f'''<svg viewBox="0 0 350 245" xmlns="http://www.w3.org/2000/svg">
<path d="{arc(O_1[0], O_1[1], r_1, 0, 180)}" fill="none" stroke="#000" stroke-width="2"/>
{line(B_1, C_1)}{dot(*O_1)}
{line(B_1, A_1)}{line(C_1, D_1)}{line(A_1, D_1)}
{txt(O_1[0], O_1[1] + 18, "O")}
{txt(A_1[0] - 9, A_1[1] + 2, "A", anc="end")}{txt(B_1[0] - 9, B_1[1] + 6, "B", anc="end")}
{txt(C_1[0] + 9, C_1[1] + 6, "C")}{txt(D_1[0] + 4, D_1[1] - 8, "D")}
{txt(P_1[0] - 6, P_1[1] - 9, "P", anc="end")}
{measured(*A_1, *D_1, -10, "10cm", 12)}
{measured(*D_1, *C_1, -11, "8cm", 11.5)}
</svg>'''

# ── s2: 반지름 18cm 원, 현 AB·CD 연장선 교점 P, 호AB=9π·호CD=13π ─────
# 조건 유도: 원주 36π → 호AB=90°, 호CD=130°. 원 밖의 각 ∠APC=60°
# → 호AC−호BD=120°, 호AC+호BD=360−90−130=140° → 호AC=130°·호BD=10°.
# 시계방향 A(96°)→B(6°)→D(−4°)→C(−134°). P 는 두 현 연장선의 교점(≈1.14r).
cx, cy, r = 150, 150, 118
aA2, aB2, aD2, aC2 = 96.0, 6.0, -4.0, -134.0
A_2, B_2 = C(cx, cy, aA2, r), C(cx, cy, aB2, r)
D_2, C_2 = C(cx, cy, aD2, r), C(cx, cy, aC2, r)
P_2 = isect(A_2, B_2, C_2, D_2)
verify_figure("s2", angles=[(60, P_2, A_2, C_2)],
              arcs=[(9, cx, cy, r, aA2, aB2), (13, cx, cy, r, aC2, aD2)])
S["s2"] = f'''<svg viewBox="0 0 336 302" xmlns="http://www.w3.org/2000/svg">
{circ(cx, cy, r)}
{line(A_2, P_2)}{line(C_2, P_2)}
{angle_mark(*P_2, A_2, C_2, r=19, dash=False)}
{halo_text(P_2[0] + 13, P_2[1] - 13, "60°", 12.5, anc="start")}
{txt(A_2[0] - 4, A_2[1] - 10, "A")}
{txt(B_2[0] + 5, B_2[1] - 8, "B", 14, anc="start")}
{txt(C_2[0] - 9, C_2[1] + 6, "C", anc="end")}
{txt(D_2[0] - 4, D_2[1] + 18, "D", 14, anc="end")}
{txt(P_2[0] + 8, P_2[1] + 17, "P")}
{arc_measured(cx, cy, r, aA2, aB2, txt="9πcm")}
{arc_measured(cx, cy, r, aC2, aD2, txt="13πcm")}
</svg>'''

if __name__ == "__main__":
    from core.figure_generator import _svg_to_png_bytes
    W = {"q1": 200, "q2": 265, "q3": 240, "q4": 205, "q5": 210, "q6": 235,
         "q7": 270, "q8": 255, "q9": 268, "q15": 245, "q16": 330, "s1": 262, "s2": 268}
    miss = unverified(S)
    if miss:
        raise SystemExit(f"검산 누락(verify_figure 미호출): {miss}")
    for k, svg in S.items():
        issues = lint_svg(svg)
        if issues:
            raise RuntimeError(f"{k} SVG lint 실패: {'; '.join(issues)}")
        png = _svg_to_png_bytes(svg, width=W[k] * 3)
        if not png:
            print(k, "FAIL")
            continue
        open(os.path.join(OUT, f"{k}.png"), "wb").write(png)
        print(k, "ok")
