# -*- coding: utf-8 -*-
"""스캔 시험지 페이지에서 **그림 영역**을 결정적으로 검출하고 크롭한다(외부 API 0원).

배경 — 왜 픽셀 분석인가
    `N:\개인\기출` 시험지 282편을 조사한 결과 **사실상 전부 스캔본**(텍스트 레이어
    없음·벡터 드로잉 없음, born-digital 2편뿐)이다. 따라서 PyMuPDF 로 벡터/이미지
    객체를 뽑는 네이티브 경로는 쓸 수 없고, 픽셀만 보고 판단해야 한다.

무엇을 그림으로 보는가 (사용자 2026-08-09)
    **HWP 로 그대로 렌더 가능한 것은 그림이 아니다** — 표·보기박스·조건박스·안내문
    ·제목은 전부 기각하고, 삼각형·원·그래프·입체 같은 **도형만** 남긴다.

파이프라인
    1) 이진화(Otsu, 클램프) → 스캔 가장자리 잡티 제거 → 페이지 테두리 제거
    2) 연결요소(run-length + union-find CCL, scipy 없이 numpy 만)
    3) 글자 높이 H(중앙값)를 기준자로 삼아 **해상도 독립** 임계값 사용
    4) 텍스트 줄 그룹화(비슷한 높이가 가로로 이어짐) → 줄에 속한 요소는 씨앗 제외
    5) 씨앗(큰 비축정렬 요소) 을 **잉크 거리**로 묶고, 주변 라벨만 흡수
    6) 표(격자)·프레임+글자·직선뿐·거대 제목 글자 등은 기각
    7) 선택지 마커(①②③) 행·본문 줄은 흡수 금지 → 발문/선택지 침범 방지

검증 (2026-08-09, 오성중·조암중·월서중·학산중 중3 4편 53개 그림)
    51/53 정확(연속 30개 무결). 남은 2건은 그림 바로 아래 **가로 선택지 행**이
    잉크 사슬로 딸려오는 케이스.
"""

from __future__ import annotations

import os

import numpy as np
from PIL import Image

DET_WIDTH = 1800           # 검출 해상도(가로 px) 정규화
SEED_MIN = 2.2             # 씨앗 최소 변 길이(H 배수)
LABEL_GAP = 1.1            # 라벨 흡수 거리(H 배수)
TEXTLINE_MIN_N = 3         # 텍스트 줄 최소 요소 수
TEXTLINE_MIN_W = 5.0       # 텍스트 줄 최소 폭(H 배수)
TEXT_COVER_REJ = 0.42      # 클러스터의 텍스트 줄 커버리지가 이 이상이면 기각
FRAME_COV = 0.45           # 프레임 변 판정 커버리지(둥근 모서리 뱃지 포함)
GLYPH_MAX = 2.2            # 글자 요소 최대 변(H 배수)
RULE_THIN = 0.35           # 축정렬 선 최대 두께(H 배수)
PAD_DET = 3                # 최종 bbox 여유(검출 해상도 px) — 라벨 끝 잘림 방지


def _to_gray(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("L"), dtype=np.uint8)


def _otsu(gray: np.ndarray) -> int:
    hist = np.bincount(gray.ravel(), minlength=256).astype(np.float64)
    total = hist.sum()
    omega = np.cumsum(hist) / total
    mu = np.cumsum(hist * np.arange(256)) / total
    mu_t = mu[-1]
    denom = omega * (1.0 - omega)
    denom[denom == 0] = 1e-12
    return int(np.argmax((mu_t * omega - mu) ** 2 / denom))


def _binarize(gray: np.ndarray, boost: int = 0) -> np.ndarray:
    """`boost` = 연한 획 복구용 임계값 상향(0 이면 종전과 동일).

    ⭐ 왜 필요한가(2026-08-09 학산중 #11·#20 실측): Otsu 는 **검은 본문 글자**가
    지배해 임계값이 낮게 잡힌다(그 페이지 otsu=158). 연필 아닌 **인쇄 회색 곡선**
    (포물선·음영 도형)은 그보다 밝아 이진화에서 통째로 사라진다 — 성분 목록에
    곡선이 아예 없어 '그림 없음'으로 판정됐다. t=190~205 에서야 곡선이 살아난다.
    """
    t = min(max(_otsu(gray), 90), 205)
    if boost:
        t = min(t + boost, 208)
    return gray < t


# ── 연결요소 ────────────────────────────────────────────────────────────
def _ccl(bw: np.ndarray, want_labels: bool = False):
    h, w = bw.shape
    parent: list[int] = []

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    rows: list[list[tuple[int, int, int]]] = []
    prev: list[tuple[int, int, int]] = []
    for y in range(h):
        row = bw[y]
        if not row.any():
            rows.append([])
            prev = []
            continue
        d = np.diff(row.astype(np.int8))
        starts = np.flatnonzero(d == 1) + 1
        ends = np.flatnonzero(d == -1) + 1
        if row[0]:
            starts = np.concatenate(([0], starts))
        if row[-1]:
            ends = np.concatenate((ends, [w]))
        cur = []
        for s, e in zip(starts, ends):
            rid = len(parent)
            parent.append(rid)
            cur.append((int(s), int(e), rid))
        i = j = 0
        while i < len(prev) and j < len(cur):
            ps, pe, pid = prev[i]
            cs, ce, cid = cur[j]
            if pe >= cs and ce >= ps:
                union(pid, cid)
            if pe < ce:
                i += 1
            else:
                j += 1
        rows.append(cur)
        prev = cur

    acc: dict[int, list[int]] = {}
    for y, cur in enumerate(rows):
        for s, e, rid in cur:
            r = find(rid)
            v = acc.get(r)
            if v is None:
                acc[r] = [s, y, e, y + 1, e - s]
            else:
                v[0] = min(v[0], s); v[2] = max(v[2], e)
                v[3] = y + 1; v[4] += e - s
    roots = list(acc.keys())
    out = [{"x0": acc[r][0], "y0": acc[r][1], "x1": acc[r][2], "y1": acc[r][3],
            "area": acc[r][4], "root": r} for r in roots]
    if not want_labels:
        return out
    rank = {r: i + 1 for i, r in enumerate(roots)}
    lab = np.zeros((h, w), dtype=np.int32)
    for y, cur in enumerate(rows):
        for s, e, rid in cur:
            lab[y, s:e] = rank[find(rid)]
    for i, r in enumerate(roots):
        out[i]["lab"] = i + 1
    return out, lab


def _median_text_height(comps: list[dict]) -> float:
    hs = [c["y1"] - c["y0"] for c in comps
          if 4 <= (c["y1"] - c["y0"]) <= 70 and (c["x1"] - c["x0"]) <= 70]
    return float(np.median(hs)) if hs else 18.0


def _dilate_v(bw: np.ndarray, k: int) -> np.ndarray:
    if k <= 0:
        return bw
    out = bw.copy()
    for s in range(1, k + 1):
        out[:-s] |= bw[s:]
        out[s:] |= bw[:-s]
    return out


def _dilate_h(bw: np.ndarray, k: int) -> np.ndarray:
    if k <= 0:
        return bw
    out = bw.copy()
    for s in range(1, k + 1):
        out[:, :-s] |= bw[:, s:]
        out[:, s:] |= bw[:, :-s]
    return out


def frame_sides(bw: np.ndarray, box) -> tuple[float, float, float, float]:
    """영역 4변의 '긴 직선' 커버리지(0~1). 스캔 기울기 보정 위해 팽창 후 측정."""
    x0, y0, x1, y1 = box
    sub = bw[y0:y1, x0:x1]
    h, w = sub.shape
    if h < 6 or w < 6:
        return (0.0, 0.0, 0.0, 0.0)
    sv = _dilate_v(sub, max(1, int(w * 0.012)))
    sh = _dilate_h(sub, max(1, int(h * 0.012)))
    bh = max(2, int(h * 0.14))
    bwd = max(2, int(w * 0.14))
    return (float(sv[:bh].mean(1).max()), float(sv[-bh:].mean(1).max()),
            float(sh[:, :bwd].mean(0).max()), float(sh[:, -bwd:].mean(0).max()))


