# -*- coding: utf-8 -*-
"""사대부중2 25-2-기말 — 그림 16개. FigureSpec v2(core.figure_scene) 선언형 작도.

좌표는 전부 문제 조건(각·길이·비)에서 계산한다(눈대중 금지). 스펙이 못 그리는
요소(점 dot, 화살표, 같은 각 •)만 해석된 translation 에 맞춰 덧그린다.
평행선(q13)·삼각뿔(s4)은 스펙 밖 도형이라 core.figure_svg 프리미티브로 직접 그린다.
화면 좌표 y 는 아래로.
"""
import json
import math
import os
import sys
import tempfile

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from core.figure_scene import compile_figure_spec  # noqa: E402
from core.figure_quality import sanitize_svg  # noqa: E402
from core.figure_svg import (auto_runs, leader, line, lint_svg, measured, measured_runs,  # noqa: E402
                             txt, unverified, verify_figure)

OUT = os.environ.get(
    "FIG_SVG_OUT",
    str(Path(tempfile.gettempdir()) / "exam_figure_svg" / "sadaebu2"),
)
os.makedirs(OUT, exist_ok=True)
S = {}
FS = 16.8  # 스펙 라벨과 같은 크기(렌더 SVG font-size 실측 — 2026-09-11 재동기화 뒤 16.8)


# ── 기하 헬퍼(화면 좌표, y 아래) ────────────────────────────────────────────
def P(x, y):
    return (float(x), float(y))


def add(p, q, t=1.0):
    return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)


def dist(p, q):
    return math.hypot(q[0] - p[0], q[1] - p[1])


def polar(p, ang_deg, r):
    """수학각(반시계, y 위) → 화면 좌표."""
    a = math.radians(ang_deg)
    return (p[0] + r * math.cos(a), p[1] - r * math.sin(a))


def isect(p1, p2, p3, p4):
    x1, y1 = p1; x2, y2 = p2; x3, y3 = p3; x4, y4 = p4
    d = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    a = x1 * y2 - y1 * x2
    b = x3 * y4 - y3 * x4
    return ((a * (x3 - x4) - (x1 - x2) * b) / d, (a * (y3 - y4) - (y1 - y2) * b) / d)


def tri(B, C, angB, angC):
    """밑변 BC(B 왼쪽, 수평), 밑각으로 꼭짓점 A(위)."""
    L = dist(B, C)
    angA = 180 - angB - angC
    ab = L * math.sin(math.radians(angC)) / math.sin(math.radians(angA))
    return polar(B, angB, ab)


def incenter(A, B, C):
    a, b, c = dist(B, C), dist(A, C), dist(A, B)
    s = a + b + c
    return ((a * A[0] + b * B[0] + c * C[0]) / s, (a * A[1] + b * B[1] + c * C[1]) / s)


def circumcenter(A, B, C):
    ax, ay = A; bx, by = B; cx, cy = C
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay)
          + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx)
          + (cx * cx + cy * cy) * (bx - ax)) / d
    return (ux, uy)


def foot(p, a, b):
    ux, uy = b[0] - a[0], b[1] - a[1]
    t = ((p[0] - a[0]) * ux + (p[1] - a[1]) * uy) / (ux * ux + uy * uy)
    return (a[0] + ux * t, a[1] + uy * t)


def unit(p, q):
    L = dist(p, q)
    return ((q[0] - p[0]) / L, (q[1] - p[1]) / L)


def bis_pt(v, p1, p2, d):
    u1, u2 = unit(v, p1), unit(v, p2)
    bx, by = u1[0] + u2[0], u1[1] + u2[1]
    L = math.hypot(bx, by)
    return (v[0] + bx / L * d, v[1] + by / L * d)


def angle_at(v, p1, p2):
    u1, u2 = unit(v, p1), unit(v, p2)
    return math.degrees(math.acos(max(-1.0, min(1.0, u1[0] * u2[0] + u1[1] * u2[1]))))


