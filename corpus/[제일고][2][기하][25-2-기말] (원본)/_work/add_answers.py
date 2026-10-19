# -*- coding: utf-8 -*-
"""정답(객관식 = 답만)·정답+해설(서술형)·메타(소단원·난이도) 기입 — 세션 풀이(API 0원).

객관식은 전 문항을 검산해 '정답 선택지가 정확히 1개'임을 확인한다(전사 체크섬).
"""
import json
import math
import sys
from fractions import Fraction as Fr
from pathlib import Path

OCR = Path(__file__).resolve().parents[1] / "ocr"
CIRC = "①②③④⑤"


def vadd(*vs):
    return tuple(sum(c) for c in zip(*vs))


def vmul(k, a):
    return tuple(k * x for x in a)


def same_dir(a, b):
    """두 2D 벡터가 같은 방향인가(양의 실수배)."""
    return a[0] * b[1] - a[1] * b[0] == 0 and a[0] * b[0] + a[1] * b[1] > 0


# ── 객관식 검산 ──────────────────────────────────────────────────────────────
# 1: 모눈 칸 좌표(오른쪽·위 양수) — 그림 판독값 그대로
VEC1 = {"a": (4, 6), "b": (-2, -5), "c": (-4, -6), "d": (6, -2), "e": (3, -1), "f": (-2, -6)}
pairs1 = [("a", "b"), ("b", "e"), ("c", "f"), ("d", "e"), ("e", "f")]
hit1 = [i for i, (x, y) in enumerate(pairs1) if same_dir(VEC1[x], VEC1[y])]


# 2: 점을 임의 좌표로 두고 각 등식을 수치로 확인
_P = {"A": (0, 0), "B": (5, 1), "C": (3, 7), "D": (-2, 4)}


def V(s):
    p, q = _P[s[0]], _P[s[1]]
    return (q[0] - p[0], q[1] - p[1])


Z = (0, 0)
eq2 = [vadd(V("AB"), vmul(-1, V("BA"))) == Z,
       vadd(V("AB"), V("CD"), V("BC")) == V("DA"),
       vadd(V("AC"), V("DB"), V("BA")) == V("CD"),
       vadd(V("AB"), V("BC"), vmul(-1, V("AB"))) == V("BC"),
       vadd(V("CB"), V("AD"), V("BA")) == Z]
hit2 = [i for i, ok in enumerate(eq2) if ok]

# 3·4: (a, b, c) 계수
q3 = vadd(vmul(2, (1, -1, 0)), vmul(3, (2, 1, -2)))
opts3 = [(8, 1, -6), (8, -1, -5), (8, -1, 3), (1, 1, 6), (1, 2, -3)]
q4 = vadd(vadd((0, 1, 0), (-1, 0, 0)), vmul(-3, vadd((0, 0, 1), (0, -1, 0))))   # (b−a) − 3(c−b)
opts4 = [(-1, 4, 3), (-1, 4, -3), (-1, -4, -4), (1, 3, -2), (1, 3, -4)]
# 5
q5 = vadd((4, -1), vmul(2, (1, 3)))
opts5 = [(2, 3), (3, 5), (4, 4), (5, 2), (6, 5)]
# 6: |AB|² 로 비교
q6 = (2 - 3) ** 2 + (-3 - 1) ** 2
opts6 = [15, 16, 17, 18, 19]
# 7: 3k + 6 = 0
q7 = Fr(-6, 3)
opts7 = [-2, -1, 1, 2, 3]
# 8: 3(x−2) + (y−3) = 0 — 계수 (a, b, c) 를 정규화해 비교
q8 = (3, 1, -9)
opts8 = [(1, -1, 1), (1, 2, -3), (2, 1, -3), (3, -2, 3), (3, 1, -9)]
# 9: 윗면 ABCD 와 만나는 면 = 옆면 4개, 아랫면 EFGH 는 평행
faces9 = ["ABFE", "BCGF", "CDHG", "DAEH", "EFGH"]
hit9 = [i for i, f in enumerate(faces9) if not set(f) & set("ABCD")]
# 10: 삼수선의 정리 → CB⊥AB, CB = AB·tan60° = 30√3, 높이² = CB² − BD² = 2700 − 1600
q10 = 2700 - 40 ** 2
opts10 = [900, 1000, 1100, 1200, 1300]                     # 30², (10√10)², (10√11)², (20√3)², (10√13)²
# 11: S′ = S cos60°
q11 = Fr(4, 2)
# 12: x축 위 수선의 발
q12 = (3, 0, 0)
opts12 = [(0, 0, 4), (0, -2, 4), (0, -2, 0), (3, 0, 0), (3, 0, 4)]
# 13: 대각선 AC 의 중점 = (−1, 2, 1) → A = 2M − C
q13 = tuple(2 * m - c for m, c in zip((-1, 2, 1), (-4, 1, 2)))
opts13 = [(2, 3, 0), (3, 2, 0), (3, 3, 2), (-2, -4, 0), (-2, -4, 2)]
# 14: 원점–중심 거리 = √(1+16+8) = 5, 최솟값 (5−3)²
_oc2 = 1 + 16 + 8
assert math.isqrt(_oc2) ** 2 == _oc2
q14 = (math.isqrt(_oc2) - 3) ** 2

