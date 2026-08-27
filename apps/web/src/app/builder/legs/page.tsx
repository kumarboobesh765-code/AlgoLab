"use client";

import React from "react";
import { useEffect, useMemo, useState } from "react";
import {
  api,
  type OptionChain,
  type OptionChainRow,
  type Instrument,
  type Strategy,
  type BacktestRun,
} from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { MetricCard } from "@/components/ui/MetricCard";
import { PayoffChart, inr, fmt } from "@/components/charts/PayoffChart";

const UNDERLYINGS = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"];
const STRIKE_STEPS: Record<string, number> = {
  NIFTY: 50,
  BANKNIFTY: 100,
  FINNIFTY: 50,
  MIDCPNIFTY: 75,
  SENSEX: 100,
};

type Action = "buy" | "sell";
type OptType = "CE" | "PE";
type SlMode = "pts" | "%" | "underlying_pts" | "underlying_pct";
type ReentryMode = "asap" | "asap_reverse" | "cost" | "cost_reverse" | "momentum" | "momentum_reverse" | "lazy_leg";

interface Leg {
  id: string;
  action: Action;
  optType: OptType;
  offset: number;
  lots: number;
  // Per-leg SL
  slMode: SlMode | "";
  slValue: string;
  // Per-leg Target
  targetMode: SlMode | "";
  targetValue: string;
  // Trail SL
  trailMode: "" | "pts" | "%";
  trailStep: string;
  trailBy: string;
  // Re-entry
  reentryOnSl: "" | ReentryMode;
  reentryOnTarget: "" | ReentryMode;
  maxReentries: string;
  // Square-off
  squareOff: "partial" | "complete";
}

function mkLeg(action: Action, optType: OptType, offset: number, lots = 1): Leg {
  return {
    id: `l_${Math.random().toString(36).slice(2, 8)}`,
    action, optType, offset, lots,
    slMode: "", slValue: "",
    targetMode: "", targetValue: "",
    trailMode: "", trailStep: "", trailBy: "",
    reentryOnSl: "", reentryOnTarget: "", maxReentries: "0",
    squareOff: "partial",
  };
}

interface LegPreset {
  name: string;
  legs: { action: Action; optType: OptType; offset: number }[];
}

const PRESETS: LegPreset[] = [
  { name: "Long Straddle", legs: [{ action: "buy", optType: "CE", offset: 0 }, { action: "buy", optType: "PE", offset: 0 }] },
  { name: "Short Straddle", legs: [{ action: "sell", optType: "CE", offset: 0 }, { action: "sell", optType: "PE", offset: 0 }] },
  { name: "Bull Call Spread", legs: [{ action: "buy", optType: "CE", offset: 0 }, { action: "sell", optType: "CE", offset: 1 }] },
  { name: "Bear Put Spread", legs: [{ action: "buy", optType: "PE", offset: 0 }, { action: "sell", optType: "PE", offset: -1 }] },
  { name: "Bull Put Spread", legs: [{ action: "sell", optType: "PE", offset: -1 }, { action: "buy", optType: "PE", offset: -2 }] },
  { name: "Iron Condor", legs: [{ action: "sell", optType: "CE", offset: 1 }, { action: "sell", optType: "PE", offset: -1 }, { action: "buy", optType: "CE", offset: 2 }, { action: "buy", optType: "PE", offset: -2 }] },
  { name: "Iron Butterfly", legs: [{ action: "sell", optType: "CE", offset: 0 }, { action: "sell", optType: "PE", offset: 0 }, { action: "buy", optType: "CE", offset: 1 }, { action: "buy", optType: "PE", offset: -1 }] },
  { name: "Call Butterfly", legs: [{ action: "buy", optType: "CE", offset: -1 }, { action: "sell", optType: "CE", offset: 0 }, { action: "sell", optType: "CE", offset: 0 }, { action: "buy", optType: "CE", offset: 1 }] },
];

function offsetLabel(o: number): string {
  return o === 0 ? "ATM" : o > 0 ? `ATM+${o}` : `ATM${o}`;
}

