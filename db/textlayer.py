# -*- coding: utf-8 -*-
"""born-digital PDF 의 텍스트 레이어로 문항을 뽑는다 — 비전 토큰 0

시험지 PDF 의 70%가 born-digital 이다. 그 안엔 글자가 이미 들어 있는데도 페이지를
이미지로 만들어 비전으로 읽고 있었다(편당 24만 토큰). 텍스트 레이어를 쓰면 같은
내용이 **공짜로** 나온다.

한글은 그대로 읽히고, 수식만 HWP 수식폰트의 사용자영역 코드(U+E0xx)로 들어 있어
`pua_table.json` 으로 되돌린다. 분수·첨자는 글자가 놓인 **좌표와 크기**로 조립한다
(분수막대 아래=분모/위=분자, 작고 위로 뜬 글자=위첨자).

  python db/textlayer.py --exam 5171 --show     한 편 뽑아 화면에 확인
  python db/textlayer.py --exam 5171 --save     db/ocr_pilot/<id>.json 로 저장
  python db/textlayer.py --verify               이미 비전으로 읽은 편과 대조
"""
from __future__ import annotations
import argparse, json, re, sqlite3, sys, io, pathlib, statistics

BASE = pathlib.Path(__file__).parent
sys.path.insert(0, str(BASE))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import fitz

DB = BASE / "exam_index.db"
PAGES = BASE / "pages"
OUT = BASE / "ocr_pilot"
_T = {int(k, 16): v for k, v in
      json.loads((BASE / "pua_table.json").read_text(encoding="utf-8"))["map"].items()}

# 분수막대 — 소스에 안 보이는 원시 글자를 박아 두면 편집 중 조용히 사라진다
FRAC_BAR = chr(0xE06D)
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"
_QNUM = re.compile(r"^\s*(\d{1,2})\.\s")
_SCORE = re.compile(r"\[\s*(?:총\s*)?(\d+(?:\.\d+)?)\s*점[^\]]*\]")
_META = re.compile(r"\[(소단원|중단원|난이도)\]\s*([^\[\n]*)")


def ispua(ch: str) -> bool:
    return 0xE000 <= ord(ch) <= 0xF8FF


def decode(s: str) -> str:
    return "".join(_T.get(ord(c), c) if ispua(c) else c for c in s)


# ---------------------------------------------------------------- 스팬 수집
def spans(doc) -> list[dict]:
    """글자 단위 위치·크기 — 분수/첨자 조립의 근거."""
    out = []
    for pno in range(doc.page_count):
        page = doc[pno]
        # ⚠️ "dict" 는 span 까지만 준다 — 분수·첨자는 **글자 단위 좌표**가 있어야
        #    조립되므로 "rawdict"(chars 포함)를 써야 한다.
        d = page.get_text("rawdict")
        for bi, blk in enumerate(d.get("blocks", [])):
            for li, line in enumerate(blk.get("lines", [])):
                # ⚠️ 정렬 기준은 **줄의 y**여야 한다. 글자 y 로 묶으면 위첨자가
                #    자기 줄에서 떨어져 나가 순서가 뒤엉킨다(a^2 → "a" 와 "2" 분리).
                ly = line.get("bbox", [0, 0, 0, 0])[1]
                for sp in line.get("spans", []):
                    for ch in sp.get("chars") or []:
                        c = ch["c"]
                        out.append({
                            "page": pno, "c": c, "eq": ispua(c),
                            "x0": ch["bbox"][0], "y0": ch["bbox"][1],
                            "x1": ch["bbox"][2], "y1": ch["bbox"][3],
                            "size": sp.get("size", 0), "ly": ly, "blk": bi, "ln": li,
                        })
    return out


def _col_of(s: dict, mid: float) -> int:
    return 0 if s["x0"] < mid else 1