# ── 스펙 조립 ────────────────────────────────────────────────────────────────
def render(key, pts, segs, angles=None, dims=None, labels=None, regions=None,
           circles=None, pre=None, post=None):
    """FigureSpec v2 → SVG. pre/post(tx,ty)->str 는 스펙이 못 그리는 덧그림."""
    spec = {"version": 2,
            "points": {k: [round(v[0], 3), round(v[1], 3)] for k, v in pts.items()},
            "segments": segs}
    if angles:
        spec["angles"] = angles
    if dims:
        spec["dimensions"] = dims
    if regions:
        spec["regions"] = regions
    if circles:
        spec["circles"] = circles
    spec["labels"] = labels if labels is not None else {
        k: k for k in pts if len(k) == 1 and k.isupper()}
    scene = compile_figure_spec(spec)
    tx, ty = scene.resolve().translation
    svg = scene.render_svg()
    if pre:
        i = svg.index("/>", svg.index("<rect")) + 2
        svg = svg[:i] + "\n" + pre(tx, ty) + svg[i:]
    if post:
        i = svg.rindex("</svg>")
        svg = svg[:i] + post(tx, ty) + "\n" + svg[i:]
    S[key] = sanitize_svg(svg)
    return spec


def dots(*ps, r=2.3):
    def f(tx, ty):
        return "".join(f'<circle cx="{p[0] + tx:.2f}" cy="{p[1] + ty:.2f}" r="{r}" fill="#111111"/>'
                       for p in ps)
    return f


def seg(p, q, dash=None, ticks=0, parallel=0):
    d = {"points": [p, q]}
    if dash:
        d["dash"] = dash
    if ticks:
        d["ticks"] = ticks
    if parallel:
        d["parallel"] = parallel
    return d


def ang(v, p1, p2, label=None, **kw):
    d = {"vertex": v, "points": [p1, p2]}
    if label is not None:
        d["label"] = label
    d.update(kw)
    return d


def dim(p1, p2, label, side="auto", **kw):
    d = {"points": [p1, p2], "label": label, "side": side}
    d.update(kw)
    return d


def raw_svg(key, w, h, *parts):
    S[key] = sanitize_svg(f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">\n'
                          + "\n".join(parts) + "\n</svg>")


# ── q5: 한 변이 1 인 정육각형, 점 P 는 A 에서 A→F 방향으로 출발 ─────────────────
Oc, R5 = P(150, 125), 92.0
A, F, E, D, C, B = (polar(Oc, a, R5) for a in (120, 60, 0, -60, -120, 180))
Pp = add(A, F, 0.27)
verify_figure("q5", lengths=[(1, A, B), (1, B, C), (1, C, D), (1, D, E), (1, E, F), (1, F, A)],
              angles=[(120, A, B, F), (120, E, F, D)], on_line=[(Pp, A, F)])


def _q5_arrow(tx, ty):
    y = A[1] - 11 + ty
    return leader((Pp[0] + 2 + tx, y), (Pp[0] + 44 + tx, y), arrow=True, w=1.1, head=7.5, gap=0.0)


render("q5", {"A": A, "B": B, "C": C, "D": D, "E": E, "F": F, "P": Pp},
       {"AP": ["A", "P"], "PF": ["P", "F"], "FE": ["F", "E"], "ED": ["E", "D"], "DC": ["D", "C"],
        "CB": ["C", "B"], "BA": ["B", "A"]},
       None,
       {"dimAB": dim("A", "B", "1")},
       labels={"A": "A", "B": "B", "C": "C", "D": "D", "E": "E", "F": "F",
               "P": {"text": "P", "position": "S"}},
       post=lambda tx, ty: dots(Pp, r=2.6)(tx, ty) + _q5_arrow(tx, ty))

