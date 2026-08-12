# -*- coding: utf-8 -*-
"""웹 변환 서비스 ↔ 로컬 HWP 커넥터 계약 회귀 테스트 (stdlib·API 0원·COM 없음).

2026-08-08 웹 E2E 를 살리며 잡은 계약들을 박제한다. 여기서 깨지면 **웹에서 변환
버튼을 눌렀을 때만** 드러나므로(로컬 exe 는 멀쩡) 자동 게이트가 특히 중요하다.

  A. payload 판별이 커넥터·convert_cli 한 곳(is_engine_envelope)에서만 이뤄질 것
  B. 엔진 봉투 → .hwp / mathgen → .hwpx (확장자가 렌더 품질을 좌우 — 합의 #12)
  C. 토큰 헤더 이름이 웹과 일치(X-Connector-Token) + CORS 로 허용될 것
  D. 워커 파이썬이 하드코딩이 아닐 것(PC 마다 경로가 다름)
  E. /health 가 웹이 읽는 필드(hwp)를 낼 것

실행: .venv\\Scripts\\python.exe tests/test_connector_contract.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FAILED: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  OK   {label}")
    else:
        FAILED.append(label)
        print(f"  FAIL {label}" + (f" — {detail}" if detail else ""))


def test_envelope_discriminator() -> None:
    print("A. payload 판별 (단일 출처)")
    from server.convert_cli import is_engine_envelope

    check("엔진 봉투 인식", is_engine_envelope({"header": "", "questions": [{"number": 1}]}))
    check("빈 questions 도 엔진 봉투", is_engine_envelope({"questions": []}))
    check("mathgen payload 는 아님",
          not is_engine_envelope({"problems": [{"number": 1}], "meta": {}}))
    check("dict 아님 방어", not is_engine_envelope([1, 2, 3]))
    check("questions 가 list 가 아니면 아님", not is_engine_envelope({"questions": "x"}))

    # 커넥터가 자기만의 판별을 다시 구현하지 않았는지(중복 = 조용한 어긋남).
    src = (ROOT / "server" / "connector.py").read_text(encoding="utf-8")
    check("커넥터가 is_engine_envelope 를 import 해서 씀",
          "is_engine_envelope" in src)
    check("커넥터에 중복 판별 없음",
          'isinstance(d.get("questions"), list)' not in src)


def test_output_suffix() -> None:
    print("B. 산출물 확장자")
    src = (ROOT / "server" / "connector.py").read_text(encoding="utf-8")
    check("엔진 봉투 → .hwp / mathgen → .hwpx",
          'suffix = ".hwp" if engine_env else ".hwpx"' in src)
    check("_run_convert_subprocess 가 suffix 를 받음",
          "def _run_convert_subprocess(payload_bytes: bytes, suffix: str" in src)


def test_token_contract() -> None:
    print("C. 연결 코드(토큰) 계약")
    import server.connector as c

    check("기본은 토큰 켬", c.REQUIRE_TOKEN is True)
    check("CORS 가 X-Connector-Token 허용",
          "X-Connector-Token" in (ROOT / "server" / "connector.py").read_text(encoding="utf-8"))

    tok = c._load_or_create_token()
    check("토큰 생성/로드", bool(tok), "빈 토큰")
    check("토큰 안정(재호출 동일)", tok == c._load_or_create_token())

    # 웹이 실제로 보내는 헤더 이름과 같은지 — 소스 대조(웹 repo 는 별도 리포라 문자열로).
    check("웹이 보내는 헤더명과 동일(X-Connector-Token)",
          'self.headers.get("X-Connector-Token")'
          in (ROOT / "server" / "connector.py").read_text(encoding="utf-8"))

    # env 로 끌 수 있어야 dev 가 막히지 않는다.
    old = os.environ.get("MATHGEN_HWP_NO_TOKEN")
    try:
        os.environ["MATHGEN_HWP_NO_TOKEN"] = "1"
        import importlib
        importlib.reload(c)
        check("MATHGEN_HWP_NO_TOKEN=1 이면 토큰 끔", c.REQUIRE_TOKEN is False)
    finally:
        if old is None:
            os.environ.pop("MATHGEN_HWP_NO_TOKEN", None)
        else:
            os.environ["MATHGEN_HWP_NO_TOKEN"] = old
        import importlib
        importlib.reload(c)


def test_allowed_origins() -> None:
    """⭐ 배포 origin 허용 — 이게 막히면 배포 즉시 변환 100% 실패한다.

    공개 HTTPS → 127.0.0.1 은 Chrome PNA preflight 대상이라, 불허 origin 이면
    do_OPTIONS 가 허용 헤더를 안 붙여 **/health 요청조차 전송되지 않고** 웹은 영영
    "HWP 도우미 없음" 을 표시한다(2026-08-08 감사).
    """
    print("G. 허용 origin (배포 도메인)")
    import importlib
    import server.connector as c
    importlib.reload(c)

    check("로컬 dev(vite 임의 포트) 허용", c._is_allowed_origin("http://localhost:5173"))
    check("127.0.0.1 임의 포트 허용", c._is_allowed_origin("http://127.0.0.1:3000"))
    check("기존 프로덕션 허용", c._is_allowed_origin("https://mathgen.para-x.co.kr"))

    # ⭐ 아래 4개는 **실제 배포에서 관측된 호스트명**이다(2026-08-08). Vercel 은 원본
    # 배포 URL 에서 프로젝트명을 잘라 쓰므로("web" 탈락) 별칭만 보고 규칙을 짜면 막힌다.
    check("Vercel 프로덕션 별칭 허용",
          c._is_allowed_origin("https://hwp-convert-web.vercel.app"))
    check("Vercel 팀 별칭 허용",
          c._is_allowed_origin(
              "https://hwp-convert-web-jaesungs-projects-404a3b31.vercel.app"))
    check("Vercel 브랜치 별칭 허용",
          c._is_allowed_origin(
              "https://hwp-convert-web-bigshol-jaesungs-projects-404a3b31.vercel.app"))
    check("Vercel 원본 배포 URL(프로젝트명 잘림) 허용",
          c._is_allowed_origin(
              "https://hwp-convert-glo4u6n9r-jaesungs-projects-404a3b31.vercel.app"))

    # ⚠️ 와일드카드를 너무 넓게 열면 아무나 만든 vercel 사이트가 로컬 커넥터를 부른다.
    check("남의 vercel.app 은 거부",
          not c._is_allowed_origin("https://evil-site.vercel.app"))
    check("접두사만 비슷한 도메인 거부",
          not c._is_allowed_origin("https://hwp-converter.vercel.app"))
    check("유사 도메인 거부",
          not c._is_allowed_origin("https://hwp-convert-web.vercel.app.evil.com"))
    check("http 공개 origin 거부", not c._is_allowed_origin("http://example.com"))
    check("빈 origin 거부", not c._is_allowed_origin(""))

    # env 로 커스텀 도메인 주입 — exe 재빌드 없이 도메인을 바꿀 수 있어야 한다.
    old = os.environ.get("MATHGEN_HWP_ORIGINS")
    try:
        os.environ["MATHGEN_HWP_ORIGINS"] = "https://exam.example.com, https://b.example.com"
        check("env 주입 origin 허용", c._is_allowed_origin("https://exam.example.com"))
        check("env 주입 2번째도 허용", c._is_allowed_origin("https://b.example.com"))
        check("env 에 없는 건 여전히 거부", not c._is_allowed_origin("https://c.example.com"))
    finally:
        if old is None:
            os.environ.pop("MATHGEN_HWP_ORIGINS", None)
        else:
            os.environ["MATHGEN_HWP_ORIGINS"] = old


def test_token_init_without_main() -> None:
    """⭐ 트레이 앱(agent.py)은 connector.main() 을 안 거친다 — 그래도 토큰이 살아야 한다.

    초기화를 main() 에만 두면 배포 exe 에서 EXPECTED_TOKEN 이 빈 값이라 검사가 통째로
    무효가 된다(웹은 코드를 요구하는데 커넥터는 아무 값이나 통과). 2026-08-08 감사 발견.
    """
    print("H. main() 없이도 토큰 유효 (배포 트레이 앱 경로)")
    import importlib
    import server.connector as c
    importlib.reload(c)  # main() 을 부르지 않은 갓 임포트한 상태

    check("임포트 직후 EXPECTED_TOKEN 은 비어 있음(지연 초기화)", c.EXPECTED_TOKEN == "")
    tok = c.ensure_token()
    check("ensure_token() 이 토큰을 만든다", bool(tok))
    check("모듈 전역에 실린다", c.EXPECTED_TOKEN == tok)
    check("멱등", c.ensure_token() == tok)

    src = (ROOT / "agent.py").read_text(encoding="utf-8")
    check("agent.py 가 ensure_token 을 호출", "connector.ensure_token()" in src)
    check("agent.py 가 연결 코드를 사용자에게 보여줌", "연결 코드" in src)
    check("agent.py SITE_URL 이 env 로 바꿀 수 있음", "MATHGEN_HWP_SITE" in src)


def test_worker_python() -> None:
    print("D. COM 워커 인터프리터 (하드코딩 금지)")
    import server.connector as c

    # 주석/문서 문구는 제외하고 **실행되는 코드 줄**만 검사(설명에 'Python311' 이
    # 남아 있는 건 정상 — 과거 함정을 기록해 둔 것).
    code = "\n".join(
        line for line in (ROOT / "server" / "connector.py").read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )
    check("Python 절대경로 하드코딩 없음",
          "Programs\\Python" not in code, "인터프리터 경로가 코드에 박혀 있음")
    py = c._worker_python()
    check("워커 파이썬이 실재", Path(py).exists(), py)
    check("엔진 .venv 우선", ".venv" in py or py == sys.executable, py)


def test_health_fields() -> None:
    print("E. /health 필드 (웹이 읽는 이름)")
    src = (ROOT / "server" / "connector.py").read_text(encoding="utf-8")
    for field in ('"hwp_com"', '"hwp"', '"token"', '"version"'):
        check(f"/health 에 {field}", field in src)


def test_form_selection_from_filename() -> None:
    print("F. 파일명 → 폼/머리말 (웹은 filename 만 보낸다)")
    from core.form_registry import parse_filename, resolve_form

    info = parse_filename("[경원고][2][기하][25-2-중간][신사고].pdf")
    check("고2 기하 파싱", info.get("valid") and info.get("학년") == "고2", str(info))
    form = resolve_form("[경원고][2][기하][25-2-중간][신사고].pdf")
    check("고2 선택과목 폼 매칭", bool(form) and "고2 선택과목" in str(form), str(form))

    mid = parse_filename("[강동중][1][25-1-기말] (원본).pdf")
    check("중1 파싱(과목 자동 '수학')",
          mid.get("valid") and mid.get("학년") == "중1" and mid.get("과목") == "수학",
          str(mid))

    # 규칙 밖 파일명은 **차단이 아니라** 기본 서식(폼 None) — 2026-06-16 사용자 합의.
    check("규칙 밖 파일명 = 폼 None(차단 아님)", resolve_form("random.pdf") is None)
    check("규칙 밖 파일명 = header_values 없음",
          parse_filename("random.pdf").get("valid") is False)


def test_web_figures_note_only() -> None:
    print("I. 웹 그림 = 안내문구 고정 (그림 실삽입은 내부 개발 전용 — 사용자 2026-08-10)")
    # 신설 그림 파이프라인(figure_crop 검출 + figure_embed 네이티브 삽입)은 미완성이라
    # 프로덕션(웹·exe) 노출 금지. 웹 경로가 render_figures=True 로 바뀌면 여기서 잡는다.
    src = (ROOT / "server" / "convert_cli.py").read_text(encoding="utf-8")
    check("폼 렌더가 render_figures=False", "render_figures=False" in src)
    check("웹 경로에 render_figures=True 없음", "render_figures=True" not in src)
    check("파서 전에 figure → 안내문구(resolve_figures) 호출",
          src.index("resolve_figures(envelope)") < src.index("parse_ocr_response("))
    con = (ROOT / "server" / "connector.py").read_text(encoding="utf-8")
    check("커넥터가 render_figures 를 덮어쓰지 않음", "render_figures" not in con)


def test_output_fallback() -> None:
    print("J. 산출물 확장자 폴백 — .hwp 굽기 실패해도 사용자는 파일을 받는다")
    # ⭐ 2026-08-10 실사고: 폼 채움이 HWP 크래시(-2147417851)로 죽고, 기본 서식 렌더는
    # 성공했는데 최종 .hwp 굽기가 실패해 .hwpx 로 떨어졌다. 그런데 요청 경로(.hwp)만
    # 확인하던 탓에 "출력 파일이 없습니다"(exit 3) → **500, 사용자는 아무것도 못 받음.**
    import tempfile
    from server.convert_cli import resolve_output

    d = Path(tempfile.mkdtemp())
    req = d / "out.hwp"
    check("아무것도 없으면 None", resolve_output(None, req) is None)
    (d / "out.hwpx").write_bytes(b"x" * 16)
    got = resolve_output(None, req)
    check("`.hwpx` 폴백을 찾아낸다", got is not None and got.name == "out.hwpx", str(got))
    (d / "out.__work.hwpx").write_bytes(b"x" * 16)
    req.write_bytes(b"y" * 16)
    got = resolve_output(None, req)
    check("요청 확장자가 있으면 그쪽 우선", got is not None and got.name == "out.hwp", str(got))
    empty = d / "empty.hwp"
    empty.write_bytes(b"")
    check("0바이트는 산출물로 안 침", resolve_output(empty, req).name == "out.hwp")

    src = (ROOT / "server" / "connector.py").read_text(encoding="utf-8")
    check("커넥터가 (bytes, 확장자) 를 돌려준다",
          "return produced.read_bytes(), produced.suffix" in src)
    check("커넥터가 폴백 확장자를 응답 헤더에 반영",
          "data, suffix = _run_convert_subprocess(body, suffix)" in src)
    check("폴백을 진단에 남긴다(성공으로 위장 금지)", '"output_suffix"' in src)

    cli = (ROOT / "server" / "convert_cli.py").read_text(encoding="utf-8")
    check("convert_cli 가 실제 산출물로 성공 판정", "resolve_output(produced, out_path)" in cli)
    check("폼 크래시 뒤 고아 HWP 정리", "reap_hwp(hwp_pids() - hwp_before)" in cli)

    # ⭐ 부모가 산출물을 **추측하지 않는다** — HWP 가 SaveAs 도중 죽으면 잘린 .hwp 가
    # 남는데, 요청 확장자를 먼저 집으면 그 깨진 파일을 성공으로 내보낸다(적대리뷰).
    check("자식이 실제 산출물명을 진단에 박는다", "_record_output(out_path, actual)" in cli)
    check("부모가 그 이름을 최우선으로 믿는다",
          'get("output")' in src and "cands = [target.with_name(declared)]" in src)
    # 재시도가 커넥터 타임아웃을 넘겨 결과를 통째로 날리면 안 된다.
    check("폼 재시도에 시간 예산 가드", "_FORM_RETRY_BUDGET_S" in cli)
    # 사용자가 변환 중 띄운 한글을 죽이지 않는다.
    check("COM 크래시일 때만 프로세스 정리", "if _is_com_crash(e):" in cli)


def test_process_reaping() -> None:
    print("K. 프로세스 정리 안전장치")
    from core.hwp_com import hwp_pids, reap_hwp

    pids = hwp_pids()
    check("hwp_pids 는 정수 집합", isinstance(pids, set)
          and all(isinstance(p, int) for p in pids), str(pids))
    check("빈 목록이면 0개 정리", reap_hwp(set()) == 0)
    # 존재하지 않는 PID → taskkill 이 실패 → **정리했다고 세면 안 된다**(허위 로그 방지).
    check("죽이지 못한 건 안 센다", reap_hwp({999999}) == 0)

    core_src = (ROOT / "core" / "hwp_com.py").read_text(encoding="utf-8")
    check("이미지명을 대조해 엉뚱한 PID 를 안 잡는다",
          'row[0].strip().lower() == "hwp.exe"' in core_src)
    check("taskkill 성공(rc 0)만 집계", "if r.returncode == 0:" in core_src)
    conn_src = (ROOT / "server" / "connector.py").read_text(encoding="utf-8")
    check("커넥터가 엔진 구현을 재사용(사본 금지)",
          "from core.hwp_com import hwp_pids as _core_pids" in conn_src)


def test_plain_two_column() -> None:
    """L. '폼 없이 2단'(웹 layout 플래그) — 켜야만 켜지고, 켜면 폼을 안 탄다."""
    print("L. 폼 없이 2단(plain2)")
    from core.plain_render import plain_header_meta
    from server.convert_cli import wants_plain_layout

    # 플래그가 없으면 **기존 동작 그대로** — 폼 경로에 회귀를 만들지 않는다.
    check("플래그 없으면 꺼짐", not wants_plain_layout({"questions": []}))
    check("빈 layout 은 꺼짐", not wants_plain_layout({"layout": ""}))
    check("모르는 layout 은 꺼짐", not wants_plain_layout({"layout": "elegant"}))
    check("dict 아님 방어", not wants_plain_layout(None))
    for v in ("plain2", "PLAIN2", " plain2col ", "plain-2col", "2col", "2단"):
        check(f"layout={v!r} 이면 켜짐", wants_plain_layout({"layout": v}))
    check("noForm 플래그도 켜짐", wants_plain_layout({"noForm": True}))

    # 켜지면 폼 매칭을 아예 건너뛴다(대수회 슬롯 채우기 금지) — 소스로 잠금.
    src = (ROOT / "server" / "convert_cli.py").read_text(encoding="utf-8")
    check("plain 이면 form_path=None",
          "form_path = None if plain else (resolve_form(filename) if filename else None)" in src)
    check("plain 은 write_exam_to_form 을 안 탄다", "if form_path:" in src)
    check("진단에 서식이 남는다", '"(2단 기본 서식)"' in src)

    # ⚠️ 렌더 구현은 **웹·exe 공용 한 곳**(core/plain_render). 사본을 만들면 "웹과 exe
    # 결과가 다르다" 가 된다(_write_tail/_put_tail 이원화 전례).
    core_src = (ROOT / "core" / "plain_render.py").read_text(encoding="utf-8")
    check("2단 + 평문 번호로 렌더",
          "columns=2," in core_src and "use_endnote=False," in core_src)
    check("커넥터가 공용 구현을 씀",
          "from core.plain_render import render_plain_2col" in src)
    gui_src = (ROOT / "gui" / "main_window.py").read_text(encoding="utf-8")
    check("exe GUI 도 같은 공용 구현을 씀", "render_plain_2col(" in gui_src)
    check("GUI 에 렌더 인자 사본 없음",
          "use_endnote=False" not in gui_src)

    # 머리말 토큰값 — 파일명 규칙에서만 채우고, 규칙 미일치면 빈 dict(차단 아님).
    info = {"valid": True, "학교": "강동중", "학년": "중1", "학기": "1",
            "구분": "기말", "과목": "수학"}
    meta = plain_header_meta(info)
    check("제목 조립", meta.get("title") == "강동중 1학년 1학기 기말고사", str(meta))
    check("과목 전달", meta.get("subject") == "수학")
    check("규칙 미일치면 빈 값", plain_header_meta({"valid": False}) == {})
    check("info 가 None 이어도 안전", plain_header_meta(None) == {})

    # 바탕 템플릿은 forms/ **하위 폴더** — 대수회 폼 드롭다운(비재귀 glob)에 안 섞인다.
    from core.form_registry import list_forms, plain_form_path

    tpl = plain_form_path()
    check("2단 바탕 템플릿 번들됨", bool(tpl) and Path(tpl).exists(), str(tpl))
    check("대수회 폼 목록에 안 섞임",
          tpl is None or all(Path(f.path) != Path(tpl) for f in list_forms()))


def main() -> int:
    print("웹 ↔ 커넥터 계약 회귀 테스트\n")
    for fn in (test_envelope_discriminator, test_output_suffix, test_token_contract,
               test_allowed_origins, test_token_init_without_main,
               test_worker_python, test_health_fields, test_form_selection_from_filename,
               test_web_figures_note_only, test_output_fallback, test_process_reaping,
               test_plain_two_column):
        fn()
        print()
    if FAILED:
        print(f"{len(FAILED)}건 FAIL:")
        for f in FAILED:
            print(f"  - {f}")
        return 1
    print("전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
