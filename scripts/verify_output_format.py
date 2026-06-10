#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""시험지 출력 포맷 합의사항 강제 검증 (verify-output-format 스킬의 실행 백엔드).

두 가지 방식으로 동작한다:

1. **PostToolUse 훅** (stdin 에 hook JSON): Edit/Write 가 건드린 파일이 COM writer
   관련 파일일 때만 검증. 위반이 있으면 stderr 로 보고하고 **exit 2** (Claude 에 차단
   피드백). 관련 없으면 조용히 exit 0.
2. **수동/CI** (`--all`): 전체 합의 검증 후 보고. 위반 시 exit 1.

합의 스펙은 `.claude/skills/verify-output-format/SKILL.md` 와 `CLAUDE.md` 에 있다.
합의가 바뀌면 이 스크립트의 검사도 함께 갱신한다.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
W_PATH = ROOT / "core" / "hwp_com_writer.py"
C_PATH = ROOT / "core" / "hwp_com.py"
F_PATH = ROOT / "core" / "hwp_form_writer.py"
L_PATH = ROOT / "core" / "latex_to_hwpeq.py"
O_PATH = ROOT / "core" / "ocr_engine.py"


def _norm(p) -> str:
    """플랫폼 무관 경로 정규화(대소문자·구분자·상대경로)."""
    return os.path.normcase(os.path.normpath(os.path.abspath(str(p))))


# 훅을 트리거할 파일들(이 중 하나라도 편집되면 검증)
WATCHED = {_norm(p) for p in (W_PATH, C_PATH, F_PATH, L_PATH, O_PATH)}


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""


def _func_body(src: str, name: str) -> str:
    """``def <name>`` 부터 다음 같은(또는 더 얕은) 들여쓰기의 def/class 직전까지.

    무경계 ``re.S`` 패턴이 파일 뒷부분의 **다른 함수** 코드와 매칭돼 검사가
    동어반복(보호 대상을 지워도 PASS)이 되는 것을 막는다 — 검사 #5/#10/#18.
    """
    m = re.search(rf"^([ \t]*)def {re.escape(name)}\b", src, re.M)
    if not m:
        return ""
    indent = m.group(1)
    nxt = re.search(rf"^{indent}(?:def |class |@)", src[m.end():], re.M)
    return src[m.start(): m.end() + nxt.start()] if nxt else src[m.start():]


