"""프롬프트/런 출처 서명 — 런 결과를 어떤 프롬프트·모델·러너로 냈는지 태깅.

`core.ocr_engine`(anthropic) 를 import 하므로 **사용자 PC 에서 실행**(scorer 코어와 분리).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# 러너 식별자 — recognize_crop 의 후처리(전사 보강·표 복구 등) 동작 버전. 프롬프트가 같아도
# 러너/스키마가 바뀌면 출력이 달라지므로 서명에 포함해 sig 충돌을 막는다. 후처리 로직을 크게
# 바꾸면 이 값을 올린다.
RUNNER = "recognize_crop_raw_v1"
SCHEMA_VERSION = 1


def _payload() -> dict:
    from core.ocr_engine import EXAM_OCR_PROMPT
    from utils.config import CLAUDE_MODEL
    return {
        "prompt": EXAM_OCR_PROMPT,
        "model": CLAUDE_MODEL,
        "schema_version": SCHEMA_VERSION,
        "runner": RUNNER,
    }


def prompt_sha256() -> str:
    """전체 payload(프롬프트+모델+스키마+러너)의 sha256(hex)."""
    blob = json.dumps(_payload(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def prompt_signature() -> str:
    """짧은 서명(12hex) — eval 캐시 디렉터리·런 태깅 키."""
    return prompt_sha256()[:12]


def metadata() -> dict:
    """eval 캐시 metadata.json 본문."""
    from utils.config import CLAUDE_MODEL
    return {
        "prompt_sig": prompt_signature(),
        "prompt_sha256": prompt_sha256(),
        "model": CLAUDE_MODEL,
        "runner": RUNNER,
        "schema_version": SCHEMA_VERSION,
    }


if __name__ == "__main__":
    print("prompt_signature:", prompt_signature())
    print(json.dumps(metadata(), ensure_ascii=False, indent=2))