const SL_MODES: { value: SlMode; label: string }[] = [
  { value: "pts", label: "Premium Pts" },
  { value: "%", label: "Premium %" },
  { value: "underlying_pts", label: "Underlying Pts" },
  { value: "underlying_pct", label: "Underlying %" },
];

const REENTRY_MODES: { value: ReentryMode; label: string }[] = [
  { value: "asap", label: "RE-ASAP (same dir)" },
  { value: "asap_reverse", label: "RE-ASAP Reverse" },
  { value: "cost", label: "RE-COST (at entry)" },
  { value: "cost_reverse", label: "RE-COST Reverse" },
  { value: "momentum", label: "RE-Momentum" },
  { value: "momentum_reverse", label: "RE-Momentum Reverse" },
  { value: "lazy_leg", label: "Lazy Leg" },
];

interface ResolvedLeg extends Leg {
  strike: number;
  premium: number;
  delta: number;
}

function resolveLegs(legs: Leg[], chain: OptionChain | null, step: number, atm: number): ResolvedLeg[] {
  const rows = new Map<number, OptionChainRow>();
  chain?.strikes.forEach((r) => rows.set(r.strike, r));
  return legs.map((l) => {
    const strike = Math.round(atm + l.offset * step);
    const row = rows.get(strike);
    const premium = l.optType === "CE" ? (row?.call_ltp ?? 50) : (row?.put_ltp ?? 50);
    const delta = l.optType === "CE" ? (row?.call_delta ?? 0.5) : (row?.put_delta ?? -0.5);
    return { ...l, strike, premium, delta };
  });
}

function buildCurve(legs: ResolvedLeg[], spot: number, lotSize: number) {
  if (!spot) return [] as { price: number; pnl: number }[];
  const lo = spot - 600;
  const hi = spot + 600;
  const n = 49;
  const out: { price: number; pnl: number }[] = [];
  for (let i = 0; i <= n; i++) {
    const S = lo + ((hi - lo) * i) / n;
    let pnl = 0;
    for (const l of legs) {
      const intrinsic = l.optType === "CE" ? Math.max(S - l.strike, 0) : Math.max(l.strike - S, 0);
      const perUnit = l.action === "buy" ? intrinsic - l.premium : l.premium - intrinsic;
      pnl += perUnit * lotSize * l.lots;
    }
    out.push({ price: S, pnl: Math.round(pnl) });
  }
  return out;
}

