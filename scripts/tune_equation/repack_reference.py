"""data/골든셋기준_조암중_hwpx해제본/ 폴더를 유효한 HWPX 파일로 재압축한다.

HWPX 규약: mimetype은 ZIP 맨 앞에 비압축으로.
"""

import shutil
import zipfile
from pathlib import Path

REF_DIR = Path(r"D:/시험지 한글화/data/골든셋기준_조암중_hwpx해제본")
OUT = Path(r"D:/시험지 한글화/data/_REFERENCE_repacked.hwpx")


def main() -> None:
    if OUT.exists():
        OUT.unlink()

    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        # mimetype 먼저, 비압축
        mime = REF_DIR / "mimetype"
        if mime.exists():
            zf.write(mime, "mimetype", zipfile.ZIP_STORED)

        for path in sorted(REF_DIR.rglob("*")):
            if path.is_dir() or path.name == "mimetype":
                continue
            arcname = path.relative_to(REF_DIR).as_posix()
            zf.write(path, arcname)

    print(f"출력: {OUT}")
    print(f"크기: {OUT.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