def _erode_h(bw: np.ndarray, k: int) -> np.ndarray:
    out = bw.copy()
    for s in range(1, k):
        out[:, :-s] &= bw[:, s:]
        out[:, -s:] = False
    return out


def _erode_v(bw: np.ndarray, k: int) -> np.ndarray:
    out = bw.copy()
    for s in range(1, k):
        out[:-s] &= bw[s:]
        out[-s:] = False
    return out


def axis_fraction(bw: np.ndarray, box, H: float) -> float:
    """영역 잉크 중 **긴 축정렬 직선**(가로·세로)이 차지하는 비율.

    표·보기박스·안내문 테두리 조각은 100% 축정렬이고, 진짜 그림(삼각형·원·그래프)은
    대각선·곡선을 반드시 포함한다 → 강한 판별자.
    """
    x0, y0, x1, y1 = box
    sub = bw[y0:y1, x0:x1]
    tot = int(sub.sum())
    if tot <= 0:
        return 0.0
    k = max(4, int(H * 2.5))
    axis = _dilate_h(_erode_h(sub, k), k - 1) | _dilate_v(_erode_v(sub, k), k - 1)
    return float((axis & sub).sum()) / tot


def grid_lines(bw: np.ndarray, box, thr: float = 0.75) -> tuple[int, int]:
    """영역을 가로지르는 **긴 직선의 개수**(가로, 세로). 표(격자) 판별용.

    표는 행·열 괘선이 각각 3개 이상이고, 도형은 기껏해야 테두리 2+2 다.
    """
    x0, y0, x1, y1 = box
    sub = bw[y0:y1, x0:x1]
    h, w = sub.shape
    if h < 8 or w < 8:
        return (0, 0)
    sv = _dilate_v(sub, max(1, int(w * 0.012)))
    sh = _dilate_h(sub, max(1, int(h * 0.012)))

    def _bands(mask_1d) -> int:
        n, run = 0, False
        for v in mask_1d:
            if v and not run:
                n += 1
                run = True
            elif not v:
                run = False
        return n

    return (_bands(sv.mean(1) >= thr), _bands(sh.mean(0) >= thr))


def _has_hole(bw: np.ndarray, c: dict, lab: np.ndarray) -> bool:
    """요소 안에 '둘러싸인 배경'(구멍)이 있는가 — 동그라미 숫자 ①~⑤ 판별용."""
    sub = (lab[c["y0"]:c["y1"], c["x0"]:c["x1"]] == c["lab"])
    h, w = sub.shape
    if h < 5 or w < 5:
        return False
    bg = ~sub
    # 테두리에서 도달 가능한 배경을 지운다(간단 반복 팽창 — 작은 영역이라 저렴)
    reach = np.zeros_like(bg)
    reach[0] = bg[0]; reach[-1] = bg[-1]; reach[:, 0] = bg[:, 0]; reach[:, -1] = bg[:, -1]
    for _ in range(h + w):
        prev = reach.sum()
        reach = _dilate_h(_dilate_v(reach, 1), 1) & bg
        if reach.sum() == prev:
            break
    hole = bg & ~reach
    return bool(hole.sum() >= 0.10 * h * w)


def choice_stacks(comps: list[dict], lab: np.ndarray, H: float,
                  exclude: list[dict] | None = None,
                  margin_of=None, colw_of=None) -> list[dict]:
    """선택지 마커(①②③④⑤) 목록을 찾는다 — 그림이 넘지 못할 경계.

    ⚠️ '동그라미 안 구멍'(_has_hole)만으로는 스캔 품질에 따라 5개 중 1개만 잡힌다
    (오성중 p3 실측). 대신 **구조**로 판정한다: 같은 크기의 정사각형 토큰이 같은 x
    (또는 같은 y)에 **일정 간격**으로 3개 이상 늘어서면 선택지 목록이다.
    """
    cand = [c for c in comps
            if H * 0.8 <= (c["y1"] - c["y0"]) <= H * 1.9
            and 0.7 <= (c["x1"] - c["x0"]) / max(1, c["y1"] - c["y0"]) <= 1.45]

    m = H * 1.2

    def _near_fig(c) -> bool:
        """도형 라벨 O·B·D 도 정사각형이라 선택지로 오인된다(학산중 p2 실측)."""
        cx, cy = (c["x0"] + c["x1"]) * 0.5, (c["y0"] + c["y1"]) * 0.5
        return bool(exclude) and any(
            e["x0"] - m <= cx <= e["x1"] + m and e["y0"] - m <= cy <= e["y1"] + m
            for e in exclude)

    out: list[dict] = []

    def _emit(run, need_margin=True):
        if len(run) < 3:
            return
        # ⭐ 세로 선택지 목록은 **단의 왼쪽 여백**에서 시작한다. 그림 안 라벨
        # (A·B·C·D)도 크기가 고르고 정렬돼 구조만으로는 구분이 안 된다(조암중 p1).
        # 가로 배치(① 4  ② 6  ③ 8)는 첫 마커가 인식 안 될 때가 있어 면제하고
        # _near_fig 다수결로만 거른다.
        rx0 = min(c["x0"] for c in run)
        rx1 = max(c["x1"] for c in run)
        if need_margin:
            if margin_of is not None and rx0 > margin_of(rx0) + H * 3.5:
                return
        else:
            # 가로 선택지 행은 **단 폭 전체**에 퍼진다. 도형 라벨 행(O B D)은
            # 그림 폭까지만 퍼지므로 이 조건으로 갈린다(학산중 p2 / 월서중 p1).
            if colw_of is not None and (rx1 - rx0) < colw_of(rx0) * 0.40:
                return
        # 크기 균일성(마커는 같은 글꼴 같은 크기)
        hs = [c["y1"] - c["y0"] for c in run]
        if max(hs) > min(hs) * 1.35:
            return
        if sum(1 for c in run if _near_fig(c)) >= len(run) * 0.6:
            return
        out.append({"x0": min(g["x0"] for g in run), "x1": max(g["x1"] for g in run),
                    "y0": min(g["y0"] for g in run), "y1": max(g["y1"] for g in run)})

    def _runs(items, key_gap, max_gap, need_margin=True):
        run = [items[0]]
        for c in items[1:]:
            if key_gap(run[-1], c) <= max_gap:
                run.append(c)
            else:
                _emit(run, need_margin)
                run = [c]
        _emit(run, need_margin)

    # ① 세로 목록(같은 x)
    byx: dict[int, list[dict]] = {}
    for c in cand:
        byx.setdefault(int(round(c["x0"] / (H * 0.6))), []).append(c)
    for g in byx.values():
        if len(g) < 3:
            continue
        g.sort(key=lambda c: c["y0"])
        _runs(g, lambda a, b: b["y0"] - a["y1"], H * 4)

    # ② 가로 배치(같은 y): ① 4   ② 6   ③ 8
    byy: dict[int, list[dict]] = {}
    for c in cand:
        byy.setdefault(int(round(c["y0"] / (H * 0.5))), []).append(c)
    for g in byy.values():
        if len(g) < 3:
            continue
        g.sort(key=lambda c: c["x0"])
        _runs(g, lambda a, b: b["x0"] - a["x1"], H * 14, need_margin=False)
    return out


