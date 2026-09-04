"use client";

import React from "react";
import { useEffect, useMemo, useState } from "react";
import {
  api,
  type OptionChain,
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
  NIFTY: 50, BANKNIFTY: 100, FINNIFTY: 50, MIDCPNIFTY: 75, SENSEX: 100,
};

type Action = "buy" | "sell";
type OptType = "CE" | "PE";
type SlMode = "pts" | "%" | "underlying_pts" | "underlying_pct" | "delta";
type ExpiryType = "weekly" | "next_weekly" | "monthly" | "next_monthly";
type StrikeMode =
  | "strike_type" | "premium_ge" | "premium_le" | "premium_range"
  | "closest_premium" | "delta_range" | "straddle_width"
  | "atm_straddle_premium_pct" | "closest_delta" | "synthetic_future" | "pct_of_atm";
type MomentumDir = "up" | "down";
type MomentumUnit = "pts" | "%";
type TrailUnit = "pts" | "%";
type ReentryMode = "" | "asap" | "asap_reverse" | "cost" | "cost_reverse" | "momentum" | "momentum_reverse" | "lazy_leg" | "reexecute" | "reexecute_reverse" | "range_breakout";
type StrategyType = "intraday" | "btst" | "positional";
type TrailingMode = "none" | "lock" | "lock_and_trail";

interface Leg {
  id: string;
  action: Action;
  lots: number;
  optType: OptType;
  expiryType: ExpiryType;
  strikeMode: StrikeMode;
  strikeOffset: number;
  strikeValue: string;
  strikeValue2: string;
  targetEnabled: boolean;
  targetMode: SlMode;
  targetValue: string;
  slEnabled: boolean;
  slMode: SlMode;
  slValue: string;
  trailEnabled: boolean;
  trailUnit: TrailUnit;
  trailTrigger: string;
  trailBy: string;
  reentryOnSl: ReentryMode;
  reentryOnTarget: ReentryMode;
  maxReentries: string;
  momentumEnabled: boolean;
  momentumDir: MomentumDir;
  momentumUnit: MomentumUnit;
  momentumValue: string;
  rangeBreakoutEnabled: boolean;
}

function mkLeg(action: Action, optType: OptType, offset = 0): Leg {
  return {
    id: `l_${Math.random().toString(36).slice(2, 8)}`,
    action, lots: 1, optType, expiryType: "weekly",
    strikeMode: "strike_type", strikeOffset: offset, strikeValue: "", strikeValue2: "",
    targetEnabled: false, targetMode: "%", targetValue: "50",
    slEnabled: false, slMode: "%", slValue: "20",
    trailEnabled: false, trailUnit: "%", trailTrigger: "20", trailBy: "10",
    reentryOnSl: "", reentryOnTarget: "", maxReentries: "0",
    momentumEnabled: false, momentumDir: "up", momentumUnit: "%", momentumValue: "14",
    rangeBreakoutEnabled: false,
  };
}

interface LazyLeg {
  id: string;
  name: string;
  action: Action;
  lots: number;
  optType: OptType;
  expiryType: ExpiryType;
  strikeMode: StrikeMode;
  strikeOffset: number;
  strikeValue: string;
  strikeValue2: string;
  targetEnabled: boolean;
  targetMode: SlMode;
  targetValue: string;
  slEnabled: boolean;
  slMode: SlMode;
  slValue: string;
  trailEnabled: boolean;
  trailUnit: TrailUnit;
  trailTrigger: string;
  trailBy: string;
  reentryOnSl: ReentryMode;
  reentryOnTarget: ReentryMode;
  maxReentries: string;
  momentumEnabled: boolean;
  momentumDir: MomentumDir;
  momentumUnit: MomentumUnit;
  momentumValue: string;
}

