"""Claude OCR 응답을 구조화 데이터(ExamDocument)로 변환하는 파서."""

from __future__ import annotations

import re

from models.exam_document import (
    ContentBlock,
    ContentType,
    Choice,
    Question,
    ExamPage,
    ExamDocument,
)

# 텍스트 내 인라인 LaTeX $...$ 감지 패턴
_INLINE_LATEX_RE = re.compile(r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)")


def parse_ocr_response(ocr_result: dict, page_number: int) -> ExamPage:
    """OCR 결과 dict를 ExamPage 객체로 변환.

    Args:
        ocr_result: Claude OCR 응답 JSON dict
        page_number: 페이지 번호 (1부터)

    Returns:
        ExamPage 객체
    """
    page = ExamPage(page_number=page_number)
    page.header_text = ocr_result.get("header", "")

    for q_data in ocr_result.get("questions", []):
        question = _parse_question(q_data)
        page.questions.append(question)

    return page


# 박스 머리 마커(들머리 ``<상자>``/``<조건>``/``<보기>``/``[조건]``/``[보기]``) 제거용.
_BOX_MARK_LEAD_RE = re.compile(r"^\s*(?:<\s*(?:상자|조건|보기)\s*>|\[\s*(?:조건|보기)\s*\])\s*")
_MIN_DUP_BOX_KO = 8   # 중복 박스 판정 최소 한글 글자수(짧은 우연 일치 방지)


def _drop_duplicate_box_fragments(raw: list[dict]) -> list[dict]:
    """발문 본문의 부분 문자열을 그대로 담은 **중복 박스 조각**(비전 OCR 환각)을 제거.

    비전 모델이 발문 일부를 잘라 ``<상자>`` 텍스트 블록으로 한 번 더 방출하면, 없던
    네모박스가 렌더된다(경명여중 중2 #20: ``<상자> 자연수)의 꼴로 나타낸 후, …몇 자리
    자연`` = 발문 ``…은 자연수)의 꼴로 나타낸 후…`` 의 조각). 판정은 **한글만 정규화**한
    뒤(수식·위첨자·기호는 LaTeX↔유니코드로 표기가 달라 비교 불가) 박스 내용 한글이 다른
    블록들의 한글 연쇄에 **부분 문자열**로 들어 있으면 중복으로 본다. 진짜 박스(지문·조건)
    내용은 발문에 그대로 반복되지 않으므로 안전하고, 최소 길이(_MIN_DUP_BOX_KO)로 우연
    일치를 막는다. 박스 머리로 시작하는 text 블록만 검사한다.
    """
    def _ko(s: str) -> str:
        return re.sub(r"[^가-힣]", "", s or "")

    drop_idx: set[int] = set()
    for i, bd in enumerate(raw):
        if bd.get("type") != "text":
            continue
        val = bd.get("value", "") or ""
        if not _BOX_MARK_LEAD_RE.match(val):
            continue
        box_ko = _ko(_BOX_MARK_LEAD_RE.sub("", val))
        if len(box_ko) < _MIN_DUP_BOX_KO:
            continue
        others_ko = "".join(_ko(b.get("value", "")) for j, b in enumerate(raw)
                            if j != i and b.get("type") == "text")
        if box_ko in others_ko:
            drop_idx.add(i)
    if not drop_idx:
        return raw
    return [bd for i, bd in enumerate(raw) if i not in drop_idx]


def _parse_question(q_data: dict) -> Question:
    """문제 dict를 Question 객체로 변환."""
    question = Question(
        number=q_data.get("number", 0),
        score=q_data.get("score"),
        label_type=q_data.get("label_type") or "",   # 서답형/서술형/단답형(폼 라벨·정답 동기화용)
    )

    # 배점 처리(원시 단계): 숫자 분리 전에 raw 텍스트에서 [N점]을 추출·제거한다.
    # (숫자 분리가 "[9점]"의 9를 수식으로 떼어내면 정규식이 못 맞추므로 반드시 먼저.)
    # ⚠️ 캡처와 제거(_SCORE_TEXT_RE)는 같은 패턴을 봐야 한다 — 캡처가 정수만 보고 제거가
    #    소수([4.5점])·총점([총 7점])까지 지우면 배점이 **캡처 없이 소실**된다(2026-06-10 감사).
    #    [총 N점](소문항 부모 총점)도 score 로 캡처 — 렌더러가 우측정렬 "[총 N점]" 으로 복원.
    raw_contents = [dict(bd) for bd in q_data.get("contents", [])]
    # 비전 OCR 환각으로 발문 일부가 ``<상자>`` 박스로 중복 방출된 조각을 먼저 제거한다
    # (경명여중 중2 #20: 발문 ``…은 자연수)의 꼴로…`` 앞에 ``<상자> 자연수)의 꼴로…``
    # 유령 박스, 2026-06-11). 안 지우면 ① 없던 네모박스가 렌더되고 ② box_head_i 가 그 박스를
    # 가리켜 발문 배점 제거가 통째 스킵된다.
    raw_contents = _drop_duplicate_box_fragments(raw_contents)
    # 박스(<상자>/<조건>/<보기>) 머리가 시작되는 raw 블록 — 그 **이후** [N점]은 채점기준 등
    # 박스 내용이므로 배점 캡처·제거 대상이 아니다(새론중 서답형2 채점기준 박스 안
    # [1점][3점][2점][4점] 이 발문 배점으로 오인돼 통째 소실, 2026-06-11). 발문 배점은 박스 앞.
    box_head_i = next((i for i, bd in enumerate(raw_contents)
                       if bd.get("type") == "text"
                       and _RAW_BOX_MARK_RE.search(bd.get("value", ""))), len(raw_contents))
    box_end = _raw_box_end(raw_contents)
    # 배점 캡처·제거 대상 = 박스 **밖** raw 블록 = 박스 머리 전(pre) + 박스 뒤 발문연속(post).
    # 박스 내용(머리~끝)은 채점기준 [1점][3점] 등 보호(새론중). **post 끝 [N점] 도 반드시
    # 캡처** — 안 하면 _finalize→_strip_score_text 가 지워 배점이 캡처 없이 완전 소실되던
    # 결함(적대리뷰 A-5, 장산중 D4 "박스→발문연속 끝 [N점]" 표준 위치). "캡처 없이 소실 금지".
    _score_idxs = list(range(box_head_i))
    if box_end is not None:
        _score_idxs += list(range(box_end, len(raw_contents)))
    if not question.score:
        for i in _score_idxs:
            bd = raw_contents[i]
            if bd.get("type") == "text":
                m = re.search(r'[\[(]\s*(?:총\s*)?(\d+(?:\.\d+)?)\s*점\s*(?:,[^\])]*)?[\])]', bd.get("value", ""))
                if m:
                    v = float(m.group(1))
                    question.score = int(v) if v.is_integer() else v
                    break
    for i in _score_idxs:
        bd = raw_contents[i]
        if bd.get("type") == "text" and bd.get("value"):
            bd["value"] = _SCORE_TEXT_RE.sub(' ', bd["value"])

    # 문제 본문 — 박스(<조건>/<보기>/<상자>) raw 블록 뒤에 발문이 더 이어지면(#18·#20),
    # **raw 경계**에서 [발문+박스]와 [박스 뒤 발문 연속]을 나눠 따로 파이프라인을 돌리고
    # 박스 블록에 box_member 태그를 단다. 인라인 수식 분리 후엔 박스 경계가 사라지므로
    # (박스 항목 수식이 발문 수식과 구별 불가) raw 단계에서 잡아야 한다.
    if box_end is not None:
        head = _finalize_contents(_parse_raw_blocks(raw_contents[:box_end]))
        post = _finalize_contents(_parse_raw_blocks(raw_contents[box_end:]))
        _tag_box_run(head)                       # 박스 마커 블록부터 head 끝까지 box_member
        question.contents = head + post
    else:
        question.contents = _finalize_contents(_parse_raw_blocks(raw_contents))

    # 선택지 — 발문의 기하 문맥을 선택지로 전파한다. 발문 "좌표평면 위의 점 A,B,C,D,E…"의
    # 선택지 ``A(2,3)``·``B(-3,1)`` 은 선택지 자체엔 기하 키워드가 없어 점 이름이 이탤릭으로
    # 새던 것(대륜중 #1) → 발문에 기하 문맥이 있으면 점 좌표 선택지를 로만+이탤릭으로 처리.
    q_geo = _has_geometry_context(question.contents)
    for choice_data in q_data.get("choices", []):
        choice = _parse_choice(choice_data, parent_geo=q_geo)
        if choice:
            question.choices.append(choice)

    # 소문항
    for sub_data in q_data.get("sub_questions", []):
        sub = _parse_question(sub_data)
        question.sub_questions.append(sub)

    return question


def _parse_choice(choice_data: dict, parent_geo: bool = False) -> Choice | None:
    """선택지 dict를 Choice 객체로 변환.

    parent_geo: 부모(발문)에 기하 문맥(점·좌표평면…)이 있으면 선택지의 점 좌표 라벨도
    로만(점 글자)+이탤릭(좌표)으로 처리한다(선택지 자체엔 키워드가 없어도). 대륜중 #1.
    """
    number = choice_data.get("number", 0)
    if not number:
        return None

    choice = Choice(number=number)
    for block_data in choice_data.get("contents", []):
        result = _parse_content_block(block_data)
        if isinstance(result, list):
            choice.contents.extend(result)
        elif result:
            choice.contents.append(result)

    # 수식 끝 정의역 (x=0, 1, ⋯, 50) 을 본수식에서 떼어 개별 수식+텍스트로(줄바꿈 자연화)
    choice.contents = _split_trailing_domain(choice.contents)
    # 쉼표로 구분된 독립 수식 분리
    choice.contents = _split_comma_equations(choice.contents)
    # eq·(연산자)·eq 로 쪼개진 수식을 한 객체로 병합
    choice.contents = _merge_operator_split_equations(choice.contents)
    # text(꼬리부등식)·eq·text(머리부등식) 병합
    choice.contents = _merge_text_eq_fragments(choice.contents)
    # 온도 단위 °C/°F (EQ+TEXT"°"+EQ"C") 한 수식 병합
    choice.contents = _merge_degree_temp_units(choice.contents)
    # 부모(발문) 기하 문맥 + 선택지 자체 문맥. 셋(stat/point/nongeo)에 같은 게이트를 줘야
    # _romanize_point_names 가 만든 점 라벨을 _italicize_nongeo_single_letters 가 안 벗긴다.
    geo = parent_geo or _has_geometry_context(choice.contents)
    # 확통 연산자·확률변수 \mathrm 벗겨 이탤릭(순열 제외)
    choice.contents = _italicize_stat_operators(choice.contents, force_geo=geo)
    # 기하 점/선/면 이름 로만체 강제
    choice.contents = _romanize_point_names(choice.contents, force_geo=geo)
    # 비기하 단일대문자 \mathrm 벗겨 이탤릭(조합 C·순열 P_ 제외)
    choice.contents = _italicize_nongeo_single_letters(choice.contents, force_geo=geo)
    # 각(∠)·삼각함수·도(°) 뒤 단일 대문자 로만체 — ∠ 등은 본질적 기하라 게이트 없이 적용.
    # **마지막**에(나 비기하 italicize 뒤) 적용해 ∠R·∠P 로만화가 되돌려지지 않게 한다
    # (발문엔 _finalize_contents 가 적용하나 선택지 경로엔 빠져 ∠R 이 이탤릭으로 남던 것,
    # 강북중 중2 2학기 #5 ∠R·∠P 닮음 도형, 2026-06-15).
    choice.contents = _romanize_angle_letters(choice.contents)

    return choice


# 조건/보기 박스 동그라미 불릿 표준 글자(사용자 2026-06-09: "가장 작은 걸로 통일·명시").
# ㅇ(한글 이응)는 ○ 의 OCR 오인식이라 표준 흰 원 ○ 로 통일한다(더 작은 글자 원하면 이 상수만 변경).
_BOX_BULLET = "○"
# 단독 원형 불릿 변형들(앞뒤 공백으로 둘러싸인 것만 — 단어 속 글자 오치환 방지). ∘(U+2218
# 합성연산자)·°·라틴 o/O·키릴 О 는 제외(수식 기호·기하 점 O·변수 오치환 방지).
# ㅇ(U+3147)·●(U+25CF)·〇(U+3007)·◦(U+25E6)·∙(U+2219) 를 표준 ○ 로 통일.
_BOX_CIRCLE_RE = re.compile(r"(?:(?<=\s)|^)[ㅇ●〇◦∙](?=\s)")   # ^ = raw 블록이 불릿으로 시작


def _normalize_box_circles(text: str) -> str:
    """조건/보기 박스의 단독 원형 불릿(ㅇ ● 〇 ◦ …)을 표준 ``○`` 로 통일."""
    return _BOX_CIRCLE_RE.sub(_BOX_BULLET, text)


