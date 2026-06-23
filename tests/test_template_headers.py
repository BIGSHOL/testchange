# 인쇄 폼(템플릿+메타) 배선 회귀 테스트 — COM·API·키 0 (순수 로직).
#   py -3.11 tests/test_template_headers.py   또는   pytest tests/test_template_headers.py
#
# 커버(§내보내기 고도화 Phase 0):
#   - adapt_payload 2→3튜플: 확장 meta + style 추출.
#   - 구버전 payload(style 없음, meta 3필드) → template=jeongtong 폴백(회귀 0).
#   - accent 해석(#RRGGBB 우선 → 템플릿 기본 → ink).
#   - render_template_header 의 _header_default 시퀀스가 기존 write() 제목-출력과 동일.
#   - 미지원 template → jeongtong 폴백(크래시 없음).
#
# win32com 미의존(adapter / template_headers 만 import) — hwp_com 은 끌어오지 않는다.
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from server.adapter import adapt_payload
from core.template_headers import (
    render_template_header,
    resolve_accent_rgb,
    _hex_to_rgb,
    starter_meta,
    token_values,
    resolve_form_path,
    generate_form_layout,
)


class _MockSession:
    """헤더 함수가 부르는 프리미티브 시퀀스를 기록(COM 없이 회귀 검증)."""

    base_pt = 11

    def __init__(self):
        self.calls = []

    def align_center(self):
        self.calls.append("AC")

    def align_left(self):
        self.calls.append("AL")

    def break_para(self):
        self.calls.append("BP")

    def text(self, t):
        self.calls.append(("T", t))

    def set_char_shape(self, pt=None, bold=None):
        self.calls.append(("CS", pt, bold))

    def table_begin(self, nrow=1, ncol=1, line_width=42000, col_widths=None):
        self.calls.append(("TB", nrow, ncol))

    def table_next_cell(self):
        self.calls.append("NC")

    def table_end(self):
        self.calls.append("TE")

    def set_char_size(self, pt=None):
        self.calls.append(("CSZ", pt))

    def header_begin(self, apply_type=0):
        self.calls.append(("HDR_BEGIN", apply_type))

    def region_end(self):
        self.calls.append("REGION_END")

    def insert_page_number(self):
        self.calls.append("PAGENUM")

    def texts(self):
        return [c[1] for c in self.calls if isinstance(c, tuple) and c[0] == "T"]

    def tables(self):
        return [(c[1], c[2]) for c in self.calls if isinstance(c, tuple) and c[0] == "TB"]


