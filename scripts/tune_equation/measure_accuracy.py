"""현재 추정기(_estimate_equation_size)가 골든셋에 대해 얼마나 정확한지 측정.

사용:
    python scripts/tune_equation/measure_accuracy.py
    python scripts/tune_equation/measure_accuracy.py --compare-image

출력: width/height의 MAE, p50, p95, 최악 케이스 Top 10
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.hwpx_writer import _estimate_equation_size  # type: ignore

GOLDEN_JSON = Path(__file__).parent / "golden_equations.json"


def main() -> None:
    samples = json.loads(GOLDEN_JSON.read_text(encoding="utf-8"))

    rows = []
    for s in samples:
        est_w, est_h = _estimate_equation_size(s["script"])
        rows.append(
            {
                "script": s["script"],
                "actual_w": s["width"],
                "actual_h": s["height"],
                "est_w": est_w,
                "est_h": est_h,
                "err_w": est_w - s["width"],
                "err_h": est_h - s["height"],
                "rel_w": (est_w - s["width"]) / max(s["width"], 1),
            }
        )

    width_errs = [abs(r["err_w"]) for r in rows]
    rel_errs = [abs(r["rel_w"]) for r in rows]
    height_ok = sum(1 for r in rows if r["est_h"] == r["actual_h"])

    print("=" * 78)
    print("현재 추정기 정확도 리포트")
    print("=" * 78)
    print(f"총 샘플: {len(rows)}")
    print()
    print("── width (hwpunit, 실제 800~23925) ──")
    print(f"  MAE    = {statistics.mean(width_errs):8.0f}")
    print(f"  median = {statistics.median(width_errs):8.0f}")
    print(f"  p95    = {sorted(width_errs)[int(len(width_errs) * 0.95)]:8.0f}")
    print(f"  max    = {max(width_errs):8.0f}")
    print()
    print("── 상대 오차 (|est-actual|/actual) ──")
    print(f"  MAPE   = {statistics.mean(rel_errs)*100:6.2f}%")
    print(f"  median = {statistics.median(rel_errs)*100:6.2f}%")
    print(f"  p95    = {sorted(rel_errs)[int(len(rel_errs) * 0.95)]*100:6.2f}%")
    print()
    print("── height ──")
    print(f"  정확: {height_ok}/{len(rows)} ({height_ok/len(rows)*100:.0f}%)")
    print()
    print("── 최악 케이스 Top 10 (절대 오차) ──")
    worst = sorted(rows, key=lambda r: -abs(r["err_w"]))[:10]
    for r in worst:
        script = r["script"][:50]
        print(
            f"  actual={r['actual_w']:6d}  est={r['est_w']:6d}  "
            f"err={r['err_w']:+6d} ({r['rel_w']*100:+.1f}%)  {script!r}"
        )

    # 전체 rows 저장 (나중 회귀 보정에 사용)
    out = Path(__file__).parent / "accuracy_report.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
