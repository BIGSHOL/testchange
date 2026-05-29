"""v3/v4/정답 HWPX의 수식 속성 분포를 비교한다."""

from __future__ import annotations

import re
import statistics
import zipfile
from collections import Counter
from pathlib import Path

DATA_DIR = Path(r"D:/시험지 한글화/data")
REF_XML = Path(r"D:/시험지 한글화/hwpx_조암/Contents/section0.xml")
V3 = DATA_DIR / "[조암중][2][25-1-중간][동아강] (변환_v3).hwpx"
V4 = DATA_DIR / "[조암중][2][25-1-중간][동아강] (변환_v4).hwpx"

EQ_RE = re.compile(r"<hp:equation\b[^>]*>.*?</hp:equation>", re.DOTALL)


def _attr(tag: str, key: str) -> str | None:
    m = re.search(rf'\b{key}="([^"]*)"', tag)
    return m.group(1) if m else None


def _child(block: str, tag: str) -> str | None:
    m = re.search(rf"<hp:{tag}\b([^/>]*)/?>", block)
    return m.group(1) if m else None


def extract(xml: str) -> list[dict]:
    out = []
    for e in EQ_RE.findall(xml):
        sz = _child(e, "sz") or ""
        om = _child(e, "outMargin") or ""
        try:
            out.append(
                {
                    "w": int(_attr(sz, "width") or "0"),
                    "h": int(_attr(sz, "height") or "0"),
                    "om_l": int(_attr(om, "left") or "0"),
                    "baseLine": int(_attr(e, "baseLine") or "0"),
                }
            )
        except ValueError:
            continue
    return out


def load_from_hwpx(path: Path) -> list[dict]:
    if path.suffix == ".xml":
        return extract(path.read_text(encoding="utf-8"))
    with zipfile.ZipFile(path, "r") as zf:
        xml = zf.read("Contents/section0.xml").decode("utf-8")
    return extract(xml)


def summarize(name: str, data: list[dict]) -> None:
    widths = [d["w"] for d in data]
    heights = Counter(d["h"] for d in data)
    om_l = Counter(d["om_l"] for d in data)
    bl = Counter(d["baseLine"] for d in data)

    print(f"━━━ {name} ({len(data)}개) ━━━")
    print(f"  width   min={min(widths)}  max={max(widths)}  mean={statistics.mean(widths):.0f}  0_count={widths.count(0)}")
    print(f"  height  {dict(heights)}")
    print(f"  outMargin.left  {dict(om_l)}")
    print(f"  baseLine        {dict(bl)}")
    print()


def main() -> None:
    ref = extract(REF_XML.read_text(encoding="utf-8"))
    v3 = load_from_hwpx(V3)
    v4 = load_from_hwpx(V4)

    print()
    summarize("REFERENCE (한컴 정답)", ref)
    summarize("v3 (이전 버전)", v3)
    summarize("v4 (패치 후)", v4)

    # ── 핵심 지표: zero-width 수식 비율 ──
    zero_v3 = sum(1 for d in v3 if d["w"] == 0)
    zero_v4 = sum(1 for d in v4 if d["w"] == 0)
    print(f"제로폭 수식:  v3={zero_v3}/{len(v3)}  v4={zero_v4}/{len(v4)}")

    # ── outMargin 정답 일치율 ──
    ok_v3 = sum(1 for d in v3 if d["om_l"] == 170)
    ok_v4 = sum(1 for d in v4 if d["om_l"] == 170)
    print(f"outMargin=170 일치:  v3={ok_v3}/{len(v3)}  v4={ok_v4}/{len(v4)}")

    # ── baseLine 정답 일치율 ──
    bl_v3 = sum(1 for d in v3 if d["baseLine"] == 85)
    bl_v4 = sum(1 for d in v4 if d["baseLine"] == 85)
    print(f"baseLine=85 일치:    v3={bl_v3}/{len(v3)}  v4={bl_v4}/{len(v4)}")

    # ── height 1200/2400만 사용하는 비율 ──
    valid_heights = {1200, 2400}
    h_v3 = sum(1 for d in v3 if d["h"] in valid_heights)
    h_v4 = sum(1 for d in v4 if d["h"] in valid_heights)
    print(f"height ∈ 1200/2400:  v3={h_v3}/{len(v3)}  v4={h_v4}/{len(v4)}")


if __name__ == "__main__":
    main()
