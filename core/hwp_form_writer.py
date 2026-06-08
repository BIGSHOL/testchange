# -*- coding: utf-8 -*-
"""대수회 폼지(.hwp)에 ExamDocument를 자동으로 채워 시험지를 만드는 writer.

2단계 파이프라인:
  1) **COM 채움**(`_fill_form`): 폼을 열어 슬롯 수를 문항 수에 맞게 조절하고,
     미주(문항번호) 앵커·보기 마커(①②③④⑤)를 찾아 문제 본문/보기를 채운다.
  2) **XML 행정렬 레이아웃**(`_layout_form`): 저장된 hwpx를 후처리해 폼의 과잉 빈줄을
     제거하고, 측정한 문항 높이로 1단·2단 문항을 같은 줄에 정렬(행정렬)한 뒤
     단나누기(columnBreak)를 건다.

⚠️ 구현 함정은 `CLAUDE.md` 의 '폼 자동입력 구현 교훈' 참고. 핵심:
  - columnBreak 는 ``<hp:endNote>`` 를 가진 **바깥** ``<hp:p>`` 에만 먹는다(미주 subList 의
    안쪽 ``<hp:p>`` 아님).
  - 섹션 XML 을 findall+join 으로 **재조립 금지**(구역/단 정의 누락 → 백지). 위치기반 편집만.
  - 빈줄 템플릿은 secPr 단락 금지·fabricate 금지. ``is_empty`` 는 **모든 태그 제거 후** 판정.
  - 고아 Hwp.exe 정리, 잠긴 출력 파일은 ``os.replace`` 무효 → 새 파일명 사용.

현재 범위(MVP): 객관식(보기 있는 문항)만. 서술형/표 셀 수식은 후속.
"""
from __future__ import annotations

import logging
import math
import os
import re
import shutil
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)

from .hwp_com import CONVERSION_VISIBLE, HwpSession, _dispatch_hwp, _win32
from .hwp_com_writer import (HwpComWriter, _BOX_BREAK_RE, _BULLET_RE,
                             _COND_HEADER_RE, _condition_start, _has_box_markup,
                             _split_tail_post, _split_trailing_score, _tail_start)
from .latex_to_hwpeq import latex_to_hwpeq
from models.exam_document import ContentBlock, ContentType, ExamDocument, Question

# ── 설정 ──────────────────────────────────────────────────
PER_COL = 3          # 한 단에 들어갈 문항 수(최대) — 페이지당 2단 = 6문항
CAP = 46             # 한 단의 줄 용량(채움 목표; 실측 ~42 + 헤더 오프셋 여유)
LONG_CHOICE_LEN = 15 # 짝 보기(①②③④) 최대 길이 ≥ 이 값이면 1열 배치
CHARS_PER_LINE = 18  # 줄 수 추정용(현재 미사용 — 측정값 우선)
CIRCLES = ["①", "②", "③", "④", "⑤"]
ESSAY_SUB_BLANKS = 3   # 서술형 소문항마다 답안 공간(빈 줄 수)
_MINGAP = 1
# 폼 그림 표시 최대 가로 픽셀. insert_picture 는 원본 픽셀 크기로 삽입하므로
# (96dpi: 260px≈69mm) 단 너비(≈80mm)를 넘지 않게 축소해 단 넘침을 막는다.
FORM_FIG_MAX_W = 260

# 머리말/꼬리말 '과목' 자리 매칭 — 수학뿐 아니라 미적분·기하·확률과 통계 등 모든 과목(비캡처).
# 폼마다 placeholder 과목이 달라(선택과목 폼은 "미적분") 수학만 매칭하면 치환 실패(사용자 2026-06-08).
_SUBJ_PAT = r'(?:수학\s*[12]?|수\s*[12]|대수|미적분\s*[12]?|기하|확률과\s*통계|확통|통계)'
# 파일명 약칭 → 머리말 표기 정식명.
_SUBJ_DISPLAY = {
    "확통": "확률과 통계", "확률과통계": "확률과 통계",
    "미적분1": "미적분", "미적분2": "미적분",
    "수1": "수학", "수2": "수학", "수학1": "수학1", "수학2": "수학2",
}


def _fit_image_width(path: str, max_w: int = FORM_FIG_MAX_W) -> str:
    """그림을 흰 배경으로 평탄화하고, max_w(px)보다 넓으면 비율 유지 축소한 임시 PNG.

    - 투명 배경(resvg SVG 출력 등) → RGB 변환 시 검정으로 합성되어 그림이 안 보이므로
      반드시 **흰 배경으로 평탄화**(검정화 방지).
    - insert_picture 는 원본 픽셀 크기로 삽입 → 단 너비를 넘는 큰 그림은 미리 축소(단 넘침 방지).
    항상 흰배경 임시 PNG 를 새로 만들어 반환(원본 그대로 반환 안 함 = 투명 위험 제거).
    """
    try:
        from PIL import Image as _Image
        with _Image.open(path) as im0:
            rgba = im0.convert("RGBA")
            bg = _Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            im = _Image.alpha_composite(bg, rgba).convert("RGB")
        w, h = im.size
        if w > max_w:
            im = im.resize((max_w, max(1, int(h * max_w / w))), _Image.LANCZOS)
        out = os.path.join(tempfile.gettempdir(), f"formfig_{os.path.basename(path)}")
        if not out.lower().endswith(".png"):
            out += ".png"
        im.save(out)
        return out
    except Exception:
        return path


# ── 저수준 COM 헬퍼 ───────────────────────────────────────
def _en_anchors(hwp) -> list[tuple[int, int, int]]:
    """본문 미주(en=문항번호) 앵커 위치 목록 (List, Para, Pos), **문서 위치순 정렬**.

    HeadCtrl 연결리스트는 컨트롤 **생성 순서**라, 슬롯을 Paste 로 복제하면 새 미주가
    리스트 끝에 붙어 문서 위치와 어긋난다. 채움/삭제는 위치 인덱스로 동작하므로 반드시
    (List, Para, Pos) 로 정렬해 문서 순서를 보장해야 한다(안 하면 인접 슬롯 오삭제).
    """
    out = []
    ctrl = hwp.HeadCtrl
    while ctrl is not None:
        if ctrl.CtrlID == "en":
            ap = ctrl.GetAnchorPos(0)
            out.append((ap.Item("List"), ap.Item("Para"), ap.Item("Pos")))
        ctrl = ctrl.Next
    return sorted(out)


def _merge_sections(hwp) -> None:
    """문서의 구역나누기(secd)를 모두 제거해 **단일 구역**으로 병합.

    폼은 2구역(객관식 일부 + 서술형/정답)이라, 슬롯 삭제가 구역 경계를 넘지 않는 경우
    (예: 14개 이상 객관식, 또는 슬롯 복사)에는 2구역으로 남는다. 그러면 XML 레이아웃
    (`_build_layout`)이 section0 만 처리해 서술형/정답 레이아웃·짝수쪽 쪽나누기가 적용되지
    않는다. 완성본(수기)도 단일 구역이므로, 채움 전에 구역을 병합해 항상 단일 section0 로
    만든다. (secd 단락 줄 시작에서 DeleteBack → 앞 구역과 합쳐짐.)
    """
    for _ in range(8):  # 구역나누기 수만큼(보통 1) 반복, 안전 상한
        # 문서 시작의 **초기 구역정의**(para==0)는 지울 수 없으므로 제외. 실제 구역나누기
        # (para>0) 중 가장 앞을 골라 그 줄 시작에서 DeleteBack → 앞 구역과 병합.
        pos = None
        ctrl = hwp.HeadCtrl
        while ctrl is not None:
            if ctrl.CtrlID == "secd":
                ap = ctrl.GetAnchorPos(0)
                p = (ap.Item("List"), ap.Item("Para"), ap.Item("Pos"))
                if p[1] > 0 and (pos is None or p[1] < pos[1]):
                    pos = p
            ctrl = ctrl.Next
        if pos is None:
            return
        hwp.SetPos(pos[0], pos[1], pos[2])
        hwp.Run("MoveLineBegin")
        hwp.Run("DeleteBack")


def _answer_block_pos(hwp) -> tuple[int, int, int] | None:
    """정답(답지) 블록 시작 위치 = 본문(list 0) **마지막 gso**(답안표 그리기객체) 앵커.

    폼 끝 정답 페이지는 본문 마지막 gso 로 앵커된다(머리말 로고 gso 는 para 0). 잉여
    서술형 슬롯을 지울 때 이 위치 **앞까지만** 삭제해야 정답 페이지가 보존된다.
    """
    best = None
    ctrl = hwp.HeadCtrl
    while ctrl is not None:
        if ctrl.CtrlID == "gso":
            ap = ctrl.GetAnchorPos(0)
            if ap.Item("List") == 0:
                p = ap.Item("Para")
                if best is None or p > best[1]:
                    best = (0, p, 0)
        ctrl = ctrl.Next
    return best


