"""
임용고시 퀴즈 플랫폼 — FastAPI 백엔드
"""

import re
import random
import unicodedata
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from db import get_client
from ingestion import ingest_pdf, get_chapters, search_chunks
from lectures import get_lectures, get_lecture, search_chunks_for_lecture
from question_gen import generate_questions_multi, grade_essay
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


@app.get("/books/{book_id}/lectures")
async def list_lectures(book_id: str):
    """교재의 강의 목록 (강의별 문제풀기용)"""
    return get_lectures(book_id)


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
    chapter: str | None = None       # 챕터별 생성
    lecture_id: str | None = None    # 강의별 생성 (둘 중 하나)
    types: list[Literal["mcq", "fill_blank", "matching", "essay"]]
    count_per_type: int = 3


def _style_examples(lecture_id, limit=3):
    """강의의 형성평가(실제 강사 출제) 문항을 생성 스타일 예시로 사용."""
    if not lecture_id:
        return []
    res = db.table("questions").select("question_data") \
        .eq("lecture_id", lecture_id).like("chapter", "[형성평가]%") \
        .limit(limit).execute()
    return [r["question_data"].get("stem", "") for r in (res.data or []) if r["question_data"].get("stem")]


def _generate_and_store(book_id, label, lecture_id, chunks, types, count):
    """공통 생성+저장 로직 — 전 유형 1회 생성 + 배치 insert. label은 questions.chapter에 기록."""
    if not chunks:
        return []
    by_type = generate_questions_multi(chunks, types, count, style_examples=_style_examples(lecture_id))
    chunk_ids = [c["id"] for c in chunks]

    rows, meta = [], []
    for q_type in types:
        for q in by_type.get(q_type, []):
            row = {
                "book_id": book_id,
                "chapter": label,
                "type": q_type,
                "difficulty": 3,
                "question_data": q,
                "source_chunk_ids": chunk_ids,
            }
            if lecture_id:
                row["lecture_id"] = lecture_id
            rows.append(row)
            meta.append((q_type, q))
    if not rows:
        return []

    saved = db.table("questions").insert(rows).execute().data
    all_questions = []
    for (q_type, q), row in zip(meta, saved):
        q["id"] = row["id"]
        q["type"] = q_type
        all_questions.append(q)
    return all_questions


@app.post("/questions/generate")
async def generate(req: GenerateRequest):
    """챕터 또는 강의 + 유형 → 문제 생성 (RAG 기반)"""
    if req.lecture_id:
        lecture = get_lecture(req.lecture_id)
        if not lecture:
            raise HTTPException(404, "강의를 찾을 수 없습니다.")
        chunks = search_chunks_for_lecture(lecture, top_k=6)
        label = f"{lecture['lecture_no']}강 {lecture['title']}"[:120]
        questions = _generate_and_store(
            req.book_id, label, req.lecture_id, chunks, req.types, req.count_per_type
        )
        return {"questions": questions}

    if not req.chapter:
        raise HTTPException(400, "chapter 또는 lecture_id가 필요합니다.")

    query = f"{req.chapter} 핵심 개념 이론"
    chunks = search_chunks(query, req.book_id, req.chapter, top_k=5)
    questions = _generate_and_store(
        req.book_id, req.chapter, None, chunks, req.types, req.count_per_type
    )
    return {"questions": questions}


@app.get("/lectures/{lecture_id}/questions")
async def lecture_questions(lecture_id: str):
    """강의에 미리 만들어둔 문제(문제은행) 조회"""
    res = db.table("questions").select("*") \
        .eq("lecture_id", lecture_id) \
        .order("created_at", desc=True).execute()
    return res.data


class PrebuildRequest(BaseModel):
    types: list[Literal["mcq", "fill_blank", "matching", "essay"]] = \
        ["mcq", "fill_blank", "matching", "essay"]
    count_per_type: int = 3

@app.post("/lectures/{lecture_id}/prebuild")
async def prebuild_lecture(lecture_id: str, req: PrebuildRequest):
    """강의 문제은행 미리 생성"""
    lecture = get_lecture(lecture_id)
    if not lecture:
        raise HTTPException(404, "강의를 찾을 수 없습니다.")
    chunks = search_chunks_for_lecture(lecture, top_k=6)
    label = f"{lecture['lecture_no']}강 {lecture['title']}"[:120]
    questions = _generate_and_store(
        lecture["book_id"], label, lecture_id, chunks, req.types, req.count_per_type
    )
    return {"created": len(questions), "questions": questions}


# ══════════════════════════════════════════
# 강의 정복 게임 모드
# ══════════════════════════════════════════

# 스테이지 구성: 잡몹(객관식) → 중간보스(빈칸·짝맞추기) → 보스(서술형)
GAME_STAGE_PLAN = [("mcq", 3), ("fill_blank", 2), ("matching", 1), ("essay", 1)]


@app.get("/game/progress")
async def game_progress(book_id: str):
    """강의 목록 + 게임 진행도 (스테이지 맵용)"""
    lectures = get_lectures(book_id)
    ids = [l["id"] for l in lectures]
    if not ids:
        return []
    res = db.table("lecture_progress").select("*").in_("lecture_id", ids).execute()
    by_lec = {p["lecture_id"]: p for p in (res.data or [])}
    return [{**l, "progress": by_lec.get(l["id"])} for l in lectures]


