# -*- coding: utf-8 -*-
"""정답(객관식 = 답만)·정답+해설(서답형) 기입 — 세션 풀이(API 0원).

객관식은 전 문항을 검산해 '정답 선택지가 정확히 1개'임을 확인한다(전사 체크섬).
서답형 5(소문항형)는 소문항에만 답·해설을 둔다 → 폼 writer 가 ⑴⑵ 머리를 붙여 모은다.
"""
import json
import math
import sys
from fractions import Fraction as Fr
from itertools import permutations, product
from pathlib import Path

OCR = Path(__file__).resolve().parents[1] / "ocr"
CIRC = "①②③④⑤"

# ── 객관식 검산: 값 → 선택지 대조 ────────────────────────────────────────────
dice = list(product(range(1, 7), repeat=2))
A, B, C = Fr(1, 2), Fr(1, 4), Fr(3, 5)
calc = {
    2: (sum(1 for p in permutations("01234", 3) if p[0] != "0"), [32, 48, 60, 64, 80]),
    3: (next(n for n in range(1, 50) if Fr(n, 10 + n) == Fr(1, 3)), [3, 4, 5, 6, 7]),
    # 인쇄는 '적어도 한 사람만'(오식) — 손정정 '적어도 한 사람이' 로 읽어야 선택지에 답이 있다.
    4: (1 - (1 - A) * (1 - B) * (1 - C), [Fr(3, 40), Fr(1, 8), Fr(1, 4), Fr(3, 4), Fr(17, 20)]),
    5: (Fr(sum(1 for a, b in dice if (a + b) % 6 == 3), 36),
        [Fr(1, 12), Fr(1, 6), Fr(1, 4), Fr(1, 3), Fr(1, 2)]),
    # 6: AD 가 이등분선이자 수선 → ∠B=∠C=g, 60+(180-2g)+g/2=180 → g=40
    6: (next(g for g in range(1, 90) if 60 + (180 - 2 * g) + Fr(g, 2) == 180), [30, 34, 38, 40, 42]),
    7: (90 + Fr(150 * 3, 5) / 2, [120, 125, 130, 135, 140]),
    8: (90 - 25 - 20, [25, 30, 35, 40, 45]),
    9: (Fr(20, 2) + Fr(16 + 12 - 20, 2), [12, 13, 14, 15, 16]),
    12: (Fr(10 * 10) / Fr(25, 2), [Fr(13, 2), 7, Fr(15, 2), 8, Fr(17, 2)]),
    13: (5 * Fr(7 * 6, 5) + 7 * Fr(5 * 9, 7), [87, 88, 89, 90, 91]),
    14: (Fr(10, 2) - Fr(6, 2), [1, Fr(4, 3), Fr(5, 3), 2, Fr(7, 3)]),
    15: (Fr(16 * 2, 3), [Fr(32, 3), 11, Fr(34, 3), Fr(35, 3), 12]),
}
MC = {1: "①", 10: "②", 11: "③"}   # 1·10·11 은 서술 판단 문항(아래 주석)
# 1: ①만 반드시 일어남(②④ 는 0, ③ 1/2, ⑤ 3/4)  10: 정삼각형·정육면체(ㄱ,ㄹ)
# 11: A↔H, B↔G, C↔F, D↔E → 닮음비 3:6=1:2, EH=4, ∠E=100°, AB↔HG(③)
for n, (val, opts) in calc.items():
    hit = [i for i, o in enumerate(opts) if o == val]
    assert len(hit) == 1, (n, val, opts)
    MC[n] = CIRC[hit[0]]
assert Fr(1, 2) * Fr(3, 4) * Fr(2, 5) == Fr(3, 20)
assert math.isclose(10 ** 2, 5 * 20)          # 12: AD^2 = BD·DC

# ── 서답형 검산 ──────────────────────────────────────────────────────────────
assert sum(1 for a, b in dice if a == 2 and b != 1) == 5                 # 서답형1
assert Fr(12, 3) == 4                                                    # 서답형2
assert (180 - 80) // 2 - (180 - 40) // 2 // 2 == 15                      # 서답형3
assert Fr(38, 27 - 8) * 1 == 2                                           # 서답형4
assert Fr(12, 6) == Fr(16, 8) == Fr(8, 4)                                # 서답형5(1)
assert Fr(2, 3) * 5 == Fr(10, 3)                                         # 서답형6

