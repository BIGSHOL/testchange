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

import logging
import os
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# COM 디스패치는 런타임에만 필요(테스트/비-Windows 환경에서 import 실패 방지).
try:
    import win32com.client as _win32  # type: ignore
except Exception:  # pragma: no cover - 비-Windows
    _win32 = None


HWP_PROGID = "HWPFrame.HwpObject"

# 변환 중 한글 창 표시 여부.
# ⚠️ **False 가 안전 기본값**(2026-06-08 사용자 데이터손상 버그로 되돌림): COM Dispatch 는
# 이미 떠 있는 한글 프로세스에 **붙어** 변환 문서를 그 앱의 한 문서로 연다. 창을 보이게(True)
# 두면 변환 중 사용자가 **다른 한글 문서로 포커스**를 옮길 때 COM 작성(HAction)이 그
# **포커스된 사용자 문서에 타이핑**돼 원본을 훼손한다(2개 파일 열림 시 보고). 또 실시간
# 렌더로 느려진다. → 숨김(False)으로 작성 과정을 사용자 포커스와 분리한다.
# (실시간 작성 모습을 보고 싶으면 True 로 하되, 변환 중 다른 한글 파일을 열지 말 것.)
CONVERSION_VISIBLE = False

# 보기 동그라미 숫자 ①②③④⑤ … (U+2460~)
CIRCLE_NUMBERS = {i: chr(0x245F + i) for i in range(1, 16)}

# HWP '파일 접근 허용' 보안 팝업 억제용 승인 모듈 DLL.
_SECURITY_DLL = "FilePathCheckerModuleExample.dll"


def _resolve_security_dll() -> Optional[str]:
    """번들된 보안 승인 모듈 DLL 경로를 찾는다(frozen=_internal/resources, dev=resources)."""
    cands = []
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        exedir = os.path.dirname(sys.executable)
        cands += [
            os.path.join(base, "resources", _SECURITY_DLL),
            os.path.join(base, _SECURITY_DLL),
            os.path.join(exedir, "_internal", "resources", _SECURITY_DLL),
            os.path.join(exedir, "resources", _SECURITY_DLL),
        ]
    here = os.path.dirname(os.path.abspath(__file__))
    cands.append(os.path.join(here, "..", "resources", _SECURITY_DLL))
    for c in cands:
        c = os.path.abspath(c)
        if os.path.exists(c):
            return c
    return None


def _register_security_module() -> bool:
    """HWP 파일접근 보안 승인 모듈을 레지스트리에 등록한다.

    ``HKCU\\Software\\HNC\\HwpAutomation\\Modules\\FilePathCheckerModule = <DLL 경로>`` 로
    등록돼 있어야 ``RegisterModule('FilePathCheckDLL', 'FilePathCheckerModule')`` 가
    바인딩돼 '파일 접근 허용' 보안 팝업이 뜨지 않는다(2026-06-05, 사용자 보고).
    번들 DLL 의 현재 경로로 매 실행 갱신(앱 이동 대비). 실패해도 변환은 계속(팝업만 남음).
    """
    dll = _resolve_security_dll()
    if not dll:
        return False
    try:
        import winreg
        with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER,
                r"Software\HNC\HwpAutomation\Modules", 0,
                winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
            try:
                cur, _ = winreg.QueryValueEx(k, "FilePathCheckerModule")
            except FileNotFoundError:
                cur = None
            if cur != dll:
                winreg.SetValueEx(k, "FilePathCheckerModule", 0, winreg.REG_SZ, dll)
        return True
    except Exception:
        return False


