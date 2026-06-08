## Skills

커스텀 검증 및 유지보수 스킬은 `.claude/skills/`에 정의되어 있습니다.

| Skill | Purpose |
|-------|---------|
| `verify-implementation` | 프로젝트의 모든 verify 스킬을 순차 실행하여 통합 검증 보고서를 생성합니다 |
| `manage-skills` | 세션 변경사항을 분석하고, 검증 스킬을 생성/업데이트하며, CLAUDE.md를 관리합니다 |
| `verify-latex-hwpeq` | LaTeX→HWP 수식 변환 매핑 무결성 검증 |
| `verify-hwpx-structure` | HWPX 문서 생성 구조 검증 |
| `verify-equation-metrics` | 수식 크기 추정기 정확도 회귀 검증 (골든셋 84개 기반) |
| `verify-ocr-parser-sync` | OCR 엔진↔콘텐츠 파서 동기화 검증 |
| `verify-output-format` | 시험지 출력 포맷 합의사항(미주 번호·배점 정렬·표 셀·보기 박스·선택지 정렬) 강제 적용 검증 |

## 시험지 출력 포맷 합의사항 (COM writer — 강제 준수)

`core/hwp_com_writer.py`·`core/hwp_com.py` 의 렌더 출력은 아래 합의를 **반드시** 지킨다.
**폼 경로(`core/hwp_form_writer.py`)도 이 합의를 똑같이 따른다 — 사용자 '항상 동일, 폼이든
아니든' 요구(2026-06-05).** 그래서 발문뒤 영역(조건/보기 박스·블록수식·그림) 렌더는 두 경로가
**공유 코드**(`_tail_start`·`_write_tail`·`_write_condition_box`·`_write_block`·`_split_trailing_score`,
모두 `hwp_com_writer.py`)를 쓴다. 폼은 그림만 토큰 임베드(`_insert_picture_inline`)를 따로 쓴다
(폼 binItem 버그 회피, 메모리 `form-figure-embed`). 회귀 방지는 **자동 강제**된다:
`.claude/settings.json` 의 PostToolUse 훅이 위 파일(+`latex_to_hwpeq.py`·`ocr_engine.py`) 편집 시마다
`scripts/verify_output_format.py` 를 돌려 위반이면 차단(exit 2)한다. 수동 검증은
`verify-output-format` 스킬 또는 `python scripts/verify_output_format.py --all`. 합의가
바뀌면 코드·그 스크립트·`verify-output-format` SKILL.md 를 **함께** 갱신한다.

1. **문항번호** = 미주 자동번호, 형식 **"1."**(suffix `.`), **12pt 볼드**.
2. **배점** — 객관식: 발문 끝 인라인 `[N점]`. **서술형: 줄바꿈 후 우측정렬**. **소문항 부모의
   총점은 발문 본문의 `[총 N점]` 을 떼어내(`_split_trailing_score`) 줄바꿈 후 우측정렬**.
3. **보기/조건** = 1×1 테두리 표 박스. 박스↔선택지 사이 **빈 줄 없음**. **발문뒤 경계
   (`_tail_start`)는 조건/보기 머리 + 표 + 그림 + 블록수식**(배점은 그 앞=발문 끝).
4. **선택지** — 짧으면 2열(①②/③④/⑤). 2열일 때 **수식 객체화**로 ②④ 열 정렬.
5. **표 셀** = **수식 객체 + 가운데 정렬**(평문 금지).
6. **수식** — 모든 숫자·문자 수식 객체화(순수숫자 텍스트 강등 금지). 번호-발문 같은 줄.
   **발문 아래 독립 블록수식(EQUATION_BLOCK)은 가운데 정렬**. 연속 블록수식은 빈 줄 없이 각
   줄 가운데. **그림(IMAGE)도 가운데**, 그림↔조건 박스 사이 **빈 줄 없음**(`_write_condition_box`
   가 단락시작 pos==0 이면 그 빈 단락을 재사용).
7. **COM 안전장치**(깨지면 위 합의가 무너짐): 표 생성 `CreateAction/CreateSet`(다중표
   크래시), 셀 안 수식 `Close` 본문(list 0)한정, 표 탈출 `SetPos(para+1)`, 글자모양
   `Ratio*/Size*`=100(투명 방지), `\mid`→`|` 매핑. 상세 함정: 메모리 `hwp-com-table-equation`.

