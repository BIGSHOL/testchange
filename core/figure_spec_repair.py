# -*- coding: utf-8 -*-
"""FigureSpec 자동 정리 + 의미 목록 대조 — 모델이 낸 그림 명세를 엔진에 넣기 전 손질.

2026-10-21 `core.figure_generator` 에서 글자 그대로 옮겼다. 그 모듈은 Claude 호출·API 키
설정(`utils.config`)까지 끌고 와서, 엔진만 옮겨 간 곳(todays-math `vendor/figure-engine`
처럼 AI 가 FigureSpec 을 내고 서버가 그리는 제품 경로)에서는 이 정리를 쓸 수 없었다.
여기는 표준 라이브러리 + `core.figure_scene` 만 쓴다.

쓰는 법::

    scene, svg, repairs = compile_with_repair(spec)          # 실패하면 SpecRepairFailed
    issue = semantic_inventory_issue(scene, desc)            # 전사(desc)에 없는 라벨·빠진 점

`figure_generator._compile_structured_candidate`(exe·웹 커넥터 경로)가 이 둘을 쓴다.
"""
from __future__ import annotations

import copy
import math
import re

from core.figure_scene import compile_figure_spec

__all__ = [
    "SNAP_TOL", "FALLBACK_FILL", "REPAIR_LIMIT", "SpecRepairFailed",
    "repair_figure_spec", "compile_with_repair", "inventory_key", "semantic_inventory_issue",
]


# ── FigureSpec 자동 정리 (2026-09-11) ───────────────────────────────────────────
#
# 웹 실사용 스펙 77개(Supabase api_cache 'figure-svg') 실측: **54개(70%)가 컴파일 실패**였고,
# 대부분은 도형이 틀려서가 아니라 모델이 붙인 **장식 칸**(라벨 위치 힌트 `pos` 68곳, 치수
# `dashed` 14, `style` 5, `size` 2 …)이나 **범위 밖 값**(치수 `side`, 진한 채색) 때문이었다.
# 그런 스펙은 모델이 손으로 찍은 SVG(라벨이 선을 밟는다)나 원본 크롭으로 떨어졌다.
#
# 원칙 — 엔진은 모르는 칸을 **일부러** 거부한다(오타를 조용히 삼키지 않으려고). 그 원칙은
# 두고, **그려지는 결과가 같은 것만** 여기서 벗긴다:
#   · 벗기는 것 = 모양·위치 힌트뿐(엔진이 스스로 정한다). 뜻을 실어 나를 수 있는 칸
#     (`label`·`text`·`value` …)이 섞여 있으면 **하나도 안 벗기고** 종전대로 실패시킨다 —
#     벗기면 치수 값이 조용히 사라진다.
#   · 엔진 오류 문구가 정본이다 — 오류를 보고 그 자리 **하나만** 고쳐 다시 컴파일한다.
#     스키마 사본을 따로 두면 엔진이 바뀔 때 한쪽만 고쳐진다.
#   · 치수가 놓일 자리가 없을 때 **치수를 빼지는 않는다** — todays-math 는 발문이 값을 말하므로
#     빼지만(renderFigureSpec.ts), 우리는 원본 그림을 옮기는 것이라 그 값이 문제의 유일한
#     정보일 수 있다(실측: 빼면 BD·OC·OA 길이가 지면에서 사라졌다).
_SPEC_DECORATIVE_FIELDS = frozenset({
    "pos", "position", "anchor", "align", "placement", "style", "size", "color",
    "colour", "width", "stroke", "stroke_width", "strokeWidth", "font_size",
    "fontSize", "opacity",
})
_SPEC_REPAIR_LIMIT = 16
# 각의 변 판정은 엔진이 `선분 길이 × 1e-7` 로 본다 — 모델 좌표 어림·반올림에 못 견딘다.
# 빗나감 실측(실패 12건): 0.09 · 0.16 · 0.57 · 0.67 | 4.2 · 4.7 · 7.4 · 13 · 20 · 32 · 34 · 350.
# 사이 [0.67, 4.2] 가 비어 있어 1.5 로 가른다 — 앞쪽은 점을 선분 위로 옮겨 붙이고(눈에 안
# 보이는 이동), 뒤쪽은 선분이 정말 빠진 것이라 종전대로 실패(모델 SVG/크롭 폴백)시킨다.
# ⚠️ 빠진 선분을 **보태는** 수리는 실측 5건 중 2건에서 원본에 없는 선·겹친 선을 만들어 기각했다.
_SPEC_SNAP_TOL = 1.5
_SPEC_FALLBACK_FILL = "#e8e8e8"   # 휘도 ≈0.81 — 엔진 하한(0.78) 위의 옅은 회색

