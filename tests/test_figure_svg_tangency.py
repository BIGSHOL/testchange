# -*- coding: utf-8 -*-
"""접선·점 검산, 좁은 각 지시선, 통일 글자 크기 회귀 테스트(2026-08-13).

셋 다 실제 출하 결함에서 나왔다:

* 왕선중 q11 의 접선이 접점 D 를 10px 비껴간 채 `lint_svg` CLEAN 으로 통과했다
  — 방향벡터를 손으로 적어 부호를 틀렸고, "닿는가" 를 보는 검산이 없었다.
* 왕선중 q5 의 20° 가 각에서 한참 아래로 밀려났다 — 좁은 각에서 halo 가 변을
  지우지 않으려면 멀리 밀 수밖에 없는데, 그러면 어느 각인지 모호해진다.
* 한 그림 안에서 점 이름 15 · 각도 11 · 치수 12.5 로 크기가 제각각이었다.
"""
from __future__ import annotations

import math
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.figure_quality import assess_svg  # noqa: E402
from core.figure_svg import (  # noqa: E402
    SVGTextRun, angle_label, angle_label_leader, angle_mark, circ, circle_pt,
    leader, line,
    lint_svg, tangent_beyond, tangent_dir, tangent_isect, tangent_seg, txt,
    type_scale, verify_figure,
)


CX, CY, R = 150.0, 112.0, 88.0


def _svg(body, w=330, h=250):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">'
            f'<rect width="{w}" height="{h}" fill="#fff"/>{body}</svg>')


class TangentHelperTests(unittest.TestCase):
    def test_direction_is_perpendicular_to_the_radius(self) -> None:
        for ang in (0, 10, 73, 190, 275, 359):
            ux, uy = tangent_dir(CX, CY, R, ang)
            px, py = circle_pt(CX, CY, ang, R)
            self.assertAlmostEqual((px - CX) * ux + (py - CY) * uy, 0.0, places=9)
            self.assertAlmostEqual(math.hypot(ux, uy), 1.0, places=12)

    def test_segment_passes_through_the_contact_point(self) -> None:
        p, q = tangent_seg(CX, CY, R, 10, back=30, fwd=50)
        c = circle_pt(CX, CY, 10, R)
        L = math.hypot(q[0] - p[0], q[1] - p[1])
        d = abs((q[0] - p[0]) * (p[1] - c[1]) - (p[0] - c[0]) * (q[1] - p[1])) / L
        self.assertLess(d, 1e-9)
        # 중심에서 선까지 거리 = 반지름
        dc = abs((q[0] - p[0]) * (p[1] - CY) - (p[0] - CX) * (q[1] - p[1])) / L
        self.assertAlmostEqual(dc, R, places=9)

    def test_beyond_extends_away_from_the_external_point(self) -> None:
        P = tangent_isect(CX, CY, R, 270, 10)
        T = tangent_beyond(CX, CY, R, 10, P, 40.0)
        D = circle_pt(CX, CY, 10, R)
        self.assertAlmostEqual(math.hypot(T[0] - D[0], T[1] - D[1]), 40.0, places=9)
        # P–D–T 가 한 직선이고 D 가 가운데다.
        self.assertGreater(math.hypot(T[0] - P[0], T[1] - P[1]),
                           math.hypot(D[0] - P[0], D[1] - P[1]))
        verify_figure("beyond", tangents=[(T, P, CX, CY, R)], on_line=[(D, T, P)])

    def test_zero_radius_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            tangent_dir(CX, CY, 0, 10)


