# -*- coding: utf-8 -*-
"""Math-Gen 로컬 HWP 커넥터 — 웹(127.0.0.1) → COM 변환 → .hwpx.

  GET  /health        커넥터/엔진 감지 (한글 안 켬 — 레지스트리 탐지)
  POST /convert-json  payload → .hwp/.hwpx octet-stream (COM subprocess 격리)
  OPTIONS             CORS preflight

payload 두 종류(convert_cli 가 분기):
  - ``{"questions":[…],"filename"}``  시험지 한글화 웹 → 대수회 폼 → **.hwp**
  - ``{"problems":[…],"meta","style"}``  mathgen 웹 → adapt_payload → .hwpx

CORS 는 모든 로컬 origin + ALLOWED_ORIGINS(공개 HTTPS). 페어링 토큰 기본 **켬**
(``--no-token`` 또는 ``MATHGEN_HWP_NO_TOKEN=1`` 로 끔).
COM-only(write_exam_to_form/write_exam_to_hwp). 동기 응답(웹이 blob을 직접 await).
COM 자식 인터프리터는 ``_worker_python()`` 이 찾는다(엔진 .venv 우선 — 하드코딩 금지).

실행: python -m server.connector [--host 127.0.0.1] [--port 8765] [--no-token]
Python 3.11(pywin32) 필수.
"""
import os
import sys
import re
import csv
import json
import secrets
import argparse
import threading
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ENGINE_ROOT = Path(__file__).resolve().parent.parent
# ⚠️ 도우미를 다시 배포할 때마다 올린다 — `/health` 의 version 이 **사용자 PC 에서
# 어느 빌드가 도는지 확인하는 유일한 수단**이다(exe 를 갈아끼웠는지 원격에서 알 길이
# 없어 2026-08-10 경상여고 사고 재테스트 때 문제가 됐다).
#
# ⭐ 이 값을 올리면 **웹의 `src/lib/connector.ts` MIN_CONNECTOR_VERSION 도 같이 올린다**
# (mathg-gen). 웹은 그 상수보다 낮은 도우미에만 "업데이트 있습니다" 배너를 띄우므로,
# 여기만 올리면 낡은 도우미를 쓰는 사용자에게 **영영 알림이 안 간다** — 고쳐 놓고도
# 사람이 일일이 "새로 받으세요" 라고 말해야 했던 게 2026-08-10 사고의 실제 경로다.
# 회귀: 웹 `npm run gate:connver`(웹 요구 ≤ 여기 VERSION 을 대조).
VERSION = "1.2.0"   # 2026-08-20: 웹 그림 렌더(renderFigures — SVG 엔진 도형 삽입)
# ⭐ 360초 — 실측 렌더가 2~4분(오성중·왕선중 2026-08-09)이라 180초는 3분 넘는
# 시험지를 **구조적으로 100% 실패**시키고(살해 후 같은 payload 재시도 → 또 180초
# 소모 → 500) 총 6분+CPU 를 낭비했다. env 로 조정 가능.
CONVERT_TIMEOUT_S = int(os.environ.get("MATHGEN_HWP_TIMEOUT", "360"))

# 동시 변환 잠금 — HWP COM 은 1건씩(여러 탭/브라우저 동시 요청은 409).
_CONVERT_LOCK = threading.Lock()
ALLOWED_ORIGINS = {
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://mathgen.para-x.co.kr",  # 프로덕션 — 공개 HTTPS origin (PNA preflight 동반)
}

# dev 의 vite 는 빈 포트를 동적으로 잡으므로(3000 점유 시 3001/3002…) 포트 하드코딩이
# 깨진다. 커넥터는 127.0.0.1 에만 listen 하므로 *모든 로컬 origin*(localhost/127.0.0.1
# 임의 포트)은 안전하게 허용한다. 공개 origin 은 위 ALLOWED_ORIGINS 로만.
_LOCAL_ORIGIN_RE = re.compile(r"^http://(?:localhost|127\.0\.0\.1)(?::\d+)?$")

