"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type ReviewCard, type MCQData, type FillBlankData, type MatchingData, type EssayData, type CumulativeStats } from "@/lib/api";
import MCQ from "@/components/quiz/MCQ";
import FillBlank from "@/components/quiz/FillBlank";
import Matching from "@/components/quiz/Matching";
import Essay from "@/components/quiz/Essay";
import KeywordRecall from "@/components/quiz/KeywordRecall";

// 학습 모드와 같은 배지 체계 — 단답/서술형이 한 큐에 섞여 나오므로 색으로 구분한다 (§9-5)
const TYPE_BADGE: Record<string, { label: string; cls: string }> = {
  mcq: { label: "객관식", cls: "bg-blue-100 text-blue-700" },
  fill_blank: { label: "빈칸", cls: "bg-blue-100 text-blue-700" },
  matching: { label: "짝맞추기", cls: "bg-blue-100 text-blue-700" },
  short_answer: { label: "단답", cls: "bg-teal-100 text-teal-700" },
  essay: { label: "서술형 · 키워드", cls: "bg-indigo-100 text-indigo-700" },
};

export default function ReviewSessionPage() {
  const [phase, setPhase] = useState<"loading" | "session" | "done" | "empty" | "error">("loading");
  const [cards, setCards] = useState<ReviewCard[]>([]);
  const [sessionId, setSessionId] = useState("");
  const [currentIdx, setCurrentIdx] = useState(0);
  const [startTime, setStartTime] = useState(0);
  const [stats, setStats] = useState<CumulativeStats | null>(null);

  const load = () => {
    setPhase("loading");
    const device = window.innerWidth < 768 ? "mobile" : "desktop";
    api.review.today(device).then(async res => {
      if (res.cards.length === 0) {
        setPhase("empty");
        return;
      }
      setCards(res.cards);
      const today = new Date().toISOString().slice(0, 10);
      const sess = await api.sessions.start({
        chapter: `오늘의 복습 ${today}`,
        question_ids: res.cards.map(c => c.question.id),
      });
      setSessionId(sess.session_id);
      setStartTime(Date.now());
      setPhase("session");
    }).catch(() => setPhase("error"));
  };

  useEffect(load, []);

  const handleAnswer = async (answer: Record<string, unknown>) => {
    const q = cards[currentIdx].question;
    const elapsed = Math.round((Date.now() - startTime) / 1000);
    const result = await api.sessions.answer({
      session_id: sessionId,
      question_id: q.id,
      user_answer: answer,
      time_spent_sec: elapsed,
      // 오늘의 복습에서 서술형은 항상 키워드 회상 — 매일 도는 큐를 문장 작성으로 막지 않는다
      mode: q.type === "essay" ? "keyword" : "full",
    });
    setStartTime(Date.now());
    return result;
  };

  const handleNext = async () => {
    if (currentIdx + 1 >= cards.length) {
      await api.sessions.complete(sessionId);
      const s = await api.stats.cumulative().catch(() => null);
      setStats(s);
      setPhase("done");
    } else {
      setCurrentIdx(i => i + 1);
    }
  };

  if (phase === "loading") return (
    <main className="min-h-screen bg-gray-50 flex items-center justify-center">
      <p className="text-gray-400">오늘의 복습을 준비하는 중...</p>
    </main>
  );

  if (phase === "error") return (
    <main className="min-h-screen bg-gray-50 flex items-center justify-center p-6">
      <div className="text-center">
        <p className="text-gray-500 mb-4">불러오지 못했어요.</p>
        <button
          onClick={load}
          className="px-5 py-2 rounded-lg bg-gray-800 text-white text-sm font-semibold"
        >
          다시 시도
        </button>
      </div>
    </main>
  );

  if (phase === "empty") return (
    <main className="min-h-screen bg-gray-50 flex items-center justify-center p-6">
      <div className="text-center">
        <div className="text-5xl mb-4">🎉</div>
        <p className="text-xl font-semibold text-gray-700">오늘 복습할 게 없어요</p>
        <Link href="/" className="mt-6 inline-block px-6 py-2.5 rounded-xl bg-blue-600 text-white font-semibold">
          홈으로
        </Link>
      </div>
    </main>
  );

  if (phase === "done") return (
    <main className="min-h-screen bg-gray-50 flex items-center justify-center p-8">
      <div className="max-w-md w-full bg-white rounded-2xl shadow-sm p-8 text-center">
        <div className="text-6xl mb-4">🎉</div>
        <p className="text-xl font-bold text-gray-900 mb-6">오늘 {cards.length}장 완료</p>
        {stats && (
          <div className="flex justify-center gap-8 mb-8">
            <div>
              <p className="text-2xl font-bold text-blue-600">{stats.total_reviews}</p>
              <p className="text-xs text-gray-400 mt-1">누적 복습</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-green-600">{stats.mastered_concepts}</p>
              <p className="text-xs text-gray-400 mt-1">정복한 개념</p>
            </div>
          </div>
        )}
        <Link href="/" className="block w-full py-3 rounded-xl bg-blue-600 text-white font-semibold">
          홈으로
        </Link>
      </div>
    </main>
  );

  // ── session ──────────────────────────────────
  const card = cards[currentIdx];
  const q = card.question;
  const progress = (currentIdx / cards.length) * 100;

  return (
    <main className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-2xl mx-auto">
        <div className="mb-6">
          <div className="flex justify-between text-sm text-gray-500 mb-2">
            <Link href="/" className="text-gray-400 hover:text-gray-600">← 홈</Link>
            <span>{card.concept_name}</span>
            <span>{currentIdx + 1} / {cards.length}</span>
          </div>
          <div className="bg-gray-200 rounded-full h-2">
            <div className="bg-blue-500 h-2 rounded-full transition-all" style={{ width: `${progress}%` }} />
          </div>
        </div>

        <div key={q.id} className="bg-white rounded-2xl shadow-sm p-6 mb-4">
          <div className="flex items-center gap-2 mb-4">
            <span className={`px-2 py-1 rounded text-xs font-semibold ${
              TYPE_BADGE[q.type]?.cls ?? "bg-gray-100 text-gray-600"
            }`}>
              {TYPE_BADGE[q.type]?.label ?? q.type}
            </span>
            <span className="px-2 py-1 rounded bg-gray-100 text-gray-500 text-xs">{card.subject}</span>
          </div>

          {q.type === "mcq" && <MCQ data={q.question_data as MCQData} onSubmit={handleAnswer} />}
          {q.type === "fill_blank" && <FillBlank data={q.question_data as FillBlankData} onSubmit={handleAnswer} />}
          {q.type === "matching" && <Matching data={q.question_data as MatchingData} onSubmit={handleAnswer} />}
          {q.type === "short_answer" && (
            <Essay data={q.question_data as EssayData} variant="short" onSubmit={handleAnswer} />
          )}
          {q.type === "essay" && (
            <KeywordRecall data={q.question_data as EssayData} onSubmit={handleAnswer} />
          )}
        </div>

        <button
          onClick={handleNext}
          className="w-full py-3 rounded-xl bg-gray-800 text-white font-semibold"
        >
          {currentIdx + 1 >= cards.length ? "완료" : "다음 →"}
        </button>
      </div>
    </main>
  );
}
