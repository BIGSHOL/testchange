# -*- coding: utf-8 -*-
"""인쇄 템플릿 6종 헤더를 HWP COM 으로 렌더한다.

웹(Math-Gen)에서 고른 폼(템플릿 + 시험지 정보)이 .hwp 출력에도 *그대로 유지*
되도록 하기 위함(§내보내기 고도화). HwpComWriter.write() 가 제목 한 줄만 그리던
것을 이 모듈의 dispatcher 로 분기한다.

설계:
  - render_template_header(s, template, meta, accent_rgb) 가 템플릿별 헤더 함수 호출.
  - 미지원/누락 template → _header_jeongtong (현재는 _header_default 폴백) → 회귀 0.
  - 헤더 함수는 HwpSession 프리미티브(text/align_*/break_para/table_*/set_char_shape)
    만 사용 — core.hwp_com 에 의존하지 않아(인자로 받은 s 만 사용) 순환 import 없음.

meta dict (server.adapter.adapt_payload 산출):
  title / subject / grade / schoolName / semester / examDate / examDuration /
  examiner / totalScore / academyName / instructorName / conceptNote / todayGoal /
  patternName / patternStrategy.

accent_rgb: (r, g, b) 0-255. 빈 accent 면 템플릿 기본색(TEMPLATE_DEFAULT_ACCENT).
  Phase 0 에서는 무채색 헤더만 있어 accent 미사용 — Phase 3(글자색/셀음영) 이후 활용.

구현 단계(점진):
  - Phase 0(현재): dispatcher + _header_default(제목만, 기존 동작) 로 전 템플릿 폴백.
  - Phase 1~5: jeongtong → pyeongga → (색 prerequisite) → workbook/yuhyung/modern → jaseup
    순으로 각 _header_* 를 실제 헤더로 교체.
"""
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_TEMPLATE = "jeongtong"

# 엔진 루트의 forms/ — 사용자가 한글에서 다듬은 폼 .hwpx/.hwp 를 둔다.
_FORMS_DIR = Path(__file__).resolve().parent.parent / "forms"

# 템플릿 기본 강조색 — 웹 PAPER_COLORS(tokens.ts)와 일치 (#RRGGBB → (r,g,b)).
# pyeongga/jeongtong 은 무채색(ink) — accent 미사용.
TEMPLATE_DEFAULT_ACCENT: dict[str, tuple[int, int, int]] = {
    "pyeongga": (0x0E, 0x0E, 0x10),
    "jeongtong": (0x0E, 0x0E, 0x10),
    "modern": (0x1B, 0x2A, 0x4E),    # navy
    "workbook": (0x8B, 0x1A, 0x1A),  # red
    "jaseup": (0xA5, 0x7F, 0x00),    # gold
    "yuhyung": (0x47, 0x55, 0x69),   # slate
}

_INK = (0x0E, 0x0E, 0x10)


def _hex_to_rgb(value: str) -> tuple[int, int, int] | None:
    """'#1B2A4E' / '1B2A4E' → (27, 42, 78). 형식 불량이면 None."""
    if not isinstance(value, str):
        return None
    h = value.strip().lstrip("#")
    if len(h) != 6:
        return None
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return None


def resolve_accent_rgb(template: str, accent_color: str) -> tuple[int, int, int]:
    """accent_color(#RRGGBB) 우선 → 템플릿 기본색 → ink. 항상 유효한 (r,g,b)."""
    return (
        _hex_to_rgb(accent_color)
        or TEMPLATE_DEFAULT_ACCENT.get(template or DEFAULT_TEMPLATE)
        or _INK
    )


def _g(meta: dict, key: str) -> str:
    """meta[key] 를 trim 한 문자열로(없거나 빈 문자열이면 '')."""
    v = meta.get(key) if isinstance(meta, dict) else None
    return v.strip() if isinstance(v, str) and v.strip() else ""


def _header_default(s, meta: dict) -> None:
    """제목만 가운데 정렬 — 기존 write() 동작과 byte 동일(회귀 0).

    아직 전용 헤더가 없는 템플릿의 폴백.
    """
    title = _g(meta, "title")
    if title:
        s.align_center()
        s.text(title)
        s.break_para()
        s.align_left()
        s.break_para()


# 헤더 표 폭(HWP 단위) = 본문 텍스트 폭과 일치시켜 헤더·문항 우측 끝을 맞춘다.
# A4 59528 - 좌우 여백(기본 15mm×2 = 8504) = 51024 ≈ 180mm. 본문 lineseg horzsize 와 동일.
# (이전 42000=148mm 는 본문보다 좁아 "문항이 헤더보다 우측으로 빠져나감" — 사용자 보고 2026-06-23.)
# 비기본 여백(좁게/넓게)은 변환 시 _fit_header_tables 가 실제 텍스트 폭으로 재조정(오버플로 방지).
_HEADER_WIDTH = 51024


