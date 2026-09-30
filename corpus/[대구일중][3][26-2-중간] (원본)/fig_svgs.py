# -*- coding: utf-8 -*-
"""대구일중3 26-2-중간 — 그림 17개, todays-math 엔진(선언형 스펙) 작도.

원본은 스캔이라 그림을 캡처하지 않고 **문제 조건에서 좌표를 유도**해 작도한다.
  - 도형: FigureSpec v2 (core.figure_scene.render_figure_spec) — 라벨 배치·굵기·조판은 엔진.
  - 함수 그래프: graph-1 (scripts/figure/graph_scene.render_graph) — x·y 등방 단위.
  - 최종 SVG 는 core.figure_quality.sanitize_svg 통과.
verify_figure 로 라벨 값과 작도가 맞는지 재측정한다(화면 좌표 기준).
q12(등대)·q17(연못)은 원본이 삽화라 기하 도식(삼각형 + 연못 윤곽)으로 대체.
"""
import math
import os
import re
import sys
import tempfile

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p_ in (str(ROOT), str(ROOT / "scripts" / "figure")):
    if p_ not in sys.path:
        sys.path.insert(0, p_)
sys.stdout.reconfigure(encoding="utf-8")
from core.figure_quality import sanitize_svg  # noqa: E402
from core.figure_scene import render_figure_spec  # noqa: E402
from core.figure_svg import lint_svg, rangle, sqrt_label, unverified, verify_figure  # noqa: E402
from graph_scene import render_graph  # noqa: E402

OUT = os.environ.get(
    "FIG_SVG_OUT",
    str(Path(tempfile.gettempdir()) / "exam_figure_svg" / "daeguil3"),
)
os.makedirs(OUT, exist_ok=True)
S = {}
SPECS = {}
GREY = "#e0e0e0"
DIM_SIDE_IF_CR_POS, DIM_SIDE_IF_CR_NEG = "right", "left"
R2, R3 = math.sqrt(2), math.sqrt(3)


def mapper(ox, oy, u):
    """수학 좌표(y 위) → 화면 좌표(y 아래). 등방 단위 u."""
    return lambda p: (round(ox + u * p[0], 3), round(oy - u * p[1], 3))


def geo(key, canvas, points, segments, angles=None, dims=None, regions=None,
        labels=None, circles=None, extra="", arcs=None, canvas_fixed=False, screen=None):
    spec = {"version": 2,
            "points": {k: (v if isinstance(v, dict) else [float(v[0]), float(v[1])]) for k, v in points.items()},
            "segments": segments}
    if canvas_fixed:
        spec["canvas"] = list(canvas)
    if circles:
        spec["circles"] = circles
    if arcs:
        spec["arcs"] = arcs
    if angles:
        spec["angles"] = angles
    if dims:
        # 치수선은 **도형 바깥**으로(사용자 2026-09-30): 원시 점들의 무게중심 반대쪽 side 지정.
        scr = screen or points
        raw = [v for v in scr.values() if not isinstance(v, dict)]
        cx = sum(p[0] for p in raw) / len(raw)
        cy = sum(p[1] for p in raw) / len(raw)
        for d in dims.values():
            if "side" in d:
                continue
            p, q = (scr[n] for n in d["points"])
            cr = (q[0] - p[0]) * (cy - p[1]) - (q[1] - p[1]) * (cx - p[0])
            d["side"] = DIM_SIDE_IF_CR_POS if cr > 0 else DIM_SIDE_IF_CR_NEG
        spec["dimensions"] = dims
    if regions:
        spec["regions"] = regions
    spec["labels"] = labels if labels is not None else {
        k: k for k in points if k[:1].isupper() and len(k) == 1}
    SPECS[key] = spec
    svg = render_figure_spec(spec)
    if extra:
        svg = svg.replace("</svg>", extra + "\n</svg>")
    S[key] = sanitize_svg(svg)


