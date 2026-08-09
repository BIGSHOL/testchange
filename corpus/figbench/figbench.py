# -*- coding: utf-8 -*-
"""그림 문항 벤치마크 — [그림 크롭 → flash 서술 → 배포 /api/solution 풀이 → 채점].

오성중 corpus 13문항(사람 정답 보유, 전부 그림 의존)으로 FIGURE_DESC_PROMPT 변형을
반복 실험한다. 서술 = 로컬 Gemini(배포 개선 목적 예외), 풀이 = 배포 엔드포인트(생산
경로와 동일). desc·answer 는 (문항, 프롬프트해시) 키로 캐시해 반복 비용을 줄인다.

사용: figbench.py [variant]   (variant 생략 = engine 프롬프트 원본)
"""
import base64
import concurrent.futures as cf
import glob
import hashlib
import io
import json
import os
import re
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"F:\시험지변환기")

from PIL import Image

from core.ocr_engine import FIGURE_DESC_PROMPT
from core.solution_generator import question_to_text

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "figbench_cache")
os.makedirs(CACHE, exist_ok=True)
CORPUS = glob.glob(r"F:\시험지변환기\corpus\*오성중*3*")[0]
GEMINI_KEY = json.load(open(r"F:\시험지변환기\배포용\config.json", encoding="utf-8"))["GEMINI_API_KEY"]
SITE = "https://hwp-convert-web.vercel.app"
CODE = "test1112"

# ── 프롬프트 변형(시행착오 실험 대상) ──────────────────────────────────────
VARIANTS = {
    "engine": FIGURE_DESC_PROMPT,
}

def load_cases():
    cases = []
    for f in sorted(glob.glob(os.path.join(glob.escape(CORPUS), "ocr", "p*_merged.json"))):
        pn = int(re.search(r"p(\d+)_", f).group(1))
        d = json.load(open(f, encoding="utf-8"))
        for q in d.get("questions", []):
            figs = [(i, b) for i, b in enumerate(q.get("contents", []))
                    if isinstance(b, dict) and b.get("type") == "figure" and b.get("bbox")]
            if not figs or not q.get("answer"):
                continue
            label = (q.get("label_type") or "MC")
            cases.append({
                "id": f"p{pn}-{label}{q.get('number')}",
                "page": pn, "q": q, "figs": figs,
                "isChoice": bool(q.get("choices")),
                "ref": str(q.get("answer")).strip(),
            })
    return cases


def crop_fig(page: int, bbox, pad=0.01) -> bytes:
    key = os.path.join(CACHE, f"fig_p{page}_{'_'.join(f'{v:.3f}' for v in bbox)}.png")
    if os.path.exists(key):
        return open(key, "rb").read()
    im = Image.open(os.path.join(CORPUS, "pages", f"p{page}.png"))
    w, h = im.size
    x0 = max(0, int((bbox[0] - pad) * w)); y0 = max(0, int((bbox[1] - pad) * h))
    x1 = min(w, int((bbox[2] + pad) * w)); y1 = min(h, int((bbox[3] + pad) * h))
    buf = io.BytesIO()
    im.crop((x0, y0, x1, y1)).save(buf, "PNG")
    data = buf.getvalue()
    open(key, "wb").write(data)
    return data


def gemini_desc(img: bytes, prompt: str) -> str:
    # 로컬 Gemini 키가 전부 회전돼 무효(2026-08-09) — 배포 /api/figure-desc 로 서술.
    # prompt 오버라이드는 벤치마크 실험용으로 서버가 허용(초대코드 한정).
    key = os.path.join(CACHE, "desc_" + hashlib.sha1(img + prompt.encode()).hexdigest()[:16] + ".txt")
    if os.path.exists(key):
        return open(key, encoding="utf-8").read()
    body = {"code": CODE, "image": base64.b64encode(img).decode(), "mime": "image/png",
            "prompt": prompt}
    req = urllib.request.Request(SITE + "/api/figure-desc", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        j = json.load(r)
    desc = str(j.get("desc", "")).strip()
    open(key, "w", encoding="utf-8").write(desc)
    return desc


def solve(case, desc_by_idx) -> str:
    import copy
    q = copy.deepcopy(case["q"])
    for i, _b in case["figs"]:
        q["contents"][i] = {"type": "figure", "value": desc_by_idx.get(i, "")}
    text = question_to_text(q)
    key = os.path.join(CACHE, "ans_" + hashlib.sha1(text.encode()).hexdigest()[:16] + ".json")
    if os.path.exists(key):
        return json.load(open(key, encoding="utf-8"))["answer"]
    body = {"code": CODE, "text": text, "isChoice": case["isChoice"],
            "number": case["q"].get("number"), "score": case["q"].get("score"),
            "filename": "[오성중][3][25-2-기말][동아박] (원본).pdf"}
    req = urllib.request.Request(SITE + "/api/solution", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=310) as r:
        j = json.load(r)
    json.dump(j, open(key, "w", encoding="utf-8"), ensure_ascii=False)
    return str(j.get("answer", "")).strip()


def norm(a: str) -> str:
    a = re.sub(r"[\s$\\{},~]|mathrm|text|dfrac|frac|,\\!", "", a)
    return a.replace("π", "pi").lower()


def grade(case, got: str) -> bool:
    ref = case["ref"]
    if case["isChoice"]:
        m = re.findall(r"[①②③④⑤]", got)
        return len(m) == 1 and m[0] == ref
    return norm(ref) in norm(got) or norm(got) in norm(ref)


def main():
    variant = sys.argv[1] if len(sys.argv) > 1 else "engine"
    prompt = VARIANTS[variant]
    cases = load_cases()
    print(f"variant={variant} cases={len(cases)}")

    def run_one(case):
        try:
            descs = {i: gemini_desc(crop_fig(case["page"], b["bbox"]), prompt)
                     for i, b in case["figs"]}
            got = solve(case, descs)
            ok = grade(case, got)
            return (case["id"], ok, case["ref"], got[:44], sum(len(d) for d in descs.values()))
        except Exception as e:  # noqa: BLE001
            return (case["id"], False, case["ref"], f"ERR {str(e)[:40]}", 0)

    with cf.ThreadPoolExecutor(max_workers=2) as ex:
        rows = list(ex.map(run_one, cases))
    ok_n = sum(1 for r in rows if r[1])
    for rid, ok, ref, got, dl in rows:
        print(f"  {'O' if ok else 'X'} {rid:<12} ref={ref[:24]:<26} got={got:<46} desc={dl}자")
    print(f"정확도: {ok_n}/{len(rows)}")


if __name__ == "__main__":
    main()
