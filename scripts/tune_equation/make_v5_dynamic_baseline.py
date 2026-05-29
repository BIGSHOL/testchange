"""v4의 모든 수식 baseLine을 '주변 텍스트 줄과 타이트하게 맞추도록' 동적 재계산.

계산 모델:
  텍스트 줄 메트릭: textheight=1000, baseline=850 (ascent=850, descent=150)
  수식 height=h, baseLine=X  →  수식 상단은 baseline 위 h*X/100, 하단은 h*(1-X/100)

  목표: 수식 상단이 텍스트 ascent(850)를 크게 넘지 않도록.
        단, 수식이 텍스트보다 크면(분수 등) 어느 쪽은 넘쳐야 함.

  규칙:
    - 1단 수식(h=1200): 가급적 텍스트 ascent에 맞춤 → X = 850/1200 × 100 ≈ 71
      (수식 상단이 텍스트 상단과 맞음. 하단은 텍스트 하단보다 200 내려감)
    - 2단 수식(h=2400): 분수선/중간이 baseline에 오도록 X = 50
      (위아래로 대칭 확장 — 분수에 자연스러움)

  단, 주변 텍스트 크기가 변하면 비율도 변함. 이 버전은 고정값으로 실험.

출력: data/[조암중]..._변환_v5.hwpx
"""

from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path

DATA_DIR = Path(r"D:/시험지 한글화/data")
V4 = DATA_DIR / "[조암중][2][25-1-중간][동아강] (변환_v4).hwpx"
V5 = DATA_DIR / "[조암중][2][25-1-중간][동아강] (변환_v5).hwpx"


def pick_baseline(height: int) -> int:
    """수식 높이에 맞춘 baseLine 계산."""
    if height >= 2000:
        return 50  # 2단 수식은 대칭
    if height >= 1100:
        return 71  # 1단 수식은 텍스트 ascent(850)에 맞춤
    return 85  # 아주 작은 수식은 정답 규약 유지


def patch_eq_block(block: str) -> str:
    sz_m = re.search(r'<hp:sz[^/>]*\bheight="(\d+)"', block)
    if not sz_m:
        return block
    h = int(sz_m.group(1))
    new_bl = pick_baseline(h)
    return re.sub(r'baseLine="\d+"', f'baseLine="{new_bl}"', block, count=1)


def main() -> None:
    if not V4.exists():
        print(f"v4 없음: {V4}")
        return

    shutil.copy(V4, V5)

    # 임시 폴더로 풀기
    work = DATA_DIR / "_v5_work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()

    with zipfile.ZipFile(V4, "r") as zf:
        zf.extractall(work)

    # section0.xml 패치
    sec = work / "Contents/section0.xml"
    xml = sec.read_text(encoding="utf-8")
    count = [0]

    def _replace(m: re.Match) -> str:
        count[0] += 1
        return patch_eq_block(m.group(0))

    new_xml = re.sub(
        r"<hp:equation\b[^>]*>.*?</hp:equation>", _replace, xml, flags=re.DOTALL
    )
    sec.write_text(new_xml, encoding="utf-8")

    # 재압축 (mimetype 비압축, 맨 앞)
    V5.unlink()
    with zipfile.ZipFile(V5, "w", zipfile.ZIP_DEFLATED) as zf:
        mime = work / "mimetype"
        if mime.exists():
            zf.write(mime, "mimetype", zipfile.ZIP_STORED)
        for path in sorted(work.rglob("*")):
            if path.is_dir() or path.name == "mimetype":
                continue
            arcname = path.relative_to(work).as_posix()
            zf.write(path, arcname)
    shutil.rmtree(work)

    print(f"수식 {count[0]}개 baseLine 재계산 완료")
    print(f"출력: {V5}")


if __name__ == "__main__":
    main()
