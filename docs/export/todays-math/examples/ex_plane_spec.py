# -*- coding: utf-8 -*-
"""예시 ② 평면 — 세 변 13·14·15 인 삼각형과 높이 AH=12 (FigureSpec + 덧그림).

평면 도형은 **FigureSpec 부터**(엔진이 점 이름·각 라벨을 충돌 없이 자동 배치). 스펙이
못 하는 것만 `post` 덧그림으로 얹는다 — 여기서는 BH·HC 가 점 H 로 나뉘어 스펙 치수가
안 걸리는 'BC=14' 를 `adim` 으로(⚠️ 스펙 `dimensions` 는 **한 선분**에만 걸린다).

좌표는 조건에서: 밑변 BC 위에 SSS 로 A 를 세우고 H 는 수선의 발. 검산이 라벨과 그림의
모순을 막는다. 실행: python ex_plane_spec.py [출력폴더]
"""
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

from core.figure_exam import FigureSet, adim, ang, dim, foot, frame, seg, sss  # noqa: E402
from core.figure_svg import verify_figure  # noqa: E402

figs = FigureSet()

# 1) 수학 좌표(y 위) → 화면 좌표(y 아래). 축 단위는 x·y 같게(frame 이 등방).
to = frame(20, 200, 12.0)
ax, ay = sss(13, 15, 14)                     # B=(0,0), C=(14,0), AB=13, AC=15
A, B, C = to(ax, ay), to(0, 0), to(14, 0)
H = foot(A, B, C)

# 2) 검산 — 13·14·15·12 가 한 척도로 그려졌는지, H 가 정말 BC 위인지
verify_figure("tri", lengths=[(13, A, B), (15, A, C), (14, B, C), (12, A, H)],
              on_line=[(H, B, C)])


def post(sh):
    """스펙 좌표 → 렌더 좌표는 반드시 sh 로(엔진이 여백 때문에 캔버스를 옮긴다).

    오프셋 16 이면 엔진이 BC 아래에 둔 점 이름 H 를 치수선이 밟아 lint 가 막는다
    ("라벨-선 겹침: 'H'"). 24 로 더 내렸다.
    """
    return adim(sh(B), sh(C), 24, "14")


# 덧그림은 엔진의 캔버스 계산에 안 들어간다 → 아래로 잘린다("잘림: viewBox 밖 잉크").
# 이름이 두 글자인 보이지 않는 점(Zz — 기본 라벨은 대문자 한 글자만)으로 캔버스를 넓힌다.
Zz = (B[0] + (C[0] - B[0]) / 2, B[1] + 30)

figs.spec("tri", {"A": A, "B": B, "C": C, "H": H, "Zz": Zz},
          {"sAB": seg("A", "B"), "sBC": seg("B", "C"), "sCA": seg("C", "A"),
           "sAH": seg("A", "H", dash="4 3")},
          angles={"rH": ang("H", "A", "C", right=True)},
          dims={"dAB": dim("A", "B", "13"), "dAC": dim("A", "C", "15"), "dAH": dim("A", "H", "12")},
          post=post)

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(tempfile.gettempdir(), "ex_plane_spec")
    rep = figs.build(out)
    for k, v in rep.items():
        print(k, v["png"], "issues:", v["issues"])
    print("지면 폭:", figs.widths())
