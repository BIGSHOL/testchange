# -*- coding: utf-8 -*-
"""왕선중3 25-2-기말 — 그림 15개 core.figure_svg 엔진 작도(정의값 기하)."""
import math
import os
import random
import sys

sys.path.insert(0, r"F:\시험지변환기")
sys.stdout.reconfigure(encoding="utf-8")
from core.figure_svg import (FONT, IT, angle_arc, arc, eq_tick, measured, pt,
                             rangle, ray_angle)

OUT = r"F:\tmp\figcrop\_ws2\_fig"
os.makedirs(OUT, exist_ok=True)
S = {}


def C(cx, cy, ang, r):
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
    ux, uy = math.cos(math.radians(ang_deg)), -math.sin(math.radians(ang_deg))
    fx, fy = P[0] - cx, P[1] - cy
    b = fx * ux + fy * uy
    d = math.sqrt(b * b - (fx * fx + fy * fy - r * r))
    return ((P[0] + (-b - d) * ux, P[1] + (-b - d) * uy),
            (P[0] + (-b + d) * ux, P[1] + (-b + d) * uy))


def isect(p1, p2, p3, p4):
    x1, y1 = p1; x2, y2 = p2; x3, y3 = p3; x4, y4 = p4
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / den
    py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / den
    return (px, py)


def tangent_isect(cx, cy, r, t1, t2):
    """두 접점 각도 t1·t2 의 접선 교점."""
    half = abs((t2 - t1 + 180) % 360 - 180) / 2.0
    mid = (t1 + ((t2 - t1 + 180) % 360 - 180) / 2.0)
    d = r / math.cos(math.radians(half))
    return C(cx, cy, mid, d)


# ── q1: 원 O, 반지름 10cm·수선 6cm·현 x cm ──────────────────────────
cx, cy, r = 122, 108, 90
chy = cy + 54
half = 72
L1, R1 = (cx - half, chy), (cx + half, chy)
S["q1"] = f'''<svg viewBox="0 0 250 220" xmlns="http://www.w3.org/2000/svg">
{circ(cx, cy, r)}{dot(cx, cy)}
{txt(cx + 6, cy - 8, "O")}
{line(L1, R1)}
{line((cx, cy), L1)}
{line((cx, cy), (cx, chy))}
{rangle(cx, chy, 1, 0, 0, -1, 9)}
{txt((cx + L1[0]) / 2 - 8, (cy + chy) / 2 - 4, "10 cm", 12, anc="end")}
{txt(cx + 7, (cy + chy) / 2 + 4, "6 cm", 12)}
{measured(*L1, *R1, 10, '<tspan font-style="italic">x</tspan> cm', 12)}
</svg>'''

# ── q2: 현 AB 가 반지름 OC 를 수직이등분 ─────────────────────────────
cx, cy, r = 120, 100, 80
C2 = (cx, cy + r)
my = cy + r / 2
hf = math.sqrt(r * r - (r / 2) ** 2)
A2, B2 = (cx - hf, my), (cx + hf, my)
S["q2"] = f'''<svg viewBox="0 0 245 210" xmlns="http://www.w3.org/2000/svg">
{circ(cx, cy, r)}{dot(cx, cy)}
{txt(cx + 3, cy - 8, "O")}
{line((cx, cy), C2)}{line(A2, B2)}
{rangle(cx, my, 1, 0, 0, 1, 8)}
{eq_tick((cx, cy), (cx, my), 5)}
{eq_tick((cx, my), C2, 5)}
{txt(A2[0] - 8, A2[1] + 6, "A", anc="end")}{txt(B2[0] + 8, B2[1] + 6, "B")}
{txt(C2[0], C2[1] + 18, "C")}
</svg>'''

