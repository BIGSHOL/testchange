# -*- coding: utf-8 -*-
import glob, json, os, sys
D = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(D))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")
from core.content_parser import parse_ocr_response
from core.latex_to_hwpeq import latex_to_hwpeq


def dump(blocks, ind="  "):
    out = []
    for b in blocks:
        tp = getattr(b.type, "name", str(b.type))
        if "EQ" in tp:
            out.append(f"[{latex_to_hwpeq(b.value)}]")
        elif tp == "TEXT":
            out.append(b.value)
        else:
            out.append(f"<{tp}>")
    return "|".join(out)


for f in sorted(glob.glob(os.path.join(glob.escape(D), "ocr", "p*_merged.json"))):
    raw = json.load(open(f, encoding="utf-8"))
    page = parse_ocr_response(raw, 1)
    for q in page.questions:
        print(q.number, q.score, dump(q.contents)); [print("   SUB", dump(s.contents)) for s in getattr(q,"sub_questions",[]) or []]
        for c in q.choices:
            print("    ", c.number, dump(c.contents))