def graph(key, xr, yr, u, **fields):
    w = 96 + u * (xr[1] - xr[0])
    h = 96 + u * (yr[1] - yr[0])
    spec = {"version": "graph-1", "xRange": list(xr), "yRange": list(yr),
            "width": round(w, 3), "height": round(h, 3), **fields}
    SPECS[key] = spec
    S[key] = sanitize_svg(graph_math(render_graph(spec)))
    pad = 48
    return lambda p: (pad + (p[0] - xr[0]) * u, h - pad - (p[1] - yr[0]) * u)


def graph_math(svg):
    """graph-1 라벨은 평문 <text> 로 나온다(웹은 data-mj 로 따로 조판) — 변수만 이탤릭으로."""
    svg = re.sub(r'(<text [^>]*)>([a-z])</text>', r'\1 font-style="italic">\2</text>', svg)
    return svg.replace(">$y=-3$</text>", '><tspan font-style="italic">y</tspan> = −3</text>')


def unit_upright(svg):
    """라벨 조판기가 단위 m 를 변수로 보고 기울인다 — 정자로 되돌린다."""
    return re.sub(r'<tspan font-style="italic"( font-family="[^"]*")?>m</tspan>',
                  r'<tspan font-style="normal">m</tspan>', svg)


def region(*names):
    ring = list(names) + [names[0]]
    return {"boundary": [{"seg": [a, b]} for a, b in zip(ring, ring[1:])], "fill": GREY}


def seg_map(*pairs):
    return {a + b: [a, b] for a, b in pairs}


# ── q1: y=-3(x+1)^2 — 꼭짓점 (-1,0), y절편 -3 ─────────────────────────
X1, Y1 = (-2.6, 1.3), (-5.9, 1.1)
G1 = graph("q1", X1, Y1, 34,
           curves=[{"coefficients": [-3, -6, -3], "domain": [-2.34, 0.34]}],
           labels=[{"at": [-1, 0], "text": "−1", "dy": -12},
                   {"at": [0, 0], "text": "O", "dx": 11, "dy": 19},
                   {"at": [0, -3], "text": "−3", "dx": 18, "dy": 4}])
verify_figure("q1", on_line=[(G1((-1, 0)), G1((-2, 0)), G1((1, 0))),
                             (G1((0, -3)), G1((0, 1)), G1((0, -5)))],
              lengths=[(1, G1((-1, 0)), G1((0, 0))), (3, G1((0, 0)), G1((0, -3)))])

# ── q5: y=½x²+2x-5/2 — A(-5,0), B(-2,-9/2), C(0,-5/2), 사각형 OABC 색칠 ──
G5 = graph("q5", (-7.2, 3.2), (-5.4, 4.2), 22,
           polygons=[{"points": [[0, 0], [-5, 0], [-2, -4.5], [0, -2.5]], "fill": "#e6e6e6"}],
           curves=[{"coefficients": [0.5, 2, -2.5], "domain": [-6.1, 2.1]}],
           segments=[{"from": [-5, 0], "to": [-2, -4.5]}, {"from": [-2, -4.5], "to": [0, -2.5]}],
           labels=[{"at": [-5, 0], "text": "A", "dx": -12, "dy": 20},
                   {"at": [-2, -4.5], "text": "B", "dy": 22}])
f5 = lambda x: 0.5 * x * x + 2 * x - 2.5                          # noqa: E731
assert f5(-5) == 0 and f5(-2) == -4.5 and f5(0) == -2.5
verify_figure("q5", lengths=[(5, G5((0, 0)), G5((-5, 0))), (2.5, G5((0, 0)), G5((0, -2.5))),
                             (4.5, G5((-2, 0)), G5((-2, -4.5)))])