def ensure_com_initialized() -> None:
    """현재 스레드 COM 초기화 보장(idempotent) — frozen 커넥터 워커 방어.

    배포 agent.exe 워커(convert_cli 인프로세스 렌더)에서 폼 채움이 HWP 서버
    크래시(-2147417851)로 실패한 뒤, 기본 서식 폴백의 Dispatch 가
    'CoInitialize가 호출되지 않았습니다'(-2147221008)로 죽었다(2026-08-10,
    경상여고 기하 — **웹 변환을 처음 해보는 PC**). ⚠️ 그 PC 에서 스레드
    refcount 가 어쩌다 0 이 됐는지는 **원인 미확정**이다(레포의 CoUninitialize 는
    `_measure_*` 두 곳뿐이고 짝이 맞는다 — 적대리뷰 2026-08-10 반증). 확정된
    것은 "Dispatch 시점에 미초기화 상태면 저 오류가 난다"는 재현
    (`.testkit/_coinit_repro.py`)뿐이므로, pythoncom 의 import 자동 초기화에
    기대지 말고 Dispatch 직전마다 명시 초기화해 원인과 무관하게 막는다.
    이미 초기화된 스레드에선 S_FALSE(무해)이고, 일부러 CoUninitialize 짝을
    안 맞춰 refcount 를 1 이상으로 남긴다. 선초기화 모델이 다르면
    (RPC_E_CHANGED_MODE) 그대로 진행 — Dispatch 는 동작한다.
    """
    try:
        import pythoncom
        pythoncom.CoInitialize()
    except Exception as e:   # noqa: BLE001 — 이미 초기화/모델 불일치면 그대로 진행
        # 진짜 초기화 실패(E_OUTOFMEMORY 등)는 직후 Dispatch 가 -2147221008 로
        # 죽으며 단서를 잃는다 → 흔적만 남긴다(흐름은 막지 않음).
        logger.debug("CoInitialize 실패(무시): %r", e)


def hwp_pids() -> set:
    """현재 실행 중인 Hwp.exe PID 집합. 조회 실패하면 빈 집합(정리를 건너뛴다).

    ⚠️ **이미지명을 반드시 대조**한다 — tasklist 필터가 안 먹거나(로케일·미지원 옵션)
    빈 결과 안내문이 오면 엉뚱한 행에서 PID 를 뽑게 되고, 그걸 `reap_hwp` 가 강제
    종료한다(적대리뷰 2026-08-10).
    """
    import csv
    import io
    import subprocess
    pids = set()
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Hwp.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=10).stdout or ""
    except Exception:   # noqa: BLE001
        return pids
    for row in csv.reader(io.StringIO(out)):
        if len(row) >= 2 and row[0].strip().lower() == "hwp.exe":
            try:
                pids.add(int(row[1]))
            except ValueError:
                pass
    return pids


def reap_hwp(pids) -> int:
    """지정 PID 의 Hwp.exe 를 강제 종료하고 **실제로 종료된** 개수를 반환한다.

    ⚠️ **이번 작업이 띄운 PID 만** 넘길 것(작업 전후 `hwp_pids()` 차집합). 전체
    taskkill 은 사용자가 열어 둔 문서를 죽인다 — 절대 금지(커넥터 `_reap` 과 같은 규칙).

    쓰는 이유: COM 호출 중 HWP 가 죽으면(-2147417851 RPC_E_SERVERFAULT) 그 인스턴스가
    고아로 남아 **이어지는 렌더까지 오염**한다(저장·Quit 실패 → .hwp 굽기 실패).

    ⚠️ 반환값은 `taskkill` **종료코드 0** 인 것만 센다 — 접근거부·이미 종료를 성공으로
    세면 "N개 정리" 로그가 하지도 않은 청소를 주장해, 정작 남은 고아를 가린다.
    """
    import subprocess
    n = 0
    for pid in pids:
        try:
            r = subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                               capture_output=True, timeout=10)
            if r.returncode == 0:
                n += 1
        except Exception:   # noqa: BLE001
            pass
    return n


def _dispatch_hwp():
    """HWP COM 객체를 생성한다 — **late-binding(dynamic.Dispatch) 우선**.

    HWP API(HAction/HParameterSet/HSet/SetItem 등)는 전부 IDispatch 라 late-binding 으로
    완전 동작하고, 이 모듈은 win32com constants 를 안 쓴다(grep 검증 2026-06-24). 배포 .exe
    (frozen)도 이미 late-binding 으로 가동 중.

    과거 early-binding(``gencache.EnsureDispatch``)은 일부 HWP 버전에서 gen_py 재생성 시
    ``HParameterSet.HHeaderFooter`` 의 ``Type`` 등 동적 멤버가 빠진 *불완전 래퍼*를 반환해
    ``header_begin`` 이 "object has no attribute 'Type'" 로 깨지는 간헐 실패의 근본 원인이었다
    (§39-0/§40-4 COM flakiness — 2026-06-24 실측 확정: 캐시 정리 후 makepy 재생성해도
    HHeaderFooter 에 Type/Item/SetItem 모두 없음). late-binding 은 DISPID 런타임 해석이라
    캐시 손상과 무관하고 강건하다. ``win32com.client.Dispatch`` 는 gen_py 존재 시 early-binding
    을 돌려줄 수 있어, *강제 late* 인 ``dynamic.Dispatch`` 를 쓴다.
    """
    ensure_com_initialized()
    return _win32.dynamic.Dispatch(HWP_PROGID)


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


