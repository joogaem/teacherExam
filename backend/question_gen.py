"""
RAG 청크 → Claude API → 구조화된 문제 생성 + 서술형 채점
"""

import json
import os

import anthropic
from dotenv import load_dotenv

load_dotenv()

claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-sonnet-4-5"

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

# ── 채점 프롬프트 ─────────────────────────────────────────────

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

[출력 형식 — JSON만]
{{"score": 0.8, "feedback": "피드백 내용"}}
"""


def generate_questions(
    context_chunks: list[dict],
    question_type: str,
    count: int = 3,
) -> list[dict]:
    """RAG 청크 → 문제 생성"""
    context = "\n\n---\n\n".join(c["content"] for c in context_chunks)
    prompt = PROMPTS[question_type].format(context=context, count=count)

    msg = claude.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = msg.content[0].text.strip()

    # JSON 파싱 (마크다운 코드블록 제거)
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    questions = json.loads(raw)
    return questions


def grade_essay(question_data: dict, user_answer: str) -> dict:
    """서술형 답안 채점 → {score, feedback}"""
    prompt = GRADING_PROMPT.format(
        stem=question_data["stem"],
        model_answer=question_data["model_answer"],
        key_concepts=", ".join(question_data.get("key_concepts", [])),
        rubric=question_data.get("rubric", "핵심 개념 포함 여부"),
        user_answer=user_answer,
    )

    msg = claude.messages.create(
        model=MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    return json.loads(raw)