# ── q6: 직각삼각형 ABC, ∠B=90°, AB=2, BC=1 ─────────────────────────────
P6 = mapper(40, 120, 90)
pts6 = {"A": P6((0, 0)), "B": P6((2, 0)), "C": P6((2, 1))}
wedge = 20
pts6["a1"] = {"type": "on_circle", "circle": "cA", "angle": 0}
pts6["a2"] = {"type": "on_circle", "circle": "cA", "angle": math.degrees(math.atan(0.5))}
geo("q6", (270, 160), pts6, seg_map("AB", "BC", "CA"),
    circles={"cA": {"center": "A", "radius": wedge, "draw": False}},
    regions={"wedgeA": {"boundary": [
        {"seg": ["A", "a1"]},
        {"arc": {"circle": "cA", "from": "a1", "to": "a2", "dir": "ccw"}},
        {"seg": ["a2", "A"]}], "fill": "#cfcfcf"}},
    angles={"angB": {"vertex": "B", "points": ["A", "C"], "right": True},
            "angA": {"vertex": "A", "points": ["B", "C"], "radius": wedge}},
    dims={"dimAB": {"points": ["A", "B"], "label": "2"},
          "dimBC": {"points": ["B", "C"], "label": "1"}})
verify_figure("q6", lengths=[(2, pts6["A"], pts6["B"]), (1, pts6["B"], pts6["C"])],
              angles=[(90, pts6["B"], pts6["A"], pts6["C"])])

# ── q7: 직각삼각형 ABC, ∠C=90°, BC=4, tanB=√5/2 → AC=2√5, AB=6 ────────
P7 = mapper(34, 170, 32)
# 원본 시각 비율: AC 는 라벨이 없어 원본(AC/BC≈0.64)을 따른다(정답 계산값 2√5 는 그림에 없음).
pts7 = {"B": P7((0, 0)), "C": P7((4, 0)), "A": P7((4, 0.64 * 4))}
geo("q7", (200, 200), pts7, seg_map("AB", "BC", "CA"),
    angles={"angC": {"vertex": "C", "points": ["B", "A"], "right": True}},
    dims={"dimBC": {"points": ["B", "C"], "label": "4"}})
verify_figure("q7", lengths=[(4, pts7["B"], pts7["C"])],
              angles=[(90, pts7["C"], pts7["B"], pts7["A"])])

# ── q9: 반지름 1 사분원 OED, ∠AOB=x°(대표값 42°) ─────────────────────
X9 = math.radians(42)
P9 = mapper(58, 196, 150)
pts9 = {"O": P9((0, 0)), "E": P9((0, 1)), "D": P9((1, 0)),
        "A": P9((math.cos(X9), math.sin(X9))), "B": P9((math.cos(X9), 0)),
        "C": P9((1, math.tan(X9)))}
spec9 = dict(pts9)
spec9["E"] = {"type": "on_circle", "circle": "q", "angle": 90}
spec9["D"] = {"type": "on_circle", "circle": "q", "angle": 0}
spec9["A"] = {"type": "on_circle", "circle": "q", "angle": 42}
geo("q9", (245, 235), spec9, seg_map("OE", "OB", "BD", "OA", "AC", "AB", "CD"),
    circles={"q": {"center": "O", "radius": 150, "draw": False}},
    arcs={"arcED": {"circle": "q", "from": "E", "to": "D", "dir": "cw"}},
    angles={"angO": {"vertex": "O", "points": ["E", "B"], "right": True},
            "angB": {"vertex": "B", "points": ["A", "D"], "right": True},
            "angD": {"vertex": "D", "points": ["B", "C"], "right": True},
            "angx": {"vertex": "O", "points": ["B", "A"], "label": "x°"},
            "angy": {"vertex": "A", "points": ["O", "B"], "label": "y°"},
            "angz": {"vertex": "C", "points": ["A", "D"], "label": "z°"}},
    dims={"dimOE": {"points": ["O", "E"], "label": "1"}}, screen=pts9)
