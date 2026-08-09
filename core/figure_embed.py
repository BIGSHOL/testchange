# -*- coding: utf-8 -*-
"""그림 자리 토큰 → **HWP 네이티브 그림 삽입**(안내문구 대신 진짜 그림).

왜 이 경로인가
    과거(2026-06-05) 폼 경로는 그림을 저장 후 HWPX XML 로 임베드했는데,
    보안경고를 없애려고 HWP 로 다시 열어 저장하면(`_com_relaunder`) **그 그림이
    통째로 드롭**됐다(메모리 `form-figure-pending`). 그래서 그림 렌더는 폐기되고
    "※ 그림 자리 —" 안내문구만 남았다.

    2026-07-24 부터 최종 산출물이 `.hwpx` 가 아니라 **`.hwp`(HWP 가 직접 저장)**
    이므로 판이 달라졌다. 실측(2026-08-09): 모든 후처리가 끝난 뒤 COM 으로 열어
    ``InsertPicture(Embedded=True)`` 하고 **`.hwp` 로 저장하면 그림이 살아남는다**
    (재오픈 시 gso 컨트롤 존재 확인). HWP 자신이 마지막 저장자라 변조 보안경고도
    없다.

사용법
    1) 본문 렌더 중 그림 자리에 `figure_token(i)` 텍스트를 남긴다.
    2) 레이아웃·XML 후처리·relaunder 를 **전부 끝낸 뒤** 이 모듈의
       `embed_figures_by_token(경로, {토큰: png})` 을 호출한다.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# 본문에 남기는 자리표시 토큰 — 일반 문서에 나올 수 없는 조합
TOKEN_FMT = "@@FIG{idx}@@"   # 본문에 나올 수 없는 ASCII 조합(⟦⟧ 는 HWP Find 실패)


def figure_token(idx: int) -> str:
    return TOKEN_FMT.format(idx=idx)


def _hwp(visible: bool = False):
    import win32com.client as wc

    h = wc.Dispatch("HWPFrame.HwpObject")
    try:
        h.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
    except Exception:  # noqa: BLE001 (보안모듈 미등록이어도 진행)
        pass
    try:
        h.XHwpWindows.Item(0).Visible = visible
    except Exception:  # noqa: BLE001
        pass
    return h


def _find(h, text: str) -> bool:
    """본문 처음부터 text 를 찾아 그 **뒤에 캐럿**을 놓는다.

    ⚠️ **`CreateAction("FindDlg") + SetItem` 방식은 이 문서들에서 동작하지 않는다**
    (실측 2026-08-09: Execute=False, GetPos 불변). 리포지토리에서 검증된 방식은
    `hwp_form_writer._repeat_find` 와 같은 **`HParameterSet.HFindReplace` +
    `RepeatFind`** 이고, 찾은 뒤 **`Run("Cancel")` 로 선택을 풀어야** 캐럿이
    확정된다(선택 상태에서 GetPos 하면 엉뚱한 값).
    """
    h.Run("MoveDocBegin")
    fp = h.HParameterSet.HFindReplace
    h.HAction.GetDefault("RepeatFind", fp.HSet)
    fp.FindString = text
    fp.IgnoreMessage = 1
    fp.Direction = 0
    if not h.HAction.Execute("RepeatFind", fp.HSet):
        return False
    return True


def embed_figures_by_token(doc_path: str | Path,
                           token_to_png: dict[str, str],
                           width_mm: float | None = None) -> int:
    """문서를 열어 각 토큰을 그림으로 바꾸고 `.hwp` 로 저장한다. 삽입 수 반환.

    ⚠️ 반드시 **모든 XML 후처리·relaunder 뒤**에 호출한다. 이 함수가 마지막
    저장자가 되어야 그림이 보존되고 보안경고도 나지 않는다.
    """
    doc_path = Path(doc_path).resolve()      # ⚠️ HWP Open 은 상대경로를 조용히 실패
    if not token_to_png:
        return 0
    if not doc_path.exists():
        raise FileNotFoundError(doc_path)

    fmt = "HWP" if doc_path.suffix.lower() == ".hwp" else "HWPX"
    h = _hwp()
    n = 0
    try:
        if not h.Open(str(doc_path), fmt, "forceopen:true"):
            raise RuntimeError(f"HWP Open 실패: {doc_path}")
        for token, png in token_to_png.items():
            png = str(Path(png).resolve())
            if not os.path.exists(png):
                logger.warning("그림 파일 없음 — 토큰만 제거: %s", png)
                if _find(h, token):
                    h.HAction.Run("Delete")
                continue
            if not _find(h, token):
                logger.warning("토큰을 문서에서 찾지 못함: %s", token)
                continue
            h.HAction.Run("Delete")          # 선택된 토큰 제거 → 캐럿이 그 자리
            try:
                # InsertPicture(경로, Embedded, sizeoption, reverse, watermark,
                #               effect, width, height) — sizeoption 2 = 원래 크기
                h.InsertPicture(png, True, 2, 0, 0, 0, 0, 0)
            except Exception:  # noqa: BLE001 (구버전 시그니처 폴백)
                h.InsertPicture(png, True, 2)
            n += 1
        # 최종 저장은 항상 .hwp — HWPX 로 저장하면 폼의 기존 binItem(머리말 배너)을
        # 재사용하는 HWP 버그로 그림 자리에 배너가 뜬다(2026-06-05 실측).
        out = doc_path if doc_path.suffix.lower() == ".hwp" else doc_path.with_suffix(".hwp")
        h.SaveAs(str(out), "HWP", "")
    finally:
        try:
            h.Quit()
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.3)                       # Quit 은 비동기 — 파일 핸들 해제 대기
    return n
