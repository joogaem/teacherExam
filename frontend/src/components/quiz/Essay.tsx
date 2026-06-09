"use client";
import { useState } from "react";
import type { EssayData, AnswerResult } from "@/lib/api";

interface Props {
  data: EssayData;
  onSubmit: (answer: Record<string, unknown>) => Promise<AnswerResult>;
}

export default function Essay({ data, onSubmit }: Props) {
  const [text, setText] = useState("");
  const [result, setResult] = useState<AnswerResult | null>(null);
  const [showModel, setShowModel] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    setLoading(true);
    const res = await onSubmit({ text });
    setResult(res);
    setLoading(false);
  };

  const scoreColor = (score: number) => {
    if (score >= 0.8) return "text-green-600";
    if (score >= 0.5) return "text-amber-600";
    return "text-red-600";
  };

  return (
    <div className="space-y-4">
      <p className="text-lg font-medium leading-relaxed">{data.stem}</p>

      <div className="flex gap-2 text-sm text-gray-500">
        <span>핵심 개념:</span>
        {data.key_concepts.map(k => (
          <span key={k} className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded">{k}</span>
        ))}
      </div>

      <textarea
        value={text}
        onChange={e => setText(e.target.value)}
        disabled={!!result}
        rows={8}
        placeholder="답안을 작성하세요..."
        className="w-full border rounded-lg p-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-400"
      />
      <p className="text-xs text-gray-400 text-right">{text.length}자</p>

      {!result && (
        <button
          onClick={handleSubmit}
          disabled={text.trim().length < 20 || loading}
          className="w-full py-3 rounded-lg bg-blue-600 text-white font-semibold disabled:opacity-40"
        >
          {loading ? "채점 중..." : "제출 (AI 채점)"}
        </button>
      )}

      {result && (
        <div className="space-y-3">
          <div className="p-4 rounded-lg bg-gray-50 border">
            <div className="flex items-center gap-3">
              <span className={`text-2xl font-bold ${scoreColor(result.score)}`}>
                {Math.round(result.score * 100)}점
              </span>
              <div className="flex-1 bg-gray-200 rounded-full h-2">
                <div
                  className={`h-2 rounded-full ${result.score >= 0.8 ? "bg-green-500" : result.score >= 0.5 ? "bg-amber-400" : "bg-red-400"}`}
                  style={{ width: `${result.score * 100}%` }}
                />
              </div>
            </div>
            <p className="mt-2 text-sm text-gray-700">{result.feedback}</p>
          </div>

          <button
            onClick={() => setShowModel(!showModel)}
            className="text-sm text-blue-600 underline"
          >
            {showModel ? "모범 답안 닫기" : "모범 답안 보기"}
          </button>

          {showModel && (
            <div className="p-4 rounded-lg bg-blue-50 border border-blue-200 text-sm">
              <p className="font-medium text-blue-800 mb-2">모범 답안</p>
              <p className="text-gray-700 whitespace-pre-wrap">{data.model_answer}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
