# -*- coding: utf-8 -*-
"""단원 분류표 PDF → 어휘 사전(JSON) 생성 — 개발용 1회 실행 도구.

세션(Claude Code)이 정답·해설 메타를 채울 때 참조하던 **분류표 어휘**를 배포 exe 도
쓸 수 있게 데이터로 굽는다(사용자 2026-08-07: "그 로컬 파일을 배포 빌드/exe 에도
기억시켜놓고 완벽하게 똑같은 동작이 되도록").

레벨 규약(CLAUDE.md 2026-07-24, 사용자 2026-10-26 재확인 "실제 표에 따라서"):
  · **고등 = 소단원**(분류표 ``ⅰ)`` 레벨 — 표가 ``1. → ① → ⅰ)`` 세 단계) — 폼 라벨 ``[소단원]``
  · **중등 = 중단원**(분류표 ``①`` 레벨 — 표가 ``1. → ①`` 두 단계)       — 폼 라벨 ``[중단원]``

현행 표 = 대수회 ``큰분류ver.261020``(2026-10-20): 고등 22개정 7과목(공통수학1·2·대수·
미적분1·확률과 통계·미적분2·기하), 중등 중1·중2 22개정 + 중3 15개정. 이전 표(고등
ver.250604 의 15개정 과목·중등 중단원 분류)는 ``*_15개정`` 키로 남긴다 — 22개정 이전
시험(2025년 중2, 2026년 고3 등)을 변환할 때 ``core.topic_vocab`` 이 연도로 고른다.

⚠️ 표는 2단 배치·칸 안 줄바꿈이라 **줄 단위 정규식으로 뽑으면 항목이 붙거나 잘린다**
(종전 산출물에 ``‘모든’이나 ‘어떤’을 포함한`` 처럼 잘린 항목 9개). 낱말 좌표로 칸을
나눠 뽑고, 수식이 그림 글자(사용자 영역 문자)로 들어간 3곳은 ``_MATH_FIX`` 로 되살린다.

사용::

    python scripts/build_topic_vocab.py            # 기본 경로(D:/기출/기출작업/…)에서 굽기
    python scripts/build_topic_vocab.py --high <고등.pdf> --mid <중등.pdf> \\
        --legacy-high <옛 고등.pdf> --legacy-mid <옛 중등.pdf>

산출: ``data/topic_vocab.json``  (build.spec 이 exe 에 번들)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# 로컬 미러 기본 경로(N: 끊김 대비 — 메모리 local-mirror-gichul-pdfs)
_BASE = Path("D:/기출/기출작업")
DEFAULT_HIGH = _BASE / "고등수학전체 소단원 분류(큰분류ver.261020).pdf"
DEFAULT_MID = _BASE / "중등수학전체 소단원 분류(큰분류ver.261020).pdf"
DEFAULT_LEGACY_HIGH = _BASE / "이전차수/189차/고등수학전체 소단원 분류(ver.250604).pdf"
DEFAULT_LEGACY_MID = _BASE / "중등수학전체 중단원 분류.pdf"

# 옛 고등 표에서 가져오는 15개정 과목(공통수학1·2 는 이미 22개정이라 현행 표가 대신한다)
LEGACY_HIGH_SUBJECTS = ("수학1", "수학2", "확률과 통계", "미적분", "기하")

_MARK_MID = re.compile(r"^([①-⑳])(.*)$")
_MARK_HIGH = re.compile(r"^([ⅰ-ⅹ]\))(.*)$")
_ANY_MARK = re.compile(r"^(?:[①-⑳]|[ⅰ-ⅹ]\)|\d+\.)")
_PUA = re.compile(r"[\ue000-\uf8ff]")
# 수식이 그림 글자로 들어가 텍스트로는 비는 자리(사용자 영역 문자 제거 후 기준)
_MATH_FIX = {
    "방정식 의 허근": "방정식 x³=1의 허근",
    "의 뜻과 그 성질": "∑의 뜻과 그 성질",
    "무리수 와 자연로그": "무리수 e와 자연로그",
}
# 분류표 원문의 오타
_TYPO_FIX = {
    "거듭제곰과 거듭제곱근": "거듭제곱과 거듭제곱근",
    "일차할수와 일차방정식의 관계": "일차함수와 일차방정식의 관계",
}


def _words(page) -> list[dict]:
    """낱말 목록 — 표지가 글자에 붙은 낱말(``ⅱ)속도와``)은 표지·글자로 나눈다."""
    out = []
    for x0, y0, x1, y1, t, *_ in page.get_text("words"):
        m = _MARK_HIGH.match(t) or _MARK_MID.match(t)
        if m and m.group(2):
            k = len(m.group(1)) / len(t)
            xm = x0 + (x1 - x0) * k
            out.append(dict(x0=x0, y0=y0, x1=xm, y1=y1, t=m.group(1)))
            out.append(dict(x0=xm, y0=y0, x1=x1, y1=y1, t=m.group(2)))
        else:
            out.append(dict(x0=x0, y0=y0, x1=x1, y1=y1, t=t))
    for w in out:
        w["ym"] = (w["y0"] + w["y1"]) / 2
    return out


def _clean(name: str) -> str:
    s = _PUA.sub("", name)
    s = re.sub(r"\s+", " ", s).strip().strip(" ,·")
    s = _MATH_FIX.get(s, s)
    return _TYPO_FIX.get(s, s)


def extract(pdf: Path, level: str) -> dict[str, list[str]]:
    """분류표 PDF → {과목(학년): [항목, …]}. level = ``mid``(①) | ``high``(ⅰ))."""
    import fitz

    target = re.compile(r"^[①-⑳]$") if level == "mid" else re.compile(r"^[ⅰ-ⅹ]\)$")
    found: dict[str, list[tuple]] = {}
    with fitz.open(str(pdf)) as doc:
        for pno, page in enumerate(doc):
            words = _words(page)
            heads = []                                   # ● 과목 머리
            for w in words:
                if w["t"] == "●":
                    line = sorted((v for v in words if abs(v["ym"] - w["ym"]) < 4 and v["x0"] > w["x0"]),
                                  key=lambda v: v["x0"])
                    name = re.sub(r"\s*\([^)]*\)\s*$", "", " ".join(v["t"] for v in line)).strip()
                    heads.append((w["ym"], name))
            marks = [w for w in words if _ANY_MARK.match(w["t"])]
            for m in (w for w in words if target.match(w["t"])):
                hs = [h for h in heads if h[0] < m["ym"]]
                if not hs:
                    continue
                subj = hs[-1][1]
                # 같은 줄 오른쪽: 다음 표지(어느 단계든) 또는 큰 간격(옆 칸) 전까지
                nxt = min([k["x0"] for k in marks if abs(k["ym"] - m["ym"]) < 4 and k["x0"] > m["x0"] + 1]
                          or [1e9])
                toks, prev = [], m["x1"]
                for w in sorted((w for w in words if abs(w["ym"] - m["ym"]) < 4 and m["x1"] - 1 < w["x0"] < nxt),
                                key=lambda w: w["x0"]):
                    if w["x0"] - prev > 25:
                        break
                    toks.append(w["t"])
                    prev = w["x1"]
                # 칸 안 줄바꿈: 바로 아래 줄(5~16pt)이 칸 왼쪽에서 시작하고 표지가 없으면 이어 붙인다
                below = [w for w in words if 5 < w["ym"] - m["ym"] < 16 and m["x0"] - 4 < w["x0"] < m["x0"] + 60]
                if below and not any(_ANY_MARK.match(w["t"]) for w in below):
                    ym = min(w["ym"] for w in below)
                    prev = None
                    for w in sorted((w for w in words if abs(w["ym"] - ym) < 3 and w["x0"] > m["x0"] - 4),
                                    key=lambda w: w["x0"]):
                        if _ANY_MARK.match(w["t"]) or (prev is not None and w["x0"] - prev > 25):
                            break
                        toks.append(w["t"])
                        prev = w["x1"]
                name = _clean(" ".join(toks))
                if name:
                    # 교육과정 순서: 쪽 → 단(왼쪽 표/오른쪽 표) → 위아래
                    col = 0 if m["x0"] < page.rect.width * 0.45 else 1
                    found.setdefault(subj, []).append(((pno, col, m["ym"]), name))
    out = {}
    for subj, items in found.items():
        seen, uniq = set(), []
        for _, n in sorted(items):
            if n not in seen:
                seen.add(n)
                uniq.append(n)
        out[subj] = uniq
    return out


def build(high: Path, mid: Path, legacy_high: Path | None, legacy_mid: Path | None) -> dict:
    vocab: dict = {
        "고등": extract(high, "high"),
        "중등": extract(mid, "mid"),
        "_source": {"고등": high.name, "중등": mid.name},
    }
    if legacy_high and legacy_high.exists():
        old = extract(legacy_high, "high")
        vocab["고등_15개정"] = {k: old[k] for k in LEGACY_HIGH_SUBJECTS if k in old}
        vocab["_source"]["고등_15개정"] = legacy_high.name
    if legacy_mid and legacy_mid.exists():
        vocab["중등_15개정"] = extract(legacy_mid, "mid")
        vocab["_source"]["중등_15개정"] = legacy_mid.name
    return vocab


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--high", type=Path, default=DEFAULT_HIGH)
    ap.add_argument("--mid", type=Path, default=DEFAULT_MID)
    ap.add_argument("--legacy-high", type=Path, default=DEFAULT_LEGACY_HIGH)
    ap.add_argument("--legacy-mid", type=Path, default=DEFAULT_LEGACY_MID)
    a = ap.parse_args(argv)
    for p in (a.high, a.mid):
        if not p.exists():
            print(f"분류표 PDF 없음: {p}")
            return 1
    vocab = build(a.high, a.mid, a.legacy_high, a.legacy_mid)
    out = REPO / "data" / "topic_vocab.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(vocab, ensure_ascii=False, indent=1), encoding="utf-8")

    for key in ("고등", "중등", "고등_15개정", "중등_15개정"):
        part = vocab.get(key) or {}
        print(f"{key}: {sum(len(v) for v in part.values())}개 / {len(part)}과목")
        for k, v in part.items():
            print(f"  {k}: {len(v)}개 — {v[:4]}")
    print(f"→ {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