def _parse_content_block(block_data: dict) -> ContentBlock | None:
    """콘텐츠 블록 dict를 ContentBlock 객체로 변환.

    텍스트 블록 안에 $...$ 인라인 LaTeX가 포함된 경우
    텍스트+수식으로 분리하여 리스트로 반환하므로,
    호출부에서 리스트 여부를 확인해야 합니다.
    """
    type_str = block_data.get("type", "")
    value = block_data.get("value", "")

    # figure 블록은 워커(_resolve_figures)에서 image 로 해소되어야 한다.
    # 여기까지 남아 있으면 해소 실패분이므로 드롭(설명 텍스트 잔재 방지).
    if type_str == "figure":
        return None

    # 조건/보기 박스의 동그라미 불릿 통일 — OCR 이 같은 시험지에서 ㅇ(한글)·○·●·〇 등을
    # 혼용해 크기가 제각각(사용자 2026-06-09). 단독 원형 불릿을 하나로 정규화(∘=합성연산자 제외).
    if type_str == "text" and value:
        value = _normalize_box_circles(value)

    # 표(table)는 value 가 비어 있고 rows 에만 내용이 있는 게 정상(OCR/표복구 스키마).
    # value 빈값 드롭 규칙에서 제외해야 표가 통째 사라지지 않는다(2026-06-08).
    if not value and type_str not in ("image", "table"):
        return None

    type_map = {
        "text": ContentType.TEXT,
        "equation": ContentType.EQUATION,
        "equation_block": ContentType.EQUATION_BLOCK,
        "image": ContentType.IMAGE,
        "table": ContentType.TABLE,
    }

    content_type = type_map.get(type_str)
    if content_type is None:
        content_type = ContentType.TEXT

    # 연립방정식(cases)을 OCR이 equation_block 으로 줘도 **인라인**으로 강등한다
    # (2026-06-05). 발문 중간의 연립("연립방정식 {…} 의 풀이…")이 가운데정렬 블록으로
    # 떠서 문장이 끊기던 문제 — 워드처럼 연립방정식 옆에 중괄호가 붙도록. (진짜 독립
    # 표시 수식은 equation_block 그대로 두어 가운데정렬 유지.)
    if content_type == ContentType.EQUATION_BLOCK and r"\begin{cases}" in (value or ""):
        content_type = ContentType.EQUATION

    # 표(table) 블록 처리
    if content_type == ContentType.TABLE:
        rows = block_data.get("rows", [])
        return ContentBlock(type=ContentType.TABLE, value=value, rows=rows)

    # LaTeX \(...\)·\[...\] 구분자를 $...$로 정규화(OCR이 $ 대신 \( \)로 줄 때 대비).
    if content_type == ContentType.TEXT:
        value = _normalize_math_delims(value)

    # OCR JSON 이 ``{"type":"text","value":"않은","underline":true}`` 속성으로 밑줄을
    # 줄 때 — 표준 규약은 ``__마크업__`` 이지만 속성 인코딩이 조용히 평문 강등되던 것
    # (새본리중 #2·#13·#17, 2026-06-12). 명시적 underline 블록은 강조 run 그대로 반환
    # (밑줄 세그먼트는 수식 추출 비대상 — __마크업__ 경로와 동일 취급).
    if content_type == ContentType.TEXT and block_data.get("underline"):
        return ContentBlock(type=ContentType.TEXT, value=value, underline=True)

    # 텍스트 블록에 __밑줄__ 마크업이 있으면 분리. **비밑줄 세그먼트는 나머지 파이프라인
    # ($·LaTeX·혼합수식 분리)에 재투입** — 조기 반환이 같은 블록의 인라인 수식 추출을
    # 억제해 "y가 x에 정비례하지 __않는__" 의 y·x 가 평문 잔존하던 것(월서중 #14, 경구중
    # #12 에서 'B형 근본원인'으로 지목, 2026-06-11). 밑줄 세그먼트(한글 강조)는 그대로.
    if content_type == ContentType.TEXT and "__" in value:
        split = _split_underline_markup(value)
        if len(split) > 1:
            out: list[ContentBlock] = []
            for sb in split:
                if (sb.type == ContentType.TEXT and not sb.underline
                        and "__" not in (sb.value or "")):
                    sub = _parse_content_block({"type": "text", "value": sb.value})
                    if sub is None:
                        continue
                    out.extend(sub if isinstance(sub, list) else [sub])
                else:
                    out.append(sb)
            return out  # type: ignore[return-value]

    # 텍스트 블록에 $...$ 인라인 LaTeX가 있으면 분리
    if content_type == ContentType.TEXT and "$" in value:
        split = _split_inline_latex(value)
        if len(split) > 1:
            return split  # type: ignore[return-value]

    # 텍스트 블록에 LaTeX 명령어(\sqrt, \frac 등)가 있으면 수식 분리
    if content_type == ContentType.TEXT and '\\' in value:
        split = _split_latex_commands(value)
        if len(split) > 1:
            return split  # type: ignore[return-value]
        # 텍스트 전체가 **단일 수식 하나**로 식별되면(예 OCR 이 단위 선택지를 text 로 준
        # "482\mathrm{cm}") 평문 TEXT 로 강등하지 말고 그 수식 블록을 반환한다. 강등하면
        # raw LaTeX(\mathrm)이 평문으로 새 "482₩mathrm{cm}" literal 렌더(성광중 #12 cm
        # 단위). 본문 "1\mathrm{cm}인"은 위 len>1 로 이미 EQ+TEXT 통과 — 이 경로는 선택지
        # 처럼 텍스트가 수식뿐일 때만. (split[0].type!=TEXT = 분리기가 수식으로 승격 확신.)
        if len(split) == 1 and split[0].type != ContentType.TEXT:
            return split[0]

    # 텍스트 블록에 수식 패턴이 섞여 있으면 분리
    if content_type == ContentType.TEXT:
        split = _split_mixed_text_equation(value)
        if len(split) > 1:
            return split  # type: ignore[return-value]
        # 텍스트 전체가 단일 수식 하나로 승격되면(선택지 ``(f^{-1})^{-1}=f`` 같은 순수 ASCII
        # 수식) 평문 강등하지 말고 그 수식 블록 반환 — \\ 경로(위 line)의 단일수식 유지와 동일.
        # 강등하면 ``^{-1}`` 캐럿이 literal 노출(매천고 수하 #4 선택지, 2026-06-14).
        if len(split) == 1 and split[0].type != ContentType.TEXT:
            return split[0]

    return ContentBlock(type=content_type, value=value)


# 콤마 분리에서 '문자(변수)'로 인정하는 단일 항목: 한 글자 + 선택적 첨자(a, b, A, x_1 …).
_VAR_ITEM_RE = re.compile(r'^[A-Za-z](?:[_^]\{?[A-Za-z0-9]+\}?)?$')


def _wrapped_in_parens(v: str) -> bool:
    """문자열 전체가 **한 쌍**의 괄호로 감싸여 있는지(중간에 먼저 안 닫힘)."""
    if not (v.startswith("(") and v.endswith(")")):
        return False
    depth = 0
    for i, ch in enumerate(v):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0 and i != len(v) - 1:
                return False
    return depth == 0


# 점·선·면 등 기하 이름(대문자 A·B·C·O·AB·OAB…)은 한국 교과서 표기상 **로만체**여야 한다.
# OCR 이 \mathrm 을 안 붙이고 평문 대문자로 주면 수식에서 이탤릭으로 렌더된다(사용자 2026-06-08).
# **블록 전체가 대문자 1~4글자(+선택 첨자)인 수식**만 기하 이름 후보로 보고 \mathrm 으로 감싼다
# (소문자 변수 x,y,a,b 는 이탤릭 유지, 'A=2^6' 처럼 연산자·숫자 섞인 건 건드리지 않음 — 안전).
_BARE_UPPER_EQ_RE = re.compile(r'^[A-Z]{1,4}(?:_\{?[A-Za-z0-9]+\}?)?$')
# 첨자 제거 후 순수 대문자 알파벳만 추출(글자 수 판정용).
_UPPER_LETTERS_RE = re.compile(r'^[A-Z]+')
# 좌표를 단 점 이름: 선두 단일 대문자 + ``(`` (또는 ``\left(``) 로 시작하는 좌표쌍. 점 글자만
# 로만, 괄호 안 좌표는 이탤릭으로 끊는다(\mathrm{P}\mathit{(a,b)}). HWP rm 이 뒤 전체로 번지므로
# 통째 로만화하면 a,b 까지 로만으로 깨진다(2026-06-11 렌더 실증). 좌표쌍 판정 = 괄호 안 쉼표
# 존재(함수호출 f(x)·확통 P(X=r) 제외 — 단일인자라 쉼표 없음). 기하 문맥에서만 적용.
_POINT_COORD_RE = re.compile(r'^([A-Z])\s*((?:\\left)?\(.*)$', re.DOTALL)

# 기하 키워드(엄격) — **대문자 1글자** 수식을 로만으로 만들지 결정. 확통의 X·P·E·V·Z·N
# (확률변수·연산자)을 로만으로 만들지 않도록, 점·선·면·다각형 등 **확실한 도형 단어만**
# 포함한다(넓이·함수·그래프 같은 넓은 단어는 X 그래프 오인 방지를 위해 제외). (사용자 2026-06-08)
_GEOMETRY_KEYWORDS = (
    "점", "꼭짓점", "교점", "원점", "중점", "무게중심",
    "삼각형", "사각형", "정사각형", "직사각형", "마름모", "평행사변형", "사다리꼴",
    "선분", "직선", "반직선", "호", "부채꼴",
    # 원 관련 — "반원의 중심을 O" 의 O 가 이탤릭 잔존(새본리중 #20, 2026-06-12).
    # 단독 "중심"·"원" 은 비기하 충돌(정규분포 '평균을 중심으로'·'원소') 위험으로 제외.
    "반원", "지름", "반지름",
    "△", "∠", "∆",
)


# 단일음절 키워드 "점"·"호" 가 **부분문자열**로 비기하 단어에 박혀 오판되던 것 차단(적대리뷰
# A-6): "점수·관점·장점·단점·배점·채점·만점" 의 점, "기호·괄호·번호·신호·부호·보호" 의 호 등.
# 키워드 검사 **전** 이 디코이들을 지워 잔여로만 판정한다. (초점·교점 등 진짜 기하어는 미등재
# → 그대로 "점" 으로 매칭됨. 확통·대수 X·E 가 로만으로 잔존하던 광역 스타일 오염의 근원.)
_NONGEO_DECOY = (
    "점수", "관점", "장점", "단점", "요점", "배점", "채점", "만점", "평점", "득점", "감점",
    "지점",  # 위치/영업점 — "A 지점에서 C 지점까지"(경우의 수·그래프)는 비기하(강북중 중2 #12)
    "기호", "괄호", "번호", "신호", "부호", "보호", "호선", "호출", "구호", "칭호", "호수",
)


def _has_geometry_context(blocks: list[ContentBlock]) -> bool:
    """blocks 안 어느 텍스트/수식에든 엄격 기하 키워드가 있으면 True.

    "점수"·"기호"·"번호" 같은 비기하 단어가 "점"·"호" 부분문자열로 오판되지 않게, 디코이를
    먼저 제거하고 잔여 텍스트로 판정한다(적대리뷰 A-6).
    """
    text = " ".join(str(b.value or "") for b in blocks)
    for decoy in _NONGEO_DECOY:
        text = text.replace(decoy, "")
    return any(k in text for k in _GEOMETRY_KEYWORDS)


# 확통 연산자·확률변수(P 확률·E 기댓값·V 분산·N 정규분포·Z 표준정규·X,Y 확률변수)는
# **이탤릭**이어야 한다(사용자 2026-06-08: "이탤릭인데 로만 된 게 너무 많다"). 그런데 OCR 이
# 이들을 관례적으로 \mathrm(로만)으로 감싼다 → 벗겨서 이탤릭으로. 단 **순열 nPr**(\mathrm{P}
# 뒤에 _ 첨자)은 로만 유지, **조합 nCr** 의 C 는 애초에 대상 아님(아래 집합에 C 없음).
_STAT_MATHRM_RE = re.compile(r'\\mathrm\{([XYPEVNZ])\}(?!\s*_)')


def _italicize_stat_operators(blocks: list[ContentBlock],
                              force_geo: bool = False) -> list[ContentBlock]:
    """수식 안 ``\\mathrm{P/E/V/N/Z/X/Y}`` 를 이탤릭(맨 글자)으로 되돌린다(순열 P_ 는 제외).

    기하 문맥(점·꼭짓점…)이면 스킵 — ``\\mathrm{P}(1,~2)`` 같은 **복합 수식 속 점 라벨**은
    여기서 벗기면 ``_romanize_point_names``(통째 라벨 수식만 재로만화)가 못 되돌려 점 P 가
    이탤릭으로 새던 버그(감사 2026-06-10). 미러(_italicize_nongeo_single_letters)와 동일 게이트.
    force_geo: 부모(발문)에 기하 문맥이 있으면 선택지엔 키워드가 없어도 기하로 취급(점 좌표 선택지).
    """
    if force_geo or _has_geometry_context(blocks):
        return blocks
    out: list[ContentBlock] = []
    for b in blocks:
        if (b.type in (ContentType.EQUATION, ContentType.EQUATION_BLOCK)
                and b.value and "\\mathrm" in b.value):
            nv = _STAT_MATHRM_RE.sub(r"\1", b.value)
            if nv != b.value:
                out.append(ContentBlock(type=b.type, value=nv))
                continue
        out.append(b)
    return out


# 각(angle)은 도형 → 로만체(사용자 2026-06-10: "각도 도형이다"). 큰 수식 속 단일 대문자
# 각도 ``_romanize_point_names``(통째 대문자 블록만)가 못 잡으므로, 각 신호가 명확한 위치의
# 단일 대문자를 부분 로만화한다. 신호: ① 삼각함수 인자(\cos A) ② 각도(A=45°/A=45^\circ)
# ③ \angle A. (소문자 변 a,b,c 는 이탤릭 유지 — 변은 도형 아닌 길이.)
_TRIG_ANGLE_RE = re.compile(r"(\\(?:cos|sin|tan|cot|sec|csc)\s+)([A-Z])(?![A-Za-z])")
_DEG_ANGLE_RE = re.compile(
    r"(?<![A-Za-z\\{])([A-Z])(\s*=\s*\d+(?:\.\d+)?\s*(?:\^\s*\{?\s*\\circ|°))")
_ANGLE_CMD_RE = re.compile(r"(\\angle\s+)([A-Z])(?![A-Za-z])")


def _romanize_angle_letters(blocks: list[ContentBlock]) -> list[ContentBlock]:
    """각(angle) 단일 대문자를 ``\\mathrm`` 로 로만체화 — 삼각함수 인자·각도(°)·``\\angle``."""
    out: list[ContentBlock] = []
    for b in blocks:
        if b.type in (ContentType.EQUATION, ContentType.EQUATION_BLOCK) and b.value:
            v = _TRIG_ANGLE_RE.sub(lambda m: m.group(1) + "\\mathrm{" + m.group(2) + "}", b.value)
            v = _DEG_ANGLE_RE.sub(lambda m: "\\mathrm{" + m.group(1) + "}" + m.group(2), v)
            v = _ANGLE_CMD_RE.sub(lambda m: m.group(1) + "\\mathrm{" + m.group(2) + "}", v)
            if v != b.value:
                out.append(ContentBlock(type=b.type, value=v))
                continue
        out.append(b)
    return out


# 행렬 문맥의 대문자 연속런(행렬곱 AB·AC·BA) — \mathit{} 이탤릭 명시 보호용.
# LaTeX 명령(소문자)·env 키워드는 앞 백슬래시/영문자 lookbehind 로 제외.
_MATRIX_UPPER_RUN_RE = re.compile(r"(?<![A-Za-z\\])[A-Z]{2,4}(?![A-Za-z])")