# ⭐ **Vercel 배포 origin.** 하드코딩만 두면 배포하는 순간 변환이 100% 막힌다 —
# 브라우저가 공개 HTTPS → 127.0.0.1 호출에 PNA preflight 를 요구하는데, 불허 origin 엔
# do_OPTIONS 가 허용 헤더를 안 붙여 **/health 요청조차 전송되지 않고** 웹은 영영
# "HWP 도우미 없음" 을 표시한다. 게다가 Vercel 은 배포마다 프리뷰 호스트명이 새로
# 생겨(``<project>-<hash>-<scope>.vercel.app``) 도메인 한 줄 추가로는 부족하다.
#
# 그래서 두 갈래로 연다:
#   1) ``MATHGEN_HWP_ORIGINS`` 환경변수(쉼표 구분) — 커스텀 도메인용. exe 재빌드 불필요.
#   2) 프로젝트 접두사로 한정한 ``*.vercel.app`` 패턴 — 프리뷰·프로덕션 자동 허용.
# ⚠️ 와일드카드를 ``*.vercel.app`` 전체로 열면 **아무나 만든 vercel 사이트**가 로컬
# 커넥터를 부를 수 있다. 반드시 프로젝트 접두사로 좁힌다(+ 연결 코드가 2차 방어).
#
# ⚠️ 접두사가 ``hwp-convert-web`` 이 아니라 ``hwp-convert`` 인 이유(2026-08-08 실측):
# Vercel 이 배포 호스트명을 만들 때 **프로젝트명을 잘라 쓴다.** 실제 배포에서
#   별칭   https://hwp-convert-web.vercel.app                        (사용자가 쓰는 주소)
#   원본   https://hwp-convert-glo4u6n9r-jaesungs-projects-….vercel.app  ← "web" 이 잘림
# 이 나왔다. 별칭만 보고 ``hwp-convert-web`` 으로 좁히면 원본 URL·프리뷰 배포가 전부
# 막힌다. 잔여 위험(누가 ``hwp-convert-*`` 이름으로 프로젝트를 만드는 경우)은 연결
# 코드가 막는다.
_VERCEL_PROJECT = os.environ.get("MATHGEN_HWP_VERCEL_PROJECT", "hwp-convert").strip()
_VERCEL_ORIGIN_RE = re.compile(
    r"^https://" + re.escape(_VERCEL_PROJECT) + r"(?:-[a-z0-9-]+)?\.vercel\.app$"
)


def _env_origins() -> set:
    raw = os.environ.get("MATHGEN_HWP_ORIGINS", "")
    return {o.strip().rstrip("/") for o in raw.split(",") if o.strip()}


def _is_allowed_origin(origin) -> bool:
    if not origin:
        return False
    o = origin.rstrip("/")
    return (
        o in ALLOWED_ORIGINS
        or o in _env_origins()
        or bool(_LOCAL_ORIGIN_RE.match(o))
        or bool(_VERCEL_ORIGIN_RE.match(o))
    )

# ⭐ 페어링 토큰 — 커넥터는 127.0.0.1 에만 listen 하지만, **로컬의 아무 페이지나**
# (사용자가 방문한 악성 사이트 포함) 커넥터를 부를 수 있다. 토큰은 그 시나리오를 막는다:
# 커넥터가 첫 실행 때 랜덤 토큰을 만들어 사용자 폴더에 두고, 사용자가 그 값을 웹에
# 붙여넣어야 변환이 된다(토큰을 모르는 사이트는 못 부름).
#
# ``MATHGEN_HWP_NO_TOKEN=1`` 이면 끈다(dev/로컬 디버깅용 — start-connector-hwp.bat).
TOKEN_PATH = Path(
    os.environ.get("LOCALAPPDATA") or Path.home()
) / "mathgen-connector" / "token.txt"
REQUIRE_TOKEN = os.environ.get("MATHGEN_HWP_NO_TOKEN", "") != "1"
EXPECTED_TOKEN = ""


def _load_or_create_token() -> str:
    """페어링 토큰을 읽거나(없으면) 만든다. 실패해도 변환을 막지 않는다."""
    try:
        if TOKEN_PATH.exists():
            tok = TOKEN_PATH.read_text(encoding="utf-8").strip()
            if tok:
                return tok
        tok = secrets.token_hex(4).upper()  # 8자 — 사람이 옮겨 적을 수 있는 길이
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(tok, encoding="utf-8")
        return tok
    except Exception:  # noqa: BLE001 — 토큰 파일 실패 시 무토큰으로 동작(기능 우선)
        return ""


