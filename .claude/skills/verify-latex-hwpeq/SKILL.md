---
name: verify-latex-hwpeq
description: LaTeX→HWP 수식 변환 매핑 무결성 검증. 수식 변환 로직 수정 후 사용.
---

# LaTeX→HWP 수식 변환 검증

## Purpose

LaTeX 수식을 HWP 수식 스크립트로 변환하는 `core/latex_to_hwpeq.py` 모듈의 무결성을 검증합니다:

1. **매핑 딕셔너리 무결성** — GREEK_MAP, SYMBOL_MAP, FUNC_MAP, ACCENT_MAP 항목이 누락/중복 없이 유지되는지
2. **키워드 리스트 동기화** — `hwpx_writer.py`의 `_SYMBOL_KEYWORDS`, `_LARGE_OP_KEYWORDS`, `_STRUCT_KEYWORDS`가 변환기의 매핑과 일치하는지
3. **변환 패턴 유효성** — 정규식 패턴이 올바른 구문이고 의도된 매칭을 하는지
4. **처리 순서 보존** — `_convert_expr()` 메서드의 변환 단계 순서가 올바르게 유지되는지

## When to Run

- `core/latex_to_hwpeq.py`에 매핑 항목을 추가/수정/삭제한 후
- `core/hwpx_writer.py`의 키워드 리스트를 변경한 후
- LaTeX 수식 변환 관련 버그 수정 후
- 새로운 LaTeX 명령어 지원을 추가한 후

## Related Files

| File | Purpose |
|------|---------|
| `core/latex_to_hwpeq.py` | LaTeX→HWP 수식 스크립트 변환기 (주 검증 대상) |
| `core/hwpx_writer.py` | HWPX 문서 생성 (키워드 리스트 참조) |

## Workflow

### Step 1: 매핑 딕셔너리 무결성 검증

**파일:** `core/latex_to_hwpeq.py`

**검사 1a:** 4개 매핑 딕셔너리가 모두 존재하는지 확인합니다.

```bash
grep -c "GREEK_MAP\|SYMBOL_MAP\|FUNC_MAP\|ACCENT_MAP" core/latex_to_hwpeq.py
```

**PASS:** 4개 딕셔너리 모두 정의되어 있음
**FAIL:** 매핑 딕셔너리가 누락됨

**검사 1b:** 각 매핑의 키가 `\` 백슬래시로 시작하는지 확인합니다 (LaTeX 명령어 규칙).

```bash
grep -n 'r"\\' core/latex_to_hwpeq.py | head -20
```

**PASS:** 모든 키가 `r"\...` 형태
**FAIL:** `\` 없이 시작하는 키가 존재

**검사 1c:** 매핑 값(HWP 스크립트)에 빈 문자열이 없는지 확인합니다.

```bash
grep -n '""' core/latex_to_hwpeq.py
```

**PASS:** 빈 값 매핑 없음 (빈 문자열이 딕셔너리 값 위치에 나타나지 않음)
**FAIL:** 빈 문자열 매핑 발견 — 변환 시 해당 심볼이 삭제됨

### Step 2: 키워드 리스트 동기화 검증

**파일:** `core/hwpx_writer.py`, `core/latex_to_hwpeq.py`

`hwpx_writer.py`의 `_SYMBOL_KEYWORDS` 리스트는 수식 크기 측정 시 키워드를 제외하기 위해 사용됩니다. 이 리스트가 `latex_to_hwpeq.py`의 SYMBOL_MAP/FUNC_MAP 값과 동기화되어야 합니다.

**검사 2a:** `_SYMBOL_KEYWORDS` 리스트가 존재하고 비어있지 않은지 확인합니다.

```bash
grep -A 30 "_SYMBOL_KEYWORDS = \[" core/hwpx_writer.py
```

**PASS:** 리스트가 존재하고 항목이 있음
**FAIL:** 리스트가 없거나 비어있음

**검사 2b:** `_LARGE_OP_KEYWORDS` 리스트가 6개 연산자를 포함하는지 확인합니다.

```bash
grep -A 2 "_LARGE_OP_KEYWORDS" core/hwpx_writer.py
```

**PASS:** `["SUM", "PROD", "OINT", "DINT", "TINT", "INT"]` 6개 항목 존재
**FAIL:** 항목 수가 다르거나 누락됨

**검사 2c:** `latex_to_hwpeq.py`의 SYMBOL_MAP에서 대문자 값(예: "TIMES", "CDOT")이 `hwpx_writer.py`의 `_SYMBOL_KEYWORDS`에 포함되어 있는지 확인합니다.

`core/latex_to_hwpeq.py`에서 SYMBOL_MAP의 대문자 값을 추출하고, `core/hwpx_writer.py`의 `_SYMBOL_KEYWORDS`와 비교합니다. Read 도구로 두 파일을 읽고 수동 비교합니다.

**PASS:** SYMBOL_MAP의 모든 대문자 값이 `_SYMBOL_KEYWORDS`에 포함
**FAIL:** `_SYMBOL_KEYWORDS`에 없는 대문자 매핑 값 발견 — 해당 키워드를 `_SYMBOL_KEYWORDS`에 추가 필요

### Step 3: 변환 처리 순서 검증

**파일:** `core/latex_to_hwpeq.py`

`_convert_expr()` 메서드 내의 변환 단계 순서가 올바른지 확인합니다. 순서가 중요한 이유: 환경 래퍼 제거 → 텍스트 처리 → 분수 → 루트 → 대형연산자 → 괄호 → 악센트 → 그리스문자 → 심볼 → 함수 → 위첨자/아래첨자.

```bash
grep -n "def _convert_expr\|_env_pattern\|_text_pattern\|_mathrm_pattern\|_binom_pattern\|_frac_pattern\|_sqrt\|_big_op\|_leftright\|_accent\|GREEK_MAP\|SYMBOL_MAP\|FUNC_MAP\|_superscript\|_subscript" core/latex_to_hwpeq.py
```

**PASS:** 함수 내에서 다음 순서 유지: (1) env → (2) text/mathrm/mathbf → (3) binom → (4) frac → (5) sqrt → (6) big_op → (7) leftright → (8) accent → (9) Greek → (10) Symbol → (11) Func → (12) super/subscript
**FAIL:** 순서가 변경되었음 — 부분 매칭이나 잘못된 치환 위험

### Step 4: 정규식 패턴 유효성 검증

**파일:** `core/latex_to_hwpeq.py`

컴파일된 정규식 패턴이 올바른 구문인지 확인합니다.

```bash
python -c "
import re, sys
sys.path.insert(0, '.')
from core.latex_to_hwpeq import LaTeXToHWPConverter
c = LaTeXToHWPConverter()
patterns = ['_frac_pattern', '_sqrt_n_pattern', '_sqrt_pattern', '_big_op_pattern',
            '_accent_pattern', '_leftright_pattern', '_superscript', '_subscript',
            '_text_pattern', '_mathrm_pattern', '_mathbf_pattern', '_binom_pattern', '_env_pattern']
