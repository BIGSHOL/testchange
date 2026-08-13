# -*- coding: utf-8 -*-
"""짝 없는 중괄호를 LaTeX 이스케이프로 교정한다 (판독 JSON 제자리 수정)

연립방정식의 큰 `{` 나 집합 `{x|…}` 는 **글자로서의 중괄호**인데, 비전 판독이
이스케이프 없이 내보내면 LaTeX 구조용 중괄호와 섞여 균형이 깨진다. 그대로 두면
`latex_to_hwpeq` 가 엉뚱하게 묶어 수식이 통째로 망가진다.

**짝이 맞는 중괄호는 손대지 않는다** — `x^{2}` 같은 구조는 그대로 둬야 한다.
짝을 못 찾은 것만 `\\{` / `\\}` 로 바꾼다.

  python db/fix_braces.py --dry     대상만 세기
  python db/fix_braces.py           교정(이후 ingest.py 로 재적재)
"""
from __future__ import annotations
import argparse, json, re, sys, io, pathlib

BASE = pathlib.Path(__file__).parent
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
SRC = BASE / "ocr_pilot"
_ESC = re.compile(r"\\[{}$]")


def escape_unmatched(s: str) -> str:
    """짝 없는 `{`/`}` 만 이스케이프. 이미 `\\{` 인 것은 건드리지 않는다."""
    if not s:
        return s
    # 이스케이프된 중괄호는 자리표시자로 빼 두고 구조용만 짝짓는다
    holes: list[str] = []

    def _stash(m):
        holes.append(m.group(0))
        return f"\x00{len(holes)-1}\x00"

    t = _ESC.sub(_stash, s)
    stack, unmatched = [], set()
    for i, c in enumerate(t):
        if c == "{":
            stack.append(i)
        elif c == "}":
            if stack:
                stack.pop()
            else:
                unmatched.add(i)
    unmatched.update(stack)
    if not unmatched:
        return s
    out = "".join(("\\" + c) if i in unmatched else c for i, c in enumerate(t))
    return re.sub(r"\x00(\d+)\x00", lambda m: holes[int(m.group(1))], out)


def walk(q: dict):
    for b in q.get("contents") or []:
        yield b
    for c in q.get("choices") or []:
        for b in c.get("contents") or []:
            yield b
    for s in q.get("sub_questions") or []:
        for b in s.get("contents") or []:
            yield b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    files = sorted(p for p in SRC.glob("*.json") if not p.name.endswith(".answers.json"))
    n_file = n_block = 0
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        hit = 0
        for q in d.get("questions") or []:
            for b in walk(q):
                v = b.get("value") or ""
                nv = escape_unmatched(v)
                if nv != v:
                    b["value"] = nv
                    hit += 1
        if hit:
            n_file += 1
            n_block += hit
            if not a.dry:
                f.write_text(json.dumps(d, ensure_ascii=False, indent=1),
                             encoding="utf-8")
    print(f"{'[dry] ' if a.dry else ''}중괄호 교정 — {n_file}편 / {n_block}블록")
    if not a.dry and n_file:
        print("  → python db/ingest.py 로 재적재할 것")


if __name__ == "__main__":
    main()
