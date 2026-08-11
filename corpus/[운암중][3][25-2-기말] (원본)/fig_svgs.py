# -*- coding: utf-8 -*-
"""운암중3 25-2-기말 — 그림 14개를 교과서급 SVG 로 작도 → resvg PNG.

math-gen SVG 규칙(core.figure_generator.SVG_RULES) 준수:
- 기하 이상화(각도·비율은 수학적 정의값으로 계산), 데이터(값·라벨)는 원본 그대로
- 본선 2px 검정 / 보조선·축 1px, 곡선은 path, 라벨은 <text>, 배경 투명
"""
import math
import os
import sys

sys.path.insert(0, r"F:\시험지변환기")
sys.stdout.reconfigure(encoding="utf-8")

OUT = r"F:\tmp\figcrop\_ua2\_fig"
os.makedirs(OUT, exist_ok=True)

FONT = 'font-family="Times New Roman, Batang, serif"'
IT = f'{FONT} font-style="italic"'


def P(x, y):
    return f"{x:.1f},{y:.1f}"


def arc(cx, cy, r, a0, a1, sweep=None):
    """중심 (cx,cy) 반지름 r, 수학각 a0→a1(도)의 원호 path (SVG y-down 보정).

    sweep 을 안 주면 방향에서 자동 결정 — 수학각 증가(a1>a0)=화면 반시계=sweep 0,
    감소=sweep 1. 고정 0 이던 시절 감소 방향 호(q2·q6 45°=180→135)가 각 바깥으로
    뒤집혀 그려졌다(사용자 지적 2026-08-11).
    """
    if sweep is None:
        sweep = 0 if a1 > a0 else 1
    x0, y0 = cx + r * math.cos(math.radians(a0)), cy - r * math.sin(math.radians(a0))
    x1, y1 = cx + r * math.cos(math.radians(a1)), cy - r * math.sin(math.radians(a1))
    large = 1 if abs(a1 - a0) > 180 else 0
    return f'M {x0:.1f} {y0:.1f} A {r} {r} 0 {large} {sweep} {x1:.1f} {y1:.1f}'


def rangle(x, y, ux, uy, vx, vy, s=11):
    """점 (x,y)에서 단위방향 u,v 로 이루는 직각 표시(작은 사각형)."""
    return (f'<path d="M {x+ux*s:.1f} {y+uy*s:.1f} L {x+(ux+vx)*s:.1f} {y+(uy+vy)*s:.1f} '
            f'L {x+vx*s:.1f} {y+vy*s:.1f}" fill="none" stroke="#000" stroke-width="1"/>')




def sqrt_label(x, y, num="2", fs=15):
    """근호를 선으로 그린 √num 라벨 — 유니코드 √ 는 vinculum 이 없어 희미하다."""
    w = 0.62 * fs * len(num)
    bar_y = y - 0.82 * fs
    return (f'<path d="M {x:.1f} {y-0.38*fs:.1f} L {x+0.16*fs:.1f} {y-0.46*fs:.1f} '
            f'L {x+0.34*fs:.1f} {y-0.06*fs:.1f} L {x+0.58*fs:.1f} {bar_y:.1f} '
            f'L {x+0.58*fs+w:.1f} {bar_y:.1f}" fill="none" stroke="#000" stroke-width="1.2"/>'
            f'<text x="{x+0.62*fs:.1f}" y="{y:.1f}" font-size="{fs}" {FONT}>{num}</text>')


def meas(px_, py_, qx_, qy_, off=10.0, bow=None, ins_p=3.0, ins_q=3.0):
    """길이 치수 점선(교과서 규격) — **끝은 꼭짓점 옆에 감겨 붙고 가운데만 볼록**.

    끝점 오프셋을 3px 로 고정해 꼭짓점 바로 옆에서 시작·끝나게 한다. 끝까지 일정
    간격을 유지하면 예각 꼭짓점(q2 C 45°)에서 끝이 모서리를 지나쳐 밖으로 삐져
    나간다(사용자 지적 2026-08-11). off = 가운데 볼록 깊이.
    """
    L = math.hypot(qx_ - px_, qy_ - py_)
    ux_, uy_ = (qx_ - px_) / L, (qy_ - py_) / L
    nx_, ny_ = -uy_, ux_
    sgn = 1.0 if off >= 0 else -1.0
    end = 3.0 * sgn
    sx_, sy_ = px_ + ux_ * ins_p + nx_ * end, py_ + uy_ * ins_p + ny_ * end
    ex_, ey_ = qx_ - ux_ * ins_q + nx_ * end, qy_ - uy_ * ins_q + ny_ * end
    c_lat = 2.0 * off - end                    # 2차곡선 중점 = off 가 되도록
    cx_, cy_ = (px_ + qx_) / 2 + nx_ * c_lat, (py_ + qy_) / 2 + ny_ * c_lat
    return (f'<path d="M {sx_:.1f} {sy_:.1f} Q {cx_:.1f} {cy_:.1f} {ex_:.1f} {ey_:.1f}" '
            f'fill="none" stroke="#000" stroke-width="1" stroke-dasharray="4 3"/>')



