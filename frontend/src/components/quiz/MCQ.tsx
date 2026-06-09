"use client";
import { useState } from "react";
import type { MCQData, AnswerResult } from "@/lib/api";

interface Props {
  data: MCQData;
  onSubmit: (answer: Record<string, unknown>) => Promise<AnswerResult>;
}

export default function MCQ({ data, onSubmit }: Props) {
  const [selected, setSelected] = useState<number | null>(null);
  const [result, setResult] = useState<AnswerResult | null>(null);

  const handleSubmit = async () => {
    if (selected === null) return;
    const res = await onSubmit({ selected });
    setResult(res);
  };

  return (
    <div className="space-y-4">
      <p className="text-lg font-medium leading-relaxed">{data.stem}</p>

      <div className="space-y-2">
        {data.options.map((opt, i) => {
          let cls = "w-full text-left px-4 py-3 rounded-lg border-2 transition-colors ";
          if (result) {
            if (i === data.answer) cls += "border-green-500 bg-green-50 text-green-800";
            else if (i === selected) cls += "border-red-400 bg-red-50 text-red-800";
            else cls += "border-gray-200 text-gray-500";
          } else {
            cls += selected === i
              ? "border-blue-500 bg-blue-50"
              : "border-gray-200 hover:border-blue-300";
          }
          return (
            <button key={i} className={cls} onClick={() => !result && setSelected(i)}>
              {opt}
            </button>
          );
        })}
      </div>

      {!result && (
        <button
          onClick={handleSubmit}
          disabled={selected === null}
          className="w-full py-3 rounded-lg bg-blue-600 text-white font-semibold disabled:opacity-40"
        >
          제출
        </button>
      )}

      {result && (
        <div className={`p-4 rounded-lg ${result.is_correct ? "bg-green-50 border border-green-300" : "bg-red-50 border border-red-300"}`}>
          <p className="font-semibold">{result.is_correct ? "✅ 정답!" : "❌ 오답"}</p>
          <p className="mt-1 text-sm text-gray-700">{result.feedback}</p>
        </div>
      )}
    </div>
  );
}
