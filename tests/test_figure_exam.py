# -*- coding: utf-8 -*-
"""기출 재작도 공용 도구(core.figure_exam) + 엔진 단독 이식 회귀.

2026-10-21: 세션 변환 `fig_svgs.py` 들이 복사해 쓰던 헬퍼를 `core.figure_exam` 으로 모았다.
같은 날 todays-math(`vendor/figure-engine` = 엔진 파일만 옮긴 곳)에서 `lint_svg` 가
`No module named 'core.figure_generator'` 로 **아예 돌지 않는 것**을 실측했다 — 래스터화를
API 키 설정까지 끌고 오는 `figure_generator` 에서 빌려 썼기 때문이다. 아래 A 가 그 환경을
그대로 재현해 막는다(엔진 파일만 임시 폴더로 복사 → 격리 실행).

(제일고·오성중 스크립트와 헬퍼·PNG 가 바이트 단위로 같다는 대조는 일회성으로 마쳤다 —
corpus 스크립트를 테스트가 import 하면 시험지 폴더가 테스트 의존이 된다.)
"""
import ast
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import core.figure_exam as fe  # noqa: E402
from core.figure_svg import verify_figure  # noqa: E402

ENGINE = ("__init__", "figure_svg", "figure_scene", "figure_solid", "figure_quality",
          "label_markup", "figure_exam", "figure_spec_repair")


class VendorOnlyTest(unittest.TestCase):
    """A. 엔진 파일만 옮겨 간 곳에서도 픽셀 검수·빌드가 돈다."""

    def test_engine_files_alone(self):
        tmp = tempfile.mkdtemp(prefix="fe_vendor_")
        try:
            os.makedirs(os.path.join(tmp, "core"))
            for name in ENGINE:
                shutil.copy(os.path.join(ROOT, "core", f"{name}.py"), os.path.join(tmp, "core"))
            script = textwrap.dedent(f"""
                import sys
                sys.path.insert(0, {tmp!r})
                from core.figure_exam import FigureSet, ltext, raw_svg
                from core.figure_svg import line, lint_svg, verify_figure
                svg = raw_svg(120, 60, line((10, 30), (110, 30), w=1.9))
                assert lint_svg(svg) == [], lint_svg(svg)
                figs = FigureSet()
                verify_figure("q1", lengths=[(5, (10, 30), (110, 30))])
                figs.raw("q1", 120, 60, line((10, 30), (110, 30), w=1.9), ltext(60, 12, "5"))
                rep = figs.build({os.path.join(tmp, 'out')!r})
                assert rep["q1"]["issues"] == [], rep
                # 모델 FigureSpec 의 장식 칸(pos)은 벗기고 그린다 — 정리 모듈도 단독으로 돈다
                from core.figure_spec_repair import compile_with_repair
                spec = {{"version": 2, "points": {{"A": [0, 0], "B": [120, 0], "C": [40, 70]}},
                        "segments": {{"s1": ["A", "B"], "s2": ["B", "C"], "s3": ["C", "A"]}},
                        "labels": {{"A": {{"text": "A", "pos": "below"}}}}}}
                scene, svg, repairs = compile_with_repair(spec)
                assert repairs and "<svg" in svg, repairs
                bad = [m for m in sys.modules if m.startswith(("core.figure_generator", "utils"))]
                assert not bad, bad
                print("VENDOR_OK")
            """)
            r = subprocess.run([sys.executable, "-I", "-c", script], capture_output=True,
                               text=True, encoding="utf-8", cwd=tmp)
            self.assertIn("VENDOR_OK", r.stdout, r.stderr[-1500:])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_top_level_imports_stdlib_and_engine_only(self):
        """numpy·PIL 은 함수 안에서만(todays-math vendoredFigureEngine 규칙과 같다)."""
        for name in ("figure_svg", "figure_exam", "figure_spec_repair"):
            tree = ast.parse(open(os.path.join(ROOT, "core", f"{name}.py"), encoding="utf-8").read())
            mods = set()
            for node in tree.body:
                if isinstance(node, ast.Import):
                    mods |= {a.name.split(".")[0] for a in node.names}
                elif isinstance(node, ast.ImportFrom) and node.module:
                    mods.add(node.module)
            heavy = {m for m in mods if m.split(".")[0] in ("numpy", "PIL", "utils", "anthropic")
                     or m == "core.figure_generator"}
            self.assertEqual(heavy, set(), name)


