"""
임용고시 퀴즈 플랫폼 — FastAPI 백엔드
"""

from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from db import get_client
from ingestion import ingest_pdf, get_chapters, search_chunks
from question_gen import generate_questions, grade_essay
from spaced_repetition import update_sr_card, get_due_questions

app = FastAPI(title="임용고시 퀴즈 플랫폼")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

db = get_client()

# ══════════════════════════════════════════
# 교재 관련
# ══════════════════════════════════════════

@app.post("/books/upload")
async def upload_book(file: UploadFile = File(...), title: str = ""):
    """PDF 업로드 → 파이프라인 실행"""
    if not file.filename.endswith(".pdf"):
        raise HTTPException(400, "PDF 파일만 업로드 가능합니다.")

    contents = await file.read()
    book_title = title or file.filename.replace(".pdf", "")

    book_id = ingest_pdf(contents, file.filename, book_title)
    chapters = get_chapters(book_id)

    return {"book_id": book_id, "title": book_title, "chapters": chapters}


@app.get("/books")
async def list_books():
    res = db.table("books").select("*").order("created_at", desc=True).execute()
    return res.data


@app.get("/books/{book_id}/chapters")
async def list_chapters(book_id: str):
    return get_chapters(book_id)


@app.get("/chunks")
async def list_chunks(book_id: str, chapter: str | None = None):
    query = db.table("chunks").select("id, chapter, content, page_start") \
        .eq("book_id", book_id)
    if chapter:
        query = query.eq("chapter", chapter)
    res = query.order("page_start").limit(200).execute()
    return res.data


# ══════════════════════════════════════════
# 문제 생성
# ══════════════════════════════════════════

class GenerateRequest(BaseModel):
    book_id: str
    chapter: str
    types: list[Literal["mcq", "fill_blank", "matching", "essay"]]
    count_per_type: int = 3

@app.post("/questions/generate")
async def generate(req: GenerateRequest):
    """챕터 + 유형 → 문제 생성 (RAG 기반)"""
    all_questions = []

    for q_type in req.types:
        # RAG 검색
        query = f"{req.chapter} 핵심 개념 이론"
        chunks = search_chunks(query, req.book_id, req.chapter, top_k=5)

        if not chunks:
            continue

        # 문제 생성
        raw_questions = generate_questions(chunks, q_type, req.count_per_type)

        # DB 저장
        for q in raw_questions:
            res = db.table("questions").insert({
                "book_id": req.book_id,
                "chapter": req.chapter,
                "type": q_type,
                "difficulty": 3,
                "question_data": q,
                "source_chunk_ids": [c["id"] for c in chunks],
            }).execute()
            q["id"] = res.data[0]["id"]
            q["type"] = q_type
            all_questions.append(q)

    return {"questions": all_questions}


@app.get("/questions")
async def list_questions(book_id: str, chapter: str | None = None, q_type: str | None = None):
    """저장된 문제 목록"""
    query = db.table("questions").select("*").eq("book_id", book_id)
    if chapter:
        query = query.eq("chapter", chapter)
    if q_type:
        query = query.eq("type", q_type)
    res = query.order("created_at", desc=True).execute()
    return res.data


# ══════════════════════════════════════════
# 퀴즈 세션
# ══════════════════════════════════════════

class StartSessionRequest(BaseModel):
    book_id: str
    chapter: str
    question_ids: list[str]

@app.post("/sessions")
async def start_session(req: StartSessionRequest):
    """퀴즈 세션 시작"""
    res = db.table("quiz_sessions").insert({
        "book_id": req.book_id,
        "chapter": req.chapter,
        "total_questions": len(req.question_ids),
    }).execute()
    session_id = res.data[0]["id"]

    # 문제 상세 반환
    questions = db.table("questions") \
        .select("*") \
        .in_("id", req.question_ids) \
        .execute().data

    return {"session_id": session_id, "questions": questions}


class AnswerRequest(BaseModel):
    session_id: str
    question_id: str
    user_answer: dict
    time_spent_sec: int = 0

@app.post("/sessions/answer")
async def submit_answer(req: AnswerRequest):
    """답변 제출 → 채점 → SR 업데이트"""
    # 문제 조회
    q_res = db.table("questions").select("*").eq("id", req.question_id).execute()
    if not q_res.data:
        raise HTTPException(404, "문제를 찾을 수 없습니다.")

    question = q_res.data[0]
    q_type = question["type"]
    q_data = question["question_data"]

    # 채점
    is_correct = False
    score = 0.0
    feedback = ""

    if q_type == "mcq":
        user_idx = req.user_answer.get("selected")
        is_correct = user_idx == q_data["answer"]
        score = 1.0 if is_correct else 0.0
        feedback = q_data.get("explanation", "")

    elif q_type == "fill_blank":
        user_text = req.user_answer.get("text", "").strip()
        correct_answers = [a.strip() for a in q_data.get("answers", [])]
        is_correct = any(user_text == a or user_text in a for a in correct_answers)
        score = 1.0 if is_correct else 0.0

    elif q_type == "matching":
        user_pairs = req.user_answer.get("pairs", [])
        correct_pairs = q_data.get("pairs", [])
        correct_set = {tuple(p) for p in correct_pairs}
        user_set = {tuple(p) for p in user_pairs}
        score = len(correct_set & user_set) / max(len(correct_set), 1)
        is_correct = score == 1.0

    elif q_type == "essay":
        result = grade_essay(q_data, req.user_answer.get("text", ""))
        score = result["score"]
        feedback = result["feedback"]
        is_correct = score >= 0.6

    # 답변 저장
    db.table("user_answers").insert({
        "session_id": req.session_id,
        "question_id": req.question_id,
        "user_answer": req.user_answer,
        "is_correct": is_correct,
        "score": score,
        "feedback": feedback,
        "time_spent_sec": req.time_spent_sec,
    }).execute()

    # SR 카드 업데이트
    update_sr_card(req.question_id, score)

    # 세션 correct_count 업데이트
    if is_correct:
        db.rpc("increment_correct_count", {"session_id": req.session_id}).execute()

    return {
        "is_correct": is_correct,
        "score": score,
        "feedback": feedback,
    }


@app.patch("/sessions/{session_id}/complete")
async def complete_session(session_id: str):
    db.table("quiz_sessions").update({
        "status": "completed",
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", session_id).execute()
    return {"ok": True}


# ══════════════════════════════════════════
# 스페이스드 리피티션
# ══════════════════════════════════════════

@app.get("/review/{book_id}")
async def get_review_queue(book_id: str, limit: int = 20):
    """오늘 복습할 문제"""
    return get_due_questions(book_id, limit)


# ══════════════════════════════════════════
# 약점 분석
# ══════════════════════════════════════════

@app.get("/weakness/{book_id}")
async def get_weakness(book_id: str):
    """챕터별 약점 분석"""
    res = db.table("weakness_view") \
        .select("*") \
        .eq("book_id", book_id) \
        .order("avg_score_pct") \
        .execute()
    return res.data


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
