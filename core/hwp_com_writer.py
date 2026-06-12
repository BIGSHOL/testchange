# -*- coding: utf-8 -*-
"""ExamDocument → HWP COM 직접 입력 writer.

한글(HWP)을 COM으로 구동해 문서를 직접 작성한다. 수식·표 크기는 HWP가
네이티브로 계산하므로 기존 ``hwpx_writer.py`` 의 크기추정 로직이 전혀 필요 없다.
HWP 미설치 환경에서는 ``hwpx_writer.write_exam_to_hwpx`` 로 폴백한다(GUI에서 분기).

수식 스크립트 생성은 ``core/latex_to_hwpeq.latex_to_hwpeq`` 를 그대로 재사용한다.
"""
from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)

# 객관식→서술형 전환 구분선 (기존 XML writer와 동일 문구)
_ESSAY_SEPARATOR = "──────────── 서술형 ────────────"
# 서술형 답안 작성 공간 줄 수
_ESSAY_BLANK_LINES = 6


import os
import re
import tempfile
import time
import zipfile

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
# 순한글(+공백) 표 셀 — 예 "합계". 수식 객체화하지 말고 평문으로(사용자 2026-06-09:
# 표 '합계'가 수식처리됨). 수학 셀(X·z·1.0·P(X=x)…)은 라틴/숫자/기호라 매칭 안 됨.
_HANGUL_CELL_RE = re.compile(r"^[가-힣\s]+$")
# 한글이 한 글자라도 든 셀 — HWP 수식 객체는 한글을 이탤릭화하고 공백을 죽이므로(이상/미만/
# 범위 "6이상 ~ 12미만", 헤더 "유통기한(개월)") 평문으로 렌더(사용자 2026-06-10).
_HAS_HANGUL_RE = re.compile(r"[가-힣]")
# 보기/조건 박스 '머리'(블록 시작이 <보기>/<조건>/<상자>) — 발문 끝 배점 위치 판정용(A2).
# 발문이 "<보기>에서…"처럼 마커로 시작해도 그건 인라인 참조다(마커에 조사가 **직결**) → 부정
# 전망. 단 ``<조건> 한 미지수…`` 처럼 마커 뒤 **공백+한글**은 박스 내용 시작이므로 박스 머리다
# (매천중 #19 소문항 조건박스가 평문 인라인되던 것, 2026-06-10). `<상자>` 는 항상 박스 머리.
# 마커 뒤 공백+참조어("중"/"중에서"/"에서")는 발문 인라인 참조 — "<보기> 중 일차함수…" 발문이 박스로
# 오인돼 발문 증발+보기 항목 평문화(월암중 #11·상원중 #16, 2026-06-11). "중간…" 등 일반
# 단어 시작 박스 내용은 lookahead 의 경계 조건([\s,.?]|$) 덕에 그대로 박스 머리다.
_COND_HEADER_RE = re.compile(
    r"^\s*(?:<\s*상자\s*>|(?:<\s*조건\s*>|<\s*보기\s*>|\[\s*조건\s*\]|\[\s*보기\s*\])"
    r"(?![가-힣])(?!\s+(?:중에서|에서|중)(?=[\s,.?]|$)))")
# 박스 내부 줄 경계: 마커(<보기>/<조건>/<상자>) 또는 항목 라벨(ㄱ. ㄴ. …, 앞이 공백/시작). 표 셀
# 안에서 마커는 자기 줄, 각 항목은 새 줄로 나누는 데 쓴다(A3/A5). (B3-2 라벨 뒤 공백은 token+공백.)
# 항목 라벨: ㄱ. ㄴ. … 또는 (가)(나)(다)… 한글 괄호 열거(조건 박스 줄나눔, #12 2026-06-08).
_KO_ENUM = r"\(\s*[가나다라마바사아자차카타파하]\s*\)"
_BOX_BOUNDARY_RE = re.compile(
    r"(<\s*상자\s*>|<\s*조건\s*>|<\s*보기\s*>|\[\s*조건\s*\]|\[\s*보기\s*\]"
    r"|(?:(?<=\s)|^)[ㄱ-ㅎ]\s*\.|" + _KO_ENUM + r")")
# 박스 줄 경계(확장): 불릿(•)도 경계로 — 불릿·<상자>는 줄바꿈만(토큰 미출력, A4), 숫자 항목
# (1. 2. 3.)은 라벨 정규식에 없으므로 불릿이 그 줄바꿈을 담당한다.
# ○(U+25CB, _normalize_box_circles 표준 불릿)도 경계로 추가하되 **_BULLET_RE 엔 없으므로
# 숨김이 아니라 표시**된다 — <조건> 박스의 ○ 항목이 한 줄로 흐르지 않고 각 ○ 가 자기 줄에서
# 시작한다(원본 동일, 대륜중 #15, 2026-06-11). 등식 블록의 ○ 는 emit_text(TEXT 전용)를 안 거쳐
# 무영향, 텍스트 박스의 ○ 는 정규화로 불릿만 존재.
_BOX_BREAK_RE = re.compile(
    r"(\s*[•·▪◦]\s*|\s*○\s*|<\s*상자\s*>|<\s*조건\s*>|<\s*보기\s*>|\[\s*조건\s*\]|\[\s*보기\s*\]"
    r"|(?:(?<=\s)|^)[ㄱ-ㅎ]\s*\.|" + _KO_ENUM + r")")
# 조건 박스 불릿: 논리 글자(content_parser._BOX_BULLET 정규화 결과 ○) ↔ 표시 글리프(작은 •).
# ○(U+25CB)가 HWP 본문에서 거대하게 렌더돼 사용자가 작은 점을 요구(2026-06-11). ○ 는 줄경계·
# 정규화 식별자로 유지하고 출력만 작은 ``•`` 로 치환(•는 _BULLET_RE 숨김자라 텍스트엔 못 넣음).
_BOX_BULLET_CHAR = "○"
_COND_BULLET_DISPLAY = "•"
# 단독(공백 경계) ○ 불릿 — content_parser._normalize_box_circles 표준화 결과. 본문 속
# "○표" 류(비불릿)는 뒤 경계 조건으로 제외. _is_labelless_box 의 "여러 항목" 판정용
# (경일중 #19 <상자> ○ 단서 2항목이 단일 진술로 오인돼 가운데정렬, 2026-06-11).
_CIRCLE_BULLET_RE = re.compile(r"(?:(?<=\s)|^)○(?=\s|$)")


# 원문자 열거 항목(㉠㉡㉢… U+3260-326D / ㉮㉯… U+326E-327B)으로 **시작**하는 TEXT 블록은
# **자기 줄**로 렌더한다 — 완료본은 항목을 각 한 줄로 둔다(대건고 #19 ㉠ AC / ㉡ CA / ㉢ A² …
# 가 한 줄에 붙던 것, 2026-06-13). 발문 첫 블록(번호/라벨 줄) 뒤 항목들 사이에만 줄바꿈.
# 블록 **선두**(공백 뒤)일 때만 — 인라인 참조('보기 ㉠은')는 블록 중간이라 미발동.
_CIRCLED_ITEM_RE = re.compile(r"^\s*[㉠-㉻]")