_SPEC_UNKNOWN_RE = re.compile(r"(\w+)\.([^\s:]+): unknown field\(s\): ([^\n]+)")
_SPEC_DIM_SIDE_RE = re.compile(r"dimension side must be ([^\n]+)")
_SPEC_DIM_OFFSET_RE = re.compile(r"dimension '([^']+)' offset must be")
_SPEC_REGION_FILL_RE = re.compile(r"region '([^']+)' fill must be")
_SPEC_LABEL_POS_RE = re.compile(r"label '([^']+)' has unknown position")
_SPEC_RAY_RE = re.compile(r"angle '([^']+)' ray to '([^']+)' is not covered")


def _spec_field_is_decorative(section: str, field_name: str) -> bool:
    if field_name in _SPEC_DECORATIVE_FIELDS:
        return True
    if section == "dimensions" and field_name in {"dash", "dashed"}:
        return True                      # 치수선은 원래 점선이다
    return section == "angles" and field_name == "ticks"   # 각에서는 arcs 의 오기


def _spec_point_xy(value) -> tuple[float, float] | None:
    if (isinstance(value, (list, tuple)) and len(value) == 2
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)):
        return float(value[0]), float(value[1])
    return None


def _spec_segment_ends(segment) -> list | None:
    if isinstance(segment, (list, tuple)):
        ends = list(segment)
    elif isinstance(segment, dict):
        ends = list(segment.get("points") or [segment.get("p1"), segment.get("p2")])
    else:
        return None
    return ends if len(ends) == 2 else None


def _covering_segment(spec: dict, points: dict, q1, q2):
    """두 점을 `_SPEC_SNAP_TOL` 안에서 함께 품는 선분 중 가장 가까운 것 — (빗나감, 시작점, 방향, 길이, 이름)."""
    best = None
    for name, segment in (spec.get("segments") or {}).items():
        ends = _spec_segment_ends(segment)
        if not ends:
            continue
        a, b = _spec_point_xy(points.get(ends[0])), _spec_point_xy(points.get(ends[1]))
        if a is None or b is None:
            continue
        d = (b[0] - a[0], b[1] - a[1])
        length = math.hypot(*d)
        if length <= _SPEC_SNAP_TOL:
            continue
        margin = _SPEC_SNAP_TOL / length
        worst = 0.0
        for q in (q1, q2):
            t = ((q[0] - a[0]) * d[0] + (q[1] - a[1]) * d[1]) / (length * length)
            off = _line_offset(a, d, length, q)
            if off > _SPEC_SNAP_TOL or not -margin <= t <= 1 + margin:
                break
            worst = max(worst, off)
        else:
            if best is None or worst < best[0]:
                best = (worst, a, d, length, name)
    return best


def _line_offset(a, d, length: float, q) -> float:
    return abs(d[0] * (a[1] - q[1]) - (a[0] - q[0]) * d[1]) / length


def _project_on_line(a, d, length: float, q) -> list[float]:
    t = ((q[0] - a[0]) * d[0] + (q[1] - a[1]) * d[1]) / (length * length)
    return [a[0] + t * d[0], a[1] + t * d[1]]


