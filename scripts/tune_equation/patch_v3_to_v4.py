"""기존 변환본(v3)의 HWPX를 열어 수식 XML만 새 추정기로 교체한 v4를 만든다.

OCR/파싱 결과는 그대로 유지하고 수식 인라인 박스의 width/height/outMargin/baseLine만
새로운 규칙으로 재계산 → 레이아웃이 얼마나 달라지는지 공정 비교.
"""

from __future__ import annotations

import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.hwpx_writer import _estimate_equation_size  # type: ignore

DATA_DIR = ROOT / "data"
V3 = DATA_DIR / "[조암중][2][25-1-중간][동아강] (변환_v3).hwpx"
V4 = DATA_DIR / "[조암중][2][25-1-중간][동아강] (변환_v4).hwpx"


EQ_BLOCK_RE = re.compile(
    r"(<hp:equation\b)([^>]*)(>.*?</hp:equation>)", re.DOTALL
)
SCRIPT_RE = re.compile(r"<hp:script[^>]*>([^<]*)</hp:script>")


def patch_equation_block(block: str) -> str:
    """단일 hp:equation 블록의 속성을 새 규칙으로 교체."""
    m = SCRIPT_RE.search(block)
    if not m:
        return block
    script = m.group(1).strip()
    est_w, est_h = _estimate_equation_size(script)

    # 1. 최상위 hp:equation 태그의 baseLine 속성을 "85"로 통일
    def _fix_eq_attrs(m2: re.Match) -> str:
        attrs = m2.group(2)
        attrs = re.sub(r'baseLine="\d+"', 'baseLine="85"', attrs)
        return m2.group(1) + attrs + m2.group(3)

    block = re.sub(
        r"(<hp:equation\b)([^>]*?)(>)",
        _fix_eq_attrs,
        block,
        count=1,
    )

    # 2. hp:sz width/height 교체
    block = re.sub(
        r'<hp:sz([^/>]*)width="\d+"([^/>]*)height="\d+"([^/>]*)(/?>)',
        lambda m2: f'<hp:sz{m2.group(1)}width="{est_w}"{m2.group(2)}height="{est_h}"{m2.group(3)}{m2.group(4)}',
        block,
        count=1,
    )

    # 3. outMargin left/right 170으로 교체
    block = re.sub(
        r'<hp:outMargin([^/>]*)left="\d+"([^/>]*)right="\d+"',
        lambda m2: f'<hp:outMargin{m2.group(1)}left="170"{m2.group(2)}right="170"',
        block,
        count=1,
    )

    # 4. data-est-height 속성 제거 (있으면)
    block = re.sub(r'\s*data-est-height="\d+"', "", block)

    return block


def patch_section_xml(xml: str) -> tuple[str, int]:
    count = [0]

    def _replace(m: re.Match) -> str:
        count[0] += 1
        full = m.group(0)
        return patch_equation_block(full)

    new_xml = re.sub(
        r"<hp:equation\b[^>]*>.*?</hp:equation>", _replace, xml, flags=re.DOTALL
    )
    return new_xml, count[0]


def main() -> None:
    if not V3.exists():
        print(f"ERROR: {V3} not found")
        return

    # v3 → v4 복사
    shutil.copy(V3, V4)

    # ZIP 안의 Contents/section*.xml 를 찾아 수식 patch
    with zipfile.ZipFile(V3, "r") as zf:
        names = zf.namelist()
        section_names = [n for n in names if re.match(r"Contents/section\d+\.xml$", n)]

    print(f"섹션 파일 {len(section_names)}개 발견: {section_names}")

    # 작업용 임시 폴더
    work_dir = DATA_DIR / "_v4_work"
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir()

    with zipfile.ZipFile(V3, "r") as zf:
        zf.extractall(work_dir)

    total_patched = 0
    for sec_name in section_names:
        sec_path = work_dir / sec_name
        xml = sec_path.read_text(encoding="utf-8")
        new_xml, n = patch_section_xml(xml)
        sec_path.write_text(new_xml, encoding="utf-8")
        total_patched += n
        print(f"  {sec_name}: 수식 {n}개 교체")

    # ZIP 재압축 — HWPX 규칙: mimetype은 맨 앞, 비압축
    V4.unlink()
    with zipfile.ZipFile(V4, "w", zipfile.ZIP_DEFLATED) as zf:
        # mimetype 먼저 (비압축)
        mime = work_dir / "mimetype"
        if mime.exists():
            zf.write(mime, "mimetype", zipfile.ZIP_STORED)

        for path in sorted(work_dir.rglob("*")):
            if path.is_dir() or path.name == "mimetype":
                continue
            arcname = path.relative_to(work_dir).as_posix()
            zf.write(path, arcname)

    shutil.rmtree(work_dir)
    print(f"\n총 {total_patched}개 수식 교체 완료")
    print(f"출력: {V4}")


if __name__ == "__main__":
    main()