def _repeat_find(hwp, s: str) -> bool:
    fp = hwp.HParameterSet.HFindReplace
    hwp.HAction.GetDefault("RepeatFind", fp.HSet)
    fp.FindString = s
    fp.IgnoreMessage = 1
    fp.Direction = 0
    return hwp.HAction.Execute("RepeatFind", fp.HSet)


def _find_all(hwp, s: str, count: int) -> list[tuple[int, int, int]]:
    """문서 처음부터 ``s`` 를 최대 count 개까지 찾아 각 매치 **뒤** 캐럿 위치를 모은다.

    RepeatFind 는 끝에 도달하면 처음으로 **순환(wrap)** 한다. 위치가 더 이상 전진하지
    않으면(역행/제자리) 순환으로 보고 멈춘다 → 실제 개수만 정확히 센다.
    """
    hwp.Run("MoveDocBegin")
    pts = []
    for _ in range(count):
        if not _repeat_find(hwp, s):
            break
        hwp.Run("Cancel")          # 선택 해제 → 캐럿이 매치 뒤
        p = hwp.GetPos()
        if pts and (p[1], p[2]) <= (pts[-1][1], pts[-1][2]):
            break                  # 전진 안 함 → 순환(wrap), 중복 방지
        pts.append(p)
    return pts


# 본문(발문·보기·배점·서술형) 글자 크기(pt). HwpSession.base_pt 기본(11)과 일치해야 한다.
# 미주 번호만 12pt(폼 스타일), 본문은 11pt(사용자 요구 2026-06-05).
_BODY_PT = 11


def _set_plain(hwp, pt: int | None = _BODY_PT) -> None:
    """캐럿 글자모양: 볼드 해제 + 장평/상대크기 100 + **본문 크기(pt)로 고정**.

    폼 슬롯(미주·플레이스홀더)은 12pt 글자모양이라 ``SetPos`` 로 그 자리에 가서 입력하면
    12pt 를 상속한다(사용자 보고 2026-06-05: "문항이 12pt, 미주만 12pt여야 하는데 문제도
    12pt"). 입력 직전 ``pt`` 를 명시해 발문·보기·배점을 본문 크기(11pt)로 강제한다(미주 번호
    자체는 우리가 건드리지 않으므로 12pt 유지). ``pt=None`` 이면 크기 미변경(볼드/장평만).
    """
    cs = hwp.HParameterSet.HCharShape
    hwp.HAction.GetDefault("CharShape", cs.HSet)
    try:
        cs.Bold = 0
    except Exception:
        pass
    if pt is not None:
        try:
            cs.Height = hwp.PointToHwpUnit(pt)
        except Exception:
            pass
    for sc in ("Hangul", "Latin", "Hanja", "Japanese", "Other", "Symbol", "User"):
        try:
            setattr(cs, f"Ratio{sc}", 100)
            setattr(cs, f"Size{sc}", 100)
        except Exception:
            pass
    hwp.HAction.Execute("CharShape", cs.HSet)


def _copy_range(hwp, start, end) -> None:
    """본문 구간(start~end = (list,para,pos))을 클립보드로 복사(슬롯 복제용)."""
    hwp.SelectText(start[1], start[2], end[1], end[2])
    hwp.HAction.Run("Copy")
    hwp.Run("Cancel")


def _paste_at(hwp, pos) -> None:
    """클립보드 내용을 pos 에 붙여넣기. 슬롯(미주 포함) 복제 시 미주 자동 재번호."""
    hwp.SetPos(pos[0], pos[1], pos[2])
    hwp.HAction.Run("Paste")
    hwp.Run("Cancel")


def _eq_script(block) -> str:
    return block.hwp_equation or latex_to_hwpeq(block.value)


def _put_block(ses, b) -> None:
    """ContentBlock 하나를 현재 캐럿에 삽입(수식/텍스트/그림)."""
    if b.type in (ContentType.EQUATION, ContentType.EQUATION_BLOCK):
        ses.equation(_eq_script(b))  # 숫자도 수식 객체로 유지(정렬)
    elif b.type == ContentType.TEXT:
        if b.value:
            ses.text(b.value)
    elif b.type == ContentType.IMAGE and b.value:
        # 그림 자동삽입 보류 — 가운데·독립줄에 '직접 캡처해 붙여넣으세요' 안내(사용자 2026-06-05).
        ses.break_para()
        ses.align_center()
        _place_figure(ses, ses.hwp, b.value)
        ses.break_para()
        ses.align_left()


def _fig_token(idx: int) -> str:
    """그림 위치 마킹 토큰(추후 그림 자동삽입 숙제용 — 현재 미사용)."""
    return f"그림삽입자리{idx}끝표식"


# 그림 자리 안내 문구(기본 모드 — 그림 자동삽입 보류). 그림(IMAGE)이 있던 자리에 넣어
# 사용자가 원본 PDF 영역을 직접 캡처해 붙이도록 한다. ⚠️ "[그림 …]" 으로 시작하면 HWP 가
# 그림 **캡션 필드**로 오인해 재저장 때 사라질 수 있어 "※ …" 로 시작한다. 상세: 메모리
# form-figure-pending.
_FIGURE_NOTE = "※ 그림 자리 — 원본에서 이 영역을 캡처해 여기에 붙여넣으세요"


def _place_figure(ses, h, path: str) -> bool:
    """그림(IMAGE) 자리 처리 — 모드 분기(`ses._render_figures`).

    - **렌더 모드**(True): 그림을 실제로 삽입(자리표시 pic + 토큰 → 저장후 `_embed_figures` 가
      binItem 교정). 단 보안경고가 뜬다(재저장 생략 — 재저장이 그림을 드롭하므로).
    - **기본 모드**(False): 그림 자동삽입 보류 → 그림 자리에 **1×1 테두리 박스 안내 문구**.
      재저장(launder)으로 보안경고 제거. (느슨한 단락은 재저장에 드롭되므로 **표 박스**에 넣어
      보존 — 사용자 결정 2026-06-05. 자세히: 메모리 `form-figure-pending`.)
    """
    if getattr(ses, "_render_figures", False):
        return _place_figure_embed(ses, h, path)
    return _place_figure_note(ses, h, path)


def _place_figure_embed(ses, h, path: str) -> bool:
    """렌더 모드: 그림 자리표시 pic(배너참조) + 토큰 삽입, 경로 등록(저장후 _embed_figures 교정)."""
    if not path or not os.path.exists(path):
        return False
    paths = getattr(ses, "_fig_paths", None)
    if paths is None:
        paths = []
        ses._fig_paths = paths
    idx = len(paths)
    paths.append(path)
    try:
        ses.text(_fig_token(idx))
    except Exception:
        pass
    fitted = _fit_image_width(path)
    try:
        h.InsertPicture(fitted, True, 2, 0, 0, 0, 0, 0)
    except Exception:
        try:
            h.InsertPicture(fitted, True, 2)
        except Exception:
            pass
    try:
        h.Run("MoveRight")
    except Exception:
        pass
    return True


def _place_figure_note(ses, h, path: str) -> bool:
    """기본 모드: 그림 자리에 안내 문구를 가운데 **볼드**로 넣어 눈에 띄게 한다(사용자 요구
    2026-06-05). path 는 호환 위해 받되 미사용.

    (1×1 테두리 표 박스로 감싸면 더 눈에 띄지만, 서술형 슬롯에서 COM 표 생성이 hang 을
    유발하므로 표 대신 볼드로 강조한다. "※ …" 문구라 그림 캡션 오인·재저장 드롭을 피한다 —
    실측 2026-06-05.)
    """
    try:
        ses.set_char_shape(pt=_BODY_PT, bold=True)
        ses.text(_FIGURE_NOTE)
        ses.set_char_shape(pt=_BODY_PT, bold=False)
    except Exception:
        try:
            ses.text(_FIGURE_NOTE)
        except Exception:
            pass
    return True


def _emit_box_text(ses, text: str, st: dict) -> None:
    """박스 텍스트를 줄 단위로 출력(불릿/마커/라벨 경계). st={'started','broke'} 상태 공유.

    기본 경로 `_write_box_content.emit_text` 와 동일 규칙: 불릿(•)은 줄 경계로만(미출력),
    마커(<조건>)/자모 라벨(ㄱ.)은 토큰 출력. 인접 빈 경계는 중복 줄바꿈 방지.
    """
    pos = 0
    after_label = False   # 라벨 직후면 뒤 내용 선행공백 strip(이중공백 방지, 2026-06-05)
    for m in _BOX_BREAK_RE.finditer(text):
        pre = text[pos:m.start()]
        if pre.strip():
            seg = pre if st["started"] else pre.lstrip()
            if after_label:
                seg = seg.lstrip()
            ses.text(seg)
            st["started"] = True
            st["broke"] = False
            after_label = False
        is_bullet = _BULLET_RE.fullmatch(m.group(0)) is not None
        if st["started"] and not st["broke"]:
            ses.break_para()
            st["broke"] = True
        if not is_bullet:
            tok = re.sub(r"\s+", "", m.group(0))
            ses.text(tok + " ")
            st["broke"] = False
            after_label = True
        st["started"] = True
        pos = m.end()
    tail = text[pos:]
    if tail.strip():
        seg = tail if st["started"] else tail.lstrip()
        if after_label:
            seg = seg.lstrip()
        ses.text(seg)
        st["started"] = True
        st["broke"] = False


