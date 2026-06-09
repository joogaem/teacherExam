"use client";
import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { api, type Book } from "@/lib/api";

interface Chunk {
  id: string;
  chapter: string;
  content: string;
  page_start: number;
}

function BrowsePage() {
  const params = useSearchParams();
  const bookIdParam = params.get("bookId") ?? "";

  const [books, setBooks] = useState<Book[]>([]);
  const [bookId, setBookId] = useState(bookIdParam);
  const [chapters, setChapters] = useState<string[]>([]);
  const [chapter, setChapter] = useState("");
  const [chunks, setChunks] = useState<Chunk[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.books.list().then(setBooks);
  }, []);

  useEffect(() => {
    if (bookId) api.books.chapters(bookId).then(setChapters);
  }, [bookId]);

  const loadChunks = async () => {
    if (!bookId || !chapter) return;
    setLoading(true);
    const res = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/chunks?book_id=${bookId}&chapter=${encodeURIComponent(chapter)}`
    );
    const data = await res.json();
    setChunks(data);
    setLoading(false);
  };

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-4xl mx-auto">
        <div className="mb-6 flex items-center gap-3">
          <a href="/" className="text-gray-400 hover:text-gray-600">← 홈</a>
          <h2 className="text-2xl font-bold">📖 챕터 내용 보기</h2>
        </div>

        <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100 mb-6 flex gap-4">
          <select
            value={bookId}
            onChange={e => { setBookId(e.target.value); setChapter(""); setChunks([]); }}
            className="flex-1 border rounded-lg px-3 py-2 text-sm"
          >
            <option value="">교재 선택</option>
            {books.map(b => (
              <option key={b.id} value={b.id}>{b.title}</option>
            ))}
          </select>

          <select
            value={chapter}
            onChange={e => setChapter(e.target.value)}
            disabled={!bookId}
            className="flex-1 border rounded-lg px-3 py-2 text-sm disabled:opacity-40"
          >
            <option value="">챕터 선택</option>
            {chapters.map(c => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>

          <button
            onClick={loadChunks}
            disabled={!chapter || loading}
            className="px-5 py-2 rounded-lg bg-blue-600 text-white text-sm font-semibold disabled:opacity-40"
          >
            {loading ? "불러오는 중..." : "보기"}
          </button>
        </div>

        {chunks.length > 0 && (
          <div className="space-y-3">
            <p className="text-sm text-gray-500">{chunks.length}개 청크</p>
            {chunks.map((chunk, i) => (
              <div key={chunk.id} className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
                <div className="flex justify-between items-center mb-2">
                  <span className="text-xs font-semibold text-blue-600">{chunk.chapter}</span>
                  <span className="text-xs text-gray-400">{chunk.page_start}p · 청크 {i + 1}</span>
                </div>
                <p className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">{chunk.content}</p>
              </div>
            ))}
          </div>
        )}

        {chunks.length === 0 && chapter && !loading && (
          <p className="text-center text-gray-400 py-16">챕터를 선택하고 보기를 클릭하세요.</p>
        )}
      </div>
    </main>
  );
}

export default function BrowsePageWrapper() {
  return <Suspense><BrowsePage /></Suspense>;
}
