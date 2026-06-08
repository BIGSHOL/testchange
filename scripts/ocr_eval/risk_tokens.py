"""위험토큰 분류기 — OCR 출력에서 '사람이 다시 봐야 할' 토큰을 표시(stdlib only).

⚠️ **이 모듈은 절대 `core.*`·`anthropic` 를 import 하지 않는다.** 감사기(audit)·실패채굴
(failures)·골든 테스트가 anthropic·API 키 없이(CI·다른 PC) 돌아야 하기 때문이다.

## 철학: "오류 검출기"가 아니라 "주의 표시기"
수학 시험지는 숫자·부등호가 매우 많다. 모든 숫자를 플래그하면 리포트가 시끄러워 쓸모가 없다.
그래서 **severity**(high/medium/low)로 노이즈를 억제한다 — 기본 감사는 medium↑만 보여 주고,
단순 숫자·% 같은 low 는 `--severity low` 일 때만 나온다. 우리가 실제로 데인 실패
(홀↔짝, 172.4↔172.44, 신뢰구간)는 high 로 올려 항상 눈에 띄게 한다.

두 용도:
  - `risk_tokens_in(text)` / `audit_blocks(questions)` : **단일 OCR 출력**(골든 불필요) 감사.
  - `categorize(golden_seg, cand_seg)` : 골든↔후보 **불일치 한 쌍**을 위험 카테고리로 태깅
    (failures.diff_crop 가 difflib opcode 구간에 적용).
"""

from __future__ import annotations

import re

# severity 순위(필터 비교용). 높을수록 항상 보여 준다.
_SEV_RANK = {"low": 0, "medium": 1, "high": 2}


def _sev_ok(sev: str, min_severity: str) -> bool:
    return _SEV_RANK.get(sev, 0) >= _SEV_RANK.get(min_severity, 1)


# ── 카테고리별 패턴 + severity ───────────────────────────────────────────────────
# high   = 우리가 실제로 데인 정답-바꾸는 오인(홀/짝·소수자릿수·신뢰구간).
# medium = 방향·지수처럼 자주 틀리지만 문맥으로 걸러지는 것.
# low    = 숫자·%·단위 — 너무 흔해 기본 출력에서 뺀다(요청 시만).
RISK_PATTERNS: dict[str, tuple[re.Pattern, str]] = {
    # 홀수↔짝수: 한 글자 차이로 정답이 뒤집힌다. 최우선.
    "HOL_JJAK": (re.compile(r"(홀수|짝수)"), "high"),
    # 소수 2자리 이상(172.44 류) — OCR 이 자릿수를 흘리거나 더한다.
    "DECIMAL": (re.compile(r"\d+\.\d{2,}"), "high"),
    # 신뢰구간·신뢰도·오차범위(±) — 통계 특유의 자주 깨지는 표기.
    "CONFIDENCE_INTERVAL": (re.compile(r"(신뢰구간|신뢰도|오차범위|±)"), "high"),
    # 부등호 — 방향(<↔>, ≤↔≥) 오인이 흔하다.
    "INEQUALITY": (re.compile(r"[<>≤≥≦≧]|\\le\b|\\ge\b|\\leq\b|\\geq\b"), "medium"),
    # 지수 — 2^{48} vs 2^{6} 처럼 위첨자 숫자가 핵심.
    "EXPONENT": (re.compile(r"\^\s*\{?\s*\d"), "medium"),
    # 백분율 — 흔하지만 99% vs 95% 처럼 가끔 중요. low.
    "PERCENT": (re.compile(r"\d+\s*%"), "low"),
    # 다글자 단위(cm·km·kg·mL·°C…) — 단위 자체는 거의 안 틀린다. low.
    "UNIT": (re.compile(r"\d+\s*(?:cm|mm|km|kg|mg|mL|kL|°C|℃)\b"), "low"),
    # 긴 정수(3자리+) — 자릿수 흘림 가능하나 너무 흔해 low.
    "NUMBER": (re.compile(r"\d{3,}"), "low"),
}

# 추상 figure 설명으로 흔히 끝나는 표현(value 가 실그림 데이터가 아니라 말풀이일 때 신호).
_FIGURE_ABSTRACT_RE = re.compile(r"(그림|도형|그래프|곡선|좌표|함수)")


def risk_tokens_in(text: str, min_severity: str = "medium") -> list[tuple[str, str, str]]:
    """단일 텍스트에서 (카테고리, 매치토큰, severity) 추출(min_severity 미만 제외).

    같은 카테고리가 여러 번 맞으면 토큰별로 모두 낸다(중복 토큰은 1회).
    """
    if not text:
        return []
    out: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for cat, (pat, sev) in RISK_PATTERNS.items():
        if not _sev_ok(sev, min_severity):
            continue
        for m in pat.finditer(text):
            tok = m.group(0)
            key = (cat, tok)
            if key in seen:
                continue
            seen.add(key)
            out.append((cat, tok, sev))
    return out


