import ast, sys, re
sys.path.insert(0, '.')

success = True

print("=== 1. HWPX Structure Verification ===")
def extract_ns(filepath):
    try:
        with open(filepath, encoding='utf-8') as f:
            for line in f:
                if line.strip().startswith('NS = {'):
                    lines = [line]
                    while '}' not in lines[-1]:
                        lines.append(next(f))
                    return eval(''.join(lines).split('=', 1)[1].strip())
    except FileNotFoundError:
        return None
    return None

ns_writer = extract_ns('core/hwpx_writer.py')
ns_loader = extract_ns('core/template_loader.py')

if ns_writer and ns_writer == ns_loader:
    print('PASS: NS dictionaries are identical')
else:
    print('FAIL: NS dictionaries differ or not found')
    success = False

print("\n=== 2. LaTeX to HWP EQ Regex Verification ===")
try:
    from core.latex_to_hwpeq import LaTeXToHWPConverter
    c = LaTeXToHWPConverter()
    patterns = ['_frac_pattern', '_sqrt_n_pattern', '_sqrt_pattern', '_big_op_pattern',
                '_accent_pattern', '_leftright_pattern', '_superscript', '_subscript',
                '_text_pattern', '_mathrm_pattern', '_mathbf_pattern', '_binom_pattern', '_env_pattern']
    for p in patterns:
        pat = getattr(c, p)
        assert isinstance(pat, re.Pattern), f'{p} is not compiled regex'
    print(f'PASS: All {len(patterns)} regex patterns compiled successfully')
except Exception as e:
    print(f'FAIL: Regex compilation failed - {e}')
    success = False

print("\n=== 3. OCR Parser Sync Verification ===")
try:
    from core.content_parser import _INLINE_LATEX_RE, _MATH_EXPR_RE
    assert isinstance(_INLINE_LATEX_RE, re.Pattern), 'Not a compiled pattern'
    test1 = 'hello $x^2$ world'
    matches = _INLINE_LATEX_RE.findall(test1)
    if matches:
        print(f'PASS: _INLINE_LATEX_RE compiled, test matches: {matches}')
    else:
        print('FAIL: _INLINE_LATEX_RE match failed')
        success = False
        
    assert isinstance(_MATH_EXPR_RE, re.Pattern), 'Not a compiled pattern'
    test2 = 'a > 0'
    match = _MATH_EXPR_RE.search(test2)
    if match:
        print(f'PASS: _MATH_EXPR_RE compiled, test match: {match.group()}')
    else:
        print('FAIL: _MATH_EXPR_RE match failed')
        success = False
except Exception as e:
    print(f'FAIL: Parser sync verification failed - {e}')
    success = False

print("\n=== 4. Equation Size Estimator Regression ===")
try:
    import json
    from pathlib import Path
    from core.hwpx_writer import _estimate_equation_size

    golden_path = Path('scripts/tune_equation/golden_equations.json')
    if not golden_path.exists():
        print('SKIP: golden_equations.json 없음 — extract_golden.py 재실행 필요')
    else:
        samples = json.loads(golden_path.read_text(encoding='utf-8'))
        errs_rel = []
        height_ok = 0
        zero_width = 0
        for s in samples:
            est_w, est_h = _estimate_equation_size(s['script'])
            if est_w <= 0:
                zero_width += 1
            errs_rel.append(abs(est_w - s['width']) / max(s['width'], 1))
            if est_h == s['height']:
                height_ok += 1

        mape = sum(errs_rel) / len(errs_rel)
        sorted_err = sorted(errs_rel)
        median = sorted_err[len(sorted_err) // 2]
        p95 = sorted_err[int(len(sorted_err) * 0.95)]
        height_pct = height_ok / len(samples)

        checks = [
            (zero_width == 0, f'zero-width={zero_width}'),
            (mape <= 0.08, f'MAPE={mape*100:.2f}% (≤8%)'),
            (median <= 0.06, f'median={median*100:.2f}% (≤6%)'),
            (p95 <= 0.20, f'p95={p95*100:.2f}% (≤20%)'),
            (height_pct >= 0.95, f'height={height_pct*100:.0f}% (≥95%)'),
        ]
        failed = [msg for ok, msg in checks if not ok]
        if failed:
            print(f'FAIL: {"; ".join(failed)}')
            success = False
        else:
            print(
                f'PASS: MAPE={mape*100:.2f}%, median={median*100:.2f}%, '
                f'p95={p95*100:.2f}%, height={height_pct*100:.0f}%, zero={zero_width}'
            )
except Exception as e:
    print(f'FAIL: 수식 추정기 검증 실패 - {e}')
    success = False

print("\n=== 5. Import/Syntax Check for Main Modules ===")
try:
    import core.hwpx_writer
    import core.latex_to_hwpeq
    import core.ocr_engine
    import core.content_parser
    import core.quality_checker
    import core.pdf_handler
    import models.exam_document
    print("PASS: All core modules can be imported without syntax errors")
except ImportError as e:
    print(f"FAIL: Core module import failed - {e}")
    success = False
except SyntaxError as e:
    print(f"FAIL: Syntax error in core modules - {e}")
    success = False
except Exception as e:
    print(f"FAIL: Error during module import - {e}")
    success = False

if success:
    print("\nOVERALL STATUS: PASS")
    sys.exit(0)
else:
    print("\nOVERALL STATUS: FAIL")
    sys.exit(1)
