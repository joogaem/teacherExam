"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type WeaknessRow } from "@/lib/api";

export default function WeaknessPage() {
  const [data, setData] = useState<WeaknessRow[]>([]);
  const [status, setStatus] = useState<"loading" | "loaded" | "error">("loading");

  const load = () => {
    setStatus("loading");
    api.weakness.get()
      .then(d => { setData(d); setStatus("loaded"); })
      .catch(() => setStatus("error"));
  };

  useEffect(load, []);

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-3xl mx-auto">
        <div className="mb-6 flex items-center justify-between">
          <h2 className="text-2xl font-bold">📊 약점 분석</h2>
          <Link href="/" className="text-sm text-gray-500 hover:text-gray-700">← 홈으로</Link>
        </div>

        {status === "loading" && (
          <p className="text-gray-400 text-center py-16">불러오는 중...</p>
        )}

        {status === "error" && (
          <div className="text-center py-16">
            <p className="text-gray-500 mb-4">불러오지 못했어요.</p>
            <button
              onClick={load}
              className="px-5 py-2 rounded-lg bg-gray-800 text-white text-sm font-semibold"
            >
              다시 시도
            </button>
          </div>
        )}

        {status === "loaded" && data.length === 0 && (
          <p className="text-gray-400 text-center py-16">아직 풀이 데이터가 없습니다.</p>
        )}

        <div className="space-y-3">
          {data.map(row => {
            const pct = row.avg_score_pct_30d ?? row.avg_score_pct;
            return (
              <div key={row.concept_id} className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
                <div className="flex justify-between items-center mb-2">
                  <div>
                    <span className="font-medium text-gray-900">{row.name}</span>
                    <span className="ml-2 text-xs px-2 py-0.5 bg-gray-100 rounded text-gray-500">
                      {row.subject}
                    </span>
                  </div>
                  <span className={`text-lg font-bold ${
                    pct >= 80 ? "text-green-600" : pct >= 50 ? "text-amber-500" : "text-red-500"
                  }`}>
                    {pct}%
                  </span>
                </div>
                <div className="bg-gray-100 rounded-full h-2">
                  <div
                    className={`h-2 rounded-full ${
                      pct >= 80 ? "bg-green-500" : pct >= 50 ? "bg-amber-400" : "bg-red-400"
                    }`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <p className="text-xs text-gray-400 mt-1">
                  {row.correct_count}/{row.total_attempts}회 정답
                  {row.missing_count > 0 && ` · 누락 개념 ${row.missing_count}회`}
                  {row.misconception_count > 0 && ` · 오개념 ${row.misconception_count}회`}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </main>
  );
}
