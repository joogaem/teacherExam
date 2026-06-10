"""
커리큘럼(설보연 교육학) → lectures 테이블 seed.
사용법: python seed_lectures.py
- 본강 1~48 → 1권, 49~ → 2권, 마이너특강 → 2권
- 페이지는 교재 인쇄페이지 → PDF페이지 앵커 보간으로 보정
- 재실행 시 기존 lectures 전부 지우고 다시 넣음(멱등)
"""
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from db import get_client

# ── 주신 커리큘럼 원본 ────────────────────────────────────────────
CURRICULUM = r"""
1강  오리엔테이션1
2강  오리엔테이션2 - 합격공부법
3강  교육학 TREE & 교육의 이해 조직화 p.16~19
4강  교육의 목적 및 교육요소~교육의 여러가지 유형 p.21~59
5강  PART 2 교육과정_조직화 개념 TREE(1) (P.68~70)
6강  PART 2 교육과정_조직화 개념 TREE(2) (P.70~81)
7강  CHAPTER 1 교육과정의 개념과 유형 (P.82~93)
8강  CHAPTER 2 교육과정의 관점_01. 교과중심 교육과정 (P.94~99)
9강  Chapter 02 <02> 경험중심 교육과정 (p100-105)
10강  Chapter 02 <03>학문중심 교육과정~<05>역량중심 교육과정 (p.106-118)
11강  Chapter 03 <01>교육과정 설계의 일반 원리(1) (p.119-126)
12강  Chapter 03 <01>교육과정 설계의 일반 원리(2) (p.126-128)
13강  CHAPTER 3 교육과정 설계의 원리_02. 교육과정 설계의 유형 (P.129-138)
14강  CHAPTER 3 교육과정 설계의 원리_03. 교육과정 통합 (P.139-146)
15강  CHAPTER 4 교육과정 개발 및 설계 모형_01. 합리적-선형적 개발모형:타일러 ~ 02. 단원 개발모형:타바 (P.147-157)
16강  CHAPTER 4 교육과정 개발 및 설계 모형_03. 자연주의적 개발모형:워커 ~ 04. 학교중심 교육과정 개발모형:스킬벡 (P.157-163)
17강  [보강] CHAPTER 4 교육과정 개발 및 설계 모형_05. 예술적 교육과정 개발모형:아이즈너 ~ 06. 교육과정의 실존적 재개념화:파이너(1) (P.163-171)
18강  [보강] CHAPTER 4 교육과정 개발 및 설계 모형_06. 교육과정의 실존적 재개념화:파이너(2) ~ 09. 이해중심 교육과정 설계모형:위긴스와 맥타이 (P.171-191)
19강  [보강] CHAPTER 5 교육과정의 실행과 최근 동향 ~ CHAPTER 6 우리나라 교육과정 (P.202- 228)
20강  PART 03 교육방법 및 공학 조직화 개념 TREE(1)(p.g276-280)
21강  PART 03 교육방법 및 공학 조직화 개념 TREE(2)~Chapter01 <02>교육공학의 이론적 기초 중 교수학습의 이해(p.g281-293)
22강  PART 03 Chapter01 <02>교육공학의 이론적 기초 중 학습자중심 수업의 이론적 배경 ~ Chapter02 <01>교수체제설계의 기초 중 수업목표 설정(p.g294-313)
23강  PART 03 Chapter02 <01>교수체제설계의 기초 중 학습과제분석~<02>교수체제 설계모형 중 ADDIE 모형(p.g314-318)
24강  CHAPTER 2 교수설계 모형과 이론_02. 교수체제 설계모형(2) ~ 03. 교수설계 이론과 전략:객관주의1(1) (P.318-326)
25강  CHAPTER 2 교수설계 모형과 이론_03. 교수설계 이론과 전략:객관주의1(2) (P.326-335)
26강  CHAPTER 2 교수설계 모형과 이론_03. 교수설계 이론과 전략:객관주의1(3) ~ 04. 교수설계 이론과 전략:객관주의2(1) (P.335-344)
27강  CHAPTER 2 교수설계 모형과 이론_04. 교수설계 이론과 전략:객관주의2(2) (P.344-351)
28강  [보강] CHAPTER 2 교수설계 모형과 이론_05. 교수설계 이론과 전략:구성주의(1) (P.352-358)
29강  [보강] CHAPTER 2 교수설계 모형과 이론_05. 교수설계 이론과 전략:구성주의(2) (P.359-362)
30강  [보강] CHAPTER 2 교수설계 모형과 이론_05. 교수설계 이론과 전략:구성주의(3) (P.362-371)
31강  Chapter 03. 교수방법과 교수매체_01. 전통적 교수법: (4) 개별화 교수 (p.g 374-379)
32강  Chapter 03. 교수방법과 교수매체_01. 전통적 교수법: (5) 토의법~(6) 자기주도학습 (p.g 379-385)
33강  Chapter 03. 교수방법과 교수매체_01. 전통적 교수법: (7)협동학습~다양한 협동학습 유형: 7. 슬래빈 외의 팀 보조 개별학습 (p.g 385-390)
34강  (7) 협동학습 中 다양한 협동학습 유형: 7. 슬래빈 외의 팀 보조 개별학습~03. 테크놀로지 활용 수업: (9)인공지능 기반 교육(p.g 390-415)
35강  PART 3 교육방법 및 공학_조직화 개념 TREE & PART 4 교육평가_조직화 개념 TREE(1) (P.278-287, P.424-425)
36강  PART 4 교육평가_조직화 개념 TREE(2) ~ CHAPTER 1 교육평가의 이해_01. 교육평가의 개념 (P.426-439)
37강  CHAPTER 1 교육평가의 이해_02. 평가의 개념에 따른 분류 ~ 04. 교육평가의 절차 (P.440-449)
38강  CHAPTER 2 교육평가의 모형 (P.450-461)
39강  설보연 교육학 - 서·결론 자동화 특강
40강  Chapter 03 교육평가의 유형_<01> 평가 기준에 따른 분류_1. 규준지향평가~3. 성취평가제 (p.g 464-475)
41강  Chapter 03 교육평가의 유형_<02> 평가 시기에 따른 분류_1. 진단평가~3. 총괄평가(p.g 475-487)
42강  Chapter 03 교육평가의 유형_<03> 대안적 평가_1. 역동적 평가~3. 성장지향평가(p.g 488-493)
43강  Chapter 03 교육평가의 유형_<03> 대안적 평가_4. 학생 참여형 평가-자기평가 및 동료평가 ~<04> 과정중심 평가_2. 과정중심 평가 (p.g 494-501)
44강  CHAPTER 3 교육평가의 유형_04. 과정중심 평가_3. 수행평가 (P.502-509)
45강  CHAPTER 3 교육평가의 유형_04. 과정중심 평가_4. 루브릭 ~ 06. 평가방법에 따른 분류 (P.510-527)
46강  CHAPTER 4 교육평가의 실제_01. 평가문항의 제작 ~ 02. 평가 양호도_1. 타당도(1) (P.533-543)
47강  CHAPTER 4 교육평가의 실제_02. 평가 양호도_1. 타당도(2) (P.543-545)
48강  [보강] CHAPTER 4 교육평가의 실제_02. 평가 양호도_2. 신뢰도 ~ PART 4 교육평가_조직화 개념 TREE (P.546-554, 424-434)
49강  [보강] PART 6 교육행정_조직화 개념 TREE (P.16-27)
50강  [보강] CHAPTER 1 교육행정의 이해_01.개념 및 원리 ~ 02. 교육행정 이론의 발달_4. 체제론적 관점(1) (P.28-48)
51강  Chapter 01 교육행정의 이해_<02> 교육행정 이론의 발달_4. 체제론적 관점 (p.g 50-54)
52강  Chapter 02 조직론_<01> 조직 이해의 기초_1. 조직의 개념 및 특징~<03> 학교조직의 특징_1. 개방된 사회체제로서의 학교 (p.g 57-68)
53강  Chapter 02 조직론_<03> 학교조직의 특징_2. 전문적 관료제로서의 학교~7. 학습조직으로서의 학교 (p.g 68-75)
54강  Chapter 02 조직론_<04> 조직풍토론_1. 리커트의 관리체제 유형~<05> 조직문화론_조직문화론 종합(표) (p.g 76-88)
55강  CHAPTER 2 조직론_06. 조직갈등론 ~ 07. 교육조직 관리기법 (P.89-100)
56강  CHAPTER 3 동기이론_01. 동기이론의 기초 ~ 02. 동기의 내용이론 (P.101-110)
57강  CHAPTER 3 동기이론_03. 동기의 과정이론 ~ CHAPTER 4 지도성이론_03. 지도성 행위론 (P.111-127)
58강  CHAPTER 4 지도성이론_04. 상황적 지도성이론 ~ 05. 대안적 지도성이론_2. 변혁적 지도성 (P.128-138)
59강  Chapter 04 지도성이론_<05> 대안적 지도성이론_3. 수업지도성~5. 문화적 지도성(p.g 138-143)
60강  Chapter 04 지도성이론_<05> 대안적 지도성이론_6. 만즈와 심스의 초우량 지도성(슈퍼리더십)~Chapter 05 정책론_<01> 의사소통_4. 의사소통의 장애 요인 및 개선 방안(p.g 144-163)
61강  Chapter 05 정책론_<02> 의사결정_2. 의사결정의 네 가지 관점~4. 의사결정 참여모형(p.g 165-175)
62강  Chapter 05 정책론_<03> 교육기획론_1. 교육기획(교육계획)의 개념 및 유형~Chapter 07 장학론_<02> 장학의 유형 및 형태_1. 장학의 유형(p.g 176-210)
63강  Chapter 07 장학론_<02> 장학의 유형 및 형태_2. 실시 주체에 따른 구분~Chapter 10 학교·학급경영(p.g 211-259)
64강  PART 06 교육행정 조직화 개념 TREE & PART 07 교육심리 조직화 개념 TREE(p.g 16-27, 284-295)
65강  Chapter 01 학습자의 발달_<01> 발달에 대한 이해~<02> 인지발달(p.g 298-314)
66강  Chapter 01 학습자의 발달_<03> 정의적 발달_1. 성격,정체성,자아개념의 발달(p.g 314-323)
67강  PART 7 교육심리_Chapter 01 학습자의 발달_<03> 정의적 발달_2. 사회성 발달~3. 도덕성 발달 中 콜버그의 도덕성 발달이론(p.g 324-335)
68강  Chapter 01 학습자의 발달_<03> 정의적 발달_3. 도덕성 발달 中 레스트의 도덕성 이론~Chapter 02 학습자의 인지적 특성_<01> 지능_2. 지능이론(p.g 335-353)
69강  Chapter 02 학습자의 인지적 특성_<01> 지능_3. 지능검사~<03> 영재성_2. 영재교육(p.g 353-366)
70강  Chapter 02 학습자의 인지적 특성_<04> 학습양식_1. 위트킨의 장독립형과 장의존형 ~ Chapter 03 학습자의 정의적 특성_<02> 동기이론_6. 기대 X 가치이론(p.g 366-388)
71강  CHAPTER 3 학습자의 정의적 특성_02. 동기이론_7. 와이너의 귀인이론 ~ 10. 드웩의 능력에 대한 견해 (P.388-395)
72강  CHAPTER 3 학습자의 정의적 특성_02. 동기이론_11. 학습된 무기력 ~ CHAPTER 4 학습의 이해_01. 행동주의 학습이론 (P.396-418)
73강  CHAPTER 4 학습의 이해_02. 사회인지 학습이론 ~ 03. 인지주의 학습이론_2. 앳킨슨과 쉬프린의 정보처리이론 (P.419-429)
74강  CHAPTER 4 학습의 이해_03. 인지주의 학습이론_3. 망각 ~ 05. 구성주의 (P.429-440)
75강  SUCCEED 2월 합격 모의고사 해설
76강  SUCCEED 2월 합격 모의고사 Q&A
"""

