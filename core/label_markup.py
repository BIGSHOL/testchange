# -*- coding: utf-8 -*-
"""도형 라벨의 **수학 조판** — 문자는 이탤릭, 숫자·기호는 정자체, `°` 는 위첨자.

## 왜 필요한가 (RPM 1:1 대조 2026-08-28)

종전에는 라벨을 `escape(text)` 로 `<text>` **한 덩어리**에 넣고 통째로 이탤릭을
걸었다.  RPM 원본을 실측해 보니 조판 규칙이 다르다:

    "125ù"    글꼴 EHsang-**Plain**    (숫자는 정자체)
    "3x"      글꼴 EHsang-**Italic**   (문자만 이탤릭)
    "ù+5ù"    글꼴 EHsang-**Plain**    (기호·숫자는 정자체)

즉 **`125°` 가 기울어 있으면 틀린 것**이다.  그리고 `°` 는 본문 크기가 아니라
**위첨자**로 작게 올라간다.  한 덩어리 `<text>` 로는 둘 다 못 한다.

## 무엇을 받나

교과서 그림 라벨에 실제로 나오는 것만 받는다.  **모르는 것은 던진다** —
조용히 날 글자로 내보내면 지면에 `\\circ` 가 그대로 찍히고, 그 결함은 스스로
신고하지 않는다(이 저장소가 되풀이해 밟은 자리).

    글자·숫자      A  x  125
    도               °   ^\\circ
    사칙·비교        + - = < > ≤ ≥ × ÷ ± · : , . ( ) [ ] { } / |
    윗줄             \\overline{AB}      (선분)
    아래·위첨자      a_1   x^2   S_{ABC}
    이름난 기호      \\angle \\times \\div \\pm \\cdot \\pi \\theta \\alpha \\beta
                     \\gamma \\le \\ge \\neq \\parallel \\perp \\triangle \\square
                     \\circ \\prime \\sim \\cong
    수식 감싸개      `$...$` 는 벗겨 낸다 (내용은 위 규칙으로 조판)
    공백             `\\,` `\\;` `~` `\\ `

`\\frac` 같은 **쌓는 조판은 안 받는다** — 받는 척하고 한 줄로 펴면 뜻이 달라진다.
필요해지면 그때 제대로 만든다(지금 RPM 그림 라벨에는 안 나온다).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from xml.sax.saxutils import escape

__all__ = ["LabelMarkupError", "parse_label", "label_pieces_svg", "label_width_em"]


class LabelMarkupError(ValueError):
    """라벨에 우리가 조판할 수 없는 것이 들어 있다."""


@dataclass(frozen=True, slots=True)
class Piece:
    """한 조각 — 같은 서식으로 이어 그릴 수 있는 최소 단위."""

    text: str
    italic: bool = False
    #: ``"sup"`` 위첨자 · ``"sub"`` 아래첨자 · ``None`` 본문 줄
    shift: str | None = None
    overline: bool = False


#: 명령 → 글자.  **정자체**로 나간다(기호는 기울이지 않는다).
_SYMBOLS = {
    "angle": "∠",
    "times": "×",
    "div": "÷",
    "pm": "±",
    "mp": "∓",
    "cdot": "·",
    "le": "≤",
    "leq": "≤",
    "ge": "≥",
    "geq": "≥",
    "neq": "≠",
    "ne": "≠",
    "parallel": "∥",
    "perp": "⊥",
    "triangle": "△",
    "square": "□",
    "circ": "°",
    "prime": "′",
    "sim": "∽",
    "cong": "≅",
    "sqrt": "√",
    "infty": "∞",
    "cdots": "⋯",
    "ldots": "…",
}
#: 그리스 문자는 **이탤릭**이다(교과 관행 — 변수처럼 쓴다).
_GREEK = {
    "alpha": "α",
    "beta": "β",
    "gamma": "γ",
    "delta": "δ",
    "theta": "θ",
    "pi": "π",
    "phi": "φ",
    "omega": "ω",
    "lambda": "λ",
    "mu": "μ",
}
#: 글자 그대로 나가는 것 — 빈칸 종류.
_SPACES = {",": " ", ";": " ", " ": " "}
#: 정자체로 두는 낱글자(연산·구두점·괄호).  나머지 라틴 글자는 이탤릭이다.
# 🔴 **대문자는 점 이름이라 정자체다** (원장님 확정 2026-08-28).
#    종전에는 이 목록에 대문자가 없어서, 조판(MathJax)을 타는 라벨과 이 폴백이
#    **서로 다른 답**을 냈다 — `mathjaxLabel.toTex` 는 홑 대문자를 `\mathrm` 으로
#    돌리는데(RPM 실측: `A` 정자체 145/153 · `O` 29/37) 여기는 이탤릭이었다.
#    같은 규칙을 쓰는 자리가 둘이면 한쪽만 고쳐진다(CLAUDE.md 2026-08-18).
#
#    드러난 자리: `data-mj` 는 어포스트로피를 **못 싣는다**(속성 값 검사가 따옴표를
#    막는다). 그래서 프라임 붙은 점 이름(`A'`·`B'`·`G'`·`T'`)만 조판을 못 타고 이
#    폴백으로 떨어져 **혼자 기울어져 나갔다** — 원장님이 지면에서 찾으셨다
#    (2026-08-29 `2-2|도형의 닮음|15` 의 `B'`). 실측으로 폴백을 타는 라벨 중
#    이탤릭인 것은 그 넷(10자리)뿐이고 나머지는 전부 한글이라 애초에 정자체다.
#
# ⚠️ `$S$` 처럼 홑 대문자를 **변수로** 쓰는 탈출구는 조판 경로에만 있다(`toTex` 가
#    `$…$` 를 보고 규칙을 안 건다). 여기서는 `$` 를 벗기므로 그 구분이 없지만,
#    그런 라벨은 금지 문자가 없어 **늘 조판 경로로 간다** — 닿지 않는 자리다.
_ROMAN_CHARS = set("0123456789+-=<>()[]{}/|:,.'°±×÷∠≤"
                   "≥≠∥⊥△□′∽≅√"
                   "∞⋯…   −"
                   "ABCDEFGHIJKLMNOPQRSTUVWXYZ")
#: `\mathrm{...}` 처럼 통째로 정자체인 묶음.
_ROMAN_CMDS = {"mathrm", "mathbf", "text", "operatorname"}

_TOKEN = re.compile(
    r"\\([a-zA-Z]+)"      # 1: 명령
    r"|\\([,;\s])"        # 2: 빈칸
    r"|([_^])"            # 3: 첨자 표시
    r"|(\{)|(\})"         # 4,5: 묶음
    r"|(\s+)"             # 6: 빈칸
    r"|(.)",              # 7: 그 밖의 한 글자
    re.DOTALL,
)


def _emit(out: list[Piece], text: str, *, italic: bool, shift: str | None,
          overline: bool) -> None:
    if not text:
        return
    if out and out[-1].italic == italic and out[-1].shift == shift \
            and out[-1].overline == overline:
        out[-1] = Piece(out[-1].text + text, italic, shift, overline)
    else:
        out.append(Piece(text, italic, shift, overline))


def _romanize_word_runs(pieces: list[Piece]) -> list[Piece]:
    """**소문자가 둘 이상 이어지면 낱말이다** — 단위·함수 이름이라 정자체로 그린다.

    RPM 실측: `5 cm` 의 `cm` 은 `EHhabu-**Plain**`(정자체)이다. 수학 조판에서
    낱글자는 변수(이탤릭)이고 `cm`·`sin`·`log` 같은 낱말은 정자체다 — 이 규칙을
    안 넣으면 지면에 **기울어진 `cm`** 이 나간다(실측으로 그랬다).

    ⚠️ 대문자 이어짐(`ABC`)은 **점 이름**이라 그대로 둔다. RPM 도 그림마다 갈린다
    (`EHhabu` 는 정자체 · `EHsang` 은 이탤릭) — 갈리는 것은 못 맞추므로
    우리 관행(이탤릭)을 지킨다.
    """

    out: list[Piece] = []
    for piece in pieces:
        if not piece.italic or len(piece.text) < 2:
            out.append(piece)
            continue
        buffer = ""
        run = ""
        for ch in piece.text:
            if ch.islower() and ch.isascii():
                run += ch
                continue
            if len(run) >= 2:
                _emit(out, buffer, italic=True, shift=piece.shift,
                      overline=piece.overline)
                _emit(out, run, italic=False, shift=piece.shift,
                      overline=piece.overline)
                buffer = ""
            else:
                buffer += run
            run = ""
            buffer += ch
        if len(run) >= 2:
            _emit(out, buffer, italic=True, shift=piece.shift, overline=piece.overline)
            _emit(out, run, italic=False, shift=piece.shift, overline=piece.overline)
        else:
            _emit(out, buffer + run, italic=True, shift=piece.shift,
                  overline=piece.overline)
    return out


def parse_label(label: str) -> list[Piece]:
    """라벨 글을 조각으로 나눈다.  **모르는 명령은 던진다.**"""

    text = label.strip()
    # `$...$` 는 벗긴다 — 안쪽만 조판한다.  `$` 가 홀수면 뜻을 알 수 없다.
    if text.count("$") % 2 != 0:
        raise LabelMarkupError(f"라벨의 `$` 짝이 안 맞는다: {label!r}")
    text = text.replace("$", "")

    out: list[Piece] = []
    # (shift, overline, forced_roman) 을 쌓아 둔다.  묶음이 끝나면 되돌린다.
    stack: list[tuple[str | None, bool, bool]] = []
    shift: str | None = None
    overline = False
    forced_roman = False
    #: 다음 한 덩어리에만 걸리는 첨자 — `x^2` 는 `2` 한 글자에만 붙는다.
    pending: str | None = None
    #: 다음 묶음을 통째로 정자체/윗줄로 만드는 명령.
    pending_group: str | None = None
    #: 명령 바로 뒤의 빈칸은 **명령의 끝 표시**이지 빈칸이 아니다 (`\angle ABC`).
    ate_command = False

    for match in _TOKEN.finditer(text):
        command, space_cmd, script, open_b, close_b, ws, char = match.groups()
        was_command, ate_command = ate_command, command is not None

        if command is not None:
            if command == "overline":
                pending_group = "overline"
                continue
            if command in _ROMAN_CMDS:
                pending_group = "roman"
                continue
            if command in _SYMBOLS:
                # `°` 글리프는 이미 윗쪽에 그려진다 — `^\circ` 를 한 번 더 올리면
                # 너무 뜬다. RPM 도 같은 높이다(실측).
                sup = "deg" if command == "circ" else (pending or shift)
                _emit(out, _SYMBOLS[command], italic=False,
                      shift=sup, overline=overline)
                pending = None
                continue
            if command in _GREEK:
                _emit(out, _GREEK[command], italic=not forced_roman,
                      shift=pending or shift, overline=overline)
                pending = None
                continue
            raise LabelMarkupError(
                f"라벨에서 모르는 명령 `\\{command}` — 조용히 날 글자로 내보내지 않는다"
                f" (라벨: {label!r})")

        if space_cmd is not None:
            _emit(out, _SPACES.get(space_cmd, " "), italic=False,
                  shift=shift, overline=overline)
            continue

        if script is not None:
            pending = "sup" if script == "^" else "sub"
            continue

        if open_b is not None:
            stack.append((shift, overline, forced_roman))
            if pending_group == "overline":
                overline = True
            elif pending_group == "roman":
                forced_roman = True
            elif pending is not None:
                shift = pending
            pending_group = None
            pending = None
            continue

        if close_b is not None:
            if not stack:
                raise LabelMarkupError(f"라벨의 중괄호 짝이 안 맞는다: {label!r}")
            shift, overline, forced_roman = stack.pop()
            continue

        if ws is not None:
            if was_command:
                continue  # `\angle ABC` — 명령의 끝 표시다
            _emit(out, " ", italic=False, shift=shift, overline=overline)
            continue

        assert char is not None
        if char == "°":
            # 글로 쓴 `°` 도 명령 `\circ` 와 **같은 물건**이다 — 한쪽만 작게 그리면
            # 같은 지면에서 도 기호가 두 크기로 나온다.
            _emit(out, char, italic=False, shift="deg", overline=overline)
            pending = None
            continue
        italic = (not forced_roman) and (char not in _ROMAN_CHARS)
        _emit(out, char, italic=italic, shift=pending or shift, overline=overline)
        pending = None

    out = _romanize_word_runs(out)

    if stack:
        raise LabelMarkupError(f"라벨의 중괄호가 안 닫혔다: {label!r}")
    return out


#: 첨자는 본문의 몇 배로 그리나 (교과 조판 관행).
SCRIPT_RATIO = 0.72
#: 🔴 **도 기호는 글꼴이 주는 크기로 두면 안 된다** (RPM 실측 2026-08-28).
#:
#:      RPM          ° 잉크 높이 0.183em · 숫자 높이의 **0.28배** · 아래끝 0.564em
#:      Cambria Math ° 잉크 높이 0.290em · 숫자 높이의   0.42배  · 아래끝 0.390em
#:
#: 그냥 쓰면 **35% 크고 한참 낮게** 앉는다 — 원장님이 「각도 기호가 좀 다른데」라고
#: 하신 것이 이것이다. 그래서 크기를 줄이고 위로 올려 RPM 치수에 맞춘다.
#: (아래 두 값은 Cambria Math 기준으로 푼 것이다 — 글꼴을 바꾸면 다시 재라.)
DEG_RATIO = 0.63     # 0.183 ÷ 0.290
DEG_RISE = 0.318     # 0.564 − 0.63×0.390  (본문 크기에 대한 비율, 위로)
#: 첨자를 본문 크기의 몇 배만큼 올리고/내리나.
SUP_RISE = 0.42
SUB_DROP = 0.20
#: 연산 기호 앞뒤 여백 — RPM 은 `3x°+5°` 의 `+` 앞뒤를 띄운다.
BINARY_SPACE_EM = 0.16
_BINARY = set("+=<>±∓×÷≤≥≠∽≅")
#: 뺄셈은 하이픈이 아니라 **빼기 기호**로 그린다(RPM 도 그렇다).
_MINUS = "−"


#: Times New Roman 의 **실제 글자 폭**(em) — AFM 표준 값.
#:
#: 🔴 종전에는 「라틴은 전부 0.61em」 한 값으로 어림했다.  그러면 `3x°+5°` 가
#:    실제 **2.8em** 인데 **5.7em** 으로 나온다(두 배).  상자가 두 배 넓으면 그만큼
#:    라벨이 멀리 밀려난다 — RPM 실측 18.8% 자리에 우리는 34% 였다.
#:    **폭을 어림하는 쪽과 그리는 쪽이 이만큼 갈리면 자리는 절대 안 맞는다.**
_TIMES_EM: dict[str, float] = {
    **{ch: 0.500 for ch in "0123456789"},
    **{ch: 0.564 for ch in "+=<>±∓×÷−"},
    **{ch: 0.549 for ch in "≤≥≠√∽≅∼"},
    **{ch: 0.333 for ch in "()[]-′"},
    **{ch: 0.480 for ch in "{}"},
    **{ch: 0.250 for ch in ".,· "},
    **{ch: 0.278 for ch in ":;/"},
    "|": 0.200,
    "°": 0.400,
    "∠": 0.768,
    "△": 0.750,
    "□": 0.750,
    "∥": 0.500,
    "⊥": 0.658,
    "∞": 0.750,
    " ": 0.170,
    "A": 0.722, "B": 0.667, "C": 0.667, "D": 0.722, "E": 0.611, "F": 0.556,
    "G": 0.722, "H": 0.722, "I": 0.333, "J": 0.389, "K": 0.722, "L": 0.611,
    "M": 0.889, "N": 0.722, "O": 0.722, "P": 0.556, "Q": 0.722, "R": 0.667,
    "S": 0.556, "T": 0.611, "U": 0.722, "V": 0.722, "W": 0.944, "X": 0.722,
    "Y": 0.722, "Z": 0.611,
    "a": 0.444, "b": 0.500, "c": 0.444, "d": 0.500, "e": 0.444, "f": 0.333,
    "g": 0.500, "h": 0.500, "i": 0.278, "j": 0.278, "k": 0.500, "l": 0.278,
    "m": 0.778, "n": 0.500, "o": 0.500, "p": 0.500, "q": 0.500, "r": 0.333,
    "s": 0.389, "t": 0.278, "u": 0.500, "v": 0.500, "w": 0.722, "x": 0.500,
    "y": 0.500, "z": 0.444,
    "α": 0.631, "β": 0.549, "γ": 0.411, "δ": 0.494, "θ": 0.521, "π": 0.549,
    "φ": 0.603, "ω": 0.686, "λ": 0.549, "μ": 0.576,
}


def _char_em(ch: str) -> float:
    """한 글자의 폭(em) — Times 실측 표.  표에 없는 라틴은 0.5, 한글·한자는 1.0."""

    if ch in _TIMES_EM:
        return _TIMES_EM[ch]
    return 1.0 if ord(ch) > 0x2FF else 0.5


def _pieces_with_spacing(pieces: list[Piece]) -> list[Piece]:
    """이항 연산 앞뒤에 여백을 넣고, 하이픈을 빼기 기호로 바꾼다."""

    out: list[Piece] = []
    for piece in pieces:
        if piece.shift is not None or piece.italic:
            out.append(piece)
            continue
        text = ""
        for index, ch in enumerate(piece.text):
            if ch == "-":
                # 맨 앞의 `-` 는 부호다 — 여백을 넣지 않는다.
                lead = index == 0 and not out
                text += _MINUS if lead else f" {_MINUS} "
            elif ch in _BINARY:
                text += f" {ch} "
            else:
                text += ch
        out.append(Piece(text, piece.italic, piece.shift, piece.overline))
    return out


def label_width_em(label: str) -> float:
    """이 라벨의 폭(em) — 첨자는 작게 센다.  `_text_box` 가 쓴다."""

    total = 0.0
    for piece in _pieces_with_spacing(parse_label(label)):
        scale = (DEG_RATIO if piece.shift == "deg"
                 else SCRIPT_RATIO if piece.shift else 1.0)
        total += sum(_char_em(ch) for ch in piece.text) * scale
    return total


def label_pieces_svg(label: str, font_size: float,
                     italic_family: str | None = None) -> str:
    """라벨을 `<tspan>` 들로 조판한다.  `<text>` 안쪽에 넣을 문자열을 낸다.

    `italic_family` 를 주면 **이탤릭 조각에만** 그 글꼴을 건다.
    🔴 수식 글꼴(Cambria Math·HancomEQN)에는 **이탤릭 판이 없다** — 그대로 두면
    브라우저가 로만을 기울여 흉내 내고, 진짜 이탤릭 `x` 와 모양이 다르다
    (원장님 「x가 이탤릭체가 아니고」). 그래서 이탤릭은 짝이 되는 본문 글꼴
    (Cambria)에서 가져온다.
    """

    out: list[str] = []
    for piece in _pieces_with_spacing(parse_label(label)):
        attrs: list[str] = []
        if piece.italic:
            attrs.append('font-style="italic"')
            if italic_family:
                attrs.append(
                    f'font-family="{escape(italic_family, {chr(34): "&quot;"})}"')
        else:
            # 바깥 `<text>` 가 이탤릭일 수 있으므로 **정자체를 명시**한다.
            attrs.append('font-style="normal"')
        if piece.shift == "deg":
            attrs.append(f'font-size="{_fmt(font_size * DEG_RATIO)}"')
            attrs.append(f'dy="{_fmt(-font_size * DEG_RISE)}"')
        elif piece.shift == "sup":
            attrs.append(f'font-size="{_fmt(font_size * SCRIPT_RATIO)}"')
            attrs.append(f'dy="{_fmt(-font_size * SUP_RISE)}"')
        elif piece.shift == "sub":
            attrs.append(f'font-size="{_fmt(font_size * SCRIPT_RATIO)}"')
            attrs.append(f'dy="{_fmt(font_size * SUB_DROP)}"')
        if piece.overline:
            attrs.append('text-decoration="overline"')
        out.append(f'<tspan {" ".join(attrs)}>{escape(piece.text)}</tspan>')
        # 첨자 뒤에는 본문 줄로 되돌린다 — `dy` 는 **누적**된다.
        if piece.shift == "deg":
            out.append(f'<tspan dy="{_fmt(font_size * DEG_RISE)}"></tspan>')
        elif piece.shift == "sup":
            out.append(f'<tspan dy="{_fmt(font_size * SUP_RISE)}"></tspan>')
        elif piece.shift == "sub":
            out.append(f'<tspan dy="{_fmt(-font_size * SUB_DROP)}"></tspan>')
    return "".join(out)


def _fmt(value: float) -> str:
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"
