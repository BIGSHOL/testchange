# -*- coding: utf-8 -*-
"""침산중2 26-2-중간 — 그림 15개(todays-math 엔진: FigureSpec v2 / graph-1).

원본은 학생 사본 스캔(손풀이·연필 표시 다수)이라 **인쇄 요소만** 재현한다.
좌표는 전부 문제 조건에서 유도하고(눈대중 금지) verify_figure 로 재측정한다.
라벨 배치·선 굵기·조판은 엔진(core.figure_scene / graph_scene)이 맡는다.
스펙이 표현 못 하는 인쇄 요소(등각 점·중심 점·접는 화살표)만 figure_svg 프리미티브로 덧댄다.

  q2  : 이등변 AB=AC, ∠BAD=38°, BD=DC                 → 밑각 52°
  q5  : x+2y=-1 · 2x+y=-5 (a=-2, b=-5), 교점 (-3, 1)
  q7  : ∠A=45°(∠DCB:∠DCE=1:2 에서 유도), DE ⊥ AC 이등분, 접힌 △DEC 음영
  q8  : OA=8·PB=PA=6 (원본 작도 비율 그대로 — 발문 ∠APO=48° 와는 모순, meta 기록)
  q9  : 공통 빗변 AB, ∠CAB=53°·∠DAB=37°
  q10 : AB=5·BC=12·CA=13, AD=5, DE⊥AC
  q11 : 직각 B, 빗변 중점 M (AB:BC 는 원본 비율 0.64)
  q12 : 외심 — AB=22·BC=24·∠B=33°(원본) / 내심 — QL=QM=8·RM=RN=6·r=4 → PQ=15·PR=13
  q13 : AB=6·BC=10·CA=11 내접원
  q14 : ∠B=52°(∠C=73°는 원본 비율), 외심 O, A-O-D
  q15 : ∠B=42°(∠AIC=111°), ∠C=103°(원본 비율)
  s1  : 2x+y-8=0 · x-y+2=0 · x축 삼각형
  s2  : ∠A=36°, AB=AC=8, BD 이등분
  s3  : AB=AC 직각, BD=20·CE=9 (AD=CE, AE=BD)
  s4  : AB=15·AC=8·BC=17
"""
import html
import math
import os
import re
import sys
import tempfile

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "figure"))
sys.stdout.reconfigure(encoding="utf-8")
from core.figure_svg import (_text_runs_markup, auto_runs, bisect_pt, dot, isect, leader, lint_svg, rangle_at,  # noqa: E402
                             unverified, verify_figure)
from core.figure_scene import render_figure_spec  # noqa: E402
from core.figure_quality import sanitize_svg  # noqa: E402
from graph_scene import render_graph  # noqa: E402

OUT = os.environ.get(
    "FIG_SVG_OUT",
    str(Path(tempfile.gettempdir()) / "exam_figure_svg" / "chimsan2"),
)
os.makedirs(OUT, exist_ok=True)
S = {}
GREY = "#c9c9c9"


# ── 기하 헬퍼 ────────────────────────────────────────────────────────
def lerp(p, q, t):
    return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)


def polar(p, ang_deg, d):
    """수학각(반시계, y-up) 방향으로 d — SVG y-down 보정."""
    a = math.radians(ang_deg)
    return (p[0] + d * math.cos(a), p[1] - d * math.sin(a))


def circumcenter(a, b, c):
    ax, ay = a
    bx, by = b
    cx, cy = c
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay)
          + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx)
          + (cx * cx + cy * cy) * (bx - ax)) / d
    return (ux, uy)


def incenter(a, b, c):
    la, lb, lc = math.dist(b, c), math.dist(a, c), math.dist(a, b)
    s = la + lb + lc
    return ((la * a[0] + lb * b[0] + lc * c[0]) / s, (la * a[1] + lb * b[1] + lc * c[1]) / s)


