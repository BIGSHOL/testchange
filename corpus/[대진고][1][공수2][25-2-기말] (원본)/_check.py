# -*- coding: utf-8 -*-
"""20문항 결정적 자력 검산 — 전사(계수·부호) 체크섬."""
import sys
from fractions import Fraction as F
import itertools, math
sys.stdout.reconfigure(encoding="utf-8")
R = {}

# q1 A={-1,0,1}, B={a+b}
B = {a+b for a in (-1,0,1) for b in (-1,0,1)}
R[1] = (len(B), "①5 ②6 ③7 ④8 ⑤9", sorted(B))

# q2 p: x^2-9x-36>=0 ; ~p 정수 개수
sol = [x for x in range(-50, 50) if x*x - 9*x - 36 < 0]
R[2] = (len(sol), "①12 ②13 ③14 ④15 ⑤16", (min(sol), max(sol)))

# q3 X={-1..3}, f(x)=2x^2 mod 5, 치역 합
rng = {(2*x*x) % 5 for x in (-1,0,1,2,3)}
R[3] = (sum(rng), "①2 ②3 ③5 ④9 ⑤10", sorted(rng))

# q4 f=(ax+b)/(x+c): 점근선 x=1/2, y=-2, f(0)=1
c = F(-1,2); a = -2; b = c*1   # f(0)=b/c=1 -> b=c
f = lambda x: (a*x + b)/(x + c)
g_ = ("ㄱ", a + 8*b*c == 0)
h_ = ("ㄴ", f(1) == -5)                      # f^-1(-5)=1
# ㄷ 중심 (1/2,-2) 통과 기울기1 직선: y=x-5/2
i_ = ("ㄷ", F(-2) == F(1,2) - F(5,2))
k = b - a*c                                   # f = a + (b-ac)/(x+c)
j_ = ("ㄹ", k == -2)                          # y=-2/x 와 겹침?
R[4] = ([n for n, v in (g_, h_, i_, j_) if v], "①ㄱㄴ ②ㄱㄴㄷ ③ㄱㄴㄹ ④ㄱㄷㄹ ⑤ㄴㄷㄹ", f"k={k}")

# q5 X={1,2,3}; f 일대일대응, g 항등, h 상수; f(1)=g(2)=h(3), f(1)+f(2)=g(3)
res5 = set()
for fperm in itertools.permutations((1,2,3)):
    fn = dict(zip((1,2,3), fperm))
    gn = {1:1,2:2,3:3}
    for cval in (1,2,3):
        hn = {1:cval,2:cval,3:cval}
        if fn[1] == gn[2] == hn[3] and fn[1]+fn[2] == gn[3]:
            res5.add(fn[3]+gn[1]+hn[2])
R[5] = (sorted(res5), "①3 ②4 ③5 ④6 ⑤7", "")

# q6 A={x|x^2-4x-5<=0}=[-1,5] ⊂ B=(a+3, b-2]
Ms = [a_ for a_ in range(-20, 20) if a_+3 < -1]
ms = [b_ for b_ in range(-20, 20) if b_-2 >= 5]
R[6] = (max(Ms)+min(ms), "①1 ②2 ③3 ④4 ⑤5", (max(Ms), min(ms)))

# q7 집합 항등식 — 모든 부분집합 조합 전수
U = (1,2,3)
def subsets(u):
    for r in range(len(u)+1):
        for s in itertools.combinations(u, r):
            yield frozenset(s)
UU = frozenset(U)
ok = {"ㄱ": True, "ㄴ": True, "ㄷ": True}
for A in subsets(U):
    for Bs in subsets(U):
        for Cs in subsets(U):
            if (A & Bs) | (A - Bs) != A: ok["ㄱ"] = False
            if (A - Bs) - Cs != A - (Bs & Cs): ok["ㄴ"] = False
            if ((A & (UU - (A - Bs))) | ((A | Bs) & Bs)) != Bs: ok["ㄷ"] = False
