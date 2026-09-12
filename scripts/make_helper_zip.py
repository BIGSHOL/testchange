# -*- coding: utf-8 -*-
"""HWP 도우미(커넥터) 배포 zip 생성 — **유출 게이트 포함**.

⚠️⚠️ 이 zip 은 **공개 URL로 배포**된다(웹 다운로드 버튼 → Supabase downloads 버킷,
인증 없음). 그래서 여기 들어가면 안 되는 것이 두 가지고, 둘 다 **눈으로는 안 보인다**:

  1. **대수회 폼지** — 링크만 알면 누구나 받아 압축을 풀 수 있다(사용자 2026-08-12
     "원본 폼을 다운받게 하고 싶지 않다"). 폼은 `<exe폴더>/forms/` 로 따로 준다.
  2. **API 키** — `config.json` 에 키가 남은 채로 굽히면 그대로 공개된다.

손으로 zip 을 만들면 이 둘을 잊는다(실제로 v1.1.1~1.1.3 이 폼을 담은 채 공개돼 있었다).
그래서 **검사에서 걸리면 zip 을 만들지 않는다** — 경고가 아니라 중단이다.

사용::

    python scripts/make_helper_zip.py                  # dist/MathGenHWP → D:/MathGenHWP.zip
    python scripts/make_helper_zip.py --out X.zip
    python scripts/make_helper_zip.py --src dist/MathGenHWP
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

REPO = Path(__file__).resolve().parent.parent
DEFAULT_SRC = REPO / "dist" / "MathGenHWP"
DEFAULT_OUT = Path("D:/MathGenHWP.zip")          # 웹 다운로드 URL 이 가리키는 이름
# 값이 비어 있어야 하는 config 키(키가 남으면 공개 zip 에 실린다)
_SECRET_KEYS = ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "DEEPSEEK_API_KEY",
                "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_URL")


def _fail(msg: str) -> None:
    print(f"\n[중단] {msg}")
    sys.exit(1)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="HWP 도우미 배포 zip 생성(유출 게이트 포함)")
    ap.add_argument("--src", default=str(DEFAULT_SRC), help=f"빌드 산출물(기본 {DEFAULT_SRC})")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help=f"출력 zip(기본 {DEFAULT_OUT})")
    ap.add_argument("--also", default="", help="같은 내용으로 복사할 추가 경로(버전 사본 등)")
    args = ap.parse_args(argv)

    src = Path(args.src).resolve()
    out = Path(args.out).resolve()
    if not (src / "MathGenHWP.exe").exists():
        _fail(f"빌드 산출물이 없습니다: {src}\n  → python -m PyInstaller agent.spec --noconfirm")

    files = sorted(p for p in src.rglob("*") if p.is_file())
    rel = [p.relative_to(src).as_posix() for p in files]

    # ── 게이트 1: 대수회 폼지가 섞였는가 ──
    forms = [r for r in rel if r.lower().endswith((".hwp", ".hwpx"))
             and "/plain2col/" not in r]
    if forms:
        _fail("대수회 폼지가 번들에 있습니다(공개 zip 에 실리면 유출):\n  "
              + "\n  ".join(forms)
              + "\n  → agent.spec datas 에서 forms/ 통째 번들을 빼고 다시 빌드하세요.")

    # ── 게이트 2: config.json 에 키가 남았는가 ──
    cfg = src / "config.json"
    if cfg.exists():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            _fail(f"config.json 을 읽을 수 없습니다: {e}")
        leaked = [k for k in _SECRET_KEYS if str(data.get(k) or "").strip()]
        if leaked:
            _fail("config.json 에 값이 남은 비밀 키가 있습니다: " + ", ".join(leaked)
                  + "\n  → 해당 값을 빈 문자열로 비우고 다시 실행하세요.")

    # ── 게이트 3: 2단 바탕 템플릿은 있어야 한다(없으면 그 모드가 조용히 퇴화) ──
    if not any("/plain2col/" in r for r in rel):
        _fail("2단 바탕 템플릿(forms/plain2col)이 번들에 없습니다.")

    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p, r in zip(files, rel):
            z.write(p, r)
    print(f"[완료] {out}  ({out.stat().st_size:,} bytes · {len(files)} 파일)")
    print("       대수회 폼 0건 · 비밀 키 0건 · 2단 템플릿 포함")
    if args.also:
        alt = Path(args.also).resolve()
        shutil.copy2(out, alt)
        print(f"[사본] {alt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
