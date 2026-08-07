"use client";
import { useState } from "react";
import { api, type EssayData, type AnswerResult } from "@/lib/api";

interface Props {
  data: EssayData;
  onSubmit: (answer: Record<string, unknown>) => Promise<AnswerResult>;
  /** short=단답형(한 줄 입력), essay=서술형(여러 줄 작성). 화면에서 두 유형이
   *  구분되지 않아 사용자가 혼동한다는 피드백으로 분리 (§9-5). */
  variant?: "essay" | "short";
}

const VERDICTS = [
  { key: "ok" as const, label: "잘 썼다", desc: "핵심 개념이 다 들어감", cls: "bg-green-600 text-white" },
  { key: "partial" as const, label: "애매하다", desc: "일부만 맞음", cls: "bg-amber-100 text-amber-800 border-2 border-amber-300" },
  { key: "no" as const, label: "못 썼다", desc: "다시 봐야 함", cls: "bg-red-100 text-red-700 border-2 border-red-300" },
];

export default function Essay({ data, onSubmit, variant = "essay" }: Props) {
  const [text, setText] = useState("");
  const [result, setResult] = useState<AnswerResult | null>(null);
  const [showModel, setShowModel] = useState(false);
  const [loading, setLoading] = useState(false);
  const [selfGraded, setSelfGraded] = useState<string | null>(null);
  const isShort = variant === "short";
  const minLen = isShort ? 1 : 20;   // 단답형에 20자를 요구하면 제출 자체가 막힌다

  const handleSubmit = async () => {
    setLoading(true);
    try {
      const res = await onSubmit({ text });
      setResult(res);
      // AI 채점을 못 쓰면 모범답안을 바로 펼쳐서 스스로 대조하게 한다
      if (res.needs_self_grade) setShowModel(true);
    } finally {
      setLoading(false);
    }
  };

  const handleSelfGrade = async (verdict: "ok" | "partial" | "no") => {
    if (!result?.answer_id) return;
    setSelfGraded(verdict);
    await api.sessions.selfGrade(result.answer_id, verdict).catch(() => {});
  };

  const scoreColor = (score: number) => {
    if (score >= 0.8) return "text-green-600";
    if (score >= 0.5) return "text-amber-600";
    return "text-red-600";
  };

  return (
    <div className="space-y-4">
      <p className="text-lg font-medium leading-relaxed">{data.stem}</p>

      {data.key_concepts?.length > 0 && (
        <div className="flex gap-2 text-sm text-gray-500 flex-wrap">
          <span>핵심 개념:</span>
          {data.key_concepts.map(k => (
            <span key={k} className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded">{k}</span>
          ))}
        </div>
      )}

      {isShort ? (
        <input
          type="text"
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={e => {
            if (e.key === "Enter" && !result && text.trim() && !loading) handleSubmit();
          }}
          disabled={!!result}
          placeholder="한 단어 또는 짧은 구로 답하세요"
          className="w-full border rounded-lg p-3 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400 disabled:bg-gray-50"
        />
      ) : (
        <>
          <textarea
            value={text}
            onChange={e => setText(e.target.value)}
            disabled={!!result}
            rows={8}
            placeholder="답안을 작성하세요..."
            className="w-full border rounded-lg p-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
          <p className="text-xs text-gray-400 text-right">{text.length}자</p>
        </>
      )}

      {!result && (
        <button
          onClick={handleSubmit}
          disabled={text.trim().length < minLen || loading}
          className={`w-full py-3 rounded-lg text-white font-semibold disabled:opacity-40 ${
            isShort ? "bg-teal-600" : "bg-blue-600"
          }`}
        >
          {loading ? "채점 중..." : "제출"}
        </button>
      )}

      {result && (
        <div className="space-y-3">
          {/* AI 채점 결과 */}
          {!result.needs_self_grade && result.score != null && (
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
          )}

          {/* 자가 채점 */}
          {result.needs_self_grade && (
            <div className="p-4 rounded-lg bg-amber-50 border border-amber-200">
              <p className="text-sm text-amber-900 font-medium mb-1">스스로 채점하기</p>
              <p className="text-xs text-amber-800 mb-3">
                아래 모범답안과 내 답을 비교해보고, 솔직하게 골라주세요. 이 판정이 복습 주기에 반영됩니다.
              </p>
              {selfGraded ? (
                <p className="text-sm font-semibold text-amber-900">
                  ✓ &lsquo;{VERDICTS.find(v => v.key === selfGraded)?.label}&rsquo;(으)로 기록했어요
                </p>
              ) : (
                <div className="flex gap-2">
                  {VERDICTS.map(v => (
                    <button
                      key={v.key}
                      onClick={() => handleSelfGrade(v.key)}
                      className={`flex-1 py-2 px-2 rounded-lg text-sm font-semibold ${v.cls}`}
                    >
                      {v.label}
                      <span className="block text-[10px] font-normal opacity-80 mt-0.5">{v.desc}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

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
