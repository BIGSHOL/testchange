---
name: verify-ocr-parser-sync
description: OCR 엔진↔콘텐츠 파서 동기화 검증. OCR 프롬프트 또는 파서 로직 수정 후 사용.
---

# OCR 엔진↔콘텐츠 파서 동기화 검증

## Purpose

OCR 엔진(`core/ocr_engine.py`)의 출력과 콘텐츠 파서(`core/content_parser.py`)의 입력 기대가 일치하는지 검증합니다:

1. **JSON 구조 동기화** — OCR 프롬프트가 요구하는 JSON 필드와 파서가 읽는 필드가 일치하는지
2. **ContentType 매핑 동기화** — OCR 응답의 type 문자열과 파서의 ContentType enum 매핑이 일치하는지
3. **수식 분리 regex 유효성** — `_INLINE_LATEX_RE`, `_MATH_EXPR_RE` 패턴이 정상 컴파일되고 의도대로 동작하는지
4. **품질 검사 임계값 일관성** — `utils/config.py`의 값이 `core/quality_checker.py`에서 올바르게 참조되는지

## When to Run

- `core/ocr_engine.py`의 `EXAM_OCR_PROMPT`를 수정한 후
- `core/content_parser.py`의 파싱 로직이나 regex를 변경한 후
- `core/quality_checker.py`의 품질 검사 로직을 수정한 후
- `utils/config.py`의 임계값을 변경한 후
- `models/exam_document.py`의 ContentType enum을 수정한 후

## Related Files

| File | Purpose |
|------|---------|
| `core/ocr_engine.py` | Codex Vision OCR 엔진 (프롬프트, JSON 파싱) |
| `core/content_parser.py` | OCR 응답 → ExamDocument 변환 파서 |
| `core/quality_checker.py` | 이미지 품질 검사기 |
| `utils/config.py` | 중앙 설정값 (임계값, 모델명) |
| `models/exam_document.py` | 데이터 모델 (ContentType enum) |

## Workflow

### Step 1: ContentType 매핑 동기화 검증

**파일:** `models/exam_document.py`, `core/content_parser.py`

`ContentType` enum의 값과 파서의 type→ContentType 매핑이 일치하는지 확인합니다.

**검사 1a:** ContentType enum 값 확인

```bash
grep -A 10 "class ContentType" models/exam_document.py
```

**검사 1b:** 파서의 type 매핑 확인

```bash
grep -A 10 '"text": ContentType\|"equation": ContentType\|"equation_block": ContentType\|"image": ContentType' core/content_parser.py
```

**PASS:** 파서가 ContentType의 모든 enum 값에 대한 매핑을 포함 (text, equation, equation_block, image)
**FAIL:** ContentType에 새 값이 추가되었지만 파서 매핑에 없음 — 해당 타입의 블록이 무시됨

**위반 시 수정:** `content_parser.py`의 type_map 딕셔너리에 누락된 ContentType 매핑을 추가합니다.

### Step 2: OCR JSON 필드 ↔ 파서 필드 동기화 검증

**파일:** `core/ocr_engine.py`, `core/content_parser.py`

OCR 프롬프트가 지정하는 JSON 구조의 핵심 필드를 파서가 올바르게 읽는지 확인합니다.

**검사 2a:** 파서가 `header` 필드를 읽는지 확인

```bash
grep -n 'header' core/content_parser.py
```

**검사 2b:** 파서가 `questions`, `number`, `score`, `contents`, `choices`, `sub_questions` 필드를 읽는지 확인

```bash
grep -n '"questions"\|"number"\|"score"\|"contents"\|"choices"\|"sub_questions"\|"type"\|"value"' core/content_parser.py
```

**PASS:** OCR 프롬프트의 모든 핵심 필드 (header, questions, number, score, contents, choices, sub_questions, type, value)를 파서가 참조
**FAIL:** 파서가 참조하지 않는 필드가 있음 — OCR 결과의 일부 데이터가 무시됨

### Step 3: 수식 분리 Regex 유효성 검증

**파일:** `core/content_parser.py`

**검사 3a:** `_INLINE_LATEX_RE` 패턴이 정상 컴파일되는지 확인

```bash
python -c "
import re, sys
sys.path.insert(0, '.')
from core.content_parser import _INLINE_LATEX_RE
assert isinstance(_INLINE_LATEX_RE, re.Pattern), 'Not a compiled pattern'
# 기본 매칭 테스트
test = 'hello \$x^2\$ world'
matches = _INLINE_LATEX_RE.findall(test)
print(f'PASS: _INLINE_LATEX_RE compiled, test matches: {matches}')
"
```

**PASS:** 패턴 컴파일 성공, `$x^2$` 형태 매칭
**FAIL:** 컴파일 실패 또는 기본 패턴 매칭 실패

**검사 3b:** `_MATH_EXPR_RE` 패턴이 정상 컴파일되는지 확인