ESSAY = {
    16: (r"$\frac{5}{36}$", [
        r"step1) 모든 경우의 수는 $6\times 6=36$이다.",
        r"step2) $x+y=2b$의 양변에 $2$를 곱하면 $2x+2y=4b$이다.",
        r"step3) 해가 없으려면 $x$, $y$의 계수는 각각 같고 상수항은 달라야 한다.",
        r"step4) 따라서 $a=2$이고 $4b\neq 4$, 즉 $b\neq 1$이다.",
        r"step5) $b$의 값은 $2$, $3$, $4$, $5$, $6$이므로 경우의 수는 $5$이다.",
        r"step6) 따라서 구하는 확률은 $\frac{5}{36}$이다.",
    ]),
    17: (r"$4$", [
        r"step1) 점 $\mathrm{I}$가 내심이므로 $\angle ABI=\angle IBD$이다.",
        r"step2) $\overline{AB}\parallel\overline{ID}$이므로 $\angle ABI=\angle BID$(엇각)이다.",
        r"step3) $\angle IBD=\angle BID$이므로 $\overline{BD}=\overline{ID}$이다.",
        r"step4) 같은 방법으로 $\overline{EC}=\overline{IE}$이다.",
        r"step5) $\angle IDE=\angle ABC=60^\circ$, $\angle IED=\angle ACB=60^\circ$(동위각)이다.",
        r"step6) 따라서 $\triangle IDE$는 정삼각형이고 $\overline{ID}=\overline{DE}=\overline{IE}$이다.",
        r"step7) $\overline{BD}=\overline{DE}=\overline{EC}$이고 $\overline{BC}=\overline{AC}=12$이다.",
        r"step8) 따라서 $\overline{DE}=\frac{1}{3}\times 12=4$이다.",
    ]),
    18: (r"$15^\circ$", [
        r"step1) $\overline{AB}=\overline{AC}$이므로 $\angle ABC=\frac{1}{2}\times(180^\circ-40^\circ)=70^\circ$이다.",
        r"step2) 점 $\mathrm{I}$가 내심이므로 $\angle IBC=\frac{1}{2}\times 70^\circ=35^\circ$이다.",
        r"step3) 점 $\mathrm{O}$가 외심이므로 $\angle BOC=2\angle BAC=80^\circ$이다.",
        r"step4) $\overline{OB}=\overline{OC}$이므로 $\angle OBC=\frac{1}{2}\times(180^\circ-80^\circ)=50^\circ$이다.",
        r"step5) 따라서 $\angle IBO=\angle OBC-\angle IBC=50^\circ-35^\circ=15^\circ$이다.",
    ]),
    19: (r"$2$", [
        r"step1) (가), (가)와 (나)를 합친 것, 처음 삼각뿔은 서로 닮은 삼각뿔이다.",
        r"step2) 세 삼각뿔의 닮음비는 높이의 비와 같으므로 $1:2:3$이다.",
        r"step3) 세 삼각뿔의 부피의 비는 $1^3:2^3:3^3=1:8:27$이다.",
        r"step4) (가), (나), (다)의 부피의 비는 $1:(8-1):(27-8)=1:7:19$이다.",
        r"step5) (가)의 부피를 $V$라 하면 $V:38=1:19$이다.",
        r"step6) $19V=38$이므로 $V=2$이다.",
    ]),
    21: (r"$\frac{10}{3}$", [
        r"step1) 점 $\mathrm{G}$가 $\triangle ABC$의 무게중심이므로 $\overline{BE}=\overline{EC}$, $\overline{AG}:\overline{GE}=2:1$이다.",
        r"step2) 점 $\mathrm{G}'$이 $\triangle ACD$의 무게중심이므로 $\overline{CF}=\overline{FD}$, $\overline{AG'}:\overline{G'F}=2:1$이다.",
        r"step3) $\overline{EF}=\overline{EC}+\overline{CF}=\frac{1}{2}(\overline{BC}+\overline{CD})$이다.",
        r"step4) $\overline{BC}+\overline{CD}=\overline{BD}=10$이므로 $\overline{EF}=5$이다.",
        r"step5) $\triangle AGG'$과 $\triangle AEF$에서 $\angle A$는 공통이다.",
        r"step6) $\overline{AG}:\overline{AE}=\overline{AG'}:\overline{AF}=2:3$이다.",
        r"step7) 따라서 $\triangle AGG'\sim\triangle AEF$ (SAS 닮음)이다.",
        r"step8) $\overline{GG'}:\overline{EF}=2:3$이므로 $\overline{GG'}=\frac{2}{3}\times 5=\frac{10}{3}$이다.",
    ]),
}

