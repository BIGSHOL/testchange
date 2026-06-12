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
                             _caption_spans, _choice_complexity, _COND_HEADER_RE,
                             _condition_start, _has_box_markup, _post_has_stem,
                             _post_is_box, _split_tail_post, _split_trailing_score,
                             _tail_start)
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
    # 글자색 검정 명시 — 폼 슬롯/박스 렌더 후 캐럿이 **흰색**(#FFFFFF) 상태로 남으면
    # 이후 입력 본문이 흰 배경에 흰 글자로 찍혀 보이지 않는다(대륜중 중1 #21 서술형:
    # <보기> 박스 뒤 소문항 전체가 흰색으로 투명. 실측 2026-06-11). _set_plain 은 본문
    # 입력 직전 항상 호출되므로 여기서 검정으로 고정한다(메타 토큰은 저장후 XML 로 교체).
    try:
        cs.TextColor = 0          # RGB 0x000000 = 검정
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
    # 본문 수식 — italicize_stat=False 로 기하 \mathrm{P}(점 P) 보존(2026-06-09).
    return block.hwp_equation or latex_to_hwpeq(block.value, italicize_stat=False)


def _put_block(ses, b) -> None:
    """ContentBlock 하나를 현재 캐럿에 삽입(수식/텍스트/그림).

    **발문 아래 독립 블록수식(EQUATION_BLOCK)은 가운데 별도줄**(기본 경로 `_write_block`
    과 동일 — 사용자 '항상 동일' 요구). 인라인 EQUATION 은 줄 흐름 그대로. 블록수식 뒤
    발문 연속의 좌측복귀는 호출부(`_put_qbody`)가 prev_type 추적으로 처리한다.
    """
    if b.type == ContentType.EQUATION_BLOCK:
        ses.break_para()
        ses.align_center()
        ses.equation(_eq_script(b))         # 좌측복귀는 _put_qbody 가 다음 블록 전에
    elif b.type == ContentType.EQUATION:
        ses.equation(_eq_script(b))  # 숫자도 수식 객체로 유지(정렬)
    elif b.type == ContentType.TEXT:
        if b.value:
            from core.hwp_com_writer import _is_figure_note
            if _is_figure_note(b):
                # 그림자리 안내(render_figures=False 시 figure→TEXT 치환)는 IMAGE 와 동일하게
                # **가운데·별도줄**(발문 인라인 금지). 기본 경로 `_write_block`(hwp_com_writer)
                # 과 동일. 폼 head 블록(text→figure→text 문장 중간 그림)이 _put_block 으로
                # 직접 쓰여 안내문구가 앞뒤 발문과 인라인 병합되던 것 보정(황금중 #16, 2026-06-11).
                ses.break_para()
                ses.align_center()
                ses.text(b.value)
                ses.break_para()
                ses.align_left()
            elif getattr(b, "underline", False):
                # __강조__ 밑줄 TEXT — 기본 경로(hwp_com_writer `_write` 의 underline_run)와
                # 동일. 폼 경로만 평문 강등돼 "옳지 않은"·"더하거나 빼어서" 밑줄이 소실됐다
                # (월암중 #9·#19, 2026-06-11 — 매천중·상원중에도 있었으나 대조에서 놓침).
                ses.underline_run(b.value)
            else:
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

# 서술형 [소단원][난이도] 메타란 자리 토큰(소단원·난이도 각각 1개씩, 자기 단락). 채움 단계엔
# 이 토큰 단락만 찍고, 저장 후 `_inject_essay_meta` 가 살아있는 폼 메타란 **run**(MC 슬롯,
# 디자인·charPr ID 유효)을 그 토큰의 run 과 **1:1 교체**한다(단락 경계·중첩 무관, 태그 균형
# 보장 — 박스로 끝난 서술형은 토큰이 중첩 단락에 들어가 단락단위 치환이 깨졌던 함정 회피).
# (폼 서술형 슬롯의 원본 메타란은 라벨 플레이스홀더 삭제 때 함께 지워지므로 재주입한다.)
_META_TOKEN_SO = "소단원자리표식QZX"
_META_TOKEN_NA = "난이도자리표식QZX"


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
    # 표 캡션이 pre 끝에 걸쳐 있으면(다음 블록=표) 줄바꿈+우측정렬로 분리(기본 경로와
    # 동일 — 사용자 '항상 동일' 요구, 2026-06-10).
    cap_j = None
    if box and box[0].type == ContentType.TABLE and pre:
        cap_j = next((j for j, t in _caption_spans(core).items() if t == cs), None)
    for b in (pre if cap_j is None else pre[:cap_j]):
        if b.type == ContentType.IMAGE and b.value:
            ses.break_para()
            ses.align_center()
            _place_figure(ses, h, b.value)         # 모드 분기(렌더/안내 박스)
            # 트레일링 break 없음 — 조건 박스가 단락시작(pos==0) 재사용으로 빈 줄 방지
        else:
            w._write_block(b)                      # EQUATION_BLOCK 가운데·EQUATION 인라인·TEXT
    if cap_j is not None:
        w._write_caption_run(pre[cap_j:])
    if box:
        w._write_condition_box(box)
    if post and _post_is_box(post):
        # post 가 또 다른 박스(<조건> 등, #16): 평문이 아니라 **두 번째 박스**로 렌더
        # (기본 경로와 동일). 핵심 박스 뒤 단락시작이라 빈 줄 없이 이어 붙는다.
        w._write_condition_box(post)
    else:
        for bi, b in enumerate(post):              # 박스 뒤 발문 연속 — 박스 밖, 새 줄에 이어서
            if box:
                ses.break_para()
                ses.align_left()
                box = []
            if bi == 0:
                # post 발문은 일반 본문이다. 폼 슬롯에선 박스(표) 탈출 후 캐럿이 폼 템플릿의
                # 볼드 단락에 착지해 발문 연속이 볼드로 상속됐다(#20, 사용자 2026-06-09). 평문 강제.
                _set_plain(ses.hwp)
            if b.type == ContentType.IMAGE and b.value:
                ses.break_para()
                ses.align_center()
                _place_figure(ses, h, b.value)
            else:
                w._write_block(b)


def _put_qbody(ses, h, contents, score, essay: bool = False, allow_break: bool = False) -> None:
    """문제(또는 소문항) 본문: 발문 → 배점(발문 끝) → 뒤 영역(조건/그림/블록수식).

    essay=True 면 배점을 **줄바꿈 후 우측정렬**(서술형 합의). 객관식은 발문 끝 인라인.
    allow_break=True 면 **tail 없는 서술형 소문항 배점을 항상 줄바꿈 우측정렬**(합의 #2,
    황금중 #22(2) — wrap 미감지 좌측잔존 해결). tail 이 있으면(박스/그림/표) caret 이
    fragile 해 강제 안 함(force_right 가 박스 깬 교훈). 호출처는 소문항 루프뿐.
    """
    ts = _tail_start(contents)
    head = contents if ts is None else contents[:ts]
    tail = [] if ts is None else contents[ts:]
    # 발문 중간 독립 블록수식(EQUATION_BLOCK)은 가운데 별도줄, 그 **뒤 발문 연속은 좌측 새
    # 줄**로 복귀해야 한다(중앙고 #19 "…다음과 같다. [블록수식] 이때 …"). _put_block 이
    # 블록수식을 break+center 하므로, 직후 비-블록수식 블록 전에 좌측복귀를 끼운다(기본 경로
    # _write_question stem 루프와 동일 — 사용자 '항상 동일').
    prev_t = None
    for b in head:
        if (prev_t == ContentType.EQUATION_BLOCK
                and b.type not in (ContentType.EQUATION_BLOCK, ContentType.IMAGE)):
            ses.break_para()
            ses.align_left()
        _put_block(ses, b)
        prev_t = b.type
    if prev_t == ContentType.EQUATION_BLOCK:   # 발문이 블록수식으로 끝남 → 배점 전 좌측복귀
        ses.break_para()
        ses.align_left()
    # 박스 뒤 발문 연속(#18·#20)이 있으면 배점은 그 뒤로 미룬다(기본 경로와 동일).
    # 객관식도 — 원본 인쇄는 의문문(post) 끝 "…것은? [4점]"(장산중 #5, 2026-06-11).
    # 단 post 가 또 다른 박스(<조건> 등, #16)거나 그림/그림노트뿐(경일중 #19)이면
    # 발문 연속이 아니므로 안 미룬다(배점=발문 끝).
    _, tail_post = _split_tail_post(tail)
    defer_score = (bool(score) and bool(tail_post)
                   and not _post_is_box(tail_post) and _post_has_stem(tail_post))
    # tail 없는 서술형 소문항만 줄바꿈 우측정렬 강제(안전 caret). tail 있으면 fragile.
    fb = allow_break and essay and not tail
    if score and not defer_score:
        _put_score(ses, h, score, essay=essay, force_break=fb)   # 객관식=인라인 / 서술형=우측정렬
    if tail:
        _put_tail(ses, h, tail)
        if defer_score:
            _put_score(ses, h, score, essay=essay)


