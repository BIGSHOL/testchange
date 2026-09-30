# -*- coding: utf-8 -*-
"""26-2 corpus 그림에서 **도형 안쪽으로 휜 치수선**을 찾는다.

치수선 = stroke-dasharray 가 있는 2차 베지에(`M x y Q cx cy x2 y2`) path.
도형 = 실선(line/polygon/polyline/실선 path) 끝점들의 볼록껍질.
판정: 현의 중점에서 제어점 쪽으로 2px 나간 점이 껍질 **안**이면 안쪽 치수선.
사용: python .testkit/_s26_dimscan.py [폴더키워드...]
"""
import re
import runpy
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(r"D:/시험지 한글화")
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

NUM = r"-?\d+(?:\.\d+)?"


def hull(pts):
    pts = sorted(set(pts))
    if len(pts) < 3:
        return pts
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def inside(h, x, y, margin=1.0):
    if len(h) < 3:
        return False
    for i in range(len(h)):
        a, b = h[i], h[(i + 1) % len(h)]
        c = (b[0] - a[0]) * (y - a[1]) - (b[1] - a[1]) * (x - a[0])
        # 반시계 껍질: 모든 변의 왼쪽이 안
        if c < margin * ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5:
            return False
    return True


def solid_points(svg):
    pts = []
    for m in re.finditer(r"<(line|polygon|polyline|path|circle|rect)\b([^>]*)/?>", svg):
        tag, attrs = m.group(1), m.group(2)
        if "stroke-dasharray" in attrs or 'stroke="none"' in attrs:
            continue
        if tag == "line":
            v = [float(re.search(rf'{k}="({NUM})"', attrs).group(1)) for k in ("x1", "y1", "x2", "y2")]
            pts += [(v[0], v[1]), (v[2], v[3])]
        elif tag in ("polygon", "polyline"):
            nums = [float(t) for t in re.findall(NUM, re.search(r'points="([^"]*)"', attrs).group(1))]
            pts += list(zip(nums[0::2], nums[1::2]))
        elif tag == "circle":
            g = lambda k: float(re.search(rf'\b{k}="({NUM})"', attrs).group(1))
            cx, cy, r = g("cx"), g("cy"), g("r")
            if r > 6:          # 점(dot) 제외
                pts += [(cx - r, cy), (cx + r, cy), (cx, cy - r), (cx, cy + r)]
        elif tag == "path":
            d = re.search(r'\bd="([^"]*)"', attrs)
            if d and "fill=\"none\"" in attrs and " A " not in d.group(1):
                nums = [float(t) for t in re.findall(NUM, d.group(1))]
                pts += list(zip(nums[0::2], nums[1::2]))
    return pts


def dim_curves(svg):
    for m in re.finditer(r"<path\b([^>]*)/?>", svg):
        attrs = m.group(1)
        if "stroke-dasharray" not in attrs:
            continue
        d = re.search(r'\bd="([^"]*)"', attrs)
        if not d:
            continue
        q = re.match(rf"\s*M\s*({NUM})[ ,]+({NUM})\s*Q\s*({NUM})[ ,]+({NUM})[ ,]+({NUM})[ ,]+({NUM})", d.group(1))
        if q:
            yield tuple(float(v) for v in q.groups())


def scan(folder: Path):
    fs = folder / "fig_svgs.py"
    with patch("os.makedirs"):
        ns = runpy.run_path(str(fs), run_name="_dimscan")
    S = ns.get("S") or {}
    bad = []
    for key, svg in S.items():
        h = hull(solid_points(svg))
        for x1, y1, cx, cy, x2, y2 in dim_curves(svg):
            # 곡선 **자체의 중점**(t=.5)이 도형 안쪽 깊이 4px 이상이면 안쪽 치수선.
            # (엔진은 라벨 자리에서 호를 두 조각으로 나누므로 조각의 현 기준 판정은 오탐)
            px = 0.25 * x1 + 0.5 * cx + 0.25 * x2
            py = 0.25 * y1 + 0.5 * cy + 0.25 * y2
            if inside(h, px, py, margin=4.0):
                bad.append((key, round(x1), round(y1), round(x2), round(y2)))
    return bad


if __name__ == "__main__":
    keys = sys.argv[1:] or ["26-2"]
    for d in sorted((ROOT / "corpus").iterdir()):
        if d.is_dir() and (d / "fig_svgs.py").exists() and all(k in d.name for k in keys):
            bad = scan(d)
            print(f"{d.name}: 안쪽 치수선 {len(bad)}개")
            for b in bad:
                print("   ", b)
