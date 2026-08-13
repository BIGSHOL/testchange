# -*- coding: utf-8 -*-
"""왕선중 q5·q11 — 새 엔진 기능 적용판(접점 기준 접선·좁은 각 지시선·통일 글자 크기).

원본 스크립트(다른 세션 소유)는 건드리지 않고 여기서 재작도해 비교만 한다.
"""
from __future__ import annotations

import math
import os
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.figure_quality import assess_svg
from core.figure_generator import _svg_to_png_bytes
from core.figure_svg import (SVGTextRun, angle_arc, angle_label, angle_label_leader, angle_mark,
                             arc_measured, circ, circle_pt as C, dot, halo_angle,
                             isect, line, lint_svg, rangle, tangent_beyond,
                             tangent_isect, txt, type_scale, verify_figure)

OUT = os.environ.get("FIG_DEMO_OUT",
                     str(Path(tempfile.gettempdir()) / "figure_demos"))
os.makedirs(OUT, exist_ok=True)
S = {}

# ── q5 ────────────────────────────────────────────────────────────────────
VB5 = (295, 255)
FS5 = type_scale(*VB5)                      # 점 이름·수치 공용(=18.4)
cx, cy, r = 152, 122, 94
A5, D5 = C(cx, cy, 95, r), C(cx, cy, 275, r)
B5, C5_ = C(cx, cy, 180, r), C(cx, cy, 220, r)
E5 = C(cx, cy, 335, r)
verify_figure("q5", angles=[(20, A5, B5, C5_), (60, D5, A5, E5)],
              arcs=[(40, cx, cy, r, 180, 220), (60, cx, cy, r, 275, 335)],
              on_circle=[(p, cx, cy, r) for p in (A5, B5, C5_, D5, E5)])
verify_figure("q5-지름", lengths=[(2, A5, D5), (1, (cx, cy), A5)])
SEG5 = [(A5, D5), (A5, B5), (A5, C5_), (D5, E5), (A5, E5)]
CIR5 = [(cx, cy, r)]
KEEP5 = [(A5[0], A5[1], 20), (B5[0], B5[1], 20), (C5_[0], C5_[1], 20),
         (D5[0], D5[1], 20), (E5[0], E5[1], 20), (cx, cy, 20)]
S["q5"] = f'''<svg viewBox="0 0 {VB5[0]} {VB5[1]}" xmlns="http://www.w3.org/2000/svg">
<rect width="{VB5[0]}" height="{VB5[1]}" fill="#ffffff"/>
{circ(cx, cy, r)}{dot(cx, cy)}
{txt(cx + 9, cy - 5, "O", FS5)}
{line(A5, D5)}{line(A5, B5)}{line(A5, C5_)}{line(D5, E5)}{line(A5, E5)}
{rangle(E5[0], E5[1], (A5[0]-E5[0])/94, (A5[1]-E5[1])/94, (D5[0]-E5[0])/108, (D5[1]-E5[1])/108, 9)}
{angle_mark(*A5, B5, C5_, r=30, dash=False, w=1)}
{angle_label(*A5, B5, C5_, "20°", fs=FS5, d=30, arc_r=30, out=62, avoid=SEG5, circles=CIR5, keep_out=KEEP5)}
<path d="{angle_arc(*D5, A5, E5, 24)}" fill="none" stroke="#000" stroke-width="1"/>
{txt(D5[0] + 20, D5[1] - 30, "60°", FS5)}
{arc_measured(cx, cy, r, 180, 220, runs=[SVGTextRun("x", italic=True), SVGTextRun(" cm")], fs=FS5)}
{arc_measured(cx, cy, r, 275, 335, txt="5 cm", fs=FS5)}
{txt(A5[0], A5[1] - 10, "A", FS5)}{txt(B5[0] - 10, B5[1] + 6, "B", FS5, anc="end")}
{txt(C5_[0] - 9, C5_[1] + 12, "C", FS5, anc="end")}{txt(D5[0] - 7, D5[1] + 20, "D", FS5, anc="end")}
{txt(E5[0] + 11, E5[1] + 5, "E", FS5)}
</svg>'''

