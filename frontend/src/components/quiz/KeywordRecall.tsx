"use client";
import { useState } from "react";
import { type EssayData, type AnswerResult } from "@/lib/api";

interface Props {
  data: EssayData;
  onSubmit: (answer: Record<string, unknown>) => Promise<AnswerResult>;
}

/**
 * 서술형 1단계 — 문장 대신 핵심어만 인출한다 (PHASE1_SPEC §9-5).
 *
 * 교육학 문항은 대부분 서술형이라 "서술형 빼기"가 불가능하다. 대신 요구 수준을 낮춰
 * 인출 연습만 성립시킨다. 핵심 개념은 **답하기 전에는 절대 보여주지 않는다** —
 * 보여주면 회상이 아니라 읽기가 되어 카드의 의미가 사라진다.
 */
export default function KeywordRecall({ data, onSubmit }: Props) {
  const [text, setText] = useState("");
  const [result, setResult] = useState<AnswerResult | null>(null);
  const [loading, setLoading] = useState(false);

  const keyCount = data.key_concepts?.length ?? 0;

  const handleSubmit = async () => {
    setLoading(true);
    try {
      setResult(await onSubmit({ text }));
    } finally {
      setLoading(false);
    }
  };

  const recalled = result?.recalled ?? [];
  const missed = result?.missed ?? [];

  return (
    <div className="space-y-4">
      <p className="text-lg font-medium leading-relaxed">{data.stem}</p>

      <div className="rounded-lg bg-indigo-50 border border-indigo-200 p-3">
        <p className="text-sm text-indigo-900 font-medium">
          ✏️ 문장으로 쓰지 말고, <strong>핵심 개념어만</strong> 떠올려 적어보세요.
        </p>
        {keyCount > 0 && (
          <p className="text-xs text-indigo-700 mt-1">
            이 문제의 핵심 개념은 {keyCount}개예요. 쉼표로 구분해서 적으면 됩니다.
          </p>
        )}
      </div>

      <input
        type="text"
        value={text}
        onChange={e => setText(e.target.value)}
        onKeyDown={e => {
          if (e.key === "Enter" && !result && text.trim() && !loading) handleSubmit();
        }}
        disabled={!!result}
        placeholder="예) 조작적 조건화, 정적 강화, 소거"
        className="w-full border rounded-lg p-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 disabled:bg-gray-50"
      />

      {!result && (
        <button
          onClick={handleSubmit}
          disabled={!text.trim() || loading}
          className="w-full py-3 rounded-lg bg-indigo-600 text-white font-semibold disabled:opacity-40"
        >
          {loading ? "확인 중..." : "확인"}
        </button>
      )}

      {result && (
        <div className="space-y-3">
          {result.score != null && (
            <div className="p-4 rounded-lg bg-gray-50 border">
              <p className="font-semibold text-gray-800 mb-2">
                핵심 개념 {recalled.length}/{recalled.length + missed.length}개 회상
              </p>
              <div className="flex gap-1.5 flex-wrap">
                {recalled.map(k => (
                  <span key={k} className="px-2 py-0.5 rounded bg-green-100 text-green-800 text-sm">
                    ✓ {k}
                  </span>
                ))}
                {missed.map(k => (
                  <span key={k} className="px-2 py-0.5 rounded bg-red-100 text-red-700 text-sm">
                    ✗ {k}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* 놓친 개념을 확인한 직후 모범답안을 붙여야 학습이 닫힌다 — 접지 않고 바로 편다 */}
          {data.model_answer && (
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
