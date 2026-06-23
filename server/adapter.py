# -*- coding: utf-8 -*-
"""웹 wire payload(HwpPayload v2) → core.content_parser.parse_ocr_response 봉투 변환.

웹(hwpConnector.ts)이 보내는 네이티브 typed-block(contents/choices/subQuestions)을
엔진이 받는 envelope({"header","questions":[...]})로 매핑한다.
- camelCase → snake_case (subQuestions→sub_questions, labelType→label_type)
- 빈 contents → text 폴백
- figure 제외 (웹 BlockType union엔 없지만 이중 안전; 파서도 figure를 None 드롭)

웹 타입(src/types/ocrBlocks.ts):
  ContentBlock { type: "text"|"equation"|"equation_block"|"table", value: str, rows: str[][] }
  ChoiceGroup  { number, contents: ContentBlock[] }
  SubQuestion  { number, contents, choices?, score?, labelType? }  (1단계 깊이)
"""
from __future__ import annotations

_ALLOWED_BLOCK_TYPES = ("text", "equation", "equation_block", "table")


def _as_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clean_contents(blocks) -> list[dict]:
    out: list[dict] = []
    for b in blocks or []:
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        if t not in _ALLOWED_BLOCK_TYPES:
            continue  # figure/image 등 제외
        value = b.get("value", "")
        rows = b.get("rows", [])
        # table에서 셀이 value(list)로 온 경우 rows로 강등 (파서도 강등하지만 선방어)
        if isinstance(value, list):
            rows = value
            value = ""
        out.append({
            "type": t,
            "value": value if isinstance(value, str) else str(value),
            "rows": rows if isinstance(rows, list) else [],
        })
    return out


def _adapt_choice(c) -> dict:
    if not isinstance(c, dict):
        return {"number": 0, "contents": []}
    return {
        "number": _as_int(c.get("number"), 0),
        "contents": _clean_contents(c.get("contents")),
    }


def _adapt_problem(p: dict) -> dict:
    q: dict = {"number": _as_int(p.get("number"), 0)}

    score = p.get("score")
    if isinstance(score, (int, float)):
        q["score"] = score

    if p.get("labelType"):
        q["label_type"] = p["labelType"]

    contents = _clean_contents(p.get("contents"))
    if not contents:
        text = (p.get("text") or "").strip()
        if text:
            contents = [{"type": "text", "value": text, "rows": []}]
    q["contents"] = contents

    choices = p.get("choices")
    if choices:
        q["choices"] = [_adapt_choice(c) for c in choices]

    subs = p.get("subQuestions")
    if subs:
        q["sub_questions"] = [_adapt_problem(s) for s in subs if isinstance(s, dict)]

    return q


def _opt_str(m: dict, key: str) -> str:
    v = m.get(key)
    return v if isinstance(v, str) else ""


def adapt_payload(payload: dict) -> tuple[dict, dict, dict]:
    """HwpPayload dict → (envelope dict, meta dict, style dict).

    envelope 는 parse_ocr_response 가 받는 한 페이지 봉투.
    meta 는 build_document(title/subject/grade) 인자 + 헤더 렌더용 확장 필드.
    style 은 고른 폼(template/accentColor/columns) — 엔진 헤더 분기용.

    구버전 웹(meta 3필드만, style 없음)도 안전: 확장 필드 빈 문자열, style 누락 시
    template="jeongtong" 기본 → 단순 제목 헤더로 폴백(회귀 0).
    """
    problems = payload.get("problems") if isinstance(payload, dict) else None
    envelope = {
        "header": "",
        "questions": [
            _adapt_problem(p) for p in (problems or []) if isinstance(p, dict)
        ],
    }
    m = (payload.get("meta") if isinstance(payload, dict) else None) or {}
    meta = {
        # build_document 인자 (필수 3).
        "title": m.get("title") or "",
        "subject": m.get("subject") or "",
        "grade": m.get("grade") or "",
        # 헤더 렌더용 확장 — 고른 템플릿이 쓰는 필드만 채워짐(없으면 빈 문자열).
        "schoolName": _opt_str(m, "schoolName"),
        "semester": _opt_str(m, "semester"),
        "examDate": _opt_str(m, "examDate"),
        "examDuration": _opt_str(m, "examDuration"),
        "examiner": _opt_str(m, "examiner"),
        "totalScore": m.get("totalScore") if isinstance(m.get("totalScore"), (int, float)) else None,
        "academyName": _opt_str(m, "academyName"),
        "instructorName": _opt_str(m, "instructorName"),
        "conceptNote": _opt_str(m, "conceptNote"),
        "todayGoal": _opt_str(m, "todayGoal"),
        "patternName": _opt_str(m, "patternName"),
        "patternStrategy": _opt_str(m, "patternStrategy"),
    }
    st = (payload.get("style") if isinstance(payload, dict) else None) or {}
    columns = st.get("columns")
    # 여백(mm) — 웹에서 설정. 유효한 숫자 필드만 추림. 없으면 None(폼/기본 여백 유지).
    mg = st.get("margins")
    margins = None
    if isinstance(mg, dict):
        picked = {
            k: mg[k]
            for k in ("top", "bottom", "left", "right")
            if isinstance(mg.get(k), (int, float))
        }
        margins = picked or None
    style = {
        "template": st.get("template") or "jeongtong",
        "accentColor": _opt_str(st, "accentColor"),
        "columns": columns if columns in (1, 2) else 1,
        "margins": margins,
    }
    return envelope, meta, style