def _grid(s, rows, *, bold=None, center=True, line_width=_HEADER_WIDTH, col_widths=None) -> None:
    """문자열 2D 배열로 표를 만들고 채운다(_write_equation_table 패턴 미러).

    셀마다 정렬·글자모양을 직접 지정 — COM 에서 검증된 안전 경로.
      - bold: 볼드로 그릴 (row, col) 집합(라벨 셀).
      - center: True 면 셀 가운데정렬, False 면 좌측정렬.
    빈 셀은 비운다(텍스트 미입력). 표 종료 후 좌측정렬 복귀.
    """
    if not rows:
        return
    nrow = len(rows)
    ncol = max(len(r) for r in rows)
    bold = bold or set()
    s.align_left()
    s.table_begin(nrow, ncol, line_width=line_width, col_widths=col_widths)
    last = (nrow - 1, ncol - 1)
    for ri in range(nrow):
        for ci in range(ncol):
            if center:
                s.align_center()
            else:
                s.align_left()
            cell = rows[ri][ci] if ci < len(rows[ri]) else ""
            val = cell.strip() if isinstance(cell, str) else str(cell)
            if (ri, ci) in bold:
                s.set_char_shape(s.base_pt, bold=True)
                if val:
                    s.text(val)
                s.set_char_shape(s.base_pt, bold=False)
            elif val:
                s.text(val)
            if (ri, ci) != last:
                s.table_next_cell()
    s.table_end()
    s.align_left()


# ── 템플릿별 헤더 (Phase 1~5 에서 실제 구현으로 교체) ─────────────────
def _jeongtong_score(meta: dict) -> str:
    """총점 셀 값. COM 폴백(실 meta): 숫자 → "/ 100". 스타터(토큰 모드): "{{배점}}" →
    파생 토큰 "{{점수표기}}"(변환 때 token_values 가 "/ 100" 또는 빈값으로 — 잔여 기호 0).
    """
    total = meta.get("totalScore")
    if isinstance(total, (int, float)):
        return f"/ {int(total)}"
    if isinstance(total, str) and total.strip():
        t = total.strip()
        return "{{점수표기}}" if t == "{{배점}}" else t
    return ""


def _jeongtong_has_info(meta: dict) -> bool:
    return any(
        _g(meta, k)
        for k in ("schoolName", "grade", "subject", "examDate", "examDuration", "examiner")
    ) or bool(_jeongtong_score(meta))


# 헤더 라벨 셀 텍스트(음영 #F4F4F6 대상 — _shade_header_labels 가 공백 제거 후 매칭).
# 웹 JeongtongTemplate 의 tdLabel(ink04 배경) 셀과 1:1 대응.
_JEONGTONG_LABELS = (
    "학교", "학년", "과목", "일시", "시간", "출제", "반", "번호", "이름", "점수",
)


def _jeongtong_title_banner(s, title: str) -> None:
    """제목 배너 — 풀폭 1×1 표 안에 큰 볼드 제목(가운데). 웹의 colSpan 제목행 대응.
    아래 정보표와 테두리가 맞닿아 한 블록처럼 보인다.
    """
    if not title:
        return
    s.align_left()
    s.table_begin(1, 1, line_width=_HEADER_WIDTH)
    s.align_center()
    s.set_char_shape(18, bold=True)
    s.text(title)
    s.set_char_shape(s.base_pt, bold=False)
    s.table_end()
    s.align_left()