def dim_label(px_, py_, qx_, qy_, off, txt, fs=13):
    """meas() 점선의 곡선 중점 위에 라벨 — paint-order 흰 테두리로 배경처리되어
    점선이 라벨 뒤에서 끊긴 것처럼 보인다(알지오매스 관행, 사용자 2026-08-11)."""
    L = math.hypot(qx_ - px_, qy_ - py_)
    nx_, ny_ = -(qy_ - py_) / L, (qx_ - px_) / L
    mx_, my_ = (px_ + qx_) / 2 + nx_ * off, (py_ + qy_) / 2 + ny_ * off
    return (f'<text x="{mx_:.1f}" y="{my_ + 0.35 * fs:.1f}" font-size="{fs}" {FONT} '
            f'text-anchor="middle" paint-order="stroke" stroke="#fff" '
            f'stroke-width="{fs * 0.5:.0f}" stroke-linejoin="round">{txt}</text>')

SVGS = {}

# ── q2: 직각삼각형 ABC (B 직각, C 45°, BC=√2, AB=x, AC=y) ────────────
SVGS["q2"] = f'''<svg viewBox="0 0 270 250" xmlns="http://www.w3.org/2000/svg">
<path d="M 65 195 L 225 195 L 65 35 Z" fill="none" stroke="#000" stroke-width="2"/>
{rangle(65, 195, 1, 0, 0, -1)}
<path d="{arc(225, 195, 30, 180, 135)}" fill="none" stroke="#000" stroke-width="1"/>
<text x="173" y="190" font-size="15" {FONT}>45°</text>
{meas(65, 35, 65, 195, off=11, bow=8)}
<text x="34" y="121" font-size="17" {IT} text-anchor="middle">x</text>
{meas(65, 35, 225, 195, off=-11, bow=8)}
<text x="163" y="98" font-size="17" {IT}>y</text>
{meas(65, 195, 225, 195, off=11, bow=8)}
{sqrt_label(133, 236, "2", 15)}
<text x="65" y="24" font-size="16" {FONT} text-anchor="middle">A</text>
<text x="52" y="210" font-size="16" {FONT} text-anchor="middle">B</text>
<text x="238" y="210" font-size="16" {FONT} text-anchor="middle">C</text>
</svg>'''

# ── q3: 사분원(r=1), 40°, B(0.76,0.64), D(1,0.84) ────────────────────
_c40, _s40, _t40 = math.cos(math.radians(40)), math.sin(math.radians(40)), math.tan(math.radians(40))
ox, oy, R = 62, 258, 235
bx, by = ox + R * _c40, oy - R * _s40
dx, dy = ox + R, oy - R * _t40
SVGS["q3"] = f'''<svg viewBox="0 0 350 300" xmlns="http://www.w3.org/2000/svg">
<line x1="{ox}" y1="{oy}" x2="335" y2="{oy}" stroke="#000" stroke-width="1"/>
<path d="M 330 {oy-4} L 338 {oy} L 330 {oy+4} Z" fill="#000"/>
<line x1="{ox}" y1="{oy}" x2="{ox}" y2="18" stroke="#000" stroke-width="1"/>
<path d="M {ox-4} 23 L {ox} 15 L {ox+4} 23 Z" fill="#000"/>
<path d="{arc(ox, oy, R, 0, 90)}" fill="none" stroke="#000" stroke-width="2"/>
<line x1="{ox}" y1="{oy}" x2="{dx:.1f}" y2="{dy:.1f}" stroke="#000" stroke-width="2"/>
<line x1="{bx:.1f}" y1="{by:.1f}" x2="{bx:.1f}" y2="{oy}" stroke="#000" stroke-width="2"/>
<line x1="{dx:.1f}" y1="{dy:.1f}" x2="{dx:.1f}" y2="{oy}" stroke="#000" stroke-width="2"/>
<line x1="{ox}" y1="{dy:.1f}" x2="{dx:.1f}" y2="{dy:.1f}" stroke="#000" stroke-width="1" stroke-dasharray="4 3"/>
<line x1="{ox}" y1="{by:.1f}" x2="{bx:.1f}" y2="{by:.1f}" stroke="#000" stroke-width="1" stroke-dasharray="4 3"/>
<path d="{arc(ox, oy, 42, 0, 40)}" fill="none" stroke="#000" stroke-width="1"/>
<text x="112" y="248" font-size="14" {FONT}>40°</text>
{rangle(bx, oy, -1, 0, 0, -1)}
{rangle(dx, oy, -1, 0, 0, -1)}
<text x="{ox-10}" y="{dy+5:.1f}" font-size="14" {FONT} text-anchor="end">0.84</text>
<text x="{ox-10}" y="{by+5:.1f}" font-size="14" {FONT} text-anchor="end">0.64</text>
<text x="{bx:.1f}" y="{oy+20}" font-size="14" {FONT} text-anchor="middle">0.76</text>
<text x="{dx:.1f}" y="{oy+20}" font-size="14" {FONT} text-anchor="middle">1</text>
<text x="{ox-8}" y="{oy+20}" font-size="15" {FONT} text-anchor="end">O</text>
<text x="336" y="{oy+22}" font-size="15" {IT}>x</text>
<text x="{ox-14}" y="26" font-size="15" {IT} text-anchor="end">y</text>
<text x="{bx+13:.1f}" y="{by+9:.1f}" font-size="15" {FONT}>B</text>
<text x="{dx+8:.1f}" y="{dy-4:.1f}" font-size="15" {FONT}>D</text>
<text x="{bx-14:.1f}" y="{oy-14}" font-size="15" {FONT} text-anchor="end">A</text>
<text x="{dx+6:.1f}" y="{oy-8}" font-size="15" {FONT}>C</text>
</svg>'''