R[7] = ([k_ for k_, v in ok.items() if v], "①ㄱ ②ㄴ ③ㄷ ④ㄱ,ㄷ ⑤ㄴ,ㄷ", "")

# q8 p:|x-1|<=5 → [-4,6]; q:(x-3a)(x+2a)<=0 (a>0 → [-2a,3a]); 역·대우 참 → P=Q
cand = [a_ for a_ in (F(n, 2) for n in range(1, 21)) if -2*a_ == -4 and 3*a_ == 6]
R[8] = (cand, "①1 ②2 ③3 ④4 ⑤5", "")

# q9 P⊆Q^c, Q^c⊆R 에서 항상 참인가 (반례 탐색)
import random
def q9():
    bad = {}
    for _ in range(20000):
        Uu = set(range(6))
        P = set(random.sample(sorted(Uu), random.randint(1,5)))
        Q = set(random.sample(sorted(Uu), random.randint(1,5)))
        Rr = set(random.sample(sorted(Uu), random.randint(1,5)))
        if not (P <= Uu-Q):  continue
        if not (Uu-Q <= Rr): continue
        for name, cond in (("①P⊂R", P <= Rr), ("②P⊂Qc", P <= Uu-Q),
                           ("③R⊂Pc", Rr <= Uu-P), ("④Qc⊂R", Uu-Q <= Rr),
                           ("⑤P⊂R∩Qc", P <= (Rr & (Uu-Q)))):
            if not cond: bad[name] = bad.get(name, 0)+1
    return bad
R[9] = (q9(), "반례가 나온 것 = 옳지 않은 것", "")

# q10 f(x)=x/4+1 (x>=0), 2x+k (x<0); 역함수 존재 → k=1
k10 = 1
f10 = lambda x: F(x,4)+1 if x >= 0 else 2*x+k10
# f(x)=0 또는 f(x)=x (증가함수라 f=f^-1 ⟺ f(x)=x)
roots = []
for expr_dom, sol_ in ((lambda x: x >= 0, F(-4)), (lambda x: x < 0, F(-k10,2))):
    if expr_dom(sol_): roots.append(sol_)
for dom, sol_ in ((lambda x: x >= 0, F(4,3)), (lambda x: x < 0, F(-k10))):
    if dom(sol_): roots.append(sol_)
prod = F(1)
for r_ in roots: prod *= r_
R[10] = (prod, "①-8/3 ②-2/3 ③2/3 ④4/3 ⑤8/3", roots)

# q11 h(y)=(3-y)/(2y-1) ; 답 = h(h(2))
h11 = lambda y: F(3-y, 2*y-1) if (2*y-1) != 0 else None
R[11] = (h11(h11(2)), "①-4 ②-5 ③-6 ④-7 ⑤-8", h11(2))

# q12 f(x)=(x-3)^2/2-2 ; (f∘f)(x)=2 실근 합
import sympy as sp
x = sp.symbols('x', real=True)
f12 = (x-3)**2/2 - 2
sol12 = sp.solve(sp.Eq(f12.subs(x, f12), 2), x)
R[12] = (sp.simplify(sum(sol12)), "①4 ②6 ③10 ④12 ⑤16", [sp.nsimplify(s) for s in sol12])

# q13 y=sqrt(2x+4)+3 의 역함수 g(x)=((x-3)^2-4)/2 (x>=3) 와 y=2x+k 두 점
ks = []
for kk in [F(n,4) for n in range(-60, 20)]:
    r_ = sp.solve(sp.Eq(((x-3)**2-4)/2, 2*x+kk), x)
    good = [s for s in r_ if s.is_real and s >= 3]
    if len(set(good)) == 2: ks.append(kk)
R[13] = (max(ks), "①-10 ②-8 ③-6 ④-4 ⑤-2", (min(ks), max(ks)))

