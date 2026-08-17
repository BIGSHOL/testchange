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
# ⚠️ append 로 붙인다 — insert(0) 이면 db/ 안 모듈이 **표준 라이브러리를
#    가린다**(db/queue.py 가 queue 를 가려 requests 임포트가 죽었다).
sys.path.append(str(BASE))
# ⚠️ stdout 교체는 **직접 실행될 때만**. import 하는 쪽의 래퍼를 닫아 버려
#    부르는 스크립트가 print 에서 죽는다(실제로 배치 실행기가 터졌다).
if __name__ == "__main__":
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
_SCORE = re.compile(r"\[\s*(?:[총합]\s*)?(\d+(?:\.\d+)?)\s*점[^\]]*\]")
_META = re.compile(r"\[(소단원|중단원|난이도)\]\s*([^\[\n]*)")


# PDF 에 **유니코드 그대로** 실리는 수식 기호. PUA 가 아니라서 그냥 두면 수식 런이
# 여기서 끊겨 `A={` / `∅` / `,{` 처럼 조각난다.
MATH_UNI = set("∅∩∪⊂⊃⊆⊇∈∉≠≤≥×÷±∞√∠△□∽≡→←↔⇔⇒∑∏∫αβγδθπωΩ")


def ispua(ch: str) -> bool:
    return 0xE000 <= ord(ch) <= 0xF8FF


# 수식 폰트에서 온 중괄호는 **글자로서의 중괄호**다. 그대로 내보내면 LaTeX 구조용
# 중괄호와 섞여 균형이 깨진다(연립방정식 `{`·집합 `{x|…}` — 감사가 154건 잡았다).
_BRACE = {"{": r"\{", "}": r"\}"}


def decode(s: str) -> str:
    out = []
    for c in s:
        if ispua(c):
            d = _T.get(ord(c), c)
            out.append(_BRACE.get(d, d))
        else:
            out.append(c)          # 본문의 평범한 괄호는 건드리지 않는다
    return "".join(out)


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
                            "page": pno, "c": c, "eq": ispua(c) or c in MATH_UNI,
                            "x0": ch["bbox"][0], "y0": ch["bbox"][1],
                            "x1": ch["bbox"][2], "y1": ch["bbox"][3],
                            "size": sp.get("size", 0), "ly": ly, "blk": bi, "ln": li,
                        })
    return out


def _col_of(s: dict, mid: float) -> int:
    return 0 if s["x0"] < mid else 1


# --------------------------------------------------- 그림·박스(벡터/이미지) 검출
def page_figures(page, pno: int) -> list[dict]:
    """그림 = **임베드 이미지**. 단 1쪽 상단 전폭 배너는 학원 로고라 뺀다."""
    W = page.rect.width
    out = []
    for im in page.get_images(full=True):
        try:
            rects = page.get_image_rects(im[0])
        except Exception:
            continue
        for r in rects:
            if pno == 0 and r.y0 < 110 and r.width > W * 0.6:
                continue                      # 머리 배너(로고)
            if r.width < 24 or r.height < 24:
                continue                      # 장식용 작은 조각
            out.append({"x0": r.x0, "y0": r.y0, "x1": r.x1, "y1": r.y1, "page": pno})
    return out


