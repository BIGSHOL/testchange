---
name: verify-output-format
description: 시험지 출력 포맷 합의사항(미주 번호·배점 정렬·표 셀·보기 박스·선택지 정렬 등)이 COM writer/폼 writer 에 강제 적용되어 있는지 검증. core/hwp_com_writer.py, core/hwp_com.py, core/hwp_form_writer.py 수정 후 사용.
---

# 시험지 출력 포맷 합의사항 검증

## Purpose

HWP COM writer(`core/hwp_com_writer.py`, `core/hwp_com.py`)와 폼 writer(`core/hwp_form_writer.py`)가
사용자와 **합의한 출력 포맷**을 유지하는지 검증한다. 이 합의들은 렌더 실측으로 확정됐고, 회귀하면 시험지 모양이 틀어진다.
각 합의는 코드의 특정 마커로 강제되며, 이 스킬이 그 마커의 존재·정합을 확인한다.

> **합의사항(스펙) 자체가 이 문서다.** 포맷 합의가 추가/변경되면 이 스킬의 검사 항목과
> `scripts/verify_output_format.py` 를 함께 갱신해 "강제 행사"를 유지한다.

## 자동 강제 (PostToolUse 훅)

`.claude/settings.json` 의 PostToolUse 훅이 `core/hwp_com_writer.py`·`core/hwp_com.py`·
`core/hwp_form_writer.py`·`core/latex_to_hwpeq.py`·`core/ocr_engine.py` 를 **편집할 때마다** `scripts/verify_output_format.py` 를 자동
실행한다. 합의 위반이 생기면 훅이 **exit 2 로 차단 피드백**을 주므로 회귀가 즉시 잡힌다.
이 SKILL 의 검사 항목과 그 스크립트는 동일한 30개 검사를 수행한다(스크립트=실행 백엔드,
SKILL=사람이 읽는 스펙·수동 실행 절차). 수동 전체 검증: `python scripts/verify_output_format.py --all`.

> 훅 설정 변경은 Claude Code 재시작(또는 `/hooks` 확인) 후 적용된다.

## When to Run

- `core/hwp_com_writer.py` / `core/hwp_com.py` / `core/hwp_form_writer.py` 의 렌더·레이아웃 로직 수정 후
- 출력 시험지 모양이 합의와 달라 보일 때
- PR 전 / `verify-implementation` 일괄 검증의 일부로

## Related Files

| File | Purpose |
|------|---------|
| `core/hwp_com_writer.py` | ExamDocument→HWP 렌더러 (주 검증 대상) |
| `core/hwp_com.py` | 저수준 COM 세션(표·수식·미주·글자모양) |
| `core/hwp_form_writer.py` | 폼 자동입력 렌더러(기본 경로와 동일 합의 적용) |
| `core/latex_to_hwpeq.py` | 수식 변환(집합 기호 `\mid` 등) |
| `core/ocr_engine.py` | OCR 프롬프트·후보정(표/지문 누락 방지) |

## 합의사항 ↔ 코드 마커

