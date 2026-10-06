# -*- coding: utf-8 -*-
"""MathGen HWP 도우미 — 시스템 트레이 앱 (한글 설치된 PC 대상 배포본).

PyInstaller(onedir) 단일 패키지로 Python + pywin32 + 엔진 변환경로 + 커넥터를 전부
번들한다. 타깃 PC 엔 **한글(HWP) 외 아무 설치도 필요 없다**. 트레이 아이콘으로 실행
상태 표시 + 종료 + 부팅 자동시작. 커넥터(127.0.0.1:8765)를 백그라운드 데몬 스레드로 구동.

변환은 connector 가 자기 자신(exe)을 ``--convert-worker`` 로 재호출해 *자식 프로세스*
에서 COM 을 돌린다(ThreadingHTTPServer 워커 스레드의 CoInitialize 문제 회피 + 크래시
격리). onedir 라 자기 재호출 시 재추출 없이 빠르다.

windowed(콘솔 없음) 빌드라 sys.stdout/stderr 가 None 일 수 있어, 시작 시 fd 로
재바인딩한다(convert_cli 의 stderr 쓰기 + connector 의 log_message 보호).
"""
import sys
import os

# ⭐ 도우미는 로컬 ``config.json`` 을 만들지 않는다 — 키·모델·QC 설정은 전부 서버
# (Vercel env)에 있고 여기서 실제로 읽는 값은 EQ_WATERMARK 하나뿐이다. 그런데도
# ``utils.config`` 가 파일이 없으면 기본값 27개를 써 놓아, "여기에 API 키를 넣어야
# 할 것처럼 보이는" 파일이 도우미 폴더·배포 zip 에 생겼다(2026-08-20 사용자 지적).
# ⚠️ **core/utils 를 import 하기 전에** 세워야 한다(utils.config 는 import 시점에
# 파일을 읽는다). 환경변수라 커넥터가 띄우는 자식 워커까지 자동으로 따라온다.
os.environ.setdefault("MATHGEN_CONFIG_READONLY", "1")

AUTOSTART_NAME = "MathGenHWP"
AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
# 트레이 "웹앱 열기" 가 여는 주소. 배포 도메인이 정해지면 env 로 바꿀 수 있게 둔다 —
# 하드코딩만 두면 도메인이 바뀔 때마다 exe 를 다시 빌드해 전 사용자에게 재배포해야 한다.
# 기본값 = 시험지 한글 변환기 웹(2026-08-09 배포처 확정). mathgen 쪽에 나눠 줄 도우미는
# MATHGEN_HWP_SITE env 로 바꾸거나 그쪽 도메인으로 재빌드한다.
SITE_URL = os.environ.get("MATHGEN_HWP_SITE") or "https://hwp-convert-web.vercel.app"


def _ensure_streams() -> None:
    """windowed exe 는 sys.stdout/stderr 가 None → None.write 크래시 방지.

    fd 1/2 가 (부모가 PIPE 로 연결했으면) 유효 → 거기에 재바인딩해 부모가 stderr 캡처.
    더블클릭 실행(콘솔 없음)이면 fd 가 무효라 devnull 로 폴백(로그만 버림)."""
    for fd, name in ((1, "stdout"), (2, "stderr")):
        if getattr(sys, name, None) is not None:
            continue
        stream = None
        try:
            stream = os.fdopen(fd, "w", encoding="utf-8", closefd=False)
        except Exception:
            try:
                stream = open(os.devnull, "w", encoding="utf-8")
            except Exception:
                stream = None
        if stream is not None:
            setattr(sys, name, stream)


def _run_worker() -> int:
    """frozen exe 가 --convert-worker 로 자기 재호출 → convert_cli.main() 위임.

    payload 는 --in 임시파일로 받는다(stdin None 회피). 출력은 --out 파일."""
    sys.argv.remove("--convert-worker")
    from server import convert_cli
    return convert_cli.main()


def _icon_image():
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([3, 3, 60, 60], radius=14, fill=(14, 165, 233, 255))
    d.text((21, 17), "M", fill=(255, 255, 255, 255))
    return img


def _autostart_enabled() -> bool:
    import winreg
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY)
        try:
            winreg.QueryValueEx(k, AUTOSTART_NAME)
            return True
        finally:
            k.Close()
    except OSError:
        return False


def _set_autostart(enable: bool) -> None:
    import winreg
    try:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY)
        try:
            if enable:
                winreg.SetValueEx(key, AUTOSTART_NAME, 0, winreg.REG_SZ,
                                  f'"{sys.executable}"')
            else:
                try:
                    winreg.DeleteValue(key, AUTOSTART_NAME)
                except OSError:
                    pass
        finally:
            key.Close()
    except Exception:
        pass


