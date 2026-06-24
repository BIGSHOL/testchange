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
from core.template_headers import (
    ACCENT_TEXT_MARK,
    ACCENT_WHITE_FILL,
    ACCENT_WHITE_INK,
    DEFAULT_TEMPLATE,
    compact_header,
    compact_header_height_mm,
    render_template_header,
    resolve_accent_rgb,
    token_values,
)
from core.latex_to_hwpeq import latex_to_hwpeq
from models.exam_document import (
    ContentBlock,
    ContentType,
    Choice,
    ExamDocument,
    ExamPage,
    Question,
    reorder_questions_by_number,
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
# 질문/명령 마커 — 캡션(명사구)엔 절대 안 나오므로 **문자열 어디에 있어도** 발문으로 본다.
# 발문이 "…a-b의 값은? (단, a>0, b>0)" 처럼 질문 뒤에 괄호 단서로 끝나면 종결 정규식($앵커)이
# 못 잡아 발문을 캡션으로 오인 → 발문이 우측정렬되고 배점이 침투(대진고 확통 #14, 2026-06-16).
_CAPTION_QUESTION_RE = re.compile(r"것은|값은|무엇|인가|되는가|구하시오|하시오|구하라|쓰라|[?？]")


def _is_table_caption(text: str | None) -> bool:
    """표 바로 앞 TEXT 가 **표 제목(캡션)**인지 — 짧고 문장 종결형/질문형이 아니어야 한다.

    "헬스클럽 회원의 나이 (단위:세)"·"어느 마트에서 판매하는 통조림의 유통기한"·"[표 1]" = 캡션.
    "…옳은 것은?"·"…나타내면 다음과 같다."·"…값은? (단, a>0)" = 발문(False). 발문이 표 바로
    앞에서 끝나거나 질문 뒤 괄호 단서로 끝나는 경우를 캡션으로 오인하지 않도록 보수적으로 판정.
    """
    # 캡션이 "독서량                  (단위: 권)" 처럼 제목↔범례 사이 큰 공백을 가질 수
    # 있어(원본 정렬용), 길이 판정 전 연속 공백을 1칸으로 접는다(안 그러면 35자 초과로
    # 캡션 미인식 → 발문에 인라인, 계성중3 #10, 2026-06-16).
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t or len(t) > 35:
        return False
    if _CAPTION_QUESTION_RE.search(t):
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


def _caption_run_back(blocks: list[ContentBlock], i: int) -> int:
    """blocks[i] 바로 앞의 **캡션 run**(짧은 제목, 예 "시청률(0|2은 2%)"·"[표 1]"·
    "맞힌 단어의 개수 (단위: 개)") 시작 인덱스를 돌려준다(캡션이 없으면 i 그대로).

    캡션이 TEXT+EQUATION 여러 블록으로 쪼개질 수 있어 run 으로 역탐색하되, **발문 종결형
    (?/시오/이다…)·질문형·그림노트·박스머리·box_member** 에서 멈춰 발문은 run 에 넣지
    않는다. 발문까지 합치면 길어져/질문마커로 `_is_table_caption` 이 False → 발문이 캡션으로
    오인되는 회귀를 막는다(사동중3 #14·덕원중3 #9, 2026-06-16).
    """
    j = i
    while j > 0:
        p = blocks[j - 1]
        if p.type not in (ContentType.TEXT, ContentType.EQUATION):
            break
        if p.type == ContentType.TEXT and (
                _is_figure_note(p) or _COND_HEADER_RE.search(p.value or "")
                or _CAPTION_SENTENCE_RE.search(p.value or "")):
            break
        if getattr(p, "box_member", False):
            break
        j -= 1
    if j < i and _is_table_caption("".join((b.value or "") for b in blocks[j:i])):
        return j
    return i


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
            # 캡션이 "시청률" + "(0|2은 2%)" 처럼 **여러 TEXT/EQ 블록**으로 쪼개져 올 수
            # 있어 run 전체를 tail 에 보낸다(단일 blocks[i-1] 만 보면 "시청률" 이 stem 에
            # 남아 발문에 인라인 + 배점이 캡션 한가운데 침투, 사동중3 #14, 2026-06-16).
            return _caption_run_back(blocks, i)
        if b.type == ContentType.TEXT and _COND_HEADER_RE.search(b.value or ""):
            # 박스 머리 **바로 앞 캡션 run**(예 "맞힌 단어의 개수 (단위: 개)")을 먼저 흡수
            # (덕원중3 #9, 2026-06-16) — 안 그러면 캡션이 stem 에 남아 배점이 캡션 뒤로 밀린다.
            # 박스 직전이 노트/그림이면 `_caption_run_back` 이 거기서 멈춰 발문 오흡수 안 함.
            j = _caption_run_back(blocks, i)
            # 그 앞에 매달린 그림(IMAGE)/블록수식/그림자리안내 연속 run 도 tail 에 포함(합의 #3:
            # 발문뒤 = 조건/보기 + 표 + 그림 + 블록수식). 안 그러면 그림(노트)이 발문에 인라인되고
            # 배점이 노트 **뒤**로 밀린다(장산중 #24 — 발문→그림→<보기>, 2026-06-11). 사이에
            # 발문 TEXT 가 끼면(문장 중간 그림) 중단.
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
        # 고른 폼(웹) — write_exam_to_hwp 가 주입. 기본값은 기존 동작(제목만 헤더).
        self._template = DEFAULT_TEMPLATE
        self._header_meta: dict = {}
        self._accent_rgb: tuple[int, int, int] = (0x0E, 0x0E, 0x10)
        self._columns = 1
        # 2단 칼럼 폭 산정용 여백(mm dict). write_exam_to_hwp 가 주입. None 이면 대수회 기본.
        self._margins: dict | None = None
        # 폼 모드 — 폼 파일(template_path)이 헤더를 제공하므로 COM 헤더를 그리지 않고
        # 본문만 append. write_exam_to_hwp 가 form_mode 일 때 True 주입.
        self._form_mode = False
        # 정답·해설 페이지(웹 showAnswers/quickAnswerOnly, §44). write_exam_to_hwp 주입.
        self._show_answers = False
        self._quick_answer_only = False

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
            elif block.underline or block.bold:
                self.s.emphasis_run(block.value, bold=block.bold, underline=block.underline)
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
            # 캡션 TEXT 의 제목↔범례 사이 큰 공백(원본 정렬용 "독서량      (단위:권)")은
            # 우측정렬 시 줄을 넘쳐 캡션이 발문 줄로 새거나 어긋난다 → 연속 공백 1칸으로
            # 접어 깔끔히 우측정렬(계성중3 #10, 2026-06-16).
            if b.type == ContentType.TEXT and b.value and "  " in b.value:
                b = ContentBlock(type=ContentType.TEXT,
                                 value=re.sub(r"\s{2,}", " ", b.value).strip(),
                                 underline=getattr(b, "underline", False))
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

    def _box_width(self) -> int:
        """본문 박스/표(보기·조건·OCR표)의 폭(HWP 단위). 2단이면 칼럼 폭, 1단이면 148mm.

        2단(colPr=2)에서 표를 1단 기본폭(148mm)으로 만들면 ~81mm 칼럼을 넘어 다음 단/거터를
        침범한다(사용자 2026-06-24). self._columns 로 분기해 칼럼 폭에 맞춘다. 2단 칼럼 폭은
        좌우 여백(self._margins)에 따라 동적 — 여백 프리셋(좁게/넓게)이 칼럼 폭에 반영된다.
        """
        if self._columns == 2:
            left, right, _ = _margins_2col_units(self._margins)
            return _col_width_2col(left, right)
        return _BOX_WIDTH_1COL

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
            self.s.table_begin(nrow, ncol, line_width=self._box_width(), col_widths=[1, 3])
        else:
            self.s.table_begin(nrow, ncol, line_width=self._box_width())
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
        self.s.table_begin(1, 1, line_width=self._box_width())   # 한 칸 테두리 박스(2단=칼럼폭)
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
        # 캡션이 pre 끝에 걸쳐 있으면 줄바꿈+우측정렬로 분리(2026-06-10). 표(_caption_spans)
        # 든 박스 머리(<상자> 등)든 동일 — 박스 앞 캡션 "맞힌 단어의 개수 (단위: 개)"도
        # 우측정렬(덕원중3 #9, 2026-06-16).
        cap_j = None
        if box and pre:
            if box[0].type == ContentType.TABLE:
                cap_j = next((j for j, t in _caption_spans(core).items() if t == cs), None)
            else:
                cj = _caption_run_back(pre, len(pre))
                cap_j = cj if cj < len(pre) else None
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

        # 본문 첫 텍스트 블록이 *자기 문항번호*("4. " 등)로 시작하면 제거 — OCR 이 인쇄된 번호를
        # 본문에 포함한 일부 문항(다사중 #4)에서 아래 writer 가 번호를 또 붙여 "4. 4." 중복
        # (§38-1 의 메인 번호판). 자기 번호 + 마침표/괄호 + 공백일 때만(보수적 — "4.5" 같은
        # 소수는 뒤 \s+ 로 제외, 다른 번호로 시작하는 정상 본문도 미발동).
        if top_level and question.contents:
            _b0 = question.contents[0]
            if _b0.type == ContentType.TEXT and isinstance(_b0.value, str):
                _stripped = re.sub(r'^\s*%d\s*[.)]\s+' % question.number,
                                   '', _b0.value, count=1)
                if _stripped != _b0.value:
                    _b0.value = _stripped

        # 번호(A1): 주문항은 미주 자동번호("1." 스타일, 12pt 볼드). 미주 마크의 번호 형식
        # "1." 의 마침표는 suffix(저장 후 XML 후처리)에서 오므로, 성공 시 마크 뒤엔 공백만.
        # 실패하면 텍스트 번호로 폴백 + 이후 문항도 텍스트(self._use_endnote=False).
        if top_level and self._use_endnote and self.s.endnote():
            self.s.text(" ")
        else:
            if top_level and self._use_endnote:
                self._use_endnote = False
            # 평문 번호: 주문항은 미주와 같은 강조(note_pt 볼드) 후 본문 복귀, 소문항은 본문 크기.
            if top_level:
                self.s.set_char_shape(self.s.note_pt, bold=True)
                self.s.text(f"{question.number}. ")
                self.s.set_char_shape(self.s.base_pt, bold=False)
            else:
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
        # 폼 모드면 헤더는 폼 파일(머릿말/꼬릿말·헤더 블록)이 제공 → COM 헤더 그리지 않고
        # 본문만 이어 쓴다(write_exam_to_hwp 가 MoveDocEnd 로 폼 헤더 뒤에 커서를 둠).
        if not self._form_mode:
            # 고른 폼의 COM 헤더를 렌더(폼 파일 없을 때의 폴백). header_meta 에 title 없으면
            # document.title 로 보강 — 헤더 함수가 제목을 그릴 수 있게.
            header_meta = dict(self._header_meta or {})
            if not header_meta.get("title"):
                header_meta["title"] = document.title or ""
            if self._columns == 2:
                # 2단: 리치 헤더는 우측 단과 겹치므로(§42-5) *간단 헤더*만 머릿말에.
                # 본문은 _apply_body_columns 후처리로 colPr=2. 1단은 아래 리치 헤더 유지.
                self.s.header_begin(0)
                self.s.set_char_size(self.s.base_pt)
                self.s.align_center()
                compact_header(self.s, header_meta)
                self.s.region_end()
            else:
                render_template_header(self.s, self._template, header_meta, self._accent_rgb)
            # 헤더 후 본문 글자 크기 복귀(헤더가 set_char_shape 로 바꿨을 수 있음).
            self.s.set_char_size(self.s.base_pt)
            self.s.align_left()
        # PDF 페이지가 뒤섞여 들어와도 검출된 인쇄 문항번호 순으로 출력한다(폼 경로와 동일 —
        # 미주 자동번호가 페이지 순서대로 매겨져 번호가 어긋나던 것, 경상여고 대수 26-1).
        # 정상(이미 정렬된) 시험지는 순서 불변(idempotent). 페이지별 머리말은 제목과 같으면
        # 본래도 생략되므로, 재정렬 시 연속 흐름으로 출력한다.
        all_q = reorder_questions_by_number(
            [q for page in document.pages for q in page.questions])
        prev_was_mc = False
        for question in all_q:
            is_essay = not question.choices
            if is_essay and prev_was_mc:
                self.s.align_center()
                self.s.text(_ESSAY_SEPARATOR)
                self.s.break_para()
                self.s.align_left()
            self._write_question(question)
            prev_was_mc = bool(question.choices)

        # 정답·해설 페이지(§44) — 정답/해설이 하나라도 있으면 문제 뒤 새 쪽에 추가.
        if self._show_answers and any(q.answer or q.solution for q in all_q):
            self._write_answer_page(all_q)

    def _write_answer_inline(self, lines: list[list[ContentBlock]]) -> None:
        """정답/해설 한 줄들을 인라인으로 — 줄 사이는 공백(정답은 보통 1줄)."""
        for li, line in enumerate(lines):
            if li > 0:
                self.s.text(" ")
            for blk in line:
                self._write_block(blk, inline=True)

    def _write_answer_page(self, questions: list[Question]) -> None:
        """문제 뒤 새 쪽에 '정답 및 해설' 페이지 — 빠른 정답 + (옵션) 문항별 해설(§44).

        웹 PrintAnswerKeyPage 미러: 제목 → 빠른 정답(번호·정답 흐름) → 문항별 정답+해설.
        본문과 같은 섹션이라 문서 단 설정 상속(2단이면 2단 흐름 = 웹 2-col 해설과 일치).
        _write_block 등 기존 프리미티브만 조합 — 신규 렌더 로직 없음.
        """
        self.s.break_page()
        # 제목 — 가운데·볼드·살짝 큰 글자(note_pt+2).
        self.s.align_center()
        self.s.set_char_shape(self.s.note_pt + 2, bold=True)
        self.s.text("정답 및 해설")
        self.s.set_char_shape(self.s.base_pt, bold=False)
        self.s.break_para()
        self.s.break_para()
        self.s.align_left()

        # 빠른 정답 — 번호 볼드 + 정답 인라인, 항목 사이 간격(자연 줄바꿈, 웹 flex-wrap 미러).
        for q in questions:
            self.s.set_char_shape(self.s.base_pt, bold=True)
            self.s.text(f"{q.number}. ")
            self.s.set_char_shape(self.s.base_pt, bold=False)
            if q.answer:
                self._write_answer_inline(q.answer)
            else:
                self.s.text("-")
            self.s.text("   ")   # 항목 간격
        self.s.break_para()

        # 문항별 해설 — quick_answer_only 면 빠른 정답에서 끝.
        if self._quick_answer_only:
            return
        self.s.break_para()
        for q in questions:
            if not q.solution:
                continue
            self.s.set_char_shape(self.s.base_pt, bold=True)
            self.s.text(f"{q.number}. ")
            self.s.set_char_shape(self.s.base_pt, bold=False)
            self.s.text("정답: ")
            if q.answer:
                self._write_answer_inline(q.answer)
            self.s.break_para()
            for line in q.solution:
                for blk in line:
                    self._write_block(blk, inline=True)
                self.s.break_para()
            self.s.break_para()   # 문항 간 간격


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


# 정통 헤더 표 열너비 비율(저장 후 XML 패치 — TableCreate 의 균등 재배분 우회, _fix_stemleaf
# 와 동일 이유). (colCnt, 라벨 키워드(공백 제거 후 매칭), 비율). 웹 JeongtongTemplate 와 정합:
#   시험정보 2×6 — 시험일 칸을 넓게(긴 날짜 뭉개짐 방지).
#   학생/점수 1×10 — 이름·점수 칸을 넓게(점수 "/ 100" 줄바꿈 방지).
_HEADER_COLW_SPECS = (
    (6, ("학교", "학년", "과목", "일시", "시간", "출제"), (7, 27, 7, 11, 8, 16)),
    # 학생행: 이름 칸을 넓게(웹의 flex 이름) → 점수 칸이 우측으로 밀림(웹 점수 박스 위치).
    (10, ("점수", "이름", "번호"), (7, 8, 6, 8, 7, 8, 7, 28, 8, 13)),
)


def _set_header_col_widths(hwpx_path: str | Path) -> int:
    """정통 헤더 표(시험정보 2×6·학생 1×10)의 셀 너비를 비율대로 강제(저장 후 XML).

    HWP TableCreate 가 col_widths 를 무시하고 균등 재배분하므로([[hwp-com-layout-limits]],
    _fix_stemleaf_colwidth 와 동일), 표 총너비는 보존하고 colAddr 별 cellSz width 만
    재분배한다. colCnt + 라벨 키워드로 헤더 표만 대상(본문 표 불간섭). Returns: 고친 표 수.
    """
    hwpx_path = Path(hwpx_path)
    with zipfile.ZipFile(hwpx_path) as z:
        infos = z.infolist()
        contents = {i.filename: z.read(i.filename) for i in infos}

    fixed = 0

    def _one_tbl(tm: "re.Match") -> str:
        nonlocal fixed
        tbl = tm.group(0)
        cc = re.search(r'colCnt="(\d+)"', tbl)
        if not cc:
            return tbl
        ncol = int(cc.group(1))
        spec = next((s for s in _HEADER_COLW_SPECS if s[0] == ncol), None)
        if spec is None:
            return tbl
        flat = tbl.replace(" ", "")
        if not any(k in flat for k in spec[1]):
            return tbl
        ratios = spec[2]
        # 0행 셀 너비 합 = 표 총너비(보존). colAddr→width.
        row0: dict[int, int] = {}
        for cm in re.finditer(r'<hp:tc\b.*?</hp:tc>', tbl, flags=re.S):
            tc = cm.group(0)
            a = re.search(r'<hp:cellAddr\s+colAddr="(\d+)"\s+rowAddr="(\d+)"', tc)
            w = re.search(r'<hp:cellSz\s+width="(\d+)"', tc)
            if a and w and a.group(2) == "0":
                row0[int(a.group(1))] = int(w.group(1))
        if len(row0) != ncol:
            return tbl
        total = sum(row0.values())
        tot_r = sum(ratios)
        neww: dict[int, int] = {}
        acc = 0
        for c in range(ncol):
            if c == ncol - 1:
                neww[c] = total - acc
            else:
                neww[c] = max(int(total * ratios[c] / tot_r), 1)
                acc += neww[c]

        def _one_tc(cm2: "re.Match") -> str:
            tc = cm2.group(0)
            a = re.search(r'<hp:cellAddr\s+colAddr="(\d+)"', tc)
            if not a or int(a.group(1)) not in neww:
                return tc
            w = neww[int(a.group(1))]
            return re.sub(r'(<hp:cellSz\s+width=")\d+(")',
                          lambda s: s.group(1) + str(w) + s.group(2), tc, count=1)

        tbl = re.sub(r'<hp:tc\b.*?</hp:tc>', _one_tc, tbl, flags=re.S)
        fixed += 1
        return tbl

    changed = False
    for fn in list(contents):
        if re.search(r'section\d+\.xml$', fn):
            xml = contents[fn].decode("utf-8")
            new = re.sub(r'<hp:tbl\b.*?</hp:tbl>', _one_tbl, xml, flags=re.S)
            if new != xml:
                contents[fn] = new.encode("utf-8")
                changed = True
    if changed:
        _rewrite_zip(hwpx_path, infos, contents)
    return fixed


_A4_WIDTH_HWPUNIT = 59528          # A4 가로(HWP 단위)
_MM_TO_HWPUNIT = 283.465

# 2단 기본 여백 = 대수회 검증 폼 그대로(사용자 2026-06-24 "상하좌우여백을 대수회폼으로").
# HWP 단위(283.465/mm). 좌우 20mm(기존 30mm은 너무 넓음) · 상15 · 하20 · 머릿말15 · 꼬릿말10.
# top/header(머릿말 밴드 높이)는 컴팩트 헤더 실제 높이에 맞춰 grow 가능(바닥값=아래 top, §42-7).
_DAERYUN_MARGIN = {"left": 5669, "right": 5669, "top": 4251, "bottom": 5669,
                   "header": 4251, "footer": 2834}
_COL_GAP_2COL = 2268               # 단 사이 간격 8mm(대수회 sameGap 과 동일)
# 2단 칼럼 폭 = (A4폭 - 좌우여백 - 단간격) / 2. 본문 박스/표(보기·조건·OCR표)를 이 폭에 맞춰
# 단 overflow 방지(사용자 2026-06-24 "단 크기에 따라 표 크기 조절, 단이 넘어감"). 약간의
# 우측 여유(−500)로 거터에 안 닿게. = (59528-5669-5669-2268)/2 - 500 ≈ 22461.
_COL_WIDTH_2COL = (_A4_WIDTH_HWPUNIT - _DAERYUN_MARGIN["left"]
                   - _DAERYUN_MARGIN["right"] - _COL_GAP_2COL) // 2 - 500
_BOX_WIDTH_1COL = 42000            # 1단 본문 박스/표 폭(148mm, 기존 table_begin 기본값)


def _col_width_2col(left_u: int, right_u: int) -> int:
    """좌우 여백(units)으로 2단 칼럼 폭 산출 — _COL_WIDTH_2COL 의 동적판(여백 프리셋 반영)."""
    return (_A4_WIDTH_HWPUNIT - left_u - right_u - _COL_GAP_2COL) // 2 - 500


def _margins_2col_units(margins: dict | None) -> tuple[int, int, int]:
    """2단 (좌, 우, 하) 여백(units). 웹 프리셋(mm) 있으면 반영, 없으면 대수회 기본.

    상단/머릿말(top/header)은 컴팩트 헤더 높이 정렬을 유지(§42-7 겹침 방지)하므로 여기서 안 다룸 —
    _apply_body_columns 가 top 을 헤더 높이 max 로 잡는다. 좌우는 칼럼 폭을, 하단은 본문 바닥 여백을
    결정. margins 없으면(구버전 payload·system) 대수회값 = 현행 동작(회귀 0).
    """
    if isinstance(margins, dict):
        left = int(round(margins.get("left", 20) * _MM_TO_HWPUNIT))
        right = int(round(margins.get("right", 20) * _MM_TO_HWPUNIT))
        bottom = int(round(margins.get("bottom", 20) * _MM_TO_HWPUNIT))
        return left, right, bottom
    return _DAERYUN_MARGIN["left"], _DAERYUN_MARGIN["right"], _DAERYUN_MARGIN["bottom"]


def _scale_table_total_width(tbl: str, target: int) -> str:
    """표 XML 의 셀 너비를 비율 보존하며 총너비 ``target`` 으로 스케일(+ 표 <hp:sz> 갱신)."""
    row0: dict[int, int] = {}
    for cm in re.finditer(r'<hp:tc\b.*?</hp:tc>', tbl, flags=re.S):
        tc = cm.group(0)
        a = re.search(r'<hp:cellAddr\s+colAddr="(\d+)"\s+rowAddr="(\d+)"', tc)
        w = re.search(r'<hp:cellSz\s+width="(\d+)"', tc)
        if a and w and a.group(2) == "0":
            row0[int(a.group(1))] = int(w.group(1))
    if not row0:
        return tbl
    ncol = max(row0) + 1
    total = sum(row0.values())
    if total <= 0 or total == target:
        return tbl
    neww: dict[int, int] = {}
    acc = 0
    for c in range(ncol):
        if c == ncol - 1:
            neww[c] = target - acc
        else:
            neww[c] = max(int(row0.get(c, 0) * target / total), 1)
            acc += neww[c]

    def _one_tc(cm2: "re.Match") -> str:
        tc = cm2.group(0)
        a = re.search(r'<hp:cellAddr\s+colAddr="(\d+)"', tc)
        if not a or int(a.group(1)) not in neww:
            return tc
        w = neww[int(a.group(1))]
        return re.sub(r'(<hp:cellSz\s+width=")\d+(")',
                      lambda s: s.group(1) + str(w) + s.group(2), tc, count=1)

    tbl = re.sub(r'<hp:tc\b.*?</hp:tc>', _one_tc, tbl, flags=re.S)
    # 표 총너비(<hp:sz>) 도 갱신 — 셀 합과 일치시켜야 HWP 가 정상 배치.
    tbl = re.sub(r'(<hp:sz\s+width=")\d+(")',
                 lambda s: s.group(1) + str(target) + s.group(2), tbl, count=1)
    return tbl


def _fit_header_tables(hwpx_path: str | Path, margins: dict | None = None) -> int:
    """정통 헤더 표(제목배너·정보·학생·OMR)를 **본문 텍스트 폭**에 맞춘다(저장 후 XML).

    문항 본문은 텍스트 폭(=A4-좌우여백) 전체를 쓰는데 헤더 표는 고정폭이라, 여백이
    기본(15/15)과 다르면 헤더·문항 우측 끝이 어긋난다. 적용된 여백으로 텍스트 폭을 계산해
    헤더 표만 스케일(본문 표 불간섭). 기본 여백이면 폭이 같아 no-op. Returns: 맞춘 표 수.
    """
    m = margins or {}
    left = m.get("left", 15)
    right = m.get("right", 15)
    target = int(round(_A4_WIDTH_HWPUNIT - (left + right) * _MM_TO_HWPUNIT))

    hwpx_path = Path(hwpx_path)
    with zipfile.ZipFile(hwpx_path) as z:
        infos = z.infolist()
        contents = {i.filename: z.read(i.filename) for i in infos}

    info_lbls = ("학교", "학년", "과목", "일시", "시간", "출제")
    stu_lbls = ("점수", "이름", "번호")
    total_fixed = 0
    changed_any = False
    for fn in list(contents):
        if not re.search(r'section\d+\.xml$', fn):
            continue
        xml = contents[fn].decode("utf-8")
        # 헤더 존재 판정 — 정보표(6열+라벨)가 있어야 헤더 영역으로 간주(본문만인 폴백 보호).
        tbls = re.findall(r'<hp:tbl\b.*?</hp:tbl>', xml, flags=re.S)
        has_header = any(
            (re.search(r'colCnt="6"', t) and any(k in t.replace(" ", "") for k in info_lbls))
            for t in tbls)
        if not has_header:
            continue
        idx = {"n": 0}

        def _one_tbl(tm: "re.Match") -> str:
            nonlocal total_fixed
            tbl = tm.group(0)
            i = idx["n"]
            idx["n"] += 1
            cc = re.search(r'colCnt="(\d+)"', tbl)
            rc = re.search(r'rowCnt="(\d+)"', tbl)
            ncol = int(cc.group(1)) if cc else 0
            nrow = int(rc.group(1)) if rc else 0
            flat = tbl.replace(" ", "")
            is_info = ncol == 6 and any(k in flat for k in info_lbls)
            is_stu = ncol == 10 and any(k in flat for k in stu_lbls)
            is_omr = ncol == 1 and ("답안" in flat or "OMR" in flat)
            is_banner = ncol == 1 and nrow == 1 and i == 0 and not is_omr
            if not (is_info or is_stu or is_omr or is_banner):
                return tbl
            new = _scale_table_total_width(tbl, target)
            if new != tbl:
                total_fixed += 1
            return new

        new_xml = re.sub(r'<hp:tbl\b.*?</hp:tbl>', _one_tbl, xml, flags=re.S)
        if new_xml != xml:
            contents[fn] = new_xml.encode("utf-8")
            changed_any = True

    if changed_any:
        _rewrite_zip(hwpx_path, infos, contents)
    return total_fixed


# 정통 헤더 라벨 셀 음영 borderFill — 전체 SOLID 0.12mm 테두리 + #F4F4F6(웹 ink04) 옅은 회색.
# _SHADE_BORDERFILL_DEF(확률분포표 #D9D9D9) 구조 그대로, faceColor 만 교체.
_HEADER_LABEL_BORDERFILL_DEF = {
    30: '<hh:borderFill id="{{BF30}}" threeD="0" shadow="0" centerLine="NONE" '
        'breakCellSeparateLine="0"><hh:slash type="NONE" Crooked="0" isCounter="0"/>'
        '<hh:backSlash type="NONE" Crooked="0" isCounter="0"/>'
        '<hh:leftBorder type="SOLID" width="0.12 mm" color="#000000"/>'
        '<hh:rightBorder type="SOLID" width="0.12 mm" color="#000000"/>'
        '<hh:topBorder type="SOLID" width="0.12 mm" color="#000000"/>'
        '<hh:bottomBorder type="SOLID" width="0.12 mm" color="#000000"/>'
        '<hh:diagonal type="SOLID" width="0.1 mm" color="#000000"/>'
        '<hc:fillBrush><hc:winBrush faceColor="#F4F4F6" hatchColor="#000000" alpha="0"/>'
        '</hc:fillBrush></hh:borderFill>',
}

# 음영 대상 라벨 셀 텍스트(공백 제거 후 완전일치). 값 셀("2학년" 등)·제목·OMR 은 제외.
_HEADER_LABEL_TEXTS = frozenset((
    "학교", "학년", "과목", "일시", "시간", "출제", "반", "번호", "이름", "점수",
))


def _shade_header_labels(hwpx_path: str | Path) -> int:
    """정통 헤더 라벨 셀(학교/학년/…/점수)에 #F4F4F6 음영(웹 tdLabel ink04 배경 대응).

    셀 텍스트가 라벨과 완전일치(공백 제거)할 때만 borderFillIDRef 를 음영 id 로 교체.
    값 셀·본문 표는 불간섭. borderFill 1종을 header.xml 에 1회 append(멱등). Returns: 음영 셀 수.
    """
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
        out, p, changed = [], 0, False
        while True:
            i = s.find("<hp:tc", p)
            if i < 0:
                out.append(s[p:])
                break
            cell, end = _tbl_balanced(s, i, "hp:tc")
            if end < 0:
                out.append(s[p:])
                break
            out.append(s[p:i])
            txt = "".join(re.findall(r'<hp:t>(.*?)</hp:t>', cell, flags=re.S)).replace(" ", "")
            if txt in _HEADER_LABEL_TEXTS:
                if shade_id is None:
                    m_old = re.search(
                        r'<hh:borderFill\b[^>]*\bid="(\d+)"(?:(?!</hh:borderFill>).)*?'
                        r'faceColor="#F4F4F6"', header, re.S)
                    if m_old:
                        shade_id = int(m_old.group(1))
                    else:
                        id_map, header = _append_borderfills(
                            header, _HEADER_LABEL_BORDERFILL_DEF, [30])
                        shade_id = id_map[30]
                new_cell = re.sub(r'(<hp:tc\b[^>]*\bborderFillIDRef=")\d+(")',
                                  lambda m: m.group(1) + str(shade_id) + m.group(2),
                                  cell, count=1)
                if new_cell != cell:
                    changed = True
                    total += 1
                out.append(new_cell)
            else:
                out.append(cell)
            p = end
        if changed:
            contents[fn] = "".join(out).encode("utf-8")

    if total == 0:
        return 0
    contents[header_fn] = header.encode("utf-8")
    _rewrite_zip(hwpx_path, infos, contents)
    return total


def _clone_charpr(header: str, src_id: int, mutate) -> tuple[int | None, str]:
    """header.xml 의 charPr(src_id)를 복제 → 새 id 부여 + mutate(body) 적용 후 append.

    원본의 크기·폰트·볼드를 보존하고 일부 속성만 바꿀 때(글자색·자간). itemCnt +1.
    Returns: (새 id 또는 None, 갱신 header).
    """
    existing = [int(x) for x in re.findall(r'<hh:charPr\b[^>]*\bid="(\d+)"', header)]
    if not existing:
        return None, header
    new_id = max(existing) + 1
    m = re.search(r'<hh:charPr\b[^>]*\bid="%d"[^>]*>.*?</hh:charPr>' % src_id, header, re.S)
    if not m:
        return None, header
    body = re.sub(r'\bid="\d+"', 'id="%d"' % new_id, m.group(0), count=1)
    body = mutate(body)
    cnt = re.search(r'(<hh:charProperties\b[^>]*itemCnt=")(\d+)(")', header)
    if cnt:
        header = (header[:cnt.start()] + cnt.group(1) + str(int(cnt.group(2)) + 1)
                  + cnt.group(3) + header[cnt.end():])
    close = header.find("</hh:charProperties>")
    if close < 0:
        return None, header
    header = header[:close] + body + header[close:]
    return new_id, header


def _style_header_runs(hwpx_path: str | Path) -> int:
    """정통 헤더 특정 런의 글자 스타일을 웹과 일치(저장 후 XML). 런의 charPr 를 복제·치환.

    - 점수 "/ 100"(폼 토큰 {{점수표기}}) → 회색 ink30(#A0A0A8)
    - 유의사항 "※ …" → 회색 ink70(#3A3A40)
    - 제목 {{제목}} → 자간(letter-spacing) 넓힘 (웹 0.12em)
    원본 크기·볼드는 유지(_clone_charpr) — 색/자간만 바꾼다. Returns: 스타일 적용 런 수.
    """
    hwpx_path = Path(hwpx_path)
    with zipfile.ZipFile(hwpx_path) as z:
        infos = z.infolist()
        contents = {i.filename: z.read(i.filename) for i in infos}
    header_fn = next((f for f in contents if f.endswith("header.xml")), None)
    if header_fn is None:
        return 0
    header = contents[header_fn].decode("utf-8")

    def set_color(c: str):
        return lambda b: re.sub(r'textColor="[^"]*"', 'textColor="%s"' % c, b, count=1)

    def set_spacing(v: int):
        repl = ('<hh:spacing hangul="%d" latin="%d" hanja="%d" japanese="%d" '
                'other="%d" symbol="%d" user="%d"/>') % ((v,) * 7)
        return lambda b: re.sub(r'<hh:spacing\b[^/]*/>', repl, b, count=1)

    specs = [
        (lambda t: t.strip() == "{{점수표기}}", set_color("#A0A0A8")),
        (lambda t: t.strip().startswith("※"), set_color("#3A3A40")),
        (lambda t: t.strip() == "{{제목}}", set_spacing(12)),
    ]

    total = 0
    state = {"header": header}
    for fn in list(contents):
        if not re.search(r'section\d+\.xml$', fn):
            continue
        s = contents[fn].decode("utf-8")
        changed = {"v": False}

        def _one_run(m: "re.Match") -> str:
            nonlocal total
            run = m.group(0)
            cpref = re.search(r'charPrIDRef="(\d+)"', run)
            tm = re.search(r'<hp:t>(.*?)</hp:t>', run, re.S)
            if not cpref or not tm:
                return run
            txt = tm.group(1)
            for pred, mut in specs:
                if pred(txt):
                    new_id, state["header"] = _clone_charpr(
                        state["header"], int(cpref.group(1)), mut)
                    if new_id is None:
                        return run
                    total += 1
                    changed["v"] = True
                    return re.sub(r'charPrIDRef="\d+"',
                                  'charPrIDRef="%d"' % new_id, run, count=1)
            return run

        new_s = re.sub(r'<hp:run\b[^>]*>.*?</hp:run>', _one_run, s, flags=re.S)
        if changed["v"]:
            contents[fn] = new_s.encode("utf-8")

    if total == 0:
        return 0
    contents[header_fn] = state["header"].encode("utf-8")
    _rewrite_zip(hwpx_path, infos, contents)
    return total


# ── accent 헤더 색 주입 (PUA 센티넬 기반) ────────────────────────────────
# 헤더 함수(_header_modern/workbook/yuhyung/jaseup)가 셀/런 텍스트 앞에 마커를 박고,
# _apply_accent_header 가 변환 후 그 마커를 찾아 faceColor(채운 배너)/textColor(흰·accent
# 글자)를 적용한 뒤 마커를 제거한다. set_char_shape 에 색 인자가 없어(COM 한계) XML 후처리.
# 마커는 PUA(U+E010~, template_headers 에 정의) — 본문 미사용 코드포인트라 충돌 0,
# 처리 후 전량 strip(tofu 방지).
_ACCENT_MARKS = (ACCENT_WHITE_INK, ACCENT_TEXT_MARK, ACCENT_WHITE_FILL)
_ACCENT_INK_HEX = "#0E0E10"


def _accent_bf_def(key: int, face_hex: str) -> dict:
    """faceColor=face_hex 채운 borderFill 정의(테두리도 같은 색=배너 솔리드, 선 안 보임)."""
    return {key: (
        '<hh:borderFill id="{{BF%d}}" threeD="0" shadow="0" centerLine="NONE" '
        'breakCellSeparateLine="0"><hh:slash type="NONE" Crooked="0" isCounter="0"/>'
        '<hh:backSlash type="NONE" Crooked="0" isCounter="0"/>'
        '<hh:leftBorder type="SOLID" width="0.12 mm" color="%s"/>'
        '<hh:rightBorder type="SOLID" width="0.12 mm" color="%s"/>'
        '<hh:topBorder type="SOLID" width="0.12 mm" color="%s"/>'
        '<hh:bottomBorder type="SOLID" width="0.12 mm" color="%s"/>'
        '<hh:diagonal type="SOLID" width="0.1 mm" color="#000000"/>'
        '<hc:fillBrush><hc:winBrush faceColor="%s" hatchColor="#000000" alpha="0"/>'
        '</hc:fillBrush></hh:borderFill>'
    ) % (key, face_hex, face_hex, face_hex, face_hex, face_hex)}


def _apply_accent_header(hwpx_path: str | Path, accent_rgb: tuple[int, int, int]) -> int:
    """accent 템플릿 헤더의 PUA 센티넬 → 색(저장 후 XML). 마커 없으면 no-op(jeongtong/pyeongga).

    U+E010 흰글자+검정(ink)배너 / U+E011 accent 글자 / U+E012 흰글자+accent 배너.
    셀 배경(채운 배너)은 borderFillIDRef 교체, 글자색은 charPr 복제(textColor). 끝에 마커 제거.
    Returns: 색 적용한 런 수.
    """
    hwpx_path = Path(hwpx_path)
    with zipfile.ZipFile(hwpx_path) as z:
        infos = z.infolist()
        contents = {i.filename: z.read(i.filename) for i in infos}
    header_fn = next((f for f in contents if f.endswith("header.xml")), None)
    if header_fn is None:
        return 0
    r, g, b = accent_rgb
    accent_hex = "#%02X%02X%02X" % (r, g, b)
    state = {"header": contents[header_fn].decode("utf-8")}

    secs = [fn for fn in contents if re.search(r'section\d+\.xml$', fn)]
    if not any(m in contents[fn].decode("utf-8", "replace") for fn in secs for m in _ACCENT_MARKS):
        return 0

    fill_cache: dict = {}

    def fill_id(face_hex: str) -> int:
        if face_hex not in fill_cache:
            key = 80 + len(fill_cache)
            id_map, state["header"] = _append_borderfills(
                state["header"], _accent_bf_def(key, face_hex), [key])
            fill_cache[face_hex] = id_map[key]
        return fill_cache[face_hex]

    total = 0
    for fn in secs:
        s = contents[fn].decode("utf-8")
        if not any(m in s for m in _ACCENT_MARKS):
            continue
        # 1) 셀 배경 — 마커 든 셀의 borderFillIDRef 교체.
        out, p = [], 0
        while True:
            i = s.find("<hp:tc", p)
            if i < 0:
                out.append(s[p:]); break
            cell, end = _tbl_balanced(s, i, "hp:tc")
            if end < 0:
                out.append(s[p:]); break
            out.append(s[p:i])
            ctxt = "".join(re.findall(r'<hp:t>(.*?)</hp:t>', cell, flags=re.S))
            face = (_ACCENT_INK_HEX if ACCENT_WHITE_INK in ctxt
                    else accent_hex if ACCENT_WHITE_FILL in ctxt else None)
            if face is not None:
                bid = fill_id(face)
                cell = re.sub(r'(<hp:tc\b[^>]*\bborderFillIDRef=")\d+(")',
                              lambda m: m.group(1) + str(bid) + m.group(2), cell, count=1)
            out.append(cell)
            p = end
        s = "".join(out)

        # 2) 런 글자색 — 마커별 textColor.
        def _one_run(m: "re.Match") -> str:
            nonlocal total
            run = m.group(0)
            cpref = re.search(r'charPrIDRef="(\d+)"', run)
            tm = re.search(r'<hp:t>(.*?)</hp:t>', run, re.S)
            if not cpref or not tm:
                return run
            txt = tm.group(1)
            if ACCENT_WHITE_INK in txt or ACCENT_WHITE_FILL in txt:
                color = "#FFFFFF"
            elif ACCENT_TEXT_MARK in txt:
                color = accent_hex
            else:
                return run
            new_id, state["header"] = _clone_charpr(
                state["header"], int(cpref.group(1)),
                lambda bdy: re.sub(r'textColor="[^"]*"', 'textColor="%s"' % color, bdy, count=1))
            if new_id is None:
                return run
            total += 1
            return re.sub(r'charPrIDRef="\d+"', 'charPrIDRef="%d"' % new_id, run, count=1)

        s = re.sub(r'<hp:run\b[^>]*>.*?</hp:run>', _one_run, s, flags=re.S)

        # 3) 모든 마커 제거(tofu 방지).
        for mk in _ACCENT_MARKS:
            s = s.replace(mk, "")
        contents[fn] = s.encode("utf-8")

    contents[header_fn] = state["header"].encode("utf-8")
    _rewrite_zip(hwpx_path, infos, contents)
    return total


def _apply_body_columns(hwpx_path: str | Path, gap_mm: float = 8.0, top_mm: float = 15.0,
                        divider: bool = False, margins: dict | None = None) -> int:
    """본문 섹션을 2단(colPr colCount=1→2)으로 + 위 여백을 머릿말 헤더 높이에 맞춤(저장 후 XML).

    divider=True 면 단 사이 세로 구분선(<hp:colLine>)을 colPr 안에 추가. type/width 는 OWPML
    enum(LineType2.SOLID, LineWidth."0.12 mm" — hwpxlib 모델로 확정 2026-06-24). 실측 렌더로
    중앙 세로선 확인. (구분선은 폼/COM 선례 없어 colPr XML 직접 주입이 유일.)

    *간단 헤더를 머릿말에 그린 뒤에만* 호출(write 가 columns==2 면 compact_header 를 머릿말에).
    좌우·하단 여백 = 웹 프리셋(margins, 좁게/보통/넓게) 반영 — 없으면 대수회 기본(좌우20·하20).
    상단/머릿말 밴드 높이는 폼의 `header == top == textHeight` 정렬을 모방 — 컴팩트 헤더 실제
    높이(top_mm)로 받되 대수회 top(15mm)을 바닥값으로(헤더 길어지면 grow, 겹침 0). 꼬릿말은
    대수회 고정(10mm). COM MultiColumn 작동 안 함(§42)이라 colPr·margin XML 직접 패치가 유일.
    Returns: 패치한 섹션 수.
    """
    hwpx_path = Path(hwpx_path)
    with zipfile.ZipFile(hwpx_path) as z:
        infos = z.infolist()
        contents = {i.filename: z.read(i.filename) for i in infos}
    gap = int(round(gap_mm * 283.465))
    # top/header = max(대수회 15mm, 컴팩트 헤더 실제 높이) — 보통은 대수회값, 헤더 길면 grow.
    top = max(_DAERYUN_MARGIN["top"], int(round(top_mm * 283.465)))
    # 좌우·하단 = 웹 프리셋 반영(§42-10). 상단/머릿말은 헤더 정렬(top) 유지, 꼬릿말은 대수회 고정.
    left, right, bottom = _margins_2col_units(margins)
    margin_xml = (
        f'<hp:margin header="{top}" footer="{_DAERYUN_MARGIN["footer"]}" gutter="0" '
        f'left="{left}" right="{right}" '
        f'top="{top}" bottom="{bottom}"/>'
    )
    n = 0
    for fn in list(contents):
        if not re.search(r'section\d+\.xml$', fn):
            continue
        s = contents[fn].decode("utf-8")
        new = re.sub(
            r'(<hp:colPr\b[^>]*\bcolCount=")1("[^>]*\bsameGap=")\d+(")',
            lambda m: f"{m.group(1)}2{m.group(2)}{gap}{m.group(3)}", s)
        # 컬럼 구분선: 2단 colPr(self-closing)에 <hp:colLine> 자식 주입(ColPrWriter 순서: colSz
        # 들 다음 colLine — 여기선 colSz 없어 colLine 만). enum 값 정확해야 Hancom 이 그림.
        if divider:
            new = re.sub(
                r'(<hp:colPr\b[^>]*\bcolCount="2"[^>]*?)/>',
                r'\1><hp:colLine type="SOLID" width="0.12 mm" color="#000000"/></hp:colPr>',
                new)
        # 페이지 여백(secPr 의 <hp:margin>) 전체를 대수회 한 벌로 교체. 섹션당 1개라 전치환 안전.
        new = re.sub(r'<hp:margin\b[^>]*/>', margin_xml, new)
        if new != s:
            n += 1
            contents[fn] = new.encode("utf-8")
    if n:
        _rewrite_zip(hwpx_path, infos, contents)
    return n


# 돋움/고딕 계열 face 판별(sans). 나머지(바탕/명조 등)는 serif 로 분류.
_SANS_FACE_RE = re.compile(r"돋움|고딕|굴림|맑은|Gothic|Dodum|Gulim|Sans", re.IGNORECASE)


def _apply_body_font(hwpx_path: str | Path, font: dict) -> int:
    """header.xml fontfaces 의 face 이름을 폰트팩 글꼴로 치환(저장 후 XML).

    charPr 의 fontRef(글꼴 id)는 그대로 두고 *글꼴 정의 자체의 face 이름만* 바꾼다 → 그 id 를
    참조하는 모든 본문/헤더가 자동으로 새 글꼴로 렌더. 바탕/명조 계열 face → serif, 돋움/고딕
    계열 → sans(기존 의도 보존). serif/sans 중 빈 값이면 그쪽 계열은 유지. COM 글꼴면 설정 불가
    (§40 색과 동일 한계)라 XML 후처리가 유일. fontfaces 블록 안에서만 치환(타 face 속성 오염 방지).
    Returns: 치환한 font 정의 수.
    """
    serif = (font.get("serif") or "").strip()
    sans = (font.get("sans") or "").strip()
    if not (serif or sans):
        return 0
    hwpx_path = Path(hwpx_path)
    with zipfile.ZipFile(hwpx_path) as z:
        infos = z.infolist()
        contents = {i.filename: z.read(i.filename) for i in infos}
    header_fn = next((f for f in contents if f.endswith("header.xml")), None)
    if header_fn is None:
        return 0
    s = contents[header_fn].decode("utf-8")
    fm = re.search(r"<hh:fontfaces\b.*?</hh:fontfaces>", s, re.S)
    if not fm:
        return 0
    block = fm.group(0)
    count = [0]

    def _repl_font(tm: "re.Match") -> str:
        tag = tm.group(0)
        face_m = re.search(r'\bface="([^"]*)"', tag)
        if not face_m:
            return tag
        face = face_m.group(1)
        new_face = sans if _SANS_FACE_RE.search(face) else serif
        if not new_face:          # 그쪽 계열 글꼴 미지정 → 유지
            return tag
        count[0] += 1
        return tag[: face_m.start(1)] + new_face + tag[face_m.end(1):]

    new_block = re.sub(r"<hh:font\b[^>]*>", _repl_font, block)
    if new_block != block:
        s = s[: fm.start()] + new_block + s[fm.end():]
        contents[header_fn] = s.encode("utf-8")
        _rewrite_zip(hwpx_path, infos, contents)
    return count[0]


def _thicken_header_outer_borders(
    hwpx_path: str | Path, thick: str = "0.5 mm", thin: str = "0.12 mm",
) -> int:
    """정통 헤더 표의 **바깥 테두리만 굵게**(웹 2.5px 프레임 + 얇은 내부선). 저장 후 XML.

    각 셀 위치(가장자리)로 굵을 변을 정해 borderFill 변형을 만들어 배정한다. 셀의 기존
    음영(faceColor)은 보존. 음영(_shade_header_labels) **이후** 실행해야 음영색을 읽는다.
    헤더 표(제목배너/정보/학생/OMR)만 대상 — 본문 표 불간섭. Returns: 처리한 셀 수.
    """
    hwpx_path = Path(hwpx_path)
    with zipfile.ZipFile(hwpx_path) as z:
        infos = z.infolist()
        contents = {i.filename: z.read(i.filename) for i in infos}
    header_fn = next((f for f in contents if f.endswith("header.xml")), None)
    if header_fn is None:
        return 0
    state = {"header": contents[header_fn].decode("utf-8")}
    info_lbls = ("학교", "학년", "과목", "일시", "시간", "출제")
    stu_lbls = ("점수", "이름", "번호")

    def face_of(bfid: int) -> str:
        m = re.search(
            r'<hh:borderFill\b[^>]*\bid="%d"[^>]*>.*?</hh:borderFill>' % bfid,
            state["header"], re.S)
        if not m:
            return ""
        fm = re.search(r'faceColor="([^"]+)"', m.group(0))
        return fm.group(1) if (fm and fm.group(1).lower() != "none") else ""

    existing = [int(x) for x in re.findall(r'<hh:borderFill\b[^>]*\bid="(\d+)"', state["header"])]
    nid = [max(existing) if existing else 0]
    cache: dict = {}
    appended: list = []

    def get_bf(sides: set, face: str) -> int:
        key = (tuple(sorted(sides)), face)
        if key in cache:
            return cache[key]
        nid[0] += 1
        bid = nid[0]

        def w(side: str) -> str:
            return thick if side in sides else thin
        fill = ('<hc:fillBrush><hc:winBrush faceColor="%s" hatchColor="#000000" '
                'alpha="0"/></hc:fillBrush>' % face) if face else ""
        bf = ('<hh:borderFill id="%d" threeD="0" shadow="0" centerLine="NONE" '
              'breakCellSeparateLine="0"><hh:slash type="NONE" Crooked="0" isCounter="0"/>'
              '<hh:backSlash type="NONE" Crooked="0" isCounter="0"/>'
              '<hh:leftBorder type="SOLID" width="%s" color="#000000"/>'
              '<hh:rightBorder type="SOLID" width="%s" color="#000000"/>'
              '<hh:topBorder type="SOLID" width="%s" color="#000000"/>'
              '<hh:bottomBorder type="SOLID" width="%s" color="#000000"/>'
              '<hh:diagonal type="SOLID" width="0.1 mm" color="#000000"/>%s</hh:borderFill>'
              ) % (bid, w("L"), w("R"), w("T"), w("B"), fill)
        appended.append(bf)
        cache[key] = bid
        return bid

    total = 0
    for fn in list(contents):
        if not re.search(r'section\d+\.xml$', fn):
            continue
        s = contents[fn].decode("utf-8")
        idx = {"n": 0}

        def _one_tbl(tm: "re.Match") -> str:
            nonlocal total
            tbl = tm.group(0)
            i = idx["n"]
            idx["n"] += 1
            cc = re.search(r'colCnt="(\d+)"', tbl)
            rc = re.search(r'rowCnt="(\d+)"', tbl)
            ncol = int(cc.group(1)) if cc else 0
            nrow = int(rc.group(1)) if rc else 0
            flat = tbl.replace(" ", "")
            is_info = ncol == 6 and any(k in flat for k in info_lbls)
            is_stu = ncol == 10 and any(k in flat for k in stu_lbls)
            is_omr = ncol == 1 and ("답안" in flat or "OMR" in flat)
            is_banner = ncol == 1 and nrow == 1 and i == 0 and not is_omr
            if not (is_info or is_stu or is_omr or is_banner):
                return tbl

            def _one_tc(cm: "re.Match") -> str:
                nonlocal total
                tc = cm.group(0)
                a = re.search(r'<hp:cellAddr\s+colAddr="(\d+)"\s+rowAddr="(\d+)"', tc)
                bf = re.search(r'borderFillIDRef="(\d+)"', tc)
                if not a or not bf:
                    return tc
                col, row = int(a.group(1)), int(a.group(2))
                sides = set()
                if row == 0:
                    sides.add("T")
                if row == nrow - 1:
                    sides.add("B")
                if col == 0:
                    sides.add("L")
                if col == ncol - 1:
                    sides.add("R")
                bid = get_bf(sides, face_of(int(bf.group(1))))
                total += 1
                return re.sub(r'(borderFillIDRef=")\d+(")',
                              lambda mm: mm.group(1) + str(bid) + mm.group(2), tc, count=1)

            return re.sub(r'<hp:tc\b.*?</hp:tc>', _one_tc, tbl, flags=re.S)

        new_s = re.sub(r'<hp:tbl\b.*?</hp:tbl>', _one_tbl, s, flags=re.S)
        if new_s != s:
            contents[fn] = new_s.encode("utf-8")

    if not appended:
        return 0
    hdr = state["header"]
    cntm = re.search(r'(<hh:borderFills\b[^>]*itemCnt=")(\d+)(")', hdr)
    if cntm:
        hdr = (hdr[:cntm.start()] + cntm.group(1) + str(int(cntm.group(2)) + len(appended))
               + cntm.group(3) + hdr[cntm.end():])
    close = hdr.find("</hh:borderFills>")
    hdr = hdr[:close] + "".join(appended) + hdr[close:]
    contents[header_fn] = hdr.encode("utf-8")
    _rewrite_zip(hwpx_path, infos, contents)
    return total


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
    template: str = DEFAULT_TEMPLATE,
    header_meta: dict | None = None,
    accent_color: str = "",
    columns: int = 1,
    form_mode: bool = False,
    margins: dict | None = None,
    use_endnote: bool = True,
    divider: bool = False,
    font: dict | None = None,
    show_answers: bool = False,
    quick_answer_only: bool = False,
) -> Path:
    """편의 함수: ExamDocument를 HWP COM으로 .hwpx 파일로 저장.

    Args:
        document: 변환할 시험 문서
        output_path: 출력 .hwpx 경로
        template_path: 양식 파일(.hwp/.hwpx). 주어지면 해당 서식 위에 작성.
            form_mode=True 면 *고른 폼 파일* — 머릿말/꼬릿말·헤더 블록은 폼이 제공하고
            본문은 그 뒤(MoveDocEnd)에 흘려 쓴다. COM 헤더는 그리지 않음.
        template: 인쇄 폼 id (pyeongga|jeongtong|modern|workbook|jaseup|yuhyung).
            폼 파일이 없을 때 COM 헤더(근사) 분기에만 사용. 미지정 → jeongtong.
        header_meta: 시험지 정보 dict(학교명·시험일·배점 등). adapt_payload 산출.
            form_mode 면 저장 후 {{토큰}} 치환에도 사용.
        accent_color: 강조색 #RRGGBB. 빈 값이면 템플릿 기본 accent.
        columns: 본문 단 수(1|2). 현재 헤더 범위 밖 — 저장만(후속 본문 단 분할용).
        form_mode: 폼 파일 사용 여부. True 면 헤더=폼 / 본문=append / {{토큰}} 치환.

    Returns:
        저장된 파일 경로
    """
    output_path = Path(output_path)
    use_form = bool(form_mode and template_path)
    # 빌드는 숨김(빠름)이 기본이나, 실시간 작성 표시 옵션(CONVERSION_VISIBLE)이면 보이게 띄운다.
    with HwpSession(visible=CONVERSION_VISIBLE) as s:
        if template_path:
            s.open(template_path)
            if use_form:
                s.move_doc_end()      # 폼 헤더(블록/머릿말) 뒤에 본문 append
            else:
                s.move_doc_begin()
        writer = HwpComWriter(s)
        # 고른 폼 주입 — write() 가 render_template_header 로 헤더 분기(폼 모드면 헤더 스킵).
        writer._template = template or DEFAULT_TEMPLATE
        writer._header_meta = header_meta or {}
        writer._accent_rgb = resolve_accent_rgb(writer._template, accent_color)
        writer._columns = columns if columns in (1, 2) else 1
        writer._margins = margins   # 2단 칼럼 폭(_box_width) 산정용
        writer._form_mode = use_form
        # 문항번호 방식: 기본 미주(자동번호) 유지. 웹 내보내기(convert_cli)는 use_endnote=False
        # 로 평문 번호 — 미주 마크(첨자) + 문서끝 미주 목록("1.2.3…") 잔여 제거(완성도, 2026-06-23).
        # 웹 payload 는 문항번호가 명시·정렬되어 평문이 정확. GUI 등 다른 경로는 기본 True(불변).
        writer._use_endnote = use_endnote
        # 정답·해설 페이지(§44) — write() 가 문제 뒤 새 쪽에 '정답 및 해설' 추가.
        writer._show_answers = show_answers
        writer._quick_answer_only = quick_answer_only
        writer.write(document)
        s.save_hwpx(output_path)
    # 폼 모드 — 폼의 {{토큰}} 을 시험지 정보로 치환(머릿말/꼬릿말·헤더 블록 모두).
    if use_form and header_meta:
        try:
            n = _fill_tokens(output_path, token_values(header_meta))
            logger.info("폼 토큰 치환 %d건", n)
        except Exception as e:  # noqa: BLE001
            logger.warning("HWPX 후처리 실패(_fill_tokens): %s", e)
    # 웹에서 설정한 쪽 여백(mm)을 출력에 적용 — 폼/기본 여백을 덮어쓴다(웹이 source).
    # 단 2단은 _apply_body_columns 가 위 여백을 머릿말 헤더 높이만큼 따로 잡으므로 제외(겹침 방지).
    if margins and columns != 2:
        try:
            tag = _margin_tag(
                top_mm=margins.get("top", 12),
                bottom_mm=margins.get("bottom", 12),
                left_mm=margins.get("left", 15),
                right_mm=margins.get("right", 15),
            )
            _set_page_margins(output_path, tag)
        except Exception as e:  # noqa: BLE001
            logger.warning("HWPX 후처리 실패(_set_page_margins): %s", e)
    # 헤더 표 폭을 실제 텍스트 폭(=A4-여백)에 맞춤 — 헤더·문항 우측 끝 정렬(여백 변경 대응).
    try:
        _fit_header_tables(output_path, margins)
    except Exception as e:  # noqa: BLE001
        logger.warning("HWPX 후처리 실패(_fit_header_tables): %s", e)
    # accent 템플릿 헤더의 PUA 센티넬 → 색(채운 배너 faceColor + 흰/accent 글자). 마커
    # 없으면 no-op(jeongtong/pyeongga). COM 헤더 경로에서 색을 입히는 유일한 수단.
    try:
        accent_rgb = resolve_accent_rgb(template or DEFAULT_TEMPLATE, accent_color)
        _apply_accent_header(output_path, accent_rgb)
    except Exception as e:  # noqa: BLE001
        logger.warning("HWPX 후처리 실패(_apply_accent_header): %s", e)
    # 2단 본문 — 간단 헤더를 머릿말에 그린 COM 경로(폼 모드 X)에서만. 섹션 colPr=2 + 위 여백.
    # write() 가 columns==2 면 compact_header 를 머릿말에 두므로 본문만 2단이 된다(§42-5).
    if columns == 2 and not use_form:
        try:
            # top 여백을 컴팩트 헤더 실제 높이에 맞춤(폼의 top=header 정렬, §42-6 동적화).
            # write() 와 동일하게 title 없으면 document.title 폴백 — 그려질 줄 수와 일치시킴.
            hdr_meta = dict(header_meta or {})
            if not hdr_meta.get("title"):
                hdr_meta["title"] = document.title or ""
            # 헤더 실제 높이 — _apply_body_columns 가 대수회 top(15mm)을 바닥값으로 max().
            # 보통 헤더(제목+정보 ~12mm) < 15mm 라 정확히 대수회값, 길면 grow(겹침 0).
            top_mm = compact_header_height_mm(hdr_meta)
            _apply_body_columns(output_path, top_mm=top_mm, divider=divider, margins=margins)
        except Exception as e:  # noqa: BLE001
            logger.warning("HWPX 후처리 실패(_apply_body_columns): %s", e)
    # 폰트팩 — header.xml fontfaces 의 바탕/돋움 계열 face 를 웹이 정한 글꼴로 치환(저장 후 XML).
    # font None(system 팩 또는 구버전 payload)이면 no-op(함초롬 유지). COM 글꼴면 설정 불가(§40
    # 색과 동일 한계)라 XML 후처리가 유일. form_mode 무관(폼 .hwpx 도 header.xml 에 fontfaces).
    if font:
        try:
            _apply_body_font(output_path, font)
        except Exception as e:  # noqa: BLE001
            logger.warning("HWPX 후처리 실패(_apply_body_font): %s", e)
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
        _inject_bogi_form(output_path, columns=columns, margins=margins)
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


