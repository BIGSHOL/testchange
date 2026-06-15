"""LaTeX 수식을 HWP 수식 스크립트로 변환하는 모듈.

한글(HWP)의 수식 편집기는 자체 수식 스크립트 문법을 사용합니다.
이 모듈은 LaTeX 수식을 HWP 수식 스크립트로 변환합니다.

주요 매핑:
  \\frac{a}{b}     → {a} over {b}
  x^{2}            → x ^{2}
  x_{n}            → x _{n}
  \\sqrt{x}         → sqrt {x}
  \\sqrt[n]{x}      → root {n} of {x}
  \\sum_{i=0}^{n}   → SUM _{i=0} ^{n}
  \\int_{a}^{b}     → INT _{a} ^{b}
  \\lim_{x \\to 0}   → lim _{x -> 0}
"""

from __future__ import annotations

import re

# 리터럴 중괄호 \{ \} 보호용 sentinel.
# HWP 수식에선 보이는 중괄호를 \{ \} 로 표기하지만(그룹핑 {}와 구분),
# 변환 도중 그룹핑 처리(\{...\} 재귀)나 명령어 정리에 망가지기 쉽다.
# 그래서 변환 시작 시 sentinel로 치환해 보호하고, 마지막에 \{ \} 로 복원한다.
_SENT_LB = "\x01"  # \{
_SENT_RB = "\x02"  # \}

# 순환소수: 소수점 뒤 \dot{d} 점 표기를 HWP ``dot {d}`` over-dot 으로 변환(양끝 숫자 위 점).
# 예: 0.1\dot{5}\dot{7} → 0.1 dot {5} dot {7}. HWP 가 ``dot {d}`` 를 정상 렌더한다(실측
# .testkit/dot_test.py, 2026-06-11). 과거 bar(overline) 로 통일했던 건 ``dot{3}`` 무공백
# 문법 오진. _normalize_repeating_decimal 참조.
# 첨자(^,_) 내용이 단순 영숫자 런이면 중괄호 없이(밀착 렌더), 아니면 그룹핑.
_SIMPLE_SCRIPT_RE = re.compile(r"^[A-Za-z0-9]+$")


def _wrap_script(content: str) -> str:
    """위/아래첨자 본문을 HWP 표기로.

    **한 글자**(예: 2, n)만 무중괄호로 밀착 렌더하고, **두 글자 이상**은 반드시
    중괄호로 묶는다. 무중괄호 다글자 첨자(예: ``x^2y``)는 HWP가 구분자 없는 ``^``를
    뒤따르는 연산자·괄호까지 탐욕적으로 삼켜(over-capture) 수식이 깨진다
    (예: ``10x^2y-6xy^2)÷2y`` → x 지수가 ``2y-6xy^2)÷`` 전체를 먹음). 실측 확정 2026-06-02.
    """
    content = content.strip()
    # 항상 중괄호로 묶는다. 무중괄호 ``^`` 는 구분자(공백) 없이는 뒤따르는 연산자·
    # 괄호까지 탐욕적으로 삼킨다 — 한 글자 지수도 ``6xy^2)÷`` 처럼 뒤에 ``)÷`` 가
    # 붙으면 ``2)÷`` 를 전부 지수로 먹어 깨진다(실측 확정 2026-06-02). 중괄호가 유일한
    # 안전한 경계다(사용자 정답도 ``x^{2y}``·``6xy^{2}`` 모두 중괄호 사용).
    return "{" + content + "}"


# 유니코드 위첨자 문자(²³¹⁰⁴…)를 LaTeX 지수 ``^{…}`` 로 정규화한다(사용자 2026-06-09:
# "지수는 항상 2^2 처럼 수식처리, 윗첨자 문자가 아님"). OCR 이 ``N(m, 2²)`` 처럼 유니코드
# 위첨자를 그대로 주면 HWP 가 작은 ² 글자로 렌더 → 지수 객체가 아님. 연속 위첨자(²³)는
# 한 지수 ``^{23}`` 로 묶는다.
_SUPERSCRIPT_MAP = {
    "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5",
    "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
    "⁺": "+", "⁻": "-", "⁼": "=", "⁽": "(", "⁾": ")", "ⁿ": "n", "ⁱ": "i",
}
_SUPERSCRIPT_RE = re.compile("[" + "".join(_SUPERSCRIPT_MAP) + "]+")


def _normalize_unicode_superscripts(s: str) -> str:
    """``2²``·``x³`` 등 유니코드 위첨자를 ``2^{2}``·``x^{3}`` LaTeX 지수로 변환."""
    if not _SUPERSCRIPT_RE.search(s):
        return s
    return _SUPERSCRIPT_RE.sub(
        lambda m: "^{" + "".join(_SUPERSCRIPT_MAP[c] for c in m.group(0)) + "}", s)


# \textcircled{...} → 유니코드 동그라미 문자 (숫자 ①~⑳, 자음 ㉠~, 음절 ㉮~)
_CIRCLED_RE = re.compile(r"\\textcircled\s*\{\s*([^}]+?)\s*\}")
_CIRCLED_HANGUL_CONS = "ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ"
_CIRCLED_HANGUL_SYL = "가나다라마바사아자차카타파하"


def _normalize_circled(s: str) -> str:
    def _repl(m: "re.Match") -> str:
        v = m.group(1).strip()
        if v.isdigit():
            n = int(v)
            if 1 <= n <= 20:
                return chr(0x2460 + n - 1)          # ①~⑳
        if len(v) == 1:
            if v in _CIRCLED_HANGUL_CONS:
                return chr(0x3260 + _CIRCLED_HANGUL_CONS.index(v))   # ㉠~
            if v in _CIRCLED_HANGUL_SYL:
                return chr(0x326E + _CIRCLED_HANGUL_SYL.index(v))    # ㉮~
        return v
    return _CIRCLED_RE.sub(_repl, s)