# ── q4: 15°/30° 직각삼각형, BD=2 ─────────────────────────────────────
u = 84.0
Bx, By = 22, 152
Dx = Bx + 2 * u
Cx = Bx + (2 + math.sqrt(3)) * u
Ay = By - u  # AC = 1
SVGS["q4"] = f'''<svg viewBox="0 0 360 200" xmlns="http://www.w3.org/2000/svg">
<path d="M {Bx} {By} L {Cx:.1f} {By} L {Cx:.1f} {Ay:.1f} Z" fill="none" stroke="#000" stroke-width="2"/>
<line x1="{Dx:.1f}" y1="{By}" x2="{Cx:.1f}" y2="{Ay:.1f}" stroke="#000" stroke-width="2"/>
{rangle(Cx, By, -1, 0, 0, -1)}
<path d="{arc(Bx, By, 56, 0, 15)}" fill="none" stroke="#000" stroke-width="1"/>
<text x="{Bx+72}" y="{By-7}" font-size="14" {FONT}>15°</text>
<path d="{arc(Dx, By, 30, 0, 30)}" fill="none" stroke="#000" stroke-width="1"/>
<text x="{Dx+38:.1f}" y="{By-8}" font-size="14" {FONT}>30°</text>
{meas(Bx, By, Dx, By, off=9)}
{dim_label(Bx, By, Dx, By, 9, "2", fs=14)}
<text x="{Bx-8}" y="{By+6}" font-size="16" {FONT} text-anchor="end">B</text>
<text x="{Dx:.1f}" y="{By+18}" font-size="16" {FONT} text-anchor="middle">D</text>
<text x="{Cx+8:.1f}" y="{By+6}" font-size="16" {FONT}>C</text>
<text x="{Cx+2:.1f}" y="{Ay-8:.1f}" font-size="16" {FONT}>A</text>
</svg>'''

# ── q6: 삼각형 AB=4cm, ∠B=45°, ∠C=60° ────────────────────────────────
Ax6, Ay6, Bx6, By6 = 40, 233, 300, 233
t75, t45 = math.tan(math.radians(75)), 1.0
Cx6 = (Bx6 + t75 * Ax6) / (1 + t75)
h6 = (Bx6 - Cx6) * t45
Cy6 = By6 - h6
SVGS["q6"] = f'''<svg viewBox="0 0 340 290" xmlns="http://www.w3.org/2000/svg">
<path d="M {Ax6} {Ay6} L {Bx6} {By6} L {Cx6:.1f} {Cy6:.1f} Z" fill="none" stroke="#000" stroke-width="2"/>
<path d="{arc(Bx6, By6, 34, 180, 135)}" fill="none" stroke="#000" stroke-width="1"/>
<text x="{Bx6-56}" y="{By6-8}" font-size="14" {FONT}>45°</text>
<path d="{arc(Cx6, Cy6, 30, -105, -45)}" fill="none" stroke="#000" stroke-width="1"/>
<text x="{Cx6+16:.1f}" y="{Cy6+52:.1f}" font-size="14" {FONT} text-anchor="middle">60°</text>
{meas(Ax6, Ay6, Bx6, By6, off=10)}
{dim_label(Ax6, Ay6, Bx6, By6, 10, "4 cm")}
<text x="{Ax6-8}" y="{Ay6+8}" font-size="16" {FONT} text-anchor="end">A</text>
<text x="{Bx6+8}" y="{By6+8}" font-size="16" {FONT}>B</text>
<text x="{Cx6:.1f}" y="{Cy6-10:.1f}" font-size="16" {FONT} text-anchor="middle">C</text>
</svg>'''

# ── q7: 원 중심 O, 현(x cm), 반지름 3cm, 수선 1cm ───────────────────
cx7, cy7, R7 = 130, 112, 92
sc7 = R7 / 3.0
chy = cy7 + sc7
half = math.sqrt(9 - 1) * sc7 / 1.0
lx7, rx7 = cx7 - half, cx7 + half
SVGS["q7"] = f'''<svg viewBox="0 0 260 250" xmlns="http://www.w3.org/2000/svg">
<circle cx="{cx7}" cy="{cy7}" r="{R7}" fill="none" stroke="#000" stroke-width="2"/>
<circle cx="{cx7}" cy="{cy7}" r="2.4" fill="#000"/>
<text x="{cx7+8}" y="{cy7-6}" font-size="16" {FONT}>O</text>
<line x1="{lx7:.1f}" y1="{chy:.1f}" x2="{rx7:.1f}" y2="{chy:.1f}" stroke="#000" stroke-width="2"/>
<line x1="{cx7}" y1="{cy7}" x2="{lx7:.1f}" y2="{chy:.1f}" stroke="#000" stroke-width="2"/>
<line x1="{cx7}" y1="{cy7}" x2="{cx7}" y2="{chy:.1f}" stroke="#000" stroke-width="2"/>
{rangle(cx7, chy, -1, 0, 0, -1)}
<text x="{(cx7+lx7)/2-6:.1f}" y="{(cy7+chy)/2-8:.1f}" font-size="13" {FONT} text-anchor="end">3 cm</text>
<text x="{cx7+7}" y="{(cy7+chy)/2+6:.1f}" font-size="13" {FONT}>1 cm</text>
<line x1="{(lx7+cx7)/2:.1f}" y1="{chy-6:.1f}" x2="{(lx7+cx7)/2:.1f}" y2="{chy+6:.1f}" stroke="#000" stroke-width="1"/>
<line x1="{(cx7+rx7)/2:.1f}" y1="{chy-6:.1f}" x2="{(cx7+rx7)/2:.1f}" y2="{chy+6:.1f}" stroke="#000" stroke-width="1"/>
{meas(lx7, chy, rx7, chy, off=9)}
{dim_label(lx7, chy, rx7, chy, 9, '<tspan font-style="italic">x</tspan> cm', fs=13)}
</svg>'''

