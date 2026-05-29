"""v4: 분수/일반 2-그룹 선형 보정.

짧은 분수는 +20% 과대, 긴 선형식은 -25% 과소 — 이는 단일 선형 (SCALE, BIAS)로
맞출 수 없는 체계 편차다. over/atop 여부로 두 모델을 분리한다.

차원:
  - HANGUL_WIDTH, LEFT_RIGHT_EXTRA, BINOP_SPACE, FRAC_PADDING, SQUARE_WIDTH, CHAR_PAD
  - 일반식 (SCALE_G, BIAS_G)
  - 분수식 (SCALE_F, BIAS_F)
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


def estimate_raw(script: str) -> float:
    """현재 모듈 상수 기준으로 base_width 측정 (SCALE=1, BIAS=0)."""
    mod._HWPEQ_GLOBAL_SCALE = 1.0  # type: ignore
    mod._HWPEQ_GLOBAL_BIAS = 0  # type: ignore
    w, _h = mod._estimate_equation_size(script)
    return float(w)


def set_params(
    hangul_w: int,
    lr_w: int,
    binop_sp: int,
    frac_pad: int,
    square_w: int,
    char_pad: int,
) -> None:
    mod._HWPEQ_HANGUL_WIDTH = hangul_w  # type: ignore
    mod._HWPEQ_LEFT_RIGHT_EXTRA = lr_w  # type: ignore
    mod._HWPEQ_BINOP_SPACE = binop_sp  # type: ignore
    mod._HWPEQ_FRAC_PADDING = frac_pad  # type: ignore
    mod._HWPEQ_CHAR_PAD = char_pad  # type: ignore
    mod._HWPEQ_KEYWORD_WIDTHS["SQUARE"] = square_w  # type: ignore


def fit_two_groups(scripts, actual):
    """일반/분수 그룹에 각각 선형 보정 (scale, bias) 피팅."""
    is_frac = np.array(
        [("over" in s or "atop" in s) for s in scripts], dtype=bool
    )
    est = np.array([estimate_raw(s) for s in scripts])

    def fit_group(mask):
        if mask.sum() < 2:
            return 1.0, 0.0
        A = np.vstack([est[mask], np.ones(mask.sum())]).T
        (a, b), *_ = np.linalg.lstsq(A, actual[mask], rcond=None)
        return float(a), float(b)

    scale_g, bias_g = fit_group(~is_frac)
    scale_f, bias_f = fit_group(is_frac)

    pred = np.where(
        is_frac, scale_f * est + bias_f, scale_g * est + bias_g
    )
    return pred, scale_g, bias_g, scale_f, bias_f


def main() -> None:
    samples = json.loads(GOLDEN_JSON.read_text(encoding="utf-8"))
    scripts = [s["script"] for s in samples]
    actual = np.array([s["width"] for s in samples], dtype=float)

    hangul_grid = [650, 700, 750]
    lr_grid = [1200, 1500, 1800]
    binop_grid = [0, 100, 200, 300]
    fracpad_grid = [100, 200, 400, 600]
    square_grid = [500, 650, 800]
    charpad_grid = [0, 50, 100, 150, 200]

    total = (
        len(hangul_grid) * len(lr_grid) * len(binop_grid)
        * len(fracpad_grid) * len(square_grid) * len(charpad_grid)
    )
    print(f"v4 Grid: {total} combos × 84")

    best = None
    for i, (h, lr, bsp, fp, sq, cp) in enumerate(
        product(hangul_grid, lr_grid, binop_grid, fracpad_grid, square_grid, charpad_grid)
    ):
        set_params(h, lr, bsp, fp, sq, cp)
        pred, sg, bg, sf, bf = fit_two_groups(scripts, actual)
        rel = np.abs(pred - actual) / np.maximum(actual, 1)
        mape = rel.mean()
        p95 = np.percentile(rel, 95)
        score = mape + 0.3 * p95
        if best is None or score < best["score"]:
            best = {
                "hangul_w": h, "lr_w": lr, "binop_sp": bsp,
                "frac_pad": fp, "square_w": sq, "char_pad": cp,
                "scale_general": sg, "bias_general": bg,
                "scale_fraction": sf, "bias_fraction": bf,
                "mape": float(mape), "p95": float(p95),
                "median": float(np.median(rel)), "score": float(score),
            }
        if (i + 1) % 500 == 0:
            print(f"  {i+1}/{total}  best MAPE={best['mape']*100:.2f}% p95={best['p95']*100:.2f}%")

    print("\n=== v4 최적 ===")
    assert best is not None
    for k, v in best.items():
        if isinstance(v, float):
            print(f"  {k:16s} = {v:.4f}")
        else:
            print(f"  {k:16s} = {v}")

    set_params(
        best["hangul_w"], best["lr_w"], best["binop_sp"],
        best["frac_pad"], best["square_w"], best["char_pad"],
    )
    pred, *_ = fit_two_groups(scripts, actual)
    err = np.abs(pred - actual)
    rel = err / np.maximum(actual, 1)

    print("\n=== v4 성능 ===")
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

    out = Path(__file__).parent / "best_params_v4.json"
    out.write_text(json.dumps(best, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {out}")


if __name__ == "__main__":
    main()
