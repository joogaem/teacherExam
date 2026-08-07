"""
2022 개정 정보과 교육과정(별책10) 카드 적재 — PHASE1_SPEC §3

원자료: 기출분석/교육과정/별책10_정보과.txt (fitz 텍스트 추출, PDF 151~222페이지 = 정보 5과목)
        교육부 고시 제2022-33호 [별책 10] 실과(기술⋅가정)/정보과 교육과정

⚠️ 정보과학(고등 진로선택 심화)은 별책10이 아니라 별책20(과학 계열 선택 과목)에 있어 이번
   적재 범위 밖 — 기출에 등장하지만 원문 미보유. 후속 과제로 남김.

동작 (전부 LLM 판단이 아니라 정규식으로 원문에서 직접 추출 — §3-1 "정답은 고시문 원문 그대로"):
  1. 성취기준(105개, 코드+원문)을 정규식으로 추출 (LLM 없음, 100% 원문)
  2. 카드 4종 생성:
     a. 성취기준 코드→과목·영역 매핑 (완전 결정론적, LLM 없음)
     b. 성취기준 빈칸 완성 (LLM이 원문에서 핵심어만 공백 처리 — 문장 재작성 금지 지시)
     c. 내용 체계(영역별 지식·이해/과정·기능/가치·태도) 회상 카드 (영역당 1장, LLM이 원문 항목을
        그대로 답으로 사용해 구성)
     d. 교수·학습 및 평가 방법 카드 (과목당 2~3장)
  3. questions insert (source='curriculum', subject='교과교육', active=false, answer_verified=false)
     — 검수함 화면이 아직 없어 전부 active=false로 저장, 검수 후 activate 필요(§8-2 수용기준 참고).

실행: python ingest_curriculum.py [--dry-run]
"""
import argparse
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from db import get_client
from question_gen import claude, MODEL, _parse_json

TXT_PATH = Path(r"C:\Users\ssduw\workspace\기출분석\교육과정\별책10_정보과.txt")
TXT_PATH_20 = Path(r"C:\Users\ssduw\workspace\기출분석\교육과정\별책20_정보과학.txt")

# (표시명, 코드 접두어, 시작줄, 끝줄(배타적), {영역번호: 영역명}, [원문 파일경로 — 생략 시 TXT_PATH])
COURSES = [
    ("정보(중학교)", "9정", 0, 533, {
        "01": "컴퓨팅 시스템", "02": "데이터", "03": "알고리즘과 프로그래밍",
        "04": "인공지능", "05": "디지털 문화",
    }),
    ("정보(고등학교, 일반선택)", "12정", 533, 916, {
        "01": "컴퓨팅 시스템", "02": "데이터", "03": "알고리즘과 프로그래밍",
        "04": "인공지능", "05": "디지털 문화",
    }),
    ("인공지능 기초(진로선택)", "12인기", 916, 1246, {
        "01": "인공지능의 이해", "02": "인공지능과 학습",
        "03": "인공지능의 사회적 영향", "04": "인공지능 프로젝트",
    }),
    ("데이터 과학(진로선택)", "12데과", 1246, 1584, {
        "01": "데이터 과학의 이해", "02": "데이터 준비와 분석",
        "03": "데이터 모델링과 평가", "04": "데이터 과학 프로젝트",
    }),
    ("소프트웨어와 생활(융합선택)", "12소생", 1584, 10**9, {
        "01": "세상을 변화시키는 소프트웨어", "02": "창작을 지원하는 소프트웨어",
        "03": "현상을 분석하는 소프트웨어", "04": "모의 실험하는 소프트웨어",
        "05": "가치를 창출하는 소프트웨어",
    }),
    # 별책20(과학 계열 선택 과목) — 정보과학(고등, 진로선택)만 발췌 (2026-08-05, 행정예고본 hwp 추출)
    ("정보과학(고등학교, 진로선택)", "12정과", 0, 10**9, {
        "01": "프로그래밍", "02": "데이터 구조",
        "03": "알고리즘", "04": "정보과학 프로젝트",
    }, TXT_PATH_20),
]

STANDARD_RE = re.compile(
    r"^\[([0-9]+[가-힣]+)(\d{2})-(\d{2})\]\s*(.*?)(?=\n\[[0-9]|\n•|\n\([가-힣]\)|\n\n|\Z)",
    re.MULTILINE | re.DOTALL,
)


def load_lines(path: Path = TXT_PATH) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def course_text(lines: list[str], start: int, end: int) -> str:
    return "\n".join(lines[start:min(end, len(lines))])