def _fill_tokens(hwpx_path: str | Path, values: dict) -> int:
    """폼 .hwpx 의 ``{{토큰}}`` 을 시험지 정보 값으로 치환(머릿말/꼬릿말·헤더 블록 모두).

    스타터 폼은 각 칸에 ``{{학교}}`` 등 토큰을 써 두고, 변환 때 이 함수가 meta 값으로
    바꾼다. 값은 XML escape(&,<,> → 엔티티). 토큰이 한 run 에 온전할 때 동작 — 스타터
    생성물 + 사용자가 토큰 글자를 그대로 둔 경우. (한글에서 토큰 중간을 재서식하면 run 이
    쪼개져 매치 실패 → 토큰이 그대로 보일 수 있으니 '토큰 글자는 그대로 두기'를 안내.)

    Returns: 치환한 토큰 개수.
    """
    import html

    hwpx_path = Path(hwpx_path)
    with zipfile.ZipFile(hwpx_path) as zin:
        infos = zin.infolist()
        contents = {i.filename: zin.read(i.filename) for i in infos}

    def esc(v: object) -> str:
        return html.escape(str(v), quote=False)

    total = 0
    for name in list(contents.keys()):
        if not name.endswith(".xml"):
            continue
        try:
            text = contents[name].decode("utf-8")
        except UnicodeDecodeError:
            continue
        if "{{" not in text:
            continue
        changed = False
        for token, val in values.items():
            for pat in ("{{%s}}" % token, "{{ %s }}" % token):
                if pat in text:
                    total += text.count(pat)
                    text = text.replace(pat, esc(val))
                    changed = True
        if changed:
            contents[name] = text.encode("utf-8")
    if total:
        _rewrite_zip(hwpx_path, infos, contents)
    return total


