# -*- coding: utf-8 -*-
"""SVG 보안 게이트와 그림 생성 재시도/폴백 회귀 테스트.

실제 비전 API, 네트워크, HWP COM을 사용하지 않는다.

실행:
    python tests/test_figure_generator_quality.py
    python -m pytest tests/test_figure_generator_quality.py -v
"""
from __future__ import annotations

import io
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import call, patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import core.figure_generator as generator  # noqa: E402
from core.figure_quality import (  # noqa: E402
    SvgAssessment,
    SvgSecurityError,
    assess_svg,
    sanitize_svg,
)


SAFE_SVG = """<svg xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 120 80" width="120" height="80" version="1.1">
  <desc>safe geometry fixture</desc>
  <circle cx="60" cy="40" r="25" fill="none" stroke="#000"
      stroke-width="1.5"/>
  <line x1="35" y1="40" x2="85" y2="40" stroke="#000"
      stroke-width="1"/>
  <text x="60" y="35" font-family="Times New Roman, Batang, serif"
      font-size="12" font-style="italic" text-anchor="middle"
      paint-order="stroke" stroke="#fff" stroke-width="4">A<tspan
      font-style="normal">1</tspan></text>
</svg>"""

SANITIZED_ONE = (
    '<svg viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">'
    '<line x1="2" y1="2" x2="18" y2="18" stroke="#000"/></svg>'
)
SANITIZED_TWO = (
    '<svg viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">'
    '<circle cx="10" cy="10" r="8" fill="none" stroke="#000"/></svg>'
)


def _model_result(svg: str, confidence: float = 0.99, *, vectorizable: bool = True) -> dict:
    return {"vectorizable": vectorizable, "confidence": confidence, "svg": svg}


def _accepted(svg: str) -> SvgAssessment:
    return SvgAssessment(sanitized_svg=svg, issues=[], security_issues=[], accepted=True)


def _rejected(*, issues: list[str] | None = None,
              security: list[str] | None = None) -> SvgAssessment:
    return SvgAssessment(
        sanitized_svg=None,
        issues=list(issues or []),
        security_issues=list(security or []),
        accepted=False,
    )


