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
    complete: (sessionId: string) =>
      fetchAPI(`/sessions/${sessionId}/complete`, { method: "PATCH" }),
  },
  review: {
    queue: (bookId: string) => fetchAPI<Question[]>(`/review/${bookId}`),
  },
  weakness: {
    get: (bookId: string) => fetchAPI<WeaknessRow[]>(`/weakness/${bookId}`),
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
  type: "mcq" | "fill_blank" | "matching" | "essay";
  difficulty: number;
  question_data: MCQData | FillBlankData | MatchingData | EssayData;
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

export interface GenerateRequest {
  book_id: string;
  chapter: string;
  types: string[];
  count_per_type: number;
}

export interface StartSessionRequest {
  book_id: string;
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
  is_correct: boolean;
  score: number;
  feedback: string;
}

export interface WeaknessRow {
  chapter: string;
  type: string;
  total_attempts: number;
  correct_count: number;
  avg_score_pct: number;
}
