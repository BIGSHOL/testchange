"""도형 엔진(`core` 꾸러미)이 **어디 있는가**. 한 곳에서만 정한다.

종전에는 이 결정이 `render_spec.py` **안에만** 있었다. 그래서 엔진을 직접 import 하는
길(판정기·시험이 `elementary` 를 바로 부르는 경우)에서는 `core` 가 sys.path 에 없고,
`from core… import` 가 `ModuleNotFoundError` 로 죽었다 — 그리고 그 죽음은 **그 경로로
불렀을 때만** 난다. 실측으로 그렇게 50개 시험이 한꺼번에 빨개졌다(2026-08-28).

⚠️ 우선순위: `FIGURE_ENGINE_PATH`(있으면) → **저장소 안 vendor** → 원본 드라이브.
   원본을 마지막에 두는 이유는 «저장소가 정본»이 되게 하려는 것이다.
"""

from __future__ import annotations

import os
import sys

# 시험지 한글화 저장소에서는 엔진(`core`)이 저장소 뿌리에 있다(todays-math 는 vendor/figure-engine).
VENDOR_ENGINE_PATH = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_ENGINE_PATH = r"F:\시험지변환기"


def engine_root() -> str:
    """엔진 뿌리. 못 찾으면 빈 문자열.

    ⚠️ 「그 폴더가 있나」가 아니라 **「그 안에 `core` 가 있나」**를 묻는다. 폴더만 보면
       빈 껍데기를 골라 놓고 뒤늦게 `No module named core` 로 죽는다 — 그 에러는
       진짜 결함에 섞여 자리 목록을 통째로 거짓으로 만든다(2026-08-24 실측).
    """
    return next(
        (
            p
            for p in (
                os.environ.get("FIGURE_ENGINE_PATH"),
                VENDOR_ENGINE_PATH,
                DEFAULT_ENGINE_PATH,
            )
            if p and os.path.isdir(os.path.join(p, "core"))
        ),
        "",
    )


def ensure_on_path() -> str:
    """엔진 뿌리를 `sys.path` 에 올리고 그 경로를 돌려준다. 이미 있으면 그대로."""
    root = engine_root()
    if root and root not in sys.path:
        sys.path.insert(0, root)
    return root
