# -*- coding: utf-8 -*-
"""정답·해설·메타(소단원/난이도) 자동 생성 — DeepSeek API.

Claude Code 세션에서 **사람 대신 문항을 풀어** OCR JSON 의
``answer``/``solution``/``topic``/``difficulty`` 를 채우던 구조(CLAUDE.md 2026-07-24 규약)를
배포 exe 에 그대로 옮긴 것. **스키마·규약·소비 경로는 전부 동일**하고 푸는 주체만
세션 AI → 외부 API(DeepSeek V4 Pro)로 바뀐다(사용자 2026-08-07 지시).

소비 경로(기존, 무변경)::

    OCR JSON {answer, solution, topic, difficulty}
      → content_parser._parse_markdown_lines  → Question.answer/solution
      → hwp_form_writer._inject_answer_runs / _inject_solutions / _inject_question_meta

즉 이 모듈은 **OCR JSON dict 를 제자리에서 채우기만** 하면 된다.

의존성: ``requests`` 만 사용한다(OpenAI 호환 REST 직접 호출). ``openai`` 패키지를 새로
번들하지 않아 PyInstaller 빌드 크기·호환 위험이 없다.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from core.topic_vocab import prompt_block as topic_prompt_block
from utils.config import (
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MAX_WORKERS,
    DEEPSEEK_MODEL,
    DEEPSEEK_TIMEOUT,
    get_deepseek_key,
)

logger = logging.getLogger(__name__)

# 난이도 허용값 — 완료본 표기(상/중/하). 그 외 값이 오면 빈 문자열로 떨군다(오염 방지).
_DIFFICULTY_OK = {"상", "중", "하"}

# 정답 오류 표기(CLAUDE.md 규약) — 검산이 선택지와 안 맞을 때 비우지 말고 종류+정답을 적는다.
_ERROR_TAGS = ("[보기 오류]", "[문제 오류]")

_SYSTEM_PROMPT = """\
당신은 한국 중·고등학교 수학 시험지의 정답과 해설을 만드는 전문 출제·검토자입니다.
문항을 실제로 풀어서(암산·추측 금지, 단계적으로 계산) 정답과 해설을 작성합니다.

반드시 아래 **구분자 형식 그대로** 출력합니다(JSON 금지, 코드펜스 금지, 다른 말 금지).
LaTeX 백슬래시를 있는 그대로 쓸 수 있도록 일부러 JSON 을 쓰지 않습니다.

###ANSWER###
(정답)
###SOLUTION###
(해설 여러 줄)
###TOPIC###
(단원명)
###DIFFICULTY###
(상 또는 중 또는 하)
###END###

- `\\frac`, `\\theta`, `\\times`, `\\neq` 처럼 LaTeX 명령은 **백슬래시 하나로 그대로** 씁니다
  (이스케이프하거나 두 개로 늘리지 마세요).

[answer 규약]
- 객관식(선택지가 주어진 문항): **원문자 하나만**. 예: "④"
- 서술형/단답형: **최종 답만** 간결히. 예: "2", "$x=-5\\pm\\sqrt{34}$", "$a=\\frac{5}{3}$"
  · 문항 번호나 "[서술형 N]" 같은 라벨은 절대 넣지 마세요(양식이 자동으로 붙입니다).
- 수식은 반드시 `$...$` 안에 LaTeX 로 씁니다. 순수 정수 하나면 `$` 없이 써도 됩니다.
- **검산 결과가 선택지와 맞지 않으면 비워 두지 말고** 다음처럼 오류 종류와 맞는 답을 함께 적습니다.
  · 발문·조건은 정상인데 선택지에 정답이 없음 → "[보기 오류] $9$"
  · 발문 조건 자체가 모순·불완전해 답이 정해지지 않음 → "[문제 오류] 조건 (나)가 (가)와 모순"

[solution 규약]
- 실제 줄바꿈으로 구분된 여러 줄. 각 줄은 `step1)` `step2)` … 로 시작합니다.
- 실제 풀이 과정을 순서대로. 수식은 **반드시 `$...$`(인라인) 한 가지만** 씁니다.
  · `$$...$$`(디스플레이)와 `\(...\)` 는 **쓰지 마세요** — 양식에서 깨집니다.