# HWP 길이 단위: 1mm ≈ 283.465 (1/7200 inch). 웹에서 mm 로 설정한 여백을 변환.
_MM_TO_HWP = 283.465


def _margin_tag(
    top_mm: float = 12.0,
    bottom_mm: float = 12.0,
    left_mm: float = 15.0,
    right_mm: float = 15.0,
    header_mm: float = 8.0,
    footer_mm: float = 10.0,
) -> str:
    """mm 여백 → ``<hp:margin .../>`` 태그. 머리말 8mm·꼬리말 10mm(페이지번호 자리) 기본."""
    def u(mm: float) -> int:
        return max(0, round(mm * _MM_TO_HWP))
    return (
        f'<hp:margin header="{u(header_mm)}" footer="{u(footer_mm)}" gutter="0" '
        f'left="{u(left_mm)}" right="{u(right_mm)}" top="{u(top_mm)}" bottom="{u(bottom_mm)}"/>'
    )


# 폼 스타터 기본 여백(좌우 15mm·상하 12mm). 웹에서 여백을 보내면 변환 때 이를 덮어쓴다.
_TIGHT_MARGIN_TAG = _margin_tag()


def _set_page_margins(hwpx_path: str | Path, margin_tag: str = _TIGHT_MARGIN_TAG) -> int:
    """section XML 의 쪽 여백 ``<hp:margin .../>`` 을 좁은 값으로 교체.

    `<hp:cellMargin>`/`<hp:outMargin>` 등 다른 margin 태그는 이름이 달라 매치 안 됨
    (`<hp:margin\\b`). section 마다 1개(pagePr 안). Returns 교체 개수.
    """
    hwpx_path = Path(hwpx_path)
    with zipfile.ZipFile(hwpx_path) as zin:
        infos = zin.infolist()
        contents = {i.filename: zin.read(i.filename) for i in infos}
    total = 0
    for name in list(contents.keys()):
        if not (name.endswith(".xml") and "section" in name.lower()):
            continue
        try:
            text = contents[name].decode("utf-8")
        except UnicodeDecodeError:
            continue
        new_text, n = re.subn(r"<hp:margin\b[^>]*/>", margin_tag, text)
        if n:
            contents[name] = new_text.encode("utf-8")
            total += n
    if total:
        _rewrite_zip(hwpx_path, infos, contents)
    return total


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