def page_boxes(page) -> list[tuple[float, float, float, float]]:
    """테두리 박스 = 가로선 2 + 세로선 2. 쪽 테두리와 단 구분선은 뺀다.

    라벨이 인쇄된 박스(`─<보기>─`)는 윗변이 라벨 자리에서 **끊겨 두 토막**으로
    그려진다 → 같은 y 의 가로 조각을 먼저 이어 붙여야 박스로 인식된다.
    """
    W, H = page.rect.width, page.rect.height
    hs, vs = [], []
    # ⚠️ 아래 짝짓기는 가로선 쌍 × 세로선 이라 O(n²)~O(n³) 이다. 벡터로 그린
    #    격자·그래프가 있는 면은 선이 수백 개라 사실상 멈춘다(실측: 배치가 한
    #    시험지에서 정지). 그런 면은 애초에 그림 면이니 박스 검출을 건너뛴다.
    _LIMIT = 120
    for d in page.get_drawings():
        for it in d["items"]:
            if it[0] != "l":
                continue
            a, b = it[1], it[2]
            if abs(a.y - b.y) < 1.2:
                hs.append((round((a.y + b.y) / 2, 1), min(a.x, b.x), max(a.x, b.x)))
            elif abs(a.x - b.x) < 1.2:
                vs.append((round((a.x + b.x) / 2, 1), min(a.y, b.y), max(a.y, b.y)))
    if len(hs) > _LIMIT or len(vs) > _LIMIT:
        return []
    merged: dict[float, list[list[float]]] = {}
    for y, x0, x1 in hs:
        segs = merged.setdefault(y, [])
        for s in segs:
            if x0 <= s[1] + 12 and x1 >= s[0] - 12:      # 라벨 틈(≤12pt) 이어 붙임
                s[0], s[1] = min(s[0], x0), max(s[1], x1)
                break
        else:
            segs.append([x0, x1])

    out = []
    ys = sorted(merged)
    for i, yt in enumerate(ys):
        for yb in ys[i + 1:]:
            if yb - yt < 14 or yb - yt > H * 0.75:
                continue
            for st in merged[yt]:
                for sb in merged[yb]:
                    x0, x1 = max(st[0], sb[0]), min(st[1], sb[1])
                    if x1 - x0 < 40:
                        continue
                    if x1 - x0 > W * 0.92 and yb - yt > H * 0.7:
                        continue                          # 쪽 테두리
                    lv = any(abs(vx - x0) < 3 and vy0 <= yt + 3 and vy1 >= yb - 3
                             for vx, vy0, vy1 in vs)
                    rv = any(abs(vx - x1) < 3 and vy0 <= yt + 3 and vy1 >= yb - 3
                             for vx, vy0, vy1 in vs)
                    if lv and rv:
                        out.append((x0, yt, x1, yb))
    # 큰 박스가 작은 박스를 품으면 큰 것만(중첩 테두리 중복 제거)
    out.sort(key=lambda r: (r[2] - r[0]) * (r[3] - r[1]), reverse=True)
    keep: list[tuple] = []
    for r in out:
        if not any(k[0] - 2 <= r[0] and k[1] - 2 <= r[1]
                   and k[2] + 2 >= r[2] and k[3] + 2 >= r[3] for k in keep):
            keep.append(r)
    return keep


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
        out.append(_eqchar(s["c"]))
    if mode:
        out.append("}")
    return "".join(out).strip()


def _eqchar(c: str) -> str:
    """수식 글자 하나 → LaTeX. 중괄호는 **글자로서의 중괄호**라 반드시 이스케이프한다.

    연립방정식의 큰 `{` 나 집합 표기 `{1,2}` 가 그대로 나가면 LaTeX 중괄호와
    섞여 균형이 깨진다(감사가 154건 잡았다). build_equation 이 만드는 구조용
    중괄호는 문자열 리터럴로 따로 붙이므로 이 경로를 안 탄다 — 구분이 정확하다.
    """
    return decode(c)     # 중괄호 이스케이프는 decode 가 일괄 처리한다


def _flush(run: list[dict], parts: list):
    if run:
        eq = build_equation(run)
        if eq:
            parts.append({"type": "equation", "value": eq})
        run.clear()


def to_blocks(sp: list[dict]) -> list[dict]:
    """글자열 → contents 블록(평문/수식 교대 + 그림·박스)."""
    parts: list[dict] = []
    run: list[dict] = []
    buf: list[str] = []

    def flush_text():
        if buf:
            t = "".join(buf).strip()
            if t:
                parts.append({"type": "text", "value": t})
            buf.clear()

    i = 0
    while i < len(sp):
        s = sp[i]
        if s.get("fig"):
            _flush(run, parts); flush_text()
            f = s["fig"]
            parts.append({"type": "figure", "value": "",
                          "bbox": [round(f["x0"], 1), round(f["y0"], 1),
                                   round(f["x1"], 1), round(f["y1"], 1)],
                          "page": f["page"] + 1})
            i += 1
            continue
        if s.get("bx") is not None:
            # 박스는 통째로 모아 라벨 순으로 조립한다(중간에 쪼개면 순서가 깨진다)
            bi = s["bx"]
            j = i
            grp = []
            while j < len(sp) and sp[j].get("bx") == bi:
                grp.append(sp[j]); j += 1
            _flush(run, parts); flush_text()
            body = box_text(grp)
            if body:
                # 인쇄된 `<보기>`/`<조건>` 라벨이 없으면 라벨 없는 박스 = `<상자>`
                if not _PRINTED_BOX.search(body):
                    body = "<상자> " + body
                parts.append({"type": "text", "value": body})
            i = j
            continue
        if s["eq"]:
            flush_text()
            run.append(s)
        elif run and s["c"] == " ":
            # 수식 사이에 낀 공백 한 칸은 수식의 일부로 본다(끊으면 조각난다)
            run.append(s)
        else:
            _flush(run, parts)
            buf.append(s["c"])
        i += 1
    flush_text()
    _flush(run, parts)
    # 그림 블록은 value 가 비어 있는 게 정상이라 빈값 필터에서 지켜 준다
    return [p for p in parts
            if p["type"] == "figure" or (p.get("value") or "").strip()]


