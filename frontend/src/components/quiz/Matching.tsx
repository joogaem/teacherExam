"use client";
import { useState } from "react";
import type { MatchingData, AnswerResult } from "@/lib/api";

interface Props {
  data: MatchingData;
  onSubmit: (answer: Record<string, unknown>) => Promise<AnswerResult>;
}

export default function Matching({ data, onSubmit }: Props) {
  // pairs: [leftIdx, rightIdx][]
  const [pairs, setPairs] = useState<[number, number][]>([]);
  const [selectedLeft, setSelectedLeft] = useState<number | null>(null);
  const [result, setResult] = useState<AnswerResult | null>(null);

  const matchedLeft = new Set(pairs.map(p => p[0]));
  const matchedRight = new Set(pairs.map(p => p[1]));

  const handleLeft = (i: number) => {
    if (result) return;
    setSelectedLeft(i);
  };

  const handleRight = (j: number) => {
    if (result || selectedLeft === null) return;
    // 이미 연결된 왼쪽/오른쪽이면 제거 후 재연결
    const filtered = pairs.filter(p => p[0] !== selectedLeft && p[1] !== j);
    setPairs([...filtered, [selectedLeft, j]]);
    setSelectedLeft(null);
  };

  const handleSubmit = async () => {
    const res = await onSubmit({ pairs });
    setResult(res);
  };

  const getPairColor = (idx: number, side: "left" | "right") => {
    if (!result) return "";
    const correct = data.pairs;
    const isCorrect = correct.some(p =>
      side === "left" ? p[0] === idx : p[1] === idx
    );
    return isCorrect ? "border-green-500 bg-green-50" : "border-red-400 bg-red-50";
  };

  return (
    <div className="space-y-4">
      <p className="font-medium">{data.instruction}</p>

      <div className="grid grid-cols-2 gap-4">
        {/* 왼쪽 */}
        <div className="space-y-2">
          {data.left.map((item, i) => (
            <button
              key={i}
              onClick={() => handleLeft(i)}
              className={`w-full text-left px-4 py-3 rounded-lg border-2 transition-colors
                ${selectedLeft === i ? "border-blue-500 bg-blue-50" : ""}
                ${matchedLeft.has(i) && selectedLeft !== i ? "border-blue-300 bg-blue-50/50" : ""}
                ${!matchedLeft.has(i) && selectedLeft !== i ? "border-gray-200 hover:border-blue-300" : ""}
                ${result ? getPairColor(i, "left") : ""}
              `}
            >
              {item}
              {matchedLeft.has(i) && (
                <span className="ml-2 text-xs text-blue-500">
                  → {data.right[pairs.find(p => p[0] === i)![1]]}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* 오른쪽 */}
        <div className="space-y-2">
          {data.right.map((item, j) => (
            <button
              key={j}
              onClick={() => handleRight(j)}
              className={`w-full text-left px-4 py-3 rounded-lg border-2 transition-colors
                ${matchedRight.has(j) ? "border-purple-300 bg-purple-50/50" : "border-gray-200"}
                ${selectedLeft !== null && !matchedRight.has(j) ? "hover:border-purple-400" : ""}
                ${result ? getPairColor(j, "right") : ""}
              `}
            >
              {item}
            </button>
          ))}
        </div>
      </div>

      {pairs.length > 0 && !result && (
        <button onClick={() => setPairs([])} className="text-sm text-gray-400 underline">
          초기화
        </button>
      )}

      {!result && (
        <button
          onClick={handleSubmit}
          disabled={pairs.length < data.left.length}
          className="w-full py-3 rounded-lg bg-blue-600 text-white font-semibold disabled:opacity-40"
        >
          제출 ({pairs.length}/{data.left.length})
        </button>
      )}

      {result && (
        <div className={`p-4 rounded-lg ${result.is_correct ? "bg-green-50 border border-green-300" : "bg-amber-50 border border-amber-300"}`}>
          <p className="font-semibold">
            {result.is_correct ? "✅ 모두 정답!" : `❌ ${Math.round((result.score ?? 0) * 100)}점`}
          </p>
          {!result.is_correct && (
            <div className="mt-3 text-sm space-y-1">
              <p className="text-gray-500 font-medium">정답</p>
              {data.pairs.map(([l, r]) => (
                <p key={l} className="text-gray-700">
                  <span className="font-medium">{data.left[l]}</span>
                  <span className="text-gray-400 mx-1">→</span>
                  {data.right[r]}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