def ensure_token() -> str:
    """토큰을 준비하고 ``EXPECTED_TOKEN`` 에 실어 돌려준다(멱등).

    ⚠️ **`main()` 안에서만 초기화하면 안 된다.** 배포 트레이 앱(`agent.py`)은
    `main()` 을 거치지 않고 `ThreadingHTTPServer(..., Handler)` 를 직접 띄우므로,
    초기화를 main 에 두면 exe 에서 `EXPECTED_TOKEN` 이 빈 문자열로 남아 **토큰 검사가
    통째로 무효**가 된다(웹은 코드를 요구하는데 커넥터는 아무 값이나 통과 — 실측 확인).
    그래서 서버를 어떤 경로로 띄우든 이 함수를 부르게 하고, 안전망으로 요청 처리
    시점에도 한 번 더 확인한다.
    """
    global EXPECTED_TOKEN, REQUIRE_TOKEN
    if not REQUIRE_TOKEN:
        return ""
    if not EXPECTED_TOKEN:
        EXPECTED_TOKEN = _load_or_create_token()
        if not EXPECTED_TOKEN:
            REQUIRE_TOKEN = False  # 토큰 파일 실패 — 기능을 막지는 않는다
    return EXPECTED_TOKEN

_convert_lock = threading.Lock()  # 한글 COM 단일 인스턴스 직렬화
_last_diag = {"v": ""}   # 마지막 변환의 진단(어떤 폼으로 렌더됐나). 쓰기·읽기 모두 락 안에서만.


def _worker_python() -> str:
    """COM 자식(convert_cli)을 돌릴 파이썬. **하드코딩 금지 — PC 마다 다르다.**

    과거엔 Python311 절대경로가 박혀 있어 그 경로가 없는 PC 에선 변환이 통째로
    실패했다(2026-08-08 실측). 필요한 건 버전이 아니라 **pywin32 가 되는 파이썬**이므로
    엔진 ``.venv`` 를 1순위로 찾는다(CLAUDE.md 의 검증 명령이 쓰는 그 인터프리터).

    우선순위: ``MATHGEN_HWP_PYTHON`` env → 엔진 .venv → 현재 인터프리터.
    """
    env = os.environ.get("MATHGEN_HWP_PYTHON", "").strip()
    if env and Path(env).exists():
        return env
    venv = ENGINE_ROOT / ".venv" / "Scripts" / "python.exe"
    if venv.exists():
        return str(venv)
    return sys.executable


class ConvertError(Exception):
    pass


def _detect_hwp_installed() -> bool:
    """한글 COM 등록 여부 — 레지스트리만(COM 객체 미생성 → 한글이 켜지지 않음)."""
    try:
        import winreg
    except Exception:
        return False
    for sub in ("HWPFrame.HwpObject", "HWPFrame.HwpObject.1"):
        try:
            key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, sub)
            key.Close()
            return True
        except OSError:
            continue
    return False


def _detect_hwp_version() -> str:
    """설치된 한글 버전 힌트 — **COM 을 만들지 않고** 레지스트리만 읽는다.

    ⭐ 왜: 사용자 PC 마다 한글 버전이 다르고(2020·2024…), COM 크래시가 버전 의존인지
    판단할 근거가 지금까지 없었다(2026-08-10 폼 채움 -2147417851 사고). `LocalServer32`
    경로에 ``Hnc\\Office 2020\\HOffice110`` 처럼 버전이 박혀 있어 그대로 실마리가 된다.
    실패해도 빈 문자열 — 진단용이라 변환에 영향 없다.
    """
    try:
        import winreg
    except Exception:  # noqa: BLE001
        return ""
    # ⚠️ 한글은 **32비트 COM 서버**라 CLSID 가 WOW6432Node 뷰에 등록된다 — 64비트
    # 파이썬에서 기본 뷰만 보면 조용히 빈 값이 나온다(실측: 이 PC 한글 2020).
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,
                            r"HWPFrame.HwpObject\CLSID") as k:
            clsid, _ = winreg.QueryValueEx(k, "")
    except OSError:
        return ""
    path = ""
    for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY, 0):
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,
                                rf"CLSID\{clsid}\LocalServer32", 0,
                                winreg.KEY_READ | view) as k:
                path, _ = winreg.QueryValueEx(k, "")
            if path:
                break
        except OSError:
            continue
    if not path:
        return ""
    path = str(path or "").strip().strip('"')
    m = re.search(r"Office\s*(\d{4})", path, re.I)
    if m:
        return f"한글 {m.group(1)}"
    m = re.search(r"HOffice(\d+)", path, re.I)
    return f"HOffice{m.group(1)}" if m else path[:120]


