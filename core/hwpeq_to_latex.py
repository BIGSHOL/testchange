# -*- coding: utf-8 -*-
"""HWP 수식 스크립트 → LaTeX (역변환)

완료본 HWP 에서 뽑은 수식은 HWP 스크립트(``{1} over {2}``·``x ^{2}``·``LEFT (``)다.
OCR JSON 스키마와 `content_parser` 는 LaTeX 를 기대하므로 되돌린다.

정합성 기준 = **왕복**: ``latex_to_hwpeq(hwpeq_to_latex(s))`` 가 원본 ``s`` 와 같아야 한다.
(`scripts/roundtrip_eq.py` 가 실데이터 전수로 측정)
"""
from __future__ import annotations
import re
from .latex_to_hwpeq import LaTeXToHWPConverter as _Conv

# ---------------------------------------------------------------- 역매핑 구축
def _build_reverse() -> dict[str, str]:
    """SYMBOL/GREEK/FUNC/ACCENT 맵을 뒤집는다. 다대일(\\le,\\leq→LEQ)은 정식 이름 우선."""
    prefer = {
        "LEQ": r"\leq", "GEQ": r"\geq", "neq": r"\neq", "VEE": r"\vee",
        "WEDGE": r"\wedge", "LNOT": r"\neg", "∽": r"\sim",
        '"∅"': r"\varnothing", "TIMES": r"\times",
    }
    rev: dict[str, str] = {}
    for mp in (_Conv.SYMBOL_MAP, _Conv.GREEK_MAP,
               _Conv.FUNC_MAP, _Conv.ACCENT_MAP):
        for tex, hwp in mp.items():
            h = str(hwp).strip()
            if not h:
                continue
            if h in prefer:
                rev[h] = prefer[h]
                continue
            # 이미 있으면 더 긴(명시적) LaTeX 이름 채택
            if h not in rev or len(tex) > len(rev[h]):
                rev[h] = tex
    return rev

_REV = _build_reverse()
# HWP 가 쓰지만 우리 정방향 변환기는 안 내보내는 고유 키워드 (완료본에 실제로 등장)
_REV.update({
    "EMPTYSET": r"\varnothing", "UNION": r"\bigcup", "INTER": r"\bigcap",
    "PLUS": "+", "MINUS": "-", "DEG": r"^\circ", "LIM": r"\lim",
    "INF": r"\infty", "PROD": r"\prod", "SUM": r"\sum", "INT": r"\int",
    "NOT": r"\neg", "AND": r"\wedge", "OR": r"\vee", "CIRC": r"\circ",
    "PRIME": "'", "DOTSAXIS": r"\cdots", "DOTSLOW": r"\ldots",
    "LNOT": r"\neg", "OWNS": r"\ni", "NOTIN": r"\notin",
    # 집합 연산: SYMBOL_MAP 은 SMALLUNION/SMALLINTER 만 내보내지만 HWP 원본은 CUP/CAP 도 쓴다
    "CUP": r"\cup", "CAP": r"\cap",
})
# ⚠️ VERT 도 제외 — 정방향이 ``vert`` 를 그대로 두므로 ``|`` 로 되돌리면 왕복이 어긋난다.
# ⚠️ PARALLEL·SQUARE·TRIANGLE 은 넣지 말 것 — 정방향이 유니코드 리터럴("⫽"·"□")로 내보내
#    왕복이 어긋난다(실측 회귀 96.0%→95.6%). 리터럴이 의도된 표기다.
# 접두 결합 분리용(HWP 는 ``RMABC`` = ``rm ABC``, ``ita`` = ``it a`` 로 토큰화)
_GLUE_PREFIX = ("RM", "IT", "SUBSET", "SUPSET", "EMPTYSET", "TIMES", "LEQ",
                "GEQ", "NEQ", "SMALLINTER", "SMALLUNION", "IN", "CDOT",
                "CUP", "CAP")   # OVER·SQRT 는 구조 키워드라 여기 넣으면 오분해된다
# 구조 키워드는 별도 처리하므로 단순치환에서 제외
_STRUCT = {"over", "sqrt", "rm", "it", "left", "right", "matrix", "pmatrix",
           "bmatrix", "vmatrix", "cases", "pile", "eqalign", "bar", "hat",
           "vec", "tilde", "dot", "ddot", "under", "from", "to", "root",
           "acute", "grave", "check", "breve", "arch"}
_ACCENTS = {"bar": r"\overline", "hat": r"\hat", "vec": r"\vec",
            "tilde": r"\tilde", "dot": r"\dot", "ddot": r"\ddot",
            "acute": r"\acute", "grave": r"\grave", "check": r"\check",
            "breve": r"\breve", "arch": r"\overarc"}
_MATRIX = {"matrix": "matrix", "pmatrix": "pmatrix", "bmatrix": "bmatrix",
           "vmatrix": "vmatrix"}

