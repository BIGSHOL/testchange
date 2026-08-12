# -*- coding: utf-8 -*-
"""Deterministic geometry-scene and FigureSpec v2 regression tests.

These tests intentionally use no vision API or network resource.  Run with::

    python tests/test_figure_scene.py
    python -m pytest tests/test_figure_scene.py -v
"""
from __future__ import annotations

import math
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.figure_generator import _compile_structured_candidate  # noqa: E402
from core.figure_quality import assess_svg  # noqa: E402
from core.figure_scene import (  # noqa: E402
    FigureScene,
    FigureSpecError,
    GeometryValidationError,
    compile_figure_spec,
    intersecting_chords_template,
)
from core.figure_svg import lint_svg  # noqa: E402


def _segment_parameter(point, start, end) -> float:
    dx, dy = end.x - start.x, end.y - start.y
    return ((point.x - start.x) * dx + (point.y - start.y) * dy) / (dx * dx + dy * dy)


def _minor_angle_degrees(vertex, first, second) -> float:
    u = (first.x - vertex.x, first.y - vertex.y)
    v = (second.x - vertex.x, second.y - vertex.y)
    cosine = (u[0] * v[0] + u[1] * v[1]) / (math.hypot(*u) * math.hypot(*v))
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def _boxes_overlap(first, second, gap: float = 0.0) -> bool:
    return not (
        first[2] + gap <= second[0]
        or second[2] + gap <= first[0]
        or first[3] + gap <= second[1]
        or second[3] + gap <= first[1]
    )


def _segment_intersects_box(start, end, box, gap: float = 0.0) -> bool:
    """Return whether a finite segment crosses a (possibly expanded) box."""

    x_min, y_min, x_max, y_max = (
        box[0] - gap, box[1] - gap, box[2] + gap, box[3] + gap,
    )
    dx, dy = end.x - start.x, end.y - start.y
    t_min, t_max = 0.0, 1.0
    for p, q in (
        (-dx, start.x - x_min),
        (dx, x_max - start.x),
        (-dy, start.y - y_min),
        (dy, y_max - start.y),
    ):
        if abs(p) <= 1.0e-12:
            if q < 0.0:
                return False
            continue
        ratio = q / p
        if p < 0.0:
            t_min = max(t_min, ratio)
        else:
            t_max = min(t_max, ratio)
        if t_min > t_max:
            return False
    return True


def _polyline_intersects_box(points, box, gap: float = 0.0) -> bool:
    return any(
        _segment_intersects_box(first, second, box, gap)
        for first, second in zip(points, points[1:])
    )


def _point_to_line_distance(point, start, end) -> float:
    dx, dy = end.x - start.x, end.y - start.y
    return abs(dx * (start.y - point.y) - (start.x - point.x) * dy) / math.hypot(dx, dy)


def _automatic_chords_scene(dx: float = 0.0, dy: float = 0.0) -> FigureScene:
    scene = FigureScene(background="white")
    scene.add_point("O", dx, dy).add_circle("omega", "O", 35)
    for name, angle in (("A", 130), ("B", 210), ("C", -48), ("D", 32)):
        scene.point_on_circle(name, "omega", angle)
    scene.add_segment("AC", "A", "C")
    scene.add_segment("BD", "B", "D")
    scene.intersection("P", "AC", "BD")
    for name in ("A", "B", "C", "D", "P"):
        scene.add_point_label(name, position="auto")
    return scene


def _dimension_avoidance_scene(
        obstacle_y: float, dx: float = 0.0, dy: float = 0.0) -> FigureScene:
    """Horizontal measurement with a labelled obstacle on exactly one side."""

    scene = FigureScene(background="white")
    scene.add_point("A", dx, dy).add_point("B", dx + 80, dy)
    scene.add_point("C", dx + 18, dy + obstacle_y)
    scene.add_point("D", dx + 62, dy + obstacle_y)
    scene.add_segment("AB", "A", "B")
    scene.add_segment("CD", "C", "D")
    scene.add_point_label("A", position="auto")
    scene.add_point_label("B", position="auto")
    obstacle_label_position = "S" if obstacle_y > 0 else "N"
    scene.add_point_label("C", position=obstacle_label_position)
    scene.add_point_label("D", position=obstacle_label_position)
    scene.add_dimension(
        "AB_length", "A", "B", "8 cm", side="auto", offset=18, inset=4,
    )
    return scene