class TangencyVerificationTests(unittest.TestCase):
    """이 검사가 없어서 왕선중 q11 이 어긋난 채 출하됐다."""

    def test_the_real_wangseon_q11_bug_is_caught(self) -> None:
        D = circle_pt(CX, CY, 10, R)
        P = tangent_isect(CX, CY, R, 270, 10)
        bad_T = (D[0] + 40 * math.sin(math.radians(10)),
                 D[1] - 40 * math.cos(math.radians(10)))     # 당시 코드 그대로
        with self.assertRaises(ValueError) as ctx:
            verify_figure("q11-bad", tangents=[(bad_T, P, CX, CY, R)])
        self.assertIn("접선", str(ctx.exception))

    def test_a_chord_is_reported_as_secant_not_tangent(self) -> None:
        a, b = circle_pt(CX, CY, 20, R), circle_pt(CX, CY, 160, R)
        with self.assertRaises(ValueError) as ctx:
            verify_figure("chord", tangents=[(a, b, CX, CY, R)])
        self.assertIn("할선", str(ctx.exception))

    def test_point_off_the_line_is_caught(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            verify_figure("off", on_line=[((10, 14), (0, 0), (100, 0))])
        self.assertIn("직선 위에 없음", str(ctx.exception))
        verify_figure("on", on_line=[((10, 0), (0, 0), (100, 0))])

    def test_point_off_the_circle_is_caught(self) -> None:
        with self.assertRaises(ValueError):
            verify_figure("offc", on_circle=[((CX + R + 6, CY), CX, CY, R)])
        verify_figure("onc", on_circle=[(circle_pt(CX, CY, 33, R), CX, CY, R)])

    def test_new_checks_count_toward_the_ledger(self) -> None:
        from core.figure_svg import _VERIFIED, unverified
        svgs = {"tan1": '<svg><text>5 cm</text></svg>'}
        self.assertEqual(unverified(svgs), ["tan1"])
        verify_figure("tan1", on_circle=[(circle_pt(CX, CY, 5, R), CX, CY, R)])
        self.assertEqual(unverified(svgs), [])
        self.assertEqual(_VERIFIED[(str(__file__), "tan1")], 1)


class NarrowAngleLeaderTests(unittest.TestCase):
    def test_label_sits_outside_the_angle_and_is_pointed_at(self) -> None:
        v, p1, p2 = (150.0, 40.0), (90.0, 200.0), (120.0, 205.0)   # 약 12° 쐐기
        markup = angle_label_leader(*v, p1, p2, "20°", fs=14, arc_r=24, out=70)
        root = ET.fromstring(_svg(markup))
        label = root.find(".//{http://www.w3.org/2000/svg}text")
        self.assertIsNotNone(label)
        lx, ly = float(label.get("x")), float(label.get("y"))
        # 라벨이 두 변 **바깥**에 있어야 한다(각 안이면 halo 로 변을 지우게 된다).
        a0 = math.degrees(math.atan2(-(p1[1] - v[1]), p1[0] - v[0]))
        a1 = math.degrees(math.atan2(-(p2[1] - v[1]), p2[0] - v[0]))
        al = math.degrees(math.atan2(-(ly - v[1]), lx - v[0]))
        inside = (min(a0, a1) - 0.5) <= al <= (max(a0, a1) + 0.5)
        self.assertFalse(inside, f"라벨이 각 안에 있음 (a0={a0:.1f} a1={a1:.1f} al={al:.1f})")

    def test_leader_has_an_arrow_head_and_can_omit_it(self) -> None:
        self.assertIn("<path", leader((10, 10), (80, 60)))
        self.assertNotIn("<path", leader((10, 10), (80, 60), arrow=False))

    def test_rich_runs_are_supported_for_x_and_y_labels(self) -> None:
        markup = angle_label_leader(150, 40, (90, 200), (120, 205),
                                    runs=[SVGTextRun("x", italic=True),
                                          SVGTextRun("°")], fs=14)
        self.assertIn('font-style="italic"', markup)
        self.assertIn("°", markup)

    def test_leader_figure_passes_the_structural_gate_and_lint(self) -> None:
        v, p1, p2 = (150.0, 40.0), (90.0, 200.0), (122.0, 205.0)
        body = (circ(CX, CY, R) + line(v, p1) + line(v, p2)
                + angle_mark(*v, p1, p2, r=24, dash=False)
                + angle_label_leader(*v, p1, p2, "20°", fs=15, arc_r=24, out=76))
        svg = _svg(body)
        self.assertTrue(assess_svg(svg).accepted, assess_svg(svg).issues)
        self.assertEqual(lint_svg(svg), [])

    def test_degenerate_leader_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            leader((10, 10), (10, 10))


class CurvedLeaderAndPolicyTests(unittest.TestCase):
    """사용자 2026-08-13: 화살표는 좁은 곳만, 그리고 각 방향과 반대면 곡선으로."""

    def test_end_dir_makes_it_a_curve_and_aims_the_head(self) -> None:
        straight = leader((10, 10), (100, 60))
        curved = leader((10, 10), (100, 60), end_dir=(-1.0, 0.0))
        self.assertIn("<line", straight)
        self.assertNotIn("<line", curved)      # 곡선은 path 로만
        self.assertIn(" Q ", curved)
        # 화살촉이 end_dir(왼쪽) 을 향해야 한다 — 밑변이 팁보다 오른쪽.
        head = curved[curved.rindex('<path d="M'):]
        nums = [float(v) for v in re.findall(r"-?\d+\.?\d*", head)]
        self.assertGreater(nums[2], nums[0])

    def test_curve_arrives_pointing_into_the_angle(self) -> None:
        v, p1, p2 = (300.0, 200.0), (240.0, 150.0), (250.0, 210.0)
        markup = angle_label_leader(*v, p1, p2, "70°", fs=14, arc_r=20, out=60,
                                    side=-1, curve_deg=40.0)
        self.assertIn(" Q ", markup, "각 반대편 라벨은 곡선이어야 한다")

    def test_curve_threshold_knob_can_force_a_straight_leader(self) -> None:
        v, p1, p2 = (150.0, 40.0), (90.0, 200.0), (120.0, 205.0)
        kw = dict(fs=14, arc_r=24, out=70)
        self.assertIn("<line", angle_label_leader(*v, p1, p2, "20°",
                                                  curve_deg=180.0, **kw))
        self.assertIn(" Q ", angle_label_leader(*v, p1, p2, "20°",
                                                curve_deg=0.0, **kw))

    def test_arrow_always_arrives_pointing_into_the_angle(self) -> None:
        """직선이든 곡선이든 화살촉은 각 안쪽(꼭짓점 쪽)을 향해야 한다."""
        for v, p1, p2 in (((150.0, 40.0), (90.0, 200.0), (120.0, 205.0)),
                          ((300.0, 200.0), (240.0, 150.0), (250.0, 210.0))):
            markup = angle_label_leader(*v, p1, p2, "70°", fs=14, arc_r=20, out=60)
            head = markup[markup.rindex('<path d="M'):]
            n = [float(t) for t in re.findall(r"-?\d+\.?\d*", head)]
            tip, base = (n[0], n[1]), ((n[2] + n[4]) / 2, (n[3] + n[5]) / 2)
            ax, ay = tip[0] - base[0], tip[1] - base[1]        # 화살 진행 방향
            bx, by = v[0] - tip[0], v[1] - tip[1]              # 팁 -> 꼭짓점
            la, lb = math.hypot(ax, ay), math.hypot(bx, by)
            self.assertGreater((ax * bx + ay * by) / (la * lb), 0.5,
                               f"화살표가 각 바깥을 향함 (v={v})")

    def test_wide_open_angle_is_labelled_inside_without_a_leader(self) -> None:
        v, p1, p2 = (150.0, 150.0), (250.0, 150.0), (150.0, 50.0)   # 90°
        markup = angle_label(*v, p1, p2, "90°", fs=14, wide_deg=30.0)
        self.assertNotIn("<path", markup)      # 화살촉·곡선 없음
        self.assertIn("<text", markup)

    def test_narrow_angle_always_gets_a_leader(self) -> None:
        v, p1, p2 = (150.0, 40.0), (90.0, 200.0), (120.0, 205.0)    # 약 12°
        self.assertIn("<path", angle_label(*v, p1, p2, "12°", fs=14, wide_deg=30.0))

    def test_blocked_wide_angle_falls_back_to_a_leader(self) -> None:
        v, p1, p2 = (150.0, 150.0), (250.0, 150.0), (150.0, 50.0)
        blocker = ((150.0, 133.0), (230.0, 133.0))    # 이등분선 위 라벨 자리를 막는 선
        plain = angle_label(*v, p1, p2, "90°", fs=14, wide_deg=30.0)
        blocked = angle_label(*v, p1, p2, "90°", fs=14, wide_deg=30.0,
                              avoid=[blocker])
        self.assertNotIn("<path", plain)
        self.assertIn("<path", blocked)


class TypeScaleTests(unittest.TestCase):
    def test_one_size_for_names_and_numbers(self) -> None:
        # 같은 그림이면 점 이름이든 각도든 같은 값이 나와야 한다(통일).
        self.assertEqual(type_scale(330, 250), type_scale(330, 250, "label"))

    def test_scales_with_the_figure_and_stays_in_a_readable_band(self) -> None:
        small, large = type_scale(200, 180), type_scale(600, 520)
        self.assertLess(small, large)
        for w, h in ((120, 100), (250, 220), (330, 250), (900, 800)):
            self.assertGreaterEqual(type_scale(w, h), 13.0)
            self.assertLessEqual(type_scale(w, h), 22.0)

    def test_bigger_than_the_old_hand_written_15(self) -> None:
        # 사용자 요구: 도형에 비해 문자가 작다 → 종전 15 보다 커야 한다.
        self.assertGreater(type_scale(330, 250), 15.0)

    def test_tick_role_is_smaller_than_label(self) -> None:
        self.assertLess(type_scale(300, 280, "tick"), type_scale(300, 280))
        self.assertLess(type_scale(300, 280, "small"), type_scale(300, 280, "tick"))

    def test_bad_inputs(self) -> None:
        with self.assertRaises(ValueError):
            type_scale(0, 100)
        with self.assertRaises(ValueError):
            type_scale(100, 100, "huge")


if __name__ == "__main__":
    unittest.main()
