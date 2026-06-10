"""
강의별 문제풀기 — 강의 조회 + 강의 페이지범위 기반 청크 검색.

검색 전략(하이브리드):
  1) 강의 제목으로 의미검색 + 페이지 윈도우 소프트필터(match_chunks_pages)
  2) 윈도우가 빗나가 결과가 부족하면 전체 책 의미검색(match_chunks)으로 폴백
"""

from ingestion import embed_query
from db import get_client

# 청크 페이지가 "챕터 그룹" 단위라 듬성듬성 → 좁은 윈도우는 비기 쉽다.
# 충분히 나올 때까지 점진적으로 넓힌다(대개 같은 PART 안에 머무름).
PAGE_PADS = [25, 60, 150]
MIN_HITS = 3          # 이보다 적으면 더 넓은 윈도우로


def get_lectures(book_id: str | None = None) -> list[dict]:
    db = get_client()
    q = db.table("lectures").select(
        "id, book_id, source, lecture_no, week, part, title, "
        "printed_page_start, printed_page_end, pdf_page_start, pdf_page_end"
    )
    if book_id:
        q = q.eq("book_id", book_id)
    rows = q.order("source").order("lecture_no").execute().data
    return rows


def get_lecture(lecture_id: str) -> dict | None:
    db = get_client()
    res = db.table("lectures").select("*").eq("id", lecture_id).execute()
    return res.data[0] if res.data else None


def search_chunks_for_lecture(lecture: dict, top_k: int = 6) -> list[dict]:
    """강의 1개에 대한 RAG 청크 검색 (페이지 윈도우 점진 확장 + 폴백)."""
    db = get_client()
    query_text = f"{lecture.get('part','')} {lecture['title']}".strip()
    query_emb = embed_query(query_text)
    p_start = lecture.get("pdf_page_start") or 1
    p_end = lecture.get("pdf_page_end") or 10_000

    # 1) 페이지 윈도우를 넓혀가며 의미검색 — 충분히 나오면 즉시 채택
    for pad in PAGE_PADS:
        res = db.rpc("match_chunks_pages", {
            "query_embedding": query_emb,
            "target_book_id": lecture["book_id"],
            "page_lo": max(1, p_start - pad),
            "page_hi": p_end + pad,
            "match_count": top_k,
        }).execute()
        hits = res.data or []
        if len(hits) >= MIN_HITS:
            return hits[:top_k]

    # 2) 그래도 부족하면 전체 책 의미검색(최후수단)
    res2 = db.rpc("match_chunks", {
        "query_embedding": query_emb,
        "target_book_id": lecture["book_id"],
        "target_chapter": None,
        "match_count": top_k,
    }).execute()
    return (res2.data or [])[:top_k]