# ── q3: 직사각형 ABCD, 세 변 접원 O, 접선 CE, ED=3·BC=6 ─────────────
u3 = 45
A3, D3 = (30, 42), (30 + 6 * u3, 42)
B3, C3 = (30, 42 + 4 * u3), (30 + 6 * u3, 42 + 4 * u3)
r3 = 2 * u3
o3 = (30 + r3, 42 + r3)
E3 = (D3[0] - 3 * u3, 42)
S["q3"] = f'''<svg viewBox="0 0 330 265" xmlns="http://www.w3.org/2000/svg">
<polygon points="{pt(*A3)} {pt(*D3)} {pt(*C3)} {pt(*B3)}" fill="none" stroke="#000" stroke-width="2"/>
{circ(*o3, r3)}{dot(*o3)}
{txt(o3[0] + 4, o3[1] + 16, "O")}
{line(C3, E3)}
{dot(*E3, 2.2)}
{txt(A3[0] - 8, A3[1] - 6, "A", anc="end")}{txt(D3[0] + 8, D3[1] - 6, "D")}
{txt(B3[0] - 8, B3[1] + 14, "B", anc="end")}{txt(C3[0] + 8, C3[1] + 14, "C")}
{txt(E3[0], E3[1] - 8, "E")}
{measured(*E3, *D3, -9, "3", 12)}
{measured(*B3, *C3, 10, "6", 12)}
</svg>'''

# ── q4: 원 O 에 외접하는 사각형 ABCD ─────────────────────────────────
cx, cy, r = 160, 125, 74
tA, tT, tR, tB = 163, 82, 351, 262      # 접점 각도(좌·상·우·하)
A4 = tangent_isect(cx, cy, r, tA, tT)
D4 = tangent_isect(cx, cy, r, tT, tR)
C4 = tangent_isect(cx, cy, r, tR, tB)
B4 = tangent_isect(cx, cy, r, tB, tA)
S["q4"] = f'''<svg viewBox="0 0 320 260" xmlns="http://www.w3.org/2000/svg">
<polygon points="{pt(*A4)} {pt(*D4)} {pt(*C4)} {pt(*B4)}" fill="none" stroke="#000" stroke-width="2"/>
{circ(cx, cy, r)}{dot(cx, cy)}
{txt(cx + 4, cy + 16, "O")}
{txt(A4[0] - 6, A4[1] - 6, "A", anc="end")}{txt(D4[0] + 6, D4[1] - 6, "D")}
{txt(B4[0] - 6, B4[1] + 14, "B", anc="end")}{txt(C4[0] + 6, C4[1] + 14, "C")}
</svg>'''

# ── q5: 지름 AD, ∠BAC=20°·∠ADE=60°, 호DE=5·호BC=x ──────────────────
cx, cy, r = 152, 122, 94
A5 = C(cx, cy, 95, r)
D5 = C(cx, cy, 275, r)
B5, C5_ = C(cx, cy, 180, r), C(cx, cy, 220, r)
E5 = C(cx, cy, 335, r)
S["q5"] = f'''<svg viewBox="0 0 295 255" xmlns="http://www.w3.org/2000/svg">
{circ(cx, cy, r)}{dot(cx, cy)}
{txt(cx + 8, cy - 4, "O")}
{line(A5, D5)}{line(A5, B5)}{line(A5, C5_)}{line(D5, E5)}{line(A5, E5)}
{rangle(E5[0], E5[1], -0.42, -0.91, -0.87, 0.42, 9)}
<path d="{angle_arc(*A5, B5, C5_, 30)}" fill="none" stroke="#000" stroke-width="1"/>
{txt(A5[0] - 34, A5[1] + 26, "20°", 11.5)}
<path d="{angle_arc(*D5, A5, E5, 24)}" fill="none" stroke="#000" stroke-width="1"/>
{txt(D5[0] + 20, D5[1] - 16, "60°", 11.5)}
<path d="{arc(cx, cy, r + 12, 180, 220)}" fill="none" stroke="#000" stroke-width="1" stroke-dasharray="3 3"/>
{txt(C(cx, cy, 200, r + 26)[0], C(cx, cy, 200, r + 26)[1], '<tspan font-style="italic">x</tspan> cm', 11.5, anc="end")}
<path d="{arc(cx, cy, r + 12, 275, 335)}" fill="none" stroke="#000" stroke-width="1" stroke-dasharray="3 3"/>
{txt(C(cx, cy, 305, r + 27)[0] + 4, C(cx, cy, 305, r + 27)[1] + 6, "5 cm", 11.5)}
{txt(A5[0], A5[1] - 9, "A")}{txt(B5[0] - 9, B5[1] + 5, "B", anc="end")}
{txt(C5_[0] - 8, C5_[1] + 10, "C", anc="end")}{txt(D5[0] - 2, D5[1] + 18, "D")}
{txt(E5[0] + 9, E5[1] + 4, "E")}
</svg>'''

