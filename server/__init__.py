# -*- coding: utf-8 -*-
"""Math-Gen 로컬 HWP 커넥터 패키지.

웹(Math-Gen, 127.0.0.1:3000) ↔ 변환 엔진(testchange, core/) 사이의 로컬 HTTP 다리.
- connector.py   : HTTP 서버 (부모, COM 미사용)
- adapter.py     : wire payload(HwpPayload v2) → parse_ocr_response 봉투
- convert_cli.py : COM 격리 자식 (parse → build → write_exam_to_hwp)
"""
