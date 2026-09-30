# -*- coding: utf-8 -*-
"""침산중3 26-2-중간 — 그림 13개 작도(조건값에서 유도한 좌표, 눈대중 금지).

기하 = FigureSpec v2(core.figure_scene) · 그래프 = graph-1(scripts/figure/graph_scene)
· 자전거 길(s4)만 core.figure_svg 프리미티브. 최종 SVG 는 figure_quality.sanitize_svg.

  q1  직각삼각형 ABC(∠B=90°), BC=28, cosC=4/5 → AB=21, AC=35
  q3  반지름 1 부채꼴, ∠A=38°, CD⊥AB
  q4  ∠B=90°, DC=9, CE=6 → DE=3√5, tanC=√5/2 (BD 는 원본 비율 ≈1.7)
  q6  ∠C=90°, CD⊥AB (원본 비율 BC/AC≈0.56)
  q7  AB=6, BC=8, CE=4, ∠B=60°, AC∥DE (D 높이는 원본 비율 1.21·A)
  q9  등변사다리꼴 AD=4, BC=8, AB=5 → 높이 √21
  q10 BH=6, CH=3, AH⊥BC (AH=7 은 원본 비율)
  q13 y=x², y=x²−5x, 축 l: x=5/2, 두 곡선 사이 0≤x≤5/2 색칠(넓이 125/8)
  q15 y=ax²+bx+3 (a>0, b<0) — 대표 (5/9)(x−3)²−2
  q16 y=−x²+4x, 정사각형 반변 t=√5−1
  s1  꼭짓점 (2,6), x절편 5 → y=−(2/3)(x−2)²+6
  s3  ∠A=90°·∠ACB=45°, ∠C=90°·∠BDC=60°, CD=10 → BC=10√3
  s4  AB=100 m, ∠A=30°, 외각 75° → ∠ABC=105°, ∠C=45°
"""
import math
import re
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (str(ROOT), str(ROOT / "scripts" / "figure")):
    if p not in sys.path:
        sys.path.insert(0, p)
sys.stdout.reconfigure(encoding="utf-8")
from core.figure_quality import sanitize_svg  # noqa: E402
from core.figure_scene import render_figure_spec  # noqa: E402
from core.figure_svg import (angle_arc, dot, line, lint_svg, measured,  # noqa: E402
                             ray_angle, runs_text, txt, unverified, verify_figure, halo_angle)
from graph_scene import render_graph  # noqa: E402

OUT = os.environ.get(
    "FIG_SVG_OUT",
    str(Path(tempfile.gettempdir()) / "exam_figure_svg" / "chimsan3"),
)
os.makedirs(OUT, exist_ok=True)
S = {}
CHECKS = []
R3, R5, R21 = math.sqrt(3), math.sqrt(5), math.sqrt(21)


def _check(name, cond, msg):
    CHECKS.append(name)
    if not cond:
        raise SystemExit(f"[{name}] 작도 검산 실패: {msg}")


def P(x, y):
    return [round(x, 3), round(y, 3)]


def spec(**kw):
    d = {"version": 2}
    d.update(kw)
    return sanitize_svg(render_figure_spec(d))


GPAD = 48  # graph_scene 여백(엔진 고정값)