# ── q6: 접선 AT, 호AB=호BP, ∠BAT=65° ────────────────────────────────
cx, cy, r = 150, 108, 85
A6 = (cx, cy + r)
B6 = C(cx, cy, 270 + 130, r)
P6 = C(cx, cy, 270 + 260, r)
T6 = (290, cy + r)
S["q6"] = f'''<svg viewBox="0 0 315 235" xmlns="http://www.w3.org/2000/svg">
{circ(cx, cy, r)}{dot(cx, cy)}
{txt(cx + 12, cy - 6, "O")}
{line((35, A6[1]), (300, A6[1]))}
{line(A6, B6)}{line(B6, P6)}{line(A6, P6)}
{dot(*T6, 2.4)}
<path d="{angle_arc(*A6, B6, T6, 24)}" fill="none" stroke="#000" stroke-width="1"/>
{txt(A6[0] + 34, A6[1] - 12, "65°", 12)}
{txt(P6[0] - 9, P6[1] + 2, "P", anc="end")}{txt(B6[0] + 8, B6[1] - 4, "B")}
{txt(A6[0] - 2, A6[1] + 20, "A")}{txt(T6[0], T6[1] + 20, "T")}
</svg>'''

# ── q7: 지름 DA 연장 P, ∠P=20°, BO=BP, 호CD=30 ─────────────────────
cx, cy, r = 125, 115, 78
D7, A7 = (cx - r, cy), (cx + r, cy)
B7 = C(cx, cy, -20, r)
P7 = (B7[0] + (B7[1] - cy) / math.tan(math.radians(20)), cy)
C7 = seci(P7, 200, cx, cy, r)[1]
S["q7"] = f'''<svg viewBox="0 0 330 225" xmlns="http://www.w3.org/2000/svg">
{circ(cx, cy, r)}{dot(cx, cy)}
{txt(cx - 2, cy - 8, "O")}
{line(D7, P7)}
{line(P7, C7)}{line(D7, C7)}
<path d="{angle_arc(*P7, C7, D7, 26)}" fill="none" stroke="#000" stroke-width="1"/>
{txt(P7[0] - 32, P7[1] - 7, "20°", 11.5, anc="end")}
<path d="{arc(cx, cy, r + 11, ray_angle(cx, cy, *C7) % 360, 180)}" fill="none" stroke="#000" stroke-width="1" stroke-dasharray="3 3"/>
{txt(C(cx, cy, 212, r + 26)[0], C(cx, cy, 212, r + 26)[1], "30", 12)}
{txt(D7[0] - 8, D7[1] + 5, "D", anc="end")}{txt(A7[0] + 2, A7[1] - 8, "A")}
{txt(P7[0] + 9, P7[1] + 5, "P")}{txt(B7[0] + 4, B7[1] + 16, "B")}
{txt(C7[0] - 6, C7[1] + 16, "C")}
</svg>'''

# ── q8: 호AB=1/9(40°)·호CD=1/3(120°), P=AC∩BD, ∠DPC ────────────────
cx, cy, r = 122, 120, 90
D8, C8 = C(cx, cy, 110, r), C(cx, cy, -10, r)
A8, B8 = C(cx, cy, 190, r), C(cx, cy, 230, r)
P8 = isect(A8, C8, D8, B8)
S["q8"] = f'''<svg viewBox="0 0 245 250" xmlns="http://www.w3.org/2000/svg">
{circ(cx, cy, r)}{dot(cx, cy)}
{txt(cx - 4, cy - 8, "O")}
{line(A8, C8)}{line(D8, B8)}
<path d="{angle_arc(*P8, D8, C8, 17)}" fill="none" stroke="#000" stroke-width="1"/>
{dot(*P8, 2)}
{txt(D8[0] + 2, D8[1] - 8, "D")}{txt(A8[0] - 8, A8[1] + 4, "A", anc="end")}
{txt(B8[0] - 4, B8[1] + 16, "B")}{txt(C8[0] + 9, C8[1] + 4, "C")}
{txt(P8[0] - 4, P8[1] + 18, "P")}
</svg>'''