verify_figure("q9", lengths=[(1, pts9["O"], pts9["E"]), (1, pts9["O"], pts9["A"]), (1, pts9["O"], pts9["D"])],
              angles=[(90, pts9["B"], pts9["A"], pts9["O"]), (48, pts9["A"], pts9["O"], pts9["B"]),
                      (48, pts9["C"], pts9["O"], pts9["D"])],
              on_line=[(pts9["A"], pts9["O"], pts9["C"])], on_circle=[(pts9["A"], *pts9["O"], 150)])

# ── q10: 반지름 1 사분원, x=56° (cos56=0.56 → DA=0.44), AC=y=tan56 ────
X10 = math.acos(0.56)
P10 = mapper(46, 192, 112)
pts10 = {"O": P10((0, 0)), "A": P10((1, 0)), "T": P10((0, 1)),
         "B": P10((math.cos(X10), math.sin(X10))), "D": P10((math.cos(X10), 0)),
         "C": P10((1, math.tan(X10)))}
spec10 = dict(pts10)
spec10["T"] = {"type": "on_circle", "circle": "q", "angle": 90}
spec10["A"] = {"type": "on_circle", "circle": "q", "angle": 0}
spec10["B"] = {"type": "on_circle", "circle": "q", "angle": math.degrees(X10)}
geo("q10", (215, 240), spec10, seg_map("OT", "OD", "DA", "OB", "BC", "BD", "AC"),
    circles={"q": {"center": "O", "radius": 112, "draw": False}},
    arcs={"arcTA": {"circle": "q", "from": "T", "to": "A", "dir": "cw"}},
    angles={"angD": {"vertex": "D", "points": ["O", "B"], "right": True},
            "angA": {"vertex": "A", "points": ["D", "C"], "right": True},
            "angx": {"vertex": "O", "points": ["D", "B"], "label": "x"}},
    dims={"dimAC": {"points": ["A", "C"], "label": "y"},
          "dimDA": {"points": ["D", "A"], "label": "0.44"}},
    labels={k: k for k in "OABCD"}, screen=pts10)
verify_figure("q10", lengths=[(0.44, pts10["D"], pts10["A"]), (math.tan(X10), pts10["A"], pts10["C"]),
                              (1, pts10["O"], pts10["A"])],
              angles=[(math.degrees(X10), pts10["O"], pts10["A"], pts10["B"])],
              on_line=[(pts10["B"], pts10["O"], pts10["C"])],
              on_circle=[(pts10["B"], *pts10["O"], 112)])

# ── q11: 직각삼각형 ABC, ∠C=90°, ∠A=55°, AB=10, BC=x ─────────────────
A55 = math.radians(55)
P11 = mapper(34, 132, 20)
pts11 = {"A": P11((0, 0)), "B": P11((10, 0)),
         "C": P11((10 * math.cos(A55) ** 2, 10 * math.cos(A55) * math.sin(A55)))}
geo("q11", (270, 175), pts11, seg_map("AB", "BC", "CA"),
    angles={"angC": {"vertex": "C", "points": ["A", "B"], "right": True},
            "angA": {"vertex": "A", "points": ["B", "C"], "label": "55"}},
    dims={"dimAB": {"points": ["A", "B"], "label": "10"},
          "dimCB": {"points": ["C", "B"], "label": "x"}})
verify_figure("q11", lengths=[(10, pts11["A"], pts11["B"]), (10 * math.sin(A55), pts11["B"], pts11["C"])],
              angles=[(55, pts11["A"], pts11["B"], pts11["C"]), (90, pts11["C"], pts11["A"], pts11["B"])])

# ── q12: 등대 A·B, 지점 C — ∠B=90°, ∠C=33°, BC=200 m (삽화 → 도식) ──
P12 = mapper(168, 186, 0.8)
ang12 = math.radians(72)
AB12 = 200 * math.tan(math.radians(33))
pts12 = {"B": P12((0, 0)), "C": P12((200 * math.cos(ang12), 200 * math.sin(ang12))),
         "A": P12((AB12 * math.cos(ang12 + math.pi / 2), AB12 * math.sin(ang12 + math.pi / 2)))}