- **한 줄을 너무 길게 쓰지 마세요**(한글 기준 60자 내외). 길어지면 줄을 나눕니다
  (좁은 2단 지면이라 긴 줄은 다른 글자와 겹칩니다).
- 도형 이름은 대문자로(점 A, 선분 $\\overline{AB}$, 삼각형 $\\triangle ABC$, 각 $\\angle ABC$).
- 각도는 `$90^\\circ$` 처럼 씁니다.
- 객관식도 해설을 씁니다(왜 그 선택지인지). 3~6줄이 적당하고, 복잡한 문항은 더 써도 됩니다.
- 표가 필요하면 마크다운 표 대신 문장으로 풀어 씁니다.

[topic 규약]
- 그 문항이 속한 단원 이름 하나. **아래에 표준 어휘 목록이 주어지면 반드시 그 안에서
  그대로 고르세요**(임의로 줄이거나 늘이지 말 것).
- 목록이 없을 때만 교과서 목차의 짧은 표준 단원명을 직접 씁니다.

[difficulty 규약]
- "상" / "중" / "하" 중 하나. 배점과 풀이 단계 수를 함께 고려합니다.
"""

_USER_TEMPLATE = """\
다음은 {grade}{subject} 시험지의 {kind} {number}번 문항입니다.{score_note}

--- 문항 시작 ---
{body}
--- 문항 끝 ---

이 문항을 풀어 정답·해설·단원·난이도를 JSON 으로 출력하세요."""


# ── OCR JSON 문항 → 프롬프트용 텍스트 ────────────────────────────────
def _blocks_to_text(blocks, depth: int = 0) -> str:
    """OCR JSON contents 블록 리스트를 사람이 읽는 LaTeX 텍스트로 직렬화."""
    out: list[str] = []
    for b in blocks or []:
        if not isinstance(b, dict):
            if isinstance(b, str):
                out.append(b)
            continue
        t = (b.get("type") or "").lower()
        v = b.get("value")
        if t in ("equation", "equation_block"):
            if v:
                out.append(f"${v}$" if t == "equation" else f"\n$${v}$$\n")
        elif t == "table":
            out.append("\n" + _table_to_text(b) + "\n")
        elif t == "figure":
            desc = (b.get("description") or b.get("value") or "").strip()
            out.append(f"\n[그림{': ' + desc if desc else ''}]\n")
        elif t == "image":
            out.append("\n[그림]\n")
        elif isinstance(v, str):
            out.append(v)
        elif isinstance(v, list):
            out.append(_blocks_to_text(v, depth + 1))
    return "".join(out)


def _table_to_text(block: dict) -> str:
    """표 블록 → 마크다운 표(모델이 읽기 쉬운 형태)."""
    rows = block.get("rows") or block.get("value") or []
    lines = []
    for r in rows:
        if isinstance(r, list):
            cells = []
            for c in r:
                if isinstance(c, dict):
                    cells.append(str(c.get("value", "")))
                else:
                    cells.append(str(c))
            lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


# OCR 텍스트가 우리 구분자를 흉내내면 파싱이 깨진다(원본에 ``###`` 가 있거나, 스캔 잡음으로
# 그런 문자열이 생길 수 있다). 문항 본문에서는 ``###`` 를 무력화한다(프롬프트 인젝션 방어).
_FENCE_RE = re.compile(r"#{3,}")


def question_to_text(q: dict) -> str:
    """문항 dict → 발문+박스+표+선택지+소문항을 담은 텍스트."""
    parts = [_blocks_to_text(q.get("contents"))]
    for sub in q.get("sub_questions") or []:
        if not isinstance(sub, dict):
            continue
        num = sub.get("number") or ""
        body = _blocks_to_text(sub.get("contents"))
        sc = sub.get("score")
        parts.append(f"\n({num}) {body}" + (f" [{sc}점]" if sc else ""))
    choices = q.get("choices") or []
    if choices:
        parts.append("\n")
        for ch in choices:
            if not isinstance(ch, dict):
                continue
            n = ch.get("number")
            mark = "①②③④⑤⑥⑦⑧⑨⑩"[n - 1] if isinstance(n, int) and 1 <= n <= 10 else str(n)
            parts.append(f"\n{mark} {_blocks_to_text(ch.get('contents'))}")
    text = re.sub(r"\n{3,}", "\n\n", "".join(parts)).strip()
    return _FENCE_RE.sub("#", text)      # 구분자 흉내 차단(파싱 보호)


# ── DeepSeek 호출 ────────────────────────────────────────────────────
class _Usage:
    """토큰 사용량 누적(스레드 안전) — GUI 비용 로깅용."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.input_tokens = 0
        self.output_tokens = 0
        self.cached_tokens = 0
        self.calls = 0

    def add(self, u: dict) -> None:
        if not isinstance(u, dict):
            return
        with self.lock:
            self.calls += 1
            self.input_tokens += int(u.get("prompt_tokens") or 0)
            self.output_tokens += int(u.get("completion_tokens") or 0)
            det = u.get("prompt_tokens_details") or {}
            self.cached_tokens += int(det.get("cached_tokens") or 0)


