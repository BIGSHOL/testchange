# -*- coding: utf-8 -*-
"""공간도형(정사영·이면각) 작도용 3D 계산 + 검산 — :mod:`core.figure_svg` 의 3D 짝.

`figure_svg` 는 2D 전용이라 정사영 그림을 그리려면 시험지 스크립트마다 투영식을
손으로 짜 넣어야 했다. 그러면 ① 스크립트마다 투영 상수가 달라지고 ② 무엇보다
**검산이 안 걸린다** — `verify_figure` 는 2D 길이·각만 재므로 "A′ 가 정말 A 의
정사영 발인가", "S′ = S cos θ 인가" 같은 공간 명제를 통과시켜 버린다. 좌표를
눈대중으로 찍은 정사영 그림이 `lint_svg` CLEAN 으로 나가는 게 실제로 가능했다.

그래서 이 모듈은 **좌표만** 만든다(SVG 는 한 조각도 내보내지 않는다):

    3D 점  ──foot/dihedral 등 공간 계산──▶  검산(verify_solid)
                     │
                     └── View 투영 ──▶ 2D 점 ──▶ figure_svg 프리미티브로 작도

검산은 `figure_svg` 의 등록부를 그대로 쓴다. 따라서 빌드 하네스의
``unverified(S)`` 가 2D·3D 그림을 **한 그물로** 잡는다(따로 관리하면 3D 쪽 누락이
조용히 빠져나간다).

표준 라이브러리만 쓴다 — 작도 경로에 numpy 를 끌어들이지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence

from core import figure_svg as _fs


Vec3 = tuple[float, float, float]
Pt2 = tuple[float, float]

_EPS = 1e-9


class SolidGeometryError(ValueError):
    """공간 구성이 모순이거나(퇴화 평면 등) 검산이 실패했을 때."""


# ── 벡터 기본(3-튜플) ────────────────────────────────────────────────────

def _v(p) -> Vec3:
    x, y, z = (float(c) for c in p)
    for c in (x, y, z):
        if not math.isfinite(c):
            raise SolidGeometryError("좌표는 유한한 수여야 함")
    return (x, y, z)


def sub(a, b) -> Vec3:
    a, b = _v(a), _v(b)
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def add(a, b) -> Vec3:
    a, b = _v(a), _v(b)
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def scale(a, t: float) -> Vec3:
    a = _v(a)
    return (a[0] * t, a[1] * t, a[2] * t)


def dot(a, b) -> float:
    a, b = _v(a), _v(b)
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b) -> Vec3:
    a, b = _v(a), _v(b)
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def norm(a) -> float:
    return math.sqrt(dot(a, a))


def unit(a) -> Vec3:
    n = norm(a)
    if n <= _EPS:
        raise SolidGeometryError("영벡터는 정규화할 수 없음")
    return scale(a, 1.0 / n)


def dist(a, b) -> float:
    return norm(sub(a, b))


# ── 평면 ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class Plane:
    """점 하나와 **단위 법선**으로 정한 평면."""

    point: Vec3
    normal: Vec3

    @classmethod
    def through(cls, a, b, c) -> "Plane":
        """세 점을 지나는 평면 — 세 점이 일직선이면 예외(퇴화 방지)."""
        n = cross(sub(b, a), sub(c, a))
        if norm(n) <= _EPS:
            raise SolidGeometryError("세 점이 일직선이라 평면이 정해지지 않음")
        return cls(_v(a), unit(n))

    @classmethod
    def xy(cls) -> "Plane":
        """z=0 평면 — 시험지 정사영 문항의 기본 평면 α."""
        return cls((0.0, 0.0, 0.0), (0.0, 0.0, 1.0))

    def signed_distance(self, p) -> float:
        return dot(sub(p, self.point), self.normal)

    def contains(self, p, tol: float = 1e-6) -> bool:
        return abs(self.signed_distance(p)) <= tol


def foot(p, plane: Plane) -> Vec3:
    """점 p 의 평면 위 **정사영 발** — 법선 성분을 뺀다."""
    return sub(p, scale(plane.normal, plane.signed_distance(p)))


def project_points(points: Iterable, plane: Plane) -> list[Vec3]:
    return [foot(p, plane) for p in points]


# ── 각·넓이 ──────────────────────────────────────────────────────────────

def _acute(deg: float) -> float:
    """0~90° 로 접는다 — 이면각·직선과 평면이 이루는 각은 예각으로 답한다."""
    d = abs(deg) % 180.0
    return 180.0 - d if d > 90.0 else d


def dihedral_angle(a: Plane, b: Plane) -> float:
    """두 평면이 이루는 각(도, 예각). 법선 방향의 부호에 흔들리지 않는다."""
    c = max(-1.0, min(1.0, dot(a.normal, b.normal)))
    return _acute(math.degrees(math.acos(c)))


def line_plane_angle(p, q, plane: Plane) -> float:
    """직선 pq 와 평면이 이루는 각(도) — 법선과의 각의 여각."""
    d = unit(sub(q, p))
    s = abs(max(-1.0, min(1.0, dot(d, plane.normal))))
    return math.degrees(math.asin(s))


def area(polygon: Sequence) -> float:
    """평면 위 다각형의 넓이 — 꼭짓점 순서대로 외적을 누적한다.

    ⚠️ 꼬인(non-planar) 다각형은 값이 의미 없다. `verify_solid` 의 ``areas``
    검사가 평면성부터 확인하는 이유다.
    """
    pts = [_v(p) for p in polygon]
    if len(pts) < 3:
        raise SolidGeometryError("넓이는 꼭짓점 3개 이상이어야 함")
    acc = (0.0, 0.0, 0.0)
    o = pts[0]
    for i in range(1, len(pts) - 1):
        acc = add(acc, cross(sub(pts[i], o), sub(pts[i + 1], o)))
    return 0.5 * norm(acc)


def is_planar(polygon: Sequence, tol: float = 1e-6) -> bool:
    pts = [_v(p) for p in polygon]
    if len(pts) <= 3:
        return True
    pl = Plane.through(pts[0], pts[1], pts[2])
    return all(pl.contains(p, tol) for p in pts[3:])


def projected_area(polygon: Sequence, plane: Plane) -> float:
    """정사영된 도형의 넓이 — S′ = S·cos θ 의 좌변을 직접 계산한 값."""
    return area(project_points(polygon, plane))


# ── 3D → 2D 투영(작도용) ─────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class View:
    """공간 좌표를 **SVG 좌표(y 아래로 증가)** 로 옮기는 사투영(oblique).

    교과서 공간도형 그림은 카메라 원근이 아니라 **사방(cabinet) 투영**이다 —
    깊이축만 눕혀서 k 배로 줄인다. mplot3d 같은 원근 렌더로 그리면 평면이
    과하게 기울고 수선이 뭉개져 시험지 그림처럼 안 보인다(실측 2026-08-13).

    x→오른쪽, y→깊이(뒤), z→위 를 가정한다.
    """

    depth_ratio: float = 0.5      # k: 깊이축 축소 비율(cabinet 관례 = 1/2)
    depth_deg: float = 45.0       # 깊이축을 지면에서 몇 도 눕힐지
    scale: float = 60.0           # 1 단위 = 몇 SVG 단위
    origin: Pt2 = (200.0, 200.0)  # 원점이 놓일 SVG 좌표

    def __post_init__(self) -> None:
        if self.scale <= 0:
            raise SolidGeometryError("View.scale 은 양수여야 함")
        if self.depth_ratio < 0:
            raise SolidGeometryError("View.depth_ratio 는 음이 아니어야 함")

    def __call__(self, p) -> Pt2:
        x, y, z = _v(p)
        a = math.radians(self.depth_deg)
        u = x + self.depth_ratio * y * math.cos(a)
        w = z + self.depth_ratio * y * math.sin(a)
        return (self.origin[0] + self.scale * u,
                self.origin[1] - self.scale * w)      # SVG 는 y 가 아래로

    def many(self, points: Iterable) -> list[Pt2]:
        return [self(p) for p in points]

    @property
    def direction(self) -> Vec3:
        """시선 방향(관찰자 → 화면 안쪽). 이 방향으로 놓인 두 점은 겹쳐 보인다."""
        a = math.radians(self.depth_deg)
        return unit((-self.depth_ratio * math.cos(a), 1.0,
                     -self.depth_ratio * math.sin(a)))

    def is_back_facing(self, outward_normal) -> bool:
        """바깥 법선이 이 방향인 면이 뒤쪽인가 — 볼록 입체의 숨은 모서리 판정용.

        ⚠️ **볼록 입체에서만** 옳다(직육면체·각기둥·정사면체). 오목하거나 여러
        입체가 겹치면 면 단위 판정으로는 부족하다.
        """
        return dot(unit(outward_normal), self.direction) > 0.0

    def collapses(self, polygon: Sequence, tol: float = 1e-3) -> bool:
        """이 시점에서 다각형이 선으로 뭉개지는가(퇴화 시점) — 작도 전 경고용."""
        pts = self.many(polygon)
        if len(pts) < 3:
            return True
        ax, ay = pts[0]
        acc = 0.0
        for i in range(1, len(pts) - 1):
            bx, by = pts[i]
            cx, cy = pts[i + 1]
            acc += (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
        return abs(0.5 * acc) <= tol * self.scale ** 2


@dataclass(frozen=True, slots=True)
class Camera:
    """**정투영(orthographic)** 시점 — 사방투영과 달리 각도·비율이 정직하다.

    사방(cabinet)투영은 깊이축만 눌러서 구가 타원으로, 구 위의 원이 구 밖으로
    삐져나온다. 구·원뿔곡선처럼 **곡선이 주인공인 그림**은 정규직교 시선기저로
    투영해야 구가 정확한 원, 3D 원이 정확한 타원이 된다.

    elev(고도)·azim(방위)는 도 단위. 시선방향은 장면 **안쪽**을 향한다.
    """

    elev: float = 22.0
    azim: float = -60.0
    scale: float = 60.0
    origin: Pt2 = (200.0, 200.0)

    def __post_init__(self) -> None:
        if self.scale <= 0:
            raise SolidGeometryError("Camera.scale 은 양수여야 함")
        if abs(math.cos(math.radians(self.elev))) <= 1e-6:
            raise SolidGeometryError("Camera.elev 이 ±90° 면 기저가 퇴화한다")

    @property
    def _basis(self) -> tuple[Vec3, Vec3, Vec3]:
        e, a = math.radians(self.elev), math.radians(self.azim)
        eye = (math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e))
        right = unit(cross((0.0, 0.0, 1.0), eye))
        up = cross(eye, right)
        return right, up, scale(eye, -1.0)          # 시선 = 장면 안쪽

    def __call__(self, p) -> Pt2:
        right, up, _ = self._basis
        return (self.origin[0] + self.scale * dot(p, right),
                self.origin[1] - self.scale * dot(p, up))

    def many(self, points: Iterable) -> list[Pt2]:
        right, up, _ = self._basis
        return [(self.origin[0] + self.scale * dot(p, right),
                 self.origin[1] - self.scale * dot(p, up)) for p in points]

    @property
    def direction(self) -> Vec3:
        return self._basis[2]

    def depth(self, p) -> float:
        """시선 방향 깊이 — 클수록 **뒤쪽**(가려지는 쪽)."""
        return dot(p, self.direction)

    def is_back_facing(self, outward_normal) -> bool:
        return dot(unit(outward_normal), self.direction) > 0.0

    def collapses(self, polygon: Sequence, tol: float = 1e-3) -> bool:
        """이 시점에서 다각형이 선으로 뭉개지는가(퇴화 시점).

        ⚠️ `View` 에만 있고 `Camera` 에 없던 검사다 — 그래서 시선과 나란해진 평면이
        납작한 조각으로 출하됐다(실측 2026-08-13, 구 그림의 기울어진 평면).
        """
        pts = self.many(polygon)
        if len(pts) < 3:
            return True
        ax, ay = pts[0]
        acc = 0.0
        for i in range(1, len(pts) - 1):
            bx, by = pts[i]
            cx, cy = pts[i + 1]
            acc += (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
        return abs(0.5 * acc) <= tol * self.scale ** 2


def circle3(center, radius: float, normal, n: int = 96) -> list[Vec3]:
    """공간에서 중심·반지름·법선으로 정해지는 **원 위의 점열**.

    구의 적도·경선, 원기둥 밑면, 정사영된 원 등이 전부 이걸로 나온다. 투영하면
    (정투영 기준) 정확한 타원이 된다.
    """
    if radius <= 0:
        raise SolidGeometryError("circle3: 반지름은 양수여야 함")
    if n < 8:
        raise SolidGeometryError("circle3: 표본은 8개 이상이어야 함")
    w = unit(normal)
    seed = (1.0, 0.0, 0.0) if abs(w[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = unit(cross(w, seed))
    v = cross(w, u)
    out = []
    for i in range(n + 1):
        t = 2.0 * math.pi * i / n
        out.append(add(center, add(scale(u, radius * math.cos(t)),
                                   scale(v, radius * math.sin(t)))))
    return out


def split_by_depth(points: Sequence, cam: "Camera", pivot: float = 0.0):
    """점열을 앞(보임)/뒤(가림) 구간들로 나눈다 — 숨은 곡선을 점선으로 그리기 위함.

    구 위의 원처럼 **곡선의 일부만 가려지는** 경우, 면 단위 back-face 판정으로는
    못 나눈다. 시선 깊이의 부호로 잘라 각 구간을 따로 그린다.
    """
    front: list[list] = []
    back: list[list] = []
    cur: list = []
    cur_back = cam.depth(points[0]) > pivot
    for p in points:
        b = cam.depth(p) > pivot
        if b != cur_back:
            if len(cur) >= 2:
                (back if cur_back else front).append(cur + [p])
            cur, cur_back = [cur[-1]] if cur else [], b
        cur.append(p)
    if len(cur) >= 2:
        (back if cur_back else front).append(cur)
    return front, back


def plane_intersection(a: Plane, b: Plane) -> tuple[Vec3, Vec3]:
    """두 평면의 교선 — (교선 위 한 점, 단위 방향). 평행이면 예외."""
    d = cross(a.normal, b.normal)
    if norm(d) <= 1e-9:
        raise SolidGeometryError("두 평면이 평행해 교선이 없음")
    d = unit(d)
    # 교선 위 한 점: a·n1 = p1·n1, b·n2 = p2·n2 를 만족하는 점을 d 에 수직한 평면에서 푼다.
    n1, n2 = a.normal, b.normal
    c1, c2 = dot(a.point, n1), dot(b.point, n2)
    denom = 1.0 - dot(n1, n2) ** 2
    k1 = (c1 - c2 * dot(n1, n2)) / denom
    k2 = (c2 - c1 * dot(n1, n2)) / denom
    return add(scale(n1, k1), scale(n2, k2)), d


def cabinet(scale: float = 60.0, origin: Pt2 = (200.0, 200.0),
            depth_ratio: float = 0.5, depth_deg: float = 45.0) -> View:
    """교과서 표준 사방 투영."""
    return View(depth_ratio, depth_deg, scale, origin)


def isometric(scale: float = 60.0, origin: Pt2 = (200.0, 200.0)) -> View:
    """등각 느낌의 사투영(깊이 30° 로 눕힌 cabinet) — 입체 겨냥도용."""
    return View(0.58, 30.0, scale, origin)


# ── 검산 ─────────────────────────────────────────────────────────────────

def plane_from_equation(a: float, b: float, c: float, d: float) -> Plane:
    """``ax + by + cz + d = 0`` 으로 평면을 만든다 — 라벨과 작도의 단일 출처.

    평면을 좌표로 따로 만들고 라벨을 손으로 적으면 둘이 갈라진다(실측 2026-08-13:
    작도는 ``y = 4`` 인데 그림엔 ``y = 3`` 이 인쇄됐고, 검산이 그걸 못 잡았다).
    """
    n = (float(a), float(b), float(c))
    if norm(n) <= _EPS:
        raise SolidGeometryError("법선이 영벡터라 평면이 아님")
    u = unit(n)
    return Plane(scale(u, -float(d) / norm(n)), u)


def equation_text(a: float, b: float, c: float, d: float,
                  names: Sequence[str] = ("x", "y", "z")) -> str:
    """평면 방정식을 사람이 읽는 문자열로 — 라벨을 **계수에서 생성**해 드리프트를 막는다."""
    parts: list[str] = []
    for coef, nm in zip((a, b, c), names):
        if abs(coef) <= _EPS:
            continue
        sign = "-" if coef < 0 else ("+" if parts else "")
        mag = abs(coef)
        body = nm if abs(mag - 1.0) <= 1e-9 else (
            f"√{round(mag ** 2)} {nm}" if abs(mag ** 2 - round(mag ** 2)) < 1e-9
            and abs(mag - round(mag)) > 1e-9 else f"{mag:g} {nm}")
        parts.append(f"{sign} {body}".strip() if parts else f"{sign}{body}")
    if abs(d) > _EPS:
        parts.append(f"{'-' if d < 0 else '+'} {abs(d):g}")
    return " ".join(parts) + " = 0"


def verify_solid(name, *, feet=(), angles=(), areas=(), lengths=(), equations=(),
                 perpendicular=(), on_plane=(), view: View | None = None,
                 tol: float = 0.06, tol_deg: float = 2.0,
                 tol_abs: float = 1e-6) -> None:
    """**공간 구성이 문제 조건과 맞는지** 재계산해 대조한다 — 안 맞으면 예외.

    `figure_svg.verify_figure` 의 3D 판이고, 같은 등록부에 기록하므로
    ``unverified(S)`` 가 2D·3D 를 함께 감시한다.

    feet:          (A′, A, plane)            — A′ 가 정말 A 의 정사영 발인가
    angles:        (라벨각, kind, *인자)      — kind='dihedral' → (평면a, 평면b)
                                                kind='line'     → (p, q, plane)
    areas:         (S′라벨|None, 다각형, plane) — 평면성 + S′ = S·cos θ
    lengths:       (라벨값, p, q)             — 3D 거리(척도 중앙값으로 비율 검사)
    equations:     ((a, b, c, d), plane)      — 그림에 적은 방정식 ↔ 실제 평면
    perpendicular: ((p, q), (r, s))          — 두 선분이 수직인가
    on_plane:      (점, plane)                — 점이 그 평면 위인가
    view:          주면 퇴화 시점(면이 선으로 뭉갬)인지 함께 본다

    ⚠️ ``lengths`` 는 **한 척도 풀**이다 — 단위가 다르면 이름을 나눠 따로 부른다
    (`verify_figure` 와 같은 규칙).
    """
    problems: list[str] = []
    checks = 0

    for f2, p, plane in feet:
        checks += 1
        want = foot(p, plane)
        d = dist(_v(f2), want)
        if d > max(tol_abs, tol * max(1.0, norm(sub(p, plane.point)))):
            problems.append(
                f"  정사영 발: 적어 둔 {tuple(round(c, 4) for c in _v(f2))} 이"
                f" 실제 발 {tuple(round(c, 4) for c in want)} 과 {d:.4f} 어긋남")

    for item in angles:
        checks += 1
        value, kind = float(item[0]), str(item[1])
        if kind == "dihedral":
            drawn = dihedral_angle(item[2], item[3])
        elif kind == "line":
            drawn = line_plane_angle(item[2], item[3], item[4])
        else:
            raise SolidGeometryError(f"angles kind 는 dihedral|line: {kind!r}")
        if abs(drawn - value) > tol_deg:
            problems.append(
                f"  각 {value}°({kind}): 실제 구성은 {drawn:.2f}°"
                f" (차 {abs(drawn - value):.2f}° > 허용 {tol_deg}°)")

    for label, poly, plane in areas:
        checks += 1
        if not is_planar(poly):
            problems.append("  넓이: 다각형이 한 평면 위에 있지 않음(꼬인 도형)")
            continue
        s = area(poly)
        s2 = projected_area(poly, plane)
        theta = dihedral_angle(Plane.through(poly[0], poly[1], poly[2]), plane)
        want = s * math.cos(math.radians(theta))
        if abs(s2 - want) > max(tol_abs, tol * max(want, _EPS)):
            problems.append(
                f"  정사영 넓이: S′={s2:.6f} 인데 S·cosθ={want:.6f}"
                f" (S={s:.6f}, θ={theta:.2f}°)")
        if label is not None and abs(s2 - float(label)) > tol * max(abs(float(label)), _EPS):
            problems.append(
                f"  정사영 넓이 라벨 {label}: 실제 S′={s2:.6f}")

    items = [(f"길이 {value}", float(value), dist(p, q)) for value, p, q in lengths]
    if items:
        ratios = sorted(m / v for _, v, m in items if v > _EPS)
        if not ratios:
            raise SolidGeometryError(f"{name} 검산: 라벨값은 양수여야 함")
        mid = len(ratios) // 2
        k = ratios[mid] if len(ratios) % 2 else 0.5 * (ratios[mid - 1] + ratios[mid])
        for desc, value, measured in items:
            want = k * value
            if want <= _EPS:
                continue
            err = abs(measured - want) / want
            if err > tol:
                problems.append(
                    f"  {desc}: 실제 길이가 라벨 대비 {measured / want:.2f}배"
                    f" (오차 {err * 100:.0f}% > 허용 {tol * 100:.0f}%)")
        checks += len(items)

    for (p, q), (r, s) in perpendicular:
        checks += 1
        u, w = sub(q, p), sub(s, r)
        if norm(u) <= _EPS or norm(w) <= _EPS:
            problems.append("  수직 검사: 길이가 0 인 선분")
            continue
        c = abs(dot(unit(u), unit(w)))
        if c > math.sin(math.radians(tol_deg)):
            problems.append(
                f"  수직 검사: 두 선분이 이루는 각 "
                f"{math.degrees(math.acos(min(1.0, c))):.2f}° (90° 여야 함)")

    for coeffs, plane in equations:
        checks += 1
        a_, b_, c_, d_ = (float(v) for v in coeffs)
        want = plane_from_equation(a_, b_, c_, d_)
        # 법선은 부호가 반대라도 같은 평면이다.
        aligned = abs(dot(want.normal, plane.normal))
        off = abs(want.signed_distance(plane.point))
        if aligned < math.cos(math.radians(tol_deg)) or off > max(tol_abs, 1e-4):
            problems.append(
                f"  방정식 라벨 {equation_text(a_, b_, c_, d_)}: 실제 평면과 다름"
                f"(법선 어긋남 {math.degrees(math.acos(min(1.0, aligned))):.2f}°,"
                f" 거리 {off:.4f})")

    for p, plane in on_plane:
        checks += 1
        d = abs(plane.signed_distance(p))
        if d > max(tol_abs, 1e-4):
            problems.append(f"  평면 위 검사: 점이 평면에서 {d:.6f} 떨어져 있음")

    if view is not None:
        for _, poly, _ in areas:
            if view.collapses(poly):
                problems.append("  시점: 이 View 에서 도형이 선으로 뭉갠다(퇴화)")
                break

    if problems:
        raise SolidGeometryError(
            f"[{name}] 공간 검산 실패 — 라벨과 구성이 모순된다. "
            f"좌표를 조건에서 유도할 것:\n" + "\n".join(problems))

    # figure_svg 와 **같은 등록부**에 남긴다 — unverified() 가 한 그물로 본다.
    _fs._VERIFIED[(_fs._caller_scope(2), str(name))] = checks