function mkLazyLeg(name: string): LazyLeg {
  return {
    id: `ll_${Math.random().toString(36).slice(2, 8)}`,
    name, action: "buy", lots: 1, optType: "CE", expiryType: "weekly",
    strikeMode: "strike_type", strikeOffset: 0, strikeValue: "", strikeValue2: "",
    targetEnabled: true, targetMode: "%", targetValue: "40",
    slEnabled: true, slMode: "%", slValue: "15",
    trailEnabled: true, trailUnit: "%", trailTrigger: "20", trailBy: "15",
    reentryOnSl: "", reentryOnTarget: "", maxReentries: "0",
    momentumEnabled: true, momentumDir: "up", momentumUnit: "%", momentumValue: "160",
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
  { name: "Iron Condor", legs: [{ action: "sell", optType: "CE", offset: 1 }, { action: "sell", optType: "PE", offset: -1 }, { action: "buy", optType: "CE", offset: 2 }, { action: "buy", optType: "PE", offset: -2 }] },
  { name: "Iron Butterfly", legs: [{ action: "sell", optType: "CE", offset: 0 }, { action: "sell", optType: "PE", offset: 0 }, { action: "buy", optType: "CE", offset: 1 }, { action: "buy", optType: "PE", offset: -1 }] },
];

const SL_MODES: { value: SlMode; label: string }[] = [
  { value: "pts", label: "Points (Pts)" },
  { value: "%", label: "Percent (%)" },
  { value: "underlying_pts", label: "Underlying Pts" },
  { value: "underlying_pct", label: "Underlying %" },
  { value: "delta", label: "Delta (pts)" },
];

const STRIKE_MODES: { value: StrikeMode; label: string }[] = [
  { value: "strike_type", label: "Strike Type" },
  { value: "premium_ge", label: "Premium >=" },
  { value: "premium_le", label: "Premium <=" },
  { value: "premium_range", label: "Premium Range" },
  { value: "closest_premium", label: "Closest Premium" },
  { value: "delta_range", label: "Delta Range" },
  { value: "closest_delta", label: "Closest Delta" },
  { value: "straddle_width", label: "Straddle Width" },
  { value: "atm_straddle_premium_pct", label: "ATM Straddle Premium %" },
  { value: "synthetic_future", label: "Synthetic Future" },
  { value: "pct_of_atm", label: "% of ATM" },
];

const EXPIRY_OPTIONS: { value: ExpiryType; label: string }[] = [
  { value: "weekly", label: "Weekly" },
  { value: "next_weekly", label: "Next Weekly" },
  { value: "monthly", label: "Monthly" },
  { value: "next_monthly", label: "Next Monthly" },
];

const STRIKE_TYPE_OFFSETS = [
  { value: -11, label: "ITM11" }, { value: -10, label: "ITM10" }, { value: -9, label: "ITM9" },
  { value: -8, label: "ITM8" }, { value: -7, label: "ITM7" }, { value: -6, label: "ITM6" },
  { value: -5, label: "ITM5" }, { value: -4, label: "ITM4" }, { value: -3, label: "ITM3" },
  { value: -2, label: "ITM2" }, { value: -1, label: "ITM1" }, { value: 0, label: "ATM" },
  { value: 1, label: "OTM1" }, { value: 2, label: "OTM2" }, { value: 3, label: "OTM3" },
  { value: 4, label: "OTM4" }, { value: 5, label: "OTM5" }, { value: 6, label: "OTM6" },
  { value: 7, label: "OTM7" }, { value: 8, label: "OTM8" }, { value: 9, label: "OTM9" },
  { value: 10, label: "OTM10" }, { value: 11, label: "OTM11" },
];

interface ResolvedLeg {
  strike: number;
  premium: number;
  delta: number;
}

function resolveStrike(leg: Leg, chain: OptionChain | null, step: number, atm: number): ResolvedLeg {
  if (!chain) return { strike: atm, premium: 50, delta: 0.5 };
  const strikes = chain.strikes;
  if (leg.strikeMode === "strike_type") {
    const strike = atm + leg.strikeOffset * step;
    const row = strikes.find((r) => r.strike === strike);
    const premium = leg.optType === "CE" ? (row?.call_ltp ?? 50) : (row?.put_ltp ?? 50);
    const delta = leg.optType === "CE" ? (row?.call_delta ?? 0.5) : (row?.put_delta ?? -0.5);
    return { strike, premium, delta };
  }
  if (leg.strikeMode === "premium_ge" || leg.strikeMode === "premium_le" || leg.strikeMode === "closest_premium") {
    const target = Number(leg.strikeValue) || 50;
    let best = strikes[0];
    let bestDiff = Infinity;
    for (const r of strikes) {
      const prem = leg.optType === "CE" ? r.call_ltp : r.put_ltp;
      const diff = Math.abs(prem - target);
      if (diff < bestDiff) { bestDiff = diff; best = r; }
    }
    const premium = leg.optType === "CE" ? best.call_ltp : best.put_ltp;
    const delta = leg.optType === "CE" ? best.call_delta : best.put_delta;
    return { strike: best.strike, premium, delta };
  }
  if (leg.strikeMode === "closest_delta") {
    const target = Number(leg.strikeValue) || 0.20;
    let best = strikes[0];
    let bestDiff = Infinity;
    for (const r of strikes) {
      const d = Math.abs((leg.optType === "CE" ? r.call_delta : Math.abs(r.put_delta)) - target);
      if (d < bestDiff) { bestDiff = d; best = r; }
    }
    const premium = leg.optType === "CE" ? best.call_ltp : best.put_ltp;
    const delta = leg.optType === "CE" ? best.call_delta : best.put_delta;
    return { strike: best.strike, premium, delta };
  }
  const strike = atm + leg.strikeOffset * step;
  const row = strikes.find((r) => r.strike === strike);
  const premium = leg.optType === "CE" ? (row?.call_ltp ?? 50) : (row?.put_ltp ?? 50);
  const delta = leg.optType === "CE" ? (row?.call_delta ?? 0.5) : (row?.put_delta ?? -0.5);
  return { strike, premium, delta };
}

function buildCurve(resolvedLegs: { premium: number; strike: number; optType: OptType; action: Action; lots: number }[], spot: number, lotSize: number) {
  if (!spot) return [] as { price: number; pnl: number }[];
  const lo = spot - 600;
  const hi = spot + 600;
  const n = 49;
  const out: { price: number; pnl: number }[] = [];
  for (let i = 0; i <= n; i++) {
    const S = lo + ((hi - lo) * i) / n;
    let pnl = 0;
    for (const l of resolvedLegs) {
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
  const [legs, setLegs] = useState<Leg[]>([mkLeg("buy", "CE", 0), mkLeg("buy", "PE", 0)]);
  const [lazyLegs, setLazyLegs] = useState<LazyLeg[]>([]);
  const [name, setName] = useState("");
  const [savedId, setSavedId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [run, setRun] = useState<BacktestRun | null>(null);
  const [saved, setSaved] = useState<Strategy[]>([]);
  const [lotSizes, setLotSizes] = useState<Record<string, number>>({});
  const [expandedLeg, setExpandedLeg] = useState<string | null>(null);
  const [expandedLazy, setExpandedLazy] = useState<string | null>(null);

  const [segment, setSegment] = useState<"weekly_monthly" | "stocks" | "crypto">("weekly_monthly");
  const [underlyingSource, setUnderlyingSource] = useState<"cash" | "futures">("cash");
  const [strategyType, setStrategyType] = useState<StrategyType>("intraday");
  const [entryTime, setEntryTime] = useState("09:35");
  const [exitTime, setExitTime] = useState("15:15");
  const [noReentryAfterEnabled, setNoReentryAfterEnabled] = useState(false);
  const [noReentryAfter, setNoReentryAfter] = useState("09:35");
  const [overallMomentumEnabled, setOverallMomentumEnabled] = useState(false);
  const [overallMomentumDir, setOverallMomentumDir] = useState<MomentumDir>("up");
  const [overallMomentumUnit, setOverallMomentumUnit] = useState<MomentumUnit>("pts");
  const [overallMomentumValue, setOverallMomentumValue] = useState("0");

  const [squareOff, setSquareOff] = useState<"partial" | "complete">("partial");
  const [trailToBreakeven, setTrailToBreakeven] = useState(false);
  const [trailToBeScope, setTrailToBeScope] = useState<"all_legs" | "sl_legs">("all_legs");

  const [overallSl, setOverallSl] = useState("");
  const [overallSlReentry, setOverallSlReentry] = useState(false);
  const [overallTarget, setOverallTarget] = useState("");
  const [overallTargetReentry, setOverallTargetReentry] = useState(false);
  const [trailingMode, setTrailingMode] = useState<TrailingMode>("none");
  const [lockProfitReach, setLockProfitReach] = useState("");
  const [lockProfitValue, setLockProfitValue] = useState("");
  const [trailEveryIncrease, setTrailEveryIncrease] = useState("");
  const [trailByValue, setTrailByValue] = useState("");
  const [backtestStart, setBacktestStart] = useState("2025-08-27");
  const [backtestEnd, setBacktestEnd] = useState("2026-08-27");

  const step = STRIKE_STEPS[underlying] ?? 50;

  useEffect(() => {
    let cancelled = false;
    api<Instrument[]>("/market/instruments")
      .then((list) => { if (!cancelled) setLotSizes(Object.fromEntries(list.map((i) => [i.symbol.toUpperCase(), i.lot_size]))); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    api<OptionChain>(`/market/option-chain?underlying=${underlying}`)
      .then((c) => { if (!cancelled) setChain(c); })
      .catch(() => { if (!cancelled) setChainError("Could not load option chain."); });
    return () => { cancelled = true; };
  }, [underlying]);

  useEffect(() => {
    let cancelled = false;
    api<Strategy[]>("/strategies")
      .then((list) => { if (!cancelled) setSaved(list.filter((s) => (s.definition as { builder?: string } | null)?.builder === "legs")); })
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

  const resolved = useMemo(() => legs.map((l) => ({ ...l, ...resolveStrike(l, chain, step, atm) })), [legs, chain, step, atm]);
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
    setRun(null); setMessage(null);
  };

  const patchLazy = (id: string, patch: Partial<LazyLeg>) =>
    setLazyLegs((prev) => prev.map((l) => (l.id === id ? { ...l, ...patch } : l)));
  const removeLazy = (id: string) => setLazyLegs((prev) => prev.filter((l) => l.id !== id));
  const addLazy = () => {
    const n = lazyLegs.length + 1;
    setLazyLegs((prev) => [...prev, mkLazyLeg(`lazy${n}`)]);
  };

  const buildDefinition = () => ({
    version: 1 as const,
    timeframe: "5m",
    builder: "legs",
    instrument: { symbol: underlying, exchange: "NSE", segment: "options" as const },
    underlying,
    strategy_type: strategyType,
    cash_or_futures: underlyingSource,
    legs: [
      ...resolved.map((l) => ({
        action: l.action, option_type: l.optType, lots: l.lots,
        strike_selection: l.strikeMode,
        strike_offset: l.strikeOffset,
        strike_selection_value: l.strikeValue ? Number(l.strikeValue) : undefined,
        strike_selection_value_2: l.strikeValue2 ? Number(l.strikeValue2) : undefined,
        strike: l.strike, premium: l.premium,
        expiry_formula: l.expiryType.toUpperCase(),
        ...(l.slEnabled && l.slMode && l.slValue ? { sl_mode: l.slMode, sl_value: Number(l.slValue) } : {}),
        ...(l.targetEnabled && l.targetMode && l.targetValue ? { target_mode: l.targetMode, target_value: Number(l.targetValue) } : {}),
        ...(l.trailEnabled && l.trailTrigger ? { trail_mode: l.trailUnit, trail_by: Number(l.trailTrigger), trail_step: Number(l.trailBy) } : {}),
        ...(l.reentryOnSl ? { reentry_on_sl: l.reentryOnSl, max_reentries: Number(l.maxReentries) } : {}),
        ...(l.reentryOnTarget ? { reentry_on_target: l.reentryOnTarget, max_reentries: Number(l.maxReentries) } : {}),
        ...(l.momentumEnabled && l.momentumValue ? { momentum_mode: `${l.momentumUnit}_${l.momentumDir}` as const, momentum_value: Number(l.momentumValue) } : {}),
        square_off: squareOff,
      })),
      ...lazyLegs.map((l) => ({
        action: l.action, option_type: l.optType, lots: l.lots,
        strike_selection: l.strikeMode,
        strike_offset: l.strikeOffset,
        strike: atm + l.strikeOffset * step, premium: 50,
        expiry_formula: l.expiryType.toUpperCase(),
        ...(l.slEnabled && l.slMode && l.slValue ? { sl_mode: l.slMode, sl_value: Number(l.slValue) } : {}),
        ...(l.targetEnabled && l.targetMode && l.targetValue ? { target_mode: l.targetMode, target_value: Number(l.targetValue) } : {}),
        ...(l.trailEnabled && l.trailTrigger ? { trail_mode: l.trailUnit, trail_by: Number(l.trailTrigger), trail_step: Number(l.trailBy) } : {}),
        ...(l.reentryOnSl ? { reentry_on_sl: l.reentryOnSl, max_reentries: Number(l.maxReentries) } : {}),
        ...(l.reentryOnTarget ? { reentry_on_target: l.reentryOnTarget, max_reentries: Number(l.maxReentries) } : {}),
        ...(l.momentumEnabled && l.momentumValue ? { momentum_mode: `${l.momentumUnit}_${l.momentumDir}` as const, momentum_value: Number(l.momentumValue) } : {}),
        square_off: squareOff,
      })),
    ],
    entry: { logic: "ALL" as const, conditions: [{ left: { kind: "price" as const, price: "close" }, op: "GT", right: { kind: "constant" as const, value: 0 } }] },
    exit: null,
    risk: null,
    position: { quantity_type: "fixed" as const, quantity: 1, direction: "long_only" as const },
    overall: {
      overall_sl: overallSl ? Number(overallSl) : null,
      overall_target: overallTarget ? Number(overallTarget) : null,
      overall_reentry_on_sl: overallSlReentry ? "asap" as const : null,
      overall_reentry_on_target: overallTargetReentry ? "asap" as const : null,
      lock_and_trail_at: trailingMode !== "none" && lockProfitReach ? Number(lockProfitReach) : null,
      lock_and_trail_profit: trailingMode !== "none" && lockProfitValue ? Number(lockProfitValue) : null,
      lock_and_trail_by: trailingMode !== "none" && trailByValue ? Number(trailByValue) : null,
    },
    entry_momentum: overallMomentumEnabled ? { enabled: true, direction: overallMomentumDir, mode: overallMomentumUnit, value: Number(overallMomentumValue) || 0 } : null,
    time_control: { no_entry_after: exitTime || null, no_reentry_after: noReentryAfterEnabled ? noReentryAfter : null, time_exit: exitTime || null },
    legwise: { trail_sl_to_breakeven: trailToBreakeven ? trailToBeScope : "none", square_off_on_leg_sl: squareOff === "complete" },
  });

  const doSave = async (): Promise<string> => {
    if (savedId) return savedId;
    const created = await api<Strategy>("/strategies", {
      method: "POST",
      body: JSON.stringify({ name: name.trim() || "Untitled Leg Strategy", description: "", exchange: "NSE", underlying, instrument: "options", strategy_type: "options", tags: ["options", "legs"], definition: buildDefinition() }),
    });
    setSavedId(created.id);
    return created.id;
  };

  const save = async () => {
    setBusy(true); setError(null);
    try {
      const id = await doSave();
      setMessage(`Saved (id ${id.slice(0, 8)}).`);
    } catch (e) { setError(e instanceof Error ? e.message : "Save failed"); }
    finally { setBusy(false); }
  };

  const backtest = async () => {
    setBusy(true); setError(null);
    try {
      const id = await doSave();
      const r = await api<BacktestRun>("/backtests", {
        method: "POST",
        body: JSON.stringify({ strategy_id: id, initial_capital: 100000, costs_pct: 0.05 }),
      });
      setRun(r);
      setMessage(`Backtest complete — return ${(r.result_summary?.summary.return_pct ?? 0).toFixed(2)}%.`);
    } catch (e) { setError(e instanceof Error ? e.message : "Backtest failed"); }
    finally { setBusy(false); }
  };

  const s = run?.result_summary?.summary ?? null;

  return (
    <div className="space-y-4">
      {/* Top row: Instrument Settings + Entry Settings */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Instrument Settings */}
        <Card title="Instrument settings">
          <div className="mb-3 flex gap-0 border-b border-slate-200">
            {([
              { key: "weekly_monthly" as const, label: "Weekly & Monthly Expiries", sub: "NIFTY | SENSEX" },
              { key: "stocks" as const, label: "Stocks - Cash / F&O", sub: "ALL NIFTY 500 STOCKS" },
              { key: "crypto" as const, label: "Crypto", sub: "Delta Exchange & CoinSwitch" },
            ]).map((tab) => (
              <button key={tab.key} onClick={() => setSegment(tab.key)}
                className={`flex-1 px-3 py-2 text-center text-xs font-medium transition-colors ${segment === tab.key ? "border-b-2 border-blue-600 text-blue-600" : "text-slate-500 hover:text-slate-700"}`}>
                {tab.label}
                <span className="block text-[10px] text-slate-400">{tab.sub}</span>
              </button>
            ))}
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="block text-xs font-medium text-slate-500">
              Index
              <select value={underlying} onChange={(e) => setUnderlying(e.target.value)} className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800">
                {UNDERLYINGS.map((u) => <option key={u}>{u}</option>)}
              </select>
            </label>
            <div className="block text-xs font-medium text-slate-500">
              Underlying from
              <div className="mt-1 flex gap-0 rounded-md border border-slate-300 overflow-hidden">
                {(["cash", "futures"] as const).map((v) => (
                  <button key={v} onClick={() => setUnderlyingSource(v)}
                    className={`flex-1 px-3 py-1.5 text-xs font-medium capitalize transition-colors ${underlyingSource === v ? "bg-blue-600 text-white" : "bg-white text-slate-600 hover:bg-slate-50"}`}>
                    {v}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </Card>

        {/* Entry Settings */}
        <Card title="Entry settings">
          <div className="grid gap-3 md:grid-cols-2">
            <div className="block text-xs font-medium text-slate-500">
              Strategy Type
              <div className="mt-1 flex gap-0 rounded-md border border-slate-300 overflow-hidden">
                {(["intraday", "btst", "positional"] as const).map((v) => (
                  <button key={v} onClick={() => setStrategyType(v)}
                    className={`flex-1 px-3 py-1.5 text-xs font-medium capitalize transition-colors ${strategyType === v ? "bg-blue-600 text-white" : "bg-white text-slate-600 hover:bg-slate-50"}`}>
                    {v}
                  </button>
                ))}
              </div>
            </div>
            <label className="block text-xs font-medium text-slate-500">
              Entry Time
              <input type="time" value={entryTime} onChange={(e) => setEntryTime(e.target.value)} className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800" />
            </label>
            <label className="block text-xs font-medium text-slate-500">
              Exit Time
              <input type="time" value={exitTime} onChange={(e) => setExitTime(e.target.value)} className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800" />
            </label>
            <div className="block text-xs font-medium text-slate-500">
              <div className="flex items-center gap-2">
                No re-entry after
                <button onClick={() => setNoReentryAfterEnabled(!noReentryAfterEnabled)}
                  className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${noReentryAfterEnabled ? "bg-blue-600" : "bg-slate-300"}`}>
                  <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform ${noReentryAfterEnabled ? "translate-x-4.5" : "translate-x-0.5"}`} />
                </button>
              </div>
              {noReentryAfterEnabled && (
                <input type="time" value={noReentryAfter} onChange={(e) => setNoReentryAfter(e.target.value)} className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800" />
              )}
            </div>
            <div className="block text-xs font-medium text-slate-500">
              <div className="flex items-center gap-2">
                Overall Momentum
                <button onClick={() => setOverallMomentumEnabled(!overallMomentumEnabled)}
                  className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${overallMomentumEnabled ? "bg-blue-600" : "bg-slate-300"}`}>
                  <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform ${overallMomentumEnabled ? "translate-x-4.5" : "translate-x-0.5"}`} />
                </button>
              </div>
              {overallMomentumEnabled && (
                <div className="mt-1 flex gap-1">
                  <select value={overallMomentumUnit} onChange={(e) => setOverallMomentumUnit(e.target.value as MomentumUnit)} className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-700">
                    <option value="pts">Points (Pts)</option>
                    <option value="%">Percent (%)</option>
                  </select>
                  <select value={overallMomentumDir} onChange={(e) => setOverallMomentumDir(e.target.value as MomentumDir)} className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-700">
                    <option value="up">Up ↑</option>
                    <option value="down">Down ↓</option>
                  </select>
                  <input type="number" value={overallMomentumValue} onChange={(e) => setOverallMomentumValue(e.target.value)} placeholder="0" className="w-20 rounded border border-slate-300 px-2 py-1 text-xs text-slate-700" />
                </div>
              )}
            </div>
          </div>
        </Card>
      </div>

      {/* Legwise Settings + Strategy Info */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Legwise settings">
          <div className="flex flex-wrap items-center gap-6">
            <div className="block text-xs font-medium text-slate-500">
              Square Off
              <div className="mt-1 flex gap-0 rounded-md border border-slate-300 overflow-hidden">
                {(["partial", "complete"] as const).map((v) => (
                  <button key={v} onClick={() => setSquareOff(v)}
                    className={`flex-1 px-4 py-1.5 text-xs font-medium capitalize transition-colors ${squareOff === v ? "bg-blue-600 text-white" : "bg-white text-slate-600 hover:bg-slate-50"}`}>
                    {v}
                  </button>
                ))}
              </div>
            </div>
            <label className="flex items-center gap-2 text-xs font-medium text-slate-500">
              <input type="checkbox" checked={trailToBreakeven} onChange={(e) => setTrailToBreakeven(e.target.checked)} className="rounded border-slate-300" />
              Trail SL to Break-even price
              {trailToBreakeven && (
                <div className="ml-2 flex gap-0 rounded-md border border-slate-300 overflow-hidden">
                  {(["all_legs", "sl_legs"] as const).map((v) => (
                    <button key={v} onClick={() => setTrailToBeScope(v)}
                      className={`px-3 py-1 text-[10px] font-medium transition-colors ${trailToBeScope === v ? "bg-blue-600 text-white" : "bg-white text-slate-600"}`}>
                      {v === "all_legs" ? "All Legs" : "SL Legs"}
                    </button>
                  ))}
                </div>
              )}
            </label>
          </div>
        </Card>
        <div />
      </div>

      {/* Leg Builder Section */}
      <Card
        title="Leg Builder"
        actions={<span className="text-[11px] text-slate-400">{chain ? `Spot ${fmt(spot)} · ${underlying}` : "Loading…"}</span>}
      >
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Presets</span>
          {PRESETS.map((p) => (
            <button key={p.name} onClick={() => applyPreset(p)} className="rounded-full border border-slate-200 px-2.5 py-1 text-[11px] font-medium text-slate-600 transition-colors hover:bg-slate-50">{p.name}</button>
          ))}
        </div>
      </Card>

      {/* Main Legs */}
      <Card title="Main Legs" subtitle="Configure each option leg with strike selection, SL, Target, Trail, Momentum, and Range Breakout.">
        <div className="space-y-2">
          {legs.map((l, i) => {
            const r = resolved[i];
            return (
              <div key={l.id} className="rounded-lg border border-slate-200 bg-white">
                {/* Leg header row */}
                <div className="flex items-center gap-2 px-3 py-2">
                  <span className="text-xs font-bold text-slate-400 w-6">#{i + 1}</span>
                  <select value={l.lots} onChange={(e) => patchLeg(l.id, { lots: Math.max(1, Number(e.target.value)) })} className="w-14 rounded border border-slate-300 px-1.5 py-1 text-xs text-slate-800">
                    {Array.from({ length: 10 }, (_, k) => k + 1).map((n) => <option key={n} value={n}>{n}</option>)}
                  </select>
                  <select value={l.action} onChange={(e) => patchLeg(l.id, { action: e.target.value as Action })} className="rounded border border-slate-300 px-2 py-1 text-xs font-medium text-slate-800">
                    <option value="buy">Buy</option>
                    <option value="sell">Sell</option>
                  </select>
                  <select value={l.optType} onChange={(e) => patchLeg(l.id, { optType: e.target.value as OptType })} className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-800">
                    <option value="CE">Call</option>
                    <option value="PE">Put</option>
                  </select>
                  <select value={l.expiryType} onChange={(e) => patchLeg(l.id, { expiryType: e.target.value as ExpiryType })} className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-800">
                    {EXPIRY_OPTIONS.map((e) => <option key={e.value} value={e.value}>{e.label}</option>)}
                  </select>
                  <select value={l.strikeMode} onChange={(e) => patchLeg(l.id, { strikeMode: e.target.value as StrikeMode })} className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-800">
                    {STRIKE_MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                  </select>
                  {l.strikeMode === "strike_type" ? (
                    <select value={l.strikeOffset} onChange={(e) => patchLeg(l.id, { strikeOffset: Number(e.target.value) })} className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-800">
                      {STRIKE_TYPE_OFFSETS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </select>
                  ) : (
                    <input type="number" step="0.01" value={l.strikeValue} onChange={(e) => patchLeg(l.id, { strikeValue: e.target.value })} placeholder="Value" className="w-24 rounded border border-slate-300 px-2 py-1 text-xs text-slate-800" />
                  )}
                  <span className="text-[10px] text-slate-400 tabular-nums">Prem: {r ? fmt(r.premium) : "—"}</span>
                  <span className="text-[10px] text-slate-400 tabular-nums">Δ: {r ? fmt(r.delta, 3) : "—"}</span>
                  <div className="ml-auto flex items-center gap-1">
                    {(l.slEnabled || l.targetEnabled || l.momentumEnabled) && <span className="text-[10px] text-blue-500">●</span>}
                    <button onClick={() => setExpandedLeg(expandedLeg === l.id ? null : l.id)} className="text-[11px] text-blue-600 hover:underline">{expandedLeg === l.id ? "Collapse" : "Expand"}</button>
                    <button onClick={() => removeLeg(l.id)} disabled={legs.length <= 1} className="text-[11px] text-red-500 hover:underline disabled:opacity-30">Remove</button>
                  </div>
                </div>
                {/* Expanded settings */}
                {expandedLeg === l.id && (
                  <div className="border-t border-slate-100 bg-slate-50/50 px-4 py-3">
                    <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
                      {/* Target Profit */}
                      <div>
                        <label className="flex items-center gap-2 mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                          <input type="checkbox" checked={l.targetEnabled} onChange={(e) => patchLeg(l.id, { targetEnabled: e.target.checked })} className="rounded border-slate-300" />
                          Target Profit
                        </label>
                        {l.targetEnabled && (
                          <div className="flex gap-1">
                            <select value={l.targetMode} onChange={(e) => patchLeg(l.id, { targetMode: e.target.value as SlMode })} className="rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700">
                              {SL_MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                            </select>
                            <input type="number" step="0.01" value={l.targetValue} onChange={(e) => patchLeg(l.id, { targetValue: e.target.value })} className="w-16 rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700" />
                          </div>
                        )}
                      </div>
                      {/* Stop Loss */}
                      <div>
                        <label className="flex items-center gap-2 mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                          <input type="checkbox" checked={l.slEnabled} onChange={(e) => patchLeg(l.id, { slEnabled: e.target.checked })} className="rounded border-slate-300" />
                          Stop Loss
                        </label>
                        {l.slEnabled && (
                          <div className="flex gap-1">
                            <select value={l.slMode} onChange={(e) => patchLeg(l.id, { slMode: e.target.value as SlMode })} className="rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700">
                              {SL_MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                            </select>
                            <input type="number" step="0.01" value={l.slValue} onChange={(e) => patchLeg(l.id, { slValue: e.target.value })} className="w-16 rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700" />
                          </div>
                        )}
                      </div>
                      {/* Trail SL */}
                      <div>
                        <label className="flex items-center gap-2 mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                          <input type="checkbox" checked={l.trailEnabled} onChange={(e) => patchLeg(l.id, { trailEnabled: e.target.checked })} className="rounded border-slate-300" />
                          Trail SL
                        </label>
                        {l.trailEnabled && (
                          <div className="flex gap-1 items-center">
                            <select value={l.trailUnit} onChange={(e) => patchLeg(l.id, { trailUnit: e.target.value as TrailUnit })} className="rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700">
                              <option value="pts">Points</option>
                              <option value="%">Percentage</option>
                            </select>
                            <span className="text-[10px] text-slate-400">Trigger</span>
                            <input type="number" step="0.01" value={l.trailTrigger} onChange={(e) => patchLeg(l.id, { trailTrigger: e.target.value })} className="w-14 rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700" />
                            <span className="text-[10px] text-slate-400">Trail by</span>
                            <input type="number" step="0.01" value={l.trailBy} onChange={(e) => patchLeg(l.id, { trailBy: e.target.value })} className="w-14 rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700" />
                          </div>
                        )}
                      </div>
                      {/* Re-entry on Target */}
                      <div>
                        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">Re-entry on Target</p>
                        <select value={l.reentryOnTarget} onChange={(e) => patchLeg(l.id, { reentryOnTarget: e.target.value as ReentryMode })} className="rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700">
                          <option value="">OFF</option>
                          <option value="asap">ASAP</option>
                          <option value="asap_reverse">ASAP Reverse</option>
                          <option value="cost">COST</option>
                          <option value="cost_reverse">COST Reverse</option>
                          <option value="reexecute">Re-Execute</option>
                          <option value="reexecute_reverse">Re-Execute Reverse</option>
                        </select>
                      </div>
                      {/* Re-entry on SL */}
                      <div>
                        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">Re-entry on SL</p>
                        <div className="flex gap-1">
                          <select value={l.reentryOnSl} onChange={(e) => patchLeg(l.id, { reentryOnSl: e.target.value as ReentryMode })} className="rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700">
                            <option value="">OFF</option>
                            <option value="asap">ASAP</option>
                            <option value="asap_reverse">ASAP Reverse</option>
                            <option value="cost">COST</option>
                            <option value="cost_reverse">COST Reverse</option>
                            <option value="reexecute">Re-Execute</option>
                            <option value="reexecute_reverse">Re-Execute Reverse</option>
                          </select>
                          {l.reentryOnSl && (
                            <input type="number" min={0} max={20} value={l.maxReentries} onChange={(e) => patchLeg(l.id, { maxReentries: e.target.value })} placeholder="Max" className="w-14 rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700" />
                          )}
                        </div>
                      </div>
                      {/* Simple Momentum */}
                      <div>
                        <label className="flex items-center gap-2 mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                          <input type="checkbox" checked={l.momentumEnabled} onChange={(e) => patchLeg(l.id, { momentumEnabled: e.target.checked })} className="rounded border-slate-300" />
                          Simple Momentum
                        </label>
                        {l.momentumEnabled && (
                          <div className="flex gap-1">
                            <select value={l.momentumUnit} onChange={(e) => patchLeg(l.id, { momentumUnit: e.target.value as MomentumUnit })} className="rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700">
                              <option value="pts">Points (Pts)</option>
                              <option value="%">Percent (%)</option>
                            </select>
                            <select value={l.momentumDir} onChange={(e) => patchLeg(l.id, { momentumDir: e.target.value as MomentumDir })} className="rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700">
                              <option value="up">↑</option>
                              <option value="down">↓</option>
                            </select>
                            <input type="number" step="0.01" value={l.momentumValue} onChange={(e) => patchLeg(l.id, { momentumValue: e.target.value })} className="w-16 rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700" />
                          </div>
                        )}
                      </div>
                      {/* Range Breakout */}
                      <div>
                        <label className="flex items-center gap-2 mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                          <input type="checkbox" checked={l.rangeBreakoutEnabled} onChange={(e) => patchLeg(l.id, { rangeBreakoutEnabled: e.target.checked })} className="rounded border-slate-300" />
                          Range Breakout
                        </label>
                        {l.rangeBreakoutEnabled && (
                          <p className="text-[10px] text-slate-400">Configure in Overall Strategy Settings</p>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
        <button onClick={addLeg} className="mt-3 rounded-md border border-dashed border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50">
          + Add leg
        </button>
      </Card>

      {/* Lazy Legs */}
      <Card title="Lazy Legs" subtitle="Optional legs with independent configuration that activate on re-entry from main legs.">
        <div className="space-y-2">
          {lazyLegs.map((l) => (
            <div key={l.id} className="rounded-lg border border-slate-200 bg-white">
              <div className="flex items-center gap-2 px-3 py-2">
                <input value={l.name} onChange={(e) => patchLazy(l.id, { name: e.target.value })} className="w-24 rounded border border-slate-300 px-1.5 py-1 text-xs font-medium text-slate-800" />
                <select value={l.lots} onChange={(e) => patchLazy(l.id, { lots: Math.max(1, Number(e.target.value)) })} className="w-14 rounded border border-slate-300 px-1.5 py-1 text-xs text-slate-800">
                  {Array.from({ length: 10 }, (_, k) => k + 1).map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
                <select value={l.action} onChange={(e) => patchLazy(l.id, { action: e.target.value as Action })} className="rounded border border-slate-300 px-2 py-1 text-xs font-medium text-slate-800">
                  <option value="buy">Buy</option>
                  <option value="sell">Sell</option>
                </select>
                <select value={l.optType} onChange={(e) => patchLazy(l.id, { optType: e.target.value as OptType })} className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-800">
                  <option value="CE">Call</option>
                  <option value="PE">Put</option>
                </select>
                <select value={l.expiryType} onChange={(e) => patchLazy(l.id, { expiryType: e.target.value as ExpiryType })} className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-800">
                  {EXPIRY_OPTIONS.map((e) => <option key={e.value} value={e.value}>{e.label}</option>)}
                </select>
                <select value={l.strikeMode} onChange={(e) => patchLazy(l.id, { strikeMode: e.target.value as StrikeMode })} className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-800">
                  {STRIKE_MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                </select>
                {l.strikeMode === "strike_type" ? (
                  <select value={l.strikeOffset} onChange={(e) => patchLazy(l.id, { strikeOffset: Number(e.target.value) })} className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-800">
                    {STRIKE_TYPE_OFFSETS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                ) : (
                  <input type="number" step="0.01" value={l.strikeValue} onChange={(e) => patchLazy(l.id, { strikeValue: e.target.value })} placeholder="Value" className="w-24 rounded border border-slate-300 px-2 py-1 text-xs text-slate-800" />
                )}
                <div className="ml-auto flex items-center gap-1">
                  <button onClick={() => setExpandedLazy(expandedLazy === l.id ? null : l.id)} className="text-[11px] text-blue-600 hover:underline">{expandedLazy === l.id ? "Collapse" : "Expand"}</button>
                  <button onClick={() => removeLazy(l.id)} className="text-[11px] text-red-500 hover:underline">Remove</button>
                </div>
              </div>
              {expandedLazy === l.id && (
                <div className="border-t border-slate-100 bg-slate-50/50 px-4 py-3">
                  <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
                    <div>
                      <label className="flex items-center gap-2 mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                        <input type="checkbox" checked={l.targetEnabled} onChange={(e) => patchLazy(l.id, { targetEnabled: e.target.checked })} className="rounded border-slate-300" />
                        Target Profit
                      </label>
                      {l.targetEnabled && (
                        <div className="flex gap-1">
                          <select value={l.targetMode} onChange={(e) => patchLazy(l.id, { targetMode: e.target.value as SlMode })} className="rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700">
                            {SL_MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                          </select>
                          <input type="number" step="0.01" value={l.targetValue} onChange={(e) => patchLazy(l.id, { targetValue: e.target.value })} className="w-16 rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700" />
                        </div>
                      )}
                    </div>
                    <div>
                      <label className="flex items-center gap-2 mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                        <input type="checkbox" checked={l.slEnabled} onChange={(e) => patchLazy(l.id, { slEnabled: e.target.checked })} className="rounded border-slate-300" />
                        Stop Loss
                      </label>
                      {l.slEnabled && (
                        <div className="flex gap-1">
                          <select value={l.slMode} onChange={(e) => patchLazy(l.id, { slMode: e.target.value as SlMode })} className="rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700">
                            {SL_MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                          </select>
                          <input type="number" step="0.01" value={l.slValue} onChange={(e) => patchLazy(l.id, { slValue: e.target.value })} className="w-16 rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700" />
                        </div>
                      )}
                    </div>
                    <div>
                      <label className="flex items-center gap-2 mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                        <input type="checkbox" checked={l.trailEnabled} onChange={(e) => patchLazy(l.id, { trailEnabled: e.target.checked })} className="rounded border-slate-300" />
                        Trail SL
                      </label>
                      {l.trailEnabled && (
                        <div className="flex gap-1 items-center">
                          <select value={l.trailUnit} onChange={(e) => patchLazy(l.id, { trailUnit: e.target.value as TrailUnit })} className="rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700">
                            <option value="pts">Points</option>
                            <option value="%">Percentage</option>
                          </select>
                          <input type="number" step="0.01" value={l.trailTrigger} onChange={(e) => patchLazy(l.id, { trailTrigger: e.target.value })} className="w-14 rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700" />
                          <input type="number" step="0.01" value={l.trailBy} onChange={(e) => patchLazy(l.id, { trailBy: e.target.value })} className="w-14 rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700" />
                        </div>
                      )}
                    </div>
                    <div>
                      <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">Re-entry on SL</p>
                      <select value={l.reentryOnSl} onChange={(e) => patchLazy(l.id, { reentryOnSl: e.target.value as ReentryMode })} className="rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700">
                        <option value="">OFF</option>
                        <option value="asap">ASAP</option>
                        <option value="cost">COST</option>
                      </select>
                    </div>
                    <div>
                      <label className="flex items-center gap-2 mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                        <input type="checkbox" checked={l.momentumEnabled} onChange={(e) => patchLazy(l.id, { momentumEnabled: e.target.checked })} className="rounded border-slate-300" />
                        Simple Momentum
                      </label>
                      {l.momentumEnabled && (
                        <div className="flex gap-1">
                          <select value={l.momentumUnit} onChange={(e) => patchLazy(l.id, { momentumUnit: e.target.value as MomentumUnit })} className="rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700">
                            <option value="pts">Points (Pts)</option>
                            <option value="%">Percent (%)</option>
                          </select>
                          <select value={l.momentumDir} onChange={(e) => patchLazy(l.id, { momentumDir: e.target.value as MomentumDir })} className="rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700">
                            <option value="up">↑</option>
                            <option value="down">↓</option>
                          </select>
                          <input type="number" step="0.01" value={l.momentumValue} onChange={(e) => patchLazy(l.id, { momentumValue: e.target.value })} className="w-16 rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700" />
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
        <button onClick={addLazy} className="mt-3 rounded-md border border-dashed border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50">
          + Add Lazy Leg
        </button>
      </Card>

      {/* Overall Strategy Settings */}
      <Card title="Overall Strategy Settings" subtitle="Strategy-level risk management in MTM (mark-to-market ₹) terms.">
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {/* Overall SL */}
          <div>
            <label className="flex items-center gap-2 text-xs font-medium text-slate-500">
              <input type="checkbox" checked={!!overallSl} onChange={(e) => setOverallSl(e.target.checked ? "1000" : "")} className="rounded border-slate-300" />
              Overall Stop Loss
            </label>
            {overallSl && (
              <div className="mt-1 flex gap-1 items-center">
                <span className="text-[10px] text-slate-400">Max Loss</span>
                <input type="number" value={overallSl} onChange={(e) => setOverallSl(e.target.value)} className="w-24 rounded border border-slate-300 px-2 py-1 text-xs text-slate-800" />
              </div>
            )}
          </div>
          {/* Overall SL Re-entry */}
          <div>
            <label className="flex items-center gap-2 text-xs font-medium text-slate-500">
              Overall Re-entry on SL
              <button onClick={() => setOverallSlReentry(!overallSlReentry)}
                className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${overallSlReentry ? "bg-blue-600" : "bg-slate-300"}`}>
                <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform ${overallSlReentry ? "translate-x-4.5" : "translate-x-0.5"}`} />
              </button>
            </label>
          </div>
          {/* Overall Target */}
          <div>
            <label className="flex items-center gap-2 text-xs font-medium text-slate-500">
              <input type="checkbox" checked={!!overallTarget} onChange={(e) => setOverallTarget(e.target.checked ? "2500" : "")} className="rounded border-slate-300" />
              Overall Target
            </label>
            {overallTarget && (
              <div className="mt-1 flex gap-1 items-center">
                <span className="text-[10px] text-slate-400">Max Profit</span>
                <input type="number" value={overallTarget} onChange={(e) => setOverallTarget(e.target.value)} className="w-24 rounded border border-slate-300 px-2 py-1 text-xs text-slate-800" />
              </div>
            )}
          </div>
          {/* Overall Target Re-entry */}
          <div>
            <label className="flex items-center gap-2 text-xs font-medium text-slate-500">
              Overall Re-entry on Target
              <button onClick={() => setOverallTargetReentry(!overallTargetReentry)}
                className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${overallTargetReentry ? "bg-blue-600" : "bg-slate-300"}`}>
                <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform ${overallTargetReentry ? "translate-x-4.5" : "translate-x-0.5"}`} />
              </button>
            </label>
          </div>
          {/* Trailing Options */}
          <div className="md:col-span-2 lg:col-span-3">
            <label className="block text-xs font-medium text-slate-500 mb-1">Trailing Options</label>
            <select value={trailingMode} onChange={(e) => setTrailingMode(e.target.value as TrailingMode)} className="w-48 rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800">
              <option value="none">None</option>
              <option value="lock">Lock Profit</option>
              <option value="lock_and_trail">Lock and Trail</option>
            </select>
            {trailingMode === "lock" && (
              <div className="mt-2 flex gap-2 items-center">
                <span className="text-[10px] text-slate-400">If profit reaches</span>
                <input type="number" value={lockProfitReach} onChange={(e) => setLockProfitReach(e.target.value)} className="w-24 rounded border border-slate-300 px-2 py-1 text-xs text-slate-800" />
                <span className="text-[10px] text-slate-400">Lock profit</span>
                <input type="number" value={lockProfitValue} onChange={(e) => setLockProfitValue(e.target.value)} className="w-24 rounded border border-slate-300 px-2 py-1 text-xs text-slate-800" />
              </div>
            )}
            {trailingMode === "lock_and_trail" && (
              <div className="mt-2 flex flex-wrap gap-2 items-center">
                <span className="text-[10px] text-slate-400">If profit reaches</span>
                <input type="number" value={lockProfitReach} onChange={(e) => setLockProfitReach(e.target.value)} className="w-24 rounded border border-slate-300 px-2 py-1 text-xs text-slate-800" />
                <span className="text-[10px] text-slate-400">Lock profit</span>
                <input type="number" value={lockProfitValue} onChange={(e) => setLockProfitValue(e.target.value)} className="w-24 rounded border border-slate-300 px-2 py-1 text-xs text-slate-800" />
                <span className="text-[10px] text-slate-400">For every increase in profit by</span>
                <input type="number" value={trailEveryIncrease} onChange={(e) => setTrailEveryIncrease(e.target.value)} className="w-24 rounded border border-slate-300 px-2 py-1 text-xs text-slate-800" />
                <span className="text-[10px] text-slate-400">Trail profit by</span>
                <input type="number" value={trailByValue} onChange={(e) => setTrailByValue(e.target.value)} className="w-24 rounded border border-slate-300 px-2 py-1 text-xs text-slate-800" />
              </div>
            )}
          </div>
        </div>
      </Card>

      {/* Backtest Duration */}
      <Card title="Backtest Duration" subtitle="Select the date range for backtesting.">
        <div className="grid gap-3 md:grid-cols-2">
          <label className="block text-xs font-medium text-slate-500">
            Start Date
            <input type="date" value={backtestStart} onChange={(e) => setBacktestStart(e.target.value)} className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800" />
          </label>
          <label className="block text-xs font-medium text-slate-500">
            End Date
            <input type="date" value={backtestEnd} onChange={(e) => setBacktestEnd(e.target.value)} className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800" />
          </label>
        </div>
      </Card>

      {/* Payoff + Metrics */}
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
              <MetricCard label="Legs" value={String(legs.length + lazyLegs.length)} />
            </div>
          ) : (
            <p className="py-6 text-center text-sm text-slate-400">—</p>
          )}
        </Card>
      </div>

      {/* Actions */}
      <div className="flex flex-wrap gap-2">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Strategy name" className="w-64 rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-800" />
        <button onClick={save} disabled={busy} className="rounded-md bg-blue-600 px-4 py-1.5 text-xs font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-60">
          {busy ? "Working…" : "Save strategy"}
        </button>
        <button onClick={backtest} disabled={busy} className="rounded-md border border-slate-300 px-4 py-1.5 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-50 disabled:opacity-60">
          Backtest
        </button>
      </div>
      {message && <p className="text-xs text-emerald-600">{message}</p>}
      {error && <p className="text-xs text-red-600">{error}</p>}
      {chainError && <p className="text-xs text-amber-600">{chainError}</p>}

      {s && (
        <Card title="Backtest result">
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

      <Card title="Saved strategies">
        {saved.length === 0 ? (
          <p className="py-4 text-center text-sm text-slate-400">No strategies yet.</p>
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
