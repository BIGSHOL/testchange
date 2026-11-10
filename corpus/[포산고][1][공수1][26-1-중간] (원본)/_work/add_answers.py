# -*- coding: utf-8 -*-
"""정답(객관식 = 답만)·정답+해설(서술형)·메타(소단원·난이도) 기입 — 세션 풀이(API 0원).

객관식은 전 문항을 처음부터 직접 풀어 '정답 선택지가 정확히 1개'임을 확인한다(학생 표시는 근거로 쓰지 않음).
"""
import itertools
import json
import math
import sys
from fractions import Fraction as Fr
from pathlib import Path

import sympy as sp

OCR = Path(__file__).resolve().parents[1] / "ocr"
CIRC = "①②③④⑤"
x = sp.symbols("x")


def only(n, flags):
    hit = [i for i, f in enumerate(flags) if f]
    assert len(hit) == 1, (n, flags)
    return CIRC[hit[0]]


def pick(n, val, opts):
    return only(n, [sp.simplify(o - val) == 0 if isinstance(o, sp.Basic) else o == val for o in opts])


MC = {}
MC[1] = pick(1, math.perm(2, 2), [1, 2, 3, 4, 5])
MC[2] = pick(2, math.comb(4, 2), [5, 6, 7, 8, 9])
MC[3] = pick(3, len({k for k in range(1, 7) if k % 3 == 0 or k % 5 == 0}), [1, 2, 3, 4, 5])
A4, B4 = 2 * x**2 + 3 * x - 1, x**2 - 2 * x + 5
MC[4] = pick(4, sp.expand(A4 + B4), [x**2 - 5 * x - 6, x**2 + x + 4, 3 * x**2 + 5 * x + 4, 3 * x**2 + x - 6,
                                      3 * x**2 + x + 4])
MC[5] = pick(5, sp.Poly(sp.expand((x - 1)**3), x).coeff_monomial(x), [-3, -1, 0, 1, 3])
a = sp.symbols("a")
sol6 = sp.solve(sp.Poly(sp.expand((x + a) * (x**2 - 2 * x + 4) - (x**3 + 8)), x).coeffs(), a, dict=True)
assert sol6 == [{a: 2}]
MC[6] = pick(6, 2, [-4, -2, 1, 2, 4])
b = sp.symbols("b")
sol7 = sp.solve(sp.Poly(sp.expand(x**2 + (a + 1) * x + 2 - (x**2 + 3 * x + b)), x).coeffs(), [a, b], dict=True)
assert sol7 == [{a: 2, b: 2}]
MC[7] = pick(7, 4, [1, 2, 3, 4, 5])
# 8: 조립제법 3 | a b c 7 → 맨 아랫줄 2 1 1 | 10. a=2, b+3·2=1, c+3·1=1, 7+3·1=10.
a8 = 2
b8 = 1 - 3 * a8
c8 = 1 - 3 * 1
assert 7 + 3 * 1 == 10
f8 = a8 * x**3 + b8 * x**2 + c8 * x + 7
q8, r8 = sp.div(f8, x - 3)
assert q8 == 2 * x**2 + x + 1 and r8 == 10
MC[8] = pick(8, a8 + b8 + c8, [-7, -5, -3, -1, 1])
MC[9] = pick(9, math.comb(4, 2) * math.comb(3, 2), [15, 16, 17, 18, 19])
p10 = sp.expand((x**2 + 3 * x) * (x**2 + 3 * x - 2) - 8)
assert sp.factor(p10) == (x - 1) * (x + 1) * (x + 2) * (x + 4)
MC[10] = only(10, [sp.rem(p10, d, x) != 0 for d in (x - 2, x - 1, x + 1, x + 2, x + 4)])
MC[11] = pick(11, sum(1 for t in itertools.product(range(1, 7), repeat=3) if sum(t) == 12), [21, 22, 23, 24, 25])
# 12: z^2 실수 ⇔ 실수부·허수부 중 하나가 0
n12 = [n for n in range(1, 50) if (n * n - 2 * n - 3) == 0 or (n - 2) == 0]
assert n12 == [2, 3]
MC[12] = pick(12, sum(n12), [3, 4, 5, 6, 7])
# 13: z=p+qi(q≠0), z^2 = z + 3 z̄
p, q = sp.symbols("p q", real=True)
z = p + sp.I * q
eq13 = sp.expand(z**2 - z - 3 * sp.conjugate(z))
s13 = [s for s in sp.solve([sp.re(eq13), sp.im(eq13)], [p, q], dict=True) if s[q] != 0]
vals13 = {sp.simplify(s[p]**2 + s[q]**2) for s in s13}
assert vals13 == {6}
MC[13] = pick(13, 6, [6, 7, 8, 9, 10])
# 14: x 로 나눈 나머지 = 상수 = (1/3)f(x) - x^2 + x → f = 3x^2 - 3x + 3r, r = f(0)+2
r = sp.symbols("r")
f14 = 3 * x**2 - 3 * x + 3 * r
r_sol = sp.solve(sp.Eq(f14.subs(x, 0) + 2, r), r)[0]
f14 = f14.subs(r, r_sol)
g14 = f14 + x**3 + 2
assert sp.rem(g14, x, x) == r_sol and sp.rem(g14, x**2 + 3 * x - 3, x) == r_sol
assert sp.simplify(f14 / 3 - x**2 + x - r_sol) == 0
MC[14] = pick(14, f14.subs(x, 1), [-3, -2, -1, 0, 1])
# 15: R(x) = k(x+1)^2 + (-2x+3), R(2) = -10
k = sp.symbols("k")
R = k * (x + 1)**2 - 2 * x + 3
k15 = sp.solve(sp.Eq(R.subs(x, 2), -10), k)[0]
MC[15] = pick(15, R.subs({k: k15, x: 1}), [-11, -7, -3, 1, 5])
# 16: 자연수 a,b,c,d — a^2+b^2=13, (a+c)^2+(b+d)^2=45
v16 = {c_ * c_ + d_ * d_ for a_, b_, c_, d_ in itertools.product(range(1, 10), repeat=4)
       if a_ * a_ + b_ * b_ == 13 and (a_ + c_)**2 + (b_ + d_)**2 == 45}