def _put_tail(ses, h, blocks) -> None:
    """발문 뒤 영역 렌더 — **기본 경로와 동일**(사용자 '항상 동일' 요구 2026-06-05).

    그림(IMAGE)·블록수식(EQUATION_BLOCK)은 개별(그림 가운데·수식 가운데), 보기/조건은
    공유 ``HwpComWriter._write_condition_box`` 의 1×1 테두리 표 박스로 렌더한다. 단,
    **그림만 폼 전용 토큰 삽입**(``_insert_picture_inline``: COM InsertPicture 의 HWPX
    binItem 누락을 후처리 임베드로 교정)을 쓴다 — 나머지는 기본 경로 코드 그대로.
    """
    w = HwpComWriter(ses)
    core, post = _split_tail_post(blocks)          # 박스 뒤 발문 연속(#18·#20) 분리
    cs = _condition_start(core)                    # 표/조건 머리 시작(없으면 전부 pre)
    pre = core if cs is None else core[:cs]
    box = [] if cs is None else core[cs:]
    for b in pre:
        if b.type == ContentType.IMAGE and b.value:
            ses.break_para()
            ses.align_center()
            _place_figure(ses, h, b.value)         # 모드 분기(렌더/안내 박스)
            # 트레일링 break 없음 — 조건 박스가 단락시작(pos==0) 재사용으로 빈 줄 방지
        else:
            w._write_block(b)                      # EQUATION_BLOCK 가운데·EQUATION 인라인·TEXT
    if box:
        w._write_condition_box(box)
    for b in post:                                 # 박스 뒤 발문 연속 — 박스 밖, 새 줄에 이어서
        if box:
            ses.break_para()
            ses.align_left()
            box = []
        if b.type == ContentType.IMAGE and b.value:
            ses.break_para()
            ses.align_center()
            _place_figure(ses, h, b.value)
        else:
            w._write_block(b)


def _put_qbody(ses, h, contents, score, essay: bool = False) -> None:
    """문제(또는 소문항) 본문: 발문 → 배점(발문 끝) → 뒤 영역(조건/그림/블록수식).

    essay=True 면 배점을 **줄바꿈 후 우측정렬**(서술형 합의). 객관식은 발문 끝 인라인.
    """
    ts = _tail_start(contents)
    head = contents if ts is None else contents[:ts]
    tail = [] if ts is None else contents[ts:]
    for b in head:
        _put_block(ses, b)
    # 박스 뒤 발문 연속(#18·#20)이 있으면 서술형 배점은 그 뒤로 미룬다(기본 경로와 동일).
    _, tail_post = _split_tail_post(tail)
    defer_essay_score = essay and bool(score) and bool(tail_post)
    if score and not defer_essay_score:
        _put_score(ses, h, score, essay=essay)   # 객관식=발문 끝 인라인 / 서술형=우측정렬
    if tail:
        _put_tail(ses, h, tail)
        if defer_essay_score:
            _put_score(ses, h, score, essay=essay)


def _put_score(ses, h, score: int, essay: bool = False) -> bool:
    """배점 삽입 — **기본 경로(hwp_com_writer)와 동일**(사용자 '항상 동일' 요구).

    - 서술형(essay=True): **항상 줄바꿈 후 우측정렬** ``[N점]``(N 은 수식 객체).
    - 객관식: 발문 끝 인라인 ``[N점]``(N 은 수식 객체). 좁은 단에서 단독으로 다음 줄로
      넘치면 우측정렬 폴백.
    배점 숫자는 합의 #6(순수숫자도 수식 객체화)에 따라 ``ses.equation`` 으로 넣는다.

    Returns: 우측정렬 단락으로 넘겼으면 True(현재 단락이 우측정렬 상태).
    """
    def put_inline(leading_space: bool):
        ses.text(" [" if leading_space else "[")
        ses.equation(str(score))
        ses.text("점]")

    if essay:
        ses.break_para()
        ses.align_right()
        _set_plain(h)
        put_inline(leading_space=False)
        ses.break_para()
        ses.align_left()
        _set_plain(h)
        return True

    def line():
        try:
            return h.KeyIndicator()[5]
        except Exception:
            return -1

    sp = h.GetPos()
    la = line()
    put_inline(leading_space=True)
    lb = line()
    if la >= 0 and lb > la:
        h.SetPos(sp[0], sp[1], sp[2])
        h.Run("MoveSelParaEnd")
        h.HAction.Run("Delete")
        h.Run("BreakPara")
        h.Run("ParagraphShapeAlignRight")
        _set_plain(h)
        put_inline(leading_space=False)
        return True
    return False


# 소문항 앞머리 번호 마커((1)/1)/1./①…) — 우리가 마커를 별도로 붙이므로 OCR 중복분 제거.
_SUBMARK_RE = re.compile(r'^\s*(?:[\(（]\s*\d+\s*[\)）]|\d+\s*[.)]|[①-⑩])\s*')
_EQ_TYPES = (ContentType.EQUATION, ContentType.EQUATION_BLOCK)
_LEAD_CLOSE_RE = re.compile(r'^\s*[\)）.]\s*')   # 분리된 마커의 닫힘부 ") "/". "


def _blk(t, v):
    return ContentBlock(type=t, value=v)


def _strip_leading_submarker(contents):
    """소문항 앞머리 번호 마커를 제거(우리가 ``(k)`` 를 따로 렌더하므로 OCR 이 남긴
    ``(1)``·``1)``·``1.``·``①`` 등의 중복을 결정적으로 차단). 길이/형태 무관.

    ⚠️ 파서가 ``(1) 일차함수…`` 를 ``TEXT "(" + EQUATION "1" + TEXT ") 일차함수…"`` 로
    **쪼개** 첫 블록만 봐서는 못 잡는다(사용자 2026-06-08: 소문항 (1)(2) 가 우리 마커와
    중복 출력). 그래서 아래 형태를 모두 처리한다(좌표 ``(2, 3)`` 은 닫힘부가 ``,`` 라 안 걸림):
      1) 단일 텍스트 ``"(1) rest"`` / ``"1) rest"`` / ``"① rest"``
      2) 분리형 ``TEXT "(" + EQ 숫자 + TEXT ") rest"``
      3) 분리형 ``EQ 숫자 + TEXT ") rest"`` (앞 괄호 없는 ``1)``/``1.``)
      4) 마커 통째가 한 수식 ``EQ "(1)"``
    """
    if not contents:
        return contents
    c = list(contents)

    def txt(b):
        return (b.value or "") if getattr(b, "type", None) == ContentType.TEXT else None

    def eqd(b):  # 수식 블록이고 값이 순수 숫자면 그 숫자, 아니면 None
        if getattr(b, "type", None) in _EQ_TYPES and (b.value or "").strip().isdigit():
            return (b.value or "").strip()
        return None

    # 형태 1: 단일 텍스트 마커
    t0 = txt(c[0])
    if t0:
        nv = _SUBMARK_RE.sub('', t0, count=1)
        if nv != t0:
            return ([_blk(ContentType.TEXT, nv)] + c[1:]) if nv.strip() else c[1:]

    # 형태 2: "(" + EQ숫자 + ")rest"
    if (len(c) >= 3 and (t0 is not None and t0.strip() in ("(", "（"))
            and eqd(c[1]) is not None
            and txt(c[2]) is not None and _LEAD_CLOSE_RE.match(txt(c[2]))):
        rest = _LEAD_CLOSE_RE.sub('', txt(c[2]), count=1)
        return ([_blk(ContentType.TEXT, rest)] if rest.strip() else []) + c[3:]

    # 형태 3: EQ숫자 + ")rest" 또는 ".rest"
    if (len(c) >= 2 and eqd(c[0]) is not None
            and txt(c[1]) is not None and _LEAD_CLOSE_RE.match(txt(c[1]))):
        rest = _LEAD_CLOSE_RE.sub('', txt(c[1]), count=1)
        return ([_blk(ContentType.TEXT, rest)] if rest.strip() else []) + c[2:]

    # 형태 4: 마커 통째가 한 수식 객체 "(1)"
    if getattr(c[0], "type", None) in _EQ_TYPES and _SUBMARK_RE.fullmatch((c[0].value or "").strip()):
        return c[1:]

    return contents


def _put_total_score(ses, h, num: int) -> None:
    """소문항 부모 총점 "[총 N점]" 을 줄바꿈 후 우측정렬(N 은 수식 객체). 기본 경로와 동일."""
    ses.break_para()
    ses.align_right()
    _set_plain(h)
    ses.text("[총 ")
    ses.equation(str(num))
    ses.text("점]")
    ses.break_para()
    ses.align_left()
    _set_plain(h)


