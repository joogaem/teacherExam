"""
Phase 1 데이터 마이그레이션 (1회 실행 스크립트) — PHASE1_SPEC §8-1

전제: supabase/phase1.sql 이 먼저 Supabase SQL Editor에서 실행되어
     concepts/question_concepts/sr_concepts 테이블이 존재해야 한다.

수행 내용:
  1. 기존 생성 문항(subject 미설정, 현재 690개 전부 교육학 교재 기반) → subject='교육학'
  2. 각 문항에서 핵심 개념명 추출 → concepts upsert → question_concepts 연결
     - essay/short_answer: 이미 있는 question_data.key_concepts 그대로 사용(무료, LLM 호출 없음)
     - mcq/fill_blank/matching: LLM 배치 호출로 추출
  3. mcq/matching 문항 → active=false (§5-1 — stage1 신규개념 진입 전용, 기본 큐 제외)
  4. 기존 sr_cards(문항 단위) → sr_concepts(개념 단위) 병합
     — 같은 개념에 여러 카드가 걸리면 가장 보수적인 상태(interval_days 최솟값) 채택

실행: python migrate_concepts.py --dry-run   (먼저 반영 없이 결과만 확인)
      python migrate_concepts.py             (실제 반영)

멱등성: concepts는 (name,subject) unique, question_concepts는 PK(question_id,concept_id)
       — 재실행해도 중복 생기지 않음. 단, subject가 이미 채워진 문항은 대상에서 빠지므로
       "부분 실패 후 재실행" 시나리오에서는 subject를 채우기 전에 끊기면 그 배치만 재시도됨.
"""
import argparse
import sys
from collections import defaultdict

from db import get_client
from question_gen import claude, MODEL, _parse_json

BATCH_LLM = 15       # LLM 호출당 문항 수
BATCH_DB = 100       # DB 배치 갱신 단위
PAGE_SIZE = 1000     # PostgREST 기본 응답 상한(설정에 따라 다를 수 있으나 1000이 보수적 기본값)


def _select_all(table: str, columns: str) -> list[dict]:
    """PostgREST의 기본 최대 응답 행 수(보통 1000) 제한을 넘는 테이블을 전량 조회.
    (마이그레이션 첫 실행에서 question_concepts 2460행을 단일 select로 읽다가
    1000행에서 잘려 sr_cards 이관이 대부분 누락된 버그의 재발 방지용.)"""
    db = get_client()
    out: list[dict] = []
    start = 0
    while True:
        res = db.table(table).select(columns).range(start, start + PAGE_SIZE - 1).execute()
        rows = res.data or []
        out.extend(rows)
        if len(rows) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    return out


def _question_context(q: dict) -> str:
    d = q["question_data"] or {}
    t = q["type"]
    if t in ("essay", "short_answer"):
        return d.get("stem", "")
    if t == "fill_blank":
        return d.get("template", "")
    if t == "mcq":
        return d.get("stem", "")
    if t == "matching":
        parts = d.get("left", []) + d.get("right", [])
        return f"{d.get('instruction', '')} / {', '.join(parts)}"
    return ""


