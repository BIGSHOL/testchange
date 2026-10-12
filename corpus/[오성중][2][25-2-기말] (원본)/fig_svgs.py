# -*- coding: utf-8 -*-
"""오성중2 25-2-기말 — 그림 16개. FigureSpec v2(core.figure_scene) 선언형 작도.

좌표는 전부 문제 조건(길이·각·비)에서 계산한다(눈대중 금지). 스펙이 못 그리는
요소(여러 선분에 걸친 치수, 같은 각 •, 깃대, <보기> 틀)만 해석된 translation 에
맞춰 덧그린다. 원뿔(q6)·정칠각형(q11)·원판(q15)은 스펙 밖 도형이라
core.figure_svg 프리미티브로 직접 그린다. 화면 좌표 y 는 아래로.
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
from core.figure_scene import compile_figure_spec  # noqa: E402
from core.figure_quality import sanitize_svg  # noqa: E402
from core.figure_svg import (curve_path, leader, line, lint_svg, meas, rangle, txt,  # noqa: E402
                             unverified, verify_figure)
from core.label_markup import label_pieces_svg, label_width_em  # noqa: E402

OUT = os.environ.get(
    "FIG_SVG_OUT",
    str(Path(tempfile.gettempdir()) / "exam_figure_svg" / "oseong2"),
)
os.makedirs(OUT, exist_ok=True)
S = {}
FS = 16.8  # 스펙 라벨과 같은 크기(렌더 SVG font-size 실측)
SPEC_FONT = 'font-family="Cambria Math, HancomEQN, Times New Roman, serif"'
ITALIC_FONT = "Cambria, Times New Roman, serif"   # StyleProfile.font_family_italic 과 동일
GRAY = "#e3e3e3"


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


def frame(ox, oy, s):
    """수학 좌표(y 위, 단위) → 화면 좌표."""
    return lambda x, y: P(ox + x * s, oy - y * s)


def sss(a, b, c):
    """밑변 c(B=(0,0), C=(c,0)), AB=a, AC=b 인 삼각형의 A(수학 좌표)."""
    x = (a * a + c * c - b * b) / (2 * c)
    return (x, math.sqrt(a * a - x * x))


# ── 덧그림 헬퍼(스펙 라벨과 같은 글꼴·조판) ──────────────────────────────────
def ltext(x, y, label, fs=FS, anc="middle"):
    """(x, y) 를 세로 중심으로 하는 라벨 — 변수 이탤릭·단위 정자·위첨자(label_markup)."""
    return (f'<text x="{x:.2f}" y="{y + 0.35 * fs:.2f}" {SPEC_FONT} font-size="{fs}" '
            f'text-anchor="{anc}" fill="#111111">{label_pieces_svg(label, fs, ITALIC_FONT)}</text>')


def curve_pt(p, q, off, t):
    """meas() 치수 곡선 위의 점과 바깥쪽 단위 법선."""
    ux, uy = unit(p, q)
    nx, ny = -uy, ux
    end = 1.5 * (1.0 if off >= 0 else -1.0)
    s = (p[0] + nx * end, p[1] + ny * end)
    e = (q[0] + nx * end, q[1] + ny * end)
    c_lat = 2.0 * off - end
    c = ((p[0] + q[0]) / 2 + nx * c_lat, (p[1] + q[1]) / 2 + ny * c_lat)
    x = (1 - t) ** 2 * s[0] + 2 * t * (1 - t) * c[0] + t * t * e[0]
    y = (1 - t) ** 2 * s[1] + 2 * t * (1 - t) * c[1] + t * t * e[1]
    sg = 1.0 if off >= 0 else -1.0
    return (x, y), (nx * sg, ny * sg)


def adim(p, q, off, label, t=0.5, gap=3.5, fs=FS):
    """치수 점선(양끝이 p·q 에 닿음) + 곡선 **바깥**에 붙인 라벨. off 부호 = 볼록한 쪽."""
    (x, y), (nx, ny) = curve_pt(p, q, off, t)
    hw = label_width_em(label) * fs / 2
    hh = 0.36 * fs
    d = gap + abs(hw * nx) + abs(hh * ny)
    return meas(p[0], p[1], q[0], q[1], off) + ltext(x + nx * d, y + ny * d, label, fs)


def sdots(*ps, r=2.3):
    return "".join(f'<circle cx="{p[0]:.2f}" cy="{p[1]:.2f}" r="{r}" fill="#111111"/>' for p in ps)


# ── 스펙 조립 ────────────────────────────────────────────────────────────────
def render(key, pts, segs, angles=None, dims=None, labels=None, regions=None,
           circles=None, pre=None, post=None):
    """FigureSpec v2 → SVG. pre/post(sh)->str 는 스펙이 못 그리는 덧그림(sh = 좌표 이동 함수)."""
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

    def sh(p):
        return (p[0] + tx, p[1] + ty)

    if pre:
        i = svg.index("/>", svg.index("<rect")) + 2
        svg = svg[:i] + "\n" + pre(sh) + svg[i:]
    if post:
        i = svg.rindex("</svg>")
        svg = svg[:i] + post(sh) + "\n" + svg[i:]
    S[key] = sanitize_svg(svg)
    return spec


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
    S[key] = sanitize_svg(f'<svg viewBox="0 0 {w:.0f} {h:.0f}" xmlns="http://www.w3.org/2000/svg">\n'
                          + "\n".join(parts) + "\n</svg>")


# ── q1: □ABCD∽□AEFG∽□HIJA. AD=4·DH=8·HG=8·HI=9 → AB=3, AE=15, BE=12 ─────────────
# 모양(변의 방향)은 원본 그림에서, 길이는 조건에서: AB=3, AD=4. 큰 것은 A 중심 5배,
# □HIJA 는 A→H, D→A 로 가는 3배 점대칭 닮음(P ↦ H − 3(P − A)).
_ub, _ud = unit((0, 0), (-60, 27)), unit((0, 0), (40, 79))
_qB, _qD = (3 * _ub[0], 3 * _ub[1]), (4 * _ud[0], 4 * _ud[1])
_qC = (-3.30, _qD[1])
_k1 = 10.5


def _s1(p, m=1.0, org=(0.0, 0.0), sign=1.0):
    return P(196 + (org[0] + sign * m * p[0]) * _k1, 14 + (org[1] + sign * m * p[1]) * _k1)


A, B, C, D = _s1((0, 0)), _s1(_qB), _s1(_qC), _s1(_qD)
E, F, G = _s1(_qB, 5), _s1(_qC, 5), _s1(_qD, 5)
_qH = (3 * _qD[0], 3 * _qD[1])
H = _s1(_qH)
I, J = _s1(_qB, 3, _qH, -1.0), _s1(_qC, 3, _qH, -1.0)
verify_figure("q1", lengths=[(4, A, D), (8, D, H), (8, H, G), (9, H, I), (3, A, B), (12, B, E), (15, A, E),
                             (20, A, G), (12, H, A)],
              on_line=[(B, A, E), (D, A, G), (H, A, G)])
# 닮음 검산: 대응변의 비 1 : 5 : 3
for _p, _q, _P5, _Q5, _P3, _Q3 in ((B, C, E, F, I, J), (C, D, F, G, J, A)):
    assert math.isclose(dist(_P5, _Q5), 5 * dist(_p, _q), rel_tol=1e-9)
    assert math.isclose(dist(_P3, _Q3), 3 * dist(_p, _q), rel_tol=1e-9)
render("q1", {"A": A, "B": B, "C": C, "D": D, "E": E, "F": F, "G": G, "H": H, "I": I, "J": J},
       {"AB": ["A", "B"], "BE": ["B", "E"], "BC": ["B", "C"], "CD": ["C", "D"], "AD": ["A", "D"],
        "DH": ["D", "H"], "HG": ["H", "G"], "EF": ["E", "F"], "FG": ["F", "G"], "HI": ["H", "I"],
        "IJ": ["I", "J"], "JA": ["J", "A"]},
       None,
       {"dAD": dim("A", "D", "4"), "dDH": dim("D", "H", "8"), "dHG": dim("H", "G", "8"),
        "dHI": dim("H", "I", "9")})

# ── q2: <보기> 여섯 그림 — BC∥DE 인가 ───────────────────────────────────────────
W2, H2 = 580, 584
_pts2, _segs2, _labels2, _over2 = {}, {}, {}, []


def _panel(i, pts, segs):
    for k, v in pts.items():
        _pts2[f"{k}{i}"] = v
        _labels2[f"{k}{i}"] = k
    for a, b in segs:
        _segs2[f"{a}{b}{i}"] = [f"{a}{i}", f"{b}{i}"]


# ㄱ: △ABC, AD=12·AB=16, AE=9·AC=12 (3:4 = 3:4 → 평행)
_f = frame(50, 196, 11.5)
_a = sss(16, 12, 13.7)
A, B, C = _f(*_a), _f(0, 0), _f(13.7, 0)
D, E = add(A, B, 0.75), add(A, C, 0.75)
verify_figure("q2", lengths=[(12, A, D), (16, A, B), (9, A, E), (12, A, C)],
              on_line=[(D, A, B), (E, A, C)])
_panel(1, {"A": A, "B": B, "C": C, "D": D, "E": E},
       [("A", "D"), ("D", "B"), ("B", "C"), ("C", "E"), ("E", "A"), ("D", "E")])
_g1 = (A, B, C, D, E)

# ㄴ: 맞꼭지각 꼴. DE=2·EA=3·AC=6·CB=4 — AE:AC=DE:BC 이지만 끼인각이 아니라 평행 아님
_th = math.radians(40.0)
_d = (6 * math.cos(_th) + math.sqrt(36 * math.cos(_th) ** 2 - 20)) / 2      # AD: d²−6d·cosθ+5=0 (큰 근)
_b = (12 * math.cos(_th) - math.sqrt(144 * math.cos(_th) ** 2 - 80)) / 2    # AB: b²−12b·cosθ+20=0 (작은 근)
_f = frame(398, 112, 24.0)
A = _f(0, 0)
C, E = polar(A, 14.5, 6 * 24.0), polar(A, 14.5 + 180, 3 * 24.0)
B, D = polar(A, -25.5, _b * 24.0), polar(A, -25.5 + 180, _d * 24.0)
verify_figure("q2-ㄴ", lengths=[(2, D, E), (3, E, A), (6, A, C), (4, C, B)],
              on_line=[(A, D, B), (A, E, C)])
assert not math.isclose(_d / _b, 0.5, abs_tol=0.05)          # AD:AB ≠ 1:2 → 닮음이 아니다
_panel(2, {"A": A, "B": B, "C": C, "D": D, "E": E},
       [("D", "A"), ("A", "B"), ("E", "A"), ("A", "C"), ("D", "E"), ("C", "B")])
_g2 = (A, B, C, D, E)

# ㄷ: 맞꼭지각 꼴. ED=4·EA=3·AC=5·BC=6 (3:5 ≠ 4:6 → 평행 아님)
_th = math.radians(73.0)
_d = (6 * math.cos(_th) + math.sqrt(36 * math.cos(_th) ** 2 + 28)) / 2      # AD: d²−6d·cosθ−7=0
_b = (10 * math.cos(_th) + math.sqrt(100 * math.cos(_th) ** 2 + 44)) / 2    # AB: b²−10b·cosθ−11=0
_f = frame(150, 288, 20.5)
A = _f(0, 0)
C, E = polar(A, -54.5, 5 * 20.5), polar(A, -54.5 + 180, 3 * 20.5)
B, D = polar(A, -127.5, _b * 20.5), polar(A, -127.5 + 180, _d * 20.5)
verify_figure("q2-ㄷ", lengths=[(4, E, D), (3, E, A), (5, A, C), (6, B, C)],
              on_line=[(A, E, C), (A, D, B)])
_panel(3, {"A": A, "B": B, "C": C, "D": D, "E": E},
       [("E", "A"), ("A", "C"), ("D", "A"), ("A", "B"), ("E", "D"), ("B", "C")])
_g3 = (A, B, C, D, E)

# ㄹ: △ABC, AD=4·DB=3, AE=5·EC=4 (4:3 ≠ 5:4 → 평행 아님)
_f = frame(376, 372, 21.5)
_a = sss(7, 9, 8.1)
A, B, C = _f(*_a), _f(0, 0), _f(8.1, 0)
D, E = add(A, B, 4 / 7), add(A, C, 5 / 9)
verify_figure("q2-ㄹ", lengths=[(4, A, D), (3, D, B), (5, A, E), (4, E, C)])
_panel(4, {"A": A, "B": B, "C": C, "D": D, "E": E},
       [("A", "D"), ("D", "B"), ("B", "C"), ("C", "E"), ("E", "A"), ("D", "E")])
_g4 = (A, B, C, D, E)

# ㅁ: △ADE, AB=9·BD=3, AC=6·CE=2 (3:1 = 3:1 → 평행)
_f = frame(60, 556, 19.5)
_a = sss(12, 8, 7.7)
A, D, E = _f(*_a), _f(0, 0), _f(7.7, 0)
B, C = add(A, D, 0.75), add(A, E, 0.75)
verify_figure("q2-ㅁ", lengths=[(9, A, B), (3, B, D), (6, A, C), (2, C, E)])
_panel(5, {"A": A, "B": B, "C": C, "D": D, "E": E},
       [("A", "B"), ("B", "D"), ("D", "E"), ("E", "C"), ("C", "A"), ("B", "C")])
_g5 = (A, B, C, D, E)

# ㅂ: 맞꼭지각 꼴. BD=20·AD=8(→AB=12), EC=15·EA=6(→AC=9) (12:8 = 9:6 → 평행)
_f = frame(462, 462, 11.5)
A = _f(0, 0)
D, B = polar(A, -28.0, 8 * 11.5), polar(A, -28.0 + 180, 12 * 11.5)
C, E = polar(A, -117.5, 9 * 11.5), polar(A, -117.5 + 180, 6 * 11.5)
verify_figure("q2-ㅂ", lengths=[(20, B, D), (6, E, A), (8, A, D), (15, E, C)],
              on_line=[(A, B, D), (A, E, C)])
_panel(6, {"A": A, "B": B, "C": C, "D": D, "E": E},
       [("B", "A"), ("A", "D"), ("E", "A"), ("A", "C"), ("B", "C"), ("E", "D")])
_g6 = (A, B, C, D, E)
_labels2["A6"] = {"text": "A", "position": "W"}
_pts2["Z1"], _pts2["Z2"] = P(0, 0), P(W2, H2)


def _q2_frame(sh):
    x0, y0 = sh((6, 16))
    x1, y1 = sh((W2 - 6, H2 - 6))
    mid = (x0 + x1) / 2
    return (f'<path d="M {mid - 62:.1f} {y0:.1f} L {x0:.1f} {y0:.1f} L {x0:.1f} {y1:.1f} L {x1:.1f} {y1:.1f} '
            f'L {x1:.1f} {y0:.1f} L {mid + 62:.1f} {y0:.1f}" fill="none" stroke="#111111" stroke-width="1.2"/>'
            + txt(mid, y0 + 5.5, "< 보 기 >", 15))


def _q2_over(sh):
    out = []
    for name, pos in (("ㄱ.", (26, 50)), ("ㄴ.", (306, 50)), ("ㄷ.", (26, 232)), ("ㄹ.", (306, 232)),
                      ("ㅁ.", (26, 412)), ("ㅂ.", (306, 412))):
        out.append(txt(*sh(pos), name, 15, anc="start"))
    # ㄱ — 안쪽(AD·AE)은 지시선 라벨, 바깥쪽(AB·AC)은 곡선 밖 라벨
    A, B, C, D, E = map(sh, _g1)
    out += [meas(*A, *D, 8), adim(A, B, 32, "16 cm", t=0.58),
            meas(*A, *E, -8), adim(A, C, -30, "12 cm", t=0.60)]
    (ax, ay), _ = curve_pt(A, D, 8, 0.36)
    lx, ly = A[0] - 104, A[1] + 4
    out += [ltext(lx, ly, "12 cm"), leader((lx + 22, ly + 4), (ax, ay), w=0.72, head=5.5, gap=2.0)]
    (ax, ay), _ = curve_pt(A, E, -8, 0.42)
    lx, ly = A[0] + 58, A[1] + 6
    out += [ltext(lx, ly, "9 cm"), leader((lx - 16, ly + 7), (ax, ay), w=0.72, head=5.5, gap=2.0)]
    # ㄴ
    A, B, C, D, E = map(sh, _g2)
    out += [adim(D, E, 9, "2 cm"), adim(E, A, 9, "3 cm"), adim(A, C, -9, "6 cm"), adim(C, B, -9, "4 cm")]
    # ㄷ
    A, B, C, D, E = map(sh, _g3)
    out += [adim(E, D, -9, "4 cm"), adim(E, A, 9, "3 cm"), adim(A, C, -9, "5 cm"), adim(B, C, 9, "6 cm")]
    # ㄹ
    A, B, C, D, E = map(sh, _g4)
    out += [adim(A, D, 9, "4 cm"), adim(D, B, 9, "3 cm"), adim(A, E, -9, "5 cm"), adim(E, C, -9, "4 cm")]
    # ㅁ
    A, B, C, D, E = map(sh, _g5)
    out += [adim(A, B, 9, "9 cm"), adim(B, D, 9, "3 cm"), adim(A, C, -9, "6 cm"), adim(C, E, -9, "2 cm")]
    # ㅂ — BD·EC 는 두 선분에 걸친 전체 길이
    A, B, C, D, E = map(sh, _g6)
    out += [adim(B, D, -14, "20 cm", t=0.20), adim(A, D, 9, "8 cm"),
            adim(E, A, 9, "6 cm"), adim(E, C, -15, "15 cm", t=0.78)]
    return "".join(out)


render("q2", _pts2, _segs2, labels=_labels2, pre=_q2_frame, post=_q2_over)

# ── q3: 한 변이 4 인 정사각형, M=BC 중점, ∠AMN=90° → CN=1 ─────────────────────
_f = frame(40, 180, 40.0)
A, D, B, C = _f(0, 4), _f(4, 4), _f(0, 0), _f(4, 0)
M, N = _f(2, 0), _f(4, 1)
verify_figure("q3", lengths=[(4, A, B), (4, B, C), (2, B, M), (2, M, C), (1, C, N), (3, N, D)],
              angles=[(90, M, A, N), (90, B, A, C)])
render("q3", {"A": A, "B": B, "C": C, "D": D, "M": M, "N": N},
       {"AB": ["A", "B"], "BM": seg("B", "M", ticks=2), "MC": seg("M", "C", ticks=2),
        "CN": ["C", "N"], "ND": ["N", "D"], "DA": ["D", "A"],
        "AM": ["A", "M"], "DM": ["D", "M"], "MN": ["M", "N"]},
       {"rM": ang("M", "A", "N", right=True)},
       {"dAB": dim("A", "B", "4")},
       labels={"A": "A", "B": "B", "C": "C", "D": "D", "M": {"text": "M", "position": "S"},
               "N": {"text": "N", "position": "E"}})

# ── q4: 닮은 깃발 셋(꼭지각 40°·밑각 70°인 이등변삼각형) ───────────────────────────
# 원본처럼 세 그림의 척도는 서로 다르다(큰 것을 줄여 그림) — 각 삼각형 안의 길이·각만 맞춘다.
C = P(178, 222)
A, B = polar(C, 120, 140), polar(C, 160, 140)
Ff = P(372, 204)
Dd, Ee = polar(Ff, 140, 118), polar(Ff, 180, 118)
Ii = P(502, 150)
Gg, Hh = polar(Ii, 194, 70), polar(Ii, 234, 70)
verify_figure("q4", lengths=[(75, A, C), (75, B, C)], angles=[(40, C, A, B), (70, A, B, C), (70, B, A, C)])
verify_figure("q4-중간", lengths=[(50, Dd, Ff), (50, Ee, Ff)], angles=[(70, Dd, Ee, Ff), (40, Ff, Dd, Ee)])
verify_figure("q4-작은", lengths=[(25, Gg, Ii), (25, Hh, Ii)], angles=[(40, Ii, Gg, Hh), (70, Gg, Hh, Ii)])


def _q4_poles(sh):
    out = []
    for top, bot, ext in ((A, B, 0.30), (Dd, Ee, 0.22), (Gg, Hh, 0.32)):
        p, q = sh(top), sh(add(top, bot, 1 + ext))
        out.append(f'<line x1="{p[0]:.1f}" y1="{p[1]:.1f}" x2="{q[0]:.1f}" y2="{q[1]:.1f}" '
                   f'stroke="#8a8a8a" stroke-width="4.5" stroke-linecap="round"/>')
    return "".join(out)


render("q4", {"A": A, "B": B, "C": C, "D": Dd, "E": Ee, "F": Ff, "G": Gg, "H": Hh, "I": Ii,
              "Z1": P(14, 54), "Z2": P(532, 238)},
       {"AB": ["A", "B"], "BC": ["B", "C"], "CA": ["C", "A"], "DE": ["D", "E"], "EF": ["E", "F"],
        "FD": ["F", "D"], "GH": ["G", "H"], "HI": ["H", "I"], "IG": ["I", "G"]},
       {"angD": ang("D", "E", "F", "70°"), "angF": ang("F", "D", "E", "40°", label_distance=52),
        "angI": ang("I", "G", "H", "40°", radius=14, label_distance=42)},
       None,
       labels={**{k: k for k in "ABCDEFGI"}, "H": {"text": "H", "position": "SW"}},
       pre=_q4_poles,
       post=lambda sh: "".join(txt(*sh((x, 72)), name, 15)
                               for x, name in ((112, "큰 깃발"), (318, "중간 깃발"), (470, "작은 깃발")))
       + adim(sh(A), sh(C), -12, "75cm") + adim(sh(B), sh(C), 12, "75cm")
       + adim(sh(Dd), sh(Ff), -11, "50cm") + adim(sh(Gg), sh(Ii), -10, "25cm"))

# ── q5: AB∥FC∥ED, FB∥EC → FC²=AB·ED, FC=10 ───────────────────────────────────
_f = frame(52, 196, 11.0)
B, C, D = _f(0, 0), _f(8, 0), _f(24, 0)
A, F, E = _f(-3, 4), _f(2, 8), _f(12, 16)
verify_figure("q5", lengths=[(5, A, B), (10, F, C), (20, E, D), (8, B, C), (16, C, D)],
              on_line=[(F, A, E), (C, B, D)])
for _p, _q, _r, _s in ((A, B, F, C), (F, C, E, D), (F, B, E, C)):                      # 평행 검산
    assert abs((_q[0] - _p[0]) * (_s[1] - _r[1]) - (_q[1] - _p[1]) * (_s[0] - _r[0])) < 1e-6
render("q5", {"A": A, "B": B, "C": C, "D": D, "E": E, "F": F},
       {"AF": ["A", "F"], "FE": ["F", "E"], "BA": seg("B", "A", parallel=1), "BC": ["B", "C"],
        "CD": ["C", "D"], "DE": seg("D", "E", parallel=1), "BF": seg("B", "F", parallel=2),
        "CF": seg("C", "F", parallel=1), "CE": seg("C", "E", parallel=2)},
       None,
       {"dAB": dim("A", "B", "5"), "dED": dim("E", "D", "20")})

# ── q6: 원뿔(반지름 5)을 밑면에 평행하게 자름 — 반지름 2·4·5, 높이 2:2:1 ───────────
_cx, _ty, _Hc, _u6 = 130.0, 14.0, 250.0, 20.0
T6 = P(_cx, _ty)
_lv = {r: P(_cx, _ty + _Hc * r / 5) for r in (2, 4, 5)}
_rim = {r: P(_cx - r * _u6, _lv[r][1]) for r in (2, 4, 5)}
verify_figure("q6", lengths=[(2, _lv[2], _rim[2]), (4, _lv[4], _rim[4]), (5, _lv[5], _rim[5])])
verify_figure("q6-높이", lengths=[(2, _lv[2], _lv[4]), (1, _lv[4], _lv[5])])
verify_figure("q6-닮음", lengths=[(2, T6, _lv[2]), (4, T6, _lv[4]), (5, T6, _lv[5])])


def _ellipse(c, rx, ry, a0, a1, n=40):
    return [(c[0] + rx * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             c[1] - ry * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


_p6 = []
_b5 = 0.10 * 5 * _u6
_tx = 5 * _u6 * math.sqrt(1 - (_b5 / _Hc) ** 2)          # 꼭짓점에서 밑면 타원에 그은 접선의 접점
_tyy = _lv[5][1] - _b5 * _b5 / _Hc
_p6 += [line(T6, P(_cx - _tx, _tyy), w=1.9), line(T6, P(_cx + _tx, _tyy), w=1.9),
        line(T6, _lv[5], w=1.1)]
for _r in (2, 4, 5):
    _rx, _ry = _r * _u6, 0.10 * _r * _u6
    _p6 += [curve_path(_ellipse(_lv[_r], _rx, _ry, 180, 360), w=1.9),
            curve_path(_ellipse(_lv[_r], _rx, _ry, 0, 180), w=1.0, dash="5 4"),
            rangle(_lv[_r][0], _lv[_r][1], -1, 0, 0, -1, 7)]
_p6 += [adim(_rim[4], _lv[4], -15, "4", gap=2.5), adim(_rim[5], _lv[5], -15, "5", gap=2.5),
        ltext(_cx + 13, _lv[2][1] - 16, "A"), ltext(_cx + 30, (_lv[2][1] + _lv[4][1]) / 2 + 6, "B"),
        ltext(_cx + 42, (_lv[4][1] + _lv[5][1]) / 2 + 6, "C")]
raw_svg("q6", 260, 292, *_p6)

# ── q7: 세 변의 중점 D·E·F, DF=2FP → △AEP = ½·△ABC ─────────────────────────────
_f = frame(30, 204, 22.0)
A, B, C = _f(1.96, 7.87), _f(0, 0), _f(12, 0)
D, E, F = add(A, B, 0.5), add(B, C, 0.5), add(A, C, 0.5)
Pp = add(D, F, 1.5)
verify_figure("q7", lengths=[(2, D, F), (1, F, Pp)], on_line=[(F, D, Pp)])
verify_figure("q7-D", lengths=[(1, A, D), (1, D, B)])
verify_figure("q7-E", lengths=[(1, B, E), (1, E, C)])
verify_figure("q7-F", lengths=[(1, A, F), (1, F, C)])


def _tri_area(p, q, r):
    return abs((q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])) / 2


assert math.isclose(_tri_area(A, E, Pp), _tri_area(A, B, C) / 2, rel_tol=1e-9)        # 12 → 6
render("q7", {"A": A, "B": B, "C": C, "D": D, "E": E, "F": F, "P": Pp},
       {"AD": seg("A", "D", ticks=1), "DB": seg("D", "B", ticks=1), "BE": seg("B", "E", ticks=2),
        "EC": seg("E", "C", ticks=2), "AF": seg("A", "F", ticks=3), "FC": seg("F", "C", ticks=3),
        "DF": ["D", "F"], "FP": ["F", "P"], "AE": ["A", "E"], "AP": ["A", "P"], "EP": ["E", "P"]})

# ── q8: ∠BAE=∠AED=∠DCE, AB=6·AE=5·AC=10 → BC=12, BE=3, DE=4.5 ──────────────────
_f = frame(22, 158, 26.0)
_a = sss(6, 10, 12)
A, B, C, E = _f(*_a), _f(0, 0), _f(12, 0), _f(3, 0)
D = add(C, A, 0.75)
_t8 = angle_at(A, B, E)
verify_figure("q8", lengths=[(6, A, B), (5, A, E), (10, A, C), (4.5, D, E), (3, B, E), (9, E, C)],
              angles=[(_t8, E, A, D), (_t8, C, D, E)], on_line=[(D, A, C)])
render("q8", {"A": A, "B": B, "C": C, "D": D, "E": E},
       {"AB": ["A", "B"], "BE": ["B", "E"], "EC": ["E", "C"], "CD": ["C", "D"], "DA": ["D", "A"],
        "AE": ["A", "E"], "ED": ["E", "D"]},
       {"angA": ang("A", "B", "E"), "angE": ang("E", "A", "D"), "angC": ang("C", "D", "E")},
       {"dAB": dim("A", "B", "6")},
       # AE=5 는 좁은 △AED 안(원본 위치) — 스펙 배치가 자리를 못 찾아 직접 둔다.
       post=lambda sh: adim(sh(A), sh(C), -20, "10", t=0.52) + adim(sh(A), sh(E), -8, "5", t=0.55, gap=2.0))

# ── q9: 사다리꼴 AD∥BC, BC=12·MN=9 → AD=6, GG′=2 ─────────────────────────────────
_f = frame(34, 254, 20.0)
A, D, B, C = _f(4.9, 11.1), _f(10.9, 11.1), _f(0, 0), _f(12, 0)
M, N, H = add(A, B, 0.5), add(D, C, 0.5), add(B, C, 0.5)
G = P((A[0] + B[0] + C[0]) / 3, (A[1] + B[1] + C[1]) / 3)
G2 = P((D[0] + B[0] + C[0]) / 3, (D[1] + B[1] + C[1]) / 3)
verify_figure("q9", lengths=[(12, B, C), (9, M, N), (6, A, D), (2, G, G2)],
              on_line=[(G, A, H), (G2, D, H)])
verify_figure("q9-M", lengths=[(1, A, M), (1, M, B)])
verify_figure("q9-N", lengths=[(1, D, N), (1, N, C)])
verify_figure("q9-H", lengths=[(1, B, H), (1, H, C)])
verify_figure("q9-G", lengths=[(2, A, G), (1, G, H)])
verify_figure("q9-G2", lengths=[(2, D, G2), (1, G2, H)])
render("q9", {"A": A, "B": B, "C": C, "D": D, "M": M, "N": N, "H": H, "G": G, "K": G2,
              "Zz": P((B[0] + C[0]) / 2, B[1] + 44)},
       {"AD": seg("A", "D", parallel=1), "AM": seg("A", "M", ticks=1), "MB": seg("M", "B", ticks=1),
        "BH": seg("B", "H", ticks=3, parallel=1), "HC": seg("H", "C", ticks=3),
        "CN": seg("C", "N", ticks=2), "ND": seg("N", "D", ticks=2), "MN": ["M", "N"],
        "AC": ["A", "C"], "DB": ["D", "B"], "AG": ["A", "G"], "GH": ["G", "H"],
        "DK": ["D", "K"], "KH": ["K", "H"], "GK": ["G", "K"]},
       labels={"A": "A", "B": "B", "C": "C", "D": "D", "M": {"text": "M", "position": "W"},
               "N": {"text": "N", "position": "E"}, "H": {"text": "H", "position": "S"},
               "G": {"text": "G", "position": "W"}, "K": {"text": "G'", "position": "E"}},
       post=lambda sh: adim(sh(M), sh(N), -9, "9", gap=2.5) + adim(sh(B), sh(C), 30, "12"))

# ── q10: 평행사변형(넓이 330), P=BC 중점, DQ:QC=1:3 → △EPF=27 ────────────────────
_f = frame(22, 204, 26.0)
A, D, B, C = _f(1.31, 6.78), _f(11.31, 6.78), _f(0, 0), _f(10, 0)
Pp = add(B, C, 0.5)
Q = add(D, C, 0.25)
E, F = isect(B, Q, A, Pp), isect(B, Q, Pp, D)
verify_figure("q10", lengths=[(1, B, Pp), (1, Pp, C)],
              on_line=[(E, A, Pp), (E, B, Q), (F, B, Q), (F, Pp, D), (Q, D, C)])
verify_figure("q10-Q", lengths=[(1, D, Q), (3, Q, C)])
assert math.isclose(_tri_area(E, Pp, F) / (2 * _tri_area(A, B, C)), 27 / 330, rel_tol=1e-9)
render("q10", {"A": A, "B": B, "C": C, "D": D, "P": Pp, "Q": Q, "E": E, "F": F},
       {"AB": ["A", "B"], "BP": seg("B", "P", ticks=2), "PC": seg("P", "C", ticks=2), "CQ": ["C", "Q"],
        "QD": ["Q", "D"], "DA": ["D", "A"], "AE": ["A", "E"], "EP": ["E", "P"], "BE": ["B", "E"],
        "EF": ["E", "F"], "FQ": ["F", "Q"], "PF": ["P", "F"], "FD": ["F", "D"]},
       labels={"A": "A", "B": "B", "C": "C", "D": "D", "P": {"text": "P", "position": "S"},
               "Q": {"text": "Q", "position": "E"}, "E": "E", "F": "F"})

# ── q11: 직각삼각형의 세 변 위의 정칠각형(넓이 4·x·16 → 변의 비 2 : 2√3 : 4) ───────
_k11 = 19.0
_C = (0.0, 0.0)
_A = (-2 * _k11, 0.0)
_B = (0.0, 2 * math.sqrt(3) * _k11)


def _hept(p, q, away):
    """선분 pq 를 한 변으로 하고 점 away 의 반대쪽에 놓이는 정칠각형의 꼭짓점."""
    best = None
    for sg in (1, -1):
        vs, d = [p, q], (q[0] - p[0], q[1] - p[1])
        for _ in range(5):
            a = math.radians(sg * 360 / 7)
            d = (d[0] * math.cos(a) - d[1] * math.sin(a), d[0] * math.sin(a) + d[1] * math.cos(a))
            vs.append((vs[-1][0] + d[0], vs[-1][1] + d[1]))
        cen = (sum(v[0] for v in vs) / 7, sum(v[1] for v in vs) / 7)
        if best is None or dist(cen, away) > dist(best[1], away):
            best = (vs, cen)
    return best


_h1, _c1 = _hept(_A, _C, _B)          # AC 위(넓이 4)
_h2, _c2 = _hept(_C, _B, _A)          # BC 위(넓이 x)
_h3, _c3 = _hept(_B, _A, _C)          # AB 위(넓이 16)
_allp = _h1 + _h2 + _h3
_ox, _oy = 12 - min(p[0] for p in _allp), 12 - min(p[1] for p in _allp)


def _m11(p):
    return P(p[0] + _ox, p[1] + _oy)


A, B, C = _m11(_A), _m11(_B), _m11(_C)
verify_figure("q11", lengths=[(2, A, C), (math.sqrt(12), B, C), (4, A, B)], angles=[(90, C, A, B)])
for _hp, _side in ((_h1, 2), (_h2, math.sqrt(12)), (_h3, 4)):                  # 정칠각형 검산
    for _i in range(7):
        assert math.isclose(dist(_hp[_i], _hp[(_i + 1) % 7]), _side * _k11, rel_tol=1e-9)


def _hept_area(vs):
    return abs(sum(vs[i][0] * vs[(i + 1) % 7][1] - vs[(i + 1) % 7][0] * vs[i][1] for i in range(7))) / 2


assert math.isclose(_hept_area(_h1) / _hept_area(_h3), 4 / 16, rel_tol=1e-9)
assert math.isclose(_hept_area(_h2) / _hept_area(_h3), 12 / 16, rel_tol=1e-9)
_w11 = max(p[0] for p in _allp) + _ox + 12
_h11 = max(p[1] for p in _allp) + _oy + 12
raw_svg("q11", _w11, _h11,
        *[curve_path([_m11(v) for v in hp], w=1.9, close=True) for hp in (_h1, _h2, _h3)],
        rangle(C[0], C[1], -1, 0, 0, 1, 7),
        ltext(A[0] - 6, A[1] + 15, "A"), ltext(B[0] + 15, B[1] - 3, "B"), ltext(C[0] + 13, C[1] + 9, "C"),
        ltext(*_m11(_c1), "4 cm^2"), ltext(*_m11(_c2), "x cm^2"), ltext(*_m11(_c3), "16 cm^2"))

# ── q12: ∠C=90°, BC=16·AC=12, AD 는 ∠A 의 이등분선 → BD=10·DC=6, AD²=180 ─────────
_f = frame(24, 196, 14.0)
A, B, C, D = _f(16, 12), _f(0, 0), _f(16, 0), _f(10, 0)
E = foot(D, A, B)
verify_figure("q12", lengths=[(16, B, C), (12, A, C), (20, A, B), (10, B, D), (6, D, C), (6, D, E),
                              (math.sqrt(180), A, D)],
              angles=[(90, C, B, A), (90, E, D, A), (angle_at(A, B, D), A, D, C)])
render("q12", {"A": A, "B": B, "C": C, "D": D, "E": E,
               "Zz": P((B[0] + C[0]) / 2, B[1] + 42), "Zy": P(C[0] + 44, (A[1] + C[1]) / 2)},
       {"BE": ["B", "E"], "EA": ["E", "A"], "BD": ["B", "D"], "DC": ["D", "C"], "CA": ["C", "A"],
        "AD": ["A", "D"], "DE": ["D", "E"]},
       {"rC": ang("C", "D", "A", right=True), "rE": ang("E", "D", "A", right=True)},
       labels={"A": "A", "B": "B", "C": {"text": "C", "position": "SE"},
               "D": {"text": "D", "position": "S"}, "E": {"text": "E", "position": "NW"}},
       post=lambda sh: sdots(sh(bis_pt(A, B, D, 26)), sh(bis_pt(A, D, C, 26)), r=1.7)
       + adim(sh(B), sh(C), 26, "16") + adim(sh(C), sh(A), 12, "12"))

# ── q15: 8등분 원판(1·3·…·15), 바늘 ─────────────────────────────────────────────
_c15, _R15 = P(110, 108), 92.0
_p15 = []
for _a0 in (0, -90, 180, 90):                                   # 3·7·11·15 칸 옅은 음영
    _w = [_c15] + _ellipse(_c15, _R15, _R15, _a0, _a0 + 45, 12)
    _p15.append(curve_path(_w, w=0.01, close=True, fill=GRAY))
_p15.append(f'<circle cx="{_c15[0]}" cy="{_c15[1]}" r="{_R15}" fill="none" stroke="#000" stroke-width="1.9"/>')
_rimpts = [polar(_c15, 45 * i, _R15) for i in range(8)]
for _i in range(4):
    _p15.append(line(_rimpts[_i], _rimpts[_i + 4], w=1.1))
verify_figure("q15", angles=[(45, _c15, _rimpts[i], _rimpts[(i + 1) % 8]) for i in range(8)],
              on_circle=[(p, _c15[0], _c15[1], _R15) for p in _rimpts])
for _n, _ang in ((1, 67.5), (3, 22.5), (5, -22.5), (7, -67.5), (9, -112.5), (11, -157.5),
                 (13, 157.5), (15, 112.5)):
    _p15.append(ltext(*polar(_c15, _ang, _R15 * 0.72), str(_n)))
_p15.append(leader(_c15, polar(_c15, 14.0, _R15 * 0.50), arrow=True, w=1.5, head=8.5, gap=0.0))
raw_svg("q15", 220, 216, *_p15)

# ── s1: ∠ABC=∠DAC, AC=20·BC=25 → △ABC∽△DAC, DC=16, BD=9 ───────────────────────
_f = frame(24, 204, 10.0)
_ax = 16.2
A, B, C, D = _f(_ax, math.sqrt(400 - (25 - _ax) ** 2)), _f(0, 0), _f(25, 0), _f(9, 0)
_tB = angle_at(B, A, C)
verify_figure("s1", lengths=[(20, A, C), (25, B, C), (9, B, D), (16, D, C)],
              angles=[(_tB, A, D, C)])
render("s1", {"A": A, "B": B, "C": C, "D": D, "Zz": P((B[0] + C[0]) / 2, B[1] + 44)},
       {"AB": ["A", "B"], "BD": ["B", "D"], "DC": ["D", "C"], "CA": ["C", "A"], "AD": ["A", "D"]},
       {"angB": ang("B", "A", "D"), "angA": ang("A", "D", "C")},
       {"dAC": dim("A", "C", "20")},
       labels={"A": "A", "B": "B", "C": "C", "D": {"text": "D", "position": "S"}},
       # ∠C 안쪽의 굵은 점은 학생 필기(공통각 표시)로 보고 뺐다 — 인쇄 점(q12)보다 훨씬 크고 번졌다.
       post=lambda sh: adim(sh(B), sh(C), 28, "25"))

# ── s2: ∠ACB=90°, AB=17·BC=8 → AC=15. CD=25·DA=20 → ∠CAD=90° → AD∥BC ────────────
_f = frame(96, 176, 9.0)
A, B, C, D = _f(0, 15), _f(-8, 0), _f(0, 0), _f(20, 15)
verify_figure("s2", lengths=[(17, A, B), (8, B, C), (25, C, D), (20, D, A), (15, A, C)],
              angles=[(90, C, B, A), (90, A, C, D)])
render("s2", {"A": A, "B": B, "C": C, "D": D},
       {"AB": ["A", "B"], "BC": ["B", "C"], "CD": ["C", "D"], "DA": ["D", "A"], "AC": ["A", "C"]},
       {"rC": ang("C", "B", "A", right=True)},
       {"dAB": dim("A", "B", "17"), "dBC": dim("B", "C", "8"), "dCD": dim("C", "D", "25"),
        "dDA": dim("D", "A", "20")})

# ── s3: BC∥DE, AD=5·DB=4·AE=6·BC=15 → x=25/3, y=24/5 ───────────────────────────
_f = frame(24, 150, 17.0)
_a = sss(9, 10.8, 15)
A, B, C = _f(*_a), _f(0, 0), _f(15, 0)
D, E = add(A, B, 5 / 9), add(A, C, 5 / 9)
verify_figure("s3", lengths=[(5, A, D), (4, D, B), (6, A, E), (24 / 5, E, C), (25 / 3, D, E), (15, B, C)])
assert abs(D[1] - E[1]) < 1e-9
render("s3", {"A": A, "B": B, "C": C, "D": D, "E": E},
       {"AD": ["A", "D"], "DB": ["D", "B"], "AE": ["A", "E"], "EC": ["E", "C"],
        "DE": seg("D", "E", parallel=1), "BC": seg("B", "C", parallel=1)},
       None,
       {"dAD": dim("A", "D", "5"), "dDB": dim("D", "B", "4"), "dAE": dim("A", "E", "6"),
        "dEC": dim("E", "C", "y"), "dDE": dim("D", "E", "x"), "dBC": dim("B", "C", "15")})


LINT_EXEMPT = {
    # 여섯 칸 그림이라 글자 요소가 61개 — lint 의 픽셀 검수 한도(40)를 넘는다(결함 아님, 육안 검수로 대체).
    "q2": ("텍스트가 픽셀 검수 안전 한도",),
    # 원본 인쇄 그대로 옅은 음영 칸 위의 숫자 — lint 는 음영도 '선 잉크'로 센다.
    "q15": ("라벨-선 겹침: '3'", "라벨-선 겹침: '7'", "라벨-선 겹침: '11'", "라벨-선 겹침: '15'"),
}

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
        png = _svg_to_png_bytes(svg, width=720 if k != "q2" else 1200)
        if not png:
            raise SystemExit(f"{k} PNG 렌더 실패")
        open(os.path.join(OUT, f"{k}.png"), "wb").write(png)
        print(k, "ok" if not issues else "LINT")
    if bad and "--lenient" not in sys.argv:
        raise SystemExit("lint 실패:\n" + "\n".join(bad))
    elif bad:
        print("\n".join(bad))