def _fill_essay_at(ses, h, pos, q: Question, label_idx: int, next_pos=None) -> None:
    """서술형 슬롯 채움: 번호줄 ``[라벨 M] 문제`` + 소문항((k) 수식 마커) + 배점.

    label_idx 는 서술형 일련번호(서답형 1, 2, …; 전체 문항번호와 별개).
    번호줄의 ``[서술형 ]`` 플레이스홀더는 삭제 후 다시 쓴다.
    next_pos: 다음 슬롯(서술형/정답) 앵커 위치. 플레이스홀더 삭제가 **단 경계를 넘어**
    다음 슬롯 미주까지 먹지 않도록 클램프한다(서술형은 1/단이라 MoveSelDown 이 다음 단의
    슬롯으로 점프해 인접 미주를 삭제하는 버그가 있었음).
    """
    label = q.label_type or "서답형"
    h.SetPos(pos[0], pos[1], pos[2])
    h.Run("MoveRight")                       # 번호(미주) 다음
    # 슬롯 템플릿: 번호줄 [서술형] + 빈줄 + 둘째 [서술형] 까지 선택 삭제([중단원] 전까지).
    h.Run("MoveSelParaEnd")                   # 번호 단락 끝(첫 [서술형])
    for _ in range(2):
        h.Run("MoveSelDown")
        cur = h.GetPos()
        if next_pos is not None and cur[1] >= next_pos[1]:   # 다음 슬롯 침범
            h.Run("MoveSelUp")                # 한 줄 되돌림
            break
    h.Run("MoveSelParaEnd")                   # 둘째 [서술형] 단락 끝
    end = h.GetPos()
    if next_pos is not None and end[1] >= next_pos[1]:        # 그래도 넘으면 번호줄만
        h.SetPos(pos[0], pos[1], pos[2])
        h.Run("MoveRight")
        h.Run("MoveSelParaEnd")
    h.HAction.Run("Delete")
    _set_plain(h)
    ses.text(f" [{label} {label_idx}] ")
    # 발문 → 배점(발문 끝) → 조건/그림/블록수식. 소문항 있으면 본문 배점은 소문항에 위임.
    if q.sub_questions:
        # 소문항 부모: 발문 끝 [총 N점] 을 본문에서 분리해 우측정렬로 따로(기본 경로와 동일).
        body, total = _split_trailing_score(q.contents)
        if total is None:
            total = q.score
        _put_qbody(ses, h, body, None)
        if total:
            _put_total_score(ses, h, total)
        for k, sub in enumerate(q.sub_questions):
            ses.break_para()
            h.Run("ParagraphShapeAlignLeft")  # 직전 배점이 우측정렬됐어도 새 줄은 좌측
            _set_plain(h)
            ses.equation(f"({k + 1})")        # 소문항 마커 (1)(2)… 는 수식으로
            ses.text(" ")
            # OCR 이 남긴 앞머리 번호 마커 제거(우리 마커와 중복 방지) — 결정적·길이무관.
            # 소문항 배점도 서술형이면 우측정렬(기본 경로 _write_question 재귀와 동일).
            _put_qbody(ses, h, _strip_leading_submarker(sub.contents), sub.score,
                       essay=not sub.choices)
            for _ in range(ESSAY_SUB_BLANKS):  # 소문항 답안 공간(2~3줄)
                ses.break_para()
                h.Run("ParagraphShapeAlignLeft")
    else:
        _put_qbody(ses, h, q.contents, q.score, essay=True)   # 소문항 없는 서술형(우측정렬)


def _choice_len(choice) -> int:
    return sum(len(b.value or "") for b in choice.contents)


def _is_long_choices(q: Question) -> bool:
    """2열로 짝짓는 ①②③④ 중 하나라도 길면 1열 배치(⑤는 3행에 홀로)."""
    paired = sorted(q.choices, key=lambda c: c.number)[:4]
    return any(_choice_len(c) >= LONG_CHOICE_LEN for c in paired)


# ── 1단계: COM 채움 ───────────────────────────────────────
def _fill_form(mc: list[Question], essays: list[Question], form_path, out_path,
               render_figures: bool = False) -> tuple[int, int, list]:
    """폼을 열어 슬롯 수 조절 + 객관식/서술형 채움 → out_path 저장.

    폼은 앞쪽 객관식 슬롯(①②③④⑤ 사전배치) + 뒤쪽 서술형 슬롯([서술형]). 잉여 객관식
    슬롯만 삭제하면 미주 자동번호로 **서술형 번호가 객관식 다음으로 이어진다**.
    render_figures: True 면 그림 실제 삽입(저장후 _embed_figures), False 면 안내 박스.

    Returns: (채운 객관식 수, 채운 서술형 수, 그림 경로 리스트(토큰 인덱스순)).
    """
    n_mc, n_es = len(mc), len(essays)
    with HwpSession(visible=CONVERSION_VISIBLE) as ses:   # 실시간 작성 표시(스위치: CONVERSION_VISIBLE)
        h = ses.hwp
        ses._render_figures = render_figures   # 그림 처리 모드(_place_figure 가 분기)
        ses.open(form_path)
        ses.set_char_size(ses.base_pt)
        _merge_sections(h)        # 2구역 → 단일 구역(레이아웃·짝수쪽이 전 영역에 적용되도록)

        def cur_line():
            try:
                return h.KeyIndicator()[5]
            except Exception:
                return -1

        def put_choice_at(pos, choice):
            h.SetPos(pos[0], pos[1], pos[2])
            _set_plain(h)
            ses.text(" ")
            for b in choice.contents:
                _put_block(ses, b)

        def put_question_at(pos, q):
            h.SetPos(pos[0], pos[1], pos[2])
            h.Run("MoveRight")            # 번호(미주) 다음
            _set_plain(h)
            ses.text(" ")
            # 발문 → 배점(발문 끝) → 조건/그림/블록수식(뒤 영역)
            _put_qbody(ses, h, q.contents, q.score)

        # (0) 폼 슬롯 구성 파악: 객관식 슬롯 수 = ① 개수, 서술형 = 나머지.
        anc = _en_anchors(h)
        mc_form = len(_find_all(h, "①", len(anc)))
        es_form = len(anc) - mc_form

        # (0b) 문항 수 > 폼 슬롯이면 슬롯 복사(grow). 미주 자동 재번호 → 번호 연속.
        #      COM Paste 가 비결정적으로 한 번 누락/오삽입될 수 있어, **실제 개수로 자가보정**
        #      한다: 객관식 = ① 개수, 서술형 = (전체 미주 − ①). 목표 개수에 도달할 때까지
        #      반복(매 회 MoveDocBegin 으로 컨트롤 목록 flush). guard 로 무한루프 방지.
        def _mc_count():
            return len(_find_all(h, "①", len(_en_anchors(h)) + 4))

        # 객관식: 템플릿(2번 슬롯) 복사 → MC 끝(첫 서술형 앞)에 삽입.
        if n_mc > mc_form >= 2:
            a = _en_anchors(h)
            _copy_range(h, a[1], a[2])
            guard = 0
            while _mc_count() < n_mc and guard < (n_mc - mc_form) + 12:
                h.Run("MoveDocBegin")
                cur = _mc_count()
                a = _en_anchors(h)
                _paste_at(h, a[cur])                # a[현재 MC수] = 첫 서술형 = MC 끝
                guard += 1
            mc_form = n_mc
        else:
            n_mc = min(n_mc, mc_form)
        # 서술형: 템플릿(첫 서술형 슬롯) 복사 → 정답 블록 앞(서술형 끝)에 삽입.
        if n_es > es_form >= 1:
            a = _en_anchors(h)
            mc_now = _mc_count()
            end = a[mc_now + 1] if mc_now + 1 < len(a) else _answer_block_pos(h)
            _copy_range(h, a[mc_now], end)
            guard = 0
            while (len(_en_anchors(h)) - _mc_count()) < n_es and guard < (n_es - es_form) + 12:
                h.Run("MoveDocBegin")
                _paste_at(h, _answer_block_pos(h))  # 정답 블록 앞에 삽입
                guard += 1
            es_form = n_es
        else:
            n_es = min(n_es, es_form)

        # (1) 잉여 서술형 슬롯 삭제(뒤) — **정답 블록 앞까지만**(정답 페이지 보존).
        #     그 다음 잉여 객관식 슬롯 삭제(중간).
        anc = _en_anchors(h)
        ans = _answer_block_pos(h)
        if n_es < es_form and ans is not None:
            s0 = anc[mc_form + n_es]
            h.SelectText(s0[1], s0[2], ans[1], ans[2])
            h.HAction.Run("Delete")
            h.Run("Cancel")
        anc = _en_anchors(h)
        if n_mc < mc_form:
            s0 = anc[n_mc]
            e0 = anc[mc_form]          # 첫 서술형 슬롯 시작(잉여 MC 제거 → 서술형 번호 연속)
            h.SelectText(s0[1], s0[2], e0[1], e0[2])
            h.HAction.Run("Delete")
            h.Run("Cancel")

        # (2) 긴 보기 슬롯(객관식)은 ②④ 앞에 단락나눔 → 1열. (문서 위치 내림차순)
        long_slots = [_is_long_choices(q) for q in mc[:n_mc]]
        c2 = _find_all(h, "②", n_mc)
        c4 = _find_all(h, "④", n_mc)
        conv = []
        for i in range(n_mc):
            if long_slots[i]:
                if i < len(c2):
                    conv.append(c2[i])
                if i < len(c4):
                    conv.append(c4[i])
        conv.sort(key=lambda p: (p[1], p[2]), reverse=True)
        for pos in conv:
            h.SetPos(pos[0], pos[1], pos[2])
            h.Run("MoveLeft")
            h.Run("BreakPara")

        # (3) 위치 재수집 후 아래→위로 채움(서술형이 아래 → 먼저, 그 다음 객관식).
        qpts = _en_anchors(h)
        cpts = {m: _find_all(h, m, n_mc) for m in CIRCLES}
        for i in range(n_es - 1, -1, -1):
            p = qpts[n_mc + i]
            later = [a for a in _en_anchors(h) if a > p]      # 다음 슬롯(삭제 경계)
            nxt = min(later) if later else _answer_block_pos(h)
            _fill_essay_at(ses, h, p, essays[i], i + 1, nxt)
        for i in range(n_mc - 1, -1, -1):
            q = mc[i]
            chs = {c.number: c for c in q.choices}
            for mi, m in enumerate(reversed(CIRCLES)):
                num = 5 - mi
                if num in chs and i < len(cpts[m]):
                    put_choice_at(cpts[m][i], chs[num])
            put_question_at(qpts[i], q)

        ses.save_hwpx(out_path)
        fig_paths = list(getattr(ses, "_fig_paths", []))
    return n_mc, n_es, fig_paths


