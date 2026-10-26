# -*- coding: utf-8 -*-
"""정답(객관식 = 답만)·정답+해설(서술형)·메타(중단원·난이도) 기입 — 세션 풀이(API 0원).

객관식은 전 문항을 검산해 '정답 선택지가 정확히 1개'임을 확인한다(전사 체크섬).
"""
import json
import math
import sys
from fractions import Fraction as Fr
from itertools import combinations, product
from pathlib import Path

OCR = Path(__file__).resolve().parents[1] / "ocr"
CIRC = "①②③④⑤"

# ── 객관식 검산: 값 → 선택지 대조 ────────────────────────────────────────────
# 1: □ABCD∽□HIJA(A↔H, D↔A) 닮음비 AD:HA=4:12 → AB=HI/3=3. □ABCD∽□AEFG 닮음비 AD:AG=4:20 → AE=15.
q1 = 5 * Fr(9, 3) - Fr(9, 3)
# 3: △ABM∽△MCN → CN=BM·MC/AB=1, DN=3, 넓이=½·DN·MC
q3 = Fr(1, 2) * (4 - Fr(2 * 2, 4)) * 2
# 5: △ABF∽△FCE, △FBC∽△ECD → AB:FC=FC:ED → FC²=AB·ED
q5 = math.isqrt(5 * 20)
assert q5 * q5 == 100
# 6: 반지름 2·4·5(높이 비 = 반지름 차의 비 → (4-r):(5-4)=2:1) → 부피 8:64:125
r6 = 4 - 2 * (5 - 4)
q6 = Fr(4 ** 3 - r6 ** 3, 5 ** 3 - 4 ** 3)
# 7: 좌표 검산 — B(0,0) C(2c,0) A(a,h), ch=12 → △AEP=ch/2
def _area(p, q, r):
    return abs((q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])) / 2
_a, _c, _h = Fr(7, 5), Fr(3), Fr(4)                       # ch = 12
_A, _B, _C = (_a, _h), (Fr(0), Fr(0)), (2 * _c, Fr(0))
assert _area(_A, _B, _C) == 12
_D = ((_A[0] + _B[0]) / 2, _h / 2); _F = ((_A[0] + _C[0]) / 2, _h / 2); _E = (_c, Fr(0))
_P = (_F[0] + (_F[0] - _D[0]) / 2, _F[1])
q7 = _area(_A, _E, _P)
# 8: △ABE∽△CBA → BC=AB·AC/AE=12, BE=AB·AE/AC=3, DE∥AB → DE=AB·EC/BC
q8 = Fr(6) * (12 - 3) / 12
# 9: AD=2·MN−BC=6, GG'=AD/3
q9 = Fr(2 * 9 - 12, 3)
# 10: 좌표 검산 — B(0,0) C(2,0) P(1,0) A(a,h) D(a+2,h), 2h=330
_a, _h = Fr(1, 2), Fr(165)
_Q = (_a + 2 - _a / 4, _h * 3 / 4)
_Ept = (Fr(4, 11) * _Q[0], Fr(4, 11) * _Q[1]); _Fpt = (Fr(4, 5) * _Q[0], Fr(4, 5) * _Q[1])
def _on(p, a, b):
    return (b[0] - a[0]) * (p[1] - a[1]) == (b[1] - a[1]) * (p[0] - a[0])
assert _on(_Ept, (_a, _h), (Fr(1), Fr(0))) and _on(_Fpt, (Fr(1), Fr(0)), (_a + 2, _h))
q10 = _area(_Ept, (Fr(1), Fr(0)), _Fpt)
# 13: n/110·n/170 이 유한소수 ⇔ 11|n 또는 17|n
q13 = sum(1 for n in range(1, 101) if n % 11 == 0 or n % 17 == 0)
# 14: (가위, 보, 보) 1가지 / 27
q14 = Fr(sum(1 for a, b, c in product("가바보", repeat=3) if (a, b, c) == ("가", "보", "보")), 27)
# 15: 1,3,…,15 중 소수가 아닌 것
_pr = lambda n: n > 1 and all(n % d for d in range(2, n))
q15 = Fr(sum(1 for n in range(1, 16, 2) if not _pr(n)), 8)
# 16
_tri = [t for t in combinations((5, 6, 8, 10, 15, 17), 3) if t[0] + t[1] > t[2]]
_rt = [t for t in _tri if t[0] ** 2 + t[1] ** 2 == t[2] ** 2]
assert (len(_tri), _rt) == (11, [(6, 8, 10), (8, 15, 17)])
q16 = Fr(len(_tri), 20) + Fr(len(_rt), 20)

