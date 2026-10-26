# -*- coding: utf-8 -*-
"""정답(객관식 = 답만)·정답+해설(서술형)·메타(중단원·난이도) 기입 — 세션 풀이(API 0원).

객관식은 전 문항을 처음부터 직접 풀어 '정답 선택지가 정확히 1개'임을 확인한다(학생 표시는 근거로 쓰지 않음).
"""
import json
import math
import sys
from fractions import Fraction as Fr
from itertools import permutations
from pathlib import Path

OCR = Path(__file__).resolve().parents[1] / "ocr"
CIRC = "①②③④⑤"


def factor(n):
    out, p = {}, 2
    while p * p <= n:
        while n % p == 0:
            out[p] = out.get(p, 0) + 1
            n //= p
        p += 1
    if n > 1:
        out[n] = out.get(n, 0) + 1
    return out


def ndiv(n):
    return math.prod(e + 1 for e in factor(n).values())


def only(n, flags):
    hit = [i for i, f in enumerate(flags) if f]
    assert len(hit) == 1, (n, flags)
    return CIRC[hit[0]]


def pick(n, val, opts):
    return only(n, [o == val for o in opts])


MC = {}
# 1: 675 = 3^3 × 5^2
assert factor(675) == {3: 3, 5: 2}
MC[1] = only(1, [len(factor(675)) == 1 and factor(675) == {675: 1},
                 set(factor(675)) == {3, 5, 7},
                 ndiv(675) == 10,
                 3 ** 2 * 5 ** 3 == 675,
                 ndiv(675) == 12])
# 2: 17640 = 2^3 × 3^2 × 5 × 7^2
f = factor(17640)
assert f == {2: 3, 3: 2, 5: 1, 7: 2}
a, b, c, d = f[2], f[3], f[5], f[7]
MC[2] = pick(2, a - b + c * d, [-2, 0, 2, 3, 4])
# 3: 서로소
MC[3] = only(3, [math.gcd(x, y) == 1 for x, y in
                 [(3, 12), (27, 135), (363, 636), (2 * 5 ** 3 * 7, 429), (2 * 3, 3 * 5 ** 2 * 7)]])
# 4: A 는 120 의 약수여야 한다
MC[4] = only(4, [120 % x != 0 for x in (1, 5, 12, 40, 50)])
# 5: 8⅓=25/3, 11¼=45/4, 3 8/9=35/9 → B=분모의 최소공배수, A=분자의 최대공약수
fr5 = [Fr(25, 3), Fr(45, 4), Fr(35, 9)]
B5 = math.lcm(*[x.denominator for x in fr5])
A5 = math.gcd(*[x.numerator for x in fr5])
assert all((x * Fr(B5, A5)).denominator == 1 for x in fr5) and math.gcd(A5, B5) == 1
assert (A5, B5) == (5, 36) and A5 - B5 not in (31, 32, 36, 39, 41)   # 인쇄본 A-B=-31 은 선택지에 없다
MC[5] = pick(5, B5 - A5, [31, 32, 36, 39, 41])
# 6: 증가 +, 증가 +, 전 -, 인상 +, 득점 +
signs = [+1, +1, -1, +1, +1]
MC[6] = only(6, [signs.count(s) == 1 for s in signs])
# 7: 대소 관계가 옳지 않은 것
MC[7] = only(7, [not (Fr(9, 8) > Fr(4, 3)), not (-3.5 < 0), not (0 < Fr(1, 7)), not (-4.6 < -3.7),
                 not (abs(3.1) < abs(-5.6))])
# 8: 가장 작은 값
v8 = [Fr(2) - Fr(2, 3) - Fr(7, 5) + 1,
      Fr(-2) + Fr(3, 2) + Fr(4, 5) - 1,
      Fr(37, 10) - Fr(15, 10) + Fr(22, 10) + Fr(23, 10),
      Fr(37, 10) - Fr(15, 10) - Fr(22, 10) + Fr(23, 10),
      Fr(-3) - Fr(11, 3) + Fr(37, 10) + Fr(23, 10)]
