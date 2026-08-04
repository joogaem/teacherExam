"""
교과교육학 카드에 고시문 원문(source_text) 붙이기 — PHASE1_SPEC §9 확장

목적: "문제를 풀고 곧바로 고시문 원문을 보며 공부한다"는 학습 흐름을 앱 안에서 완결시킨다.
교과교육 문항은 고시문 표현을 토씨까지 요구하므로(§3-1), 해설보다 **원문 자체**가 중요하다.

원자료: 기출분석/교육과정/별책10_정보과.txt (교육부 고시 제2022-33호 별책10, fitz 추출본)

카드 종류별로 붙이는 원문:
  - 성취기준 카드(코드 연결): 성취기준 원문 + 성취기준 해설(있으면)
  - 내용체계 카드: 그 과목·영역의 내용 체계 블록
  - 교수·학습/평가 카드: 그 과목의 교수·학습 및 평가 블록

실행: python backfill_curriculum_source.py [--dry-run]
멱등성: source_text가 이미 있으면 건너뜀.
"""
import argparse
import re
import sys

from db import get_client
from ingest_curriculum import (
    COURSES, load_lines, course_text,
    extract_content_structure_block, extract_teaching_eval_block,
)

CODE_RE = re.compile(r"^\[(\d+[가-힣]+\d{2}-\d{2})\]$")
MAX_LEN = 1800


def build_source_maps():
    """코드→원문, (과목,영역)→내용체계, 과목→교수학습평가 맵을 만든다."""
    lines = load_lines()
    by_code: dict[str, str] = {}
    by_area: dict[tuple[str, str], str] = {}
    by_course: dict[str, str] = {}

    for course, prefix, start, end, area_map in COURSES:
        text = course_text(lines, start, end)

        # 성취기준 원문 (줄 맨앞 [코드])
        for m in re.finditer(
            rf"^\[({re.escape(prefix)}\d{{2}}-\d{{2}})\]\s*(.*?)(?=\n\[\d|\n•|\n\([가-힣]\)|\n\n|\Z)",
            text, re.MULTILINE | re.DOTALL,
        ):
            by_code[m.group(1)] = " ".join(m.group(2).split())

        # 성취기준 해설 (• [코드] 로 시작하는 불릿)
        for m in re.finditer(
            rf"^•\s*\[({re.escape(prefix)}\d{{2}}-\d{{2}})\]\s*(.*?)(?=\n•|\n\[\d|\n\([가-힣]\)|\n\n|\Z)",
            text, re.MULTILINE | re.DOTALL,
        ):
            code, body = m.group(1), " ".join(m.group(2).split())
            if code in by_code:
                by_code[code] += f"\n\n[성취기준 해설]\n{body}"

        for area_no, area_name in area_map.items():
            blk = extract_content_structure_block(text, area_no, area_name)
            if blk:
                by_area[(course, area_name)] = "\n".join(
                    l for l in blk.splitlines() if l.strip()
                )[:MAX_LEN]

        te = extract_teaching_eval_block(text)
        if te:
            by_course[course] = "\n".join(l for l in te.splitlines() if l.strip())[:MAX_LEN]

    return by_code, by_area, by_course


def course_of_chapter(chapter: str) -> str:
    """questions.chapter('[교육과정] 정보(중학교)') → COURSES의 과목명"""
    return (chapter or "").replace("[교육과정]", "").strip()


def main(dry_run: bool):
    by_code, by_area, by_course = build_source_maps()
    print(f"원문 맵: 성취기준 {len(by_code)}개 / 내용체계 {len(by_area)}개 / 교수학습평가 {len(by_course)}개")

    db = get_client()
    cards = db.table("questions").select("id, chapter, type, question_data") \
        .eq("source", "curriculum").execute().data or []

    # 카드 → 연결 개념명
    # PostgREST 기본 응답 상한(1000행)을 넘으므로 반드시 페이지네이션 (question_concepts 2700행+)
    qc = []
    start = 0
    while True:
        page = db.table("question_concepts").select("question_id, concepts(name)") \
            .range(start, start + 999).execute().data or []
        qc.extend(page)
        if len(page) < 1000:
            break
        start += 1000
    names: dict[str, list[str]] = {}
    for r in qc:
        c = r.get("concepts")
        if c:
            names.setdefault(r["question_id"], []).append(c["name"])

    filled = skipped = missed = 0
    for q in cards:
        data = dict(q.get("question_data") or {})
        if data.get("source_text"):
            skipped += 1
            continue

        course = course_of_chapter(q["chapter"])
        src = None
        for n in names.get(q["id"], []):
            m = CODE_RE.match(n)
            if m and m.group(1) in by_code:
                src = f"[{m.group(1)}] {by_code[m.group(1)]}"
                break
            if n.endswith("-내용체계"):
                # "정보(중학교)-컴퓨팅 시스템-내용체계" → 영역명 추출
                area = n[len(course) + 1:-len("-내용체계")] if n.startswith(course) else None
                if area and (course, area) in by_area:
                    src = by_area[(course, area)]
                    break
            if "교수·학습 및 평가" in n and course in by_course:
                src = by_course[course]
                break

        if not src:
            missed += 1
            continue

        filled += 1
        if dry_run:
            if filled <= 3:
                print(f"\n[{q['type']}] {course}\n  원문: {src[:220]}")
        else:
            data["source_text"] = src
            db.table("questions").update({"question_data": data}).eq("id", q["id"]).execute()

    print(f"\n{'[dry-run] ' if dry_run else ''}원문 {filled}개 {'생성(미저장)' if dry_run else '저장'} "
          f"/ 이미 있음 {skipped} / 매칭 실패 {missed}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    main(p.parse_args().dry_run)
