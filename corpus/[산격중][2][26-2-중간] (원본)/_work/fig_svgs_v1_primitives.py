# -*- coding: utf-8 -*-
"""산격중2 26-2-중간 — 그림 19개 core.figure_svg 엔진 작도(정의값 기하).

원본은 학생 사본 스캔(연필 풀이·색펜 낙서)이라 그림을 캡처하지 않고 **문제 조건에서
좌표를 유도**해 다시 그린다. 조건이 모양을 정하지 않는 부분(자유 변의 길이·기울기)은
원본 인쇄 도형의 비율을 실측해 따른다. 축척은 x·y 등방(한 그림 = 한 척도).
라벨값과 작도가 맞는지는 전부 verify_figure 로 재측정한다.
"""
import math
import os
import sys
import tempfile

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
from core.figure_svg import (SVGTextRun, angle_mark, bisect_pt, dot, eq_tick,  # noqa: E402
                             halo_angle, halo_text, isect, leader, line, lint_svg,
                             measured, measured_runs, rangle_at, txt, type_scale,
                             unverified, verify_figure)

OUT = os.environ.get(
    "FIG_SVG_OUT",
    str(Path(tempfile.gettempdir()) / "exam_figure_svg" / "sangyeok2"),
)
os.makedirs(OUT, exist_ok=True)
S = {}

X_RUN = [SVGTextRun("x", italic=True)]


def runs(*parts):
    """('x',True) 같은 조각들 → SVGTextRun 튜플."""
    return [SVGTextRun(t, italic=i) for t, i in parts]


class Frame:
    """수학 좌표(y 위) → SVG 좌표(y 아래), **등방 척도 s**. 여백 pad=(좌,위,우,아래)."""

    def __init__(self, pts, s, pad=(30, 30, 30, 30), ox=0.0, oy=0.0):
        xs = [p[0] for p in pts.values()]
        ys = [p[1] for p in pts.values()]
        self.minx, self.maxy, self.s = min(xs), max(ys), s
        self.l, self.t = pad[0] + ox, pad[1] + oy
        self.W = pad[0] + (max(xs) - min(xs)) * s + pad[2]
        self.H = pad[1] + (max(ys) - min(ys)) * s + pad[3]
        self.m = {k: self.p(v) for k, v in pts.items()}
        self.c = (sum(p[0] for p in self.m.values()) / len(self.m),
                  sum(p[1] for p in self.m.values()) / len(self.m))

    def p(self, q):
        return (self.l + (q[0] - self.minx) * self.s, self.t + (self.maxy - q[1]) * self.s)

    def __getitem__(self, k):
        return self.m[k]


def lab(P, name, fs, ang=None, d=None, center=None, it=False):
    """점 이름 — 기본은 도형 중심에서 바깥쪽(ang 도, 수학각으로 지정 가능)."""
    d = fs * 0.85 if d is None else d
    if ang is None:
        dx, dy = P[0] - center[0], P[1] - center[1]
        L = math.hypot(dx, dy) or 1.0
        ux, uy = dx / L, dy / L
    else:
        ux, uy = math.cos(math.radians(ang)), -math.sin(math.radians(ang))
    return txt(P[0] + ux * d, P[1] + uy * d + 0.35 * fs, name, fs, it=it)


def poly(*ps, w=2):
    return "\n".join(line(ps[i], ps[(i + 1) % len(ps)], w) for i in range(len(ps)))


def ticks(p, q, n=1, gap=5.0, ln=5.5):
    """같음 표시 n 개 — 변에 수직, 중점 둘레 gap 간격."""
    L = math.hypot(q[0] - p[0], q[1] - p[1])
    ux, uy = (q[0] - p[0]) / L, (q[1] - p[1]) / L
    mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
    out = []
    for i in range(n):
        o = (i - (n - 1) / 2) * gap
        c = (mx + ux * o, my + uy * o)
        out.append(eq_tick((c[0] - ux, c[1] - uy), (c[0] + ux, c[1] + uy), ln=ln))
    return "".join(out)


def arcm(v, p1, p2, r=18):
    return angle_mark(*v, p1, p2, r=r, dash=False, w=1.0)


def dot_in(v, p1, p2, d=16, r=1.9):
    return dot(*bisect_pt(*v, p1, p2, d), r)


def ring_in(v, p1, p2, d=16, r=2.4):
    x, y = bisect_pt(*v, p1, p2, d)
    return (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="none" '
            f'stroke="#000" stroke-width="0.9"/>')


def cross_in(v, p1, p2, d=18, s=3.0):
    x, y = bisect_pt(*v, p1, p2, d)
    return (line((x - s, y - s), (x + s, y + s), 1.0)
            + line((x - s, y + s), (x + s, y - s), 1.0))


def par_arrow(p, q, head=6.0):
    """평행 표시 화살촉(선분 중점, p→q 방향)."""
    L = math.hypot(q[0] - p[0], q[1] - p[1])
    ux, uy = (q[0] - p[0]) / L, (q[1] - p[1]) / L
    tx, ty = (p[0] + q[0]) / 2 + ux * head / 2, (p[1] + q[1]) / 2 + uy * head / 2
    bx, by = tx - ux * head, ty - uy * head
    nx, ny = -uy, ux
    return (f'<path d="M {tx:.1f} {ty:.1f} L {bx + nx * 3:.1f} {by + ny * 3:.1f} '
            f'L {bx - nx * 3:.1f} {by - ny * 3:.1f} Z" fill="#000"/>')


def svg(F, body):
    return (f'<svg viewBox="0 0 {F.W:.0f} {F.H:.0f}" xmlns="http://www.w3.org/2000/svg">\n'
            + body + "\n</svg>")


def pol(r, deg_):
    return (r * math.cos(math.radians(deg_)), r * math.sin(math.radians(deg_)))


