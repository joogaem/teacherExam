"use client";
import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { api, type Book } from "@/lib/api";

export default function BooksPage() {
  const [books, setBooks] = useState<Book[]>([]);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.books.list().then(setBooks).catch(console.error);
  }, []);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const title = prompt("교재 제목을 입력하세요:", file.name.replace(".pdf", ""));
    if (!title) return;
    setUploading(true);
    setProgress("PDF 분석 중... (교재 크기에 따라 2~5분 소요)");
    try {
      const res = await api.books.upload(file, title);
      setProgress(`완료! ${res.chapters.length}개 챕터 감지됨`);
      const updated = await api.books.list();
      setBooks(updated);
    } catch (err) {
      setProgress("업로드 실패: " + String(err));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-3xl mx-auto">
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">📚 교재 관리</h1>
            <p className="text-gray-500 mt-1 text-sm">교재 업로드 · 챕터·강의별 문제 생성</p>
          </div>
          <Link href="/" className="text-sm text-gray-500 hover:text-gray-700">← 오늘의 복습으로</Link>
        </div>

        <div className="bg-white rounded-2xl border-2 border-dashed border-blue-300 p-8 text-center mb-8 hover:border-blue-500 transition-colors">
          <input ref={fileRef} type="file" accept=".pdf" onChange={handleUpload}
            disabled={uploading} className="hidden" id="pdf-upload" />
          <label htmlFor="pdf-upload" className="cursor-pointer">
            <div className="text-4xl mb-2">📄</div>
            <p className="font-semibold text-gray-700">
              {uploading ? progress : "PDF 교재 업로드"}
            </p>
            <p className="text-sm text-gray-400 mt-1">클릭하여 파일 선택</p>
          </label>
        </div>

        <div className="space-y-3">
          {books.map(book => (
            <div key={book.id} className="bg-white rounded-xl p-5 shadow-sm border border-gray-100 flex items-center justify-between">
              <div>
                <p className="font-semibold text-gray-900">{book.title}</p>
                <p className="text-sm text-gray-400">{book.total_pages}페이지 · {new Date(book.created_at).toLocaleDateString()}</p>
              </div>
              <div className="flex gap-2">
                <Link href={`/browse?bookId=${book.id}`}
                  className="px-4 py-2 rounded-lg bg-gray-100 text-gray-700 text-sm font-semibold hover:bg-gray-200">
                  내용 보기
                </Link>
                <Link href={`/quiz?bookId=${book.id}`}
                  className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-semibold hover:bg-blue-700">
                  퀴즈 시작
                </Link>
                <Link href={`/game?bookId=${book.id}`}
                  className="px-4 py-2 rounded-lg bg-gray-900 text-amber-400 text-sm font-semibold hover:bg-gray-800">
                  🏰 정복전
                </Link>
              </div>
            </div>
          ))}
          {books.length === 0 && !uploading && (
            <p className="text-center text-gray-400 py-8">교재를 업로드하면 여기에 표시됩니다.</p>
          )}
        </div>
      </div>
    </main>
  );
}
