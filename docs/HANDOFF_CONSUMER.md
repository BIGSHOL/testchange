# 핸드오프 — corpus 렌더/검수 소비자 세션 (2026-06-13, 운영모델 갱신 2026-06-14)

다음 컴퓨터/세션이 **corpus 자가발전 검수**를 바로 이어받기 위한 인계 문서.

## 1. 운영 모델 — 단일 master (2026-06-14 워크트리 통합)

> ⚠️ **2026-06-14 변경**: 과거의 멀티 worktree 분리 모델은 **폐지**됐다. 모든 worktree
> (`hwakt-ocr`·`mij-ocr`·`render-review`·`go1-ocr`)와 브랜치를 **`master` 로 통합·삭제**했고,
> 이제 트리는 `F:\시험지변환기`(master) **하나뿐**이다. 생산(OCR)과 소비(렌더/검수)는 더 이상
> 별도 worktree·브랜치가 아니라 **같은 master 에서** 진행한다(여러 컴퓨터가 협업하면 각자
> clone 해 master 를 pull/commit/push). 아래 옛 worktree 표는 **역사 기록**일 뿐 재현하지 말 것.

- **단일 트리/브랜치**: `F:\시험지변환기` = `master`. 원격 `testchange`(= origin, 같은 remote
  `BIGSHOL/testchange`)의 `master` 가 통합지점.
- 핸드오프/완료 신호는 그대로 **corpus `<폴더>/meta.json` `status`**: 생산 끝 = `"ocr_done"`,
  검수 끝 = `"reviewed"` + `review` 블록. 다른 세션/컴퓨터는 `git pull` 로 최신 master 를 받는다.
- **옛 모델(역사, 재현 금지)**: `F:\sihum-hwakt`(hwakt-ocr=확통)·`F:\시험지변환기-mij`(mij-ocr=
  미적분)·`F:\시험지변환기-render`(render-review=렌더/검수)·고1 공수(go1-ocr) 의 격리 worktree
  를 한 .git 공유로 병행. 동시성 사고(reset 레이스)가 잦아 통합으로 정리함.

## 2. 현재 상태 (2026-06-13 기준)

- **canonical `testchange/master` = 1d70291** 이후(소비자 검수 8건 통합 푸시 완료).
- **corpus 129개**: `reviewed` **72** / `ocr_done` **56** / 기타 1.
- 소비자가 이번에 검수·커밋·푸시한 것(고1 02.09 파란폼): **상원고·계성고·대건고·혜화여고 공수1
  중간** (전부 결함 0, clean). render-review → master 머지로 canonical 반영.

### ⚠️ 미커밋/미완성 (메인 트리 로컬)
- 메인 트리(`F:\시험지변환기`)의 untracked 16폴더 중 **15개는 이미 canonical 에 커밋됨**(중복,
  메인이 pull 안 해 untracked 로 남음) — pull 시 정리됨.
- **`[수성고][1][공수2][25-2-중간]` 1개만 meta 없는 미완성**(생산자 진행 중) — 무시.
- 메인 트리에서 `git pull` 하려면 위 중복 untracked 가 FF 를 막으므로 `git clean`(중복 폴더만)
  후 pull 권장. 생산자 트리는 각자 정리.

## 3. 검수 백로그 & .hwp 레퍼런스 이슈

- ready(레퍼런스 실존, 검수가능)은 watch_handoff 기준 ~11건(공수1·수하·혜화 공수2 등 변동).
- **확통(원본기반)도 검수 가능**: 완료본이 `N:\개인\기출\…\워드\확통\<학기>\[학교]…(완료).hwp`
  에 존재. **단 생산자가 meta 에 `reference_pdf` 를 안 적음** → `match_refs.py` 로 자동매칭
  (`scripts/corpus_consumer/ref_match.tsv`): **정확 12 / 유사(회차변형) 7 / 약함 10 / 없음 6**.
- ⛔ **`.hwp→PDF` 변환이 깨짐**(HWP COM 이 외부 .hwp 를 12KB 빈 PDF + 잠금 + Quit hang).
  → **레퍼런스가 .hwp 인 건(수하·확통)은 `hwp2txt.py` 텍스트 추출로 내용 1:1** 한다(PDF 말고).
- 🔎 **데이터 품질 의심 — 3학년 확통 라벨**: "약함" 10건 다수가 corpus `[3]확통` ↔ N: `[2]확통`.
  확통은 통상 2학년 → **생산자가 학년 라벨을 3으로 오기**했을 가능성(또는 진짜 3학년이면 ref 부재).
  생산자(hwakt-ocr)가 원본 PDF 로 재확인 필요.

## 4. 셋업 (다음 컴퓨터에서 재현) — 단일 master clone

```powershell
# 1) clone (worktree 셋업 불필요 — master 하나)
git clone https://github.com/BIGSHOL/testchange.git 시험지변환기
cd 시험지변환기
# 2) 의존성 + 키 (상세는 docs/HANDOFF.md §2)
pip install -r requirements.txt          # PySide6·anthropic·google-genai·pymupdf·pywin32 등
# config.json (루트, gitignore) 에 anthropic/gemini 키 — 검수(캐시 렌더)만이면 키 불필요
```
- python = clone 한 트리의 `.venv\Scripts\python.exe` (또는 시스템 python + requirements).
- `forms/` 는 gitignore(머신 로컬) → 폼 렌더하려면 폼 파일을 이 트리 `forms\` 로 복사/배치.
- HWP COM 시작 smoke test 먼저: `python -c "import win32com.client as w; h=w.Dispatch('HWPFrame.HwpObject'); h.Quit(); print('OK')"`.
- 검수 사이클·가짜결함 주의는 `scripts/corpus_consumer/README.md`.

## 5. 커밋/푸시 규약 (단일 master)

- 검수/생산 모두 **`master` 에 직접 커밋·푸시**: `git pull` → 작업 → `git push testchange master`
  (worktree·render-review 브랜치 분리 없음 — 2026-06-14 통합으로 폐지).
- **검수한/생산한 폴더만 literal pathspec 으로 add**: `git add ":(literal)corpus/[학교]...."`.
  습관적 `git add -A` 는 다른 미커밋 작업(예: 수성고 공수2 부분 OCR) 오염 위험이라 지양.
- 여러 컴퓨터가 협업하면 **커밋 전 `git pull`(또는 `git fetch && merge testchange/master`)** 로
  분기를 막는다(과거 멀티 worktree 시절 reset/분기 레이스를 비싸게 배운 교훈 — 이제 단일
  master 라 단순하지만 pull-before-commit 원칙은 동일).

## 6. 남은 일 (우선순위)

1. **수하 23-2 ×3 + 혜화여고 공수2** 검수(레퍼런스 .hwp → `hwp2txt` 텍스트 대조).
2. **확통 검수**: `ref_match.tsv` 정확 12 + 유사 7 부터(유사는 `대비`본이라 내용 확인). meta 에
   `reference_pdf` 기록은 생산자 몫(정석) 또는 소비자가 매칭값으로 보강.
3. **3학년 확통 라벨 의심 10건** 생산자 재확인.
4. **완료본 없음 6건**(경명여고·경상여고·분성고·숙명여고·신선여고·제일고 확통) = 결정론 체크섬 검증만.

## 7. 회귀/검증
- 코드 변경 시: `tests/test_content_parser.py`·`test_render_fixes.py`·`scripts/verify_output_format.py --all`.
- 렌더 후: `scripts/corpus_lint.py --xml <hwpx>`(정식 게이트).