def save_as_hwp(hwpx_path: str | Path, hwp_path: str | Path) -> bool:
    """후처리 끝난 .hwpx 를 HWP COM 으로 열어 **최종 .hwp 로 굽는다**.

    ⭐ 대수회 폼의 2단 가운데 세로 구분선은 **바탕쪽(masterpage0.xml)의 단 구분선**이다
    (폼 7종·레퍼런스 워드본 전부 `colPr colCount=2` + `colLine SOLID 0.12mm`). 그런데
    **HWP 는 .hwpx 를 열 때 바탕쪽을 그리지 않는다** — 레퍼런스 `[다사중](워드).hwp` 를
    .hwpx 로 변환해 렌더하면 선이 사라지는 것으로 확정(2026-07-24). 과거(2026-07-13)엔 본문
    구역 colPr 에 `<hp:colLine>` 을 주입해 메웠는데 그건 **다단 설정의 구분선**이라 내용
    높이까지만 그려져 레퍼런스(바닥까지)와 다르다(사용자 지적) → 주입 폐기, 최종을 .hwp 로
    저장해 폼 바탕쪽 선을 그대로 살린다. XML 후처리는 압축포맷인 .hwpx 에서만 가능하므로
    **중간은 .hwpx, 최종만 .hwp**.

    HWP 가 직접 저장하므로 `_com_relaunder` 와 같은 효과(변조 보안경고 없음).
    실패해도 .hwpx 는 유효하니 변환을 중단하지 않는다. Returns: 성공 여부.
    """
    hwpx_path, hwp_path = Path(hwpx_path).resolve(), Path(hwp_path).resolve()
    try:
        with HwpSession(visible=CONVERSION_VISIBLE) as ses:
            ses.open(hwpx_path)
            ses.save_hwp(hwp_path)
        return hwp_path.exists()
    except Exception:  # noqa: BLE001
        return False