# ── 2단계: XML 행정렬 레이아웃 ────────────────────────────
_PARA = re.compile(r"<hp:p\b.*?</hp:p>", re.S)


def _visible_text(p: str) -> str:
    """모든 태그 제거 후 텍스트(보기 속 <hp:tab/> 등 섞여도 정확)."""
    return re.sub(r"<[^>]+>", "", p)


def _slot_opens(sec: str, en_phs: list[str]) -> list[int]:
    """미주 플레이스홀더 위치 → 그 앞 바깥 ``<hp:p`` 시작 오프셋(슬롯 시작)."""
    out = []
    for ph in en_phs:
        pos = sec.find(ph)
        if pos >= 0:
            out.append(sec.rfind("<hp:p ", 0, pos))
    return sorted(set(out))


def _build_layout(src_hwpx, out_hwpx, slot_blanks: dict, colbreak_slots, n_mc: int = -1,
                  answer_pagebreak: bool = False, answer_blank_pages: int = 0) -> None:
    """src 의 채운 내용을 바탕으로: 폼 빈줄 제거 + 슬롯별 빈줄 삽입 + columnBreak.

    colbreak_slots: 새 단을 시작할 슬롯 인덱스 집합(객관식 3/단·서술형 1/단을 따로 지정).
    n_mc: 객관식 슬롯 수. 빈줄 제거는 **객관식 영역에만** 적용(서술형은 소문항 답안 여백을
    보존). n_mc<0 이면 전체에 적용(객관식 전용 문서).
    answer_pagebreak: True 면 정답(답지) 블록을 새 페이지로 보낸다(쪽나누기).
    answer_blank_pages: 정답 블록 앞에 끼울 빈 페이지 수(짝수 마무리용 — 정답이 홀수쪽에
    오도록 보정). 정답 페이지가 짝수면 1을 줘서 한 장 밀어 홀수로 만든다.
    위치기반 편집만 사용(재조립 금지). 답안블록(container)/endNote/표/수식을 마스킹.
    """
    shutil.copy(src_hwpx, out_hwpx)
    with zipfile.ZipFile(out_hwpx) as z:
        infos = z.infolist()
        data = {i.filename: z.read(i.filename) for i in infos}
    name = next(n for n in data if n.endswith("section0.xml"))
    sec = data[name].decode("utf-8")

    # 마스킹: 답안(정답) 블록/endNote/table/equation → 플레이스홀더(중첩 단락 안전).
    store: list[str] = []

    def _mask(pat):
        nonlocal sec

        def _r(m):
            store.append(m.group(0))
            return f"@@X{len(store) - 1}@@"

        sec = re.sub(pat, _r, sec, flags=re.S)

    # 정답(답지) 블록 = '정답' 텍스트를 품은 그리기객체 컨테이너 — 통째 마스킹(가장 먼저).
    _mask(r"<hp:container\b.*?</hp:container>")
    answer_ph = next((f"@@X{i}@@" for i, s in enumerate(store) if "정답" in s), None)

    # 폼 잔존 단/쪽 나누기 리셋(마스킹된 정답 블록 내부는 보존, 내가 의도한 것만 재설정).
    sec = sec.replace('columnBreak="1"', 'columnBreak="0"').replace('pageBreak="1"', 'pageBreak="0"')

    _mask(r"<hp:endNote\b.*?</hp:endNote>")
    en_phs = [f"@@X{i}@@" for i, s in enumerate(store) if s.startswith("<hp:endNote")]
    _mask(r"<hp:tbl\b.*?</hp:tbl>")
    _mask(r"<hp:equation\b.*?</hp:equation>")

    def is_empty(p):
        # 그림(pic/gso) 든 단락은 '빈 줄' 아님 — 인라인 그림(보이는 텍스트 없음)이 빈줄삭제로
        # 지워지는 것 방지(그림은 _finalize_com 이 native 로 교체할 마커이기도 함).
        if "<hp:pic" in p or "<hp:gso" in p:
            return False
        return (not _visible_text(p).strip()) and ("@@X" not in p)

    N = len(_slot_opens(sec, en_phs))

    # 빈줄 템플릿: secPr 없고 <hp:p 1개뿐인 최단 빈 단락(섹션정의 단락·fabricate 금지).
    cands = [
        m.group(0)
        for m in _PARA.finditer(sec)
        if is_empty(m.group(0))
        and "<hp:secPr" not in m.group(0)
        and len(re.findall(r"<hp:p[ >]", m.group(0))) == 1
    ]
    blank = min(cands, key=len) if cands else ""

    # (1) 폼 과잉 빈줄 삭제 — **객관식 영역에만**(서술형 소문항 답안 여백 보존).
    ops0 = _slot_opens(sec, en_phs)
    first = ops0[0]
    # 서술형 시작(첫 서술형 슬롯) 이후는 건드리지 않음.
    es_start = ops0[n_mc] if (0 <= n_mc < len(ops0)) else len(sec)
    empties = [
        (m.start(), m.end())
        for m in _PARA.finditer(sec)
        if first <= m.start() < es_start and is_empty(m.group(0))
    ]
    for s, e in sorted(empties, reverse=True):
        sec = sec[:s] + sec[e:]

    # (2) 슬롯 끝(마지막 단락 뒤)에 계산된 빈줄 삽입. 뒤→앞.
    for si in range(N - 1, -1, -1):
        ops = _slot_opens(sec, en_phs)
        st = ops[si]
        en = ops[si + 1] if si + 1 < len(ops) else len(sec)
        last_end = st
        for m in _PARA.finditer(sec[st:en]):
            last_end = m.end() + st
        sec = sec[:last_end] + blank * slot_blanks.get(si, _MINGAP) + sec[last_end:]

    # (3) columnBreak: 지정된 단 첫 슬롯의 바깥 단락에. 뒤→앞.
    boundaries = sorted(b for b in colbreak_slots if 0 < b < N)
    for b in sorted(boundaries, reverse=True):
        ops = _slot_opens(sec, en_phs)
        s0 = ops[b]
        e0 = sec.find(">", s0)
        sec = sec[:s0] + re.sub(r'columnBreak="\d"', 'columnBreak="1"', sec[s0:e0 + 1]) + sec[e0 + 1:]

    # (4) 정답(답지) 블록: 새 페이지로(문제는 짝수쪽 마무리, 정답은 홀수쪽). 마지막에.
    def _force_pagebreak(open_tag: str) -> str:
        if "pageBreak=" in open_tag:
            return re.sub(r'pageBreak="\d"', 'pageBreak="1"', open_tag)
        return open_tag[:-1] + ' pageBreak="1">'

    if answer_ph and answer_pagebreak:
        pos = sec.find(answer_ph)
        if pos >= 0:
            ap = sec.rfind("<hp:p ", 0, pos)
            e0 = sec.find(">", ap)
            new_open = _force_pagebreak(sec[ap:e0 + 1])
            # 짝수 보정: pageBreak 걸린 빈 단락을 앞에 끼워 정답을 다음(홀수) 쪽으로 민다.
            blank_pages = ""
            if blank and answer_blank_pages > 0:
                bo = blank.find(">")
                blank_pb = _force_pagebreak(blank[:bo + 1]) + blank[bo + 1:]
                blank_pages = blank_pb * answer_blank_pages
            sec = sec[:ap] + blank_pages + new_open + sec[e0 + 1:]

    # 언마스킹(높은 인덱스부터 — 표/수식이 미주 플레이스홀더를 품을 수 있음).
    for i in range(len(store) - 1, -1, -1):
        sec = sec.replace(f"@@X{i}@@", store[i])

    # 태그 균형 점검(불일치 = 깨진 XML → 백지). 안전을 위해 검사만.
    if sec.count("<hp:p ") + sec.count("<hp:p>") != sec.count("</hp:p>"):
        raise RuntimeError("hp:p 태그 불균형 — XML 편집 오류")

    data[name] = sec.encode("utf-8")
    fd, tmp = tempfile.mkstemp(suffix=".hwpx", dir=str(Path(out_hwpx).parent))
    os.close(fd)
    with zipfile.ZipFile(tmp, "w") as zo:
        for io in infos:
            zi = zipfile.ZipInfo(io.filename, date_time=io.date_time)
            zi.compress_type = io.compress_type
            zi.external_attr = io.external_attr
            zi.internal_attr = io.internal_attr
            zi.create_system = io.create_system
            zi.flag_bits = io.flag_bits
            zo.writestr(zi, data[io.filename])
    os.replace(tmp, out_hwpx)


