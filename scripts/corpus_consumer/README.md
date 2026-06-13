# corpus 렌더/검수 소비자 도구

> ⚠️ **2026-06-14: 멀티 worktree 폐지 → 단일 `master`.** 과거엔 격리 worktree(render-review 등)
> 에서 소비자 세션을 돌렸으나, 이제 모두 master 로 통합됐다. 아래 도구는 그대로 쓰되 **master
> 에서 실행**한다(worktree 셋업 불필요). 자세한 운영모델은 `docs/HANDOFF_CONSUMER.md`.

`ocr_done` 핸드오프된 corpus 를 **렌더 → 완료본 1:1 검수 → `reviewed` 마킹**하는 도구 모음.
모든 스크립트는 `_repo()` 로 repo 루트를 자동탐지하므로 어느 경로에서 실행해도 동작한다.

## 도구

| 스크립트 | 용도 |
|---|---|
| `watch_handoff.py` | corpus 스캔 → ready 핸드오프(=status `ocr_done*` + `reference_pdf`\|`ref_pdf` 가 **실존 파일** + ocr JSON) vs 미완성 분류. `--pull` 로 ff-only pull 후 스캔. |
| `corpus_render.py` | `corpus/<폴더>` 의 `ocr/p*_merged.json` → `write_exam_to_form` 폼 렌더(figure→안내문구, `render_figures=False`). |
| `mark_reviewed.py` | `<폴더> <note>` → meta.json `status=reviewed` + review 블록 주입(멱등). |
| `match_refs.py` | ref 없는 ocr_done 폴더 → `N:\개인\기출` 완료본 매칭(정확/유사/약함/없음 4단계) → `ref_match.tsv`. |
| `hwp2pdf.py` | `<src.hwp\|hwpx> <out.pdf>` → HWP COM PDF 변환. **Quit() hang 회피** 위해 SaveAs 후 `os._exit`(호출측이 `taskkill Hwp.exe`). ⚠️ 외부 .hwp 워드본은 12KB 빈 PDF 가 나올 수 있음. |
| `hwp2txt.py` | `<src.hwp\|hwpx> <out.txt>` → HWP COM `GetTextFile` 텍스트 추출. **.hwp 레퍼런스는 PDF 변환이 깨지므로 텍스트 추출로 내용 1:1 대조**(권장). |
| `ref_match.tsv` | match_refs 산출 매칭 목록(folder ⇥ ref ⇥ tier). |

## 표준 검수 사이클 (AUTO)

1. `git fetch testchange && git merge testchange/master --no-edit` (통합지점에서 핸드오프 수신)
2. `python watch_handoff.py` → ready 목록
3. ready 마다: 고아 Hwp 정리 → `corpus_render.py` 렌더(com_error 면 taskkill 후 재시도) →
   **`python scripts/corpus_lint.py --xml <hwpx>`** 정식 게이트(자모혼입·라벨·정답증발·배점중복;
   보기 ㄱㄴㄷ 오탐 0) → `scripts/render_to_png.py` PNG → 레퍼런스 PNG화(PDF=fitz / **.hwp=hwp2txt
   텍스트 추출**) → 문항 1:1 대조 → clean 이면 `mark_reviewed.py` → 그 폴더만 commit → push.
4. **A형(OCR JSON)·B형(코드) 결함 시에만 멈추고 사용자 보고.** figure→안내문구는 C한계(결함 아님).

## 가짜결함 주의
- COM 오류-재시도 중 혼입(잡 음절 '리'류) = 비결정 → **클린 재렌더로 소거**(데이터/코드 결함 아님).
- 보기 라벨 ㄱㄴㄷ·온도 ℃ = 정상(단순 자모 grep 쓰지 말고 `corpus_lint --xml` 사용).

## 셋업 (다음 컴퓨터) — 단일 master
`docs/HANDOFF_CONSUMER.md` §4 참고. 요지: `git clone` 후 **master 에서 작업**, `forms\` 에 폼
파일 배치, 검수/생산 모두 master 에 직접 커밋·`git push testchange master`(worktree·브랜치 분리
없음 — 2026-06-14 통합). 검수한 폴더만 literal pathspec 으로 add(`git add -A` 지양).