# ── q8: 접선 2개, OB=12cm, CP=8cm, PA=x cm ──────────────────────────
ox8, oy8, R8 = 100, 122, 80
Px8 = 352
alpha = math.degrees(math.acos(R8 / (Px8 - ox8)))
Ax8 = ox8 + R8 * math.cos(math.radians(alpha))
Ay8 = oy8 - R8 * math.sin(math.radians(alpha))
By8 = 2 * oy8 - Ay8
Cx8 = ox8 + R8
_uL = math.hypot(Px8 - Ax8, oy8 - Ay8)
_ux, _uy = (Px8 - Ax8) / _uL, (oy8 - Ay8) / _uL     # PA 방향
_px, _py = _uy, -_ux                                 # PA 위쪽 수직
SVGS["q8"] = f'''<svg viewBox="0 0 380 250" xmlns="http://www.w3.org/2000/svg">
<circle cx="{ox8}" cy="{oy8}" r="{R8}" fill="none" stroke="#000" stroke-width="2"/>
<line x1="{ox8}" y1="{oy8}" x2="{Ax8:.1f}" y2="{Ay8:.1f}" stroke="#000" stroke-width="2"/>
<line x1="{ox8}" y1="{oy8}" x2="{Ax8:.1f}" y2="{By8:.1f}" stroke="#000" stroke-width="2"/>
<line x1="{ox8}" y1="{oy8}" x2="{Px8}" y2="{oy8}" stroke="#000" stroke-width="2"/>
<line x1="{Ax8:.1f}" y1="{Ay8:.1f}" x2="{Px8}" y2="{oy8}" stroke="#000" stroke-width="2"/>
<line x1="{Ax8:.1f}" y1="{By8:.1f}" x2="{Px8}" y2="{oy8}" stroke="#000" stroke-width="2"/>
<circle cx="{ox8}" cy="{oy8}" r="2.4" fill="#000"/>
<text x="{ox8-14}" y="{oy8-6}" font-size="16" {FONT} text-anchor="end">O</text>
<text x="{Ax8-2:.1f}" y="{Ay8-10:.1f}" font-size="16" {FONT}>A</text>
<text x="{Ax8-2:.1f}" y="{By8+20:.1f}" font-size="16" {FONT}>B</text>
<text x="{Cx8-14}" y="{oy8-9}" font-size="15" {FONT} text-anchor="end">C</text>
<text x="{Px8+6}" y="{oy8+6}" font-size="16" {FONT}>P</text>
{meas(Ax8, Ay8, Px8, oy8, off=-9, bow=6, ins_q=14)}
<text x="{(Ax8+Px8)/2-4:.1f}" y="{(Ay8+oy8)/2-24:.1f}" font-size="12" {FONT}><tspan font-style="italic">x</tspan> cm</text>
<text x="{(Cx8+Px8)/2-28:.1f}" y="{oy8+25}" font-size="11" {FONT} text-anchor="middle">8 cm</text>
{meas(Cx8, oy8, Px8, oy8, off=8, bow=4, ins_q=30)}
{meas(ox8, oy8, Ax8, By8, off=8, bow=5, ins_p=12, ins_q=6)}
<text x="{ox8-6}" y="{oy8+54}" font-size="11.5" {FONT} text-anchor="end">12 cm</text>
</svg>'''

# ── q9: 원 O 내접 오각형, ∠A=120°, ∠D=100°, 중심각 x=∠BOC ──────────
cx9, cy9, R9 = 128, 130, 102
pts9 = {}
for k, ang in {"A": 90, "B": 150, "C": 230, "D": 310, "E": 30}.items():
    pts9[k] = (cx9 + R9 * math.cos(math.radians(ang)), cy9 - R9 * math.sin(math.radians(ang)))