# ── q9: 외접원, 호BC 중점 M, N=AM∩BC, 45°·60°·AN=4 ─────────────────
cx, cy, r = 130, 122, 95
A9, C9 = C(cx, cy, 100, r), C(cx, cy, 10, r)
B9 = C(cx, cy, 250, r)
M9 = C(cx, cy, 310, r)
N9 = isect(A9, M9, B9, C9)
S["q9"] = f'''<svg viewBox="0 0 265 260" xmlns="http://www.w3.org/2000/svg">
{circ(cx, cy, r)}
{line(A9, B9)}{line(A9, C9)}{line(B9, C9)}
{line(A9, M9)}{line(B9, M9)}{line(C9, M9)}
{dot(*N9, 2)}
<path d="{angle_arc(*A9, B9, C9, 22)}" fill="none" stroke="#000" stroke-width="1"/>
{txt(A9[0] - 4, A9[1] + 38, "60°", 11.5)}
<path d="{angle_arc(*B9, A9, C9, 22)}" fill="none" stroke="#000" stroke-width="1"/>
{txt(B9[0] + 28, B9[1] - 10, "45°", 11.5)}
{txt((A9[0] + N9[0]) / 2 + 8, (A9[1] + N9[1]) / 2, "4", 12.5)}
{txt(A9[0], A9[1] - 9, "A")}{txt(B9[0] - 9, B9[1] + 10, "B", anc="end")}
{txt(C9[0] + 9, C9[1] + 4, "C")}{txt(M9[0] + 4, M9[1] + 16, "M")}
{txt(N9[0] - 4, N9[1] + 17, "N")}
</svg>'''

# ── q10: 접선 ST(S 접점)·현 AC∥ST·지름 AB, P=AB∩CS, 20°·x° ─────────
cx, cy, r = 135, 118, 85
S10 = (cx, cy + r)
A10, C10 = C(cx, cy, 128, r), C(cx, cy, 52, r)
B10 = C(cx, cy, -52, r)
T10 = (285, cy + r)
P10 = isect(A10, B10, C10, S10)
S["q10"] = f'''<svg viewBox="0 0 310 245" xmlns="http://www.w3.org/2000/svg">
{circ(cx, cy, r)}{dot(cx, cy)}
{txt(cx - 10, cy - 6, "O", anc="end")}
{line((30, S10[1]), (295, S10[1]))}
{line(A10, C10)}{line(A10, B10)}{line(A10, S10)}{line(C10, S10)}{line(S10, B10)}
{dot(*P10, 2)}{dot(*T10, 2.4)}
<path d="{angle_arc(*S10, B10, T10, 22)}" fill="none" stroke="#000" stroke-width="1"/>
{txt(S10[0] + 30, S10[1] - 10, "20°", 11.5)}
{txt(P10[0] + 10, P10[1] + 2, '<tspan font-style="italic">x</tspan>°', 12)}
<path d="M {(A10[0] + C10[0]) / 2 - 5:.1f} {A10[1] - 5:.1f} L {(A10[0] + C10[0]) / 2 + 5:.1f} {A10[1]:.1f} L {(A10[0] + C10[0]) / 2 - 5:.1f} {A10[1] + 5:.1f}" fill="none" stroke="#000" stroke-width="1"/>
<path d="M {cx - 40:.1f} {S10[1] - 5:.1f} L {cx - 30:.1f} {S10[1]:.1f} L {cx - 40:.1f} {S10[1] + 5:.1f}" fill="none" stroke="#000" stroke-width="1"/>
{txt(A10[0] - 8, A10[1] - 4, "A", anc="end")}{txt(C10[0] + 8, C10[1] - 4, "C")}
{txt(B10[0] + 9, B10[1] + 6, "B")}{txt(S10[0] - 4, S10[1] + 20, "S")}
{txt(T10[0], T10[1] + 20, "T")}{txt(P10[0] - 2, P10[1] - 8, "P")}
</svg>'''

