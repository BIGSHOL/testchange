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


def _parse_question(q_data: dict) -> Question:
    """문제 dict를 Question 객체로 변환."""
    question = Question(
        number=q_data.get("number", 0),
        score=q_data.get("score"),
    )

    # 배점 처리(원시 단계): 숫자 분리 전에 raw 텍스트에서 [N점]을 추출·제거한다.
    # (숫자 분리가 "[9점]"의 9를 수식으로 떼어내면 정규식이 못 맞추므로 반드시 먼저.)
    raw_contents = [dict(bd) for bd in q_data.get("contents", [])]
    if not question.score:
        for bd in raw_contents:
            if bd.get("type") == "text":
                m = re.search(r'\[(\d+)점\]', bd.get("value", ""))
                if m:
                    question.score = int(m.group(1))
                    break
    for bd in raw_contents:
        if bd.get("type") == "text" and bd.get("value"):
            bd["value"] = _SCORE_TEXT_RE.sub(' ', bd["value"])

    # 문제 본문
    for block_data in raw_contents:
        result = _parse_content_block(block_data)
        if isinstance(result, list):
            question.contents.extend(result)
        elif result:
            question.contents.append(result)

    # 수식 끝 정의역 (x=0, 1, ⋯, 50) 을 본수식에서 떼어 개별 수식+텍스트로(줄바꿈 자연화)
    question.contents = _split_trailing_domain(question.contents)

    # 쉼표로 구분된 독립 수식 분리 (안전 폴백)
    question.contents = _split_comma_equations(question.contents)

    # eq·(연산자)·eq 로 쪼개진 수식(x = -2y+3)을 한 객체로 병합(가운데 = 평문화 방지)
    question.contents = _merge_operator_split_equations(question.contents)

    # 확통 연산자·확률변수 P/E/V/N/Z/X/Y 의 \mathrm(로만)을 벗겨 이탤릭으로(순열 제외)
    question.contents = _italicize_stat_operators(question.contents)

    # 기하 점/선/면 이름(통째 대문자 수식)을 로만체로 강제
    question.contents = _romanize_point_names(question.contents)

    # 잔여 [N점] 제거 (분리 후에도 온전히 남은 경우 대비)
    question.contents = _strip_score_text(question.contents)

    # 선택지
    for choice_data in q_data.get("choices", []):
        choice = _parse_choice(choice_data)
        if choice:
            question.choices.append(choice)

    # 소문항
    for sub_data in q_data.get("sub_questions", []):
        sub = _parse_question(sub_data)
        question.sub_questions.append(sub)

    return question


def _parse_choice(choice_data: dict) -> Choice | None:
    """선택지 dict를 Choice 객체로 변환."""
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
    # 확통 연산자·확률변수 \mathrm 벗겨 이탤릭(순열 제외)
    choice.contents = _italicize_stat_operators(choice.contents)
    # 기하 점/선/면 이름 로만체 강제
    choice.contents = _romanize_point_names(choice.contents)

    return choice


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

    # 텍스트 블록에 __밑줄__ 마크업이 있으면 분리
    if content_type == ContentType.TEXT and "__" in value:
        split = _split_underline_markup(value)
        if len(split) > 1:
            return split  # type: ignore[return-value]

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

    # 텍스트 블록에 수식 패턴이 섞여 있으면 분리
    if content_type == ContentType.TEXT:
        split = _split_mixed_text_equation(value)
        if len(split) > 1:
            return split  # type: ignore[return-value]

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

# 기하 키워드(엄격) — **대문자 1글자** 수식을 로만으로 만들지 결정. 확통의 X·P·E·V·Z·N
# (확률변수·연산자)을 로만으로 만들지 않도록, 점·선·면·다각형 등 **확실한 도형 단어만**
# 포함한다(넓이·함수·그래프 같은 넓은 단어는 X 그래프 오인 방지를 위해 제외). (사용자 2026-06-08)
_GEOMETRY_KEYWORDS = (
    "점", "꼭짓점", "교점", "원점", "중점", "무게중심",
    "삼각형", "사각형", "정사각형", "직사각형", "마름모", "평행사변형", "사다리꼴",
    "선분", "직선", "반직선", "호", "부채꼴",
    "△", "∠", "∆",
)


