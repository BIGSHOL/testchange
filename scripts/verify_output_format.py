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
    # 2단 본문(웹 내보내기)에서 박스를 칼럼 폭에 맞추느라 ``line_width=self._box_width()``
    # 인자가 붙었다(2026-06-24 머지). 합의(1×1 테두리 표 박스)는 그대로라 호출 형태만 완화.
    chk(6, "보기 1×1 테두리 박스", "table_begin(1, 1" in W)
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

    F = _read(F_PATH)
    chk(29, "표 캡션 줄바꿈+우측정렬(_write_caption_run)",
        "def _caption_spans" in W
        and "align_right()" in _func_body(W, "_write_caption_run")
        and "_write_tail_seq" in _func_body(W, "_write_condition_box")
        and "_write_caption_run(pre[cap_j:])" in W
        and "w._write_caption_run(pre[cap_j:])" in F)
    _msp = 'h.Run("MoveSelParaEnd")'   # 실제 코드 패턴(경고 주석의 단어와 구별)
    chk(30, "배점 폴백 정확 span 삭제(정답 블록 보호)",
        _msp not in _func_body(W, "_write_score_inline_or_right")
        and _msp not in _func_body(W, "_write_total_score_inline_or_right")
        and _msp not in _func_body(F, "_put_score")
        and _msp not in _func_body(F, "_put_total_score")
        and "SelectText(sp[1], sp[2], ep[1], ep[2])" in F
        and "SelectText(sp[1], sp[2], ep[1], ep[2])" in W,
        "배점 우측정렬 폴백은 삽입분(sp→ep)만 SelectText 로 삭제 — MoveSelParaEnd 는 "
        "마지막 서술형에서 폼 정답 블록 앵커까지 삼킴(강동중 #20, 2026-06-10)")

    chk(31, "2단 가운데 구분선 = 폼 바탕쪽(최종 .hwp 저장), 본문 colLine 주입 금지",
        "_inject_column_divider" not in F
        and "def save_as_hwp" in C
        and "save_as_hwp(output_path, final_hwp)" in F
        and "save_as_hwp(output_path, final_hwp)" in W,
        "폼 가운데선은 masterpage0.xml 의 바탕쪽 단 구분선 — 본문 colPr 에 <hp:colLine> 을 "
        "주입하면 내용 높이까지만 그려져 레퍼런스(전체 높이)와 다르다(사용자 2026-07-24). "
        "HWP 는 .hwpx 의 바탕쪽을 안 그리므로 최종 산출물을 .hwp 로 굽는다(save_as_hwp)")

    chk(32, "정답·메타란·해설 기입(완료본 규약)",
        "_inject_answer_runs(output_path" in F and "_inject_question_meta(output_path" in F
        and "_inject_solutions(output_path" in F
        and "difficulty" in _read(ROOT / "models" / "exam_document.py"),
        "정답 페이지(미주 내용)에 정답 run·서술형 해설(step), 문항별 [소단원]/[난이도] 메타란 "
        "값을 저장후 XML 로 기입 — 완료본(194차 달서고) 규약. 라이브 COM 캐럿 진입은 정답 "
        "블록 앵커 파손 전례(강동중 #20)라 금지")

    # ⭐ #33 배점 표시 단일 출처 — `score_str` 을 **모든** 소비자가 써야 한다.
    #
    # 처음엔 렌더 4곳에만 넣었는데, `score` 를 문자열로 만드는 곳은 그 외에도 있었다:
    # `solution_generator` 의 소문항 배점·문항 배점(=**DeepSeek 프롬프트**)과
    # `hwpx_writer` 폴백. 그래서 exe 는 모델에 `(배점 3.0점)` 을, 웹은 `(배점 3점)` 을
    # 보내 **생성되는 정답·해설이 갈리고 그게 그대로 .hwp 에 렌더**됐다(적대리뷰 2026-08-08).
    # 렌더만 맞춰서는 소용이 없어 grep 게이트로 박제한다.
    _score_raw = []
    for rel in ("core/hwp_com_writer.py", "core/hwp_form_writer.py", "core/hwpx_writer.py",
                "core/solution_generator.py", "gui/main_window.py"):
        for i, ln in enumerate(_read(ROOT / rel).splitlines(), 1):
            if ln.lstrip().startswith("#"):
                continue
            # ⚠️ `score_str(score)` 안의 `str(score)` 를 잡지 않도록 lookbehind 필수
            # (첫 시도가 자기 자신을 오탐해 전부 FAIL 이었다).
            if re.search(r"(?<!score_)str\(\s*(score|sc|num)\s*\)"
                         r"|\{\s*(score|sc)\s*\}\s*점", ln):
                _score_raw.append(f"{rel}:{i}")
    chk(33, "배점 표시는 score_fmt.score_str 단일 출처(raw str(score) 금지)",
        not _score_raw and "def score_str" in _read(ROOT / "core" / "score_fmt.py"),
        f"raw 사용 잔존: {', '.join(_score_raw)}" if _score_raw else
        "3.0 배점이 exe 는 '[3.0점]', 웹은 '[3점]' 으로 갈린다 — JSON 이 int/float 를 "
        "구분 못 하므로 표시 시점 정규화가 유일한 해법이고, **프롬프트 생성기까지** "
        "같은 함수를 써야 정답·해설이 안 갈린다")

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
