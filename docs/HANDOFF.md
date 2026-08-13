# 이어작업 핸드오프 (타 컴퓨터 인수인계)

> 이 문서 하나로 **다른 컴퓨터에서 이어서 작업**할 수 있게 정리. 상세 설계·함정은
> `CLAUDE.md`(루트)와 자동메모리(`C:\Users\<you>\.claude\projects\F--------\memory\MEMORY.md`)에 있다.

## 🔴 2026-08-13 — 문제 DB(N: 기출) 재개 절차 · exam id 앵커

작업 PC 가 원격 접속 중 셧다운돼 중단됐다. **판독 결과는 전부 git 에 있다**
(`db/ocr_pilot/` 269개 = 본문 136편 3,094문항 + 정답 133). 날아간 건 재생성
가능한 것들뿐이다 — `exam_index.db`·`db/pages/`(PNG 616MB)·`n_inventory.tsv`.
마지막 체크포인트 `e7dc3eb`(136편 3,094문항, 정답 2,483·80.3%)와 커밋된 JSON 이
정확히 일치하므로 **유실된 판독분은 없다**.

### ⭐⭐ 재개 전 반드시 — exam id 는 인벤토리 순서에 매달려 있다
`build_index.py` 는 DB 를 지우고 그룹을 정렬한 순서로 id 를 다시 매긴다. 그래서
**N: 스캔 결과가 달라지면 id 가 통째로 밀려** 기존 `db/ocr_pilot/<id>.json` 이
엉뚱한 시험지에 붙는다(형식은 멀쩡하고 lint 도 통과 — 조용히 오염된다).
실측: 2026-08-13 재스캔은 28,473개로 원래 23,395개보다 늘어 있었다.

- **`db/n_inventory.tsv` 를 git 추적으로 바꿨다** = id 앵커. **작업하던 PC 가
  켜지면 그 PC 의 기존 TSV(현재 id 를 만들어낸 원본)를 그대로 커밋**할 것.
  다른 PC 에서 새로 스캔한 TSV 를 올리면 id 가 밀린다.
- 인덱스 재구축 뒤에는 **항상** `python db/verify_ids.py` — 판독 JSON 이 들고
  있는 메타(학교·학년·과목·연도·학기·회차)를 DB 행과 대조해 밀림을 잡는다.
- `db/scan_inventory.py` 신설(종전엔 임시 스캔이라 레포에 없어 다른 PC 에서
  인덱스를 못 만들었다). **TSV 가 이미 있으면 돌리지 말 것.**
- `build_index.py` 스키마에 `answer_source` 추가 — 세션 중 `ALTER` 로 만들었던
  컬럼이라 스키마에 없어서, 재구축하면 `merge_answers.py`·`solve_merge.py` 가
  "no such column" 으로 죽는다.

### 👉 이어작업 절차·판독 규약·함정 전부 = **`docs/HANDOFF_DB.md`**
그 문서 하나로 원격/다른 PC 에서 바로 이어서 작업할 수 있게 정리했다(5분 시작 명령,
JSON 스키마 실물, 정답 3경로, 체크포인트 규약, 함정표). 요약만 적으면:

```powershell
git pull                                  # 위 안전장치 3건 받기
git add -f db/n_inventory.tsv             # 현재 id 를 만든 원본 인벤토리 = 앵커
git commit -m "data(db): exam id 앵커 - N: 인벤토리 스냅샷 추적"
.venv\Scripts\python.exe db\queue.py status    # DB 살아 있으면 136편 done 이 보인다
.venv\Scripts\python.exe db\verify_ids.py      # id 대조(필수)
```
DB 까지 없으면 `build_index.py` → `verify_ids.py` → `queue.py scan` → `ingest.py` →
`merge_answers.py` → `solve_merge.py` → `audit.py` 순으로 복원한 뒤,
`prep_pages.py` → 세션 비전 판독 → `checkpoint.py`(1,000문항마다 커밋·푸시)로 잇는다.

## 🟢 현재 상태 (2026-06-14) — ⭐ 워크트리 통합 완료, 단일 master

> **다른 컴퓨터에서 이어받는 사람은 이 절만 읽으면 된다. 아래 나머지 절은 환경/하네스 레퍼런스다.**

### 🆕 2026-06-23 업데이트 — 원본 8교 검수 reviewed + 파서 B형 다발 수정 (커밋 푸시 완료)
- **corpus 검수 진척**: ocr_done 8교 **전부 reviewed** 완료 — 수2 25-1-중간 완료기반 3교
  (경산여고·사대부고·영송여고) + 수2 25-2-중간 원본 3교(성서고·진명여고·학남고) + 확통 25-2-중간
  원본 2교(다사고·동부고). **남은 미완료 corpus = `오성중`(중2 25-2-중간 파일럿, 사용자 의도 보류)뿐.**
