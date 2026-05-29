"""v5: MAPE 위주 score (p95 가중 0.3 → 0.1) + 탐색 범위 재조정.

v3에서 char_pad=0이 나온 이유는 score에 p95가 0.3 가중되어 있어
짧은 분수 과대가 p95를 지배했기 때문. MAPE 중심 score로 바꾸면
char_pad가 양의 값으로 나올 가능성을 검증.
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

    hangul_grid = [650, 700, 750]
    lr_grid = [1000, 1300, 1500, 1800, 2100]
    binop_grid = [0, 100, 200, 300, 400]
    fracpad_grid = [0, 100, 200, 300, 400]
    square_grid = [400, 500, 600, 700]
    charpad_grid = [0, 50, 100, 150, 200]

    total = (
        len(hangul_grid) * len(lr_grid) * len(binop_grid)
        * len(fracpad_grid) * len(square_grid) * len(charpad_grid)
    )
    print(f"v5 Grid: {total} combos × 84 (MAPE-centered score)")

    best = None
    for i, (h, lr, bsp, fp, sq, cp) in enumerate(
        product(hangul_grid, lr_grid, binop_grid, fracpad_grid, square_grid, charpad_grid)
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
        med = np.median(rel)
        # MAPE + median에 무게 (p95는 드롭)
        score = mape + 0.5 * med
        if best is None or score < best["score"]:
            best = {
                "hangul_w": h, "lr_w": lr, "binop_sp": bsp,
                "frac_pad": fp, "square_w": sq, "char_pad": cp,
                "scale": float(a), "bias": float(b),
                "mape": float(mape), "p95": float(p95), "median": float(med),
                "score": float(score),
            }
        if (i + 1) % 1000 == 0:
            print(f"  {i+1}/{total}  best MAPE={best['mape']*100:.2f}% med={best['median']*100:.2f}%")

    print("\n=== v5 최적 ===")
    assert best is not None
    for k, v in best.items():
        if isinstance(v, float):
            print(f"  {k:12s} = {v:.4f}")
        else:
            print(f"  {k:12s} = {v}")

    est = np.array(
        [
            estimate_with_params(
                s, best["hangul_w"], best["lr_w"], best["binop_sp"],
                best["frac_pad"], best["square_w"], best["char_pad"],
            )
            for s in scripts
        ]
    )
    pred = best["scale"] * est + best["bias"]
    err = np.abs(pred - actual)
    rel = err / np.maximum(actual, 1)

    print("\n=== v5 성능 ===")
    print(f"  MAPE    = {rel.mean()*100:.2f}%")
    print(f"  median  = {np.median(rel)*100:.2f}%")
    print(f"  p95     = {np.percentile(rel, 95)*100:.2f}%")
    print(f"  max     = {err.max():.0f}  ({rel.max()*100:.1f}%)")

    worst = np.argsort(-rel)[:10]
    print("\n── 최악 Top 10 ──")
    for i in worst:
        print(
            f"  actual={int(actual[i]):6d}  pred={int(pred[i]):6d}  "
            f"rel={(pred[i]-actual[i])/actual[i]*100:+.1f}%  {scripts[i][:55]!r}"
        )

    out = Path(__file__).parent / "best_params_v5.json"
    out.write_text(json.dumps(best, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {out}")


if __name__ == "__main__":
    main()
