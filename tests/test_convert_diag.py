# -*- coding: utf-8 -*-
"""폼 채움 실패 → 기본 서식 폴백 시 diag 가 사실을 기록하는지 (COM 없음·API 0원).

적대리뷰 2026-08-10 실결함: diag 를 시도 **전에** 써서, 폴백이 나도 "폼=대수회…"로
거짓 보고 + rc=0 이라 부모가 stderr 를 안 읽어 사고가 무음화됐다. 폴백은 결과물이
통째로 달라지는 사건인데(대수회 폼 → 기본 서식) 웹에는 "성공"으로만 보이므로,
`form_fallback_error` 가 유일한 관측 채널이다 — 커넥터가 이 키를 보고 stderr 꼬리를
진단에 실어 웹 로그(Supabase)로 올린다.

실행: python tests/test_convert_diag.py
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import core.hwp_form_writer as hfw          # noqa: E402
import core.hwp_com_writer as hcw           # noqa: E402
from server import convert_cli              # noqa: E402

OUT = Path(tempfile.gettempdir()) / "_diag_fb.hwp"
DIAG = OUT.with_suffix(OUT.suffix + ".diag.json")
FAILED = []


def check(label, cond, detail=""):
    print(("  OK   " if cond else "  FAIL ") + label + ("" if cond else f" — {detail}"))
    if not cond:
        FAILED.append(label)


def run_case(form_raises: bool):
    for p in (OUT, DIAG):
        if p.exists():
            p.unlink()

    def _form(*a, **k):
        if form_raises:
            raise RuntimeError("(-2147417851, '서버에서 예외 오류가 발생했습니다.')")
        OUT.write_bytes(b"FORM")

    def _basic(*a, **k):
        OUT.write_bytes(b"BASIC")

    hfw.write_exam_to_form = _form           # convert_cli 가 함수 내부에서 import
    hcw.write_exam_to_hwp = _basic
    payload = {
        "header": "",
        "questions": [{"number": 1, "score": 3,
                       "contents": [{"type": "text", "value": "값은?"}],
                       "choices": [], "sub_questions": []}],
        "filename": "[경상여고][2][기하][25-2-중간][비상] (원본).pdf",
    }
    convert_cli._render_engine_envelope(payload, OUT)
    return json.loads(DIAG.read_text(encoding="utf-8")), OUT.read_bytes()


print("폼 성공 경로")
d, body = run_case(form_raises=False)
check("폼으로 렌더됨", body == b"FORM")
check("diag form = 폼 이름", "대수회" in d["form"], d["form"])
check("fallback_error 비어 있음", d["form_fallback_error"] == "", d["form_fallback_error"])

print("폼 실패 → 기본 서식 폴백")
d, body = run_case(form_raises=True)
check("기본 서식으로 렌더됨", body == b"BASIC")
check("diag form = (기본 서식)", d["form"] == "(기본 서식)", d["form"])
check("매칭됐던 폼은 form_matched 로 보존", "대수회" in d["form_matched"], d["form_matched"])
check("fallback_error 에 원인 기록",
      "2147417851" in d["form_fallback_error"], d["form_fallback_error"])
check("커넥터 보강 트리거 문자열 조건 일치",
      '"form_fallback_error": ""' not in json.dumps(d, ensure_ascii=False)
      and "form_fallback_error" in json.dumps(d, ensure_ascii=False))

print("전부 통과" if not FAILED else f"{len(FAILED)}건 FAIL")
sys.exit(1 if FAILED else 0)