_TOKEN_RE = re.compile(r"""
    (?P<space>\s+)
  | (?P<lit>"[^"]*")
  | (?P<word>[A-Za-z][A-Za-z0-9]*)
  | (?P<num>\d+(?:\.\d+)?)
  | (?P<brace>[{}])
  | (?P<script>[\^_])
  | (?P<tilde>~)
  | (?P<tick>`)
  | (?P<sep>[#&])
  | (?P<other>.)
""", re.X)


def _tokens(s: str):
    for m in _TOKEN_RE.finditer(s):
        kind = m.lastgroup
        if kind == "space":
            continue
        yield kind, m.group()


class _P:
    def __init__(self, toks):
        self.t = list(toks)
        self.i = 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def next(self):
        v = self.peek()
        self.i += 1
        return v

    # --- 그룹: {...} 또는 단일 원자 ---
    def group(self) -> str:
        k, v = self.peek()
        if k == "brace" and v == "{":
            self.next()
            out = self.seq(stop="}")
            if self.peek()[1] == "}":
                self.next()
            return out
        return self.atom()

    def atom(self) -> str:
        k, v = self.next()
        if k is None:
            return ""
        if k == "word":
            low = v.lower()
            if low in _ACCENTS:
                return f"{_ACCENTS[low]}{{{self.group()}}}"
            if low == "sqrt":
                return f"\\sqrt{{{self.group()}}}"
            if low == "root":                      # root {n} of {x}
                n = self.group()
                if self.peek()[1] and self.peek()[1].lower() == "of":
                    self.next()
                return f"\\sqrt[{n}]{{{self.group()}}}"
            if low in _MATRIX:
                return self._matrix(low)
            if low in ("cases", "pile", "eqalign"):
                return self._matrix("cases")
            if low in ("rm", "it"):
                cmd = r"\mathrm" if low == "rm" else r"\mathit"
                return f"{cmd}{{{self.group()}}}"
            if low in ("left", "right"):
                d = self.next()[1] or ""
                if d in ("."):
                    d = "."
                pre = "\\left" if low == "left" else "\\right"
                if d in ("{", "}"):
                    d = "\\" + d
                return f"{pre}{d} "
            if low in ("from", "to"):               # 합/적분 상하한
                return ("_" if low == "from" else "^") + f"{{{self.group()}}}"
            if v in _REV:
                return _REV[v] + " "
            if low in _REV:
                return _REV[low] + " "
            up = v.upper()
            if up in _REV:
                return _REV[up] + " "
            # 결합 토큰: 알려진 키워드 접두를 떼고 나머지를 이어붙인다(RMABC → rm ABC)
            for pre in sorted(_GLUE_PREFIX, key=len, reverse=True):
                if up.startswith(pre) and len(v) > len(pre):
                    rest = v[len(pre):]
                    low2 = pre.lower()
                    if low2 in ("rm", "it"):
                        cmd = r"\mathrm" if low2 == "rm" else r"\mathit"
                        return f"{cmd}{{{rest}}}"
                    head = _REV.get(pre) or _REV.get(pre.lower()) or ""
                    if head:
                        return f"{head} {rest}"
            return v
        if k == "lit":
            inner = v[1:-1]
            return f"\\text{{{inner}}}" if inner else ""
        if k == "script":
            return v + f"{{{self.group()}}}"
        if k == "tilde":
            return "~"
        if k == "tick":
            return "\\,"
        if k == "num":
            return v
        if k == "brace":
            return ""
        return v

    def _matrix(self, env: str) -> str:
        k, v = self.peek()
        body = self.group() if (k == "brace" and v == "{") else self.atom()
        rows = [r.strip() for r in body.split("#")]
        rows = [" & ".join(c.strip() for c in r.split("&")) for r in rows]
        inner = " \\\\ ".join(r for r in rows)
        return f"\\begin{{{env}}} {inner} \\end{{{env}}}"

    def seq(self, stop: str | None = None) -> str:
        parts: list[str] = []
        while True:
            k, v = self.peek()
            if k is None or (stop and v == stop and k == "brace"):
                break
            if k == "word" and v.lower() == "over":
                self.next()
                num = parts.pop() if parts else ""
                den = self.group()
                parts.append(f"\\frac{{{num.strip()}}}{{{den.strip()}}}")
                continue
            if k == "sep":                     # 행렬 구분자는 상위에서 처리
                self.next()
                parts.append(v)
                continue
            if k == "brace" and v == "{":      # 그룹은 통째로 — over 의 피연산자가 된다
                parts.append(self.group())
                continue
            parts.append(self.atom())
        return "".join(parts)


def hwpeq_to_latex(script: str) -> str:
    """HWP 수식 스크립트를 LaTeX 로 되돌린다."""
    if not script or not script.strip():
        return ""
    s = script.replace("​", "")
    out = _P(_tokens(s)).seq()
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out.strip()
