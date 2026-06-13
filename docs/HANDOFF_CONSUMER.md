# 핸드오프 — corpus 렌더/검수 소비자 세션 (2026-06-13)

다음 컴퓨터/세션이 **corpus 자가발전 검수**를 바로 이어받기 위한 인계 문서.

## 1. 운영 모델 — 생산자·소비자 (멀티 worktree)

corpus 작업은 **격리 git worktree** 로 역할 분리되어 병행 진행된다(한 .git 공유). 모든 worktree
는 `F:\` 아래, 공유 .git 은 메인 트리 `F:\시험지변환기\.git`.

| worktree | 브랜치 | 역할 |
|---|---|---|
| `F:\시험지변환기` | `master` | 메인/고1 공수 OCR 생산(go1-ocr 와 연동) |
| `F:\sihum-hwakt` | `hwakt-ocr` | **확통** crop/OCR 생산 |
| `F:\시험지변환기-mij` | `mij-ocr` | **미적분** crop/OCR 생산 |
| `F:\시험지변환기-render` | `render-review` | **렌더/검수 소비자(이 역할)** |

- **통합지점 = `testchange/master`**(= origin/master, 같은 remote `BIGSHOL/testchange`).
  생산자들이 자기 브랜치를 여기로 머지/푸시, 소비자는 여기서 핸드오프를 받고 검수결과를 여기로 보낸다.
- 생산자 핸드오프 신호 = corpus `<폴더>/meta.json` `"status": "ocr_done"` 커밋.
- 소비자 완료 신호 = 같은 meta `"status": "reviewed"` + `review` 블록.

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

## 4. 소비자 셋업 (다음 컴퓨터에서 재현)

```powershell
# 1) 격리 worktree (메인 트리에서)
git -C F:\시험지변환기 worktree add F:\시험지변환기-render -b render-review testchange/master
# 2) forms junction (gitignore 라 worktree 에 없음 — 메인 공유), .venv·scripts 는 메인 것 절대경로 사용
New-Item -ItemType Junction -Path F:\시험지변환기-render\forms -Target F:\시험지변환기\forms
# 3) 도구는 추적됨: F:\시험지변환기-render\scripts\corpus_consumer\ (이 인계의 산출)
```
- python = `F:\시험지변환기\.venv\Scripts\python.exe`(메인 venv 절대경로).
- HWP COM 시작 smoke test 먼저: `python -c "import win32com.client as w; h=w.Dispatch('HWPFrame.HwpObject'); h.Quit(); print('OK')"`.
- 검수 사이클·가짜결함 주의는 `scripts/corpus_consumer/README.md`.

## 5. 푸시/머지 규약 (충돌 예방 — 비싸게 배운 것)

- 소비자는 **render-review 브랜치**에 커밋, `git push testchange render-review`(master 직접 X).
- canonical 반영은 **`git merge-tree` 0충돌 검증 → `commit-tree`(작업트리 무접촉) → push** 로
  render-review 를 master 에 머지(이번 1d70291 방식). 라이브 작업트리 머지 금지(생산자 경합).
- **핵심: 생산자들이 "커밋 전 pull 안 함" 으로 반복 분기**(master↔hwakt-ocr 2회 충돌, 둘 다
  0충돌 머지로 해소). 각 생산자는 **새 핸드오프 커밋 전 `git fetch && merge testchange/master`** 할 것.
- 공유 트리이므로 **절대 `git add -A` 금지**(생산자 untracked 오염) — 검수한 폴더만 literal
  pathspec `:(literal)corpus/...` 로 add.

## 6. 남은 일 (우선순위)

1. **수하 23-2 ×3 + 혜화여고 공수2** 검수(레퍼런스 .hwp → `hwp2txt` 텍스트 대조).
2. **확통 검수**: `ref_match.tsv` 정확 12 + 유사 7 부터(유사는 `대비`본이라 내용 확인). meta 에
   `reference_pdf` 기록은 생산자 몫(정석) 또는 소비자가 매칭값으로 보강.
3. **3학년 확통 라벨 의심 10건** 생산자 재확인.
4. **완료본 없음 6건**(경명여고·경상여고·분성고·숙명여고·신선여고·제일고 확통) = 결정론 체크섬 검증만.

## 7. 회귀/검증
- 코드 변경 시: `tests/test_content_parser.py`·`test_render_fixes.py`·`scripts/verify_output_format.py --all`.
- 렌더 후: `scripts/corpus_lint.py --xml <hwpx>`(정식 게이트).