def graph(xRange, yRange, width, labels=(), fs=19, **kw):
    """graph-1 렌더 + 등방 크기 + 라벨 조판.

    엔진의 화면 매핑은 pad 48 을 뺀 안쪽 폭/높이로 비례하므로, **등방은 W/H 가 아니라
    (W-96)/xspan == (H-96)/yspan** 이다. graph-1 의 $…$ 조판은 웹(MathJax) 몫이라
    여기선 라벨을 figure_svg.runs_text(변수 이탤릭·숫자 정자)로 직접 찍는다.
    """
    xs, ys = xRange[1] - xRange[0], yRange[1] - yRange[0]
    height = GPAD * 2 + ys * (width - 2 * GPAD) / xs
    d = {"version": "graph-1", "xRange": xRange, "yRange": yRange,
         "width": width, "height": round(height, 3)}
    d.update(kw)
    svg = render_graph(d)
    u = (width - 2 * GPAD) / xs

    def scr(x, y):
        return (GPAD + (x - xRange[0]) * u, height - GPAD - (y - yRange[0]) * u)
    # 자동 축 라벨 x·y 는 변수 → 이탤릭
    svg = re.sub(r'(<text [^>]*?)(>)([xy])(</text>)',
                 lambda m: m.group(1) + ' font-style="italic"' + m.group(2) + m.group(3) + m.group(4), svg)
    extra = []
    for lab in labels:
        x, y, text = lab[0], lab[1], lab[2]
        dx, dy = (lab[3], lab[4]) if len(lab) > 4 else (0, 0)
        anc = lab[5] if len(lab) > 5 else "middle"
        X, Y = scr(x, y)
        if re.fullmatch(r"[A-Z0-9]+", text):          # 점 이름·수 = 정자
            extra.append(txt(X + dx, Y + dy, text, fs, anc=anc))
        else:                                          # 식 = 변수 이탤릭
            extra.append(runs_text(X + dx, Y + dy, text.replace("-", "−"), fs, anc=anc))
    svg = svg.replace("</svg>", "".join(extra) + "</svg>")
    svg = re.sub(r"(<svg[^>]*>)", lambda m: m.group(1) + f'<rect width="{width}" height="{height:.3f}" fill="#ffffff"/>', svg, count=1)
    return sanitize_svg(svg)


def foot(p, a, b):
    ux, uy = b[0] - a[0], b[1] - a[1]
    t = ((p[0] - a[0]) * ux + (p[1] - a[1]) * uy) / (ux * ux + uy * uy)
    return (a[0] + t * ux, a[1] + t * uy)


def isect(p1, p2, p3, p4):
    x1, y1 = p1; x2, y2 = p2; x3, y3 = p3; x4, y4 = p4
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    a = x1 * y2 - y1 * x2
    b = x3 * y4 - y3 * x4
    return ((a * (x3 - x4) - (x1 - x2) * b) / den, (a * (y3 - y4) - (y1 - y2) * b) / den)


# ── q1 ────────────────────────────────────────────────────────────────
k = 7.0
B1 = (40.0, 190.0); C1 = (B1[0] + 28 * k, B1[1]); A1 = (B1[0], B1[1] - 21 * k)
verify_figure("q1", lengths=[(21, A1, B1), (28, B1, C1), (35, A1, C1)],
              angles=[(90, B1, A1, C1)])
_check("q1-cos", abs((28 / 35) - 0.8) < 1e-12, "cosC=4/5")
S["q1"] = spec(points={"A": P(*A1), "B": P(*B1), "C": P(*C1)},
               segments={"AB": ["A", "B"], "BC": ["B", "C"], "CA": ["C", "A"]},
               angles={"angB": {"vertex": "B", "points": ["A", "C"], "right": True}},
               dimensions={"dimBC": {"points": ["B", "C"], "label": "28 cm", "side": "auto"}},
               labels={"A": "A", "B": "B", "C": "C"})

# ── q3 ────────────────────────────────────────────────────────────────
r3 = 200.0
A3 = (40.0, 170.0); B3 = (A3[0] + r3, A3[1])
C3 = (A3[0] + r3 * math.cos(math.radians(38)), A3[1] - r3 * math.sin(math.radians(38)))
D3 = (C3[0], A3[1])
verify_figure("q3", lengths=[(1, A3, C3), (1, A3, B3)],
              angles=[(38, A3, B3, C3), (90, D3, C3, B3)])