def foot(p, a, b):
    ux, uy = b[0] - a[0], b[1] - a[1]
    t = ((p[0] - a[0]) * ux + (p[1] - a[1]) * uy) / (ux * ux + uy * uy)
    return (a[0] + ux * t, a[1] + uy * t)


# ── 스펙 헬퍼 ────────────────────────────────────────────────────────
def pts(**kw):
    return {k: {"type": "raw", "x": round(v[0], 3), "y": round(v[1], 3)} for k, v in kw.items()}


def fig(canvas, points, segments, angles=None, dims=None, labels=None,
        circles=None, regions=None, extra=""):
    spec = {"version": 2, "theme": "exam-thin", "canvas": list(canvas),
            "points": points, "segments": segments}
    if angles:
        spec["angles"] = angles
    if dims:
        spec["dimensions"] = dims
    if circles:
        spec["circles"] = circles
    if regions:
        spec["regions"] = regions
    spec["labels"] = labels if labels is not None else {
        k: k for k in points if len(k) == 1}
    svg = render_figure_spec(spec)
    if extra:
        svg = svg.replace("</svg>", extra + "\n</svg>")
    return sanitize_svg(svg)


_TEXT_RE = re.compile(r"(<text [^>]*>)([^<]*)(</text>)")


def graph(spec):
    """graph-1 렌더 + 라벨 조판 보정.

    ⚠️ 파이썬 render_graph 는 라벨을 원문 <text> 로 낸다($…$ 조판은 Node 쪽 몫) —
    축 이름 x·y 와 식 라벨의 변수가 정자로 나온다. 라틴 문자만 이탤릭 런으로 바꾼다
    (auto_runs: 변수 이탤릭·숫자/기호 정자, 대문자 O 는 원점이라 정자 유지).
    """
    svg = render_graph(spec)

    def fix(m):
        body = html.unescape(m.group(2))
        if not re.search(r"[a-z]", body):
            return m.group(0)
        return m.group(1) + _text_runs_markup(auto_runs(body)) + m.group(3)

    return sanitize_svg(_TEXT_RE.sub(fix, svg))


def seg(p, q, **kw):
    if not kw:
        return [p, q]
    d = {"points": [p, q]}
    d.update(kw)
    return d


def ang(v, p1, p2, label=None, **kw):
    d = {"vertex": v, "points": [p1, p2]}
    if label is not None:
        d["label"] = label
    d.update(kw)
    return d


def dim(p, q, label, **kw):
    d = {"points": [p, q], "label": label, "side": kw.pop("side", "auto")}
    d.update(kw)
    return d


# ── q2: 이등변삼각형, ∠BAD=38°, BD=5·DC=x ─────────────────────────
u = 26.0
A2 = (160.0, 30.0)
D2 = (160.0, 30.0 + 5 * u / math.tan(math.radians(38)))
B2, C2 = (160.0 - 5 * u, D2[1]), (160.0 + 5 * u, D2[1])
verify_figure("q2", angles=[(38, A2, B2, D2), (52, C2, A2, B2)],
              lengths=[(5, B2, D2), (5, D2, C2)])
S["q2"] = fig((320, 240), pts(A=A2, B=B2, C=C2, D=D2, l38=(A2[0] - 46, A2[1] + 20)),
              {"AB": seg("A", "B", ticks=2), "AC": seg("A", "C", ticks=2),
               "BD": seg("B", "D"), "DC": seg("D", "C"), "AD": seg("A", "D")},
              angles={"angA": ang("A", "B", "D"),
                      "angC": ang("C", "A", "D", "y°")},
              dims={"dimBD": dim("B", "D", "5 cm", side="left"),
                    "dimDC": dim("D", "C", "x cm", side="left")},
              labels={**{k: k for k in "ABCD"}, "l38": {"text": "38°", "dx": 0, "dy": 0}})

