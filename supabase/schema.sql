-- pgvector 확장 활성화
create extension if not exists vector;

-- ─────────────────────────────────────────
-- 1. 교재 (books)
-- ─────────────────────────────────────────
create table books (
  id          uuid primary key default gen_random_uuid(),
  title       text not null,
  filename    text not null,
  total_pages int,
  created_at  timestamptz default now()
);

-- ─────────────────────────────────────────
-- 2. RAG 청크 (chunks)
-- ─────────────────────────────────────────
create table chunks (
  id          uuid primary key default gen_random_uuid(),
  book_id     uuid references books(id) on delete cascade,
  chapter     text not null,          -- "PART 2 > Chapter 3"
  section     text,                   -- 세부 절
  content     text not null,
  page_start  int,
  page_end    int,
  embedding   vector(1024),           -- voyage-3 dim
  created_at  timestamptz default now()
);

create index on chunks using ivfflat (embedding vector_cosine_ops) with (lists = 100);
create index on chunks (book_id, chapter);

-- ─────────────────────────────────────────
-- 3. 생성된 문제 (questions)
-- ─────────────────────────────────────────
create table questions (
  id           uuid primary key default gen_random_uuid(),
  book_id      uuid references books(id) on delete cascade,
  chapter      text not null,
  section      text,
  type         text not null check (type in ('mcq','fill_blank','matching','essay')),
  difficulty   int check (difficulty between 1 and 5),
  question_data jsonb not null,        -- 유형별 구조화 데이터
  source_chunk_ids uuid[],
  created_at   timestamptz default now()
);

create index on questions (book_id, chapter, type);

-- ─────────────────────────────────────────
-- 4. 퀴즈 세션 (quiz_sessions)
-- ─────────────────────────────────────────
create table quiz_sessions (
  id              uuid primary key default gen_random_uuid(),
  book_id         uuid references books(id) on delete cascade,
  chapter         text not null,
  question_types  text[],
  total_questions int,
  correct_count   int default 0,
  status          text default 'in_progress' check (status in ('in_progress','completed')),
  started_at      timestamptz default now(),
  completed_at    timestamptz
);

-- ─────────────────────────────────────────
-- 5. 답변 기록 (user_answers)
-- ─────────────────────────────────────────
create table user_answers (
  id              uuid primary key default gen_random_uuid(),
  session_id      uuid references quiz_sessions(id) on delete cascade,
  question_id     uuid references questions(id) on delete cascade,
  user_answer     jsonb not null,
  is_correct      boolean,
  score           numeric(4,2),       -- 서술형 부분점수 (0~1)
  feedback        text,               -- Claude 채점 피드백
  time_spent_sec  int,
  answered_at     timestamptz default now()
);

-- ─────────────────────────────────────────
-- 6. 스페이스드 리피티션 (sr_cards) — SM-2
-- ─────────────────────────────────────────
create table sr_cards (
  id              uuid primary key default gen_random_uuid(),
  question_id     uuid references questions(id) on delete cascade unique,
  ease_factor     numeric(4,2) default 2.5,
  interval_days   int default 1,
  repetition      int default 0,
  next_review_at  timestamptz default now(),
  last_reviewed_at timestamptz
);

create index on sr_cards (next_review_at);

-- ─────────────────────────────────────────
-- 7. 약점 집계 뷰 (weakness_view)
-- ─────────────────────────────────────────
create view weakness_view as
select
  q.book_id,
  q.chapter,
  q.type,
  count(*) as total_attempts,
  sum(case when ua.is_correct then 1 else 0 end) as correct_count,
  round(avg(ua.score) * 100, 1) as avg_score_pct
from user_answers ua
join questions q on ua.question_id = q.id
group by q.book_id, q.chapter, q.type;

-- ─────────────────────────────────────────
-- 8. RAG 유사도 검색 함수
-- ─────────────────────────────────────────
create or replace function match_chunks(
  query_embedding vector(1024),
  target_book_id  uuid,
  target_chapter  text default null,
  match_count     int default 5
)
returns table (
  id        uuid,
  chapter   text,
  section   text,
  content   text,
  page_start int,
  similarity float
)
language sql stable
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

-- ─────────────────────────────────────────
-- 9. 오늘 복습 문제 조회 함수
-- ─────────────────────────────────────────
create or replace function get_due_questions(
  p_book_id uuid,
  p_now     timestamptz,
  p_limit   int default 20
)
returns table (
  id            uuid,
  chapter       text,
  type          text,
  difficulty    int,
  question_data jsonb
)
language sql stable
as $$
  select q.id, q.chapter, q.type, q.difficulty, q.question_data
  from sr_cards sr
  join questions q on sr.question_id = q.id
  where q.book_id = p_book_id
    and sr.next_review_at <= p_now
  order by sr.next_review_at
  limit p_limit;
$$;

-- ─────────────────────────────────────────
-- 10. 세션 정답 수 증가 함수
-- ─────────────────────────────────────────
create or replace function increment_correct_count(session_id uuid)
returns void language sql as $$
  update quiz_sessions
  set correct_count = correct_count + 1
  where id = session_id;
$$;
