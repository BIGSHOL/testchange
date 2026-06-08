---
name: verify-hwpx-structure
description: HWPX 문서 생성 구조 검증. HWPX 생성/템플릿 로직 수정 후 사용.
---

# HWPX 문서 생성 구조 검증

## Purpose

HWPX 문서 생성(`core/hwpx_writer.py`)과 템플릿 로딩(`core/template_loader.py`) 모듈의 구조적 무결성을 검증합니다:

1. **XML 네임스페이스 동기화** — `hwpx_writer.py`와 `template_loader.py`의 NS 딕셔너리가 동일한지
2. **상수 값 일관성** — FRAC_SCALE, CHAR_WIDTH, LINE_CAPACITY 등 핵심 상수가 코드 내에서 일관되게 사용되는지
3. **원숫자 매핑 완전성** — CIRCLE_NUMBERS가 ①②③④⑤를 올바르게 매핑하는지
4. **정렬 ID 일관성** — `_RIGHT_ALIGN_PR_ID`, `_CENTER_ALIGN_PR_ID`가 선언과 사용 위치에서 일치하는지

## When to Run

- `core/hwpx_writer.py`의 상수나 레이아웃 로직을 변경한 후
- `core/template_loader.py`의 네임스페이스나 파싱 로직을 변경한 후
- HWPX 출력의 수식 크기 또는 레이아웃이 비정상적일 때
- 템플릿 관련 기능을 추가/수정한 후

## Related Files

| File | Purpose |
|------|---------|
| `core/hwpx_writer.py` | HWPX 문서 생성기 (주 검증 대상) |
| `core/template_loader.py` | HWPX 템플릿 로더 (NS 동기화 대상) |
| `models/template_config.py` | 템플릿 설정 데이터 모델 |

## Workflow

### Step 1: XML 네임스페이스 동기화 검증

**파일:** `core/hwpx_writer.py`, `core/template_loader.py`

두 파일의 `NS` 딕셔너리가 동일한 키-값 쌍을 포함하는지 확인합니다.

```bash
python -c "
import ast, sys
sys.path.insert(0, '.')
# 파일에서 NS 딕셔너리 추출
def extract_ns(filepath):
    with open(filepath) as f:
        for line in f:
            if line.strip().startswith('NS = {'):
                lines = [line]
                while '}' not in lines[-1]:
                    lines.append(next(f))
                return eval(''.join(lines).split('=', 1)[1].strip())
    return None

ns_writer = extract_ns('core/hwpx_writer.py')
ns_loader = extract_ns('core/template_loader.py')

if ns_writer == ns_loader:
    print('PASS: NS dictionaries are identical')
    for k, v in ns_writer.items():
        print(f'  {k}: {v}')
else:
    print('FAIL: NS dictionaries differ')
    for k in set(list(ns_writer.keys()) + list(ns_loader.keys())):
        w = ns_writer.get(k, 'MISSING')
        l = ns_loader.get(k, 'MISSING')
        status = 'OK' if w == l else 'MISMATCH'
        print(f'  {status}: {k} -> writer={w}, loader={l}')
"
```

**PASS:** 두 파일의 NS 딕셔너리가 동일 (5개 키: hp, hs, hc, hh, ha)
**FAIL:** 키 또는 값이 다름 — 한쪽을 수정하여 동기화 필요

**위반 시 수정:** 두 파일의 NS 딕셔너리를 동일하게 맞춥니다. 기준은 `hwpx_writer.py` (주 생성기).

### Step 2: 핵심 상수 값 일관성 검증

**파일:** `core/hwpx_writer.py`

**검사 2a:** `LINE_CAPACITY` 값이 모든 사용 위치에서 동일한지 확인합니다.

```bash
grep -n "LINE_CAPACITY" core/hwpx_writer.py
```

**PASS:** 모든 `LINE_CAPACITY = 42520` 할당이 동일한 값
**FAIL:** 서로 다른 값이 존재 — 레이아웃 계산 불일치

**검사 2b:** `FRAC_SCALE` 값이 일관되게 0.85인지 확인합니다.

```bash
grep -n "FRAC_SCALE" core/hwpx_writer.py
```

**PASS:** `FRAC_SCALE = 0.85` 값이 일관됨
**FAIL:** 다른 값이 사용됨 — 수식 크기 계산 오류

