# 시험지 한글화 → todays-math 전달 묶음 (2026-10-21)

시험지 한글화(이 저장소, `D:\시험지 한글화`, 원격 `BIGSHOL/testchange`)에서 기출 시험지를 한글 문서로
옮길 때 하는 일 **전부**를 todays-math 가 **골라서** 가져가도록 묶었다. 사용자 지시: "우리 시험지 한글화
할 때 하는 모든 걸 거기에 넣어 줘. 알아서 필터링해서 받아쓸 수 있게."

- 코드로 바로 넣을 것 = `patches/`(검토용) · `drop-in/`(그대로 덮어쓰기용) — **둘은 같은 내용**이다.
- 방법·노하우 = 문서 세 개. 항목마다 todays-math 에 맞는지 표시를 달았다.
- ⚠️ 이 폴더의 정본은 시험지 한글화 쪽이다. todays-math 에서 고친 것이 있으면 알려 달라
  (도형 엔진은 2026-08-24 부터 양쪽을 오가며 맞춰 왔다 — `figure_scene` 은 지금 todays-math 가 앞선다).

## 한눈에

| 항목 | todays-math 현재(main `3aa03a021` 기준 실측) | 권장 |
|---|---|---|
| 도형 엔진 `figure_svg`·`figure_solid`·`label_markup` | 시험지 한글화와 **바이트 동일** | — |
| `figure_scene` | **todays-math 가 앞선다**(`clear_angle_labels`, 2커밋) | **건드리지 말 것** — 패치에 없음 |
| ⭐ 픽셀 검수 `lint_svg` | **돌지 않는다** — `No module named 'core.figure_generator'` | 패치 01 (래스터화를 엔진 안으로) |
| ⭐ 기출 재작도 공용 도구 `figure_exam` (신규) | 없음 | 패치 01 — 조건→좌표→검산→작도→검수→PNG 를 한 모듈로 |
| ⭐ FigureSpec 자동 정리 `figure_spec_repair` (신규) | 없음 — `render_spec.py` 는 장식 칸 하나에도 실패 | 패치 01 + 연결 한 줄(01 문서 §3) |
| `figure_quality` 전면 배경 rect | `fill="none"/"transparent"` 전면 rect 도 반려 | 패치 01 (한 덩어리) |
| 수식 변환기 `vendor/hwpx/latex_to_hwpeq.py` | 4건 뒤짐(단위·닮음 기호) | 패치 02 — corpus 수식 9,870개 중 76개 개선, 나머지 동일 |
| 기출 도형 작도법 | — | `02-기출-도형-작도법.md` |
| 한글화 노하우 전체(OCR·조판·정답·게이트·운영) | — | `03-한글화-노하우-전체.md` |
| ⭐ 단원 분류표 새 판(큰분류ver.261020, 2026-10-26 추가) | 같은 모듈 없음 — 단원명은 문서·스킬에 손으로 | `04-단원분류표-261020.md` + `drop-in/topic-vocab/`(JSON·조회 모듈·생성 스크립트·테스트). 대수회 작업 규정 표준과 다른 9곳 목록 포함 |
| ⭐ 대수회 작업 규정 표준(26.03.12)·기준표 맞춤(2026-10-26 추가) | 확률 P·여집합·행렬·집합 중괄호 등이 표준과 다름 | `05-작업규정표준-맞춤.md` + 패치 03(수식 변환기, 02 위에). 04 의 "다른 9곳"은 이걸로 해소. 조판 규칙(배점·단서 우측정렬·`⑴`·표 선 굵기)과 HWPX 함정 3개 |

표시: ★ 바로 쓸 것 · ◆ 맞춰 보고 쓸 것 · ○ 참고(우리 사정에 묶인 것) · ✕ 해당 없음(한글 COM 등)

## 적용

```bash
# todays-math 루트에서 — 둘 다 2026-10-21 실저장소에서 git apply --check 통과
git apply "D:/시험지 한글화/docs/export/todays-math/patches/01-figure-engine.patch"
git apply "D:/시험지 한글화/docs/export/todays-math/patches/02-latex-to-hwpeq.patch"
git apply "D:/시험지 한글화/docs/export/todays-math/patches/03-latex-to-hwpeq-std.patch"   # 02 다음(2026-10-26)
# 또는 drop-in/ 아래 파일을 같은 경로로 복사(파일이 그새 바뀌었으면 패치 쪽이 안전)
```

