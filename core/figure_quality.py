# -*- coding: utf-8 -*-
"""Security and quality gate for SVG returned by a vision model.

The vision model is an untrusted producer.  This module therefore implements a
small, reference-free SVG profile instead of trying to remove a handful of
known-dangerous constructs.  A successful sanitization rebuilds the XML tree
using only allow-listed elements and attributes.

``sanitize_svg`` is the security boundary.  ``validate_svg_structure`` adds
cheap semantic checks, while ``assess_svg`` optionally runs the existing
pixel-based figure linter as the final quality gate.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
import unicodedata
import xml.etree.ElementTree as ET

__all__ = [
    "SvgAssessment",
    "SvgAssessmentResult",
    "SvgSecurityError",
    "assess_svg",
    "sanitize_svg",
    "validate_svg_structure",
]


SVG_NS = "http://www.w3.org/2000/svg"
XML_NS = "http://www.w3.org/XML/1998/namespace"

# Generous enough for detailed school-math figures, but small enough to make
# parser/memory abuse and pathological render times unattractive.
MAX_SVG_BYTES = 512 * 1024
MAX_ELEMENTS = 2_000
MAX_DEPTH = 32
MAX_ATTRIBUTES = 12_000
MAX_TEXT_CHARS = 20_000
MAX_ATTRIBUTE_CHARS = 2_048
MAX_PATH_CHARS = 100_000
MAX_PATH_TOKENS = 20_000
MAX_COORDINATE = 10_000_000.0
# Pixel lint deliberately renders at two pixels per SVG unit.  A huge or very
# thin viewBox therefore becomes a renderer/memory attack even when the XML is
# otherwise harmless.  Real exam figures in the regression corpus top out at
# 510 units, so this leaves comfortable headroom without permitting gigapixel
# rasters.
MAX_VIEWBOX_SIDE = 640.0
MAX_VIEWBOX_ASPECT = 20.0
MAX_PIXEL_LINT_ELEMENTS = 200
MAX_PIXEL_LINT_TEXTS = 40
MAX_STROKE_WIDTH = 256.0


class SvgSecurityError(ValueError):
    """Raised when SVG violates the safe, reference-free input profile."""


@dataclass(frozen=True)
class SvgAssessment:
    """Combined result of SVG sanitization and quality checks."""

    sanitized_svg: str | None
    issues: list[str]
    security_issues: list[str]
    accepted: bool


# A descriptive alias makes the result type easier to discover at call sites.
SvgAssessmentResult = SvgAssessment


_ALLOWED_TAGS = frozenset({
    "svg",
    "g",
    "circle",
    "ellipse",
    "line",
    "path",
    "polygon",
    "polyline",
    "rect",
    "text",
    "tspan",
    "title",
    "desc",
    "defs",
    "linearGradient",
    "radialGradient",
    "stop",
})
_BLOCKED_TAGS = frozenset({
    "script",
    "foreignobject",
    "image",
    "use",
    "style",
    "iframe",
    "object",
    "embed",
    "audio",
    "video",
    "a",
})

_PRESENTATION_ATTRS = frozenset({
    "fill",
    "fill-opacity",
    "fill-rule",
    "stroke",
    "stroke-opacity",
    "stroke-width",
    "stroke-linecap",
    "stroke-linejoin",
    "stroke-miterlimit",
    "stroke-dasharray",
    "stroke-dashoffset",
    "opacity",
    "paint-order",
    "vector-effect",
    "shape-rendering",
    "color",
    "font-family",
    "font-size",
    "font-style",
    "font-weight",
    "text-anchor",
    "dominant-baseline",
    "alignment-baseline",
    "letter-spacing",
    "word-spacing",
})
_COMMON_ATTRS = _PRESENTATION_ATTRS
_TEXT_ATTRS = frozenset({"x", "y", "dx", "dy", "rotate", "xml:space"})
_TAG_ATTRS = {
    "svg": frozenset({"viewBox", "preserveAspectRatio"}),
    "g": _COMMON_ATTRS,
    "circle": _COMMON_ATTRS | {"cx", "cy", "r"},
    "ellipse": _COMMON_ATTRS | {"cx", "cy", "rx", "ry"},
    "line": _COMMON_ATTRS | {"x1", "y1", "x2", "y2"},
    "path": _COMMON_ATTRS | {"d"},
    "polygon": _COMMON_ATTRS | {"points"},
    "polyline": _COMMON_ATTRS | {"points"},
    "rect": _COMMON_ATTRS | {"x", "y", "width", "height", "rx", "ry"},
    "text": _COMMON_ATTRS | _TEXT_ATTRS,
    "tspan": _COMMON_ATTRS | _TEXT_ATTRS,
    "title": frozenset(),
    "desc": frozenset(),
    "defs": frozenset(),
    "linearGradient": frozenset({"id", "x1", "y1", "x2", "y2", "gradientUnits"}),
    "radialGradient": frozenset({"id", "cx", "cy", "r", "fx", "fy", "gradientUnits"}),
    "stop": frozenset({"offset", "stop-color", "stop-opacity"}),
}
_GRADIENT_TAGS = frozenset({"linearGradient", "radialGradient"})
_PAINT_ATTRS = frozenset({"fill", "stroke"})
_LOCAL_REF_RE = re.compile(r"^url\(\s*#([A-Za-z][\w.:-]*)\s*\)$")
_ID_RE = re.compile(r"^[A-Za-z][\w.:-]*$")

_CONTAINER_CHILDREN = (_ALLOWED_TAGS - {"svg", "tspan", "stop"}
                       - _GRADIENT_TAGS)
_TEXT_CHILDREN = frozenset({"tspan"})
_DRAWABLE_TAGS = frozenset({
    "circle", "ellipse", "line", "path", "polygon", "polyline", "rect", "text"
})
_GEOMETRY_TAGS = _DRAWABLE_TAGS - {"text"}

_NUMBER_PATTERN = r"[+-]?(?:(?:\d+(?:\.\d*)?)|(?:\.\d+))(?:[eE][+-]?\d+)?"
_NUMBER_RE = re.compile(rf"^(?:{_NUMBER_PATTERN})$")
_NUMBER_FIND_RE = re.compile(_NUMBER_PATTERN)
_PATH_TOKEN_RE = re.compile(rf"[AaCcHhLlMmQqSsTtVvZz]|{_NUMBER_PATTERN}")
_PREDEFINED_ENTITY_RE = re.compile(r"&(amp|lt|gt|quot|apos);|&#(?:\d+|x[0-9A-Fa-f]+);")
_SCHEME_RE = re.compile(r"(?:^|[\s'\"(])(?:https?|ftp|file|data|javascript):", re.I)

_COLOR_NAMES = frozenset({
    "black", "white", "gray", "grey", "red", "green", "blue", "yellow",
    "orange", "purple", "brown", "pink", "navy", "teal", "maroon",
    "silver", "lime", "aqua", "fuchsia", "transparent",
})
_ENUM_VALUES = {
    "fill-rule": frozenset({"nonzero", "evenodd", "inherit"}),
    "stroke-linecap": frozenset({"butt", "round", "square", "inherit"}),
    "stroke-linejoin": frozenset({"miter", "miter-clip", "round", "bevel", "arcs", "inherit"}),
    "vector-effect": frozenset({"none", "non-scaling-stroke"}),
    "shape-rendering": frozenset({
        "auto", "optimizespeed", "crispedges", "geometricprecision"
    }),
    "font-style": frozenset({"normal", "italic", "oblique", "inherit"}),
    "text-anchor": frozenset({"start", "middle", "end", "inherit"}),
    "dominant-baseline": frozenset({
        "auto", "alphabetic", "middle", "central", "mathematical", "hanging",
        "text-after-edge", "text-before-edge", "inherit",
    }),
    "alignment-baseline": frozenset({
        "auto", "baseline", "before-edge", "text-before-edge", "middle",
        "central", "after-edge", "text-after-edge", "ideographic", "alphabetic",
        "hanging", "mathematical", "inherit",
    }),
}


def _local_tag(name: str) -> tuple[str, str | None]:
    if name.startswith("{"):
        namespace, _, local = name[1:].partition("}")
        return local, namespace
    return name, None


def _attribute_name(name: str) -> str:
    if name == f"{{{XML_NS}}}space":
        return "xml:space"
    if name.startswith("{"):
        namespace, _, local = name[1:].partition("}")
        if local.lower() == "href":
            raise SvgSecurityError("href/xlink references are not allowed")
        raise SvgSecurityError(f"attribute namespace is not allowed: {namespace}")
    if ":" in name:
        if name.lower().endswith(":href"):
            raise SvgSecurityError("href/xlink references are not allowed")
        raise SvgSecurityError(f"namespaced attribute is not allowed: {name}")
    return name


def _preflight(svg: str) -> None:
    if not isinstance(svg, str):
        raise SvgSecurityError("SVG input must be a string")
    try:
        size = len(svg.encode("utf-8", errors="strict"))
    except UnicodeEncodeError as exc:
        raise SvgSecurityError("SVG contains an invalid Unicode surrogate") from exc
    if size == 0:
        raise SvgSecurityError("SVG input is empty")
    if size > MAX_SVG_BYTES:
        raise SvgSecurityError(f"SVG exceeds the {MAX_SVG_BYTES}-byte limit")
    if "\x00" in svg:
        raise SvgSecurityError("NUL bytes are not allowed in SVG")
    if re.search(r"<!\s*DOCTYPE\b", svg, re.I):
        raise SvgSecurityError("DOCTYPE declarations are not allowed")
    if re.search(r"<!\s*ENTITY\b", svg, re.I):
        raise SvgSecurityError("ENTITY declarations are not allowed")
    for _ref in re.finditer(r"\burl\s*\(([^)]*)\)", svg, re.I):
        # 사용자 승인(2026-08-13)은 **구 음영 같은 특정 경우 한정**이다. 문서 안
        # 그라데이션을 가리키는 url(#id) 만 통과시키고 나머지(외부 URL·pattern·
        # filter·clip-path 참조)는 종전대로 막는다.
        if not re.fullmatch(r"\s*#[A-Za-z][\w.:-]*\s*", _ref.group(1)):
            raise SvgSecurityError("only local url(#id) gradient references are allowed")

    # XML declarations are harmless; all other processing instructions are
    # unnecessary for a generated diagram and are rejected.
    without_decl = re.sub(r"^\s*<\?xml\s+[^?]*\?>", "", svg, count=1, flags=re.I)
    if "<?" in without_decl:
        raise SvgSecurityError("XML processing instructions are not allowed")

    # ElementTree accepts the five XML predefined entities and numeric
    # character references.  Reject any other reference even before parsing.
    stripped = _PREDEFINED_ENTITY_RE.sub("", svg)
    if re.search(r"&[A-Za-z_][A-Za-z0-9_.:-]*;", stripped):
        raise SvgSecurityError("custom entity references are not allowed")


def _parse(svg: str) -> ET.Element:
    _preflight(svg)
    try:
        root = ET.fromstring(svg)
    except (ET.ParseError, ValueError) as exc:
        raise SvgSecurityError(f"malformed SVG XML: {exc}") from exc
    return root


def _parse_number(value: str, *, label: str, minimum: float | None = None,
                  maximum: float = MAX_COORDINATE) -> float:
    value = value.strip()
    if not _NUMBER_RE.fullmatch(value):
        raise SvgSecurityError(f"{label} must be a finite plain number")
    number = float(value)
    if not math.isfinite(number):
        raise SvgSecurityError(f"{label} must be finite")
    if abs(number) > maximum:
        raise SvgSecurityError(f"{label} exceeds the allowed magnitude")
    if minimum is not None and number < minimum:
        raise SvgSecurityError(f"{label} must be at least {minimum:g}")
    return number


def _parse_length(value: str, *, label: str, minimum: float = 0) -> float:
    """Parse a safe SVG length.

    Geometry is normally expressed in viewBox units.  Percentages are retained
    solely because ``width="100%" height="100%"`` is a common, safe background
    rectangle idiom.  Physical/CSS units are deliberately outside the profile.
    """

    stripped = value.strip()
    if stripped.endswith("%"):
        return _parse_number(
            stripped[:-1], label=label, minimum=minimum, maximum=10_000
        )
    return _parse_number(stripped, label=label, minimum=minimum)


def _number_list(value: str, *, label: str, min_count: int = 1,
                 even: bool = False) -> list[float]:
    if len(value) > MAX_ATTRIBUTE_CHARS:
        raise SvgSecurityError(f"{label} is too long")
    pieces = re.split(r"[\s,]+", value.strip()) if value.strip() else []
    if len(pieces) < min_count or (even and len(pieces) % 2):
        qualifier = "an even number of" if even else f"at least {min_count}"
        raise SvgSecurityError(f"{label} must contain {qualifier} coordinates")
    return [_parse_number(piece, label=label) for piece in pieces]


def _validate_viewbox(value: str | None) -> tuple[float, float]:
    if value is None:
        raise SvgSecurityError("root <svg> requires viewBox")
    values = _number_list(value, label="viewBox", min_count=4)
    if len(values) != 4:
        raise SvgSecurityError("viewBox must contain exactly four numbers")
    x, y, width, height = values
    if x != 0.0 or y != 0.0:
        raise SvgSecurityError("viewBox must start at 0 0")
    if width <= 0.0 or height <= 0.0:
        raise SvgSecurityError("viewBox width and height must be positive")
    if width > MAX_VIEWBOX_SIDE or height > MAX_VIEWBOX_SIDE:
        raise SvgSecurityError("viewBox dimensions exceed the allowed limit")
    aspect = max(width / height, height / width)
    if aspect > MAX_VIEWBOX_ASPECT:
        raise SvgSecurityError(
            f"viewBox aspect ratio exceeds {MAX_VIEWBOX_ASPECT:g}:1")
    return width, height


def _validate_color(value: str, label: str) -> None:
    raw = value.strip()
    lower = raw.lower()
    if lower == "none" or lower in _COLOR_NAMES:
        return
    if re.fullmatch(r"#[0-9A-Fa-f]{3,4}|#[0-9A-Fa-f]{6}|#[0-9A-Fa-f]{8}", raw):
        return
    raise SvgSecurityError(f"unsupported {label} color: {raw!r}")


def _hex_color_is_fully_transparent(value: str) -> bool:
    """Return whether CSS hex color *value* carries an all-zero alpha."""

    raw = value.strip().lower()
    return bool(
        (re.fullmatch(r"#[0-9a-f]{4}", raw) and raw[-1] == "0")
        or (re.fullmatch(r"#[0-9a-f]{8}", raw) and raw[-2:] == "00")
    )


def _color_is_white(value: str) -> bool:
    """Recognize opaque or alpha-bearing CSS hex spellings of white."""

    raw = value.strip().lower()
    if raw in {"white", "rgb(255,255,255)"}:
        return True
    match = re.fullmatch(r"#([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})", raw)
    if not match:
        return False
    digits = match.group(1)
    rgb = digits[:3] if len(digits) in {3, 4} else digits[:6]
    return all(char == "f" for char in rgb)


def _validate_path(value: str) -> None:
    if not value.strip():
        raise SvgSecurityError("path d must not be empty")
    if len(value) > MAX_PATH_CHARS:
        raise SvgSecurityError("path data is too long")

    tokens: list[str] = []
    end = 0
    for match in _PATH_TOKEN_RE.finditer(value):
        gap = value[end:match.start()]
        if gap.strip(" \t\r\n,"):
            raise SvgSecurityError("path data contains unsupported syntax")
        tokens.append(match.group(0))
        end = match.end()
        if len(tokens) > MAX_PATH_TOKENS:
            raise SvgSecurityError("path data has too many tokens")
    if value[end:].strip(" \t\r\n,") or not tokens:
        raise SvgSecurityError("path data contains unsupported syntax")
    if tokens[0] not in {"M", "m"}:
        raise SvgSecurityError("path data must begin with M or m")

    arity = {
        "M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4,
        "Q": 4, "T": 2, "A": 7, "Z": 0,
    }
    index = 0
    saw_draw = False
    while index < len(tokens):
        command = tokens[index]
        if not command.isalpha():
            raise SvgSecurityError("path coordinates require a preceding command")
        index += 1
        upper = command.upper()
        needed = arity[upper]
        if needed == 0:
            continue
        start = index
        while index < len(tokens) and not tokens[index].isalpha():
            index += 1
        args = tokens[start:index]
        if len(args) < needed or len(args) % needed:
            raise SvgSecurityError(f"path command {command} has invalid argument count")
        numbers = [_parse_number(arg, label="path coordinate") for arg in args]
        for offset in range(0, len(numbers), needed):
            group = numbers[offset:offset + needed]
            if upper == "A":
                if group[0] < 0 or group[1] < 0:
                    raise SvgSecurityError("path arc radii must be non-negative")
                if group[3] not in (0.0, 1.0) or group[4] not in (0.0, 1.0):
                    raise SvgSecurityError("path arc flags must be 0 or 1")
        if upper != "M" or len(numbers) > 2:
            saw_draw = True
    if not saw_draw:
        raise SvgSecurityError("path data contains no drawing segment")


def _validate_font_family(value: str) -> None:
    if not value.strip() or len(value) > 256:
        raise SvgSecurityError("font-family is empty or too long")
    if any(char in value for char in ";{}()<>\\"):
        raise SvgSecurityError("font-family contains unsafe syntax")
    if any(unicodedata.category(char) == "Cc" for char in value):
        raise SvgSecurityError("font-family contains control characters")


def _validate_attr(tag: str, name: str, value: str) -> None:
    if len(value) > (MAX_PATH_CHARS if name == "d" else MAX_ATTRIBUTE_CHARS):
        raise SvgSecurityError(f"attribute {name} is too long")
    lowered_name = name.lower()
    lowered_value = value.lower()
    if lowered_name.startswith("on"):
        raise SvgSecurityError(f"event attribute is not allowed: {name}")
    if lowered_name in {"href", "xlink:href", "style", "class", "src"}:
        raise SvgSecurityError(f"attribute is not allowed: {name}")
    if "url(" in lowered_value:
        if name not in _PAINT_ATTRS or not _LOCAL_REF_RE.match(value.strip()):
            raise SvgSecurityError(f"external/reference value is not allowed in {name}")
    elif _SCHEME_RE.search(value) or value.lstrip().startswith("//"):
        raise SvgSecurityError(f"external/reference value is not allowed in {name}")
    if name not in _TAG_ATTRS[tag]:
        raise SvgSecurityError(f"attribute {name!r} is not allowed on <{tag}>")

    if name == "id":
        if not _ID_RE.match(value.strip()):
            raise SvgSecurityError("invalid id")
    elif name == "gradientUnits":
        if value.strip() not in {"objectBoundingBox", "userSpaceOnUse"}:
            raise SvgSecurityError("invalid gradientUnits")
    elif name == "offset":
        v = value.strip()
        _parse_number(v[:-1] if v.endswith("%") else v, label="offset")
    elif name == "stop-color":
        _validate_color(value.strip(), name)
    elif name == "stop-opacity":
        _parse_number(value, label=name, minimum=0.0, maximum=1.0)
    elif name == "viewBox":
        _validate_viewbox(value)
    elif name == "preserveAspectRatio":
        if not re.fullmatch(
            r"(?:none|x(?:Min|Mid|Max)Y(?:Min|Mid|Max)(?:\s+(?:meet|slice))?)", value.strip()
        ):
            raise SvgSecurityError("invalid preserveAspectRatio")
    elif name == "d":
        _validate_path(value)
    elif name == "points":
        minimum = 6 if tag == "polygon" else 4
        coords = _number_list(value, label=f"{tag} points", min_count=minimum, even=True)
        if len(coords) < minimum:
            raise SvgSecurityError(f"{tag} has too few points")
    elif name in {"fill", "stroke", "color"}:
        # 로컬 그라데이션 참조는 색이 아니라 참조다 — 존재 여부는 sanitize_svg 가
        # 문서 전체를 보고 확인한다(여기선 형식만).
        if not (name in _PAINT_ATTRS and _LOCAL_REF_RE.match(value.strip())):
            _validate_color(value, name)
    elif name in {"fill-opacity", "stroke-opacity", "opacity"}:
        _parse_number(value, label=name, minimum=0, maximum=1)
    elif name == "stroke-width":
        _parse_number(value, label=name, minimum=0, maximum=MAX_STROKE_WIDTH)
    elif name == "stroke-miterlimit":
        _parse_number(value, label=name, minimum=1, maximum=1_000)
    elif name in {"stroke-dashoffset", "letter-spacing", "word-spacing"}:
        if value.strip() != "normal":
            _parse_number(value, label=name)
    elif name == "stroke-dasharray":
        if value.strip().lower() != "none":
            values = _number_list(value, label=name, min_count=1)
            if any(number < 0 for number in values) or not any(number > 0 for number in values):
                raise SvgSecurityError("stroke-dasharray must contain non-negative lengths")
    elif name == "font-size":
        _parse_number(value, label=name, minimum=0.1, maximum=512)
    elif name == "font-weight":
        if value.strip().lower() not in {"normal", "bold", "bolder", "lighter", "inherit"}:
            weight = _parse_number(value, label=name, minimum=1, maximum=1_000)
            if weight % 100 != 0:
                raise SvgSecurityError("numeric font-weight must be a multiple of 100")
    elif name == "font-family":
        _validate_font_family(value)
    elif name in _ENUM_VALUES:
        if value.strip().lower() not in _ENUM_VALUES[name]:
            raise SvgSecurityError(f"unsupported value for {name}: {value!r}")
    elif name == "paint-order":
        pieces = value.strip().lower().split()
        if value.strip().lower() != "normal" and (
            not pieces or len(pieces) > 3 or len(set(pieces)) != len(pieces)
            or any(piece not in {"fill", "stroke", "markers"} for piece in pieces)
        ):
            raise SvgSecurityError("invalid paint-order")
    elif name == "xml:space":
        if value not in {"default", "preserve"}:
            raise SvgSecurityError("xml:space must be default or preserve")
    elif name in {"x", "y", "dx", "dy", "rotate"} and tag in {"text", "tspan"}:
        _number_list(value, label=name, min_count=1)
    elif name in {"r", "rx", "ry", "width", "height"}:
        number = _parse_length(value, label=name, minimum=0)
        if name in {"r", "width", "height"} and number == 0:
            raise SvgSecurityError(f"{name} must be positive")
    else:
        # Remaining geometry coordinates (x/y/cx/.../x1/y1/...) are single
        # plain finite numbers.
        _parse_number(value, label=name)


def _safe_text(value: str | None, *, context: str) -> str | None:
    if value is None:
        return None
    for char in value:
        if unicodedata.category(char) == "Cc" and char not in "\t\r\n":
            raise SvgSecurityError(f"control character in {context}")
    return value


def _check_limits_and_shape(root: ET.Element) -> None:
    elements = 0
    attributes = 0
    text_chars = 0
    stack: list[tuple[ET.Element, int, str | None]] = [(root, 1, None)]
    while stack:
        element, depth, parent_tag = stack.pop()
        elements += 1
        attributes += len(element.attrib)
        if elements > MAX_ELEMENTS:
            raise SvgSecurityError(f"SVG exceeds the {MAX_ELEMENTS}-element limit")
        if attributes > MAX_ATTRIBUTES:
            raise SvgSecurityError(f"SVG exceeds the {MAX_ATTRIBUTES}-attribute limit")
        if depth > MAX_DEPTH:
            raise SvgSecurityError(f"SVG exceeds the depth limit of {MAX_DEPTH}")

        tag, namespace = _local_tag(element.tag)
        if namespace not in {None, SVG_NS}:
            raise SvgSecurityError(f"element namespace is not allowed: {namespace}")
        if tag.lower() in _BLOCKED_TAGS:
            raise SvgSecurityError(f"blocked SVG element: <{tag}>")
        if tag not in _ALLOWED_TAGS:
            raise SvgSecurityError(f"unsupported SVG element: <{tag}>")
        if parent_tag is None and tag != "svg":
            raise SvgSecurityError("root element must be <svg>")
        if parent_tag == "svg" and tag == "svg":
            raise SvgSecurityError("nested <svg> elements are not allowed")
        if tag == "defs" and parent_tag != "svg":
            raise SvgSecurityError("<defs> may only appear directly under <svg>")
        if tag in _GRADIENT_TAGS and parent_tag != "defs":
            raise SvgSecurityError(f"<{tag}> may only appear inside <defs>")
        if tag == "stop" and parent_tag not in _GRADIENT_TAGS:
            raise SvgSecurityError("<stop> may only appear inside a gradient")
        if parent_tag == "defs" and tag not in _GRADIENT_TAGS:
            raise SvgSecurityError(f"<defs> may only contain gradients, not <{tag}>")
        if parent_tag in _GRADIENT_TAGS and tag != "stop":
            raise SvgSecurityError(f"gradients may only contain <stop>, not <{tag}>")
        if parent_tag in {"text", "tspan"} and tag not in _TEXT_CHILDREN:
            raise SvgSecurityError(f"<{parent_tag}> may only contain <tspan> elements")
        if parent_tag not in {None, "svg", "g", "text", "tspan", "defs"} | _GRADIENT_TAGS:
            raise SvgSecurityError(f"<{parent_tag}> cannot contain child elements")
        if parent_tag in {"svg", "g"} and tag not in _CONTAINER_CHILDREN:
            raise SvgSecurityError(f"<{parent_tag}> cannot contain <{tag}>")
        if tag in {"title", "desc"} and list(element):
            raise SvgSecurityError(f"<{tag}> cannot contain child elements")

        own_text = _safe_text(element.text, context=f"<{tag}> text") or ""
        tail_text = _safe_text(element.tail, context=f"<{tag}> tail") or ""
        text_chars += len(own_text) + len(tail_text)
        if text_chars > MAX_TEXT_CHARS:
            raise SvgSecurityError(f"SVG exceeds the {MAX_TEXT_CHARS}-character text limit")
        if tag not in {"text", "tspan", "title", "desc"} and own_text.strip():
            raise SvgSecurityError(f"text content is not allowed inside <{tag}>")
        if parent_tag not in {"text", "tspan"} and tail_text.strip():
            raise SvgSecurityError(f"mixed text content is not allowed after <{tag}>")

        for child in reversed(list(element)):
            stack.append((child, depth + 1, tag))


def _format_number(number: float) -> str:
    if number == 0:
        return "0"
    return format(number, ".12g")


def sanitize_svg(svg: str) -> str:
    """Return a safe, reference-free SVG, or raise :class:`SvgSecurityError`.

    The returned document is rebuilt from parsed nodes.  Root ``width`` and
    ``height`` are intentionally discarded so consumers size it from the
    mandatory ``viewBox``.
    """

    root = _parse(svg)
    _check_limits_and_shape(root)
    root_tag, root_namespace = _local_tag(root.tag)
    if root_tag != "svg" or root_namespace not in {None, SVG_NS}:
        raise SvgSecurityError("root element must be an SVG <svg>")

    # ElementTree consumes xmlns declarations rather than exposing them as
    # regular attributes.  Root width/height are deliberately ignored.
    source_viewbox = root.attrib.get("viewBox")
    width, height = _validate_viewbox(source_viewbox)

    def rebuild(source: ET.Element, *, is_root: bool = False) -> ET.Element:
        tag, _ = _local_tag(source.tag)
        clean_attrs: dict[str, str] = {}
        for raw_name, raw_value in source.attrib.items():
            name = _attribute_name(raw_name)
            if is_root and name in {"width", "height", "version", "xmlns"}:
                continue
            _validate_attr(tag, name, raw_value)
            clean_attrs[name] = raw_value.strip() if name != "font-family" else raw_value
        if is_root:
            clean_attrs["viewBox"] = (
                f"0 0 {_format_number(width)} {_format_number(height)}"
            )
            clean_attrs["xmlns"] = SVG_NS

        clean = ET.Element(tag, clean_attrs)
        clean.text = _safe_text(source.text, context=f"<{tag}> text")
        for source_child in source:
            child = rebuild(source_child)
            child.tail = _safe_text(source_child.tail, context=f"<{tag}> child tail")
            clean.append(child)
        return clean

    clean_root = rebuild(root, is_root=True)
    defined = {e.get("id") for e in clean_root.iter()
               if _local_tag(e.tag)[0] in _GRADIENT_TAGS and e.get("id")}
    for element in clean_root.iter():
        for attr in _PAINT_ATTRS:
            ref = _LOCAL_REF_RE.match((element.get(attr) or "").strip())
            if ref and ref.group(1) not in defined:
                raise SvgSecurityError(
                    f"paint references an undefined gradient: {ref.group(1)}")
    sanitized = ET.tostring(clean_root, encoding="unicode", short_empty_elements=True)
    if len(sanitized.encode("utf-8")) > MAX_SVG_BYTES:
        raise SvgSecurityError("sanitized SVG exceeds the output size limit")
    return sanitized


def _effective_style(element: ET.Element, inherited: dict[str, str]) -> dict[str, str]:
    style = dict(inherited)
    # SVG ``opacity`` is not merely an inherited presentation value: opacity
    # on every ancestor group composites multiplicatively with descendants.
    # Keep that product separately so a child cannot undo ``<g opacity="0">``
    # by declaring opacity="1".
    try:
        composite_opacity = float(inherited.get("__composite_opacity", "1"))
    except ValueError:
        composite_opacity = 0.0
    for raw_name, value in element.attrib.items():
        try:
            name = _attribute_name(raw_name)
        except SvgSecurityError:
            continue
        if name == "opacity":
            try:
                composite_opacity *= float(value)
            except ValueError:
                composite_opacity = 0.0
        elif name in {"fill", "stroke", "stroke-width", "fill-opacity", "stroke-opacity"}:
            normalized = value.strip().lower()
            if normalized != "inherit":
                style[name] = normalized
    style["__composite_opacity"] = str(composite_opacity)
    return style


def _looks_like_background_rect(element: ET.Element, view_width: float,
                                view_height: float) -> bool:
    if _local_tag(element.tag)[0] != "rect":
        return False
    def resolve(value: str, extent: float) -> float:
        value = value.strip()
        if value.endswith("%"):
            return float(value[:-1]) * extent / 100.0
        return float(value)

    try:
        x = resolve(element.attrib.get("x", "0"), view_width)
        y = resolve(element.attrib.get("y", "0"), view_height)
        width = resolve(element.attrib.get("width", "nan"), view_width)
        height = resolve(element.attrib.get("height", "nan"), view_height)
    except ValueError:
        return False
    fill = element.attrib.get("fill", "black").strip().lower()
    return (
        x == 0 and y == 0 and width == view_width and height == view_height
        and fill in {"white", "#fff", "#ffffff"}
    )


def _is_likely_visible(tag: str, style: dict[str, str]) -> bool:
    try:
        if float(style.get("__composite_opacity", "1")) <= 0:
            return False
    except ValueError:
        return False
    fill = style.get("fill", "black")
    stroke = style.get("stroke", "none")
    try:
        fill_alpha = float(style.get("fill-opacity", "1"))
        stroke_alpha = float(style.get("stroke-opacity", "1"))
        stroke_width = float(style.get("stroke-width", "1"))
    except ValueError:
        return False
    fill_transparent = fill in {"none", "transparent"} or _hex_color_is_fully_transparent(fill)
    stroke_transparent = (
        stroke in {"none", "transparent"} or _hex_color_is_fully_transparent(stroke)
    )
    has_fill = (
        tag not in {"line", "polyline"}
        and not fill_transparent and not _color_is_white(fill)
        and fill_alpha > 0
    )
    has_stroke = (
        not stroke_transparent and not _color_is_white(stroke)
        and stroke_alpha > 0 and stroke_width > 0
    )
    return has_fill or has_stroke


def _path_has_extent(value: str) -> bool:
    """Return whether validated path data contains a non-degenerate draw.

    Merely containing an ``L``/``C`` token is insufficient: ``M 1 1 L 1 1``
    is a common blank-SVG gate bypass.  This small interpreter tracks command
    endpoints (and curve controls) for both absolute and relative commands.
    """

    _validate_path(value)
    tokens = _PATH_TOKEN_RE.findall(value)
    arity = {
        "M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4,
        "Q": 4, "T": 2, "A": 7, "Z": 0,
    }
    current = (0.0, 0.0)
    subpath_start = current
    index = 0
    while index < len(tokens):
        command = tokens[index]
        index += 1
        upper = command.upper()
        relative = command.islower()
        if upper == "Z":
            if math.hypot(current[0] - subpath_start[0],
                          current[1] - subpath_start[1]) > 1.0e-12:
                return True
            current = subpath_start
            continue

        end = index
        while end < len(tokens) and not tokens[end].isalpha():
            end += 1
        numbers = [float(token) for token in tokens[index:end]]
        size = arity[upper]
        groups = [numbers[offset:offset + size]
                  for offset in range(0, len(numbers), size)]
        index = end
        for group_index, group in enumerate(groups):
            base_x, base_y = current

            def pair(x_value: float, y_value: float) -> tuple[float, float]:
                if relative:
                    return base_x + x_value, base_y + y_value
                return x_value, y_value

            if upper == "M":
                target = pair(group[0], group[1])
                if group_index == 0:
                    subpath_start = target
                elif math.hypot(target[0] - current[0],
                                target[1] - current[1]) > 1.0e-12:
                    return True
                current = target
            elif upper in {"L", "T"}:
                target = pair(group[0], group[1])
                if math.hypot(target[0] - current[0],
                              target[1] - current[1]) > 1.0e-12:
                    return True
                current = target
            elif upper == "H":
                target_x = base_x + group[0] if relative else group[0]
                if abs(target_x - current[0]) > 1.0e-12:
                    return True
                current = (target_x, current[1])
            elif upper == "V":
                target_y = base_y + group[0] if relative else group[0]
                if abs(target_y - current[1]) > 1.0e-12:
                    return True
                current = (current[0], target_y)
            elif upper in {"C", "S", "Q"}:
                points = [pair(group[offset], group[offset + 1])
                          for offset in range(0, len(group), 2)]
                if any(math.hypot(point[0] - current[0], point[1] - current[1])
                       > 1.0e-12 for point in points):
                    return True
                current = points[-1]
            elif upper == "A":
                target = pair(group[5], group[6])
                if math.hypot(target[0] - current[0],
                              target[1] - current[1]) > 1.0e-12:
                    return True
                current = target
    return False


def _has_geometric_extent(element: ET.Element, tag: str) -> bool:
    """Conservatively reject primitives that render no geometric extent."""

    try:
        if tag == "circle":
            return _parse_length(element.attrib.get("r", "0"), label="r") > 0
        if tag == "ellipse":
            return (
                _parse_length(element.attrib.get("rx", "0"), label="rx") > 0
                and _parse_length(element.attrib.get("ry", "0"), label="ry") > 0
            )
        if tag == "rect":
            return (
                _parse_length(element.attrib.get("width", "0"), label="width") > 0
                and _parse_length(element.attrib.get("height", "0"), label="height") > 0
            )
        if tag == "line":
            p = (float(element.attrib.get("x1", "0")), float(element.attrib.get("y1", "0")))
            q = (float(element.attrib.get("x2", "0")), float(element.attrib.get("y2", "0")))
            return p != q
        if tag in {"polygon", "polyline"}:
            values = _number_list(
                element.attrib.get("points", ""), label=f"{tag} points",
                min_count=6 if tag == "polygon" else 4, even=True,
            )
            points = list(zip(values[::2], values[1::2]))
            return len(set(points)) >= 2
        if tag == "path":
            return _path_has_extent(element.attrib.get("d", ""))
    except (SvgSecurityError, ValueError):
        return False
    return False


def _path_conservative_bounds(value: str) -> tuple[float, float, float, float] | None:
    """Return a conservative bbox for safe path data.

    Curve controls and generous arc-radius envelopes are included.  The box may
    be larger than the exact painted path, which is intentional: the only use
    is proving that an entire primitive is outside (or absurdly far from) the
    viewBox without false rejection of a curve that bends back inside.
    """

    try:
        _validate_path(value)
    except SvgSecurityError:
        return None
    tokens = _PATH_TOKEN_RE.findall(value)
    arity = {
        "M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4,
        "Q": 4, "T": 2, "A": 7, "Z": 0,
    }
    current = (0.0, 0.0)
    subpath_start = current
    points: list[tuple[float, float]] = []
    index = 0
    while index < len(tokens):
        command = tokens[index]
        index += 1
        upper = command.upper()
        relative = command.islower()
        if upper == "Z":
            points.extend((current, subpath_start))
            current = subpath_start
            continue
        end = index
        while end < len(tokens) and not tokens[end].isalpha():
            end += 1
        numbers = [float(token) for token in tokens[index:end]]
        size = arity[upper]
        index = end
        for group_index, offset in enumerate(range(0, len(numbers), size)):
            group = numbers[offset:offset + size]
            base_x, base_y = current

            def pair(x_value: float, y_value: float) -> tuple[float, float]:
                return ((base_x + x_value, base_y + y_value) if relative
                        else (x_value, y_value))

            if upper == "M":
                target = pair(group[0], group[1])
                if group_index == 0:
                    subpath_start = target
                else:
                    points.extend((current, target))
                points.append(target)
                current = target
            elif upper in {"L", "T"}:
                target = pair(group[0], group[1])
                points.extend((current, target))
                current = target
            elif upper == "H":
                target = (base_x + group[0] if relative else group[0], base_y)
                points.extend((current, target))
                current = target
            elif upper == "V":
                target = (base_x, base_y + group[0] if relative else group[0])
                points.extend((current, target))
                current = target
            elif upper in {"C", "S", "Q"}:
                controls = [pair(group[pos], group[pos + 1])
                            for pos in range(0, len(group), 2)]
                points.append(current)
                points.extend(controls)
                current = controls[-1]
            elif upper == "A":
                rx, ry = abs(group[0]), abs(group[1])
                target = pair(group[5], group[6])
                for anchor in (current, target):
                    points.extend(((anchor[0] - rx, anchor[1] - ry),
                                   (anchor[0] + rx, anchor[1] + ry)))
                current = target
    if not points:
        return None
    return (min(point[0] for point in points), min(point[1] for point in points),
            max(point[0] for point in points), max(point[1] for point in points))


def _primitive_bounds(element: ET.Element, tag: str) -> tuple[float, float, float, float] | None:
    """Return a conservative geometry bbox for an explicit SVG primitive."""

    try:
        if tag == "circle":
            cx, cy, radius = (float(element.attrib.get(key, "0"))
                              for key in ("cx", "cy", "r"))
            return (cx - radius, cy - radius, cx + radius, cy + radius)
        if tag == "ellipse":
            cx, cy, rx, ry = (float(element.attrib.get(key, "0"))
                              for key in ("cx", "cy", "rx", "ry"))
            return (cx - rx, cy - ry, cx + rx, cy + ry)
        if tag == "line":
            x1, y1, x2, y2 = (float(element.attrib.get(key, "0"))
                              for key in ("x1", "y1", "x2", "y2"))
            return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
        if tag == "rect":
            x = float(element.attrib.get("x", "0"))
            y = float(element.attrib.get("y", "0"))
            width = float(element.attrib["width"])
            height = float(element.attrib["height"])
            return (x, y, x + width, y + height)
        if tag in {"polygon", "polyline"}:
            values = _number_list(element.attrib.get("points", ""),
                                  label=f"{tag} points", min_count=2, even=True)
            return (min(values[::2]), min(values[1::2]),
                    max(values[::2]), max(values[1::2]))
        if tag == "path":
            return _path_conservative_bounds(element.attrib.get("d", ""))
    except (KeyError, ValueError, SvgSecurityError):
        return None
    return None


def _bounds_intersect_viewbox(bounds: tuple[float, float, float, float],
                              width: float, height: float) -> bool:
    return not (bounds[2] < 0 or bounds[3] < 0
                or bounds[0] > width or bounds[1] > height)


def validate_svg_structure(svg: str) -> list[str]:
    """Return non-throwing structural/semantic issues found in *svg*.

    This checker intentionally overlaps with the sanitizer.  It is useful on
    its own in diagnostics, and on sanitized output it verifies references,
    finite geometry, sensible strokes, and minimum visible content.
    """

    issues: list[str] = []
    try:
        root = _parse(svg)
    except SvgSecurityError as exc:
        return [f"unsafe or malformed SVG: {exc}"]

    root_tag, root_namespace = _local_tag(root.tag)
    if root_tag != "svg" or root_namespace not in {None, SVG_NS}:
        issues.append("root element must be <svg> in the SVG namespace")

    try:
        view_width, view_height = _validate_viewbox(root.attrib.get("viewBox"))
    except SvgSecurityError as exc:
        issues.append(str(exc))
        view_width = view_height = 0.0

    visible_geometry = 0
    stack: list[tuple[ET.Element, dict[str, str]]] = [(root, {})]
    element_count = 0
    while stack:
        element, inherited = stack.pop()
        element_count += 1
        tag, namespace = _local_tag(element.tag)
        if namespace not in {None, SVG_NS}:
            issues.append(f"foreign namespace on <{tag}>: {namespace}")
        if tag not in _ALLOWED_TAGS:
            issues.append(f"unsupported tag: <{tag}>")
        if tag.lower() in _BLOCKED_TAGS:
            issues.append(f"blocked tag: <{tag}>")

        style = _effective_style(element, inherited)
        for raw_name, value in element.attrib.items():
            try:
                name = _attribute_name(raw_name)
            except SvgSecurityError as exc:
                issues.append(str(exc))
                continue
            if name.lower().startswith("on") or name.lower() in {"href", "xlink:href", "src"}:
                issues.append(f"reference/event attribute is not allowed: {name}")
            if "url(" in value.lower():
                # 허용된 좁은 예외(구 음영): fill/stroke 의 로컬 그라데이션 참조.
                if name not in _PAINT_ATTRS or not _LOCAL_REF_RE.match(value.strip()):
                    issues.append(f"external/reference value in {name}")
            elif _SCHEME_RE.search(value):
                issues.append(f"external/reference value in {name}")
            if re.search(r"(?:nan|[+-]?inf(?:inity)?)", value, re.I):
                issues.append(f"non-finite numeric value in {name}")
            if tag in _TAG_ATTRS:
                try:
                    if not (tag == "svg" and name in {"width", "height", "version"}):
                        _validate_attr(tag, name, value)
                except SvgSecurityError as exc:
                    issues.append(str(exc))

        if "stroke-width" in element.attrib:
            try:
                stroke_width = float(element.attrib["stroke-width"])
                if not math.isfinite(stroke_width) or stroke_width <= 0:
                    issues.append(f"<{tag}> stroke-width must be positive and finite")
                elif stroke_width > MAX_STROKE_WIDTH:
                    issues.append(f"<{tag}> stroke-width is unreasonably large")
            except ValueError:
                issues.append(f"<{tag}> stroke-width is not numeric")

        if tag == "text" and element.attrib.get("paint-order", "").strip().lower().split()[:1] == ["stroke"]:
            stroke_color = element.attrib.get("stroke", "").strip().lower()
            if stroke_color in {"white", "#fff", "#ffffff", "#ffffffff"}:
                try:
                    halo_width = float(element.attrib.get("stroke-width", "0"))
                    font_size = float(element.attrib.get("font-size", "0"))
                    if not (3.0 <= halo_width <= min(12.0, 0.8 * font_size)):
                        issues.append(
                            "<text> white halo width must be between 3 and "
                            "min(12, 0.8 * font-size)"
                        )
                except ValueError:
                    issues.append("<text> halo width/font-size must be numeric")

        if tag in _DRAWABLE_TAGS:
            visible = _is_likely_visible(tag, style)
            has_extent = (
                tag == "text"
                or _has_geometric_extent(element, tag)
            )
            is_background = bool(
                view_width and view_height
                and _looks_like_background_rect(element, view_width, view_height)
            )
            primitive_bounds = None if tag == "text" else _primitive_bounds(element, tag)
            if (primitive_bounds is not None and view_width and view_height
                    and not is_background):
                if not _bounds_intersect_viewbox(primitive_bounds, view_width, view_height):
                    issues.append(f"<{tag}> lies entirely outside the viewBox")
                elif (primitive_bounds[0] < -view_width
                      or primitive_bounds[1] < -view_height
                      or primitive_bounds[2] > 2.0 * view_width
                      or primitive_bounds[3] > 2.0 * view_height):
                    issues.append(f"<{tag}> has coordinates unreasonably far outside the viewBox")
            if tag in {"line", "polyline"} and not visible:
                issues.append(f"<{tag}> requires a visible stroke")
            elif (tag in {"circle", "ellipse", "path", "polygon", "rect", "text"}
                  and not visible and not is_background):
                issues.append(f"<{tag}> has neither a visible fill nor stroke")
            if tag in _GEOMETRY_TAGS and not has_extent:
                issues.append(f"<{tag}> has no geometric extent")
            if (
                visible and has_extent and tag in _GEOMETRY_TAGS
                and not is_background
            ):
                visible_geometry += 1

        if tag == "tspan" and (element.text or "").strip():
            if not _is_likely_visible("text", style):
                issues.append("<tspan> contains text with neither a visible fill nor stroke")
            # Positional tspan attributes allow a model to hide only part of a
            # semantic label far outside the canvas while the parent <text>
            # still passes.  Structured engine runs do not need them; fail
            # closed for the untrusted raw-SVG fallback.
            for coordinate in ("x", "y", "dx", "dy", "rotate"):
                if coordinate not in element.attrib:
                    continue
                try:
                    values = _number_list(
                        element.attrib[coordinate], label=f"tspan {coordinate}",
                        min_count=1,
                    )
                except SvgSecurityError as exc:
                    issues.append(str(exc))
                    continue
                if coordinate == "x" and view_width and any(
                        value < 0 or value > view_width for value in values):
                    issues.append("<tspan> x lies outside the viewBox")
                elif coordinate == "y" and view_height and any(
                        value < 0 or value > view_height for value in values):
                    issues.append("<tspan> y lies outside the viewBox")
                elif coordinate == "rotate":
                    # Rotation can selectively make a suffix illegible while
                    # the parent label remains visible.  Structured runs never
                    # need it, so fail closed.
                    issues.append("<tspan> positional attribute rotate is not allowed")
                elif coordinate == "dx" and view_width and any(
                        abs(value) > view_width for value in values):
                    issues.append("<tspan> dx exceeds the viewBox width")
                elif coordinate == "dy" and view_height and any(
                        abs(value) > view_height for value in values):
                    issues.append("<tspan> dy exceeds the viewBox height")

        for child in reversed(list(element)):
            stack.append((child, style))

    if element_count > MAX_ELEMENTS:
        issues.append(f"SVG exceeds the {MAX_ELEMENTS}-element limit")
    if visible_geometry == 0:
        issues.append("minimum content not met: no visible geometric primitive")

    # Preserve order for useful diagnostics while avoiding repeated issues from
    # a group of similarly malformed descendants.
    return list(dict.fromkeys(issues))


def assess_svg(svg: str, run_pixel_lint: bool = True) -> SvgAssessment:
    """Sanitize and assess untrusted SVG without propagating gate failures."""

    try:
        sanitized = sanitize_svg(svg)
    except SvgSecurityError as exc:
        return SvgAssessment(
            sanitized_svg=None,
            issues=[],
            security_issues=[str(exc)],
            accepted=False,
        )

    issues = validate_svg_structure(sanitized)
    if run_pixel_lint and not issues:
        # lint_svg renders the document once per text label.  Bound that work
        # before entering the native renderer so a syntactically valid model
        # response cannot turn quality checking into a CPU/RAM denial of
        # service.
        clean_root = ET.fromstring(sanitized)
        clean_elements = list(clean_root.iter())
        text_count = sum(
            1 for element in clean_elements if _local_tag(element.tag)[0] == "text"
        )
        if len(clean_elements) > MAX_PIXEL_LINT_ELEMENTS:
            issues.append(
                f"pixel lint element limit exceeded: {len(clean_elements)} > "
                f"{MAX_PIXEL_LINT_ELEMENTS}"
            )
        if text_count > MAX_PIXEL_LINT_TEXTS:
            issues.append(
                f"pixel lint text limit exceeded: {text_count} > {MAX_PIXEL_LINT_TEXTS}"
            )
    if run_pixel_lint and not issues:
        try:
            from core.figure_svg import lint_svg

            pixel_issues = lint_svg(sanitized)
            issues.extend(f"pixel lint: {issue}" for issue in pixel_issues)
        except Exception as exc:  # noqa: BLE001 - a gate failure must be data, not a crash
            issues.append(f"pixel lint failed: {type(exc).__name__}: {exc}")

    issues = list(dict.fromkeys(issues))
    return SvgAssessment(
        sanitized_svg=sanitized,
        issues=issues,
        security_issues=[],
        accepted=not issues,
    )
