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

# ``\left\{ … \right\}`` 의 **구분자 중괄호** 전용 sentinel(마지막에 맨 ``{``/``}`` 로 복원).
# HWP 는 ``LEFT { … RIGHT }``(맨 중괄호)만 자동크기 중괄호로 그린다 — 따옴표 리터럴
# ``LEFT "{"`` 는 파싱이 깨져 ``" … ÿ)`` 로 렌더된다(실측 2026-07-31, 후보 H·I·L).
# 그렇다고 변환 도중 맨 중괄호로 두면 step 12 그룹핑 재귀(\{…\})가 다시 먹으므로 sentinel.
_SENT_DLB = "\x03"  # LEFT 구분자 {

# 맨 ``\{…\}`` 승격 판정 — 내용에 이 2단 구조가 있으면 고정 리터럴 중괄호가 내용을
# 못 감싼다(조건제시법 분수 실측). \left\{ 의 ``\{`` 를 오인하지 않게 앞말을 본다.
_TALL_INNER_RE = re.compile(
    r"\\(?:d?frac|sqrt|sum|prod|int|binom|over(?:line)?\b)|\batop\b")


def _upgrade_tall_set_braces(s: str) -> str:
    """키 큰 내용을 품은 맨 ``\\{…\\}`` 를 ``\\left\\{…\\right\\}`` 로 승격."""
    i = 0
    while True:
        j = s.find(r"\{", i)
        if j < 0:
            return s
        # ``\left\{``/``\right\{`` 의 일부면 건너뛴다(이미 자동크기 경로).
        head = s[max(0, j - 6):j]
        if head.endswith("\\left") or head.endswith("\\right") or head.endswith("middle"):
            i = j + 2
            continue
        depth, k = 1, j + 2
        while k < len(s) and depth:
            if s.startswith(r"\{", k):
                depth += 1
                k += 2
            elif s.startswith(r"\}", k):
                depth -= 1
                k += 2
            else:
                k += 1
        if depth:                      # 짝 없음 — 그대로 두고 종료
            return s
        inner = s[j + 2:k - 2]
        if _TALL_INNER_RE.search(inner):
            s = s[:j] + r"\left\{" + inner + r"\right\}" + s[k:]
            i = j + 7                  # \left\{ 뒤부터 재개
        else:
            i = k
    return s
_SENT_DRB = "\x04"  # RIGHT 구분자 }
# ``\middle|`` — 짝 없는 중간 구분자. HWP 는 ``LEFT { … RIGHT | … RIGHT }`` 로 표기한다
# (실측 후보 B·C). ``\mid``(→``|``)가 ``\middle`` 을 접두 매칭해 ``|dle|`` 로 새던 버그
# (사용자 보고 2026-07-31, 현풍고 서답형4)도 이 선치환으로 함께 막는다.
_SENT_MID = "\x05"
# ``\middle`` 뒤에 올 수 있는 구분자(리터럴 중괄호는 이미 sentinel 로 보호된 상태).
_MIDDLE_RE = re.compile(
    r"\\middle\s*(\\\||\\lVert|\\rVert|\\langle|\\rangle|[|()\[\]./"
    + _SENT_LB + _SENT_RB + r"])")

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
    "g", "℃", "℉", "ℓ",
]
# 각도 위첨자 ``^\circ``/``^{\circ}``/``^{°}`` → ``°`` (위첨자 표시자 제거). ° 글리프 자체가
# 이미 위첨자 높이라 한 번 더 올리면 과하게 작고 높이 뜬다(실측 2026-08-07). 첨자 그룹의
# **유일한 내용**일 때만 매칭 — 합성함수 ``f \circ g``(위첨자 아님)는 무영향.
_DEG_SUPERSCRIPT_RE = re.compile(
    r"\^\s*(?:\{\s*(?:\\circ|\\degree|°)\s*\}|(?:\\circ|\\degree)(?![a-zA-Z])|°)"
)
# 위첨자 없이 **숫자 뒤**에 온 ``\circ`` 는 각도(``90\circ``) — OCR 이 위첨자를 빠뜨린 경우의
# 방어(corpus 상 bare \circ 30건은 전부 합성이라 실발화는 없음).
# ⚠️ **뒤에 함수 이름/여는괄호가 오면 합성**으로 되돌린다 — 첨자 숫자로 끝나는 함수열 합성
# ``f_1 \circ f_2``·``(f_2 \circ f_1)(x)`` 이 ``f_1 ° f_2`` 로 깨지던 것(적대리뷰 2026-08-07).
_BARE_DEG_CIRC_RE = re.compile(
    r"(?<=\d)\s*\\(?:circ|degree)(?![a-zA-Z])(?!\s*[A-Za-z(])")