pg = " ".join(P(*pts9[k]) for k in "ABCDE" if True)
A9, B9, C9, D9, E9 = (pts9[k] for k in "ABCDE")
SVGS["q9"] = f'''<svg viewBox="0 0 260 265" xmlns="http://www.w3.org/2000/svg">
<circle cx="{cx9}" cy="{cy9}" r="{R9}" fill="none" stroke="#000" stroke-width="2"/>
<polygon points="{P(*A9)} {P(*B9)} {P(*C9)} {P(*D9)} {P(*E9)}" fill="none" stroke="#000" stroke-width="2"/>
<line x1="{cx9}" y1="{cy9}" x2="{B9[0]:.1f}" y2="{B9[1]:.1f}" stroke="#000" stroke-width="2"/>
<line x1="{cx9}" y1="{cy9}" x2="{C9[0]:.1f}" y2="{C9[1]:.1f}" stroke="#000" stroke-width="2"/>
<circle cx="{cx9}" cy="{cy9}" r="2.4" fill="#000"/>
<text x="{cx9+7}" y="{cy9+5}" font-size="15" {FONT}>O</text>
<path d="{arc(cx9, cy9, 24, 150, 230)}" fill="none" stroke="#000" stroke-width="1"/>
<text x="{cx9-30}" y="{cy9+8}" font-size="15" {IT} text-anchor="end">x</text>
<path d="{arc(*A9, 26, 210, 330)}" fill="none" stroke="#000" stroke-width="1"/>
<text x="{A9[0]:.1f}" y="{A9[1]+46:.1f}" font-size="14" {FONT} text-anchor="middle">120°</text>
<path d="{arc(*D9, 24, 80, 180)}" fill="none" stroke="#000" stroke-width="1"/>
<text x="{D9[0]-30:.1f}" y="{D9[1]-26:.1f}" font-size="14" {FONT} text-anchor="middle">100°</text>
<text x="{A9[0]:.1f}" y="{A9[1]-10:.1f}" font-size="16" {FONT} text-anchor="middle">A</text>
<text x="{B9[0]-8:.1f}" y="{B9[1]-4:.1f}" font-size="16" {FONT} text-anchor="end">B</text>
<text x="{C9[0]-8:.1f}" y="{C9[1]+12:.1f}" font-size="16" {FONT} text-anchor="end">C</text>
<text x="{D9[0]+6:.1f}" y="{D9[1]+16:.1f}" font-size="16" {FONT}>D</text>
<text x="{E9[0]+8:.1f}" y="{E9[1]+4:.1f}" font-size="16" {FONT}>E</text>
</svg>'''

# ── q10: 접선 PT, ∠PTA=60°, ∠BAT=46° ────────────────────────────────
cx10, cy10, R10 = 160, 108, 86
T10 = (cx10, cy10 + R10)
A10 = (cx10 + R10 * math.cos(math.radians(150)), cy10 - R10 * math.sin(math.radians(150)))
B10 = (cx10 + R10 * math.cos(math.radians(40)), cy10 - R10 * math.sin(math.radians(40)))
SVGS["q10"] = f'''<svg viewBox="0 0 310 260" xmlns="http://www.w3.org/2000/svg">
<circle cx="{cx10}" cy="{cy10}" r="{R10}" fill="none" stroke="#000" stroke-width="2"/>
<line x1="30" y1="{T10[1]}" x2="292" y2="{T10[1]}" stroke="#000" stroke-width="2"/>
<line x1="{T10[0]}" y1="{T10[1]}" x2="{A10[0]:.1f}" y2="{A10[1]:.1f}" stroke="#000" stroke-width="2"/>
<line x1="{T10[0]}" y1="{T10[1]}" x2="{B10[0]:.1f}" y2="{B10[1]:.1f}" stroke="#000" stroke-width="2"/>
<line x1="{A10[0]:.1f}" y1="{A10[1]:.1f}" x2="{B10[0]:.1f}" y2="{B10[1]:.1f}" stroke="#000" stroke-width="2"/>
<circle cx="62" cy="{T10[1]}" r="2.6" fill="#000"/>
<path d="{arc(*T10, 30, 120, 180)}" fill="none" stroke="#000" stroke-width="1"/>
<text x="82" y="{T10[1]-12}" font-size="14" {FONT}>60°</text>
<path d="{arc(*A10, 30, -60, 5)}" fill="none" stroke="#000" stroke-width="1"/>
<text x="{A10[0]+34:.1f}" y="{A10[1]+16:.1f}" font-size="14" {FONT}>46°</text>
<text x="62" y="{T10[1]+22}" font-size="16" {FONT} text-anchor="middle">P</text>
<text x="{T10[0]}" y="{T10[1]+22}" font-size="16" {FONT} text-anchor="middle">T</text>
<text x="{A10[0]-8:.1f}" y="{A10[1]:.1f}" font-size="16" {FONT} text-anchor="end">A</text>
<text x="{B10[0]+6:.1f}" y="{B10[1]-6:.1f}" font-size="16" {FONT}>B</text>
</svg>'''

