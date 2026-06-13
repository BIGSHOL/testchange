# .hwp/.hwpx → PDF (HWP COM). Quit() 가 hang 하므로 SaveAs 후 파일크기 안정 확인하고
# os._exit 로 강제 종료(COM cleanup 생략) — 호출측이 taskkill Hwp.exe 로 잔여 정리.
# 사용법: python hwp2pdf.py "<src.hwp|hwpx>" "<out.pdf>"
import sys, os, time, pythoncom
import win32com.client as w

src, pdf = sys.argv[1], sys.argv[2]
fmt = "HWP" if src.lower().endswith(".hwp") else "HWPX"
pythoncom.CoInitialize()
h = w.Dispatch("HWPFrame.HwpObject")
h.SetMessageBoxMode(0xFFFFFF)
h.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
try: h.XHwpWindows.Item(0).Visible = False
except Exception: pass
if os.path.exists(pdf):
    try: os.remove(pdf)
    except Exception: pass
h.Open(src, fmt, "")
h.SaveAs(pdf, "PDF", "")
# 파일 크기 안정될 때까지 대기(최대 20s) — SaveAs 비동기 마무리
last, stable = -1, 0
for _ in range(40):
    time.sleep(0.5)
    sz = os.path.getsize(pdf) if os.path.exists(pdf) else 0
    if sz > 0 and sz == last:
        stable += 1
        if stable >= 3: break
    else:
        stable = 0
    last = sz
print("PDF size:", os.path.getsize(pdf) if os.path.exists(pdf) else 0)
sys.stdout.flush()
os._exit(0)   # Quit() hang 회피 — 강제 종료