def add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def mid(a, b):
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def incenter(A, B, C):
    a, b, c = dist(B, C), dist(A, C), dist(A, B)
    s = a + b + c
    return ((a * A[0] + b * B[0] + c * C[0]) / s, (a * A[1] + b * B[1] + c * C[1]) / s)


def foot(P, A, B):
    ux, uy = B[0] - A[0], B[1] - A[1]
    t = ((P[0] - A[0]) * ux + (P[1] - A[1]) * uy) / (ux * ux + uy * uy)
    return (A[0] + ux * t, A[1] + uy * t)


def rot(P, O, deg_):
    c, s = math.cos(math.radians(deg_)), math.sin(math.radians(deg_))
    dx, dy = P[0] - O[0], P[1] - O[1]
    return (O[0] + c * dx - s * dy, O[1] + s * dx + c * dy)


# ── q1: AB=AC 이등변삼각형, ∠A=40°, B 에서의 외각 x ─────────────────────
A = (0.0, 0.0)
B = (10.0, 0.0)
C = pol(10.0, 40.0)
F = Frame({"A": A, "B": B, "C": C, "X": (13.2, 0.0)}, 19, (26, 26, 12, 28))
fs = type_scale(F.W, F.H)
verify_figure("q1", lengths=[(10, F["A"], F["B"]), (10, F["A"], F["C"])],
              angles=[(40, F["A"], F["B"], F["C"]), (110, F["B"], F["C"], F["X"])])
S["q1"] = svg(F, "\n".join([
    line(F["A"], F["X"]), line(F["A"], F["C"]), line(F["B"], F["C"]),
    ticks(F["A"], F["B"]), ticks(F["A"], F["C"]),
    arcm(F["A"], F["B"], F["C"], 22), halo_angle(*F["A"], F["B"], F["C"], 36, "40°", fs - 2),
    arcm(F["B"], F["X"], F["C"], 14), halo_angle(*F["B"], F["X"], F["C"], 26, None, fs, runs=X_RUN),
    lab(F["A"], "A", fs, ang=180), lab(F["B"], "B", fs, ang=-100, d=fs),
    lab(F["C"], "C", fs, ang=90),
]))

# ── q2: AB=AC, BC=DC, ∠ACD=∠DCE=52°, x=∠ABD ─────────────────────────
B = (0.0, 0.0)
C = (2.0, 0.0)
A = (1.0, math.tan(math.radians(76)))       # ∠ACE=104° → ∠ACB=76°
D = add(C, pol(2.0, 52.0))                  # CD=CB, ∠DCE=52°
E = (4.1, 0.0)
F = Frame({"A": A, "B": B, "C": C, "D": D, "E": E, "X": (4.6, 0.0)}, 52, (30, 28, 12, 30))
fs = type_scale(F.W, F.H)
ab = dist(A, B)
verify_figure("q2", lengths=[(ab, F["A"], F["B"]), (ab, F["A"], F["C"]),
                             (2, F["B"], F["C"]), (2, F["C"], F["D"])],
              angles=[(52, F["C"], F["A"], F["D"]), (52, F["C"], F["D"], F["E"]),
                      (50, F["B"], F["A"], F["D"])])
S["q2"] = svg(F, "\n".join([
    line(F["B"], F["X"]), line(F["A"], F["B"]), line(F["A"], F["C"]),
    line(F["B"], F["D"]), line(F["C"], F["D"]), dot(*F["E"], 2.2),
    ticks(F["A"], F["B"], 2), ticks(F["A"], F["C"], 2),
    ticks(F["B"], F["C"]), ticks(F["C"], F["D"]),
    dot_in(F["C"], F["A"], F["D"], 12), dot_in(F["C"], F["D"], F["E"], 12),
    arcm(F["C"], F["D"], F["E"], 20),
    halo_angle(*F["C"], F["D"], F["E"], 30, "52°", fs - 2),
    arcm(F["B"], F["D"], F["A"], 20),
    halo_angle(*F["B"], F["D"], F["A"], 28, None, fs - 1, runs=X_RUN),
    lab(F["A"], "A", fs, ang=90), lab(F["B"], "B", fs, ang=180),
    lab(F["C"], "C", fs, ang=-90), lab(F["D"], "D", fs, ang=20),
    lab(F["E"], "E", fs, ang=-90),
]))

# ── q3: ∠B=∠C, AC=(x+6) cm, AB=(2x-4) cm (x=10 → 16) ──────────────────
half = math.degrees(math.asin(6.6 / 16))
A = (0.0, 0.0)
C = pol(16.0, half)
B = pol(16.0, -half)
F = Frame({"A": A, "B": B, "C": C}, 12, (30, 44, 30, 44))
fs = type_scale(F.W, F.H)
verify_figure("q3", lengths=[(16, F["A"], F["B"]), (16, F["A"], F["C"])],
              angles=[(90 - half, F["B"], F["A"], F["C"]), (90 - half, F["C"], F["A"], F["B"])])
S["q3"] = svg(F, "\n".join([
    poly(F["A"], F["B"], F["C"]),
    dot_in(F["B"], F["A"], F["C"], 13), dot_in(F["C"], F["A"], F["B"], 13),
    measured_runs(*F["A"], *F["C"], -16, runs(("(", 0), ("x", 1), ("+6) cm", 0)), fs - 2),
    measured_runs(*F["A"], *F["B"], 16, runs(("(2", 0), ("x", 1), ("-4) cm", 0)), fs - 2),
    lab(F["A"], "A", fs, ang=180), lab(F["B"], "B", fs, ang=-30),
    lab(F["C"], "C", fs, ang=30),
]))