def _put_score(ses, h, score: int, essay: bool = False, force_break: bool = False) -> bool:
    """배점 삽입 — **기본 경로(hwp_com_writer)와 동일**(사용자 '항상 동일' 요구).

    서술형·객관식 **공통**: 배점을 **발문 끝 인라인** ``[N점]`` 으로 먼저 시도하고,
    그게 줄을 넘치면(=현재 줄에 공간 부족) **줄바꿈 후 우측정렬**로 폴백한다(사용자
    2026-06-09: "공간이 충분하면 인라인, 없을 때만 줄바꿈 우측정렬 — 공간 충분한데도
    줄바꿈하면 공간낭비"). 줄 넘침 판정은 인라인 입력 전후 ``KeyIndicator()[5]``(줄)
    비교로 결정적으로 한다. 배점 숫자는 합의 #6(순수숫자도 수식 객체화)에 따라
    ``ses.equation`` 으로 넣는다.

    서술형은 우측정렬 폴백 시 뒤 내용을 위해 **좌측 정렬로 복귀**(break+align_left).

    force_break=True: 인라인 wrap 감지를 건너뛰고 **항상 줄바꿈 후 우측정렬**(합의 #2).
    폼 단(column) 컨텍스트에서 ``KeyIndicator()[5]`` 가 단락 내 자동 wrap 을 비일관 측정해
    (황금중 #22(2) — 인라인이 줄넘침해도 미감지 → 좌측 잔존) 폴백이 안 걸리는 문제 해결.
    **반드시 안전 caret(소문항 본문 끝 평문, tail 없음)에서만** 호출 — BreakPara 가 박스/단
    레이아웃을 침범하지 않는다(force_right 전역적용이 박스 깬 교훈, 2026-06-11).

    Returns: 우측정렬 단락으로 넘겼으면 True(현재 단락이 우측정렬 상태).
    """
    def put_inline(leading_space: bool):
        ses.text(" [" if leading_space else "[")
        ses.equation(str(score))
        ses.text("점]")

    def line():
        try:
            return h.KeyIndicator()[5]
        except Exception:
            return -1

    if force_break and essay:
        # 줄바꿈 후 우측정렬 강제 — _put_total_score 의 wrap 분기와 동일한 검증된 시퀀스.
        ses.break_para()
        h.Run("ParagraphShapeAlignRight")
        _set_plain(h)
        put_inline(leading_space=False)
        ses.break_para()
        ses.align_left()
        _set_plain(h)
        return True

    sp = h.GetPos()
    la = line()
    if essay:
        _set_plain(h)           # 서술형 배점은 평문(라벨 볼드 상속 방지)
    put_inline(leading_space=True)
    ep = h.GetPos()             # 삽입 끝(정확한 span 삭제용)
    lb = line()
    if la >= 0 and lb > la:
        # 인라인이 줄을 넘김 = 공간 부족 → 지우고 줄바꿈 후 우측정렬.
        # ⚠️ 삭제는 **삽입분(sp→ep)만 정확히 선택** — MoveSelParaEnd 는 캐럿 뒤 같은
        # 단락의 다른 내용까지 선택한다. 마지막 서술형에선 표 탈출(SetPos para+1)로
        # 본문이 폼 **정답 단락 안**에 타이핑되는데, 그때 MoveSelParaEnd+Delete 가
        # 정답 블록 앵커 문자(답안표 gso·container)까지 삼켜 정답 페이지가 통째
        # 사라졌다(강동중 #20 sub(2) [4점], 2026-06-10).
        h.SetPos(sp[0], sp[1], sp[2])
        h.SelectText(sp[1], sp[2], ep[1], ep[2])
        h.HAction.Run("Delete")
        h.Run("BreakPara")
        h.Run("ParagraphShapeAlignRight")
        _set_plain(h)
        put_inline(leading_space=False)
        if essay:               # 서술형: 뒤 내용을 위해 좌측 복귀
            ses.break_para()
            ses.align_left()
            _set_plain(h)
        return True
    return False


# 소문항 앞머리 번호 마커((1)/1)/1./①…) — 우리가 마커를 별도로 붙이므로 OCR 중복분 제거.
_SUBMARK_RE = re.compile(r'^\s*(?:[\(（]\s*\d+\s*[\)）]|\d+\s*[.)]|[①-⑩])\s*')
_EQ_TYPES = (ContentType.EQUATION, ContentType.EQUATION_BLOCK)
_LEAD_CLOSE_RE = re.compile(r'^\s*[\)）.]\s*')   # 분리된 마커의 닫힘부 ") "/". "


def _blk(t, v):
    return ContentBlock(type=t, value=v)


def _is_ref_not_submarker(seg: str, rest: str) -> bool:
    """``seg``(소문항 마커 후보)가 **공백 없이 닫는 괄호로 끝나고** ``rest``(그 뒤 텍스트)가
    한글로 시작하면 소문항 마커가 아니라 **본문 교차참조**(``(1)에서 구한 식…``)다 — strip
    하지 않는다(학산중 #19, 2026-06-12). 진짜 소문항 마커는 ``(2) 일차함수…`` 처럼 마커 뒤
    공백이 있어 ``seg`` 가 trailing 공백을 먹는다. 원숫자 ``①``·``1.`` 류는 닫는 괄호가
    없어 항상 마커로 취급."""
    return (seg == seg.rstrip()                       # 닫힘부가 trailing 공백을 안 먹음
            and seg.rstrip().endswith((")", "）"))
            and bool(rest) and "가" <= rest[0] <= "힣")


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
        m = _SUBMARK_RE.match(t0)
        if m and not _is_ref_not_submarker(m.group(0), t0[m.end():]):
            nv = t0[m.end():]
            return ([_blk(ContentType.TEXT, nv)] + c[1:]) if nv.strip() else c[1:]

    # 형태 2: "(" + EQ숫자 + ")rest"
    if (len(c) >= 3 and (t0 is not None and t0.strip() in ("(", "（"))
            and eqd(c[1]) is not None and txt(c[2]) is not None):
        m2 = _LEAD_CLOSE_RE.match(txt(c[2]))
        if m2 and not _is_ref_not_submarker(m2.group(0), txt(c[2])[m2.end():]):
            rest = txt(c[2])[m2.end():]
            return ([_blk(ContentType.TEXT, rest)] if rest.strip() else []) + c[3:]

    # 형태 3: EQ숫자 + ")rest" 또는 ".rest"
    if (len(c) >= 2 and eqd(c[0]) is not None and txt(c[1]) is not None):
        m3 = _LEAD_CLOSE_RE.match(txt(c[1]))
        if m3 and not _is_ref_not_submarker(m3.group(0), txt(c[1])[m3.end():]):
            rest = txt(c[1])[m3.end():]
            return ([_blk(ContentType.TEXT, rest)] if rest.strip() else []) + c[2:]

    # 형태 4: 마커 통째가 한 수식 객체 "(1)"
    # (파서가 ``(1)에서 구한…`` 의 ``(1)`` 을 괄호원자로 수식화해 EQ"(1)"+TEXT"에서…" 로
    #  쪼개기도 한다 — 다음 TEXT 가 공백 없이 한글이면 교차참조라 보존, 학산중 #19.)
    if (getattr(c[0], "type", None) in _EQ_TYPES
            and _SUBMARK_RE.fullmatch((c[0].value or "").strip())
            and not _is_ref_not_submarker((c[0].value or "").strip(),
                                          (txt(c[1]) if len(c) >= 2 else "") or "")):
        return c[1:]

    return contents


def _put_total_score(ses, h, num: int) -> None:
    """소문항 부모 총점 "[총 N점]" — **발문 끝 인라인 우선, 줄 넘치면 줄바꿈 후 우측정렬**
    (N 은 수식 객체). 점수 ④와 동일 로직(사용자 2026-06-09: 공간 충분하면 인라인). 기본 경로 동일.
    """
    def put_inline(leading_space: bool):
        ses.text(" [총 " if leading_space else "[총 ")
        ses.equation(str(num))
        ses.text("점]")

    def line():
        try:
            return h.KeyIndicator()[5]
        except Exception:
            return -1

    sp = h.GetPos()
    la = line()
    _set_plain(h)
    put_inline(leading_space=True)
    ep = h.GetPos()             # 삽입 끝(정확한 span 삭제용)
    lb = line()
    if la >= 0 and lb > la:
        # ⚠️ 삽입분(sp→ep)만 선택-삭제 — MoveSelParaEnd 는 정답 단락 침범 시 정답
        # 앵커까지 삼킨다(_put_score 와 동일 함정, 2026-06-10).
        h.SetPos(sp[0], sp[1], sp[2])
        h.SelectText(sp[1], sp[2], ep[1], ep[2])
        h.HAction.Run("Delete")
        h.Run("BreakPara")
        h.Run("ParagraphShapeAlignRight")
        _set_plain(h)
        put_inline(leading_space=False)
        ses.break_para()
        ses.align_left()
        _set_plain(h)


# 라벨 괄호는 ``[ ]`` 와 ``【 】``(렌티큘러) 둘 다 — OCR 이 같은 시험지에서 혼용한다(경운중
# #3·#5 가 ``【서답형 3】`` → 우리 ``[서답형 3]`` 와 겹쳐 중복, 2026-06-09). 캡처해 정규화.
_ESSAY_LABEL_LEAD = re.compile(r'^\s*[\[【]\s*(서[답술]형)\s*(\d+)\s*[\]】]\s*')


def _essay_label_and_body(contents, fallback_label, label_idx):
    """contents 선두의 ``[서술형/서답형 N]`` 라벨을 추출해 (라벨문자열, 라벨제거 contents) 반환.

    OCR 은 발문 앞에 ``[서술형 N]`` 라벨을 contents 에 넣는다(프롬프트 규칙). _fill_essay_at
    가 자기 라벨을 또 쓰면 ``[서답형 N] [서술형 N]`` 중복이 생기고, 이를 저장 후 regex 로
    지우던 ``_dedupe_essay_labels`` 가 **lineseg 를 갱신하지 않아** HWP 재저장 시 그 단락
    (미주 포함)을 통째 드롭했다(서술형 4·5 누락의 근본 원인, 2026-06-09). → contents 의
    라벨을 그대로 쓰고 본문에서 떼어 **라벨을 한 번만** 출력 → 중복·후처리 자체를 제거.
    라벨이 없으면 폴백 ``[{label_type} {label_idx}]``.
    """
    import copy
    out = list(contents)
    # 선두 박스 블록(box_member)은 건너뛴다 — 발문 앞에 전체 안내박스("※ [서답형 1~5] …")가
    # 끼면 진짜 라벨이 그 뒤에 온다(2026-06-09). 박스는 라벨이 아니므로 보존하고 스킵만.
    i = 0
    while i < len(out) and getattr(out[i], "box_member", False):
        i += 1
    # 비박스 첫 텍스트가 라벨이어야. 라벨은 (1) 한 블록 "[서답형 N] rest" 또는
    # (2) 분리형 TEXT"[서답형 " + EQ"N" + TEXT"] rest" (번호가 수식 객체일 때 — #2, 2026-06-09).
    if i < len(out) and out[i].type == ContentType.TEXT and (out[i].value or "").strip():
        b0 = out[i]
        m = _ESSAY_LABEL_LEAD.match(b0.value)
        if m:                                   # 형태 1: 한 블록(라벨을 [서답형 N]로 정규화)
            nb = copy.copy(b0)
            nb.value = b0.value[m.end():]
            out[i] = nb
            return f"[{m.group(1)} {m.group(2)}]", out
        # 형태 2: 분리형 "[서답형 " + EQ숫자 + "] rest"(여는 [ 또는 【)
        head = re.match(r'^\s*[\[【]\s*(서[답술]형)\s*$', b0.value)
        if (head and i + 2 < len(out)
                and out[i + 1].type in _EQ_TYPES
                and (out[i + 1].value or "").strip().isdigit()
                and out[i + 2].type == ContentType.TEXT
                and re.match(r'^\s*[\]】]', out[i + 2].value or "")):
            num = (out[i + 1].value or "").strip()
            rest = re.sub(r'^\s*[\]】]\s*', '', out[i + 2].value or "")
            nb2 = copy.copy(out[i + 2])
            nb2.value = rest
            tail = ([nb2] if rest.strip() else []) + out[i + 3:]
            return f"[{head.group(1)} {num}]", out[:i] + tail
        # 형태 3: **비괄호** "서술형 N. rest" — OCR 이 괄호 없이 줄 때(강동중 등). 파싱 후
        #   TEXT"서술형 " + EQ"N" + TEXT". rest" 로 쪼개진다. 폼 라벨([서답형 N])과 중복되어
        #   "[서답형 4] 서술형 4." 가 되던 문제(사용자 2026-06-10). 떼고 그 단어로 라벨 통일.
        head3 = re.match(r'^\s*(서답형|서술형|단답형)\s*$', b0.value)
        if (head3 and i + 2 < len(out)
                and out[i + 1].type in _EQ_TYPES
                and (out[i + 1].value or "").strip().isdigit()
                and out[i + 2].type == ContentType.TEXT
                and re.match(r'^\s*[.．]', out[i + 2].value or "")):
            num = (out[i + 1].value or "").strip()
            rest = re.sub(r'^\s*[.．]\s*', '', out[i + 2].value or "")
            nb3 = copy.copy(out[i + 2])
            nb3.value = rest
            tail = ([nb3] if rest.strip() else []) + out[i + 3:]
            return f"[{head3.group(1)} {num}]", out[:i] + tail
        # 형태 4: 비괄호 한 블록 "서술형 N. rest"(숫자가 수식 분리 안 된 경우).
        m4 = re.match(r'^\s*(서답형|서술형|단답형)\s*(\d+)\s*[.．]\s*', b0.value)
        if m4:
            nb = copy.copy(b0)
            nb.value = b0.value[m4.end():]
            out[i] = nb
            return f"[{m4.group(1)} {m4.group(2)}]", out
    return f"[{fallback_label} {label_idx}]", out