@app.post("/game/lectures/{lecture_id}/start")
async def game_start(lecture_id: str):
    """스테이지 시작 — 문제은행에서 구성을 채우고 부족한 유형만 AI 생성으로 보충."""
    lecture = get_lecture(lecture_id)
    if not lecture:
        raise HTTPException(404, "강의를 찾을 수 없습니다.")

    bank = db.table("questions").select("*") \
        .eq("lecture_id", lecture_id).execute().data or []
    by_type: dict[str, list] = {}
    for q in bank:
        by_type.setdefault(q["type"], []).append(q)

    picked_ids: dict[str, list[str]] = {}
    missing: dict[str, int] = {}
    for t, n in GAME_STAGE_PLAN:
        have = by_type.get(t, [])
        sample = random.sample(have, min(n, len(have)))  # 재도전마다 다른 문제
        picked_ids[t] = [q["id"] for q in sample]
        if len(have) < n:
            missing[t] = n - len(have)

    if missing:
        chunks = search_chunks_for_lecture(lecture, top_k=6)
        label = f"{lecture['lecture_no']}강 {lecture['title']}"[:120]
        generated = _generate_and_store(
            lecture["book_id"], label, lecture_id, chunks,
            list(missing.keys()), missing,
        )
        for q in generated:
            t = q["type"]
            if len(picked_ids.get(t, [])) < dict(GAME_STAGE_PLAN)[t]:
                picked_ids.setdefault(t, []).append(q["id"])

    ordered_ids = [qid for t, _ in GAME_STAGE_PLAN for qid in picked_ids.get(t, [])]
    if not ordered_ids:
        raise HTTPException(400, "문제를 준비하지 못했어요. 잠시 후 다시 시도해주세요.")

    sess = db.table("quiz_sessions").insert({
        "book_id": lecture["book_id"],
        "chapter": f"[게임] {lecture['lecture_no']}강 {lecture['title']}"[:120],
        "total_questions": len(ordered_ids),
    }).execute()

    rows = db.table("questions").select("*").in_("id", ordered_ids).execute().data
    by_id = {r["id"]: r for r in rows}
    questions = [by_id[qid] for qid in ordered_ids if qid in by_id]

    return {"session_id": sess.data[0]["id"], "questions": questions}


class GameRecordRequest(BaseModel):
    cleared: bool
    score: int = 0
    stars: int = 0
    max_combo: int = 0

@app.post("/game/lectures/{lecture_id}/record")
async def game_record(lecture_id: str, req: GameRecordRequest):
    """게임 결과 기록 — 최고 기록만 갱신, 시도 횟수 누적."""
    res = db.table("lecture_progress").select("*") \
        .eq("lecture_id", lecture_id).execute()
    prev = res.data[0] if res.data else None

    row = {
        "lecture_id": lecture_id,
        "cleared": (prev or {}).get("cleared", False) or req.cleared,
        "stars": max((prev or {}).get("stars", 0), req.stars),
        "best_score": max((prev or {}).get("best_score", 0), req.score),
        "best_combo": max((prev or {}).get("best_combo", 0), req.max_combo),
        "attempts": (prev or {}).get("attempts", 0) + 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if req.cleared and not (prev or {}).get("cleared"):
        row["cleared_at"] = datetime.now(timezone.utc).isoformat()

    db.table("lecture_progress").upsert(row, on_conflict="lecture_id").execute()
    return row


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
        def _norm(s: str) -> str:
            """NFC 정규화 + 괄호 내용 제거 + 공백 정리"""
            s = unicodedata.normalize("NFC", s.strip())
            s = re.sub(r'\s*[\(（][^)）]*[\)）]\s*', '', s)
            return s.strip()

        def _blank_match(user: str, candidates: list[str]) -> bool:
            """빈칸 하나의 답이 후보 목록 중 하나와 일치하는지 확인.
            - 슬래시 구분 단일 문자열도 분해해서 비교
            - 괄호 표기(숙의(熟議)) 제거 후 비교
            - 대소문자·공백 무시"""
            u = _norm(user)
            if not u:
                return False
            for a in candidates:
                # 슬래시로 묶인 경우 분해
                for part in re.split(r'\s*/\s*', a):
                    p = _norm(part)
                    if u == p or u in p or p in u:
                        return True
            return False

        correct_answers = [a.strip() for a in q_data.get("answers", [])]
        # texts 배열(빈칸별 독립 입력) 우선, 구버전 text 폴백
        user_texts: list[str] = req.user_answer.get("texts") or []
        if not user_texts:
            t = req.user_answer.get("text", "").strip()
            user_texts = [t] if t else []
        if not user_texts:
            is_correct = False
        elif len(user_texts) == 1:
            is_correct = _blank_match(user_texts[0], correct_answers)
        else:
            # 빈칸 여러 개: texts[i] → answers[i]
            is_correct = all(
                _blank_match(user_texts[i],
                             correct_answers[i:i+1] if i < len(correct_answers) else correct_answers)
                for i in range(len(user_texts))
            )
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
