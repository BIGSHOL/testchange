"""OCR 골든셋 회귀 테스트 — 채점기(scripts/ocr_eval)의 안전망.

두 부류:
  (a) **synthetic 실패모드 단위테스트**(항상 실행, 골든·anthropic 불필요): 정규화가 시험 정답을
      바꾸는 차이(지수·로만체·대소문자·표 누락·선택지 누락·타입 순서·번호)를 **삼키지 않는지**
      직접 박는다. 점수가 실제로 1.0 미만으로 떨어지고 해당 회귀 태그가 붙는지 확인.
  (b) **골든 회귀**: tests/golden_ocr/*.json + .testkit/ocr_eval 후보 캐시가 있으면 aggregate
      하여 _ocr_thresholds.json 게이트와 비교. 둘 중 하나라도 없으면 skip(시드 전엔 CI green).

실행:
    python -m pytest tests/test_ocr_golden.py -v
    python tests/test_ocr_golden.py            # unittest 모드(pytest 없이도)

이 테스트는 **stdlib 만** 쓴다(anthropic·core import 안 함) — CI·다른 PC 어디서나 돈다.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ocr_eval.metrics import aggregate, score_crop  # noqa: E402
from scripts.ocr_eval.normalize import (  # noqa: E402
    norm_latex,
    norm_text_strict,
    seq_ratio,
)

GOLDEN_DIR = ROOT / "tests" / "golden_ocr"
THRESHOLDS = ROOT / "tests" / "_ocr_thresholds.json"
EVAL_CACHE = ROOT / ".testkit" / "ocr_eval"


def _q(contents, *, number=1, score=None, choices=None):
    """간단한 단일 문항 dict 생성 헬퍼."""
    q: dict = {"number": number, "contents": contents}
    if score is not None:
        q["score"] = score
    q["choices"] = choices or []
    return {"header": "", "questions": [q]}


class NormalizationSwallowTest(unittest.TestCase):
    """⭐ 정규화가 '시험 정답을 바꾸는 차이'를 절대 흡수하지 않음을 보장."""

    def test_exponent_diff_lowers_equation_ratio(self):
        a = norm_latex(r"\frac{2^{48}}{x}")
        b = norm_latex(r"\frac{2^{6}}{x}")
        self.assertLess(seq_ratio(a, b), 1.0, "지수 48 vs 6 차이를 삼킴")

    def test_spacing_macros_are_noise(self):
        a = norm_latex(r"\frac{a}{\,b\,}")
        b = norm_latex(r"\frac{a}{b}")
        self.assertEqual(a, b, "간격 매크로(\\,)는 노이즈로 제거돼야 함")

    def test_nested_exponent_structure_preserved(self):
        # 이중 위첨자 괄호가 보존돼야 2^{2^{n}} != 2^{2n}.
        self.assertNotEqual(norm_latex("2^{2^{n}}"), norm_latex("2^{2n}"))

    def test_nested_fraction_sqrt_preserved(self):
        s = norm_latex(r"\sqrt{\frac{1}{2}}")
        self.assertIn("frac", s)
        self.assertIn("sqrt", s)
        self.assertIn("{", s)

    def test_mathrm_vs_plain_differs(self):
        a = norm_latex(r"\mathrm{A}")
        b = norm_latex("A")
        self.assertLess(seq_ratio(a, b), 1.0, "로만체 \\mathrm{A} vs 이탤릭 A 를 삼킴")

    def test_uppercase_lowercase_text_differs(self):
        # 가장 중요: strict 정규화는 대소문자를 보존(P↔p 오인이 드러나야 함).
        a = norm_text_strict("P(A)")
        b = norm_text_strict("p(A)")
        self.assertNotEqual(a, b, "strict 정규화가 P vs p 를 삼킴(.lower() 쓰면 안 됨)")
        self.assertLess(seq_ratio(a, b), 1.0)


class ScoreCropFailureModeTest(unittest.TestCase):
    """score_crop 이 각 실패 모드에서 점수를 낮추고 회귀 태그를 붙이는지."""

    def test_perfect_match_scores_one(self):
        doc = _q([{"type": "text", "value": "다음 값을 구하시오"},
                  {"type": "equation", "value": "2^{6}"}])
        s = score_crop(doc, doc, "perfect")
        self.assertEqual(s.text_ratio, 1.0)
        self.assertEqual(s.equation_ratio, 1.0)
        self.assertEqual(s.struct_score, 1.0)
        self.assertEqual(s.regressions, [])

    def test_exponent_drift_tagged(self):
        cand = _q([{"type": "equation", "value": "2^{6}"}])
        gold = _q([{"type": "equation", "value": "2^{48}"}])
        s = score_crop(cand, gold, "exp")
        self.assertLess(s.equation_ratio, 1.0)
        self.assertIn("EQUATION_DRIFT", s.regressions)

    def test_uppercase_text_drift(self):
        cand = _q([{"type": "text", "value": "확률 p(A)를 구하라"}])
        gold = _q([{"type": "text", "value": "확률 P(A)를 구하라"}])
        s = score_crop(cand, gold, "pp")
        self.assertLess(s.text_ratio, 1.0, "P vs p 차이가 text_ratio 에 드러나야 함")

    def test_missing_table_tagged(self):
        cand = _q([{"type": "text", "value": "다음 표를 보고 답하라"}])
        gold = _q([{"type": "text", "value": "다음 표를 보고 답하라"},
                   {"type": "table", "value": "",
                    "rows": [["x", "1", "2"], ["P", "0.3", "0.7"]]}])
        s = score_crop(cand, gold, "tbl")
        self.assertLess(s.table_presence_f1, 1.0)
        self.assertEqual(s.table_cell_acc, 0.0)
        self.assertIn("TABLE_MISSING", s.regressions)

    def test_table_cell_acc_partial(self):
        rows_g = [["x", "1", "2"], ["P", "0.3", "0.7"]]
        rows_c = [["x", "1", "2"], ["P", "0.3", "0.9"]]  # 셀 1개 오인
        cand = _q([{"type": "table", "value": "", "rows": rows_c}])
        gold = _q([{"type": "table", "value": "", "rows": rows_g}])
        s = score_crop(cand, gold, "tblcell")
        self.assertIsNotNone(s.table_cell_acc)
        self.assertAlmostEqual(s.table_cell_acc, 5 / 6, places=4)

    def test_missing_choice_tagged(self):
        def ch(n, v):
            return {"number": n, "contents": [{"type": "equation", "value": v}]}
        cand = _q([{"type": "text", "value": "값은?"}],
                  choices=[ch(1, "1"), ch(2, "2"), ch(3, "3"), ch(4, "4")])
        gold = _q([{"type": "text", "value": "값은?"}],
                  choices=[ch(1, "1"), ch(2, "2"), ch(3, "3"), ch(4, "4"), ch(5, "5")])
        s = score_crop(cand, gold, "choice")
        self.assertLess(s.choice_count_score, 1.0)
        self.assertIn("CHOICE_COUNT", s.regressions)

    def test_content_type_order_drift_tagged(self):
        cand = _q([{"type": "equation", "value": "x"},
                   {"type": "text", "value": "이고"}])
        gold = _q([{"type": "text", "value": "이고"},
                   {"type": "equation", "value": "x"}])
        s = score_crop(cand, gold, "order")
        self.assertLess(s.content_type_score, 1.0)
        self.assertIn("CONTENT_TYPE_DRIFT", s.regressions)

    def test_number_mismatch_tagged(self):
        cand = _q([{"type": "text", "value": "값은?"}], number=19)
        gold = _q([{"type": "text", "value": "값은?"}], number=20)
        s = score_crop(cand, gold, "num")
        self.assertEqual(s.number_score, 0.0)
        self.assertIn("NUMBER_MISMATCH", s.regressions)

    def test_box_prose_drop_tagged(self):
        prose = "독수리들이 하늘 높이 날다가 먹이를 발견하고 빠르게 내려와 사냥을 한다는 이야기"
        cand = _q([{"type": "text", "value": "다음 글을 읽고 물음에 답하시오"}])
        gold = _q([{"type": "text", "value": "다음 글을 읽고 물음에 답하시오"},
                   {"type": "text", "value": prose}])
        s = score_crop(cand, gold, "prose")
        self.assertIn("BOX_PROSE_DROP", s.regressions)

    def test_question_count_mismatch_tagged(self):
        cand = {"header": "", "questions": [
            {"number": 1, "contents": [{"type": "text", "value": "a"}], "choices": []}]}
        gold = {"header": "", "questions": [
            {"number": 1, "contents": [{"type": "text", "value": "a"}], "choices": []},
            {"number": 2, "contents": [{"type": "text", "value": "b"}], "choices": []}]}
        s = score_crop(cand, gold, "qc")
        self.assertLess(s.question_count_score, 1.0)
        self.assertIn("QUESTION_COUNT", s.regressions)


class AggregateTest(unittest.TestCase):
    """집계의 None 처리 — 표 없는 샘플은 mean_table_cell_acc 에서 제외."""

    def test_table_cell_acc_excludes_none(self):
        s1 = score_crop(_q([{"type": "text", "value": "표 없음"}]),
                        _q([{"type": "text", "value": "표 없음"}]), "a")
        rows = [["x", "1"], ["P", "1"]]
        s2 = score_crop(_q([{"type": "table", "value": "", "rows": rows}]),
                        _q([{"type": "table", "value": "", "rows": rows}]), "b")
        self.assertIsNone(s1.table_cell_acc)
        agg = aggregate([s1, s2])
        # 표 있는 샘플(s2=1.0) 만 평균에 들어가야 함.
        self.assertEqual(agg["mean_table_cell_acc"], 1.0)
        self.assertEqual(agg["n_samples"], 2)

    def test_empty_aggregate_safe(self):
        agg = aggregate([])
        self.assertEqual(agg["n_samples"], 0)


def _load_golden_samples() -> list[dict]:
    if not GOLDEN_DIR.exists():
        return []
    out = []
    for fp in sorted(GOLDEN_DIR.glob("*.json")):
        try:
            out.append(json.loads(fp.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out


class GoldenRegressionTest(unittest.TestCase):
    """실제 골든셋 회귀 게이트. 골든·후보 캐시가 없으면 skip(시드 전엔 green)."""

    def test_golden_gate(self):
        samples = _load_golden_samples()
        if not samples:
            self.skipTest("tests/golden_ocr 비어 있음 — crop_dump→golden_record 로 시딩 필요")
        if not EVAL_CACHE.exists():
            self.skipTest(".testkit/ocr_eval 후보 캐시 없음 — score_ocr.py --reocr 로 생성")

        thr_doc = json.loads(THRESHOLDS.read_text(encoding="utf-8"))
        thr = thr_doc[thr_doc["gate"]]
        scores = []
        for sample in samples:
            sid = sample.get("sample_id", "")
            src = sample.get("source", {})
            cand = _find_candidate(src)
            if cand is None:
                continue
            scores.append(score_crop(cand, sample.get("golden", {}), sid))
        if not scores:
            self.skipTest("골든에 대응하는 후보 캐시를 찾지 못함")

        agg = aggregate(scores)
        self.assertGreaterEqual(agg["mean_text_ratio"], thr["mean_text_ratio"])
        self.assertGreaterEqual(agg["mean_equation_ratio"], thr["mean_equation_ratio"])
        self.assertGreaterEqual(agg["struct_accuracy"], thr["struct_accuracy"])
        if agg["mean_table_cell_acc"] is not None:
            self.assertGreaterEqual(agg["mean_table_cell_acc"],
                                    thr["mean_table_cell_acc"])
        self.assertLessEqual(agg["regression_rate"], thr["regression_rate"])


def _find_candidate(src: dict):
    """골든 source({pdf_stem,i,ci}) 로 .testkit/ocr_eval 에서 raw 후보 JSON 찾기.

    prompt_sig 디렉터리 중 가장 최근 것의 p{i}_c{ci}.json 을 쓴다(없으면 None).
    """
    stem, i, ci = src.get("pdf_stem"), src.get("i"), src.get("ci")
    if stem is None or i is None or ci is None:
        return None
    stem_dir = EVAL_CACHE / stem
    if not stem_dir.exists():
        return None
    sig_dirs = sorted([d for d in stem_dir.iterdir() if d.is_dir()],
                      key=lambda d: d.stat().st_mtime, reverse=True)
    for sig in sig_dirs:
        fp = sig / f"p{i}_c{ci}.json"
        if fp.exists():
            try:
                return json.loads(fp.read_text(encoding="utf-8"))
            except Exception:
                return None
    return None


if __name__ == "__main__":
    unittest.main(verbosity=2)