_ESSAY_LABEL_SPLIT_RE = re.compile(r'^(\[\s*서[답술]형\s*)(\d+)(\s*\])$')


def _put_essay_label(ses, label: str) -> None:
    """서술형 라벨을 ``[서답형 `` 텍스트 + 번호 **수식** + ``]`` 텍스트로 쓴다.

    번호는 합의 #6(모든 숫자=수식 객체)에 따라 수식으로(사용자 2026-06-09: "[서답형 5]의
    5는 수식"). 형식이 안 맞으면 통째 텍스트 폴백.
    """
    m = _ESSAY_LABEL_SPLIT_RE.match((label or "").strip())
    if m:
        ses.text(" " + m.group(1))
        ses.equation(m.group(2))
        ses.text(m.group(3) + " ")
    else:
        ses.text(f" {label} ")


def _fill_essay_at(ses, h, pos, q: Question, label_idx: int, next_pos=None) -> None:
    """서술형 슬롯 채움: 번호줄 ``[라벨 M] 문제`` + 소문항((k) 수식 마커) + 배점.

    label_idx 는 서술형 일련번호(서답형 1, 2, …; 전체 문항번호와 별개).
    번호줄의 ``[서술형 ]`` 플레이스홀더는 삭제 후 다시 쓴다.
    next_pos: 다음 슬롯(서술형/정답) 앵커 위치. 플레이스홀더 삭제가 **단 경계를 넘어**
    다음 슬롯 미주까지 먹지 않도록 클램프한다(서술형은 1/단이라 MoveSelDown 이 다음 단의
    슬롯으로 점프해 인접 미주를 삭제하는 버그가 있었음).
    """
    # contents 선두 라벨을 한 번만 쓰고 본문에서 제거(중복 라벨 → dedupe lineseg 손상 차단).
    disp_label, contents = _essay_label_and_body(q.contents, q.label_type or "서답형", label_idx)
    h.SetPos(pos[0], pos[1], pos[2])
    h.Run("MoveRight")                       # 번호(미주) 다음
    # 슬롯 템플릿: 번호줄 [서술형] + 빈줄 + 둘째 [서술형] 까지 선택 삭제([중단원] 전까지).
    # (이 삭제는 폼 [소단원][난이도] 메타란을 함께 먹지만, 발문/박스/post발문 렌더는 이 구조에
    #  의존한다 — 보수적 삭제 시 #18·#20 박스+post발문이 깨졌음. 메타란은 채움 **후** 토큰을
    #  찍고 저장후 XML(`_inject_essay_meta`)이 살아있는 MC 메타란 단락을 복제해 재주입한다.)
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
    _put_essay_label(ses, disp_label)
    # 발문 → 배점(발문 끝) → 조건/그림/블록수식. 소문항 있으면 본문 배점은 소문항에 위임.
    if q.sub_questions:
        # 소문항 부모: 발문 끝 [총 N점] 을 본문에서 분리. **배점은 발문 끝(표/그림 앞)에**
        # 두어야 한다 — 원본 PDF 가 "발문 …[N점]" 다음에 값/표/줄기-잎을 둔다(사용자
        # 2026-06-10). 과거엔 _put_qbody(발문+tail) 뒤에 총점을 찍어 표/잎 **다음**에
        # [총 N점]이 와 순서가 뒤집혔다. 기본 경로(_write_question)와 동일하게 발문 head →
        # 총점 → tail(표/그림) 순으로 직접 배치한다.
        body, total = _split_trailing_score(contents)
        if total is None:
            total = q.score
        ts = _tail_start(body)
        head = body if ts is None else body[:ts]
        tail = [] if ts is None else body[ts:]
        # 소문항이 **개별 배점**을 가질 때만 부모 배점이 '총점'("[총 N점]"). 소문항이
        # 배점 없는 단순 항목((1)(2)(3) 조건 나열, 상인고 #21)이면 부모 배점은 그 문제
        # 전체 배점이므로 평문 "[N점]"(완료본 일치). 기본 경로(_write_question)와 동일.
        subs_have_scores = any(getattr(s, "score", 0) for s in q.sub_questions)
        for b in head:
            _put_block(ses, b)
        if total:
            if subs_have_scores:
                _put_total_score(ses, h, total)
            else:
                _put_score(ses, h, total, essay=True)
        if tail:
            _put_tail(ses, h, tail)
        for k, sub in enumerate(q.sub_questions):
            ses.break_para()
            h.Run("ParagraphShapeAlignLeft")  # 직전 배점이 우측정렬됐어도 새 줄은 좌측
            _set_plain(h)
            ses.equation(f"({k + 1})")        # 소문항 마커 (1)(2)… 는 수식으로
            ses.text(" ")
            # OCR 이 남긴 앞머리 번호 마커 제거(우리 마커와 중복 방지) — 결정적·길이무관.
            # 소문항 배점도 서술형이면 우측정렬(기본 경로 _write_question 재귀와 동일).
            # allow_break=True: tail 없는 서술형 소문항 배점은 항상 줄바꿈 우측정렬(#22(2)).
            _put_qbody(ses, h, _strip_leading_submarker(sub.contents), sub.score,
                       essay=not sub.choices, allow_break=True)
            for _ in range(ESSAY_SUB_BLANKS):  # 소문항 답안 공간(2~3줄)
                ses.break_para()
                h.Run("ParagraphShapeAlignLeft")
    else:
        _put_qbody(ses, h, contents, q.score, essay=True)   # 소문항 없는 서술형(우측정렬)
    # 메타란([소단원][난이도]) 자리 토큰 — 모든 서술형 끝에 각 1줄. 저장후 _inject_essay_meta 가
    # 살아있는 MC 메타란 run 을 이 토큰 run 과 교체한다(폼 디자인·색상 동일, 사용자 2026-06-09:
    # "객관식이든 서술형이든 모든 문제 아래에 [소단원][난이도]를").
    for tok in (_META_TOKEN_SO, _META_TOKEN_NA):
        ses.break_para()
        h.Run("ParagraphShapeAlignLeft")
        _set_plain(h)
        ses.text(tok)
    # [난이도] 뒤 줄바꿈 — 안 하면 다음 슬롯(번호줄 [서술형 N]+미주)에 [난이도] 가 prepend 돼
    # "[난이도] 21. [서답형 5] …" 처럼 한 줄에 붙는다(#3, 2026-06-09). 빈 단락은 layout 이 정리.
    ses.break_para()
    h.Run("ParagraphShapeAlignLeft")
    _set_plain(h)


def _choice_len(choice) -> int:
    # LaTeX 원문 길이가 아니라 시각 글리프 근사(공유 `_choice_complexity`) — 근호·분수
    # 명령어 부풀림으로 짧은 보기가 1열 강등되던 것 수정(중앙중 #1·#2·#3, 2026-06-11).
    return _choice_complexity(choice)


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
            # ⚠️ 목표값(n_mc) 무조건 대입 금지 — Paste 비결정 실패(guard 소진)/이중삽입이면
            # 실제 슬롯 수와 어긋나 이후 앵커 산술 전체가 오염된다(감사 2026-06-10). 측정값으로.
            mc_form = _mc_count()
            if mc_form != n_mc:
                logger.warning("객관식 슬롯 grow 불일치: 목표 %d, 실제 %d — 실제값으로 진행",
                               n_mc, mc_form)
                n_mc = min(n_mc, mc_form)
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
            es_form = len(_en_anchors(h)) - _mc_count()   # 측정값(위 mc grow 와 동일 원칙)
            if es_form != n_es:
                logger.warning("서술형 슬롯 grow 불일치: 목표 %d, 실제 %d — 실제값으로 진행",
                               n_es, es_form)
                n_es = min(n_es, es_form)
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
            # 서술형 0개(n_es=0)면 위에서 서술형 슬롯이 전부 삭제돼 anc 가 MC 앵커뿐
            # (len==mc_form) → anc[mc_form] 은 IndexError. 그땐 정답 블록 앞까지 삭제.
            e0 = anc[mc_form] if mc_form < len(anc) else _answer_block_pos(h)
            if e0 is not None:
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
                  answer_pagebreak: bool = False, answer_blank_pages: int = 0,
                  pack_essays: bool = False) -> None:
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

    # 머리말/꼬리말 재정의 블록부터 마스킹 — 정답 구역용 header/footer 가 정답 container 와
    # **같은 본문 단락 안**에 통째로 들어 있는 폼(중3 빨강)이 있다. 안 가리면 꼬리말 내부
    # <hp:p> 가 '바깥 단락' 탐색(아래 (4) rfind)에 잡혀 정답 pageBreak·짝수보정 빈 페이지가
    # 꼬리말 subList 안에 박혀 무효가 된다(중앙중 중3 — 정답이 새 쪽으로 안 밀림, 2026-06-11).
    _mask(r"<hp:header\b.*?</hp:header>")
    _mask(r"<hp:footer\b.*?</hp:footer>")
    # 정답(답지) 블록 = '정답' 텍스트를 품은 그리기객체 컨테이너 — 통째 마스킹.
    # (container 한정 필수: 꼬리말 마스크에도 "(정답)" 텍스트가 있어 store 순회가 잡는다.)
    _mask(r"<hp:container\b.*?</hp:container>")
    answer_ph = next((f"@@X{i}@@" for i, s in enumerate(store)
                      if s.startswith("<hp:container") and "정답" in s), None)

    # 폼 잔존 단/쪽 나누기 리셋(마스킹된 정답 블록 내부는 보존, 내가 의도한 것만 재설정).
    sec = sec.replace('columnBreak="1"', 'columnBreak="0"').replace('pageBreak="1"', 'pageBreak="0"')

    _mask(r"<hp:endNote\b.*?</hp:endNote>")
    en_phs = [f"@@X{i}@@" for i, s in enumerate(store) if s.startswith("<hp:endNote")]
    _tbl_lo = len(store)
    _mask(r"<hp:tbl\b.*?</hp:tbl>")
    tbl_phs = {f"@@X{i}@@" for i in range(_tbl_lo, len(store))}   # 표(조건/보기 박스 포함) 플레이스홀더
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

    # (1) 폼 과잉 빈줄 삭제. **객관식 영역**은 전부 삭제(빽빽). **서술형 영역**은 ``pack_essays``
    # 면 연속 빈줄을 **1개로 collapse**(전부 삭제하면 소문항 (1)(2)가 딱 붙어 답란 구분이 안 됨 —
    # 사용자 2026-06-11 "소문항 사이 최소 한 줄"). pack_essays 아니면 서술형 빈줄 전부 보존.
    # (과거엔 pack_essays 가 서술형 빈줄도 전부 삭제 = 0줄; 메모리 form-layout-no-answer-space 갱신.)
    ops0 = _slot_opens(sec, en_phs)
    first = ops0[0]
    mc_end = ops0[n_mc] if (0 <= n_mc < len(ops0)) else len(sec)
    to_remove = []
    prev_empty_essay = False
    prev_was_box = False                       # 직전(비빈) 단락이 박스(표)였나
    for m in _PARA.finditer(sec):
        if m.start() < first:
            continue
        p = m.group(0)
        emp = is_empty(p)
        if m.start() < mc_end:                 # 객관식 영역: 빈줄 전부 삭제
            if emp:
                to_remove.append((m.start(), m.end()))
        elif pack_essays:                      # 서술형 영역
            if emp:
                # 박스(조건/보기) 바로 뒤 빈 줄은 **전부 삭제**(박스↔소문항 여백 없음 — 합의 #3
                # 일반화, 사용자 2026-06-11 "박스와 소문항 사이 여백은 없어야"). 그 외 연속
                # 빈줄은 1개로 collapse(소문항 사이 답란 최소 1줄 — form-layout-no-answer-space).
                if prev_was_box or prev_empty_essay:
                    to_remove.append((m.start(), m.end()))
                prev_empty_essay = True
            else:
                prev_empty_essay = False
        if not emp:                            # 빈 단락은 박스 상태 유지(박스+빈줄들 사이)
            prev_was_box = any(ph in p for ph in tbl_phs)
    for s, e in sorted(to_remove, reverse=True):
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
    _replace_retry(tmp, out_hwpx)


