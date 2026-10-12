# -*- coding: utf-8 -*-
"""<보기> 표 안 그림(2번) — 파서·tail 분배가 그림을 **박스 안**으로 보내는지 점검."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
from core.content_parser import parse_ocr_response  # noqa: E402
from core.hwp_com_writer import _condition_start, _split_tail_post, _tail_start  # noqa: E402
from models.exam_document import ContentType  # noqa: E402

d = json.loads((HERE / "ocr" / "p2_merged.json").read_text(encoding="utf-8"))
for q in d["questions"]:
    for i, b in enumerate(q["contents"]):
        if b.get("type") == "figure":
            q["contents"][i] = {"type": "image", "value": "X.png"}
pg = parse_ocr_response(d, page_number=1)
for q in pg.questions:
    if q.number not in (2, 4):
        continue
    cs = q.contents
    print(f"Q{q.number}", [(b.type.name[:3], (b.value or "")[:24]) for b in cs])
    ts = _tail_start(cs)
    tail = cs[ts:] if ts is not None else []
    core, post = _split_tail_post(tail)
    c0 = _condition_start(core)
    pre, box = (core, []) if c0 is None else (core[:c0], core[c0:])
    show = lambda bs: [(b.type.name[:3], (b.value or "")[:14]) for b in bs]   # noqa: E731
    print("   head", show(cs[:ts] if ts is not None else cs))
    print("   pre ", show(pre))
    print("   box ", show(box))
    print("   post", show(post))
    if q.number == 2:
        assert [b.type for b in box] == [ContentType.TEXT, ContentType.IMAGE], "그림이 박스 안에 없다"
        assert not pre and not post
print("OK")
