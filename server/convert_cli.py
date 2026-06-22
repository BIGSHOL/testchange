# -*- coding: utf-8 -*-
"""COM 격리 자식 — stdin의 HwpPayload JSON → .hwpx(COM write_exam_to_hwp) 저장.

부모 connector.py가 subprocess로 호출한다(ThreadingHTTPServer 워커 스레드의
COM 초기화 문제 회피 + 타임아웃/크래시 격리). Python 3.11(pywin32) 필수 — 3.13 불가.

COM-only: write_exam_to_hwp 만 사용. write_exam_to_hwpx(비-COM)는 레이아웃 깨짐으로
사용 금지(사용자 확정). is_hwp_available()도 호출 안 함(한글을 켜므로) — 바로 변환,
실패 시 예외 전파 → 부모 500.

실행: python -m server.convert_cli --out <path>   (payload는 stdin bytes)
"""
import sys
import json
import argparse
import traceback
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ENGINE_ROOT = Path(__file__).resolve().parent.parent
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="출력 .hwpx 경로")
    ap.add_argument("--in", dest="infile", default=None,
                    help="입력 JSON 경로(없으면 stdin)")
    args = ap.parse_args()

    raw = (Path(args.infile).read_bytes()
           if args.infile else sys.stdin.buffer.read())
    if not raw:
        sys.stderr.write("빈 입력(payload 없음)\n")
        return 2
    payload = json.loads(raw)

    from server.adapter import adapt_payload
    from core.content_parser import parse_ocr_response, build_document
    from core.hwp_com_writer import write_exam_to_hwp

    envelope, meta = adapt_payload(payload)
    page = parse_ocr_response(envelope, page_number=1)
    document = build_document(
        [page],
        title=meta["title"],
        subject=meta["subject"],
        grade=meta["grade"],
    )

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_exam_to_hwp(document, out_path)  # COM → save_hwpx → .hwpx

    if not out_path.exists():
        sys.stderr.write("write_exam_to_hwp 완료했으나 출력 파일이 없습니다.\n")
        return 3
    sys.stderr.write(f"OK: {out_path} ({out_path.stat().st_size} bytes)\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