def _has_geometry_context(blocks: list[ContentBlock]) -> bool:
    """blocks 안 어느 텍스트/수식에든 엄격 기하 키워드가 있으면 True."""
    text = " ".join(str(b.value or "") for b in blocks)
    return any(k in text for k in _GEOMETRY_KEYWORDS)


# 확통 연산자·확률변수(P 확률·E 기댓값·V 분산·N 정규분포·Z 표준정규·X,Y 확률변수)는
# **이탤릭**이어야 한다(사용자 2026-06-08: "이탤릭인데 로만 된 게 너무 많다"). 그런데 OCR 이
# 이들을 관례적으로 \mathrm(로만)으로 감싼다 → 벗겨서 이탤릭으로. 단 **순열 nPr**(\mathrm{P}
# 뒤에 _ 첨자)은 로만 유지, **조합 nCr** 의 C 는 애초에 대상 아님(아래 집합에 C 없음).
_STAT_MATHRM_RE = re.compile(r'\\mathrm\{([XYPEVNZ])\}(?!\s*_)')


def _italicize_stat_operators(blocks: list[ContentBlock]) -> list[ContentBlock]:
    """수식 안 ``\\mathrm{P/E/V/N/Z/X/Y}`` 를 이탤릭(맨 글자)으로 되돌린다(순열 P_ 는 제외)."""
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


def _romanize_point_names(blocks: list[ContentBlock]) -> list[ContentBlock]:
    """기하 점/선/면 이름(통째 대문자 수식 블록)을 \\mathrm 으로 감싸 로만체로 강제.

    **기하 도형 라벨에만** 적용한다(사용자 2026-06-08: "도형 아닌데 로만체 너무 많다").
      - 대문자 2~4글자(AB, ABC, OAB …) = 꼭짓점 라벨 → 무조건 로만(통계엔 거의 없음).
      - 대문자 1글자(A, X, P, E …) = **같은 contents 에 기하 키워드가 있을 때만** 로만.
        없으면 이탤릭 유지(확률변수 X·연산자 P/E/V 등을 로만화하지 않기 위해).
    """
    has_geo = _has_geometry_context(blocks)
    out: list[ContentBlock] = []
    for b in blocks:
        if b.type == ContentType.EQUATION:
            v = (b.value or "").strip()
            if v and "\\mathrm" not in v and _BARE_UPPER_EQ_RE.match(v):
                m = _UPPER_LETTERS_RE.match(v)
                n_letters = len(m.group(0)) if m else 0
                # 2글자 이상은 라벨로 보고 항상 로만, 1글자는 기하 문맥에서만 로만.
                if n_letters >= 2 or (n_letters == 1 and has_geo):
                    out.append(ContentBlock(type=ContentType.EQUATION,
                                            value=f"\\mathrm{{{v}}}"))
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
        if b.type in (ContentType.EQUATION, ContentType.EQUATION_BLOCK) and b.value:
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


def _split_one_eq_commas(block: ContentBlock, result: list[ContentBlock]) -> bool:
    """쉼표 든 수식 한 블록을 규칙대로 분해해 ``result`` 에 추가. 처리했으면 True."""
    v = (block.value or "").strip()
    paren = _wrapped_in_parens(v)
    inner = v[1:-1] if paren else v
    parts = [p.strip() for p in _split_at_top_level_commas(inner) if p.strip()]
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
    # ``P(…)=16/9, P(…)`` → "16/9 , P(…)" 로 깨진다. 진짜 나열은 항목이 **전부 단순 원자**
    # (숫자·변수·⋯)이거나 **전부 최상위 관계식**(=,<,>,≤,≥…)일 때뿐 — 일부만 관계식이고
    # 나머지가 함수식(P(…))이면 쉼표는 곱셈 자리의 OCR 오삽입이므로 **쉼표 제거 후 한 수식**.
    if not (all(_is_atom_item(p) for p in parts) or all(_has_toplevel_relation(p) for p in parts)):
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
    """단순 원자 = 숫자·변수(_VAR_ITEM_RE)·줄임표(⋯/\\cdots) — 진짜 나열 후보."""
    p = (p or "").strip()
    return bool(_VAR_ITEM_RE.match(p)
                or re.fullmatch(r"[-+]?\d+(?:\.\d+)?", p)
                or re.fullmatch(r"\\c?dots|\\ldots|⋯|\.\.\.", p))