def _interior_stats(bw: np.ndarray, box, H: float) -> tuple[float, float]:
    """(내부 잉크밀도, 내부 잉크 중 글자크기 요소 비율). 프레임 두께만큼 안쪽."""
    x0, y0, x1, y1 = box
    pad = max(3, int(H * 0.9))
    ix0, iy0 = x0 + pad, y0 + pad
    ix1, iy1 = max(ix0 + 1, x1 - pad), max(iy0 + 1, y1 - pad)
    sub = bw[iy0:iy1, ix0:ix1]
    if sub.size == 0:
        return (0.0, 0.0)
    dens = float(sub.mean())
    if not sub.any():
        return (0.0, 0.0)
    comps = _ccl(sub)
    tot = sum(c["area"] for c in comps)
    if tot <= 0:
        return (dens, 0.0)
    gl = sum(c["area"] for c in comps
             if max(c["x1"] - c["x0"], c["y1"] - c["y0"]) <= H * GLYPH_MAX)
    return (dens, gl / tot)


# ── 텍스트 줄 그룹화 ────────────────────────────────────────────────────
def _text_lines(comps: list[dict], H: float) -> list[list[int]]:
    """비슷한 높이 요소가 가로로 이어진 사슬(=텍스트 줄) 인덱스 목록.

    제목처럼 큰 글자도 '서로 비슷한 높이' 라는 성질로 함께 묶인다(해상도·글꼴 무관).
    """
    import bisect
    idx = sorted(range(len(comps)), key=lambda i: comps[i]["x0"])
    xs = [comps[i]["x0"] for i in idx]
    n = len(comps)
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for pos, i in enumerate(idx):
        a = comps[i]
        ah = a["y1"] - a["y0"]
        reach = max(H, ah) * 1.6
        lo = bisect.bisect_left(xs, a["x0"])
        hi = bisect.bisect_right(xs, a["x1"] + reach)
        for j in idx[lo:hi]:
            if j == i:
                continue
            b = comps[j]
            bh = b["y1"] - b["y0"]
            gap = b["x0"] - a["x1"]
            if gap > max(H, min(ah, bh)) * 1.6:
                continue
            # 세로 겹침 ≥ 작은쪽 높이의 45%
            ov = min(a["y1"], b["y1"]) - max(a["y0"], b["y0"])
            if ov < min(ah, bh) * 0.45:
                continue
            # 높이 유사
            if not (0.55 <= ah / max(bh, 1) <= 1.8):
                continue
            union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    out = []
    for g in groups.values():
        if len(g) < TEXTLINE_MIN_N:
            continue
        x0 = min(comps[i]["x0"] for i in g)
        x1 = max(comps[i]["x1"] for i in g)
        if (x1 - x0) < H * TEXTLINE_MIN_W:
            continue
        out.append(g)
    return out


# ── 메인 ────────────────────────────────────────────────────────────────
SOFT_BOOST = 45            # 연한 획 복구 패스의 임계값 상향(회색 인쇄 곡선)


def detect(img: Image.Image, debug: bool = False, h_override: float | None = None,
           faint: bool = True):
    """엄격 패스 + **연한 획 복구 패스**를 합쳐 최종 그림 상자를 낸다.

    두 패스 모두 같은 기각 규칙(표·글자덩어리·본문)을 통과해야 하므로 오검출은
    늘지 않고, 회색 곡선만 추가로 살아난다. 겹치는 상자는 **큰 쪽만** 남긴다
    (연한 패스가 찾은 포물선 전체가 엄격 패스의 축 조각을 흡수).
    """
    if not faint:
        return _detect_once(img, debug, h_override, 0)
    strict = _detect_once(img, False, h_override, 0)
    soft = _detect_once(img, False, h_override, SOFT_BOOST)
    # 연한 패스에만 있는 상자는 **스캔 얼룩일 수 있다** → 선화 판정 통과분만 채택
    soft = [b for b in soft
            if _overlaps_any(b, strict) or not _is_smudge(img, b)]
    out = _merge_boxes(strict, soft, img.size[0])
    if debug:
        _, dbg = _detect_once(img, True, h_override, 0)
        dbg["strict"] = strict
        dbg["soft"] = soft
        return out, dbg
    return out


SMUDGE_ERODE = 0.40        # 1px 침식 후 잉크 생존율이 이 이상이면 선화가 아니다


def _overlaps_any(box, others, thr: float = 0.3) -> bool:
    for o in others:
        ix = max(0, min(box[2], o[2]) - max(box[0], o[0]))
        iy = max(0, min(box[3], o[3]) - max(box[1], o[1]))
        if ix * iy / max(1, (box[2] - box[0]) * (box[3] - box[1])) >= thr:
            return True
    return False


def _is_smudge(img: Image.Image, box) -> bool:
    """스캔 얼룩(덩어리) vs 그림(선화) 판별 — **1px 침식 생존율**.

    실측(2026-08-09 월서중 오검출 2건 대 학산중 그림 4건): 얼룩은 속이 꽉 찬
    덩어리라 침식해도 47~59% 가 남고, 인쇄 선화는 획이 얇아 6~24% 만 남는다.
    농도(어둡기) 분포는 둘이 거의 같아 판별에 못 쓴다 — 형태로 갈라야 한다.
    """
    g = np.asarray(img.convert("L"), dtype=np.uint8)[box[1]:box[3], box[0]:box[2]]
    if g.size == 0:
        return True
    m = _binarize(g, SOFT_BOOST)
    n = int(m.sum())
    if n == 0:
        return True
    inv = ~m
    er = ~_dilate_h(_dilate_v(inv, 1), 1)
    return int(er.sum()) / n >= SMUDGE_ERODE


def _merge_boxes(a: list, b: list, page_w: int) -> list:
    """두 패스 결과 합치기 — 80% 이상 겹치면 **큰 상자만** 남긴다.

    정렬은 **읽기 순서**(왼단 위→아래, 오른단)를 유지해야 한다. OCR figure 블록과
    1:1 로 맞물리는 순서라, 여기서 흐트러지면 그림이 엉뚱한 문항에 들어간다.
    """
    all_b = list(a) + [x for x in b if x not in a]
    drop = set()
    for i, p in enumerate(all_b):
        for j, q in enumerate(all_b):
            if i == j or i in drop or j in drop:
                continue
            ix = max(0, min(p[2], q[2]) - max(p[0], q[0]))
            iy = max(0, min(p[3], q[3]) - max(p[1], q[1]))
            ap = max(1, (p[2] - p[0]) * (p[3] - p[1]))
            aq = max(1, (q[2] - q[0]) * (q[3] - q[1]))
            if ix * iy / min(ap, aq) >= 0.8:
                drop.add(j if aq <= ap else i)
    keep = [x for k, x in enumerate(all_b) if k not in drop]
    mid = page_w * 0.5
    keep.sort(key=lambda b_: (0 if (b_[0] + b_[2]) * 0.5 < mid else 1, b_[1], b_[0]))
    return keep