**검사 2c:** `CHAR_WIDTH` 값이 일관되게 650인지 확인합니다.

```bash
grep -n "CHAR_WIDTH" core/hwpx_writer.py
```

**PASS:** `CHAR_WIDTH = 650` 값이 일관됨
**FAIL:** 다른 값이 사용됨

### Step 3: 원숫자 매핑 완전성 검증

**파일:** `core/hwpx_writer.py`

`CIRCLE_NUMBERS` 딕셔너리가 1~5 매핑을 모두 포함하는지 확인합니다.

```bash
grep -A 5 "CIRCLE_NUMBERS" core/hwpx_writer.py
```

**PASS:** `{1: "①", 2: "②", 3: "③", 4: "④", 5: "⑤"}` 5개 매핑 완전
**FAIL:** 누락된 번호가 있음 — 선택지 번호 표시 오류

**위반 시 수정:** 누락된 매핑을 추가합니다. 유니코드: ① = U+2460, ② = U+2461, ③ = U+2462, ④ = U+2463, ⑤ = U+2464

### Step 4: 정렬 ID 일관성 검증

**파일:** `core/hwpx_writer.py`

`_RIGHT_ALIGN_PR_ID`와 `_CENTER_ALIGN_PR_ID`의 선언 값이 사용 위치와 일치하는지 확인합니다.

```bash
grep -n "_RIGHT_ALIGN_PR_ID\|_CENTER_ALIGN_PR_ID" core/hwpx_writer.py
```

**PASS:** 선언된 값 (`"100"`, `"101"`)이 모든 사용 위치에서 변수 참조로 사용됨 (하드코딩된 문자열이 아닌 변수 사용)
**FAIL:** 하드코딩된 `"100"` 또는 `"101"`이 변수 대신 직접 사용됨

### Step 5: 템플릿 필수 파일 경로 검증

**파일:** `core/template_loader.py`

HWPX ZIP 내 필수 파일 경로가 올바르게 정의되어 있는지 확인합니다.

```bash
grep -n "header.xml\|section0.xml\|REQUIRED" core/template_loader.py
```

**PASS:** `Contents/header.xml`과 `Contents/section0.xml`이 필수 파일로 정의됨
**FAIL:** 필수 파일 경로가 누락되거나 변경됨

### Step 6: 수식 XML 구조 검증

**파일:** `core/hwpx_writer.py`

수식 삽입 시 필수 XML 요소(`hp:equation`, `hp:script`, `hp:sz`, `hp:pos`)가 코드에서 생성되는지 확인합니다.

```bash
grep -n "equation\|hp:script\|hp:sz\|hp:pos\|shapeComment" core/hwpx_writer.py | head -20
```

**PASS:** 수식 XML의 필수 요소 (equation, script, sz, pos)가 모두 생성됨
**FAIL:** 필수 XML 요소 누락 — 한글에서 수식이 표시되지 않음

## Output Format

```markdown
## verify-hwpx-structure 검증 결과

| # | 검사 항목 | 상태 | 상세 |
|---|----------|------|------|
| 1 | NS 네임스페이스 동기화 | PASS/FAIL | ... |
| 2a | LINE_CAPACITY 일관성 | PASS/FAIL | ... |
| 2b | FRAC_SCALE 일관성 | PASS/FAIL | ... |
| 2c | CHAR_WIDTH 일관성 | PASS/FAIL | ... |
| 3 | 원숫자 매핑 완전성 | PASS/FAIL | ... |
| 4 | 정렬 ID 일관성 | PASS/FAIL | ... |
| 5 | 템플릿 필수 파일 경로 | PASS/FAIL | ... |
| 6 | 수식 XML 구조 | PASS/FAIL | ... |
```

## Exceptions

다음은 **위반이 아닙니다**:

1. **`LINE_CAPACITY`의 지역 변수 재선언** — 여러 메서드에서 동일한 값으로 지역 변수를 선언하는 것은 Python 클래스 패턴상 정상 (모듈 상수가 아닌 메서드 내 상수)
2. **NS 딕셔너리 외 네임스페이스 문자열** — XML 요소를 직접 생성할 때 `{http://...}tagname` 형태로 네임스페이스를 인라인하는 것은 lxml 패턴
3. **테스트 파일의 상수 참조** — 테스트에서 별도의 상수 값을 정의하는 것은 테스트 고유 설정