# ── q4: 두 직각삼각형 ABC(∠C=90°) · DEF(∠F=90°) ────────────────────────
C = (0.0, 0.0)
B = (-6.0, 0.0)
A = (0.0, 10.2)
Fp = (2.4, 0.0)
E = (8.4, 0.0)
D = (2.4, 10.2)
F = Frame({"A": A, "B": B, "C": C, "D": D, "E": E, "F": Fp}, 15, (26, 28, 26, 28))
fs = type_scale(F.W, F.H)
verify_figure("q4", lengths=[(6, F["B"], F["C"]), (6, F["E"], F["F"]),
                             (10.2, F["A"], F["C"]), (10.2, F["D"], F["F"])],
              angles=[(90, F["C"], F["A"], F["B"]), (90, F["F"], F["D"], F["E"])])
S["q4"] = svg(F, "\n".join([
    poly(F["A"], F["B"], F["C"]), poly(F["D"], F["E"], F["F"]),
    rangle_at(*F["C"], F["A"], F["B"], 8), rangle_at(*F["F"], F["D"], F["E"], 8),
    lab(F["A"], "A", fs, ang=90), lab(F["B"], "B", fs, ang=190),
    lab(F["C"], "C", fs, ang=-35), lab(F["D"], "D", fs, ang=90),
    lab(F["E"], "E", fs, ang=-10), lab(F["F"], "F", fs, ang=-145),
]))

# ── q5: ∠C=90°, AB=20·AC=12·BC=16, ∠A 이등분선 AD, DC=6 ────────────────
B = (0.0, 0.0)
C = (16.0, 0.0)
A = (16.0, 12.0)
D = (10.0, 0.0)
F = Frame({"A": A, "B": B, "C": C, "D": D}, 11.5, (30, 26, 58, 40))
fs = type_scale(F.W, F.H)
hA = math.degrees(math.atan2(16, 12)) / 2
verify_figure("q5", lengths=[(20, F["A"], F["B"]), (12, F["A"], F["C"]),
                             (6, F["D"], F["C"]), (16, F["B"], F["C"])],
              angles=[(hA, F["A"], F["B"], F["D"]), (hA, F["A"], F["D"], F["C"]),
                      (90, F["C"], F["A"], F["B"])])
S["q5"] = svg(F, "\n".join([
    poly(F["A"], F["B"], F["C"]), line(F["A"], F["D"]),
    rangle_at(*F["C"], F["A"], F["B"], 8),
    dot_in(F["A"], F["B"], F["D"], 22), dot_in(F["A"], F["D"], F["C"], 22),
    measured(*F["B"], *F["A"], 16, "20 cm", fs - 2),
    measured(*F["C"], *F["A"], 16, "12 cm", fs - 2),
    measured(*F["D"], *F["C"], -9, "6 cm", fs - 3),
    lab(F["A"], "A", fs, ang=80), lab(F["B"], "B", fs, ang=190),
    lab(F["C"], "C", fs, ang=-30), lab(F["D"], "D", fs, ang=-120),
]))

# ── q6: 외심 O, ∠OBC=26°, ∠OCA=40°, x=∠OAB ─────────────────────────────
O = (0.0, 0.0)
Bq, Cq, Aq = pol(5, 206), pol(5, 334), pol(5, 74)
F = Frame({"A": Aq, "B": Bq, "C": Cq, "O": O}, 27, (26, 28, 26, 26))
fs = type_scale(F.W, F.H)
verify_figure("q6", angles=[(26, F["B"], F["O"], F["C"]), (40, F["C"], F["O"], F["A"]),
                            (24, F["A"], F["B"], F["O"])],
              lengths=[(5, F["O"], F["A"]), (5, F["O"], F["B"]), (5, F["O"], F["C"])])
S["q6"] = svg(F, "\n".join([
    poly(F["A"], F["B"], F["C"]),
    line(F["O"], F["A"], 1.4), line(F["O"], F["B"], 1.4), line(F["O"], F["C"], 1.4),
    dot(*F["O"], 2.4),
    arcm(F["B"], F["C"], F["O"], 26), halo_angle(*F["B"], F["C"], F["O"], 36, "26°", fs - 3),
    arcm(F["C"], F["O"], F["A"], 22), halo_angle(*F["C"], F["O"], F["A"], 36, "40°", fs - 3),
    arcm(F["A"], F["B"], F["O"], 26),
    halo_angle(*F["A"], F["B"], F["O"], 38, None, fs - 2, runs=X_RUN),
    lab(F["A"], "A", fs, ang=90), lab(F["B"], "B", fs, ang=200),
    lab(F["C"], "C", fs, ang=-20), lab(F["O"], "O", fs, ang=-90, d=fs * 0.9),
]))

# ── q7: 외심 O, OD⊥AC, AD=6 → AC=12, 둘레 30 → R=9 ─────────────────────
R7 = 9.0
hd = math.degrees(math.asin(6 / R7))
O = (0.0, 0.0)
Aq, Cq, Bq = pol(R7, 16 + hd), pol(R7, 16 - hd), pol(R7, 205)
Dq = mid(Aq, Cq)
F = Frame({"A": Aq, "B": Bq, "C": Cq, "O": O, "D": Dq}, 13.5, (28, 28, 66, 28))
fs = type_scale(F.W, F.H)
verify_figure("q7", lengths=[(6, F["A"], F["D"]), (6, F["D"], F["C"]),
                             (9, F["O"], F["A"]), (9, F["O"], F["C"]), (9, F["O"], F["B"])],
              angles=[(90, F["D"], F["O"], F["A"])])
S["q7"] = svg(F, "\n".join([
    poly(F["A"], F["B"], F["C"]),
    line(F["O"], F["A"], 1.4), line(F["O"], F["C"], 1.4), line(F["O"], F["D"], 1.4),
    rangle_at(*F["D"], F["O"], F["A"], 7), dot(*F["O"], 2.6),
    measured(*F["A"], *F["D"], 12, "6 cm", fs - 1),
    lab(F["A"], "A", fs, ang=95), lab(F["B"], "B", fs, ang=190),
    lab(F["C"], "C", fs, ang=-20), lab(F["D"], "D", fs, ang=5, d=fs * 1.0),
    lab(F["O"], "O", fs, ang=-150, d=fs * 1.0),
]))

