# content_parser 후보정 회귀 단위테스트 (stdlib only, API·키 0).
#   python tests/test_content_parser.py
#
# 현재 커버: 한글↔숫자 띄어쓰기(_space_hangul_before_eq) + 서수 접두사 '제' 예외.
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core.content_parser import parse_ocr_response
from models.exam_document import ContentType


def _render(text: str) -> str:
    """발문 텍스트 하나를 파서에 통과시켜, 텍스트/수식을 평문으로 직렬화."""
    doc = {"header": "", "questions": [{"number": 1, "contents": [{"type": "text", "value": text}]}]}
    q = parse_ocr_response(doc, page_number=1).questions[0]
    out = []
    for b in q.contents:
        if b.type == ContentType.TEXT:
            out.append(b.value or "")
        else:
            out.append((b.value or "").strip())  # 수식은 값만(숫자/기호)
    return "".join(out)


# (입력, 직렬화 결과에 **반드시 포함**돼야 하는 부분문자열) — 띄어쓰기 검증.
_SPACING_CASES = [
    ("이 시행을36번 반복할 때", "시행을 36번"),    # 조사+숫자 → 띄움
    ("주사위를2번 던질 때", "주사위를 2번"),        # 조사+숫자 → 띄움
    ("제4사분면을 지나지 않는다", "제4사분면"),      # 서수 접두사 '제'+숫자 → 붙임
    ("그림의 제2사분면", "제2사분면"),              # 〃 (문장 중간)
    ("제100항까지", "제100항"),                   # 〃 (여러 자리)
    ("이 문제3을 풀어라", "문제 3"),               # '제'가 단어 끝 음절(문제) → 띄움
    ("과제3을 제출", "과제 3"),                    # 〃 (과제)
]


def _parse_q(text: str, score=None):
    doc = {"header": "", "questions": [{"number": 1, "score": score,
                                        "contents": [{"type": "text", "value": text}]}]}
    return parse_ocr_response(doc, page_number=1).questions[0]


# (입력 텍스트, OCR score 필드, 기대 score) — 배점 캡처(소수·총점) 검증. 본문에선 제거돼야 함.
_SCORE_CASES = [
    ("다음을 구하시오. [4.5점]", None, 4.5),    # 소수 배점: 캡처 없이 삭제되던 버그(M1)
    ("다음을 구하시오. [총 7점]", None, 7),     # 부모 총점: split 후 소실되던 버그(M2)
    ("다음을 구하시오. [3점]", None, 3),        # 기존 정수 경로 유지
    ("다음을 구하시오. [4점]", 5, 5),           # score 필드 우선(본문 캡처 안 함)
    ("값을 구하시오. [8점, 부분점수 있음]", None, 8),  # 점 뒤 부가문구: 쪼개진 배점 제거(수성고 #21)
]


def _parse_eq_blocks(value: str):
    """equation 블록 하나를 파서에 통과시켜 (type,value) 리스트로."""
    doc = {"header": "", "questions": [{"number": 1, "contents": [
        {"type": "equation", "value": value}]}]}
    q = parse_ocr_response(doc, page_number=1).questions[0]
    return [(b.type, (b.value or "")) for b in q.contents]


# B-1(상인고 #14): 복소수 상수 + 그리스 변수 근 나열 ``2-3i, \alpha, \beta`` 의 쉼표가
# 스푸리어스-쉼표 방어에 뭉개져 ``2-3i \alpha \beta`` 로 합쳐지던 회귀. 쉼표(텍스트)가
# 항목 사이에 보존돼야(개별 수식 + 텍스트 ", ").
def _check_comma_roots(fails):
    blocks = _parse_eq_blocks(r"2-3i, \alpha, \beta")
    eqs = [v for t, v in blocks if t == ContentType.EQUATION]
    texts = "".join(v for t, v in blocks if t == ContentType.TEXT)
    if len(eqs) < 3 or "," not in texts:
        fails.append(f"  B-1 근나열 쉼표: {blocks!r} (기대: 개별수식 3+ & 텍스트 쉼표)")


# D3(상인고 수1 #22): 박스 ASCII 수식 ``2a_{n+1} = a_n + a_{n+2}`` 가 ``_MATH_ATOM`` 의
# 중괄호 미흡수로 ``2a``+``_{``(평문)+… 로 쪼개져 중괄호·밑줄이 literal 로 새던 회귀.
# brace 첨자 원자가 통째 한 수식으로 묶이고, 평문에 ``_{``/``}`` 가 남지 않아야 한다.
def _check_brace_subscript(fails):
    from core.content_parser import _split_mixed_text_equation
    blocks = _split_mixed_text_equation("(가) 모든 자연수 n에 대하여 2a_{n+1} = a_n + a_{n+2} 이다.")
    eqs = [b.value or "" for b in blocks if b.type == ContentType.EQUATION]
    texts = "".join(b.value or "" for b in blocks if b.type == ContentType.TEXT)
    if not any("2a_{n+1}" in e and "a_{n+2}" in e for e in eqs):
        fails.append(f"  D3 brace 첨자: {[(b.type.name, b.value) for b in blocks]!r}")
    if "_{" in texts or "}" in texts:
        fails.append(f"  D3 brace leak: 평문에 중괄호 잔존: {texts!r}")


# 이므로-누수(상인고 수1 #12): ``_split_latex_commands`` 가 ``k \geq 2이므로`` 에서 공백 없는
# 한글 "이므로"를 수식에 흡수하던 회귀. 중괄호 밖(depth 0) 한글이면 끊고, ``\boxed{가}`` 처럼
# 중괄호 안 한글은 보호해 한 수식으로 유지돼야 한다.
def _check_korean_leak(fails):
    from core.content_parser import _split_latex_commands
    from models.exam_document import ContentType as CT
    blocks = _split_latex_commands(r"이 때 k \geq 2이므로")
    eq_txt = "".join(b.value or "" for b in blocks if b.type == CT.EQUATION)
    txt = "".join(b.value or "" for b in blocks if b.type == CT.TEXT)
    if "이므로" in eq_txt or "이므로" not in txt:
        fails.append(f"  이므로 누수: {[(b.type.name, b.value) for b in blocks]!r}")
    # \boxed{가} 는 중괄호 안 한글이라 수식에 유지(끊기지 않음)
    bx = _split_latex_commands(r"\boxed{가} 는 점")
    if not any(b.type == CT.EQUATION and "\\boxed{가}" in (b.value or "") for b in bx):
        fails.append(f"  boxed 보호: {[(b.type.name, b.value) for b in bx]!r}")


