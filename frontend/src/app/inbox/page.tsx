"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Question, type FillBlankData, type EssayData } from "@/lib/api";

const LIMIT = 50;

export default function InboxPage() {
  const [items, setItems] = useState<Question[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [typeFilter, setTypeFilter] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [status, setStatus] = useState<"loading" | "loaded" | "error">("loading");
  const [busy, setBusy] = useState(false);

  const load = () => {
    setStatus("loading");
    api.inbox.list({ q_type: typeFilter || undefined, limit: LIMIT, offset })
      .then(res => { setItems(res.items); setTotal(res.total); setStatus("loaded"); })
      .catch(() => setStatus("error"));
  };

  useEffect(load, [offset, typeFilter]);

  const toggle = (id: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };
  const selectAll = () => setSelected(new Set(items.map(i => i.id)));
  const clearSelection = () => setSelected(new Set());

  const approve = async () => {
    if (selected.size === 0 || busy) return;
    setBusy(true);
    try {
      await api.inbox.approve([...selected]);
      clearSelection();
      load();
    } finally {
      setBusy(false);
    }
  };

  const reject = async () => {
    if (selected.size === 0 || busy) return;
    if (!confirm(`${selected.size}개 카드를 삭제하시겠습니까? 되돌릴 수 없습니다.`)) return;
    setBusy(true);
    try {
      await api.inbox.reject([...selected]);
      clearSelection();
      load();
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-4xl mx-auto">
        <div className="mb-6 flex items-center justify-between">
          <h2 className="text-2xl font-bold">📥 검수함</h2>
          <Link href="/" className="text-sm text-gray-500 hover:text-gray-700">← 홈으로</Link>
        </div>

        <div className="flex items-center gap-3 mb-4 flex-wrap">
          <select
            value={typeFilter}
            onChange={e => { setOffset(0); setTypeFilter(e.target.value); }}
            className="border rounded-lg px-3 py-1.5 text-sm bg-white"
          >
            <option value="">전체 유형</option>
            <option value="fill_blank">빈칸</option>
            <option value="short_answer">단문 서술</option>
          </select>
          <span className="text-sm text-gray-400">총 {total}개 · {selected.size}개 선택</span>
          <div className="flex-1" />
          <button onClick={selectAll} className="text-sm text-blue-600 underline">전체 선택</button>
          <button onClick={clearSelection} className="text-sm text-gray-400 underline">선택 해제</button>
        </div>

        <div className="flex gap-3 mb-4">
          <button
            onClick={approve}
            disabled={selected.size === 0 || busy}
            className="px-5 py-2 rounded-lg bg-green-600 text-white text-sm font-semibold disabled:opacity-40"
          >
            선택 승인 ({selected.size})
          </button>
          <button
            onClick={reject}
            disabled={selected.size === 0 || busy}
            className="px-5 py-2 rounded-lg bg-red-100 text-red-700 text-sm font-semibold disabled:opacity-40"
          >
            선택 반려(삭제)
          </button>
        </div>

        {status === "loading" && <p className="text-gray-400 text-center py-16">불러오는 중...</p>}

        {status === "error" && (
          <div className="text-center py-16">
            <p className="text-gray-500 mb-4">불러오지 못했어요.</p>
            <button onClick={load} className="px-5 py-2 rounded-lg bg-gray-800 text-white text-sm font-semibold">
              다시 시도
            </button>
          </div>
        )}

        {status === "loaded" && (
          <>
            <div className="space-y-2">
              {items.map(item => (
                <label
                  key={item.id}
                  className="flex gap-3 bg-white rounded-xl p-4 shadow-sm border border-gray-100 cursor-pointer hover:border-gray-200"
                >
                  <input
                    type="checkbox"
                    checked={selected.has(item.id)}
                    onChange={() => toggle(item.id)}
                    className="mt-1"
                  />
                  <div className="flex-1 text-sm min-w-0">
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className="px-2 py-0.5 rounded bg-gray-100 text-gray-500 text-xs">
                        {item.chapter}
                      </span>
                      <span className="px-2 py-0.5 rounded bg-blue-100 text-blue-700 text-xs">
                        {item.type === "fill_blank" ? "빈칸" : "단문 서술"}
                      </span>
                    </div>
                    {item.type === "fill_blank" ? (
                      <>
                        <p className="text-gray-800">{(item.question_data as FillBlankData).template}</p>
                        <p className="text-green-700 mt-1">
                          답: {(item.question_data as FillBlankData).answers?.join(" / ")}
                        </p>
                      </>
                    ) : (
                      <>
                        <p className="text-gray-800">{(item.question_data as EssayData).stem}</p>
                        <p className="text-green-700 mt-1 whitespace-pre-wrap">
                          답: {(item.question_data as EssayData).model_answer}
                        </p>
                      </>
                    )}
                  </div>
                </label>
              ))}
              {items.length === 0 && (
                <p className="text-gray-400 text-center py-16">검수 대기 카드가 없습니다.</p>
              )}
            </div>

            {total > LIMIT && (
              <div className="flex justify-center items-center gap-4 mt-6">
                <button
                  onClick={() => setOffset(o => Math.max(0, o - LIMIT))}
                  disabled={offset === 0}
                  className="px-4 py-2 text-sm text-gray-600 disabled:opacity-30"
                >
                  ← 이전
                </button>
                <span className="text-sm text-gray-400">
                  {offset + 1}~{Math.min(offset + LIMIT, total)} / {total}
                </span>
                <button
                  onClick={() => setOffset(o => o + LIMIT)}
                  disabled={offset + LIMIT >= total}
                  className="px-4 py-2 text-sm text-gray-600 disabled:opacity-30"
                >
                  다음 →
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </main>
  );
}