S["q3"] = spec(points={"A": P(*A3), "D": P(*D3),
                       "B": {"type": "on_circle", "circle": "sec", "angle": 0},
                       "C": {"type": "on_circle", "circle": "sec", "angle": 38}},
               circles={"sec": {"center": "A", "radius": r3, "draw": False}},
               arcs={"arcBC": {"circle": "sec", "from": "B", "to": "C", "dir": "ccw"}},
               segments={"AD": ["A", "D"], "DB": ["D", "B"], "AC": ["A", "C"], "CD": ["C", "D"]},
               angles={"angA": {"vertex": "A", "points": ["D", "C"], "label": "38°"},
                       "angD": {"vertex": "D", "points": ["C", "B"], "right": True}},
               dimensions={"dimAC": {"points": ["A", "C"], "label": "1", "side": "auto"}},
               labels={"A": "A", "B": "B", "C": "C", "D": "D"})

# ── q4 ────────────────────────────────────────────────────────────────
k = 17.0
BD4, DC4 = 1.7, 9.0
BC4 = BD4 + DC4
AB4 = BC4 * R5 / 2
A4 = (40.0, 30.0); B4 = (A4[0], A4[1] + AB4 * k); C4 = (B4[0] + BC4 * k, B4[1])
D4 = (B4[0] + BD4 * k, B4[1])
AC4 = math.hypot(C4[0] - A4[0], C4[1] - A4[1])
E4 = (C4[0] + 6 * k * (A4[0] - C4[0]) / AC4, C4[1] + 6 * k * (A4[1] - C4[1]) / AC4)
verify_figure("q4", lengths=[(9, D4, C4), (6, E4, C4), (3 * R5, D4, E4)],
              angles=[(90, B4, A4, C4), (90, E4, D4, C4)],
              on_line=[(E4, A4, C4)])
_check("q4-tan", abs(math.atan2(AB4, BC4) - math.atan(R5 / 2)) < 1e-9, "tanC=√5/2")
ANG_AC4 = ray_angle(*A4, *C4) % 360
S["q4"] = spec(points={"A": P(*A4), "B": P(*B4), "C": P(*C4), "D": P(*D4), "E": P(*E4),
                       "P1": {"type": "on_circle", "circle": "cA", "angle": 270},
                       "P2": {"type": "on_circle", "circle": "cA", "angle": round(ANG_AC4, 6)}},
               segments={"AB": ["A", "B"], "BD": ["B", "D"], "DC": ["D", "C"], "AE": ["A", "E"], "EC": ["E", "C"], "DE": ["D", "E"]},
               circles={"cA": {"center": "A", "radius": 15, "draw": False}},
               regions={"shadeA": {"boundary": [
                   {"seg": ["A", "P1"]},
                   {"arc": {"circle": "cA", "from": "P1", "to": "P2", "dir": "ccw"}},
                   {"seg": ["P2", "A"]}], "fill": "#d6d6d6"}},
               angles={"angB": {"vertex": "B", "points": ["A", "D"], "right": True},
                       "angE": {"vertex": "E", "points": ["D", "C"], "right": True},
                       "angA": {"vertex": "A", "points": ["B", "E"], "label": "x", "radius": 15}},
               dimensions={"dimDC": {"points": ["D", "C"], "label": "9", "side": "auto"},
                           "dimEC": {"points": ["E", "C"], "label": "6", "side": "auto"}},
               labels={"A": "A", "B": "B", "C": "C", "D": "D", "E": "E"})

# ── q6 ────────────────────────────────────────────────────────────────
A6 = (30.0, 150.0); C6 = (250.0, 150.0); B6 = (250.0, 150.0 - 0.56 * 220)
D6 = foot(C6, A6, B6)
verify_figure("q6", angles=[(90, C6, A6, B6), (90, D6, C6, B6)], on_line=[(D6, A6, B6)])
S["q6"] = spec(points={"A": P(*A6), "B": P(*B6), "C": P(*C6), "D": P(*D6)},
               segments={"AD": ["A", "D"], "DB": ["D", "B"], "BC": ["B", "C"], "CA": ["C", "A"], "CD": ["C", "D"]},
               angles={"angC": {"vertex": "C", "points": ["A", "B"], "right": True},
                       "angD": {"vertex": "D", "points": ["C", "B"], "right": True}},
               labels={"A": "A", "B": "B", "C": "C", "D": "D"})

