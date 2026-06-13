# .hwp/.hwpx → 본문 텍스트 (HWP COM GetTextFile). PDF SaveAs 가 외부 .hwp 에서 깨지므로
# 텍스트 추출로 내용 1:1 대조. Quit() hang 회피 위해 GetTextFile 후 os._exit.
# 사용법: python hwp2txt.py "<src.hwp|hwpx>" "<out.txt>"
import sys, os, pythoncom
import win32com.client as w

src, out = sys.argv[1], sys.argv[2]
fmt = "HWP" if src.lower().endswith(".hwp") else "HWPX"
pythoncom.CoInitialize()
h = w.Dispatch("HWPFrame.HwpObject")
h.SetMessageBoxMode(0xFFFFFF)
h.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
try: h.XHwpWindows.Item(0).Visible = False
except Exception: pass
h.Open(src, fmt, "")
txt = h.GetTextFile("TEXT", "")
with open(out, "w", encoding="utf-8") as f:
    f.write(txt or "")
print("chars:", len(txt or ""))
sys.stdout.flush()
os._exit(0)   # Quit() hang 회피