calc = {
    1: (q1, [9, 10, 12, 15, 16]),
    3: (q3, [2, 3, 4, 5, 6]),
    5: (q5, [7, 8, 9, 10, 11]),
    6: (q6, [Fr(16, 25), Fr(56, 53), Fr(56, 61), Fr(64, 61), Fr(64, 125)]),
    7: (q7, [3, 4, 5, 6, 7]),
    8: (q8, [Fr(41, 10), Fr(42, 10), Fr(43, 10), Fr(44, 10), Fr(45, 10)]),
    9: (q9, [1, 2, 3, 4, 5]),
    10: (q10, [27, Fr(99, 2), 72, Fr(165, 2), 99]),
    11: (16 - 4, [10, 12, 14, 18, 20]),                       # 닮은 도형의 넓이 ∝ 변², AB²=AC²+BC²
    12: (12 ** 2 + (16 * Fr(12, 20 + 12)) ** 2, [100, 108, 120, 150, 180]),   # BD:DC=AB:AC=20:12
    13: (q13, [11, 12, 13, 14, 15]),
    14: (q14, [Fr(1, 27), Fr(1, 18), Fr(1, 9), Fr(1, 6), Fr(1, 3)]),
    15: (q15, [Fr(1, 5), Fr(1, 4), Fr(3, 8), Fr(1, 2), Fr(5, 8)]),
    16: (q16, [Fr(1, 10), Fr(11, 120), Fr(11, 20), Fr(6, 10), Fr(13, 20)]),
}
# 2: ㄱ(12:16=9:12)·ㅁ(9:3=6:2)·ㅂ(12:8=9:6) 만 평행 — ㄴ(AE:AC=DE:BC 뿐, 끼인각 아님)·ㄷ(3:5≠4:6)·ㄹ(4:3≠5:4)
assert Fr(12, 16) == Fr(9, 12) and Fr(9, 3) == Fr(6, 2) and Fr(20 - 8, 8) == Fr(15 - 6, 6)
assert Fr(3, 5) != Fr(4, 6) and Fr(4, 3) != Fr(5, 4)
# 4: 중간 깃발 ∠E=70° → 꼭지각 F=40°인 이등변. 큰 깃발 꼭지각 C=40°(ㄹ)·∠A=70°(ㅁ✗), 작은 깃발 HI=GI=25(ㄱ)·∠G=70°(ㄷ✗)·GH≠25(ㄴ✗)
assert 180 - 70 - 40 == 70 and not math.isclose(2 * 25 * math.sin(math.radians(20)), 25)
MC = {2: "①", 4: "②"}
for n, (val, opts) in calc.items():
    hit = [i for i, o in enumerate(opts) if o == val]
    assert len(hit) == 1, (n, val, opts)
    MC[n] = CIRC[hit[0]]

# ── 서술형 검산 ──────────────────────────────────────────────────────────────
assert 25 - Fr(20 * 20, 25) == 9                                           # 서술형1
assert 17 ** 2 - 8 ** 2 == 15 ** 2 and 15 ** 2 + 20 ** 2 == 25 ** 2        # 서술형2
assert Fr(5 * 15, 9) * Fr(4 * 6, 5) == 40                                  # 서술형3
assert Fr(5 * 2 + 1, 8 * 2 + 1) == Fr(11, 17)                              # 서술형4
assert (Fr(12, 14) * Fr(11, 13) * Fr(2, 12) + Fr(12, 14) * Fr(2, 13) * Fr(1, 12)
        + Fr(2, 14) * Fr(12, 13) * Fr(1, 12)) == Fr(1, 7)                  # 서술형5