# ── q11: 지름 BC 연장선과 접선 AQ, ∠BAQ=55° ────────────────────────
cx11, cy11, R11 = 250, 103, 64
A11 = (cx11, cy11 + R11)
B11 = (cx11 + R11 * math.cos(math.radians(20)), cy11 - R11 * math.sin(math.radians(20)))
C11 = (cx11 + R11 * math.cos(math.radians(200)), cy11 - R11 * math.sin(math.radians(200)))
ty = A11[1]
t11 = (ty - B11[1]) / (C11[1] - B11[1])
P11 = (B11[0] + t11 * (C11[0] - B11[0]), ty)
SVGS["q11"] = f'''<svg viewBox="0 0 360 215" xmlns="http://www.w3.org/2000/svg">
<circle cx="{cx11}" cy="{cy11}" r="{R11}" fill="none" stroke="#000" stroke-width="2"/>
<line x1="30" y1="{ty}" x2="340" y2="{ty}" stroke="#000" stroke-width="2"/>
<line x1="{P11[0]:.1f}" y1="{ty}" x2="{B11[0]:.1f}" y2="{B11[1]:.1f}" stroke="#000" stroke-width="2"/>
<line x1="{A11[0]}" y1="{A11[1]}" x2="{B11[0]:.1f}" y2="{B11[1]:.1f}" stroke="#000" stroke-width="2"/>
<circle cx="{cx11}" cy="{cy11}" r="2.4" fill="#000"/>
<circle cx="325" cy="{ty}" r="2.4" fill="#000"/>
<path d="{arc(*A11, 19, 0, 55)}" fill="none" stroke="#000" stroke-width="1"/>
<text x="{A11[0]+22}" y="{A11[1]-7}" font-size="11.5" {FONT}>55°</text>
<path d="{arc(*B11, 24, 200, 250)}" fill="none" stroke="#000" stroke-width="1"/>
<text x="{B11[0]-14:.1f}" y="{B11[1]+30:.1f}" font-size="14" {IT}>x</text>
<path d="{arc(*P11, 26, 0, 20)}" fill="none" stroke="#000" stroke-width="1"/>
<text x="{P11[0]+28:.1f}" y="{ty-24}" font-size="14" {IT}>y</text>
<text x="{cx11}" y="{cy11-8}" font-size="15" {FONT} text-anchor="middle">O</text>
<text x="{C11[0]-6:.1f}" y="{C11[1]-8:.1f}" font-size="15" {FONT} text-anchor="end">C</text>
<text x="{B11[0]+8:.1f}" y="{B11[1]-4:.1f}" font-size="15" {FONT}>B</text>
<text x="{P11[0]-8:.1f}" y="{ty+20}" font-size="15" {FONT} text-anchor="end">P</text>
<text x="{A11[0]}" y="{ty+22}" font-size="15" {FONT} text-anchor="middle">A</text>
<text x="325" y="{ty+22}" font-size="15" {FONT} text-anchor="middle">Q</text>
</svg>'''

# ── q15: 산점도 ──────────────────────────────────────────────────────
pts15 = [(5, 8), (8, 5), (12, 28), (15, 16), (18, 48), (20, 37), (20, 28), (25, 29),
         (35, 31), (45, 26), (57, 50), (77, 8), (80, 35), (85, 36)]
ga, na = (75, 85), (103, 105)
ox15, oy15, sx, sy = 52, 262, 2.0, 2.0
grid = "".join(
    f'<line x1="{ox15+i*40}" y1="{oy15}" x2="{ox15+i*40}" y2="{oy15-220}" stroke="#999" stroke-width="0.8"/>'
    for i in range(1, 7)) + "".join(
    f'<line x1="{ox15}" y1="{oy15-j*40}" x2="{ox15+250}" y2="{oy15-j*40}" stroke="#999" stroke-width="0.8"/>'
    for j in range(1, 6))
dots = "".join(f'<circle cx="{ox15+x*sx:.0f}" cy="{oy15-y*sy:.0f}" r="3.2" fill="#000"/>'
               for x, y in pts15)
xt = "".join(f'<text x="{ox15+i*40}" y="{oy15+20}" font-size="13" {FONT} text-anchor="middle">{i*20}</text>'
             for i in range(1, 7))
yt = "".join(f'<text x="{ox15-8}" y="{oy15-j*40+5}" font-size="13" {FONT} text-anchor="end">{j*20}</text>'
             for j in range(1, 6))
SVGS["q15"] = f'''<svg viewBox="0 0 340 300" xmlns="http://www.w3.org/2000/svg">
{grid}
<line x1="{ox15}" y1="{oy15}" x2="{ox15+256}" y2="{oy15}" stroke="#000" stroke-width="1.4"/>
<path d="M {ox15+252} {oy15-4} L {ox15+260} {oy15} L {ox15+252} {oy15+4} Z" fill="#000"/>
<line x1="{ox15}" y1="{oy15}" x2="{ox15}" y2="{oy15-226}" stroke="#000" stroke-width="1.4"/>
<path d="M {ox15-4} {oy15-222} L {ox15} {oy15-230} L {ox15+4} {oy15-222} Z" fill="#000"/>
{dots}
<circle cx="{ox15+ga[0]*sx:.0f}" cy="{oy15-ga[1]*sy:.0f}" r="3.2" fill="#000"/>
<text x="{ox15+ga[0]*sx:.0f}" y="{oy15-ga[1]*sy-10:.0f}" font-size="13" {FONT} text-anchor="middle">(가)</text>
<circle cx="{ox15+na[0]*sx:.0f}" cy="{oy15-na[1]*sy:.0f}" r="3.2" fill="#000"/>
<text x="{ox15+na[0]*sx:.0f}" y="{oy15-na[1]*sy-10:.0f}" font-size="13" {FONT} text-anchor="middle">(나)</text>
{xt}{yt}
<text x="{ox15-10}" y="{oy15+18}" font-size="14" {FONT} text-anchor="end">O</text>
<text x="{ox15+266}" y="{oy15+18}" font-size="14" {IT}>x</text>
<text x="{ox15-12}" y="{oy15-222}" font-size="14" {IT} text-anchor="end">y</text>
</svg>'''