```bash
python -c "
import re, sys
sys.path.insert(0, '.')
from core.content_parser import _MATH_EXPR_RE
assert isinstance(_MATH_EXPR_RE, re.Pattern), 'Not a compiled pattern'
# 기본 매칭 테스트
test = 'a > 0'
match = _MATH_EXPR_RE.search(test)
print(f'PASS: _MATH_EXPR_RE compiled, test match: {match.group() if match else None}')
"
```

**PASS:** 패턴 컴파일 성공
**FAIL:** 컴파일 실패

### Step 4: 품질 검사 임계값 참조 일관성 검증

**파일:** `utils/config.py`, `core/quality_checker.py`

`config.py`에 정의된 임계값이 `quality_checker.py`에서 올바르게 import/사용되는지 확인합니다.

**검사 4a:** config.py에서 정의된 QC 관련 변수 확인

```bash
grep -n "^QC_" utils/config.py
```

**검사 4b:** quality_checker.py에서 config의 QC 변수를 import하는지 확인

```bash
grep -n "from utils.config import\|QC_" core/quality_checker.py
```

**PASS:** config.py의 모든 QC 변수 (QC_MIN_WIDTH, QC_MIN_HEIGHT, QC_BLUR_THRESHOLD, QC_BLANK_THRESHOLD, QC_CONTRAST_THRESHOLD, QC_PASS_SCORE)가 quality_checker.py에서 import 및 사용됨
**FAIL:** config에 정의되었지만 quality_checker에서 참조하지 않는 변수가 있음 — 하드코딩된 값 위험

**위반 시 수정:** 하드코딩된 임계값을 config의 변수 참조로 교체합니다.

### Step 5: OCR 모델 설정 참조 검증

**파일:** `utils/config.py`, `core/ocr_engine.py`

OCR 엔진이 config에서 모델 설정을 올바르게 가져오는지 확인합니다.

**검사 5a:** ocr_engine.py가 CLAUDE_MODEL과 CLAUDE_MAX_TOKENS를 config에서 import하는지 확인

```bash
grep -n "CLAUDE_MODEL\|CLAUDE_MAX_TOKENS\|from utils.config" core/ocr_engine.py
```

**PASS:** config의 `CLAUDE_MODEL`과 `CLAUDE_MAX_TOKENS`를 import하여 사용
**FAIL:** 하드코딩된 모델명이나 토큰 수 사용 — config 변경 시 반영되지 않음

**검사 5b:** config.py의 CLAUDE_MODEL 기본값이 유효한 Codex 모델인지 확인

```bash
grep "CLAUDE_MODEL" utils/config.py
```

**PASS:** 기본값이 `Codex-haiku-4-5-20251001` 또는 유효한 Codex 모델 ID
**FAIL:** 존재하지 않는 모델 ID — API 호출 실패

### Step 6: 데이터 모델 import 일관성 검증

**파일:** `core/content_parser.py`, `models/exam_document.py`

파서가 데이터 모델의 핵심 클래스를 올바르게 import하는지 확인합니다.

```bash
grep -n "from models\|import.*ContentBlock\|import.*Choice\|import.*Question\|import.*ExamPage\|import.*ExamDocument\|import.*ContentType" core/content_parser.py
```

**PASS:** ContentBlock, Choice, Question, ExamPage, ExamDocument, ContentType 모두 import됨
**FAIL:** 누락된 import — RuntimeError 발생

## Output Format

```markdown
## verify-ocr-parser-sync 검증 결과

| # | 검사 항목 | 상태 | 상세 |
|---|----------|------|------|
| 1 | ContentType 매핑 동기화 | PASS/FAIL | ... |
| 2 | OCR JSON↔파서 필드 일치 | PASS/FAIL | ... |
| 3a | _INLINE_LATEX_RE 유효성 | PASS/FAIL | ... |
| 3b | _MATH_EXPR_RE 유효성 | PASS/FAIL | ... |
| 4 | QC 임계값 참조 일관성 | PASS/FAIL | ... |
| 5 | OCR 모델 설정 참조 | PASS/FAIL | ... |
| 6 | 데이터 모델 import 일관성 | PASS/FAIL | ... |
```

## Exceptions

다음은 **위반이 아닙니다**:

1. **EXAM_OCR_PROMPT 내의 예시 JSON** — OCR 프롬프트에 포함된 예시 JSON은 문서용이며, 파서 코드와 구조적으로 약간 다를 수 있음 (예시는 설명용)
2. **환경변수 오버라이드** — `GEMINI_API_KEY` 등 환경변수 오버라이드는 정상 동작(config.py). config.py의 기본값만 검증 대상. (`.env` 파일은 2026-06-10 제거 — 코드는 config.json 만 읽음)
3. **quality_checker의 추가 내부 상수** — `quality_checker.py`가 config 외에 내부적으로 사용하는 상수 (예: Laplacian 커널 값 `[0,1,0],[1,-4,1],[0,1,0]`)는 검증 대상이 아님