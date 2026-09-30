# -*- coding: utf-8 -*-
"""산격중2 26-2-중간 — 그림 19개, FigureSpec v2(core.figure_scene) 선언형 작도.

원본은 학생 사본 스캔(연필 풀이·색펜 낙서)이라 그림을 캡처하지 않고 **문제 조건에서
좌표를 유도**해 스펙으로 적는다(라벨 배치·선 굵기·조판은 엔진 몫). 조건이 모양을
정하지 않는 부분(자유 변의 길이·기울기)은 원본 인쇄 도형의 비율을 실측해 따른다.
축척은 x·y 등방. 라벨값과 작도가 맞는지는 전부 verify_figure 로 재측정한다.
스펙이 표현 못 하는 인쇄 기호(각 안 •·×·○ 등각 표시, 점 •)만 figure_svg 로 덧그린다.
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
from core.figure_quality import sanitize_svg  # noqa: E402
from core.figure_scene import compile_figure_spec  # noqa: E402
from core.figure_svg import (bisect_pt, dot, isect, leader, lint_svg, meas,  # noqa: E402
                             unverified, verify_figure)

OUT = os.environ.get(
    "FIG_SVG_OUT",
    str(Path(tempfile.gettempdir()) / "exam_figure_svg" / "sangyeok2"),
)
os.makedirs(OUT, exist_ok=True)
S = {}
SPECS = {}
MARK_W = 0.72          # 엔진 mark_width 와 같은 굵기(각 표시)


class Frame:
    """수학 좌표(y 위) → 화면 좌표(y 아래), **등방 척도 s**."""

    def __init__(self, pts, s, ox=0.0, oy=0.0):
        xs = [p[0] for p in pts.values()]
        ys = [p[1] for p in pts.values()]
        self.minx, self.maxy, self.s, self.ox, self.oy = min(xs), max(ys), s, ox, oy
        self.m = {k: self.p(v) for k, v in pts.items()}

    def p(self, q):
        return (self.ox + (q[0] - self.minx) * self.s, self.oy + (self.maxy - q[1]) * self.s)

    def __getitem__(self, k):
        return self.m[k]


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


# ── 덧그림(스펙에 없는 인쇄 기호) ──────────────────────────────────────────
def dot_in(v, p1, p2, d=16, r=1.9):
    return dot(*bisect_pt(*v, p1, p2, d), r)


def ring_in(v, p1, p2, d=16, r=2.4):
    x, y = bisect_pt(*v, p1, p2, d)
    return (f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r}" fill="none" '
            f'stroke="#111111" stroke-width="{MARK_W}"/>')


def cross_in(v, p1, p2, d=18, s=3.0):
    x, y = bisect_pt(*v, p1, p2, d)
    return (f'<line x1="{x - s:.2f}" y1="{y - s:.2f}" x2="{x + s:.2f}" y2="{y + s:.2f}" '
            f'stroke="#111111" stroke-width="0.9"/>'
            f'<line x1="{x - s:.2f}" y1="{y + s:.2f}" x2="{x + s:.2f}" y2="{y - s:.2f}" '
            f'stroke="#111111" stroke-width="0.9"/>')


ENGINE_FONT = "Cambria Math, HancomEQN, Times New Roman, serif"


def etxt(x, y, s, fs=16.8, anc="middle"):
    return (f'<text x="{x:.2f}" y="{y:.2f}" font-family="{ENGINE_FONT}" font-size="{fs}" '
            f'text-anchor="{anc}" fill="#111111">{s}</text>')


def itxt(x, y, s, fs=16.8):
    """이탤릭 변수 라벨(엔진 조판과 같은 글꼴) — 좁은 각에서 엔진 자리 대신 쓴다."""
    return (f'<text x="{x:.2f}" y="{y + 0.35 * fs:.2f}" font-family="Cambria, Times New Roman, serif" '
            f'font-style="italic" font-size="{fs}" text-anchor="middle" fill="#111111" '
            f'paint-order="stroke" stroke="#ffffff" stroke-width="3.15">{s}</text>')


def seg_spec(item):
    """"AB" → ["A","B"] · ("AB", {"ticks":2}) → {"points":[..], "ticks":2} ·
    ("AO", "A", "O", {...}) 처럼 이름과 끝점을 따로 줄 수도 있다."""
    if isinstance(item, str):
        return f"s{item}", [item[0], item[1]] if len(item) == 2 else item
    if len(item) == 2:
        name, opts = item
        return f"s{name}", {"points": [name[0], name[1]], **opts}
    name, p, q, opts = item
    return f"s{name}", {"points": [p, q], **opts}


def build(key, F, segs, angles=None, dims=None, labels=None, extra=None, dots=(),
          points=None, pos=None):
    """스펙 작성 → 엔진 렌더 → 덧그림 → sanitize. S[key] 에 저장."""
    names = points or list(F.m)
    spec = {
        "version": 2,
        "points": {n: [round(F[n][0], 3), round(F[n][1], 3)] for n in names},
        "segments": dict(seg_spec(s) for s in segs),
    }
    if angles:
        spec["angles"] = angles
    if dims:
        spec["dimensions"] = dims
    spec["labels"] = labels if labels is not None else {n: n for n in names if len(n) == 1}
    for n, where in (pos or {}).items():
        spec["labels"][n] = ({"text": n, **where} if isinstance(where, dict)
                             else {"text": n, "position": where})
    SPECS[key] = spec
    scene = compile_figure_spec(spec)
    svg = scene.render_svg()
    tx, ty = scene.resolve().translation

    def T(n):
        return (F[n][0] + tx, F[n][1] + ty)

    more = [dot(*T(n), 2.1) for n in dots]
    if extra:
        more += extra(T)
    if more:
        svg = svg.replace("</svg>", "\n".join(more) + "\n</svg>")
    S[key] = sanitize_svg(svg)


# ── q1: AB=AC 이등변삼각형, ∠A=40°, B 에서의 외각 x ─────────────────────
F = Frame({"A": (0, 0), "B": (10, 0), "C": pol(10, 40), "X": (13.3, 0)}, 19)
verify_figure("q1", lengths=[(10, F["A"], F["B"]), (10, F["A"], F["C"])],
              angles=[(40, F["A"], F["B"], F["C"]), (110, F["B"], F["C"], F["X"])])
build("q1", F, [("AB", {"ticks": 2}), ("AC", {"ticks": 2}), "BC", "BX"],
      angles={"angA": {"vertex": "A", "points": ["B", "C"], "label": "40°"},
              "angX": {"vertex": "B", "points": ["X", "C"], "label": "x", "radius": 20}},
      labels={"A": "A", "B": "B", "C": "C"})

# ── q2: AB=AC, BC=DC, ∠ACD=∠DCE=52°, x=∠ABD(=50°) ─────────────────────
q2 = {"B": (0, 0), "C": (2, 0), "A": (1, math.tan(math.radians(76)))}
q2["D"] = add(q2["C"], pol(2, 52))
q2["E"], q2["X"] = (4.1, 0), (4.6, 0)
F = Frame(q2, 52)
ab = dist(q2["A"], q2["B"])
verify_figure("q2", lengths=[(ab, F["A"], F["B"]), (ab, F["A"], F["C"]),
                             (2, F["B"], F["C"]), (2, F["C"], F["D"])],
              angles=[(52, F["C"], F["A"], F["D"]), (52, F["C"], F["D"], F["E"]),
                      (50, F["B"], F["A"], F["D"])])
build("q2", F, [("AB", {"ticks": 2}), ("AC", {"ticks": 2}), ("BC", {"ticks": 1}),
                ("CD", {"ticks": 1}), "BD", "CE", "EX"],
      angles={"angDCE": {"vertex": "C", "points": ["D", "E"], "label": "52°"},
              "angx": {"vertex": "B", "points": ["D", "A"], "label": "x"}},
      labels={k: k for k in "ABCDE"}, dots=("E",),
      extra=lambda T: [dot_in(T("C"), T("A"), T("D"), 11),
                       dot_in(T("C"), T("D"), T("E"), 11)])

# ── q3: ∠B=∠C, AC=(x+6) cm, AB=(2x-4) cm (x=10 → 16) ──────────────────
half = math.degrees(math.asin(6.6 / 16))
F = Frame({"A": (0, 0), "C": pol(16, half), "B": pol(16, -half)}, 12)
verify_figure("q3", lengths=[(16, F["A"], F["B"]), (16, F["A"], F["C"])],
              angles=[(90 - half, F["B"], F["A"], F["C"]), (90 - half, F["C"], F["A"], F["B"])])
build("q3", F, ["AB", "BC", "CA"],
      dims={"dimAC": {"points": ["A", "C"], "label": "(x+6) cm"},
            "dimAB": {"points": ["A", "B"], "label": "(2x-4) cm"}},
      extra=lambda T: [dot_in(T("B"), T("A"), T("C"), 12),
                       dot_in(T("C"), T("A"), T("B"), 12)])

# ── q4: 두 직각삼각형 ABC(∠C=90°) · DEF(∠F=90°) ────────────────────────
F = Frame({"A": (0, 10.2), "B": (-6, 0), "C": (0, 0),
           "D": (2.4, 10.2), "E": (8.4, 0), "F": (2.4, 0)}, 15)
verify_figure("q4", lengths=[(6, F["B"], F["C"]), (6, F["E"], F["F"]),
                             (10.2, F["A"], F["C"]), (10.2, F["D"], F["F"])],
              angles=[(90, F["C"], F["A"], F["B"]), (90, F["F"], F["D"], F["E"])])
build("q4", F, ["AB", "BC", "CA", "DE", "EF", "FD"],
      angles={"angC": {"vertex": "C", "points": ["A", "B"], "right": True},
              "angF": {"vertex": "F", "points": ["D", "E"], "right": True}},
      pos={"A": "N", "D": "N"})

# ── q5: ∠C=90°, AB=20·AC=12·BC=16, ∠A 이등분선 AD, DC=6 ────────────────
F = Frame({"A": (16, 12), "B": (0, 0), "C": (16, 0), "D": (10, 0)}, 11.5)
hA = math.degrees(math.atan2(16, 12)) / 2
verify_figure("q5", lengths=[(20, F["A"], F["B"]), (12, F["A"], F["C"]),
                             (6, F["D"], F["C"]), (16, F["B"], F["C"])],
              angles=[(hA, F["A"], F["B"], F["D"]), (hA, F["A"], F["D"], F["C"]),
                      (90, F["C"], F["A"], F["B"])])
build("q5", F, ["AB", "BD", "DC", "CA", "AD"],
      angles={"angC": {"vertex": "C", "points": ["A", "D"], "right": True}},
      dims={"dimAB": {"points": ["B", "A"], "label": "20 cm", "side": "auto"},
            "dimAC": {"points": ["C", "A"], "label": "12 cm", "side": "auto"},
            "dimDC": {"points": ["D", "C"], "label": "6 cm", "side": "auto"}},
      extra=lambda T: [dot_in(T("A"), T("B"), T("D"), 22),
                       dot_in(T("A"), T("D"), T("C"), 22)])

# ── q6: 외심 O, ∠OBC=26°, ∠OCA=40°, x=∠OAB(=24°) ──────────────────────
F = Frame({"A": pol(5, 74), "B": pol(5, 206), "C": pol(5, 334), "O": (0, 0)}, 27)
verify_figure("q6", angles=[(26, F["B"], F["O"], F["C"]), (40, F["C"], F["O"], F["A"]),
                            (24, F["A"], F["B"], F["O"])],
              lengths=[(5, F["O"], F["A"]), (5, F["O"], F["B"]), (5, F["O"], F["C"])])
build("q6", F, ["AB", "BC", "CA", "OA", "OB", "OC"],
      angles={"angB": {"vertex": "B", "points": ["C", "O"], "label": "26°"},
              "angC": {"vertex": "C", "points": ["O", "A"], "label": "40°"},
              "angA": {"vertex": "A", "points": ["B", "O"], "radius": 26}},
      dots=("O",), pos={"O": "S"},
      extra=lambda T: [itxt(*bisect_pt(*T("A"), T("B"), T("O"), 44), "x")])

# ── q7: 외심 O, OD⊥AC, AD=6 → AC=12, 둘레 30 → R=9 ─────────────────────
R7 = 9.0
hd = math.degrees(math.asin(6 / R7))
q7 = {"A": pol(R7, 16 + hd), "C": pol(R7, 16 - hd), "B": pol(R7, 205), "O": (0, 0)}
q7["D"] = mid(q7["A"], q7["C"])
F = Frame(q7, 13.5)
verify_figure("q7", lengths=[(6, F["A"], F["D"]), (6, F["D"], F["C"]),
                             (9, F["O"], F["A"]), (9, F["O"], F["C"]), (9, F["O"], F["B"])],
              angles=[(90, F["D"], F["O"], F["A"])])
build("q7", F, ["AB", "BC", "AD", "DC", "OA", "OC", "OD"],
      angles={"angD": {"vertex": "D", "points": ["O", "A"], "right": True}},
      dims={"dimAD": {"points": ["A", "D"], "label": "6 cm", "side": "auto"}},
      dots=("O",))

# ── q8: 내심 I, 수선의 발 D(AB)·E(BC)·F(CA) ───────────────────────────
A8, B8, C8 = (530 / 3.4, -130 / 3.4), (175 / 3.4, -755 / 3.4), (1060 / 3.4, -740 / 3.4)
I8 = incenter(A8, B8, C8)
F = Frame({"A": A8, "B": B8, "C": C8, "I": I8, "D": foot(I8, A8, B8),
           "E": foot(I8, B8, C8), "F": foot(I8, C8, A8)}, 1.0)
cosA = ((B8[0] - A8[0]) * (C8[0] - A8[0]) + (B8[1] - A8[1]) * (C8[1] - A8[1])) \
    / (dist(A8, B8) * dist(A8, C8))
hA8 = math.degrees(math.acos(cosA)) / 2
verify_figure("q8", angles=[(90, F["D"], F["I"], F["A"]), (90, F["E"], F["I"], F["C"]),
                            (90, F["F"], F["I"], F["C"]),
                            (hA8, F["A"], F["B"], F["I"]), (hA8, F["A"], F["I"], F["C"])],
              on_line=[(F["D"], F["A"], F["B"]), (F["E"], F["B"], F["C"]),
                       (F["F"], F["C"], F["A"])])
build("q8", F, ["AD", "DB", "BE", "EC", "CF", "FA", "IA", "IB", "IC", "ID", "IE", "IF"],
      angles={"angD": {"vertex": "D", "points": ["I", "B"], "right": True},
              "angE": {"vertex": "E", "points": ["I", "C"], "right": True},
              "angF": {"vertex": "F", "points": ["I", "A"], "right": True}},
      dots=("I",), pos={"I": "SW"},
      extra=lambda T: [cross_in(T("A"), T("B"), T("I"), 30),
                       cross_in(T("A"), T("I"), T("C"), 30),
                       dot_in(T("B"), T("A"), T("I"), 30, 2.3),
                       dot_in(T("B"), T("I"), T("C"), 30, 2.3)])

# ── q9: 내심 I, ∠IBC=30°, ∠ICB=25° → x=70° ────────────────────────────
B9, C9 = (0, 0), (10, 0)
A9 = isect(B9, pol(1, 60), C9, add(C9, pol(1, 130)))
F = Frame({"A": A9, "B": B9, "C": C9, "I": incenter(A9, B9, C9)}, 24)
verify_figure("q9", angles=[(30, F["B"], F["C"], F["I"]), (25, F["C"], F["I"], F["B"]),
                            (70, F["A"], F["B"], F["C"]), (30, F["B"], F["A"], F["I"])])
build("q9", F, ["AB", "BC", "CA", "IB", "IC"],
      angles={"angB": {"vertex": "B", "points": ["C", "I"], "label": "30°"},
              "angC": {"vertex": "C", "points": ["I", "B"], "label": "25°"},
              "angA": {"vertex": "A", "points": ["B", "C"], "label": "x"}},
      dots=("I",))

# ── q10: ∠A=100°(정답 ①) 이등변, 내심 I, 외심 O, ∠IBO=30° ───────────────
R10 = 10 / (2 * math.sin(math.radians(100)))
A10 = (5, 5 * math.tan(math.radians(40)))
F = Frame({"A": A10, "B": (0, 0), "C": (10, 0), "I": (5, 5 * math.tan(math.radians(20))),
           "O": (5, A10[1] - R10)}, 27)
verify_figure("q10", angles=[(30, F["B"], F["I"], F["O"]), (100, F["A"], F["B"], F["C"]),
                             (20, F["B"], F["A"], F["I"]), (20, F["B"], F["I"], F["C"])],
              lengths=[(R10, F["O"], F["A"]), (R10, F["O"], F["B"]), (R10, F["O"], F["C"])])
F.m["Z"] = (F["B"][0] + 22, F["B"][1] + 72)      # 30° 지시선 라벨 자리(캔버스 확보용)
build("q10", F, ["AB", "BC", "CA", "BI", "BO"], labels={k: k for k in "ABCIO"},
      angles={"angIBO": {"vertex": "B", "points": ["I", "O"], "radius": 30}},
      dots=("I", "O"),
      extra=lambda T: [dot_in(T("B"), T("A"), T("I"), 44, 2.1),
                       dot_in(T("B"), T("I"), T("C"), 52, 2.1),
                       leader((T("B")[0] + 22, T("B")[1] + 50),
                              bisect_pt(*T("B"), T("I"), T("O"), 30.5), gap=8.0, w=0.72),
                       etxt(T("B")[0] + 22, T("B")[1] + 64, "30°")])

# ── q11: 평행사변형, AD=7, BC=(4x-5)(x=3), ∠A=y°(80°), ∠D=100° ───────────
q11 = {"A": (0, 0), "D": (7, 0), "B": pol(5.5, -80)}
q11["C"] = add(q11["B"], (7, 0))
F = Frame(q11, 27)
verify_figure("q11", lengths=[(7, F["A"], F["D"]), (7, F["B"], F["C"])],
              angles=[(80, F["A"], F["D"], F["B"]), (100, F["D"], F["A"], F["C"])])
build("q11", F, ["AB", "BC", "CD", "DA"],
      angles={"angA": {"vertex": "A", "points": ["D", "B"], "label": "y°"},
              "angD": {"vertex": "D", "points": ["C", "A"], "label": "100°"}},
      dims={"dimAD": {"points": ["A", "D"], "label": "7 cm", "side": "auto"},
            "dimBC": {"points": ["B", "C"], "label": "(4x-5) cm", "side": "auto"}})

# ── q12: 평행사변형 AB=15, AD=20, ∠A·∠D 이등분선 AE·DF, FE=10 ───────────
q12 = {"B": (0, 0), "C": (20, 0), "A": pol(15, 70), "E": (15, 0), "F": (5, 0)}
q12["D"] = add(q12["A"], (20, 0))
q12["G"] = isect(q12["A"], q12["E"], q12["D"], q12["F"])
F = Frame(q12, 10.5)
verify_figure("q12", lengths=[(20, F["A"], F["D"]), (15, F["A"], F["B"]),
                              (15, F["B"], F["E"]), (15, F["F"], F["C"]), (10, F["F"], F["E"])],
              angles=[(55, F["A"], F["B"], F["E"]), (55, F["A"], F["E"], F["D"]),
                      (35, F["D"], F["A"], F["F"]), (35, F["D"], F["F"], F["C"])],
              on_line=[(F["G"], F["A"], F["E"]), (F["G"], F["D"], F["F"])])
build("q12", F, ["AB", "BF", "FE", "EC", "CD", "DA", "AG", "GE", "DG", "GF"],
      dims={"dimAD": {"points": ["A", "D"], "label": "20 cm", "side": "auto"},
            "dimAB": {"points": ["B", "A"], "label": "15 cm", "side": "auto"}},
      extra=lambda T: [dot_in(T("A"), T("B"), T("E"), 15), dot_in(T("A"), T("E"), T("D"), 15),
                       ring_in(T("D"), T("A"), T("F"), 19, 2.1),
                       ring_in(T("D"), T("F"), T("C"), 19, 2.1),
                       ring_in(T("F"), T("G"), T("E"), 15, 2.1),
                       dot_in(T("E"), T("G"), T("F"), 13)])

# ── q14: 평행사변형 ABCD, 두 대각선의 교점 O ──────────────────────────
q14 = {"B": (0, 0), "C": (10, 0), "A": pol(7.8, 69)}
q14["D"] = add(q14["A"], (10, 0))
q14["O"] = mid(q14["A"], q14["C"])
F = Frame(q14, 21)
rb = dist(q14["O"], q14["B"])
verify_figure("q14", lengths=[(1, F["O"], F["A"]), (1, F["O"], F["C"])],
              on_line=[(F["O"], F["A"], F["C"]), (F["O"], F["B"], F["D"])])
verify_figure("q14-BD", lengths=[(rb, F["O"], F["B"]), (rb, F["O"], F["D"])])
build("q14", F, ["AB", "BC", "CD", "DA", "AO", "OC", "BO", "OD"])

# ── q15: 마름모, ∠ABO=35°, x=∠AOB(90°), y=∠ADO(35°) ────────────────────
t35 = 5 * math.tan(math.radians(35))
F = Frame({"A": (0, t35), "B": (-5, 0), "C": (0, -t35), "D": (5, 0), "O": (0, 0)}, 21)
verify_figure("q15", angles=[(35, F["B"], F["A"], F["D"]), (35, F["D"], F["B"], F["A"]),
                             (90, F["O"], F["B"], F["A"])],
              lengths=[(1, F["A"], F["B"]), (1, F["B"], F["C"]), (1, F["C"], F["D"]),
                       (1, F["D"], F["A"])])
build("q15", F, ["AB", "BC", "CD", "DA", "AO", "OC", "BO", "OD"],
      angles={"angB": {"vertex": "B", "points": ["O", "A"], "label": "35°"},
              "angO": {"vertex": "O", "points": ["B", "A"], "label": "x", "radius": 12},
              "angD": {"vertex": "D", "points": ["A", "O"], "label": "y"}},
      pos={"O": "SW"})

# ── q16: 직사각형 AD=14, ED=6 → AE=EC=8, CD=√28, AFCE 는 마름모 ─────────
h16 = math.sqrt(28)
q16 = {"A": (0, h16), "B": (0, 0), "C": (14, 0), "D": (14, h16), "E": (8, h16), "F": (6, 0)}
q16["O"] = mid(q16["A"], q16["C"])
F = Frame(q16, 17)
verify_figure("q16", lengths=[(6, F["E"], F["D"]), (14, F["B"], F["C"]),
                              (8, F["A"], F["E"]), (8, F["E"], F["C"]),
                              (8, F["A"], F["F"]), (8, F["F"], F["C"])],
              angles=[(90, F["O"], F["A"], F["F"]), (90, F["B"], F["A"], F["C"])],
              on_line=[(F["O"], F["E"], F["F"]), (F["O"], F["A"], F["C"])])
build("q16", F, ["AE", "ED", "DC", "BC", "BA", ("AO", {"ticks": 2}),
                 ("OC", {"ticks": 2}), "EO", "OF", "AF", "EC"],
      angles={"angO": {"vertex": "O", "points": ["A", "F"], "right": True}},
      dims={"dimED": {"points": ["E", "D"], "label": "6 cm", "side": "auto"},
            "dimBC": {"points": ["B", "C"], "label": "14 cm", "side": "left",
                      "offset": 30}},
      pos={"O": "NW", "E": "N", "F": "SW"})

# ── q17: △ABC 세 변 위 정삼각형 ABD·BCE·ACF, □EDAF ──────────────────────
B17, C17, A17 = (0, 0), (8.3, 0), (2.65, 3.35)
F = Frame({"A": A17, "B": B17, "C": C17, "D": rot(A17, B17, 60), "E": rot(C17, B17, 60),
           "F": rot(C17, A17, 60)}, 24)
ab17, ac17 = dist(A17, B17), dist(A17, C17)
verify_figure("q17", lengths=[(ab17, F["A"], F["B"]), (ab17, F["B"], F["D"]),
                              (ab17, F["A"], F["D"]), (8.3, F["B"], F["C"]),
                              (8.3, F["B"], F["E"]), (8.3, F["C"], F["E"]),
                              (ac17, F["A"], F["C"]), (ac17, F["A"], F["F"]),
                              (ac17, F["C"], F["F"]), (ac17, F["D"], F["E"]),
                              (ab17, F["E"], F["F"])],
              angles=[(60, F["B"], F["C"], F["E"]), (60, F["B"], F["A"], F["D"]),
                      (60, F["A"], F["C"], F["F"])])
build("q17", F, ["BC", "CF", "FE", "ED", "DB", "BE", "EC", "BA", "AF", "DA", "AC"])

# ── s1: ∠C=90°, AB=10·AC=8·BC=6 ───────────────────────────────────────
F = Frame({"A": (0, 8), "B": (-6, 0), "C": (0, 0)}, 23)
verify_figure("s1", lengths=[(10, F["A"], F["B"]), (8, F["A"], F["C"]), (6, F["B"], F["C"])],
              angles=[(90, F["C"], F["A"], F["B"])])
build("s1", F, ["AB", "BC", "CA"],
      angles={"angC": {"vertex": "C", "points": ["A", "B"], "right": True}},
      dims={"dimAB": {"points": ["B", "A"], "label": "10 cm", "side": "auto"},
            "dimAC": {"points": ["C", "A"], "label": "8 cm", "side": "auto"},
            "dimBC": {"points": ["B", "C"], "label": "6 cm", "side": "auto"}})

# ── s2: 두 대각선의 길이가 같은 평행사변형(직사각형 모양) ─────────────────
F = Frame({"A": (0, 5), "B": (0, 0), "C": (6.9, 0), "D": (6.9, 5)}, 30)
dg2 = math.hypot(6.9, 5)
verify_figure("s2", lengths=[(dg2, F["A"], F["C"]), (dg2, F["B"], F["D"]),
                             (6.9, F["A"], F["D"]), (6.9, F["B"], F["C"])],
              angles=[(90, F["B"], F["A"], F["C"])])
build("s2", F, ["AB", "BC", "CD", "DA", "AC", "BD"])

# ── s3: 평행사변형이 되는 조건 네 가지 (1)~(4) ────────────────────────
p1 = {"B": (0, 0), "C": (9, 0), "A": pol(7, 109)}   # 원본: B 가 A 보다 오른쪽(\ 기울기)
p1["D"] = add(p1["A"], (9, 0))
p2 = {"B": (0, 0), "C": (8, 0), "A": pol(6.26, 50)}
p2["D"] = add(p2["A"], (8, 0))
p3 = {"B": (0, 0), "C": (4, 0), "A": pol(2.82, 74.6)}
p3["D"] = add(p3["A"], (4, 0))
p4 = {"B": (0, 0), "C": (7.1, 0), "A": (-2.35, 5.55), "D": (4.75, 5.55)}
p4["O"] = mid(p4["A"], p4["C"])
F1 = Frame(p1, 17, 40, 20)
F2 = Frame(p2, 17, 330, 20)
F3 = Frame(p3, 34, 40, 225)
F4 = Frame(p4, 24, 360, 225)
verify_figure("s3", lengths=[(9, F1["A"], F1["D"]), (9, F1["B"], F1["C"]),
                             (7, F1["A"], F1["B"]), (7, F1["D"], F1["C"])])
verify_figure("s3-각", angles=[(50, F2["B"], F2["C"], F2["A"]),
                               (50, F2["D"], F2["A"], F2["C"]),
                               (130, F2["C"], F2["B"], F2["D"])])
verify_figure("s3-평행", lengths=[(4, F3["A"], F3["D"]), (4, F3["B"], F3["C"])],
              on_line=[((F3["A"][0] + 30, F3["A"][1]), F3["A"], F3["D"])])
# (4) 라벨 OA=OC=3 cm 만 작도와 대조한다 — OB=4 cm·OD=2 cm 는 원본 인쇄값
#     그대로 옮겼지만 서로 달라 평행사변형과 모순이다(원본 오식 의심, meta 기록).
verify_figure("s3-대각선", lengths=[(3, F4["A"], F4["O"]), (3, F4["O"], F4["C"])],
              on_line=[(F4["O"], F4["A"], F4["C"]), (F4["O"], F4["B"], F4["D"])])


class _Merged:
    def __init__(self, *frames):
        self.m = {}
        for i, f in enumerate(frames, 1):
            for k, v in f.m.items():
                self.m[f"{k}{i}"] = v
        self.m["n1"] = (F1.ox - 40, F1.oy + 2)
        self.m["n2"] = (F2.ox - 40, F2.oy + 2)
        self.m["n3"] = (F3.ox - 40, F3.oy + 2)
        self.m["n4"] = (F4.ox - 40, F4.oy + 2)

    def __getitem__(self, k):
        return self.m[k]


M = _Merged(F1, F2, F3, F4)
lab3 = {f"{c}{i}": c for i in (1, 2, 3, 4) for c in "ABCD"}
lab3["O4"] = {"text": "O", "position": "S"}
for i in (1, 2, 3, 4):
    lab3[f"n{i}"] = {"text": f"({i})", "dx": 0, "dy": 0}


def pg(i):
    return [(f"AB{i}", f"A{i}", f"B{i}", {}), (f"BC{i}", f"B{i}", f"C{i}", {}),
            (f"CD{i}", f"C{i}", f"D{i}", {}), (f"DA{i}", f"D{i}", f"A{i}", {})]


segs3 = pg(1) + pg(2) + [
    ("AB3", "A3", "B3", {}), ("BC3", "B3", "C3", {"parallel": 1}),
    ("CD3", "C3", "D3", {}), ("AD3", "A3", "D3", {"parallel": 1}),
] + pg(4) + [("AO4", "A4", "O4", {}), ("OC4", "O4", "C4", {}),
             ("BO4", "B4", "O4", {}), ("OD4", "O4", "D4", {})]
def s3_extra(T):
    """OD=2 cm·OB=4 cm — 원본처럼 치수 점선 + 바깥 라벨에서 지시선 화살표."""
    O, D, B = T("O4"), T("D4"), T("B4")
    mOD = ((O[0] + D[0]) / 2, (O[1] + D[1]) / 2)
    mOB = ((O[0] + B[0]) / 2, (O[1] + B[1]) / 2)
    return [meas(*O, *D, 9), meas(*O, *B, 9),
            leader((D[0] + 24, mOD[1] + 4), (mOD[0] + 9, mOD[1] + 6), gap=4.0, w=0.72),
            etxt(D[0] + 40, mOD[1] + 2, "2 cm"),
            leader((B[0] - 30, mOB[1] - 2), (mOB[0] - 9, mOB[1] - 6), gap=4.0, w=0.72),
            etxt(B[0] - 44, mOB[1] + 10, "4 cm")]


build("s3", M, segs3,
      angles={"angB2": {"vertex": "B2", "points": ["C2", "A2"], "label": "50°"},
              "angD2": {"vertex": "D2", "points": ["A2", "C2"], "label": "50°"},
              "angC2": {"vertex": "C2", "points": ["D2", "B2"], "label": "130°"}},
      dims={"dimAD1": {"points": ["A1", "D1"], "label": "9 cm", "side": "right"},
            "dimBC1": {"points": ["B1", "C1"], "label": "9 cm", "side": "left"},
            "dimAB1": {"points": ["B1", "A1"], "label": "7 cm", "side": "right"},
            "dimDC1": {"points": ["C1", "D1"], "label": "7 cm", "side": "left"},
            "dimAD3": {"points": ["A3", "D3"], "label": "4 cm", "side": "right"},
            "dimBC3": {"points": ["B3", "C3"], "label": "4 cm", "side": "left"},
            "dimAO4": {"points": ["A4", "O4"], "label": "3 cm", "side": "right"},
            "dimOC4": {"points": ["O4", "C4"], "label": "3 cm", "side": "left"},
            },
      labels=lab3, extra=s3_extra)

# ── s4: 정사각형, 대각선 교점 O, OA=2 cm → 한 변 2√2 ─────────────────────
a4 = 2 * math.sqrt(2)
F = Frame({"A": (0, a4), "B": (0, 0), "C": (a4, 0), "D": (a4, a4), "O": (a4 / 2, a4 / 2)}, 62)
verify_figure("s4", lengths=[(2, F["O"], F["A"]), (2, F["O"], F["B"]),
                             (2, F["O"], F["C"]), (2, F["O"], F["D"]),
                             (a4, F["A"], F["B"]), (a4, F["A"], F["D"])],
              angles=[(90, F["B"], F["A"], F["C"]), (45, F["A"], F["B"], F["O"])])
build("s4", F, ["AB", "BC", "CD", "DA", "AO", "OC", "BO", "OD"],
      dims={"dimAO": {"points": ["A", "O"], "label": "2 cm", "side": "auto"}},
      pos={"O": "S"})


if __name__ == "__main__":
    from core.figure_generator import _svg_to_png_bytes

    miss = unverified(S)
    if miss:
        raise SystemExit(f"검산 누락(verify_figure 미호출): {miss}")
    bad = 0
    for k, s in S.items():
        issues = lint_svg(s)
        if issues:
            print(f"{k} LINT:")
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