def extract_concepts_batch(questions: list[dict]) -> dict[str, list[str]]:
    """문항id → 핵심 개념명 리스트. essay/short_answer는 기존 key_concepts 재사용(무료)."""
    result: dict[str, list[str]] = {}
    to_call = []
    for q in questions:
        d = q["question_data"] or {}
        if q["type"] in ("essay", "short_answer") and d.get("key_concepts"):
            result[q["id"]] = d["key_concepts"]
        else:
            to_call.append(q)

    print(f"  key_concepts 재사용: {len(result)}개, LLM 추출 대상: {len(to_call)}개")

    for i in range(0, len(to_call), BATCH_LLM):
        batch = to_call[i:i + BATCH_LLM]
        items = "\n".join(f'- id={q["id"]}: {_question_context(q)[:200]}' for q in batch)
        prompt = (
            "다음은 교육학 임용고시 문제 목록이다. 각 문제가 테스트하는 핵심 개념명을 "
            "1~2개씩 뽑아라(간결한 명사구, 예: '근접발달영역', 'SM-2 알고리즘', '타일러 목표중심 모형').\n\n"
            f"{items}\n\n"
            '[출력 형식 — 아래 키를 가진 JSON 객체 하나만 출력, 다른 텍스트 없이]\n'
            '{"문제id": ["개념명", ...], ...}'
        )
        try:
            msg = claude.messages.create(
                model=MODEL, max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            parsed = _parse_json(msg.content[0].text)
        except Exception as e:
            print(f"  ! 배치 {i}~{i+len(batch)} 실패: {e}", file=sys.stderr)
            parsed = {}
        if isinstance(parsed, dict):
            result.update(parsed)
        print(f"  LLM 배치 {i + len(batch)}/{len(to_call)} 완료")
    return result


def migrate_sr_cards(dry_run: bool):
    db = get_client()
    cards = db.table("sr_cards").select("*").execute().data or []
    print(f"기존 sr_cards: {len(cards)}개 → sr_concepts 병합")
    if not cards:
        return

    qc = _select_all("question_concepts", "question_id, concept_id")
    print(f"  question_concepts 전량 조회: {len(qc)}행 (페이지네이션 적용)")
    by_question: dict[str, list[str]] = defaultdict(list)
    for r in qc:
        by_question[r["question_id"]].append(r["concept_id"])

    # concept_id → 채택할 카드 상태 (interval_days가 작을수록 보수적 = 우선 채택)
    best: dict[str, dict] = {}
    unmapped = 0
    for card in cards:
        cids = by_question.get(card["question_id"])
        if not cids:
            unmapped += 1
            continue
        for cid in cids:
            cur = best.get(cid)
            if cur is None or card["interval_days"] < cur["interval_days"]:
                best[cid] = card

    if unmapped:
        print(f"  ! 개념 연결 없는 sr_card {unmapped}개는 건너뜀(해당 문항에 개념 추출 실패)")

    rows = [{
        "concept_id": cid,
        "ease_factor": card["ease_factor"],
        "interval_days": card["interval_days"],
        "repetition": card["repetition"],
        "next_review_at": card["next_review_at"],
        "last_reviewed_at": card["last_reviewed_at"],
    } for cid, card in best.items()]

    print(f"  sr_concepts로 병합될 개념: {len(rows)}개")
    if dry_run:
        return
    for i in range(0, len(rows), 200):
        db.table("sr_concepts").upsert(rows[i:i + 200], on_conflict="concept_id").execute()
    print("  sr_concepts 반영 완료")


def main(dry_run: bool):
    db = get_client()

    questions = db.table("questions") \
        .select("id, type, chapter, question_data, subject") \
        .is_("subject", "null").execute().data or []
    print(f"대상 문항(subject 미설정): {len(questions)}개")
    if not questions:
        print("이미 마이그레이션된 것으로 보임. 종료.")
        return

    concept_map = extract_concepts_batch(questions)

    concepts_cache: dict[str, str] = {}

    def get_or_create_concept(name: str) -> str | None:
        name = name.strip()
        if not name:
            return None
        if name in concepts_cache:
            return concepts_cache[name]
        existing = db.table("concepts").select("id") \
            .eq("name", name).eq("subject", "교육학").execute().data
        if existing:
            cid = existing[0]["id"]
        elif dry_run:
            cid = f"dry-{name}"
        else:
            cid = db.table("concepts").insert(
                {"name": name, "subject": "교육학"}
            ).execute().data[0]["id"]
        concepts_cache[name] = cid
        return cid

    qc_links: list[tuple[str, str]] = []
    subject_update_ids: list[str] = []
    inactive_ids: list[str] = []

    for q in questions:
        for name in concept_map.get(q["id"], []):
            cid = get_or_create_concept(name)
            if cid:
                qc_links.append((q["id"], cid))
        subject_update_ids.append(q["id"])
        if q["type"] in ("mcq", "matching"):
            inactive_ids.append(q["id"])

    print(f"추출된 고유 개념: {len(concepts_cache)}개 / 문항-개념 연결: {len(qc_links)}건")
    print(f"subject='교육학' 설정 대상: {len(subject_update_ids)}개")
    print(f"active=false(mcq/matching) 대상: {len(inactive_ids)}개")

    if dry_run:
        print("\n[dry-run] 실제 반영 없음. 샘플 5건:")
        for qid, cid in qc_links[:5]:
            print(f"  {qid} -> {cid}")
        migrate_sr_cards(dry_run=True)
        return

    for i in range(0, len(subject_update_ids), BATCH_DB):
        db.table("questions").update({"subject": "교육학"}) \
            .in_("id", subject_update_ids[i:i + BATCH_DB]).execute()

    if qc_links:
        rows = [{"question_id": qid, "concept_id": cid} for qid, cid in qc_links]
        for i in range(0, len(rows), 500):
            db.table("question_concepts").upsert(
                rows[i:i + 500], on_conflict="question_id,concept_id"
            ).execute()

    if inactive_ids:
        for i in range(0, len(inactive_ids), BATCH_DB):
            db.table("questions").update({"active": False}) \
                .in_("id", inactive_ids[i:i + BATCH_DB]).execute()

    print("questions 갱신 완료")
    migrate_sr_cards(dry_run=False)
    print("\n마이그레이션 완료")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