def _jeongtong_tables(s, meta: dict) -> None:
    """시험정보 표(2×6) + 학생/점수 표(1×10) + 유의사항 박스(1×1). 무채색(라벨 음영은 후처리).

    웹 JeongtongTemplate 과 일치: 학교/학년/과목 · 일시/시간/출제 / 학년·반·번호·이름 + 점수.
    헤더(본문 블록)와 폼 본문 page-1 블록이 공유 — 단일 소스.
    col_widths 로 긴 값(시험일·출제자) 칸을 넓혀 글자 뭉개짐 방지(렌더 검증 2026-06-23).
    """
    _grid(
        s,
        [
            ["학 교", _g(meta, "schoolName"), "학 년", _g(meta, "grade"),
             "과 목", _g(meta, "subject") or "수학"],
            ["일 시", _g(meta, "examDate"), "시 간", _g(meta, "examDuration"),
             "출 제", _g(meta, "examiner")],
        ],
        bold={(0, 0), (0, 2), (0, 4), (1, 0), (1, 2), (1, 4)},
        col_widths=[8, 24, 8, 12, 8, 16],
    )
    # 학생 기입(학년·반·번호·이름) + 점수. 이름·점수 칸을 넓게.
    _grid(
        s,
        [["학년", "", "반", "", "번호", "", "이름", "", "점 수", _jeongtong_score(meta)]],
        bold={(0, 0), (0, 2), (0, 4), (0, 6), (0, 8)},
        col_widths=[8, 9, 7, 9, 8, 9, 8, 16, 9, 17],
    )
    s.align_left()
    s.table_begin(1, 1, line_width=_HEADER_WIDTH)
    s.align_left()
    s.set_char_shape(9)
    s.text("※ 답안은 OMR 카드에 컴퓨터용 사인펜으로 표기하시오. 한 문항에 두 개 이상 표기한 경우 0점 처리합니다.")
    s.set_char_shape(s.base_pt)
    s.table_end()
    s.align_left()


def _header_jeongtong(s, meta: dict, accent: tuple[int, int, int]) -> None:
    """정통 내신형 (COM 폴백 — 폼 파일 없을 때). 제목 배너 + 시험정보/학생/유의사항 표를 본문에.

    시험지 정보가 하나라도 있으면 표 헤더, 없으면(gui/legacy) 제목만 — 회귀 0.
    """
    if not _jeongtong_has_info(meta):
        _header_default(s, meta)
        return
    _jeongtong_title_banner(s, _g(meta, "title"))
    _jeongtong_tables(s, meta)
    s.align_left()
    s.break_para()
    s.set_char_shape(s.base_pt, bold=False)


def _header_pyeongga(s, meta: dict, accent: tuple[int, int, int]) -> None:
    _header_default(s, meta)


def _header_modern(s, meta: dict, accent: tuple[int, int, int]) -> None:
    _header_default(s, meta)


def _header_workbook(s, meta: dict, accent: tuple[int, int, int]) -> None:
    _header_default(s, meta)


def _header_jaseup(s, meta: dict, accent: tuple[int, int, int]) -> None:
    _header_default(s, meta)


def _header_yuhyung(s, meta: dict, accent: tuple[int, int, int]) -> None:
    _header_default(s, meta)


_DISPATCH = {
    "jeongtong": _header_jeongtong,
    "pyeongga": _header_pyeongga,
    "modern": _header_modern,
    "workbook": _header_workbook,
    "jaseup": _header_jaseup,
    "yuhyung": _header_yuhyung,
}


def render_template_header(s, template: str, meta: dict, accent_rgb: tuple[int, int, int]) -> None:
    """고른 템플릿의 헤더를 현재 캐럿 위치(문서 맨 앞)에 렌더한다.

    미지원/누락 template → jeongtong 폴백. meta 누락 → 빈 dict.
    헤더 함수는 끝에서 좌측 정렬·기본 글자모양으로 복귀해 본문이 정상 입력되게 한다.

    ※ 이 COM 헤더는 *폼 파일이 없을 때의 폴백*(근사). 폼 파일(forms/<template>.hwpx)이
       있으면 커넥터가 template_path 로 그 폼을 써서 *픽셀 완벽* 헤더를 쓰고 이 함수는 호출 안 함.
    """
    fn = _DISPATCH.get(template or DEFAULT_TEMPLATE, _header_jeongtong)
    fn(s, meta or {}, accent_rgb or _INK)


# ── 폼(.hwp) 파일 + 토큰 치환 ──────────────────────────────────────────
# (토큰 한글명, meta dict 키). 스타터 폼은 각 칸에 "{{토큰}}"을 써 두고, 변환 시
# 커넥터가 meta 값으로 치환한다. 스타터 생성·치환이 *같은 표*를 공유해 어긋남 0.
TOKEN_FIELDS: list[tuple[str, str]] = [
    ("제목", "title"),
    ("학교", "schoolName"),
    ("학년", "grade"),
    ("과목", "subject"),
    ("학기", "semester"),
    ("시험일", "examDate"),
    ("시험시간", "examDuration"),
    ("출제자", "examiner"),
    ("배점", "totalScore"),
    ("학원명", "academyName"),
    ("강사명", "instructorName"),
    ("오늘의목표", "todayGoal"),
    ("개념정리", "conceptNote"),
    ("유형명", "patternName"),
    ("전략", "patternStrategy"),
]