def _is_circled_item_start(block) -> bool:
    """TEXT 블록이 원문자 열거 항목(㉠…/㉮…)으로 시작하는가 — 항목별 줄바꿈 판정."""
    return (getattr(block, "type", None) == ContentType.TEXT
            and bool(_CIRCLED_ITEM_RE.match(block.value or "")))


def _has_box_markup(text: str) -> bool:
    """줄 분리가 필요한 박스 텍스트인지 — **불릿(•)이 있을 때만** 참.

    (불릿 없이 "<조건>에 맞게"처럼 본문에서 박스를 가리키는 인라인 참조는
    줄을 끊으면 안 되므로 제외.)
    """
    return bool(_BULLET_RE.search(text))


def _is_value_box(blocks: list[ContentBlock]) -> bool:
    """라벨 없는 **값 나열 상자**인지(``<상자>`` 마커 + 값들, 항목라벨/지문 없음).

    #10 "<상자> 18 13 8 9 17 13 x 13" 처럼 값(수식/짧은 텍스트)만 나열된 박스 →
    가운데정렬 + 값 사이 공백(사용자 2026-06-10). <보기>/<조건> 라벨 박스나 긴 지문
    박스(독수리 이야기)·(가)(나)/ㄱㄴㄷ 항목 박스는 제외(좌측정렬 유지).
    """
    texts = [b for b in blocks if b.type == ContentType.TEXT]
    eqs = [b for b in blocks
           if b.type in (ContentType.EQUATION, ContentType.EQUATION_BLOCK)]
    if not any(_PLAIN_BOX_RE.search(b.value or "") for b in texts):
        return False
    if any(_COND_MARKER_RE.search(b.value or "") for b in texts):
        return False                       # <보기>/<조건> 라벨 박스
    joined = "".join(b.value or "" for b in texts)
    if _CIRCLE_BULLET_RE.search(joined):
        # ○ 불릿 = 항목 나열 박스(값 나열 아님) → 좌측정렬. _BULLET_RE(•) 제거만으로는
        # ○ 2항목 박스(leftover '○ ○' ≤6자)가 값상자로 오인돼 _is_labelless_box 의
        # _CIRCLE_BULLET_RE 가드(경일중)를 단락 우회했다(새본리중 #5, 2026-06-12).
        return False
    # 마커(<상자>)·불릿 제거 후 남는 평문이 거의 없어야(항목 라벨/지문 박스 배제).
    leftover = "".join(_PLAIN_BOX_RE.sub("", b.value or "") for b in texts)
    leftover = _BULLET_RE.sub("", leftover)
    if _BOX_BOUNDARY_RE.search(leftover):  # ㄱ./(가) 등 항목 라벨이 있으면 값상자 아님
        return False
    return len(eqs) >= 2 and len(leftover.strip()) <= 6


def _is_labelless_box(blocks: list[ContentBlock]) -> bool:
    """항목 라벨((가)(나)/ㄱ.ㄴ.)·불릿(•) 없는 ``<상자>`` — 단일 진술/값 박스.

    #14 "모든 자연수 n에 대하여 2a_n+S_n=k이다." 처럼 라벨 없는 셀 내용은 가운데정렬
    (사용자 2026-06-10). <보기>/<조건> 라벨 박스나 (가)(나)/ㄱㄴㄷ 항목 박스는 좌측 유지.
    값 나열 박스(_is_value_box)도 이 조건을 만족(부분집합).
    """
    texts = [b for b in blocks if b.type == ContentType.TEXT]
    if not any(_PLAIN_BOX_RE.search(b.value or "") for b in texts):
        return False
    if any(_COND_MARKER_RE.search(b.value or "") for b in texts):
        return False                       # <보기>/<조건> 라벨 박스
    joined = "".join(b.value or "" for b in texts)
    if _BULLET_RE.search(joined) or _CIRCLE_BULLET_RE.search(joined):
        return False                       # 불릿(•·○) = 여러 항목 → 좌측
    leftover = _PLAIN_BOX_RE.sub("", joined)
    if _BOX_BOUNDARY_RE.search(leftover):  # (가)/ㄱ. 항목 라벨이 있으면 라벨 박스
        return False
    return True


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


# 그림자리 안내(그림 렌더 OFF 시 figure → 이 평문). 그림(IMAGE)과 동일하게 발문뒤 영역에
# 가운데·별도줄로 렌더해야 한다(사용자 2026-06-09: 평문이라 발문에 인라인되던 문제). 문구가
# 바뀌어도 견고하도록 **접두**로 인식한다(gui `_FIGURE_NOTE_TEXT`·form `_FIGURE_NOTE` 와 일치).
_FIGURE_NOTE_PREFIX = "※ 그림 자리"


def _is_figure_note(b: ContentBlock) -> bool:
    """그림자리 안내 TEXT 블록인지 — 그림(IMAGE)처럼 발문뒤 가운데 별도줄로 취급."""
    return (b.type == ContentType.TEXT
            and (b.value or "").lstrip().startswith(_FIGURE_NOTE_PREFIX))


# 표 제목(캡션) 종결형 — 발문 문장(종결어미/물음)은 캡션이 아니다(tail 로 넘기면 안 됨).
# 종결 패턴 뒤에 **닫는 괄호**가 와도 종결로 본다 — "(단, a는 상수이다.)" 처럼 발문이 괄호
# 조건절로 끝나면 마지막 TEXT 가 "는 상수이다.)" (이다.+닫는괄호). 닫는 괄호를 무시하지
# 않으면 종결 판정이 실패해 캡션으로 오인 → 배점이 괄호 한가운데 침투한다(중앙고 #2, 2026-06-10).
# 종결어미(이다/있다/한다/같다/된다)도 추가 — "유통기한"(명사 끝) 같은 캡션과 구별된다.
_CAPTION_SENTENCE_RE = re.compile(
    r"([.?!。]|시오|하라|구하라|쓰라|것은\??|값은\??|무엇|인가|니까|되는가|구하시오|하시오"
    r"|이다|있다|한다|같다|된다)\s*[)）.]*\s*$")


def _is_table_caption(text: str | None) -> bool:
    """표 바로 앞 TEXT 가 **표 제목(캡션)**인지 — 짧고 문장 종결형이 아니어야 한다.

    "헬스클럽 회원의 나이 (단위:세)"·"어느 마트에서 판매하는 통조림의 유통기한" = 캡션(True).
    "…옳은 것은?"·"…나타내면 다음과 같다." = 발문 문장(False). 발문이 표 바로 앞에서
    끝나는 정상 케이스(학남고 #3 등)를 캡션으로 오인하지 않도록 보수적으로 판정.
    """
    t = (text or "").strip()
    if not t or len(t) > 35:
        return False
    return not bool(_CAPTION_SENTENCE_RE.search(t))


