# -*- coding: utf-8 -*-
"""HWP COM 자동화 저수준 래퍼.

한글(HWP)을 COM으로 구동해 텍스트·수식·표를 직접 입력한다.
수식 크기는 HWP가 네이티브로 계산하므로 우리는 일절 추정하지 않는다.

핵심 기법(세션에서 실측 검증, [[hwp-com-pivot]] 참고):
- ``SetMessageBoxMode(0xFFFFFF)``: 복구/저장 등 모든 대화상자를 자동응답.
  누락 시 '문서 복구' 팝업으로 COM이 무한 대기(hang)한다. **필수**.
- 인라인 수식: ``EquationCreate`` 실행 후 ``Close`` → ``FindCtrl`` →
  ``ShapeObjTreatAsChar`` 로 '글자처럼 취급' 적용. (ShapeObjDialog는 모달이라 hang.)
- 표 탈출: 셀을 다 채운 뒤 ``Close`` → ``MoveRight`` 로 표 뒤 단락으로 이동.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

# COM 디스패치는 런타임에만 필요(테스트/비-Windows 환경에서 import 실패 방지).
try:
    import win32com.client as _win32  # type: ignore
except Exception:  # pragma: no cover - 비-Windows
    _win32 = None


HWP_PROGID = "HWPFrame.HwpObject"

# 보기 동그라미 숫자 ①②③④⑤ … (U+2460~)
CIRCLE_NUMBERS = {i: chr(0x245F + i) for i in range(1, 16)}


def _dispatch_hwp():
    """HWP COM 객체를 생성한다.

    PyInstaller로 동결(frozen)된 exe에서는 ``gencache.EnsureDispatch`` 의
    gen_py 캐시 생성이 실패할 수 있으므로, 실패 시 late-binding
    ``Dispatch`` 로 폴백한다. HWP API(HAction/HParameterSet 등)는 모두
    IDispatch 속성이라 late-binding 으로도 정상 동작한다.
    """
    try:
        return _win32.gencache.EnsureDispatch(HWP_PROGID)
    except Exception:
        return _win32.Dispatch(HWP_PROGID)


def is_hwp_available() -> bool:
    """HWP COM 디스패치가 가능한지(=한글 설치 여부) 탐지한다."""
    if _win32 is None:
        return False
    try:
        hwp = _dispatch_hwp()
    except Exception:
        return False
    try:
        hwp.Quit()
    except Exception:
        pass
    return True


class HwpSession:
    """HWP COM 세션 컨텍스트 매니저.

    사용::

        with HwpSession() as s:
            s.text("값 ")
            s.equation("x ^{2}")
            s.save_hwpx("out.hwpx")

    ``__exit__`` 에서 항상 ``Quit`` 을 보장해 고아 Hwp.exe 프로세스를 막는다.
    """

    def __init__(self, visible: bool = False, base_pt: int = 10, eq_pt: int = 11):
        if _win32 is None:
            raise RuntimeError("win32com을 사용할 수 없습니다 (HWP COM 미지원 환경).")
        self.base_pt = base_pt   # 본문 텍스트(한글 등) 글자 크기(pt)
        self.eq_pt = eq_pt       # 수식 글자 크기(pt)
        self.hwp = _dispatch_hwp()
        # 모든 대화상자 자동응답 — 복구/저장 팝업 hang 방지(필수).
        try:
            self.hwp.SetMessageBoxMode(0xFFFFFF)
        except Exception:
            pass
        # 파일 입출력 보안 모듈 등록 — Open/SaveAs 시 보안 팝업 방지.
        try:
            self.hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
        except Exception:
            pass
        try:
            self.hwp.XHwpWindows.Item(0).Visible = visible
        except Exception:
            pass

    def __enter__(self) -> "HwpSession":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.quit()

    # ── 문서 단위 ──────────────────────────────────────────
    def open(self, path: str | Path) -> None:
        """기존 문서(템플릿)를 연다."""
        path = str(Path(path))
        ext = os.path.splitext(path)[1].lower().lstrip(".")
        fmt = "HWPX" if ext == "hwpx" else "HWP"
        self.hwp.Open(path, fmt, "")

    def move_doc_begin(self) -> None:
        """커서를 문서 맨 앞으로 이동."""
        self.hwp.HAction.Run("MoveDocBegin")

    def set_char_size(self, pt: int) -> None:
        """이후 입력될 텍스트의 글자 크기(pt)를 고정한다.

        선택 영역이 없으면 캐럿 위치의 글자모양에 적용되어 이후 입력에 반영된다.
        """
        h = self.hwp
        h.HAction.GetDefault("CharShape", h.HParameterSet.HCharShape.HSet)
        h.HParameterSet.HCharShape.Height = h.PointToHwpUnit(pt)
        h.HAction.Execute("CharShape", h.HParameterSet.HCharShape.HSet)

    def force_layout(self) -> None:
        """전체 문서 레이아웃을 일괄 계산하도록 강제한다.

        숨김 창에서는 레이아웃이 지연되어 첫 저장이 비정상적으로 느려진다(또는 멈춤).
        반대로 창을 계속 보이게 두면 수식 삽입(수식편집기 렌더)마다 빌드가 느려진다.
        따라서 빌드는 숨김(빠름)으로 하고, 저장 직전에만 창을 띄워 문서 끝까지
        스크롤해 전체 레이아웃을 일괄 계산시킨다 → 저장이 빨라진다.
        """
        try:
            self.hwp.XHwpWindows.Item(0).Visible = True
        except Exception:
            pass
        for act in ("RecalcPageCount", "ScrollDocEnd", "MoveDocBegin"):
            try:
                self.hwp.HAction.Run(act)
            except Exception:
                pass

    def save_hwpx(self, path: str | Path) -> Path:
        path = Path(path)
        if path.exists():
            try:
                path.unlink()
            except Exception:
                pass
        self.force_layout()
        self.hwp.SaveAs(str(path), "HWPX", "")
        return path

    def save_pdf(self, path: str | Path) -> Path:
        """렌더 검증용 PDF 내보내기."""
        path = Path(path)
        if path.exists():
            try:
                path.unlink()
            except Exception:
                pass
        self.hwp.SaveAs(str(path), "PDF", "")
        return path

    def quit(self) -> None:
        if getattr(self, "hwp", None) is None:
            return
        try:
            self.hwp.Quit()
        except Exception:
            pass
        finally:
            self.hwp = None

    # ── 저수준 입력 헬퍼 ───────────────────────────────────
    def text(self, s: str) -> None:
        """본문에 텍스트 삽입."""
        if not s:
            return
        h = self.hwp
        h.HAction.GetDefault("InsertText", h.HParameterSet.HInsertText.HSet)
        h.HParameterSet.HInsertText.Text = s
        h.HAction.Execute("InsertText", h.HParameterSet.HInsertText.HSet)

    def underline_run(self, s: str) -> None:
        """밑줄이 적용된 텍스트 run 삽입(앞뒤로 밑줄 토글)."""
        if not s:
            return
        h = self.hwp
        h.HAction.Run("CharShapeUnderline")
        self.text(s)
        h.HAction.Run("CharShapeUnderline")

    def equation(self, script: str) -> None:
        """HWP 수식 스크립트를 인라인(글자처럼 취급)으로 삽입.

        크기는 HWP가 네이티브로 계산한다.
        """
        if not script:
            return
        h = self.hwp
        h.HAction.GetDefault("EquationCreate", h.HParameterSet.HEqEdit.HSet)
        h.HParameterSet.HEqEdit.string = script
        h.HParameterSet.HEqEdit.BaseUnit = h.PointToHwpUnit(self.eq_pt)
        h.HAction.Execute("EquationCreate", h.HParameterSet.HEqEdit.HSet)
        h.HAction.Run("Close")            # 수식편집기 닫고 본문 복귀(객체 선택 상태)
        h.FindCtrl()                      # 방금 삽입한 수식 컨트롤 선택
        h.HAction.Run("ShapeObjTreatAsChar")  # 글자처럼 취급 → 인라인
        h.HAction.Run("Cancel")           # 선택 해제
        h.HAction.Run("MoveRight")        # 수식 객체 뒤로 커서 이동

    def break_para(self) -> None:
        """단락 나누기(새 줄)."""
        self.hwp.HAction.Run("BreakPara")

    def align_center(self) -> None:
        """현재 단락 가운데 정렬."""
        self.hwp.HAction.Run("ParagraphShapeAlignCenter")

    def align_left(self) -> None:
        """현재 단락 왼쪽 정렬."""
        self.hwp.HAction.Run("ParagraphShapeAlignLeft")

    def align_right(self) -> None:
        """현재 단락 오른쪽 정렬."""
        self.hwp.HAction.Run("ParagraphShapeAlignRight")

    def table(self, rows: list[list[str]], line_width: int = 8000) -> None:
        """문자열 2D 배열로 표를 만들고 채운다.

        rows: 행 우선(row-major) 문자열 배열. 셀은 텍스트만 지원.
        """
        if not rows:
            return
        h = self.hwp
        nrow = len(rows)
        ncol = max(len(r) for r in rows)

        h.HAction.GetDefault("TableCreate", h.HParameterSet.HTableCreation.HSet)
        ps = h.HParameterSet.HTableCreation
        ps.Rows = nrow
        ps.Cols = ncol
        ps.WidthType = 0
        ps.HeightType = 0
        col_w = max(int(line_width // ncol), 1)
        ps.CreateItemArray("ColWidth", ncol)
        for c in range(ncol):
            ps.ColWidth.SetItem(c, col_w)
        ps.CreateItemArray("RowHeight", nrow)
        for r in range(nrow):
            ps.RowHeight.SetItem(r, 1000)
        h.HAction.Execute("TableCreate", ps.HSet)

        # 셀 채우기 — 생성 직후 커서는 (0,0) 셀.
        for ri in range(nrow):
            row = rows[ri]
            for ci in range(ncol):
                val = row[ci] if ci < len(row) else ""
                self.text(str(val))
                if not (ri == nrow - 1 and ci == ncol - 1):
                    h.HAction.Run("TableRightCell")

        # 표 밖(뒤 단락)으로 탈출 — 실측으로 확정된 시퀀스.
        h.HAction.Run("Close")
        h.HAction.Run("MoveRight")
