# -*- coding: utf-8 -*-
"""단원 분류표 어휘 사전 — 정답·해설 메타(소단원/중단원) 생성의 표준 어휘 공급.

세션(Claude Code)이 메타를 채울 때는 분류표 PDF(고등 소단원·중등 중단원)를 직접 읽고
그 어휘 안에서 골랐다. 배포 exe 도 **같은 어휘를 보게** 하려고 PDF 를 JSON 으로 구워
번들한다(`scripts/build_topic_vocab.py` → `data/topic_vocab.json`, 사용자 2026-08-07).

레벨 규약(CLAUDE.md 2026-07-24, 사용자 2026-10-26 "실제 표에 따라서"):
  · **고등 = 소단원**(분류표 ``ⅰ)`` 레벨 — 표가 ``1. → ① → ⅰ)`` 세 단계) — 폼 라벨 ``[소단원]``
  · **중등 = 중단원**(분류표 ``①`` 레벨 — 표가 ``1. → ①`` 두 단계)       — 폼 라벨 ``[중단원]``

표는 두 벌이다. 현행 = 대수회 ``큰분류ver.261020``(고등 22개정 7과목 207개, 중등 중1·중2
22개정 + 중3 15개정 64개), 15개정 = 옛 표(고등 수학1·수학2·확률과 통계·미적분·기하 145개,
중등 51개). ``vocabulary(..., year=)`` 가 시험 연도·학년으로 고른다(연도를 모르면 현행).

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


# 파일명/폼에서 오는 과목 표기 → (현행 22개정 표 키, 15개정 표 키). 한쪽 표에만 있는 과목은 None.
# 현행 표 = 대수회 큰분류ver.261020(2026-10-20), 15개정 표 = 고등 ver.250604 의 선택과목.
_SUBJ_KEYS = {
    "공통수학1": ("공통 수학1", None), "공수1": ("공통 수학1", None),
    "수학상": ("공통 수학1", None), "수상": ("공통 수학1", None),
    "공통수학2": ("공통수학2", None), "공수2": ("공통수학2", None),
    "수학하": ("공통수학2", None), "수하": ("공통수학2", None),
    "대수": ("대수", None), "수학1": (None, "수학1"), "수1": (None, "수학1"),
    "미적분1": ("미적분1", None), "미적분i": ("미적분1", None), "미적분ⅰ": ("미적분1", None),
    "수학2": (None, "수학2"), "수2": (None, "수학2"),
    "미적분2": ("미적분2", None), "미적분ii": ("미적분2", None), "미적분ⅱ": ("미적분2", None),
    "미적분": (None, "미적분"), "미적": (None, "미적분"),
    "확률과통계": ("확률과 통계", "확률과 통계"), "확통": ("확률과 통계", "확률과 통계"),
    "기하": ("기하", "기하"),
}


def level_for(grade: str) -> str:
    """학년 표기 → 메타 레벨(``소단원``=고등 / ``중단원``=중등)."""
    return _LEVEL_MID if "중" in str(grade or "") else _LEVEL_HIGH


def _year(year) -> int | None:
    m = re.search(r"\d{2,4}", str(year or ""))
    if not m:
        return None
    y = int(m.group(0))
    return y + 2000 if y < 100 else y


def is_legacy_curriculum(grade: str, year) -> bool:
    """22개정 이전(15개정) 교육과정 시험인가 — 연도·학년을 알 때만 판정한다.

    22개정 적용: 중1·고1 2025년, 중2·고2 2026년, 중3·고3 2027년부터.
    연도나 학년을 모르면 현행 표(False)를 쓴다.
    """
    y = _year(year)
    m = re.search(r"([123])", str(grade or ""))
    if y is None or not m:
        return False
    return y < 2024 + int(m.group(1))


def vocabulary(grade: str, subject: str, year=None) -> list[str]:
    """학년·과목(·연도)에 해당하는 표준 단원명 목록(없으면 빈 리스트).

    고등은 과목별 소단원, 중등은 학년별 중단원. ``year`` 가 22개정 이전 시험이면
    15개정 표(``*_15개정``)를 먼저 본다. 과목을 못 찾으면 **그 학교급 전체**를
    합쳐 반환한다(없는 것보다 낫다 — 모델이 후보 중에서 고르게).
    """
    data = _load()
    if not data:
        return []
    g = str(grade or "")
    legacy = is_legacy_curriculum(g, year)
    if "중" in g:
        tables = [data.get("중등_15개정", {}), data.get("중등", {})]
        if not legacy:
            tables.reverse()
        m = re.search(r"([123])", g)
        if m:
            for tb in tables:
                if f"중등수학 {m.group(1)}" in tb:
                    return list(tb[f"중등수학 {m.group(1)}"])
        return [t for v in data.get("중등", {}).values() for t in v]

    cur, old = data.get("고등", {}), data.get("고등_15개정", {})
    sub_n = _norm(subject)
    cur_key, old_key = _SUBJ_KEYS.get(sub_n, (None, None))
    picks = [(old, old_key), (cur, cur_key)] if legacy else [(cur, cur_key), (old, old_key)]
    for tb, key in picks:
        if key and key in tb:
            return list(tb[key])
    for tb in ((old, cur) if legacy else (cur, old)):
        for key in tb:                     # 표 키와 같은 이름(공백 차이만)
            if _norm(key) == sub_n:
                return list(tb[key])
        for key in tb:                     # 부분 일치(예: "확률과통계 " 변형)
            if sub_n and (sub_n in _norm(key) or _norm(key) in sub_n):
                return list(tb[key])
    return [t for v in cur.values() for t in v]


def prompt_block(grade: str, subject: str, max_items: int = 260, year=None) -> str:
    """프롬프트에 넣을 어휘 안내문(없으면 빈 문자열)."""
    items = vocabulary(grade, subject, year)
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
