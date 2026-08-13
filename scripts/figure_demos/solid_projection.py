# -*- coding: utf-8 -*-
"""core.figure_solid 실증 — 시험지 스크립트가 쓸 패턴 그대로.

① 정사영(평면 α + 삼각형 ABC + 정사영 A′B′C′ + 이면각 θ)
② 직육면체 겨냥도(뒤쪽 모서리 자동 점선)
둘 다 verify_solid → figure_svg 작도 → assess_svg/lint_svg 게이트를 통과해야 한다.
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
from core.figure_solid import (Plane, cabinet, dihedral_angle, foot, isometric,
                               project_points, projected_area, verify_solid)
from core.figure_svg import (angle_mark, dot, halo_text, line, lint_svg, pt,
                             rangle_at, txt, unverified)

OUT = os.environ.get("FIG_DEMO_OUT",
                     str(Path(tempfile.gettempdir()) / "figure_demos"))
os.makedirs(OUT, exist_ok=True)
S = {}


def _poly(points, w=1.4, fill="none"):
    return (f'<polygon points="{" ".join(pt(x, y) for x, y in points)}" '
            f'fill="{fill}" stroke="#000" stroke-width="{w}"/>')


def _outward(points, names, d=19.0, far=(), fixed=None):
    gx = sum(x for x, _ in points) / len(points)
    gy = sum(y for _, y in points) / len(points)
    out = []
    for (x, y), nm in zip(points, names):
        vx, vy = x - gx, y - gy
        L = math.hypot(vx, vy) or 1.0
        if fixed and nm in fixed:            # 안쪽 꼭짓점은 손으로 자리를 준다
            dx, dy = fixed[nm]
            out.append(txt(x + dx, y + dy, nm, fs=14))
            continue
        dd = 34.0 if nm in far else d
        out.append(txt(x + vx / L * dd, y + vy / L * dd + 4, nm, fs=14))
    return out


# ══════════ ① 정사영 — 평면 α 위 삼각형 ABC 의 정사영 A′B′C′ ══════════

ALPHA = Plane.xy()
TRI = [(-1.30, -0.55, 1.05), (1.45, -0.35, 0.80), (-0.20, 1.30, 1.50)]
FEET = project_points(TRI, ALPHA)
THETA = dihedral_angle(Plane.through(*TRI), ALPHA)

# ⭐ 검산 먼저 — 좌표가 조건과 모순이면 여기서 예외가 난다.
verify_solid(
    "proj",
    feet=[(FEET[i], TRI[i], ALPHA) for i in range(3)],       # A′ 가 진짜 A 의 발인가
    on_plane=[(f, ALPHA) for f in FEET],                     # 발이 평면 위인가
    areas=[(projected_area(TRI, ALPHA), TRI, ALPHA)],        # S′ = S·cosθ
    angles=[(THETA, "dihedral", Plane.through(*TRI), ALPHA)],
    perpendicular=[(((TRI[0]), (FEET[0])), ((FEET[0]), (FEET[1])))],  # 수선 ⊥ 평면
    view=cabinet(),                                          # 퇴화 시점 아닌가
)

V = cabinet(scale=52, origin=(190, 200), depth_ratio=0.55, depth_deg=32)
PLANE_QUAD = [(-2.1, -1.5, 0), (2.2, -1.5, 0), (2.9, 1.7, 0), (-1.4, 1.7, 0)]
p2, t2, f2 = V.many(PLANE_QUAD), V.many(TRI), V.many(FEET)

body = [_poly(p2), _poly(f2, w=1.5, fill="#e8e8e8")]
body += [line(t2[i], t2[(i + 1) % 3], w=1.8) for i in range(3)]
body += [line(t2[i], f2[i], w=1.2, dash="5 4") for i in range(3)]   # 수선 = 점선
body += [rangle_at(f2[0][0], f2[0][1], t2[0], f2[1], 9)]           # 발의 직각 표시
body += [dot(*q) for q in t2 + f2]
body += _outward(t2 + f2, ["A", "B", "C", "A'", "B'", "C'"],
                 fixed={"C'": (-20, -8)})
body += [txt(318, 189, "α", fs=15, it=True),   # 평면 안 빈 곳(오른쪽, 모서리 사이)
         halo_text(96, 128, f"θ = {THETA:.0f}°", fs=13)]
S["proj"] = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 300">'
             '<rect width="420" height="300" fill="#ffffff"/>\n  '
             + "\n  ".join(body) + "\n</svg>")


# ══════════ ② 직육면체 겨냥도 — 뒤쪽 모서리 자동 점선 ══════════

W, D, H = 2.4, 1.5, 1.6
BOX = [(0, 0, 0), (W, 0, 0), (W, D, 0), (0, D, 0),
       (0, 0, H), (W, 0, H), (W, D, H), (0, D, H)]
FACES = {                       # 면 → (꼭짓점 인덱스, 바깥 법선)
    "bottom": ((0, 1, 2, 3), (0, 0, -1)), "top": ((4, 5, 6, 7), (0, 0, 1)),
    "front":  ((0, 1, 5, 4), (0, -1, 0)), "back": ((3, 2, 6, 7), (0, 1, 0)),
    "left":   ((0, 3, 7, 4), (-1, 0, 0)), "right": ((1, 2, 6, 5), (1, 0, 0)),
}
EDGES = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
         (0, 4), (1, 5), (2, 6), (3, 7)]

VB = isometric(scale=54, origin=(110, 210))
b2 = VB.many(BOX)

# 볼록 입체이므로 "앞면에 하나도 안 걸린 모서리" = 숨은 모서리.
visible = set()
for verts, n in FACES.values():
    if VB.is_back_facing(n):
        continue
    for i in range(4):
        a, b = verts[i], verts[(i + 1) % 4]
        visible.add((min(a, b), max(a, b)))

verify_solid("box",
             lengths=[(W, BOX[0], BOX[1]), (D, BOX[1], BOX[2]), (H, BOX[0], BOX[4])],
             perpendicular=[((BOX[0], BOX[1]), (BOX[0], BOX[3])),
                            ((BOX[0], BOX[1]), (BOX[0], BOX[4]))])

body = []
for a, b in EDGES:
    seen = (min(a, b), max(a, b)) in visible
    body.append(line(b2[a], b2[b], w=1.8 if seen else 1.1,
                     dash=None if seen else "5 4"))
body += [dot(*q, 2.2) for q in b2]
# D 는 숨은 꼭짓점이라 도형 안쪽에 있다 — 바깥밀기로는 선을 못 피한다.
body += _outward(b2, ["A", "B", "C", "D", "E", "F", "G", "H"], d=17,
                 fixed={"D": (-17, -7), "F": (13, 17)})
S["box"] = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 285">'
            '<rect width="360" height="285" fill="#ffffff"/>\n  '
            + "\n  ".join(body) + "\n</svg>")


if __name__ == "__main__":
    miss = unverified(S)
    if miss:
        raise SystemExit(f"검산 누락: {miss}")
    hidden = len(EDGES) - len(visible)
    print(f"정사영 θ = {THETA:.2f}°   S′ = {projected_area(TRI, ALPHA):.4f}")
    print(f"직육면체 숨은 모서리 {hidden}개 (볼록 입체는 3개가 정상)")
    for k, svg in S.items():
        a = assess_svg(svg)
        issues = lint_svg(svg)
        png = _svg_to_png_bytes(svg, width=560)
        open(os.path.join(OUT, f"solid_{k}.png"), "wb").write(png)
        print(f"  {k:5s} gate={'PASS' if a.accepted else 'FAIL ' + str(a.issues)}"
              f"  lint={issues or 'CLEAN'}")