# R1~R7(상인고 수1 #4·#5·#12·#18, 2026-06-10): 소문항 마커·연산자 pull·각 로만·범위 공백.
def _check_box_polish(fails):
    from core.content_parser import (_split_mixed_text_equation, _split_latex_commands,
                                     _romanize_angle_letters, _merge_paren_range)
    from models.exam_document import ContentBlock, ContentType as CT
    # R1: 소문항 (i)(ii) 통째 한 수식, f(i) 함수호출은 보존
    b = _split_mixed_text_equation("(i), (ii)에 의하여")
    eqs = [x.value for x in b if x.type == CT.EQUATION]
    if "(i)" not in eqs or "(ii)" not in eqs:
        fails.append(f"  R1 소문항마커: {[(x.type.name, x.value) for x in b]!r}")
    b2 = _split_mixed_text_equation("함수 f(i)의 값")
    if not any(x.type == CT.EQUATION and "f(i)" in (x.value or "") for x in b2):
        fails.append(f"  R1 함수호출 보존: {[(x.type.name, x.value) for x in b2]!r}")
    # R2: 선행 연산자 = - 를 수식에 포함
    b3 = _split_latex_commands(r"= - \frac{1}{2} 에서")
    if not any(x.type == CT.EQUATION and (x.value or "").startswith("= -") for x in b3):
        fails.append(f"  R2 연산자 pull: {[(x.type.name, x.value) for x in b3]!r}")
    # R5/R6: 각(angle) 단일 대문자 로만 — \cos A, A=45°
    ang = _romanize_angle_letters([ContentBlock(type=CT.EQUATION, value=r"\frac{b}{\cos A}"),
                                   ContentBlock(type=CT.EQUATION, value=r"A=45^\circ")])
    av = "".join(x.value or "" for x in ang)
    if r"\cos \mathrm{A}" not in av or r"\mathrm{A}=45" not in av:
        fails.append(f"  R5/R6 각 로만: {av!r}")
    # R7: 점화식 + (n=1,2,3⋯) ~ 공백 병합
    mg = _merge_paren_range([ContentBlock(type=CT.EQUATION, value="a_{n+1}=a_n+4"),
                             ContentBlock(type=CT.TEXT, value=" "),
                             ContentBlock(type=CT.EQUATION, value="(n=1, 2, 3 \\cdots)")])
    if not (len(mg) == 1 and "~" in (mg[0].value or "")):
        fails.append(f"  R7 범위 공백병합: {[(x.type.name, x.value) for x in mg]!r}")
    # 괄호base 거듭제곱 (능인고 수1 #18): (1+h)^n 이 (·)^ 로 쪼개져 ^ 가 literal 캐럿으로
    # 새던 것 — 한 수식에 (1+h)^n 통째 묶여야(_MATH_ATOM 이 괄호식도 원자로).
    b4 = _split_mixed_text_equation("수 n에 대하여 (1+h)^n > 1+nh가 성립")
    if not any(x.type == CT.EQUATION and "(1+h)^n" in (x.value or "") for x in b4):
        fails.append(f"  괄호base 거듭제곱: {[(x.type.name, x.value) for x in b4]!r}")
    if any(x.type == CT.TEXT and "^" in (x.value or "") for x in b4):
        fails.append(f"  ^ 캐럿 평문 누수: {[(x.type.name, x.value) for x in b4]!r}")


# W1~W5(월암중 중2 #5·#6·#11·#15·#19, 2026-06-11): 박스 cases 원자·나란히 수식·참조어 머리.
def _check_wolam_box_fixes(fails):
    from core.content_parser import _split_latex_commands, _RAW_BOX_MARK_RE
    from models.exam_document import ContentType as CT
    # W1: \begin{cases}…\end{cases} 통째 한 수식 원자 (begin·cases 산산조각 → literal 방지)
    b = _split_latex_commands(r"<상자> \begin{cases} 4x+3y=4 \\ x+3y=10 \end{cases}")
    eqs = [x.value for x in b if x.type == CT.EQUATION]
    if len(eqs) != 1 or not eqs[0].startswith(r"\begin{cases}") or not eqs[0].endswith(r"\end{cases}"):
        fails.append(f"  W1 cases 원자: {[(x.type.name, x.value) for x in b]!r}")
    # W2: cases 2개 나란히 → 각각 원자
    b2 = _split_latex_commands(
        r"\begin{cases} 3x+4y=2 \\ 2x+my=9 \end{cases}  \begin{cases} mx+ny=-7 \\ 4x+2y=6 \end{cases}")
    eqs2 = [x.value for x in b2 if x.type == CT.EQUATION]
    if len(eqs2) != 2 or not all(v.startswith(r"\begin{cases}") for v in eqs2):
        fails.append(f"  W2 cases x2: {[(x.type.name, x.value) for x in b2]!r}")
    # W3: 깊이 0 더블스페이스 = 별개 수식 경계 + 둘째 머리(4^x) 수식 승격
    b3 = _split_latex_commands(r"(3^x)^3 \times 9^y = 3^{11}  4^x \times 2^y = 128")
    if any(x.type == CT.TEXT and "^" in (x.value or "") for x in b3):
        fails.append(f"  W3 ^ 평문 누수: {[(x.type.name, x.value) for x in b3]!r}")
    joined3 = " | ".join(x.value for x in b3 if x.type == CT.EQUATION)
    if "128" not in joined3 or "3^{11}" not in joined3:
        fails.append(f"  W3 등식 소실: {joined3!r}")
    # W4: 명령 앞 연산자+식별자(y=-) 모두 수식으로 — y 평문(정자) 잔존 방지
    b4 = _split_latex_commands(r"ㄷ. y=-\frac{c}{a}x-\frac{b}{a}")
    if not any(x.type == CT.EQUATION and (x.value or "").startswith("y=-") for x in b4):
        fails.append(f"  W4 y=- 흡수: {[(x.type.name, x.value) for x in b4]!r}")
    # W5: 박스 머리 vs 발문 인라인 참조 (<보기> 중/에서·조사직결 = 참조, 그 외 = 박스)
    for s, want in [("<보기> 중 일차함수", False), ("<보기>에서 고른", False),
                    ("<보기> ㄱ. 항목", True), ("<조건> 한 미지수에 대한", True),
                    ("<상자> 18 13", True), ("<보기> 중간값", True)]:
        got = bool(_RAW_BOX_MARK_RE.match(s))
        if got != want:
            fails.append(f"  W5 박스머리 판정: {s!r} → {got} (기대 {want})")