calc = {
    3: (q3, opts3), 4: (q4, opts4), 5: (q5, opts5), 6: (q6, opts6), 7: (q7, opts7), 8: (q8, opts8),
    10: (q10, opts10), 11: (q11, [1, 2, 3, 4, 5]), 12: (q12, opts12), 13: (q13, opts13),
    14: (q14, [1, 2, 3, 4, 5]),
}
MC = {}
for n, hit in ((1, hit1), (2, hit2), (9, hit9)):
    assert len(hit) == 1, (n, hit)
    MC[n] = CIRC[hit[0]]
for n, (val, opts) in calc.items():
    hit = [i for i, o in enumerate(opts) if o == val]
    assert len(hit) == 1, (n, val, opts)
    MC[n] = CIRC[hit[0]]
assert len(MC) == 14

# ── 서술형 검산 ──────────────────────────────────────────────────────────────
# 서술형1: p−q = −a+3b, q−r = (4−k)a − 9b ∥ → (4−k)/(−1) = −9/3
assert Fr(-9, 3) * -1 == 3 and 4 - 1 == 3
# 서술형2: a·b = (9−1−4)/2 = 2, |a−2b|² = 1 − 8 + 16 = 9
assert Fr(9 - 1 - 4, 2) == 2 and 1 - 4 * 2 + 4 * 4 == 9
# 서술형3: PA+PB = (−2x, 2−2y), 4x² + 4(y−1)² = 16
for x, y in ((2, 1), (0, 3), (-2, 1), (0, -1)):
    assert (-2 * x) ** 2 + (2 - 2 * y) ** 2 == 16 and x * x + (y - 1) ** 2 == 4
# 서술형4: EG = 5, HI = 12/5, DI² = 1 + 144/25 = 169/25
assert Fr(3 * 4, 5) == Fr(12, 5) and 1 + Fr(12, 5) ** 2 == Fr(13, 5) ** 2
# 서술형5: G = △OBC(넓이 9), cosθ = OM/FM = 3/(3√3) — 3D 좌표로 확인
_s = 6 / math.sqrt(2)
_B, _C, _F = (0, _s, 0), (-_s, 0, 0), (0, 0, -_s)
_n1 = (0, 0, 1)
_u = tuple(c - b for b, c in zip(_B, _C))
_w = tuple(f - b for b, f in zip(_B, _F))
_n2 = (_u[1] * _w[2] - _u[2] * _w[1], _u[2] * _w[0] - _u[0] * _w[2], _u[0] * _w[1] - _u[1] * _w[0])
_cos = abs(sum(a * b for a, b in zip(_n1, _n2))) / math.sqrt(sum(c * c for c in _n2))
assert math.isclose(_cos, 1 / math.sqrt(3)) and math.isclose(36 / 4 * _cos, 3 * math.sqrt(3))
# 서술형6: P = ((3a+1)/4, (3+b)/4, (3+c)/4), Q = (2−a, 2b−1, 2c−1)
_a, _b, _c = 2, -3, -3
assert (3 + _b, 3 + _c, 2 - _a) == (0, 0, 0) and _a + _b + _c == -4

