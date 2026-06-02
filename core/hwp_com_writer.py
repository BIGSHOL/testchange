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


import re

# 조건/보기 박스 마커·불릿·경계대시
_COND_MARKER_RE = re.compile(r"(<\s*조건\s*>|<\s*보기\s*>|\[\s*조건\s*\]|\[\s*보기\s*\])")
_BULLET_RE = re.compile(r"\s*[•·▪◦]\s*")
_DASH_RUN_RE = re.compile(r"\s*[-−—–―─━]{2,}\s*")  # 하이픈·각종 대시·박스선(U+2500/2501)


def _has_box_markup(text: str) -> bool:
    """줄 분리가 필요한 박스 텍스트인지 — **불릿(•)이 있을 때만** 참.

    (불릿 없이 "<조건>에 맞게"처럼 본문에서 박스를 가리키는 인라인 참조는
    줄을 끊으면 안 되므로 제외.)
    """
    return bool(_BULLET_RE.search(text))


def _segment_box_text(text: str) -> list[str]:
    """박스 텍스트를 줄 단위 리스트로 분리.

    - 경계 대시(−−, --) → 줄 경계로 제거
    - <조건>/<보기> 마커 → 독립 줄
    - 불릿(•) → 각 항목을 "• "로 시작하는 독립 줄
    """
    t = _DASH_RUN_RE.sub("\n", text)
    t = _COND_MARKER_RE.sub(lambda m: "\n" + re.sub(r"\s+", "", m.group(1)) + "\n", t)
    t = _BULLET_RE.sub("\n• ", t)
    lines = [ln.strip() for ln in t.split("\n")]
    return [ln for ln in lines if ln]


def _choice_complexity(choice: Choice) -> int:
    """보기 하나의 '길이' 추정. 블록수식/표가 있으면 매우 큼(→1단)."""
    score = 0
    for b in choice.contents:
        if b.type in (ContentType.TABLE, ContentType.EQUATION_BLOCK, ContentType.IMAGE):
            return 999
        score += len(b.value or "")
    return score


def _choice_columns(choices: list[Choice]) -> int:
    """보기 배치 단 수(1~5)를 보기 길이로 자동 결정.

    아주 짧은 보기는 한 줄에 여러 개(최대 5), 길면 한 줄당 하나.
    """
    if not choices:
        return 1
    n = len(choices)
    maxc = max(_choice_complexity(c) for c in choices)
    if maxc >= 18:
        return 1
    if maxc >= 9:
        return 2
    # 매우 짧음: 전부 한 줄(최대 5단) 또는 적절히 나눔
    return min(n, 5)


def _eq_script(block: ContentBlock) -> str:
    """ContentBlock에서 HWP 수식 스크립트를 얻는다(없으면 LaTeX에서 변환)."""
    if block.hwp_equation:
        return block.hwp_equation
    return latex_to_hwpeq(block.value)


# 숫자만으로 이뤄진 인라인 수식(예: "15", "3.14", "1,000")은 일반 텍스트로 렌더한다.
# HWP COM으로 만든 '숫자 전용' 수식 객체는 베이스라인 메트릭이 stale 상태로 남아
# 줄 위로 떠오르는(=잘못 렌더되는) 버그가 있다(편집기 재저장 시에만 정상화). 글자·연산자가
# 하나라도 섞이면(x, x+y, x=15, x^2 …) 정상 렌더되므로 '순수 숫자'만 강등한다.
_PLAIN_NUMBER_RE = re.compile(r"^[\d\s.,]+$")


