# corpus/<시험지>/ocr/p{n}_merged.json → 폼 렌더 (API 0원).
# REVIEW_PROTOCOL 5단계(캐시 렌더) 하네스 — testkit.py 의 corpus 레이아웃 어댑터.
#
# 사용법:
#   python .testkit/corpus_render.py "corpus/<시험지폴더>" [OUT.hwpx]
import sys, os, json, re
from pathlib import Path

def _repo():
    from pathlib import Path as _P
    p=_P(__file__).resolve()
    for q in p.parents:
        if (q/'core').is_dir() and (q/'corpus').is_dir(): return q
    return p.parents[1]
REPO = _repo()
sys.path.insert(0, str(REPO))

from core.content_parser import parse_ocr_response, build_document
from core.hwp_form_writer import write_exam_to_form
from core.form_registry import parse_filename, resolve_form

FIG_NOTE = "※ 그림 자리 — 원본에서 이 영역을 캡처해 여기에 붙여넣으세요"


def resolve_figs(d):
    """figure 블록 → 안내문구 (REVIEW_PROTOCOL 5a, testkit.resolve_figs 동일)."""
    def fix(blocks):
        if not isinstance(blocks, list):
            return blocks
        return [{"type": "text", "value": FIG_NOTE}
                if isinstance(b, dict) and b.get("type") == "figure" else b
                for b in blocks]
    for q in d.get("questions") or []:
        if not isinstance(q, dict):
            continue
        if "contents" in q:
            q["contents"] = fix(q["contents"])
        for ch in q.get("choices") or []:
            if isinstance(ch, dict) and "contents" in ch:
                ch["contents"] = fix(ch["contents"])
        for sub in q.get("sub_questions") or []:
            if isinstance(sub, dict) and "contents" in sub:
                sub["contents"] = fix(sub["contents"])


def main(argv):
    if not argv:
        raise SystemExit("사용법: python .testkit/corpus_render.py <corpus폴더> [OUT.hwpx]")
    corpus_dir = Path(argv[0]).resolve()
    out = os.path.abspath(argv[1]) if len(argv) >= 2 else \
        str(REPO / ".testkit" / (corpus_dir.name + ".hwpx"))
    files = sorted((corpus_dir / "ocr").glob("p*_merged.json"),
                   key=lambda p: int(re.search(r"p(\d+)_merged", p.name).group(1)))
    if not files:
        raise SystemExit(f"ocr/p*_merged.json 없음: {corpus_dir}")
    pages = []
    for pnum, fp in enumerate(files, 1):
        d = json.load(open(fp, encoding="utf-8"))
        resolve_figs(d)
        pages.append(parse_ocr_response(d, page_number=pnum))
    print(f"pages: {len(pages)} | questions: {sum(len(p.questions) for p in pages)}")

    doc = build_document(pages)
    info = parse_filename(corpus_dir.name)
    # 시험 범위(제목 아래 " ~ " 자리): corpus 폴더의 scope.txt 한 줄("시작단원 ~ 끝단원").
    scope_fp = corpus_dir / "scope.txt"
    if info["valid"] and scope_fp.exists():
        info = dict(info, 범위=scope_fp.read_text(encoding="utf-8").strip())
        print("scope:", info["범위"])
    form = resolve_form(corpus_dir.name)
    if not form:
        raise SystemExit(f"폼 매칭 실패: {corpus_dir.name}")
    print("form:", os.path.basename(form))
    res = write_exam_to_form(doc, form, out,
                             header_values=(info if info["valid"] else None),
                             render_figures=False)
    print("WROTE:", res, os.path.exists(res))


if __name__ == "__main__":
    main(sys.argv[1:])
