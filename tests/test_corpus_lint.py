"""corpus_lint XML 게이트 회귀 — 적대적 리뷰 A-4(2026-06-13).

메타토큰·라벨 검사가 raw 연속 문자열 기반이라 COM run 분할 시 우회되던 것(효성중 B-1)과,
정답 페이지 증발을 꼬리말 "(정답)" 때문에 못 잡던 무력 게이트를 회귀로 박제한다. stdlib 만
쓰므로 키 0·HWP 0 으로 실행된다.
"""
import importlib.util
import os
import sys
import tempfile
import zipfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
_spec = importlib.util.spec_from_file_location(
    "corpus_lint", os.path.join(_ROOT, "scripts", "corpus_lint.py"))
cl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cl)


def _hwpx(section_xml: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".hwpx")
    os.close(fd)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("Contents/section0.xml", section_xml)
    return path


def run() -> int:
    fails = []

    # A-4①: 메타토큰이 run 분할돼도 검출(태그 제거 후 연속 문자열 판정).
    split_tok = ('<hp:p><hp:run><hp:t>소단원자리표식Q</hp:t><hp:t>ZX</hp:t></hp:run></hp:p>'
                 '<hp:p><hp:t>정답</hp:t></hp:p>')
    p = _hwpx(split_tok)
    if not any("메타란 토큰" in m for _, m in cl.lint_xml(p)):
        fails.append("  A4 run 분할 메타토큰 미검출(게이트 우회)")
    os.remove(p)

    # A-4①: 라벨도 run 분할 후 철자 혼용 검출.
    split_lbl = ('<hp:p><hp:t>[서답형 1]</hp:t></hp:p>'
                 '<hp:p><hp:run><hp:t>[서</hp:t><hp:t>술형 2]</hp:t></hp:run></hp:p>'
                 '<hp:p><hp:t>정답</hp:t></hp:p>')
    p = _hwpx(split_lbl)
    if not any("철자 혼용" in m for _, m in cl.lint_xml(p)):
        fails.append("  A4 run 분할 라벨 혼용 미검출")
    os.remove(p)

    # A-4②: 정답 페이지 증발(꼬리말 "(정답)" 만 남음) 검출.
    footer_only = ('<hp:p><hp:t>1번 문제</hp:t></hp:p>'
                   '<hp:footer><hp:t>(정답)</hp:t></hp:footer>')
    p = _hwpx(footer_only)
    if not any("정답' 블록 없음" in m for _, m in cl.lint_xml(p)):
        fails.append("  A4 정답 증발(꼬리말만) 미검출")
    os.remove(p)

    # 무회귀: 정답 container 본문 '정답' 이 있으면 꼬리말이 있어도 오탐 없음.
    ok = ('<hp:p><hp:t>1번</hp:t></hp:p>'
          '<hp:container><hp:t>정답</hp:t></hp:container>'
          '<hp:footer><hp:t>(정답)</hp:t></hp:footer>')
    p = _hwpx(ok)
    if any("정답' 블록 없음" in m for _, m in cl.lint_xml(p)):
        fails.append("  A4 정상 정답 페이지 오탐")
    os.remove(p)

    # 무회귀: 메타토큰 없는 깨끗한 렌더는 토큰/라벨 FAIL 없음.
    clean = '<hp:p><hp:t>[서술형 1] 풀이</hp:t></hp:p><hp:container><hp:t>정답</hp:t></hp:container>'
    p = _hwpx(clean)
    iss = cl.lint_xml(p)
    if any("메타란 토큰" in m or "철자 혼용" in m or "정답' 블록 없음" in m for _, m in iss):
        fails.append(f"  A4 깨끗한 렌더 오탐: {iss!r}")
    os.remove(p)

    if fails:
        print("FAIL test_corpus_lint:")
        print("\n".join(fails))
        return 1
    print("OK test_corpus_lint (A-4 게이트 6 cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
