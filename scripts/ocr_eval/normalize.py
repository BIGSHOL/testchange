"""정규화 + 문자열 유사도 — OCR 채점 코어(stdlib only).

⚠️ **이 모듈은 절대 `core.*`·`anthropic` 를 import 하지 않는다.** 채점기/골든 테스트가
anthropic·API 키 없이(CI·다른 PC) 돌아야 하기 때문이다. (core.ocr_engine 은 최상단에서
`import anthropic` 하므로 끌어오면 오프라인에서 죽는다.)

## 정규화 원칙 (가장 중요)
**"노이즈(공백·전각 등)만 제거, 시험 정답을 바꾸는 차이는 절대 흡수하지 않는다."**
지수(`2^{48}` vs `2^{6}`)·분수 숫자·로만/이탤릭(`\\mathrm{A}` vs `A`)·대소문자(P↔p)
오인이 **점수 하락으로 드러나야** 한다. 그래서:
  - 채점 기본 텍스트 정규화 = `norm_text_strict` (대소문자 **보존**).
  - `norm_text_loose`(소문자화)는 core.ocr_engine._norm_match 와 동일 — **참고/레거시 전용**.
  - `norm_latex` 는 **간격 매크로만** 지우고 구조(`^ _ { } \\frac \\sqrt \\mathrm …`)는 보존.
"""

from __future__ import annotations

import difflib
import re

# 공백·문장부호·언더스코어 묶음(매칭 노이즈). 대소문자는 *건드리지 않는다*.
_NOISE_RE = re.compile(r"[\s\W_]+")


def norm_text_strict(s: str) -> str:
    """채점 기본 정규화: 공백·문장부호만 제거, **대소문자 보존**.

    `P(A)` → ``PA`` / `p(A)` → ``pA`` 처럼 대소문자 차이를 **유지**해 P↔p 오인이
    점수 하락으로 드러나게 한다(소문자화하면 둘 다 ``pa`` 가 되어 차이를 삼킨다).
    """
    return _NOISE_RE.sub("", s or "")


def norm_text_loose(s: str) -> str:
    """레거시/참고 정규화 = core.ocr_engine._norm_match 와 동일(소문자화).

    **채점 기본값이 아니다.** 대소문자를 무시하고 "대충 같은가"만 보고 싶을 때만.
    """
    return _NOISE_RE.sub("", s or "").lower()


# 간격(spacing) 매크로 — **긴 것부터** 제거해야 `\\qquad` 가 `\\quad` 로 잘리지 않는다.
# 시각적 간격일 뿐 값을 바꾸지 않으므로 노이즈로 보고 지운다.
_LATEX_SPACING_PATTERNS = [
    r"\\qquad",
    r"\\quad",
    r"\\,",
    r"\\!",
    r"\\;",
    r"\\:",
    r"\\ ",       # 백슬래시+공백(thin space)
]
_SPACING_RE = re.compile("|".join(_LATEX_SPACING_PATTERNS))


def norm_latex(s: str) -> str:
    """수식 비교용 보수적 정규화.

    제거: 일반 공백 + 간격 매크로(`\\, \\! \\; \\: \\quad \\qquad` 등).
    **절대 보존**(제거 금지): `^` `_` `{` `}` `\\frac` `\\sqrt` `\\mathrm` `\\text`
    `\\left` `\\right`. 이것들을 지우면 지수/분수/로만체 차이가 사라져 회귀를 *삼킨다*.
    """
    s = s or ""
    s = _SPACING_RE.sub("", s)     # 간격 매크로(토큰 경계 보존, 긴 것부터)
    s = re.sub(r"\s+", "", s)      # 남은 일반 공백
    return s


def seq_ratio(a: str, b: str) -> float:
    """두 (정규화된) 문자열의 difflib 유사도 [0,1]. 둘 다 빈 문자열이면 1.0."""
    if not a and not b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()
