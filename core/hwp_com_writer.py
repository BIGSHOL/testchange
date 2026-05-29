# -*- coding: utf-8 -*-
"""ExamDocument → HWP COM 직접 입력 writer.

한글(HWP)을 COM으로 구동해 문서를 직접 작성한다. 수식·표 크기는 HWP가
네이티브로 계산하므로 기존 ``hwpx_writer.py`` 의 크기추정 로직이 전혀 필요 없다.
HWP 미설치 환경에서는 ``hwpx_writer.write_exam_to_hwpx`` 로 폴백한다(GUI에서 분기).

수식 스크립트 생성은 ``core/latex_to_hwpeq.latex_to_hwpeq`` 를 그대로 재사용한다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from core.hwp_com import HwpSession, CIRCLE_NUMBERS
from core.latex_to_hwpeq import latex_to_hwpeq
from models.exam_document import (
    ContentBlock,
    ContentType,
    Choice,
    ExamDocument,
    ExamPage,
    Question,
)

# 객관식→서술형 전환 구분선 (기존 XML writer와 동일 문구)
_ESSAY_SEPARATOR = "──────────── 서술형 ────────────"
# 서술형 답안 작성 공간 줄 수
_ESSAY_BLANK_LINES = 6


def _eq_script(block: ContentBlock) -> str:
    """ContentBlock에서 HWP 수식 스크립트를 얻는다(없으면 LaTeX에서 변환)."""
    if block.hwp_equation:
        return block.hwp_equation
    return latex_to_hwpeq(block.value)


class HwpComWriter:
    """ExamDocument를 HWP 세션에 렌더링한다."""

    def __init__(self, session: HwpSession):
        self.s = session
        self._title = ""

    # ── 콘텐츠 블록 ────────────────────────────────────────
    def _write_block(self, block: ContentBlock) -> None:
        if block.type == ContentType.TABLE:
            # 표는 자체 단락 필요 — 앞 단락과 분리
            self.s.break_para()
            self.s.table(block.rows or [])
        elif block.type == ContentType.EQUATION_BLOCK:
            self.s.break_para()
            self.s.equation(_eq_script(block))
        elif block.type == ContentType.EQUATION:
            self.s.equation(_eq_script(block))
        elif block.type == ContentType.TEXT:
            if block.underline:
                self.s.underline_run(block.value)
            else:
                self.s.text(block.value)
        # ContentType.IMAGE: 파서가 생성하지 않는 dead type — 미구현(기존과 동일)

    def _has_table(self, blocks: list[ContentBlock]) -> bool:
        return any(b.type == ContentType.TABLE for b in blocks)

    # ── 문제 ──────────────────────────────────────────────
    def _write_question(self, question: Question) -> None:
        is_essay = not question.choices

        # 번호 "N. " (숫자는 일반 텍스트)
        self.s.text(f"{question.number}. ")

        # 배점은 본문 텍스트 끝(표 앞)에 둬 표 셀로 들어가는 것을 방지.
        # 표가 본문에 있으면 배점을 먼저, 없으면 본문 뒤에 인라인으로.
        has_table = self._has_table(question.contents)
        if has_table and question.score:
            # 표가 있으면 배점을 본문 앞에 둬 표 셀로 들어가는 것을 방지
            self.s.text(f"[{question.score}점] ")

        for block in question.contents:
            self._write_block(block)

        if not has_table and question.score:
            self._write_score(question.score)

        self.s.break_para()

        # 보기 (한 보기당 한 줄)
        for choice in question.choices:
            self._write_choice(choice)
            self.s.break_para()

        # 소문항 재귀
        for sub in question.sub_questions:
            self._write_question(sub)

        # 서술형 풀이 공간
        if is_essay:
            self._write_essay_space()

        # 문제 간 빈 줄
        self.s.break_para()

    def _write_choice(self, choice: Choice) -> None:
        circle = CIRCLE_NUMBERS.get(choice.number, f"({choice.number})")
        self.s.text(f"  {circle} ")
        for block in choice.contents:
            self._write_block(block)

    def _write_score(self, score: int) -> None:
        self.s.text(f" [{score}점]")

    def _write_essay_space(self) -> None:
        self.s.text("풀이)")
        for _ in range(_ESSAY_BLANK_LINES):
            self.s.break_para()

    # ── 페이지 / 문서 ──────────────────────────────────────
    def _write_page(self, page: ExamPage) -> None:
        # 헤더가 제목과 동일하면 생략(build_document가 헤더를 제목으로 복사하므로 중복 방지)
        header = page.header_text
        if header and header.strip() != self._title.strip():
            self.s.text(header)
            self.s.break_para()
            self.s.break_para()

        prev_was_mc = False
        for question in page.questions:
            is_essay = not question.choices
            if is_essay and prev_was_mc:
                self.s.align_center()
                self.s.text(_ESSAY_SEPARATOR)
                self.s.break_para()
                self.s.align_left()
            self._write_question(question)
            prev_was_mc = bool(question.choices)

    def write(self, document: ExamDocument) -> None:
        # 본문 텍스트(한글 등) 글자 크기 고정. 수식은 equation()에서 eq_pt로 고정.
        self.s.set_char_size(self.s.base_pt)
        self._title = document.title or ""
        if document.title:
            self.s.align_center()
            self.s.text(document.title)
            self.s.break_para()
            self.s.align_left()
            self.s.break_para()
        for page in document.pages:
            self._write_page(page)


def write_exam_to_hwp(
    document: ExamDocument,
    output_path: str | Path,
    template_path: str | Path | None = None,
) -> Path:
    """편의 함수: ExamDocument를 HWP COM으로 .hwpx 파일로 저장.

    Args:
        document: 변환할 시험 문서
        output_path: 출력 .hwpx 경로
        template_path: 양식 파일(.hwp/.hwpx). 주어지면 해당 서식 위에 작성.

    Returns:
        저장된 파일 경로
    """
    output_path = Path(output_path)
    # 빌드는 숨김(빠름), 저장 직전 force_layout()에서 창을 띄워 레이아웃 일괄계산.
    with HwpSession(visible=False) as s:
        if template_path:
            s.open(template_path)
            s.move_doc_begin()
        writer = HwpComWriter(s)
        writer.write(document)
        s.save_hwpx(output_path)
    return output_path


# ── 스모크 테스트 ─────────────────────────────────────────
def _sample_document() -> ExamDocument:
    """프로토타입과 동일한 검증용 샘플(텍스트+수식+표+5지선다+밑줄)."""
    def eq(latex: str, block: bool = False) -> ContentBlock:
        return ContentBlock(
            type=ContentType.EQUATION_BLOCK if block else ContentType.EQUATION,
            value=latex,
            hwp_equation=latex_to_hwpeq(latex),
        )

    def t(s: str, underline: bool = False) -> ContentBlock:
        return ContentBlock(type=ContentType.TEXT, value=s, underline=underline)

    q1 = Question(
        number=1, score=3,
        contents=[
            t("다음 식 "), eq(r"x^{2} + \frac{1}{2}x - 3"),
            t(" 에서 "), eq("x^2"), t(" 의 계수를 구하시오."),
        ],
    )
    q2 = Question(
        number=2, score=4,
        contents=[
            t("세 수 "), eq("A = 2^{6}"), t(", "), eq("B = 3^{4}"),
            t(", "), eq("C = 5^{3}"), t(" 의 대소 관계로 옳은 것은?"),
        ],
        choices=[
            Choice(1, [eq("A < B < C")]),
            Choice(2, [eq("A < C < B")]),
            Choice(3, [eq("B < A < C")]),
            Choice(4, [eq("B < C < A")]),
            Choice(5, [eq("C < A < B")]),
        ],
    )
    q3 = Question(
        number=3, score=5,
        contents=[
            t("아래 표는 함수 "), eq("y = f(x)"),
            t(" 의 값을 나타낸 것이다. "),
            t("f(-1) + f(2)", underline=True),
            t(" 의 값을 구하시오."),
            ContentBlock(
                type=ContentType.TABLE, value="",
                rows=[["x", "-1", "0", "1", "2"], ["f(x)", "3", "1", "-1", "5"]],
            ),
        ],
    )
    page = ExamPage(
        page_number=1,
        header_text="2025학년도 1학기 중간고사  ·  수학  ·  중2",
        questions=[q1, q2, q3],
    )
    return ExamDocument(title="중2 수학 중간고사", subject="수학", grade="중2",
                        pages=[page])


if __name__ == "__main__":
    import sys

    out = sys.argv[1] if len(sys.argv) > 1 else r"D:\tmp\hwp_com_writer_smoke.hwpx"
    write_exam_to_hwp(_sample_document(), out)
    print("[ok] saved:", out)
