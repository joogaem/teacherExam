-- ════════════════════════════════════════════════════════════
-- 강의별 문제풀기 기능 — 추가(additive) 스키마
-- 기존 테이블은 건드리지 않음. Supabase SQL Editor에서 1회 실행.
-- ════════════════════════════════════════════════════════════

-- 1. 강의 테이블 (커리큘럼)
create table if not exists lectures (
  id                 uuid primary key default gen_random_uuid(),
  book_id            uuid references books(id) on delete cascade,
  source             text default 'main',     -- 'main'(본강) | 'minor'(마이너특강)
  lecture_no         int,                      -- 강 번호
  week               text,                     -- 주차 라벨 (예: "1-1주차")
  part               text,                     -- PART/영역 (예: "PART 02 교육과정")
  title              text not null,            -- 강의 제목
  printed_page_start int,                       -- 교재 인쇄 페이지
  printed_page_end   int,
  pdf_page_start     int,                       -- 보정된 PDF 페이지
  pdf_page_end       int,
  created_at         timestamptz default now()
);

create index if not exists lectures_book_idx on lectures (book_id, source, lecture_no);

-- 2. 문제에 강의 태그 추가 (문제은행을 강의별로 조회/저장)
alter table questions add column if not exists lecture_id uuid references lectures(id) on delete set null;
create index if not exists questions_lecture_idx on questions (lecture_id);

-- 3. 강의용 벡터검색 함수 — 페이지 윈도우로 좁힌 뒤 유사도 정렬
--    청크 그룹 [page_start,page_end] 가 [page_lo,page_hi] 와 겹치면 후보
--    ※ ivfflat 근사검색은 book_id 필터와 겹치면 recall 구멍(0건)이 생김.
--      enable_indexscan=off 로 인덱스를 끄고 정밀검색(청크가 적어 성능 문제 없음).
create or replace function match_chunks_pages(
  query_embedding vector(1024),
  target_book_id  uuid,
  page_lo         int,
  page_hi         int,
  match_count     int default 8
)
returns table (
  id         uuid,
  chapter    text,
  content    text,
  page_start int,
  page_end   int,
  similarity float
)
language sql stable
set enable_indexscan = off
set enable_indexonlyscan = off
as $$
  select
    c.id, c.chapter, c.content, c.page_start, c.page_end,
    1 - (c.embedding <=> query_embedding) as similarity
  from chunks c
  where c.book_id = target_book_id
    and c.page_end   >= page_lo
    and c.page_start <= page_hi
  order by c.embedding <=> query_embedding
  limit match_count;
$$;

-- 4. 기존 챕터 검색 함수도 동일한 recall 구멍이 있어 정밀검색으로 교체(시그니처 동일).
create or replace function match_chunks(
  query_embedding vector(1024),
  target_book_id  uuid,
  target_chapter  text default null,
  match_count     int default 5
)
returns table (
  id         uuid,
  chapter    text,
  section    text,
  content    text,
  page_start int,
  similarity float
)
language sql stable
set enable_indexscan = off
set enable_indexonlyscan = off
as $$
  select
    c.id, c.chapter, c.section, c.content, c.page_start,
    1 - (c.embedding <=> query_embedding) as similarity
  from chunks c
  where c.book_id = target_book_id
    and (target_chapter is null or c.chapter = target_chapter)
  order by c.embedding <=> query_embedding
  limit match_count;
$$;
