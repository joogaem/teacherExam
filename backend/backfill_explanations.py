"""
해설 백필 (1회성) — PHASE1_SPEC §9-4

빈칸(fill_blank)·짝맞추기(matching) 문항에는 explanation이 하나도 없어서
파트별 학습 모드(§9)의 핵심인 "문제 직후 상세 해설"이 성립하지 않는다.
mcq는 이미 explanation 보유, essay는 model_answer로 대체되므로 대상이 아니다.

품질 기준: 정답이 무엇인지가 아니라 **왜 그런지 + 기억에 남는 비유/대비**.
(사용자가 실사용 후 좋다고 평가한 CA 연습지 해설 수준)

실행: python backfill_explanations.py --dry-run   → 생성 결과만 출력
      python backfill_explanations.py             → question_data.explanation에 저장
멱등성: explanation이 이미 있는 문항은 건너뛴다. 중단 후 재실행해도 안전.
"""
import argparse
import sys

sys.stdout.reconfigure(encoding="utf-8")

from db import get_client
from question_gen import claude, MODEL, _parse_json

BATCH = 8
TARGET_TYPES = ("fill_blank", "matching")

PROMPT = """다음은 교육학(중등 임용) 학습용 문제들이다. 각 문제에 붙일 **해설**을 써라.

[해설 작성 규칙]
- 정답을 반복하지 말고, **왜 그 답인지**를 설명한다.
- 가능하면 기억에 남는 **비유나 대비**를 한 줄 넣는다.
  (좋은 예: "버스는 좁은 복도 하나라서 한 번에 한 명만 지나가.")
- 헷갈리기 쉬운 옆 개념이 있으면 **무엇과 구분해야 하는지** 짚는다.
- 2~3문장, 공부하는 사람에게 말하듯 편한 어투("~야", "~해").
- 교재에 없는 사실을 지어내지 말 것. 확실하지 않으면 개념 정의 수준에서만 설명한다.

[문제 목록]
{items}

[출력 형식 — JSON 객체만, 다른 텍스트 없이]
{{"문제id": "해설 내용", ...}}
"""


def describe(q: dict) -> str:
    d = q.get("question_data") or {}
    if q["type"] == "fill_blank":
        return f"(빈칸) {d.get('template','')} / 정답: {', '.join(d.get('answers') or [])}"
    pairs = d.get("pairs") or []
    left, right = d.get("left") or [], d.get("right") or []
    joined = "; ".join(
        f"{left[a]}={right[b]}" for a, b in pairs
        if isinstance(a, int) and isinstance(b, int) and a < len(left) and b < len(right)
    )
    return f"(짝맞추기) {d.get('instruction','')} / 정답 짝: {joined}"


def main(dry_run: bool):
    db = get_client()
    rows = db.table("questions").select("id, type, question_data") \
        .in_("type", list(TARGET_TYPES)).execute().data or []
    targets = [q for q in rows if not (q.get("question_data") or {}).get("explanation")]
    print(f"대상 {len(targets)}개 (전체 {len(rows)}개 중 explanation 없는 것)")
    if not targets:
        print("이미 모두 채워져 있음. 종료.")
        return

    done = 0
    for i in range(0, len(targets), BATCH):
        chunk = targets[i:i + BATCH]
        items = "\n".join(f'{q["id"]}: {describe(q)[:400]}' for q in chunk)
        try:
            msg = claude.messages.create(
                model=MODEL, max_tokens=2048,
                messages=[{"role": "user", "content": PROMPT.format(items=items)}],
            )
            result = _parse_json(msg.content[0].text)
        except Exception as e:
            print(f"  ! 배치 {i}~{i+len(chunk)} 실패: {e}", file=sys.stderr)
            continue
        if not isinstance(result, dict):
            continue

        for q in chunk:
            exp = result.get(q["id"])
            if not exp or not isinstance(exp, str):
                continue
            if dry_run:
                print(f"  [{q['type']}] {describe(q)[:70]}\n      → {exp[:150]}")
            else:
                data = dict(q.get("question_data") or {})
                data["explanation"] = exp.strip()
                db.table("questions").update({"question_data": data}).eq("id", q["id"]).execute()
            done += 1
        print(f"  {min(i+BATCH, len(targets))}/{len(targets)} 처리")

    print(f"\n{'[dry-run] ' if dry_run else ''}해설 {done}개 {'생성(미저장)' if dry_run else '저장'} 완료")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    main(p.parse_args().dry_run)