# 단위: 수식 내 "숫자+단위"의 단위를 로만체로(rm) + 1/4칸(`) 살짝 띄움.
# HWP 수식은 라틴 문자를 기본 이탤릭으로 렌더하므로 단위(kg, cm …)도 기울어진다.
# 사용자 요구: 0.5kg → "0.5 rm`kg" (단위는 정자, 숫자와 살짝 띄움). 실측 확정 2026-06-02.
# 긴 단위 먼저(min 이 m 보다, cm 이 m 보다 우선). 한글 단위(원 등)는 수식에서 깨질 수 있어 제외.
# **단일문자 m·t·s·h·L 은 제외**(사용자 2026-06-08): 확통의 모평균 m·시간/변수 t·s·h·L 을
# 단위(미터·초·리터)로 오인해 로만화하면 안 됨(예 "2m"=2×모평균, 이탤릭). 다문자 단위와
# g(그램; 숫자 뒤에서만 매칭이라 변수 충돌 적음)·기호만 자동 로만화한다.
_UNITS = [
    "kcal", "min", "km", "cm", "mm", "kg", "mg", "mL", "dL", "kL",
    "g", "°", "℃", "℉", "ℓ",
]
# 숫자와 단위 사이에 공백/`(=\,변환) 가 끼어도 단위로 인식한다(사용자 2026-06-08: "20 g"·
# "20\,g" 처럼 띄어진 단위가 로만 처리 안 됨). 단위 뒤에 영문/숫자 없을 때만(변수 5x 제외).
# L(리터)은 단독 변수와 충돌해 _UNITS 에서 뺐지만(2026-06-08), **숫자 직결 꼬리**(1L·25L)
# 에선 단위가 확실하므로 그 위치 한정으로 정자화(범물중 #22 "연료 1L", 2026-06-11).
_NUM_TAIL_UNITS = _UNITS + ["L"]
_UNIT_RE = re.compile(
    r"(\d)[\s`]*(" + "|".join(re.escape(u) for u in _NUM_TAIL_UNITS) + r")(?![A-Za-z0-9])"
)
# 분수/근호 닫는 ``}`` 뒤 단위(``\frac{8}{3}cm`` → ``{8} over {3}cm`` 의 ``}cm``, ``\sqrt{2}cm``)도
# 로만화 — 분수+cm 이 이탤릭으로 남던 것(강북중 중2 #6 ①③④, 2026-06-15). 단, **다문자 단위만**
# (cm·mm·kg·km…). 단일문자 L·g·° 는 첨자 뒤 변수일 수 있어(``a_{1}L`` 의 ``}L``) 제외(O2 회귀).
_MULTI_UNITS = [u for u in _NUM_TAIL_UNITS if len(u) >= 2]
_BRACE_UNIT_RE = re.compile(
    r"(\})[\s`]*(" + "|".join(re.escape(u) for u in _MULTI_UNITS) + r")(?![A-Za-z0-9])"
)
# 단일 변수 글자 뒤 무공백 단위("xkm"·"yL") — 다문자 단위+L 한정(g·° 등 단일기호 제외:
# 변수곱 "ag" 오인 방지). 앞이 다른 글자면(LCM 류 식별자) 제외. 완료본 인쇄는 변수 이탤릭
# + 단위 정자 + 얇은 간격(범물중 #22 "xkm인"·"yL라고" 통째 이탤릭이던 것, 2026-06-11).
_VAR_TAIL_UNITS = [u for u in _UNITS if len(u) >= 2 and u.isascii()] + ["L", "ℓ"]
_VAR_UNIT_RE = re.compile(
    r"(?<![A-Za-z])([A-Za-z])[\s`]*("
    + "|".join(re.escape(u) for u in _VAR_TAIL_UNITS) + r")(?![A-Za-z0-9])"
)

# 확통 연산자·확률변수 P/E/V/N/Z/X/Y 의 \mathrm(로만)을 벗겨 이탤릭으로(순열 \mathrm{P}_ 제외).
# 본문 수식뿐 아니라 **표 셀**(latex_to_hwpeq 직접 호출)에도 적용되도록 변환기에서 처리
# (사용자 2026-06-08: 정규분포표 셀 내부 P·Z 가 로만). 조합 C 는 집합에 없어 로만 유지.
_STAT_ITALIC_RE = re.compile(r"\\mathrm\{([XYPEVNZ])\}(?!\s*_)")


def _romanize_units(s: str) -> str:
    """수식 내 '숫자(+공백/`) 뒤 단위'를 ``rm`<단위>`` (정자 + 1/4칸)로 변환.

    예: ``10kg`` → ``10 rm`kg``, ``5cm`` → ``5 rm`cm``, ``20 g``/``20`g`` → ``20 rm`g``.
    숫자 뒤 + 뒤에 영문/숫자가 이어지지 않을 때만(변수 ``5x`` 등은 건드리지 않음).
    단일 변수 뒤 다문자 단위/L(``xkm``·``yL``)도 정자+간격(``x rm`km``, 범물중 #22).
    """
    s = _UNIT_RE.sub(lambda m: m.group(1) + " rm`" + m.group(2), s)
    s = _BRACE_UNIT_RE.sub(lambda m: m.group(1) + " rm`" + m.group(2), s)
    return _VAR_UNIT_RE.sub(lambda m: m.group(1) + " rm`" + m.group(2), s)


# 변환 후 ``<글자/숫자> rm <단위>`` 의 일반 공백을 백틱(1/4칸)으로 — ``a\mathrm{cm}`` →
# ``a rm cm``(렌더상 "a㎝" 붙음) → ``a rm`cm``(얇은 간격). bare ``5cm`` 은 _romanize_units 가
# 이미 ``5 rm`cm`` 로 처리하나, ``\mathrm{}`` 로 감싸진 단위(변수 a\mathrm{cm}·숫자 5\mathrm{cm})는
# _mathrm_pattern 경로로 빠져 백틱이 없었다(2026-06-11 렌더 실증). _UNITS 한정이라 오검출 없음.
_RM_UNIT_RE = re.compile(
    r"([A-Za-z0-9])\s+rm\s+("
    + "|".join(re.escape(u) for u in _NUM_TAIL_UNITS) + r")(?![A-Za-z0-9])"
)


def _backtick_rm_units(s: str) -> str:
    """``<글자/숫자> rm <단위>`` → ``<글자/숫자> rm`<단위>`` (단위 앞 백틱 얇은공백)."""
    return _RM_UNIT_RE.sub(lambda m: m.group(1) + " rm`" + m.group(2), s)


# 베이스 없는 선행 첨자(``_{n-1}C``)에 빈그룹 베이스 ``{}`` 삽입(혜화여고 #19). 단 대형
# 연산자 하한(``SUM _{k=1}``·``INT _{0}``·``UNION _{i}`` …)은 그 op 의 정상 첨자라 삽입하면
# 안 된다 — 공백 분기가 ``SUM _{`` 를 ``SUM {}_{`` 로 깨던 회귀(적대리뷰 A-1, 2026-06-13).
_LEAD_SUBSCRIPT_RE = re.compile(r"(^|[+\-=<>(\s])_\{")
# endswith 는 부분일치라 ``INT`` 가 ``DINT``/``TINT``/``OINT`` 를, ``PROD`` 가 ``COPROD`` 를
# 포괄한다(대형연산자 출력 키워드 전체).
_BIG_OP_KEYWORDS = ("SUM", "PROD", "INT", "UNION", "INTER")


def _lead_subscript_repl(m: "re.Match") -> str:
    sep = m.group(1)
    # 공백 분기일 때만 — 앞 토큰이 대형연산자 키워드면 그 op 의 하한이므로 빈그룹 삽입 금지.
    if sep and sep.isspace() and m.string[:m.start()].rstrip().endswith(_BIG_OP_KEYWORDS):
        return m.group(0)
    return sep + "{}_{"


# OCR 이 단위를 ``20\text{g}`` 처럼 \text 로 감싸 주면 변환기는 ``20"g"``(따옴표 리터럴)로
# 만든다 — 정자이긴 하나 단위 간격(``rm`g``)이 안 붙고 사용자에겐 여전히 어색(2026-06-09:
# "g(그램)이 rm 으로 로만처리 안 됨"). 그래서 변환 **전** ``\text{<단위>}`` 를 평문 단위로
# 풀어 ``20g`` 로 만들면 뒤의 ``_romanize_units`` 가 ``20 rm`g`` 로 정자+간격 처리한다.
_TEXT_UNIT_RE = re.compile(
    r"\\text\s*\{\s*(" + "|".join(re.escape(u) for u in _UNITS) + r")\s*\}")


def _unwrap_text_units(s: str) -> str:
    """``\\text{g}``·``\\text{kg}`` 등 **단위만** 감싼 \\text 를 평문 단위로 푼다."""
    return _TEXT_UNIT_RE.sub(lambda m: m.group(1), s)


_REPEAT_DECIMAL_RE = re.compile(r"\.((?:\\dot\s*\{\s*\d\s*\}|\d)+)")
_DOT_TOKEN_RE = re.compile(r"\\dot\s*\{\s*(\d)\s*\}|(\d)")