def _replace_retry(src, dst, attempts: int = 20, wait: float = 0.5) -> None:
    """os.replace 를 핸들 해제까지 재시도 — COM 측정(_measure_*) 의 hwp.Quit() 이
    비동기라 직후 os.replace 가 PermissionError 로 간헐 실패한다(2026-06-12 실측:
    _fix_answer_parity·패리티 재빌드 모두). 실패 시 임시파일 정리 후 재던짐."""
    import time
    for att in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if att == attempts - 1:
                try:
                    os.remove(src)
                except OSError:
                    pass
                raise
            time.sleep(wait)


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
        # ⚠️ Quit 은 finally 로 — Open/Find 예외 시 **보이는 고아 Hwp.exe** 가 남아
        # (문서화된 비결정 hang·RPC 주범) 방금 쓴 hwpx 핸들을 잡고 다음 os.replace 가
        # WinError 5 로 연쇄 실패한다(감사 2026-06-10).
        try:
            hwp.Open(str(hwpx), "HWPX", "")
            hwp.Run("MoveDocBegin")
            pos = []
            last = None
            guard = n * 4 + 8
            while len(pos) < n and guard > 0:
                guard -= 1
                if not _repeat_find(hwp, "①"):
                    break
                hwp.Run("Cancel")          # 선택 해제 → 캐럿이 매치 뒤
                gp = hwp.GetPos()
                cur = (gp[0], gp[1], gp[2])
                if last is not None and cur <= last:
                    break                  # RepeatFind 순환(wrap) — 새 매치 없음
                last = cur
                # 선택지 마커 ① 는 단락 첫 글자(캐럿 pos==1). 발문 문장 중간의
                # ①(예: "①~⑤에 들어갈 식을…", 도원중 #2)을 마커로 오인하면 측정이
                # 한 칸씩 밀려 높이 전체가 엉킨다(2026-06-11) → pos>1 은 건너뛴다.
                if gp[2] > 1:
                    continue
                ki = hwp.KeyIndicator()
                pos.append((ki[3], ki[4], ki[5]))
            return pos
        finally:
            try:
                hwp.Quit()
            except Exception:
                logger.warning("측정용 HWP Quit 실패 — 고아 프로세스 가능")
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
        try:    # Quit 은 finally 로(고아 Hwp.exe·파일핸들 잠금 방지 — 위 측정 함수와 동일)
            hwp.Open(str(hwpx), "HWPX", "")
            page = 0
            pos = _answer_block_pos(hwp)
            if pos is not None:
                hwp.SetPos(pos[0], pos[1], pos[2])
                page = hwp.KeyIndicator()[3]
            return page
        finally:
            try:
                hwp.Quit()
            except Exception:
                logger.warning("측정용 HWP Quit 실패 — 고아 프로세스 가능")
    finally:
        pythoncom.CoUninitialize()


def _fix_answer_parity(hwpx_path: str | Path) -> int:
    """정답(답지) 페이지 홀수쪽 **최종 검증·교정** — 모든 본문-높이 후처리 뒤 측정 기반.

    `_layout_form` 의 짝수 보정은 레이아웃 직후 측정인데, 그 **뒤** 후처리(<보기> 5×5 폼
    치환·서술형 메타란 주입 등)가 본문 높이를 키워 페이지 흐름이 한 쪽 밀리면 보정이
    어긋난다 — 측정 4쪽(빈장 삽입) → 최종 5+1=6쪽(경구중·새본리중), 측정 5쪽(보정 없음)
    → 최종 6쪽(월암중) 전부 **정답이 짝수쪽**으로 출하됐다(2026-06-12). 여기서 최종
    문서를 다시 측정해 짝수면: 정답 직전이 패리티 빈 단락이면 **제거**(한 쪽 당김),
    아니면 빈 단락(pageBreak)을 **삽입**(한 쪽 밀기). 반환 = 변경 여부(0/1).
    호출부는 변경 시 `_com_relaunder` 재실행으로 보안경고를 제거한다.
    """
    hwpx_path = Path(hwpx_path).resolve()   # HWP Open 은 상대경로를 조용히 실패(절대경로화 교훈)
    page = _measure_answer_page(hwpx_path)
    if not page or page % 2 == 1:
        return 0
    with zipfile.ZipFile(hwpx_path) as z:
        infos = z.infolist()
        data = {i.filename: z.read(i.filename) for i in infos}
    name = next(n for n in data if n.endswith("section0.xml"))
    sec = data[name].decode("utf-8")

    # 머리말/꼬리말을 **인덱스 보존** 공백 마스킹 — 중3 폼은 정답 구역 header/footer 가
    # 정답 container 와 같은 단락에 있어, 안 가리면 꼬리말 내부 단락/"(정답)" 이 잡힌다
    # (중앙중 교훈). 공백 치환이라 마스크 사본의 위치가 원본 sec 에 그대로 유효하다.
    masked = re.sub(r"<hp:header\b.*?</hp:header>|<hp:footer\b.*?</hp:footer>",
                    lambda m: " " * len(m.group(0)), sec, flags=re.S)
    ans = None
    for m in re.finditer(r"<hp:container\b.*?</hp:container>", masked, flags=re.S):
        if "정답" in m.group(0):
            ans = m.start()
            break
    if ans is None:
        logger.warning("[폼] 정답 패리티 교정: 정답 container 못 찾음 — 생략")
        return 0
    ap = masked.rfind("<hp:p ", 0, ans)            # 정답 바깥 단락
    if ap < 0:
        return 0

    def _is_simple_blank(span: str) -> bool:
        return (span.count("<hp:p") == 1 and "<hp:secPr" not in span
                and not re.sub(r"<[^>]+>", "", span).strip()
                and "<hp:pic" not in span and "<hp:gso" not in span)

    changed = False
    # (a) 제거 경로: 정답 직전 형제 단락이 '빈 pageBreak 단락'(초기 보정 잔재)이면 삭제.
    prev_end = len(sec[:ap].rstrip())
    if sec[:prev_end].endswith("</hp:p>"):
        ps = sec.rfind("<hp:p ", 0, prev_end)
        span = sec[ps:prev_end]
        if ps >= 0 and _is_simple_blank(span) and 'pageBreak="1"' in span[:span.find(">")]:
            sec = sec[:ps] + sec[prev_end:]
            changed = True
            logger.info("[폼] 정답 패리티 교정: 잉여 빈 페이지 제거(정답 %d→%d쪽)", page, page - 1)
    # (b) 삽입 경로: 잔재가 없으면 빈 pageBreak 단락 1장을 정답 앞에 끼워 홀수로 민다.
    if not changed:
        cands = [m.group(0) for m in re.finditer(r"<hp:p\b[^>]*>.*?</hp:p>", masked, flags=re.S)
                 if _is_simple_blank(m.group(0))]
        if not cands:
            logger.warning("[폼] 정답 패리티 교정: 빈 단락 템플릿 없음 — 생략")
            return 0
        blank = min(cands, key=len)
        bo = blank.find(">")
        open_tag = blank[:bo + 1]
        if "pageBreak=" in open_tag:
            open_tag = re.sub(r'pageBreak="\d"', 'pageBreak="1"', open_tag)
        else:
            open_tag = open_tag[:-1] + ' pageBreak="1">'
        sec = sec[:ap] + open_tag + blank[bo + 1:] + sec[ap:]
        changed = True
        logger.info("[폼] 정답 패리티 교정: 빈 페이지 삽입(정답 %d→%d쪽)", page, page + 1)

    if sec.count("<hp:p ") + sec.count("<hp:p>") != sec.count("</hp:p>"):
        raise RuntimeError("hp:p 태그 불균형 — 정답 패리티 교정 편집 오류")
    data[name] = sec.encode("utf-8")
    from core.hwp_com_writer import _rewrite_zip
    # ⚠️ 직전 _measure_answer_page 의 hwp.Quit() 이 비동기라 파일 핸들이 즉시 안 풀려
    # os.replace 가 PermissionError 로 실패한다(처음 통합 때 조용히 무변경 — 2026-06-12).
    # 핸들 해제까지 재시도.
    import time
    for _att in range(20):
        try:
            _rewrite_zip(hwpx_path, infos, data)
            break
        except PermissionError:
            if _att == 19:
                raise
            time.sleep(0.5)
    return 1


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
# 서술형 단당 최대 문항 수. 사용자 요구(2026-06-09): 기본 2개/단, **여유 있으면 객관식처럼
# 3개/단도 허용**. 답란 불필요(노트 풀이)라 높이가 허락하면 CAP 까지 빽빽(추정 기반).
# 메모리 form-layout-no-answer-space.
_ES_PER_COL = 3