# ── q6: 내심 I, AD⊥BC(→ AB=AC), ∠AEI=60° → ∠B=∠C=40°, ∠A=100° ───────────────
B, C = P(20, 190), P(320, 190)
A = tri(B, C, 40, 40)
D = foot(A, B, C)
I = incenter(A, B, C)
E = isect(C, I, A, B)
verify_figure("q6", angles=[(60, E, A, I), (90, D, A, C), (40, B, A, C), (100, A, B, C), (20, C, I, D)],
              on_line=[(I, A, D), (E, A, B)])
render("q6", {"A": A, "B": B, "C": C, "D": D, "E": E, "I": I},
       {"AE": ["A", "E"], "EB": ["E", "B"], "BD": ["B", "D"], "DC": ["D", "C"], "CA": ["C", "A"],
        "AI": ["A", "I"], "ID": ["I", "D"], "EI": ["E", "I"], "IC": ["I", "C"]},
       {"angE": ang("E", "A", "I", "60°", label_distance=40),
        "rD": ang("D", "I", "C", "90°", right=True, label_distance=27)},
       labels={"A": "A", "B": "B", "C": "C", "D": "D", "E": "E",
               "I": "I"},
       post=dots(I))

# ── q7: 내심 I, ∠A=30°, ∠B:∠C=2:3 → ∠B=60°, ∠C=90° ─────────────────────────
C = P(200, 245)
B = P(C[0] - 132.0, C[1])
A = P(C[0], C[1] - 132.0 * math.tan(math.radians(60)))
I = incenter(A, B, C)
verify_figure("q7", angles=[(30, A, B, C), (60, B, A, C), (90, C, A, B), (135, I, A, B)])
render("q7", {"A": A, "B": B, "C": C, "I": I},
       {"AB": ["A", "B"], "BC": ["B", "C"], "CA": ["C", "A"],
        "IA": ["I", "A"], "IB": ["I", "B"], "IC": ["I", "C"]},
       labels={"A": "A", "B": "B", "C": "C", "I": {"text": "I", "position": "S"}},
       post=dots(I))

# ── q8: 외심 O, ∠OAC=25°, ∠OBA=20° → ∠OBC=45° (∠A=45°, ∠B=65°, ∠C=70°) ─────
B, C = P(30, 235), P(215, 235)
A = tri(B, C, 65, 70)
O = circumcenter(A, B, C)
verify_figure("q8", angles=[(25, A, O, C), (20, B, A, O), (45, B, O, C)],
              lengths=[(1, O, A), (1, O, B), (1, O, C)])
render("q8", {"A": A, "B": B, "C": C, "O": O},
       {"AB": ["A", "B"], "BC": ["B", "C"], "CA": ["C", "A"],
        "OA": ["O", "A"], "OB": ["O", "B"], "OC": ["O", "C"]},
       {"angA": ang("A", "O", "C", "25°", label_distance=74), "angB": ang("B", "A", "O", "20°")},
       labels={"A": "A", "B": "B", "C": "C", "O": {"text": "O", "position": "S"}},
       post=dots(O))

# ── q9: 직각삼각형(∠C=90°) 16·12·20, 외접원 O(반지름 10)·내접원 I(반지름 4) ──────
u = 11.0
C = P(240, 215)
B = P(C[0] - 16 * u, C[1])
A = P(C[0], C[1] - 12 * u)
O = add(A, B, 0.5)
I = P(C[0] - 4 * u, C[1] - 4 * u)
verify_figure("q9", lengths=[(20, A, B), (12, A, C), (16, B, C), (10, O, C),
                             (4, I, (I[0], C[1])), (4, I, (C[0], I[1])), (4, I, foot(I, A, B))],
              angles=[(90, C, A, B)])
