# ref 없는 ocr_done corpus 폴더 → N: 완료본 매칭 (렌더/검수 없이 목록만). 3단계 분류.
# corpus [학교][학년][과목][회차] (원본) ↔ 레퍼런스 [..][출판사] (완료). 회차 '대비'접미·2024모음 포함.
import json, os, re, sys
from pathlib import Path

def _repo():
    from pathlib import Path as _P
    p=_P(__file__).resolve()
    for q in p.parents:
        if (q/'core').is_dir() and (q/'corpus').is_dir(): return q
    return p.parents[1]
WT = _repo()
CORPUS = WT / "corpus"
KICHUL = Path(r"N:\개인\기출")
# 탐색 루트(완료본이 흩어져 있어 넓게)
ROOTS = ["2025 기출모음", "2024 기출모음", "2023 기출모음"]

BRK = re.compile(r"\[([^\]]*)\]")


def parse(name):
    b = BRK.findall(name)
    school = b[0] if len(b) > 0 else ""
    grade = b[1] if len(b) > 1 else ""
    subj = b[2] if len(b) > 2 else ""
    exam = b[3] if len(b) > 3 else ""
    sem = "".join(re.findall(r"(\d\d-\d|기말|중간)", exam))  # 회차 핵심
    half = "기말" if "기말" in exam else ("중간" if "중간" in exam else "")
    return school, grade, subj, exam, half


# 완료본 인덱스 1회 구축
def build_index():
    idx = []
    for rel in ROOTS:
        root = KICHUL / rel
        if not root.exists():
            continue
        for dp, dns, fns in os.walk(root):
            for fn in fns:
                if not fn.lower().endswith((".hwp", ".pdf")):
                    continue
                if "완료" not in fn:
                    continue
                s, g, su, ex, hf = parse(fn)
                idx.append((s, g, su, hf, str(Path(dp) / fn), fn))
    return idx


def best(folder, idx):
    s, g, su, ex, hf = parse(folder)
    exact, good, weak = None, None, None
    for cs, cg, csu, chf, path, fn in idx:
        if cs != s or csu != su:        # 학교·과목 필수
            continue
        if fn.startswith(folder.replace(" (원본)", "")):
            exact = path
        if cg == g and chf == hf:
            good = good or path
        weak = weak or path
    if exact:
        return exact, "정확"
    if good:
        return good, "유사(회차변형)"
    if weak:
        return weak, "약함(학년/회차 불일치 — 검증필요)"
    return "", "완료본 없음"


def main():
    idx = build_index()
    rows = []
    for d in sorted(CORPUS.iterdir()):
        if not d.is_dir():
            continue
        mj = d / "meta.json"
        if not mj.exists():
            continue
        try:
            meta = json.loads(mj.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not str(meta.get("status", "")).startswith("ocr_done"):
            continue
        if meta.get("reference_pdf") or meta.get("ref_pdf"):
            continue
        ref, tier = best(d.name, idx)
        rows.append((d.name, ref, tier))

    out = WT / ".testkit" / "ref_match.tsv"
    with open(out, "w", encoding="utf-8") as f:
        f.write("folder\tref\ttier\n")
        for r in rows:
            f.write("\t".join(r) + "\n")

    from collections import Counter
    c = Counter(r[2] for r in rows)
    print(f"=== ref 없는 ocr_done: {len(rows)}건 (완료본 인덱스 {len(idx)}) ===")
    for k in ("정확", "유사(회차변형)", "약함(학년/회차 불일치 — 검증필요)", "완료본 없음"):
        if c.get(k):
            print(f"  {k}: {c[k]}")
    print(f"  목록: {out}\n")
    for tier in ("정확", "유사(회차변형)", "약함(학년/회차 불일치 — 검증필요)", "완료본 없음"):
        sub = [r for r in rows if r[2] == tier]
        if not sub:
            continue
        print(f"--- [{tier}] {len(sub)}건 ---")
        for folder, ref, _ in sub:
            print(f"  {folder}")
            if ref:
                print(f"     -> {ref}")


if __name__ == "__main__":
    main()
