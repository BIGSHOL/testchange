from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ContentType(Enum):
    """콘텐츠 블록 유형."""
    TEXT = "text"
    EQUATION = "equation"          # 인라인 수식
    EQUATION_BLOCK = "equation_block"  # 블록(독립행) 수식
    IMAGE = "image"
    TABLE = "table"                # 표 (격자/그리드)


@dataclass
class ContentBlock:
    """문서 내 개별 콘텐츠 블록."""
    type: ContentType
    value: str  # TEXT: 텍스트, EQUATION/EQUATION_BLOCK: LaTeX, IMAGE: 파일경로
    hwp_equation: Optional[str] = None  # 변환된 HWP 수식 스크립트
    underline: bool = False  # 밑줄 강조 여부
    bold: bool = False  # 볼드 강조 여부(부정 선택문 "옳지 않은" 등의 부정어 — 밑줄과 함께)
    rows: Optional[list[list[str]]] = None  # TABLE: 2D 문자열 배열
    # 보기/조건/상자 박스 내부 블록인가(자기완결 raw 박스 블록의 인라인 분리 산물).
    # 렌더러가 박스 경계 뒤 '발문 연속'(#18·#20)을 박스 밖으로 빼는 데 쓴다(2026-06-08).
    box_member: bool = False

    @property
    def is_equation(self) -> bool:
        return self.type in (ContentType.EQUATION, ContentType.EQUATION_BLOCK)


@dataclass
class Choice:
    """선택지 (보기)."""
    number: int       # 1~5
    contents: list[ContentBlock] = field(default_factory=list)


@dataclass
class Question:
    """시험 문제 하나."""
    number: int
    score: Optional[int] = None
    contents: list[ContentBlock] = field(default_factory=list)   # 문제 본문
    choices: list[Choice] = field(default_factory=list)          # 선택지
    sub_questions: list[Question] = field(default_factory=list)  # 소문항
    # 서술형 라벨 유형(서답형/서술형/단답형 등). 원본에 따라 다르며 크롭/OCR 단계에서
    # 판별한다. 빈 값이면 폼 채움 시 기본값("서답형") 사용. choices 가 없으면 서술형 문항.
    label_type: str = ""
    # 정답·해설(웹 내보내기 정답페이지용, §44). 각각 *줄별 ContentBlock 런* 리스트(한 줄 =
    # 인라인 블록들). content_parser 가 마크다운/LaTeX 문자열을 파싱해 채운다($...$ 는
    # forward-split 으로 equation 블록 분리). 빈 리스트면 그 문항은 정답페이지에서 생략.
    answer: list[list[ContentBlock]] = field(default_factory=list)
    solution: list[list[ContentBlock]] = field(default_factory=list)


@dataclass
class ExamPage:
    """시험지 한 페이지."""
    page_number: int
    questions: list[Question] = field(default_factory=list)
    header_text: str = ""   # 페이지 상단 (과목명, 학년 등)


@dataclass
class ExamDocument:
    """전체 시험 문서."""
    title: str = ""
    subject: str = ""
    grade: str = ""
    pages: list[ExamPage] = field(default_factory=list)

    @property
    def all_questions(self) -> list[Question]:
        """모든 페이지의 문제 목록."""
        questions = []
        for page in self.pages:
            questions.extend(page.questions)
        return questions


def reorder_questions_by_number(questions: list[Question]) -> list[Question]:
    """검출된 인쇄 문항번호(`.number`)로 재정렬 — PDF 페이지가 뒤섞인 시험지 보정.

    크롭/OCR 은 인쇄된 문항번호를 정확히 읽지만(crops.json·merged.json 의 ``number``),
    렌더는 **페이지(파일) 순서대로** 미주 자동번호를 매기므로, PDF 페이지가 물리적으로
    뒤섞여 들어오면 최종 문항번호가 어긋난다(경상여고 대수 26-1-중간: p2=7~10·p3=11~13·
    p4=1~6·p5/p6=서답형, 사용자 보고 2026-06-18 — 최종본이 7,8,…,1,2,… 순으로 번호 부여).

    객관식(choices 있음)·서술형(choices 없음)을 **각 그룹 안에서** ``number`` 오름차순으로
    정렬한다(둘은 독립 번호계 — 객관식 1..N 먼저, 서술형 1..M 뒤; 폼 구조도 객관식 구역→
    서술형 구역). 안전장치: 그룹 내 번호가 **모두 양수이고 서로 다를 때만** 정렬한다 —
    번호 누락(0)·중복이면 신뢰할 수 없으므로 원순서를 유지해 정상 시험지를 오정렬하지
    않는다. 이미 정렬된(정상) 시험지는 결과가 동일하다(idempotent).
    """
    mc = [q for q in questions if q.choices]
    essays = [q for q in questions if not q.choices]

    def _sorted(group: list[Question]) -> list[Question]:
        nums = [q.number for q in group]
        if (group and all(isinstance(n, int) and n > 0 for n in nums)
                and len(set(nums)) == len(nums)):
            return sorted(group, key=lambda q: q.number)
        return group

    return _sorted(mc) + _sorted(essays)