class IntersectingChordsGoldenTest(unittest.TestCase):
    def setUp(self) -> None:
        self.scene = intersecting_chords_template()

    def test_reference_six_geometry_and_minor_angle(self) -> None:
        circle = self.scene.circles["omega"]
        center = self.scene.points[circle.center]
        for name in ("A", "B", "C", "D"):
            point = self.scene.points[name]
            self.assertAlmostEqual(
                math.hypot(point.x - center.x, point.y - center.y),
                circle.radius,
                places=9,
                msg=f"{name} must lie on omega",
            )

        intersection = self.scene.points["P"]
        self.assertEqual(intersection.segment_refs, ("AC", "BD"))
        for segment_name in intersection.segment_refs:
            segment = self.scene.segments[segment_name]
            parameter = _segment_parameter(
                intersection,
                self.scene.points[segment.p1],
                self.scene.points[segment.p2],
            )
            self.assertGreater(parameter, 0.0)
            self.assertLess(parameter, 1.0)

        angle = self.scene.angles["DPC"]
        self.assertEqual((angle.vertex, angle.p1, angle.p2), ("P", "D", "C"))
        self.assertEqual(angle.label, "x\u00b0")
        self.assertAlmostEqual(
            _minor_angle_degrees(
                self.scene.points[angle.vertex],
                self.scene.points[angle.p1],
                self.scene.points[angle.p2],
            ),
            79.0,
            places=9,
        )

    def test_render_is_deterministic_and_passes_both_quality_gates(self) -> None:
        first = self.scene.render_svg()
        second = self.scene.render_svg()

        self.assertEqual(first, second)
        self.assertIn("x\u00b0", first)
        self.assertEqual(lint_svg(first), [])
        assessment = assess_svg(first, run_pixel_lint=True)
        self.assertTrue(
            assessment.accepted,
            assessment.security_issues + assessment.issues,
        )
        self.assertEqual(assessment.security_issues, [])
        self.assertEqual(assessment.issues, [])


class SceneLayoutTest(unittest.TestCase):
    def test_auto_fit_uses_numeric_translation_without_svg_transform_or_ids(self) -> None:
        scene = FigureScene(background="transparent")
        scene.add_point("A", -40, -30)
        scene.add_point("B", -5, -2)
        scene.add_segment("AB", "A", "B")
        scene.add_point_label("A", position="NW")
        scene.add_point_label("B", position="SE")

        resolved = scene.resolve()
        svg = scene.render_svg()
        root = ET.fromstring(svg)

        self.assertGreater(resolved.translation[0], 0.0)
        self.assertGreater(resolved.translation[1], 0.0)
        self.assertEqual(root.attrib["viewBox"].split()[:2], ["0", "0"])
        self.assertNotIn("transform=", svg)
        self.assertNotIn(" id=", svg)
        self.assertTrue(all("transform" not in element.attrib for element in root.iter()))
        self.assertTrue(all("id" not in element.attrib for element in root.iter()))

    def test_fixed_canvas_rejects_clipped_content(self) -> None:
        scene = FigureScene(canvas=(20, 20))
        scene.add_point("O", 5, 5)
        scene.add_circle("omega", "O", 10)

        with self.assertRaisesRegex(GeometryValidationError, "fixed canvas clips"):
            scene.render_svg()

    def test_automatic_labels_do_not_overlap_and_are_translation_invariant(self) -> None:
        original = _automatic_chords_scene()
        shifted = _automatic_chords_scene(123.0, -77.0)
        first = original.resolve()
        second = shifted.resolve()

        point_label_boxes = [
            (name, box) for name, box in first.label_boxes.items()
            if not name.startswith("angle:")
        ]
        for index, (name, box) in enumerate(point_label_boxes):
            for other_name, other_box in point_label_boxes[index + 1:]:
                self.assertFalse(
                    _boxes_overlap(box, other_box),
                    f"automatic labels {name} and {other_name} overlap",
                )

        self.assertAlmostEqual(first.width, second.width, places=9)
        self.assertAlmostEqual(first.height, second.height, places=9)
        for name in ("A", "B", "C", "D", "P"):
            p1, p2 = original.points[name], shifted.points[name]
            label1, label2 = first.label_positions[name], second.label_positions[name]
            self.assertAlmostEqual(label1[0] - p1.x, label2[0] - p2.x, places=9)
            self.assertAlmostEqual(label1[1] - p1.y, label2[1] - p2.y, places=9)
            self.assertAlmostEqual(
                label1[0] + first.translation[0],
                label2[0] + second.translation[0],
                places=9,
            )
            self.assertAlmostEqual(
                label1[1] + first.translation[1],
                label2[1] + second.translation[1],
                places=9,
            )


