"""OCR 실패채굴(④)·위험토큰 감사(②) 단위테스트 — 합성쌍, 항상 실행(API·골든 불필요).

`test_ocr_golden.py` 의 골격을 모사한다. 우리가 실제로 데인 실패모드(홀↔짝·지수·소수자릿수·
부등호 방향)를 합성쌍으로 직접 박아:
  - failures.diff_crop 가 올바른 category·Mismatch 를 뽑는지(④ 채굴의 1차 검증),
  - risk_tokens.audit_blocks/risk_tokens_in 이 위험토큰을 잡고 severity 필터가 low 노이즈를
    거르는지(② 감사 검증)
를 확인한다. stdlib 만 쓴다(anthropic·core import 안 함) — CI·다른 PC 어디서나 돈다.

실행:
    python tests/test_ocr_failures.py            # unittest 모드
    python -m pytest tests/test_ocr_failures.py -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ocr_eval.failures import cluster_by_category, diff_crop  # noqa: E402
from scripts.ocr_eval.risk_tokens import (  # noqa: E402
    audit_blocks,
    categorize,
    risk_tokens_in,
)


def _q(contents, *, number=1, choices=None):
    q: dict = {"number": number, "contents": contents, "choices": choices or []}
    return {"header": "", "questions": [q]}


def _cats(mismatches):
    return {m.category for m in mismatches}


class CategorizeTest(unittest.TestCase):
    """categorize 가 불일치 한 쌍을 올바른 위험류로 태깅."""

    def test_hol_jjak_swap(self):
        self.assertEqual(categorize("홀수", "짝수"), "HOL_JJAK")
        self.assertEqual(categorize("짝수이다", "홀수이다"), "HOL_JJAK")

    def test_decimal_digits(self):
        self.assertEqual(categorize("172.44", "172.4"), "DECIMAL")

    def test_inequality_direction(self):
        self.assertEqual(categorize("a<b", "a>b"), "INEQUALITY")

    def test_exponent_number(self):
        self.assertEqual(categorize("2^{48}", "2^{6}"), "EXPONENT")

    def test_confidence_interval(self):
        self.assertEqual(categorize("신뢰구간은", "구간은"), "CONFIDENCE_INTERVAL")

    def test_no_diff_returns_none(self):
        self.assertIsNone(categorize("같다", "같다"))


class DiffCropTest(unittest.TestCase):
    """diff_crop 이 합성 후보↔골든에서 구체 Mismatch 를 채굴."""

    def test_exponent_mined(self):
        cand = _q([{"type": "equation", "value": "2^{6}"}])
        gold = _q([{"type": "equation", "value": "2^{48}"}])
        ms = diff_crop(cand, gold, "exp")
        self.assertTrue(ms, "지수 차이를 채굴하지 못함")
        self.assertIn("EXPONENT", _cats(ms))
        self.assertTrue(all(m.kind == "equation" for m in ms if m.category == "EXPONENT"))

    def test_hol_jjak_mined(self):
        cand = _q([{"type": "text", "value": "이 수는 짝수이다"}])
        gold = _q([{"type": "text", "value": "이 수는 홀수이다"}])
        ms = diff_crop(cand, gold, "hj")
        self.assertIn("HOL_JJAK", _cats(ms))

    def test_decimal_mined(self):
        cand = _q([{"type": "text", "value": "평균은 172.4 이다"}])
        gold = _q([{"type": "text", "value": "평균은 172.44 이다"}])
        ms = diff_crop(cand, gold, "dec")
        self.assertIn("DECIMAL", _cats(ms))

    def test_inequality_mined(self):
        cand = _q([{"type": "equation", "value": "f(12)>f(22)"}])
        gold = _q([{"type": "equation", "value": "f(12)<f(24)"}])
        ms = diff_crop(cand, gold, "ineq")
        # 부등호 방향 또는 숫자(22 vs 24) 둘 중 하나는 반드시 잡혀야 함.
        self.assertTrue({"INEQUALITY", "NUMBER"} & _cats(ms))

    def test_table_missing_structure(self):
        cand = _q([{"type": "text", "value": "표를 보고 답하라"}])
        gold = _q([{"type": "text", "value": "표를 보고 답하라"},
                   {"type": "table", "value": "", "rows": [["x", "1"], ["P", "1"]]}])
        ms = diff_crop(cand, gold, "tbl")
        self.assertIn("TABLE_COUNT", _cats(ms))
        self.assertTrue(any(m.kind == "structure" for m in ms))

    def test_choice_count_structure(self):
        def ch(n, v):
            return {"number": n, "contents": [{"type": "equation", "value": v}]}
        cand = _q([{"type": "text", "value": "값은?"}],
                  choices=[ch(1, "1"), ch(2, "2"), ch(3, "3"), ch(4, "4")])
        gold = _q([{"type": "text", "value": "값은?"}],
                  choices=[ch(1, "1"), ch(2, "2"), ch(3, "3"), ch(4, "4"), ch(5, "5")])
        ms = diff_crop(cand, gold, "ch")
        self.assertIn("CHOICE_COUNT", _cats(ms))

    def test_perfect_match_no_mismatch(self):
        doc = _q([{"type": "text", "value": "다음 값을 구하시오"},
                  {"type": "equation", "value": "2^{6}"}])
        self.assertEqual(diff_crop(doc, doc, "perfect"), [])

    def test_cluster_groups_by_category(self):
        cand = _q([{"type": "text", "value": "짝수이고 평균 172.4"}])
        gold = _q([{"type": "text", "value": "홀수이고 평균 172.44"}])
        clusters = cluster_by_category(diff_crop(cand, gold, "multi"))
        self.assertIn("HOL_JJAK", clusters)
        self.assertIn("DECIMAL", clusters)


class RiskTokenAuditTest(unittest.TestCase):
    """audit_blocks/risk_tokens_in — 단일 OCR 출력 감사 + severity 필터."""

    def test_hol_jjak_flagged_high(self):
        flags = audit_blocks(_q([{"type": "text", "value": "짝수의 개수"}])["questions"])
        self.assertTrue(any(f["category"] == "HOL_JJAK" and f["severity"] == "high"
                            for f in flags))

    def test_decimal_flagged(self):
        flags = audit_blocks(_q([{"type": "text", "value": "값 172.44"}])["questions"])
        self.assertTrue(any(f["category"] == "DECIMAL" for f in flags))

    def test_confidence_interval_flagged(self):
        flags = audit_blocks(
            _q([{"type": "text", "value": "신뢰구간을 구하시오"}])["questions"])
        self.assertTrue(any(f["category"] == "CONFIDENCE_INTERVAL" for f in flags))

    def test_plain_number_is_low_noise_filtered(self):
        # 긴 정수는 low → 기본 medium 감사에서 빠져야(시끄럽지 않게).
        text = "전체 12345 명 중"
        self.assertEqual(risk_tokens_in(text, "medium"), [])
        self.assertTrue(any(c == "NUMBER" for c, _, _ in risk_tokens_in(text, "low")))

    def test_percent_low_filtered_by_default(self):
        self.assertEqual(
            [c for c, _, _ in risk_tokens_in("정답률 80%", "medium")
             if c == "PERCENT"], [])
        self.assertTrue(
            any(c == "PERCENT" for c, _, _ in risk_tokens_in("정답률 80%", "low")))

    def test_figure_empty_value_flagged(self):
        q = {"number": 3, "contents": [{"type": "figure", "value": ""}], "choices": []}
        flags = audit_blocks([q])
        self.assertTrue(any(f["category"] == "FIGURE_HANDWRITING" for f in flags))


if __name__ == "__main__":
    unittest.main(verbosity=2)
