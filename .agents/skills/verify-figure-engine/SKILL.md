---
name: verify-figure-engine
description: Figure Engine v2의 선언형 기하, 치수 곡선, 라벨 충돌 회피, SVG 보안 게이트와 기존 42개 도형 회귀를 검증합니다. 도형 엔진·생성기·품질 게이트 수정 후 사용.
---

# Figure Engine v2 검증

## Purpose

도형 엔진이 선명하지만 틀리거나, 라벨이 선과 겹치거나, 치수 점선이 사라지는 회귀를 방지합니다.

1. **선언형 기하 무결성** — 점·원·선분·교점·각·치수 관계와 fail-closed 검증
2. **자동 배치 품질** — A/B/C 라벨, 곡선 점선 치수선, 짧은 변·긴 라벨 충돌 회피
3. **결정성** — 같은 의미의 입력 순서가 달라도 동일한 SVG 생성
4. **SVG 보안/품질** — 외부 참조·스크립트·투명/화면 밖 요소 차단과 픽셀 lint
5. **기존 도형 회귀** — 3개 학교 corpus의 42개 SVG가 구조·픽셀 검사를 모두 통과

## When to Run

- `core/figure_scene.py`, `core/figure_svg.py`, `core/figure_quality.py` 수정 후
- `core/figure_generator.py`의 SVG/FigureSpec 생성·채택·폴백 경로 수정 후
- 치수선, 각 표시, 라벨 자동 배치 또는 스타일 값을 수정한 후
- 도형 corpus를 추가·수정한 후
- 커밋·PR 전 전체 도형 품질을 확인할 때

## Related Files

| File | Purpose |
|------|---------|
| `core/figure_scene.py` | FigureSpec v2, 기하 검증, 자동 라벨·치수 배치, SVG 직렬화 |
| `core/figure_quality.py` | 비신뢰 SVG sanitize, 구조·픽셀 품질 게이트 |
| `core/figure_svg.py` | 기존 SVG 프리미티브와 픽셀 lint |
| `core/figure_generator.py` | 비전→FigureSpec/SVG 생성, 재시도, 안전한 크롭 폴백 |
| `tests/test_figure_scene.py` | 선언형 기하·결정성·치수·라벨 회귀 |
| `tests/test_figure_generator_quality.py` | SVG 보안과 생성 파이프라인 회귀 |
| `tests/test_figure_svg_dimension.py` | 기존 치수선과 안전한 rich text 회귀 |
| `corpus/**/fig_svgs.py` | 기존 학교 도형 42개 실데이터 |
| `scripts/verify_figure_engine.py` | 이 스킬의 실행 백엔드 |

## Workflow

### Step 1: 전체 도형 게이트 실행

```bash
cd "D:/시험지 한글화" && PYTHONUTF8=1 python scripts/verify_figure_engine.py
```

**PASS 기준:**

- 도형 모듈 4개 `py_compile` 통과
- 도형 전용 테스트 3개 파일 전체 통과
- corpus 파일 3개, SVG 42개 구조 검사 통과
- 42개 모두 `lint_svg(scale=2)` 통과

**FAIL 시 조치:** 실패한 테스트 또는 `학교/도형키`를 먼저 재현하고, 좌표를 눈대중으로 옮기기 전에 의미 관계·후보 배치 비용·lint 판정을 확인합니다.

### Step 2: 개발 중 빠른 검사

```bash
cd "D:/시험지 한글화" && PYTHONUTF8=1 python scripts/verify_figure_engine.py --quick
```

`--quick`은 corpus 픽셀 lint만 생략합니다. 커밋·PR 전에는 반드시 Step 1 전체 검사를 다시 실행합니다.

### Step 3: 실제 크기 육안 검수

사용자가 제공한 원본 또는 변경된 대표 fixture를 다음 기준으로 260px에서 렌더합니다.

- 선 굵기와 글자 크기가 시험지 인쇄에서 균형적인가
- A/B/C/P 및 수치 라벨이 선·원·각호와 겹치지 않는가
- 곡선 점선이 라벨 때문에 양끝의 짧은 조각으로 사라지지 않는가
- 짧은 변의 긴 라벨은 곡선 밖으로 이동하는가
- 의미가 불확실한 원본은 임의 작도 대신 크롭 폴백되는가

육안 실패는 자동 lint 통과 여부와 무관하게 FAIL입니다. 대표 PNG를 비교해 배치 로직 또는 fixture를 수정한 뒤 Step 1을 반복합니다.

## Output Format

```markdown
## verify-figure-engine 검증 결과

| 검사 | 상태 | 상세 |
|------|------|------|
| 모듈 컴파일 | PASS/FAIL | 4개 |
| 도형 전용 테스트 | PASS/FAIL | N개 |
| 기존 corpus | PASS/FAIL | 42/42 |
| 260px 육안 검수 | PASS/FAIL | 대표 유형과 발견사항 |
| 결정성·충돌 회피 | PASS/FAIL | 순열/짧은 변/저 offset |
```

## Exceptions

다음은 위반이 아닙니다.

1. **저해상도 원본의 판독 불확실성** — 엔진 렌더 품질과 OCR 의미 인식은 별개입니다. 불확실하면 원본 크롭으로 되돌아가는 것이 정상입니다.
2. **치수선의 의도적인 중앙 gap** — 라벨이 곡선 위에 있을 때 가독성을 위해 중앙 구간을 비우는 것은 정상입니다. 단, 양쪽 곡선 조각이 육안으로 충분히 보여야 합니다.
3. **불가능한 밀집 배치의 `GeometryValidationError`** — 겹친 라벨을 출력하지 않고 fail-closed 하는 것이 정상입니다.
4. **사진·복잡한 통계 차트의 crop 폴백** — FigureSpec 지원 범위 밖 도형은 raw SVG를 강제하지 않습니다.
