"""
SM-2 알고리즘 기반 스페이스드 리피티션
"""

from datetime import datetime, timedelta, timezone
from db import get_client


def update_sr_card(question_id: str, score: float):
    """
    score: 0.0 ~ 1.0
      0.0~0.39 → 다시 시작 (틀림)
      0.4~0.59 → 맞았지만 어려움
      0.6~1.0  → 완벽
    """
    db = get_client()
    now = datetime.now(timezone.utc)

    # 기존 카드 조회
    res = db.table("sr_cards").select("*").eq("question_id", question_id).execute()

    if res.data:
        card = res.data[0]
        ef = card["ease_factor"]
        interval = card["interval_days"]
        repetition = card["repetition"]
    else:
        ef = 2.5
        interval = 1
        repetition = 0

    # SM-2 계산
    # quality: 0~5로 변환
    quality = round(score * 5)

    if quality < 3:
        # 틀림 → 처음부터
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

    # Ease Factor 업데이트
    ef = ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    ef = max(1.3, ef)  # 최소값

    next_review = now + timedelta(days=interval)

    data = {
        "question_id": question_id,
        "ease_factor": round(ef, 2),
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
    """오늘 복습할 문제 목록 (next_review_at <= now)"""
    db = get_client()
    now = datetime.now(timezone.utc).isoformat()

    res = db.rpc("get_due_questions", {
        "p_book_id": book_id,
        "p_now": now,
        "p_limit": limit,
    }).execute()

    return res.data or []
