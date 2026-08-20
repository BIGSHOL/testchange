from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
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
    # 단원명(웹 showChapter 토글, §45). 있으면 본문 문항 위에 작은 라벨로 출력. 빈 값이면 생략.
    # 폼 경로에서는 [소단원]/[중단원] 메타란(흰 글자 = 인쇄 비표시 메타데이터) 값으로도 쓴다.
    topic: str = ""
    # 난이도(상/중/하) — 폼 [난이도] 메타란 값. 대수회 완료본 관례(2026-07-24 조사: 93편
    # 1944문항이 이 라벨을 채워 씀). 빈 값이면 메타란은 라벨만(기존 동작).
    difficulty: str = ""
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


def _raw_block_text(blocks) -> str:
    """raw 문항 dict 의 블록 리스트 → 평문(중첩 contents 포함). figure 는 제외."""
    out = []
    for b in blocks or []:
        if not isinstance(b, dict) or b.get("type") == "figure":
            continue
        v = b.get("value")
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, list):
            out.append(_raw_block_text(v))
    return "".join(out)


def _raw_question_text(q: dict) -> str:
    """발문 + 소문항 + 선택지 평문(빈 문항 판정용)."""
    parts = [_raw_block_text(q.get("contents"))]
    for sub in q.get("sub_questions") or []:
        if isinstance(sub, dict):
            parts.append(_raw_block_text(sub.get("contents")))
    for ch in q.get("choices") or []:
        if isinstance(ch, dict):
            parts.append(_raw_block_text(ch.get("contents")))
    return "".join(parts).strip()


_RAW_ESSAY_LABEL_RE = re.compile(r"[\[【]\s*(?:서술형|서답형|단답형)\s*\d*\s*[\]】]")


def drop_answer_key_questions(questions: list[dict]) -> tuple[list[dict], list[dict]]:
    """``(원본+답)`` PDF 의 **답지 페이지**가 문항으로 들어온 것을 걷어낸다.

    ⭐ 왜(대륜고 공수2 25-2-기말, 사용자 보고 2026-08-20): 문제지 뒤에 붙은 정답·해설
    2쪽까지 크롭·OCR 대상이 되어 봉투에 **28문항**(진짜 20 + 유령 8)이 실렸다. 유령은
    본문에 채점기준 조각을 문항으로 찍을 뿐 아니라, 서답형 수를 7→15 로 부풀려
    `hwp_form_writer._renumber_essay_labels` 의 오손상 방지 가드(라벨 수 ≠ 2×서답형수)를
    발동시켜 **정답면 라벨 재부여가 통째로 생략**됐다(정답 블록이 [서술형 5] 셋).

    크롭 프롬프트에도 ``class="answer"`` 룰을 넣었지만 그건 모델 판단이라 비결정적이다.
    이 함수는 **모델과 무관한 결정적 안전망**이고, 오검출로 진짜 문항을 지우지 않도록
    아래를 **전부** 만족하는 **뒤쪽 연속 구간**만 걷어낸다(답지는 항상 문제지 뒤에 온다):

      - 선택지가 없다(서답형 자리) — 객관식은 절대 대상이 아니다
      - 배점이 없다(``score`` falsy) — 진짜 서답형은 배점이 인쇄돼 있다
      - 문항번호가 **앞선 서답형 번호와 중복**이거나 번호가 없다 — 답지는 문제 번호를
        되풀이한다(유형별 독립 번호 시험지도 앞쪽에서 이미 그 번호를 썼으므로 안전)
      - 본문에 ``[서술형 N]``/``[단답형 N]`` 라벨이 없고 ``label_type`` 도 비었다 —
        진짜 서답형은 라벨이 인쇄되거나 OCR 이 유형을 확정해 준다

    마지막으로 **전체의 절반 이상**을 답지로 판정하면 그 판정을 통째로 버린다(안전 상한).

    추가로 **내용이 통째 빈 문항**(발문·선택지·소문항 텍스트 0자)은 위치와 무관하게
    걷어낸다 — 렌더하면 빈 슬롯만 남고 문항 수만 늘린다(정답표 페이지가 이 꼴로 온다).

    Returns: ``(남길 문항, 걷어낸 문항)``. 원본 리스트는 건드리지 않는다.
    """
    if not questions:
        return list(questions), []

    kept = [q for q in questions if isinstance(q, dict)]
    dropped: list[dict] = []

    # ① 빈 문항 — 위치 무관.
    empties = [q for q in kept if not _raw_question_text(q)]
    if empties:
        dropped.extend(empties)
        kept = [q for q in kept if _raw_question_text(q)]

    # ② 뒤쪽 답지 조각 연속 구간.
    cut = _answer_key_tail_start(
        [(bool(q.get("choices")), q.get("score"), q.get("number"),
          _raw_block_text(q.get("contents")), q.get("label_type") or "") for q in kept])
    if cut < len(kept):
        dropped.extend(kept[cut:])
        kept = kept[:cut]

    return kept, dropped


