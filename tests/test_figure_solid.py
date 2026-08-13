# -*- coding: utf-8 -*-
"""공간도형(정사영·이면각) 계산과 검산 게이트 회귀 테스트.

이 모듈의 존재 이유는 렌더가 아니라 **검산**이다. 정사영 그림은 좌표를 눈대중으로
찍어도 `lint_svg` 를 CLEAN 으로 통과한다(2D 린트는 겹침·잘림만 본다). 그래서
아래 테스트는 "맞는 구성은 통과시키고 **틀린 구성은 반드시 예외를 던지는가**" 를
양쪽 다 확인한다 — 통과만 검사하면 게이트가 죽어도 초록으로 남는다.
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import figure_svg as fs  # noqa: E402
from core.figure_solid import (  # noqa: E402
    Plane, SolidGeometryError, View, area, cabinet, dihedral_angle, dist, foot,
    is_planar, isometric, line_plane_angle, project_points, projected_area,
    verify_solid,
)


TRI = [(-1.30, -0.55, 1.05), (1.35, -0.30, 0.42), (0.10, 1.25, 1.32)]


class PlaneAndFootTests(unittest.TestCase):
    def test_foot_lands_on_plane_and_is_perpendicular(self) -> None:
        pl = Plane.xy()
        f = foot((3.0, -2.0, 5.0), pl)
        self.assertTrue(pl.contains(f))
        self.assertAlmostEqual(f[0], 3.0)
        self.assertAlmostEqual(f[1], -2.0)
        self.assertAlmostEqual(f[2], 0.0)

    def test_foot_on_a_tilted_plane(self) -> None:
        pl = Plane.through((0, 0, 0), (1, 0, 1), (0, 1, 0))
        p = (2.0, 3.0, -1.0)
        f = foot(p, pl)
        self.assertTrue(pl.contains(f))
        # 수선은 평면의 두 방향 모두와 수직이어야 한다.
        for a, b in (((0, 0, 0), (1, 0, 1)), ((0, 0, 0), (0, 1, 0))):
            d = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
            v = (p[0] - f[0], p[1] - f[1], p[2] - f[2])
            self.assertAlmostEqual(sum(x * y for x, y in zip(d, v)), 0.0, places=9)

    def test_collinear_points_do_not_define_a_plane(self) -> None:
        with self.assertRaises(SolidGeometryError):
            Plane.through((0, 0, 0), (1, 1, 1), (2, 2, 2))


class AngleAndAreaTests(unittest.TestCase):
    def test_dihedral_angle_is_acute_regardless_of_normal_sign(self) -> None:
        a = Plane.xy()
        b = Plane((0, 0, 0), (0.0, -math.sin(math.radians(30)),
                              -math.cos(math.radians(30))))
        self.assertAlmostEqual(dihedral_angle(a, b), 30.0, places=6)

    def test_line_plane_angle(self) -> None:
        # z=0 평면과 45° 로 올라가는 직선
        self.assertAlmostEqual(
            line_plane_angle((0, 0, 0), (1, 0, 1), Plane.xy()), 45.0, places=6)

    def test_projected_area_equals_S_cos_theta(self) -> None:
        pl = Plane.xy()
        s = area(TRI)
        s2 = projected_area(TRI, pl)
        theta = dihedral_angle(Plane.through(*TRI), pl)
        self.assertAlmostEqual(s2, s * math.cos(math.radians(theta)), places=9)

    def test_planarity_check_rejects_a_skew_quad(self) -> None:
        self.assertTrue(is_planar([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]))
        self.assertFalse(is_planar([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 1)]))


class ViewTests(unittest.TestCase):
    def test_projection_is_affine_and_y_grows_downward(self) -> None:
        v = cabinet(scale=50, origin=(100, 100))
        self.assertEqual(v((0, 0, 0)), (100.0, 100.0))
        self.assertAlmostEqual(v((1, 0, 0))[0], 150.0)
        self.assertAlmostEqual(v((0, 0, 1))[1], 50.0)   # z 가 커지면 SVG y 는 작아짐

    def test_view_direction_collapses_points_that_overlap(self) -> None:
        v = cabinet()
        d = v.direction
        p = (0.4, -0.2, 0.7)
        q = (p[0] + 2 * d[0], p[1] + 2 * d[1], p[2] + 2 * d[2])
        for a, b in zip(v(p), v(q)):
            self.assertAlmostEqual(a, b, places=6)

    def test_back_facing_detects_the_hidden_side_of_a_box(self) -> None:
        v = cabinet()
        # 깊이(+y)가 뒤쪽이므로 +y 를 보는 면이 뒤, -y 를 보는 면이 앞이다.
        self.assertTrue(v.is_back_facing((0, 1, 0)))
        self.assertFalse(v.is_back_facing((0, -1, 0)))

    def test_degenerate_view_is_reported(self) -> None:
        flat = View(depth_ratio=0.0, depth_deg=45.0, scale=60.0)
        # 깊이축을 0 으로 죽이면 y 로만 뻗은 도형이 선으로 뭉갠다.
        self.assertTrue(flat.collapses([(0, 0, 0), (0, 1, 0), (0, 2, 0.0)]))
        self.assertFalse(cabinet().collapses([(0, 0, 0), (1, 0, 0), (0, 1, 0)]))

    def test_isometric_is_a_view(self) -> None:
        self.assertIsInstance(isometric(), View)

    def test_bad_scale_is_rejected(self) -> None:
        with self.assertRaises(SolidGeometryError):
            View(scale=0.0)


class VerifySolidTests(unittest.TestCase):
    """게이트의 본체 — 맞으면 통과, **틀리면 반드시 예외**."""

    def test_correct_scene_passes(self) -> None:
        pl = Plane.xy()
        feet = project_points(TRI, pl)
        verify_solid(
            "ok",
            feet=[(feet[i], TRI[i], pl) for i in range(3)],
            areas=[(None, TRI, pl)],
            on_plane=[(f, pl) for f in feet],
        )

    def test_hand_placed_foot_is_caught(self) -> None:
        """눈대중으로 찍은 A′ — 이게 이 모듈을 만든 이유다."""
        pl = Plane.xy()
        wrong = (TRI[0][0] + 0.35, TRI[0][1], 0.0)
        with self.assertRaises(SolidGeometryError) as ctx:
            verify_solid("bad-foot", feet=[(wrong, TRI[0], pl)])
        self.assertIn("정사영 발", str(ctx.exception))

    def test_foot_left_off_the_plane_is_caught(self) -> None:
        pl = Plane.xy()
        with self.assertRaises(SolidGeometryError):
            verify_solid("bad-onplane", on_plane=[((0.0, 0.0, 0.4), pl)])

    def test_wrong_dihedral_label_is_caught(self) -> None:
        pl = Plane.xy()
        real = dihedral_angle(Plane.through(*TRI), pl)
        verify_solid("angle-ok", angles=[(real, "dihedral", Plane.through(*TRI), pl)])
        with self.assertRaises(SolidGeometryError) as ctx:
            verify_solid("angle-bad",
                         angles=[(real + 8.0, "dihedral", Plane.through(*TRI), pl)])
        self.assertIn("각", str(ctx.exception))

    def test_line_angle_kind(self) -> None:
        pl = Plane.xy()
        verify_solid("line-ok", angles=[(45.0, "line", (0, 0, 0), (1, 0, 1), pl)])
        with self.assertRaises(SolidGeometryError):
            verify_solid("line-bad", angles=[(30.0, "line", (0, 0, 0), (1, 0, 1), pl)])

    def test_unknown_angle_kind_is_rejected(self) -> None:
        with self.assertRaises(SolidGeometryError):
            verify_solid("kind", angles=[(10.0, "twist", Plane.xy(), Plane.xy())])

    def test_projected_area_label_is_checked(self) -> None:
        pl = Plane.xy()
        good = projected_area(TRI, pl)
        verify_solid("area-ok", areas=[(good, TRI, pl)])
        with self.assertRaises(SolidGeometryError) as ctx:
            verify_solid("area-bad", areas=[(good * 1.5, TRI, pl)])
        self.assertIn("넓이", str(ctx.exception))

    def test_skew_polygon_area_is_refused(self) -> None:
        with self.assertRaises(SolidGeometryError):
            verify_solid("skew",
                         areas=[(None, [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 1)],
                                 Plane.xy())])

    def test_length_ratio_uses_one_scale(self) -> None:
        a, b, c = (0, 0, 0), (3, 0, 0), (3, 4, 0)
        verify_solid("len-ok", lengths=[(3, a, b), (4, b, c), (5, a, c)])
        with self.assertRaises(SolidGeometryError) as ctx:
            verify_solid("len-bad", lengths=[(3, a, b), (4, b, c), (9, a, c)])
        self.assertIn("길이", str(ctx.exception))

    def test_perpendicularity(self) -> None:
        verify_solid("perp-ok",
                     perpendicular=[(((0, 0, 0), (1, 0, 0)), ((0, 0, 0), (0, 1, 0)))])
        with self.assertRaises(SolidGeometryError):
            verify_solid("perp-bad",
                         perpendicular=[(((0, 0, 0), (1, 0, 0)),
                                         ((0, 0, 0), (1, 1, 0)))])

    def test_degenerate_view_is_flagged_during_verification(self) -> None:
        flat = View(depth_ratio=0.0, depth_deg=45.0, scale=60.0)
        poly = [(0, 0, 0), (0, 1, 0), (0, 2, 0)]
        with self.assertRaises(SolidGeometryError):
            verify_solid("degenerate", areas=[(None, poly, Plane.xy())], view=flat)


class RegistryIntegrationTests(unittest.TestCase):
    """`unverified()` 가 2D·3D 를 **한 그물로** 봐야 한다."""

    def test_verify_solid_registers_in_the_shared_ledger(self) -> None:
        svgs = {"solid1": '<svg><text>5 cm</text></svg>'}
        self.assertEqual(fs.unverified(svgs), ["solid1"])
        verify_solid("solid1", lengths=[(5, (0, 0, 0), (5, 0, 0))])
        self.assertEqual(fs.unverified(svgs), [])

    def test_scope_is_the_calling_module_not_this_helper(self) -> None:
        verify_solid("scoped", on_plane=[((0, 0, 0), Plane.xy())])
        key = (str(__file__), "scoped")
        self.assertIn(key, fs._VERIFIED)




class CameraAndCurveTests(unittest.TestCase):
    """구·원뿔곡선처럼 곡선이 주인공인 그림용(2026-08-13 추가)."""

    def test_sphere_stays_a_circle_and_its_great_circle_fits_inside(self) -> None:
        from core.figure_solid import Camera, circle3
        cam = Camera(elev=20, azim=-58, scale=60, origin=(200, 200))
        pts = cam.many(circle3((0, 0, 0), 1.0, (0, 0, 1)))
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        # 정투영이면 적도의 반장축 = 구 반지름(=scale), 반단축 = scale·sin(고도).
        # 표본이 유한해 극점을 정확히 밟지 못하므로 0.05px 여유를 둔다.
        self.assertAlmostEqual((max(xs) - min(xs)) / 2, 60.0, delta=0.05)
        self.assertAlmostEqual((max(ys) - min(ys)) / 2,
                               60.0 * math.sin(math.radians(20)), delta=0.05)

    def test_every_projected_point_lies_within_the_sphere_outline(self) -> None:
        from core.figure_solid import Camera, circle3
        cam = Camera(elev=33, azim=17, scale=50, origin=(0, 0))
        for normal in ((0, 0, 1), (1, 0.4, 0), (0.3, 1, 0.2)):
            for x, y in cam.many(circle3((0, 0, 0), 1.0, normal)):
                self.assertLessEqual(math.hypot(x, y), 50.0 + 1e-6)

    def test_depth_split_separates_front_and_back(self) -> None:
        from core.figure_solid import Camera, circle3, split_by_depth
        cam = Camera(elev=20, azim=-58, scale=60, origin=(200, 200))
        pts = circle3((0, 0, 0), 1.0, (0, 0, 1))
        front, back = split_by_depth(pts, cam)
        self.assertTrue(front and back)
        for seg in front:
            self.assertTrue(all(cam.depth(p) <= 1e-9 for p in seg[1:-1]))
        for seg in back:
            self.assertTrue(all(cam.depth(p) >= -1e-9 for p in seg[1:-1]))

    def test_plane_intersection_point_lies_on_both_planes(self) -> None:
        from core.figure_solid import Plane, plane_intersection, add, scale as vs
        a = Plane((0, 0, 0), (0, 0, 1))
        b = Plane((0, 0.2, 0), (0, -0.6, 0.8))
        p, d = plane_intersection(a, b)
        self.assertTrue(a.contains(p) and b.contains(p))
        for t in (-2.0, 3.5):
            q = add(p, vs(d, t))
            self.assertTrue(a.contains(q) and b.contains(q))

    def test_parallel_planes_have_no_intersection(self) -> None:
        from core.figure_solid import Plane, plane_intersection
        with self.assertRaises(SolidGeometryError):
            plane_intersection(Plane((0, 0, 0), (0, 0, 1)), Plane((0, 0, 2), (0, 0, 1)))

    def test_degenerate_camera_and_circle_inputs(self) -> None:
        from core.figure_solid import Camera, circle3
        with self.assertRaises(SolidGeometryError):
            Camera(elev=90.0)
        with self.assertRaises(SolidGeometryError):
            circle3((0, 0, 0), 0.0, (0, 0, 1))
        with self.assertRaises(SolidGeometryError):
            circle3((0, 0, 0), 1.0, (0, 0, 1), n=4)

if __name__ == "__main__":
    unittest.main()
