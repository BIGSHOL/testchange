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
_MINGAP = 1


# ── 저수준 COM 헬퍼 ───────────────────────────────────────
def _en_anchors(hwp) -> list[tuple[int, int, int]]:
    """본문 미주(en=문항번호) 앵커 위치 목록 (List, Para, Pos)."""
    out = []
    ctrl = hwp.HeadCtrl
    while ctrl is not None:
        if ctrl.CtrlID == "en":
            ap = ctrl.GetAnchorPos(0)
            out.append((ap.Item("List"), ap.Item("Para"), ap.Item("Pos")))
        ctrl = ctrl.Next
    return out


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


def _fill_essay_at(ses, h, pos, q: Question, label_idx: int) -> None:
    """서술형 슬롯 채움: 번호줄 ``[라벨 M] 문제`` + 소문항((k) 수식 마커) + 배점.

    label_idx 는 서술형 일련번호(서답형 1, 2, …; 전체 문항번호와 별개).
    번호줄의 ``[서술형 ]`` 플레이스홀더는 삭제 후 다시 쓴다.
    """
    label = q.label_type or "서답형"
    h.SetPos(pos[0], pos[1], pos[2])
    h.Run("MoveRight")                       # 번호(미주) 다음
    # 슬롯 템플릿: 번호줄 [서술형] + 빈줄 + 둘째 [서술형] 까지 선택 삭제([중단원] 전까지).
    h.Run("MoveSelParaEnd")                   # 번호 단락 끝(첫 [서술형])
    h.Run("MoveSelDown")                      # 빈 단락으로
    h.Run("MoveSelDown")                      # 둘째 [서술형] 단락으로
    h.Run("MoveSelParaEnd")                   # 둘째 [서술형] 단락 끝
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
            ses.break_para()                  # 답안 공간 한 줄
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
        n_mc = min(n_mc, mc_form)     # TODO: 초과 시 슬롯 복사
        n_es = min(n_es, es_form)

        # (1) 잉여 서술형 슬롯 삭제(뒤). 그 다음 잉여 객관식 슬롯 삭제(중간).
        anc = _en_anchors(h)
        if mc_form + n_es < len(anc):
            h.Run("MoveDocEnd")
            end = h.GetPos()
            s0 = anc[mc_form + n_es]
            h.SelectText(s0[1], s0[2], end[1], end[2])
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
            _fill_essay_at(ses, h, qpts[n_mc + i], essays[i], i + 1)
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


def _build_layout(src_hwpx, out_hwpx, slot_blanks: dict, per_col: int) -> None:
    """src 의 채운 내용을 바탕으로: 폼 빈줄 제거 + 슬롯별 빈줄 삽입 + columnBreak.

    위치기반 편집만 사용(재조립 금지). endNote/표/수식을 마스킹해 바깥 단락만 다룬다.
    """
    shutil.copy(src_hwpx, out_hwpx)
    with zipfile.ZipFile(out_hwpx) as z:
        infos = z.infolist()
        data = {i.filename: z.read(i.filename) for i in infos}
    name = next(n for n in data if n.endswith("section0.xml"))
    sec = data[name].decode("utf-8")
    # 폼 잔존 단/쪽 나누기 전부 리셋(내가 의도한 것만 다시 설정).
    sec = sec.replace('columnBreak="1"', 'columnBreak="0"').replace('pageBreak="1"', 'pageBreak="0"')

    # 마스킹: endNote/table/equation → 플레이스홀더(중첩 단락 안전).
    store: list[str] = []

    def _mask(pat):
        nonlocal sec

        def _r(m):
            store.append(m.group(0))
            return f"@@X{len(store) - 1}@@"

        sec = re.sub(pat, _r, sec, flags=re.S)

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

    # (1) 폼 과잉 빈줄 전부 삭제(첫 슬롯 이후의 빈 바깥단락). 완전 span, 뒤→앞.
    first = _slot_opens(sec, en_phs)[0]
    empties = [
        (m.start(), m.end())
        for m in _PARA.finditer(sec)
        if m.start() >= first and is_empty(m.group(0))
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

    # (3) columnBreak: 각 단 첫 슬롯의 바깥 단락에. 뒤→앞.
    boundaries = [g * per_col for g in range(1, (N + per_col - 1) // per_col)]
    for b in sorted(boundaries, reverse=True):
        ops = _slot_opens(sec, en_phs)
        s0 = ops[b]
        e0 = sec.find(">", s0)
        sec = sec[:s0] + re.sub(r'columnBreak="\d"', 'columnBreak="1"', sec[s0:e0 + 1]) + sec[e0 + 1:]

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


def _layout_form(filled_hwpx, out_hwpx, per_col: int, n: int) -> None:
    """채운 hwpx → (tight 측정 → 행정렬 빈줄 계산 → 최종) 레이아웃."""
    tight = str(Path(out_hwpx).with_suffix("")) + "_tight.hwpx"
    # tight: 빈줄 최소(측정용). columnBreak 포함.
    _build_layout(filled_hwpx, tight, {i: _MINGAP for i in range(n)}, per_col)
    pos = _measure_first_choice_lines(tight, n)
    try:
        os.remove(tight)
    except Exception:
        pass
    if len(pos) < n:
        # 측정 실패 시 균일 폴백(문제 이후 4줄).
        blanks = {i: 4 for i in range(n)}
    else:
        blanks = _row_align_blanks(pos, n, per_col)
    _build_layout(filled_hwpx, out_hwpx, blanks, per_col)


# ── 진입점 ────────────────────────────────────────────────
def write_exam_to_form(
    document: ExamDocument,
    form_path: str | Path,
    output_path: str | Path,
    per_col: int = PER_COL,
) -> Path:
    """ExamDocument 를 대수회 폼(.hwp)에 채워 .hwpx 로 저장.

    Args:
        document: 변환할 시험 문서.
        form_path: 폼 양식(.hwp) 경로.
        output_path: 출력 .hwpx 경로.
        per_col: 한 단당 문항 수(기본 3 → 페이지당 6).

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
        if n_es == 0:
            # 객관식만 → 행정렬 레이아웃.
            _layout_form(filled, output_path, per_col, n_mc)
        else:
            # 서술형 포함 → 현재는 폼 자연 흐름 유지(객관식+서술형 혼합 레이아웃은 후속).
            shutil.copy(filled, output_path)
    finally:
        try:
            os.remove(filled)
        except Exception:
            pass
    return output_path