geo("q12", (265, 215), pts12, seg_map("AB", "BC", "CA"),
    angles={"angB": {"vertex": "B", "points": ["A", "C"], "right": True},
            "angC": {"vertex": "C", "points": ["A", "B"], "label": "33°"}},
    dims={"dimBC": {"points": ["B", "C"], "label": "200 m"}})
S["q12"] = unit_upright(S["q12"])
verify_figure("q12", lengths=[(200, pts12["B"], pts12["C"]), (AB12, pts12["A"], pts12["B"])],
              angles=[(90, pts12["B"], pts12["A"], pts12["C"]), (33, pts12["C"], pts12["A"], pts12["B"])])

# ── q13: △ABC, AB=5, AC=8, 넓이 8√3 → sinA=2√3/5 (A 예각) ───────────
cosA = math.sqrt(13) / 5
BC13 = math.sqrt(25 + 64 - 80 * cosA)
xa = (BC13 ** 2 - 39) / (2 * BC13)
P13 = mapper(66, 160, 22)
ANG13 = 62.0                                  # 원본 그림의 ∠A 시각값(라벨 없음)
BC13 = math.sqrt(25 + 64 - 80 * math.cos(math.radians(ANG13)))
xa = (BC13 ** 2 - 39) / (2 * BC13)
P13 = mapper(40, 150, 22)
pts13 = {"B": P13((0, 0)), "C": P13((BC13, 0)), "A": P13((xa, math.sqrt(25 - xa * xa)))}
assert abs(0.5 * 5 * 8 * math.sqrt(1 - cosA ** 2) - 8 * R3) < 1e-9
geo("q13", (235, 190), pts13, seg_map("AB", "BC", "CA"),
    regions={"sh": region("A", "B", "C")},
    dims={"dimAB": {"points": ["B", "A"], "label": "5cm"},
          "dimAC": {"points": ["A", "C"], "label": "8cm"}})
verify_figure("q13", lengths=[(5, pts13["A"], pts13["B"]), (8, pts13["A"], pts13["C"])],
              angles=[(ANG13, pts13["A"], pts13["B"], pts13["C"])])

# ── q14: 정사면체(모서리 3, DH=√3), 사투영(D 를 x축 위에 두어 AH⊥HD 가 화면에서도 직각) ──
def proj14(p):
    x, y, z = p
    return (round(128 + 50 * (x - 0.65 * y), 3), round(152 - 50 * (z + 0.35 * y + 0.22 * x), 3))


def base14(deg):
    return (R3 * math.cos(math.radians(deg)), R3 * math.sin(math.radians(deg)), 0.0)


D3, B3, C3 = base14(0), base14(120), base14(240)
A3, H3 = (0.0, 0.0, math.sqrt(6)), (0.0, 0.0, 0.0)
M3 = tuple((B3[i] + C3[i]) / 2 for i in range(3))
for p_, q_ in ((A3, B3), (A3, C3), (A3, D3), (B3, C3), (C3, D3), (B3, D3)):
    assert abs(math.dist(p_, q_) - 3) < 1e-9                       # 정사면체 모서리 3
