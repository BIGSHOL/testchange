# -*- coding: utf-8 -*-
"""게이트 hwpx 에서 메타란([중단원]/[난이도]) 값과 시험범위를 뽑아 OCR JSON 과 대조."""
import json
import re
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")
hwpx = sorted((HERE / "out").glob("*__gate.hwpx"))[-1]
with zipfile.ZipFile(hwpx) as z:
    xml = "".join(z.read(n).decode("utf-8") for n in z.namelist() if re.search(r"section\d+\.xml$", n))

want = []
for f in sorted((HERE / "ocr").glob("p*_merged.json")):
    for q in json.loads(f.read_text(encoding="utf-8"))["questions"]:
        want.append((q["number"], q["topic"], q["difficulty"]))


def para_texts(label):
    out = []
    for m in re.finditer(r"<hp:p\b(?:(?!<hp:p\b).)*?</hp:p>", xml, re.S):
        t = "".join(re.findall(r"<hp:t[^>]*>(.*?)</hp:t>", m.group(0), re.S))
        t = re.sub(r"<[^>]+>", "", t)
        if label in t:
            out.append(t.strip())
    return out


topics = [t.split("[중단원]", 1)[1].strip() for t in para_texts("[중단원]")]
diffs = [t.split("[난이도]", 1)[1].strip() for t in para_texts("[난이도]")]
print("중단원 칸", len(topics), "| 난이도 칸", len(diffs), "| 문항", len(want))
bad = 0
for i, (n, tp, df) in enumerate(want):
    got_t = topics[i] if i < len(topics) else None
    got_d = diffs[i] if i < len(diffs) else None
    ok = (got_t == tp and got_d == df)
    bad += not ok
    print(f"{n:>2} {'OK ' if ok else 'BAD'} [{got_t}] [{got_d}]" + ("" if ok else f"  ← 기대 [{tp}] [{df}]"))
print("소단원 라벨 잔존:", xml.count("[소단원]"))
rng = [t for t in re.findall(r"<hp:t[^>]*>([^<]*~[^<]*)</hp:t>", xml) if "범위" in t or "소인수" in t or "문자" in t]
print("시험범위:", rng[:3])
raise SystemExit(1 if bad or len(topics) != len(want) else 0)