- **파서 결함 수정(전부 corpus 전역 숨은결함 정정, 회귀 0)** — 매 수정 전 corpus OLD/NEW 스캔
  (4097문항·8869수식) + 재렌더 고배율 시각 확인 + 단위테스트:
  · 값나열 쉼표 보존(`b,0,√2`·좌표쌍·`f(x),g(x)`)·함수콜 단위(`2g(x)`) — `99d2ff1`
  · `\limits` 제거(`lim lim its` 깨짐)·mid-block 박스마커(`…것은? <보기> ㄱ.`)·A형 OCR 전사오류
    (다사고#9·동부고#17) — `8126286`
  · 선택지 이중마커(`① 14`)·box overflow(라벨없는 풀이박스 뒤 질문)·trailing figure 박스앞 이동 — `dbe8143`
  · reviewed 마킹 커밋: `793fe97`(3교)·`cf26b26`(5교). 회귀 테스트: `test_content_parser`
    VL·EBM·CM·BO·FM, `test_render_fixes` O4·O5.
- **이상문자열 검수 도구 추가**: `.testkit/_stray_scan.py`(렌더 hwpx `<hp:t>` 전수 — 낱자모·
  메타토큰·치환/제어문자). 8교 출력 0건 CLEAN. ⚠️ corpus_lint 게이트엔 미반영(자음자모+조사
  `ㄱ과` 오탐 위험 — 수동 보조 도구로 운영).
- **server/ 웹 커넥터**: 동시 세션이 `89a15f5`(Math-Gen↔로컬 HWP 커넥터+트레이앱)로 커밋 → 통합됨.
- **`.testkit` 대청소**: 1.5GB → 248K(옛 세션 스크래치·PNG·hwpx·review 삭제). CLAUDE.md 참조
  도구(`corpus_render.py`·`_stray_scan.py`·`scan_leaks.py`·`eq_scope_test.py`)·가이드만 보존.
- **다음 할 일(권장 순)**: ① **exe v0.1.23 빌드·배포** — 위 파서 수정이 배포 변환 품질에 직접
  반영됨(쉼표·단위·`\limits`·박스마커·선택지마커·overflow·figure). ② 차기 캠페인 OCR 미착수분:
  확통 ② 4교(사동고·영남고·함지고·효성여고)·중2 25-2-중간 9교·중3 25-2-중간. ③ 미해결: 긴
  객관식 배점 줄넘침 우측정렬(CLAUDE.md 마지막 절, 정답증발 위험 경로·전용 집중 작업).

### 🆕 2026-06-16 업데이트 — OCR 다중 백엔드 + 배포 GUI 정리 (exe v0.1.17 배포·selftest OK)
- **OCR 백엔드 다중화 + 품질 자동 라우팅 구현·배포**: Claude 단일 → 품질 3단계 자동 분기
  (born-digital/고QC → `gemini-3.5-flash`, 스캔/저품질 → `gemini-3.1-pro-preview`). seam =
  `OCREngine._stream_message` 한 곳. 비용 5~7배↓. **Anthropic 키 선택사항화**(Gemini 키만 있어도
  변환). config `OCR_BACKEND`(auto 기본)·`GEMINI_PRO_MODEL`·`GEMINI_FLASH_MODEL`·`QC_CLEAN_SCORE`
  + GUI OCR 엔진 드롭다운. **⭐ 자가발전 corpus·ocr_eval 은 Sonnet 고정**(OCREngine 기본
  backend=claude 가 config 를 honor 안 함=의도, testkit/score_ocr 명시). 상세 = CLAUDE.md
  "OCR 백엔드 다중화" 절 + 메모리 `ocr-engine-quality-routing`.
- **렌더/배포 GUI 수정**(전부 배포): ① 서술형 소문항 배점 **인라인 우선**(공간 부족 시에만 줄바꿈
  우측정렬 — 합의 #2, force_break 폐기) ② **부정 선택문 부정어 볼드+밑줄**("옳지 않은 것" —
  합의 #11, `ContentBlock.bold`) ③ 폼 자동 미일치 시 **기본 서식 폴백**(차단 안 함) ④ 그림 렌더
  옵션 폐지(항상 안내 박스) ⑤ 툴팁·로그 일반 사용자용 간소화.
- ⚠️ **이 PC config 의 ANTHROPIC_API_KEY 가 401(invalid)** — Gemini 정상이라 기본 무영향,
  Claude 백엔드 쓰려면 키 갱신 필요.
- 커밋: `082737c`(OCR 라우팅)·`df4609b`(폼폴백·그림제거)·`b28164c`(배점인라인·로그)·
  `9e32abe`(부정어 강조) → `testchange/master` 푸시. 회귀: verify 30/30·단위테스트 전부 PASS.


- **워크트리·브랜치 전부 정리됨 → 이제 `master` 단일 트리 하나뿐.** 과거에는 한 PC에서
  멀티 worktree(`hwakt-ocr`=확통, `mij-ocr`=미적분, `render-review`=렌더/검수, `go1-ocr`=고1
  공수)로 역할 분리해 병행했으나(아래 §HANDOFF_CONSUMER 의 옛 모델), **2026-06-14 전부 master 로
  머지하고 worktree·브랜치 삭제**. → **다른 컴퓨터는 그냥 `git clone` 후 `master` 에서 작업**한다.
  worktree 셋업·브랜치 핸드오프 불필요(옛 `docs/HANDOFF_CONSUMER.md`·`scripts/corpus_consumer`
  의 worktree 절차는 **폐지/역사 기록**).
- **모든 corpus 캠페인 산출이 master 에 반영됨**: 확통 31교+ OCR, 미적분(성서고·매천고), 고1
  공수1·공수2 27편/10교, 그리고 검수 `reviewed` 다수. (옛 worktree 4종의 모든 커밋이 master
  조상으로 포함됨을 검증함.) 원격 `testchange/master`(=origin/master, `BIGSHOL/testchange`)에도
  동기화 완료.
- **진행 중 캠페인 = `corpus/QUEUE_*.md`** 의 상태표로 추적(이게 "다음에 뭘 OCR/검수하나"의
  단일 출처): `QUEUE_확통.md`·`QUEUE_고1_확장.md`(고1 공수)·`QUEUE_고2미적분.md`·`QUEUE_고3미적분.md`
  등. `ocr_done`/`reviewed`/`pending` 표시. corpus 폴더의 `meta.json` `status` 가 진실값.
- ~~유일한 미완 1건: 수성고 공수2중간 부분 OCR~~ → **2026-06-14 마무리 완료**:
  `corpus/[수성고][1][공수2][25-2-중간] (원본)` = 선택형 Q20~23 + 서답형 1~10 신규 OCR로
  완성(33문항·100점 자력검산·lint PASS, `ocr_done`). 캠페인 잔여는 수성·영송 공수2기말(2023
  수하 원본 부재로 보류)뿐 — 상세 `corpus/QUEUE_고1_확장.md`.
- **되돌리기 안전장치**: 통합 직전 master 스냅샷 = git 태그 `backup/pre-merge-master-20260614`
  (= 옛 `265e1be`).
- **이어작업 셋업 요지**(상세는 아래 §2): `git clone` → `pip install -r requirements.txt` →
  `config.json`(API 키, gitignore) → 한글(HWP) 설치 → `python main.py`. corpus 검수는
  `python scripts/corpus_consumer/watch_handoff.py` 로 ready 목록 확인 후 `corpus_render.py`.
> 최종 갱신: 2026-06-16 (OCR 다중 백엔드·배포 GUI 정리, 위 🆕 절). 이전: 2026-06-14(워크트리 통합).
> ✅ **배포 exe = v0.1.17 (2026-06-16, 이 PC 빌드·배포·selftest OK + GEMINI LIVE OK)** —
> OCR 라우팅·배점 인라인·부정어 강조·폼 폴백·그림옵션 폐지·로그 간소화까지 **전부 반영**.
> (이전 stale 노트: ~~배포 exe 97b577d 시점, 월암중 6건 미반영~~ — v0.1.17 로 해소됨.)
> 🔁 **월암중 중2(천재이) 타학교 교차검증** = 중2 폼 2번째 corpus(완료기반). B형 6건 수정:
> ① `\begin{cases}` 박스 literal(`_LATEX_ENV_RE` 통째 원자 — **매천중 #6도 같은 숨은 결함**이
> 었음) ② 박스 나란히 수식 병합(깊이 0 더블스페이스 경계) ③ 발문 `<보기> 중` 박스 오인
> (참조어 부정전망 — 상원중 이연분 B형 해결, 상원중 #16 JSON 원본 복원) ④ `y=-\frac` 의 y
> 평문(연산자 흡수 후 식별자 재흡수) ⑤ 폼 밑줄 강조 소실(`_put_block` underline_run).
> 도원중 점이름·단위 수정의 중2 무회귀 확인(#12 점좌표·#18 cm²). 회귀: `test_content_parser`
> W1~W5(16케이스)·`test_render_fixes` M2·P. 무회귀 재렌더: 매천중·도원중·상원중·상인고×2·
> 능인고 XML lint 전부 PASS. 상세 = CLAUDE.md "월암중 중2 (폼) 타학교 교차검증" 섹션.
> 최종 갱신(이전): 2026-06-11 (이 PC, `56dac24` — 점이름·단위 구현 + 상원중 교차검증).
> ✅ **HWP COM 블로커 해소**: 이 PC 의 `Dispatch("HWPFrame.HwpObject")` FontCache 크래시
> (§6-c)는 **재부팅으로 정상화** — COM smoke test OK, corpus 폼 렌더·PDF/PNG 전 구간 통과.
> 🔧 도원중 중1(남색 폼) 첫 corpus 검수 = `hwp_form_writer` 빈 단 회귀 2건 수정(발문 속 ①
> 마커 오인 + `_repair_column_overflow` 자가치유, `56dac24`) + 진단 2건 **구현 완료**(2026-06-11):
> ① 점이름 로만+좌표 이탤릭(`rm P it {(a,~b)}` — HWP `rm` 은 뒤 전체로 번져 `\mathit` 명시 필수,
> `latex_to_hwpeq._mathit_pattern` + `content_parser._POINT_COORD_RE`) ② 변수/숫자+단위 백틱
> 얇은공백(`a\mathrm{cm}`→`a rm`cm`, `_backtick_rm_units`). 회귀 `test_render_fixes` N·O.
> 🔁 **상원중 중1(지학사) 타학교 교차검증** = 위 두 수정이 다른 학교에서 무회귀(서답형4 #21
> `A(a-5,b+3)`·`B(ab+6,3a-b)`·삼각형 `ABC` 점이름 / #1·#16·서답형3 단위 백틱). 두 번째 중1 corpus.
> 상세 = CLAUDE.md "도원중 중1 (폼) 자가발전 검수" + "상원중 중1 (폼) 타학교 교차검증" 섹션.
> 최종 갱신(이전): 2026-06-10 늦은 세션 (메인 PC, HEAD `5d97335`).
> ✅ **배포 exe = `11f5fc5` 빌드 완료, v0.1.15**(2026-06-10 일괄 빌드·`배포용/` 배포,
> `--selftest` = `SELFTEST OK (v0.1.15)` + `GEMINI LIVE OK`, `config.json` 379B 보존).
> 그 후 정리 2커밋(코드 무변경 — 재빌드 불필요): `e94d119` 불용 삭제(`verify_all.py`·루트
> `.env`(미사용 실키, 코드는 config.json 만 읽음)·빈 `templates/`), `5d97335` 골든셋 기준
> XML 개명(`hwpx_조암` → `data/골든셋기준_조암중_hwpx해제본/`, 참조 6곳 동기 — §8 지도 참고).
> 이 빌드 = corpus 검수 시리즈 누적분: `0ca05e4`·`b25cf4a`(중앙고 확통 파일럿+학교급 수정),
> `3a75f3c`·`509baff`(corpus SOP·결정적 lint·후보선별), `22266a1`(상인고 공수1 4건 — 쉼표근·
> 총점·overline·답지라벨), `f3ed2eb`(상인고 수1 — bigstar★·박스 brace 첨자), `f4225ec`
> (**빈칸 `\boxed`→BOX{} 박스·소문항 (i)(ii) 수식·각 로만·R4 거대문항 단독 단**), `a7d58c3`
> (**서술형·단답형 혼합 라벨·괄호base 거듭제곱 `(1+h)^n`** — 능인고 타학교 교차검증).
> 상세 = CLAUDE.md "완료본 기반 corpus 검수 시리즈" 섹션 + `corpus/REVIEW_PROTOCOL.md`(SOP)
> + `corpus/*/meta.json`(시험지별 결함·검증 기록). 빌드 게이트 = pytest 51 + verify 30 + 키 0.
> 배포본(`6eb7b99`) = 정답 페이지 증발 수정(배점 폴백 MoveSelParaEnd → 정확 span 삭제) +
> 표 캡션 우측정렬(합의 #8) + 잎 셀 토큰별 수식(합의 #10), verify 28→30. 검증 = 강동중 캐시
> 재렌더(API 0원) + pytest 51 + verify 30/30. (Codex PC 의 HWP COM 시작 블로커는 그 PC 로컬
> 문제 — 메인 PC 는 COM smoke test OK, corpus 렌더도 메인 PC 에서 전부 수행.)

## 0. 프로젝트 한 줄
PDF 수학 시험지 → HWPX 자동 변환 (PySide6 GUI + Gemini 크롭검출 + Claude OCR + HWP COM 렌더).
파이프라인: `PDF→이미지→크롭검출(Gemini)→OCR(Claude)→JSON→ExamDocument→HWPX(COM)`.

## 1. 저장소 / 원격
- 원격 `testchange` = `https://github.com/BIGSHOL/testchange.git` (푸시는 여기로: `git push testchange master`).
- 메인 브랜치: `master`. 현재 HEAD는 이어받은 PC에서 `git rev-parse --short HEAD` 로 확인.
- 클론 후: `git remote -v` 로 `testchange` 확인(없으면 `git remote add testchange <URL>`).
  - ⚠️ PC 마다 원격 이름이 다를 수 있다(어떤 PC는 `origin`). `git remote -v` 로 실제 이름 확인 후 그 이름으로 push.

## 2. 환경 세팅 (새 컴퓨터)
1. **Python 의존성**: `pip install -r requirements.txt` (PySide6, anthropic, google-genai,
   pymupdf(fitz), pywin32, resvg_py, Pillow 등).
2. **한글(HWP) 설치 필수** — COM 렌더(`HWPFrame.HwpObject`). 한컴오피스 한글 필요(Windows 전용).
3. **API 키** → `config.json`(루트, **gitignore됨, 절대 커밋 금지**):
   ```json
   { "anthropic_api_key": "sk-ant-...", "gemini_api_key": "AIza..." }
   ```
   (배포본은 `배포용/config.json` 에 별도 보존 — robocopy `/MIR` 는 `_internal` 에만.)
4. 동작 확인: `python main.py` (GUI) 또는 `python main.py --selftest`(임포트 점검).

## 3. ⭐ 무료 테스트 하네스 (API 0원 반복 검증) — 이어작업의 핵심
파서/렌더(`content_parser`·`hwp_com_writer`·`hwp_form_writer`·`latex_to_hwpeq`) 변경은
**API 호출 없이** 캐시로 반복 검증한다. 도구는 repo 에 포함(`scripts/`):

- `python scripts/testkit.py <PDF> --render-only` → 캐시만 사용, **API 절대 호출 안 함**, HWPX 출력.
- `python scripts/render_to_png.py <OUT.hwpx>` → HWPX를 PDF→PNG 로 렌더(육안 검증).
- 프롬프트/OCR 로직 바꿨을 때만: `--reocr=20`(해당 문항만 재OCR, 타깃 과금) 또는 `--reocr`(전체).

**캐시 이전(중요)**: 캐시(`crops.json` + `ocr_p{page}_c{crop}.json`)가 있어야 `--render-only` 가
된다. 기본 위치 `<repo>/.testkit/ocr_cache/<pdf_stem>/` (gitignore됨, git 으로 안 옮겨짐). 둘 중 하나:
- (A) **기존 컴퓨터의 캐시 폴더를 복사** → 새 컴퓨터의 `TESTKIT_CACHE` 위치에 둔다(API 0원 재현).
  - 기존 캐시 현 위치: `D:\tmp\ocr_cache\<pdf_stem>\` (구버전 testkit 기본값).
  - 새 위치 지정: 환경변수 `TESTKIT_CACHE=<경로>` 로 덮어쓰기 가능.
- (B) 캐시가 없으면 **첫 1회만** `--reocr` 로 재생성(API 비용 발생, 그 뒤로는 0원).

**또다른 결정적 기록(2026-06-09)**: exe/GUI 변환 때마다 `<exe-or-root>/ocr/<stem>/p{n}_merged.json`·
`crop/<stem>/*.png` 가 **영구 저장**된다(`temperature=0` → 같은 입력=같은 출력). 이 `p{n}_merged.json`
은 testkit 캐시와 **포맷이 다르다**(워커 후처리 후 병합본). 이걸로 폼 경로를 직접 재렌더하려면
`parse_ocr_response→build_document→write_exam_to_form→render PDF` 한 짧은 스크립트면 된다(이번 세션
`D:\tmp\hn_cache_render.py`·`kw_cache_render.py` 가 그 예 — **D:\tmp 라 repo 밖, 새 PC엔 없음**;
필요하면 그 패턴으로 재작성). `ocr/`·`crop/` 폴더는 gitignore(머신 로컬) → 이어 작업 시 함께 복사.

예) 학남고 확통 회귀 테스트:
```
set TESTKIT_CACHE=D:\tmp\ocr_cache          # 기존 캐시 재사용(있으면)
python scripts/testkit.py "D:\...\[학남고][2][확통][25-2-기말][미래엔] (원본).pdf" --render-only
python scripts/render_to_png.py .testkit\testkit_out.hwpx
```

## 3-b. ⭐ OCR 골든셋 플라이휠 (프롬프트 회귀를 측정으로 잡기)
프롬프트/후보정을 바꿀 때 "좋아졌나 나빠졌나"를 **측정**한다. 크롭 PNG + 정답(ground-truth)
OCR JSON 을 모아, 모델 출력 ↔ 정답을 자동 채점(`scripts/ocr_eval/`, 채점기·테스트는 **stdlib
only** — anthropic 없이도 돈다). 정답 JSON 은 `tests/golden_ocr/` 에 **commit**(PC 간 재현).
```
1) python scripts/crop_dump.py "<PDF>"               # 크롭 PNG 덤프 + crops_manifest.json
2) (크롭 PNG 보고 정답 JSON 작성) → golden_record.py 로 tests/golden_ocr/ 에 기록
3) python scripts/ocr_eval/score_ocr.py "<PDF>"      # 현 프롬프트 vs 골든(캐시 있으면 0원)
   python scripts/ocr_eval/score_ocr.py "<PDF>" --reocr   # 새 프롬프트로 1회 재생성 후 A/B
4) python tests/test_ocr_golden.py                   # 회귀 게이트(_ocr_thresholds.json)
5) (옵션) python scripts/ocr_eval/supabase_sync.py "<PDF>" [--dry-run]  # 누적 분석 push
```
- 후보 캐시는 prompt_signature 별(`.testkit/ocr_eval/<stem>/<sig>/`) — 한 번 OCR 한 프롬프트는
  이후 채점이 0원. figure 채점 위해 **raw 출력**(resolve_figs 미적용) 저장.
- Supabase 는 **개발/수동 전용**(키는 config.json `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`,
  배포 exe 비포함). 스키마: `supabase/schema.sql`(RLS enable·정책 미생성=service_role 만).
  `supabase` 패키지는 `requirements-dev.txt`(lazy import).

## 3-c. ⭐ OCR 프롬프트 보강 반자동 루프 (위험토큰 감사 ② + 보강 ④)
교정만 쌓아선 다음 시험지 OCR 이 안 좋아진다(배포 모델·프롬프트가 정적). **누적 실패 → 패턴 →
프롬프트 보강 → 재측정**의 사람-루프를 반자동화한다. base 프롬프트(`EXAM_OCR_PROMPT`)는 **불변**,
승인된 일반 규칙만 `core/ocr_reinforcement.md` 에 모아 런타임에 `active_prompt()` 가 덧붙인다.
```
0. (키 필요) crop_dump.py "<PDF>" ; score_ocr.py "<PDF>" --reocr   # 실모델 후보 (sig A)
1. python scripts/ocr_eval/audit_ocr.py tests/golden_ocr          # ② 위험토큰 감사(키 0)
   #   — severity 별(기본 medium↑) 플래그. 단일 OCR 출력만으로 작동(골든 불필요).
2. python scripts/ocr_eval/suggest_reinforcement.py "<stem>"      # ④ 실패 채굴 → suggestions/*.md
3. [Claude Code 세션] 리포트 읽고 보강 정련 → 사람 승인 후 core/ocr_reinforcement.md 반영(제안만)
4. python scripts/ocr_eval/score_ocr.py "<PDF>" --reocr           # 보강 반영 새 sig B 후보
5. python scripts/ocr_eval/score_ocr.py "<PDF>" --baseline=<A> --candidate=<B>  # A/B 게이트
```
- **A/B 게이트**(5)는 두 sig 캐시 후보를 골든과 채점해 **집계 델타 + 문항별 회귀 목록**(평균에
  묻히는 개별 악화 노출) + PASS/FAIL(회귀율 ≤ baseline & 신규 악화 0)을 낸다. PASS 일 때만 보강
  채택. 재OCR 안 함(API 0).
- 보강이 바뀌면 `prompt_version._payload()` 가 그 내용을 서명에 포함 → `prompt_signature` 변경 →
  eval 캐시 자동 분리(A/B 성립). 자동적용 금지: 루틴은 **제안**만, 반영은 사람 승인 후.
- 감사/채굴 코어(`risk_tokens.py`·`failures.py`)는 **stdlib only**(키 0). 메커니즘 검증은
  `python tests/test_ocr_failures.py`(합성쌍). 실모델 후보 채굴은 키 필요(없으면 스켈레톤만).

## 4. 빌드 / 배포 워크플로우 (CLAUDE.md '작업 마무리' 필수 준수)
1. **검증** — 위 하네스로 렌더 PNG 육안 확인.
2. **사용자 최종 체크** — 커밋·푸시·배포 전 **반드시 사용자 승인**.
3. **커밋 + 푸시** — `git push testchange master`. 커밋 메시지 끝에
   `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
4. **exe 빌드** — `python -m PyInstaller build.spec --noconfirm` → `dist/시험지한글화/` 의 exe·
   `_internal` 을 `배포용/` 으로 복사(**`배포용/config.json` 보존**) → `--selftest` 임포트 확인.
- 보안: 커밋 전 `git diff | grep -E "sk-ant-|AIza"` = **0건** 확인. `config.json`/`build/`/`dist/`/
  `배포용/`/`*.log`/`토큰사용.csv` 는 gitignore됨.

## 5. 회귀 방지 (자동 강제)
- `python scripts/verify_output_format.py --all` → 출력포맷 합의 28개 검증(위반=exit 2).
- `python tests/test_ocr_golden.py` → 골든 회귀 게이트, `python tests/test_ocr_failures.py` → 채굴/감사
  단위(둘 다 stdlib·키 0). `python tests/test_equation_metrics.py` → 수식 크기 추정 회귀.
- (2026-06-10 신규, 전부 stdlib·키 0) `test_content_parser.py` → 한글↔숫자 띄어쓰기·서수 '제',
  `test_table_recovery.py` → 객관식 표 복구 게이트/파싱/삽입, `test_form_layout.py` → 폼 MC 높이 추정.
- `.claude/settings.json` PostToolUse 훅: `hwp_com_writer`·`hwp_com`·`latex_to_hwpeq` 편집 시 자동 실행.
- 검증 스킬: `verify-output-format`·`verify-latex-hwpeq`·`verify-ocr-parser-sync`·`verify-hwpx-structure`·
  `verify-equation-metrics`(`.claude/skills/`, Codex 는 `.agents/skills/` 미러).

## 6. 현재 상태 — 최근 세션 완료분 (master HEAD `a7d58c3`)

**최신(2026-06-10 늦은 세션) = 완료본 기반 corpus 검수 시리즈** (API 0원, 완료본 직접 판독
→ 우리 파이프라인 렌더 → 1:1 대조. 절차 = `corpus/REVIEW_PROTOCOL.md`):
- `22266a1` 상인고 **공수1**(고1 폼 첫 완료본 검증): 복소근 나열 쉼표 증발(B-1)·배점없는
  소문항 `[총 N점]`(B-2)·`2i\overline{z}`→`2ibarz`(B-3)·정답면 답지라벨 비결정(B-4,
  `_renumber_essay_labels` 결정적 재부여).
- `f3ed2eb` 상인고 **수1**: `\bigstar`→★ 증발·박스 ASCII brace 첨자(`2a_{n+1}`) literal.
- `f4225ec` 상인고 수1 #12(귀납법 증명) 폴리시 7건: **빈칸 `\boxed{}`→`BOX{ ~ ㈎ ~ }` 테두리
  박스**·소문항 (i)(ii) 통째 수식·선행연산자(`= -`) 수식 흡수·"이므로" 한글 누수 차단·라벨
  없는 셀 가운데정렬·각(∠/cos A/45°) 로만체·점화식 뒤 `(n=1,2,⋯)` 공백·**R4 거대문항
  단독 단**(`_SOLO_MC_LINES`=18, `_adaptive_columns(solo=)`).
- `a7d58c3` **능인고 수1**(신사고 — 타학교 교차검증): 이전 수정 견고성 확인 + **서술형·단답형
  혼합 라벨**(`_DUP_LABEL_RE` 단답형, `_renumber_essay_labels(words=)`, lint 혼합 허용) +
  **괄호base 거듭제곱 `(1+h)^n`**(`_MATH_ATOM` 괄호식 원자).
- 검수 코퍼스 누적: 중앙고 확통(원본) / 상인고 공수1·수1 / 능인고 수1(전부 `corpus/`,
  JSON git 추적·PNG gitignore). 회귀: `test_content_parser` 15 cases·`test_render_fixes`
  (bigstar/boxed/labelless/solo/mixed-label)·verify 30.

---

이하 = 직전 세션 기록 (master `ac396e2` 시점).
빌드 버전: `_version.py = 0.1.14` (사용자 결정 "버전업 하지마 — 바뀐 게 없음", 그대로 유지).
**배포 exe = `ac396e2` 빌드 완료**(2026-06-10 재빌드·`배포용/` 배포, `config.json` 379B 보존,
`--selftest` = `SELFTEST OK (v0.1.14)` + `GEMINI LIVE OK`). 강동중 렌더 8건(`f85eb7c`)·'캐시로
변환' 버튼(`ac396e2`)이 이번 세션 추가분. `c77008d`(문서)·`9dfbb9c`(경운중 폼
4건)·`389e974`(표복구/폼측정/서수'제') **전부 배포 반영** → 추가 빌드 불필요. 상세 ✅ 목록은 §7.

**이번 세션 핵심 = 학남고 확통 워드본 1:1 리뷰 후보정 14건** (캐시 재렌더 API 0원, `배포용/ocr`·`crop`
영구기록 기반). 상세는 `CLAUDE.md` "학남고 확통 — 워드본 1:1 리뷰 14건" 섹션. 커밋:
- `3a09217` — 박스 줄바꿈·그림자리·라벨번호수식·메타란분리·수식조각화(이전).
- `a33013e` — 리뷰 11건: 지수(²→2^2)·단위(`\text{g}`→정자)·박스 spill(#14)·로만/이탤릭(#15 A·B 이탤릭/
  #19 점 P 로만)·`[4.3점]` 중복·`-1≤x≤1` 병합·한글↔수식 띄어쓰기·(나) ASCII 수식화.
- `e2f145e` — 박스 긴수식 평문화 방지(`len>20` 필터에 연산자/괄호 예외)·유니코드 부등호(`≤≥≠`→
  `\leq\geq\neq`)·**파일명 충돌 시 윈도우식 `(1)(2)…` 자동 증가**.
- `경운중 폼 리뷰 4건` — 서술형 라벨 중복(`[]`↔`【】` 괄호 혼용)·소단원 메타 토큰 평문 leak(폼에
  [소단원] 템플릿 없으면 토큰 제거)·조건박스 첫줄 들여쓰기·동그라미(ㅇ/○) 크기 통일. 상세는 CLAUDE.md
  "경운중 중3 (폼) 리뷰" 섹션.
- 검증: `verify_output_format --all`(28)·`test_ocr_failures`(20)·`test_ocr_golden`(19+1skip) PASS,
  학남고·경운중 캐시 재렌더 육안 확인 전부 정상.

**0.1.14 빌드(이번 세션 직전)에 이미 포함**(별도 빌드 불필요): `6923e5f` 서답형 4·5 누락 수정,
`ad57f4d` 골든셋 7건, `81c7100`/`f9d33f4` OCR 플라이휠 ②+④, `de6a790` 크롭·OCR 영구저장+OCR
`temperature=0`, `62a061b` Gemini→Claude 폴백 가시화.

### 6-b. Codex 인계 세션 — Claude 사용량 소진 후 이어받은 미커밋 변경 마무리 (2026-06-10)

Claude Code가 사용량 소진으로 끊긴 뒤 Codex가 이어받아 **기존 dirty worktree의 코드/테스트를
검증하고 문서화**했다. 주요 변경 범위:

- `content_parser.py`: 소수/총점 배점 캡처 소실 방지, `[총 N점]` 제거/복원 동기화, 단독 불릿
  시작 정규화, 기하 문맥에서 stat-이탤릭 스킵, 쉼표 나열/스푸리어스 쉼표 판정 완화,
  `\le/\ge/\ne`·명령어+숫자 경계 인식, raw 박스가 다음 항목으로 이어질 때 box spill 방지,
  단일 수식 블록 평문 강등 방지.
- `latex_to_hwpeq.py`: 중첩 `\left...\right` 를 최내곽부터 고정점 치환, `45^\circ` 같은
  중괄호 없는 명령어 첨자 보호, `\setminus` 연산자 증발 방지.
- `ocr_engine.py`: usage 집계 락, 빈 message content 방어(`_msg_text`), 닫는 코드펜스 없는
  JSON 응답 복구, 비-dict question 방어.
- `hwp_com_writer.py`: `_write_condition_box` 의 표 혼합 무한재귀 방지, HWPX zip 재작성 공통화
  및 실패 시 임시파일 정리, 표 음영 borderFill 멱등화.
- `hwp_com.py`/`hwp_form_writer.py`: HWP `Open/SaveAs/PDF` 절대경로화, 저장 침묵 실패 감지,
  HWP Quit 경고 로그, 0행/0열 표 방어, 폼 슬롯 grow 실제 개수 기반 진행, 측정용 HWP finally
  Quit, `_dedupe_essay_labels` 동일 길이 공백 치환(lineseg 보존).
- `gui/main_window.py`: 부분 캐시 완결 마커 경고, 기록 폴더 reset 시점 지연(크롭 게이트 통과 후),
  변환 중 창 닫기 취소 처리.
- 테스트 추가/보강: `tests/test_extract_json.py`, `test_content_parser.py`, `test_render_fixes.py`.

검증 완료(키 0):

```powershell
.venv\Scripts\python.exe tests/test_content_parser.py
.venv\Scripts\python.exe tests/test_render_fixes.py
.venv\Scripts\python.exe tests/test_extract_json.py
.venv\Scripts\python.exe tests/test_equation_metrics.py
.venv\Scripts\python.exe scripts/verify_output_format.py --all
.venv\Scripts\python.exe -m compileall core gui scripts tests
```

추가 수동 검증:
- `verify-latex-hwpeq`: 13개 regex 패턴 컴파일 + `\mid` 공개 API 변환 확인 PASS.
- `verify-hwpx-structure`: `hwpx_writer.py`/`template_loader.py` NS 동일 확인 PASS.
- `verify-ocr-parser-sync`: `_INLINE_LATEX_RE`, `_MATH_EXPR_RE` 컴파일/기본 매칭 PASS.
- `pytest` 는 현재 `.venv`에 미설치라 실행 못 함.

실데이터 재렌더 시도:

```powershell
.venv\Scripts\python.exe scripts/testkit.py `
  "N:\개인\기출\기출작업\194차\[학남고][2][확통][25-2-기말][미래엔] (원본).pdf" `
  ".testkit\codex_after_claude.hwpx" --render-only
```

결과: `loaded 6 pages`, `crops: CACHE`, `OCR: 21 cache, 0 api-call` 까지 정상. 이후
`HWPFrame.HwpObject` COM 시작에서 로컬 HWP 2020이 크래시해 HWPX/PNG 렌더는 미완료.

### 6-c. 현재 로컬 HWP COM 블로커 — 다른 PC/재부팅 후 먼저 재시도

이 PC의 현재 세션에서 `win32com.client.Dispatch("HWPFrame.HwpObject")` 가
`CO_E_SERVER_EXEC_FAILURE(0x80080005)` 로 실패한다. Windows 이벤트 로그의 실제 원인:

- 앱: `C:\Program Files (x86)\HNC\Office 2020\HOffice110\bin\hwp.exe` (`11.0.0.2129`)
- 예외: `.NET Runtime` `System.UriFormatException`
- 스택: `MS.Internal.FontCache.Util..cctor()` →
  `Hnc.Office.Controls.Manager.CultureFontManager.GetPrivateFont()` →
  `Hwp.HwpAppMain.InitApp()`

재현/판별:
- 직접 `hwp.exe -Automation` 은 뜬다.
- 직접 `hwp.exe -Embedding` 도 뜬다.
- **`hwp.exe -Automation -Embedding` 은 같은 FontCache/CultureFontManager 크래시**를 재현한다.
- COM은 등록된 `LocalServer32 = hwp.exe -Automation` 에 `-Embedding` 을 붙이는 경로로 보여 현재
  이 조합에서 죽는다.
- 32비트 PowerShell `New-Object -ComObject HWPFrame.HwpObject` 도 같은 `0x80080005`.
- HKCU CLSID override 실험은 효과 없어 **원복 완료**. 현재 레지스트리 변경 없음.

Codex가 한 로컬 조치(되돌릴 수 있음):
- HNC 폰트 캐시 의심 파일 3개를 삭제하지 않고 백업명으로 이동:
  - `C:\Users\user\AppData\Roaming\Hnc\User\Common\110\Fonts\ShareFont.ini.codexbak_20260610_115155`
  - `C:\Users\user\AppData\Roaming\Hnc\User\Fonts\ListFnt110.ini.codexbak_20260610_115155`
  - `C:\Users\user\AppData\Roaming\Hnc\User\Fonts\PrivateFont110.dat.codexbak_20260610_115155`
- HWP가 `ShareFont.ini`/`PrivateFont110.dat` 는 재생성했다. 필요하면 새 파일을 치우고 `.codexbak_*`
  를 원래 이름으로 되돌리면 된다.

다음 사람의 시작 순서:
1. Windows/HWP 재시작 또는 다른 PC에서 `Get-Process Hwp,WerFault | Stop-Process -Force`.
2. `python -c "import win32com.client; h=win32com.client.Dispatch('HWPFrame.HwpObject'); h.Quit(); print('OK')"`
   로 COM 시작만 먼저 확인.
3. 성공하면 위 학남고 `scripts/testkit.py ... --render-only` 재실행 → `scripts/render_to_png.py` 로
   PNG 육안 확인.
4. 렌더 OK 후 사용자 최종 체크를 받고 exe 빌드/배포(`PyInstaller`) 진행.

## 7. 미해결 / 다음 작업
1. **실모델 OCR 검증(키 필요)** — `config.json` Anthropic 키 만료 가능(과거 PC 기준 401).
   플라이휠 ④의 실측(보강이 실제 sonnet 출력 개선?)·실변환은 **유효 키 필요**. 키 없으면 §3-b/c 의
   stdlib 코어(감사·채굴·단위테스트)까지만 0원으로 가능.
2. **폼 레이아웃 행정렬 여백(설계상)** — 측정 경로(절대경로=프로덕션)는 정상 패킹(학남고 5쪽·경운중
   5쪽 캐시 렌더 검증). 단 한 단에 짧은 문항 2~3개면 **행정렬**(같은 순번이 같은 절대 줄에서 시작 —
   사용자 요구) 때문에 문항 사이 빈줄이 생긴다(버그 아님, N등분 정렬 의도). 줄이려면 행정렬 vs 빽빽
   트레이드오프 재합의 필요.

> ✅ **이번 세션(2026-06-10) 해결**:
> - **폼 과여백(측정 폴백)** — COM ① 측정 실패(보안팝업·gen_py·환경) 시 과거엔 균일 빈줄 4 → 과여백/
>   오버플로우. 이제 `_estimate_mc_heights`(내용기반 추정) + `_adaptive_columns` **빽빽 패킹** 폴백으로
>   교체(측정 실패해도 학남고 5쪽, 측정판과 동일). `_layout_form(..., mc=mc)` 로 문항 전달.
>   회귀: `tests/test_form_layout.py`. ⚠️ **HWP COM 저장은 절대경로 필수** — 상대경로면 HWP 작업
>   디렉터리 기준 저장→빈 출력→측정 0/16→폴백(과거 "과여백" 오진의 원인이 이 하네스 함정).
> - **객관식 표 누락** — `ocr_engine._recover_table`(v0.1.8)로 이미 복구됨. 학남고 #3·#4·#10 표 캐시
>   온전(검증). 결정적 경로 회귀: `tests/test_table_recovery.py`. 실모델 전사 충실도만 키 필요.
> - **한글↔숫자 띄어쓰기** — "시행을36번"→"시행을 36번"(숫자 수식화+`_space_hangul_before_eq`). 더해
>   **서수 접두사 '제'+숫자는 붙여쓰기**(제4사분면 — 과거 "제 4사분면" 오공백 수정, `_ORDINAL_JE_RE`).
>   회귀: `tests/test_content_parser.py`(경운중 #15 ② 렌더 검증).
> - **강동중(중1) 렌더 8건**(`f85eb7c`, 변환 1:1 리뷰 — OCR 무결, 전부 렌더): ⓐ표 셀 한글·범위
>   "6이상 ~ 12미만"·"12 ~ 18" 평문(공백/~보존, `_write_cell`) ⓑ줄기-잎 잎 좌측정렬+줄기:잎 1:3
>   너비(`table_begin(col_widths)`) ⓒ값상자 "<상자> 18 13 …" 공백+가운데(`_is_value_box`) ⓓ#16
>   2열 도수분포표 오음영 수정(z-표 음영은 `LEQ Z LEQ` 시그니처로 한정) ⓔ서술형 배점을 발문
>   끝(표제목·표 앞)으로(`_fill_essay_at` 재정렬·`_is_table_caption`) ⓕ비괄호 '서술형 N.' 라벨
>   중복 제거+단어 통일(`_essay_label_and_body`) ⓖ서술형 [중단원] 메타 누락(소단원 OR 중단원).
>   회귀: `tests/test_render_fixes.py`. 학남고·경운중 캐시 재렌더 회귀 없음(API 0원).

> ✅ 지난 핸드오프의 "빌드·배포 최우선"은 이번 세션에 **완료**(0.1.14 빌드·`배포용/` 배포). 버전은
> 사용자 결정으로 0.1.15 안 올리고 0.1.14 유지(서답형 4·5 수정 등은 0.1.14 빌드에 이미 포함).
> ✅ 위 §7 ✅ 수정들(content_parser·hwp_com_writer·hwp_form_writer)은 **2026-06-10 `f85eb7c` 빌드에
> 반영·배포 완료**.

> ✅ **GUI '캐시로 변환' 버튼**(`ac396e2`, 2026-06-10): 선택한 PDF **파일명(stem)** 기준
> `ocr/<시험지명>/p{n}_merged.json`(영구 기록)으로 **크롭·OCR·Gemini·API 전부 생략**하고 폼 렌더만
> 수행(₩0). `ConversionWorker(cache_only=True)`→`_do_cache_conversion`(merged.json→`build_document`
> →`write_exam_to_form`, `_reset_record_dirs` 호출 안 함=캐시 보존). 워커 배선은 `_run_worker()`
> 공통. **용도**: 폼 채움 실패(파일 잠김) 복구·코드 개선 후 무료 재렌더·반복 검토. 그림은 안내문구
> (render_figures=False; 실제 임베드는 크롭 재해소 필요=추후). 캐시 없으면 안내. dev harness 등가물
> = `F:\tmp\cache_render.py`.

> ⚠️ **이번에 힘들었던 함정(기록)**:
> - **WinError 5(액세스 거부) on `os.replace`** — 출력 `_변환.hwpx` 가 **열려 있으면**(사용자가 보고
>   있거나 HWP 가 잠금) 임시→최종 교체가 막혀 변환이 **기본 서식으로 폴백**(경명여중 사례). 해결:
>   출력이 이미 있으면 `_unique_output_path` 로 새 이름(`_변환(1).hwpx`). 일반·캐시 변환 둘 다 적용.
> - **HWP COM 저장은 절대경로 필수** — 상대경로면 HWP가 **자기 작업디렉터리** 기준으로 저장→빈
>   출력→폼 측정 0/16→폴백(과거 "폼 과여백" 오진의 진짜 원인이 이 하네스 함정이었음).
> - **고아 Hwp.exe 핸들** — 연속 렌더(채움→relaunder→render_to_png)가 겹치면 이전 HWP가 `.testkit`
>   파일 핸들을 놓지 않아 다음 `os.replace`가 WinError 5. COM 작업 전 항상 `Get-Process Hwp |
>   Stop-Process -Force` + 새 파일명.

## 8. 핵심 파일 지도
| 파일 | 역할 |
|------|------|
| `core/ocr_engine.py` | Claude OCR(프롬프트·전사 2-pass 복구·토큰 usage 집계) |
| `core/content_parser.py` | OCR JSON→ExamDocument(인라인 수식 분리·이탤릭/로만·박스 태그) |
| `core/latex_to_hwpeq.py` | LaTeX→HWP 수식 스크립트 변환 |
| `core/hwp_com_writer.py` | 기본 경로 COM 렌더(박스·표 음영·tail 분리) |
| `core/hwp_form_writer.py` | 폼(대수회) 채우기(공유 렌더 + 레이아웃·짝수쪽·정답보존) |
| `core/hwp_com.py` | HWP COM 세션(**`CONVERSION_VISIBLE=False` 필수**) |
| `models/exam_document.py` | ContentBlock/Question/ExamPage 데이터 모델 |
| `gui/main_window.py` | PySide6 GUI·ConversionWorker(`cache_only`=캐시 재렌더)·'캐시로 변환' 버튼·토큰비용 로깅 |
| `core/ocr_reinforcement.md` | 승인된 프롬프트 보강(런타임 `active_prompt()` 가 append, 빈 상태=no-op) |
| `scripts/ocr_eval/` | 플라이휠: `metrics`·`normalize`·`failures`·`risk_tokens`·`audit_ocr`·`suggest_reinforcement`·`score_ocr`·`golden_record`·`prompt_version` |
| `tests/golden_ocr/` | OCR 정답(ground-truth) JSON — commit 됨(PC 간 재현) |
| `corpus/` | 자가발전 검수 코퍼스 — `REVIEW_PROTOCOL.md`(SOP)·시험지별 OCR JSON+meta.json(추적)·pages PNG(ignore, 재생성) |
| `scripts/corpus_lint.py`·`corpus_select.py` | 검수 게이트(JSON 규약·XML 결함)·후보 자동 선별 |
| `data/골든셋기준_조암중_hwpx해제본/` | 수식 크기 골든셋 84개 **기준 XML**(조암중 완성본 해제, README 참고). `test_equation_metrics` 회귀 기준 — **삭제 금지**. (구명 `hwpx_조암` — 2026-06-10 개명) |
| `data/` | 조암중 초기 레퍼런스(원본 PDF·워드 hwp·테스트 hwpx) — `crop_editor`·`tune_equation` 참조 |

## 9. 절대 금지 / 주의
- **`hwp_com.CONVERSION_VISIBLE` 을 True 로 되돌리지 말 것** — 한글 2개 열렸을 때 COM 이
  사용자 포커스 문서에 타이핑(데이터 오염). 기본 False(숨김).
- API 키는 `config.json` 에만. 추적 파일·커밋에 절대 금지.
- 라이브 COM 레이아웃 조작 금지 → 저장 후 XML 후처리(결정적·무크래시). 상세: CLAUDE.md.