def _has_toplevel_relation(p: str) -> bool:
    """괄호·중괄호 **내용 제거 후** 최상위에 관계연산자가 있으면 True(함수 인자 속 ≤ 제외)."""
    s = p or ""
    for _ in range(6):                       # 중첩 괄호/중괄호 반복 제거
        s2 = re.sub(r"\([^()]*\)|\{[^{}]*\}", "", s)
        if s2 == s:
            break
        s = s2
    return bool(re.search(r"=|<|>|\\le\b|\\leq\b|\\ge\b|\\geq\b|\\neq\b|\\ne\b|\\in\b|≤|≥|≠", s))


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
_MATH_ATOM = r'[a-zA-Z0-9]+(?:\.[0-9]+)?(?:\s*\([^()가-힣]*\))?'
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


def _split_mixed_text_equation(text: str) -> list[ContentBlock]:
    """텍스트 안에 섞인 수식 패턴(영문 변수, 부등호 등)을 분리.

    예: "(a > 0, b는 정수)에서"
    → text("(") + eq("a > 0") + text(", ") + eq("b") + text("는 정수)에서")
    """
    # 한글이 전혀 없으면 분리 불필요 (순수 텍스트거나 이미 수식)
    if not re.search(r'[\uac00-\ud7a3]', text):
        return [ContentBlock(type=ContentType.TEXT, value=text)]

    # 수식 후보가 없으면 분리 불필요
    if not re.search(r'[a-zA-Z0-9]', text):
        return [ContentBlock(type=ContentType.TEXT, value=text)]

    blocks: list[ContentBlock] = []
    last_end = 0

    for m in _MATH_EXPR_RE.finditer(text):
        expr = m.group(1).strip()
        # 너무 긴 영문 단어는 수식이 아님 (예: "정수")
        if len(expr) > 20:
            continue
        # 한글이 포함된 매치는 건너뜀
        if re.search(r'[\uac00-\ud7a3]', expr):
            continue
        # 단독 숫자도 모두 수식화 (사용자 요구: 숫자는 전부 수식)

        before = text[last_end:m.start()]
        if before:
            blocks.append(ContentBlock(type=ContentType.TEXT, value=before))
        blocks.append(ContentBlock(type=ContentType.EQUATION, value=expr))
        last_end = m.end()

    after = text[last_end:]
    if after:
        blocks.append(ContentBlock(type=ContentType.TEXT, value=after))

    return blocks if len(blocks) > 1 else [ContentBlock(type=ContentType.TEXT, value=text)]


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


# ── LaTeX 명령어 감지 패턴 ──
_LATEX_CMD_RE = re.compile(
    r'\\[!,;: ]'                         # 간격 명령(\! \, \; \: \ ) — P\!\left 의 \! 가
    r'|\\(?:sqrt|d?frac|tfrac|sum|prod|int|oint|lim|'   # text 로 새 "P₩!" 되는 것 방지(#12)
    r'times|div|pm|mp|cdot|cdots|ldots|quad|qquad|'
    r'left|right|leq|geq|neq|infty|'
    r'alpha|beta|gamma|delta|epsilon|zeta|eta|theta|iota|kappa|'
    r'lambda|mu|nu|xi|pi|rho|sigma|tau|phi|chi|psi|omega|'
    r'partial|nabla|forall|exists|'
    r'dot|ddot|hat|bar|vec|tilde|overline|underline|'
    r'log|ln|sin|cos|tan|sec|csc|cot|'
    r'square|circ|triangle|angle|perp|parallel|'
    r'cup|cap|subset|supset|in|notin|'
    r'mathbb|mathrm|mathbf|mathit|text)'
    r'(?:\b|(?=[{^_(\[]))'
)

