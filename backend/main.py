"""
임용고시 퀴즈 플랫폼 — FastAPI 백엔드
"""

import re
import random
import unicodedata
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from db import get_client
from ingestion import ingest_pdf, get_chapters, search_chunks
from lectures import get_lectures, get_lecture, search_chunks_for_lecture
from question_gen import generate_questions_multi, grade_essay
from spaced_repetition import update_sr_concept, get_due_concept_ids, get_due_questions

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
    types: list[Literal["mcq", "fill_blank", "matching", "essay", "short_answer"]]
    count_per_type: int = 3


def _style_examples(lecture_id, limit=3):
    """강의의 형성평가(실제 강사 출제) 문항을 생성 스타일 예시로 사용."""
    if not lecture_id:
        return []
    res = db.table("questions").select("question_data") \
        .eq("lecture_id", lecture_id).like("chapter", "[형성평가]%") \
        .limit(limit).execute()
    return [r["question_data"].get("stem", "") for r in (res.data or []) if r["question_data"].get("stem")]


# 현재 교재(books)는 전부 교육학 — 전공은 기출·교육과정 스크립트로 별도 적재됨
GENERATED_SUBJECT = "교육학"


def _get_or_create_concept(name: str, subject: str) -> str | None:
    name = (name or "").strip()
    if not name:
        return None
    existing = db.table("concepts").select("id") \
        .eq("name", name).eq("subject", subject).execute().data
    if existing:
        return existing[0]["id"]
    return db.table("concepts").insert(
        {"name": name, "subject": subject}
    ).execute().data[0]["id"]


def _extract_concept_names(q_type: str, q: dict) -> list[str]:
    """생성된 문항에서 개념명 추출 — key_concepts 우선, 빈칸은 정답 자체가 개념어."""
    names = q.get("key_concepts") or []
    if not names and q_type == "fill_blank":
        names = (q.get("answers") or [])[:1]
    return [n for n in names[:2] if n and n.strip()]


def _generate_and_store(book_id, label, lecture_id, chunks, types, count):
    """공통 생성+저장 로직 — 전 유형 1회 생성 + 배치 insert. label은 questions.chapter에 기록.
    개념 연결(question_concepts)까지 만들어야 오답이 약점 분석·SR 복습 큐에 반영된다
    (초기 Phase 1에서 이 연결이 빠져 45문항이 집계 밖에 있었음 — 2026-07-15 수정)."""
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
                "subject": GENERATED_SUBJECT,
                # mcq/matching은 재인 훈련용(stage 1) — 즉석 퀴즈·게임에선 풀 수 있지만
                # 복습 큐 기본 편입에서는 제외 (PHASE1_SPEC §5-1)
                "active": q_type not in ("mcq", "matching"),
            }
            if lecture_id:
                row["lecture_id"] = lecture_id
            rows.append(row)
            meta.append((q_type, q))
    if not rows:
        return []

    saved = db.table("questions").insert(rows).execute().data
    qc_rows = []
    all_questions = []
    for (q_type, q), row in zip(meta, saved):
        q["id"] = row["id"]
        q["type"] = q_type
        all_questions.append(q)
        for name in _extract_concept_names(q_type, q):
            cid = _get_or_create_concept(name, GENERATED_SUBJECT)
            if cid:
                qc_rows.append({"question_id": row["id"], "concept_id": cid})
    if qc_rows:
        db.table("question_concepts").upsert(
            qc_rows, on_conflict="question_id,concept_id"
        ).execute()
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
    types: list[Literal["mcq", "fill_blank", "matching", "essay", "short_answer"]] = \
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
    book_id: str | None = None   # "오늘의 복습"은 여러 책/과목을 넘나들어 단일 book_id가 없을 수 있음
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


def _norm(s: str) -> str:
    """NFC 정규화 + 괄호 내용 제거 + 공백 정리"""
    s = unicodedata.normalize("NFC", s.strip())
    s = re.sub(r'\s*[\(（][^)）]*[\)）]\s*', '', s)
    return s.strip()


