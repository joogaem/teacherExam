"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  api,
  type LearnArea, type LearnPart, type LearnSession,
  type MCQData, type FillBlankData, type MatchingData, type EssayData,
} from "@/lib/api";
import MCQ from "@/components/quiz/MCQ";
import FillBlank from "@/components/quiz/FillBlank";
import Matching from "@/components/quiz/Matching";
import Essay from "@/components/quiz/Essay";
import KeywordRecall from "@/components/quiz/KeywordRecall";

// 단답형과 서술형이 같은 배지·같은 입력창이라 구분이 안 된다는 피드백 → 색까지 분리 (§9-5)
const TYPE_BADGE: Record<string, { label: string; cls: string }> = {
  mcq: { label: "객관식", cls: "bg-blue-100 text-blue-700" },
  matching: { label: "짝맞추기", cls: "bg-blue-100 text-blue-700" },
  fill_blank: { label: "빈칸", cls: "bg-blue-100 text-blue-700" },
  short_answer: { label: "단답", cls: "bg-teal-100 text-teal-700" },
  essay: { label: "서술형", cls: "bg-indigo-100 text-indigo-700" },
};
const LAST_KEY = "learn_last_area";

type View = "areas" | "parts" | "session";

export default function LearnPage() {
  const [view, setView] = useState<View>("areas");
  const [areas, setAreas] = useState<LearnArea[]>([]);
  const [area, setArea] = useState<string>("");
  const [parts, setParts] = useState<LearnPart[]>([]);
  const [session, setSession] = useState<LearnSession | null>(null);
  const [sessionId, setSessionId] = useState("");
  const [solved, setSolved] = useState<Record<string, boolean>>({}); // 이번 세션에서 푼 것
  const [status, setStatus] = useState<"loading" | "ok" | "error">("loading");

  /* ── 목록 ── */
  const loadAreas = useCallback(() => {
    setStatus("loading");
    api.learn.areas()
      .then(a => { setAreas(a); setStatus("ok"); })
      .catch(() => setStatus("error"));
  }, []);

  useEffect(loadAreas, [loadAreas]);

  const openArea = async (a: LearnArea, autoEnter = true) => {
    setStatus("loading");
    setArea(a.part);
    localStorage.setItem(LAST_KEY, a.key);
    try {
      // 교과교육학은 강의 체계가 없어 중간 목록 없이 바로 세션으로
      if (a.kind === "curriculum") {
        setParts([]);
        await startSession(() => api.learn.curriculum(a.key));
        return;
      }
      const ps = await api.learn.parts(a.key);
      setParts(ps);
      setStatus("ok");
      // §9-2 아침 결정 제로 — 안 끝난 첫 파트로 자동 진입
      const next = ps.find(p => !p.done);
      if (autoEnter && next) await openPart(next.lecture_id);
      else setView("parts");
    } catch {
      setStatus("error");
    }
  };

  const startSession = async (fetcher: () => Promise<LearnSession>) => {
    setStatus("loading");
    try {
      const s = await fetcher();
      const label = s.lecture.lecture_no
        ? `[학습] ${s.lecture.lecture_no}강 ${s.lecture.title}`
        : `[학습] ${s.lecture.title}`;
      const sess = await api.sessions.start({
        chapter: label.slice(0, 120),
        question_ids: s.questions.map(q => q.id),
      });
      setSession(s);
      setSessionId(sess.session_id);
      setSolved({});
      setView("session");
      setStatus("ok");
      window.scrollTo({ top: 0 });
    } catch {
      setStatus("error");
    }
  };

  const openPart = (lectureId: string, stage = 1) =>
    startSession(() => api.learn.session(lectureId, stage));

  const reopenCurrent = (stage?: number) => {
    if (!session) return;
    const id = session.lecture.id;
    return session.lecture.lecture_no
      ? startSession(() => api.learn.session(id, stage ?? session.stage))
      : startSession(() => api.learn.curriculum(id));
  };

  const handleAnswer =
    (questionId: string, mode: "full" | "keyword" = "full") =>
    async (answer: Record<string, unknown>) => {
      const res = await api.sessions.answer({
        session_id: sessionId,
        question_id: questionId,
        user_answer: answer,
        time_spent_sec: 0,
        mode,
      });
      setSolved(s => ({ ...s, [questionId]: res.is_correct !== false }));
      return res;
    };

  /* ── 공통 상태 화면 ── */
  if (status === "error") return (
    <Shell>
      <div className="text-center py-16">
        <p className="text-gray-500 mb-4">불러오지 못했어요.</p>
        <button onClick={loadAreas} className="px-5 py-2 rounded-lg bg-gray-800 text-white text-sm font-semibold">
          다시 시도
        </button>
      </div>
    </Shell>
  );

  if (status === "loading") return (
    <Shell><p className="text-gray-400 text-center py-16">불러오는 중...</p></Shell>
  );

  /* ── 1. 영역 선택 ── */
  if (view === "areas") return (
    <Shell>
      <p className="text-gray-500 text-sm mb-4">고르면 이어서 학습할 곳으로 바로 들어갑니다.</p>
      <div className="space-y-2">
        {areas.map(a => {
          const isCur = a.kind === "curriculum";
          const pct = isCur
            ? (a.total_q ? Math.round((a.answered_q / a.total_q) * 100) : 0)
            : (a.lectures ? Math.round((a.done_lectures / a.lectures) * 100) : 0);
          return (
            <button
              key={a.key}
              onClick={() => openArea(a)}
              className="w-full text-left bg-white rounded-xl p-4 shadow-sm border border-gray-100 hover:border-blue-300"
            >
              <div className="flex justify-between items-baseline mb-2 gap-2">
                <span className="font-semibold text-gray-900">
                  {isCur && (
                    <span className="mr-1.5 px-1.5 py-0.5 rounded bg-purple-100 text-purple-700 text-[11px] align-middle">
                      교과교육
                    </span>
                  )}
                  {a.part}
                </span>
                <span className="text-sm text-gray-400 shrink-0">
                  {isCur ? `${a.total_q}장 중 ${a.answered_q}장` : `${a.lectures}강 중 ${a.done_lectures}강 완료`}
                </span>
              </div>
              <div className="bg-gray-100 rounded-full h-2">
                <div className={`h-2 rounded-full transition-all ${isCur ? "bg-purple-500" : "bg-blue-500"}`}
                     style={{ width: `${pct}%` }} />
              </div>
            </button>
          );
        })}
        {areas.length === 0 && <p className="text-gray-400 text-center py-12">학습할 강의가 없습니다.</p>}
      </div>
    </Shell>
  );

  /* ── 2. 파트(강의) 목록 ── */
  if (view === "parts") return (
    <Shell>
      <div className="flex items-center justify-between mb-4">
        <p className="font-semibold text-gray-800">{area}</p>
        <button onClick={() => setView("areas")} className="text-sm text-gray-500">← 영역 목록</button>
      </div>
      <div className="space-y-2">
        {parts.map(p => (
          <button
            key={p.lecture_id}
            onClick={() => openPart(p.lecture_id)}
            className={`w-full text-left rounded-xl p-4 border shadow-sm hover:border-blue-300 ${
              p.done ? "bg-green-50 border-green-200" : "bg-white border-gray-100"
            }`}
          >
            <div className="flex justify-between items-baseline">
              <span className="font-medium text-gray-900">
                {p.source === "minor" ? "[마이너] " : ""}{p.lecture_no}강 · {p.title.slice(0, 40)}
              </span>
              <span className="text-sm text-gray-400 shrink-0 ml-2">
                {p.done ? "완료" : `${p.answered}/${p.total}`}
              </span>
            </div>
          </button>
        ))}
      </div>
    </Shell>
  );

  /* ── 3. 파트 학습 세션 ── */
  if (!session) return null;
  const qs = session.questions;
  const solvedCount = Object.keys(solved).length;
  const allSolved = solvedCount >= qs.length;
  const rightCount = Object.values(solved).filter(Boolean).length;
  const nextPart = parts.find(p => !p.done && p.lecture_id !== session.lecture.id);
  const isCurriculum = !session.lecture.lecture_no;
  // 1단계에서는 서술형을 키워드 회상으로 낮춰 제시한다 (§9-5)
  const keywordStage = session.stage === 1;

  return (
    <Shell>
      <div className="mb-5">
        <div className="flex justify-between items-center text-sm text-gray-500 mb-2">
          <button onClick={() => { setView(isCurriculum ? "areas" : "parts"); loadAreas(); }}
                  className="text-gray-400">
            ← {isCurriculum ? "과목 목록" : "강의 목록"}
          </button>
          <span>{solvedCount} / {qs.length}</span>
        </div>
        <h2 className="text-lg font-bold text-gray-900">
          {isCurriculum ? session.lecture.title : `${session.lecture.lecture_no}강 · ${session.lecture.title}`}
          {session.stage === 2 && (
            <span className="ml-2 px-2 py-0.5 rounded bg-indigo-600 text-white text-xs align-middle">
              서술 연습
            </span>
          )}
        </h2>
        <div className="bg-gray-200 rounded-full h-2 mt-2">
          <div className="bg-blue-500 h-2 rounded-full transition-all"
               style={{ width: `${(solvedCount / Math.max(qs.length, 1)) * 100}%` }} />
        </div>
      </div>

      <div className="space-y-4">
        {qs.map((q, i) => {
          const d = q.question_data as { explanation?: string; source_text?: string };
          const answered = solved[q.id] !== undefined;
          return (
            <div key={q.id} className="bg-white rounded-2xl shadow-sm p-5 border border-gray-100">
              <div className="flex items-center gap-2 mb-3">
                <span className="font-bold text-gray-400">{i + 1}.</span>
                <span className={`px-2 py-0.5 rounded text-xs font-semibold ${
                  TYPE_BADGE[q.type]?.cls ?? "bg-gray-100 text-gray-600"
                }`}>
                  {TYPE_BADGE[q.type]?.label ?? q.type}
                </span>
                {q.type === "essay" && keywordStage && (
                  <span className="px-2 py-0.5 rounded bg-indigo-50 text-indigo-600 text-xs font-medium">
                    키워드만
                  </span>
                )}
              </div>

              {q.type === "mcq" && <MCQ data={q.question_data as MCQData} onSubmit={handleAnswer(q.id)} />}
              {q.type === "fill_blank" && <FillBlank data={q.question_data as FillBlankData} onSubmit={handleAnswer(q.id)} />}
              {q.type === "matching" && <Matching data={q.question_data as MatchingData} onSubmit={handleAnswer(q.id)} />}
              {q.type === "short_answer" && (
                <Essay data={q.question_data as EssayData} variant="short" onSubmit={handleAnswer(q.id)} />
              )}
              {q.type === "essay" && (
                keywordStage
                  ? <KeywordRecall data={q.question_data as EssayData} onSubmit={handleAnswer(q.id, "keyword")} />
                  : <Essay data={q.question_data as EssayData} onSubmit={handleAnswer(q.id)} />
              )}

              {/* 해설 — mcq는 채점 피드백이 곧 해설이라 중복 표시하지 않음 */}
              {answered && q.type !== "mcq" && d.explanation && (
                <div className="mt-3 p-3 rounded-lg bg-amber-50 border-l-4 border-amber-300 text-sm text-amber-900">
                  <span className="font-semibold">해설 </span>{d.explanation}
                </div>
              )}

              {/* 고시문 원문 — 교과교육 문항은 원문 표현을 토씨까지 요구하므로 답 직후 원문을 붙인다 */}
              {answered && d.source_text && (
                <details className="mt-3" open>
                  <summary className="cursor-pointer text-sm font-semibold text-purple-700">
                    📄 고시문 원문
                  </summary>
                  <pre className="mt-2 p-3 rounded-lg bg-purple-50 border border-purple-200 text-sm text-gray-800 whitespace-pre-wrap font-sans leading-relaxed">
                    {d.source_text}
                  </pre>
                </details>
              )}
            </div>
          );
        })}
      </div>

      {allSolved && (
        <div className="mt-6 bg-white rounded-2xl border-2 border-gray-800 p-6">
          <p className="text-xl font-bold mb-1">이 세트 완료!</p>
          <p className="text-gray-500 mb-4">{qs.length}문제 중 {rightCount}개 맞았어요.</p>
          {/* 서술 연습은 '밀린 것'이 아니라 원할 때 고르는 추가 패스 — 강요하지 않는다 (§0-2) */}
          {session.stage === 1 && session.essay_total > 0 && session.remaining === 0 && (
            <div className="mb-4 p-3 rounded-xl bg-indigo-50 border border-indigo-200">
              <p className="text-sm text-indigo-900 mb-2">
                여기 서술형 {session.essay_total}개는 키워드로만 풀었어요. 문장으로도 써볼래요?
              </p>
              <button onClick={() => reopenCurrent(2)}
                      className="px-4 py-2 rounded-lg bg-indigo-600 text-white font-semibold text-sm">
                ✍️ 문장으로 써보기 →
              </button>
            </div>
          )}
          <div className="flex gap-2 flex-wrap">
            {session.remaining > 0 && (
              <button onClick={() => reopenCurrent()}
                      className="px-5 py-2.5 rounded-xl bg-blue-600 text-white font-semibold text-sm">
                이어서 {session.remaining}문제 →
              </button>
            )}
            {session.remaining === 0 && nextPart && (
              <button onClick={() => openPart(nextPart.lecture_id)}
                      className="px-5 py-2.5 rounded-xl bg-blue-600 text-white font-semibold text-sm">
                다음 강의 ({nextPart.lecture_no}강) →
              </button>
            )}
            <button onClick={() => { setView(isCurriculum ? "areas" : "parts"); loadAreas(); }}
                    className="px-5 py-2.5 rounded-xl border-2 border-gray-200 text-gray-600 font-semibold text-sm">
              {isCurriculum ? "과목 목록" : "강의 목록"}
            </button>
          </div>
        </div>
      )}
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-2xl mx-auto">
        <div className="flex items-center justify-between mb-5">
          <h1 className="text-2xl font-bold">📖 교육학 학습</h1>
          <Link href="/" className="text-sm text-gray-500 hover:text-gray-700">← 홈</Link>
        </div>
        {children}
      </div>
    </main>
  );
}