# 항목 머리 = `(가)` `ㄱ.` `①` — 여는 괄호부터 통째로 잡아야 잘린 자리가 깨끗하다
_ITEM_HEAD = re.compile(r"[(（]\s*([가-힣])\s*[)）]|(?:^|(?<=\s))([ㄱ-ㅎ])\s*\.|([①-⑩])")
_LABEL_ORDER = {c: i for i, c in enumerate("가나다라마바사아자차카타파하")}
_LABEL_ORDER.update({c: i for i, c in enumerate("ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊ")})
_LABEL_ORDER.update({c: i for i, c in enumerate("①②③④⑤⑥⑦⑧⑨⑩")})
_PRINTED_BOX = re.compile(r"<\s*(보기|조건)\s*>")


def _head_label(m) -> str | None:
    """_ITEM_HEAD 의 세 갈래(괄호한글·자모마침표·원문자) 중 잡힌 것을 돌려준다."""
    return next((g for g in m.groups() if g), None)


def box_text(chars: list[dict]) -> str:
    """박스 안 내용을 우리 파서가 아는 꼴로 — 라벨 순 정렬 + `•` 구분.

    박스 항목은 2~3열로 배치되곤 하는데, 지면을 읽는 순서(행 우선)와 라벨 순서가
    어긋난다(작성자가 세로로 (가)(나)(다)를 먼저 채운다). 문항 본문이 라벨로
    항목을 가리키므로 **라벨 순서가 의미상 옳다** — 그 순서로 되돌린다.
    """
    lines: dict[tuple, list[dict]] = {}
    for c in chars:
        lines.setdefault((c["blk"], c["ln"]), []).append(c)
    segs: list[str] = []
    for key in sorted(lines):
        row = decode("".join(c["c"] for c in sorted(lines[key], key=lambda c: c["x0"])))
        row = re.sub(r"\s+", " ", row).strip()
        if not row:
            continue
        # 항목 라벨 위치에서 자른다. 글자 단위로 끊으면 여는 괄호가 떨어져 나가
        # `( • 가)` 처럼 망가진다 — **줄 문자열에 정규식**을 걸어야 한다.
        cuts = [m.start() for m in _ITEM_HEAD.finditer(row)]
        if not cuts or cuts[0] != 0:
            cuts = [0] + cuts
        for a, b in zip(cuts, cuts[1:] + [len(row)]):
            t = row[a:b].strip()
            if t:
                segs.append(t)
    lab = []
    for t in segs:
        m = _ITEM_HEAD.match(t)
        key = _LABEL_ORDER.get(_head_label(m)) if m else None
        lab.append((key, t))
    # 라벨 붙은 항목이 과반이면 라벨 순으로 재배열(열 우선 배치를 되돌린다)
    if sum(1 for k, _ in lab if k is not None) >= max(2, len(segs) * 0.6):
        known = sorted((x for x in lab if x[0] is not None), key=lambda x: x[0])
        segs = [t for _, t in known] + [t for k, t in lab if k is None]
    return " • ".join(segs)


