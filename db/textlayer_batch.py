# -*- coding: utf-8 -*-
"""born-digital 시험지를 텍스트 레이어로 일괄 판독 — 비전 토큰 0

비전 판독은 편당 24만 토큰이 든다. born-digital 은 글자가 이미 PDF 안에 있으므로
여기서 뽑아 `db/ocr_pilot/<id>.json` 에 넣으면 **공짜로** 같은 자리를 채운다.
비전은 이 경로가 못 만드는 것(그림 설명·스캔본)에만 남겨 둔다.

  python db/textlayer_batch.py --limit 50        50편 판독(품질 게이트 통과분만 저장)
  python db/textlayer_batch.py --limit 50 --dry  저장 없이 판정만
  python db/textlayer_batch.py --report          남은 물량이 어느 경로로 갈지 집계

품질 게이트(하나라도 어긋나면 저장하지 않고 비전으로 넘긴다):
  · 문항이 최소 개수 이상 잡혔는가
  · 배점 합계가 100점 근처인가 — **전사 누락을 잡는 체크섬**
  · 판독불가 글리프(⟨XXXX⟩)가 없는가
"""
from __future__ import annotations
import argparse, json, re, sqlite3, sys, io, pathlib, traceback

BASE = pathlib.Path(__file__).parent
# ⚠️ append 로 붙인다 — insert(0) 이면 db/ 안 모듈이 **표준 라이브러리를
#    가린다**(db/queue.py 가 queue 를 가려 requests 임포트가 죽었다).
sys.path.append(str(BASE))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import textlayer as tl                                    # noqa: E402
import scope as _scope                                    # noqa: E402
import fitz                                               # noqa: E402

DB = BASE / "exam_index.db"
PAGES = BASE / "pages"
OUT = BASE / "ocr_pilot"
MIN_Q = 15                    # 시험지 한 편의 최소 문항 수(이보다 적으면 분해 실패)


def score_sum(d: dict) -> float:
    tot = 0.0
    for q in d.get("questions") or []:
        s = q.get("score")
        subs = [x.get("score") for x in (q.get("sub_questions") or [])
                if x.get("score") is not None]
        # 부모 총점과 소문항 배점을 **둘 다 더하면 이중 계산**이 된다
        tot += float(s) if s is not None else sum(float(x) for x in subs)
    return round(tot, 1)


_PRINTED_SCORE = re.compile(r"\[\s*(?:총\s*)?(\d+(?:\.\d+)?)\s*점")


def printed_scores(pdf: pathlib.Path) -> list[float]:
    """문제면에 **인쇄된** 배점 전부 — 추출이 뭘 흘렸는지 재는 기준자."""
    doc = fitz.open(pdf)
    a = tl.answer_page_start(doc)
    txt = "".join(tl.decode(doc[p].get_text()) for p in range(a))
    doc.close()
    return [float(x) for x in _PRINTED_SCORE.findall(txt)]


def gate(d: dict, pdf: pathlib.Path) -> tuple[bool, str]:
    """저장해도 되는가. ⚠️ 기준은 '100점인가'가 아니라 **인쇄된 것을 다 담았는가**다.

    처음엔 배점 합 100±8 로 걸렀는데, 학원 대비 편집본은 실제로 114.6점이거나
    배점이 일부만 인쇄돼 86.6점이다(둘 다 추출은 정확했다). 시험지 사정을 결함으로
    오인하면 멀쩡한 판독을 버린다 — 그래서 **자기 일관성**만 본다.
    """
    qs = d.get("questions") or []
    if len(qs) < MIN_Q:
        return False, f"문항 {len(qs)}개 — 분해 실패"
    nums = [q["number"] for q in qs]
    if nums != list(range(1, len(qs) + 1)):
        return False, f"문항 번호가 1~{len(qs)} 연속이 아님"
    blob = json.dumps(d, ensure_ascii=False)
    if re.search(r"⟨[0-9A-F]{4}⟩", blob):
        return False, "미확정 글리프 잔존"
    bad = [q["number"] for q in qs if q.get("choices") and len(q["choices"]) != 5]
    if bad:
        return False, f"선택지 5개가 아닌 문항 {bad[:4]}"
    pr = d.get("_printed_scores") or printed_scores(pdf)
    got = [q["score"] for q in qs if q.get("score") is not None]
    got += [x["score"] for q in qs for x in (q.get("sub_questions") or [])
            if x.get("score") is not None]
    if len(got) != len(pr) or abs(sum(got) - sum(pr)) > 0.05:
        return False, (f"배점 누락 — 인쇄 {len(pr)}개({sum(pr):.1f}) "
                       f"vs 추출 {len(got)}개({sum(got):.1f})")
    return True, f"문항 {len(qs)} · 배점 {sum(got):.1f}({len(got)}개)"