assert abs(math.dist(M3, H3) * 2 - math.dist(H3, D3)) < 1e-9       # 무게중심 1:2
assert abs(math.dist(H3, D3) - R3) < 1e-9 and abs(A3[2] / 3 - math.sqrt(6) / 3) < 1e-9
pts14 = {k: proj14(v) for k, v in (("A", A3), ("B", B3), ("C", C3), ("D", D3), ("H", H3), ("M", M3))}
_hx, _hy = pts14["H"]
_u = (pts14["A"][0] - _hx, pts14["A"][1] - _hy)
_v = (pts14["D"][0] - _hx, pts14["D"][1] - _hy)
_lu, _lv = math.hypot(*_u), math.hypot(*_v)
HMARK14 = rangle(_hx, _hy, _u[0] / _lu, _u[1] / _lu, _v[0] / _lv, _v[1] / _lv, 8)
geo("q14", (250, 220), pts14,
    {"AB": ["A", "B"], "AC": ["A", "C"], "AD": ["A", "D"], "BC": ["B", "C"],
     "CD": ["C", "D"], "BD": {"points": ["B", "D"], "dashed": "5 4"},
     "AH": ["A", "H"], "MH": ["M", "H"], "HD": ["H", "D"]},
    regions={"sh": region("A", "H", "D")},
    canvas_fixed=True, extra=HMARK14,
    angles={
            "angx": {"vertex": "D", "points": ["A", "H"], "label": "x°", "label_distance": 36}})
verify_figure("q14", on_line=[(pts14["H"], pts14["M"], pts14["D"]), (pts14["M"], pts14["B"], pts14["C"])])

# ── q15: 직각삼각형 ABD, ∠D=90°, AD=2, AC=BC, ∠ACD=45° ──────────────
P15 = mapper(30, 112, 48)
pts15 = {"B": P15((0, 0)), "C": P15((2 * R2, 0)), "D": P15((2 + 2 * R2, 0)),
         "A": P15((2 + 2 * R2, 2))}
geo("q15", (285, 145), pts15,
    {"AB": ["A", "B"], "BC": {"points": ["B", "C"], "ticks": 2}, "CD": ["C", "D"],
     "AD": ["A", "D"], "CA": {"points": ["C", "A"], "ticks": 2}},
    angles={"angD": {"vertex": "D", "points": ["A", "C"], "right": True},
            "angC": {"vertex": "C", "points": ["D", "A"], "label": "45°"}})
verify_figure("q15", lengths=[(2, pts15["A"], pts15["D"]), (2 * R2, pts15["A"], pts15["C"]),
                              (2 * R2, pts15["B"], pts15["C"])],
              angles=[(45, pts15["C"], pts15["D"], pts15["A"]), (22.5, pts15["B"], pts15["D"], pts15["A"])])

# ── q16: ∠B=90°, ∠C=45°, AC=6, ∠ADB=60°, DE⊥AC ───────────────────────
s16 = 3 * R2
BD16 = s16 / R3
tE = (BD16 * s16 + s16 * s16) / (2 * s16 * s16)
P16 = mapper(44, 200, 40)
pts16 = {"B": P16((0, 0)), "C": P16((s16, 0)), "A": P16((0, s16)), "D": P16((BD16, 0)),
         "E": P16((tE * s16, s16 - tE * s16))}
geo("q16", (235, 235), pts16, seg_map("AB", "BD", "DC", "AC", "AD", "DE"),
    angles={"angB": {"vertex": "B", "points": ["A", "D"], "right": True},
            "angE": {"vertex": "E", "points": ["D", "C"], "right": True},
            "angD": {"vertex": "D", "points": ["A", "B"], "label": "60°"},
            "angC": {"vertex": "C", "points": ["D", "E"]}},
    dims={"dimAC": {"points": ["A", "C"], "label": "6"}})
verify_figure("q16", lengths=[(6, pts16["A"], pts16["C"]), (3 - R3, pts16["D"], pts16["E"])],
              angles=[(60, pts16["D"], pts16["A"], pts16["B"]), (45, pts16["C"], pts16["A"], pts16["B"]),
                      (90, pts16["E"], pts16["D"], pts16["C"])],
              on_line=[(pts16["E"], pts16["A"], pts16["C"])])

# ── q17: 연못 A·B, 지점 C — AC=20 m, ∠A=75°, ∠C=60° → AB=10√6 ─────
AB17 = 10 * math.sqrt(6)
P17 = mapper(62, 66, 8)
pts17 = {"A": P17((0, 0)), "B": P17((AB17, 0)),
         "C": P17((20 * math.cos(math.radians(75)), -20 * math.sin(math.radians(75))))}