def _caption_spans(blocks: list[ContentBlock]) -> dict[int, int]:
    """표(TABLE) 바로 앞의 **캡션 run** {시작idx: 표idx} 맵.

    캡션이 "나이(1|6은 16세)" 처럼 TEXT+EQUATION 여러 블록으로 쪼개져 올 수 있어
    run(TEXT/EQUATION 연속)을 모아 **결합 텍스트**로 `_is_table_caption` 판정한다.
    그림자리 안내·조건/보기 머리·box_member 블록은 run 에 넣지 않는다.
    """
    spans: dict[int, int] = {}
    for ti, b in enumerate(blocks):
        if b.type != ContentType.TABLE:
            continue
        j = ti
        while j > 0:
            p = blocks[j - 1]
            if p.type not in (ContentType.TEXT, ContentType.EQUATION):
                break
            if p.type == ContentType.TEXT and (
                    _is_figure_note(p) or _COND_HEADER_RE.search(p.value or "")):
                break
            if getattr(p, "box_member", False):
                break
            j -= 1
        if j < ti and _is_table_caption(
                "".join((blk.value or "") for blk in blocks[j:ti])):
            spans[j] = ti
    return spans


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
            # 표 바로 앞 **캡션(표 제목)**(예 "헬스클럽 회원의 나이 (단위:세)")은 표의 일부이므로
            # tail 에 포함 → 배점이 캡션 **앞**(발문 끝)에 온다(원본 PDF: 발문 [N점] → 표제목 →
            # 표). 발문 문장(종결형)은 캡션이 아니라 그대로 발문(사용자 2026-06-10).
            if i > 0 and blocks[i - 1].type == ContentType.TEXT \
                    and _is_table_caption(blocks[i - 1].value):
                return i - 1
            return i
        if b.type == ContentType.TEXT and _COND_HEADER_RE.search(b.value or ""):
            # 박스 머리 **바로 앞**에 매달린 그림(IMAGE)/블록수식/그림자리안내 연속 run 은
            # tail 에 포함(합의 #3: 발문뒤 = 조건/보기 + 표 + 그림 + 블록수식). 안 그러면
            # 그림(노트)이 발문에 인라인되고 배점이 노트 **뒤**로 밀린다(장산중 #24 —
            # 발문→그림→<보기> 순서, 2026-06-11). 사이에 TEXT 가 끼면(문장 중간 그림) 중단.
            j = i
            while j > 0 and (blocks[j - 1].type in (ContentType.IMAGE,
                                                    ContentType.EQUATION_BLOCK)
                             or _is_figure_note(blocks[j - 1])):
                j -= 1
            return j
    # 2순위: 끝에 매달린 그림/블록수식/그림자리안내 연속 run 의 시작(문장 중간 블록은 제외).
    i = len(blocks)
    while i > 0 and (blocks[i - 1].type in (ContentType.IMAGE, ContentType.EQUATION_BLOCK)
                     or _is_figure_note(blocks[i - 1])):
        i -= 1
    return i if i < len(blocks) else None


def _split_tail_post(blocks: list[ContentBlock]):
    """발문 뒤 영역(tail)을 '박스 코어'와 '박스 뒤 발문 연속(post)'으로 나눈다.

    OCR 은 보기/조건/상자 박스를 **자기완결 한 텍스트 블록**(헤더 라벨 + 항목
    (가)(나)/ㄱㄴㄷ 이 **한 블록 안**)으로 준다. 그 블록 **뒤**에 더 오는 블록은
    박스 항목이 아니라 **발문 연속**이다 — 예) #20 ``P(Y≤29)`` + "의 값을 … 구하시오
    [7점]", #18 "m이 자연수일 때 …". 과거엔 조건 헤더부터 **끝까지** 박스에 넣어 발문
    연속이 셀 하나에 갇혔다(학남고 확통 #18·#20, 2026-06-08).

    판정은 **box_member 태그**로 한다(content_parser 가 raw 박스 경계에서 단다 —
    인라인 수식 분리 후엔 박스 항목 수식과 발문 수식이 구별 불가하므로). box_member
    run(박스 블록들) 뒤에 태그 없는 블록이 있으면 그게 post(발문 연속).

    Returns: (core, post). post 가 비면 분리 없음(기존 동작 보존).
    """
    start = next((i for i, b in enumerate(blocks)
                  if getattr(b, "box_member", False)), None)
    if start is None:
        return blocks, []
    end = start
    while end < len(blocks) and getattr(blocks[end], "box_member", False):
        end += 1
    if end < len(blocks):                 # 박스 run 뒤에 발문 연속이 있음
        return blocks[:end], blocks[end:]
    return blocks, []


def _post_is_box(post: list[ContentBlock]) -> bool:
    """post(박스 뒤 '발문 연속')가 사실은 **또 다른 박스**(<조건>/<보기>/<상자>)인지.

    #16 처럼 ``<보기>`` 박스 **뒤에** ``<조건>`` 박스가 오면, 박스 그룹화가 ``<조건>`` 을
    자기완결 박스 뒤 발문 연속으로 오분류(box_member=False)해 평문으로 흘린다. 이건 발문
    연속이 아니라 **두 번째 박스** — 평문이 아니라 박스로 렌더하고, 서답형 배점도 미루지
    않아야 한다(배점은 발문 끝·박스 앞 = #18 와 동일). 첫 가시 TEXT 가 박스 머리이면 박스.
    (장산중 #5 같은 진짜 발문 연속 "이때 …것은?" 은 머리 매칭 안 돼 기존 동작 유지.)
    """
    b = next((b for b in post
              if b.type == ContentType.TEXT and (b.value or "").strip()), None)
    return b is not None and bool(_COND_HEADER_RE.search(b.value or ""))


def _post_has_stem(post: list[ContentBlock]) -> bool:
    """post(박스 뒤 블록들)에 진짜 '발문 연속' 콘텐츠가 있는지.

    그림(IMAGE)·그림자리 안내문구 TEXT **뿐**이면 발문이 아니라 발문뒤 시각 콘텐츠다 —
    배점을 그 뒤로 미루면(defer) 배점이 발문 끝을 떠나 그림/노트 아래 좌측에 찍힌다
    (경일중 #19 박스→그림 [6점], 2026-06-11. 원본·완료본은 발문 끝 "…서술하시오. [6점]").
    수식(EQ/EQUATION_BLOCK)·일반 TEXT 가 하나라도 있으면 기존대로 발문 연속(defer 유지).
    """
    return any(not (b.type == ContentType.IMAGE or _is_figure_note(b)) for b in post)


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


