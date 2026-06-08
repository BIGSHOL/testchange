"""실패 채굴 — 골든↔후보의 **구체적 불일치**를 추출·태깅(stdlib only).

⚠️ `core.*`·`anthropic` import 금지(채굴기·골든 테스트가 오프라인에서 돌아야 함).

`diff_crop(candidate, golden, sample_id)` 는 한 크롭의 후보 OCR 출력과 골든을 비교해
`Mismatch` 리스트를 낸다. 텍스트/수식은 difflib opcode 로 **(golden_seg ↔ candidate_seg)**
구체 구간을 뽑고 `risk_tokens.categorize` 로 위험류를 태깅한다. 구조(table/figure/choice)
차이는 별도 `kind="structure"` Mismatch.

재사용: 정규화는 `normalize`(norm_text_strict·norm_latex), 문항 페어링·블록 추출은 `metrics`
(_pair_questions·_concat_text·_concat_equations·has_block_type·_blocks_of_type). 채점기와 같은
경로를 써 'A/B 채점에서 드러난 회귀'와 '여기서 채굴한 실패'가 일관되게 한다.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from scripts.ocr_eval.metrics import (
    _blocks_of_type,
    _concat_equations,
    _concat_text,
    _pair_questions,
    _questions,
)
from scripts.ocr_eval.normalize import norm_latex
from scripts.ocr_eval.risk_tokens import categorize

_WS_RE = re.compile(r"\s+")


def _norm_text_mine(s: str) -> str:
    """채굴용 텍스트 정규화 — **공백만** 제거(소수점·부등호·% 등 의미 글자는 보존).

    채점용 `norm_text_strict` 는 문장부호(`.` 포함)를 노이즈로 지워 172.44↔172.4 가 둘 다
    17244/1724 가 된다 → DECIMAL 을 NUMBER 로 격하한다. 채굴은 '무엇이 어떻게 달라졌나'를
    봐야 하므로 의미 글자를 살린다.
    """
    return _WS_RE.sub("", s or "")

# 너무 짧은 불일치 구간(한두 글자 노이즈)은 버린다 — 의미 있는 실패만 채굴.
_MIN_SEG = 1
# diff 구간 양옆 문맥 글자 수. difflib 은 최소 구간(홀↔짝, 4↔'')을 주므로, 카테고리 판정에
# 필요한 문맥(홀'수', '172.'44, '^{'48)을 살리려 양옆을 넓혀 잡는다.
_CTX = 5


@dataclass
class Mismatch:
    """골든↔후보 한 건의 구체적 실패.

    kind     = "text" | "equation" | "structure"
    category = risk_tokens 카테고리(text/equation) 또는 구조 사유(structure). None 가능.
    golden   = 골든 쪽 구간(구조면 설명).
    candidate= 후보 쪽 구간(구조면 설명). 누락이면 빈 문자열.
    """

    sample_id: str
    kind: str
    category: str | None
    golden: str
    candidate: str


def _diff_segments(g_norm: str, c_norm: str) -> list[tuple[str, str]]:
    """두 정규화 문자열의 difflib opcode 에서 (golden_seg, cand_seg) 불일치 쌍 추출.

    구간은 **양옆 문맥(`_CTX`)을 포함**해 넓혀 잡는다 — difflib 이 주는 최소 구간(홀↔짝,
    172.4 에서 '4' 하나)만으로는 위험 카테고리(HOL_JJAK·DECIMAL·EXPONENT)를 판정할 문맥이
    없기 때문. 보고/태깅 모두 이 확장 구간을 쓴다.
    """
    sm = difflib.SequenceMatcher(None, g_norm, c_norm)
    segs: list[tuple[str, str]] = []
    for op, g1, g2, c1, c2 in sm.get_opcodes():
        if op == "equal":
            continue
        if (g2 - g1) + (c2 - c1) < _MIN_SEG:
            continue
        gseg = g_norm[max(0, g1 - _CTX):g2 + _CTX]
        cseg = c_norm[max(0, c1 - _CTX):c2 + _CTX]
        segs.append((gseg, cseg))
    return segs


def diff_crop(candidate: dict, golden: dict, sample_id: str = "") -> list[Mismatch]:
    """후보 vs 골든 한 크롭 채굴 → Mismatch 리스트. 둘 다 ``{header, questions:[...]}``."""
    cqs = _questions(candidate)
    gqs = _questions(golden)
    out: list[Mismatch] = []

    # 1) 텍스트/수식 — 문항 페어별로(전체 concat 은 페어 경계를 잃으므로 페어 단위).
    for cq, gq in _pair_questions(cqs, gqs):
        for kind, norm_fn, extract in (
            ("text", _norm_text_mine, _concat_text),
            ("equation", norm_latex, _concat_equations),
        ):
            g_norm = norm_fn(extract([gq]))
            c_norm = norm_fn(extract([cq]))
            if g_norm == c_norm:
                continue
            for gseg, cseg in _diff_segments(g_norm, c_norm):
                out.append(Mismatch(
                    sample_id=sample_id,
                    kind=kind,
                    category=categorize(gseg, cseg),
                    golden=gseg,
                    candidate=cseg,
                ))

    # 2) 구조 — table/figure 존재, choice 개수.
    for btype in ("table", "figure"):
        gn = len(_blocks_of_type(gqs, btype))
        cn = len(_blocks_of_type(cqs, btype))
        if gn != cn:
            out.append(Mismatch(
                sample_id=sample_id,
                kind="structure",
                category=f"{btype.upper()}_COUNT",
                golden=f"{btype} x{gn}",
                candidate=f"{btype} x{cn}",
            ))
    for cq, gq in _pair_questions(cqs, gqs):
        gc = len([c for c in (gq.get("choices") or []) if isinstance(c, dict)])
        cc = len([c for c in (cq.get("choices") or []) if isinstance(c, dict)])
        if gc != cc:
            out.append(Mismatch(
                sample_id=sample_id,
                kind="structure",
                category="CHOICE_COUNT",
                golden=f"choices x{gc}",
                candidate=f"choices x{cc}",
            ))

    return out


def cluster_by_category(mismatches: list[Mismatch]) -> dict[str, list[Mismatch]]:
    """카테고리별 군집(보강 리포트용). None 카테고리는 'UNCATEGORIZED' 로 모은다."""
    clusters: dict[str, list[Mismatch]] = {}
    for m in mismatches:
        key = m.category or "UNCATEGORIZED"
        clusters.setdefault(key, []).append(m)
    return clusters
