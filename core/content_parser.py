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

    # 쉼표로 구분된 독립 수식 분리 (안전 폴백)
    question.contents = _split_comma_equations(question.contents)

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

    # 쉼표로 구분된 독립 수식 분리
    choice.contents = _split_comma_equations(choice.contents)

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

    if not value and type_str != "image":
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
    # 괄호 없는 수식 나열 → 개별 수식 + 텍스트 쉼표(종전 동작).
    for i, p in enumerate(parts):
        if i > 0:
            result.append(ContentBlock(type=ContentType.TEXT, value=", "))
        result.append(ContentBlock(type=ContentType.EQUATION, value=p))
    return True


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
_MATH_EXPR_RE = re.compile(
    r'(?<![a-zA-Z])'              # 앞에 영문자 없음 (단어 중간 방지)
    r'('
    r'[a-zA-Z0-9]+(?:\.[0-9]+)?'  # 시작: 변수/숫자(소수점 포함, 예 1.1)
    r'(?:'
    r'\s*[=><+\-×÷≤≥≠^_]\s*'      # 수학 연산자
    r'[a-zA-Z0-9]+(?:\.[0-9]+)?'  # 뒤따르는 변수/숫자(소수점 포함)
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


def _split_underline_markup(text: str) -> list[ContentBlock]:
    """텍스트에서 __밑줄__ 마크업을 분리하여 ContentBlock 리스트로 반환.

    예: "옳지 __않은__ 것은?"
    → text("옳지 ") + text("않은", underline=True) + text(" 것은?")
    """
    blocks: list[ContentBlock] = []
    last_end = 0

    for m in _UNDERLINE_RE.finditer(text):
        before = text[last_end:m.start()]
        if before:
            blocks.append(ContentBlock(type=ContentType.TEXT, value=before))
        inner = m.group(1)
        if inner:
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
    r'\\(?:sqrt|d?frac|tfrac|sum|prod|int|oint|lim|'
    r'times|div|pm|mp|cdot|cdots|ldots|'
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
        blocks.append(ContentBlock(type=ContentType.TEXT, value=before))
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
