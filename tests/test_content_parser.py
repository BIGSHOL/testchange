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
    for text, must in _SPACING_CASES:
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
    print(f"OK test_content_parser ({len(_SPACING_CASES) + len(_SCORE_CASES) + 9} cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