for p in patterns:
    try:
        pat = getattr(c, p)
        assert isinstance(pat, re.Pattern), f'{p} is not compiled regex'
        print(f'PASS: {p}')
    except Exception as e:
        print(f'FAIL: {p} - {e}')
"
```

**PASS:** 모든 13개 패턴이 `re.Pattern` 인스턴스로 정상 컴파일
**FAIL:** 컴파일 실패 패턴 존재 — 정규식 구문 오류 수정 필요

### Step 5: 공개 API 무결성 검증

**파일:** `core/latex_to_hwpeq.py`

모듈 수준 공개 함수 `latex_to_hwpeq()`과 `latex_to_image()`가 존재하는지 확인합니다.

```bash
grep -n "^def latex_to_hwpeq\|^def latex_to_image\|^_converter" core/latex_to_hwpeq.py
```

**PASS:** `latex_to_hwpeq()` 함수와 `_converter` 싱글턴이 모듈 수준에 존재
**FAIL:** 공개 함수가 삭제되었거나 이름이 변경됨 — 다른 모듈의 import 깨짐

**위반 시 수정:** 누락된 함수를 복원하거나, import하는 모듈(`core/hwpx_writer.py`)의 참조를 업데이트합니다.

## Output Format

```markdown
## verify-latex-hwpeq 검증 결과

| # | 검사 항목 | 상태 | 상세 |
|---|----------|------|------|
| 1a | 매핑 딕셔너리 존재 | PASS/FAIL | ... |
| 1b | LaTeX 키 형식 | PASS/FAIL | ... |
| 1c | 빈 값 없음 | PASS/FAIL | ... |
| 2a | _SYMBOL_KEYWORDS 존재 | PASS/FAIL | ... |
| 2b | _LARGE_OP_KEYWORDS 항목 수 | PASS/FAIL | ... |
| 2c | 키워드 동기화 | PASS/FAIL | ... |
| 3 | 변환 순서 | PASS/FAIL | ... |
| 4 | 정규식 유효성 | PASS/FAIL | ... |
| 5 | 공개 API | PASS/FAIL | ... |
```

## Exceptions

다음은 **위반이 아닙니다**:

1. **주석 내 매핑 예시** — 주석에 있는 LaTeX 명령어 표기 (`# \alpha → alpha`)는 실제 코드가 아님
2. **테스트 코드의 매핑** — 테스트 파일에서의 매핑 값 참조는 별도 코드
3. **SYMBOL_MAP의 소문자 값** — 일부 HWP 키워드는 의도적으로 소문자 (예: "alpha", "in", "subset"). `_SYMBOL_KEYWORDS`에 이미 소문자 키워드가 별도로 포함되어 있으면 정상