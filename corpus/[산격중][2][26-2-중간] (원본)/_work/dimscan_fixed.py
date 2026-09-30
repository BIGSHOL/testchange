"""_s26_dimscan 사본 — 호(A) 명령의 반지름·플래그를 좌표로 읽던 오탐을 고친 판정.

원본 스캐너는 `A rx ry rot large sweep x y` 의 숫자를 전부 (x,y) 쌍으로 읽어 (0,0)·(1,y)
같은 가짜 꼭짓점이 볼록껍질에 들어가 바깥 치수선을 '안쪽'으로 오판한다. 여기선 경로를
명령 단위로 파싱해 끝점만 쓰고, 치수선은 M…Q 조각을 **전부** 본다(엔진은 라벨 틈 때문에
한 치수선을 두 조각으로 낸다).
"""
import re
import runpy
import sys
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / ".testkit"))
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
import _s26_dimscan as D  # noqa: E402

TOK = re.compile(r"[MLQACZ]|-?\d+(?:\.\d+)?", re.I)
NARGS = {"M": 2, "L": 2, "Q": 4, "C": 6, "A": 7}


def path_points(d):
    toks = TOK.findall(d)
    pts, i, cmd = [], 0, None
    while i < len(toks):
        t = toks[i]
        if t.isalpha():
            cmd = t.upper()
            i += 1
            if cmd == "Z":
                continue
        n = NARGS[cmd]
        v = [float(x) for x in toks[i:i + n]]
        i += n
        if cmd == "A":
            pts.append((v[5], v[6]))
        else:
            pts += list(zip(v[0::2], v[1::2]))
    return pts


def solid_points(svg):
    pts = []
    for m in re.finditer(r"<(line|path)\b([^>]*)/?>", svg):
        tag, attrs = m.groups()
        if "stroke-dasharray" in attrs:
            continue
        if tag == "line":
            v = [float(re.search(rf'{k}="(-?[\d.]+)"', attrs).group(1)) for k in ("x1", "y1", "x2", "y2")]
            pts += [(v[0], v[1]), (v[2], v[3])]
        else:
            d = re.search(r'\bd="([^"]*)"', attrs)
            if d and 'fill="none"' in attrs:
                pts += path_points(d.group(1))
    return pts


def dim_pieces(svg):
    for m in re.finditer(r"<path\b([^>]*)/?>", svg):
        attrs = m.group(1)
        if "stroke-dasharray" not in attrs:
            continue
        d = re.search(r'\bd="([^"]*)"', attrs).group(1)
        for q in re.finditer(r"M\s*([-\d.]+)[ ,]+([-\d.]+)\s*Q\s*([-\d.]+)[ ,]+([-\d.]+)[ ,]+([-\d.]+)[ ,]+([-\d.]+)", d):
            yield tuple(float(v) for v in q.groups())


with patch("os.makedirs"):
    ns = runpy.run_path(str(HERE / "fig_svgs.py"), run_name="_dimscan")
bad = []
def panel(key, x, y):
    """s3 는 2x2 조합 그림 — 칸마다 따로 껍질을 잡는다(한 껍질이면 전부 '안쪽')."""
    return (x > 300, y > 200) if key == "s3" else 0


for key, svg in ns["S"].items():
    sp = solid_points(svg)
    hulls = {}
    for x, y in sp:
        hulls.setdefault(panel(key, x, y), []).append((x, y))
    hulls = {k: D.hull(v) for k, v in hulls.items()}
    for x1, y1, cx, cy, x2, y2 in dim_pieces(svg):
        h = hulls[panel(key, (x1 + x2) / 2, (y1 + y2) / 2)]
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        vx, vy = cx - mx, cy - my
        n = (vx * vx + vy * vy) ** 0.5 or 1.0
        if D.inside(h, mx + vx / n * 3, my + vy / n * 3):
            bad.append((key, round(x1), round(y1), round(x2), round(y2)))
print("inward:", len(bad))
for b in bad:
    print("  ", b)