def _romanize_point_names(blocks: list[ContentBlock],
                          force_geo: bool = False) -> list[ContentBlock]:
    """기하 점/선/면 이름(통째 대문자 수식 블록)을 \\mathrm 으로 감싸 로만체로 강제.

    **기하 도형 라벨에만** 적용한다(사용자 2026-06-08: "도형 아닌데 로만체 너무 많다").
      - 대문자 2~4글자(AB, ABC, OAB …) = 꼭짓점 라벨 → 무조건 로만(통계엔 거의 없음).
      - 대문자 1글자(A, X, P, E …) = **같은 contents 에 기하 키워드가 있을 때만** 로만.
        없으면 이탤릭 유지(확률변수 X·연산자 P/E/V 등을 로만화하지 않기 위해).
      - 좌표 단 점 이름(P(a,b)·A(-5,-3)) = 기하 문맥에서 **점 글자만** \\mathrm, 괄호 안
        좌표는 \\mathit(이탤릭). HWP rm 이 명시적 it 전까지 뒤 전체로 번지므로 통째 로만화하면
        a,b 까지 로만으로 깨진다(2026-06-11 렌더 실증). 좌표쌍 판정 = 괄호 안 쉼표(함수호출
        f(x)·확통 P(X=r) 는 단일인자라 쉼표 없음·비기하라 제외).
    force_geo: 부모(발문)에 기하 문맥이 있으면 선택지엔 키워드가 없어도 기하로 취급. 발문
        "좌표평면 위의 점 A,B,C,D,E…" 의 선택지 ``A(2,3)``·``B(-3,1)`` 처럼 좌표 단 점 이름이
        선택지 문맥(키워드 없음)에서 이탤릭으로 새던 것 차단(대륜중 #1, 사용자 2026-06-11).

    ⚠️ **행렬 문맥이면 로만화 대신 이탤릭 명시** — 2022 개정 공수1 행렬 단원에서 행렬곱
    ``AB``·``AC`` 가 "2글자 이상 항상 로만" 규칙에 걸려 정자로 깨졌다(상원고 #22
    ``AB=pmatrix``·#12 명제 보기 ``AB=AC`` — 원본은 이탤릭 행렬 변수). 같은 문항 contents
    에 '행렬' 키워드가 있으면 대문자 라벨은 도형이 아니라 행렬이다(행렬+기하 혼합 문항은
    사실상 없음). 파서 스킵만으론 부족 — **latex_to_hwpeq `_apply_roman_labels` 가 변환
    스크립트 레벨에서 대문자 연속런을 무조건 `rm{}` 로 감싸므로**, ``\\mathit{}`` 로 명시
    감싸 변환기 로만화를 차단한다(`it {` 직전 런은 스킵됨 — 도원중 `rm` 번짐 실증 참고).
    """
    joined_txt = "".join((b.value or "") for b in blocks if b.type == ContentType.TEXT)
    if "행렬" in joined_txt:
        for b in blocks:
            if (b.type == ContentType.EQUATION and b.value and "\\math" not in b.value):
                b.value = _MATRIX_UPPER_RUN_RE.sub(
                    lambda m: "\\mathit{" + m.group(0) + "}", b.value)
        return blocks
    has_geo = force_geo or _has_geometry_context(blocks)
    out: list[ContentBlock] = []
    for b in blocks:
        if b.type == ContentType.EQUATION:
            v = (b.value or "").strip()
            if v and "\\math" not in v and _BARE_UPPER_EQ_RE.match(v):
                m = _UPPER_LETTERS_RE.match(v)
                n_letters = len(m.group(0)) if m else 0
                # 2글자 이상은 라벨로 보고 항상 로만, 1글자는 기하 문맥에서만 로만.
                if n_letters >= 2 or (n_letters == 1 and has_geo):
                    out.append(ContentBlock(type=ContentType.EQUATION,
                                            value=f"\\mathrm{{{v}}}"))
                    continue
            # 좌표 단 점 이름 P(a,b)·A(-5,-3)·C(\frac{a}{b},-a): 점 글자만 로만, 좌표는 이탤릭.
            mc = _POINT_COORD_RE.match(v) if (has_geo and v and "\\math" not in v) else None
            if mc and "," in mc.group(2):
                out.append(ContentBlock(
                    type=ContentType.EQUATION,
                    value=f"\\mathrm{{{mc.group(1)}}}\\mathit{{{mc.group(2)}}}"))
                continue
        out.append(b)
    return out


# 비기하 문맥에서 OCR 이 단일 대문자를 ``\mathrm{A}`` 로 감싸면(체스 선수 A·B, 사건 A 등)
# 로만으로 굳어 어색하다(사용자 2026-06-09: "도형이 아닌데 로만체 처리"). 기하 문맥이 아니면
# **단일 대문자** ``\mathrm`` 를 벗겨 이탤릭으로. 단 조합 ``\mathrm{C}``·순열 ``\mathrm{P}_``
# (아래첨자)은 로만 유지. (확통 X·Y·P·E·V·N·Z 는 _italicize_stat_operators 가 이미 처리.)
_NONGEO_SINGLE_MATHRM_RE = re.compile(r'\\mathrm\{([A-BD-Z])\}(?!\s*_)')


def _italicize_nongeo_single_letters(blocks: list[ContentBlock],
                                     force_geo: bool = False) -> list[ContentBlock]:
    """기하 문맥이 **아닐 때만** 단일 대문자 ``\\mathrm{A}`` 를 이탤릭으로(조합 C·순열 P_ 제외).

    force_geo: 부모(발문) 기하 문맥이면 선택지도 기하로 취급해 스킵 — 그래야 직전
    ``_romanize_point_names`` 가 만든 점 라벨 ``\\mathrm{A}\\mathit{(…)}`` 를 다시 안 벗긴다.
    """
    if force_geo or _has_geometry_context(blocks):
        return blocks
    out: list[ContentBlock] = []
    for b in blocks:
        if (b.type in (ContentType.EQUATION, ContentType.EQUATION_BLOCK)
                and b.value and "\\mathrm" in b.value):
            nv = _NONGEO_SINGLE_MATHRM_RE.sub(r"\1", b.value)
            if nv != b.value:
                out.append(ContentBlock(type=b.type, value=nv))
                continue
        out.append(b)
    return out


# 두 수식 사이의 "연산자만" 텍스트(=, <, >, ≤, ≥, ≠, +, -, ×, ÷, ± …) — 이걸로 쪼개진
# 수식을 한 객체로 다시 합친다. 쉼표(,)는 제외(나열 분리는 의도적). 한글/단어가 섞이면 제외.
_EQ_OP_CHARS = set("=<>≤≥≠≈≡≅∼+-±×÷·∘*/^∓→↔⇒⇔")


def _is_operator_only(text: str) -> bool:
    """텍스트가 **연산자/관계기호만**(공백 무시)으로 이뤄졌는지 — 수식 병합 판정용.

    내부 공백("= -")도 허용해야 ``x = -2y+3`` 처럼 ``= -`` 로 쪼개진 케이스가 합쳐진다.
    """
    s = re.sub(r"\s+", "", text or "")
    return bool(s) and all(c in _EQ_OP_CHARS for c in s)


# 점화식·함수 뒤에 바로 붙는 **범위/정의역 나열** ``(n=1, 2, 3 ⋯)`` 은 앞 수식과 붙어
# ``a_n+4(n=1,2,3⋯)`` 처럼 공백 없이 렌더된다(사용자 2026-06-10 #5). 앞 수식에 ``~``(HWP
# 빈칸)로 병합해 한 수식+공백으로 — n 은 이탤릭 유지(평문화하면 정자됨).
_PAREN_RANGE_RE = re.compile(r"^\(.*\)$")


def _merge_degree_temp_units(blocks: list[ContentBlock]) -> list[ContentBlock]:
    """온도 단위 ``°C``/``°F`` 병합 — 인라인 수식 분리가 ``6°C`` 를 EQ"6"+TEXT"°"+EQ"C"
    로 쪼개 C 를 단독 이탤릭 변수로 만들고 사이에 공백까지 생기던 것(성광중 #17). ``°`` 직후
    단일 대문자 C/F 는 온도 단위이므로 한 수식 ``6°\\mathrm{C}``(→ ``6°rm C``, C 정자)로 병합.
    각도 ``45°``(뒤가 C/F 아님)·점 이름 C 는 무영향(strict 게이트)."""
    eq_types = (ContentType.EQUATION, ContentType.EQUATION_BLOCK)
    out: list[ContentBlock] = []
    i = 0
    while i < len(blocks):
        b = blocks[i]
        nxt = blocks[i + 1] if i + 1 < len(blocks) else None
        nn = blocks[i + 2] if i + 2 < len(blocks) else None
        if (b.type in eq_types and nxt is not None and nn is not None
                and nxt.type == ContentType.TEXT and (nxt.value or "").strip() == "°"
                and nn.type in eq_types and (nn.value or "").strip() in ("C", "F")):
            unit = (nn.value or "").strip()
            out.append(ContentBlock(
                type=ContentType.EQUATION,
                value=(b.value or "").rstrip() + "°\\mathrm{" + unit + "}"))
            i += 3
            continue
        out.append(b)
        i += 1
    return out


def _merge_paren_range(blocks: list[ContentBlock]) -> list[ContentBlock]:
    """앞 수식 + 인접 괄호범위 수식 ``(n=1,2,3⋯)`` 을 ``~`` 공백으로 한 수식에 병합."""
    eq_types = (ContentType.EQUATION, ContentType.EQUATION_BLOCK)
    out: list[ContentBlock] = []
    for b in blocks:
        v = (b.value or "").strip()
        if (b.type == ContentType.EQUATION
                and _PAREN_RANGE_RE.match(v) and "=" in v
                and ("," in v or "cdots" in v or "dots" in v or "⋯" in v)):
            # 앞에 낀 공백-only 텍스트는 건너뛰고 직전 수식에 ~ 공백으로 병합.
            j = len(out) - 1
            if j >= 0 and out[j].type == ContentType.TEXT and not (out[j].value or "").strip():
                j -= 1
            if j >= 0 and out[j].type in eq_types:
                out[j] = ContentBlock(type=out[j].type,
                                      value=(out[j].value or "").rstrip() + " ~ " + v)
                del out[j + 1:]
                continue
        out.append(b)
    return out


def _merge_operator_split_equations(blocks: list[ContentBlock]) -> list[ContentBlock]:
    """``eq · (연산자 text) · eq`` 로 쪼개진 수식을 **한 수식 객체**로 병합(사용자 2026-06-08).

    OCR/분리가 ``x = -2y+3`` 을 ``eq("x") + text("=") + eq("-2y+3")`` 으로 쪼개면 가운데
    ``=`` 만 평문이라 기준선·글꼴이 어긋나 ``x =-2y+3`` 처럼 이상하게 보인다. 연산자만 든
    텍스트로 이어진 인접 수식들을 ``x = -2y+3`` 한 객체로 합쳐 한 번에 수식 렌더한다.
    (쉼표 나열·한글 연결어(``이고``)는 연산자가 아니라 병합 안 함 → 의도된 분리 보존.)
    """
    out: list[ContentBlock] = []
    i, n = 0, len(blocks)
    while i < n:
        b = blocks[i]
        if b.type == ContentType.EQUATION:
            parts = [(b.value or "").strip()]
            j = i + 1
            while (j + 1 < n
                   and blocks[j].type == ContentType.TEXT
                   and _is_operator_only(blocks[j].value)
                   and blocks[j + 1].type == ContentType.EQUATION):
                parts.append((blocks[j].value or "").strip())
                parts.append((blocks[j + 1].value or "").strip())
                j += 2
            if len(parts) > 1:
                out.append(ContentBlock(type=ContentType.EQUATION,
                                        value=" ".join(p for p in parts if p)))
                i = j
                continue
        out.append(b)
        i += 1
    return out


# 관계연산자(부등호·등호) — 텍스트 꼬리/머리에 붙은 수식 조각을 인접 수식으로 빨아들일 때 쓴다.
_FRAG_RELOP = r"(?:=|<|>|≤|≥|≠|\\le|\\leq|\\ge|\\geq|\\neq|\\ne)"
# 수식 원자: 숫자/변수(+소수·첨자), 앞에 부호·여는 괄호 허용.
_FRAG_ATOM = r"[-+]?[0-9A-Za-z][0-9A-Za-z._^{}]*"
# 텍스트 **끝**이 "원자(선택) 관계연산자"로 끝나면(예 "-1 ≤ "·"≤ ") 미완성 식 → 다음 수식과 결합.
_FRAG_TAIL_RE = re.compile(r"(?<![가-힣A-Za-z0-9])((?:" + _FRAG_ATOM + r"\s*)?" + _FRAG_RELOP + r"\s*)$")
# 텍스트 **머리**가 "관계연산자 원자"로 시작하면(예 " ≤ 1") 앞 수식의 연속 → 앞 수식에 결합.
_FRAG_HEAD_RE = re.compile(r"^(\s*" + _FRAG_RELOP + r"\s*" + _FRAG_ATOM + r")(?![0-9A-Za-z])")
# 병합 수식 안 유니코드 부등호 → LaTeX 명령(latex_to_hwpeq 가 LEQ/GEQ 키워드로 정상 변환).
_UNICODE_RELOP = {"≤": r" \leq ", "≥": r" \geq ", "≠": r" \neq "}


def _normalize_frag_relops(s: str) -> str:
    for u, l in _UNICODE_RELOP.items():
        s = s.replace(u, l)
    return re.sub(r"\s+", " ", s).strip()