# J1~J2(장산중 중3 #5·#13, 2026-06-11): \therefore 명령 수식 포함 + 자모 라벨 한글 가드.
def _check_jangsan_fixes(fails):
    from core.content_parser import _split_latex_commands, _split_mixed_text_equation
    from models.exam_document import ContentType as CT
    # J1: \therefore 가 _LATEX_CMD_RE 에 없어 TEXT 로 남아 literal ₩therefore 렌더되던 회귀.
    b = _split_latex_commands(r"양변을 정리하면 \therefore x=\frac{3\pm\boxed{다}}{2}")
    eqs = [x.value or "" for x in b if x.type == CT.EQUATION]
    txts = "".join(x.value or "" for x in b if x.type == CT.TEXT)
    if "\\therefore" in txts or not any("\\therefore" in e and "\\frac" in e for e in eqs):
        fails.append(f"  J1 therefore: {[(x.type.name, x.value) for x in b]!r}")
    # J2: 자모 라벨(ㄷ.ㄹ.) 세그먼트 — 음절만 보는 한글 가드에 걸려 ASCII 수식이 평문 잔존.
    b2 = _split_mixed_text_equation(" • ㄷ. y=4x^2+1 • ㄹ. y=-(x+1)^2-3")
    eqs2 = [x.value or "" for x in b2 if x.type == CT.EQUATION]
    txts2 = "".join(x.value or "" for x in b2 if x.type == CT.TEXT)
    if "^" in txts2 or not any("4x^2" in e for e in eqs2) or not any("(x+1)^2" in e for e in eqs2):
        fails.append(f"  J2 자모 가드: {[(x.type.name, x.value) for x in b2]!r}")
    # J3(새론중 서답형2): 채점기준 <상자> 안 항목별 배점 [1점][3점]…이 발문 배점으로 오인돼
    # 통째 소실되던 회귀. 박스 머리 이후 [N점]은 보존, 발문 배점은 여전히 제거돼야 한다.
    # (실제 OCR 은 발문·박스를 별도 text 블록으로 준다 — _parse_q 단일블록 헬퍼로는 재현 불가.)
    doc3 = {"header": "", "questions": [{"number": 1, "score": None, "contents": [
        {"type": "text", "value": "넓이를 구하시오. [10점]"},
        {"type": "text", "value": "<상자> [배점] / 미지수 정하기 [1점] / 풀기 [2점]"}]}]}
    q3 = parse_ocr_response(doc3, page_number=1).questions[0]
    body3 = "".join((b.value or "") for b in q3.contents)
    if q3.score != 10:
        fails.append(f"  J3 발문 배점 캡처: score={q3.score!r} (기대 10)")
    if "10점" in body3:
        fails.append("  J3 발문 배점 본문 잔존")
    if "1점" not in body3 or "2점" not in body3:
        fails.append("  J3 채점기준 박스 배점 소실")


# K1(경구중 #5 ㄷ·ㅁ·#13 ㄹ, 2026-06-11): ASCII 수식의 선행 단항부호(-5x+6=…)가 평문
# 하이픈으로 수식 밖에 떨어지던 것 — 흡수. 이항(f(x) - 5x)·범위(3-5개)는 기존 동작 보존.
def _check_ascii_leading_sign(fails):
    from core.content_parser import _split_mixed_text_equation
    from models.exam_document import ContentType as CT
    for s, want_eq in [("ㄷ. -5x+6=6-5x", "-5x+6=6-5x"),
                       ("값은 -5이다", "-5")]:
        b = _split_mixed_text_equation(s)
        eqs = [x.value for x in b if x.type == CT.EQUATION]
        txts = "".join(x.value or "" for x in b if x.type == CT.TEXT)
        if want_eq not in eqs or "-" in txts:
            fails.append(f"  K1 단항부호 흡수: {s!r} → {[(x.type.name, x.value) for x in b]!r}")
    # 이항: f(x) - 5x 는 한 수식(또는 병합 대상)으로 — '-' 평문 잔존만 아니면 OK
    b2 = _split_mixed_text_equation("함수 f(x) - 5x의 값")
    if not any(x.type == CT.EQUATION and "f(x)" in (x.value or "") and "5x" in (x.value or "")
               for x in b2):
        fails.append(f"  K1 이항 보존: {[(x.type.name, x.value) for x in b2]!r}")
    # 전체 파이프라인: 보기 항목 ㅁ '=-' 분리가 한 수식으로 재병합 + 선행 '-' 포함
    doc = {"header": "", "questions": [{"number": 1, "contents": [
        {"type": "text", "value": "<보기> ㄱ. 2-3x=5 • ㅁ. -3(x+1)+2=-3x-1"}]}]}
    q = parse_ocr_response(doc, page_number=1).questions[0]
    eqs = [b.value or "" for b in q.contents if b.type == ContentType.EQUATION]
    txts = "".join(b.value or "" for b in q.contents if b.type == ContentType.TEXT)
    if not any(e.startswith("-3(x+1)+2") and "3x-1" in e for e in eqs) or "-3(" in txts:
        fails.append(f"  K1 파이프라인 ㅁ: eqs={eqs!r} txts={txts!r}")


def _check_saebon_fixes(fails):
    """새본리중 중3 B형 회귀(2026-06-12) — L1 첨자 절단·L2 자모 수식 병합·L3 underline
    JSON 키·L4 반원 기하 키워드."""
    import re
    from models.exam_document import ContentType as CT
    # L1: x^2-\frac… 의 brace-less 첨자가 'x^' 고아 수식으로 절단되지 않아야(새본리중 #7).
    doc = {"header": "", "questions": [{"number": 1, "contents": [
        {"type": "text",
         "value": "<상자> 2x^2-7x-3=0 • x^2-\\frac{7}{2}x+A=\\frac{3}{2}+A • (x+B)^2=C"}]}]}
    q = parse_ocr_response(doc, page_number=1).questions[0]
    eqs = [b.value or "" for b in q.contents if b.type == CT.EQUATION]
    if any(e.rstrip().endswith(("^", "_")) for e in eqs):
        fails.append(f"  L1 첨자 고아 수식: eqs={eqs!r}")
    if not any(e.startswith("x^2-") and "+A=" in e for e in eqs):
        fails.append(f"  L1 첨자 절단: eqs={eqs!r}")
    # L2: 자모 라벨(ㄴ.ㄷ.)·불릿이 수식 안으로 병합되면 안 됨(새본리중 #17 보기 박스).
    doc2 = {"header": "", "questions": [{"number": 1, "contents": [
        {"type": "text",
         "value": "<보기> ㄱ. y=\\frac{1}{2}x^2 • ㄴ. y=-3x^2-2 • ㄷ. y=3x^2"}]}]}
    q2 = parse_ocr_response(doc2, page_number=1).questions[0]
    eqs2 = [b.value or "" for b in q2.contents if b.type == CT.EQUATION]
    if any(re.search(r"[ㄱ-ㆎ•]", e) for e in eqs2):
        fails.append(f"  L2 자모/불릿 수식 병합: eqs={eqs2!r}")
    if not any("3x^2-2" in e for e in eqs2) or not any("y=3x^2" in e.replace(" ", "") for e in eqs2):
        fails.append(f"  L2 항목 수식 소실: eqs={eqs2!r}")
    # L3: OCR JSON 의 {"underline": true} 속성 인코딩도 강조 run 으로(새본리중 #2·#13·#17).
    doc3 = {"header": "", "questions": [{"number": 1, "contents": [
        {"type": "text", "value": "해가 되지 "},
        {"type": "text", "value": "않는", "underline": True},
        {"type": "text", "value": " 것은?"}]}]}
    q3 = parse_ocr_response(doc3, page_number=1).questions[0]
    if not any(b.type == CT.TEXT and b.underline and b.value == "않는" for b in q3.contents):
        fails.append(f"  L3 underline 속성: {[(b.type.name, b.value, b.underline) for b in q3.contents]!r}")
    # L4: '반원의 중심/지름' 기하 문맥 — 점 이름 O 로만화(새본리중 #20).
    doc4 = {"header": "", "questions": [{"number": 1, "contents": [
        {"type": "text", "value": "반원의 중심을 "},
        {"type": "equation", "value": "O"},
        {"type": "text", "value": "라고 하자."}]}]}
    q4 = parse_ocr_response(doc4, page_number=1).questions[0]
    eqs4 = [b.value or "" for b in q4.contents if b.type == CT.EQUATION]
    if not any("\\mathrm{O}" in e for e in eqs4):
        fails.append(f"  L4 반원 기하 로만: eqs={eqs4!r}")


