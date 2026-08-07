# 핸드오프 — 웹 변환 서비스 (2026-08-07, **2026-08-08 갱신**)

다른 PC 에서 이어서 작업하기 위한 인계 문서. **이 문서만 읽으면 현재 상태와 다음 할 일을
알 수 있게** 썼다.

> ⚠️ **경로는 PC 마다 다르다.** 이 문서의 `D:\시험지 한글화` = 엔진 리포, `D:\hwp-convert-web`
> = 웹 리포. 예를 들어 2026-08-08 작업 PC 에선 각각 `F:\시험지변환기`·`F:\hwp-convert-web`
> 였다. 명령을 그대로 붙여넣기 전에 자기 PC 경로로 바꿀 것.

---

## 0. 지금 어디까지 왔나

배포 exe 를 남에게 주려다 **API 키가 config.json 에 평문으로 나간다**는 문제에 부딪혔고,
결론적으로 **웹 서비스로 가는 게 근본 해결**이라 새 프로젝트를 시작했다.

| 구성요소 | 위치 | 상태 |
|---|---|---|
| 변환 엔진 | `D:\시험지 한글화` (이 리포) | ✅ 완성 |
| 사용자 PC 도우미(커넥터) | 같은 리포 `server/connector.py` (+`agent.py`·`agent.spec`) | ✅ 웹 계약 연결 완료(2026-08-08) |
| **웹 프론트 + 서버 API** | `D:\hwp-convert-web` | ✅ **배포됨** — https://hwp-convert-web.vercel.app |
| GitHub 저장소 | `BIGSHOL/hwp-convert-web` (private) | ✅ 생성·푸시됨 (Vercel 자동배포 연결) |
| Vercel 프로젝트 | `jaesungs-projects-404a3b31/hwp-convert-web` | ✅ 생성·링크됨 |
| **환경변수(API 키·초대코드)** | Vercel env | ❌ **미설정 — 이게 없으면 변환이 안 된다** |

> ⚠️ **계정 메모**: GitHub `BIGSHOL` = Vercel `bigshol` = `st2000423@gmail.com` 로 **같은
> 사람**이다(2026-08-08 확인). 이전 판 문서의 "목표 계정은 st2000423 / 현재는 다른 계정"
> 서술은 다른 PC 기준이었고, 지금은 계정 전환이 필요 없다.

### 2026-08-08 에 한 일 — 웹↔커넥터 E2E 를 실제로 통과시킴

문서가 "확인 필요"로 남겨 뒀던 **payload 스키마 불일치**는 추측이 아니라 실제였고, 그 외에도
계약이 여러 군데 어긋나 있었다(웹이 보낸 요청은 커넥터에서 **400 즉사**했다). 전부 수정 후
캐시 corpus(경원고 기하 20문항, API 0원)로 **대수회 폼 5쪽 + 정답면까지 렌더 확인**했다.