def _merge_text_eq_fragments(blocks: list[ContentBlock]) -> list[ContentBlock]:
    """``TEXT(…원자 관계연산자) · EQ · TEXT(관계연산자 원자…한글)`` 을 한 수식으로 병합.

    OCR 이 ``-1 ≤ x ≤ 1에서`` 를 ``text("-1 ≤ ") + eq("x") + text(" ≤ 1에서")`` 로 쪼개면
    ``-1`` 이 평문(정자)·``x`` 만 이탤릭이라 어긋난다(사용자 2026-06-09 #12). 텍스트 꼬리의
    미완성 부등식(원자+관계연산자)과 머리의 연속(관계연산자+원자)을 인접 수식에 빨아들여
    ``-1 ≤ x ≤ 1`` 한 객체로 만든다(앞에 한글/영숫자가 붙은 진짜 단어 경계는 건드리지 않음).
    """
    out: list[ContentBlock] = []
    i, n = 0, len(blocks)
    while i < n:
        b = blocks[i]
        if (b.type == ContentType.EQUATION and i + 1 <= n):
            prefix = ""
            # 앞 텍스트 꼬리의 "원자 관계연산자" 흡수
            if out and out[-1].type == ContentType.TEXT and (out[-1].value or ""):
                m = _FRAG_TAIL_RE.search(out[-1].value)
                if m:
                    prefix = m.group(1)
                    out[-1] = ContentBlock(type=ContentType.TEXT,
                                           value=out[-1].value[:m.start(1)],
                                           underline=out[-1].underline)
            suffix = ""
            # 뒤 텍스트 머리의 "관계연산자 원자" 흡수
            if i + 1 < n and blocks[i + 1].type == ContentType.TEXT and (blocks[i + 1].value or ""):
                m2 = _FRAG_HEAD_RE.search(blocks[i + 1].value)
                if m2:
                    suffix = m2.group(1)
                    blocks[i + 1] = ContentBlock(type=ContentType.TEXT,
                                                 value=blocks[i + 1].value[m2.end(1):],
                                                 underline=blocks[i + 1].underline)
            if prefix or suffix:
                merged = _normalize_frag_relops(prefix + " " + (b.value or "") + " " + suffix)
                out.append(ContentBlock(type=ContentType.EQUATION, value=merged))
                # 앞 텍스트가 비었으면 제거(이중 공백 방지)
                if out and len(out) >= 2 and out[-2].type == ContentType.TEXT and not (out[-2].value or "").strip():
                    del out[-2]
                i += 1
                continue
        out.append(b)
        i += 1
    return out


# 수식 끝에 \quad 등으로 붙은 **정의역/조건 나열** ``(x=0, 1, ⋯, 50)`` 을 본수식에서 떼어
# **개별 수식 + 텍스트 괄호·쉼표**로 분리한다(사용자 2026-06-08: #8 메인수식 뒤 정의역을
# 따로 처리해야 줄바꿈이 자연스럽다). 떼는 조건(엄격): 끝 괄호 내용이 **쉼표 나열**이고
# 줄임표(\cdots/\dots/...) 또는 ``=`` 를 포함할 때만 — 좌표쌍 ``(3, 2)``·함수 인자 ``f(x)``·
# 관계식 ``f(12)>f(22)``(쉼표 없음)는 절대 건드리지 않는다(쪼개지면 안 되는 수식 보호).
_TRAILING_DOMAIN_RE = re.compile(
    r"(?:\\quad|\\qquad|\\,|\\;|\\:|\\!|\\ |~|\s)+"      # 본수식과의 구분(\quad 등)
    r"\(\s*(?P<body>[^()]*(?:,[^()]*)+)\)\s*$")           # 끝의 (a, b, ⋯) 나열


def _split_trailing_domain(blocks: list[ContentBlock]) -> list[ContentBlock]:
    """수식 끝 ``\\quad (x=0, 1, ⋯, 50)`` 정의역을 떼어 개별 수식+텍스트로 분리."""
    out: list[ContentBlock] = []
    for b in blocks:
        # EQUATION_BLOCK(독립 디스플레이 수식)은 정의역까지 **통째 유지** — 가운데 한 줄로
        # 렌더해야 자연스럽다. 인라인 EQUATION 만 긴 정의역 꼬리를 떼어 줄바꿈을 자연화한다
        # (이항분포 P(X=r)=…(r=0,1,⋯,72) 가 인라인 텍스트로 쪼개지던 것, 중앙고 #19 2026-06-10).
        if b.type == ContentType.EQUATION and b.value:
            v = b.value.rstrip()
            m = _TRAILING_DOMAIN_RE.search(v)
            if m and re.search(r"\\c?dots|\\ldots|\.\.\.|⋯|=", m.group("body")):
                main = v[:m.start()].rstrip()
                items = [re.sub(r"^(?:\\[,;:!\s]|\\quad|~|\s)+", "", p).strip()
                         for p in _split_at_top_level_commas(m.group("body"))]
                items = [it for it in items if it]
                if main and len(items) >= 2:
                    out.append(ContentBlock(type=b.type, value=main))
                    out.append(ContentBlock(type=ContentType.TEXT, value=" ("))
                    for i, it in enumerate(items):
                        if i > 0:
                            out.append(ContentBlock(type=ContentType.TEXT, value=", "))
                        out.append(ContentBlock(type=ContentType.EQUATION, value=it))
                    out.append(ContentBlock(type=ContentType.TEXT, value=")"))
                    continue
        out.append(b)
    return out


def _split_comma_equations(blocks: list[ContentBlock]) -> list[ContentBlock]:
    """쉼표로 구분된 수식 항목 처리(사용자 규칙 2026-06-05).

    HWP 수식 객체는 공백을 무시하므로 ``a, b, c`` 를 한 수식으로 넣으면 ``a,b,c`` 로 붙어
    보기 나쁘다. 그래서:
      - **문자(변수) 나열**(``a, b, c`` / ``(a, b, c)``): 문자별 **개별 수식 객체** + 쉼표·
        괄호는 **일반 텍스트** → 텍스트 공백이 살아 ``a, b, c`` 로 깔끔히.
      - **좌표/수식 나열**(``(3, 2)`` 처럼 숫자 포함): 쪼개지 않고 **한 수식**으로 두되 쉼표
        뒤를 ``~``(HWP 강제공백)으로 → ``(3,~2)``.
      - 괄호 없는 최상위 수식 나열(예 ``A=2^6, B=3^6``): 종전처럼 개별 수식 + 텍스트 쉼표.
    """
    result: list[ContentBlock] = []
    for block in blocks:
        if block.type == ContentType.EQUATION and "," in (block.value or ""):
            if _split_one_eq_commas(block, result):
                continue
        result.append(block)
    return result


_EDGE_MATH_SPACE_RE = re.compile(
    r"^(?:\\(?:qquad|quad|[,;:! ])\s*)+|(?:\\(?:qquad|quad|[,;:! ])\s*)+$")


def _strip_edge_math_space(p: str) -> str:
    """수식 조각 양끝의 LaTeX 간격명령(``\\quad``·``\\,`` 등)을 제거.

    쉼표로 분리한 각 항목에 적용한다 — 텍스트 쉼표 ``, `` 가 이미 간격을 주므로 ``\\quad``
    (→ HWP ``~~`` 강제공백)이 남으면 틈이 과하게 겹쳐 보인다(경명여중 중2 #18 보기
    ``3+ax \\geq bx, \\quad -0.3x …``, 2026-06-11). 항목 **사이**의 간격은 텍스트 공백으로.
    """
    return _EDGE_MATH_SPACE_RE.sub("", (p or "").strip()).strip()


def _split_one_eq_commas(block: ContentBlock, result: list[ContentBlock]) -> bool:
    """쉼표 든 수식 한 블록을 규칙대로 분해해 ``result`` 에 추가. 처리했으면 True."""
    v = (block.value or "").strip()
    paren = _wrapped_in_parens(v)
    inner = v[1:-1] if paren else v
    parts = [s for s in (_strip_edge_math_space(p)
                         for p in _split_at_top_level_commas(inner)) if s]
    if len(parts) < 2:
        return False
    all_vars = all(_VAR_ITEM_RE.match(p) for p in parts)
    if all_vars:
        # 문자(변수) 나열 → 개별 수식 객체 + 텍스트 쉼표/괄호(공백 보존).
        if paren:
            result.append(ContentBlock(type=ContentType.TEXT, value="("))
        for i, p in enumerate(parts):
            if i > 0:
                result.append(ContentBlock(type=ContentType.TEXT, value=", "))
            result.append(ContentBlock(type=ContentType.EQUATION, value=p))
        if paren:
            result.append(ContentBlock(type=ContentType.TEXT, value=")"))
        return True
    if paren:
        # 좌표/수식 묶음(숫자 포함) → 한 수식 유지, 쉼표 뒤 ~ 강제공백.
        result.append(ContentBlock(type=ContentType.EQUATION,
                                   value=re.sub(r",\s*", ",~", v)))
        return True
    # **스푸리어스 쉼표 방어**(사용자 2026-06-08, 학남고 #12): OCR 이 곱셈에 쉼표를 끼우면
    # ``P(…)=16/9, P(…)`` → "16/9 , P(…)" 로 깨진다. 스푸리어스 = **원자도 관계식도 아닌**
    # 항목(함수식 P(…)·16/9 등)이 하나라도 있을 때만 — 관계식+원자 혼합(``x = 1, 2`` 해답
    # 나열)은 진짜 나열이라 쉼표를 보존한다(감사 2026-06-10: "전부 원자 or 전부 관계식"
    # 조건이 이 혼합의 쉼표를 지웠음).
    if any(not _is_atom_item(p) and not _has_toplevel_relation(p) for p in parts):
        result.append(ContentBlock(type=ContentType.EQUATION, value=" ".join(parts)))
        return True
    # 괄호 없는 수식 나열 → 개별 수식 + 텍스트 쉼표(종전 동작).
    for i, p in enumerate(parts):
        if i > 0:
            result.append(ContentBlock(type=ContentType.TEXT, value=", "))
        result.append(ContentBlock(type=ContentType.EQUATION, value=p))
    return True


# 스푸리어스 쉼표 판정용 보조(괄호 없는 수식 나열 분리 가드).
def _is_atom_item(p: str) -> bool:
    """단순 원자 = 숫자·변수(_VAR_ITEM_RE)·그리스문자·복소수/숫자 리터럴·줄임표 — 진짜 나열 후보.

    근 나열 ``2-3i, \\alpha, \\beta``(상인고 #14) 처럼 항목이 **복소수 상수**(``2-3i``)나
    **그리스 변수**(``\\alpha``)면 진짜 나열이다. 이들을 원자로 인정하지 않으면
    스푸리어스-쉼표 방어가 곱셈 잡음으로 오판해 쉼표를 공백으로 뭉갠다(``2-3iαβ``).
    복소수/숫자 리터럴 = ``0-9 + - . i`` + 공백만으로 구성되고 숫자를 1개 이상 포함.
    그리스/단순기호 = ``\\name`` (선택적 아래/위첨자) — ``\\frac{}{}`` 같은 구조명령은
    뒤에 ``{`` 가 와서 매칭 안 됨(원자 아님 유지)."""
    p = (p or "").strip()
    return bool(_VAR_ITEM_RE.match(p)
                or re.fullmatch(r"[-+]?\d+(?:\.\d+)?", p)
                or (re.search(r"\d", p) and re.fullmatch(r"[0-9+\-.\si]+", p))
                or re.fullmatch(r"\\[A-Za-z]+(?:[_^]\{?[A-Za-z0-9]+\}?)?", p)
                or re.fullmatch(r"\\c?dots|\\ldots|⋯|\.\.\.", p))


def _has_toplevel_relation(p: str) -> bool:
    """괄호·중괄호 **내용 제거 후** 최상위에 관계연산자가 있으면 True(함수 인자 속 ≤ 제외)."""
    s = p or ""
    for _ in range(6):                       # 중첩 괄호/중괄호 반복 제거
        s2 = re.sub(r"\([^()]*\)|\{[^{}]*\}", "", s)
        if s2 == s:
            break
        s = s2
    # \to(사상 화살표)·:(함수 정의 콜론)도 관계로 — 함수 선언 ``f:X \to Y, g:Y \to Z`` 의
    # 쉼표가 스푸리어스(곱셈 잡음)로 오판돼 공백으로 뭉개지며 ``X \to Y g`` 로 붙던 것
    # (경상고 수하 #12, 2026-06-14). 화살표/콜론 든 항목은 명백히 곱셈 조각이 아니다.
    # 기하 관계(\parallel·\perp·합동 \equiv·닮음 \sim·∽)도 관계로 — ``\overline{AD} \parallel
    # \overline{BC}, \overline{AD}=…`` 처럼 평행 관계 + 등식 나열의 쉼표가 스푸리어스로 오판돼
    # 드롭되며 ``BC AD`` 가 붙던 것(강북중 중2 #1 ①, 2026-06-15). 평행/수직/합동 든 항목은
    # 곱셈 조각이 아니라 완결된 관계식이다.
    return bool(re.search(
        r"=|<|>|\\le\b|\\leq\b|\\ge\b|\\geq\b|\\neq\b|\\ne\b|\\in\b"
        r"|\\to\b|\\mapsto\b|\\parallel\b|\\perp\b|\\equiv\b|\\sim\b|\\cong\b"
        r"|→|:|≤|≥|≠|∥|⊥|∽|≡|⫽", s))