def _repair_column_overflow(filled_hwpx, out_hwpx, blanks: dict, colbreak: set,
                            n_mc: int, cols: list) -> None:
    """최종 빌드의 각 단 시작 문항 (쪽,단)을 실측해 계획과 대조 — 밀렸으면 직전 단의
    빈줄을 줄여 재빌드(측정-검증-수리, 패리티 보정과 같은 패턴).

    `_extract_heights` 는 단 마지막 슬롯 높이를 같은 단 **평균**으로 추정하는데, 분수
    선택지(시각 높이 ~1.6줄)·메타란 줄이 몰린 문항이 단 끝에 오면 실제 단 높이가 CAP 을
    넘어 보이지 않는 꼬리(메타란 등)가 다음 단으로 흘러넘친다 → 이후 단나누기가 전부 한
    단씩 밀려 **중간에 빈 단**이 생긴다(도원중 중1 #13~15 단, 2026-06-11). 서술형 단은
    ① 앵커가 없어 검증 대상에서 제외(객관식 단만 — 서술형은 객관식 뒤라 연쇄로 복구됨).
    """
    for floor in (_MINGAP, 0):
        pos = _measure_first_choice_lines(out_hwpx, n_mc)
        if len(pos) < n_mc:
            logger.warning("[폼] 단 시작 검증 측정 실패(%d/%d) — 넘침 보정 생략",
                           len(pos), n_mc)
            return
        bad = None
        for k, c in enumerate(cols):
            expect = (k // 2 + 1, k % 2 + 1)          # 단 k → (쪽, 쪽내 단)
            got = (pos[c[0]][0], pos[c[0]][1])
            if got > expect:
                bad = k - 1                            # 늦게 시작 = 직전 단이 넘침
                break
            if got < expect:                           # 계획보다 이르면(비정상) 불개입
                return
        if bad is None or bad < 0:
            return
        shrunk = False
        for i in cols[bad][:-1]:
            if blanks.get(i, 0) > floor:
                blanks[i] = floor
                shrunk = True
        if not shrunk:
            logger.warning("[폼] 단%d 물리 넘침 감지 — 줄일 빈줄이 없어 보정 한계", bad)
            return
        logger.info("[폼] 단%d 물리 넘침 → 문항간 빈줄 %d로 축소 재빌드", bad, floor)
        _build_layout(filled_hwpx, out_hwpx, blanks, colbreak, n_mc,
                      answer_pagebreak=True, pack_essays=True)


def _estimate_essay_heights(essays) -> dict:
    """서술형 슬롯 높이(줄)를 **내용으로 결정적 추정**(COM 측정 불필요·견고).

    COM 텍스트 검색은 폼에서 불안정(``[`` 특수문자·정답페이지 라벨 중복)해 못 쓴다. 대신
    발문/소문항 글자수 + 표 행수 + 소문항 수로 추정한다. **보수적 과대추정**(단 넘침 방지) —
    답란을 안 두므로 약간 빽빽해도 무방하고, 과소추정으로 한 단에 너무 많이 몰아 넘치는 게
    더 나쁘다(메모리 form-layout-no-answer-space).
    """
    # 학남고 확통 5개 서술형 실측(렌더 줄수)에 맞춰 보정(2026-06-09): CPL 26, 수식폭 0.4,
    # 표=행+테두리1, 소문항=마커 1줄. 실측 [6,12,10,13,16] ≈ 추정 [9,13,13,14,17](±1~3,
    # 약간 과대 — 단 넘침 방지). 짧은 서술형 3개가 한 단(CAP 46)에 들어가도록 과대를 줄였다.
    CPL = 26                                    # 단 한 줄당 본문 글자수(한글+수식 혼합 실측)
    heights = {}
    for idx, q in enumerate(essays):
        text = sum(len(b.value or "") for b in q.contents if b.type == ContentType.TEXT)
        eq = sum(len(b.value or "") for b in q.contents
                 if b.type in (ContentType.EQUATION, ContentType.EQUATION_BLOCK))
        tables = sum(1 for b in q.contents if b.type == ContentType.TABLE)
        rows = sum(len(b.rows or []) for b in q.contents if b.type == ContentType.TABLE)
        sub_text = sum(len(b.value or "") for s in (q.sub_questions or [])
                       for b in (s.contents or []) if b.type == ContentType.TEXT)
        inline = text + sub_text + int(eq * 0.4)
        h = 2                                   # 번호줄 + 여유
        h += -(-inline // CPL)                  # ceil(inline/CPL)
        h += (rows + 1) if tables else 0        # 표(행 + 헤더 테두리)
        h += len(q.sub_questions or [])         # 소문항 마커/배점 1줄씩
        h += 2                                  # [소단원][난이도] 메타란(저장후 주입, 2026-06-09)
        heights[idx] = max(3, h)
    return heights


def _estimate_mc_heights(mc) -> dict:
    """객관식 슬롯 높이(줄)를 **내용 기반 결정적 추정**(COM 측정 실패 시 폴백용).

    평소엔 `_measure_first_choice_lines` 실측을 쓰지만, COM 측정이 실패(보안팝업·gen_py·
    환경)하면 과거엔 균일 빈줄 4로 폴백해 **과여백**이 났다(사용자 보고, HANDOFF §7-2).
    그 대신 서술형(`_estimate_essay_heights`)과 같은 방식으로 발문·수식·표·선택지에서 줄수를
    추정해 `_adaptive_columns` 로 빽빽 배치한다 → 측정이 실패해도 과여백 없음. **보수적
    과대추정**(단 넘침 방지). 측정이 되면 이 함수는 안 쓰인다.
    """
    CPL = 26                                    # 단 한 줄당 본문 글자수(서술형 추정기와 동일)
    heights = {}
    for idx, q in enumerate(mc):
        text = sum(len(b.value or "") for b in q.contents if b.type == ContentType.TEXT)
        eq = sum(len(b.value or "") for b in q.contents
                 if b.type in (ContentType.EQUATION, ContentType.EQUATION_BLOCK))
        rows = sum(len(b.rows or []) for b in q.contents if b.type == ContentType.TABLE)
        tables = sum(1 for b in q.contents if b.type == ContentType.TABLE)
        inline = text + int(eq * 0.4)
        h = 1                                   # 번호줄
        h += -(-inline // CPL)                  # ceil(발문/CPL)
        h += (rows + 1) if tables else 0        # 표(행 + 헤더 테두리)
        # 선택지: 짧으면 2열(①②/③④/⑤)=3줄, 길면 1열 5줄(가장 긴 보기로 판정)
        ch_max = max((sum(len(b.value or "") for b in (c.contents or []))
                      for c in (q.choices or [])), default=0)
        h += 5 if ch_max > 12 else 3
        heights[idx] = max(3, h)
    return heights


# 거대 문항(예: 수학적 귀납법 증명 박스 #12)은 한 단에 **혼자** 둔다(사용자 2026-06-10).
# 내용기반 추정 줄수가 이 값 이상이면 단독 단(앞뒤로 단나누기). CAP 의 ~40%(다른 2문항과
# 같이 두면 단을 넘침). 일반 문항(추정 5~13줄)은 해당 없음.
_SOLO_MC_LINES = 18


def _adaptive_columns(heights: dict, n: int, per_col_max: int, rebalance_tail: bool = True,
                      solo: set | None = None):
    """측정 높이로 **스마트 단배치**: 한 단(CAP 줄) 안에서 문항 수를 가변(최대 per_col_max).

    rebalance_tail: 마지막 단이 1문항이면 직전 단에서 끌어와 균형(객관식용). 서술형은 끄면
    가운데 단이 외톨이가 되는 걸 피하고 마지막 단에 단독을 둔다(자연스러움, 사용자 2026-06-09).

    - 긴 문항이 섞이면 단당 2개로 줄여 단을 넘기지 않게, 짧으면 3개까지 채운다(그리디).
    - 각 단의 남는 여유(CAP-내용)는 문항 사이 빈줄로 균등 분배(여유로운 배치). 단 마지막
      슬롯은 0(단나누기로 다음 단). 긴 단일수록 빈줄이 자동으로 줄어든다(사용자 요구
      2026-06-05: 문제가 길면 여백을 더 줄이거나 단당 2개로).

    Returns: (colbreak:set[새 단 시작 인덱스], blanks:dict[i→후행 빈줄], cols:list[list[i]]).
    """
    solo = solo or set()
    fb = CAP // per_col_max
    cols: list[list[int]] = []
    cur: list[int] = []
    cur_h = 0
    for i in range(n):
        h = heights.get(i, fb)
        # 거대 문항은 단독 단 — 현재 단을 닫고 자기만의 단에 두고, 다음 문항은 새 단에서.
        if i in solo:
            if cur:
                cols.append(cur)
                cur, cur_h = [], 0
            cols.append([i])
            continue
        prospective = cur_h + (_GAP if cur else 0) + h
        if cur and (prospective > CAP or len(cur) >= per_col_max):
            cols.append(cur)
            cur, cur_h = [], 0
        cur.append(i)
        cur_h += (_GAP if len(cur) > 1 else 0) + h
    if cur:
        cols.append(cur)

    # 트레일링 리밸런스: 마지막 단에 문항이 **1개만** 남으면(예: 16개를 3씩 → …,3,1)
    # 직전 단의 끝 문항을 끌어와 (…,2,2) 로 균형(외로운 끝 단의 큰 과여백 완화). 직전 단이
    # 2개 이상이고, 옮겨도 마지막 단이 CAP 안에 들 때만(행정렬·단넘침 안전).
    def _col_h(col):
        return sum(heights.get(i, fb) for i in col) + _GAP * max(0, len(col) - 1)
    if (rebalance_tail and len(cols) >= 2 and len(cols[-1]) == 1 and len(cols[-2]) >= 2
            and cols[-1][0] not in solo and cols[-2][-1] not in solo
            and _col_h([cols[-2][-1]] + cols[-1]) <= CAP):
        cols[-1].insert(0, cols[-2].pop())

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


def _layout_form(filled_hwpx, out_hwpx, per_col: int, n_mc: int, n_es: int,
                 essays=None, mc=None) -> None:
    """채운 hwpx → 혼합 레이아웃. 객관식·서술형 **둘 다 측정 기반 빽빽배치**.

    학생 답란 공간은 보존하지 않는다(노트 풀이 전제 — 메모리 form-layout-no-answer-space).
    객관식은 행정렬(per_col/단), 서술형도 높이 측정 후 단당 여러 개를 채운다(`_adaptive_columns`).
    측정 tight 빌드는 객관식 고정 per_col + **서술형 연속배치**(단나누기 없음, 높이 측정용).
    """
    n = n_mc + n_es
    # 측정 tight: 객관식만 고정 per_col 단나누기. 서술형은 연속배치(높이 측정 위해 단나누기
    # 없음) + pack_essays 로 폼 답란 빈줄 제거. 첫 서술형 경계는 측정엔 불필요.
    measure_colbreak = set(range(per_col, n_mc, per_col))

    tight = str(Path(out_hwpx).with_suffix("")) + "_tight.hwpx"
    _build_layout(filled_hwpx, tight, {i: _MINGAP for i in range(n)}, measure_colbreak,
                  n_mc, pack_essays=True)
    pos = _measure_first_choice_lines(tight, n_mc) if n_mc else []
    try:
        os.remove(tight)
    except Exception:
        pass
    # 서술형 높이는 **내용 기반 결정적 추정**(COM 텍스트 검색은 라벨 번호가 수식 객체라
    # 쪼개져 불안정 — 사용자 지적 2026-06-09). 추정 실패 없음(객체만 있으면 항상 계산).
    es_heights = _estimate_essay_heights(essays) if (n_es and essays) else {}

    # 거대 문항(수학적 귀납법 증명 박스 #12 등) = 내용기반 추정 줄수가 큰 객관식 → 단독 단.
    # COM 실측은 박스 높이를 과소추정(#12 측정 15 vs 실제 ~24)하므로 **추정으로 solo 판정**.
    mc_est = _estimate_mc_heights(mc) if (n_mc and mc) else {}
    solo_mc = {i for i, h in mc_est.items() if h >= _SOLO_MC_LINES}
    if solo_mc:
        logger.info("폼 거대문항 단독 단: %s", sorted(i + 1 for i in solo_mc))

    blanks: dict = {}
    colbreak: set = set(range(per_col, n_mc, per_col))     # 폴백 기본(객관식 고정 per_col)
    mc_cols: list | None = None               # 측정 기반 단 구성(넘침 검증용)
    # ── 객관식 적응배치 ──
    if n_mc:
        if len(pos) >= n_mc:
            heights = _extract_heights(pos, n_mc, per_col)
            for i in solo_mc:                 # 거대문항은 실측 과소추정 → 추정으로 보정
                heights[i] = max(heights.get(i, 0), mc_est.get(i, 0))
            obj_colbreak, mc_blanks, cols = _adaptive_columns(heights, n_mc, per_col, solo=solo_mc)
            colbreak = set(obj_colbreak)
            blanks.update(mc_blanks)
            mc_cols = cols
            logger.info(
                "폼 객관식 스마트 단배치(측정 %d/%d): %d개 단, 단당문항=%s",
                len(pos), n_mc, len(cols), [len(c) for c in cols])
        elif mc:
            # 측정 실패 → **내용 기반 추정**으로 단배치(균일 빈줄 4의 과여백 회피).
            # 단, 추정 높이는 실측과 달라 `_adaptive_columns` 의 fill-to-CAP 빈줄이 단을
            # 넘칠 수 있다(짧은 문항이 모인 단의 과여백·오버플로우) → **최소 간격 빽빽 패킹**
            # 으로 단 상단부터 채운다(행정렬 포기, 안전 우선).
            mc_heights = _estimate_mc_heights(mc)
            obj_colbreak, _ignore, cols = _adaptive_columns(mc_heights, n_mc, per_col, solo=solo_mc)
            colbreak = set(obj_colbreak)
            for c in cols:
                for i in c:
                    blanks[i] = 0 if i == c[-1] else _GAP
            logger.warning(
                "[FALLBACK] 폼 객관식 COM 측정 실패(%d/%d) → 내용기반 추정 빽빽배치(%d개 단, "
                "단당=%s). COM 측정(보안팝업·gen_py) 확인 권장.",
                len(pos), n_mc, len(cols), [len(c) for c in cols])
        else:
            logger.warning(
                "[FALLBACK] 폼 객관식 측정 실패(%d/%d)·문항 미전달 → 고정 per_col + 균일 빈줄(4). "
                "과여백/단넘침 가능 — COM 측정(보안팝업·gen_py) 확인 필요.", len(pos), n_mc)
            colbreak = set(range(per_col, n_mc, per_col))
            blanks.update({i: 4 for i in range(n_mc)})

    # ── 서술형 적응 빽빽배치(신규) ── 첫 서술형은 항상 새 단(객관식↔서술형 경계).
    if n_es:
        colbreak.add(n_mc)
        if len(es_heights) >= n_es:
            # 서술형 구역도 2단. 추정 높이로 단당 최대 _ES_PER_COL(2)개 채운다(답란 불필요).
            # 여백은 객관식과 **동일한 스마트 분배**(`_adaptive_columns` 행정렬 여백) — 문항을
            # 단 상단에 붙이지 않고 적절히 띄워 단을 고르게 채운다(사용자 2026-06-09).
            es_cb, es_blanks, es_cols = _adaptive_columns(
                es_heights, n_es, _ES_PER_COL, rebalance_tail=False)
            colbreak |= {i + n_mc for i in es_cb}             # 0-기준 → 전체 슬롯 인덱스
            blanks.update({i + n_mc: v for i, v in es_blanks.items()})
            logger.info("폼 서술형 빽빽배치(추정 %d): 단당=%s",
                        n_es, [len(c) for c in es_cols])
        else:
            # 추정 불가(essays 미전달) → 기존 1/단 폴백(안전).
            logger.warning("[FALLBACK] 폼 서술형 추정 불가 → 1/단.")
            colbreak |= set(range(n_mc, n))
            blanks.update({i: 0 for i in range(n_mc, n)})

    # 정답(답지) 블록을 새 페이지로 보낸 뒤, 짝수쪽에 떨어지면 빈 페이지 1장으로 밀어
    # 홀수쪽에 오도록(문제는 짝수쪽 마무리). 정답 페이지를 측정해 패리티 보정.
    _build_layout(filled_hwpx, out_hwpx, blanks, colbreak, n_mc,
                  answer_pagebreak=True, pack_essays=True)
    # 단 물리 넘침 자가치유(빈 단 방지) — 패리티 측정 **전에**(재빌드가 쪽수를 바꿈).
    if mc_cols and n_mc:
        _repair_column_overflow(filled_hwpx, out_hwpx, blanks, colbreak, n_mc, mc_cols)
    ans_page = _measure_answer_page(out_hwpx)
    if ans_page and ans_page % 2 == 0:
        _build_layout(filled_hwpx, out_hwpx, blanks, colbreak, n_mc,
                      answer_pagebreak=True, answer_blank_pages=1, pack_essays=True)


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
    # HWP COM Quit 비동기 핸들 레이스 — os.replace 직행은 PermissionError 로 간헐 전실패
    # (계성고 머리말 '2024년 학기 고사' 0/2 잔존, 2026-06-12). _replace_retry 통일.
    _replace_retry(tmp, hwpx_path)
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
    _replace_retry(tmp, hwpx_path)   # COM Quit 핸들 레이스 — 라벨 sync 등 공용(계성고 계열)


# 폼 grow 서술형 슬롯의 잔존 라벨([서답형 N]) 뒤에 우리 라벨([서술형 N])이 붙어 중복됨.
# 뒤에 또 다른 '[' 라벨이 따라오는 [서…형 N] 만 제거 → 우리 라벨만 남긴다. (같은 <hp:t>
# 안에서만 매칭되므로 태그 균형 안전. 문제 길이·개수와 무관한 결정적 후처리.)
# 괄호는 [ ] 와 【 】 둘 다(OCR 혼용). 앞 라벨 뒤에 또 라벨이 오면 앞 것 제거.
_DUP_LABEL_RE = re.compile(
    r'[\[【]\s*(?:서[답술]형|단답형)\s*\d+\s*[\]】]\s*(?=[\[【]\s*(?:서[답술]형|단답형))')


# 폼 슬롯 라벨 ``[서술형 ]`` 의 번호가 **수식 객체**로 남는 경우(grow 슬롯 COM 라벨삭제 실패).
# 예: ``<hp:t> [서술형 </hp:t><hp:equation>…script 5…</hp:equation><hp:t>] `` → 번호 5 가 수식.
# 사용자(2026-06-09): "[서술형 5] 의 5 는 텍스트여야". 결정적 후처리로 eq 번호를 **텍스트**로
# in-place 치환(단락 조작 없음 → lineseg 안전, 멱등).
_ESSAY_NUM_EQ_RE = re.compile(
    r'(\[\s*서[술답]형\s*)</hp:t>\s*<hp:equation\b[^>]*>'
    r'(?:(?!</hp:equation>).)*?<hp:script\b[^>]*>\s*(\d+)\s*</hp:script>'
    r'(?:(?!</hp:equation>).)*?</hp:equation>\s*<hp:t>(\s*\])',
    re.S)


def _textify_essay_label_numbers(hwpx_path: str | Path) -> int:
    """서술형 라벨 ``[서술형/서답형 N]`` 의 번호가 수식 객체면 **평문 텍스트**로 치환(저장후 XML).

    grow 슬롯의 폼 placeholder 라벨이 번호를 수식으로 남기는 걸 결정적으로 보정. Returns: 치환 수.
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
        sec2, n = _ESSAY_NUM_EQ_RE.subn(r"\1\2\3", sec)
        if n:
            data[name] = sec2.encode("utf-8")
            total += n
    if total:
        _repackage_hwpx(hwpx_path, infos, data)
    return total


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
        # ⚠️ 삭제 대신 **동일 길이 공백 치환** — <hp:t> 텍스트를 줄이면 linesegarray 가
        # 안 맞아 직후 _com_relaunder 가 단락+미주를 통째 드롭한다(메모리
        # `hwpx-lineseg-relaunder-trap`, 서답형 4·5 증발의 근본원인과 같은 패턴).
        # 한계: 잔존 라벨 번호가 수식 객체로 쪼개진 형태는 태그를 넘어 매칭 불가(미보정).
        sec2, n = _DUP_LABEL_RE.subn(lambda m: " " * len(m.group(0)), sec)
        if n:
            data[name] = sec2.encode("utf-8")
            total += n
    if total:
        _repackage_hwpx(hwpx_path, infos, data)
    return total


# 라벨 유형 단어만 치환(번호가 텍스트 ``[서술형 5]`` 든 수식 객체 ``[서술형 <hp:equation>5
# </hp:equation>]`` 든 무관). 정답 페이지 라벨은 폼이 번호를 **수식 객체**로 구워둬 ``\d+`` 를
# 요구하던 옛 패턴이 매치 실패했다(중앙고 27 "[서술형 5]" 잔존, 2026-06-10). 여는 ``[`` 직후
# 유형단어 + (숫자] 또는 <hp:equation = 수식번호) 일 때만 라벨로 확정(본문 일반어 "서술형으로
# 답하라" 는 여는 ``[`` 가 없어 제외). 유형 단어만 바꾸고 번호·닫는 ``]`` 는 보존.
_ESSAY_LABEL_SYNC_RE = re.compile(r'(\[\s*)(?:서술형|서답형|단답형)')
_LABEL_WORD_XML_RE = re.compile(r'\[\s*(서술형|서답형|단답형)')


def _label_words_in_xml(hwpx_path: str | Path) -> set:
    """섹션 XML 에 남은 ``[…형`` 라벨 유형 단어 집합(혼용 잔존 검사용 — relaunder 후 호출)."""
    with zipfile.ZipFile(Path(hwpx_path)) as z:
        full = "".join(z.read(n).decode("utf-8") for n in z.namelist()
                       if re.search(r"section\d+\.xml$", n))
    return set(_LABEL_WORD_XML_RE.findall(full))


def _sync_essay_label_word(hwpx_path: str | Path, target: str) -> int:
    """모든 ``[서술형/서답형/단답형 N]`` 라벨의 **유형 단어**를 ``target`` 으로 통일(저장후 XML).

    문제 라벨은 content_parser 가 통일하지만, **폼이 구워둔 정답 페이지 라벨**(``[서술형 N]``)은
    OCR/파서를 안 거쳐 그대로 남는다(사용자 2026-06-09: 정답 페이지도 서답형으로). 라벨 패턴
    (``[…형 N]``, 번호 포함)만 매칭하므로 본문의 일반 단어("서술형으로 답하라")는 안 건드린다.
    Returns: 치환 수.
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
        sec2, n = _ESSAY_LABEL_SYNC_RE.subn(rf"\g<1>{target}", sec)
        if n:
            data[name] = sec2.encode("utf-8")
            total += n
    if total:
        _repackage_hwpx(hwpx_path, infos, data)
    return total


# 서술형 라벨 번호 = ``[…형 ``(텍스트) + **수식 객체**(`<hp:script>N</hp:script>`) + ``]``.
# 본문 라벨(우리 삽입)과 정답 페이지 라벨(폼 native grow)이 문서순으로 (본문,정답) 쌍 교차.
# grow 슬롯 복사가 5번 슬롯을 베껴 마지막 라벨이 ``5``로 남고(6이어야), 어느 쪽이 틀리는지
# 매 렌더 비결정적으로 뒤바뀐다(상인고 #25). 라벨 단어 통일 후 번호도 결정적으로 재부여한다.
_ESSAY_LABEL_NUM_RE = re.compile(
    r'(<hp:t>[^<]*\[\s*(?:서술형|서답형|단답형)\s*</hp:t>'
    r'<hp:equation\b(?:(?!</hp:equation>).)*?<hp:script>)(\d+)(</hp:script>)', re.S)


_ESSAY_WORD_IN_LABEL_RE = re.compile(r'(?:서술형|서답형|단답형)(?=\s*</hp:t>)')


def _renumber_essay_labels(hwpx_path: str | Path, n_essays: int, words=None, nums=None) -> int:
    """모든 ``[…형 N]`` 라벨 번호를 **문서순 (본문,정답) 쌍**으로 결정적 재부여(저장후 XML).

    폼 grow 가 마지막 서술형 답지 라벨을 ``[서술형 5]``(6이어야)로 굽고, COM 비결정성으로 본문/
    정답 중 어느 쪽이 어긋나는지 렌더마다 뒤바뀌는 것을 결정적으로 고친다. 번호는 **수식 객체
    `<hp:script>`** 안 숫자라 텍스트 길이·lineseg 불변(직후 `_com_relaunder` 가 재렌더). 라벨 수가
    ``2×서술형수`` 가 아니면(비결정 paste 누락/이중) 건드리지 않는다(오손상 방지). Returns: 변경 수.

    words: 서술형별 유형 단어 리스트([서술형/단답형/…], essay 순). 주면 정답 페이지 라벨까지
    문항별 유형으로 통일(서술형·단답형 **혼합 시험지** — 능인고 수1, 2026-06-10). 폼이 구워둔
    정답 라벨은 한 단어(서술형)뿐이라, 쌍의 essay 인덱스(i//2)로 본문 유형을 따라 맞춘다.

    nums: essay 순 **원본 라벨 번호** 리스트(OCR 인쇄 그대로). 주면 통합 일련번호 1,2,…,n 대신
    이 번호를 쓴다 — 유형별 독립 번호 시험지(정화중 단답형 1~4·서술형 1~3)와 통합 번호 시험지
    (능인고 서술형 1~3·단답형 4~5)가 폼마다 달라, 통합 강제(i//2+1)가 정화중 서술형을 [서술형 5]
    로 굽던 것(2026-06-12). 능인고는 nums=[1,2,3,4,5]=통합과 동일이라 무회귀.
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
        matches = list(_ESSAY_LABEL_NUM_RE.finditer(sec))
        if not matches:
            continue
        if n_essays and len(matches) != 2 * n_essays:
            logger.warning("서술형 라벨 수 불일치: 라벨 %d, 기대 %d(=2×%d) — 재부여 생략",
                           len(matches), 2 * n_essays, n_essays)
            continue
        out, prev = [], 0
        for i, m in enumerate(matches):
            out.append(sec[prev:m.start()])
            ei = i // 2
            want = str(nums[ei]) if (nums and ei < len(nums)) else str(ei + 1)
            g1 = m.group(1)
            if words and i // 2 < len(words) and words[i // 2]:
                g1n, wn = _ESSAY_WORD_IN_LABEL_RE.subn(words[i // 2], g1)
                if wn and g1n != g1:
                    total += 1
                    g1 = g1n
            if m.group(2) != want:
                total += 1
            out.append(g1 + want + m.group(3))
            prev = m.end()
        out.append(sec[prev:])
        data[name] = "".join(out).encode("utf-8")
    if total:
        _repackage_hwpx(hwpx_path, infos, data)
    return total


def _inject_essay_meta(hwpx_path: str | Path) -> int:
    """서술형 끝 메타란 토큰 run 을 **살아있는 폼 [소단원]/[난이도] run** 으로 1:1 교체.

    폼 서술형 슬롯의 원본 메타란은 라벨 플레이스홀더 삭제 때 함께 지워지므로, 채움 단계에서
    토큰 단락(소단원·난이도 각 1줄)만 찍어 두고 여기서 재주입한다(사용자 2026-06-09: 모든
    문제 아래 [소단원][난이도]를 폼과 **동일한 디자인·색상**으로). 템플릿은 같은 문서에
    **살아남은 객관식 슬롯 메타란 단락**의 첫 ``<hp:run>``(마크펜 색·charPr ID 유효)을 그대로
    복제한다 — **run 단위 교체**라 단락 경계/중첩과 무관하게 태그 균형이 보장된다(과거 단락단위
    치환은 박스로 끝난 서술형의 중첩 토큰에서 깨졌다). linesegs 는 직후 ``_com_relaunder``
    재저장에서 HWP 가 재계산한다. Returns: 교체된 run 수.
    """
    hwpx_path = Path(hwpx_path)
    with zipfile.ZipFile(hwpx_path) as z:
        infos = z.infolist()
        data = {i.filename: z.read(i.filename) for i in infos}

    def _first_run(para):
        m = re.search(r"<hp:run\b.*?</hp:run>", para or "", re.S) if para else None
        return m.group(0) if m else None

    total = 0
    for name in list(data):
        if not re.search(r"section\d+\.xml$", name):
            continue
        sec = data[name].decode("utf-8")
        if _META_TOKEN_SO not in sec and _META_TOKEN_NA not in sec:
            continue
        paras = re.findall(r"<hp:p\b.*?</hp:p>", sec, re.S)

        def _ptext(p):
            return re.sub(r"<[^>]+>", "", p)
        # 템플릿 탐색에서 **토큰 단락 자신을 제외**한다 — 토큰("소단원자리표식QZX")도 "소단원"
        # 을 포함해, 폼에 진짜 [소단원] 템플릿이 없으면 토큰을 템플릿으로 오인해 자기 자신으로
        # 교체(no-op) → 평문 leak(경운중 폼은 [난이도]만 있고 [소단원] 없음, 2026-06-09).
        # 폼마다 단원 메타란 라벨이 [소단원] 또는 [중단원] 으로 다르다(강동중 폼은 [중단원]).
        # 어느 쪽이든 살아있는 MC 단원 메타란 run 을 찾아 서술형에 주입한다(사용자 2026-06-10:
        # 객관식엔 [중단원] 있는데 서술형엔 누락 — "소단원"만 찾아 [중단원] 폼에서 못 찾던 버그).
        run_so = _first_run(next((p for p in paras
                                  if ("소단원" in _ptext(p) or "중단원" in _ptext(p))
                                  and _META_TOKEN_SO not in p), None))
        run_na = _first_run(next((p for p in paras
                                  if "난이도" in _ptext(p) and _META_TOKEN_NA not in p), None))
        for tok, run in ((_META_TOKEN_SO, run_so), (_META_TOKEN_NA, run_na)):
            if run is None:
                # 폼에 이 메타 템플릿이 없음 → 토큰 단락을 통째 제거(평문 노출 방지). 단락 단위
                # 제거라 태그 균형 유지(토큰은 중첩 없는 자기-단락). linesegs 는 _com_relaunder 가 재계산.
                para_re = re.compile(
                    r"<hp:p\b(?:(?!</hp:p>).)*?" + re.escape(tok) + r"(?:(?!</hp:p>).)*?</hp:p>", re.S)
                sec, n = para_re.subn("", sec)
                total += n
                continue
            # 토큰 텍스트를 품은 run 통째를 메타란 run 으로 교체(run 1개 ↔ run 1개, 균형 보장).
            tok_run_re = re.compile(
                r"<hp:run\b[^>]*>(?:(?!</hp:run>).)*?" + re.escape(tok) + r"(?:(?!</hp:run>).)*?</hp:run>",
                re.S)
            sec, n = tok_run_re.subn(lambda m: run, sec)
            total += n
        data[name] = sec.encode("utf-8")
    if total:
        _repackage_hwpx(hwpx_path, infos, data)
    return total


def _count_meta_tokens(hwpx_path: str | Path) -> int:
    """section XML 의 메타란 토큰(소단원/난이도 자리표식) 연속-문자열 개수. relaunder 후
    (run=1 정규화) 호출해야 정확하다(쪼개진 토큰은 0 으로 세질 수 있음)."""
    hwpx_path = Path(hwpx_path)
    with zipfile.ZipFile(hwpx_path) as z:
        n = 0
        for info in z.infolist():
            if re.search(r"section\d+\.xml$", info.filename):
                sec = z.read(info.filename).decode("utf-8")
                n += sec.count(_META_TOKEN_SO) + sec.count(_META_TOKEN_NA)
    return n


def _strip_residual_meta_tokens(hwpx_path: str | Path) -> int:
    """최종 안전망 — relaunder 후에도 남은 메타란 토큰의 **텍스트만 비운다**(평문 노출 방지).

    `_inject_essay_meta` 의 토큰 교체/제거가 COM 비결정(토큰 run 이 쪼개졌다 relaunder 가
    run=1 로 정규화)으로 가끔 실패해 ``소단원자리표식QZX`` 가 평문 노출된다(효성중 4중 1회,
    2026-06-12). 토큰 문자열을 ``""`` 로 치환 — run/단락 구조는 유지(빈 메타란 한 줄)되고
    lineseg 영향은 빈 텍스트라 미미. 호출부는 변경 시 relaunder 로 재저장(보안경고 제거).
    Returns: 비운 토큰 수.
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
        n = sec.count(_META_TOKEN_SO) + sec.count(_META_TOKEN_NA)
        if n:
            sec = sec.replace(_META_TOKEN_SO, "").replace(_META_TOKEN_NA, "")
            data[name] = sec.encode("utf-8")
            total += n
    if total:
        _repackage_hwpx(hwpx_path, infos, data)
        logger.warning("[폼] 메타란 토큰 비결정 잔존 %d개 — 텍스트 비움(최종 안전망)", total)
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
        _replace_retry(tmp, hwpx_path)   # 방금 Quit 한 COM 의 핸들 레이스 — 직행 금지
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
        # 혼합 레이아웃(객관식 행정렬 + 서술형 빽빽배치 2개/단, 답란 미보존).
        # mc 도 넘겨 COM 측정 실패 시 내용기반 추정으로 폴백(과여백 회피).
        _layout_form(filled, output_path, per_col, n_mc, n_es, essays=essays, mc=mc)
    finally:
        try:
            os.remove(filled)
        except Exception:
            pass
    # 1.5단계: 서술형 라벨 후처리 — 중복 라벨 제거.
    # (라벨 번호는 이제 `_put_essay_label` 이 **수식**으로 쓴다 — 사용자 2026-06-09: "[서답형 5]
    #  의 5는 수식". 과거 _textify_essay_label_numbers(번호 수식→텍스트)는 그 반대라 제거했다.)
    try:
        _dedupe_essay_labels(output_path)
    except Exception as e:  # noqa: BLE001
        logger.warning("폼 후처리 실패(_dedupe_essay_labels): %s", e)
    # 1.55단계: 유형 라벨 통일 — 문제 라벨은 파서가 통일했으나 폼이 구워둔 정답 페이지 라벨이
    # 남는다. **서술형별 유형 단어**(서술형/단답형/서답형)를 essay 순으로 모은다. 서술형·단답형
    # **혼합 시험지**(능인고 수1)면 문항마다 다르므로 단일 통일은 틀린다 → 균일할 때만 통일하고,
    # 혼합이면 `_renumber_essay_labels(words=…)` 가 정답 라벨을 쌍의 본문 유형으로 맞춘다.
    _word_re = re.compile(r"(서술형|서답형|단답형)")

    def _essay_word(q):
        w = getattr(q, "label_type", "") or ""
        if w:
            return w
        joined = "".join(b.value or "" for b in q.contents[:6]
                         if getattr(b, "type", None) == ContentType.TEXT)
        m = _word_re.search(joined)
        return m.group(1) if m else "서답형"
    _words = [_essay_word(q) for q in essays]
    # essay 순 **원본 라벨 번호**(OCR 인쇄 그대로) — 통합 일련번호 강제 대신 원본 보존.
    # 유형별 독립(정화중 단답형 1~4·서술형 1~3) vs 통합(능인고 서술형 1~3·단답형 4~5)이
    # 폼마다 달라, 통합 강제가 정화중 서술형을 [서술형 5]로 굽던 것(2026-06-12).
    def _essay_num(q, idx):
        lbl, _ = _essay_label_and_body(q.contents, q.label_type or "서답형", idx + 1)
        m = re.match(r'^\[\s*\S+?\s*(\d+)\s*\]$', lbl)
        return int(m.group(1)) if m else idx + 1
    _nums = [_essay_num(q, i) for i, q in enumerate(essays)]
    try:
        if _words and len(set(_words)) == 1:        # 균일 시험지: 한 단어로 통일(기존 경로)
            _sync_essay_label_word(output_path, _words[0])
    except Exception as e:  # noqa: BLE001
        logger.warning("폼 후처리 실패(_sync_essay_label_word): %s", e)
    # 1.57단계: 서술형 라벨 **번호+유형** 결정적 재부여 — 폼 grow 가 마지막 답지 라벨을 5(6이어야)로
    # 굽고 COM 비결정성으로 본문/정답 중 한쪽이 어긋남(상인고 #25). 문서순 (본문,정답) 쌍을
    # 원본 번호(_nums)로. words 로 정답 라벨 유형도 문항별로 맞춤(혼합 시험지). _com_relaunder **전**.
    try:
        _renumber_essay_labels(output_path, len(essays), words=_words, nums=_nums)
    except Exception as e:  # noqa: BLE001
        logger.warning("폼 후처리 실패(_renumber_essay_labels): %s", e)
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
    # 1.85단계: 강조 밑줄 실선 검정 강제(폼 기본 밑줄=회색 점선 상속 보정, 기본 경로와
    # 동일). _com_relaunder **전**에 해 재저장 때 HWP 가 실선 검정으로 굳히게 한다.
    try:
        from core.hwp_com_writer import _solidify_underline
        _solidify_underline(output_path)
    except Exception as e:  # noqa: BLE001
        logger.warning("폼 후처리 실패(_solidify_underline): %s", e)
    # 1.86단계: 줄기-잎 표 열너비 줄기:잎=1:3 강제(TableCreate 균등 재배분 보정, 기본
    # 경로와 동일). _com_relaunder **전**. relaunder(HWP 재저장)가 차등폭을 보존하는지는
    # 렌더로 검증해야 한다(HWP 가 load 시 명시 셀너비를 유지하면 통과).
    try:
        from core.hwp_com_writer import _fix_stemleaf_colwidth
        _fix_stemleaf_colwidth(output_path)
    except Exception as e:  # noqa: BLE001
        logger.warning("폼 후처리 실패(_fix_stemleaf_colwidth): %s", e)
    # 1.9단계: 서술형 끝 메타란 토큰 → [소단원][난이도] 주입(살아있는 MC 메타란 복제, 폼
    # 디자인 동일). _com_relaunder **전**에 해 HWP 가 재저장 때 linesegs 재계산하게 한다.
    try:
        _inject_essay_meta(output_path)
    except Exception as e:  # noqa: BLE001
        logger.warning("폼 후처리 실패(_inject_essay_meta): %s", e)
    # 2단계: 그림 렌더 모드면 그림 binItem 임베드(경고 감수). 아니면(기본) COM 재저장(launder)
    # 으로 '변조' 보안경고 제거 — 그림 자리엔 안내 박스(표라서 재저장에 보존).
    # 2.5단계: 정답 페이지 패리티 **최종 검증·교정**(_fix_answer_parity) — _layout_form 의
    # 짝수 보정은 그 뒤 후처리(보기 5×5 폼·메타란 주입)가 본문 높이를 키우면 어긋난다
    # (경구중·새본리중·월암중 정답 짝수쪽, 2026-06-12). relaunder **후** 측정해야 최종
    # 페이지네이션 기준이고, 교정(XML 수정) 시 relaunder 재실행으로 보안경고를 다시 없앤다.
    if render_figures and fig_paths:
        try:
            _embed_figures(output_path, fig_paths)
        except Exception as e:  # noqa: BLE001
            logger.warning("폼 후처리 실패(_embed_figures): %s", e)
        try:
            _fix_answer_parity(output_path)   # 그림 경로는 경고가 어차피 있어 재저장 불필요
        except Exception as e:  # noqa: BLE001
            logger.warning("폼 후처리 실패(_fix_answer_parity): %s", e)
    else:
        if not _com_relaunder(output_path):
            logger.warning("폼 후처리 실패(_com_relaunder): 보안경고 제거 재저장 실패")
        try:
            if _fix_answer_parity(output_path):
                if not _com_relaunder(output_path):
                    logger.warning("폼 후처리 실패(_com_relaunder): 패리티 교정 재저장 실패")
        except Exception as e:  # noqa: BLE001
            logger.warning("폼 후처리 실패(_fix_answer_parity): %s", e)
        # ⚠️ _inject_essay_meta 시점의 메타란 토큰 run 구조는 **비결정적**이다 — COM 저장이
        # 토큰("소단원자리표식QZX")을 한 run 에 두기도, 여러 run/t 로 쪼개기도 한다(고2 선택과목
        # 폼 중앙고에서 평문 노출, 2026-06-10). 쪼개지면 위 1.9단계 매치가 실패한다. relaunder
        # (HWP 재저장)가 토큰을 한 run 으로 정규화하므로, 그 뒤 **잔여 토큰을 재주입**하고 한 번
        # 더 relaunder 로 linesegs 를 재계산한다. 첫 시도에 성공했으면 토큰 0 → no-op(추가비용 없음).
        # 메타란 토큰 비결정 잔존 해소 — **relaunder 후 검사·처리 반복**. _inject_essay_meta
        # 시점의 토큰 run 은 비결정으로 쪼개져(여러 run/t) 매치 실패하고, relaunder 가 run=1 로
        # 정규화하며 평문 노출된다(효성중 4중 1회, 2026-06-12 — 1회 폴백으론 relaunder 가 다시
        # 쪼개면 놓침). 매 회: relaunder 후 토큰을 세고(이때 run=1 라 정확), 남으면 메타란
        # 재주입(채움) 또는 최후 비우기 + relaunder. 토큰 0 이면 relaunder 직후 상태라 경고도 없다.
        try:
            for _ in range(3):
                _need_meta = _count_meta_tokens(output_path) > 0
                # 라벨 혼용 잔존 — COM 저장이 라벨 run 을 비결정 쪼개면 sync 가 연속 문자열을
                # 못 잡고, relaunder 가 run 을 정규화해 온전한 ``[서술형`` 이 최종 XML 에
                # 남는다(대진고 공수1 정답면 4중 2회 — 메타토큰과 동일 메커니즘, 검사는
                # 반드시 relaunder **후**). 균일 시험지만(혼합은 renumber 가 문항별 처리).
                _need_lbl = (_words and len(set(_words)) == 1
                             and bool(_label_words_in_xml(output_path) - {_words[0]}))
                if not _need_meta and not _need_lbl:
                    break
                if _need_meta:
                    if _inject_essay_meta(output_path) == 0:   # run=1 인데도 못 채우면(템플릿 없음)
                        _strip_residual_meta_tokens(output_path)   # 텍스트 비움(평문 노출 0)
                if _need_lbl:
                    _sync_essay_label_word(output_path, _words[0])
                    _renumber_essay_labels(output_path, len(essays), words=_words, nums=_nums)
                _com_relaunder(output_path)                # 정규화 + 재저장(경고 제거)
        except Exception as e:  # noqa: BLE001
            logger.warning("폼 후처리 실패(메타 토큰/라벨 잔존 해소): %s", e)
    return output_path