class HelperTest(unittest.TestCase):
    """B. 작도 관용구의 규칙."""

    def test_width_rule(self):
        self.assertEqual(fe.width_mm(fe.raw_svg(300, 100)), 51)       # 300 × 0.17
        self.assertEqual(fe.width_mm(fe.raw_svg(600, 100)), 68)       # 상한
        figs = fe.FigureSet()
        figs.raw("a", 300, 100)
        self.assertEqual(figs.widths({"7": "a"}), {"7": {"key": "a", "width_mm": 51}})

    def test_fit_contains_points_with_padding(self):
        pts = [(3.0, -4.0), (50.0, 12.0)]
        (dx, dy), (w, h) = fe.fit(pts, (10, 20, 30, 40))
        xs = [p[0] + dx for p in pts]
        ys = [p[1] + dy for p in pts]
        self.assertAlmostEqual(min(xs), 10)
        self.assertAlmostEqual(min(ys), 20)
        self.assertAlmostEqual(w - max(xs), 30)
        self.assertAlmostEqual(h - max(ys), 40)

    def test_oblique_height_scale_keeps_floor(self):
        """zs 는 높이만 키운다 — 바닥(z=0) 점은 그대로."""
        f1, f2 = fe.oblique((0, 0), 40, 0.5, 45), fe.oblique((0, 0), 40, 0.5, 45, zs=2.0)
        self.assertEqual(f1((3, 2, 0)), f2((3, 2, 0)))
        self.assertNotEqual(f1((3, 2, 1)), f2((3, 2, 1)))

    def test_adim_label_on_convex_side(self):
        """라벨은 치수 곡선 **바깥**(o 부호 쪽)에 앉는다."""
        p, q = (0.0, 0.0), (100.0, 0.0)          # p→q 오른쪽, 법선 (-uy, ux) = (0, 1) = 아래
        for o, below in ((10, True), (-10, False)):
            s = fe.adim(p, q, o, "7")
            y = float(s.split('<text x="')[1].split('y="')[1].split('"')[0])
            self.assertEqual(y > 0, below, (o, y))

    def test_rtext_upright_vs_ltext(self):
        self.assertIn('font-style="normal"', fe.rtext(0, 0, "30 m"))
        self.assertIn("italic", fe.ltext(0, 0, "m"))     # 한 글자 m 은 변수로 기울어진다


class BuildGateTest(unittest.TestCase):
    """C. 빌드 = 검산 누락 차단 → lint → PNG."""

    def setUp(self):
        self.out = tempfile.mkdtemp(prefix="fe_build_")

    def tearDown(self):
        shutil.rmtree(self.out, ignore_errors=True)

    def test_unverified_measure_label_blocks(self):
        figs = fe.FigureSet()
        figs.raw("nv", 120, 60, fe.ltext(60, 30, "5 cm"))
        with self.assertRaises(ValueError):
            figs.build(self.out)

    def test_verified_builds_png(self):
        figs = fe.FigureSet()
        A, B = (10.0, 40.0), (110.0, 40.0)
        verify_figure("ok", lengths=[(5, A, B)])
        figs.raw("ok", 120, 70, fe.line(A, B, w=1.9), fe.adim(A, B, -10, "5"))
        rep = figs.build(self.out)
        self.assertTrue(os.path.getsize(rep["ok"]["png"]) > 0)
        self.assertEqual(rep["ok"]["issues"], [])
        with open(rep["ok"]["png"], "rb") as f:
            self.assertTrue(fe.flatten_white(f.read()).startswith(b"\x89PNG"))

    def test_lint_exempt_only_named_prefix(self):
        figs = fe.FigureSet()
        # 길이 라벨이 아니므로 검산 대상 아님 — viewBox 밖으로 나간 선(잘림)
        figs.raw("cut", 100, 50, fe.line((10, 25), (140, 25), w=1.9))
        with self.assertRaises(ValueError):
            figs.build(self.out)
        rep = figs.build(self.out, lint_exempt={"cut": ("잘림",)})
        self.assertEqual(rep["cut"]["issues"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
