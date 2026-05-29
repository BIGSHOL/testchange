"""골든셋 84개로 추정기의 자유 파라미터를 최소제곱 피팅한다.

피팅 대상:
  - HANGUL_WIDTH         : 한글 음절 폭 (현재 1000)
  - LEFT_RIGHT_WIDTH     : LEFT/RIGHT 괄호 기여 폭 (현재 0, 각 발생마다)
  - BINOP_SPACE          : 이항 연산자(+,-,=) 주변 공백 추가 (현재 0, 발생마다)
  - GLOBAL_SCALE, BIAS   : 최종 선형 보정

모델:
  y_pred = GLOBAL_SCALE * base_width(params) + BIAS
  base_width(params) = _measure_hwpeq_width with (HANGUL_WIDTH, LEFT_RIGHT_WIDTH, BINOP_SPACE)

파라미터를 grid search로 탐색한 뒤 최적값을 출력.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import core.hwpx_writer as mod  # type: ignore

GOLDEN_JSON = Path(__file__).parent / "golden_equations.json"


def estimate_with_params(script: str, hangul_w: int, lr_w: int, binop_sp: int) -> float:
    """임시로 모듈 상수를 바꿔서 _estimate_equation_size를 호출."""
    mod._HWPEQ_HANGUL_WIDTH = hangul_w  # type: ignore

    # LEFT/RIGHT는 구조에서 빠져있음. 폭 가산을 위해 등장 횟수 × lr_w 를 수동 추가.
    n_left_right = len(re.findall(r"\b(LEFT|RIGHT)\b", script))
    n_binop = len(re.findall(r"[=+\-<>]", script))

    w, _h = mod._estimate_equation_size(script)  # type: ignore
    w += n_left_right * lr_w
    w += n_binop * binop_sp
    return w


def main() -> None:
    samples = json.loads(GOLDEN_JSON.read_text(encoding="utf-8"))
    scripts = [s["script"] for s in samples]
    actual = np.array([s["width"] for s in samples], dtype=float)

    # ── Grid search on (hangul_w, lr_w, binop_sp) ──
    best = None
    print("Grid search over (HANGUL_WIDTH, LEFT_RIGHT_EXTRA, BINOP_SPACE)...")
    for hangul_w in [700, 800, 850, 900, 950, 1000]:
        for lr_w in [0, 200, 400, 600, 800, 1000]:
            for binop_sp in [0, 100, 200, 300, 400]:
                est = np.array(
                    [estimate_with_params(s, hangul_w, lr_w, binop_sp) for s in scripts]
                )
                # Simple linear fit: actual = a*est + b
                A = np.vstack([est, np.ones(len(est))]).T
                (a, b), res, *_ = np.linalg.lstsq(A, actual, rcond=None)
                pred = a * est + b
                mape = np.mean(np.abs(pred - actual) / np.maximum(actual, 1))
                p95 = np.percentile(np.abs(pred - actual) / np.maximum(actual, 1), 95)
                score = mape + 0.3 * p95
                if best is None or score < best["score"]:
                    best = {
                        "hangul_w": hangul_w,
                        "lr_w": lr_w,
                        "binop_sp": binop_sp,
                        "scale": a,
                        "bias": b,
                        "mape": mape,
                        "p95": p95,
                        "score": score,
                    }

    print("\n=== 최적 파라미터 ===")
    assert best is not None
    for k, v in best.items():
        if isinstance(v, float):
            print(f"  {k:12s} = {v:.4f}")
        else:
            print(f"  {k:12s} = {v}")

    # 최적으로 재측정 상세
    est = np.array(
        [
            estimate_with_params(
                s, best["hangul_w"], best["lr_w"], best["binop_sp"]
            )
            for s in scripts
        ]
    )
    pred = best["scale"] * est + best["bias"]
    err = np.abs(pred - actual)
    rel = err / np.maximum(actual, 1)

    print("\n=== 최적 파라미터 적용 시 성능 ===")
    print(f"  width MAE    = {err.mean():.0f}")
    print(f"  width MAPE   = {rel.mean()*100:.2f}%")
    print(f"  width median = {np.median(rel)*100:.2f}%")
    print(f"  width p95    = {np.percentile(rel, 95)*100:.2f}%")
    print(f"  width max    = {err.max():.0f}  ({rel.max()*100:.1f}%)")

    # 최악 케이스
    worst_idx = np.argsort(-err)[:10]
    print("\n── 최악 케이스 Top 10 ──")
    for i in worst_idx:
        print(
            f"  actual={int(actual[i]):6d}  pred={int(pred[i]):6d}  "
            f"err={int(pred[i]-actual[i]):+6d} ({(pred[i]-actual[i])/actual[i]*100:+.1f}%)  "
            f"{scripts[i][:55]!r}"
        )

    # JSON으로 저장 (최종 구현에 투입)
    out = Path(__file__).parent / "best_params.json"
    out.write_text(json.dumps(best, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {out}")


if __name__ == "__main__":
    main()
