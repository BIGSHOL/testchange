# -*- coding: utf-8 -*-
"""수식 소유권 표식(워터마크) 회귀 — stdlib·COM 없음·API 0원.

HWP 렌더 실측(2026-08-10, 41케이스)으로 확정한 규칙을 박제한다:
  · 일반 수식·분수·근호·cases·이미 from/to 를 쓰는 합 → 표식이 **안 보인다**(붙인다)
  · **큰 연산자로 끝나는 식**(``A = sum``·``int``·``lim``·``prod``) → 표식이 그 연산자의
    하한/상한으로 **인쇄된다** → 반드시 생략한다(스마트 게이트, 사용자 2026-08-10)

실행: python tests/test_eq_watermark.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.eq_watermark import is_stampable, stamp, strip_mark  # noqa: E402

FAILED: list[str] = []
MARK = "(C) 2026 매쓰원"


def check(label: str, cond: bool, detail: str = "") -> None:
    print(("  OK   " if cond else "  FAIL ") + label + ("" if cond else f" — {detail}"))
    if not cond:
        FAILED.append(label)


print("A. 붙여도 안 보이는 형태(실측 확인) — 표식 부착")
SAFE = [
    "y = -6x",
    "{x+1} over {2} = 3",
    "sqrt {2} + sqrt {3}",
    "CASES {x+y=3 # 2x-y=1}",
    "x ^ {2} + y _{1}",                       # 일반 첨자는 상·하한 연산자가 아니라 안전
    "bar {rm {AB}} = 5",
    "x ^",                                    # 미완성 첨자 — 실측상 안 보임
    "1 over",
    "{x+1",
]
for s in SAFE:
    out = stamp(s, MARK)
    check(f"부착: {s[:28]!r}", out != s and out.endswith("}") and "from {" in out, out[-40:])

print("\nB. ⚠️ 결합해 인쇄되는 형태 — 표식 생략(스마트 게이트)")
UNSAFE = [
    "A = sum",        # Σ 아래에 문구가 찍힌다(실측)
    "A = int",
    "A = lim",
    "A = prod",
    "A = SUM",        # 대소문자 무관
    "x = max",
    "y = int   ",     # 뒤 공백 있어도 마지막 토큰은 int
    "a = b from",     # from/to 로 끝나면 인자 자리를 먹는다
    "a = b to",
    # ⚠️ 상·하한 연산자가 **중간에** 있어도 생략(사용자 2026-08-10 보수 규칙)
    "sum _{i=1} ^{n} i",
    "sum from {i=1} to {n} i = 10",
    "int f(x) dx",
    "lim _{x -> 0} f(x) = 3",
    "A = lim _{n -> inf} a_n",
]
for s in UNSAFE:
    check(f"생략: {s!r}", stamp(s, MARK) == s and not is_stampable(s))

print("\nC. 기능 OFF·멱등·역변환")
check("빈 표식이면 원본", stamp("y=1", "") == "y=1")
check("None 표식이면 원본", stamp("y=1", None) == "y=1")
check("공백 표식이면 원본", stamp("y=1", "   ") == "y=1")
once = stamp("y=1", MARK)
check("멱등(두 번 붙지 않음)", stamp(once, MARK) == once, once)
check("strip 로 원본 복원", strip_mark(once) == "y=1", strip_mark(once))
check("표식 없는 식은 strip 무해", strip_mark("y=1") == "y=1")
check("빈 스크립트 방어", stamp("", MARK) == "" and not is_stampable(""))

print("\nD. 스크립트를 깨뜨리지 않는 문구 정규화")
brace = stamp("y=1", "매쓰원 {학원} $x$")
check("중괄호·$ 제거", "{학원}" not in brace and "$" not in brace, brace)
check("중괄호 균형", brace.count("{") == brace.count("}"), brace)
nl = stamp("y=1", "매쓰원\n2026")
check("개행 제거", "\n" in nl and nl.count("\n") == 1, repr(nl))

print("\n" + ("전부 통과" if not FAILED else f"{len(FAILED)}건 FAIL"))
sys.exit(1 if FAILED else 0)
