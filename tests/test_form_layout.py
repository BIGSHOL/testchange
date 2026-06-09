# 폼 레이아웃 추정기 회귀 단위테스트 (stdlib only, HWP COM·API·키 0).
#   python tests/test_form_layout.py
#
# COM 측정 실패 시 폴백으로 쓰는 객관식 높이 추정(_estimate_mc_heights)이 단조·보수적인지
# 검증한다(과여백/오버플로우 회피의 핵심). 전체 폴백 단배치는 COM 이 필요해 여기선 추정기만.
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core.hwp_form_writer import _estimate_mc_heights
from models.exam_document import Choice, ContentBlock, ContentType as CT, Question


def _q(texts, choices, table_rows=0):
    contents = [ContentBlock(type=CT.TEXT, value=t) for t in texts]
    if table_rows:
        contents.append(ContentBlock(type=CT.TABLE, value="", rows=[["x"]] * table_rows))
    chs = [Choice(number=i + 1, contents=[ContentBlock(type=CT.TEXT, value=c)])
           for i, c in enumerate(choices)]
    return Question(number=1, contents=contents, choices=chs)


def run():
    fails = []

    def chk(cond, msg):
        if not cond:
            fails.append("  " + msg)

    short = _q(["다음 중 옳은 것은?"], ["①", "②", "③", "④", "⑤"])
    long_q = _q(["아주 긴 발문입니다 " * 12], ["꽤 긴 선택지 텍스트입니다 정말"], table_rows=3)
    table_q = _q(["짧은 발문"], ["①", "②"], table_rows=4)

    h = _estimate_mc_heights([short, long_q, table_q])

    chk(h[0] >= 3, f"최소 높이 3 위반: {h[0]}")
    chk(h[1] > h[0], f"긴 문항이 짧은 문항보다 안 큼: {h[1]} vs {h[0]}")
    chk(h[2] > h[0], f"표 있는 문항이 더 안 큼: {h[2]} vs {h[0]}")
    # 짧은 선택지(≤12자)는 2열(3줄), 긴 선택지(>12자)는 5줄 → 선택지 길이가 높이에 반영
    chk(_estimate_mc_heights([_q(["x"], ["짧"])])[0]
        < _estimate_mc_heights([_q(["x"], ["아주 긴 선택지 텍스트입니다 정말로요"])])[0],
        "선택지 길이가 높이에 반영 안 됨")

    if fails:
        print("FAIL test_form_layout:")
        print("\n".join(fails))
        return 1
    print("OK test_form_layout (mc-height estimator)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