def extract_standards(text: str, expected_prefix: str) -> list[tuple[str, str, str]]:
    """반환: [(전체코드, 영역번호, 원문텍스트), ...] — expected_prefix로 이 과목 소속만 필터.
    성취기준 해설 절이 "• [코드]"(별책10, fitz)가 아니라 "[코드]"로 바로 시작하는 원자료도 있어
    (별책20, hwp 추출) 같은 코드가 두 번 매칭될 수 있다 — 첫 등장(=실제 성취기준 목록)만 채택."""
    seen: set[str] = set()
    out = []
    for prefix, area_no, sub_no, body in STANDARD_RE.findall(text):
        if prefix != expected_prefix:
            continue
        code = f"[{prefix}{area_no}-{sub_no}]"
        if code in seen:
            continue
        seen.add(code)
        clean = " ".join(body.split())
        out.append((code, area_no, clean))
    return out


def extract_content_structure_block(text: str, area_no: str, area_name: str) -> str:
    """"(N) 영역명" 헤더부터 다음 "(N+1)" 또는 "2. 내용 체계"/"나. 성취기준" 전까지 원문 슬라이스."""
    pat = re.compile(rf"\({int(area_no)}\)\s*{re.escape(area_name)}\s*\n(.*?)(?=\n\(\d\)\s|\nㆍ|\n나\.\s|\Z)",
                      re.DOTALL)
    m = pat.search(text)
    return m.group(0)[:2500] if m else ""


def extract_teaching_eval_block(text: str) -> str:
    """"(1) 교수⋅학습의 방향" 부터 과목 끝(또는 다음 "1. 성격" 직전)까지.
    가운뎃점 문자가 원자료마다 다르다(fitz 추출=U+22C5 ⋅, hwp 추출=U+00B7 ·) — 둘 다 허용."""
    m = re.search(r"교수[⋅·]학습의 방향(.*?)(?=\Z)", text, re.DOTALL)
    return m.group(0)[:4000] if m else ""


# ── LLM 카드 생성 ──────────────────────────────────────────────

BLANK_PROMPT = """
아래는 2022 개정 정보과 교육과정의 실제 성취기준 원문 목록이다. 각 문장에서 핵심 용어
1개(구, 명사 위주)를 골라 공백( ___ )으로 바꾼 빈칸 카드를 만들어라.

규칙(중요):
- 문장을 절대 바꿔쓰지 마라. 원문 그대로에서 핵심 용어만 ___ 로 치환한다.
- answer는 그 자리에 있던 원문 그대로의 문자열이어야 한다(패러프레이즈 금지).
- 이미 있는 코드(예: 9정01-01)를 key로 그대로 사용해 매칭하라.

[성취기준 목록]
{items}

[출력 형식 — JSON 객체만]
{{"9정01-01": {{"template": "...___...", "answer": "..."}}, ...}}
"""

CONTENT_STRUCTURE_PROMPT = """
아래는 2022 개정 정보과 교육과정 '{course}' 과목의 '{area}' 영역 내용 체계 원문이다.

[원문]
{block}

이 원문을 바탕으로 빈칸 완성 카드 1개를 만들어라.
- template: "{course} '{area}' 영역의 지식·이해 내용 요소는 ___이다." 형태로, 실제 지식·이해
  항목들을 원문 그대로 answer에 넣을 수 있게 구성
- answer: 지식·이해 항목들을 원문 문구 그대로, 쉼표로 나열 (패러프레이즈 금지)
- hint: 핵심 아이디어 문장 중 1개(원문 그대로)

[출력 형식 — JSON 객체만]
{{"template": "...", "answer": "...", "hint": "..."}}
"""

TEACHING_EVAL_PROMPT = """
아래는 2022 개정 정보과 교육과정 '{course}' 과목의 교수·학습 및 평가 원문이다.

[원문]
{block}

이 원문에서 단답형으로 물을 수 있는 카드 2~3개를 만들어라. 답은 반드시 원문 표현 그대로
사용하고, 절대 요약하거나 바꿔쓰지 마라(고시문 용어 그대로 시험에 나오기 때문).

[출력 형식 — JSON 배열만]
[{{"question": "...", "answer": "..."}}, ...]
"""


def call_llm(prompt: str, max_tokens: int = 2048):
    try:
        msg = claude.messages.create(model=MODEL, max_tokens=max_tokens,
                                      messages=[{"role": "user", "content": prompt}])
        return _parse_json(msg.content[0].text)
    except Exception as e:
        print(f"  ! LLM 호출/파싱 실패: {e}", file=sys.stderr)
        return None