MINOR = r"""
1강  [마이너특강] PART 8 교육사회학_조직화 개념 TREE (P.448-457)
2강  [마이너특강] CHAPTER 1 교육사회학 이론_01. 기능이론 ~ 03. 신교육사회학_2. 신교육사회학의 관점 (P.460-480)
3강  [마이너특강] CHAPTER 1 교육사회학 이론_03. 신교육사회학_3. 주요 이론 ~ 04. 새로운 이론의 등장 (P.480-490)
4강  [마이너특강] CHAPTER 2 교육과 학력상승 ~ CHAPTER 5 교육과 비행,문화 (P.492-547)
5강  [마이너파트] PART 8 교육사회학_조직화 개념 TREE & PART 9 생활지도 및 상담_조직화 개념 TREE ~ CHAPTER 1 생활지도 (P.448-457, P.554-604)
6강  [마이너파트] CHAPTER 2 학교상담과 상담이론 (P.606-641)
7강  [마이너파트] PART 10 교육사 및 교육철학 (P.652-737)
"""

# ── 교재페이지 → PDF페이지 앵커 (계측값) ─────────────────────────
ANCHORS = {
    "book1.pdf": [(16, 17), (68, 70), (276, 281), (424, 430)],
    "book2.pdf": [(16, 16), (284, 281), (448, 448), (554, 554), (652, 652)],
}