검증(시험지 한글화 쪽에서 이미 돌린 것 — 같은 명령으로 재현 가능):

| 검사 | 결과 |
|---|---|
| 패치를 todays-math 와 같은 설정(autocrlf)의 임시 저장소에 적용 → `drop-in/` 과 대조 | 5파일 동일 |
| 적용된 엔진(그쪽 `figure_scene` 그대로)으로 `examples/` 두 개 실행 | 둘 다 lint 0건, PNG 생성 |
| 적용된 엔진만으로 `lint_svg` + `compile_with_repair` (`figure_generator`·`utils` import 0) | 통과 |
| 수식: 시험지 한글화 corpus 고유 수식 9,870개 → 패치본 출력 == 시험지 한글화 출력 | 불일치 0 |
| 시험지 한글화 쪽 그림 테스트(`tests/test_figure_*.py` 11개 파일) | 171 통과 |
| `figure_exam` 이 기존 시험지 스크립트(제일고·오성중)와 같은 출력 | 헬퍼 비교 36건·PNG 5장 바이트 동일 |

todays-math 쪽 잠금(`vendoredFigureEngine.test.ts` — 최상단 import 에 numpy·PIL 금지)은 새 두 모듈도
지킨다(시험지 한글화 `tests/test_figure_exam.py` 가 같은 규칙을 검사).

## 파일

```
README.md                      ← 이 문서
01-엔진-동기화.md               ← 무엇이 다르고 패치가 무엇을 바꾸나, 연결 방법
02-기출-도형-작도법.md           ← 세션 변환에서 그림을 그리는 법 전부(★)
03-한글화-노하우-전체.md         ← 파이프라인 단계별 노하우 카탈로그(적용성 표시)
04-단원분류표-261020.md         ← 단원 분류표 새 판·레벨 규칙·엔진 변경·작업 규정 표준 대조(2026-10-26)
05-작업규정표준-맞춤.md          ← 표준 55항목·기준표에 맞춘 엔진 변경 + HWPX 함정(2026-10-26, 패치 03)
drop-in/topic-vocab/            ← topic_vocab.json·topic_vocab.py·build_topic_vocab.py·test_topic_vocab.py
patches/01-figure-engine.patch  ← vendor/figure-engine/core: figure_svg·figure_quality 수정 + 새 2파일
patches/02-latex-to-hwpeq.patch ← vendor/hwpx/latex_to_hwpeq.py
drop-in/…                       ← 위 패치를 적용한 완성 파일(같은 경로)
examples/ex_solid_foot.py       ← 입체(3D 좌표→verify_solid→사투영) — 제일고 원본과 SVG 바이트 동일
examples/ex_plane_spec.py       ← 평면(FigureSpec + 덧그림 치수)
```

예시는 `scripts/figure/` 에 두면 `engine_path.engine_root()` 로 엔진을 찾는다. todays-math 규칙
("경로 결정은 `engine_path.py` 한 벌")에 맞추려면 옮길 때 `FIGURE_ENGINE_PATH` 폴백 줄은 지운다.

## 원본 위치(시험지 한글화)

| 무엇 | 경로 |
|---|---|
| 엔진·도구 | `core/figure_svg.py` · `figure_scene.py` · `figure_solid.py` · `figure_quality.py` · `label_markup.py` · **`figure_exam.py`** · **`figure_spec_repair.py`** |
| 수식 변환 | `core/latex_to_hwpeq.py` |
| 실전 그림 스크립트(시험지별) | `corpus/<시험지>/fig_svgs.py` — 본보기: 제일고 고2 기하(입체·벡터), 오성중 중2(평면·보기 표 안 그림), 왕선중 중3(원주각·접선·산점도), 대진고 고1 공수2(함수 그래프) |
| 전체 규칙·사고 기록 | `CLAUDE.md`(약 2,000줄, 날짜별) · `corpus/REVIEW_PROTOCOL.md` · `docs/HANDOFF_FIGURE_ENGINE.md` |
