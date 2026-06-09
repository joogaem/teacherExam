"""
PDF → 챕터 파싱 → 청킹 → 임베딩 → Supabase 저장
"""

import os
import re
import uuid
from dataclasses import dataclass

import fitz  # pymupdf
import voyageai
from dotenv import load_dotenv

from db import get_client

load_dotenv()

voyage = voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])

# ── 챕터 헤딩 패턴 (교육학 교재 구조에 맞게 조정) ──────────────
CHAPTER_PATTERNS = [
    re.compile(r"^(PART\s+\d+[가-힣\s\w]*)$", re.MULTILINE),
    re.compile(r"^(Chapter\s+\d+[가-힣\s\w]*)$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^(제\s*\d+\s*장[가-힣\s\w]*)$", re.MULTILINE),
    re.compile(r"^(CHAPTER\s+\d+[가-힣\s\w]*)$", re.MULTILINE),
]

CHUNK_SIZE = 800      # 토큰 근사값 (글자수 기준)
CHUNK_OVERLAP = 150


@dataclass
class Chunk:
    book_id: str
    chapter: str
    section: str
    content: str
    page_start: int
    page_end: int


def extract_pages(pdf_bytes: bytes) -> list[dict]:
    """페이지별 텍스트 추출"""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    for i, page in enumerate(doc):
        text = page.get_text().strip()
        if text:
            pages.append({"page": i + 1, "text": text})
    return pages


def detect_chapter(text: str) -> str | None:
    for pat in CHAPTER_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1).strip()
    return None


def parse_chapters(pages: list[dict]) -> list[dict]:
    """
    각 페이지에 chapter 레이블을 붙임
    TOC가 없는 교재 기준 — 헤딩 패턴으로 추적
    """
    current_chapter = "서론"
    current_section = ""
    result = []

    for page in pages:
        text = page["text"]
        chapter = detect_chapter(text)
        if chapter:
            current_chapter = chapter
            current_section = ""

        result.append({
            "page": page["page"],
            "text": text,
            "chapter": current_chapter,
            "section": current_section,
        })

    return result


def chunk_pages(pages: list[dict]) -> list[Chunk]:
    """챕터 경계를 유지하면서 텍스트 청킹"""
    chunks: list[Chunk] = []

    # 챕터별로 그룹핑
    from itertools import groupby
    for chapter, group in groupby(pages, key=lambda p: p["chapter"]):
        group_pages = list(group)
        full_text = "\n".join(p["text"] for p in group_pages)
        page_start = group_pages[0]["page"]
        page_end = group_pages[-1]["page"]
        section = group_pages[0].get("section", "")

        # 슬라이딩 윈도우 청킹
        start = 0
        while start < len(full_text):
            end = start + CHUNK_SIZE
            chunk_text = full_text[start:end].strip()
            if len(chunk_text) > 100:  # 너무 짧은 청크 제외
                chunks.append(Chunk(
                    book_id="",  # 나중에 주입
                    chapter=chapter,
                    section=section,
                    content=chunk_text,
                    page_start=page_start,
                    page_end=page_end,
                ))
            start += CHUNK_SIZE - CHUNK_OVERLAP

    return chunks


def embed_chunks(texts: list[str]) -> list[list[float]]:
    """Voyage AI로 임베딩 (배치 처리)"""
    BATCH = 128
    embeddings = []
    for i in range(0, len(texts), BATCH):
        batch = texts[i:i + BATCH]
        result = voyage.embed(batch, model="voyage-3", input_type="document")
        embeddings.extend(result.embeddings)
    return embeddings


def embed_query(text: str) -> list[float]:
    result = voyage.embed([text], model="voyage-3", input_type="query")
    return result.embeddings[0]


def ingest_pdf(pdf_bytes: bytes, filename: str, title: str) -> str:
    """
    PDF 전처리 → 임베딩 → Supabase 저장
    Returns: book_id
    """
    db = get_client()

    # 1. 교재 등록
    book_res = db.table("books").insert({
        "title": title,
        "filename": filename,
    }).execute()
    book_id = book_res.data[0]["id"]

    # 2. 페이지 추출 → 챕터 파싱 → 청킹
    pages = extract_pages(pdf_bytes)
    pages = parse_chapters(pages)

    # 페이지 수 업데이트
    db.table("books").update({"total_pages": len(pages)}).eq("id", book_id).execute()

    chunks = chunk_pages(pages)
    for c in chunks:
        c.book_id = book_id

    if not chunks:
        return book_id

    # 3. 임베딩
    texts = [c.content for c in chunks]
    embeddings = embed_chunks(texts)

    # 4. Supabase 저장 (배치)
    BATCH = 500
    for i in range(0, len(chunks), BATCH):
        batch_chunks = chunks[i:i + BATCH]
        batch_embeddings = embeddings[i:i + BATCH]
        rows = [
            {
                "book_id": c.book_id,
                "chapter": c.chapter,
                "section": c.section,
                "content": c.content,
                "page_start": c.page_start,
                "page_end": c.page_end,
                "embedding": emb,
            }
            for c, emb in zip(batch_chunks, batch_embeddings)
        ]
        db.table("chunks").insert(rows).execute()

    return book_id


def get_chapters(book_id: str) -> list[str]:
    """교재의 챕터 목록 반환"""
    db = get_client()
    res = db.rpc("get_distinct_chapters", {"p_book_id": book_id}).execute()
    if res.data:
        return [r["chapter"] for r in res.data]
    # fallback
    res = db.table("chunks").select("chapter").eq("book_id", book_id).limit(2000).execute()
    chapters = list(dict.fromkeys(r["chapter"] for r in res.data))
    return chapters


def search_chunks(query: str, book_id: str, chapter: str | None = None, top_k: int = 5) -> list[dict]:
    """RAG 검색"""
    db = get_client()
    query_emb = embed_query(query)

    res = db.rpc("match_chunks", {
        "query_embedding": query_emb,
        "target_book_id": book_id,
        "target_chapter": chapter,
        "match_count": top_k,
    }).execute()

    return res.data
