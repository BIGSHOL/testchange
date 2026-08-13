# -*- coding: utf-8 -*-
"""처리 범위 한 곳 정의 — 큐·렌더·업로드가 같은 기준을 쓴다

범위가 스크립트마다 흩어져 있으면 판독은 했는데 큐에서 빠지거나, 큐엔 있는데
업로드에서 빠지는 어긋남이 생긴다. 여기 하나만 고치면 전부 따라온다.

사용자 지시(2026-08-13): **2024~2026년 × 중1~3 + 고1**.
- 2026 은 아직 카탈로그에 없지만 범위에 넣어 둔다(생기면 자동 편입).
- 범위 밖 이미 판독한 편은 **지우지 않는다** — 데이터는 보존하고 큐에서만 뺀다.
"""
from __future__ import annotations

YEAR_MIN, YEAR_MAX = 2024, 2026

# exams 테이블 별칭이 e 인 곳과 없는 곳이 섞여 있어 별칭을 인자로 받는다
def sql(alias: str = "") -> str:
    p = f"{alias}." if alias else ""
    return (f"({p}year BETWEEN {YEAR_MIN} AND {YEAR_MAX}"
            f" AND ({p}level='중' OR ({p}level='고' AND {p}grade=1)))")


LABEL = f"{YEAR_MIN}~{YEAR_MAX} × 중1~3 + 고1"