render("q9", {"A": A, "B": B, "C": C, "O": O, "I": I, "Zz": P(C[0] + 52, (A[1] + C[1]) / 2)},
       {"AO": ["A", "O"], "OB": ["O", "B"], "BC": ["B", "C"], "CA": ["C", "A"]},
       {"rC": ang("C", "A", "B", right=True)},
       None,
       circles={"outer": {"center": "O", "radius": 10 * u}, "inner": {"center": "I", "radius": 4 * u}},
       labels={"A": "A", "B": "B", "C": "C", "O": {"text": "O", "position": "NW"},
               "I": {"text": "I", "position": "S"}},
       post=lambda tx, ty: dots(O, I)(tx, ty) + "".join(
           measured(p[0] + tx, p[1] + ty, q[0] + tx, q[1] + ty, o, t, FS)
           for p, q, o, t in ((B, C, 11, "16"), (A, C, -38, "12")))   # 12 는 외접원 바깥(원본 위치)
       + measured(A[0] + tx, A[1] + ty, B[0] + tx, B[1] + ty, 22, "20", FS, t=0.36))

# ── q11: □ABCD∽□HGFE(닮음비 1:2) — 큰 쪽은 작은 쪽을 좌우로 뒤집어 2배 ─────────
u = 33.0
_C, _D, _B = (3.0, 0.0), (2.53, 2.06), (0.0, 0.0)
_th = math.atan2(_C[1] - _D[1], _C[0] - _D[0]) - math.radians(100)   # ∠ADC=100°, AD=2
_A = (_D[0] + 2 * math.cos(_th), _D[1] + 2 * math.sin(_th))


def _sm(p):
    return P(20 + p[0] * u, 220 - p[1] * u)


def _lg(p):
    return P(20 + 3 * u + 60 + 2 * (3 - p[0]) * u, 220 - 2 * p[1] * u)


A, B, C, D = _sm(_A), _sm(_B), _sm(_C), _sm(_D)
H, G, F, E = _lg(_A), _lg(_B), _lg(_C), _lg(_D)
_ab = math.hypot(_A[0], _A[1])
verify_figure("q11", lengths=[(2, A, D), (3, B, C), (6, F, G), (4, E, H), (_ab, A, B), (2 * _ab, H, G)],
              angles=[(100, D, A, C), (100, E, H, F)])
render("q11", {"A": A, "B": B, "C": C, "D": D, "E": E, "F": F, "G": G, "H": H},
       {"AB": ["A", "B"], "BC": ["B", "C"], "CD": ["C", "D"], "DA": ["D", "A"],
        "EF": ["E", "F"], "FG": ["F", "G"], "GH": ["G", "H"], "HE": ["H", "E"]},
       {"angD": ang("D", "A", "C", "100°", radius=13, label_distance=33)},
       {"dAD": dim("A", "D", "2"), "dBC": dim("B", "C", "3"), "dFG": dim("F", "G", "6")})

# ── q12: 직각삼각형(∠A=90°), AD⊥BC, O=BC 중점, DE⊥AO. AD=10·BD=5·DC=20 ────────
u = 11.0
B = P(20, 205)
D = P(B[0] + 5 * u, B[1])
C = P(B[0] + 25 * u, B[1])
A = P(D[0], D[1] - 10 * u)
O = add(B, C, 0.5)
E = foot(D, A, O)
verify_figure("q12", lengths=[(10, A, D), (5, B, D), (20, D, C), (12.5, B, O), (12.5, A, O), (8, A, E)],
              angles=[(90, A, B, C), (90, D, A, B), (90, E, D, A)])
render("q12", {"A": A, "B": B, "C": C, "D": D, "E": E, "O": O},
       {"AB": ["A", "B"], "BD": ["B", "D"], "DO": ["D", "O"], "OC": ["O", "C"], "CA": ["C", "A"],
        "AD": ["A", "D"], "AE": ["A", "E"], "EO": ["E", "O"], "DE": ["D", "E"]},
       {"rA": ang("A", "B", "C", right=True), "rD": ang("D", "A", "B", right=True),
        "rE": ang("E", "D", "A", right=True)},
       {"dBD": dim("B", "D", "5")},
       labels={"A": "A", "B": "B", "C": "C", "D": {"text": "D", "position": "S"},
               "E": {"text": "E", "position": "E"}, "O": {"text": "O", "position": "NE"}},
       # AD=10 은 좁은 △ABD 안(원본 위치) — 스펙 배치가 자리를 못 찾아 직접 둔다.
       # DC=20 은 두 선분(DO·OC)에 걸친 치수라 스펙 치수(한 선분 전용)로 못 건다.
       post=lambda tx, ty: measured(A[0] + tx, A[1] + ty, D[0] + tx, D[1] + ty, 8, "10", FS, t=0.56)
       + measured(D[0] + tx, D[1] + ty, C[0] + tx, C[1] + ty, 11, "20", FS))

