"""OCR 후보 ↔ 골든 채점 — stdlib only(anthropic·core import 금지).

`score_crop(candidate, golden)` 는 한 크롭의 OCR 결과 dict(`{header, questions:[...]}`)를
정답 dict 와 비교해 `CropScore` 를 만든다. `aggregate(scores)` 는 게이트 판정용 집계를 낸다.

설계 원칙:
  - **방어적 채점**: 스키마가 조금 깨져도 죽지 않고 점수를 낮춘다(`.get(...,[])`). 엄격 검증은
    `golden_record.py`(시딩) 담당.
  - **정규화가 실패를 삼키지 않게**: 텍스트=strict(대소문자 보존), 수식=norm_latex(구조 보존).
    지수/분수/로만체/대소문자 오인은 ratio 하락으로 드러난다.
  - figure/table 은 `type` 이 정확히 ``"figure"``/``"table"`` 일 때만 인정(FIG_NOTE text 미인정).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from scripts.ocr_eval.normalize import (
    norm_latex,
    norm_text_strict,
    seq_ratio,
)

# 수식 유사도가 이 값 미만이면 EQUATION_DRIFT 태그(지수·계수 오인 신호).
_EQ_DRIFT_THRESHOLD = 0.98
# 골든 지문 박스로 간주할 최소 정규화 길이(짧은 건 노이즈).
_PROSE_MIN_LEN = 20
_WIN, _STRIDE = 12, 6


@dataclass
class CropScore:
    """한 크롭의 세부 채점 결과(struct 하나로 뭉치지 않고 분해 — 디버깅용)."""

    sample_id: str = ""
    struct_score: float = 0.0
    question_count_score: float = 0.0
    choice_count_score: float = 0.0
    content_type_score: float = 0.0
    table_presence_f1: float = 0.0
    figure_presence_f1: float = 0.0
    number_score: float = 0.0
    score_score: float = 0.0
    text_ratio: float = 0.0
    equation_ratio: float = 0.0
    table_cell_acc: float | None = None
    regressions: list[str] = field(default_factory=list)


# ── 방어적 추출 헬퍼 ────────────────────────────────────────────────────────────

def _questions(doc) -> list[dict]:
    if not isinstance(doc, dict):
        return []
    qs = doc.get("questions")
    return [q for q in qs if isinstance(q, dict)] if isinstance(qs, list) else []


def _iter_blocks(question: dict):
    """한 문항의 모든 content 블록(문항·선택지·소문항)을 평탄화해 yield."""
    if not isinstance(question, dict):
        return
    for c in question.get("contents") or []:
        if isinstance(c, dict):
            yield c
    for ch in question.get("choices") or []:
        if isinstance(ch, dict):
            for c in ch.get("contents") or []:
                if isinstance(c, dict):
                    yield c
    for sub in question.get("sub_questions") or []:
        if isinstance(sub, dict):
            yield from _iter_blocks(sub)


def has_block_type(question: dict, block_type: str) -> bool:
    """문항 어디든 주어진 type 의 블록이 하나라도 있으면 True(figure/table 존재 판정용)."""
    return any(b.get("type") == block_type for b in _iter_blocks(question))


def _blocks_of_type(questions: list[dict], block_type: str) -> list[dict]:
    out: list[dict] = []
    for q in questions:
        out.extend(b for b in _iter_blocks(q) if b.get("type") == block_type)
    return out


def _concat_text(questions: list[dict]) -> str:
    return "".join(str(b.get("value", "")) for q in questions
                   for b in _iter_blocks(q) if b.get("type") == "text")


def _concat_equations(questions: list[dict]) -> str:
    return "".join(str(b.get("value", "")) for q in questions
                   for b in _iter_blocks(q)
                   if b.get("type") in ("equation", "equation_block"))


def _content_types(question: dict) -> list[str]:
    return [str(b.get("type", "")) for b in question.get("contents") or []
            if isinstance(b, dict)]


# ── 작은 점수 함수 ──────────────────────────────────────────────────────────────

def _count_score(a: int, b: int) -> float:
    """두 개수의 일치도 [0,1]. 같으면 1.0, 아니면 min/max."""
    if a == b:
        return 1.0
    hi = max(a, b)
    return (min(a, b) / hi) if hi > 0 else 1.0


def _presence_f1(cand_count: int, gold_count: int) -> float:
    """블록 존재(개수) F1. 둘 다 0이면 1.0(둘 다 '없음'에 합의)."""
    if gold_count == 0 and cand_count == 0:
        return 1.0
    tp = min(cand_count, gold_count)
    precision = tp / cand_count if cand_count else 0.0
    recall = tp / gold_count if gold_count else 0.0
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _windows(pn: str):
    if len(pn) <= _WIN:
        yield pn
        return
    for k in range(0, len(pn) - _WIN + 1, _STRIDE):
        yield pn[k:k + _WIN]


def _present_in(needle_norm: str, haystack_norm: str) -> bool:
    return bool(haystack_norm) and any(
        w and w in haystack_norm for w in _windows(needle_norm))


# ── 문항 페어링 ─────────────────────────────────────────────────────────────────

def _pair_questions(cqs: list[dict], gqs: list[dict]) -> list[tuple[dict, dict]]:
    """후보↔골든 문항 페어링. number 우선, 없으면 인덱스 순.

    초기 시드는 서술형(크롭당 단일 문항) 위주라 1:1 이 대부분. number 가 양쪽 다 있고 매칭되면
    그걸 쓰고, 남는 건 순서대로 채운다.
    """
    pairs: list[tuple[dict, dict]] = []
    used_c = set()
    # 1) number 매칭
    by_num = {}
    for ci, cq in enumerate(cqs):
        n = cq.get("number")
        if n is not None:
            by_num.setdefault(n, ci)
    matched_g = set()
    for gi, gq in enumerate(gqs):
        n = gq.get("number")
        if n is not None and n in by_num and by_num[n] not in used_c:
            ci = by_num[n]
            pairs.append((cqs[ci], gq))
            used_c.add(ci)
            matched_g.add(gi)
    # 2) 남은 것 인덱스 순
    rem_c = [cqs[i] for i in range(len(cqs)) if i not in used_c]
    rem_g = [gqs[i] for i in range(len(gqs)) if i not in matched_g]
    for cq, gq in zip(rem_c, rem_g):
        pairs.append((cq, gq))
    return pairs


# ── 메인 채점 ───────────────────────────────────────────────────────────────────

def score_crop(candidate, golden, sample_id: str = "") -> CropScore:
    """후보(candidate) vs 골든(golden) 한 크롭 채점. 둘 다 ``{header, questions:[...]}``."""
    cqs = _questions(candidate)
    gqs = _questions(golden)
    regressions: list[str] = []

    # 구조: 문항 수
    question_count_score = _count_score(len(cqs), len(gqs))
    if len(cqs) != len(gqs):
        regressions.append("QUESTION_COUNT")

    # 페어별 세부
    pairs = _pair_questions(cqs, gqs)
    choice_scores, ctype_scores, num_scores, score_scores = [], [], [], []
    for cq, gq in pairs:
        cc = [c for c in (cq.get("choices") or []) if isinstance(c, dict)]
        gc = [c for c in (gq.get("choices") or []) if isinstance(c, dict)]
        cs = _count_score(len(cc), len(gc))
        choice_scores.append(cs)
        if len(cc) != len(gc):
            regressions.append("CHOICE_COUNT")

        ct = "\x00".join(_content_types(cq))
        gt = "\x00".join(_content_types(gq))
        cts = seq_ratio(ct, gt)
        ctype_scores.append(cts)
        if ct != gt:
            regressions.append("CONTENT_TYPE_DRIFT")

        cn, gn = cq.get("number"), gq.get("number")
        ns = 1.0 if cn == gn else 0.0
        num_scores.append(ns)
        if cn != gn:
            regressions.append("NUMBER_MISMATCH")

        csc, gsc = cq.get("score"), gq.get("score")
        score_scores.append(1.0 if csc == gsc else 0.0)

    def _avg(xs: list[float]) -> float:
        return sum(xs) / len(xs) if xs else 1.0

    choice_count_score = _avg(choice_scores)
    content_type_score = _avg(ctype_scores)
    number_score = _avg(num_scores)
    score_score = _avg(score_scores)

    # 텍스트/수식 유사도(크롭 전체)
    text_ratio = seq_ratio(norm_text_strict(_concat_text(cqs)),
                           norm_text_strict(_concat_text(gqs)))
    equation_ratio = seq_ratio(norm_latex(_concat_equations(cqs)),
                               norm_latex(_concat_equations(gqs)))
    if equation_ratio < _EQ_DRIFT_THRESHOLD:
        regressions.append("EQUATION_DRIFT")

    # 지문 박스 누락(BOX_PROSE_DROP): 골든의 긴 text 블록이 후보 텍스트에 없으면.
    cand_text_norm = norm_text_strict(_concat_text(cqs))
    for q in gqs:
        for b in _iter_blocks(q):
            if b.get("type") != "text":
                continue
            pn = norm_text_strict(str(b.get("value", "")))
            if len(pn) >= _PROSE_MIN_LEN and not _present_in(pn, cand_text_norm):
                regressions.append("BOX_PROSE_DROP")
                break
        else:
            continue
        break

    # figure/table 존재 F1 (type 정확히 일치할 때만 — FIG_NOTE text 미인정)
    cand_tables = _blocks_of_type(cqs, "table")
    gold_tables = _blocks_of_type(gqs, "table")
    cand_figs = _blocks_of_type(cqs, "figure")
    gold_figs = _blocks_of_type(gqs, "figure")
    table_presence_f1 = _presence_f1(len(cand_tables), len(gold_tables))
    figure_presence_f1 = _presence_f1(len(cand_figs), len(gold_figs))

    # 표 셀 정확도: denominator = 골든 셀 수. 위치(row,col) 일치만(초기엔 alignment 없음).
    table_cell_acc: float | None
    if not gold_tables:
        table_cell_acc = None  # 표 없는 샘플 → 평균에서 제외
    elif not cand_tables:
        table_cell_acc = 0.0
        regressions.append("TABLE_MISSING")
    else:
        table_cell_acc = _table_cell_accuracy(cand_tables, gold_tables, regressions)

    struct_score = _avg([
        question_count_score, choice_count_score, content_type_score,
        number_score, score_score, table_presence_f1, figure_presence_f1,
    ])

    # 회귀 태그 중복 제거(순서 보존).
    seen: set[str] = set()
    regressions = [r for r in regressions if not (r in seen or seen.add(r))]

    return CropScore(
        sample_id=sample_id,
        struct_score=struct_score,
        question_count_score=question_count_score,
        choice_count_score=choice_count_score,
        content_type_score=content_type_score,
        table_presence_f1=table_presence_f1,
        figure_presence_f1=figure_presence_f1,
        number_score=number_score,
        score_score=score_score,
        text_ratio=text_ratio,
        equation_ratio=equation_ratio,
        table_cell_acc=table_cell_acc,
        regressions=regressions,
    )


def _table_cell_accuracy(cand_tables: list[dict], gold_tables: list[dict],
                         regressions: list[str]) -> float:
    """위치(row,col) 기반 셀 일치율. denom=골든 셀 수. extra row/cell 은 구조 회귀 태그.

    표가 여러 개면 가장 큰 골든 표 1개와 가장 큰 후보 표 1개를 비교(초기 단순화).
    """
    def _rows(t: dict) -> list[list[str]]:
        rows = t.get("rows")
        return [[str(c) for c in r] for r in rows if isinstance(r, list)] \
            if isinstance(rows, list) else []

    g = max((_rows(t) for t in gold_tables), key=lambda r: sum(len(x) for x in r),
            default=[])
    c = max((_rows(t) for t in cand_tables), key=lambda r: sum(len(x) for x in r),
            default=[])
    denom = sum(len(r) for r in g)
    if denom == 0:
        return 1.0
    correct = 0
    for ri, grow in enumerate(g):
        crow = c[ri] if ri < len(c) else []
        for cj, gcell in enumerate(grow):
            ccell = crow[cj] if cj < len(crow) else ""
            if norm_text_strict(ccell) == norm_text_strict(gcell):
                correct += 1
    # 후보에 행/열 초과(스키마 drift) → 태그(점수엔 영향 없지만 신호).
    if len(c) > len(g) or any(len(c[i]) > len(g[i])
                              for i in range(min(len(c), len(g)))):
        if "CONTENT_TYPE_DRIFT" not in regressions:
            regressions.append("CONTENT_TYPE_DRIFT")
    return correct / denom


# ── 집계 ────────────────────────────────────────────────────────────────────────

def aggregate(scores: list[CropScore]) -> dict:
    """게이트 판정용 집계. table_cell_acc=None(표 없는 샘플)은 평균에서 제외."""
    n = len(scores)
    if n == 0:
        return {"n_samples": 0, "mean_text_ratio": 1.0, "mean_equation_ratio": 1.0,
                "struct_accuracy": 1.0, "mean_table_cell_acc": None,
                "n_regressions": 0, "regression_rate": 0.0}

    def _mean(attr: str) -> float:
        return sum(getattr(s, attr) for s in scores) / n

    tbl = [s.table_cell_acc for s in scores if s.table_cell_acc is not None]
    crops_with_reg = sum(1 for s in scores if s.regressions)
    return {
        "n_samples": n,
        "mean_text_ratio": _mean("text_ratio"),
        "mean_equation_ratio": _mean("equation_ratio"),
        "struct_accuracy": _mean("struct_score"),
        "mean_table_cell_acc": (sum(tbl) / len(tbl)) if tbl else None,
        "n_regressions": crops_with_reg,           # 회귀가 있는 크롭 수
        "regression_rate": crops_with_reg / n,      # 비율(게이트 임계값과 비교)
    }
