# -*- coding: utf-8 -*-
"""파싱 결과 전수 점검 — 평문 LaTeX 누수·수식 강등·박스 분리를 눈으로 본다."""
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")

from core.content_parser import parse_ocr_response          # noqa: E402
from core.latex_to_hwpeq import latex_to_hwpeq              # noqa: E402
from models.exam_document import ContentType                # noqa: E402

LEAK = re.compile(r"\\[a-zA-Z]|\^\{|_\{|\\\{|(?<!\{)\}(?!\})")
problems = []


def dump(q, prefix=""):
    print(f"\n=== {prefix}Q{q.number} (score={q.score}, label={q.label_type}) ===")
    for b in q.contents:
        _show(b, q.number, "본문")
    for ch in q.choices or []:
        for b in ch.contents:
            _show(b, q.number, f"선택지{ch.number}")
    for s in q.sub_questions or []:
        dump(s, prefix=f"{q.number}-")


def _show(b, num, where):
    v = b.value or ""
    tag = b.type.value
    extra = ""
    if b.type in (ContentType.EQUATION, ContentType.EQUATION_BLOCK):
        try:
            extra = " → " + latex_to_hwpeq(v, italicize_stat=False)
        except Exception as e:  # noqa: BLE001
            extra = f" → 변환실패 {e}"
            problems.append(f"Q{num} {where} 변환실패: {v}")
        if "\\" in extra:
            problems.append(f"Q{num} {where} 백슬래시 누수: {extra}")
    elif b.type == ContentType.TEXT and LEAK.search(v):
        problems.append(f"Q{num} {where} 평문 LaTeX 누수: {v!r}")
    flags = []
    if getattr(b, "bold", False):
        flags.append("B")
    if getattr(b, "underline", False):
        flags.append("U")
    if getattr(b, "box_member", False):
        flags.append("box")
    print(f"  [{tag}{'/' + ''.join(flags) if flags else ''}] {v!r}{extra}")


total = 0.0
files = [os.path.join(HERE, "ocr", n) for n in os.listdir(os.path.join(HERE, "ocr")) if re.match(r"p\d+_merged\.json$", n)]
for fp in sorted(files,
                 key=lambda p: int(re.search(r"p(\d+)_", os.path.basename(p)).group(1))):
    d = json.load(open(fp, encoding="utf-8"))
    page = parse_ocr_response(d, page_number=1)
    for q in page.questions:
        total += q.score or 0
        dump(q)

print("\n배점 합계:", round(total, 1))
print("\n=== 의심 항목", len(problems), "===")
for p in problems:
    print(" *", p)