# ── q11: 두 접선(C·D 접점)·P 80°, 오각 EABCD, x°·y°·40°·70° ─────────
cx, cy, r = 150, 112, 88
C11 = (cx, cy + r)
D11 = C(cx, cy, 10, r)
P11 = tangent_isect(cx, cy, r, 270, 10)
E11 = C(cx, cy, 150, r)
A11 = C(cx, cy, 75, r)
B11 = C(cx, cy, 190, r)
F11 = isect(E11, D11, A11, B11)
_td = (math.sin(math.radians(10)), math.cos(math.radians(10)))
T11 = (D11[0] + 40 * _td[0], D11[1] - 40 * _td[1])
S11p = (40, C11[1])
S["q11"] = f'''<svg viewBox="0 0 330 250" xmlns="http://www.w3.org/2000/svg">
{circ(cx, cy, r)}{dot(cx, cy)}
{txt(cx - 2, cy + 18, "O")}
{line(S11p, (P11[0] + 8, C11[1]))}
{line(T11, P11)}
{line(E11, B11)}{line(E11, C11)}{line(E11, D11)}
{line(A11, B11)}{line(A11, D11)}{line(B11, C11)}{line(C11, D11)}{line(B11, D11)}
{dot(*F11, 2)}{dot(*S11p, 2.2)}
<path d="{angle_arc(*B11, E11, A11, 20)}" fill="none" stroke="#000" stroke-width="1"/>
{txt(B11[0] + 24, B11[1] - 6, "40°", 10.5)}
<path d="{angle_arc(*D11, E11, C11, 20)}" fill="none" stroke="#000" stroke-width="1"/>
{txt(D11[0] - 24, D11[1] + 12, "70°", 10.5, anc="end")}
<path d="{angle_arc(*P11, C11, D11, 22)}" fill="none" stroke="#000" stroke-width="1"/>
{txt(P11[0] - 26, P11[1] - 8, "80°", 10.5, anc="end")}
<path d="{angle_arc(*E11, C11, D11, 18)}" fill="none" stroke="#000" stroke-width="1"/>
{txt(E11[0] + 22, E11[1] + 12, '<tspan font-style="italic">x</tspan>°', 11)}
{txt(F11[0] + 10, F11[1] - 4, '<tspan font-style="italic">y</tspan>°', 11)}
{txt(E11[0] - 8, E11[1] - 6, "E", anc="end")}{txt(A11[0] + 4, A11[1] - 8, "A")}
{txt(T11[0] + 6, T11[1], "T")}{txt(B11[0] - 9, B11[1] + 5, "B", anc="end")}
{txt(C11[0] - 2, C11[1] + 19, "C")}{txt(D11[0] + 9, D11[1] + 2, "D")}
{txt(S11p[0], S11p[1] + 19, "S")}{txt(P11[0] + 8, P11[1] + 12, "P")}
</svg>'''

# ── q16: 음의 상관 산점도(예시) ──────────────────────────────────────
rnd = random.Random(16)
pts16 = []
for i in range(30):
    t = rnd.uniform(0.05, 0.95)
    y = 1 - t + rnd.uniform(-0.18, 0.18)
    pts16.append((t, min(max(y, 0.05), 0.95)))
d16 = "".join(dot(40 + x * 170, 160 - y * 130, 2.2) for x, y in pts16)
S["q16"] = f'''<svg viewBox="0 0 230 190" xmlns="http://www.w3.org/2000/svg">
<line x1="35" y1="165" x2="220" y2="165" stroke="#000" stroke-width="1.2"/>
<path d="M 214 161 L 222 165 L 214 169 Z" fill="#000"/>
<line x1="35" y1="165" x2="35" y2="20" stroke="#000" stroke-width="1.2"/>
<path d="M 31 26 L 35 18 L 39 26 Z" fill="#000"/>
{d16}
{txt(28, 180, "O", 13, anc="end")}
{txt(224, 181, "x", 13, it=True)}
{txt(26, 26, "y", 13, anc="end", it=True)}
</svg>'''