def _check_sangwon_fixes(fails):
    """상원고 공수1 B형 회귀(2026-06-12) — M1 단서 괄호 안 LaTeX 명령 무한재귀."""
    from models.exam_document import ContentType as CT
    # M1: "(단, \overline{α}와 …)" — 함수꼴 괄호 흡수("P(X" 보호)가 한글 경계의 여는괄호
    # 보호("(우변)")와 맞물려 소비 0 → _split_latex_commands 무한 재귀(RecursionError).
    # 중1 은 단서 괄호 안에 LaTeX 명령이 없어 잠복, 고1 켤레복소수 표기가 첫 발화.
    doc = {"header": "", "questions": [{"number": 1, "contents": [
        {"type": "text",
         "value": "두 복소수 \\alpha=3-i와 \\beta=2+2i에 대하여 "
                  "\\alpha\\overline{\\alpha}+\\beta\\overline{\\beta}의 값은? "
                  "(단, \\overline{\\alpha}와 \\overline{\\beta}는 각각 \\alpha와 \\beta의 켤레복소수이다.)"}]}]}
    try:
        q = parse_ocr_response(doc, page_number=1).questions[0]
    except RecursionError:
        fails.append("  M1 단서괄호 LaTeX 무한재귀(RecursionError)")
        return
    eqs = [b.value or "" for b in q.contents if b.type == CT.EQUATION]
    if not any("\\overline" in e for e in eqs):
        fails.append(f"  M1 \\overline 수식 객체화 누락: eqs={eqs!r}")
    texts = "".join(b.value or "" for b in q.contents if b.type == CT.TEXT)
    if "켤레복소수" not in texts:
        fails.append(f"  M1 단서 문장 소실: texts={texts!r}")


def _check_seonggwang_fixes(fails):
    """성광중 중2 B형 2건 — (1) text 블록 전체가 단일 LaTeX 수식일 때 평문 강등 금지
    (#12 선택지 '482\\mathrm{cm}' raw 누수), (2) 온도 단위 °C/°F 병합(#17 C 단독 이탤릭)."""
    from core.latex_to_hwpeq import latex_to_hwpeq
    CT = ContentType
    # (1) #12 선택지: text "482\mathrm{cm}" → EQUATION(평문 강등 금지) → "482 rm`cm"(정자 단위)
    doc = {"header": "", "questions": [{"number": 1, "contents": [{"type": "text", "value": "X"}],
            "choices": [{"number": 1, "contents": [{"type": "text", "value": "482\\mathrm{cm}"}]}]}]}
    ch = parse_ocr_response(doc, page_number=1).questions[0].choices[0]
    eq = [b for b in ch.contents if b.type == CT.EQUATION]
    if not eq:
        fails.append(f"  SG1 단일수식 선택지 평문 강등(EQ 없음): {[(b.type.name, b.value) for b in ch.contents]!r}")
    else:
        hw = latex_to_hwpeq(eq[0].value)
        if "mathrm" in hw or "₩" in hw:
            fails.append(f"  SG1 선택지 단위 raw 누수: {hw!r}")
        if "rm" not in hw or "cm" not in hw:
            fails.append(f"  SG1 선택지 cm 단위 정자화 실패: {hw!r}")
    # (2) #17 본문: "6°C씩" → EQ "6°\mathrm{C}" → "6°rm C"(C 정자), 단독 EQ "C"(이탤릭) 없음
    q = _parse_q("물의 온도가 6°C씩 올라가고 20°C까지 데운다")
    eqs = [b.value or "" for b in q.contents if b.type == CT.EQUATION]
    if any(v.strip() == "C" for v in eqs):
        fails.append(f"  SG2 °C 분리(단독 이탤릭 C 잔존): eqs={eqs!r}")
    deg = [v for v in eqs if "°" in v]
    if not deg or not all("mathrm{C}" in v for v in deg):
        fails.append(f"  SG2 온도 단위 병합 실패: eqs={eqs!r}")
    else:
        hw = latex_to_hwpeq(deg[0])
        if "rm" not in hw:
            fails.append(f"  SG2 °C 정자화 실패: {hw!r}")
    # 무회귀: 각도 45°(뒤가 C/F 아님)는 병합 안 함
    q2 = _parse_q("∠A=45°이고 나머지를 구하라")
    if any("mathrm{C}" in (b.value or "") for b in q2.contents):
        fails.append("  SG2 각도 45° 오병합(°C 아닌데 병합)")


def _check_sinmyeong_fixes(fails):
    """신명여중 중1 #7 — 박스 마커 직후 LaTeX 명령(``<상자> \\frac…``)에서 선행 연산자
    흡수가 마커의 닫는 ``>`` 를 끌어가 마커가 ``<상자 `` 로 깨지고 수식이 ``> \\frac…``
    으로 새던 회귀. 마커는 자기 TEXT 블록으로 보호돼야 한다."""
    from core.content_parser import _split_latex_commands
    CT = ContentType
    b = _split_latex_commands(r"<상자> \frac{1}{3}x+4=-1  \frac{1}{3}x=-5  \therefore x=-15")
    txts = [x.value or "" for x in b if x.type == CT.TEXT]
    eqs = [x.value or "" for x in b if x.type == CT.EQUATION]
    if not any(t.strip() == "<상자>" for t in txts):
        fails.append(f"  SM1 마커 깨짐(온전한 <상자> TEXT 없음): {[(x.type.name, x.value) for x in b]!r}")
    if any(e.lstrip().startswith(">") for e in eqs):
        fails.append(f"  SM1 마커 > 가 수식으로 흡수: eqs={eqs!r}")
    # env 경로 무회귀: <상자> \begin{cases}… 는 원래 안전(_LATEX_ENV_RE 선행) — 유지 확인.
    b2 = _split_latex_commands(r"<상자> \begin{cases}y-ax=4 \\ 2x-y=-2\end{cases}")
    txts2 = [x.value or "" for x in b2 if x.type == CT.TEXT]
    if not any(t.strip() == "<상자>" for t in txts2):
        fails.append(f"  SM1 env 경로 마커 회귀: {[(x.type.name, x.value) for x in b2]!r}")
    # 참조어 무회귀: '<보기> 중 고른 것은' 은 박스 머리가 아니다(부정전망) — 가드 미발동.
    b3 = _split_latex_commands(r"<보기> 중 \frac{1}{2}보다 큰 것은")
    if (b3[0].type == CT.TEXT and b3[0].value or "").strip() == "<보기>":
        fails.append("  SM1 참조어 '<보기> 중' 오분리(박스 머리로 오인)")