# 서답형 5 — 소문항별
SUB = {
    20: {
        1: (r"$\triangle ABC\sim\triangle DCA$ (SSS 닮음)", [
            r"step1) $\overline{AB}:\overline{DC}=12:6=2:1$이다.",
            r"step2) $\overline{BC}:\overline{CA}=16:8=2:1$이다.",
            r"step3) $\overline{CA}:\overline{AD}=8:4=2:1$이다.",
            r"step4) 세 쌍의 대응변의 길이의 비가 같으므로",
            r"step5) $\triangle ABC\sim\triangle DCA$ (SSS 닮음)이다.",
        ]),
        2: (r"$\triangle ABC\sim\triangle EBD$ (AA 닮음)", [
            r"step1) $\angle B$는 공통인 각이다.",
            r"step2) $\angle ACB=\angle EDB$이다.",
            r"step3) 두 쌍의 대응각의 크기가 각각 같으므로",
            r"step4) $\triangle ABC\sim\triangle EBD$ (AA 닮음)이다.",
        ]),
    },
}

# ── 메타란: [중단원](중등 분류표 ① 레벨 — data/topic_vocab.json 어휘 그대로) · [난이도](상/중/하 초안) ──
IO, SIM, PAR, CEN, CNT, PRB = ("삼각형의 내심과 외심", "도형의 닮음", "평행선과 선분의 길이의 비",
                               "삼각형의 무게 중심", "경우의 수", "확률")
META = {1: (PRB, "하"), 2: (CNT, "중"), 3: (PRB, "하"), 4: (PRB, "중"), 5: (PRB, "상"),
        6: (IO, "상"), 7: (IO, "중"), 8: (IO, "하"), 9: (IO, "중"),
        10: (SIM, "하"), 11: (SIM, "중"), 12: (SIM, "상"),
        13: (PAR, "중"), 14: (PAR, "중"), 15: (CEN, "중"),
        16: (PRB, "상"), 17: (IO, "중"), 18: (IO, "중"),
        19: (SIM, "중"),      # 닮은 도형의 부피의 비 — 분류표에 전용 중단원이 없어 '도형의 닮음'
        20: (SIM, "중"), 21: (CEN, "상")}
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from core.topic_vocab import vocabulary  # noqa: E402
_vocab = set(vocabulary("중2", "수학"))
assert all(t in _vocab for t, _ in META.values()), [t for t, _ in META.values() if t not in _vocab]
assert len(META) == 21 and all(dv in ("상", "중", "하") for _, dv in META.values())

for f in sorted(OCR.glob("p*_merged.json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    for q in d["questions"]:
        n = q["number"]
        q["topic"], q["difficulty"] = META[n]
        if q.get("choices"):
            q["answer"] = MC[n]
            q.pop("solution", None)          # 객관식은 답만(사용자 지시)
        elif n in SUB:
            for s in q["sub_questions"]:
                ans, sol = SUB[n][s["number"]]
                s["answer"] = ans
                s["solution"] = "\n".join(sol)
            q.pop("answer", None)
            q.pop("solution", None)
        else:
            ans, sol = ESSAY[n]
            q["answer"] = ans
            q["solution"] = "\n".join(sol)
    f.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    json.loads(f.read_text(encoding="utf-8"))
print("MC", "".join(f"{n}{MC[n]} " for n in sorted(MC)))
