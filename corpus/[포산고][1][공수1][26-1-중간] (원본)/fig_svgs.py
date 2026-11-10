# -*- coding: utf-8 -*-
"""포산고 고1 공통수학1 26-1-중간 그림 3개 — 원본 인쇄면만 다시 그린다(학생 필기·음영 제외).

q8  조립제법 틀(3 | a b c 7 / 빈칸 셋 / 2 1 1 | 10)
s3  서술형 3 직육면체 ABCD-EFGH(밑면 가로 a·세로 b, 높이 c, 대각선 AG=4√2)
s4  서술형 4 의자 8개가 나란한 긴 의자

렌더 하네스(.testkit/_s26_render.py)가 FIG_SVG_OUT 폴더를 주고 실행한다.
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from core.figure_exam import FS, HIDDEN, FigureSet, adim, curve_pt, fit, ltext, oblique, pt_label, rtext  # noqa: E402
from core.figure_solid import verify_solid  # noqa: E402
from core.figure_svg import line, meas, sqrt_label, verify_figure  # noqa: E402

OUT = os.environ.get("FIG_SVG_OUT") or os.path.join(tempfile.gettempdir(), "posan_fig")
figs = FigureSet()

# ── q8 조립제법 틀 ───────────────────────────────────────────────────────────
# 원본: 나누는 수 3, 윗줄 계수 a·b·c·7, 가운데 줄 빈칸 세 개, 아랫줄 2·1·1, 나머지 10 은 ㄴ 자 칸 안.
cx = [88, 152, 216, 280]            # 열 가운데
Y1, YB0, YB1, YL, Y3 = 24, 40, 72, 86, 106
FS8 = 21                            # 표처럼 읽는 그림이라 본문 글자 크기에 맞춘다(지면 60mm 에서 약 10.5pt)
parts8 = [rtext(30, Y1, "3", fs=FS8)]
parts8 += [ltext(c, Y1, s, fs=FS8) for c, s in zip(cx, ("a", "b", "c", "7"))]
for c in cx[1:]:                    # 빈칸(인쇄된 네모) — 안에 적힌 6·3·3 은 학생 필기
    x0, x1 = c - 24, c + 24
    parts8 += [line((x0, YB0), (x1, YB0), w=1.2), line((x1, YB0), (x1, YB1), w=1.2),
               line((x1, YB1), (x0, YB1), w=1.2), line((x0, YB1), (x0, YB0), w=1.2)]
parts8 += [line((50, 8), (50, YL), w=1.5), line((50, YL), (314, YL), w=1.5)]
parts8 += [ltext(c, Y3, s, fs=FS8) for c, s in zip(cx, ("2", "1", "1", "10"))]
parts8 += [line((250, YL), (250, 122), w=1.5), line((250, 122), (312, 122), w=1.5)]   # 나머지 칸
verify_figure("q8")                 # 길이 라벨 없음(계수 표) — 검산할 비율이 없다
figs.raw("q8", 330, 132, *parts8)

# ── s3 직육면체 ──────────────────────────────────────────────────────────────
# 3D: x = 밑면 가로(FG=a), y = 세로(GH=b, 뒤로), z = 높이(DH=c). 윗면 ABCD(A 뒤 왼쪽), 앞면 BFGC.
# ⚠️ 문제 조건(a+b+c=12, a²+b²+c²=32)을 만족하는 직육면체는 없다(a²+b²+c² ≥ 48) — 그림은 원본
#    비례(가로가 가장 길고 높이·세로가 비슷)만 따른다. 라벨은 문자 a·b·c 와 대각선 4√2.
A3, B3, C3 = 5.0, 3.6, 2.7
V = {"F": (0, 0, 0), "G": (A3, 0, 0), "H": (A3, B3, 0), "E": (0, B3, 0),
     "B": (0, 0, C3), "C": (A3, 0, C3), "D": (A3, B3, C3), "A": (0, B3, C3)}
verify_solid("s3", lengths=[(A3, V["F"], V["G"]), (B3, V["G"], V["H"]), (C3, V["H"], V["D"])],
             perpendicular=[((V["F"], V["G"]), (V["G"], V["H"])), ((V["G"], V["H"]), (V["H"], V["D"])),
                            ((V["F"], V["G"]), (V["H"], V["D"]))])
proj0 = oblique((0, 0), 40, 0.75, 37)
org, wh = fit([proj0(v) for v in V.values()], (34, 30, 40, 40))
pr = oblique(org, 40, 0.75, 37)
p = {k: pr(v) for k, v in V.items()}
parts3 = [line(p["A"], p["E"], **HIDDEN), line(p["E"], p["F"], **HIDDEN), line(p["E"], p["H"], **HIDDEN)]
parts3 += [line(p[u], p[v], w=1.9) for u, v in ("AB", "AD", "BC", "CD", "BF", "CG", "DH", "FG", "GH")]
parts3 += [line(p["A"], p["G"], w=1.9)]                           # 대각선 AG(원본 실선)
parts3 += [adim(p["F"], p["G"], 12, "a"), adim(p["G"], p["H"], 12, "b"), adim(p["H"], p["D"], 12, "c")]
# 대각선 치수: 점선 곡선은 AG 의 왼쪽 아래(E 쪽)로 볼록, 라벨 4√2(근호는 선으로 — 유니코드 √ 금지)
OFF_AG = 18
parts3 += [meas(p["A"][0], p["A"][1], p["G"][0], p["G"][1], OFF_AG)]
(mx, my), (nx, ny) = curve_pt(p["A"], p["G"], OFF_AG, 0.5)
lx, ly = mx + nx * 20 + 4, my + ny * 20 + 14                       # 라벨 가운데 — 점선 EH 아래
w4 = 0.55 * FS
parts3 += [rtext(lx - 0.62 * FS, ly, "4", anc="middle"),
           sqrt_label(lx - 0.62 * FS + w4 / 2 + 1, ly + 0.35 * FS, "2", fs=FS)]
parts3 += [pt_label(p["A"], "A", -4, -13), pt_label(p["D"], "D", 12, -8), pt_label(p["B"], "B", -14, 2),
           pt_label(p["C"], "C", 12, 9), pt_label(p["E"], "E", -11, -9), pt_label(p["F"], "F", -13, 6),
           pt_label(p["G"], "G", 2, 15), pt_label(p["H"], "H", 13, 7)]
figs.raw("s3", *wh, *parts3)

# ── s4 의자 8개 ──────────────────────────────────────────────────────────────
N, PITCH, X0 = 8, 47, 14
parts4 = []
for i in range(N):
    c = X0 + 22 + i * PITCH
    parts4 += [f'<rect x="{c - 21}" y="8" width="42" height="16" rx="6" fill="#4a4a4a" stroke="#222222" stroke-width="1"/>',
               f'<rect x="{c - 9}" y="24" width="4" height="18" fill="#6e6e6e"/>',
               f'<rect x="{c + 5}" y="24" width="4" height="18" fill="#6e6e6e"/>',
               f'<rect x="{c - 22}" y="42" width="44" height="11" rx="4" fill="#9a9a9a" stroke="#333333" stroke-width="1"/>']
bx0, bx1 = X0 - 4, X0 + 22 + (N - 1) * PITCH + 30
parts4 += [f'<rect x="{bx0}" y="55" width="{bx1 - bx0}" height="7" fill="#333333"/>',
           f'<rect x="{bx0}" y="62" width="6" height="16" fill="#333333"/>',
           f'<rect x="{bx1 - 6}" y="62" width="6" height="16" fill="#333333"/>']
figs.raw("s4", bx1 + 10, 86, *parts4)

LINT_EXEMPT = {
    # 숨은 꼭짓점 E 는 원본처럼 앞면 안쪽에 이름을 둔다 — lint 는 점선 모서리를 잉크로 센다.
    "s3": ("라벨-선 겹침: 'E'",),
}

if __name__ == "__main__":
    rep = figs.build(OUT, lint_exempt=LINT_EXEMPT)
    for k, v in rep.items():
        print(k, "ok" if not v["issues"] else v["issues"])
    print(figs.widths({"8": "q8", "19": "s3", "20": "s4"}))
