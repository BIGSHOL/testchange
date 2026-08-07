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

    # Vercel 은 배포마다 프리뷰 호스트명이 새로 생긴다 — 프로덕션 한 줄로는 부족.
    check("Vercel 프로덕션 허용",
          c._is_allowed_origin("https://hwp-convert-web.vercel.app"))
    check("Vercel 프리뷰(해시 붙은 호스트) 허용",
          c._is_allowed_origin("https://hwp-convert-web-abc123-sun.vercel.app"))

    # ⚠️ 와일드카드를 너무 넓게 열면 아무나 만든 vercel 사이트가 로컬 커넥터를 부른다.
    check("남의 vercel.app 은 거부",
          not c._is_allowed_origin("https://evil-site.vercel.app"))
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


def main() -> int:
    print("웹 ↔ 커넥터 계약 회귀 테스트\n")
    for fn in (test_envelope_discriminator, test_output_suffix, test_token_contract,
               test_allowed_origins, test_token_init_without_main,
               test_worker_python, test_health_fields, test_form_selection_from_filename):
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
