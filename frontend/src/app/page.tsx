"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type CumulativeStats } from "@/lib/api";

const SEC_PER_CARD = 45;

export default function Home() {
  const [cardCount, setCardCount] = useState<number | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [stats, setStats] = useState<CumulativeStats | null>(null);

  const load = () => {
    setLoadError(false);
    setCardCount(null);
    const device = window.innerWidth < 768 ? "mobile" : "desktop";
    api.review.today(device)
      .then(res => setCardCount(res.cards.length))
      .catch(() => setLoadError(true));
  };

  useEffect(load, []);

  useEffect(() => {
    if (cardCount === 0) {
      api.stats.cumulative().then(setStats).catch(() => setStats(null));
    }
  }, [cardCount]);

  const minutes = cardCount ? Math.max(1, Math.ceil((cardCount * SEC_PER_CARD) / 60)) : 0;

  return (
    <main className="min-h-screen bg-gray-50 flex flex-col">
      <div className="flex-1 flex items-center justify-center p-6">
        <div className="max-w-md w-full">
          {cardCount === null && !loadError && (
            <p className="text-center text-gray-400">오늘의 복습을 준비하는 중...</p>
          )}

          {loadError && (
            <div className="text-center">
              <p className="text-gray-500 mb-4">불러오지 못했어요.</p>
              <button
                onClick={load}
                className="px-5 py-2 rounded-lg bg-gray-800 text-white text-sm font-semibold"
              >
                다시 시도
              </button>
            </div>
          )}

          {cardCount !== null && cardCount > 0 && (
            <Link
              href="/review"
              className="block w-full bg-white rounded-3xl shadow-sm border border-gray-100 p-10 text-center hover:shadow-md transition-shadow"
            >
              <div className="text-5xl mb-4">🔁</div>
              <p className="text-2xl font-bold text-gray-900 mb-1">
                오늘의 복습 {cardCount}개
              </p>
              <p className="text-gray-400 mb-6">약 {minutes}분</p>
              <span className="inline-block px-8 py-3 rounded-xl bg-blue-600 text-white font-bold text-lg">
                시작하기 →
              </span>
            </Link>
          )}

          {cardCount === 0 && (
            <div className="text-center">
              <div className="text-5xl mb-4">🎉</div>
              <p className="text-xl font-bold text-gray-900 mb-1">오늘 분량 완료</p>
              <p className="text-gray-400 mb-8">내일 또 만나요.</p>

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

              <Link
                href="/books"
                className="inline-block px-6 py-2.5 rounded-xl border-2 border-gray-200 text-gray-600 font-semibold text-sm hover:border-gray-300"
              >
                더 풀기 (새 문제)
              </Link>
            </div>
          )}
        </div>
      </div>

      <div className="flex justify-center gap-6 pb-8 text-sm text-gray-400">
        <Link href="/books" className="hover:text-gray-600">교재 관리</Link>
        <Link href="/weakness" className="hover:text-gray-600">약점 보기</Link>
      </div>
    </main>
  );
}