def _detect_once(img: Image.Image, debug: bool = False,
                 h_override: float | None = None, boost: int = 0):
    W0, H0 = img.size
    scale = DET_WIDTH / float(W0)
    if scale < 1.0:
        det = img.resize((DET_WIDTH, max(1, int(H0 * scale))), Image.LANCZOS)
    else:
        det, scale = img, 1.0
    gray = _to_gray(det)
    bw = _binarize(gray, boost)
    h, w = bw.shape

    comps, lab = _ccl(bw, want_labels=True)
    # 작은 창(힌트 영역)에서는 글자가 거의 없어 H 중앙값이 무의미하다 → 페이지 H 주입
    H = float(h_override) * scale if h_override else _median_text_height(comps)
    comps = [c for c in comps if c["area"] >= max(3, (H * 0.12) ** 2)]

    edge = max(3, int(H * 0.4))

    def is_edge_junk(c):
        # ⚠️ '가장자리에 닿는다'만으로 판정하면 **전폭 꼬리말 괘선**(x0≈0)까지 지워
        # 본문 영역(body_bot) 검출이 무너진다(조암중 p3 실측) → 요소의 **중심**이
        # 페이지 테두리에 붙어 있을 때만 스캔 잡티로 본다.
        cw, ch = c["x1"] - c["x0"], c["y1"] - c["y0"]
        cx, cy = (c["x0"] + c["x1"]) * 0.5, (c["y0"] + c["y1"]) * 0.5
        hugs = min(cx, w - cx) <= w * 0.02 or min(cy, h - cy) <= h * 0.02
        return hugs and (cw <= H * 1.2 or ch <= H * 1.2) and max(cw, ch) >= H * 2

    comps = [c for c in comps if not is_edge_junk(c)]
    # 페이지 전체를 감싸는 테두리 사각형(조암중) — 있으면 모든 씨앗이 하나로 뭉친다
    comps = [c for c in comps
             if not ((c["x1"] - c["x0"]) >= w * 0.75 and (c["y1"] - c["y0"]) >= h * 0.75)]

    lines = _text_lines(comps, H)
    in_line = set()
    for g in lines:
        in_line.update(g)

    # 텍스트 줄 마스크(커버리지 계산용) + 줄 bbox 목록
    tmask = np.zeros((h, w), dtype=bool)
    line_boxes: list[tuple[int, int, int, int]] = []
    for g in lines:
        x0 = min(comps[i]["x0"] for i in g); x1 = max(comps[i]["x1"] for i in g)
        y0 = min(comps[i]["y0"] for i in g); y1 = max(comps[i]["y1"] for i in g)
        tmask[y0:y1, x0:x1] = True
        line_boxes.append((x0, y0, x1, y1))

    seeds, smalls = [], []
    for i, c in enumerate(comps):
        cw, ch = c["x1"] - c["x0"], c["y1"] - c["y0"]
        elong = max(cw, ch) / max(1, min(cw, ch))
        thin = elong >= 12 and min(cw, ch) <= H * 1.2
        big = cw >= H * SEED_MIN and ch >= H * SEED_MIN
        if big and not thin and i not in in_line:
            seeds.append(c)
        else:
            smalls.append(c)


    # ── 단(column) 경계: 긴 세로 괘선 = 2단 구분선. 클러스터가 단을 넘지 않게 ──
    # ── 본문 영역: 머리말 괘선 아래 ~ 꼬리말 괘선 위 ────────────────────
    # 시험지 머리(제목·코드 뱃지·배점표)와 꼬리(쪽번호)는 문항이 아니다.
    hrules = [c for c in comps if (c["x1"] - c["x0"]) >= w * 0.55
              and (c["y1"] - c["y0"]) <= H * 1.2]
    body_top = max([c["y1"] for c in hrules if c["y1"] <= h * 0.32], default=0)
    body_bot = min([c["y0"] for c in hrules if c["y0"] >= h * 0.88], default=h)

    seps = sorted(c["x0"] for c in comps
                  if (c["y1"] - c["y0"]) >= h * 0.35
                  and (c["x1"] - c["x0"]) <= H * 1.2)
    if not seps:
        # 구분선이 인쇄되지 않은 2단 시험지 — 가운데 **빈 세로 거터**를 찾는다.
        colink = bw[body_top:body_bot].sum(0)
        thr = max(1, int((body_bot - body_top) * 0.004))
        best, run_s = None, None
        for x in range(int(w * 0.33), int(w * 0.67)):
            if colink[x] <= thr:
                if run_s is None:
                    run_s = x
            else:
                if run_s is not None and (best is None or x - run_s > best[1] - best[0]):
                    best = (run_s, x)
                run_s = None
        if run_s is not None and (best is None or int(w * 0.67) - run_s > best[1] - best[0]):
            best = (run_s, int(w * 0.67))
        if best and (best[1] - best[0]) >= max(4, H * 0.4):
            seps = [(best[0] + best[1]) // 2]

    bounds = [0] + [s for s in seps] + [w]

    def col_of(box) -> int:
        cx = (box[0] + box[2]) * 0.5
        for k in range(len(bounds) - 1):
            if bounds[k] <= cx < bounds[k + 1]:
                return k
        return 0

    # ── 씨앗 그룹핑: **실제 잉크 거리** 기준(bbox 근접 금지) ───────────────
    # bbox 근접으로 흡수하면 그래프처럼 큰 그림의 bbox 안에 들어온 선택지·발문까지
    # 삼킨다(오성중 #7 실측). 씨앗 획에서 LABEL_GAP 이내인 것만 라벨로 본다.
    gap_px = max(2, int(H * LABEL_GAP))
    # 단별 본문 왼쪽 여백(텍스트 줄 시작 x 의 최솟값) — 선택지 판정 기준
    def _margin_of(x: float) -> float:
        k = 0
        for i in range(len(bounds) - 1):
            if bounds[i] <= x < bounds[i + 1]:
                k = i
                break
        xs = [b[0] for b in line_boxes if bounds[k] <= b[0] < bounds[k + 1]]
        return min(xs) if xs else bounds[k]

    def _colw_of(x: float) -> float:
        for i in range(len(bounds) - 1):
            if bounds[i] <= x < bounds[i + 1]:
                return float(bounds[i + 1] - bounds[i])
        return float(w)

    # ⭐ 선택지 마커(①②③) 판정은 **항상 엄격 이진화로** — 연한 획 복구 패스
    # (boost>0)에서는 동그라미 안이 메워져 마커 구조(같은 크기·일정 간격)가 깨져
    # 판정이 실패하고, 그 결과 선택지 줄이 그림에 흡수된다(학산중 #12 실측:
    # 크롭 아래 "④ 4  ⑤ 16" 침범). 마커는 검은 인쇄라 엄격 패스에 늘 보인다.
    if boost:
        _cs, _ls = _ccl(_binarize(gray, 0), want_labels=True)
        _cs = [c for c in _cs if c["area"] >= max(3, (H * 0.12) ** 2)]
        stacks = choice_stacks(_cs, _ls, H, exclude=seeds,
                               margin_of=_margin_of, colw_of=_colw_of)
    else:
        stacks = choice_stacks(comps, lab, H, exclude=seeds,
                               margin_of=_margin_of, colw_of=_colw_of)

    groups = _group_by_ink(seeds, lab, bw.shape, gap_px, col_of)

    # ── 흡수 단위: '줄에 안 묶인 낱 요소' + '짧은 줄'(라벨·수식 조각) ──────
    units: list[dict] = []
    for i, c in enumerate(comps):
        if i not in in_line:
            units.append({"x0": c["x0"], "y0": c["y0"], "x1": c["x1"], "y1": c["y1"],
                          "labs": [c["lab"]], "solo": True})
    for g in lines:
        x0 = min(comps[i]["x0"] for i in g); x1 = max(comps[i]["x1"] for i in g)
        y0 = min(comps[i]["y0"] for i in g); y1 = max(comps[i]["y1"] for i in g)
        med = float(np.median([comps[i]["y1"] - comps[i]["y0"] for i in g]))
        # 축 라벨 줄(O   B   D)은 '짧은 토큰 몇 개'가 그림 폭에 흩어진 것 — 본문
        # 줄이 아니므로 치수 라벨 보강 대상으로 허용한다(학산중 p2 실측).
        labelish = (len(g) <= 6
                    and max(comps[i]["x1"] - comps[i]["x0"] for i in g) <= H * 3.5)
        units.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1,
                      "labs": [comps[i]["lab"] for i in g],
                      # 점선 호·파선(작은 점의 사슬)은 '텍스트 줄' 이 아니라 그림 일부다
                      "chain": med < H * 0.5, "labelish": labelish})
    # 라벨 크기 제한 — 단 구분선(세로 1953px)·머리말 괘선(1568px) 흡수 방지(실측).
    # 단, 점선 체인은 그림의 치수 보조선이므로 폭 제한 면제(오성중 #8 '5cm' 실측).
    units = [u for u in units
             if u.get("chain")
             or ((u["x1"] - u["x0"]) <= H * 10 and (u["y1"] - u["y0"]) <= H * 6)]

    # ⭐ 선택지 행(①②③…)에 걸친 것은 **절대 흡수하지 않는다**. 파괴적으로 잘라내면
    # 옆에 나란히 놓인 그림까지 반토막 난다(조암중 #? 실측) → 애초에 안 먹는 쪽이 안전.
    # ⭐ 마커 검출에 의존하지 않는 2차 방어: **씨앗(그림) 잉크를 뺀 뒤** 단 폭의
    # 55% 이상을 가로지르는 행 = 본문 줄 또는 선택지 행. 그림 라벨은 그림 폭까지만
    # 퍼지므로 여기 안 걸린다(월서중 p1 · 학산중 p3 실측).
    nonseed = bw.copy()
    pad_s = int(H * 1.5)
    for c in seeds:            # 그림 영역(점선 호·라벨 포함) 전체를 뺀다
        nonseed[max(0, c["y0"] - pad_s):c["y1"] + pad_s,
                max(0, c["x0"] - pad_s):c["x1"] + pad_s] = False
    wide_bands: list[tuple[int, int, int]] = []      # (col, y0, y1)
    for k in range(len(bounds) - 1):
        cx0, cx1 = bounds[k], bounds[k + 1]
        colw = max(1, cx1 - cx0)
        sub = nonseed[:, cx0:cx1]
        any_row = sub.any(1)
        first = np.argmax(sub, axis=1)
        last = colw - 1 - np.argmax(sub[:, ::-1], axis=1)
        span = np.where(any_row, last - first, -1)
        mark = span >= colw * 0.55
        y = 0
        while y < h:
            if mark[y]:
                y2 = y
                while y2 + 1 < h and (mark[y2 + 1] or
                                      (y2 + 1 - y) < H * 0.4):
                    if not mark[y2 + 1] and not mark[min(h - 1, y2 + 2)]:
                        break
                    y2 += 1
                wide_bands.append((k, y, y2 + 1))
                y = y2 + 1
            else:
                y += 1

    def _in_wide_band(u) -> bool:
        ck = col_of((u["x0"], u["y0"], u["x1"], u["y1"]))
        for k, by0, by1 in wide_bands:
            if k != ck:
                continue
            if u["y1"] > by0 - H * 0.35 and u["y0"] < by1 + H * 0.35:
                return True
        return False

    def _in_choice_row(u) -> bool:
        for st in stacks:
            if col_of((u["x0"], u["y0"], u["x1"], u["y1"])) !=                     col_of((st["x0"], st["y0"], st["x1"], st["y1"])):
                continue
            if u["y1"] > st["y0"] - H * 0.4 and u["y0"] < st["y1"] + H * 0.4:
                return True
        return False

    units = [u for u in units if not _in_choice_row(u)]


    clusters = []
    for g in groups:
        cl = {"x0": g["x0"], "y0": g["y0"], "x1": g["x1"], "y1": g["y1"]}
        gcol = col_of((cl["x0"], cl["y0"], cl["x1"], cl["y1"]))
        M = int(H * 8)                    # 지역 창(전면 팽창은 너무 느림)
        for _ in range(8):
            wx0 = max(0, cl["x0"] - M); wy0 = max(0, cl["y0"] - M)
            wx1 = min(w, cl["x1"] + M); wy1 = min(h, cl["y1"] + M)
            sub_lab = lab[wy0:wy1, wx0:wx1]
            m = np.isin(sub_lab, g["labs"])
            grown = _dilate_h(_dilate_v(m, gap_px), gap_px)
            changed = False
            for u in units:
                if u.get("_used"):
                    continue
                if u["x0"] < wx0 or u["y0"] < wy0 or u["x1"] > wx1 or u["y1"] > wy1:
                    continue
                if col_of((u["x0"], u["y0"], u["x1"], u["y1"])) != gcol:
                    continue
                s = grown[u["y0"] - wy0:u["y1"] - wy0, u["x0"] - wx0:u["x1"] - wx0]
                if s.size == 0 or not s.any():
                    continue
                cl["x0"] = min(cl["x0"], u["x0"]); cl["y0"] = min(cl["y0"], u["y0"])
                cl["x1"] = max(cl["x1"], u["x1"]); cl["y1"] = max(cl["y1"], u["y1"])
                u["_used"] = True
                changed = True
                g["labs"].extend(u["labs"])
            if not changed:
                break

        # ── 발문/본문 줄 침범 제거: 클러스터 가장자리에 걸친 긴 텍스트 줄을 잘라낸다 ──
        for (lx0, ly0, lx1, ly1) in line_boxes:
            if (lx1 - lx0) < H * 10:
                continue
            if lx1 <= cl["x0"] or lx0 >= cl["x1"] or ly1 <= cl["y0"] or ly0 >= cl["y1"]:
                continue
            ch = max(1, cl["y1"] - cl["y0"])
            if ly1 - cl["y0"] <= ch * 0.35:          # 위쪽 가장자리 → 아래로 잘라냄
                cl["y0"] = min(cl["y1"] - 1, ly1 + 1)
            elif cl["y1"] - ly0 <= ch * 0.35:        # 아래쪽 가장자리 → 위로 잘라냄
                cl["y1"] = max(cl["y0"] + 1, ly0 - 1)

        # ── 치수 라벨 보강: 그림 **바로 위/아래에 가운데로** 붙은 짧은 토큰 ──
        # 점선 호(파선)가 끊겨 잉크 사슬이 닿지 않는 '5cm'·'6cm' 류를 살린다.
        # 좌우 여백 12% 를 요구해 단 왼쪽 여백에 붙는 선택지(①②③)는 배제한다.
        # ⚠️ **단 한 번만**, 그리고 기준은 얼어붙인 base — 반복하면 위쪽 발문으로
        # 한 줄씩 걸어 올라간다(오성중 #7·#9 실측: 608→381 로 발문 침범).
        base = dict(cl)
        cw = max(1, base["x1"] - base["x0"])
        cands = []
        for u in units:
            if u.get("_used") or not (u.get("solo") or u.get("labelish")):
                continue
            if col_of((u["x0"], u["y0"], u["x1"], u["y1"])) != gcol:
                continue
            # **아래쪽만** — 위쪽은 발문(줄바꿈된 짧은 꼬리 '는? [4점]')이 걸려든다.
            # 도형에 닿아 있는 아래쪽 라벨(원 밑의 점 D)은 클러스터와 겹치므로
            # '아래로 삐져나오는가' 로 판정한다(겹침 허용, 시작은 1.6H 이내).
            if u["y1"] <= base["y1"]:
                continue
            # 축 라벨 줄(O  B  D)은 그림 폭만큼 퍼진다 → 폭 상한을 클러스터 폭까지 허용
            if u["y0"] - base["y1"] > H * 1.6:
                continue
            if (u["x1"] - u["x0"]) > max(H * 8, cw * 1.05):
                continue
            # 좌우 여백 12% 요구는 '넓은 텍스트 조각'만 — 축 라벨(O·D)은 그림 모서리
            # 바로 아래에 오므로 좁은 토큰은 면제한다(학산중 p2 실측).
            if (u["x1"] - u["x0"]) > H * 3.5:
                if ((u["x0"] - base["x0"]) < cw * 0.12
                        or (base["x1"] - u["x1"]) < cw * 0.12):
                    continue
            elif not (base["x0"] - H <= u["x0"] and u["x1"] <= base["x1"] + H):
                continue      # 좁은 라벨은 그림 x-범위 안(모서리 포함)에 있어야 한다
            cands.append(u)

        # 축 라벨(O · B · C)은 **그림 폭**까지만 퍼진다. 후보들이 **단 폭**의 60%
        # 이상으로 퍼져 있으면 그건 선택지 행이다(월서중 p1 · 학산중 p3 실측).
        if cands:
            sx0 = min(u["x0"] for u in cands); sx1 = max(u["x1"] for u in cands)
            if (sx1 - sx0) < _colw_of(base["x0"]) * 0.6:
                for u in cands:
                    cl["x0"] = min(cl["x0"], u["x0"]); cl["y0"] = min(cl["y0"], u["y0"])
                    cl["x1"] = max(cl["x1"], u["x1"]); cl["y1"] = max(cl["y1"], u["y1"])
                    u["_used"] = True

        # ── 트림 후 정규화: 남은 잉크에 딱 맞추고, 뭉개진 것은 버린다 ──────
        if cl["x1"] - cl["x0"] < H or cl["y1"] - cl["y0"] < H:
            continue
        sub = bw[cl["y0"]:cl["y1"], cl["x0"]:cl["x1"]]
        if not sub.any():
            continue
        ys = np.flatnonzero(sub.any(1)); xs2 = np.flatnonzero(sub.any(0))
        cl = {"x0": cl["x0"] + int(xs2[0]), "y0": cl["y0"] + int(ys[0]),
              "x1": cl["x0"] + int(xs2[-1]) + 1, "y1": cl["y0"] + int(ys[-1]) + 1}
        clusters.append(cl)

    kept, rejected = [], []
    for cl in clusters:
        box = (cl["x0"], cl["y0"], cl["x1"], cl["y1"])
        a = max(1, (box[2] - box[0]) * (box[3] - box[1]))
        cov = float(tmask[box[1]:box[3], box[0]:box[2]].sum()) / a
        t, b, l, r = frame_sides(bw, box)
        framed = min(t, b, l, r) >= FRAME_COV
        dens, gfrac = _interior_stats(bw, box, H)
        axf = axis_fraction(bw, box, H)
        gh, gv = grid_lines(bw, box)
        # 큰 제목 글자(표지 '3학년 수학')는 획이 여러 조각으로 깨져 텍스트 줄
        # 그룹화를 빠져나간다 → **구성 요소의 중앙값 높이**로 잡는다(그림은 라벨이
        # 다수라 중앙값이 글자 크기, 제목은 조각도 거대하다).
        inner = [c for c in comps
                 if c["x0"] >= box[0] and c["x1"] <= box[2]
                 and c["y0"] >= box[1] and c["y1"] <= box[3]]
        # 큰 요소가 '속이 찬'(fill 높은) 획이면 글자, '속이 빈' 윤곽이면 도형.
        fat = 0
        for c in inner:
            cw2, ch2 = c["x1"] - c["x0"], c["y1"] - c["y0"]
            if ch2 >= H * 3 and c["area"] / max(1, cw2 * ch2) >= 0.35:
                fat += 1
        big_glyphs = fat >= 3

        # 아주 큰 요소(도형 윤곽) 존재 여부 — glyph-region 면제 조건
        # ⚠️ fill 상한을 0.5 로 두면 **음영/칠해진 도형**(학산중 #6 직사각형 색칠)이
        # 면제에서 탈락한다 → 0.85 로 완화하고 크기 문턱도 4.5H 로 낮춘다.
        has_big = any((c["x1"] - c["x0"]) >= H * 4.5 and (c["y1"] - c["y0"]) >= H * 4.5
                      and c["area"] / max(1, (c["x1"] - c["x0"]) * (c["y1"] - c["y0"])) < 0.85
                      for c in inner)

        wide = max(H * 12, (box[2] - box[0]) * 0.6)
        n_long = sum(1 for (lx0, ly0, lx1, ly1) in line_boxes
                     if lx0 >= box[0] - 2 and lx1 <= box[2] + 2
                     and ly0 >= box[1] - 2 and ly1 <= box[3] + 2
                     and (lx1 - lx0) >= wide)
        cl["_cov"] = cov; cl["_sides"] = (t, b, l, r)
        cl["_dens"] = dens; cl["_gfrac"] = gfrac; cl["_axis"] = axf; cl["_nlong"] = n_long; cl["_grid"] = (gh, gv)
        # 표·보기박스·뱃지 = 테두리 + 내부가 글자. 빈 테두리(사각형 도형)는 살린다.
        why = None
        cy = (box[1] + box[3]) * 0.5
        crosses = any(box[0] + H * 2 < bx < box[2] - H * 2 for bx in seps)
        if cy < body_top or cy > body_bot:
            why = "header/footer"
        elif crosses:
            why = "cross-column"       # 그림은 한 단 안에 있다(단 넘는 것 = 잡영역)
        elif (gh >= 2 and gv == 0 and gfrac >= 0.45
              and (box[2] - box[0]) >= (box[3] - box[1]) * 3.0):
            why = "ruled-text"         # 위아래 괘선 + 글자 = 자료 나열 띠(렌더 가능)
        elif ((gh >= 3 and gv >= 3) or gh >= 5) and gfrac >= 0.35:
            # ⚠️ **모눈 그래프**(거리-시간 그래프 배경)도 격자다 — 표와의 차이는
            # **셀 안에 글자가 있는가**. 표는 셀마다 값이 들어 있고(gfrac 높음),
            # 모눈은 셀이 비어 있고 라벨이 바깥이다(실측: 도원중 #14·황금중 #16).
            why = "table-grid"         # 행·열 괘선 격자 + 셀 안 글자 = 표
        elif axf >= 0.75 and dens < 0.12:
            # 칠해진 도형(검게 칠한 L자 다각형)은 내부가 긴 수평런이라 axf 가 1 에
            # 가깝지만 명백한 그림이다 → 잉크가 빽빽하면 면제(도원중 #6 실측).
            why = "all-straight"       # 축정렬 직선뿐 = 표·박스 테두리 조각
        elif big_glyphs:
            why = "title-text"         # 거대 제목 글자 덩어리
        elif dens >= 0.28 and not (box[2] - box[0] >= H * 5 and box[3] - box[1] >= H * 5):
            # '선택형' 같은 글자 덩어리는 **작다**. 검게 칠한 다각형처럼 크고 빽빽한
            # 것은 그림이다(도원중 #6: dens 0.63, 양변 5H 초과) → 크기로 면제.
            why = "dense-glyph"        # '선택형' 같은 큰 글자 덩어리(그림은 성김)
        elif cov >= TEXT_COVER_REJ:
            why = "text-cover"
        elif dens < 0.002 and axf >= 0.45:
            why = "empty-frame"        # 잉크 없는 테두리 조각(꺾쇠)
        elif n_long >= 1:
            why = "text-block"         # 긴 텍스트 줄이 2개 이상 = 안내문·표
        elif gfrac >= 0.55 and dens >= 0.005 and not has_big:
            # 라벨·수식이 많은 도형(직사각형+치수, 포물선+식)은 gfrac 이 올라가지만
            # **아주 큰 요소**(도형 윤곽)가 하나라도 있으면 그림이다(학산중 실측).
            why = "glyph-region"       # 잉크 대부분이 글자 = 보기박스·표 조각
        elif framed and dens >= 0.005 and (cov >= 0.13 or gfrac >= 0.5):
            why = "framed-text"
        if why:
            cl["_why"] = why
            rejected.append(cl)
        else:
            kept.append(cl)

    # ⭐ **포개진 검출 제거**(2026-08-09 학산중 #21 실측): 같은 그림에서 큰 상자
    # (451x362)와 그 안에 든 작은 상자(132x84)가 **둘 다** 살아남아, 배정이 작은
    # 쪽을 골라 그림의 일부만 잘렸다. 한 상자가 다른 상자에 대부분(80%+) 들어가면
    # **부모만 남긴다** — 자식은 같은 그림의 조각이다.
    if len(kept) > 1:
        drop = set()
        for i, a in enumerate(kept):
            for j, b in enumerate(kept):
                if i == j or j in drop or i in drop:
                    continue
                ix = max(0, min(a["x1"], b["x1"]) - max(a["x0"], b["x0"]))
                iy = max(0, min(a["y1"], b["y1"]) - max(a["y0"], b["y0"]))
                aa = max(1, (a["x1"] - a["x0"]) * (a["y1"] - a["y0"]))
                bb = max(1, (b["x1"] - b["x0"]) * (b["y1"] - b["y0"]))
                inter = ix * iy
                if inter / min(aa, bb) >= 0.8:      # 작은 쪽이 큰 쪽에 잠김
                    drop.add(j if bb <= aa else i)
        if drop:
            for j in sorted(drop, reverse=True):
                kept[j]["_why"] = "nested"
                rejected.append(kept[j])
            kept = [c for k, c in enumerate(kept) if k not in drop]

    # ⭐ 가장자리 여유(사용자 제안 2026-08-09): 검출 해상도(1800px)에서 원본으로
    # 되돌릴 때의 반올림 + 이진화가 놓친 안티앨리어싱 획 때문에 라벨 끝이 1~2px
    # 잘릴 수 있다. 검출 좌표 기준 PAD_DET px 를 넉넉히 두고 이미지 밖은 클램프.
    inv = 1.0 / scale
    out = []
    for cl in kept:
        x0 = max(0, int((cl["x0"] - PAD_DET) * inv))
        y0 = max(0, int((cl["y0"] - PAD_DET) * inv))
        x1 = min(W0, int(np.ceil((cl["x1"] + PAD_DET) * inv)))
        y1 = min(H0, int(np.ceil((cl["y1"] + PAD_DET) * inv)))
        out.append((x0, y0, x1, y1))
    # ⭐ **읽기 순서**(2단 시험지: 왼단 위→아래, 그 다음 오른단)로 정렬한다.
    # OCR JSON 의 figure 블록 순서(문항 순서)와 1:1 로 맞추기 위해 필수.
    def _order(b):
        cx = (b[0] + b[2]) * 0.5 * scale
        col = 0
        for k in range(len(bounds) - 1):
            if bounds[k] <= cx < bounds[k + 1]:
                col = k
                break
        return (col, b[1], b[0])

    out.sort(key=_order)
    if debug:
        return out, {"H": H, "H_page": H / max(scale, 1e-9), "shape": (w, h), "scale": scale, "bw": bw,
                     "comps": comps, "lines": lines, "seeds": seeds,
                     "clusters": clusters, "kept": kept, "rejected": rejected,
                     "tmask": tmask}
    return out