MC[8] = only(8, [x == min(v8) for x in v8])
# 9: □×□−□ 의 최댓값(서로 다른 세 수)
nums9 = [Fr(-5), Fr(-9, 2), Fr(0), Fr(5, 3), Fr(3)]
best9 = max(p * q - r for p, q, r in permutations(nums9, 3))
MC[9] = pick(9, best9, [5, 10, Fr(45, 2), 25, Fr(55, 2)])
# 10: ㉠ (-7/4)×(-5) → (-5)×(-7/4) 순서 바꿈 = 교환법칙, ㉡ 뒤 두 수를 먼저 묶음 = 결합법칙
pairs10 = [("교환", "결합"), ("교환", "분배"), ("결합", "교환"), ("결합", "분배"), ("분배", "결합")]
MC[10] = only(10, [p == ("교환", "결합") for p in pairs10])
# 11: ㄱ 참(-1×-1=1) ㄴ 거짓(0 은 역수 없음) ㄷ 참 ㄹ 거짓(0÷a=0 가능) ㅁ 거짓((-2)×(-3)=+6, 공통 부호 -)
#     ㅂ 참
assert Fr(-1) * Fr(-1) == 1 and Fr(0, 5) == 0 and (-2) * (-3) == 6 and Fr(-6, 3) == -abs(Fr(6, 3))
t11 = [True, False, True, False, False, True]
MC[11] = pick(11, sum(t11), [2, 3, 4, 5, 6])
# 12
a12 = (1 - Fr(-2, 3) ** 2 / Fr(-8, 3)) / Fr(-1, 3)
b12 = Fr(-5, 6) - (-1 + Fr(3, 4) * Fr(1, 3) ** 2 / Fr(-1, 2) ** 3)
assert (a12, b12) == (Fr(-7, 2), Fr(5, 6))
cnt12 = sum(1 for x in range(-10, 10) if a12 < x < b12)
MC[12] = pick(12, cnt12, [2, 3, 4, 5, 6])
# 13: (72a+150b)/(a+150) — 표본 값으로 다섯 식을 대조
def f13(a, b):
    return [Fr(b + 72, a), Fr(b + 72, a + 150), Fr(a + 72, b + 150), Fr(72 * a + 150 * b, a + 150),
            Fr(150 * a + 72 * b, a + 150)]
truth = lambda a, b: Fr(72 * a + 150 * b, a + 150)      # noqa: E731
MC[13] = only(13, [all(f13(a, b)[i] == truth(a, b) for a, b in ((30, 80), (7, 91))) for i in range(5)])
# 14
a14, b14 = Fr(-1, 2), Fr(-4)
v14 = [b14 - a14, a14 ** 2 * b14, -a14 / b14, a14 ** 2 / b14, -b14 / a14]
MC[14] = only(14, [x == max(v14) for x in v14])
# 15: 표본 값으로 등식 검사. ㄷ '0.x²' 는 0.1x² 의 1 을 생략한 잘못된 표기(값 비교 대상이 아님) → 거짓.
x, y, z, a, b, c = Fr(3), Fr(5), Fr(7), Fr(2), Fr(11), Fr(13)
t15 = [Fr(1) / a / b * c == 1 / (a * b * c),
       x / (y / z) == x * z / y,
       False,
       2 * b / (a / 4) == 2 * b / (4 * a),
       (a - b) * 3 == 3 * (a - b),
       x * 2 - 2 / y == 2 * x - 2 / y,
       (x - 2 * y) * (-3) == x - 2 * y - 3,
       b * (-7) * a * c == -7 * a * b * c]
MC[15] = pick(15, sum(t15), [3, 4, 5, 6, 7])
# 16
x, y = Fr(5, 7), Fr(-3, 11)
MC[16] = only(16, [-2 * (-x - 1) == 2 * x - 1,
                   Fr(-1, 3) * (9 * x - 6) == -3 * x - 2,
                   (x + Fr(1, 2)) / Fr(-1, 6) == -6 * x - 3,
                   (-9 * x - 3) / Fr(-3, 4) == -12 * x + 4,
                   (Fr(16, 3) - 8 * y) / Fr(-3, 2) == -8 + 12 * y])
# 17: -(8+5x²)/7 + x/2 = -5/7 x² + 1/2 x - 8/7 → 차수 2, 항 3개, c=-5/7, d=-8/7
a17, b17, c17, d17 = 2, 3, Fr(-5, 7), Fr(-8, 7)
MC[17] = pick(17, a17 - b17 + c17 / d17, [Fr(-43, 8), Fr(-13, 8), Fr(-23, 16), Fr(-5, 8), Fr(-3, 8)])
# 18: 2(x-4) - {7x - ((x+2)/2 - (5x+4)/4)} = ax + b
g18 = lambda x: 2 * (x - 4) - (7 * x - ((x + 2) / Fr(2) - (5 * x + 4) / Fr(4)))   # noqa: E731
b18 = g18(Fr(0))
a18 = g18(Fr(1)) - b18
assert g18(Fr(9)) == a18 * 9 + b18 and (a18, b18) == (Fr(-23, 4), -8)
MC[18] = pick(18, a18 * b18, [Fr(-31, 2), 23, 34, Fr(69, 2), 46])