ESSAY = {
    15: (r"$1$", [
        r"step1) $\vec{p}-\vec{q}=(3\vec{a}+\vec{b})-(4\vec{a}-2\vec{b})=-\vec{a}+3\vec{b}$이다.",
        r"step2) $\vec{q}-\vec{r}=(4\vec{a}-2\vec{b})-(k\vec{a}+7\vec{b})=(4-k)\vec{a}-9\vec{b}$이다.",
        r"step3) 두 벡터가 서로 평행하므로 $\vec{q}-\vec{r}=t(\vec{p}-\vec{q})$인 $0$이 아닌 실수 $t$가 있다.",
        r"step4) $(4-k)\vec{a}-9\vec{b}=-t\vec{a}+3t\vec{b}$이다.",
        r"$\vec{a}$, $\vec{b}$는 영벡터가 아니고 서로 평행하지 않으므로 $4-k=-t$, $-9=3t$이다.",
        r"step5) $t=-3$이므로 $4-k=3$, 즉 $k=1$이다.",
    ]),
    16: (r"$3$", [
        r"step1) $|\vec{a}+\vec{b}|^{2}=|\vec{a}|^{2}+2\vec{a}\cdot\vec{b}+|\vec{b}|^{2}$이므로 "
        r"$9=1+2\vec{a}\cdot\vec{b}+4$이다.",
        r"step2) 따라서 $\vec{a}\cdot\vec{b}=2$이다.",
        r"step3) $|\vec{a}-2\vec{b}|^{2}=|\vec{a}|^{2}-4\vec{a}\cdot\vec{b}+4|\vec{b}|^{2}=1-8+16=9$이다.",
        r"step4) $|\vec{a}-2\vec{b}|\geq0$이므로 $|\vec{a}-2\vec{b}|=3$이다.",
    ]),
    17: (r"$x^{2}+(y-1)^{2}=4$", [
        r"step1) 점 $\mathrm{P}$의 좌표를 $(x, y)$라 하면 $\overrightarrow{PA}=(1-x, 2-y)$, "
        r"$\overrightarrow{PB}=(-1-x, -y)$이다.",
        r"step2) $\overrightarrow{PA}+\overrightarrow{PB}=(-2x, 2-2y)$이다.",
        r"step3) $\left|\overrightarrow{PA}+\overrightarrow{PB}\right|=4$이므로 $(-2x)^{2}+(2-2y)^{2}=16$이다.",
        r"step4) 양변을 $4$로 나누면 $x^{2}+(y-1)^{2}=4$이다.",
        r"step5) 따라서 점 $\mathrm{P}$가 그리는 도형은",
        r"중심이 $(0, 1)$이고 반지름의 길이가 $2$인 원이다.",
    ]),
    18: (r"$\frac{13}{5}$", [
        r"step1) $\overline{DH}$는 평면 $\mathrm{EFGH}$에 수직이고 $\overline{DI}\perp\overline{EG}$이다.",
        r"따라서 삼수선의 정리에 의하여 $\overline{HI}\perp\overline{EG}$이다.",
        r"step2) $\overline{EH}=\overline{AD}=3$, $\overline{HG}=\overline{DC}=4$이므로 "
        r"$\overline{EG}=\sqrt{3^{2}+4^{2}}=5$이다.",
        r"step3) 직각삼각형 $\mathrm{EHG}$의 넓이에서 $\frac{1}{2}\times3\times4=\frac{1}{2}\times5\times\overline{HI}$"
        r"이므로 $\overline{HI}=\frac{12}{5}$이다.",
        r"step4) $\overline{DH}=\overline{AE}=1$이고 삼각형 $\mathrm{DHI}$는 $\angle DHI=90^{\circ}$인 직각삼각형이다.",
        r"step5) 따라서 $\overline{DI}=\sqrt{1^{2}+\left(\frac{12}{5}\right)^{2}}=\sqrt{\frac{169}{25}}=\frac{13}{5}$이다.",
    ]),
    19: (r"$3\sqrt{3}$", [
        r"step1) 정사각형 $\mathrm{BCDE}$의 두 대각선의 교점을 $\mathrm{O}$라 하면",
        r"꼭짓점 $\mathrm{A}$에서 평면 $\mathrm{BCDE}$에 내린 수선의 발은 $\mathrm{O}$이다.",
        r"step2) 따라서 도형 $\mathit{G}$는 삼각형 $\mathrm{OBC}$이다.",
        r"그 넓이는 정사각형 $\mathrm{BCDE}$의 넓이의 $\frac{1}{4}$이므로 $\frac{1}{4}\times6^{2}=9$이다.",
        r"step3) 선분 $\mathrm{BC}$의 중점을 $\mathrm{M}$이라 하면",
        r"$\overline{OM}\perp\overline{BC}$, $\overline{FM}\perp\overline{BC}$이므로",
        r"두 평면 $\mathrm{BCDE}$, $\mathrm{BCF}$가 이루는 각의 크기를 $\theta$라 하면 $\theta=\angle OMF$이다.",
        r"step4) $\overline{OM}=3$, $\overline{FM}=\frac{\sqrt{3}}{2}\times6=3\sqrt{3}$이고 $\angle FOM=90^{\circ}$"
        r"이므로 $\cos\theta=\frac{3}{3\sqrt{3}}=\frac{\sqrt{3}}{3}$이다.",
        r"step5) 따라서 구하는 정사영의 넓이는 $9\times\frac{\sqrt{3}}{3}=3\sqrt{3}$이다.",
    ]),
    20: (r"$-4$", [
        r"step1) 선분 $\mathrm{AB}$를 $1:3$으로 내분하는 점 $\mathrm{P}$의 좌표는 "
        r"$\left(\frac{1+3a}{4}, \frac{b+3}{4}, \frac{c+3}{4}\right)$이다.",
        r"step2) 점 $\mathrm{P}$가 $x$축 위에 있으므로 $\frac{b+3}{4}=0$, $\frac{c+3}{4}=0$, 즉 $b=-3$, $c=-3$이다.",
        r"step3) 선분 $\mathrm{AB}$를 $2:1$로 외분하는 점 $\mathrm{Q}$의 좌표는",
        r"$\left(\frac{2-a}{2-1}, \frac{2b-1}{2-1}, \frac{2c-1}{2-1}\right)=(2-a, 2b-1, 2c-1)$이다.",
        r"step4) 점 $\mathrm{Q}$가 $yz$평면 위에 있으므로 $2-a=0$, 즉 $a=2$이다.",
        r"step5) 따라서 $a+b+c=2+(-3)+(-3)=-4$이다.",
    ]),
}