def _normalize_repeating_decimal(s: str) -> str:
    """소수점 뒤 \\dot{} 순환마디 표기를 HWP ``dot {d}`` 점 표기로 변환.

    한글 교과서 표준은 순환마디 양끝 숫자 위 **점**(0.15̇7̇). HWP 수식 ``dot {d}`` 가
    이 over-dot 를 정상 렌더한다(.testkit/dot_test.py 실측 — 과거 'dot 미렌더, bar 로
    통일' 판단은 잘못된 문법(``dot{3}`` 무공백)으로 테스트한 오진이었다, 2026-06-11).
    OCR 이 점 찍을 숫자에만 ``\\dot{}`` 를 주므로 그 위치를 그대로 보존한다.
    예: 0.1\\dot{5}\\dot{7} → 0.1 dot {5} dot {7}, 0.\\dot{3}7\\dot{5} → 0. dot {3}7 dot {5}.
    """
    def _repl(m: "re.Match") -> str:
        run = m.group(1)
        if r"\dot" not in run:
            return m.group(0)
        seq = [(d or p, bool(d)) for d, p in _DOT_TOKEN_RE.findall(run)]
        out = "."
        for c, is_dot in seq:
            out += (" dot {" + c + "}") if is_dot else c
        return out
    return _REPEAT_DECIMAL_RE.sub(_repl, s)


# 괄호 자동크기 대상: 분수·근호·이항계수·대형연산자 등 '키 큰' 구조.
# 평문 ``(...)`` 안에 이게 있으면 괄호가 내용보다 작아 보기 나쁨(사용자 2026-06-05) →
# ``\left(...\right)`` 로 바꿔 기존 LEFT/RIGHT 자동크기 경로를 태운다.
_TALL_DELIM_RE = re.compile(
    r"\\(?:d|t)?frac|\\cfrac|\\sqrt|\\binom|\\sum|\\prod|\\int|\\iint|\\iiint|\\oint"
    r"|\\bigcup|\\bigcap|\\bigoplus|\\bigotimes")


def _autosize_parens(s: str) -> str:
    """평문 ``(...)`` 중 분수·근호 등 키 큰 내용을 담은 쌍을 ``\\left(...\\right)`` 로.

    균형 잡힌 괄호를 스택으로 매칭하고, 내용에 `_TALL_DELIM_RE` 가 있으면 그 쌍만 감싼다.
    이미 ``\\left(``/``\\right)`` 인 괄호는 건드리지 않는다. 삽입은 인덱스 큰 쪽부터 적용해
    중첩/오프셋 안전. (``[ ]``·``\\{ \\}`` 는 사용자 요구가 괄호라 현재 미대상.)
    """
    if "(" not in s:
        return s
    stack: list[tuple[int, bool]] = []
    inserts: list[tuple[int, str]] = []
    for i, c in enumerate(s):
        if c == "(":
            is_left = s[max(0, i - 5):i].endswith("\\left")
            stack.append((i, is_left))
        elif c == ")" and stack:
            oidx, is_left = stack.pop()
            is_right = s[max(0, i - 6):i].endswith("\\right")
            if not is_left and not is_right and _TALL_DELIM_RE.search(s[oidx + 1:i]):
                inserts.append((oidx, r"\left"))
                inserts.append((i, r"\right"))
    for idx, text in sorted(inserts, key=lambda x: -x[0]):
        s = s[:idx] + text + s[idx:]
    return s