# ── q17: 산점도 높이뛰기·멀리뛰기(25명) ─────────────────────────────
p17 = [(9, 10), (10, 10), (6, 9), (8, 9), (9, 9), (10, 9),
       (6, 8), (7, 8), (8, 8), (9, 8), (10, 8),
       (6, 7), (7, 7), (8, 7), (9, 7), (10, 7),
       (5, 6), (6, 6), (7, 6), (8, 6), (9, 6),
       (5, 5), (6, 5), (7, 5), (10, 5)]
ox, oy, s17 = 74, 232, 27
g17 = "".join(f'<line x1="{ox + (i - 4) * s17}" y1="{oy}" x2="{ox + (i - 4) * s17}" y2="{oy - 6 * s17}" stroke="#bbb" stroke-width="0.7"/>' for i in range(4, 11)) + \
      "".join(f'<line x1="{ox}" y1="{oy - (j - 4) * s17}" x2="{ox + 6 * s17}" y2="{oy - (j - 4) * s17}" stroke="#bbb" stroke-width="0.7"/>' for j in range(4, 11))
d17 = "".join(dot(ox + (x - 4) * s17, oy - (y - 4) * s17, 3.4) for x, y in p17)
xt17 = "".join(txt(ox + (i - 4) * s17, oy + 17, str(i), 11.5) for i in range(5, 11))
yt17 = "".join(txt(ox - 7, oy - (j - 4) * s17 + 4, str(j), 11.5, anc="end") for j in range(5, 11))
ylab17 = "".join(f'<tspan x="24" dy="{"0" if i == 0 else "13"}">{ch}</tspan>' for i, ch in enumerate("멀리뛰기"))
S["q17"] = f'''<svg viewBox="0 0 300 280" xmlns="http://www.w3.org/2000/svg">
{g17}
<line x1="{ox}" y1="{oy}" x2="{ox + 6 * s17 + 12}" y2="{oy}" stroke="#000" stroke-width="1.3"/>
<path d="M {ox + 6 * s17 + 8} {oy - 4} L {ox + 6 * s17 + 16} {oy} L {ox + 6 * s17 + 8} {oy + 4} Z" fill="#000"/>
<line x1="{ox}" y1="{oy}" x2="{ox}" y2="{oy - 6 * s17 - 12}" stroke="#000" stroke-width="1.3"/>
<path d="M {ox - 4} {oy - 6 * s17 - 8} L {ox} {oy - 6 * s17 - 16} L {ox + 4} {oy - 6 * s17 - 8} Z" fill="#000"/>
{d17}{xt17}{yt17}
<path d="M {ox - 14} {oy + 8} q 5 -5 0 -10 q -5 -5 0 -10" fill="none" stroke="#000" stroke-width="1"/>
{txt(ox - 20, oy + 18, "O", 13, anc="end")}
<text x="24" y="62" font-size="11.5" {FONT}>{ylab17}<tspan x="24" dy="13">(점)</tspan></text>
{txt(ox + 3 * s17, oy + 38, "높이뛰기(점)", 11.5)}
{txt(ox + 6 * s17 + 22, oy + 17, "x", 12, it=True)}
{txt(ox - 12, oy - 6 * s17 - 8, "y", 12, anc="end", it=True)}
</svg>'''

# ── q18: 산점도 수학·과학(20명) + ──────────────────────────────────
p18 = [(80, 100), (90, 100), (70, 90), (80, 90), (90, 90), (100, 90),
       (60, 80), (70, 80), (80, 80), (90, 80),
       (60, 70), (70, 70), (80, 70), (90, 70),
       (50, 60), (60, 60), (70, 60), (80, 60), (50, 50), (70, 50)]
