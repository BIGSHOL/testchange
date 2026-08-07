# -*- coding: utf-8 -*-
"""빌드 → 산출물 검증 → 배포 → selftest 를 한 번에 (재현 가능한 배포 절차).

사용자 2026-08-07: "다른 PC 에서 변환기를 배포/exe 만들더라도 같은 변환기가 만들어질 수
있게 강력하게 잡아둘 것". 손으로 PyInstaller 를 돌리면 아래 함정에 걸린다:

  ⚠️ **PyInstaller 는 datas 경로가 없어도 경고만 내고 빌드가 성공**한다 → 기능이 조용히
     빠진 exe 가 나간다.
  ⚠️ spec 안에서 `SystemExit` 로 중단해도 **프로세스 exit code 가 0** 이라(실측 2026-08-07)
     "빌드 성공" 으로 오인하고, `dist/` 의 **이전 빌드 잔재**를 그대로 배포하게 된다.
  ⚠️ spec 안 `print` 에 비ASCII 가 있으면 cp949 콘솔에서 UnicodeEncodeError 로 빌드가
     중단된다 → **PC 마다 결과가 달라진다**.

그래서 이 스크립트는 **빌드 성공 여부를 exit code 로 믿지 않고 산출물을 직접 검사**한다.

사용::

    python scripts/build_release.py            # 빌드 + 검증 + 배포 + selftest
    python scripts/build_release.py --no-deploy   # 빌드 + 검증까지만
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DIST = REPO / "dist" / "시험지한글화"
DEPLOY = REPO / "배포용"

# 번들에 **반드시** 있어야 하는 산출물(없으면 기능이 조용히 빠진다)
REQUIRED_IN_BUNDLE = [
    "_internal/data/topic_vocab.json",   # 단원 분류 어휘(정답·해설 메타)
    "_internal/forms",                   # 대수회 폼지
    "_internal/resources",               # HWP 보안모듈
    "시험지한글화.exe",
]


def _fail(msg: str) -> None:
    print(f"\n[FAIL] {msg}")
    sys.exit(1)


def main(argv: list[str]) -> int:
    deploy = "--no-deploy" not in argv

    # 0) 소스 게이트 — spec 이 검사하지만 exit code 를 못 믿으므로 여기서도 본다.
    vocab_src = REPO / "data" / "topic_vocab.json"
    if not vocab_src.exists():
        _fail(f"소스 어휘 파일 없음: {vocab_src}\n"
              "  → python scripts/build_topic_vocab.py (분류표 PDF 필요) 또는 git 복원")
    try:
        v = json.loads(vocab_src.read_text(encoding="utf-8"))
        n_high = sum(len(x) for x in v.get("고등", {}).values())
        n_mid = sum(len(x) for x in v.get("중등", {}).values())
    except Exception as e:  # noqa: BLE001
        _fail(f"소스 어휘 파일 파손: {e}")
    print(f"[1/5] source vocab OK: high={n_high} mid={n_mid}")

    # 1) 이전 산출물 제거 — 잔재를 새 빌드로 오인하지 않도록(핵심).
    if DIST.exists():
        shutil.rmtree(DIST, ignore_errors=True)
    print("[2/5] cleaned dist/")

    # 2) 빌드
    print("[3/5] PyInstaller build ...")
    r = subprocess.run([sys.executable, "-m", "PyInstaller", "build.spec", "--noconfirm"],
                       cwd=str(REPO), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    tail = "\n".join((r.stdout or "").splitlines()[-6:])
    if r.returncode != 0:
        print(tail)
        _fail(f"PyInstaller 실패(exit={r.returncode})")

    # 3) ⭐ 산출물 검증 — exit code 를 믿지 않는다(spec SystemExit 이 0 으로 나온 전례).
    missing = [p for p in REQUIRED_IN_BUNDLE if not (DIST / p).exists()]
    if missing:
        print(tail)
        _fail("빌드 산출물 누락(기능이 빠진 exe 입니다):\n  " + "\n  ".join(missing))
    bundled = json.loads((DIST / "_internal/data/topic_vocab.json").read_text(encoding="utf-8"))
    b_high = sum(len(x) for x in bundled.get("고등", {}).values())
    b_mid = sum(len(x) for x in bundled.get("중등", {}).values())
    if (b_high, b_mid) != (n_high, n_mid):
        _fail(f"번들 어휘가 소스와 다릅니다(소스 {n_high}/{n_mid} vs 번들 {b_high}/{b_mid})")
    print(f"[4/5] bundle verified: vocab high={b_high} mid={b_mid}")

    if not deploy:
        print("\n[OK] 빌드·검증 완료(--no-deploy)")
        return 0

    # 4) 배포 — config.json 은 보존하고 _internal 만 미러링
    DEPLOY.mkdir(exist_ok=True)
    shutil.copy2(DIST / "시험지한글화.exe", DEPLOY / "시험지한글화.exe")
    subprocess.run(["robocopy", str(DIST / "_internal"), str(DEPLOY / "_internal"),
                    "/MIR", "/NFL", "/NDL", "/NJH", "/NJS", "/NP"],
                   capture_output=True)
    if not (DEPLOY / "config.json").exists():
        print("  (주의) 배포용/config.json 이 없습니다 — API 키를 넣어야 동작합니다.")

    # 5) selftest — 런타임에서 어휘·키·Gemini 를 실제로 확인
    res = DEPLOY / "selftest_result.txt"
    if res.exists():
        res.unlink()
    subprocess.run([str(DEPLOY / "시험지한글화.exe"), "--selftest"], capture_output=True)
    for _ in range(30):
        if res.exists():
            break
        time.sleep(1)
    txt = res.read_text(encoding="utf-8", errors="replace") if res.exists() else ""
    print("[5/5] selftest:")
    for ln in txt.splitlines()[:6]:
        print("   " + ln)
    if "SELFTEST OK" not in txt:
        _fail("selftest 실패 — 배포본이 정상 동작하지 않습니다.")
    if "TOPIC VOCAB OK" not in txt:
        _fail("selftest 에 단원 어휘 확인이 없습니다 — 어휘가 번들에서 빠졌습니다.")
    print("\n[OK] 빌드·검증·배포·selftest 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
