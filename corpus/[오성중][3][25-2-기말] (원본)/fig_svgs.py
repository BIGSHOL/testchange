# -*- coding: utf-8 -*-
"""오성중3 25-2-기말 — 그림 13개 core.figure_svg 엔진 작도(정의값 기하)."""
import math
import os
import sys

sys.path.insert(0, r"F:\시험지변환기")
sys.stdout.reconfigure(encoding="utf-8")
from core.figure_svg import (FONT, IT, angle_arc, arc, dim_label, eq_tick, meas,
                             measured, pt, rangle, ray_angle)

OUT = r"F:\tmp\figcrop\_os2\_fig"
os.makedirs(OUT, exist_ok=True)
S = {}


def C(cx, cy, ang, r):
    """원 위 점(수학각 도)."""
    return (cx + r * math.cos(math.radians(ang)), cy - r * math.sin(math.radians(ang)))


def line(p, q, w=2):
    return (f'<line x1="{p[0]:.1f}" y1="{p[1]:.1f}" x2="{q[0]:.1f}" y2="{q[1]:.1f}" '
            f'stroke="#000" stroke-width="{w}"/>')


def txt(x, y, t, fs=15, anc="middle", it=False):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{fs}" {IT if it else FONT} '
            f'text-anchor="{anc}">{t}</text>')


def dot(x, y, r=2.4):
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="#000"/>'


def circ(cx, cy, r, w=2):
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#000" stroke-width="{w}"/>'


def seci(P, ang_deg, cx, cy, r):
    """P 에서 수학각 방향 반직선이 원과 만나는 두 점(가까운 것, 먼 것)."""
    ux, uy = math.cos(math.radians(ang_deg)), -math.sin(math.radians(ang_deg))
    fx, fy = P[0] - cx, P[1] - cy
    b = fx * ux + fy * uy
    c0 = fx * fx + fy * fy - r * r
    d = math.sqrt(b * b - c0)
    t1, t2 = -b - d, -b + d
    return ((P[0] + t1 * ux, P[1] + t1 * uy), (P[0] + t2 * ux, P[1] + t2 * uy))


# ── q1: 원 O, 평행현 AB·CD=24cm, 지름 30cm ──────────────────────────
cx, cy, r = 118, 118, 93          # r=15cm → 6.2px/cm
h = 12 / 15 * r                    # 반현 24/2=12cm
d9 = 9 / 15 * r                    # 중심거리 9cm
A1, B1 = (cx - h, cy - d9), (cx + h, cy - d9)
C1, D1 = (cx - h, cy + d9), (cx + h, cy + d9)
dia1, dia2 = C(cx, cy, 205, r), C(cx, cy, 25, r)
S["q1"] = f'''<svg viewBox="0 0 245 245" xmlns="http://www.w3.org/2000/svg">
{circ(cx, cy, r)}{dot(cx, cy)}
{line(A1, B1)}{line(C1, D1)}
{line(dia1, dia2, 1)}
{txt(cx + 10, cy - 5, "O")}
{txt(A1[0] - 8, A1[1] - 6, "A", anc="end")}{txt(B1[0] + 8, B1[1] - 6, "B")}
{txt(C1[0] - 8, C1[1] + 16, "C", anc="end")}{txt(D1[0] + 8, D1[1] + 16, "D")}
{measured(*A1, *B1, -9, "24 cm", 12)}
{measured(*C1, *D1, 9, "24 cm", 12)}
{txt((dia1[0] + cx) / 2 - 6, (dia1[1] + cy) / 2 + 14, "30 cm", 12)}
</svg>'''

# ── q2: 외부점 A 의 두 접선(P·Q), B·C, BC 접점 D, PB=15·BA=17 ────────
cx, cy, r = 100, 118, 74
A2 = (330, 118)
dA = A2[0] - cx
al = math.degrees(math.acos(r / dA))
P2 = C(cx, cy, al, r)
Q2 = C(cx, cy, -al, r)
D2 = (cx + r, cy)
tB = (D2[0] - P2[0]) / (A2[0] - P2[0])
B2 = (P2[0] + tB * (A2[0] - P2[0]), P2[1] + tB * (A2[1] - P2[1]))
C2 = (B2[0], 2 * cy - B2[1])
S["q2"] = f'''<svg viewBox="0 0 360 240" xmlns="http://www.w3.org/2000/svg">
{circ(cx, cy, r)}{dot(cx, cy)}
{line(P2, A2)}{line(Q2, A2)}{line(B2, C2)}{line((cx, cy), A2, 1)}
{line((cx, cy), P2, 1)}{line((cx, cy), Q2, 1)}
{txt(cx - 10, cy - 6, "O", anc="end")}{txt(A2[0] + 8, A2[1] + 5, "A")}
{txt(P2[0] - 2, P2[1] - 10, "P")}{txt(Q2[0] - 2, Q2[1] + 20, "Q")}
{txt(B2[0] + 9, B2[1] - 11, "B")}{txt(C2[0] + 9, C2[1] + 20, "C")}
{txt(D2[0] - 8, D2[1] - 7, "D", anc="end")}{dot(*B2, 2)}{dot(*C2, 2)}{dot(*D2, 2)}
{txt((P2[0] + B2[0]) / 2 - 2, (P2[1] + B2[1]) / 2 - 10, "15 cm", 12)}
{txt((B2[0] + A2[0]) / 2 + 4, (B2[1] + A2[1]) / 2 - 10, "17 cm", 12)}
</svg>'''

