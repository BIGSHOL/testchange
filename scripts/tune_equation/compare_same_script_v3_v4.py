"""v3와 v4의 동일 script에 대한 width/height 변화를 비교."""

from __future__ import annotations

import re
import statistics
import zipfile
from pathlib import Path

DATA_DIR = Path(r"D:/시험지 한글화/data")
V3 = DATA_DIR / "[조암중][2][25-1-중간][동아강] (변환_v3).hwpx"
V4 = DATA_DIR / "[조암중][2][25-1-중간][동아강] (변환_v4).hwpx"

EQ_RE = re.compile(r"<hp:equation\b[^>]*>.*?</hp:equation>", re.DOTALL)


def load(path: Path) -> list[dict]:
    with zipfile.ZipFile(path, "r") as zf:
        xml = zf.read("Contents/section0.xml").decode("utf-8")

    out = []
    for e in EQ_RE.findall(xml):
        sz = re.search(r"<hp:sz\b([^/>]*)/?>", e)
        script = re.search(r"<hp:script[^>]*>([^<]*)</hp:script>", e)
        if not (sz and script):
            continue
        try:
            w = int(re.search(r'width="(\d+)"', sz.group(1)).group(1))
            h = int(re.search(r'height="(\d+)"', sz.group(1)).group(1))
        except AttributeError:
            continue
        out.append({"script": script.group(1), "w": w, "h": h})
    return out


def main() -> None:
    v3 = load(V3)
    v4 = load(V4)

    assert len(v3) == len(v4), f"수식 개수 불일치: v3={len(v3)}, v4={len(v4)}"

    print(f"v3/v4 수식 {len(v3)}개 대응 비교\n")

    same_w = 0
    changed_w = 0
    diffs = []
    height_changes = 0
    for a, b in zip(v3, v4):
        assert a["script"] == b["script"], "스크립트 불일치"
        if a["w"] == b["w"]:
            same_w += 1
        else:
            changed_w += 1
            diffs.append((a["script"], a["w"], b["w"]))
        if a["h"] != b["h"]:
            height_changes += 1

    print(f"width 변화: 동일={same_w}, 달라짐={changed_w}")
    print(f"height 변화: {height_changes}개\n")

    if diffs:
        rel_diffs = [abs(b - a) / max(a, 1) for _, a, b in diffs]
        print(f"width 변화량: MAE={statistics.mean([abs(b-a) for _, a, b in diffs]):.0f}  "
              f"평균 상대변화={statistics.mean(rel_diffs)*100:.1f}%")

        print("\n── width 변화가 큰 Top 15 ──")
        diffs.sort(key=lambda t: -abs(t[2] - t[1]))
        for script, a, b in diffs[:15]:
            delta = b - a
            pct = delta / max(a, 1) * 100
            print(f"  v3={a:6d}  v4={b:6d}  Δ={delta:+6d} ({pct:+.1f}%)  {script[:55]!r}")


if __name__ == "__main__":
    main()
