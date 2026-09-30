import json, sys
sys.path.insert(0, r"D:\시험지 한글화")
sys.stdout.reconfigure(encoding="utf-8")
from core.content_parser import parse_ocr_response
from core.latex_to_hwpeq import latex_to_hwpeq
base = r"D:\시험지 한글화\corpus\[대구일중][3][26-2-중간] (원본)\ocr"
for n in range(1,5):
    d = json.load(open(f"{base}\p{n}_merged.json", encoding="utf-8"))
    pg = parse_ocr_response(d, n)
    for q in pg.questions:
        if q.number not in (8,9,10,13,17,18,20,22): continue
        print("Q", q.number, q.score)
        for b in q.contents:
            v = b.value
            if b.type.name.startswith("EQ"):
                try: v = v + "  =>  " + latex_to_hwpeq(v)
                except Exception as e: v += f" ERR {e}"
            print("   ", b.type.name, repr(v)[:160])