# ── q5: 두 직선 x+2y=-1(완만)·2x+y=-5(가파름), 교점 (-3,1) ───────────
a5, b5 = -2.0, -5.0
g_st = lambda x: b5 - 2 * x            # 2x+y=b
g_sh = lambda x: (x + 1) / a5          # x-ay=-1 → y=(x+1)/a
assert abs(g_st(-3) - 1) < 1e-9 and abs(g_sh(-3) - 1) < 1e-9
XR5, YR5 = [-4.5, 2.0], [-1.6, 3.6]
W5 = 300
H5 = round(W5 * (YR5[1] - YR5[0]) / (XR5[1] - XR5[0]))
verify_figure("q5", on_line=[((-3, 1), (-4, g_st(-4)), (-2, g_st(-2))),
                             ((-3, 1), (-4, g_sh(-4)), (1, g_sh(1)))])
S["q5"] = graph({
    "version": "graph-1", "xRange": XR5, "yRange": YR5, "width": W5, "height": H5,
    "curves": [{"coefficients": [-2, b5], "domain": [-4.1, -1.8]},
               {"coefficients": [1 / a5, 1 / a5], "domain": [-4.2, 1.65]}],
    "segments": [{"from": [-3, 1], "to": [-3, 0], "dashed": True},
                 {"from": [-3, 1], "to": [0, 1], "dashed": True}],
    "labels": [{"at": [-3, 0], "text": "−3", "dx": -6, "dy": 20},
               {"at": [0, 1], "text": "1", "dx": 11, "dy": 5},
               {"at": [0, 0], "text": "O", "dx": -12, "dy": -8}],
})

# ── q7: 이등변삼각형 ABC(∠A=45°) 를 DE 로 접어 A→C ───────────────────
half7 = 80.0
A7 = (150.0, 30.0)
B7 = (150.0 - half7, 30.0 + half7 / math.tan(math.radians(22.5)))
C7 = (150.0 + half7, B7[1])
E7 = lerp(A7, C7, 0.5)
nx7, ny7 = -(C7[1] - A7[1]), (C7[0] - A7[0])
D7 = isect(E7, (E7[0] + nx7, E7[1] + ny7), A7, B7)      # AC 의 수직이등분선 ∩ AB
verify_figure("q7", angles=[(45, A7, B7, C7), (67.5, B7, A7, C7),
                            (22.5, C7, D7, B7), (45, C7, D7, E7), (90, D7, B7, C7)],
              lengths=[(1, D7, A7), (1, D7, C7)], on_line=[(D7, A7, B7)])
def fold_arrow(p0, c1, c2, p3, w=1.6, head=7.5):
    """접는 방향 곡선 화살표(원본: 위에서 왼쪽으로 휘어 음영 안으로 내려꽂힘) — 3차 베지에."""
    ux, uy = p3[0] - c2[0], p3[1] - c2[1]
    L = math.hypot(ux, uy)
    ux, uy = ux / L, uy / L
    bx, by = p3[0] - ux * head, p3[1] - uy * head
    nx, ny = -uy, ux
    return (f'<path d="M {p0[0]:.1f} {p0[1]:.1f} C {c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} '
            f'{bx:.1f} {by:.1f}" fill="none" stroke="#111111" stroke-width="{w}"/>'
            f'<path d="M {p3[0]:.1f} {p3[1]:.1f} L {bx + nx * head * 0.4:.1f} {by + ny * head * 0.4:.1f} '
            f'L {bx - nx * head * 0.4:.1f} {by - ny * head * 0.4:.1f} Z" fill="#111111"/>')


ax7, ay7 = A7
S["q7"] = fig((300, 250), pts(A=A7, B=B7, C=C7, D=D7, E=E7),
              {"AD": seg("A", "D", dash="5 4"), "AE": seg("A", "E", dash="5 4"),
               "DB": seg("D", "B"), "BC": seg("B", "C"), "EC": seg("E", "C"),
               "DE": seg("D", "E"), "DC": seg("D", "C")},
              regions={"fold": {"boundary": [{"seg": ["D", "E"]}, {"seg": ["E", "C"]},
                                             {"seg": ["C", "D"]}], "fill": GREY}},
              extra=fold_arrow((ax7 + 16, ay7 + 66), (ax7 - 10, ay7 + 66),
                               (ax7 - 12, ay7 + 104), (ax7 + 6, ay7 + 124)))