# ── s1(16): 삼각형 AB=3cm, AC=4cm, ∠A=120° ──────────────────────────
sc1 = 44.0
A16 = (95, 158)
B16 = (A16[0] + 3 * sc1 * math.cos(math.radians(125)), A16[1] - 3 * sc1 * math.sin(math.radians(125)))
C16 = (A16[0] + 4 * sc1 * math.cos(math.radians(5)), A16[1] - 4 * sc1 * math.sin(math.radians(5)))
_l1 = math.hypot(C16[0] - A16[0], C16[1] - A16[1])
_u1x, _u1y = (C16[0] - A16[0]) / _l1, (C16[1] - A16[1]) / _l1
_n1x, _n1y = -_u1y, _u1x          # AC 아래쪽 법선
SVGS["s1"] = f'''<svg viewBox="0 0 320 215" xmlns="http://www.w3.org/2000/svg">
<path d="M {P(*A16)} L {P(*B16)} L {P(*C16)} Z" fill="none" stroke="#000" stroke-width="2"/>
<path d="{arc(*A16, 26, 5, 125)}" fill="none" stroke="#000" stroke-width="1"/>
<text x="{A16[0]+14}" y="{A16[1]-30}" font-size="14" {FONT}>120°</text>
<text x="{(A16[0]+B16[0])/2-10:.1f}" y="{(A16[1]+B16[1])/2:.1f}" font-size="13" {FONT} text-anchor="end">3 cm</text>
{meas(*A16, *C16, off=9)}
{dim_label(*A16, *C16, 9, "4 cm")}
<text x="{B16[0]-4:.1f}" y="{B16[1]-8:.1f}" font-size="16" {FONT} text-anchor="middle">B</text>
<text x="{A16[0]-10}" y="{A16[1]+16}" font-size="16" {FONT} text-anchor="end">A</text>
<text x="{C16[0]+8:.1f}" y="{C16[1]+6:.1f}" font-size="16" {FONT}>C</text>
</svg>'''

# ── s2(17): 타워 개략도 — D 30°, C 60°, DC=20m ───────────────────────
gy = 190
D17, B17 = (42, gy), (300, gy)
AB17 = 150.0
C17 = (B17[0] - AB17 / math.tan(math.radians(60)), gy)
A17 = (B17[0], gy - AB17)
SVGS["s2"] = f'''<svg viewBox="0 0 360 225" xmlns="http://www.w3.org/2000/svg">
<line x1="20" y1="{gy}" x2="340" y2="{gy}" stroke="#000" stroke-width="2"/>
<line x1="{B17[0]}" y1="{gy}" x2="{A17[0]}" y2="{A17[1]:.1f}" stroke="#000" stroke-width="2"/>
<line x1="{D17[0]}" y1="{gy}" x2="{A17[0]}" y2="{A17[1]:.1f}" stroke="#000" stroke-width="2"/>
<line x1="{C17[0]:.1f}" y1="{gy}" x2="{A17[0]}" y2="{A17[1]:.1f}" stroke="#000" stroke-width="2"/>
{rangle(B17[0], gy, -1, 0, 0, -1)}
<path d="{arc(*D17, 40, 0, 30)}" fill="none" stroke="#000" stroke-width="1"/>
<text x="{D17[0]+46}" y="{gy-8}" font-size="13" {FONT}>30°</text>
<path d="{arc(C17[0], gy, 26, 0, 60)}" fill="none" stroke="#000" stroke-width="1"/>
<text x="{C17[0]+27:.1f}" y="{gy-13}" font-size="12" {FONT} text-anchor="middle">60°</text>
<text x="{(D17[0]+C17[0])/2:.1f}" y="{gy+22}" font-size="13" {FONT} text-anchor="middle">20 m</text>
<text x="{A17[0]+10}" y="{A17[1]+4:.1f}" font-size="15" {FONT}>A</text>
<text x="{B17[0]+10}" y="{gy+8}" font-size="15" {FONT}>B</text>
<text x="{C17[0]-2:.1f}" y="{gy+22}" font-size="15" {FONT} text-anchor="middle">C</text>
<text x="{D17[0]}" y="{gy+22}" font-size="15" {FONT} text-anchor="middle">D</text>
</svg>'''

# ── s3(18): 원 안 두 현 AC·BD 교차, ∠x ──────────────────────────────
cx18, cy18, R18 = 118, 120, 92
A18 = (cx18 + R18 * math.cos(math.radians(135)), cy18 - R18 * math.sin(math.radians(135)))
D18 = (cx18 + R18 * math.cos(math.radians(45)), cy18 - R18 * math.sin(math.radians(45)))
B18 = (cx18 + R18 * math.cos(math.radians(215)), cy18 - R18 * math.sin(math.radians(215)))
C18 = (cx18 + R18 * math.cos(math.radians(305)), cy18 - R18 * math.sin(math.radians(305)))