def starter_meta(template: str) -> dict:
    """스타터 폼 생성용 meta — 모든 필드를 "{{토큰}}" 문자열로. 헤더 함수가
    템플릿별로 쓰는 칸에만 토큰이 들어간다(예: jeongtong → 제목/학교/학년/…/배점).
    """
    return {meta_key: "{{%s}}" % token for token, meta_key in TOKEN_FIELDS}


def token_values(meta: dict) -> dict:
    """meta dict → {토큰명: 문자열 값}. 빈 값은 ""(치환 시 토큰 제거). 변환 경로 전용."""
    out: dict[str, str] = {}
    for token, meta_key in TOKEN_FIELDS:
        v = meta.get(meta_key) if isinstance(meta, dict) else None
        if isinstance(v, (int, float)):
            out[token] = str(int(v) if float(v).is_integer() else v)
        elif isinstance(v, str):
            out[token] = v.strip()
        else:
            out[token] = ""
    # 파생 토큰: 점수 표기 — 값 있으면 "/ 100", 없으면 ""(폼의 "/ {{점수표기}}" 잔여 없이 빈칸).
    score = meta.get("totalScore") if isinstance(meta, dict) else None
    if isinstance(score, (int, float)):
        out["점수표기"] = f"/ {int(score) if float(score).is_integer() else score}"
    elif isinstance(score, str) and score.strip() and not score.strip().startswith("{{"):
        out["점수표기"] = f"/ {score.strip()}"
    else:
        out["점수표기"] = ""
    return out


def resolve_form_path(template: str) -> str | None:
    """forms/<template>.hwpx (또는 .hwp) 가 있으면 절대경로, 없으면 None(COM 헤더 폴백)."""
    if not template:
        template = DEFAULT_TEMPLATE
    for ext in (".hwpx", ".hwp"):
        p = _FORMS_DIR / f"{template}{ext}"
        if p.exists():
            return str(p)
    return None


# ── 폼 레이아웃 생성 (스타터 전용 — 머릿말/페이지번호 자동 생성) ──────────────
# 스타터 폼 생성기가 호출. COM 으로 머릿말 영역(러닝 헤더) + 자동 페이지 번호를 만들고,
# 본문 page-1 에 상세 시험정보 블록 + (그 뒤로 변환 시 문항이 흐를) 자리를 둔다.
# 변환 시점엔 이 함수가 아니라 *폼 파일*(template_path)이 쓰이므로 meta 는 항상 토큰.

def _form_jeongtong(s, meta: dict, accent: tuple[int, int, int]) -> None:
    # 러닝 머릿말은 생략 — 상세 박스가 1쪽에서 시험을 다 식별하므로 2쪽+ 문항 공간을
    # 최대화한다(사용자 결정 2026-06-23). 페이지 번호만 꼬릿말 위치(아래 가운데)에.
    # (평가원식 러닝 헤더가 필요하면 여기서 s.header_begin(0)…s.region_end() 추가.)
    s.insert_page_number()
    # 본문 page-1: 제목 배너 + 상세 시험정보/학생/유의사항 표 (그 뒤로 문항 flow)
    s.set_char_size(s.base_pt)
    s.align_left()
    _jeongtong_title_banner(s, _g(meta, "title"))
    _jeongtong_tables(s, meta)
    s.break_para()


def _form_generic(s, meta: dict, template: str, accent: tuple[int, int, int]) -> None:
    """전용 폼 빌더가 없는 템플릿 — 러닝 헤더(제목) + 페이지번호 + 본문 COM 헤더."""
    s.header_begin(0)
    s.align_center()
    s.set_char_shape(9)
    s.text(_g(meta, "title"))
    s.set_char_shape(s.base_pt)
    s.region_end()
    s.insert_page_number()
    s.set_char_size(s.base_pt)
    s.align_left()
    render_template_header(s, template, meta, accent)


_FORM_DISPATCH = {
    "jeongtong": _form_jeongtong,
}


def generate_form_layout(s, template: str, meta: dict, accent_rgb: tuple[int, int, int]) -> None:
    """스타터 폼 레이아웃 생성 — 머릿말/페이지번호(COM 자동) + 본문 블록.

    전용 빌더(_form_*)가 있으면 그걸로, 없으면 _form_generic. 스타터 생성기가 호출.
    """
    fn = _FORM_DISPATCH.get(template or DEFAULT_TEMPLATE)
    if fn is not None:
        fn(s, meta or {}, accent_rgb or _INK)
    else:
        _form_generic(s, meta or {}, template or DEFAULT_TEMPLATE, accent_rgb or _INK)