# ── q13: l∥m∥n, 세 직선이 잘린 길이 7:5 = x:6 = 9:y (x=42/5, y=45/7) ──────────
k13, s13 = 13.0, 13.8                       # 평행선 간격 7k·5k, 길이 척도 s(px/단위)
yl, ym, yn = 26.0, 26.0 + 7 * k13, 26.0 + 12 * k13


def _tr(xl, val, sign):
    """l 과 만나는 x, l~m 구간 길이값 → (l, m, n 과의 교점)."""
    dx = sign * math.sqrt((val * s13) ** 2 - (7 * k13) ** 2)
    return P(xl, yl), P(xl + dx, ym), P(xl + dx * 12 / 7, yn)


T1, T2, T3 = _tr(104, 7, -1), _tr(69, 42 / 5, 1), _tr(158, 9, 1)
verify_figure("q13", lengths=[(7, T1[0], T1[1]), (5, T1[1], T1[2]), (42 / 5, T2[0], T2[1]),
                              (6, T2[1], T2[2]), (9, T3[0], T3[1]), (45 / 7, T3[1], T3[2])])
_x1 = add(T3[0], T3[2], 1.13)[0] + 14
raw_svg("q13", round(_x1 + 26), 216,
        *[line(P(8, y), P(_x1, y), w=1.5) for y in (yl, ym, yn)],
        *[line(add(t[0], t[2], -0.14), add(t[0], t[2], 1.13), w=1.5) for t in (T1, T2, T3)],
        measured(*T1[0], *T1[1], 11, "7", FS), measured(*T1[1], *T1[2], 11, "5", FS),
        measured_runs(*T2[0], *T2[1], -11, auto_runs("x"), FS), measured(*T2[1], *T2[2], -11, "6", FS),
        measured(*T3[0], *T3[1], -11, "9", FS), measured_runs(*T3[1], *T3[2], 11, auto_runs("y"), FS),
        *[txt(_x1 + 9, y + 4.5, name, FS + 1, anc="start", it=True)
          for y, name in ((yl, "l"), (ym, "m"), (yn, "n"))])

# ── q14: 사다리꼴 AD∥BC, AD=6·BC=10, M·N 중점, P=BD∩MN, Q=AC∩MN → PQ=2 ────────
u = 24.0


def _u14(x, y):
    return P(20 + x * u, 170 - y * u)


A, D, B, C = _u14(1.6, 5.9), _u14(7.6, 5.9), _u14(0, 0), _u14(10, 0)
M, N = add(A, B, 0.5), add(D, C, 0.5)
Pq, Qq = isect(B, D, M, N), isect(A, C, M, N)
verify_figure("q14", lengths=[(6, A, D), (10, B, C), (3, M, Pq), (5, M, Qq), (2, Pq, Qq), (8, M, N)],
              on_line=[(Pq, B, D), (Qq, A, C)])
verify_figure("q14-M", lengths=[(1, A, M), (1, M, B)])
verify_figure("q14-N", lengths=[(1, D, N), (1, N, C)])
render("q14", {"A": A, "B": B, "C": C, "D": D, "M": M, "N": N, "P": Pq, "Q": Qq},
       {"AD": ["A", "D"], "AM": seg("A", "M", ticks=2), "MB": seg("M", "B", ticks=2), "BC": ["B", "C"],
        "CN": seg("C", "N", ticks=1), "ND": seg("N", "D", ticks=1),
        "MP": ["M", "P"], "PQ": ["P", "Q"], "QN": ["Q", "N"],
        "BP": ["B", "P"], "PD": ["P", "D"], "AQ": ["A", "Q"], "QC": ["Q", "C"]},
       None,
       {"dAD": dim("A", "D", "6"), "dBC": dim("B", "C", "10")},
       labels={"A": "A", "B": "B", "C": "C", "D": "D", "M": "M", "N": "N",
               "P": {"text": "P", "position": "N"}, "Q": {"text": "Q", "position": "N"}})