# ── q7 ────────────────────────────────────────────────────────────────
k = 22.0
ox, oy = 30.0, 175.0
def q7(x, y): return (ox + x * k, oy - y * k)
A7 = q7(3, 3 * R3); B7 = q7(0, 0); C7 = q7(8, 0); E7 = q7(12, 0)
t7 = 1.21
D7 = q7(12 - 5 * t7, 3 * R3 * t7)
verify_figure("q7", lengths=[(6, B7, A7), (8, B7, C7), (4, C7, E7)],
              angles=[(60, B7, C7, A7)])
_check("q7-평행", abs(ray_angle(*A7, *C7) - ray_angle(*D7, *E7)) < 1e-6, "AC∥DE")
S["q7"] = spec(points={"A": P(*A7), "B": P(*B7), "C": P(*C7), "D": P(*D7), "E": P(*E7),
                       "M": P((C7[0] + E7[0]) / 2, C7[1])},
               segments={"AB": ["A", "B"], "BC": ["B", "C"], "CE": ["C", "E"],
                         "AD": ["A", "D"], "DC": ["D", "C"], "AE": ["A", "E"],
                         "AC": {"points": ["A", "C"], "parallel": 1},
                         "DE": {"points": ["D", "E"], "parallel": 1}},
               regions={"shade": {"boundary": [{"seg": ["A", "B"]}, {"seg": ["B", "C"]},
                                               {"seg": ["C", "D"]}, {"seg": ["D", "A"]}],
                                  "fill": "#ececec"}},
               angles={"angB": {"vertex": "B", "points": ["C", "A"], "label": "60°", "label_distance": 34}},
               dimensions={"dimAB": {"points": ["B", "A"], "label": "6 cm", "side": "auto"},
                           "dimBC": {"points": ["B", "C"], "label": "8 cm", "side": "auto"}},
               labels={"A": "A", "B": "B", "C": "C", "D": "D", "E": "E",
                       "M": {"text": "4 cm", "position": "S"}})

# ── q9 ────────────────────────────────────────────────────────────────
k = 24.0
B9 = (30.0, 150.0); C9 = (B9[0] + 8 * k, B9[1])
A9 = (B9[0] + 2 * k, B9[1] - R21 * k); D9 = (B9[0] + 6 * k, A9[1])
verify_figure("q9", lengths=[(4, A9, D9), (8, B9, C9), (5, A9, B9), (5, D9, C9)])
S["q9"] = spec(points={"A": P(*A9), "B": P(*B9), "C": P(*C9), "D": P(*D9)},
               segments={"AB": ["A", "B"], "BC": ["B", "C"], "CD": ["C", "D"], "DA": ["D", "A"]},
               dimensions={"dimAD": {"points": ["A", "D"], "label": "4", "side": "auto"},
                           "dimBC": {"points": ["B", "C"], "label": "8", "side": "auto"}},
               labels={"A": "A", "B": "B", "C": "C", "D": "D"})

# ── q10 ───────────────────────────────────────────────────────────────
k = 20.0
B10 = (30.0, 170.0); H10 = (B10[0] + 6 * k, B10[1]); C10 = (B10[0] + 9 * k, B10[1])
A10 = (H10[0], B10[1] - 7 * k)
verify_figure("q10", lengths=[(6, B10, H10), (3, H10, C10)], angles=[(90, H10, A10, C10)])
S["q10"] = spec(points={"A": P(*A10), "B": P(*B10), "C": P(*C10), "H": P(*H10)},
                segments={"AB": ["A", "B"], "BH": ["B", "H"], "HC": ["H", "C"], "CA": ["C", "A"], "AH": ["A", "H"]},
                angles={"angH": {"vertex": "H", "points": ["A", "C"], "right": True}},
                dimensions={"dimBH": {"points": ["B", "H"], "label": "6", "side": "auto"},
                            "dimHC": {"points": ["H", "C"], "label": "3", "side": "auto"}},
                labels={"A": "A", "B": "B", "C": "C", "H": "H"})