# 배점 텍스트 패턴 (예: [3점], [4점])
_SCORE_TEXT_RE = re.compile(r'\s*\[\d+점\]\s*')


def _split_latex_commands(text: str) -> list[ContentBlock]:
    """텍스트에서 LaTeX 명령어를 감지하여 text + equation 블록으로 분리.

    예: "ㄱ. \\sqrt{2}+\\sqrt{2}" → text("ㄱ. ") + eq("\\sqrt{2}+\\sqrt{2}")
    예: "\\sqrt{24} \\div \\sqrt{3} 의 값은" → eq(...) + text(" 의 값은")
    """
    first_match = _LATEX_CMD_RE.search(text)
    if not first_match:
        return [ContentBlock(type=ContentType.TEXT, value=text)]

    latex_start = first_match.start()
    # 수식 직전에 **공백 없이 붙은 식별자**(P, f, X, 숫자 등)는 수식의 일부 → 수식 영역에
    # 포함시킨다. 안 그러면 "P\!\left(…" 의 P 가 텍스트로 떨어지고 \! 가 literal "P₩!" 로
    # 샌다(학남고 #12, 2026-06-08). 한글은 텍스트이므로 ASCII 영숫자만 끌어온다.
    while latex_start > 0 and ("a" <= text[latex_start - 1].lower() <= "z"
                               or text[latex_start - 1].isdigit()):
        latex_start -= 1
    before = text[:latex_start]

    # LaTeX 영역 끝 찾기: 한글이 나오면 수식 종료
    rest = text[latex_start:]
    korean_match = re.search(r'(?<=[^\\])\s+[\uac00-\ud7a3]', rest)
    if korean_match:
        eq_end = latex_start + korean_match.start()
        eq_text = text[latex_start:eq_end].strip()
        after_text = text[eq_end:]
    else:
        eq_text = rest.strip()
        after_text = ""

    blocks: list[ContentBlock] = []
    if before.strip():
        # before 에 평문 함수꼴 수식(f(-x)=f(x) 등)이 있으면 살린다(#12 (가): OCR 이 일부
        # 조건을 LaTeX 없이 평문으로 줘 텍스트로 흘러가던 것 — 2026-06-08).
        blocks.extend(_split_mixed_text_equation(before))
    if eq_text:
        blocks.append(ContentBlock(type=ContentType.EQUATION, value=eq_text))
    if after_text.strip():
        # 남은 텍스트에 LaTeX가 더 있을 수 있으므로 재귀 처리
        remaining = _split_latex_commands(after_text)
        blocks.extend(remaining)

    return blocks if len(blocks) > 1 else [
        ContentBlock(type=ContentType.TEXT, value=text)
    ]


def _extract_score(blocks: list[ContentBlock]) -> int | None:
    """텍스트 블록에서 첫 [N점] 배점 숫자를 추출 (score 필드 보강용)."""
    for block in blocks:
        if block.type == ContentType.TEXT:
            m = re.search(r'\[(\d+)점\]', block.value)
            if m:
                return int(m.group(1))
    return None


def _strip_score_text(blocks: list[ContentBlock]) -> list[ContentBlock]:
    """텍스트 블록에서 [N점] 배점 패턴을 제거 (score 필드와 중복 방지)."""
    result: list[ContentBlock] = []
    for block in blocks:
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
    return result


def build_document(
    pages: list[ExamPage],
    title: str = "",
    subject: str = "",
    grade: str = "",
) -> ExamDocument:
    """ExamPage 리스트로 ExamDocument 생성."""
    doc = ExamDocument(title=title, subject=subject, grade=grade)
    doc.pages = pages

    # 헤더에서 제목/과목 자동 추출 시도
    if pages and not title:
        header = pages[0].header_text
        if header:
            doc.title = header

    return doc