cx17, cy17, ry17 = (pts17["A"][0] + pts17["B"][0]) / 2, pts17["A"][1] - 7, 28
rx17 = (pts17["B"][0] - pts17["A"][0]) / 2 / math.sqrt(1 - (7 / ry17) ** 2)
pond = (f'<ellipse cx="{cx17:.2f}" cy="{cy17:.2f}" rx="{rx17:.2f}" ry="{ry17}" '
        f'fill="#ececec" stroke="#555555" stroke-width="0.9"/>')
geo("q17", (300, 250), pts17, seg_map("AB", "BC", "CA"),
    angles={"angC": {"vertex": "C", "points": ["A", "B"], "label": "60°"}},
    dims={"dimAC": {"points": ["C", "A"], "label": "20 m"}}, canvas_fixed=True)
S["q17"] = unit_upright(S["q17"]).replace("<g>", pond + "\n<g>", 1)
verify_figure("q17", lengths=[(20, pts17["A"], pts17["C"]), (AB17, pts17["A"], pts17["B"])],
              angles=[(75, pts17["A"], pts17["B"], pts17["C"]), (60, pts17["C"], pts17["A"], pts17["B"])])

# ── q18: 평행사변형 ABCD, AB=6, AD=7√2, ∠A=135°, E=BC 중점 ──────────
AD18 = 7 * R2
P18 = mapper(34, 150, 14.5)
a18 = (6 / R2, 6 / R2)
pts18 = {"B": P18((0, 0)), "C": P18((AD18, 0)), "A": P18(a18), "D": P18((a18[0] + AD18, a18[1])),
         "E": P18((AD18 / 2, 0))}
geo("q18", (305, 185), pts18,
    {"AB": ["A", "B"], "BE": {"points": ["B", "E"], "ticks": 1}, "EC": {"points": ["E", "C"], "ticks": 1},
     "CD": ["C", "D"], "DA": ["D", "A"], "BD": ["B", "D"], "ED": ["E", "D"]},
    regions={"sh": region("B", "E", "D")},
    angles={"angA": {"vertex": "A", "points": ["B", "D"], "label": "135°"}},
    dims={"dimAB": {"points": ["B", "A"], "label": "6cm"},
          "dimAD": {"points": ["A", "D"], "label": "7√2 cm"}})
verify_figure("q18", lengths=[(6, pts18["A"], pts18["B"]), (AD18, pts18["A"], pts18["D"]),
                              (AD18 / 2, pts18["B"], pts18["E"]), (AD18 / 2, pts18["E"], pts18["C"])],
              angles=[(135, pts18["A"], pts18["B"], pts18["D"])])

# ── s1: y=⅓(x-1)(x-7), 꼭짓점 (4,-3) ─────────────────────────────────
Gs1 = graph("s1", (-1.2, 9.4), (-4.6, 4.4), 22,
            curves=[{"coefficients": [1 / 3, -8 / 3, 7 / 3], "domain": [-0.55, 8.55]}],
            segments=[{"from": [-1.2, -3], "to": [9.4, -3]}, {"from": [4, 0], "to": [4, -3]}],
            labels=[{"at": [0, 0], "text": "O", "dx": -10, "dy": 18},
                    {"at": [1, 0], "text": "1", "dx": -9, "dy": 18},
                    {"at": [7, 0], "text": "7", "dx": 7, "dy": 18},
                    {"at": [0, -3], "text": "−3", "dx": -16, "dy": 18},
                    {"at": [7.6, -3], "text": "$y=-3$", "dy": 20}])
fs1 = lambda x: (x - 1) * (x - 7) / 3                              # noqa: E731
assert fs1(1) == 0 and fs1(7) == 0 and abs(fs1(4) + 3) < 1e-12
verify_figure("s1", lengths=[(6, Gs1((1, 0)), Gs1((7, 0))), (3, Gs1((4, 0)), Gs1((4, -3)))])