def _check_sangwon_go1_fixes(fails):
    """상원고 공수1 #18 — env(pmatrix) 직전 식별자 미흡수로 행렬곱 ``, A`` 의 A 가 한글
    없는 TEXT 조각으로 남아 평문(정자) 렌더되던 회귀. env 원자에 선행 식별자를 흡수하고,
    finalize 의 eq·연산자·eq 병합이 ``A(…)=(…)`` 를 한 수식으로 만들어야 한다."""
    CT = ContentType
    v = (r'행렬 A에 대하여 A\begin{pmatrix} 1 \\ 2 \end{pmatrix}='
         r'\begin{pmatrix} k \\ 1 \end{pmatrix}, A\begin{pmatrix} 2 \\ -1 \end{pmatrix}='
         r'\begin{pmatrix} 0 \\ -8 \end{pmatrix}이고')
    doc = {"header": "", "questions": [{"number": 1, "contents": [{"type": "text", "value": v}]}]}
    q = parse_ocr_response(doc, page_number=1).questions[0]
    eqs = [b.value or "" for b in q.contents if b.type == CT.EQUATION]
    txts = [b.value or "" for b in q.contents if b.type == CT.TEXT]
    # 행렬곱 식 2개가 각각 A 포함 한 수식으로(= 병합 포함)
    mat_eqs = [e for e in eqs if "pmatrix" in e]
    if len(mat_eqs) != 2 or not all(e.startswith("A\\begin") and "=" in e for e in mat_eqs):
        fails.append(f"  SW1 행렬곱 식별자 흡수/병합 실패: {mat_eqs!r}")
    # A 가 평문 TEXT 로 남으면 정자 렌더(결함)
    if any("A" in t for t in txts):
        fails.append(f"  SW1 A 평문 잔존(정자 렌더): txts={txts!r}")
    # SW2: 행렬 문맥 가드 — 행렬곱 AB(2글자 대문자)가 '항상 로만' 규칙에 걸려 정자로
    # 깨지면 안 된다(#22 AB=pmatrix·#12 명제 AB=AC — 원본 이탤릭). latex_to_hwpeq 의
    # 변환 레벨 로만화(_apply_roman_labels)까지 차단하려 \mathit{} 명시 → `it {AB}`.
    from core.latex_to_hwpeq import latex_to_hwpeq as _l2h
    v2 = r'행렬 A와 B에 대하여 AB=\begin{pmatrix} -3 & -5 \\ 2b-4 & -6 \end{pmatrix}일 때'
    doc2 = {"header": "", "questions": [{"number": 1, "contents": [{"type": "text", "value": v2}]}]}
    q2 = parse_ocr_response(doc2, page_number=1).questions[0]
    if any("\\mathrm" in (b.value or "") for b in q2.contents):
        fails.append(f"  SW2 행렬 AB 오로만화: {[(b.type.name, b.value) for b in q2.contents]!r}")
    eqs2 = [b.value or "" for b in q2.contents if b.type == CT.EQUATION and "AB" in (b.value or "")]
    if not eqs2 or "\\mathit{AB}" not in eqs2[0]:
        fails.append(f"  SW2 행렬 AB \\mathit 보호 누락: {eqs2!r}")
    elif "rm {AB}" in _l2h(eqs2[0]) or "it {AB}" not in _l2h(eqs2[0]):
        fails.append(f"  SW2 변환기 레벨 AB 정자화 잔존: {_l2h(eqs2[0])!r}")
    doc3 = {"header": "", "questions": [{"number": 1, "contents": [
        {"type": "text", "value": "삼각형의 변 AB의 길이가 5일 때"}]}]}
    q3 = parse_ocr_response(doc3, page_number=1).questions[0]
    if not any("\\mathrm{AB}" in (b.value or "") for b in q3.contents):
        fails.append("  SW2 기하 AB 로만 회귀(이탤릭으로 풀림)")


def _check_daejin_go1_fixes(fails):
    """대진고 공수1 — (1) #1 ``<상자> 4x-7 \\le …`` 관계연산자 명령 좌변 ASCII 흡수,
    (2) #16 박스 ○ 불릿이 ASCII 수식에 흡수돼 항목 줄바꿈이 깨지던 회귀."""
    CT = ContentType
    # (1) 좌변 흡수 — 4x-7 이 평문으로 떨어지면 정자 렌더
    doc = {"header": "", "questions": [{"number": 1, "contents": [
        {"type": "text", "value": r"<상자> 4x-7 \le 7x-1 \le 3x+15"}]}]}
    q = parse_ocr_response(doc, page_number=1).questions[0]
    eqs = [b.value or "" for b in q.contents if b.type == CT.EQUATION]
    if not any(e.startswith("4x-7") and "3x+15" in e for e in eqs):
        fails.append(f"  DJ1 \\le 좌변 흡수 실패: {[(b.type.name, b.value) for b in q.contents]!r}")
    # (2) ○ 불릿 분리 — 수식에 흡수되면 _BOX_BREAK_RE 가 줄을 못 끊음
    doc2 = {"header": "", "questions": [{"number": 16, "contents": [
        {"type": "text", "value": r"<상자> ○ |x|+2|y|+3|z|=11 ○ xyz \ne 0"}]}]}
    q2 = parse_ocr_response(doc2, page_number=1).questions[0]
    eqs2 = [b.value or "" for b in q2.contents if b.type == CT.EQUATION]
    if any("○" in e for e in eqs2):
        fails.append(f"  DJ1 ○ 불릿 수식 흡수: eqs={eqs2!r}")
    txts2 = [b.value or "" for b in q2.contents if b.type == CT.TEXT]
    if sum(t.count("○") for t in txts2) != 2:
        fails.append(f"  DJ1 ○ 불릿 TEXT 분리 실패: txts={txts2!r}")


