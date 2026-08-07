# 핸드오프 — 웹 변환 서비스 (2026-08-07)

다른 PC 에서 이어서 작업하기 위한 인계 문서. **이 문서만 읽으면 현재 상태와 다음 할 일을
알 수 있게** 썼다.

---

## 0. 지금 어디까지 왔나

배포 exe 를 남에게 주려다 **API 키가 config.json 에 평문으로 나간다**는 문제에 부딪혔고,
결론적으로 **웹 서비스로 가는 게 근본 해결**이라 새 프로젝트를 시작했다.

| 구성요소 | 위치 | 상태 |
|---|---|---|
| 변환 엔진 | `D:\시험지 한글화` (이 리포) | ✅ 완성 |
| 사용자 PC 도우미(커넥터) | 같은 리포 `agent.py` + `agent.spec` | ✅ **이미 완성돼 있었음** |
| **웹 프론트 + 서버 API** | `D:\hwp-convert-web` | 🟡 코드 완성, **미배포** |
| GitHub 저장소 | — | ❌ 미생성(로그인 필요) |
| Vercel 프로젝트 | — | ❌ 미생성(로그인 필요) |

---

## 1. 왜 이 구조인가 (핵심 제약)

**한글(HWP) COM 은 한글이 설치된 Windows 에서만 돈다.** 그래서 서버가 `.hwp` 를 만들 수
없다. 렌더만 사용자 PC 의 도우미가 맡는 구조가 된 이유다.

```
브라우저                     Vercel                    사용자 PC
────────                   ────────                  ──────────
초대코드 입력          →   코드 검증
PDF 열기(pdf.js)
페이지·크롭 이미지     →   Gemini 크롭검출 / OCR
                      →   DeepSeek 정답·해설
                      ←   문항 JSON
localhost:8765 호출 ──────────────────────→  HWP 도우미(한글 COM)
HWP 다운로드        ←──────────────────────  .hwp
```

**이 구조가 해결하는 것**
- API 키가 **Vercel env 에만** 있다 → 배포물에 키가 안 나간다(원래 문제).
- 받는 사람은 **브라우저 + 한글**만 있으면 된다(exe·키 불필요).
- 초대코드·횟수제한이 서버에서 자연스럽게 걸린다.
- PDF→이미지를 브라우저에서 하므로 업로드 용량·serverless 시간제한·원본 보관 부담이 없다.

⚠️ **Claude 구독으로 변환을 대신하는 방안은 불가**(약관: 구독 중개). CLAUDE.md 의
"세션 내 변환 = 구독 / 배포 = API" 원칙 그대로.

---

## 2. 웹 프로젝트 (`D:\hwp-convert-web`)

로컬 git 저장소로 커밋돼 있다(`a60e7c7`). **원격이 없어 다른 PC 에서 받으려면 아래 3-A 를
먼저 해야 한다.**

```
api/_lib.ts          API 키·Gemini 호출·JSON 추출 (키는 여기서만 읽음)
api/_usage.ts        초대코드 사용 횟수(KV 있으면 영구, 없으면 메모리 폴백)
api/_ocrPrompt.ts    ⚠️ 자동 생성 — 엔진 EXAM_OCR_PROMPT(8,901자) 사본
api/verify.ts        초대코드 검증(차감 안 함)
api/consume.ts       변환 성공 후 1회 차감
api/crop-detect.ts   Gemini — 페이지 → 문제영역 bbox
api/ocr.ts           Gemini Flash — 크롭 → 문항 JSON(엔진과 같은 프롬프트)
api/solution.ts      DeepSeek — 정답·해설·단원·난이도
src/App.tsx          코드입력 → 업로드 → 진행로그 → 다운로드
src/lib/pdf.ts       pdf.js: PDF → 페이지/크롭 이미지
src/lib/connector.ts 127.0.0.1:8765 커넥터 호출
scripts/sync-prompt.mjs  엔진 프롬프트 → api/_ocrPrompt.ts 재생성
```

⚠️ **OCR 프롬프트는 엔진이 단일 출처다.** `api/_ocrPrompt.ts` 를 손으로 고치지 말 것 —
corpus 검수로 축적된 규약이 8,900자에 담겨 있고 계속 갱신된다. 엔진이 바뀌면:

```bash
cd D:\hwp-convert-web
node scripts/sync-prompt.mjs "D:\시험지 한글화"
```

### 상태
- `npm install` 완료, `npm run build` **통과**, `tsc` 타입체크 **통과**
- 실제 API 호출은 **아직 한 번도 안 해봤다**(키·배포 전) — 검증 필요

---

## 3. 다음에 할 일 (순서대로)

### A. 계정 로그인 — ⚠️ 사람이 직접 해야 함(브라우저 인증)
현재 이 PC 는 GitHub=BIGSHOL, Vercel=chrismathone 으로 로그인돼 있다.
목표 계정은 **st2000423@gmail.com**. **별도 PowerShell 창**에서(세션 안에서는 TUI 가 안 됨):