# ── q8: 내심 I, 수선의 발 D(AB)·E(BC)·F(CA) ───────────────────────────
Aq, Bq, Cq = (530 / 3.2, -130 / 3.2), (175 / 3.2, -755 / 3.2), (1060 / 3.2, -740 / 3.2)
Iq = incenter(Aq, Bq, Cq)
Dq, Eq, Fq = foot(Iq, Aq, Bq), foot(Iq, Bq, Cq), foot(Iq, Cq, Aq)
F = Frame({"A": Aq, "B": Bq, "C": Cq, "I": Iq, "D": Dq, "E": Eq, "F": Fq}, 1.0,
          (26, 28, 26, 30))
fs = type_scale(F.W, F.H)
hA8 = math.degrees(math.acos(
    ((Bq[0] - Aq[0]) * (Cq[0] - Aq[0]) + (Bq[1] - Aq[1]) * (Cq[1] - Aq[1]))
    / (dist(Aq, Bq) * dist(Aq, Cq)))) / 2
verify_figure("q8", angles=[(90, F["D"], F["I"], F["A"]), (90, F["E"], F["I"], F["C"]),
                            (90, F["F"], F["I"], F["C"]),
                            (hA8, F["A"], F["B"], F["I"]), (hA8, F["A"], F["I"], F["C"])],
              on_line=[(F["D"], F["A"], F["B"]), (F["E"], F["B"], F["C"]),
                       (F["F"], F["C"], F["A"])])
S["q8"] = svg(F, "\n".join([
    poly(F["A"], F["B"], F["C"]),
    *[line(F["I"], F[k], 1.1) for k in "ABCDEF"],
    rangle_at(*F["D"], F["I"], F["B"], 7), rangle_at(*F["E"], F["I"], F["C"], 7),
    rangle_at(*F["F"], F["I"], F["A"], 7), dot(*F["I"], 2.4),
    cross_in(F["A"], F["B"], F["I"], 30), cross_in(F["A"], F["I"], F["C"], 30),
    dot_in(F["B"], F["A"], F["I"], 30, 2.4), dot_in(F["B"], F["I"], F["C"], 30, 2.4),
    lab(F["A"], "A", fs, ang=90), lab(F["B"], "B", fs, ang=200),
    lab(F["C"], "C", fs, ang=-15), lab(F["D"], "D", fs, ang=160),
    lab(F["E"], "E", fs, ang=-90), lab(F["F"], "F", fs, ang=30),
    lab(F["I"], "I", fs, ang=-120, d=fs * 1.15),
]))

# ── q9: 내심 I, ∠IBC=30°, ∠ICB=25° → ∠B=60°, ∠C=50°, x=70° ─────────────
Bq, Cq = (0.0, 0.0), (10.0, 0.0)
Aq = isect(Bq, pol(1, 60), Cq, add(Cq, pol(1, 130)))
Iq = incenter(Aq, Bq, Cq)
F = Frame({"A": Aq, "B": Bq, "C": Cq, "I": Iq}, 24, (26, 28, 26, 28))
fs = type_scale(F.W, F.H)
verify_figure("q9", angles=[(30, F["B"], F["C"], F["I"]), (25, F["C"], F["I"], F["B"]),
                            (70, F["A"], F["B"], F["C"]), (30, F["B"], F["A"], F["I"])])
S["q9"] = svg(F, "\n".join([
    poly(F["A"], F["B"], F["C"]),
    line(F["I"], F["B"], 1.4), line(F["I"], F["C"], 1.4), dot(*F["I"], 2.6),
    arcm(F["B"], F["C"], F["I"], 26), halo_angle(*F["B"], F["C"], F["I"], 40, "30°", fs - 2),
    arcm(F["C"], F["I"], F["B"], 28), halo_angle(*F["C"], F["I"], F["B"], 44, "25°", fs - 2),
    arcm(F["A"], F["B"], F["C"], 18),
    halo_angle(*F["A"], F["B"], F["C"], 30, None, fs - 1, runs=X_RUN),
    lab(F["A"], "A", fs, ang=90), lab(F["B"], "B", fs, ang=200),
    lab(F["C"], "C", fs, ang=-20), lab(F["I"], "I", fs, ang=90, d=fs * 0.95),
]))

# ── q10: ∠A=100°(정답 ①) 이등변, 내심 I, 외심 O, ∠IBO=30° ───────────────
Bq, Cq = (0.0, 0.0), (10.0, 0.0)
Aq = (5.0, 5.0 * math.tan(math.radians(40)))
Iq = (5.0, 5.0 * math.tan(math.radians(20)))
R10 = 10 / (2 * math.sin(math.radians(100)))
Oq = (5.0, Aq[1] - R10)
F = Frame({"A": Aq, "B": Bq, "C": Cq, "I": Iq, "O": Oq}, 27, (60, 28, 26, 64))
fs = type_scale(F.W, F.H)
verify_figure("q10", angles=[(30, F["B"], F["I"], F["O"]), (100, F["A"], F["B"], F["C"]),
                             (20, F["B"], F["A"], F["I"]), (20, F["B"], F["I"], F["C"])],
              lengths=[(R10, F["O"], F["A"]), (R10, F["O"], F["B"]), (R10, F["O"], F["C"])])
