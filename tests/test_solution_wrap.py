# -*- coding: utf-8 -*-
"""정답·해설 줄 폭 처리 회귀 — stdlib·COM 없음·API 0원.

2026-08-10 오성중 실측(정답면 렌더 + XML 대조)으로 확정한 3건:
  A. 긴 정답이 자동개행으로 2줄이 되면 폼 주입이 **첫 줄만** 써서 뒤가 사라졌다(#7).
  B. 폭 근사가 `\\triangle`·`\\angle` 같은 **보이는 글리프까지 0** 으로 세어 과소평가.
  C. 칼럼보다 넓은 **수식 하나**는 HWP 가 못 끊어 단 구분선을 넘었다(서답형3) →
     최상위 `=` 앞에서 여러 수식으로 분해.

실행: python tests/test_solution_wrap.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.content_parser import (  # noqa: E402
    _sol_seg_width, _wrap_solution_line, parse_ocr_response)
from core.latex_to_hwpeq import fold_long_equation, latex_to_hwpeq  # noqa: E402

FAILED: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(("  OK   " if cond else "  FAIL ") + label + ("" if cond else f" — {detail}"))
    if not cond:
        FAILED.append(label)


print("A. 긴 정답이 잘리지 않는다 (실데이터: 오성중 #7)")
ANS = "[문제 오류] 변의 길이 등 구체적 조건이 주어지지 않아 풀이가 불가능합니다."
env = {"header": "", "questions": [{
    "number": 7, "score": 4,
    "contents": [{"type": "text", "value": "값은?"}],
    "choices": [], "sub_questions": [], "answer": ANS}]}
q = parse_ocr_response(env, page_number=1).questions[0]
flat = " ".join("".join(b.value or "" for b in line) for line in q.answer)
check("정답 전체가 보존됨(줄 합계)", "불가능합니다" in flat, flat)

from core.hwp_form_writer import _answer_runs  # noqa: E402

runs = _answer_runs(q.answer)
check("_answer_runs 가 모든 줄을 기입", "불가능합니다" in runs, runs[-120:])
check("_answer_runs 가 첫 줄도 유지", "문제 오류" in runs)
check("빈 정답 방어", _answer_runs([]) == "")

print("\nB. 폭 근사 — 보이는 글리프를 0 으로 세지 않는다")
check("구조 명령은 0(\\mathrm)", _sol_seg_width(r"$\mathrm{AB}$") == _sol_seg_width("$AB$"))
check("기호 명령은 폭 있음(\\triangle)",
      _sol_seg_width(r"$\triangle ABC$") > _sol_seg_width("$ABC$"))
check("각 기호도 폭 있음(\\angle)",
      _sol_seg_width(r"$\angle A$") > _sol_seg_width("$A$"))
check("한글은 2, 반각은 1", _sol_seg_width("가나") == 4 and _sol_seg_width("ab") == 2)

print("\nC-0. 칼럼보다 넓은 전개식 = 여러 수식 run 으로 분할(기하 게이트)")
from core.hwp_form_writer import (  # noqa: E402
    _answer_col_width, _split_latex_at_top_eq, _wide_eq_runs)

WIDE_TEX0 = (r"\cos\angle AOI = \frac{-2}{2\cdot 2\sqrt{2-\sqrt3}} "
             r"= -\frac{1}{2\sqrt{2-\sqrt3}} = -\frac{\sqrt6+\sqrt2}{4} "
             r"= -\cos 15^\circ = \cos 165^\circ")
parts = _split_latex_at_top_eq(WIDE_TEX0)
check("최상위 = 앞에서 분할", len(parts) >= 4, str(len(parts)))
check("내용 보존(= 개수)", sum(p.count("=") for p in parts) == WIDE_TEX0.count("="))
check("cases 환경은 분할 금지",
      _split_latex_at_top_eq(r"\begin{cases}x=1\\y=2\end{cases}") == [])
# ⚠️ 바깥 = 는 끊어도 안전하다 — 금지 대상은 \left…\right **안쪽** = 다.
_lr = _split_latex_at_top_eq(r"\left| a = b \right| = 3 = 4")
check("left|…right| 그룹은 통째로 한 조각",
      bool(_lr) and _lr[0] == r"\left| a = b \right|", str(_lr))
check("left/right 균형 보존",
      "".join(_lr).count(r"\left") == 1 and "".join(_lr).count(r"\right") == 1)
check("= 하나면 분할 안 함", _split_latex_at_top_eq(r"y = -6x") == [])
check("분수 안 = 는 최상위 아님",
      _split_latex_at_top_eq(r"\frac{x=1}{y=2}") == [])
check("\\leq 는 = 로 오인하지 않음", _split_latex_at_top_eq(r"a \leq b \leq c") == [])

wide_runs = _wide_eq_runs(WIDE_TEX0, 1100, 29620)
check("과폭이면 여러 수식 run", wide_runs.count("<hp:equation") >= 4,
      str(wide_runs.count("<hp:equation")))
check("좁은 칼럼 기준이 없으면 단일 run",
      _wide_eq_runs(WIDE_TEX0, 1100, 0).count("<hp:equation") == 1)
check("짧은 수식은 단일 run",
      _wide_eq_runs("y = -6x", 1100, 29620).count("<hp:equation") == 1)
check("칼럼 폭 측정 폴백", _answer_col_width("<no lineseg/>") == 29620)
check("칼럼 폭 최빈값 측정",
      _answer_col_width('<hp:lineseg horzsize="29620"/><hp:lineseg horzsize="29620"/>'
                        '<hp:lineseg horzsize="100"/>') == 29620)

print("\nC. 쪼갤 = 가 없는 과폭 수식 = #(행)+&(정렬)로 접기 (사용자 제안 2026-08-10)")
WIDE_TEX = (r"\cos\angle AOI = \frac{-2}{2\cdot 2\sqrt{2-\sqrt3}} "
            r"= -\frac{1}{2\sqrt{2-\sqrt3}} = -\frac{\sqrt6+\sqrt2}{4} "
            r"= -\cos 15^\circ = \cos 165^\circ")
wide = latex_to_hwpeq(WIDE_TEX, italicize_stat=False)
folded = fold_long_equation(wide)
check("접힘(행 구분자 # 생성)", folded.count("#") >= 2, folded[:90])
check("정렬 기준 & 생성", folded.count("&") >= 3, str(folded.count("&")))
check("중괄호 균형 보존",
      folded.count("{") == wide.count("{") and folded.count("}") == wide.count("}"))
check("내용 보존(= 개수)", folded.count("=") == wide.count("="))
check("행 수 상한(4)", folded.count("#") <= 3, str(folded.count("#")))

print("\nC-2. 접으면 안 되는 것 — 무회귀")
check("이미 # 쓰는 cases 는 무변경",
      fold_long_equation("CASES {x+y=3 # 2x-y=1}") == "CASES {x+y=3 # 2x-y=1}")
check("이미 & 쓰는 행렬은 무변경",
      fold_long_equation("PMATRIX {1 & 2 # 3 & 4}") == "PMATRIX {1 & 2 # 3 & 4}")
check("= 한 번뿐이면 무변경", fold_long_equation("y = -6x") == "y = -6x")
check("중괄호 안 = 는 최상위 아님",
      fold_long_equation("f({x=1}) + g({y=2})") == "f({x=1}) + g({y=2})")
check("LEFT|…RIGHT| 안은 안 끊음",
      "#" not in fold_long_equation("LEFT | a = b RIGHT | = 3"))
check("<= 는 끊지 않음", fold_long_equation("a <= b <= c") == "a <= b <= c")
check("빈 스크립트 방어", fold_long_equation("") == "")

print("\nD. 텍스트 줄 개행은 그대로 동작")
short = "step1) 값을 구한다."
check("짧은 줄 무변경", _wrap_solution_line(short) == [short])
long_text = "step3) " + "가나다라마바사아자차카타파하 " * 8
check("긴 텍스트 줄은 여러 줄로", len(_wrap_solution_line(long_text)) >= 2)
check("짧은 수식 줄은 무변경",
      _wrap_solution_line("step2) $a = b$ 이다.") == ["step2) $a = b$ 이다."])

print("\n" + ("전부 통과" if not FAILED else f"{len(FAILED)}건 FAIL"))
sys.exit(1 if FAILED else 0)