# ⚠️ ``°`` 는 _UNITS 에서 **제외** — 이미 정자 글리프라 ``rm`` 이 불필요하고, 백틱(1/4칸)이
# 붙으면 ``90 °`` 처럼 벌어져 원본 인쇄(90°)와 어긋난다(``%`` 를 뺀 것과 같은 이유).
# ℃/℉ 는 단위 조합(온도)이라 종전대로 유지.
# 숫자와 단위 사이에 공백/`(=\,변환) 가 끼어도 단위로 인식한다(사용자 2026-06-08: "20 g"·
# "20\,g" 처럼 띄어진 단위가 로만 처리 안 됨). 단위 뒤에 영문/숫자 없을 때만(변수 5x 제외).
# L(리터)은 단독 변수와 충돌해 _UNITS 에서 뺐지만(2026-06-08), **숫자 직결 꼬리**(1L·25L)
# 에선 단위가 확실하므로 그 위치 한정으로 정자화(범물중 #22 "연료 1L", 2026-06-11).
_NUM_TAIL_UNITS = _UNITS + ["L"]
# 단위 뒤에 ``(`` 가 오면 **함수 호출**(``2g(x)``=계수2×함수g, ``aL(t)``)이지 단위가 아니다 —
# 단위 g·L 은 함수명 g(x)·L(t) 과 충돌한다. ``(`` 를 부정전망에 넣어 함수호출은 로만화 제외
# (경산여고 수2 #9 ``2g(x)`` 의 g(x) 가 ``2 rm`g(x)`` 로 로만화돼 italic 비대칭이던 것, 2026-06-23).
_UNIT_RE = re.compile(
    r"(\d)[\s`]*(" + "|".join(re.escape(u) for u in _NUM_TAIL_UNITS) + r")(?![A-Za-z0-9(])"
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
# ⚠️ **이미 로만화된 도형 라벨 안**(``rm {AL}``·``rm {"LL"}``)은 제외한다 — 2글자 라벨의
# 둘째가 단위 글자면(선분 AL·BL·KL·CL, 사용자 지적 LL) 첫 글자를 변수로, 둘째를 리터 L 로
# 오인해 ``rm {A rm`L}``("A 리터")로 깨진다. `_romanize_units` 는 `_apply_roman_labels`
# **뒤**에 돌아 라벨 내부까지 훑기 때문. 3글자 이상(``ABL``)은 앞 글자 lookbehind 로 이미
# 안전했고, corpus 실사용 0건이라 드러나지 않던 잠복 결함(2026-08-07).
# ⚠️ **이미 로만화된 단위 런 안**(``rm mL``·``rm`mL``)도 제외한다 — mL·dL·kL 처럼 **단위가
# L 로 끝나면** 앞 글자(m·d·k)를 변수로, 끝 L 을 리터로 오인해 ``rm m rm`L``("m 리터")로
# 쪼갠다(``100\mathrm{mL}`` 가 "100 m L" 로 렌더되던 것, 운암중 25-2 서답형6, 2026-08-11).
# ``rm {AL}`` 라벨 가드(2026-08-07)와 같은 계열 — 로만 런은 이미 정자라 재처리 불필요.
_VAR_UNIT_RE = re.compile(
    r"(?<![A-Za-z])(?<!rm \{)(?<!rm \{\")(?<!rm )(?<!rm`)([A-Za-z])[\s`]*("
    + "|".join(re.escape(u) for u in _VAR_TAIL_UNITS) + r")(?![A-Za-z0-9(])"
)
# 접두(숫자·}·변수글자) 없는 **단독 다문자 단위** — ``cm^{2}``(단독 "몇 cm²인가")·
# ``20\pi cm``(π 뒤 공백) 의 cm 이 로만화 안 돼 이탤릭이던 것(경산중2 #14·사동중3 #3·
# 고산중3 #11, 2026-06-15). 다문자 단위(cm/mm/km/kg…)는 변수 충돌이 거의 없어 안전.
# 이미 로만화된 ``rm`cm`` 의 백틱 뒤·식별자 글자 뒤·} 뒤는 제외(중복/오검출 방지).
_STANDALONE_UNIT_RE = re.compile(
    r"(?<![A-Za-z0-9`}])(?<!rm )(" + "|".join(re.escape(u) for u in _MULTI_UNITS) + r")(?![A-Za-z0-9])"
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
    s = _VAR_UNIT_RE.sub(lambda m: m.group(1) + " rm`" + m.group(2), s)
    return _STANDALONE_UNIT_RE.sub(lambda m: "rm`" + m.group(1), s)


# 변환 후 ``<글자/숫자> rm <단위>`` 의 일반 공백을 백틱(1/4칸)으로 — ``a\mathrm{cm}`` →
# ``a rm cm``(렌더상 "a㎝" 붙음) → ``a rm`cm``(얇은 간격). bare ``5cm`` 은 _romanize_units 가
# 이미 ``5 rm`cm`` 로 처리하나, ``\mathrm{}`` 로 감싸진 단위(변수 a\mathrm{cm}·숫자 5\mathrm{cm})는
# _mathrm_pattern 경로로 빠져 백틱이 없었다(2026-06-11 렌더 실증). _UNITS 한정이라 오검출 없음.
# 중괄호 형태 ``rm {g}`` 도 같이 받는다 — 단일 소문자 ``\mathrm{}`` 는 `_mathrm_repl` 이
# 중괄호로 감싸므로(`_stop_roman_bleed` 오작동 차단, 2026-08-11) 백틱 보정을 놓치면 bare
# ``20g``(→``20 rm`g``)와 간격이 달라진다. 중괄호는 벗기고 백틱 형태로 통일.
_RM_UNIT_RE = re.compile(
    r"([A-Za-z0-9])\s+rm\s+\{?("
    + "|".join(re.escape(u) for u in _NUM_TAIL_UNITS) + r")\}?(?![A-Za-z0-9])"
)


def _backtick_rm_units(s: str) -> str:
    """``<글자/숫자> rm <단위>`` → ``<글자/숫자> rm`<단위>`` (단위 앞 백틱 얇은공백)."""
    return _RM_UNIT_RE.sub(lambda m: m.group(1) + " rm`" + m.group(2), s)


def _space_value_commas(s: str) -> str:
    """쉼표 뒤 강제 띄어쓰기(``,~``) — 좌표/나열 쉼표를 HWP 가 시각적으로 죽이는 것 방지.

    HWP 수식은 ``(2,3)``·``P(25,3)`` 의 쉼표 뒤 공백을 시각적으로 무시해 ``(2,3)`` 로 붙인다
    (사용자 2026-06-09·2026-06-18: "좌표형태는 항상 ``P(25, ~3)``"). 종전엔 쉼표 **뒤에 공백이
    이미 있을 때만**(``re.sub(r",[ \t`]+", ",~")``) ``,~`` 로 살려서, OCR 이 ``\mathrm{P}(25,3)``
    처럼 공백 없는 좌표를 주면(경상여고 대수 #11) ``,3`` 이 그대로 붙었다. 이제 **괄호 안(좌표/
    함수 인자) 쉼표는 공백 유무와 무관하게** ``,~`` 로, 괄호 밖은 종전대로 **공백이 있을 때만**
    ``,~`` 로 처리한다(아래첨자 ``a_{1,2}`` 의 공백 없는 쉼표는 괄호 밖 ``{}`` 안이라 보존).
    """
    out: list[str] = []
    paren = 0
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c == "(":
            paren += 1
            out.append(c)
            i += 1
        elif c == ")":
            if paren > 0:
                paren -= 1
            out.append(c)
            i += 1
        elif c == ",":
            j = i + 1
            while j < n and s[j] in " \t`":
                j += 1
            had_space = j > i + 1
            if had_space:
                # 종전 동작 유지(``,[ \t`]+`` → ``,~``): 공백을 ~ 로, 뒤따르는 ~/`\quad` 의 ~~ 는
                # 그대로 흘려보낸다(``, \quad`` → ``,~~~`` 등 기존 reviewed 출력 보존).
                out.append(",~")
                i = j
            elif j < n and s[j] == "~":
                # 공백 없이 이미 ``,~`` 면 중복 삽입 금지(LaTeX 값 ``(b,~-2)`` → ``,~~`` 회귀 방지).
                out.append(",")
                i = j
            elif paren > 0:
                # **신규**: 괄호 안(좌표·인자) 공백 없는 쉼표 → ``,~`` (``\mathrm{P}(25,3)`` 경상여고 #11).
                out.append(",~")
                i = j
            else:
                out.append(",")
                i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)


# 베이스 없는 선행 첨자(``_{n-1}C``)에 빈그룹 베이스 ``{}`` 삽입(혜화여고 #19). 단 대형
# 연산자 하한(``SUM _{k=1}``·``INT _{0}``·``UNION _{i}`` …)은 그 op 의 정상 첨자라 삽입하면
# 안 된다 — 공백 분기가 ``SUM _{`` 를 ``SUM {}_{`` 로 깨던 회귀(적대리뷰 A-1, 2026-06-13).
_LEAD_SUBSCRIPT_RE = re.compile(r"(^|[+\-=<>(\s])_\{")
# endswith 는 부분일치라 ``INT`` 가 ``DINT``/``TINT``/``OINT`` 를, ``PROD`` 가 ``COPROD`` 를
# 포괄한다(대형연산자 출력 키워드 전체).
_BIG_OP_KEYWORDS = ("SUM", "PROD", "INT", "UNION", "INTER")

# 소문자 극한형 연산자(lim·max·min·sup·inf·gcd·det) — 첨자가 연산자 **아래**로 가야 한다.
# HWP 실측: ``lim _{x->0}`` = 아래첨자(정상), ``lim {}_{x->0}`` = 우측첨자(깨짐). 그래서 빈그룹
# ``{}`` 삽입을 금지해 ``lim _{`` 를 보존한다(int/sum 은 _BIG_OP_KEYWORDS 가드로 이미 정상).
# 사용자 2026-06-17: ``\lim_{x\to0}`` 가 ``lim {}_{x->0}`` 로 변환돼 x→0 가 lim **우측**에
# 붙던 회귀(_{n-1}C 빈그룹 삽입의 부작용, ~2026-06-12 도입). 실증 .testkit/_eq_limtest.py
# (A=우측 broken / B=아래 fix / F=lim inf 아래). 단어경계 lookbehind 로 ``xlim`` 등 오매칭 차단.
_BELOW_OP_LOWER_RE = re.compile(r"(?<![A-Za-z])(?:lim|max|min|sup|inf|gcd|det)$")

# HWP 연산자 키워드와 글자가 같은 점/선분 라벨 — rm {} 안에서도 HWP 가 관계연산자로
# 토큰화해 글자가 증발한다(GE→≥, LE→≤, NE→≠, GG→≫, LL→≪; 대륜중2 #16 GE→≥ 실증).
# 이 라벨은 따옴표 리터럴(□·★ 방식)로 감싸 토큰화를 차단한다.
_KEYWORD_LABEL_QUOTE = {"GE", "LE", "NE", "GG", "LL"}


def _lead_subscript_repl(m: "re.Match") -> str:
    sep = m.group(1)
    # 공백 분기일 때만 — 앞 토큰이 대형연산자/극한형 연산자면 그 op 의 하한이므로 빈그룹 삽입 금지.
    if sep and sep.isspace():
        prefix = m.string[:m.start()].rstrip()
        if prefix.endswith(_BIG_OP_KEYWORDS) or _BELOW_OP_LOWER_RE.search(prefix):
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
        # 닮음 기호: 한국 교과서는 ∽(U+223D). HWP 키워드 SIM 은 ∼(U+223C, similar)로
        # 렌더돼 닮음 글리프가 어긋난다(경산여중2·능인중2·구암중2, 2026-06-15). 리터럴 ∽로.
        r"\backsim": "∽",
        r"\sim": "∽",
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
        # 공집합/공사건 ∅ — HWP eq 에 ``emptyset`` 키워드가 없어 literal "emptyset" 로 렌더되던
        # 것(영진고 확통 #8 ``P(\varnothing)`` 이 ``P()``로 증발). □(\square)·∖(\setminus) 처럼
        # 유니코드 따옴표 리터럴로 고정. ``\varnothing``(∅, 자주 쓰임)도 같은 기호로.
        r"\emptyset": '"∅"',
        r"\varnothing": '"∅"',
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
        # 각: HWP 키워드는 대소문자 무관하게 같은 ∠ 글리프로 렌더된다(실측 2026-08-07,
        # `angle`/`ANGLE` 픽셀 동일). 사용자 지정 표기(HWP 수식편집기 표준)에 맞춰 대문자로.
        r"\angle": "ANGLE",
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
        # 각도 \degree → ° (리터럴 도, 정상 렌더). 과거 대문자 CIRC 키워드를 각도로 쓰려다
        # 통째 깨져 ° 가 증발했다(경명여중3·노변중3·영남삼육중3, 2026-06-15) — 당연한 결과로,
        # circ 키워드는 **각도 ° 가 아니라 합성 ∘** 이기 때문이다(실측 확정 2026-08-07).
        r"\degree": "°",
        # ⭐ ``\circ`` 단독 = **합성함수 ∘**(HWP ``circ`` 키워드로 정상 렌더 — 실측
        # `.testkit/_ang_probe5.py` #3, 리터럴 ``"∘"`` 과 픽셀 동일). 각도는 ``^\circ``
        # (위첨자) 형태로 오고 전처리 `_DEG_SUPERSCRIPT_RE` 가 이미 ``°`` 로 떼어낸 뒤이며,
        # 위첨자 없는 숫자 직결 ``90\circ`` 도 `_BARE_DEG_CIRC_RE` 가 각도로 처리한다.
        # 종전 ``\circ``→``°`` 는 corpus 30건(9개교)의 ``(f∘g)(x)`` 를 ``(f°g)(x)`` 로
        # 렌더하던 오류(사용자 2026-08-07 확인 후 수정).
        r"\circ": "circ",
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
        # 호(⌒) — 중·고등 수학에서 \widehat 은 사실상 항상 호다. HAT(꺾쇠 악상)로
        # 두면 hat{rm AB} 가 원본(호 장식)과 어긋난다(사용자 2026-08-09 오성중:
        # "arch {rm AB} = 9 pi `rm cm 로 할 것"). \overarc 와 동일 매핑.
        r"\widehat": "arch",
        r"\widetilde": "TILDE",
    }

    # 대문자 연속런(AB, ABC, ABCD …)을 정자(rm)로 감쌀 때 **제외**할 HWP 키워드.
    # HWP 수식은 라틴 문자를 기본으로 이탤릭 렌더하므로(실측 확정 2026-06-02:
    # `x+ay-1` 기본 = `it {x+ay-1}` 와 픽셀 동일), 변수는 손대지 않는다. 다만
    # 도형 라벨(선분 AB·삼각형 ABC·사각형 ABCD 등)도 이탤릭이 되어버리므로,
    # 연속 대문자 2자 이상을 `rm {…}` 로 정자화한다. 이때 SUM·LEFT·LEQ 같은
    # 전부-대문자 키워드는 라벨이 아니라 제어어이므로 감싸면 안 된다 → 이 집합으로 제외.
    # 프라임(') 을 라벨 글자에 허용 — 대칭이동/접기의 상(像) 라벨 ``A'P``·``QB'``·``A'B'`` 이
    # ``[A-Z]{2,}`` 에 안 걸려 **이탤릭으로 남던 것**(사용자 2026-08-07 렌더 지적: 같은 줄의
    # ``AP``·``PQ``·``QB`` 는 정자인데 프라임 라벨만 기울어 혼재). ``(?:[A-Z]'*){2,}`` = 대문자
    # 2자 이상이면 사이·끝 프라임 허용. **단일 대문자+프라임**(``A'``·도함수 ``F'(x)``)은
    # 여전히 제외 — 함수 도함수와 구분이 안 돼 위험하다(점 ``A'(7,4)`` 는 좌표쌍+기하 게이트가
    # 있는 content_parser `_POINT_COORD_RE` 가 담당).
    _ROMAN_LABEL_RE = re.compile(r"(?<![A-Za-z])((?:[A-Z]'*){2,})(?![A-Za-z])")
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
        # ``"..."`` HWP 리터럴 구간(=\text{} 출력) 안의 대문자는 이미 정자라 rm {} 로 감싸면 안
        # 된다 — ``\text{ABCD}`` → ``"ABCD"`` 가 ``"rm {ABCD}"`` 로 깨져 HWP 가 'rm {ABCD}' 를
        # **리터럴 렌더**(다사중 #7 직사각형 ABCD, 사용자 2026-06-24). 따옴표 구간을 미리 구한다.
        _quoted_spans: list[tuple[int, int]] = []
        _qs = -1
        for _i, _ch in enumerate(script):
            if _ch == '"':
                if _qs < 0:
                    _qs = _i
                else:
                    _quoted_spans.append((_qs, _i))
                    _qs = -1

        def _in_quote(pos: int) -> bool:
            return any(a < pos < b for a, b in _quoted_spans)

        def _repl(m: "re.Match") -> str:
            run = m.group(1)
            if run in self._roman_skip:
                return run
            start = m.start(1)
            if _in_quote(start):
                return run   # 따옴표 리터럴 안 = 이미 정자(중복/깨짐 방지)
            prev = m.string[max(0, start - 4):start]
            # 이미 rm/it/bold 로 감싸진 라벨(예: \mathrm 출력)은 중복 적용 방지.
            if prev.endswith("rm {") or prev.endswith("rm ") \
                    or prev.endswith("it {") or prev.endswith("bold"):
                return run
            # HWP 연산자 키워드와 충돌하는 점/선분 라벨(GE=≥·LE=≤·NE=≠·GG=≫·LL=≪)은
            # rm {} 안에서도 HWP 가 ≥ 등으로 토큰화해 글자가 사라진다(대륜중2 #16 GE→≥,
            # 2026-06-15 렌더 실증). 따옴표 리터럴(□·★ 방식)로 감싸 토큰화 차단.
            # 프라임 라벨(``GE'``)도 같은 함정 — HWP 는 **연속 대문자 시퀀스**를 토큰화하므로
            # 프라임이 붙어도 ``rm {GE'}`` 는 ≥′ 로 글자가 사라진다(실측 2026-08-07). 반대로
            # ``G'E`` 는 프라임이 끼어 GE 연속이 아니라 안전 → 프라임으로 끊은 **세그먼트**
            # 단위로 판정해 키워드 세그먼트만 따옴표로 감싼다(``GE'`` → ``rm {"GE"'}``).
            # 프라임 없는 라벨은 종전과 동일한 결과(무회귀).
            if any(seg in _KEYWORD_LABEL_QUOTE for seg in run.split("'") if seg):
                quoted = re.sub(
                    r"[A-Z]+",
                    lambda mm: ('"' + mm.group(0) + '"'
                                if mm.group(0) in _KEYWORD_LABEL_QUOTE else mm.group(0)),
                    run)
                return "rm {" + quoted + "}"
            return "rm {" + run + "}"

        return self._ROMAN_LABEL_RE.sub(_repl, script)


    # HWP 의 ``rm`` 은 **명시적 ``it`` 이 나올 때까지 뒤 전체**에 적용된다(도원중 렌더 실증).
    # 그래서 ``TRIANGLE rm {ANC} = p TIMES …`` 의 변수 ``p`` 가 정자로 나갔다(왕선중 #9,
    # 사용자 2026-07-27 "it{p} 같은 느낌으로"). 라벨 뒤의 **단일 소문자 변수**만 ``it {p}`` 로
    # 감싸 이탤릭을 되살린다 — HWP 키워드(bar·angle·sqrt·lim …)는 모두 2자 이상이라 무영향.
    _ROMAN_BLEED_SCAN = re.compile(
        r"(?P<style>(?<![A-Za-z])(?:rm|it)(?![A-Za-z]))"
        r"|(?P<var>(?<![A-Za-z0-9_`{])[a-z](?![A-Za-z0-9_]))")

    def _stop_roman_bleed(self, script: str) -> str:
        """``rm`` 이후 단일 소문자 변수를 ``it {x}`` 로 감싸 정자 번짐을 끊는다."""
        out, last, roman = [], 0, False
        for m in self._ROMAN_BLEED_SCAN.finditer(script):
            if m.lastgroup == "style":
                roman = (m.group("style") == "rm")
                continue
            if not roman:
                continue
            out.append(script[last:m.start()])
            out.append("it {" + m.group("var") + "}")
            last = m.end()
        out.append(script[last:])
        return "".join(out)

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

        # \begin{env}...\end{env} (행렬/조건식/표)
        # ``array`` 는 뒤에 열 정렬 스펙 ``{r|rrrr}`` 이 붙는다(조립제법·나눗셈 과정 표).
        # HWP matrix 에는 정렬 스펙이 없으므로 스펙만 떼고 내용은 살린다.
        self._env_pattern = re.compile(
            r"\\begin\{(cases|pmatrix|bmatrix|vmatrix|matrix|array)\}"
            r"(?:\s*\{[^{}]*\})?"          # array 열 스펙(있으면 버린다)
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

        # ``\lt`` ``\gt`` (less-than/greater-than) — SYMBOL_MAP 에 ``\le``/``\ge`` 만 있고
        # ``\lt``/``\gt`` 가 없어, OCR 이 부등호를 ``\lt``/``\gt`` 로 주면(경상여고 대수 #9
        # ``\cos\theta\tan\theta \lt 0``) step 13 의 ``\\[a-zA-Z]+`` 에서 **조용히 삭제**돼
        # 부등호가 통째 증발했다(``cosθtanθ 0``). 리터럴 ``<``/``>`` 로 정규화하면 아래 line의
        # ``<``→`` < `` 간격 처리까지 함께 받는다. ``\ltimes``/``\gtrsim`` 오매칭은 경계로 차단.
        s = re.sub(r"\\lt(?![a-zA-Z])", "<", s)
        s = re.sub(r"\\gt(?![a-zA-Z])", ">", s)

        # ``\not`` 부정 — SYMBOL_MAP 에 ``\not`` 단독이 없어, 뒤 ``\in``/``=`` 만 치환되고
        # ``\not`` 은 step 13 의 ``\\[a-zA-Z]+`` 에서 **조용히 삭제**돼 ∉→∈·≠→= 로 **의미가
        # 뒤집히던** 무증상 오답(적대리뷰 B-1). 부정형을 매핑된 명령으로 정규화(없으면 NOT
        # 리터럴로 보존 — 침묵 반전 금지).
        s = re.sub(r"\\not\s*\\in\b", r"\\notin", s)
        s = re.sub(r"\\not\s*=", r"\\neq", s)
        s = re.sub(r"\\not\s*\\equiv\b", r' NOT EQUIV ', s)
        s = re.sub(r"\\not\s*\\subset\b", r' NOT SUBSET ', s)
        s = re.sub(r"\\not\s*(\\[a-zA-Z]+|[<>])", r' NOT \1', s)

        # ``\limits``/``\nolimits`` 위치 수식자 제거 — HWP eq 는 ``lim _{…}``·``SUM _{…}^{…}`` 가
        # 이미 연산자 아래/위로 렌더하므로 no-op. 안 지우면 step 13 의 ``\lim`` 부분매칭이
        # ``\lim\limits`` → "lim lim its"(중복 lim + 잔여 'its'), ``\sum\limits`` → "SUM lim its"
        # 로 깨졌다(진명여고·학남고 수2 #1·6·12·13·15·17·21, 2026-06-23).
        s = re.sub(r"\\(?:no)?limits(?![a-zA-Z])", "", s)

        # 각도 ``90^\circ`` → ``90°`` — **위첨자 표시자를 뗀다**. ° 글리프는 그 자체가 이미
        # 베이스라인 위 작은 동그라미라, 위첨자로 한 번 더 올리면 ``90˚`` 처럼 과하게 작고
        # 높이 떠 원본 인쇄(90°)와 어긋난다(HWP 실측 확정 2026-08-07, 사용자 지적).
        # ``\circ``/``\degree``/유니코드 ° 가 **첨자 그룹의 유일한 내용**일 때만 — 합성함수
        # ``f \circ g``(위첨자 아님)·다른 첨자 내용은 건드리지 않는다.
        s = _DEG_SUPERSCRIPT_RE.sub("°", s)
        # 위첨자 없이 숫자 직결된 ``\circ``/``\degree`` 도 각도로(합성함수는 앞이 숫자가 아님).
        s = _BARE_DEG_CIRC_RE.sub("°", s)

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

        # ⭐ 키 큰 내용을 품은 맨 ``\{…\}`` → ``\left\{…\right\}`` 승격(사용자 2026-08-09):
        # 조건제시법 ``B=\{\frac{x+14}{3}|x\in A\}`` 를 모델이 \left 없이 주면 고정 크기
        # 리터럴 ``"{"``/``"}"`` 가 분수를 못 감쌌다. 내용에 2단 구조가 있을 때만 —
        # 짧은 ``\{7,13\}`` 은 종전 리터럴 유지(2026-07-31 corpus 무회귀 결정 보존).
        # ⚠️ 반드시 sentinel 보호 **앞**에서 — 보호 뒤엔 ``\{`` 가 이미 사라져 무효.
        s = _upgrade_tall_set_braces(s)
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
        # LEFT/RIGHT 구분자 중괄호는 **맨 중괄호**로(자동크기), 짝 없는 \middle 은 제거.
        result = result.replace(_SENT_DLB, "{").replace(_SENT_DRB, "}")
        result = result.replace(_SENT_MID, "")

        # 도형 라벨(연속 대문자 2자+) 정자화: HWP 기본 이탤릭이라 선분/삼각형/
        # 사각형 라벨(AB, ABC, ABCD)이 기울어 보이는 것을 rm {…} 로 바로세운다.
        result = self._apply_roman_labels(result)

        result = self._stop_roman_bleed(result)   # rm 번짐 차단(단일 소문자 변수)
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
        # 괄호 안(좌표·인자) 쉼표는 공백 없이 붙은 ``(25,3)`` 도 ``,~`` 로(경상여고 대수 #11).
        result = _space_value_commas(result)

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

        # 0-. ``\middle<구분자>`` 선치환 — 기호매핑(9)의 ``\mid``→``|`` 이 ``\middle`` 을
        #     접두 매칭해 ``|dle|`` 로 새는 것을 막는다. sentinel 은 감싸는 \left…\right
        #     쌍에서 ``RIGHT`` 로 승격되고(=자동크기 세로바), 짝이 없으면 convert() 끝에서
        #     그냥 지워져 평범한 구분자만 남는다.
        s = _MIDDLE_RE.sub(lambda m: _SENT_MID + m.group(1), s)

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
                "array": "MATRIX",      # HWP 에 array 대응이 없어 matrix 로(정렬·괘선 손실)
            }
            hwp_env = env_map[env]
            # \\ → # (행 구분자 변환)
            content = re.sub(r"\\\\", " # ", content)
            # array 의 가로 괘선·간격 명령은 HWP matrix 에 대응이 없다 → 제거
            # (안 지우면 ``\hline`` 이 백슬래시째 literal 로 새 나간다)
            content = re.sub(r"\\(?:hline|cline\s*\{[^{}]*\}|noalign\s*\{[^{}]*\})", "", content)
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
        def _text_repl(m: "re.Match") -> str:
            txt = m.group("txt")
            # 도형 라벨(순수 대문자 라틴 1+자) → 정자 로만 ``rm {…}``. 따옴표 리터럴 ``"ABCD"`` 은
            # HWP 가 **이탤릭**으로 렌더해 도형 이름(직사각형 ABCD)이 기운다(§2-10 위반, 다사중 #7
            # ``\text{ABCD}``, 사용자 2026-06-24). 단어·혼합·기호 ``\text{}`` 는 종전대로 따옴표
            # 리터럴. HWP 연산자 충돌 라벨(GE/LE/NE/GG/LL)은 토큰화 차단 위해 인용 보호.
            if txt and re.fullmatch(r"[A-Za-z]+", txt) and txt.isupper():
                lead = " " if (m.start() > 0 and m.string[m.start() - 1].isalnum()) else ""
                inner = '"' + txt + '"' if txt in _KEYWORD_LABEL_QUOTE else txt
                return lead + "rm {" + inner + "}"
            return '"' + txt + '"'
        s = self._text_pattern.sub(_text_repl, s)
        # \mathrm{X} → rm X. HWP rm 은 명시적 it 전까지 **뒤 전체로 번지므로**, ``\mathrm`` 뒤에
        # 수식 내용이 더 이어지면(예 ``\mathrm{pH} = -\log x``) 뒤따르는 변수(x)까지 정자(로만)로
        # 굳는다(경상여고 대수 #5 pH, 사용자 2026-06-18: ``rm {pH}= it {-logx}`` 처럼 돼야 x 이탤릭).
        # 그래서 뒤에 **이탤릭 대상이 될 내용**이 이어지면 ``it`` 를 끼워 로만 스코프를 닫는다.
        # 제외: ① 첨자/프라임(``_``·``^``·``'``)은 로만 베이스에 붙으므로 it 가 끊으면 안 됨,
        # ② 다음이 또 다른 스타일 명령(\mathit/\mathrm/\mathbf/\text/\boxed)이면 그쪽이 스코프 관리,
        # ③ 뒤에 **소문자 변수**(이탤릭 대상)가 없으면 불필요 — 명령어(\log·\angle 등) 제거 후
        #    소문자가 남아야 삽입한다. 그래야 ``\angle\mathrm{A}=\angle\mathrm{B}``(뒤가 전부
        #    로만/연산자/대문자 라벨, 번짐 무해)에는 ``it`` 를 안 넣어 기존 reviewed 출력을 보존하고,
        #    ``\mathrm{pH}=-\log x``(소문자 x 변수)에만 넣는다. 숫자 좌표 ``\mathrm{P}(25,3)`` 도
        #    소문자 없어 미삽입(쉼표만 보정 → ``rm P(25,~3)``), 글자 좌표 ``\mathrm{P}(a,b)`` 는
        #    삽입 → ``rm P it (a,~b)``(좌표 이탤릭, 점이름 로만 — 설계 형태와 일치).
        # ⚠️ **단일 소문자 내용은 중괄호로 감싼다**(``\mathrm{m}`` → ``rm {m}``) — bare ``rm m`` 은
        # 뒤이어 도는 `_stop_roman_bleed`(rm 뒤 단일 소문자 = 번짐 피해자로 보고 ``it {}`` 로 감쌈,
        # 2026-07-27 왕선중 #9)가 **rm 자기 피연산자**와 구별하지 못해 ``rm it {m}``(단위 m 이
        # 이탤릭)으로 뒤집는다. 미터 단위 ``20\mathrm{m}``·``5\mathrm{m}`` 가 전 corpus 에서
        # 기울어 있던 잠복 결함(운암중 25-2 서답형2 렌더로 발각, 2026-08-11). ``{`` 앞 lookbehind 가
        # 있어 감싸면 bleed 스캐너가 건너뛴다. 다문자(``cm``·``mL``)는 스캐너가 애초에 단일 글자만
        # 보므로 무영향, 대문자(``\mathrm{P}``)도 스캐너 대상(`[a-z]`)이 아니라 무영향 → churn 최소.
        _MATHRM_NEXT_STYLE = re.compile(r"\\(?:math(?:rm|it|bf|bb)|text|boxed|fbox)\b")
        def _mathrm_repl(m: "re.Match") -> str:
            lead = " " if (m.start() > 0 and m.string[m.start() - 1].isalnum()) else ""
            txt = m.group("txt")
            if re.fullmatch(r"[a-z]", txt):
                txt = "{" + txt + "}"
            base = lead + "rm " + txt
            tail = m.string[m.end():]
            tstrip = tail.lstrip(" \t")
            no_cmd = re.sub(r"\\[a-zA-Z]+", "", tstrip)   # 함수·기호 명령(키워드) 제거
            if (tstrip and tstrip[0] not in "_^'}"
                    and not _MATHRM_NEXT_STYLE.match(tstrip)
                    and re.search(r"[a-z]", no_cmd)):
                return base + " it "
            return base
        s = self._mathrm_pattern.sub(_mathrm_repl, s)
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
                # 중괄호 구분자는 **맨 ``{``/``}``** 여야 자동크기로 그려진다(따옴표 리터럴
                # ``LEFT "{"`` 는 렌더 깨짐 — 실측 2026-07-31). 변환 도중 그룹핑 재귀에
                # 먹히지 않게 전용 sentinel 로 두고 convert() 끝에서 맨 중괄호로 복원한다.
                _SENT_LB: _SENT_DLB, _SENT_RB: _SENT_DRB,
                "{": _SENT_DLB, "}": _SENT_DRB,
                r"\langle": "langle", r"\rangle": "rangle",
                r"\|": "parallel",
                "|": "|", ".": "",
            }
            l_str = delim_map.get(left, left)
            r_str = delim_map.get(right, right)
            inner = self._convert_expr(body)
            # ``\middle|`` → ``RIGHT |``(자동크기 중간 구분자). 여는 LEFT 가 있을 때만
            # 승격하고, 없으면(``\left. … \right.``) 구분자만 남긴다.
            inner = inner.replace(_SENT_MID, " RIGHT " if l_str else "")
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


