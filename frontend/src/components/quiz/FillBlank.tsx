"use client";
import { useState } from "react";
import type { FillBlankData, AnswerResult } from "@/lib/api";

interface Props {
  data: FillBlankData;
  onSubmit: (answer: Record<string, unknown>) => Promise<AnswerResult>;
}

export default function FillBlank({ data, onSubmit }: Props) {
  const blankCount = (data.template.match(/___/g) ?? []).length;
  const [texts, setTexts] = useState<string[]>(() => Array(Math.max(1, blankCount)).fill(""));
  const [result, setResult] = useState<AnswerResult | null>(null);
  const [showHint, setShowHint] = useState(false);

  const handleSubmit = async () => {
    const res = await onSubmit({ texts });
    setResult(res);
  };

  const setBlank = (i: number, val: string) =>
    setTexts(prev => prev.map((t, j) => (j === i ? val : t)));

  // ___ → input으로 치환
  const parts = data.template.split("___");

  return (
    <div className="space-y-4">
      <div className="text-lg leading-relaxed flex flex-wrap items-center gap-1">
        {parts.map((part, i) => (
          <>
            <span key={`p-${i}`}>{part}</span>
            {i < parts.length - 1 && (
              <input
                key={`i-${i}`}
                value={texts[i] ?? ""}
                onChange={e => setBlank(i, e.target.value)}
                disabled={!!result}
                placeholder="답 입력"
                className="border-b-2 border-blue-400 px-2 py-1 outline-none min-w-[100px] text-center"
              />
            )}
          </>
        ))}
      </div>

      {data.hints.length > 0 && !result && (
        <button
          onClick={() => setShowHint(true)}
          className="text-sm text-gray-400 underline"
        >
          힌트 보기
        </button>
      )}
      {showHint && (
        <p className="text-sm text-gray-500 italic">💡 {data.hints.join(", ")}</p>
      )}

      {!result && (
        <button
          onClick={handleSubmit}
          disabled={texts.some(t => !t.trim())}
          className="w-full py-3 rounded-lg bg-blue-600 text-white font-semibold disabled:opacity-40"
        >
          제출
        </button>
      )}

      {result && (
        <div className={`p-4 rounded-lg ${result.is_correct ? "bg-green-50 border border-green-300" : "bg-red-50 border border-red-300"}`}>
          <p className="font-semibold">{result.is_correct ? "✅ 정답!" : "❌ 오답"}</p>
          <p className="text-sm text-gray-600 mt-1">
            정답: <span className="font-medium text-gray-900">{data.answers.join(" / ")}</span>
          </p>
        </div>
      )}
    </div>
  );
}