# ----------------------------------------------------------------- 문항 분해
def answer_page_start(doc) -> int:
    """정답·해설면이 시작하는 쪽(없으면 page_count).

    ⚠️ 정답면을 문제면과 함께 파싱하면 **정답 표의 ①②③ 이 선택지로 빨려 들어가고**
    (실측: 마지막 문항이 선택지 20개), 해설의 배점이 더해져 배점 합이 100 을 넘는다.
    정답면은 문서 뒤쪽에 있고 '정답' 이라는 낱말을 달고 있다 — 앞쪽 문제면엔 없다.
    """
    n = doc.page_count
    for p in range(max(1, n // 2), n):
        t = decode(doc[p].get_text())
        # ⚠️ 낱말로 판정하면 안 된다. '풀이 과정을 쓰시오' 는 **서술형 발문**에
        #    흔해서 거기서 자르면 뒤 문항이 통째로 사라지고(25문항 → 16문항 적재,
        #    감사가 잡았다), 반대로 '정답' 만 찾으면 해설면을 놓친다.
        #    구조로 본다: 빠른정답 목록은 `1. ①` 꼴이 줄줄이 이어진다.
        if len(re.findall(r"(?m)^\s*\d{1,2}\s*[.)]\s*[①-⑩]\s*$", t)) >= 4:
            return p
        if len(re.findall(r"(?m)^\s*\d{1,2}\s*[.)]\s*[①-⑩]", t)) >= 8:
            return p
    return n


def _answer_cut(sp: list[dict], flat: str, last_start: int) -> int:
    """문항 흐름이 끝나고 **정답 목록이 시작하는 글자 위치**(없으면 끝).

    쪽 단위 판정이 못 잡는 경우가 있다(정답이 마지막 문항과 같은 면에 붙는 폼).
    정답 목록은 번호가 **1부터 다시** 시작하므로, 마지막 문항 뒤에 줄머리 `1.` 이
    나오고 그 뒤가 원문자면 거기서 끊는다.
    """
    m0 = re.match(r"(\d{1,2})", flat[last_start:last_start + 3])
    last_num = int(m0.group(1)) if m0 else 99
    for i in range(last_start + 1, len(sp)):
        if not sp[i].get("bol"):
            continue
        m = re.match(r"(\d{1,2})\s*[.)]\s", flat[i:i + 6])
        if not m:
            continue
        # 번호가 **되돌아가면** 거기부터가 정답 목록이다. 낱말('정답'·'해설')로
        # 찾으면 표기가 제각각이라 놓치고, '풀이 과정' 같은 발문에 걸려 문항을
        # 잘라먹는다. 번호 역행은 형식과 무관한 신호다.
        if int(m.group(1)) <= last_num:
            return i
    return len(sp)


def parse_answers(doc, start: int) -> list[dict]:
    """정답면에서 `1. ①` `17. 5` 꼴을 걷어 온다 — 이것도 비전 없이 얻는다."""
    items = []
    for p in range(start, doc.page_count):
        txt = decode(doc[p].get_text())
        for m in re.finditer(r"(?m)^\s*(\d{1,2})\s*[.)]\s*([^\n]{0,60})", txt):
            num, val = int(m.group(1)), m.group(2).strip()
            if not val or num > 60:
                continue
            # 객관식은 원문자 하나, 서답형은 짧은 값. 해설 문장은 정답이 아니다.
            if val[0] in CIRCLED:
                items.append({"number": num, "answer": val[0]})
            elif len(val) <= 24 and not re.search(r"[가-힣]{3,}", val):
                items.append({"number": num, "answer": val})
    seen, out = set(), []
    for it in items:                       # 같은 번호가 여러 번이면 첫 것만
        if it["number"] in seen:
            continue
        seen.add(it["number"])
        out.append(it)
    return sorted(out, key=lambda x: x["number"])


def extract(pdf: pathlib.Path, with_answers: bool = False):
    doc = fitz.open(pdf)
    a_start = answer_page_start(doc)
    answers = parse_answers(doc, a_start) if with_answers else None
    sp = [s for s in spans(doc) if s["page"] < a_start]
    w = doc[0].rect.width
    boxes, figs = [], []
    for pno in range(a_start):
        page = doc[pno]
        for b in page_boxes(page):
            boxes.append((pno,) + tuple(b))
        figs += page_figures(page, pno)
    doc.close()

    # 글자에 박스 소속을 붙인다(박스 안 내용은 따로 조립한다)
    for s in sp:
        s["bx"] = None
        cx, cy = (s["x0"] + s["x1"]) / 2, (s["y0"] + s["y1"]) / 2
        for bi, (pno, x0, y0, x1, y1) in enumerate(boxes):
            if s["page"] == pno and x0 <= cx <= x1 and y0 <= cy <= y1:
                s["bx"] = bi
                break
    sp = read_order(sp, w)
    # 그림은 **바로 위 본문 다음**에 끼운다 — 같은 단에서 그림보다 위에 있는
    # 마지막 글자를 찾아 그 뒤에 합성 스팬을 넣는다.
    for f in figs:
        best = -1
        for i, s in enumerate(sp):
            if s["page"] == f["page"] and s["y1"] <= f["y0"] + 2 \
               and s["x1"] > f["x0"] - 30 and s["x0"] < f["x1"] + 30:
                best = i
        sp.insert(best + 1, {"c": "\x00", "eq": False, "page": f["page"],
                             "x0": f["x0"], "y0": f["y0"], "x1": f["x1"], "y1": f["y1"],
                             "size": 0, "ly": f["y0"], "blk": -1, "ln": -1,
                             "bol": False, "bx": None, "fig": f})
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
    # 마지막 문항이 정답 목록까지 삼키지 않게 경계를 하나 더 둔다
    tail = _answer_cut(sp, flat, starts[-1][1]) if starts else len(flat)
    qs = []
    for i, (num, pos) in enumerate(starts):
        end = starts[i + 1][1] if i + 1 < len(starts) else tail
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
            # 서술형은 `(1) … [3점]` 소문항으로 갈린다. 안 나누면 소문항 배점이
            # 통째로 사라져(첫 배점만 잡힌다) 인쇄 배점과 개수가 안 맞는다.
            subs = _split_subs(seg, num)
            if subs:
                q["contents"], q["sub_questions"] = subs[0], subs[1]
                # 부모에 `[총 N점]` 이 없으면 소문항 합을 총점으로 두지 않는다
                # (이중 계산 방지 — 합산은 소비하는 쪽이 판단한다)
        qs.append(q)
    doc_out = {"header": {"title": decode(flat[:120]).split("\n")[0].strip()},
               "questions": qs}
    return (doc_out, answers) if with_answers else doc_out


_SUBMARK = re.compile(r"^[(（]\s*(\d{1,2})\s*[)）]\s")


def _split_subs(seg: list[dict], num: int):
    """서술형을 `(1) (2)` 소문항으로 가른다. 없으면 None.

    소문항 마커는 **줄 첫머리**에 오고 번호가 1부터 이어진다. 본문 속 교차참조
    (`(1)에서 구한 …`)는 닫는 괄호 뒤에 공백 없이 한글이 붙어 구분된다.
    """
    flat = decode("".join(s["c"] for s in seg))
    marks: list[tuple[int, int]] = []
    for i in range(len(seg)):
        # ⚠️ 줄머리만 보면 `(1) 평균  (2) 중앙값  (3) 최빈값` 처럼 **한 줄에 나열된**
        #    소문항을 통째로 놓친다(그러면 소문항 배점이 사라져 게이트에 걸린다).
        #    참조 `(1)에서` 와는 **닫는 괄호 뒤 공백**으로 갈린다.
        m = _SUBMARK.match(flat[i:i + 6])
        if not m:
            continue
        k = int(m.group(1))
        if (not marks and k == 1) or (marks and k == marks[-1][0] + 1):
            marks.append((k, i))
    if len(marks) < 2:
        return None
    head = _clean(to_blocks(_drop_marks(seg[:marks[0][1]])), num)
    subs = []
    for j, (k, pos) in enumerate(marks):
        end = marks[j + 1][1] if j + 1 < len(marks) else len(seg)
        part = seg[pos:end]
        sc = _SCORE.search(decode("".join(s["c"] for s in part)))
        body = _clean(to_blocks(_drop_marks(part)), None)
        if body:
            # 소문항 머리의 `(k)` 는 우리 스키마의 number 와 중복이라 뗀다
            b0 = body[0]
            if b0["type"] == "text":
                b0["value"] = _SUBMARK.sub("", b0["value"]).strip()
                if not b0["value"]:
                    body = body[1:]
        s: dict = {"number": k, "contents": body}
        if sc:
            s["score"] = float(sc.group(1))
        subs.append(s)
    return head, subs


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


_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _clean(blocks: list[dict], num: int | None) -> list[dict]:
    out = []
    for b in blocks:
        # 그림 블록은 value 가 비어 있는 게 정상 — 빈값 검사에 걸려 사라지면 안 된다
        if b["type"] == "figure":
            out.append(b)
            continue
        # 그림 자리 표식(\x00) 등 제어문자가 값에 남으면 안 된다
        v = _CTRL.sub("", decode(b["value"]))
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
