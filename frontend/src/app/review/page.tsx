"use client";
import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { api, type Question } from "@/lib/api";

function ReviewPage() {
  const params = useSearchParams();
  const bookId = params.get("bookId") ?? "";
  const [queue, setQueue] = useState<Question[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    api.review.queue(bookId).then(q => { setQueue(q); setLoaded(true); });
  }, [bookId]);

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-2xl mx-auto">
        <h2 className="text-2xl font-bold mb-2">🔁 오늘의 복습</h2>
        <p className="text-gray-400 text-sm mb-6">SM-2 알고리즘 기반 · 틀린 문제 우선</p>

        {!loaded && <p className="text-gray-400">불러오는 중...</p>}

        {loaded && queue.length === 0 && (
          <div className="text-center py-16">
            <div className="text-5xl mb-4">🎊</div>
            <p className="text-xl font-semibold text-gray-700">오늘 복습할 문제가 없어요!</p>
            <p className="text-gray-400 mt-1">내일 또 확인해보세요.</p>
          </div>
        )}

        {queue.length > 0 && (
          <>
            <p className="text-sm text-gray-600 mb-4">
              <strong>{queue.length}개</strong> 문제가 오늘 복습 대상입니다.
            </p>
            <Link
              href={`/quiz?bookId=${bookId}&reviewMode=true`}
              className="block w-full py-4 rounded-xl bg-purple-600 text-white font-bold text-center text-lg"
            >
              복습 시작 →
            </Link>
          </>
        )}
      </div>
    </main>
  );
}

export default function ReviewPageWrapper() {
  return <Suspense><ReviewPage /></Suspense>;
}
