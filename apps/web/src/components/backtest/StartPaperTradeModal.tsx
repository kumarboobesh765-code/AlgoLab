"use client";

import { useEffect, useState } from "react";
import {
  api,
  type ForwardTestOut,
  type PaperAccountOut,
  type Strategy,
} from "@/lib/api";

interface StartPaperTradeModalProps {
  strategy: Strategy;
  onClose: () => void;
  onStarted: (run: ForwardTestOut, account: PaperAccountOut) => void;
}

export function StartPaperTradeModal({
  strategy,
  onClose,
  onStarted,
}: StartPaperTradeModalProps) {
  const [accounts, setAccounts] = useState<PaperAccountOut[]>([]);
  const [accountId, setAccountId] = useState<string>("");
  const [createNew, setCreateNew] = useState(false);
  const [newName, setNewName] = useState(
    `${strategy.name} paper (${new Date().toLocaleDateString("en-IN", { day: "2-digit", month: "short" })})`,
  );
  const [newCapital, setNewCapital] = useState("1000000");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<PaperAccountOut[]>("/paper/accounts")
      .then((list) => {
        setAccounts(list);
        if (list.length === 0) {
          setCreateNew(true);
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load paper accounts"));
  }, []);

  async function start() {
    setLoading(true);
    setError(null);
    try {
      let resolvedAccount: PaperAccountOut;
      if (createNew) {
        resolvedAccount = await api<PaperAccountOut>("/paper/accounts", {
          method: "POST",
          body: JSON.stringify({
            name: newName.trim() || `${strategy.name} paper`,
            initial_capital: Math.max(1, Number(newCapital) || 1_000_000),
          }),
        });
      } else {
        const found = accounts.find((a) => a.id === accountId);
        if (!found) throw new Error("Select a paper account first");
        resolvedAccount = found;
      }

      const run = await api<ForwardTestOut>("/forward-tests", {
        method: "POST",
        body: JSON.stringify({
          strategy_id: strategy.id,
          account_id: resolvedAccount.id,
        }),
      });
      onStarted(run, resolvedAccount);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start paper trade");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-xl">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-slate-900">
            Start paper trade
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <p className="mt-1 text-xs text-slate-500">
          Forward-test{" "}
          <span className="font-medium text-slate-700">{strategy.name}</span>{" "}
          against a paper account. The runner will tick the strategy every 5
          seconds and fill orders virtually.
        </p>

        <div className="mt-4 space-y-3">
          {accounts.length > 0 && (
            <label className="block text-xs font-medium text-slate-500">
              <input
                type="radio"
                checked={!createNew}
                onChange={() => setCreateNew(false)}
                className="mr-2"
              />
              Use an existing paper account
              <select
                value={accountId}
                onChange={(e) => setAccountId(e.target.value)}
                disabled={createNew}
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-800 disabled:opacity-50"
              >
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name} — ₹
                    {Math.round(a.equity).toLocaleString("en-IN")} equity
                  </option>
                ))}
              </select>
            </label>
          )}

          <label className="block text-xs font-medium text-slate-500">
            <input
              type="radio"
              checked={createNew}
              onChange={() => setCreateNew(true)}
              className="mr-2"
            />
            Create a new paper account
          </label>

          {createNew && (
            <div className="space-y-2 rounded-md border border-slate-200 bg-slate-50 p-3">
              <label className="block text-xs font-medium text-slate-500">
                Account name
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-800"
                />
              </label>
              <label className="block text-xs font-medium text-slate-500">
                Initial capital (INR)
                <input
                  type="number"
                  value={newCapital}
                  onChange={(e) => setNewCapital(e.target.value)}
                  min="1"
                  className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-800"
                />
              </label>
            </div>
          )}
        </div>

        {error && <p className="mt-3 text-xs text-red-600">{error}</p>}

        <div className="mt-5 flex items-center justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-md border border-slate-200 px-4 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50"
          >
            Cancel
          </button>
          <button
            onClick={start}
            disabled={loading || (!createNew && !accountId)}
            className="rounded-md bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {loading ? "Starting..." : "Start paper trade"}
          </button>
        </div>
      </div>
    </div>
  );
}