# q14 a<0,b>0,c>0 (그래프) ; g(x)=-sqrt(bx+a)-c
a14, b14, c14 = -1.0, 2.0, 3.0
dom_ok = (-a14/b14 > 0)
rng_ok = True                     # 최댓값 g(-a/b) = -c
quad = "제4사분면"                 # x>=-a/b>0, y<=-c<0
# ㄹ: bc/a < m < 0 인 y=mx 가 g 와 안 만나는가 → 반례 탐색
import numpy as np
m0 = b14*c14/a14
hit = 0
for m in np.linspace(m0*0.99, -1e-6, 50):
    xs = np.linspace(-a14/b14, 1e6, 200001)
    gg = -np.sqrt(b14*xs + a14) - c14
    if np.any(np.diff(np.sign(m*xs - gg)) != 0): hit += 1
R[14] = (f"ㄱ={dom_ok} ㄴ={rng_ok} ㄷ={quad} ㄹ교차한기울기수={hit}/50",
         "①ㄱㄴㄷ ②ㄱㄴㄹ ③ㄱㄷㄹ ④ㄴㄷㄹ ⑤ㄱㄴㄷㄹ", f"bc/a={m0}")

# q15 n(A)=5, B={(x+k)/3}, A∩B={8,11}, sumA=39, sum(A∪B)=53
kk = sp.symbols('k')
sol15 = sp.solve(sp.Eq(39 + (39+5*kk)/3 - 19, 53), kk)
k15 = sol15[0]
A15 = {8, 11, 3*8-k15, 3*11-k15}
A15 = A15 | {39 - sum(A15)}
B15 = {(v+k15)/3 for v in A15}
R[15] = (k15, "①12 ②13 ③14 ④20 ⑤24",
         f"A={sorted(A15)} sumA={sum(A15)} A∩B={sorted(A15 & B15)} sum(A∪B)={sum(A15 | B15)}")

# q16 CH = 3a/4 + 1/a 최솟값
a_ = sp.symbols('a', positive=True)
xC = ((a_ + 2/a_) + a_/2)/2
mn = sp.minimum(sp.simplify(xC), a_, sp.Interval.open(0, sp.oo))
R[16] = (sp.simplify(mn), "①√2/3 ②√3/2 ③1 ④√2 ⑤√3", sp.simplify(xC))

# 서답형1 n(U)=50 n(A)=22 n(A-B^c)=n(A∩B)=5 n(A^c∩B^c)=7
nAB = 5; nUnion = 50 - 7
R["s1"] = (nUnion - 22 + nAB, "n(B)", (nUnion,))

# 서답형2 f(x)=-x+2, f^2=id
f2 = lambda x: -x+2
def fn(n, v):
    for _ in range(n % 2 if n % 2 else 2):
        v = f2(v)
    return v
v1 = 1
for _ in range(2025 % 2 + 2*0): v1 = f2(v1)
v2 = 2
R["s2"] = (v1 + v2, "f^2025(1)+f^2026(2)", (v1, v2))

# 서답형3 (가) 모든 실수 x 에 대하여 ~p → P=∅ ; (나) p 는 ~q 의 필요조건 → Q^c ⊆ P
Ms3 = [a_ for a_ in range(-20, 20) if a_ < 0 and 36 + 20*a_ < 0]
Ns3 = [b_ for b_ in range(1, 20) if 16*b_*b_ - 256 <= 0]
R["s3"] = (max(Ms3) + max(Ns3), "M+N", (max(Ms3), max(Ns3)))

# 서답형4 y=sqrt(3x) (0<x<27), B(27,9), 삼각형 OAB 넓이 최대
s = sp.symbols('s', positive=True)
area = sp.Rational(3,2)*(9*s - s**2)
smax = sp.solve(sp.diff(area, s), s)[0]
amax = sp.simplify(area.subs(s, smax))
R["s4"] = (amax, "3^m/2^n", (sp.factorint(sp.Rational(amax).p), sp.factorint(sp.Rational(amax).q), smax))

for k_, v in R.items():
    print(k_, "→", v)
