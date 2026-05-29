"""정답 수식 84개에서 height=1200 vs height=2400을 가르는 실제 규칙을 역공학."""

import json
import re
from pathlib import Path

GOLDEN_JSON = Path(__file__).parent / "golden_equations.json"

# 분석할 마커 키워드
MARKERS = [
    ("over", r"\bover\b"),
    ("atop", r"\batop\b"),
    ("sqrt", r"\bsqrt\b"),
    ("root", r"\broot\b"),
    ("SUM", r"\bSUM\b"),
    ("INT", r"\bINT\b"),
    ("PROD", r"\bPROD\b"),
    ("lim", r"\blim\b"),
    ("LEFT", r"\bLEFT\b"),
    ("matrix", r"\bmatrix\b"),
    ("array", r"\{array\}"),
    ("binom", r"\bbinom\b"),
    ("^", r"\^"),
    ("_", r"_"),
]


def has_marker(script: str, pattern: str) -> bool:
    return bool(re.search(pattern, script))


def main() -> None:
    samples = json.loads(GOLDEN_JSON.read_text(encoding="utf-8"))
    tall = [s for s in samples if s["height"] == 2400]
    short = [s for s in samples if s["height"] == 1200]

    print(f"height=2400: {len(tall)}개 / height=1200: {len(short)}개\n")
    print("── 각 마커의 분포 (2400 vs 1200) ──")
    print(f"{'marker':10s}  {'2400':>8s}  {'1200':>8s}  {'exclusive':>12s}")
    for name, pattern in MARKERS:
        n_tall = sum(1 for s in tall if has_marker(s["script"], pattern))
        n_short = sum(1 for s in short if has_marker(s["script"], pattern))
        print(
            f"{name:10s}  {n_tall:>4d}/{len(tall):>3d}  "
            f"{n_short:>4d}/{len(short):>3d}  "
            f"{('2400만' if n_short == 0 and n_tall > 0 else '1200만' if n_tall == 0 and n_short > 0 else '혼재'):>12s}"
        )

    print("\n── 2400인데 분수/적분 마커 없는 케이스 (있다면) ──")
    for s in tall:
        if not any(has_marker(s["script"], p) for _, p in MARKERS if _ in ("over", "atop", "sqrt", "root", "SUM", "INT", "PROD", "binom", "matrix", "array")):
            print(f"  {s['script']!r}")

    print("\n── 1200인데 분수 마커 있는 케이스 (있다면) ──")
    for s in short:
        if re.search(r"\b(over|atop)\b", s["script"]):
            print(f"  {s['script']!r}")


if __name__ == "__main__":
    main()
