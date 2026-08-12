# -*- coding: utf-8 -*-
"""Legacy SVG dimension-curve and rich-label regression tests.

The v1 helper contract is intentionally split at the trust boundary:

* ``dim_label``/``measured`` receive plain text and must XML-escape it.
* Rich ``tspan`` content is legacy trusted markup only.  It still has to pass
  the central SVG allowlist before it can be rendered.

The Wangseon q1 expected-failure records the current call-site regression:
``measured`` is correctly treating a rich string as plain text, so the literal
``<tspan ...>`` source is displayed instead of an italic ``x``.  A production
fix should add a structured trusted-run API (not a raw-XML escape hatch), move
that call site to it, and then remove ``expectedFailure``.
"""
from __future__ import annotations

import math
import runpy
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.figure_quality import assess_svg  # noqa: E402
from core.figure_svg import (  # noqa: E402
    SVGTextRun,
    dim_label,
    halo_text,
    lint_svg,
    meas,
    measured,
    measured_runs,
    txt,
)


def _svg(body: str, *, width: int = 140, height: int = 80) -> str:
    return (
        f'<svg viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg">{body}</svg>'
    )


def _local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


class DimensionCurveGeometryTest(unittest.TestCase):
    def test_curve_has_inset_ends_and_requested_midpoint_offset(self) -> None:
        fragment = meas(10, 20, 110, 20, off=12)
        path = ET.fromstring(fragment)

        self.assertEqual(path.attrib["stroke-dasharray"], "4 3")
        numbers = [float(token) for token in path.attrib["d"].split()[1::3]]
        # The exact v1 path is M(13,23) Q(60,41) (107,23).  A quadratic
        # Bezier with those controls reaches y=32 at t=.5: 12 px off y=20.
        self.assertEqual(path.attrib["d"], "M 13.0 23.0 Q 60.0 41.0 107.0 23.0")
        self.assertTrue(all(math.isfinite(value) for value in numbers))
        midpoint_y = 0.25 * 23.0 + 0.5 * 41.0 + 0.25 * 23.0
        self.assertAlmostEqual(midpoint_y, 32.0)

    def test_curve_and_label_share_the_same_normal_offset(self) -> None:
        fragment = measured(10, 20, 110, 20, -12, "24 cm", fs=12)
        root = ET.fromstring(_svg(fragment))
        path = next(element for element in root if _local_name(element) == "path")
        label = next(element for element in root if _local_name(element) == "text")

        self.assertEqual(path.attrib["d"], "M 13.0 17.0 Q 60.0 -1.0 107.0 17.0")
        self.assertEqual(label.attrib["x"], "60.0")
        # Curve midpoint is y=8; text baseline adds the documented 0.35*fs.
        self.assertEqual(label.attrib["y"], "12.2")
        self.assertEqual(label.attrib["paint-order"], "stroke")
        self.assertEqual(label.attrib["stroke"], "#fff")

    def test_zero_length_dimension_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            meas(5, 5, 5, 5)
        with self.assertRaises(ValueError):
            dim_label(5, 5, 5, 5, 8, "x cm")


class DimensionLabelTrustBoundaryTest(unittest.TestCase):
    def test_plain_dimension_text_escapes_xml_injection(self) -> None:
        payload = '<script onload="alert(1)">x & y</script>'
        fragment = dim_label(10, 40, 130, 40, -10, payload, fs=12)
        root = ET.fromstring(_svg(f'<line x1="5" y1="40" x2="135" y2="40" '
                                  f'stroke="#000"/>{fragment}'))
        label = next(element for element in root if _local_name(element) == "text")

        self.assertEqual(label.text, payload)
        self.assertEqual(list(label), [])
        self.assertNotIn("<script", fragment)
        self.assertIn("&lt;script", fragment)
        result = assess_svg(ET.tostring(root, encoding="unicode"), run_pixel_lint=False)
        self.assertTrue(result.accepted, result.security_issues + result.issues)

    def test_trusted_tspan_passes_but_injected_element_fails_allowlist(self) -> None:
        safe = halo_text(
            70,
            34,
            '<tspan font-style="italic">x</tspan> cm',
            fs=12,
        )
        safe_result = assess_svg(
            _svg('<line x1="5" y1="40" x2="135" y2="40" '
                 f'stroke="#000"/>{safe}'),
            run_pixel_lint=False,
        )
        self.assertTrue(safe_result.accepted, safe_result.security_issues + safe_result.issues)
        safe_root = ET.fromstring(safe_result.sanitized_svg or "")
        self.assertEqual(len(safe_root.findall(".//{*}tspan")), 1)

        injected = halo_text(70, 34, '<script onload="alert(1)">x</script>', fs=12)
        injected_result = assess_svg(
            _svg('<line x1="5" y1="40" x2="135" y2="40" '
                 f'stroke="#000"/>{injected}'),
            run_pixel_lint=False,
        )
        self.assertFalse(injected_result.accepted)
        self.assertIsNone(injected_result.sanitized_svg)
        self.assertTrue(injected_result.security_issues)

    def test_structured_runs_escape_text_and_preserve_emphasis(self) -> None:
        fragment = measured_runs(
            10, 40, 130, 40, -10,
            (SVGTextRun("x", italic=True), SVGTextRun(" <cm>")),
            fs=12,
        )
        root = ET.fromstring(_svg(fragment))
        label = root.findall(".//{*}text")[0]
        runs = label.findall("./{*}tspan")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].attrib.get("font-style"), "italic")
        self.assertEqual(runs[0].text, "x")
        self.assertEqual(runs[0].tail, " <cm>")
        self.assertNotIn("<cm>", fragment)

    def test_wangseon_q1_renders_italic_x_run_instead_of_literal_markup(self) -> None:
        corpus_path = (
            ROOT
            / "corpus"
            / "[왕선중][3][25-2-기말] (원본)"
            / "fig_svgs.py"
        )
        namespace = runpy.run_path(str(corpus_path))
        root = ET.fromstring(namespace["S"]["q1"])
        labels = root.findall(".//{*}text")
        dimension = next(
            label for label in labels
            if any(run.attrib.get("font-style") == "italic"
                   for run in label.findall("./{*}tspan"))
        )

        runs = dimension.findall("./{*}tspan")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].attrib.get("font-style"), "italic")
        self.assertEqual(runs[0].text, "x")
        self.assertEqual(runs[0].tail, " cm")

    def test_linter_flags_point_label_drawn_through_a_segment(self) -> None:
        body = (
            '<line x1="10" y1="40" x2="130" y2="40" '
            'stroke="#000" stroke-width="2"/>'
            + txt(70, 44, "A", fs=16)
        )
        issues = lint_svg(_svg(body))
        self.assertTrue(any("'A'" in issue for issue in issues), issues)


if __name__ == "__main__":
    unittest.main()