def _post_chat(api_key: str, model: str, messages: list[dict], *,
               timeout: int, max_retries: int = 3) -> dict:
    """OpenAI 호환 chat/completions 호출(+지수 백오프 재시도).

    429/5xx/연결오류는 재시도한다(ocr_engine._stream_message 의 레이트리밋 정책과 동일 취지).
    """
    url = DEEPSEEK_BASE_URL.rstrip("/") + "/chat/completions"
    # ⚠️ ``response_format: json_object`` 를 **쓰지 않는다** — LaTeX 백슬래시가 JSON
    # 이스케이프와 충돌해 ``\frac``→폼피드+rac 처럼 명령이 증발한다(2026-08-07 실측).
    # 대신 ``###ANSWER###`` 구분자 포맷으로 받는다(_parse_sections).
    payload = {"model": model, "messages": messages, "stream": False}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    delay = 2.0
    last: Exception | None = None
    for attempt in range(max_retries):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 500, 502, 503, 504, 529):
                ra = r.headers.get("retry-after")
                wait = float(ra) if (ra or "").replace(".", "", 1).isdigit() else delay
                last = RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
            else:
                # 401/400 등은 재시도해도 같으므로 즉시 실패(키 오류를 빨리 드러냄).
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
        except requests.RequestException as e:  # 연결/타임아웃
            last = e
            wait = delay
        if attempt < max_retries - 1:
            time.sleep(min(wait, 30.0))
            delay *= 2
    raise RuntimeError(f"DeepSeek 호출 실패: {last}")


_SECTION_RE = re.compile(
    r"###\s*(ANSWER|SOLUTION|TOPIC|DIFFICULTY)\s*###\s*\n?(.*?)(?=###\s*(?:ANSWER|SOLUTION|"
    r"TOPIC|DIFFICULTY|END)\s*###|\Z)", re.S | re.I)

# JSON 안의 LaTeX 백슬래시가 파서에 먹히는 것을 되살리는 표(응답이 JSON 으로 왔을 때만 씀).
# ⚠️ ``\n``(개행)은 진짜 줄바꿈과 구분이 불가능해 복구하지 않는다 — 그래서 애초에 JSON 을
# 쓰지 않고 구분자 포맷을 쓴다(``\neq`` 가 개행+eq 로 깨지던 것, 2026-08-07 실측).
_JSON_CTRL_FIX = [("\x0c", "\\f"), ("\x08", "\\b"), ("\r", "\\r"), ("\t", "\\t")]


def _revive_latex_ctrl(s: str) -> str:
    """JSON 파싱이 삼킨 제어문자를 LaTeX 명령으로 되살린다(``\\x0crac`` → ``\\frac``).

    제어문자 **뒤에 알파벳**이 오면 LaTeX 명령이 잘린 것으로 본다(진짜 탭/줄바꿈은 보통
    공백·줄 끝에 온다).
    """
    for ch, cmd in _JSON_CTRL_FIX:
        # ⚠️ replacement 는 **함수**로 준다 — 문자열이면 re 가 ``\f`` 를 다시 이스케이프로
        # 해석해 복구가 무효가 된다(백슬래시 치환의 고전 함정).
        s = re.sub(re.escape(ch) + r"(?=[a-zA-Z])", lambda _m, _c=cmd: _c, s)
    return s