## 작업 마무리 워크플로우 (필수)

코드를 변경한 뒤에는 **항상 아래 순서로 마무리**한다:

1. **검증** — 변경을 실데이터/렌더로 확인(가능하면 HWP COM 렌더 PNG로 육안 확인).
2. **사용자 최종 체크** — 커밋·푸시·배포 전에 **반드시 사용자에게 결과를 보여주고 확인(체크)을 받는다.** 사용자 승인 없이 커밋/푸시/배포하지 않는다.
3. **커밋 + 푸시** — 승인되면 커밋하고 **`testchange` 원격(BIGSHOL)** 으로 푸시한다 (`git push testchange master`).
4. **exe 빌드 + 배포** — `python -m PyInstaller build.spec --noconfirm` 로 재빌드하고, `dist/시험지한글화/` 의 exe와 `_internal` 을 `배포용/` 으로 복사한다. **`배포용/config.json` 은 보존**(robocopy `/MIR` 는 `_internal` 에만 적용). 배포 후 `--selftest` 로 임포트 확인.

### 보안 (절대 준수)
- **API 키(ANTHROPIC/GEMINI)는 gitignore된 `config.json` 에만** 둔다. 추적 파일·커밋에 키를 절대 넣지 않는다. (`config.json`, `build/`, `dist/`, `배포용/` 은 `.gitignore` 처리됨.)

## OCR/파서 후보정 교훈 — 확통 등 어려운 시험지 대응 (2026-06-08, 긴 디버깅)

확률과 통계처럼 표·지문·확률표기가 많은 시험지에서 드러난 함정과 해결. **전부 결정적
후보정**(프롬프트 의존 최소화)으로 잡았다. 회귀 방지: `scripts/verify_output_format.py`(28개)
+ 아래 단위검증.

