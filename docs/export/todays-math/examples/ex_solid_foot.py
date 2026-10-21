# -*- coding: utf-8 -*-
"""예시 ① 입체 — 직육면체에서 D 의 EG 위 수선의 발 I (제일고 고2 기하 25-2-기말 서술형 4).

`core.figure_exam` 로 다시 쓴 판. 원래 시험지 스크립트(`corpus/[제일고]…/fig_svgs.py` 의 s4)와
**SVG 가 바이트 단위로 같다**(2026-10-21 대조). 흐름: 3D 좌표 → 검산(verify_solid) → 사투영 →
프리미티브 → 빌드(검산 누락 차단 + 픽셀 검수 + PNG).

실행: python ex_solid_foot.py [출력폴더]
엔진 위치: todays-math `scripts/figure/` 에 두면 `engine_path.engine_root()`, 아니면
`FIGURE_ENGINE_PATH`, 둘 다 없으면 시험지 한글화 저장소 루트.
"""
import math
import os
import sys
import tempfile
from pathlib import Path

try:
    from engine_path import engine_root   # todays-math scripts/figure/
    _ENGINE = engine_root()
except Exception:  # noqa: BLE001
    _ENGINE = os.environ.get("FIGURE_ENGINE_PATH") or str(Path(__file__).resolve().parents[4])
sys.path.insert(0, _ENGINE)
sys.stdout.reconfigure(encoding="utf-8")   # Windows 콘솔(cp949)에서 한글 출력

from core.figure_exam import FigureSet, adim, box, box_parts, fit, oblique, pt_label, unit  # noqa: E402
from core.figure_solid import verify_solid  # noqa: E402
from core.figure_svg import line, rangle  # noqa: E402

figs = FigureSet()

# 1) 3D 좌표는 실제 길이(AD=3·DC=4·AE=1). 수선의 발 I 는 계산으로.
b = box(4, 3, 1)
E, G, D, H = b["E"], b["G"], b["D"], b["H"]
t = sum((h - e) * (g - e) for e, g, h in zip(E, G, H)) / sum((g - e) ** 2 for e, g in zip(E, G))
I3 = tuple(e + t * (g - e) for e, g in zip(E, G))
assert math.isclose(t, 9 / 25)                       # EI:IG = 9:16
assert math.isclose(math.dist(D, I3), 13 / 5)        # 정답 13/5 — 그림이 문제와 같은 세계인지

# 2) 공간 검산 — 라벨값·수직이 실제 좌표와 맞는지(안 맞으면 예외)
verify_solid("s4", lengths=[(3, b["A"], b["D"]), (4, b["D"], b["C"]), (1, b["A"], b["E"]), (5, E, G)],
             perpendicular=[((D, I3), (E, G)), ((H, I3), (E, G)), ((D, H), (E, G))])

# 3) 사투영. 원본 그림처럼 높이만 2배(zs=2) — 아랫면 비례는 그대로라 I 의 위치는 정확하다.
org, wh = fit([oblique((0, 0), 40, 0.72, 44, zs=2.0)(v) for v in b.values()], (34, 34, 26, 24))
pr = oblique(org, 40, 0.72, 44, zs=2.0)
q = {k: pr(v) for k, v in b.items()}
I = pr(I3)

# 4) 프리미티브: 음영 면·숨은 모서리·보조선·직각 표시·바깥 치수·점 이름(정자, 선 밖)
parts = box_parts(q)
parts += [line(q["E"], q["G"], w=1.5), line(q["D"], I, w=1.5),
          rangle(I[0], I[1], *unit(I, q["D"]), *unit(I, q["G"]), s=7)]
parts += [adim(q["A"], q["D"], -12, "3"), adim(q["D"], q["C"], -12, "4"), adim(q["A"], q["E"], 12, "1")]
parts += [pt_label(q["A"], "A", -13, -3), pt_label(q["B"], "B", 11, 11), pt_label(q["C"], "C", 11, -10),
          pt_label(q["D"], "D", -3, -13), pt_label(q["E"], "E", -8, 12), pt_label(q["F"], "F", 4, 13),
          pt_label(q["G"], "G", 13, 3), pt_label(q["H"], "H", -10, -9), pt_label(I, "I", 3, 13)]
figs.raw("s4", *wh, *parts)

LINT_EXEMPT = {
    # 원본처럼 옆면 음영 안에 둔 꼭짓점 이름 — lint 는 면 음영도 '선 잉크'로 센다.
    "s4": ("라벨-선 겹침: 'B'",),
}

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(tempfile.gettempdir(), "ex_solid_foot")
    rep = figs.build(out, lint_exempt=LINT_EXEMPT)
    for k, v in rep.items():
        print(k, v["png"], "issues:", v["issues"])
    print("지면 폭:", figs.widths())
