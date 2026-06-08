"""OCR 골든셋 플라이휠 — 채점·시딩·동기화 도구.

계층:
  - normalize.py / metrics.py : **stdlib only** scorer 코어. anthropic·core·pytest 불필요.
    어디서나(CI·다른 PC) 돈다. 이 둘은 절대 `core.*`/`anthropic` 를 import 하지 않는다.
  - prompt_version / golden_record / score_ocr / supabase_sync : API/런 스크립트.
    `core`/anthropic 를 import 하므로 **사용자 PC(키·한글·PDF 있음)** 에서 실행.

상세 설계: docs/HANDOFF.md, repo 루트 CLAUDE.md.
"""