# ── q8: ∠O 이등분선 위 P, 수선의 발 A·B, OA=8·PB=6 ──────────────────
u8 = 18.0
O8 = (38.0, 212.0)
th8 = math.degrees(math.atan2(6, 8))          # 반각(원본 작도 비율)
B8 = polar(O8, 0, 8 * u8)
A8 = polar(O8, 2 * th8, 8 * u8)
P8 = polar(O8, th8, 10 * u8)
A8x = polar(O8, 2 * th8, 8 * u8 + 36)
B8x = polar(O8, 0, 8 * u8 + 50)
P8x = polar(O8, th8, 10 * u8 + 48)
verify_figure("q8", lengths=[(8, O8, A8), (6, P8, B8), (6, P8, A8), (8, O8, B8)],
              angles=[(90, A8, O8, P8), (90, B8, O8, P8)],
              on_line=[(P8, O8, P8x), (A8, O8, A8x)])
dA8 = bisect_pt(*O8, A8, P8, 22)
dB8 = bisect_pt(*O8, P8, B8, 22)
S["q8"] = fig((270, 240), pts(O=O8, A=A8, B=B8, P=P8, Ax=A8x, Bx=B8x, Px=P8x),
              {"OA": seg("O", "A"), "AAx": seg("A", "Ax"), "OB": seg("O", "B"), "BBx": seg("B", "Bx"),
               "OP": seg("O", "P"), "PPx": seg("P", "Px"),
               "AP": seg("A", "P"), "PB": seg("P", "B")},
              angles={"rA": ang("A", "O", "P", right=True),
                      "rB": ang("B", "O", "P", right=True),
                      "angP": ang("P", "A", "O", "48°", label_distance=44)},
              dims={"dimOA": dim("O", "A", "8 cm", side="auto"),
                    "dimPB": dim("P", "B", "6 cm", side="auto")},
              labels={"O": "O", "A": "A", "B": "B", "P": "P"},
              extra=dot(*dA8, 2.2) + dot(*dB8, 2.2))

# ── q9: 공통 빗변 AB, 직각 C·D, ∠CAB=53°·∠DAB=37° ───────────────────
A9, B9 = (32.0, 186.0), (292.0, 186.0)
AB9 = B9[0] - A9[0]
C9 = polar(A9, 53, AB9 * math.cos(math.radians(53)))
D9 = polar(A9, 37, AB9 * math.cos(math.radians(37)))
E9 = isect(A9, D9, B9, C9)
verify_figure("q9", angles=[(90, C9, A9, B9), (90, D9, A9, B9), (37, A9, D9, B9),
                            (37, B9, C9, A9), (16, B9, D9, C9)],
              lengths=[(1, C9, A9), (1, D9, B9)])
S["q9"] = fig((325, 210), pts(A=A9, B=B9, C=C9, D=D9, E=E9),
              {"AB": seg("A", "B"), "AC": seg("A", "C", ticks=2), "CB": seg("C", "B"),
               "AD": seg("A", "D"), "DB": seg("D", "B", ticks=2)},
              angles={"rC": ang("C", "A", "B", right=True),
                      "rD": ang("D", "A", "B", right=True),
                      "angA": ang("A", "B", "D", "37°", label_distance=46)})

# ── q10: 직각삼각형 AB=5·BC=12·CA=13, AD=AB, DE⊥AC ──────────────────
u10 = 20.0
B10 = (60.0, 170.0)
A10 = (B10[0], B10[1] - 5 * u10)
C10 = (B10[0] + 12 * u10, B10[1])
D10 = lerp(A10, C10, 5 / 13)
BE10 = 5 * math.tan(math.atan2(12, 5) / 2)
E10 = (B10[0] + BE10 * u10, B10[1])
verify_figure("q10", lengths=[(5, A10, B10), (12, B10, C10), (13, C10, A10), (5, A10, D10),
                              (BE10, B10, E10), (BE10, D10, E10)],
              angles=[(90, B10, A10, C10), (90, D10, E10, C10)])