def _snap_ray_point(spec: dict, angle_name: str, ray_point: str) -> str | None:
    """각의 변이 선언된 선분에서 `_SPEC_SNAP_TOL` 이내로만 빗나갔으면 점을 선분 위로 옮긴다.

    꼭짓점이 **두 변의 교점**이면(두 변이 서로 다른 선분 위) 한쪽 선분에만 붙이면 다른
    쪽에서 떨어져 두 오류가 번갈아 난다(실측 #061) — 그때는 두 선분의 **교점**으로 옮긴다.
    ⚠️ 반올림하지 않는다 — 엔진 허용오차가 `길이 × 1e-7`(길이 96 이면 1e-5)이라 소수 넷째
       자리 반올림(±5e-5)만으로도 다시 빗나가 같은 오류가 되풀이됐다.
    """
    angle = (spec.get("angles") or {}).get(angle_name)
    points = spec.get("points")
    if not isinstance(angle, dict) or not isinstance(points, dict):
        return None
    vertex = angle.get("vertex")
    rays = list(angle.get("points") or [angle.get("p1"), angle.get("p2")])
    v, p = _spec_point_xy(points.get(vertex)), _spec_point_xy(points.get(ray_point))
    if v is None or p is None:
        return None
    hit = _covering_segment(spec, points, v, p)
    if hit is None:
        return None
    _, a, d, length, name = hit
    moved = []
    if _line_offset(a, d, length, v) > 1e-9:
        target = _project_on_line(a, d, length, v)
        other = next((r for r in rays if r and r != ray_point), None)
        q_other = _spec_point_xy(points.get(other)) if other else None
        hit2 = _covering_segment(spec, points, v, q_other) if q_other else None
        if hit2 is not None and hit2[4] != name:
            _, a2, d2, length2, _ = hit2
            det = d[0] * d2[1] - d[1] * d2[0]
            if abs(det) > 1e-9 * length * length2:
                s = ((a2[0] - a[0]) * d2[1] - (a2[1] - a[1]) * d2[0]) / det
                crossing = [a[0] + s * d[0], a[1] + s * d[1]]
                if math.hypot(crossing[0] - v[0], crossing[1] - v[1]) <= 2 * _SPEC_SNAP_TOL:
                    target = crossing
        points[vertex] = target
        moved.append(vertex)
    if _line_offset(a, d, length, p) > 1e-9:
        points[ray_point] = _project_on_line(a, d, length, p)
        moved.append(ray_point)
    return f"snap:{'/'.join(moved)}→{name}" if moved else None


def _repair_figure_spec(spec: dict, message: str) -> str | None:
    """엔진 오류 하나를 보고 **그려지는 결과가 같은** 수리 하나를 한다. 못 하면 None."""
    m = _SPEC_UNKNOWN_RE.search(message)
    if m:
        section, name = m.group(1), m.group(2)
        fields = [f.strip() for f in m.group(3).split(",") if f.strip()]
        entries = spec.get(section)
        entry = entries.get(name) if isinstance(entries, dict) else None
        if (not isinstance(entry, dict) or not fields
                or not all(_spec_field_is_decorative(section, f) for f in fields)):
            return None
        for f in fields:
            value = entry.pop(f, None)
            if (section == "segments" and f == "style" and isinstance(value, str)
                    and ("dash" in value or "dot" in value)):
                entry.setdefault("dashed", True)
            if (section == "angles" and f == "ticks" and "arcs" not in entry
                    and isinstance(value, int) and not isinstance(value, bool)
                    and 1 <= value <= 3):
                entry["arcs"] = value
        return f"{section}.{name}-{'+'.join(fields)}"
    m = _SPEC_DIM_SIDE_RE.search(message)
    if m:
        allowed = set(re.findall(r"'([^']+)'", m.group(1)))
        dims = spec.get("dimensions") or {}
        changed = [n for n, d in dims.items()
                   if isinstance(d, dict) and "side" in d and d["side"] not in allowed]
        for n in changed:
            dims[n].pop("side")
        return f"dimensions.{'/'.join(changed)}-side" if changed else None
    m = _SPEC_DIM_OFFSET_RE.search(message)
    if m:
        entry = (spec.get("dimensions") or {}).get(m.group(1))
        if isinstance(entry, dict) and "offset" in entry:
            entry.pop("offset")
            return f"dimensions.{m.group(1)}-offset"
        return None
    m = _SPEC_REGION_FILL_RE.search(message)
    if m:
        entry = (spec.get("regions") or {}).get(m.group(1))
        if isinstance(entry, dict) and entry.get("fill") != _SPEC_FALLBACK_FILL:
            entry["fill"] = _SPEC_FALLBACK_FILL
            return f"regions.{m.group(1)}-fill"
        return None
    m = _SPEC_LABEL_POS_RE.search(message)
    if m:
        entry = (spec.get("labels") or {}).get(m.group(1))
        if isinstance(entry, dict) and "position" in entry:
            entry.pop("position")
            return f"labels.{m.group(1)}-position"
        return None
    m = _SPEC_RAY_RE.search(message)
    if m:
        return _snap_ray_point(spec, m.group(1), m.group(2))
    return None


