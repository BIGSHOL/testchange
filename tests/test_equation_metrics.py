"""수식 크기 추정기 회귀 테스트.

정답 HWPX(hwpx_조암/Contents/section0.xml)에서 84개 수식의 실측 (script, width, height)를
골든셋으로 삼아 `_estimate_equation_size`가 일정 수준 이상으로 정확한지 검증.

실행:
    python -m pytest tests/test_equation_metrics.py -v
    python tests/test_equation_metrics.py   # unittest 모드 (pytest 없이도 가능)
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.hwpx_writer import _estimate_equation_size  # type: ignore

GOLDEN = ROOT / "scripts" / "tune_equation" / "golden_equations.json"


def _load_golden() -> list[dict]:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


class EquationSizeRegressionTest(unittest.TestCase):
    """골든셋 84개 정답 수식에 대한 추정 정확도 회귀 방지."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.samples = _load_golden()
        cls.errors_rel = []
        cls.height_ok = 0
        for s in cls.samples:
            est_w, est_h = _estimate_equation_size(s["script"])
            cls.errors_rel.append(abs(est_w - s["width"]) / max(s["width"], 1))
            if est_h == s["height"]:
                cls.height_ok += 1

    def test_golden_dataset_loaded(self) -> None:
        self.assertEqual(len(self.samples), 84, "골든셋 크기가 변경됨 — extract_golden.py 재실행 필요")

    def test_height_accuracy_ge_95pct(self) -> None:
        """height 정확도 95% 이상. 정답은 1200 또는 2400 이진값."""
        acc = self.height_ok / len(self.samples)
        self.assertGreaterEqual(
            acc, 0.95, f"height 정확도 {acc*100:.1f}% (목표 95% 이상)"
        )

    def test_width_mape_le_8pct(self) -> None:
        """width 평균 상대 오차 8% 이하 (v5 튠 달성: 6.54%)."""
        mape = sum(self.errors_rel) / len(self.errors_rel)
        self.assertLessEqual(mape, 0.08, f"width MAPE {mape*100:.2f}% (목표 8% 이하)")

    def test_width_median_le_6pct(self) -> None:
        """width 중간값 오차 6% 이하 (v5 튠 달성: 4.18%)."""
        sorted_err = sorted(self.errors_rel)
        median = sorted_err[len(sorted_err) // 2]
        self.assertLessEqual(
            median, 0.06, f"width median 오차 {median*100:.2f}% (목표 6% 이하)"
        )

    def test_width_p95_le_20pct(self) -> None:
        """width 95 백분위 오차 20% 이하 (v5 튠 달성: 18.59%)."""
        sorted_err = sorted(self.errors_rel)
        p95 = sorted_err[int(len(sorted_err) * 0.95)]
        self.assertLessEqual(p95, 0.20, f"width p95 오차 {p95*100:.2f}% (목표 20% 이하)")

    def test_no_zero_width(self) -> None:
        """어떤 수식도 width=0을 반환하지 않아야 한다 (옆 글자 겹침의 주원인)."""
        zero_count = 0
        for s in self.samples:
            est_w, _ = _estimate_equation_size(s["script"])
            if est_w <= 0:
                zero_count += 1
        self.assertEqual(zero_count, 0, f"{zero_count}개 수식이 zero-width를 반환")

    def test_width_minimum_bound(self) -> None:
        """모든 수식 width >= 400 HWPUNIT."""
        for s in self.samples:
            est_w, _ = _estimate_equation_size(s["script"])
            self.assertGreaterEqual(est_w, 400, f"width {est_w} < 400: {s['script']!r}")


class IndividualCasesTest(unittest.TestCase):
    """자주 쓰이는 수식 패턴의 개별 회귀 테스트."""

    def test_simple_fraction_returns_2400_height(self) -> None:
        _, h = _estimate_equation_size("{a} over {b}")
        self.assertEqual(h, 2400)

    def test_linear_expression_returns_1200_height(self) -> None:
        _, h = _estimate_equation_size("x + y + z")
        self.assertEqual(h, 1200)

    def test_sqrt_returns_2400_height(self) -> None:
        _, h = _estimate_equation_size("sqrt {x+1}")
        self.assertEqual(h, 2400)

    def test_sum_returns_2400_height(self) -> None:
        _, h = _estimate_equation_size("SUM _{i=1} ^{n} a _{i}")
        self.assertEqual(h, 2400)

    def test_hangul_included_does_not_crash(self) -> None:
        w, _ = _estimate_equation_size('"의 곱의 계수의 합"을 a')
        self.assertGreater(w, 0)

    def test_square_keyword_recognized(self) -> None:
        """SQUARE는 심볼 키워드로 처리되어야 한다 (과거 버그: 6글자로 분해)."""
        w, _ = _estimate_equation_size("SQUARE")
        # 정답 샘플에서 SQUARE 단독의 width는 약 850 hwpunit.
        # 6글자 분해 시 4000+가 나온다.
        self.assertLess(w, 2500, f"SQUARE가 6글자로 분해된 것으로 보임 (width={w})")


if __name__ == "__main__":
    unittest.main(verbosity=2)