| 어긋나 있던 것 | 고친 방향 |
|---|---|
| 웹은 `{header,questions}`, 커넥터는 `payload["problems"]` 요구 → 400 | `convert_cli.is_engine_envelope` **한 곳**에서 판별, 두 payload 다 수용 |
| mathgen 템플릿으로 렌더 → 대수회 폼·머리말·정답면 전부 유실 | 엔진 봉투는 **exe 와 같은 경로**(`write_exam_to_form`, 파일명→폼) |
| 산출물 `.hwpx` (폼 바탕쪽 2단 구분선 소실) | 엔진 봉투는 **`.hwp`** 로 굽기(합의 #12). mathgen 은 종전 `.hwpx` |
| 토큰 헤더 이름 불일치(`X-Connector-Token` vs `X-Pairing-Token`) | 커넥터가 **둘 다** 수용 + CORS 허용 목록에 추가 |
| `/health` 가 `hwp_com`, 웹은 `j.hwp` 를 읽음 → 한글 미설치 경고가 영영 안 뜸 | 커넥터가 `hwp` 별칭도 반환, 웹도 셋 다 확인 |
| 커넥터 토큰 인증 미구현(로컬 아무 페이지나 호출 가능) | **기본 켬** + 웹에 연결 코드 입력란 |
| 워커 파이썬이 `Python311` **절대경로 하드코딩** → 그 경로 없는 PC 는 변환 전멸 | `_worker_python()` 탐색(엔진 `.venv` 우선) |
| 웹 API 에 한도초과 즉시중단 없음 | `isFatalApiError`(엔진 규칙과 1:1 대조 검증) + `{fatal:true}` |
| 정답·해설에 **단원 표준 어휘 미주입** → 단원명이 분류표 밖 자유 생성으로 퇴화 | `sync-vocab.mjs` 로 엔진 어휘 동기화 + 파일명→학년·과목 |

회귀 박제: `tests/test_connector_contract.py`(stdlib·COM 없음·API 0원).

### 2026-08-08 배포 — 다중에이전트 감사에서 나온 blocker 를 먼저 막고 올림

첫 배포 직전 29개 에이전트로 5개 축(서버리스 호환·설정·보안·커넥터 origin·데이터 흐름)을
감사하고 각 발견을 적대적으로 반증했다(24건 중 23건 확인·1건 기각). **그대로 배포했다면
① 변환이 100% 실패하고 ② 아무나 API 크레딧을 태울 수 있었다.**

| blocker | 그대로 뒀다면 | 고친 것 |
|---|---|---|
| 유료 API 3개가 **완전 무인증** | URL 만 알면 누구나 Gemini/DeepSeek 소진(1편 ≈ 215원) | `requireInvite()` 를 세 핸들러 첫 줄에 |
| Vercel 본문 **4.5MB 한계** 초과 | 고해상도 스캔 10%가 413 → 첫 페이지에서 중단 | PNG→**JPEG q85** + 최대변 4096 + 예산 초과 시 적응 축소 |
| OCR 해상도 **144dpi** (엔진은 300) | 총 픽셀 4.3배 부족 → 같은 프롬프트로도 인식 저하 | 300dpi 로 상향(위 JPEG 전환 덕에 **오히려 10배 작아짐**) |
| 커넥터 origin 에 배포 도메인 없음 | PNA preflight 실패 → 웹이 영영 "도우미 없음" | env 주입 + `hwp-convert*` 패턴 |
| 트레이 앱 토큰이 **빈 값** | 연결 코드 검사가 통째로 무효(아무 값이나 통과) | `ensure_token()` 분리 + 트레이에 코드 표시 |

실측 근거(기출 24편, 가장 큰 페이지·base64 봉투 포함):

| 렌더 설정 | 최악 payload | 4.5MB 초과 |
|---|---|---|
| 현행 scale=2 PNG (144dpi) | 28.68MB | 1편 |
| 300dpi PNG (4096) | 13.36MB | 3편 |
| **300dpi JPEG q85 (4096)** ← 채택 | **2.57MB** | **0편** |

프로덕션 실증: 무인증 `/api/ocr` → **401**, 잘못된 코드 → **403**, 배포 도메인의 PNA
preflight → `Allow-Origin`+`Allow-Private-Network` 정상, 남의 `*.vercel.app` → 허용 헤더 0개.

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
api/_lib.ts          API 키·Gemini 호출·JSON 추출·한도초과 판정·파일명 파서
api/_usage.ts        초대코드 사용 횟수(KV 있으면 영구, 없으면 메모리 폴백)
api/_ocrPrompt.ts    ⚠️ 자동 생성 — 엔진 EXAM_OCR_PROMPT(8,896자) 사본
api/_topicVocab.ts   ⚠️ 자동 생성 — 엔진 단원 분류 어휘(26종 키 / 963항목)
api/verify.ts        초대코드 검증(차감 안 함)
api/consume.ts       변환 성공 후 1회 차감
api/crop-detect.ts   Gemini — 페이지 → 문제영역 bbox
api/ocr.ts           Gemini Flash — 크롭 → 문항 JSON(엔진과 같은 프롬프트)
api/solution.ts      DeepSeek — 정답·해설·단원·난이도 (파일명→학년·과목→표준 어휘)
src/App.tsx          코드입력 → 연결코드 → 업로드 → 진행로그 → 다운로드
src/lib/pdf.ts       pdf.js: PDF → 페이지/크롭 이미지
src/lib/connector.ts 127.0.0.1:8765 커넥터 호출(토큰·Content-Disposition 파일명)
scripts/sync-prompt.mjs  엔진 프롬프트 → api/_ocrPrompt.ts 재생성
scripts/sync-vocab.mjs   엔진 단원 어휘 → api/_topicVocab.ts 재생성
```

⚠️ **엔진이 단일 출처인 파일이 둘 있다.** `api/_ocrPrompt.ts`·`api/_topicVocab.ts` 를 손으로
고치지 말 것 — 전자는 corpus 검수로 축적된 규약 8,900자, 후자는 분류표 어휘다. 둘 다 빠지거나
낡으면 **조용히 품질만 떨어진다**(OCR 규약 누락 / 단원명 자유 생성). 엔진이 바뀌면:

```bash
cd D:\hwp-convert-web
node scripts/sync-prompt.mjs "D:\시험지 한글화"
node scripts/sync-vocab.mjs  "D:\시험지 한글화"
```

### 상태 (2026-08-08)
- `npm install`·`tsc --noEmit`·`npm run build` **전부 통과**
- **커넥터 E2E 검증 완료** — 캐시 corpus 로 `.hwp` 5쪽(대수회 폼 + 정답면) 생성 확인, API 0원
- 헬퍼 정확도는 **엔진과 1:1 대조**로 검증(파일명→학년·과목·어휘수 5케이스, 한도초과 판정 7케이스)
- **Gemini/DeepSeek 실호출은 아직 안 해봤다**(키·배포 전) — 남은 검증은 그 두 API 뿐

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

### B. 저장소 — ✅ **이미 만들어 푸시함**
`https://github.com/BIGSHOL/hwp-convert-web` (**private**). 다른 PC 에서:

```powershell
gh repo clone BIGSHOL/hwp-convert-web D:\hwp-convert-web
cd D:\hwp-convert-web
npm install
node scripts/sync-prompt.mjs "D:\시험지 한글화"   # 엔진 경로에 맞게
```

⚠️ st2000423 계정이 아니라 **BIGSHOL 계정에 만들었다** — 그때 그 계정만 로그인돼
있었고, 안 올리면 다른 PC 에서 코드를 받을 수 없었다. 원하면 나중에 Settings →
Transfer ownership 으로 옮기면 된다(또는 지우고 새로 만들기).

### C. Vercel 연결 + 환경변수 — 🟡 링크·배포 완료, **env 미설정**
```powershell
cd D:\hwp-convert-web
vercel link --yes --project hwp-convert-web --scope jaesungs-projects-404a3b31  # 완료
vercel --prod                                                                   # 완료
# ↓ 남은 것 — 값을 붙여넣어야 하므로 사람이 직접
vercel env add GEMINI_API_KEY production
vercel env add DEEPSEEK_API_KEY production
vercel env add INVITE_CODES production      # 예: TEST0001:10, FRIEND01:5
vercel --prod                               # env 추가 후 재배포해야 반영됨
```

| 변수 | 용도 | 값 출처 |
|---|---|---|
| `GEMINI_API_KEY` | 크롭검출 + OCR (**필수**) | 엔진 `config.json` 의 같은 이름 필드 |
| `DEEPSEEK_API_KEY` | 정답·해설 (없으면 그 기능만 꺼짐) | DeepSeek 콘솔 (엔진 config.json 에 없으면 별도 발급) |
| `INVITE_CODES` | `코드:횟수` 쉼표 구분 | 직접 정함. **없으면 모든 변환이 403** |
| `KV_REST_API_URL`/`KV_REST_API_TOKEN` | 횟수 영구저장 | Vercel Marketplace → Upstash Redis(무료) |

⚠️ **`INVITE_CODES` 가 비어 있으면 유료 엔드포인트가 전부 403 이다** — 지금 배포된 상태가
그렇다(=아무도 돈을 못 쓴다. 안전한 기본값이지만 본인도 못 쓴다).
⚠️ **KV 를 안 붙이면 횟수가 인스턴스 메모리라 콜드스타트마다 초기화**된다 — 실질 무제한에
가깝다. 남에게 코드를 나눠 주기 전에 붙일 것.

### D. 커넥터에 새 도메인 허용 — ✅ **자동으로 됨(2026-08-08)**
`hwp-convert*.vercel.app` 패턴이 기본 허용이라 현재 배포 도메인은 **추가 작업 없이 통과**한다
(실증: PNA preflight 에 `Allow-Origin`+`Allow-Private-Network` 정상 응답).

⚠️ **Vercel 은 원본 배포 URL 에서 프로젝트명을 자른다** — 별칭은
`hwp-convert-web.vercel.app` 인데 원본은 `hwp-convert-<hash>-….vercel.app`("web" 탈락).
그래서 접두사를 `hwp-convert-web` 이 아니라 **`hwp-convert`** 로 잡았다.

**커스텀 도메인**을 붙이면 exe 재빌드 없이 env 로 넣는다:
```powershell
setx MATHGEN_HWP_ORIGINS "https://exam.example.com"
setx MATHGEN_HWP_SITE    "https://exam.example.com"   # 트레이 '웹앱 열기'
```
`agent.py` 의 `SITE_URL` 기본값은 아직 `mathgen.para-x.co.kr` 이므로, 배포된 도우미 exe 를
새 도메인으로 굳히려면 그 기본값을 바꾸고 `agent.spec` 으로 재빌드한다.

### ⚠️ 남은 보안·안정성 숙제 (감사 major, 배포는 됐지만 미해결)

돈이 걸린 순서대로. **남에게 코드를 나눠 주기 전에** 위 두 개는 처리할 것.

| # | 문제 | 왜 위험한가 |
|---|---|---|
| 1 | **횟수 차감이 클라이언트 의존** — `/api/consume` 을 안 부르면 `used` 가 안 오른다 | 개발자도구로 그 호출만 막으면 한도가 무한이 된다 |
| 2 | **KV 미설정 시 카운터가 인스턴스 메모리** | 콜드스타트마다 0으로 리셋 → 사실상 무제한 |
| 3 | `/api/verify` 레이트리밋 없음 | 짧은 코드 브루트포스 + 남의 코드 소진 가능 |
| 4 | `text/plain` simple request 는 CORS preflight 없이 통과 | 다른 사이트가 방문자 브라우저로 우리 API 를 부를 수 있다(코드는 필요) |
| 5 | `/api/solution` maxDuration 60s 안에 DeepSeek 2회 순차 | 긴 문항에서 504 → 그 문항 해설 유실 |
| 6 | 46회 전 구간 순차 호출 + 중간결과 미보존 | 마지막 렌더 실패 시 이미 쓴 API 비용 전액 소실 |
| 7 | 업스트림 오류 원문 그대로 반환 | 모델명·GCP 프로젝트 번호 노출(minor) |

### E. 커넥터 토큰 인증 — ✅ **구현됨(2026-08-08)**
커넥터가 첫 실행 때 랜덤 토큰을 만들어 `%LOCALAPPDATA%\mathgen-connector\token.txt` 에 두고
**시작할 때 콘솔에 "연결 코드"로 표시**한다. 웹은 그 코드를 입력해 `X-Connector-Token` 헤더로
보낸다(브라우저에 기억됨). 코드가 없거나 틀리면 **401**. 이제 악성 사이트가 로컬 커넥터를
몰래 부르지 못한다. dev 에서 끄려면 `--no-token` 또는 `MATHGEN_HWP_NO_TOKEN=1`.

### F. end-to-end 검증 — 🟡 양 끝은 검증, **가운데(실 API)만 남음**
- ✅ **커넥터 경로**: 캐시 corpus JSON 을 웹과 똑같은 형태로 POST → `.hwp` 5쪽(대수회 폼 +
  정답면 1~20) 확인. 무토큰 401 / 토큰 200. **API 0원.**
- ✅ **프로덕션 API 게이트**: 무인증 `/api/ocr` 401, 잘못된 코드 403, SPA 200.
- ✅ **배포 도메인 ↔ 로컬 커넥터**: PNA preflight 통과, 악성 도메인 차단.
- ❌ **남은 것**: 브라우저에서 실제 PDF 한 편 → Gemini 크롭·OCR → DeepSeek 해설 → 커넥터
  → `.hwp` 다운로드. **env(API 키 + 초대코드) 설정 후에만 가능**하다.

배포 후 첫 확인 순서:
1. `vercel env add` 로 키 3개 넣고 `vercel --prod` 재배포
2. 도우미 실행 → 트레이 메뉴의 **연결 코드** 클릭(클립보드 복사)
3. https://hwp-convert-web.vercel.app 에서 초대코드 → 연결 코드 → 파일명 규칙에 맞는
   시험지 PDF 업로드 → 변환

---

## 4. 알아둘 함정

- ~~커넥터 payload 스키마 불일치~~ → **해결(2026-08-08)**. 실제로 어긋나 있었고(웹 요청이
  400 즉사), `convert_cli.is_engine_envelope` 한 곳에서 판별하도록 고쳤다. ⚠️ **판별을
  커넥터에 다시 구현하지 말 것** — 양쪽이 따로 판정하면 확장자·렌더 경로가 조용히 어긋난다
  (`tests/test_connector_contract.py` 가 중복 판별을 막는다).
- ~~웹 API 한도초과 미처리~~ → **해결**. `isFatalApiError`(엔진 `_is_fatal_api_error` 와
  같은 규칙, 7케이스 1:1 대조)가 `{fatal:true}` 를 붙이면 프론트가 남은 크롭을 포기하고
  즉시 멈춘다. ⚠️ 일시적 429/503 과 반드시 구분해야 한다(재시도로 풀리는 것까지 중단하면 안 됨).
- ⚠️ **`scripts/render_to_png.py` 는 `.hwp` 를 못 연다** — `hwp.Open(src,"HWPX","")` 로
  포맷이 하드코딩돼 있어 `.hwp` 를 넣으면 **빈 1쪽 PDF** 가 나온다(2026-08-08 실측, 결함으로
  오인하기 딱 좋음). 확장자에 맞춰 `"HWP"`/`"HWPX"` 를 넘기는 변형으로 렌더할 것.
- ⚠️ **렌더 중 타이핑 혼입**: 변환 중 다른 곳에 타이핑하면 숨김 COM 문서로 낱자모가 샌다
  (CLAUDE.md 문서화). 2026-08-08 검증에서도 `[5.1점]ㅂ` 이 한 번 나왔다가 **재렌더로 사라짐** —
  결함으로 단정하기 전에 클린 재렌더로 확인할 것.
- **비용**: 시험지 1편 ≈ 215원(Gemini 126 + DeepSeek 89). 실측치.
- **Vercel 무료 티어 실행시간**: `api/ocr.ts` 는 `maxDuration=60` 으로 뒀다. 문항이 많으면
  브라우저가 크롭별로 나눠 호출하므로 개별 호출은 짧다.
- **파일명이 폼을 정한다**: 웹은 사용자에게 학교·학년·과목을 묻지 않고 **업로드 파일명**
  (`[학교][학년][과목][25-2-중간][출판사].pdf`)으로 폼·머리말·단원 어휘를 결정한다. 규칙에
  안 맞으면 차단하지 않고 **기본 서식**으로 렌더된다(GUI 2026-06-16 합의와 동일).

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