# ── q3: 원 O 에 외접하는 등변사다리꼴 AD=5·BC=20 ─────────────────────
sc = 14
B3, C3 = (22, 192), (22 + 20 * sc / 14 * 14, 192)
C3 = (22 + 280, 192)
A3, D3 = (22 + 105, 52), (22 + 175, 52)
ox3, oy3, r3 = (B3[0] + C3[0]) / 2, 122, 70
S["q3"] = f'''<svg viewBox="0 0 325 245" xmlns="http://www.w3.org/2000/svg">
<polygon points="{pt(*A3)} {pt(*D3)} {pt(*C3)} {pt(*B3)}" fill="none" stroke="#000" stroke-width="2"/>
{circ(ox3, oy3, r3)}{dot(ox3, oy3)}
{txt(ox3 + 10, oy3 + 5, "O")}
{txt(A3[0] - 8, A3[1] - 8, "A", anc="end")}{txt(D3[0] + 8, D3[1] - 8, "D")}
{txt(B3[0] - 8, B3[1] + 14, "B", anc="end")}{txt(C3[0] + 8, C3[1] + 14, "C")}
{measured(*A3, *D3, -9, "5 cm", 12)}
{measured(*B3, *C3, 10, "20 cm", 12)}
</svg>'''

# ── q4: 지름 AB, P(54°)·R·Q, 현 PQ·PB·RQ·RB ─────────────────────────
cx, cy, r = 130, 122, 95
A4, B4 = (cx - r, cy), (cx + r, cy)
P4, R4, Q4 = C(cx, cy, 145, r), C(cx, cy, 55, r), C(cx, cy, 253, r)
S["q4"] = f'''<svg viewBox="0 0 260 250" xmlns="http://www.w3.org/2000/svg">
{circ(cx, cy, r)}{dot(cx, cy)}
{line(A4, B4, 1)}
{line(P4, Q4)}{line(P4, B4)}{line(R4, Q4)}{line(R4, B4)}
<path d="{angle_arc(*P4, Q4, B4, 20)}" fill="none" stroke="#000" stroke-width="1"/>
{txt(P4[0] + 26, P4[1] + 14, "54°", 12)}
{txt(cx - 3, cy - 8, "O")}
{txt(A4[0] - 9, A4[1] + 5, "A", anc="end")}{txt(B4[0] + 9, B4[1] + 5, "B")}
{txt(P4[0] - 6, P4[1] - 8, "P", anc="end")}{txt(R4[0] + 6, R4[1] - 6, "R")}
{txt(Q4[0] - 2, Q4[1] + 18, "Q")}
</svg>'''