_TEX_CMD_RE = re.compile(r"\\[a-zA-Z]+")


def _choice_complexity(choice: Choice) -> int:
    """보기 하나의 '길이' 추정(시각 글리프 근사). 블록수식/표가 있으면 매우 큼(→1단).

    LaTeX 원문 길이를 그대로 재면 근호·분수 명령어(``\\sqrt{}``·``\\frac{}{}``)가 부풀어
    시각적으로 짧은 보기(``√30×√6=□√5`` = 11글리프, 원문 33자)가 1열로 강등된다
    (중앙중 #1·#2·#3 — 완료본은 2열). 명령어=1글리프, 구조문자({}^_·공백)=0글리프로
    정규화해 화면 폭을 근사한다. 긴 전개식(#5, 22글리프)은 여전히 1열(임계 18 유지).
    """
    score = 0
    for b in choice.contents:
        if b.type in (ContentType.TABLE, ContentType.EQUATION_BLOCK, ContentType.IMAGE):
            return 999
        v = _TEX_CMD_RE.sub("@", b.value or "")
        v = re.sub(r"[{}^_\\ ]", "", v)
        score += len(v)
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
    """ContentBlock에서 HWP 수식 스크립트를 얻는다(없으면 LaTeX에서 변환).

    본문 수식은 ``italicize_stat=False`` — content_parser 가 확통 이탤릭을 이미 처리했고,
    남은 ``\\mathrm{P}`` 는 기하 점(점 P·꼭짓점 A)을 위한 로만이라 보존해야 한다(2026-06-09).
    """
    if block.hwp_equation:
        return block.hwp_equation
    return latex_to_hwpeq(block.value, italicize_stat=False)


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
            # 표는 자체 단락 필요 — 앞 단락과 분리. 직전 단락(우측정렬 캡션 등)의
            # 정렬을 상속하지 않게 좌측으로 명시(사용자 2026-06-10 캡션 우측정렬).
            self.s.break_para()
            self.s.align_left()
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
            if _is_figure_note(block):
                # 그림자리 안내 = 그림(IMAGE)과 동일하게 가운데·별도줄(발문 인라인 금지, 2026-06-09).
                self.s.break_para()
                self.s.align_center()
                self.s.text(block.value)
                self.s.break_para()
                self.s.align_left()
            elif block.underline:
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

    def _write_caption_run(self, run: list[ContentBlock]) -> None:
        """표 캡션(표 제목) run — **줄바꿈 후 우측정렬**(사용자 2026-06-10).

        과거엔 캡션이 발문/배점에 인라인으로 이어져 "[5점]어느 마트…" 처럼 붙었다.
        run 은 TEXT/EQUATION 혼합(캡션 숫자가 수식으로 쪼개진 "나이(1|6은 16세)" 포함).
        캡션 뒤 표는 `_write_block` 의 TABLE 분기가 새 단락+좌측정렬로 잇는다(빈 줄 없음).
        """
        try:
            at_start = self.s.hwp.GetPos()[2] == 0
        except Exception:
            at_start = False
        if not at_start:
            self.s.break_para()
        self.s.align_right()
        for b in run:
            self._write_block(b, inline=True)

    def _write_tail_seq(self, blocks: list[ContentBlock]) -> None:
        """tail 블록 나열 렌더 — 표 바로 앞 캡션 run 은 우측정렬 줄로 분리, 나머지는
        `_write_block`. (`_write_condition_box` 의 표-혼합 경로·post 나열에서 사용.)"""
        spans = _caption_spans(blocks)
        i = 0
        while i < len(blocks):
            if i in spans:
                self._write_caption_run(blocks[i:spans[i]])
                i = spans[i]
                continue
            self._write_block(blocks[i])
            i += 1

    def _write_cell(self, val: str) -> None:
        """표 셀 1개 렌더(셀 정렬은 호출부에서 미리 지정).

        값 종류별 일관 규칙(사용자 2026-06-10):
        - **한글 포함**(합계·"6이상 ~ 12미만"·"유통기한(개월)") → 평문. HWP 수식 객체는
          한글을 이탤릭화하고 공백/물결(~)을 죽이므로 평문이라야 원본대로 보인다.
        - **LaTeX 명령(``\\``) 또는 공백 없는 단일 토큰**(``\\dfrac``·``P(0 \\leq Z \\leq z)``·
          ``A``·``0.16``·``P(X=x)``) → 수식 객체(본문 수식과 글꼴/기울임 일치).
        - **공백으로 나뉜 다중값**(줄기-잎 잎 "6 8"·범위 "12 ~ 18") → **토큰별 수식 객체**
          + 사이 공백/물결은 평문(합의 #5 수식 객체화 — 사용자 2026-06-10 "잎도 수식").
          통수식 하나로 넣으면 HWP 가 공백을 죽여 "68"·"1218" 로 붙으므로 토큰 단위로.
        """
        if not val:
            return
        if _HAS_HANGUL_RE.search(val) and "\\" not in val:
            self.s.text(val)
        elif "\\" in val or " " not in val:
            self.s.equation(latex_to_hwpeq(val))
        else:
            for i, tok in enumerate(val.split()):
                if i:
                    self.s.text(" ")
                if re.fullmatch(r"[~\-—–:|]", tok):
                    self.s.text(tok)        # 구분 기호는 평문(수식화하면 모양 변형)
                else:
                    self.s.equation(latex_to_hwpeq(tok))

    def _write_equation_table(self, rows: list[list[str]]) -> None:
        """표를 만들고 각 셀을 종류별로 렌더(수식 객체 / 평문). 빈 셀은 비운다.

        OCR 표(rows)의 수식 셀(``x``·``f(x)``·``\\frac{1}{2}``)은 수식 객체로(사용자
        2026-06-04). 한글·공백구분 다중값 셀은 평문(``_write_cell``, 2026-06-10).
        **줄기-잎 표**(헤더 ``[줄기, 잎]``)는 잎을 **좌측정렬**하고 열너비를 **줄기:잎=1:3**
        으로 잡아 원본처럼 렌더한다(사용자 2026-06-10).
        """
        if not rows:
            return
        nrow = len(rows)
        ncol = max((len(r) for r in rows), default=0)
        if ncol == 0:
            return
        is_stemleaf = (nrow >= 2 and ncol == 2
                       and str(rows[0][0]).strip() == "줄기"
                       and str(rows[0][1]).strip() == "잎")
        if is_stemleaf:
            self.s.table_begin(nrow, ncol, col_widths=[1, 3])
        else:
            self.s.table_begin(nrow, ncol)
        for ri in range(nrow):
            row = rows[ri]
            for ci in range(ncol):
                # 줄기-잎 '잎' 칸(둘째 열·헤더 제외)은 좌측정렬, 그 외는 가운데정렬.
                if is_stemleaf and ci == 1 and ri >= 1:
                    self.s.align_left()
                else:
                    self.s.align_center()    # 셀 값 가운데 정렬(사용자 요구 2026-06-04)
                val = str(row[ci]).strip() if ci < len(row) else ""
                if val and _HANGUL_CELL_RE.match(val):
                    self.s.text(val)         # 순한글 셀("합계")은 평문(수식객체 금지, 2026-06-09)
                elif val:
                    self._write_cell(val)    # 단일토큰=수식객체(self.s.equation(latex_to_hwpeq(val)))
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

    def _write_box_content(self, blocks: list[ContentBlock], space_values: bool = False) -> None:
        """보기/조건 박스 '내부'를 줄 단위로 출력(표 셀 안에서 호출).

        마커(<보기>)는 자기 줄, 각 항목 라벨(ㄱ. …)은 새 줄로 나눈다(A5). 수식 블록은
        항목 줄 안에 인라인으로 유지(A8). 항목 라벨 뒤엔 공백 1칸(A6).

        space_values: 값 나열 상자(#10)면 연속 값 수식 사이에 공백을 넣어 붙지 않게 한다.
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
            matches = list(_BOX_BREAK_RE.finditer(text))
            for mi, m in enumerate(matches):
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
                # 고아 ○ 불릿: 같은 텍스트에서 다음 경계까지 내용이 없으면(뒤가 곧장 (나)/ㄱ.
                # 라벨) 표시하지 않는다 — "(가)… ○ (나)…" 의 ○ 가 단독 줄로 떨어지던 것
                # (월서중 #12, 2026-06-11). 텍스트 끝 ○(항목 내용이 다음 EQ 블록)은 유지.
                if (tok == _BOX_BULLET_CHAR and mi + 1 < len(matches)
                        and not text[m.end():matches[mi + 1].start()].strip()):
                    is_hidden = True
                if emitted and not broke:
                    self.s.break_para()   # 마커/항목 라벨/불릿 앞에서 줄바꿈(보인 내용 있을 때만)
                    broke = True
                if not is_hidden:
                    # 표시 마커/라벨 출력(<조건>/<보기>/ㄱ. 등)
                    # 조건 박스 불릿 ○(U+25CB, content_parser._BOX_BULLET 정규화 결과)는 HWP 에서
                    # 거대하게 렌더돼(대륜중 #15) 작은 ``•`` 로 표시 치환(사용자 2026-06-11). 논리
                    # 불릿은 ○ 유지(_BOX_BREAK_RE 줄경계·정규화), 화면 글리프만 작은 점으로.
                    disp = _COND_BULLET_DISPLAY if tok == _BOX_BULLET_CHAR else tok
                    self.s.text(disp + " ")                # 라벨/마커 뒤 공백(A6)
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
                        # 라벨 뒤 첫 내용의 선행 공백 제거 — 안 그러면 첫 항목만 한 칸
                        # 들여써진다(2번째부터는 `•` 불릿이 양옆 공백을 흡수해 flush, #조건박스
                        # 첫줄 들여쓰기, 2026-06-09). after_label=True 로 첫 내용도 lstrip.
                        after_label = True
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
                if space_values and emitted:
                    self.s.text("  ")                # 값 나열 상자: 값 사이 공백(붙음 방지)
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
                self._write_tail_seq(blocks)   # 조건 머리 없음 → 표/블록(캡션 분리) 그대로
                return
            self._write_tail_seq(blocks[:ci])  # 조건 머리 앞(표 등)은 개별 렌더(캡션 분리)
            # 조건 머리 **뒤**에도 표가 있으면(예: _recover_table 이 끝에 append) 박스는
            # 머리~표 직전까지만 — 그대로 재귀하면 동일 리스트 무한재귀(RecursionError).
            rest = blocks[ci:]
            ti = next((i for i, b in enumerate(rest)
                       if b.type == ContentType.TABLE), None)
            if ti is None:
                self._write_condition_box(rest)      # 표 없음 보장 → 재귀 안전
            else:
                self._write_condition_box(rest[:ti])
                self._write_tail_seq(rest[ti:])      # 표(와 그 뒤)는 개별 렌더(캡션 분리)
            return
        # 단락 시작(pos==0, 예: 그림 뒤 빈 단락)이면 추가 줄바꿈 없이 그 단락을 재사용
        # → 그림↔조건 사이 빈 줄 방지(사용자 2026-06-05). 아니면 새 줄로.
        try:
            at_para_start = self.s.hwp.GetPos()[2] == 0
        except Exception:
            at_para_start = False
        if not at_para_start:
            self.s.break_para()
        # 라벨((가)(나)/ㄱㄴㄷ) 없는 **값 나열 상자**(<상자> + 값들, 예 #10 "18 13 8 …")는
        # 가운데정렬을 기본으로(사용자 2026-06-10). 라벨/지문 박스는 좌측(원본대로).
        value_box = _is_value_box(blocks)
        center_box = value_box or _is_labelless_box(blocks)   # 라벨 없는 셀=가운데(#14)
        self.s.align_left()             # 직전 블록수식/그림 가운데정렬 해제(표는 좌측)
        self.s.table_begin(1, 1)        # 한 칸 테두리 박스
        if center_box:
            self.s.align_center()       # **셀 안에서** 가운데정렬(table_begin 후=커서가 셀 안)
        self._write_box_content(blocks, space_values=value_box)
        self.s.table_end()
        self.s.align_left()

    def _write_tail(self, tail: list[ContentBlock]) -> bool:
        """발문 뒤 영역 렌더(**폼·기본 경로 공통** — 사용자 '항상 동일' 요구 2026-06-05).

        그림(IMAGE)·블록수식(EQUATION_BLOCK)은 개별 렌더(그림 가운데·수식 가운데),
        보기/조건(<보기>/<조건> 머리 이후)은 1×1 테두리 표 박스로. 그림↔조건 사이 빈 줄은
        `_write_condition_box` 가 단락시작(pos==0) 재사용으로 방지.

        Returns: 표 박스로 끝났는지(True면 트레일링 단락이 이미 새 줄이라 추가 줄바꿈 불필요).
        """
        core, post = _split_tail_post(tail)       # 박스 뒤 발문 연속(#18·#20) 분리
        cs = _condition_start(core)               # 표/조건 머리 시작(없으면 전부 pre)
        pre = core if cs is None else core[:cs]
        box = [] if cs is None else core[cs:]
        # 표 캡션이 pre 끝에 걸쳐 있으면(다음 블록=표) 줄바꿈+우측정렬로 분리(2026-06-10).
        cap_j = None
        if box and box[0].type == ContentType.TABLE and pre:
            cap_j = next((j for j, t in _caption_spans(core).items() if t == cs), None)
        for b in (pre if cap_j is None else pre[:cap_j]):
            self._write_block(b)                  # IMAGE 가운데·EQUATION_BLOCK 가운데(인라인 아님)
        if cap_j is not None:
            self._write_caption_run(pre[cap_j:])
        ended_box = False
        if box:
            self._write_condition_box(box)
            ended_box = True
        if post and _post_is_box(post):
            # post 가 또 다른 박스(<조건> 등, #16): 평문이 아니라 **두 번째 박스**로 렌더.
            # 핵심 박스 뒤 단락시작(table_end→pos0)이라 _write_condition_box 가 빈 줄 없이
            # 이어 붙인다(#17·#18 의 <조건> 박스와 동일 모양).
            self._write_condition_box(post)
            ended_box = True
        else:
            for bi, b in enumerate(post):         # 박스 뒤 발문 연속 — 박스 밖, 새 줄에 이어서
                if ended_box:
                    self.s.break_para()
                    self.s.align_left()
                    ended_box = False
                if bi == 0:
                    # post 발문은 일반 본문 — 박스/폼 템플릿의 볼드 상속 차단(#20, 2026-06-09).
                    self.s.set_char_shape(pt=self.s.base_pt, bold=False)
                self._write_block(b)
        return ended_box

    # ── 문제 ──────────────────────────────────────────────
    def _write_question(self, question: Question, top_level: bool = True) -> None:
        is_essay = not question.choices
        has_subs = bool(question.sub_questions)
        # 소문항이 **개별 배점**을 가질 때만 부모 배점이 '총점'("[총 N점]", 강동중). 배점 없는
        # 소문항((1)(2)(3) 조건 나열, 상인고 #21)이면 부모 배점은 그 문제 전체 배점이므로
        # 평문 "[N점]"(완료본 일치) → 부모가 직접 배점 표기.
        subs_have_scores = has_subs and any(getattr(s, "score", 0)
                                            for s in question.sub_questions)
        # 총점 소문항 부모는 본문에 "[총 N점]"으로 이미 표기됨 → 인라인 배점 생략(중복 방지).
        show_score = bool(question.score) and not subs_have_scores

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
        if subs_have_scores:
            stem, total_num = _split_trailing_score(stem)
            if total_num is None:
                total_num = question.score

        # 박스 뒤 발문 연속(#18·#20)이 있으면 배점은 그 발문 연속 **뒤**로 미룬다
        # (박스 → "P(Y≤29)의 값을 … 구하시오" → [N점] 순서). 서술형만이 아니라 **객관식도**
        # — 원본·완료본 모두 배점은 의문문(post) 끝 "…것은? [4점]" 에 인쇄된다(장산중 #5
        # 과정상자+㈎㈏㈐, 2026-06-11. 과거엔 발문 머리 뒤에 찍혀 우측정렬 폴백까지 발화).
        # post 가 그 자체로 박스(<조건> 등, #16)면 발문 연속이 아니므로 배점을 안 미룬다
        # (배점은 발문 끝·박스 앞 = #18 와 동일). 진짜 발문 연속(장산중 #5)만 미룬다.
        # post 가 그림/그림노트뿐(경일중 #19)이어도 발문 연속이 아님 → 배점=발문 끝.
        _, tail_post = _split_tail_post(tail)
        defer_score = (show_score and bool(tail_post)
                       and not _post_is_box(tail_post) and _post_has_stem(tail_post))

        # 발문 — 첫 블록은 인라인(번호와 같은 줄), 발문 선두 수식 줄바꿈 방지(A7).
        # 발문 중간 독립 블록수식(EQUATION_BLOCK) 뒤 발문 연속은 좌측 새 줄로 복귀(#19).
        prev_t = None
        for i, block in enumerate(stem):
            if (prev_t == ContentType.EQUATION_BLOCK
                    and block.type not in (ContentType.EQUATION_BLOCK, ContentType.IMAGE)):
                self.s.break_para()
                self.s.align_left()
            # 원문자 열거 항목(㉠㉡…)은 각 자기 줄(완료본 일치, 대건고 #19). 첫 블록 제외.
            elif i > 0 and _is_circled_item_start(block):
                self.s.break_para()
                self.s.align_left()
            self._write_block(block, inline=(i == 0))
            prev_t = block.type
        if prev_t == ContentType.EQUATION_BLOCK:   # 발문이 블록수식으로 끝남 → 배점 전 좌측복귀
            self.s.break_para()
            self.s.align_left()
        # 배점 — 객관식은 발문 끝 인라인. 서술형은 발문 끝 인라인 시도 후 줄 넘치면 우측정렬
        # (사용자 2026-06-09: 공간 충분하면 인라인, 없을 때만 줄바꿈 우측정렬).
        if show_score and not defer_score:
            if is_essay:
                self._write_score_inline_or_right(question.score)
            else:
                self._write_score(question.score)
        elif has_subs and total_num:
            # 소문항 부모 총점 "[총 N점]": 발문 끝 인라인 우선, 줄 넘치면 우측정렬(N 은 수식).
            self._write_total_score_inline_or_right(total_num)
        # 뒤 영역: 그림/블록수식은 개별(가운데), 보기/조건은 1×1 테두리 표 박스 (A3)
        if tail:
            ended_box = self._write_tail(tail)
            # 박스 뒤 발문 연속이 있던 문항: 미뤘던 배점을 여기서 — 서술형은 인라인 시도 후
            # 넘치면 우측정렬, 객관식은 발문(post) 끝 인라인(합의 #2).
            if defer_score:
                if is_essay:
                    self._write_score_inline_or_right(question.score)
                else:
                    self._write_score(question.score)
                ended_box = False
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
                self.s.equation(latex_to_hwpeq(block.value, italicize_stat=False))
            else:
                self._write_block(block)

    def _write_score(self, score: int, leading_space: bool = True) -> None:
        # 배점 숫자도 수식 객체로(A8). "[" "점]"는 텍스트.
        self.s.text(" [" if leading_space else "[")
        self.s.equation(str(score))
        self.s.text("점]")

    def _write_score_inline_or_right(self, score: int) -> None:
        """서술형 배점 — **발문 끝 인라인 우선, 줄 넘치면 줄바꿈 후 우측정렬**(폼 경로
        `_put_score` 와 동일, 사용자 2026-06-09: 공간 충분하면 인라인, 없을 때만 우측정렬).

        줄 넘침은 인라인 입력 전후 ``KeyIndicator()[5]``(줄) 비교로 결정적으로 판정한다.
        """
        h = self.s.hwp

        def line():
            try:
                return h.KeyIndicator()[5]
            except Exception:
                return -1

        sp = h.GetPos()
        la = line()
        self._write_score(score, leading_space=True)
        ep = h.GetPos()         # 삽입 끝(정확한 span 삭제용)
        lb = line()
        if la >= 0 and lb > la:
            # 인라인이 줄을 넘김 = 공간 부족 → 지우고 줄바꿈 후 우측정렬.
            # ⚠️ 삽입분(sp→ep)만 선택-삭제 — MoveSelParaEnd 는 캐럿 뒤 같은 단락의
            # 다른 내용까지 삼킨다(폼 정답 단락 침범 시 정답 페이지 증발, 2026-06-10).
            h.SetPos(sp[0], sp[1], sp[2])
            h.SelectText(sp[1], sp[2], ep[1], ep[2])
            h.HAction.Run("Delete")
            h.Run("BreakPara")
            self.s.align_right()
            self._write_score(score, leading_space=False)
            self.s.break_para()
            self.s.align_left()

    def _write_total_score_inline_or_right(self, num: int) -> None:
        """소문항 부모 총점 "[총 N점]" — 발문 끝 인라인 우선, 줄 넘치면 줄바꿈 후 우측정렬
        (서술형 점수와 동일 로직, 사용자 2026-06-09). N 은 수식 객체."""
        h = self.s.hwp

        def line():
            try:
                return h.KeyIndicator()[5]
            except Exception:
                return -1

        def put_inline(leading_space: bool):
            self.s.text(" [총 " if leading_space else "[총 ")
            self.s.equation(str(num))
            self.s.text("점]")

        sp = h.GetPos()
        la = line()
        put_inline(leading_space=True)
        ep = h.GetPos()         # 삽입 끝(정확한 span 삭제용)
        lb = line()
        if la >= 0 and lb > la:
            # ⚠️ 삽입분(sp→ep)만 선택-삭제(위 _write_score_inline_or_right 와 동일 함정).
            h.SetPos(sp[0], sp[1], sp[2])
            h.SelectText(sp[1], sp[2], ep[1], ep[2])
            h.HAction.Run("Delete")
            h.Run("BreakPara")
            self.s.align_right()
            put_inline(leading_space=False)
            self.s.break_para()
            self.s.align_left()

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


def _rewrite_zip(hwpx_path: "str | Path", infos, contents: dict) -> None:
    """ZipInfo(이름·순서·압축방식·플래그)를 보존하며 hwpx 를 재작성 — 임시파일 + 원자 교체.

    ⚠️ 실패(os.replace 잠김 등) 시 임시파일을 **반드시 정리** — 예외가 호출부에서 경고로만
    먹히면 출력 폴더에 무작위 이름 `.hwpx` 가 진짜 변환물처럼 남았다(감사 2026-06-10).
    """
    hwpx_path = Path(hwpx_path)
    fd, tmp = tempfile.mkstemp(suffix=".hwpx.tmp", dir=str(hwpx_path.parent))
    os.close(fd)
    try:
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
        # HWP COM Quit 비동기 핸들 레이스 — 직행 os.replace 는 PermissionError 로 간헐
        # 전실패해 후처리가 조용히 무변경(계성고 머리말 계열, 2026-06-12). 재시도.
        for _i in range(20):
            try:
                os.replace(tmp, str(hwpx_path))
                break
            except PermissionError:
                if _i == 19:
                    raise
                time.sleep(0.5)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


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

    _rewrite_zip(hwpx_path, infos, contents)
    return count


def _solidify_underline(hwpx_path: str | Path) -> int:
    """저장된 .hwpx 의 밑줄(underline) 글자모양을 **실선 검정**으로 강제한다.

    본문 밑줄은 ``HwpCom.underline_run`` 의 ``CharShapeUnderline`` 토글로만 들어가는데,
    토글은 **폼 템플릿의 기본 밑줄 스타일을 상속**한다. 대수회 폼들의 기본 밑줄은
    회색 점선(``shape="DOT" color="#808080"``)이라, 강조어("않은" 등)가 원본의 실선
    검정이 아니라 흐린 점선으로 렌더된다(강동중 중1 #1·#6 실측 2026-06-11). COM 으로
    토글 시 shape/color 를 안정적으로 못 덮으므로(action 은 단순 토글), 저장 후
    header.xml 의 ``<hh:underline …/>`` 를 직접 패치한다.

    우리 출력의 밑줄 char-run 은 **전부 강조**(다른 용도 밑줄을 만들지 않음)이고,
    레거시 ``hwpx_writer`` 도 항상 ``shape="SOLID" color="#000000"`` 으로 썼다. 그래서
    모든 ``<hh:underline>`` 의 shape→SOLID·color→#000000 로 통일한다(type 보존).
    머리말의 가로 줄 등은 charPr 밑줄이 아니라(테두리/그리기객체) 영향 없음.

    Returns:
        실선 검정으로 바꾼 underline 태그 수(0 이면 손댈 것 없음).
    """
    import zipfile

    hwpx_path = Path(hwpx_path)
    with zipfile.ZipFile(hwpx_path) as z:
        infos = z.infolist()
        hdr_info = next((i for i in infos if i.filename.endswith("header.xml")), None)
        if hdr_info is None:
            return 0
        contents = {i.filename: z.read(i.filename) for i in infos}

    hdr = contents[hdr_info.filename].decode("utf-8")
    count = 0

    def _solid(m: "re.Match") -> str:
        nonlocal count
        tag = m.group(0)
        new = tag
        if 'shape="' in new:
            new = re.sub(r'shape="[^"]*"', 'shape="SOLID"', new)
        if 'color="' in new:
            new = re.sub(r'color="[^"]*"', 'color="#000000"', new)
        if new != tag:
            count += 1
        return new

    hdr = re.sub(r'<hh:underline\b[^>]*/>', _solid, hdr)
    if count == 0:
        return 0
    contents[hdr_info.filename] = hdr.encode("utf-8")

    _rewrite_zip(hwpx_path, infos, contents)
    return count


def _fix_stemleaf_colwidth(hwpx_path: str | Path, ratio: tuple[int, int] = (1, 3)) -> int:
    """저장된 .hwpx 의 **줄기-잎 표** 열너비를 줄기:잎 = ``ratio`` 로 강제한다.

    ``table_begin(col_widths=[1, 3])`` 으로 1:3 을 지정해도 HWP 의 ``TableCreate`` 가
    열너비를 **균등 재배분**해 1:1 로 만든다(강동중 중1 #20 실측 2026-06-11: 셀 14528·14528).
    라이브 COM 표 조작은 불안정([[hwp-com-layout-limits]])하므로, 저장 후 section XML 의
    셀너비를 직접 패치한다. **표 총너비(``<hp:sz>``)는 보존**하고 colAddr 0·1 셀만
    재분배한다(콘텐츠/레이아웃 영향 최소). 줄기-잎 표(첫 셀 "줄기", 2열)만 대상 —
    표준정규분포표·확률분포표 등 다른 2열 표는 건드리지 않는다.

    Returns:
        열너비를 고친 표 개수(0 이면 손댈 것 없음).
    """
    import zipfile

    hwpx_path = Path(hwpx_path)
    with zipfile.ZipFile(hwpx_path) as z:
        infos = z.infolist()
        contents = {i.filename: z.read(i.filename) for i in infos}

    fixed = 0

    def _patch_section(xml: str) -> str:
        nonlocal fixed

        def _one_tbl(tm: "re.Match") -> str:
            nonlocal fixed
            tbl = tm.group(0)
            cc = re.search(r'colCnt="(\d+)"', tbl)
            if not cc or cc.group(1) != "2" or "줄기" not in tbl:
                return tbl
            szm = re.search(r'<hp:sz\s+width="(\d+)"\s+widthRelTo="ABSOLUTE"', tbl)
            if not szm:
                return tbl
            total = int(szm.group(1))
            r0, r1 = ratio
            w0 = max(int(total * r0 / (r0 + r1)), 1)
            w1 = total - w0
            widths = {"0": w0, "1": w1}

            def _one_tc(cm: "re.Match") -> str:
                tc = cm.group(0)
                am = re.search(r'<hp:cellAddr\s+colAddr="(\d+)"', tc)
                if not am or am.group(1) not in widths:
                    return tc
                w = widths[am.group(1)]
                return re.sub(
                    r'(<hp:cellSz\s+width=")\d+(")',
                    lambda s: s.group(1) + str(w) + s.group(2), tc, count=1)

            tbl = re.sub(r'<hp:tc\b.*?</hp:tc>', _one_tc, tbl, flags=re.S)
            fixed += 1
            return tbl

        return re.sub(r'<hp:tbl\b.*?</hp:tbl>', _one_tbl, xml, flags=re.S)

    changed = False
    for fn in list(contents):
        if re.search(r'section\d+\.xml$', fn):
            xml = contents[fn].decode("utf-8")
            new = _patch_section(xml)
            if new != xml:
                contents[fn] = new.encode("utf-8")
                changed = True
    if not changed:
        return 0

    _rewrite_zip(hwpx_path, infos, contents)
    return fixed


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

    _rewrite_zip(hwpx_path, infos, contents)
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
    except Exception as e:  # noqa: BLE001
        logger.warning("HWPX 후처리 실패(_fix_invisible_charpr): %s", e)
    # 강조 밑줄을 실선 검정으로 강제(폼 기본 밑줄=회색 점선 상속 보정).
    try:
        _solidify_underline(output_path)
    except Exception as e:  # noqa: BLE001
        logger.warning("HWPX 후처리 실패(_solidify_underline): %s", e)
    # 보기 2열 정렬: header.xml tabPr 에 고정 좌측 탭 주입(COM 미커밋 회피책).
    try:
        _inject_choice_tabstop(output_path)
    except Exception as e:  # noqa: BLE001
        logger.warning("HWPX 후처리 실패(_inject_choice_tabstop): %s", e)
    # 미주(문항번호) 번호 형식 "1)" → "1." : 저장 후 section XML 의 autoNumFormat
    # suffixChar 패치(COM EndnoteShape 는 캐럿 부작용·인코딩 불확실 → XML 결정적).
    try:
        _set_endnote_suffix(output_path)
    except Exception as e:  # noqa: BLE001
        logger.warning("HWPX 후처리 실패(_set_endnote_suffix): %s", e)
    # <보기>/<조건> 라벨 1×1 박스 → 5×5 병합표 폼(레퍼런스와 픽셀 동일). <상자>·일반표 제외.
    try:
        _inject_bogi_form(output_path)
    except Exception as e:  # noqa: BLE001
        logger.warning("HWPX 후처리 실패(_inject_bogi_form): %s", e)
    # 확률분포표 1열·표준정규분포표 최상단 행에 #D9D9D9 음영(수기본 통일).
    try:
        _inject_table_shading(output_path)
    except Exception as e:  # noqa: BLE001
        logger.warning("HWPX 후처리 실패(_inject_table_shading): %s", e)
    # 줄기-잎 표 열너비 줄기:잎=1:3 강제(TableCreate 가 균등 재배분하는 것 보정).
    try:
        _fix_stemleaf_colwidth(output_path)
    except Exception as e:  # noqa: BLE001
        logger.warning("HWPX 후처리 실패(_fix_stemleaf_colwidth): %s", e)
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

    _rewrite_zip(hwpx_path, infos, contents)
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
            # 내용 선두의 **빈 단락 제거** — COM 1×1 박스 작성이 라벨 직후 빈 단락을
            # 남겨 5×5 폼 내용 셀 첫 줄이 항상 한 줄 띄워졌다(다사중 #4 류, 사용자
            # 2026-06-12 — 원본은 라벨 아래 바로 항목). 판정은 태그 제거 후 텍스트
            # (탭 혼입 오판 방지 — 폼 is_empty 교훈).
            content_paras = list(paras[1:])
            while content_paras and not re.sub(r"<[^>]+>", "", content_paras[0]).strip():
                content_paras.pop(0)
            if not content_paras:        # 방어: 내용이 전부 빈 단락이면 기존 유지
                content_paras = list(paras[1:])
            content_sub = _wrap_subList(content_paras)

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

    _rewrite_zip(hwpx_path, infos, contents)
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
    # z-표(표준정규분포표)는 **헤더가 P(0≤Z≤z)** 인 2열 표만. 단순 2열(도수분포표 #16 등)을
    # colCnt==2 만으로 z-표로 오판해 1행 음영하던 버그 수정(사용자 2026-06-10). HWP 수식
    # 스크립트에서 ≤ 는 ``LEQ`` → "P(0 LEQ Z LEQ z)" 의 ``LEQ Z LEQ`` 시그니처로 한정.
    is_ztable = bool(re.search(r"LEQ\s*Z\s*LEQ", tbl_xml))
    if ncol == 2 and nrow >= 2 and is_ztable:
        return "row0"                     # z-표(표준정규분포표)
    # 확률분포표는 **확률 표기 P(X…) 가 있는** 표만. 2행×다열 모양만으로 음영하면 정비례
    # x/y 표까지 1열 음영되는 오탐(월서중 #21 — 완료본 무음영, 2026-06-11. z-표 LEQ 시그니처
    # 와 같은 결함 계열).
    is_dist = bool(re.search(r"P\s*\(\s*[A-Z]", tbl_xml))
    if nrow == 2 and ncol >= 3 and is_dist:
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
                # 멱등화: 이미 주입된 #D9D9D9 음영 borderFill 이 있으면 그 id 재사용 —
                # 재실행마다 새 id 를 append 하면 중복 정의가 누적되고 셀 참조가 매번
                # 바뀌어 "이미 음영이면 무변경" 보장이 깨졌다(감사 2026-06-10).
                m_old = re.search(
                    r'<hh:borderFill\b[^>]*\bid="(\d+)"(?:(?!</hh:borderFill>).)*?'
                    r'faceColor="#D9D9D9"', header, re.S)
                if m_old:
                    shade_id = int(m_old.group(1))
                else:
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
    _rewrite_zip(hwpx_path, infos, contents)
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
