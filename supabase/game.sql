-- ════════════════════════════════════════════════════════════
-- 강의 정복 게임 모드 — 추가(additive) 스키마
-- 기존 테이블은 건드리지 않음. Supabase SQL Editor에서 1회 실행.
-- ════════════════════════════════════════════════════════════

-- 강의별 게임 진행도 (강의당 1행, 클리어 기록·별점·최고 기록)
create table if not exists lecture_progress (
  id           uuid primary key default gen_random_uuid(),
  lecture_id   uuid references lectures(id) on delete cascade unique not null,
  cleared      boolean default false,
  stars        int default 0,          -- 1~3 (남은 목숨 기준)
  best_score   int default 0,
  best_combo   int default 0,
  attempts     int default 0,
  card_earned  boolean default false,  -- 학자 카드 보상 (2단계 기능)
  cleared_at   timestamptz,
  updated_at   timestamptz default now()
);

create index if not exists lecture_progress_lecture_idx on lecture_progress (lecture_id);
