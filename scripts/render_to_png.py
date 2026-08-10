# HWPX/HWP → PDF → PNG 렌더 (육안 검증용). HWP COM(한글) 설치 필요.
#
# 사용법:
#   python scripts/render_to_png.py <IN.hwpx|IN.hwp> [OUT_PREFIX]
#     → <OUT_PREFIX>_1.png, _2.png, … (기본 prefix: <repo>/.testkit/render)
#
# ⚠️ Open 포맷은 **확장자로 정한다**. 과거엔 "HWPX" 하드코딩이라 .hwp 를 넣으면
# 조용히 **빈 1쪽 PDF** 가 나왔다(2026-08-08 실측, 결함으로 오인하기 딱 좋음).
# 최종 산출물이 .hwp 가 된 뒤로(합의 #12) 이 경로를 자주 밟는다.
#
# CONVERSION_VISIBLE=False(숨김) 라 변환 중 사용자 문서로 타이핑이 새지 않는다.
# 다른 한글 파일을 열어둔 채 돌려도 안전(데이터 오염 방지, CLAUDE.md 참고).
import os, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_TESTKIT_DIR = REPO / ".testkit"


def main(argv):
    if not argv:
        raise SystemExit("사용법: python scripts/render_to_png.py <IN.hwpx> [OUT_PREFIX]")
    src = os.path.abspath(argv[0])
    # HWP COM 저장은 절대경로 필수 — 상대 prefix 면 PDF 가 HWP 작업디렉터리로 샌다
    prefix = os.path.abspath(argv[1] if len(argv) >= 2 else str(_TESTKIT_DIR / "render"))
    os.makedirs(os.path.dirname(prefix) or ".", exist_ok=True)
    pdf = prefix + ".pdf"

    # 고아 Hwp.exe 정리(비결정적 hang 방지, CLAUDE.md COM 교훈)
    try:
        import subprocess
        subprocess.run(["taskkill", "/F", "/IM", "Hwp.exe"],
                       capture_output=True)
    except Exception:
        pass

    import pythoncom; pythoncom.CoInitialize()
    import win32com.client as win32
    hwp = win32.Dispatch("HWPFrame.HwpObject")
    hwp.SetMessageBoxMode(0xFFFFFF)
    hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
    try:
        hwp.XHwpWindows.Item(0).Visible = False
    except Exception:
        pass
    fmt = "HWP" if os.path.splitext(src)[1].lower() == ".hwp" else "HWPX"
    if not hwp.Open(src, fmt, "forceopen:true"):
        hwp.Quit()
        raise SystemExit(f"HWP Open 실패({fmt}): {src}")
    if os.path.exists(pdf):
        os.remove(pdf)
    hwp.SaveAs(pdf, "PDF", "")
    hwp.Quit(); pythoncom.CoUninitialize()

    import fitz
    d = fitz.open(pdf)
    for i in range(d.page_count):
        d[i].get_pixmap(dpi=150).save(f"{prefix}_{i+1}.png")
    print(f"pages: {d.page_count} → {prefix}_*.png")


if __name__ == "__main__":
    main(sys.argv[1:])