def is_answer_key_fragment(has_choices: bool, score, number, stem_text: str,
                           earlier_essay_nums: set, label_type: str = "") -> bool:
    """답지 조각 판정(원시 dict·Question 두 경로 공용). 판정 근거는
    :func:`drop_answer_key_questions` 문서 참고 — 전부 만족해야 한다."""
    if has_choices:
        return False
    if score:
        return False
    if (label_type or "").strip():
        return False          # OCR 이 서답형 유형을 확정한 문항 — 진짜 문제다
    if isinstance(number, int) and number > 0 and number not in earlier_essay_nums:
        return False
    if _RAW_ESSAY_LABEL_RE.search(stem_text or ""):
        return False
    return True


# 답지 판정이 이보다 많이 지우면 판정 자체가 틀린 것으로 본다(문제지를 통째 날리는 사고 방지).
_ANSWER_KEY_MAX_RATIO = 0.5


def _answer_key_tail_start(rows: list[tuple]) -> int:
    """``rows[i] = (has_choices, score, number, stem_text, label_type)`` → 답지 꼬리 시작."""
    cut = len(rows)
    while cut > 0:
        i = cut - 1
        earlier = {r[2] for r in rows[:i] if not r[0] and isinstance(r[2], int)}
        if not is_answer_key_fragment(rows[i][0], rows[i][1], rows[i][2], rows[i][3],
                                      earlier, rows[i][4] if len(rows[i]) > 4 else ""):
            break
        cut = i
    # ⚠️ 안전 상한 — 절반 이상을 답지로 판정하면 그 판정을 믿지 않는다. 배점이 통째로
    # 안 읽힌 시험지(스캔 불량)에서 문제지를 다 날리는 것보다, 유령 몇 개가 남는 편이 낫다.
    if rows and (len(rows) - cut) > len(rows) * _ANSWER_KEY_MAX_RATIO:
        return len(rows)
    return cut


def drop_answer_key_pages(pages: list) -> list:
    """파싱된 :class:`ExamPage` 리스트에서 답지 조각 문항을 걷어낸다(GUI/exe 경로).

    웹(`server/convert_cli`)은 파싱 **전** 원시 봉투에서 걷어내지만, GUI 는 페이지별로
    파싱하므로 여기서 **페이지를 가로질러** 같은 규칙을 적용한다(답지는 마지막 페이지에
    오므로 페이지 단위로는 "앞선 서답형 번호"를 볼 수 없다). Returns: 걷어낸 문항 리스트.
    """
    flat = [(p, q) for p in pages for q in p.questions]
    if not flat:
        return []

    def _text(q) -> str:
        # 파서가 figure 를 이미 드롭하므로 남은 블록의 **문자열 값**만 이으면 된다
        # (TABLE 블록의 value 는 행 리스트라 제외).
        return "".join(b.value for b in (q.contents or []) if isinstance(b.value, str))

    cut = _answer_key_tail_start(
        [(bool(q.choices), q.score, q.number, _text(q), getattr(q, "label_type", ""))
         for _, q in flat])
    dropped = [q for _, q in flat[cut:]]
    if dropped:
        drop_ids = {id(q) for q in dropped}
        for p in pages:
            p.questions = [q for q in p.questions if id(q) not in drop_ids]
    return dropped


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