def _parse_sections(text: str) -> dict:
    """응답 본문 파싱 — 구분자 형식 우선, JSON 으로 오면 폴백(제어문자 복구 포함).

    구분자 형식을 쓰는 이유: LaTeX 백슬래시(``\\frac``·``\\theta``·``\\neq``)가 JSON
    이스케이프와 충돌해 **명령이 통째로 사라진다**(``\\f``=폼피드·``\\t``=탭·``\\n``=개행).
    """
    if not text:
        return {}
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s.rstrip())
    out: dict = {}
    for m in _SECTION_RE.finditer(s):
        out[m.group(1).lower()] = m.group(2).strip()
    if out:
        return out
    # 폴백: 모델이 지시를 어기고 JSON 을 준 경우(제어문자 복구 후 사용).
    try:
        v = json.loads(s)
    except Exception:  # noqa: BLE001
        m = re.search(r"\{.*\}", s, re.S)
        try:
            v = json.loads(m.group(0)) if m else None
        except Exception:  # noqa: BLE001
            v = None
    if isinstance(v, dict):
        return {k: (_revive_latex_ctrl(x) if isinstance(x, str) else x)
                for k, x in v.items()}
    return {}


_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"

# 모델이 JSON 습관으로 ``\\sqrt`` 처럼 백슬래시를 **이중**으로 쓰는 일이 잦다(구분자 포맷으로
# 바꾼 뒤에도 관찰됨 — 실측 #20 정답 ``$\\sqrt{37}$``). 그대로 두면 변환기에서 **명령이 통째
# 증발**한다(``\\sqrt{37}`` → ``{37}``, ``\\pm`` → 백틱). **명령 앞(알파벳 앞)에서만** 단일화 —
# ``\begin{cases} a \\ b \end{cases}`` 의 줄바꿈 ``\\``(뒤가 공백)는 보존해야 한다.
_DOUBLE_BS_RE = re.compile(r"\\{2,}(?=[a-zA-Z])")


def _unescape_latex(s: str) -> str:
    """이중(이상) 백슬래시를 LaTeX 명령용 단일 백슬래시로 정규화."""
    return _DOUBLE_BS_RE.sub(lambda _m: "\\", s or "")


def _normalize_answer(raw, is_choice: bool) -> str:
    """정답 문자열 정규화 — 객관식은 원문자 한 글자로, 라벨·번호 접두 제거."""
    s = _normalize_math_delims(_unescape_latex(str(raw or "").strip())).strip()
    if not s:
        return ""
    # 앞에 붙은 문항번호("17. ")·양식 라벨("[서술형 1]")은 폼이 자동으로 넣으므로 제거.
    s = re.sub(r"^\d+\s*[.)]\s*", "", s)
    s = re.sub(r"^\[\s*[가-힣]*형\s*\d*\s*\]\s*", "", s)
    # 오류 표기의 **정답 부분이 순수 수치**면 수식 객체가 되도록 ``$…$`` 로 감싼다
    # (CLAUDE.md 규약 예: ``"[보기 오류] $9$"`` — 합의 #6 숫자도 수식 객체).
    # "조건 모순" 같은 설명 문장은 그대로 둔다.
    m_err = re.match(r"^(\[(?:보기|문제) 오류\])\s*(.+)$", s)
    if m_err and re.fullmatch(r"[-+]?\d+(?:\.\d+)?", m_err.group(2).strip()):
        return f"{m_err.group(1)} ${m_err.group(2).strip()}$"
    if is_choice and not s.startswith(_ERROR_TAGS):
        m = re.search(r"[①-⑩]", s)
        if m:
            return m.group(0)
        m = re.search(r"\b([1-9]|10)\b", s)          # "정답: 4" → ④
        if m:
            i = int(m.group(1))
            if 1 <= i <= len(_CIRCLED):
                return _CIRCLED[i - 1]
    return s


