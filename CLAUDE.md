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
8. **표 캡션(표 제목) = 줄바꿈 후 우측정렬**(2026-06-10) — 배점과 같은 줄 금지("[5점]어느
   마트…" 금지). 캡션이 TEXT+EQ 여러 런으로 쪼개져도(`나이(1|6은 16세)`) `_caption_spans` 가
   run 결합으로 판정, `_write_caption_run` 이 우측정렬 렌더. 표는 새 단락+좌측 명시.
9. **배점 우측정렬 폴백은 삽입분(sp→ep)만 선택-삭제**(2026-06-10) — `MoveSelParaEnd` 금지.
   마지막 서술형에서 표 탈출(`SetPos(para+1)`)이 캐럿을 폼 **정답 단락**에 착지시켜 이후
   본문이 그 안에 타이핑되는데, MoveSelParaEnd+Delete 가 정답 블록 앵커 문자(답안표
   gso·container)까지 삼켜 **정답 페이지가 통째 증발**했다(강동중 #20 sub(2) [4점]).
10. **표 셀 공백 다중값("6 8"·"12 ~ 18") = 토큰별 수식 객체 + 사이 공백 평문**(2026-06-10) —
   통수식은 HWP 가 공백을 죽여 "68"로 붙고, 통평문은 합의 #5(수식 객체) 위반(잎 글꼴 불일치).

## 자가발전 corpus 검수 프로토콜 (구독 요금제, API 0원)

외부 API 없이(Claude Code 세션 내 비전으로) 시험지를 crop→OCR→렌더→검수해 **품질 코퍼스**를
쌓는다. 표준 절차·함정·규약은 **`corpus/REVIEW_PROTOCOL.md`** (반드시 따를 것). 산출물은
`corpus/<시험지>/`(`crop/crops.json`·`ocr/p{n}_merged.json`·`meta.json`) — JSON 은 git 추적,
PNG 는 gitignore(재생성 가능).

**철칙(중앙고 2026-06-10 에서 비싸게 배움)**: ① **"렌더 안 깨짐 ≠ 정상"** — 반드시 원본 크롭과
**문항별 1:1 비전 대조**(렌더만 훑어 결함 11건 놓침). ② JSON 규약위반(A)을 코드버그(B)와
분리해 A 먼저 제거 후 재렌더(순수 B만 디버깅). ③ 결함은 가려져 있다 — 하나 고치면 새 결함
드러남, **매번 전수 재렌더·재대조**. ④ COM 비결정적(메타란 토큰 run·캐럿) — 비결정 결함은
**3회+ 렌더**로 확인.

**자동 게이트**: `python scripts/corpus_lint.py --json <ocr_dir>`(JSON 규약)·`--xml <hwpx>`
(메타토큰·자모혼입·라벨혼재·정답증발·배점중복). FAIL=차단, WARN=알려진 한계. **단 lint PASS
가 정상은 아님** — 위치·레이아웃 결함은 비전 대조로만 잡힌다(lint 는 1차 게이트).

## OCR 백엔드 다중화 + 품질 자동 라우팅 (2026-06-16, 구현·검증 완료)

배포 exe 의 OCR 을 **Claude 단일 → 품질 기반 3단계 자동 분기**로 다중화(비용 5~7배↓). 분기점은
`core/ocr_engine.OCREngine._stream_message` **단 하나** — 그 아래(`recognize_page/crop`·`_transcribe`·
`_recover_table`·`_extract_json`·`_accrue_usage`)는 전부 모델 무관 재사용. Gemini 응답은
`_GeminiMessage`/`_GeminiUsage` 가 Anthropic Message 형태(`.content[0].text`·`.stop_reason`·
`.usage`)로 감싼다. `_stream_message(..., json_mode=)` 로 JSON 모드(`response_mime_type`) 분기 —
전사(`_transcribe`/`_transcribe_table`)만 평문(False).

- **라우팅(GUI 워커, 크롭검출=문제 유무 확정 *후* 페이지별)**: born-digital(텍스트레이어/벡터)
  **또는** 고QC(`QC_CLEAN_SCORE`≥70) → `gemini-3.5-flash`(클린·저렴), 아니면(스캔/저품질=손글씨
  가능) → `gemini-3.1-pro-preview`(충실도·보수적). ⚠️ **스캔 원본은 born=False**(만덕고도 img=1)
  → **QC 점수 폴백이 클린 스캔을 flash 로 보내는 핵심 라우터**(검증: 클린 QC100→flash, 흐림
  QC60→pro). config `OCR_BACKEND`("auto"|"claude"|"gemini-pro"|"gemini-flash") + GUI 드롭다운으로
  override. Gemini 키 없으면 Claude 폴백(1회 경고).
- **제약(사용자 강조)**: ① 품질-차단은 **문제 페이지에만**(표지·답지=크롭0 자동 스킵=별개 축).
  ② **페이지 차단 ≠ PDF 차단**(한 장 불가→그 장만 스킵, 전 페이지 불가→PDF 거부). Gate1 문구
  "OCR 불가 — 이 페이지만 건너뜀(변환은 계속)"로 명확화.
- **⭐ 자가발전(corpus)·ocr_eval 은 Sonnet 고정(사용자 2026-06-16)** — 전 reviewed corpus 가
  Sonnet 베이스라인 + 결정적 후보정으로 구축됐다. 같은 모델로 계속 돌려야 후보정 회귀가 비교
  가능("비슷한 효과"). 그래서 **`OCREngine` 기본 backend="claude" 는 config `OCR_BACKEND` 를
  honor하지 않는다(의도)** — 직접 인스턴스화하는 `scripts/testkit.py`·`scripts/ocr_eval/score_ocr.py`
  는 `backend="claude"` 명시. **Gemini 자동 라우팅은 배포 GUI(`gui/main_window`) 한 곳만.**
  corpus_render(소비자)는 캐시 렌더라 OCR 자체가 없어 무관. (메모리 `ocr-engine-quality-routing`.)
- Anthropic 키 **선택사항화**: auto/Gemini OCR 은 Gemini 키만 있으면 됨(둘 중 하나 이상 필요).
  크롭 검출은 종전대로 항상 Gemini Flash(별개, `crop_detector._detect_with_gemini`).

## 작업 마무리 워크플로우 (필수)

코드를 변경한 뒤에는 **항상 아래 순서로 마무리**한다:

1. **검증** — 변경을 실데이터/렌더로 확인(가능하면 HWP COM 렌더 PNG로 육안 확인).
2. **사용자 최종 체크** — 커밋·푸시·배포 전에 **반드시 사용자에게 결과를 보여주고 확인(체크)을 받는다.** 사용자 승인 없이 커밋/푸시/배포하지 않는다.
3. **커밋 + 푸시** — 승인되면 커밋하고 **`testchange` 원격(BIGSHOL)** 으로 푸시한다 (`git push testchange master`).
4. **exe 빌드 + 배포** — `python -m PyInstaller build.spec --noconfirm` 로 재빌드하고, `dist/시험지한글화/` 의 exe와 `_internal` 을 `배포용/` 으로 복사한다. **`배포용/config.json` 은 보존**(robocopy `/MIR` 는 `_internal` 에만 적용). 배포 후 `--selftest` 로 임포트 확인.

### 보안 (절대 준수)
- **API 키(ANTHROPIC/GEMINI)는 gitignore된 `config.json` 에만** 둔다. 추적 파일·커밋에 키를 절대 넣지 않는다. (`config.json`, `build/`, `dist/`, `배포용/` 은 `.gitignore` 처리됨.)

## Codex 인계 — Claude 사용량 소진 후 미커밋 변경 검증 (2026-06-10)

Claude Code가 사용량 소진으로 중단된 뒤 Codex가 기존 dirty worktree를 이어받아 코드/테스트를
검증하고 핸드오프 문서화했다. 이번 묶음은 **소스·테스트·문서 커밋까지만**이며, 이 PC의 HWP COM
시작 오류 때문에 새 exe 빌드/배포는 아직 하지 않았다.

주요 변경 범위:
- `content_parser.py`: 소수/총점 배점 캡처, `[총 N점]` 제거/복원 동기화, raw 박스 spill 방지,
  기하 문맥에서 stat-이탤릭 스킵, `\le/\ge/\ne` 명령어 경계, 단일 수식 블록 평문 강등 방지.
- `latex_to_hwpeq.py`: 중첩 `\left...\right` 최내곽 고정점 치환, `45^\circ` 같은 brace-less 첨자
  보호, `\setminus` 연산자 증발 방지.
- `ocr_engine.py`: usage 집계 락, 빈 message content 방어, 닫는 코드펜스 없는 JSON 복구,
  비-dict question 방어.
- `hwp_com_writer.py`/`hwp_com.py`/`hwp_form_writer.py`: 조건박스 무한재귀 방지, HWPX zip 재작성
  공통화와 tempfile 정리, 표 음영 멱등화, HWP Open/SaveAs/PDF 절대경로화, 저장 침묵 실패 감지,
  폼 grow 실제 개수 기반 진행, 측정용 HWP finally Quit, essay label dedupe 시 lineseg 보존.
- `gui/main_window.py`: 부분 캐시 완결 마커 경고, 기록 폴더 reset 시점 지연, 변환 중 창 닫기 취소.
- 테스트: `tests/test_extract_json.py` 추가, `test_content_parser.py`/`test_render_fixes.py` 보강.

검증 완료(키 0):
```powershell
.venv\Scripts\python.exe tests/test_content_parser.py
.venv\Scripts\python.exe tests/test_render_fixes.py
.venv\Scripts\python.exe tests/test_extract_json.py
.venv\Scripts\python.exe tests/test_equation_metrics.py
.venv\Scripts\python.exe scripts/verify_output_format.py --all
.venv\Scripts\python.exe -m compileall core gui scripts tests
```
추가 수동 확인: `verify-latex-hwpeq` 핵심 regex/`\mid`, `verify-hwpx-structure` NS 동일성,
`verify-ocr-parser-sync` 주요 parser regex 모두 PASS. `pytest` 는 `.venv` 미설치라 실행 못 함.

실데이터 캐시 렌더 시도:
```powershell
.venv\Scripts\python.exe scripts/testkit.py `
  "N:\개인\기출\기출작업\194차\[학남고][2][확통][25-2-기말][미래엔] (원본).pdf" `
  ".testkit\codex_after_claude.hwpx" --render-only
```
`loaded 6 pages`, `crops: CACHE`, `OCR: 21 cache, 0 api-call` 까지 정상. 이후
`win32com.client.Dispatch("HWPFrame.HwpObject")` 단계에서 로컬 HWP 2020이 크래시해 HWPX/PNG 렌더는
미완료. 다른 PC/재부팅 후 아래 COM smoke test부터 재시도:
```powershell
Get-Process Hwp,WerFault -ErrorAction SilentlyContinue | Stop-Process -Force
python -c "import win32com.client; h=win32com.client.Dispatch('HWPFrame.HwpObject'); h.Quit(); print('OK')"
```
성공하면 위 `testkit.py ... --render-only` → `scripts/render_to_png.py` → 사용자 육안 체크 →
PyInstaller 빌드/배포 순서로 이어간다.

현재 로컬 COM 블로커의 실제 관찰:
- `Dispatch("HWPFrame.HwpObject")` = `CO_E_SERVER_EXEC_FAILURE(0x80080005)`.
- Windows 이벤트 로그: `.NET Runtime` `System.UriFormatException`,
  `MS.Internal.FontCache.Util..cctor()` → `CultureFontManager.GetPrivateFont()` → `Hwp.HwpAppMain.InitApp()`.
- 직접 `hwp.exe -Automation`/`-Embedding` 단독은 뜨지만, `hwp.exe -Automation -Embedding` 조합은 같은
  FontCache 크래시. COM이 등록된 `LocalServer32 = hwp.exe -Automation` 에 `-Embedding` 을 붙이는
  경로로 보여 이 조합이 로컬 원인.
- HKCU CLSID override 실험은 효과 없어 원복 완료. HNC 폰트 캐시 3개는 `.codexbak_20260610_115155`
  로 백업해두었고 일부는 HWP가 재생성했다. 필요하면 새 파일을 치우고 백업명을 원래 이름으로 복원.

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
- ✅ **객관식 표 누락도 복구됨**(v0.1.8 `a21db42`): `ocr_engine._recover_table` — 결과에 table
  블록이 없고 본문/선택지에 표 지시어(`_TABLE_HINT_RE`: 확률분포표·정규분포표·`P(X=x)`·`z의 값`
  등)가 있으면 **표만 마크다운으로 전사**(`_transcribe_table`)해 `_parse_markdown_table`로 rows
  파싱 후 `questions[0].contents` 끝(발문 뒤·선택지 앞)에 끼운다. 지시어 게이트라 평소엔 추가
  호출 없음. 결정적 경로(게이트·파싱·삽입) 회귀: `tests/test_table_recovery.py`(stdlib·키 0).
  실모델 전사 충실도 검증만 키 필요. (학남고 #3·#4·#10 표는 현 캐시에서 온전히 잡힘 — 검증됨.)
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

## 강동중 정답 페이지 증발 — 캐럿 침범 연쇄 (2026-06-10, 긴 bisect 끝에 확정)

강동중 중1(객관식 16+서술형 4) 캐시 렌더에서 **정답 페이지(답안표 gso·'정답' container·
pageBreak)가 통째 사라진** 회귀. COM 실험은 **캐럿 상태가 실험을 오염**시키므로(아래), 격리
재현 + 단계 bisect 로 잡았다. 합의 #8~#10 으로 강제(verify 30개).

- **파괴 연쇄**: 마지막 서술형(#20)의 tail 표 렌더 후 표 탈출(`table_end` 의
  `SetPos(para+1)`)이 캐럿을 **정답 단락 pos 0** 에 착지 → 이후 모든 본문(소문항 (1)(2))이
  정답 단락 **안**에 타이핑되며 앵커 문자들을 밀고 다님 → 소문항 (2) 배점 `[4점]` 이 줄넘침
  → 우측정렬 폴백의 `MoveSelParaEnd`+Delete 가 캐럿 뒤 **정답 앵커 문자 20자**까지 선택-삭제.
- **수정**: 폴백 4곳(`_write_score_inline_or_right`·`_write_total_score_inline_or_right`·폼
  `_put_score`·`_put_total_score`) 전부 **삽입분(sp→ep)만 `SelectText` 로 선택-삭제**. 본문
  타이핑은 항상 앵커 **앞** 삽입이라, 과잉삭제만 막으면 마지막 break_para 후 앵커가 자기
  단락에 남아 **자가 치유**된다(별도 분리 복구 불필요 — 검증됨).
- **COM 실험 함정 2개**(이것 때문에 두 번 오진): ① `RepeatFind` 가 캐럿을 컨트롤 subList(list
  44)로 옮긴 채 `SelectText` 하면 본문(list 0)이 아닌 그 리스트에서 동작 — probe 의 find 가
  실험을 오염. ② `save_hwpx` 가 캐럿을 문서 처음으로 리셋 — 중간 스냅샷 찍으면 이후 쓰기가
  엉뚱한 위치로. **격리 재현은 캐럿을 안 움직이는 probe(컨트롤 순회)로만**.
- 트리거 조건이라 다른 시험지(경운중·학남고)에선 안 보였다: **마지막 서술형 + tail 이 표로
  끝남 + 그 뒤 배점이 줄넘침** 셋이 겹쳐야 발화.
- 같은 세션: 표 캡션 우측정렬(합의 #8)·잎 셀 토큰별 수식(합의 #10)·타이핑 혼입 검출(아래).

### ⚠️ 변환 중 사용자 타이핑이 숨김 COM 문서로 샘 (재확인)
`CONVERSION_VISIBLE=False`(숨김)여도 **변환 중 사용자 키 입력이 변환 문서에 혼입**될 수 있다
(실측: #1 배점 뒤 `ᅟᅡᆫ ㅁ` 낱자모). 렌더/변환 중에는 타이핑 금지 안내가 필수(GUI 경고 유지).
검출법: 출력 XML `<hp:t>` 에서 자모 영역(U+1100-11FF·U+3130-318F) grep.

## 폼 자동입력(form auto-fill) 구현 교훈 — 매우 중요 (2026-06-02, 긴 디버깅 끝에 확립)

대수회 폼지(.hwp)에 OCR 결과를 자동 채우는 작업. 설계/진행은 `docs/form_fill_plan.md` 참고.
프로토타입은 `D:\tmp\xml_v8.py`(= 측정기반 행정렬 최종). 정식 모듈(`core/hwp_form_writer.py`)로
옮길 때 **아래 함정들을 반드시 지킬 것**. 모르면 똑같이 며칠을 날린다.

### COM / 프로세스
- **고아 Hwp.exe가 비결정적 hang·RPC 오류의 주범.** COM 스크립트 실행 전 항상 `Get-Process Hwp | Stop-Process -Force`. 같은 증상이 한 번은 되고 한 번은 멈추면 십중팔구 고아 프로세스.
- **2026-06-10 현재 이 PC 로컬 HWP COM 시작 블로커**: `Dispatch("HWPFrame.HwpObject")` 가
  `0x80080005` 로 실패하고 이벤트 로그는 `MS.Internal.FontCache.Util`/`System.UriFormatException`.
  직접 `hwp.exe -Automation -Embedding` 이 같은 크래시를 재현한다. 코드/캐시 렌더는 HWP 시작 전까지
  통과했으므로 다른 PC/재부팅 후 COM smoke test를 먼저 실행하고, 성공하면 `testkit --render-only`
  부터 이어간다. 자세한 인계는 `docs/HANDOFF.md` §6-b/6-c 와 메모리 `codex-handoff-hwp-com-20260610`.
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
- ~~남은 cosmetic: grown 서술형의 답지 [서술형 N] 하위라벨이 어긋남~~ **해결(2026-06-10,
  상인고 #25)**: grow 슬롯 복사가 마지막 답지 라벨을 ``[서술형 5]``(6이어야)로 굽고, COM
  비결정성으로 본문/정답 중 어느 쪽이 어긋나는지 렌더마다 뒤바뀜. → 저장후 XML
  ``_renumber_essay_labels`` 가 모든 ``[…형 N]`` 라벨(번호=수식 객체 `<hp:script>`)을 **문서순
  (본문,정답) 쌍**으로 1,1,…,n,n 결정적 재부여(라벨 수 ≠ 2×서술형수면 오손상 방지로 생략).
  라벨 단어 통일(`_sync_essay_label_word`) 직후·`_com_relaunder` 전. 회귀: `test_render_fixes.py`(H).
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

## 학남고 확통 — 워드본 1:1 리뷰 14건 (2026-06-09, 커밋 a33013e·e2f145e)

`배포용/ocr`·`배포용/crop` 영구기록(`temperature=0` 결정적 OCR) 기반 **캐시 재렌더(API 0원)**로
1:1 비교하며 잡은 결함들. 전부 **결정적 후보정**. 회귀 방지: `verify_output_format.py`(28).

### 지수·단위 (latex_to_hwpeq)
- **유니코드 위첨자 = 지수 객체화**: OCR 이 `N(m, 2²)` 처럼 유니코드 위첨자(`²³¹⁰⁴…`)를 주면
  HWP 가 작은 ² 글자로 렌더(지수 아님). `_normalize_unicode_superscripts` 가 `2²`→`2^{2}`.
- **단위 `\text{g}` 정자화**: `20\text{g}`→`20"g"`(따옴표 리터럴)는 간격이 안 붙는다.
  `_unwrap_text_units` 가 `\text{<단위>}`→평문 단위로 풀어 뒤의 `_romanize_units` 가 `20 rm\`g`.
- **유니코드 부등호**: `≤ ≥ ≠`→`\leq \geq \neq` (convert 전처리). OCR 이 `\leq` 대신 유니코드로
  주면 리터럴 ≤ 로 새고 연산자 간격이 깨진다.
- **쉼표 강제공백이 백틱도 매칭**: `N(m,\, 4σ²)` 의 `\,`(얇은공백)은 변환 후 `,`+백틱(1/4칸)이
  돼 `,[ \t]+` 가 못 잡았다 → `,[ \t\`]+`→`,~` 로 백틱 포함(좌표형 정규분포 `N(m,~4σ²)`).

### 로만 vs 이탤릭 — 문맥 기반 (content_parser + latex_to_hwpeq `italicize_stat`)
- **본문 stat-이탤릭은 content_parser 가 전담**: `latex_to_hwpeq(…, italicize_stat=False)` 추가.
  본문은 `_italicize_stat_operators` 가 이미 확통 `\mathrm{P/E/V/N/Z/X/Y}` 를 벗겼으므로, 남은
  `\mathrm{P}` 는 **기하 점 P**(점 P·꼭짓점 A)다 → latex_to_hwpeq 가 다시 벗기면 안 됨. 표 셀은
  content_parser 를 안 거치므로 기존대로 `italicize_stat=True`(이탤릭화). 본문 호출처(`_eq_script`
  ×2)만 False.
- **비기하 단일 대문자 이탤릭화**: `_italicize_nongeo_single_letters` — 기하 문맥이 **아닐 때만**
  단일 대문자 `\mathrm{A}`(체스 선수 A·B, 사건 A) 를 이탤릭으로. **조합 C·순열 P_(아래첨자)는
  로만 유지**, 기하 문맥(점·꼭짓점…)이면 `_romanize_point_names` 가 로만 유지.
- ⚠️ **배점 "점"이 기하 키워드 "점"과 충돌**: `[4.3점]` 의 "점" 때문에 `_has_geometry_context`
  가 비기하 문제를 기하로 오인 → A·B 로만 잔존. **`_strip_score_text` 를 기하 판정 앞으로** 옮겨
  해결. (배점이 수식으로 쪼개진 `[`+EQ+`점]` 은 `_strip_split_score` 가 제거 — score 필드와 중복
  방지, #15 `[4.3점]` 두 번.)

### 수식 분리/병합 (content_parser)
- **text(꼬리부등식)·eq·text(머리부등식) 병합**: OCR 이 `-1 ≤ x ≤ 1에서` 를 `text("-1 ≤ ") +
  eq("x") + text(" ≤ 1에서")` 로 쪼개면 `-1` 만 평문(정자)·`x` 만 이탤릭. `_merge_text_eq_fragments`
  가 꼬리/머리의 미완성 부등식을 인접 수식에 흡수해 `-1 ≤ x ≤ 1` 한 객체로(유니코드 부등호는
  `\leq` 로 정규화).
- **LaTeX 없는 ASCII 수식도 분리**: `_split_latex_commands` 가 백슬래시 없으면 평문 반환하던 것 →
  `_split_mixed_text_equation` 위임. 박스 `(가) … \leq … • (나) f(20) = g(30)` 의 (나)처럼 앞
  항목이 `\leq` 로 수식화돼 재귀로 넘어온 ASCII 수식이 평문화되던 것 해결.
- ⚠️ **`len(expr) > 20` 필터가 긴 수식을 평문화**: `_split_mixed_text_equation` 의 긴-영문단어
  방어 필터가 `P(X ≤ 15) ≤ P(Y ≥ 30)`(21자)를 단어로 오인 → 박스 (가) 평문. **연산자
  `[=<>≤≥≠+\-×÷^_]`·괄호가 있으면 길이 무관 수식 유지**.
- **한글↔수식 띄어쓰기**: `_space_hangul_before_eq` — 한글로 끝나는 TEXT 바로 뒤 EQ 사이 공백
  (`확률을p_1`→`확률을 p_1`). 수식은 새 기호라 앞 공백; EQ 뒤 한글은 조사(`p_5이라`)라 안 건드림.

### 박스 그룹화 (content_parser `_raw_box_end`)
- ⚠️ **OCR 이 보기 박스를 여러 raw 블록으로 쪼개면**(`<보기> ㄱ.` + 별도 수식블록 + `• ㄴ. …`)
  `_raw_box_end` 가 `<보기> ㄱ.`(라벨만)을 **완결 박스로 오인**해 ㄴㄷㄹ 를 "발문 연속"으로 떼어
  박스 **밖**으로 보냈다(#14). **마커 뒤가 항목 라벨 단독(`_BARE_ITEM_LABEL_RE`)이면 자기완결
  아님** → 분리 안 함(박스가 다음 블록으로 이어짐). 박스가 한 raw 블록에 다 든 경우(#16)는 정상.

### 파일명 충돌 (gui/main_window)
- 출력 파일이 이미 있으면 덮어쓰기 확인 대신 **윈도우식 `(1)(2)…` 자동 증가**(`_unique_output_path`).
  기존 변환물 보존 + 재변환 비교 편의(사용자 요구).

## 경운중 중3 (폼) 리뷰 — 라벨·메타·박스 4건 (2026-06-09)

대수회 **중3 폼**(이차방정식) 변환을 워드본과 비교해 잡은 폼 경로 결함. 캐시 재렌더(API 0원).

### 서술형 라벨 중복 `[서답형 N] 【서답형 N】` — OCR 괄호 혼용
- OCR 이 같은 시험지에서 라벨을 ``[서답형 N]``(대괄호)·``【서답형 N】``(렌티큘러) **혼용**한다.
  우리 라벨-제거 정규식(`_ESSAY_LABEL_LEAD`)이 ``[]`` 만 잡아 ``【】`` 는 본문에 남아 우리 라벨과
  중복. **양쪽 괄호 `[\[【]…[\]】]` 매칭 + 추출 라벨을 `[서답형 N]` 로 정규화**. dedup(`_DUP_LABEL_RE`)도
  ``【】`` 포함(방어). 분리형 ``[서답형 ``+EQ+``]`` 의 여는/닫는 괄호도 양쪽 허용.

### ⭐ 소단원 메타란 토큰 평문 leak — 토큰 자기-오인
- 서술형 끝 ``[소단원][난이도]`` 는 토큰(`소단원자리표식QZX`·`난이도자리표식QZX`)을 찍고 저장 후
  `_inject_essay_meta` 가 **살아있는 폼 메타란 run** 으로 교체한다. 그런데 **이 폼은 `[난이도]`만
  있고 `[소단원]` 템플릿이 없다** → 템플릿 탐색 `next(p for p if "소단원" in p)` 가 **토큰 단락 자신**
  (``소단원자리표식QZX`` 도 "소단원" 포함)을 템플릿으로 오인 → 자기 자신으로 교체(no-op) → 평문 leak.
- 해결: ①템플릿 탐색에서 **토큰 단락 제외**(`_META_TOKEN_SO not in p`) ②템플릿이 없으면(run is None)
  **토큰 단락을 통째 제거**(평문 노출 방지, linesegs 는 `_com_relaunder` 재계산). → 폼에 있는 메타만
  주입, 없는 건 깔끔히 삭제. (객관식은 폼 native 메타라 정상, 서술형만 토큰 경로였음.)

### 조건/보기 박스 첫 줄만 들여쓰기 — 라벨 뒤 선행공백
- `_write_box_content`(`hwp_com_writer`): `<조건>`/`<보기>` 라벨 뒤 **첫 항목만** 선행 공백이 안 깎여
  한 칸 들여써졌다(2번째부터는 `•` 불릿이 `\s*…\s*` 로 양옆 공백을 흡수해 flush). 라벨 처리 분기에서
  `after_label=True` 로 바꿔 **첫 내용도 lstrip** → 모든 항목 flush.

### 조건/보기 박스 동그라미 크기 제각각 — OCR 불릿 글자 혼용
- OCR 이 항목 불릿을 ``ㅇ``(한글 이응 U+3147)·``○``(흰 원 U+25CB)·``●``·``〇`` 등으로 혼용 → 글자가
  달라 크기 제각각. `content_parser._normalize_box_circles` 가 **단독 원형 불릿**(앞뒤 공백)을 표준
  ``○``(상수 `_BOX_BULLET`)로 통일. **`∘`(합성연산자)·라틴 o/O·키릴 О 는 제외**(수식·기하 점 O 오치환
  방지). 더 작은 글자 원하면 `_BOX_BULLET` 상수만 변경.

## 완료본 기반 corpus 검수 시리즈 — 상인고 공수1·수1 + 능인고 수1 (2026-06-10)

3단계 사람검수 **완료본(정답지)을 직접 판독해 OCR JSON 을 만들고**(입력 노이즈 0) 우리
파이프라인으로 렌더 → 완료본과 1:1 대조하는 검수(절차 = `corpus/REVIEW_PROTOCOL.md`).
고1 공수1(`22266a1`)·고2 수1 상인고(`f3ed2eb`·`f4225ec`)·고2 수1 능인고(`a7d58c3`, 타학교
교차검증). 전부 결정적 후보정 + 회귀 테스트(`test_content_parser` 15·`test_render_fixes`).

### 빈칸채우기(수학적 귀납법 증명 등) = `\boxed{}` → HWP `BOX{ ~ … ~ }`
- 원본의 작은 테두리 빈칸 `(가)(나)(다)` 는 OCR 이 ``\boxed{가}`` 로 주고, latex_to_hwpeq 가
  ``BOX{ ~ ㈎ ~ }``(괄호한글 단일문자 U+320E)로 변환. **`BOX` 를 `_roman_skip` 에** 추가해야
  ``rm {BOX}`` 글자 깨짐이 없다. 식이면(``\boxed{f(k)}``) 일반 변환으로 내용 렌더.
- `\bigstar`→`"★"` 리터럴(`\square`→□ 방식). 매핑 없으면 ``(★)`` 이 ``()`` 로 증발.

### 소문항·연산자·한글 경계 (content_parser)
- **(i)(ii)(iii) 괄호 통째 한 수식**(`_SUBMARKER_RE`) — 사용자: "소문항은 항상 수식처리".
  `f(i)` 함수호출은 앞 영숫자 lookbehind 로 보존.
- **선행 연산자 흡수**: ``= - \frac…`` 의 ``= -`` 를 수식에 포함(음수부호가 평문으로 떨어져
  큰 간격 생기던 것). `_split_latex_commands` 가 명령어 앞 연산자+공백을 끌어옴.
- **중괄호 밖(depth 0) 한글 = 수식 종료**: ``k \geq 2이므로`` 의 "이므로" 누수 차단.
  ``\boxed{가}``(중괄호 안 한글)는 보호. 한글 앞 여는 괄호는 텍스트 쪽으로(``(우변)`` 보존).
- **`_MATH_ATOM` 확장**: ① LaTeX 첨자 brace ``_{n+1}`` 흡수(``2a_{n+1}=a_n+a_{n+2}`` literal
  중괄호 노출 방지) ② **괄호base 원자** ``(1+h)^n``(능인고 #18 — ``)^`` 분해로 ^ 캐럿 노출 방지).
- **각(angle)=도형=로만**: `_romanize_angle_letters` — 삼각함수 인자(``\cos A``)·각도
  (``A=45^\circ``)·``\angle A`` 의 단일 대문자만 ``\mathrm``. 변 a,b(소문자·길이)는 이탤릭 유지.
- **점화식 뒤 범위 ``(n=1,2,3⋯)``**: `_merge_paren_range` 가 앞 수식에 ``~``(HWP 공백) 병합.

### 박스/레이아웃 (hwp_com_writer · hwp_form_writer)
- **라벨 없는 셀 = 가운데정렬**: `_is_labelless_box`(항목라벨·불릿 없는 ``<상자>``, #14 단일
  진술) → 셀 안 가운데. (가)(나)/ㄱㄴㄷ/<보기> 박스는 좌측 유지.
- **거대 문항 단독 단(R4)**: 내용기반 추정(`_estimate_mc_heights`) ≥ `_SOLO_MC_LINES`(18줄)
  객관식은 `_adaptive_columns(solo=)` 가 **한 단에 혼자**(앞뒤 단나누기). 귀납법 증명박스
  (#12, 추정 24줄)가 3/단 슬롯을 넘쳐 캐스케이드 나던 것 해소. COM 실측은 거대 박스를
  과소측정(15 vs 24)하므로 **solo 판정은 추정으로**.
- **서술형·단답형 혼합 시험지**(능인고 16~18 서술형 + 19~20 단답형): 라벨을 한 단어로 강제
  통일하면 본문 중복(`[서술형 4][서술형 4]`)+정답면 오표기. → `_DUP_LABEL_RE` 에 단답형 추가,
  `_renumber_essay_labels(words=문항별유형)` 가 정답 라벨(폼 native 는 전부 [서술형])을 쌍
  essay 인덱스로 본문 유형에 맞춤. 균일 시험지만 `_sync_essay_label_word` 단일 통일.
  lint 도 서술형·단답형 혼합 허용(서답형/서술형 **철자 혼용**만 경고).

### 검수 중 비전 대조 함정
- "렌더 중 사용자 타이핑 혼입"(낱자모 잡토큰)은 코드 결함 아님 — 재렌더로 확인(jamo grep 0).
- 완료본 판독 시 #12 같은 거대 증명박스는 **불릿(•)으로 줄 경계**를 명시하고, 디스플레이
  수식이 박스 폭을 넘으면 원본처럼 둘째 ``=`` 에서 줄을 끊어 준다(JSON 작성 규약).

## 도원중 중1 (폼) 자가발전 검수 — 빈 단 회귀 + 점이름/단위 진단 (2026-06-11)

중1 폼(남색) **첫 corpus**. HWP COM 시작 블로커는 **재부팅으로 해소**(이 PC COM smoke test
OK — 메모리 `codex-handoff-hwp-com-20260610` 갱신). 도원중 캐시 → 폼 렌더(API 0원,
`.testkit/corpus_render.py` 어댑터 = corpus `p{n}_merged.json` → `write_exam_to_form`) → 완료본
(동아강) 1:1 대조. `render_to_png.py` 는 OUT_PREFIX **절대경로화**(상대면 PDF 가 HWP 작업
디렉터리로 샘). 회귀 방지: `verify_output_format`(30) + `test_form_layout`/`test_render_fixes`.

### ⭐ 빈 단 회귀 — 발문 속 `①` 을 선택지 마커로 오인 (hwp_form_writer, **수정 완료**)
- 증상: 객관식 단 하나가 통째 비고 이후 단나누기가 한 단씩 밀림(p3 우단 백지).
- 원인: `_measure_first_choice_lines` 가 #2 발문 "**①~⑤에 들어갈 식**"의 `①` 을 선택지
  마커로 카운트 → 17문항 ① 위치 측정이 한 칸씩 어긋나 `_extract_heights` 높이가 전부 밀려
  단 넘침 → 빈 단 캐스케이드. (기존 5개 corpus엔 발문 ① 가 없어 안 드러났던 함정.)
- 해결 ①: 선택지 마커 ① 는 **단락 첫 글자**(캐럿 `GetPos`[2]≤1). pos>1(발문 문장 중간 ①)
  이면 건너뛴다 + RepeatFind wrap 가드(GetPos 비전진 시 중단).
- 해결 ②(이중 안전망): `_repair_column_overflow` — 최종 빌드의 각 단 시작 (쪽,단) 을 실측해
  계획보다 밀렸으면 직전 단 문항간 빈줄을 줄여 재빌드(패리티 보정과 같은 **측정-검증-수리**).
  측정 과소추정으로 단이 물리적으로 넘칠 때 빈 단을 막는다.

### ⭐ 점 이름 로만 + 좌표 이탤릭 — HWP `rm` 은 뒤 전체로 번진다 (**구현 완료 2026-06-11**)
- 증상(#10·#12·#23): 좌표를 단 점 `A(-5,-3)`·`P(a,b)`·`C(a+7,2b+2)` 이 **통째 이탤릭**. 같은
  문장의 통라벨 `ABCD`·`ABC`(좌표 없음)는 이미 로만이라 한 문장에 정자/이탤릭 혼재.
- 원인: `_romanize_point_names` 가 `_BARE_UPPER_EQ_RE`(순수 대문자 블록)만 로만화 → 좌표/
  괄호 붙은 점 이름은 통과해 이탤릭 잔존.
- **핵심 함정(렌더 실증)**: HWP 수식 `rm` 은 다음 1토큰이 아니라 **명시적 `it` 전까지 뒤
  전체에 적용**된다. 그래서 `\mathrm{P}(a,b)`(→`rm P(a,~b)`)·`\mathrm{P(a,b)}`·`rm {P}(a,~b)`
  **모두 a,b 까지 로만**으로 깨진다. 오직 **`rm P it {(a,~b)}`** 만 P 로만 + a,b 이탤릭
  (`.testkit/eq_scope_test.py` 6케이스 렌더로 확정 — 사용자가 미리 지적).
- **고침**: ① `latex_to_hwpeq` `_mathit_pattern`: `\mathit{…}`→`it {…}`(중괄호로 스코프 명시,
  기존엔 `\mathit` 버려져 `it` 미출력) ② `_romanize_point_names` `_POINT_COORD_RE`: 기하 문맥
  +괄호 안 쉼표(좌표쌍) 조건에서 `점이름(좌표)`→`\mathrm{P}\mathit{(…)}` 생성. **안전경계**:
  확통 `P(X=r)`·`E(X)` 는 비기하라 `_has_geometry_context`=False → 이탤릭 유지, 함수 `f(x)`
  (소문자)·`F(x)`(쉼표 없음)도 제외. 회귀: `test_render_fixes` N(점이름)·O(mathit). 검증:
  도원중 #10·#12·#23 재렌더 + **상원중(타학교) 서답형4 `A(a-5,b+3)`·`B(ab+6,3a-b)`·`ABC`
  교차검증** — 점 로만+좌표 이탤릭 정상.

### ⭐ 변수/숫자 ↔ 단위 사이 백틱 얇은공백 누락 (**구현 완료 2026-06-11**)
- 증상(#19): `a\mathrm{cm}` 이 "a㎝"(붙음)로 렌더. 백틱 `` ` ``(1/4칸)이 없음.
- 원인: `_romanize_units` 는 **bare 숫자+단위**(`5cm`→`5 rm`cm`)에만 백틱을 넣는다. 단위가
  `\mathrm{}` 로 감싸지면(변수 `a\mathrm{cm}` 든 숫자 `5\mathrm{cm}` 든) `_mathrm_pattern`
  경로로 `rm cm`(일반 공백=렌더상 붙음)이 됨.
- **고침**: `latex_to_hwpeq._backtick_rm_units`(`_RM_UNIT_RE`) — 변환 끝 후처리로
  `<글자/숫자> rm <단위>` → `<글자/숫자> rm`<단위>`(숫자 `5 rm`cm` 와 동일 형식, `_UNITS`
  한정). bare 와 달리 붙어있던 `5\mathrm{cm}` 류도 함께 정상화. 회귀: `test_render_fixes` L·O.
  검증: 도원중 #19 `a/b/c cm` + **상원중 #1 `a cm`·`b cm`, #16 보기 `x cm`·`y cm`, 서답형3
  `y mg`·`4mg`·`100g` 교차검증** — 변수·숫자+단위 얇은 간격 정상.

### 상원중 중1 (폼) 타학교 교차검증 (2026-06-11) — 위 두 수정 무회귀 확인
도원중에서 잡은 점이름·단위 수정을 **다른 중1 학교**(상원중, 지학사)로 교차검증(API 0원,
완료본 레퍼런스). 21문항(17객관식+4서답형) 렌더 → 원본 1:1 대조. 두 수정 모두 정상 + 무회귀.
검수 중 잡은 결함은 **전부 A형(OCR JSON 작성)**: ① 발문 `<보기> 중`(보기 中=~중에서)이
`_COND_HEADER_RE` 박스머리로 오인(당시 발문에서 `<보기>` 제거로 회피 → **월암중 #11 재현으로
B형 승격·파서 수정 후 원본 충실로 복원** — 아래 월암중 섹션), ② 쉼표목록을 한 수식(`2x^2,
7x, 6`)에 넣으면 `_split_comma_equations` 가 쉼표 제거(항별 분리로 회피). 둘 다 코드 회귀
아님. corpus `corpus/[상원중][1][25-1-기말] (원본)/`.

## 월암중 중2 (폼) 타학교 교차검증 — 박스 수식·참조어·밑줄 6건 (2026-06-11)

매천중(비상)에 이어 **중2 폼(연두) 2번째 corpus**(월암중, 천재이 — 완료기반, 원본 후보 전부
손풀이라 corpus_select 상위 4종 비전 탈락). 21문항(객관식 15+서술형 6) 완료본 판독 → 렌더 →
1:1 대조. **도원중 점이름·단위 수정의 중2 무회귀 확인**(#12 `A(-1,4)`·`B(-3,-1)`·`C(5,1)` 로만
+△ABC, #18 `3cm`·`y cm²`·`60cm²` 백틱). 결함 6건 전부 B형(코드) — 결정적 수정 + 회귀 테스트
(`test_content_parser` W1~W5 16케이스·`test_render_fixes` M2·P). 무회귀: 매천중·도원중·상원중·
상인고×2·능인고 재렌더 XML lint 전부 PASS. corpus `corpus/[월암중][2][25-1-기말] (완료기반)/`.

### ⭐ 박스 안 `\begin{cases}` literal 산산조각 — `\begin`/`\end` 미인식 (D1·D4)
- 증상: `<상자>` 박스 안 연립이 `₩ begin{ { } 4x+3y=4 ₩ …` literal(#5 cases 2개·#19 단일).
- 원인: `_LATEX_CMD_RE` 에 `\begin`/`\end` 가 없어 cases 안 개행 `\\ `(백슬래시+공백)만 간격
  명령으로 매칭 → begin·cases 가 영단어처럼 쪼개짐. **매천중 #6도 동일하게 깨짐** — 당시
  "수식박스 가운데 정상" 검수 기록과 모순(당시 대조에서 놓친 숨은 결함으로 정정). 발문 인라인
  cases(#1~#7)는 OCR 이 equation 블록으로 줘 분리기를 안 거쳐 정상이었음(박스 TEXT 만 발화).
- 수정: `_LATEX_ENV_RE` — `\begin{env}…\end{env}` 를 `_split_latex_commands` **선두에서 통째
  한 수식 원자**로. cases 2개 나란히(#5)는 각각 원자(재귀).

### 박스 안 나란히 수식 병합 (D2) + `y=-\frac` 의 y 평문 (D5)
- #6 등식 2개가 한 수식으로 합쳐져 `3^{11}4^x` 붙음 → **중괄호 깊이 0 의 2칸+ 공백 = 별개
  수식 경계** + 한글 없는 ASCII 수식 조각(`4^x`)은 통째 수식 승격. JSON 규약: 나란히 수식은
  2칸 공백 구분(REVIEW_PROTOCOL).
- #15 ㄷ `y=-\frac{c}{a}x` 의 `y=` 평문(정자) 잔존 — 식별자 흡수가 연산자 흡수보다 **먼저**라
  `=-` 만 끌려감 → 연산자 흡수 후 **식별자 재흡수**.

### ⭐ 발문 선두 `<보기> 중` 박스 오인 (D3 — 상원중 이연분 B형 해결)
- 증상: #11 발문 "<보기> 중 일차함수…"가 박스 머리로 → 발문 증발, 박스에 "중 일차함수"만
  갇히고 진짜 보기 항목(ㄱ~ㄹ)이 평문으로 풀림. 상원중 #16에 이어 **2개교 재현 = 일반 패턴**.
- 수정: `_RAW_BOX_MARK_RE`(파서)·`_COND_HEADER_RE`(렌더러) 에 **참조어 부정전망**
  `(?!\s+(?:중|에서)(?=[\s,.?]|$))`. 라벨 뒤 공백+"중"/"에서"+경계 = 발문 인라인 참조.
  "중간…" 같은 일반 단어 박스 내용은 경계 조건으로 보호(매천중 `<조건> 한 미지수…` 무회귀).
  상원중 #16 JSON 도 원본 충실(`<보기> 중`)로 복원, 재렌더 정상.

### 폼 경로 밑줄 강조 소실 (D6)
- `__옳지 않은__`(#9)·`__더하거나 빼어서__`(#19) 밑줄이 폼 렌더에서 평문 — 기본 경로는
  `underline_run` 지원하나 폼 `_put_block` TEXT 분기가 underline 속성 무시. 매천중·상원중
  corpus 에도 있었으나 당시 대조에서 놓침(원칙 ③ "결함은 가려져 있다" 실례). 수정 후 상원중
  #13·#14 "않은" 밑줄도 정상 렌더.

## 중앙중 중3 (폼) 검수 — 세션 분리 첫 핸드오프, B형 3건 (2026-06-11, 커밋 571e342)

중3 폼(빨강 02.09) 첫 corpus. OCR 세션(생산)→렌더 세션(소비) 분리 운영의 첫 실전 — 핸드오프
신호(meta `status: ocr_done`) → 캐시 렌더 4회 → 완료본(5쪽) 1:1 → `reviewed`. 내용 결함 0,
B형(코드) 3건 전부 수정·회귀 박제(`test_render_fixes` Q·R5).

### sqrt/root 키워드도 영숫자 앞 공백 (PLEFT 계열 — 잠복이 길었던 이유)
- ``a\sqrt{2}`` → "asqrt {2}" 식별자 오인 literal(#4·#15). **숫자 앞(``2\sqrt{2}``)은 HWP 가
  숫자→알파벳 경계를 토큰 분리해 우연히 정상**이라 지금까지 전부 통과해 보였다 — 글자+sqrt
  조합이 처음 나온 시험지에서야 발화. accent(2026-06-10 상인고 #24)와 동종, 같은 방식 수정.

### ⭐ 중3 폼 정답 페이지 미분리 — header/footer 가 정답 container 와 한 단락
- 중3 폼은 정답 구역용 머리말/꼬리말 재정의(`hp:header`/`hp:footer`)가 **정답 container 와
  같은 본문 단락 안**에 통째로 들어 있다(고등 폼과 구조 다름). `_build_layout` 이 이를 마스킹
  하지 않아 정답 pageBreak 용 `rfind("<hp:p")` 가 **꼬리말 내부 단락**을 바깥 단락으로 오인 →
  pageBreak·짝수보정 빈페이지가 꼬리말 subList 안에 박혀 **무효**(정답이 서술형 뒤 인라인).
- 수정: `_mask(header)`·`_mask(footer)` 를 **container 마스킹보다 먼저**. `answer_ph` 탐색은
  **container 마스크 한정**(꼬리말 텍스트 "(정답)" 오인 방지). 측정(`_answer_block_pos`)은
  COM CtrlID "gso" 가 container 도 포함해 폼에 ``<hp:gso>`` 가 없어도 동작(오해 주의).

### ⭐ 선택지 2열 판정 = 시각 글리프 근사 (LaTeX 원문 길이 금지)
- 합의 #4(짧으면 2열)의 길이 추정이 **LaTeX 원문 길이**라 근호·분수 명령어가 부풀어
  ``√30×√6=□√5``(11글리프, 원문 33자)가 1열 강등(#1·#2·#3 — 완료본 2열). 순수 숫자(#4·#12)만
  2열로 가던 비대칭의 원인. **`_choice_complexity`: 명령어(``\sqrt``…)=1글리프, 구조문자
  ({}^_·공백)=0글리프** 정규화. 폼 경로 `_choice_len` 의 중복 구현도 공유 함수로 통일(항상
  동일 원칙). 긴 전개식(#5, 22글리프)은 1열 유지(임계 15/18 불변).
- 영향: corpus 10종에서 1열→2열 전환 19문항(전부 한 방향, 2열→1열 회귀 0). 무회귀 일괄
  재렌더 8종 lint 전부 PASS + 전환 7건 육안 정상. 도구: `D:\tmp\choice_flip_check.py`(데이터만
  으로 전환 목록 산출), `D:\tmp\regression_rerender.py`(8종 일괄 재렌더+lint+PNG).

### 잔여·합의 차이 (meta.json 상세)
- **박스 내부 항목 2열 미지원**(#8 ㄱ~ㅂ — 완료본 ㄱㄴ/ㄷㄹ/ㅁㅂ 2열, 우리 1열) — 다음 차수 숙제.
- 서술형 3/단(완료본 2/단) = 합의된 빽빽배치. 정답쪽 머리말 "중 학년 수학" = 폼 자체 빈 학년
  (GUI header_values 채움 검증 추후). #19 원본 오타 충실 전사(완료본은 교정함 — corpus 규약 우선).

## 장산중 중3 (폼) 검수 — 과정상자·자모 라벨·배점 위치 B형 4건 (2026-06-11)

중3 폼(빨강) **2번째 corpus**(장산중, 비상 — 세션 분리 OCR 세션 산출). 25문항 전부 객관식.
4회 렌더, 완료본(7쪽) 1:1 — 내용 결함 0, A형(JSON) 0건, B형(코드) 4건 수정. 회귀 테스트
(`test_content_parser` J1·J2·`test_render_fixes` S). corpus `corpus/[장산중][3][25-1-기말] (원본)/`.

### ⭐ `\therefore` 가 파서 인라인 분리기에 없어 literal (D1)
- 증상: #5 과정상자 안 ``\therefore x=\frac{3±㈐}{2}`` 가 ``₩therefore x=…`` literal.
- 원인: `latex_to_hwpeq` 에 매핑은 있으나(``\therefore``→``therefore``), **content_parser
  `_LATEX_CMD_RE` 에 therefore/because 가 없어** 인라인 수식 분리가 그 명령을 못 잡아 TEXT 로
  남김 → latex 변환을 못 거침. 월암중 `\begin` 동족 함정(매핑은 있는데 분리기가 모름).
- 수정: `_LATEX_CMD_RE` 에 ``therefore|because`` 추가.

### ⭐ 보기 항목 라벨 ㄱㄴㄷㄹ(호환 자모)을 한글 가드가 놓침 (D2)
- 증상: #13 보기 박스 ㄷ·ㄹ 항목(``y=4x^2+1``·``y=-(x+1)^2-3``)이 평문 잔존(^ 캐럿 노출).
  ㄱ·ㄴ(LaTeX `\frac` 포함)은 정상이라 한 박스에 정자/수식 혼재.
- 원인: `_split_mixed_text_equation` 한글 가드가 **음절(가-힣)만** 검사 → 항목 라벨
  ㄱㄴㄷㄹ은 **호환 자모**(U+3131~318E)라 "한글 없음=분리 불필요"로 오판, ASCII 수식 세그먼트가
  통째 평문. ㄱㄴ 세그먼트는 `\frac`(역슬래시) 덕에 다른 경로로 수식화돼 우연히 생존.
- 수정: 가드에 ``ㄱ-ㆎ`` 범위 포함(자모 라벨 = 한글 혼합 텍스트로 취급).

### ⭐ 발문→그림→`<보기>` 순서에서 그림이 발문 인라인 + 배점 밀림 (D3)
- 증상: #24 그림 안내문구가 발문에 인라인되고 배점 [5점]이 노트 뒤로 밀림.
- 원인: `_tail_start` 가 ``<보기>`` 머리에서 경계를 끊어 **그 앞의 그림(노트)** 이 발문에 잔류.
  과거 corpus 는 전부 발문→`<보기>`(그림 없음) 또는 발문→그림(보기 없음)이라 안 드러남.
- 수정: 박스 머리 **바로 앞**의 IMAGE/EQUATION_BLOCK/그림노트 **연속 run** 을 tail 에 포함
  (walk-back). 사이에 TEXT 가 끼면(문장 중간 그림) 중단(기존 동작 보존).

### ⭐⭐ 박스 뒤 발문연속 배점 미루기 = 서술형 전용이던 것을 전 문항으로 (D4)
- 증상: #5 배점 [4점]이 **발문 머리(박스 앞) 뒤**에 찍혀 우측정렬 폴백까지 발화. 원본·완료본은
  박스 뒤 발문연속 끝 "이때 ㈎,㈏,㈐에 알맞은 것은? **[4점]**" 에 인쇄.
- 원인: 박스 그룹화(`tail_post`) 배점 미루기(`defer_essay_score`)가 **서술형 전용**이었음. 박스
  뒤 발문연속이 있는 **객관식**은 배점이 발문 머리 뒤로 갔다(학남고 확통 #18·#20 서술형만 고쳤던
  당시 객관식 케이스가 없었음).
- 수정: `defer_score` 로 이름 바꿔 **전 문항**(객관식 포함)에 적용 — 기본(`hwp_com_writer`)·폼
  (`hwp_form_writer`) 두 경로. 객관식은 발문(post) 끝 인라인(합의 #2).
- **무회귀 = 사실 숨은 결함 정정**(매천중 #6 패턴): 같은 조합 corpus(상인고 수1 #12·14·16,
  중앙고 확통 #22, 청구중 #3)의 과거 "발문 머리 뒤 배점"은 전부 원본과 어긋난 숨은 결함이었음.
  재렌더 대조: 상인고 #14(박스→"값은? [4점]")·완료본 #12 일치·중앙고 #22(조건상자→"구간은?
  (단,…) [4.2점]" 우측정렬) — 전부 원본 인쇄와 일치(lint PASS).

### 의도된 단순화 (meta 상세)
- #5 선택지 ㈎㈏㈐ 3값·#14 선택지(축의방정식/꼭짓점) — 원본 열 머리글 표를 **표준 선택지로
  인코딩**(폼 ① 앵커 카운팅 안전). 레이아웃 차이는 알려진 차이.
- 인쇄 결손 3건(#3③·#4①·#15③) 400dpi+완료본 교차 확정. 스캔 면 순서 섞임 → pages/ 재배열.

## 강동중 중1 (폼) 검수 — 강조 밑줄·줄기-잎 열폭 B형 2건 (2026-06-11)

중1 폼(남색) **3번째 corpus**(강동중, 신사고 — 세션 분리 OCR 세션 산출). 16객관식+서술형4.
완료본 1:1 — 내용 결함 0, **A형(JSON) 0건**(OCR 세션 작성 충실), **B형(코드) 2건 수정**.
회귀 테스트 `test_render_fixes` T. corpus `corpus/[강동중][1][25-1-기말] (원본)/`(meta `review`).
두 결함 모두 **저장후 XML 후처리**(라이브 COM 조작 회피)로, 기본·폼 양 경로 공유.

### ⭐ 강조 밑줄이 회색 점선으로 — 폼 기본 밑줄 스타일 상속 (B-1, #1·#6)
- 증상: 발문 강조어(``__않은__``)가 원본의 **실선 검정**이 아니라 **회색 점선**(DOT/#808080).
- 원인: `HwpCom.underline_run` 이 ``CharShapeUnderline`` **토글만** 함 → 폼 템플릿의 기본 밑줄
  스타일(대수회 폼들 = DOT/#808080)을 상속. 렌더 hwpx header.xml charPr underline 이 그대로
  점선·회색. **폼 경로 모든 밑줄 강조에 영향**(단일 강조 charPr 이라 답란 빈칸 등과 미공유 —
  실측: 밑줄 charPr 28 하나, section0 2회=#1·#6 강조 전용).
- 수정 = `hwp_com_writer._solidify_underline`: 저장후 header.xml 의 모든 ``<hh:underline>`` 을
  ``shape="SOLID" color="#000000"`` 로 강제(type 보존). 우리 출력의 밑줄 char-run 은 전부 강조라
  안전(레거시 `hwpx_writer` 도 항상 SOLID/검정). `_com_relaunder` 재저장 생존 검증.

### ⭐ 줄기-잎 표 열너비 1:1 — TableCreate 가 col_widths 균등 재배분 (B-2, #20)
- 증상: 줄기-잎 표가 줄기:잎 = **1:1**(원본 ~1:4, 기대 1:3). 줄기(한 자리)·잎(여러 자리)인데
  같은 폭.
- 원인: `hwp_com_writer._write_table` 이 ``table_begin(col_widths=[1, 3])`` 로 1:3 을 지정해도
  **HWP `TableCreate` 가 열너비를 균등 재배분**(실측 셀 14528·14528, 총 29056). 라이브 COM 표
  조작은 불안정([[hwp-com-layout-limits]])이라 창작시점 강제 불가.
- 수정 = `hwp_com_writer._fix_stemleaf_colwidth`: 저장후 section XML 에서 **줄기-잎 표**(2열·첫
  셀 "줄기")만 colAddr 0·1 셀너비를 줄기:잎=1:3 으로 재분배(**총폭 `<hp:sz>` 보존**: 7264·21792).
  표준정규분포표·확률분포표 등 다른 2열 표는 미변경. **핵심 검증: `_com_relaunder`(HWP 재저장)가
  명시 셀너비를 보존**(load 시 균등화 안 함 — 렌더 확정).

### 반박으로 기각된 오탐 3건 (전부 합의/스타일)
- #13 표 헤더/합계 음영 = 도수분포표는 음영 대상 아님(z-표/확률분포표만, 2026-06-10).
- #16 이상/미만 위첨자 = 글꼴 모양 차이(내용 동일). #19 [총 8점] 인라인 = 인라인-우선 합의.

## 새론중 중3 (폼) 검수 — 채점기준 박스 배점 소실 B형 1건 (2026-06-11)

중3 폼(빨강) **3번째 corpus**(새론중, 비상). 13객관식+8서답형, 복잡도 최상(채점기준박스·
대화박스·말풍선·`<조건>`×4·boxed 원문자·소문항). 완료본(5쪽) 1:1 — 내용 결함 0, B형 1건.
**중3 1차분 3개 완주**(중앙중·장산중·새론중, 누적 B형 8건). corpus
`corpus/[새론중][3][25-1-기말] (원본)/`.

### ⭐ 채점기준 `<상자>` 안 항목별 배점 [1점][3점]…이 통째 소실 (SR-1)
- 증상: #15 서답형2 채점기준 박스 `[배점] ○ 미지수 정하기 [1점] ○ … [3점] …` 에서 **항목
  배점 [1점][3점][2점][4점]이 전부 사라짐**(원본은 각 항목 끝에 인쇄). 발문 끝 [10점]은 정상.
- 원인: content_parser 의 배점 제거 **3경로**가 전부 박스 내용의 [N점]을 발문 배점으로 오인 —
  ① `_parse_question` raw 단계 `_SCORE_TEXT_RE.sub` 무차별 적용, ② `_strip_score_text`,
  ③ `_strip_split_score`(쪼개진 `[`+EQ+`점]`). 배점 제거는 본래 **발문 배점 1개**(score 필드
  중복 방지)용인데 박스 채점기준까지 쓸었다.
- 수정(박스 머리 경계로 보호): ① raw 제거/캡처를 **박스 머리(`_RAW_BOX_MARK_RE`) 전 블록만**,
  ② `_strip_score_text` 를 박스 머리 전(pre)만 `_strip_split_score`+`_SCORE_TEXT_RE` 적용하고
  박스(box)는 **그대로 반환**. 발문 배점은 박스 **앞**이라 정상 제거(무회귀). 박스 뒤 발문연속
  배점(#18·#20)은 `post` 가 별도 `_finalize`(박스 머리 없음)라 정상 제거 — score 중복 안 남음.
- 무회귀: 전 corpus 스캔 — 박스 있는 문항 46개 박스앞 배점 잔존 0·박스없는 문항 잔존 0.
  회귀: `test_content_parser` J3(발문 배점 캡처+제거 / 채점기준 배점 보존).

### 검수 포인트 전부 정상 (meta 상세)
- `\boxed{㉠}`(원문자)→`BOX{ ~ ㉠ ~ }`·카드대화/말풍선 `<상자>` 가운데정렬·`<조건>`×4·자모 보기
  라벨(장산중 D2 효과)·소문항 개별 배점·기하 로만(△ABO·□AOQP·overline)·정답 라벨 전부 정상.

## 대륜중 중1 (폼) 검수 — 흰색 투명·점좌표 선택지·조건 불릿·소문항 여백 B형 4건 (2026-06-11)

중1 폼(남색) **4번째 corpus**(대륜중, 지학사 — 세션 분리 OCR 세션 2호). 20객관식+서술형2
(소문항 2+2, 22문항). 완료본 1:1 — **A형(JSON) 0건**, B형 4건 수정. 회귀 `test_render_fixes`
U·U2. corpus `corpus/[대륜중][1][25-1-기말] (원본)/`(meta `review`). B-2 는 데이터(content_parser),
나머지는 렌더(폼·박스 writer).

### ⭐⭐ 서술형 박스 뒤 소문항이 흰색(#FFFFFF)으로 통째 투명 (B-1, #21)
- 증상: `<보기>` 박스 뒤 소문항 (1)(2) 발문이 안 보임 — 빈 밑줄·배점만. 박스 없는 #22 소문항은 정상.
- 원인: `hwp_form_writer._set_plain`(본문 입력 직전 항상 호출)이 Bold·크기·장평만 설정하고
  **글자색을 리셋 안 함**. `<보기>`/`<조건>` 박스 렌더 후 캐럿이 **흰색** 상태로 남아(폼 색 배경
  메타 라벨 등에서 옴) 이후 입력 본문이 흰 배경에 흰 글자로 찍혀 투명. (렌더 hwpx charPr
  textColor=#FFFFFF 실측, 보이는 본문은 #000000.)
- 수정: `_set_plain` 에 `cs.TextColor=0`(검정) 명시 — 폼 본문 전체를 검정으로 고정.
  `_fix_invisible_charpr`(ratio/relSz 0)의 색 버전. 헤더·정답 배너의 **의도적** 흰색(색 배경
  위)은 _set_plain 을 안 거쳐 무손상. (커밋 190d69a)

### ⭐ 점좌표 선택지 A(2,3)·B(-3,1)…이 이탤릭 — 발문 기하 문맥 미전파 (B-2, #1)
- 증상: "좌표평면 위의 점 A,B,C,D,E…" 발문의 선택지 점이름이 이탤릭(도형은 로만이어야).
- 원인: `_parse_choice` 가 선택지를 **선택지 자체 contents 만**으로 처리 → 발문의 기하 키워드를
  못 봐 `_has_geometry_context`=False → `_romanize_point_names` 의 점좌표 로만화(`_POINT_COORD_RE`)
  미발동. (도원중 #10·12·23 본문 점좌표 수정이 선택지엔 안 닿았음.)
- 수정: 발문 기하 문맥을 선택지로 전파 — `_parse_choice(parent_geo=)` → `_romanize_point_names`·
  `_italicize_stat_operators`·`_italicize_nongeo_single_letters` 에 `force_geo` 파라미터(셋 다 같은
  게이트라야 로만화한 점 라벨을 nongeo 가 다시 안 벗김). 결과 `\mathrm{A}\mathit{(2,3)}`
  (`rm A it {(2,~3)}` 점 로만+좌표 이탤릭). **발문 비기하면 미발동** → 확통 `P(X=2)`·`E(X)`
  이탤릭 무회귀(검증). (커밋 e52e030)

### ⭐ 조건 박스 ○ 불릿 거대 렌더 + 항목 줄바꿈 없음 (B-3, #15)
- 증상: `<조건>` 박스 ○(U+25CB) 불릿이 HWP 본문에서 거대하게 렌더 + ○ 3항목이 한 줄로 흐름.
- 원인: ① ○ 가 `_BOX_BREAK_RE` 줄경계에 없어 항목이 안 끊김(• 구분 보기는 끊김). ② ○ 글리프
  자체가 큼(사용자 "점 작게" 합의).
- 수정: ① `_BOX_BREAK_RE` 에 `○` 추가(but `_BULLET_RE` 엔 없으므로 숨김 아닌 **표시**=각 항목
  자기 줄). ② 표시 시점에 ○→작은 `•` 치환(`_COND_BULLET_DISPLAY`). 논리 불릿은 ○ 유지
  (content_parser `_BOX_BULLET` 정규화·줄경계 식별자), 화면 글리프만 작은 점. `•` 는 `_BULLET_RE`
  숨김자라 텍스트엔 직접 못 넣어 표시 치환으로 우회. (커밋 e52e030)

### ⭐ 서술형 소문항 (1)(2) 사이 여백 0 (B-4, #21)
- 증상: 소문항 (1)·(2)가 답란 없이 딱 붙음(사용자: "최소 한 줄은 띄울 것").
- 원인: `_build_layout` 의 `pack_essays`(서술형 답란 빈줄 제거, 메모리 `form-layout-no-answer-space`)가
  서술형 영역 빈줄을 **전부 삭제**(0줄).
- 수정: 객관식 영역은 그대로 전부 삭제(빽빽), **서술형 영역은 연속 빈줄을 1개로 collapse**
  (소문항 사이 최소 1줄 확보). 정답 페이지·레이아웃 무회귀(강동중 재렌더 검증). (커밋 e52e030)

### 크롭 프롬프트 — 인접 박스 비중첩 규칙 추가 (검수 부산물, da7bb3c)
- 검수 중 #2~4 크롭이 인접 박스 ~1% 겹침(crops.json y0/y1 실측) 발견 — OCR JSON 은 이미 깨끗해
  출력 무해. `_CROP_PROMPT` 에 "ADJACENT BOXES MUST NOT OVERLAP VERTICALLY"(prev.yMax <
  next.yMin, 경계는 문항 사이 빈 줄) 규칙 명시. 향후 크롭 품질용(재크롭은 OCR 세션 몫).

## 황금중 중1 (폼) 검수 — figure 한계 집중 시험지, B형 3·A형 1 + 잔여 2 (2026-06-11)

중1 폼(남색) **6번째 corpus**(황금중, 동아강 — OCR 세션 핸드오프). 18객관식+서술형4(22문항).
figure **7개**(그래프선택지 5·좌표점·꺾은선)로 우리 파이프라인 figure 미지원 한계가 집중된
시험지. 다중에이전트 워크플로(8) + 직접 교차검증. corpus `corpus/[황금중]…`(meta `reviewed`).

### ⭐ 그림자리 안내문구가 발문 한가운데 인라인 병합 (B형, #16)
- 증상: 발문→[그림]→발문(text→figure→text 문장 중간 그림)에서 그림자리 안내("※ 그림 자리…")
  가 앞뒤 발문과 줄바꿈 없이 인라인 병합(가운데 별도줄 실패).
- 원인: 기본 경로 `hwp_com_writer._write_block` 은 TEXT 분기에 `_is_figure_note` 가운데 별도줄
  처리가 있으나, 폼 head 전용 `hwp_form_writer._put_block` TEXT 분기에는 없어 평문 인라인.
  `_tail_start` 도 figure_note 바로 뒤가 발문2 TEXT 라 walk-back 이 멈춰 head 에 남음.
- 수정: `_put_block` TEXT 분기에 `_is_figure_note` 가운데 별도줄 추가(기본 경로 동일화).

### ⭐ #22(2) 서술형 소문항 배점 줄바꿈 우측정렬 (B형, 사용자 재요청으로 잔여→해결)
- 증상: #22(2) 소문항 배점 `[2점]` 이 줄바꿈됐으나 **좌측정렬**(우측정렬이어야 — 합의 #2).
- 원인: `_put_score` 의 인라인→줄넘침감지→우측정렬 폴백이 `KeyIndicator()[5]`(줄)에 의존하는데
  **폼 단(column) 컨텍스트에서 단락 내 자동 wrap 을 비일관 측정**(probe 확정: 인라인 #22(1)·wrap
  #22(2)가 줄[5]·칸[6] 동일) → `lb>la` 미성립 → 폴백 미발동 → 인라인 좌측 잔존.
- **폐기한 우회**: `force_right`(모든 서술형 배점 항상 break+right)는 **BreakPara 가 fragile
  caret(박스/표 탈출 직후)에서 단/열/박스 레이아웃 파괴**(10쪽·#16 보기박스 1단폭 깨짐). 폼
  미주/단 캐럿 조작 위험(강동중 정답증발 계열).
- **해결**: `_put_score(force_break=True)` — **tail 없는 서술형 소문항 배점만** 항상 줄바꿈
  우측정렬(`_put_total_score` 의 **검증된** break+right 시퀀스 재사용). 핵심 = **안전 caret
  게이트**: `_put_qbody(allow_break=)` 가 `essay and allow_break and not tail` 일 때만 force_break
  (tail[박스/그림/표] 있으면 caret fragile → 인라인 유지, force_right 가 깬 바로 그 케이스 회피).
  `_fill_essay_at` 소문항 루프(`allow_break=True`)에서만 전달 — 부모 총점·객관식·tail 소문항은
  기존 인라인-우선. #22(1)[5점]·#21(1)(2)[4점]·새론중(1)(2)도 함께 우측정렬(consistency), 새론중
  #17(3)은 `<조건>` tail 이라 인라인 유지(게이트 정상). 3회 렌더 안정·무회귀(lint PASS).

### ⭐ 박스(<보기>/<조건>)↔소문항(1) 사이 빈 줄 제거 (B형, 사용자 재요청)
- 증상: #22 `<보기>`·#21 `<조건>` 박스 바로 아래 소문항 `(1)` 사이에 빈 줄 1개(사용자: "박스와
  소문항 사이 여백은 없어야"). 원인 = 박스(표) 탈출 빈 단락 + 소문항 루프 `break_para` 가 빈
  단락 1개를 남기고, `_build_layout` collapse-to-1 이 단일 빈줄이라 보존.
- 해결: `_build_layout` 서술형 영역 cleanup 에 **`prev_was_box` 추적**(표 플레이스홀더 `tbl_phs`
  포함 단락) — **박스 바로 뒤 빈 단락은 전부 삭제**(합의 #3 "박스↔선택지 빈줄 없음" 일반화).
  소문항 사이 답란(연속 빈줄 1개 collapse)은 보존. **저장후 XML(결정적)**, live COM 조작 회피.

### A형(OCR JSON) 1건 — 핸드오프 후 렌더 세션 직접 수정
- #10 어미 오전사 '평행하며'→'평행하게'(원본 '게'). 규약대로 렌더 세션이 OCR JSON 직접 수정.

### ⚠️ 잔여 2건 (다음 차수 숙제 — meta 상세)
- **#6 수식 객체 내부 base 글자 부호강조 밑줄**: `underline_run`(평문 `__강조__`만) 미지원(C).
- **figure 레이아웃 비결정**: figure 안내문구 다수(#14 그래프선택지 5개)가 `_build_layout` 단
  측정을 **COM 비결정**으로 불안정화(5~10쪽 변동·#13 단독페이지). figure 미구현(C)의 심화 —
  안내문구 압축/높이추정 고정 필요. (배점·박스여백 수정 후 5쪽 안정 관측.)

## 경일중 중1 (폼·완료기반) 검수 — 그림노트 post 배점·○불릿 박스 B형 2건 (2026-06-11)

중1 폼(남색) **7번째 corpus**(경일중, 비상 — OCR 세션 핸드오프, 완료기반). 15객+5서술.
A형 0건, B형 2건 — 둘 다 **숨은 결함 정정 동반**(상원중 #5·새론중 #15 재렌더 정정). 회귀
테스트 `test_render_fixes`(G1·○불릿). 3회 렌더 5쪽 안정. corpus `corpus/[경일중]…(완료기반)/`.

### ⭐ 박스 뒤 post 가 그림노트뿐인데 defer_score 발동 — 배점이 발문 끝을 떠남 (#19)
- 증상: 발문→`<상자>`(단서)→그림 구조에서 [6점]이 그림 노트 **뒤** 좌측에 찍힘(완료본은
  발문 끝 "…서술하시오. [6점]").
- 원인: 그림노트(TEXT)가 박스 그룹화의 post(발문 연속)로 분류돼 배점 미루기(장산중 D4
  `defer_score`)가 발동. 그림/안내문구는 발문이 아니라 발문뒤 시각 콘텐츠.
- **기각한 첫 시도(함정)**: 파서 `_raw_box_end` 에서 분리 자체를 막으면 노트 TEXT 가 tail 의
  박스 내용 수집(`_condition_start` 이후 전부)에 빨려 **박스 셀 안**에 인쇄된다. 분리는
  유지해야 노트가 박스 밖(post 경로, `_is_figure_note` 가운데)에 렌더된다.
- **해결**: `hwp_com_writer._post_has_stem` — post 가 IMAGE/그림자리 안내문구**뿐**이면
  defer 안 함(배점=발문 끝). 수식·일반 TEXT 가 하나라도 있으면 기존 defer 유지(학남고
  #20 `P(Y≤29)`+텍스트·장산중 #5 무회귀). 기본·폼 두 경로의 defer 판정에 동일 적용.

### ⭐ ○ 불릿 다항목 `<상자>` 가 가운데정렬 — `_is_labelless_box` 불릿 인식 누락 (#19·#16)
- 원인: `_is_labelless_box` 가 `•·▪◦`(`_BULLET_RE`)만 불릿으로 봐서, 표준화 ○ 불릿
  (`_BOX_BULLET`, 대륜중 B-3 때 `_BULLET_RE` 에 의도적으로 안 넣음=표시용) 다항목 박스를
  "단일 진술"로 오인 → 가운데정렬. `_CIRCLE_BULLET_RE`(단독 공백경계 ○, "○표 하시오" 류
  비불릿 제외) 추가로 좌측정렬.
- **숨은 결함 정정 2건**: 상원중 #5(○ 항목 5개 — 원본 좌측 확인)·새론중 #15 채점기준 박스
  (좌측 + SR-1 항목배점 보존) 도 같은 패턴이었음(당시 대조에서 놓침, 원칙 ③ 실례). 재렌더
  lint PASS. 상원중 meta 는 신 스키마(form/status) 보강.

## 범물중 중1 (폼·완료기반) 검수 — 단위 L·변수+단위 무공백 B형 1건 (2026-06-11)

중1 폼(남색) **8번째 corpus**(범물중, 천재이 — OCR 세션 핸드오프, 완료기반). 17객+5서답.
A형 0건, B형 1건(매천중 #9 숨은 결함 정정 동반). 회귀 테스트 `test_render_fixes` O2(6케이스).
3회 렌더 7쪽 안정. corpus `corpus/[범물중]…(완료기반)/`.

### ⭐ 단위 L 이탤릭 + 변수에 무공백으로 붙은 단위 미인식 (#22 "1L·xkm·yL")
- 증상: `1L로`·`yL라고` 의 L, `xkm인` 의 km 이 통째 이탤릭(완료본 = 변수만 이탤릭, 단위는
  정자+얇은 간격).
- 원인 두 갈래: ① 학남고(2026-06-08) 때 단일문자 단위 m·t·s·h·**L** 을 `_UNITS` 에서 일괄
  제거(모평균 m 오로만화 방지) → L 이 어디서도 단위 취급 안 됨. ② `_romanize_units` 는
  **숫자** 접두만 처리해 변수 글자에 무공백으로 붙은 다문자 단위(`xkm`)가 식별자 run 으로
  통째 이탤릭.
- 수정(latex_to_hwpeq, 좁은 결정적 규칙): ① `_NUM_TAIL_UNITS` — **숫자 직결 꼬리** L 은
  단위 확실(`1L`→``1 rm`L``). ② `_VAR_UNIT_RE` — **단일 변수 글자**(앞이 글자면 LCM 류
  식별자라 제외) + 다문자 단위/L(`xkm`→``x rm`km``, `yL`→``y rm`L``; g·° 단일기호는 변수곱
  `ag` 오인 방지로 제외). **모평균 `2m`·첨자 `a_1L`·변수곱 `ag` 이탤릭 보존**(학남고 결정
  유지 — L 만, 그것도 직결 꼬리 한정 복원).
- **숨은 결함 정정**: 매천중 #9 선택지 `300L·5L·yL` 도 이탤릭이었음 — 재렌더로 정자 확인
  (5쪽·lint PASS). 평문 TEXT 런의 "x cm" 류(경일중 #18 등)는 수식 경로를 안 타 원래 정상.

### 의도된 단순화 (meta 상세)
- 완료본 배점 표기 `[합 7점, 부분 점수 있음]`(#19·#22)·`[7점, 부분 점수 있음]` 줄바꿈(#20)
  → 우리 표준 `[총 7점]`·`[7점]` 인라인(부분점수 문구 드롭, 인라인-우선 합의 — 강동중 #19
  기각 선례). 검수 정상: #11 [4점] 줄바꿈 우측(완료본 동일)·#20 `<상자>` 두 식 가운데(완료본
  동일)·#17·#21 점이름 로만+좌표 이탤릭·#18 `<조건>` 5×5 폼·정답면 라벨 동기화.

## 경구중 중1 (폼·완료기반) 검수 — 박스 ASCII 선행 단항부호 B형 1건 (2026-06-11)

중1 폼(남색) **9번째 corpus**(경구중, 신사고 — OCR 세션 핸드오프, 완료기반). 16객+4서술.
A형 0건, B형 1건. 회귀 테스트 `test_content_parser` K1. 3회 렌더 6쪽 안정. corpus
`corpus/[경구중]…(완료기반)/`.

### ⭐ 박스 ASCII 수식의 선행 단항부호가 평문 하이픈으로 분리 (#5 ㄷ·ㅁ, #13 ㄹ)
- 증상: `<보기>` 항목 ``ㄷ. -5x+6=6-5x`` 의 선행 ``-`` 가 수식 밖 평문(짧은 하이픈·정자)으로
  렌더 — 수식 마이너스(―)와 글리프가 달라 시각 불일치.
- 원인: 선행 연산자 흡수(능인고 R2 ``= - \frac``·월암중 W4 ``y=-``)가 **LaTeX 경로**
  (`_split_latex_commands`)에만 있고, 순수 ASCII 경로(`_split_mixed_text_equation`)는
  `_MATH_ATOM` 이 부호 없이 시작해 선행 ``-`` 가 직전 TEXT 로 떨어짐.
- 수정: ASCII 경로에 **선행 단항부호 흡수** — 부호 앞이 라벨점(``ㄷ.``)·불릿·한글·여는괄호·
  시작이면 수식에 포함. **직전 블록이 수식이고 사이가 부호뿐이면 이항**(``f(x) - 5x``) —
  흡수하지 않고 `_merge_operator_split_equations` 의 한 수식 병합에 맡긴다(기존 동작 보존).
  ``=-`` 분리(ㅁ ``+2=-3x-1``)는 기존 merge 가 한 수식으로 재병합(무변경).
- 무회귀: 청구중(ASCII 풀이상자)·월암중(박스) 재렌더 lint PASS·쪽수 안정. 검수 정상: #10
  선택지 점 A~E 로만·#12 강조밑줄+frac(OCR 명시 equation 분리 규약)·#14 ``ykm``(범물중
  단위수정 효과)·#3 해후보 ``[n]``·정답면. 잔여 C: #8 이항 밑줄(수식 내부 밑줄 미지원)·
  박스 내부 항목 2열(#5·#13, 중앙중 잔여와 동일)·figure 3종.

## 월서중 중1 (폼) 검수 — 밑줄 분기 수식추출 억제 해소 등 B형 4건 (2026-06-11)

중1 폼(남색) **8번째 corpus**(월서중, 비상 완료본 — 원본 직접 판독, 쭌쭌 사본). 17선다+4서답
=21문항. 4회 렌더 7쪽 안정, lint 전부 PASS. A형 1건(#12 ○→• 불릿 통일), B형 4건. 회귀
테스트 `test_content_parser`·`test_render_fixes`(O2·음영 음성). corpus
`corpus/[월서중][1][25-1-기말] (원본)/`(meta `reviewed`).

### ⭐⭐ `__밑줄__` 분기가 인라인 수식 추출을 통째 억제 (B-3 — 잠복 근본원인)
- 증상: #14 ``y가 x에 정비례하지 __않는__`` 의 y·x 평문(정자) 잔존. #7 ``x``·``a, b``·
  ``a+b``, #10 ``제2사분면`` 의 2 도 동일.
- 원인: `content_parser._parse_content_block` 이 TEXT 에 ``__`` 가 있으면 **밑줄 분리만 하고
  조기 반환** — 비밑줄 세그먼트가 인라인 수식 분리 파이프라인을 안 거침. **밑줄 강조가 있는
  발문 전체의 수식이 평문화**되는 광역 함정(경구중 meta 가 ``__이 포함된 발문은 수식 추출이
  안 된다``고 지목했던 것의 근본원인).
- 수정: 밑줄 분리 후 **비밑줄 TEXT 세그먼트를 `_parse_content_block` 재투입**(재귀) — 밑줄
  run 은 보존, 나머지는 일반 파이프라인(수식 분리·로만화·단위) 통과.
- **영향권 정밀 산출(전수 재렌더 대신)**: HEAD↔현재 파서로 **전 corpus 파싱 시그니처 비교**
  → 변화는 월서중 #7·#10·#14 + 황금중 #12 + 대륜중 #1 + 매천중 #1 + 월암중 #19 뿐(전부
  수식 객체화 방향). 4개교 재렌더 lint PASS — **대륜중 #1 발문 점 A~E 로만 객체화**(선택지와
  일치 = 숨은 결함 정정), 매천중 #1 ``2개`` 객체화, **월암중 #19 분리형 ``[서술형 ``+EQ+``]``
  라벨**도 dedupe·renumber 정상(정답면 1~6 연속), 황금중 7쪽(figure 비결정 범위) 판정.

### 박스 고아 불릿 빈 줄 (B-1) + JSON 불릿 혼용 (A형)
- #12 ``<상자>`` 에서 ``○ (가)…`` + ``• (나)…`` 불릿 혼용 → 항목 사이 고아 불릿이 빈 항목
  줄로 인쇄. 렌더러: `_write_box_content.emit_text` 에 **고아 불릿 숨김 가드**(불릿 매치 뒤
  다음 매치까지 내용이 없으면 hidden). JSON: ``○ (나)``→``• (나)`` 통일(A형, 렌더 세션 직접).
- 인접 정정 마침: 같은 가드가 새본리중 #5·#6(○불릿 박스) 류 입력 혼용도 방어.

### kcal 단위 (B-2) + 서답형4 ⋯표 음영 오탐 (B-4)
- #14 ``18kcal`` 이탤릭 — `_UNITS` 에 kcal 누락. 추가로 숫자/단일변수 꼬리 정자화 일괄 적용
  (``10L``·``5kg`` 함께 정상). 회귀: `test_render_fixes` O2.
- #21(서답형4) 2행×8열 ``⋯`` 나열표 1열에 확률분포표 음영(#D9D9D9) 오탐 — 음영 판정(2행×
  ≥3열)에 **P(X 류 확률표기 게이트** 추가(`_shade_target_mode`). z-표 게이트(LEQ Z LEQ)와
  같은 내용 시그니처 원칙.

### 검수 정상 확인 (meta 상세)
- #21 [총 8점] 인라인·(1)[3점]·(2)[5점] 우측정렬(완료본 일치), #17 점 A·B·C·OBC·OAB 로만,
  #18 값박스 두 방정식 가운데(2칸 분리 규약), #19 [9점] 줄바꿈 우측정렬·<조건> ※머리+번호
  항목, #20 [총 9점] 인라인·소문항 [3점]×3 우측정렬·``yL``/``300L`` 정자(범물중 수정 효과),
  p7 정답면 [서답형 1~4](원본 충실 — 완료본은 [서술형] 표기)·답안칸 21개·홀수 패리티.
- 잔여 C: figure 5종 안내문구(#2·#9·#12·#13·#17·#20)·#3 중괄호 리터럴 따옴표(단일줄 무해).

## 새본리중 중3 (폼) 검수 — 정답 패리티 측정시점 등 B형 5건 + A형 5건 (2026-06-12)

중3 폼(빨강) **4번째 corpus**(새본리중, 동아강 — 원본 직접, 깨끗본). 17선택형+5서술형
=22문항. **다중에이전트 워크플로 검수**(33 에이전트: 22문항 1:1 비전 대조 + 결함별 반박
검증, 기각 0) + 직접 교차검증(패리티·정답면). 6회 렌더 5쪽 안정, lint 전부 PASS. 회귀
테스트 `test_content_parser` L1~L4(19케이스)·`test_render_fixes`(○박스 음성). corpus
`corpus/[새본리중][3][25-1-기말] (원본)/`(meta `reviewed`).

### ⭐⭐ 정답 페이지 패리티 측정시점 — 정답이 짝수쪽으로 출하 (B-1, 잠복 광역)
- 증상: 문제 4쪽(짝수 마무리 정상) + **빈 p5 + 정답 p6(짝수)** — 양면 인쇄 시 정답이
  문제부 마지막 장 뒷면에 붙는다. 전 렌더 corpus 패리티 전수 점검으로 **경구중(6쪽)·
  월암중(6쪽)도 같은 숨은 결함**으로 출하됐던 것 확인(당시 "쪽수 안정"만 보고 패리티
  미점검 — 원칙 ③ 실례).
- 원인(이중): ① `_layout_form` 의 짝수 보정이 **레이아웃 직후 측정**인데, 그 뒤 후처리
  (`_inject_bogi_form` 5×5 표 치환·`_inject_essay_meta` 메타란 주입)가 본문 높이를 키워
  페이지 흐름이 한 쪽 밀림 — 측정 4쪽(빈장 삽입)→최종 6쪽(경구중·새본리중), 측정 5쪽
  (보정 없음)→최종 6쪽(월암중). ② 격리 재현 중 발견한 **잠복 레이스**:
  `_measure_answer_page` 의 `hwp.Quit()` 이 비동기라 직후 `os.replace` 가 간헐
  PermissionError(처음 통합 때 예외가 경고로 먹혀 조용히 무변경).
- 수정: `hwp_form_writer._fix_answer_parity` — **모든 후처리·relaunder 뒤** 최종 측정,
  짝수면 정답 직전 패리티 빈 단락 **제거**(당김, 새본리중 6→5) 또는 빈 단락 **삽입**
  (밀기, 월암중 6→7). 교정 시 `_com_relaunder` 재실행(보안경고 재제거). 헤더/풋터는
  **인덱스 보존 공백 마스킹**(중3 폼 꼬리말 오인 방지, 중앙중 교훈). `_replace_retry`
  (os.replace 재시도)로 ①②의 핸들 레이스 동시 해소 — `_build_layout` 의 replace 에도 적용.
  **HWP Open 은 상대경로 조용히 실패** → 함수 진입 시 resolve() (기존 교훈 재확인).
- 검증: 제거(새본리중 6→5)·삽입(월암중 6→7)·무변경(홀수)·멱등 4경로 + 파이프라인 통합
  렌더. 측정은 relaunder 후 = PDF 와 같은 페이지네이션 기준.

### 첨자 절단·자모 병합·○값상자·반원 키워드 (B-2~B-5)
- **B-2 brace-less 첨자 절단**(#7 과정상자): ``x^2-\frac{7}{2}x+A=\frac{3}{2}+A`` 가
  ``x^``(고아 수식)+``2-…`` 로 절단 — x² 이 "x  2"(베이스라인 풀사이즈)로 렌더. 원인 =
  선행 연산자 흡수 후 식별자 재흡수(`_is_eq_lead_char`)가 ``2`` 까지만 끌고 ``^`` 에서
  멈춤. 같은 박스 2행이 멀쩡했던 건 TEXT ``^`` 경유 `_merge_operator_split_equations`
  재병합의 우연. 수정: `_is_eq_lead_char` 에 첨자 ``^``/``_``(앞이 영숫자/``}``) 흡수.
- **B-3 자모 라벨 수식 병합**(#17 보기 박스): ``ㄴ. y=-3x^2-2 • ㄷ. …`` 조각이 통째 한
  수식(라벨·불릿 literal). `_split_latex_commands` 의 "한글 없는 순수 ASCII 수식 조각"
  가드가 음절(가-힣)만 검사 — **자모(ㄱ-ㆎ) 포함**(장산중 D2 의 latex 경로판). + OCR JSON
  ``{"underline": true}`` 속성 인코딩을 파서가 강조 run 으로 수용(조용한 평문 강등 방지).
- **B-4 ○불릿 2항목 박스 가운데**(#5): `_is_value_box` 가 leftover 에서 •만 제거해 ○ 2개
  (≤6자)가 값상자 오인 → `_is_labelless_box` 의 경일중 ○ 가드를 단락 우회. ○ 존재 = 항목
  나열 = 값상자 아님.
- **B-5 반원 기하 문맥**(#20): "반원의 중심을 O" 의 O 이탤릭 — `_GEOMETRY_KEYWORDS` 에
  반원·지름·반지름 추가(단독 "중심"·"원" 은 정규분포 '평균을 중심으로'·'원소' 충돌로 제외).

### A형 5건 — 검수 에이전트 픽셀 판독으로 잡은 오전사 (렌더 세션 직접 수정)
- #15 선택지 ② ``-2``→``-6``: **정답 보기가 소실**돼 있었음(4배 확대 + a-b+c=-6 검산).
  #16 ``(-k,-1)``→``(k,-1)``(10배 확대 — 연필 자국을 음수부호로 오인). #10 '라(고)' 누락.
  #2·#13·#17 밑줄 속성 인코딩 → ``__마크업__`` 재인코딩. #22 sub(2) 삼각형→``\triangle``.
- ⚠️ **도구 이스케이프 함정**: Bash here-doc 인라인 수정에서 ``\t``/``\f`` 가 도구 JSON
  레이어에서 한 꺼풀 벗겨져 **탭/폼피드 오염**(#22 ``rianglePAB`` 렌더로 발각). 백슬래시
  포함 JSON 수정은 **스크립트 파일로 작성**(Write 도구)해 실행할 것.

### 검수 정상 확인 (meta 상세)
- #18 [총 8점]·소문항 [3점][3점][2점] 우측정렬, #11 점 Q·A·B·P·R·□OPQR 로만, #20 overline·
  ``x cm``, #22 △PAB·점 P·A·B 로만+[총 8점] 인라인, p5 정답면 [서술형 1~5]·답안칸 22.
- 잔여 C: figure 3종(#11·#20·#22) 안내문구 — figure 미지원 한계.

## 운암중 중3 (폼) 검수 — 무회귀 교차검증 (A형 3건·B형 0건) (2026-06-12)

중3 폼(빨강) **5번째 corpus**(운암중, 비상 — pristine 미사용본). 16선택형+6서답형=22문항.
다중에이전트 워크플로(25 에이전트, 반박 검증 기각 0). **새본리중 중3에서 도입·수정한 5건
(정답 패리티 측정시점·brace-less 첨자·자모 보기 박스·○값상자·반원 기하)이 타학교에서 전부
무회귀** — B형(코드) 0건이 그 방증. 3회 렌더 5쪽 안정(정답 p5 홀수·빈장 없음). corpus
`corpus/[운암중][3][25-1-기말] (원본)/`(meta `reviewed`).

### A형 3건 — 검수 에이전트 확대 판독으로 잡은 오전사 (렌더 세션 직접 수정)
- #4 선택지 ② ``5``→``4``(원본 짝수열 2,4,6,8,10 — 2배 확대 확정. major: 선택지 값 오류).
- #3 발문 '두 근의 비'→'두 해의 비'(원본 충실 — **OCR 세션 meta 가 '근 유지'로 기록했으나**
  검수 에이전트가 4배 확대로 원본 '해' 확정. 답 무관하나 원문 우선 규약, 장산중 #19 선례).
- #16 'C라 할 때'→'C라고 할 때'('고' 1음절 누락 — 같은 문장 'A라 하고'는 원본도 '라'라
  일관 정규화 아닌 C 부분만 실제 오전사).
- ⚠️ 백슬래시 없는 순수 한글/숫자 수정이라도 [[bash-heredoc-backslash-trap]] 교훈대로
  Write 스크립트(.testkit/fix_unam.py)로 처리.

### 무회귀 교차검증의 의미
- B형 0건 = 새본리중 패리티 수정(`_fix_answer_parity`)이 정답을 짝수쪽으로 밀지 않고 5쪽
  홀수로 정상 출하. 첨자·자모·○박스·반원 수정도 운암중엔 해당 케이스가 없어 부작용 0.
- 검수 정상: #6 정사각형 EFGH overline·로만, #7 '않은' 밑줄, #11·12·16·21·22 figure 안내,
  점/도형 로만(ABCD·EFGH·OABC·AOH·O~T), 단위 cm·g·m 백틱, p5 정답면 [서답형 1~6]·답안칸 22.
- 잔여 C: figure 5종 안내문구 — figure 미지원 한계.

## 학산중 중3 (폼) 검수 — 소문항 교차참조 '(1)에서' strip B형 1건 (2026-06-12)

중3 폼(빨강) **6번째 corpus**(학산중, 동아박 — 깨끗본). 16선택형+5서답형=21문항. 다중에이전트
워크플로(22 에이전트, 반박 검증 기각 0). A형 0건, B형 1건. 5회 렌더 7쪽 안정(정답 p7 홀수·
빈 p6). 회귀 `test_render_fixes` V(submark-ref). corpus `corpus/[학산중][3][25-1-기말] (원본)/`
(meta `reviewed`).

### ⭐ 소문항 교차참조 '(1)에서 구한 식' 의 '(1)' 이 strip 됨 (B-1, #19)
- 증상: #19 sub(2) 원본 ``(2) (1)에서 구한 이차함수의 식을 이용하여…`` → 렌더
  ``(2) 에서 구한…`` (교차참조 ``(1)`` 누락, 문장 불완전). OCR JSON 은 ``(1)에서…`` 정확.
- 원인: `_strip_leading_submarker`(폼 경로, 우리 ``(k)`` 마커와 중복인 OCR 마커 제거)가
  소문항 본문 머리의 ``(1)`` 을 **소문항 마커로 오인** 제거. 두 겹:
  ① 파서가 ``(1)에서`` 의 ``(1)`` 을 괄호원자로 **수식화**(EQ``(1)``+TEXT``에서…``) → 형태4
  (마커 통째 한 수식)가 EQ``(1)`` 를 제거. ② `_SUBMARK_RE` 의 trailing ``\s*`` 가 공백 0개를
  허용해 ``(1)에서`` 텍스트(형태1)도 매칭.
- 핵심 구분: **진짜 소문항 마커는 마커 뒤 공백**(``(2) 일차함수…``), **교차참조는 닫는 괄호
  직후 공백 없이 한글 직결**(``(1)에서``). `_is_ref_not_submarker(seg, rest)` = seg 가
  trailing 공백을 안 먹고 ``)``/``）`` 로 끝나고 rest 가 한글로 시작 → 참조(strip 금지).
  형태1·2·3·4 **전부**에 가드 적용(분리형 EQ 마커 포함). 원숫자 ``①``·``1.`` 는 닫는 괄호가
  없어 항상 마커 취급(무영향). 회귀: `test_render_fixes` V(5케이스).

### 무회귀 교차검증 (새본리중 수정)
- 보기박스 #7·#8·#14(자모 ㄱ~ㅁ 각 항목 자기 줄)·조건박스 #13·#18·#19·#21(○→• 불릿 각 줄)·
  그림 8종이 새본리중 자모 보기 병합·○값상자·패리티 수정과 겹침 — 전부 무회귀. 점/도형 로만
  (□PBOA·ABCD·PBQ·OABC·AOB)+좌표 이탤릭(P(a,b)·O(0,0)·A(6,-12)), 단위 cm·m·g·km 백틱 정상.
- 잔여 C: figure 8종 안내문구 — figure 미지원 한계.

## 정화중 중1 (폼) 검수 — 서답형 라벨 통합 번호 → 원본 보존 B형 1건 (2026-06-12)

중1 폼(남색) **11번째 corpus**(정화중, 동아강 — 원본 직접). 13선다+4단답+3서술=20문항,
소수배점. 20문항 전수 직접 대조(워크플로 미사용 — [[corpus-review-direct-not-workflow]]).
A형 0건, B형 1건. 2회 렌더 7쪽 안정·lint PASS. 회귀 `test_render_fixes` K2. corpus
`corpus/[정화중][1][25-1-기말] (원본)/`(meta `reviewed`).

### ⭐ 서답형 라벨 통합 번호 강제 — 유형별 독립 시험지에서 어긋남 (B-1)
- 증상: #18 서술형 본문·정답 라벨이 ``[서술형 5]``(원본 ``[서술형 1]``). 단답형 4개(#14~17
  = [단답형 1~4]) 뒤 서술형이 5·6·7로 통합 일련번호.
- 원인: `_renumber_essay_labels` 가 모든 서답형 라벨을 **문서순 통합 번호**(``i//2+1``)로
  재부여 — 폼 grow 비결정 라벨(상인고 #25) 교정용. 그런데 **폼마다 라벨 체계가 다름**:
  정화중은 **유형별 독립**(단답형 1~4·서술형 1~3), 능인고는 **통합**(서술형 1~3·단답형 4~5).
  통합 강제가 능인고는 우연히 맞고(통합=통합) 정화중은 틀림.
- 수정: 원본(OCR 인쇄)이 정답 — `write_exam_to_form` 이 `_essay_label_and_body` 로 essay별
  **원본 라벨 번호**(``nums``)를 추출해 `_renumber_essay_labels(nums=)` 로 전달. 통합 강제
  대신 OCR 원본 번호 보존. 능인고 ``nums=[1,2,3,4,5]``=통합과 동일이라 **무회귀**(재렌더 #19
  ``[단답형 4]`` 확인). 회귀: `test_render_fixes` K2(유형별 보존 + 능인고 통합 무회귀).

### 검수/렌더 파이프라인 도입 (이 corpus부터)
- 검수(비전, HWP 미사용) 중 **다음 대기 corpus 1차 렌더를 백그라운드 선행**
  (`.testkit/batch_render.py`, HWP COM 순차) — 렌더 블로킹과 검수를 겹쳐 throughput↑
  (사용자 요구, [[render-review-pipeline]]). 이번에 정화중·매호중·효성중을 선행 렌더.
  부수 발견: 매호중·효성중 meta form 이 ``(02.09)``(중2 폼은 ``(01.09)``만 존재)로 잘못
  기록 → 정정.

### 검수 정상 확인 (meta 상세)
- 소수배점([3.5]~[4.3])·중첩괄호(#10 ``[{()}]``)·보기박스 4종(#9 ㄱ~ㅅ 7항목)·#20 2열
  문장 셀 표+소문항 (1)~(4) [5][1][5][1]·[총 12점]·작업자 A~F·X 변수 이탤릭. 정답면
  [단답형 1~4][서술형 1~3].
- 잔여 C: figure 1종(#13)·박스 내부 2열(#9, 중앙중 잔여와 동일).

## 효성중 중2 (폼) 검수 — 메타란 토큰 비결정 노출 루프 해소 B형 1건 (2026-06-12)

중2 폼(연두) **2번째 corpus**(효성중, 동아박 — 깨끗본). 18선택형+서술형4=22문항, 소수배점
8문항. 22문항 전수 직접 대조(워크플로 미사용). 내용 결함 0건, B형 1건(비결정 코드). 회귀
`test_render_fixes`(기존 메타 함수). corpus `corpus/[효성중][2][25-1-기말] (원본)/`(meta `reviewed`).

### ⭐ 메타란 토큰 비결정 평문 노출 — relaunder 후 반복 루프로 해소 (B-1)
- 증상: 같은 입력 9회 렌더 중 2회에서 서술형 메타란 토큰 ``소단원자리표식QZX``·
  ``난이도자리표식QZX`` 가 평문 노출(corpus_lint FAIL). 같은 연두 폼 매호중은 PASS만.
- 원인: `_inject_essay_meta` 가 토큰 run 을 ``[소단원]/[난이도]`` 메타란 run 으로 교체하는데,
  **COM 저장이 토큰을 비결정으로 여러 run/t 로 쪼개면**(연속 문자열 매치 실패) 처리 못 하고,
  직후 `_com_relaunder`(HWP 재저장)가 토큰을 **run=1 로 정규화**하며 평문 노출. 기존 1회 폴백
  (relaunder 후 _inject_essay_meta 재주입)은 그 relaunder 가 **다시 쪼개면** 놓쳐(검사 1회뿐)
  비결정이 남았다.
- 수정: `write_exam_to_form` 끝에 **relaunder 후 검사·처리 반복 루프**(최대 3회):
  매 회 `_count_meta_tokens`(relaunder 직후라 run=1 → 연속 문자열 정확) → 남으면
  `_inject_essay_meta`(채움, run=1 이라 성공) 또는 `_strip_residual_meta_tokens`(텍스트 비움,
  최후 안전망) + `_com_relaunder`. 토큰 0 이면 relaunder 직후 상태라 **보안경고도 없다**.
  루프 수정 후 효성중 5/5 PASS + 매호중·정화중·새본리중 무회귀.
- 핵심 교훈: **COM 비결정 토큰은 relaunder 가 정규화한 *뒤* 검사**해야 정확(쪼개진 상태에선
  연속 문자열 count=0). 1회 후처리로는 relaunder 의 비결정 재쪼갬을 못 막아 — 검사·재저장
  **반복**이 필요. ([[hwp-com-table-equation]] COM 비결정 계열.)

### 검수 정상 확인 (meta 상세)
- ㉠/㉡ 라벨+원문자 연산 선택지(#2)·cases 박스 2개 나란히(서술형1)·기하 로만(서술형2 overline
  AB=10·점 A·B)·선행 단항부호('-b만큼' 서술형3)·밑줄(#9)·소수배점([3.5]×4·[4.5]×4)·단위
  (#17 cm×4+소수)·figure(#9·#16) 전부 정상. 새본리중·학산중 수정 무회귀.

## 성광중 중2 (폼) 검수 — 단위 선택지 평문강등·온도 °C 분리 B형 2건 (2026-06-12)

중2 폼(연두) **6번째 corpus**(성광중, 천재류 — OCR 세션 핸드오프). 18선택형+서술형3=21문항,
소수배점 17. 직접 1:1 대조(원본 ↔ 렌더 컬럼 확대, API 0원). 내용 결함 0, A형 0, B형 2건.
회귀 `test_content_parser` SG1·SG2. 무회귀=트리거 스캔 전 corpus 성광중 단독. corpus
`corpus/[성광중][2][25-1-기말] (원본)/`(meta `reviewed`).

### ⭐ 단위 선택지가 단일 LaTeX 수식일 때 평문 강등 — raw `\mathrm` 누수 (B-1, #12)
- 증상: 선택지 `①482cm ②486cm …` 가 `482₩mathrm{cm}` literal 렌더(단위 변환 안 됨). 본문
  `1cm·6cm·10cm`(같은 `1\mathrm{cm}`)는 정상.
- 원인: OCR 이 단위 선택지를 **text 타입** `{'type':'text','value':'482\mathrm{cm}'}` 로 줌.
  `_split_latex_commands` 가 이걸 **단일 EQUATION 하나**로 올바르게 식별하지만,
  `_parse_content_block` 의 `if len(split) > 1:` 가드가 **단일 split 을 버리고** 평문 TEXT 로
  강등 → raw LaTeX 가 평문 노출. 본문 `1\mathrm{cm}인 정육각형`은 EQ+TEXT 2개(len>1)라 통과
  했으나, 선택지처럼 텍스트가 **수식뿐**이면 len==1 이라 강등.
- 수정: `len(split) == 1 and split[0].type != TEXT`(분리기가 수식으로 승격 확신)면 그 단일
  수식 블록 반환(평문 강등 금지). CLAUDE 의 '단일 수식 블록 평문 강등 방지'와 동일 방향.
  `\mathrm{cm}`→`482 rm\`cm`(정자 단위+얇은 간격).

### ⭐ 온도 단위 °C 분리 — C 단독 이탤릭 변수 + 공백 (B-2, #17)
- 증상: `6°C씩` 이 `6° C`(C 이탤릭 변수 + 사이 공백)로 렌더. 원본 `6°C`(정자 단위, 붙음).
- 원인: 인라인 수식 분리가 `6°C` 를 **EQ`6` + TEXT`°` + EQ`C`** 로 쪼갬(° 가 수식 원자
  경계). 고립된 `C` 가 단독 수식 = HWP 기본 이탤릭 변수, EQ 런 사이 공백까지.
- 수정: `_merge_degree_temp_units` — `°` 직후 **단일 대문자 C/F**(온도 단위 확정)면 EQ+TEXT`°`
  +EQ`C` 를 한 수식 `6°\mathrm{C}`(→`6°rm C`, C 정자)로 병합. **strict 게이트**: 각도 `45°`
  (뒤가 C/F 아님)·점 이름 C 무영향. 본문·선택지 두 경로(finalize + `_parse_choice`).

### 검수 정상 확인 (meta 상세)
- 보기 박스(#1 ㄱ~ㅁ·#11 ㄱ~ㅅ 7항목 부등호·분수)·cases 연립(#5·#20 괄호전개)·분수(#4·#6·#8·
  #15)·overline(#8 AB/CD·#18)·점 로만(#16 ABC/OAD/O·#18 ABCD)·소수배점 17문항([3.1]~[4.2]
  인라인)·독립 서술형 [N점] 인라인(인라인-우선 합의)·#21 a·b부호→사분면 빈 표(작성형)·정답면
  [서술형 1~3]·홀수 패리티(5쪽). figure 4종(#7·#11·#12·#16·#18) 안내문구 — figure 미지원 C한계.

## 시지중 중2 (폼) 검수 — 무회귀 교차검증 (A형 0·B형 0) (2026-06-12)

중2 폼(연두) **5번째 corpus**(시지중, 천재류 — OCR 세션 핸드오프). 17선택형+서술형5=22문항.
직접 1:1 대조 — **결함 0건**. 성광중에서 도입한 단위 수정(단일수식 강등방지·°C 병합)·도원중
점이름 로만+좌표 이탤릭·범물중 단위 백틱이 **타학교에서 전부 무회귀**(B형 0이 방증). 트리거
스캔상 시지중은 성광중 수정 영향권 아님(단일수식·°C 0건) → 기존 배치 렌더 = 현재 코드 출력.
corpus `corpus/[시지중][2][25-1-기말] (원본)/`(meta `reviewed`).

### 무회귀 교차검증의 의미
- 점 로만+좌표 이탤릭(#12 A(1,3)·B(2,-1)·C(4,1)+△ABC)·단위(#8 x km·30 km·x cm·y cm²·8 cm
  변수 이탤릭+단위 정자, #17 15π cm³·7π cm³·y cm³ — 15π 보존)·cases(#2 …①②·#5 보기박스 내
  cases·#18·#19 …①②)·overline(#22 AD/CD/BC)·삼각형 APC 로만·부등호(#12 < vs ≤ OCR 일치)
  전부 정상. #22 [총 7점] 인라인+(1)[4점]·(2)[3점] 우측정렬, 독립 서술형 [7점] 인라인.
- #22(2) '출발한지'(붙임)는 원본 충실(원본 확대 확정). 배점 '[3점, 부분점수 있음]'→'[3점]'은
  인라인-우선 합의(범물중 #20 선례). figure 3종(#14 ㉠~㉤·#17 원기둥+원뿔 입체[중2 첫 입체]·
  #22 삼각형) 안내문구 — figure 미지원 C한계.

## 학산중 중2 (폼) 검수 — 타이핑 혼입 자동검출 게이트 개선 (내용 0·게이트 1) (2026-06-12)

중2 폼(연두) **4번째 corpus**(학산중, 동아박 — OCR 세션 핸드오프, PDF 면순서 섞임). 18선택형
+서답형4=22문항. 직접 1:1 대조 — **내용 결함 0·A형 0·B형 0**. OCR 고품질(의심점 전부 원본
확대+정답키 교차로 OCR 충실 확정 — 내 저해상도 reads 가 오류원이었음). 단 배치 렌더에 타이핑
혼입 1건 → **corpus_lint 게이트 개선**. corpus `corpus/[학산중][2][25-1-기말] (원본)/`(meta `reviewed`).

### ⭐ 배경 배치 렌더 타이핑 혼입 + corpus_lint 자동검출 게이트
- 증상: 배치 렌더(_cr_haksan2) #1 번호 앞에 단독 'ㄷ'(U+3137) — XML `</hp:container><hp:t>ㄷ
  </hp:t>`. CLAUDE '렌더 중 사용자 타이핑이 숨김 COM 문서로 샘'(강동중 낱자모) 패턴. **코드
  결함 아님·비결정** — 재렌더(_cr_haksan2b)로 해소(단독 자모 grep 0). ⚠️ **배경 배치 렌더는
  작업 중 내 타이핑(툴콜)과 겹쳐 혼입에 더 취약**(검수/렌더 병행의 부작용).
- 게이트 갭: 기존 `corpus_lint._JAMO_RE` 는 **조합용 첫가끝 자모(U+1100-11FF)만** 검사 — 호환자모
  (U+3130-318F: ㄱㄴㄷ)는 보기 라벨이라 제외했었다. 그래서 혼입 'ㄷ'(호환자모)를 못 잡고 lint
  PASS(오염 렌더가 통과). 5개교 반복 발생(강동중·월서중·새본리중·도원중·학산중)인데 자동검출 0.
- 개선: `_LONE_JAMO_RE = <hp:t>단일 호환자모</hp:t>` — **단독 호환자모 1글자가 통째 한 hp:t
  런**이면 타이핑 혼입 FAIL. 보기 라벨 'ㄷ. 가로…'는 마침표+내용이 **같은 런**이라 단독 아님 →
  미검출(오탐 0: 성광중 ㄱ~ㅅ 7항목·시지중·새본리중 박스 전부 PASS 검증). 이제 배치 렌더
  타이핑 혼입이 **검수 전 corpus_lint --xml 로 자동 차단** → 수동 jamo grep 불필요.

### 무회귀 교차검증 + 검수 정상 (meta 상세)
- 성광중 단위 수정·도원중 점이름·범물중 L 단위가 학산중에서 무회귀(B형 0). 보기 박스(#7 단위
  ㄱ~ㅁ·#13 일차함수식 ㄱ~ㅁ)·<조건>+사각형 OABC(#14)·cases(#19 삼중등식 '2x+ay=bx+2y=8'
  원본 충실)·멀티소문항(#19 (1)(2)(3)·#20 (1)(2) — [총 N점] 인라인+소문항 우측정렬)·#15 ① a≤0·
  정답면 [서답형 1~4]·홀수 7쪽 정상. figure 4종(#9·#10·#14·#22) C한계. **교훈 재확인: 확대 전
  결함 단정 금지** — #16·#17·#18 저해상도 오판 3건 전부 원본 확대로 기각(OCR·렌더 정확).

## 신명여중 중1 (폼) 검수 — 박스 마커 직후 LaTeX 마커 깨짐 B형 1건 (2026-06-12)

중1 폼(남색) corpus(신명여중, 동아강 — OCR 세션 핸드오프, 25문항 = 중1 최다·서술형 8개).
직접 1:1 대조 — 내용 결함 0·A형 0, B형 1건. 회귀 `test_content_parser` SM1. corpus
`corpus/[신명여중][1][25-1-기말] (원본)/`(meta `reviewed`).

### ⭐ 박스 마커 직후 LaTeX — 선행 연산자 흡수가 마커의 `>` 를 끌어감 (B-1, #7)
- 증상: `<상자> \frac{1}{3}x+4=-1 …`(풀이과정 상자)에서 발문 끝에 `<상자` 평문 leak +
  풀이과정 수식들이 박스 없이 인라인(`> ⅓x+4=-1 …`).
- 원인: 인라인 수식 분리기의 **선행 연산자 흡수**(능인고 R2 `= - \frac…`)가 마커의 닫는
  `>` 를 비교연산자로 오인해 수식으로 끌어감 → TEXT `<상자 ` + EQ `> \frac…` 로 깨져
  렌더러 `_COND_HEADER_RE` 가 박스 인식 실패. **`<상자> \begin{cases}…` 는 env 경로
  (`_LATEX_ENV_RE`)가 흡수보다 먼저라 원래 안전** — 매천중 #6·월암중 #5·#19·효성중 #19
  전부 env 라 기검수 corpus 무결함(트리거 스캔 확인). `\frac`/`\therefore` 직결만 발화.
- 수정: `_split_box_marker_prefix` — 두 분리기(`_split_latex_commands`·
  `_split_mixed_text_equation`) 선두에서 박스 마커(`<상자>`/`<보기>`/`<조건>`)를 자기
  TEXT 블록으로 떼어 보호 후 나머지만 분리. `<보기> 중` 참조어는 `_RAW_BOX_MARK_RE`
  부정전망이 걸러 가드 미발동(월암중 D3 유지). 수정 후 #7 = `<상자>` 1×1 박스(풀이 3수식
  가운데) + `<보기>` 5×5 폼 정상.

### 검수 정상 확인 (meta 상세)
- #6 ② `(x/60+40)초` 는 원본 인쇄 그대로(옳지않은 것 문제의 의도된 오답 항목 — 원본 확대
  확정)·'않은' 밑줄. #7 ㄷ `ac=ac` 원본 오타 충실(삼동 사본 교차). #21 서술형4 표 인쇄값
  `a`·`-a+2`(학생 연필 오염을 삼동 교차로 정정한 박제값) 표 셀 수식. #24 (가)~(라) kcal 4건
  정자(월서중 kcal 수정 효과). 정답면 [서술형 1~8]·홀수 패리티(7쪽). 저해상도 오판 3건
  (#3·#12·#17) 확대로 기각 — 원칙 재확인.
- C한계: figure 8종(중1 최다). ⚠️ **정답면 머리말 '중 학년 수학'**(학년 빈 폼 원문) —
  정답 구역 머리말 재정의(`hp:header`)에 header_values 미적용. 중앙중 잔여와 동일(추후 숙제).

## 강동고·대구고 수1 (고2 초록폼) 검수 — 그리스+조사 경계·overarc B형 2건 (2026-06-12)

고2 수1 폼(초록) **정식 렌더 1·2호**(완료기반 — 원본 사본 손풀이 만연). 강동고 23문항
(A형 1)·대구고 20문항(B형 2). 직접 1:1 대조. corpus `corpus/[강동고]…`·`corpus/[대구고]…`.

### ⭐⭐ LaTeX 명령 직후 한글 = 명령 미인식 → ₩ literal (대구고 #8·#9·#11 — 고등 광역 지뢰)
- 증상: `0<x<2\pi일 때` → `0<x<2` + **평문 `₩`** + `π`(`\` literal). `\theta라`·`\theta가` 동일.
- 원인: `_LATEX_CMD_RE` 꼬리 경계 `(?:\b|(?=[{^_(\[\d]))` — **한글이 \w 라** `\pi일`(명령
  직후 한글 직결)에서 `\b` 실패 → 명령 미인식. 블록에 다른 매치가 없으면
  `_split_latex_commands` 가 ASCII 경로로 빠져 `\` 가 평문 누수. 그리스 문자+조사 직결은
  **고등(공수1·수1·확통) 전반의 패턴**(α·β·θ·ω·π + 라/가/일/를) — 중등에선 잠복했다가
  고1/고2 전환기에 발화.
- 수정: 경계를 `(?![a-zA-Z])` 로 — 한글·공백·문장부호 전부 경계, `\pix` 같은 더 긴 영문
  명령 접두 오인만 차단. **정밀 스캔**(.testkit/_scan_cmdkorean2.py): 구 정규식 매치 0
  블록 = 대구고 #8·#9·#11 단독. `\(...\)` 구분자 블록(강동고 #4·성서고 #18 등)은
  `_normalize_math_delims` 의 $-경로라 무관 — 기검수 corpus 무영향.

### ⭐ \overarc(호 ⌒) 매핑 누락 (대구고 #10)
- `\overarc{AB}:...=3:4:5` 가 ACCENT_MAP 에 없어 **호 장식 증발**, `{rm {AB}}` 만 렌더.
  `\overarc`→`arch`(HWP 호) 추가 → `arch {rm {AB}}`(완료본 A͡B:B͡C:C͡A 일치).
  `_LATEX_CMD_RE` 에도 overarc 추가(TEXT 경로 안전).

### 강동고 A형 1건 + 검수 정상
- 강동고 #20 서술형3: display 합 수식(1/(2²-1)+…+1/(100²-1))을 OCR 이 `equation`(인라인)
  으로 인코딩 → 발문에 인라인 + 배점 밀림. **`equation_block` 정정**(A형) → [6점] 발문 끝
  인라인 + 수식 가운데(완료본 일치).
- 정상: 소수배점 사다리(강동고 [3.0]~[4.7]·#14=4.4 4.3건너뜀 / 대구고 [3.3]~[4.5])·overline·
  각 로만(cosB·tanC·∠DAE)·Σ 상하한·cases 점화식(#15 홀짝)·절댓값·귀납법 빈칸 BOX(대구고
  #12 ㈎㈏㈐+display 다줄)·(가)(나)(다) 박스·[총 N점]+소문항 우측·그리스 이탤릭·정답면
  [서술형 1~N]·홀수 패리티. 강동고 #1 완료본 자체 문제↔정답 불일치는 인쇄 충실 전사 유지.

### 빌드/배포 (v0.1.15, 2026-06-12 — 사용자 지시)
- 위 수정 전부 포함해 PyInstaller 재빌드 → `배포용/` 배포(robocopy /MIR `_internal` 한정,
  `config.json` 보존) → `--selftest` OK (v0.1.15) + Gemini live OK.

## 상원고·대진고 공수1 (고1 파란폼 1·2호) — 행렬 첫 실측 B형 6건 (2026-06-12)

고1 파란폼 정식 검수 1·2호(원본 직접). **행렬(2022 개정 공수1) HWP 렌더 첫 실측** —
PMATRIX·열벡터 자체는 통과, 주변 텍스트 처리에서 B형 다발. 내용 결함 0·A형 0. 회귀
`test_content_parser` SW1·SW2·DJ1. corpus `corpus/[상원고]…`·`corpus/[대진고]…`(`reviewed`).

### ⭐ env(pmatrix) 직전 식별자 미흡수 — 행렬곱 A 정자/이탤릭 혼재 (상원고 #18)
- `, A\begin{pmatrix}…` 의 A 가 한글 없는 TEXT 조각으로 남아 mixed 분리기의 한글 가드에
  걸려 평문 정자(첫째 A 는 앞 한글 덕에 EQ 승격 — 비대칭). env 원자에 선행 식별자 흡수
  (`_is_eq_lead_char`) + finalize 의 eq·연산자·eq 병합이 `=` 까지 흡수해 식 전체 한 수식.

### ⭐⭐ 행렬곱 AB 오로만화 — '2~4 대문자 항상 로만'의 행렬 예외 (상원고 #22·#12)
- 기하 꼭짓점용 '항상 로만' 규칙이 행렬곱 `AB`·`AC`·`BA` 를 정자로(원본 이탤릭 행렬 변수).
- **파서 스킵만으론 부족** — `latex_to_hwpeq._apply_roman_labels` 가 변환 스크립트 레벨에서
  대문자 연속런을 무조건 `rm{}` 로 감싼다. '행렬' 키워드 문맥이면 `_romanize_point_names`
  가 대문자 런을 **`\mathit{}` 명시 감싸기**(→`it {AB}`, `it {` 직전 런은 변환기 로만화
  스킵 — 도원중 rm 번짐 실증 경로 활용). 기하 선분 AB 로만 무회귀.

### ⭐ 관계연산자 명령 좌변 미흡수 (대진고 #1) + ○ 불릿 수식 흡수 (대진고 #16)
- `<상자> 4x-7 \le 7x-1 \le 3x+15` — 수식이 `\le` 로 시작하면 사이 공백 때문에 좌변
  ASCII 조각(4x-7)이 평문 정자로 떨어짐 → `_EQ_LEAD_OPCMD_RE` 좌변 흡수(한글 경계 보호).
- 박스 ASCII 수식 경로(월암중 #6)의 선행 불릿 분리가 `•·▪◦` 만 알아 ○ 불릿이 수식에 흡수
  (`○ |x|+…=11 ○`) → 항목 줄바꿈 깨짐. ○·〇 추가 + **꼬리 불릿**(다음 항목 경계) 분리.

### ⭐ 정답면 라벨 동기화 비결정 (대진고 — 효성중 메타토큰과 동일 메커니즘)
- COM 저장이 라벨 run 을 비결정 쪼개면 `_sync_essay_label_word` 가 연속 문자열 `[서술형`
  을 못 잡고 relaunder 가 정규화해 혼용 잔존(4중 2회 FAIL). 메타토큰 루프에
  `_label_words_in_xml` 검사 통합 — relaunder 후 균일 시험지인데 혼용이면 sync+renumber
  재실행. **타이핑 혼입 '체 '(음절)** 1회 — 자모 게이트 미검출 대상(음절 게이트는 정상
  조사 run '와 '·'를 ' 오탐 위험으로 보류), 재렌더 해소.

## 다사중 중2 (배포 GUI 사용자 보고) — 보기박스 B형 2건 (2026-06-12)

배포 exe(v0.1.15 이전) 변환물 사용자 보고 2건 — 배포 OCR 캐시 재현 렌더로 수정·검증.

### ⭐⭐ 박스 첫 항목이 인라인 수식으로 쪼개지면 자기완결 오인 — 항목 유출 (#13)
- `<보기> ㄱ. 점 ` + EQ`(6,3)` + `을 지난다. • ㄴ. …`(여러 raw 블록)에서 `_raw_box_end`
  가 첫 블록을 자기완결로 오인(라벨 단독 가드 미발동 — 'ㄱ. 점' 은 라벨+내용) → ㄴㄷㄹ 가
  발문 연속으로 분리돼 **박스 밖 유출**. **다음 raw 가 equation 이고 이후 text 에 후속
  항목 라벨(`• ㄴ.`)이 보이면 박스 연속**(`_ITEM_LEAD_RE`·`_INNER_ITEM_LABEL_RE`).
  학남고 #20형 post(eq+조사, 라벨 없음)는 분리 유지 — 무회귀.

### ⭐ 5×5 보기 폼 첫 줄 빈 단락 — 전 corpus 잠복 cosmetic ('항상 윗줄 띄워짐')
- COM 1×1 박스 작성이 라벨 직후 빈 단락을 남겨 `_inject_bogi_form` 내용 셀 선두가 항상
  빈 줄(다사중 3개 폼 전부 `['','ㄱ…']` 실측 — 기검수 corpus 도 공통이었으나 대조에서
  놓침, 원칙 ③ 실례). 내용 조립에서 선두 빈 단락 strip(태그 제거 후 텍스트 판정).

## 고2 수2(보라) 핸드오프 4종 + 정답 머리말 침범 — B형 3건 (2026-06-13)

핸드오프 4종(경산고·대원고·덕원고 수2 + 대건고 공수1) 캐시 렌더(API 0원) → 완료본 1:1.
경산고·대원고는 결함 0. 덕원고·대건고에서 B형 3건(머리말 strip·캐럿·원문자 줄바꿈) 수정.
회귀 `test_content_parser` DG1·`test_render_fixes` W2(answer-header-neutralize, 2026-06-14 갱신).

### ⭐⭐ 정답 구역 머리말/꼬리말 재정의가 마지막 서술형 문제 페이지를 덮음 (덕원고 #19)
- 증상: 단답형+서술형 **혼합** 수2(덕원고)에서 p4(서술형 #17·18·19 문제 페이지) 머리말이
  "고 학년 수학"(정답 머리말, 학년 빈값)·꼬리말 "(정답)"으로 렌더. p1~3 은 "덕원고 2학년
  수학2" 정상. 같은 보라 수2 폼인 경산고(단답형)·대원고(서술형만)는 header 2개(정답 재정의
  없음)로 정상 — 덕원고만 header 3개(정답 재정의 id=8 잔존).
- 원인: 폼 정답 구역의 머리말/꼬리말 재정의(`hp:header`/`hp:footer` ctrl)가 **마지막 서술형
  #19(부채꼴) 본문과 한 본문 단락**에 들어감(grow 가 #19 슬롯을 정답구역 단락에 삽입). 머리말
  ctrl 이 단락 시작에 있어 #19 가 있는 p4 전체가 정답 머리말을 받는다. **#19 가 재정의 뒤에
  위치 = 페이지네이션 무관 결정적 결함**(중앙중 중3 "header/footer 가 정답 container 와 한
  단락" 동족).
- 수정(`hwp_form_writer`, **첫 본문 단락(secPr=메인 머리말) 뒤**의 재정의만 손대고 메인은 보존,
  `_layout_form` 후·`_fill_form_header` 전 호출): ⚠️ **최초 구현 `_strip_answer_header_redefine`
  (재정의 ctrl 제거)은 relaunder 가 정답 container 를 통째 드롭하는 결함이 있었다**(상원고
  공수2 발견·덕원고도 잠복 — 2026-06-14 절 참조). **현재 = `_neutralize_answer_header_redefine`**:
  재정의 ctrl 을 제거하지 않고 그 inner(subList)를 메인 것으로 **치환**(ctrl 보존 → 정답
  container 살아남음). 표시는 메인=문제 페이지와 같아져 bleed 소거. **부수효과: 정답면 머리말
  학년 빈값 C한계('중/고 학년 수학')도 해소** — 중앙중·새본리중(중3 빨강) 재렌더에서 정답면이
  "중앙중 3학년 수학"·"새본리중 3학년 수학"으로 개선 + 정답 분리·홀수 패리티 무회귀.

### ⭐ 소문항 원문자 항목 ``㉢ A^2`` 캐럿 노출 (대건고 #19 ㉢㉣㉤)
- 증상: 소문항 항목 ``㉢ A^2``(별도 text 블록, caret 표기)가 ``A^2`` literal(``^`` 노출). 같은
  식이 ``\cdots`` 와 섞인 SUB2 ``A+A^2+\cdots+A^{10}`` 는 latex 경로라 정상이었음 — caret 단독만 발화.
- 원인: `_split_mixed_text_equation` 의 "한글·불릿 없으면 평문 반환" 가드가 첨자(``A^2``)를
  통째 평문화. `_MATH_EXPR_RE` 는 ``A^2`` 를 매치하나 가드에서 조기 반환됨.
- 수정: 가드에 첨자 패턴 예외 ``not re.search(r'[A-Za-z0-9][_^]', text)`` 추가 → 첨자 있는
  텍스트는 ASCII 경로 통과 → ``㉢ A^2`` = TEXT ``㉢ `` + EQUATION ``A^2``(위첨자·이탤릭). ``㉠ AC``
  (첨자 없음)는 평문 유지(무회귀). 순수 단독 ``A^2``/``x^2+1`` 은 단일 블록 가드(line 965)로
  TEXT 유지 — 실제 데이터는 접두 있어 변환됨(과변환 회피).

### ⭐ 소문항 원문자 항목이 한 줄에 붙음 — 각 자기 줄 (대건고 #19)
- 증상: ㉠ AC ㉡ CA ㉢ A² ㉣ B² ㉤ C² 가 한 줄로 흐름(완료본 = 각 항목 한 줄).
- 수정 = `hwp_com_writer._is_circled_item_start`(`_CIRCLED_ITEM_RE` = 블록 선두 ㉠-㉻): 발문
  본문 첫 블록 **뒤** 원문자(㉠㉡…)로 시작하는 TEXT 블록 앞에 줄바꿈. 기본(`_write_question`
  stem 루프)·폼(`_put_qbody` head 루프) 두 경로 공유. 인라인 참조('보기 ㉢ 은')는 블록 중간
  이라 미발동. 재렌더로 완료본 일치 확인. (남은 minor: 행렬 ``AC``/``CA`` 평문 vs 완료본
  이탤릭 — 단독 대문자열 행렬 이탤릭은 별개 숙제.)

## 수2 핸드오프 2차 — 번호+유형 이중 라벨·부가문구 배점 B형 2건 (2026-06-13)

수2 핸드오프 5종(강동고·강북고·도원고·수성고·중앙고) 검수. 강동고·강북고(공수1 행렬 —
캐럿/원문자 수정 무회귀 입증)·중앙고는 결함 0. 도원고·수성고에서 B형 2건. 회귀
`test_content_parser`(split-score)·`test_render_fixes` W3(essay-type-label). 무회귀: 대건고
수2(라벨 숨은결함 정정)·도원고·수성고 재렌더 lint PASS.

### ⭐ OCR 번호+유형 이중 라벨 ``[서답형 N][서술형]`` → 폼 라벨과 중복 (도원고 #17~20)
- 증상: 서술형 라벨이 ``[서술형 7] [서술형]`` 이중 표기. OCR 이 번호 라벨 ``[서답형 N]`` 과
  유형 라벨 ``[서술형]``(번호 없음)을 **둘 다** contents 선두에 줌(``[서답형 7][서술형] 그림…``).
- 원인: `_essay_label_and_body` 가 번호 라벨 ``[서답형 7]`` 만 떼고 유형 라벨 ``[서술형]`` 은
  본문에 남김 → 폼이 자기 라벨 ``[서술형 7]`` 을 붙여 ``[서술형 7] [서술형]``. `label_type`
  필드가 이미 유형을 담아 본문 유형 라벨은 중복.
- 수정: `_ESSAY_TYPE_LABEL`(번호 없는 ``[서술형]``/``[단답형]``/``[서답형]``) 추가, 번호 라벨
  추출 후 따라오는 유형 라벨도 본문에서 제거(형태1·형태2 분리형 둘 다). 정상 단일 라벨
  ``[서술형 3]`` 은 무회귀. **숨은결함 정정**: 대건고 수2(기검수)도 1건 있어 재렌더로 해소
  (원칙 ③ 실례). 트리거 스캔: 도원고(7)·대건고 수2(1)뿐.

### ⭐ 점 뒤 부가문구 배점 ``[N점, 부분점수 있음]`` 쪼개짐 미제거 (수성고 #21)
- 증상: 배점 ``[8점, 부분점수 있음] [8점]`` 이중. OCR score 필드 8 + 본문에 ``[8점, 부분점수
  있음]`` 잔존 → 폼이 score 로 ``[8점]`` 추가.
- 원인: 본문 ``[8점, 부분점수 있음]`` 이 인라인 수식 분리로 ``[`` + EQ``8`` + ``점, 부분점수
  있음]`` 으로 쪼개짐. `_strip_split_score` 의 닫는 패턴 `_CLOSE_SCORE_JEOM_RE`(``^점\s*[\])]``)
  가 ``점, 부분점수 있음]``(점 뒤 쉼표+문구)을 못 잡아 잔존. (`_SCORE_TEXT_RE` 는 단일 텍스트
  ``[N점, …]`` 은 잡으나, 쪼개진 split 경로는 별도.)
- 수정: `_CLOSE_SCORE_JEOM_RE` 에 ``,부가문구`` 허용 → ``^점\s*(?:,[^\])]*)?[\])]``
  (`_SCORE_TEXT_RE` 와 동치). 재렌더 단일 ``[8점]`` 확인. 표준 ``[N점]`` 만 렌더(부분점수
  문구 드롭, 범물중 인라인-우선 합의 연장).

## 고1 수(하) 완료기반 9개교 검수 — 집합·경우의수·함수 렌더 버그 8건 (2026-06-14, 커밋 67c2e73)

고1 **공수2기말 슬롯(2023 수하 대체)** 완료기반 9개교(강동·강북·경상·경신·대구외·시지·매천·
창녕·칠성) 파란폼 재렌더 → 완료본 1:1 + **결정적 누수 스캔**(`.testkit/scan_leaks.py` — 전
EQUATION 을 `latex_to_hwpeq` 돌려 출력 backslash[₩ 누수]·TEXT 잔여 LaTeX[\·^{·_{·{}_] 검출).
전부 **결정적 후보정**, 회귀 박제(`test_content_parser` SH1~SH6 + 기존 30 verify). 누수 스캔
**0/9**. 집합과 명제·경우의 수·함수(합성/역함수/유리/무리) 단원에서 잠복하던 함정 다발.

### content_parser (수식 분리기 — 6 갈래)
- **조합/순열 선두 좌측첨자 흡수**(강동고 #12 박스): `{}_{n}\mathrm{C}` 의 빈그룹+첨자 prefix 가
  명령(\mathrm) 직전에 붙으면 `_split_latex_commands` 가 `{}_{` 평문 leak + 첨자내용(`13`)만
  EQ 로 분리(식중간 `={}_{13}\mathrm…`은 명령 run 내부라 정상). `_LEFT_SCRIPT_PREFIX_RE`
  (``\{\}\s*[_^]\s*\{[^{}]*\}\s*$``) 로 latex_start 직전 prefix 를 수식에 흡수.
- **집합 기호 `\{ \}`**(강북고 #14 `Y=\{y|1\le y\le 8\}`): `_LATEX_CMD_RE` 에 ``\\[{}]`` 추가.
  빠지면 `\{` 가 ₩{ 로 새고 set 식이 `Y`·`=\{`·`y` 로 쪼개짐(latex_to_hwpeq 는 `\{`→`"{"` 정상
  매핑이라 분리만 고치면 됨).
- **화살표족**(매천고 #4 ③ `\Leftrightarrow`): `_LATEX_CMD_RE` 에 Leftrightarrow·Rightarrow·
  rightarrow·iff·implies… 추가(긴 것 먼저). latex_to_hwpeq 엔 매핑(LRARROW 등) 있으나 분리기에
  없어 `\Leftrightarrow` 가 TEXT `\`(₩) + bare EQ `Leftrightarrow`(literal)로 쪼개졌다.
  ⚠️ 누수 스캔이 처음 놓침(` \`=백슬래시+공백, `\letter` 아님) → TEXT_LEAK 를 **단독 `\`** 로 강화.
- **중괄호 첨자 ASCII 원자**(시지고 #4 `a^{2}bc`·대구외고 #16 `a_{1}b_{1}`): `_MATH_EXPR_RE` 끝
  `(?![a-zA-Z])` 가 첨자 뒤 영숫자(`a^{2}`+`b`)에서 실패해 bare `a` 로 후퇴 + `^{`/`_{` leak.
  `_MATH_ATOM` 을 ``(?:base _SUBSUP)+`` 반복으로(암묵적 곱 흡수).
- **순수 ASCII 수식 단일블록 평문강등 방지**(매천고 #4 선택지 `(f^{-1})^{-1}=f`): `_split_mixed_
  text_equation`(line 965) + `_parse_content_block`(text 경로) 둘 다 len>1 조건이 단일 EQ 를
  TEXT 로 강등 → `^{-1}` literal. `_split_latex_commands` 의 단일수식 유지(성광중 2026-06-10)와 통일.
- **함수선언 나열 쉼표 보존**(경상고 #12·칠성고 #6 `f:X\to Y, g:Y\to Z`): `_split_one_eq_commas`
  의 스푸리어스-쉼표 방어(학남고 #12 곱셈 잡음용)가 `\to Y` 를 atom·relation 둘 다 아니라 판정→
  공백 병합(`Y g`→HWP `Yg`). `_has_toplevel_relation` 에 `\to`·`:`(사상/함수콜론) 추가. 학남고
  스푸리어스(곱셈) 무회귀(`\to`·`:` 없는 `P(…)`는 여전히 병합).

### latex_to_hwpeq
- **수식 내 한글 음절 사이 공백 → `~`**(강동고 #15 cases 조건 `(x가 정수인 경우)`): HWP 가 bare
  한글 일반공백을 시각적으로 죽여 `x가정수인경우` 로 붙음. `convert` 끝에서 한글-한글 경계 공백을
  `~`(전각)로. ⚠️ `\text{한글}`→`"정수인 경우"`(따옴표 리터럴)는 HWP 가 공백 보존 → **따옴표 밖만**
  변환(따옴표 안 ~ 는 literal 틸드로 샘). 순수 math 간격 불변.

### 검수 운영 교훈
- **누수 스캔이 비주얼 검수보다 빨리 잡는다**: `scan_leaks.py`(결정적) 가 #4·#7 을 전 9교에서
  즉시 검출(비주얼은 페이지별). 단 표현 갭(` \`·`Yg` 공백병합·로만/이탤릭)은 못 잡아 **비전 대조
  병행 필수**. 갭 발견 시 스캔 규칙 강화(단독 `\` 추가).
- **수정마다 영향 entry 만 재렌더**(전수 재렌더 treadmill 회피): raw JSON 스캔으로 패턴 보유 학교
  특정(`\to…,…` = 경상·칠성, arrow = 매천뿐) → 그 학교만 재렌더. 도구 `F:/tmp/suha_render/batch_render.py`.
- 정답면 패리티 전 9교 홀수(렌더 5·5·5·5·7·5·5·5·7쪽) — 문제 짝수 마무리 + 정답 홀수쪽 정상.

## ocr_done 57편 전수 렌더+검수 — 신규 버그 0 + 고3 폼 폴백 + 상원고 정답증발 해결 (2026-06-14)

남은 `ocr_done` 57편(확통 31·공수2중간 10·수하원본 8·공수1중간 6·미적분 2)을 **백그라운드 배치
렌더(`F:/tmp/all_render/batch_all.py`)와 병렬 검수**. 결정적 게이트(누수 스캔 0/57·corpus_lint
--xml·패리티) + 콘텐츠 유형 대표 1:1 비전 대조. **57편 reviewed**(신규 B형 1 — 정답 머리말 재정의
제거가 정답증발 유발, 상원고 발견+덕원고 잠복 동반 수정; 8 수하 수정+기존이 전 단원 커버).

### ⭐ form_registry 고3 선택과목 폼 폴백 (확통·미적분 14+2편 렌더 가능화)
- `match_by_grade("고3", "선택과목")` 가 None(고3 전용 폼 없음) → 고3 확통·미적분 변환 불가였다.
  확통/미적분/기하는 **학년 무관 선택과목**(폼 구조 동일, 학년은 header_values 로 덮어씀) →
  고3 선택과목은 **고2 선택과목(남색) 폼 폴백**. 렌더 검증: "매천고 3학년 미적분" 헤더 정상.
  제품 개선(고3 선택과목 시험지가 변환 가능해짐). 무회귀: 기존 매핑 불변(순수 추가).
- 검증된 콘텐츠 유형(전부 클린): 확통(z표 최상단행 음영·확률분포표 1열 음영·셀 수식 가운데·
  순열/조합/반복순열 Π/반복조합 H·여집합·set·조건박스), 공수1(복소수·켤레 overline·항등식·근호),
  공수2 도형(**점이름 로만+좌표 이탤릭**·원·집합·여집합), 미적분(∫·dy/dx·f′·f″·ln·sin·π·매개변수).

### ⭐⭐ 상원고 공수2 정답 페이지 증발 — 정답 머리말 재정의 제거가 relaunder 드롭 유발 (해결 2026-06-14)
- 증상: 렌더 XML 의 `<hp:container>` 가 **1개(헤더 로고만)** — 정상 엔트리는 4개('정답' 타이틀
  +빈 2). '정답' 0회. 정답 슬롯·라벨([단답형 1~4][서술형 5~9])은 잔존하나 pageBreak 앵커(정답
  container) 소실로 정답이 문제면 p4 하단에 인라인 병합. **결정적**(2회 렌더 동일).
- **bisect(단계별 container 카운트)**: COM 채움·`_build_layout`·전 XML 후처리까지 container=4
  유지인데 **`_com_relaunder`(HWP 재저장)가 4→1 로 드롭**. 스냅샷을 단계별로 relaunder 해보니
  **`_strip_answer_header_redefine`(덕원고 2026-06-13 도입) 직후 스냅샷만** relaunder 가 드롭.
  → 그 strip 이 정답 구역 머리말/꼬리말 **재정의 ctrl 을 제거**한 게 원인. header/footer 텍스트만
  든 run 을 비우든 run 째 지우든 **모두 드롭**(strip 변형 실험) — HWP 가 이 재정의를 **정답
  페이지 영역 anchor 로 구조상 필수**로 쓴다. 제거 시 anchor 가 무너져 재저장이 정답 단락을 통째
  버린다([[hwpx-lineseg-relaunder-trap]] 계열, 단 텍스트 삭제가 아니라 ctrl 삭제 경로).
- ⚠️ **덕원고도 동일하게 잠복 깨짐**: strip 의 설계 케이스(덕원고 수2)도 같은 probe 로 container
  5→2 드롭 확인 — bleed(마지막 서답형 문제면 정답 머리말 침범)만 고치고 **정답 페이지를 조용히
  증발**시키고 있었다(당시 container-after-relaunder 미점검). 상원고는 `corpus_lint --xml` 의
  '정답 블록 없음' FAIL 이 잡아 발견(비전 누락 방지 실례), 덕원고는 안 잡혀 reviewed 로 출하됐었음.
- **수정 = `_strip_answer_header_redefine` → `_neutralize_answer_header_redefine`**: 재정의 ctrl 을
  **제거하지 않고**, 그 header/footer **inner(subList)를 메인(첫 본문 단락) 것으로 치환**한다.
  ctrl 은 살아 정답 container 보존(relaunder 후 container 유지 검증), 표시 텍스트는 메인=문제
  페이지와 같아져 bleed 소거. 이후 `_fill_form_header` 가 메인·재정의 둘 다 "{학교} {N}학년
  {과목}"·꼬리말로 정규화 → 정답면 학년 빈값 C한계("고 학년 수학")와 "(정답)" 오표기도 해소.
  정상 엔트리(재정의 없는 폼: 대건고·계성고)는 no-op. 멱등.
- 검증: 상원고 container 1→4·lint PASS, 덕원고 5(보존)·대건고·계성고 4(무회귀), 경산고·대원고
  수2 무회귀. 회귀 `test_render_fixes` W2(재정의 치환·메인 보존·ctrl 존속·균형·멱등). meta
  `status=reviewed`. **57편 전부 reviewed**.

## corpus 생산자·소비자 운영 — ⭐ 단일 master (2026-06-14 worktree 통합)

> ⚠️ **2026-06-14**: 과거 멀티 worktree(`hwakt-ocr`·`mij-ocr`·`render-review`·`go1-ocr`) 분리
> 모델은 **폐지**. 전부 master 로 머지하고 worktree·브랜치 삭제 → 이제 **`master` 단일 트리**.
> 다른 컴퓨터는 `git clone` 후 master 에서 작업. 현재상태/이어작업 = `docs/HANDOFF.md` 최상단 절.

corpus 자가발전 검수 = OCR(생산) `ocr_done` → 렌더+완료본 1:1 검수 → `reviewed`, 모두 **같은
master 에서**(통합지점 `testchange/master`=origin/master, `BIGSHOL/testchange`). 핸드오프 신호 =
corpus `<폴더>/meta.json` `status`.

- **상세 인계·셋업·남은일 = `docs/HANDOFF_CONSUMER.md`. 소비자 도구 = `scripts/corpus_consumer/`**
  (`watch_handoff`·`corpus_render`·`mark_reviewed`·`match_refs`·`hwp2txt`·`hwp2pdf`, README 포함).
- ⚠️ **분기 주의(여전히 유효)**: 여러 컴퓨터/세션이 협업하면 **커밋 전 `git pull`**(과거 worktree
  공유 시절 master↔hwakt-ocr 2회 충돌·reset 레이스를 비싸게 배움). **`git add -A` 금지**(작업한
  폴더만 literal pathspec) — 미커밋 작업(예: 수성고 공수2 부분 OCR) 오염 방지.
- ⚠️ **.hwp 레퍼런스 PDF 변환 깨짐**(12KB 빈 PDF) → 수하·확통은 `hwp2txt` 텍스트 추출로 1:1.
- ⚠️ **확통 완료본은 N:\…\워드\확통\ 에 있으나 meta 에 `reference_pdf` 미기록**(생산자 갭) →
  `match_refs.py`/`ref_match.tsv` 자동매칭. **3학년 확통 라벨 의심**(N:엔 2학년만) = 생산자 재확인.
- 가짜결함: COM 재시도 혼입('리'류)=클린 재렌더로 소거, 보기 ㄱㄴㄷ·℃=정상(`corpus_lint --xml` 게이트).

## 중2·중3 24-2-기말 완료기반 21교 검수 — 박스 유출·표 캡션 merge B형 다수 (2026-06-16)

중2 11교+중3 10교(완료기반, 통계 단원 다수) 폼 재렌더 → 완료본 1:1. **이전 세션이
"보기/조건 박스 5×5 폼 overflow(C-한계, 내용 보존)"로 분류했던 majors 13건이 사실 대부분
실제 코드 B형**이었다 — XML 에서 **첫 항목만** 박스 안임을 확인하고 "내용 보존"으로 단정했으나
(원칙 ③·"렌더 안 깨짐≠정상"·lint PASS≠정상의 실례), 전수 재대조 결과 **나머지 항목이 박스
밖으로 유출**. 결정적 후보정 + 회귀(`test_content_parser` BX1~4·`test_render_fixes` E2·E3).

### ⭐⭐ 박스 항목 유출 — 불릿/쉼표 나열 박스가 인라인 수식으로 쪼개짐 (`_raw_box_end`)
- 증상: `<조건>`/`<상자>` 박스의 둘째+ 항목이 `</hp:tbl>` **뒤** 평문으로 유출(경일여중3
  #19 '자료의 분산을…', 대구동중2 #19 'x cm'). `_raw_box_end` 가 마커 블록(``<조건> ·
  자료의 평균을``·``<상자> 5cm, 7cm,``)을 **자기완결 박스로 오인** → 이후 블록을 발문연속
  (post)으로 떼어 박스 밖 렌더. OCR 이 박스 항목의 인라인 수식(``a``·``x``)을 별도 블록으로
  쪼개 마커 블록이 미완(불릿/쉼표)으로 끝나는 게 트리거.
- 수정: ① **불릿 머리**(`_BULLET_LEAD_RE` = rest 가 ·•○ 로 시작) + 다음 raw=equation +
  이후 블록에 또 불릿(`_INNER_BULLET_RE`) → 박스 연속(분리 금지). ② **쉼표 끝**(rest 가
  `,`로 끝남=나열 미완) + 다음 raw=equation → 박스 연속. 자기완결 다항목(한 블록 ·item1
  ·item2)+발문연속은 후속 블록에 불릿/쉼표-끝 없어 분리 유지(학남고 #20 무회귀).
- corpus 전수 스캔: 영향 6문항(경일여중3 #9·19·20·22, 대구동중2 #19, 영남삼육중3 #18)만.

### ⭐ 표 캡션 merge — 다블록/박스앞 캡션을 `_tail_start` 가 못 잡음 (공유+폼 두 경로)
- 증상: 캡션이 발문에 인라인되고 배점이 캡션 한가운데 침투(사동중3 #14
  ``구하면?시청률(0|2은 2 [3점]`` + ``%)`` 줄넘침). 원인 갈래: ① 캡션이 ``시청률`` +
  ``(0|2은 2%)`` 처럼 **여러 TEXT/EQ 블록**(단일 blocks[i-1]만 보면 첫 블록 stem 잔류).
  ② 캡션이 **박스 머리(`<상자>`) 앞**(덕원중3 #9·계성중3 #10·동부중3 #11 — cond-header
  분기엔 캡션 역탐색 없었음). ③ 캡션 제목↔범례 큰 공백(``독서량      (단위:권)``)이 35자
  초과로 `_is_table_caption` False. ④ 발문이 ``값은? (단, a>0)`` 처럼 질문 뒤 괄호단서로
  끝나면 종결정규식($앵커)이 못 잡아 발문을 캡션 오인(대진고 확통 #14).
- 수정: **`_caption_run_back(blocks, i)` 헬퍼**(표 앞 TEXT/EQ run 역탐색, 발문 종결형·질문
  마커·그림노트·박스머리·box_member 에서 멈춤)로 `_tail_start` TABLE·cond-header 두 분기
  통일. `_is_table_caption` 에 **질문마커 위치무관 검사**(`_CAPTION_QUESTION_RE`)+**공백
  정규화**(길이판정 전). 폼 `_put_tail` 에 **박스마커 캡션 분기**(`_write_tail` 과 동일,
  폼 경로가 누락이었음). `_write_caption_run` 캡션 TEXT 공백 정규화(우측정렬 깔끔).
- ⚠️ **공유 코드 vs 폼 경로 이원화 주의**: 발문뒤 렌더는 공유(`_write_tail`)지만 폼은
  **별도 `_put_tail`** 을 쓴다 — `_write_tail` 만 고치면 폼 렌더(corpus_render=폼)엔 안 먹는다.
  캡션/박스 수정은 **두 곳 다** 반영해야 함(이번에 `_put_tail` 누락으로 한 라운드 헛돌았음).
- corpus 전수 스캔: 영향 10문항 전부 개선(발문은 stem 복귀·진짜 캡션만 우측정렬). 이미 reviewed
  였던 대진고·상인고·수성고·경명여중3 도 개선(숨은 결함 정정 — 원칙 ③ 실례, OCR JSON 불변).

### A형(OCR JSON) 재인코딩 2건
- 구암중2 #20: 직각삼각형 변 박스(3,4,5,8,12,13)가 figure 로 오인코딩(그림안내 노트로 렌더,
  박스 누락) → `<상자>` 텍스트로 재인코딩. 계성중3 #10·16: 단행 자료가 `\quad` 인라인 수식 →
  `<상자>` 박스(테두리)로 재인코딩(사동중3 #15·덕원중3 #9 동형). 데이터·간격 보존, 테두리만 추가.

### 잔여 C-한계
- figure 그림안내문구(전 corpus·미지원). 영남삼육중3 #4 줄기-잎 캡션은 발문 단서 ``(단, b<c)``
  와 캡션 사이 경계라 인라인 잔존(minor, 내용 완전). 고산중3 #21 서술형 소문항 단 배치 분리(레이아웃).

## 고2 미적분 25-2-중간 캠페인 파일럿(강동고) — 수열 도형 점이름 로만화 확장 B형 1건 (2026-06-16)

차기 캠페인(미개척 25-2-중간) 1번 카테고리 **고2 미적분**(QUEUE_고2미적분_25_2_중간.md, 10교)
파일럿 1호. 원본 PDF(원본+답안, 체크섬용) 300~400dpi 컬럼 크롭 비전 OCR(키리스, API 0원) →
고2 선택과목 남색폼 렌더 → 1:1 대조. 20문항(선택형 15+서답형 5) 체크섬 100.0. 내용 0·A형 0,
B형 1건. 회귀 `test_content_parser` MJ1. 미적분 표기(lim·∑·\frac·\ln·\log_2·\sec·sin15°·
e^{4x}·dy/dx·\sqrt·\overline·매개변수·등비급수·역함수) 렌더 검증 — 캠페인 실증.

### ⭐ 수열 도형 점 이름 로만화 — 다토큰 선분명·첨자점+좌표가 이탤릭으로 샘 (MJ1, #8·#14)
- 증상: 기하 문맥(선분·반원·호·그래프 위의 점)에서 **다토큰 선분명**(`A_1C_1`·`A_1A_2`·`C_1D_1`,
  #14)과 **첨자 단 점+좌표**(`P_n(n, f(n))`·`Q_n(n+2, f(n+2))`, #8 그래프 위의 두 점)가 이탤릭
  렌더. 같은 문장의 `BA_1`·`BC_1`·`O_1`(단일 토큰)은 이미 로만이라 한 문장에 정자/이탤릭 혼재.
  원본은 점 이름 전부 정자(로만) — 한국 교과서·평가원 표기. 수열·도형 점 문제(미적분/기하/수1)에
  공통인 광역 결함(중등엔 첨자 점이름이 드물어 잠복).
- 원인: `_romanize_point_names` 의 `_BARE_UPPER_EQ_RE` 는 **단일 토큰**(또는 `BA_1` 처럼 첨자
  하나)만 매칭 — 글자마다 첨자가 붙은 선분명(`A_1C_1`)은 미매칭, `_POINT_COORD_RE` 도 점글자와
  여는 괄호 사이 첨자(`P_n(`)를 못 받아 미매칭 → 둘 다 이탤릭 잔존.
- 수정(`content_parser`): ① `_POINT_NAME_SEQ_RE`(첨자/프라임 단 대문자 토큰 2개+ 공백/연접열)
  — 기하 문맥에서 통째 `\mathrm`(점글자+첨자뿐이라 안전). ② `_POINT_COORD_RE` 에 선두 대문자
  **첨자 허용**(`P_n(n,f(n))`→`\mathrm{P_n}\mathit{(n, f(n))}` 점 로만+좌표 이탤릭). **둘 다
  기하 게이트**(`_has_geometry_context`) — 확통 확률변수 `X_1`·`X_2`·`P(X=r)`는 비기하라 이탤릭
  유지(무회귀 검증). 5~6글자 다각형(`ABCDEF` 정육각형)도 `_BARE_UPPER_EQ_RE`(≤4) 한계를 넘어
  SEQ 가 로만화.
- 무회귀: corpus 전수 스캔(`.testkit/_scan_pointname.py` = NEW 패턴이 OLD 미매칭에서 발화하는
  문항) → 영향 **7개교 전부 기하 점이름**(강동고 + 경원고/계성고/혜화여고 공수2 점·다각형,
  남산고/대구고 수1 `A_n`·삼각형, 대륜중 정육각형) — 모두 로만 개선 방향, 확통 random-var 오염 0.
  3 대표(경원고 `C_1(x_1,y_1)` 중심좌표·혜화여고 `ABCDEF` 정육각형·남산고 `A_n O B_n`) 재렌더
  육안+lint PASS·페이지 안정. 도원중/대륜중 좌표 단일점(`A(2,3)`) 무회귀(test MJ1).

### ⭐ 수열/집합 나열 쉼표 보존 — '두 수열 \{a_n\}, \{b_n\}' 쉼표 드롭 (KD2, 경덕여고 2호 #18·#19)
- 증상: 조건상자 안 '두 수열 \{a_n\}, \{b_n\}이 수렴하고' 의 쉼표가 사라져 `\{a_n\} \{b_n\}` 으로
  붙음. 발문(별도 블록 e+t(", ")+e)은 정상이나, **박스 텍스트(한 블록 inline)**에서만 발화 —
  `_split_latex_commands` 가 `\{a_n\}, \{b_n\}` 를 한 수식으로 합치고, `_split_one_eq_commas` 의
  **스푸리어스 쉼표 방어**(학남고 #12 곱셈 잡음용)가 `\{a_n\}` 을 원자/관계식/list_term 어느 것도
  아니라 판정 → 곱셈 잡음으로 오인해 공백 병합(쉼표 드롭).
- 원인: `_is_atom_item` 가 `\{…\}`(수열/집합 표기)를 나열 항목으로 인정 안 함. 두 수열 A, B 는
  명백한 나열인데 곱셈 조각으로 오판.
- 수정: `_is_atom_item` 에 `re.fullmatch(r"\\\{.+\\\}", p)` 추가 — 통째 `\{…\}` 항목은 수열/집합
  이름 → 원자. 그러면 두 항목 모두 원자 → 스푸리어스 방어 미발동 → 개별 수식+TEXT(", ") 쉼표 보존.
  스푸리어스(P(A)=16/9, P(B) 곱셈)·다항 나열(2x^2, 7x, 6)은 무회귀(둘 다 \{…\} 아님).
- 무회귀: 전수 스캔(`\{..\}, \{..\}` JSON 값) 영향 4개교(경덕여고+강동고/대진고 수1·혜화여고 공수2)
  전부 쉼표 복원·재렌더 lint PASS. 회귀 test_content_parser KD2. 경덕여고: #9 cases 분기함수·
  #15·#18·#19 조건상자 박스뒤발문연속 정상, 플라이 사본 학생 손풀이 위 인쇄 발문 판독.
