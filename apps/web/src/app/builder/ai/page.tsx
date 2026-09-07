"use client";

import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type {
  AiDraftResponse,
  BacktestRun,
  BacktestResults,
  Strategy,
} from "@/lib/api";
import type { StrategyDefinitionV1 } from "@/lib/builders";
import { useAuth } from "@/lib/auth";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { DeployModal } from "@/components/backtest/DeployModal";

const INSTANT_STRATEGIES: {
  label: string;
  description: string;
  tag: string;
  build: (symbol: string) => StrategyDefinitionV1;
}[] = [
  {
    label: "ATM Straddle",
    description: "Buy ATM call + ATM put at start, square off at end of day.",
    tag: "straddle",
    build: (symbol) => ({
      version: 1,
      timeframe: "5m",
      instrument: { symbol, exchange: "NSE", segment: "index" },
      variables: [],
      indicators: [],
      entry: { logic: "ALL", conditions: [] },
      exit: null,
      risk: { stop_loss_pct: null, target_pct: null, trailing_sl_pct: null },
      position: { direction: "both", quantity_type: "fixed", quantity: 1, capital_pct: null },
      strategy_type: "intraday",
      legs: [
        { action: "buy", option_type: "CE", strike_offset: 0, expiry: null, expiry_formula: "current_expiry" },
        { action: "buy", option_type: "PE", strike_offset: 0, expiry: null, expiry_formula: "current_expiry" },
      ],
    }),
  },
  {
    label: "OTM Strangle",
    description: "Buy OTM call + OTM put (500 pts from ATM), lower premium, wider breakeven.",
    tag: "strangle",
    build: (symbol) => ({
      version: 1,
      timeframe: "5m",
      instrument: { symbol, exchange: "NSE", segment: "index" },
      variables: [],
      indicators: [],
      entry: { logic: "ALL", conditions: [] },
      exit: null,
      risk: { stop_loss_pct: null, target_pct: null, trailing_sl_pct: null },
      position: { direction: "both", quantity_type: "fixed", quantity: 1, capital_pct: null },
      strategy_type: "intraday",
      legs: [
        { action: "buy", option_type: "CE", strike_offset: 500, expiry: null, expiry_formula: "current_expiry" },
        { action: "buy", option_type: "PE", strike_offset: 500, expiry: null, expiry_formula: "current_expiry" },
      ],
    }),
  },
  {
    label: "Short Straddle",
    description: "Sell ATM call + ATM put. Collect premium, bounded risk if move is large.",
    tag: "short-straddle",
    build: (symbol) => ({
      version: 1,
      timeframe: "5m",
      instrument: { symbol, exchange: "NSE", segment: "index" },
      variables: [],
      indicators: [],
      entry: { logic: "ALL", conditions: [] },
      exit: null,
      risk: { stop_loss_pct: null, target_pct: null, trailing_sl_pct: null },
      position: { direction: "both", quantity_type: "fixed", quantity: 1, capital_pct: null },
      strategy_type: "intraday",
      legs: [
        { action: "sell", option_type: "CE", strike_offset: 0, expiry: null, expiry_formula: "current_expiry" },
        { action: "sell", option_type: "PE", strike_offset: 0, expiry: null, expiry_formula: "current_expiry" },
      ],
      overall: {
        overall_sl: 1000, overall_target: null, overall_trail_sl: null,
        overall_trail_every: null, lock_profit: null, lock_at: null,
        lock_and_trail_profit: null, lock_and_trail_at: null, lock_and_trail_by: null,
        overall_reentry_on_sl: null, overall_reentry_on_target: null,
      },
    }),
  },
  {
    label: "Iron Condor",
    description: "Sell OTM call spread + sell OTM put spread. Range-bound strategy.",
    tag: "iron-condor",
    build: (symbol) => ({
      version: 1,
      timeframe: "5m",
      instrument: { symbol, exchange: "NSE", segment: "index" },
      variables: [],
      indicators: [],
      entry: { logic: "ALL", conditions: [] },
      exit: null,
      risk: { stop_loss_pct: null, target_pct: null, trailing_sl_pct: null },
      position: { direction: "both", quantity_type: "fixed", quantity: 1, capital_pct: null },
      strategy_type: "intraday",
      legs: [
        { action: "sell", option_type: "CE", strike_offset: 200, expiry: null, expiry_formula: "current_expiry" },
        { action: "buy", option_type: "CE", strike_offset: 400, expiry: null, expiry_formula: "current_expiry" },
        { action: "sell", option_type: "PE", strike_offset: 200, expiry: null, expiry_formula: "current_expiry" },
        { action: "buy", option_type: "PE", strike_offset: 400, expiry: null, expiry_formula: "current_expiry" },
      ],
      overall: {
        overall_sl: 1500, overall_target: null, overall_trail_sl: null,
        overall_trail_every: null, lock_profit: null, lock_at: null,
        lock_and_trail_profit: null, lock_and_trail_at: null, lock_and_trail_by: null,
        overall_reentry_on_sl: null, overall_reentry_on_target: null,
      },
    }),
  },
  {
    label: "Bull Call Spread",
    description: "Buy ATM call, sell OTM call. Limited risk, limited reward.",
    tag: "bull-call",
    build: (symbol) => ({
      version: 1,
      timeframe: "5m",
      instrument: { symbol, exchange: "NSE", segment: "index" },
      variables: [],
      indicators: [],
      entry: { logic: "ALL", conditions: [] },
      exit: null,
      risk: { stop_loss_pct: null, target_pct: null, trailing_sl_pct: null },
      position: { direction: "long_only", quantity_type: "fixed", quantity: 1, capital_pct: null },
      strategy_type: "intraday",
      legs: [
        { action: "buy", option_type: "CE", strike_offset: 0, expiry: null, expiry_formula: "current_expiry" },
        { action: "sell", option_type: "CE", strike_offset: 300, expiry: null, expiry_formula: "current_expiry" },
      ],
    }),
  },
  {
    label: "Bear Put Spread",
    description: "Buy ATM put, sell OTM put. Profit when price falls.",
    tag: "bear-put",
    build: (symbol) => ({
      version: 1,
      timeframe: "5m",
      instrument: { symbol, exchange: "NSE", segment: "index" },
      variables: [],
      indicators: [],
      entry: { logic: "ALL", conditions: [] },
      exit: null,
      risk: { stop_loss_pct: null, target_pct: null, trailing_sl_pct: null },
      position: { direction: "long_only", quantity_type: "fixed", quantity: 1, capital_pct: null },
      strategy_type: "intraday",
      legs: [
        { action: "buy", option_type: "PE", strike_offset: 0, expiry: null, expiry_formula: "current_expiry" },
        { action: "sell", option_type: "PE", strike_offset: 300, expiry: null, expiry_formula: "current_expiry" },
      ],
    }),
  },
];