def _check_dasa_fixes(fails):
    """다사중 #13(배포 GUI 보고) — 박스 첫 항목이 인라인 수식 분리로 text+eq 로 쪼개진
    여러 raw 블록일 때 `<보기> ㄱ. 점` 을 자기완결로 오인해 ㄴㄷㄹ 가 박스 밖으로 새던
    회귀. 후속 항목 라벨(• ㄴ.) 신호로 박스 연속 판정. 학남고형 post(eq+조사) 분리 유지."""
    CT = ContentType
    doc = {"header": "", "questions": [{"number": 13, "contents": [
        {"type": "text", "value": "옳은 것만을 <보기>에서 있는 대로 고른 것은?"},
        {"type": "text", "value": "<보기> ㄱ. 점 "},
        {"type": "equation", "value": "(6, 3)"},
        {"type": "text", "value": "을 지난다. • ㄴ. "},
        {"type": "equation", "value": "x"},
        {"type": "text", "value": "축과 만나는 점의 좌표는 "},
        {"type": "equation", "value": "(-4, 0)"},
        {"type": "text", "value": "이다."},
    ]}]}
    q = parse_ocr_response(doc, page_number=1).questions[0]
    # 박스 미분리(자기완결 오인 금지): 'ㄴ' 라벨 텍스트가 contents 에 남아 있어야 한다
    # (post 로 떼였으면 head 에서 사라짐 — parse 결과 contents 는 head+post 합본이라
    # 분리 자체보다 box 마커 뒤 어떤 블록도 손실되지 않았는지 + 마커가 온전한지 본다).
    joined = "".join((b.value or "") for b in q.contents)
    if "ㄴ" not in joined or "<보기>" not in joined:
        fails.append(f"  DS1 박스 연속 오분리: {joined[:120]!r}")
    # 학남고형 무회귀: 자기완결 박스 + eq·조사 post 는 분리 유지(box_member 태그 존재)
    doc2 = {"header": "", "questions": [{"number": 20, "contents": [
        {"type": "text", "value": "<조건> (가) E(Y)=20 이다. (나) V(Y)=16 이다."},
        {"type": "equation", "value": "P(Y \\le 29)"},
        {"type": "text", "value": "의 값을 구하시오."},
    ]}]}
    q2 = parse_ocr_response(doc2, page_number=1).questions[0]
    tagged = [b for b in q2.contents if getattr(b, "box_member", False)]
    untagged_tail = [b for b in q2.contents if not getattr(b, "box_member", False)
                     and "구하시오" in (b.value or "")]
    if not tagged or not untagged_tail:
        fails.append("  DS1 학남고형 post 분리 회귀(box_member 태그/post 소실)")


def _check_daegeon_go1_fixes(fails):
    """대건고 #19(고1 공수1) — 소문항 원문자 항목 ``㉢ A^2``(caret 표기, 별도 text 블록)가
    한글·LaTeX 없어 평문화돼 ``^`` 가 노출되던 것. 첨자 패턴이면 ASCII 경로 통과 → 수식 객체."""
    CT = ContentType
    from core.content_parser import _split_mixed_text_equation
    # ㉢ A^2 → TEXT '㉢ ' + EQUATION 'A^2'(위첨자). ㉠ AC(첨자 없음)는 평문 유지.
    r = _split_mixed_text_equation("㉢ A^2")
    if not (len(r) == 2 and r[0].type == CT.TEXT and r[1].type == CT.EQUATION
            and r[1].value == "A^2"):
        fails.append(f"  DG1 원문자 첨자 항목 분리 실패: {[(str(b.type).split('.')[-1], b.value) for b in r]!r}")
    r2 = _split_mixed_text_equation("값 A^2 이다")      # 한글+caret 혼합도 caret 토큰 수식화
    if not any(b.type == CT.EQUATION and b.value == "A^2" for b in r2):
        fails.append(f"  DG1 혼합 caret 미추출: {[(str(b.type).split('.')[-1], b.value) for b in r2]!r}")
    r3 = _split_mixed_text_equation("㉠ AC")           # 첨자 없는 항목은 평문(무회귀)
    if any(b.type == CT.EQUATION for b in r3):
        fails.append(f"  DG1 첨자 없는 항목 오추출: {[(str(b.type).split('.')[-1], b.value) for b in r3]!r}")
    # 원문자 항목 줄바꿈 판정(_is_circled_item_start)
    from core.hwp_com_writer import _is_circled_item_start
    from models.exam_document import ContentBlock as _CB
    if not _is_circled_item_start(_CB(type=CT.TEXT, value="㉢ A")):
        fails.append("  DG1 원문자 항목 시작 미감지")
    if _is_circled_item_start(_CB(type=CT.TEXT, value="보기 ㉢ 은")):  # 중간 참조는 미발동
        fails.append("  DG1 인라인 원문자 오감지")


def _check_jung2_2sem_fixes(fails):
    """강북중 중2 2학기 #5 — 닮음 도형 선택지의 각(∠R·∠P)이 로만화 안 되던 것.
    _parse_choice 에 _romanize_angle_letters 누락 → 발문 기하문맥 미감지 시 ∠ 단일대문자 이탤릭.
    선택지 경로에 각 로만화 추가(∠ 본질적 기하라 게이트 없이)."""
    from core.content_parser import _parse_choice
    from core.latex_to_hwpeq import latex_to_hwpeq as l2h
    # 발문 기하문맥 없이도(parent_geo=False) ∠ 뒤 단일 대문자는 로만
    c = _parse_choice({"number": 1, "contents": [
        {"type": "equation", "value": r"\angle R=80°"}]}, parent_geo=False)
    eqs = [b.value for b in c.contents if b.type.name == "EQUATION"]
    if not any(r"\angle \mathrm{R}" in (e or "") for e in eqs):
        fails.append(f"  J2S ∠R 로만화 실패: {eqs!r}")
    # 확률 P 도 ∠ 뒤면 로만(렌더 italicize_stat=False 에서 rm P)
    cP = _parse_choice({"number": 2, "contents": [
        {"type": "equation", "value": r"\angle P=125°"}]}, parent_geo=False)
    eqP = [b.value for b in cP.contents if b.type.name == "EQUATION"]
    if not any(r"\angle \mathrm{P}" in (e or "") for e in eqP):
        fails.append(f"  J2S ∠P 로만화 실패: {eqP!r}")
    if "angle rm P" not in l2h(eqP[0], italicize_stat=False):
        fails.append(f"  J2S ∠P 렌더 로만 실패: {l2h(eqP[0], italicize_stat=False)!r}")
    # 무회귀: ∠ 없는 확통 선택지 P(X=2) 는 이탤릭 유지(로만화 안 함)
    cx = _parse_choice({"number": 3, "contents": [
        {"type": "equation", "value": r"P(X=2)"}]}, parent_geo=False)
    eqx = [b.value for b in cx.contents if b.type.name == "EQUATION"]
    if any(r"\mathrm{P}" in (e or "") for e in eqx):
        fails.append(f"  J2S 확통 P 오로만화: {eqx!r}")
    # #12 "A 지점에서 C 지점까지"(경우의 수·비기하)는 기하 오판 금지(지점=위치, 디코이)
    from core.content_parser import _has_geometry_context
    from models.exam_document import ContentBlock as _CB2, ContentType as _CT2
    if _has_geometry_context([_CB2(type=_CT2.TEXT, value="A 지점에서 C 지점까지 가는 경우의 수")]):
        fails.append("  J2S '지점'(비기하) 기하 오판")
    if not _has_geometry_context([_CB2(type=_CT2.TEXT, value="점 P 를 지나는 직선")]):
        fails.append("  J2S 진짜 기하(점) 미감지")
    # #6 분수+단위 cm 로만화(분수 닫는 } 뒤), a_1L(첨자 뒤 변수 L)은 보호
    if "rm`cm" not in l2h(r"\frac{8}{3}cm", italicize_stat=False):
        fails.append(f"  J2S 분수+cm 미로만: {l2h(chr(92)+'frac{8}{3}cm', italicize_stat=False)!r}")
    if "rm`L" in l2h("a_1L", italicize_stat=False):
        fails.append(f"  J2S a_1L 변수 L 오로만(O2 회귀): {l2h('a_1L', italicize_stat=False)!r}")
    # 평행기호 ⫽ 리터럴(세로 ││ 금지)
    if "⫽" not in l2h(r"\overline{DE} \parallel \overline{BC}", italicize_stat=False):
        fails.append(f"  J2S 평행 ⫽ 미적용: {l2h(chr(92)+'overline{DE} '+chr(92)+'parallel '+chr(92)+'overline{BC}', italicize_stat=False)!r}")
    # #1 ① 평행관계 + 등식 쉼표 나열 — 쉼표가 스푸리어스로 드롭되며 BC·AD 붙던 것
    # (_has_toplevel_relation 에 \parallel 누락). 관계+관계는 쉼표 보존(개별 수식).
    from core.content_parser import _split_comma_equations
    from models.exam_document import ContentBlock as _CB3, ContentType as _CT3
    r1 = _split_comma_equations([_CB3(type=_CT3.EQUATION,
        value=r"\overline{AD} \parallel \overline{BC},\ \overline{AD}=\overline{BC}=6cm")])
    if not any(b.type.name == "TEXT" and "," in (b.value or "") for b in r1):
        fails.append(f"  J2S 평행+등식 쉼표 드롭: {[(b.type.name, b.value) for b in r1]!r}")