# ── 서술형 검산 ──────────────────────────────────────────────────────────────
L = math.lcm(6, 14)
years = [2026 + L * k for k in range(1, 6)]
assert L == 42 and [yy for yy in years if yy > 2027][2] == 2152                     # 서술형1
a20, b20 = Fr(-5, 6) + Fr(1, 2), Fr(2, 3) - (-3)
assert (a20, b20, a20 / b20) == (Fr(-1, 3), Fr(11, 3), Fr(-1, 11))                  # 서술형2
A21 = lambda x: 5 * x - 4 + (-2 * x - 3)                                           # noqa: E731
assert all(A21(t) - (-2 * t - 3) == 5 * t - 4 and A21(t) == 3 * t - 7 and A21(t) + (-2 * t - 3) == t - 10
           for t in range(-3, 4))                                                   # 서술형3

ESSAY = {
    # 해설 한 줄은 정답면 단 폭(한글 30자 남짓)에 들어가게 짧게 — 넘치면 엔진 강제 개행 + 한글
    # 재개행으로 짧은 꼬리 줄이 생긴다(1회차 렌더 서술형 1·3).
    19: (r"$2152$년", [
        r"step1) $6=2\times 3$, $14=2\times 7$이다.",
        r"step2) 최소공배수는 $2\times 3\times 7=42$이다.",
        r"step3) 두 종의 매미는 $42$년마다 동시에 나타난다.",
        r"step4) $2026$년 다음은 $2068$년, $2110$년, $2152$년이다.",
        r"step5) 따라서 $2027$년 이후 $3$번째는 $2152$년이다.",
    ]),
    20: (r"$a=-\frac{1}{3}$, $b=\frac{11}{3}$, $a\div b=-\frac{1}{11}$", [
        r"step1) $a=-\frac{5}{6}+\frac{1}{2}=-\frac{5}{6}+\frac{3}{6}=-\frac{1}{3}$이다.",
        r"step2) $b=\frac{2}{3}-(-3)=\frac{2}{3}+\frac{9}{3}=\frac{11}{3}$이다.",
        r"step3) $a\div b=\left(-\frac{1}{3}\right)\times\frac{3}{11}=-\frac{1}{11}$이다.",
    ]),
    21: (r"$3x-7$, $x-10$", [
        r"step1) 어떤 식을 $A$라 하면 $A-(-2x-3)=5x-4$이다.",
        r"step2) $A=5x-4+(-2x-3)=3x-7$이다.",
        r"step3) 따라서 어떤 식은 $3x-7$이다.",
        r"step4) 바르게 계산하면 $(3x-7)+(-2x-3)$이다.",
        r"step5) 따라서 바르게 계산한 식은 $x-10$이다.",
    ]),
}

# ── 메타란: [중단원](중등 분류표 어휘 그대로) · [난이도](상/중/하 초안 — 배점·풀이 단계 기준) ──
# 대수회 분류표 큰분류ver.261020 의 중1(22개정) ① 단계. 13~15 는 문자를 쓴 식·식의 값·기호 생략
# (문자의 사용), 16~18·서술형 3 은 다항식·일차식 계산(일차식과 그 계산).
PF, GL, IQ, IC, LU, LE = ("소인수분해", "최대공약수와 최소공배수", "정수와 유리수", "정수와 유리수의 계산",
                          "문자의 사용", "일차식과 그 계산")
META = {1: (PF, "하"), 2: (PF, "중"), 3: (GL, "하"), 4: (GL, "중"), 5: (GL, "상"),
        6: (IQ, "하"), 7: (IQ, "하"), 8: (IC, "중"), 9: (IC, "상"), 10: (IC, "중"),
        11: (IC, "중"), 12: (IC, "상"),
        13: (LU, "중"), 14: (LU, "중"), 15: (LU, "중"), 16: (LE, "중"), 17: (LE, "상"), 18: (LE, "상"),
        19: (GL, "중"), 20: (IC, "하"), 21: (LE, "중")}
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from core.topic_vocab import vocabulary  # noqa: E402
_vocab = set(vocabulary("중1", "수학", 2026))
assert all(t in _vocab for t, _ in META.values()), [t for t, _ in META.values() if t not in _vocab]
assert len(META) == 21 and all(dv in ("상", "중", "하") for _, dv in META.values())
assert len(MC) == 18

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
