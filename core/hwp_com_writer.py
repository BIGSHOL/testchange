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

from core.hwp_com import CONVERSION_VISIBLE, HwpSession, CIRCLE_NUMBERS
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
# 보기 항목 라벨(ㄱ. ㄴ. …) 뒤에 공백이 없으면("ㅁ.0") 한 칸 띄운다("ㅁ. 0"). (A6)
_LABEL_SPACE_RE = re.compile(r"^([ㄱ-ㅎ가-힣]\s*\.)\s*(\S)")
# 라벨 없는 '그냥 테두리 박스' 마커(표시 안 함, 박스만 생성) — #1처럼 보기/조건이 아닌
# 박스(수식·조건문 등)나 서술형 지문 박스용. `<조건>`/`<보기>` 와 달리 **셀에 글자를 안 찍고**
# 1×1 표만 만든다(사용자 결정 2026-06-08: 원본에 라벨이 있을 때만 라벨 표기).
_PLAIN_BOX_MARK = "<상자>"
_PLAIN_BOX_RE = re.compile(r"<\s*상자\s*>")
# 보기/조건 박스 '머리'(블록 시작이 <보기>/<조건>/<상자>) — 발문 끝 배점 위치 판정용(A2).
# 발문이 "<보기>에서…"처럼 마커로 시작해도 그건 인라인 참조다(뒤에 조사=가-힣 음절) → 부정 전망.
# 단 `<상자>`(라벨 없는 박스)는 뒤에 한글 지문이 와도 항상 박스 머리다(부정 전망 없음).
_COND_HEADER_RE = re.compile(
    r"^\s*(?:<\s*상자\s*>|(?:<\s*조건\s*>|<\s*보기\s*>|\[\s*조건\s*\]|\[\s*보기\s*\])(?!\s*[가-힣]))")
# 박스 내부 줄 경계: 마커(<보기>/<조건>/<상자>) 또는 항목 라벨(ㄱ. ㄴ. …, 앞이 공백/시작). 표 셀
# 안에서 마커는 자기 줄, 각 항목은 새 줄로 나누는 데 쓴다(A3/A5). (B3-2 라벨 뒤 공백은 token+공백.)
# 항목 라벨: ㄱ. ㄴ. … 또는 (가)(나)(다)… 한글 괄호 열거(조건 박스 줄나눔, #12 2026-06-08).
_KO_ENUM = r"\(\s*[가나다라마바사아자차카타파하]\s*\)"
_BOX_BOUNDARY_RE = re.compile(
    r"(<\s*상자\s*>|<\s*조건\s*>|<\s*보기\s*>|\[\s*조건\s*\]|\[\s*보기\s*\]"
    r"|(?:(?<=\s)|^)[ㄱ-ㅎ]\s*\.|" + _KO_ENUM + r")")