assert v16 == {10}
MC[16] = pick(16, 10, [10, 13, 16, 20, 25])

# ── 서술형 검산 ──
assert 2 * math.perm(4, 2) * math.perm(5, 2) == 480
# 서술형 4: 의자 8개에 여학생 4·남학생 3 — 여학생끼리 이웃 금지(빈 의자가 사이에 있으면 이웃 아님)
n_patterns = len({s for s in itertools.permutations("GGGGBBBE")
                  if not any(s[i] == s[i + 1] == "G" for i in range(7))})
assert n_patterns * math.factorial(4) * math.factorial(3) == 2880
aa, bb = sp.symbols("aa bb", real=True)
lhs = sp.expand(aa * sp.I * (-2 + sp.I) + 4 * bb / (1 - sp.I))
s18 = sp.solve([sp.re(lhs) - 15, sp.im(lhs) - bb], [aa, bb], dict=True)
assert s18 == [{aa: 5, bb: 10}]
# 서술형 3: a+b+c=12, a²+b²+c²=32 → ab+bc+ca=56 — 그러나 a²+b²+c² ≥ ab+bc+ca 라 실제 직육면체는 없다.
assert (12**2 - 32) // 2 == 56 and 32 < 56
f21, g21 = x**2 - x + 1, -x**2 + x + 2
assert sp.expand(f21 + g21) == 3
assert sp.expand(f21**3 + g21**3) == sp.expand(9 * x**4 - 18 * x**3 + 9 * x + 9)