def _group_by_ink(seeds, lab, shape, gap, col_of):
    """씨앗들을 **잉크 거리** 기준으로 묶는다(bbox 근접이 아니라 실제 획 거리)."""
    if not seeds:
        return []
    h, w = shape
    seed_labs = np.array([c["lab"] for c in seeds], dtype=np.int32)
    m = np.isin(lab, seed_labs)
    d = _dilate_h(_dilate_v(m, gap), gap)
    blobs, blab = _ccl(d, want_labels=True)
    groups = []
    for b in blobs:
        sel = (blab[b["y0"]:b["y1"], b["x0"]:b["x1"]] == b["lab"]) & \
              m[b["y0"]:b["y1"], b["x0"]:b["x1"]]
        if not sel.any():
            continue
        ys, xs = np.nonzero(sel)
        labs = sorted({int(v) for v in
                       lab[b["y0"]:b["y1"], b["x0"]:b["x1"]][sel]})
        groups.append({"x0": b["x0"] + int(xs.min()), "y0": b["y0"] + int(ys.min()),
                       "x1": b["x0"] + int(xs.max()) + 1,
                       "y1": b["y0"] + int(ys.max()) + 1, "labs": labs})
    return groups


def _near(a, b, gap: float) -> bool:
    dx = max(0, max(a["x0"] - b["x1"], b["x0"] - a["x1"]))
    dy = max(0, max(a["y0"] - b["y1"], b["y0"] - a["y1"]))
    return dx <= gap and dy <= gap