tip10 = bisect_pt(*F["B"], F["I"], F["O"], 34)
S["q10"] = svg(F, "\n".join([
    poly(F["A"], F["B"], F["C"]),
    line(F["B"], F["I"], 1.4), line(F["B"], F["O"], 1.4),
    dot(*F["I"], 2.6), dot(*F["O"], 2.6),
    dot_in(F["B"], F["A"], F["I"], 44, 2.2), dot_in(F["B"], F["I"], F["C"], 50, 2.2),
    arcm(F["B"], F["I"], F["O"], 34),
    leader((tip10[0] - 18, tip10[1] + 40), tip10, arrow=True, gap=9.0),
    txt(tip10[0] - 22, tip10[1] + 54, "30°", fs - 2),
    lab(F["A"], "A", fs, ang=90), lab(F["B"], "B", fs, ang=180),
    lab(F["C"], "C", fs, ang=0), lab(F["I"], "I", fs, ang=90, d=fs * 0.95),
    lab(F["O"], "O", fs, ang=-90, d=fs * 0.95),
]))

# ── q11: 평행사변형, AD=7, BC=(4x-5)(x=3), ∠A=y°(80°), ∠D=100° ───────────
Aq = (0.0, 0.0)
Dq = (7.0, 0.0)
Bq = pol(5.5, -80)
Cq = add(Bq, (7.0, 0.0))
F = Frame({"A": Aq, "B": Bq, "C": Cq, "D": Dq}, 27, (30, 42, 30, 44))
fs = type_scale(F.W, F.H)
verify_figure("q11", lengths=[(7, F["A"], F["D"]), (7, F["B"], F["C"])],
              angles=[(80, F["A"], F["D"], F["B"]), (100, F["D"], F["A"], F["C"])])
S["q11"] = svg(F, "\n".join([
    poly(F["A"], F["B"], F["C"], F["D"]),
    arcm(F["A"], F["D"], F["B"], 14),
    halo_angle(*F["A"], F["D"], F["B"], 28, None, fs - 1, runs=runs(("y", 1), ("°", 0))),
    arcm(F["D"], F["C"], F["A"], 14), halo_angle(*F["D"], F["C"], F["A"], 34, "100°", fs - 2),
    measured(*F["A"], *F["D"], -12, "7 cm", fs - 1),
    measured_runs(*F["B"], *F["C"], 12, runs(("(4", 0), ("x", 1), ("-5) cm", 0)), fs - 1),
    lab(F["A"], "A", fs, ang=180), lab(F["B"], "B", fs, ang=190),
    lab(F["C"], "C", fs, ang=-10), lab(F["D"], "D", fs, ang=0),
]))

# ── q12: 평행사변형 AB=15, AD=20, ∠A·∠D 이등분선 AE·DF, FE=10 ───────────
Bq, Cq = (0.0, 0.0), (20.0, 0.0)
Aq = pol(15.0, 70.0)
Dq = add(Aq, (20.0, 0.0))
Eq, Fq = (15.0, 0.0), (5.0, 0.0)
Gq = isect(Aq, Eq, Dq, Fq)
F = Frame({"A": Aq, "B": Bq, "C": Cq, "D": Dq, "E": Eq, "F": Fq, "G": Gq}, 10.5,
          (58, 44, 28, 30))
fs = type_scale(F.W, F.H)
verify_figure("q12", lengths=[(20, F["A"], F["D"]), (15, F["A"], F["B"]),
                              (15, F["B"], F["E"]), (15, F["F"], F["C"]), (10, F["F"], F["E"])],
              angles=[(55, F["A"], F["B"], F["E"]), (55, F["A"], F["E"], F["D"]),
                      (35, F["D"], F["A"], F["F"]), (35, F["D"], F["F"], F["C"])],
              on_line=[(F["G"], F["A"], F["E"]), (F["G"], F["D"], F["F"])])
S["q12"] = svg(F, "\n".join([
    poly(F["A"], F["B"], F["C"], F["D"]),
    line(F["A"], F["E"], 1.5), line(F["D"], F["F"], 1.5),
    dot_in(F["A"], F["B"], F["E"], 16), dot_in(F["A"], F["E"], F["D"], 16),
    ring_in(F["D"], F["A"], F["F"], 20, 2.2), ring_in(F["D"], F["F"], F["C"], 20, 2.2),
    ring_in(F["F"], F["D"], F["E"], 16, 2.2), dot_in(F["E"], F["A"], F["F"], 14),
    measured(*F["A"], *F["D"], -12, "20 cm", fs - 2),
    measured(*F["B"], *F["A"], -12, "15 cm", fs - 2),
    lab(F["A"], "A", fs, ang=120), lab(F["B"], "B", fs, ang=-120),
    lab(F["C"], "C", fs, ang=-40), lab(F["D"], "D", fs, ang=30),
    lab(F["E"], "E", fs, ang=-90), lab(F["F"], "F", fs, ang=-90),
    lab(F["G"], "G", fs, ang=90, d=fs * 1.0),
]))

# ── q14: 평행사변형 ABCD, 두 대각선의 교점 O ──────────────────────────
Bq, Cq = (0.0, 0.0), (10.0, 0.0)
Aq = pol(7.8, 69.0)
Dq = add(Aq, (10.0, 0.0))
Oq = mid(Aq, Cq)
F = Frame({"A": Aq, "B": Bq, "C": Cq, "D": Dq, "O": Oq}, 21, (26, 28, 26, 28))
fs = type_scale(F.W, F.H)
verify_figure("q14", lengths=[(1, F["O"], F["A"]), (1, F["O"], F["C"]),
                              (dist(Oq, Bq) / dist(Oq, Aq), F["O"], F["B"]),
                              (dist(Oq, Bq) / dist(Oq, Aq), F["O"], F["D"])],
              on_line=[(F["O"], F["A"], F["C"]), (F["O"], F["B"], F["D"])])
S["q14"] = svg(F, "\n".join([
    poly(F["A"], F["B"], F["C"], F["D"]),
    line(F["A"], F["C"], 1.3), line(F["B"], F["D"], 1.3),
    lab(F["A"], "A", fs, ang=150), lab(F["B"], "B", fs, ang=200),
    lab(F["C"], "C", fs, ang=-20), lab(F["D"], "D", fs, ang=20),
    lab(F["O"], "O", fs, ang=-90, d=fs * 1.0),
]))

