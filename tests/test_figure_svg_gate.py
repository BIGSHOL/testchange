# -*- coding: utf-8 -*-
"""figure_svg 방어장치 회귀 — 이스케이프 이중적용 차단·검산 게이트·각/호 표시.

2026-08-13 오성중 13그림 원본 1:1 전수 대조에서 드러난 결함군을 **구조적으로**
막으려고 넣은 장치들이다. 하나라도 풀리면 같은 결함이 조용히 되돌아온다:

* 이중 escape → 화면에 '&lt; 보 기 &gt;' 리터럴 인쇄(q16 실측)
* 라벨값↔작도 모순 → lint 는 통과하는데 학생이 틀린 그림으로 푼다(q2·s2·운암중 s4)
* 넓은 호의 치수선이 원 안으로 침범(s2 13π 130° 실측)
"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.figure_svg import (  # noqa: E402
    SVGTextRun, angle_mark, arc_measured, arc_tick, bisect_pt, circle_pt,
    dim_label, eq_angle, halo_angle, halo_text, txt, unverified, verify_figure,
)


class EscapeGuardTest(unittest.TestCase):
    """이미 escape 된 문자열이 다시 들어오면 입구에서 막는다."""

    def test_pre_escaped_entity_is_rejected(self):
        for call in (
            lambda: txt(0, 0, "&lt; 보 기 &gt;"),
            lambda: dim_label(0, 0, 10, 0, 5, "&amp;"),
            lambda: halo_text(0, 0, runs=[SVGTextRun("&lt;x&gt;")]),
        ):
            with self.assertRaises(ValueError):
                call()

    def test_raw_text_is_escaped_exactly_once(self):
        self.assertIn("&lt;보기&gt;", txt(0, 0, "<보기>"))
        self.assertNotIn("&amp;lt;", txt(0, 0, "<보기>"))

    def test_bare_ampersand_still_works(self):
        self.assertIn("A&amp;B", txt(0, 0, "A&B"))

    def test_halo_text_rejects_raw_angle_brackets_but_runs_work(self):
        with self.assertRaises(ValueError):
            halo_text(0, 0, "<보기>")
        self.assertIn("&lt;보기&gt;", halo_text(0, 0, runs=[SVGTextRun("<보기>")]))

    def test_halo_text_still_accepts_tspan_markup(self):
        out = halo_text(0, 0, '<tspan font-style="italic">x</tspan>°')
        self.assertIn("<tspan", out)

    def test_halo_text_requires_exactly_one_of_content_or_runs(self):
        with self.assertRaises(ValueError):
            halo_text(0, 0, "x", runs=[SVGTextRun("y")])
        with self.assertRaises(ValueError):
            halo_text(0, 0)


class VerifyGateTest(unittest.TestCase):
    """라벨에 적은 값과 실제 작도가 어긋나면 빌드를 세운다."""

    def test_length_ratio_mismatch_fails(self):
        # 15:17 이라 적고 1:3 으로 그린 경우(오성중 q2 원래 상태)
        with self.assertRaises(ValueError):
            verify_figure("bad-len", lengths=[(15, (0, 0), (30, 0)),
                                              (17, (30, 0), (120, 0))])

    def test_length_ratio_match_passes(self):
        verify_figure("ok-len", lengths=[(15, (0, 0), (75, 0)),
                                         (17, (75, 0), (160, 0))])

    def test_arc_ratio_mismatch_fails(self):
        with self.assertRaises(ValueError):
            verify_figure("bad-arc", arcs=[(9 * math.pi, 0, 0, 100, 0, 70),
                                           (13 * math.pi, 0, 0, 100, 90, 140)])

    def test_arc_ratio_match_passes(self):
        verify_figure("ok-arc", arcs=[(9 * math.pi, 0, 0, 100, 0, 90),
                                      (13 * math.pi, 0, 0, 100, 90, 220)])

    def test_angle_mismatch_fails(self):
        drawn36 = (100 * math.cos(math.radians(36)), -100 * math.sin(math.radians(36)))
        with self.assertRaises(ValueError):
            verify_figure("bad-ang", angles=[(54, (0, 0), (100, 0), drawn36)])

    def test_angle_match_passes(self):
        drawn54 = (100 * math.cos(math.radians(54)), -100 * math.sin(math.radians(54)))
        verify_figure("ok-ang", angles=[(54, (0, 0), (100, 0), drawn54)])

    def test_lengths_and_arcs_share_one_scale(self):
        verify_figure("ok-mix", lengths=[(10, (0, 0), (50, 0))],
                      arcs=[(20, 0, 0, 100, 0, 57.2957795)])

    def test_unverified_reports_only_figures_with_measure_labels(self):
        verify_figure("checked", lengths=[(5, (0, 0), (50, 0))])
        svgs = {
            "checked": '<svg><text x="0" y="0">15cm</text></svg>',
            "with-label": '<svg><text x="0" y="0">24cm</text></svg>',
            "with-angle": '<svg><text x="0" y="0">54°</text></svg>',
            "no-label": '<svg><text x="0" y="0">A</text></svg>',
        }
        self.assertEqual(sorted(unverified(svgs)), ["with-angle", "with-label"])


class ArcMeasuredTest(unittest.TestCase):
    """호 치수선은 각도가 얼마든 **원 밖**에 머물러야 한다."""

    def _points(self, fragment):
        d = fragment.split('d="', 1)[1].split('"', 1)[0]
        nums = [float(t) for t in d.replace("M", " ").replace("L", " ").split()]
        return list(zip(nums[0::2], nums[1::2]))

    def test_wide_arc_never_enters_the_circle(self):
        # s2 의 13π 는 130° — 2차 베지에 하나로 그리면 중간이 원 안으로 들어갔다.
        frag = arc_measured(150, 150, 118, -134, -4, txt="13πcm")
        for x, y in self._points(frag):
            self.assertGreaterEqual(math.hypot(x - 150, y - 150), 118.0)

    def test_narrow_arc_also_stays_outside(self):
        frag = arc_measured(150, 150, 118, 96, 6, txt="9πcm")
        for x, y in self._points(frag):
            self.assertGreaterEqual(math.hypot(x - 150, y - 150), 118.0)

    def test_ends_hug_the_circle_and_middle_bows_out(self):
        cx, cy, r = 0.0, 0.0, 100.0
        pts = self._points(arc_measured(cx, cy, r, 0, 90, txt="9πcm"))
        ends = [math.hypot(*pts[0]), math.hypot(*pts[-1])]
        mid = math.hypot(*pts[len(pts) // 2])
        for e in ends:
            self.assertLess(e - r, 5.0)          # 끝은 원에 붙는다
        self.assertGreater(mid - r, 12.0)        # 가운데는 벌어진다

    def test_requires_exactly_one_of_txt_or_runs(self):
        with self.assertRaises(ValueError):
            arc_measured(0, 0, 50, 0, 90)
        with self.assertRaises(ValueError):
            arc_measured(0, 0, 50, 0, 90, txt="a", runs=[SVGTextRun("b")])


class AngleAndArcMarkTest(unittest.TestCase):
    def test_angle_mark_is_dashed_by_default(self):
        self.assertIn("stroke-dasharray", angle_mark(0, 0, (10, 0), (0, -10)))

    def test_angle_mark_solid_when_requested(self):
        self.assertNotIn("dasharray",
                         angle_mark(0, 0, (10, 0), (0, -10), dash=False))

    def test_eq_angle_draws_n_solid_arcs(self):
        out = eq_angle(0, 0, (10, 0), (0, -10), n=2)
        self.assertEqual(out.count("<path"), 2)
        self.assertNotIn("dasharray", out)

    def test_arc_tick_sits_across_the_circle_at_the_arc_midpoint(self):
        frag = arc_tick(0, 0, 100, 0, 90, ln=8)
        self.assertEqual(frag.count("<line"), 1)
        vals = {k: float(frag.split(f'{k}="', 1)[1].split('"', 1)[0])
                for k in ("x1", "y1", "x2", "y2")}
        inner = math.hypot(vals["x1"], vals["y1"])
        outer = math.hypot(vals["x2"], vals["y2"])
        # 좌표는 소수 1자리로 찍히므로 반올림 오차를 허용한다
        self.assertAlmostEqual(inner, 96.0, delta=0.2)
        self.assertAlmostEqual(outer, 104.0, delta=0.2)
        # 45° 방향(호의 중점)
        self.assertAlmostEqual(math.degrees(math.atan2(-vals["y2"], vals["x2"])),
                               45.0, places=1)

    def test_bisect_pt_is_on_the_angle_bisector(self):
        p = bisect_pt(0, 0, (10, 0), (0, -10), 50)
        self.assertAlmostEqual(math.degrees(math.atan2(-p[1], p[0])), 45.0, places=6)
        self.assertAlmostEqual(math.hypot(*p), 50.0, places=6)

    def test_halo_angle_places_label_on_the_bisector(self):
        out = halo_angle(0, 0, (10, 0), (0, -10), 50, "54°", 12)
        x = float(out.split('x="', 1)[1].split('"', 1)[0])
        self.assertAlmostEqual(x, 50 * math.cos(math.radians(45)), places=1)

    def test_circle_pt_matches_bisect_convention(self):
        self.assertAlmostEqual(circle_pt(0, 0, 90, 10)[1], -10.0, places=6)


if __name__ == "__main__":
    unittest.main(verbosity=1)