# ── 긴 전개식 접기(#=행, &=정렬) ─────────────────────────────────────────────
# ⭐ 수식 객체는 **내부에서 줄바꿈이 안 되는 원자**라, 칼럼보다 넓은 전개식 하나가
# 단 구분선을 넘어 옆 단을 침범한다(오성중 서답형3 실측 2026-08-10 — 정답면 8쪽).
# HWP 수식은 ``#`` 로 행을, ``&`` 로 정렬 기준을 준다(사용자 제안·실측 확인):
#     ``A &= B # &= C # &= D`` → ``=`` 를 세로로 맞춘 여러 행
# 완료본의 전개식 표기와 같은 모양이고, 칼럼 안에 들어간다.
_FOLD_MAX_ROWS = 4          # 조각이 너무 잘게 쪼개지면 오히려 읽기 나쁘다
_FOLD_MIN_SEG = 3           # 이보다 짧은 조각은 앞 행에 붙인다(고아 방지)


def _toplevel_eq_cuts(script: str) -> list[int]:
    """HWP 스크립트에서 **최상위** ``=`` 위치들. 중괄호·괄호·LEFT/RIGHT 안은 제외."""
    cuts: list[int] = []
    depth = 0
    lr = 0                     # LEFT…RIGHT 깊이 — 구분자가 | . 면 괄호로 안 잡힌다
    i, n = 0, len(script)
    while i < n:
        if script.startswith("LEFT", i) and (i + 4 >= n or not script[i + 4].isalpha()):
            lr += 1
            i += 4
            continue
        if script.startswith("RIGHT", i) and (i + 5 >= n or not script[i + 5].isalpha()):
            lr = max(0, lr - 1)
            i += 5
            continue
        c = script[i]
        if c in "({[":
            depth += 1
        elif c in ")}]":
            depth = max(0, depth - 1)
        elif c == "=" and depth == 0 and lr == 0 and i > 0:
            prev, nxt = script[i - 1], (script[i + 1] if i + 1 < n else "")
            # <= >= != == 는 한 덩어리 — 그 안에서 끊지 않는다.
            if prev not in "<>!=" and nxt != "=":
                cuts.append(i)
        i += 1
    return cuts


