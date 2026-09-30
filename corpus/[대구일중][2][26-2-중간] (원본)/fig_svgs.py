# -*- coding: utf-8 -*-
"""대구일중2 26-2-중간 — 그림 20개. FigureSpec v2(core.figure_scene) 선언형 작도.

좌표는 전부 문제 조건(각·길이)에서 계산한다(눈대중 금지). 스펙이 못 그리는
요소(점 dot, 등분 표시 점/×)만 해석된 translation 에 맞춰 덧그린다.
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
from core.figure_svg import lint_svg, meas, measured, txt, unverified, verify_figure  # noqa: E402

OUT = os.environ.get(
    "FIG_SVG_OUT",
    str(Path(tempfile.gettempdir()) / "exam_figure_svg" / "daeguil2"),
)
os.makedirs(OUT, exist_ok=True)
S = {}
GRAY = "#e3e3e3"
FS = 13  # 스펙 라벨과 같은 크기(렌더 SVG font-size 실측)


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


def reflect(p, a, b):
    f = foot(p, a, b)
    return (2 * f[0] - p[0], 2 * f[1] - p[1])


def unit(p, q):
    L = dist(p, q)
    return ((q[0] - p[0]) / L, (q[1] - p[1]) / L)


def bis_pt(v, p1, p2, d):
    u1, u2 = unit(v, p1), unit(v, p2)
    bx, by = u1[0] + u2[0], u1[1] + u2[1]
    L = math.hypot(bx, by)
    return (v[0] + bx / L * d, v[1] + by / L * d)


def part_pt(v, p1, p2, frac, d):
    """꼭짓점 v 의 각 v→p1..v→p2 안에서 비율 frac(0=p1 쪽) 방향 d 거리 점."""
    a1 = math.atan2(p1[1] - v[1], p1[0] - v[0])
    a2 = math.atan2(p2[1] - v[1], p2[0] - v[0])
    da = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi
    a = a1 + da * frac
    return (v[0] + d * math.cos(a), v[1] + d * math.sin(a))


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


def poly_region(*names, fill=GRAY):
    ring = list(names) + [names[0]]
    return {"boundary": [{"seg": [ring[i], ring[i + 1]]} for i in range(len(names))],
            "fill": fill}


# ── q1: 이등변삼각형, 꼭지각 70°, C 외각 x° ──────────────────────────────────
B, C = P(40, 160), P(190, 160)
A = tri(B, C, 55, 55)
X = P(255, 160)
verify_figure("q1", angles=[(70, A, B, C), (125, C, A, X)], lengths=[(1, A, B), (1, A, C)])
render("q1", {"A": A, "B": B, "C": C, "X": X},
       {"AB": seg("A", "B", ticks=2), "AC": seg("A", "C", ticks=2), "BX": ["B", "X"]},
       {"angA": ang("A", "B", "C", "70°"), "angX": ang("C", "A", "X", "x°", radius=18, label_distance=30)},
       labels={"A": "A", "B": "B", "C": "C"})

# ── q2: 두 직각삼각형 ABC(∠B=90°)·DEF(∠E=90°) ─────────────────────────────
A, B, C = P(30, 20), P(30, 135), P(110, 135)
D, E, F = P(165, 20), P(165, 135), P(245, 135)
verify_figure("q2", angles=[(90, B, A, C), (90, E, D, F)],
              lengths=[(1, A, B), (1, D, E)])
render("q2", {"A": A, "B": B, "C": C, "D": D, "E": E, "F": F},
       {"AB": ["A", "B"], "BC": ["B", "C"], "CA": ["C", "A"],
        "DE": ["D", "E"], "EF": ["E", "F"], "FD": ["F", "D"]},
       {"rB": ang("B", "A", "C", right=True), "rE": ang("E", "D", "F", right=True)})

# ── q3: 내심 I, ∠BAI=35°·∠IBC=25°·∠ICB=x°(=30°) ────────────────────────────
B, C = P(30, 200), P(300, 200)
A = tri(B, C, 50, 60)
I = incenter(A, B, C)
verify_figure("q3", angles=[(35, A, B, I), (25, B, I, C), (30, C, I, B)])
render("q3", {"A": A, "B": B, "C": C, "I": I},
       {"AB": ["A", "B"], "BC": ["B", "C"], "CA": ["C", "A"],
        "AI": ["A", "I"], "BI": ["B", "I"], "CI": ["C", "I"]},
       {"angA": ang("A", "B", "I", "35°"), "angB": ang("B", "I", "C", "25°"),
        "angC": ang("C", "I", "B", "x°")})

# ── q4: 외심 O, ∠AOC=110°(이중 호), ∠B=x° ─────────────────────────────────
B, C = P(30, 200), P(300, 200)
A = tri(B, C, 55, 63)
O = circumcenter(A, B, C)
verify_figure("q4", angles=[(110, O, A, C), (55, B, A, C)],
              lengths=[(1, O, A), (1, O, B), (1, O, C)])
render("q4", {"A": A, "B": B, "C": C, "O": O},
       {"AB": ["A", "B"], "BC": ["B", "C"], "CA": ["C", "A"],
        "OA": ["O", "A"], "OC": ["O", "C"]},
       {"angO": ang("O", "A", "C", "110°", arcs=2, radius=12, label_distance=34), "angB": ang("B", "A", "C", "x°")},
       post=dots(O))

# ── q6: 마름모, ∠OAD=55°, ∠ABO=y°(음영), OD=8cm·BO=x cm ────────────────────
O = P(160, 120)
oa = 95.0
od = oa * math.tan(math.radians(55))
A, C = P(O[0], O[1] - oa), P(O[0], O[1] + oa)
B, D = P(O[0] - od, O[1]), P(O[0] + od, O[1])
verify_figure("q6", angles=[(55, A, O, D), (35, B, A, O)],
              lengths=[(8, O, D), (8, B, O)])


def _q6_shade(tx, ty):
    r = 26.0
    p1 = (B[0] + r, B[1])
    u = unit(B, A)
    p2 = (B[0] + u[0] * r, B[1] + u[1] * r)
    return (f'<path d="M {B[0] + tx:.2f} {B[1] + ty:.2f} L {p1[0] + tx:.2f} {p1[1] + ty:.2f} '
            f'A {r} {r} 0 0 0 {p2[0] + tx:.2f} {p2[1] + ty:.2f} Z" fill="#cfcfcf" stroke="none"/>')


render("q6", {"A": A, "B": B, "C": C, "D": D, "O": O},
       {"AB": ["A", "B"], "BC": ["B", "C"], "CD": ["C", "D"], "DA": ["D", "A"],
        "AC": ["A", "C"], "BD": ["B", "D"]},
       {"angA": ang("A", "O", "D", "55°"), "angB": ang("B", "A", "O", "y°", radius=26)},
       {"dimOD": dim("O", "D", "8 cm", "right"), "dimBO": dim("B", "O", "x cm", "left")},
       labels={"A": "A", "B": "B", "C": "C", "D": "D", "O": {"text": "O", "position": "SE"}},
       pre=_q6_shade)

# ── q7: 외심 O, AD=6cm·OD=4cm·넓이 50 → 사각형 OECF 음영 ─────────────────────
# ⚠️ 조건(AB=12, OD=4, 넓이 50)을 그대로 쓰면 ∠B≈88°로 O 가 변 AC 에 붙어
# 사각형 OECF 가 찌그러진다(원본 인쇄도 비례 아님). AD:OD=6:4 는 ∠C=atan(6/4)
# 에서만 정해지므로 그 비만 지키고 나머지 각은 원본 모양(∠B≈68°)을 따른다.
def _q7():
    angC = math.degrees(math.atan2(6, 4))
    B = P(30, 210)
    C = P(300, 210)
    A = tri(B, C, 68, angC)
    return A, B, C, circumcenter(A, B, C)


A, B, C, O = _q7()
D = add(A, B, 0.5)
E = foot(O, B, C)
F = foot(O, C, A)
verify_figure("q7", lengths=[(6, A, D), (4, O, D)],
              angles=[(90, D, A, O), (90, E, C, O), (90, F, C, O)])


def _q7_thin(tx, ty):
    return "".join(
        f'<line x1="{p[0] + tx:.2f}" y1="{p[1] + ty:.2f}" x2="{O[0] + tx:.2f}" y2="{O[1] + ty:.2f}" '
        f'stroke="#111111" stroke-width="0.8"/>' for p in (A, B, C))


render("q7", {"A": A, "B": B, "C": C, "O": O, "D": D, "E": E, "F": F},
       {"AD": ["A", "D"], "DB": ["D", "B"], "BE": ["B", "E"], "EC": ["E", "C"],
        "CF": ["C", "F"], "FA": ["F", "A"], "OD": ["O", "D"], "OE": ["O", "E"], "OF": ["O", "F"]},
       {"rD": ang("D", "A", "O", right=True), "rE": ang("E", "C", "O", right=True),
        "rF": ang("F", "C", "O", right=True)},
       {"dimAD": dim("A", "D", "6cm", "left"), "dimDO": dim("D", "O", "4cm", "left")},
       regions={"shade": poly_region("O", "E", "C", "F")},
       labels={"A": "A", "B": "B", "C": "C", "D": "D", "E": "E", "F": "F", "O": "O"},
       post=dots(O))

# ── q8: A·C·D 한 직선, AB=BC=CD, B 외각 132°, ∠D=x ─────────────────────────
# ⚠️ 원본 그림 비율 그대로(정비례 아님) — 조건대로 그리면(∠A=∠ACB=88°) AC 가
# CD 의 7% 로 붙어 A·C 가 겹친다. 원본 인쇄도 과장 그림이다(원본 측정 약 120°).
A, C, D = P(40, 40), P(100, 40), P(265, 40)
hB = math.sqrt(dist(C, D) ** 2 - ((C[0] - A[0]) / 2) ** 2)
B = P((A[0] + C[0]) / 2, 40 + hB)
X = add(D, B, 1.22)
verify_figure("q8", lengths=[(1, A, B), (1, B, C), (1, C, D)])
render("q8", {"A": A, "B": B, "C": C, "D": D, "X": X},
       {"AC": ["A", "C"], "CD": seg("C", "D", ticks=2), "AB": seg("A", "B", ticks=2),
        "BC": seg("B", "C", ticks=2), "DX": ["D", "X"]},
       {"angB": ang("B", "A", "X", "132°", radius=16, label_distance=34), "angD": ang("D", "C", "B", "x")},
       labels={"A": "A", "B": {"text": "B", "position": "E"}, "C": "C", "D": "D"})

# ── q9: 내심 I, DE∥BC, ∠ADI=70°, ∠ECI=21° ──────────────────────────────────
B, C = P(30, 200), P(300, 200)
A = tri(B, C, 70, 42)
I = incenter(A, B, C)
D = isect(A, B, I, (I[0] + 10, I[1]))
E = isect(A, C, I, (I[0] + 10, I[1]))
verify_figure("q9", angles=[(70, D, A, E), (21, C, E, I), (42, E, A, D)])
render("q9", {"A": A, "B": B, "C": C, "I": I, "D": D, "E": E},
       {"AD": ["A", "D"], "DB": ["D", "B"], "BC": ["B", "C"], "CE": ["C", "E"], "EA": ["E", "A"],
        "DI": ["D", "I"], "IE": ["I", "E"], "BI": ["B", "I"], "CI": ["C", "I"]},
       {"angD": ang("D", "A", "I", "70°", label_distance=30), "angE": ang("E", "A", "I"),
        "angC": ang("C", "E", "I", "21°")})

# ── q10: 평행사변형 ABCD, 대각선 교점 O ─────────────────────────────────────
A, D, B = P(60, 20), P(240, 20), P(20, 150)
C = P(B[0] + D[0] - A[0], B[1] + D[1] - A[1])
O = isect(A, C, B, D)
verify_figure("q10", lengths=[(1, A, D), (1, B, C)], on_line=[(O, A, C), (O, B, D)])
render("q10", {"A": A, "B": B, "C": C, "D": D, "O": O},
       {"AB": ["A", "B"], "BC": ["B", "C"], "CD": ["C", "D"], "DA": ["D", "A"],
        "AC": ["A", "C"], "BD": ["B", "D"]},
       labels={"A": "A", "B": "B", "C": "C", "D": "D", "O": {"text": "O", "position": "S"}})

# ── q11: 평행사변형 ABCD, 엇각 표시(∠BAO·∠DCO, ∠CDO) ────────────────────────
A, D, B = P(60, 15), P(240, 15), P(20, 135)
C = P(B[0] + D[0] - A[0], B[1] + D[1] - A[1])
O = isect(A, C, B, D)
verify_figure("q11", lengths=[(1, A, D), (1, B, C)], on_line=[(O, A, C), (O, B, D)])
render("q11", {"A": A, "B": B, "C": C, "D": D, "O": O},
       {"AB": ["A", "B"], "BC": ["B", "C"], "CD": ["C", "D"], "DA": ["D", "A"],
        "AC": ["A", "C"], "BD": ["B", "D"]},
       {"angA": ang("A", "B", "C"), "angC": ang("C", "D", "A"), "angD": ang("D", "B", "C")},
       labels={"A": "A", "B": "B", "C": "C", "D": "D", "O": {"text": "O", "position": "S"}})

# ── q12: 직사각형 접기(A→C), ∠FCG=26° → ∠EFC=x°(=58°) ──────────────────────
h = 150.0
w = h * (math.tan(math.radians(26)) + 1 / math.cos(math.radians(26)))
A, B = P(30, 20), P(30, 20 + h)
C, D = P(30 + w, 20 + h), P(30 + w, 20)
F = P(B[0] + h * math.tan(math.radians(26)), B[1])
E = P(D[0] - (F[0] - B[0]), 20)
G = reflect(B, E, F)
verify_figure("q12", angles=[(26, C, F, G), (58, F, E, C), (90, C, E, G)],
              lengths=[(1, A, F), (1, C, F)])
render("q12", {"A": A, "B": B, "C": C, "D": D, "E": E, "F": F, "G": G},
       {"AE": seg("A", "E", dash="5 4"), "AB": seg("A", "B", dash="5 4"),
        "BF": seg("B", "F", dash="5 4"), "ED": ["E", "D"], "DC": ["D", "C"], "FC": ["F", "C"],
        "EF": ["E", "F"], "EC": ["E", "C"], "FG": ["F", "G"], "GC": ["G", "C"]},
       {"angF": ang("F", "E", "C", "x°", radius=28, label_distance=42), "angC": ang("C", "F", "G", "26°", radius=32, label_distance=54)})

# ── q13: 평행사변형, B·D 에서 AC 에 내린 수선의 발 E·F ─────────────────────
A, D, B = P(65, 15), P(292, 15), P(10, 190)
C = P(B[0] + D[0] - A[0], B[1] + D[1] - A[1])
O = isect(A, C, B, D)
E = foot(B, A, C)
F = foot(D, A, C)
verify_figure("q13", angles=[(90, E, B, C), (90, F, D, A)], lengths=[(1, B, E), (1, D, F)])
render("q13", {"A": A, "B": B, "C": C, "D": D, "O": O, "E": E, "F": F},
       {"AB": ["A", "B"], "BC": ["B", "C"], "CD": ["C", "D"], "DA": ["D", "A"],
        "AE": ["A", "E"], "EO": ["E", "O"], "OF": ["O", "F"], "FC": ["F", "C"],
        "BO": ["B", "O"], "OD": ["O", "D"], "BE": ["B", "E"], "DF": ["D", "F"],
        "BF": ["B", "F"], "DE": ["D", "E"]},
       {"rE": ang("E", "B", "O", right=True), "rF": ang("F", "D", "O", right=True)},
       labels={"A": "A", "B": "B", "C": "C", "D": "D", "E": {"text": "E", "position": "N"},
               "F": {"text": "F", "position": "S"}, "O": "O"})

# ── q14: 이등변 ∠A=80°, 내심 I·외심 O, D=AC 중점, E=OD∩IC ─────────────────
B, C = P(20, 200), P(300, 200)
A = tri(B, C, 50, 50)
I = incenter(A, B, C)
O = circumcenter(A, B, C)
D = add(A, C, 0.5)
E = isect(O, D, I, C)
verify_figure("q14", angles=[(80, A, B, C), (65, E, D, C), (90, D, O, C)])
render("q14", {"A": A, "B": B, "C": C, "I": I, "O": O, "D": D, "E": E},
       {"AB": ["A", "B"], "BC": ["B", "C"], "AD": ["A", "D"], "DC": ["D", "C"],
        "IE": ["I", "E"], "EC": ["E", "C"], "OE": ["O", "E"], "ED": ["E", "D"]},
       {"angA": ang("A", "B", "D", "80°", label_distance=36), "angE": ang("E", "D", "C")},
       labels={"A": "A", "B": "B", "C": "C", "D": "D", "E": {"text": "E", "position": "S"},
               "I": {"text": "I", "position": "NW"}, "O": {"text": "O", "position": "W"}},
       post=dots(I, O))

# ── q15: AE∥DC, AF=6·BE=8·EC=5, □ABED 음영 ────────────────────────────────
u = 20.0
B = P(20, 160)
F = P(B[0] + 2 * u, 160)
E = P(B[0] + 8 * u, 160)
C = P(E[0] + 5 * u, 160)
A = P(F[0], 160 - 6 * u)
D = add(C, (C[0] + A[0] - E[0], C[1] + A[1] - E[1]), 0.63)
verify_figure("q15", lengths=[(6, A, F), (8, B, E), (5, E, C)], angles=[(90, F, A, E)])
render("q15", {"A": A, "B": B, "C": C, "D": D, "E": E, "F": F},
       {"AB": ["A", "B"], "BF": ["B", "F"], "FE": ["F", "E"], "EC": ["E", "C"],
        "CD": seg("C", "D", parallel=1), "DA": ["D", "A"], "EA": seg("E", "A", parallel=1),
        "ED": ["E", "D"], "AF": ["A", "F"]},
       {"rF": ang("F", "A", "E", right=True)},
       None,
       regions={"shade": poly_region("A", "B", "E", "D")},
       post=lambda tx, ty: "".join(measured(p[0] + tx, p[1] + ty, q[0] + tx, q[1] + ty, o, t, FS)
                                   for p, q, o, t in ((B, E, 11, "8cm"), (E, C, 11, "5cm")))
       + meas(A[0] + tx, A[1] + ty, F[0] + tx, F[1] + ty, -8)
       + txt(F[0] + 20 + tx, (A[1] + F[1]) / 2 + 5 + ty, "6cm", FS, anc="start"))

# ── q16: 등변사다리꼴 AD∥BC, AD=CD, AC=BC → ∠DAC=36° ─────────────────────
B, C = P(20, 150), P(260, 150)
L = dist(B, C)
s = 2 * L * math.sin(math.radians(18))
A = polar(B, 72, s)
D = polar(C, 108, s)
verify_figure("q16", lengths=[(1, A, D), (1, C, D)], angles=[(36, A, D, C), (72, B, A, C)])
verify_figure("q16-AC", lengths=[(1, A, C), (1, B, C)])
render("q16", {"A": A, "B": B, "C": C, "D": D},
       {"AB": ["A", "B"], "BC": seg("B", "C", ticks=1), "CD": seg("C", "D", ticks=2),
        "DA": seg("D", "A", ticks=2), "AC": seg("A", "C", ticks=1)},
       {"angA": ang("A", "D", "C")})

# ── s1: 직각삼각형(∠C=90°) 6·8·10, 외접원·내접원 ──────────────────────────
u = 18.0
C = P(200, 170)
B = P(C[0] - 8 * u, C[1])
A = P(C[0], C[1] - 6 * u)
M = add(A, B, 0.5)
Ic = P(C[0] - 2 * u, C[1] - 2 * u)
verify_figure("s1", lengths=[(10, A, B), (6, A, C), (8, B, C), (5, M, C)], angles=[(90, C, A, B)])
render("s1", {"A": A, "B": B, "C": C, "M": M, "K": Ic, "Z": P(M[0] + 5 * u + 42, M[1])},
       {"AB": ["A", "B"], "BC": ["B", "C"], "CA": ["C", "A"]},
       {"rC": ang("C", "A", "B", right=True)},
       None,
       circles={"outer": {"center": "M", "radius": 5 * u}, "inner": {"center": "K", "radius": 2 * u}},
       labels={"A": "A", "B": "B", "C": "C"},
       post=lambda tx, ty: "".join(measured(p[0] + tx, p[1] + ty, q[0] + tx, q[1] + ty, o, t, FS)
                                   for p, q, o, t in ((A, B, 13, "10cm"), (B, C, 10, "8cm")))
       + meas(A[0] + tx, A[1] + ty, C[0] + tx, C[1] + ty, -7)
       + txt(M[0] + 5 * u + 5 + tx, (A[1] + C[1]) / 2 + 5 + ty, "6cm", FS, anc="start"))

# ── s2: 정사각형(80cm²), AE=DF, AE:AF=3:5, △AEO 음영 ─────────────────────
k = 22.5
A, D = P(20, 20), P(20 + 8 * k, 20)
B, C = P(20, 20 + 8 * k), P(20 + 8 * k, 20 + 8 * k)
E = P(20, 20 + 3 * k)
F = P(20 + 5 * k, 20)
O = isect(A, C, B, D)
verify_figure("s2", lengths=[(3, A, E), (5, A, F), (3, F, D), (8, A, D)])
render("s2", {"A": A, "B": B, "C": C, "D": D, "E": E, "F": F, "O": O},
       {"AE": seg("A", "E", ticks=2), "EB": ["E", "B"], "BC": ["B", "C"], "CD": ["C", "D"],
        "DF": seg("D", "F", ticks=2), "FA": ["F", "A"], "AC": ["A", "C"], "BD": ["B", "D"],
        "OE": ["O", "E"], "OF": ["O", "F"]},
       regions={"shade": poly_region("A", "E", "O")},
       labels={"A": "A", "B": "B", "C": "C", "D": "D", "E": "E", "F": "F",
               "O": {"text": "O", "position": "S"}})

S3_OFF = float(os.environ.get("S3_OFF", 13))
S5_OFF = float(os.environ.get("S5_OFF", 10))
S5_T = float(os.environ.get("S5_T", 0.68))
# ── s3: 평행사변형 ∠B=60°, AB=10·AD=15, AE·CF 이등분선 ─────────────────────
u = 11.0
B = P(20, 150)
A = polar(B, 60, 10 * u)
D = P(A[0] + 15 * u, A[1])
C = P(B[0] + 15 * u, B[1])
E = P(B[0] + 10 * u, B[1])
F = P(A[0] + 5 * u, A[1])
verify_figure("s3", lengths=[(10, A, B), (15, A, D), (10, B, E), (5, A, F)],
              angles=[(60, B, A, C), (60, A, B, E), (60, A, E, D), (60, C, F, B)])


def _s3_marks(tx, ty):
    out = []
    for fr in (0.3, 0.7):
        p = part_pt(A, B, D, fr * 0.5 if fr < 0.5 else 0.5 + (fr - 0.5), 17)
        out.append(f'<circle cx="{p[0] + tx:.2f}" cy="{p[1] + ty:.2f}" r="1.9" fill="#111111"/>')
    for fr in (0.25, 0.75):
        p = part_pt(C, D, B, fr, 19)
        x, y = p[0] + tx, p[1] + ty
        s_ = 3.0
        out.append(f'<path d="M {x - s_:.2f} {y - s_:.2f} L {x + s_:.2f} {y + s_:.2f} '
                   f'M {x - s_:.2f} {y + s_:.2f} L {x + s_:.2f} {y - s_:.2f}" '
                   f'stroke="#111111" stroke-width="0.9" fill="none"/>')
    return "".join(out)


render("s3", {"A": A, "B": B, "C": C, "D": D, "E": E, "F": F},
       {"AB": ["A", "B"], "BE": ["B", "E"], "EC": ["E", "C"], "CD": ["C", "D"],
        "DF": ["D", "F"], "FA": ["F", "A"], "AE": ["A", "E"], "CF": ["C", "F"]},
       {"angB": ang("B", "A", "E", "60°", radius=14, label_distance=32)},
       None,
       labels={"A": "A", "B": "B", "C": "C", "D": "D", "E": "E",
               "F": {"text": "F", "dx": -9, "dy": 15}},
       post=lambda tx, ty: _s3_marks(tx, ty) + "".join(
           measured(p[0] + tx, p[1] + ty, q[0] + tx, q[1] + ty, o, t, FS)
           for p, q, o, t in ((A, D, -13, "15 cm"), (B, A, -S3_OFF, "10 cm"))))

# ── s4: 이등변 ∠A=72°, 내심 I·외심 O, ∠ICO ───────────────────────────────
B, C = P(20, 200), P(300, 200)
A = tri(B, C, 54, 54)
I = incenter(A, B, C)
O = circumcenter(A, B, C)
verify_figure("s4", angles=[(72, A, B, C), (9, C, I, O), (27, C, I, B), (18, C, O, B)])
render("s4", {"A": A, "B": B, "C": C, "I": I, "O": O},
       {"AB": ["A", "B"], "BC": ["B", "C"], "CA": ["C", "A"], "BI": ["B", "I"], "CI": ["C", "I"],
        "BO": ["B", "O"], "CO": ["C", "O"]},
       {"angA": ang("A", "B", "C", "72°"), "angC": ang("C", "I", "O", radius=40)},
       labels={"A": "A", "B": "B", "C": "C", "I": {"text": "I", "position": "N"},
               "O": {"text": "O", "position": "S"}},
       post=dots(I, O))

# ── s5: 직각이등변 ABC(∠A=90°), 직선 l, BD⊥l·CE⊥l, BD=7·CE=3 ──────────────
# 국소 좌표(l 을 y 축)에서 만든 뒤 BC 가 수평이 되게 돌린다(원본 배치).
u = 14.0
_loc = {"A": (0.0, 0.0), "D": (0.0, 3.0), "E": (0.0, 7.0), "B": (-7.0, 3.0), "C": (3.0, 7.0),
        "L1": (0.0, -2.6), "L2": (0.0, 8.8)}
_phi = math.atan2(_loc["C"][1] - _loc["B"][1], _loc["C"][0] - _loc["B"][0])


def _s5(p):
    x, y = p
    xr = x * math.cos(-_phi) - y * math.sin(-_phi)
    yr = x * math.sin(-_phi) + y * math.cos(-_phi)
    return P(170 + xr * u, 60 + yr * u)


A, D, E, B, C, L1, L2 = (_s5(_loc[k]) for k in ("A", "D", "E", "B", "C", "L1", "L2"))
Fp = isect(A, E, B, C)
verify_figure("s5", lengths=[(7, B, D), (3, C, E), (3, A, D), (7, A, E)],
              angles=[(90, A, B, C), (90, D, B, A), (90, E, C, A)])
verify_figure("s5-iso", lengths=[(1, A, B), (1, A, C)])
render("s5", {"A": A, "B": B, "C": C, "D": D, "E": E, "F": Fp, "L1": L1, "L2": L2},
       {"lA": ["L1", "A"], "lD": ["A", "D"], "lF": ["D", "F"], "lE": ["F", "E"], "lL": ["E", "L2"], "AB": seg("A", "B", ticks=2), "AC": seg("A", "C", ticks=2),
        "BC": ["B", "C"], "BD": ["B", "D"], "CE": ["C", "E"]},
       {"rA": ang("A", "B", "C", right=True), "rD": ang("D", "B", "A", right=True),
        "rE": ang("E", "C", "F", right=True)},
       None,
       labels={"A": "A", "B": "B", "C": "C", "D": {"text": "D", "dx": 11, "dy": 6}, "E": "E",
               "F": {"text": "F", "position": "NW"}, "L1": {"text": "l", "italic": True}},
       post=lambda tx, ty: "".join(
           measured(p[0] + tx, p[1] + ty, q[0] + tx, q[1] + ty, o, t, FS, t=tt)
           for p, q, o, t, tt in ((B, D, S5_OFF, "7cm", S5_T), (C, E, -9, "3cm", 0.5))))


# 원본 인쇄 그대로 음영 위에 halo 없이 적은 치수 라벨 — lint 는 연한 음영도 '선 잉크'로 센다.
LINT_EXEMPT = {"q15": ("라벨-선 겹침: '6cm'",)}

if __name__ == "__main__":
    from core.figure_generator import _svg_to_png_bytes
    W = json.loads((Path(__file__).parent / "_work" / "fig_map.json").read_text(encoding="utf-8")) \
        if (Path(__file__).parent / "_work" / "fig_map.json").exists() else {}
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
