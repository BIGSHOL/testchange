# -*- coding: utf-8 -*-
"""파서 결과 점검 — 박스 마커·수식 분리가 의도대로인지."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
from core.content_parser import parse_ocr_response  # noqa: E402

want = [int(a) for a in sys.argv[1:]]
for f in sorted((HERE / "ocr").glob("p*_merged.json")):
    pg = parse_ocr_response(json.loads(f.read_text(encoding="utf-8")), page_number=1)
    for q in pg.questions:
        if want and q.number not in want:
            continue
        print(f"Q{q.number}", [(b.type.name[:2], b.value[:60], "BOX" if getattr(b, "box_member", False) else "")
                               for b in q.contents])