def insert_card(db, course: str, concept_name: str, card_type: str, question_data: dict, dry_run: bool):
    print(f"    + [{card_type}] {concept_name}: {question_data}")
    if dry_run:
        return None
    row = db.table("questions").insert({
        "book_id": None,
        "chapter": f"[교육과정] {course}",
        "type": card_type,
        "difficulty": 2,
        "question_data": question_data,
        "source": "curriculum",
        "subject": "교과교육",
        "active": False,
        "answer_verified": False,
    }).execute().data[0]

    existing = db.table("concepts").select("id").eq("name", concept_name).eq("subject", "교과교육").execute().data
    if existing:
        cid = existing[0]["id"]
    else:
        cid = db.table("concepts").insert({"name": concept_name, "subject": "교과교육"}).execute().data[0]["id"]
    db.table("question_concepts").upsert(
        {"question_id": row["id"], "concept_id": cid}, on_conflict="question_id,concept_id"
    ).execute()
    return row["id"]


def main(dry_run: bool, only: list[str] | None = None):
    lines_cache: dict[Path, list[str]] = {}

    def lines_for(path: Path) -> list[str]:
        if path not in lines_cache:
            lines_cache[path] = load_lines(path)
        return lines_cache[path]

    db = get_client()
    total_cards = 0

    courses = COURSES
    if only:
        courses = [c for c in COURSES if any(k in c[0] for k in only)]
        if not courses:
            print(f"--only={only} 와 일치하는 과목 없음. 가능한 값: {[c[0] for c in COURSES]}")
            return
        print(f"대상 과목만 처리: {[c[0] for c in courses]}")

    for entry in courses:
        course, prefix, start, end, area_map = entry[:5]
        path = entry[5] if len(entry) > 5 else TXT_PATH
        text = course_text(lines_for(path), start, end)
        print(f"\n=== {course} ({prefix}) ===")

        # (a)+(b) 성취기준: 코드매핑(결정론) + 빈칸(LLM)
        standards = extract_standards(text, prefix)
        print(f"  성취기준 {len(standards)}개 발견")

        for code, area_no, _ in standards:
            area_name = area_map.get(area_no, f"영역{area_no}")
            q_data = {"question": f"{code}는 어느 과목, 어느 영역의 성취기준인가?",
                       "model_answer": f"{course}, '{area_name}' 영역",
                       "key_concepts": [code]}
            insert_card(db, course, code, "short_answer",
                        {**q_data, "stem": q_data["question"], "rubric": "과목명과 영역명 정확히 포함"},
                        dry_run)
            total_cards += 1

        BATCH = 12
        for i in range(0, len(standards), BATCH):
            batch = standards[i:i + BATCH]
            items = "\n".join(f"{code}: {body}" for code, _, body in batch)
            result = call_llm(BLANK_PROMPT.format(items=items))
            if not isinstance(result, dict):
                continue
            for code, _, _ in batch:
                key = code.strip("[]")
                card = result.get(key) or result.get(code)
                if not card or not card.get("template") or not card.get("answer"):
                    continue
                insert_card(db, course, code, "fill_blank", {
                    "template": card["template"], "answers": [card["answer"]],
                    "hints": [f"{course} 성취기준 {code}"],
                }, dry_run)
                total_cards += 1

        # (c) 내용 체계 회상 카드 — 영역당 1장
        for area_no, area_name in area_map.items():
            block = extract_content_structure_block(text, area_no, area_name)
            if not block:
                print(f"  ! 내용체계 블록 못 찾음: ({area_no}) {area_name}")
                continue
            card = call_llm(CONTENT_STRUCTURE_PROMPT.format(course=course, area=area_name, block=block))
            if not isinstance(card, dict) or not card.get("template"):
                continue
            insert_card(db, course, f"{course}-{area_name}-내용체계", "fill_blank", {
                "template": card["template"], "answers": [card.get("answer", "")],
                "hints": [card.get("hint", "")],
            }, dry_run)
            total_cards += 1

        # (d) 교수·학습 및 평가
        te_block = extract_teaching_eval_block(text)
        if te_block:
            cards = call_llm(TEACHING_EVAL_PROMPT.format(course=course, block=te_block))
            if isinstance(cards, list):
                for c in cards:
                    if not isinstance(c, dict) or not c.get("question"):
                        continue
                    insert_card(db, course, f"{course}-교수학습및평가", "short_answer", {
                        "stem": c["question"], "model_answer": c.get("answer", ""),
                        "key_concepts": [f"{course} 교수·학습 및 평가"],
                        "rubric": "원문 표현 포함 여부",
                    }, dry_run)
                    total_cards += 1

    print(f"\n{'[dry-run] ' if dry_run else ''}총 카드 {total_cards}개 처리")
    if not dry_run:
        print("⚠️ 전부 active=false로 저장됨(검수 전). 확인 후 일괄 activate 스크립트 별도 실행 필요.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--only", nargs="+", metavar="키워드",
        help="특정 과목만 처리 (과목명 부분 일치). 예: --only 고등학교 '데이터 과학'. "
             "이미 승인된 과목을 중복 생성하지 않으려면 반드시 지정할 것.",
    )
    args = parser.parse_args()
    main(args.dry_run, args.only)