```powershell
gh auth login --hostname github.com --git-protocol https --web
gh auth switch                      # 계정이 여러 개라 활성 계정 전환
vercel login st2000423@gmail.com    # 메일의 Verify 클릭
gh auth status ; vercel whoami      # 확인
```

### B. 저장소 생성 + 푸시
```powershell
cd D:\hwp-convert-web
gh repo create hwp-convert-web --private --source=. --push
```

### C. Vercel 연결 + 환경변수
```powershell
cd D:\hwp-convert-web
vercel link
vercel env add GEMINI_API_KEY production
vercel env add DEEPSEEK_API_KEY production
vercel env add INVITE_CODES production      # 예: TEST0001:10, FRIEND01:5
vercel --prod
```

| 변수 | 용도 |
|---|---|
| `GEMINI_API_KEY` | 크롭검출 + OCR (필수) |
| `DEEPSEEK_API_KEY` | 정답·해설 (선택) |
| `INVITE_CODES` | `코드:횟수` 쉼표 구분 |
| `KV_REST_API_URL`/`KV_REST_API_TOKEN` | 횟수 영구저장(선택). 없으면 인스턴스 재시작 시 카운트 초기화 |

### D. 커넥터에 새 도메인 허용
배포 도메인이 정해지면 `server/connector.py` 의 `ALLOWED_ORIGINS` 에 추가하고,
`agent.py` 의 `SITE_URL` 도 바꾼 뒤 `agent.spec` 으로 빌드한다.

```python
ALLOWED_ORIGINS = {
    ...,
    "https://<새-도메인>",   # ← 추가
}
```

### E. 커넥터 토큰 인증 (미구현)
`server/connector.py` 에 seam 만 있다: `REQUIRE_TOKEN = False`, `EXPECTED_TOKEN = ""`.
지금은 **로컬의 아무 페이지나 커넥터를 부를 수 있다**(127.0.0.1 바인딩이라 외부 노출은
없지만, 악성 사이트가 로컬 커넥터를 부르는 시나리오는 막지 못한다). 배포 전 채울 것.

### F. end-to-end 검증
로컬에서 `npm run dev` → 도우미 실행 → 실제 시험지 PDF 로 변환해 본다.
**아직 한 번도 통과시켜 본 적 없는 경로**다(특히 커넥터 payload 스키마가 웹이 만든 JSON 과
맞는지 — `server/adapter.py` 가 camelCase 를 기대할 수 있으니 확인 필요).

---

## 4. 알아둘 함정

- **커넥터 payload 스키마**: `server/adapter.py` 는 웹(mathgen)의 camelCase typed-block
  (`subQuestions`·`labelType`)을 기대한다. 지금 웹이 보내는 건 엔진 OCR JSON(snake_case)
  이라 **그대로 맞는지 확인이 필요하다**. 안 맞으면 adapter 를 우회하거나 변환을 넣어야 한다.
- **한도 초과**: Gemini 월 지출 한도에 걸리면 429 `spending cap` 이 온다. exe 는 이제 즉시
  중단하지만(이번 커밋), **웹 API 는 아직 그 처리가 없다** — `api/_lib.ts` 에 추가할 것.
- **비용**: 시험지 1편 ≈ 215원(Gemini 126 + DeepSeek 89). 실측치.
- **Vercel 무료 티어 실행시간**: `api/ocr.ts` 는 `maxDuration=60` 으로 뒀다. 문항이 많으면
  브라우저가 크롭별로 나눠 호출하므로 개별 호출은 짧다.

---

## 5. 이 세션에서 엔진에 한 변경 (커밋 완료)

| 커밋 | 내용 |
|---|---|
| `1bc9bd7` | 각 `ANGLE` 표기 · 도(°) 위첨자 제거 · 프라임 도형 라벨 로만화 |
| `d478d79` | 합성함수 ∘ · 라벨 내부 단위 오염 + 적대적 리뷰 회귀 2건 |
| `16f0c39` | 정답·해설·메타 자동 생성 (DeepSeek V4 Pro) + 적대적 리뷰 8건 |
| `9097422` | 단원 분류 어휘 exe 번들 + 재현 가능한 빌드 게이트 |
| `725b4d2` | 헤드리스 변환 CLI + 비용 로그 cp949 유실 · DeepSeek CSV 누락 |
| `00b1516` | 폼지·OCR 전자동 + 키 입력란 제거 + Claude 제외 + 한도초과 즉시중단 |

**배포본**: v0.1.24 (`배포용/`), zip 은 `D:\시험지한글화_v0.1.24.zip` (137MB).
⚠️ 그 zip 은 `00b1516` **이전** 빌드다 — 위 변경을 반영하려면 다시 만들어야 한다:

```powershell
cd "D:\시험지 한글화"
python scripts\build_release.py      # 빌드 → 산출물 검증 → 배포 → selftest
python scripts\make_release_zip.py   # 배포 zip (개인기록·키백업 제외)
```
