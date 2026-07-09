"""
SM-2 알고리즘 기반 스페이스드 리피티션

Phase 1(2026-07)부터 SR의 단위를 문항(sr_cards)에서 개념(sr_concepts)으로 전환.
sr_cards/update_sr_card·get_due_questions는 마이그레이션 스크립트(migrate_concepts.py)의
과거 데이터 이관 용도로만 남겨두고, 신규 코드 경로(main.py)는 개념 단위 함수를 사용한다.
"""

from datetime import datetime, timedelta, timezone
from db import get_client


def _sm2_step(ef: float, interval: int, repetition: int, quality: int) -> tuple[float, int, int]:
    """SM-2 핵심 계산. quality: 0~5 (반올림된 정수)."""
    if quality < 3:
        repetition = 0
        interval = 1
    else:
        if repetition == 0:
            interval = 1
        elif repetition == 1:
            interval = 6
        else:
            interval = round(interval * ef)
        repetition += 1

    ef = ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    ef = max(1.3, ef)
    return round(ef, 2), interval, repetition


# ── 개념 단위 (신규 — main.py가 사용) ────────────────────────────

def update_sr_concept(concept_id: str, score: float, quality_cap: int | None = None):
    """
    score: 0.0~1.0 → quality 0~5로 변환해 SM-2 갱신.
    quality_cap: 서술형 채점에서 missing/misconception 개념이 있으면 상한(예: 3)을 걸어
                 (§6-2) 점수가 높아도 간격이 크게 벌어지지 않게 한다.
    """
    db = get_client()
    now = datetime.now(timezone.utc)

    res = db.table("sr_concepts").select("*").eq("concept_id", concept_id).execute()
    if res.data:
        card = res.data[0]
        ef, interval, repetition = card["ease_factor"], card["interval_days"], card["repetition"]
    else:
        ef, interval, repetition = 2.5, 1, 0

    quality = round(score * 5)
    if quality_cap is not None:
        quality = min(quality, quality_cap)

    ef, interval, repetition = _sm2_step(ef, interval, repetition, quality)
    next_review = now + timedelta(days=interval)

    data = {
        "concept_id": concept_id,
        "ease_factor": ef,
        "interval_days": interval,
        "repetition": repetition,
        "next_review_at": next_review.isoformat(),
        "last_reviewed_at": now.isoformat(),
    }
    if res.data:
        db.table("sr_concepts").update(data).eq("concept_id", concept_id).execute()
    else:
        db.table("sr_concepts").insert(data).execute()


def get_due_concept_ids(limit: int = 20) -> list[str]:
    """오늘 복습 기한이 된 개념 id 목록 (책/과목 무관 통합)."""
    db = get_client()
    now = datetime.now(timezone.utc).isoformat()
    res = db.table("sr_concepts").select("concept_id") \
        .lte("next_review_at", now) \
        .order("next_review_at") \
        .limit(limit).execute()
    return [r["concept_id"] for r in (res.data or [])]


# ── 문항 단위 (레거시 — migrate_concepts.py 이관용으로만 유지) ──────

def update_sr_card(question_id: str, score: float):
    db = get_client()
    now = datetime.now(timezone.utc)

    res = db.table("sr_cards").select("*").eq("question_id", question_id).execute()
    if res.data:
        card = res.data[0]
        ef, interval, repetition = card["ease_factor"], card["interval_days"], card["repetition"]
    else:
        ef, interval, repetition = 2.5, 1, 0

    quality = round(score * 5)
    ef, interval, repetition = _sm2_step(ef, interval, repetition, quality)
    next_review = now + timedelta(days=interval)

    data = {
        "question_id": question_id,
        "ease_factor": ef,
        "interval_days": interval,
        "repetition": repetition,
        "next_review_at": next_review.isoformat(),
        "last_reviewed_at": now.isoformat(),
    }
    if res.data:
        db.table("sr_cards").update(data).eq("question_id", question_id).execute()
    else:
        db.table("sr_cards").insert(data).execute()


def get_due_questions(book_id: str, limit: int = 20) -> list[dict]:
    """오늘 복습할 문제 목록 (next_review_at <= now) — 구 화면(호환용)."""
    db = get_client()
    now = datetime.now(timezone.utc).isoformat()
    res = db.rpc("get_due_questions", {
        "p_book_id": book_id,
        "p_now": now,
        "p_limit": limit,
    }).execute()
    return res.data or []