# 라벨·전사 비교용 정규형 — 같은 값을 다르게 적은 것(35°/35 degrees, √11/\sqrt{11},
# 5 cm/5cm)을 맞춘다. 실측: 전사가 "angle A is 35 degrees" 인데 라벨 "35°" 라 멀쩡한
# 스펙 8개가 떨어졌다(웹 실사용 77개 중).
_INVENTORY_SQRT_RE = re.compile(
    r"\\sqrt\s*\{([^{}]+)\}|\bsqrt\s*\(([^()]+)\)|square root of\s+(\w+)")
_INVENTORY_DEGREE_RE = re.compile(r"(\d+(?:\.\d+)?|\b[a-zA-Z]\b)\s*(?:degrees?|°)")


def _inventory_key(text: str) -> str:
    s = _INVENTORY_SQRT_RE.sub(
        lambda m: "√" + (m.group(1) or m.group(2) or m.group(3)).strip(), str(text or ""))
    s = _INVENTORY_DEGREE_RE.sub(lambda m: m.group(1) + "°", s)
    return re.sub(r"\s+", "", s)


def _semantic_inventory_issue(scene, desc: str) -> str | None:
    """Cross-check structured labels against the model's own transcription.

    This is not image understanding; it is a deterministic anti-omission gate.
    Every explicit point/angle/dimension label compiled into the scene must occur in the
    preceding transcription, and the transcription may not name an additional
    standalone Latin point that the spec silently dropped.
    """

    normalized = str(desc or "").strip()
    if not normalized:
        # Direct/internal FigureSpec calls need no transcription.  Model output
        # does: `_vision_to_svg` always sets ``desc`` (possibly empty), so only
        # enforce when the key is present at the caller below.
        return None
    expected = {label.text for label in scene.labels.values()}
    expected.update(angle.label for angle in scene.angles.values() if angle.label)
    expected.update(dimension.label for dimension in scene.dimensions.values()
                    if dimension.label)
    haystack = _inventory_key(normalized)
    missing = sorted(label for label in expected if _inventory_key(label) not in haystack)
    if missing:
        return "FigureSpec 의미 목록 불일치: 전사에 없는 라벨 " + ", ".join(missing)
    transcript_points = set(re.findall(r"(?<![A-Za-z])([A-Z])(?![A-Za-z])", normalized))
    scene_points = {label.text for label in scene.labels.values()
                    if re.fullmatch(r"[A-Z]", label.text)}
    omitted = sorted(transcript_points - scene_points)
    if omitted:
        return "FigureSpec 의미 목록 불일치: spec에서 누락된 점 " + ", ".join(omitted)
    return None


class SpecRepairFailed(ValueError):
    """정리해도 컴파일되지 않는 스펙. 메시지 = 마지막 엔진 오류(``형식: 문구``)."""


def compile_with_repair(spec, limit: int = _SPEC_REPAIR_LIMIT):
    """FigureSpec → (scene, svg, 정리 기록). 엔진 오류를 보고 **그려지는 결과가 같은** 수리를
    하나씩 해 다시 컴파일한다. 호출자의 스펙은 고치지 않는다(사본에서 작업).

    뜻을 실을 수 있는 칸이 섞였거나 같은 수리가 되풀이되면 `SpecRepairFailed`.
    """
    if isinstance(spec, dict):
        spec = copy.deepcopy(spec)
    repairs: list[str] = []
    while True:
        try:
            scene = compile_figure_spec(spec)
            return scene, scene.render_svg(), repairs
        except Exception as exc:  # noqa: BLE001 — invalid model data becomes feedback
            note = None
            if isinstance(spec, dict) and len(repairs) < limit:
                note = _repair_figure_spec(spec, str(exc))
            if not note or note in repairs[-1:]:      # 같은 수리가 되풀이되면 그만
                raise SpecRepairFailed(f"{type(exc).__name__}: {exc}") from exc
            repairs.append(note)


# 공개 이름 — 모듈 안의 밑줄 이름은 figure_generator 와 테스트가 그대로 쓴다.
SNAP_TOL = _SPEC_SNAP_TOL
FALLBACK_FILL = _SPEC_FALLBACK_FILL
REPAIR_LIMIT = _SPEC_REPAIR_LIMIT
repair_figure_spec = _repair_figure_spec
inventory_key = _inventory_key
semantic_inventory_issue = _semantic_inventory_issue