def _is_plain_number(script: str) -> bool:
    """수식 스크립트가 숫자·공백·구두점(.,)만으로 이뤄졌는지 — 텍스트 강등 대상."""
    s = (script or "").strip()
    return bool(s) and any(c.isdigit() for c in s) and bool(_PLAIN_NUMBER_RE.match(s))


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
            script = _eq_script(block)
            if _is_plain_number(script):
                self.s.text(script.strip())
            else:
                self.s.equation(script)
        elif block.type == ContentType.EQUATION:
            script = _eq_script(block)
            if _is_plain_number(script):
                self.s.text(script.strip())  # 숫자 전용 수식 → 텍스트(베이스라인 버그 회피)
            else:
                self.s.equation(script)
        elif block.type == ContentType.TEXT:
            if block.underline:
                self.s.underline_run(block.value)
            elif _has_box_markup(block.value):
                self._write_segmented_text(block.value)
            else:
                self.s.text(block.value)
        elif block.type == ContentType.IMAGE:
            # 도형/그림 크롭 이미지 임베딩 (value=이미지 파일 경로)
            if block.value:
                self.s.break_para()
                self.s.align_center()
                self.s.insert_picture(block.value)
                self.s.break_para()
                self.s.align_left()

    def _write_segmented_text(self, text: str) -> None:
        """조건/보기 박스 텍스트를 줄 단위로 분리해 출력.

        OCR이 박스를 한 줄로 흘려 "−−<조건>−−• A• B• C" 처럼 뭉쳐 들어오면
        <조건>·각 불릿(•)을 개별 줄로 분리한다.
        """
        lines = _segment_box_text(text)
        for line in lines:
            self.s.break_para()  # 박스 각 줄은 새 줄에서 시작(앞 문장과 분리)
            self.s.text(line)

    def _has_table(self, blocks: list[ContentBlock]) -> bool:
        return any(b.type == ContentType.TABLE for b in blocks)

    # ── 문제 ──────────────────────────────────────────────
    def _write_question(self, question: Question) -> None:
        is_essay = not question.choices
        has_subs = bool(question.sub_questions)
        # 소문항이 있는 부모는 배점이 '총점'이라 본문에 "[총 N점]"으로 이미 표기됨.
        # 인라인 배점([N점])을 또 찍으면 중복 → 부모는 인라인 배점 생략, 소문항만 표기.
        show_score = bool(question.score) and not has_subs

        # 번호 "N. " (숫자는 일반 텍스트)
        self.s.text(f"{question.number}. ")

        # 배점은 본문 텍스트 끝(표 앞)에 둬 표 셀로 들어가는 것을 방지.
        # 표가 본문에 있으면 배점을 먼저, 없으면 본문 뒤에 인라인으로.
        has_table = self._has_table(question.contents)
        if has_table and show_score:
            # 표가 있으면 배점을 본문 앞에 둬 표 셀로 들어가는 것을 방지
            self.s.text(f"[{question.score}점] ")

        for block in question.contents:
            self._write_block(block)

        if not has_table and show_score:
            self._write_score(question.score)

        self.s.break_para()

        # 보기 — 길이에 따라 1~5단 배치(짧으면 여러 단을 한 줄에, 길면 한 줄당 하나)
        if question.choices:
            cols = _choice_columns(question.choices)
            last = len(question.choices) - 1
            for i, choice in enumerate(question.choices):
                self._write_choice(choice)
                if i % cols == cols - 1 or i == last:
                    self.s.break_para()
                else:
                    self.s.text("\t")

        # 소문항 재귀
        for sub in question.sub_questions:
            self._write_question(sub)

        # 서술형 '풀이)' 답안 공간은 넣지 않는다(사용자 요구 2026-06-02): 배점에서 끝낸다.

        # 문제 간 빈 줄
        self.s.break_para()

    def _write_choice(self, choice: Choice) -> None:
        # 선택지는 들여쓰기 없이 좌측에 붙인다(사용자 요구 2026-06-02).
        circle = CIRCLE_NUMBERS.get(choice.number, f"({choice.number})")
        self.s.text(f"{circle} ")
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


def _fix_invisible_charpr(hwpx_path: str | Path) -> int:
    """저장된 .hwpx 의 글자모양에서 장평(ratio)·상대크기(relSz) 0 을 100 으로 보정.

    템플릿(.hwp/.hwpx)을 열어 작성하면 그 컨텍스트의 글자모양이 장평/상대크기
    0 으로 상속되는 경우가 있다. ratio=0 이면 글자 폭이 0, relSz=0 이면 글자
    높이가 0 이라 **본문 텍스트가 통째로 안 보인다**(수식은 별도 객체라 영향 없음).
    COM 으로는 이 컨텍스트를 안정적으로 못 덮으므로(SelectAll+CharShape 는 수식
    객체 포함 시 헤드리스에서 hang), 저장 후 header.xml 을 직접 패치한다.

    ``<hh:ratio …="0"…>`` / ``<hh:relSz …="0"…>`` 의 0 속성만 100 으로 바꾼다
    (이 태그들엔 스크립트별 비율값만 들어 있어 0→100 치환이 안전하며, 정상값
    100/90 등은 그대로 둔다). 반환값은 치환한 0 필드 수.

    Returns:
        보정한 0 값 속성의 개수(0 이면 손댈 것 없음).
    """
    import zipfile, tempfile, os

    hwpx_path = Path(hwpx_path)
    # 원본 엔트리 메타(ZipInfo: 이름·순서·압축방식·플래그)를 그대로 보존해야
    # HWP 가 정상적으로 연다. 재압축/순서변경 시 HWP 가 복구 모드로 hang 한다.
    with zipfile.ZipFile(hwpx_path) as z:
        infos = z.infolist()
        hdr_info = next((i for i in infos if i.filename.endswith("header.xml")), None)
        if hdr_info is None:
            return 0
        contents = {i.filename: z.read(i.filename) for i in infos}

    hdr = contents[hdr_info.filename].decode("utf-8")
    count = 0

    def _bump(m: "re.Match") -> str:
        nonlocal count
        tag = m.group(0)
        count += tag.count('="0"')
        return tag.replace('="0"', '="100"')

    hdr = re.sub(r'<hh:ratio\b[^>]*/>', _bump, hdr)
    hdr = re.sub(r'<hh:relSz\b[^>]*/>', _bump, hdr)
    if count == 0:
        return 0
    contents[hdr_info.filename] = hdr.encode("utf-8")

    # 원본 ZipInfo 를 그대로 재사용해 같은 순서·같은 압축방식으로 재작성.
    fd, tmp = tempfile.mkstemp(suffix=".hwpx", dir=str(hwpx_path.parent))
    os.close(fd)
    with zipfile.ZipFile(tmp, "w") as zout:
        for info in infos:
            # ZipInfo 복제(압축방식·외부속성·플래그 유지), 내용만 교체
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type = info.compress_type
            zi.external_attr = info.external_attr
            zi.internal_attr = info.internal_attr
            zi.create_system = info.create_system
            zi.flag_bits = info.flag_bits
            zout.writestr(zi, contents[info.filename])
    os.replace(tmp, hwpx_path)
    return count


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
    # 저장 후 본문 글자모양의 장평/상대크기 0(투명) 보정 — 템플릿 상속으로
    # 본문이 안 보이는 문제 방지. COM 종료 뒤 XML 직접 패치(안전·결정적).
    try:
        _fix_invisible_charpr(output_path)
    except Exception:
        pass
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
