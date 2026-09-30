# -*- coding: utf-8 -*-
"""초등 후반 그림 — 그래프·입체·쌓기나무·이동·대칭.

elementary.render_elementary 이 KIND 를 합친다. 같은 그림이 두 번이면 여기 kind (D-61).
기하 작도(치수선만)는 엔진 A. 조작형(자·컴퍼스·그리세요)은 그리지 않는다.
"""
from __future__ import annotations

import math
import re
from typing import Any, Mapping

from elementary import (
    DIM_OFF,
    FIT_PAD,
    GRID,
    GRID_SW,
    INK,
    PAPER,
    TABLE_VIEWBOX_MAX,
    _arrow_right,
    _dashed_polyline,
    _esc,
    _label_w_max,
    _text_bboxes,
    _length_mark,
    _n,
    _rect,
    _shift_body,
    _svg,
    _svg_raw,
    _text,
)

# 🔴 **입체 그림의 획 굵기** — 원장님 확정 2026-08-28 (D-07 · 시안 ②).
#
# 정본 실측(RPM 중1-2 p126·p130 여러 자리): 도형 윤곽선 **0.8pt** · 치수/숨은 파선
# **0.3~0.5pt** — 치수가 도형선의 **0.375~0.625배**다. 우리는 도형 1.15 · 치수 1.4 라
# **치수가 더 굵었다**(비 1.22). 그래서 치수 점선이 배경으로 안 물러나고 앞으로 튀어나왔다.
#
# 확정: 도형 실선 **1.4** · 치수 점선 **0.6**(vendor `core.figure_svg.meas`) → 비 **0.43**.
#
# ⚠️ 각 호(`angle_mark`)는 **여기 없다** — 별도 D-07 항목(「각 호가 정본보다 2배 굵다」)이라
#    같이 움직이면 어느 쪽이 원장님 확정인지 이력에서 안 갈린다.
SOLID_SW = 1.4

# 🔴 **입체 그림의 크기** — 원장님 확정 2026-08-28 「정본 비율로 바로 맞춰라」(D-07).
#
# 정본 실측(RPM 0849 — 우리 `cutCuboid` 와 **같은 문제·같은 치수 여섯**):
# 도형(실선) 대각 95.1pt ÷ 라벨 8.0pt = **11.9**. 우리는 **7.1** 이었다 — 도형이 정본의
# 60% 라 치수를 놓을 자리가 없었고, 고정 거리가 실루엣 안쪽에 떨어졌다.
#
# ⚠️ **배율만 올리면 안 된다.** viewBox 가 커지면 `figureSvgFrame` 등급(폭 ≤160 →
#    140px, ≤320 → 240px)을 넘어 종이에서 그림이 통째로 1.7배가 되고, 그러면 라벨도
#    같이 커진다. 정본은 **라벨 ÷ 본문 글자**도 0.762 인데 우리는 0.930 이었다.
#    그래서 **배율을 올리고 라벨을 줄인다** — 여백도 라벨에 맞춰 줄어 등급이 안 넘어간다.
#
# ⚠️ 이 셋은 **한 곳에만** 적는다. 종전에는 `56.0 / mx` 가 세 곳(`_cuboid`·`_hollow_box`
#    ·`_cut_cuboid`), `70.0 / …` 이 네 곳에 손으로 적혀 있었다 — 한쪽만 고치면
#    같은 지면에 두 크기가 섞인다.
SOLID_UNITS = 84.0      # 각기둥·직육면체 계열: 가장 긴 모서리의 화면 길이 (종전 56.0)
ROUND_UNITS = 112.7     # 원기둥·원뿔·구 계열 (70.0 → 98.0 → 112.7)
#                         ⚠️ 여기가 **인쇄 등급 경계가 허락하는 한계**다 — 원기둥의
#                         viewBox 폭이 정확히 **160.0** 이 된다(`figureSvgFrame` 은
#                         ≤160 이 compact/140px). 넘으면 mid(240px)로 뛰어 종이에서
#                         그림이 1.7배가 되고 **라벨도 같이 커져** 본문 12.5px 를
#                         넘는다 — 고치려던 그 결함이 난다.
#
#                         🔴 **98 에서 멈춰 있던 이유는 배율이 아니라 «놀던 여백»이었다**
#                         (원장님 2026-08-29 「회전체도 등급 안 넘게 최대로 키워봐」).
#                         `_fitted_cabinet` 은 도형 꼭짓점 + **고정 여백**만 보고
#                         라벨을 안 본다. 그래서 라벨이 안 서는 쪽 여백이 통째로 놀았다 —
#                         실측으로 원기둥 오른쪽 22.8, 구멍 원기둥 왼쪽 21.0. 그 여백을
#                         내용에 맞춰 줄이니 같은 160 안에서 도형이 **+15.0%** 커졌다.
#                         쓸기: `.tmp-orca/sweep2.py` (등급 변화 0 · 새 잘림 0 을 전량 확인).
DIM_FS = 10.5           # 치수 라벨 글자 크기 (종전 12)
_DIM_PAD_K = DIM_FS / 12.0


def _dim_pads(pads: tuple[float, float, float, float]) -> tuple[float, ...]:
    """치수 라벨이 앉을 여백 — **라벨 크기에 비례**한다.

    여백은 라벨을 담으려고 잡은 값이다(직육면체 계열은 viewBox 폭의 **64%** 가 여백이었다).
    라벨을 줄이면서 여백을 그대로 두면 도형만 작아 보이고, 배율을 올린 만큼 viewBox 가
    커져 인쇄 등급을 넘는다.
    """
    return tuple(round(v * _DIM_PAD_K, 1) for v in pads)


# ⚠️ **여백을 도형에 비례시켜 보는 대안은 재 보고 버렸다.** 여백을 그대로 두고
#    배율만 72/88 로 낮추면(등급은 안 넘는다) 겹침은 **똑같이 5** 인데 비가
#    12.1 → 10.4 로 내려가고, `cutCuboid` 의 `4 cm` 가 도형에서 **뚝 떨어져**
#    지시선이 그림을 가로지른다(눈으로 확인). 라벨은 «밖»보다 «가까이»가 낫다 —
#    정본도 `7 cm` 하나는 홈 속에 halo 로 얹는다.

FILL = "#e2b48a"
FAINT = "#f4efe6"
FACE_TOP = "#f2e6d4"
FACE_FRONT = "#e4d3b8"
FACE_SIDE = "#d4c09e"
CHART = ("#c5d6c2", "#d7c2e4", "#e2b48a", "#c5d4e8", "#e8d4a8", "#d4c0b0")
# 겨냥도 숨은 모서리. 실선과 눈에 띄게 갈려야 면·모서리를 셀 수 있다 (09 §4-14).
HIDDEN_DASH = "5 4"
# 둥근 입체(원기둥·원뿔·**구**) 타원의 납작한 정도(ry/rx).
# 사방(45°) 투영은 타원이 기울어 「타원기둥」처럼 보인다 — 깊이축을 화면 위(90°)로
# 세우면 축에 나란한 타원이 되고 depth_ratio 가 곧 ry/rx 가 된다 (09 §4-15).
#
# **0.15 — 원장님 확정 2026-08-22**: 「강력하게 조여. 절대 초등과정에서 원기둥 원뿔
# 구에서 타원이 그려지지 않도록」. 0.30·0.20·0.15·0.12 를 셋 다 렌더해 견주고 고르셨다
# (`scripts/qa/shot-round-ratio.py` 로 다시 낼 수 있다). 0.12 는 납작한 원기둥이
# 직사각형처럼 보이고 구 적도가 거의 직선이 된다 — 그게 하한이다 (09 §4-20-d).
#
# ⚠️ **셋이 이 한 숫자를 쓴다.** 예전에는 구만 날 리터럴 `0.32` 라 상수를 조여도
#    구는 안 따라왔다 — 게다가 셋 중 **가장 뚱뚱한 것**이 안 고쳐지고 남았다
#    (2026-08-18 「배선이 한쪽만 되면 그쪽 지표만 좋아진다」).
ROUND_RATIO = 0.15
ROUND_DEG = 90.0

# 세로 눈금 걸음 사다리 — `1·2·5` 를 열 배씩. 초등에서 「한 칸이 몇인가」를 암산할 수
# 있는 것은 이 셋뿐이다(3칸·7칸은 눈금을 세게 만든다).
NICE_STEPS: tuple[int, ...] = tuple(m * 10**k for k in range(5) for m in (1, 2, 5))
# 0 을 포함한 세로 눈금 줄 수 상한.
#
# ⚠️ **9 는 「읽기 좋은 수」가 아니라 「지금 규칙이 내는 최대」다.** `y_max = 8` 은
#    걸음 1로 0~8 아홉 줄을 낸다 — 상한을 8로 두면 그 장들이 같이 바뀐다. 상한은
#    **결함(눈금 과밀)만 걸러야** 하고 멀쩡한 장을 건드리면 안 된다. 실측: 이 값을
#    8로 낮추면 **지금 결함이 없는 장 829장**(2,400장 중)이 같이 바뀌고, 7이면
#    1,123장이 바뀐다. 9에서는 0장이다 — 그래서 9다.
#    (잰 자: `scripts/qa/measure-elem-charts.py`, 씨앗 400 · 그래프 2,400장)
MAX_Y_TICKS = 9