class DimensionLayoutTest(unittest.TestCase):
    def test_short_segment_long_label_moves_clear_and_keeps_one_full_quadratic(self) -> None:
        scene = FigureScene(background="white")
        scene.add_point("A", 0, 0).add_point("B", 36, 0)
        scene.add_segment("AB", "A", "B")
        scene.add_dimension(
            "AB_length", "A", "B", "12 centimeters",
            side="auto", offset=15, inset=3,
        )

        layout = scene.resolve().dimension_layouts["AB_length"]
        self.assertFalse(
            _polyline_intersects_box(layout.path_samples, layout.label_box),
            "a long dimension label must move clear of the complete curve",
        )

        svg = scene.render_svg()
        root = ET.fromstring(svg)
        dimension_paths = [
            element for element in root.findall(".//{*}path")
            if "stroke-dasharray" in element.attrib
        ]
        self.assertEqual(len(dimension_paths), 1)
        path_data = dimension_paths[0].attrib["d"]
        self.assertEqual(path_data.split().count("M"), 1, path_data)
        self.assertEqual(path_data.split().count("Q"), 1, path_data)
        self.assertEqual(lint_svg(svg), [])
        assessment = assess_svg(svg, run_pixel_lint=True)
        self.assertTrue(
            assessment.accepted,
            assessment.security_issues + assessment.issues,
        )

    def test_multi_dimension_spec_render_is_independent_of_record_order(self) -> None:
        points = {
            "A": [0, 0], "B": [70, 0],
            "C": [0, 65], "D": [70, 65],
        }
        segments = {"AB": ["A", "B"], "CD": ["C", "D"]}
        labels_forward = {
            "A": {"text": "A", "position": "NW"},
            "B": {"text": "B", "position": "NE"},
            "C": {"text": "C", "position": "SW"},
            "D": {"text": "D", "position": "SE"},
        }
        dimensions_forward = {
            "AB_length": {
                "points": ["A", "B"], "label": "7 cm", "side": "left",
            },
            "CD_length": {
                "points": ["C", "D"], "label": "9 cm", "side": "right",
            },
        }
        forward = {
            "version": 2, "points": points, "segments": segments,
            "dimensions": dimensions_forward, "labels": labels_forward,
        }
        reverse = {
            "version": 2, "points": points, "segments": segments,
            "dimensions": dict(reversed(list(dimensions_forward.items()))),
            "labels": dict(reversed(list(labels_forward.items()))),
        }

        forward_svg = compile_figure_spec(forward).render_svg()
        reverse_svg = compile_figure_spec(reverse).render_svg()

        self.assertEqual(forward_svg, reverse_svg)
        self.assertEqual(
            ET.fromstring(forward_svg).attrib["viewBox"],
            ET.fromstring(reverse_svg).attrib["viewBox"],
        )

    def test_near_zero_explicit_offset_separates_from_measured_chord_or_fails_closed(self) -> None:
        scene = FigureScene(background="white")
        scene.add_point("A", 0, 0).add_point("B", 80, 0)
        scene.add_segment("AB", "A", "B")
        scene.add_dimension(
            "AB_length", "A", "B", "8 cm",
            side="auto", offset=0.001, inset=3,
        )

        try:
            layout = scene.resolve().dimension_layouts["AB_length"]
        except GeometryValidationError:
            return  # A valid fail-closed outcome is explicitly part of the contract.

        self.assertFalse(
            _segment_intersects_box(
                scene.points["A"], scene.points["B"], layout.label_box,
            ),
            "dimension label must not overlap its measured chord",
        )
        apex = layout.path_samples[len(layout.path_samples) // 2]
        self.assertGreaterEqual(
            _point_to_line_distance(
                apex, scene.points["A"], scene.points["B"],
            ),
            3.0,
            "an accepted near-zero request must be promoted to a visibly separated curve",
        )
        svg = scene.render_svg()
        self.assertEqual(lint_svg(svg), [])
        assessment = assess_svg(svg, run_pixel_lint=True)
        self.assertTrue(
            assessment.accepted,
            assessment.security_issues + assessment.issues,
        )

    def test_curved_dashed_dimension_has_inspectable_safe_layout(self) -> None:
        scene = FigureScene(background="white")
        scene.add_point("A", 0, 0).add_point("B", 80, 0)
        scene.add_segment("AB", "A", "B")
        scene.add_point_label("A", position="N")
        scene.add_point_label("B", position="N")
        scene.add_dimension(
            "AB_length", "A", "B", "8 cm",
            side="left", offset=18, inset=4, font_size=12,
        )

        resolved = scene.resolve()
        layout = resolved.dimension_layouts["AB_length"]

        self.assertEqual(layout.side, "left")
        self.assertAlmostEqual(math.hypot(layout.start.x, layout.start.y), 4.0)
        self.assertAlmostEqual(math.hypot(layout.end.x - 80, layout.end.y), 4.0)
        signed_control_offset = 80 * layout.control.y
        self.assertGreater(signed_control_offset, 0.0)
        self.assertGreaterEqual(len(layout.path_samples), 9)
        self.assertAlmostEqual(layout.path_samples[0].x, layout.start.x)
        self.assertAlmostEqual(layout.path_samples[0].y, layout.start.y)
        self.assertAlmostEqual(layout.path_samples[-1].x, layout.end.x)
        self.assertAlmostEqual(layout.path_samples[-1].y, layout.end.y)

        label_x, label_y = layout.label_position
        self.assertLessEqual(layout.label_box[0], label_x)
        self.assertLessEqual(label_x, layout.label_box[2])
        self.assertLessEqual(layout.label_box[1], label_y)
        self.assertLessEqual(label_y, layout.label_box[3])
        self.assertFalse(
            _segment_intersects_box(scene.points["A"], scene.points["B"], layout.label_box),
            "dimension label must not sit on the measured segment",
        )
        for point_name in ("A", "B"):
            self.assertFalse(
                _boxes_overlap(layout.label_box, resolved.label_boxes[point_name]),
                f"dimension label overlaps point label {point_name}",
            )

        svg = scene.render_svg()
        self.assertIn("8 cm", svg)
        self.assertIn("stroke-dasharray", svg)
        root = ET.fromstring(svg)
        dimension_path = next(
            element for element in root.findall(".//{*}path")
            if "stroke-dasharray" in element.attrib
        )
        self.assertEqual(
            dimension_path.attrib["d"].split().count("M"), 2,
            "dimension curve must have a real label-width gap, not rely on halo only",
        )
        self.assertEqual(lint_svg(svg), [])
        assessment = assess_svg(svg, run_pixel_lint=True)
        self.assertTrue(
            assessment.accepted,
            assessment.security_issues + assessment.issues,
        )

    def test_auto_side_avoids_obstacles_and_is_deterministic_and_translation_invariant(self) -> None:
        for obstacle_y, expected_side in ((18.0, "right"), (-18.0, "left")):
            with self.subTest(obstacle_y=obstacle_y):
                scene = _dimension_avoidance_scene(obstacle_y)
                first = scene.resolve()
                second = scene.resolve()
                self.assertEqual(first.dimension_layouts, second.dimension_layouts)
                self.assertEqual(
                    first.dimension_layouts["AB_length"].side,
                    expected_side,
                )
                self.assertEqual(scene.render_svg(), scene.render_svg())

        original = _dimension_avoidance_scene(18.0)
        shifted = _dimension_avoidance_scene(18.0, 137.0, -91.0)
        first = original.resolve()
        second = shifted.resolve()
        layout1 = first.dimension_layouts["AB_length"]
        layout2 = second.dimension_layouts["AB_length"]
        anchor1, anchor2 = original.points["A"], shifted.points["A"]

        self.assertEqual(layout1.side, layout2.side)
        self.assertAlmostEqual(first.width, second.width, places=9)
        self.assertAlmostEqual(first.height, second.height, places=9)
        for point1, point2 in zip(
            (layout1.start, layout1.control, layout1.end, *layout1.path_samples),
            (layout2.start, layout2.control, layout2.end, *layout2.path_samples),
        ):
            self.assertAlmostEqual(point1.x - anchor1.x, point2.x - anchor2.x, places=9)
            self.assertAlmostEqual(point1.y - anchor1.y, point2.y - anchor2.y, places=9)
        self.assertAlmostEqual(
            layout1.label_position[0] - anchor1.x,
            layout2.label_position[0] - anchor2.x,
            places=9,
        )
        self.assertAlmostEqual(
            layout1.label_position[1] - anchor1.y,
            layout2.label_position[1] - anchor2.y,
            places=9,
        )

    def test_offset_curvature_aliases_produce_the_same_curve(self) -> None:
        def build(**dimension_options) -> FigureScene:
            scene = FigureScene(background="transparent")
            scene.add_point("A", 0, 0).add_point("B", 60, 20)
            scene.add_segment("AB", "A", "B")
            scene.add_dimension(
                "length", "A", "B", "7 cm", side="right", inset=3,
                **dimension_options,
            )
            return scene

        by_offset = build(offset=17).resolve().dimension_layouts["length"]
        by_curvature = build(curvature=17).resolve().dimension_layouts["length"]
        for first, second in zip(
            (by_offset.start, by_offset.control, by_offset.end, *by_offset.path_samples),
            (by_curvature.start, by_curvature.control, by_curvature.end,
             *by_curvature.path_samples),
        ):
            self.assertAlmostEqual(first.x, second.x, places=9)
            self.assertAlmostEqual(first.y, second.y, places=9)
        self.assertEqual(by_offset.label_position, by_curvature.label_position)
        self.assertEqual(by_offset.label_box, by_curvature.label_box)

    def test_figure_spec_parses_dimensions(self) -> None:
        scene = compile_figure_spec({
            "version": 2,
            "points": {"A": [0, 0], "B": [70, 0]},
            "segments": {"AB": ["A", "B"]},
            "labels": {"A": "A", "B": "B"},
            "dimensions": {
                "AB_length": {
                    "points": ["A", "B"],
                    "label": "12 cm",
                    "side": "auto",
                    "curvature": 19,
                    "inset": 3,
                    "font_size": 12,
                },
            },
        })

        self.assertIn("AB_length", scene.dimensions)
        mark = scene.dimensions["AB_length"]
        self.assertEqual((mark.p1, mark.p2, mark.label), ("A", "B", "12 cm"))
        self.assertEqual(mark.offset, 19.0)
        self.assertEqual(mark.inset, 3.0)
        self.assertEqual(mark.font_size, 12.0)
        self.assertIn("AB_length", scene.resolve().dimension_layouts)
        assessment = assess_svg(scene.render_svg(), run_pixel_lint=True)
        self.assertTrue(
            assessment.accepted,
            assessment.security_issues + assessment.issues,
        )

    def test_invalid_dimension_contracts_fail_closed(self) -> None:
        base = {
            "version": 2,
            "points": {"A": [0, 0], "B": [40, 0]},
            "segments": {"AB": ["A", "B"]},
        }
        cases = {
            "invalid_side": {"points": ["A", "B"], "label": "4 cm", "side": "above"},
            "unknown_ref": {"points": ["A", "Z"], "label": "4 cm"},
            "zero_segment": {"points": ["A", "A"], "label": "4 cm"},
            "zero_offset": {"points": ["A", "B"], "label": "4 cm", "offset": 0},
            "negative_offset": {"points": ["A", "B"], "label": "4 cm", "offset": -1},
            "nonfinite_offset": {
                "points": ["A", "B"], "label": "4 cm", "offset": float("inf"),
            },
            "negative_inset": {"points": ["A", "B"], "label": "4 cm", "inset": -1},
            "inset_consumes_segment": {
                "points": ["A", "B"], "label": "4 cm", "inset": 20,
            },
            "conflicting_aliases": {
                "points": ["A", "B"], "label": "4 cm",
                "offset": 12, "curvature": 12,
            },
        }
        for label, dimension in cases.items():
            with self.subTest(case=label):
                spec = dict(base)
                spec["dimensions"] = {"bad": dimension}
                with self.assertRaises(FigureSpecError):
                    compile_figure_spec(spec)


class DensePointLabelClearanceTest(unittest.TestCase):
    def test_automatic_abc_labels_clear_every_rendered_segment(self) -> None:
        scene = FigureScene(background="white")
        for name, x, y in (
            ("A", 0, 0), ("B", 80, 0), ("C", 40, 48),
            ("D", 40, -30), ("E", 18, 22), ("F", 62, 22),
        ):
            scene.add_point(name, x, y)
        for name, first, second in (
            ("AB", "A", "B"), ("AC", "A", "C"), ("BC", "B", "C"),
            ("AD", "A", "D"), ("BD", "B", "D"), ("CD", "C", "D"),
            ("EF", "E", "F"),
        ):
            scene.add_segment(name, first, second)
        for point_name in ("A", "B", "C"):
            scene.add_point_label(point_name, position="auto")

        resolved = scene.resolve()
        for point_name in ("A", "B", "C"):
            label_box = resolved.label_boxes[point_name]
            for segment_name, segment in scene.segments.items():
                self.assertFalse(
                    _segment_intersects_box(
                        scene.points[segment.p1], scene.points[segment.p2], label_box,
                    ),
                    f"label {point_name} overlaps rendered segment {segment_name}",
                )
        for first, second in (("A", "B"), ("A", "C"), ("B", "C")):
            self.assertFalse(
                _boxes_overlap(resolved.label_boxes[first], resolved.label_boxes[second]),
                f"labels {first} and {second} overlap",
            )

        svg = scene.render_svg()
        self.assertEqual(lint_svg(svg), [])
        assessment = assess_svg(svg, run_pixel_lint=True)
        self.assertTrue(
            assessment.accepted,
            assessment.security_issues + assessment.issues,
        )


class StrictFigureSpecTest(unittest.TestCase):
    def test_invalid_specs_fail_closed(self) -> None:
        cases = {
            "version": {"version": 1},
            "boolean_number": {"version": 2, "points": {"A": [True, 0]}},
            "unknown_field": {"version": 2, "surprise": []},
            "unknown_reference": {
                "version": 2,
                "points": {"A": [0, 0]},
                "segments": {"AB": ["A", "B"]},
            },
            "duplicate_name": {
                "version": 2,
                "points": [
                    {"name": "A", "x": 0, "y": 0},
                    {"name": "A", "x": 1, "y": 1},
                ],
            },
            "zero_segment": {
                "version": 2,
                "points": {"A": [0, 0], "B": [0, 0]},
                "segments": {"AB": ["A", "B"]},
            },
            "parallel_intersection": {
                "version": 2,
                "points": {
                    "A": [0, 0], "B": [10, 0],
                    "C": [0, 1], "D": [10, 1],
                    "P": {"type": "intersection", "segments": ["AB", "CD"]},
                },
                "segments": {"AB": ["A", "B"], "CD": ["C", "D"]},
            },
            "outside_intersection": {
                "version": 2,
                "points": {
                    "A": [0, 0], "B": [1, 0],
                    "C": [2, -1], "D": [2, 1],
                    "P": {"type": "intersection", "segments": ["AB", "CD"]},
                },
                "segments": {"AB": ["A", "B"], "CD": ["C", "D"]},
            },
            "degenerate_angle": {
                "version": 2,
                "points": {"V": [0, 0], "A": [1, 0], "B": [2, 0]},
                "angles": {
                    "AVB": {"vertex": "V", "points": ["A", "B"], "label": "x"}
                },
            },
            "angle_without_drawn_rays": {
                "version": 2,
                "points": {"V": [0, 0], "A": [10, 0], "B": [0, 10]},
                "angles": {
                    "AVB": {"vertex": "V", "points": ["A", "B"], "label": "x"}
                },
            },
            "unsafe_paint_reference": {
                "version": 2,
                "style": {"stroke": "url(http://evil.example/a.svg#x)"},
                "points": {"A": [0, 0], "B": [10, 0]},
                "segments": {"AB": ["A", "B"]},
            },
            "unsafe_dash": {
                "version": 2,
                "points": {"A": [0, 0], "B": [10, 0]},
                "segments": {"AB": {"points": ["A", "B"], "dash": "4;url(x)"}},
            },
        }

        for label, spec in cases.items():
            with self.subTest(case=label):
                with self.assertRaises(FigureSpecError):
                    compile_figure_spec(spec)

    def test_tiny_perpendicular_segments_intersect_without_false_parallel_error(self) -> None:
        scene = FigureScene(background="transparent")
        scene.add_point("A", 0, 0).add_point("B", 1.0e-6, 0)
        scene.add_point("C", 0, 0).add_point("D", 0, 1.0e-6)
        scene.add_segment("AB", "A", "B").add_segment("CD", "C", "D")
        scene.intersection("P", "AB", "CD")
        self.assertAlmostEqual(scene.points["P"].x, 0.0, places=15)
        self.assertAlmostEqual(scene.points["P"].y, 0.0, places=15)

    def test_malicious_label_text_is_escaped_as_text(self) -> None:
        payload = '<script onclick="steal()">&data</script>'
        scene = compile_figure_spec({
            "version": 2,
            "points": {"A": [0, 0], "B": [30, 0]},
            "segments": {"AB": ["A", "B"]},
            "labels": {"A": payload},
        })

        svg = scene.render_svg()
        root = ET.fromstring(svg)
        texts = root.findall(".//{*}text")

        self.assertNotIn("<script", svg.lower())
        self.assertIn('&lt;script onclick="steal()"&gt;', svg)
        self.assertEqual([element.text for element in texts], [payload])
        self.assertEqual(root.findall(".//{*}script"), [])
        self.assertFalse(any(
            attribute.lower().startswith("on")
            for element in root.iter()
            for attribute in element.attrib
        ))


class StructuredGeneratorInventoryTest(unittest.TestCase):
    SPEC = {
        "version": 2,
        "points": {"A": [0, 0], "B": [30, 0]},
        "segments": {"AB": ["A", "B"]},
        "labels": {"A": "A", "B": "B"},
    }

    def test_transcript_missing_spec_label_is_rejected(self) -> None:
        candidate, issue = _compile_structured_candidate({
            "figure_spec": self.SPEC,
            "svg": "<svg>must not be used</svg>",
            "desc": "A가 표시된 선분",
        })

        self.assertIsNone(candidate)
        self.assertIsNotNone(issue)
        self.assertIn("B", issue)

    def test_transcript_extra_point_omitted_from_spec_is_rejected(self) -> None:
        candidate, issue = _compile_structured_candidate({
            "figure_spec": self.SPEC,
            "svg": "<svg>must not be used</svg>",
            "desc": "A B C",
        })

        self.assertIsNone(candidate)
        self.assertIsNotNone(issue)
        self.assertIn("C", issue)

    def test_model_candidate_requires_nonempty_transcription(self) -> None:
        candidate, issue = _compile_structured_candidate({
            "figure_spec": self.SPEC,
            "svg": "<svg>must not be used</svg>",
            "desc": "",
        })
        self.assertIsNone(candidate)
        self.assertIn("desc", issue)

    def test_structured_dimension_is_compiled_and_inventory_checked(self) -> None:
        spec = {
            "version": 2,
            "points": {"A": [0, 0], "B": [70, 0]},
            "segments": {"AB": ["A", "B"]},
            "labels": {"A": "A", "B": "B"},
            "dimensions": {
                "AB_len": {"points": ["A", "B"], "label": "12 cm"},
            },
        }
        candidate, issue = _compile_structured_candidate({
            "figure_spec": spec,
            "svg": "<svg>must not be used</svg>",
            "desc": "선분 A B의 길이는 12 cm",
        })
        self.assertIsNone(issue)
        self.assertIn("12 cm", candidate or "")
        self.assertIn("stroke-dasharray", candidate or "")
        self.assertTrue(assess_svg(candidate or "", run_pixel_lint=True).accepted)

        missing_candidate, missing_issue = _compile_structured_candidate({
            "figure_spec": spec,
            "svg": "<svg>must not be used</svg>",
            "desc": "선분 A B",
        })
        self.assertIsNone(missing_candidate)
        self.assertIn("12 cm", missing_issue or "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
