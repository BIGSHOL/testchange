# 폼 {{토큰}} 치환(_fill_tokens) 회귀 테스트 — 합성 .hwpx zip, 한글 COM 불요.
#   py -3.11 tests/test_form_tokens.py   또는   pytest tests/test_form_tokens.py
#
# 커버(§내보내기 고도화 — 폼 우선):
#   - 머릿말/꼬릿말·헤더 블록의 {{학교}}·{{배점}} 등을 값으로 치환.
#   - 빈 값 토큰 → 빈 문자열로 제거.
#   - XML escape(값에 & < > 포함 시 엔티티).
#   - 토큰 없는 파일/값 → 무변경(0건), 멱등.
#
# core.hwp_com_writer import 시 win32com 이 로드됨(test_render_fixes 와 동일 전제 — 엔진 테스트
# 환경엔 pywin32 설치). 실제 COM 은 호출하지 않고 zip XML 만 다룬다.
import sys
import os
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core.hwp_com_writer import _fill_tokens, _set_page_margins
from core.template_headers import token_values


def _make_hwpx(section_xml: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".hwpx")
    os.close(fd)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/hwp+zip")
        z.writestr("Contents/section0.xml", section_xml)
    return path


def _read_section(path: str) -> str:
    with zipfile.ZipFile(path) as z:
        return z.read("Contents/section0.xml").decode("utf-8")


def run() -> int:
    fails = []

    def chk(cond, msg):
        if not cond:
            fails.append("  " + msg)

    # 1) 기본 치환 + 빈값 제거 + 숫자
    xml = ("<hml><hp:t>{{제목}}</hp:t><hp:t>{{학교}}</hp:t>"
           "<hp:t>{{배점}}</hp:t><hp:t>{{출제자}}</hp:t></hml>")
    p = _make_hwpx(xml)
    try:
        vals = token_values({"title": "1학기 중간", "schoolName": "성광고",
                             "totalScore": 100, "examiner": ""})
        n = _fill_tokens(p, vals)
        out = _read_section(p)
        chk(n >= 4, f"치환 개수: {n}")
        chk("1학기 중간" in out and "성광고" in out and "100" in out, f"값 치환: {out}")
        chk("{{제목}}" not in out and "{{학교}}" not in out, f"토큰 제거: {out}")
        chk("{{출제자}}" not in out, f"빈값 토큰 제거: {out}")
    finally:
        os.remove(p)

    # 2) XML escape — 값에 & < >
    p2 = _make_hwpx("<hml><hp:t>{{학교}}</hp:t></hml>")
    try:
        _fill_tokens(p2, token_values({"schoolName": "A&B<중>"}))
        out2 = _read_section(p2)
        chk("A&amp;B&lt;중&gt;" in out2, f"XML escape: {out2}")
        chk("A&B<중>" not in out2, f"raw 미삽입: {out2}")
    finally:
        os.remove(p2)

    # 3) 토큰 없으면 무변경(0건) + 멱등
    p3 = _make_hwpx("<hml><hp:t>토큰 없음</hp:t></hml>")
    try:
        n3 = _fill_tokens(p3, token_values({"schoolName": "X"}))
        chk(n3 == 0, f"토큰 없음 0건: {n3}")
        # 멱등 — 이미 치환된 파일에 재실행해도 0건
        p4 = _make_hwpx("<hml><hp:t>{{학교}}</hp:t></hml>")
        _fill_tokens(p4, token_values({"schoolName": "성광고"}))
        n5 = _fill_tokens(p4, token_values({"schoolName": "성광고"}))
        chk(n5 == 0, f"멱등(재실행 0건): {n5}")
        os.remove(p4)
    finally:
        os.remove(p3)

    # 4) _set_page_margins — 쪽 여백만 교체, cellMargin/outMargin 은 불변
    sec = ('Contents/section0.xml')
    fd, p5 = tempfile.mkstemp(suffix=".hwpx")
    os.close(fd)
    with zipfile.ZipFile(p5, "w") as z:
        z.writestr("mimetype", "application/hwp+zip")
        z.writestr(sec,
                   '<hml><hp:pagePr><hp:margin header="4252" footer="4252" gutter="0" '
                   'left="8504" right="8504" top="5668" bottom="4252"/></hp:pagePr>'
                   '<hp:tbl><hp:cellMargin left="510" right="510" top="141" bottom="141"/></hp:tbl></hml>')
    try:
        n = _set_page_margins(p5)
        with zipfile.ZipFile(p5) as z:
            out = z.read(sec).decode("utf-8")
        chk(n == 1, f"여백 교체 1건: {n}")
        chk('left="4252"' in out and 'top="3402"' in out, f"좁은 여백 적용: {out}")
        chk('left="8504"' not in out, "옛 여백 제거")
        chk('<hp:cellMargin left="510"' in out, "cellMargin 불변(오매치 없음)")
    finally:
        os.remove(p5)

    if fails:
        print("FAIL test_form_tokens:")
        print("\n".join(fails))
        return 1
    print("OK test_form_tokens (토큰 치환/escape/빈값/멱등 + 여백)")
    return 0


def test_form_tokens():
    assert run() == 0


if __name__ == "__main__":
    raise SystemExit(run())