# ── q15: E·F 는 AB·AC 의 중점, G=CE∩BF(무게중심) ─────────────────────────────
B, C = P(20, 215), P(280, 215)
A = P(178, 35)
E, F = add(A, B, 0.5), add(A, C, 0.5)
G = isect(C, E, B, F)
verify_figure("q15", lengths=[(1, A, E), (1, E, B)], on_line=[(G, C, E), (G, B, F)])
verify_figure("q15-F", lengths=[(1, A, F), (1, F, C)])
verify_figure("q15-G", lengths=[(2, B, G), (1, G, F)])
verify_figure("q15-G2", lengths=[(2, C, G), (1, G, E)])
render("q15", {"A": A, "B": B, "C": C, "E": E, "F": F, "G": G},
       {"AE": seg("A", "E", ticks=2), "EB": seg("E", "B", ticks=2), "BC": ["B", "C"],
        "CF": seg("C", "F", ticks=1), "FA": seg("F", "A", ticks=1),
        "CG": ["C", "G"], "GE": ["G", "E"], "BG": ["B", "G"], "GF": ["G", "F"]},
       labels={"A": "A", "B": "B", "C": "C", "E": "E", "F": "F",
               "G": {"text": "G", "position": "S"}})

# ── s2: 정삼각형(한 변 12), 내심 I, ID∥AB·IE∥AC → BD=DE=EC=4 ───────────────────
B, C = P(30, 225), P(270, 225)
A = tri(B, C, 60, 60)
I = incenter(A, B, C)
D, E = add(B, C, 1 / 3), add(B, C, 2 / 3)
verify_figure("s2", lengths=[(12, A, C), (12, A, B), (12, B, C), (4, B, D), (4, D, E), (4, E, C),
                             (4, I, D), (4, I, E)],
              angles=[(60, D, I, E), (60, E, I, D), (60, B, A, C)])
render("s2", {"A": A, "B": B, "C": C, "I": I, "D": D, "E": E},
       {"BA": seg("B", "A", parallel=1), "BD": ["B", "D"], "DE": ["D", "E"], "EC": ["E", "C"],
        "CA": seg("C", "A", parallel=2), "DI": seg("D", "I", parallel=1), "EI": seg("E", "I", parallel=2)},
       None,
       {"dAC": dim("A", "C", "12")},
       labels={"A": "A", "B": "B", "C": "C", "D": "D", "E": "E",
               "I": {"text": "I", "position": "N"}},
       post=dots(I))

# ── s3: 이등변(AB=AC) ∠A=40°, 외심 O·내심 I → ∠IBO=50°-35°=15° ───────────────
B, C = P(40, 275), P(220, 275)
A = tri(B, C, 70, 70)
O = circumcenter(A, B, C)
I = incenter(A, B, C)
verify_figure("s3", angles=[(40, A, B, C), (15, B, I, O), (35, B, I, C), (50, B, O, C)],
              lengths=[(1, A, B), (1, A, C)])
verify_figure("s3-O", lengths=[(1, O, A), (1, O, B), (1, O, C)])
render("s3", {"A": A, "B": B, "C": C, "O": O, "I": I},
       {"AB": seg("A", "B", ticks=2), "AC": seg("A", "C", ticks=2), "BC": ["B", "C"],
        "OB": ["O", "B"], "OC": ["O", "C"], "IB": ["I", "B"], "IC": ["I", "C"]},
       {"angA": ang("A", "B", "C", "40°")},
       labels={"A": "A", "B": "B", "C": "C", "O": {"text": "O", "position": "N"},
               "I": {"text": "I", "position": "S"}},
       post=dots(O, I))

