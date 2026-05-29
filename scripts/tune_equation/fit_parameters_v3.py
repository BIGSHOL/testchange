"""v3: 문자 단위 트래킹(CHAR_PAD) 추가.

v2 최적이 MAPE 6.44%에서 정체된 이유는 `a+b+c+d` 같은 선형식에서
HWP의 내재 자간(문자 간 간격)이 모델에 없었기 때문.

차원:
  - HANGUL_WIDTH, LEFT_RIGHT_EXTRA, BINOP_SPACE, FRAC_PADDING, SQUARE_WIDTH
  - **CHAR_PAD** (신규) : 가시 문자마다 가산되는 트래킹
  - GLOBAL_SCALE, BIAS  : 최종 선형 보정
"""

from __future__ import annotations

import json
import re
import sys
from itertools import product
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import core.hwpx_writer as mod  # type: ignore

GOLDEN_JSON = Path(__file__).parent / "golden_equations.json"


def estimate_with_params(
    script: str,
    hangul_w: int,
    lr_w: int,
    binop_sp: int,
    frac_pad: int,
    square_w: int,
    char_pad: int,
) -> float:
    mod._HWPEQ_HANGUL_WIDTH = hangul_w  # type: ignore
    mod._HWPEQ_LEFT_RIGHT_EXTRA = lr_w  # type: ignore
    mod._HWPEQ_BINOP_SPACE = binop_sp  # type: ignore
    mod._HWPEQ_FRAC_PADDING = frac_pad  # type: ignore
    mod._HWPEQ_CHAR_PAD = char_pad  # type: ignore
    mod._HWPEQ_KEYWORD_WIDTHS["SQUARE"] = square_w  # type: ignore

    mod._HWPEQ_GLOBAL_SCALE = 1.0  # type: ignore
    mod._HWPEQ_GLOBAL_BIAS = 0  # type: ignore

    w, _h = mod._estimate_equation_size(script)
    return float(w)


def main() -> None:
    samples = json.loads(GOLDEN_JSON.read_text(encoding="utf-8"))
    scripts = [s["script"] for s in samples]
    actual = np.array([s["width"] for s in samples], dtype=float)

    # v2 최적 주변으로 좁힌 탐색 + CHAR_PAD 차원
    hangul_grid = [650, 700, 750]
    lr_grid = [1200, 1500, 1800]
    binop_grid = [0, 100, 200]
    fracpad_grid = [200, 400, 600]
    square_grid = [500, 650, 800]
    charpad_grid = [0, 50, 100, 150, 200, 250, 300]

    total = (
        len(hangul_grid) * len(lr_grid) * len(binop_grid)
        * len(fracpad_grid) * len(square_grid) * len(charpad_grid)
    )
    print(f"Grid: {total} combinations × 84 samples")

    best = None
    for i, (h, lr, bsp, fp, sq, cp) in enumerate(
        product(
            hangul_grid, lr_grid, binop_grid, fracpad_grid, square_grid, charpad_grid
        )
    ):
        est = np.array(
            [estimate_with_params(s, h, lr, bsp, fp, sq, cp) for s in scripts]
        )
        A = np.vstack([est, np.ones(len(est))]).T
        (a, b), *_ = np.linalg.lstsq(A, actual, rcond=None)
        pred = a * est + b
        rel = np.abs(pred - actual) / np.maximum(actual, 1)
        mape = rel.mean()
        p95 = np.percentile(rel, 95)
        score = mape + 0.3 * p95
        if best is None or score < best["score"]:
            best = {
                "hangul_w": h,
                "lr_w": lr,
                "binop_sp": bsp,
                "frac_pad": fp,
                "square_w": sq,
                "char_pad": cp,
                "scale": float(a),
                "bias": float(b),
                "mape": float(mape),
                "p95": float(p95),
                "median": float(np.median(rel)),
                "score": float(score),
            }
        if (i + 1) % 500 == 0:
            print(f"  {i+1}/{total}  best MAPE={best['mape']*100:.2f}% p95={best['p95']*100:.2f}%")

    print("\n=== 최적 파라미터 ===")
    assert best is not None
    for k, v in best.items():
        if isinstance(v, float):
            print(f"  {k:12s} = {v:.4f}")
        else:
            print(f"  {k:12s} = {v}")

    est = np.array(
        [
            estimate_with_params(
                s,
                best["hangul_w"],
                best["lr_w"],
                best["binop_sp"],
                best["frac_pad"],
                best["square_w"],
                best["char_pad"],
            )
            for s in scripts
        ]
    )
    pred = best["scale"] * est + best["bias"]
    err = np.abs(pred - actual)
    rel = err / np.maximum(actual, 1)

    print("\n=== 최적 성능 ===")
    print(f"  MAPE    = {rel.mean()*100:.2f}%")
    print(f"  median  = {np.median(rel)*100:.2f}%")
    print(f"  p95     = {np.percentile(rel, 95)*100:.2f}%")
    print(f"  max     = {err.max():.0f}  ({rel.max()*100:.1f}%)")

    worst = np.argsort(-rel)[:10]
    print("\n── 최악 케이스 Top 10 ──")
    for i in worst:
        print(
            f"  actual={int(actual[i]):6d}  pred={int(pred[i]):6d}  "
            f"rel={(pred[i]-actual[i])/actual[i]*100:+.1f}%  "
            f"{scripts[i][:55]!r}"
        )

    out = Path(__file__).parent / "best_params_v3.json"
    out.write_text(json.dumps(best, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {out}")


if __name__ == "__main__":
    main()