def _normalize_math_delims(s: str) -> str:
    """수식 구분자를 파서가 아는 ``$…$`` 인라인으로 통일.

    모델이 ``\\(…\\)``(LaTeX 인라인)이나 ``$$…$$``(디스플레이)를 쓰면 파서
    (`content_parser._parse_inline_run`)가 못 알아봐 **평문으로 샌다** — 특히 ``$$`` 를
    단독 줄로 쓰면 그 줄이 평문 ``$`` 로 렌더된다(경원고 #5 실측 2026-08-07).
    """
    # ``\(…\)`` → ``$…$``
    s = re.sub(r"\\\((.+?)\\\)", lambda m: "$" + m.group(1).strip() + "$", s, flags=re.S)
    # ``$$ … $$``(줄바꿈 포함 가능) → 한 줄 인라인 ``$…$``
    s = re.sub(r"\$\$\s*(.+?)\s*\$\$",
               lambda m: "$" + re.sub(r"\s*\n\s*", " ", m.group(1).strip()) + "$",
               s, flags=re.S)
    # 짝이 안 맞아 남은 단독 ``$$`` 는 제거(평문 $ 노출 방지)
    s = re.sub(r"^[ \t]*\$\$[ \t]*$", "", s, flags=re.M)
    return s


def _normalize_solution(raw) -> str:
    """해설 정규화 — 줄별 ``stepN)`` 유지, 빈 줄 제거, 코드펜스 제거, 이중 백슬래시 단일화,
    수식 구분자 통일(``\\(…\\)``·``$$…$$`` → ``$…$``)."""
    s = _unescape_latex(str(raw or "").strip())
    if not s:
        return ""
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s.rstrip())
    s = _normalize_math_delims(s)
    lines = [ln.strip() for ln in s.replace("\r\n", "\n").split("\n")]
    return "\n".join(ln for ln in lines if ln)


def _normalize_difficulty(raw) -> str:
    s = str(raw or "").strip()
    return s if s in _DIFFICULTY_OK else ""


def _normalize_topic(raw) -> str:
    s = re.sub(r"\s+", " ", str(raw or "").strip())
    s = s.strip("[]()<> ")
    return s[:40]