def _valid_png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (2, 2), (0, 0, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


class SvgQualityGateTest(unittest.TestCase):
    def test_safe_svg_is_sanitized_and_accepted(self) -> None:
        sanitized = sanitize_svg(SAFE_SVG)
        root = ET.fromstring(sanitized)

        self.assertEqual(root.tag.rsplit("}", 1)[-1], "svg")
        self.assertEqual(root.attrib["viewBox"], "0 0 120 80")
        self.assertNotIn("width", root.attrib)
        self.assertNotIn("height", root.attrib)
        self.assertNotIn("version", root.attrib)
        self.assertEqual(len(root.findall(".//{*}circle")), 1)
        self.assertEqual(len(root.findall(".//{*}line")), 1)
        self.assertEqual(len(root.findall(".//{*}text")), 1)
        self.assertEqual(len(root.findall(".//{*}tspan")), 1)

        result = assess_svg(SAFE_SVG, run_pixel_lint=False)
        self.assertTrue(result.accepted, result.issues + result.security_issues)
        self.assertEqual(result.sanitized_svg, sanitized)
        self.assertEqual(result.issues, [])
        self.assertEqual(result.security_issues, [])

    def test_unsafe_svg_vectors_fail_closed(self) -> None:
        attacks = {
            "script": (
                '<svg viewBox="0 0 10 10"><script>alert(1)</script>'
                '<line x1="0" y1="0" x2="10" y2="10" stroke="#000"/></svg>'
            ),
            "doctype": (
                '<!DOCTYPE svg SYSTEM "https://evil.example/svg.dtd">'
                '<svg viewBox="0 0 10 10"><line x1="0" y1="0" x2="10" '
                'y2="10" stroke="#000"/></svg>'
            ),
            "entity_declaration": (
                '<!ENTITY payload SYSTEM "file:///etc/passwd">'
                '<svg viewBox="0 0 10 10"><text x="1" y="5">x</text>'
                '<line x1="0" y1="0" x2="10" y2="10" stroke="#000"/></svg>'
            ),
            "custom_entity_reference": (
                '<svg viewBox="0 0 10 10"><text x="1" y="5">&payload;</text>'
                '<line x1="0" y1="0" x2="10" y2="10" stroke="#000"/></svg>'
            ),
            "event_handler": (
                '<svg viewBox="0 0 10 10" onload="alert(1)">'
                '<line x1="0" y1="0" x2="10" y2="10" stroke="#000"/></svg>'
            ),
            "href": (
                '<svg viewBox="0 0 10 10"><text x="1" y="5" '
                'href="https://evil.example/">x</text>'
                '<line x1="0" y1="0" x2="10" y2="10" stroke="#000"/></svg>'
            ),
            "style_attribute": (
                '<svg viewBox="0 0 10 10"><line x1="0" y1="0" x2="10" '
                'y2="10" style="stroke:#000"/></svg>'
            ),
            "url_reference": (
                '<svg viewBox="0 0 10 10"><circle cx="5" cy="5" r="4" '
                'fill="url(https://evil.example/a.svg#paint)"/></svg>'
            ),
            "transform": (
                '<svg viewBox="0 0 10 10"><g transform="translate(1 1)">'
                '<line x1="0" y1="0" x2="8" y2="8" stroke="#000"/>'
                '</g></svg>'
            ),
            "missing_viewbox": (
                '<svg><line x1="0" y1="0" x2="10" y2="10" '
                'stroke="#000"/></svg>'
            ),
            "shifted_viewbox": (
                '<svg viewBox="-1 0 10 10"><line x1="0" y1="0" x2="10" '
                'y2="10" stroke="#000"/></svg>'
            ),
            "zero_viewbox": (
                '<svg viewBox="0 0 0 10"><line x1="0" y1="0" x2="10" '
                'y2="10" stroke="#000"/></svg>'
            ),
            "nonfinite_viewbox": (
                '<svg viewBox="0 0 NaN 10"><line x1="0" y1="0" x2="10" '
                'y2="10" stroke="#000"/></svg>'
            ),
            "huge_viewbox": (
                '<svg viewBox="0 0 100000 100000"><line x1="0" y1="0" '
                'x2="10" y2="10" stroke="#000"/></svg>'
            ),
            "extreme_aspect": (
                '<svg viewBox="0 0 1 1000"><line x1="0" y1="0" '
                'x2="1" y2="999" stroke="#000"/></svg>'
            ),
        }

        for label, payload in attacks.items():
            with self.subTest(vector=label):
                with self.assertRaises(SvgSecurityError):
                    sanitize_svg(payload)
                result = assess_svg(payload, run_pixel_lint=False)
                self.assertFalse(result.accepted)
                self.assertIsNone(result.sanitized_svg)
                self.assertEqual(result.issues, [])
                self.assertTrue(result.security_issues)

    def test_blank_or_hidden_geometry_is_rejected(self) -> None:
        blanks = {
            "zero_length_path": (
                '<svg viewBox="0 0 10 10"><path d="M1 1 L1 1" '
                'fill="none" stroke="#000"/></svg>'
            ),
            "hidden_by_parent": (
                '<svg viewBox="0 0 10 10"><g opacity="0"><path opacity="1" '
                'd="M1 1 L9 9" fill="none" stroke="#000"/></g></svg>'
            ),
            "white_only": (
                '<svg viewBox="0 0 10 10"><line x1="1" y1="1" x2="9" '
                'y2="9" stroke="#fff"/></svg>'
            ),
        }
        for label, payload in blanks.items():
            with self.subTest(blank=label):
                result = assess_svg(payload, run_pixel_lint=True)
                self.assertFalse(result.accepted)
                self.assertTrue(result.issues)

    def test_pixel_lint_work_budget_rejects_many_labels(self) -> None:
        labels = "".join(
            f'<text x="10" y="{10 + index}" font-size="4">A</text>'
            for index in range(81)
        )
        payload = (
            '<svg viewBox="0 0 120 120"><line x1="1" y1="1" x2="119" '
            f'y2="119" stroke="#000"/>{labels}</svg>'
        )
        result = assess_svg(payload, run_pixel_lint=True)
        self.assertFalse(result.accepted)
        self.assertTrue(any("text limit" in issue for issue in result.issues))

    def test_invisible_outside_and_fake_halo_labels_are_rejected(self) -> None:
        cases = {
            "outside": (
                '<circle cx="50" cy="50" r="30" fill="none" stroke="#000"/>'
                '<text x="1000" y="1000">A</text>'
            ),
            "white": (
                '<circle cx="50" cy="50" r="30" fill="none" stroke="#000"/>'
                '<text x="50" y="50" fill="rgb(100%,100%,100%)">A</text>'
            ),
            "fake_halo": (
                '<line x1="10" y1="50" x2="90" y2="50" stroke="#000"/>'
                '<text x="50" y="53" paint-order="fill">A</text>'
            ),
            "far_geometry": (
                '<circle cx="50" cy="50" r="30" fill="none" stroke="#000"/>'
                '<line x1="1000" y1="1000" x2="1010" y2="1010" stroke="#000"/>'
            ),
            "oversized_halo": (
                '<circle cx="50" cy="50" r="30" fill="none" stroke="#000"/>'
                '<text x="50" y="53" font-size="12" paint-order="stroke" '
                'stroke="#fff" stroke-width="256">A</text>'
            ),
            "current_color": (
                '<circle cx="50" cy="50" r="30" fill="none" stroke="#000"/>'
                '<g color="white"><line x1="10" y1="10" x2="90" y2="90" '
                'stroke="currentColor"/></g>'
            ),
            "transparent_hex_text_group": (
                '<circle cx="50" cy="50" r="30" fill="none" stroke="#000"/>'
                '<g fill="#0000"><text x="50" y="50">A</text></g>'
            ),
            "transparent_hex_geometry_group": (
                '<line x1="10" y1="10" x2="90" y2="90" stroke="#000"/>'
                '<g stroke="#00000000"><circle cx="50" cy="50" r="30" '
                'fill="none"/></g>'
            ),
            "hidden_tspan": (
                '<line x1="10" y1="50" x2="90" y2="50" stroke="#000"/>'
                '<text x="20" y="30">A<tspan fill="#0000">B</tspan></text>'
            ),
            "white_alpha_tspan": (
                '<line x1="10" y1="50" x2="90" y2="50" stroke="#000"/>'
                '<text x="20" y="30">A<tspan fill="#ffffff80">B</tspan></text>'
            ),
            "far_tspan": (
                '<line x1="10" y1="50" x2="90" y2="50" stroke="#000"/>'
                '<text x="20" y="30">A<tspan x="10000">B</tspan></text>'
            ),
            "padded_far_tspan": (
                '<line x1="10" y1="50" x2="90" y2="50" stroke="#000"/>'
                '<text x="20" y="30">A<tspan x="150">B</tspan></text>'
            ),
            "relative_tspan_shift": (
                '<line x1="10" y1="50" x2="90" y2="50" stroke="#000"/>'
                '<text x="20" y="30">A<tspan dx="150">B</tspan></text>'
            ),
        }
        for label, body in cases.items():
            with self.subTest(label=label):
                result = assess_svg(
                    f'<svg viewBox="0 0 100 100">{body}</svg>',
                    run_pixel_lint=True,
                )
                self.assertFalse(result.accepted, result)


class FigureGeneratorPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out_dir = self.tmp.name
        self.image = Image.new("RGBA", (2, 2), (0, 0, 0, 0))
        self.png = _valid_png_bytes()
        self.expected_path = str(Path(self.out_dir) / "fixture.png")

    def _render(self, hint: str = "geometry") -> tuple[str | None, str]:
        return generator.render_figure(
            self.image, hint, self.out_dir, "fixture", api_key="unused-test-key"
        )

    def test_first_attempt_success_renders_only_sanitized_svg(self) -> None:
        raw = "<svg>RAW MODEL OUTPUT</svg>"
        with (
            patch.object(generator, "_vision_to_svg", return_value=_model_result(raw)) as vision,
            patch.object(generator, "_assess_generated_svg",
                         return_value=_accepted(SANITIZED_ONE)) as gate,
            patch.object(generator, "_svg_to_png_bytes", return_value=self.png) as rasterize,
            patch.object(generator, "_save_raster") as crop,
        ):
            result = self._render()

        self.assertEqual(result, (self.expected_path, "svg"))
        self.assertTrue(Path(self.expected_path).is_file())
        self.assertEqual(vision.call_count, 1)
        self.assertIsNone(vision.call_args.kwargs["feedback"])
        gate.assert_called_once_with(raw)
        rasterize.assert_called_once_with(SANITIZED_ONE)
        crop.assert_not_called()

    def test_gate_rejection_retries_with_feedback_then_succeeds(self) -> None:
        raw_one, raw_two = "raw-one", "raw-two"
        first = _rejected(
            security=["blocked <script>"],
            issues=["label overlap", "blocked <script>"],
        )
        with (
            patch.object(generator, "_vision_to_svg",
                         side_effect=[_model_result(raw_one), _model_result(raw_two)]) as vision,
            patch.object(generator, "_assess_generated_svg",
                         side_effect=[first, _accepted(SANITIZED_TWO)]) as gate,
            patch.object(generator, "_svg_to_png_bytes", return_value=self.png) as rasterize,
            patch.object(generator, "_save_raster") as crop,
        ):
            result = self._render()

        self.assertEqual(result, (self.expected_path, "svg"))
        self.assertEqual(vision.call_count, 2)
        feedback = vision.call_args_list[1].kwargs["feedback"]
        self.assertEqual(feedback, "blocked <script>\nlabel overlap")
        self.assertEqual(gate.call_args_list, [call(raw_one), call(raw_two)])
        rasterize.assert_called_once_with(SANITIZED_TWO)
        crop.assert_not_called()

    def test_two_gate_rejections_fall_back_to_crop(self) -> None:
        rejected = _rejected(issues=["label collision"])
        with (
            patch.object(generator, "_vision_to_svg",
                         return_value=_model_result("raw")) as vision,
            patch.object(generator, "_assess_generated_svg",
                         return_value=rejected) as gate,
            patch.object(generator, "_svg_to_png_bytes") as rasterize,
            patch.object(generator, "_save_raster",
                         return_value=self.expected_path) as crop,
        ):
            result = self._render()

        self.assertEqual(result, (self.expected_path, "crop"))
        self.assertEqual(vision.call_count, generator.SVG_GENERATION_ATTEMPTS)
        self.assertEqual(gate.call_count, generator.SVG_GENERATION_ATTEMPTS)
        self.assertIn("label collision", vision.call_args_list[1].kwargs["feedback"])
        rasterize.assert_not_called()
        crop.assert_called_once()

    def test_render_failure_retries_then_succeeds(self) -> None:
        with (
            patch.object(generator, "_vision_to_svg",
                         side_effect=[_model_result("raw-one"),
                                      _model_result("raw-two")]) as vision,
            patch.object(generator, "_assess_generated_svg",
                         side_effect=[_accepted(SANITIZED_ONE),
                                      _accepted(SANITIZED_TWO)]) as gate,
            patch.object(generator, "_svg_to_png_bytes",
                         side_effect=[None, self.png]) as rasterize,
            patch.object(generator, "_save_raster",
                         return_value=self.expected_path) as crop,
        ):
            result = self._render()

        self.assertEqual(result, (self.expected_path, "crop"))
        self.assertEqual(vision.call_count, 1)
        self.assertEqual(gate.call_count, 1)
        rasterize.assert_called_once_with(SANITIZED_ONE)
        crop.assert_called_once()

    def test_low_confidence_falls_back_without_gate_or_retry(self) -> None:
        low = generator.CONFIDENCE_THRESHOLD - 0.01
        with (
            patch.object(generator, "_vision_to_svg",
                         return_value=_model_result("raw", confidence=low)) as vision,
            patch.object(generator, "_assess_generated_svg") as gate,
            patch.object(generator, "_svg_to_png_bytes") as rasterize,
            patch.object(generator, "_save_raster",
                         return_value=self.expected_path) as crop,
        ):
            result = self._render()

        self.assertEqual(result, (self.expected_path, "crop"))
        vision.assert_called_once()
        gate.assert_not_called()
        rasterize.assert_not_called()
        crop.assert_called_once()

    def test_photo_hint_skips_vision_and_falls_back_immediately(self) -> None:
        with (
            patch.object(generator, "_vision_to_svg") as vision,
            patch.object(generator, "_assess_generated_svg") as gate,
            patch.object(generator, "_svg_to_png_bytes") as rasterize,
            patch.object(generator, "_save_raster",
                         return_value=self.expected_path) as crop,
        ):
            result = self._render("  [PHOTO] real-world scene")

        self.assertEqual(result, (self.expected_path, "crop"))
        vision.assert_not_called()
        gate.assert_not_called()
        rasterize.assert_not_called()
        crop.assert_called_once()

    def test_gate_exception_is_fail_closed_and_falls_back(self) -> None:
        with (
            patch.object(generator, "_vision_to_svg",
                         return_value=_model_result("raw")) as vision,
            patch.object(generator, "_assess_generated_svg",
                         side_effect=RuntimeError("gate exploded")) as gate,
            patch.object(generator, "_svg_to_png_bytes") as rasterize,
            patch.object(generator, "_save_raster",
                         return_value=self.expected_path) as crop,
        ):
            result = self._render()

        self.assertEqual(result, (self.expected_path, "crop"))
        self.assertEqual(vision.call_count, 1)
        self.assertEqual(gate.call_count, 1)
        rasterize.assert_not_called()
        crop.assert_called_once()

    def test_basename_cannot_escape_output_directory(self) -> None:
        with self.assertRaises(ValueError):
            generator.render_figure(
                self.image, "[photo]", self.out_dir, "..\\outside", api_key="unused"
            )

    def test_structured_spec_is_compiled_instead_of_raw_svg(self) -> None:
        spec = {
            "version": 2,
            "points": {"O": [30, 30]},
            "circles": {"c": {"center": "O", "radius": 18}},
        }
        compiled, issue = generator._compile_structured_candidate(
            {"svg": "<svg>untrusted raw</svg>", "figure_spec": spec}
        )
        self.assertIsNone(issue)
        self.assertIn("<circle", compiled)
        self.assertNotIn("untrusted raw", compiled)
        self.assertTrue(assess_svg(compiled, run_pixel_lint=True).accepted)


class LocalGradientAllowanceTests(unittest.TestCase):
    """구 음영 한 가지 경우만 여는 좁은 예외(사용자 승인 2026-08-13, "특정 경우에만").

    참조 기반 SVG 는 원래 통째로 막혀 있었다. 여는 순간 pattern·filter·clip-path·
    외부 URL 이 함께 열리기 쉬우므로 **막혀 있어야 할 것들이 여전히 막히는지**를
    허용 케이스와 같은 무게로 검사한다.
    """

    SPHERE = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        '<defs><radialGradient id="sph" cx="0.35" cy="0.32" r="0.75">'
        '<stop offset="0" stop-color="#ffffff"/>'
        '<stop offset="1" stop-color="#9a9a9a"/></radialGradient></defs>'
        '<circle cx="50" cy="50" r="40" fill="url(#sph)" stroke="#000" '
        'stroke-width="2"/></svg>'
    )

    def test_sphere_shading_is_accepted(self) -> None:
        out = sanitize_svg(self.SPHERE)
        self.assertIn("radialGradient", out)
        self.assertIn("url(#sph)", out)

    def test_dangling_reference_is_rejected(self) -> None:
        with self.assertRaises(SvgSecurityError):
            sanitize_svg(self.SPHERE.replace("url(#sph)", "url(#nope)"))

    def test_external_and_scheme_urls_stay_blocked(self) -> None:
        for bad in ("url(http://evil/x.png)", "url(//evil/x)"):
            with self.assertRaises(SvgSecurityError):
                sanitize_svg(self.SPHERE.replace("url(#sph)", bad))

    def test_other_reference_constructs_stay_blocked(self) -> None:
        cases = {
            "pattern": self.SPHERE.replace("radialGradient", "pattern"),
            "clip-path": self.SPHERE.replace('stroke="#000"', 'clip-path="url(#sph)"'),
            "filter": self.SPHERE.replace('stroke="#000"', 'filter="url(#sph)"'),
            "mask": self.SPHERE.replace('stroke="#000"', 'mask="url(#sph)"'),
        }
        for name, svg in cases.items():
            with self.subTest(name), self.assertRaises(SvgSecurityError):
                sanitize_svg(svg)

    def test_gradient_placement_rules(self) -> None:
        bad = [
            self.SPHERE.replace("<defs>", "").replace("</defs>", ""),
            self.SPHERE.replace("</radialGradient>",
                                '</radialGradient><circle cx="1" cy="1" r="1"/>'),
            self.SPHERE.replace('<stop offset="0" stop-color="#ffffff"/>',
                                '<circle cx="1" cy="1" r="1"/>'),
        ]
        for svg in bad:
            with self.assertRaises(SvgSecurityError):
                sanitize_svg(svg)

    def test_gradient_cannot_inherit_via_href(self) -> None:
        for attr in ('href="#o"', 'xlink:href="#o"'):
            with self.assertRaises(Exception):
                sanitize_svg(self.SPHERE.replace('id="sph"', f'id="sph" {attr}'))

    def test_script_and_style_stay_blocked(self) -> None:
        for bad in ("<script>x</script>", "<style>*{fill:red}</style>"):
            with self.assertRaises(SvgSecurityError):
                sanitize_svg(self.SPHERE.replace("<defs>", bad + "<defs>"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
