# -*- coding: utf-8 -*-
"""고난도 공간도형 2종 — 업로드 레퍼런스 수준을 SVG 엔진으로 낼 수 있는지 실증.

A) 구 + 두 평면(y=4 · y+√3z+8=0) 으로의 정사영 벡터
B) 두 평면 α·β 가 만나는 곳의 원뿔곡선 C₁·C₂ (가려진 부분 점선)
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
from core.figure_solid import (Camera, Plane, add, circle3, cross, dot, foot,
                               equation_text, plane_from_equation, plane_intersection,
                               project_points, scale as vscale,
                               split_by_depth, sub, unit, verify_solid)
from core.figure_svg import (circ, curve_path, shaded_sphere, dot as pdot, leader, line, lint_svg,
                             point_labels, rangle_at, txt, type_scale,
                             unverified)

OUT = os.environ.get("FIG_DEMO_OUT",
                     str(Path(tempfile.gettempdir()) / "figure_demos"))
os.makedirs(OUT, exist_ok=True)
S = {}


def poly(pts, w=1.3, dash=None):
    return curve_path(list(pts) + [pts[0]], w=w, dash=dash)


def quad(plane: Plane, u, v, hu, hv):
    """평면 위 평행사변형 네 꼭짓점 — u·v 는 평면 안 두 방향."""
    o = plane.point
    return [add(o, add(vscale(u, su * hu), vscale(v, sv * hv)))
            for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))]


# ═══════════ A) 구와 두 평면으로의 정사영 ═══════════
VBA = (520, 440)
FSA = type_scale(*VBA)
CAM = Camera(elev=20, azim=55, scale=44, origin=(250, 196))
R = 1.0
EQ1 = (0.0, 1.0, 0.0, -4.0)                       # y = 4
EQ2 = (0.0, 1.0, math.sqrt(3.0), 8.0)             # y + √3 z + 8 = 0
PL1, PL2 = plane_from_equation(*EQ1), plane_from_equation(*EQ2)
_n2 = PL2.normal

P3 = (0.0, 0.0, 0.0)                       # 구의 중심(레퍼런스)
Q3 = vscale(unit((-0.30, 0.42, 0.86)), R)  # 구면 위(화면 우상단)
P1, Q1 = foot(P3, PL1), foot(Q3, PL1)
P2, Q2 = foot(P3, PL2), foot(Q3, PL2)

QUAD1 = quad(PL1, (1, 0, 0), (0, 0, 1), 2.0, 1.9)
QUAD2 = quad(PL2, (1, 0, 0), unit(cross(_n2, (1, 0, 0))), 2.0, 1.8)
verify_solid("sphere-proj",
             feet=[(P1, P3, PL1), (Q1, Q3, PL1), (P2, P3, PL2), (Q2, Q3, PL2)],
             on_plane=[(P1, PL1), (Q1, PL1), (P2, PL2), (Q2, PL2)],
             lengths=[(R, (0, 0, 0), Q3)],                        # Q 는 구면 위
             areas=[(None, QUAD1, PL1), (None, QUAD2, PL2)],
             equations=[(EQ1, PL1), (EQ2, PL2)],   # 라벨 ↔ 평면 일치
             view=CAM)                                            # 납작해지면 예외

q1, q2 = CAM.many(QUAD1), CAM.many(QUAD2)
eqf, eqb = split_by_depth(circle3((0, 0, 0), R, (0, 0, 1)), CAM)   # 적도
mrf, mrb = split_by_depth(circle3((0, 0, 0), R, (1, 0.35, 0)), CAM)  # 경선

body = [poly(q2), poly(q1)]
body.append(shaded_sphere(*CAM((0, 0, 0)), R * CAM.scale, w=1.6))
for seg in eqb + mrb:
    body.append(curve_path(CAM.many(seg), w=1.0, dash="4 3"))
for seg in eqf + mrf:
    body.append(curve_path(CAM.many(seg), w=1.1))

for a, b in ((P3, P1), (Q3, Q1), (P3, P2), (Q3, Q2)):
    body.append(line(CAM(a), CAM(b), w=0.9, dash="3 3"))
for a, b in ((P3, Q3), (P1, Q1), (P2, Q2)):
    body.append(leader(CAM(a), CAM(b), w=1.6, head=7.5, gap=0.0))
body += [pdot(*CAM(p), 2.4) for p in (P3, Q3, P1, Q1, P2, Q2)]

SEGA = ([(q1[i], q1[(i + 1) % 4]) for i in range(4)]
        + [(q2[i], q2[(i + 1) % 4]) for i in range(4)]
        + [(CAM(a), CAM(b)) for a, b in ((P3, P1), (Q3, Q1), (P3, P2), (Q3, Q2),
                                         (P3, Q3), (P1, Q1), (P2, Q2))])
CURA = [CAM.many(sg) for sg in (eqf + eqb + mrf + mrb)]
body += [point_labels([(*CAM(p), n) for p, n in
                       ((P3, "P"), (Q3, "Q"), (P1, "P₁"), (Q1, "Q₁"),
                        (P2, "P₂"), (Q2, "Q₂"))]
                      + [(q1[1][0] + 6, q1[1][1] + 30, "y = 4"),
                         (q2[0][0] - 10, q2[0][1] + 52, equation_text(*EQ2))],
                      avoid=SEGA, curves=CURA,
                      circles=[(*CAM((0, 0, 0)), R * CAM.scale)],
                      fs=FSA, gap=26)]
S["sphere"] = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VBA[0]} {VBA[1]}">'
               f'<rect width="{VBA[0]}" height="{VBA[1]}" fill="#ffffff"/>\n  '
               + "\n  ".join(body) + "\n</svg>")


# ═══════════ B) 두 평면 위의 원뿔곡선 ═══════════
VBB = (430, 360)
FSB = type_scale(*VBB)
CAMB = Camera(elev=26, azim=-63, scale=52, origin=(205, 195))
ALPHA = Plane((0.0, 0.0, 0.0), (0.0, 0.0, 1.0))                       # α: 수평
BETA = Plane((0.0, 0.0, 0.0), unit((0.0, -math.sin(math.radians(40)),
                                    math.cos(math.radians(40)))))     # β: 40° 기울기
LP, LD = plane_intersection(ALPHA, BETA)

# 두 원이 교선(α∩β = x축) 위 X± 에서 **정확히 만나도록** 유도한다.
XR = 1.05
_c1y, _c2y = 0.34, -0.30
_tan = math.tan(math.radians(40.0))
C1C = (0.0, _c1y, 0.0)                                  # α 위 중심
C2C = (0.0, _c2y, _c2y * _tan)                          # β 위 중심(β 식을 만족)
C1 = circle3(C1C, math.hypot(XR, _c1y), ALPHA.normal)
C2 = circle3(C2C, math.hypot(XR, _c2y / math.cos(math.radians(40.0))), BETA.normal)
XP, XM = (XR, 0.0, 0.0), (-XR, 0.0, 0.0)
Pt = add((0.10, 0.05, 0.0), vscale(ALPHA.normal, 1.15))               # 꼭짓점 P
F = (-0.42, 0.05, 0.0)
E, B_, Q = (0.42, 0.05, 0.0), XP, (0.0, 1.28, 0.0)
A = XM

verify_solid("conic",
             angles=[(40.0, "dihedral", ALPHA, BETA)],
             on_plane=[(F, ALPHA), (E, ALPHA), (Q, ALPHA), (A, ALPHA), (LP, ALPHA),
                       (LP, BETA), (C1C, ALPHA), (C2C, BETA), (XP, ALPHA), (XP, BETA),
                       (XM, ALPHA), (XM, BETA)],
             lengths=[(1, C1C, XP), (1, C1C, XM)],
             perpendicular=[((Pt, (0.10, 0.05, 0.0)), (XM, XP))])

qa = CAMB.many(quad(ALPHA, (1, 0, 0), (0, 1, 0), 2.3, 1.7))
qb = CAMB.many(quad(BETA, (1, 0, 0), unit(cross(BETA.normal, (1, 0, 0))), 2.1, 1.6))
c2f, c2b = split_by_depth(C2, CAMB, pivot=CAMB.depth((0, 0, 0)))

body = [poly(qb), poly(qa)]
for seg in c2b:
    body.append(curve_path(CAMB.many(seg), w=1.0, dash="4 3"))
for seg in c2f:
    body.append(curve_path(CAMB.many(seg), w=1.3))
body.append(curve_path(CAMB.many(C1), w=1.5))
body.append(line(CAMB(add(LP, vscale(LD, -2.4))), CAMB(add(LP, vscale(LD, 2.4))), w=1.2))
body.append(line(CAMB(add(XM, (-0.25, 0, 0))), CAMB(add(XP, (0.25, 0, 0))), w=1.2))
body.append(line(CAMB(Pt), CAMB((0.10, 0.05, 0.0)), w=1.1, dash="3 3"))
body.append(rangle_at(*CAMB((0.10, 0.05, 0.0)), CAMB(Pt), CAMB(XP), 9))
body += [pdot(*CAMB(p), 2.4) for p in (Pt, F, E, B_, Q, A)]
SEGB = ([(qa[i], qa[(i + 1) % 4]) for i in range(4)]
        + [(qb[i], qb[(i + 1) % 4]) for i in range(4)]
        + [(CAMB(A), CAMB(Q)), (CAMB(Pt), CAMB((0.10, 0.05, 0.0))),
           (CAMB(add(LP, vscale(LD, -2.4))), CAMB(add(LP, vscale(LD, 2.4))))])
CURB = [CAMB.many(C1), CAMB.many(C2)]
body += [point_labels([(*CAMB(p), n) for p, n in
                       ((Pt, "P"), (F, "F"), (E, "E"), (B_, "B"), (Q, "Q"), (A, "A"))]
                      + [(*CAMB(C1[12]), "C₁"), (*CAMB(C2[60]), "C₂"),
                         (qa[0][0] + 26, qa[0][1] - 10, "α"),
                         (qb[3][0] - 4, qb[3][1] + 22, "β")],
                      avoid=SEGB, curves=CURB, fs=FSB, gap=15,
                      italic={"α", "β"})]
S["conic"] = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VBB[0]} {VBB[1]}">'
              f'<rect width="{VBB[0]}" height="{VBB[1]}" fill="#ffffff"/>\n  '
              + "\n  ".join(body) + "\n</svg>")


if __name__ == "__main__":
    miss = unverified(S)
    if miss:
        raise SystemExit(f"검산 누락: {miss}")
    print(f"글자 {FSA} / {FSB}")
    for k, svg in S.items():
        a, issues = assess_svg(svg), lint_svg(svg)
        open(os.path.join(OUT, f"hard_{k}.png"), "wb").write(_svg_to_png_bytes(svg, width=760))
        print(f"  {k:7s} gate={'PASS' if a.accepted else 'FAIL ' + str(a.issues[:3])}"
              f"  lint={issues or 'CLEAN'}")
