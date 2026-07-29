const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function fetchAPI<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export const api = {
  books: {
    list: () => fetchAPI<Book[]>("/books"),
    upload: (file: File, title: string) => {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("title", title);
      return fetch(`${BASE}/books/upload`, { method: "POST", body: fd }).then(r => r.json());
    },
    chapters: (bookId: string) => fetchAPI<string[]>(`/books/${bookId}/chapters`),
    lectures: (bookId: string) => fetchAPI<Lecture[]>(`/books/${bookId}/lectures`),
  },
  lectures: {
    questions: (lectureId: string) => fetchAPI<Question[]>(`/lectures/${lectureId}/questions`),
    prebuild: (lectureId: string, body?: { types?: string[]; count_per_type?: number }) =>
      fetchAPI<{ created: number; questions: Question[] }>(`/lectures/${lectureId}/prebuild`, {
        method: "POST",
        body: JSON.stringify(body ?? {}),
      }),
  },
  questions: {
    generate: (body: GenerateRequest) =>
      fetchAPI<{ questions: Question[] }>("/questions/generate", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    list: (bookId: string, chapter?: string, type?: string) => {
      const params = new URLSearchParams({ book_id: bookId });
      if (chapter) params.set("chapter", chapter);
      if (type) params.set("q_type", type);
      return fetchAPI<Question[]>(`/questions?${params}`);
    },
  },
  sessions: {
    start: (body: StartSessionRequest) =>
      fetchAPI<{ session_id: string; questions: Question[] }>("/sessions", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    answer: (body: AnswerRequest) =>
      fetchAPI<AnswerResult>("/sessions/answer", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    selfGrade: (answer_id: string, verdict: "ok" | "partial" | "no") =>
      fetchAPI<{ ok: boolean; score?: number; is_correct?: boolean }>("/sessions/self-grade", {
        method: "POST",
        body: JSON.stringify({ answer_id, verdict }),
      }),
    complete: (sessionId: string) =>
      fetchAPI(`/sessions/${sessionId}/complete`, { method: "PATCH" }),
  },
  learn: {
    areas: () => fetchAPI<LearnArea[]>("/learn/areas"),
    parts: (part: string) => fetchAPI<LearnPart[]>(`/learn/areas/${encodeURIComponent(part)}/parts`),
    session: (lectureId: string) => fetchAPI<LearnSession>(`/learn/parts/${lectureId}`),
  },
  game: {
    progress: (bookId: string) => fetchAPI<GameLecture[]>(`/game/progress?book_id=${bookId}`),
    start: (lectureId: string) =>
      fetchAPI<{ session_id: string; questions: Question[] }>(
        `/game/lectures/${lectureId}/start`, { method: "POST" }),
    record: (lectureId: string, body: GameRecordRequest) =>
      fetchAPI<LectureProgress>(`/game/lectures/${lectureId}/record`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
  },
  review: {
    queue: (bookId: string) => fetchAPI<Question[]>(`/review/${bookId}`),
    today: (device: "mobile" | "desktop") =>
      fetchAPI<{ cards: ReviewCard[] }>(`/review/today?device=${device}`),
    amnesty: () => fetchAPI<{ redistributed: number }>("/review/amnesty", { method: "POST" }),
  },
  weakness: {
    get: () => fetchAPI<WeaknessRow[]>("/weakness"),
  },
  stats: {
    cumulative: () => fetchAPI<CumulativeStats>("/stats/cumulative"),
  },
  inbox: {
    list: (params: { q_type?: string; limit?: number; offset?: number }) => {
      const sp = new URLSearchParams();
      if (params.q_type) sp.set("q_type", params.q_type);
      sp.set("limit", String(params.limit ?? 50));
      sp.set("offset", String(params.offset ?? 0));
      return fetchAPI<{ items: Question[]; total: number }>(`/inbox?${sp}`);
    },
    approve: (question_ids: string[]) =>
      fetchAPI<{ approved: number }>("/inbox/approve", {
        method: "POST",
        body: JSON.stringify({ question_ids }),
      }),
    reject: (question_ids: string[]) =>
      fetchAPI<{ rejected: number }>("/inbox/reject", {
        method: "POST",
        body: JSON.stringify({ question_ids }),
      }),
  },
};

// ── 타입 정의 ──────────────────────────────────────────────────

export interface Book {
  id: string;
  title: string;
  filename: string;
  total_pages: number;
  created_at: string;
}

export interface Question {
  id: string;
  book_id: string;
  chapter: string;
  type: "mcq" | "fill_blank" | "matching" | "essay" | "short_answer";
  difficulty: number;
  question_data: MCQData | FillBlankData | MatchingData | EssayData;
  desk_only?: boolean;
  source?: "generated" | "past_exam" | "curriculum" | "manual";
}

export interface MCQData {
  stem: string;
  options: string[];
  answer: number;
  explanation: string;
}

export interface FillBlankData {
  template: string;
  answers: string[];
  hints: string[];
}

export interface MatchingData {
  instruction: string;
  left: string[];
  right: string[];
  pairs: [number, number][];
}

export interface EssayData {
  stem: string;
  model_answer: string;
  key_concepts: string[];
  rubric: string;
}

export interface Lecture {
  id: string;
  book_id: string;
  source: "main" | "minor";
  lecture_no: number;
  week: string | null;
  part: string | null;
  title: string;
  printed_page_start: number | null;
  printed_page_end: number | null;
  pdf_page_start: number | null;
  pdf_page_end: number | null;
}

export interface GenerateRequest {
  book_id: string;
  chapter?: string;
  lecture_id?: string;
  types: string[];
  count_per_type: number;
}

export interface StartSessionRequest {
  book_id?: string;
  chapter: string;
  question_ids: string[];
}

export interface AnswerRequest {
  session_id: string;
  question_id: string;
  user_answer: Record<string, unknown>;
  time_spent_sec: number;
}

export interface AnswerResult {
  is_correct: boolean | null;
  score: number | null;
  feedback: string;
  // AI 채점 불가 시(크레딧 소진 등) 자가 채점으로 전환하기 위한 필드
  needs_self_grade?: boolean;
  answer_id?: string;
  model_answer?: string;
  key_concepts?: string[];
}

export interface LearnArea {
  part: string;
  lectures: number;
  done_lectures: number;
  total_q: number;
  answered_q: number;
}

export interface LearnPart {
  lecture_id: string;
  lecture_no: number;
  title: string;
  source: string;
  total: number;
  answered: number;
  done: boolean;
}

export interface LearnSession {
  lecture: { id: string; lecture_no: number; title: string; part: string | null };
  questions: Question[];
  answered: Record<string, { id: string; is_correct: boolean | null; score: number | null; feedback: string }>;
  remaining: number;
  lecture_total: number;
  lecture_answered: number;
}

export interface LectureProgress {
  lecture_id: string;
  cleared: boolean;
  stars: number;
  best_score: number;
  best_combo: number;
  attempts: number;
}

export interface GameLecture extends Lecture {
  progress: LectureProgress | null;
}

export interface GameRecordRequest {
  cleared: boolean;
  score: number;
  stars: number;
  max_combo: number;
}

export interface WeaknessRow {
  concept_id: string;
  name: string;
  subject: string;
  total_attempts: number;
  correct_count: number;
  avg_score_pct: number;
  avg_score_pct_30d: number | null;
  missing_count: number;
  misconception_count: number;
}

export interface ReviewCard {
  concept_id: string;
  concept_name: string;
  subject: string;
  question: Question;
}

export interface CumulativeStats {
  total_reviews: number;
  mastered_concepts: number;
  by_subject: Record<string, number>;
}