S["q10"] = fig((330, 215), pts(A=A10, B=B10, C=C10, D=D10, E=E10),
               {"AB": seg("A", "B"), "BC": seg("B", "C"), "CA": seg("C", "A"),
                "AE": seg("A", "E"), "DE": seg("D", "E")},
               angles={"rB": ang("B", "A", "C", right=True)},
               dims={"dimAB": dim("A", "B", "5 cm", side="auto"),
                     "dimBC": dim("B", "C", "12 cm", side="auto"),
                     "dimCA": dim("A", "C", "13 cm", side="auto")},
               extra=rangle_at(*D10, A10, E10, 8))

# ── q11: 직각 B, 빗변 AC 의 중점 M ───────────────────────────────────
B11 = (40.0, 182.0)
A11 = (40.0, 40.0)
C11 = (263.0, 182.0)
M11 = lerp(A11, C11, 0.5)
verify_figure("q11", angles=[(90, B11, A11, C11)],
              lengths=[(1, A11, M11), (1, M11, C11), (1, B11, M11)])
S["q11"] = fig((300, 210), pts(A=A11, B=B11, C=C11, M=M11),
               {"AB": seg("A", "B"), "BC": seg("B", "C"), "AM": seg("A", "M", ticks=2),
                "MC": seg("M", "C", ticks=2), "BM": seg("B", "M")},
               angles={"rB": ang("B", "A", "C", right=True)},
               extra=dot(*M11, 2.8))

# ── q12: 외심 O(△ABC) · 내심 I(△PQR) ─────────────────────────────────
u12 = 10.0
B12 = (30.0, 222.0)
C12 = (B12[0] + 24 * u12, B12[1])
A12 = polar(B12, 33, 22 * u12)
O12 = circumcenter(A12, B12, C12)
D12, E12, F12 = lerp(B12, A12, 0.5), lerp(B12, C12, 0.5), lerp(A12, C12, 0.5)
u12r = 13.5
Q12 = (345.0, 222.0)
R12 = (Q12[0] + 14 * u12r, Q12[1])
P12 = (Q12[0] + 9 * u12r, Q12[1] - 12 * u12r)          # PQ=15, PR=13
I12 = incenter(P12, Q12, R12)
L12, M12, N12 = foot(I12, P12, Q12), foot(I12, Q12, R12), foot(I12, P12, R12)
verify_figure("q12-외심", lengths=[(11, A12, D12), (11, D12, B12), (12, B12, E12), (12, E12, C12)],
              angles=[(90, D12, O12, A12), (90, E12, O12, C12), (90, F12, O12, C12)])
verify_figure("q12", lengths=[(8, Q12, L12), (8, Q12, M12), (6, M12, R12), (6, R12, N12),
                                  (4, I12, L12), (4, I12, M12), (4, I12, N12),
                                  (15, P12, Q12), (13, P12, R12)],
              on_line=[(L12, P12, Q12), (N12, P12, R12)])
