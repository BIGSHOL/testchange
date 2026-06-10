#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""자가발전 corpus 후보 자동 선별 (REVIEW_PROTOCOL 0단계 자동화).

시험지 원본 폴더에서 **손풀이가 적은(깨끗한) 사본**을 잉크 밀도 + 색펜 비율로 점수화하고,
**3단계 사람검수 완료본(pdf/ 정답지)이 있는** 것을 우선해 검수 후보를 추린다.

- 깨끗도 점수 = 어두운 픽셀(잉크) 비율 + 색펜(채점/풀이) 비율 ×2.5. **낮을수록 깨끗.**
  (저해상도 dpi 50 — 연한 연필 손풀이는 못 잡으니, 상위 후보는 비전으로 최종 확인 필요.)
- 완료본 매칭 = [학교][시기] 키(출판사·닉·완료/원본 토큰 제거)로 원본↔완료본 연결.

사용:
  python scripts/corpus_select.py <원본폴더> [완료본폴더] [파일필터]
예:
  python scripts/corpus_select.py "N:/…/원본/고1" "N:/…/pdf/공수1" 공수1
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


def _cleanliness(path: str) -> float | None:
    """본문 페이지 평균 깨끗도(잉크+색펜). 낮을수록 깨끗. 실패 None."""
    import fitz
    import numpy as np
    try:
        doc = fitz.open(path)
    except Exception:
        return None
    scores = []
    for pno in range(min(8, doc.page_count)):
        pix = doc[pno].get_pixmap(dpi=50)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
        rgb = arr[:, :, :3].astype(np.int16)
        dark = float((rgb.mean(2) < 110).mean())
        if dark < 0.012:                          # 백지/표지 제외
            continue
        colorful = float(((rgb.max(2) - rgb.min(2)) > 45).mean())
        scores.append(dark + colorful * 2.5)
    doc.close()
    return (sum(scores) / len(scores)) if scores else None


def main(argv: list[str]) -> int:
    if not argv:
        sys.stderr.write(__doc__)
        return 2
    orig_dir = argv[0]
    done_dir = argv[1] if len(argv) > 1 else ""
    filt = argv[2] if len(argv) > 2 else ""

    done_keys = {}
    if done_dir and os.path.isdir(done_dir):
        for f in os.listdir(done_dir):
            if f.lower().endswith(".pdf") and (not filt or filt in f):
                done_keys.setdefault(_key(f), f)
        print(f"완료본(정답지): {len(done_keys)}개")

    rows = []
    for f in os.listdir(orig_dir):
        if not (f.lower().endswith(".pdf") and (not filt or filt in f)):
            continue
        if done_keys and _key(f) not in done_keys:
            continue                              # 완료본 있는 것만(요청 시)
        sc = _cleanliness(os.path.join(orig_dir, f))
        if sc is not None:
            rows.append((sc, f, done_keys.get(_key(f), "")))
    rows.sort()
    print(f"\n깨끗순위 상위 12 (낮을수록 깨끗 — 상위는 비전으로 최종 확인):")
    for sc, orig, done in rows[:12]:
        print(f"  {sc:.3f}  {orig}")
        if done:
            print(f"         ↳ 정답지: {done}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
