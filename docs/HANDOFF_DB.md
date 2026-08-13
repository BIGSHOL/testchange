# 문제 DB (N: 기출 → 문항 DB) — 이어작업 핸드오프

> **이 문서 하나로 원격/다른 PC 에서 바로 이어서 작업할 수 있게** 정리했다.
> 파이프라인 코드는 `db/`, 설계 배경은 커밋 `61a2431`, 렌더·파서 규약은 루트 `CLAUDE.md`.
> 최종 갱신: 2026-08-13.

---

## 0. 지금 상태 (30초 요약)

| 항목 | 값 |
|---|---|
| 인덱싱 대상 | **5,925편** (N: 전수 23,395파일 → 파일명 파싱 → 중복 12,979 제거, 2020년 이후) |
| 판독 완료 | **136편 / 3,094문항** (진행률 2.3%) |
| 정답 확보 | **2,483 (80.3%)** |
| 마지막 체크포인트 | `e7dc3eb` (2026-08-12) |
| 중단 사유 | 작업 PC 가 **원격 접속 중 셧다운** |

**판독 결과는 전부 git 에 있다** — `db/ocr_pilot/`(269개 = 본문 136 + 정답 133),
`db/extracted/`(100), `db/solve/`(63). 커밋된 JSON 을 세면 마지막 체크포인트 수치와
정확히 일치한다 = **유실된 판독분 없음**.

git 에 없는 것은 전부 재생성 가능한 것들뿐이다:
`db/exam_index.db`(인덱스) · `db/pages/`(판독용 PNG 616MB) · `db/n_inventory.tsv`(N: 스캔).

---

## 1. ⚠️⚠️ 시작 전에 — exam id 는 인벤토리 순서에 매달려 있다

`db/build_index.py` 는 **DB 를 지우고**(`DB.unlink()`) 그룹을 정렬한 순서로 id 를 다시 매긴다.
그래서 **N: 스캔 결과가 달라지면 id 가 통째로 밀리고**, 기존 `db/ocr_pilot/<id>.json` 이
**엉뚱한 시험지에 붙는다**. 형식은 멀쩡하고 audit·lint 도 통과하는, 조용히 오염되는 종류다.

- 실측(2026-08-13): 다른 PC 에서 재스캔하니 **28,473개** — 원래 23,395개보다 늘어 있었다.
- 그래서 **`db/n_inventory.tsv` 를 git 추적으로 바꿨다 = id 앵커**.
  어느 PC 에서 언제 재구축해도 같은 id 가 나오게 하는 단일 출처다.

### 지켜야 할 규칙
1. **TSV 가 이미 있으면 `scan_inventory.py` 를 돌리지 않는다.** 스캐너는 ① 최초 생성
   ② 새 시험지를 **의도적으로** 편입할 때만.
2. 앵커로 커밋할 TSV 는 **현재 id 를 만들어낸 원본**(= 지금까지 작업하던 PC 의 것)이어야 한다.
3. 인덱스를 재구축했으면 **항상** `python db/verify_ids.py` 로 대조한다.
4. 새 시험지를 편입해 id 가 밀리는 게 불가피하면, 먼저 `verify_ids.py --remap` 으로
   기존 136편의 새 id 를 확인하고 `db/ocr_pilot/*.json`·`db/extracted/*.json`·`db/solve/*`
   파일명을 함께 옮긴다(옮긴 매핑을 커밋 메시지에 남길 것).

---

## 2. 5분 안에 시작하기

```powershell
git pull                                   # 안전장치(scan_inventory·verify_ids·스키마) 받기
```

### (A) 작업하던 PC — `db/exam_index.db` 가 살아 있는 경우 ← 정상 경로
```powershell
git add -f db/n_inventory.tsv              # 현재 id 를 만든 원본 인벤토리 = 앵커. 최초 1회만
git commit -m "data(db): exam id 앵커 - N: 인벤토리 스냅샷 추적"

.venv\Scripts\python.exe db\queue.py status    # 136편 done / 3,094문항 이 보이면 정상
.venv\Scripts\python.exe db\verify_ids.py      # id 대조 (전부 일치여야 함)
.venv\Scripts\python.exe db\audit.py           # 내용 무결성 (오류 0 이어야 함)
```
→ 이상 없으면 **바로 §4 판독 루프**로 간다.

### (B) DB 가 없는 PC — JSON 에서 재구축
```powershell
# ⚠️ n_inventory.tsv 가 git 에 있으면 그걸 쓴다. 없을 때만 스캔(10분, N: 연결 필수)
.venv\Scripts\python.exe db\scan_inventory.py

.venv\Scripts\python.exe db\build_index.py     # → exam_index.db (5,925편)
.venv\Scripts\python.exe db\verify_ids.py      # ⚠️ 여기서 불일치가 나오면 멈추고 §1 로
.venv\Scripts\python.exe db\queue.py scan      # 판독 JSON 기준으로 done 상태 복원
.venv\Scripts\python.exe db\ingest.py          # 본문 → questions 테이블
.venv\Scripts\python.exe db\merge_answers.py   # 정답면 추출본 병합
.venv\Scripts\python.exe db\solve_merge.py     # A·B 교차 일치분(computed) 병합
.venv\Scripts\python.exe db\audit.py           # 게이트
```
복원 성공 기준: **136편 / 3,094문항 / 정답 2,483(80.3%) / audit 오류 0**.