# ── s4: 삼각뿔을 높이 삼등분(밑면에 평행한 두 평면) — (가)·(나)·(다) ────────────
_k4 = 1.32                                   # 원본 크기(단 폭의 절반 남짓)에 맞춘 배율
T4, L4, R4, F4 = (P(x * _k4, y * _k4) for x, y in
                  ((95.3, 12), (15, 115.2), (187.7, 112.1), (122.6, 148.4)))
_c1 = [add(T4, v, 1 / 3) for v in (L4, R4, F4)]
_c2 = [add(T4, v, 2 / 3) for v in (L4, R4, F4)]
verify_figure("s4", lengths=[(1, T4, _c1[0]), (1, _c1[0], _c2[0]), (1, _c2[0], L4)])
verify_figure("s4-R", lengths=[(1, T4, _c1[1]), (1, _c1[1], _c2[1]), (1, _c2[1], R4)])
verify_figure("s4-F", lengths=[(1, T4, _c1[2]), (1, _c1[2], _c2[2]), (1, _c2[2], F4)])
_tips = tuple((x * _k4, y * _k4, name) for x, y, name in
              ((107.1, 35.3, "(가)"), (122.6, 62.5, "(나)"), (153.6, 102.2, "(다)")))
_lx4 = 203 * _k4
raw_svg("s4", round(_lx4 + 46), round(162 * _k4),
        *[line(T4, v, w=1.9) for v in (L4, R4, F4)],
        line(L4, F4, w=1.9), line(F4, R4, w=1.9), line(L4, R4, w=1.1, dash="5 4"),
        *[s for c in (_c1, _c2) for s in (line(c[0], c[2], w=1.9), line(c[2], c[1], w=1.9),
                                          line(c[0], c[1], w=1.1, dash="5 4"))],
        *[leader((_lx4, y), (x, y), arrow=True, w=0.9, head=6.5, gap=0.0) for x, y, _ in _tips],
        *[txt(_lx4 + 5, y + 5.5, name, FS, anc="start") for _, y, name in _tips])

# ── s5a: △ABC(12·16·8)∽△DCA(6·8·4) — SSS, AD∥BC ────────────────────────────
u = 17.0
B = P(20, 150)
C = P(B[0] + 16 * u, B[1])
_ax = (12 ** 2 + 16 ** 2 - 8 ** 2) / (2 * 16)
_ay = math.sqrt(12 ** 2 - _ax ** 2)
A = P(B[0] + _ax * u, B[1] - _ay * u)
D = P(A[0] + 4 * u, A[1])
verify_figure("s5a", lengths=[(12, A, B), (16, B, C), (8, A, C), (4, A, D), (6, D, C)])
render("s5a", {"A": A, "B": B, "C": C, "D": D},
       {"AB": ["A", "B"], "BC": ["B", "C"], "CA": ["C", "A"], "AD": ["A", "D"], "DC": ["D", "C"]},
       None,
       {"dAB": dim("A", "B", "12"), "dBC": dim("B", "C", "16"), "dAC": dim("A", "C", "8"),
        "dAD": dim("A", "D", "4"), "dDC": dim("D", "C", "6")})

# ── s5b: △ABC∽△EBD — AA(∠B 공통, ∠C=∠BDE). AB=8(AD=2·DB=6), BC=12, BE=4 ──────
u = 23.0
B = P(20, 190)
C = P(B[0] + 12 * u, B[1])
A = polar(B, 40, 8 * u)
D = polar(B, 40, 6 * u)
E = P(B[0] + 4 * u, B[1])
_angC = angle_at(C, A, B)
verify_figure("s5b", lengths=[(2, A, D), (6, D, B), (12, B, C), (4, B, E)],
              angles=[(_angC, C, A, B), (_angC, D, B, E)])