class HwpSession:
    """HWP COM 세션 컨텍스트 매니저.

    사용::

        with HwpSession() as s:
            s.text("값 ")
            s.equation("x ^{2}")
            s.save_hwpx("out.hwpx")

    ``__exit__`` 에서 항상 ``Quit`` 을 보장해 고아 Hwp.exe 프로세스를 막는다.
    """

    def __init__(self, visible: bool = False, base_pt: int = 11, eq_pt: int = 11,
                 eq_font: str = "HYhwpEQ", note_pt: int = 12):
        if _win32 is None:
            raise RuntimeError("win32com을 사용할 수 없습니다 (HWP COM 미지원 환경).")
        self.base_pt = base_pt   # 본문 텍스트(한글 등) 글자 크기(pt)
        self.eq_pt = eq_pt       # 수식 글자 크기(pt)
        self.note_pt = note_pt   # 문항번호(미주 자동번호) 글자 크기(pt) — 폼 스타일
        self.eq_font = eq_font   # 수식 글꼴 — HYhwpEQ 고정(편집기 직접입력과 동일)
        self.hwp = _dispatch_hwp()
        # 모든 대화상자 자동응답 — 복구/저장 팝업 hang 방지(필수).
        try:
            self.hwp.SetMessageBoxMode(0xFFFFFF)
        except Exception:
            pass
        # 파일 입출력 보안 모듈 등록 — Open/SaveAs 시 '파일 접근 허용' 보안 팝업 방지.
        # 먼저 번들 DLL 을 레지스트리에 등록해야 RegisterModule 이 바인딩된다(미등록이면 팝업).
        _register_security_module()
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
        """기존 문서(템플릿)를 연다.

        ⚠️ 절대경로 강제 — HWP COM 은 상대경로를 **Hwp.exe 프로세스 CWD** 기준으로
        해석해 엉뚱한 파일을 열거나(저장은 엉뚱한 곳에 쓰고) 후처리는 파이썬 CWD 의
        다른 파일을 만진다(메모리 `cache-rerender-and-winerror5-lock` 함정 2).
        """
        path = str(Path(path).resolve())
        ext = os.path.splitext(path)[1].lower().lstrip(".")
        fmt = "HWPX" if ext == "hwpx" else "HWP"
        self.hwp.Open(path, fmt, "")

    def move_doc_begin(self) -> None:
        """커서를 문서 맨 앞으로 이동."""
        self.hwp.HAction.Run("MoveDocBegin")

    def move_doc_end(self) -> None:
        """커서를 문서 본문 맨 끝으로 이동(폼 헤더 블록 뒤에 본문 append 용)."""
        self.hwp.HAction.Run("MoveDocEnd")

    def header_begin(self, apply_type: int = 0) -> None:
        """머릿말 편집 영역으로 진입(이후 입력은 머릿말에 들어감). region_end() 로 빠져나온다.

        apply_type: 0=양쪽 / 1=짝수쪽 / 2=홀수쪽 (HWP 'HeaderFooter' 액션의 Type — 실측
        확정 2026-06-23). 비모달이라 헤드리스 동작. ⚠️ 이 액션은 *머릿말만* 만든다(꼬릿말 X);
        페이지 번호는 insert_page_number() 사용.
        """
        h = self.hwp
        h.HAction.GetDefault("HeaderFooter", h.HParameterSet.HHeaderFooter.HSet)
        h.HParameterSet.HHeaderFooter.Type = apply_type
        h.HAction.Execute("HeaderFooter", h.HParameterSet.HHeaderFooter.HSet)

    def region_end(self) -> None:
        """머릿말/표 등 편집 영역에서 본문으로 빠져나온다."""
        self.hwp.HAction.Run("CloseEx")

    def insert_page_number(self, draw_pos: str = "OutsideBottom") -> None:
        """자동 페이지 번호(쪽 번호)를 넣는다(꼬릿말 위치 — PageNumPos, <hp:pageNum> 생성).

        꼬릿말 커스텀 텍스트 영역은 COM 으로 못 만들지만, 페이지 번호는 이 전용 API 로
        넣는다(실측 확정 2026-06-23).

        draw_pos: HWP PageNumPosition 이름. 기본 "OutsideBottom"(바깥쪽 아래 = 홀수쪽
        오른쪽 / 짝수쪽 왼쪽 자동 미러 — 양면 인쇄 정석). 다른 값: BottomCenter,
        BottomLeft, BottomRight, OutsideBottom 등. 헬퍼 미지원 시 기본 위치(아래 가운데).
        """
        h = self.hwp
        h.HAction.GetDefault("PageNumPos", h.HParameterSet.HPageNumPos.HSet)
        try:
            h.HParameterSet.HPageNumPos.DrawPos = h.PageNumPosition(draw_pos)
        except Exception:
            pass  # PageNumPosition 헬퍼 없거나 잘못된 이름 → 기본(아래 가운데)
        h.HAction.Execute("PageNumPos", h.HParameterSet.HPageNumPos.HSet)

    def set_char_size(self, pt: int) -> None:
        """이후 입력될 텍스트의 글자 크기(pt)를 고정한다.

        선택 영역이 없으면 캐럿 위치의 글자모양에 적용되어 이후 입력에 반영된다.

        주의: 템플릿(.hwp/.hwpx)을 연 상태에서 ``GetDefault("CharShape")`` 는
        그 컨텍스트의 글자모양을 돌려주는데, 장평(Ratio)·글자크기비율(Size)이
        **0** 으로 오는 경우가 있다. 그대로 Execute 하면 모든 본문 글자가
        폭/높이 0 으로 렌더돼 **보이지 않는다**(수식은 별도 객체라 영향 없음).
        따라서 Ratio·Size 를 항상 100% 로 명시해 0 적용을 차단한다.
        """
        h = self.hwp
        cs = h.HParameterSet.HCharShape
        h.HAction.GetDefault("CharShape", cs.HSet)
        cs.Height = h.PointToHwpUnit(pt)
        for _script in ("Hangul", "Latin", "Hanja", "Japanese",
                        "Other", "Symbol", "User"):
            try:
                setattr(cs, f"Ratio{_script}", 100)   # 장평 0 → 글자 폭 0(투명) 방지
                setattr(cs, f"Size{_script}", 100)     # 상대크기 0 → 글자 높이 0 방지
            except Exception:
                pass
        h.HAction.Execute("CharShape", cs.HSet)

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
        path = Path(path).resolve()   # 상대경로 → HWP CWD 저장(빈/엉뚱한 출력) 방지
        if path.exists():
            try:
                path.unlink()
            except Exception:
                pass
        self.force_layout()
        import time as _time
        t0 = _time.time()
        self.hwp.SaveAs(str(path), "HWPX", "")
        # 침묵 실패 방어 — 출력이 잠겨 있으면(WinError 5 상황) SaveAs 가 메시지박스만
        # 자동응답하고 조용히 실패해, 호출부가 **이전 회차의 낡은 파일**을 후처리해 성공
        # 반환하던 버그(감사 2026-06-10). 파일 존재+mtime 갱신을 확인하고 아니면 raise.
        if not path.exists() or path.stat().st_mtime < t0 - 2:
            raise RuntimeError(
                f"HWPX 저장 실패(파일 미갱신): {path} — 출력 파일이 열려 있거나(잠김) "
                f"경로가 잘못됐을 수 있습니다.")
        return path

    def save_hwp(self, path: str | Path) -> Path:
        """최종 산출물 .hwp 저장.

        **.hwpx 로는 폼의 바탕쪽(master page)이 적용되지 않는다** — 대수회 폼의 2단 가운데
        구분선은 `masterpage0.xml` 의 단 구분선(colLine)인데, HWP 가 .hwpx 를 열면 이 바탕쪽을
        그리지 않는다(레퍼런스 `[다사중] (워드).hwp` 도 .hwpx 로 변환하면 똑같이 선이 사라짐 —
        실측 2026-07-24). .hwp 로 저장하면 살아나 레퍼런스와 동일한 **전체 높이** 세로선이
        나온다. 그래서 중간 후처리는 .hwpx 로 하되 **최종만 .hwp** 로 굽는다.
        """
        path = Path(path).resolve()   # 상대경로 → HWP CWD 저장 방지(save_hwpx 와 동일)
        if path.exists():
            try:
                path.unlink()
            except Exception:
                pass
        self.force_layout()
        import time as _time
        t0 = _time.time()
        self.hwp.SaveAs(str(path), "HWP", "")
        if not path.exists() or path.stat().st_mtime < t0 - 2:
            raise RuntimeError(
                f"HWP 저장 실패(파일 미갱신): {path} — 출력 파일이 열려 있거나(잠김) "
                f"경로가 잘못됐을 수 있습니다.")
        return path

    def save_pdf(self, path: str | Path) -> Path:
        """렌더 검증용 PDF 내보내기."""
        path = Path(path).resolve()
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
        except Exception as e:
            # Quit 실패 = 고아 Hwp.exe 가능(비결정적 hang·파일잠금의 문서화된 주범) —
            # 침묵하면 원인 추적이 불가능해 최소한 로그는 남긴다.
            logger.warning("HWP Quit 실패(고아 프로세스 가능): %s", e)
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
        self.emphasis_run(s, underline=True)

    def emphasis_run(self, s: str, bold: bool = False, underline: bool = False) -> None:
        """볼드/밑줄 강조 텍스트 run 삽입(앞뒤로 해당 글자모양 토글).

        부정 선택문("옳지 않은 것")의 부정어를 볼드+밑줄로 강조하는 데 쓴다(사용자 2026-06-16).
        토글은 본문 기본 상태(볼드·밑줄 OFF — `_set_plain`/번호 뒤 set_char_shape 가 보장)에서
        켜고 끄므로 앞뒤 상태를 오염하지 않는다. 밑줄 색/선형은 저장 후 `_solidify_underline`
        가 검정 실선으로 통일.
        """
        if not s:
            return
        h = self.hwp
        if underline:
            h.HAction.Run("CharShapeUnderline")
        if bold:
            h.HAction.Run("CharShapeBold")
        self.text(s)
        if bold:
            h.HAction.Run("CharShapeBold")
        if underline:
            h.HAction.Run("CharShapeUnderline")

    def superscript_run(self, s: str) -> None:
        """위첨자(글자모양) 텍스트 run 삽입. 수식 객체보다 본문에 밀착돼

        네이티브 입력과 동일하게 렌더된다(예: 3²). 앞뒤로 토글.
        """
        if not s:
            return
        h = self.hwp
        h.HAction.Run("CharShapeSuperscript")
        self.text(s)
        h.HAction.Run("CharShapeSuperscript")

    def subscript_run(self, s: str) -> None:
        """아래첨자(글자모양) 텍스트 run 삽입(예: a_n). 앞뒤로 토글."""
        if not s:
            return
        h = self.hwp
        h.HAction.Run("CharShapeSubscript")
        self.text(s)
        h.HAction.Run("CharShapeSubscript")

    def equation(self, script: str) -> None:
        """HWP 수식 스크립트를 인라인(글자처럼 취급)으로 삽입.

        크기는 HWP가 네이티브로 계산한다.
        """
        if not script:
            return
        # 수식 안 소유권 표식(config EQ_WATERMARK, 기본 OFF) — 렌더엔 안 보이고
        # 결합 위험(큰 연산자로 끝나는 식)은 게이트가 걸러 생략한다.
        try:
            from core.eq_watermark import stamp as _wm_stamp
            from utils.config import get_eq_watermark
            script = _wm_stamp(script, get_eq_watermark())
        except Exception:   # noqa: BLE001 — 표식 실패가 변환을 막지 않는다
            pass
        h = self.hwp
        # ParameterSet 은 반드시 한 번만 가져와 캐싱해 재사용한다. ``h.HParameterSet
        # .HEqEdit`` 를 매번 새로 접근하면 GetDefault/설정/Execute 가 서로 다른
        # 인스턴스를 보게 되어, 수식이 "미확정"(version="") 상태로 남아 HWP 가
        # 구형 메트릭으로 무겁게 렌더한다(편집기로 한 번 열었다 닫으면 정상화됨).
        # 같은 객체에 모든 설정을 쌓고 그 HSet 으로 Execute 해야 version 이 스탬프되어
        # 편집기 직접입력과 동일한(가벼운) 렌더가 된다. (실측 확정 2026-06-02)
        eq = h.HParameterSet.HEqEdit
        h.HAction.GetDefault("EquationCreate", eq.HSet)
        eq.string = script
        eq.BaseUnit = h.PointToHwpUnit(self.eq_pt)
        eq.TreatAsChar = 1                # 글자처럼 취급(인라인) — 생성 시점에 지정.
        # 수식 글꼴 명시 고정(빈 값이면 HWP 기본 HancomEQN 으로 렌더).
        if self.eq_font:
            try:
                eq.EqFontName = self.eq_font
            except Exception:
                pass
        h.HAction.Execute("EquationCreate", eq.HSet)
        # 편집기 닫기. TreatAsChar=1 로 이미 인라인이며, Close 가 커서를 수식 뒤에
        # 두므로 사후 FindCtrl/ShapeObjTreatAsChar 처리(미확정 version="" 유발)는
        # 불필요하다. (실측 확정 2026-06-02: 사후 처리 제거로 version 스탬프 + 인라인 동시 달성)
        #
        # 단 **본문(list 0)에서만** Close 한다. 표 셀(list!=0) 안에서는 열린 편집기가
        # 없어 Run("Close")가 '셀 편집영역'을 닫는다 → 커서가 본문으로 튕겨 보기/조건
        # 박스(1×1 표) 안 수식이 셀 밖으로 새고, 게다가 표 객체가 닫힘/선택 상태로 남아
        # **다음 TableCreate 가 COM 예외로 실패**한다(SetPos 로 커서만 되돌려도 표 상태는
        # 깨진 채). 셀 안에선 Execute 만으로 수식이 인라인 삽입되고 커서가 그 뒤에 오므로
        # Close 가 애초에 불필요하다. (실측 확정 2026-06-04)
        if h.GetPos()[0] == 0:
            h.HAction.Run("Close")

    def insert_picture(self, path: str | Path) -> None:
        """그림 파일을 본문에 삽입(글자처럼 취급, 인라인).

        도형 크롭 이미지를 HWPX에 임베딩할 때 사용. 표시 크기는 호출 전에
        이미지 픽셀 크기로 조절한다(ShapeObjDialog는 모달이라 헤드리스 hang →
        COM 리사이즈 대신 PIL 리사이즈 사용).
        """
        path = str(Path(path))
        if not os.path.exists(path):
            return
        h = self.hwp
        try:
            # InsertPicture(파일, Embedded, sizeoption, reverse, watermark, effect, width, height)
            # Embedded=True: 문서에 포함. sizeoption=2(=이미지 원래 크기).
            h.InsertPicture(path, True, 2, 0, 0, 0, 0, 0)
        except Exception:
            try:
                h.InsertPicture(path, True, 2)
            except Exception:
                return
        # 방금 삽입한 그림 선택 → 글자처럼 취급(인라인)
        try:
            h.FindCtrl()
            h.HAction.Run("ShapeObjTreatAsChar")
            h.HAction.Run("Cancel")
            h.HAction.Run("MoveRight")
        except Exception:
            pass

    def break_para(self) -> None:
        """단락 나누기(새 줄)."""
        self.hwp.HAction.Run("BreakPara")

    def break_page(self) -> None:
        """쪽 나누기(강제 새 페이지). 정답·해설 페이지를 문제 뒤 새 쪽에 시작할 때(§44).

        late-binding(dynamic.Dispatch)이라 BreakPage 액션 정상 동작. 실패해도 예외 전파만
        (호출부 _write_answer_page 는 페이지 안 나뉘어도 정답 내용은 이어 출력)."""
        self.hwp.HAction.Run("BreakPage")

    def align_center(self) -> None:
        """현재 단락 가운데 정렬."""
        self.hwp.HAction.Run("ParagraphShapeAlignCenter")

    def align_left(self) -> None:
        """현재 단락 왼쪽 정렬."""
        self.hwp.HAction.Run("ParagraphShapeAlignLeft")

    def align_right(self) -> None:
        """현재 단락 오른쪽 정렬."""
        self.hwp.HAction.Run("ParagraphShapeAlignRight")

    def set_char_shape(self, pt: float | None = None, bold: bool | None = None) -> None:
        """캐럿 글자모양을 설정한다(이후 입력되는 글자에 적용). 지정 안 한 항목은 현 상태 유지.

        **장평(Ratio*)·상대크기(Size*)를 모든 스크립트에 100 으로 명시**해야 한다. GetDefault
        가 이들을 0 으로 주는 경우가 있고, 0 이면 글자가 투명(폭/크기 0)으로 렌더돼 본문이
        통째로 사라진다(실측 2026-06-04: 누락 시 한글·번호 전부 소실). hwp_form_writer
        ``_set_plain`` 과 동일한 안전 패턴.
        """
        h = self.hwp
        h.HAction.GetDefault("CharShape", h.HParameterSet.HCharShape.HSet)
        cs = h.HParameterSet.HCharShape
        if pt is not None:
            try:
                cs.Height = h.PointToHwpUnit(pt)
            except Exception:
                pass
        if bold is not None:
            try:
                cs.Bold = 1 if bold else 0
            except Exception:
                pass
        for sc in ("Hangul", "Latin", "Hanja", "Japanese", "Other", "Symbol", "User"):
            try:
                setattr(cs, f"Ratio{sc}", 100)
                setattr(cs, f"Size{sc}", 100)
            except Exception:
                pass
        h.HAction.Execute("CharShape", cs.HSet)

    def endnote(self) -> bool:
        """현재 위치에 미주(자동번호)를 삽입하고 **본문으로 복귀**한다. 성공 시 True.

        문항번호를 미주 자동번호로 쓰기 위함(문항 N개 = 미주 N개). InsertEndnote 는 커서를
        미주 편집영역으로 옮기는데, 그대로 두면 이후 본문이 전부 미주로 들어가 문서가 깨진다.
        → 삽입 전 본문 위치(GetPos)를 기억했다가 **SetPos 로 마크 다음(본문)으로 강제 복귀**.
        복귀가 본문 list 로 확인되지 않으면 MoveDocEnd 로 안전 복구하고 False(호출부가 텍스트
        번호로 폴백). COM 미주 '생성'은 이 코드베이스 전례가 없어 실측 검증 필요(2026-06-04).

        번호 글자모양은 **note_pt(기본 12pt)·볼드**로 — 사용자 폼 스타일(문항번호 12pt 볼드).
        마크는 삽입 시점의 캐럿 글자모양을 상속하므로 InsertEndnote 직전에 12pt 볼드를 걸고,
        복귀 후 본문(base_pt·일반)으로 되돌려 발문은 기본 크기로 입력되게 한다. (번호 형식
        "1." 의 마침표 suffix 는 supscript=0 과 함께 저장 후 XML 후처리 ``_set_endnote_suffix``.)
        """
        h = self.hwp
        try:
            self.set_char_shape(self.note_pt, bold=True)   # 번호 12pt 볼드
            before = h.GetPos()                  # (list, para, pos) — 본문 번호 위치
            h.HAction.Run("InsertEndnote")       # 미주 삽입(마크 1글자) → 커서 미주영역
            # 본문 복귀: 마크 다음 위치로. (미주영역 list 에서 본문 list 로 빠져나옴)
            h.SetPos(before[0], before[1], before[2] + 1)
            after = h.GetPos()
            self.set_char_shape(self.base_pt, bold=False)  # 발문은 기본 크기·일반
            if after[0] != before[0]:            # 본문 list 로 복귀 못 하면 실패
                h.HAction.Run("MoveDocEnd")
                return False
            return True
        except Exception:
            try:
                h.HAction.Run("MoveDocEnd")
            except Exception:
                pass
            return False

    def table_begin(self, nrow: int = 1, ncol: int = 1, line_width: int = 42000,
                    col_widths: list[int] | None = None) -> None:
        """빈 표를 만들고 커서를 (0,0) 셀에 둔다.

        셀에 텍스트/수식 등 리치 콘텐츠를 직접 입력할 때 사용(보기/조건 테두리 박스).
        입력이 끝나면 반드시 ``table_end()`` 로 표 밖으로 탈출한다.

        col_widths: 열별 **상대 비율**(예 ``[1, 3]`` = 줄기:잎 1:3). None 이면 균등 분할.
        """
        if nrow < 1 or ncol < 1:
            raise ValueError(f"table_begin: 행/열은 1 이상이어야 함 (nrow={nrow}, ncol={ncol})")
        h = self.hwp
        # **반드시 CreateAction/CreateSet 으로 독립 파라미터셋**을 쓴다. 공유
        # ``h.HParameterSet.HTableCreation`` 을 재사용하면, 문서에 수식(EquationCreate)이
        # 한 번이라도 삽입된 뒤로는 공유 HParameterSet 가 오염돼 **두 번째 TableCreate
        # 부터 COM 서버 예외(-2147417851)로 실패**한다(첫 표는 통과). 보기/조건을 1×1 표
        # 박스로 감싸면(A3) 문항마다 표가 생기는데, 수식 든 문항이 흔해 둘째 문항부터
        # 전량 크래시했다. CreateSet 는 호출마다 새 파라미터셋이라 수식 오염·재사용과
        # 무관하게 N개 표가 안정 생성된다. (실측 확정 2026-06-04: 수식+표3개 생존.)
        act = h.CreateAction("TableCreate")
        pset = act.CreateSet()
        act.GetDefault(pset)
        pset.SetItem("Rows", nrow)
        pset.SetItem("Cols", ncol)
        pset.SetItem("WidthType", 0)    # 0=절대너비(ColWidth 합). 원본 동작 유지.
        pset.SetItem("HeightType", 0)
        col_arr = pset.CreateItemArray("ColWidth", ncol)
        if col_widths and len(col_widths) == ncol and sum(col_widths) > 0:
            tot = sum(col_widths)
            for c in range(ncol):
                col_arr.SetItem(c, max(int(line_width * col_widths[c] / tot), 1))
        else:
            col_w = max(int(line_width // ncol), 1)
            for c in range(ncol):
                col_arr.SetItem(c, col_w)
        row_arr = pset.CreateItemArray("RowHeight", nrow)
        for r in range(nrow):
            row_arr.SetItem(r, 1000)
        act.Execute(pset)
        # 커서는 (0,0) 셀에 위치

    def table_next_cell(self) -> None:
        """다음 셀로 이동(좌→우, 행 끝이면 다음 행 첫 셀)."""
        self.hwp.HAction.Run("TableRightCell")

    def table_end(self) -> None:
        """표 밖(표 '다음' 단락)으로 탈출.

        ``Run("Close")`` 는 셀 편집을 끝내고 커서를 본문으로 보내지만 **표 '앞' 단락**
        (표의 앵커 단락)에 둔다. 여기서 ``Run("MoveRight")`` 를 하면 표를 건너뛰는 게
        아니라 **표 셀 안(시작)으로 재진입**해(실측: Close→(0,P,0) → MoveRight→(2,0,0)),
        이후 쓰는 내용이 전부 셀 맨 앞에 쌓여 보기/조건 박스 뒤 문항이 박스 안으로
        빨려들어간다. 대신 **표 다음 단락(P+1)으로 SetPos** 한다(단락 인덱스 기반이라
        박스 높이와 무관·결정적). 표 뒤엔 항상 트레일링 단락이 있다. (실측 확정 2026-06-04)
        """
        h = self.hwp
        h.HAction.Run("Close")
        p = h.GetPos()                       # (list, 표 앵커 단락, 0)
        try:
            h.SetPos(p[0], p[1] + 1, 0)      # 표 '다음' 단락 시작으로
        except Exception:
            h.HAction.Run("MoveDown")

    def table(self, rows: list[list[str]], line_width: int = 8000) -> None:
        """문자열 2D 배열로 표를 만들고 채운다.

        rows: 행 우선(row-major) 문자열 배열. 셀은 텍스트만 지원.
        """
        if not rows:
            return
        nrow = len(rows)
        ncol = max(len(r) for r in rows)
        self.table_begin(nrow, ncol, line_width)
        for ri in range(nrow):
            row = rows[ri]
            for ci in range(ncol):
                val = row[ci] if ci < len(row) else ""
                self.text(str(val))
                if not (ri == nrow - 1 and ci == ncol - 1):
                    self.table_next_cell()
        self.table_end()