---

## 3. 파이프라인 지도

```
N: 파일 ──scan_inventory.py──▶ n_inventory.tsv ──build_index.py──▶ exam_index.db
                                                    (exams / exam_files / questions)
                                                          │
      prep_pages.py ◀──────────────────────────────────────┘  (pending 을 꺼내 PNG 렌더)
            │  db/pages/<id>/p1.png …  + meta.json
            ▼
      batch_args.py ──▶ 판독 대상 목록(JSON)
            │
            ▼  ⭐ 세션 비전 판독(구독 요금제, 외부 OCR API 금지)
      db/ocr_pilot/<id>.json          본문
      db/ocr_pilot/<id>.answers.json  정답면(있는 편만)
            │
   ingest.py ─▶ questions        merge_answers.py ─▶ answer(printed)
   solve_export.py ─▶ db/solve/<id>.questions.json ─(독립 2회 풀이 A·B)─▶ solve_merge.py
            │                                                          answer(computed)
            ▼
        audit.py (게이트) ──▶ checkpoint.py (1,000문항마다 커밋·푸시)
            │
            └──▶ query.py (조회) / export_supabase.py (웹 업로드 산출물)
```

각 스크립트는 `--help` 없이도 **파일 상단 docstring 에 사용법**이 있다.

---

## 4. 판독 루프 (실제 작업)

### 4-1. 페이지 준비
```powershell
.venv\Scripts\python.exe db\prep_pages.py --limit 6          # 다음 6편
.venv\Scripts\python.exe db\prep_pages.py --limit 6 --with-ref  # 완료본 있는 편 우선(정답 교차 가능)
.venv\Scripts\python.exe db\batch_args.py --limit 6          # 판독 대상 목록 출력
```
- 산출: `db/pages/<id>/p{n}.png`(폭 1100px) + `src.pdf` 사본 + `meta.json`.
- 네트워크 드라이브를 반복해 읽지 않으려고 **PDF 를 로컬로 복사한 뒤** 렌더한다.
- `needs_pdf_convert=1`(HWP 만 있는 편)은 대상에서 빠진다 — PDF 가 있는 편부터 한다.

### 4-2. ⭐ 판독은 **세션 비전**으로 (외부 OCR API 금지)
루트 `CLAUDE.md` 규약 그대로다 — 세션 안에서의 판독은 **구독 요금제(내 비전)로 처리**하고
Anthropic/Gemini OCR API 를 호출하지 않는다(`meta.ocr_source = "session-vision"`).
`db/pages/<id>/p*.png` 를 직접 읽어 아래 스키마로 JSON 을 쓴다.
여러 편을 동시에 돌릴 때는 편별로 서브에이전트에 맡기되, **한 편은 한 에이전트가 통째로**
판독한다(페이지를 쪼개면 문항이 경계에서 잘린다).

### 4-3. 본문 JSON — `db/ocr_pilot/<exam_id>.json`
```jsonc
{
  "meta": { "exam_id": 4347, "school": "…", "grade": 1, "subject": "공수1",
            "year": 2025, "semester": 1, "round": "중간",
            "pages": 8, "ocr_source": "session-vision", "ocr_date": "2026-08-13" },
  "header": { "title": "2025년 1학기 중간고사 …" },
  "questions": [
    { "number": 1, "score": 2.8, "type": "객관식", "label": null,
      "contents": [ { "type": "text", "value": "두 다항식 A=5x^{2}-4x+6 … 하면?" } ],
      "choices": [ { "number": 1, "contents": [ { "type": "equation", "value": "x^{2}-3x+7" } ] } ]
    }
  ]
}
```
- `meta` 는 **학교·학년·과목·연도·학기·회차까지 채운다** — `verify_ids.py` 가 id 밀림을
  잡는 근거이고, 비어 있으면 판정이 약해진다(실측: 136편 중 8편이 근거 빈약).
- 블록 `type`: `text` / `equation` / `equation_block` / `figure` / `table`(내용은 `rows`).
- 수식은 **LaTeX 로 저장**한다(웹 표시·검색 + 후일 HWP 변환에 함께 쓴다).
- `type`: `객관식` / `서술형` / `단답형`. 서술형 소문항은 `sub_questions`.
- 못 읽은 부분은 지어내지 말고 `[판독불가]` 로 남긴다(audit 이 경고로 잡는다).

### 4-4. 정답 JSON — `db/ocr_pilot/<exam_id>.answers.json`
정답면이 **인쇄돼 있는 편만**. 본문 파일을 건드리지 말고 따로 낸다(병합은 결정론적으로).
```jsonc
{ "exam_id": 4347, "answer_pages": [7, 8],
  "items": [ { "number": 1, "answer": "②", "solution": "", "topic": "", "difficulty": "" } ] }
```
- 객관식 정답은 **원문자**(①~⑤). 서술형은 최종답 문자열.
- 정답면이 아예 없으면 파일을 만들지 않는다 → `merge_answers.py` 가
  `solution_status='no_source'` 로 표시한다(**결함이 아니라 원본 미인쇄**).

