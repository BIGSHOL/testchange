# -*- coding: utf-8 -*-
"""FigureSpec 자동 정리(`figure_generator._repair_figure_spec`) 회귀 — 2026-09-11.

웹 실사용 스펙 77개(Supabase api_cache 'figure-svg') 실측에서 54개(70%)가 모델이 붙인
장식 칸(`pos`·`dashed`·`style` …)이나 범위 밖 값(치수 `side`, 진한 채색) 때문에 컴파일에
실패했다. **그려지는 결과가 같은 것만** 벗기고, 뜻을 실어 나를 수 있는 칸은 여전히
실패해야 한다 — 그래서 대부분의 시험은 「정리된 스펙 = 처음부터 깨끗하게 쓴 스펙」을
**바이트 단위로** 비교한다.

    python tests/test_figure_spec_repair.py
    python -m pytest tests/test_figure_spec_repair.py -v
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.figure_generator import (  # noqa: E402
    _SPEC_FALLBACK_FILL,
    _SPEC_SNAP_TOL,
    _compile_structured_candidate,
    _inventory_key,
)


def _triangle(**sections) -> dict:
    spec = {
        "version": 2,
        "points": {"A": [0, 0], "B": [160, 0], "C": [80, 120]},
        "segments": {"AB": ["A", "B"], "BC": ["B", "C"], "CA": ["C", "A"]},
        "labels": {"A": "A", "B": "B", "C": "C"},
    }
    spec.update(sections)
    return spec


def _run(spec: dict, desc: str = "삼각형 A B C") -> tuple[str | None, str | None]:
    return _compile_structured_candidate({"figure_spec": spec, "desc": desc, "svg": ""})


class DecorativeFieldRepairTest(unittest.TestCase):
    def assertSameDrawing(self, dirty: dict, clean: dict, desc: str = "삼각형 A B C") -> None:
        clean_svg, clean_issue = _run(clean, desc)
        self.assertIsNone(clean_issue, "기준 스펙부터 그려져야 비교가 뜻이 있다")
        dirty_svg, dirty_issue = _run(dirty, desc)
        self.assertIsNone(dirty_issue)
        self.assertEqual(dirty_svg, clean_svg)

    def test_label_position_hint_is_stripped(self) -> None:
        labels = {"B": "B", "C": "C"}
        self.assertSameDrawing(
            _triangle(labels={"A": {"text": "A", "pos": "top-left"}, **labels}),
            _triangle(labels={"A": {"text": "A"}, **labels}))

    def test_caller_payload_is_not_mutated(self) -> None:
        spec = _triangle(labels={"A": {"text": "A", "pos": "top"}, "B": "B", "C": "C"})
        before = copy.deepcopy(spec)
        _run(spec)
        self.assertEqual(spec, before)

    def test_dimension_dashed_and_style_are_stripped(self) -> None:
        desc = "삼각형 A B C, AB = 8 cm"
        base = {"points": ["A", "B"], "label": "8 cm"}
        self.assertSameDrawing(
            _triangle(dimensions={"dimAB": {**base, "dashed": True, "style": "curve"}}),
            _triangle(dimensions={"dimAB": dict(base)}), desc)

    def test_invalid_dimension_side_falls_back_to_default(self) -> None:
        desc = "삼각형 A B C, AB = 8 cm"
        base = {"points": ["A", "B"], "label": "8 cm"}
        self.assertSameDrawing(
            _triangle(dimensions={"dimAB": {**base, "side": "below"}}),
            _triangle(dimensions={"dimAB": dict(base)}), desc)

    def test_non_positive_dimension_offset_is_dropped(self) -> None:
        desc = "삼각형 A B C, AB = 8 cm"
        base = {"points": ["A", "B"], "label": "8 cm"}
        self.assertSameDrawing(
            _triangle(dimensions={"dimAB": {**base, "offset": -10}}),
            _triangle(dimensions={"dimAB": dict(base)}), desc)

    def test_angle_ticks_become_arcs(self) -> None:
        base = {"vertex": "A", "points": ["B", "C"]}
        self.assertSameDrawing(
            _triangle(angles={"angA": {**base, "ticks": 2}}),
            _triangle(angles={"angA": {**base, "arcs": 2}}))

    def test_dark_region_fill_is_lightened(self) -> None:
        boundary = [{"seg": ["A", "B"]}, {"seg": ["B", "C"]}, {"seg": ["C", "A"]}]
        svg, issue = _run(_triangle(regions={"shade": {"boundary": boundary, "fill": "#333333"}}))
        self.assertIsNone(issue)
        self.assertIn(_SPEC_FALLBACK_FILL, (svg or "").lower())

    def test_meaningful_unknown_field_still_fails(self) -> None:
        # 선분에 붙은 `label` 은 길이 값일 수 있다 — 벗기면 값이 조용히 사라진다.
        spec = _triangle(segments={"AB": {"points": ["A", "B"], "label": "5 cm"},
                                   "BC": ["B", "C"], "CA": ["C", "A"]})
        svg, issue = _run(spec)
        self.assertIsNone(svg)
        self.assertIn("label", issue or "")

    def test_mixed_unknown_fields_are_not_partially_stripped(self) -> None:
        spec = _triangle(labels={"A": {"text": "A", "pos": "top", "value": "3"},
                                 "B": "B", "C": "C"})
        svg, issue = _run(spec)
        self.assertIsNone(svg)
        self.assertIn("value", issue or "")


class RaySnapTest(unittest.TestCase):
    """각의 변 판정이 좌표 어림(모델)에 못 견디던 자리 — 작은 빗나감만 붙인다."""

    @staticmethod
    def _spec(off: float) -> dict:
        return {
            "version": 2,
            "points": {"A": [0, 0], "B": [200, 0], "C": [100, 120], "D": [100, off]},
            "segments": {"AB": ["A", "B"], "BC": ["B", "C"], "CA": ["C", "A"],
                         "CD": ["C", "D"]},
            "labels": {"A": "A", "B": "B", "C": "C", "D": "D"},
            "angles": {"angD": {"vertex": "D", "points": ["B", "C"], "right": True}},
        }

    def test_point_within_tolerance_is_snapped_onto_the_segment(self) -> None:
        svg, issue = _run(self._spec(0.5), "삼각형 A B C 와 점 D")
        self.assertIsNone(issue)
        self.assertIsNotNone(svg)

    def test_vertex_at_two_segment_crossing_is_snapped_to_the_crossing(self) -> None:
        # 실측 #061: 꼭짓점 E 가 OD·IC 의 교점인데 둘 다에서 조금씩 빗나가 있었다.
        # 한 선분에만 붙이면 다른 선분에서 떨어져 두 오류가 번갈아 났다.
        spec = {
            "version": 2,
            "points": {"O": [0, 0], "D": [100, 100], "I": [0, 100], "C": [100, 0],
                       "E": [50.6, 49.7]},
            "segments": {"OD": ["O", "D"], "IC": ["I", "C"]},
            "labels": {"O": "O", "D": "D", "I": "I", "C": "C", "E": "E"},
            "angles": {"angE": {"vertex": "E", "points": ["D", "C"], "arcs": 1}},
        }
        svg, issue = _run(spec, "선분 O D 와 선분 I C 가 점 E 에서 만난다")
        self.assertIsNone(issue)
        self.assertIsNotNone(svg)

    def test_point_beyond_tolerance_still_fails(self) -> None:
        svg, issue = _run(self._spec(_SPEC_SNAP_TOL + 2.0), "삼각형 A B C 와 점 D")
        self.assertIsNone(svg)
        self.assertIsNotNone(issue)


class InventoryKeyTest(unittest.TestCase):
    def test_degree_words_match_the_symbol(self) -> None:
        self.assertIn(_inventory_key("35°"), _inventory_key("angle A is 35 degrees"))

    def test_sqrt_spellings_match(self) -> None:
        self.assertIn(_inventory_key("√11"), _inventory_key(r"BC has length \sqrt{11}"))
        self.assertIn(_inventory_key("2√2"), _inventory_key("AD = 2 sqrt(2)"))

    def test_spacing_is_ignored(self) -> None:
        self.assertIn(_inventory_key("12 cm"), _inventory_key("AB 는 12cm"))

    def test_worded_degree_transcript_accepts_the_angle_label(self) -> None:
        spec = _triangle(angles={"angA": {"vertex": "A", "points": ["B", "C"],
                                          "label": "35°"}})
        svg, issue = _run(spec, "삼각형 A B C, 각 A 는 35 degrees")
        self.assertIsNone(issue)
        self.assertIsNotNone(svg)

    def test_label_absent_from_transcript_is_still_rejected(self) -> None:
        spec = _triangle(angles={"angA": {"vertex": "A", "points": ["B", "C"],
                                          "label": "35°"}})
        svg, issue = _run(spec, "삼각형 A B C")
        self.assertIsNone(svg)
        self.assertIn("35°", issue or "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