ESSAY = {
    17: (r"$480$", [
        r"step1) 짝수는 $2$, $4$, $6$, $8$의 $4$개, 홀수는 $1$, $3$, $5$, $7$, $9$의 $5$개이다.",
        r"step2) 교대로 놓는 방법은 짝수부터, 홀수부터의 $2$가지이다.",
        r"step3) 짝수 자리에 짝수 $2$개를 나열하는 경우의 수는 ${}_{4}\mathrm{P}_{2}=12$이다.",
        r"step4) 홀수 자리에 홀수 $2$개를 나열하는 경우의 수는 ${}_{5}\mathrm{P}_{2}=20$이다.",
        r"step5) 따라서 구하는 경우의 수는 $2\times 12\times 20=480$이다.",
    ]),
    18: (r"$15$", [
        r"step1) $ai(-2+i)=-2ai+ai^{2}=-a-2ai$이다.",
        r"step2) $\frac{4b}{1-i}=\frac{4b(1+i)}{(1-i)(1+i)}=2b+2bi$이다.",
        r"step3) 좌변은 $(-a+2b)+(-2a+2b)i$이므로 $-a+2b=15$, $-2a+2b=b$이다.",
        r"step4) $-2a+2b=b$에서 $b=2a$이고, 이를 대입하면 $3a=15$이다.",
        r"step5) $a=5$, $b=10$이므로 $a+b=15$이다.",
    ]),
    19: (r"[문제 오류] $56$", [
        r"step1) 모든 모서리의 길이의 합이 $48$이므로 $4(a+b+c)=48$, $a+b+c=12$이다.",
        r"step2) 대각선 $\mathrm{AG}$의 길이가 $4\sqrt{2}$이므로 $a^{2}+b^{2}+c^{2}=32$이다.",
        r"step3) $S_{1}=ab$, $S_{2}=ca$, $S_{3}=bc$이다.",
        r"step4) $(a+b+c)^{2}=a^{2}+b^{2}+c^{2}+2(ab+bc+ca)$이므로 $144=32+2(ab+bc+ca)$이다.",
        r"step5) 따라서 $S_{1}+S_{2}+S_{3}=ab+bc+ca=56$이다.",
        r"step6) 그런데 $a^{2}+b^{2}+c^{2}\geq ab+bc+ca$이므로 $32\geq 56$이 되어 모순이다.",
        r"step7) 즉 조건을 만족시키는 직육면체는 없고, 식으로 구한 값은 $56$이다.",
    ]),
    20: (r"$2880$", [
        r"step1) 의자 $8$개에 $7$명이 앉으므로 빈 의자는 $1$개이다.",
        r"step2) 여학생이 앉지 않는 의자 $4$개를 먼저 일렬로 놓는다.",
        r"step3) 그 사이사이와 양 끝의 $5$곳 중 $4$곳을 골라 여학생의 의자를 둔다.",
        r"step4) 그 경우의 수는 ${}_{5}\mathrm{C}_{4}=5$이다.",
        r"step5) 여학생 $4$명을 앉히는 경우의 수는 $4!=24$이다.",
        r"step6) 남은 의자 $4$개에 남학생 $3$명을 앉히는 경우의 수는 ${}_{4}\mathrm{P}_{3}=24$이다.",
        r"step7) 따라서 구하는 경우의 수는 $5\times 24\times 24=2880$이다.",
    ]),
    21: (r"$f(x)=x^{2}-x+1$, $g(x)=-x^{2}+x+2$", [
        r"step1) (가)에서 $\{f(x)\}^{3}+\{g(x)\}^{3}=27-9f(x)g(x)$이다.",
        r"step2) (나)에서 $f(x)g(x)=-x^{4}+2x^{3}-x+2$이다.",
        r"step3) $x^{2}-x=t$로 놓으면 $f(x)g(x)=-t^{2}+t+2=(t+1)(-t+2)$이다.",
        r"step4) 즉 $f(x)$, $g(x)$는 합이 $3$, 곱이 $(x^{2}-x+1)(-x^{2}+x+2)$이다.",
        r"step5) (다)에서 $f(x)=x^{2}-x+1$, $g(x)=-x^{2}+x+2$이다.",
    ]),
}

# ── 메타란: [소단원](고등 분류표 큰분류ver.261020 ⅰ) 단계, 22개정 공통수학1) · [난이도](상/중/하 초안) ──
POLY, IDEN, REM, FACT, CPLX, CNT, PERM, COMB = ("다항식의 연산", "항등식과 미정계수", "나머지정리와 인수정리",
                                              "인수분해", "복소수", "경우의 수", "순열", "조합")
META = {1: (PERM, "하"), 2: (COMB, "하"), 3: (CNT, "하"), 4: (POLY, "하"), 5: (POLY, "하"),
        6: (FACT, "하"), 7: (IDEN, "하"), 8: (REM, "중"), 9: (COMB, "하"), 10: (FACT, "중"),
        11: (CNT, "중"), 12: (CPLX, "중"), 13: (CPLX, "중"), 14: (REM, "상"), 15: (REM, "상"),
        16: (CPLX, "상"), 17: (PERM, "중"), 18: (CPLX, "중"), 19: (POLY, "중"), 20: (PERM, "상"),
        21: (POLY, "상")}
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from core.topic_vocab import vocabulary  # noqa: E402
_vocab = set(vocabulary("고1", "공수1", 2026))
assert all(t in _vocab for t, _ in META.values()), [t for t, _ in META.values() if t not in _vocab]
assert len(META) == 21 and all(dv in ("상", "중", "하") for _, dv in META.values())
assert len(MC) == 16

for f in sorted(OCR.glob("p*_merged.json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    for qq in d["questions"]:
        n = qq["number"]
        qq["topic"], qq["difficulty"] = META[n]
        if qq.get("choices"):
            qq["answer"] = MC[n]
            qq.pop("solution", None)          # 객관식은 답만
        else:
            ans, sol = ESSAY[n]
            qq["answer"] = ans
            qq["solution"] = "\n".join(sol)
    f.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    json.loads(f.read_text(encoding="utf-8"))
sys.stdout.reconfigure(encoding="utf-8")
print("MC", " ".join(f"{n}{MC[n]}" for n in sorted(MC)))