def _hwp_pids() -> set:
    """현재 떠 있는 Hwp.exe PID 집합 — 엔진 `core.hwp_com.hwp_pids` 와 **같은 구현**.

    ⚠️ 사본을 두지 않는다(적대리뷰 2026-08-10: 파서가 갈려 엉뚱한 PID 를 죽일 위험).
    엔진 import 가 안 되는 환경(부분 배포)에서는 아래 자체 구현으로 폴백한다.
    """
    try:
        from core.hwp_com import hwp_pids as _core_pids
        return _core_pids()
    except Exception:  # noqa: BLE001 — 엔진 미탑재 환경 폴백
        pass
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Hwp.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except Exception:
        return set()
    pids = set()
    for line in out.splitlines():
        try:
            row = next(csv.reader([line]))
        except Exception:
            continue
        if len(row) >= 2 and row[0].lower() == "hwp.exe":
            try:
                pids.add(int(row[1]))
            except ValueError:
                pass
    return pids


def _reap(pids) -> None:
    """주어진 PID의 Hwp.exe 강제 종료 (이번 변환이 띄운 고아만)."""
    for pid in pids:
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True, timeout=10)
        except Exception:
            pass


def _run_convert_subprocess(payload_bytes: bytes, suffix: str = ".hwpx") -> tuple:
    """payload JSON bytes → convert_cli subprocess → ``(bytes, 실제 확장자)``.

    ⚠️ 반환 확장자가 요청과 다를 수 있다 — HWP 가 크래시하면 최종 ``.hwp`` 굽기가
    실패하고 writer 가 ``.hwpx`` 로 떨어뜨린다. 그 경우에도 **파일은 온전하므로
    그대로 내보낸다**(전달 안 하면 사용자는 500 만 받는다 — 2026-08-10 실사고).

    ``suffix`` 는 산출물 확장자. 엔진 봉투(시험지 한글화 웹)는 **.hwp** 로 굽는다 —
    폼 바탕쪽 2단 가운데 구분선이 .hwpx 로는 안 그려지기 때문(CLAUDE 합의 #12).
    mathgen 경로는 종전대로 .hwpx.

    엔진의 HwpSession.quit() 이 간헐적으로 실패해 고아 Hwp.exe 가 남는다
    (hwp_com.py:268 문서화). 변환 전후 Hwp.exe PID 를 비교해 *이번 변환이 띄운*
    인스턴스만 정리한다 — 사용자가 열어둔 문서·기존 인스턴스는 보존(전체 taskkill 금지).
    """
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / f"out{suffix}"
        inp = Path(td) / "in.json"
        inp.write_bytes(payload_bytes)
        # 배포본(frozen exe)은 자기 자신을 --convert-worker 로 재호출(번들 Python 사용).
        # dev 는 _worker_python() -m server.convert_cli. payload 는 stdin 대신 --in 파일로 —
        # windowed exe 는 sys.stdin 이 None 일 수 있어 파일 경유가 안전.
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--convert-worker",
                   "--in", str(inp), "--out", str(out)]
            cwd = None
        else:
            cmd = [_worker_python(), "-m", "server.convert_cli",
                   "--in", str(inp), "--out", str(out)]
            cwd = str(ENGINE_ROOT)
        target = out
        # 한글 COM 은 SaveAs/Quit 가 간헐적으로 실패한다(hwp_com.py:268 문서화 —
        # AttributeError HwpObject.SaveAs 등). 거의 항상 재시도로 회복하므로 1회 재시도.
        import time as _t
        last = "변환 실패"
        for _attempt in range(2):
            before = _hwp_pids()
            timed_out = False
            proc = None
            try:
                proc = subprocess.run(
                    cmd, cwd=cwd, capture_output=True, timeout=CONVERT_TIMEOUT_S,
                )
            except subprocess.TimeoutExpired:
                timed_out = True
            finally:
                _reap(_hwp_pids() - before)  # 이번 시도 고아만 정리
            produced = None
            if not timed_out and proc is not None and proc.returncode == 0:
                # ⭐ 자식이 진단에 박아 준 **실제 산출물명을 최우선**으로 믿는다.
                # 부모가 스스로 찾으면 규칙이 어긋나 사고가 난다: HWP 가 SaveAs 도중
                # 죽으면 잘린 `out.hwp` 가 남는데, 요청 확장자를 먼저 집으면 그
                # 깨진 파일을 성공으로 내보낸다(적대리뷰 2026-08-10).
                declared = ""
                try:
                    _dp = target.with_suffix(target.suffix + ".diag.json")
                    if _dp.exists():
                        declared = str(json.loads(
                            _dp.read_text(encoding="utf-8")).get("output") or "")
                except Exception:  # noqa: BLE001
                    declared = ""
                cands = [target.with_name(declared)] if declared else []
                cands += [target, target.with_suffix(".hwpx"),
                          target.with_name(target.stem + ".__work.hwpx")]
                for _c in cands:
                    try:
                        if _c.exists() and _c.stat().st_size > 0:
                            produced = _c
                            break
                    except OSError:
                        pass
            if produced is not None:
                # 진단 사이드카(있으면) — 부모가 응답 헤더로 웹에 넘긴다.
                diag = target.with_suffix(target.suffix + ".diag.json")
                try:
                    _last_diag["v"] = diag.read_text(encoding="utf-8") if diag.exists() else ""
                except Exception:  # noqa: BLE001
                    _last_diag["v"] = ""
                # ⭐ 한글 버전을 **매 변환 진단에** 싣는다 — COM 크래시가 버전 의존인지
                # 판단할 근거가 지금까지 없어 사용자에게 매번 물어봐야 했다(2026-08-10).
                try:
                    _d0 = json.loads(_last_diag["v"] or "{}")
                    _d0["hwp_version"] = _detect_hwp_version()
                    _d0["connector"] = VERSION
                    _last_diag["v"] = json.dumps(_d0, ensure_ascii=False)
                except Exception:  # noqa: BLE001
                    pass
                # ⭐ 폼 채움이 실패해 기본 서식으로 떨어졌으면(=rc 0 이라 stderr 를 안 읽는
                # 경로) **자식 stderr 꼬리를 진단에 실어** 웹 로그로 올린다. 안 그러면
                # 결과물이 통째로 달라진 사고가 "성공" 으로만 보인다(적대리뷰 2026-08-10).
                try:
                    if '"form_fallback_error": ""' not in _last_diag["v"] \
                            and "form_fallback_error" in _last_diag["v"]:
                        d = json.loads(_last_diag["v"])
                        d["stderr_tail"] = proc.stderr.decode("utf-8", "replace")[-1200:]
                        _last_diag["v"] = json.dumps(d, ensure_ascii=False)
                        sys.stderr.write(
                            f"[connector] 폼 채움 실패 → 기본 서식: "
                            f"{d.get('form_fallback_error')}\n")
                except Exception:  # noqa: BLE001 — 진단 보강 실패가 변환을 막지 않는다
                    pass
                if produced.suffix.lower() != suffix.lower():
                    # ⭐ 진단에도 싣는다 — 이걸 안 남기면 "폼 바탕쪽 세로선이 빠진
                    # .hwpx 가 나갔다"는 사고가 웹에선 **그냥 성공**으로만 보인다
                    # (폼 폴백을 stderr_tail 로 올린 것과 같은 이유, 적대리뷰 2026-08-10).
                    sys.stderr.write(
                        f"[connector] 산출물 확장자 폴백: {produced.name}"
                        f" (요청 {suffix})\n")
                    try:
                        d = json.loads(_last_diag["v"] or "{}")
                        d["output_suffix"] = produced.suffix
                        d["output_suffix_requested"] = suffix
                        _last_diag["v"] = json.dumps(d, ensure_ascii=False)
                    except Exception:  # noqa: BLE001
                        pass
                return produced.read_bytes(), produced.suffix
            if timed_out:
                # ⚠️ 타임아웃은 **재시도하지 않는다** — 시험지 크기가 원인이라 결정적으로
                # 재발한다. 재시도는 같은 시간을 또 태우고 실패할 뿐(COM flake 만 재시도).
                raise ConvertError(f"변환 타임아웃({CONVERT_TIMEOUT_S}s) — 문항이 매우 많은 시험지입니다")
            tail = proc.stderr.decode("utf-8", "replace")[-1200:] if proc else ""
            rc = proc.returncode if proc else "none"
            last = f"변환 실패(exit {rc})\n{tail}"
            _t.sleep(1.0)  # 잠깐 쉬고 1회 재시도(COM 안정화)
        raise ConvertError(last)