# ── q5: 외접원·내심 I, ∠B=45°, AI=4·ID=11 ───────────────────────────
cx, cy, r = 132, 132, 100
A5, B5, C5 = C(cx, cy, 100, r), C(cx, cy, 205, r), C(cx, cy, 10, r)
D5 = C(cx, cy, 287.5, r)
I5 = (A5[0] + 4 / 15 * (D5[0] - A5[0]), A5[1] + 4 / 15 * (D5[1] - A5[1]))
S["q5"] = f'''<svg viewBox="0 0 265 265" xmlns="http://www.w3.org/2000/svg">
{circ(cx, cy, r)}
{line(A5, B5)}{line(A5, C5)}{line(B5, C5)}
{line(A5, D5)}{line(B5, D5)}{line(C5, D5)}
{dot(*I5, 2.2)}
<path d="{angle_arc(*B5, A5, C5, 22)}" fill="none" stroke="#000" stroke-width="1"/>
{txt(B5[0] + 30, B5[1] - 8, "45°", 12)}
{txt(A5[0], A5[1] - 9, "A")}{txt(B5[0] - 9, B5[1] + 10, "B", anc="end")}
{txt(C5[0] + 9, C5[1] + 4, "C")}{txt(D5[0] + 4, D5[1] + 16, "D")}
{txt(I5[0] + 9, I5[1] - 2, "I")}
{txt((A5[0] + I5[0]) / 2 - 7, (A5[1] + I5[1]) / 2 + 2, "4 cm", 11.5, anc="end")}
{txt((I5[0] + D5[0]) / 2 - 7, (I5[1] + D5[1]) / 2 + 6, "11 cm", 11.5, anc="end")}
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
S["q7"] = f'''<svg viewBox="0 0 310 255" xmlns="http://www.w3.org/2000/svg">
{circ(cx, cy, r)}{dot(cx, cy)}
{line(A7, P7)}{line(C7, P7)}{line(B7, A7)}{line(B7, C7)}
<path d="{angle_arc(*P7, A7, C7, 26)}" fill="none" stroke="#000" stroke-width="1"/>
{txt(P7[0] - 32, P7[1] + 4, "53°", 12, anc="end")}
{txt(cx - 2, cy + 18, "O")}
{txt(A7[0] - 2, A7[1] - 9, "A")}{txt(E7[0] + 5, E7[1] - 7, "E")}
{txt(D7[0] + 7, D7[1] + 8, "D")}{txt(C7[0] - 4, C7[1] + 17, "C")}
{txt(B7[0] - 9, B7[1] + 5, "B", anc="end")}{txt(P7[0] + 8, P7[1] + 5, "P")}
</svg>'''

# ── q8: 내접 사각형 ABCD + 접선 BT, ∠CBT=48° ────────────────────────
cx, cy, r = 150, 118, 90
B8 = (cx, cy + r)
A8, D8, C8 = C(cx, cy, 130, r), C(cx, cy, 60, r), C(cx, cy, 10, r)
T8 = (315, cy + r)
S["q8"] = f'''<svg viewBox="0 0 345 250" xmlns="http://www.w3.org/2000/svg">
{circ(cx, cy, r)}{dot(cx, cy)}
{line((35, B8[1]), (330, B8[1]))}
{line(A8, B8)}{line(B8, C8)}{line(C8, D8)}{line(D8, A8)}
{dot(*T8, 2.4)}
<path d="{angle_arc(*B8, C8, T8, 24)}" fill="none" stroke="#000" stroke-width="1"/>
{txt(B8[0] + 34, B8[1] - 10, "48°", 12)}
{txt(cx - 8, cy + 5, "O", anc="end")}
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
S["q9"] = f'''<svg viewBox="0 0 350 225" xmlns="http://www.w3.org/2000/svg">
{circ(cx, cy, r)}
{line(P9, tanA)}
{line(P9, C9)}{line(A9, B9)}{line(A9, C9)}{line(P9, Q9)}
<path d="{angle_arc(*A9, B9, C9, 20)}" fill="none" stroke="#000" stroke-width="1"/>
{txt(A9[0] + 14, A9[1] + 26, "56°", 12)}
{txt(P9[0] - 9, P9[1] + 5, "P", anc="end")}{txt(A9[0] - 2, A9[1] - 9, "A")}
{txt(Q9[0] + 8, Q9[1] - 2, "Q")}{dot(*Q9, 2)}
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

# ── q16: <보기> 산점도 7개(ㄱ~ㅅ) ────────────────────────────────────
import random
rnd = random.Random(7)
def mini(x0, y0, kind, lab):
    w, h = 86, 74
    el = [f'<line x1="{x0}" y1="{y0 + h}" x2="{x0 + w}" y2="{y0 + h}" stroke="#000" stroke-width="1"/>',
          f'<line x1="{x0}" y1="{y0 + h}" x2="{x0}" y2="{y0}" stroke="#000" stroke-width="1"/>',
          txt(x0 - 4, y0 + 12, lab + ".", 13, anc="end")]
    for i in range(9):
        t = (i + 0.5) / 9
        if kind == "strong+":
            px, py = t, t + rnd.uniform(-0.06, 0.06)
        elif kind == "weak+":
            px, py = t, t + rnd.uniform(-0.28, 0.28)
        elif kind == "strong-":
            px, py = t, 1 - t + rnd.uniform(-0.06, 0.06)
        elif kind == "weak-":
            px, py = t, 1 - t + rnd.uniform(-0.28, 0.28)
        elif kind == "none":
            px, py = rnd.uniform(0.08, 0.92), rnd.uniform(0.08, 0.92)
        elif kind == "flat":
            px, py = t, 0.5 + rnd.uniform(-0.07, 0.07)
        else:
            px, py = 0.5 + rnd.uniform(-0.07, 0.07), (i + 0.5) / 9
        px, py = min(max(px, 0.06), 0.94), min(max(py, 0.06), 0.94)
        el.append(dot(x0 + 6 + px * (w - 12), y0 + h - 6 - py * (h - 12), 2.2))
    return "".join(el)
kinds = ["strong+", "weak+", "strong-", "weak-", "none", "flat", "tall"]
labs = "ㄱㄴㄷㄹㅁㅂㅅ"
cells = []
for i in range(7):
    col, row = i % 4, i // 4
    cells.append(mini(38 + col * 118, 46 + row * 108, kinds[i], labs[i]))
S["q16"] = f'''<svg viewBox="0 0 510 280" xmlns="http://www.w3.org/2000/svg">
<rect x="4" y="4" width="502" height="272" fill="none" stroke="#000" stroke-width="1.4"/>
<line x1="4" y1="22" x2="205" y2="22" stroke="#fff" stroke-width="0"/>
{txt(255, 27, "&lt; 보 기 &gt;", 14)}
{"".join(cells)}
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
S["s1"] = f'''<svg viewBox="0 0 350 245" xmlns="http://www.w3.org/2000/svg">
<path d="{arc(O_1[0], O_1[1], r_1, 0, 180)}" fill="none" stroke="#000" stroke-width="2"/>
{line(B_1, C_1)}{dot(*O_1)}
{line(B_1, A_1)}{line(C_1, D_1)}{line(A_1, D_1)}
{dot(*P_1, 2.2)}
{rangle(B_1[0], B_1[1], 1, 0, 0, -1, 9)}
{rangle(C_1[0], C_1[1], -1, 0, 0, -1, 9)}
{txt(O_1[0], O_1[1] + 18, "O")}
{txt(A_1[0] - 9, A_1[1] + 2, "A", anc="end")}{txt(B_1[0] - 9, B_1[1] + 6, "B", anc="end")}
{txt(C_1[0] + 9, C_1[1] + 6, "C")}{txt(D_1[0] + 4, D_1[1] - 8, "D")}
{txt(P_1[0] - 6, P_1[1] - 9, "P", anc="end")}
{measured(*A_1, *D_1, -10, "10 cm", 12)}
{txt((C_1[0] + D_1[0]) / 2 + 9, (C_1[1] + D_1[1]) / 2 + 4, "8 cm", 12)}
</svg>'''