def run() -> int:
    fails = []

    def chk(cond, msg):
        if not cond:
            fails.append("  " + msg)

    # 1) 신규 payload — meta 확장 + style 추출
    new_payload = {
        "schema": "v2",
        "meta": {
            "title": "1학기 중간고사",
            "subject": "수학",
            "grade": "2학년",
            "schoolName": "대구중",
            "examDate": "2026-06-23",
            "totalScore": 100,
        },
        "style": {"template": "modern", "accentColor": "#1B2A4E", "columns": 2},
        "problems": [{"number": 1, "text": "문제"}],
    }
    env, meta, style = adapt_payload(new_payload)
    chk(style["template"] == "modern" and style["accentColor"] == "#1B2A4E"
        and style["columns"] == 2, f"style 추출: {style}")
    chk(style.get("margins") is None, f"margins 없으면 None: {style.get('margins')}")
    chk(meta["schoolName"] == "대구중", f"meta.schoolName: {meta.get('schoolName')}")
    chk(meta["totalScore"] == 100, f"meta.totalScore: {meta.get('totalScore')}")
    chk(meta["title"] == "1학기 중간고사", f"meta.title: {meta.get('title')}")
    chk(len(env["questions"]) == 1, f"envelope.questions: {env}")

    # 2) 구버전 payload — style 없음, meta 3필드 → 회귀 폴백
    legacy = {"meta": {"title": "T", "subject": "수학", "grade": ""}, "problems": []}
    env2, meta2, style2 = adapt_payload(legacy)
    chk(style2["template"] == "jeongtong", f"legacy template: {style2}")
    chk(style2["accentColor"] == "" and style2["columns"] == 1, f"legacy style: {style2}")
    chk(meta2["schoolName"] == "" and meta2["totalScore"] is None,
        f"legacy meta 확장 빈값: {meta2}")

    # 2c) style.margins 추출 — 유효 숫자 필드만, 잘못된 값 무시
    _, _, st_m = adapt_payload({
        "meta": {"title": "T", "subject": "수학", "grade": ""},
        "style": {"template": "jeongtong", "margins": {"top": 10, "bottom": 10, "left": 12, "right": 12, "bogus": "x"}},
        "problems": [],
    })
    chk(st_m["margins"] == {"top": 10, "bottom": 10, "left": 12, "right": 12},
        f"margins 추출: {st_m['margins']}")

    # 3) accent 해석
    chk(_hex_to_rgb("#1B2A4E") == (27, 42, 78), "hex→rgb")
    chk(_hex_to_rgb("bad") is None, "hex 불량 None")
    chk(resolve_accent_rgb("modern", "") == (27, 42, 78), "accent: 템플릿 기본 navy")
    chk(resolve_accent_rgb("workbook", "#FF0000") == (255, 0, 0), "accent: 명시 우선")
    chk(resolve_accent_rgb("", "") == (14, 14, 16), "accent: ink 폴백")

    # 4) _header_default 시퀀스 = 기존 write() 제목-출력과 동일(회귀 0)
    m = _MockSession()
    render_template_header(m, "jeongtong", {"title": "제목"}, (14, 14, 16))
    chk(m.calls == ["AC", ("T", "제목"), "BP", "AL", "BP"],
        f"jeongtong 기본 헤더 시퀀스: {m.calls}")

    # 5) 미지원 template → jeongtong 폴백(크래시 없음)
    m2 = _MockSession()
    render_template_header(m2, "unknown_tpl", {"title": "X"}, None)
    chk(m2.calls == ["AC", ("T", "X"), "BP", "AL", "BP"],
        f"미지원 template 폴백: {m2.calls}")

    # 6) 제목 없으면 헤더 무출력(빈 문서 회귀)
    m3 = _MockSession()
    render_template_header(m3, "jeongtong", {"title": ""}, None)
    chk(m3.calls == [], f"빈 제목 무출력: {m3.calls}")

    # 7) jeongtong 전체 헤더(시험지 정보 있음) → 표 3개 + 라벨/값/점수 렌더
    m4 = _MockSession()
    render_template_header(m4, "jeongtong", {
        "title": "1학기 중간고사", "subject": "수학", "grade": "2학년",
        "schoolName": "대구중", "examDate": "2026-06-23", "totalScore": 100,
    }, (14, 14, 16))
    tables = m4.tables()
    texts = m4.texts()
    chk(tables == [(1, 1), (2, 6), (1, 10), (1, 1)],
        f"jeongtong 표 구성(제목배너 1×1/정보 2×6/학생 1×10/유의 1×1): {tables}")
    chk("1학기 중간고사" in texts, "제목 배너")
    chk("대구중" in texts, "학교 값(정보표)")
    chk("반" in texts and "이름" in texts, "학생 라벨(반·이름)")
    chk("/ 100" in texts, "점수 max")
    chk(any(t.startswith("※") for t in texts), "유의사항 박스")

    # 8) jeongtong 정보 없음(gui/legacy) → 제목만(회귀 0, 표 0개)
    m5 = _MockSession()
    render_template_header(m5, "jeongtong", {"title": "제목만"}, None)
    chk(m5.tables() == [], f"정보 없으면 표 0개: {m5.tables()}")
    chk(m5.calls == ["AC", ("T", "제목만"), "BP", "AL", "BP"], f"제목만 시퀀스: {m5.calls}")

    # 9) 스타터 폼 meta — 모든 필드가 {{토큰}}
    sm = starter_meta("jeongtong")
    chk(sm["title"] == "{{제목}}" and sm["schoolName"] == "{{학교}}" and sm["totalScore"] == "{{배점}}",
        f"starter_meta 토큰: {sm}")

    # 9b) starter_meta 로 그린 jeongtong → 표에 토큰 텍스트(배점 토큰 포함)
    m6 = _MockSession()
    render_template_header(m6, "jeongtong", starter_meta("jeongtong"), (14, 14, 16))
    t6 = m6.texts()
    # 학교는 제목 아래 부제(값 토큰), 점수 칸은 파생 토큰 {{점수표기}}(변환 때 "/ 100"|빈값).
    chk("{{학교}}" in t6 and "{{점수표기}}" in t6 and "{{제목}}" in t6, f"토큰 렌더: {t6}")
    chk(m6.tables() == [(1, 1), (2, 6), (1, 10), (1, 1)], f"토큰 모드 표 구성: {m6.tables()}")

    # 10) token_values — 숫자/빈값/문자 매핑
    tv = token_values({"title": "T", "schoolName": "성광고", "totalScore": 100, "examiner": ""})
    chk(tv["제목"] == "T" and tv["학교"] == "성광고", f"token_values 문자: {tv}")
    chk(tv["배점"] == "100", f"token_values 숫자→문자: {tv['배점']}")
    chk(tv["출제자"] == "" and tv["학원명"] == "", f"token_values 빈값: {tv}")
    # 파생 토큰 점수표기 — 값 있으면 "/ 100", 없으면 ""(폼 잔여 기호 0)
    chk(tv["점수표기"] == "/ 100", f"token_values 점수표기: {tv['점수표기']}")
    chk(token_values({"totalScore": None})["점수표기"] == "", "점수표기 빈값")
    chk(token_values({})["점수표기"] == "", "점수표기 누락")

    # 11) resolve_form_path — 폼 파일 없으면 None(COM 헤더 폴백)
    chk(resolve_form_path("nonexistent_template_xyz") is None, "폼 없음 → None")

    # 12) generate_form_layout(jeongtong) — 페이지번호(꼬릿말 위치) + 본문 표 시퀀스.
    #     러닝 머릿말은 생략(B안, 사용자 결정 2026-06-23).
    m7 = _MockSession()
    generate_form_layout(m7, "jeongtong", starter_meta("jeongtong"), (14, 14, 16))
    seq = m7.calls
    chk(("HDR_BEGIN", 0) not in seq, f"러닝 머릿말 없음: {seq[:3]}")
    chk("PAGENUM" in seq, "페이지번호 삽입")
    # 페이지번호가 본문 표보다 먼저
    i_pn = seq.index("PAGENUM")
    i_tbl = next(i for i, c in enumerate(seq) if isinstance(c, tuple) and c[0] == "TB")
    chk(i_pn < i_tbl, f"순서 페이지번호<본문표: {i_pn},{i_tbl}")
    chk("{{제목}}" in m7.texts(), f"폼 제목 토큰 렌더: {m7.texts()}")
    chk(m7.tables() == [(1, 1), (2, 6), (1, 10), (1, 1)], f"폼 본문 표 구성: {m7.tables()}")

    if fails:
        print("FAIL test_template_headers:")
        print("\n".join(fails))
        return 1
    print("OK test_template_headers (adapt_payload 3-tuple / accent / 헤더 회귀)")
    return 0


def test_template_headers():
    assert run() == 0


if __name__ == "__main__":
    raise SystemExit(run())