def _blank_match(user: str, candidates: list[str], strict: bool = False) -> bool:
    """빈칸 하나의 답이 후보 목록 중 하나와 일치하는지 확인 (PHASE1_SPEC §6-1 채점 엄격화).
    - 완전 일치를 항상 우선 확인
    - 부분 일치는 "사용자 답이 정답을 포함하는" 방향만 허용(사용자 답 ⊇ 정답).
      반대 방향(정답이 사용자 답을 포함 — 예: 정답 "근접발달영역"에 사용자가 "발달"만
      입력해도 정답 처리되던 구 버전 버그)은 금지.
    - 부분 일치 시에도 사용자 답 길이가 정답의 60% 미만이면 무조건 오답 처리.
    - strict=True(교과교육 카드 — 고시문 용어 시험)는 완전 일치만 인정.
    - 슬래시 구분 복수 정답 문자열도 분해해서 비교."""
    u = _norm(user)
    if not u:
        return False
    for a in candidates:
        for part in re.split(r'\s*/\s*', a):
            p = _norm(part)
            if not p:
                continue
            if u == p:
                return True
            if not strict and p in u and len(u) >= len(p) * 0.6:
                return True
    return False


def _linked_concepts(question_id: str) -> list[dict]:
    """이 문항에 연결된 개념 목록 [{id, name}] (question_concepts 조인)."""
    res = db.table("question_concepts") \
        .select("concept_id, concepts(id, name)") \
        .eq("question_id", question_id).execute()
    out = []
    for r in (res.data or []):
        c = r.get("concepts")
        if c:
            out.append({"id": c["id"], "name": c["name"]})
    return out


def _concept_verdicts_from_grading(linked: list[dict], graded: list[dict]) -> list[dict]:
    """grade_essay가 개념명 기준으로 준 판정을 concept_id 기준으로 매핑."""
    by_name = {c["name"]: c["id"] for c in linked}
    out = []
    for g in graded:
        cid = by_name.get(g["name"])
        if cid:
            out.append({"concept_id": cid, "verdict": g["verdict"]})
    return out