# ── q13 (graph) ───────────────────────────────────────────────────────
f13 = lambda x: x * x
g13 = lambda x: x * x - 5 * x
_check("q13-넓이", abs(sum((f13((i + .5) * 2.5 / 2000) - g13((i + .5) * 2.5 / 2000)) * 2.5 / 2000
                          for i in range(2000)) - 125 / 8) < 1e-3, "색칠 넓이 125/8")
shade13 = [[i * 2.5 / 40, f13(i * 2.5 / 40)] for i in range(41)] + \
          [[2.5 - i * 2.5 / 40, g13(2.5 - i * 2.5 / 40)] for i in range(41)]
shade13 = [[round(x, 4), round(y, 4)] for x, y in shade13]
verify_figure("q13", on_line=[((2.5, g13(2.5)), (2.5, -7), (2.5, 8))],
              lengths=[(2.5, (0, 0), (2.5, 0)), (5, (0, 0), (5, 0))])
S["q13"] = graph(xRange=[-3.3, 6.7], yRange=[-7.6, 9.6], width=250,
                 polygons=[{"points": shade13, "fill": "#e2e2e2"}],
                 curves=[{"coefficients": [1, 0, 0], "domain": [-2.85, 2.85]},
                         {"coefficients": [1, -5, 0], "domain": [-1.35, 6.35]}],
                 segments=[{"from": [2.5, -7.4], "to": [2.5, 8.6]}],
                 labels=[(0, 0, "O", -10, 19), (2.5, -7.4, "l", 9, 6),
                         (-2.85, 8.12, "y=x²", -2, -9), (6.35, 8.12, "y=x²-5x", -8, -9)])

# ── q15 (graph) ───────────────────────────────────────────────────────
a15, b15 = 5 / 9, -10 / 3
f15 = lambda x: a15 * x * x + b15 * x + 3
_check("q15-부호", a15 > 0 and b15 < 0 and f15(0) == 3 and f15(3) < 0, "a>0, b<0, y절편 3, 꼭짓점 제4사분면")
verify_figure("q15", on_line=[((0, f15(0)), (0, -2), (0, 8))])
S["q15"] = graph(xRange=[-1.7, 4.3], yRange=[-2.8, 8.4], width=240,
                 curves=[{"coefficients": [a15, b15, 3], "domain": [-1.2, 3.35]}],
                 points=[{"at": [0, 3]}],
                 labels=[(0, 3, "3", -13, 6), (0, 0, "O", -11, 19)])

# ── q16 (graph) ───────────────────────────────────────────────────────
t16 = R5 - 1
f16 = lambda x: -x * x + 4 * x
A16, B16 = (2 - t16, 0), (2 + t16, 0)
C16, D16 = (2 + t16, 2 * t16), (2 - t16, 2 * t16)
_check("q16-정사각형", abs(f16(C16[0]) - 2 * t16) < 1e-9 and abs(f16(D16[0]) - 2 * t16) < 1e-9,
       "C·D 가 포물선 위이고 변=2t")