class Handler(BaseHTTPRequestHandler):
    server_version = f"MathGenHWP/{VERSION}"

    def _origin(self):
        return self.headers.get("Origin")

    def _cors(self, origin) -> None:
        if _is_allowed_origin(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def _send_json(self, code: int, obj: dict, origin=None) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self._cors(origin)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def do_OPTIONS(self):
        origin = self._origin()
        self.send_response(204)
        self._cors(origin)
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        # X-Connector-Token 은 시험지 한글화 웹, X-Pairing-Token 은 mathgen 웹이 쓴다.
        self.send_header("Access-Control-Allow-Headers",
                         "Content-Type, X-Pairing-Token, X-Connector-Token")
        # Private Network Access — 공개 HTTPS origin(프로덕션)이 로컬 127.0.0.1 을
        # 호출할 때 Chrome 이 preflight 에 PNA 허용을 요구. 허용 origin 에만 응답.
        if (_is_allowed_origin(origin)
                and self.headers.get("Access-Control-Request-Private-Network") == "true"):
            self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_GET(self):
        if self.path.split("?")[0] != "/health":
            self._send_json(404, {"error": "not found"}, self._origin())
            return
        hwp = _detect_hwp_installed()
        self._send_json(200, {
            "status": "ok",
            "version": VERSION,
            "engine": "hwpx",
            "hwp_com": hwp,
            "hwp": hwp,          # 웹(시험지 한글화)이 읽는 이름 — 같은 값
            # 한글 버전 힌트(진단용) — COM 크래시가 버전 의존인지 가르는 유일한 단서.
            "hwp_version": _detect_hwp_version(),
            "token": bool(REQUIRE_TOKEN),
            "capabilities": ["convert-json"],
        }, self._origin())

    def do_POST(self):
        origin = self._origin()
        if self.path.split("?")[0] != "/convert-json":
            self._send_json(404, {"error": "not found"}, origin)
            return
        if origin is not None and not _is_allowed_origin(origin):
            self._send_json(403, {"error": f"origin not allowed: {origin}"}, origin)
            return
        expected = ensure_token()  # 어떤 경로로 띄웠든 여기서 보장(agent.py 대비)
        if REQUIRE_TOKEN and expected:
            got = (self.headers.get("X-Connector-Token")
                   or self.headers.get("X-Pairing-Token") or "")
            if got.strip().upper() != expected.upper():
                self._send_json(401, {
                    "error": "연결 코드가 필요합니다 — HWP 도우미 창에 표시된 "
                             "코드를 웹에 입력하세요.",
                }, origin)
                return

        # ⭐ 동시 변환 차단 — HWP COM 은 한 번에 하나만 안전하다. 웹을 여러 탭/창으로
        # 띄워 동시에 돌리면 렌더가 충돌하므로, 두 번째 요청은 409 로 즉시 거절한다
        # (웹 쪽 Web Locks 는 같은 브라우저만 막고, 이건 도우미 차원의 최종 방어).
        if not _CONVERT_LOCK.acquire(blocking=False):
            self._send_json(409, {
                "error": "다른 변환이 진행 중입니다 — 앞의 변환이 끝난 뒤 다시 시도하세요.",
            }, origin)
            return
        try:
            self._do_convert(origin)
        finally:
            _CONVERT_LOCK.release()

    def _do_convert(self, origin) -> None:
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            length = 0
        if length <= 0:
            self._send_json(400, {"error": "빈 요청 본문"}, origin)
            return
        body = self.rfile.read(length)

        try:
            payload = json.loads(body)
        except Exception:
            self._send_json(400, {"error": "JSON 파싱 실패"}, origin)
            return
        # payload 두 종류 — 엔진 봉투(questions) / mathgen(problems). 판별은
        # convert_cli.is_engine_envelope 한 곳(중복 판정 금지).
        from server.convert_cli import is_engine_envelope

        d = payload if isinstance(payload, dict) else {}
        engine_env = is_engine_envelope(d)
        if not (d.get("questions") if engine_env else d.get("problems")):
            self._send_json(400, {"error": "내보낼 문항이 없습니다."}, origin)
            return
        # 엔진 봉투는 폼 바탕쪽(2단 가운데 구분선) 보존을 위해 .hwp 로 굽는다.
        suffix = ".hwp" if engine_env else ".hwpx"
        stem = Path(str(d.get("filename") or "export")).stem or "export"

        try:
            with _convert_lock:  # 한글 COM 직렬화
                data, suffix = _run_convert_subprocess(body, suffix)
                # ⚠️ 진단은 **락 안에서** 집어 온다. `ThreadingHTTPServer` 라 동시 요청이
                # 실재하고, 밖에서 읽으면 락을 놓은 뒤 다른 요청이 덮어쓴 값(= 남의 폼)을
                # 헤더로 내보낼 수 있다. 지금 창은 아주 좁지만, 이 줄이 밖에 있으면
                # 리팩터 한 번에 조용히 살아나는 종류의 버그다.
                diag = _last_diag.get("v") or ""
        except ConvertError as e:
            self._send_json(500, {"error": str(e)}, origin)
            return
        except Exception as e:  # noqa: BLE001
            self._send_json(500, {"error": f"내부 오류: {e}"}, origin)
            return

        self.send_response(200)
        self._cors(origin)
        self.send_header("Content-Type", "application/octet-stream")
        # 한글 파일명은 RFC 5987(filename*)로 — ASCII filename= 만 쓰면 깨진다.
        # 웹이 fetch 로 읽으려면 Expose-Headers 가 필요(CORS 기본 노출 목록에 없음).
        name = f"{stem}_변환{suffix}"
        self.send_header(
            "Content-Disposition",
            "attachment; filename=\"export{}\"; filename*=UTF-8''{}".format(
                suffix, quote(name, safe="")))
        # 웹이 "어떤 폼으로 렌더됐나"를 로그에 남길 수 있게 진단을 헤더로 넘긴다.
        # (헤더는 ASCII 만 안전 → URL 인코딩. 값은 위 락 안에서 이미 집어 왔다.)
        if diag:
            self.send_header("X-Convert-Diag", quote(diag, safe=""))
        self.send_header("Access-Control-Expose-Headers",
                         "Content-Disposition, X-Convert-Diag")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except Exception:
            pass

    def log_message(self, fmt, *args):
        sys.stderr.write("[connector] " + (fmt % args) + "\n")


def main() -> int:
    global EXPECTED_TOKEN, REQUIRE_TOKEN

    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-token", action="store_true", help="페어링 토큰 끄기(dev)")
    ap.add_argument("--output-dir", default=None, help="(미사용, 디버그 예약)")
    args = ap.parse_args()

    if args.no_token:
        REQUIRE_TOKEN = False
    ensure_token()

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    if REQUIRE_TOKEN:
        sys.stderr.write(
            "\n" + "=" * 46
            + f"\n  연결 코드:  {EXPECTED_TOKEN}\n"
              "  웹에 이 코드를 입력하면 변환이 시작됩니다.\n"
            + "=" * 46 + "\n\n")
    sys.stderr.write(
        f"[connector] listening on http://{args.host}:{args.port} "
        f"(engine=hwpx, hwp_com={_detect_hwp_installed()}, "
        f"token={'on' if REQUIRE_TOKEN else 'off'})\n"
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write("[connector] shutting down\n")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
