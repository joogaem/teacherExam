"use client";
import { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { api, type Question, type MCQData, type FillBlankData, type MatchingData, type EssayData } from "@/lib/api";
import MCQ from "@/components/quiz/MCQ";
import FillBlank from "@/components/quiz/FillBlank";
import Matching from "@/components/quiz/Matching";
import Essay from "@/components/quiz/Essay";

const Q_TYPES = [
  { value: "mcq", label: "객관식" },
  { value: "fill_blank", label: "빈칸 완성" },
  { value: "matching", label: "짝맞추기" },
  { value: "essay", label: "서술형" },
];

function QuizPage() {
  const params = useSearchParams();
  const bookId = params.get("bookId") ?? "";

  const [chapters, setChapters] = useState<string[]>([]);
  const [chapter, setChapter] = useState("");
  const [selectedTypes, setSelectedTypes] = useState<string[]>(["mcq"]);
  const [countPerType, setCountPerType] = useState(3);

  const [sessionId, setSessionId] = useState("");
  const [questions, setQuestions] = useState<Question[]>([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [phase, setPhase] = useState<"setup" | "generating" | "quiz" | "done">("setup");
  const [startTime, setStartTime] = useState(0);
  const [score, setScore] = useState({ correct: 0, total: 0 });

  useEffect(() => {
    if (bookId) api.books.chapters(bookId).then(setChapters);
  }, [bookId]);

  const handleStart = async () => {
    if (!chapter) return;
    setPhase("generating");
    try {
      const gen = await api.questions.generate({
        book_id: bookId,
        chapter,
        types: selectedTypes,
        count_per_type: countPerType,
      });
      const sess = await api.sessions.start({
        book_id: bookId,
        chapter,
        question_ids: gen.questions.map((q: Question) => q.id),
      });
      setSessionId(sess.session_id);
      setQuestions(sess.questions);
      setCurrentIdx(0);
      setStartTime(Date.now());
      setPhase("quiz");
    } catch (err) {
      alert("오류: " + String(err));
      setPhase("setup");
    }
  };

  const handleAnswer = async (answer: Record<string, unknown>) => {
    const q = questions[currentIdx];
    const elapsed = Math.round((Date.now() - startTime) / 1000);
    const result = await api.sessions.answer({
      session_id: sessionId,
      question_id: q.id,
      user_answer: answer,
      time_spent_sec: elapsed,
    });
    setScore(s => ({
      correct: s.correct + (result.is_correct ? 1 : 0),
      total: s.total + 1,
    }));
    setStartTime(Date.now());
    return result;
  };

  const handleNext = async () => {
    if (currentIdx + 1 >= questions.length) {
      await api.sessions.complete(sessionId);
      setPhase("done");
    } else {
      setCurrentIdx(i => i + 1);
    }
  };

  const toggleType = (t: string) => {
    setSelectedTypes(prev =>
      prev.includes(t) ? prev.filter(x => x !== t) : [...prev, t]
    );
  };

  // ── Setup ──────────────────────────────────
  if (phase === "setup") return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-xl mx-auto bg-white rounded-2xl shadow-sm p-8">
        <h2 className="text-2xl font-bold mb-6">퀴즈 설정</h2>

        <div className="space-y-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">챕터 선택</label>
            <select
              value={chapter}
              onChange={e => setChapter(e.target.value)}
              className="w-full border rounded-lg px-3 py-2 text-sm"
            >
              <option value="">챕터를 선택하세요</option>
              {chapters.map(c => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">문제 유형</label>
            <div className="flex flex-wrap gap-2">
              {Q_TYPES.map(t => (
                <button
                  key={t.value}
                  onClick={() => toggleType(t.value)}
                  className={`px-4 py-2 rounded-full text-sm font-medium border-2 transition-colors
                    ${selectedTypes.includes(t.value)
                      ? "border-blue-500 bg-blue-50 text-blue-700"
                      : "border-gray-200 text-gray-500"}`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              유형별 문제 수: {countPerType}개
            </label>
            <input
              type="range" min={1} max={5} value={countPerType}
              onChange={e => setCountPerType(Number(e.target.value))}
              className="w-full"
            />
          </div>

          <div className="text-sm text-gray-500">
            총 문제 수: <strong>{selectedTypes.length * countPerType}개</strong>
          </div>

          <button
            onClick={handleStart}
            disabled={!chapter || selectedTypes.length === 0}
            className="w-full py-3 rounded-xl bg-blue-600 text-white font-bold text-lg disabled:opacity-40"
          >
            문제 생성 시작
          </button>
        </div>
      </div>
    </main>
  );

  // ── Generating ─────────────────────────────
  if (phase === "generating") return (
    <main className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="text-center">
        <div className="text-5xl mb-4 animate-bounce">🤖</div>
        <p className="text-xl font-semibold text-gray-700">AI가 문제를 생성하는 중...</p>
        <p className="text-gray-400 mt-1">교재 내용을 분석하고 있어요</p>
      </div>
    </main>
  );

  // ── Done ───────────────────────────────────
  if (phase === "done") return (
    <main className="min-h-screen bg-gray-50 flex items-center justify-center p-8">
      <div className="max-w-md w-full bg-white rounded-2xl shadow-sm p-8 text-center">
        <div className="text-6xl mb-4">🎉</div>
        <h2 className="text-2xl font-bold mb-2">퀴즈 완료!</h2>
        <p className="text-5xl font-bold text-blue-600 my-4">
          {score.correct} / {score.total}
        </p>
        <p className="text-gray-500">
          정답률 {Math.round((score.correct / score.total) * 100)}%
        </p>
        <div className="flex gap-3 mt-8">
          <button
            onClick={() => { setPhase("setup"); setScore({ correct: 0, total: 0 }); }}
            className="flex-1 py-3 rounded-xl bg-blue-600 text-white font-semibold"
          >
            다시 풀기
          </button>
          <a href="/" className="flex-1 py-3 rounded-xl border border-gray-200 text-gray-700 font-semibold text-center">
            홈으로
          </a>
        </div>
      </div>
    </main>
  );

  // ── Quiz ───────────────────────────────────
  const q = questions[currentIdx];
  if (!q) return null;
  const progress = ((currentIdx) / questions.length) * 100;

  return (
    <main className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-2xl mx-auto">
        {/* 상단 진행 표시 */}
        <div className="mb-6">
          <div className="flex justify-between text-sm text-gray-500 mb-2">
            <span>{q.chapter}</span>
            <span>{currentIdx + 1} / {questions.length}</span>
          </div>
          <div className="bg-gray-200 rounded-full h-2">
            <div className="bg-blue-500 h-2 rounded-full transition-all" style={{ width: `${progress}%` }} />
          </div>
        </div>

        {/* 문제 카드 */}
        <div className="bg-white rounded-2xl shadow-sm p-6 mb-4">
          <div className="flex items-center gap-2 mb-4">
            <span className="px-2 py-1 rounded bg-blue-100 text-blue-700 text-xs font-semibold">
              {Q_TYPES.find(t => t.value === q.type)?.label}
            </span>
            <span className="text-xs text-gray-400">난이도 {"⭐".repeat(q.difficulty)}</span>
          </div>

          {q.type === "mcq" && (
            <MCQ data={q.question_data as MCQData} onSubmit={handleAnswer} />
          )}
          {q.type === "fill_blank" && (
            <FillBlank data={q.question_data as FillBlankData} onSubmit={handleAnswer} />
          )}
          {q.type === "matching" && (
            <Matching data={q.question_data as MatchingData} onSubmit={handleAnswer} />
          )}
          {q.type === "essay" && (
            <Essay data={q.question_data as EssayData} onSubmit={handleAnswer} />
          )}
        </div>

        <button
          onClick={handleNext}
          className="w-full py-3 rounded-xl bg-gray-800 text-white font-semibold"
        >
          {currentIdx + 1 >= questions.length ? "결과 보기" : "다음 문제 →"}
        </button>
      </div>
    </main>
  );
}

export default function QuizPageWrapper() {
  return <Suspense><QuizPage /></Suspense>;
}