verify_figure("q16", lengths=[(1, A16, B16), (1, B16, C16), (1, C16, D16), (1, D16, A16)])
S["q16"] = graph(xRange=[-1.0, 6.6], yRange=[-2.0, 4.8], width=330,
                 curves=[{"coefficients": [-1, 4, 0], "domain": [-0.42, 4.42]}],
                 segments=[{"from": list(A16), "to": list(D16)}, {"from": list(D16), "to": list(C16)},
                           {"from": list(C16), "to": list(B16)}],
                 labels=[(0, 0, "O", -17, 20), (A16[0], 0, "A", 5, 19), (B16[0], 0, "B", -5, 19),
                         (C16[0], C16[1], "C", 10, -7), (D16[0], D16[1], "D", -11, -7),
                         (4.45, -1.6, "y=-x²+4x", 6, 8, "start")])

# ── s1 (graph) ────────────────────────────────────────────────────────
a17 = -2 / 3
f17 = lambda x: a17 * (x - 2) ** 2 + 6
_check("s1", abs(f17(5)) < 1e-12 and abs(f17(-1)) < 1e-12 and f17(2) == 6, "꼭짓점 (2,6), x절편 5")
verify_figure("s1", on_line=[((2, f17(2)), (2, 0), (2, 7))])
S["s1"] = graph(xRange=[-1.9, 6.4], yRange=[-2.6, 7.4], width=260,
                curves=[{"coefficients": [a17, -4 * a17, 4 * a17 + 6], "domain": [-1.5, 5.5]}],
                segments=[{"from": [0, 6], "to": [2, 6], "dashed": True},
                          {"from": [2, 6], "to": [2, 0], "dashed": True}],
                labels=[(0, 6, "6", -11, 6), (2, 0, "2", 0, 19), (5, 0, "5", -10, 19),
                        (0, 0, "O", -11, 19)])

# ── s3 ────────────────────────────────────────────────────────────────
k = 16.0
B19 = (30.0, 200.0); C19 = (B19[0] + 10 * R3 * k, B19[1]); D19 = (C19[0], C19[1] - 10 * k)
A19 = ((B19[0] + C19[0]) / 2, B19[1] - 5 * R3 * k)
E19 = isect(B19, D19, A19, C19)
verify_figure("s3", lengths=[(10, C19, D19), (10 * R3, B19, C19)],
              angles=[(45, C19, B19, A19), (60, D19, B19, C19), (90, A19, B19, C19),
                      (90, C19, B19, D19)])
S["s3"] = spec(points={"A": P(*A19), "B": P(*B19), "C": P(*C19), "D": P(*D19),
                       "E": {"type": "intersection", "segments": ["BD", "AC"]}},
               segments={"AB": ["A", "B"], "AC": ["A", "C"], "BD": ["B", "D"],
                         "DC": ["D", "C"], "BC": ["B", "C"]},
               regions={"shade": {"boundary": [{"seg": ["E", "B"]}, {"seg": ["B", "C"]},
                                               {"seg": ["C", "E"]}], "fill": "#ececec"}},
               angles={"angD": {"vertex": "D", "points": ["B", "C"], "label": "60°"},
                       "angC": {"vertex": "C", "points": ["B", "A"], "label": "45°"}},
               dimensions={"dimCD": {"points": ["C", "D"], "label": "10", "side": "auto"}},
               labels={"A": "A", "B": "B", "C": "C", "D": "D", "E": {"text": "E", "position": "N"}})

# ── s4 (primitives) ───────────────────────────────────────────────────
k = 1.55
A20 = (95.0, 150.0)
B20 = (A20[0] + 100 * k * math.cos(math.radians(30)), A20[1] - 100 * k * math.sin(math.radians(30)))
C20 = (B20[0] + 50 * k, A20[1])
ux, uy = (B20[0] - A20[0]) / (100 * k), (B20[1] - A20[1]) / (100 * k)
X20 = (B20[0] + 42 * ux, B20[1] + 42 * uy)          # AB 연장선 끝
verify_figure("s4", lengths=[(100, A20, B20)],
              angles=[(30, A20, C20, B20), (75, B20, X20, C20), (45, C20, A20, B20)])


