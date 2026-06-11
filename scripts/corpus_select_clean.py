#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""연필·색펜 민감 corpus 후보 선별 (corpus_select.py 의 개선판).

기존 `corpus_select.py`(dpi 50, dark<110)는 **연한 연필 손풀이를 못 잡아** 깨끗도 1위가
연필 범벅인 사고(고산중, 2026-06-11)를 냈다. 이 스크립트는:

- **dpi 100** 으로 올려 연필 스트로크를 포착.
- 점수 = 잉크(near-black) + **연필 회색대역(gray band, 저채도 중간톤)×1.5** + **색펜×4**.
  연필·색펜을 무겁게 가중해 *진짜 깨끗한 인쇄본*을 위로 올린다. **낮을수록 깨끗.**
- **학교별 최선(가장 깨끗한) 사본만** 대표로(같은 학교 사본이 수십 개 — 사본별 깨끗도 상이).
- 완료본(3단계 검수 정답지) 보유한 것만. `--exclude` 로 기검수/골든 학교 제외.

⚠️ 자동 점수는 **1차 필터**일 뿐 — 상위 후보는 반드시 montage 비전(`corpus_prep.py montage`)
으로 최종 확인한다(연필 회색대역은 인쇄 음영·표와 혼동될 수 있음).

사용:
  python scripts/corpus_select_clean.py <원본폴더> <완료본폴더> [파일필터] \
      [--exclude 학교1,학교2,...] [--top N]
예:
  python scripts/corpus_select_clean.py \
      "N:/.../원본/중3" "N:/.../pdf/중3" 25-1-기말 \
      --exclude 조암중,중앙중,장산중,새론중,새본리중,고산중 --top 20
"""
from __future__ import annotations

import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _key(fn: str) -> str:
    """[학교][시기] 키 — 출판사·닉·완료/원본 토큰 무시하고 원본↔완료본 매칭."""
    toks = re.findall(r"\[([^\]]+)\]", fn)
    sch = toks[0] if toks else ""
    m = re.search(r"(2\d-\d-(?:중간|기말))", fn)
    return f"{sch}|{m.group(1) if m else ''}"


def _school(fn: str) -> str:
    toks = re.findall(r"\[([^\]]+)\]", fn)
    return toks[0] if toks else ""


def _cleanliness(path: str) -> float | None:
    """본문 페이지 평균 깨끗도(잉크+연필회색대역+색펜). 낮을수록 깨끗. 실패 None."""
    import fitz
    import numpy as np
    try:
        doc = fitz.open(path)
    except Exception:
        return None
    scores = []
    for pno in range(min(8, doc.page_count)):
        pix = doc[pno].get_pixmap(dpi=100)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
        rgb = arr[:, :, :3].astype(np.int16)
        mean = rgb.mean(2)
        sat = rgb.max(2) - rgb.min(2)
        ink = float((mean < 110).mean())                  # near-black 인쇄+진한 연필
        if ink < 0.010:                                   # 백지/표지 제외
            continue
        # 연필 회색대역: 중간톤(120~205) & 저채도(무채색) — 연한 손글씨
        gray = float(((mean >= 120) & (mean <= 205) & (sat < 28)).mean())
        color = float((sat > 45).mean())                  # 색펜(채점/풀이)
        scores.append(ink + gray * 1.5 + color * 4.0)
    doc.close()
    return (sum(scores) / len(scores)) if scores else None


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    orig_dir, done_dir = argv[0], argv[1]
    rest = argv[2:]
    filt = ""
    exclude: set[str] = set()
    top = 20
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--exclude":
            exclude = {s.strip() for s in rest[i + 1].split(",") if s.strip()}
            i += 2
        elif a == "--top":
            top = int(rest[i + 1])
            i += 2
        else:
            filt = a
            i += 1

    done_keys: dict[str, str] = {}
    if done_dir and os.path.isdir(done_dir):
        for f in os.listdir(done_dir):
            if f.lower().endswith(".pdf") and (not filt or filt in f):
                done_keys.setdefault(_key(f), f)
    print(f"완료본(정답지): {len(done_keys)}개 · 제외 학교: {sorted(exclude) or '없음'}")

    # 학교별 최선(min) 사본
    best: dict[str, tuple[float, str, str]] = {}
    for f in os.listdir(orig_dir):
        if not (f.lower().endswith(".pdf") and (not filt or filt in f)):
            continue
        sch = _school(f)
        if sch in exclude:
            continue
        if done_keys and _key(f) not in done_keys:
            continue                                       # 완료본 있는 것만
        sc = _cleanliness(os.path.join(orig_dir, f))
        if sc is None:
            continue
        cur = best.get(sch)
        if cur is None or sc < cur[0]:
            best[sch] = (sc, f, done_keys.get(_key(f), ""))

    rows = sorted(best.values())
    print(f"\n학교별 최선사본 깨끗순위 상위 {top} (낮을수록 깨끗 — montage 비전 최종확인 필수):")
    for sc, orig, done in rows[:top]:
        print(f"  {sc:.3f}  {orig}")
        if done:
            print(f"         ↳ 정답지: {done}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