def _merge(items: list[dict], gap: float) -> list[dict]:
    out: list[dict] = []
    for c in items:
        box = {"x0": c["x0"], "y0": c["y0"], "x1": c["x1"], "y1": c["y1"]}
        rest = []
        for o in out:
            if _near(o, box, gap):
                box["x0"] = min(box["x0"], o["x0"]); box["y0"] = min(box["y0"], o["y0"])
                box["x1"] = max(box["x1"], o["x1"]); box["y1"] = max(box["y1"], o["y1"])
            else:
                rest.append(o)
        rest.append(box)
        out = rest
    return out


# ── 공개 API ────────────────────────────────────────────────────────────
def crop_figures(img: Image.Image, out_dir, prefix: str = "fig",
                 pad: int = 6, max_width: int = 900) -> list[str]:
    """페이지 이미지에서 그림을 검출해 PNG 로 잘라 저장하고 경로 목록을 돌려준다.

    pad 는 원본 픽셀 기준 추가 여유(검출기 자체도 `PAD_DET` 만큼 여유를 둔다 —
    가장자리 글자가 1~2px 잘리는 것 방지, 사용자 요청 2026-08-09).
    """
    import os

    os.makedirs(out_dir, exist_ok=True)
    paths: list[str] = []
    for i, (x0, y0, x1, y1) in enumerate(detect(img)):
        box = (max(0, x0 - pad), max(0, y0 - pad),
               min(img.width, x1 + pad), min(img.height, y1 + pad))
        crop = img.crop(box)
        if max_width and crop.width > max_width:
            crop = crop.resize((max_width, max(1, int(crop.height * max_width / crop.width))),
                               Image.LANCZOS)
        path = os.path.join(out_dir, f"{prefix}_{i}.png")
        crop.save(path)
        paths.append(path)
    return paths


