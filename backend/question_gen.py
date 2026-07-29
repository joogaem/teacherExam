"""
RAG 청크 → Claude API → 구조화된 문제 생성 + 서술형 채점
"""

import json
import os

import anthropic
from dotenv import load_dotenv

load_dotenv()

claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
# 기본 Haiku(저비용). 품질 우선으로 바꾸려면 .env에 QUIZ_MODEL=claude-sonnet-4-5
MODEL = os.environ.get("QUIZ_MODEL", "claude-haiku-4-5-20251001")

# ── 유형별 프롬프트 ────────────────────────────────────────────

PROMPTS = {
    "mcq": """
다음 교육학 교재 내용을 바탕으로 객관식 문제 {count}개를 만들어라.

[교재 내용]
{context}

[요구사항]
- 임용고시 수준의 문제
- 4지선다
- 정답은 반드시 교재 내용에 근거
- 오답지는 그럴듯하게 (단순 엉터리 X)

[출력 형식 — JSON 배열만 출력, 다른 텍스트 없이]
[
  {{
    "stem": "문제 내용",
    "options": ["①선택지", "②선택지", "③선택지", "④선택지"],
    "answer": 0,
    "explanation": "해설"
  }}
]
""",

    "fill_blank": """
다음 교육학 교재 내용을 바탕으로 빈칸 완성 문제 {count}개를 만들어라.

[교재 내용]
{context}

[요구사항]
- 핵심 개념어 또는 이론명이 빈칸
- 빈칸은 ___로 표시
- 힌트 제공 가능

[출력 형식 — JSON 배열만 출력]
[
  {{
    "template": "___는 비고츠키가 제안한 개념으로...",
    "answers": ["ZPD", "근접발달영역"],
    "hints": ["비고츠키의 핵심 개념"]
  }}
]
""",

    "matching": """
다음 교육학 교재 내용을 바탕으로 짝맞추기 문제 {count}개를 만들어라.

[교재 내용]
{context}

[요구사항]
- 이론가-개념, 모형-특징, 용어-설명 등의 짝
- 왼쪽 4~6개, 오른쪽 4~6개
- 1:1 대응

[출력 형식 — JSON 배열만 출력]
[
  {{
    "instruction": "다음 학자와 이론을 올바르게 연결하시오.",
    "left": ["타일러", "타바", "워커"],
    "right": ["목표중심 모형", "귀납적 개발 모형", "자연주의적 숙의 모형"],
    "pairs": [[0,0],[1,1],[2,2]]
  }}
]
""",

    "essay": """
다음 교육학 교재 내용을 바탕으로 서술형 문제 {count}개를 만들어라.

[교재 내용]
{context}

[요구사항]
- 임용고시 서술형 수준 (400자 내외 예상 답안)
- 핵심 개념 포함 여부로 채점 가능

[출력 형식 — JSON 배열만 출력]
[
  {{
    "stem": "문제 내용",
    "model_answer": "예시 답안",
    "key_concepts": ["개념1", "개념2", "개념3"],
    "rubric": "채점 기준"
  }}
]
""",
}

# ── 채점 프롬프트 (개념별 구조화 판정 — PHASE1_SPEC §6-2) ─────────

GRADING_PROMPT = """
[문제]
{stem}

[모범 답안]
{model_answer}

[핵심 개념]
{key_concepts}

[채점 기준]
{rubric}

[학생 답안]
{user_answer}

위 학생 답안을 채점하라.
- score: 0.0 ~ 1.0 (핵심 개념 포함 비율 기준)
- feedback: 구체적인 피드백 (100자 내외)
- concepts: [핵심 개념] 각각에 대해 학생 답안에서의 반영 여부를 판정
  - "hit": 개념을 정확히 포함/서술함
  - "missing": 개념이 답안에 없음
  - "misconception": 개념을 언급했으나 잘못 이해함
  각 항목은 {{"name": 개념명(핵심 개념 목록의 표기 그대로), "verdict": "hit"|"missing"|"misconception", "evidence": 판단 근거 한 줄}}

[출력 형식 — JSON만, 다른 텍스트 없이]
{{"score": 0.8, "feedback": "...", "concepts": [{{"name": "...", "verdict": "hit", "evidence": "..."}}]}}
"""


