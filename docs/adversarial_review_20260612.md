# 전체 코드 적대적 리뷰 보고서 (2026-06-12)

대상: `core/` 전체(약 9,600줄) + `gui/` + `scripts/` + `models/` (~14,800줄).
방법: 영역별 7개 검수 에이전트 병렬 정독 → 주요 주장 전건 직접 반박 검증(재현 실행 또는 소스 정적 확정).
기준: 스타일 지적 배제 — **실제 깨지는 입력/시나리오가 있는 결함만** 등재. 각 항목에 재현 상태 명기.

표기: ✅재현 = python3 실행으로 출력 확인, 📐정적 = 코드 경로로 확정(COM/lxml 등 환경 제약), 🔶추정 = 렌더 글리프 등 최종 단계만 미실측.

---

## A. HIGH — 즉시 수정 권고 (8건)

### A-1. [회귀·오늘 커밋] 대형연산자 상하한이 빈 그룹의 첨자로 변형 — `SUM {}_{k=1}`
- `core/latex_to_hwpeq.py:671` — 커밋 `f4102d0`(베이스 없는 선행 첨자 빈 그룹 삽입, 혜화여고 #19)의 lookbehind 가 big-op 출력(`SUM _{lo}`, 공백+`_{`)에도 매칭.
- ✅재현: `\sum_{k=1}^{n} k` → `SUM {}_{k=1} ^{n} k` (정본: `SUM _{k=1} ^{n}` — 모듈 docstring·test_equation_metrics 의 형태와 불일치). `\int`·`\bigcup` 동일. `\lim` 은 무공백 출력이라 무사.
- 영향: 수1/수2/확통의 Σ·∫ 전부. 강동고·대구고 "Σ 상하한 정상" 검수는 이 커밋 **이전** — 미검출 상태로 잠복.
- 수정: lookbehind 에서 대형연산자 키워드 직후 공백을 제외하거나, big-op 출력의 `_{` 앞 공백 제거 후 별도 마커.

### A-2. GREEK_MAP·FUNC_MAP 전체가 공백 미보장 — `sintheta`·`absin C` 광역 literal
- `core/latex_to_hwpeq.py:872-896` — SYMBOL_MAP(step 9)만 alpha 양끝 패딩, 그리스/함수 맵은 무패딩 `str.replace`. PLEFT/asqrt 와 완전 동종(sqrt·accent·mathrm·env 만 고치고 이 두 맵은 누락).
- ✅재현: `\sin\theta`→`sintheta`, `\tan\theta=\frac{\sin\theta}{\cos\theta}`→`tantheta = {sintheta} over {costheta}`, `S=\frac{1}{2}ab\sin C`→`…absin C`, `a\cos B`→`acos B`.
- 영향: 고등 삼각함수 전반(명령 직결·글자 앞). 숫자 앞(`3\pi`→`3pi`)만 HWP 토큰 분리로 우연히 정상.
- 부수(같은 맵, str.replace 접두 잠식): ✅`\leqslant`→`LEQ slant`, `\pmod`→`PLUSMINUS od{…}`.

### A-3. 크롭 JSON 파싱 실패가 "빈 페이지"로 둔갑 → 페이지 통째 증발
- `core/crop_detector.py:302-306` — `_parse_crops` 가 JSONDecodeError 를 잡아 `[]` 반환. `detect_crops` 의 Gemini 3회 재시도·Claude 폴백(195-224)은 **예외에만** 반응 → 잘린/깨진 응답은 재시도·폴백 없이 빈 리스트로 즉시 반환.
- 📐정적 확정. `gui/main_window.py:604-610` 이 "문항 없음" 페이지로 자동 스킵 → 해당 페이지 전 문항이 출력에서 조용히 소실. `_detect_with_claude` 는 `stop_reason=="max_tokens"` 미검사(ocr_engine 은 검사함).
- 수정: 파싱 실패 시 예외 raise — 기존 재시도/폴백이 그대로 받아냄.

### A-4. corpus_lint 핵심 게이트가 raw XML 연속 문자열 기반 → run 분할 시 통째 우회
- `scripts/corpus_lint.py:106-120` — 메타토큰 `full.count(tok)`·라벨 혼용 `re.findall(r"\[\s*(서술형…")` 이 raw XML 대상. COM 이 토큰/라벨을 여러 `<hp:t>` run 으로 쪼개는 비결정(효성중 B-1·대진고에서 직접 문서화)이 발생하면 count=0 → **오염 렌더가 PASS**. 효성중 수정의 "최후 게이트"가 정확히 그 케이스를 놓침.
- `scripts/corpus_lint.py:122` — `'정답' not in full` 은 꼬리말 "(정답)"·발문 "정답을 구하시오"로 항상 충족 → 정답 페이지(container·gso) 증발을 못 잡는 무력 게이트(강동중 클래스 검출 목적과 불일치).
- ✅재현(우회)·📐정적('정답'). 수정: 배점중복 검사처럼 `re.sub(r"<[^>]+>","",full)` 후 검사 + '정답' 게이트는 container/gso 존재 검사로.

### A-5. 박스 뒤 발문연속(post)의 배점 — score 필드 누락 시 캡처 없이 완전 소실
- `core/content_parser.py:103-113(캡처)` vs `1539-1547(제거)` — 캡처는 박스 **앞** 블록만 보는데, 제거는 post 경로 `_finalize_contents`→`_strip_score_text`(박스 머리 없어 무가드)에서 발생.
- ✅재현: `{"score": null, contents:[<상자>…, "…알맞은 것은? [4점]"]}` → `score=None` + 본문 `[4점]` 삭제 = **배점 완전 증발**. 장산중 D4 가 명시한 "박스→발문연속 끝 [N점]" 표준 위치에서 발화. "캡처 없이 소실 금지" 감사 원칙(2026-06-10) 위반.
- 수정: post 경로에서도 제거 전 캡처(score 필드 비어 있으면 채움).

### A-6. `_has_geometry_context` 부분문자열 매칭 — "점수·기호·괄호·번호" 가 기하 문맥
- `core/content_parser.py:342-356` — `any(k in text)` 라 키워드 `"점"`이 점수·관점·장점, `"호"`가 기호·괄호·번호·신호에 매칭.
- ✅재현: "주사위를 던져 얻은 점수를", "집합을 기호로 나타낼 때", "전화번호를 정하는 경우의 수" 전부 True.
- 영향: ① stat-이탤릭 복원 스킵(`\mathrm{E}` 로만 잔존) ② 단일 대문자 오로만화 ③ 점좌표 로만화 오발동 — 사용자가 반복 항의한 "로만/이탤릭" 계열의 잔존 광역 경로.
- 수정: 단어 경계 매칭 또는 "점수/기호/괄호/번호/신호/관점/장점/단점" 부정 필터.

### A-7. [폴백 경로 한정] hwpx_writer 블록 요소 뒤 본문 순서 역전
- `core/hwpx_writer.py:722, 884-898` — EQUATION_BLOCK/TABLE/IMAGE 는 `sec_elem` 끝에 새 문단 append, 이후 TEXT 는 계속 **앞서 만든 `p_elem`** 에 추가 → `[TEXT, 블록, TEXT]` 역순 렌더. 배점 인라인도 블록 앞 문단에 찍힘.
- 📐정적 확정. **COM 미설치 폴백 경로 전용**이라 프로덕션(COM/폼) 무관 — 단 폴백이 동원되는 순간 박스 뒤 발문연속·블록수식 문항 전부 깨짐.

### A-8. [템플릿 경로 한정] hwpx_writer 고정 ID(charPr 7, paraPr 100/101) 충돌 시 오참조
- `core/hwpx_writer.py:46-50, 876, 1279-1312` — 주입부는 "id 존재 시 스킵", 참조부는 무조건 `"7"/"100"/"101"`. 실제 시험지 템플릿(charPr 수십 개)에선 밑줄 강조·배점 우측정렬·제목 가운데가 **템플릿의 임의 스타일**로 찍힘.
- 📐정적. 기본 골격(`HwpxDocument.new()`) 경로는 안전.

---

## B. MED — 수정 권고 (주제별)

### B-1. 수식 변환 (latex_to_hwpeq)
| # | 결함 | 위치 | 재현 |
|---|---|---|---|
| 1 | **`\not` 무처리 → 의미 반전**: `x \not\in A`→`x in A`, `x \not= y`→`x = y` (∉→∈, ≠→= 무증상 오답 — 위험도상 HIGH 인접) | SYMBOL_MAP·:927 고아 `\` 삭제 | ✅ |
| 2 | `\text{}` 따옴표 리터럴 내부에 후속 패스 오염: `\text{5cm}`→`"5 rm`cm"`, `\text{AB}`→`"rm {AB}"`, `\text{(단, }`→`"(단,~"` | :661-683·:741 | ✅ |
| 3 | `\lcm`/`\min` 을 변수+단위로 오인 절단: `\lcm(4,6)`→`` l rm`cm(4,6) `` | :117-136 | ✅ |
| 4 | `rm {AB}` 삽입 후 it 미복귀 — 도원중 실증(rm 은 명시적 it 까지 번짐) 기준 `AB=x+y` 의 `=x+y` 까지 로만 | :472-491 | 🔶(출력 재현, 글리프 추정) |

### B-2. OCR 엔진 (ocr_engine)
| # | 결함 | 위치 | 재현 |
|---|---|---|---|
| 1 | `_extract_json` 1.5단계가 1차 json.loads **이전** 무조건 적용 — 정상 `\n`+라틴 이스케이프를 리터럴 `₩n` 으로 오염(무경고). LaTeX 충돌 회피 휴리스틱의 부작용 | :779 | ✅(정적+부분 재현) |
| 2 | `recognize_crop` 이 `_msg_text` 방어 우회(`message.content[0].text` 직접) — 빈 content 시 IndexError 가 ValueError 재시도 경로를 우회, 문항 통째 스킵 | :644,651 | 📐 |
| 3 | `_parse_markdown_table` 셀 내 `\|`(절댓값 `P(\|X\|<1)`) 분해 + ragged rows 통과 | :189-216 | ✅ |
| 4 | `validate_ocr_response` 비-dict/null 방어 부재 — 변형 스키마 1회에 페이지 변환 전체 크래시(TypeError/AttributeError) | :947-975 | 📐 |

### B-3. COM 렌더 (hwp_com.py / hwp_com_writer.py)
| # | 결함 | 위치 | 재현 |
|---|---|---|---|
| 1 | **`force_layout` 이 `Visible=True` 올리고 미복구** — save_hwpx 마다 호출 → 첫 저장 후 모든 후속 COM 조작이 보이는 창. 5개교 반복 "타이핑 혼입"의 정합적 기여 요인 | hwp_com.py:222 | 📐(소스 확정) |
| 2 | **`save_pdf` 침묵 실패 무검증** — save_hwpx 의 존재+mtime 검사가 PDF 엔 없음 → 잠긴 출력 시 **낡은 PDF 로 검수**(검수 파이프라인 신뢰성 직결) | hwp_com.py:251-260 | 📐(소스 확정) |
| 3 | `endnote` 실패 시 삽입된 미주 마크 미제거 → 미주+텍스트 번호 이중, 이후 번호 체계 어긋남 | hwp_com.py:427-459 | 📐 |
| 4 | `insert_picture` 이중 침묵 실패 — 그림 통누락 로그 0 + 실패 후 FindCtrl 이 직전 수식 컨트롤을 오타깃(캐럿 침범 가능) | hwp_com.py:353-380 | 📐 |
| 5 | `_fix_stemleaf_colwidth` 가 `_tbl_balanced` 대신 비탐욕 정규식 — 중첩표에서 내표 미수정(조용) 또는 외표·내표 셀폭 뒤섞임(XML 수치 손상) | hwp_com_writer.py:1217-1221 | ✅ |
| 6 | `_inject_table_shading` 멱등 재사용이 "색=#D9D9D9 첫 borderFill" — 폼 템플릿 자체 회색 fill 매칭 시 셀 테두리 오염 | :1701-1713 | 📐 |
| 7 | `_split_trailing_score` 끝-3블록 경직 — 후행 빈 블록 1개로 실패 → score 폴백과 **총점 이중 렌더** | :383-400 | ✅ |
| 8 | 배점 줄넘침 판정 `KeyIndicator()[5]` 만 비교 — 단/쪽 경계 넘김 시 lb<la 로 미감지(기본 경로) + KeyIndicator 예외 시 -1 로 폴백 영구 비활성 | :935-989 | 📐 |
| 9 | 부모 총점([총 N점])은 defer_score 미적용 — 박스 뒤 발문연속 구조에서 stem 끝 인라인(원본 위치와 불일치, 입력에 따라 이중) | :824-867 | 📐 |
| 10 | 게이트 모순 3종: `_BOX_BREAK_RE` 의 ○ 무경계("○표 하시오" 분해✅) / `_is_value_box` join 무구분으로 `_CIRCLE_BULLET_RE` 앵커 소실✅ / `_is_circled_item_start` 가 수식 분리 후 꼬리 TEXT 선두 ㉠(인라인 참조)에 오발동✅ | :81-163, 95-105 | ✅ |

### B-4. 폼 경로 (hwp_form_writer)
| # | 결함 | 위치 | 재현 |
|---|---|---|---|
| 1 | `_ESSAY_LABEL_SYNC_RE` 번호 가드 부재(주석 계약 위반) — 안내박스 원문 `[서답형 1~5] 답은…` 이 `[서술형 1~5]` 로 **본문 변조**. `_label_words_in_xml` 동일 → 최종 루프 오탐·불필요 relaunder 연쇄 | :2059, 2063 | ✅ |
| 2 | `_renumber_essay_labels` 의 `if n_essays and len(matches)!=2*n_essays` — **n_essays==0 에서 가드 통째 우회**, 객관식 전용 시험지에서 폼 native 라벨 오재부여 | :2138 | ✅ |
| 3 | grow 실패/슬롯 부족 시 **문항 침묵 탈락** — `n_mc=min(...)` 후 변환 성공 처리(경고 로그뿐, 일부 경로는 로그 0). 문항 누락은 최악급인데 사용자 신호 없음 | :956-982 | 📐 |
| 4 | render_figures=True 경로에 메타토큰/라벨 보정 전무 — 토큰 run 분할 시 `소단원자리표식QZX` 평문 출하, 안전망 없음 | :2435-2443 | 📐 |
| 5 | `_strip_answer_header_redefine` — 첫 단락의 secPr 미검증: 메인 머리말이 첫 최상위 단락에 없는 신규 폼이면 **메인까지 제거**(현 폼들은 안전) + 편집 후 태그 균형 검증 없음 | :1785 | ✅(합성) |

### B-5. 검증 도구·기타
| # | 결함 | 위치 | 재현 |
|---|---|---|---|
| 1 | verify_output_format chk26 연산자 우선순위 `A or (B and C)` — 매핑 지워도 PASS(무력) | scripts/verify_output_format.py:135-136 | ✅ |
| 2 | `_func_body` 가 클래스 마지막 메서드에서 파일 끝까지 과확장 — 동어반복 방지 검사(#5/#10/#18)가 리팩토링 한 번에 무력화 가능 | :47-58 | ✅ |
| 3 | `_LONE_JAMO_RE` 오탐(라벨 run 분할 시 'ㄷ' 단독)·미탐(2글자·공백 동반 혼입) 양방향 | scripts/corpus_lint.py:91 | ✅ |
| 4 | GUI: 취소 후 인플라이트 API 콜 지속 + 잔존 스레드가 새 변환의 기록 폴더 오염 / COM 렌더 중 취소 체크포인트 없음 → closeEvent terminate 상시화(고아 Hwp 자가 생성) | gui/main_window.py:554,750,1590-1607 | 📐 |
| 5 | 부분 실패 캐시 박제 — 크롭 1개 OCR 실패 시에도 `_complete.json` 기록 → 문항 빠진 캐시 무한 재사용 | gui/main_window.py:722-804 | 📐 |
| 6 | testkit `--recrop` 이 OCR 캐시(인덱스 키) 무효화 안 함 → 새 박스에 옛 내용+번호 덮어쓰기(오염 은폐) / `--render-only` 가 API 키 요구 | scripts/testkit.py:93-131 | 📐 |
| 7 | template_loader HWP→HWPX 변환 침묵 실패 + stale .hwpx 통과(`exists()` 만 검사 — save_hwpx 에서 고친 동일 패턴 미반영) | core/template_loader.py:240-298 | 📐 |
| 8 | hwpx_writer(폴백): PMATRIX/cases 높이 1줄 오판✅·`block.hwp_equation` 무시(italicize_stat 발산)📐·제어문자 TEXT 크래시📐·임베드 이미지 manifest 미등록📐 | core/hwpx_writer.py | 혼합 |
| 9 | form_registry: exe 옆 forms/ 로 "폼 교체" 불가(번들 선착 dedupe — docstring 목적과 모순) / 학년 폴백 오탐✅ | core/form_registry.py:69-135 | 혼합 |
| 10 | `Question.score` 주석 `Optional[int]` 거짓 — 소수배점은 float 저장(CLAUDE.md "score 는 int" 합의 문구도 불일치). 현 소비자는 우연히 동작 | models/exam_document.py:45 | 📐 |

---

## C. LOW (요약 — 상세는 각 영역 에이전트 보고)

- latex_to_hwpeq: `x\boxed{}` lead 공백, `2 L` 공백 허용 단위화, bold 가드 불발(`\mathbf{AB}`→`bold rm{AB}`), `\right.` 고아 LEFT, `\bmod` 증발.
- content_parser: `(3점, 4점)` 나열 통삭제(쉼표 분기 과매칭 — B-5 의 `_CLOSE_SCORE_JEOM_RE` 확장 부작용), 문장 중간 배점 제거 시 공백 소실, 영문 다단어 수식 오분류(`file_name`), 다사중 가드 lookahead 6블록 고정, 라벨 없는 다단락 지문박스 둘째 단락 유출(설계 트레이드오프).
- hwp_form_writer: `_first_para_end` self-closing `<hp:p/>` depth 비복귀(실파일상 이론적), `(1), (2)에서` 다중 교차참조 strip 오발동(hwp_form_writer:591-599, ✅재현), 마커 뒤 공백 누락 OCR 시 역방향 중복, `_inject_essay_meta` 템플릿 오선택('난이도' 단어 품은 본문), `_embed_figures` 토큰→임의 pic 바인딩, `_fit_image_width` 예외 시 원본 반환(검정 그림 재유입), grow `a[2]` IndexError 가능, 메타 루프 3회 후 최종 검증 없음.
- hwp_com_writer: 1×1 탐지 속성 순서 의존, 중첩표 음영/폼 치환 스킵, 2열 판정 한글 전각폭 미반영, 2열 한글 선택지 수식 객체화(자기 규칙 모순), `_set_endnote_suffix` 각주 포함 전역 변경, post 블록수식 꼬리 defer 배점 가운데 인라인, table_end MoveDown 폴백 표 재진입.
- ocr/크롭: CropBox.clamp 가 qtype/note 소실(편집기 라벨 공백), questions 0개 크롭 불필요 전사 호출, raw 탭 미복구, 재시도 곱셈(5×5), pdf_handler finally 미보호.
- GUI/스크립트: corpus_lint 단락 경계 소실 배점중복 오탐, verify chk23 멀티라인 포매팅 시 거짓 FAIL, crop_editor 최소크기 클램프 역방향, 캐시 재변환 page_number 재부여.

## D. 점검했으나 결함 없음 (반박으로 기각된 의심 포함)

- zip 재작성(`_rewrite_zip`/`_repackage_hwpx`): ZipInfo·순서·os.replace 재시도 전부 건전. `_replace_retry` 누락 지점 없음.
- 캐럿 합의 #9: `MoveSel*` 잔존 사용처 0, SelectText sp→ep 정확.
- usage 집계 락·키 노출 경로·CSV BOM/이스케이프·워커의 UI 직접 접근: 결함 없음(BOM 의심은 실행 검증으로 기각).
- `\left...\right` 고정점: 무한루프/지수폭발 없음. `_LATEX_CMD_RE` 새 한글직결 경계 `(?![a-zA-Z])` 자체: 회귀 없음.
- `_adaptive_columns` 비례축소 overflow 의심: 재현 시도 후 기각. `_strip_answer_header_redefine` 과매칭(본문 삼킴) 의심: 직결 패턴이라 기각.
- 모델 mutable default·hwpx NS·quality_checker: 결함 없음.

---

## E. 우선순위 수정 로드맵 제안

1. **A-1**(오늘 커밋 회귀 — Σ/∫ 전체) + **A-2**(GREEK/FUNC 패딩) + B-1-1(`\not`) — latex_to_hwpeq 일괄, verify-latex-hwpeq 케이스 추가.
2. **A-5·A-6**(content_parser 배점 소실·기하 오판) — 데이터 손상/광역 스타일 직결.
3. **A-3**(크롭 빈 리스트)·B-2-2(`_msg_text` 우회) — 문항/페이지 침묵 소실 차단.
4. **A-4**(corpus_lint 게이트)·B-5-1·2(verify 무력 검사)·B-3-2(save_pdf 검증) — **검수 인프라 자체의 신뢰성**(이게 뚫리면 이후 corpus 검수 전부가 의심 대상).
5. B-4-1·2·3(폼 라벨 변조·renumber 가드·grow 침묵 탈락), B-3-1(force_layout Visible).
6. 나머지 MED/LOW 는 차기 corpus 검수 사이클에 점진 반영.