# ── q15: 마름모, ∠ABO=35°, x=∠AOB(90°), y=∠ADO(35°) ────────────────────
Oq = (0.0, 0.0)
Bq, Dq = (-5.0, 0.0), (5.0, 0.0)
Aq, Cq = (0.0, 5 * math.tan(math.radians(35))), (0.0, -5 * math.tan(math.radians(35)))
F = Frame({"A": Aq, "B": Bq, "C": Cq, "D": Dq, "O": Oq}, 21, (28, 28, 28, 28))
fs = type_scale(F.W, F.H)
verify_figure("q15", angles=[(35, F["B"], F["A"], F["D"]), (35, F["D"], F["B"], F["A"]),
                             (90, F["O"], F["B"], F["A"])],
              lengths=[(1, F["A"], F["B"]), (1, F["B"], F["C"]), (1, F["C"], F["D"]),
                       (1, F["D"], F["A"])])
S["q15"] = svg(F, "\n".join([
    poly(F["A"], F["B"], F["C"], F["D"]),
    line(F["A"], F["C"], 1.4), line(F["B"], F["D"], 1.4),
    arcm(F["B"], F["D"], F["A"], 24), halo_angle(*F["B"], F["D"], F["A"], 44, "35°", fs - 2),
    arcm(F["O"], F["B"], F["A"], 12),
    halo_angle(*F["O"], F["B"], F["A"], 22, None, fs - 1, runs=X_RUN),
    arcm(F["D"], F["A"], F["B"], 22),
    halo_angle(*F["D"], F["A"], F["B"], 40, None, fs - 1, runs=runs(("y", 1))),
    lab(F["A"], "A", fs, ang=90), lab(F["B"], "B", fs, ang=180),
    lab(F["C"], "C", fs, ang=-90), lab(F["D"], "D", fs, ang=0),
    lab(F["O"], "O", fs, ang=-120, d=fs * 1.1),
]))

# ── q16: 직사각형 AD=14, ED=6 → AE=EC=8, CD=√28, AFCE 는 마름모 ─────────
h16 = math.sqrt(28)
Aq, Bq, Cq, Dq = (0.0, h16), (0.0, 0.0), (14.0, 0.0), (14.0, h16)
Eq, Fq = (8.0, h16), (6.0, 0.0)
Oq = mid(Aq, Cq)
F = Frame({"A": Aq, "B": Bq, "C": Cq, "D": Dq, "E": Eq, "F": Fq, "O": Oq}, 17,
          (26, 42, 26, 42))
fs = type_scale(F.W, F.H)
verify_figure("q16", lengths=[(6, F["E"], F["D"]), (14, F["B"], F["C"]),
                              (8, F["A"], F["E"]), (8, F["E"], F["C"]),
                              (8, F["A"], F["F"]), (8, F["F"], F["C"])],
              angles=[(90, F["O"], F["A"], F["F"]), (90, F["B"], F["A"], F["C"])],
              on_line=[(F["O"], F["E"], F["F"]), (F["O"], F["A"], F["C"])])
S["q16"] = svg(F, "\n".join([
    poly(F["A"], F["B"], F["C"], F["D"]),
    line(F["A"], F["C"], 1.4), line(F["E"], F["F"], 1.4),
    line(F["A"], F["F"], 1.4), line(F["E"], F["C"], 1.4),
    rangle_at(*F["O"], F["A"], F["F"], 6),
    ticks(F["A"], F["O"], 2, 4.0), ticks(F["O"], F["C"], 2, 4.0),
    measured(*F["E"], *F["D"], -10, "6 cm", fs - 2),
    measured(*F["B"], *F["C"], 12, "14 cm", fs - 2),
    lab(F["A"], "A", fs, ang=160), lab(F["B"], "B", fs, ang=200),
    lab(F["C"], "C", fs, ang=-20), lab(F["D"], "D", fs, ang=20),
    lab(F["E"], "E", fs, ang=110, d=fs * 0.95), lab(F["F"], "F", fs, ang=-80),
    lab(F["O"], "O", fs, ang=95, d=fs * 1.0),
]))

# ── q17: △ABC 세 변 위 정삼각형 ABD·BCE·ACF, □EDAF ──────────────────────
Bq, Cq = (0.0, 0.0), (8.3, 0.0)
Aq = (2.65, 3.35)
Eq = rot(Cq, Bq, 60)
Dq = rot(Aq, Bq, 60)
Fq = rot(Cq, Aq, 60)
F = Frame({"A": Aq, "B": Bq, "C": Cq, "D": Dq, "E": Eq, "F": Fq}, 24, (26, 28, 26, 28))
fs = type_scale(F.W, F.H)
verify_figure("q17", lengths=[(dist(Aq, Bq), F["A"], F["B"]), (dist(Aq, Bq), F["B"], F["D"]),
                              (dist(Aq, Bq), F["A"], F["D"]),
                              (8.3, F["B"], F["C"]), (8.3, F["B"], F["E"]),
                              (8.3, F["C"], F["E"]),
                              (dist(Aq, Cq), F["A"], F["C"]), (dist(Aq, Cq), F["A"], F["F"]),
                              (dist(Aq, Cq), F["C"], F["F"]),
                              (dist(Aq, Cq), F["D"], F["E"]), (dist(Aq, Bq), F["E"], F["F"])],
              angles=[(60, F["B"], F["C"], F["E"]), (60, F["B"], F["A"], F["D"]),
                      (60, F["A"], F["C"], F["F"])])
S["q17"] = svg(F, "\n".join([
    poly(F["B"], F["C"], F["F"], F["E"], F["D"], w=1.6),
    *[line(F[a], F[b], 1.6) for a, b in ("BE", "EC", "BA", "AF", "DA", "AC")],
    lab(F["A"], "A", fs, ang=95, d=fs * 0.9), lab(F["B"], "B", fs, ang=-120),
    lab(F["C"], "C", fs, ang=-30), lab(F["D"], "D", fs, ang=180),
    lab(F["E"], "E", fs, ang=90), lab(F["F"], "F", fs, ang=20),
]))