def _parse_json(raw: str):
    """Claude 응답에서 JSON 추출 — 코드펜스/설명문이 섞여도 견고하게."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw[:4].lower() == "json":
            raw = raw[4:]
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # 첫 [ ~ 마지막 ] (배열) 또는 { ~ } (객체) 만 잘라서 재시도
        for open_c, close_c in (("[", "]"), ("{", "}")):
            i, j = raw.find(open_c), raw.rfind(close_c)
            if i != -1 and j > i:
                return json.loads(raw[i:j + 1])
        raise


def generate_questions(
    context_chunks: list[dict],
    question_type: str,
    count: int = 3,
) -> list[dict]:
    """RAG 청크 → 단일 유형 문제 생성 (하위호환용)."""
    return generate_questions_multi(context_chunks, [question_type], count).get(question_type, [])


# ── 유형 통합 생성 ────────────────────────────────────────────────
# 유형별 요구사항 + 출력 아이템 형식 (단일 호출에서 전 유형을 한 번에 생성)
# 모든 유형에 key_concepts 포함 — 문항→개념 연결(question_concepts)이 있어야
# 오답이 약점 분석·SR 복습 큐에 반영된다 (없으면 풀이 기록만 남고 재출제 안 됨).
TYPE_SPECS = {
    "mcq": (
        "객관식(4지선다). 정답은 교재 근거, 오답지는 그럴듯하게. key_concepts: 테스트하는 핵심 개념명 1~2개.",
        '{"stem":"문제","options":["①..","②..","③..","④.."],"answer":0,"explanation":"해설","key_concepts":["개념1"]}',
    ),
    "fill_blank": (
        "빈칸 완성. 핵심 개념어/이론명이 빈칸(___). 힌트 제공 가능. key_concepts: 테스트하는 핵심 개념명 1~2개.",
        '{"template":"___는 비고츠키가 제안한...","answers":["ZPD","근접발달영역"],"hints":["비고츠키 핵심 개념"],"key_concepts":["근접발달영역"]}',
    ),
    "matching": (
        "짝맞추기. 이론가-개념/모형-특징 등 1:1 대응, 왼쪽·오른쪽 각 3~6개. key_concepts: 테스트하는 핵심 개념명 1~2개.",
        '{"instruction":"학자와 이론을 연결하시오.","left":["타일러","타바"],"right":["목표중심 모형","귀납적 개발 모형"],"pairs":[[0,0],[1,1]],"key_concepts":["교육과정 개발 모형"]}',
    ),
    "essay": (
        "서술형(임용 수준, 400자 내외 예상답안). 핵심 개념 포함 여부로 채점 가능.",
        '{"stem":"문제","model_answer":"예시 답안","key_concepts":["개념1","개념2"],"rubric":"채점 기준"}',
    ),
    "short_answer": (
        "단문 인출(1~3문장). 재인(mcq)을 졸업한 학습자용 — 핵심 개념이 정확히 들어가야 득점.",
        '{"stem":"문제","model_answer":"1~3문장 예시 답안","key_concepts":["개념1","개념2"],"rubric":"채점 기준"}',
    ),
}


def generate_questions_multi(
    context_chunks: list[dict],
    types: list[str],
    count: int | dict[str, int] = 3,
    style_examples: list[str] | None = None,
) -> dict[str, list[dict]]:
    """RAG 청크 → 선택한 전 유형을 1회 호출로 생성. {유형: [문제...]} 반환.
    count: 공통 개수(int) 또는 유형별 개수 딕셔너리.
    style_examples: 실제 강사 출제 문항(형성평가) — 스타일·난이도 기준으로 주입."""
    if not types:
        return {}
    context = "\n\n---\n\n".join(c["content"] for c in context_chunks)

    def n_of(t: str) -> int:
        return count.get(t, 1) if isinstance(count, dict) else count

    spec_lines, out_lines = [], []
    for t in types:
        desc, fmt = TYPE_SPECS[t]
        spec_lines.append(f'- "{t}" {n_of(t)}개: {desc}')
        out_lines.append(f'  "{t}": [ {fmt}, ... {n_of(t)}개 ]')

    style_block = ""
    if style_examples:
        style_block = (
            "[실제 강사 출제 문항 예시 — 이 스타일·난이도·묻는 방식을 따라라]\n"
            + "\n".join(f"- {s}" for s in style_examples[:3]) + "\n\n"
        )

    prompt = (
        "다음 교육학 교재 내용을 바탕으로 임용고시 수준 문제를 유형별로 만들어라.\n\n"
        f"[교재 내용]\n{context}\n\n"
        + style_block +
        "[생성할 유형과 개수]\n" + "\n".join(spec_lines) + "\n\n"
        "[출력 형식 — 아래 키를 가진 JSON 객체 하나만 출력, 다른 텍스트 없이]\n"
        "{\n" + ",\n".join(out_lines) + "\n}\n"
    )

    # 유형·개수에 따라 출력 토큰 여유 확보
    total_count = sum(n_of(t) for t in types)
    max_tokens = min(8192, 1200 + 700 * total_count)
    msg = claude.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    obj = _parse_json(msg.content[0].text)
    if not isinstance(obj, dict):
        return {}
    return {t: (obj.get(t) or []) for t in types}


_VALID_VERDICTS = {"hit", "missing", "misconception"}


def grade_essay(question_data: dict, user_answer: str) -> dict:
    """서술형/단문서술 답안 채점 → {score, feedback, concepts:[{name,verdict,evidence}]}.
    Claude 응답의 키 부재·형식 이탈에 방어적으로 대응(PHASE1_SPEC §6-2,
    구 버전에서 result["score"] 직접 접근 시 KeyError로 500 나던 문제 수정).

    LLM을 쓸 수 없을 때(크레딧 소진·네트워크 장애 등)는 예외를 던지지 않고
    {"unavailable": True}를 반환한다 — 호출부가 자가 채점으로 전환할 수 있게.
    (2026-07-18 크레딧 소진으로 서술형 제출이 전부 500 나던 것을 계기로 추가.
    강의 문제은행 668개 중 475개가 서술형이라 이 경로가 죽으면 앱이 사실상 멈춤.)"""
    key_concepts = question_data.get("key_concepts", [])
    prompt = GRADING_PROMPT.format(
        stem=question_data["stem"],
        model_answer=question_data["model_answer"],
        key_concepts=", ".join(key_concepts),
        rubric=question_data.get("rubric", "핵심 개념 포함 여부"),
        user_answer=user_answer,
    )

    try:
        msg = claude.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        return {
            "unavailable": True,
            "score": None,
            "feedback": f"AI 채점을 지금 쓸 수 없어요({type(e).__name__}). 모범답안과 비교해 직접 판정해주세요.",
            "concepts": [],
        }

    try:
        result = _parse_json(msg.content[0].text)
    except (json.JSONDecodeError, ValueError):
        result = {}
    if not isinstance(result, dict):
        result = {}

    try:
        score = max(0.0, min(1.0, float(result.get("score", 0.0))))
    except (TypeError, ValueError):
        score = 0.0
    feedback = result.get("feedback") or ""

    concepts: list[dict] = []
    for c in (result.get("concepts") or []):
        if not isinstance(c, dict):
            continue
        name, verdict = c.get("name"), c.get("verdict")
        if name and verdict in _VALID_VERDICTS:
            concepts.append({"name": name, "verdict": verdict, "evidence": c.get("evidence", "")})

    # 채점 응답이 일부 핵심 개념을 누락하면 보수적으로 missing 처리
    # (누락된 개념이 "판정 안 됨"으로 조용히 사라져 SR에서 빠지는 것을 방지)
    covered = {c["name"] for c in concepts}
    for kc in key_concepts:
        if kc not in covered:
            concepts.append({"name": kc, "verdict": "missing", "evidence": "채점 응답에 미포함"})

    return {"score": score, "feedback": feedback, "concepts": concepts}