# ── OCR 힌트 → 실제 잉크 경계 스냅 ──────────────────────────────────────
def _to_px(img: Image.Image, rect) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = rect
    return (max(0, int(x0 * img.width)), max(0, int(y0 * img.height)),
            min(img.width, int(x1 * img.width)), min(img.height, int(y1 * img.height)))


def _overlap_frac(a, b) -> float:
    """a 가 b 와 겹치는 넓이 / a 의 넓이."""
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    aa = max(1, (a[2] - a[0]) * (a[3] - a[1]))
    return ix * iy / aa


def _page_text_height(img: Image.Image) -> float:
    """페이지 전체 글자 높이 중앙값 — **원본 픽셀 단위**로 돌려준다.

    ⚠️ 검출 해상도(1800px) 단위로 돌려주면, 작은 창에 주입할 때 창의 확대배율이
    한 번 더 곱해져 H 가 과대해지고 **검출이 통째로 죽는다**(실측: 문항 27개 중
    9개 미검출). `detect(h_override=)` 는 원본 픽셀 H 를 받아 창 배율을 곱한다.
    """
    scale = DET_WIDTH / float(img.width)
    det = img.resize((DET_WIDTH, max(1, int(img.height * scale))), Image.LANCZOS)         if scale < 1.0 else img
    comps = _ccl(_binarize(_to_gray(det)))
    h_det = _median_text_height(comps)
    return h_det / scale if scale < 1.0 else h_det


def _ink_trim(img: Image.Image, box) -> tuple[int, int, int, int] | None:
    """영역 안 잉크의 bbox 로 줄인다(검출 실패 시 폴백 — 힌트보다는 항상 낫다)."""
    x0, y0, x1, y1 = box
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    sub = np.asarray(img.convert("L").crop((x0, y0, x1, y1)), dtype=np.uint8)
    bw = sub < min(max(_otsu(sub), 90), 205)
    if not bw.any():
        return None
    ys = np.flatnonzero(bw.any(1))
    xs = np.flatnonzero(bw.any(0))
    return (x0 + int(xs[0]), y0 + int(ys[0]), x0 + int(xs[-1]) + 1, y0 + int(ys[-1]) + 1)


