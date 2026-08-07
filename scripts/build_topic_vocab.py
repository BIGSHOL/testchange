# -*- coding: utf-8 -*-
"""단원 분류표 PDF → 어휘 사전(JSON) 생성 — 개발용 1회 실행 도구.

세션(Claude Code)이 정답·해설 메타를 채울 때 참조하던 **분류표 어휘**를 배포 exe 도
쓸 수 있게 데이터로 굽는다(사용자 2026-08-07: "그 로컬 파일을 배포 빌드/exe 에도
기억시켜놓고 완벽하게 똑같은 동작이 되도록").

레벨 규약(CLAUDE.md 2026-07-24):
  · **고등 = 소단원**(분류표 ``ⅰ)`` 레벨) — 폼 라벨 ``[소단원]``
  · **중등 = 중단원**(분류표 ``①`` 레벨)  — 폼 라벨 ``[중단원]``

사용::

    python scripts/build_topic_vocab.py            # 기본 경로(D:/기출/기출작업/…)에서 굽기
    python scripts/build_topic_vocab.py <고등.pdf> <중등중단원.pdf>

산출: ``data/topic_vocab.json``  (build.spec 이 exe 에 번들)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# 로컬 미러 기본 경로(N: 끊김 대비 — 메모리 local-mirror-gichul-pdfs)
DEFAULT_HIGH = Path("D:/기출/기출작업/189차/고등수학전체 소단원 분류(ver.250604).pdf")
DEFAULT_MID = Path("D:/기출/기출작업/중등수학전체 중단원 분류.pdf")

_SUBJ_RE = re.compile(r"●\s*([^\n]+)")
_SMALL_RE = re.compile(r"[ⅰ-ⅹ]\)\s*([^\n]+)")     # 고등 소단원 (ⅰ) …
_MID_RE = re.compile(r"[①-⑳]\s*([^\n]+)")          # 중등 중단원 ① …


def _pdf_text(path: Path) -> str:
    import fitz
    with fitz.open(str(path)) as d:
        return "".join(p.get_text() for p in d)


def _split_by_subject(text: str) -> list[tuple[str, str]]:
    """``● 과목`` 기준으로 (과목명, 본문) 조각 리스트."""
    marks = list(_SUBJ_RE.finditer(text))
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out.append((m.group(1).strip(), text[m.end():end]))
    return out


def _clean(name: str) -> str:
    """항목명 정리 — 줄바꿈 잔재·번호·공백 정규화."""
    s = re.sub(r"\s+", " ", name).strip()
    s = s.strip(" ,·")
    return s


def build(high_pdf: Path, mid_pdf: Path) -> dict:
    vocab: dict = {"고등": {}, "중등": {}}

    # 고등: 과목별 **소단원(ⅰ)** 목록
    for subj, body in _split_by_subject(_pdf_text(high_pdf)):
        names = [_clean(n) for n in _SMALL_RE.findall(body)]
        # 중복 제거(순서 보존)
        seen, uniq = set(), []
        for n in names:
            if n and n not in seen:
                seen.add(n)
                uniq.append(n)
        if uniq:
            vocab["고등"][_clean(subj)] = uniq

    # 중등: 학년별 **중단원(①)** 목록
    for subj, body in _split_by_subject(_pdf_text(mid_pdf)):
        names = [_clean(n) for n in _MID_RE.findall(body)]
        seen, uniq = set(), []
        for n in names:
            if n and n not in seen:
                seen.add(n)
                uniq.append(n)
        if uniq:
            vocab["중등"][_clean(subj)] = uniq
    return vocab


def main(argv: list[str]) -> int:
    high = Path(argv[0]) if len(argv) > 0 else DEFAULT_HIGH
    mid = Path(argv[1]) if len(argv) > 1 else DEFAULT_MID
    for p in (high, mid):
        if not p.exists():
            print(f"분류표 PDF 없음: {p}")
            return 1
    vocab = build(high, mid)
    out = REPO / "data" / "topic_vocab.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(vocab, ensure_ascii=False, indent=1), encoding="utf-8")

    n_h = sum(len(v) for v in vocab["고등"].values())
    n_m = sum(len(v) for v in vocab["중등"].values())
    print(f"고등(소단원) {n_h}개 / {len(vocab['고등'])}과목")
    for k, v in vocab["고등"].items():
        print(f"  {k}: {len(v)}개 — {v[:4]}")
    print(f"중등(중단원) {n_m}개 / {len(vocab['중등'])}학년")
    for k, v in vocab["중등"].items():
        print(f"  {k}: {len(v)}개 — {v[:4]}")
    print(f"→ {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
