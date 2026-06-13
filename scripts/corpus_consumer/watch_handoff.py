# 핸드오프 감시 (렌더/검수 소비자 세션용).
#   1) (옵션) git pull --ff-only 로 생산자(크롭1/크롭2) 푸시 수신
#   2) corpus/*/meta.json 스캔 → status 가 ocr_done* 인(=미검수) 학교 목록 출력
#      (reviewed*/validated* 는 이미 끝난 것이라 제외)
#
# 사용법:
#   python .testkit/watch_handoff.py            # 스캔만
#   python .testkit/watch_handoff.py --pull     # git pull 후 스캔
import sys, os, json, subprocess
from pathlib import Path

def _repo():
    from pathlib import Path as _P
    p=_P(__file__).resolve()
    for q in p.parents:
        if (q/'core').is_dir() and (q/'corpus').is_dir(): return q
    return p.parents[1]
REPO = _repo()
CORPUS = REPO / "corpus"


def main(argv):
    if "--pull" in argv:
        r = subprocess.run(["git", "-C", str(REPO), "pull", "--ff-only"],
                           capture_output=True, text=True)
        print("--- git pull ---")
        print((r.stdout or "").strip() or "(no stdout)")
        if r.stderr.strip():
            print(r.stderr.strip())
        print("----------------")

    ready, incomplete = [], []
    for d in sorted(CORPUS.iterdir()):
        if not d.is_dir():
            continue
        mj = d / "meta.json"
        if not mj.exists():
            continue
        try:
            j = json.loads(mj.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[parse-err] {d.name}: {e}")
            continue
        st = str(j.get("status", ""))
        if not st.startswith("ocr_done"):
            continue
        # 레퍼런스 키 규약: 신 corpus=reference_pdf(완료본), 구 corpus=ref_pdf. 둘 중 하나면 검수 가능.
        ref = str(j.get("reference_pdf", "") or j.get("ref_pdf", "") or "")
        ocr_files = sorted((d / "ocr").glob("p*_merged.json")) if (d / "ocr").exists() else []
        # 완성 핸드오프 게이트: 레퍼런스가 '실제 존재하는 파일' + ocr JSON 존재해야 1:1 검수 가능.
        # ref 가 안내문("완료본 없음…")이거나 파일 부재면 검수 불가 → 건너뜀(다음 틱 재확인).
        ref_ok = bool(ref) and ("\\" in ref or "/" in ref) and os.path.exists(ref)
        if ref_ok and ocr_files:
            ready.append((d.name, st, ref, len(ocr_files)))
        else:
            why = []
            if not ref:
                why.append("reference 없음")
            elif not (("\\" in ref or "/" in ref)):
                why.append("reference 가 경로 아님(안내문)")
            elif not os.path.exists(ref):
                why.append("reference 파일 부재")
            if not ocr_files:
                why.append("ocr JSON 없음")
            incomplete.append((d.name, st, ", ".join(why)))

    print(f"=== 완성 핸드오프(검수 가능): {len(ready)}건 ===")
    for name, st, ref, n in ready:
        print(f"  - {name}   [{st}] ocr={n}p")
        print(f"      ref_pdf: {ref}")
    if not ready:
        print("  (없음)")
    if incomplete:
        print(f"=== ocr_done 이나 미완성(생산자 작업중 추정, 건너뜀): {len(incomplete)}건 ===")
        for name, st, why in incomplete:
            print(f"  ~ {name}   [{st}]  ({why})")
    # 종료코드 = 완성 핸드오프 수(0=대기). 루프 게이트.
    return min(len(ready), 250)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
