"use client";
import { useState, useEffect, useRef, useCallback, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import {
  api, type Question, type GameLecture, type AnswerResult,
  type MCQData, type FillBlankData, type MatchingData, type EssayData,
} from "@/lib/api";
import MCQ from "@/components/quiz/MCQ";
import FillBlank from "@/components/quiz/FillBlank";
import Matching from "@/components/quiz/Matching";
import Essay from "@/components/quiz/Essay";
import Battle, { type BattleHandle } from "@/components/game/Battle";

// 유형별 제한시간(초) / 기본 점수 / 라벨
const TIMER: Record<string, number> = { mcq: 45, fill_blank: 60, matching: 90, essay: 300 };
const BASE_PT: Record<string, number> = { mcq: 100, fill_blank: 150, matching: 200, essay: 500 };
const PHASE_LABEL: Record<string, string> = {
  mcq: "⚔️ 잡몹전", fill_blank: "🛡️ 중간보스", matching: "🛡️ 중간보스", essay: "👑 보스전",
};

function GamePage() {
  const params = useSearchParams();
  const bookId = params.get("bookId") ?? "";

  const [screen, setScreen] = useState<"map" | "loading" | "play" | "clear" | "gameover">("map");

  // 브라우저/모바일 뒤로가기 → 맵으로 돌아옴
  useEffect(() => {
    const onPop = () => {
      stopTimer();
      setScreen("map");
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const [lectures, setLectures] = useState<GameLecture[]>([]);
  const [current, setCurrent] = useState<GameLecture | null>(null);

  const [sessionId, setSessionId] = useState("");
  const [questions, setQuestions] = useState<Question[]>([]);
  const [idx, setIdx] = useState(0);
  const [lives, setLives] = useState(3);
  const [combo, setCombo] = useState(0);
  const [maxCombo, setMaxCombo] = useState(0);
  const [score, setScore] = useState(0);
  const [answered, setAnswered] = useState(false);
  const [timeLeft, setTimeLeft] = useState(0);
  const [timedOut, setTimedOut] = useState(false);
  const [lastGain, setLastGain] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const battleRef = useRef<BattleHandle>(null);

  const loadProgress = useCallback(() => {
    if (bookId) api.game.progress(bookId).then(setLectures).catch(() => setLectures([]));
  }, [bookId]);

  useEffect(() => { loadProgress(); }, [loadProgress]);

  const stopTimer = () => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
  };

  // 문제가 바뀌면 타이머 시작
  useEffect(() => {
    if (screen !== "play" || answered) return;
    const q = questions[idx];
    if (!q) return;
    setTimeLeft(TIMER[q.type] ?? 60);
    stopTimer();
    timerRef.current = setInterval(() => {
      setTimeLeft(t => {
        if (t <= 1) { stopTimer(); handleTimeout(); return 0; }
        return t - 1;
      });
    }, 1000);
    return stopTimer;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [screen, idx, questions]);

  // 새 문제 = 새 몬스터 등장
  useEffect(() => {
    if (screen !== "play") return;
    const q = questions[idx];
    if (q) battleRef.current?.spawnEnemy(q.type);
  }, [screen, idx, questions]);

  const goMap = () => {
    stopTimer();
    setScreen("map");
    window.history.pushState(null, "");
  };

  const startStage = async (lec: GameLecture) => {
    setCurrent(lec);
    window.history.pushState(null, "");
    setScreen("loading");
    try {
      const res = await api.game.start(lec.id);
      setSessionId(res.session_id);
      setQuestions(res.questions);
      setIdx(0); setLives(3); setCombo(0); setMaxCombo(0); setScore(0);
      setAnswered(false); setTimedOut(false);
      setScreen("play");
    } catch (err) {
      alert("스테이지 준비 실패: " + String(err));
      setScreen("map");
    }
  };

  const loseLife = (finalScore: number) => {
    setCombo(0);
    setLives(l => {
      const next = l - 1;
      if (next <= 0) {
        stopTimer();
        api.game.record(current!.id, { cleared: false, score: finalScore, stars: 0, max_combo: maxCombo })
          .then(loadProgress).catch(() => {});
        // 피격 → 쓰러짐 애니메이션을 보여준 뒤 게임오버 화면으로
        setTimeout(() => battleRef.current?.defeat(), 500);
        setTimeout(() => setScreen("gameover"), 1500);
      }
      return next;
    });
  };

  const handleTimeout = () => {
    setTimedOut(true);
    setAnswered(true);
    battleRef.current?.hurt();
    loseLife(score);
  };

  // 퀴즈 컴포넌트의 onSubmit 래핑 — 채점 후 게임 상태 갱신
  const handleAnswer = async (answer: Record<string, unknown>): Promise<AnswerResult> => {
    stopTimer();
    const q = questions[idx];
    const result = await api.sessions.answer({
      session_id: sessionId,
      question_id: q.id,
      user_answer: answer,
      time_spent_sec: (TIMER[q.type] ?? 60) - timeLeft,
    });
    setAnswered(true);
    if (result.is_correct) {
      const newCombo = combo + 1;
      setCombo(newCombo);
      setMaxCombo(m => Math.max(m, newCombo));
      const mult = Math.min(2, 1 + 0.25 * (newCombo - 1));
      const gain = Math.floor((BASE_PT[q.type] ?? 100) * result.score * mult);
      setLastGain(gain);
      setScore(s => s + gain);
      battleRef.current?.attack(true, gain);
    } else {
      // 부분 점수(짝맞추기·서술형)는 절반만 인정
      const gain = Math.floor((BASE_PT[q.type] ?? 100) * result.score * 0.5);
      setLastGain(gain);
      setScore(s => s + gain);
      battleRef.current?.hurt();
      loseLife(score + gain);
    }
    return result;
  };

  const handleNext = async () => {
    if (idx + 1 >= questions.length) {
      stopTimer();
      await api.sessions.complete(sessionId).catch(() => {});
      const stars = lives; // 남은 목숨 = 별
      await api.game.record(current!.id, { cleared: true, score, stars, max_combo: maxCombo })
        .catch(() => {});
      loadProgress();
      setScreen("clear");
    } else {
      setIdx(i => i + 1);
      setAnswered(false);
      setTimedOut(false);
      setLastGain(0);
    }
  };

  // ── 스테이지 맵 ─────────────────────────────
  if (screen === "map") {
    const clearedCount = lectures.filter(l => l.progress?.cleared).length;
    const parts = Array.from(new Set(lectures.map(l => l.part ?? "기타")));
    const firstUncleared = lectures.find(l => !l.progress?.cleared)?.id;
    return (
      <main className="min-h-screen bg-gray-900 p-6 text-white">
        <div className="max-w-3xl mx-auto">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-2xl font-bold">🏰 강의 정복</h1>
              <p className="text-gray-400 text-sm mt-1">한 강씩 도장깨기 — 보스(서술형)를 쓰러뜨리면 클리어</p>
            </div>
            <div className="text-right">
              <p className="text-3xl font-bold text-amber-400">{clearedCount}<span className="text-lg text-gray-400"> / {lectures.length}</span></p>
              <p className="text-xs text-gray-400">정복한 강의</p>
            </div>
          </div>

          {lectures.length === 0 && (
            <p className="text-center text-gray-500 py-12">강의 목록을 불러오는 중...</p>
          )}

          {parts.map(part => (
            <div key={part} className="mb-6">
              <h2 className="text-sm font-semibold text-gray-400 mb-2">{part}</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {lectures.filter(l => (l.part ?? "기타") === part).map(l => {
                  const p = l.progress;
                  const isNext = l.id === firstUncleared;
                  return (
                    <button
                      key={l.id}
                      onClick={() => startStage(l)}
                      className={`text-left rounded-xl p-3 border-2 transition-colors
                        ${p?.cleared
                          ? "border-emerald-700 bg-emerald-950/60 hover:border-emerald-500"
                          : isNext
                            ? "border-amber-500 bg-amber-950/40 hover:border-amber-400"
                            : "border-gray-700 bg-gray-800/60 hover:border-gray-500"}`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-semibold">
                          {l.source === "minor" ? "[마이너] " : ""}{l.lecture_no}강 {l.title.slice(0, 26)}
                        </span>
                        {isNext && !p?.cleared && (
                          <span className="text-[10px] font-bold text-amber-400 border border-amber-500 rounded-full px-2 py-0.5">NEXT</span>
                        )}
                      </div>
                      <div className="flex items-center justify-between mt-1">
                        <span className="text-xs text-amber-400">
                          {p?.cleared ? "★".repeat(p.stars) + "☆".repeat(3 - p.stars) : "☆☆☆"}
                        </span>
                        <span className="text-[11px] text-gray-500">
                          {p ? `최고 ${p.best_score}점 · ${p.attempts}회 도전` : "미도전"}
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}

          <div className="flex justify-center gap-6 mt-8">
            <a href="/" className="text-sm text-gray-500 hover:text-gray-300">← 홈으로</a>
          </div>
        </div>
      </main>
    );
  }

  // ── 로딩 ────────────────────────────────────
  if (screen === "loading") return (
    <main className="min-h-screen bg-gray-900 flex items-center justify-center text-white">
      <div className="text-center">
        <div className="text-5xl mb-4 animate-bounce">⚔️</div>
        <p className="text-xl font-semibold">스테이지 준비 중...</p>
        <p className="text-gray-400 mt-2 text-sm">문제은행이 비어있으면 AI가 새로 만들어요 (최대 1분)</p>
      </div>
    </main>
  );

  // ── 클리어 ──────────────────────────────────
  if (screen === "clear") return (
    <main className="min-h-screen bg-gray-900 flex items-center justify-center p-8 text-white">
      <div className="max-w-md w-full bg-gray-800 rounded-2xl p-8 text-center border-2 border-amber-500">
        <div className="text-6xl mb-2">🏆</div>
        <h2 className="text-2xl font-bold mb-1">스테이지 클리어!</h2>
        <p className="text-gray-400 text-sm mb-4">{current?.lecture_no}강 {current?.title.slice(0, 30)}</p>
        <p className="text-4xl text-amber-400 mb-2">{"★".repeat(lives)}{"☆".repeat(3 - lives)}</p>
        <p className="text-5xl font-bold text-white my-4">{score.toLocaleString()}<span className="text-lg text-gray-400">점</span></p>
        <p className="text-gray-400 text-sm">최대 콤보 ×{maxCombo}</p>
        <div className="flex gap-3 mt-8">
          <button onClick={goMap}
            className="flex-1 py-3 rounded-xl bg-amber-500 text-gray-900 font-bold">
            다음 스테이지
          </button>
          <button onClick={() => current && startStage(current)}
            className="flex-1 py-3 rounded-xl border border-gray-600 text-gray-300 font-semibold">
            다시 도전
          </button>
        </div>
      </div>
    </main>
  );

  // ── 게임 오버 ───────────────────────────────
  if (screen === "gameover") return (
    <main className="min-h-screen bg-gray-900 flex items-center justify-center p-8 text-white">
      <div className="max-w-md w-full bg-gray-800 rounded-2xl p-8 text-center border-2 border-red-800">
        <div className="text-6xl mb-2">💀</div>
        <h2 className="text-2xl font-bold mb-1">게임 오버</h2>
        <p className="text-gray-400 text-sm mb-4">{current?.lecture_no}강 — 목숨을 모두 잃었어요</p>
        <p className="text-3xl font-bold text-white my-4">{score.toLocaleString()}점</p>
        <p className="text-gray-500 text-sm">틀린 개념은 복습 큐에 자동으로 들어가요</p>
        <div className="flex gap-3 mt-8">
          <button onClick={() => current && startStage(current)}
            className="flex-1 py-3 rounded-xl bg-red-600 text-white font-bold">
            재도전
          </button>
          <button onClick={goMap}
            className="flex-1 py-3 rounded-xl border border-gray-600 text-gray-300 font-semibold">
            맵으로
          </button>
        </div>
      </div>
    </main>
  );

  // ── 플레이 ──────────────────────────────────
  const q = questions[idx];
  if (!q) return null;
  const total = TIMER[q.type] ?? 60;
  const timePct = (timeLeft / total) * 100;
  const isBoss = q.type === "essay";

  return (
    <main className={`min-h-screen p-6 ${isBoss ? "bg-red-950" : "bg-gray-900"}`}>
      <div className="max-w-2xl mx-auto">
        {/* HUD */}
        <div className="flex items-center justify-between mb-3 text-white">
          <div className="flex items-center gap-3">
            <button onClick={goMap} className="text-gray-500 hover:text-gray-300 text-sm">
              ← 맵
            </button>
            <span className="text-xl tracking-wider">
              {"❤️".repeat(lives)}{"🖤".repeat(3 - lives)}
            </span>
            {combo >= 2 && (
              <span className="px-2 py-0.5 rounded-full bg-amber-500 text-gray-900 text-xs font-bold animate-pulse">
                🔥 {combo}콤보 ×{Math.min(2, 1 + 0.25 * (combo - 1)).toFixed(2)}
              </span>
            )}
          </div>
          <div className="text-right">
            <p className="text-lg font-bold">{score.toLocaleString()}점</p>
            {lastGain > 0 && answered && <p className="text-xs text-emerald-400">+{lastGain}</p>}
          </div>
        </div>

        {/* 스테이지 진행 */}
        <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
          <span className={isBoss ? "text-red-400 font-bold" : ""}>{PHASE_LABEL[q.type]}</span>
          <span>{idx + 1} / {questions.length}</span>
        </div>
        <div className="flex gap-1 mb-3">
          {questions.map((qq, i) => (
            <div key={qq.id} className={`h-1.5 flex-1 rounded-full
              ${i < idx ? "bg-emerald-500" : i === idx ? (isBoss ? "bg-red-500" : "bg-amber-400") : "bg-gray-700"}`} />
          ))}
        </div>

        {/* 전투 씬 (Phaser) */}
        <div className="bg-gray-800/60 rounded-2xl mb-3 overflow-hidden">
          <Battle ref={battleRef} />
        </div>

        {/* 타이머 */}
        {!answered && (
          <div className="mb-4">
            <div className="flex justify-between text-xs text-gray-400 mb-1">
              <span>⏱ 남은 시간</span>
              <span className={timeLeft <= 10 ? "text-red-400 font-bold" : ""}>{timeLeft}초</span>
            </div>
            <div className="bg-gray-700 rounded-full h-2">
              <div
                className={`h-2 rounded-full transition-all ${timePct > 50 ? "bg-emerald-500" : timePct > 20 ? "bg-amber-400" : "bg-red-500"}`}
                style={{ width: `${timePct}%` }}
              />
            </div>
          </div>
        )}

        {/* 문제 카드 */}
        <div className={`bg-white rounded-2xl p-6 mb-4 ${isBoss ? "border-4 border-red-500" : ""}`}>
          {isBoss && (
            <p className="text-red-600 font-bold text-sm mb-3">👑 보스전 — 서술형 60점 이상이면 격파!</p>
          )}
          {timedOut ? (
            <div className="text-center py-6">
              <p className="text-4xl mb-2">⏰</p>
              <p className="font-bold text-red-600 text-lg">시간 초과!</p>
              <p className="text-gray-500 text-sm mt-1">목숨을 1개 잃었어요</p>
            </div>
          ) : (
            <div key={q.id}>
              {q.type === "mcq" && <MCQ data={q.question_data as MCQData} onSubmit={handleAnswer} />}
              {q.type === "fill_blank" && <FillBlank data={q.question_data as FillBlankData} onSubmit={handleAnswer} />}
              {q.type === "matching" && <Matching data={q.question_data as MatchingData} onSubmit={handleAnswer} />}
              {q.type === "essay" && <Essay data={q.question_data as EssayData} onSubmit={handleAnswer} />}
            </div>
          )}
        </div>

        {answered && (
          <button onClick={handleNext}
            className="w-full py-3 rounded-xl bg-amber-500 text-gray-900 font-bold text-lg">
            {idx + 1 >= questions.length ? "🏆 결과 보기" : "다음 →"}
          </button>
        )}
      </div>
    </main>
  );
}

export default function GamePageWrapper() {
  return <Suspense><GamePage /></Suspense>;
}