def fold_long_equation(script: str, max_rows: int = _FOLD_MAX_ROWS) -> str:
    """긴 전개식을 ``#``(행) + ``&``(정렬)로 접는다. 접을 수 없으면 원본 그대로.

    ⚠️ 이미 ``#``/``&`` 를 쓰는 스크립트(CASES·PMATRIX·행렬·기존 정렬식)는 **손대지
    않는다** — 그 문법을 덮어써 구조가 깨진다. 접은 뒤 중괄호·LEFT/RIGHT 균형이
    맞지 않으면 통째 롤백한다(미지의 형태까지 덮는 최후 안전망).
    """
    s = (script or "").strip()
    if not s or "#" in s or "&" in s:
        return script
    cuts = _toplevel_eq_cuts(s)
    if len(cuts) < 2:                     # A=B 한 번은 접을 이유가 없다
        return script
    segs, prev = [], 0
    for c in cuts:
        seg = s[prev:c].strip()
        if seg:
            segs.append(seg)
        prev = c
    tail = s[prev:].strip()
    if tail:
        segs.append(tail)
    if len(segs) < 2:
        return script
    # 너무 짧은 조각은 앞에 병합(고아 방지) — 첫 조각은 그대로 둔다.
    merged = [segs[0]]
    for seg in segs[1:]:
        if len(seg.replace("=", "").strip()) < _FOLD_MIN_SEG:
            merged[-1] = merged[-1] + " " + seg
        else:
            merged.append(seg)
    # 행 수 상한 — 넘으면 뒤쪽을 마지막 행에 몰아 넣는다.
    if len(merged) > max_rows:
        merged = merged[:max_rows - 1] + [" ".join(merged[max_rows - 1:])]
    if len(merged) < 2:
        return script
    rows = [merged[0]] + [f"&{seg}" for seg in merged[1:]]
    folded = " # ".join(rows)
    # 첫 행에도 정렬 기준(&)을 넣어야 = 가 세로로 맞는다.
    first_cuts = _toplevel_eq_cuts(merged[0])
    if first_cuts:
        k = first_cuts[0]
        rows[0] = merged[0][:k].rstrip() + " &" + merged[0][k:]
        folded = " # ".join(rows)
    # 균형 검증 — 깨지면 통째 롤백(원본이 잘못 나가는 것보다 낫다).
    if (folded.count("{") != s.count("{") or folded.count("}") != s.count("}")
            or folded.count("LEFT") != s.count("LEFT")
            or folded.count("RIGHT") != s.count("RIGHT")):
        return script
    return folded


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
