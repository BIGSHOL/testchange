"""정답 HWPX에서 수식 골든 데이터셋을 추출한다.

hp:equation 요소마다 script, 실측 width/height, baseLine, outMargin을 뽑아
golden_equations.json으로 저장.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

REFERENCE_XML = Path(r"D:/시험지 한글화/hwpx_조암/Contents/section0.xml")
OUTPUT_JSON = Path(__file__).parent / "golden_equations.json"


EQ_RE = re.compile(r"<hp:equation\b[^>]*>.*?</hp:equation>", re.DOTALL)


def _attr(tag_xml: str, attr: str) -> str | None:
    m = re.search(rf'\b{attr}="([^"]*)"', tag_xml)
    return m.group(1) if m else None


def _child(eq_xml: str, tag: str) -> str | None:
    m = re.search(rf"<hp:{tag}\b([^/>]*)/?>", eq_xml)
    return m.group(1) if m else None


def extract_one(eq_xml: str) -> dict | None:
    sz = _child(eq_xml, "sz")
    om = _child(eq_xml, "outMargin")
    script_m = re.search(r"<hp:script[^>]*>([^<]*)</hp:script>", eq_xml)
    if not (sz and om and script_m):
        return None

    try:
        w = int(_attr(sz, "width"))
        h = int(_attr(sz, "height"))
        om_l = int(_attr(om, "left"))
        om_r = int(_attr(om, "right"))
    except (TypeError, ValueError):
        return None

    return {
        "script": script_m.group(1),
        "width": w,
        "height": h,
        "baseLine": int(_attr(eq_xml, "baseLine") or "0"),
        "out_margin_left": om_l,
        "out_margin_right": om_r,
    }


def main() -> None:
    xml = REFERENCE_XML.read_text(encoding="utf-8")
    samples = [s for s in (extract_one(e) for e in EQ_RE.findall(xml)) if s]
    samples.sort(key=lambda s: (len(s["script"]), s["script"]))

    OUTPUT_JSON.write_text(
        json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    heights = Counter(s["height"] for s in samples)
    base_lines = Counter(s["baseLine"] for s in samples)
    margins = Counter((s["out_margin_left"], s["out_margin_right"]) for s in samples)
    widths = [s["width"] for s in samples]

    print(f"총 {len(samples)}개 수식을 {OUTPUT_JSON}에 저장")
    print(f"height 분포: {dict(heights)}")
    print(f"baseLine 분포: {dict(base_lines)}")
    print(f"outMargin 분포: {dict(margins)}")
    print(f"width: min={min(widths)}  max={max(widths)}  평균={sum(widths)/len(widths):.0f}")


if __name__ == "__main__":
    main()
