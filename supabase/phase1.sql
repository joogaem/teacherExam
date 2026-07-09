-- ════════════════════════════════════════════════════════════
-- Phase 1 — 기출 문제은행 · 교과교육학 · 개념 단위 SR — 추가(additive) 스키마
-- 기존 테이블은 건드리지 않음(컬럼 추가만). Supabase SQL Editor에서 1회 실행.
-- 상세 스펙: study-app/docs/PHASE1_SPEC.md
-- ════════════════════════════════════════════════════════════

-- 1. questions 컬럼 추가 (§1-1)
alter table questions add column if not exists source text not null default 'generated';
alter table questions add column if not exists exam_year int;
alter table questions add column if not exists paper text;              -- 'A' / 'B' / 'edu'
alter table questions add column if not exists subject text;
alter table questions add column if not exists points int;
alter table questions add column if not exists image_urls text[] default '{}';
alter table questions add column if not exists desk_only boolean default false;
alter table questions add column if not exists active boolean default true;
alter table questions add column if not exists answer_verified boolean default false;

-- type CHECK에 'short_answer' 추가 (기존 제약 교체)
alter table questions drop constraint if exists questions_type_check;
alter table questions add constraint questions_type_check
  check (type in ('mcq','fill_blank','matching','essay','short_answer'));

create index if not exists questions_source_idx on questions (source, subject);
create index if not exists questions_active_idx on questions (active) where active;

-- 2. concepts — SR의 새 단위 (§1-2)
create table if not exists concepts (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  subject     text not null,     -- §1-4 enum (앱 레벨 검증)
  unit        text,
  summary     text,
  source_ref  text,
  exam_years  int[] default '{}',
  stage       int default 2,     -- 교육학 사다리 단계(§5). 전공은 항상 2 취급
  created_at  timestamptz default now(),
  unique (name, subject)
);

create index if not exists concepts_subject_idx on concepts (subject);

-- 3. question_concepts — 다대다 (§1-3)
create table if not exists question_concepts (
  question_id uuid references questions(id) on delete cascade,
  concept_id  uuid references concepts(id) on delete cascade,
  primary key (question_id, concept_id)
);

create index if not exists question_concepts_concept_idx on question_concepts (concept_id);

-- 4. sr_concepts — 개념 단위 SM-2, sr_cards(문항 단위)를 대체 (§1-5)
create table if not exists sr_concepts (
  id               uuid primary key default gen_random_uuid(),
  concept_id       uuid references concepts(id) on delete cascade unique,
  ease_factor      numeric(4,2) default 2.5,
  interval_days    int default 1,
  repetition       int default 0,
  next_review_at   timestamptz default now(),
  last_reviewed_at timestamptz
);

create index if not exists sr_concepts_due_idx on sr_concepts (next_review_at);

-- 5. user_answers.concept_results (§1-6)
alter table user_answers add column if not exists concept_results jsonb;

-- 6. weakness_view 재정의 — 개념 단위 (§1-7)
drop view if exists weakness_view;
create view weakness_view as
select
  c.id as concept_id,
  c.name,
  c.subject,
  count(*) as total_attempts,
  sum(case when ua.is_correct then 1 else 0 end) as correct_count,
  round(avg(ua.score) * 100, 1) as avg_score_pct,
  round(avg(ua.score) filter (
    where ua.answered_at >= now() - interval '30 days'
  ) * 100, 1) as avg_score_pct_30d,
  sum(case when qc2.verdict = 'missing' then 1 else 0 end) as missing_count,
  sum(case when qc2.verdict = 'misconception' then 1 else 0 end) as misconception_count
from concepts c
join question_concepts qcx on qcx.concept_id = c.id
join user_answers ua on ua.question_id = qcx.question_id
left join lateral (
  select (elem->>'verdict') as verdict
  from jsonb_array_elements(coalesce(ua.concept_results, '[]'::jsonb)) as elem
  where (elem->>'concept_id')::uuid = c.id
     or (elem->>'name') = c.name
) qc2 on true
group by c.id, c.name, c.subject
order by avg_score_pct_30d nulls first, avg_score_pct nulls first;