const INSTANT_SYMBOLS = [
  { value: "NIFTY", label: "NIFTY" },
  { value: "BANKNIFTY", label: "BANKNIFTY" },
  { value: "FINNIFTY", label: "FINNIFTY" },
  { value: "SENSEX", label: "SENSEX" },
];

const NL_EXAMPLES = [
  "Buy ATM straddle on NIFTY at 9:20 and square off at 15:15",
  "Sell iron condor on BANKNIFTY every Tuesday expiry",
  "Buy call when RSI(14) < 30 on NIFTY 5m chart",
  "Short straddle on NIFTY when IV > 30%",
];

function fmtMoney(v: number): string {
  return v.toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

function MetricPill({ label, value, tone }: { label: string; value: string; tone?: "green" | "red" | "slate" }) {
  const cls = tone === "green" ? "text-emerald-600" : tone === "red" ? "text-red-600" : "text-slate-800";
  return (
    <div className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-center">
      <p className="text-[10px] uppercase tracking-wide text-slate-400">{label}</p>
      <p className={`mt-0.5 text-sm font-semibold tabular-nums ${cls}`}>{value}</p>
    </div>
  );
}

export default function AIBuilderPage() {
  const auth = useAuth();
  const [symbol, setSymbol] = useState("NIFTY");
  const [prompt, setPrompt] = useState("");
  const [drafting, setDrafting] = useState(false);
  const [draft, setDraft] = useState<AiDraftResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedStrategy, setSavedStrategy] = useState<Strategy | null>(null);
  const [instantBusy, setInstantBusy] = useState<string | null>(null);
  const [backtesting, setBacktesting] = useState(false);
  const [backtestRun, setBacktestRun] = useState<BacktestRun | null>(null);
  const [backtestError, setBacktestError] = useState<string | null>(null);
  const [showDeployModal, setShowDeployModal] = useState<"paper" | "live" | null>(null);

  async function saveAndBacktest(strategyBody: object) {
    setSaving(true);
    try {
      const strategy = await api<Strategy>("/strategies", {
        method: "POST",
        body: JSON.stringify(strategyBody),
      });
      setSavedStrategy(strategy);

      setBacktesting(true);
      setBacktestError(null);
      setBacktestRun(null);
      try {
        const today = new Date();
        const end = today.toISOString().slice(0, 10);
        const start = new Date(today.getTime() - 30 * 86400000).toISOString().slice(0, 10);
        const run = await api<BacktestRun>("/backtests", {
          method: "POST",
          body: JSON.stringify({
            strategy_id: strategy.id,
            start,
            end,
            initial_capital: 1_000_000,
            costs_pct: 0.05,
            slippage_pct: 0,
          }),
        });
        setBacktestRun(run);
      } catch (e) {
        setBacktestError(e instanceof Error ? e.message : "Backtest failed");
      } finally {
        setBacktesting(false);
      }
    } finally {
      setSaving(false);
    }
  }

  function runDraft() {
    if (!prompt.trim() || drafting) return;
    setDrafting(true);
    setError(null);
    setDraft(null);
    setSavedStrategy(null);
    setBacktestRun(null);
    setBacktestError(null);
    api<AiDraftResponse>("/ai/draft-strategy", {
      method: "POST",
      body: JSON.stringify({ prompt: prompt.trim() }),
    })
      .then((d) => { setDraft(d); setDrafting(false); })
      .catch((e: Error) => { setError(e.message); setDrafting(false); });
  }

  function saveDraft() {
    if (!draft || !draft.valid || saving) return;
    const def = draft.definition as unknown as StrategyDefinitionV1;
    saveAndBacktest({
      name: `AI — ${prompt.trim().slice(0, 60)}`,
      description: `Drafted from: "${prompt.trim()}"`,
      underlying: def.instrument?.symbol ?? symbol,
      exchange: def.instrument?.exchange ?? "NSE",
      instrument: def.instrument?.segment ?? "index",
      strategy_type: def.strategy_type ?? "intraday",
      tags: ["ai-draft"],
      definition: def,
    });
  }

  async function saveInstant(inst: (typeof INSTANT_STRATEGIES)[0]) {
    setInstantBusy(inst.tag);
    setSavedStrategy(null);
    setBacktestRun(null);
    setBacktestError(null);
    try {
      await saveAndBacktest({
        name: `${inst.label} — ${symbol}`,
        description: inst.description,
        underlying: symbol,
        exchange: "NSE",
        instrument: "index",
        strategy_type: "intraday",
        tags: ["instant", inst.tag],
        definition: inst.build(symbol),
      });
    } finally {
      setInstantBusy(null);
    }
  }

  if (!auth.loading && !auth.user) {
    return <p className="text-sm text-slate-500">Connecting to the API…</p>;
  }
  if (auth.loading) {
    return <p className="text-sm text-slate-500">Loading…</p>;
  }

  const results = backtestRun?.result_summary as BacktestResults | null | undefined;
  const s = results?.summary ?? null;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Signals AI</h2>
        <p className="mt-1 text-sm text-slate-500">
          Describe a strategy in plain English, or pick a pre-built options preset — then
          backtest it instantly and deploy with one click.
        </p>
      </div>

      {/* Symbol selector */}
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-xs font-medium text-slate-500">Symbol:</span>
        {INSTANT_SYMBOLS.map((sy) => (
          <button
            key={sy.value}
            onClick={() => setSymbol(sy.value)}
            className={`rounded-md border px-3 py-1 text-xs font-medium transition-colors ${
              symbol === sy.value
                ? "border-blue-300 bg-blue-50 text-blue-700"
                : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
            }`}
          >
            {sy.label}
          </button>
        ))}
      </div>

      {/* Instant strategies grid */}
      <Card title="Instant strategies" subtitle="One-click presets — pick a symbol above, then save and backtest instantly.">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {INSTANT_STRATEGIES.map((inst) => (
            <button
              key={inst.tag}
              onClick={() => saveInstant(inst)}
              disabled={instantBusy !== null}
              className="group flex flex-col gap-2 rounded-xl border border-slate-200 bg-white p-4 text-left transition-all hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-sm disabled:opacity-50"
            >
              <span className="flex items-center justify-between">
                <h4 className="text-[13px] font-semibold text-slate-900 group-hover:text-blue-700">
                  {inst.label}
                </h4>
                {instantBusy === inst.tag ? (
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
                ) : (
                  <svg className="h-4 w-4 text-slate-400 group-hover:text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                  </svg>
                )}
              </span>
              <p className="text-[11px] leading-relaxed text-slate-500">{inst.description}</p>
              <span className="mt-auto text-[10px] text-slate-400">{symbol} · {symbol === "SENSEX" ? "Thu" : "Tue"} expiry</span>
            </button>
          ))}
        </div>
      </Card>

      {/* NL Prompt */}
      <Card title="Or describe it in plain English">
        <div className="mb-2 flex flex-wrap gap-2">
          <span className="text-[11px] text-slate-400">Try:</span>
          {NL_EXAMPLES.map((ex) => (
            <button
              key={ex}
              onClick={() => setPrompt(ex)}
              className="rounded-full border border-slate-200 px-2.5 py-0.5 text-[11px] text-slate-500 hover:bg-slate-50"
            >
              {ex.length > 50 ? `${ex.slice(0, 50)}…` : ex}
            </button>
          ))}
        </div>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={3}
          placeholder={`e.g. "Buy ATM straddle on ${symbol} at 9:20, square off at 15:15"`}
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
        />
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            onClick={runDraft}
            disabled={drafting || !prompt.trim()}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {drafting ? "Drafting…" : "Generate & backtest"}
          </button>
          {error && <p className="text-xs text-red-600">{error}</p>}
        </div>
      </Card>

      {/* Draft result */}
      {draft && (
        <Card
          title="Draft result"
          actions={
            <div className="flex items-center gap-2">
              <Badge tone={draft.source === "llm" ? "blue" : "amber"}>
                {draft.source === "llm" ? "LLM" : "rule-based"}
              </Badge>
              <Badge tone={draft.valid ? "green" : "red"}>{draft.valid ? "valid" : "invalid"}</Badge>
            </div>
          }
        >
          {draft.errors.length > 0 && (
            <div className="mb-3 rounded-lg border border-red-200 bg-red-50 p-3">
              <p className="text-xs font-semibold text-red-700">Validation errors</p>
              <ul className="mt-1 list-inside list-disc text-xs text-red-600">
                {draft.errors.map((e) => <li key={e}>{e}</li>)}
              </ul>
            </div>
          )}
          {draft.warnings.length > 0 && (
            <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 p-3">
              <p className="text-xs font-semibold text-amber-700">Warnings</p>
              <ul className="mt-1 list-inside list-disc text-xs text-amber-700">
                {draft.warnings.map((w) => <li key={w}>{w}</li>)}
              </ul>
            </div>
          )}
          <pre className="max-h-64 overflow-auto rounded-lg bg-slate-900 p-3 text-[11px] leading-relaxed text-slate-100">
            {JSON.stringify(draft.definition, null, 2)}
          </pre>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button
              onClick={saveDraft}
              disabled={!draft.valid || saving || backtesting}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
            >
              {saving ? "Saving & backtesting…" : "Save & backtest"}
            </button>
            <Link
              href="/builder/legs"
              className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Edit in Leg Builder
            </Link>
          </div>
        </Card>
      )}

      {/* Backtest results */}
      {(backtesting || backtestRun || backtestError) && (
        <Card
          title={
            backtesting
              ? "Running backtest…"
              : backtestError
                ? "Backtest failed"
                : `Backtest result — ${symbol}`
          }
          actions={
            backtestRun && (
              <Badge tone={backtestRun.status === "completed" ? "green" : "red"}>
                {backtestRun.status}
              </Badge>
            )
          }
        >
          {backtesting && (
            <div className="flex items-center gap-2 py-4">
              <span className="h-5 w-5 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
              <span className="text-sm text-slate-500">Running 30-day backtest…</span>
            </div>
          )}

          {backtestError && (
            <p className="text-xs text-red-600">{backtestError}</p>
          )}

          {s && (
            <>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
                <MetricPill label="Net P&L" value={`${s.net_pnl >= 0 ? "+" : ""}${fmtMoney(s.net_pnl)}`} tone={s.net_pnl >= 0 ? "green" : "red"} />
                <MetricPill label="Return" value={`${s.return_pct >= 0 ? "+" : ""}${s.return_pct}%`} tone={s.return_pct >= 0 ? "green" : "red"} />
                <MetricPill label="Win rate" value={`${s.win_rate}%`} />
                <MetricPill label="Trades" value={`${s.total_trades}`} />
                <MetricPill label="Profit factor" value={`${s.profit_factor}`} />
                <MetricPill label="Max DD" value={`${s.max_drawdown_pct}%`} tone="red" />
                <MetricPill label="Costs" value={fmtMoney(s.total_costs)} />
              </div>

              {savedStrategy && (
                <div className="mt-4 flex flex-wrap items-center gap-2">
                  <span className="text-xs text-slate-500">
                    Saved as <strong>{savedStrategy.name}</strong>
                  </span>
                  <Link
                    href={`/backtest?strategy=${savedStrategy.id}`}
                    className="text-xs text-indigo-600 hover:underline"
                  >
                    Full backtest →
                  </Link>
                  <button
                    onClick={() => setShowDeployModal("paper")}
                    className="rounded-md border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                  >
                    Deploy paper
                  </button>
                  <button
                    onClick={() => setShowDeployModal("live")}
                    className="rounded-md bg-blue-600 px-3 py-1 text-xs font-semibold text-white hover:bg-blue-700"
                  >
                    Deploy live
                  </button>
                </div>
              )}
            </>
          )}
        </Card>
      )}

      {showDeployModal && savedStrategy && (
        <DeployModal
          strategy={savedStrategy}
          mode={showDeployModal}
          onClose={() => setShowDeployModal(null)}
          onDeployed={() => {
            setShowDeployModal(null);
          }}
        />
      )}

      <p className="text-xs text-slate-400">
        Without an LLM key the server uses its deterministic rule-based parser. AI drafts
        are always suggestions — review the definition before deploying.
      </p>
    </div>
  );
}