def _int(value: Any, name: str, lo: int, hi: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
        raise ValueError(f"{name} 은 정수여야 합니다")
    n = int(value)
    if n < lo or n > hi:
        raise ValueError(f"{name} 은 {lo} 이상 {hi} 이하여야 합니다")
    return n


def _num(value: Any, name: str, lo: float, hi: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} 은 수여야 합니다")
    n = float(value)
    if n < lo or n > hi:
        raise ValueError(f"{name} 은 {lo} 이상 {hi} 이하여야 합니다")
    return n


def _poly(pts: list[tuple[float, float]], fill: str, sw: float = 1.3) -> str:
    s = " ".join(f"{_n(x)},{_n(y)}" for x, y in pts)
    return f'<polygon points="{s}" fill="{fill}" stroke="{INK}" stroke-width="{_n(sw)}"/>'


def _line(a: tuple[float, float], b: tuple[float, float], sw: float = 1.3, dash: str | None = None) -> str:
    d = f' stroke-dasharray="{_esc(dash)}"' if dash else ""
    return (
        f'<line x1="{_n(a[0])}" y1="{_n(a[1])}" x2="{_n(b[0])}" y2="{_n(b[1])}" '
        f'stroke="{INK}" stroke-width="{_n(sw)}"{d}/>'
    )


def _polyline(
    pts: list[tuple[float, float]],
    *,
    sw: float = 1.15,
    dash: str | None = None,
) -> str:
    s = " ".join(f"{_n(x)},{_n(y)}" for x, y in pts)
    d = f' stroke-dasharray="{_esc(dash)}"' if dash else ""
    return (
        f'<polyline points="{s}" fill="none" stroke="{INK}" '
        f'stroke-width="{_n(sw)}"{d}/>'
    )


def _frac_bars(spec: Mapping[str, Any]) -> str:
    cols = _int(spec["cols"], "cols", 2, 16)
    rows = _int(spec["rows"], "rows", 1, 8)
    filled_raw = spec["filled"]
    total = cols * rows
    if isinstance(filled_raw, (int, float)) and not isinstance(filled_raw, bool):
        nfill = _int(filled_raw, "filled", 0, total)
        filled = set(range(nfill))
    elif isinstance(filled_raw, list):
        filled = set()
        for item in filled_raw:
            filled.add(_int(item, "filled", 0, total - 1))
    else:
        raise ValueError("filled 는 개수 또는 칸 번호 배열이어야 합니다")
    fill_on = str(spec.get("fill") or FILL)
    pad = 8.0
    box_w = TABLE_VIEWBOX_MAX - pad * 2
    cw = box_w / cols
    ch = 22.0
    gap = 4.0
    parts: list[str] = []
    for r in range(rows):
        for c in range(cols):
            i = r * cols + c
            x = pad + c * cw
            y = pad + r * (ch + gap)
            fill = fill_on if i in filled else FAINT
            parts.append(_rect(x + 0.5, y, cw - 1, ch, sw=1.05, fill=fill))
    h = pad * 2 + rows * ch + (rows - 1) * gap
    return _svg(TABLE_VIEWBOX_MAX, h, "".join(parts))


# 항목의 허용 키. 오타가 조용히 무시되면 「지웠는데 왜 그대로냐」가 된다 (namedShapes 와 같다).
_VALUE_ITEM_KEYS = frozenset({"label", "value", "unknown"})

# 🔴 **「이 차트가 «가려진 값»을 받는가」는 여기서 한 번만 정한다.**
#
# 예전에는 `_bar_chart` 만 `allow_unknown=True` 를 손으로 넘기고 `_line_chart` 는 안
# 넘겼다. 값은 맞았지만 **자리가 둘**이라, 세 번째 차트 종류가 생기면 같은 구멍이 또
# 열린다 — 새 차트를 만드는 사람이 **이 축이 있다는 것조차 모르기 때문**이다.
# (2026-08-23 실측: 저장소 전체에서 `allow_unknown=True` 는 호출부 **한 곳**뿐이었고,
#  그 한쪽을 만든 것이 이 세션이다. 막대에 넣으면서 꺾은선을 안 봤다.)
#
# 「같은 규칙을 쓰는 자리가 둘이면 **한 숫자를 두 곳이 쓰게** 하고, 한쪽만 옮기면
#  빨개지는 시험을 같이 둘 것」(CLAUDE.md 2026-08-18) — 그 후반부가 `mutate-elem-figure.sh`
#  의 「호출부가 표를 안 읽는다」 변이와 `probe-chart-unknown.py` 다.
#
# ⚠️ **꺾은선을 `True` 로 바꾸는 것만으로는 안 열린다.** 렌더러가 「값 없는 점」의 y 를
#    못 정해 죽는다. 그것은 지면 모양 결정(D-07)이라 여기 밖이다 — 표만 바꾸지 말 것.
CHART_ACCEPTS_UNKNOWN: dict[str, bool] = {
    "barChart": True,  # 점선 상자로 값 축 전체를 두른다 (D-72 자료형 심화)
    "lineChart": False,  # 점을 못 찍는다 — 지면 모양이 아직 안 정해졌다
}


def _chart_values_of(
    kind: str, raw: Any, name: str
) -> list[tuple[str, float | None]]:
    """차트 종류로 «가려진 값» 허용 여부를 **표에서 찾아** 값을 읽는다.

    호출부가 `allow_unknown` 을 손으로 정하지 않게 하는 것이 목적이다.
    표에 없는 종류는 **던진다** — 조용히 `False` 로 두면 새 차트가 이 축을 모른 채
    지나가고, 그것이 정확히 지난번 결함의 모양이다.
    """
    if kind not in CHART_ACCEPTS_UNKNOWN:
        raise ValueError(
            f"«{kind}» 가 가려진 값을 받는지 안 정해졌습니다 — "
            f"CHART_ACCEPTS_UNKNOWN 에 적으십시오"
        )
    return _chart_values(raw, name, allow_unknown=CHART_ACCEPTS_UNKNOWN[kind])


def _chart_values(
    raw: Any, name: str, allow_unknown: bool = False
) -> list[tuple[str, float | None]]:
    """항목 목록. 값이 `None` 이면 **지워진 막대**(unknown)다 (D-72 자료형 심화).

    ## 참값을 스펙에 싣지 않는다

    「지워진 막대의 값을 역산하라」가 문제인데 스펙이 그 값을 들고 있으면 **그림이 답을
    흘린다**(D-66 ⑺). 그래서 unknown 항목에는 `value` 자체가 **없어야** 하고, 같이 오면
    던진다 — 나중에 누가 「편의로」 되살리는 것을 막는 자리다.
    숨긴 값이 무엇이든 점선 상자가 똑같이 그려지는 것은 **값이 아예 없으니 자동으로 참**이다.

    ## 값이 하나도 없으면 못 그린다

    축 맨 위를 정할 근거가 사라진다 — 조용히 1로 두지 않고 던진다.
    """
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{name} 는 비어 있지 않은 배열이어야 합니다")
    if len(raw) > 8:
        raise ValueError(f"{name} 는 8개 이하여야 합니다")
    out: list[tuple[str, float | None]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise ValueError(f"{name}[{i}] 는 객체여야 합니다")
        extra = set(item) - _VALUE_ITEM_KEYS
        if extra:
            raise ValueError(
                f"{name}[{i}] 에 허용되지 않은 키: {', '.join(sorted(str(k) for k in extra))}"
            )
        label = str(item.get("label", ""))
        if "unknown" in item:
            if item["unknown"] is not True:
                raise ValueError(f"{name}[{i}].unknown 은 true 만 쓸 수 있습니다")
            if not allow_unknown:
                raise ValueError(f"{name}[{i}] — 이 그림은 지워진 막대를 그리지 못합니다")
            if "value" in item:
                raise ValueError(
                    f"{name}[{i}] 는 unknown 인데 value 가 있습니다 — "
                    f"참값을 스펙에 실으면 그림이 답을 흘립니다"
                )
            out.append((label, None))
            continue
        out.append((label, _num(item.get("value"), f"{name}[{i}].value", 0, 10000)))
    if all(v is None for _, v in out):
        raise ValueError(f"{name} 에 값이 하나도 없습니다 — 축 맨 위를 정할 수 없습니다")
    if max(v for _, v in out if v is not None) <= 0:
        # 「0명」 하나는 정당한 자료지만 **전부 0이면 막대가 하나도 안 그려진다** —
        # 읽을 것이 없는 그림이다. `yMax` 가 있어도 마찬가지라 여기서 막는다.
        raise ValueError(f"{name} 의 값이 전부 0입니다 — 막대가 하나도 안 그려집니다")
    return out


def _y_step(y_max: float) -> int:
    """세로 눈금 한 칸.

    지금 규칙(`≤8→1` · `≤12→2` · 그 위 `5`)을 **바닥**으로 깔고, 그 걸음이 눈금을
    `MAX_Y_TICKS` 줄보다 많이 만들 때에만 사다리를 올린다 — **넘칠 때만 키운다.**

    ⚠️ 「5~8줄이 읽기 좋다」로 걸음을 다시 고르면 **지금 잘 나오는 장이 같이 바뀐다**
    (`y_max` 15·16·17 은 지금 4줄인데 그 규칙이면 8~9줄이 된다). 결함이 아닌 장을
    바꾸는 것은 수리가 아니라 **다른 그림으로 갈아 끼우는 것**이라, 원장님 확정
    없이는 못 한다(D-07). 그래서 상한만 두고 나머지는 손대지 않는다 (09 §4-23).

    사다리는 `1·2·5` 를 열 배씩 — 그 셋 말고는 「한 칸이 몇인가」가 암산이 안 된다.
    """
    base = 1 if y_max <= 8 else (2 if y_max <= 12 else 5)
    for step in NICE_STEPS:
        if step >= base and _tick_count(y_max, step) <= MAX_Y_TICKS:
            return step
    return NICE_STEPS[-1]


def _tick_count(axis_top: float, step: int) -> int:
    """0 을 포함한 눈금 줄 수 — `_plot_axes` 의 고리가 실제로 그리는 수와 같아야 한다."""
    return int(math.floor(axis_top / step + 1e-9)) + 1


def _axis_top(
    y_max: float, data_max: float, y_step: int | None = None
) -> tuple[float, int]:
    """축 맨 위와 걸음.

    ## `yStep` 이 오면 **그 걸음 그대로 긋는다** (D-70)

    「눈금 한 칸은 몇 명인가」 유형은 발문이 걸음을 말한다. 그 값을 여기서 다시
    고르면 **발문이 그림과 다른 말을 한다** — D-67 이 그 유형을 통째로 뺐던 이유다.
    그래서 `yStep` 이 있으면 사다리를 **안 탄다.** 축을 올려야 하면 걸음은 그대로 두고
    **눈금 수만** 늘린다.

    ⚠️ **그 걸음으로 못 그리면 던진다.** 조용히 사다리로 올리면 발문이 「한 칸 5명」인데
    그림은 10명 간격이 된다 — 에러도 안 나고 학생만 틀린다. TS 가 옳게 정하면 안 밟는
    경로지만, **방어는 침묵이 아니라 던짐이다.**

    ## `yStep` 이 없으면 (기존 그대로)

    **`yMax` 는 「진실」이 아니라 「최소 높이 요청」이다.** 걸음을 아는 쪽은 여기이므로,
    맨 위 눈금선이 데이터보다 낮으면(=제일 높은 점이 눈금 밖으로 뜨면) 여기서 올린다.
    실측으로 꺾은선 `yMax = 최댓값 + 3` 은 최댓값이 5로 나눠 1이 남을 때마다 떴다
    (2,400장 중 214장). 하필 그 점이 「가장 많은 때는 언제인가」의 답이다.

    올리면 걸음이 다시 커질 수 있고, 걸음이 커지면 필요한 높이가 또 달라진다 —
    그래서 **더 안 움직일 때까지** 되풀이한다. 한 번만 돌면 `yMax 44 · 값 44` 가
    45(걸음 10, 맨 위 눈금 40)에서 멈춰 **값 44가 다시 뜬다**(실측: 6,000칸 중 1,119칸).

    `max(...)` 라서 **필요 없으면 아무것도 안 올린다** — 지금 맞게 나오는 장은
    `y_max` 도 걸음도 그대로고, 따라서 픽셀도 그대로다.

    ⚠️ **못 끝나면 조용히 도는 대신 던진다.** 고리가 안 끝나는 것은 걸음이 사다리를
    한 칸씩만 올라간다는 전제가 깨졌다는 뜻이고, 그때 마지막 값을 그냥 돌려주면
    **눈금과 데이터가 어긋난 그림이 조용히 지면으로 나간다.** 입력 전 범위
    (`yMax` 1~10000 × 데이터 5종 = 50,000칸)에서 여기 닿는 조합은 없다.
    """
    top = max(float(y_max), 1.0)
    if y_step is not None:
        # 걸음이 요청한 높이보다 크면 **부르는 쪽이 스스로 어긋난 것**이다 — 「8까지
        # 그려 달라」면서 「한 칸은 100」이라 한 셈. 그대로 그리면 눈금이 0과 100 둘뿐이고
        # 막대가 바닥에 깔린다(231줄과 **반대 방향의 같은 병**). 문턱을 지어낸 게 아니라
        # 부르는 쪽이 준 두 수를 견준 것이다.
        if y_step > y_max:
            raise ValueError(
                f"yStep {y_step} 이 yMax {y_max:g} 보다 큽니다 — 눈금이 데이터를 못 가릅니다"
            )
        need = math.ceil(data_max / y_step - 1e-9) * y_step if data_max > 0 else 0.0
        top = max(top, float(need))
        ticks = _tick_count(top, y_step)
        if ticks > MAX_Y_TICKS:
            raise ValueError(
                f"yStep {y_step} 으로는 눈금이 {ticks}줄이 됩니다 "
                f"({MAX_Y_TICKS}줄 이하여야 합니다. 축 맨 위 {top:g})"
            )
        return top, y_step
    # 사다리 칸을 한 번씩 다 밟아도 끝난다 — 같은 걸음이면 필요 높이가 그대로라
    # 다음 바퀴에서 반드시 돌아간다. +1 은 마지막 확인 한 바퀴.
    for _ in range(len(NICE_STEPS) + 1):
        step = _y_step(top)
        need = math.ceil(data_max / step - 1e-9) * step if data_max > 0 else 0.0
        if need <= top:
            return top, step
        top = float(need)
    raise ValueError(f"축 맨 위가 수렴하지 않습니다 (yMax={y_max}, 값 최댓값={data_max})")


def _y_step_spec(spec: Mapping[str, Any]) -> int | None:
    """스펙이 실어 온 눈금 걸음. 없으면 `None` — 그때만 `_y_step` 이 고른다 (D-70).

    「눈금 한 칸은 몇 명인가」 발문은 **TS 가 정한 걸음**을 말한다. 그 값을 여기서
    다시 고르면 발문과 그림이 갈린다.
    """
    if "yStep" not in spec:
        return None
    return _int(spec["yStep"], "yStep", 1, 10000)


# 세로축 단위 이름표는 맨 위 눈금보다 «한 줄 위»에 앉는다. 그 한 줄이 이 값이다.
UNIT_LABEL_DROP = 20.0
UNIT_LABEL_SIZE = 13.0


def unit_label_min_top() -> float:
    """세로축 단위를 넣을 때 **맨 위 눈금이 내려와 있어야 할 최소 높이**.

    ⚠️ 이름표는 `dominant-baseline="middle"` 이라 닻점 위아래로 글자가 반씩 걸친다.
       `_svg` 는 닻점만 보므로 이 몫을 부르는 쪽이 안 빼면 **프레임 위로 잘린다**
       — `_scatter_plot` 이 실제로 그랬다(원장님 지적 2026-08-25).
       그래서 「한 줄 위」를 눈대중으로 적지 않고 **여기서 계산**해 나눠 쓴다.
    """
    return UNIT_LABEL_DROP + UNIT_LABEL_SIZE * 0.56 + FIT_PAD


def _unit_label(left: float, top: float, ylab: str) -> str:
    """세로축 단위는 눈금과 같은 열, 맨 위 눈금보다 한 줄 위.

    🔴 **왼쪽 여백은 눈금 «숫자» 폭으로 정해진다** — 단위 이름표는 그 계산에
       들어 있지 않다. 그래서 `(원)`(29.2단위)처럼 숫자보다 넓은 이름표는
       왼쪽 끝을 **넘어가 잘렸다**(실측 -3.43단위, 짝 그래프). `_svg` 가
       글자를 닻점으로만 세던 시절에는 에러도 안 났다.

       이름표는 맨 위 눈금보다 **한 줄 위**에 있어 오른쪽으로 밀어도 눈금
       숫자와 겹치지 않는다. 그래서 여기서 **못 나가게 붙든다** —
       열 정렬이 조금 어긋나는 것보다 글자가 잘리는 편이 나쁘다.
    """
    if not ylab:
        return ""
    x = max(left - 7, _label_w_max(ylab, UNIT_LABEL_SIZE))
    return _text(x, top - UNIT_LABEL_DROP, ylab, size=UNIT_LABEL_SIZE, anchor="end")


# 눈금 숫자 한 자의 폭(그림 단위, 14pt). **실측값이다** — 지면과 같은 렌더러
# (헤드리스 Chromium)에서 `getComputedTextLength()` 로 쟀다:
#   `0`8.62 · `20`17.21 · `500`25.83 · `1000`34.42 → 전부 8.605/자
# Batang bold 는 숫자가 고정폭이라 «자당 폭 × 자릿수» 가 어림이 아니라 정확하다.
# 파이썬에는 글꼴 계측이 없어서 리터럴 말고는 방법이 없다.
# ⚠️ 글꼴을 바꾸면 이 값을 **다시 재야 한다**(`scripts/qa/…` 시안의 measure-text.mjs).
TICK_DIGIT_W = 8.605
# 마지막 눈금 숫자와 단위 라벨 사이 틈. 지면에서 약 1.4mm.
UNIT_GAP = 6.0
# 이웃한 값 눈금 숫자 사이 최소 틈.
TICK_MIN_GAP = 3.0
# 지워진 막대(unknown)의 점선. 숨은 모서리(`5 4`)와 **다른 무늬**여야 한다 —
# 겨냥도 점선과 같은 그림에 함께 나오지는 않지만, 뜻이 다르면 무늬도 달라야 헷갈리지 않는다.
UNKNOWN_DASH = "4 3"

# ── 그래프 짝 (chartPair) ────────────────────────────────────────────────────
# 두 그래프 사이 틈.
PAIR_GAP = 10.0
# 짝이 화면에서 차지하는 폭(px)과 지면 폭(mm).
#
# ⚠️ **이 두 수는 `src/lib/figure/figureSvgFrame.ts` 와 반드시 같아야 한다.**
#    거기서 정한 폭으로 그려지는데 여기서 다른 수로 판정하면, 가드가 통과시킨 그림이
#    지면에서는 글자가 작아진다. `elementaryFigure.test.ts` 가 **두 파일의 숫자가
#    같은지** 대조한다(한쪽만 고치면 빨개진다).
#    근거: 문항 열 폭 실측 363.5px(`printGeometry.ts` `problemColumn`)과
#    그 지면 환산 96.9mm(= 363.5 ÷ 3.75px/mm, 중간 등급 240px/64mm 에서 나온 배율).
PAIR_FRAME_PX = 364.0
PAIR_FRAME_MM = 97.0
# 문항 본문 글자 크기(px). `printGeometry.ts` 의 `line` 20.3125 = 12.5 × 1.625.
# **눈금 글자가 이보다 작아지면 안 된다** — 원장님이 내건 조건이다.
BODY_TEXT_PX = 12.5
# 눈금 글자 크기(그림 단위). `_plot_axes` 가 실제로 쓰는 값과 같아야 한다.
TICK_FONT = 14.0

_SVG_SPLIT = re.compile(r'^<svg viewBox="0 0 ([0-9.]+) ([0-9.]+)"[^>]*>(.*)</svg>$', re.S)


def _fixed_width_svg(width: float, height: float, body: str, what: str, hint: str) -> str:
    """**폭을 박아** 내보낸다. 벌어졌으면 던진다.

    `_svg` 는 그린 것이 넘치면 viewBox 를 **넓혀** 준다. 잘림을 막는 좋은 성질이지만,
    폭이 곧 지면 등급(≤160 → 140px · ≤320 → 240px)인 kind 에서는 넓어지는 순간
    **그 그림만 화면에서 작아지고 아무 에러도 안 난다**(09 §4-24 ㉠).

    ⚠️ 폭을 박는 kind 가 셋(통계·좌표평면·원뿔 전개도)이라 **여기 한 곳**만 본다 —
       각자 적으면 한쪽만 고쳐진다(2026-08-18 「한 숫자를 두 곳이 쓰게 하라」).

    🔴 **그리고 글자가 프레임 밖으로 나가는지도 여기서 본다** (2026-08-25).
       종전에는 이 자리에 「`_svg` 는 닻점만 세므로 글자 폭은 여기 안 잡힌다 —
       그 몫은 부르는 쪽이 재서 미리 빼야 한다」고만 적혀 있었다. 그 말은 **옳지만
       아무도 지키는지 확인하지 않았다**: `_scatter_plot` 이 x축 단위 이름표 몫을
       안 빼고 있었고(`_stat_frame`·`_box_plot` 은 빼고 있었다), y축 단위는
       프레임 위로 반쯤 나가 있었다. 그림은 그냥 잘렸고 **에러는 안 났다**
       (원장님 지적 2026-08-25 `J30702-A03-002`·`A04-002`).

       그래서 「부르는 쪽이 알아서」를 **검사로 바꾼다.** 폭은 늘리면 지면 등급이
       뒤집히므로(위 문단) 늘리지 않고 **던진다** — 조용한 잘림보다 시끄러운 실패다.
    """
    svg = _svg(width, height, body)
    m = _SVG_SPLIT.match(svg)
    if m is None:  # pragma: no cover — 우리 렌더러 산출물이라 늘 맞는다
        raise ValueError(f"{what} SVG 를 읽지 못했습니다")
    got = float(m.group(1))
    if abs(got - width) > 0.51:
        raise ValueError(
            f"{what} 폭이 {got:.0f}단위로 벌어졌습니다 ({width:.0f} 이어야 합니다) — "
            f"지면 등급이 바뀝니다. {hint}"
        )
    got_h = float(m.group(2))
    for x0, y0, x1, y1, text in _text_bboxes(m.group(3)):
        if x0 < -0.51 or x1 > got + 0.51 or y0 < -0.51 or y1 > got_h + 0.51:
            raise ValueError(
                f"{what} 의 글자 「{text}」가 프레임 밖으로 나갑니다 "
                f"(글자 {x0:.0f}~{x1:.0f} × {y0:.0f}~{y1:.0f}, "
                f"프레임 {got:.0f}×{got_h:.0f}) — {hint}"
            )
    return svg


def _assert_ticks_readable(total_w: float) -> None:
    """짝이 화면에서 줄어든 뒤에도 **눈금 글자가 본문 이상**인가.

    참을 어림으로 만들지 않는다 — 그림을 그리는 그 상수들(`TICK_FONT`·`PAIR_FRAME_PX`)과
    실제 합성 폭에서 바로 계산한다. 따로 세워 둔 추정치를 쓰면 그림과 판정이 갈린다.
    """
    px = TICK_FONT * PAIR_FRAME_PX / total_w
    if px < BODY_TEXT_PX:
        raise ValueError(
            f"짝이 {total_w:.0f}단위라 눈금 글자가 화면에서 {px:.2f}px 이 됩니다 "
            f"(본문 {BODY_TEXT_PX}px 이상이어야 합니다). 값을 줄이거나 걸음을 키우십시오"
        )


def _digits_half(value: int) -> float:
    """눈금 숫자가 가운데 정렬이라 **오른쪽으로 뻗는 만큼**(폭의 절반)."""
    return TICK_DIGIT_W * len(str(int(value))) / 2


def _assert_ticks_fit(ticks: list, plot_w: float, intervals: int | None = None) -> None:
    """가로형 값 눈금이 **옆으로 늘어서므로** 숫자끼리 겹칠 수 있다.

    ⚠️ `intervals` — 눈금 **사이 칸의 수**. 안 주면 `len(ticks) - 1` 로 본다(눈금이
    칸을 꽉 채우는 경우). 도수분포다각형처럼 **눈금 밖으로 칸이 더 있는** 그림은
    그 수가 다르다 — 짐작한 분모로 재면 간격을 실제보다 넓게 봐서 겹침을 놓친다
    (2026-08-17 「임계값을 물려받을 때는 분모가 같은지부터 볼 것」).

    세로형은 눈금이 위아래로 쌓여 이 결함이 없다 — **방향이 만드는 차이**다.
    실측(커밋 7d3edc42): 값 축 140단위에 세 자리 눈금 9개를 그리면
    「0100200300…」처럼 **읽을 수 없는 덩어리**가 된다. 에러도 안 나고 지면에만 나간다.

    조용히 겹치게 두지 않고 **던진다** — 상한은 우리가 아니라 엔진이 정한다
    (`yStep` 9줄 상한과 같은 무늬, D-70).
    """
    if len(ticks) < 2:
        return
    widest = TICK_DIGIT_W * max(len(str(t)) for t in ticks)
    pitch = plot_w / (len(ticks) - 1 if intervals is None else intervals)
    if pitch < widest + TICK_MIN_GAP:
        raise ValueError(
            f"값 축 {plot_w:g} 단위에 눈금 {len(ticks)}개를 그리면 숫자가 겹칩니다 "
            f"(간격 {pitch:.1f} · 숫자 폭 {widest:.1f}). 걸음을 키우거나 값을 줄이십시오"
        )


def _tick_values(axis_top: float, step: int) -> list[int]:
    """0부터 `axis_top` 까지 `step` 마다. **방향과 무관하다** — 값 축의 눈금은 하나다.

    가로형·세로형이 각자 눈금을 세면 규칙이 두 벌이 되어 한쪽만 고쳐진다
    (2026-08-18 「같은 규칙을 쓰는 자리가 둘이면 한 숫자를 두 곳이 쓰게 하라」).
    """
    out: list[int] = []
    v = 0
    while v <= axis_top + 1e-6:
        out.append(v)
        v += step
    return out


def _plot_axes(
    left: float,
    top: float,
    plot_w: float,
    plot_h: float,
    axis_top: float,
    step: int,
    horizontal: bool = False,
) -> list[str]:
    """축 두 줄과 **값 축**의 눈금.

    `axis_top` 과 `step` 은 **둘 다 `_axis_top()` 이 낸 것을 그대로** 받는다.
    막대·꺾은선의 배율도 같은 `axis_top` 을 써야 한다 — 안 그러면 눈금과 데이터가
    다른 자로 그려진다(변이 ㉕·㉖).

    ⚠️ **여기서 `_y_step` 을 다시 부르면 안 된다.** 그러면 스펙이 실어 온 `yStep` 이
    조용히 무시되어 「한 칸 5명」 발문 옆에 10명 간격이 그려진다 (D-70).

    `horizontal` 은 **값 축을 어느 화면 축에 눕히는가**만 바꾼다. 눈금 값 자체는
    `_tick_values` 하나가 낸다 — 방향마다 규칙이 갈리지 않는다.
    """
    parts = [
        _line((left, top), (left, top + plot_h)),
        _line((left, top + plot_h), (left + plot_w, top + plot_h)),
    ]
    for v in _tick_values(axis_top, step):
        if horizontal:
            x = left + plot_w * v / axis_top
            # 0 눈금은 세로축과 겹친다.
            if v > 0:
                parts.append(_line((x, top), (x, top + plot_h), sw=0.4, dash="3 3"))
            parts.append(_line((x, top + plot_h), (x, top + plot_h + 4), sw=0.9))
            parts.append(_text(x, top + plot_h + 14, str(v), size=14))
        else:
            y = top + plot_h - plot_h * v / axis_top
            # 0 눈금은 가로축과 겹친다. 흰 외곽선 halo 는 mix-blend-multiply 에서
            # 가장자리가 회색으로 뭉개지므로 쓰지 않는다.
            if v > 0:
                parts.append(_line((left, y), (left + plot_w, y), sw=0.4, dash="3 3"))
            parts.append(_line((left - 4, y), (left, y), sw=0.9))
            parts.append(_text(left - 7, y, str(v), size=14, anchor="end"))
    return parts


def _orient(spec: Mapping[str, Any]) -> bool:
    """가로형인가. 기본은 세로 — **없으면 지금 지면과 완전히 같다.**

    ⚠️ `yMax`·`yStep`·`yLabel` 은 화면의 세로축이 아니라 **값 축**을 가리킨다.
    가로형이면 그 축이 아래로 눕을 뿐 이름은 그대로다. **`valueMax` 로 «개선»하지 마라**
    — 한 가지에 이름이 둘이 되면 축 규칙을 고칠 때 한쪽만 고쳐진다
    (2026-08-18 「같은 규칙을 쓰는 자리가 둘이면 한 숫자를 두 곳이 쓰게 하라」).
    읽는 법: **y = 값 · x = 항목, 화면 방향과 무관.**
    """
    raw = spec.get("orient", "vertical")
    if raw not in ("vertical", "horizontal"):
        raise ValueError('orient 는 "vertical" 또는 "horizontal" 이어야 합니다')
    return raw == "horizontal"


def _chart_title(title: str, cx: float, plot_w: float, y: float = 16.0) -> str:
    """그래프 제목 — 값 축 눈금(14)보다 크지 않게, plot 가운데.

    ⚠️ **제목이 제 그래프보다 넓으면 던진다.** 짝으로 놓으면 옆 그래프를 침범하고,
    혼자여도 viewBox 밖으로 나가 잘린다. 긴 정보는 **발문 몫**이다 — 원장님 확정
    2026-08-23: 제목은 「팔린 수」·「한 개의 가격」처럼 짧게 쓰고, 「종류별 팔린
    아이스크림의 수」 같은 설명은 발문이 이미 하고 있다(실측 185.1단위로 폭을 넘겼다).
    """
    if not title:
        return ""
    want = _label_w_max(title, 14.0)
    if want > plot_w:
        raise ValueError(
            f"제목 「{title}」이 그래프 폭보다 넓습니다 ({want:.0f} > {plot_w:.0f}단위). "
            f"제목은 짧게 쓰고 설명은 발문에 두십시오"
        )
    return _text(cx, y, title, size=14)


def _bar_chart_h(
    spec: Mapping[str, Any], values, axis_top: float, step: int, compact: bool = False
) -> str:
    """가로 막대. 항목 라벨이 왼쪽, **값 축이 아래**로 눕는다.

    축 계산(`_axis_top`)은 세로형과 **같은 것을 이미 받아** 온다 — 여기서 다시 정하지
    않는다. 이 함수가 정하는 것은 «어디에 그리는가»뿐이다.
    """
    title = str(spec.get("title", ""))
    n = len(values)
    gap = 8.0
    if compact:
        # 짝으로 놓을 때는 **내용이 폭을 정한다** — 고정 폭이면 둘을 나란히 놓았을 때
        # 열을 넘겨 글자가 본문보다 작아진다(실측 498단위 · 10.24px).
        # 항목 라벨이 들어갈 만큼만 왼쪽을, 눈금 숫자가 안 겹칠 만큼만 값 축을 준다.
        ticks = _tick_values(axis_top, step)
        left = max(_label_w_max(str(lab)) for lab, _ in values) + 7
        widest = TICK_DIGIT_W * max(len(str(t)) for t in ticks)
        plot_w = (len(ticks) - 1) * (widest + TICK_MIN_GAP)
    else:
        left, plot_w = 60.0, 140.0
    top, plot_h = (34.0 if title else 16.0), 118.0
    pad_b = 34.0
    bh = (plot_h - gap * (n + 1)) / n
    _assert_ticks_fit(_tick_values(axis_top, step), plot_w)
    parts = _plot_axes(left, top, plot_w, plot_h, axis_top, step, horizontal=True)
    for i, (lab, val) in enumerate(values):
        y = top + gap + i * (bh + gap)
        if val is None:
            # 지워진 막대 — **값 축 전체**를 점선으로 두른다. 어떤 눈금에도 안 걸리므로
            # 그림이 답을 흘리지 않는다(D-66 ⑺). 항목마다 늘 같은 기하다.
            parts.append(_rect(left, y, plot_w, bh, fill="none", sw=1.05, dash=UNKNOWN_DASH))
            parts.append(_text(left + plot_w / 2, y + bh / 2, "?", size=16))
        else:
            w = 0 if axis_top <= 0 else min(plot_w, plot_w * val / axis_top)
            # 0 은 정당한 자료다. rect 를 **안 그린다** — 폭 0 은 정제기가 막는다
            # (`figure_quality` 의 「width must be positive」). 이름표 「0」은 그린다.
            if w > 0:
                parts.append(_rect(left, y, w, bh, fill=CHART[i % len(CHART)], sw=1.05))
            num = str(int(val)) if val == int(val) else _n(val)
            # 막대 안쪽이면 격자선과 안 겹친다. 짧은 막대만 바깥 오른쪽에 둔다.
            nx = left + w - 16 if w >= 34 else left + w + 12
            parts.append(_text(nx, y + bh / 2, num, size=16))
        parts.append(_text(left - 7, y + bh / 2, lab, size=13, anchor="end"))
    ylab = str(spec.get("yLabel", ""))
    # 단위 라벨은 **오른쪽 끝**에 오므로 viewBox 를 넘으면 잘린다. `_svg` 의 맞춤은
    # 글자 «닻»만 보고 뻗는 폭은 모르므로 여기서 넉넉히 잡아 준다 — 실측으로 세 자리
    # 눈금에서 2.4단위, 네 자리에서 6.8단위가 잘리고 있었다(닫는 괄호가 사라졌다).
    # 짝으로 놓을 때는 **내용이 폭을 정한다**. 혼자 쓸 때는 240 이 기준이고
    # 넘칠 때만 넓힌다(지금 지면과 같은 크기를 유지하려고).
    width = (left + plot_w + 4) if compact else TABLE_VIEWBOX_MAX
    if ylab:
        # 마지막 눈금 숫자 바로 뒤 — 교과서가 「0 20 40 (개)」로 적는 자리다.
        #
        # ⚠️ **마지막 눈금 숫자는 축 끝에 «가운데» 정렬이라 오른쪽으로 절반을 더 뻗는다.**
        # 축 끝 + 6 에 그냥 놓으면 겹친다 — `yStep` 을 실으면 맨 위 눈금이 축 끝에
        # 딱 떨어지는 것이 보통이라 **D-70 유형에서는 거의 항상** 겹쳤다
        # (실측: 2자리 −2.60단위 · 3자리 −6.91단위, 커밋 7d3edc42).
        # 세로형은 단위가 축 **위**(`top-20`)라 이 결함이 없다 — 줄이 다르기 때문이다.
        last = _tick_values(axis_top, step)[-1]
        unit_x = left + plot_w + _digits_half(last) + UNIT_GAP
        parts.append(_text(unit_x, top + plot_h + 14, ylab, size=13, anchor="start"))
        width = max(width, unit_x + _label_w_max(ylab) + 4)
    parts.append(_chart_title(title, left + plot_w / 2, plot_w))
    return _svg(width, top + plot_h + pad_b, "".join(parts))


def _chart_pair(spec: Mapping[str, Any]) -> str:
    """그래프 둘을 **옆으로 나란히** (D-70 계열, 원장님 확정 2026-08-23).

    두 그래프에서 같은 항목의 값을 읽어 곱하는 유형(「멜론이 팔린 수 × 멜론 한 개의 값」)
    에 쓴다. **안쪽 스펙은 단독으로 쓸 때와 완전히 같은 모양**이고, 여기서는 배치만 한다.

    ## 규칙을 두 벌로 만들지 않는다

    안쪽은 `render_elementary` 로 **같은 검증·같은 렌더 함수**를 탄다. 좌표만 옮겨 붙이므로
    (`transform` 은 `sanitize_svg` 가 막는다) 축 규칙·겹침 가드가 그대로 적용된다.
    안쪽이 던지면 **그대로 올려 보낸다** — 삼키면 그 그래프만 조용히 빠진다.

    ## 눈금 글자가 본문보다 작아지면 안 된다

    짝은 폭이 두 배라 화면에서 축소된다. 그 축소율이 눈금 글자를 본문(12.5px) 아래로
    끌어내리면 **던진다.** 실측으로 짝은 405단위 · 12.56px 이라 여유가 0.06px 뿐이고,
    그 값을 정하는 것이 `TICK_MIN_GAP` 이다 — 상수가 움직이면 이 가드가 빨개진다.
    """
    from elementary import validate_elementary  # 순환 import 라 여기서

    charts = spec["charts"]
    if not isinstance(charts, list) or len(charts) != 2:
        raise ValueError("charts 는 그래프 스펙 2개여야 합니다")
    boxes: list[tuple[float, float, str]] = []
    for i, inner in enumerate(charts):
        if not isinstance(inner, Mapping):
            raise ValueError(f"charts[{i}] 는 객체여야 합니다")
        if inner.get("kind") not in ("barChart", "lineChart"):
            raise ValueError(f"charts[{i}].kind 는 barChart 또는 lineChart 여야 합니다")
        # 검증은 **단독 스펙과 같은 것**을 탄다 — 짝 안에서만 오타 키가 통과하면 안 된다.
        # 그린 뒤에는 «좁게»(compact) 라 폭을 내용이 정한다. 안쪽이 던지면 그대로 전파.
        kind = validate_elementary({**inner, "version": "elem-1"})
        svg = ADV_RENDER[kind]({**inner, "version": "elem-1"}, compact=True)
        m = _SVG_SPLIT.match(svg)
        if m is None:  # pragma: no cover — 우리 렌더러 산출물이라 늘 맞는다
            raise ValueError("그래프 SVG 를 읽지 못했습니다")
        boxes.append((float(m.group(1)), float(m.group(2)), m.group(3)))

    total_w = boxes[0][0] + PAIR_GAP + boxes[1][0]
    total_h = max(b[1] for b in boxes)
    _assert_ticks_readable(total_w)
    # 아래를 맞춘다 — 두 그래프의 가로축이 같은 줄에 와야 견주기 쉽다.
    body = "".join(
        _shift_body(b, x, total_h - b_h)
        for x, (b_w, b_h, b) in zip((0.0, boxes[0][0] + PAIR_GAP), boxes)
    )
    # 🔴 **화면 폭 등급을 정하는 표식.** 지면 쪽(`figureSvgFrame.ts`)이 이것을 **먼저**
    #    보고 `pair`(문항 열 전체)로 보낸다. 폭으로는 못 가른다 — 실측에서 짝
    #    273.21~359.61 과 단독 `cuboid` 128.17~324.97 이 **겹친다**(2026-08-23).
    #    종전 규칙(viewBox > 380)은 짝이 380 을 한 번도 안 넘어 **구조적으로 0**이었고,
    #    그래서 파이썬 가드(`_assert_ticks_readable`, PAIR_FRAME_PX=364)는 통과시키는데
    #    지면은 `mid`(240px)로 그려 눈금 글자가 최악 11.45px 이 됐다(본문 12.5px 미만).
    #
    #    ⚠️ `sanitize_svg` 는 `desc` 를 허용하지만 **속성은 하나도 안 받는다**
    #       (`_ALLOWED_TAGS` · `"desc": frozenset()`). 빈 태그로만 쓴다.
    #    ⚠️ 이 문자열은 `figureSvgFrame.ts` 의 `PAIR_DESC` 와 **같아야 한다.**
    #       한쪽만 고치면 짝이 조용히 `mid` 로 돌아간다 — 시험이 양쪽을 대조한다.
    return _svg_raw(total_w, total_h, "<desc>chartPair</desc>" + body)


def _bar_chart(spec: Mapping[str, Any], compact: bool = False) -> str:
    # 「가려진 값을 받는가」는 **여기서 정하지 않는다** — `CHART_ACCEPTS_UNKNOWN` 이 정한다.
    values = _chart_values_of("barChart", spec["values"], "values")
    data_max = max(v for _, v in values if v is not None)
    y_max = _num(spec.get("yMax", data_max or 1), "yMax", 1, 10000)
    # 축 규칙은 **방향보다 위**에 있다 — 사다리·9줄·yStep·인상·던짐이 한 벌뿐이다.
    axis_top, step = _axis_top(y_max, data_max, _y_step_spec(spec))
    if _orient(spec):
        return _bar_chart_h(spec, values, axis_top, step, compact=compact)
    title = str(spec.get("title", ""))
    # 제목이 있으면 **한 줄 내린다.** 단위 라벨이 `top - 20` 에 앉으므로 그대로 두면
    # 긴 제목과 같은 줄에서 부딪힌다. 제목이 없으면 `top` 은 36 그대로라
    # **지금 지면 2,400장이 한 픽셀도 안 바뀐다.**
    n = len(values)
    gap = 8.0
    if compact:
        # 세로형의 폭을 정하는 것은 눈금 숫자가 아니라 **항목 라벨 간격**이다 —
        # 이웃 라벨이 겹치지 않을 만큼이 최소다(실측: 「바닐라」 39.7단위).
        ticks = _tick_values(axis_top, step)
        left = TICK_DIGIT_W * max(len(str(t)) for t in ticks) + 7
        label_w = max(_label_w_max(str(lab)) for lab, _ in values)
        plot_w = (label_w + TICK_MIN_GAP) * n + gap
    else:
        left, plot_w = 46.0, 186.0
    top, plot_h, pad_b = (56.0 if title else 36.0), 118.0, 32.0
    bw = (plot_w - gap * (n + 1)) / n
    parts = _plot_axes(left, top, plot_w, plot_h, axis_top, step)
    for i, (lab, val) in enumerate(values):
        x = left + gap + i * (bw + gap)
        if val is None:
            # 지워진 막대 — **값 축 전체**를 점선으로 두른다. 어떤 눈금에도 안 걸리므로
            # 그림이 답을 흘리지 않는다(D-66 ⑺). 항목마다 늘 같은 기하다.
            parts.append(_rect(x, top, bw, plot_h, fill="none", sw=1.05, dash=UNKNOWN_DASH))
            parts.append(_text(x + bw / 2, top + plot_h / 2, "?", size=16))
        else:
            h = 0 if axis_top <= 0 else min(plot_h, plot_h * val / axis_top)
            y = top + plot_h - h
            # 0 은 정당한 자료다. rect 를 **안 그린다** — 높이 0 은 정제기가 막는다
            # (`figure_quality` 의 「height must be positive」). 이름표 「0」은 그린다.
            if h > 0:
                parts.append(_rect(x, y, bw, h, fill=CHART[i % len(CHART)], sw=1.05))
            num = str(int(val)) if val == int(val) else _n(val)
            # 막대 안쪽이면 격자선과 안 겹친다. 짧은 막대만 위에 둔다.
            ny = y + 14 if h >= 24 else y - 12
            parts.append(_text(x + bw / 2, ny, num, size=16))
        parts.append(_text(x + bw / 2, top + plot_h + 16, lab, size=13))
    parts.append(_unit_label(left, top, str(spec.get("yLabel", ""))))
    parts.append(_chart_title(title, left + plot_w / 2, plot_w, y=18.0))
    if compact:
        # 마지막 항목 라벨이 마지막 막대보다 넓으면 오른쪽으로 삐져나간다.
        last_cx = left + gap + (n - 1) * (bw + gap) + bw / 2
        label_w = max(_label_w_max(str(lab)) for lab, _ in values)
        w = max(left + plot_w + gap, last_cx + label_w / 2 + 2)
    else:
        w = min(TABLE_VIEWBOX_MAX, left + plot_w + 8)
    return _svg(w, top + plot_h + pad_b, "".join(parts))


def _line_chart(spec: Mapping[str, Any], compact: bool = False) -> str:
    values = _chart_values_of("lineChart", spec["values"], "values")
    data_max = max(v for _, v in values if v is not None)
    y_max = _num(spec.get("yMax", data_max or 1), "yMax", 1, 10000)
    axis_top, step = _axis_top(y_max, data_max, _y_step_spec(spec))
    n = len(values)
    title = str(spec.get("title", ""))
    if compact:
        # 세로형 막대와 같은 이유 — 가로축 라벨 간격이 폭을 정한다.
        ticks = _tick_values(axis_top, step)
        left = TICK_DIGIT_W * max(len(str(t)) for t in ticks) + 7
        label_w = max(_label_w_max(str(lab), 10.0) for lab, _ in values)
        plot_w = (label_w + TICK_MIN_GAP) * n
    else:
        left, plot_w = 46.0, 186.0
    top, plot_h, pad_b = (56.0 if title else 36.0), 100.0, 28.0
    parts = _plot_axes(left, top, plot_w, plot_h, axis_top, step)
    pts: list[tuple[float, float]] = []
    for i, (lab, val) in enumerate(values):
        x = left + (plot_w * i / max(n - 1, 1))
        y = top + plot_h - (0 if axis_top <= 0 else min(plot_h, plot_h * val / axis_top))
        pts.append((x, y))
        parts.append(_text(x, top + plot_h + 12, lab, size=10))
    for a, b in zip(pts, pts[1:]):
        parts.append(_line(a, b, sw=1.5))
    for x, y in pts:
        parts.append(f'<circle cx="{_n(x)}" cy="{_n(y)}" r="2.4" fill="{INK}"/>')
    parts.append(_unit_label(left, top, str(spec.get("yLabel", ""))))
    parts.append(_chart_title(title, left + plot_w / 2, plot_w, y=18.0))
    if compact:
        label_w = max(_label_w_max(str(lab), 10.0) for lab, _ in values)
        w = max(left + plot_w + 8, left + plot_w + label_w / 2 + 2)
    else:
        w = min(TABLE_VIEWBOX_MAX, left + plot_w + 8)
    return _svg(w, top + plot_h + pad_b, "".join(parts))


# ── 통계 그림 — 히스토그램·도수분포다각형 (중1 IV. 통계, 2026-08-23) ──────────
#
# 정본은 RPM 중학 1-2 p152(개념)·p153(09-3·09-4)·p157(유형06)·p164(두 집단)의
# 원본 지면이다. 렌더해서 **모양을 대조**했다 — 구조만 가져왔고 본문·수치는 안 베꼈다.
#
# ## 왜 barChart·lineChart 로 안 되나 (넷 + 하나)
#
# `barChart` 는 ⑴ 막대 사이에 **틈**이 있고 ⑵ 막대마다 색이 다르고 ⑶ 막대 위에 값
# 숫자를 적고 ⑷ 항목 라벨이 **막대 가운데**에 온다. 히스토그램은 넷 다 반대다 —
# **틈이 없고**(직사각형의 넓이가 도수에 비례한다는 근거가 여기서 나온다) 한 색이고
# 값을 안 적고(그림에서 **읽어 내는 것**이 문항이다) 라벨은 **계급의 양 끝 값**,
# 즉 눈금 자리에 온다. `lineChart` 는 ⑸ **양끝 0 연장이 없다** — 도수분포다각형은
# 계급 하나 바깥의 도수 0 으로 내려 닫아야 넓이가 히스토그램과 같아진다.
#
# ## 그림이 곧 검산이다
#
# 계급 폭이 다르면 «넓이 ∝ 도수» 가 깨진다 → **던진다**. `total` 이 도수의 합과
# 다르면 발문이 그림과 다른 말을 한다 → **던진다**. 「일부가 안 보이는」 유형은
# 총합이 없으면 아무도 못 푼다 → `hidden` 이 있으면 `total` 을 **요구한다**.
#
# ## 지면 폭을 박는다
#
# viewBox 폭 하나로 지면 등급(140/240/360px)이 갈린다. 안 박으면 내용에 따라 폭이
# 떠다녀 **도형마다 눈금 글자 크기가 뒤집힌다**(CLAUDE.md 2026-08-23). 240 으로
# 박고, 라벨이 넘쳐 벌어지면 **던진다** — 조용히 넓히면 그 그림만 작아진다.
STAT_VIEWBOX = TABLE_VIEWBOX_MAX
# 계급 수 상한. 경계 눈금이 계급 수 + 1 개라 이 위는 숫자가 겹친다(`_assert_ticks_fit`).
STAT_MAX_CLASSES = 9
# 그림 칸의 최소 가로. 이보다 좁으면 계급이 실오라기가 된다.
STAT_MIN_PLOT_W = 90.0
STAT_PLOT_H = 118.0
# 히스토그램 직사각형 — **한 색**이다. 계급마다 색을 바꾸면 막대그래프가 된다.
HIST_FILL = "#c5d4e8"
# 2계열 둘째 계열의 파선. 실선과 눈에 띄게 갈려야 흑백 지면에서 두 집단이 구분된다.
STAT_DASH_2 = "5 3"
# 찢긴 가장자리의 물결 폭·마디 길이(단위). RPM 1-2 유형06 「찢어져 보이지 않는」 자국.
TEAR_AMP = 2.4
TEAR_SEG = 7.0
TEAR_INK = "#8a8a8a"
# 소수 눈금 자릿수 상한. 상대도수(0.24 등)까지가 교과 범위다.
STAT_MAX_DECIMALS = 2


def _grid_line(a: tuple[float, float], b: tuple[float, float]) -> str:
    return (
        f'<line x1="{_n(a[0])}" y1="{_n(a[1])}" x2="{_n(b[0])}" y2="{_n(b[1])}" '
        f'stroke="{GRID}" stroke-width="{_n(GRID_SW)}"/>'
    )


def _stat_decimals(nums: list[float]) -> int:
    """이 수들을 정확히 적는 데 필요한 소수 자릿수. 넘으면 던진다.

    도수는 정수지만 **상대도수**는 0.24 처럼 소수다. 자릿수를 알면 전부 10^d 배 해서
    **정수 축 규칙 한 벌**(`_axis_top`·`_y_step`·9줄 상한)을 그대로 태울 수 있다 —
    소수용 사다리를 따로 만들면 규칙이 두 벌이 되어 한쪽만 고쳐진다.
    """
    for d in range(STAT_MAX_DECIMALS + 1):
        k = 10**d
        if all(abs(v * k - round(v * k)) < 1e-7 for v in nums):
            return d
    raise ValueError(
        f"도수는 소수 {STAT_MAX_DECIMALS}자리까지만 그립니다 — 값을 반올림해 주십시오"
    )


def _stat_axis(values: list[float], spec: Mapping[str, Any]) -> tuple[int, int, int]:
    """값 축을 **정수로 환산해** `_axis_top` 에 넘긴다. 돌려주는 것은 (맨 위, 걸음, 배율).

    `yStep` 이 오면 그 걸음 그대로 긋는다(D-70) — 여기서 다시 고르면 「한 칸 몇 명」
    발문이 그림과 다른 말을 한다. 못 그리면 `_axis_top` 이 던진다.
    """
    data_max = max(values)
    y_max_raw = spec.get("yMax", data_max if data_max > 0 else 1)
    y_max = _num(y_max_raw, "yMax", 0.01, 10000)
    step_raw = spec.get("yStep")
    y_step = None if step_raw is None else _num(step_raw, "yStep", 0.01, 10000)
    pool = list(values) + [y_max] + ([] if y_step is None else [y_step])
    k = 10 ** _stat_decimals(pool)
    top_i, step_i = _axis_top(
        round(y_max * k),
        round(data_max * k),
        None if y_step is None else round(y_step * k),
    )
    return int(round(top_i)), int(step_i), k


def _stat_fmt(value_i: int, k: int) -> str:
    """정수로 환산한 눈금을 사람이 읽는 글자로.

    자릿수는 **걸음이 정한다** — `_n` 이 꼬리 0을 떼므로 걸음 0.1 이면 「0.1」,
    0.05 면 「0.05」, 0 은 그냥 「0」 이다. 데이터의 자릿수로 맞추면 걸음이 0.1인데
    눈금이 「0.10」 으로 찍힌다(교과서는 그렇게 안 쓴다).
    """
    return _n(value_i / k)


def _stat_classes(spec: Mapping[str, Any]) -> tuple[list[float], float]:
    """계급의 양 끝 값과 **계급의 크기**. 폭이 다르면 던진다 — 그림이 곧 검산이다.

    히스토그램에서 「직사각형의 넓이 = 계급의 크기 × 도수」가 성립하는 근거가
    **폭이 같다**는 것이다. 폭이 다른 것을 그려 놓고 넓이를 묻는 문항을 내면 답이
    없다. 조용히 그리지 않고 던진다.
    """
    raw = spec["classes"]
    if not isinstance(raw, list) or not (3 <= len(raw) <= STAT_MAX_CLASSES + 1):
        raise ValueError(
            f"classes 는 계급의 양 끝 값 3~{STAT_MAX_CLASSES + 1}개여야 합니다 "
            f"(계급 {STAT_MAX_CLASSES}개까지)"
        )
    vals = [_num(v, f"classes[{i}]", -10000, 10000) for i, v in enumerate(raw)]
    width = vals[1] - vals[0]
    if width <= 0:
        raise ValueError("classes 는 작은 값부터 커지는 순서여야 합니다")
    for i in range(len(vals) - 1):
        gap = vals[i + 1] - vals[i]
        if abs(gap - width) > 1e-7:
            raise ValueError(
                f"계급의 크기가 다릅니다 ({i + 1}번째 계급 {gap:g}, 첫 계급 {width:g}) — "
                f"히스토그램은 폭이 같아야 넓이가 도수에 비례합니다"
            )
    return vals, width


def _stat_series(raw: Any, n: int, name: str) -> list[float]:
    if not isinstance(raw, list) or len(raw) != n:
        raise ValueError(f"{name} 는 계급 수({n})와 같은 길이의 배열이어야 합니다")
    return [_num(v, f"{name}[{i}]", 0, 10000) for i, v in enumerate(raw)]


def _stat_total(spec: Mapping[str, Any], values: list[float], name: str) -> None:
    """도수의 합이 `total` 과 같은가. 다르면 던진다 — 발문이 그림과 다른 말을 한다."""
    if "total" not in spec:
        return
    total = _num(spec["total"], f"{name}total", 0, 100000)
    got = sum(values)
    if abs(got - total) > 1e-7:
        raise ValueError(
            f"{name}도수의 합 {got:g} 이 total {total:g} 과 다릅니다 — "
            f"그림과 발문이 다른 말을 합니다"
        )


def _stat_second(spec: Mapping[str, Any], n: int) -> tuple[list[float], str, str] | None:
    """두 집단 비교용 둘째 계열. 있으면 **두 계열 다 이름이 있어야 한다**.

    이름 없이 둘을 겹쳐 그리면 어느 것이 어느 반인지 지면에서 알 수 없다
    (RPM 1-2 p164 는 그래프마다 이름표를 단다).
    """
    raw = spec.get("series2")
    if raw is None:
        # 이름만 주고 둘째 계열이 없으면 그 이름은 **어디에도 안 그려진다.**
        # 조용히 버리면 부르는 쪽은 이름표가 붙은 줄 안다 (D-70 — 침묵 금지).
        if spec.get("label"):
            raise ValueError("label 은 series2 와 함께 씁니다 — 한 계열에는 이름표를 안 답니다")
        return None
    if not isinstance(raw, Mapping):
        raise ValueError("series2 는 객체여야 합니다")
    extra = set(raw) - {"values", "label", "total"}
    if extra:
        raise ValueError(
            f"series2 에 허용되지 않은 키: {', '.join(sorted(str(k) for k in extra))}"
        )
    values = _stat_series(raw.get("values"), n, "series2.values")
    _stat_total(raw, values, "series2 ")
    label2 = str(raw.get("label", ""))
    label1 = str(spec.get("label", ""))
    if not label1 or not label2:
        raise ValueError("두 집단을 겹쳐 그리려면 label 과 series2.label 이 둘 다 있어야 합니다")
    return values, label1, label2


def _stat_hidden(spec: Mapping[str, Any], n: int) -> list[int]:
    """찢어져 보이지 않는 계급. 있으면 `total` 을 **요구한다**.

    총합이 없으면 「보이지 않는 계급의 도수」를 구할 근거가 그림에도 발문에도 없다 —
    풀 수 없는 문항이 조용히 나간다(RPM 1-2 유형06).
    """
    raw = spec.get("hidden")
    if raw is None:
        return []
    if not isinstance(raw, list) or not raw:
        raise ValueError("hidden 은 비어 있지 않은 계급 번호 배열이어야 합니다")
    idx = sorted({_int(h, "hidden[]", 0, n - 1) for h in raw})
    if len(idx) >= n:
        raise ValueError("hidden 이 모든 계급을 가립니다 — 읽을 것이 남지 않습니다")
    if "total" not in spec:
        raise ValueError(
            "hidden 을 쓰면 total 이 있어야 합니다 — 총합이 없으면 보이지 않는 계급의 "
            "도수를 구할 근거가 없습니다"
        )
    return idx


def _tear_edge(x: float, y0: float, y1: float) -> str:
    """찢긴 세로 가장자리 — 물결선. 마디가 고정이라 **같은 스펙이면 같은 그림**이다."""
    steps = max(4, int(round((y1 - y0) / TEAR_SEG)))
    pts = [
        (x + (TEAR_AMP if j % 2 else -TEAR_AMP), y0 + (y1 - y0) * j / steps)
        for j in range(steps + 1)
    ]
    s = " ".join(f"{_n(px)},{_n(py)}" for px, py in pts)
    return f'<polyline points="{s}" fill="none" stroke="{TEAR_INK}" stroke-width="1"/>'


def _axis_break(x: float, y: float) -> str:
    """가로축이 0 이 아닌 값에서 시작할 때의 **생략 표시**. 교과서 규약이다."""
    return (
        f'<polyline points="{_n(x)},{_n(y + 4)} {_n(x + 3)},{_n(y - 1)} '
        f'{_n(x + 1)},{_n(y - 5)}" fill="none" stroke="{INK}" stroke-width="1"/>'
        f'<polyline points="{_n(x + 4)},{_n(y + 4)} {_n(x + 7)},{_n(y - 1)} '
        f'{_n(x + 5)},{_n(y - 5)}" fill="none" stroke="{INK}" stroke-width="1"/>'
    )


def _stat_dot(x: float, y: float, hollow: bool) -> str:
    fill = PAPER if hollow else INK
    return (
        f'<circle cx="{_n(x)}" cy="{_n(y)}" r="2.6" fill="{fill}" '
        f'stroke="{INK}" stroke-width="1"/>'
    )


def _stat_frame(
    y_labels: list[str], x_labels: list[str], ylab: str, xlab: str, x_frac: float
) -> tuple[float, float]:
    """왼쪽 여백과 그림 칸 가로. **폭이 240 에 박혀 있으므로 여백이 칸을 정한다.**

    왼쪽은 세로 눈금 숫자와 단위 라벨(`(명)`) 중 넓은 쪽이 정한다.

    오른쪽은 **마지막 가로 눈금이 칸의 어디에 있는가**로 푼다. 그 숫자는 가운데
    정렬이라 오른쪽으로 절반을 뻗고, 가로 단위(`(m)`)가 그 뒤에 붙는다. 히스토그램은
    마지막 눈금이 칸의 오른쪽 끝(`x_frac = 1`)이지만 **도수분포다각형은 계급 하나
    바깥까지 그리므로 안쪽**이다(`x_frac = (n+1)/(n+2)`). 그 차이를 안 보고 여백을
    빼면 칸이 실제보다 좁아져 **멀쩡한 그림이 거절된다** — 실측으로 계급 6개짜리
    다각형이 154단위로 좁아져 눈금 「10 12 14」가 붙었다.
    """
    left = max(
        (_label_w_max(ylab) + 7 + FIT_PAD) if ylab else 0.0,
        max(_label_w_max(t) for t in y_labels) + 9.0,
        30.0,
    )
    tail = _label_w_max(x_labels[-1]) / 2 + FIT_PAD
    if xlab:
        tail += UNIT_GAP + _label_w_max(xlab)
    plot_w = min(
        (STAT_VIEWBOX - FIT_PAD - left - tail) / x_frac,
        STAT_VIEWBOX - left - FIT_PAD,
    )
    if plot_w < STAT_MIN_PLOT_W:
        raise ValueError(
            f"라벨이 넓어 그림 칸이 {plot_w:.0f}단위밖에 안 남습니다 "
            f"({STAT_MIN_PLOT_W:.0f} 이상이어야 합니다). 단위 이름을 줄이십시오"
        )
    return left, plot_w


def _stat_svg(height: float, body: str) -> str:
    """**폭을 박아** 내보낸다. 벌어졌으면 던진다.

    `_svg` 는 그린 것이 넘치면 viewBox 를 **넓혀** 준다. 그것은 잘림을 막는 좋은
    성질이지만, 여기서는 폭이 곧 지면 등급이라 넓어지는 순간 이 그림만 화면에서
    작아진다 — 그리고 아무 에러도 안 난다. 그래서 넓어졌으면 멈춘다.

    ## 이 가드는 **오늘 안 걸린다** — 그게 결함이 아니라 여유가 0이라는 뜻이다

    실측(2026-08-23): 두 kind × 계급 2~9 × 걸음 1·2·5·10 × 단위 라벨 16조합 =
    **808장 전부 정확히 240**, 가장 오른쪽 좌표 **238.0**(= 240 − `FIT_PAD`, 여유
    **0.00**). `_stat_frame` 이 여백을 정확히 되돌려 주므로 지금 입력으로는 도달할 수
    없다 — 그래서 변이 하네스가 이 줄을 「판정 안 함」으로 돌려준다. **정상이다.**

    ⚠️ 그러니 이 줄을 「초록이니 가드가 아니다」로 읽고 지우지 마라. 여유가 0이라
    **프레임 밖으로 한 단위라도 더 그리는 순간 걸린다** — 앞으로 요소를 하나 더할 때
    지면 등급이 조용히 뒤집히는 것을 막는 그물이 이것뿐이다.
    """
    return _fixed_width_svg(STAT_VIEWBOX, height, body, "통계 그림", "라벨을 줄이십시오")


def _stat_legend(
    cx: float, y: float, entries: list[tuple[str, str]], plot_w: float
) -> list[str]:
    """두 집단 이름표. 넘치면 던진다 — 겹치면 어느 것이 어느 반인지 사라진다.

    `entries` 는 (이름, 모양) 이고 모양은 "fill1"·"fill2"·"line1"·"line2".
    """
    swatch, gap, pitch = 16.0, 5.0, 14.0
    widths = [swatch + gap + _label_w_max(name) for name, _ in entries]
    total = sum(widths) + pitch * (len(entries) - 1)
    if total > plot_w:
        raise ValueError(
            f"이름표가 그림보다 넓습니다 ({total:.0f} > {plot_w:.0f}단위) — 이름을 줄이십시오"
        )
    parts: list[str] = []
    x = cx - total / 2
    for (name, mode), w in zip(entries, widths):
        if mode == "fill1":
            parts.append(_rect(x, y - 5, swatch, 10, fill=HIST_FILL, sw=1.05))
        elif mode == "fill2":
            # 실제 막대가 `fill="none"` 이므로 견본도 비운다 — 색을 칠하면
            # **이름표가 그림과 다른 말을 한다**.
            parts.append(
                _rect(x, y - 5, swatch, 10, fill="none", sw=1.4, dash=STAT_DASH_2)
            )
        else:
            parts.append(
                _line((x, y), (x + swatch, y), sw=1.5,
                      dash=STAT_DASH_2 if mode == "line2" else None)
            )
            parts.append(_stat_dot(x + swatch / 2, y, mode == "line2"))
        parts.append(_text(x + swatch + gap, y, name, size=13, anchor="start"))
        x += w + pitch
    return parts


def _stat_chart(spec: Mapping[str, Any], kind: str) -> str:
    """히스토그램과 도수분포다각형의 **한 벌**. 다른 것은 셋뿐이다.

    ⑴ 가로 범위 — 다각형은 양끝에 도수 0 인 계급을 **하나씩 더** 둔다.
    ⑵ 그리는 것 — 직사각형이냐 꺾은선이냐(다각형은 `bars` 로 히스토그램을 깔 수 있다).
    ⑶ 찢김(`hidden`) 은 히스토그램 유형에만 있다.

    축·모눈·눈금·이름표·폭 박기는 **같은 코드**가 낸다. 각자 그리면 규칙이 두 벌이
    되어, 하필 「넓이가 같다」를 보이려고 겹쳐 그린 그림에서 두 자가 어긋난다.
    """
    classes, width = _stat_classes(spec)
    n = len(classes) - 1
    values = _stat_series(spec["values"], n, "values")
    _stat_total(spec, values, "")
    second = _stat_second(spec, n)
    hidden = _stat_hidden(spec, n) if kind == "histogram" else []
    bars = kind == "histogram" or bool(spec.get("bars", False))
    if kind == "freqPolygon" and not isinstance(spec.get("bars", False), bool):
        raise ValueError("bars 는 참·거짓이어야 합니다")

    # ⑴ 가로 범위. 다각형은 계급 하나 바깥까지 — 거기서 도수 0 으로 내려 닫는다.
    pad_cls = width if kind == "freqPolygon" else 0.0
    x_lo, x_hi = classes[0] - pad_cls, classes[-1] + pad_cls

    pool = values + (list(second[0]) if second else [])
    top_i, step_i, k = _stat_axis(pool, spec)
    y_labels = [_stat_fmt(v, k) for v in _tick_values(top_i, step_i)]
    x_labels = [_n(c) for c in classes]
    ylab, xlab = str(spec.get("yLabel", "")), str(spec.get("xLabel", ""))
    title = str(spec.get("title", ""))
    x_frac = (classes[-1] - x_lo) / (x_hi - x_lo)
    left, plot_w = _stat_frame(y_labels, x_labels, ylab, xlab, x_frac)
    _assert_ticks_fit(x_labels, plot_w, round((x_hi - x_lo) / width))
    top = 50.0 if title else 30.0
    plot_h = STAT_PLOT_H
    bottom = top + plot_h

    def px(v: float) -> float:
        return left + plot_w * (v - x_lo) / (x_hi - x_lo)

    def py(v: float) -> float:
        return bottom - plot_h * (v * k) / top_i

    parts: list[str] = []
    # ── 모눈. 세로는 계급의 양 끝 값과 **가운데 값**(다각형 꼭짓점 자리),
    #    가로는 눈금과 그 절반(걸음이 짝수일 때만 — 홀수면 반 칸이 안 읽힌다).
    v = x_lo
    while v <= x_hi + 1e-7:
        parts.append(_grid_line((px(v), top), (px(v), bottom)))
        v += width / 2
    minor = step_i // 2 if step_i % 2 == 0 else step_i
    gy = 0
    while gy <= top_i + 1e-7:
        parts.append(_grid_line((left, py(gy / k)), (left + plot_w, py(gy / k))))
        gy += minor
    parts.append(_grid_line((left, top), (left + plot_w, top)))
    parts.append(_grid_line((left + plot_w, top), (left + plot_w, bottom)))

    # ── 찢긴 자리. 모눈을 지우고 막대를 안 그린다. 축보다 **먼저** 덮어야
    #    가로축이 살아남는다(찢겨도 축은 남는다 — RPM 유형06 지면 그대로).
    for i in hidden:
        x0, x1 = px(classes[i]), px(classes[i + 1])
        parts.append(
            _rect(x0, top, x1 - x0, plot_h, fill=PAPER, stroke="none", sw=0)
        )

    # ── 직사각형. **틈이 없다** — 넓이가 도수에 비례한다는 근거가 여기다.
    if bars:
        for i, val in enumerate(values):
            if i in hidden:
                continue
            x0, x1 = px(classes[i]), px(classes[i + 1])
            y = py(val)
            parts.append(_rect(x0, y, x1 - x0, bottom - y, fill=HIST_FILL, sw=1.15))
        if second is not None and kind == "histogram":
            for i, val in enumerate(second[0]):
                if i in hidden:
                    continue
                x0, x1 = px(classes[i]), px(classes[i + 1])
                y = py(val)
                parts.append(
                    _rect(x0, y, x1 - x0, bottom - y, fill="none", sw=1.5,
                          dash=STAT_DASH_2)
                )

    # ── 꺾은선. 양끝을 계급 하나 바깥의 **도수 0** 으로 내려 닫는다.
    if kind == "freqPolygon":
        mids = [(classes[i] + classes[i + 1]) / 2 for i in range(n)]
        for si, series in enumerate(
            [values] + ([list(second[0])] if second else [])
        ):
            pts = (
                [(px(mids[0] - width), py(0))]
                + [(px(m), py(val)) for m, val in zip(mids, series)]
                + [(px(mids[-1] + width), py(0))]
            )
            parts.append(
                _polyline(pts, sw=1.6, dash=STAT_DASH_2 if si else None)
            )
            parts.extend(_stat_dot(x, y, bool(si)) for x, y in pts)

    # ── 축 두 줄과 눈금. 축은 찢김·막대 **위**에 그린다.
    parts.append(_line((left, top), (left, bottom)))
    parts.append(_line((left, bottom), (left + plot_w, bottom)))
    for i, val_i in enumerate(_tick_values(top_i, step_i)):
        y = py(val_i / k)
        parts.append(_line((left - 4, y), (left, y), sw=0.9))
        parts.append(_text(left - 7, y, y_labels[i], size=14, anchor="end"))
    for c, lab in zip(classes, x_labels):
        x = px(c)
        parts.append(_line((x, bottom), (x, bottom + 4), sw=0.9))
        parts.append(_text(x, bottom + 14, lab, size=14))
    # 가로축이 0 에서 시작하지 않으면 **생략 표시**를 단다 (교과서 규약).
    if x_lo > 1e-7:
        parts.append(_axis_break(left + 2, bottom - 5))
    # 찢긴 가장자리는 맨 위에 — 막대·모눈·축을 가로질러야 「찢겼다」로 읽힌다.
    for i in hidden:
        parts.append(_tear_edge(px(classes[i]), top, bottom))
        parts.append(_tear_edge(px(classes[i + 1]), top, bottom))

    parts.append(_unit_label(left, top, ylab))
    if xlab:
        x_unit = px(classes[-1]) + _label_w_max(x_labels[-1]) / 2 + UNIT_GAP
        parts.append(_text(x_unit, bottom + 14, xlab, size=13, anchor="start"))
    parts.append(_chart_title(title, left + plot_w / 2, plot_w, y=18.0))

    pad_b = 24.0
    if second is not None:
        mode1, mode2 = ("fill1", "fill2") if kind == "histogram" else ("line1", "line2")
        parts.extend(
            _stat_legend(
                left + plot_w / 2,
                bottom + 34,
                [(second[1], mode1), (second[2], mode2)],
                plot_w,
            )
        )
        pad_b = 46.0
    return _stat_svg(bottom + pad_b, "".join(parts))


def _histogram(spec: Mapping[str, Any]) -> str:
    return _stat_chart(spec, "histogram")


def _freq_polygon(spec: Mapping[str, Any]) -> str:
    return _stat_chart(spec, "freqPolygon")


# ═══════════════════════════════════════════════════════════════════════════
# boxPlot · scatterPlot — 산포도·상자그림과 산점도 (물결 6E, 2026-08-24)
#
# 막고 있던 것: 3-2 「산포도」 7 + 「상자그림과 산점도」 10 = 17유형. `stripChart`(pct
# 문법)·`pointGrid`(찍힌 점에만 라벨)로는 못 그린다 — 다섯 수 요약과 (x,y) 실수좌표는
# 그 kind 들의 허용 키가 아니다(물결 3 조사 §0㉢).
#
# ## 축은 **부르는 쪽이 정한다** — `histogram` 의 `classes` 와 같은 무늬
#
# 「예쁜 눈금」을 여기서 지어내면(예: 데이터 범위로 축을 자동 계산) 발문의 다른
# 수치(평균·분산 등)와 눈금이 갈릴 수 있다. TS 쪽이 이미 문제에 쓸 정수를 들고
# 있으므로, 축 범위·걸음(`axisMin`/`axisMax`/`axisStep`, `xRange`/`xStep` 등)은
# 필수 키로 받아 **여기서는 검산만** 한다(범위 밖 값·안 나눠떨어지는 걸음은 던진다).
# ═══════════════════════════════════════════════════════════════════════════

BOX_H = 20.0           # 상자 높이
BOX_ROW_H = 40.0       # 집단 하나가 차지하는 세로 칸(상자 + 위아래 여백)
BOX_CAP_H = 12.0       # 수염 끝 세로 표시 높이
BOX_LABEL_GAP = 8.0    # 집단 이름표와 축 사이 간격
AXIS_MAX_TICKS = 20    # 눈금 상한 — 이 위는 숫자가 붙어 안 읽힌다
SCATTER_R = 2.6        # 산점도 점 반지름
SCATTER_MAX_POINTS = 40
SCATTER_PAD_L = 30.0
SCATTER_PAD_T = 14.0
SCATTER_PAD_R = 10.0


def _axis_from_spec(
    lo_key: str, hi_key: str, step_key: str, spec: Mapping[str, Any], pool: list[float]
) -> tuple[float, float, float, list[float]]:
    """부르는 쪽이 실어 온 축 범위·걸음을 **검산만** 한다 — 여기서 새로 고르지 않는다.

    범위 밖 값은 던진다(그림이 자료를 못 담는다는 뜻). 걸음이 범위를 나누어떨어지지
    않아도 던진다 — 조용히 반올림하면 마지막 눈금이 축 끝과 어긋난 그림이 나간다.
    """
    lo = _num(spec[lo_key], lo_key, -100000, 100000)
    hi = _num(spec[hi_key], hi_key, -100000, 100000)
    if hi <= lo:
        raise ValueError(f"{hi_key} 는 {lo_key} 보다 커야 합니다")
    step = _num(spec[step_key], step_key, 1e-6, 100000)
    for v in pool:
        if v < lo - 1e-7 or v > hi + 1e-7:
            raise ValueError(
                f"값 {_n(v)} 가 축 범위 [{_n(lo)}, {_n(hi)}] 밖입니다 — "
                f"그림이 자료를 못 담습니다"
            )
    n = (hi - lo) / step
    if abs(n - round(n)) > 1e-6:
        raise ValueError(f"{step_key} 이 {lo_key}~{hi_key} 를 나누어떨어지지 않습니다")
    ticks_n = int(round(n))
    if not 1 <= ticks_n <= AXIS_MAX_TICKS:
        raise ValueError(f"눈금이 {ticks_n}개입니다 (1~{AXIS_MAX_TICKS}개여야 합니다)")
    return lo, hi, step, [lo + i * step for i in range(ticks_n + 1)]


def _box_five(raw: Any, name: str) -> list[float]:
    """다섯 수 요약(최솟값·Q1·중앙값·Q3·최댓값). **순서가 아니면 던진다** — 조용히
    뒤집힌 상자를 그리지 않는다(물결 계약 §「boxPlot」).
    """
    if not isinstance(raw, list) or len(raw) != 5:
        raise ValueError(f"{name} 는 다섯 수(최솟값·Q1·중앙값·Q3·최댓값)여야 합니다")
    nums = [_num(v, f"{name}[{i}]", -100000, 100000) for i, v in enumerate(raw)]
    for i in range(4):
        if nums[i] > nums[i + 1] + 1e-7:
            raise ValueError(
                f"{name} 는 최솟값 ≤ 제1사분위수 ≤ 중앙값 ≤ 제3사분위수 ≤ 최댓값 순서여야 "
                f"합니다 ({', '.join(_n(v) for v in nums)})"
            )
    return nums


def _box_row(px, y: float, five: list[float]) -> list[str]:
    lo, q1, med, q3, hi = five
    half = BOX_H / 2
    cap = BOX_CAP_H / 2
    return [
        _line((px(lo), y), (px(q1), y), sw=1.3),
        _line((px(q3), y), (px(hi), y), sw=1.3),
        _line((px(lo), y - cap), (px(lo), y + cap), sw=1.3),
        _line((px(hi), y - cap), (px(hi), y + cap), sw=1.3),
        _rect(px(q1), y - half, px(q3) - px(q1), BOX_H, fill=PAPER, sw=1.4),
        _line((px(med), y - half), (px(med), y + half), sw=1.4),
    ]


def _box_plot(spec: Mapping[str, Any]) -> str:
    values1 = _box_five(spec["values"], "values")
    label1 = str(spec.get("label", ""))
    rows, labels = [values1], [label1]

    second = spec.get("series2")
    if second is not None:
        if not isinstance(second, Mapping):
            raise ValueError("series2 는 객체여야 합니다")
        extra = set(second) - {"values", "label"}
        if extra:
            raise ValueError(
                f"series2 에 허용되지 않은 키: {', '.join(sorted(str(k) for k in extra))}"
            )
        values2 = _box_five(second.get("values"), "series2.values")
        label2 = str(second.get("label", ""))
        if not label1 or not label2:
            raise ValueError(
                "두 상자그림을 겹쳐 그리려면 label 과 series2.label 이 둘 다 있어야 합니다"
            )
        rows.append(values2)
        labels.append(label2)
    elif label1:
        raise ValueError("label 은 series2 와 함께 씁니다 — 한 상자에는 이름표를 안 답니다")

    pool = [v for row in rows for v in row]
    lo, hi, _step, ticks = _axis_from_spec("axisMin", "axisMax", "axisStep", spec, pool)
    tick_labels = [_n(v) for v in ticks]
    xlab = str(spec.get("xLabel", ""))

    left = max(
        (max(_label_w_max(lb) for lb in labels) + BOX_LABEL_GAP) if label1 else 0.0,
        _label_w_max(tick_labels[0]) / 2 + FIT_PAD,
        12.0,
    )
    tail = _label_w_max(tick_labels[-1]) / 2 + FIT_PAD
    if xlab:
        tail += UNIT_GAP + _label_w_max(xlab)
    plot_w = STAT_VIEWBOX - left - tail
    if plot_w < STAT_MIN_PLOT_W:
        raise ValueError(
            f"이름표가 넓어 그림 칸이 {plot_w:.0f}단위밖에 안 남습니다 "
            f"({STAT_MIN_PLOT_W:.0f} 이상이어야 합니다) — 이름을 줄이십시오"
        )

    def px(v: float) -> float:
        return left + plot_w * (v - lo) / (hi - lo)

    top = 14.0
    parts: list[str] = []
    for i, (row, lb) in enumerate(zip(rows, labels)):
        y = top + BOX_ROW_H * i + BOX_ROW_H / 2
        parts += _box_row(px, y, row)
        if lb:
            parts.append(_text(left - BOX_LABEL_GAP, y, lb, size=13, anchor="end"))
    axis_y = top + BOX_ROW_H * len(rows)
    parts.append(_line((left, axis_y), (left + plot_w, axis_y), sw=1.0))
    for v, lb in zip(ticks, tick_labels):
        x = px(v)
        parts.append(_line((x, axis_y), (x, axis_y + 4), sw=0.9))
        parts.append(_text(x, axis_y + 14, lb, size=14))
    if xlab:
        x_unit = px(ticks[-1]) + _label_w_max(tick_labels[-1]) / 2 + UNIT_GAP
        parts.append(_text(x_unit, axis_y + 14, xlab, size=13, anchor="start"))
    return _stat_svg(axis_y + 24.0, "".join(parts))


def _scatter_points(
    raw: Any, xr: tuple[float, float], yr: tuple[float, float]
) -> list[tuple[float, float]]:
    if not isinstance(raw, list) or not 2 <= len(raw) <= SCATTER_MAX_POINTS:
        raise ValueError(f"points 는 2~{SCATTER_MAX_POINTS}개의 [x, y] 목록이어야 합니다")
    xlo, xhi = xr
    ylo, yhi = yr
    out: list[tuple[float, float]] = []
    for i, p in enumerate(raw):
        if not isinstance(p, list) or len(p) != 2:
            raise ValueError(f"points[{i}] 는 [x, y] 여야 합니다")
        x = _num(p[0], f"points[{i}][0]", -100000, 100000)
        y = _num(p[1], f"points[{i}][1]", -100000, 100000)
        if not (xlo - 1e-7 <= x <= xhi + 1e-7 and ylo - 1e-7 <= y <= yhi + 1e-7):
            raise ValueError(
                f"points[{i}] = ({_n(x)}, {_n(y)}) 가 축 범위 밖입니다 — "
                f"그림이 자료를 못 담습니다"
            )
        out.append((x, y))
    return out


def _scatter_plot(spec: Mapping[str, Any]) -> str:
    xlo, xhi, _xstep, xticks = _axis_from_spec("xMin", "xMax", "xStep", spec, [])
    ylo, yhi, _ystep, yticks = _axis_from_spec("yMin", "yMax", "yStep", spec, [])
    pts = _scatter_points(spec["points"], (xlo, xhi), (ylo, yhi))
    x_labels = [_n(v) for v in xticks]
    y_labels = [_n(v) for v in yticks]
    xlab = str(spec.get("xLabel", ""))
    ylab = str(spec.get("yLabel", ""))
    title = str(spec.get("title", ""))

    left = max(
        (_label_w_max(ylab) + 7 + FIT_PAD) if ylab else 0.0,
        max(_label_w_max(t) for t in y_labels) + 9.0,
        SCATTER_PAD_L,
    )
    tail = _label_w_max(x_labels[-1]) / 2 + FIT_PAD
    if xlab:
        # ⚠️ 이 두 줄이 없어서 x축 단위 이름표가 **오른쪽에서 잘렸다**
        #    (원장님 지적 2026-08-25 — 화면에 「100 (」 까지만 보였다).
        #    `_stat_frame`(히스토그램)과 `_box_plot` 은 진작 빼고 있었고 여기만 빠져
        #    있었다 — 같은 규칙을 쓰는 자리가 셋인데 하나만 안 고쳐진 그 자리다.
        tail += UNIT_GAP + _label_w_max(xlab)
    plot_w = STAT_VIEWBOX - left - tail - SCATTER_PAD_R
    if plot_w < STAT_MIN_PLOT_W:
        raise ValueError(
            f"라벨이 넓어 그림 칸이 {plot_w:.0f}단위밖에 안 남습니다 "
            f"({STAT_MIN_PLOT_W:.0f} 이상이어야 합니다)"
        )
    # 세로축 단위를 넣으면 맨 위 눈금이 그만큼 내려와야 한다 — 안 내리면 위가 잘린다.
    top = max(30.0 if title else SCATTER_PAD_T, unit_label_min_top() if ylab else 0.0)
    plot_h = STAT_PLOT_H
    bottom = top + plot_h

    def px(v: float) -> float:
        return left + plot_w * (v - xlo) / (xhi - xlo)

    def py(v: float) -> float:
        return bottom - plot_h * (v - ylo) / (yhi - ylo)

    parts: list[str] = []
    for v in xticks[1:-1]:
        parts.append(_grid_line((px(v), top), (px(v), bottom)))
    for v in yticks[1:-1]:
        parts.append(_grid_line((left, py(v)), (left + plot_w, py(v))))
    parts.append(_line((left, top), (left, bottom)))
    parts.append(_line((left, bottom), (left + plot_w, bottom)))
    for v, lb in zip(xticks, x_labels):
        x = px(v)
        parts.append(_line((x, bottom), (x, bottom + 4), sw=0.9))
        parts.append(_text(x, bottom + 14, lb, size=14))
    for v, lb in zip(yticks, y_labels):
        y = py(v)
        parts.append(_line((left - 4, y), (left, y), sw=0.9))
        parts.append(_text(left - 7, y, lb, size=14, anchor="end"))
    # 점은 축·모눈 **위**에 그린다 — 겹치면 자료가 격자에 가려 안 보인다.
    parts += [
        f'<circle cx="{_n(px(x))}" cy="{_n(py(y))}" r="{_n(SCATTER_R)}" fill="{INK}"/>'
        for x, y in pts
    ]
    parts.append(_unit_label(left, top, ylab))
    if xlab:
        x_unit = px(xticks[-1]) + _label_w_max(x_labels[-1]) / 2 + UNIT_GAP
        parts.append(_text(x_unit, bottom + 14, xlab, size=13, anchor="start"))
    parts.append(_chart_title(title, left + plot_w / 2, plot_w, y=18.0))
    return _stat_svg(bottom + 24.0, "".join(parts))


def _pictograph(spec: Mapping[str, Any]) -> str:
    unit = _int(spec["unit"], "unit", 1, 100)
    items = spec["items"]
    if not isinstance(items, list) or not items or len(items) > 6:
        raise ValueError("items 는 1~6개여야 합니다")
    # viewBox 폭을 240으로 고정 — 칸 수가 달라도 화면 크기가 안 변한다.
    icon_w, icon_h, pad = 22.0, 24.0, 10.0
    parts: list[str] = [_text(pad, 14, f"□ = {unit}", size=13, anchor="start")]
    y = 32.0
    for i, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise ValueError("items 항목은 객체여야 합니다")
        lab = str(item.get("label", ""))
        count = _int(item.get("count"), f"items[{i}].count", 0, 12)
        parts.append(_text(pad + 28, y + icon_h / 2, lab, size=12, anchor="end"))
        for k in range(count):
            x = pad + 36 + k * (icon_w + 4)
            parts.append(_rect(x, y, icon_w, icon_h, rx=2, fill=CHART[i % len(CHART)], sw=1.0))
        y += icon_h + 8
    return _svg(TABLE_VIEWBOX_MAX, y + pad, "".join(parts))


def _strip_chart(spec: Mapping[str, Any]) -> str:
    segs = spec["segments"]
    if not isinstance(segs, list) or not segs or len(segs) > 8:
        raise ValueError("segments 는 1~8개여야 합니다")
    parsed: list[tuple[str, float]] = []
    total = 0.0
    for i, item in enumerate(segs):
        if not isinstance(item, Mapping):
            raise ValueError("segments 항목은 객체여야 합니다")
        pct = _num(item.get("pct"), f"segments[{i}].pct", 0, 100)
        parsed.append((str(item.get("label", "")), pct))
        total += pct
    if abs(total - 100) > 0.6:
        raise ValueError("segments pct 합은 100이어야 합니다")
    x0, y0, bw, bh = 8.0, 8.0, 224.0, 28.0
    parts = [_rect(x0, y0, bw, bh, sw=1.2)]
    x = x0
    for i, (lab, pct) in enumerate(parsed):
        w = bw * pct / 100.0
        parts.append(_rect(x, y0, w, bh, fill=CHART[i % len(CHART)], sw=0.8))
        if w >= 44:
            parts.append(_text(x + w / 2, y0 + bh / 2, f"{lab} {int(pct)}%", size=9))
        x += w
    y = y0 + bh + 14
    for i, (lab, pct) in enumerate(parsed):
        if bw * pct / 100.0 < 44:
            parts.append(_text(8 + i * 56, y, f"{lab} {int(pct)}%", size=9, anchor="start"))
    return _svg(min(TABLE_VIEWBOX_MAX, 240), y + 10, "".join(parts))


def _pie_chart(spec: Mapping[str, Any]) -> str:
    slices = spec["slices"]
    if not isinstance(slices, list) or not slices or len(slices) > 8:
        raise ValueError("slices 는 1~8개여야 합니다")
    parsed: list[tuple[str, float]] = []
    total = 0.0
    for i, item in enumerate(slices):
        if not isinstance(item, Mapping):
            raise ValueError("slices 항목은 객체여야 합니다")
        pct = _num(item.get("pct"), f"slices[{i}].pct", 0, 100)
        parsed.append((str(item.get("label", "")), pct))
        total += pct
    if abs(total - 100) > 0.6:
        raise ValueError("slices pct 합은 100이어야 합니다")
    r, pad, cx, cy = 44.0, 8.0, 52.0, 52.0
    start = -90.0
    parts: list[str] = []
    for i, (lab, pct) in enumerate(parsed):
        sweep = 360.0 * pct / 100.0
        a0 = math.radians(start)
        a1 = math.radians(start + sweep)
        large = 1 if sweep > 180 else 0
        x0, y0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
        x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
        parts.append(
            f'<path d="M{_n(cx)} {_n(cy)} L{_n(x0)} {_n(y0)} '
            f'A{_n(r)} {_n(r)} 0 {large} 1 {_n(x1)} {_n(y1)} Z" '
            f'fill="{CHART[i % len(CHART)]}" stroke="{INK}" stroke-width="1.05"/>'
        )
        mid = math.radians(start + sweep / 2)
        if pct >= 8:
            parts.append(_text(cx + r * 0.55 * math.cos(mid), cy + r * 0.55 * math.sin(mid), f"{int(pct)}", size=10))
        start += sweep
    ly = pad
    for i, (lab, pct) in enumerate(parsed):
        lx = pad * 2 + r * 2 + 8
        parts.append(_rect(lx, ly, 10, 10, fill=CHART[i % len(CHART)], sw=0.8))
        parts.append(_text(lx + 14, ly + 6, f"{lab} {int(pct)}%", size=10, anchor="start"))
        ly += 14
    return _svg(min(TABLE_VIEWBOX_MAX, 240), max(pad * 2 + r * 2, ly + 4), "".join(parts))


def _protractor(spec: Mapping[str, Any]) -> str:
    deg = _num(spec["deg"], "deg", 1, 179)
    cx, cy, r = 110.0, 88.0, 72.0
    parts = [
        f'<path d="M{_n(cx - r)} {_n(cy)} A{_n(r)} {_n(r)} 0 0 1 {_n(cx + r)} {_n(cy)}" '
        f'fill="{FAINT}" stroke="{INK}" stroke-width="1.4"/>',
        _line((cx - r, cy), (cx + r, cy), sw=1.2),
    ]
    for d in range(0, 181, 10):
        a = math.radians(180 - d)
        inner = r - (8 if d % 30 == 0 else 4)
        x0, y0 = cx + r * math.cos(a), cy - r * math.sin(a)
        x1, y1 = cx + inner * math.cos(a), cy - inner * math.sin(a)
        parts.append(_line((x0, y0), (x1, y1), sw=0.9))
        if d % 30 == 0:
            tx, ty = cx + (r + 11) * math.cos(a), cy - (r + 11) * math.sin(a)
            parts.append(_text(tx, ty, str(d), size=9))
    a = math.radians(180 - deg)
    parts.append(_line((cx, cy), (cx + r * math.cos(0), cy), sw=1.5))
    parts.append(_line((cx, cy), (cx + r * math.cos(a), cy - r * math.sin(a)), sw=1.5))
    parts.append(f'<circle cx="{_n(cx)}" cy="{_n(cy)}" r="2.2" fill="{INK}"/>')
    return _svg(220, 110, "".join(parts))


def _transform_cells(cells: list[tuple[int, int]], op: str, n: int) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for c, r in cells:
        if op == "rot90":
            out.append((n - 1 - r, c))
        elif op == "rot180":
            out.append((n - 1 - c, n - 1 - r))
        elif op == "rot270":
            out.append((r, n - 1 - c))
        elif op == "flipH":
            out.append((n - 1 - c, r))
        elif op == "flipV":
            out.append((c, n - 1 - r))
        else:
            raise ValueError("op 은 rot90·rot180·rot270·flipH·flipV 여야 합니다")
    return out


def _draw_cell_grid(ox: float, oy: float, n: int, cells: set[tuple[int, int]], size: float) -> str:
    parts = []
    for r in range(n):
        for c in range(n):
            x, y = ox + c * size, oy + r * size
            fill = FILL if (c, r) in cells else PAPER
            parts.append(_rect(x, y, size, size, fill=fill, sw=0.9, stroke=INK))
    return "".join(parts)


def _group_dots(spec: Mapping[str, Any]) -> str:
    """똑같이 나누기 — 묶음 수 × 묶음당 개수. viewBox 240 고정."""
    groups = _int(spec["groups"], "groups", 2, 10)
    each = _int(spec["each"], "each", 1, 12)
    fills = ("#c4a574", "#7eb89a", "#8f9fd4", "#d4a0c8", "#e0a87a", "#c9b56a")
    w, h = TABLE_VIEWBOX_MAX, 150.0
    cols_g = min(groups, 5)
    rows_g = (groups + cols_g - 1) // cols_g
    slot_w = w / cols_g
    slot_h = h / rows_g
    dot_r = 4.2
    parts: list[str] = []
    for g in range(groups):
        gc, gr = g % cols_g, g // cols_g
        ox = gc * slot_w + 6
        oy = gr * slot_h + 6
        bw, bh = slot_w - 12, slot_h - 10
        fill = fills[g % len(fills)]
        parts.append(_rect(ox, oy, bw, bh, rx=6, fill=FAINT, sw=1.05, stroke="#c8c4bc"))
        inner_cols = 1 if bh >= bw else min(each, 3)
        inner_rows = (each + inner_cols - 1) // inner_cols
        gap_x = bw / (inner_cols + 1)
        gap_y = bh / (inner_rows + 1)
        for k in range(each):
            ic, ir = k % inner_cols, k // inner_cols
            cx = ox + gap_x * (ic + 1)
            cy = oy + gap_y * (ir + 1)
            parts.append(
                f'<circle cx="{_n(cx)}" cy="{_n(cy)}" r="{_n(dot_r)}" fill="{fill}" '
                f'stroke="{INK}" stroke-width="0.8"/>'
            )
    return _svg(w, h, "".join(parts))


def _rotate_flip(spec: Mapping[str, Any]) -> str:
    n = _int(spec.get("n", 4), "n", 3, 6)
    op = str(spec["op"])
    raw = spec["cells"]
    if not isinstance(raw, list) or not raw:
        raise ValueError("cells 는 비어 있지 않은 배열이어야 합니다")
    cells: list[tuple[int, int]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError("cells 항목은 [열, 행] 이어야 합니다")
        cells.append((_int(item[0], f"cells[{i}][0]", 0, n - 1), _int(item[1], f"cells[{i}][1]", 0, n - 1)))
    after = _transform_cells(cells, op, n)
    size, pad = 16.0, 8.0
    g = n * size
    parts = [_draw_cell_grid(pad, pad, n, set(cells), size)]
    parts.append(_arrow_right(pad + g + 4, pad + g + 28, pad + g / 2))
    parts.append(_draw_cell_grid(pad + g + 36, pad, n, set(after), size))
    w = pad * 2 + g * 2 + 36
    return _svg(min(w, 240), pad * 2 + g, "".join(parts))


_MOTIF_PTS: dict[str, list[tuple[float, float]]] = {
    "kite": [(0.50, 0.08), (0.88, 0.42), (0.50, 0.92), (0.12, 0.42)],
    "eqTri": [(0.50, 0.10), (0.90, 0.88), (0.10, 0.88)],
    "isoTrap": [(0.30, 0.18), (0.70, 0.18), (0.90, 0.86), (0.10, 0.86)],
    "arrow": [
        (0.50, 0.08),
        (0.88, 0.40),
        (0.68, 0.40),
        (0.68, 0.90),
        (0.32, 0.90),
        (0.32, 0.40),
        (0.12, 0.40),
    ],
    "house": [(0.18, 0.90), (0.18, 0.48), (0.50, 0.12), (0.82, 0.48), (0.82, 0.90)],
    "rhombus": [(0.50, 0.10), (0.88, 0.50), (0.50, 0.90), (0.12, 0.50)],
    "heart": [
        (0.50, 0.88),
        (0.14, 0.50),
        (0.14, 0.32),
        (0.28, 0.16),
        (0.50, 0.32),
        (0.72, 0.16),
        (0.86, 0.32),
        (0.86, 0.50),
    ],
    "para": [(0.28, 0.18), (0.90, 0.18), (0.72, 0.84), (0.10, 0.84)],
    "hourglass": [(0.28, 0.12), (0.72, 0.12), (0.58, 0.50), (0.72, 0.88), (0.28, 0.88), (0.42, 0.50)],
    "z": [
        (0.18, 0.18),
        (0.82, 0.18),
        (0.82, 0.32),
        (0.40, 0.68),
        (0.82, 0.68),
        (0.82, 0.82),
        (0.18, 0.82),
        (0.18, 0.68),
        (0.60, 0.32),
        (0.18, 0.32),
    ],
}

_MOTIF_FILL = {
    "kite": "#e2b48a",
    "eqTri": "#c5d6c2",
    "isoTrap": "#c5d4e8",
    "arrow": "#d7c2e4",
    "house": "#e8d4a8",
    "rhombus": "#d4c0b0",
    "heart": "#e4c2c8",
    "para": "#c5d6c2",
    "hourglass": "#d7c2e4",
    "z": "#c5d4e8",
    "hex": "#e2b48a",
}


def _hex_pts() -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for i in range(6):
        a = math.radians(-90 + 60 * i)
        pts.append((0.5 + 0.38 * math.cos(a), 0.5 + 0.38 * math.sin(a)))
    return pts


def _symmetry_marks(axis: str, pad: float, g: float) -> str:
    if axis == "v":
        x = pad + g / 2
        return _line((x, pad - 2), (x, pad + g + 2), sw=1.2, dash="5 4")
    if axis == "h":
        y = pad + g / 2
        return _line((pad - 2, y), (pad + g + 2, y), sw=1.2, dash="5 4")
    cx, cy = pad + g / 2, pad + g / 2
    return f'<circle cx="{_n(cx)}" cy="{_n(cy)}" r="2.6" fill="{INK}"/>'


def _symmetry_motif(axis: str, motif: str) -> str:
    if motif == "hex":
        unit = _hex_pts()
    elif motif in _MOTIF_PTS:
        unit = _MOTIF_PTS[motif]
    else:
        raise ValueError(f"모르는 대칭 모양입니다: {motif}")
    pad, g = 12.0, 120.0
    swap = axis == "h"
    pts = []
    for x, y in unit:
        if swap:
            x, y = y, x
        pts.append((pad + x * g, pad + y * g))
    fill = _MOTIF_FILL.get(motif, FILL)
    parts = [_poly(pts, fill, 1.4), _symmetry_marks(axis, pad, g)]
    return _svg(pad * 2 + g, pad * 2 + g, "".join(parts))


def _symmetry(spec: Mapping[str, Any]) -> str:
    axis = str(spec["axis"])
    if axis not in {"v", "h", "point"}:
        raise ValueError("axis 는 v·h·point 여야 합니다")
    motif = str(spec.get("motif") or "")
    if motif:
        return _symmetry_motif(axis, motif)
    n = _int(spec.get("n", 5), "n", 3, 8)
    raw = spec.get("cells")
    if not isinstance(raw, list) or not raw:
        raise ValueError("cells 또는 motif 가 필요합니다")
    cells: list[tuple[int, int]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError("cells 항목은 [열, 행] 이어야 합니다")
        cells.append((_int(item[0], f"cells[{i}][0]", 0, n - 1), _int(item[1], f"cells[{i}][1]", 0, n - 1)))
    size, pad = 16.0, 10.0
    g = n * size
    parts = [_draw_cell_grid(pad, pad, n, set(cells), size), _symmetry_marks(axis, pad, g)]
    return _svg(pad * 2 + g, pad * 2 + g, "".join(parts))


def _parse_voxels(spec: Mapping[str, Any]) -> list[tuple[int, int, int]]:
    raw = spec["voxels"]
    if not isinstance(raw, list) or not raw:
        raise ValueError("voxels 는 비어 있지 않은 배열이어야 합니다")
    if len(raw) > 48:
        raise ValueError("voxels 는 48개 이하여야 합니다")
    out: list[tuple[int, int, int]] = []
    seen: set[tuple[int, int, int]] = set()
    for i, item in enumerate(raw):
        if not isinstance(item, list) or len(item) != 3:
            raise ValueError("voxels 항목은 [x, y, z] 이어야 합니다")
        v = (
            _int(item[0], f"voxels[{i}][0]", 0, 6),
            _int(item[1], f"voxels[{i}][1]", 0, 6),
            _int(item[2], f"voxels[{i}][2]", 0, 6),
        )
        if v in seen:
            raise ValueError("같은 칸의 쌓기나무가 두 번 있습니다")
        seen.add(v)
        out.append(v)
    return out


def paint_order(voxels: list[tuple[int, int, int]]) -> list[tuple[int, int, int]]:
    """쌓기나무를 **먼 것부터** 늘어놓는다 (화가 알고리즘).

    카메라는 `View.direction` 이 말하듯 **+x · -y · +z** 쪽에 있다 — 그래서
    `_iso_cube` 가 위·오른쪽·앞면만 그린다. 그러면 큐브 B 가 A 를 가리는 조건은
    **세 축 모두에서 앞**일 때다:  `B.x >= A.x and B.y <= A.y and B.z >= A.z`.
    이때 `x - y + z` 는 B 쪽이 **반드시** 더 크다. 그래서 그 값 오름차순이 곧
    「가려지는 것 먼저」다(값이 같으면 서로 가릴 수 없어 순서가 자유롭다).

    🔴 종전 키는 `(y, x, z)` **내림차순**이었다. y 는 맞았지만 **x·z 가 거꾸로**라
       앞의 큐브를 먼저 그리고 뒤의 큐브를 그 위에 덮었다. 지면에서는 앞쪽 낮은
       큐브의 **윗면이 옆 높은 기둥의 앞면을 뚫고** 나와 계단 모양으로 파였다
       (원장님 2026-08-25 지적, 초6 2-3 공간과 입체 여섯 문항 중 **다섯**).

    ⚠️ 이 함수를 고치면 `scripts/qa/probe-elem-cube-order.py` 가 빨개진다.
       그 판정기는 **이 함수를 그대로 불러** 재므로 규칙이 두 벌이 되지 않는다.
    """
    return sorted(voxels, key=lambda v: (v[0] - v[1] + v[2], v[1], v[0]))


def _iso_cube(view: Any, x: int, y: int, z: int, occ: set[tuple[int, int, int]]) -> str:
    def p(dx: float, dy: float, dz: float) -> tuple[float, float]:
        return view((x + dx, y + dy, z + dz))

    parts = []
    if (x, y, z + 1) not in occ:
        parts.append(_poly([p(0, 0, 1), p(1, 0, 1), p(1, 1, 1), p(0, 1, 1)], FACE_TOP, 1.05))
    if (x + 1, y, z) not in occ:
        parts.append(_poly([p(1, 0, 0), p(1, 1, 0), p(1, 1, 1), p(1, 0, 1)], FACE_SIDE, 1.05))
    if (x, y - 1, z) not in occ:
        parts.append(_poly([p(0, 0, 0), p(1, 0, 0), p(1, 0, 1), p(0, 0, 1)], FACE_FRONT, 1.05))
    return "".join(parts)


def _cell_center_text(cx: float, cy: float, t: Any, size: float = 13) -> str:
    """칸 한가운데. Batang 은 middle 이 시각 중앙보다 위라 central 을 쓴다."""
    return (
        f'<text x="{_n(cx)}" y="{_n(cy)}" fill="{INK}" font-size="{_n(size)}" '
        f'font-family="Batang, serif" font-weight="700" text-anchor="middle" '
        f'dominant-baseline="central">{_esc(t)}</text>'
    )


def _ortho_grid(voxels: list[tuple[int, int, int]], which: str, ox: float, oy: float) -> tuple[str, float, float]:
    xs = [v[0] for v in voxels]
    ys = [v[1] for v in voxels]
    zs = [v[2] for v in voxels]
    cell = 24.0
    title_h = 18.0
    title = {"top": "위", "front": "앞", "side": "옆"}[which]
    gy = oy + title_h
    parts: list[str] = []
    if which == "top":
        w, h = max(xs) + 1, max(ys) + 1
        height: dict[tuple[int, int], int] = {}
        for x, y, z in voxels:
            height[(x, y)] = max(height.get((x, y), 0), z + 1)
        parts.append(_text(ox + w * cell / 2, oy + 8, title, size=13))
        for y in range(h):
            for x in range(w):
                rx, ry = ox + x * cell, gy + (h - 1 - y) * cell
                fill = FILL if (x, y) in height else PAPER
                parts.append(_rect(rx, ry, cell, cell, fill=fill, sw=1.0))
                if (x, y) in height:
                    parts.append(_cell_center_text(rx + cell / 2, ry + cell / 2, str(height[(x, y)])))
        return "".join(parts), w * cell, title_h + h * cell
    if which == "front":
        w, h = max(xs) + 1, max(zs) + 1
        occ = {(x, z) for x, _y, z in voxels}
        parts.append(_text(ox + w * cell / 2, oy + 8, title, size=13))
        for z in range(h):
            for x in range(w):
                rx, ry = ox + x * cell, gy + (h - 1 - z) * cell
                fill = FILL if (x, z) in occ else PAPER
                parts.append(_rect(rx, ry, cell, cell, fill=fill, sw=1.0))
        return "".join(parts), w * cell, title_h + h * cell
    w, h = max(ys) + 1, max(zs) + 1
    occ = {(y, z) for _x, y, z in voxels}
    parts.append(_text(ox + w * cell / 2, oy + 8, title, size=13))
    for z in range(h):
        for y in range(w):
            rx, ry = ox + y * cell, gy + (h - 1 - z) * cell
            fill = FILL if (y, z) in occ else PAPER
            parts.append(_rect(rx, ry, cell, cell, fill=fill, sw=1.0))
    return "".join(parts), w * cell, title_h + h * cell


def _stack_cubes(spec: Mapping[str, Any]) -> str:
    from core.figure_solid import View

    voxels = _parse_voxels(spec)
    views = spec.get("views", ["iso"])
    if isinstance(views, str):
        views = [views]
    if not isinstance(views, list) or not views:
        raise ValueError("views 는 비어 있지 않은 배열이어야 합니다")
    allowed = {"iso", "top", "front", "side"}
    for v in views:
        if v not in allowed:
            raise ValueError("views 는 iso·top·front·side 여야 합니다")
    occ = set(voxels)
    parts: list[str] = []
    pad, gap = 10.0, 18.0
    x_cursor = pad
    height = 40.0
    if "iso" in views:
        scale = 16.0
        probe = View(0.5, 45, scale, (0.0, 0.0))
        corners: list[tuple[float, float]] = []
        for x, y, z in voxels:
            for dx in (0, 1):
                for dy in (0, 1):
                    for dz in (0, 1):
                        corners.append(probe((x + dx, y + dy, z + dz)))
        minx = min(c[0] for c in corners)
        maxx = max(c[0] for c in corners)
        miny = min(c[1] for c in corners)
        maxy = max(c[1] for c in corners)
        view = View(0.5, 45, scale, (x_cursor - minx, pad - miny))
        # 순서 규칙은 `paint_order` 한 곳에 있다 — 판정기가 그것을 그대로 부른다.
        ordered = paint_order(voxels)
        for vx, vy, vz in ordered:
            parts.append(_iso_cube(view, vx, vy, vz, occ))
        x_cursor += (maxx - minx) + gap
        height = max(height, (maxy - miny) + pad)
    for name in ("top", "front", "side"):
        if name not in views:
            continue
        chunk, w, h = _ortho_grid(voxels, name, x_cursor, pad)
        parts.append(chunk)
        x_cursor += w + gap
        height = max(height, h + pad)
    return _svg(x_cursor + pad - gap, height + pad, "".join(parts))


def _outward_off(
    a: tuple[float, float],
    b: tuple[float, float],
    inside: tuple[float, float],
    mag: float,
) -> float:
    """치수 곡선을 입체 바깥으로. +off 는 선분 법선 방향."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length, dx / length
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    if nx * (mx - inside[0]) + ny * (my - inside[1]) >= 0:
        return mag
    return -mag


def _off_towards(
    a: tuple[float, float],
    b: tuple[float, float],
    want: tuple[float, float],
    mag: float,
) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length, dx / length
    if nx * want[0] + ny * want[1] >= 0:
        return mag
    return -mag


def _cuboid(spec: Mapping[str, Any]) -> str:
    from core.figure_solid import View

    w = _num(spec["w"], "w", 0.5, 40)
    d = _num(spec["d"], "d", 0.5, 40)
    h = _num(spec["h"], "h", 0.5, 40)
    mx = max(w, d, h)
    scale = SOLID_UNITS / mx
    # cabinet 45° 에서 깊이 모서리 투영 길이는 0.5·scale·d. 너무 짧으면 치수를 못 붙인다.
    depth_px = 0.5 * scale * d
    if depth_px < 24.0:
        scale *= 24.0 / depth_px
    probe = View(0.5, 45, scale, (0.0, 0.0))
    corners0 = [probe((x, y, z)) for x in (0, w) for y in (0, d) for z in (0, h)]
    minx = min(c[0] for c in corners0)
    maxx = max(c[0] for c in corners0)
    miny = min(c[1] for c in corners0)
    maxy = max(c[1] for c in corners0)
    # 가로=앞 아래, 높이=앞 왼쪽, 세로=밑면 오른쪽 뒤. 위-오른쪽 짧은 모서리는 쓰지 않는다.
    # 왼쪽 높이 라벨의 근사 상자까지 담되 총 폭은 유지한다(44+48 == 종전 40+52).
    # viewBox 폭 문턱(160/320)을 넘나들지 않게 오른쪽 여백을 같은 만큼 줄인다.
    pad_l, pad_t, pad_r, pad_b = _dim_pads((44.0, 22.0, 48.0, 44.0))
    view = View(0.5, 45, scale, (pad_l - minx, pad_t - miny))

    def p(x: float, y: float, z: float) -> tuple[float, float]:
        return view((x, y, z))

    inside = p(w / 2, d / 2, h / 2)
    parts = [
        _poly([p(0, 0, 0), p(w, 0, 0), p(w, 0, h), p(0, 0, h)], FACE_FRONT),
        _poly([p(w, 0, 0), p(w, d, 0), p(w, d, h), p(w, 0, h)], FACE_SIDE),
        _poly([p(0, 0, h), p(w, 0, h), p(w, d, h), p(0, d, h)], FACE_TOP),
    ]
    # 각기둥·각뿔과 같은 기준: 안 보이는 모서리는 점선이다 (09 §4-14).
    verts3 = [(x, y, z) for x in (0.0, w) for y in (0.0, d) for z in (0.0, h)]

    def vi(x: float, y: float, z: float) -> int:
        return verts3.index((x, y, z))

    faces_idx = [
        [vi(0, 0, 0), vi(w, 0, 0), vi(w, 0, h), vi(0, 0, h)],
        [vi(0, d, 0), vi(w, d, 0), vi(w, d, h), vi(0, d, h)],
        [vi(0, 0, 0), vi(0, d, 0), vi(0, d, h), vi(0, 0, h)],
        [vi(w, 0, 0), vi(w, d, 0), vi(w, d, h), vi(w, 0, h)],
        [vi(0, 0, 0), vi(w, 0, 0), vi(w, d, 0), vi(0, d, 0)],
        [vi(0, 0, h), vi(w, 0, h), vi(w, d, h), vi(0, d, h)],
    ]
    parts += _hidden_lines(view, verts3, faces_idx)

    avoid = _DimSpace(_seen_edges(view, [(e[0], e[1]) for e in _box_edges(w, d, h)]))

    def dim(a: tuple[float, float], b: tuple[float, float], label: str) -> None:
        span = math.hypot(b[0] - a[0], b[1] - a[1])
        off = _outward_off(a, b, inside, DIM_OFF if span >= 28 else DIM_OFF + 6)
        off, t = _dim_place(a, b, label, off, avoid, DIM_FS)
        mark = _length_mark(a[0], a[1], b[0], b[1], label, off=off, fs=DIM_FS, t=t)
        parts.append(mark)
        avoid.add(mark, _dim_label_box(a, b, off, label, DIM_FS, t))

    dim(p(0, 0, 0), p(w, 0, 0), f"{_n(w)} cm")
    dim(p(0, 0, 0), p(0, 0, h), f"{_n(h)} cm")
    dim(p(w, 0, 0), p(w, d, 0), f"{_n(d)} cm")
    return _svg((maxx - minx) + pad_l + pad_r, (maxy - miny) + pad_t + pad_b, "".join(parts))


# 서로 다른 꼭짓점의 **화면 x** 가 이보다 가까우면 세로 모서리가 겹쳐 보인다(반지름 1 기준).
# 오각기둥에서 앞왼쪽·뒤왼쪽 모서리가 0.03 차이라 숨은 점선이 실선에 딱 붙었다.
NGON_MIN_GAP = 0.18
# 각뿔에는 세로 모서리가 없다 — 밑면 꼭짓점이 화면 x 로 가까워도 높이가 달라 읽힌다.
# 여기서 x 를 세게 잡으면 정작 겹치는 **모선**을 갈라 줄 각이 남지 않는다.
NGON_MIN_GAP_APEX = 0.08
# 각뿔 모선은 꼭대기에서 부챗살로 퍼진다 — 겹침을 가르는 것은 x 가 아니라 **극각**이다.
# 칠각뿔에서 v2·v3 극각이 1.1° 차이라 숨은 모선이 실선 모선 위에 겹쳐 그려졌다.
# ⚠️ 이 값은 **닿을 수 있는 값**이어야 한다. 부챗살은 실루엣 쪽에서 반드시 몰리므로
#    각형 수가 커지면 아무리 돌려도 못 넘는다(팔각뿔 최선 3.1°). 못 넘으면 최선을 쓴다 —
#    「닿을 수 없는 목표」를 두면 조용히 0°(=안 돌림)로 되돌아간다(CLAUDE.md 2026-08-18).
NGON_MIN_APEX_DEG = 4.0


def _screen_xy(angle: float, ratio: float, deg: float) -> tuple[float, float]:
    """사방투영에서 밑면 위 한 점의 **화면 좌표**(반지름 1, 배율 1, y 는 위가 +).

    깊이 y 가 화면 x 와 화면 y 양쪽에 섞여 들어온다.
    """
    a = math.radians(deg)
    return (
        math.cos(angle) + ratio * math.cos(a) * math.sin(angle),
        ratio * math.sin(a) * math.sin(angle),
    )


def _spread_gaps(
    angles: list[float], ratio: float, deg: float, apex_h: float | None
) -> tuple[float, float]:
    """(가장 가까운 두 꼭짓점의 화면 x 차이, 가장 가까운 두 모선의 극각 차이)."""
    pts = [_screen_xy(a, ratio, deg) for a in angles]
    us = sorted(p[0] for p in pts)
    x_gap = min(b - a for a, b in zip(us, us[1:]))
    if apex_h is None:
        return x_gap, math.inf
    polar = sorted(math.atan2(apex_h - p[1], p[0]) for p in pts)
    return x_gap, min(b - a for a, b in zip(polar, polar[1:]))


def _spread_rotation(
    n: int, base: float, ratio: float, deg: float, apex_h: float | None
) -> float:
    """꼭짓점이 화면에서 겹치지 않을 만큼만 밑면을 돌리는 **추가 각**.

    교과서 배치(옆면 하나가 정면 / 꼭짓점이 정면)를 그대로 두고, 겹칠 때만 필요한
    만큼만 돌린다 — 그래서 **가장 조금 도는** 각부터 본다. 각형 수마다 각도를 손으로
    맞추면 다음 각형에서 또 겹친다 (D-61).

    가로 간격이 먼저다(밑면 윤곽이 무너지면 도형 자체가 안 읽힌다). 그 안에서
    극각 문턱을 넘는 첫 각을 쓰고, 못 넘으면 **가장 나은 각**을 쓴다.
    """
    step = 2 * math.pi / n
    period = 2 * math.pi / n
    min_gap = NGON_MIN_GAP_APEX if apex_h is not None else NGON_MIN_GAP
    best_d, best_gap = 0.0, -1.0
    for k in range(0, 1441):
        for sign in (1.0, -1.0):
            d = sign * math.radians(k * 0.25)
            if abs(d) > period:
                continue
            x_gap, apex_gap = _spread_gaps(
                [base + d + i * step for i in range(n)], ratio, deg, apex_h
            )
            if x_gap < min_gap:
                continue
            if apex_gap >= math.radians(NGON_MIN_APEX_DEG):
                return d
            if apex_gap > best_gap:
                best_d, best_gap = d, apex_gap
            if k == 0:
                break
    return best_d


def _ngon_xy(
    n: int,
    r: float,
    *,
    vertex_front: bool = False,
    ratio: float = 0.5,
    deg: float = 45.0,
    apex_h: float | None = None,
) -> list[tuple[float, float]]:
    base = -math.pi / 2 + (0.0 if vertex_front else -math.pi / n)
    base += _spread_rotation(n, base, ratio, deg, apex_h)
    return [
        (r * math.cos(base + i * 2 * math.pi / n), r * math.sin(base + i * 2 * math.pi / n))
        for i in range(n)
    ]


def _fitted_cabinet(
    points: list[tuple[float, float, float]],
    scale: float,
    pad: tuple[float, float, float, float] = (14.0, 14.0, 14.0, 14.0),
    *,
    ratio: float = 0.5,
    deg: float = 45.0,
):
    from core.figure_solid import View

    probe = View(ratio, deg, scale, (0.0, 0.0))
    pts2 = [probe(p) for p in points]
    minx = min(p[0] for p in pts2)
    maxx = max(p[0] for p in pts2)
    miny = min(p[1] for p in pts2)
    maxy = max(p[1] for p in pts2)
    pl, pt, pr, pb = pad
    view = View(ratio, deg, scale, (pl - minx, pt - miny))
    return view, (maxx - minx) + pl + pr, (maxy - miny) + pt + pb


def _hidden_edges(
    view: Any,
    verts3: list[tuple[float, float, float]],
    faces: list[list[int]],
) -> list[tuple[int, int]]:
    """볼록 입체에서 **숨은 모서리** — 양쪽 면이 둘 다 뒤를 보는 모서리다.

    09 §4-4 는 「관찰자 반대편 꼭짓점에 닿는 모서리」라고 적었는데 그건 직육면체에만
    맞다. 오각기둥·육각뿔에서는 뒤 꼭짓점이 둘 이상이라 손으로 고른 목록이 샌다
    (원장님 2026-08-22: 각기둥이 막힌 덩어리, 각뿔 모선 점선 없음). 면 두 장으로
    판정하면 각형 수와 무관하게 맞는다.

    면의 감김 방향은 믿지 않는다 — 무게중심에서 바깥쪽으로 법선을 돌려세운다.
    감김이 틀리면 숨은 모서리가 통째로 뒤집히는데 그건 화면에서 티가 잘 안 난다.
    """
    from core.figure_solid import cross, dot, sub

    n = len(verts3)
    cen = tuple(sum(p[i] for p in verts3) / n for i in range(3))
    back: list[bool] = []
    for f in faces:
        nrm = cross(sub(verts3[f[1]], verts3[f[0]]), sub(verts3[f[2]], verts3[f[0]]))
        if dot(nrm, sub(verts3[f[0]], cen)) < 0:
            nrm = (-nrm[0], -nrm[1], -nrm[2])
        back.append(view.is_back_facing(nrm))
    seen: dict[tuple[int, int], list[bool]] = {}
    for fi, f in enumerate(faces):
        for i, a in enumerate(f):
            b = f[(i + 1) % len(f)]
            seen.setdefault((min(a, b), max(a, b)), []).append(back[fi])
    return sorted(e for e, flags in seen.items() if len(flags) == 2 and all(flags))


def _hidden_lines(
    view: Any,
    verts3: list[tuple[float, float, float]],
    faces: list[list[int]],
) -> list[str]:
    pts = [view(p) for p in verts3]
    return [
        _line(pts[a], pts[b], sw=1.0, dash=HIDDEN_DASH)
        for a, b in _hidden_edges(view, verts3, faces)
    ]


def _ngon_on_edge(
    n: int,
    ax: float,
    ay: float,
    bx: float,
    by: float,
    prefer: str,
) -> list[tuple[float, float]]:
    side = math.hypot(bx - ax, by - ay) or 1.0
    chosen: list[tuple[float, float]] = []
    for sign in (-1.0, 1.0):
        ang = math.atan2(by - ay, bx - ax)
        pts: list[tuple[float, float]] = [(ax, ay), (bx, by)]
        x, y = bx, by
        for _ in range(n - 2):
            ang += sign * 2 * math.pi / n
            x += side * math.cos(ang)
            y += side * math.sin(ang)
            pts.append((x, y))
        cy = sum(p[1] for p in pts) / n
        ey = (ay + by) / 2
        if (prefer == "min" and cy < ey) or (prefer == "max" and cy > ey):
            return pts
        chosen = pts
    return chosen


# ═══════════════════════════════════════════════════════════════════════════
# 전개도의 **접는 선** (원장님 2026-08-27, `J10504-A05-005`)
#
# 초5 「직육면체의 전개도」 교과서 규약:
#   · **실선 = 자르는 선** — 바깥 윤곽
#   · **점선 = 접는 선** — 면과 면이 맞닿는 안쪽 변
# 지금까지는 면마다 닫힌 실선 `_rect`/`_poly` 를 그려서 안쪽 변과 바깥 윤곽이
# **같은 획**이었다 — 그래서 못 갈랐고, 그림이 전개도가 아니었다.
#
# 규칙을 kind 마다 좌표로 적지 않고 **여기 한 곳**에 둔다 (D-61). kind 는 「면이
# 어디 있나」만 말하고, 「어느 변이 접는 선인가」는 **공유 여부**가 정한다 —
# 그러면 새 전개도 kind 가 같은 결함을 다시 낼 자리가 없다.
#
# 🔴 접는 선 지문은 **치수와 겹치면 안 된다.** 치수는 `#000` 1.4 `6 4` 이고,
#    `scripts/qa/probe-dim-outside.py` 가 그 지문으로 치수를 고른다. 접는 선을
#    그 지문으로 그리면 그 판정기가 전개도 **안쪽**의 접는 선을 전부 「치수가
#    도형 안에 있다」로 세어 거짓 결함이 쏟아진다. 겨냥도 숨은 모서리와 같은
#    지문(`#111111` `5 4`)을 쓴다 — 전개도는 평면이라 숨은 모서리가 없으므로
#    한 그림 안에서 둘이 부딪치지 않는다.
#
# 판정기는 `scripts/qa/probe-elem-net-fold.py` (양성 5 · 음성 5).
# ═══════════════════════════════════════════════════════════════════════════

NET_SW = SOLID_SW   # 전개도도 같은 굵기 — 같은 지면에 나란히 놓인다
# 자르는 선과 접는 선은 **같은 굵기**다 — 갈라 주는 것은 점선이다.
FOLD_DASH = "5 4"


def _rect_ring(x: float, y: float, w: float, h: float) -> list[tuple[float, float]]:
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def _net_face(pts: list[tuple[float, float]], fill: str) -> str:
    """면의 **칠**. 획은 `_net_body` 가 따로 긋는다(그래야 안쪽 변을 가른다).

    ⚠️ 축에 나란한 네모는 `<polygon>` 이 아니라 **`<rect>` 로** 남긴다.
       `probe-dim-outside.py` 는 「가장 큰 `<polygon>`」을 도형 윤곽으로 삼는데,
       전개도 면을 polygon 으로 바꾸면 그 판정기가 **면 한 장**을 도형으로 읽기
       시작한다(실측 2026-08-27: 잰 그림 111 → 129 로 분모가 움직였다). 그리는
       것은 같으니 그쪽 분모를 흔들지 않는 표현을 고른다.
    """
    if len(pts) == 4:
        xs = {round(p[0], 6) for p in pts}
        ys = {round(p[1], 6) for p in pts}
        if len(xs) == 2 and len(ys) == 2:
            # ⚠️ 폭·높이를 **찍는 자리수로 반올림한 꼭짓점에서** 뺀다.
            #    `<rect>` 는 `x` 와 `width` 를 따로 찍고 둘 다 소수 둘째에서 반올림된다.
            #    원래 값에서 폭을 재면 둘이 같이 올림되어 `x + width` 가 이웃 면의 `x`
            #    보다 0.01 커진다 — 맞닿아야 할 두 면이 어긋나고, 그러면 그 변은
            #    「두 면이 공유하는 변」으로 안 읽혀 **접는 선이 아니라 윤곽**이 된다.
            #    실측(2026-08-27): 전개도 40장 중 4장이 그랬다(접는 선 216 → 210).
            x0, x1 = round(min(xs), 2), round(max(xs), 2)
            y0, y1 = round(min(ys), 2), round(max(ys), 2)
            return _rect(x0, y0, x1 - x0, y1 - y0, fill=fill, stroke="none", sw=NET_SW)
    return (
        f'<polygon points="{" ".join(f"{_n(x)},{_n(y)}" for x, y in pts)}" '
        f'fill="{fill}" stroke="none"/>'
    )


def _net_body(faces: list[tuple[list[tuple[float, float]], str]]) -> str:
    """전개도 몸통 — 면은 **칠만**, 바깥 윤곽은 실선, 접는 선은 점선.

    `faces` 는 (꼭짓점 고리, 칠) 목록. 같은 변을 **두 면이 공유**하면 그 변이
    접는 선이다. 윤곽은 변마다 따로 긋지 않고 **한 폴리라인**으로 이어 그린다 —
    변마다 그으면 butt 마개 때문에 모서리마다 톱니가 남는다.

    윤곽이 한 고리로 안 이어지면 **던진다**. 조용히 다른 것을 그리면 잘려도
    아무도 모른다(09 §4-14 와 같은 이유).
    """

    def key(p: tuple[float, float]) -> tuple[float, float]:
        return (round(p[0], 3), round(p[1], 3))

    count: dict[tuple, int] = {}
    for pts, _fill in faces:
        n = len(pts)
        for i in range(n):
            ka, kb = key(pts[i]), key(pts[(i + 1) % n])
            if ka == kb:
                continue
            count[(ka, kb) if ka <= kb else (kb, ka)] = (
                count.get((ka, kb) if ka <= kb else (kb, ka), 0) + 1
            )

    cuts: list[tuple[tuple[float, float], tuple[float, float]]] = []
    folds: list[tuple[tuple[float, float], tuple[float, float]]] = []
    seen: set[tuple] = set()
    for pts, _fill in faces:
        n = len(pts)
        for i in range(n):
            a, b = pts[i], pts[(i + 1) % n]
            ka, kb = key(a), key(b)
            if ka == kb:
                continue
            ek = (ka, kb) if ka <= kb else (kb, ka)
            if ek in seen:
                continue
            seen.add(ek)
            (folds if count[ek] >= 2 else cuts).append((a, b))

    parts = [_net_face(pts, fill) for pts, fill in faces]
    parts.append(_polyline(_net_outline_ring(cuts), sw=NET_SW))
    parts += [_line(a, b, sw=NET_SW, dash=FOLD_DASH) for a, b in folds]
    return "".join(parts)


def _net_outline_ring(
    cuts: list[tuple[tuple[float, float], tuple[float, float]]],
) -> list[tuple[float, float]]:
    """자르는 변들을 **한 고리**로 잇는다(닫는 점을 되풀이해 돌려준다)."""

    def key(p: tuple[float, float]) -> tuple[float, float]:
        return (round(p[0], 3), round(p[1], 3))

    adj: dict[tuple[float, float], list[tuple[float, float]]] = {}
    for a, b in cuts:
        adj.setdefault(key(a), []).append(b)
        adj.setdefault(key(b), []).append(a)
    bad = [k for k, v in adj.items() if len(v) != 2]
    if bad:
        raise ValueError(
            f"전개도 윤곽이 한 고리로 안 이어집니다 — 갈래가 2가 아닌 꼭짓점 {bad[:4]}"
        )
    start = cuts[0][0]
    ring = [start]
    prev, cur = None, start
    while True:
        nxts = adj[key(cur)]
        nxt = nxts[0] if prev is None or key(nxts[0]) != key(prev) else nxts[1]
        prev, cur = cur, nxt
        ring.append(cur)
        if key(cur) == key(start):
            break
    if len(ring) != len(cuts) + 1:
        raise ValueError(
            f"전개도 윤곽이 한 고리가 아닙니다 — 자르는 변 {len(cuts)} 중 {len(ring) - 1} 만 이어집니다"
        )
    return ring


def _net_prism(sides: int) -> str:
    ww, hh = 22.0, 38.0
    # 밑면 각형이 옆면 위·아래로 얼마나 솟는지 손으로 셈하지 않는다 — 변 수가 바뀌면
    # 그 셈이 어긋나 꼭짓점이 잘렸다(내접원 반지름을 썼는데 정오각형은 그보다 높다).
    # `_svg` 가 그린 것을 다 담게 viewBox 를 맞춘다 (09 §4-14).
    pad_x, pad_t, pad_b = 10.0, 10.0, 10.0
    ox, oy = pad_x, pad_t
    # 옆면 n 장은 세로 변끼리, 두 밑면은 첫 옆면의 가로 변에 맞닿는다 — 그 변들이
    # **접는 선**이다. 어느 변인지는 `_net_body` 가 공유 여부로 정한다(손으로 안 짚는다).
    faces = [
        (_rect_ring(ox + i * ww, oy, ww, hh), FACE_FRONT if i % 2 == 0 else FACE_SIDE)
        for i in range(sides)
    ]
    faces.append((_ngon_on_edge(sides, ox, oy, ox + ww, oy, "min"), FACE_TOP))
    faces.append((_ngon_on_edge(sides, ox, oy + hh, ox + ww, oy + hh, "max"), FACE_TOP))
    return _svg(pad_x * 2 + sides * ww, pad_t + hh + pad_b, _net_body(faces))


def _prism(spec: Mapping[str, Any]) -> str:
    sides = _int(spec["sides"], "sides", 3, 8)
    _num(spec["h"], "h", 0.5, 20)
    if spec.get("net"):
        return _net_prism(sides)
    r, h = 1.0, 1.5
    xy = _ngon_xy(sides, r)
    bot3 = [(x, y, 0.0) for x, y in xy]
    top3 = [(x, y, h) for x, y in xy]
    view, svg_w, svg_h = _fitted_cabinet(bot3 + top3, 48.0)
    bot = [view(p) for p in bot3]
    top = [view(p) for p in top3]
    verts3 = bot3 + top3
    # 밑면 · 윗면 · 옆면 n 장. 감김은 `_hidden_edges` 가 무게중심으로 바로잡는다.
    faces_idx = [list(range(sides)), [sides + i for i in range(sides)]]
    for i in range(sides):
        j = (i + 1) % sides
        faces_idx.append([i, j, sides + j, sides + i])
    faces: list[tuple[float, str]] = []
    for i in range(sides):
        j = (i + 1) % sides
        depth = (bot3[i][1] + bot3[j][1]) / 2
        fill = FACE_FRONT if depth < 0 else FACE_SIDE
        faces.append((depth, _poly([bot[i], bot[j], top[j], top[i]], fill, SOLID_SW)))
    faces.sort(key=lambda t: t[0], reverse=True)
    # 숨은 모서리는 **맨 위에** 그린다. 면 아래에 깔면 칠에 덮여 겨냥도가 막힌
    # 덩어리가 된다 — 그러면 면·모서리를 셀 수 없다(원장님 2026-08-22).
    parts = (
        [svg for _, svg in faces]
        + [_poly(top, FACE_TOP, 1.2)]
        + _hidden_lines(view, verts3, faces_idx)
    )
    return _svg(svg_w, svg_h, "".join(parts))


def _pyramid(spec: Mapping[str, Any]) -> str:
    sides = _int(spec["sides"], "sides", 3, 8)
    _num(spec["h"], "h", 0.5, 20)
    r, h = 1.0, 1.45
    # 꼭짓점을 카메라 쪽으로 — 앞면 하나를 정면으로 보면 삼각뿔이 납작한 삼각형이 된다.
    # `apex_h` 를 주면 모선끼리 겹치지 않는 각까지 같이 본다.
    xy = _ngon_xy(sides, r, vertex_front=True, apex_h=h)
    base3 = [(x, y, 0.0) for x, y in xy]
    apex3 = (0.0, 0.0, h)
    view, svg_w, svg_h = _fitted_cabinet(base3 + [apex3], 50.0, (14.0, 18.0, 14.0, 16.0))
    base = [view(p) for p in base3]
    apex = view(apex3)
    verts3 = base3 + [apex3]
    # 밑면 + 옆면 n 장. 밑면 모서리만 보고 숨김을 정하면 **모선**(꼭대기→뒤 꼭짓점)이
    # 실선으로 남는다 — 원장님이 「모선 점선이 없음」이라 하신 자리다.
    faces_idx = [list(range(sides))] + [
        [i, (i + 1) % sides, sides] for i in range(sides)
    ]
    faces: list[tuple[float, str]] = []
    for i in range(sides):
        j = (i + 1) % sides
        depth = (base3[i][1] + base3[j][1]) / 2
        fill = FACE_FRONT if depth < 0 else FACE_SIDE
        faces.append((depth, _poly([base[i], base[j], apex], fill, SOLID_SW)))
    faces.sort(key=lambda t: t[0], reverse=True)
    parts = (
        [_poly(base, FACE_TOP, 1.1)]
        + [svg for _, svg in faces]
        + _hidden_lines(view, verts3, faces_idx)
    )
    return _svg(svg_w, svg_h, "".join(parts))


def _split_ring(
    ring: list[tuple[float, float]], i0: int, i1: int
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """고리를 두 점에서 잘라 (가까운 호, 먼 호). 화면 아래쪽이 가까운 호다."""
    n = len(ring)

    def walk(a: int, b: int) -> list[tuple[float, float]]:
        pts = [ring[a]]
        i = a
        for _ in range(n):
            if i == b:
                return pts
            i = (i + 1) % n
            pts.append(ring[i])
        return pts

    one, two = walk(i0, i1), walk(i1, i0)

    def mid_y(pts: list[tuple[float, float]]) -> float:
        return sum(p[1] for p in pts) / len(pts)

    return (one, two) if mid_y(one) >= mid_y(two) else (two, one)


def _round_ring(view: Any, pts3: list[tuple[float, float, float]]) -> list[tuple[float, float]]:
    ring = [view(p) for p in pts3]
    if math.hypot(ring[0][0] - ring[-1][0], ring[0][1] - ring[-1][1]) < 0.05:
        ring = ring[:-1]
    return ring


# 원기둥의 치수 여백 — 왼쪽에 높이 라벨, 오른쪽은 라벨이 안 선다.
# 구가 **같은 값**을 읽는다(아래). 손으로 두 번 적으면 한쪽만 고쳐도 아무도 모른다.
CYL_PADS = (44.0, 24.0, 10.0, 24.0)

# 구의 틀 — **원기둥과 같은 «도형 ÷ 틀» 비율**이라야 종이에서 같은 크기로 나온다.
# 지면 폭은 등급이 정하므로(compact 140px) 종이에서의 크기는 그 비율이 전부다.
#
# 🔴 실측 2026-08-29: 옛 판은 `pr` 이 날 리터럴 36 · 틀이 140 이라 72/140 = **51.4%**
#    였다. 같은 반지름인 원기둥(112.7/160 = 70.4%)보다 종이에서 **27% 작다**
#    (지름 72px vs 98.6px). 구는 `ROUND_UNITS` 를 안 써서 2026-08-29 의 +15% 확대에도
#    **혼자 안 따라왔다** — 상수를 안 쓰는 리터럴은 이렇게 조용히 뒤처진다
#    (§4-20-d 의 `0.32` 와 같은 자리, 이번엔 크기 축이다).
#
# ⚠️ 구는 라벨이 없어 여백이 필요 없다. 그래서 여백을 깎아 「최대로」 키우면
#    이번엔 **원기둥보다 커진다.** 한 지면에 두 입체가 같이 나오므로 집안의
#    상한(원기둥)에 맞춘다 — 원장님 2026-08-29 「회전체도 등급 안 넘게 최대로」.
#    세로는 라벨이 없으니 획 몫만 둔다(여백을 두면 지면만 길어진다).
SPHERE_PAD_W = sum(_dim_pads(CYL_PADS)[0::2])
SPHERE_PAD_H = 4.0


def _cylinder(spec: Mapping[str, Any]) -> str:
    from core.figure_solid import circle3

    r = _num(spec["r"], "r", 0.4, 20)
    h = _num(spec["h"], "h", 0.4, 30)
    scale = ROUND_UNITS / max(2 * r, h)
    bot3 = circle3((0, 0, 0), r, (0, 0, 1), 64)
    top3 = circle3((0, 0, h), r, (0, 0, 1), 64)
    view, svg_w, svg_h = _fitted_cabinet(
        # 왼쪽 높이 라벨 halo 를 4px 더 담되 총 폭은 유지한다(44+26 == 40+30).
        # 오른쪽 26 은 **놀던 여백**이었다 — 원기둥은 오른쪽에 라벨을 안 놓는다.
        # 실측(2026-08-29): viewBox 159.3 중 오른쪽 22.8 에 내용이 하나도 없었다.
        bot3 + top3, scale, _dim_pads(CYL_PADS), ratio=ROUND_RATIO, deg=ROUND_DEG
    )
    top = _round_ring(view, top3)
    bot = _round_ring(view, bot3)
    # 축에 나란한 타원이라 좌·우 끝이 곧 모선이 닿는 자리다.
    i_l = min(range(len(bot)), key=lambda i: bot[i][0])
    i_r = max(range(len(bot)), key=lambda i: bot[i][0])
    near_bot, far_bot = _split_ring(bot, i_l, i_r)
    near_top, _far_top = _split_ring(top, i_l, i_r)
    if near_top[0][0] > near_top[-1][0]:
        near_top = near_top[::-1]
    if near_bot[0][0] < near_bot[-1][0]:
        near_bot = near_bot[::-1]
    # 옆면은 곧은 사다리꼴이 아니다 — 위·아래 앞쪽 호를 그대로 잇는다.
    # 예전처럼 네 점 사각형으로 덮으면 밑면 타원을 가로지르는 실선이 남는다.
    parts = [
        _poly(near_top + near_bot, FACE_FRONT, SOLID_SW),
        _polyline(far_bot, sw=1.05, dash=HIDDEN_DASH),
        _poly(top, FACE_TOP, SOLID_SW),
    ]
    tl, bl = top[i_l], bot[i_l]
    c_top = view((0.0, 0.0, h))
    rim = top[i_r]
    # 높이는 왼쪽 모선 바깥, 반지름은 윗면 안 — 둘 다 measured() 하나로 (09 §2.1).
    parts.append(
        _length_mark(
            tl[0], tl[1], bl[0], bl[1], f"{_n(h)} cm",
            off=_off_towards(tl, bl, (-1.0, 0.0), DIM_OFF), fs=DIM_FS,
        )
    )
    # 반지름은 **안 적는다** (원장님 확정 2026-08-22): 「문제에 굳이 있는데 라벨로
    # 이중표기해서 너저분해질 필요가 없을듯」. 값을 쓰는 갈래의 발문이
    # 「밑면의 반지름이 $2$ cm 인 원기둥의 밑면의 지름은?」이라 **발문이 이미 말한다.**
    #
    # 높이는 **남긴다** — 어느 발문도 높이를 말하지 않아 이중표기가 아니다.
    # 둘 다 빼면 설명 없는 점선만 남는다(§4-20 사다리꼴과 같은 자리).
    #
    # 중심 점도 같이 뺐다. 반지름 라벨이 없으면 그 점은 **설명 없는 표시**다.
    #
    # ⚠️ 이러면 「그린 r:h 가 스펙과 맞는가」를 지면에서 아무도 안 본다.
    #    끄는 게 아니라 옮긴다 — 시험이 SVG 에서 직접 잰다 (09 §4-20-a).
    _ = rim
    return _svg(svg_w, svg_h, "".join(parts))


def _cone(spec: Mapping[str, Any]) -> str:
    from core.figure_solid import circle3

    r = _num(spec["r"], "r", 0.4, 20)
    h = _num(spec["h"], "h", 0.4, 30)
    scale = ROUND_UNITS / max(2 * r, h)
    base3 = circle3((0, 0, 0), r, (0, 0, 1), 64)
    apex3 = (0.0, 0.0, h)
    view, svg_w, svg_h = _fitted_cabinet(
        base3 + [apex3], scale, _dim_pads((18.0, 20.0, 18.0, 16.0)), ratio=ROUND_RATIO, deg=ROUND_DEG
    )
    apex = view(apex3)
    ring = _round_ring(view, base3)
    n = len(ring)

    def polar(p: tuple[float, float]) -> float:
        return math.atan2(p[1] - apex[1], p[0] - apex[0])

    # 꼭대기에서 타원에 그은 두 접선이 모선이다. 좌·우 끝점이 아니다 (09 §4-13).
    i_right = min(range(n), key=lambda i: polar(ring[i]))
    i_left = max(range(n), key=lambda i: polar(ring[i]))
    near, far = _split_ring(ring, i_right, i_left)
    parts = [
        _poly([apex] + near, FACE_FRONT, SOLID_SW),
        _polyline(far, sw=1.05, dash=HIDDEN_DASH),
    ]
    return _svg(svg_w, svg_h, "".join(parts))


def _sphere(spec: Mapping[str, Any]) -> str:
    r = _num(spec["r"], "r", 0.4, 20)
    # 지름이 곧 `ROUND_UNITS` — 같은 반지름의 원기둥 지름(2r·scale)과 같은 길이다.
    pr = ROUND_UNITS / 2.0
    svg_w = ROUND_UNITS + SPHERE_PAD_W
    svg_h = ROUND_UNITS + 2 * SPHERE_PAD_H
    cx, cy = svg_w / 2.0, svg_h / 2.0
    parts = [
        f'<circle cx="{_n(cx)}" cy="{_n(cy)}" r="{_n(pr)}" fill="{FACE_TOP}" '
        f'stroke="{INK}" stroke-width="1.4"/>',
        # 적도도 **같은 상수**를 쓴다. 예전엔 여기만 날 리터럴 `0.32` 라
        # `ROUND_RATIO` 를 조여도 구는 안 따라왔다 (09 §4-20-d).
        f'<ellipse cx="{_n(cx)}" cy="{_n(cy)}" rx="{_n(pr)}" ry="{_n(pr * ROUND_RATIO)}" '
        f'fill="none" stroke="{INK}" stroke-width="1.05" stroke-dasharray="5 4"/>',
    ]
    # 반지름은 **안 적는다** (원장님 확정 2026-08-22, 이중표기). 값을 쓰는 갈래의 발문이
    # 「반지름이 $3$ cm 인 구의 지름은?」이라 발문이 이미 말한다. 나머지 갈래는 아예
    # 수를 안 쓰는 개념 문항이라(「구를 잘라도 잘린 면은?」) 라벨이 할 일이 없다.
    #
    # 이걸로 §4-16 위반도 같이 사라진다 — 여기가 저장소에서 **유일한 날 텍스트 치수**였다.
    # halo 로 바꿔 남기는 선택지도 있었지만, 이중표기라 뺀다.
    #
    # ⚠️ `pr` 은 리터럴 36 이라 **그림이 `r` 을 한 톨도 안 담는다**(r=1 과 r=20 이 같은 원).
    #    지금 구 문항은 길이를 그림에서 읽지 않으니 성립하지만, 「그림을 보고 반지름을
    #    구하시오」가 생기면 그 순간 못 쓴다. 시험이 그 사실을 **적어 두고 있다.**
    _ = r
    return _svg(svg_w, svg_h, "".join(parts))


def _net_cuboid(spec: Mapping[str, Any]) -> str:
    w = _num(spec["w"], "w", 0.5, 20)
    d = _num(spec["d"], "d", 0.5, 20)
    h = _num(spec["h"], "h", 0.5, 20)
    extra_l, extra_t, extra_r, extra_b = 32.0, 16.0, 16.0, 32.0
    span_w = d + w + d
    span_h = d + h + d + h
    u = min(22.0, (208.0 - extra_l - extra_r) / span_w, (200.0 - extra_t - extra_b) / span_h)
    ww, dd, hh = w * u, d * u, h * u
    #     [top]
    # [L][front][R]
    #     [bot]
    #     [back]
    ox, oy = extra_l + dd, extra_t
    # 여섯 면이 맞닿는 다섯 변이 **접는 선**이다(면 6장 - 1). 어느 변인지는
    # `_net_body` 가 공유 여부로 정한다 — 좌표로 짚으면 w·d·h 가 바뀔 때 어긋난다.
    parts = [
        _net_body(
            [
                (_rect_ring(ox, oy, ww, dd), FACE_TOP),
                (_rect_ring(ox - dd, oy + dd, dd, hh), FACE_SIDE),
                (_rect_ring(ox, oy + dd, ww, hh), FACE_FRONT),
                (_rect_ring(ox + ww, oy + dd, dd, hh), FACE_SIDE),
                (_rect_ring(ox, oy + dd + hh, ww, dd), FACE_TOP),
                (_rect_ring(ox, oy + dd + hh + dd, ww, hh), FACE_FRONT),
            ]
        )
    ]
    # 면 안 곱셈(7×4)은 치수가 아니다. 직육면체만 변 밖에 cm.
    if not (w == d == h):
        back_y = oy + dd + hh + dd + hh
        parts.append(_length_mark(ox, back_y, ox + ww, back_y, f"{_n(w)} cm", off=12, fs=11))
        parts.append(_length_mark(ox, oy, ox, oy + dd, f"{_n(d)} cm", off=12, fs=11))
        parts.append(
            _length_mark(ox - dd, oy + dd, ox - dd, oy + dd + hh, f"{_n(h)} cm", off=12, fs=11)
        )
    width = extra_l + dd + ww + dd + extra_r
    height = extra_t + dd + hh + dd + hh + extra_b
    return _svg(width, height, "".join(parts))


# 원기둥 전개도: 원은 옆면 직사각형의 긴 변(둘레)에만 접한다.
# 짧은 변(높이)에 붙이면 접을 수 없는 그림이 된다. t 는 긴 변 위 접점 비율.
_NET_CYL_LAYOUTS: dict[str, tuple[tuple[str, float], tuple[str, float]]] = {
    "opp": (("top", 0.28), ("bot", 0.72)),
    "oppFlip": (("top", 0.72), ("bot", 0.28)),
    "oppMid": (("top", 0.5), ("bot", 0.5)),
    "sameTop": (("top", 0.25), ("top", 0.75)),
    "sameBot": (("bot", 0.25), ("bot", 0.75)),
    "ends": (("top", 0.22), ("bot", 0.78)),
}


def _net_cylinder(spec: Mapping[str, Any]) -> str:
    r = _num(spec["r"], "r", 0.4, 20)
    h = _num(spec["h"], "h", 0.4, 30)
    pi = _num(spec.get("pi", 3), "pi", 3, 3.15)
    raw = spec.get("layout", "opp")
    name = str(raw)
    if name not in _NET_CYL_LAYOUTS:
        raise ValueError(f"layout 은 {', '.join(_NET_CYL_LAYOUTS)} 중 하나여야 합니다")
    circ = 2 * r * pi
    u = ROUND_UNITS / max(circ, h, r * 2)
    rw, rh, cr = circ * u, h * u, r * u
    circles: list[tuple[float, float]] = []
    for side, t in _NET_CYL_LAYOUTS[name]:
        cx = t * rw
        cy = -cr if side == "top" else rh + cr
        circles.append((cx, cy))
    pad = 8.0
    xs = [0.0, rw] + [c[0] - cr for c in circles] + [c[0] + cr for c in circles]
    ys = [0.0, rh] + [c[1] - cr for c in circles] + [c[1] + cr for c in circles]
    minx, miny = min(xs), min(ys)
    ox, oy = pad - minx, pad - miny
    parts = [_rect(ox, oy, rw, rh, fill=FACE_FRONT, sw=SOLID_SW)]
    for cx, cy in circles:
        parts.append(
            f'<circle cx="{_n(ox + cx)}" cy="{_n(oy + cy)}" r="{_n(cr)}" fill="{FACE_TOP}" '
            f'stroke="{INK}" stroke-width="{_n(SOLID_SW)}"/>'
        )
    return _svg(max(xs) - minx + pad * 2, max(ys) - miny + pad * 2, "".join(parts))

# ═══════════════════════════════════════════════════════════════════════════
# netCone — 원뿔의 전개도 (물결 4A, 2026-08-24)
#
# 막고 있던 것: RPM 1-2 「17 회전체의 전개도」와 「19 전개도가 주어진 원뿔의 겉넓이와
# 부피」. 정본은 RPM 1-2 0887·0888(p133)·0801(p121) — **모양만** 본다.
#   · 옆면은 부채꼴, 밑면은 원. 원은 호에 **닿아** 있다(0801). 떨어뜨리면 어디에
#     붙는 원인지 안 보인다(`netCylinder` 의 §4-12 와 같은 결함).
#   · 부채꼴은 꼭짓점이 **위**, 호가 아래.
#   · 치수는 **모선과 중심각**만 적는다 — 밑면 반지름은 그 둘이 정하므로 이중표기다
#     (§4-16 · `sphere` 의 선례). 0887·0888 도 모선만 적는다.
#     발문이 반지름을 이미 말한 갈래를 위해 `labels` 로 켤 수는 있다(§4-20-b).
#
# ## 중심각은 임의가 아니다 — **r 과 l 이 정한다**
#
#     (중심각) = (밑면 둘레) ÷ (모선이 반지름인 원의 둘레) × 360 = 360 r / l
#
# 그래서 **한 배율**(`u`)로 부채꼴 반지름 `l·u` 와 밑면 반지름 `r·u` 를 그리면
# 호의 길이와 밑면 둘레가 **저절로 같아진다.** 시험이 그 둘을 재서 견준다 —
# 그림이 곧 검산이다(좌표를 손으로 맞추면 이 성질이 조용히 깨진다).
#
# ## 던지는 것 (D-70)
#
#   · `l <= r` — 중심각이 360° 이상이 되어 원뿔이 아니다(모선은 밑면 반지름보다 길다).
#   · 중심각이 **정수 도가 아니면** — 교과 전개도는 전부 정수 도이고, 소수 도는
#     각도기로 못 읽는다. 그런 (r, l) 은 전개도가 아니라 겨냥도(`cone`)로 내야 한다.
#   · 중심각이 `NC_DEG_MIN` 미만 / `NC_DEG_MAX` 초과 — 실오라기이거나 거의 닫힌 원이라
#     부채꼴로 안 읽힌다.
#
# ## 지면 폭을 박는다
#
# 중심각이 움직이면 경계 상자가 크게 달라져 폭이 떠다닌다 — 그러면 같은 kind 인데
# 지면 등급이 그림마다 뒤집힌다(09 §4-24 ㉠). `NC_VIEWBOX` 로 박고, 그 안에 들어가게
# 배율을 정한 다음 가운데에 놓는다.
# ═══════════════════════════════════════════════════════════════════════════

NC_VIEWBOX = 240.0      # 지면 등급 mid — `CP_VIEWBOX` 와 같은 이유다
NC_DEG_MIN = 30.0       # 중심각 하한 — 이보다 좁으면 부채꼴이 실오라기다
NC_DEG_MAX = 330.0      # 중심각 상한 — 이보다 넓으면 거의 닫힌 원이 된다
NC_PAD = 10.0           # 그림 둘레 여백
NC_LABEL_FS = 11.0      # 치수 글자 — `netCuboid` 와 같은 값
NC_ANG_R = 20.0         # 꼭짓점 각 표시 호의 반지름(화면 단위)
NC_LABELS = ("slant", "angle", "radius")


def _nc_polar(deg: float, rad: float) -> tuple[float, float]:
    """화면 좌표계 극좌표 — 아래가 +y 이므로 90° 가 «아래»다."""
    return rad * math.cos(math.radians(deg)), rad * math.sin(math.radians(deg))


def _nc_arc_d(cx: float, cy: float, rad: float, a0: float, a1: float) -> str:
    """중심 (cx,cy)·반지름 rad 인 원호를 a0 → a1(도) 로 그리는 path 조각(`A ...`)."""
    x1, y1 = _nc_polar(a1, rad)
    large = 1 if a1 - a0 > 180 else 0
    return f"A {_n(rad)} {_n(rad)} 0 {large} 1 {_n(cx + x1)} {_n(cy + y1)}"


def _net_cone(spec: Mapping[str, Any]) -> str:
    r = _num(spec["r"], "r", 0.5, 20)
    l = _num(spec["l"], "l", 0.5, 40)
    if l <= r:
        raise ValueError(
            f"모선 {_n(l)} 이 밑면 반지름 {_n(r)} 이하입니다 — 원뿔이 아닙니다 (l > r 이어야 합니다)"
        )
    deg = 360.0 * r / l
    if abs(deg - round(deg)) > 1e-9:
        raise ValueError(
            f"중심각이 {deg:.4f}° 라 정수 도가 아닙니다 — 전개도로 못 냅니다. "
            "360r/l 이 정수가 되는 r·l 을 고르거나 겨냥도(cone)를 쓰십시오"
        )
    deg = float(round(deg))
    if not NC_DEG_MIN <= deg <= NC_DEG_MAX:
        raise ValueError(
            f"중심각 {deg:.0f}° 는 {NC_DEG_MIN:.0f}~{NC_DEG_MAX:.0f}° 밖입니다 — 부채꼴로 안 읽힙니다"
        )

    raw = spec.get("labels", ["slant", "angle"])
    if not isinstance(raw, list) or any(v not in NC_LABELS for v in raw):
        raise ValueError(f"labels 는 {', '.join(NC_LABELS)} 중에서 고른 배열이어야 합니다")
    labels = set(raw)

    # ── cm 자리 (부채꼴 꼭짓점이 원점, 아래로 벌어진다) ───────────────
    a0, a1 = 90.0 - deg / 2, 90.0 + deg / 2
    base_cy = l + r  # 밑면 원은 호 한가운데(꼭짓점 바로 아래)에 **닿는다**
    xs = [0.0, -r, r]
    ys = [0.0, base_cy - r, base_cy + r]
    for d in (a0, a1, 0.0, 90.0, 180.0, 270.0):
        if a0 - 1e-9 <= d <= a1 + 1e-9:
            x, y = _nc_polar(d, l)
            xs.append(x)
            ys.append(y)
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)

    # 배율 — **박힌 폭** 안에 들어가게. 치수 글자 자리를 미리 뺀다. `_svg` 는 `<text>` 의
    # 닻점만 세므로 여기서 안 잡으면 지면에서 글자가 프레임 밖으로 나간다.
    room = _label_w_max(f"{_n(l)} cm", NC_LABEL_FS) if "slant" in labels else 0.0
    avail_w = NC_VIEWBOX - 2 * NC_PAD - 2 * room
    avail_h = NC_VIEWBOX - 2 * NC_PAD
    u = min(avail_w / (maxx - minx), avail_h / (maxy - miny))
    ox = (NC_VIEWBOX - (maxx - minx) * u) / 2 - minx * u
    oy = NC_PAD - miny * u

    def scr(d: float, rad: float) -> tuple[float, float]:
        x, y = _nc_polar(d, rad)
        return ox + x * u, oy + y * u

    px0, py0 = scr(a0, l)
    parts = [
        f'<path d="M {_n(ox)} {_n(oy)} L {_n(px0)} {_n(py0)} '
        f'{_nc_arc_d(ox, oy, l * u, a0, a1)} Z" '
        f'fill="{FACE_FRONT}" stroke="{INK}" stroke-width="{_n(SOLID_SW)}"/>',
        f'<circle cx="{_n(ox)}" cy="{_n(oy + base_cy * u)}" r="{_n(r * u)}" '
        f'fill="{FACE_TOP}" stroke="{INK}" stroke-width="{_n(SOLID_SW)}"/>',
    ]
    if "slant" in labels:
        # 모선은 **왼쪽** 직선 변에 적는다(0887 과 같은 자리).
        parts.append(_length_mark(px0, py0, ox, oy, f"{_n(l)} cm", off=12, fs=NC_LABEL_FS))
    if "angle" in labels:
        parts.append(
            f'<path d="M {_n(ox + _nc_polar(a0, NC_ANG_R)[0])} '
            f'{_n(oy + _nc_polar(a0, NC_ANG_R)[1])} {_nc_arc_d(ox, oy, NC_ANG_R, a0, a1)}" '
            f'fill="none" stroke="{INK}" stroke-width="1.0"/>'
        )
        lx, ly = scr(90.0, (NC_ANG_R + 11.0) / u)
        parts.append(_text(lx, ly, f"{deg:.0f}°", size=NC_LABEL_FS, weight="400"))
    if "radius" in labels:
        cy = oy + base_cy * u
        parts.append(_length_mark(ox, cy, ox + r * u, cy, f"{_n(r)} cm", off=-9, fs=NC_LABEL_FS))

    return _fixed_width_svg(
        NC_VIEWBOX, oy + maxy * u + NC_PAD, "".join(parts), "원뿔 전개도", "치수 글자를 줄이십시오"
    )



def _area_box(base: float, height: float) -> tuple[float, float]:
    """cm 비율을 유지한다. 고정 140×70 이면 4×5와 9×8이 같은 직사각형이 된다."""
    px = 14.0
    max_w, max_h = 152.0, 110.0
    bw, bh = base * px, height * px
    scale = min(1.0, max_w / bw, max_h / bh)
    return bw * scale, bh * scale


def _area_poly(spec: Mapping[str, Any]) -> str:
    shape = str(spec["shape"])
    base = _num(spec["base"], "base", 0.5, 40)
    height = _num(spec["height"], "height", 0.5, 40)
    pad = 16.0
    # 마름모의 세로 길이는 **적히는 값**(`d2`)이다. 세로 자리에 `height` 를 쓰면
    # `d2` 를 따로 준 순간 그림과 라벨이 어긋난다 — 「4」 길이로 그려 놓고 「8 cm」로
    # 적는다. 지금 부르는 쪽은 늘 `height == d2` 라 안 드러날 뿐이다(09 §4-20).
    vertical = _num(spec.get("d2", height), "d2", 0.5, 40) if shape == "rhombus" else height
    bw, bh = _area_box(base, vertical)
    # 세로 치수를 오른쪽 바깥에 놓고 긴 라벨 halo 까지 담는다. 최대 폭은 236px 로
    # 종전 208px 와 같은 figureSvgFrame mid 등급(161~320)이다.
    extra_r, extra_b = 52.0, 18.0
    parts: list[str] = []
    if shape == "rect":
        parts.append(_rect(pad, pad, bw, bh, fill=FAINT, sw=1.4))
        parts.append(_length_mark(pad, pad + bh, pad + bw, pad + bh, f"{_n(base)} cm", off=12))
        parts.append(_length_mark(pad + bw, pad, pad + bw, pad + bh, f"{_n(height)} cm", off=-12))
    elif shape == "tri":
        pts = [(pad, pad + bh), (pad + bw, pad + bh), (pad + bw * 0.45, pad)]
        parts.append(_poly(pts, FAINT, 1.4))
        parts.append(_length_mark(pts[0][0], pts[0][1], pts[1][0], pts[1][1], f"{_n(base)} cm", off=12))
        hx = pad + bw + 8.0
        parts.append(_length_mark(hx, pad, hx, pad + bh, f"{_n(height)} cm", off=-12))
    elif shape == "para":
        skew = min(bw * 0.22, bh * 0.4)
        pts = [(pad + skew, pad), (pad + bw, pad), (pad + bw - skew, pad + bh), (pad, pad + bh)]
        parts.append(_poly(pts, FAINT, 1.4))
        parts.append(_length_mark(pts[3][0], pts[3][1], pts[2][0], pts[2][1], f"{_n(base)} cm", off=12))
        hx = pad + bw + 8.0
        parts.append(_length_mark(hx, pad, hx, pad + bh, f"{_n(height)} cm", off=-12))
    elif shape == "trap":
        top = _num(spec.get("top", base * 0.5), "top", 0.5, 40)
        tw = bw * (top / base)
        ox = pad + (bw - tw) / 2
        pts = [(ox, pad), (ox + tw, pad), (pad + bw, pad + bh), (pad, pad + bh)]
        parts.append(_poly(pts, FAINT, 1.4))
        parts.append(_length_mark(pts[3][0], pts[3][1], pts[2][0], pts[2][1], f"{_n(base)} cm", off=12))
        parts.append(_length_mark(pts[0][0], pts[0][1], pts[1][0], pts[1][1], f"{_n(top)} cm", off=-10))
        # 높이는 도형 오른쪽 바깥에서 윗변·아랫변 사이의 수직 거리를 잰다. 도형 안의
        # 보조선 위에 measured() 를 겹치면 치수 곡선과 라벨이 도형을 가로지른다.
        hx = pad + bw + 8.0
        parts.append(
            _length_mark(hx, pad, hx, pad + bh, f"{_n(height)} cm", off=-12)
        )
    elif shape == "rhombus":
        d2 = vertical
        cx, cy = pad + bw / 2, pad + bh / 2
        pts = [(cx, pad), (pad + bw, cy), (cx, pad + bh), (pad, cy)]
        parts.append(_poly(pts, FAINT, 1.4))
        # 마름모는 **라벨을 안 적는다** (원장님 확정 2026-08-22):
        # 「충분히 도형 크기가 크지 않으면 그냥 문제에 적어두고 내부에는 라벨 표기 안 하는
        #  걸로 하자. 표기하니까 오히려 너저분해지는듯」. 네 안(대각선 자체가 치수선 /
        # 삼각형처럼 아래로 / 둘 다 바깥 / 둘 다 안쪽)을 다 그려 본 뒤 나온 결정이다.
        #
        # 대각선 점선은 **남긴다** — 넓이 규칙(d1×d2÷2)이 그 선에서 보인다. 뺀 것은 라벨뿐.
        # 길이는 발문이 말한다(「두 대각선의 길이가 18 cm, 6 cm인」).
        #
        # ⚠️ 이러면 §4-20 의 「값이 곧 조명」이 지면에서 꺼진다. **끄는 게 아니라 옮겼다** —
        #    「그린 가로:세로가 스펙의 d1:d2 와 맞는가」를 시험이 직접 잰다(09 §4-20).
        #    그 시험이 없으면 마름모는 오늘부터 아무도 안 보는 그림이 된다.
        extra_r, extra_b = 0.0, 0.0
        parts.append(_dashed_polyline([pts[0], pts[2]], "5 4", sw=1.05))
        parts.append(_dashed_polyline([pts[1], pts[3]], "5 4", sw=1.05))
    else:
        raise ValueError("shape 는 rect·tri·para·trap·rhombus 여야 합니다")
    return _svg(bw + pad * 2 + extra_r, bh + pad * 2 + extra_b, "".join(parts))


# ═══════════════════════════════════════════════════════════════════════════
# 입체 kind 셋 — hollowSolid · cutCuboid · revolvePlan (2026-08-23)
#
# 정본은 RPM 중학 1-2 원본 지면이다(본문·수치는 베끼지 않고 **모양만**):
#   · hollowSolid — p127 유형07 0845(원기둥⊖원기둥)·0846/0848(직육면체⊖직육면체)
#     ·0847(정육면체⊖원기둥)
#   · cutCuboid  — p127 유형08 0849(윗면·앞면에 닿은 홈)·0850(같은 무리, 정육면체)
#     ·0851(앞면 세로 홈, 바닥까지)·유형08 개념 상자(모서리 코너 컷)
#   · revolvePlan — p111 유형14(회전 전 반평면 도형 + 축 ℓ + 회전 화살표)
#     ·p133 유형20 0891(치수 붙은 직각삼각형)
#
# ## 숨은 모서리 — 면-쌍 규칙이 아니라 **가림 판정**으로 가른다
#
# §4-14 의 「양쪽 면이 다 뒤를 보면 숨음」은 볼록 입체에만 맞다. 구멍·홈이 있는
# 입체는 **앞을 보는 면의 모서리도 다른 살에 가려진다** — 0851 의 깊은 홈에서
# 안쪽 벽 모서리가 오른쪽 기둥 뒤로 숨는 것이 정확히 그 자리다(원본도 그 토막만
# 점선이다). 그래서 모서리를 점으로 나눠, 각 점에서 **관찰자 쪽 반직선이 살을
# 지나는 길이**를 해석적으로(상자·수직 원기둥의 구간 교집합) 재고, 숨은 토막만
# 점선으로 긋는다. 구멍 안쪽 세로 모서리가 **개구부 바로 아래에서 잠깐 실선**이
# 되는 것도 이 판정의 산물이다 — 뚫린 곳으로는 실제로 보이기 때문이다(원본 0846).
#
# ## 투영
#
# 각진 것은 기존 `_cuboid` 와 같은 cabinet(45°, ratio 0.5). 둥근 것만 §4-15 대로
# 깊이축을 화면 위(90°)로 세우고 `ROUND_RATIO` 를 쓴다. 정육면체에 뚫린 원기둥
# 구멍(0847)은 **그 면 위의 원을 같은 View 로 투영**한다 — 여기서 타원이 기우는
# 것은 §4-15 의 결함이 아니라 기운 면 위의 원이라 그런 것이고, 원본 지면도 그렇다.
# ═══════════════════════════════════════════════════════════════════════════

# 구멍·컷과 바깥 사이 최소 살 두께(cm). 더 얇으면 지면에서 선끼리 붙는다.
SOLID_MIN_WALL = 0.3
# 가림 판정에서 「제 표면 스침」을 걸러 내는 여유(cm). 살 두께(≥0.3)보다 훨씬 작아야
# 하고, 0이면 모서리가 제가 속한 면에 걸려 전부 숨은 것으로 나온다.
SOLID_RAY_EPS = 0.05
# 곧은 모서리 하나를 몇 점으로 나눠 가림을 재는가.
SOLID_EDGE_SAMPLES = 48


def _ray_dir(ratio: float, deg: float) -> tuple[float, float, float]:
    """화면에서 같은 자리에 겹쳐 보이는 점들의 방향, **관찰자 쪽**(y 감소)으로.

    `View.direction` 은 관찰자→화면 안쪽이므로 그 반대다.
    """
    a = math.radians(deg)
    return (ratio * math.cos(a), -1.0, ratio * math.sin(a))


def _iv_box_fn(dr, x0, x1, y0, y1, z0, z1):
    """점 p 에서 dr 방향 직선이 상자와 만나는 매개변수 구간 (s0, s1) — 없으면 None."""

    def iv(p):
        s0, s1 = -1e18, 1e18
        for pi, di, lo, hi in (
            (p[0], dr[0], x0, x1),
            (p[1], dr[1], y0, y1),
            (p[2], dr[2], z0, z1),
        ):
            if abs(di) < 1e-12:
                if pi <= lo or pi >= hi:
                    return None
            else:
                a, b = (lo - pi) / di, (hi - pi) / di
                if a > b:
                    a, b = b, a
                if a > s0:
                    s0 = a
                if b < s1:
                    s1 = b
        return (s0, s1) if s1 - s0 > 1e-9 else None

    return iv


def _iv_vcyl_fn(dr, cx, cy, r, z0, z1):
    """수직 원기둥(축이 z, 중심 (cx,cy))과의 매개변수 구간."""

    def iv(p):
        dx, dy, dz = dr
        fx, fy = p[0] - cx, p[1] - cy
        qa = dx * dx + dy * dy
        qb = 2 * (fx * dx + fy * dy)
        qc = fx * fx + fy * fy - r * r
        disc = qb * qb - 4 * qa * qc
        if disc <= 0:
            return None
        rt = math.sqrt(disc)
        s0, s1 = (-qb - rt) / (2 * qa), (-qb + rt) / (2 * qa)
        if abs(dz) < 1e-12:
            if p[2] <= z0 or p[2] >= z1:
                return None
        else:
            a, b = (z0 - p[2]) / dz, (z1 - p[2]) / dz
            if a > b:
                a, b = b, a
            s0, s1 = max(s0, a), min(s1, b)
        return (s0, s1) if s1 - s0 > 1e-9 else None

    return iv


def _make_hidden(outer_iv, inner_iv):
    """숨음 판정 — 관찰자 쪽 반직선이 «바깥 − 구멍» 살을 SOLID_RAY_EPS 넘게 지나는가."""

    def hidden(p) -> bool:
        o = outer_iv(p)
        if o is None:
            return False
        s0, s1 = max(o[0], SOLID_RAY_EPS), o[1]
        if s1 - s0 <= SOLID_RAY_EPS:
            return False
        if inner_iv is not None:
            iv = inner_iv(p)
            if iv is not None:
                a, b = max(iv[0], s0), min(iv[1], s1)
                return (s1 - s0) - max(0.0, b - a) > SOLID_RAY_EPS
        return True

    return hidden


def _seg3(a, b, n: int = SOLID_EDGE_SAMPLES):
    return [
        (
            a[0] + (b[0] - a[0]) * i / n,
            a[1] + (b[1] - a[1]) * i / n,
            a[2] + (b[2] - a[2]) * i / n,
        )
        for i in range(n + 1)
    ]


def _draw_chains(chains, view, hidden) -> list[str]:
    """모서리(3D 점열)를 화면 토막으로 — 보이는 토막 실선, 숨은 토막 점선.

    토막 경계는 이웃 표본의 중점이라 표본 간격(모서리/48)의 절반까지 어긋날 수
    있는데, 획 1px 에서는 안 보인다. 곧은 모서리의 토막은 양끝 두 점으로 줄여
    SVG 를 키우지 않는다.
    """
    parts: list[str] = []
    for pts3, straight in chains:
        if straight:
            pts3 = _seg3(pts3[0], pts3[-1])
        flags = [hidden(p) for p in pts3]
        scr = [view(p) for p in pts3]
        runs: list[tuple[bool, list[tuple[float, float]]]] = []
        cur = [scr[0]]
        f = flags[0]
        for k in range(1, len(pts3)):
            if flags[k] == f:
                cur.append(scr[k])
            else:
                mid = ((scr[k - 1][0] + scr[k][0]) / 2, (scr[k - 1][1] + scr[k][1]) / 2)
                cur.append(mid)
                runs.append((f, cur))
                cur = [mid, scr[k]]
                f = flags[k]
        runs.append((f, cur))
        for hid, pts in runs:
            if len(pts) < 2:
                continue
            if straight:
                pts = [pts[0], pts[-1]]
            if hid:
                parts.append(_polyline(pts, sw=1.0, dash=HIDDEN_DASH))
            else:
                parts.append(_polyline(pts, sw=SOLID_SW))
    return parts


def _fill_poly(pts, fill: str) -> str:
    """윤곽 없는 면 칠. 모서리는 `_draw_chains` 가 따로 긋는다 — 칠에 잉크 윤곽을
    주면 가려진 모서리까지 실선으로 둘러져 점선과 겹친다. 같은 색 hairline 은
    이웃 칠 사이 안티에일리어싱 틈을 메운다."""
    s = " ".join(f"{_n(x)},{_n(y)}" for x, y in pts)
    return f'<polygon points="{s}" fill="{fill}" stroke="{fill}" stroke-width="0.6"/>'


def _shape_keys(m: Any, name: str, required: frozenset[str], optional: frozenset[str] = frozenset()) -> None:
    if not isinstance(m, Mapping):
        raise ValueError(f"{name} 은 객체여야 합니다")
    extra = set(m) - required - optional
    if extra:
        raise ValueError(f"{name} 에 허용되지 않은 키: {', '.join(sorted(str(k) for k in extra))}")
    missing = required - set(m)
    if missing:
        raise ValueError(f"{name} 에 빠진 키: {', '.join(sorted(missing))}")


# --- 치수 라벨을 **도형 밖으로** — RPM 0849 규칙 ---------------------------
#
# 정본(RPM 중1-2 유형08 0849)은 우리와 **같은 문제·같은 치수 여섯**을 그리는데,
# 여섯 중 **다섯을 실루엣 바깥** 둘레에 두고 홈 속에는 하나만 넣는다(실측).
# 우리는 거리를 `DIM_OFF`(=9) 로 **못 박아** 두어 라벨이 도형 위에 앉았다 —
# `cutCuboid` 여섯 중 **넷**이 그랬다(실측 2026-08-28).
#
# 왜 그렇게 되나: 정본은 도형이 라벨보다 크다. 「도형 대각 ÷ 라벨 글자」가
# 정본 **13.0**, 우리 **8.0** 이다(같은 문제로 실측). 도형이 작으면 고정 거리 9 는
# 실루엣 **안쪽**에 떨어진다.
#
# ⚠️ **문턱을 올려서 고치지 마라.** 9 를 14 로 바꾸면 이 그림은 낫고 다른 그림은
#    치수가 도형에서 떨어져 무엇을 잰 것인지 안 읽힌다. 거리는 도형마다 달라야 한다.
#    그래서 여기서는 거리를 정하지 않고 **«비켰나»를 직접 묻는다** —
#    좌표평면 `O` 를 고칠 때와 같은 방식이다(D-61 · `_cp_o_offset`).
DIM_CLEAR = 1.5      # 라벨 상자와 획 사이 최소 여유(SVG 단위)
DIM_PUSH_TRIES = 14   # 더 밀면 치수가 도형에서 떨어져 «무엇을 쟀나»가 안 읽힌다.
#                       실측(그림 149장): 7 → 겹침 8 · 10 → 7 · **14 → 5** · 20 → 5.
#                       도형을 키운 만큼(SOLID_UNITS) 밀 거리도 늘어야 한다 —
#                       7 로 두면 밀다 만 라벨이 반대쪽 면 위에 앉는다(실측 `12 cm`).


# 라벨을 선분 **위에서** 옮겨 볼 자리 (0=시작점 · 0.5=중점 · 1=끝점).
# 정본은 거리를 늘리는 대신 이쪽을 쓴다 — 호가 짧아야 «무엇을 쟀나»가 읽힌다.
DIM_TS = (0.5, 0.7, 0.3, 0.82, 0.18)


def _dim_label_box(a, b, off: float, label: str, fs: float, t: float = 0.5):
    """그 치수 라벨이 지면에서 차지할 상자.

    🔴 **자리 계산을 옮겨 적지 않는다.** 제품이 실제로 그리는 그 문자열
       (`core.figure_svg.dim_label`)을 만들어 `_text_bboxes` 로 잰다. vendor 의
       `_label_push` 든 여기 폭 표든 한쪽만 바뀌면 자와 그림이 갈라진다 —
       이 저장소가 여러 번 겪은 자리다.
    """
    from core.figure_svg import dim_label

    boxes = _text_bboxes(dim_label(a[0], a[1], b[0], b[1], off, label, fs=fs, t=t))
    return boxes[0][:4] if boxes else None


def _dim_place(a, b, label: str, off: float, avoid,
               fs: float = DIM_FS, slide_only: bool = False) -> tuple[float, float]:
    """라벨이 획을 비키는 (거리, 선분 위 자리) 를 고른다.

    ⚠️ **거리만 늘리면 안 된다.** `measured()` 는 같은 `off` 로 점선 호도 부풀리므로,
       멀리 밀수록 호가 도형을 가로질러 «무엇을 잰 치수인가»가 안 읽힌다(실측).
       정본은 호를 짧게 두고 라벨을 **선분 위에서** 옮긴다. 그래서 가까운 거리부터
       보고, 같은 거리 안에서 `t` 를 먼저 흔든다.

    `slide_only` — 반지름처럼 **그 선 자체가 치수선**인 경우(`off=0`). 옆으로 밀면
    치수선에서 떨어져 「무엇을 잰 것인가」가 깨지므로 `t` 만 흔든다.

    끝내 비킬 자리가 없으면 **획이 가장 적게 지나는** 자리를 고른다 — 안쪽으로
    되돌리지 않는다(도형 한가운데보다 가장자리가 낫다).
    """
    if avoid is None:
        return off, 0.5
    segs, boxes = avoid.segs, avoid.boxes
    if not segs and not boxes:
        return off, 0.5
    # 걸음을 잘게(0.25·fs) 해 «비키는 가장 가까운 자리»를 찾게도 해 봤다 —
    # 그림은 눈으로 구분이 안 되고 겹침만 6 → 7 로 나빠졌다(실측). 굵은 걸음을 둔다.
    step = max(4.0, 0.5 * fs)
    best, best_hits = (off, 0.5), None
    # 부르는 쪽의 `want` 는 **어느 쪽을 먼저 볼지**만 정한다. 먼저 그쪽을 다 보고,
    # 끝내 못 비키면 **반대쪽**도 본다 — 홈이 왼쪽 끝에 붙은 컷처럼 «빈 하늘»이
    # 부르는 쪽 예상과 반대편인 경우가 있다(실측 `cutCuboid` cut.x=0).
    signs = (1.0,) if slide_only else (
        1.0 if off >= 0 else -1.0, -1.0 if off >= 0 else 1.0)
    for sign in signs:
        base = abs(off) * sign
        for k in range(1 if slide_only else DIM_PUSH_TRIES):
            cand = base + sign * step * k
            for t in DIM_TS:
                box = _dim_label_box(a, b, cand, label, fs, t)
                if box is None:
                    return cand, t
                pad = (box[0] - DIM_CLEAR, box[1] - DIM_CLEAR,
                       box[2] + DIM_CLEAR, box[3] + DIM_CLEAR)
                hits = sum(1 for p, q in segs if _seg_hits_box(p, q, pad))
                # 이 후보의 **곡선**이 앞서 놓은 라벨을 무는가 — 라벨 자리만 보면
                # 「내가 비켰다」는 참인데 「내 곡선이 남을 덮는다」가 안 보인다.
                if boxes:
                    curve = _dim_curve_segs(
                        _length_mark(a[0], a[1], b[0], b[1], label, off=cand, fs=fs, t=t))
                    hits += sum(1 for bx in boxes for p, q in curve
                                if _seg_hits_box(p, q, bx))
                if hits == 0:
                    return cand, t
                if best_hits is None or hits < best_hits:
                    best, best_hits = (cand, t), hits
    return best


_DIM_PATH_RE = re.compile(
    r'd="M ([-\d.]+) ([-\d.]+) Q ([-\d.]+) ([-\d.]+) ([-\d.]+) ([-\d.]+)"')


def _dim_curve_segs(markup: str, steps: int = 12) -> list:
    """치수 곡선(2차 베지에)을 화면 선분들로 — **그려 낸 그 markup 에서** 읽는다.

    🔴 곡선 식을 여기 다시 적지 않는다. `core.figure_svg.meas` 가 정본이고,
       그 식이 바뀌면 여기 사본만 옛 모양으로 남아 **초록인 채로** 눈이 먼다.

    왜 필요한가: 라벨을 밖으로 밀면 **치수 곡선도 같이 나간다.** 그 곡선이
    다음 라벨을 가로지르면 방금 고친 만큼 새 겹침이 생긴다 — 실측으로
    `12 cm`·`6 cm` 를 비키게 하자 그 곡선이 `7 cm` 를 물었다.
    """
    m = _DIM_PATH_RE.search(markup)
    if not m:
        # ⚠️ **조용히 [] 를 내면 안 된다.** 그러면 「비켜야 할 것」에서 치수 곡선이
        #    통째로 빠지고, 겹침이 0 으로 **줄어드는 게 아니라 안 보이게** 된다 —
        #    0 은 «깨끗»과 «못 셈»을 안 가른다.
        raise ValueError(f"치수 곡선을 못 읽었다 — meas() 의 path 모양이 바뀌었나: {markup[:120]}")
    x0, y0, cx, cy, x1, y1 = (float(v) for v in m.groups())
    pts = []
    for i in range(steps + 1):
        t = i / steps
        u = 1.0 - t
        pts.append((u * u * x0 + 2 * u * t * cx + t * t * x1,
                    u * u * y0 + 2 * u * t * cy + t * t * y1))
    return [(pts[i], pts[i + 1]) for i in range(steps)]


class _DimSpace:
    """치수를 놓을 때 **비켜야 할 것** — 획과 «이미 놓은 라벨 상자».

    라벨 상자가 왜 필요한가: 곡선은 라벨과 같이 밀리므로, 뒤에 놓는 치수의 곡선이
    **앞서 놓은 라벨**을 가로지를 수 있다. 획만 보면 그 자리는 구조적으로 안 보인다 —
    실측으로 `cutCuboid` 에서 컷 치수 곡선이 `7 cm` 를 물었다(겹침 넷을 둘로 줄인
    바로 그 회차에 **새로** 생겼다).
    """

    __slots__ = ("segs", "boxes")

    def __init__(self, segs: list | None = None):
        self.segs: list = list(segs or [])
        self.boxes: list = []

    def add(self, mark: str, box) -> None:
        self.segs.extend(_dim_curve_segs(mark))
        if box is not None:
            self.boxes.append(box)


def _seen_edges(view, edges3) -> list:
    """3D 모서리 목록 → 화면 선분. 치수 라벨이 **비켜야 할 것**이다."""
    return [(view(a3), view(b3)) for a3, b3 in edges3]


def _chain_segs(view, chains) -> list:
    """`_draw_chains` 에 넘긴 사슬 → 화면 선분 목록.

    ⚠️ **그리는 것과 같은 목록**을 쓴다. 여기서 모서리를 다시 세면 한쪽만 늘어나
       「라벨이 비켰다」가 거짓이 된다 — 원 구멍의 실루엣이 딱 그런 자리다.
    """
    out: list = []
    for pts, _solid in chains:
        scr = [view(q) for q in pts]
        for i in range(len(scr) - 1):
            out.append((scr[i], scr[i + 1]))
    return out


def _cuboid_dim_parts(view, w: float, d: float, h: float, edges3,
                      avoid=None) -> list[str]:
    """직육면체 계열 바깥 치수 세 개 — `_cuboid` 와 같은 자리·같은 `measured()` 한 벌.

    edges3 는 (w모서리, h모서리, d모서리) 의 3D 끝점 쌍 — 컷이 그 모서리를 끊었으면
    부르는 쪽이 성한 모서리로 바꿔 넘긴다(끊긴 모서리에 전체 길이를 적으면 거짓말이다).
    """
    inside = view((w / 2, d / 2, h / 2))
    parts: list[str] = []
    for (a3, b3), label in zip(edges3, (f"{_n(w)} cm", f"{_n(h)} cm", f"{_n(d)} cm")):
        a, b = view(a3), view(b3)
        span = math.hypot(b[0] - a[0], b[1] - a[1])
        off = _outward_off(a, b, inside, DIM_OFF if span >= 28 else DIM_OFF + 6)
        off, t = _dim_place(a, b, label, off, avoid, DIM_FS)
        mark = _length_mark(a[0], a[1], b[0], b[1], label, off=off, fs=DIM_FS, t=t)
        parts.append(mark)
        if avoid is not None:
            avoid.add(mark, _dim_label_box(a, b, off, label, DIM_FS, t))
    return parts


def _dim_towards(view, a3, b3, label: str, want3, off_mag: float = DIM_OFF,
                 avoid=None) -> str:
    """치수 곡선을 3D 상의 want3 쪽(빈 공간)으로 밀어 measured() 로 긋는다.

    `want3` 는 **어느 쪽**인지만 정한다 — **얼마나** 미는지는 `_dim_clear_off` 가
    「비켰나」를 물어 정한다. 예전에는 `off_mag` 가 곧 거리라 라벨이 도형 위에 앉았다.
    """
    a, b = view(a3), view(b3)
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    wv = view(want3)
    off = _off_towards(a, b, (wv[0] - mid[0], wv[1] - mid[1]), off_mag)
    off, t = _dim_place(a, b, label, off, avoid, DIM_FS)
    mark = _length_mark(a[0], a[1], b[0], b[1], label, off=off, fs=DIM_FS, t=t)
    if avoid is not None:
        avoid.add(mark, _dim_label_box(a, b, off, label, DIM_FS, t))
    return mark


def _box_edges(w: float, d: float, h: float) -> list:
    out = []
    for z in (0.0, h):
        out.append([(0.0, 0.0, z), (w, 0.0, z)])
        out.append([(w, 0.0, z), (w, d, z)])
        out.append([(w, d, z), (0.0, d, z)])
        out.append([(0.0, d, z), (0.0, 0.0, z)])
    for x in (0.0, w):
        for y in (0.0, d):
            out.append([(x, y, 0.0), (x, y, h)])
    return out


# ── hollowSolid — 구멍이 뚫린 기둥 (RPM 유형07) ──────────────────────────────


def _hollow_cyl(R: float, H: float, r: float) -> str:
    from core.figure_solid import circle3

    if R - r < SOLID_MIN_WALL:
        raise ValueError(f"구멍 반지름 {_n(r)} 이 바깥 반지름 {_n(R)} 에 너무 가깝습니다")
    scale = ROUND_UNITS / max(2 * R, H)
    obot = circle3((0, 0, 0), R, (0, 0, 1), 64)
    otop = circle3((0, 0, H), R, (0, 0, 1), 64)
    ibot = circle3((0, 0, 0), r, (0, 0, 1), 64)
    itop = circle3((0, 0, H), r, (0, 0, 1), 64)
    view, svg_w, svg_h = _fitted_cabinet(
        # 왼쪽 24 도 놀던 여백이다 — 구멍 원기둥의 치수는 오른쪽에 선다(실측 왼 21.0 이 비었다).
        obot + otop, scale, _dim_pads((8.0, 26.0, 40.0, 24.0)), ratio=ROUND_RATIO, deg=ROUND_DEG
    )
    dr = _ray_dir(ROUND_RATIO, ROUND_DEG)
    hidden = _make_hidden(
        _iv_vcyl_fn(dr, 0.0, 0.0, R, 0.0, H), _iv_vcyl_fn(dr, 0.0, 0.0, r, -1.0, H + 1.0)
    )
    top_scr = _round_ring(view, otop)
    bot_scr = _round_ring(view, obot)
    i_l = min(range(len(bot_scr)), key=lambda i: bot_scr[i][0])
    i_r = max(range(len(bot_scr)), key=lambda i: bot_scr[i][0])
    near_bot, _far_bot = _split_ring(bot_scr, i_l, i_r)
    near_top, _far_top = _split_ring(top_scr, i_l, i_r)
    if near_top[0][0] > near_top[-1][0]:
        near_top = near_top[::-1]
    if near_bot[0][0] < near_bot[-1][0]:
        near_bot = near_bot[::-1]
    parts = [
        _fill_poly(near_top + near_bot, FACE_FRONT),
        _fill_poly(top_scr, FACE_TOP),
        # 개구부는 「안이 비어 있다」로 읽히게 셋 중 가장 어두운 면색을 깐다.
        _fill_poly(_round_ring(view, itop), FACE_SIDE),
    ]
    chains = [
        (otop, False),
        (obot, False),
        (itop, False),
        (ibot, False),
        ([(R, 0.0, 0.0), (R, 0.0, H)], True),
        ([(-R, 0.0, 0.0), (-R, 0.0, H)], True),
        ([(r, 0.0, 0.0), (r, 0.0, H)], True),
        ([(-r, 0.0, 0.0), (-r, 0.0, H)], True),
    ]
    parts += _draw_chains(chains, view, hidden)
    avoid = _DimSpace(_chain_segs(view, chains))
    # 치수 — 전부 measured() 한 벌(§4-16). 반지름은 중심에 점을 찍고 그 선 자체가
    # 치수선이 되게 off=0. 바깥 R 은 오른쪽, 구멍 r 은 왼쪽으로 갈라 겹치지 않는다.
    #
    # ⚠️ 반지름 라벨은 **옆으로 못 민다** — 밀면 치수선에서 떨어져 무엇을 잰 것인지
    #    안 읽힌다. 대신 선 **위에서** 미끄러뜨린다(`slide_only`). 중심에서 곧장
    #    절반 자리에 두면 안쪽 원의 타원을 그대로 물었다(실측: `8 cm`·`5 cm` 둘 다).
    c = view((0.0, 0.0, H))
    pR = view((R, 0.0, H))
    pr = view((-r, 0.0, H))
    parts.append(f'<circle cx="{_n(c[0])}" cy="{_n(c[1])}" r="2" fill="{INK}"/>')
    for q, text, want in ((pR, f"{_n(R)} cm", (R, 0.0, 2.0 * H)),
                          (pr, f"{_n(r)} cm", (-r, 0.0, 2.0 * H))):
        a2, b2 = (c[0], c[1]), (q[0], q[1])
        wv = view(want)
        off0 = _off_towards(a2, b2, (wv[0] - (a2[0] + b2[0]) / 2,
                                     wv[1] - (a2[1] + b2[1]) / 2), DIM_OFF)
        off, t = _dim_place(a2, b2, text, off0, avoid, DIM_FS)
        mark = _length_mark(c[0], c[1], q[0], q[1], text, off=off, fs=DIM_FS, t=t)
        parts.append(mark)
        avoid.add(mark, _dim_label_box(a2, b2, off, text, DIM_FS, t))
    parts.append(
        _dim_towards(view, (R, 0.0, H), (R, 0.0, 0.0), f"{_n(H)} cm",
                     (2 * R, 0.0, H / 2), DIM_OFF, avoid=avoid)
    )
    return _svg(svg_w, svg_h, "".join(parts))


def _hollow_box(w: float, d: float, h: float, cw: float, cd: float, hole_r: float | None) -> str:
    """직육면체에 관통 구멍 — 사각(0846) 또는 원(0847). 구멍은 가운데."""
    from core.figure_solid import circle3

    mx = max(w, d, h)
    scale = SOLID_UNITS / mx
    depth_px = 0.5 * scale * d
    if depth_px < 24.0:
        scale *= 24.0 / depth_px
    corners = [(x, y, z) for x in (0.0, w) for y in (0.0, d) for z in (0.0, h)]
    view, svg_w, svg_h = _fitted_cabinet(corners, scale, _dim_pads((40.0, 22.0, 52.0, 44.0)))
    dr = _ray_dir(0.5, 45.0)
    outer_iv = _iv_box_fn(dr, 0.0, w, 0.0, d, 0.0, h)
    if hole_r is None:
        if (w - cw) / 2 < SOLID_MIN_WALL or (d - cd) / 2 < SOLID_MIN_WALL:
            raise ValueError("구멍이 바깥 직육면체에 너무 가깝습니다")
        hx0, hx1 = (w - cw) / 2, (w + cw) / 2
        hy0, hy1 = (d - cd) / 2, (d + cd) / 2
        inner_iv = _iv_box_fn(dr, hx0, hx1, hy0, hy1, -1.0, h + 1.0)
    else:
        if min(w, d) / 2 - hole_r < SOLID_MIN_WALL:
            raise ValueError("구멍 반지름이 바깥 직육면체에 너무 가깝습니다")
        inner_iv = _iv_vcyl_fn(dr, w / 2, d / 2, hole_r, -1.0, h + 1.0)
    hidden = _make_hidden(outer_iv, inner_iv)

    def p(x: float, y: float, z: float):
        return view((x, y, z))

    parts = [
        _fill_poly([p(0, 0, 0), p(w, 0, 0), p(w, 0, h), p(0, 0, h)], FACE_FRONT),
        _fill_poly([p(w, 0, 0), p(w, d, 0), p(w, d, h), p(w, 0, h)], FACE_SIDE),
        _fill_poly([p(0, 0, h), p(w, 0, h), p(w, d, h), p(0, d, h)], FACE_TOP),
    ]
    chains = [(e, True) for e in _box_edges(w, d, h)]
    if hole_r is None:
        opening = [(hx0, hy0, h), (hx1, hy0, h), (hx1, hy1, h), (hx0, hy1, h)]
        parts.append(_fill_poly([view(q) for q in opening], FACE_SIDE))
        bottom = [(x, y, 0.0) for x, y, _z in opening]
        for ring in (opening, bottom):
            m = len(ring)
            chains += [([ring[i], ring[(i + 1) % m]], True) for i in range(m)]
        chains += [([(x, y, h), (x, y, 0.0)], True) for x, y, _z in opening]
    else:
        htop = circle3((w / 2, d / 2, h), hole_r, (0, 0, 1), 64)
        hbot = circle3((w / 2, d / 2, 0), hole_r, (0, 0, 1), 64)
        parts.append(_fill_poly([view(q) for q in htop[:-1]], FACE_SIDE))
        chains += [(htop, False), (hbot, False)]
        # 구멍 벽의 실루엣 — 시선의 수평 성분에 접하는 두 점의 세로선.
        th = math.atan2(dr[0], -dr[1])
        for t in (th, th + math.pi):
            sx = w / 2 + hole_r * math.cos(t)
            sy = d / 2 + hole_r * math.sin(t)
            chains.append(([(sx, sy, 0.0), (sx, sy, h)], True))
    parts += _draw_chains(chains, view, hidden)
    avoid = _DimSpace(_chain_segs(view, chains))
    parts += _cuboid_dim_parts(
        view, w, d, h,
        (((0, 0, 0), (w, 0, 0)), ((0, 0, 0), (0, 0, h)), ((w, 0, 0), (w, d, 0))),
        avoid=avoid,
    )
    if hole_r is None:
        void = ((hx0 + hx1) / 2, (hy0 + hy1) / 2, h)
        parts.append(
            _dim_towards(view, (hx0, hy0, h), (hx1, hy0, h), f"{_n(cw)} cm", void, 8.0,
                         avoid=avoid)
        )
        parts.append(
            _dim_towards(view, (hx1, hy0, h), (hx1, hy1, h), f"{_n(cd)} cm", void, 8.0,
                         avoid=avoid)
        )
    else:
        c = view((w / 2, d / 2, h))
        th = math.atan2(dr[0], -dr[1])
        rim = view((w / 2 + hole_r * math.cos(th), d / 2 + hole_r * math.sin(th), h))
        parts.append(f'<circle cx="{_n(c[0])}" cy="{_n(c[1])}" r="2" fill="{INK}"/>')
        parts.append(_length_mark(c[0], c[1], rim[0], rim[1], f"{_n(hole_r)} cm", off=0, fs=DIM_FS))
    return _svg(svg_w, svg_h, "".join(parts))


def _hollow_solid(spec: Mapping[str, Any]) -> str:
    outer, inner = spec["outer"], spec["inner"]
    if not isinstance(outer, Mapping) or not isinstance(inner, Mapping):
        raise ValueError("outer/inner 는 객체여야 합니다")
    oshape, ishape = outer.get("shape"), inner.get("shape")
    if oshape == "cylinder":
        _shape_keys(outer, "outer", frozenset({"shape", "r", "h"}))
        if ishape != "cylinder":
            raise ValueError("원기둥에는 원기둥 구멍만 지원합니다")
        _shape_keys(inner, "inner", frozenset({"shape", "r"}))
        return _hollow_cyl(
            _num(outer["r"], "outer.r", 0.4, 20),
            _num(outer["h"], "outer.h", 0.4, 30),
            _num(inner["r"], "inner.r", 0.2, 20),
        )
    if oshape == "cuboid":
        _shape_keys(outer, "outer", frozenset({"shape", "w", "d", "h"}))
        w = _num(outer["w"], "outer.w", 0.5, 40)
        d = _num(outer["d"], "outer.d", 0.5, 40)
        h = _num(outer["h"], "outer.h", 0.5, 40)
        if ishape == "cuboid":
            _shape_keys(inner, "inner", frozenset({"shape", "w", "d"}))
            return _hollow_box(
                w, d, h,
                _num(inner["w"], "inner.w", 0.2, 40),
                _num(inner["d"], "inner.d", 0.2, 40),
                None,
            )
        if ishape == "cylinder":
            _shape_keys(inner, "inner", frozenset({"shape", "r"}))
            return _hollow_box(w, d, h, 0.0, 0.0, _num(inner["r"], "inner.r", 0.2, 20))
        raise ValueError(f"모르는 구멍 모양입니다: {ishape}")
    raise ValueError(f"모르는 바깥 모양입니다: {oshape}")


# ── cutCuboid — 일부를 잘라 낸 직육면체 (RPM 유형08) ─────────────────────────


def _notched_rect(W: float, V: float, a: float, b: float, c: float):
    """[0,W]×[0,V] − [a,b]×[c,V] — 노치는 반드시 위 변(v=V)에 닿는다. 남는 다각형 목록."""
    gl = a > 1e-9
    gr = b < W - 1e-9
    gb = c > 1e-9
    if not gb:
        out = []
        if gl:
            out.append([(0.0, 0.0), (a, 0.0), (a, V), (0.0, V)])
        if gr:
            out.append([(b, 0.0), (W, 0.0), (W, V), (b, V)])
        return out
    if gl and gr:
        return [[(0.0, 0.0), (W, 0.0), (W, V), (b, V), (b, c), (a, c), (a, V), (0.0, V)]]
    if gl:
        return [[(0.0, 0.0), (W, 0.0), (W, c), (a, c), (a, V), (0.0, V)]]
    if gr:
        return [[(0.0, 0.0), (W, 0.0), (W, V), (b, V), (b, c), (0.0, c)]]
    return [[(0.0, 0.0), (W, 0.0), (W, c), (0.0, c)]]


def _cut_cuboid(spec: Mapping[str, Any]) -> str:
    w = _num(spec["w"], "w", 0.5, 40)
    d = _num(spec["d"], "d", 0.5, 40)
    h = _num(spec["h"], "h", 0.5, 40)
    cut = spec["cut"]
    _shape_keys(cut, "cut", frozenset(), frozenset({"x", "w", "d", "h"}))
    given_w, given_d, given_h = "w" in cut, "d" in cut, "h" in cut
    # 뺀 키는 「그 방향 전체」다. 둘 이상 빼면 통째 조각을 떼는 것이라 잘린 모양이
    # 남지 않거나(널판 제거) 입체가 두 동강 난다 — 조용히 그리지 않고 던진다.
    if (not given_w) + (not given_d) + (not given_h) > 1:
        raise ValueError("cut 은 w·d·h 중 둘 이상을 주어야 합니다 (뺀 키 = 그 방향 전체)")
    cw = _num(cut["w"], "cut.w", 0.2, 40) if given_w else w
    cd = _num(cut["d"], "cut.d", 0.2, 40) if given_d else d
    ch = _num(cut["h"], "cut.h", 0.2, 40) if given_h else h
    if given_w and cw > w - SOLID_MIN_WALL:
        raise ValueError(f"cut.w {_n(cw)} 는 w {_n(w)} 보다 {_n(SOLID_MIN_WALL)} 이상 작아야 합니다")
    if given_d and cd > d - SOLID_MIN_WALL:
        raise ValueError(f"cut.d {_n(cd)} 는 d {_n(d)} 보다 {_n(SOLID_MIN_WALL)} 이상 작아야 합니다")
    if given_h and ch > h - SOLID_MIN_WALL:
        raise ValueError(f"cut.h {_n(ch)} 는 h {_n(h)} 보다 {_n(SOLID_MIN_WALL)} 이상 작아야 합니다")
    x_given = "x" in cut
    if x_given:
        if not given_w:
            raise ValueError("cut.w 없이 cut.x 를 줄 수 없습니다")
        cx = _num(cut["x"], "cut.x", 0, 40)
        if cx + cw > w + 1e-9:
            raise ValueError("cut.x + cut.w 가 w 를 넘습니다")
    else:
        cx = (w - cw) / 2
    eps = 1e-9
    zf = h - ch
    touch_l, touch_r = cx <= eps, cx + cw >= w - eps
    touch_b, touch_k = ch >= h - eps, cd >= d - eps  # 바닥·뒷면까지 닿는가

    mx = max(w, d, h)
    scale = SOLID_UNITS / mx
    depth_px = 0.5 * scale * d
    if depth_px < 24.0:
        scale *= 24.0 / depth_px
    corners = [(x, y, z) for x in (0.0, w) for y in (0.0, d) for z in (0.0, h)]
    view, svg_w, svg_h = _fitted_cabinet(corners, scale, _dim_pads((40.0, 22.0, 52.0, 44.0)))
    dr = _ray_dir(0.5, 45.0)
    hidden = _make_hidden(
        _iv_box_fn(dr, 0.0, w, 0.0, d, 0.0, h),
        _iv_box_fn(
            dr,
            cx - 1.0 if touch_l else cx,
            cx + cw + 1.0 if touch_r else cx + cw,
            -1.0,
            cd + 1.0 if touch_k else cd,
            zf - 1.0 if touch_b else zf,
            h + 1.0,
        ),
    )

    # 면 목록: (3D 다각형, 칠 색 | None). 보이는 법선(+x·−y·+z)만 칠한다.
    faces: list[tuple[list, str | None]] = []

    def add(local_polys, mapf, fill):
        for poly in local_polys:
            faces.append(([mapf(u, v) for u, v in poly], fill))

    add(_notched_rect(w, h, cx, cx + cw, zf), lambda u, v: (u, 0.0, v), FACE_FRONT)
    add(_notched_rect(w, d, cx, cx + cw, d - cd), lambda u, v: (u, d - v, h), FACE_TOP)
    if touch_r:
        add(_notched_rect(d, h, 0.0, cd, zf), lambda u, v: (w, u, v), FACE_SIDE)
    else:
        faces.append(([(w, 0.0, 0.0), (w, d, 0.0), (w, d, h), (w, 0.0, h)], FACE_SIDE))
    if touch_l:
        add(_notched_rect(d, h, 0.0, cd, zf), lambda u, v: (0.0, u, v), None)
    else:
        faces.append(([(0.0, 0.0, 0.0), (0.0, d, 0.0), (0.0, d, h), (0.0, 0.0, h)], None))
    if touch_b:
        add(_notched_rect(w, d, cx, cx + cw, d - cd), lambda u, v: (u, d - v, 0.0), None)
    else:
        faces.append(([(0.0, 0.0, 0.0), (w, 0.0, 0.0), (w, d, 0.0), (0.0, d, 0.0)], None))
    if touch_k:
        add(_notched_rect(w, h, cx, cx + cw, zf), lambda u, v: (u, d, v), None)
    else:
        faces.append(([(0.0, d, 0.0), (w, d, 0.0), (w, d, h), (0.0, d, h)], None))
    inner: list[tuple[list, str | None]] = []
    if not touch_b:  # 홈 바닥
        inner.append(([(cx, 0.0, zf), (cx + cw, 0.0, zf), (cx + cw, cd, zf), (cx, cd, zf)], FACE_TOP))
    if not touch_k:  # 홈 뒷벽 (관찰자를 본다)
        inner.append(([(cx, cd, zf), (cx + cw, cd, zf), (cx + cw, cd, h), (cx, cd, h)], FACE_FRONT))
    if not touch_l:  # 홈 왼벽 (법선 +x → 보인다)
        inner.append(([(cx, 0.0, zf), (cx, cd, zf), (cx, cd, h), (cx, 0.0, h)], FACE_SIDE))
    if not touch_r:  # 홈 오른벽 (법선 −x → 안 보인다)
        inner.append(([(cx + cw, 0.0, zf), (cx + cw, cd, zf), (cx + cw, cd, h), (cx + cw, 0.0, h)], None))

    # 안쪽 벽 → 윗면 → 오른면 → 앞면 순서로 칠한다 — 깊은 홈이 오른쪽 기둥 뒤로
    # 숨는 경우(0851) 가까운 면이 나중에 와야 실제 가림과 같아진다.
    parts = [_fill_poly([view(q) for q in poly], fill) for poly, fill in inner if fill]
    for want in (FACE_TOP, FACE_SIDE, FACE_FRONT):
        for poly, fill in faces:
            if fill == want:
                parts.append(_fill_poly([view(q) for q in poly], fill))

    # 모서리 — 면 다각형에서 모아 중복을 걷고, 토막별로 실선/점선.
    edge_map: dict[tuple, tuple] = {}
    for poly, _fill in faces + inner:
        m = len(poly)
        for i in range(m):
            a3, b3 = poly[i], poly[(i + 1) % m]
            key = tuple(sorted((tuple(round(c, 4) for c in a3), tuple(round(c, 4) for c in b3))))
            edge_map.setdefault(key, (a3, b3))
    _cut_chains = [([a3, b3], True) for a3, b3 in edge_map.values()]
    parts += _draw_chains(_cut_chains, view, hidden)
    avoid = _DimSpace(_chain_segs(view, _cut_chains))

    # 바깥 치수 — 컷이 끊은 모서리에는 적지 않는다(성한 모서리로 옮긴다).
    w_edge = ((0, 0, 0), (w, 0, 0)) if not touch_b else ((0, d, h), (w, d, h))
    if not touch_l:
        h_edge = ((0, 0, 0), (0, 0, h))
    elif not touch_r:
        h_edge = ((w, 0, 0), (w, 0, h))
    else:
        h_edge = ((w, d, 0), (w, d, h))
    d_edge = ((w, 0, 0), (w, d, 0)) if not (touch_r and touch_b) else ((0, 0, 0), (0, d, 0))
    parts += _cuboid_dim_parts(view, w, d, h, (w_edge, h_edge, d_edge), avoid=avoid)

    # 컷 치수 — 받은 값만 적는다(§4-20). 셋을 홈 안에 다 밀어 넣으면 서로 겹치므로
    # (0849 재현에서 실측) 폭·깊이는 위(빈 하늘)로, 높이만 홈의 빈 공간으로 민다.
    void = (cx + cw / 2, cd / 2, (zf + h) / 2)
    x1 = cx + cw
    if given_w:
        if not touch_b:
            # 홈 바닥 앞모서리 — 라벨은 그 아래 앞면 위로. 위 하늘에 두면 cd 라벨과
            # 정확히 겹친다(0849 재현 실측: cd 의 halo 가 cw 를 통째로 덮었다).
            a3, b3 = (cx, 0.0, zf), (x1, 0.0, zf)
            want = (cx + cw / 2, 0.0, zf - 5.0)
        else:
            a3, b3 = (cx, cd, h), (x1, cd, h)  # 바닥까지 뚫린 홈 — 뒷벽 윗모서리 위
            want = (cx + cw / 2, cd, h + 6.0)
        parts.append(_dim_towards(view, a3, b3, f"{_n(cw)} cm", want, 9.0, avoid=avoid))
    if given_d:
        if not touch_r:
            a3, b3 = (x1, 0.0, h), (x1, cd, h)
            want = (x1 + 5.0, cd / 2, h - 5.0)  # 오른쪽 아래(윗면 위) — cw 와 갈라놓는다
        elif not touch_l:
            a3, b3 = (cx, 0.0, h), (cx, cd, h)
            want = (cx - 5.0, cd / 2, h + 5.0)  # 왼쪽 위(빈 하늘)
        else:
            a3, b3 = (x1, 0.0, zf), (x1, cd, zf)
            want = (x1 + 5.0, cd / 2, zf - 3.0)
        parts.append(_dim_towards(view, a3, b3, f"{_n(cd)} cm", want, 9.0, avoid=avoid))
    if given_h:
        if not touch_r:
            a3, b3 = (x1, 0.0, zf), (x1, 0.0, h)
        elif not touch_l:
            a3, b3 = (cx, 0.0, zf), (cx, 0.0, h)
        else:
            # 좌우가 다 바깥에 닿는 컷(폭 전체) — 뒷벽의 오른끝 세로 모서리에 적는다.
            a3, b3 = (w, cd, zf), (w, cd, h)
        parts.append(_dim_towards(view, a3, b3, f"{_n(ch)} cm", void, 9.0, avoid=avoid))
    # 컷 위치(x)는 양쪽에 기둥이 남을 때만 치수가 된다 — 왼기둥 폭으로 적는다.
    if x_given and not touch_l and not touch_r:
        parts.append(
            _dim_towards(view, (0.0, 0.0, h), (cx, 0.0, h), f"{_n(cx)} cm",
                         (cx / 2, 0.0, h + 6.0), avoid=avoid)
        )
    return _svg(svg_w, svg_h, "".join(parts))


# ── revolvePlan — 회전 전 반평면 도형 + 축 (RPM 유형14·유형20) ───────────────
#
# ⚠️ 축은 **실선**이다. 착수 브리프에 「점선」이라 적혀 있었지만 원본 지면
#    (p111 유형14 상자·0738·0739·p133 0890~0892)이 전부 가는 실선이고,
#    원본이 정본이다. 축 라벨 ℓ 과 회전 화살표는 축 맨 위.

_REV_REQ: dict[str, frozenset[str]] = {
    "rect": frozenset({"shape", "w", "h"}),
    "rightTri": frozenset({"shape", "w", "h"}),
    "rightTrap": frozenset({"shape", "w", "w2", "h"}),
    "semicircle": frozenset({"shape", "r"}),
    "quarter": frozenset({"shape", "r"}),
}
_REV_OPT: dict[str, frozenset[str]] = {
    "rect": frozenset({"wLabel", "hLabel"}),
    "rightTri": frozenset({"flip", "wLabel", "hLabel", "slantLabel"}),
    "rightTrap": frozenset({"wLabel", "w2Label", "hLabel"}),
    "semicircle": frozenset({"rLabel"}),
    "quarter": frozenset({"flip", "rLabel"}),
}
# 회전 화살표 타원 반지름(px) — 원본처럼 축을 감싸는 납작한 고리.
REV_ARROW_RX = 8.0
REV_ARROW_RY = 3.2


def _rev_arc(cx_cm: float, cy_cm: float, r_cm: float, a0: float, a1: float, n: int = 36):
    """cm 좌표의 원호 점열 (a0→a1, 도 단위 반시계)."""
    return [
        (
            cx_cm + r_cm * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
            cy_cm + r_cm * math.sin(math.radians(a0 + (a1 - a0) * i / n)),
        )
        for i in range(n + 1)
    ]


def _revolve_plan(spec: Mapping[str, Any]) -> str:
    pieces = spec["pieces"]
    if not isinstance(pieces, list) or not 1 <= len(pieces) <= 3:
        raise ValueError("pieces 는 1~3개여야 합니다")
    gap = _num(spec.get("gap", 0), "gap", 0, 10)
    parsed = []
    for i, piece in enumerate(pieces):
        if not isinstance(piece, Mapping):
            raise ValueError(f"pieces[{i}] 는 객체여야 합니다")
        shape = piece.get("shape")
        if shape not in _REV_REQ:
            raise ValueError(f"모르는 회전 평면도형입니다: {shape}")
        _shape_keys(piece, f"pieces[{i}]", _REV_REQ[shape], _REV_OPT[shape])
        parsed.append(piece)
        if shape == "semicircle" and len(pieces) > 1:
            raise ValueError("semicircle 은 혼자만 쓸 수 있습니다 (위아래가 축에 닿는다)")

    # 조각별 (아랫폭, 윗폭, 높이, 바깥 윤곽 점열 생성기). 좌표는 cm — x 는 축에서
    # 바깥쪽(+), y 는 아래에서 위(+). 화면에 옮길 때 x 를 왼쪽으로 뒤집는다.
    outline: list[tuple[float, float]] = []  # 바깥 윤곽 (아래 → 위)
    corners: list[tuple[tuple[float, float], tuple[float, float], tuple[float, float]]] = []
    labels: list[tuple[tuple[float, float], tuple[float, float], str, str]] = []
    y = 0.0
    prev_top = None
    for i, piece in enumerate(parsed):
        shape = piece["shape"]
        flip = bool(piece.get("flip", False))
        if shape == "rect":
            pw = _num(piece["w"], "w", 0.5, 30)
            ph = _num(piece["h"], "h", 0.5, 30)
            bw, tw = pw, pw
            seg = [(pw, y), (pw, y + ph)]
        elif shape == "rightTri":
            pw = _num(piece["w"], "w", 0.5, 30)
            ph = _num(piece["h"], "h", 0.5, 30)
            bw, tw = (0.0, pw) if flip else (pw, 0.0)
            seg = [(0.0, y), (pw, y + ph)] if flip else [(pw, y), (0.0, y + ph)]
        elif shape == "rightTrap":
            pw = _num(piece["w"], "w", 0.5, 30)
            tw2 = _num(piece["w2"], "w2", 0.3, 30)
            ph = _num(piece["h"], "h", 0.5, 30)
            if abs(pw - tw2) < 1e-9:
                raise ValueError("rightTrap 은 w 와 w2 가 달라야 합니다 (같으면 rect)")
            bw, tw = pw, tw2
            seg = [(pw, y), (tw2, y + ph)]
        elif shape == "semicircle":
            pr = _num(piece["r"], "r", 0.5, 30)
            bw, tw, ph = 0.0, 0.0, 2 * pr
            seg = _rev_arc(0.0, y + pr, pr, -90.0, 90.0)
        else:  # quarter
            pr = _num(piece["r"], "r", 0.5, 30)
            ph = pr
            if flip:
                bw, tw = 0.0, pr
                seg = _rev_arc(0.0, y + pr, pr, -90.0, 0.0)
            else:
                bw, tw = pr, 0.0
                seg = _rev_arc(0.0, y, pr, 0.0, 90.0)
        if tw <= 1e-9 and i < len(parsed) - 1:
            raise ValueError("윗변이 축에 닿는 조각 위에는 더 쌓을 수 없습니다")
        if bw <= 1e-9 and i > 0:
            raise ValueError("아랫변이 축에 닿는 조각은 맨 아래에만 놓을 수 있습니다")
        if prev_top is not None and abs(prev_top - bw) > 1e-9:
            outline.append((bw, y))  # 층 사이 가로 턱
        outline += seg
        prev_top = tw
        piece_geom = (shape, flip, y, ph, bw, tw)
        # 라벨 좌표는 나중에 화면 변환 뒤 measured() 로 — cm 끝점만 기억해 둔다.
        for key, a, b in _rev_label_edges(piece, piece_geom):
            labels.append((a, b, str(piece[key]), key))
        y += ph
    total_h = y
    width = max((x for x, _ in outline), default=1.0)

    s = min(110.0 / max(total_h, 1e-9), 84.0 / max(width + gap, 1e-9), 30.0)
    pad_l = 20.0
    ax = pad_l + s * (width + gap)
    top_y = 46.0

    def scr(pt) -> tuple[float, float]:
        return (ax - s * (gap + pt[0]), top_y + s * (total_h - pt[1]))

    poly = [scr((0.0, 0.0))]
    poly += [scr(pt) for pt in outline]
    if prev_top is not None and prev_top > 1e-9:
        poly.append(scr((0.0, total_h)))
    # 연속 중복 꼭짓점 제거 — 턱 점과 다음 조각의 시작점이 같은 자리다.
    dedup: list[tuple[float, float]] = []
    for pt in poly:
        if not dedup or math.hypot(pt[0] - dedup[-1][0], pt[1] - dedup[-1][1]) > 1e-6:
            dedup.append(pt)
    if len(dedup) > 1 and math.hypot(dedup[0][0] - dedup[-1][0], dedup[0][1] - dedup[-1][1]) <= 1e-6:
        dedup.pop()
    poly = dedup
    parts = [_poly(poly, FAINT, 1.4)]

    # 직각 표시 — 곧은 변끼리 90° 로 만나는 모퉁이에만(원본: 직사각형 넷·삼각형 하나).
    pts_logical = poly
    m = len(pts_logical)
    mark = 7.0
    for i in range(m):
        p0, p1, p2 = pts_logical[i - 1], pts_logical[i], pts_logical[(i + 1) % m]
        v1 = (p0[0] - p1[0], p0[1] - p1[1])
        v2 = (p2[0] - p1[0], p2[1] - p1[1])
        l1, l2 = math.hypot(*v1), math.hypot(*v2)
        if l1 < mark * 1.5 or l2 < mark * 1.5:
            continue
        u1 = (v1[0] / l1, v1[1] / l1)
        u2 = (v2[0] / l2, v2[1] / l2)
        if abs(u1[0] * u2[0] + u1[1] * u2[1]) > 0.02:
            continue
        q1 = (p1[0] + u1[0] * mark, p1[1] + u1[1] * mark)
        q3 = (p1[0] + u2[0] * mark, p1[1] + u2[1] * mark)
        q2 = (q1[0] + u2[0] * mark, q1[1] + u2[1] * mark)
        parts.append(_polyline([q1, q2, q3], sw=0.9))

    # 회전축 — 원본대로 **가는 실선**, 도형 위·아래로 넉넉히 뻗는다.
    axis_top = 22.0
    axis_bot = top_y + s * total_h + 14.0
    parts.append(_line((ax, axis_top), (ax, axis_bot), sw=1.0))
    parts.append(_text(ax, 8.0, "ℓ", size=13))
    # 회전 화살표 — 축을 감싸는 납작한 타원 호 + 오른끝 화살촉.
    acy = 20.0
    arc = [
        (ax + REV_ARROW_RX * math.cos(math.radians(t)), acy - REV_ARROW_RY * math.sin(math.radians(t)))
        for t in range(200, -21, -10)
    ]
    parts.append(_polyline(arc, sw=1.0))
    hx, hy = arc[-1]
    parts.append(
        f'<polygon points="{_n(hx - 3.4)},{_n(hy - 2.6)} {_n(hx + 1.8)},{_n(hy - 0.4)} '
        f'{_n(hx - 2.2)},{_n(hy + 2.4)}" fill="{INK}"/>'
    )

    # 치수 라벨 — 전부 measured() 한 벌(§4-16). 반지름은 중심 점 + off=0.
    for a_cm, b_cm, text, key in labels:
        a, b = scr(a_cm), scr(b_cm)
        if key == "rLabel":
            parts.append(f'<circle cx="{_n(a[0])}" cy="{_n(a[1])}" r="2" fill="{INK}"/>')
            parts.append(_length_mark(a[0], a[1], b[0], b[1], text, off=0, fs=DIM_FS))
            continue
        cxs = sum(p[0] for p in poly) / len(poly)
        cys = sum(p[1] for p in poly) / len(poly)
        off = _outward_off(a, b, (cxs, cys), DIM_OFF)
        parts.append(_length_mark(a[0], a[1], b[0], b[1], text, off=off, fs=DIM_FS))
    # 축 위(x=0)에 앉는 라벨은 바깥 = 축 오른쪽이다. `_svg` 는 글자 닻점만 세므로
    # (09 §4-17) 그 글자 폭만큼 오른쪽 여백을 여기서 잡아 준다 — 0891 재현에서
    # 「7 cm」의 m 이 잘려 나갔다.
    pad_r = 34.0 if any(a[0] == 0.0 and b[0] == 0.0 for a, b, _t, _k in labels) else 18.0
    return _svg(ax + pad_r, axis_bot + 6.0, "".join(parts))


def _rev_label_edges(piece: Mapping[str, Any], geom) -> list:
    """조각의 라벨 키 → 잰 두 끝점(cm). 없는 라벨은 안 낸다(받은 치수만, §4-20)."""
    shape, flip, y, ph, bw, tw = geom
    out = []
    if shape == "rect":
        if "wLabel" in piece:
            out.append(("wLabel", (0.0, y), (bw, y)))
        if "hLabel" in piece:
            out.append(("hLabel", (bw, y), (bw, y + ph)))
    elif shape == "rightTri":
        base_y = y + ph if flip else y
        w_cm = bw if not flip else tw
        if "wLabel" in piece:
            out.append(("wLabel", (0.0, base_y), (w_cm, base_y)))
        if "hLabel" in piece:
            out.append(("hLabel", (0.0, y), (0.0, y + ph)))
        if "slantLabel" in piece:
            if flip:
                out.append(("slantLabel", (0.0, y), (w_cm, y + ph)))
            else:
                out.append(("slantLabel", (w_cm, y), (0.0, y + ph)))
    elif shape == "rightTrap":
        if "wLabel" in piece:
            out.append(("wLabel", (0.0, y), (bw, y)))
        if "w2Label" in piece:
            out.append(("w2Label", (0.0, y + ph), (tw, y + ph)))
        if "hLabel" in piece:
            out.append(("hLabel", (0.0, y), (0.0, y + ph)))
    elif shape == "semicircle":
        if "rLabel" in piece:
            out.append(("rLabel", (0.0, y + ph / 2), (ph / 2, y + ph / 2)))
    else:  # quarter
        if "rLabel" in piece:
            base_y = y + ph if flip else y
            out.append(("rLabel", (0.0, base_y), (ph, base_y)))
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 좌표평면 **한 벌** — `linearGraph`(직선) 과 `curveGraph`(쌍곡선·포물선) 이 같이 쓴다
# (물결 2C 2026-08-23 → 물결 4A 2026-08-24)
#
# 정본은 RPM 원본 지면이다(본문·수치는 베끼지 않고 **모양만**):
#   · 2-1 일차함수 0891(p132) — 직선 하나 + 점 (4,3)·(-4,-1) 을 **점선 안내선**으로
#     축에 잇고 그 발치에만 숫자. 점 자체에는 표식이 없다(원본도 없다).
#   · 2-1 0974(p144) — 절편 숫자는 직선이 축을 지나는 자리 **옆에** 적는다(6·2).
#   · 2-1 0882(p130)·0975(p144) — 두 직선 교점·평행. 식 라벨은 직선 위끝 부근.
#   · 1-1 정비례와 반비례 1077(p146) — 쌍곡선 **두 가지**(1·3사분면), 곡선이 축보다
#     굵고, 점에서 두 축으로 점선 안내선, 식 라벨은 위 가지 옆.
#   · 3-1 이차함수 0962·1070(p137·p154) — 포물선의 꼭짓점을 **같은 점선 안내선**으로
#     축에 잇고 숫자만 적는다. 축(x=p)을 따로 긋는 것은 개념 상자의 문법이고,
#     문항 지면은 안 긋는다 — 그래서 kind 에도 안 넣었다.
#
# ## 왜 한 벌인가
#
# 중1 「정비례와 반비례」는 **같은 중단원에** 직선(정비례)과 쌍곡선(반비례)이 있다 —
# 한 시험지에 나란히 실린다. 규칙이 두 벌이면 축·눈금·화살촉·글자 크기가 그래프마다
# 달라지고, 한쪽만 고쳐진다(이 저장소의 되풀이되는 결함).
#
# ## 지면 폭을 박는다 — 안 박으면 **글자 크기가 그래프마다 뒤집힌다**
#
# `viewBox` 폭 하나로 지면 등급(≤160 → 140px · ≤320 → 240px · 그 위)이 갈린다.
# 폭을 내용이 정하게 두면 같은 kind 인데 범위가 한 칸 바뀔 때마다 등급이 넘나든다.
#
# **실측(2026-08-24, 이 저장소가 이미 내보내던 값)**: 옛 `linearGraph` 는 범위·라벨에
# 따라 viewBox 폭이 126~238 로 떠다녔고, 눈금 글자가 지면에서 **10.50px ~ 17.78px**
# 이었다. 그중 셋(폭 142·144·160)은 본문 12.5px **아래**다 — 에러는 안 났다.
# 그래서 폭을 `CP_VIEWBOX` 로 **박고**, 벌어지면 던진다(`_cp_svg`).
#
# ## 등척이다 — x·y 한 칸이 같은 px
#
# 두 축의 칸이 다르면 「기울기 1」이 45°로 안 보인다 — 그린 값이 적힌 값이어야
# 한다(09 §4-21). 시험이 «기울기 m 직선의 화면 dx/dy == 1/m» 을 잠근다.
#
# ## 던지는 것 (D-70 — 못 담으면 조용히 구겨 넣지 않는다)
#
#   · `marks` 의 점이 어느 직선·곡선 위에도 없으면 — **검산 겸용이다.** 생성기가
#     역산을 틀리면 그림이 먼저 던진다. 그래서 marks 는 정수만 받는다.
#   · 범위가 원점을 안 품으면 — 원점 O·화살촉 문법이 성립하지 않는다.
#   · 식 라벨이 그림보다 넓으면 — 잘린 라벨은 지면에서 티가 안 난다.
# ═══════════════════════════════════════════════════════════════════════════

# 지면 폭을 박는 값. **`src/lib/figure/figureSvgFrame.ts` 와 맞물린다** —
# `CP_VIEWBOX` 는 `FIGURE_SVG_MID_VIEWBOX`(320) 이하라 «mid» 등급이 되고,
# 그때 실제로 그려지는 폭이 `CP_FRAME_PX`(= `FIGURE_SVG_MID_MAX_PX`) 다.
# 어긋나면 가드가 통과시킨 그림이 지면에서 작아진다 — `figureCurveGraph.test.ts`
# 가 두 파일의 숫자를 대조한다(한쪽만 고치면 빨개진다).
CP_VIEWBOX = 240.0
CP_FRAME_PX = 240.0
# 눈금 숫자·식 라벨 크기(그림 단위). 폭을 박았으므로 **지면 px = CP_FONT × 배율** 이고
# 배율은 CP_FRAME_PX / CP_VIEWBOX = 1 이다. 본문(BODY_TEXT_PX) 아래로 내려가면 던진다
# (`_cp_assert_readable`) — 옛 12 는 폭 240 에서 정확히 12.0px 이라 본문보다 작았다.
CP_FONT = 13.0
CP_MAX_H = 240.0        # 세로 상한. 폭과 달리 등급과 무관하지만 지면에서 길어지면 못 쓴다
CP_PAD_L = 26.0         # 축 왼쪽 최소 여백(y축 눈금 숫자 자리)
CP_PAD_T = 24.0
CP_PAD_R = 26.0         # 화살촉 뒤 여백(식 라벨 자리)
CP_PAD_B = 8.0
CP_TICK = 2.6           # 정수 눈금 짧은 획 절반 길이
CP_AXIS_OVER = 11.0     # 축이 범위 밖으로 나가는 길이(화살촉 앞)
CP_ARROW = 7.0          # 화살촉 길이
CP_GUIDE_DASH = "4 3"   # 점선 안내선 (숨은 모서리 "5 4"·치수 "6 4" 와 구분)
CP_SLOPE_MAX = 6.0      # 기울기 극단 상한 — tan⁻¹6 ≈ 80.5° (0882 의 3 이 실측 최대급)
CP_MIN_SEG = 0.45       # 직선의 보이는 토막 최소 길이(짧은 범위 변 대비 비율)
CP_SPAN_MIN = 4         # 범위 폭(칸)
CP_SPAN_MAX = 12
CP_GRAPH_SW = 1.9       # 직선·곡선 굵기. 축(1.0)·눈금(0.9)보다 굵다 — 원본과 같은 위계
CP_LABEL_GAP = 26.0     # 라벨이 축에 겹칠 때 비키는 거리
# marks 가 그래프 위인가 — 잔차 허용치. **반올림한 손 좌표를 걸러 내는 값이다.**
# 이 자리에 있을 수 있는 오차는 배정도 부동소수의 반올림뿐이라(값이 20 이하면 ~1e-15)
# 1e-9 는 그보다 여섯 자리 넉넉하고, 소수 여섯째 자리 어긋남(1e-6)도 확실히 막는다.
# 시험이 양쪽을 다 못 박는다: 1e-6 어긋난 점은 던지고, 1/3 같은 유리수 격자점은 통과한다.
CP_ON_EPS = 1e-9


def _cp_assert_readable() -> None:
    """눈금 글자가 **지면에서** 본문 이상인가. 폭을 박았으니 배율이 곧 답이다.

    참을 어림으로 만들지 않는다 — 그림을 그리는 그 상수(`CP_FONT`)와 지면이 정하는
    폭(`CP_FRAME_PX`/`CP_VIEWBOX`)에서 바로 계산한다(`_assert_ticks_readable` 와 같은 무늬).
    """
    px = CP_FONT * CP_FRAME_PX / CP_VIEWBOX
    if px < BODY_TEXT_PX:
        raise ValueError(
            f"좌표평면 눈금 글자가 지면에서 {px:.2f}px 이 됩니다 "
            f"(본문 {BODY_TEXT_PX}px 이상이어야 합니다) — CP_FONT 또는 CP_VIEWBOX 를 고치십시오"
        )


def _cp_text(x: float, y: float, t: Any, *, anchor: str = "middle", italic: bool = False) -> str:
    """좌표평면 글자 — 원본 지면처럼 **가는 명조**다(발문 굵기가 아니다).

    크기는 **한 값**(`CP_FONT`)뿐이다. 눈금 숫자와 식 라벨이 따로 놀면 한쪽만
    본문 아래로 내려가도 아무도 모른다.
    """
    style = ' font-style="italic"' if italic else ""
    return (
        f'<text x="{_n(x)}" y="{_n(y)}" fill="{INK}" font-size="{_n(CP_FONT)}" '
        f'font-family="Batang, serif" font-weight="400"{style} text-anchor="{anchor}" '
        f'dominant-baseline="middle">{_esc(t)}</text>'
    )


class _Plane:
    """좌표평면 한 장의 배치. **폭이 박혀 있으므로 칸(u)은 범위가 정한다.**"""

    __slots__ = ("xlo", "xhi", "ylo", "yhi", "u", "pad_l", "height")

    def __init__(self, xlo: int, xhi: int, ylo: int, yhi: int) -> None:
        self.xlo, self.xhi, self.ylo, self.yhi = xlo, xhi, ylo, yhi
        span_x, span_y = xhi - xlo, yhi - ylo
        # 가로는 **박힌 폭**이, 세로는 상한이 칸을 정한다. 둘 중 작은 쪽 — 등척이다.
        #
        # 칸 크기에 따로 상한을 두지 않는다. 두면 좁은 범위에서 그림이 프레임 한가운데
        # 작게 뜨고 양옆이 빈다 — 폭을 박은 뒤에는 **채우는 쪽**이 지면에서 낫다
        # (실렌더로 견줬다). 범위가 다르면 칸이 다른 것은 당연하고, 한 그림 안에서
        # x·y 칸이 같은 것(등척)만 지키면 된다.
        avail_w = CP_VIEWBOX - CP_PAD_L - CP_AXIS_OVER - CP_ARROW - CP_PAD_R
        avail_h = CP_MAX_H - CP_PAD_T - CP_AXIS_OVER - CP_PAD_B
        self.u = min(avail_w / span_x, avail_h / span_y)
        # 그린 것(왼쪽 축 끝 ~ 화살촉 끝)을 프레임 한가운데에 놓는다.
        ink = span_x * self.u + 2 * CP_AXIS_OVER + CP_ARROW
        self.pad_l = max(CP_PAD_L, (CP_VIEWBOX - ink) / 2 + CP_AXIS_OVER)
        self.height = CP_PAD_T + span_y * self.u + CP_AXIS_OVER + CP_PAD_B

    def sx(self, x: float) -> float:
        return self.pad_l + (x - self.xlo) * self.u

    def sy(self, y: float) -> float:
        return CP_PAD_T + (self.yhi - y) * self.u

    @property
    def ax(self) -> float:
        return self.sx(0.0)

    @property
    def ay(self) -> float:
        return self.sy(0.0)

    @property
    def x_end(self) -> float:
        return self.sx(self.xhi) + CP_AXIS_OVER

    @property
    def y_end(self) -> float:
        return self.sy(self.yhi) - CP_AXIS_OVER

    def inside(self, x: float, y: float) -> bool:
        e = 1e-9
        return self.xlo - e <= x <= self.xhi + e and self.ylo - e <= y <= self.yhi + e


def _cp_range(spec: Mapping[str, Any], name: str) -> tuple[int, int]:
    rng = spec[name]
    if not isinstance(rng, list) or len(rng) != 2:
        raise ValueError(f"{name} 은 [lo, hi] 여야 합니다")
    lo = _int(rng[0], f"{name}[0]", -20, 20)
    hi = _int(rng[1], f"{name}[1]", -20, 20)
    if lo > -1 or hi < 1:
        raise ValueError(f"{name} 은 원점을 품어야 합니다 (lo ≤ -1, hi ≥ 1)")
    if not CP_SPAN_MIN <= hi - lo <= CP_SPAN_MAX:
        raise ValueError(f"{name} 폭은 {CP_SPAN_MIN}~{CP_SPAN_MAX}칸이어야 합니다")
    return lo, hi


def _cp_plane(spec: Mapping[str, Any]) -> _Plane:
    _cp_assert_readable()
    xlo, xhi = _cp_range(spec, "xRange")
    ylo, yhi = _cp_range(spec, "yRange")
    return _Plane(xlo, xhi, ylo, yhi)


def _cp_label(raw: Any, name: str) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str) or not 1 <= len(raw) <= 20:
        raise ValueError(f"{name} 은 1~20자 문자열이어야 합니다")
    if _label_w_max(raw, CP_FONT) > CP_VIEWBOX - 2 * FIT_PAD:
        raise ValueError(f"{name} 이 그림보다 넓습니다 — 식을 줄이십시오")
    return raw


def _cp_lines(spec: Mapping[str, Any]) -> list[tuple[float, float, str | None]]:
    """`lines` — 기울기·y절편·식 라벨. `linearGraph` 와 `curveGraph` 가 같이 쓴다."""
    lines = spec.get("lines", [])
    if not isinstance(lines, list) or len(lines) > 3:
        raise ValueError("lines 는 최대 3개의 객체 목록이어야 합니다")
    parsed: list[tuple[float, float, str | None]] = []
    for i, ln in enumerate(lines):
        if not isinstance(ln, Mapping):
            raise ValueError(f"lines[{i}] 는 객체여야 합니다")
        extra = set(ln) - {"slope", "yIntercept", "label"}
        if extra:
            raise ValueError(f"lines[{i}] 허용되지 않은 키: {', '.join(sorted(map(str, extra)))}")
        m = _num(ln.get("slope"), f"lines[{i}].slope", -CP_SLOPE_MAX, CP_SLOPE_MAX)
        if abs(m) < 1.0 / CP_SLOPE_MAX:
            raise ValueError(f"lines[{i}].slope 이 극단입니다 — 축과 겹쳐 보입니다 (|m| 은 1/6~6)")
        b = _num(ln.get("yIntercept"), f"lines[{i}].yIntercept", -20, 20)
        label = _cp_label(ln.get("label"), f"lines[{i}].label")
        for pm, pb, _pl in parsed:
            if abs(pm - m) < 1e-12 and abs(pb - b) < 1e-12:
                raise ValueError("같은 직선이 두 번 있습니다")
        parsed.append((m, b, label))
    return parsed


def _cp_clip_line(m: float, b: float, pl: _Plane):
    """직선 y=mx+b 를 범위 상자에 자른 토막 — 없으면 None. 끝점은 경계 위다."""
    xlo, xhi, ylo, yhi = pl.xlo, pl.xhi, pl.ylo, pl.yhi
    if m > 0:
        xa = max(xlo, (ylo - b) / m)
        xb = min(xhi, (yhi - b) / m)
    else:
        xa = max(xlo, (yhi - b) / m)
        xb = min(xhi, (ylo - b) / m)
    if xa >= xb - 1e-12:
        return None
    return (xa, m * xa + b), (xb, m * xb + b)


def _cp_line_segs(pl: _Plane, lines) -> list:
    """직선을 상자에 자른다. 없거나 구석만 스치면 던진다(직선이 아니라 흠집으로 보인다)."""
    segs = []
    for m, b, _l in lines:
        seg = _cp_clip_line(m, b, pl)
        if seg is None:
            raise ValueError(f"직선 y={_n(m)}x{b:+g} 이 범위 안에 없습니다")
        (xa, ya), (xb, yb) = seg
        if math.hypot(xb - xa, yb - ya) < CP_MIN_SEG * min(pl.xhi - pl.xlo, pl.yhi - pl.ylo):
            raise ValueError(f"직선 y={_n(m)}x{b:+g} 이 범위 구석만 스칩니다 — 범위를 옮기십시오")
        segs.append(seg)
    return segs


def _cp_marks(spec: Mapping[str, Any], pl: _Plane, on_graph) -> list[tuple[int, int]]:
    """`marks` — 정수 격자점. **어느 그래프 위에도 없으면 던진다**(검산 겸용).

    부동소수 «위에 있음» 판정은 지어낸 참이 되기 쉬워서 좌표는 정수만 받는다.
    잔차 허용치는 `on_graph` 가 정하고, 시험이 그 값을 못 박는다.
    """
    raw = spec.get("marks", [])
    if not isinstance(raw, list) or len(raw) > 4:
        raise ValueError("marks 는 최대 4개의 [x, y] 목록이어야 합니다")
    out: list[tuple[int, int]] = []
    for i, mk in enumerate(raw):
        if not isinstance(mk, list) or len(mk) != 2:
            raise ValueError(f"marks[{i}] 는 [x, y] 여야 합니다")
        mx = _int(mk[0], f"marks[{i}][0]", pl.xlo, pl.xhi)
        my = _int(mk[1], f"marks[{i}][1]", pl.ylo, pl.yhi)
        if mx == 0 and my == 0:
            raise ValueError(f"marks[{i}] 가 원점입니다 — 원점은 O 로 이미 표기합니다")
        if not on_graph(mx, my):
            raise ValueError(f"marks[{i}] = ({mx}, {my}) 가 어느 그래프 위에도 없습니다")
        out.append((mx, my))
    return out


def _cp_grid_flag(spec: Mapping[str, Any]) -> bool:
    grid = spec.get("grid", False)
    if not isinstance(grid, bool):
        raise ValueError("grid 는 true/false 여야 합니다")
    return grid


# 🔴 **`O` 는 그래프가 안 지나는 사분면에 앉는다** — RPM 정본에서 배웠다.
#
# 원장님 지시(2026-08-28): 「RPM 1학기 교재에서 함수파트를 보고 함수 파트에서 라벨
# 위치를 분석하고 학습해. 그래야 어떻게 라벨위치를 **선과 안겹치게** 배치하는지
# 파악할 수 있을것 같네」.
#
# 실측(`scripts/qa/measure-rpm-function-labels.py` — 1학기 함수 단원 3권,
# 원점 라벨 291개):
#   · 앉는 자리 — 왼아래(제3사분면) **64.9%** · 오른아래 14.4% · 왼위 5.5% · 오른위 3.1%
#   · **고를 자리가 있을 때 79.9% 가 「그래프가 안 지나는」 사분면**이다
#   · 축과의 여백은 글자 크기의 **0.17배**(중앙값)
#
# 종전에는 `(-7, +10)` **한 자리에 못 박혀** 있었다. 그래서 기울기가 양수인 직선처럼
# 제3사분면을 지나는 그래프에서는 `O` 가 그 선 위에 그대로 앉았다 — 실측
# `1-1|정비례와 반비례|09`: 직선이 글자 상자 **안을 지난다**(표본점 16개).
# 원장님이 화면에서 처음 짚으신 결함이 바로 이 자리다.
# 자리는 **여백에서 거꾸로 유도한다** — 좌표를 손으로 박지 않는다. 박으면 글자
# 크기를 바꿀 때 여백이 조용히 달라지고, 칸(u)이 좁은 그림에서는 첫 눈금 획을
# 스친다(실측 `1-1|정비례와 반비례|10`: 종전 `dy=10` 이 y축 −1 눈금과 0.45 겹쳤다).
#
# ⚠️ **RPM 의 거리(0.79배)를 그대로 베끼면 안 된다.** 우리 `O` 는 조판본이라
#    정본보다 넓다 — 폭이 글자 크기의 0.78배(실측 10.114/13)인데 RPM 은 0.58배다.
#    같은 거리를 쓰면 여백이 0.06배로 좁아진다. **여백을 지키면 거리는 따라온다**:
#    아래 값으로 나오는 거리가 0.76배로 정본의 0.79배와 맞는다(서로 다른 두 수가
#    맞아떨어지는 것이 이 유도가 옳다는 검산이다).
CP_O_CLEAR = 0.17          # RPM 실측 — 획까지 띄우는 몫 (글자 크기 배, 중앙값)
CP_O_HALF_W = 0.39         # 조판된 `O` 폭의 절반 ÷ 글자 크기 (실측 10.114/13/2)
CP_O_HALF_H = 0.365        # 그 잉크 높이의 절반 ÷ 글자 크기 (실측 9.451/13/2)
_O_DX = round((CP_O_HALF_W + CP_O_CLEAR) * CP_FONT, 2)
_O_DY = round((CP_O_HALF_H + CP_O_CLEAR) * CP_FONT, 2)
CP_O_CORNERS = ((-_O_DX, _O_DY), (_O_DX, _O_DY), (-_O_DX, -_O_DY), (_O_DX, -_O_DY))


def _seg_hits_box(a: tuple[float, float], b: tuple[float, float],
                  box: tuple[float, float, float, float]) -> bool:
    """선분이 상자와 만나는가 (Liang–Barsky).

    ⚠️ **표본점을 찍어 «상자 안에 있나»로 묻지 마라.** 상자가 작고 선분이 길면
       표본이 상자를 건너뛴다 — 겹쳤는데 «안 겹쳤다»가 나오고, 그 실패는
       조용하다. 여기서는 자른다.
    """
    x0, y0 = a
    dx, dy = b[0] - x0, b[1] - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - box[0]), (dx, box[2] - x0),
                 (-dy, y0 - box[1]), (dy, box[3] - y0)):
        if p == 0.0:
            if q < 0.0:
                return False        # 그 축에 나란한데 밖이다
            continue
        r = q / p
        if p < 0.0:
            if r > t1:
                return False
            t0 = max(t0, r)
        else:
            if r < t0:
                return False
            t1 = min(t1, r)
    return t0 <= t1


def _cp_o_offset(pl: _Plane, inks: list) -> tuple[float, float]:
    """`O` 를 놓을 모서리 — RPM 순서로 훑어 **선이 안 지나는 첫 자리**를 고른다.

    `inks` 는 그린 것의 **화면 좌표 폴리라인**이다(그래프·곡선·점선 안내선).

    ⚠️ **축과 눈금은 넣지 마라.** 그 둘은 원점에서 사방으로 뻗으므로 넣으면
       네 자리가 다 막히고, 이 고르기가 **구조적으로 늘 첫 자리**를 낸다 —
       고치기 전과 똑같아지는데 아무 에러도 안 난다. RPM 도 `O` 를 축 바로
       옆(여백 0.17배)에 붙인다.
    ⚠️ 네 자리가 다 막히면 첫 자리로 돌아온다. 정본도 그렇다 — 빈 사분면이
       없는 그림이 291개 중 27개였다.
    """
    hw = (CP_O_HALF_W + CP_O_CLEAR) * CP_FONT
    hh = (CP_O_HALF_H + CP_O_CLEAR) * CP_FONT
    for dx, dy in CP_O_CORNERS:
        cx, cy = pl.ax + dx, pl.ay + dy
        box = (cx - hw, cy - hh, cx + hw, cy + hh)
        if not any(_seg_hits_box(p, q, box)
                   for pts in inks for p, q in zip(pts, pts[1:])):
            return dx, dy
    return CP_O_CORNERS[0]


def _cp_guide_polylines(pl: _Plane, marks: list[tuple[int, int]]) -> list[list]:
    """점선 안내선의 **기하**. 그리는 쪽(`_cp_mark_parts`)과 `O` 고르기가 같이 쓴다 —
    규칙이 두 벌이 되면 한쪽만 고쳐도 아무도 모른다."""
    ax, ay = pl.ax, pl.ay
    return [[(pl.sx(mx), ay), (pl.sx(mx), pl.sy(my)), (ax, pl.sy(my))]
            for mx, my in marks if mx != 0 and my != 0]


def _cp_frame_parts(pl: _Plane, grid: bool,
                    o_offset: tuple[float, float] = CP_O_CORNERS[0]) -> list[str]:
    """모눈 → 축·화살촉·라벨 x·y·O → 정수 눈금 짧은 획. **이 셋이 한 벌이다.**"""
    parts: list[str] = []
    if grid:
        for gx in range(pl.xlo, pl.xhi + 1):
            if gx == 0:
                continue
            parts.append(_grid_line((pl.sx(gx), pl.sy(pl.yhi)), (pl.sx(gx), pl.sy(pl.ylo))))
        for gy in range(pl.ylo, pl.yhi + 1):
            if gy == 0:
                continue
            parts.append(_grid_line((pl.sx(pl.xlo), pl.sy(gy)), (pl.sx(pl.xhi), pl.sy(gy))))

    ax, ay, x_end, y_end = pl.ax, pl.ay, pl.x_end, pl.y_end
    parts.append(_line((pl.sx(pl.xlo) - CP_AXIS_OVER, ay), (x_end, ay), sw=1.0))
    parts.append(_line((ax, pl.sy(pl.ylo) + CP_AXIS_OVER), (ax, y_end), sw=1.0))
    parts.append(
        f'<polygon points="{_n(x_end + CP_ARROW)},{_n(ay)} {_n(x_end)},{_n(ay - 2.8)} '
        f'{_n(x_end)},{_n(ay + 2.8)}" fill="{INK}"/>'
    )
    parts.append(
        f'<polygon points="{_n(ax)},{_n(y_end - CP_ARROW)} {_n(ax - 2.8)},{_n(y_end)} '
        f'{_n(ax + 2.8)},{_n(y_end)}" fill="{INK}"/>'
    )
    parts.append(_cp_text(x_end + 4.0, ay + 12.0, "x", italic=True))
    parts.append(_cp_text(ax - 9.0, y_end - 4.0, "y", italic=True))
    parts.append(_cp_text(ax + o_offset[0], ay + o_offset[1], "O"))

    for gx in range(pl.xlo, pl.xhi + 1):
        if gx == 0:
            continue
        parts.append(_line((pl.sx(gx), ay - CP_TICK), (pl.sx(gx), ay + CP_TICK), sw=0.9))
    for gy in range(pl.ylo, pl.yhi + 1):
        if gy == 0:
            continue
        parts.append(_line((ax - CP_TICK, pl.sy(gy)), (ax + CP_TICK, pl.sy(gy)), sw=0.9))
    return parts


def _cp_mark_parts(pl: _Plane, marks: list[tuple[int, int]]) -> list[str]:
    """점선 안내선 + 숫자 — 0891 문법. 축 위의 점(절편)은 안내선 없이 숫자만(0974)."""
    parts: list[str] = []
    ax, ay = pl.ax, pl.ay
    done: set[tuple[str, int]] = set()
    # 안내선 기하는 `_cp_guide_polylines` 한 곳에서 온다 — `O` 고르기가 같은 것을 본다.
    guides = {(mx, my): pts for (mx, my), pts
              in zip([(mx, my) for mx, my in marks if mx != 0 and my != 0],
                     _cp_guide_polylines(pl, marks))}
    for mx, my in marks:
        if mx != 0 and my != 0:
            parts.append(_polyline(guides[(mx, my)], sw=0.9, dash=CP_GUIDE_DASH))
        if mx != 0 and ("x", mx) not in done:
            done.add(("x", mx))
            # 숫자는 안내선 반대쪽 — 점이 위면 축 아래(0891 의 4), 아래면 축 위(0891 의 -4).
            ny = ay + 11.0 if my >= 0 else ay - 8.0
            parts.append(_cp_text(pl.sx(mx) + (-5.0 if mx > 0 else 5.0), ny, mx))
        if my != 0 and ("y", my) not in done:
            done.add(("y", my))
            if mx >= 0:
                parts.append(_cp_text(ax - 5.0, pl.sy(my) + 1.0, my, anchor="end"))
            else:
                parts.append(_cp_text(ax + 5.0, pl.sy(my) + 1.0, my, anchor="start"))
    return parts


def _cp_fit_label(pl: _Plane, spot: tuple[float, float], half: float) -> tuple[float, float]:
    """라벨 닻점을 프레임 안으로 당긴다 — **잘린 라벨은 지면에서 티가 안 난다.**

    `_svg` 는 `<text>` 의 닻점만 세므로 글자가 밖으로 나가도 viewBox 가 안 넓어진다.
    그래서 여기서 글자 폭(`half`)까지 재서 넣는다.
    """
    lo, hi = FIT_PAD + half, CP_VIEWBOX - FIT_PAD - half
    x = min(max(spot[0], min(max(30.0, lo), hi)), max(min(pl.x_end - 4.0, hi), lo))
    return min(max(x, lo), hi), spot[1]


def _cp_label_parts(pl: _Plane, items: list) -> list[str]:
    """식 라벨 — 앞 라벨과 겹치면 **대안 자리**로 옮긴다. 둘이 위 경계를 가까이서
    나가면 위끝 라벨이 포개져 못 읽는다(실사 미리보기에서 확인).

    `items` 는 (라벨, 우선 자리, 대안 자리). **자리는 모양이 정한다** — 직선은 위끝의
    기울기가 비는 쪽(0882), 곡선은 위끝에서 y축 반대쪽(1077). 겹침·프레임 처리만
    여기 한 곳에 있다.
    """
    parts: list[str] = []
    placed: list[tuple[float, float]] = []
    for label, first, second in items:
        half = _label_w_max(label, CP_FONT) / 2
        cand = _cp_fit_label(pl, first, half)
        if any(abs(cand[0] - px) < 46.0 and abs(cand[1] - py) < 14.0 for px, py in placed):
            cand = _cp_fit_label(pl, second, half)
        placed.append(cand)
        parts.append(_cp_text(cand[0], cand[1], label, italic=True))
    return parts


def _cp_line_label_items(pl: _Plane, lines, segs) -> list:
    """직선 라벨 자리 — 직선 위끝 부근(0882). 축과 겹치면 **기울기의 빈 쪽**으로 비킨다."""

    def spot(m: float, end: tuple[float, float], at_top: bool) -> tuple[float, float]:
        ex, ey = end
        if abs(ex - pl.ax) < CP_LABEL_GAP + 2.0:
            free_right = (m > 0) == at_top  # 위끝은 기울기 쪽이, 아래끝은 반대쪽이 빈다
            ex += CP_LABEL_GAP if free_right else -CP_LABEL_GAP
        return ex, (ey - 8.0 if at_top else ey + 12.0)

    items = []
    for (m, _b, label), ((xa, ya), (xb, yb)) in zip(lines, segs):
        if not label:
            continue
        top, bot = (pl.sx(xa), pl.sy(ya)), (pl.sx(xb), pl.sy(yb))
        if top[1] > bot[1]:
            top, bot = bot, top
        items.append((label, spot(m, top, True), spot(-m, bot, False)))
    return items


def _cp_svg(pl: _Plane, parts: list[str]) -> str:
    """**폭을 박아** 내보낸다. 벌어졌으면 던진다.

    `_svg` 는 그린 것이 넘치면 viewBox 를 **넓혀** 준다. 잘림을 막는 좋은 성질이지만
    여기서는 폭이 곧 지면 등급이라 넓어지는 순간 이 그림만 화면에서 작아진다 —
    그리고 아무 에러도 안 난다. 그래서 넓어졌으면 멈춘다(`_stat_svg` 와 같은 무늬).

    ⚠️ `_svg` 는 `<text>` 의 **닻점만** 세므로 라벨 글자 폭은 여기 안 잡힌다.
       그 몫은 `_cp_label_parts` 가 `_label_w_max` 로 재서 안쪽으로 당긴다.
    """
    return _fixed_width_svg(
        CP_VIEWBOX, pl.height, "".join(parts), "좌표평면", "범위를 좁히십시오"
    )


def _linear_graph(spec: Mapping[str, Any]) -> str:
    lines = _cp_lines(spec)
    if not lines:
        raise ValueError("lines 는 1~3개여야 합니다")
    pl = _cp_plane(spec)

    def on_line(x: float, y: float) -> bool:
        return any(abs(y - (m * x + b)) < CP_ON_EPS for m, b, _l in lines)

    marks = _cp_marks(spec, pl, on_line)
    grid = _cp_grid_flag(spec)
    segs = _cp_line_segs(pl, lines)

    # `O` 는 **그린 것을 보고** 자리를 고른다 (RPM 실측 — `CP_O_CORNERS` 주석).
    inks = [[(pl.sx(xa), pl.sy(ya)), (pl.sx(xb), pl.sy(yb))]
            for (xa, ya), (xb, yb) in segs]
    inks += _cp_guide_polylines(pl, marks)

    parts = _cp_frame_parts(pl, grid, _cp_o_offset(pl, inks))
    parts += _cp_mark_parts(pl, marks)
    for (xa, ya), (xb, yb) in segs:
        parts.append(_line((pl.sx(xa), pl.sy(ya)), (pl.sx(xb), pl.sy(yb)), sw=CP_GRAPH_SW))
    parts += _cp_label_parts(pl, _cp_line_label_items(pl, lines, segs))
    return _cp_svg(pl, parts)


# ═══════════════════════════════════════════════════════════════════════════
# curveGraph — 쌍곡선(반비례)·포물선(이차함수)·직선을 **한 kind** 로 (물결 4A, 2026-08-24)
#
# 막고 있던 것: 중1 「정비례와 반비례」 21유형 + 중3 「이차함수의 그래프 ⑴⑵」 42유형.
# 둘을 따로 파면 축·눈금·화살촉·라벨 규칙이 두 벌이 되어 한쪽만 고쳐진다 —
# 그래서 위 좌표평면 한 벌(`_cp_*`)을 그대로 쓰고, 여기서는 **곡선만** 더한다.
#
# ## 곡선을 자르는 법 — 종류마다 손으로 풀지 않는다
#
# 「어디까지 보이나」를 종류별 닫힌 식으로 풀면 종류를 더할 때마다 규칙이 는다.
# 대신 x 를 촘촘히 훑어 **범위 안에 있는 토막**을 찾고 경계를 이분법으로 다듬는다
# (`_cg_runs`). 그래서 쌍곡선의 「두 가지」도, 꼭짓점이 밖인 포물선도 같은 코드가 본다.
# 그리는 점은 **꺾임이 안 보일 만큼만** 남긴다(`_cg_thin`) — 촘촘히 찍으면 지면
# 마크업이 곡선 하나에 5KB 를 먹는다.
#
# ## 던지는 것 (D-70)
#
#   · `marks` 가 어느 곡선·직선 위에도 없으면 — 검산 겸용(위 `_cp_marks`).
#     허용치 `CP_ON_EPS` 는 **반올림한 손 좌표를 걸러 내는** 값이다.
#   · 쌍곡선이 **두 가지로 안 보이면** — 한 가지만 그리면 반비례가 아니다.
#   · 가지·팔이 축에 너무 붙거나(`CG_ASYM_GAP`) 실오라기면(`CG_MIN_ARC`) — 곡선이
#     점근선에 닿은 것처럼 보이거나 흠집으로 보인다.
#   · 포물선의 꼭짓점이 범위 밖이면 — 그림이 포물선으로 안 읽힌다.
#   · 포물선이 범위 안에서 거의 안 휘면(`CG_PARA_RISE`) — 직선과 구별이 안 된다.
# ═══════════════════════════════════════════════════════════════════════════

CG_MAX_CURVES = 3
CG_SCAN = 1200          # 「어디까지 보이나」를 찾는 훑기 표본 수
CG_SAMPLES = 400        # 토막 하나를 뜨는 표본 수 (아래에서 솎는다)
CG_THIN_PX = 0.12       # 솎기 허용 오차(화면 단위). 선 굵기 1.9 의 1/16 이라 눈에 안 띈다
CG_REFINE = 40          # 경계 이분법 횟수 — 2^-40 칸이면 화면 픽셀의 1조분의 1이다
CG_ASYM_GAP = 0.5       # 곡선이 좌표축에서 떨어져 있어야 하는 최소 칸수
CG_MIN_ARC = 1.2        # 토막 하나의 최소 가로 칸수
CG_PARA_RISE = 1.0      # 포물선이 범위 안에서 휘어야 하는 최소 세로 칸수
CG_K_MAX = 60           # 반비례 상수 |k| 상한
CG_A_MAX = 8.0          # 이차항 계수 |a| 상한 (하한은 1/8)


def _cg_curves(spec: Mapping[str, Any]) -> list[dict]:
    raw = spec["curves"]
    if not isinstance(raw, list) or not 1 <= len(raw) <= CG_MAX_CURVES:
        raise ValueError(f"curves 는 1~{CG_MAX_CURVES}개여야 합니다")
    out: list[dict] = []
    for i, c in enumerate(raw):
        if not isinstance(c, Mapping):
            raise ValueError(f"curves[{i}] 는 객체여야 합니다")
        kind = c.get("type")
        if kind == "inverse":
            extra = set(c) - {"type", "k", "label"}
            if extra:
                raise ValueError(
                    f"curves[{i}] 허용되지 않은 키: {', '.join(sorted(map(str, extra)))}"
                )
            k = _int(c.get("k"), f"curves[{i}].k", -CG_K_MAX, CG_K_MAX)
            if k == 0:
                raise ValueError(f"curves[{i}].k 가 0 입니다 — 반비례가 아닙니다")
            item: dict = {"type": "inverse", "k": float(k), "p": 0.0, "q": 0.0, "a": 0.0}
        elif kind == "quadratic":
            extra = set(c) - {"type", "a", "p", "q", "label"}
            if extra:
                raise ValueError(
                    f"curves[{i}] 허용되지 않은 키: {', '.join(sorted(map(str, extra)))}"
                )
            a = _num(c.get("a"), f"curves[{i}].a", -CG_A_MAX, CG_A_MAX)
            if abs(a) < 1.0 / CG_A_MAX:
                raise ValueError(f"curves[{i}].a 가 극단입니다 — 직선처럼 보입니다 (|a| 은 1/8~8)")
            p = _int(c.get("p", 0), f"curves[{i}].p", -12, 12)
            q = _int(c.get("q", 0), f"curves[{i}].q", -20, 20)
            item = {"type": "quadratic", "a": a, "p": float(p), "q": float(q), "k": 0.0}
        else:
            raise ValueError(f"curves[{i}].type 은 inverse 또는 quadratic 이어야 합니다")
        item["label"] = _cp_label(c.get("label"), f"curves[{i}].label")
        for prev in out:
            if all(prev[key] == item[key] for key in ("type", "k", "a", "p", "q")):
                raise ValueError("같은 곡선이 두 번 있습니다")
        out.append(item)
    return out


def _cg_fn(curve: Mapping[str, Any]):
    if curve["type"] == "inverse":
        k = curve["k"]
        return lambda x: None if abs(x) < 1e-12 else k / x
    a, p, q = curve["a"], curve["p"], curve["q"]
    return lambda x: a * (x - p) * (x - p) + q


def _cg_desc(curve: Mapping[str, Any]) -> str:
    if curve["type"] == "inverse":
        return f"쌍곡선 y={_n(curve['k'])}/x"
    return f"포물선 (꼭짓점 {_n(curve['p'])}, {_n(curve['q'])} · a={_n(curve['a'])})"


def _cg_runs(fn, pl: _Plane) -> list[tuple[float, float]]:
    """`fn` 이 범위 상자 **안**에 있는 x 토막들. 경계는 이분법으로 다듬는다.

    종류마다 닫힌 식으로 풀지 않는다 — 그러면 곡선을 더할 때마다 규칙이 는다.
    """
    xlo, xhi = float(pl.xlo), float(pl.xhi)
    step = (xhi - xlo) / CG_SCAN

    def ok(x: float) -> bool:
        y = fn(x)
        return y is not None and pl.ylo - 1e-12 <= y <= pl.yhi + 1e-12

    def edge(inside: float, outside: float) -> float:
        for _ in range(CG_REFINE):
            mid = (inside + outside) / 2
            if ok(mid):
                inside = mid
            else:
                outside = mid
        return inside

    runs: list[tuple[float, float]] = []
    start: float | None = None   # 지금 토막의 왼쪽 끝
    last_in: float | None = None # 마지막으로 «안»이던 x
    last_out: float | None = None  # 마지막으로 «밖»이던 x
    for i in range(CG_SCAN + 1):
        x = xlo + i * step
        if ok(x):
            if start is None:
                start = x if last_out is None else edge(x, last_out)
            last_in = x
        else:
            if start is not None and last_in is not None:
                runs.append((start, edge(last_in, x)))
            start = None
            last_out = x
    if start is not None and last_in is not None:
        runs.append((start, last_in))
    return runs


def _cg_check(curve: Mapping[str, Any], fn, runs: list[tuple[float, float]], pl: _Plane) -> None:
    """그림이 곧 검산이다 — 그려서 **말이 되는가**를 여기서 가른다."""
    what = _cg_desc(curve)
    if curve["type"] == "inverse":
        left = [r for r in runs if r[1] <= 0]
        right = [r for r in runs if r[0] >= 0]
        if len(left) != 1 or len(right) != 1:
            raise ValueError(
                f"{what} 가 두 가지로 안 보입니다 — 한 가지만 그리면 반비례가 아닙니다. "
                "범위를 넓히거나 k 를 줄이십시오"
            )
        for run in (left[0], right[0]):
            _cg_arc_check(what, run, "가지")
            near_x = min(abs(run[0]), abs(run[1]))
            near_y = min(abs(fn(run[0])), abs(fn(run[1])))
            if near_x < CG_ASYM_GAP or near_y < CG_ASYM_GAP:
                raise ValueError(
                    f"{what} 가 좌표축에 {min(near_x, near_y):.2f}칸까지 붙습니다 "
                    f"({CG_ASYM_GAP}칸 이상 떨어져야 합니다) — 점근선에 닿은 것처럼 보입니다"
                )
        return

    p, q = curve["p"], curve["q"]
    if not pl.inside(p, q):
        raise ValueError(
            f"{what} 의 꼭짓점이 범위 밖입니다 — 그림이 포물선으로 안 읽힙니다"
        )
    if len(runs) != 1:
        raise ValueError(f"{what} 의 보이는 토막이 {len(runs)}개입니다 — 범위를 옮기십시오")
    _cg_arc_check(what, runs[0], "팔")
    a, b = runs[0]
    ys = [fn(a), fn(b), q]
    if max(ys) - min(ys) < CG_PARA_RISE:
        raise ValueError(
            f"{what} 가 범위 안에서 {max(ys) - min(ys):.2f}칸밖에 안 휩니다 "
            f"({CG_PARA_RISE}칸 이상이어야 합니다) — 직선과 구별이 안 됩니다"
        )


def _cg_arc_check(what: str, run: tuple[float, float], noun: str) -> None:
    if run[1] - run[0] < CG_MIN_ARC:
        raise ValueError(
            f"{what} 의 {noun}가 {run[1] - run[0]:.2f}칸밖에 안 보입니다 "
            f"({CG_MIN_ARC}칸 이상이어야 합니다) — 곡선이 아니라 흠집으로 보입니다"
        )


def _cg_thin(pts: list[tuple[float, float]], eps: float) -> list[tuple[float, float]]:
    """꺾임이 `eps` 아래인 점을 솎는다 (Ramer–Douglas–Peucker, 되풀이 없이 쌓기)."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        if j - i < 2:
            continue
        x0, y0 = pts[i]
        x1, y1 = pts[j]
        dx, dy = x1 - x0, y1 - y0
        norm = math.hypot(dx, dy) or 1.0
        best, at = -1.0, -1
        for t in range(i + 1, j):
            px, py = pts[t]
            d = abs(dy * (px - x0) - dx * (py - y0)) / norm
            if d > best:
                best, at = d, t
        if best > eps and at > 0:
            keep[at] = True
            stack.append((i, at))
            stack.append((at, j))
    return [p for p, k in zip(pts, keep) if k]


def _cg_screen_points(fn, run: tuple[float, float], pl: _Plane) -> list:
    """곡선 한 토막의 **화면 좌표** 점들. 그리는 쪽과 `O` 고르기가 같이 쓴다."""
    a, b = run
    pts: list[tuple[float, float]] = []
    for i in range(CG_SAMPLES + 1):
        x = a + (b - a) * i / CG_SAMPLES
        y = fn(x)
        if y is None:  # pragma: no cover — 토막은 이미 범위 안이다
            continue
        # 이분법 잔차가 경계를 몇 자리 넘길 수 있다. **그리기 전에** 상자로 다시 조인다 —
        # 프레임 밖으로 새는 곡선은 지면에서 옆 문항을 덮는다.
        y = min(max(y, float(pl.ylo)), float(pl.yhi))
        pts.append((pl.sx(x), pl.sy(y)))
    return pts


def _cg_polyline(fn, run: tuple[float, float], pl: _Plane) -> str:
    return _polyline(_cg_thin(_cg_screen_points(fn, run, pl), CG_THIN_PX), sw=CP_GRAPH_SW)


def _cg_label_item(pl: _Plane, curve, fn, runs) -> tuple:
    """곡선 라벨 자리 — **위끝에서 y축 반대쪽**(1077 의 위 가지 옆).

    왜 「기울기의 빈 쪽」(직선 규칙)이 아닌가: 쌍곡선의 위끝은 **점근선 바로 옆**이라
    거기서 기울기가 거의 수직이다. 그 규칙을 그대로 대면 라벨이 y축 위로 올라앉는다
    (실렌더로 확인했다). 곡선이 비켜 갈 쪽은 기울기가 아니라 **어느 사분면에 있나**가
    정한다 — 위끝이 오른쪽이면 오른쪽이, 왼쪽이면 왼쪽이 빈다.
    """
    half = _label_w_max(curve["label"], CP_FONT) / 2
    mid_y = (pl.sy(pl.ylo) + pl.sy(pl.yhi)) / 2

    def spot(end: tuple[float, tuple[float, float]]) -> tuple[float, float]:
        gx, (ex, ey) = end
        side = 1.0 if gx >= 0 else -1.0
        # 세로로는 **가운데 쪽**으로 민다 — 위 경계에 붙은 끝은 아래로, 아래 끝은 위로.
        return ex + side * (half + 9.0), ey + (7.0 if ey < mid_y else -7.0)

    ends = [
        (x, (pl.sx(x), pl.sy(min(max(fn(x), float(pl.ylo)), float(pl.yhi)))))
        for run in runs
        for x in run
    ]
    top = min(ends, key=lambda e: (round(e[1][1], 3), -abs(e[0])))
    bot = max(ends, key=lambda e: (round(e[1][1], 3), -abs(e[0])))
    return (curve["label"], spot(top), spot(bot))


def _curve_graph(spec: Mapping[str, Any]) -> str:
    curves = _cg_curves(spec)
    lines = _cp_lines(spec)
    if len(curves) + len(lines) > 4:
        raise ValueError("곡선과 직선을 합쳐 4개까지입니다")
    pl = _cp_plane(spec)
    fns = [_cg_fn(c) for c in curves]

    def on_graph(x: float, y: float) -> bool:
        for fn in fns:
            fy = fn(x)
            if fy is not None and abs(y - fy) < CP_ON_EPS:
                return True
        return any(abs(y - (m * x + b)) < CP_ON_EPS for m, b, _l in lines)

    marks = _cp_marks(spec, pl, on_graph)
    grid = _cp_grid_flag(spec)

    runs_by_curve = []
    for curve, fn in zip(curves, fns):
        runs = _cg_runs(fn, pl)
        _cg_check(curve, fn, runs, pl)
        runs_by_curve.append(runs)
    segs = _cp_line_segs(pl, lines)

    # `O` 는 **그린 것을 보고** 자리를 고른다 (RPM 실측 — `CP_O_CORNERS` 주석).
    inks = [[(pl.sx(xa), pl.sy(ya)), (pl.sx(xb), pl.sy(yb))]
            for (xa, ya), (xb, yb) in segs]
    inks += [_cg_screen_points(fn, run, pl)
             for fn, runs in zip(fns, runs_by_curve) for run in runs]
    inks += _cp_guide_polylines(pl, marks)

    parts = _cp_frame_parts(pl, grid, _cp_o_offset(pl, inks))
    parts += _cp_mark_parts(pl, marks)
    for (xa, ya), (xb, yb) in segs:
        parts.append(_line((pl.sx(xa), pl.sy(ya)), (pl.sx(xb), pl.sy(yb)), sw=CP_GRAPH_SW))
    for fn, runs in zip(fns, runs_by_curve):
        for run in runs:
            parts.append(_cg_polyline(fn, run, pl))

    items = [
        _cg_label_item(pl, curve, fn, runs)
        for curve, fn, runs in zip(curves, fns, runs_by_curve)
        if curve["label"]
    ]
    items += _cp_line_label_items(pl, lines, segs)
    parts += _cp_label_parts(pl, items)
    return _cp_svg(pl, parts)


ADV_FIELDS: dict[str, frozenset[str]] = {
    "fracBars": frozenset({"cols", "rows", "filled"}),
    "groupDots": frozenset({"groups", "each"}),
    "barChart": frozenset({"values"}),
    "lineChart": frozenset({"values"}),
    "chartPair": frozenset({"charts"}),
    "pictograph": frozenset({"unit", "items"}),
    "stripChart": frozenset({"segments"}),
    "pieChart": frozenset({"slices"}),
    "protractor": frozenset({"deg"}),
    "rotateFlip": frozenset({"cells", "op"}),
    "symmetry": frozenset({"axis"}),
    "stackCubes": frozenset({"voxels"}),
    "cuboid": frozenset({"w", "d", "h"}),
    "prism": frozenset({"sides", "h"}),
    "pyramid": frozenset({"sides", "h"}),
    "cylinder": frozenset({"r", "h"}),
    "cone": frozenset({"r", "h"}),
    "sphere": frozenset({"r"}),
    "netCuboid": frozenset({"w", "d", "h"}),
    "netCylinder": frozenset({"r", "h"}),
    "areaPoly": frozenset({"shape", "base", "height"}),
    # 입체 kind 셋 (2026-08-23, RPM 1-2 유형07·08·14) — 위 절 참조.
    "hollowSolid": frozenset({"outer", "inner"}),
    "cutCuboid": frozenset({"w", "d", "h", "cut"}),
    "revolvePlan": frozenset({"pieces"}),
    # 교과 좌표평면 일차함수 (물결 2C, RPM 2-1 일차함수) — 위 절 참조.
    "linearGraph": frozenset({"lines", "xRange", "yRange"}),
    # 쌍곡선·포물선 (물결 4A, RPM 1-1 정비례와 반비례 · 3-1 이차함수) — 위 절 참조.
    "curveGraph": frozenset({"curves", "xRange", "yRange"}),
    # 원뿔 전개도 (물결 4A, RPM 1-2 회전체의 전개도 · 겉넓이와 부피) — 위 절 참조.
    "netCone": frozenset({"r", "l"}),
    # 중1 통계 (물결 3A, RPM 1-2 도수분포표와 상대도수) — 위 절 참조.
    "histogram": frozenset({"classes", "values"}),
    "freqPolygon": frozenset({"classes", "values"}),
    # 중3 통계 (물결 6E, RPM 3-2 산포도·상자그림과 산점도) — 위 절 참조.
    "boxPlot": frozenset({"values", "axisMin", "axisMax", "axisStep"}),
    "scatterPlot": frozenset({"points", "xMin", "xMax", "xStep", "yMin", "yMax", "yStep"}),
}
ADV_OPTIONAL: dict[str, frozenset[str]] = {
    "fracBars": frozenset({"fill"}),
    # `yStep` — 「눈금 한 칸은 몇」 발문이 말하는 걸음. 있으면 **그대로 긋는다** (D-70).
    # `orient` — "vertical"(기본) / "horizontal". 값 축을 어느 화면 축에 눕히는가만 바꾼다.
    "barChart": frozenset({"yMax", "yStep", "yLabel", "xLabel", "orient", "title"}),
    "lineChart": frozenset({"yMax", "yStep", "yLabel", "title"}),
    "stripChart": frozenset(),
    "pieChart": frozenset(),
    "rotateFlip": frozenset({"n"}),
    "symmetry": frozenset({"n", "cells", "motif"}),
    "stackCubes": frozenset({"views"}),
    "netCylinder": frozenset({"pi", "layout"}),
    "areaPoly": frozenset({"top", "d2"}),
    "cylinder": frozenset(),
    "prism": frozenset({"net"}),
    "revolvePlan": frozenset({"gap"}),
    "linearGraph": frozenset({"marks", "grid"}),
    # `lines` — 곡선과 겹쳐 그리는 직선(정비례·교점 유형). `linearGraph` 와 같은 문법이다.
    # `marks`·`grid` 도 같다 — 좌표평면 규칙은 **한 벌**이다.
    "curveGraph": frozenset({"lines", "marks", "grid"}),
    # `labels` — 무엇을 적을지. "slant"·"angle"·"radius" 의 부분집합이고 값은 **엔진이 쓴다**
    # (스펙이 글자를 실어 나르면 그림이 r·l 과 다른 말을 할 수 있다). 기본은 슬랜트+중심각.
    "netCone": frozenset({"labels"}),
    # `total` — 도수의 총합. 합과 다르면 **던진다**(그림이 곧 검산).
    # `hidden` — 찢어져 안 보이는 계급 번호. 쓰면 `total` 이 **있어야 한다**.
    # `series2`·`label` — 두 집단 비교. 둘 다 이름이 있어야 한다.
    "histogram": frozenset(
        {"yMax", "yStep", "yLabel", "xLabel", "title", "total", "hidden", "series2", "label"}
    ),
    # `bars` — 히스토그램을 깔고 그 위에 겹쳐 그린다(넓이가 같다는 것을 보이는 그림).
    "freqPolygon": frozenset(
        {"yMax", "yStep", "yLabel", "xLabel", "title", "total", "bars", "series2", "label"}
    ),
    # `series2`·`label` — 상자그림 두 개를 겹쳐 그려 두 자료를 비교한다(유형05).
    # 둘 다 이름이 있어야 한다(histogram 의 같은 규칙과 무늬가 같다).
    "boxPlot": frozenset({"series2", "label", "xLabel"}),
    "scatterPlot": frozenset({"xLabel", "yLabel", "title"}),
}
ADV_RENDER = {
    "fracBars": _frac_bars,
    "groupDots": _group_dots,
    "barChart": _bar_chart,
    "chartPair": _chart_pair,
    "lineChart": _line_chart,
    "pictograph": _pictograph,
    "stripChart": _strip_chart,
    "pieChart": _pie_chart,
    "protractor": _protractor,
    "rotateFlip": _rotate_flip,
    "symmetry": _symmetry,
    "stackCubes": _stack_cubes,
    "cuboid": _cuboid,
    "prism": _prism,
    "pyramid": _pyramid,
    "cylinder": _cylinder,
    "cone": _cone,
    "sphere": _sphere,
    "netCuboid": _net_cuboid,
    "netCylinder": _net_cylinder,
    "areaPoly": _area_poly,
    "hollowSolid": _hollow_solid,
    "cutCuboid": _cut_cuboid,
    "revolvePlan": _revolve_plan,
    "linearGraph": _linear_graph,
    "curveGraph": _curve_graph,
    "netCone": _net_cone,
    "histogram": _histogram,
    "freqPolygon": _freq_polygon,
    "boxPlot": _box_plot,
    "scatterPlot": _scatter_plot,
}