ESSAY = {
    17: (r"$9$", [
        r"step1) $\triangle ABC$와 $\triangle DAC$에서 $\angle C$는 공통이다.",
        r"step2) $\angle ABC=\angle DAC$이므로 $\triangle ABC\sim\triangle DAC$ (AA 닮음)이다.",
        r"step3) $\overline{AC}:\overline{DC}=\overline{BC}:\overline{AC}$이므로 $20:\overline{DC}=25:20$이다.",
        r"step4) $25\times\overline{DC}=400$이므로 $\overline{DC}=16$이다.",
        r"step5) 따라서 $\overline{BD}=\overline{BC}-\overline{DC}=25-16=9$이다.",
    ]),
    18: (r"$\overline{AC}=15$, $\angle ACB=\angle CAD=90^\circ$(엇각)이므로 평행하다.", [
        r"step1) $\triangle ABC$는 $\angle ACB=90^\circ$인 직각삼각형이다.",
        r"step2) $\overline{AC}^2=17^2-8^2=225$이고 $\overline{AC}>0$이므로 $\overline{AC}=15$이다.",
        r"step3) $\triangle ACD$에서 $\overline{AC}^2+\overline{DA}^2=15^2+20^2=625$이다.",
        r"step4) $\overline{CD}^2=25^2=625$이므로 $\overline{AC}^2+\overline{DA}^2=\overline{CD}^2$이다.",
        r"step5) 따라서 $\triangle ACD$는 $\angle CAD=90^\circ$인 직각삼각형이다.",
        r"step6) $\angle ACB=\angle CAD=90^\circ$로 엇각의 크기가 같다.",
        r"step7) 따라서 $\overline{AD}\parallel\overline{BC}$이다.",
    ]),
    19: (r"$40$", [
        r"step1) $\overline{BC}\parallel\overline{DE}$이므로 $\overline{AD}:\overline{AB}=\overline{DE}:\overline{BC}$이다.",
        r"step2) $5:9=x:15$이므로 $9x=75$, $x=\frac{25}{3}$이다.",
        r"step3) $\overline{AD}:\overline{DB}=\overline{AE}:\overline{EC}$이므로 $5:4=6:y$이다.",
        r"step4) $5y=24$이므로 $y=\frac{24}{5}$이다.",
        r"step5) 따라서 $xy=\frac{25}{3}\times\frac{24}{5}=40$이다.",
    ]),
    20: (r"$10$", [
        r"step1) 처음 전체 사탕의 개수를 $8k$, 딸기 맛 사탕의 개수를 $5k$라 하자.",
        r"step2) 딸기 맛 사탕을 하나 더 넣으면 전체는 $8k+1$, 딸기 맛은 $5k+1$이다.",
        r"step3) $\frac{5k+1}{8k+1}=\frac{11}{17}$이므로 $17(5k+1)=11(8k+1)$이다.",
        r"step4) $85k+17=88k+11$이므로 $3k=6$, $k=2$이다.",
        r"step5) 따라서 처음 딸기 맛 사탕의 개수는 $5\times 2=10$이다.",
    ]),
    21: (r"$\frac{1}{7}$", [
        r"step1) 세 번째 학생이 노란 구슬을 꺼내는 경우는 세 가지이다.",
        r"step2) (흰, 흰, 노란)일 확률은 $\frac{12}{14}\times\frac{11}{13}\times\frac{2}{12}=\frac{11}{91}$이다.",
        r"step3) (흰, 노란, 노란)일 확률은 $\frac{12}{14}\times\frac{2}{13}\times\frac{1}{12}=\frac{1}{91}$이다.",
        r"step4) (노란, 흰, 노란)일 확률은 $\frac{2}{14}\times\frac{12}{13}\times\frac{1}{12}=\frac{1}{91}$이다.",
        r"step5) 따라서 구하는 확률은 $\frac{11}{91}+\frac{1}{91}+\frac{1}{91}=\frac{13}{91}=\frac{1}{7}$이다.",
    ]),
}

# ── 메타란: [중단원](중등 분류표 어휘 그대로) · [난이도](상/중/하 초안 — 배점·풀이 단계 기준) ──
SIM, PAR, CEN, PYT, CNT, PRB = ("도형의 닮음", "평행선과 선분의 길이의 비", "삼각형의 무게 중심",
                               "피타고라스 정리", "경우의 수", "확률")
META = {1: (SIM, "하"), 2: (PAR, "중"), 3: (SIM, "하"), 4: (SIM, "중"), 5: (SIM, "중"),
        6: (SIM, "상"), 7: (PAR, "상"),     # 7: 삼각형의 두 변의 중점을 연결한 선분
        8: (SIM, "중"), 9: (CEN, "중"), 10: (SIM, "상"),
        11: (PYT, "하"), 12: (PYT, "중"),
        13: (CNT, "중"), 14: (PRB, "중"), 15: (PRB, "하"), 16: (PRB, "상"),
        17: (SIM, "중"), 18: (PYT, "중"), 19: (PAR, "하"), 20: (PRB, "중"), 21: (PRB, "상")}
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from core.topic_vocab import vocabulary  # noqa: E402
_vocab = set(vocabulary("중2", "수학", 2025))
assert all(t in _vocab for t, _ in META.values()), [t for t, _ in META.values() if t not in _vocab]
assert len(META) == 21 and all(dv in ("상", "중", "하") for _, dv in META.values())

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