ox, oy, s18 = 84, 232, 25
g18 = "".join(f'<line x1="{ox + i * s18}" y1="{oy}" x2="{ox + i * s18}" y2="{oy - 5 * s18}" stroke="#bbb" stroke-width="0.7"/>' for i in range(0, 6)) + \
      "".join(f'<line x1="{ox}" y1="{oy - j * s18}" x2="{ox + 5 * s18}" y2="{oy - j * s18}" stroke="#bbb" stroke-width="0.7"/>' for j in range(0, 6))
d18 = "".join(dot(ox + (x - 50) / 10 * s18, oy - (y - 50) / 10 * s18, 3.4) for x, y in p18)
xt18 = "".join(txt(ox + i * s18, oy + 17, str(50 + i * 10), 11) for i in range(0, 6))
yt18 = "".join(txt(ox - 7, oy - j * s18 + 4, str(50 + j * 10), 11, anc="end") for j in range(0, 6))
S["q18"] = f'''<svg viewBox="0 0 300 285" xmlns="http://www.w3.org/2000/svg">
{g18}
<line x1="{ox - 14}" y1="{oy + 14}" x2="{ox + 5 * s18 + 14}" y2="{oy + 14}" stroke="#000" stroke-width="1.3"/>
<path d="M {ox + 5 * s18 + 10} {oy + 10} L {ox + 5 * s18 + 18} {oy + 14} L {ox + 5 * s18 + 10} {oy + 18} Z" fill="#000"/>
<line x1="{ox - 14}" y1="{oy + 14}" x2="{ox - 14}" y2="{oy - 5 * s18 - 12}" stroke="#000" stroke-width="1.3"/>
<path d="M {ox - 18} {oy - 5 * s18 - 8} L {ox - 14} {oy - 5 * s18 - 16} L {ox - 10} {oy - 5 * s18 - 8} Z" fill="#000"/>
{d18}{xt18}{yt18}
{txt(ox - 20, oy + 30, "O", 13, anc="end")}
<text x="30" y="60" font-size="11.5" {FONT}><tspan x="30" dy="0">과</tspan><tspan x="30" dy="13">학</tspan><tspan x="30" dy="13">(점)</tspan></text>
{txt(ox + 2.5 * s18, oy + 32, "수학(점)", 11.5)}
{txt(ox + 5 * s18 + 24, oy + 31, "x", 12, it=True)}
{txt(ox - 24, oy - 5 * s18 - 8, "y", 12, anc="end", it=True)}
</svg>'''

# ── s1(서답형1): P 의 두 접선 PA=PB 증명 그림 ───────────────────────
cx, cy, r = 225, 118, 72
P19 = (45, 118)
al = math.degrees(math.acos(r / (cx - P19[0])))
A19 = C(cx, cy, 180 - al, r)
B19 = C(cx, cy, 180 + al, r)
S["s1"] = f'''<svg viewBox="0 0 320 240" xmlns="http://www.w3.org/2000/svg">
{circ(cx, cy, r)}{dot(cx, cy)}
{txt(cx + 10, cy + 4, "O")}
{line(P19, A19)}{line(P19, B19)}{line(P19, (cx, cy), 1)}
{line((cx, cy), A19, 1)}{line((cx, cy), B19, 1)}
{eq_tick(P19, A19, 6)}
{eq_tick(P19, B19, 6)}
{txt(P19[0] - 9, P19[1] + 5, "P", anc="end")}
{txt(A19[0] + 2, A19[1] - 9, "A")}{txt(B19[0] + 2, B19[1] + 19, "B")}
</svg>'''

if __name__ == "__main__":
    from core.figure_generator import _svg_to_png_bytes
    W = {"q1": 195, "q2": 190, "q3": 240, "q4": 235, "q5": 215, "q6": 240,
         "q7": 255, "q8": 195, "q9": 208, "q10": 240, "q11": 262, "q16": 175,
         "q17": 235, "q18": 235, "s1": 240}
    for k, svg in S.items():
        png = _svg_to_png_bytes(svg, width=W[k] * 2)
        if not png:
            print(k, "FAIL")
            continue
        open(os.path.join(OUT, f"{k}.png"), "wb").write(png)
        print(k, "ok")