def generate_for_question(q: dict, *, api_key: str, model: str, grade: str = "",
                          subject: str = "", timeout: int = 180) -> dict:
    """문항 하나의 정답·해설·단원·난이도를 생성해 **dict 로 반환**(q 는 안 건드림)."""
    is_choice = bool(q.get("choices"))
    kind = "객관식" if is_choice else "서답형"
    score = q.get("score")
    body = question_to_text(q)
    if not body.strip():
        return {}
    user = _USER_TEMPLATE.format(
        grade=(grade + " ") if grade else "",
        subject=subject or "수학",
        kind=kind,
        number=q.get("number") or "?",
        score_note=f" (배점 {score}점)" if score else "",
        body=body,
    )
    # 분류표 표준 어휘를 프롬프트에 실어 준다 — 세션이 분류표 PDF 를 보고 고르던 것과 같은
    # 입력을 모델에 주는 것(사용자 2026-08-07: "완벽하게 똑같은 동작"). 어휘가 없으면 빈 문자열.
    sys_prompt = _SYSTEM_PROMPT + topic_prompt_block(grade, subject)
    msgs = [{"role": "system", "content": sys_prompt},
            {"role": "user", "content": user}]
    # ⚠️ 빈 정답은 **재시도**한다 — 배치 실행에서 문항 하나가 비결정적으로 비는 일이 관찰됐고
    # (경원고 #2, 단독 재호출은 정상), 그때 사용자는 정답만 빈 채 출하받는다(적대리뷰 2026-08-07).
    data: dict = {}
    text = ""
    for attempt in range(2):
        resp = _post_chat(api_key, model, msgs, timeout=timeout)
        try:
            choice = resp["choices"][0]
            text = choice["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise RuntimeError(f"DeepSeek 응답 형식 오류: {str(resp)[:200]}")
        # 출력이 잘리면(max_tokens 도달) 해설 끝이 사라진 채 들어간다 — 경고로 남긴다.
        if choice.get("finish_reason") == "length":
            logger.warning("해설 응답이 잘림(finish_reason=length) — 문항 #%s",
                           q.get("number"))
        data = _parse_sections(text)
        if (data.get("answer") or "").strip():
            break
        if attempt == 0:
            logger.warning("정답 비어 재시도 — 문항 #%s (응답 %d자)",
                           q.get("number"), len(text or ""))
    if not (data.get("answer") or "").strip():
        raise RuntimeError(f"정답을 얻지 못함(응답 {len(text or '')}자)")
    return {
        "answer": _normalize_answer(data.get("answer"), is_choice),
        "solution": _normalize_solution(data.get("solution")),
        "topic": _normalize_topic(data.get("topic")),
        "difficulty": _normalize_difficulty(data.get("difficulty")),
        "_usage": resp.get("usage") or {},
    }


def generate_solutions(questions: list[dict], *, grade: str = "", subject: str = "",
                       api_key: str | None = None, model: str | None = None,
                       progress=None, cancel=None) -> dict:
    """문항 리스트에 정답·해설·메타를 **제자리로 채운다**.

    Args:
        questions: OCR JSON 의 questions(dict) 리스트. 각 dict 에
            ``answer``/``solution``/``topic``/``difficulty`` 를 써 넣는다.
            ⚠️ **이미 값이 있으면 건너뛴다**(세션에서 손으로 넣은 값·재시도 보호).
        grade/subject: 프롬프트 문맥("중2"·"확률과 통계" 등). 없으면 생략.
        progress: ``progress(done, total, number)`` 콜백(GUI 진행률).
        cancel: ``cancel()`` 이 True 면 남은 작업 중단(GUI 취소 버튼).

    Returns:
        {"filled": int, "failed": int, "skipped": int, "usage": {...}}
    """
    key = api_key or get_deepseek_key()
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY 가 설정되지 않았습니다 (config.json).")
    model = model or DEEPSEEK_MODEL
    targets = [q for q in questions
               if isinstance(q, dict) and not (q.get("answer") or "").strip()]
    skipped = len(questions) - len(targets)
    usage = _Usage()
    filled = failed = 0
    done = 0
    total = len(targets)
    if not total:
        return {"filled": 0, "failed": 0, "skipped": skipped, "usage": {}}

    lock = threading.Lock()

    def _work(q: dict):
        if cancel and cancel():
            return None
        return q, generate_for_question(
            q, api_key=key, model=model, grade=grade, subject=subject,
            timeout=DEEPSEEK_TIMEOUT)

    failed_numbers: list = []
    cancelled = False
    # ⚠️ ``with ThreadPoolExecutor`` 는 종료 시 **제출된 모든 future 를 기다린다** — 취소를
    # 눌러도 남은 문항이 다 끝날 때까지(문항당 최대 수 분) GUI 가 멈춘 것처럼 보인다.
    # OCR 병렬(gui/main_window)과 같이 `shutdown(wait=False, cancel_futures=True)` 로 즉시 뺀다.
    ex = ThreadPoolExecutor(max_workers=max(1, DEEPSEEK_MAX_WORKERS))
    try:
        futs = {ex.submit(_work, q): q for q in targets}
        for fut in as_completed(futs):
            q = futs[fut]
            if cancel and cancel():
                cancelled = True
                break
            try:
                res = fut.result()
            except Exception as e:  # noqa: BLE001
                # 집계는 아래 else 분기에서 한 번만 한다(여기서도 append 하면 중복 — 적대리뷰).
                logger.warning("정답·해설 생성 실패(#%s): %s", q.get("number"), e)
                res = None
            with lock:
                done += 1
            if res:
                _q, data = res
                usage.add(data.pop("_usage", {}))
                # 값이 실제로 있을 때만 기록(빈 값으로 덮어써 기존 동작을 바꾸지 않는다).
                for k in ("answer", "solution", "topic", "difficulty"):
                    if data.get(k):
                        _q[k] = data[k]
                if data.get("answer"):
                    filled += 1
                else:
                    failed += 1
                    failed_numbers.append(_q.get("number"))
            elif not (cancel and cancel()):
                # 취소로 인한 None 은 실패가 아니다(사용자에게 "실패 N"으로 보이면 오해).
                failed += 1
                failed_numbers.append(q.get("number"))
            if progress:
                try:
                    progress(done, total, q.get("number"))
                except Exception:  # noqa: BLE001
                    pass
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    return {
        "filled": filled, "failed": failed, "skipped": skipped,
        "cancelled": cancelled,
        # 실패한 문항 번호 — 조용히 비는 것을 막기 위해 호출자(GUI)가 사용자에게 알린다.
        "failed_numbers": sorted(n for n in failed_numbers if n is not None),
        "usage": {"input_tokens": usage.input_tokens,
                  "output_tokens": usage.output_tokens,
                  "cached_tokens": usage.cached_tokens,
                  "calls": usage.calls, "model": model},
    }
