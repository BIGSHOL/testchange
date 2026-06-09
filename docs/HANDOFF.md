# 이어작업 핸드오프 (타 컴퓨터 인수인계)

> 이 문서 하나로 **다른 컴퓨터에서 이어서 작업**할 수 있게 정리. 상세 설계·함정은
> `CLAUDE.md`(루트)와 자동메모리(`C:\Users\<you>\.claude\projects\D---------\memory\MEMORY.md`)에 있다.
> 최종 갱신: 2026-06-10 (커밋 `ac396e2`). ✅ **소스 HEAD=`ac396e2`, 배포 exe=`ac396e2` 빌드 완료**
> (2026-06-10 재빌드·`배포용/` 배포, `--selftest` = `SELFTEST OK (v0.1.14)` + `GEMINI LIVE OK`,
> `config.json` 379B 보존). 강동중 렌더 8건(`f85eb7c`)·**'캐시로 변환' 버튼(`ac396e2`)**·경운중 폼
> 4건·표복구/폼측정/서수'제' 전부 배포 반영됨 → 추가 빌드 불필요.

## 0. 프로젝트 한 줄
PDF 수학 시험지 → HWPX 자동 변환 (PySide6 GUI + Gemini 크롭검출 + Claude OCR + HWP COM 렌더).
파이프라인: `PDF→이미지→크롭검출(Gemini)→OCR(Claude)→JSON→ExamDocument→HWPX(COM)`.

## 1. 저장소 / 원격
- 원격 `testchange` = `https://github.com/BIGSHOL/testchange.git` (푸시는 여기로: `git push testchange master`).
- 메인 브랜치: `master`. 현재 HEAD: `389e974`.
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

## 6. 현재 상태 — 최근 세션 완료분 (master `ac396e2`)
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

## 9. 절대 금지 / 주의
- **`hwp_com.CONVERSION_VISIBLE` 을 True 로 되돌리지 말 것** — 한글 2개 열렸을 때 COM 이
  사용자 포커스 문서에 타이핑(데이터 오염). 기본 False(숨김).
- API 키는 `config.json` 에만. 추적 파일·커밋에 절대 금지.
- 라이브 COM 레이아웃 조작 금지 → 저장 후 XML 후처리(결정적·무크래시). 상세: CLAUDE.md.
