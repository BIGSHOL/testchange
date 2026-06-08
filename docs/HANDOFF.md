# 이어작업 핸드오프 (타 컴퓨터 인수인계)

> 이 문서 하나로 **다른 컴퓨터에서 이어서 작업**할 수 있게 정리. 상세 설계·함정은
> `CLAUDE.md`(루트)와 자동메모리(`C:\Users\<you>\.claude\projects\D---------\memory\MEMORY.md`)에 있다.
> 최종 갱신: 2026-06-08 (커밋 `30eb84c`).

## 0. 프로젝트 한 줄
PDF 수학 시험지 → HWPX 자동 변환 (PySide6 GUI + Gemini 크롭검출 + Claude OCR + HWP COM 렌더).
파이프라인: `PDF→이미지→크롭검출(Gemini)→OCR(Claude)→JSON→ExamDocument→HWPX(COM)`.

## 1. 저장소 / 원격
- 원격 `testchange` = `https://github.com/BIGSHOL/testchange.git` (푸시는 여기로: `git push testchange master`).
- 메인 브랜치: `master`. 현재 HEAD: `30eb84c`.
- 클론 후: `git remote -v` 로 `testchange` 확인(없으면 `git remote add testchange <URL>`).

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
- `.claude/settings.json` PostToolUse 훅: `hwp_com_writer`·`hwp_com`·`latex_to_hwpeq` 편집 시 자동 실행.
- 검증 스킬: `verify-output-format`·`verify-latex-hwpeq`·`verify-ocr-parser-sync`·`verify-hwpx-structure`·
  `verify-equation-metrics`(`.claude/skills/`).

## 6. 현재 상태 — 이번 세션 완료분 (커밋 3ab371e→30eb84c, **빌드 아직 안 함**)
마지막 빌드 버전: `_version.py = 0.1.13`. 아래는 그 **이후 커밋(빌드 전 체크포인트)**:
- `3ab371e` 확통 연산자 이탤릭 · 함수괄호 수식포함 · 단위 m 오인해제
- `2f61919` 표 셀 포함 확통 연산자 이탤릭(`latex_to_hwpeq._STAT_ITALIC_RE`)
- `588c305` `<조건>`/`<보기>` 라벨은 박스 헤더에 인쇄됐을 때만(OCR 프롬프트)
- `30eb84c` **박스 그룹화 #18·#20** — 셀 안엔 (가)(나)만, 발문 연속은 박스 밖 + CLAUDE.md 정리
  - `ContentBlock.box_member` 태그를 raw OCR 경계에서 부착(`content_parser._raw_box_end`·
    `_finalize_contents`·`_tag_box_run`) → 렌더러 `_split_tail_post` 가 박스 뒤 발문 연속을
    박스 밖으로. 서술형 배점은 발문 연속 뒤로 미룸(`defer_essay_score`). 기본·폼 경로 동일.
  - 양 경로 캐시 렌더 검증 완료(#18·#20 = (가)(나)만 박스, 발문 박스 밖, [7점] 우측정렬).

## 7. 미해결 / 다음 작업
1. **빌드·배포** — 위 6의 체크포인트들이 아직 exe 로 안 들어감. 사용자 승인 후
   `0.1.14` 로 올려 빌드(`_version.py`)·배포.
2. **#20 `<조건>` 라벨** — 캐시 OCR 잔재. 프롬프트는 이미 "박스 머리에 인쇄됐을 때만" 으로
   수정됨(`588c305`) → **실변환(재OCR)하면 `<상자>`(무라벨)로 해소**. 확인하려면 `--reocr=20`.
3. **폼 레이아웃 과여백** — 함수괄호 수식화로 수식 높이 ↑ → 페이지 수 증가(7→9 관측). #1-2-3 사이
   여백 과다로 다음 단 넘침. `hwp_form_writer._build_layout`(줄용량 CAP) 스마트 단넘김 보정 필요.
4. **객관식 표 누락**(미해결) — 단일 크롭 구조화 OCR 이 확률분포표를 "요약"해 통째 누락. 서술형은
   `_merge_missing_passages`(전사 2-pass)로 복구하나 객관식 표는 아직(전사+표 구조 복원 필요).
5. **#9 "시행을36번" 띄어쓰기** — OCR 뿌리. 후보정 여지.

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
| `gui/main_window.py` | PySide6 GUI·ConversionWorker·토큰비용 로깅 |

## 9. 절대 금지 / 주의
- **`hwp_com.CONVERSION_VISIBLE` 을 True 로 되돌리지 말 것** — 한글 2개 열렸을 때 COM 이
  사용자 포커스 문서에 타이핑(데이터 오염). 기본 False(숨김).
- API 키는 `config.json` 에만. 추적 파일·커밋에 절대 금지.
- 라이브 COM 레이아웃 조작 금지 → 저장 후 XML 후처리(결정적·무크래시). 상세: CLAUDE.md.