# ── q11 ───────────────────────────────────────────────────────────────────
VB11 = (330, 250)
FS11 = type_scale(*VB11)                    # =18.0
cx, cy, r = 150, 112, 88
C11 = (cx, cy + r)
D11 = C(cx, cy, 10, r)
P11 = tangent_isect(cx, cy, r, 270, 10)
E11, A11, B11 = C(cx, cy, 130, r), C(cx, cy, 50, r), C(cx, cy, 190, r)
F11 = isect(E11, D11, A11, B11)
T11 = tangent_beyond(cx, cy, r, 10, P11, 40)      # ⭐ 접점 기준 — 부호 실수 불가
S11p = (40, C11[1])
verify_figure("q11", angles=[(90, A11, B11, D11), (40, B11, E11, A11),
                             (80, P11, C11, D11), (70, D11, E11, C11)],
              tangents=[(T11, P11, cx, cy, r), (S11p, P11, cx, cy, r)],
              on_line=[(D11, T11, P11), (C11, S11p, P11), (F11, E11, D11)],
              on_circle=[(p, cx, cy, r) for p in (A11, B11, C11, D11, E11)])
SEG11 = [(S11p, (P11[0] + 8, C11[1])), (T11, P11), (E11, B11), (E11, C11), (E11, D11),
         (A11, B11), (A11, D11), (B11, C11), (C11, D11), (B11, D11)]
CIR11 = [(cx, cy, r)]
KEEP11 = [(F11[0], F11[1], 22), (E11[0], E11[1], 20),
          (A11[0], A11[1], 20), (D11[0], D11[1], 24), (C11[0], C11[1], 22),
          (B11[0], B11[1], 20), (P11[0], P11[1], 22), (cx, cy, 20)]
S["q11"] = f'''<svg viewBox="0 0 {VB11[0]} {VB11[1]}" xmlns="http://www.w3.org/2000/svg">
<rect width="{VB11[0]}" height="{VB11[1]}" fill="#ffffff"/>
{circ(cx, cy, r)}{dot(cx, cy)}
{txt(cx - 2, cy + 20, "O", FS11)}
{line(S11p, (P11[0] + 8, C11[1]))}
{line(T11, P11)}
{line(E11, B11)}{line(E11, C11)}{line(E11, D11)}
{line(A11, B11)}{line(A11, D11)}{line(B11, C11)}{line(C11, D11)}{line(B11, D11)}
{dot(*F11, 2)}{dot(*S11p, 2.2)}
{angle_mark(*B11, E11, A11, r=20, dash=False)}
{angle_label(*B11, E11, A11, "40°", fs=FS11, d=30, arc_r=20, out=52, avoid=SEG11, circles=CIR11, keep_out=KEEP11)}
{angle_mark(*D11, E11, C11, r=20, dash=False)}
{angle_label(*D11, E11, C11, "70°", fs=FS11, d=30, arc_r=20, out=52, avoid=SEG11, circles=CIR11, keep_out=KEEP11)}
{angle_mark(*P11, C11, D11, r=22, dash=False)}
{angle_label(*P11, C11, D11, "80°", fs=FS11, d=30, arc_r=22, out=52, avoid=SEG11, circles=CIR11, keep_out=KEEP11)}
{angle_mark(*E11, C11, D11, r=18, dash=False)}
{angle_label(*E11, C11, D11, runs=[SVGTextRun("x", italic=True), SVGTextRun("°")],
                    fs=FS11, arc_r=18, out=54, side=-1, avoid=SEG11, circles=CIR11, keep_out=KEEP11)}
{angle_mark(*F11, A11, D11, r=15, dash=False)}
{angle_label(*F11, A11, D11, runs=[SVGTextRun("y", italic=True), SVGTextRun("°")],
                    fs=FS11, arc_r=15, out=50, side=1, avoid=SEG11, circles=CIR11, keep_out=KEEP11)}
{txt(E11[0] - 9, E11[1] - 7, "E", FS11, anc="end")}{txt(A11[0] + 5, A11[1] - 9, "A", FS11)}
{txt(T11[0] + 8, T11[1], "T", FS11)}{txt(B11[0] - 10, B11[1] + 6, "B", FS11, anc="end")}
{txt(C11[0] - 2, C11[1] + 22, "C", FS11)}{txt(D11[0] + 22, D11[1] + 2, "D", FS11)}
{txt(S11p[0], S11p[1] + 22, "S", FS11)}{txt(P11[0] + 10, P11[1] + 14, "P", FS11)}
{txt(F11[0] - 10, F11[1] - 8, "F", FS11, anc="end")}
</svg>'''

if __name__ == "__main__":
    W = {"q5": 215 * 3, "q11": 262 * 3}
    print(f"글자 크기: q5={FS5}  q11={FS11}  (종전 점이름 15 / 각도 10.5~12)")
    for k, svg in S.items():
        a, issues = assess_svg(svg), lint_svg(svg)
        open(os.path.join(OUT, f"fixed_{k}.png"), "wb").write(_svg_to_png_bytes(svg, width=W[k]))
        print(f"  {k:4s} gate={'PASS' if a.accepted else 'FAIL ' + str(a.issues)}"
              f"  lint={issues or 'CLEAN'}")