# SH1·SH2 (강동고·강북고 수하 23-2-기말 완료기반, 2026-06-14): 조합/순열 좌측첨자·집합 괄호.
def _check_suha_fixes(fails):
    from core.content_parser import _split_latex_commands
    from models.exam_document import ContentType as CT
    # SH1(강동고 #12 박스): 명령 직전 좌측첨자 prefix ``{}_{13}\mathrm{C}`` 가 수식에 흡수돼야.
    # 안 하면 ``{}_{`` 가 평문 leak + ``13`` 만 EQ 로 떨어져 ``{}_{13}`` literal 렌더.
    b1 = _split_latex_commands(r"(가) {}_{13}\mathrm{C}_{r+2}={}_{13}\mathrm{C}_{2r-1}")
    eq1 = "".join(b.value or "" for b in b1 if b.type == CT.EQUATION)
    tx1 = "".join(b.value or "" for b in b1 if b.type == CT.TEXT)
    if r"{}_{13}\mathrm{C}_{r+2}" not in eq1:
        fails.append(f"  SH1 좌측첨자 흡수 실패: {[(b.type.name, b.value) for b in b1]!r}")
    if "{}_{" in tx1 or "{}" in tx1:
        fails.append(f"  SH1 좌측첨자 평문 leak: {tx1!r}")
    # SH2(강북고 #14): 집합 기호 ``\{ \}`` 가 수식에 유지돼야(평문 ₩{ 누수 방지). set 식이
    # ``Y`` ``=\{`` ``y`` 로 쪼개지면 안 됨.
    b2 = _split_latex_commands(r"공역이 Y=\{y|1 \leq y \leq 8\}일 때")
    eq2 = "".join(b.value or "" for b in b2 if b.type == CT.EQUATION)
    tx2 = "".join(b.value or "" for b in b2 if b.type == CT.TEXT)
    if r"\{" not in eq2 or r"\}" not in eq2:
        fails.append(f"  SH2 집합 괄호 수식 미포함: {[(b.type.name, b.value) for b in b2]!r}")
    if "\\{" in tx2 or "\\}" in tx2:
        fails.append(f"  SH2 집합 괄호 평문 leak: {tx2!r}")
    # SH3(시지고·대구외고): ASCII 중괄호 첨자 ``a^{2}bc``·``a_{1}b_{1}`` 가 한 수식으로 — 끝
    # ``(?![a-zA-Z])`` 가 첨자 뒤 영숫자에서 실패해 bare ``a`` 로 후퇴 + ``^{``/``_{`` 평문 leak.
    from core.content_parser import _split_mixed_text_equation as _smte
    for src, want_eq in ((r"상수 a, b에 대하여 a^{2}bc의 값은?", "a^{2}bc"),
                         (r"일 때, a_{1}b_{1}+a_{2}b_{2}의 값은?", "a_{1}b_{1}+a_{2}b_{2}")):
        bl = _smte(src)
        eqs = [b.value for b in bl if b.type == CT.EQUATION]
        txs = "".join(b.value or "" for b in bl if b.type == CT.TEXT)
        if want_eq not in eqs:
            fails.append(f"  SH3 중괄호 첨자 미흡수: {src!r} → {[(b.type.name, b.value) for b in bl]!r}")
        if "^{" in txs or "_{" in txs:
            fails.append(f"  SH3 첨자 평문 leak: {txs!r}")
    # SH4(매천고 #4 선택지): 순수 ASCII 수식 ``(f^{-1})^{-1}=f`` 가 평문 강등되지 않고 EQ 유지.
    from core.content_parser import _parse_content_block
    r4 = _parse_content_block({"type": "text", "value": "(f^{-1})^{-1}=f"})
    if not (r4 and getattr(r4, "type", None) == CT.EQUATION):
        fails.append(f"  SH4 순수 수식 선택지 평문 강등: {r4!r}")
    # SH5(경상고 #12): 함수 선언 나열 ``f:X \to Y, g:Y \to Z`` 의 쉼표가 스푸리어스로 오판돼
    # 공백 병합(→ ``X \to Y g`` → HWP 가 ``Yg`` 로 붙임)되지 않고 텍스트 쉼표로 보존돼야.
    from core.content_parser import _split_one_eq_commas as _soec
    from models.exam_document import ContentBlock as _CB
    _res5: list = []
    _soec(_CB(type=CT.EQUATION, value=r"\to Y, g : Y \to Z"), _res5)
    _joined5 = "".join(b.value or "" for b in _res5)
    if "," not in _joined5:  # 쉼표가 텍스트로 남아야(공백 병합 = "Y g" 누락)
        fails.append(f"  SH5 함수선언 쉼표 소실: {[(b.type.name, b.value) for b in _res5]!r}")
    # 학남고 #12 스푸리어스 쉼표(곱셈)는 여전히 공백 병합(무회귀): P(…)=16/9, P(…)
    _res5b: list = []
    _soec(_CB(type=CT.EQUATION, value=r"P(A)=16/9, P(B)"), _res5b)
    if any("," in (b.value or "") for b in _res5b):
        fails.append(f"  SH5 스푸리어스 쉼표 무회귀 실패: {[(b.type.name, b.value) for b in _res5b]!r}")
    # SH6(매천고 #4 ③): 화살표 명령 ``\Leftrightarrow`` 가 _LATEX_CMD_RE 에 있어 수식으로 흡수
    # (TEXT ``\``(₩ 누수) + bare EQ ``Leftrightarrow`` literal 로 쪼개지지 않음).
    b6 = _split_latex_commands(r"y=f(x) \Leftrightarrow x=f^{-1}(y)")
    eq6 = "".join(b.value or "" for b in b6 if b.type == CT.EQUATION)
    tx6 = "".join(b.value or "" for b in b6 if b.type == CT.TEXT)
    if r"\Leftrightarrow" not in eq6:
        fails.append(f"  SH6 화살표 미흡수: {[(b.type.name, b.value) for b in b6]!r}")
    if "\\" in tx6:
        fails.append(f"  SH6 백슬래시 평문 leak: {tx6!r}")


