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