| # | 합의사항 | 강제 마커(코드) |
|---|----------|----------------|
| 1 | 문항번호 = 미주 자동번호 | `_write_question` 에서 `self.s.endnote()` 호출 |
| 2 | 미주 번호 형식 "1." (suffix `.`) | `_set_endnote_suffix` 정의 + `write_exam_to_hwp` 에서 호출 |
| 3 | 미주 번호 12pt 볼드 | `endnote()` 가 `set_char_shape(self.note_pt, bold=True)`; `note_pt` 기본 12 |
| 4 | 객관식 배점 = 발문 끝 인라인 | `_write_question` 의 `else: self._write_score(question.score)` |
| 5 | 서술형 배점 = 줄바꿈 + 우측정렬 | `if is_essay:` 블록에서 `align_right()` 후 `_write_score(..., leading_space=False)` |
| 6 | 보기/조건 = 1×1 테두리 표 박스 | `_write_condition_box` 의 `table_begin(1, 1)` |
| 7 | 박스 ↔ 선택지 빈 줄 없음 | `ended_box = self._write_tail(tail)` + `if question.choices and not ended_box:` (박스로 끝나면 추가 줄바꿈 없음) |
| 8 | 선택지 2열 ②④ 정렬 | `_write_choice(choice, as_equation=(cols == 2))` + `_write_choice` 의 `as_equation` 분기 |
| 9 | 표 셀 = 수식 객체 | `_write_equation_table` 의 `self.s.equation(latex_to_hwpeq(` |
| 10 | 표 셀 = 가운데 정렬 | `_write_equation_table` 의 `align_center()` |
| 11 | 번호-발문 같은 줄(A7) | `_write_block(block, inline=(i == 0))` |
| 12 | 모든 숫자·문자 수식화(A8) | 순수숫자 텍스트 강등 코드(`_is_plain_number`/`_PLAIN_NUMBER_RE`) **없음** |
| 13 | 표 생성 다중표 안전 | `table_begin` 이 `CreateAction("TableCreate")` 사용(공유 HParameterSet 금지) |
| 14 | 셀 안 수식 커서 보존 | `equation()` 의 `Run("Close")` 가 `if h.GetPos()[0] == 0:` 가드 안 |
| 15 | 표 탈출 = 다음 단락 | `table_end()` 가 `SetPos(p[0], p[1] + 1, 0)` (MoveRight 재진입 금지) |
| 16 | 글자모양 투명 방지 | `set_char_shape` 가 `Ratio*`/`Size*` 를 100 으로 설정 |
| 17 | 집합 기호 바 `\mid` | `latex_to_hwpeq` SYMBOL_MAP 에 `\mid` |
| 18 | 발문 아래 블록수식 가운데정렬 | `_write_block` 의 `EQUATION_BLOCK` 분기 `if not inline:` 에 `align_center()` |
| 19 | 소문항 부모 총점 우측정렬 | `_split_trailing_score` 정의 + `elif has_subs and total_num:` 에 `align_right()` |
| 20 | 발문뒤 영역 공통 렌더 | `_write_tail`·`_tail_start` 정의 + `_write_condition_box(box)` 호출(폼·기본 공유) |
| 29 | 표 캡션(표 제목) = 줄바꿈 후 **우측정렬** (배점과 같은 줄 금지, 2026-06-10) | `_caption_spans` 정의 + `_write_caption_run` 에 `align_right()` + `_write_condition_box` 표-혼합 경로가 `_write_tail_seq` 사용 + 폼 `_put_tail` 의 `w._write_caption_run(pre[cap_j:])` |
| 30 | 배점 우측정렬 폴백 = **삽입분(sp→ep)만** 선택-삭제 | 4개 폴백(`_write_score_inline_or_right`·`_write_total_score_inline_or_right`·폼 `_put_score`·`_put_total_score`)에 `h.Run("MoveSelParaEnd")` **없음** + `SelectText(sp[1], sp[2], ep[1], ep[2])`. MoveSelParaEnd 는 마지막 서술형에서 표 탈출로 본문이 폼 **정답 단락 안**에 타이핑될 때 정답 블록 앵커까지 삼켜 정답 페이지가 증발했다(강동중 #20, 2026-06-10) |

(#21~#28 은 OCR/변환기 방어 하네스 — `scripts/verify_output_format.py` 참조.)

**참고(2026-06-05):** 위 합의는 **폼 경로(`core/hwp_form_writer.py`)에도 동일 적용**된다(사용자
'항상 동일' 요구). 폼은 발문뒤 렌더를 `HwpComWriter(ses)._write_tail`/`_write_condition_box` 로
**재사용**하므로 같은 코드로 보장된다. 그림만 폼 전용 토큰 임베드(`_insert_picture_inline`).

## Workflow

### Step 1: 미주(문항번호) 합의 (#1·#2·#3)

```bash
grep -n "self.s.endnote()" core/hwp_com_writer.py
grep -n "def _set_endnote_suffix\|_set_endnote_suffix(output_path)" core/hwp_com_writer.py
grep -n "set_char_shape(self.note_pt, bold=True)" core/hwp_com.py
grep -n "note_pt" core/hwp_com.py | grep -i "12"
```

**PASS:** 네 검사 모두 매치(미주 호출 / suffix 정의+호출 / 12pt 볼드 / note_pt 기본 12).
**FAIL:** 하나라도 없음 → 미주 번호가 "1)" 작은 글씨로 회귀.

### Step 2: 배점 정렬 합의 (#4·#5)

`core/hwp_com_writer.py` 의 `_write_question` 배점 처리부를 Read 로 확인한다.

```bash
grep -n "is_essay" core/hwp_com_writer.py
grep -n "align_right()" core/hwp_com_writer.py
```

**PASS:** `if is_essay:` 분기 안에 `break_para()`→`align_right()`→`_write_score(..., leading_space=False)`→`break_para()`→`align_left()` 가 있고, `else:` 분기는 인라인 `self._write_score(question.score)`.
**FAIL:** 서술형 분기에 `align_right` 가 없으면 배점이 왼쪽에 붙는다(회귀).

### Step 3: 보기/조건 박스 합의 (#6·#7)

```bash
grep -n "table_begin(1, 1)" core/hwp_com_writer.py
```

`_write_question` 의 박스 처리부를 Read 로 확인: `if box: self._write_condition_box(box)` **직후에 `break_para()` 가 없어야** 하고, `else: self.s.break_para()` 만 있어야 한다.

**PASS:** 박스=1×1 표, 박스 분기에 추가 break 없음.
**FAIL:** 박스 분기 뒤 `break_para` 가 있으면 박스와 선택지 사이에 빈 줄 회귀.

### Step 4: 선택지 2열 정렬 합의 (#8)

```bash
grep -n "as_equation=(cols == 2)" core/hwp_com_writer.py
grep -n "def _write_choice(self, choice: Choice, as_equation" core/hwp_com_writer.py
```

**PASS:** 두 검사 매치(2열일 때 수식 객체화 전달 + `_write_choice` 가 `as_equation` 분기에서 TEXT 를 `equation(latex_to_hwpeq(...))` 로).
**FAIL:** 없으면 텍스트 보기 ②④ 가 열정렬 안 됨.

### Step 5: 표 셀 합의 (#9·#10)

```bash
grep -n "def _write_equation_table" core/hwp_com_writer.py
grep -n "self.s.equation(latex_to_hwpeq(val))" core/hwp_com_writer.py
grep -n "align_center()" core/hwp_com_writer.py | head
```

`_write_equation_table` 안에 셀마다 `align_center()` + `equation(latex_to_hwpeq(val))` 가 있는지 Read 로 확인. 평문 `self.s.table(` 직접 호출이 _write_block 의 TABLE 분기에 **없어야** 한다.

```bash
grep -n "self.s.table(" core/hwp_com_writer.py
```

**PASS:** 표 셀이 수식+가운데, `_write_block` 의 TABLE 분기는 `_write_equation_table` 사용.
**FAIL:** `self.s.table(block.rows` 가 남아 있으면 셀이 평문·좌측 회귀.

### Step 6: A7·A8 합의 (#11·#12)

```bash
grep -n "inline=(i == 0)" core/hwp_com_writer.py
grep -n "_is_plain_number\|_PLAIN_NUMBER_RE" core/hwp_com_writer.py
```

**PASS:** `inline=(i == 0)` 존재(번호-발문 같은 줄), 순수숫자 강등 코드는 **0건**.
**FAIL:** 강등 코드가 다시 생기면 숫자가 텍스트로(A8 위반).

### Step 7: COM 안전장치 합의 (#13·#14·#15·#16)

```bash
grep -n "CreateAction(\"TableCreate\")" core/hwp_com.py
grep -n "if h.GetPos()\[0\] == 0:" core/hwp_com.py
grep -n "SetPos(p\[0\], p\[1\] + 1, 0)" core/hwp_com.py
grep -n "Ratio{sc}\|Size{sc}\|f\"Ratio\|f\"Size" core/hwp_com.py
```

**PASS:** 네 마커 모두 존재(다중표 크래시·셀수식 이탈·표탈출·투명글자 방지).
**FAIL:** 빠지면 표 크래시/레이아웃 깨짐 재발(2026-06-04 디버깅 회귀).

### Step 8: 수식 변환 합의 (#17)

```bash
grep -nF 'r"\mid"' core/latex_to_hwpeq.py
python -c "from core.latex_to_hwpeq import latex_to_hwpeq as f; assert f(r'x \mid y').count('|')==1, f(r'x \mid y'); print('PASS mid')"
```

**PASS:** `\mid` 매핑 존재(`grep -F` 로 백슬래시 리터럴 매치) + 변환 결과에 `|` 1개.
런타임 `python -c` 검사가 권위 있다(grep 은 보조).
**FAIL:** 집합표기 `{x | x≤3}` 의 바가 누락(`xx` 로 붙음).

## Output Format

```markdown
## verify-output-format 검증 결과

| # | 합의사항 | 상태 | 상세 |
|---|----------|------|------|
| 1 | 미주 자동번호 | PASS/FAIL | ... |
| 2 | 미주 suffix "." | PASS/FAIL | ... |
| 3 | 미주 12pt 볼드 | PASS/FAIL | ... |
| 4 | 객관식 배점 인라인 | PASS/FAIL | ... |
| 5 | 서술형 배점 우측정렬 | PASS/FAIL | ... |
| 6 | 보기 1×1 박스 | PASS/FAIL | ... |
| 7 | 박스↔선택지 빈줄 없음 | PASS/FAIL | ... |
| 8 | 선택지 2열 정렬 | PASS/FAIL | ... |
| 9 | 표 셀 수식 | PASS/FAIL | ... |
| 10 | 표 셀 가운데정렬 | PASS/FAIL | ... |
| 11 | 번호-발문 같은 줄 | PASS/FAIL | ... |
| 12 | 숫자 수식화(강등 없음) | PASS/FAIL | ... |
| 13 | 표 CreateSet | PASS/FAIL | ... |
| 14 | 셀수식 Close 가드 | PASS/FAIL | ... |
| 15 | 표 탈출 SetPos | PASS/FAIL | ... |
| 16 | 글자 투명 방지 | PASS/FAIL | ... |
| 17 | \mid 매핑 | PASS/FAIL | ... |
```

## Exceptions

다음은 **위반이 아니다**:

1. **주석 안의 마커 언급** — 주석에서 합의를 설명하는 문구는 실제 코드가 아님(검사는 실행
   코드의 호출/할당을 본다).
2. **`_write_essay_space`/`_write_score`의 정의 존재** — `_write_essay_space` 는 호출되지
   않는 게 정상(서술형 답란 미삽입, 2026-06-02 합의). 정의만 있는 것은 위반 아님.
3. **fallback XML writer(`core/hwpx_writer.py`)** — 이 스킬은 COM 경로만 검증한다.
   fallback 의 정렬/상수는 `verify-hwpx-structure` 소관.
4. **`note_pt` 를 호출부에서 다른 값으로 명시** — 사용자가 의도적으로 크기를 바꾼 경우.
   기본값 12 가 정의에 있으면 PASS.
