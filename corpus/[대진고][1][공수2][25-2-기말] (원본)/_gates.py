# -*- coding: utf-8 -*-
"""결정적 게이트 — 최종 .hwp 를 .hwpx 로 변환해 XML 을 검사한다.

  1) corpus_lint --xml (메타토큰·자모혼입·라벨혼재·정답증발·배점중복)
  2) 이상문자열 스캔(단독 자모·자모+음절·치환문자·메타토큰 잔여)
  3) 그림(gso/pic) 개수·binItem 참조 — 그림이 배너로 바뀌지 않았는지
  4) 수식 baseUnit(정답면 10pt 문제) · 정답 페이지 존재 · 라벨 단어 일관성
"""
import os
import re
import subprocess
import sys
import zipfile

from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

JAMO_LONE = re.compile(r"<hp:t>[ㄱ-ㆎ]</hp:t>")
JAMO_ADJ = re.compile(r"[㄰-㆏][가-힣\d]")
CTRL = re.compile("[" + "\ufffd" + "\x00-\x08\x0b\x0c\x0e-\x1f" + "]")
META_TOKEN = re.compile(r"(소단원자리표식QZX|난이도자리표식QZX|그림삽입자리\d+끝표식)")


def to_hwpx(hwp_path: Path) -> Path:
    out = hwp_path.with_name(hwp_path.stem + "__gate.hwpx")
    import pythoncom
    import win32com.client as wc
    pythoncom.CoInitialize()
    h = wc.Dispatch("HWPFrame.HwpObject")
    h.SetMessageBoxMode(0xFFFFFF)
    try:
        h.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
    except Exception:  # noqa: BLE001
        pass
    try:
        h.XHwpWindows.Item(0).Visible = False
    except Exception:  # noqa: BLE001
        pass
    if not h.Open(str(hwp_path), "HWP", "forceopen:true"):
        raise SystemExit(f"HWP Open 실패: {hwp_path}")
    if out.exists():
        out.unlink()
    h.SaveAs(str(out), "HWPX", "")
    h.Quit()
    return out


def main(argv):
    hwp = Path(argv[0] if argv else HERE / "out" / "대진고_공수2_기말_변환.hwp").resolve()
    hwpx = to_hwpx(hwp)
    with zipfile.ZipFile(hwpx) as z:
        names = z.namelist()
        secs = {n: z.read(n).decode("utf-8") for n in names if re.search(r"section\d+\.xml$", n)}
        hpf = next((z.read(n).decode("utf-8") for n in names if n.endswith("content.hpf")), "")
    xml = "".join(secs.values())
    fails, warns = [], []

    # 1) corpus_lint
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "corpus_lint.py"), "--xml", str(hwpx)],
                       capture_output=True, text=True, encoding="utf-8")
    print("[corpus_lint]", (r.stdout or r.stderr).strip())
    if r.returncode != 0:
        fails.append("corpus_lint --xml FAIL")

    # 2) 이상문자열
    texts = re.findall(r"<hp:t>(.*?)</hp:t>", xml, re.S)
    body = "".join(texts)
    if JAMO_LONE.search(xml):
        fails.append(f"단독 자모 런: {JAMO_LONE.findall(xml)[:5]}")
    if JAMO_ADJ.search(body):
        fails.append(f"자모+음절 혼입: {JAMO_ADJ.findall(body)[:5]}")
    if CTRL.search(body):
        fails.append("제어/치환 문자 혼입")
    if META_TOKEN.search(xml):
        fails.append(f"자리표식 토큰 잔존: {set(META_TOKEN.findall(xml))}")

    # 3) 그림
    pics = re.findall(r'<hp:pic\b.*?</hp:pic>', xml, re.S)
    refs = [re.search(r'binaryItemIDRef="([^"]+)"', p).group(1) for p in pics
            if re.search(r'binaryItemIDRef="([^"]+)"', p)]
    embedded = {m.group(1) for m in re.finditer(r'id="(image\d+)"[^>]*isEmbeded="1"', hpf)}
    print("[그림] pic", len(pics), "| binItem 참조", refs, "| 임베드 등록", sorted(embedded))
    body_pics = [p for p in pics if 'binaryItemIDRef="image1"' not in p]
    if len(body_pics) < 4:
        fails.append(f"본문 그림이 4개 미만: {len(body_pics)}")
    sizes = [re.search(r'<hp:sz width="(\d+)"[^>]*height="(\d+)"', p) for p in pics]
    print("[그림 크기 mm]", [(round(int(m.group(1)) / 283.465, 1),
                              round(int(m.group(2)) / 283.465, 1)) for m in sizes if m])

    # 4) 정답 페이지·라벨·수식 크기
    if "정답" not in body:
        fails.append("정답 블록 없음")
    labels = set(re.findall(r"\[(서답형|서술형|단답형)\s*", body))
    print("[라벨]", labels, "| 서답형 라벨 수", body.count("[서답형"))
    if len(labels) > 1:
        fails.append(f"라벨 단어 혼재: {labels}")
    units = re.findall(r'baseUnit="(\d+)"', xml)
    from collections import Counter
    print("[수식 baseUnit]", Counter(units).most_common())
    print("[수식 개수]", len(re.findall(r"<hp:equation", xml)),
          "| 워터마크", len(re.findall(r"수식 변환기로 변환된 수식입니다", xml)))
    print("[쪽 수 추정] linesegarray page 표시는 PDF 로 확인")

    for w in warns:
        print("WARN:", w)
    if fails:
        print("\n=== GATE FAIL ===")
        for f in fails:
            print(" *", f)
        raise SystemExit(1)
    print("\n=== GATE PASS ===")


if __name__ == "__main__":
    main(sys.argv[1:])
