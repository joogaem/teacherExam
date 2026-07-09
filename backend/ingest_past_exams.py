"""
기출 문제은행 적재 (1회성 스크립트, 파일 1개당 1회 실행) — PHASE1_SPEC §2

전제: supabase/phase1.sql 이 먼저 적용되어 있어야 함(questions 신규 컬럼, concepts 등).

원자료: fitz로 텍스트 추출한 기출 파일 (예: C:\\Users\\ssduw\\workspace\\기출분석\\exam2026A.txt)
       "========== PAGE N ==========" 로 페이지 구분, 각 문항은 "\n숫자. " 로 시작.

동작:
  1. 원자료를 문항 단위로 분리 (페이지 헤더/각주 잡음 제거)
  2. 배점([2점]/[4점])은 정규식으로 직접 추출(신뢰도 높음, LLM에 맡기지 않음)
  3. 문항별로 Claude 호출 — stem/materials/conditions/instructions/model_answer/
     key_concepts/subject/desk_only 를 구조화 JSON으로 생성
     ⚠️ model_answer는 공식 정답이 아닌 AI 초안이다. answer_verified=False로 저장되며
        반드시 사용자가 고시문·기본서 대조 후 검수해야 한다 (PHASE1_SPEC §2-2).
  4. questions insert + concepts upsert + question_concepts 연결 + concepts.exam_years 갱신

실행: python ingest_past_exams.py <파일경로> <학년도(int)> <A|B|edu> [--dry-run]
      예) python ingest_past_exams.py "../../기출분석/exam2026A.txt" 2026 A
"""
import argparse
import json
import re
import sys
from pathlib import Path

from db import get_client
from question_gen import claude, MODEL, _parse_json

SUBJECTS = [
    "자료구조", "알고리즘", "프로그래밍", "데이터베이스", "운영체제", "네트워크",
    "컴퓨터구조", "논리회로", "인공지능", "소프트웨어공학", "이산수학", "교과교육",
]

# 그림 없이도 desk_only(책상용: 코드 작성·계산 추적)로 분류할 강한 신호 키워드.
# 완벽하지 않은 휴리스틱 — 나중에 검수 화면에서 수동 조정 가능하게 설계됨(현재는 값만 세팅).
DESK_ONLY_HINTS = re.compile(
    r"프로그램|코드|계산|버킷|레지스터|패킷|서브넷|트랜잭션|스케줄|"
    r"진리표|타임아웃|시퀀스|주소지정|페이지 테이블|해시|정렬 알고리즘"
)

PAGE_HEADER = re.compile(r"^정보[․·]컴퓨터.*\(\d+면 중.*면\)$", re.MULTILINE)
FOOTER_JUNK = re.compile(r"^◦문제지 전체 면수.*$|^◦모든 문항에는.*$", re.MULTILINE)
Q_START = re.compile(r"\n(\d{1,2})\.\s")
POINTS = re.compile(r"\[(\d)점\]")


def split_questions(raw: str) -> list[str]:
    """원자료 텍스트를 문항 단위로 분리.
    주의: 문항 안에 "<다>" 같은 절차 설명이 1./2./3.으로 다시 번호 매겨 나오는 경우가 있어
    (예: 직렬화 그래프 작성 절차) 단순히 '\\n숫자. ' 패턴만 보면 그 중첩 목록을 새 문항으로
    잘못 쪼갠다. 최상위 문항 번호는 1부터 끊김 없이 증가한다는 성질을 이용해,
    "다음에 와야 할 번호"와 일치하는 매치만 실제 문항 경계로 인정한다."""
    text = re.sub(r"=+ PAGE \d+ =+", "", raw)
    text = PAGE_HEADER.sub("", text)
    text = FOOTER_JUNK.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n" + text

    all_matches = list(Q_START.finditer(text))
    boundaries = []
    expected = 1
    for m in all_matches:
        if int(m.group(1)) == expected:
            boundaries.append(m.start())
            expected += 1

    chunks = []
    for i, start in enumerate(boundaries):
        end = boundaries[i + 1] if i + 1 < len(boundaries) else len(text)
        chunk = text[start:end].strip()
        if len(chunk) > 30:
            chunks.append(chunk)
    return chunks


STRUCTURE_PROMPT = """
다음은 대한민국 중등교사 임용시험 '정보·컴퓨터' 과목의 실제 기출 문제 1개다.
PDF에서 텍스트로 추출한 것이라 수식·표·그림 일부가 깨져 있을 수 있다.

[원문]
{raw}

이 문제를 분석해 아래 JSON으로 구조화하라.
- stem: 문제의 핵심 발문(자료 설명 제외, 실제 질문 부분)
- materials: 문제 속 (가)/(나)/(다) 등 제시 자료를 배열로(각 항목은 그 자료의 텍스트 요약, 없으면 빈 배열)
- conditions: <조건>에 해당하는 내용 요약(없으면 빈 문자열)
- instructions: <작성 방법>에 제시된 요구사항 목록(배열)
- model_answer: 각 작성 방법 요구사항에 대한 모범답안 초안(항목별로 구분해 서술). 확신이 없는
  부분은 "(확인 필요)"를 붙여라. 추측으로 확정 답을 단정하지 말 것.
- key_concepts: 이 문제가 테스트하는 핵심 개념명 1~3개(간결한 명사구)
- subject: 다음 중 정확히 하나 {subjects}
- desk_only: 이 문제가 코드 작성·계산 추적·표 채우기처럼 책상(데스크톱)에서 푸는 게
  자연스러우면 true, 개념 회상형 단답이면 false

[출력 형식 — JSON 객체만, 다른 텍스트 없이]
{{"stem":"...", "materials":["..."], "conditions":"...", "instructions":["..."],
  "model_answer":"...", "key_concepts":["...","..."], "subject":"...", "desk_only": true}}
"""


