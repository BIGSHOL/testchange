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

import math
import os
import re
import shutil
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path

from .hwp_com import HwpSession, _dispatch_hwp, _win32
from .latex_to_hwpeq import latex_to_hwpeq
from models.exam_document import ContentType, ExamDocument, Question

# ── 설정 ──────────────────────────────────────────────────
PER_COL = 3          # 한 단에 들어갈 문항 수(최대) — 페이지당 2단 = 6문항
CAP = 46             # 한 단의 줄 용량(채움 목표; 실측 ~42 + 헤더 오프셋 여유)
LONG_CHOICE_LEN = 15 # 짝 보기(①②③④) 최대 길이 ≥ 이 값이면 1열 배치
CHARS_PER_LINE = 18  # 줄 수 추정용(현재 미사용 — 측정값 우선)
CIRCLES = ["①", "②", "③", "④", "⑤"]
ESSAY_SUB_BLANKS = 3   # 서술형 소문항마다 답안 공간(빈 줄 수)
_MINGAP = 1


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


def _set_plain(hwp) -> None:
    """캐럿 글자모양 볼드 해제(+장평/상대크기 100). 미주 볼드 상속 차단."""
    cs = hwp.HParameterSet.HCharShape
    hwp.HAction.GetDefault("CharShape", cs.HSet)
    try:
        cs.Bold = 0
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
    """ContentBlock 하나를 현재 캐럿에 삽입(수식/텍스트)."""
    if b.type in (ContentType.EQUATION, ContentType.EQUATION_BLOCK):
        ses.equation(_eq_script(b))  # 숫자도 수식 객체로 유지(정렬)
    elif b.type == ContentType.TEXT:
        if b.value:
            ses.text(b.value)


def _put_score(ses, h, score: int) -> bool:
    """배점 ``[N점]`` 삽입. 단독으로 다음 줄로 넘어가면 줄바꿈 후 우측정렬.

    Returns: 우측정렬 단락으로 넘겼으면 True(현재 단락이 우측정렬 상태).
    """
    def line():
        try:
            return h.KeyIndicator()[5]
        except Exception:
            return -1

    sp = h.GetPos()
    la = line()
    ses.text(f" [{score}점]")
    lb = line()
    if la >= 0 and lb > la:
        h.SetPos(sp[0], sp[1], sp[2])
        h.Run("MoveSelParaEnd")
        h.HAction.Run("Delete")
        h.Run("BreakPara")
        h.Run("ParagraphShapeAlignRight")
        _set_plain(h)
        ses.text(f"[{score}점]")
        return True
    return False


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
    for b in q.contents:
        _put_block(ses, b)
    if q.sub_questions:
        for k, sub in enumerate(q.sub_questions):
            ses.break_para()
            h.Run("ParagraphShapeAlignLeft")  # 직전 배점이 우측정렬됐어도 새 줄은 좌측
            _set_plain(h)
            ses.equation(f"({k + 1})")        # 소문항 마커 (1)(2)… 는 수식으로
            ses.text(" ")
            for b in sub.contents:
                _put_block(ses, b)
            if sub.score:
                _put_score(ses, h, sub.score)  # 배점 줄넘침 시 우측정렬
            for _ in range(ESSAY_SUB_BLANKS):  # 소문항 답안 공간(2~3줄)
                ses.break_para()
                h.Run("ParagraphShapeAlignLeft")
    elif q.score:
        _put_score(ses, h, q.score)


def _choice_len(choice) -> int:
    return sum(len(b.value or "") for b in choice.contents)


def _is_long_choices(q: Question) -> bool:
    """2열로 짝짓는 ①②③④ 중 하나라도 길면 1열 배치(⑤는 3행에 홀로)."""
    paired = sorted(q.choices, key=lambda c: c.number)[:4]
    return any(_choice_len(c) >= LONG_CHOICE_LEN for c in paired)


# ── 1단계: COM 채움 ───────────────────────────────────────
def _fill_form(mc: list[Question], essays: list[Question], form_path, out_path) -> tuple[int, int]:
    """폼을 열어 슬롯 수 조절 + 객관식/서술형 채움 → out_path 저장.

    폼은 앞쪽 객관식 슬롯(①②③④⑤ 사전배치) + 뒤쪽 서술형 슬롯([서술형]). 잉여 객관식
    슬롯만 삭제하면 미주 자동번호로 **서술형 번호가 객관식 다음으로 이어진다**.

    Returns: (채운 객관식 수, 채운 서술형 수).
    """
    n_mc, n_es = len(mc), len(essays)
    with HwpSession(visible=False) as ses:
        h = ses.hwp
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
            for b in q.contents:
                _put_block(ses, b)
            if q.score:
                _put_score(ses, h, q.score)   # 배점 줄넘침 시 우측정렬

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
    return n_mc, n_es


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