export default function LegBuilderPage() {
  const [underlying, setUnderlying] = useState("NIFTY");
  const [chain, setChain] = useState<OptionChain | null>(null);
  const [chainError, setChainError] = useState<string | null>(null);
  const [expiry, setExpiry] = useState<string>("");
  const [legs, setLegs] = useState<Leg[]>([mkLeg("buy", "CE", 0), mkLeg("sell", "CE", 1)]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [savedId, setSavedId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [run, setRun] = useState<BacktestRun | null>(null);
  const [saved, setSaved] = useState<Strategy[]>([]);
  const [lotSizes, setLotSizes] = useState<Record<string, number>>({});
  const [chainFor, setChainFor] = useState(underlying);
  const [expandedLeg, setExpandedLeg] = useState<string | null>(null);

  // Overall settings
  const [overallSl, setOverallSl] = useState("");
  const [overallTarget, setOverallTarget] = useState("");
  const [overallTrailSl, setOverallTrailSl] = useState("");
  const [overallTrailEvery, setOverallTrailEvery] = useState("");
  const [lockProfit, setLockProfit] = useState("");
  const [lockAt, setLockAt] = useState("");
  const [lockTrailProfit, setLockTrailProfit] = useState("");
  const [lockTrailAt, setLockTrailAt] = useState("");
  const [lockTrailBy, setLockTrailBy] = useState("");

  // Entry momentum
  const [momentumEnabled, setMomentumEnabled] = useState(false);
  const [momentumDir, setMomentumDir] = useState<"up" | "down">("up");
  const [momentumMode, setMomentumMode] = useState<"pts" | "%">("pts");
  const [momentumValue, setMomentumValue] = useState("");

  // Time controls
  const [noEntryAfter, setNoEntryAfter] = useState("");
  const [noReentryAfter, setNoReentryAfter] = useState("");
  const [timeExit, setTimeExit] = useState("");

  // Legwise
  const [trailToBreakeven, setTrailToBreakeven] = useState<"none" | "sl_legs" | "all_legs">("none");
  const [squareOffOnLegSl, setSquareOffOnLegSl] = useState(false);

  if (chainFor !== underlying) {
    setChainFor(underlying);
    setChain(null);
    setChainError(null);
  }

  const step = STRIKE_STEPS[underlying] ?? 50;

  useEffect(() => {
    let cancelled = false;
    api<Instrument[]>("/market/instruments")
      .then((list) => {
        if (!cancelled) setLotSizes(Object.fromEntries(list.map((i) => [i.symbol.toUpperCase(), i.lot_size])));
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    api<OptionChain>(`/market/option-chain?underlying=${underlying}`)
      .then((c) => {
        if (!cancelled) {
          setChain(c);
          setExpiry(c.expiry);
        }
      })
      .catch(() => {
        if (!cancelled) setChainError("Could not load option chain (mock mode needs the API or mock layer).");
      });
    return () => { cancelled = true; };
  }, [underlying]);

  useEffect(() => {
    let cancelled = false;
    api<Strategy[]>("/strategies")
      .then((list) => {
        if (!cancelled) setSaved(list.filter((s) => (s.definition as { builder?: string } | null)?.builder === "legs"));
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [savedId]);

  const atm = useMemo(() => {
    if (!chain || chain.strikes.length === 0) return 0;
    let best = chain.strikes[0].strike;
    let bestD = Infinity;
    for (const r of chain.strikes) {
      const d = Math.abs(r.strike - chain.spot);
      if (d < bestD) { bestD = d; best = r.strike; }
    }
    return best;
  }, [chain]);

  const resolved = useMemo(() => resolveLegs(legs, chain, step, atm), [legs, chain, step, atm]);
  const spot = chain?.spot ?? 0;
  const lotSize = lotSizes[underlying] ?? 50;
  const curve = useMemo(() => buildCurve(resolved, spot, lotSize), [resolved, spot, lotSize]);

  const metrics = useMemo(() => {
    if (curve.length === 0) return null;
    const pnls = curve.map((c) => c.pnl);
    const maxProfit = Math.max(...pnls);
    const maxLoss = Math.min(...pnls);
    const breakevens: number[] = [];
    for (let i = 1; i < curve.length; i++) {
      const a = curve[i - 1];
      const b = curve[i];
      if ((a.pnl <= 0 && b.pnl > 0) || (a.pnl > 0 && b.pnl <= 0)) {
        const t = a.pnl / (a.pnl - b.pnl);
        breakevens.push(Math.round(a.price + t * (b.price - a.price)));
      }
    }
    let netPremium = 0;
    let netDelta = 0;
    for (const l of resolved) {
      const sign = l.action === "buy" ? 1 : -1;
      netPremium += sign * l.premium * lotSize * l.lots;
      netDelta += sign * l.delta * l.lots;
    }
    return { maxProfit, maxLoss, breakevens, netPremium, netDelta };
  }, [curve, resolved, lotSize]);

  const patchLeg = (id: string, patch: Partial<Leg>) =>
    setLegs((prev) => prev.map((l) => (l.id === id ? { ...l, ...patch } : l)));
  const removeLeg = (id: string) => setLegs((prev) => prev.filter((l) => l.id !== id));
  const addLeg = () => setLegs((prev) => [...prev, mkLeg("buy", "CE", 0)]);
  const applyPreset = (p: LegPreset) => {
    setLegs(p.legs.map((l) => mkLeg(l.action, l.optType, l.offset)));
    setRun(null);
    setMessage(null);
  };

  const buildDefinition = () => ({
    version: 1 as const,
    timeframe: "1m",
    builder: "legs",
    instrument: { symbol: underlying, exchange: "NSE", segment: "options" as const },
    underlying,
    expiry: chain?.expiry ?? null,
    legs: resolved.map((l) => ({
      action: l.action,
      option_type: l.optType,
      strike_offset: l.offset,
      strike: l.strike,
      lots: l.lots,
      premium: l.premium,
      ...(l.slMode && l.slValue ? { sl_mode: l.slMode, sl_value: Number(l.slValue) } : {}),
      ...(l.targetMode && l.targetValue ? { target_mode: l.targetMode, target_value: Number(l.targetValue) } : {}),
      ...(l.trailMode && l.trailStep ? { trail_mode: l.trailMode, trail_step: Number(l.trailStep), trail_by: Number(l.trailBy) || undefined } : {}),
      ...(l.reentryOnSl ? { reentry_on_sl: l.reentryOnSl, max_reentries: Number(l.maxReentries) } : {}),
      ...(l.reentryOnTarget ? { reentry_on_target: l.reentryOnTarget, max_reentries: Number(l.maxReentries) } : {}),
      square_off: l.squareOff,
    })),
    entry: { logic: "ALL" as const, conditions: [{ left: { kind: "price" as const, price: "close" }, op: "GT", right: { kind: "constant" as const, value: 0 } }] },
    exit: { logic: "ALL" as const, conditions: [{ left: { kind: "price" as const, price: "close" }, op: "GT", right: { kind: "constant" as const, value: 0 } }] },
    position: { quantity_type: "fixed" as const, quantity: 1, direction: "long_only" as const },
    risk: null,
    overall: {
      overall_sl: overallSl ? Number(overallSl) : null,
      overall_target: overallTarget ? Number(overallTarget) : null,
      overall_trail_sl: overallTrailSl ? Number(overallTrailSl) : null,
      overall_trail_every: overallTrailEvery ? Number(overallTrailEvery) : null,
      lock_profit: lockProfit ? Number(lockProfit) : null,
      lock_at: lockAt ? Number(lockAt) : null,
      lock_and_trail_profit: lockTrailProfit ? Number(lockTrailProfit) : null,
      lock_and_trail_at: lockTrailAt ? Number(lockTrailAt) : null,
      lock_and_trail_by: lockTrailBy ? Number(lockTrailBy) : null,
    },
    entry_momentum: momentumEnabled ? { enabled: true, direction: momentumDir, mode: momentumMode, value: Number(momentumValue) || 0 } : null,
    time_control: {
      no_entry_after: noEntryAfter || null,
      no_reentry_after: noReentryAfter || null,
      time_exit: timeExit || null,
    },
    legwise: { trail_sl_to_breakeven: trailToBreakeven, square_off_on_leg_sl: squareOffOnLegSl },
  });

  const doSave = async (): Promise<string> => {
    if (savedId) return savedId;
    const created = await api<Strategy>("/strategies", {
      method: "POST",
      body: JSON.stringify({
        name: name.trim() || "Untitled Leg Strategy",
        description: description.trim(),
        exchange: "NSE",
        underlying,
        instrument: "options",
        strategy_type: "options",
        tags: ["options", "legs"],
        definition: buildDefinition(),
      }),
    });
    setSavedId(created.id);
    return created.id;
  };

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const id = await doSave();
      setMessage(`Saved "${name.trim() || "Untitled Leg Strategy"}" (id ${id.slice(0, 8)}).`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const backtest = async () => {
    setBusy(true);
    setError(null);
    try {
      const id = await doSave();
      const r = await api<BacktestRun>("/backtests", {
        method: "POST",
        body: JSON.stringify({ strategy_id: id, initial_capital: 100000, costs_pct: 0.05 }),
      });
      setRun(r);
      setMessage(`Backtest complete — return ${(r.result_summary?.summary.return_pct ?? 0).toFixed(2)}%.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Backtest failed");
    } finally {
      setBusy(false);
    }
  };

  const s = run?.result_summary?.summary ?? null;

  return (
    <div className="space-y-4">
      <Card
        title="Leg Builder"
        subtitle="Compose multi-leg options strategies — spreads, straddles, condors with per-leg risk management."
        actions={
          <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600 ring-1 ring-inset ring-slate-200">
            {chain ? `Spot ${fmt(spot)} · ${underlying}` : "Loading chain…"}
          </span>
        }
      >
        <div className="grid gap-3 md:grid-cols-2">
          <label className="block text-xs font-medium text-slate-500">
            Underlying
            <select value={underlying} onChange={(e) => setUnderlying(e.target.value)} className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800">
              {UNDERLYINGS.map((u) => <option key={u}>{u}</option>)}
            </select>
          </label>
          <label className="block text-xs font-medium text-slate-500">
            Expiry
            <select value={expiry} onChange={(e) => setExpiry(e.target.value)} className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800">
              {chain?.expiries.map((e) => <option key={e} value={e}>{e}</option>)}
            </select>
          </label>
          <label className="block text-xs font-medium text-slate-500">
            Strategy name
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. NIFTY Bull Call Spread" className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800" />
          </label>
        </div>
        <label className="mt-3 block text-xs font-medium text-slate-500">
          Description
          <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Optional notes" className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800" />
        </label>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Presets</span>
          {PRESETS.map((p) => (
            <button key={p.name} onClick={() => applyPreset(p)} className="rounded-full border border-slate-200 px-2.5 py-1 text-[11px] font-medium text-slate-600 transition-colors hover:bg-slate-50">{p.name}</button>
          ))}
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <button onClick={save} disabled={busy} className="rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-60">
            {busy ? "Working…" : "Save strategy"}
          </button>
          <button onClick={backtest} disabled={busy} className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-50 disabled:opacity-60">
            Backtest
          </button>
        </div>
        {message && <p className="mt-2 text-xs text-emerald-600">{message}</p>}
        {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
        {chainError && <p className="mt-2 text-xs text-amber-600">{chainError}</p>}
      </Card>

      <Card title="Legs" subtitle="Each leg is a buy/sell of a call or put at a strike offset from ATM. Click a leg to expand SL/Target/Re-entry settings.">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-[11px] uppercase tracking-wide text-slate-400">
                <th className="py-2 pr-2">#</th>
                <th className="py-2 pr-2">Action</th>
                <th className="py-2 pr-2">Type</th>
                <th className="py-2 pr-2">Strike</th>
                <th className="py-2 pr-2">Lots</th>
                <th className="py-2 pr-2 text-right">Premium</th>
                <th className="py-2 pr-2 text-right">Δ</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody>
              {legs.map((l, i) => (
                <React.Fragment key={l.id}>
                  <tr className="border-b border-slate-50 cursor-pointer hover:bg-slate-50/50" onClick={() => setExpandedLeg(expandedLeg === l.id ? null : l.id)}>
                    <td className="py-2 pr-2 text-slate-400">{i + 1}</td>
                    <td className="py-2 pr-2" onClick={(e) => e.stopPropagation()}>
                      <select value={l.action} onChange={(e) => patchLeg(l.id, { action: e.target.value as Action })} className="rounded border border-slate-300 px-1.5 py-1 text-xs text-slate-800">
                        <option value="buy">Buy</option>
                        <option value="sell">Sell</option>
                      </select>
                    </td>
                    <td className="py-2 pr-2" onClick={(e) => e.stopPropagation()}>
                      <select value={l.optType} onChange={(e) => patchLeg(l.id, { optType: e.target.value as OptType })} className="rounded border border-slate-300 px-1.5 py-1 text-xs text-slate-800">
                        <option value="CE">CE</option>
                        <option value="PE">PE</option>
                      </select>
                    </td>
                    <td className="py-2 pr-2" onClick={(e) => e.stopPropagation()}>
                      <select value={l.offset} onChange={(e) => patchLeg(l.id, { offset: Number(e.target.value) })} className="rounded border border-slate-300 px-1.5 py-1 text-xs text-slate-800">
                        {Array.from({ length: 11 }, (_, k) => k - 5).map((o) => (
                          <option key={o} value={o}>{offsetLabel(o)}</option>
                        ))}
                      </select>
                    </td>
                    <td className="py-2 pr-2" onClick={(e) => e.stopPropagation()}>
                      <input type="number" min={1} value={l.lots} onChange={(e) => patchLeg(l.id, { lots: Math.max(1, Number(e.target.value)) })} className="w-16 rounded border border-slate-300 px-1.5 py-1 text-xs text-slate-800" />
                    </td>
                    <td className="py-2 pr-2 text-right tabular-nums text-slate-700">{fmt(resolved[i]?.premium)}</td>
                    <td className="py-2 pr-2 text-right tabular-nums text-slate-500">{fmt(resolved[i]?.delta, 3)}</td>
                    <td className="py-2 text-right" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center gap-1">
                        {(l.slMode || l.targetMode || l.reentryOnSl || l.reentryOnTarget) && (
                          <span className="text-[10px] text-blue-500">●</span>
                        )}
                        <button onClick={() => removeLeg(l.id)} disabled={legs.length <= 1} className="text-xs text-red-500 hover:underline disabled:opacity-30">Remove</button>
                      </div>
                    </td>
                  </tr>
                  {expandedLeg === l.id && (
                    <tr>
                      <td colSpan={8} className="border-b border-slate-100 bg-slate-50/50 px-4 py-3">
                        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                          {/* Stop Loss */}
                          <div>
                            <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">Stop Loss</p>
                            <div className="flex gap-1">
                              <select value={l.slMode} onChange={(e) => patchLeg(l.id, { slMode: e.target.value as SlMode | "" })} className="rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700">
                                <option value="">None</option>
                                {SL_MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                              </select>
                              {l.slMode && (
                                <input type="number" value={l.slValue} onChange={(e) => patchLeg(l.id, { slValue: e.target.value })} placeholder="Value" className="w-20 rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700" />
                              )}
                            </div>
                          </div>
                          {/* Target */}
                          <div>
                            <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">Target</p>
                            <div className="flex gap-1">
                              <select value={l.targetMode} onChange={(e) => patchLeg(l.id, { targetMode: e.target.value as SlMode | "" })} className="rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700">
                                <option value="">None</option>
                                {SL_MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                              </select>
                              {l.targetMode && (
                                <input type="number" value={l.targetValue} onChange={(e) => patchLeg(l.id, { targetValue: e.target.value })} placeholder="Value" className="w-20 rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700" />
                              )}
                            </div>
                          </div>
                          {/* Trail SL */}
                          <div>
                            <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">Trail SL</p>
                            <div className="flex gap-1">
                              <select value={l.trailMode} onChange={(e) => patchLeg(l.id, { trailMode: e.target.value as "" | "pts" | "%" })} className="rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700">
                                <option value="">None</option>
                                <option value="pts">Points</option>
                                <option value="%">Percent</option>
                              </select>
                              {l.trailMode && (
                                <>
                                  <input type="number" value={l.trailBy} onChange={(e) => patchLeg(l.id, { trailBy: e.target.value })} placeholder="For every" className="w-20 rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700" />
                                  <span className="self-center text-[10px] text-slate-400">→</span>
                                  <input type="number" value={l.trailStep} onChange={(e) => patchLeg(l.id, { trailStep: e.target.value })} placeholder="Move SL" className="w-20 rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700" />
                                </>
                              )}
                            </div>
                          </div>
                          {/* Re-Entry on SL */}
                          <div>
                            <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">Re-Entry on SL</p>
                            <div className="flex gap-1">
                              <select value={l.reentryOnSl} onChange={(e) => patchLeg(l.id, { reentryOnSl: e.target.value as "" | ReentryMode })} className="rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700">
                                <option value="">None</option>
                                {REENTRY_MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                              </select>
                              {l.reentryOnSl && (
                                <input type="number" min={0} max={20} value={l.maxReentries} onChange={(e) => patchLeg(l.id, { maxReentries: e.target.value })} placeholder="Max" className="w-14 rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700" />
                              )}
                            </div>
                          </div>
                          {/* Re-Entry on Target */}
                          <div>
                            <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">Re-Entry on Target</p>
                            <div className="flex gap-1">
                              <select value={l.reentryOnTarget} onChange={(e) => patchLeg(l.id, { reentryOnTarget: e.target.value as "" | ReentryMode })} className="rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700">
                                <option value="">None</option>
                                {REENTRY_MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                              </select>
                              {l.reentryOnTarget && (
                                <input type="number" min={0} max={20} value={l.maxReentries} onChange={(e) => patchLeg(l.id, { maxReentries: e.target.value })} placeholder="Max" className="w-14 rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700" />
                              )}
                            </div>
                          </div>
                          {/* Square Off */}
                          <div>
                            <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">Square Off</p>
                            <select value={l.squareOff} onChange={(e) => patchLeg(l.id, { squareOff: e.target.value as "partial" | "complete" })} className="rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700">
                              <option value="partial">Partial (this leg only)</option>
                              <option value="complete">Complete (all legs)</option>
                            </select>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
        <button onClick={addLeg} className="mt-3 rounded-md border border-dashed border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50">
          + Add leg
        </button>
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Payoff at expiry" subtitle="Net P&L across underlying prices." className="lg:col-span-2">
          {curve.length > 0 ? (
            <PayoffChart curve={curve} spot={spot} breakevens={metrics?.breakevens ?? []} />
          ) : (
            <p className="py-10 text-center text-sm text-slate-400">Loading option chain…</p>
          )}
        </Card>
        <Card title="Strategy metrics">
          {metrics ? (
            <div className="grid grid-cols-2 gap-3">
              <MetricCard label="Max Profit" value={inr(metrics.maxProfit)} tone="positive" />
              <MetricCard label="Max Loss" value={inr(metrics.maxLoss)} tone="negative" />
              <MetricCard label="Breakeven" value={metrics.breakevens.length ? metrics.breakevens.map((b) => fmt(b, 0)).join(" / ") : "—"} />
              <MetricCard label="Net Premium" value={inr(Math.abs(metrics.netPremium))} hint={metrics.netPremium < 0 ? "net debit" : "net credit"} tone={metrics.netPremium < 0 ? "negative" : "positive"} />
              <MetricCard label="Net Delta" value={fmt(metrics.netDelta, 3)} hint="directional bias" />
              <MetricCard label="Legs" value={String(legs.length)} />
            </div>
          ) : (
            <p className="py-6 text-center text-sm text-slate-400">—</p>
          )}
        </Card>
      </div>

      {/* Overall Strategy Settings */}
      <Card title="Overall Strategy Settings" subtitle="Strategy-level risk management in MTM (mark-to-market ₹) terms.">
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          <label className="block text-xs font-medium text-slate-500">
            Overall Stop Loss (₹)
            <input value={overallSl} onChange={(e) => setOverallSl(e.target.value)} placeholder="e.g. 5000" className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800" />
          </label>
          <label className="block text-xs font-medium text-slate-500">
            Overall Target (₹)
            <input value={overallTarget} onChange={(e) => setOverallTarget(e.target.value)} placeholder="e.g. 10000" className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800" />
          </label>
          <label className="block text-xs font-medium text-slate-500">
            Trail SL step (₹)
            <input value={overallTrailSl} onChange={(e) => setOverallTrailSl(e.target.value)} placeholder="e.g. 500" className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800" />
          </label>
          <label className="block text-xs font-medium text-slate-500">
            Trail every (₹)
            <input value={overallTrailEvery} onChange={(e) => setOverallTrailEvery(e.target.value)} placeholder="e.g. 1000" className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800" />
          </label>
          <label className="block text-xs font-medium text-slate-500">
            Lock Profit (₹)
            <input value={lockProfit} onChange={(e) => setLockProfit(e.target.value)} placeholder="e.g. 3000" className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800" />
          </label>
          <label className="block text-xs font-medium text-slate-500">
            Lock when MTM reaches (₹)
            <input value={lockAt} onChange={(e) => setLockAt(e.target.value)} placeholder="e.g. 5000" className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800" />
          </label>
          <label className="block text-xs font-medium text-slate-500">
            Lock &amp; Trail profit (₹)
            <input value={lockTrailProfit} onChange={(e) => setLockTrailProfit(e.target.value)} placeholder="e.g. 3000" className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800" />
          </label>
          <label className="block text-xs font-medium text-slate-500">
            Lock &amp; Trail at (₹)
            <input value={lockTrailAt} onChange={(e) => setLockTrailAt(e.target.value)} placeholder="e.g. 5000" className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800" />
          </label>
          <label className="block text-xs font-medium text-slate-500">
            Lock &amp; Trail by (₹)
            <input value={lockTrailBy} onChange={(e) => setLockTrailBy(e.target.value)} placeholder="e.g. 200" className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800" />
          </label>
        </div>
      </Card>

      {/* Entry Momentum */}
      <Card title="Entry Momentum" subtitle="Enter only when combined premium moves by X from strategy start.">
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs font-medium text-slate-500">
            <input type="checkbox" checked={momentumEnabled} onChange={(e) => setMomentumEnabled(e.target.checked)} className="rounded border-slate-300" />
            Enable
          </label>
          {momentumEnabled && (
            <>
              <select value={momentumDir} onChange={(e) => setMomentumDir(e.target.value as "up" | "down")} className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-700">
                <option value="up">Up ↑</option>
                <option value="down">Down ↓</option>
              </select>
              <select value={momentumMode} onChange={(e) => setMomentumMode(e.target.value as "pts" | "%")} className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-700">
                <option value="pts">Points</option>
                <option value="%">Percent</option>
              </select>
              <input type="number" value={momentumValue} onChange={(e) => setMomentumValue(e.target.value)} placeholder="Value" className="w-24 rounded border border-slate-300 px-2 py-1 text-xs text-slate-700" />
            </>
          )}
        </div>
      </Card>

      {/* Time Controls */}
      <Card title="Time Controls" subtitle="Restrict entries and exits by time of day.">
        <div className="grid gap-3 md:grid-cols-3">
          <label className="block text-xs font-medium text-slate-500">
            No Entry After
            <input type="time" value={noEntryAfter} onChange={(e) => setNoEntryAfter(e.target.value)} className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800" />
          </label>
          <label className="block text-xs font-medium text-slate-500">
            No Re-Entry After
            <input type="time" value={noReentryAfter} onChange={(e) => setNoReentryAfter(e.target.value)} className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800" />
          </label>
          <label className="block text-xs font-medium text-slate-500">
            Force Exit At
            <input type="time" value={timeExit} onChange={(e) => setTimeExit(e.target.value)} className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800" />
          </label>
        </div>
      </Card>

      {/* Legwise Settings */}
      <Card title="Legwise Settings" subtitle="Cross-leg interaction behavior when SL/Target hits.">
        <div className="flex flex-wrap items-center gap-6">
          <label className="block text-xs font-medium text-slate-500">
            Trail SL to Breakeven
            <select value={trailToBreakeven} onChange={(e) => setTrailToBreakeven(e.target.value as typeof trailToBreakeven)} className="mt-1 w-48 rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800">
              <option value="none">None</option>
              <option value="sl_legs">SL Legs only</option>
              <option value="all_legs">All Legs</option>
            </select>
          </label>
          <label className="flex items-center gap-2 text-xs font-medium text-slate-500">
            <input type="checkbox" checked={squareOffOnLegSl} onChange={(e) => setSquareOffOnLegSl(e.target.checked)} className="rounded border-slate-300" />
            Square off all legs on any leg SL hit
          </label>
        </div>
      </Card>

      {s && (
        <Card title="Backtest result" subtitle="Mock backtest of this leg strategy.">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
            <MetricCard label="Net P&L" value={inr(s.net_pnl)} tone={s.net_pnl >= 0 ? "positive" : "negative"} />
            <MetricCard label="Return" value={`${s.return_pct.toFixed(2)}%`} />
            <MetricCard label="Trades" value={String(s.total_trades)} />
            <MetricCard label="Win Rate" value={`${s.win_rate.toFixed(1)}%`} />
            <MetricCard label="Sharpe" value={s.sharpe_ratio.toFixed(2)} />
            <MetricCard label="Max DD" value={`${s.max_drawdown_pct.toFixed(2)}%`} tone="negative" />
          </div>
        </Card>
      )}

      <Card title="Saved leg strategies" subtitle="Strategies created with the Leg Builder.">
        {saved.length === 0 ? (
          <p className="py-4 text-center text-sm text-slate-400">No leg strategies yet — build one above and hit Save.</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {saved.map((st) => (
              <li key={st.id} className="flex items-center justify-between py-2">
                <div>
                  <p className="text-sm font-medium text-slate-800">{st.name}</p>
                  <p className="text-[11px] text-slate-400">{st.underlying} · {st.description || "—"}</p>
                </div>
                <Badge tone="blue">{st.status}</Badge>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