_MUTEX_HANDLE = None   # 프로세스 수명 동안 잡고 있어야 함 — GC 되면 뮤텍스가 풀린다


def _already_running() -> bool:
    """전역 뮤텍스로 중복 실행 감지.

    포트 검사만으론 부족하다 — 두 번째 인스턴스가 조용히 죽으면 사용자는 "안 켜졌다"고
    다시 더블클릭하고, 죽은 프로세스의 트레이 유령 아이콘까지 겹쳐 아이콘이 여러 개로
    보인다(실보고 2026-08-09). 뮤텍스 + 안내창으로 명시적으로 알린다.
    """
    global _MUTEX_HANDLE
    try:
        import ctypes
        _MUTEX_HANDLE = ctypes.windll.kernel32.CreateMutexW(
            None, False, "MathGenHWP_SingleInstance")
        return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS
    except Exception:
        return False   # 감지 실패 시 실행은 막지 않는다(포트 검사가 2차 방어)


def _msgbox(text: str) -> None:
    """windowed exe 는 콘솔이 없다 — 사용자에게 보이는 유일한 통로가 메시지박스다."""
    if os.environ.get("MATHGEN_HWP_QUIET"):   # 자동화 테스트용(모달이 프로세스를 붙잡음)
        return
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, "MathGen HWP 도우미", 0x40)
    except Exception:
        pass


def _run_tray() -> int:
    import threading
    import webbrowser
    from http.server import ThreadingHTTPServer
    import pystray
    from server import connector

    # ⚠️ 중복 실행 방지 — 반드시 --convert-worker 분기 **뒤**에서만 검사한다(변환
    # 자식 프로세스는 같은 exe 를 재호출하므로 뮤텍스를 잡으면 변환이 통째로 막힌다).
    if _already_running():
        _msgbox("MathGen HWP 도우미가 이미 실행 중입니다.\n"
                "트레이(시계 옆 ^ 화살표)에서 아이콘을 확인하세요.")
        return 0

    # 커넥터 HTTP 서버 — 백그라운드 데몬 스레드. 8765 점유면(다른 프로그램) 안내 후 종료.
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", 8765), connector.Handler)
    except OSError:
        _msgbox("8765 포트를 다른 프로그램이 쓰고 있어 시작할 수 없습니다.\n"
                "이미 실행 중인 도우미(또는 개발용 커넥터)를 먼저 종료하세요.")
        return 0
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    # 첫 실행 시 부팅 자동시작 등록(이미 있으면 유지).
    if not _autostart_enabled():
        _set_autostart(True)

    hwp_ok = connector._detect_hwp_installed()
    status = "한글(HWP) 감지됨 ✓" if hwp_ok else "한글(HWP) 미설치 — 설치 필요 ✗"

    # ⭐ 연결 코드는 여기서 **반드시** 준비해야 한다 — 트레이 앱은 connector.main() 을
    # 거치지 않으므로, 초기화를 main 에만 두면 exe 에서 토큰이 빈 값이 되어 검사가
    # 통째로 무효가 된다(웹은 코드를 요구하는데 커넥터는 아무 값이나 통과).
    token = connector.ensure_token()
    token_label = f"연결 코드: {token}  (클릭 = 복사)" if token else "연결 코드: 사용 안 함"

    def on_site(icon, item):
        webbrowser.open(SITE_URL)

    def on_copy_token(icon, item):
        """연결 코드를 클립보드로 — 사용자가 옮겨 적지 않아도 되게."""
        if not token:
            return
        try:
            import subprocess
            subprocess.run("clip", input=token.encode("utf-16-le"),
                           check=False, shell=True)
        except Exception:
            pass

    def on_toggle_autostart(icon, item):
        _set_autostart(not _autostart_enabled())

    def on_quit(icon, item):
        try:
            httpd.shutdown()
        except Exception:
            pass
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("MathGen HWP 도우미 · 실행 중", None, enabled=False),
        pystray.MenuItem(status, None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(token_label, on_copy_token, enabled=bool(token)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("웹앱 열기", on_site, default=True),
        pystray.MenuItem("부팅 시 자동 시작", on_toggle_autostart,
                         checked=lambda item: _autostart_enabled()),
        pystray.MenuItem("종료", on_quit),
    )
    icon = pystray.Icon(
        "MathGenHWP", _icon_image(),
        "MathGen HWP 도우미 (127.0.0.1:8765)", menu,
    )
    icon.run()
    return 0


def main() -> int:
    _ensure_streams()
    if "--convert-worker" in sys.argv:
        return _run_worker()
    return _run_tray()


if __name__ == "__main__":
    sys.exit(main())