### 4-5. 적재·검증
```powershell
.venv\Scripts\python.exe db\ingest.py --exam 4347        # parse/build 통과 + 수식 누수 0 검증 후 적재
.venv\Scripts\python.exe db\merge_answers.py --exam 4347
.venv\Scripts\python.exe db\merge_answers.py --verify    # 완료본(.hwp) 보유 편은 교차 대조
.venv\Scripts\python.exe db\audit.py --exam 4347
```
`ingest.py` 는 **적재 전에** `parse_ocr_response`/`build_document` 를 태워 *우리 변환기로
렌더 가능한 데이터인지* 확인하고, `latex_to_hwpeq` 로 **수식 누수(`\` 잔존)** 를 검사한다.
실패하면 적재하지 않는다 — 그 편의 JSON 을 고쳐 다시 돌린다.

### 4-6. 정답이 없는 편 — 독립 2회 풀이
```powershell
.venv\Scripts\python.exe db\solve_export.py             # 결측 문항 → db/solve/<id>.questions.json
#   → 서로 모른 채 두 번 푼다: db/solve/<id>.A.json, <id>.B.json
.venv\Scripts\python.exe db\solve_merge.py --dry        # 대조만
.venv\Scripts\python.exe db\solve_merge.py              # 일치분만 채움(answer_source='computed')
```
**A·B 가 갈리면 비워 둔다 — 추측 금지.** 수학 정답은 하나만 틀려도 DB 신뢰도가 깨진다.

---

## 5. 커밋 규약 (체크포인트)

```powershell
.venv\Scripts\python.exe db\checkpoint.py        # 1,000문항 경계를 넘었으면 커밋 + 푸시
.venv\Scripts\python.exe db\checkpoint.py --force
```
- **`db/` 만 커밋한다.** 이 저장소는 여러 세션이 동시에 쓰므로 `git add -A` 로 남의
  미커밋 작업을 삼키면 안 된다(루트 `CLAUDE.md` 규약).
- 원격은 `testchange`(= `origin`, BIGSHOL/testchange). 푸시 거부되면 `git pull` 후 재시도.
- 작업 PC 가 꺼진 전례가 있어 **주기적으로 남기는 게 핵심**이다. `queue.py` 는 WAL 이라
  급정전에도 DB 가 깨지지 않고, `queue.py scan` 으로 산출물 기준 복구된다.

---

## 6. 함정 모음 (비싸게 배운 것들)

| 함정 | 내용 |
|---|---|
| **exam id 밀림** | §1. 재구축 후 `verify_ids.py` 필수. 형식은 멀쩡해 lint 로 안 잡힌다 |
| **`answer_source` 컬럼** | 세션 중 `ALTER` 로 만들어 스키마에 없었다 → 재구축하면 `merge_answers`·`solve_merge` 가 "no such column" 으로 죽는다. 2026-08-13 `build_index.py` 스키마에 편입 |
| **`n_inventory.tsv` 부재** | 스캐너가 레포에 없어 다른 PC 에서 인덱스를 만들 수 없었다 → `scan_inventory.py` 신설 |
| **표(table) 블록** | `value` 가 아니라 `rows` 에 내용이 있다. 안 펼치면 표가 통째로 사라져 문항을 풀 수 없다(구산고 #9 에서 발각) |
| **부모 score 이중계산** | 부모 `score` 는 소문항 총점인 경우가 많다. 배점 체크섬은 부모가 있으면 부모만, 없으면 소문항 합 |
| **정답면 없음** | 결함이 아니다. `solution_status='no_source'` 로 구분하고 §4-6 으로 채운다 |
| **네트워크 드라이브** | N: 는 느리다(전수 스캔 10분+). `prep_pages` 가 PDF 를 로컬 복사하는 이유 |
| **정답 출처 혼입** | `printed`(원본 인쇄) / `computed`(검산) 를 절대 섞지 않는다 |

---

## 7. 다음 할 일

1. **작업 PC 에서 `db/n_inventory.tsv` 커밋**(id 앵커 확정) — 최우선.
2. `queue.py status` → `verify_ids.py` → `audit.py` 로 136편 건강 확인.
3. 판독 재개: `prep_pages.py --limit 6 --with-ref`(완료본 있는 편 = 정답 교차 가능) 부터.
   2024~2025 년도가 우선(`batch_args.py --year-min 2024`).
4. 1,000문항마다 `checkpoint.py`.
5. 여유가 생기면 `export_supabase.py` 로 웹 업로드 산출물 갱신.

### 품질 기준선 (36편 833문항 시점 측정)
- 완료본 교차 대조 **184/186 (98.9%)** — 불일치 2건은 PDF 쪽이 더 정확했다
- 객관식 정답 분포 최대 편차 **2.7%p**(균등) — 판독 편향 없음
- audit 오류 **0건**
