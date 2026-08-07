# -*- coding: utf-8 -*-
"""배포용 폴더 → 배포 zip 생성(개인 기록·백업 키 제외).

사용자 2026-08-07: 다른 사람에게 줄 설치용 zip.

⚠️ **제외 대상**(넣으면 안 되는 것):
  · ``crop/``·``ocr/``·``output/`` — 지금까지 변환한 **시험지 원본 이미지·OCR 기록**
    (400MB+ 이고 학교 시험지 내용이라 남에게 넘기면 안 된다)
  · ``config.json.bak*`` — **이전 API 키**가 든 백업(불필요한 노출)
  · ``*.log``·``토큰사용.csv``·``selftest_result.txt`` — 사용 이력

포함: exe + ``_internal`` + ``config.json``(키 포함) + 사용설명서.
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "배포용"

# 통째로 제외할 최상위 폴더
SKIP_DIRS = {"crop", "ocr", "output", "__pycache__"}
# 제외할 파일(정확 이름 또는 접두/확장자)
SKIP_EXACT = {"selftest_result.txt", "토큰사용.csv"}
SKIP_SUFFIX = (".log",)
SKIP_PREFIX = ("config.json.bak",)


def _skip(rel: Path) -> bool:
    if rel.parts and rel.parts[0] in SKIP_DIRS:
        return True
    n = rel.name
    return (n in SKIP_EXACT or n.endswith(SKIP_SUFFIX)
            or any(n.startswith(p) for p in SKIP_PREFIX))


def main(argv: list[str]) -> int:
    sys.path.insert(0, str(REPO))          # _version.py 는 리포 루트에 있다
    try:
        from _version import __version__ as ver
    except Exception:  # noqa: BLE001
        ver = "0"
    out = Path(argv[0]) if argv else Path(f"D:/시험지한글화_v{ver}.zip")
    if not SRC.exists():
        print(f"배포용 폴더 없음: {SRC}")
        return 1
    if not (SRC / "config.json").exists():
        print("⚠️ config.json 이 없습니다 — 받는 사람이 API 키를 직접 넣어야 합니다.")

    files, skipped, total = [], 0, 0
    for p in SRC.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(SRC)
        if _skip(rel):
            skipped += 1
            continue
        files.append((p, rel))
        total += p.stat().st_size

    print(f"포함 {len(files)}개 파일 ({total / 1024 / 1024:,.0f}MB) · 제외 {skipped}개")
    if out.exists():
        out.unlink()
    root = "시험지한글화"          # 압축 풀면 이 폴더 하나로
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for i, (p, rel) in enumerate(files, 1):
            z.write(p, f"{root}/{rel.as_posix()}")
            if i % 300 == 0:
                print(f"  … {i}/{len(files)}", flush=True)
    size = out.stat().st_size / 1024 / 1024
    print(f"\n[완료] {out}  ({size:,.0f}MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