# ── 메타란: [소단원](고등 분류표 어휘 그대로) · [난이도](상/중/하 초안 — 배점·풀이 단계 기준) ──
META = {1: ("벡터의 뜻", "하"), 2: ("벡터의 덧셈과 뺄셈", "중"), 3: ("벡터의 실수배", "하"),
        4: ("위치벡터", "중"), 5: ("평면벡터의 성분", "하"), 6: ("평면벡터의 성분", "하"),
        7: ("평면벡터의 내적과 수직,평행", "하"), 8: ("직선의 방정식", "중"),
        9: ("직선과 평면의 위치관계", "하"), 10: ("삼수선의 정리", "상"), 11: ("정사영", "중"),
        12: ("공간에서의 점의 좌표", "하"), 13: ("선분의 내분점과 외분점", "중"), 14: ("구의 방정식", "상"),
        15: ("벡터의 실수배", "중"), 16: ("평면벡터의 내적", "중"), 17: ("원의 방정식", "중"),
        18: ("삼수선의 정리", "상"), 19: ("정사영", "상"), 20: ("선분의 내분점과 외분점", "중")}
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from core.topic_vocab import vocabulary  # noqa: E402
_vocab = set(vocabulary("고2", "기하"))
assert all(t in _vocab for t, _ in META.values()), [t for t, _ in META.values() if t not in _vocab]
assert len(META) == 20 and all(dv in ("상", "중", "하") for _, dv in META.values())

for f in sorted(OCR.glob("p*_merged.json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    for q in d["questions"]:
        n = q["number"]
        q["topic"], q["difficulty"] = META[n]
        if q.get("choices"):
            q["answer"] = MC[n]
            q.pop("solution", None)          # 객관식은 답만
        else:
            ans, sol = ESSAY[n]
            q["answer"] = ans
            q["solution"] = "\n".join(sol)
    f.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    json.loads(f.read_text(encoding="utf-8"))
sys.stdout.reconfigure(encoding="utf-8")
print("MC", " ".join(f"{n}{MC[n]}" for n in sorted(MC)))
