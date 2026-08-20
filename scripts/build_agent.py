# -*- coding: utf-8 -*-
"""웹 HWP 도우미(agent.exe) 빌드 → **산출물 게이트** → 배포 zip.

GUI exe 의 `build_release.py` 와 같은 원칙: **PyInstaller 의 exit code 를 믿지 않고
산출물을 직접 검사**한다(datas 경로가 없어도 경고만 내고 빌드가 성공한다).

⭐ 이 도우미에만 있는 게이트 — **``config.json`` 을 배포에 넣지 않는다.**
도우미는 이 파일의 값을 하나만 쓰고(EQ_WATERMARK), 키·모델·QC 설정은 전부 서버
(Vercel env)에 있다. 그런데 ``utils.config`` 가 파일이 없으면 기본값 27개를 써 놓아,
2026-08-20 배포 zip 에 "여기에 API 키를 넣어야 할 것처럼 보이는" config.json 이
섞였다(사용자 지적). 더 나쁜 경우: 빌드 폴더에 **진짜 키가 든** config.json 이 있으면
그대로 남에게 배포된다. 그래서 ① 도우미 진입점이 자동 생성을 끄고
(``MATHGEN_CONFIG_READONLY``) ② 여기서 **번들·zip 에 있으면 빌드를 실패**시킨다.
게이트가 하나뿐이면 조용히 되돌아간다(플래그를 지우거나, 손으로 zip 을 뜨거나).

사용::

    python scripts/build_agent.py                 # 빌드 + 게이트
    python scripts/build_agent.py --zip D:/MathGenHWP.zip   # + 배포 zip
    python scripts/build_agent.py --no-build --zip …       # 기존 dist 로 zip 만
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

# ⚠️ cp949 콘솔에서 비ASCII print 가 UnicodeEncodeError 로 빌드를 죽인다(실측
# 2026-08-07 — PC 마다 결과가 달라진 원인). 스트림을 먼저 고정한다.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

REPO = Path(__file__).resolve().parent.parent
DIST = REPO / "dist" / "MathGenHWP"

# 번들에 **반드시** 있어야 하는 것(없으면 기능이 조용히 빠진다)
REQUIRED = [
    "MathGenHWP.exe",
    "_internal/resources",            # HWP 보안모듈(무인 변환 필수)
    "_internal/forms/plain2col",      # '폼 없이 2단' 바탕
    "_internal/resvg_py",             # SVG → PNG (웹 그림 렌더)
]
# 번들·zip 에 **있으면 안 되는** 것
FORBIDDEN_NAMES = {"config.json"}
FORBIDDEN_PREFIX = ("config.json.bak",)

# 키처럼 생긴 문자열 — config 계열 파일에서만 본다(바이너리 전수 스캔은 오탐투성이).
_KEY_RE = re.compile(r"(sk-[A-Za-z0-9_\-]{16,}|AIza[A-Za-z0-9_\-]{20,}"
                     r"|sk-ant-[A-Za-z0-9_\-]{16,}|eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,})")


def _fail(msg: str) -> None:
    print(f"\n[FAIL] {msg}")
    sys.exit(1)


def _gate_bundle() -> None:
    if not DIST.is_dir():
        _fail(f"산출물 없음: {DIST}")
    for rel in REQUIRED:
        if not (DIST / rel).exists():
            _fail(f"번들 누락: {rel}")
    forms = sorted((DIST / "_internal" / "forms").glob("*.hwp"))
    if len(forms) < 7:
        _fail(f"대수회 폼 {len(forms)}종 — 7종 필요(웹 도우미는 폼을 싣는다)")
    print(f"  번들 OK — 폼 {len(forms)}종 · plain2col · resources · resvg_py")

    bad = [p for p in DIST.rglob("*")
           if p.is_file() and (p.name in FORBIDDEN_NAMES
                               or p.name.startswith(FORBIDDEN_PREFIX))]
    if bad:
        rels = ", ".join(str(p.relative_to(DIST)) for p in bad[:5])
        _fail(f"배포하면 안 되는 파일이 번들에 있습니다: {rels}\n"
              "  → 도우미는 config.json 을 쓰지 않는다(진입점이 "
              "MATHGEN_CONFIG_READONLY=1 을 세운다). 지우고 다시 검사하세요:\n"
              f"  del \"{bad[0]}\"")
    print("  config.json 게이트 OK — 번들에 없음")


def _gate_zip(z: Path) -> None:
    """zip 안까지 다시 본다 — 손으로 만든 zip 이 게이트를 우회하지 못하게."""
    with zipfile.ZipFile(z) as zf:
        names = zf.namelist()
        bad = [n for n in names
               if Path(n).name in FORBIDDEN_NAMES
               or Path(n).name.startswith(FORBIDDEN_PREFIX)]
        if bad:
            _fail(f"zip 에 배포 금지 파일: {bad[:5]}")
        # 혹시 다른 이름으로 들어온 설정 파일에 키가 있는지(마지막 방어).
        for n in names:
            if n.lower().endswith((".json", ".env", ".ini", ".cfg", ".txt")) \
                    and zf.getinfo(n).file_size < 200_000:
                try:
                    body = zf.read(n).decode("utf-8", "ignore")
                except Exception:  # noqa: BLE001
                    continue
                m = _KEY_RE.search(body)
                if m:
                    _fail(f"zip 안 {n} 에 API 키로 보이는 값이 있습니다: "
                          f"{m.group(0)[:12]}…")
    print(f"  zip 게이트 OK — 배포 금지 파일 0 · 키 노출 0 ({len(names)}개 항목)")


def main(argv: list[str]) -> int:
    do_build = "--no-build" not in argv
    zip_out = None
    if "--zip" in argv:
        i = argv.index("--zip")
        zip_out = Path(argv[i + 1]) if i + 1 < len(argv) else Path("D:/MathGenHWP.zip")

    if do_build:
        if DIST.exists():
            print(f"[1/3] 이전 산출물 삭제 — {DIST}")
            shutil.rmtree(DIST, ignore_errors=True)
        print("[2/3] PyInstaller agent.spec …")
        r = subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm",
                            str(REPO / "agent.spec")], cwd=str(REPO))
        # ⚠️ exit code 를 믿지 않는다(spec 의 SystemExit 이 0 으로 끝난다 — 실측
        # 2026-08-07). 아래 산출물 게이트가 진짜 판정이다.
        if r.returncode != 0:
            print(f"  (PyInstaller exit={r.returncode} — 산출물 검사로 판정)")
    print("[3/3] 산출물 게이트")
    _gate_bundle()

    if zip_out:
        if zip_out.exists():
            zip_out.unlink()
        files = [p for p in sorted(DIST.rglob("*")) if p.is_file()
                 and p.name not in FORBIDDEN_NAMES
                 and not p.name.startswith(FORBIDDEN_PREFIX)]
        with zipfile.ZipFile(zip_out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for p in files:
                z.write(p, f"MathGenHWP/{p.relative_to(DIST).as_posix()}")
        _gate_zip(zip_out)
        mb = zip_out.stat().st_size / 1024 / 1024
        print(f"\n[완료] {zip_out}  ({mb:,.0f}MB · {len(files)}개 파일)")
    else:
        print("\n[완료] 빌드+게이트 통과 (zip 은 --zip <경로> 로)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
