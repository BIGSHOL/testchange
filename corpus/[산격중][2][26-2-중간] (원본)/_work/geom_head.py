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


