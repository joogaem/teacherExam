"use client";
import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { api, type WeaknessRow } from "@/lib/api";

const TYPE_LABEL: Record<string, string> = {
  mcq: "객관식", fill_blank: "빈칸", matching: "짝맞추기", essay: "서술형",
};

function WeaknessPage() {
  const params = useSearchParams();
  const bookId = params.get("bookId") ?? "";
  const [data, setData] = useState<WeaknessRow[]>([]);

  useEffect(() => {
    api.weakness.get(bookId).then(setData);
  }, [bookId]);

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-3xl mx-auto">
        <h2 className="text-2xl font-bold mb-6">📊 약점 분석</h2>

        {data.length === 0 ? (
          <p className="text-gray-400 text-center py-16">아직 풀이 데이터가 없습니다.</p>
        ) : (
          <div className="space-y-3">
            {data.map((row, i) => (
              <div key={i} className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
                <div className="flex justify-between items-center mb-2">
                  <div>
                    <span className="font-medium text-gray-900">{row.chapter}</span>
                    <span className="ml-2 text-xs px-2 py-0.5 bg-gray-100 rounded text-gray-500">
                      {TYPE_LABEL[row.type] ?? row.type}
                    </span>
                  </div>
                  <span className={`text-lg font-bold ${
                    row.avg_score_pct >= 80 ? "text-green-600" :
                    row.avg_score_pct >= 50 ? "text-amber-500" : "text-red-500"
                  }`}>
                    {row.avg_score_pct}%
                  </span>
                </div>
                <div className="bg-gray-100 rounded-full h-2">
                  <div
                    className={`h-2 rounded-full ${
                      row.avg_score_pct >= 80 ? "bg-green-500" :
                      row.avg_score_pct >= 50 ? "bg-amber-400" : "bg-red-400"
                    }`}
                    style={{ width: `${row.avg_score_pct}%` }}
                  />
                </div>
                <p className="text-xs text-gray-400 mt-1">
                  {row.correct_count}/{row.total_attempts}회 정답
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}

export default function WeaknessPageWrapper() {
  return <Suspense><WeaknessPage /></Suspense>;
}