def snap_hint(img: Image.Image, hint, page_boxes=None,
              min_overlap: float = 0.25, page_h: float | None = None):
    """OCR 이 준 figure bbox 힌트(페이지 정규화)를 **실제 그림 경계**로 스냅한다.

    OCR bbox 는 LLM 추정이라 타이트/저편향이다(기존 코드도 pad 0.05 로 보정했다).
    여기서는 ① 페이지 전체 검출 결과 중 힌트와 가장 많이 겹치는 것을 쓰고,
    ② 없으면 힌트 영역의 잉크 bbox 로 줄인다.

    반환: (x0, y0, x1, y1) 원본 픽셀, 실패 시 None.
    """
    hx = _to_px(img, hint)
    harea = max(1, (hx[2] - hx[0]) * (hx[3] - hx[1]))
    if page_boxes is None:
        page_boxes = detect(img)

    # ⭐ **창 검출 우선**: 페이지 전체 검출은 그림+주변을 하나로 묶은 거대 영역일 수
    # 있어(도원중 #6 실측: 발문·선택지 포함) 힌트 주변만 다시 보는 쪽이 정확하다.
    w, h = hx[2] - hx[0], hx[3] - hx[1]
    pad_x, pad_y = int(w * 0.12) + 8, int(h * 0.12) + 8
    grown = (max(0, hx[0] - pad_x), max(0, hx[1] - pad_y),
             min(img.width, hx[2] + pad_x), min(img.height, hx[3] + pad_y))
    if page_h is None:
        page_h = _page_text_height(img)
    win = img.crop(grown)
    try:
        wb = detect(win, h_override=page_h)
    except Exception:  # noqa: BLE001
        wb = []
    best2, sc2 = None, 0.0
    for b in wb:
        gb = (grown[0] + b[0], grown[1] + b[1], grown[0] + b[2], grown[1] + b[3])
        if (gb[2] - gb[0]) * (gb[3] - gb[1]) > harea * 2.5:
            continue                       # 힌트보다 지나치게 큰 영역은 병합 사고
        f = max(_overlap_frac(hx, gb), _overlap_frac(gb, hx))
        if f > sc2:
            best2, sc2 = gb, f
    if best2 is not None and sc2 >= 0.15:
        return best2

    # 폴백 ①: 페이지 전체 검출 중 힌트와 충분히 겹치고 크기도 합리적인 것
    best, score = None, 0.0
    for b in page_boxes:
        if (b[2] - b[0]) * (b[3] - b[1]) > harea * 2.5:
            continue
        f = max(_overlap_frac(hx, b), _overlap_frac(b, hx))
        if f > score:
            best, score = b, f
    if best is not None and score >= min_overlap:
        return best
    # 폴백 ②: 힌트 영역 잉크 bbox
    return _ink_trim(img, grown)


def figures_in_region(img: Image.Image, region, page_h: float | None = None,
                      page_boxes=None):
    """**문항 크롭 영역 안에서** 그림을 검출한다(페이지 좌표 bbox 목록, 읽기순).

    OCR 이 준 figure bbox 는 corpus 마다 기준계도 다르고 경계도 거칠다(실측).
    그래서 bbox 는 '어느 그림이냐' 를 고르는 데만 쓰고, **경계는 언제나 검출기가**
    정한다. 문항 크롭으로 범위를 좁히면 발문·선택지가 같은 영역에 있어 선택지
    마커 차단·본문 줄 배제가 그대로 작동해 페이지 전체 검출보다 정확하다.
    """
    x0, y0, x1, y1 = _to_px(img, region)
    if x1 - x0 < 20 or y1 - y0 < 20:
        return []

    # ⭐ **페이지 전체 검출 결과를 문항 크롭으로 걸러내는 쪽이 먼저**다.
    # 문항 크롭만 떼어 검출하면 그림이 선택지·발문과 한 덩어리로 묶여
    # `glyph-region`(잉크 대부분이 글자)으로 기각된다 — 미검출 9건 중 6건이
    # 이 경로였다(실측). 분류에는 페이지 전체 통계(텍스트 줄·선택지 마커·단 경계)가
    # 필요하다.
    if page_boxes is None:
        page_boxes = detect(img)
    inside = [b for b in page_boxes
              if x0 <= (b[0] + b[2]) * 0.5 <= x1 and y0 <= (b[1] + b[3]) * 0.5 <= y1]
    if inside:
        return inside

    # 페이지 검출이 이 문항에서 아무것도 못 찾았을 때만 창 검출로 재시도
    if page_h is None:
        page_h = _page_text_height(img)
    win = img.crop((x0, y0, x1, y1))
    try:
        boxes = detect(win, h_override=page_h)
    except Exception:  # noqa: BLE001
        return []
    return [(x0 + b[0], y0 + b[1], x0 + b[2], y0 + b[3]) for b in boxes]


def assign_figures(img: Image.Image, region, hints, page_h: float | None = None,
                   page_boxes=None):
    """문항 안 그림 검출 결과를 figure 블록(힌트)에 배정한다.

    hints: 블록별 후보 rect 목록(기준계가 불확실하므로 여러 후보 허용).
    반환: hints 와 같은 길이의 bbox(또는 None) 목록.
    """
    boxes = figures_in_region(img, region, page_h, page_boxes)
    out: list[tuple | None] = [None] * len(hints)
    if not boxes:
        return out
    # ⭐ **개수가 맞으면 힌트를 아예 쓰지 않고 읽기순 1:1** — OCR bbox 는 기준계도
    # 경계도 못 믿는다(실측: 힌트 개입이 정확도를 오히려 깎았다). 힌트는 개수가
    # 어긋날 때 tie-break 로만 쓴다.
    if len(boxes) == len(hints):
        return list(boxes)
    used = set()
    # ① 겹침이 큰 순으로 확정(힌트는 '선택'에만 쓴다)
    pairs = []
    for i, cands in enumerate(hints):
        for j, b in enumerate(boxes):
            f = 0.0
            for r in (cands if isinstance(cands[0], (tuple, list)) else [cands]):
                hx = _to_px(img, r)
                f = max(f, _overlap_frac(hx, b), _overlap_frac(b, hx))
            pairs.append((f, i, j))
    for f, i, j in sorted(pairs, reverse=True):
        if f <= 0.05 or out[i] is not None or j in used:
            continue
        out[i] = boxes[j]
        used.add(j)
    # ② 남은 것은 읽기 순서로 채운다(개수가 같으면 순서 매칭이 안전)
    rest = [b for j, b in enumerate(boxes) if j not in used]
    for i in range(len(hints)):
        if out[i] is None and rest:
            out[i] = rest.pop(0)
    return out


def _fallback_from_hint(img: Image.Image, cands):
    """검출기가 못 찾은 블록의 최후 수단 — 힌트 영역 잉크 bbox."""
    best, area = None, 0
    for r in (cands if isinstance(cands[0], (tuple, list)) else [cands]):
        hx = _to_px(img, r)
        w, h = hx[2] - hx[0], hx[3] - hx[1]
        if w < 12 or h < 12:
            continue
        pad_x, pad_y = int(w * 0.08) + 4, int(h * 0.08) + 4
        t = _ink_trim(img, (max(0, hx[0] - pad_x), max(0, hx[1] - pad_y),
                            min(img.width, hx[2] + pad_x), min(img.height, hx[3] + pad_y)))
        if t is None:
            continue
        a = (t[2] - t[0]) * (t[3] - t[1])
        if a > area:
            best, area = t, a
    return best
