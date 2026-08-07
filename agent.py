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

AUTOSTART_NAME = "MathGenHWP"
AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
# 트레이 "웹앱 열기" 가 여는 주소. 배포 도메인이 정해지면 env 로 바꿀 수 있게 둔다 —
# 하드코딩만 두면 도메인이 바뀔 때마다 exe 를 다시 빌드해 전 사용자에게 재배포해야 한다.
SITE_URL = os.environ.get("MATHGEN_HWP_SITE") or "https://mathgen.para-x.co.kr"


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


def _run_tray() -> int:
    import threading
    import webbrowser
    from http.server import ThreadingHTTPServer
    import pystray
    from server import connector

    # 커넥터 HTTP 서버 — 백그라운드 데몬 스레드. 8765 이미 점유면(중복 실행) 조용히 종료.
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", 8765), connector.Handler)
    except OSError:
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
