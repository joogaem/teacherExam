"""필기노트 PDF → chunks 테이블 임포트 (검색 소스 확장).

각 필기노트를 Claude로 주제 단위 정리:
  과목·제목·내용·교재 페이지 인용 추출 → 인쇄→PDF 페이지 변환 → Voyage 임베딩 → chunks 저장.
chapter='[필기노트] ...' 로 태깅. 기존 match_chunks_pages 페이지 윈도우 검색에 자동 포함된다.
재실행 시 기존 필기노트 청크 삭제 후 재삽입(멱등).

사용: python import_notes.py [--test]
"""

import sys
from pathlib import Path

import fitz

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from db import get_client
from ingestion import embed_chunks
from question_gen import claude, MODEL, _parse_json
from seed_lectures import printed_to_pdf

PDF_DIR = Path(r"D:\teacherExam\classPdfs")

BOOK1 = "ddae116b-4177-490d-b8a7-231948352efc"
BOOK2 = "52b5908b-5fd1-4a81-87d8-0d40fa898a09"

# 과목 → (book_id, 파일명, 인쇄 페이지 범위) — 페이지 인용 없을 때 폴백 범위로도 사용
SUBJECTS = {
    "교육의 이해": (BOOK1, "book1.pdf", 16, 59),
    "교육과정": (BOOK1, "book1.pdf", 68, 228),
    "교육방법 및 공학": (BOOK1, "book1.pdf", 276, 425),
    "교육평가": (BOOK1, "book1.pdf", 426, 554),
    "교육행정": (BOOK2, "book2.pdf", 16, 259),
    "교육심리": (BOOK2, "book2.pdf", 298, 440),
    "교육사회": (BOOK2, "book2.pdf", 448, 604),
    "생활지도 및 상담": (BOOK2, "book2.pdf", 606, 641),
    "교육사 및 교육철학": (BOOK2, "book2.pdf", 652, 737),
}

PARSE_PROMPT = """아래는 임용 교육학 강사의 필기노트 PDF에서 추출한 텍스트다.
손글씨 앱 추출이라 특수문자 쓰레기와 순서 섞임이 있다. 강사가 강조한 핵심 정리 내용이다.

주제 단위로 나눠 정리해라. 각 청크는:
- subject: 과목명 — 다음 중 하나로 정확히: 교육의 이해, 교육과정, 교육방법 및 공학, 교육평가, 교육행정, 교육심리, 교육사회, 생활지도 및 상담, 교육사 및 교육철학
- title: 주제 (예: "잠재적 교육과정")
- content: 정리된 내용 — 원래 필기의 핵심을 보존하되 읽을 수 있는 문장/개조식으로. 표·화살표 관계는 텍스트로 풀어쓰기. 300~800자.
- printed_pages: 텍스트에 인용된 교재 페이지 숫자들 (예: "p31" → 31). 없으면 빈 배열.

[필기노트 텍스트]
{text}

[출력 — JSON 배열만, 다른 텍스트 없이]
[
  {{"subject": "교육과정", "title": "주요 교육관", "content": "...", "printed_pages": [31]}}
]
"""


def parse_file(path: Path):
    doc = fitz.open(path)
    text = "\n\n".join(f"--- 노트 {i+1}쪽 ---\n{p.get_text()}" for i, p in enumerate(doc))
    doc.close()
    msg = claude.messages.create(
        model=MODEL,
        max_tokens=12000,
        messages=[{"role": "user", "content": PARSE_PROMPT.format(text=text[:30000])}],
    )
    items = _parse_json(msg.content[0].text)
    return items if isinstance(items, list) else []


def main():
    test = "--test" in sys.argv
    db = get_client()

    files = sorted(PDF_DIR.glob("*필기노트*.pdf"))
    if test:
        files = files[:1]
    print(f"대상 파일: {len(files)}개")

    db.table("chunks").delete().like("chapter", "[필기노트]%").execute()
    print("기존 필기노트 청크 삭제")

    total = 0
    for f in files:
        try:
            items = parse_file(f)
        except Exception as e:
            print(f"⚠ 파싱 실패 {f.name}: {e}")
            continue

        rows = []
        for it in items:
            subject = (it.get("subject") or "").strip()
            content = (it.get("content") or "").strip()
            if subject not in SUBJECTS or len(content) < 50:
                continue
            book_id, book_file, p_lo, p_hi = SUBJECTS[subject]
            pages = [p for p in (it.get("printed_pages") or [])
                     if isinstance(p, int) and p_lo - 10 <= p <= p_hi + 10]
            if pages:
                pdf_start = printed_to_pdf(book_file, min(pages))
                pdf_end = printed_to_pdf(book_file, max(pages))
            else:
                # 인용 없으면 과목 전체 범위 — 유사도 정렬이 걸러줌
                pdf_start = printed_to_pdf(book_file, p_lo)
                pdf_end = printed_to_pdf(book_file, p_hi)
            rows.append({
                "book_id": book_id,
                "chapter": f"[필기노트] {subject}"[:120],
                "section": (it.get("title") or "")[:120],
                "content": f"[강사 필기노트] {it.get('title', '')}\n{content}",
                "page_start": pdf_start,
                "page_end": pdf_end,
            })

        if rows:
            embeddings = embed_chunks([r["content"] for r in rows])
            for r, emb in zip(rows, embeddings):
                r["embedding"] = emb
            db.table("chunks").insert(rows).execute()
        total += len(rows)
        print(f"✔ {f.name[:50]:50s} → {len(rows)}청크")

    print(f"\n완료: 총 {total}청크 임포트")


if __name__ == "__main__":
    main()