# ── s3: □ABCD, AB=3, BC=4, CD=2, DA=√3, ∠B=60°, ∠D=150° ──────────────
Am, Bm, Cm = (1.5, 1.5 * R3), (0.0, 0.0), (4.0, 0.0)
dAC = math.dist(Am, Cm)
a_ = (3 - 4 + dAC ** 2) / (2 * dAC)
h_ = math.sqrt(3 - a_ * a_)
ux_, uy_ = (Cm[0] - Am[0]) / dAC, (Cm[1] - Am[1]) / dAC
Dm = max(((Am[0] + a_ * ux_ - s * h_ * uy_, Am[1] + a_ * uy_ + s * h_ * ux_) for s in (1, -1)),
         key=lambda p: math.dist(p, Bm))
Ps3 = mapper(44, 150, 44)
ptss3 = {"A": Ps3(Am), "B": Ps3(Bm), "C": Ps3(Cm), "D": Ps3(Dm)}
geo("s3", (260, 185), ptss3, seg_map("AB", "BC", "CD", "DA"),
    regions={"sh": region("A", "B", "C", "D")},
    angles={"angB": {"vertex": "B", "points": ["C", "A"], "label": "60°"},
            "angD": {"vertex": "D", "points": ["A", "C"], "label": "150°", "label_distance": 34}},
    dims={"dimAB": {"points": ["B", "A"], "label": "3 cm"},
          "dimBC": {"points": ["B", "C"], "label": "4 cm"},
          "dimCD": {"points": ["D", "C"], "label": "2 cm"},
          "dimDA": {"points": ["A", "D"], "label": "√3 cm"}})
verify_figure("s3", lengths=[(3, ptss3["A"], ptss3["B"]), (4, ptss3["B"], ptss3["C"]),
                             (2, ptss3["C"], ptss3["D"]), (R3, ptss3["D"], ptss3["A"])],
              angles=[(60, ptss3["B"], ptss3["A"], ptss3["C"]), (150, ptss3["D"], ptss3["A"], ptss3["C"])])

# ── s4: 직사각형 ABCD, AD=6, DC=4, M·N 중점, ∠MBN=x ──────────────────
Ps4 = mapper(34, 160, 32)
ptss4 = {"A": Ps4((0, 4)), "D": Ps4((6, 4)), "B": Ps4((0, 0)), "C": Ps4((6, 0)),
         "M": Ps4((3, 4)), "N": Ps4((6, 2))}
geo("s4", (265, 185), ptss4, seg_map("AM", "MD", "DN", "NC", "CB", "BA", "BM", "MN", "BN"),
    angles={"angx": {"vertex": "B", "points": ["N", "M"], "label": "x"}})
verify_figure("s4", lengths=[(6, ptss4["A"], ptss4["D"]), (4, ptss4["D"], ptss4["C"]),
                             (5, ptss4["B"], ptss4["M"]), (2 * math.sqrt(10), ptss4["B"], ptss4["N"])],
              angles=[(90, ptss4["B"], ptss4["A"], ptss4["C"])])


if __name__ == "__main__":
    from core.figure_generator import _svg_to_png_bytes

    miss = unverified(S)
    if miss:
        raise SystemExit(f"검산 누락(verify_figure 미호출): {miss}")
    bad = 0
    for k, svg in S.items():
        issues = lint_svg(svg)
        if issues:
            print(f"{k} LINT:", "; ".join(issues))
        png = _svg_to_png_bytes(svg, width=int(
            float(svg.split('viewBox="0 0 ')[1].split()[0]) * 4))
        if not png:
            print(k, "PNG 실패")
            bad += 1
            continue
        with open(os.path.join(OUT, f"{k}.png"), "wb") as f:
            f.write(png)
        print(k, "ok ->", os.path.join(OUT, f"{k}.png"))
    raise SystemExit(1 if bad else 0)
