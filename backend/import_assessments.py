"""형성평가 해설편 PDF → 문제은행(questions) 임포트.

각 해설편을 Claude로 구조화 파싱:
  문항(인출 프롬프트) + 교재 페이지 인용 + 모범답안 → essay형 문제로 저장.
페이지 인용(인쇄 페이지)으로 강의를 자동 매핑한다. 재실행 시 기존 임포트 삭제 후 재삽입(멱등).

사용: python import_assessments.py [--test]   (--test: 02 교육과정 1개 파일만)
"""

import json
import re
import sys
from pathlib import Path

import fitz

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from db import get_client
from question_gen import claude, MODEL, _parse_json

PDF_DIR = Path(r"D:\teacherExam\classPdfs")

BOOK1 = "ddae116b-4177-490d-b8a7-231948352efc"  # 1권: 이해·과정·방법·평가
BOOK2 = "52b5908b-5fd1-4a81-87d8-0d40fa898a09"  # 2권: 행정·심리·사회·생활지도·사철학

# 파일명 과목 키워드 → (book_id, PART 키워드)
SUBJECT_MAP = [
    ("교육의 이해", BOOK1, "PART1"),
    ("교육의이해", BOOK1, "PART1"),
    ("교육과정", BOOK1, "PART2"),
    ("교육방법", BOOK1, "PART3"),
    ("교육평가", BOOK1, "PART4"),
    ("교육행정", BOOK2, "PART6"),
    ("교육심리", BOOK2, "PART7"),
    ("교육사회", BOOK2, "PART8"),
    ("생활지도", BOOK2, "PART9"),  # 18번 파일은 생활지도+교육사철학 혼합 → 페이지로 구분됨
]

PARSE_PROMPT = """아래는 임용 교육학 강의의 형성평가 해설편 PDF에서 추출한 텍스트다.
레이아웃 때문에 순서가 섞여 있고, 머리말/사이드바(과목명 나열, '복습check', 페이지 번호 등) 쓰레기 텍스트가 섞여 있다.

문항들을 복원해라. 각 문항은:
- 인출형 문제 (예: "잠재적 교육과정의 개념과 특징 2가지")
- 교재 페이지 인용 (예: p87-2-(1)) 이 괄호로 붙어 있음
- 해설편이므로 각 문항에 대한 답(해설) 텍스트가 존재함

[추출 텍스트]
{text}

[출력 — JSON 배열만, 다른 텍스트 없이]
[
  {{
    "no": 1,
    "stem": "문항 내용 (페이지 인용 괄호는 제거하고 자연스러운 문제로)",
    "pages": [87],
    "model_answer": "해설(답) 내용 — 원문 유지, 없으면 빈 문자열",
    "key_concepts": ["핵심 개념 2~5개"]
  }}
]

규칙:
- pages: 문항에 인용된 인쇄 페이지 숫자들 (p87-2-(1) → 87)
- 답을 찾을 수 없는 문항도 stem은 포함 (model_answer: "")
- 머리말/사이드바 쓰레기는 무시
"""


def get_lecture_map(db):
    """book_id → [(printed_start, printed_end, lecture_id, part)] 정렬 리스트"""
    rows = db.table("lectures").select("id, book_id, part, printed_page_start, printed_page_end") \
        .execute().data
    by_book = {}
    for r in rows:
        if r["printed_page_start"] is None:
            continue
        by_book.setdefault(r["book_id"], []).append(
            (r["printed_page_start"], r["printed_page_end"] or r["printed_page_start"], r["id"], r["part"] or "")
        )
    for v in by_book.values():
        v.sort()
    return by_book


def find_lecture(lecture_map, book_id, page):
    """인쇄 페이지 → 강의. 범위 포함 우선, 없으면 가장 가까운 강의."""
    cands = lecture_map.get(book_id, [])
    if not cands:
        return None
    for start, end, lid, _ in cands:
        if start <= page <= end:
            return lid
    best = min(cands, key=lambda c: min(abs(c[0] - page), abs(c[1] - page)))
    return best[2]


def subject_of(filename):
    for kw, book, part in SUBJECT_MAP:
        if kw in filename:
            return kw, book, part
    return None, None, None


def parse_file(path: Path):
    doc = fitz.open(path)
    text = "\n".join(p.get_text() for p in doc)
    doc.close()
    # 16k자 단위로 자르기엔 파일이 작음(보통 ~12k자) — 통째로 전달
    msg = claude.messages.create(
        model=MODEL,
        max_tokens=20000,
        messages=[{"role": "user", "content": PARSE_PROMPT.format(text=text[:40000])}],
    )
    items = _parse_json(msg.content[0].text)
    return items if isinstance(items, list) else []


def main():
    test = "--test" in sys.argv
    db = get_client()
    lecture_map = get_lecture_map(db)

    files = sorted(PDF_DIR.glob("*해설편*형성평가*.pdf")) + sorted(PDF_DIR.glob("*형성평가*해설편*.pdf"))
    files = sorted(set(files))
    if test:
        files = [f for f in files if "02" in f.name and "교육과정" in f.name][:1]
    print(f"대상 파일: {len(files)}개")

    force = "--force" in sys.argv

    total = 0
    for f in files:
        subject, book_id, part = subject_of(f.name)
        if not book_id:
            print(f"⚠ 과목 매핑 실패, 건너뜀: {f.name}")
            continue

        m = re.search(r"형성평가\s*_?(\d+)", f.name)
        file_no = m.group(1) if m else "?"
        label = f"[형성평가] {file_no} {subject}"[:120]

        # 이어하기: 이미 임포트된 파일은 건너뜀 (--force 시 재임포트)
        existing = db.table("questions").select("id").eq("chapter", label).limit(1).execute().data
        if existing and not force:
            print(f"↷ 건너뜀(이미 임포트됨): {f.name[:50]}")
            continue
        if existing:
            db.table("questions").delete().eq("chapter", label).execute()

        try:
            items = parse_file(f)
        except Exception as e:
            print(f"⚠ 파싱 실패 {f.name}: {e}")
            continue

        rows = []
        for it in items:
            stem = (it.get("stem") or "").strip()
            if not stem:
                continue
            pages = [p for p in (it.get("pages") or []) if isinstance(p, int)]
            lecture_id = find_lecture(lecture_map, book_id, pages[0]) if pages else None
            rows.append({
                "book_id": book_id,
                "chapter": label,
                "type": "essay",
                "difficulty": 3,
                "lecture_id": lecture_id,
                "question_data": {
                    "stem": stem,
                    "model_answer": (it.get("model_answer") or "").strip(),
                    "key_concepts": it.get("key_concepts") or [],
                    "rubric": "핵심 개념 포함 여부",
                    "source": "형성평가",
                    "origin_pages": pages,
                },
                "source_chunk_ids": [],
            })
        if rows:
            db.table("questions").insert(rows).execute()
        mapped = sum(1 for r in rows if r["lecture_id"])
        total += len(rows)
        print(f"✔ {f.name[:50]:50s} → {len(rows)}문항 (강의 매핑 {mapped})")

    print(f"\n완료: 총 {total}문항 임포트")


if __name__ == "__main__":
    main()