def read_order(sp: list[dict], page_w: float) -> list[dict]:
    """2단 조판을 좌단 전체 → 우단 전체 순으로 펴고 **줄 시작**을 표시한다.

    rawdict 의 글자 스트림에는 줄바꿈 문자가 없다. 문항 머리("12. ")는 줄 첫머리에
    올 때만 문항 번호이므로(본문 중간의 "1. "는 아니다), 좌표로 줄이 바뀌는 지점을
    찍어 두지 않으면 번호를 못 찾는다.
    """
    out = []
    for pno in sorted({s["page"] for s in sp}):
        page = [s for s in sp if s["page"] == pno]
        # ⭐ PyMuPDF 의 **문서 순서**(블록·줄 번호)를 그대로 쓴다. 2단 조판도 이미
        #    풀려 있고, 무엇보다 인라인 분수를 "막대 줄 → 분모 → 분자+뒷말" 순으로
        #    내놓아 **문항 머리가 앞에 온다**. y 좌표로 다시 정렬하면 분자 줄이 위에
        #    있다는 이유로 문항 머리를 앞질러 경계가 깨진다(직접 겪었다).
        page.sort(key=lambda s: (s["blk"], s["ln"], s["x0"]))
        prev = None
        for s in page:
            key = (s["blk"], s["ln"])
            s["bol"] = key != prev
            prev = key
        out += page
    return out


# ------------------------------------------------------- 수식 조립(위치 기반)
def build_equation(run: list[dict]) -> str:
    """수식 글자 묶음 → LaTeX. 분수막대와 첨자를 좌표로 되살린다."""
    if not run:
        return ""
    bars = [s for s in run if s["c"] == FRAC_BAR]
    if bars:
        bar = max(bars, key=lambda s: s["x1"] - s["x0"])
        lo, hi = bar["x0"] - 0.5, bar["x1"] + 0.5
        # ⚠️ 막대 글리프의 bbox 는 **전각 상자**라 실제 선은 그 한가운데 있다.
        #    y0 로 위아래를 가르면 분자가 분모로 잡힌다(전부 뒤집혔다).
        cut = (bar["y0"] + bar["y1"]) / 2
        num, den, rest = [], [], []
        for s in run:
            if s is bar:
                continue
            if lo <= s["x0"] <= hi or lo <= s["x1"] <= hi:
                (num if (s["y0"] + s["y1"]) / 2 < cut else den).append(s)
            else:
                rest.append(s)
        if num and den:
            head = build_equation([s for s in rest if s["x1"] <= bar["x0"] + 1])
            tail = build_equation([s for s in rest if s["x0"] > bar["x1"] - 1])
            return (f"{head}\\frac{{{build_equation(num)}}}"
                    f"{{{build_equation(den)}}}{tail}")
    # 첨자 — 본문 글자보다 작고 기준선이 위/아래로 벗어난 것
    body = [s for s in run if s["c"] != FRAC_BAR]
    if not body:
        return ""
    base = statistics.median(s["size"] for s in body)
    mid_y = statistics.median((s["y0"] + s["y1"]) / 2 for s in body)
    out, mode = [], None
    for s in body:
        cy = (s["y0"] + s["y1"]) / 2
        small = s["size"] < base * 0.86
        want = None
        if small and cy < mid_y - base * 0.12:
            want = "^"
        elif small and cy > mid_y + base * 0.12:
            want = "_"
        if want != mode:
            if mode:
                out.append("}")
            if want:
                out.append(want + "{")
            mode = want
        out.append(decode(s["c"]))
    if mode:
        out.append("}")
    return "".join(out).strip()


def _flush(run: list[dict], parts: list):
    if run:
        eq = build_equation(run)
        if eq:
            parts.append({"type": "equation", "value": eq})
        run.clear()


def to_blocks(sp: list[dict]) -> list[dict]:
    """글자열 → contents 블록(평문/수식 교대)."""
    parts: list[dict] = []
    run: list[dict] = []
    buf: list[str] = []
    for s in sp:
        if s["eq"]:
            if buf:
                t = "".join(buf).strip()
                if t:
                    parts.append({"type": "text", "value": t})
                buf.clear()
            run.append(s)
        else:
            # 수식 사이에 낀 공백 한 칸은 수식의 일부로 본다(끊으면 조각난다)
            if run and s["c"] == " ":
                run.append(s)
                continue
            _flush(run, parts)
            buf.append(s["c"])
    if buf:
        t = "".join(buf).strip()
        if t:
            parts.append({"type": "text", "value": t})
    _flush(run, parts)
    return [p for p in parts if (p["value"] or "").strip()]