def born_digital(pdf: pathlib.Path) -> bool:
    try:
        doc = fitz.open(pdf)
        n = sum(len(doc[i].get_text().strip()) for i in range(min(3, doc.page_count)))
        doc.close()
        return n > 200
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()

    con = sqlite3.connect(DB)
    rows = con.execute(f"""SELECT id, school, grade, subject, year, semester, round
                           FROM exams
                           WHERE ocr_status='pending' AND src_ext='.pdf' AND {_scope.sql()}
                           ORDER BY year DESC, id""").fetchall()
    con.close()

    if a.report:
        prepped = born = 0
        for eid, *_ in rows:
            p = PAGES / str(eid) / "src.pdf"
            if not p.exists():
                continue
            prepped += 1
            born += born_digital(p)
        print(f"범위 {_scope.LABEL} — 남은 {len(rows):,}편")
        print(f"  페이지 준비됨 {prepped:,}편 중 born-digital {born:,}"
              f" ({born/max(1,prepped)*100:.0f}%) → 텍스트 레이어 후보")
        print(f"  나머지 {prepped-born:,}편은 스캔본 → 비전 필요")
        return

    ok = fail = skip = 0
    figq = nans = 0
    for eid, sch, gr, subj, yr, sem, rnd in rows:
        if ok + fail >= a.limit:
            break
        pdf = PAGES / str(eid) / "src.pdf"
        if not pdf.exists() or (OUT / f"{eid}.json").exists():
            skip += 1
            continue
        tag = f"[{sch}][{gr}][{subj}][{yr % 100}-{sem}-{rnd}]"
        try:
            d, ans = tl.extract(pdf, with_answers=True)
        except Exception as ex:
            fail += 1
            print(f"  비전필요 {eid} {tag} :: {str(ex).splitlines()[0][:60]}")
            continue
        good, why = gate(d, pdf)
        if not good:
            fail += 1
            print(f"  비전필요 {eid} {tag} :: {why}")
            continue
        nf = sum(1 for q in d["questions"]
                 for b in q.get("contents") or [] if b.get("type") == "figure")
        figq += nf
        ok += 1
        nans += len(ans)
        print(f"  OK   {eid} {tag}  {why}  그림 {nf}  정답 {len(ans)}")
        if not a.dry:
            d["_source"] = "textlayer"      # 비전 판독과 구분해 추적한다
            (OUT / f"{eid}.json").write_text(
                json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            # 정답면도 같은 경로에서 얻는다 — merge_answers.py 가 그대로 먹는다
            (OUT / f"{eid}.answers.json").write_text(
                json.dumps({"exam_id": eid, "items": ans, "_source": "textlayer"},
                           ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n{'[dry] ' if a.dry else ''}텍스트 레이어 {ok}편 통과 / {fail}편 비전 필요"
          f" / {skip}편 건너뜀(이미 있음·미준비)")
    if ok:
        print(f"  아낀 비전 토큰 ≈ {ok * 240_000:,} (편당 24만 실측 기준)")
        print(f"  정답 {nans:,}개도 함께 추출(정답면도 텍스트 레이어)")
        print(f"  그림 {figq}개는 bbox 로 기록 — 나중에 그 자리만 잘라 보강할 수 있다")


if __name__ == "__main__":
    main()