def _check_adversarial_high(fails, _l2h):
    """적대적 리뷰(2026-06-13) HIGH 수정 회귀.

    A-1 대형연산자 하한이 빈그룹 첨자로 깨지던 회귀 / A-2 그리스·함수 명령 공백 미보장 /
    \\not 의미 반전 / A-5 박스 뒤 post 배점 캡처 / A-6 기하 문맥 부분문자열 오판.
    """
    from core.content_parser import _has_geometry_context, parse_ocr_response
    from models.exam_document import ContentBlock as _CB

    # A-1: SUM/INT 하한은 빈그룹 삽입 금지(``SUM _{`` ≠ ``SUM {}_{``), 진짜 선행첨자는 유지.
    _sum = _l2h(r"\sum_{k=1}^{n}")
    _int = _l2h(r"\int_{0}^{1}")
    if "SUM {}_" in _sum or "SUM _{k=1}" not in _sum:
        fails.append(f"  A1 Σ 하한 빈그룹 회귀: {_sum!r}")
    if "INT {}_" in _int:
        fails.append(f"  A1 ∫ 하한 빈그룹 회귀: {_int!r}")

    # A-2: 그리스·함수 명령은 앞뒤 공백 보장(붙어서 식별자 오인 금지 — raw 출력에 글자 직결 X).
    _sint = _l2h(r"\sin\theta")
    _absin = _l2h(r"ab\sin C")
    if "sintheta" in _sint:
        fails.append(f"  A2 sin theta 공백 미보장: {_sint!r}")
    if "absin" in _absin:
        fails.append(f"  A2 ab sin C 식별자 붙음: {_absin!r}")

    # \not: ∉·≠ 보존(의미 반전 금지).
    _notin = _l2h(r"x \not\in A")
    _note = _l2h(r"x \not= y")
    if "notin" not in _notin:
        fails.append(f"  not-in 반전(∉→∈): {_notin!r}")
    if "neq" not in _note:
        fails.append(f"  not-eq 반전(≠→=): {_note!r}")

    # A-6: 비기하 디코이는 False, 진짜 기하 키워드는 True.
    def _g(t):
        return _has_geometry_context([_CB(type=ContentType.TEXT, value=t)])
    for t in ("주사위를 던져 얻은 점수를 X라 할 때", "집합을 기호로 나타낼 때",
              "전화번호를 정하는 경우의 수"):
        if _g(t):
            fails.append(f"  A6 비기하 오판: {t!r}")
    for t in ("점 P 를 지나는 직선", "삼각형 ABC", "호 AB 의 길이"):
        if not _g(t):
            fails.append(f"  A6 기하 미감지: {t!r}")

    # A-5: 박스 뒤 발문연속(post) 끝 배점을 score 필드 없이도 캡처 + 본문서 제거.
    data = {"questions": [{"number": 1, "contents": [
        {"type": "text", "value": "<상자> (가) 조건1 (나) 조건2"},
        {"type": "text", "value": "이때 알맞은 것은? [4점]"}],
        "choices": [{"marker": "①", "contents": [{"type": "text", "value": "1"}]}]}]}
    q = parse_ocr_response(data, 1).questions[0]
    if q.score != 4:
        fails.append(f"  A5 post 배점 미캡처: score={q.score!r} (기대 4)")
    if "4점" in "".join((b.value or "") for b in q.contents):
        fails.append("  A5 post 배점 본문 잔존")


def run():
    fails = []
    _check_comma_roots(fails)
    _check_brace_subscript(fails)
    _check_korean_leak(fails)
    _check_box_polish(fails)
    _check_wolam_box_fixes(fails)
    _check_jangsan_fixes(fails)
    _check_ascii_leading_sign(fails)
    _check_saebon_fixes(fails)
    _check_sangwon_fixes(fails)
    _check_seonggwang_fixes(fails)
    _check_sinmyeong_fixes(fails)
    _check_sangwon_go1_fixes(fails)
    _check_daejin_go1_fixes(fails)
    _check_dasa_fixes(fails)
    _check_daegeon_go1_fixes(fails)
    _check_jung2_2sem_fixes(fails)
    _check_suha_fixes(fails)
    # HH1(혜화여고 #19): 베이스 없는 선행 첨자(조합 _{n-1}C)는 HWP 가 빈 렌더 — {} 베이스 삽입.
    from core.latex_to_hwpeq import latex_to_hwpeq as _l2h_hh
    _hh = _l2h_hh(r"_{n-1}C_{r-1}+_{n-1}C_{r}=_{n}C_{r}")
    if not _hh.startswith("{}_{n-1}") or "+{}_{n-1}" not in _hh or "={}_{n}" not in _hh:
        fails.append(f"  HH1 선행 첨자 빈 베이스 삽입 실패: {_hh!r}")
    if "a_{n+1}" not in _l2h_hh(r"a_{n+1}=a_n+4"):   # 정상 첨자(베이스 있음)는 무변경
        fails.append(f"  HH1 정상 첨자 오삽입: {_l2h_hh(chr(97)+'_{n+1}=a_n+4')!r}")
    _check_adversarial_high(fails, _l2h_hh)
    for text, must in _SPACING_CASES:  # noqa: E305
        got = _render(text)
        if must not in got:
            fails.append(f"  띄어쓰기: {text!r} → {got!r} (기대 포함: {must!r})")
    for text, field, want in _SCORE_CASES:
        q = _parse_q(text, score=field)
        if q.score != want:
            fails.append(f"  배점 캡처: {text!r}(score={field}) → {q.score!r} (기대 {want!r})")
        body = "".join((b.value or "") for b in q.contents)
        if "점]" in body:
            fails.append(f"  배점 잔존: {text!r} → 본문에 남음: {body!r}")
    if fails:
        print("FAIL test_content_parser:")
        print("\n".join(fails))
        return 1
    print(f"OK test_content_parser ({len(_SPACING_CASES) + len(_SCORE_CASES) + 16} cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