def structure_question(raw: str) -> dict | None:
    prompt = STRUCTURE_PROMPT.format(raw=raw[:3000], subjects=", ".join(SUBJECTS))
    try:
        msg = claude.messages.create(
            model=MODEL, max_tokens=1536,
            messages=[{"role": "user", "content": prompt}],
        )
        obj = _parse_json(msg.content[0].text)
    except Exception as e:
        print(f"  ! 구조화 실패: {e}", file=sys.stderr)
        return None
    if not isinstance(obj, dict):
        return None
    if obj.get("subject") not in SUBJECTS:
        obj["subject"] = "교과교육" if any(
            kw in raw for kw in ("교육과정", "성취기준", "교수․학습", "평가")
        ) else "프로그래밍"
    return obj


def main(path: str, year: int, paper: str, dry_run: bool):
    raw = Path(path).read_text(encoding="utf-8")
    chunks = split_questions(raw)
    print(f"{path}: 문항 {len(chunks)}개 분리됨")

    db = get_client()
    concepts_cache: dict[str, str] = {}

    def get_or_create_concept(name: str) -> str | None:
        name = name.strip()
        if not name:
            return None
        key = f"{name}|기출"
        if key in concepts_cache:
            return concepts_cache[key]
        existing = db.table("concepts").select("id, exam_years") \
            .eq("name", name).execute().data
        if existing:
            cid = existing[0]["id"]
            years = set(existing[0].get("exam_years") or [])
            years.add(year)
            if not dry_run:
                db.table("concepts").update({"exam_years": sorted(years)}) \
                    .eq("id", cid).execute()
        elif dry_run:
            cid = f"dry-{name}"
        else:
            row = db.table("concepts").insert(
                {"name": name, "subject": "전공-기출", "exam_years": [year]}
            ).execute().data[0]
            cid = row["id"]
        concepts_cache[key] = cid
        return cid

    saved = 0
    for i, chunk in enumerate(chunks):
        points_m = POINTS.search(chunk)
        points = int(points_m.group(1)) if points_m else None

        structured = structure_question(chunk)
        if not structured:
            print(f"  [{i+1}/{len(chunks)}] 구조화 실패 — 건너뜀")
            continue

        question_data = {
            "stem": structured.get("stem", ""),
            "materials": structured.get("materials", []),
            "conditions": structured.get("conditions", ""),
            "instructions": structured.get("instructions", []),
            "model_answer": structured.get("model_answer", ""),
            "key_concepts": structured.get("key_concepts", []),
        }
        subject = structured.get("subject", "프로그래밍")
        desk_only = bool(structured.get("desk_only")) or bool(DESK_ONLY_HINTS.search(chunk))

        print(f"  [{i+1}/{len(chunks)}] {points}점 · {subject} · desk_only={desk_only} "
              f"· 개념={structured.get('key_concepts')}")

        if dry_run:
            saved += 1
            continue

        row = db.table("questions").insert({
            "book_id": None,
            "chapter": f"{year}학년도 전공{paper} 기출",
            "type": "essay",
            "difficulty": 4 if points == 4 else 2,
            "question_data": question_data,
            "source": "past_exam",
            "exam_year": year,
            "paper": paper,
            "subject": subject,
            "points": points,
            "desk_only": desk_only,
            "active": True,
            "answer_verified": False,
        }).execute().data[0]

        qc_rows = []
        for name in structured.get("key_concepts", []):
            cid = get_or_create_concept(name)
            if cid:
                qc_rows.append({"question_id": row["id"], "concept_id": cid})
        if qc_rows:
            db.table("question_concepts").upsert(
                qc_rows, on_conflict="question_id,concept_id"
            ).execute()
        saved += 1

    print(f"\n{'[dry-run] ' if dry_run else ''}완료: {saved}/{len(chunks)}문항 처리")
    if not dry_run:
        print("⚠️ model_answer는 전부 AI 초안(answer_verified=false). "
              "고시문·기본서 대조 후 검수 필요 — 검수 화면은 아직 미구현, "
              "우선 Supabase Table Editor에서 확인 가능.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("year", type=int)
    parser.add_argument("paper", choices=["A", "B", "edu"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(args.path, args.year, args.paper, args.dry_run)
