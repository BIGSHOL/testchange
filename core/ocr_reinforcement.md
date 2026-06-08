<!--
OCR 보강 블록 — 승인된 일반 규칙만 여기 둔다(base 프롬프트 EXAM_OCR_PROMPT 는 불변).

작동:
  - 런타임에 core/ocr_engine.active_prompt() 가 EXAM_OCR_PROMPT 뒤에 이 파일의 내용을
    덧붙인다. 이 머리말(HTML 주석)과 빈 줄만 있으면 no-op(아무것도 안 붙음).
  - scripts/ocr_eval/prompt_version._payload() 가 이 파일 내용을 서명에 포함 → 보강이 바뀌면
    prompt_signature 가 바뀌어 eval 캐시가 분리되고 A/B 가 성립한다.

규칙:
  1. 인스턴스 암기 금지 — '원본 그대로 옮겨라' 류의 일반 규칙으로만 군집해 적는다.
  2. 자동 반영 금지 — scripts/ocr_eval/suggest_reinforcement.py 의 제안을 Claude Code 가
     정련하고 사람 승인 후에만 여기 추가한다.
  3. 분량 상한을 지킨다(프롬프트는 이미 길다). 골든 A/B(개선 + 무회귀)에서만 채택.

승인된 보강 블록은 이 주석 블록 바깥(아래)에 형식 예처럼 추가한다:

  ## (카테고리) 보강 — YYYY-MM-DD
  - 일반 규칙 1
  - 일반 규칙 2
-->
