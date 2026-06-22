# -*- coding: utf-8 -*-
"""Math-Gen 로컬 HWP 커넥터 — 웹(127.0.0.1) → COM 변환 → .hwpx.

  GET  /health        커넥터/엔진 감지 (한글 안 켬 — 레지스트리 탐지)
  POST /convert-json  HwpPayload → .hwpx octet-stream (COM subprocess 격리)
  OPTIONS             CORS preflight

dev 범위: CORS는 localhost:3000만. 무토큰(REQUIRE_TOKEN=False — 후속에 토큰 시스템).
COM-only(write_exam_to_hwp). 동기 응답(웹이 blob을 직접 await).

실행: python -m server.connector [--host 127.0.0.1] [--port 8765]
Python 3.11(pywin32) 필수.
"""
import sys
import csv
import json
import argparse
import threading
import subprocess
import tempfile
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ENGINE_ROOT = Path(__file__).resolve().parent.parent
PY311 = r"C:\Users\user\AppData\Local\Programs\Python\Python311\python.exe"
VERSION = "1.0.0"
CONVERT_TIMEOUT_S = 180
ALLOWED_ORIGINS = {
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://mathgen.para-x.co.kr",  # 프로덕션 — 공개 HTTPS origin (PNA preflight 동반)
}

# 후속 토큰 시스템 seam — True로 바꾸고 EXPECTED_TOKEN을 token.txt에서 로드.
REQUIRE_TOKEN = False
EXPECTED_TOKEN = ""

_convert_lock = threading.Lock()  # 한글 COM 단일 인스턴스 직렬화


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


def _hwp_pids() -> set:
    """현재 떠 있는 Hwp.exe PID 집합."""
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


def _run_convert_subprocess(payload_bytes: bytes) -> bytes:
    """payload JSON bytes → convert_cli subprocess → .hwpx bytes.

    엔진의 HwpSession.quit() 이 간헐적으로 실패해 고아 Hwp.exe 가 남는다
    (hwp_com.py:268 문서화). 변환 전후 Hwp.exe PID 를 비교해 *이번 변환이 띄운*
    인스턴스만 정리한다 — 사용자가 열어둔 문서·기존 인스턴스는 보존(전체 taskkill 금지).
    """
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "out.hwpx"
        inp = Path(td) / "in.json"
        inp.write_bytes(payload_bytes)
        # 배포본(frozen exe)은 자기 자신을 --convert-worker 로 재호출(번들 Python 사용).
        # dev 는 PY311 -m server.convert_cli. payload 는 stdin 대신 --in 파일로 전달 —
        # windowed exe 는 sys.stdin 이 None 일 수 있어 파일 경유가 안전.
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--convert-worker",
                   "--in", str(inp), "--out", str(out)]
            cwd = None
        else:
            cmd = [PY311, "-m", "server.convert_cli",
                   "--in", str(inp), "--out", str(out)]
            cwd = str(ENGINE_ROOT)
        before = _hwp_pids()
        timed_out = False
        proc = None
        try:
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                timeout=CONVERT_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:
            _reap(_hwp_pids() - before)  # 이번 변환 고아만 정리
        if timed_out:
            raise ConvertError(f"변환 타임아웃({CONVERT_TIMEOUT_S}s)")
        if proc is None or proc.returncode != 0 or not out.exists():
            tail = proc.stderr.decode("utf-8", "replace")[-1500:] if proc else ""
            rc = proc.returncode if proc else "none"
            raise ConvertError(f"변환 실패(exit {rc})\n{tail}")
        return out.read_bytes()


class Handler(BaseHTTPRequestHandler):
    server_version = f"MathGenHWP/{VERSION}"

    def _origin(self):
        return self.headers.get("Origin")

    def _cors(self, origin) -> None:
        if origin and origin in ALLOWED_ORIGINS:
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
        self.send_header("Access-Control-Allow-Headers",
                         "Content-Type, X-Pairing-Token")
        # Private Network Access — 공개 HTTPS origin(프로덕션)이 로컬 127.0.0.1 을
        # 호출할 때 Chrome 이 preflight 에 PNA 허용을 요구. 허용 origin 에만 응답.
        if (origin in ALLOWED_ORIGINS
                and self.headers.get("Access-Control-Request-Private-Network") == "true"):
            self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_GET(self):
        if self.path.split("?")[0] != "/health":
            self._send_json(404, {"error": "not found"}, self._origin())
            return
        self._send_json(200, {
            "status": "ok",
            "version": VERSION,
            "engine": "hwpx",
            "hwp_com": _detect_hwp_installed(),
            "capabilities": ["convert-json"],
        }, self._origin())

    def do_POST(self):
        origin = self._origin()
        if self.path.split("?")[0] != "/convert-json":
            self._send_json(404, {"error": "not found"}, origin)
            return
        if origin is not None and origin not in ALLOWED_ORIGINS:
            self._send_json(403, {"error": f"origin not allowed: {origin}"}, origin)
            return
        if REQUIRE_TOKEN:
            if self.headers.get("X-Pairing-Token", "") != EXPECTED_TOKEN:
                self._send_json(401, {"error": "페어링 토큰이 필요합니다."}, origin)
                return

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
        problems = payload.get("problems") if isinstance(payload, dict) else None
        if not problems:
            self._send_json(400, {"error": "내보낼 문항이 없습니다."}, origin)
            return

        try:
            with _convert_lock:  # 한글 COM 직렬화
                hwpx = _run_convert_subprocess(body)
        except ConvertError as e:
            self._send_json(500, {"error": str(e)}, origin)
            return
        except Exception as e:  # noqa: BLE001
            self._send_json(500, {"error": f"내부 오류: {e}"}, origin)
            return

        self.send_response(200)
        self._cors(origin)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition",
                         'attachment; filename="export.hwpx"')
        self.send_header("Content-Length", str(len(hwpx)))
        self.end_headers()
        try:
            self.wfile.write(hwpx)
        except Exception:
            pass

    def log_message(self, fmt, *args):
        sys.stderr.write("[connector] " + (fmt % args) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--output-dir", default=None, help="(미사용, 디버그 예약)")
    args = ap.parse_args()

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
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
