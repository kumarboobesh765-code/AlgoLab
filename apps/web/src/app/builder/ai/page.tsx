"use client";

import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { AiDraftResponse, Strategy } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { TEMPLATE_HANDOFF_KEY, TEMPLATE_HANDOFF_NAME } from "@/lib/builders";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";

const EXAMPLES = [
  "Buy NIFTY when RSI(14) drops below 30 on 15m and sell above 70",
  "EMA 9 and 21 crossover on BANKNIFTY 5m with stop loss 0.5% and target 1%",
  "MACD histogram crosses above zero on 5m",
  "Close below Bollinger lower band on NIFTY daily, exit at middle band",
  "Supertrend 10 period flip long on SENSEX 15m",
];

export default function AIBuilderPage() {
  const auth = useAuth();
  const [prompt, setPrompt] = useState("");
  const [drafting, setDrafting] = useState(false);
  const [draft, setDraft] = useState<AiDraftResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedStrategy, setSavedStrategy] = useState<Strategy | null>(null);

  function runDraft() {
    if (!prompt.trim() || drafting) return;
    setDrafting(true);
    setError(null);
    setDraft(null);
    setSavedStrategy(null);
    api<AiDraftResponse>("/ai/draft-strategy", {
      method: "POST",
      body: JSON.stringify({ prompt: prompt.trim() }),
    })
      .then((d) => {
        setDraft(d);
        setDrafting(false);
      })
      .catch((e: Error) => {
        setError(e.message);
        setDrafting(false);
      });
  }

  function save() {
    if (!draft || !draft.valid || saving) return;
    const d = draft.definition as {
      instrument?: { symbol?: string; exchange?: string; segment?: string };
      timeframe?: string;
    };
    const symbol = d.instrument?.symbol ?? "NIFTY";
    const exchange = d.instrument?.exchange ?? "NSE";
    setSaving(true);
    api<Strategy>("/strategies", {
      method: "POST",
      body: JSON.stringify({
        name: `AI Draft — ${prompt.trim().slice(0, 60)}`,
        description: `Drafted by AI Builder from: "${prompt.trim()}"`,
        underlying: symbol,
        exchange,
        instrument: d.instrument?.segment ?? "index",
        strategy_type: "intraday",
        tags: ["ai-draft"],
        definition: draft.definition,
      }),
    })
      .then((s) => {
        setSavedStrategy(s);
        setSaving(false);
      })
      .catch((e: Error) => {
        setError(e.message);
        setSaving(false);
      });
  }

  function openInBuilder(href: string) {
    if (!draft) return;
    sessionStorage.setItem(TEMPLATE_HANDOFF_KEY, JSON.stringify(draft.definition, null, 2));
    sessionStorage.setItem(TEMPLATE_HANDOFF_NAME, "AI Draft");
    window.location.href = href;
  }

  if (!auth.loading && !auth.user) {
    return <p className="text-sm text-slate-500">Connecting to the API…</p>;
  }
  if (auth.loading) {
    return <p className="text-sm text-slate-500">Loading…</p>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">AI Builder</h2>
        <p className="text-sm text-slate-500">
          Describe a strategy in plain English — get a validated definition you can save and
          backtest.
        </p>
      </div>

      <Card title="Describe your strategy">
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={3}
          placeholder='e.g. "Buy when RSI(14) goes below 30 on a 15m NIFTY chart and sell above 70"'
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
        />
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            onClick={runDraft}
            disabled={drafting || !prompt.trim()}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {drafting ? "Drafting…" : "Generate draft"}
          </button>
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              onClick={() => setPrompt(ex)}
              className="rounded-full border border-slate-200 px-3 py-1 text-[11px] text-slate-500 hover:bg-slate-50"
            >
              {ex.length > 44 ? `${ex.slice(0, 44)}…` : ex}
            </button>
          ))}
        </div>
        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      </Card>

      {draft && (
        <Card
          title="Draft result"
          actions={
            <div className="flex items-center gap-2">
              <Badge tone={draft.source === "llm" ? "blue" : "amber"}>
                {draft.source === "llm" ? "LLM" : "rule-based"}
              </Badge>
              <Badge tone={draft.valid ? "green" : "red"}>
                {draft.valid ? "valid" : "invalid"}
              </Badge>
            </div>
          }
        >
          {draft.errors.length > 0 && (
            <div className="mb-3 rounded-lg border border-red-200 bg-red-50 p-3">
              <p className="text-xs font-semibold text-red-700">Validation errors</p>
              <ul className="mt-1 list-inside list-disc text-xs text-red-600">
                {draft.errors.map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            </div>
          )}
          {draft.warnings.length > 0 && (
            <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 p-3">
              <p className="text-xs font-semibold text-amber-700">Warnings</p>
              <ul className="mt-1 list-inside list-disc text-xs text-amber-700">
                {draft.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          <pre className="max-h-80 overflow-auto rounded-lg bg-slate-900 p-3 text-[11px] leading-relaxed text-slate-100">
            {JSON.stringify(draft.definition, null, 2)}
          </pre>

          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button
              onClick={save}
              disabled={!draft.valid || saving}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save as strategy"}
            </button>
            <button
              onClick={() => openInBuilder("/builder/technical")}
              disabled={!draft.valid}
              className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              Open in Technical Builder
            </button>
            <button
              onClick={() => openInBuilder("/builder/visual")}
              disabled={!draft.valid}
              className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              Open in Visual Builder
            </button>
            {savedStrategy && (
              <span className="flex items-center gap-2 text-xs text-slate-600">
                Saved as <strong>{savedStrategy.name}</strong>
                <Link href={`/backtest?strategy=${savedStrategy.id}`} className="text-indigo-600 hover:underline">
                  Backtest it →
                </Link>
              </span>
            )}
          </div>
        </Card>
      )}

      <p className="text-xs text-slate-400">
        Without an LLM key configured the server uses its deterministic rule-based parser — always
        review the generated conditions before trading.
      </p>
    </div>
  );
}