S["q12"] = fig((570, 272),
               pts(A=A12, B=B12, C=C12, D=D12, E=E12, F=F12, O=O12,
                   P=P12, Q=Q12, R=R12, I=I12, L=L12, M=M12, N=N12, mLI=lerp(L12, I12, 0.5)),
               {"BD": seg("B", "D"), "DA": seg("D", "A"), "BE": seg("B", "E"), "EC": seg("E", "C"),
                "AF": seg("A", "F"), "FC": seg("F", "C"),
                "OD": seg("O", "D"), "OE": seg("O", "E"), "OF": seg("O", "F"),
                "PL": seg("P", "L"), "LQ": seg("L", "Q"), "QM": seg("Q", "M"), "MR": seg("M", "R"),
                "RN": seg("R", "N"), "NP": seg("N", "P"),
                "IL": seg("I", "L"), "IM": seg("I", "M"), "IN": seg("I", "N")},
               angles={"rD": ang("D", "A", "O", right=True), "rE": ang("E", "C", "O", right=True),
                       "rF": ang("F", "C", "O", right=True), "rL": ang("L", "P", "I", right=True),
                       "rM": ang("M", "R", "I", right=True), "rN": ang("N", "R", "I", right=True)},
               dims={"dimAD": dim("D", "A", "11 cm", side="auto", offset=9),
                     "dimBD": dim("B", "D", "x cm", side="auto", offset=9),
                     "dimBE": dim("B", "E", "12 cm", side="auto"),
                     "dimQL": dim("Q", "L", "8 cm", side="auto", offset=9),
                     "dimIM": dim("I", "M", "z cm", side="left", offset=8),
                     "dimQM": dim("Q", "M", "y cm", side="auto"),
                     "dimMR": dim("M", "R", "6 cm", side="auto")},
               labels={**{k: k for k in "ABCDEFPQRILMN"}, "O": {"text": "O", "position": "N"},
                       "mLI": {"text": "4 cm", "dx": -6, "dy": 18}},
               extra=dot(*O12, 2.3) + dot(*I12, 2.3))

# ── q13: AB=6·BC=10·CA=11, 내접원 ────────────────────────────────────
u13 = 25.0
B13 = (50.0, 196.0)
C13 = (B13[0] + 10 * u13, B13[1])
ax13 = (36 - 121 + 100) / 20.0
A13 = (B13[0] + ax13 * u13, B13[1] - math.sqrt(36 - ax13 * ax13) * u13)
I13 = incenter(A13, B13, C13)
r13 = 0.5 * 10 * math.sqrt(36 - ax13 * ax13) / 13.5 * u13
D13, E13, F13 = foot(I13, A13, B13), foot(I13, B13, C13), foot(I13, A13, C13)
verify_figure("q13", lengths=[(6, A13, B13), (10, B13, C13), (11, C13, A13),
                              (2.5, B13, D13), (2.5, B13, E13), (7.5, C13, F13), (7.5, C13, E13)],
              on_circle=[(D13, *I13, r13), (E13, *I13, r13), (F13, *I13, r13)])
S["q13"] = fig((330, 235), pts(A=A13, B=B13, C=C13, D=D13, E=E13, F=F13, I=I13),
               {"AB": seg("A", "B"), "BC": seg("B", "C"), "CA": seg("C", "A")},
               circles={"inc": {"center": "I", "radius": round(r13, 3)}},
               dims={"dimAB": dim("A", "B", "6 cm", side="auto"),
                     "dimCA": dim("A", "C", "11 cm", side="auto"),
                     "dimBC": dim("B", "C", "10 cm", side="auto")},
               extra=dot(*I13, 2.3))

# ── q14: 외심 O, ∠B=52°, A-O-D ───────────────────────────────────────
Bang, Cang = 52.0, 73.0
Aang = 180 - Bang - Cang
B14 = (30.0, 200.0)
k14 = 175.0 / math.sin(math.radians(Aang))
C14 = (B14[0] + 175.0, B14[1])
A14 = polar(B14, Bang, k14 * math.sin(math.radians(Cang)))
O14 = circumcenter(A14, B14, C14)
D14 = isect(A14, O14, B14, C14)
verify_figure("q14", angles=[(52, B14, A14, C14), (73, C14, A14, B14),
                             (90 - 52, A14, D14, C14)],
              on_line=[(O14, A14, D14)])
S["q14"] = fig((245, 228), pts(A=A14, B=B14, C=C14, D=D14, O=O14),
               {"AB": seg("A", "B"), "BC": seg("B", "C"), "CA": seg("C", "A"),
                "AD": seg("A", "D")},
               angles={"angB": ang("B", "A", "C", "52°", label_distance=36),
                       "angA": ang("A", "D", "C")},
               extra=dot(*O14, 2.5))

