"""골든셋 84개로 파라미터를 재피팅 (v2).

v1 대비 튜닝 차원 확장:
  - HANGUL_WIDTH          : 한글 음절 폭
  - LEFT_RIGHT_EXTRA      : LEFT/RIGHT 괄호 가산
  - BINOP_SPACE           : 이항 연산자 주변 여백
  - FRAC_PADDING          : 분수선 양쪽 여백
  - SQUARE_WIDTH          : SQUARE 기호 폭 (v1 분석에서 +27.59% 과대추정)
  - GLOBAL_SCALE, BIAS    : 최종 선형 보정 (최소제곱)

grid search 후보군은 각 파라미터의 v1 피팅 결과 ±50% 범위로 설정.
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
) -> float:
    """모듈 상수를 임시로 바꿔 _estimate_equation_size 호출."""
    mod._HWPEQ_HANGUL_WIDTH = hangul_w  # type: ignore
    mod._HWPEQ_LEFT_RIGHT_EXTRA = lr_w  # type: ignore
    mod._HWPEQ_BINOP_SPACE = binop_sp  # type: ignore
    mod._HWPEQ_FRAC_PADDING = frac_pad  # type: ignore
    mod._HWPEQ_KEYWORD_WIDTHS["SQUARE"] = square_w  # type: ignore

    # 선형 보정은 이 함수 바깥에서 재피팅하므로, 여기서는 SCALE=1, BIAS=0으로 고정.
    mod._HWPEQ_GLOBAL_SCALE = 1.0  # type: ignore
    mod._HWPEQ_GLOBAL_BIAS = 0  # type: ignore

    w, _h = mod._estimate_equation_size(script)
    return float(w)


def main() -> None:
    samples = json.loads(GOLDEN_JSON.read_text(encoding="utf-8"))
    scripts = [s["script"] for s in samples]
    actual = np.array([s["width"] for s in samples], dtype=float)

    hangul_grid = [650, 700, 750]
    lr_grid = [800, 1000, 1200, 1500, 1800]
    binop_grid = [0, 100, 200, 300]
    fracpad_grid = [200, 400, 600, 800]
    square_grid = [500, 600, 700, 800, 850]

    total = (
        len(hangul_grid) * len(lr_grid) * len(binop_grid)
        * len(fracpad_grid) * len(square_grid)
    )
    print(f"Grid: {total} combinations × 84 samples")

    best = None
    for i, (h, lr, bsp, fp, sq) in enumerate(
        product(hangul_grid, lr_grid, binop_grid, fracpad_grid, square_grid)
    ):
        est = np.array([estimate_with_params(s, h, lr, bsp, fp, sq) for s in scripts])
        # Linear fit: actual = a*est + b
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
                "scale": float(a),
                "bias": float(b),
                "mape": float(mape),
                "p95": float(p95),
                "median": float(np.median(rel)),
                "score": float(score),
            }
        if (i + 1) % 200 == 0:
            print(f"  {i+1}/{total}  cur_best MAPE={best['mape']*100:.2f}% p95={best['p95']*100:.2f}%")

    print("\n=== 최적 파라미터 ===")
    assert best is not None
    for k, v in best.items():
        if isinstance(v, float):
            print(f"  {k:12s} = {v:.4f}")
        else:
            print(f"  {k:12s} = {v}")

    # 상세 재측정
    est = np.array(
        [
            estimate_with_params(
                s,
                best["hangul_w"],
                best["lr_w"],
                best["binop_sp"],
                best["frac_pad"],
                best["square_w"],
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

    # 최악 케이스 Top 10
    worst = np.argsort(-rel)[:10]
    print("\n── 최악 케이스 Top 10 ──")
    for i in worst:
        sign = "+" if pred[i] >= actual[i] else ""
        print(
            f"  actual={int(actual[i]):6d}  pred={int(pred[i]):6d}  "
            f"rel={sign}{(pred[i]-actual[i])/actual[i]*100:+.1f}%  "
            f"{scripts[i][:55]!r}"
        )

    out = Path(__file__).parent / "best_params_v2.json"
    out.write_text(json.dumps(best, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {out}")


if __name__ == "__main__":
    main()
