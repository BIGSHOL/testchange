# -*- coding: utf-8 -*-
"""N: 전수 스캔 → `n_inventory.tsv` (build_index.py 의 입력)

`build_index.py` 는 이 TSV(`경로\\t크기\\t수정시각`)만 읽는다. 종전에는 임시로
훑어 만들었던 탓에 다른 PC·다음 세션에서 재개할 때 인덱스를 못 만들었다.

⚠️⚠️ **이미 `n_inventory.tsv` 가 있으면 다시 스캔하지 말 것.** exam id 는
`build_index.py` 가 이 목록을 정렬해 넣는 순서로 매겨지므로, N: 에 파일이 하나만
늘어도 id 가 통째로 밀려 기존 판독 결과(`db/ocr_pilot/<id>.json`)가 **엉뚱한
시험지에 붙는다**(조용히 오염된다). 그래서 TSV 는 git 추적 = **id 앵커**다.
이 스크립트는 ① 최초 생성 ② 새 시험지를 의도적으로 편입할 때만 쓴다.
어느 경우든 재구축 뒤 **반드시** `python db/verify_ids.py` 로 대조할 것.

  python db/scan_inventory.py                    기본 루트 스캔
  python db/scan_inventory.py --root "N:/개인"   루트 지정(반복 가능)
"""
from __future__ import annotations
import argparse, os, sys, io, time, pathlib, datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = pathlib.Path(__file__).parent
OUT = BASE / "n_inventory.tsv"
DEFAULT_ROOTS = ["N:/개인"]


def walk(root: str):
    """os.scandir 재귀 — 네트워크 드라이브에서 pathlib.rglob 보다 빠르다.

    접근 거부·끊긴 링크는 건너뛴다(스캔 전체를 멈추지 않게).
    """
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            it = list(os.scandir(d))
        except OSError as ex:
            print(f"  건너뜀: {d} :: {ex}", file=sys.stderr)
            continue
        for e in it:
            try:
                if e.is_dir(follow_symlinks=False):
                    stack.append(e.path)
                elif e.is_file(follow_symlinks=False):
                    st = e.stat()
                    yield e.path, st.st_size, st.st_mtime
            except OSError:
                continue


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", action="append", default=None)
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    roots = a.root or DEFAULT_ROOTS

    out = pathlib.Path(a.out)
    tmp = out.with_suffix(".tmp")          # 중단 시 반쪽 TSV 를 남기지 않는다
    n = 0
    t0 = time.time()
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for root in roots:
            if not pathlib.Path(root).exists():
                sys.exit(f"루트 없음: {root}  (N: 드라이브 연결 확인)")
            print(f"스캔: {root}")
            for path, size, mtime in walk(root):
                ts = datetime.datetime.fromtimestamp(mtime).isoformat(timespec="seconds")
                f.write(f"{path}\t{size}\t{ts}\n")
                n += 1
                if n % 2000 == 0:
                    print(f"  {n:,}개 ({time.time()-t0:.0f}s)")
    tmp.replace(out)
    print(f"\n{n:,}개 → {out}  ({time.time()-t0:.0f}s)")
    print("다음: python db/build_index.py  →  python db/verify_ids.py")


if __name__ == "__main__":
    main()