# ── q15: 내심 I, ∠AIC=111°(∠B=42°), D·E 는 이등분선의 발 ──────────────
B15ang, C15ang = 42.0, 103.0
A15ang = 180 - B15ang - C15ang
B15 = (30.0, 300.0)
k15 = 205.0 / math.sin(math.radians(A15ang))
C15 = (B15[0] + 205.0, B15[1])
A15 = polar(B15, B15ang, k15 * math.sin(math.radians(C15ang)))
I15 = incenter(A15, B15, C15)
D15 = isect(C15, I15, A15, B15)
E15 = isect(A15, I15, B15, C15)
verify_figure("q15", angles=[(111, I15, A15, C15), (42, B15, A15, C15),
                             (A15ang / 2, A15, B15, E15), (C15ang / 2, C15, A15, D15)],
              on_line=[(I15, A15, E15), (I15, C15, D15)])
S["q15"] = fig((330, 335), pts(A=A15, B=B15, C=C15, D=D15, E=E15, I=I15,
                               lI=bisect_pt(*I15, A15, C15, 36)),
               {"AD": seg("A", "D"), "DB": seg("D", "B"), "BE": seg("B", "E"), "EC": seg("E", "C"),
                "CA": seg("C", "A"), "AI": seg("A", "I"), "IE": seg("I", "E"),
                "CI": seg("C", "I"), "ID": seg("I", "D")},
               labels={**{k: k for k in "ABCDEI"}, "lI": {"text": "111°", "dx": 0, "dy": 0}},
               angles={"angI": ang("I", "A", "C", radius=18),
                       "angD": ang("D", "A", "I"),
                       "angE": ang("E", "I", "C")},
               extra=dot(*I15, 2.5))

# ── s1: 2x+y-8=0 · x-y+2=0 · x축 ─────────────────────────────────────
XR1, YR1 = [-3.8, 6.8], [-1.8, 7.4]
W1 = 320
H1 = round(W1 * (YR1[1] - YR1[0]) / (XR1[1] - XR1[0]))
verify_figure("s1", on_line=[((2, 4), (0, 8), (4, 0)), ((2, 4), (-2, 0), (0, 2))])
S["s1"] = graph({
    "version": "graph-1", "xRange": XR1, "yRange": YR1, "width": W1, "height": H1,
    "curves": [{"coefficients": [1, 2], "domain": [-2.9, 4.1]},
               {"coefficients": [-2, 8], "domain": [0.9, 4.55]}],
    "polygons": [{"points": [[-2, 0], [4, 0], [2, 4]], "fill": "#e2e2e2"}],
    "labels": [{"at": [0, 0], "text": "O", "dx": -12, "dy": 20},
               {"at": [4.1, 6.1], "text": "x − y + 2 = 0", "dx": 4, "dy": -6, "anchor": "start", "size": 17},
               {"at": [4.55, -0.9], "text": "2x + y − 8 = 0", "dx": -18, "dy": 24, "anchor": "middle", "size": 17}],
})

# ── s2: ∠A=36°, AB=AC=8, BC≈5, ∠B 의 이등분선 BD ──────────────────────
u2 = 22.0
A2s = (150.0, 30.0)
B2s = polar(A2s, 270 - 18, 8 * u2)
C2s = polar(A2s, 270 + 18, 8 * u2)
BC2s = math.dist(B2s, C2s)
D2s = lerp(A2s, C2s, BC2s / (8 * u2))                  # AD = BD = BC
verify_figure("s2", angles=[(36, A2s, B2s, C2s), (36, B2s, A2s, D2s), (36, B2s, D2s, C2s)],
              lengths=[(8, A2s, B2s), (5, B2s, C2s)])
dot1 = bisect_pt(*B2s, A2s, D2s, 24)
dot2 = bisect_pt(*B2s, D2s, C2s, 24)
S["s2"] = fig((280, 245), pts(A=A2s, B=B2s, C=C2s, D=D2s),
              {"AB": seg("A", "B"), "BC": seg("B", "C"), "CA": seg("C", "A"),
               "BD": seg("B", "D")},
              angles={"angA": ang("A", "B", "C", "36°", label_distance=56)},
              dims={"dimAB": dim("A", "B", "8 cm", side="auto"),
                    "dimBC": dim("B", "C", "5 cm", side="auto")},
              extra=dot(*dot1, 3.0) + dot(*dot2, 3.0))

