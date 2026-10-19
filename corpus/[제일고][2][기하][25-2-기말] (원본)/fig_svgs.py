# -*- coding: utf-8 -*-
"""제일고 고2 기하 25-2-기말 — 그림 5개(1·9·10번, 서술형 4·5).

좌표는 문제 조건에서 계산한다(눈대중 금지). 입체(9·10번, 서술형 4·5)는 3D 좌표를 먼저 세우고
검산(verify_solid)한 뒤 사투영해 core.figure_svg 프리미티브로 그린다. 화면 좌표 y 는 아래로.
학생 필기(10번의 '50', 서술형 4 의 √17·√10·5·호)는 옮기지 않는다.
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
from core.figure_solid import View, verify_solid  # noqa: E402
from core.figure_svg import (curve_path, leader, line, lint_svg, meas, rangle,  # noqa: E402
                             unverified, verify_figure)
from core.label_markup import label_pieces_svg, label_width_em  # noqa: E402

OUT = os.environ.get(
    "FIG_SVG_OUT",
    str(Path(tempfile.gettempdir()) / "exam_figure_svg" / "jeil2geo"),
)
os.makedirs(OUT, exist_ok=True)
S = {}
FS = 16.8  # 스펙 라벨과 같은 크기
SPEC_FONT = 'font-family="Cambria Math, HancomEQN, Times New Roman, serif"'
ITALIC_FONT = "Cambria, Times New Roman, serif"
LIGHT, DARK = "#ececec", "#c6c6c6"     # 앞면(옅은 음영) · 옆면(진한 음영)
HID = dict(w=1.0, dash="5 4")          # 숨은 모서리


# ── 2D 헬퍼 ──────────────────────────────────────────────────────────────────
def add(p, q, t=1.0):
    return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)


def dist(p, q):
    return math.hypot(q[0] - p[0], q[1] - p[1])


def unit(p, q):
    L = dist(p, q)
    return ((q[0] - p[0]) / L, (q[1] - p[1]) / L)


def off(p, dx, dy):
    return (p[0] + dx, p[1] + dy)


def ltext(x, y, label, fs=FS, anc="middle"):
    """(x, y) 를 세로 중심으로 하는 라벨 — 변수 이탤릭·숫자 정자(label_markup)."""
    return (f'<text x="{x:.2f}" y="{y + 0.35 * fs:.2f}" {SPEC_FONT} font-size="{fs}" '
            f'text-anchor="{anc}" fill="#111111">{label_pieces_svg(label, fs, ITALIC_FONT)}</text>')


def rtext(x, y, s, fs=FS, anc="middle"):
    """전부 정자인 라벨(점 이름·'30 m' 처럼 단위가 붙은 수치)."""
    return (f'<text x="{x:.2f}" y="{y + 0.35 * fs:.2f}" {SPEC_FONT} font-size="{fs}" '
            f'text-anchor="{anc}" font-style="normal" fill="#111111">{s}</text>')


def pt_label(p, name, dx, dy):
    return rtext(p[0] + dx, p[1] + dy, name)


def curve_pt(p, q, o, t):
    """meas() 치수 곡선 위의 점과 바깥쪽 단위 법선."""
    ux, uy = unit(p, q)
    nx, ny = -uy, ux
    end = 1.5 * (1.0 if o >= 0 else -1.0)
    s = (p[0] + nx * end, p[1] + ny * end)
    e = (q[0] + nx * end, q[1] + ny * end)
    c_lat = 2.0 * o - end
    c = ((p[0] + q[0]) / 2 + nx * c_lat, (p[1] + q[1]) / 2 + ny * c_lat)
    x = (1 - t) ** 2 * s[0] + 2 * t * (1 - t) * c[0] + t * t * e[0]
    y = (1 - t) ** 2 * s[1] + 2 * t * (1 - t) * c[1] + t * t * e[1]
    sg = 1.0 if o >= 0 else -1.0
    return (x, y), (nx * sg, ny * sg)


def adim(p, q, o, label, t=0.5, gap=3.5, fs=FS, upright=False, width_em=None):
    """치수 점선(양끝이 p·q 에 닿음) + 곡선 **바깥**에 붙인 라벨. o 부호 = 볼록한 쪽."""
    (x, y), (nx, ny) = curve_pt(p, q, o, t)
    hw = (width_em if width_em is not None else label_width_em(label)) * fs / 2
    hh = 0.36 * fs
    d = gap + abs(hw * nx) + abs(hh * ny)
    lab = rtext(x + nx * d, y + ny * d, label, fs) if upright else ltext(x + nx * d, y + ny * d, label, fs)
    return meas(p[0], p[1], q[0], q[1], o) + lab


def poly(pts, fill):
    return curve_path(pts, w=0.01, close=True, fill=fill)


def raw_svg(key, w, h, *parts):
    S[key] = sanitize_svg(f'<svg viewBox="0 0 {w:.0f} {h:.0f}" xmlns="http://www.w3.org/2000/svg">\n'
                          + "\n".join(parts) + "\n</svg>")


def oblique(origin, s, depth_ratio, depth_deg, zs=1.0):
    """사투영 — x 오른쪽, y 깊이(뒤), z 위. zs 는 높이만 키우는 배율(원본 그림의 비례를 따를 때)."""
    a = math.radians(depth_deg)

    def f(p):
        x, y, z = p
        return (origin[0] + s * (x + depth_ratio * y * math.cos(a)),
                origin[1] - s * (zs * z + depth_ratio * y * math.sin(a)))
    return f


def fit(pts, pad=(24, 24, 24, 24)):
    """점들의 범위 + 여백(왼·위·오른·아래)으로 이동량과 viewBox 크기를 정한다."""
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    dx, dy = pad[0] - min(xs), pad[1] - min(ys)
    return (dx, dy), (max(xs) - min(xs) + pad[0] + pad[2], max(ys) - min(ys) + pad[1] + pad[3])


def box(xw, yd, zh):
    """직육면체 ABCD-EFGH(윗면 ABCD: A 앞 왼쪽, B 앞 오른쪽, C 뒤 오른쪽, D 뒤 왼쪽)."""
    return {"A": (0, 0, zh), "B": (xw, 0, zh), "C": (xw, yd, zh), "D": (0, yd, zh),
            "E": (0, 0, 0), "F": (xw, 0, 0), "G": (xw, yd, 0), "H": (0, yd, 0)}


def box_parts(p):
    """음영 두 면 + 보이는 모서리 실선 + 숨은 모서리 점선."""
    A, B, C, D, E, F, G, H = (p[k] for k in "ABCDEFGH")
    out = [poly([A, B, F, E], LIGHT), poly([B, C, G, F], DARK)]
    out += [line(D, H, **HID), line(H, E, **HID), line(H, G, **HID)]
    out += [line(a, b, w=1.9) for a, b in ((A, B), (B, C), (C, D), (D, A), (A, E), (B, F), (C, G),
                                           (E, F), (F, G))]
    return out


# ── q1: 모눈 위 벡터 여섯 개 ─────────────────────────────────────────────────
# 칸 좌표(왼쪽 위 (0,0), 오른쪽·아래로 증가) — 원본 판독. 수학 성분은 (dx, −dy).
VEC1 = {"a": ((1, 7), (5, 1)), "b": ((6, 4), (4, 9)), "c": ((11, 3), (7, 9)),
        "d": ((8, 1), (14, 3)), "e": ((12, 8), (15, 9)), "f": ((17, 1), (15, 7))}
_comp = {k: (q[0] - p[0], p[1] - q[1]) for k, (p, q) in VEC1.items()}
assert _comp["d"] == (2 * _comp["e"][0], 2 * _comp["e"][1])          # d = 2e → 같은 방향(정답 ④)
assert _comp["c"] == (-_comp["a"][0], -_comp["a"][1])                # c = −a
_CELL, _M1 = 22.0, 6.0
_NX, _NY = 18, 10


def g1(i, j):
    return (_M1 + _CELL * i, _M1 + _CELL * j)


_p1 = []
for i in range(_NX + 1):
    _p1.append(f'<line x1="{g1(i, 0)[0]:.1f}" y1="{g1(i, 0)[1]:.1f}" x2="{g1(i, _NY)[0]:.1f}" '
               f'y2="{g1(i, _NY)[1]:.1f}" stroke="#8a8a8a" stroke-width="0.6" stroke-dasharray="2 1.5"/>')
for j in range(_NY + 1):
    _p1.append(f'<line x1="{g1(0, j)[0]:.1f}" y1="{g1(0, j)[1]:.1f}" x2="{g1(_NX, j)[0]:.1f}" '
               f'y2="{g1(_NX, j)[1]:.1f}" stroke="#8a8a8a" stroke-width="0.6" stroke-dasharray="2 1.5"/>')
_len1 = []
for k, (p, q) in VEC1.items():
    P0, P1 = g1(*p), g1(*q)
    _p1.append(leader(P0, P1, arrow=True, w=1.9, head=9.0, gap=0.0))
    _len1.append((math.hypot(*_comp[k]), P0, P1))
verify_figure("q1", lengths=_len1)
# 벡터 이름(원본 위치) — 흰 바탕 위 이탤릭 글자 + 위 화살표
_LAB1 = {"a": (2.45, 3.6), "b": (4.35, 6.55), "c": (8.5, 5.6), "d": (11.45, 1.5), "e": (13.6, 7.85),
         "f": (15.4, 3.5)}
for k, (i, j) in _LAB1.items():
    x, y = g1(i, j)
    _p1.append(f'<rect x="{x - 7:.1f}" y="{y - 17:.1f}" width="14" height="26" fill="#ffffff"/>')
    _p1.append(ltext(x, y, k))
    _p1.append(leader((x - 5.5, y - 12.5), (x + 6.0, y - 12.5), arrow=True, w=0.8, head=4.0, gap=0.0))
raw_svg("q1", 2 * _M1 + _CELL * _NX, 2 * _M1 + _CELL * _NY, *_p1)

# ── q9: 직육면체 ABCD-EFGH(크기 조건 없음 — 원본 비례) ──────────────────────
_b9 = box(3, 3, 2)
_o9, _wh9 = fit([oblique((0, 0), 42, 0.5, 40)(v) for v in _b9.values()], (26, 22, 24, 24))
_pr9 = oblique(_o9, 42, 0.5, 40)
verify_solid("q9", lengths=[(3, _b9["A"], _b9["B"]), (3, _b9["D"], _b9["C"]), (2, _b9["A"], _b9["E"]),
                            (3, _b9["A"], _b9["D"])],
             perpendicular=[((_b9["A"], _b9["B"]), (_b9["A"], _b9["D"])),
                            ((_b9["A"], _b9["E"]), (_b9["A"], _b9["B"]))])
_q9 = {k: _pr9(v) for k, v in _b9.items()}
_p9 = box_parts(_q9)
_p9 += [pt_label(_q9["A"], "A", -12, -2), pt_label(_q9["B"], "B", 11, 11), pt_label(_q9["C"], "C", 10, -10),
        pt_label(_q9["D"], "D", -2, -13), pt_label(_q9["E"], "E", -9, 12), pt_label(_q9["F"], "F", 4, 13),
        pt_label(_q9["G"], "G", 13, 2), pt_label(_q9["H"], "H", 9, 12)]
raw_svg("q9", *_wh9, *_p9)

# ── q10: 도로·진입로·건물 — 삼수선의 정리 ─────────────────────────────────────
# 지면: x = 도로 방향, y = 진입로 방향(도로에 수직), z = 위. AB=30, BD=40(D = 건물의 발), ∠CAB=60°.
_h10 = 10 * math.sqrt(11)                       # 건물 높이(정답) — CB = 30√3, CD² = CB² − BD²
A3, B3, D3, C3 = (0, 0, 0), (30, 0, 0), (30, 40, 0), (30, 40, _h10)
_ac = [c - a for a, c in zip(A3, C3)]
_ab = [b - a for a, b in zip(A3, B3)]
_cos = sum(x * y for x, y in zip(_ac, _ab)) / (math.hypot(*_ac) * math.hypot(*_ab))
assert math.isclose(math.degrees(math.acos(_cos)), 60.0)
verify_solid("q10", lengths=[(30, A3, B3), (40, B3, D3), (50, A3, D3), (60, A3, C3)],
             perpendicular=[((A3, B3), (B3, D3)), ((C3, D3), (A3, D3)), ((C3, D3), (B3, D3)),
                            ((C3, B3), (A3, B3))])
# 원본 그림의 축 방향(사투영): 도로 x → 오른쪽 아래, 진입로 y → 오른쪽 위, 높이 z → 위
_UX, _UY, _UZ = (3.72, 1.52), (2.35, -1.81), (0.0, -2.82)
_O10 = (0.0, 0.0)


def p10(p):
    x, y, z = p
    return (_O10[0] + x * _UX[0] + y * _UY[0] + z * _UZ[0], _O10[1] + x * _UX[1] + y * _UY[1] + z * _UZ[1])


_W, _Dp = 8.0, 6.0
_key10 = [p10(q) for q in (A3, B3, D3, C3, (30 + _W, 40, _h10), (30 + _W, 40 + _Dp, _h10),
                           (30, 40 + _Dp, _h10), (38 + _W, 0, 0))]
_O10, _wh10 = fit(_key10 + [(p10(A3)[0] - 34, p10(A3)[1] - 30)], (8, 20, 10, 22))
A, B, D, C = p10(A3), p10(B3), p10(D3), p10(C3)
_p10 = []
# 도로(회색 두 줄 띠) — 직선 AB 를 따라
_ru = unit(A, B)
_rn = (-_ru[1], _ru[0])                         # 아래쪽 법선
for o0, o1 in ((1.5, 5.0), (9.0, 12.5)):
    s0, s1 = -40.0, dist(A, B) + 4.02 * (8 + _W)
    q = [(A[0] + _ru[0] * s + _rn[0] * o, A[1] + _ru[1] * s + _rn[1] * o)
         for s, o in ((s0, o0), (s1, o0), (s1, o1), (s0, o1))]
    _p10.append(poly(q, "#c9c9c9"))
# 건물: 발 D 에서 도로 방향으로 폭 8, 진입로 방향으로 깊이 6, 높이 h
_f0, _f1 = D, p10((30 + _W, 40, 0))
_f2, _f3 = p10((30 + _W, 40, _h10)), C
_t1, _t2 = p10((30 + _W, 40 + _Dp, _h10)), p10((30, 40 + _Dp, _h10))
_p10.append(poly([_f3, _f2, _t1, _t2], "#f4f4f4"))
_p10.append(poly([_f0, _f1, _f2, _f3], "#e2e2e2"))
_p10.append(curve_path([_f3, _f2, _t1, _t2], w=1.0, close=True))
_p10.append(curve_path([_f0, _f1, _f2, _f3], w=1.2, close=True))


def _face(s, t):
    """건물 앞면 위의 점 — s: 도로 방향 비율, t: 높이 비율."""
    return p10((30 + _W * s, 40, _h10 * t))


for r in range(10):                              # 창문 열 줄 × 두 칸
    t0 = 0.30 + 0.062 * r
    for s0, s1 in ((0.12, 0.46), (0.54, 0.88)):
        _p10.append(curve_path([_face(s0, t0), _face(s1, t0), _face(s1, t0 + 0.038), _face(s0, t0 + 0.038)],
                               w=0.6, close=True, fill="#ffffff"))
_p10.append(curve_path([_face(0.36, 0.0), _face(0.64, 0.0), _face(0.64, 0.14), _face(0.36, 0.14)],
                       w=0.7, close=True, fill="#ffffff"))         # 출입구
# 집(A 의 왼쪽 위) — 몸채·지붕·문·창
_hx, _hy = A[0] - 3.0, A[1] - 1.0
_p10.append(curve_path([(_hx - 26, _hy), (_hx, _hy), (_hx, _hy - 15), (_hx - 26, _hy - 15)],
                       w=1.0, close=True, fill="#ffffff"))
_p10.append(curve_path([(_hx - 29, _hy - 14), (_hx - 13, _hy - 27), (_hx + 3, _hy - 14)],
                       w=1.0, close=True, fill="#d6d6d6"))
_p10.append(curve_path([(_hx - 9, _hy), (_hx - 9, _hy - 9), (_hx - 4, _hy - 9), (_hx - 4, _hy)], w=0.7))
_p10.append(curve_path([(_hx - 21, _hy - 5), (_hx - 21, _hy - 10), (_hx - 15, _hy - 10), (_hx - 15, _hy - 5)],
                       w=0.7, close=True))
# 선분: AC·AB·BD 굵게, AD 가늘게, BC 옅은 점선
_p10.append(f'<line x1="{B[0]:.1f}" y1="{B[1]:.1f}" x2="{C[0]:.1f}" y2="{C[1]:.1f}" stroke="#7a7a7a" '
            f'stroke-width="0.8" stroke-dasharray="2 2"/>')
_p10 += [line(A, D, w=1.0), line(A, C, w=1.9), line(A, B, w=1.9), line(B, D, w=1.9)]
_p10 += [rangle(B[0], B[1], *unit(B, A), *unit(B, D), s=6),
         rangle(D[0], D[1], *unit(D, C), *unit(D, A), s=6)]
# ∠CAB = 60° 호와 표시
_r10 = 19.0
_aB, _aC = unit(A, B), unit(A, C)
_p10.append(f'<path d="M {A[0] + _aC[0] * _r10:.1f} {A[1] + _aC[1] * _r10:.1f} A {_r10} {_r10} 0 0 1 '
            f'{A[0] + _aB[0] * _r10:.1f} {A[1] + _aB[1] * _r10:.1f}" fill="none" stroke="#000" '
            f'stroke-width="0.72"/>')
_mid = math.atan2(*reversed(unit(A, D))) / 2 + math.atan2(_aB[1], _aB[0]) / 2
_p10.append(ltext(A[0] + 37 * math.cos(_mid), A[1] + 37 * math.sin(_mid), "60°"))
_p10 += [adim(A, B, 9, "30 m", upright=True, width_em=2.0), adim(B, D, 9, "40 m", upright=True, width_em=2.0)]
for _pp, _dx, _dy in ((A, -9, 12), (B, 3, 14)):      # 도로 띠 위 라벨 — 흰 바탕으로 띠를 끊는다
    _p10.append(f'<rect x="{_pp[0] + _dx - 7:.1f}" y="{_pp[1] + _dy - 8:.1f}" width="14" height="16" '
                f'fill="#ffffff"/>')
_p10 += [pt_label(A, "A", -9, 12), pt_label(B, "B", 3, 14), pt_label(C, "C", -4, -12)]
raw_svg("q10", *_wh10, *_p10)

# ── s4: 직육면체, AD=3·DC=4·AE=1, D 에서 EG 에 내린 수선의 발 I ───────────────
# 3D 는 실제 길이. 높이(AE=1)만 원본 그림처럼 키워 그린다(zs) — 아랫면(EFGH)은 z=0 이라
# 비례가 그대로여서 I 의 위치(EI:IG = 9:16)는 정확하다.
_b4 = box(4, 3, 1)
_E4, _G4, _D4, _H4 = _b4["E"], _b4["G"], _b4["D"], _b4["H"]
_t = sum((h - e) * (g - e) for e, g, h in zip(_E4, _G4, _H4)) / sum((g - e) ** 2 for e, g in zip(_E4, _G4))
I4 = tuple(e + _t * (g - e) for e, g in zip(_E4, _G4))
assert math.isclose(_t, 9 / 25)
_di = math.dist(_D4, I4)
assert math.isclose(_di, 13 / 5)                                   # 정답 13/5
verify_solid("s4", lengths=[(3, _b4["A"], _b4["D"]), (4, _b4["D"], _b4["C"]), (1, _b4["A"], _b4["E"]),
                            (5, _E4, _G4)],
             perpendicular=[((_D4, I4), (_E4, _G4)), ((_H4, I4), (_E4, _G4)), ((_D4, _H4), (_E4, _G4))])
_o4, _wh4 = fit([oblique((0, 0), 40, 0.72, 44, zs=2.0)(v) for v in _b4.values()], (34, 34, 26, 24))
_pr4 = oblique(_o4, 40, 0.72, 44, zs=2.0)
_q4 = {k: _pr4(v) for k, v in _b4.items()}
I = _pr4(I4)
_p4 = box_parts(_q4)
_p4 += [line(_q4["E"], _q4["G"], w=1.5), line(_q4["D"], I, w=1.5),
        rangle(I[0], I[1], *unit(I, _q4["D"]), *unit(I, _q4["G"]), s=7)]
_p4 += [adim(_q4["A"], _q4["D"], -12, "3"), adim(_q4["D"], _q4["C"], -12, "4"), adim(_q4["A"], _q4["E"], 12, "1")]
_p4 += [pt_label(_q4["A"], "A", -13, -3), pt_label(_q4["B"], "B", 11, 11), pt_label(_q4["C"], "C", 11, -10),
        pt_label(_q4["D"], "D", -3, -13), pt_label(_q4["E"], "E", -8, 12), pt_label(_q4["F"], "F", 4, 13),
        pt_label(_q4["G"], "G", 13, 3), pt_label(_q4["H"], "H", -10, -9), pt_label(I, "I", 3, 13)]
raw_svg("s4", *_wh4, *_p4)

# ── s5: 정팔면체(모서리 6) ───────────────────────────────────────────────────
_s5 = 3 * math.sqrt(2)                         # 중심에서 꼭짓점까지 = 6/√2
O5 = {"A": (0, 0, _s5), "F": (0, 0, -_s5), "C": (-_s5, 0, 0), "E": (_s5, 0, 0),
      "D": (0, -_s5, 0), "B": (0, _s5, 0)}     # D 앞, B 뒤
_edges5 = [("A", "C"), ("A", "E"), ("A", "D"), ("A", "B"), ("F", "C"), ("F", "E"), ("F", "D"), ("F", "B"),
           ("C", "D"), ("D", "E"), ("E", "B"), ("B", "C")]
verify_solid("s5", lengths=[(6, O5[a], O5[b]) for a, b in _edges5])
_o5, _wh5 = fit([View(0.276, 109.7, 22.0, (0.0, 0.0))(v) for v in O5.values()], (40, 24, 24, 24))
_v5 = View(depth_ratio=0.276, depth_deg=109.7, scale=22.0, origin=_o5)
_q5 = {k: _v5(v) for k, v in O5.items()}
A, B, C, D, E, F = (_q5[k] for k in "ABCDEF")
_p5 = [poly([A, D, E], LIGHT), poly([C, D, F], LIGHT), poly([D, E, F], DARK)]
_p5 += [line(A, B, **HID), line(B, C, **HID), line(B, E, **HID), line(B, F, **HID)]
_p5 += [line(p, q, w=1.9) for p, q in ((A, C), (A, E), (A, D), (C, D), (D, E), (C, F), (E, F), (D, F))]
_p5.append(adim(C, A, -13, "6"))
_p5 += [pt_label(A, "A", 0, -13), pt_label(F, "F", 0, 14), pt_label(C, "C", -13, 0), pt_label(E, "E", 13, 0),
        pt_label(B, "B", -11, -9), pt_label(D, "D", 11, 13)]
raw_svg("s5", *_wh5, *_p5)


LINT_EXEMPT = {
    # 모눈 위에 놓인 벡터 이름 — 흰 바탕을 깔았지만 lint 는 모눈 점선도 '선 잉크'로 센다.
    "q1": ("라벨-선 겹침",),
    # 원본처럼 음영 면 안에 둔 꼭짓점 이름 — lint 는 면 음영도 잉크로 센다.
    "q9": ("라벨-선 겹침: 'B'",), "s4": ("라벨-선 겹침: 'B'",), "s5": ("라벨-선 겹침: 'D'",),
}

if __name__ == "__main__":
    from core.figure_generator import _svg_to_png_bytes
    miss = unverified(S)
    if miss:
        raise SystemExit(f"검산 누락(verify 미호출): {miss}")
    bad = []
    only = [k for k in os.environ.get("FIG_ONLY", "").split(",") if k]
    for k, svg in S.items():
        if only and k not in only:
            continue
        issues = [i for i in lint_svg(svg) if not any(i.startswith(x) for x in LINT_EXEMPT.get(k, ()))]
        if issues:
            bad.append(f"{k}: {'; '.join(issues)}")
        png = _svg_to_png_bytes(svg, width=900)
        if not png:
            raise SystemExit(f"{k} PNG 렌더 실패")
        open(os.path.join(OUT, f"{k}.png"), "wb").write(png)
        print(k, "ok" if not issues else "LINT")
    if bad and "--lenient" not in sys.argv:
        raise SystemExit("lint 실패:\n" + "\n".join(bad))
    elif bad:
        print("\n".join(bad))