# ── 영역(PART) 경계 — UI 그룹핑/표시용 ───────────────────────────
AREAS = {
    "book1.pdf": [(16, "PART1 교육의 이해"), (67, "PART2 교육과정"),
                  (276, "PART3 교육방법 및 공학"), (424, "PART4 교육평가")],
    "book2.pdf": [(16, "PART6 교육행정"), (281, "PART7 교육심리"),
                  (448, "PART8 교육사회학"), (554, "PART9 생활지도 및 상담"),
                  (652, "PART10 교육사 및 교육철학")],
}


def printed_to_pdf(filename: str, p: int) -> int:
    a = ANCHORS[filename]
    if p <= a[0][0]:
        (x0, y0), (x1, y1) = a[0], a[1]
    elif p >= a[-1][0]:
        (x0, y0), (x1, y1) = a[-2], a[-1]
    else:
        for i in range(len(a) - 1):
            if a[i][0] <= p <= a[i + 1][0]:
                (x0, y0), (x1, y1) = a[i], a[i + 1]
                break
    return round(y0 + (y1 - y0) * (p - x0) / (x1 - x0))


def area_of(filename: str, printed_start: int) -> str:
    label = ""
    for thr, name in AREAS[filename]:
        if printed_start >= thr:
            label = name
    return label