def _measure_first_choice_lines(hwpx, n: int) -> list[tuple[int, int, int]]:
    """COM 으로 열어 각 슬롯의 ① 위치(page, col, line)를 측정(읽기전용)."""
    import pythoncom

    pythoncom.CoInitialize()
    try:
        hwp = _dispatch_hwp()
        hwp.SetMessageBoxMode(0xFFFFFF)
        try:
            hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
        except Exception:
            pass
        try:
            hwp.XHwpWindows.Item(0).Visible = True  # 레이아웃 계산 위해
        except Exception:
            pass
        hwp.Open(str(hwpx), "HWPX", "")
        hwp.Run("MoveDocBegin")
        pos = []
        for _ in range(n):
            if not _repeat_find(hwp, "①"):
                break
            hwp.Run("Cancel")
            ki = hwp.KeyIndicator()
            pos.append((ki[3], ki[4], ki[5]))
        hwp.Quit()
        return pos
    finally:
        pythoncom.CoUninitialize()


def _measure_answer_page(hwpx) -> int:
    """COM 으로 열어 정답(답지) 블록이 놓인 쪽 번호를 측정(0=못 찾음).

    텍스트 "정답" 검색은 **꼬리말의 "(정답)"** 을 먼저 잡아 오측정되므로, 정답 블록
    그리기객체(gso) 앵커 위치(`_answer_block_pos`)로 쪽을 측정한다.
    """
    import pythoncom

    pythoncom.CoInitialize()
    try:
        hwp = _dispatch_hwp()
        hwp.SetMessageBoxMode(0xFFFFFF)
        try:
            hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
        except Exception:
            pass
        try:
            hwp.XHwpWindows.Item(0).Visible = True
        except Exception:
            pass
        hwp.Open(str(hwpx), "HWPX", "")
        page = 0
        pos = _answer_block_pos(hwp)
        if pos is not None:
            hwp.SetPos(pos[0], pos[1], pos[2])
            page = hwp.KeyIndicator()[3]
        hwp.Quit()
        return page
    finally:
        pythoncom.CoUninitialize()


def _extract_heights(pos: list[tuple[int, int, int]], n: int, per_col: int) -> dict:
    """측정한 ① 위치(page,col,line)로 각 객관식 슬롯의 줄 높이를 추정.

    높이 = 같은 (page,col) 안에서 다음 ① 까지의 줄차이. 단 마지막 슬롯은 같은 단 평균.
    """
    rowh = CAP // per_col
    colmap = defaultdict(list)
    for i, (pg, col, ln) in enumerate(pos):
        colmap[(pg, col)].append((i, ln))
    heights = {}
    for _, lst in colmap.items():
        lst.sort(key=lambda x: x[1])
        for j, (i, ln) in enumerate(lst):
            if j + 1 < len(lst):
                heights[i] = max(1, lst[j + 1][1] - ln)
            else:
                diffs = [lst[k + 1][1] - lst[k][1] for k in range(len(lst) - 1)]
                heights[i] = int(sum(diffs) / len(diffs)) if diffs else rowh
    return heights


# 문항 사이 기본 여유 간격(줄). 단 용량이 허락하면 이만큼 띄운다.
_GAP = 2


def _adaptive_columns(heights: dict, n: int, per_col_max: int):
    """측정 높이로 **스마트 단배치**: 한 단(CAP 줄) 안에서 문항 수를 가변(최대 per_col_max).

    - 긴 문항이 섞이면 단당 2개로 줄여 단을 넘기지 않게, 짧으면 3개까지 채운다(그리디).
    - 각 단의 남는 여유(CAP-내용)는 문항 사이 빈줄로 균등 분배(여유로운 배치). 단 마지막
      슬롯은 0(단나누기로 다음 단). 긴 단일수록 빈줄이 자동으로 줄어든다(사용자 요구
      2026-06-05: 문제가 길면 여백을 더 줄이거나 단당 2개로).

    Returns: (colbreak:set[새 단 시작 인덱스], blanks:dict[i→후행 빈줄], cols:list[list[i]]).
    """
    fb = CAP // per_col_max
    cols: list[list[int]] = []
    cur: list[int] = []
    cur_h = 0
    for i in range(n):
        h = heights.get(i, fb)
        prospective = cur_h + (_GAP if cur else 0) + h
        if cur and (prospective > CAP or len(cur) >= per_col_max):
            cols.append(cur)
            cur, cur_h = [], 0
        cur.append(i)
        cur_h += (_GAP if len(cur) > 1 else 0) + h
    if cur:
        cols.append(cur)

    colbreak = {c[0] for c in cols[1:]}     # 첫 단 제외, 각 단 첫 문항 앞에서 단나누기
    blanks: dict = {}
    for c in cols:
        content = sum(heights.get(i, fb) for i in c)
        nonlast = c[:-1]
        budget = max(0, CAP - content)      # 빈줄로 쓸 수 있는 여유 줄 수
        if nonlast:
            # 행정렬 목표: 각 문항이 이 단의 행높이(rowh=CAP//단문항수)를 차지하도록
            # rowh-height 만큼 띄운다(같은 순번이 비슷한 줄에서 시작). **단, 빈줄 총합이
            # 단 여유(budget)를 넘으면 비례 축소**(긴 단일수록 자동으로 빽빽 — 사용자 요구).
            rowh = CAP // len(c)
            ideal = {i: max(_MINGAP, rowh - heights.get(i, fb)) for i in nonlast}
            tot = sum(ideal.values())
            if tot > budget and tot > 0:
                lo = _MINGAP if budget >= _MINGAP * len(nonlast) else 0
                scale = budget / tot
                ideal = {i: max(lo, int(v * scale)) for i, v in ideal.items()}
            for i in c:
                blanks[i] = 0 if i == c[-1] else ideal[i]
        else:
            blanks[c[0]] = 0
    if os.environ.get("FORM_LAYOUT_DEBUG"):
        for ci, c in enumerate(cols):
            tot = sum(heights.get(i, fb) + blanks.get(i, 0) for i in c)
            print(f"[ADAPT] 단{ci}(문항{len(c)}): " + " ".join(
                f"Q{i}(h={heights.get(i)},b={blanks.get(i)})" for i in c)
                + f" 합계={tot}/{CAP}" + ("  ⚠초과" if tot > CAP else ""), flush=True)
    return colbreak, blanks, cols