# ── s1: ∠C=90°, AB=10·AC=8·BC=6 ───────────────────────────────────────
Cq, Bq, Aq = (0.0, 0.0), (-6.0, 0.0), (0.0, 8.0)
F = Frame({"A": Aq, "B": Bq, "C": Cq}, 20, (60, 30, 60, 42))
fs = type_scale(F.W, F.H)
verify_figure("s1", lengths=[(10, F["A"], F["B"]), (8, F["A"], F["C"]), (6, F["B"], F["C"])],
              angles=[(90, F["C"], F["A"], F["B"])])
S["s1"] = svg(F, "\n".join([
    poly(F["A"], F["B"], F["C"]), rangle_at(*F["C"], F["A"], F["B"], 9),
    measured(*F["B"], *F["A"], 14, "10 cm", fs - 1),
    measured(*F["C"], *F["A"], 14, "8 cm", fs - 1),
    measured(*F["B"], *F["C"], 12, "6 cm", fs - 1),
    lab(F["A"], "A", fs, ang=90), lab(F["B"], "B", fs, ang=190),
    lab(F["C"], "C", fs, ang=-15),
]))

# ── s2: 두 대각선의 길이가 같은 평행사변형(직사각형 모양) ─────────────────
Aq, Bq, Cq, Dq = (0.0, 5.0), (0.0, 0.0), (6.9, 0.0), (6.9, 5.0)
F = Frame({"A": Aq, "B": Bq, "C": Cq, "D": Dq}, 30, (26, 24, 26, 24))
fs = type_scale(F.W, F.H)
verify_figure("s2", lengths=[(1, F["A"], F["C"]), (1, F["B"], F["D"]),
                             (6.9 / 5, F["A"], F["D"]), (6.9 / 5, F["B"], F["C"])],
              angles=[(90, F["B"], F["A"], F["C"])])
S["s2"] = svg(F, "\n".join([
    poly(F["A"], F["B"], F["C"], F["D"]),
    line(F["A"], F["C"], 1.4), line(F["B"], F["D"], 1.4),
    lab(F["A"], "A", fs, ang=160), lab(F["B"], "B", fs, ang=200),
    lab(F["C"], "C", fs, ang=-20), lab(F["D"], "D", fs, ang=20),
]))

# ── s3: 평행사변형이 되는 조건 네 가지 (1)~(4) ────────────────────────
# (1) 두 쌍의 대변의 길이 AD=BC=9, AB=DC=7 (각 71°, 원본 비율)
p1 = {"B": (0.0, 0.0), "C": (9.0, 0.0)}
p1["A"] = pol(7.0, 71.0)
p1["D"] = add(p1["A"], (9.0, 0.0))
F1 = Frame(p1, 17, (72, 40, 64, 40), ox=0, oy=0)
# (2) ∠B=∠D=50°, ∠C=130° (BC=8, AB=6.26)
p2 = {"B": (0.0, 0.0), "C": (8.0, 0.0)}
p2["A"] = pol(6.26, 50.0)
p2["D"] = add(p2["A"], (8.0, 0.0))
F2 = Frame(p2, 17, (60, 40, 36, 40), ox=F1.W, oy=0)
# (3) AD∥BC, AD=BC=4
p3 = {"B": (0.0, 0.0), "C": (4.0, 0.0)}
p3["A"] = pol(2.82, 74.6)
p3["D"] = add(p3["A"], (4.0, 0.0))
F3 = Frame(p3, 34, (72, 40, 64, 40), ox=0, oy=max(F1.H, F2.H))
# (4) 대각선 교점 O — 라벨 OA=OC=3 cm, OB=4 cm, OD=2 cm(원본 인쇄 그대로)
p4 = {"B": (0.0, 0.0), "C": (7.1, 0.0), "A": (-2.35, 5.55), "D": (4.75, 5.55)}
p4["O"] = mid(p4["A"], p4["C"])
F4 = Frame(p4, 21, (60, 40, 60, 40), ox=F1.W, oy=max(F1.H, F2.H))


class _Box:
    pass


FS3 = _Box()
FS3.W = max(F1.W + F2.W, F3.W + F4.W)
FS3.H = max(F1.H, F2.H) + max(F3.H, F4.H)
fs = type_scale(FS3.W / 2, FS3.H / 2)
verify_figure("s3", lengths=[(9, F1["A"], F1["D"]), (9, F1["B"], F1["C"]),
                             (7, F1["A"], F1["B"]), (7, F1["D"], F1["C"])])
verify_figure("s3-각", angles=[(50, F2["B"], F2["A"], F2["C"]),
                               (50, F2["D"], F2["A"], F2["C"]),
                               (130, F2["C"], F2["B"], F2["D"])])
verify_figure("s3-평행", lengths=[(4, F3["A"], F3["D"]), (4, F3["B"], F3["C"])],
              angles=[(0.0001, F3["A"], F3["D"], (F3["A"][0] + 50, F3["A"][1]))])
verify_figure("s3-대각선", lengths=[(3, F4["A"], F4["O"]), (3, F4["O"], F4["C"])],
              on_line=[(F4["O"], F4["A"], F4["C"]), (F4["O"], F4["B"], F4["D"])])


def panel_no(Fx, s):
    return txt(Fx.l - 46, Fx.t + 4, s, fs - 1, anc="start")


