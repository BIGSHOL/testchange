# -*- coding: utf-8 -*-
"""수식 안 **보이지 않는 소유권 표식**(워터마크) — 도용 억제용.

원리(실측 2026-08-10, HWP 렌더 41케이스)
    HWP 수식 스크립트 끝에 개행 + ``from {문구}`` 를 붙이면 **렌더에 전혀 안 보인다**.
    ``from``/``to`` 는 바로 앞 *큰 연산자*(sum·int·prod·lim)의 하한/상한으로만 쓰이는데,
    앞에 결합할 연산자가 없으면 HWP 가 조용히 버리기 때문이다. 단순식·분수·근호·행렬
    (cases)·이미 ``from``/``to`` 를 쓰는 합까지 26종 전부 기준선과 픽셀 동일이었고,
    ``.hwpx → .hwp → .hwpx`` 왕복에서도 script 에 그대로 남았다(=식별 가능).

⚠️ **스마트 게이트가 필수다**(사용자 2026-08-10 "혹시 모르니까"): 스크립트가 **큰
    연산자로 끝나면** 붙인 문구가 그 연산자의 하한/상한이 되어 **그대로 인쇄된다**
    (실측: ``A = sum`` + from → Σ 아래 문구 노출. int·lim·prod 동일, ``to`` 는 위쪽).
    그런 수식은 표식을 **생략**한다 — 표식보다 출력물 정확성이 우선이다.

    게이트는 "끝에 있을 때"가 아니라 **상·하한을 받는 연산자가 스크립트 안에 하나라도
    있으면 생략**한다(사용자 2026-08-10 "위첨자 아래첨자가 없는 것들만"). 실측상
    ``sum _{i=1} ^{n} i`` 처럼 피연산자로 끝나면 안전했지만, 그 판정은 스크립트 형태에
    의존하므로 여유를 크게 둔다. 일반 첨자(``x^2``·``a_1``)는 상·하한을 받는 연산자가
    아니어서 안전하다(실측) — 그것까지 빼면 대상이 절반 이하로 줄어 표식 의미가 옅어진다.

⚠️ 이건 **억제책이지 보호가 아니다**: 수식 편집기를 열면 보이고 지울 수 있다.
    출처를 남겨 무단 사용을 확인·주장하기 위한 표식으로만 쓴다.
"""
from __future__ import annotations

import re

# from/to 를 하한·상한으로 받는 연산자 — 이걸로 끝나면 표식이 결합해 **보인다**.
_LIMIT_OPS = frozenset("""
sum int iint iiint oint prod coprod lim liminf limsup
union inter cup cap max min sup inf gcd det
""".split())

# 표식 자체 — 문서에서 이 접두로 찾아낼 수 있게 고정 형태를 쓴다.
_MARK_RE = re.compile(r"\n?from\s*\{[^{}]*\}\s*$")
_LAST_TOKEN_RE = re.compile(r"([A-Za-z]+)\s*$")


def is_stampable(script: str) -> bool:
    """이 수식에 표식을 붙여도 **안 보이는가**(=붙여도 되는가)."""
    s = (script or "").strip()
    if not s:
        return False
    if _MARK_RE.search(s):        # 이미 붙어 있음(멱등)
        return False
    # ⚠️ 상·하한을 받는 연산자가 **어디에든** 있으면 생략(보수적).
    for tok in re.findall(r"[A-Za-z]+", s):
        if tok.lower() in _LIMIT_OPS:
            return False
    m = _LAST_TOKEN_RE.search(s)
    if m and m.group(1).lower() in _LIMIT_OPS:
        return False              # ⚠️ 결합해서 인쇄된다 — 생략
    # 끝이 from/to 면 그 자리의 인자로 먹힌다.
    if re.search(r"\b(from|to)\s*$", s, re.I):
        return False
    return True


def stamp(script: str, mark: str) -> str:
    """표식을 붙인 스크립트(붙일 수 없으면 원본 그대로).

    ``mark`` 가 비면 기능 자체가 꺼진 것으로 보고 원본을 돌려준다.
    """
    if not mark or not str(mark).strip():
        return script
    if not is_stampable(script):
        return script
    safe = re.sub(r"[{}$\n]", " ", str(mark)).strip()   # 중괄호·개행은 스크립트를 깬다
    if not safe:
        return script
    return f"{script}\nfrom {{{safe}}}"


def strip_mark(script: str) -> str:
    """표식을 떼어낸 스크립트 — 폭 추정·비교·회귀에서 원본과 대조할 때 쓴다."""
    return _MARK_RE.sub("", script or "").rstrip()
