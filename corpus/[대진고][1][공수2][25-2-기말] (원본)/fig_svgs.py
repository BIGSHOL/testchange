# -*- coding: utf-8 -*-
"""대진고1 공수2 25-2-기말 — 그림 4개 core.figure_svg 엔진 작도(정의값 기하).

원본은 스캔이라 그림을 **캡처하지 않고 조건에서 다시 유도해 작도**한다. 그래서
좌표는 전부 문제의 식에서 계산하고(눈대중 금지), 라벨에 적은 값이 실제 작도와
같은지 `verify_figure` 와 `_check` 로 재측정해 대조한다(핸드오프 §4 원칙).

  q4  : 유리함수 f(x)=(ax+b)/(x+c) — 점근선 x=1/2·y=-2, (0,1) 통과 → f=-2-3/2/(x-1/2)
  q12 : 이차함수 y=f(x) — 근 1·5, 꼭짓점 (3,-2)  → f=(x-3)^2/2-2
  q14 : 무리함수 y=f(x)=√(ax+b)+c (a<0,b>0,c>0) — 대표값 a=-1,b=4,c=1
  q16 : f(x)=x^2-ax 와 g(x)=(2/a)x, 꼭짓점 B·중점 C·수선의 발 H — 대표값 a=1.35
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
from core.figure_svg import (FONT, curve_path, dot, frac_label, line,  # noqa: E402
                             lint_svg, point_labels, rangle_at, txt, type_scale,
                             unverified, verify_figure)

OUT = os.environ.get(
    "FIG_SVG_OUT",
    str(Path(tempfile.gettempdir()) / "exam_figure_svg" / "daejin_gs2_final"),
)
os.makedirs(OUT, exist_ok=True)
S = {}
CHECKS = []


def _check(name, cond, msg):
    """라벨(=문제 조건)과 작도가 어긋나면 즉시 실패 — lint 로는 못 잡는 종류."""
    CHECKS.append(name)
    if not cond:
        raise SystemExit(f"[{name}] 작도 검산 실패: {msg}")


def _arrow(tip, ux, uy, s=5.0):
    """축 화살촉(삼각형)."""
    px, py = -uy, ux
    a = (tip[0] - ux * s * 1.8 + px * s * 0.75, tip[1] - uy * s * 1.8 + py * s * 0.75)
    b = (tip[0] - ux * s * 1.8 - px * s * 0.75, tip[1] - uy * s * 1.8 - py * s * 0.75)
    return (f'<path d="M {tip[0]:.1f} {tip[1]:.1f} L {a[0]:.1f} {a[1]:.1f} '
            f'L {b[0]:.1f} {b[1]:.1f} Z" fill="#000"/>')


def axes(X0, X1, Y0, Y1, ox, oy, w=1.4):
    """x축(왼→오른쪽 화살표)·y축(아래→위 화살표). 좌표는 화면 px."""
    return "\n".join([
        f'<line x1="{X0:.1f}" y1="{oy:.1f}" x2="{X1:.1f}" y2="{oy:.1f}" '
        f'stroke="#000" stroke-width="{w}"/>',
        _arrow((X1, oy), 1, 0),
        f'<line x1="{ox:.1f}" y1="{Y0:.1f}" x2="{ox:.1f}" y2="{Y1:.1f}" '
        f'stroke="#000" stroke-width="{w}"/>',
        _arrow((ox, Y1), 0, -1),
    ])


def sample(f, x0, x1, X, Y, n=240, ylim=None):
    """수식 f 를 화면 좌표 점열로 — ylim 밖(발산)은 잘라 낸다."""
    pts = []
    for i in range(n + 1):
        x = x0 + (x1 - x0) * i / n
        try:
            y = f(x)
        except (ZeroDivisionError, ValueError):
            continue
        if ylim and not (ylim[0] <= y <= ylim[1]):
            continue
        pts.append((X(x), Y(y)))
    return pts


# ── q4: 유리함수 — 점근선 x=1/2·y=-2, (0,1) 통과 ────────────────────
# 조건에서 유도: 세로점근선 x=-c=1/2 → c=-1/2, 가로점근선 y=a=-2,
#               f(0)=b/c=1 → b=c=-1/2.  f(x) = -2 + (b-ac)/(x+c) = -2 - 1.5/(x-0.5)
A4, B4, C4 = -2.0, -0.5, -0.5
f4 = lambda x: (A4 * x + B4) / (x + C4)
VX4, VY4 = 320, 240
ox4, oy4, ux4, uy4 = 104.0, 120.0, 44.0, 26.0
X4 = lambda x: ox4 + ux4 * x
Y4 = lambda y: oy4 - uy4 * y
FS4 = type_scale(VX4, VY4)
_check("q4-점근선", abs(-C4 - 0.5) < 1e-9 and abs(A4 + 2) < 1e-9,
       "세로 x=1/2·가로 y=-2 이어야 한다")
_check("q4-절편", abs(f4(0) - 1.0) < 1e-9, "f(0)=1 이어야 한다(그림의 눈금 1)")
_check("q4-ㄱ", abs(A4 + 8 * B4 * C4) < 1e-9, "보기 ㄱ(a+8bc=0)이 성립해야 한다")
_check("q4-ㄴ", abs(f4(1) + 5) < 1e-9, "보기 ㄴ(f^-1(-5)=1)이 성립해야 한다")
asym_x4, asym_y4 = X4(0.5), Y4(-2.0)
left4 = sample(f4, -2.2, 0.45, X4, Y4, ylim=(-4.4, 4.3))
right4 = sample(f4, 0.55, 4.5, X4, Y4, ylim=(-4.4, 4.3))
S["q4"] = f'''<svg viewBox="0 0 {VX4} {VY4}" xmlns="http://www.w3.org/2000/svg">
{axes(X4(-2.3), X4(4.6), Y4(-4.5), Y4(4.35), ox4, oy4)}
<line x1="{asym_x4:.1f}" y1="{Y4(4.35):.1f}" x2="{asym_x4:.1f}" y2="{Y4(-4.5):.1f}" stroke="#000" stroke-width="1.2" stroke-dasharray="6 4"/>
<line x1="{X4(-2.3):.1f}" y1="{asym_y4:.1f}" x2="{X4(4.6):.1f}" y2="{asym_y4:.1f}" stroke="#000" stroke-width="1.2" stroke-dasharray="6 4"/>
{curve_path(left4)}
{curve_path(right4)}
{dot(X4(0), Y4(1))}
{txt(ox4 - 10, Y4(1) + 5, "1", FS4, anc="end")}
{txt(ox4 - 10, Y4(-2) + 22, "-2", FS4, anc="end")}
{frac_label(asym_x4 + 17, Y4(0) - 24, 1, 2, FS4 - 3)}
{txt(ox4 + 5, Y4(0) + 19, "O", FS4, anc="start")}
{txt(X4(4.6) + 6, Y4(0) - 9, "x", FS4, it=True)}
{txt(ox4 - 11, Y4(4.35) + 4, "y", FS4, it=True)}
{txt(X4(3.4), Y4(-3.35), "y = f(x)", FS4, it=True)}
</svg>'''

# ── q12: 이차함수 — 근 1·5, 꼭짓점 (3,-2) ──────────────────────────
# f(x)=k(x-1)(x-5), 꼭짓점 f(3)=-2 → k(2)(-2)=-2 → k=1/2
K12 = 0.5
f12 = lambda x: K12 * (x - 1) * (x - 5)
# ⚠️ 축 단위는 x·y 같게(등방). 가로 단위만 크게 잡으면 포물선이 눌려 원본보다
#    납작·넓게 보인다(2026-08-18 사용자 지적 — 이전 30:22 은 x 가 1.36배였다).
VX12, VY12 = 252, 227
ox12, oy12, ux12, uy12 = 52.0, 141.0, 27.0, 27.0
X12 = lambda x: ox12 + ux12 * x
Y12 = lambda y: oy12 - uy12 * y
FS12 = type_scale(VX12, VY12)
_check("q12-근", abs(f12(1)) < 1e-9 and abs(f12(5)) < 1e-9, "x=1,5 에서 x축과 만나야 한다")
_check("q12-꼭짓점", abs(f12(3) + 2) < 1e-9, "꼭짓점 (3,-2) 이어야 한다")
_check("q12-합", abs(sum(sorted({round(r, 6) for r in (
    3 + math.sqrt(2 * (2 + 3 + 2 * math.sqrt(2))), 3 - math.sqrt(2 * (2 + 3 + 2 * math.sqrt(2))),
    3 + math.sqrt(2 * (2 + 3 - 2 * math.sqrt(2))), 3 - math.sqrt(2 * (2 + 3 - 2 * math.sqrt(2))))})) - 12) < 1e-6,
       "(f∘f)(x)=2 의 네 실근 합이 12(=정답 ④)여야 한다")
par12 = sample(f12, -0.75, 6.75, X12, Y12, ylim=(-2.6, 4.0))
S["q12"] = f'''<svg viewBox="0 0 {VX12} {VY12}" xmlns="http://www.w3.org/2000/svg">
{axes(X12(-0.95), X12(6.6), Y12(-2.75), Y12(4.1), ox12, oy12)}
{curve_path(par12)}
<line x1="{X12(3):.1f}" y1="{Y12(0):.1f}" x2="{X12(3):.1f}" y2="{Y12(-2):.1f}" stroke="#000" stroke-width="1.2" stroke-dasharray="5 4"/>
<line x1="{X12(0):.1f}" y1="{Y12(-2):.1f}" x2="{X12(3):.1f}" y2="{Y12(-2):.1f}" stroke="#000" stroke-width="1.2" stroke-dasharray="5 4"/>
{txt(X12(1) - 11, Y12(0) + 21, "1", FS12)}
{txt(X12(5) + 12, Y12(0) + 21, "5", FS12)}
{txt(X12(3), Y12(0) - 9, "3", FS12)}
{txt(ox12 - 10, Y12(-2) + 6, "-2", FS12, anc="end")}
{txt(ox12 - 8, Y12(0) + 20, "O", FS12, anc="end")}
{txt(X12(6.6) + 5, Y12(0) - 9, "x", FS12, it=True)}
{txt(ox12 + 9, Y12(4.1) + 6, "y", FS12, it=True)}
{txt(X12(5.9), Y12(3.5), "y = f(x)", FS12, it=True, anc="end")}
</svg>'''

# ── q14: 무리함수 √(ax+b)+c (a<0, b>0, c>0) ───────────────────────
A14, B14, C14 = -1.0, 4.0, 1.0            # 대표값 — 부호 조건만 반영
f14 = lambda x: math.sqrt(A14 * x + B14) + C14
VX14, VY14 = 300, 215
ox14, oy14, ux14, uy14 = 172.0, 172.0, 22.0, 30.0
X14 = lambda x: ox14 + ux14 * x
Y14 = lambda y: oy14 - uy14 * y
FS14 = type_scale(VX14, VY14)
end14 = -B14 / A14                         # 정의역 오른쪽 끝 x=-b/a
_check("q14-감소", f14(-6) > f14(0) > f14(end14), "a<0 이므로 감소해야 한다")
_check("q14-끝점", end14 > 0 and f14(end14) == C14 and C14 > 0,
       "끝점 (-b/a, c) 가 제1사분면(x>0, y>0)이어야 한다")
_check("q14-부호", A14 < 0 < B14 and C14 > 0, "그림이 뜻하는 부호는 a<0, b>0, c>0")
cur14 = sample(f14, -6.1, end14, X14, Y14)
S["q14"] = f'''<svg viewBox="0 0 {VX14} {VY14}" xmlns="http://www.w3.org/2000/svg">
{axes(X14(-6.5), X14(4.9), Y14(-0.75), Y14(4.6), ox14, oy14)}
{curve_path(cur14)}
<line x1="{X14(0):.1f}" y1="{Y14(C14):.1f}" x2="{X14(end14):.1f}" y2="{Y14(C14):.1f}" stroke="#000" stroke-width="1.2" stroke-dasharray="5 4"/>
<line x1="{X14(end14):.1f}" y1="{Y14(C14):.1f}" x2="{X14(end14):.1f}" y2="{Y14(0):.1f}" stroke="#000" stroke-width="1.2" stroke-dasharray="5 4"/>
{txt(X14(-3.7), Y14(2.05), "y = f(x)", FS14, it=True)}
{txt(ox14 - 8, Y14(0) + 20, "O", FS14, anc="end")}
{txt(X14(4.9) + 5, Y14(0) - 9, "x", FS14, it=True)}
{txt(ox14 - 11, Y14(4.6) + 4, "y", FS14, it=True)}
</svg>'''

# ── q16: f(x)=x^2-ax 와 g(x)=(2/a)x, 꼭짓점 B·중점 C·수선의 발 H ───
A16 = 1.35                                  # 대표값(양수 a)
f16 = lambda x: x * x - A16 * x
g16 = lambda x: (2.0 / A16) * x
ax16 = A16 + 2.0 / A16                      # 교점 A 의 x좌표: x^2-ax=(2/a)x
PA = (ax16, g16(ax16))
PB = (A16 / 2.0, f16(A16 / 2.0))            # 꼭짓점
PC = ((PA[0] + PB[0]) / 2.0, (PA[1] + PB[1]) / 2.0)
PH = (0.0, PC[1])                           # C 에서 y축에 내린 수선의 발
# ⚠️ 등방 단위(ux==uy) — 이전 58:30 은 가로가 1.9배라 포물선이 눌리고 직선
#    g 의 기울기도 실제(56°)보다 훨씬 완만하게 보였다(2026-08-18 사용자 지적).
VX16, VY16 = 268, 292
ox16, oy16, ux16, uy16 = 100.0, 229.0, 42.0, 42.0
X16 = lambda x: ox16 + ux16 * x
Y16 = lambda y: oy16 - uy16 * y
FS16 = type_scale(VX16, VY16)
P = lambda p: (X16(p[0]), Y16(p[1]))
_check("q16-교점", abs(f16(PA[0]) - g16(PA[0])) < 1e-9 and abs(f16(0) - g16(0)) < 1e-12,
       "두 그래프는 O 와 A 에서만 만나야 한다")
_check("q16-꼭짓점", abs(PB[0] - A16 / 2) < 1e-12 and PB[1] < 0, "B 는 포물선의 꼭짓점")
_check("q16-중점", abs(PC[0] - (PA[0] + PB[0]) / 2) < 1e-12, "C 는 선분 AB 의 중점")
_check("q16-수선", abs(PH[0]) < 1e-12 and abs(PH[1] - PC[1]) < 1e-12,
       "H 는 C 에서 y축에 내린 수선의 발")
_check("q16-CH", abs((3 * A16 / 4 + 1 / A16) - PC[0]) < 1e-9,
       "CH = 3a/4 + 1/a (최솟값 √3 = 정답 ⑤)")
# 그림이 주장하는 명제: ∠(CH, y축)=90°(직각 표시) · C 는 선분 AB 위 · A 는 직선 g 위
verify_figure("q16",
              angles=[(90, P(PH), P(PC), (X16(0), Y16(3.0)))],
              on_line=[(P(PC), P(PA), P(PB)), (P(PA), P((0.0, 0.0)), P((1.0, g16(1.0))))])
par16 = sample(f16, -1.60, 3.00, X16, Y16, ylim=(-1.05, 4.05))
lin16 = sample(g16, -0.85, 2.95, X16, Y16, ylim=(-1.15, 4.35))
S["q16"] = f'''<svg viewBox="0 0 {VX16} {VY16}" xmlns="http://www.w3.org/2000/svg">
{axes(X16(-1.70), X16(3.30), Y16(-1.30), Y16(4.55), ox16, oy16)}
{curve_path(par16)}
{curve_path(lin16, w=1.6)}
{line(P(PA), P(PB), 1.6)}
<line x1="{P(PH)[0]:.1f}" y1="{P(PH)[1]:.1f}" x2="{P(PC)[0]:.1f}" y2="{P(PC)[1]:.1f}" stroke="#000" stroke-width="1.2" stroke-dasharray="4 3"/>
{rangle_at(*P(PH), P(PC), (P(PH)[0], P(PH)[1] - 30), 9)}
{dot(*P(PA), 2.6)}{dot(*P(PB), 2.6)}{dot(*P(PC), 2.6)}
{txt(P(PC)[0] + 9, P(PC)[1] + 9, "C", FS16 - 4)}
{point_labels([(*P(PA), "A"), (*P(PB), "B"), (*P(PH), "H")],
              avoid=[(P(PA), P(PB)), (P(PH), P(PC)),
                     ((X16(-1.70), Y16(0)), (X16(3.30), Y16(0))),
                     ((ox16, Y16(-1.30)), (ox16, Y16(4.55)))],
              curves=[par16, lin16], fs=FS16 - 4, gap=9.5,
              occupied=[(P(PC)[0] + 2, P(PC)[1] - 3, P(PC)[0] + 17, P(PC)[1] + 12)])}
{txt(4, 26, "f(x) = x² - ax", FS16 - 4, it=True, anc="start")}
{txt(150, 26, "g(x) =", FS16 - 4, it=True, anc="start")}
{frac_label(150 + (FS16 - 4) * 3.3, 22, 2, "a", FS16 - 6)}
{txt(150 + (FS16 - 4) * 4.1, 26, "x", FS16 - 4, it=True, anc="start")}
{txt(ox16 - 16, Y16(0) + 20, "O", FS16 - 4, anc="end")}
{txt(X16(3.30) + 6, Y16(0) - 9, "x", FS16, it=True)}
{txt(ox16 + 9, Y16(4.55) + 6, "y", FS16, it=True)}
</svg>'''


if __name__ == "__main__":
    from core.figure_generator import _svg_to_png_bytes

    miss = unverified(S)
    if miss:
        raise SystemExit(f"검산 누락(verify_figure 미호출): {miss}")
    print("작도 검산", len(CHECKS), "건 통과:", ", ".join(CHECKS))
    bad = 0
    for k, svg in S.items():
        issues = lint_svg(svg)
        if issues:
            bad += 1
            print(f"{k} LINT 실패:")
            for it in issues:
                print("   -", it)
            continue
        png = _svg_to_png_bytes(svg, width=int(
            float(svg.split('viewBox="0 0 ')[1].split()[0]) * 4))
        if not png:
            print(k, "PNG 실패")
            bad += 1
            continue
        with open(os.path.join(OUT, f"{k}.png"), "wb") as f:
            f.write(png)
        print(k, "ok →", os.path.join(OUT, f"{k}.png"))
    raise SystemExit(1 if bad else 0)