# 박스 줄 경계(확장): 불릿(•)도 경계로 — 불릿·<상자>는 줄바꿈만(토큰 미출력, A4), 숫자 항목
# (1. 2. 3.)은 라벨 정규식에 없으므로 불릿이 그 줄바꿈을 담당한다.
_BOX_BREAK_RE = re.compile(
    r"(\s*[•·▪◦]\s*|<\s*상자\s*>|<\s*조건\s*>|<\s*보기\s*>|\[\s*조건\s*\]|\[\s*보기\s*\]"
    r"|(?:(?<=\s)|^)[ㄱ-ㅎ]\s*\.|" + _KO_ENUM + r")")


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
    - 불릿(•) → 항목 분리자로만(독립 줄), 출력엔 • 미부착 (A4)
    - 항목 라벨(ㄱ. …) 뒤 공백 보정 (A6)
    """
    t = _DASH_RUN_RE.sub("\n", text)
    t = _COND_MARKER_RE.sub(lambda m: "\n" + re.sub(r"\s+", "", m.group(1)) + "\n", t)
    t = _BULLET_RE.sub("\n", t)   # 불릿(•)은 항목 분리자로만 쓰고 출력엔 붙이지 않는다 (A4)
    lines = [ln.strip() for ln in t.split("\n")]
    # 라벨 뒤 공백 보정("ㅁ.0"→"ㅁ. 0") (A6)
    return [_LABEL_SPACE_RE.sub(r"\1 \2", ln) for ln in lines if ln]


def _condition_start(blocks: list[ContentBlock]) -> int | None:
    """발문이 끝나고 보기/조건 박스(또는 표)가 시작되는 contents 인덱스. 없으면 None.

    배점을 '발문 끝'(보기/조건·표 앞)에 두기 위한 경계(A2). 보기/조건 박스는
    블록 시작이 <보기>/<조건> 머리이거나, OCR이 표(table)로 준 경우다.
    """
    for i, b in enumerate(blocks):
        if b.type == ContentType.TABLE:
            return i
        if b.type == ContentType.TEXT and _COND_HEADER_RE.search(b.value or ""):
            return i
    return None


def _tail_start(blocks: list[ContentBlock]) -> int | None:
    """발문이 끝나고 '뒤 영역'(조건/보기 박스·표·그림·블록수식)이 시작되는 인덱스.

    배점은 이 경계 **앞**(발문 끝)에 둔다. 폼·기본 경로 공통 경계(사용자 '항상 동일'
    요구 2026-06-05).

    경계 판정(2026-06-05 개정 — 발문 중간 블록수식/그림 오인 방지):
    - **조건/보기 머리(TEXT) 또는 표(TABLE)** 가 나오면 거기서부터 뒤 영역(1순위).
      (보기 박스가 시작되면 그 뒤는 전부 박스 내용.)
    - **그림(IMAGE)·블록수식(EQUATION_BLOCK)** 은 *발문 끝의 독립 표시*일 때만 경계로
      본다 = **끝에서부터 이어지는 IMAGE/EQUATION_BLOCK 연속 run** 의 시작. 문장 중간에
      박힌 블록수식(예: "연립방정식 {…} 의 풀이에 대한 …")은 뒤에 발문 TEXT 가 더
      이어지므로 경계가 **아니다**(과거: 첫 블록수식에서 끊겨 배점이 발문 첫 단어 뒤로
      튀고 블록이 문장 중간에서 가운데정렬됨 — 사용자 보고 4·16번).
    """
    # 1순위: 조건/보기 머리 또는 표 — 진짜 발문뒤 영역 시작.
    for i, b in enumerate(blocks):
        if b.type == ContentType.TABLE:
            return i
        if b.type == ContentType.TEXT and _COND_HEADER_RE.search(b.value or ""):
            return i
    # 2순위: 끝에 매달린 그림/블록수식 연속 run 의 시작(문장 중간 블록은 제외).
    i = len(blocks)
    while i > 0 and blocks[i - 1].type in (ContentType.IMAGE, ContentType.EQUATION_BLOCK):
        i -= 1
    return i if i < len(blocks) else None


# 발문 끝에 박힌 총점/배점 [총 N점]·[N점] (소문항 부모는 우측정렬로 따로 표기).
_TRAIL_SCORE_RE = re.compile(r'\s*\[\s*(?:총\s*)?(\d+)\s*점\s*\]\s*$')
_OPEN_SCORE_RE = re.compile(r'\[\s*(?:총\s*)?$')   # 텍스트 끝이 "[" 또는 "[총"
_CLOSE_SCORE_RE = re.compile(r'^\s*점\s*\]')        # 텍스트 시작이 "점]"


def _split_trailing_score(blocks: list[ContentBlock]):
    """발문 끝의 ``[총 N점]``/``[N점]`` 을 떼어낸다(한 블록 안이든, 숫자가 수식 객체로
    쪼개져 ``TEXT "[총 " + EQ "N" + TEXT "점]"`` 든).

    소문항 부모의 총점을 발문 본문에서 빼내 **우측정렬**로 따로 렌더하기 위함
    (사용자 2026-06-05). Returns: (떼어낸 뒤 blocks, N|None).
    """
    # (1) 한 텍스트 블록 안에 통째로 [총 N점].
    for i in range(len(blocks) - 1, -1, -1):
        b = blocks[i]
        if b.type == ContentType.TEXT and (b.value or "").strip():
            m = _TRAIL_SCORE_RE.search(b.value)
            if m:
                num = int(m.group(1))
                nv = b.value[:m.start()].rstrip()
                cleaned = list(blocks)
                if nv:
                    cleaned[i] = ContentBlock(type=ContentType.TEXT, value=nv)
                else:
                    cleaned.pop(i)
                return cleaned, num
            break   # 마지막 비어있지 않은 텍스트 → 단일 매칭 실패 시 (2) 쪼개진 경우로
    # (2) 숫자가 수식 객체화돼 쪼개진 경우: 끝 3블록 = TEXT "[총 " + EQ(숫자) + TEXT "점]".
    if len(blocks) >= 3:
        t1, eq, t2 = blocks[-3], blocks[-2], blocks[-1]
        if (t1.type == ContentType.TEXT and t2.type == ContentType.TEXT
                and eq.type in (ContentType.EQUATION, ContentType.EQUATION_BLOCK)
                and (eq.value or "").strip().isdigit()
                and _OPEN_SCORE_RE.search(t1.value or "")
                and _CLOSE_SCORE_RE.match(t2.value or "")):
            num = int(eq.value.strip())
            nv1 = _OPEN_SCORE_RE.sub("", t1.value or "").rstrip()
            nv2 = _CLOSE_SCORE_RE.sub("", t2.value or "").lstrip()
            cleaned = list(blocks[:-3])
            if nv1:
                cleaned.append(ContentBlock(type=ContentType.TEXT, value=nv1))
            if nv2:
                cleaned.append(ContentBlock(type=ContentType.TEXT, value=nv2))
            return cleaned, num
    return blocks, None


def _choice_complexity(choice: Choice) -> int:
    """보기 하나의 '길이' 추정. 블록수식/표가 있으면 매우 큼(→1단)."""
    score = 0
    for b in choice.contents:
        if b.type in (ContentType.TABLE, ContentType.EQUATION_BLOCK, ContentType.IMAGE):
            return 999
        score += len(b.value or "")
    return score


def _choice_columns(choices: list[Choice]) -> int:
    """보기 배치 단 수(1~2)를 보기 길이로 자동 결정.

    짧은 보기는 항상 2열(①②/③④/⑤ — 5지선다면 2열 3행), 길면 한 줄당 하나.
    (사용자 요구 2026-06-02: 짧은 보기는 항상 2열 3행. 탭으로 줄맞춤.)
    """
    if not choices:
        return 1
    maxc = max(_choice_complexity(c) for c in choices)
    if maxc >= 18:
        return 1
    # 짧음/중간: 항상 2열
    return 2


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
        # 문항번호를 미주 자동번호로(A1). 미주 삽입이 한 번이라도 실패하면 False 로 떨궈
        # 이후 문항은 텍스트 번호로(반복 실패·문서 깨짐 방지).
        self._use_endnote = True

    # ── 콘텐츠 블록 ────────────────────────────────────────
    def _write_block(self, block: ContentBlock, inline: bool = False) -> None:
        # 모든 수식(EQUATION/EQUATION_BLOCK)은 수식 객체로 삽입한다 — 순수 숫자도 포함(A8:
        # "200" 등 모든 숫자·문자 수식화). 과거엔 숫자 전용 수식이 베이스라인 메트릭 stale 로
        # 줄 위로 떠올라 텍스트로 강등했으나, 수식 확정(version-stamp, 2026-06-02) 이후 해소됐다.
        # 수식 객체가 든 단락은 고정 탭(7cm)에도 정상 재계산되어 보기 정렬에도 유리하다.
        # inline=True: EQUATION_BLOCK 도 줄바꿈 없이 인라인 — 번호-발문 같은 줄(A7)·보기 항목(A5).
        if block.type == ContentType.TABLE:
            # 표는 자체 단락 필요 — 앞 단락과 분리
            self.s.break_para()
            self._write_equation_table(block.rows or [])
        elif block.type == ContentType.EQUATION_BLOCK:
            if not inline:
                self.s.break_para()
                self.s.align_center()   # 발문 아래 독립 블록수식은 가운데 정렬(사용자 2026-06-05)
            self.s.equation(_eq_script(block))
            # 좌측 복귀는 소비처(조건 박스·선택지)에서 — 연속 블록수식은 가운데 유지(빈 줄 없음)
        elif block.type == ContentType.EQUATION:
            self.s.equation(_eq_script(block))
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

    def _write_equation_table(self, rows: list[list[str]]) -> None:
        """표를 만들고 각 셀을 **수식 객체**로 채운다.

        OCR 표(rows)는 LaTeX 문자열(예: "x", "f(x)", "-1", "\\frac{1}{2}")이라,
        수학 표는 셀도 수식으로 렌더해야 본문 수식과 글꼴·기울임이 일치한다(사용자
        요구 2026-06-04: 표 안 값이 일반 텍스트로 들어가면 안 됨). 빈 셀은 비운다.
        """
        if not rows:
            return
        nrow = len(rows)
        ncol = max((len(r) for r in rows), default=0)
        if ncol == 0:
            return
        self.s.table_begin(nrow, ncol)
        for ri in range(nrow):
            row = rows[ri]
            for ci in range(ncol):
                self.s.align_center()        # 셀 값 가운데 정렬(사용자 요구 2026-06-04)
                val = str(row[ci]).strip() if ci < len(row) else ""
                if val:
                    self.s.equation(latex_to_hwpeq(val))
                if not (ri == nrow - 1 and ci == ncol - 1):
                    self.s.table_next_cell()
        self.s.table_end()
        self.s.align_left()                  # 표 뒤 본문은 좌측 정렬 복귀

    def _write_segmented_text(self, text: str) -> None:
        """조건/보기 박스 텍스트를 줄 단위로 분리해 출력.

        OCR이 박스를 한 줄로 흘려 "−−<조건>−−• A• B• C" 처럼 뭉쳐 들어오면
        <조건>·각 불릿(•)을 개별 줄로 분리한다.
        """
        lines = _segment_box_text(text)
        for line in lines:
            self.s.break_para()  # 박스 각 줄은 새 줄에서 시작(앞 문장과 분리)
            self.s.text(line)

    def _write_box_content(self, blocks: list[ContentBlock]) -> None:
        """보기/조건 박스 '내부'를 줄 단위로 출력(표 셀 안에서 호출).

        마커(<보기>)는 자기 줄, 각 항목 라벨(ㄱ. …)은 새 줄로 나눈다(A5). 수식 블록은
        항목 줄 안에 인라인으로 유지(A8). 항목 라벨 뒤엔 공백 1칸(A6).
        """
        started = False
        # `emitted` = 셀에 **실제 보이는 내용**(텍스트/마커/수식/그림)을 한 번이라도 찍었는가.
        # 줄바꿈(break_para)은 emitted 일 때만 — 빈 셀 첫 단락에 아무것도 안 쓴 채 줄을 끊으면
        # **선두 빈 단락**이 생긴다(<상자>•수식 처럼 숨은 마커 직후 불릿이 break 를 부르던 버그.
        # 사용자 2026-06-08: 상자 내용이 둘째 줄부터 시작). started(공백 lstrip 판정)와 분리.
        emitted = False

        def emit_text(text: str) -> None:
            nonlocal started, emitted
            pos = 0
            broke = False   # 직전이 빈 경계 줄바꿈이면 중복 줄바꿈 방지(불릿+라벨 인접)
            after_label = False  # 라벨 직후면 뒤 내용 선행공백 strip(이중공백 방지, 2026-06-05)
            for m in _BOX_BREAK_RE.finditer(text):
                pre = text[pos:m.start()]
                if pre.strip():
                    seg = pre if started else pre.lstrip()
                    if after_label:
                        seg = seg.lstrip()   # "ㄱ. " + " 내용" → "ㄱ. 내용"(한 칸)
                    self.s.text(seg)
                    started = True
                    emitted = True
                    broke = False
                    after_label = False
                tok = re.sub(r"\s+", "", m.group(0))   # "ㄱ ." → "ㄱ.", "< 보기 >" → "<보기>"
                # 불릿(•)·<상자>(라벨 없는 박스)는 줄 경계로만 쓰고 **출력 안 함**(A4).
                is_hidden = (_BULLET_RE.fullmatch(m.group(0)) is not None) or tok == _PLAIN_BOX_MARK
                if emitted and not broke:
                    self.s.break_para()   # 마커/항목 라벨/불릿 앞에서 줄바꿈(보인 내용 있을 때만)
                    broke = True
                if not is_hidden:
                    # 표시 마커/라벨 출력(<조건>/<보기>/ㄱ. 등)
                    self.s.text(tok + " ")                 # 라벨/마커 뒤 공백(A6)
                    emitted = True
                    broke = False
                    after_label = True
                    # <보기>/<조건> 박스 라벨은 **자기 단락 단독**으로 끊는다 — 5×5 폼 주입
                    # (`_inject_bogi_form`)이 para0=라벨, para1+=내용으로 분리하므로, 라벨과
                    # 첫 내용(가)이 같은 단락이면 라벨셀에 내용이 끼어 좁은 셀에서 잘린다
                    # (#12 f(x) 누락, 2026-06-08). 항목 라벨(ㄱ.)은 해당 안 됨.
                    if _BOGI_LABEL_TEXT_RE.match(tok):
                        self.s.break_para()
                        broke = True
                        after_label = False
                elif tok == _PLAIN_BOX_MARK:
                    after_label = True   # <상자> 뒤 내용 선행 공백 제거(셀 내용 깔끔히)
                started = True
                pos = m.end()
            tail = text[pos:]
            if tail.strip():
                seg = tail if started else tail.lstrip()
                if after_label:
                    seg = seg.lstrip()
                self.s.text(seg)
                started = True
                emitted = True

        for block in blocks:
            if block.type == ContentType.TEXT:
                emit_text(block.value or "")
            elif block.type in (ContentType.EQUATION, ContentType.EQUATION_BLOCK):
                self.s.equation(_eq_script(block))   # 항목 줄 안 인라인 수식
                started = True
                emitted = True
            elif block.type == ContentType.IMAGE and block.value:
                if emitted:
                    self.s.break_para()   # 보인 내용 뒤에서만 줄바꿈(선두 빈 줄 방지)
                self.s.align_center()
                self.s.insert_picture(block.value)
                self.s.break_para()
                self.s.align_left()
                started = True
                emitted = True

    def _write_condition_box(self, blocks: list[ContentBlock]) -> None:
        """보기/조건 블록들을 1×1 테두리 표(박스) 안에 줄 단위로 렌더한다(A3)."""
        # 표(데이터 표: 확률분포표·정규분포표)와 조건/보기(<상자>/<조건>/<보기>) 박스가
        # **섞여** 오면: 표는 표로, 조건 머리부터는 박스로 **분리** 렌더한다. 과거엔 표가
        # 하나라도 있으면 전부 평문(_write_block)으로 흘려 <상자> 조건이 literal 텍스트로
        # 새고 수식이 객체화 안 됐다(학남고 확통 #18 — z-표 뒤 (가)(나) 조건, 2026-06-08).
        if any(b.type == ContentType.TABLE for b in blocks):
            ci = next((i for i, b in enumerate(blocks)
                       if b.type == ContentType.TEXT
                       and _COND_HEADER_RE.search(b.value or "")), None)
            if ci is None:
                for b in blocks:           # 조건 머리 없음 → 표/블록만 그대로
                    self._write_block(b)
                return
            for b in blocks[:ci]:          # 조건 머리 앞(표 등)은 개별 렌더
                self._write_block(b)
            self._write_condition_box(blocks[ci:])   # 조건부터는 박스(재귀, 이제 표 없음)
            return
        # 단락 시작(pos==0, 예: 그림 뒤 빈 단락)이면 추가 줄바꿈 없이 그 단락을 재사용
        # → 그림↔조건 사이 빈 줄 방지(사용자 2026-06-05). 아니면 새 줄로.
        try:
            at_para_start = self.s.hwp.GetPos()[2] == 0
        except Exception:
            at_para_start = False
        if not at_para_start:
            self.s.break_para()
        self.s.align_left()             # 직전 블록수식/그림 가운데정렬 해제(표는 좌측)
        self.s.table_begin(1, 1)        # 한 칸 테두리 박스
        self._write_box_content(blocks)
        self.s.table_end()
        self.s.align_left()

    def _write_tail(self, tail: list[ContentBlock]) -> bool:
        """발문 뒤 영역 렌더(**폼·기본 경로 공통** — 사용자 '항상 동일' 요구 2026-06-05).

        그림(IMAGE)·블록수식(EQUATION_BLOCK)은 개별 렌더(그림 가운데·수식 가운데),
        보기/조건(<보기>/<조건> 머리 이후)은 1×1 테두리 표 박스로. 그림↔조건 사이 빈 줄은
        `_write_condition_box` 가 단락시작(pos==0) 재사용으로 방지.

        Returns: 표 박스로 끝났는지(True면 트레일링 단락이 이미 새 줄이라 추가 줄바꿈 불필요).
        """
        cs = _condition_start(tail)               # 표/조건 머리 시작(없으면 전부 pre)
        pre = tail if cs is None else tail[:cs]
        box = [] if cs is None else tail[cs:]
        for b in pre:
            self._write_block(b)                  # IMAGE 가운데·EQUATION_BLOCK 가운데(인라인 아님)
        if box:
            self._write_condition_box(box)
            return True
        return False

    # ── 문제 ──────────────────────────────────────────────
    def _write_question(self, question: Question, top_level: bool = True) -> None:
        is_essay = not question.choices
        has_subs = bool(question.sub_questions)
        # 소문항이 있는 부모는 배점이 '총점'이라 본문에 "[총 N점]"으로 이미 표기됨.
        # 인라인 배점([N점])을 또 찍으면 중복 → 부모는 인라인 배점 생략, 소문항만 표기.
        show_score = bool(question.score) and not has_subs

        # 번호(A1): 주문항은 미주 자동번호("1." 스타일, 12pt 볼드). 미주 마크의 번호 형식
        # "1." 의 마침표는 suffix(저장 후 XML 후처리)에서 오므로, 성공 시 마크 뒤엔 공백만.
        # 실패하면 텍스트 번호로 폴백 + 이후 문항도 텍스트(self._use_endnote=False).
        if top_level and self._use_endnote and self.s.endnote():
            self.s.text(" ")
        else:
            if top_level and self._use_endnote:
                self._use_endnote = False
            self.s.text(f"{question.number}. ")

        # 발문 / 뒤 영역(조건·표·그림·블록수식) 경계(A2/A3). 배점은 '발문 끝'(경계 앞)에 둔다.
        tail_start = _tail_start(question.contents)
        stem = question.contents if tail_start is None else question.contents[:tail_start]
        tail = [] if tail_start is None else question.contents[tail_start:]

        # 소문항 부모: 발문 끝 [총 N점] 을 본문에서 분리해 우측정렬로 따로 표기(사용자 2026-06-05).
        total_num = None
        if has_subs:
            stem, total_num = _split_trailing_score(stem)
            if total_num is None:
                total_num = question.score

        # 발문 — 첫 블록은 인라인(번호와 같은 줄), 발문 선두 수식 줄바꿈 방지(A7).
        for i, block in enumerate(stem):
            self._write_block(block, inline=(i == 0))
        # 배점 — 객관식은 발문 끝 인라인. 서술형은 줄바꿈 후 우측정렬(사용자 합의 2026-06-04).
        if show_score:
            if is_essay:
                self.s.break_para()
                self.s.align_right()
                self._write_score(question.score, leading_space=False)
                self.s.break_para()
                self.s.align_left()
            else:
                self._write_score(question.score)
        elif has_subs and total_num:
            # 소문항 부모 총점: 줄바꿈 후 우측정렬 "[총 N점]"(N 은 수식 객체).
            self.s.break_para()
            self.s.align_right()
            self.s.text("[총 ")
            self.s.equation(str(total_num))
            self.s.text("점]")
            self.s.break_para()
            self.s.align_left()
        # 뒤 영역: 그림/블록수식은 개별(가운데), 보기/조건은 1×1 테두리 표 박스 (A3)
        if tail:
            ended_box = self._write_tail(tail)
            # 박스(표) 뒤 트레일링 단락이 이미 새 줄 → 선택지 사이 빈 줄 없음(사용자 2026-06-04).
            # 박스로 안 끝났으면(그림/블록수식) 선택지 전에 좌측 새 줄 확보.
            if question.choices and not ended_box:
                self.s.break_para()
                self.s.align_left()
        else:
            self.s.break_para()

        # 보기 — 길이에 따라 1~5단 배치(짧으면 여러 단을 한 줄에, 길면 한 줄당 하나)
        if question.choices:
            cols = _choice_columns(question.choices)
            last = len(question.choices) - 1
            for i, choice in enumerate(question.choices):
                # 2열 배치일 때만 보기 내용을 수식 객체로(텍스트 단락은 \t 탭이 7cm
                # 고정정지점으로 재계산되지 않아 2열이 안 맞음 — 수식 든 단락은 재계산됨).
                self._write_choice(choice, as_equation=(cols == 2))
                if i % cols == cols - 1 or i == last:
                    self.s.break_para()
                else:
                    self.s.text("\t")

        # 소문항 재귀 (소문항 번호는 미주 아님)
        for sub in question.sub_questions:
            self._write_question(sub, top_level=False)

        # 서술형 '풀이)' 답안 공간은 넣지 않는다(사용자 요구 2026-06-02): 배점에서 끝낸다.

        # 문제 간 빈 줄
        self.s.break_para()

    def _write_choice(self, choice: Choice, as_equation: bool = False) -> None:
        # 선택지는 들여쓰기 없이 좌측에 붙인다(사용자 요구 2026-06-02).
        circle = CIRCLE_NUMBERS.get(choice.number, f"({choice.number})")
        self.s.text(f"{circle} ")
        for block in choice.contents:
            # 2열 정렬(as_equation): TEXT 도 수식 객체로 삽입해 단락을 재계산시킨다
            # → \t 가 7cm 고정탭에 정렬돼 ②④ 가 같은 열에 선다. (이미 수식/표면 그대로)
            if as_equation and block.type == ContentType.TEXT and (block.value or "").strip():
                self.s.equation(latex_to_hwpeq(block.value))
            else:
                self._write_block(block)

    def _write_score(self, score: int, leading_space: bool = True) -> None:
        # 배점 숫자도 수식 객체로(A8). "[" "점]"는 텍스트.
        self.s.text(" [" if leading_space else "[")
        self.s.equation(str(score))
        self.s.text("점]")

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


# 보기 2열 배치의 두 번째 열 시작 위치(HWPUNIT). 7cm ≈ 19842 (1cm=2834.6).
# 본문 탭(`\t`)은 보기 열 구분에만 쓰이므로, 모든 tabPr에 이 고정 좌측 탭을 주입하면
# 보기 ②④가 첫 열 내용 폭(수식 객체 포함)과 무관하게 항상 같은 x에서 정렬된다.
# COM ParagraphShape 로는 TabDef 가 문서에 커밋되지 않으므로(검증: tabItem 미저장)
# 저장 후 header.xml 을 직접 패치한다([[hwp-com-layout-limits]] 회피책).
_CHOICE_COL2_HWPUNIT = 19842


def _inject_choice_tabstop(hwpx_path: str | Path, pos: int = _CHOICE_COL2_HWPUNIT) -> int:
    """저장된 .hwpx 의 header.xml tabPr 에 고정 좌측 탭 정지점을 주입한다.

    자기닫음 ``<hh:tabPr …/>`` 만 대상(이미 자식 tabItem 이 있는 커스텀 탭은 건드리지
    않음). 문서 내 탭은 보기 2열 구분용뿐이라, 단일 좌측 탭 정지점이면 모든 보기의
    둘째 열이 같은 위치에서 정렬된다.

    Returns:
        주입한 tabPr 개수(0 이면 손댈 것 없음).
    """
    import zipfile, tempfile, os

    hwpx_path = Path(hwpx_path)
    with zipfile.ZipFile(hwpx_path) as z:
        infos = z.infolist()
        hdr_info = next((i for i in infos if i.filename.endswith("header.xml")), None)
        if hdr_info is None:
            return 0
        contents = {i.filename: z.read(i.filename) for i in infos}

    hdr = contents[hdr_info.filename].decode("utf-8")
    item = f'<hh:tabItem pos="{pos}" type="LEFT" leader="NONE"/>'

    def _add_item(m: "re.Match") -> str:
        tag = m.group(0)
        # 자동탭(autoTabLeft/Right)을 끈다 — 켜져 있으면 기본 자동탭이 고정탭보다
        # 먼저 잡혀(짧은 텍스트 보기에서 둘째 열이 덜 정렬됨) 7cm 고정 정렬이 깨진다.
        tag = re.sub(r'autoTabLeft="\d+"', 'autoTabLeft="0"', tag)
        tag = re.sub(r'autoTabRight="\d+"', 'autoTabRight="0"', tag)
        # 자기닫음 `…/>` → `…>{item}</hh:tabPr>`
        return tag[:-2] + ">" + item + "</hh:tabPr>"

    hdr, count = re.subn(r'<hh:tabPr\b[^>]*/>', _add_item, hdr)
    if count == 0:
        return 0
    contents[hdr_info.filename] = hdr.encode("utf-8")

    # 원본 ZipInfo 를 그대로 재사용해 같은 순서·같은 압축방식으로 재작성.
    fd, tmp = tempfile.mkstemp(suffix=".hwpx", dir=str(hwpx_path.parent))
    os.close(fd)
    with zipfile.ZipFile(tmp, "w") as zout:
        for info in infos:
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
    # 빌드는 숨김(빠름)이 기본이나, 실시간 작성 표시 옵션(CONVERSION_VISIBLE)이면 보이게 띄운다.
    with HwpSession(visible=CONVERSION_VISIBLE) as s:
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
    # 보기 2열 정렬: header.xml tabPr 에 고정 좌측 탭 주입(COM 미커밋 회피책).
    try:
        _inject_choice_tabstop(output_path)
    except Exception:
        pass
    # 미주(문항번호) 번호 형식 "1)" → "1." : 저장 후 section XML 의 autoNumFormat
    # suffixChar 패치(COM EndnoteShape 는 캐럿 부작용·인코딩 불확실 → XML 결정적).
    try:
        _set_endnote_suffix(output_path)
    except Exception:
        pass
    # <보기>/<조건> 라벨 1×1 박스 → 5×5 병합표 폼(레퍼런스와 픽셀 동일). <상자>·일반표 제외.
    try:
        _inject_bogi_form(output_path)
    except Exception:
        pass
    # 확률분포표 1열·표준정규분포표 최상단 행에 #D9D9D9 음영(수기본 통일).
    try:
        _inject_table_shading(output_path)
    except Exception:
        pass
    return output_path


def _set_endnote_suffix(hwpx_path: str | Path, suffix: str = ".") -> int:
    """저장된 .hwpx section XML 의 미주/각주 번호 suffixChar 를 ``)`` → ``suffix`` 로.

    문항번호를 미주 자동번호로 쓰는데(A1), 폼 스타일은 "1." 형식이라 기본 ")" 를 "." 로
    바꾼다(본문 마크·답란 번호 모두 이 형식을 따른다). ``<hp:autoNumFormat … suffixChar=")"``
    만 대상(이미 다른 suffix 면 건드리지 않음).

    Returns:
        패치한 autoNumFormat 개수.
    """
    import zipfile, tempfile, os

    hwpx_path = Path(hwpx_path)
    with zipfile.ZipFile(hwpx_path) as z:
        infos = z.infolist()
        contents = {i.filename: z.read(i.filename) for i in infos}

    count = 0
    pat = re.compile(r'(<hp:autoNumFormat\b[^>]*?suffixChar=")\)(")')
    for fn in list(contents):
        if not (fn.endswith(".xml") and "section" in fn.lower()):
            continue
        text = contents[fn].decode("utf-8")
        new, n = pat.subn(lambda m: m.group(1) + suffix + m.group(2), text)
        if n:
            contents[fn] = new.encode("utf-8")
            count += n
    if not count:
        return 0

    tmp = str(hwpx_path) + ".tmp"
    with zipfile.ZipFile(tmp, "w") as zout:
        for info in infos:
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type = info.compress_type
            zi.external_attr = info.external_attr
            zi.internal_attr = info.internal_attr
            zi.create_system = info.create_system
            zi.flag_bits = info.flag_bits
            zout.writestr(zi, contents[info.filename])
    os.replace(tmp, hwpx_path)
    return count


# ── 보기/조건 라벨 박스 → 5×5 병합표 폼 주입 ───────────────────────
def _tbl_balanced(s: str, start: int, tag: str = "hp:tbl") -> tuple[str, int]:
    """``start`` 의 여는 태그부터 **중첩을 고려해** 닫는 태그까지 균형 추출.

    Returns: (segment, end_index). 못 찾으면 ("", -1).
    """
    close = "</%s>" % tag
    tok = re.compile(re.escape("<" + tag) + r"\b|" + re.escape(close))
    depth = 0
    for m in tok.finditer(s, start):
        if m.group().startswith("</"):
            depth -= 1
            if depth == 0:
                return s[start:m.end()], m.end()
        else:
            depth += 1
    return "", -1


# 셀 subList(라벨/내용)용 — paraPrIDRef/charPrIDRef 는 호출측이 주입(라벨은 가운데 paraPr).
_BOGI_SUBLIST_HEAD = (
    '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" '
    'linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" '
    'hasTextRef="0" hasNumRef="0">'
)


def _bogi_center_parapr_id(header_xml: str) -> str:
    """헤더에서 가운데 정렬 paraPr id 를 찾는다(없으면 "0")."""
    for pm in re.finditer(r'<hh:paraPr\b[^>]*\bid="(\d+)".*?</hh:paraPr>', header_xml, re.S):
        al = re.search(r'<hh:align\b[^>]*horizontal="(\w+)"', pm.group(0))
        if al and al.group(1) == "CENTER":
            return pm.group(1)
    return "0"


def _wrap_subList(paras: list[str]) -> str:
    """``<hp:p>…</hp:p>`` 단락 리스트를 하나의 ``<hp:subList>`` 로 감싼다."""
    if not paras:
        paras = [
            '<hp:p id="0" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" '
            'merged="0"><hp:run charPrIDRef="0"/><hp:linesegarray><hp:lineseg textpos="0" '
            'vertpos="0" vertsize="1000" textheight="1000" baseline="850" spacing="600" '
            'horzpos="0" horzsize="100" flags="393216"/></hp:linesegarray></hp:p>'
        ]
    return _BOGI_SUBLIST_HEAD + "".join(paras) + "</hp:subList>"


def _set_para_align(para_xml: str, parapr_id: str) -> str:
    """단락의 paraPrIDRef 를 ``parapr_id`` 로 바꾼다(가운데정렬 적용)."""
    return re.sub(r'(<hp:p\b[^>]*\bparaPrIDRef=")\d+(")',
                  lambda m: m.group(1) + parapr_id + m.group(2), para_xml, count=1)


def _extract_cell_paras(tbl_xml: str) -> list[str]:
    """1×1 표 셀 subList 안의 ``<hp:p>…</hp:p>`` 단락들을 순서대로 반환."""
    # 셀 subList 안만 대상(표 자체엔 subList 가 셀 하나뿐).
    sub_start = tbl_xml.find("<hp:subList")
    sub_seg, _ = _tbl_balanced(tbl_xml, sub_start, "hp:subList")
    if not sub_seg:
        return []
    paras = []
    p = 0
    while True:
        i = sub_seg.find("<hp:p ", p)
        if i < 0:
            break
        seg, end = _tbl_balanced(sub_seg, i, "hp:p")
        if end < 0:
            break
        paras.append(seg)
        p = end
    return paras


def _para_plaintext(para_xml: str) -> str:
    """단락의 보이는 텍스트(모든 태그 제거 + XML 엔티티 복원).

    라벨 ``<보기>`` 는 XML 에 ``&lt;보기&gt;`` 로 인코딩되므로 엔티티를 풀어야
    ``_BOGI_LABEL_TEXT_RE`` 가 매칭된다.
    """
    txt = re.sub(r"<[^>]+>", "", para_xml)
    txt = (txt.replace("&lt;", "<").replace("&gt;", ">")
              .replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&"))
    return txt.strip()


# 1×1 박스 셀 첫 단락이 <보기>/<조건> 로 시작하는지 (라벨 박스 판정). <상자>·일반표 제외.
_BOGI_LABEL_TEXT_RE = re.compile(r"^\s*<\s*(보기|조건)\s*>")


def _inject_bogi_form(hwpx_path: str | Path) -> int:
    """저장된 .hwpx 에서 ``<보기>``/``<조건>`` 라벨 1×1 박스를 5×5 병합표 폼으로 치환.

    - section XML 의 모든 1×1 표 중 **셀 첫 단락 텍스트가 ``<보기>``/``<조건>`` 로 시작**
      하는 표만 대상(``<상자>``·OCR 표·기타 1×1 박스는 건드리지 않음).
    - 셀 subList 단락을 라벨(첫 단락)·내용(나머지)으로 분리해 ``bogi_box_template`` 의
      5×5 표에 채운다. 라벨은 가운데정렬.
    - 테두리 7+1종(BF4,8~15)을 header.xml 의 ``<hh:borderFills>`` 에 새 id 로 append,
      itemCnt 갱신, 템플릿 플레이스홀더를 실제 id 로 치환.
    - **위치기반 치환만**(findall+join 금지). 끝에 ``<hp:p`` 균형 검증.

    Returns: 치환한 라벨 박스 개수.
    """
    import zipfile, os
    from core.bogi_box_template import (
        BOGI_TABLE_TEMPLATE, BORDERFILL_DEFS, BORDERFILL_KEYS,
    )

    hwpx_path = Path(hwpx_path)
    with zipfile.ZipFile(hwpx_path) as z:
        infos = z.infolist()
        contents = {i.filename: z.read(i.filename) for i in infos}

    header_fn = next((f for f in contents if f.endswith("header.xml")), None)
    if header_fn is None:
        return 0
    header = contents[header_fn].decode("utf-8")
    center_pid = _bogi_center_parapr_id(header)

    total = 0
    bf_id_map = None  # 첫 치환 때 한 번만 borderFill 을 헤더에 append
    tiny_cp_id = None  # 첫 치환 때 한 번만 1pt charPr 를 헤더에 append(빈 셀 행높이 강제 해제)
    tbl_id_seq = 0

    for fn in list(contents):
        if not (fn.endswith(".xml") and "section" in fn.lower()):
            continue
        s = contents[fn].decode("utf-8")
        out = []
        last = 0
        changed = False
        # 1×1 표를 위치 순회(중첩표 고려 균형 추출)
        p = 0
        while True:
            m = re.search(r'<hp:tbl\b[^>]*rowCnt="1"[^>]*colCnt="1"', s[p:])
            if not m:
                break
            tstart = p + m.start()
            tbl_xml, tend = _tbl_balanced(s, tstart, "hp:tbl")
            if tend < 0:
                break
            p = tend
            paras = _extract_cell_paras(tbl_xml)
            if not paras:
                continue
            first_txt = _para_plaintext(paras[0])
            if not _BOGI_LABEL_TEXT_RE.match(first_txt):
                continue  # <상자>·일반표 등은 그대로 둠

            # borderFill·1pt charPr 는 처음 한 번만 헤더에 append
            if bf_id_map is None:
                bf_id_map, header = _append_borderfills(
                    header, BORDERFILL_DEFS, BORDERFILL_KEYS)
                tiny_cp_id, header = _append_tiny_charpr(header)

            # 라벨 = 첫 단락(가운데정렬), 내용 = 나머지 단락
            label_para = _set_para_align(paras[0], center_pid)
            label_sub = _wrap_subList([label_para])
            content_sub = _wrap_subList(paras[1:])

            tbl_id_seq += 1
            new_tbl = BOGI_TABLE_TEMPLATE
            new_tbl = new_tbl.replace("{{TBL_ID}}", str(2000000000 + tbl_id_seq))
            for k in BORDERFILL_KEYS:
                new_tbl = new_tbl.replace("{{BF%d}}" % k, str(bf_id_map[k]))
            new_tbl = new_tbl.replace("{{TINY_CP}}", str(tiny_cp_id))
            new_tbl = new_tbl.replace("{{LABEL_SUBLIST}}", label_sub)
            new_tbl = new_tbl.replace("{{CONTENT_SUBLIST}}", content_sub)

            out.append(s[last:tstart])
            out.append(new_tbl)
            last = tend
            changed = True
            total += 1
            # 치환으로 인덱스가 바뀌었지만 우리는 원본 s 의 tend 이후만 계속 스캔하므로 OK
        if changed:
            out.append(s[last:])
            new_s = "".join(out)
            # 태그 균형 검증(<hp:p 여는 == </hp:p> 닫는)
            opens = len(re.findall(r"<hp:p\b", new_s))
            closes = new_s.count("</hp:p>")
            if opens != closes:
                raise ValueError(
                    "bogi 폼 주입 후 <hp:p> 불균형: open=%d close=%d (%s)" % (opens, closes, fn))
            contents[fn] = new_s.encode("utf-8")

    if total == 0:
        return 0

    # 헤더(테두리 append) 반영
    contents[header_fn] = header.encode("utf-8")

    tmp = str(hwpx_path) + ".tmp"
    with zipfile.ZipFile(tmp, "w") as zout:
        for info in infos:
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type = info.compress_type
            zi.external_attr = info.external_attr
            zi.internal_attr = info.internal_attr
            zi.create_system = info.create_system
            zi.flag_bits = info.flag_bits
            zout.writestr(zi, contents[info.filename])
    os.replace(tmp, hwpx_path)
    return total


# 수기본(레퍼런스) 표 음영 borderFill — 전체 SOLID 0.12mm 테두리 + #D9D9D9 회색 채움.
# 레퍼런스 [학남고]…(워드).hwpx 의 borderFill id=16 구조 그대로(faceColor 추출 확인).
_SHADE_BORDERFILL_DEF = {
    16: '<hh:borderFill id="{{BF16}}" threeD="0" shadow="0" centerLine="NONE" '
        'breakCellSeparateLine="0"><hh:slash type="NONE" Crooked="0" isCounter="0"/>'
        '<hh:backSlash type="NONE" Crooked="0" isCounter="0"/>'
        '<hh:leftBorder type="SOLID" width="0.12 mm" color="#000000"/>'
        '<hh:rightBorder type="SOLID" width="0.12 mm" color="#000000"/>'
        '<hh:topBorder type="SOLID" width="0.12 mm" color="#000000"/>'
        '<hh:bottomBorder type="SOLID" width="0.12 mm" color="#000000"/>'
        '<hh:diagonal type="SOLID" width="0.1 mm" color="#000000"/>'
        '<hc:fillBrush><hc:winBrush faceColor="#D9D9D9" hatchColor="#000000" alpha="0"/>'
        '</hc:fillBrush></hh:borderFill>',
}


def _shade_target_mode(tbl_xml: str) -> str | None:
    """데이터 표(확률분포표·표준정규분포표)의 라벨 셀 음영 대상을 판정.

    수기본 통일(사용자 2026-06-08):
      - 표준정규분포표(z|P 세로형, colCnt==2) → **최상단 행**(rowAddr=0) 음영.
      - 확률분포표(X|값 가로형, rowCnt==2·colCnt>=3) → **첫 열**(colAddr=0) 음영.
    그 외(보기 5×5·1×1 박스·1행 레이아웃·답안표 등)는 None(미적용). 수식 데이터 표만 대상.
    """
    rm = re.search(r'<hp:tbl\b[^>]*\browCnt="(\d+)"', tbl_xml)
    cm = re.search(r'<hp:tbl\b[^>]*\bcolCnt="(\d+)"', tbl_xml)
    if not (rm and cm):
        return None
    nrow, ncol = int(rm.group(1)), int(cm.group(1))
    if "<hp:equation" not in tbl_xml:
        return None                       # 수식 없는 표(답안·레이아웃)는 제외
    if ncol == 2 and nrow >= 2:
        return "row0"                     # z-표(표준정규분포표)
    if nrow == 2 and ncol >= 3:
        return "col0"                     # 확률분포표
    return None


def _shade_cells(tbl_xml: str, shade_id: int, mode: str) -> str:
    """표 XML 안에서 음영 대상 셀(mode=row0/col0)의 borderFillIDRef 를 shade_id 로."""
    out = []
    p = 0
    while True:
        i = tbl_xml.find("<hp:tc", p)
        if i < 0:
            break
        cell, end = _tbl_balanced(tbl_xml, i, "hp:tc")
        if end < 0:
            break
        out.append(tbl_xml[p:i])
        addr = re.search(r'<hp:cellAddr colAddr="(\d+)" rowAddr="(\d+)"', cell)
        target = False
        if addr:
            col, row = int(addr.group(1)), int(addr.group(2))
            target = (mode == "row0" and row == 0) or (mode == "col0" and col == 0)
        if target:
            cell = re.sub(r'(<hp:tc\b[^>]*\bborderFillIDRef=")\d+(")',
                          lambda m: m.group(1) + str(shade_id) + m.group(2),
                          cell, count=1)
        out.append(cell)
        p = end
    out.append(tbl_xml[p:])
    return "".join(out)


def _inject_table_shading(hwpx_path: str | Path) -> int:
    """저장된 .hwpx 의 확률분포표·표준정규분포표 라벨 셀에 #D9D9D9 음영을 입힌다.

    수기본과 통일(사용자 2026-06-08). 음영 borderFill 1종을 header.xml 에 1회 append 한 뒤,
    `_shade_target_mode` 가 가리키는 셀의 borderFillIDRef 만 교체(위치기반). 멱등(이미 음영 id면
    재실행해도 동일). Returns: 음영 입힌 표 개수.
    """
    import zipfile, os
    hwpx_path = Path(hwpx_path)
    with zipfile.ZipFile(hwpx_path) as z:
        infos = z.infolist()
        contents = {i.filename: z.read(i.filename) for i in infos}

    header_fn = next((f for f in contents if f.endswith("header.xml")), None)
    if header_fn is None:
        return 0
    header = contents[header_fn].decode("utf-8")

    shade_id = None
    total = 0
    for fn in list(contents):
        if not (fn.endswith(".xml") and "section" in fn.lower()):
            continue
        s = contents[fn].decode("utf-8")
        out, last, p, changed = [], 0, 0, False
        while True:
            m = re.search(r'<hp:tbl\b', s[p:])
            if not m:
                break
            tstart = p + m.start()
            tbl_xml, tend = _tbl_balanced(s, tstart, "hp:tbl")
            if tend < 0:
                break
            p = tend
            mode = _shade_target_mode(tbl_xml)
            if mode is None:
                continue
            if shade_id is None:
                id_map, header = _append_borderfills(
                    header, _SHADE_BORDERFILL_DEF, [16])
                shade_id = id_map[16]
            new_tbl = _shade_cells(tbl_xml, shade_id, mode)
            if new_tbl != tbl_xml:
                out.append(s[last:tstart])
                out.append(new_tbl)
                last = tend
                changed = True
                total += 1
        if changed:
            out.append(s[last:])
            contents[fn] = "".join(out).encode("utf-8")

    if total == 0:
        return 0
    contents[header_fn] = header.encode("utf-8")
    tmp = str(hwpx_path) + ".tmp"
    with zipfile.ZipFile(tmp, "w") as zout:
        for info in infos:
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type = info.compress_type
            zi.external_attr = info.external_attr
            zi.internal_attr = info.internal_attr
            zi.create_system = info.create_system
            zi.flag_bits = info.flag_bits
            zout.writestr(zi, contents[info.filename])
    os.replace(tmp, hwpx_path)
    return total


def _append_borderfills(header: str, defs: dict, keys: list) -> tuple[dict, str]:
    """``BORDERFILL_DEFS`` 를 header.xml ``<hh:borderFills>`` 에 새 id 로 append.

    템플릿 키(4,8~15)는 새로 할당한 실제 id 로 매핑된다(기존 max id+1 부터 연속).
    같은 정의 안 다른 BFx 참조는 없으므로 각 def 의 자기 id 만 치환하면 된다.

    Returns: ({템플릿키: 실제id}, 갱신된 header).
    """
    bfs_open = re.search(r'<hh:borderFills\b[^>]*>', header)
    if not bfs_open:
        raise ValueError("header.xml 에 <hh:borderFills> 없음")
    existing = [int(x) for x in re.findall(r'<hh:borderFill\b[^>]*\bid="(\d+)"', header)]
    next_id = (max(existing) + 1) if existing else 1
    id_map = {}
    new_defs = []
    for k in keys:
        id_map[k] = next_id
        body = defs[k].replace("{{BF%d}}" % k, str(next_id))
        new_defs.append(body)
        next_id += 1
    # itemCnt += len(keys)
    cnt_m = re.search(r'(<hh:borderFills\b[^>]*itemCnt=")(\d+)(")', header)
    new_cnt = int(cnt_m.group(2)) + len(keys)
    header = header[:cnt_m.start()] + cnt_m.group(1) + str(new_cnt) + cnt_m.group(3) + header[cnt_m.end():]
    # append before </hh:borderFills>
    close_idx = header.find("</hh:borderFills>")
    header = header[:close_idx] + "".join(new_defs) + header[close_idx:]
    return id_map, header


def _append_tiny_charpr(header: str) -> tuple[int, str]:
    """header.xml ``<hh:charProperties>`` 에 1pt 글자모양(charPr)을 1회 append.

    5×5 폼표의 **빈 셀**(스페이서/테두리 행)이 기본 11pt(`height="1000"`)면 그 행 높이가
    11pt 로 강제돼 템플릿 cellSz 의 얇은 높이(691·382 HWPUNIT)가 안 먹는다(사용자
    2026-06-08). 빈 셀의 charPrIDRef 를 이 1pt(`height="100"`) charPr 로 가리키게 해
    행높이 강제를 푼다. (`_append_borderfills` 패턴 미러: 기존 charPr 하나 복제 →
    새 id(max+1) + height="100", itemCnt +1.)

    Returns: (새 charPr id, 갱신된 header).
    """
    cp_open = re.search(r'<hh:charProperties\b[^>]*>', header)
    if not cp_open:
        raise ValueError("header.xml 에 <hh:charProperties> 없음")
    existing = [int(x) for x in re.findall(r'<hh:charPr\b[^>]*\bid="(\d+)"', header)]
    if not existing:
        raise ValueError("header.xml 에 <hh:charPr> 없음")
    new_id = max(existing) + 1
    # 기존 charPr 하나(첫 번째) 복제 → id·height 만 바꿔 동일 폰트/메트릭 유지.
    src_m = re.search(r'<hh:charPr\b.*?</hh:charPr>', header, re.S)
    body = src_m.group(0)
    body = re.sub(r'\bid="\d+"', 'id="%d"' % new_id, body, count=1)
    body = re.sub(r'\bheight="\d+"', 'height="100"', body, count=1)  # 1pt = 100 HWPUNIT
    # itemCnt += 1
    cnt_m = re.search(r'(<hh:charProperties\b[^>]*itemCnt=")(\d+)(")', header)
    new_cnt = int(cnt_m.group(2)) + 1
    header = header[:cnt_m.start()] + cnt_m.group(1) + str(new_cnt) + cnt_m.group(3) + header[cnt_m.end():]
    # append before </hh:charProperties>
    close_idx = header.find("</hh:charProperties>")
    header = header[:close_idx] + body + header[close_idx:]
    return new_id, header


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
