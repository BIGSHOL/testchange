# -*- coding: utf-8 -*-
"""단원 분류 어휘(메타란 [소단원]/[중단원]) — 현행 표·15개정 표 선택과 항목 온전성 (stdlib·API 0원).

⭐ 왜: 대수회 분류표가 2026-10-20 판(큰분류ver.261020)으로 바뀌어 중1·중2 가 22개정 어휘가
됐다(``문자의 사용과 식의 계산`` → ``문자의 사용``·``일차식과 그 계산``). 옛 어휘로 메타를
채우면 표에 없는 단원명이 나간다(성광중 중1 26-1-중간에서 발견). 반대로 2025년 중2 처럼
22개정 이전 시험은 옛 표가 맞다 — 연도로 고른다.

또 종전 추출은 표의 칸 안 줄바꿈에서 항목을 잘랐다(``‘모든’이나 ‘어떤’을 포함한`` 등 9개).
항목이 조사로 끝나거나 그림 글자(사용자 영역 문자)가 남으면 실패.

실행: .venv\\Scripts\\python.exe tests/test_topic_vocab.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

for _s in (sys.stdout, sys.stderr):
    try:                        # cp949 콘솔에서 비ASCII print 가 죽는 것 방지
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

from core.topic_vocab import is_legacy_curriculum, level_for, vocabulary  # noqa: E402

FAILED: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  OK   {label}")
    else:
        print(f"  FAIL {label} {detail}")
        FAILED.append(label)


print("A. 레벨 — 중등 [중단원] / 고등 [소단원]")
check("중1 → 중단원", level_for("중1") == "중단원")
check("고2 → 소단원", level_for("고2") == "소단원")

print("B. 현행 표(큰분류ver.261020)")
m1 = vocabulary("중1", "수학")
check("중1 22개정: 문자의 사용·일차식과 그 계산", {"문자의 사용", "일차식과 그 계산"} <= set(m1), m1)
check("중1 옛 단원명 없음", "문자의 사용과 식의 계산" not in m1)
check("중1 표 순서(소인수분해 먼저)", m1[:2] == ["소인수분해", "최대공약수와 최소공배수"], m1[:3])
check("중2 22개정", "평행선 사이의 선분의 길이의 비" in vocabulary("중2", "수학", 2026))
check("고2 대수 = 현행 대수", "∑의 뜻과 그 성질" in vocabulary("고2", "대수"))
check("고2 미적분1", "평균값 정리" in vocabulary("고2", "미적분1"))
check("미적분2 수식 복원", "무리수 e와 자연로그" in vocabulary("고3", "미적분2"))
check("공통수학1 수식 복원", "방정식 x³=1의 허근" in vocabulary("고1", "공수1"))
check("고2 기하 2026 = 22개정", "삼수선 정리" in vocabulary("고2", "기하", 2026))

print("C. 15개정 표 — 22개정 이전 시험")
check("2025 중2 = 15개정", is_legacy_curriculum("중2", 2025) and not is_legacy_curriculum("중2", 2026))
check("2026 고3 = 15개정", is_legacy_curriculum("고3", "2026") and not is_legacy_curriculum("고2", "26"))
check("연도 모르면 현행", not is_legacy_curriculum("중2", None))
check("2025 중2 어휘", "평행선과 선분의 길이의 비" in vocabulary("중2", "수학", 2025))
check("2026 고3 기하 어휘", "삼수선의 정리" in vocabulary("고3", "기하", 2026))
check("수1·수2·미적분 = 15개정 과목", "시그마의 뜻과 그 성질" in vocabulary("고2", "수1")
      and "넓이" in vocabulary("고2", "수2") and "이계도함수" in vocabulary("고3", "미적분"))

print("D. 항목 온전성(잘림·그림 글자·오타)")
data = json.loads((ROOT / "data" / "topic_vocab.json").read_text(encoding="utf-8"))
allv = [(tb, k, x) for tb in ("고등", "중등", "고등_15개정", "중등_15개정")
        for k, v in data.get(tb, {}).items() for x in v]
cut = [x for _, _, x in allv if re.search(r"(과|와|을|를|에|원의|함수의|포함한)$", x)]
check("조사로 끝나는(잘린) 항목 없음", not cut, cut)
names = {x for *_, x in allv}
whole = ["‘모든’이나 ‘어떤’을 포함한 명제", "두 원의 교점을 지나는 직선과 원의 방정식",
         "이산확률변수의 기댓값과 표준편차", "삼각함수가 포함된 방정식과 부등식",
         "삼각함수를 포함한 식의 최대 최소", "매개변수로 나타낸 함수의 미분법",
         "정적분의 치환적분법과 부분적분법", "속도와 거리"]
check("예전에 잘렸던 항목 온전", all(w in names for w in whole), [w for w in whole if w not in names])
check("사용자 영역 문자 없음", not [x for *_, x in allv if re.search(r"[-]", x)])
check("분류표 오타 교정", not [x for *_, x in allv if "거듭제곰" in x or "일차할수" in x])
cnt = {tb: sum(len(v) for v in data.get(tb, {}).values()) for tb in ("고등", "중등")}
check("빌드 게이트 개수(고등≥100·중등≥30)", cnt["고등"] >= 100 and cnt["중등"] >= 30, cnt)

print()
if FAILED:
    print(f"FAILED {len(FAILED)}: {FAILED}")
    sys.exit(1)
print("ALL OK")