# ── s2: 두 할선 교점 P(60°), 호AB=9π·호CD=13π ───────────────────────
cx, cy, r = 138, 132, 96
P_2 = (300, 138)
E1, F1 = seci(P_2, 149, cx, cy, r)     # 위 할선: 가까운 B, 먼 A
B_2, A_2 = E1, F1
E2, F2 = seci(P_2, 209, cx, cy, r)
D_2, C_2 = E2, F2
S["s2"] = f'''<svg viewBox="0 0 345 265" xmlns="http://www.w3.org/2000/svg">
{circ(cx, cy, r)}
{line(A_2, P_2)}{line(C_2, P_2)}
<path d="{angle_arc(*P_2, A_2, C_2, 22)}" fill="none" stroke="#000" stroke-width="1"/>
{txt(P_2[0] - 26, P_2[1] - 8, "60°", 12, anc="end")}
{txt(A_2[0] - 2, A_2[1] - 9, "A")}{txt(B_2[0] + 6, B_2[1] - 8, "B")}
{txt(C_2[0] - 8, C_2[1] + 16, "C", anc="end")}{txt(D_2[0] + 8, D_2[1] + 14, "D")}
{txt(P_2[0] + 8, P_2[1] + 5, "P")}
<path d="{arc(cx, cy, r + 13, ray_angle(cx, cy, *A_2), ray_angle(cx, cy, *B_2))}" fill="none" stroke="#000" stroke-width="1" stroke-dasharray="3 3"/>
{txt((A_2[0] + B_2[0]) / 2 + 42, (A_2[1] + B_2[1]) / 2 - 32, "9π cm", 12.5)}
<path d="{arc(cx, cy, r + 13, ray_angle(cx, cy, *C_2), ray_angle(cx, cy, *D_2))}" fill="none" stroke="#000" stroke-width="1" stroke-dasharray="3 3"/>
{txt(cx + 10, cy + r + 26, "13π cm", 12.5)}
</svg>'''

if __name__ == "__main__":
    from core.figure_generator import _svg_to_png_bytes
    W = {"q1": 200, "q2": 265, "q3": 240, "q4": 205, "q5": 210, "q6": 235,
         "q7": 270, "q8": 255, "q9": 268, "q15": 245, "q16": 330, "s1": 262, "s2": 268}
    for k, svg in S.items():
        png = _svg_to_png_bytes(svg, width=W[k] * 2)
        if not png:
            print(k, "FAIL")
            continue
        open(os.path.join(OUT, f"{k}.png"), "wb").write(png)
        print(k, "ok")