# ----------------------------------------------------------------- 문항 분해
def extract(pdf: pathlib.Path) -> dict:
    doc = fitz.open(pdf)
    sp = spans(doc)
    w = doc[0].rect.width
    doc.close()
    sp = read_order(sp, w)
    if not any(s["eq"] for s in sp):
        raise ValueError("수식 글리프가 없다 — 텍스트 레이어 없는 스캔본")

    flat = "".join(s["c"] for s in sp)
    # 문항 시작 = **줄 첫머리**의 "N. " 이고 번호가 1씩 이어질 때만.
    # 번호 연속을 요구해야 본문 속 "3. " 이나 쪽번호를 문항으로 오인하지 않는다.
    starts: list[tuple[int, int]] = []
    for i, s in enumerate(sp):
        if not s.get("bol"):
            continue
        m = re.match(r"(\d{1,2})\.\s", flat[i:i + 5])
        if not m:
            continue
        n = int(m.group(1))
        if (not starts and n == 1) or (starts and n == starts[-1][0] + 1):
            starts.append((n, i))
    qs = []
    for i, (num, pos) in enumerate(starts):
        end = starts[i + 1][1] if i + 1 < len(starts) else len(flat)
        seg = sp[pos:end]
        raw = "".join(s["c"] for s in seg)
        q: dict = {"number": num, "type": "객관식"}
        mm = _SCORE.search(decode(raw))
        if mm:
            q["score"] = float(mm.group(1))
        for kind, val in _META.findall(decode(raw)):
            q["topic" if kind != "난이도" else "difficulty"] = val.strip()
        # 선택지 경계
        cut = [(j, s["c"]) for j, s in enumerate(seg) if s["c"] in CIRCLED]
        cut = [(j, c) for j, c in cut if CIRCLED.index(c) < 5]
        body_end = cut[0][0] if cut else len(seg)
        # ⚠️ 배점·메타는 **글자 단위에서** 걷어낸다. 배점 숫자가 수식 글리프라
        #    블록으로 만든 뒤에 지우려 하면 "[" / 수식 3 / "점]" 세 조각으로
        #    쪼개져 어느 블록에도 안 걸린다.
        head = _drop_marks(seg[:body_end])
        q["contents"] = _clean(to_blocks(head), num)
        chs = []
        for k, (j, c) in enumerate(cut):
            e = cut[k + 1][0] if k + 1 < len(cut) else len(seg)
            blocks = _clean(to_blocks(seg[j + 1:e]), None)
            if blocks:
                chs.append({"number": CIRCLED.index(c) + 1, "contents": blocks})
        if chs:
            q["choices"] = chs
        else:
            q["type"] = "서술형"
        qs.append(q)
    return {"header": {"title": decode(flat[:120]).split("\n")[0].strip()},
            "questions": qs}


def _drop_marks(seg: list[dict]) -> list[dict]:
    """배점 `[N점]` 과 숨은 메타 `[소단원]…` 을 글자 단위로 제거한다.

    배점 숫자는 수식 글리프라 텍스트/수식 경계를 가로지른다 — 블록으로 만든 뒤
    정규식으로 지우면 가운데 숫자만 살아남아 발문에 섞인다.
    """
    dec = [decode(s["c"]) for s in seg]
    txt = "".join(dec)
    # 디코드는 1:1 이라 문자 인덱스가 그대로 스팬 인덱스다
    kill = set()
    for rx in (_SCORE, _META):
        for m in rx.finditer(txt):
            kill.update(range(m.start(), m.end()))
    return [s for j, s in enumerate(seg) if j not in kill]


