# Supabase 연동 자가발전(self-improvement) 시스템 계획

> 상태: **계획(미구현)**. 사용자 요청 2026-06-18 — "배포용으로 변환한 시험지의 ocr/crop 을
> 웹(Supabase)에 저장해 자가발전 시스템을 구축". 이 문서는 설계·단계·보안·프라이버시 가이드.

## 0. 목표와 가치

배포 exe 사용자가 변환할 때마다 생성되는 **crop(문제영역 좌표·검출번호) + OCR JSON** 을
중앙(Supabase)에 모아, 프로젝트의 기존 **자가발전 corpus 검수 루프**(OCR→렌더→완료본 1:1
대조→`reviewed`)에 실제 사용 데이터를 공급한다.

- **회귀셋 확장**: 오늘(2026-06-18) 경상여고 수정 검증에 쓴 *전 corpus 4115문항 OLD/NEW
  전수 비교* 같은 회귀 스캔의 모집단을 실사용 시험지로 크게 늘린다.
- **실사용 결함 자동 발견**: Extra data·보기 박스 유출처럼 특정 입력에서만 터지는 결함을
  실데이터에서 조기 포착(텔레메트리: 스킵률·실패 사유 집계).
- **미개척 영역 우선순위화**: 학년·과목·학기·출판사별 커버리지 갭을 데이터로 식별
  (캠페인 선별을 추측이 아니라 실데이터로).

## 1. 무엇을 올리나 (데이터 등급)

| 등급 | 내용 | 프라이버시 위험 | 단계 |
|------|------|-----------------|------|
| **T0 텔레메트리** | 변환 통계(페이지·문항·스킵 수·모델·앱버전·실패 사유·소요시간), 파일명에서 파싱한 메타(학교·학년·과목·학기) | 낮음(학교명만 식별성) | Phase 1 |
| **T1 구조화 OCR** | `crops.json`(좌표·kind·number) + `p{n}_merged.json`(OCR 결과 JSON) | 중간(시험 본문 텍스트=출판사 저작물 파생) | Phase 2 |
| **T2 크롭 PNG** | crop/page PNG(비전 재검수·SVG 재생성용) | 높음(원본 이미지) | Phase 3 |

⚠️ **원본 PDF 자체는 업로드하지 않는다**(저작권·용량). 크롭 PNG(T2)도 consent 필수.

## 2. 프라이버시·동의 (반드시 선행)

