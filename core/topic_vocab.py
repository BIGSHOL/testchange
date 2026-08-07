# -*- coding: utf-8 -*-
"""단원 분류표 어휘 사전 — 정답·해설 메타(소단원/중단원) 생성의 표준 어휘 공급.

세션(Claude Code)이 메타를 채울 때는 분류표 PDF(고등 소단원·중등 중단원)를 직접 읽고
그 어휘 안에서 골랐다. 배포 exe 도 **같은 어휘를 보게** 하려고 PDF 를 JSON 으로 구워
번들한다(`scripts/build_topic_vocab.py` → `data/topic_vocab.json`, 사용자 2026-08-07).

레벨 규약(CLAUDE.md 2026-07-24):
  · **고등 = 소단원**(분류표 ``ⅰ)`` 레벨, 215개/7과목) — 폼 라벨 ``[소단원]``
  · **중등 = 중단원**(분류표 ``①`` 레벨, 51개/3학년)  — 폼 라벨 ``[중단원]``

⚠️ 분류표는 **정식 명칭**이고 학교/작성자별 축약 표기가 따로 있다(경원고 기하는
``타원의 방정식`` 대신 ``타원``). 분류표 어휘를 **후보로 제시**하되 강제하지 않는 이유다.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_LEVEL_HIGH = "소단원"
_LEVEL_MID = "중단원"


def _data_dir() -> Path:
    """번들(exe) / 소스 양쪽에서 data 디렉터리 경로."""
    if getattr(sys, "frozen", False):        # PyInstaller onedir
        return Path(sys._MEIPASS) / "data"   # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent / "data"


@lru_cache(maxsize=1)
def _load() -> dict:
    p = _data_dir() / "topic_vocab.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001 — 없으면 어휘 없이 동작(기존 자유 생성)
        logger.warning("단원 분류 어휘 로드 실패(%s): %s", p, e)
        return {}


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", str(s or "")).lower()


# 파일명/폼에서 오는 과목 표기 → 분류표 과목 키(정규화 비교로 못 잡는 것만)
_SUBJ_ALIAS = {
    "공통수학1": "공통 수학1", "공수1": "공통 수학1", "수학상": "공통 수학1", "수상": "공통 수학1",
    "공통수학2": "공통수학2", "공수2": "공통수학2", "수학하": "공통수학2", "수하": "공통수학2",
    "대수": "수학1", "수1": "수학1",
    "미적분i": "수학2", "수2": "수학2",
    "확통": "확률과 통계", "확률과통계": "확률과 통계",
    "미적분ii": "미적분", "미적": "미적분",
}


def level_for(grade: str) -> str:
    """학년 표기 → 메타 레벨(``소단원``=고등 / ``중단원``=중등)."""
    return _LEVEL_MID if "중" in str(grade or "") else _LEVEL_HIGH


def vocabulary(grade: str, subject: str) -> list[str]:
    """학년·과목에 해당하는 표준 단원명 목록(없으면 빈 리스트).

    고등은 과목별 소단원, 중등은 학년별 중단원. 과목을 못 찾으면 **그 학교급 전체**를
    합쳐 반환한다(없는 것보다 낫다 — 모델이 후보 중에서 고르게).
    """
    data = _load()
    if not data:
        return []
    g = str(grade or "")
    if "중" in g:
        m = re.search(r"([123])", g)
        if m:
            key = f"중등수학 {m.group(1)}"
            if key in data.get("중등", {}):
                return list(data["중등"][key])
        return [t for v in data.get("중등", {}).values() for t in v]

    highs = data.get("고등", {})
    sub_n = _norm(subject)
    alias = _SUBJ_ALIAS.get(sub_n)
    for key in highs:
        if _norm(key) == sub_n or (alias and _norm(key) == _norm(alias)):
            return list(highs[key])
    # 부분 일치(예: "확률과통계 " 변형)
    for key in highs:
        if sub_n and (sub_n in _norm(key) or _norm(key) in sub_n):
            return list(highs[key])
    return [t for v in highs.values() for t in v]


def prompt_block(grade: str, subject: str, max_items: int = 260) -> str:
    """프롬프트에 넣을 어휘 안내문(없으면 빈 문자열)."""
    items = vocabulary(grade, subject)
    if not items:
        return ""
    lvl = level_for(grade)
    shown = items[:max_items]
    return (
        f"\n[{lvl} 표준 어휘 — 아래 목록에서 **그대로** 하나를 고르세요]\n"
        f"· 목록에 딱 맞는 항목이 없을 때만 가장 가까운 표준 단원명을 직접 씁니다.\n"
        f"· 목록 항목을 임의로 줄이거나 늘이지 마세요(예: 목록이 \"포물선의 방정식\"이면\n"
        f"  \"포물선\"으로 줄이지 말 것).\n"
        + " / ".join(shown) + "\n"
    )
