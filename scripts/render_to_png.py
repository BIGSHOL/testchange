# HWPX → PDF → PNG 렌더 (육안 검증용). HWP COM(한글) 설치 필요.
#
# 사용법:
#   python scripts/render_to_png.py <IN.hwpx> [OUT_PREFIX]
#     → <OUT_PREFIX>_1.png, _2.png, … (기본 prefix: <repo>/.testkit/render)
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
    hwp.Open(src, "HWPX", "")
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