def _isect(p1, p2, p3, p4):
    x1, y1 = p1; x2, y2 = p2; x3, y3 = p3; x4, y4 = p4
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / den
    py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / den
    return px, py


P18 = _isect(A18, C18, B18, D18)
SVGS["s3"] = f'''<svg viewBox="0 0 240 245" xmlns="http://www.w3.org/2000/svg">
<circle cx="{cx18}" cy="{cy18}" r="{R18}" fill="none" stroke="#000" stroke-width="2"/>
<line x1="{A18[0]:.1f}" y1="{A18[1]:.1f}" x2="{C18[0]:.1f}" y2="{C18[1]:.1f}" stroke="#000" stroke-width="2"/>
<line x1="{B18[0]:.1f}" y1="{B18[1]:.1f}" x2="{D18[0]:.1f}" y2="{D18[1]:.1f}" stroke="#000" stroke-width="2"/>
<path d="{arc(*P18, 20, -48, 42)}" fill="none" stroke="#000" stroke-width="1"/>
<text x="{P18[0]+24:.1f}" y="{P18[1]+6:.1f}" font-size="15" {IT}>x</text>
<text x="{P18[0]-26:.1f}" y="{P18[1]+4:.1f}" font-size="14" {FONT} text-anchor="end">P</text>
<text x="{A18[0]-6:.1f}" y="{A18[1]-6:.1f}" font-size="16" {FONT} text-anchor="end">A</text>
<text x="{D18[0]+6:.1f}" y="{D18[1]-6:.1f}" font-size="16" {FONT}>D</text>
<text x="{B18[0]-8:.1f}" y="{B18[1]+10:.1f}" font-size="16" {FONT} text-anchor="end">B</text>
<text x="{C18[0]+4:.1f}" y="{C18[1]+16:.1f}" font-size="16" {FONT}>C</text>
</svg>'''

# ── s4(19): 원 O 내접 이등변삼각형, BC=12cm, r=10cm ─────────────────
cx19, cy19, R19 = 120, 132, 100
A19 = (cx19, cy19 - R19)
B19 = (cx19 + R19 * math.cos(math.radians(152)), cy19 - R19 * math.sin(math.radians(152)))
C19 = (cx19 + R19 * math.cos(math.radians(28)), cy19 - R19 * math.sin(math.radians(28)))


def _tick(p, q):
    mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
    dx, dy = q[0] - p[0], q[1] - p[1]
    L = math.hypot(dx, dy)
    nx, ny = -dy / L, dx / L
    return (f'<line x1="{mx-6*nx:.1f}" y1="{my-6*ny:.1f}" x2="{mx+6*nx:.1f}" y2="{my+6*ny:.1f}" '
            f'stroke="#000" stroke-width="1.6"/>')


SVGS["s4"] = f'''<svg viewBox="0 0 240 255" xmlns="http://www.w3.org/2000/svg">
<circle cx="{cx19}" cy="{cy19}" r="{R19}" fill="none" stroke="#000" stroke-width="2"/>
<path d="M {P(*A19)} L {P(*B19)} L {P(*C19)} Z" fill="none" stroke="#000" stroke-width="2"/>
{_tick(A19, B19)}
{_tick(A19, C19)}
<line x1="{B19[0]:.1f}" y1="{B19[1]:.1f}" x2="{C19[0]:.1f}" y2="{C19[1]:.1f}" stroke="#000" stroke-width="2"/>
{meas(*B19, *C19, off=9)}
{dim_label(*B19, *C19, 9, "12 cm", fs=12)}
<circle cx="{cx19}" cy="{cy19}" r="2.4" fill="#000"/>
<text x="{cx19}" y="{cy19+22}" font-size="15" {FONT} text-anchor="middle">O</text>
<text x="{A19[0]}" y="{A19[1]-8:.1f}" font-size="16" {FONT} text-anchor="middle">A</text>
<text x="{B19[0]-10:.1f}" y="{B19[1]+4:.1f}" font-size="16" {FONT} text-anchor="end">B</text>
<text x="{C19[0]+8:.1f}" y="{C19[1]+4:.1f}" font-size="16" {FONT}>C</text>
</svg>'''

# ── 렌더 ─────────────────────────────────────────────────────────────
# 의도 표시폭(px @96dpi) — 2배로 렌더하고 figure_src_dpi=192 로 절반 표시.
WIDTHS = {"q2": 190, "q3": 235, "q4": 262, "q6": 235, "q7": 195, "q8": 250,
          "q9": 205, "q10": 228, "q11": 268, "q15": 240, "s1": 240, "s2": 262,
          "s3": 178, "s4": 180}

if __name__ == "__main__":
    from core.figure_generator import _svg_to_png_bytes
    for k, svg in SVGS.items():
        if k == "s2":      # 사진 문항 — 원본 정리본을 별도 저장(photo_s2.py)
            continue
        png = _svg_to_png_bytes(svg, width=WIDTHS[k] * 2)
        if not png:
            print(k, "렌더 실패")
            continue
        open(os.path.join(OUT, f"{k}.png"), "wb").write(png)
        print(k, "ok", len(png))