render("s5b", {"A": A, "B": B, "C": C, "D": D, "E": E, "Zz": P((B[0] + C[0]) / 2, B[1] + 40)},
       {"AD": ["A", "D"], "DB": ["D", "B"], "BE": ["B", "E"], "EC": ["E", "C"], "CA": ["C", "A"],
        "DE": ["D", "E"]},
       None,
       {"dAD": dim("A", "D", "2"), "dDB": dim("D", "B", "6")},
       labels={"A": "A", "B": "B", "C": "C", "D": "D", "E": "E"},
       # BC=12 는 BE·EC 두 선분에 걸친 치수 — 점 E 이름표 아래로 지나게 깊게 휜다(원본 모양).
       post=lambda tx, ty: dots(bis_pt(D, B, E, 14), bis_pt(C, A, B, 27), r=1.7)(tx, ty)
       + measured(B[0] + tx, B[1] + ty, C[0] + tx, C[1] + ty, 25, "12", FS))

# ── s6: G·G′ 는 △ABC·△ACD 의 무게중심, BD=10 → EF=5, GG′=10/3 ────────────────
u = 26.0
B = P(20, 228)
Dd = P(B[0] + 10 * u, B[1])
C = P(B[0] + 4 * u, B[1])
A = P(B[0] + 4.96 * u, B[1] - 8.0 * u)
E, F = add(B, C, 0.5), add(C, Dd, 0.5)
G, G2 = add(A, E, 2 / 3), add(A, F, 2 / 3)
verify_figure("s6", lengths=[(10, B, Dd), (5, E, F), (10 / 3, G, G2), (2, B, E), (2, E, C), (3, C, F), (3, F, Dd)])
verify_figure("s6-G", lengths=[(2, A, G), (1, G, E)])
verify_figure("s6-G2", lengths=[(2, A, G2), (1, G2, F)])
render("s6", {"A": A, "B": B, "C": C, "D": Dd, "E": E, "F": F, "G": G, "H": G2,
              "Zz": P((B[0] + Dd[0]) / 2, B[1] + 50)},
       {"AB": ["A", "B"], "AD": ["A", "D"], "BE": ["B", "E"], "EC": ["E", "C"], "CF": ["C", "F"],
        "FD": ["F", "D"], "AG": ["A", "G"], "GE": ["G", "E"], "AC": ["A", "C"],
        "AH": ["A", "H"], "HF": ["H", "F"], "GH": ["G", "H"]},
       labels={"A": "A", "B": "B", "C": "C", "D": "D", "E": "E", "F": "F",
               "G": {"text": "G", "position": "W"}, "H": {"text": "G'", "position": "E"}},
       # BD=10 은 네 선분에 걸친 치수 — E·C·F 이름표 아래로 지나게 깊게 휜다(원본 모양).
       post=lambda tx, ty: dots(G, G2)(tx, ty)
       + measured(B[0] + tx, B[1] + ty, Dd[0] + tx, Dd[1] + ty, 34, "10", FS))


LINT_EXEMPT = {}

if __name__ == "__main__":
    from core.figure_generator import _svg_to_png_bytes
    miss = unverified(S)
    if miss:
        raise SystemExit(f"검산 누락(verify_figure 미호출): {miss}")
    bad = []
    only = [k for k in os.environ.get("FIG_ONLY", "").split(",") if k]
    for k, svg in S.items():
        if only and k not in only:
            continue
        issues = [i for i in lint_svg(svg) if not any(i.startswith(x) for x in LINT_EXEMPT.get(k, ()))]
        if issues:
            bad.append(f"{k}: {'; '.join(issues)}")
        png = _svg_to_png_bytes(svg, width=720)
        if not png:
            raise SystemExit(f"{k} PNG 렌더 실패")
        open(os.path.join(OUT, f"{k}.png"), "wb").write(png)
        print(k, "ok" if not issues else "LINT")
    if bad and "--lenient" not in sys.argv:
        raise SystemExit("lint 실패:\n" + "\n".join(bad))
    elif bad:
        print("\n".join(bad))