@app.post("/sessions/answer")
async def submit_answer(req: AnswerRequest):
    """답변 제출 → 채점 → 개념 단위 SR 업데이트"""
    # 문제 조회
    q_res = db.table("questions").select("*").eq("id", req.question_id).execute()
    if not q_res.data:
        raise HTTPException(404, "문제를 찾을 수 없습니다.")

    question = q_res.data[0]
    q_type = question["type"]
    q_data = question["question_data"]
    is_curriculum = question.get("subject") == "교과교육"

    # 채점
    is_correct = False
    score = 0.0
    feedback = ""
    concept_verdicts: list[dict] = []
    linked = _linked_concepts(req.question_id)

    if q_type == "mcq":
        user_idx = req.user_answer.get("selected")
        is_correct = user_idx == q_data["answer"]
        score = 1.0 if is_correct else 0.0
        feedback = q_data.get("explanation", "")

    elif q_type == "fill_blank":
        correct_answers = [a.strip() for a in q_data.get("answers", [])]
        # texts 배열(빈칸별 독립 입력) 우선, 구버전 text 폴백
        user_texts: list[str] = req.user_answer.get("texts") or []
        if not user_texts:
            t = req.user_answer.get("text", "").strip()
            user_texts = [t] if t else []
        if not user_texts:
            is_correct = False
        elif len(user_texts) == 1:
            is_correct = _blank_match(user_texts[0], correct_answers, strict=is_curriculum)
        else:
            # 빈칸 여러 개
            # Claude가 "처방적, 역동적" 처럼 쉼표 튜플로 정답을 묶어 저장하는 경우 처리
            u_norms = [_norm(t) for t in user_texts]

            def _tuple_match(u_list: list[str], ans: str) -> bool:
                parts = [_norm(p) for p in re.split(r',\s*', ans)]
                if len(parts) != len(u_list):
                    return False
                if is_curriculum:
                    return all(u == p for u, p in zip(u_list, parts))
                return all(
                    u == p or (p in u and len(u) >= len(p) * 0.6)
                    for u, p in zip(u_list, parts)
                )

            is_correct = any(_tuple_match(u_norms, a) for a in correct_answers)
            if not is_correct:
                # 폴백: 각 빈칸을 전체 answers에서 개별 매칭
                is_correct = all(
                    _blank_match(user_texts[i], correct_answers, strict=is_curriculum)
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

    needs_self_grade = False

    if q_type in ("essay", "short_answer"):
        result = grade_essay(q_data, req.user_answer.get("text", ""))
        feedback = result["feedback"]
        if result.get("unavailable"):
            # LLM 채점 불가 → 답안은 저장하되 점수 미정으로 두고 자가 채점으로 넘긴다.
            needs_self_grade = True
            score = None
            is_correct = None
        else:
            score = result["score"]
            is_correct = score >= 0.6
            concept_verdicts = _concept_verdicts_from_grading(linked, result["concepts"])

    # mcq/fill_blank/matching은 개념별 세분화가 불가 — 문항 전체 정오답을 전 연결 개념에 적용
    if not concept_verdicts and linked and not needs_self_grade:
        verdict = "hit" if is_correct else "missing"
        concept_verdicts = [{"concept_id": c["id"], "verdict": verdict} for c in linked]

    # 답변 저장
    saved = db.table("user_answers").insert({
        "session_id": req.session_id,
        "question_id": req.question_id,
        "user_answer": req.user_answer,
        "is_correct": is_correct,
        "score": score,
        "feedback": feedback,
        "time_spent_sec": req.time_spent_sec,
        "concept_results": concept_verdicts or None,
    }).execute().data

    # 개념 단위 SR 갱신 — missing/misconception이 하나라도 있으면 quality 상한 3으로 캡
    # (점수가 높아도 간격이 크게 벌어지지 않게. PHASE1_SPEC §6-3)
    has_gap = any(v["verdict"] in ("missing", "misconception") for v in concept_verdicts)
    quality_cap = 3 if has_gap else None
    for v in concept_verdicts:
        update_sr_concept(v["concept_id"], score, quality_cap=quality_cap)

    # 세션 correct_count 업데이트
    if is_correct:
        db.rpc("increment_correct_count", {"session_id": req.session_id}).execute()

    resp = {
        "is_correct": is_correct,
        "score": score,
        "feedback": feedback,
    }
    if needs_self_grade:
        # 프론트가 모범답안을 보여주고 자가 채점 버튼을 띄울 수 있게 필요한 것만 실어보냄
        resp.update({
            "needs_self_grade": True,
            "answer_id": (saved[0]["id"] if saved else None),
            "model_answer": q_data.get("model_answer", ""),
            "key_concepts": q_data.get("key_concepts", []),
        })
    return resp


class SelfGradeRequest(BaseModel):
    answer_id: str
    verdict: Literal["ok", "partial", "no"]


SELF_GRADE_SCORE = {"ok": 1.0, "partial": 0.6, "no": 0.0}


@app.post("/sessions/self-grade")
async def self_grade(req: SelfGradeRequest):
    """AI 채점을 쓸 수 없을 때 사용자가 모범답안과 대조해 직접 판정.
    Anki류의 자기평가와 같은 방식이며, 서술형은 '내 답과 모범답안의 차이를 스스로 짚는' 것
    자체가 유효한 훈련이라 대체재로도 타당하다. 판정 후에야 SR이 갱신된다."""
    ans = db.table("user_answers").select("id, question_id, score") \
        .eq("id", req.answer_id).execute().data
    if not ans:
        raise HTTPException(404, "답안을 찾을 수 없습니다.")
    if ans[0]["score"] is not None:
        return {"ok": True, "already_graded": True}

    score = SELF_GRADE_SCORE[req.verdict]
    is_correct = score >= 0.6
    linked = _linked_concepts(ans[0]["question_id"])
    verdict = "hit" if is_correct else "missing"
    concept_verdicts = [{"concept_id": c["id"], "verdict": verdict} for c in linked]

    db.table("user_answers").update({
        "score": score,
        "is_correct": is_correct,
        "concept_results": concept_verdicts or None,
    }).eq("id", req.answer_id).execute()

    for v in concept_verdicts:
        update_sr_concept(v["concept_id"], score, quality_cap=None if is_correct else 3)

    return {"ok": True, "score": score, "is_correct": is_correct}


@app.patch("/sessions/{session_id}/complete")
async def complete_session(session_id: str):
    db.table("quiz_sessions").update({
        "status": "completed",
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", session_id).execute()
    return {"ok": True}


# ══════════════════════════════════════════
# 스페이스드 리피티션 (개념 단위 — PHASE1_SPEC §4)
# ══════════════════════════════════════════

DAILY_REVIEW_LIMIT = 15   # 복습(이미 SR 기록 있는 개념) 상한
NEW_DAILY_LIMIT = 10      # 신규(아직 한 번도 안 푼 개념) 상한 — §0-2 "복습 15 + 신규 10"


def _select_all(table: str, columns: str, filter_fn=None) -> list[dict]:
    """PostgREST 기본 응답 상한(보통 1000행)을 넘는 테이블 전량 조회.
    (마이그레이션 스크립트에서 이 한계를 모르고 단일 select만 했다가 데이터 대부분이
    누락된 적이 있어 — 커지는 테이블은 항상 이 헬퍼로 읽는다.)
    filter_fn: 쿼리 빌더에 .eq()/.gte() 등을 추가로 걸고 싶을 때 사용, 예: lambda q: q.gte("x", 1)"""
    out: list[dict] = []
    start = 0
    while True:
        q = db.table(table).select(columns)
        if filter_fn:
            q = filter_fn(q)
        res = q.range(start, start + 999).execute()
        rows = res.data or []
        out.extend(rows)
        if len(rows) < 1000:
            break
        start += 1000
    return out


def _pick_new_concept_ids(limit: int) -> list[str]:
    """아직 sr_concepts에 없는(한 번도 안 푼) 개념 중 활성 문항이 연결된 것을 신규 후보로.
    한 번도 안 푼 개념이 영원히 복습 큐에 안 나타나는 부트스트랩 갭을 해소.

    소스별로 번갈아 배정한다(라운드로빈) — 처음엔 기출만 우선했더니, 기출(105개)이
    교육과정(승인분 55개)보다 훨씬 많아서 신규 슬롯이 매일 기출로만 채워지고 교육과정
    카드가 영구적으로 밀리는 실제 버그가 있었음(2026-07-10 실사용 중 발견). 어느 한
    소스가 다른 소스를 굶기지 않도록 그룹별로 순서를 섞어 배정."""
    existing = {r["concept_id"] for r in _select_all("sr_concepts", "concept_id")}
    links = _select_all("question_concepts", "concept_id, questions(source, active)")

    by_source: dict[str, list[str]] = {}
    seen = set()
    for r in links:
        cid = r["concept_id"]
        if cid in existing or cid in seen:
            continue
        q = r.get("questions")
        if not q or not q.get("active"):
            continue
        seen.add(cid)
        by_source.setdefault(q.get("source") or "generated", []).append(cid)

    for group in by_source.values():
        random.shuffle(group)

    merged: list[str] = []
    groups = list(by_source.values())
    i = 0
    while len(merged) < limit and any(groups):
        for g in groups:
            if i < len(g):
                merged.append(g[i])
        i += 1
        groups = [g for g in groups if i < len(g)]

    return merged[:limit]


def _recently_shown_question_ids(days: int = 30) -> set[str]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = _select_all("user_answers", "question_id", lambda q: q.gte("answered_at", cutoff))
    return {r["question_id"] for r in rows}


def _pick_question_for_concept(concept_id: str, recent_qids: set[str], device: str) -> dict | None:
    """개념 1개에 대해 출제할 문항 선택.
    우선순위: 기출 중 최근 미출제 → 그 외 미출제 → 아무거나(최후수단).
    모바일이면 desk_only 문항 제외 — 후보가 하나도 없으면 개념을 건너뜀(다음 데스크톱 세션으로 이월).
    ※ 이번 라운드는 '연결된 기존 활성 문항 중 선택'까지만 구현 — 문항이 아예 없는 개념을 위한
       동적 생성 폴백(PHASE1_SPEC §4-2 ③)은 다음 라운드(기출 문제은행 적재와 함께) 과제로 남김."""
    qres = db.table("question_concepts").select("question_id").eq("concept_id", concept_id).execute()
    qids = [r["question_id"] for r in (qres.data or [])]
    if not qids:
        return None

    candidates = db.table("questions").select("*") \
        .in_("id", qids).eq("active", True).execute().data or []
    if device == "mobile":
        candidates = [q for q in candidates if not q.get("desk_only")]
    if not candidates:
        return None

    unshown = [q for q in candidates if q["id"] not in recent_qids]
    pool = unshown or candidates
    exam_first = [q for q in pool if q.get("source") == "past_exam"]
    return random.choice(exam_first or pool)


def _interleave_by_subject(cards: list[dict]) -> list[dict]:
    """같은 subject가 3연속 나오지 않도록 재배치."""
    if len(cards) <= 2:
        return cards
    random.shuffle(cards)
    for i in range(2, len(cards)):
        if cards[i]["subject"] == cards[i - 1]["subject"] == cards[i - 2]["subject"]:
            for j in range(i + 1, len(cards)):
                if cards[j]["subject"] != cards[i - 1]["subject"]:
                    cards[i], cards[j] = cards[j], cards[i]
                    break
    return cards


@app.get("/review/today")
async def review_today(device: str = "desktop"):
    """오늘의 복습 — 개념 단위 통합 큐 (PHASE1_SPEC §4-2).
    복습(이미 SR 기록 있는 개념, 상한 15) + 신규(한 번도 안 푼 개념, 상한 10)를 함께 채운다.
    응답에 due 총수(밀린 개수)를 포함하지 않는다 — §0-2 "빚 지표 노출 금지"."""
    due_ids = get_due_concept_ids(limit=DAILY_REVIEW_LIMIT * 3)
    new_ids = _pick_new_concept_ids(NEW_DAILY_LIMIT * 2)
    wanted = [(cid, False) for cid in due_ids] + [(cid, True) for cid in new_ids]
    if not wanted:
        return {"cards": []}

    all_ids = [cid for cid, _ in wanted]
    concepts_res = db.table("concepts").select("id, name, subject").in_("id", all_ids).execute()
    concepts_by_id = {c["id"]: c for c in (concepts_res.data or [])}
    recent_qids = _recently_shown_question_ids()

    cards = []
    review_count = new_count = 0
    for cid, is_new in wanted:
        count = new_count if is_new else review_count
        cap = NEW_DAILY_LIMIT if is_new else DAILY_REVIEW_LIMIT
        if count >= cap:
            continue
        concept = concepts_by_id.get(cid)
        if not concept:
            continue
        question = _pick_question_for_concept(cid, recent_qids, device)
        if not question:
            continue
        cards.append({
            "concept_id": cid,
            "concept_name": concept["name"],
            "subject": concept["subject"],
            "question": question,
        })
        if is_new:
            new_count += 1
        else:
            review_count += 1
        if review_count >= DAILY_REVIEW_LIMIT and new_count >= NEW_DAILY_LIMIT:
            break

    return {"cards": _interleave_by_subject(cards)}


@app.get("/today-plan")
async def today_plan():
    """뽀모도로(focus-app) 연동용 — /review/today 큐를 블록 목록으로 변환 (PHASE1_SPEC §7).
    개념 하나당 15분 블록 하나. focus-app이 실제 시각·휴식을 붙여 시간표로 조립한다."""
    queue = await review_today()
    return [
        {
            "block": c["concept_name"],
            "minutes": 15,
            "subject": c["subject"],
            "question_ids": [c["question"]["id"]] if c.get("question") else [],
        }
        for c in queue["cards"]
    ]


@app.post("/review/amnesty")
async def review_amnesty():
    """밀린 개념 복습을 오늘부터 14일에 걸쳐 균등 분산 재배정 (1회성, PHASE1_SPEC §4-3).
    ease/interval/repetition은 보존 — next_review_at만 재배정."""
    now = datetime.now(timezone.utc)
    overdue = db.table("sr_concepts").select("id") \
        .lte("next_review_at", now.isoformat()).execute().data or []
    if not overdue:
        return {"redistributed": 0}

    random.shuffle(overdue)
    for i, row in enumerate(overdue):
        day_offset = i % 14
        new_time = now + timedelta(days=day_offset, hours=random.uniform(0, 20))
        db.table("sr_concepts").update({"next_review_at": new_time.isoformat()}) \
            .eq("id", row["id"]).execute()

    return {"redistributed": len(overdue)}


@app.get("/review/{book_id}")
async def get_review_queue(book_id: str, limit: int = 20):
    """오늘 복습할 문제 (구 문항 단위 — 하위호환용, 신규 화면은 /review/today 사용).
    ※ /review/today 보다 반드시 뒤에 등록해야 함 — 앞에 두면 "today"를 book_id로
    오인해 UUID 캐스팅 에러(PGRST 22P02)가 남 (실배포 중 실제로 발생해 발견됨)."""
    return get_due_questions(book_id, limit)


@app.get("/stats/cumulative")
async def stats_cumulative():
    """누적 지표만 (§0-2 — 밀림/스트릭 등 감점형 지표는 절대 포함하지 않음)."""
    answers = _select_all("user_answers", "id, question_id")
    total_reviews = len(answers)

    qids = list({a["question_id"] for a in answers})
    subject_by_qid: dict[str, str] = {}
    for i in range(0, len(qids), 500):
        batch = qids[i:i + 500]
        qres = db.table("questions").select("id, subject").in_("id", batch).execute()
        for q in (qres.data or []):
            subject_by_qid[q["id"]] = q.get("subject") or "미분류"

    by_subject = Counter(subject_by_qid.get(a["question_id"], "미분류") for a in answers)
    mastered = db.table("sr_concepts").select("id", count="exact").gte("repetition", 3).execute()

    return {
        "total_reviews": total_reviews,
        "mastered_concepts": mastered.count or 0,
        "by_subject": dict(by_subject),
    }


# ══════════════════════════════════════════
# 약점 분석 (개념 단위 — PHASE1_SPEC §1-7)
# ══════════════════════════════════════════

@app.get("/weakness")
async def get_weakness():
    """개념 단위 약점 분석 — 최근 30일 평균 점수가 낮은(또는 기록 없는) 개념 우선."""
    res = db.table("weakness_view").select("*") \
        .order("avg_score_pct_30d", desc=False, nullsfirst=True) \
        .order("avg_score_pct", desc=False, nullsfirst=True) \
        .execute()
    return res.data


# ══════════════════════════════════════════
# 파트별 학습 모드 (교육학 — PHASE1_SPEC §9)
# ══════════════════════════════════════════
# 코스 = 대영역(lectures.part), 파트 = 강의(lecture).
# 진행도는 별도 테이블 없이 user_answers로 계산한다(lecture_progress는 게임 모드 전용).
# active=false인 mcq/matching도 여기서는 포함 — 학습 모드가 곧 stage 1이고,
# active 플래그의 의미는 "복습 큐 편입 여부"이지 "사용 가능 여부"가 아니다(§9-3).

# 쉬운 유형 → 어려운 유형 순서로 제시 (재인에서 회상으로)
LEARN_TYPE_ORDER = {"mcq": 0, "matching": 1, "fill_blank": 2, "short_answer": 3, "essay": 4}


def _answered_question_ids() -> set[str]:
    return {r["question_id"] for r in _select_all("user_answers", "question_id")}


def _learn_lectures() -> list[dict]:
    """강의 + 그 강의에 연결된 문항 id 목록."""
    lectures = get_lectures()
    qs = _select_all("questions", "id, lecture_id")
    by_lec: dict[str, list[str]] = {}
    for q in qs:
        if q.get("lecture_id"):
            by_lec.setdefault(q["lecture_id"], []).append(q["id"])
    for l in lectures:
        l["question_ids"] = by_lec.get(l["id"], [])
    return lectures


@app.get("/learn/areas")
async def learn_areas():
    """코스 목록 + 진행률.
    두 트랙을 함께 돌려준다:
      - kind='lecture'   : 교육학 대영역(PART) — 파트는 강의
      - kind='curriculum': 교과교육학 과목 — 중간 단계 없이 바로 8문항 세션
    진행 중인 코스가 먼저 오도록 정렬."""
    lectures = _learn_lectures()
    answered = _answered_question_ids()

    areas: dict[str, dict] = {}
    for l in lectures:
        qids = l["question_ids"]
        if not qids:
            continue  # 문제가 없는 강의는 학습 단위가 안 되므로 제외
        key = l.get("part") or "기타"
        a = areas.setdefault(key, {"key": key, "part": key, "kind": "lecture",
                                    "lectures": 0, "done_lectures": 0,
                                    "total_q": 0, "answered_q": 0})
        done_here = sum(1 for q in qids if q in answered)
        a["lectures"] += 1
        a["total_q"] += len(qids)
        a["answered_q"] += done_here
        if done_here == len(qids):
            a["done_lectures"] += 1

    # 교과교육학 — 강의 체계가 없으므로 과목(questions.chapter)이 곧 코스
    cur = db.table("questions").select("id, chapter") \
        .eq("source", "curriculum").eq("active", True).execute().data or []
    for q in cur:
        key = q["chapter"] or "[교육과정] 기타"
        a = areas.setdefault(key, {"key": key, "part": key.replace("[교육과정]", "").strip(),
                                    "kind": "curriculum", "lectures": 0, "done_lectures": 0,
                                    "total_q": 0, "answered_q": 0})
        a["total_q"] += 1
        if q["id"] in answered:
            a["answered_q"] += 1

    out = list(areas.values())
    def rank(a):
        if a["total_q"] and a["answered_q"] >= a["total_q"]:
            return 2
        return 0 if a["answered_q"] > 0 else 1
    out.sort(key=lambda a: (rank(a), a["kind"] != "curriculum", a["part"]))
    return out


@app.get("/learn/curriculum/{chapter}")
async def learn_curriculum(chapter: str, limit: int = 8):
    """교과교육학 과목 하나에서 미답 카드 위주로 세션 구성.
    강의(lecture) 체계가 없는 트랙이라 lecture 기반 엔드포인트를 쓸 수 없어 별도로 둔다."""
    all_q = db.table("questions").select("*") \
        .eq("source", "curriculum").eq("active", True).eq("chapter", chapter).execute().data or []
    if not all_q:
        raise HTTPException(404, "해당 과목의 카드가 없습니다.")
    all_q.sort(key=lambda q: (LEARN_TYPE_ORDER.get(q["type"], 9), q["created_at"]))

    qids = [q["id"] for q in all_q]
    prev: dict[str, dict] = {}
    rows = db.table("user_answers") \
        .select("id, question_id, is_correct, score, feedback, answered_at") \
        .in_("question_id", qids).order("answered_at").execute().data or []
    for r in rows:
        prev[r["question_id"]] = r

    unanswered = [q for q in all_q if q["id"] not in prev]
    questions = (unanswered or all_q)[:limit]
    remaining = max(0, len(unanswered) - len(questions))

    return {
        "lecture": {"id": chapter, "lecture_no": 0,
                     "title": chapter.replace("[교육과정]", "").strip(), "part": chapter},
        "questions": questions,
        "answered": {q["id"]: prev[q["id"]] for q in questions if q["id"] in prev},
        "remaining": remaining,
        "lecture_total": len(all_q),
        "lecture_answered": len(prev),
    }


@app.get("/learn/areas/{part}/parts")
async def learn_parts(part: str):
    """한 대영역의 파트(강의) 목록 + 파트별 진행."""
    answered = _answered_question_ids()
    out = []
    for l in _learn_lectures():
        if (l.get("part") or "기타") != part or not l["question_ids"]:
            continue
        qids = l["question_ids"]
        done = sum(1 for q in qids if q in answered)
        out.append({
            "lecture_id": l["id"], "lecture_no": l["lecture_no"], "title": l["title"],
            "source": l.get("source"), "total": len(qids), "answered": done,
            "done": done == len(qids),
        })
    out.sort(key=lambda x: (x["source"] != "main", x["lecture_no"] or 0))
    return out


LEARN_SESSION_SIZE = 8   # 한 번에 내주는 최대 문항 수


@app.get("/learn/parts/{lecture_id}")
async def learn_part(lecture_id: str, limit: int = LEARN_SESSION_SIZE):
    """파트 하나 = 그 강의의 문제 세트(쉬운 유형 → 어려운 유형).

    강의마다 문항 수 편차가 크다(1~23개). 23문항을 한 번에 내주면 사용자가 지적한
    '한 화면에 너무 많다' 문제가 그대로 재현되므로, **미답 문항 위주로 최대 limit개**만
    내주고 나머지는 remaining으로 알린다(§9-2, §0-2 "끝낼 수 있는 크기")."""
    lecture = get_lecture(lecture_id)
    if not lecture:
        raise HTTPException(404, "강의를 찾을 수 없습니다.")

    all_q = db.table("questions").select("*").eq("lecture_id", lecture_id).execute().data or []
    all_q.sort(key=lambda q: (LEARN_TYPE_ORDER.get(q["type"], 9), q["created_at"]))

    qids = [q["id"] for q in all_q]
    prev: dict[str, dict] = {}
    if qids:
        rows = db.table("user_answers") \
            .select("id, question_id, is_correct, score, feedback, user_answer, answered_at") \
            .in_("question_id", qids).order("answered_at").execute().data or []
        for r in rows:      # 같은 문항을 여러 번 풀었으면 최신 답안만 남김
            prev[r["question_id"]] = r

    unanswered = [q for q in all_q if q["id"] not in prev]
    if unanswered:
        questions = unanswered[:limit]
        remaining = len(unanswered) - len(questions)
    else:
        # 이미 다 푼 강의 → 복습으로 전체를 다시 보여준다
        questions = all_q[:limit]
        remaining = 0

    return {
        "lecture": {"id": lecture["id"], "lecture_no": lecture["lecture_no"],
                     "title": lecture["title"], "part": lecture.get("part")},
        "questions": questions,
        "answered": {q["id"]: prev[q["id"]] for q in questions if q["id"] in prev},
        "remaining": remaining,
        "lecture_total": len(all_q),
        "lecture_answered": len(prev),
    }


# ══════════════════════════════════════════
# 검수함 (source='curriculum'의 active=false 카드 검토 — PHASE1_SPEC §5/§7)
# ══════════════════════════════════════════
# 주의: mcq/matching 레거시 문항도 active=false지만(§5-1, stage1 전용 의도적 비활성)
# 이건 "검수 대기"가 아니라 설계상 상태라 검수함 대상이 아님 — source='curriculum'만 다룬다.

@app.get("/inbox")
async def list_inbox(q_type: str | None = None, limit: int = 50, offset: int = 0):
    """검수 대기 카드 목록."""
    query = db.table("questions").select("*", count="exact") \
        .eq("source", "curriculum").eq("active", False)
    if q_type:
        query = query.eq("type", q_type)
    res = query.order("chapter").range(offset, offset + limit - 1).execute()
    return {"items": res.data, "total": res.count or 0}


class InboxActionRequest(BaseModel):
    question_ids: list[str]


@app.post("/inbox/approve")
async def approve_inbox(req: InboxActionRequest):
    """선택한 카드를 활성화 + 검수 완료 처리 → 오늘의 복습 큐(신규)에 편입 가능해짐."""
    if not req.question_ids:
        return {"approved": 0}
    db.table("questions").update({"active": True, "answer_verified": True}) \
        .in_("id", req.question_ids).execute()
    return {"approved": len(req.question_ids)}


@app.post("/inbox/reject")
async def reject_inbox(req: InboxActionRequest):
    """선택한 카드를 삭제 (연결된 question_concepts는 FK cascade로 함께 제거됨)."""
    if not req.question_ids:
        return {"rejected": 0}
    db.table("questions").delete().in_("id", req.question_ids).execute()
    return {"rejected": len(req.question_ids)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