def _layout_form(filled_hwpx, out_hwpx, per_col: int, n_mc: int, n_es: int) -> None:
    """채운 hwpx → 혼합 레이아웃. 객관식: 측정 기반 행정렬(per_col/단). 서술형: 1/단.

    객관식과 서술형은 폼의 별도 구역(섹션)이라 서술형은 새 페이지에서 시작한다.
    columnBreak: 객관식은 per_col 마다, 서술형은 매 문항(첫 서술형 제외).
    """
    n = n_mc + n_es
    essay_colbreak = set(range(n_mc, n))              # 서술형 1/단(매 문항이 새 단)
    # 측정용 tight 빌드는 고정 per_col 단나누기로(① 위치만 재면 됨).
    measure_colbreak = set(range(per_col, n_mc, per_col)) | essay_colbreak

    tight = str(Path(out_hwpx).with_suffix("")) + "_tight.hwpx"
    _build_layout(filled_hwpx, tight, {i: _MINGAP for i in range(n)}, measure_colbreak, n_mc)
    pos = _measure_first_choice_lines(tight, n_mc) if n_mc else []
    try:
        os.remove(tight)
    except Exception:
        pass

    blanks = {}
    colbreak = measure_colbreak
    if n_mc:
        if len(pos) >= n_mc:
            # 측정 성공 → **스마트 단배치**(높이 기반 단당 문항수 가변 + 여백 적응).
            heights = _extract_heights(pos, n_mc, per_col)
            obj_colbreak, mc_blanks, cols = _adaptive_columns(heights, n_mc, per_col)
            colbreak = obj_colbreak | essay_colbreak
            blanks.update(mc_blanks)
            logger.info(
                "폼 스마트 단배치(측정 %d/%d): %d개 단, 단당문항=%s, 높이=%s",
                len(pos), n_mc, len(cols), [len(c) for c in cols],
                {i: heights.get(i) for i in range(n_mc)})
        else:
            # ① 위치 측정 실패(COM Open/Find 방해 — 보안팝업·gen_py 등) → 균일 빈줄(4)
            # 더미 폴백. 행정렬이 안 돼 **과여백·다음단 넘침**이 발생한다.
            logger.warning(
                "[FALLBACK] 폼 스마트 단배치 측정 실패(측정 %d/%d 슬롯) → 고정 per_col + "
                "균일 빈줄(4) 폴백. 레이아웃 과여백/단넘침 가능 — COM 측정(보안팝업·gen_py) "
                "확인 필요.", len(pos), n_mc)
            colbreak = set(range(per_col, n_mc, per_col)) | essay_colbreak
            blanks.update({i: 4 for i in range(n_mc)})  # 측정 실패 폴백
    for i in range(n_mc, n):
        blanks[i] = 0                                 # 서술형: 1/단, 후행 0(답안 공간)

    # 정답(답지) 블록을 새 페이지로 보낸 뒤, 짝수쪽에 떨어지면 빈 페이지 1장으로 밀어
    # 홀수쪽에 오도록(문제는 짝수쪽 마무리). 정답 페이지를 측정해 패리티 보정.
    _build_layout(filled_hwpx, out_hwpx, blanks, colbreak, n_mc, answer_pagebreak=True)
    ans_page = _measure_answer_page(out_hwpx)
    if ans_page and ans_page % 2 == 0:
        _build_layout(filled_hwpx, out_hwpx, blanks, colbreak, n_mc,
                      answer_pagebreak=True, answer_blank_pages=1)


# ── 진입점 ────────────────────────────────────────────────
def _fill_form_header(hwpx_path: str | Path, values: dict) -> int:
    """출력 .hwpx 의 폼 머리말/꼬리말 텍스트를 학년·과목·시기 값으로 치환(결정적 XML).

    폼마다 박힌 텍스트가 제각각이라(예: 중2폼인데 머리말이 "고 1학년 수학") 고정 텍스트가
    아니라 **구조 패턴**(학년+과목 / 시험명 / "… 대비 (과목)" 꼬리말)을 정규식으로 잡아 값으로
    바꾼다. 모든 머리말 요소(홀/짝수쪽)·밴드를 한 번에. 값이 비면(학년/과목 없음) 건너뜀.
    꼬리말의 "(정답)" 은 보존. (toten 삽입 대신 출력 후처리 — 폼 원본 미변경.)

    학교+학년+과목이 들어가는 자리(머리말 가운데·꼬리말 대비문구)는 **항상
    "{학교} {N}학년 {과목}"** 형식(예 "침산중 2학년 수학", "영진고 2학년 수학1").
    시험명 자리는 "{년도}년 {학기}학기 {구분}고사".

    values 키: 학교("침산중"), 학년("중2"), 과목("수학"/"수학1"/"대수"…),
               년도("2025"), 학기("1"), 구분("중간"/"기말").
    Returns: 치환 건수(0 이면 손댄 것 없음).
    """
    school = (values.get("학교") or "").strip()
    g = (values.get("학년") or "").strip()
    gnum = g[-1] if g and g[-1].isdigit() else ""   # "중2" → "2"
    subj = (values.get("과목") or "").strip()
    # 과목 표시명 정규화: 파일명 약칭(확통 등) → 머리말 표기 정식명(사용자 2026-06-08).
    subj = _SUBJ_DISPLAY.get(subj.replace(" ", ""), subj)
    if not (g and subj):
        return 0
    yr = (values.get("년도") or "").strip()
    yr2 = yr[-2:] if yr else ""          # "2025" → "25" (꼬리말 학년도)
    term = (values.get("학기") or "").strip()
    kind = (values.get("구분") or "").strip()
    # 시험명(머리말 좌측): "2025년 1학기 중간고사"
    exam = (f"{yr}년 {term}학기 {kind}고사" if yr else f"{term}학기 {kind}고사").replace("  ", " ").strip()
    # 머리말 가운데: "{학교} {N}학년 {과목}"  (예 "침산중 2학년 수학", "영진고 2학년 수학1")
    who = (f"{school} {gnum}학년" if school and gnum else (f"{gnum}학년" if gnum else g))
    center = f"{who} {subj}".strip()
    # 꼬리말(우하단): "{학교} {YY}학년 {학기}학기 {구분}고사 대비 ({과목})"
    #   (예 "침산중 25학년 1학기 중간고사 대비 (수학)", "칠성고 25학년 1학기 기말고사 대비 (미적분)")
    prep = ((f"{school} " if school else "") + (f"{yr2}학년 " if yr2 else "")
            + f"{term}학기 {kind}고사").replace("  ", " ").strip()
    footer = f"{prep} 대비 ({subj})"
    pats = [
        # 꼬리말 먼저(시험명 패턴이 "고사"를 먼저 먹지 않게). "(정답)" 보존.
        # 과목은 수학뿐 아니라 미적분·기하·확률과 통계 등 **모든 선택과목**을 매칭(_SUBJ_PAT).
        (re.compile(r'(?:중|고)\s*\d{2,4}\s*년\s*학기\s*고사\s*대비\s*\(\s*' + _SUBJ_PAT + r'\s*\)(\s*\(\s*정답\s*\))?'),
         lambda mm: footer + (mm.group(1) or "")),
        (re.compile(r'(?:중|고)\s*[1-3]\s*학년\s*' + _SUBJ_PAT), lambda mm: center),
        (re.compile(r'\d{2,4}\s*년\s*학기\s*고사(?!\s*대비)'), lambda mm: exam),
    ]
    hwpx_path = Path(hwpx_path)
    with zipfile.ZipFile(hwpx_path) as z:
        infos = z.infolist()
        contents = {i.filename: z.read(i.filename) for i in infos}
    cnt = 0
    for fn in list(contents):
        if not (fn.endswith(".xml") and "section" in fn.lower()):
            continue
        text = contents[fn].decode("utf-8")
        n = 0
        for rx, repl in pats:
            text, k = rx.subn(repl, text)
            n += k
        if n:
            contents[fn] = text.encode("utf-8")
            cnt += n
    if not cnt:
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
    return cnt


def _embed_figures(hwpx_path: str | Path, fig_paths: list[str]) -> int:
    """그림 binItem 결정적 임베드(저장 후 XML 후처리).

    COM `InsertPicture` 가 만든 pic 요소는 ``binaryItemIDRef`` 가 폼 배너 binItem(image1)을
    가리켜 **배너가 표시**된다(HWP 의 HWPX SaveAs 가 새 binItem 을 안 만드는 버그). 여기서
    각 그림 PNG 바이트를 ``BinData/imageN.png`` 로 임베드하고, 본문 토큰 ``⟦F{idx}⟧`` **다음
    pic** 의 binItem 참조를 그 새 binItem 으로 교정한 뒤 토큰 텍스트를 제거한다. binItem
    등록은 ``Contents/content.hpf`` 의 ``<opf:item … isEmbeded="1">`` 로 한다(이 폼은
    header.xml 에 binDataList 가 없고 content.hpf manifest 가 등록처).

    Returns: 임베드한 그림 수.
    """
    if not fig_paths:
        return 0
    hwpx_path = Path(hwpx_path)
    with zipfile.ZipFile(hwpx_path) as z:
        infos = z.infolist()
        data = {i.filename: z.read(i.filename) for i in infos}
    hpf_name = next((n for n in data if n.endswith("content.hpf")), None)
    if hpf_name is None:
        return 0
    hpf = data[hpf_name].decode("utf-8")
    used = [int(m.group(1)) for m in re.finditer(r'id="image(\d+)"', hpf)]
    next_idx = (max(used) + 1) if used else 1

    section_names = [n for n in data if re.search(r"section\d+\.xml$", n)]
    new_items: list[str] = []
    new_bins: dict[str, bytes] = {}
    embedded = 0

    for idx, png in enumerate(fig_paths):
        token = _fig_token(idx)
        target = next((sn for sn in section_names if token in data[sn].decode("utf-8")), None)
        if target is None:
            continue
        try:
            with open(png, "rb") as f:
                img_bytes = f.read()
        except Exception:
            # 그림 파일 분실 → 토큰만 제거(깨진 토큰 텍스트 잔존 방지)
            sec = data[target].decode("utf-8").replace(token, "")
            data[target] = sec.encode("utf-8")
            continue
        img_id = f"image{next_idx}"
        next_idx += 1
        bin_name = f"BinData/{img_id}.png"
        new_bins[bin_name] = img_bytes
        new_items.append(
            f'<opf:item id="{img_id}" href="{bin_name}" media-type="image/png" isEmbeded="1"/>'
        )
        sec = data[target].decode("utf-8")
        tpos = sec.find(token)
        ppos = sec.find("<hp:pic", tpos)
        if ppos >= 0:
            pe = sec.find("</hp:pic>", ppos)
            pe = pe + len("</hp:pic>") if pe >= 0 else len(sec)
            pic = sec[ppos:pe]
            # 그 pic 의 첫 binaryItemIDRef 만 새 binItem 으로 교체(배너 등 다른 pic 불변).
            pic2 = re.sub(r'binaryItemIDRef="[^"]*"', f'binaryItemIDRef="{img_id}"', pic, count=1)
            sec = sec[:ppos] + pic2 + sec[pe:]
            embedded += 1
        sec = sec.replace(token, "")          # 토큰 텍스트 제거
        data[target] = sec.encode("utf-8")

    if not new_bins:
        # 토큰 제거만 반영(임베드 0)
        _repackage_hwpx(hwpx_path, infos, data)
        return 0
    data[hpf_name] = hpf.replace("</opf:manifest>", "".join(new_items) + "</opf:manifest>", 1).encode("utf-8")
    data.update(new_bins)
    _repackage_hwpx(hwpx_path, infos, data)
    return embedded