mOD = mid(F4["O"], F4["D"])
mOB = mid(F4["O"], F4["B"])
S["s3"] = (f'<svg viewBox="0 0 {FS3.W:.0f} {FS3.H:.0f}" '
           f'xmlns="http://www.w3.org/2000/svg">\n' + "\n".join([
               # (1)
               panel_no(F1, "(1)"),
               poly(F1["A"], F1["B"], F1["C"], F1["D"]),
               measured(*F1["A"], *F1["D"], -11, "9 cm", fs - 2),
               measured(*F1["B"], *F1["C"], 11, "9 cm", fs - 2),
               measured(*F1["B"], *F1["A"], 11, "7 cm", fs - 2),
               measured(*F1["C"], *F1["D"], -11, "7 cm", fs - 2),
               lab(F1["A"], "A", fs, ang=150), lab(F1["B"], "B", fs, ang=-120),
               lab(F1["C"], "C", fs, ang=-30), lab(F1["D"], "D", fs, ang=45),
               # (2)
               panel_no(F2, "(2)"),
               poly(F2["A"], F2["B"], F2["C"], F2["D"]),
               arcm(F2["B"], F2["C"], F2["A"], 14),
               halo_angle(*F2["B"], F2["C"], F2["A"], 30, "50°", fs - 3),
               arcm(F2["D"], F2["A"], F2["C"], 14),
               halo_angle(*F2["D"], F2["A"], F2["C"], 32, "50°", fs - 3),
               arcm(F2["C"], F2["D"], F2["B"], 12),
               halo_angle(*F2["C"], F2["D"], F2["B"], 28, "130°", fs - 3),
               lab(F2["A"], "A", fs, ang=120), lab(F2["B"], "B", fs, ang=190),
               lab(F2["C"], "C", fs, ang=-40), lab(F2["D"], "D", fs, ang=20),
               # (3)
               panel_no(F3, "(3)"),
               poly(F3["A"], F3["B"], F3["C"], F3["D"]),
               par_arrow(F3["A"], F3["D"]), par_arrow(F3["B"], F3["C"]),
               measured(*F3["A"], *F3["D"], -11, "4 cm", fs - 2),
               measured(*F3["B"], *F3["C"], 11, "4 cm", fs - 2),
               lab(F3["A"], "A", fs, ang=150), lab(F3["B"], "B", fs, ang=200),
               lab(F3["C"], "C", fs, ang=-20), lab(F3["D"], "D", fs, ang=20),
               # (4)
               panel_no(F4, "(4)"),
               poly(F4["A"], F4["B"], F4["C"], F4["D"]),
               line(F4["A"], F4["C"], 1.3), line(F4["B"], F4["D"], 1.3),
               measured(*F4["A"], *F4["O"], -9, "3 cm", fs - 3),
               measured(*F4["O"], *F4["C"], -9, "3 cm", fs - 3),
               measured(*F4["O"], *F4["D"], -7, "", fs - 3).split("\n")[0],
               measured(*F4["O"], *F4["B"], -7, "", fs - 3).split("\n")[0],
               leader((F4["D"][0] + 20, mOD[1] + 2), (mOD[0] + 10, mOD[1] + 6), gap=12),
               txt(F4["D"][0] + 30, mOD[1] - 2, "2 cm", fs - 3),
               leader((F4["B"][0] - 38, mOB[1] + 10), (mOB[0] - 9, mOB[1] - 2), gap=16),
               txt(F4["B"][0] - 48, mOB[1] + 18, "4 cm", fs - 3),
               lab(F4["A"], "A", fs, ang=150), lab(F4["B"], "B", fs, ang=210),
               lab(F4["C"], "C", fs, ang=-20), lab(F4["D"], "D", fs, ang=30),
               lab(F4["O"], "O", fs, ang=-95, d=fs * 1.05),
           ]) + "\n</svg>")

# ── s4: 정사각형, 대각선 교점 O, OA=2 cm → 한 변 2√2 ─────────────────────
a4 = 2 * math.sqrt(2)
Aq, Bq, Cq, Dq = (0.0, a4), (0.0, 0.0), (a4, 0.0), (a4, a4)
Oq = mid(Aq, Cq)
F = Frame({"A": Aq, "B": Bq, "C": Cq, "D": Dq, "O": Oq}, 42, (26, 24, 26, 24))
fs = type_scale(F.W, F.H)
verify_figure("s4", lengths=[(2, F["O"], F["A"]), (2, F["O"], F["B"]),
                             (2, F["O"], F["C"]), (2, F["O"], F["D"]),
                             (a4, F["A"], F["B"]), (a4, F["A"], F["D"])],
              angles=[(90, F["B"], F["A"], F["C"]), (45, F["A"], F["B"], F["O"])])
S["s4"] = svg(F, "\n".join([
    poly(F["A"], F["B"], F["C"], F["D"]),
    line(F["A"], F["C"], 1.3), line(F["B"], F["D"], 1.3),
    measured(*F["A"], *F["O"], -12, "2 cm", fs - 2),
    lab(F["A"], "A", fs, ang=150), lab(F["B"], "B", fs, ang=210),
    lab(F["C"], "C", fs, ang=-30), lab(F["D"], "D", fs, ang=30),
    lab(F["O"], "O", fs, ang=-90, d=fs * 1.05),
]))


if __name__ == "__main__":
    from core.figure_generator import _svg_to_png_bytes

    miss = unverified(S)
    if miss:
        raise SystemExit(f"검산 누락(verify_figure 미호출): {miss}")
    bad = 0
    for k, s in S.items():
        issues = lint_svg(s)
        if issues:
            bad += 1
            print(f"{k} LINT 실패:")
            for it in issues:
                print("   -", it)
        png = _svg_to_png_bytes(s, width=int(float(s.split('viewBox="0 0 ')[1].split()[0]) * 4))
        if not png:
            print(k, "PNG 실패")
            bad += 1
            continue
        with open(os.path.join(OUT, f"{k}.png"), "wb") as f:
            f.write(png)
        print(k, "ok" if not issues else "(lint)", "→", os.path.join(OUT, f"{k}.png"))
    raise SystemExit(1 if bad else 0)