def _clean(blocks: list[dict], num: int | None) -> list[dict]:
    out = []
    for b in blocks:
        v = decode(b["value"])
        if b["type"] == "text":
            v = _SCORE.sub("", v)
            v = _META.sub("", v)
            if num is not None:
                v = re.sub(rf"^\s*{num}\.\s*", "", v, count=1)
            v = re.sub(r"\s+", " ", v).strip()
        if v.strip():
            out.append({"type": b["type"], "value": v})
    return out


# -------------------------------------------------------------------- 검증
# ⚠️ 반드시 raw 문자열 — `"\times"` 는 앞 두 글자가 **탭**으로 해석돼 매칭이 죽는다
_CMP = {r"\div": "÷", r"\times": "×", r"\cdot": "·", r"\pm": "±",
        r"\leq": "≤", r"\le": "≤", r"\geq": "≥", r"\ge": "≥", r"\neq": "≠"}


def _cmp_norm(s: str) -> str:
    r"""대조용 정규화 — 같은 기호를 비전은 명령(\div)으로, 텍스트 레이어는
    글자(÷)로 준다. 표기 차이를 내용 차이로 세면 일치율이 실제보다 낮게 나온다."""
    for k, v in _CMP.items():
        s = s.replace(k, v)
    return re.sub(r"[\s{}$\\_^]", "", s)


def verify(limit: int) -> None:
    """이미 비전으로 읽은 편과 대조 — 텍스트 레이어가 얼마나 맞는지 실측."""
    import difflib
    rows, done = [], 0
    for jf in sorted(OUT.glob("*.json")):
        if jf.name.endswith(".answers.json"):
            continue
        src = PAGES / jf.stem / "src.pdf"
        if not src.exists():
            continue
        try:
            got = extract(src)
            ref = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue
        rq = {q["number"]: q for q in ref.get("questions") or []}
        gq = {q["number"]: q for q in got.get("questions") or []}
        if not rq or not gq:
            continue
        sims, sc_ok, sc_n = [], 0, 0
        for n, r in rq.items():
            g = gq.get(n)
            if not g:
                sims.append(0.0)
                continue
            f = lambda q: _cmp_norm("".join(
                (b.get("value") or "") for b in (q.get("contents") or [])))
            sims.append(difflib.SequenceMatcher(None, f(r), f(g)).ratio())
            if r.get("score") is not None:
                sc_n += 1
                sc_ok += int(g.get("score") == r.get("score"))
        rows.append((jf.stem, len(rq), len(gq),
                     sum(sims) / len(sims) if sims else 0,
                     sc_ok / sc_n if sc_n else None))
        done += 1
        if done >= limit:
            break
    print(f"{'편':<8}{'문항(비전/텍스트)':<18}{'본문 일치':<11}배점 일치")
    for eid, a, b, sim, sc in rows:
        s = f"{sc:.0%}" if sc is not None else "—"
        print(f"{eid:<8}{a:>6} / {b:<10}{sim:>9.1%}  {s:>8}")
    if rows:
        print(f"\n평균 본문 일치 {statistics.mean(r[3] for r in rows):.1%}"
              f"  / 문항수 일치 {sum(1 for r in rows if r[1]==r[2])}/{len(rows)}편")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exam", type=int)
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--limit", type=int, default=20)
    a = ap.parse_args()

    if a.verify:
        verify(a.limit)
        return
    if not a.exam:
        sys.exit("--exam 또는 --verify")
    d = extract(PAGES / str(a.exam) / "src.pdf")
    if a.show:
        for q in d["questions"]:
            print(f"\n#{q['number']} [{q.get('score')}점] {q.get('topic','')}")
            for b in q["contents"]:
                print(f"   {b['type'][:3]}| {b['value'][:96]}")
            for c in q.get("choices") or []:
                print(f"   ({c['number']}) " +
                      " ".join((b['value'] or '') for b in c['contents'])[:80])
    if a.save:
        p = OUT / f"{a.exam}.json"
        p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"저장 {p}  문항 {len(d['questions'])}")


if __name__ == "__main__":
    main()