- **opt-in 기본 OFF**. 최초 실행 시 1회 동의 다이얼로그("변환 데이터(문항 인식 결과)를
  품질 개선용으로 익명 제공하시겠습니까? 원본 PDF·개인정보는 전송하지 않습니다").
  config `UPLOAD_CORPUS=false` 기본, 동의 시 true.
- **학교명 익명화 옵션**: 업로드 전 학교명을 해시/일반화(`OO고`) 토글. 메타의 식별성 제거.
- 시험 본문은 출판사 저작물 파생물 — **내부 품질개선 한정 사용**, 외부 공개·재배포 금지를
  동의 문구·정책에 명시. 보존기간·삭제요청 경로 안내.
- 콘텐츠 **해시 dedup**(같은 시험지 반복 업로드 방지) — 해시는 OCR JSON 정규화본 기준.

## 3. Supabase 아키텍처

### 3-a. 테이블(Postgres)
```
conversions
  id uuid pk, created_at timestamptz, client_id text(설치별 익명 UUID),
  app_version text, ocr_model text, school text, grade text, subject text,
  term text, publisher text, page_count int, question_count int,
  skipped_crops int, duration_s real, content_hash text unique, anonymized bool
pages
  id uuid pk, conversion_id uuid fk, page_num int,
  crop_json jsonb,        -- crops.json 의 해당 페이지
  ocr_json jsonb          -- p{n}_merged.json
-- T2(선택): page_assets (conversion_id, page_num, kind, storage_path) + Storage 버킷
```

### 3-b. 보안 (RLS)
- **anon 키 = insert-only**: 클라이언트(exe)는 `conversions`/`pages` 에 **INSERT 만**.
  SELECT/UPDATE/DELETE 정책 없음 → 다른 사용자 데이터 조회 불가. anon 키는 insert-only라
  exe 에 임베드해도 안전(단 rate-limit·size-limit 정책 필수).
- **service-role 키는 exe 에 절대 넣지 않는다** — corpus puller(내부 도구)만 사용,
  gitignore 된 config 에 보관(기존 ANTHROPIC/GEMINI 키 규칙과 동일).
- 업로드 크기 상한·분당 호출 상한(Edge Function 또는 RLS 체크)으로 남용 차단.

## 4. 클라이언트(exe) 구현 — 비차단 업로드

- 의존성: `supabase-py`(또는 순수 `httpx` POST — exe 용량 고려해 httpx 권장).
- 변환 완료 후(`gui/main_window` 워커 끝), `UPLOAD_CORPUS` 면 **백그라운드 스레드**로
  메타+crops.json+merged.json 을 POST. 실패해도 변환 결과엔 영향 없음(fire-and-forget +
  로컬 큐 재시도). 이미 `_save_record` 가 로컬에 crop/ocr 를 남기므로 **그 산출물을 그대로
  전송**(추가 연산 0).
- config 추가: `UPLOAD_CORPUS`(bool), `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
  `ANONYMIZE_SCHOOL`(bool), `client_id`(최초 생성·보관).
- ⚠️ 현재 `_n_skipped_crops`(2026-06-18 추가)·문항수·모델·버전은 이미 워커가 알고 있으니
  T0 텔레메트리는 즉시 구성 가능.

## 5. 서버/코퍼스 측 — 수집 파이프라인

- 신규 도구 `scripts/corpus_consumer/pull_supabase.py`(service-role): 새 `conversions`
  조회 → `corpus/<자동생성폴더>/`(`ocr/p{n}_merged.json`·`crop/crops.json`·`meta.json
  status="uploaded"`)로 스테이징 → 기존 검수 루프 진입.
- **품질 게이트**: 스킵률 높은 변환·중복 해시·저신뢰 제외. 학년·과목 **커버리지 갭 우선**
  선별(현 캠페인 선별을 데이터 기반으로 대체).
- 이후 기존 흐름 그대로: `corpus_render`(폼 렌더)→완료본/원본 대조→결정적 후보정→
  `reviewed`→회귀 테스트·`scan_leaks` 모집단 편입.

## 6. 단계별 로드맵

1. **Phase 1 — 텔레메트리(T0)**: 동의 다이얼로그 + 익명 통계 업로드. 위험 최소, 즉시
   가치(실패 사유·스킵률 집계로 다음 수정 우선순위). Supabase 프로젝트·테이블·RLS 셋업.
2. **Phase 2 — 구조화 OCR(T1)**: crops.json+merged.json 업로드 + `pull_supabase` 수집 +
   corpus 스테이징. 자가발전 모집단 실데이터 확장 시작.
3. **Phase 3 — 크롭 PNG(T2, consent)**: Storage 버킷 + 비전 재검수/SVG 재생성 입력.
4. **Phase 4 — 대시보드/자동화**: 커버리지·실패율 대시보드, 신규 결함 패턴 자동 클러스터링,
   주기적 회귀 스캔 자동화.

## 7. 미해결·결정 필요 사항

- 동의 UX·법적 문구(저작물 파생 데이터 수집 범위) — 사용자 확인 필요.
- 학교명 기본 익명화 여부(기본 ON 권장).
- exe 용량 증가(supabase-py vs httpx) 트레이드오프.
- Supabase 무료 티어 용량(jsonb 누적·Storage) vs 보존정책.
- 중복·악성 업로드 방어(해시 dedup + rate-limit + 크기 상한).

> 구현 착수 전 Phase 1 범위·동의 문구를 사용자와 확정할 것.