class LaTeXToHWPConverter:
    """LaTeX → HWP 수식 스크립트 변환기."""

    # 그리스 문자 매핑
    GREEK_MAP = {
        r"\alpha": "alpha",
        r"\beta": "beta",
        r"\gamma": "gamma",
        r"\delta": "delta",
        r"\epsilon": "epsilon",
        r"\varepsilon": "varepsilon",
        r"\zeta": "zeta",
        r"\eta": "eta",
        r"\theta": "theta",
        r"\vartheta": "vartheta",
        r"\iota": "iota",
        r"\kappa": "kappa",
        r"\lambda": "lambda",
        r"\mu": "mu",
        r"\nu": "nu",
        r"\xi": "xi",
        r"\pi": "pi",
        r"\rho": "rho",
        r"\sigma": "sigma",
        r"\tau": "tau",
        r"\upsilon": "upsilon",
        r"\phi": "phi",
        r"\varphi": "varphi",
        r"\chi": "chi",
        r"\psi": "psi",
        r"\omega": "omega",
        # 대문자 (PascalCase — HWP 규칙: 첫 글자만 대문자)
        r"\Gamma": "Gamma",
        r"\Delta": "Delta",
        r"\Theta": "Theta",
        r"\Lambda": "Lambda",
        r"\Xi": "Xi",
        r"\Pi": "Pi",
        r"\Sigma": "Sigma",
        r"\Upsilon": "Upsilon",
        r"\Phi": "Phi",
        r"\Chi": "Chi",
        r"\Psi": "Psi",
        r"\Omega": "Omega",
    }

    # 연산자/기호 매핑
    SYMBOL_MAP = {
        # 이스케이프 리터럴
        r"\%": "%",            # 백분율: 99\% → 99% (미매핑이면 백슬래시 잔존)
        # 산술 연산
        r"\times": "TIMES",
        r"\cdot": "CDOT",
        r"\div": "DIV",
        r"\pm": "PLUSMINUS",
        r"\mp": "MINUSPLUS",
        # 관계 연산
        r"\leq": "LEQ",
        r"\le": "LEQ",
        r"\geq": "GEQ",
        r"\ge": "GEQ",
        r"\neq": "neq",
        r"\ne": "neq",
        r"\approx": "APPROX",
        r"\equiv": "EQUIV",
        r"\sim": "SIM",
        r"\simeq": "SIMEQ",
        r"\cong": "CONG",
        r"\propto": "PROPTO",
        r"\asymp": "ASYMP",
        r"\doteq": "DOTEQ",
        r"\prec": "PREC",
        r"\succ": "SUCC",
        r"\ll": "<<",
        r"\gg": ">>",
        # 특수 기호
        r"\infty": "inf",
        r"\partial": "partial",
        r"\nabla": "LAPLACE",
        r"\forall": "forall",
        r"\exists": "EXIST",
        r"\in": "in",
        r"\notin": "notin",
        r"\ni": "OWNS",
        r"\subset": "subset",
        r"\supset": "supset",
        r"\subseteq": "subseteq",
        r"\supseteq": "supseteq",
        r"\cup": "SMALLUNION",
        r"\cap": "SMALLINTER",
        r"\emptyset": "emptyset",
        r"\vee": "VEE",
        r"\lor": "VEE",
        r"\wedge": "WEDGE",
        r"\land": "WEDGE",
        r"\neg": "LNOT",
        r"\lnot": "LNOT",
        r"\oplus": "OPLUS",
        r"\otimes": "OTIMES",
        r"\therefore": "therefore",
        r"\because": "because",
        r"\angle": "angle",
        r"\perp": "BOT",
        # 평행기호: HWP ``parallel`` 키워드는 **세로 두 줄**(││)로 렌더돼 평행처럼 안 보인다
        # (사용자 2026-06-15). ⫽(U+2AFD, 빗금 두 줄) 리터럴로 고정 — □(\square) 방식. norm
        # ‖(\Vert·\|)는 세로가 맞으므로 그대로 둔다.
        r"\parallel": '"⫽"',
        r"\mid": "|",          # 집합 표기 바: {x | x≤3}. 없으면 누락돼 "xx"로 붙음
        r"\vert": "|",
        r"\Vert": "PARALLEL",
        # 차집합 — 백슬래시("\\") 매핑은 step 13 의 ``\␣``→백틱 치환·잔여명령 제거에 먹혀
        # 연산자가 통째 증발했다(감사 2026-06-10). □(\square)와 같은 따옴표 리터럴로.
        r"\setminus": '"∖"',
        r"\triangle": "TRIANGLE",
        r"\square": '"□"',
        r"\circ": "CIRC",
        r"\bullet": "BULLET",
        # ★ 마커(귀납법 증명 ``(★)`` 등) — 키워드 미지원이라 □(\square)처럼 따옴표 리터럴.
        # 없으면 ``\bigstar`` 가 통째 증발해 ``(★)`` 가 ``()`` 로 샌다(상인고 수1 #12).
        r"\bigstar": '"★"',
        r"\star": "STAR",
        r"\diamond": "DIAMOND",
        r"\top": "TOP",
        r"\vdash": "VDASH",
        r"\models": "MODELS",
        # 화살표 — 단일선
        r"\rightarrow": "->",
        r"\leftarrow": "<-",
        r"\leftrightarrow": "<->",
        r"\to": "->",
        r"\gets": "<-",
        r"\uparrow": "uparrow",
        r"\downarrow": "downarrow",
        r"\updownarrow": "udarrow",
        r"\nearrow": "nearrow",
        r"\nwarrow": "nwarrow",
        r"\searrow": "searrow",
        r"\swarrow": "swarrow",
        r"\hookleftarrow": "hookleft",
        r"\hookrightarrow": "hookright",
        r"\mapsto": "mapsto",
        # 화살표 — 이중선
        r"\Rightarrow": "RARROW",
        r"\Leftarrow": "LARROW",
        r"\Leftrightarrow": "LRARROW",
        r"\Uparrow": "UPARROW",
        r"\Downarrow": "DOWNARROW",
        r"\Updownarrow": "UDARROW",
        # 점
        r"\ldots": "LDOTS",
        r"\cdots": "CDOTS",
        r"\vdots": "VDOTS",
        r"\ddots": "DDOTS",
        # 기타 기호
        r"\prime": "prime",
        r"\aleph": "ALEPH",
        r"\hbar": "HBAR",
        r"\imath": "IMATH",
        r"\jmath": "JMATH",
        r"\ell": "ELL",
        r"\wp": "WP",
        r"\Im": "IMAG",
        r"\Re": "REIMAGE",
        r"\dagger": "DAGGER",
        r"\ddagger": "DDAGGER",
    }

    # 함수 매핑
    FUNC_MAP = {
        r"\sin": "sin",
        r"\cos": "cos",
        r"\tan": "tan",
        r"\sec": "sec",
        r"\csc": "csc",
        r"\cot": "cot",
        r"\cosec": "cosec",
        r"\arcsin": "arcsin",
        r"\arccos": "arccos",
        r"\arctan": "arctan",
        r"\sinh": "sinh",
        r"\cosh": "cosh",
        r"\tanh": "tanh",
        r"\coth": "coth",
        r"\log": "log",
        r"\ln": "ln",
        r"\lg": "lg",
        r"\exp": "exp",
        r"\Exp": "Exp",
        r"\det": "det",
        r"\max": "max",
        r"\min": "min",
        r"\sup": "sup",
        r"\inf": "inf",
        r"\lim": "lim",
        r"\Lim": "Lim",
        r"\gcd": "gcd",
        r"\arg": "arg",
        r"\dim": "dim",
        r"\ker": "ker",
        r"\hom": "hom",
        r"\mod": "mod",
        r"\lcm": "lcm",
    }

    # 장식(accent) 매핑
    ACCENT_MAP = {
        r"\vec": "VEC",
        r"\bar": "BAR",
        r"\hat": "HAT",
        r"\tilde": "TILDE",
        r"\dot": "DOT",
        r"\ddot": "DDOT",
        r"\acute": "acute",
        r"\grave": "grave",
        r"\check": "check",
        r"\breve": "arch",
        r"\overarc": "arch",   # 호(⌒) — \overarc{AB} 가 매핑 없어 장식이 증발하고 rm AB 만
        r"\overline": "bar",   # 남던 것(대구고 수1 #10 호 AB:BC:CA, 2026-06-12). HWP=arch.
        r"\underline": "underline",
        r"\overrightarrow": "VEC",
        r"\widehat": "HAT",
        r"\widetilde": "TILDE",
    }

    # 대문자 연속런(AB, ABC, ABCD …)을 정자(rm)로 감쌀 때 **제외**할 HWP 키워드.
    # HWP 수식은 라틴 문자를 기본으로 이탤릭 렌더하므로(실측 확정 2026-06-02:
    # `x+ay-1` 기본 = `it {x+ay-1}` 와 픽셀 동일), 변수는 손대지 않는다. 다만
    # 도형 라벨(선분 AB·삼각형 ABC·사각형 ABCD 등)도 이탤릭이 되어버리므로,
    # 연속 대문자 2자 이상을 `rm {…}` 로 정자화한다. 이때 SUM·LEFT·LEQ 같은
    # 전부-대문자 키워드는 라벨이 아니라 제어어이므로 감싸면 안 된다 → 이 집합으로 제외.
    _ROMAN_LABEL_RE = re.compile(r"(?<![A-Za-z])([A-Z]{2,})(?![A-Za-z])")
    # 맵에 없는 구조 키워드(대형연산자·괄호·행렬·이항계수)도 제외 대상.
    _ROMAN_SKIP_EXTRA = {
        "LEFT", "RIGHT", "SUM", "PROD", "COPROD", "INT", "DINT", "TINT",
        "OINT", "UNION", "INTER", "CASES", "MATRIX", "PMATRIX", "BMATRIX",
        "DMATRIX", "RM", "IT", "BOLD", "ROOT", "OF", "OVER", "ATOP", "SQRT",
        "BOX",   # \boxed → BOX{…} 테두리 박스 키워드(rm 으로 감싸면 "BOX" 글자로 깨짐)
    }

    def __init__(self):
        self._build_patterns()
        # 변환기 맵의 값 중 '전부 대문자 2자 이상'인 것을 라벨 정자화에서 제외.
        skip = set(self._ROMAN_SKIP_EXTRA)
        for mp in (self.SYMBOL_MAP, self.FUNC_MAP, self.ACCENT_MAP, self.GREEK_MAP):
            for v in mp.values():
                if re.fullmatch(r"[A-Z]{2,}", v):
                    skip.add(v)
        self._roman_skip = skip

    def _apply_roman_labels(self, script: str) -> str:
        """변환된 HWP 스크립트에서 도형 라벨(연속 대문자 2자+)을 `rm {…}` 로 정자화.

        HWP 기본이 이탤릭이라 변수(x, a, 단일 대문자)는 그대로 두고, 선분/삼각형/
        사각형 라벨(AB, ABC, ABCD)만 정자로 만든다. HWP 키워드(SUM, LEFT, LEQ …)와
        이미 `rm {` 로 감싼 구간은 건드리지 않는다.
        """
        def _repl(m: "re.Match") -> str:
            run = m.group(1)
            if run in self._roman_skip:
                return run
            start = m.start(1)
            prev = m.string[max(0, start - 4):start]
            # 이미 rm/it/bold 로 감싸진 라벨(예: \mathrm 출력)은 중복 적용 방지.
            if prev.endswith("rm {") or prev.endswith("rm ") \
                    or prev.endswith("it {") or prev.endswith("bold"):
                return run
            return "rm {" + run + "}"

        return self._ROMAN_LABEL_RE.sub(_repl, script)

    def _build_patterns(self):
        """정규식 패턴 사전 컴파일."""
        # \frac{a}{b}, \dfrac{a}{b}, \tfrac{a}{b}
        self._frac_pattern = re.compile(
            r"\\[dt]?frac\s*" + self._brace_group("num") + r"\s*" + self._brace_group("den")
        )
        # \sqrt[n]{x} 또는 \sqrt{x}
        self._sqrt_n_pattern = re.compile(
            r"\\sqrt\s*\[([^\]]+)\]\s*" + self._brace_group("body")
        )
        self._sqrt_pattern = re.compile(r"\\sqrt\s*" + self._brace_group("body"))

        # \sum, \prod, \int 등 대형 연산자
        self._big_op_pattern = re.compile(
            r"\\(sum|prod|coprod|int|iint|iiint|oint|bigcup|bigcap)"
            r"(?:\s*_\s*" + self._brace_group_or_char("lo") + r")?"
            r"(?:\s*\^\s*" + self._brace_group_or_char("hi") + r")?"
        )

        # accent: \vec{A}, \bar{x} 등
        accent_cmds = "|".join(
            re.escape(k[1:]) for k in self.ACCENT_MAP
        )
        self._accent_pattern = re.compile(
            r"\\(" + accent_cmds + r")\s*" + self._brace_group("body")
        )

        # \left( ... \right) — 구분자로 \{ \}(sentinel로 보호됨) \langle \rangle \| 도 허용
        _ldelim = r"(\\langle|\\rangle|\\\||[(\[{|." + _SENT_LB + _SENT_RB + r"])"
        _rdelim = r"(\\langle|\\rangle|\\\||[)\]}|." + _SENT_LB + _SENT_RB + r"])"
        # body 는 \left/\right 를 품지 않는 **최내곽**만 매칭 — 비탐욕 (.*?) 은 중첩
        # \left(\left(…\right)^2\right) 에서 첫 \left↔첫 \right 를 짝지어 쌍이 어긋난다
        # (감사 2026-06-10). 치환은 고정점까지 반복(안쪽→바깥쪽).
        self._leftright_pattern = re.compile(
            r"\\left\s*" + _ldelim + r"\s*((?:(?!\\left|\\right).)*?)\s*\\right\s*" + _rdelim,
            re.DOTALL,
        )

        # 상첨자/하첨자
        self._superscript = re.compile(r"\^\s*" + self._brace_group_or_char("sup"))
        self._subscript = re.compile(r"_\s*" + self._brace_group_or_char("sub"))

        # \text{...}
        self._text_pattern = re.compile(r"\\text\s*" + self._brace_group("txt"))
        # \mathrm{...}
        self._mathrm_pattern = re.compile(r"\\mathrm\s*" + self._brace_group("txt"))
        # \mathbf{...}
        self._mathbf_pattern = re.compile(r"\\mathbf\s*" + self._brace_group("txt"))
        # \mathit{...} → it {…} (이탤릭 명시). HWP rm 은 명시적 it 전까지 뒤 전체로 번지므로,
        # 점이름 ``\mathrm{P}`` 뒤 좌표를 이탤릭 유지하려면 ``\mathit{(a,b)}`` 로 끊어야 한다
        # (2026-06-11 렌더 실증: rm{P}(a,b) 는 a,b 까지 로만). 기존엔 \mathit 가 버려져 it 미출력.
        self._mathit_pattern = re.compile(r"\\mathit\s*" + self._brace_group("txt"))
        # \boxed{...}/\fbox{...} → HWP ``BOX{ ~ … ~ }`` 테두리 박스(빈칸채우기 (가)/(나) 등).
        self._boxed_pattern = re.compile(r"\\(?:boxed|fbox)\s*" + self._brace_group("boxed"))

        # \binom{n}{k}
        self._binom_pattern = re.compile(
            r"\\binom\s*" + self._brace_group("top") + r"\s*" + self._brace_group("bot")
        )

        # \begin{env}...\end{env} (행렬/조건식)
        self._env_pattern = re.compile(
            r"\\begin\{(cases|pmatrix|bmatrix|vmatrix|matrix)\}"
            r"\s*(.*?)\s*"
            r"\\end\{\1\}",
            re.DOTALL,
        )

    @staticmethod
    def _brace_group(name: str) -> str:
        """Named group for {content} - handles up to 3 levels of nesting."""
        # 각 단계가 한 단계 더 깊은 중괄호를 허용
        L0 = r"[^{}]*"
        L1 = r"(?:[^{}]|\{" + L0 + r"\})*"
        L2 = r"(?:[^{}]|\{" + L1 + r"\})*"
        L3 = r"(?:[^{}]|\{" + L2 + r"\})*"
        return r"\{(?P<" + name + r">" + L3 + r")\}"

    @staticmethod
    def _brace_group_or_char(name: str) -> str:
        """Named group for {content} or single char."""
        L0 = r"[^{}]*"
        L1 = r"(?:[^{}]|\{" + L0 + r"\})*"
        L2 = r"(?:[^{}]|\{" + L1 + r"\})*"
        L3 = r"(?:[^{}]|\{" + L2 + r"\})*"
        return (
            r"(?:\{(?P<" + name + r">" + L3 + r")\}"
            r"|(?P<" + name + r"_c>[^\s{}\\]))"
        )

    def _get_match(self, match: re.Match, name: str) -> str:
        """brace_group_or_char에서 값 추출."""
        val = match.group(name)
        if val is None:
            val = match.group(name + "_c")
        return val or ""

    def convert(self, latex: str, italicize_stat: bool = True) -> str:
        """LaTeX 수식을 HWP 수식 스크립트로 변환.

        Args:
            latex: LaTeX 수식 문자열
            italicize_stat: ``\\mathrm{P/E/V/N/Z/X/Y}`` 를 이탤릭으로 벗길지. 표 셀 등
                content_parser 를 안 거치는 경로는 True(기본). **본문**은 content_parser 가
                이미 확통 이탤릭을 처리했고, 남은 ``\\mathrm{P}`` 는 기하 점(점 P·꼭짓점 A)을
                위해 일부러 붙인 로만이므로 False 로 호출해 보존한다(사용자 2026-06-09:
                "점·선·면인데 이탤릭 처리됨").

        Returns:
            HWP 수식 스크립트 문자열

        Raises:
            ValueError: 변환 실패 시
        """
        # 전처리: 불필요한 공백, $기호 제거
        s = latex.strip().strip("$").strip()

        # 유니코드 위첨자(2²·x³)를 LaTeX 지수(^{})로 — 지수 객체화(사용자 2026-06-09).
        s = _normalize_unicode_superscripts(s)

        # 유니코드 부등호 ≤ ≥ ≠ → LaTeX \leq \geq \neq (LEQ/GEQ 키워드로 정상 변환+연산자
        # 간격). OCR 이 \leq 대신 유니코드로 주면(temp=0 재실행 #20 (가)) 리터럴 ≤ 로 새던 것.
        s = s.replace("≤", r" \leq ").replace("≥", r" \geq ").replace("≠", r" \neq ")

        # ``\not`` 부정 — SYMBOL_MAP 에 ``\not`` 단독이 없어, 뒤 ``\in``/``=`` 만 치환되고
        # ``\not`` 은 step 13 의 ``\\[a-zA-Z]+`` 에서 **조용히 삭제**돼 ∉→∈·≠→= 로 **의미가
        # 뒤집히던** 무증상 오답(적대리뷰 B-1). 부정형을 매핑된 명령으로 정규화(없으면 NOT
        # 리터럴로 보존 — 침묵 반전 금지).
        s = re.sub(r"\\not\s*\\in\b", r"\\notin", s)
        s = re.sub(r"\\not\s*=", r"\\neq", s)
        s = re.sub(r"\\not\s*\\equiv\b", r' NOT EQUIV ', s)
        s = re.sub(r"\\not\s*\\subset\b", r' NOT SUBSET ', s)
        s = re.sub(r"\\not\s*(\\[a-zA-Z]+|[<>])", r' NOT \1', s)

        # 단위 \text{g} → 평문 g (뒤 _romanize_units 가 rm`g 로 정자+간격, 2026-06-09).
        s = _unwrap_text_units(s)

        # 확통 연산자/확률변수(P·E·V·N·Z·X·Y)의 \mathrm 을 벗겨 이탤릭으로(표 셀 포함, 순열
        # 제외). 본문(italicize_stat=False)은 기하 \mathrm{P} 보존을 위해 건너뛴다.
        if italicize_stat:
            s = _STAT_ITALIC_RE.sub(r"\1", s)

        # 순환소수 정규화: 소수점 뒤 \dot{} 연쇄를 \overline{...}로 합침.
        # (HWP는 dot 키워드의 over-dot를 렌더하지 못함 — bar(overline)만 정상. 실측 확정.)
        s = _normalize_repeating_decimal(s)

        # 동그라미 기호 정규화: \textcircled{N|ㄱ|가} → 유니코드 ①/㉠/㉮
        s = _normalize_circled(s)

        # 리터럴 중괄호 \{ \} 를 sentinel로 보호(그룹핑 {}와 구분, 변환 중 훼손 방지).
        s = s.replace(r"\{", _SENT_LB).replace(r"\}", _SENT_RB)

        # displaymath 환경 제거
        for env in [r"\[", r"\]", r"\(", r"\)"]:
            s = s.replace(env, "")
        for env_name in ["equation", "align", "gather", "displaymath"]:
            s = re.sub(r"\\begin\{" + env_name + r"\*?\}", "", s)
            s = re.sub(r"\\end\{" + env_name + r"\*?\}", "", s)

        # 부등호 보호: bare ``<`` ``>`` 를 공백으로 감싼다. HWP 수식에서 ``<-`` 는
        # 왼쪽화살표(←), ``->`` 는 오른쪽화살표로 오인식되므로, 관계연산자 뒤에 음수가
        # 붙으면(예: ``x<-3``) 화살표로 깨진다. 화살표 토큰(``<-`` ``->`` ``<->`` ``<<``
        # ``>>``)은 \leftarrow·\to·\ll 등 명령에서 _convert_expr 내부(이 시점 이후)에
        # 생성되므로 영향받지 않는다. (실측 확정 2026-06-02)
        s = s.replace("<", " < ").replace(">", " > ")

        # 분수·근호 든 평문 괄호를 \left(...\right) 로 → 괄호 자동크기(사용자 2026-06-05).
        s = _autosize_parens(s)

        s = s.strip()
        result = self._convert_expr(s)

        # sentinel 복원: 보호했던 리터럴 중괄호 → HWP 따옴표 리터럴 "{" "}".
        # (escaped \{ \}는 뒤 문자와 인접 시 파싱이 깨지는 반면, 따옴표형은 항상 안정적 — 실측 확정.)
        result = result.replace(_SENT_LB, '"{"').replace(_SENT_RB, '"}"')

        # 도형 라벨(연속 대문자 2자+) 정자화: HWP 기본 이탤릭이라 선분/삼각형/
        # 사각형 라벨(AB, ABC, ABCD)이 기울어 보이는 것을 rm {…} 로 바로세운다.
        result = self._apply_roman_labels(result)

        # 단위 정자화: 숫자 뒤 단위(kg, cm …)를 rm`<단위>로 (정자 + 살짝 띄움).
        result = _romanize_units(result)
        # \mathrm 로 감싸진 단위(a\mathrm{cm}·5\mathrm{cm})의 ``rm <단위>`` 일반공백도 백틱으로.
        result = _backtick_rm_units(result)

        # 베이스 없는 선행 첨자(조합 ``_{n-1}C_{r-1}`` — 수식 시작/연산자 뒤 ``_{``)는 HWP 가
        # **빈 렌더**(객체는 생기나 안 보임)한다(혜화여고 #19 파스칼 항등식 통째 미표시,
        # 2026-06-12 — 계성고 ``{}_{n}C`` 플래그 동족). 빈 그룹 ``{}`` 베이스를 삽입.
        # ⚠️ 단 **대형연산자 하한**(``SUM _{k=1}``·``INT _{0}``)은 빈그룹 삽입 금지 — 공백
        # 분기가 ``SUM _{`` 를 ``SUM {}_{`` 로 깨뜨리던 회귀(적대리뷰 A-1, 2026-06-13).
        result = _LEAD_SUBSCRIPT_RE.sub(_lead_subscript_repl, result)
        # 조합/순열 ``rm C``/``rm P`` 의 로만이 **다음 선행첨자**(``+{}_{n+1}``)까지 번지는
        # 것 차단 — HWP rm 은 명시적 it 까지 뒤 전체 적용(도원중 실증). 연산자 뒤 빈그룹
        # 선행첨자 앞에 ``it`` 복귀(계성고 #4 ``ₙC₂+ₙ₊₁C₃=ₙ₊₁P₂`` 의 n+1 정자, 2026-06-12).
        result = re.sub(r"(rm\s+[A-Z](?:_\{[^{}]*\})?)\s*([+\-=<>])\s*\{\}_",
                        r"\1 \2 it {}_", result)

        # 쉼표 뒤 강제 띄어쓰기: OCR 이 준 ``, `` 공백을 HWP 수식이 시각적으로 무시해
        # ``N(m,2²)``·``(2,3)`` 처럼 붙어버린다(사용자 2026-06-09). 쉼표+공백 → ``,~`` 강제
        # 공백으로 살린다(아래첨자 ``a_{1,2}`` 등 공백 없는 쉼표는 안 건드림).
        # OCR 이 ``N(m,\, 4σ²)`` 처럼 쉼표 뒤 ``\,``(얇은공백)을 주면 변환 후 ``,`` + 백틱(1/4칸)이
        # 되어 ``,[ \t]+`` 가 못 잡았다(#16 정규분포 좌표, 2026-06-09) → 백틱도 매칭에 포함.
        result = re.sub(r",[ \t`]+", ",~", result)

        # 후처리: 다중 공백 정리
        result = re.sub(r"  +", " ", result).strip()

        # 한글 음절 사이 공백 → ``~``(HWP 전각 공백). 수식 안 bare 한글 구절(cases 조건
        # ``(x가 정수인 경우)``·``그 외`` 등)의 일반 공백을 HWP 가 시각적으로 죽여
        # ``x가정수인경우`` 로 붙던 것(강동고 수하 #15, 2026-06-14). ⚠️ ``\text{한글 구절}`` 은
        # 이미 따옴표 리터럴(``"정수인 경우"``)이라 HWP 가 공백을 보존 → 따옴표 **밖**만 변환
        # (따옴표 안 ~ 는 literal 틸드로 샘). 한글-한글 경계만 → 수식 연산자 간격 불변.
        _parts = re.split(r'("[^"]*")', result)
        for _i in range(0, len(_parts), 2):   # 짝수 인덱스 = 따옴표 밖
            _parts[_i] = re.sub(r"(?<=[가-힣]) (?=[가-힣])", "~", _parts[_i])
        result = "".join(_parts)
        return result

    # 빈칸 라벨용 괄호한글 단일문자(작은 박스): 가→㈎ … (U+320E 부터 가나다라마바사아자차…)
    _PAREN_HANGUL = {ch: chr(0x320E + i) for i, ch in enumerate("가나다라마바사아자차카타파하")}

    def _boxed_inner(self, body: str) -> str:
        """``\\boxed{...}`` 내용 변환. 빈칸 라벨 (가)/가 → 괄호한글 단일문자(작은 박스),
        그 외(식)는 일반 수식 변환."""
        b = (body or "").strip()
        m = re.fullmatch(r"\(?\s*([가-힣])\s*\)?", b)
        if m and m.group(1) in self._PAREN_HANGUL:
            return self._PAREN_HANGUL[m.group(1)]
        return self._convert_expr(b)

    def _convert_expr(self, s: str) -> str:
        """재귀적으로 LaTeX 표현식을 변환."""
        if not s:
            return ""

        # 0. 행렬/조건식 환경: \begin{env}...\end{env}
        def _env_repl(m: re.Match) -> str:
            env = m.group(1)
            content = m.group(2)
            env_map = {
                "cases": "CASES",
                "pmatrix": "PMATRIX",
                "bmatrix": "BMATRIX",
                "vmatrix": "DMATRIX",
                "matrix": "MATRIX",
            }
            hwp_env = env_map[env]
            # \\ → # (행 구분자 변환)
            content = re.sub(r"\\\\", " # ", content)
            content = self._convert_expr(content)
            # 키워드 앞이 영숫자면 공백 보장(PLEFT 계열) — ``A\begin{pmatrix}…`` 가
            # "APMATRIX" 로 붙어 literal + 다글자 대문자 오로만화(rm {APMATRIX})로
            # 깨졌다(상원고 공수1 서답형4, 2026-06-12).
            lead = " " if m.start() > 0 and m.string[m.start() - 1].isalnum() else ""
            return lead + hwp_env + " {" + content + "}"

        s = self._env_pattern.sub(_env_repl, s)

        # 0.5 \boxed{...}/\fbox{...} → BOX{ ~ … ~ }. 빈칸 라벨 (가)/(나)/(다)…는 괄호한글
        # 단일문자(㈎㈏㈐ U+320E~)로 줄여 작은 박스(원본 빈칸 모양). 그 외엔 일반 변환.
        s = self._boxed_pattern.sub(lambda m: "BOX{ ~ " + self._boxed_inner(m.group("boxed")) + " ~ }", s)

        # 1. \text, \mathrm, \mathbf — rm/bold 키워드 앞이 영숫자면 공백 보장(PLEFT 계열).
        # ``x\mathrm{km}`` 이 ``xrm km`` 으로 붙으면 HWP 가 xrm literal 렌더(매천중 #7·#18,
        # 2026-06-10). accent(bar) 수정과 동일 패턴. \text 는 따옴표 리터럴이라 무관.
        def _kw_repl(kw: str):
            def _r(m: re.Match) -> str:
                lead = " " if (m.start() > 0 and m.string[m.start() - 1].isalnum()) else ""
                return lead + kw + " " + m.group("txt")
            return _r
        s = self._text_pattern.sub(lambda m: '"' + m.group("txt") + '"', s)
        s = self._mathrm_pattern.sub(_kw_repl("rm"), s)
        s = self._mathbf_pattern.sub(_kw_repl("bold"), s)
        # \mathit{(a,b)} → it {(a,b)} — 그룹 중괄호로 it 스코프를 명시(rm 번짐 차단). 앞이
        # 영숫자면 공백 보장(``rm P\mathit`` → ``rm P it``, 키워드 분리).
        s = self._mathit_pattern.sub(
            lambda m: (" " if (m.start() > 0 and m.string[m.start() - 1].isalnum()) else "")
            + "it {" + m.group("txt") + "}", s)

        # 2. \binom{n}{k}
        s = self._binom_pattern.sub(
            lambda m: "LEFT ( {"
            + self._convert_expr(m.group("top"))
            + "} atop {"
            + self._convert_expr(m.group("bot"))
            + "} RIGHT )",
            s,
        )

        # 3. \frac{a}{b}
        s = self._frac_pattern.sub(
            lambda m: "{"
            + self._convert_expr(m.group("num"))
            + "} over {"
            + self._convert_expr(m.group("den"))
            + "}",
            s,
        )

        # 4. \sqrt[n]{x} 또는 \sqrt{x}
        #   sqrt/root 키워드도 앞 글자에 붙으면 literal 이 된다(``a\sqrt{2}`` → ``asqrt {2}``
        #   → 식별자 "asqrt" 오인, 중앙중 #4·#15). 숫자 앞(``2\sqrt{2}``)은 HWP 가 숫자→알파벳
        #   경계를 쪼개 우연히 살았을 뿐 — accent(PLEFT/XLEQ 동종)와 같이 영숫자 앞 공백 보장.
        s = self._sqrt_n_pattern.sub(
            lambda m: (" " if (m.start() > 0 and s[m.start() - 1].isalnum()) else "")
            + "root {"
            + self._convert_expr(m.group(1))
            + "} of {"
            + self._convert_expr(m.group("body"))
            + "}",
            s,
        )
        s = self._sqrt_pattern.sub(
            lambda m: (" " if (m.start() > 0 and s[m.start() - 1].isalnum()) else "")
            + "sqrt {" + self._convert_expr(m.group("body")) + "}", s
        )

        # 5. 대형 연산자
        def _big_op_repl(m: re.Match) -> str:
            op = m.group(1).upper()
            op_map = {
                "SUM": "SUM", "PROD": "PROD", "COPROD": "COPROD",
                "INT": "INT", "IINT": "DINT", "IIINT": "TINT", "OINT": "OINT",
                "BIGCUP": "UNION", "BIGCAP": "INTER",
            }
            hwp_op = op_map.get(op, op)
            lo = self._get_match(m, "lo")
            hi = self._get_match(m, "hi")
            result = hwp_op
            if lo:
                result += " _{" + self._convert_expr(lo) + "}"
            if hi:
                result += " ^{" + self._convert_expr(hi) + "}"
            return result

        s = self._big_op_pattern.sub(_big_op_repl, s)

        # 6. \left( ... \right)
        def _leftright_repl(m: re.Match) -> str:
            left = m.group(1)
            body = m.group(2)
            right = m.group(3)
            # 구분 문자 매핑
            delim_map = {
                "(": "(", ")": ")", "[": "[", "]": "]",
                # 중괄호는 sentinel 유지(step 12 그룹핑 처리 회피) → convert()에서 \{ \} 로 복원
                _SENT_LB: _SENT_LB, _SENT_RB: _SENT_RB,
                "{": _SENT_LB, "}": _SENT_RB,
                r"\langle": "langle", r"\rangle": "rangle",
                r"\|": "parallel",
                "|": "|", ".": "",
            }
            l_str = delim_map.get(left, left)
            r_str = delim_map.get(right, right)
            inner = self._convert_expr(body)
            # 중괄호 리터럴은 HWP의 LEFT/RIGHT 자동크기 구분자로 못 쓴다(렌더 깨짐).
            # 어느 한쪽이라도 중괄호면 LEFT/RIGHT 없이 인라인으로 출력한다.
            braces = {_SENT_LB, _SENT_RB}
            if l_str in braces or r_str in braces:
                return f"{l_str} {inner} {r_str}".strip()
            # 앞에 공백을 둬 인접 글자(`P\left(` → `P LEFT (`)가 키워드에 붙지 않게 한다.
            # 안 그러면 `PLEFT` 가 되어 로만화·렌더가 깨진다(사용자 2026-06-08).
            if l_str and r_str:
                return f" LEFT {l_str} {inner} RIGHT {r_str}"
            elif l_str:
                return f" LEFT {l_str} {inner}"
            elif r_str:
                return f"{inner} RIGHT {r_str}"
            return inner

        # 최내곽부터 고정점까지 반복 — 중첩 \left…\right 쌍을 안쪽→바깥쪽 순서로 정확 매칭.
        while True:
            _new = self._leftright_pattern.sub(_leftright_repl, s)
            if _new == s:
                break
            s = _new

        # 고아 \left/\right 제거: OCR이 짝(\right\})을 놓쳐 비대칭이면 위 패턴이 매칭
        # 실패해 \left 가 잔존한다. 그대로 두면 step 9 기호매핑에서 \le 가 \left 의
        # 'le' 를 먹어 "LEQft"(=≤ft) 로 깨진다(구분자 sentinel/괄호는 보존). (실측 2026-06-04)
        s = re.sub(r"\\(?:left|right)(?![a-zA-Z])", "", s)

        # 7. accent: \vec{A} → VEC A
        def _accent_repl(m: re.Match) -> str:
            cmd = "\\" + m.group(1)
            body = m.group("body")
            hwp_accent = self.ACCENT_MAP.get(cmd, m.group(1).upper())
            # HWP accent 키워드(bar·hat·vec…)는 앞 글자에 붙으면 literal 이 된다
            # (``2i\overline{z}`` → ``2ibar`` → 식별자 오인). PLEFT/XLEQ 공백 버그와 동종 —
            # 바로 앞이 영숫자면 공백을 보장한다(상인고 #24).
            lead = " " if (m.start() > 0 and s[m.start() - 1].isalnum()) else ""
            return lead + hwp_accent + " {" + self._convert_expr(body) + "}"

        s = self._accent_pattern.sub(_accent_repl, s)

        # 7.5 중괄호 없는 명령어 첨자 보호: ``45^\circ``/``x_\alpha`` → ``^{\circ}``/``_{\alpha}``.
        #   기호 치환(8·9)이 첨자 파싱(11)보다 먼저 돌아 ``45^ CIRC`` 의 첫 글자만 첨자로
        #   잡혀 "45^{C}IRC" 로 깨진다(감사 2026-06-10). 중괄호로 그룹을 보존.
        s = re.sub(r"([_^])\s*\\([a-zA-Z]+)", r"\1{\\\2}", s)

        # 8. 그리스 문자
        #   SYMBOL_MAP(9)과 동일하게 알파벳 키워드는 **앞뒤 공백 보장** — 안 그러면 명령
        #   직결 시 ``\sin\theta``→``sintheta``, ``ab\sin C``→``absin C`` 처럼 붙어 식별자
        #   오인·연속대문자 로만화로 깨진다(적대리뷰 A-2, 2026-06-13). HWP 는 여분 공백 무시.
        for latex_cmd, hwp_name in sorted(
            self.GREEK_MAP.items(), key=lambda x: -len(x[0])
        ):
            repl = hwp_name
            if repl and (repl[0].isalpha() or repl[-1].isalpha()):
                repl = " " + repl + " "
            s = s.replace(latex_cmd, repl)

        # 9. 기호/연산자
        #   HWP 키워드(LEQ, GEQ, TIMES, CDOT …)는 **앞뒤에 공백을 보장**해 인접 영숫자에
        #   붙지 않게 한다. 단순 `s.replace(\le, LEQ)` 는 `X\le 1` → `XLEQ 1` 처럼 앞 글자에
        #   붙어, 그 "XLEQ" 가 연속대문자 로만화(`_apply_roman_labels`)에 걸려 깨진다
        #   (사용자 보고 "PLEFT"/"XLEQ" 2026-06-08). HWP 수식은 여분 공백을 무시하므로 안전.
        #   값이 알파벳으로 시작/끝나는 키워드형(LEQ, neq, in …)만 패딩하고, 연산자형
        #   (->, <, |, %, \ 등)은 그대로 둔다(공백이 화살표 토큰을 깰 수 있음).
        for latex_cmd, hwp_sym in sorted(
            self.SYMBOL_MAP.items(), key=lambda x: -len(x[0])
        ):
            repl = hwp_sym
            if repl and (repl[0].isalpha() or repl[-1].isalpha()):
                repl = " " + repl + " "
            s = s.replace(latex_cmd, repl)

        # 10. 함수명 — 그리스(8)·기호(9)와 동일하게 앞뒤 공백 보장(``\sin``→`` sin ``).
        #   ``S=\frac{1}{2}ab\sin C``→``…absin C`` 식별자 오인 방지(적대리뷰 A-2).
        for latex_cmd, hwp_func in sorted(
            self.FUNC_MAP.items(), key=lambda x: -len(x[0])
        ):
            repl = hwp_func
            if repl and (repl[0].isalpha() or repl[-1].isalpha()):
                repl = " " + repl + " "
            s = s.replace(latex_cmd, repl)

        # 11. 상첨자/하첨자.
        #   HWP는 첨자 내용에 중괄호를 쓰면 본문과 간격이 벌어진다(3^{2}→"3 ²").
        #   편집기 네이티브 입력(3^2)처럼 **단순 영숫자 첨자는 중괄호 없이** 출력해
        #   밀착 렌더한다. 공백·연산자 등이 있으면 그룹핑 위해 중괄호 유지. (실측 확정)
        s = self._superscript.sub(
            lambda m: "^" + _wrap_script(self._convert_expr(self._get_match(m, "sup"))), s
        )
        s = self._subscript.sub(
            lambda m: "_" + _wrap_script(self._convert_expr(self._get_match(m, "sub"))), s
        )

        # 12. { } 내부 재귀 처리 (단순 그룹)
        def _brace_recurse(m: re.Match) -> str:
            inner = m.group(1)
            return "{" + self._convert_expr(inner) + "}"

        s = re.sub(r"\{([^{}]+)\}", _brace_recurse, s)

        # 13. HWP 공백 문자 및 기타 남은 LaTeX 명령어 정리
        s = s.replace("\\,", "`")
        s = s.replace("\\;", "~")
        s = s.replace("\\!", "")
        s = s.replace("\\qquad", "~~~~")
        s = s.replace("\\quad", "~~")
        # 제어 공백 ``\␣``(백슬래시+공백)·``\:`` — 좌표 ``(,\ a)`` 등에서 누수돼
        # ``\a`` 로 렌더되던 문제(2026-06-05). 작은/중간 공백으로 치환.
        s = s.replace("\\ ", "`")
        s = s.replace("\\:", "~")
        s = s.replace("\\\\", "")
        s = re.sub(r"\\[a-zA-Z]+", "", s)  # 남은 알 수 없는 명령어 제거

        return s