# bogi 5×5 폼 템플릿의 레퍼런스 총폭(bogi_box_template.py <hp:sz width>). 2단 스케일 기준.
_BOGI_BASE_WIDTH = 29307
# bogi 박스의 outMargin(좌+우 = 283×2). 2단 칼럼 fit 계산 시 차감(박스 footprint = 표폭+이것).
_BOGI_OUT_MARGIN = 566


def _scale_bogi_box_width(tbl: str, target: int) -> str:
    """bogi 5×5 병합표를 칼럼 폭(target)에 맞춰 비례 스케일(저장 후 XML).

    템플릿의 수치 ``width="N"`` 은 표크기(<hp:sz>)+셀폭(<hp:cellSz>) 뿐이고 모두 29307 기준
    비례값이라, 일괄 ratio 곱으로 행별 합·병합(colSpan) 구조가 그대로 보존된다. cellMargin/
    outMargin/inMargin 은 left/right(=width 아님), lineseg 는 horzsize → 불변. widthRelTo=
    "ABSOLUTE" 는 토큰이 ``width=`` 와 달라 매칭 안 됨. target<=0/base 면 그대로(1단).
    """
    if target <= 0 or target == _BOGI_BASE_WIDTH:
        return tbl
    ratio = target / _BOGI_BASE_WIDTH
    return re.sub(
        r'width="(\d+)"',
        lambda m: 'width="%d"' % max(int(round(int(m.group(1)) * ratio)), 1),
        tbl)


def _inject_bogi_form(hwpx_path: str | Path, columns: int = 1,
                      margins: dict | None = None) -> int:
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
            # 2단: 5×5 박스(기본 29307=103mm)를 칼럼 폭에 맞춰 비례 축소(단 overflow 방지).
            # target = 칼럼폭 − outMargin → 박스 footprint(표폭+outMargin) 가 칼럼 안에 들어감.
            # 칼럼 폭은 좌우 여백 프리셋 반영(§42-10) — margins 없으면 대수회 기본.
            if columns == 2:
                _l, _r, _ = _margins_2col_units(margins)
                new_tbl = _scale_bogi_box_width(
                    new_tbl, _col_width_2col(_l, _r) - _BOGI_OUT_MARGIN)

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