def _row_align_blanks(pos: list[tuple[int, int, int]], n: int, per_col: int) -> dict:
    """측정한 ① 위치로 슬롯 높이·단 시작을 구해 행정렬 빈줄을 계산.

    같은 행(1단·2단의 같은 순번)의 문항이 같은 절대 줄에서 시작하도록:
      - 행 높이 ROWH = CAP // per_col
      - 첫 행: (최대단시작 + ROWH) - 자기단시작 - 높이  (열 시작 오프셋 보정)
      - 이후 행: ROWH - 높이
      - 단 마지막 슬롯: 0 (단나누기로 다음 단)
    """
    rowh = CAP // per_col
    colmap = defaultdict(list)
    for i, (pg, col, ln) in enumerate(pos):
        colmap[(pg, col)].append((i, ln))
    # 슬롯 높이 = 같은 (page,col) 내 ① 줄차이. 마지막 슬롯은 같은 단 평균으로 추정.
    heights = {}
    for _, lst in colmap.items():
        lst.sort(key=lambda x: x[1])
        for j, (i, ln) in enumerate(lst):
            if j + 1 < len(lst):
                heights[i] = lst[j + 1][1] - ln
            else:
                diffs = [lst[k + 1][1] - lst[k][1] for k in range(len(lst) - 1)]
                heights[i] = int(sum(diffs) / len(diffs)) if diffs else rowh

    groups = [list(range(g * per_col, min(g * per_col + per_col, n)))
              for g in range((n + per_col - 1) // per_col)]
    starts = {gi: pos[g[0]][2] for gi, g in enumerate(groups) if g}
    maxstart = max(starts.values()) if starts else 0

    blanks = {}
    for gi, g in enumerate(groups):
        s = starts.get(gi, 0)
        for r, i in enumerate(g):
            if r == len(g) - 1:                       # 단 마지막 → 0(단나누기)
                blanks[i] = 0
            elif r == 0:                              # 첫 행: 단 시작 오프셋 보정
                blanks[i] = max(_MINGAP, (maxstart + rowh) - s - heights.get(i, rowh))
            else:                                      # 이후 행: ROWH 간격
                blanks[i] = max(_MINGAP, rowh - heights.get(i, rowh))
    return blanks


def _layout_form(filled_hwpx, out_hwpx, per_col: int, n_mc: int, n_es: int) -> None:
    """채운 hwpx → 혼합 레이아웃. 객관식: 측정 기반 행정렬(per_col/단). 서술형: 1/단.

    객관식과 서술형은 폼의 별도 구역(섹션)이라 서술형은 새 페이지에서 시작한다.
    columnBreak: 객관식은 per_col 마다, 서술형은 매 문항(첫 서술형 제외).
    """
    n = n_mc + n_es
    colbreak = set(range(per_col, n_mc, per_col))     # 객관식 단나누기(per_col마다)
    colbreak |= set(range(n_mc, n))                   # 서술형 1/단(매 문항이 새 단)

    tight = str(Path(out_hwpx).with_suffix("")) + "_tight.hwpx"
    _build_layout(filled_hwpx, tight, {i: _MINGAP for i in range(n)}, colbreak, n_mc)
    pos = _measure_first_choice_lines(tight, n_mc) if n_mc else []
    try:
        os.remove(tight)
    except Exception:
        pass

    blanks = {}
    if n_mc:
        if len(pos) >= n_mc:
            blanks.update(_row_align_blanks(pos, n_mc, per_col))
        else:
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
        (re.compile(r'(?:중|고)\s*\d{2,4}\s*년\s*학기\s*고사\s*대비\s*\(\s*수학[12]?\s*\)(\s*\(\s*정답\s*\))?'),
         lambda mm: footer + (mm.group(1) or "")),
        (re.compile(r'(?:중|고)\s*[1-3]\s*학년\s*수학[12]?'), lambda mm: center),
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


def write_exam_to_form(
    document: ExamDocument,
    form_path: str | Path,
    output_path: str | Path,
    per_col: int = PER_COL,
    header_values: dict | None = None,
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
        n_mc, n_es = _fill_form(mc, essays, form_path, filled)
        # 혼합 레이아웃(객관식 행정렬 + 서술형 1/단).
        _layout_form(filled, output_path, per_col, n_mc, n_es)
    finally:
        try:
            os.remove(filled)
        except Exception:
            pass
    # 2단계: 머리말/꼬리말 학년·과목·시기 채움(결정적 XML 후처리).
    if header_values:
        try:
            _fill_form_header(output_path, header_values)
        except Exception:
            pass
    return output_path
