---
name: verify-equation-metrics
description: 수식 크기 추정기(_estimate_equation_size) 정확도 회귀 검증. `core/hwpx_writer.py`의 수식 폭·높이 계산 로직 수정 후 사용.
---

# 수식 크기 추정기 정확도 검증

## Purpose

`core/hwpx_writer.py`의 `_estimate_equation_size`, `_measure_hwpeq_width`, 문자·키워드 폭 테이블, 전역 보정 상수가 HWP의 실제 수식 레이아웃과 일치하는지 정량 검증합니다.

골든셋: `scripts/tune_equation/golden_equations.json` (한컴이 생성한 정답 HWPX 84개 수식의 실측 `(script, width, height)`)

핵심 목표: **수식 width=0으로 인한 옆 글자 겹침 재발 방지**.

## When to Run

- `core/hwpx_writer.py`의 `_estimate_equation_size`, `_measure_hwpeq_width` 수정 후
- `_HWPEQ_CHAR_WIDTHS`, `_HWPEQ_KEYWORD_WIDTHS`, `_SYMBOL_KEYWORDS`, `_STRUCT_KEYWORDS` 변경 후
- `_HWPEQ_HANGUL_WIDTH`, `_HWPEQ_LEFT_RIGHT_EXTRA`, `_HWPEQ_GLOBAL_SCALE`, `_HWPEQ_GLOBAL_BIAS` 튜닝 후
- `_inject_equation_xml`의 sz/outMargin/baseLine 속성 수정 후
- HWPX 출력에서 수식이 옆 글자와 겹친다는 신고가 있을 때

## Related Files

| File | Purpose |
|------|---------|
| `core/hwpx_writer.py` | `_estimate_equation_size`, 상수 테이블 (주 검증 대상) |
| `scripts/tune_equation/golden_equations.json` | 84개 정답 수식 (변경 금지) |
| `tests/test_equation_metrics.py` | 회귀 테스트 스위트 |
| `scripts/tune_equation/extract_golden.py` | 새 정답 HWPX가 추가되면 재실행 |
| `scripts/tune_equation/measure_accuracy.py` | 상세 오차 리포트 |
| `scripts/tune_equation/fit_parameters.py` | 파라미터 재튜닝 시 사용 |

## Workflow

### Step 1: 회귀 테스트 실행

```bash
cd "D:/시험지 한글화" && PYTHONIOENCODING=utf-8 python tests/test_equation_metrics.py
```

**PASS 기준:**
- 13개 테스트 전부 OK
- width MAPE ≤ 10%, median ≤ 8%, p95 ≤ 25%
- height 정확도 ≥ 95%
- zero-width 수식 0개

**FAIL 시 조치:** 어떤 assert가 실패했는지에 따라
- MAPE/median 초과 → `_HWPEQ_CHAR_WIDTHS`/`_HWPEQ_KEYWORD_WIDTHS` 조정, `scripts/tune_equation/fit_parameters.py` 재실행
- height 정확도 < 95% → `_estimate_equation_size`의 `two_line` 판정 로직 확인
- zero-width 반환 → `_estimate_equation_size` 마지막 `max(int(width), 400)` 확인
- SQUARE 관련 실패 → `_SYMBOL_KEYWORDS`와 `_HWPEQ_KEYWORD_WIDTHS["SQUARE"]` 복구

### Step 2: 상세 오차 리포트로 원인 분석 (FAIL 시)

```bash
cd "D:/시험지 한글화" && PYTHONIOENCODING=utf-8 python scripts/tune_equation/measure_accuracy.py
```

**출력물:**
- width MAE/MAPE/median/p95/max
- 최악 케이스 Top 10 (각 script의 실제/추정/오차)

**판독:**
- 최악 케이스가 **매트릭스(`{array}`)** 한두 개 → 정상. 일반화 대상 아님
- 최악 케이스 대부분이 **한글 포함 수식** → `_HWPEQ_HANGUL_WIDTH` 재튜닝
- 최악 케이스 대부분이 **LEFT/RIGHT 포함** → `_HWPEQ_LEFT_RIGHT_EXTRA` 재튜닝
- 최악 케이스가 **분수 + 뒤 표현식** → `_estimate_equation_size`의 분수 분기 (`FRAC_SCALE`, frac_w padding) 확인

### Step 3: 필수 수식 XML 속성 고정값 검증

**파일:** `core/hwpx_writer.py` (`_inject_equation_xml` 함수)

정답 HWPX 84개 전부 동일한 값을 갖는 세 속성이 코드에서 하드코딩으로 유지되는지 확인:

```bash
grep -n '"outMargin"\|"baseLine"\|"TOP_AND_BOTTOM"' core/hwpx_writer.py | head -20
```

**PASS 기준:**
- `out_margin.set("left", "170")` 및 `right="170"`
- `eq.set("baseLine", "85")` 고정
- `eq.set("textWrap", "TOP_AND_BOTTOM")` 고정
- `pos.set("treatAsChar", "1")` 고정
- `sz.set("width", str(est_width))` 및 `sz.set("height", str(est_height))` — **"0"이 아닌 실제 값**

**FAIL 시 조치:** 어떤 속성이든 정답과 다른 값이 들어가면 바로 수정. 특히 width=0은 옆 글자 겹침의 주원인이므로 절대 금지.

### Step 4: 새 정답 HWPX가 추가됐는지 확인

`data/골든셋기준_조암중_hwpx해제본/` 외의 새 정답 폴더가 추가되면 골든셋 확장 고려:

```bash
ls "D:/시험지 한글화" | grep -i "hwpx_"
```

새 폴더가 있다면 `scripts/tune_equation/extract_golden.py`를 수정해 복수 레퍼런스를 병합한 뒤 재실행. 골든셋이 확장되면 `fit_parameters.py`를 재돌려 파라미터를 재튜닝.

## Output Format

```markdown
## verify-equation-metrics 검증 결과

| # | 검사 항목 | 상태 | 상세 |
|---|----------|------|------|
| 1 | 13개 회귀 테스트 | PASS/FAIL | MAPE=X.X%, median=X.X%, p95=X.X%, height=XX/84 |
| 2 | 최악 케이스 분석 | (FAIL 시만) | ... |
| 3 | XML 속성 고정값 | PASS/FAIL | outMargin=170, baseLine=85, textWrap=TOP_AND_BOTTOM, treatAsChar=1, sz ≠ 0 |
| 4 | 골든셋 확장 여부 | INFO | 현재 data/골든셋기준_조암중_hwpx해제본 84개 / 추가 레퍼런스: 없음 |
```

## Exceptions

다음은 **위반이 아닙니다**:

1. **개별 매트릭스 수식의 최대 오차 30% 이상** — `{array}{|c|c|c|}` 환경은 셀 개수에 따라 폭이 크게 달라지며 이 추정기의 범위 밖. p95 기준만 만족하면 허용.
2. **짧은 수식(width < 1500)의 절대 오차가 300 HWPUNIT 이하인데 상대 오차가 20%로 표시** — 상대 오차 기준이 엄격한 것일 뿐 시각적 차이는 없음.
3. **`_HWPEQ_GLOBAL_SCALE`/`_HWPEQ_GLOBAL_BIAS`를 재튜닝한 후 소수점 아래 변경** — 재피팅 시 기대되는 동작.
