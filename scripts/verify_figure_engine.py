# -*- coding: utf-8 -*-
"""Figure Engine v2 security, layout, and legacy-corpus regression gate.

Run from the repository root::

    python scripts/verify_figure_engine.py

The full gate intentionally performs pixel lint on all 42 committed corpus
figures.  Use ``--quick`` while iterating to run structural assessment only;
the full command remains the pre-commit/PR contract.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import py_compile
import runpy
import subprocess
import sys
import time
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.figure_quality import assess_svg  # noqa: E402
from core.figure_svg import lint_svg  # noqa: E402


FIGURE_MODULES = (
    ROOT / "core" / "figure_generator.py",
    ROOT / "core" / "figure_quality.py",
    ROOT / "core" / "figure_scene.py",
    ROOT / "core" / "figure_svg.py",
)
FIGURE_TESTS = (
    "tests/test_figure_scene.py",
    "tests/test_figure_generator_quality.py",
    "tests/test_figure_svg_dimension.py",
)
EXPECTED_CORPUS_FIGURES = 42


def _compile_modules() -> None:
    for path in FIGURE_MODULES:
        py_compile.compile(str(path), doraise=True)
    print(f"[PASS] py_compile: {len(FIGURE_MODULES)} modules")


def _run_tests() -> None:
    command = [sys.executable, "-m", "pytest", *FIGURE_TESTS, "-q"]
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)
    print(f"[PASS] figure tests: {len(FIGURE_TESTS)} files")


def _load_corpus_figures(path: Path, index: int) -> dict[str, str]:
    # Corpus scripts have a render-only __main__ block and are safe to import.
    # Prevent even their portable temporary output directories from being
    # created during verification.
    with patch("os.makedirs"):
        namespace = runpy.run_path(str(path), run_name=f"_figure_verify_{index}")
    figures = namespace.get("S") or namespace.get("SVGS")
    if not isinstance(figures, dict):
        raise RuntimeError(f"{path}: S/SVGS figure dictionary not found")
    return figures


def _verify_corpus(*, quick: bool) -> None:
    corpus_files = sorted((ROOT / "corpus").rglob("fig_svgs.py"))
    if len(corpus_files) != 3:
        raise RuntimeError(
            f"legacy corpus file count changed: expected 3, got {len(corpus_files)}"
        )

    total = 0
    failures: list[str] = []
    started = time.perf_counter()
    for index, path in enumerate(corpus_files, 1):
        figures = _load_corpus_figures(path, index)
        for name, svg in figures.items():
            total += 1
            assessment = assess_svg(svg, run_pixel_lint=False)
            if not assessment.accepted:
                details = assessment.security_issues + assessment.issues
                failures.append(f"{path.parent.name}/{name}: {'; '.join(details)}")
                continue
            if not quick:
                issues = lint_svg(svg, scale=2)
                if issues:
                    failures.append(
                        f"{path.parent.name}/{name}: {'; '.join(issues)}"
                    )

    if total != EXPECTED_CORPUS_FIGURES:
        failures.append(
            f"corpus figure count changed: expected {EXPECTED_CORPUS_FIGURES}, got {total}"
        )
    if failures:
        print("[FAIL] legacy corpus")
        for failure in failures:
            print(f"  - {failure}")
        raise SystemExit(1)

    mode = "structure" if quick else "structure + pixel lint(scale=2)"
    elapsed = time.perf_counter() - started
    print(f"[PASS] legacy corpus: {total}/{total} ({mode}, {elapsed:.1f}s)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quick",
        action="store_true",
        help="skip the slow per-figure pixel lint; PR/pre-commit must use full mode",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="skip pytest when it has already run in the same verification session",
    )
    args = parser.parse_args()

    _compile_modules()
    if not args.skip_tests:
        _run_tests()
    _verify_corpus(quick=args.quick)
    print("[PASS] Figure Engine v2 verification complete")


if __name__ == "__main__":
    main()