def arrowhead(tip, frm, s=7.0):
    L = math.hypot(tip[0] - frm[0], tip[1] - frm[1])
    dx, dy = (tip[0] - frm[0]) / L, (tip[1] - frm[1]) / L
    px, py = -dy, dx
    a = (tip[0] - dx * s + px * s * 0.42, tip[1] - dy * s + py * s * 0.42)
    b = (tip[0] - dx * s - px * s * 0.42, tip[1] - dy * s - py * s * 0.42)
    return (f'<path d="M {tip[0]:.1f} {tip[1]:.1f} L {a[0]:.1f} {a[1]:.1f} '
            f'L {b[0]:.1f} {b[1]:.1f} Z" fill="#000"/>')


bike = "\n".join([
    '<circle cx="28" cy="142" r="9" fill="none" stroke="#000" stroke-width="2.2"/>',
    '<circle cx="62" cy="142" r="9" fill="none" stroke="#000" stroke-width="2.2"/>',
    line((28, 142), (42, 130), 1.6), line((42, 130), (62, 142), 1.6), line((42, 130), (58, 126), 1.6),
    line((58, 126), (62, 142), 1.6), line((58, 126), (60, 118), 1.6),
    line((42, 130), (40, 122), 1.6),
    '<ellipse cx="42" cy="110" rx="7" ry="10" fill="#555"/>',
    '<circle cx="44" cy="96" r="5" fill="#333"/>',
    line((46, 112), (58, 118), 2.2), line((40, 118), (48, 132), 2.2),
])
puddle = ('<path d="M 186 150 q 8 -7 22 -6 q 14 -3 24 4 q -6 7 -22 7 q -16 2 -24 -5 Z" '
          'fill="#9a9a9a" stroke="#555" stroke-width="0.8"/>')
S["s4"] = f'''<svg viewBox="0 0 372 180" xmlns="http://www.w3.org/2000/svg">
<rect width="372" height="180" fill="#ffffff"/>
{bike}
{line((72, 150), A20, 1.8)}{arrowhead((A20[0] - 3, A20[1]), (72, 150))}
{line(A20, C20, 1.5, dash="7 5")}
{puddle}
{line(C20, (362, 150), 1.8)}{arrowhead((364, 150), C20)}
{line(A20, B20, 2.2)}{arrowhead(B20, A20, 9)}
{line(B20, X20, 1.8)}
{line(B20, C20, 2.2)}{arrowhead(C20, B20, 9)}
<path d="{angle_arc(*A20, C20, B20, 26)}" fill="none" stroke="#000" stroke-width="1"/>
{txt(A20[0] + 46, A20[1] - 7, "30°", 17)}
<path d="{angle_arc(*B20, X20, C20, 13)}" fill="none" stroke="#000" stroke-width="1"/>
{txt(B20[0] + 34, B20[1] + 1, "75°", 17)}
{measured(*A20, *B20, -22, "100 m", 17)}
{txt(A20[0], A20[1] + 22, "A", 17)}{txt(B20[0] - 2, B20[1] - 12, "B", 17)}
{txt(C20[0], C20[1] + 22, "C", 17)}
</svg>'''

if __name__ == "__main__":
    from core.figure_generator import _svg_to_png_bytes

    miss = unverified(S)
    if miss:
        raise SystemExit(f"검산 누락(verify_figure 미호출): {miss}")
    print("작도 검산", len(CHECKS), "건 통과")
    bad = 0
    for key, svg in S.items():
        issues = lint_svg(svg)
        if issues:
            print(f"{key} LINT:", "; ".join(issues))
        vw = float(svg.split('viewBox="')[1].split()[2])
        png = _svg_to_png_bytes(svg, width=int(vw * 3))
        if not png:
            print(key, "PNG 실패")
            bad += 1
            continue
        with open(os.path.join(OUT, f"{key}.png"), "wb") as f:
            f.write(png)
        print(key, "ok")
    raise SystemExit(1 if bad else 0)