### ⭐ 비전 OCR "요약" 누락 — 단일 크롭의 본질적 한계
- **단일 문제 크롭을 구조화(JSON) OCR 하면 비전 모델이 긴 지문 박스·확률분포표를 "요약"하며
  통째 누락**한다(독수리 이야기 박스, #3·#4 확률분포표). 같은 모델이 **전체 페이지** 또는
  **"그대로 전사(transcription)"** 작업에선 충실히 읽는다(검증). 프롬프트 강화(4종)로는 못 막음.
- 해결(서술형): `core/ocr_engine._merge_missing_passages` — **선택지 없는 크롭**에 전사 2-pass를
  돌려 구조화가 빠뜨린 문단을 찾아 원위치 삽입. **존재 판정은 12자 윈도우(6자 stride) 다중
  포함검사** — 접두 단일매칭은 라벨차이([서답형]vs[서술형])·수식분리로 어긋나 **정상 서답형을
  통째 `<상자>` 박스로 오주입**(중복·박스갇힘)했다. 윈도우 하나라도 맞으면 "있음"=주입 안 함.
- ⚠️ **객관식 표 누락은 아직 미해결**(2-pass는 서술형만). 객관식 확률분포표 복구는 추후(전사+표
  구조 복원 필요).
- **이미지는 프롬프트보다 앞**에 두는 게 비전 충실도에 유리(단 캐싱 포기). 단 박스/표 요약은
  순서로 안 풀리고 위 전사 2-pass가 본질 해결.

### 보기/조건 박스 = 5×5 병합표 폼 (`──<보기>──`)
- 레퍼런스 워드본의 보기 박스는 **5×5 병합표**(윗테두리에 라벨이 박힘). 단순 1×1로는 재현 불가.
- 구현: COM 은 지금처럼 1×1 박스에 내용을 우리 스타일로 채우고, **저장 후 XML에서 5×5 폼으로
  치환**(`core/bogi_box_template.py` 템플릿 + `core/hwp_com_writer._inject_bogi_form`). borderFill
  9종을 우리 header에 ID충돌 없이 주입, 내용 셀엔 우리 단락 이동(레퍼런스 charPr/paraPr ID 못 씀
  → 빈 셀은 paraPr/charPr=0). 기본·폼 경로 둘 다 저장 후 호출. 멱등(2회 호출 0건).
- **라벨 규칙(사용자 결정)**: 원본에 라벨이 **있을 때만** 표기. `<보기>`/`<조건>` = 5×5 폼(라벨
  표시), **`<상자>` = 라벨 없는 그냥 1×1 박스(표시 안 함)** — #1처럼 라벨 없는 테두리 박스·지문
  박스용. OCR 프롬프트도 "원본 라벨 있을 때만 `<보기>`/`<조건>`, 없으면 `<상자>`".

### 로만체 = 점·선·면 기하 도형만 (사용자 강력 요구)
- `core/content_parser._romanize_point_names`: 대문자 **2~4글자**(AB·ABC·OAB 꼭짓점) 항상 로만,
  **1글자**(A·X·P·E…)는 **엄격 기하 키워드**(점·꼭짓점·교점·원점·삼각형·선분·직선·△·∠ 등; 넓이·
  함수·그래프 제외) 문맥일 때만 로만. **확통의 X·P·E·V·Z·N(확률변수·연산자)은 이탤릭 유지.**
  (과거 "대문자=무조건 로만"이 과해 확통 기호까지 로만화됨.)

### latex_to_hwpeq — HWP 키워드 공백 분리 (PLEFT/XLEQ 버그)
- HWP 키워드(LEFT·RIGHT·LEQ·GEQ·NEQ·TIMES…)로 치환할 때 **앞뒤 공백을 보장**한다. 안 그러면
  `P\left`→"PLEFT", `X\le`→"XLEQ" 로 앞글자에 붙어 **literal 렌더 + 연속대문자 로만화** 연쇄.
- `\%`→`%` 매핑(없으면 "99\%" literal). `%` 는 unit 로만화 대상에서 제외(이미 정자).

### 병렬화·방어·표시
- **크롭 검출(Gemini) 페이지 병렬**(`gui/main_window.py` `as_completed`, 최대 6동시) — 직렬이
  최대 병목이었음. OCR은 페이지 **내** 병렬, 페이지 **간 직렬**(레이트리밋 burst 제어, 의도적).
- **레이트리밋 백오프**: 429·529·5xx·연결오류 지수 백오프 재시도(`_stream_message` + 클라이언트
  `max_retries=5`; ocr/crop/figure 전부). retry-after 헤더 우선 + 지터.
- **실시간 작성 표시**: `core/hwp_com.CONVERSION_VISIBLE`(변환 중 한글 창 표시). 느리면 False 로.
- **그림 렌더 OFF면 SVG 생성 자체 금지**: `_resolve_figures` 가 `render_figures` 를 보고 OFF면
  figure→안내 텍스트(`_FIGURE_NOTE_TEXT`)로 대체. 안 그러면 체크 꺼도 깨진 SVG 곡선이 보기
  박스에 생성됨(사용자 보고).

### 기타 결정적 후보정 (content_parser)
- `__xy__`(이중밑줄로 둘러싼 라틴/수식)는 OCR 오인 → **수식 복원**(한글 강조 `__않은__`은 밑줄).
- `eq·(연산자)·eq` 로 쪼개진 수식(`x = -2y+3`)을 **한 수식 객체로 병합**(`_merge_operator_split_equations`).
- 소문항 마커 중복: 파서가 `(1)` 을 `( + EQ"1" + )` 로 쪼개도 잡는 견고한 `_strip_leading_submarker`.

## 학남고 확통 (워드본) 비교 교정 — 크리티컬 수정 (2026-06-08)

수기 워드본과 1:1 비교하며 잡은 치명적 결함들. 전부 결정적 후보정. 회귀 방지:
`scripts/verify_output_format.py`(28개) + 캐시 렌더(`D:\tmp\testkit.py --render-only`, **API 0원**).

### ⭐⭐ 데이터 오염 — 변환 중 COM 이 '사용자가 보는' 한글 문서에 타이핑
- **한글 파일이 2개 열려 있으면 COM HAction 이 *사용자가 포커스한* 문서에 글자를 찍는다**
  (변환 대상이 아니라). 원인 = `hwp_com.CONVERSION_VISIBLE=True`(변환 중 한글 창 표시)면
  COM 앱이 사용자 세션과 프로세스를 공유 → 입력이 포커스 창으로 샌다. **해결: 기본
  `CONVERSION_VISIBLE=False`(숨김)**. 절대 다시 True 로 두지 말 것(사용자 작업물 손상).
- GUI 는 변환 시작 시 **"변환 중 다른 곳에 타이핑 금지" 경고**를 1회 띄운다(세션당, `_typing_warned`).

### ⭐ 박스 그룹화 — `<조건>`/`<상자>` 뒤에 발문이 이어지는 패턴 (#18·#20)
- 증상: 셀(박스) 안에 `(가)(나)` 조건 **+ 그 뒤 문제 발문까지** 통째로 갇힘. 사용자 요구:
  **셀 안엔 (가)(나)[(다)(라)…]만, `(나)` 끝나면 줄바꿈 후 나머지 문제는 박스 밖**으로.
- 본질: OCR 은 박스를 **자기완결 한 raw 텍스트 블록**(마커+항목이 한 블록)으로 주고, 그
  **뒤 raw 블록**은 발문 연속(#20 `P(Y≤29)`+"의 값을…", #18 "m이 자연수일 때…"). 그러나
  `content_parser` 의 인라인 수식 분리 후엔 박스 항목 수식과 발문 수식이 **구별 불가**해진다.
- 해결(raw 경계에서 태그): `content_parser._raw_box_end` 가 자기완결 박스 뒤 발문 시작
  raw 인덱스를 찾아 **[발문+박스]와 [발문 연속]을 따로 파이프라인**(`_finalize_contents`)
  돌리고, 박스 마커 run 에 `ContentBlock.box_member=True`(`_tag_box_run`). 렌더러
  `hwp_com_writer._split_tail_post` 가 box_member run 뒤 블록을 **post(발문 연속)**로 떼어
  `_write_tail`/`_put_tail`(폼) 이 **박스 밖**에 렌더. **서술형 배점은 post 뒤로 미룬다**
  (`defer_essay_score`: 박스→발문연속→`[N점]` 우측정렬 순서). 기본·폼 경로 동일.
- 박스가 **마지막 raw 블록**이면(#12·#16) `_raw_box_end=None` → 분리 안 함(기존 동작). 항목
  개수 무관((가)(나)(다)(라) 다 같은 자기완결 블록).

### ⭐ 로만 vs 이탤릭 — 확통 연산자·확률변수는 이탤릭
- 과거 "대문자=무조건 로만"이 과해 **확통 기호 X·Y·P·E·V·N·Z 까지 로만화**됨(사용자: "이탤릭
  처리돼야 하는데 로만 처리된 게 너무 많아"). 해결: `_italicize_stat_operators`(+
  `latex_to_hwpeq._STAT_ITALIC_RE`, 표 셀용) 가 `\mathrm{X|Y|P|E|V|N|Z}`(아래첨자 없는 것)
  의 `\mathrm` 을 벗겨 이탤릭. **순열 `\mathrm{P}_`·조합 `\mathrm{C}` 는 로만 유지**(아래첨자
  부정전망). 점·선·면 다글자 기하 라벨(AB·ABC)은 여전히 로만(`_romanize_point_names`).
- **단위 오로만화**: `m`(모평균)·`t`·`s`·`h`·`L` 을 `_UNITS` 에서 제거 — "모평균 m"을 길이
  단위 m 로 보고 로만화하던 버그(사용자: "이건 너무한 거 아니냐"). 다글자 단위 + `g` + 기호만 유지.

### ⭐ 함수 괄호는 수식 안 — 단 `(x=1,2,3…)` 나열만 텍스트
- `f(x)`·`g(30)`·`P(Y≤29)` 의 괄호는 **수식 객체 안**에 둔다. **오직 정의역 나열
  `(x=0,1,⋯,50)` 만** 텍스트로 떼어 줄바꿈을 자연화(`_split_trailing_domain` +
  `_TRAILING_DOMAIN_RE`). `_MATH_ATOM` 에 함수호출 괄호 패턴 포함. 수식 직전 공백 없이
  붙은 식별자(P·f·X·숫자)는 수식 영역으로 끌어와 `P\!\left`→"P₩!" literal 샘 방지.

### 표 배경색(음영) — 수기본과 통일
- **표준정규분포표(z-표)** = colCnt==2 → **최상단 행(z, P(0≤Z≤z))** 음영. **확률분포표**
  = rowCnt==2 & colCnt≥3 → **1열** 음영. `hwp_com_writer._inject_table_shading`
  (`_shade_target_mode`) 가 저장 후 XML 에 `#D9D9D9` borderFill(레퍼런스 id=16 구조) 주입.
  기본·폼 경로 둘 다.

### 토큰/비용 로깅
- `gui/main_window._log_token_usage`: 시험지당 입력·출력·캐시 토큰 → 모델별 단가로 USD 계산,
  **KRW=USD×1500**. `[USAGE]` 로그 + `토큰사용.csv` 누적(시각·시험지·모델·토큰·USD·KRW).
  `OCREngine.usage`(`_accrue_usage`)가 `_stream_message` 마다 집계.

### `<조건>`/`<보기>` 라벨은 박스에 **인쇄됐을 때만** (OCR 프롬프트)
- OCR 이 발문의 "다음 **조건**을 만족" 같은 단어를 박스 헤더 라벨로 오인해 `<조건>` 을
  환각 주입하던 문제. 프롬프트 강화: 박스 **테두리 머리에 실제로 인쇄된** 라벨일 때만
  `<조건>`/`<보기>`, 없으면 `<상자>`. (캐시엔 옛 환각이 남아 있을 수 있음 → 재OCR 시 해소.)

## 폼 자동입력(form auto-fill) 구현 교훈 — 매우 중요 (2026-06-02, 긴 디버깅 끝에 확립)

대수회 폼지(.hwp)에 OCR 결과를 자동 채우는 작업. 설계/진행은 `docs/form_fill_plan.md` 참고.
프로토타입은 `D:\tmp\xml_v8.py`(= 측정기반 행정렬 최종). 정식 모듈(`core/hwp_form_writer.py`)로
옮길 때 **아래 함정들을 반드시 지킬 것**. 모르면 똑같이 며칠을 날린다.

### COM / 프로세스
- **고아 Hwp.exe가 비결정적 hang·RPC 오류의 주범.** COM 스크립트 실행 전 항상 `Get-Process Hwp | Stop-Process -Force`. 같은 증상이 한 번은 되고 한 번은 멈추면 십중팔구 고아 프로세스.
- **출력 .hwpx가 열려 있으면(사용자가 보고 있으면) `os.replace` 가 조용히 실패** → 변경이 "전혀 반영 안 됨". 매 빌드마다 **새 파일명**으로 출력하거나 사용자에게 닫게 한다.
- **라이브 COM 레이아웃 조작(DeleteBack 반복, 다수 BreakColumn + force_layout)은 불안정**(hang/RPC 크래시). 레이아웃은 **저장 후 XML 후처리**로 (결정적·무크래시).
- `KeyIndicator()` = (…, [3]=쪽, [4]=단, [5]=줄). 단 줄용량 실측 ~42이나 컨텍스트마다 다름.

### HWPX XML 후처리 (치명적 함정들)
- **단나누기 columnBreak는 `<hp:endNote>` 를 가진 "바깥 `<hp:p>`" 에 걸어야 먹는다.** 미주(endNote)는 `<hp:subList>` 안에 **중첩 `<hp:p>`(미주 내용)**를 가지므로, 정규식 `<hp:p\b.*?</hp:p>` 가 **안쪽 단락**을 잡는다. 거기에 columnBreak 걸면 본문 흐름에 무효(="columnBreak 무시됨"으로 오판). → `<hp:endNote>` 위치에서 `rfind("<hp:p ")` 로 **바깥 단락**을 찾아 그 여는 태그의 `columnBreak="0"→"1"`. (쪽나누기=`pageBreak="1"`.)
- **섹션 XML을 `findall + join` 으로 재조립하지 말 것.** 단락 사이의 **비-단락 요소(구역/단 정의 `secd`/`cold` 등)가 누락**되어 HWP가 **백지 렌더**한다. 반드시 **위치기반 편집만**(정확한 span 삭제/삽입, 속성 플립).
- 중첩 단락 안전을 위해 **endNote/table/equation 을 플레이스홀더로 마스킹**한 뒤 바깥 단락을 파싱하고, 끝에 언마스킹.
- **빈 단락 삭제로 채우기**: 빈줄을 빼고 균등 빈줄을 다시 넣는다. 단:
  - **빈줄 템플릿은 "섹션정의(secPr) 단락"을 잡으면 안 된다.** 첫 본문 단락은 secPr+중첩 `<hp:p>` 라 `<hp:p` 가 2개(불균형). 삽입하면 태그 깨져 백지. → `<hp:secPr` 없고 `<hp:p` 가 **1개뿐**인 **최단 빈 단락**을 템플릿으로.
  - **빈 단락 fabricate 금지**(직접 만든 lineseg는 파서가 거부). 문서의 진짜 빈 단락을 복사.
  - **`is_empty` 판정은 모든 태그 제거 후 텍스트로** 한다. 보기 단락은 `<hp:t>` 안에 `<hp:tab/>` 가 섞여 있어, `<hp:t>([^<]*)` 식 추출은 빈칸으로 오판→보기를 삭제해버린다. `re.sub(r"<[^>]+>","",p).strip()` 로 판정.
- 편집 후 **태그 균형 검증**: `<hp:p[ >]` 여는 수 == `</hp:p>` 닫는 수. 불일치=깨진 XML=백지.

### 레이아웃(N등분/행 정렬) — 사용자 요구
- 페이지당 객관식 3/단(최대 6/쪽), 서술형 2/쪽. **단 마지막 슬롯은 후행 여백 0**(단나누기로 다음 단). 문제는 짝수 쪽 마무리.
- **1단·2단의 같은 순번 문항이 같은 절대 줄에서 시작(행 정렬)** 해야 N등분처럼 깔끔. 구현: tight 빌드로 각 문항 실제 높이 + 각 단 시작줄 **측정** → `행높이=용량/행수`, 첫 행 빈줄 = `(최대단시작 + 행높이) − 자기단시작 − 높이`(열 시작 오프셋 보정), 이후 행 = `행높이 − 높이`, 단 마지막 = 0.
- 보기 정렬: 숫자 보기도 **수식 객체로 유지**(force_equation)해야 고정 탭에 정렬. 폼은 보기 ①②③④⑤·문항번호(미주 자동번호)가 사전배치 → 우리는 위치 찾아 채우기만.

### 짝수 쪽 마무리 + 정답(답지) 페이지 보존 (2026-06-03, 검증됨)
- **폼은 2섹션**(객관식=section0, 서술형+정답=section1, 경계는 슬롯14 `secd`)이나, **잉여 객관식 슬롯 삭제(중간)가 섹션 경계를 넘어 삭제 → 단일 section0로 병합**된다. 완성본(수기)도 단일 섹션·`pageBreak=0`·`columnBreak`만. 그래서 XML 후처리는 **section0 하나만** 다루면 된다(우연 아님, 병합이 정상 경로).
- **정답 페이지는 본문(list 0) 마지막 `gso`(그리기객체=답안표) 로 앵커**된다(머리말 로고 gso 는 para 0). 잉여 서술형 슬롯 삭제는 **이 gso 앵커 앞까지만**(`_answer_block_pos`); `MoveDocEnd` 까지 지우면 **정답 페이지가 통째 삭제**된다(과거 버그). 답안칸은 미주 자동번호라 문항수에 맞게 **자동 축소**(서술형 답안칸도 자동).
- **정답 블록 = `<hp:container>`**('정답' 텍스트가 그 안 `rect→drawText→subList→p` 에 있음, 표/gso 아님). XML 후처리 시 **container 를 가장 먼저 통째 마스킹**하고 그 placeholder 를 품은 **바깥 `<hp:p>` 에 `pageBreak="1"`** 를 걸어 새 페이지로. (단/쪽 나누기 전역 리셋은 **마스킹 후**에 해 정답 내부는 보존.)
- **짝수 보정**: 정답 pageBreak 빌드 후 COM 으로 정답 쪽 측정(`_measure_answer_page`, "정답" find). **짝수면 정답 앞에 `pageBreak` 걸린 빈 단락 1장**을 끼워 홀수로 민다 → 문제는 짝수쪽(4/6) 마무리, 정답은 5/7쪽(홀수). 빈 단락도 `_force_pagebreak` 로 만든다(빈 페이지 1장 = pageBreak 빈 단락 + 정답 pageBreak).
- 문항이 적어 문제가 홀수쪽에 끝나면 **빈 페이지가 생기는 게 정상**(양면 인쇄: 문제부=짝수 장, 답지=다음 홀수쪽 새 장).

### 슬롯 복사(grow) + 단일구역 병합 (2026-06-03, 검증됨)
- 이전 교훈의 "section0 하나만 다루면 된다"는 **반은 맞고 반은 틀림**: 잉여 객관식 삭제가
  구역 경계(슬롯14 secd)를 넘을 때만 단일섹션으로 병합된다. **14개 이상 객관식·슬롯 복사
  (삭제가 경계를 안 넘는 경우)는 2섹션으로 남아** `_build_layout`(section0 전용)이 서술형/
  정답 레이아웃·짝수쪽을 적용 못 한다. → **채움 전 `_merge_sections` 로 항상 단일구역화**.
- `_merge_sections`: **문서 시작의 초기 secd(para==0)는 못 지운다**(DeleteBack 무효). 실제
  구역나누기(**para>0**)만 골라 그 줄 시작에서 `DeleteBack` → 앞 구역과 합쳐짐. 폼엔 secd
  2개(초기+경계)라 para>0 필터 필수.
- **슬롯 복사**(`_copy_range`+`_paste_at`, COM Copy/Paste): 미주 포함 슬롯을 붙여넣으면 미주
  자동 재번호 → 번호 연속. 단 **COM Paste 는 비결정적으로 한 번 누락/오삽입**된다. range 로
  N번 세지 말고 **실제 개수 기반 while** 로(객관식=① 개수, 서술형=전체미주−①) 목표 도달까지
  반복(매 회 MoveDocBegin flush, guard 상한).
- **`_en_anchors` 는 반드시 (List,Para,Pos) 정렬**: HeadCtrl 연결리스트는 컨트롤 **생성 순서**
  라 Paste 한 미주가 리스트 끝에 붙어 문서순과 어긋난다. 채움/삭제가 위치 인덱스로 동작하므로
  정렬 안 하면 인접 슬롯 오삭제.
- **서술형 플레이스홀더 삭제는 다음 슬롯 앵커로 클램프**(`_fill_essay_at(next_pos=...)`):
  서술형 1/단 배치라 `MoveSelDown`(시각줄)이 단 경계를 넘어 **다음 단 슬롯의 미주까지 선택·
  삭제**한다(특정 배치에서만 발생). 다음 앵커 para 를 넘으면 MoveSelUp 으로 되돌리고 번호줄만.
- **정답 쪽 측정은 gso 앵커로**(`_measure_answer_page` → `_answer_block_pos`): 텍스트 "정답"
  find 는 **꼬리말 "(정답)"** 을 먼저 잡아 오측정 → 짝수 보정이 틀어진다. 정답 그리기객체
  앵커 위치 SetPos + KeyIndicator 로 정확한 쪽을 얻는다.
- 남은 cosmetic: grown 서술형의 답지 [서술형 N] 하위라벨이 어긋남(문제 번호는 정확).
- **서술형 라벨/소문항 마커 중복 — 결정적 후처리로 강제 해결**(2026-06-05): grow 서술형
  슬롯의 COM 라벨 삭제가 비결정적으로 실패해 폼 라벨이 남아 `[서답형 N] [서술형 N]` 중복.
  → COM 을 고치는 대신 **저장 후 XML `_dedupe_essay_labels`**: 뒤에 또 라벨이 오는 앞
  라벨(`[서…형 N] (?=[서…형)`)만 제거(같은 `<hp:t>` 안 매칭이라 태그 안전, 문제 길이·개수
  무관). 소문항은 OCR 이 `(1)`/`1)`/`1.`/`①` 마커를 본문에 포함해 우리 `(k)` 와 중복 →
  `_strip_leading_submarker` 가 sub 첫 텍스트의 앞머리 마커를 strip(데이터 단계, 결정적).

### ⚠️ 폼 경로 그림 — 두 모드 + 보안경고 해결 (2026-06-05, 사용자 결정)
**보안경고 해결**: 변환 문서를 한글에서 열면 HWP 가 "문서 손상/변조 가능 — 보안설정 낮춰야
열림" 경고를 띄움(원인=우리가 HWP 저장 **후** XML(레이아웃·라벨·머리말)을 고쳐 HWP 가
외부변경으로 감지). **해결 = `_com_relaunder`**: 후처리 뒤 HWP COM 으로 한 번 더 열어 다시
저장(HWP 가 최종 파일 직접 authoring → 경고 사라짐). `write_exam_to_form` 의 그림 비렌더 경로
마지막 단계.

**그림 두 모드**(GUI 체크박스 `_render_fig_check` → `write_exam_to_form(render_figures=...)`):
- **기본(False, 권장)**: 그림 자리에 안내 문구(`_FIGURE_NOTE`="※ 그림 자리 — 원본에서 이
  영역을 캡처해 여기에 붙여넣으세요", 평문 가운데 — `_place_figure_note`) + `_com_relaunder`
  → **경고 없이 열림**. ⚠️ 문구를 "[그림…" 으로 시작하면 HWP 가 그림 캡션으로 오인해 재저장 때
  사라짐 → "※…". 1×1 표 박스는 에세이 슬롯 COM 표 생성이 hang → 평문.
- **그림 렌더(True)**: `_embed_figures` 로 그림 실제 삽입 + **재저장 생략**(재저장이 그림 드롭)
  → 그림 보이나 **보안경고 뜸**.
- 분기: `_fill_form(render_figures=)` 가 `ses._render_figures` 세팅 → `_place_figure` 가
  `_place_figure_embed`(pic+토큰) vs `_place_figure_note`(안내) 선택.
- **그림 native 삽입(렌더 모드도 경고 없이)은 추후 숙제**: 재저장이 우리 삽입 그림(COM·XML
  무관)을 드롭. COM `InsertPicture` 를 HWPX 로드 세션에 하면 native 로 재저장 생존하나, 그
  세션에서 그림 위치 찾기 막힘(HWP COM Find 가 폼 본문 특정 단락 못 찾음, 컨트롤 순회도 안 됨).
  상세: 메모리 `form-figure-pending`.

### 폼 경로 그림 임베드 (2026-06-05, 이전 시도 — 현재 미사용, 추후 숙제 참고용)
대수회 폼에 문제 내 그림(SVG 재생성/크롭 PNG)을 채울 때의 치명적 함정과 해결. 상세 메모:
`form-figure-embed`. (아래 `_embed_figures` XML 방식은 렌더는 되나 재저장에 드롭돼 현재 미사용.)
- **COM `InsertPicture(Embedded=True)` 는 HWPX SaveAs 시 새 binItem 을 안 만들고 폼의 기존
  binItem(머리말 배너 `image1`)을 재사용**한다 → 삽입한 그림 자리에 **배너가 표시**됨. 저장된
  section XML 의 삽입 pic 이 `binaryItemIDRef="image1"`(배너) 로 찍힌다. (BMP/PNG 무관.
  빈 새 문서면 정상 임베드되나 폼처럼 binItem 선점 시 충돌.)
- 해결 = **저장 후 XML 후처리**(`_embed_figures`, 라이브 COM 금지 교훈과 동일):
  `_insert_picture_inline` 가 그림 **바로 앞**에 토큰 `⟦F{idx}⟧` 텍스트를 찍고 경로를
  `ses._fig_paths` 에 등록 → 레이아웃 후 `_embed_figures` 가 토큰 다음 pic 의 첫
  `binaryItemIDRef` 를 새 `imageN` 으로 교체 + PNG 를 `BinData/imageN.png` 임베드 +
  `content.hpf` `<opf:manifest>` 에 `<opf:item … isEmbeded="1"/>` 등록(이 폼은 header.xml 에
  binDataList 없음) + 토큰 제거. orgSz 는 COM 이 실제 픽셀로 맞추므로 불변, 그림은
  `_fit_image_width`(260px≈69mm)로 단 너비 안에 축소.
- 토큰은 인라인 pic 단락(보이는 텍스트 없음)이 `_build_layout` 빈줄삭제(`is_empty`)에 지워지지
  않게 **보호**하는 역할도 한다. `Question.score` 는 **int**(=`_put_score` 가 `점` 1회만 부착).