# ── s3: AB=AC 직각, 직선 l, BD=20·CE=9 ───────────────────────────────
u3 = 8.0
AB3 = math.sqrt(20 ** 2 + 9 ** 2)
A3 = (44.0, 206.0)
B3 = (A3[0] + AB3 * u3, A3[1])
C3 = (A3[0], A3[1] - AB3 * u3)
th3 = math.degrees(math.asin(20 / AB3))                 # l 과 AB 사이 각
D3 = polar(A3, th3, 9 * u3)
E3 = polar(A3, th3, 20 * u3)
L3 = polar(A3, th3, 20 * u3 + 28)
verify_figure("s3", lengths=[(20, B3, D3), (9, C3, E3), (9, A3, D3), (20, A3, E3)],
              angles=[(90, A3, B3, C3), (90, D3, A3, B3), (90, E3, A3, C3)])
S["s3"] = fig((250, 238), pts(A=A3, B=B3, C=C3, D=D3, E=E3, l=L3),
              {"AB": seg("A", "B", ticks=2), "AC": seg("A", "C", ticks=2), "BC": seg("B", "C"),
               "AD": seg("A", "D"), "DE": seg("D", "E"), "El": seg("E", "l"), "BD": seg("B", "D"), "CE": seg("C", "E")},
              angles={"rA": ang("A", "B", "C", right=True),
                      "rD": ang("D", "E", "B", right=True),
                      "rE": ang("E", "D", "C", right=True)},
              dims={"dimCE": dim("C", "E", "9 cm", side="auto"),
                    "dimDB": dim("D", "B", "20 cm", side="left", offset=10)},
              labels={"A": "A", "B": "B", "C": "C", "D": "D", "E": "E",
                      "l": {"text": "l", "italic": True}})

# ── s4: 직각 A, AB=15·AC=8·BC=17 ─────────────────────────────────────
u4 = 13.0
B4 = (26.0, 166.0)
C4 = (B4[0] + 17 * u4, B4[1])
ax4 = (225 - 64 + 289) / 34.0
A4 = (B4[0] + ax4 * u4, B4[1] - math.sqrt(225 - ax4 * ax4) * u4)
verify_figure("s4", lengths=[(15, A4, B4), (8, A4, C4), (17, B4, C4)],
              angles=[(90, A4, B4, C4)])
S["s4"] = fig((290, 210), pts(A=A4, B=B4, C=C4),
              {"AB": seg("A", "B"), "AC": seg("A", "C"), "BC": seg("B", "C")},
              angles={"rA": ang("A", "B", "C", right=True)},
              dims={"dimAB": dim("B", "A", "15", side="auto"),
                    "dimAC": dim("A", "C", "8", side="auto"),
                    "dimBC": dim("B", "C", "17", side="auto")})


if __name__ == "__main__":
    from core.figure_generator import _svg_to_png_bytes

    miss = unverified(S)
    if miss:
        raise SystemExit(f"검산 누락(verify_figure 미호출): {miss}")
    only = set(sys.argv[1:])
    bad = 0
    for k, svg in S.items():
        if only and k not in only:
            continue
        issues = lint_svg(svg)
        if issues:
            bad += 1
            print(f"{k} LINT 실패:")
            for it in issues:
                print("   -", it)
        png = _svg_to_png_bytes(svg, width=int(
            float(svg.split('viewBox="')[1].split()[2]) * 4))
        if not png:
            print(k, "PNG 실패")
            bad += 1
            continue
        with open(os.path.join(OUT, f"{k}.png"), "wb") as f:
            f.write(png)
        print(k, "ok" if not issues else "png(lint fail)", "→", os.path.join(OUT, f"{k}.png"))
    raise SystemExit(1 if bad else 0)
