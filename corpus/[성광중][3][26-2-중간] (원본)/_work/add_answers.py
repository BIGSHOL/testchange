# -*- coding: utf-8 -*-
"""정답 기입 — 객관식 18문항(답만). 검산은 아래 numeric check 로 재확인."""
import json, math, os

T = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S3, S2 = math.sqrt(3), math.sqrt(2)
d = math.radians

# 독립 수치 검산: (정답번호, 계산값, 해당 선택지 값)
chk = {
    1: (1, 6 / math.sqrt(64 - 36), 3 * math.sqrt(7) / 7),
    2: (2, round(1 - 0.8746, 4), 0.1254),
    4: (3, (4 * S3 + 4 - 8) / 2, 2 * S3 - 2),
    5: (4, (5 + 2 - 1) / (2 * math.sqrt(5) * S2), 3 * math.sqrt(10) / 10),
    6: (3, 8 * 0.6 + 8 * 0.8, 11.2),
    7: (2, 10 / (1 - 1 / S3), 5 * (3 + S3)),
    8: (1, 8 * math.pi - 0.5 * 16 * math.sin(d(120)), 8 * math.pi - 4 * S3),
    9: (4, 0.5 * (6 * S3 - 6 * math.tan(d(30))) * 6, 12 * S3),
    10: (4, 2 * math.sqrt(36 - 4), 8 * S2),
    11: (5, S3 / 4 * (4 * S3) ** 2 + 16 * math.pi, 12 * S3 + 16 * math.pi),
    12: (4, 2 * (0.5 * 3 * 8) / 5, 24 / 5),
    13: (1, 25 * 2 / 5, 10),
    14: (3, 8 - 6, 2),
    15: (2, math.pi * (256 / 8), 32 * math.pi),
    16: (5, (576 - 144) / 24, 18),
    17: (2, 4 + 4 * S2, 4 + 4 * S2),
    18: (1, 0.5 * S3 * 6, 3 * S3),
}
for n, (_, got, want) in chk.items():
    assert abs(got - want) < 1e-6, (n, got, want)
# 3번 보기: ㄱ·ㄴ·ㄷ 모두 참
g = (1 - math.cos(d(45)) - math.sin(d(30))) * (1 + math.sin(d(45)) - math.cos(d(60)))
nn = sum(math.sin(d(a)) ** 2 + math.cos(d(a)) ** 2 for a in (30, 45, 60))
assert abs(g + 0.25) < 1e-12 and abs(nn - 3) < 1e-12 and abs(math.tan(d(30)) - S3 / 3) < 1e-12

ANS = {1: 1, 2: 2, 3: 5, 4: 3, 5: 4, 6: 3, 7: 2, 8: 1, 9: 4, 10: 4,
       11: 5, 12: 4, 13: 1, 14: 3, 15: 2, 16: 5, 17: 2, 18: 1}
for n, (a, _, _) in chk.items():
    assert ANS[n] == a
CIRC = "①②③④⑤"
for p in range(1, 5):
    f = os.path.join(T, "ocr", f"p{p}_merged.json")
    data = json.load(open(f, encoding="utf-8"))
    for q in data["questions"]:
        q["answer"] = CIRC[ANS[q["number"]] - 1]
        q.pop("solution", None)
    with open(f, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
print("ok")