def figure_risk(question: dict) -> list[dict]:
    """figure 휴리스틱 — regex 한계 보완(손글씨 곡선 오인 등 '검토 필요' 신호).

    단순 정규식으로는 손글씨 figure 를 못 잡는다(JSON value 에 '손글씨' 가 없다). 대신 구조
    신호로 '검토 필요' 를 표시한다:
      - figure 블록 value 가 비었거나 추상 설명뿐(그림/그래프 등 말풀이) → OCR 이 그림을
        못 읽고 얼버무린 신호.
      - figure 가 표/박스(table·조건/상자 text) 와 같은 문항에 동반 → 박스 뒤 figure 오배치
        가능.
    """
    if not isinstance(question, dict):
        return []
    blocks = list(_iter_question_blocks(question))
    types = [b.get("type") for b in blocks]
    has_table = "table" in types
    has_box_prose = any(
        b.get("type") == "text" and _looks_like_box(str(b.get("value", "")))
        for b in blocks
    )
    out: list[dict] = []
    for b in blocks:
        if b.get("type") != "figure":
            continue
        val = str(b.get("value", "")).strip()
        reason = None
        if not val:
            reason = "figure value 비어 있음(그림 미해독 가능)"
        elif len(val) < 40 and _FIGURE_ABSTRACT_RE.search(val) and not any(ch.isdigit() for ch in val):
            reason = "figure value 가 추상 설명뿐(좌표·수치 없음)"
        elif has_table or has_box_prose:
            reason = "표/박스 동반 figure(오배치 검토)"
        if reason:
            out.append({
                "q_number": question.get("number"),
                "block_type": "figure",
                "token": (val[:30] or "<empty>"),
                "category": "FIGURE_HANDWRITING",
                "severity": "medium",
                "reason": reason,
            })
    return out


# 박스(조건/보기/상자) 라벨 흔적 — figure 동반 판정 보조.
_BOX_LABEL_RE = re.compile(r"[<\[](보기|조건|상자)[>\]]")


def _looks_like_box(text: str) -> bool:
    return bool(_BOX_LABEL_RE.search(text or ""))


def _iter_question_blocks(question: dict):
    """문항의 모든 content 블록 평탄화. metrics._iter_blocks 와 동일 형태(여기 자체 구현 —
    risk_tokens 는 metrics 에 의존하지 않게 둔다; failures 가 둘을 묶는다)."""
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
            yield from _iter_question_blocks(sub)


def audit_blocks(questions: list[dict], min_severity: str = "medium") -> list[dict]:
    """단일 OCR 출력(문항 리스트)을 감사 → 위험토큰 플래그 리스트(골든 불필요).

    각 플래그 = {q_number, block_type, token, category, severity[, reason]}.
    """
    flags: list[dict] = []
    for q in questions or []:
        if not isinstance(q, dict):
            continue
        qn = q.get("number")
        for b in _iter_question_blocks(q):
            btype = b.get("type")
            if btype not in ("text", "equation", "equation_block"):
                continue
            for cat, tok, sev in risk_tokens_in(str(b.get("value", "")), min_severity):
                flags.append({
                    "q_number": qn,
                    "block_type": btype,
                    "token": tok,
                    "category": cat,
                    "severity": sev,
                })
        # figure 휴리스틱(문항 단위)
        for fr in figure_risk(q):
            if _sev_ok(fr["severity"], min_severity):
                flags.append(fr)
    return flags


# ── 불일치 한 쌍 태깅(failures.diff_crop 용) ─────────────────────────────────────

_HOL = "홀수"
_JJAK = "짝수"


def categorize(golden_seg: str, cand_seg: str) -> str | None:
    """골든↔후보 **불일치 구간 한 쌍**을 위험 카테고리로 태깅. 매칭 없으면 None.

    한 구간이 정답을 바꾸는 어떤 위험류에 속하는지 — 우선순위는 high 먼저.
    """
    g = golden_seg or ""
    c = cand_seg or ""

    # 홀↔짝 swap(가장 치명적): 한쪽이 홀수 다른쪽이 짝수.
    if (_HOL in g and _JJAK in c) or (_JJAK in g and _HOL in c):
        return "HOL_JJAK"

    # 소수 자릿수 차이(172.4 vs 172.44).
    gd = re.findall(r"\d+\.\d+", g)
    cd = re.findall(r"\d+\.\d+", c)
    if gd != cd and (gd or cd):
        return "DECIMAL"

    # 신뢰구간/오차 표기 차이(한쪽에만 있거나 양쪽 표기가 다름).
    ci_pat = RISK_PATTERNS["CONFIDENCE_INTERVAL"][0]
    if (bool(ci_pat.search(g)) != bool(ci_pat.search(c))) and (
            ci_pat.search(g) or ci_pat.search(c)):
        return "CONFIDENCE_INTERVAL"

    # 부등호 방향/유무 차이.
    ineq = RISK_PATTERNS["INEQUALITY"][0]
    gi = ineq.findall(g)
    ci = ineq.findall(c)
    if gi != ci and (gi or ci):
        return "INEQUALITY"

    # 지수 숫자 차이.
    gx = re.findall(r"\^\s*\{?\s*(\d+)", g)
    cx = re.findall(r"\^\s*\{?\s*(\d+)", c)
    if gx != cx and (gx or cx):
        return "EXPONENT"

    # 일반 숫자 차이(자릿수/값) — 위 어디에도 안 걸리면 fallback.
    gn = re.findall(r"\d+", g)
    cn = re.findall(r"\d+", c)
    if gn != cn and (gn or cn):
        return "NUMBER"

    return None