PAGE_RE = re.compile(r"[pP]\s*\.?\s*g?\s*\.?\s*(\d{2,3})(?:\s*[~\-]\s*(\d{2,3}))?")


def parse_pages(title: str):
    """제목의 페이지 인용(p.16~19, (P.68~70), (p.g276-280) 등)에서 min/max 추출."""
    nums = []
    for a, b in PAGE_RE.findall(title):
        nums.append(int(a))
        if b:
            nums.append(int(b))
    nums = [n for n in nums if 10 <= n <= 800]
    if not nums:
        return None, None
    return min(nums), max(nums)


def build_rows(text: str, source: str, book_for):
    rows = []
    for line in text.strip().splitlines():
        line = line.strip()
        m = re.match(r"(\d+)강\s+(.+)", line)
        if not m:
            continue
        no = int(m.group(1))
        title = m.group(2).strip()
        p_lo, p_hi = parse_pages(title)
        if p_lo is None:
            continue  # 페이지 없는 강(오리엔테이션/특강/모의고사)은 제외
        fn = book_for(source, no)
        pdf_lo = printed_to_pdf(fn, p_lo)
        pdf_hi = printed_to_pdf(fn, p_hi)
        rows.append({
            "filename": fn,
            "source": source,
            "lecture_no": no,
            "part": area_of(fn, p_lo),
            "title": title,
            "printed_page_start": p_lo,
            "printed_page_end": p_hi,
            "pdf_page_start": pdf_lo,
            "pdf_page_end": pdf_hi,
        })
    return rows


def main():
    db = get_client()

    # 책 매핑 (청크 있는 것만)
    books = db.table("books").select("*").execute().data
    by_file = {}
    for b in books:
        cnt = db.table("chunks").select("id", count="exact").eq("book_id", b["id"]).execute().count
        if cnt and b["filename"] not in by_file:
            by_file[b["filename"]] = b["id"]
    print("책 매핑:", {k: v[:8] for k, v in by_file.items()})

    def book_for(source, no):
        if source == "minor":
            return "book2.pdf"
        return "book1.pdf" if no <= 48 else "book2.pdf"

    rows = build_rows(CURRICULUM, "main", book_for) + build_rows(MINOR, "minor", book_for)

    # book_id 주입
    for r in rows:
        r["book_id"] = by_file[r.pop("filename")]

    # 멱등: 기존 강의 삭제 후 재삽입
    db.table("lectures").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
    db.table("lectures").insert(rows).execute()

    print(f"\n[완료] 강의 {len(rows)}개 삽입")
    for r in rows[:5] + rows[-3:]:
        print(f"  {r['source']:5} {r['lecture_no']:>2}강 | {r['part'][:14]:<14} "
              f"| 교재{r['printed_page_start']}-{r['printed_page_end']} "
              f"→ PDF{r['pdf_page_start']}-{r['pdf_page_end']} | {r['title'][:40]}")


if __name__ == "__main__":
    main()