# 모듈 레벨 싱글톤
_converter = LaTeXToHWPConverter()


def latex_to_hwpeq(latex: str, italicize_stat: bool = True) -> str:
    """LaTeX 수식을 HWP 수식 스크립트로 변환.

    Args:
        latex: LaTeX 수식 문자열 (예: r"\\frac{1}{2}")
        italicize_stat: ``\\mathrm{P/E/V/…}`` 이탤릭화 여부(표 셀=True, 본문=False).
            본문은 content_parser 가 확통 이탤릭을 이미 처리했고 남은 ``\\mathrm`` 은 기하
            점(점 P) 로만이므로 False 로 보존한다(사용자 2026-06-09).

    Returns:
        HWP 수식 스크립트 (예: "{1} over {2}")
    """
    return _converter.convert(latex, italicize_stat=italicize_stat)


def latex_to_image(latex: str, dpi: int = 150) -> bytes:
    """LaTeX 수식을 PNG 이미지로 렌더링 (폴백용).

    Args:
        latex: LaTeX 수식 문자열
        dpi: 이미지 DPI

    Returns:
        PNG 이미지 바이트
    """
    import io
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(0.01, 0.01))
    ax.axis("off")

    # matplotlib의 LaTeX 렌더링
    text = ax.text(
        0.5, 0.5,
        f"${latex}$",
        transform=ax.transAxes,
        fontsize=14,
        ha="center", va="center",
    )

    # 텍스트 크기에 맞게 그림 크기 조정
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    bbox = text.get_window_extent(renderer=renderer)
    # 포인트 → 인치 변환 + 여백
    width = bbox.width / dpi + 0.1
    height = bbox.height / dpi + 0.1
    fig.set_size_inches(max(width, 0.5), max(height, 0.3))

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", pad_inches=0.02,
                transparent=True)
    plt.close(fig)
    buf.seek(0)
    return buf.read()