def _repackage_hwpx(hwpx_path: Path, infos, data: dict) -> None:
    """기존 엔트리는 원래 ZipInfo(압축·mimetype STORED 등) 보존, 새 엔트리는 추가 후 교체."""
    fd, tmp = tempfile.mkstemp(suffix=".hwpx", dir=str(hwpx_path.parent))
    os.close(fd)
    seen = set()
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zo:
        for info in infos:
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type = info.compress_type
            zi.external_attr = info.external_attr
            zi.internal_attr = info.internal_attr
            zi.create_system = info.create_system
            zi.flag_bits = info.flag_bits
            zo.writestr(zi, data[info.filename])
            seen.add(info.filename)
        for name, b in data.items():
            if name not in seen:
                zo.writestr(name, b)
    os.replace(tmp, hwpx_path)


# 폼 grow 서술형 슬롯의 잔존 라벨([서답형 N]) 뒤에 우리 라벨([서술형 N])이 붙어 중복됨.
# 뒤에 또 다른 '[' 라벨이 따라오는 [서…형 N] 만 제거 → 우리 라벨만 남긴다. (같은 <hp:t>
# 안에서만 매칭되므로 태그 균형 안전. 문제 길이·개수와 무관한 결정적 후처리.)
_DUP_LABEL_RE = re.compile(r'\[\s*서[답술]형\s*\d+\s*\]\s*(?=\[\s*서[답술]형)')


def _dedupe_essay_labels(hwpx_path: str | Path) -> int:
    """서술형 번호줄의 중복 라벨([서답형 N] [서술형 N] → [서술형 N]) 제거. 항상 실행(강제).

    폼 grow 슬롯의 COM 라벨 삭제가 비결정적으로 실패해 폼 라벨이 남는 것을, 저장 후 XML 에서
    **뒤에 또 라벨이 오는 앞 라벨만** 지워 결정적으로 보정한다. Returns: 제거 건수.
    """
    hwpx_path = Path(hwpx_path)
    with zipfile.ZipFile(hwpx_path) as z:
        infos = z.infolist()
        data = {i.filename: z.read(i.filename) for i in infos}
    total = 0
    for name in list(data):
        if not re.search(r"section\d+\.xml$", name):
            continue
        sec = data[name].decode("utf-8")
        sec2, n = _DUP_LABEL_RE.subn("", sec)
        if n:
            data[name] = sec2.encode("utf-8")
            total += n
    if total:
        _repackage_hwpx(hwpx_path, infos, data)
    return total


def _com_relaunder(hwpx_path: str | Path) -> bool:
    """후처리한 hwpx 를 HWP COM 으로 한 번 더 열어 다시 저장(launder)해 '변조' 보안경고 제거.

    XML 후처리(레이아웃·라벨·머리말)는 HWP 저장 **후** 파일을 외부에서 고치므로, HWP 가 여는
    시점에 "문서가 손상/변조됐을 수 있음 — 보안 설정을 낮춰야 열림" 경고를 띄운다(사용자 보고
    2026-06-05). HWP 가 그 파일을 직접 다시 저장하면 HWP authoring 으로 인식돼 경고가
    사라진다(폼 원본·재저장본 모두 경고 없음 사용자 확인). 레이아웃/박스/안내문구 보존(검증).
    실패해도 출력은 유효(경고만)하므로 변환을 중단하지 않는다. Returns: 성공 여부.
    """
    hwpx_path = Path(hwpx_path)
    fd, tmp = tempfile.mkstemp(suffix=".hwpx", dir=str(hwpx_path.parent))
    os.close(fd)
    try:
        with HwpSession(visible=CONVERSION_VISIBLE) as ses:   # 재저장(launder)도 표시
            ses.open(hwpx_path)
            ses.save_hwpx(tmp)
        os.replace(tmp, hwpx_path)
        return True
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass
        return False


def write_exam_to_form(
    document: ExamDocument,
    form_path: str | Path,
    output_path: str | Path,
    per_col: int = PER_COL,
    header_values: dict | None = None,
    render_figures: bool = False,
) -> Path:
    """ExamDocument 를 대수회 폼(.hwp)에 채워 .hwpx 로 저장.

    Args:
        document: 변환할 시험 문서.
        form_path: 폼 양식(.hwp) 경로.
        output_path: 출력 .hwpx 경로.
        per_col: 한 단당 문항 수(기본 3 → 페이지당 6).
        header_values: 머리말/꼬리말 채울 값(학년·과목·년도·학기·구분). None 이면 폼 원문 유지.

    Returns:
        저장된 파일 경로.
    """
    if _win32 is None:
        raise RuntimeError("win32com을 사용할 수 없습니다 (HWP COM 미지원 환경).")
    output_path = Path(output_path)
    qs = [q for page in document.pages for q in page.questions]
    mc = [q for q in qs if q.choices]            # 객관식
    essays = [q for q in qs if not q.choices]    # 서술형(보기 없음)
    if not mc and not essays:
        raise ValueError("채울 문항이 없습니다.")

    # 1단계: COM 채움 → 임시 hwpx.
    fd, filled = tempfile.mkstemp(suffix=".hwpx", dir=str(output_path.parent))
    os.close(fd)
    try:
        n_mc, n_es, fig_paths = _fill_form(mc, essays, form_path, filled,
                                           render_figures=render_figures)
        # 혼합 레이아웃(객관식 행정렬 + 서술형 1/단).
        _layout_form(filled, output_path, per_col, n_mc, n_es)
    finally:
        try:
            os.remove(filled)
        except Exception:
            pass
    # 1.5단계: 서술형 중복 라벨([서답형 N] [서술형 N]) 결정적 제거(폼 grow 잔존 라벨 보정).
    try:
        _dedupe_essay_labels(output_path)
    except Exception as e:  # noqa: BLE001
        logger.warning("폼 후처리 실패(_dedupe_essay_labels): %s", e)
    # 1.6단계: 서술형 중복 라벨 제거는 위에서 완료. 머리말/꼬리말 채움(결정적 XML 후처리).
    if header_values:
        try:
            _fill_form_header(output_path, header_values)
        except Exception as e:  # noqa: BLE001
            logger.warning("폼 후처리 실패(_fill_form_header): %s", e)
    # 1.7단계: <보기>/<조건> 라벨 1×1 박스 → 5×5 병합표 폼(기본 경로와 동일, 사용자
    # '항상 동일' 요구). <상자>·일반표는 제외. _com_relaunder **전**에 주입해 재저장 때
    # HWP 가 표 linesegs 를 재계산하고 보안경고도 없게 한다.
    try:
        from core.hwp_com_writer import _inject_bogi_form
        _inject_bogi_form(output_path)
    except Exception as e:  # noqa: BLE001
        logger.warning("폼 후처리 실패(_inject_bogi_form): %s", e)
    # 1.8단계: 확률분포표 1열·표준정규분포표 최상단 행 #D9D9D9 음영(수기본 통일, 기본 경로와 동일).
    try:
        from core.hwp_com_writer import _inject_table_shading
        _inject_table_shading(output_path)
    except Exception as e:  # noqa: BLE001
        logger.warning("폼 후처리 실패(_inject_table_shading): %s", e)
    # 2단계: 그림 렌더 모드면 그림 binItem 임베드(경고 감수). 아니면(기본) COM 재저장(launder)
    # 으로 '변조' 보안경고 제거 — 그림 자리엔 안내 박스(표라서 재저장에 보존).
    if render_figures and fig_paths:
        try:
            _embed_figures(output_path, fig_paths)
        except Exception as e:  # noqa: BLE001
            logger.warning("폼 후처리 실패(_embed_figures): %s", e)
    else:
        if not _com_relaunder(output_path):
            logger.warning("폼 후처리 실패(_com_relaunder): 보안경고 제거 재저장 실패")
    return output_path