def run_checks():
    """(번호, 합의명, pass여부, 상세) 목록 반환."""
    W = _read(W_PATH)
    C = _read(C_PATH)
    L = _read(L_PATH)
    O = _read(O_PATH)
    out = []

    def chk(n, name, ok, detail=""):
        out.append((n, name, bool(ok), detail))

    chk(1, "미주 자동번호", "self.s.endnote()" in W)
    chk(2, '미주 형식 "1." (suffix .)',
        "def _set_endnote_suffix" in W and "_set_endnote_suffix(output_path)" in W)
    chk(3, "미주 12pt 볼드",
        "set_char_shape(self.note_pt, bold=True)" in C and "note_pt: int = 12" in C)
    chk(4, "객관식 배점 인라인", "self._write_score(question.score)" in W)
    body5 = _func_body(W, "_write_score_inline_or_right")
    chk(5, "서술형 배점 인라인-우선·넘치면 우측정렬",
        "self._write_score_inline_or_right(question.score)" in W
        and bool(re.search(
            r"KeyIndicator\(\)\[5\].*?align_right\(\).*?leading_space=False",
            body5, re.S)))
    chk(6, "보기 1×1 테두리 박스", "table_begin(1, 1)" in W)
    chk(7, "박스↔선택지 빈줄 없음(_write_tail)",
        "ended_box = self._write_tail(tail)" in W
        and "if question.choices and not ended_box:" in W
        and "self._write_condition_box(box)" in W)
    chk(8, "선택지 2열 정렬",
        "as_equation=(cols == 2)" in W and "as_equation: bool = False" in W)
    chk(9, "표 셀 수식 객체", "self.s.equation(latex_to_hwpeq(val))" in W)
    chk(10, "표 셀 가운데정렬",
        "align_center()" in _func_body(W, "_write_equation_table"))
    chk(11, "번호-발문 같은 줄(A7)", "inline=(i == 0)" in W)
    chk(12, "숫자 수식화(강등 없음, A8)",
        "_is_plain_number" not in W and "_PLAIN_NUMBER_RE" not in W
        and "self.s.table(" not in W)
    chk(13, "표 CreateSet(다중표)", 'CreateAction("TableCreate")' in C)
    chk(14, "셀수식 Close 가드", "if h.GetPos()[0] == 0:" in C)
    chk(15, "표 탈출 SetPos(para+1)", "SetPos(p[0], p[1] + 1, 0)" in C)
    chk(16, "글자 투명 방지(Ratio/Size 100)",
        'setattr(cs, f"Ratio{sc}", 100)' in C and 'setattr(cs, f"Size{sc}", 100)' in C)

    chk(18, "블록수식 가운데정렬",
        bool(re.search(r"EQUATION_BLOCK:.*?if not inline:.*?align_center\(\)",
                       _func_body(W, "_write_block"), re.S)))
    chk(19, "소문항 총점 인라인-우선·넘치면 우측정렬",
        "def _split_trailing_score" in W
        and "self._write_total_score_inline_or_right(total_num)" in W
        and bool(re.search(
            r"KeyIndicator\(\)\[5\].*?align_right\(\)",
            _func_body(W, "_write_total_score_inline_or_right"), re.S)))
    chk(20, "발문뒤 영역 공통 렌더(_write_tail)",
        "def _write_tail" in W and "def _tail_start" in W
        and "_write_condition_box(box)" in W)

    # ── 방어 하네스: 핵심 후보정 함수/패턴 생존 확인(버그류 재발 방지, 정적 검사) ────
    # 과거 디버깅으로 확립한 후보정 로직이 리팩터링 중 사라지면 같은 버그가 재발한다.
    # OCR 엔진/변환기의 핵심 함수·패턴이 살아있는지 grep 기반으로 검사한다.
    chk(21, "서답형 지문 윈도우 포함검사(_merge 오주입 방지)",
        "def _merge_missing_passages" in O
        and "_WIN, _STRIDE" in O and "def _windows" in O,
        "" if "def _merge_missing_passages" in O else "_merge_missing_passages 없음")
    chk(22, "객관식 표 복구 트리거(_recover_table)",
        "def _recover_table" in O and "def _transcribe_table" in O
        and "_TABLE_HINT_RE" in O and "_has_table_block" in O
        and "_parse_markdown_table" in O)
    chk(23, "표 복구 후 table 블록 삽입",
        bool(re.search(r'"type":\s*"table".*?"rows":\s*rows', O)))
    chk(24, "OCR 프롬프트 표 강조(요약 금지)",
        "type=\"table\"" in O and "확률분포표" in O
        and ("요약·생략" in O or "요약·생략하거나" in O))
    chk(25, r"latex \left 자동크기 경로",
        r"\left" in L and "leftright" in L.lower())
    chk(26, r"latex \% → %% 매핑",
        r'r"\%": "%"' in L or r"\%" in L and '"%"' in L)
    chk(27, "단위 로만체+공백(_romanize_units)",
        "def _romanize_units" in L)
    chk(28, "기하 라벨 로만체(mathrm/로만 라벨)",
        "_mathrm_pattern" in L and "_apply_roman_labels" in L)

    mid_ok = ("mid" in L) and (r"\mid" in L)
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from core.latex_to_hwpeq import latex_to_hwpeq
        mid_ok = mid_ok and latex_to_hwpeq(r"x \mid y").count("|") == 1
        chk(17, "\\mid 매핑", mid_ok)
    except Exception as e:
        chk(17, "\\mid 매핑", False, f"import/convert err: {e}")
    return out


def report(results):
    lines = ["## verify-output-format 검증 결과", ""]
    for n, name, ok, detail in results:
        mark = "PASS" if ok else "FAIL"
        lines.append(f"  [{mark}] #{n} {name}" + (f" — {detail}" if detail else ""))
    sys.stderr.write("\n".join(lines) + "\n")
    return all(r[2] for r in results)


def main() -> int:
    raw = ""
    try:
        if not sys.stdin.isatty():
            raw = sys.stdin.read()
    except Exception:
        raw = ""

    hook_mode = bool(raw.strip()) and "--all" not in sys.argv
    if hook_mode:
        # 훅: 편집된 파일이 감시 대상일 때만 검증
        try:
            data = json.loads(raw)
            fp = (data.get("tool_input") or {}).get("file_path", "")
        except Exception:
            return 0
        if not fp or _norm(fp) not in WATCHED:
            return 0  # 관련 없는 편집 → 통과

    ok = report(run_checks())
    if ok:
        return 0
    if hook_mode:
        sys.stderr.write(
            "\n[verify-output-format] 출력 포맷 합의사항 위반 — 위 FAIL 항목을 고치거나, "
            "합의가 바뀐 것이라면 SKILL.md/CLAUDE.md 와 이 스크립트를 함께 갱신하세요.\n")
        return 2  # PostToolUse: stderr 를 Claude 에 차단 피드백
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