def _split_at_top_level_commas(s: str) -> list[str]:
    """최상위 레벨의 쉼표에서 분리 (괄호·중괄호 안 쉼표 무시)."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in s:
        if ch in "({[":
            depth += 1
        elif ch in ")}]":
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(ch)
    parts.append("".join(current))
    return parts


# 텍스트 안에서 수식 구간을 감지하는 패턴
# 영문 변수/숫자 + 수학 연산자(=, >, <, +, -, ×, ÷, ≤, ≥, ≠) 조합
# 예: "a > 0", "b", "x = 3", "2x + 1"
# 원자 = 변수/숫자 + **함수꼴 괄호**(f(-x), P(0≤X≤2/5) 등 — 괄호를 수식 안에 포함, 사용자
# 2026-06-08: "함수괄호는 수식 안에, (x=1,2,3) 값나열만 텍스트"). 괄호 안엔 한글 없음.
# 원자 뒤 LaTeX 첨자(아래/위 — 중괄호 그룹 또는 단일 토큰)를 한 원자로 흡수. 없으면
# ``2a_{n+1}`` 이 ``2a``+``_{``(평문)+``n+1`` 로 쪼개져 중괄호·밑줄이 박스에 literal 로
# 샌다(상인고 수1 #22 ``2a_{n+1}=a_n+a_{n+2}``). 박스/발문 ASCII 수식 공통.
_SUBSUP = r'(?:[_^](?:\{[^{}]*\}|[a-zA-Z0-9]+))*'
# 원자 = 영숫자(+소수) **또는 괄호식 (1+h)** — 둘 다 뒤 첨자(_SUBSUP)를 흡수. 괄호base
# 거듭제곱 ``(1+h)^n`` 이 ``(`` + ``1+h`` + ``)^`` 로 쪼개져 ^n 이 literal 캐럿으로 새던 것
# 방지(능인고 수1 #18). 괄호 안 한글은 제외(텍스트 괄호 "(즉…)" 오인 방지).
# ⚠️ base+첨자를 **반복**(``(?:…)+``) — 첨자 뒤 곧바로 영숫자가 오는 암묵적 곱(``a^{2}bc``·
# ``a_{1}b_{1}``)에서 _MATH_EXPR_RE 의 끝 ``(?![a-zA-Z])`` 가 ``a^{2}`` 뒤 ``b`` 때문에 실패해
# bare ``a`` 로 후퇴 → ``^{``·``_{`` 가 평문 leak 되던 것 차단(시지고·대구외고 수하, 2026-06-14).
_MATH_ATOM = (r'(?:(?:[a-zA-Z0-9]+(?:\.[0-9]+)?|\([^()가-힣]*\))'
              + _SUBSUP + r')+(?:\s*\([^()가-힣]*\))?')
_MATH_EXPR_RE = re.compile(
    r'(?<![a-zA-Z])'              # 앞에 영문자 없음 (단어 중간 방지)
    r'('
    + _MATH_ATOM +               # 시작 원자(함수꼴 포함)
    r'(?:'
    r'\s*[=><+\-×÷≤≥≠^_]\s*'      # 수학 연산자
    + _MATH_ATOM +               # 뒤따르는 원자(함수꼴 포함)
    r')*'
    r')'
    r'(?![a-zA-Z])'              # 뒤에 영문자 없음
)


# 소문항 괄호 로마숫자 마커 (i)(ii)(iii)(iv)(v) — 함수호출 f(i) 와 구별하려 앞에 영숫자 없을 때만.
_SUBMARKER_RE = re.compile(r"(?<![A-Za-z0-9])\(\s*(?:i{1,3}|iv|v)\s*\)")

# 관계/이항 연산자 LaTeX 명령 — 수식이 이걸로 **시작**하면 좌변 ASCII 조각도 수식에 흡수
# (대진고 공수1 #1 ``4x-7 \le …`` 좌변 평문 정자, _split_latex_commands 참고).
_EQ_LEAD_OPCMD_RE = re.compile(r"\\(?:leq|geq|neq|le|ge|ne|times|div|pm|mp|cdot)(?![a-zA-Z])")


def _split_box_marker_prefix(text: str, splitter) -> "list[ContentBlock] | None":
    """텍스트 선두의 박스 마커(``<상자>``/``<보기>``/``<조건>``)를 자기 TEXT 블록으로 보호.

    마커 바로 뒤가 LaTeX 명령이면(``<상자> \\frac…``) 선행 연산자 흡수가 마커의 닫는 ``>``
    를 비교연산자로 끌어가 수식이 ``> \\frac…`` 이 되고 마커가 ``<상자 `` 로 깨진다 —
    렌더러 ``_COND_HEADER_RE`` 가 박스를 인식 못 해 마커 평문 leak + 내용 박스 미적용
    (신명여중 #7 풀이과정 상자, 2026-06-12). 마커를 떼고 나머지만 분리기로 재투입한다.
    (``<보기> 중`` 참조어는 _RAW_BOX_MARK_RE 부정전망이 걸러 가드 미발동 — 기존 동작 유지.)
    """
    m = _RAW_BOX_MARK_RE.match(text)
    if not m or m.end() == 0:
        return None
    rest = text[m.end():]
    blocks: list[ContentBlock] = [ContentBlock(type=ContentType.TEXT, value=text[:m.end()])]
    if rest.strip():
        blocks.extend(splitter(rest))
    return blocks


def _split_mixed_text_equation(text: str) -> list[ContentBlock]:
    """텍스트 안에 섞인 수식 패턴(영문 변수, 부등호 등)을 분리.

    예: "(a > 0, b는 정수)에서"
    → text("(") + eq("a > 0") + text(", ") + eq("b") + text("는 정수)에서")
    """
    # 선두 박스 마커 보호(신명여중 #7 — docstring 은 _split_box_marker_prefix 참고).
    _boxed = _split_box_marker_prefix(text, _split_mixed_text_equation)
    if _boxed is not None:
        return _boxed

    # 소문항 괄호 마커 (i)(ii)(iii)(iv)(v) 는 **괄호 통째** 한 수식으로(사용자 2026-06-10:
    # "소문항처럼 (i) 전체에 수식"). 함수호출 f(i) 오인 방지로 앞에 영숫자 없을 때만.
    _sm = _SUBMARKER_RE.search(text)
    if _sm:
        out: list[ContentBlock] = []
        if _sm.start() > 0:
            out.extend(_split_mixed_text_equation(text[:_sm.start()]))
        out.append(ContentBlock(type=ContentType.EQUATION,
                                value=re.sub(r"\s+", "", _sm.group(0))))
        if _sm.end() < len(text):
            out.extend(_split_mixed_text_equation(text[_sm.end():]))
        return out

    # 한글이 전혀 없으면 분리 불필요 (순수 텍스트거나 이미 수식).
    # ⚠️ 음절(가-힣)만 보면 안 된다 — 보기 항목 라벨 ㄱㄴㄷㄹ 은 **호환 자모**(U+3131~318E)라
    # 음절 검사에 안 걸려 'ㄷ. y=4x^2+1 • ㄹ. y=-(x+1)^2-3' 세그먼트가 통째 평문
    # 잔존했다(장산중 #13 보기 박스, 2026-06-11). 자모 라벨 = 한글 혼합 텍스트.
    # \u26a0\ufe0f \ubd88\ub9bf(\u2022)\uc73c\ub85c \ub098\ub25c \ubc15\uc2a4 \ub0b4\uc6a9\uc740 \ud55c\uae00\uc774 \uc5c6\uc5b4\ub3c4(\uc21c\uc218 ASCII \ud480\uc774\uacfc\uc815 \uc0c1\uc790) \ubd84\ub9ac\ud55c\ub2e4 \u2014
    # '<\uc0c1\uc790> 0.3x-3=\u2026 \u2193 \u2022 3x-30=-2x-25 \u2193 \u2022 \u2026' \ub458\uc9f8 \uc904\ubd80\ud130\uac00 \ud1b5\uc9f8 \ud3c9\ubb38\uc73c\ub85c \ub0a8\uc544 \uc218\uc2dd
    # \uac1d\uccb4\ud654 \uc548 \ub418\ub358 \uac83(\uccad\uad6c\uc911 #3 \uc77c\ucc28\ubc29\uc815\uc2dd \ud480\uc774\uacfc\uc815 \uc0c1\uc790, 2026-06-11). \ubd88\ub9bf/\ud654\uc0b4\ud45c\ub294 \ud14d\uc2a4\ud2b8
    # \uad6c\ubd84\uc790\ub85c \ub0a8\uace0 \uac01 \uc218\uc2dd\uc740 \uac1d\uccb4\ud654 + _merge_operator_split_equations \uac00 '=-' \ubd84\ub9ac\ub97c \uc7ac\ubcd1\ud569.
    # \u26a0\ufe0f \ucca8\uc790(``A^2``\u00b7``x_1``)\ub3c4 \ubd84\ub9ac \ub300\uc0c1 \u2014 \ud55c\uae00\u00b7\ubd88\ub9bf \uc5c6\ub294 \uc21c\uc218 ASCII \ub77c\ub3c4 \uc704\u00b7\uc544\ub798\ucca8\uc790\uac00 \uc788\uc73c\uba74
    # \uc218\uc2dd\uc774\ub2e4. OCR \uc774 \uc18c\ubb38\ud56d \ud56d\ubaa9\uc744 ``\u3262 A^2`` (caret \ud45c\uae30, \ubcc4\ub3c4 text \ube14\ub85d)\ub85c \uc8fc\uba74 \uc704 \uac00\ub4dc\uac00
    # \ud1b5\uc9f8 \ud3c9\ubb38\ud654\ud574 ``A^2`` \uc758 ``^`` \uac00 \uadf8\ub300\ub85c \ub178\ucd9c\ub410\ub2e4(\ub300\uac74\uace0 #19 \u3262\u3263\u3264, 2026-06-13). \uac19\uc740 \uc2dd\uc774
    # ``\cdots`` \ub4f1 LaTeX \uc640 \uc11e\uc774\uba74(SUB2 ``A+A^2+\cdots``) latex \uacbd\ub85c\ub77c \uc815\uc0c1\uc774\uc5c8\ub2e4 \u2014 caret \ub2e8\ub3c5\ub9cc \ubc1c\ud654.
    if (not re.search(r'[\u2022\u00b7\u25aa\u25e6]', text)
            and not re.search(r'[\uac00-\ud7a3\u3131-\u318e]', text)
            and not re.search(r'[A-Za-z0-9][_^]', text)):
        return [ContentBlock(type=ContentType.TEXT, value=text)]

    # 수식 후보가 없으면 분리 불필요
    if not re.search(r'[a-zA-Z0-9]', text):
        return [ContentBlock(type=ContentType.TEXT, value=text)]

    blocks: list[ContentBlock] = []
    last_end = 0

    for m in _MATH_EXPR_RE.finditer(text):
        expr = m.group(1).strip()
        # 긴 매치는 영문 단어일 수 있어 거른다(예: 우연히 이어진 변수열) — 단 **수학
        # 연산자·괄호가 있으면** 명백한 수식이므로 길이와 무관하게 살린다(사용자 2026-06-09:
        # OCR 이 유니코드 부등호로 준 ``P(X ≤ 15) ≤ P(Y ≥ 30)``(21자)가 길이필터에 걸려
        # 평문 처리되던 #20 (가)). 연산자·괄호 없는 순수 토큰만 길이로 거른다.
        if len(expr) > 20 and not re.search(r'[=<>≤≥≠+\-×÷^_()]', expr):
            continue
        # 한글이 포함된 매치는 건너뜀
        if re.search(r'[\uac00-\ud7a3]', expr):
            continue
        # 단독 숫자도 모두 수식화 (사용자 요구: 숫자는 전부 수식)

        before = text[last_end:m.start()]
        # 선행 단항부호 흡수 — "ㄷ. -5x+6=6-5x" 의 '-' 가 평문(정자 하이픈)으로 수식 밖에
        # 떨어지던 것(경구중 #5 ㄷ·ㅁ·#13 ㄹ, 2026-06-11). 능인고 R2·월암중 W4(LaTeX 경로
        # _split_latex_commands)의 ASCII 경로판. 단항 판정: 부호 앞이 라벨점·불릿·한글·여는
        # 괄호·시작이면 흡수. 직전 블록이 수식이고 사이가 부호뿐이면 **이항**(f(x) - 5x) —
        # 흡수하지 않고 _merge_operator_split_equations 의 한 수식 병합에 맡긴다.
        sign_m = re.search(r'([+\-])(\s*)$', before)
        if sign_m:
            sign_tail = before[:sign_m.start()].rstrip()
            prev_is_eq = (not sign_tail and blocks
                          and blocks[-1].type == ContentType.EQUATION)
            if not prev_is_eq and (not sign_tail or re.search(
                    r'[.•·:,;([{가-힣ㄱ-ㆎ]$', sign_tail)):
                expr = sign_m.group(1) + expr
                before = before[:sign_m.start()]
        if before:
            blocks.append(ContentBlock(type=ContentType.TEXT, value=before))
        blocks.append(ContentBlock(type=ContentType.EQUATION, value=expr))
        last_end = m.end()

    after = text[last_end:]
    if after:
        blocks.append(ContentBlock(type=ContentType.TEXT, value=after))

    # 블록이 하나여도 **수식이면 유지** — 텍스트 전체가 한 수식(선택지 ``(f^{-1})^{-1}=f`` 등
    # 순수 ASCII 수식)일 때 len>1 조건이 평문으로 강등시켜 ``^{-1}`` 캐럿이 literal 노출됐다
    # (매천고 수하 #4 선택지, 2026-06-14). _split_latex_commands 의 동일 가드(2026-06-10 성광중)와 통일.
    if len(blocks) > 1 or (blocks and blocks[0].type == ContentType.EQUATION):
        return blocks
    return [ContentBlock(type=ContentType.TEXT, value=text)]


def _normalize_math_delims(text: str) -> str:
    """LaTeX 수식 구분자 ``\\(...\\)``(인라인)·``\\[...\\]``(디스플레이)를 ``$...$``로 변환.

    OCR이 인라인 수식을 ``$`` 대신 ``\\(`` ``\\)`` 로 감싸 줄 때 그대로 출력되던
    문제(조건 박스의 ``\\(A = 2x^2y\\)`` 등이 raw로 찍힘)를 막는다. 변환 후엔 기존
    ``$...$`` 분리 경로가 수식으로 처리한다.
    """
    if "\\(" in text or "\\)" in text:
        text = text.replace("\\(", "$").replace("\\)", "$")
    if "\\[" in text or "\\]" in text:
        text = text.replace("\\[", "$").replace("\\]", "$")
    return text


def _split_inline_latex(text: str) -> list[ContentBlock]:
    """텍스트에서 $...$ 인라인 LaTeX를 분리하여 ContentBlock 리스트로 반환."""
    blocks: list[ContentBlock] = []
    last_end = 0

    for m in _INLINE_LATEX_RE.finditer(text):
        # 수식 앞 텍스트
        before = text[last_end:m.start()]
        if before:
            blocks.append(ContentBlock(type=ContentType.TEXT, value=before))
        # 수식
        latex = m.group(1).strip()
        if latex:
            blocks.append(ContentBlock(type=ContentType.EQUATION, value=latex))
        last_end = m.end()

    # 마지막 텍스트
    after = text[last_end:]
    if after:
        blocks.append(ContentBlock(type=ContentType.TEXT, value=after))

    return blocks if blocks else [ContentBlock(type=ContentType.TEXT, value=text)]


# __밑줄__ 마크업 감지 패턴
_UNDERLINE_RE = re.compile(r"__(.+?)__")
# 한글 포함 여부 — __강조__ 가 한글이면 밑줄(옳지 않은), 라틴/수식이면 OCR 오인 → 수식 복원.
_HANGUL_RE = re.compile(r"[가-힣]")


def _split_underline_markup(text: str) -> list[ContentBlock]:
    """텍스트에서 __밑줄__ 마크업을 분리하여 ContentBlock 리스트로 반환.

    예: "옳지 __않은__ 것은?"
    → text("옳지 ") + text("않은", underline=True) + text(" 것은?")

    단 ``__xy__`` 처럼 **한글 없는 라틴/수식 토큰**을 감싼 이중 밑줄은 인쇄 시험지에 존재할
    수 없는 OCR 오인(손글씨 변수 등)이므로 밑줄이 아니라 **수식 객체로 복원**한다 — 발문에
    ``__xy__`` 같은 literal 이중밑줄이 찍히던 문제(사용자 2026-06-08). 한글 강조는 밑줄 유지.
    """
    blocks: list[ContentBlock] = []
    last_end = 0

    for m in _UNDERLINE_RE.finditer(text):
        before = text[last_end:m.start()]
        if before:
            blocks.append(ContentBlock(type=ContentType.TEXT, value=before))
        inner = m.group(1)
        if inner:
            is_math = (not _HANGUL_RE.search(inner)) and bool(re.search(r"[A-Za-z0-9]", inner))
            if is_math:
                blocks.append(ContentBlock(type=ContentType.EQUATION, value=inner.strip()))
            else:
                blocks.append(
                    ContentBlock(type=ContentType.TEXT, value=inner, underline=True)
                )
        last_end = m.end()

    after = text[last_end:]
    if after:
        blocks.append(ContentBlock(type=ContentType.TEXT, value=after))

    return blocks if blocks else [ContentBlock(type=ContentType.TEXT, value=text)]


# \begin{env}…\end{env}(cases 등 LaTeX 환경)는 **통째 한 수식 원자**로 다룬다 — 인라인
# 분리기(_LATEX_CMD_RE)가 \begin/\end 을 몰라 cases 안 개행 ``\\ ``(백슬래시+공백)을 간격
# 명령으로 오인, begin·cases 가 영단어처럼 쪼개져 박스 안 연립이 "₩ begin{ { }" literal 로
# 깨졌다(월암중 #5·#19 + 매천중 #6 동일 — 2026-06-11).
_LATEX_ENV_RE = re.compile(r"\\begin\s*\{(\w+)\}.*?\\end\s*\{\1\}", re.DOTALL)

# 좌측 첨자 prefix ``{}_{n}`` / ``{}^{n}`` — 조합·순열 ``{}_{n}\mathrm{C}_{r}``(ₙCᵣ·ₙPᵣ)의
# 빈 그룹+첨자. 명령(\mathrm) 직전에 붙으면 수식 영역에 흡수해야 한다. 안 하면 ``{}_{`` 가
# 평문 leak + 첨자 내용(``13``)만 EQ 로 떨어져 ``{}_{13}`` 가 literal 노출(강동고 수하 #12
# 상자, 2026-06-14). 끝 ``$`` 로 latex_start 직전을 정확히 매칭.
_LEFT_SCRIPT_PREFIX_RE = re.compile(r"\{\}\s*[_^]\s*\{[^{}]*\}\s*$")

# ── LaTeX 명령어 감지 패턴 ──
_LATEX_CMD_RE = re.compile(
    r'\\[!,;: ]'                         # 간격 명령(\! \, \; \: \ ) — P\!\left 의 \! 가
    r'|\\[{}]'                           # 집합 기호 \{ \} (집합·명제 set-builder) — 빠지면 \{ 가
                                         # 평문 ₩{ 로 새고 set 식이 ``Y`` ``=\{`` ``y`` 로 쪼개짐
                                         # (강북고 수하 #14 ``Y=\{y|1\le y\le 8\}``, 2026-06-14)
    r'|\\(?:sqrt|d?frac|tfrac|sum|prod|int|oint|lim|'   # text 로 새 "P₩!" 되는 것 방지(#12)
    r'times|div|pm|mp|cdot|cdots|ldots|quad|qquad|'
    r'left|right|leq|geq|neq|infty|'
    r'alpha|beta|gamma|delta|epsilon|zeta|eta|theta|iota|kappa|'
    r'lambda|mu|nu|xi|pi|rho|sigma|tau|phi|chi|psi|omega|'
    r'partial|nabla|forall|exists|therefore|because|'   # ∴/∵ — 빠지면 literal ₩therefore(장산중 #5)
    r'dot|ddot|hat|bar|vec|tilde|overline|underline|'
    r'log|ln|sin|cos|tan|sec|csc|cot|'
    r'square|circ|triangle|angle|perp|parallel|'
    r'cup|cap|subset|supset|in|notin|'
    # 화살표(명제 ⟺/⟹·사상): latex_to_hwpeq 엔 매핑(LRARROW 등) 있으나 여기 없어 ``\Leftrightarrow``
    # 가 TEXT ``\``(₩ 누수) + bare EQ ``Leftrightarrow``(literal)로 쪼개졌다(매천고 수하 #4
    # 선택지, 2026-06-14). 긴 것 먼저(leftmost 매칭). iff/implies 도 포함.
    r'Leftrightarrow|Rightarrow|Leftarrow|'
    r'longleftrightarrow|longrightarrow|longleftarrow|'
    r'leftrightarrow|rightarrow|leftarrow|mapsto|iff|implies|'
    r'mathbb|mathrm|mathbf|mathit|text|boxed|fbox|overarc|'
    r'le|ge|ne|to|sim)'                  # 짧은꼴(\le \ge \ne …) — OCR 이 \leq 대신 자주 씀.
    # 경계 = **ASCII 영문자만 아니면 됨**. 기존 `(?:\b|(?=[{^_(\[\d]))` 는 한글이 \w 라
    # ``\pi일``(명령 직후 한글)에서 \b 실패 → 명령 미인식 → ASCII 경로가 ``\`` 를 평문
    # literal(₩)로 흘렸다(대구고 수1 #11 ``0<x<2\pi일 때``, 2026-06-12). 한글·공백·문장부호
    # 전부 경계가 맞고, ``\pix`` 같은 더 긴 영문 명령의 접두 오인만 막으면 된다.
    r'(?![a-zA-Z])'
)

# 배점 텍스트 패턴 (예: [3점], [4.5점], [총 7점], [7점, 부분점수 있음]) — 캡처 정규식
# (_parse_question)과 동치 유지. ``점`` 뒤 ``, 부분점수 있음`` 같은 부가 문구도 함께 제거
# (서답형 배점, 2026-06-10 중앙고 — 본문 배점 텍스트 + score 중복 출력 방지).
# 배점 ``[N점]`` — 대괄호가 표준이나 OCR/원본이 소괄호 ``(N점)`` 으로 줄 때도 제거해야
# score 필드와 중복 렌더되지 않는다(경명여중 중2 #20·#21 ``서술하시오. (7점)`` + 우측정렬
# ``[7점]`` 이중 출력, 2026-06-11). 여는 ``[/(`` · 닫는 ``]/)`` 를 각각 허용(혼용도 방어).
_SCORE_TEXT_RE = re.compile(r'\s*[\[(]\s*(?:총\s*)?\d+(?:\.\d+)?\s*점\s*(?:,[^\])]*)?[\])]\s*')

# 보기/조건/상자 박스 머리 마커(원시 텍스트 시작). 자기완결 박스(마커+항목이 한 raw
# 블록) 판정과 그 뒤 발문 연속 분리에 쓴다.
# ``<보기>에서``(조사 직결)·``<보기> 중/중에서/에서 ~``(참조어)는 발문의 **인라인 참조**라 박스
# 머리가 아니다 — 발문 선두 "<보기> 중 일차함수…"가 박스로 오인돼 발문이 박스에 갇히고
# 진짜 보기 항목이 평문으로 풀렸다(월암중 #11·상원중 #16, 2026-06-11). ``<상자>`` 는 항상 박스.
_RAW_BOX_MARK_RE = re.compile(
    r"^\s*(?:<\s*상자\s*>"
    r"|(?:<\s*(?:조건|보기)\s*>|\[\s*(?:조건|보기)\s*\])(?![가-힣])(?!\s+(?:중에서|에서|중)(?=[\s,.?]|$)))")
# 항목 라벨 단독(ㄱ./ㄴ./…, (가)/(나)/…, 1)/2)/…) — 박스 머리 뒤가 이것뿐이면 자기완결 아님.
_BARE_ITEM_LABEL_RE = re.compile(
    r"^(?:[ㄱ-ㅎ]\s*\.?|[（(]\s*[가-힣]\s*[)）]|\d+\s*[.)])\s*$")
# 다음 raw 블록이 박스 항목으로 **시작**하는지(라벨/불릿) — 박스 연속 판정(#14 변종).
_NEXT_ITEM_START_RE = re.compile(
    r"^\s*(?:[•·▪◦○ㅇ]\s*)?(?:[ㄱ-ㅎ]\s*\.|[（(]\s*[가-힣]\s*[)）])")
# 마커 블록 rest 가 항목 라벨로 **시작**하는지(다사중 #13 ``ㄱ. 점``) — eq 연속 가드 게이트.
_ITEM_LEAD_RE = re.compile(r"^(?:[ㄱ-ㅎ]\s*\.|[（(]\s*[가-힣]\s*[)）])")
# 이후 text 블록 **안**의 후속 항목 라벨(``• ㄴ.``·``(나)``) — 박스가 여러 raw 로 쪼개진 신호.
_INNER_ITEM_LABEL_RE = re.compile(r"[•·▪◦○〇ㅇ]\s*(?:[ㄱ-ㅎ]\s*\.|[（(]\s*[가-힣]\s*[)）])")


def _parse_raw_blocks(raws: list[dict]) -> list[ContentBlock]:
    """raw OCR 블록 dict 리스트를 ContentBlock 리스트로(인라인 수식 분리 포함)."""
    out: list[ContentBlock] = []
    for bd in raws:
        result = _parse_content_block(bd)
        if isinstance(result, list):
            out.extend(result)
        elif result:
            out.append(result)
    return out


def _finalize_contents(blocks: list[ContentBlock]) -> list[ContentBlock]:
    """문제 본문 후처리 파이프라인(분리·병합·이탤릭·로만·배점제거)."""
    blocks = _split_trailing_domain(blocks)        # 수식 끝 정의역 (x=0,1,⋯) 분리
    blocks = _split_comma_equations(blocks)         # 쉼표 구분 독립 수식 분리
    blocks = _merge_operator_split_equations(blocks)  # eq·연산자·eq 병합
    blocks = _merge_text_eq_fragments(blocks)       # text(꼬리부등식)·eq·text(머리부등식) 병합
    blocks = _merge_degree_temp_units(blocks)       # 온도 단위 °C/°F (EQ+TEXT"°"+EQ"C") 한 수식 병합
    blocks = _merge_paren_range(blocks)             # 점화식 뒤 범위 (n=1,2,3⋯) 를 ~공백으로 병합
    # 배점 [N점] 제거를 **기하 판정 앞에** 둔다 — 점수의 "점"이 기하 키워드 "점"(point)과
    # 충돌해 비기하 문제를 기하로 오인(체스 #15 A·B 로만 잔존, 2026-06-09)하던 것 방지.
    blocks = _strip_score_text(blocks)              # 잔여 [N점] 제거(기하판정 오염 방지)
    blocks = _italicize_stat_operators(blocks)      # 확통 연산자 \mathrm 벗겨 이탤릭
    blocks = _romanize_point_names(blocks)          # 기하 점/선/면 이름 로만체
    blocks = _italicize_nongeo_single_letters(blocks)  # 비기하 단일대문자 \mathrm 벗겨 이탤릭
    blocks = _romanize_angle_letters(blocks)        # 각(angle) 단일대문자 로만체(삼각함수·°·∠)
    blocks = _romanize_context_units(blocks)        # '단위는 g' 등 문맥상 단위 수식 로만화
    blocks = _space_hangul_before_eq(blocks)        # 한글 끝 TEXT + EQ 사이 공백(확률을p_1 → 확률을 p_1)
    blocks = _rstrip_last_text(blocks)              # 끝 TEXT 의 꼬리 공백 제거(점수 앞 이중공백 방지)
    return blocks


# 한글로 끝나는 텍스트 바로 뒤에 수식이 붙으면(OCR 이 꼬리 공백을 안 줌) "확률을p_1" 처럼
# 한글과 수식이 붙는다(사용자 2026-06-09 #19). 수식은 **새 기호**이므로 앞에 공백을 넣는다.
# (수식 뒤 한글은 조사 "p_5이라"가 정상이라 그쪽은 건드리지 않는다 — 비대칭.)
_HANGUL_TAIL_RE = re.compile(r"[가-힣]$")
# 서수 접두사 '제'(第)+숫자 = 붙여쓰는 구성(제4사분면·제3항). 위 공백 규칙의 예외.
# 단 '문제3'·'과제3'(제가 단어의 끝 음절)은 띄어야 하므로, **앞이 한글이 아닌 독립 '제'**
# 뒤에 순수 숫자 수식이 올 때만 공백을 막는다(사용자 2026-06-09 잔여 띄어쓰기 케이스).
_ORDINAL_JE_RE = re.compile(r"(?:^|[^가-힣])제$")
_PURE_NUM_RE = re.compile(r"^\d+$")


def _space_hangul_before_eq(blocks: list[ContentBlock]) -> list[ContentBlock]:
    """``TEXT(…한글) + EQ`` 경계에 공백 1칸 삽입(이미 공백/부호로 끝나면 안 함).

    예외: 독립 서수 접두사 '제' + 순수 숫자(제4사분면)는 붙여쓴다.
    """
    eq_types = (ContentType.EQUATION, ContentType.EQUATION_BLOCK)
    for i in range(len(blocks) - 1):
        b, nxt = blocks[i], blocks[i + 1]
        if (b.type == ContentType.TEXT and nxt.type in eq_types
                and b.value and _HANGUL_TAIL_RE.search(b.value)):
            if (_ORDINAL_JE_RE.search(b.value)
                    and _PURE_NUM_RE.match((nxt.value or "").strip())):
                continue  # 제4사분면: 접두사 '제'+숫자는 붙여쓰기
            b.value = b.value + " "
    return blocks


# 문맥상 '단위' 로 명시된 직후의 단위 기호(수식). 모평균 m·변수 t 를 무조건 로만화하면 안 되므로
# (사용자 2026-06-08) **앞 텍스트가 '단위…' 로 끝날 때만** 단위로 확정해 로만화한다(사용자
# 2026-06-09: "단위는 g" 의 g 가 이탤릭 — 문맥 읽으면 단위 판별 가능, 단 모평균 m 은 제외).
_CTX_UNIT_SET = {"g", "kg", "mg", "cm", "mm", "km", "m", "L", "mL", "dL", "kL", "min", "s", "h", "t", "℃"}
_UNIT_CTX_RE = re.compile(r"단위[가는은를로이]*\s*$")


def _romanize_context_units(blocks: list[ContentBlock]) -> list[ContentBlock]:
    """'단위는 g' 처럼 앞 텍스트가 '단위…'로 끝나는 직후의 단위 수식을 로만체(``\\mathrm``)로.

    HWP 수식의 라틴 1글자는 기본 이탤릭이라 단위 g·m 도 기운다. 모평균 m·변수 t 오로만화를
    피하려 **문맥이 단위임을 명시할 때만** 처리한다(사용자 2026-06-09). 숫자+단위(20g)는
    이미 ``_romanize_units`` 가 처리하므로 여기선 문맥 기반 단독 단위만 다룬다.
    """
    eq_types = (ContentType.EQUATION, ContentType.EQUATION_BLOCK)
    for i, b in enumerate(blocks):
        if b.type not in eq_types:
            continue
        u = (b.value or "").strip()
        if u not in _CTX_UNIT_SET or u.startswith("\\mathrm"):
            continue
        prev_txt = next((blocks[j].value for j in range(i - 1, -1, -1)
                         if blocks[j].type == ContentType.TEXT and (blocks[j].value or "").strip()), None)
        if prev_txt and _UNIT_CTX_RE.search(prev_txt.rstrip()):
            b.value = "\\mathrm{" + u + "}"
    return blocks


def _rstrip_last_text(blocks: list[ContentBlock]) -> list[ContentBlock]:
    """마지막 TEXT 블록의 꼬리 공백을 제거한다.

    OCR 이 발문 끝 텍스트에 꼬리 공백을 남기면("…작성하시오. "), 렌더러가 배점을 발문 끝
    인라인(" [N점]")으로 붙일 때 공백이 둘이 된다(사용자 2026-06-09: 서답형 2·3 [7점] 앞 두
    칸). 문제(또는 박스 뒤 발문 연속) **끝** 텍스트의 꼬리 공백은 의미가 없으므로 제거한다.
    """
    if blocks and blocks[-1].type == ContentType.TEXT and (blocks[-1].value or ""):
        v = blocks[-1].value.rstrip()
        if v:
            blocks[-1].value = v
        else:
            blocks = blocks[:-1]
    return blocks


def _raw_box_end(raws: list[dict]) -> int | None:
    """자기완결 박스(<조건>/<보기>/<상자> + 항목이 한 raw 텍스트 블록) **뒤에** 발문이
    더 이어지면 그 발문 연속이 시작되는 raw 인덱스를 돌려준다(없으면 None).

    박스 마커를 떼고도 같은 블록에 **내용이 남으면**(=항목이 그 블록 안=자기완결) 박스는
    그 한 raw 블록까지. 그 뒤 raw 블록이 있으면 발문 연속(#18 "m이 자연수일 때 …",
    #20 "P(Y≤29)의 값을 …"). 마커만 있는 라벨-단독 머리(뒤 raw 가 항목)는 분리 안 함.

    단 마커 뒤가 **항목 라벨 하나뿐**(``ㄱ.``·``(가)``)이면 자기완결이 아니다 — OCR 이 보기
    박스를 ``<보기> ㄱ.`` + (별도)수식 + ``• ㄴ. …`` 처럼 **여러 raw 블록으로 쪼개** 줄 때,
    ``ㄱ.`` 만 박스로 보고 ㄴㄷㄹ 를 발문 연속으로 떼어 **박스 밖**으로 내보내던 버그
    (학남고 #14, 2026-06-09). 라벨만 남으면 박스가 다음 블록으로 이어지는 것 → 분리 안 함.

    post 가 그림(image/그림자리 안내문구)뿐이어도 분리는 그대로 한다 — 노트가 박스 밖
    (post 경로)에 렌더돼야 하므로. 단 그런 post 는 발문 연속이 아니라서 **배점은 미루지
    않는다**(렌더러 `_post_has_stem` 게이트, 경일중 #19 [6점], 2026-06-11).
    """
    for i, bd in enumerate(raws):
        if bd.get("type") == "text":
            v = (bd.get("value") or "")
            m = _RAW_BOX_MARK_RE.search(v)
            if m:
                rest = v[m.end():].strip()
                if rest and not _BARE_ITEM_LABEL_RE.match(rest) and i + 1 < len(raws):
                    # #14 변종 방어: 마커 블록에 첫 항목이 통째로 있어도(``<보기> ㄱ. f(x)=x``)
                    # **다음 raw 가 항목 라벨/불릿으로 시작**하면(``ㄴ. …``) 박스가 이어지는
                    # 것 — 발문 연속으로 떼면 ㄴㄷㄹ 가 박스 밖으로 샌다(감사 2026-06-10).
                    nxt = raws[i + 1]
                    if (nxt.get("type") == "text"
                            and _NEXT_ITEM_START_RE.match(nxt.get("value") or "")):
                        return None
                    # 다사중 #13 변종(2026-06-12): 첫 항목이 **인라인 수식 분리**로 쪼개져
                    # 마커 블록이 ``<보기> ㄱ. 점 `` 처럼 미완으로 끝나고 다음 raw 가
                    # equation((6,3))인 경우 — 이후 text 에 **후속 항목 라벨**(``• ㄴ.``)이
                    # 보이면 박스 연속(분리 금지). post 가 eq+조사 발문 연속(학남고 #20
                    # ``P(Y≤29)``+"의 값을…" — 라벨 없음)은 그대로 분리(무회귀).
                    if (_ITEM_LEAD_RE.match(rest) and nxt.get("type") == "equation"):
                        for j in range(i + 2, min(i + 8, len(raws))):
                            if raws[j].get("type") != "text":
                                continue
                            if _INNER_ITEM_LABEL_RE.search(raws[j].get("value") or ""):
                                return None
                    return i + 1
                return None
    return None


def _tag_box_run(blocks: list[ContentBlock]) -> None:
    """head 안의 박스 마커 블록부터 끝까지 box_member=True (발문 연속은 이미 분리됨)."""
    started = False
    for b in blocks:
        if not started and b.type == ContentType.TEXT and _RAW_BOX_MARK_RE.search(b.value or ""):
            started = True
        if started:
            b.box_member = True


def _is_eq_lead_char(text: str, pos: int) -> bool:
    """``pos`` 바로 앞 글자가 수식 선두로 끌어올 영숫자/소수점인지(수식 직전 식별자 흡수용).

    영문·숫자는 항상 포함. ``.`` 은 **숫자 사이의 소수점**(앞·뒤가 모두 숫자)일 때만 — 안 그러면
    ``0.3x`` 의 ``0.`` 가 수식에서 떨어져 ``0 . 3x`` 로 간격이 벌어진다(청구중 #3 풀이상자
    ``0.3x-3=-\\frac…``, 2026-06-11). 문장 끝 마침표는 앞뒤 숫자 조건에 안 걸려 안전.
    """
    c = text[pos - 1]
    if "a" <= c.lower() <= "z" or c.isdigit():
        return True
    # 첨자 캐럿/언더스코어: ``x^2-\frac…`` 의 ``^`` 도 끌어와야 베이스(x)까지 수식에
    # 포함된다 — ``2`` 만 흡수하고 ``^`` 에서 멈추면 ``x^`` 가 고아 수식으로 잘려
    # ``x  2-…``(베이스라인 풀사이즈 2) 로 렌더됐다(새본리중 #7 과정상자, 2026-06-12).
    # 앞이 영숫자/닫는중괄호일 때만(텍스트 속 단독 ^ 보호).
    if c in "^_" and pos >= 2 and (text[pos - 2].isalnum() or text[pos - 2] == "}"):
        return True
    return (c == "." and pos >= 2 and text[pos - 2].isdigit()
            and pos < len(text) and text[pos].isdigit())


def _split_latex_commands(text: str) -> list[ContentBlock]:
    """텍스트에서 LaTeX 명령어를 감지하여 text + equation 블록으로 분리.

    예: "ㄱ. \\sqrt{2}+\\sqrt{2}" → text("ㄱ. ") + eq("\\sqrt{2}+\\sqrt{2}")
    예: "\\sqrt{24} \\div \\sqrt{3} 의 값은" → eq(...) + text(" 의 값은")
    """
    # 선두 박스 마커 보호 — 마커의 닫는 > 가 선행 연산자 흡수에 끌려가 수식 ``> \frac…``
    # 으로 새고 마커가 깨지던 것(신명여중 #7, _split_box_marker_prefix docstring 참고).
    _boxed = _split_box_marker_prefix(text, _split_latex_commands)
    if _boxed is not None:
        return _boxed

    # \begin{cases}…\end{cases} 같은 LaTeX 환경은 가장 먼저 통째 수식 원자로 떼어낸다
    # (아래 명령어 분리가 \begin 을 몰라 cases 를 산산조각 냄 — _LATEX_ENV_RE 주석 참고).
    env = _LATEX_ENV_RE.search(text)
    if env:
        blocks: list[ContentBlock] = []
        before, after = text[:env.start()], text[env.end():]
        # env 직전에 공백 없이 붙은 식별자(행렬곱 ``A\begin{pmatrix}…`` 의 A)는 수식 원자에
        # 포함 — 안 하면 ``, A`` 같은 한글 없는 TEXT 조각으로 남아 mixed 분리기의 한글 가드에
        # 걸려 평문(정자) 렌더된다(상원고 공수1 #18 둘째 식 A 정자 — 첫째 A 는 앞 한글 덕에
        # EQ 승격되는 비대칭). 명령 경로의 식별자 흡수와 동일 원칙.
        _lead = len(before)
        while _lead > 0 and _is_eq_lead_char(before, _lead):
            _lead -= 1
        _lead_id = before[_lead:]
        if _lead_id:
            before = before[:_lead]
        if before.strip():
            blocks.extend(_split_latex_commands(before))
        elif before:
            blocks.append(ContentBlock(type=ContentType.TEXT, value=before))
        blocks.append(ContentBlock(type=ContentType.EQUATION, value=_lead_id + env.group(0)))
        if after.strip():
            blocks.extend(_split_latex_commands(after))   # 둘째 cases 도 여기서 원자 처리
        elif after:
            blocks.append(ContentBlock(type=ContentType.TEXT, value=after))
        return blocks
    first_match = _LATEX_CMD_RE.search(text)
    if not first_match:
        # LaTeX 명령은 없어도 ASCII 수식(f(20)=g(30) 등)이 섞여 있을 수 있다 — 박스
        # "(가) … \leq … • (나) f(20) = g(30)" 의 (나)처럼 앞 항목이 \leq 로 수식화돼
        # _split_latex_commands 재귀로 넘어온 뒤 백슬래시가 없어 평문 처리되던 것(#20,
        # 2026-06-09). _split_mixed_text_equation 은 한글+ASCII수식 혼재일 때만 분리하고
        # 아니면 그대로 평문 1블록을 돌려주므로 안전.
        return _split_mixed_text_equation(text)

    latex_start = first_match.start()
    # 수식 직전에 **공백 없이 붙은 식별자**(P, f, X, 숫자 등)는 수식의 일부 → 수식 영역에
    # 포함시킨다. 안 그러면 "P\!\left(…" 의 P 가 텍스트로 떨어지고 \! 가 literal "P₩!" 로
    # 샌다(학남고 #12, 2026-06-08). 한글은 텍스트이므로 ASCII 영숫자만 끌어온다.
    while latex_start > 0 and _is_eq_lead_char(text, latex_start):
        latex_start -= 1
    # 수식 **앞에 붙은 선행 연산자**(= - + < > ≤ ≥ …)도 수식에 포함 — "= - \frac{…}" 의
    # ``= -`` 가 텍스트로 떨어져 음수부호가 수식 밖에 따로(큰 간격) 렌더되던 것(#12 9째줄,
    # 2026-06-10). 연산자와 그 사이 공백만 끌어오고, 한글/불릿을 만나면 멈춘다.
    _op = latex_start
    while _op > 0 and text[_op - 1] in " \t":   # 명령어 바로 앞 공백 먼저 건너뛰기
        _op -= 1
    _seen_op = False
    while _op > 0:
        _c = text[_op - 1]
        if _c in _EQ_OP_CHARS:
            _op -= 1
            _seen_op = True
        elif _c in " \t":
            _op -= 1            # 연산자 사이 공백 흡수
        else:
            break
    if _seen_op:
        latex_start = _op
        # 연산자 앞에 공백 없이 붙은 식별자(``y=-\frac…`` 의 y)도 수식으로 — ``=-`` 만
        # 흡수하면 변수가 평문으로 떨어져 정자 렌더된다(월암중 #15 ㄷ, 2026-06-11).
        while latex_start > 0 and _is_eq_lead_char(text, latex_start):
            latex_start -= 1
    # 수식이 **관계/이항 연산자 명령**(\le \ge \times …)으로 시작하면 그 좌변(ASCII 식
    # 조각 ``4x-7``)도 수식이다 — 사이 공백 때문에 식별자/연산자 흡수가 멈춰 좌변이
    # 평문(정자)으로 떨어지던 것(대진고 공수1 #1 상자 ``4x-7 \le 7x-1 \le 3x+15``,
    # 2026-06-12). 한글·문장부호(.만으로는 식 아님)는 경계로 보호.
    if text[latex_start] == "\\" and _EQ_LEAD_OPCMD_RE.match(text, latex_start):
        _p2 = latex_start
        while _p2 > 0 and text[_p2 - 1] in " \t":
            _p2 -= 1
        _q2 = _p2
        while _q2 > 0:
            _c2 = text[_q2 - 1]
            if _c2.isascii() and (_c2.isalnum() or _c2 in "+-*/^_()."):
                _q2 -= 1
            else:
                break
        if _q2 < _p2 and re.search(r"[0-9a-zA-Z]", text[_q2:_p2]):
            latex_start = _q2
    # 함수꼴 괄호 안의 \leq(예 "P(X \leq 15)")는 **괄호 시작부터** 한 수식이어야 한다. \leq
    # 앞에 **안 닫힌 "("**(함수호출 괄호)가 있으면 그 "(" 와 앞 식별자(P)까지 수식에 포함한다.
    # (안 하면 "P(X" 가 P·(·X 로 쪼개진다 — #20 박스, 2026-06-09.)
    _pre = text[:latex_start]
    if _pre.count("(") > _pre.count(")"):
        _depth = 0
        for _j in range(len(_pre) - 1, -1, -1):
            if _pre[_j] == ")":
                _depth += 1
            elif _pre[_j] == "(":
                if _depth == 0:
                    # ⚠️ "(" 바로 뒤가 한글이면 단서/설명 괄호("(단, \overline{α}와 …)")다 —
                    # 함수호출 괄호가 아니므로 흡수하지 않는다. 흡수하면 아래 한글 경계의
                    # "(우변)" 보호(_b←여는괄호)와 맞물려 eq_end==latex_start(소비 0)가 되어
                    # _split_latex_commands 가 같은 문자열로 무한 재귀했다(상원고 공수1 #4
                    # 켤레복소수, 2026-06-12 — 중1 은 단서 괄호 안에 LaTeX 가 없어 잠복).
                    if _j + 1 < len(text) and "가" <= text[_j + 1] <= "힣":
                        break
                    _k = _j
                    while _k > 0 and _pre[_k - 1].isalnum():
                        _k -= 1
                    latex_start = _k
                    break
                _depth -= 1
    # 좌측 첨자 ``{}_{n}\mathrm{C}`` (조합 ₙCᵣ·순열 ₙPᵣ) — 빈 그룹+첨자 prefix 가 명령
    # 직전에 붙으면 수식에 흡수. 안 하면 ``{}_{`` 가 평문 leak + ``13`` 만 EQ 로 떨어져
    # ``{}_{13}`` literal 노출(강동고 수하 #12 박스, 2026-06-14). 식 중간(``={}_{13}\mathrm…``)
    # 의 같은 표기는 명령 run 내부라 이미 정상. ``$`` 앵커로 latex_start 직전만 매칭.
    _lsp = _LEFT_SCRIPT_PREFIX_RE.search(text[:latex_start])
    if _lsp:
        latex_start = _lsp.start()
    before = text[:latex_start]

    # LaTeX 영역 끝 찾기: 한글이 나오면 수식 종료
    rest = text[latex_start:]
    # \ubd88\ub9bf(\u2022)\u00b7(\uac00)(\ub098) \ubc15\uc2a4 \ub77c\ubca8\ub3c4 \uacbd\uacc4\ub85c \u2014 OCR \uc774 \leq \ub97c \uc4f0\uba74 \ubc15\uc2a4 "(\uac00) \u2026 \u2022 (\ub098) \u2026" \uc758
    # \ubd88\ub9bf\u00b7\ub77c\ubca8\uae4c\uc9c0 \ud55c \uc218\uc2dd\uc5d0 \ube68\ub824\ub4e4\uc5b4\uac00 \ubc15\uc2a4 \uc904\ubc14\uafc8\uc774 \uae68\uc84c\ub2e4(#20, 2026-06-09).
    _ends = []
    for _pat in (r'(?<=[^\\])\s+[\uac00-\ud7a3]',          # \uacf5\ubc31 \ub4a4 \ud55c\uae00(\uc870\uc0ac \ub4f1)
                 r'\s*[\u2022\u00b7\u25aa\u25e6]',          # \ubd88\ub9bf(\u2022\u00b7\u25aa\u25e6) \ubc15\uc2a4 \ud56d\ubaa9 \uad6c\ubd84\uc790
                 r'[\(\uff08]\s*[\uac00-\ud7a3]\s*[\)\uff09]'):  # (\uac00)(\ub098)\u2026 \ubc15\uc2a4 \ub77c\ubca8
        _mm = re.search(_pat, rest)
        if _mm:
            _ends.append(_mm.start())
    # 한글이 **중괄호 밖(depth 0)** 에서 나오면 수식 종료(공백 없어도) — ``2이므로``·``{k}이다``
    # 처럼 수·닫는중괄호 뒤 한글이 붙어도 끊는다. ``\boxed{가}``·``\text{가}``(중괄호 안 한글)
    # 은 depth>0 이라 보호된다(상인고 수1 #12 ``k \geq 2이므로`` 누수, 2026-06-10).
    _depth = 0
    for _i, _ch in enumerate(rest):
        if _ch == "{":
            _depth += 1
        elif _ch == "}":
            _depth = _depth - 1 if _depth > 0 else 0
        elif (_depth == 0 and _ch == " " and rest[_i:_i + 2] == "  "
              and rest[:_i].strip() and rest[_i:].strip()):
            # 깊이 0 의 2칸+ 공백 = 나란히 놓인 **별개 수식의 경계** — 박스 안 등식 2개가
            # 한 수식으로 합쳐져 "3^{11}4^x" 로 붙던 것(월암중 #6, 2026-06-11). LaTeX 에서
            # 연속 2칸 공백은 의도적 나열 구분일 때뿐이라 안전하다.
            _ends.append(_i)
            break
        elif _depth == 0 and "가" <= _ch <= "힣":
            _b = _i
            # 한글 바로 앞의 여는 괄호(+공백)는 한글 쪽(텍스트)으로 — "(우변)" 이 수식에
            # "(" 만 끼고 "우변)" 이 떨어져 나가지 않게.
            _j = _i - 1
            while _j >= 0 and rest[_j] in " \t":
                _j -= 1
            if _j >= 0 and rest[_j] in "(（":
                _b = _j
            _ends.append(_b)
            break
    if _ends:
        eq_end = latex_start + min(_ends)
        eq_text = text[latex_start:eq_end].strip()
        after_text = text[eq_end:]
        # 무한재귀 방어: 수식이 비고 잔여가 원문 그대로면(소비 0) 분리 불가 — 평문 유지.
        # (위 단서 괄호 가드로 정상 경로에선 안 오지만, 미지의 경계 조합 크래시를 차단.)
        if not eq_text and not before.strip() and after_text == text:
            return [ContentBlock(type=ContentType.TEXT, value=text)]
    else:
        eq_text = rest.strip()
        after_text = ""

    blocks: list[ContentBlock] = []
    if before.strip():
        # 한글 없는 순수 ASCII 수식 조각(거듭제곱 ``4^x`` 등)은 통째 수식으로 — 더블스페이스
        # 경계 분리 뒤 다음 수식의 머리가 평문으로 남던 것(월암중 #6 둘째 등식, 2026-06-11).
        # ⚠️ 자모(ㄱ-ㆎ) 항목 라벨도 한글로 취급 — 음절만 검사하면 ``ㄴ. y=-3x^2-2 • ㄷ. …``
        # 조각이 통째 한 수식으로 병합돼 라벨·불릿이 수식 안에 literal 노출됐다(새본리중
        # #17 보기 박스, 2026-06-12 — 장산중 D2 와 같은 자모 함정의 latex 경로판).
        if not re.search(r"[가-힣ㄱ-ㆎ]", before) and re.search(r"[\^_=]", before):
            # 선행 불릿(• 등)은 박스 줄 경계라 **별도 TEXT** 로 떼어낸다 — 수식에 흡수되면
            # _write_box_content 의 _BOX_BREAK_RE 가 줄을 못 끊어 ``• B = …`` 가 앞 항목과
            # 한 줄로 붙는다(경명여중 중2 #11 상자 A=…•B=…, 2026-06-11). ○(흰 원, 표준화
            # 불릿)도 동일 — 빠지면 ``○ |x|+…=11 ○`` 처럼 수식이 불릿째 흡수돼 박스 항목
            # 줄바꿈이 깨진다(대진고 공수1 #16, 2026-06-12).
            _bm = re.match(r"^\s*[•·▪◦○〇]\s*", before)
            if _bm:
                blocks.append(ContentBlock(type=ContentType.TEXT, value=before[:_bm.end()]))
                before = before[_bm.end():]
            # 꼬리 불릿 = **다음 항목의 줄 경계** — 수식 꼬리에 남기지 말고 별도 TEXT 로.
            _tm = re.search(r"\s*[•·▪◦○〇]\s*$", before)
            _tail_bullet = None
            if _tm and _tm.start() > 0:
                _tail_bullet = before[_tm.start():]
                before = before[:_tm.start()]
            blocks.append(ContentBlock(type=ContentType.EQUATION, value=before.strip()))
            if _tail_bullet:
                blocks.append(ContentBlock(type=ContentType.TEXT, value=_tail_bullet))
        else:
            # before 에 평문 함수꼴 수식(f(-x)=f(x) 등)이 있으면 살린다(#12 (가): OCR 이 일부
            # 조건을 LaTeX 없이 평문으로 줘 텍스트로 흘러가던 것 — 2026-06-08).
            blocks.extend(_split_mixed_text_equation(before))
    if eq_text:
        blocks.append(ContentBlock(type=ContentType.EQUATION, value=eq_text))
    if after_text.strip():
        # 남은 텍스트에 LaTeX가 더 있을 수 있으므로 재귀 처리
        remaining = _split_latex_commands(after_text)
        blocks.extend(remaining)

    # 블록이 하나여도 **수식이면 유지** — 텍스트 블록 전체가 한 수식(\sqrt{24} \div \sqrt{3})
    # 일 때 len>1 조건이 평문으로 강등시켜 백슬래시 LaTeX 가 그대로 인쇄됐다(감사 2026-06-10).
    if len(blocks) > 1 or (blocks and blocks[0].type != ContentType.TEXT):
        return blocks
    return [ContentBlock(type=ContentType.TEXT, value=text)]


# 쪼개진 배점 ``[`` + EQ(숫자) + ``점]`` 제거용(점수가 수식 객체화되면 _SCORE_TEXT_RE 가
# 한 텍스트에서 못 잡아 score 필드와 중복 렌더 — #15 [4.3점] 두 번, 2026-06-09).
_OPEN_SCORE_BRACKET_RE = re.compile(r'[\[(]\s*(?:총\s*)?$')
# ``점`` 뒤 ``, 부분점수 있음`` 같은 부가 문구도 함께 닫는 괄호까지 매칭(수성고 #21
# ``[`` + EQ``8`` + ``점, 부분점수 있음]`` 쪼개진 배점, 2026-06-13). _SCORE_TEXT_RE 와 동치.
_CLOSE_SCORE_JEOM_RE = re.compile(r'^\s*점\s*(?:,[^\])]*)?[\])]')


def _strip_split_score(blocks: list[ContentBlock]) -> list[ContentBlock]:
    """``TEXT(…[) · EQ(숫자) · TEXT(점]…)`` 로 쪼개진 배점을 제거(score 필드와 중복 방지)."""
    out: list[ContentBlock] = []
    i, n = 0, len(blocks)
    while i < n:
        if i + 2 < n:
            t1, eq, t2 = blocks[i], blocks[i + 1], blocks[i + 2]
            if (t1.type == ContentType.TEXT and t2.type == ContentType.TEXT
                    and eq.type in (ContentType.EQUATION, ContentType.EQUATION_BLOCK)
                    and re.fullmatch(r'\d+(?:\.\d+)?', (eq.value or '').strip() or '')
                    and _OPEN_SCORE_BRACKET_RE.search(t1.value or '')
                    and _CLOSE_SCORE_JEOM_RE.match(t2.value or '')):
                nv1 = _OPEN_SCORE_BRACKET_RE.sub('', t1.value or '').rstrip()
                nv2 = _CLOSE_SCORE_JEOM_RE.sub('', t2.value or '').lstrip()
                if nv1.strip():
                    out.append(ContentBlock(type=ContentType.TEXT, value=nv1,
                                            underline=t1.underline))
                if nv2.strip():
                    out.append(ContentBlock(type=ContentType.TEXT, value=nv2,
                                            underline=t2.underline))
                i += 3
                continue
        out.append(blocks[i])
        i += 1
    return out


def _strip_score_text(blocks: list[ContentBlock]) -> list[ContentBlock]:
    """텍스트 블록에서 [N점] 배점 패턴을 제거 (score 필드와 중복 방지).

    ⚠️ 박스(<상자>/<조건>/<보기>) 머리 **이후** 블록은 건드리지 않는다 — 채점기준 박스의
    항목별 배점([1점][3점]…)이 발문 배점으로 오인돼 소실되던 것 방지(새론중 서답형2,
    2026-06-11). 발문 배점은 박스 앞에 있으므로 박스 전 블록만 처리하면 충분하다.
    """
    box_i = next((i for i, b in enumerate(blocks)
                  if b.type == ContentType.TEXT and _RAW_BOX_MARK_RE.search(b.value or "")),
                 len(blocks))
    pre, box = blocks[:box_i], blocks[box_i:]
    pre = _strip_split_score(pre)   # 쪼개진 [ + EQ + 점] 먼저 제거(#15, 2026-06-09)
    result: list[ContentBlock] = []
    for block in pre:
        if block.type == ContentType.TEXT:
            cleaned = _SCORE_TEXT_RE.sub('', block.value)
            if cleaned.strip():
                result.append(ContentBlock(
                    type=ContentType.TEXT,
                    value=cleaned,
                    underline=block.underline,
                ))
        else:
            result.append(block)
    return result + box


_ESSAY_LABEL_WORD_RE = re.compile(r'\[\s*(서술형|서답형)(\s*\d*\s*)\]')


def _normalize_essay_label_type(doc: "ExamDocument") -> None:
    """문서의 서술형/서답형 라벨이 **혼재하면 '서답형'으로 통일**(결정적 후처리).

    OCR 이 같은 시험지의 일부 문항 라벨을 ``서답형``↔``서술형`` 으로 다르게 읽는다(같은 시험지는
    한 용어로 일관됨 — 사용자 2026-06-09: "전부 서답형인데 일부가 서술형으로 치환"). 혼재는
    OCR 오인이므로 **교육과정 공식 구성형 용어인 '서답형'** 으로 통일한다(사용자 결정). 라벨이
    한 종류로 일관되면(정상) 건드리지 않는다 — 진짜 '서술형' 시험지를 보존. 프롬프트 강화(라벨
    원문 그대로 읽기)와 병행하나, 이 결정적 통일이 캐시·오인에도 견고하다.
    """
    found = set()
    for pg in doc.pages:
        for q in pg.questions:
            for b in q.contents:
                if b.type == ContentType.TEXT and b.value:
                    found.update(m.group(1) for m in _ESSAY_LABEL_WORD_RE.finditer(b.value))
    if len(found) < 2:
        return                                   # 일관(또는 라벨 없음) → 유지
    target = "서답형"
    for pg in doc.pages:
        for q in pg.questions:
            for b in q.contents:
                if b.type == ContentType.TEXT and b.value:
                    b.value = _ESSAY_LABEL_WORD_RE.sub(
                        lambda m: f"[{target}{m.group(2)}]", b.value)
            if getattr(q, "label_type", None) in ("서술형", "서답형"):
                q.label_type = target


def build_document(
    pages: list[ExamPage],
    title: str = "",
    subject: str = "",
    grade: str = "",
) -> ExamDocument:
    """ExamPage 리스트로 ExamDocument 생성."""
    doc = ExamDocument(title=title, subject=subject, grade=grade)
    doc.pages = pages

    # 서술형/서답형 라벨 혼재(OCR 오인) → 서답형 통일(결정적).
    _normalize_essay_label_type(doc)

    # 헤더에서 제목/과목 자동 추출 시도
    if pages and not title:
        header = pages[0].header_text
        if header:
            doc.title = header

    return doc
