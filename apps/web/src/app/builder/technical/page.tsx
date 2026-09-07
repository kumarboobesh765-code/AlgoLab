"use client";

import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@/lib/auth";
import { api, type BacktestRun, type Instrument, type OptionChain, type Strategy } from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { MetricCard } from "@/components/ui/MetricCard";
import IndicatorsEditor from "@/components/builder/IndicatorsEditor";
import ConditionGroupEditor from "@/components/builder/ConditionGroupEditor";
import {
  EMPTY_META,
  useBuilderWorkflow,
  type StrategyMeta,
} from "@/lib/builder-workflow";
import {
  STRATEGY_EDIT_KEY,
  TEMPLATE_HANDOFF_KEY,
  TEMPLATE_HANDOFF_NAME,
  type ConditionGroup,
  type IndicatorDef,
  type OptionLeg,
  type StrategyDefinitionV1,
} from "@/lib/builders";
import { useAppSettings } from "@/lib/settings";

export { TEMPLATE_HANDOFF_KEY, TEMPLATE_HANDOFF_NAME };

/* ------------------------------------------------------------------ */
/* Constants                                                          */
/* ------------------------------------------------------------------ */

const UNDERLYINGS = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"];
const STRIKE_STEPS: Record<string, number> = {
  NIFTY: 50, BANKNIFTY: 100, FINNIFTY: 50, MIDCPNIFTY: 75, SENSEX: 100,
};

const TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "1d"] as const;
const CANDLE_FIELDS = ["Equity", "Futures", "Index"];
const CHART_TYPES = ["Candle", "Line"];
const SEGMENTS = [
  { key: "weekly_monthly" as const, label: "Weekly & Monthly Expiries", sub: "NIFTY | SENSEX" },
  { key: "stocks" as const, label: "Stocks - Cash / F&O", sub: "ALL NIFTY 500 STOCKS" },
  { key: "crypto" as const, label: "Crypto", sub: "Delta Exchange & CoinSwitch" },
];
const TRADE_TYPES = [
  { value: "intraday" as const, label: "Intraday" },
  { value: "intraday_same_day" as const, label: "Same-Day Square-off" },
  { value: "btst" as const, label: "BTST" },
  { value: "positional" as const, label: "Positional" },
];
const EXPIRIES = [
  { value: "WEEKLY", label: "Weekly" },
  { value: "NEXT_WEEKLY", label: "Next Weekly" },
  { value: "MONTHLY", label: "Monthly" },
  { value: "NEXT_MONTHLY", label: "Next Monthly" },
];
const STRIKE_OFFSETS = [
  { value: -5, label: "ITM5" }, { value: -4, label: "ITM4" }, { value: -3, label: "ITM3" },
  { value: -2, label: "ITM2" }, { value: -1, label: "ITM1" }, { value: 0, label: "ATM" },
  { value: 1, label: "OTM1" }, { value: 2, label: "OTM2" }, { value: 3, label: "OTM3" },
  { value: 4, label: "OTM4" }, { value: 5, label: "OTM5" },
];
const ADJUSTMENTS = [
  { value: "none", label: "Off" },
  { value: "asap", label: "ASAP" },
  { value: "asap_reverse", label: "ASAP Reverse" },
  { value: "cost", label: "At Cost" },
  { value: "cost_reverse", label: "At Cost Reverse" },
];
const LEG_PRESETS: { name: string; legs: { action: "buy" | "sell"; option_type: "CE" | "PE"; strike_offset: number }[] }[] = [
  { name: "Long Straddle", legs: [{ action: "buy", option_type: "CE", strike_offset: 0 }, { action: "buy", option_type: "PE", strike_offset: 0 }] },
  { name: "Short Straddle", legs: [{ action: "sell", option_type: "CE", strike_offset: 0 }, { action: "sell", option_type: "PE", strike_offset: 0 }] },
  { name: "Bull Call Spread", legs: [{ action: "buy", option_type: "CE", strike_offset: 0 }, { action: "sell", option_type: "CE", strike_offset: 1 }] },
  { name: "Bear Put Spread", legs: [{ action: "buy", option_type: "PE", strike_offset: 0 }, { action: "sell", option_type: "PE", strike_offset: -1 }] },
  { name: "Iron Condor", legs: [{ action: "sell", option_type: "CE", strike_offset: 1 }, { action: "sell", option_type: "PE", strike_offset: -1 }, { action: "buy", option_type: "CE", strike_offset: 2 }, { action: "buy", option_type: "PE", strike_offset: -2 }] },
];

/* ------------------------------------------------------------------ */
/* Types                                                              */
/* ------------------------------------------------------------------ */

interface CaseRow {
  id: string;
  name: string;
  entry: ConditionGroup;
  exit: ConditionGroup;
}

interface LegRow {
  id: string;
  lots: number;
  action: "buy" | "sell";
  option_type: "CE" | "PE";
  expiry: "WEEKLY" | "NEXT_WEEKLY" | "MONTHLY" | "NEXT_MONTHLY";
  strike_offset: number;
  slPts: string;
  slPct: string;
  tpPts: string;
  tpPct: string;
  moveToCost: boolean;
  adjustment: string;
  reentryMax: string;
  reexecute: boolean;
  openNewLegs: boolean;
  advancedOpen: boolean;
}

function uid(prefix: string): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 8)}`;
}

function mkCase(index: number): CaseRow {
  return {
    id: uid("case"),
    name: `Case ${index}`,
    entry: { logic: "ALL", conditions: [] },
    exit: { logic: "ALL", conditions: [] },
  };
}

function mkLeg(): LegRow {
  return {
    id: uid("leg"),
    lots: 1,
    action: "buy",
    option_type: "CE",
    expiry: "WEEKLY",
    strike_offset: 0,
    slPts: "",
    slPct: "",
    tpPts: "",
    tpPct: "",
    moveToCost: false,
    adjustment: "none",
    reentryMax: "0",
    reexecute: false,
    openNewLegs: false,
    advancedOpen: false,
  };
}

function isoDaysFromNow(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/* ------------------------------------------------------------------ */
/* Definition assembly                                                */
/* ------------------------------------------------------------------ */

function nonEmptyGroups(groups: ConditionGroup[]): ConditionGroup[] {
  return groups.filter((g) => g.conditions.length > 0);
}

/** Entry/exit always needs at least one condition (backend min_length=1). */
const ALWAYS_TRUE: ConditionGroup = {
  logic: "ALL",
  conditions: [
    {
      left: { kind: "price", price: "close" },
      op: "GT",
      right: { kind: "constant", value: 0 },
    },
  ],
};

function mergeCases(groups: ConditionGroup[], logic: "ALL" | "ANY"): ConditionGroup {
  const groupsNonNull = nonEmptyGroups(groups);
  if (groupsNonNull.length === 0) return ALWAYS_TRUE;
  if (groupsNonNull.length === 1) return groupsNonNull[0];
  return { logic, conditions: groupsNonNull };
}

function hasAnyCondition(groups: ConditionGroup[]): boolean {
  return groups.some((g) => g.conditions.length > 0);
}

function num(raw: string): number | null {
  const n = Number(raw);
  return raw.trim() !== "" && Number.isFinite(n) ? n : null;
}

/** Returns { mode, value } picking per-leg value first, then transaction-target fallback. */
function slConfig(
  leg: LegRow,
  txPts: string,
  txPct: string,
): { mode: "pts" | "%"; value: number } | null {
  const v = num(leg.slPts) ?? num(txPts);
  if (v !== null && (leg.slPts.trim() || txPts.trim())) return { mode: "pts", value: v };
  const pct = num(leg.slPct) ?? num(txPct);
  if (pct !== null && (leg.slPct.trim() || txPct.trim())) return { mode: "%", value: pct };
  return null;
}

function targetConfig(
  leg: LegRow,
  txPts: string,
  txPct: string,
): { mode: "pts" | "%"; value: number } | null {
  const v = num(leg.tpPts) ?? num(txPts);
  if (v !== null && (leg.tpPts.trim() || txPts.trim())) return { mode: "pts", value: v };
  const pct = num(leg.tpPct) ?? num(txPct);
  if (pct !== null && (leg.tpPct.trim() || txPct.trim())) return { mode: "%", value: pct };
  return null;
}

/* ------------------------------------------------------------------ */
/* Page                                                               */
/* ------------------------------------------------------------------ */

export default function TechnicalBuilderPage() {
  const { user, loading: authLoading } = useAuth();
  const workflow = useBuilderWorkflow();
  const savedTimeframe = useAppSettings().timeframe;

  /* header / backtest meta */
  const [mode, setMode] = useState<"backtest" | "live">("backtest");
  const [meta, setMeta] = useState<StrategyMeta>(EMPTY_META);
  const [editingId, setEditingId] = useState<string | null>(null);

  /* duration */
  const [startDate, setStartDate] = useState(() => isoDaysFromNow(-30));
  const [endDate, setEndDate] = useState(() => isoDaysFromNow(0));

  /* instrument + candle */
  const [segment, setSegment] = useState<"weekly_monthly" | "stocks" | "crypto">("weekly_monthly");
  const [symbol, setSymbol] = useState("NIFTY");
  const [exchange, setExchange] = useState("NSE");
  const [underlyingSource, setUnderlyingSource] = useState<"cash" | "futures">("cash");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [candleName, setCandleName] = useState("Current");
  const [candleInterval, setCandleInterval] = useState<typeof TIMEFRAMES[number]>(savedTimeframe as typeof TIMEFRAMES[number]);
  const [candleFields, setCandleFields] = useState("Equity");
  const [chartType, setChartType] = useState("Candle");
  const [indicators, setIndicators] = useState<IndicatorDef[]>([]);

  /* features */
  const [featTrailing, setFeatTrailing] = useState(false);
  const [trailingPct, setTrailingPct] = useState("1.0");
  const [featReentry, setFeatReentry] = useState(false);
  const [featReexecute, setFeatReexecute] = useState(false);
  const [featMultipleCase, setFeatMultipleCase] = useState(false);

  /* cases */
  const [cases, setCases] = useState<CaseRow[]>([mkCase(1)]);

  /* legs */
  const [legs, setLegs] = useState<LegRow[]>([]);

  /* targets */
  const [txSlPct, setTxSlPct] = useState("");
  const [txSlPts, setTxSlPts] = useState("");
  const [txTpPct, setTxTpPct] = useState("");
  const [txTpPts, setTxTpPts] = useState("");
  const [dailySl, setDailySl] = useState("");
  const [dailyTp, setDailyTp] = useState("");

  /* strategy settings */
  const [defaultExpiry, setDefaultExpiry] = useState<"WEEKLY" | "NEXT_WEEKLY" | "MONTHLY" | "NEXT_MONTHLY">("WEEKLY");
  const [tradeType, setTradeType] = useState<"intraday" | "intraday_same_day" | "btst" | "positional">("intraday");
  const [tradeFrom, setTradeFrom] = useState("09:35");
  const [tradeTo, setTradeTo] = useState("15:15");
  const [maxTxns, setMaxTxns] = useState("0");

  /* runtime */
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<BacktestRun | null>(null);
  const [savedId, setSavedId] = useState<string | null>(null);
  const [chain, setChain] = useState<OptionChain | null>(null);
  const [lotSizes, setLotSizes] = useState<Record<string, number>>({});

  const hasLegs = legs.length > 0;
  const step = STRIKE_STEPS[symbol] ?? 50;
  const lotSize = lotSizes[symbol] ?? 50;
  const spot = chain?.spot ?? 0;

  function applyDefinition(def: StrategyDefinitionV1) {
    if (def.instrument) {
      setSymbol(def.instrument.symbol ?? "NIFTY");
      setExchange(def.instrument.exchange ?? "NSE");
      if (def.instrument.segment === "cash") setSegment("stocks");
      else if (symbol.toUpperCase() === "BTCINR" || symbol.toUpperCase() === "ETHINR") setSegment("crypto");
    }
    if (def.timeframe) setCandleInterval(def.timeframe as typeof TIMEFRAMES[number]);
    if (def.indicators) setIndicators(def.indicators);
    if (def.strategy_type) setTradeType(def.strategy_type);
    if (def.max_position_in_a_day !== undefined) setMaxTxns(String(def.max_position_in_a_day));
    if (def.time_control) {
      if (def.time_control.no_entry_after) setTradeFrom(def.time_control.no_entry_after);
      if (def.time_control.time_exit) setTradeTo(def.time_control.time_exit);
    }
    if (def.overall) {
      if (def.overall.overall_sl !== null) setDailySl(String(def.overall.overall_sl));
      if (def.overall.overall_target !== null) setDailyTp(String(def.overall.overall_target));
    }
    if (def.risk) {
      if (def.risk.stop_loss_pct !== null) setTxSlPct(String(def.risk.stop_loss_pct));
      if (def.risk.target_pct !== null) setTxTpPct(String(def.risk.target_pct));
      if (def.risk.trailing_sl_pct !== null) {
        setFeatTrailing(true);
        setTrailingPct(String(def.risk.trailing_sl_pct));
      }
    }
    setCases([{ id: uid("case"), name: "Case 1", entry: def.entry, exit: def.exit ?? { logic: "ALL", conditions: [] } }]);
    if (def.legs && def.legs.length > 0) {
      setLegs(
        def.legs.map((leg) => ({
          id: uid("leg"),
          lots: leg.lots ?? 1,
          action: leg.action,
          option_type: leg.option_type,
          expiry: (leg.expiry_formula?.toUpperCase() as LegRow["expiry"]) ?? "WEEKLY",
          strike_offset: leg.strike_offset ?? 0,
          slPts: leg.sl_mode === "pts" && leg.sl_value !== null ? String(leg.sl_value) : "",
          slPct: leg.sl_mode === "%" && leg.sl_value !== null ? String(leg.sl_value) : "",
          tpPts: leg.target_mode === "pts" && leg.target_value !== null ? String(leg.target_value) : "",
          tpPct: leg.target_mode === "%" && leg.target_value !== null ? String(leg.target_value) : "",
          moveToCost: false,
          adjustment: leg.reentry_on_sl ?? "none",
          reentryMax: String(leg.max_reentries ?? 0),
          reexecute: leg.reentry_on_target === "reexecute",
          openNewLegs: false,
          advancedOpen: false,
        })),
      );
    }
  }

  /* strategy-library handoff ("Edit from library" / template handoff) */
  useEffect(() => {
    let raw: string | null = null;
    let name: string | null = null;
    let editId: string | null = null;
    try {
      raw = sessionStorage.getItem(TEMPLATE_HANDOFF_KEY);
      name = sessionStorage.getItem(TEMPLATE_HANDOFF_NAME);
      editId = sessionStorage.getItem(STRATEGY_EDIT_KEY);
      if (raw !== null) sessionStorage.removeItem(TEMPLATE_HANDOFF_KEY);
      if (name !== null) sessionStorage.removeItem(TEMPLATE_HANDOFF_NAME);
      if (editId !== null) sessionStorage.removeItem(STRATEGY_EDIT_KEY);
    } catch {
      return;
    }
    if (raw === null && editId === null) return;
    Promise.resolve().then(() => {
      let def: StrategyDefinitionV1 | null = null;
      if (raw !== null) {
        try {
          def = JSON.parse(raw) as StrategyDefinitionV1;
        } catch {
          setError("Handoff definition is not valid JSON — starting with a blank builder.");
        }
      }
      if (name) setMeta((m) => ({ ...m, name }));
      if (editId !== null) setEditingId(editId);
      if (def) applyDefinition(def);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* market data: option chain + lot sizes (only meaningful in legs mode) */
  useEffect(() => {
    let cancelled = false;
    api<Instrument[]>("/market/instruments")
      .then((list) => {
        if (!cancelled) {
          setLotSizes(Object.fromEntries(list.map((i) => [i.symbol.toUpperCase(), i.lot_size])));
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (!hasLegs) return;
    api<OptionChain>(`/market/option-chain?underlying=${symbol}`)
      .then((c) => {
        if (!cancelled) setChain(c);
      })
      .catch(() => {
        if (!cancelled) setChain(null);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, hasLegs]);

  const indicatorContext = useMemo(() => {
    const outputs: Record<string, string[]> = {};
    for (const ind of indicators) {
      const entry = workflow.catalog?.indicators.find((c) => c.type === ind.type);
      outputs[ind.id] = entry?.outputs ?? [];
    }
    return {
      indicatorIds: indicators.map((i) => i.id),
      indicatorOutputs: outputs,
      variableNames: [],
    };
  }, [indicators, workflow.catalog]);

  /* ------------------------------------------------------------------ */
  /* Definition builder                                                 */
  /* ------------------------------------------------------------------ */

  const definition = useMemo<StrategyDefinitionV1>(() => {
    const instrumentSegment = segment === "stocks" ? "cash" : segment === "crypto" ? "crypto" : "index";
    const legOut: OptionLeg[] = legs.map((l) => {
      const sl = slConfig(l, txSlPts, txSlPct);
      const tp = targetConfig(l, txTpPts, txTpPct);
      const reentryOnSl =
        l.adjustment !== "none"
          ? (l.adjustment as OptionLeg["reentry_on_sl"])
          : featReentry
            ? ("asap" as const)
            : null;
      const reentryOnTarget =
        l.reexecute || featReexecute ? ("reexecute" as const) : null;
      const maxRe = Math.max(0, Math.min(20, num(l.reentryMax) ?? 0));
      return {
        action: l.action,
        option_type: l.option_type,
        strike_selection: "strike_type" as const,
        strike_offset: l.strike_offset,
        lots: Math.max(1, l.lots),
        expiry_formula: l.expiry,
        square_off: "partial" as const,
        ...(sl ? { sl_mode: sl.mode, sl_value: sl.value } : {}),
        ...(tp ? { target_mode: tp.mode, target_value: tp.value } : {}),
        ...(reentryOnSl ? { reentry_on_sl: reentryOnSl, max_reentries: maxRe } : {}),
        ...(reentryOnTarget ? { reentry_on_target: reentryOnTarget, max_reentries: maxRe } : {}),
      } as OptionLeg;
    });

    const entry = mergeCases(cases.map((c) => c.entry), "ANY");
    const hasExit = hasAnyCondition(cases.map((c) => c.exit));
    const exit = hasExit ? mergeCases(cases.map((c) => c.exit), "ANY") : null;

    const riskValue =
      txSlPct || txTpPct || featTrailing
        ? {
            stop_loss_pct: num(txSlPct),
            target_pct: num(txTpPct),
            trailing_sl_pct: featTrailing ? num(trailingPct) : null,
          }
        : null;

    const overall =
      dailySl || dailyTp
        ? {
            overall_sl: num(dailySl),
            overall_target: num(dailyTp),
            overall_trail_sl: null,
            overall_trail_every: null,
            lock_profit: null,
            lock_at: null,
            lock_and_trail_profit: null,
            lock_and_trail_at: null,
            lock_and_trail_by: null,
          }
        : null;

    return {
      version: 1,
      builder: hasLegs ? "legs" : "technical",
      timeframe: candleInterval,
      instrument: { symbol, exchange, segment: instrumentSegment },
      variables: [],
      indicators,
      entry,
      exit: hasExit ? exit : null,
      risk: riskValue,
      position: {
        direction: "long_only",
        quantity_type: "fixed",
        quantity: 1,
        capital_pct: null,
      },
      strategy_type: tradeType,
      skip_initial_candles: 0,
      max_position_in_a_day: Math.max(0, num(maxTxns) ?? 0),
      cash_or_futures: underlyingSource,
      reentry_time_restriction: featReentry ? "none" : "none",
      ...(hasLegs ? { legs: legOut } : {}),
      ...(overall ? { overall } : {}),
      time_control: {
        no_entry_after: tradeFrom || null,
        no_reentry_after: featReentry && tradeFrom ? tradeFrom : null,
        time_exit: tradeTo || null,
      },
      legwise: {
        trail_sl_to_breakeven: legs.some((l) => l.moveToCost) ? ("all_legs" as const) : ("none" as const),
        square_off_on_leg_sl: false,
      },
    };
  }, [
    segment, legs, txSlPts, txSlPct, txTpPts, txTpPct, featReentry, featReexecute,
    dailySl, dailyTp, candleInterval, symbol, exchange, indicators, cases, tradeType,
    maxTxns, underlyingSource, tradeFrom, tradeTo, featTrailing, trailingPct,
  ]);

  /* ------------------------------------------------------------------ */
  /* Actions                                                            */
  /* ------------------------------------------------------------------ */

  const patchCase = (id: string, patch: Partial<CaseRow>) =>
    setCases((prev) => prev.map((c) => (c.id === id ? { ...c, ...patch } : c)));
  const removeCase = (id: string) =>
    setCases((prev) => (prev.length <= 1 ? prev : prev.filter((c) => c.id !== id)));
  const addCase = () =>
    setCases((prev) => [...prev, mkCase(prev.length + 1)]);

  const patchLeg = (id: string, patch: Partial<LegRow>) =>
    setLegs((prev) => prev.map((l) => (l.id === id ? { ...l, ...patch } : l)));
  const removeLeg = (id: string) =>
    setLegs((prev) => (prev.length <= 1 ? prev : prev.filter((l) => l.id !== id)));
  const addLeg = () => setLegs((prev) => [...prev, mkLeg()]);
  const applyPreset = (preset: (typeof LEG_PRESETS)[number]) => {
    setLegs(preset.legs.map((p) => ({ ...mkLeg(), action: p.action, option_type: p.option_type, strike_offset: p.strike_offset })));
    setRun(null);
    setMessage(null);
  };

  const doSave = async (): Promise<string> => {
    if (savedId) return savedId;
    const created = await api<Strategy>("/strategies", {
      method: "POST",
      body: JSON.stringify({
        name: meta.name.trim() || "Untitled Strategy",
        description: meta.description || null,
        underlying: symbol,
        exchange,
        strategy_type: "options",
        tags: ["builder", ...(hasLegs ? ["legs"] : ["technical"])],
        definition,
      }),
    });
    setSavedId(created.id);
    return created.id;
  };

  const handleSave = async () => {
    setBusy(true);
    setError(null);
    try {
      const created = await doSave();
      setMessage(`Saved — id ${created.slice(0, 8)}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const handleValidate = async () => {
    setError(null);
    setMessage(null);
    try {
      await workflow.validate(definition);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Validation failed");
    }
  };

  const handlePreview = async () => {
    if (!hasLegs) {
      setError(null);
      await workflow.runPreview(definition);
    } else {
      setMessage("Signal preview is for technical strategies — use Run Backtest for legs.");
    }
  };

  const handleBacktest = async () => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const id = await doSave();
      const r = await api<BacktestRun>("/backtests", {
        method: "POST",
        body: JSON.stringify({
          strategy_id: id,
          start: startDate,
          end: endDate,
          initial_capital: 100000,
          costs_pct: 0.05,
        }),
      });
      setRun(r);
      const summary = r.result_summary?.summary;
      setMessage(
        summary
          ? `Backtest complete — return ${summary.return_pct.toFixed(2)}% over ${summary.total_trades} trade(s).`
          : r.status === "failed"
            ? "Backtest failed — see result below."
            : "Backtest run submitted.",
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Backtest failed");
    } finally {
      setBusy(false);
    }
  };

  const s = run?.result_summary?.summary ?? null;
  const durationDays = Math.max(0, Math.round((new Date(endDate).getTime() - new Date(startDate).getTime()) / 86400000));
  const durationLabel =
    durationDays === 0
      ? "intraday"
      : durationDays < 45
        ? `≈ ${Math.max(1, Math.round(durationDays / 30))} month${Math.round(durationDays / 30) > 1 ? "s" : ""}`
        : `≈ ${(durationDays / 365).toFixed(1)} years`;

  if (!authLoading && !user) {
    return (
      <Card>
        <div className="py-10 text-center">
          <p className="text-sm text-slate-500">Connecting to the API…</p>
        </div>
      </Card>
    );
  }

  const canSave = meta.name.trim().length > 0;

  /* ------------------------------------------------------------------ */
  /* Render                                                             */
  /* ------------------------------------------------------------------ */

  return (
    <div className="space-y-4">
      {/* Header toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-3 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
        <div className="flex items-center gap-3">
          <div>
            <h1 className="text-lg font-semibold text-slate-800">Strategy Builder</h1>
            <p className="text-xs text-slate-400">
              {editingId ? "Editing an existing strategy — saving creates a new version." : "Build technical or options strategies the way you trade them."}
            </p>
          </div>
          <div className="flex gap-0 overflow-hidden rounded-lg border border-slate-200">
            <button
              onClick={() => setMode("backtest")}
              className={`px-4 py-2 text-sm font-semibold transition-colors ${mode === "backtest" ? "bg-slate-800 text-white" : "bg-white text-slate-500 hover:bg-slate-50"}`}
            >
              Backtest
            </button>
            <button
              onClick={() => setMode("live")}
              className={`px-4 py-2 text-sm font-semibold transition-colors ${mode === "live" ? "bg-blue-600 text-white" : "bg-white text-slate-500 hover:bg-slate-50"}`}
            >
              Live
            </button>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="amber">DEMO DATA</Badge>
          <button
            onClick={handleValidate}
            disabled={workflow.validating || busy}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            {workflow.validating ? "Validating…" : "Validate"}
          </button>
          <button
            onClick={handlePreview}
            disabled={workflow.previewing || busy || (hasLegs && false)}
            className="rounded-lg border border-blue-300 bg-blue-50 px-3 py-2 text-sm font-medium text-blue-700 hover:bg-blue-100 disabled:opacity-50"
          >
            {workflow.previewing ? "Previewing…" : "Preview signals"}
          </button>
          <button
            onClick={handleBacktest}
            disabled={!canSave || busy || mode === "live"}
            title={!canSave ? "Enter a Run Name first" : mode === "live" ? "Live trading is disabled in V1 — research only" : undefined}
            className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-900 disabled:opacity-50"
          >
            {busy ? "Working…" : "Run Backtest"}
          </button>
          <button
            onClick={handleSave}
            disabled={!canSave || busy}
            title={!canSave ? "Enter a Run Name first" : undefined}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            Save
          </button>
        </div>
      </div>

      {mode === "live" && (
        <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700">
          <strong>Live trading is disabled in V1.</strong> This platform is research, backtesting, and paper trading
          only — you can still configure and save your strategy; it just won&apos;t place real orders.
        </div>
      )}

      {(error || workflow.saveError) && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-600 ring-1 ring-inset ring-red-200">
          {error ?? workflow.saveError}
        </p>
      )}
      {(message || (workflow.validation && !workflow.validation.valid)) && (
        <p
          className={`rounded-md px-3 py-2 text-xs ring-1 ring-inset ${
            workflow.validation && !workflow.validation.valid
              ? "bg-amber-50 text-amber-700 ring-amber-200"
              : "bg-emerald-50 text-emerald-700 ring-emerald-200"
          }`}
        >
          {message ??
            `Definition invalid — ${workflow.validation?.errors.length} error(s): ${workflow.validation?.errors.slice(0, 3).join(" · ")}`}
        </p>
      )}

      {/* Backtest duration */}
      <Card
        title="Backtest Duration"
        actions={
          <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-medium text-slate-500">
            {durationLabel}
          </span>
        }
      >
        <div className="grid gap-3 md:grid-cols-2">
          <label className="block text-xs font-medium text-slate-500">
            From
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
            />
          </label>
          <label className="block text-xs font-medium text-slate-500">
            To
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
            />
          </label>
        </div>
      </Card>

      {/* Run + folder + instrument */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Run & Folder">
          <div className="grid gap-3">
            <label className="block text-xs font-medium text-slate-500">
              Run Name
              <input
                value={meta.name}
                onChange={(e) => setMeta((m) => ({ ...m, name: e.target.value }))}
                placeholder="e.g. NIFTY Monthly Iron Condor"
                className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
              />
            </label>
            <div className="grid gap-3 md:grid-cols-2">
              <label className="block text-xs font-medium text-slate-500">
                Folder Name
                <input
                  value={meta.description ?? ""}
                  onChange={(e) => setMeta((m) => ({ ...m, description: e.target.value }))}
                  placeholder="Optional folder"
                  className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
                />
              </label>
              <label className="block text-xs font-medium text-slate-500">
                Exchange
                <select value={exchange} onChange={(e) => setExchange(e.target.value)} className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800">
                  <option>NSE</option>
                  <option>BSE</option>
                </select>
              </label>
            </div>
          </div>
        </Card>

        <Card title="Instrument" actions={<Badge tone="blue">{hasLegs ? "Options mode" : "Technical mode"}</Badge>}>
          <div className="mb-3 flex gap-0 rounded-lg border border-slate-200 overflow-hidden">
            {(["cash", "futures"] as const).map((v) => (
              <button
                key={v}
                onClick={() => setUnderlyingSource(v)}
                className={`flex-1 px-3 py-2 text-xs font-medium capitalize transition-colors ${underlyingSource === v ? "bg-blue-600 text-white" : "bg-white text-slate-600 hover:bg-slate-50"}`}
              >
                {v}
              </button>
            ))}
          </div>
          <label className="block text-xs font-medium text-slate-500">
            Underlying / Symbol
            {segment === "stocks" ? (
              <input
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                placeholder="RELIANCE"
                className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
              />
            ) : (
              <select value={symbol} onChange={(e) => setSymbol(e.target.value)} className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800">
                {(segment === "crypto" ? ["BTCINR", "ETHINR"] : UNDERLYINGS).map((u) => (
                  <option key={u}>{u}</option>
                ))}
              </select>
            )}
          </label>
          {hasLegs && (chain || spot) && (
            <p className="mt-2 text-[11px] text-slate-400 tabular-nums">
              {spot ? `${symbol} spot ${spot.toFixed(0)} · lot ${lotSize} · step ${step}` : "Loading option chain…"}
            </p>
          )}
        </Card>
      </div>

      {/* Advanced: indicators + current candle */}
      <Card
        title="Advanced"
        actions={
          <button
            onClick={() => setAdvancedOpen((v) => !v)}
            className="flex items-center gap-1 text-xs font-medium text-blue-600 hover:underline"
          >
            <span className="inline-block transition-transform" style={{ transform: advancedOpen ? "rotate(90deg)" : undefined }}>▸</span>
            {advancedOpen ? "Hide Indicators & Candle" : "Indicators & Current Candle"}
          </button>
        }
      >
        {advancedOpen && (
          <div className="grid gap-4 lg:grid-cols-2">
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Indicators</h3>
              <IndicatorsEditor
                definition={indicators}
                catalog={workflow.catalog}
                catalogError={workflow.catalogError}
                onChange={setIndicators}
              />
            </div>
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Current Candle</h3>
              <div className="grid gap-3 md:grid-cols-2">
                <label className="block text-xs font-medium text-slate-500">
                  Name
                  <input value={candleName} onChange={(e) => setCandleName(e.target.value)} className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800" />
                </label>
                <label className="block text-xs font-medium text-slate-500">
                  Candle Interval
                  <select
                    value={candleInterval}
                    onChange={(e) => setCandleInterval(e.target.value as typeof TIMEFRAMES[number])}
                    className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
                  >
                    {TIMEFRAMES.map((t) => (
                      <option key={t} value={t}>{t === "1m" ? "1 Minute" : t === "1h" ? "1 Hour" : t === "1d" ? "1 Day" : `${t.replace("m", "")} Minutes`}</option>
                    ))}
                  </select>
                </label>
                <label className="block text-xs font-medium text-slate-500">
                  Fields
                  <select value={candleFields} onChange={(e) => setCandleFields(e.target.value)} className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800">
                    {CANDLE_FIELDS.map((f) => <option key={f}>{f}</option>)}
                  </select>
                </label>
                <label className="block text-xs font-medium text-slate-500">
                  Chart Type
                  <select value={chartType} onChange={(e) => setChartType(e.target.value)} className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800">
                    {CHART_TYPES.map((c) => <option key={c}>{c}</option>)}
                  </select>
                </label>
              </div>
            </div>
          </div>
        )}
      </Card>

      {/* Features enablement */}
      <Card title="Features Enablement">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <FeatureToggle
            label="Trailing Stop Loss"
            checked={featTrailing}
            onChange={(v) => setFeatTrailing(v)}
            input={featTrailing ? { value: trailingPct, set: setTrailingPct, suffix: "%" } : undefined}
          />
          <FeatureToggle label="Re-Entry" checked={featReentry} onChange={(v) => setFeatReentry(v)} hint="Allows re-entry on SL/target" />
          <FeatureToggle label="Re-Execute" checked={featReexecute} onChange={(v) => setFeatReexecute(v)} hint="Re-open leg at cost after target" />
          <FeatureToggle label="Multiple Case" checked={featMultipleCase} onChange={(v) => setFeatMultipleCase(v)} hint="Run several entry/exit cases in parallel" />
        </div>
      </Card>

      {/* Parallel cases */}
      <Card
        title="Parallel Cases"
        subtitle="Each case runs its own Entry and Exit rules over the same legs."
        actions={
          <button
            onClick={addCase}
            disabled={cases.length >= 3 && !featMultipleCase}
            title={!featMultipleCase && cases.length >= 3 ? "Enable Multiple Case to add more" : undefined}
            className="rounded-md border border-dashed border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-40"
          >
            + Add case
          </button>
        }
      >
        <div className="space-y-4">
          {cases.map((c) => (
            <div key={c.id} className="rounded-xl border border-slate-200 p-3">
              <div className="mb-3 flex items-center justify-between gap-2">
                <input
                  value={c.name}
                  onChange={(e) => patchCase(c.id, { name: e.target.value })}
                  className="w-40 rounded-md border border-slate-300 px-2 py-1 text-xs font-semibold text-slate-700"
                />
                <button onClick={() => removeCase(c.id)} className="text-[11px] text-red-500 hover:underline disabled:opacity-30" disabled={cases.length <= 1}>
                  Remove case
                </button>
              </div>
              <div className="grid gap-3 lg:grid-cols-2">
                <ConditionGroupEditor
                  group={c.entry}
                  title="Entry When"
                  tone="green"
                  context={indicatorContext}
                  onChange={(next) => patchCase(c.id, { entry: next })}
                />
                <ConditionGroupEditor
                  group={c.exit}
                  title="Exit When"
                  tone="red"
                  context={indicatorContext}
                  onChange={(next) => patchCase(c.id, { exit: next })}
                />
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Action / Legs */}
      <Card
        title="Action"
        actions={
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Presets</span>
            {LEG_PRESETS.map((p) => (
              <button
                key={p.name}
                onClick={() => applyPreset(p)}
                className="rounded-full border border-slate-200 px-2.5 py-1 text-[11px] font-medium text-slate-600 transition-colors hover:bg-slate-50"
              >
                {p.name}
              </button>
            ))}
          </div>
        }
      >
        <div className="mb-3 flex gap-0 border-b border-slate-200">
          {SEGMENTS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setSegment(tab.key)}
              className={`flex-1 px-3 py-2 text-center text-xs font-medium transition-colors ${segment === tab.key ? "border-b-2 border-blue-600 text-blue-600" : "text-slate-500 hover:text-slate-700"}`}
            >
              {tab.label}
              <span className="block text-[10px] text-slate-400">{tab.sub}</span>
            </button>
          ))}
        </div>
        <p className="mb-3 text-[11px] text-slate-400">
          Add legs to trade options. With no legs the strategy is driven purely by the case conditions (technical mode).
        </p>

        {hasLegs ? (
          <div className="space-y-2">
            {legs.map((l, idx) => (
              <div key={l.id} className="rounded-lg border border-slate-200 bg-white">
                {/* Leg header row */}
                <div className="flex flex-wrap items-center gap-2 px-3 py-2">
                  <span className="w-6 text-xs font-bold text-slate-400">#{idx + 1}</span>
                  <select
                    value={l.lots}
                    onChange={(e) => patchLeg(l.id, { lots: Math.max(1, Number(e.target.value)) })}
                    className="w-14 rounded border border-slate-300 px-1.5 py-1 text-xs text-slate-800"
                  >
                    {Array.from({ length: 10 }, (_, k) => k + 1).map((n) => (
                      <option key={n} value={n}>{n}</option>
                    ))}
                  </select>
                  <select value={l.action} onChange={(e) => patchLeg(l.id, { action: e.target.value as LegRow["action"] })} className="rounded border border-slate-300 px-2 py-1 text-xs font-medium text-slate-800">
                    <option value="buy">Buy</option>
                    <option value="sell">Sell</option>
                  </select>
                  <select value={l.option_type} onChange={(e) => patchLeg(l.id, { option_type: e.target.value as LegRow["option_type"] })} className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-800">
                    <option value="CE">CE</option>
                    <option value="PE">PE</option>
                  </select>
                  <select
                    value={l.expiry}
                    onChange={(e) => patchLeg(l.id, { expiry: e.target.value as LegRow["expiry"] })}
                    className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-800"
                  >
                    {EXPIRIES.map((e) => (
                      <option key={e.value} value={e.value}>{e.label}</option>
                    ))}
                  </select>
                  <select
                    value={l.strike_offset}
                    onChange={(e) => patchLeg(l.id, { strike_offset: Number(e.target.value) })}
                    className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-800"
                  >
                    {STRIKE_OFFSETS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                  <span className="text-[10px] text-slate-400 tabular-nums">
                    {spot ? `${Math.round((spot + l.strike_offset * step) / step) * step} ${l.option_type} · lot ${lotSize}` : "loading chain…"}
                  </span>
                  <div className="ml-auto flex items-center gap-2">
                    <button
                      onClick={() => patchLeg(l.id, { advancedOpen: !l.advancedOpen })}
                      className="text-[11px] font-medium text-blue-600 hover:underline"
                    >
                      {l.advancedOpen ? "Hide advanced" : "Advanced Options"}
                    </button>
                    <button onClick={() => removeLeg(l.id)} className="text-[11px] text-red-500 hover:underline disabled:opacity-30" disabled={legs.length <= 1}>
                      Remove
                    </button>
                  </div>
                </div>
                {/* Advanced options */}
                {l.advancedOpen && (
                  <div className="border-t border-slate-100 bg-slate-50/50 px-4 py-3">
                    <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
                      <div>
                        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">Stop Loss</p>
                        <div className="flex gap-1">
                          <input value={l.slPts} onChange={(e) => patchLeg(l.id, { slPts: e.target.value })} placeholder="Pts" className="w-full rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700" />
                          <input value={l.slPct} onChange={(e) => patchLeg(l.id, { slPct: e.target.value })} placeholder="%" className="w-full rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700" />
                        </div>
                      </div>
                      <div>
                        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">Take Profit</p>
                        <div className="flex gap-1">
                          <input value={l.tpPts} onChange={(e) => patchLeg(l.id, { tpPts: e.target.value })} placeholder="Pts" className="w-full rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700" />
                          <input value={l.tpPct} onChange={(e) => patchLeg(l.id, { tpPct: e.target.value })} placeholder="%" className="w-full rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700" />
                        </div>
                      </div>
                      <div>
                        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">Adjustment / ReEntry</p>
                        <select value={l.adjustment} onChange={(e) => patchLeg(l.id, { adjustment: e.target.value })} className="w-full rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700">
                          {ADJUSTMENTS.map((a) => (
                            <option key={a.value} value={a.value}>{a.label}</option>
                          ))}
                        </select>
                        {l.adjustment !== "none" && (
                          <input value={l.reentryMax} onChange={(e) => patchLeg(l.id, { reentryMax: e.target.value })} placeholder="Max re-entries" className="mt-1 w-full rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700" />
                        )}
                      </div>
                      <div className="space-y-2">
                        <label className="flex items-center gap-2 text-[11px] font-medium text-slate-600">
                          <input type="checkbox" checked={l.reexecute} onChange={(e) => patchLeg(l.id, { reexecute: e.target.checked })} className="rounded border-slate-300" />
                          Re-Execute
                        </label>
                        <label className="flex items-center gap-2 text-[11px] font-medium text-slate-600">
                          <input type="checkbox" checked={l.moveToCost} onChange={(e) => patchLeg(l.id, { moveToCost: e.target.checked })} className="rounded border-slate-300" />
                          Move to Cost
                        </label>
                        <label className="flex items-center gap-2 text-[11px] font-medium text-slate-600">
                          <input type="checkbox" checked={l.openNewLegs} onChange={(e) => patchLeg(l.id, { openNewLegs: e.target.checked })} className="rounded border-slate-300" />
                          Open New Legs
                        </label>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded-lg border border-dashed border-slate-300 py-6 text-center">
            <p className="text-xs text-slate-400">No legs configured — strategy runs on indicator conditions only.</p>
          </div>
        )}

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button onClick={addLeg} className="rounded-md border border-dashed border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50">
            + Add leg
          </button>
          <div className="ml-auto flex items-center gap-1 rounded-lg border border-amber-200 bg-amber-50/60 px-3 py-1.5">
            <span className="text-xs text-amber-700">Quick Adjustments</span>
            <Badge tone="amber">PRO — coming soon</Badge>
          </div>
        </div>
      </Card>

      {/* Transaction + daily targets */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Transaction Targets">
          <div className="grid gap-3 md:grid-cols-4">
            <label className="block text-[11px] font-medium text-slate-500">
              Stop Loss %
              <input value={txSlPct} onChange={(e) => setTxSlPct(e.target.value)} placeholder="—" className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800" />
            </label>
            <label className="block text-[11px] font-medium text-slate-500">
              Stop Loss Pts
              <input value={txSlPts} onChange={(e) => setTxSlPts(e.target.value)} placeholder="—" className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800" />
            </label>
            <label className="block text-[11px] font-medium text-slate-500">
              Take Profit %
              <input value={txTpPct} onChange={(e) => setTxTpPct(e.target.value)} placeholder="—" className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800" />
            </label>
            <label className="block text-[11px] font-medium text-slate-500">
              Take Profit Pts
              <input value={txTpPts} onChange={(e) => setTxTpPts(e.target.value)} placeholder="—" className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800" />
            </label>
          </div>
          <p className="mt-2 text-[10px] text-slate-400">
            Applied as the default per-transaction SL/TP (in premium points or %). Leg-level values override these.
          </p>
        </Card>

        <Card title="Daily Targets">
          <div className="grid gap-3 md:grid-cols-2">
            <label className="block text-xs font-medium text-slate-500">
              Daily Stop Loss (₹)
              <input value={dailySl} onChange={(e) => setDailySl(e.target.value)} placeholder="e.g. 5000" className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800" />
            </label>
            <label className="block text-xs font-medium text-slate-500">
              Daily Take Profit (₹)
              <input value={dailyTp} onChange={(e) => setDailyTp(e.target.value)} placeholder="e.g. 10000" className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800" />
            </label>
          </div>
          <p className="mt-2 text-[10px] text-slate-400">
            Portfolio-level MTM stop / target across all legs for the day.
          </p>
        </Card>
      </div>

      {/* Strategy settings */}
      <Card title="Strategy Settings">
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
          <label className="block text-xs font-medium text-slate-500">
            Expiry
            <select
              value={defaultExpiry}
              onChange={(e) => {
                setDefaultExpiry(e.target.value as typeof defaultExpiry);
                if (legs.length > 0) setLegs((prev) => prev.map((l) => ({ ...l, expiry: e.target.value as LegRow["expiry"] })));
              }}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
            >
              {EXPIRIES.map((e) => (
                <option key={e.value} value={e.value}>{e.label}</option>
              ))}
            </select>
          </label>
          <div className="block text-xs font-medium text-slate-500">
            Trade Type
            <div className="mt-1 grid grid-cols-2 gap-0 overflow-hidden rounded-md border border-slate-300">
              {TRADE_TYPES.map((t) => (
                <button
                  key={t.value}
                  onClick={() => setTradeType(t.value)}
                  className={`px-2 py-1.5 text-[11px] font-medium transition-colors ${tradeType === t.value ? "bg-blue-600 text-white" : "bg-white text-slate-600 hover:bg-slate-50"}`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>
          <div className="block text-xs font-medium text-slate-500">
            Trade During
            <div className="mt-1 flex items-center gap-1">
              <input type="time" value={tradeFrom} onChange={(e) => setTradeFrom(e.target.value)} className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800" />
              <span className="text-xs text-slate-400">–</span>
              <input type="time" value={tradeTo} onChange={(e) => setTradeTo(e.target.value)} className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800" />
            </div>
          </div>
          <label className="block text-xs font-medium text-slate-500">
            Max Transactions Per Day
            <input
              type="number"
              min={0}
              value={maxTxns}
              onChange={(e) => setMaxTxns(e.target.value)}
              placeholder="0 = unlimited"
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
            />
          </label>
        </div>
      </Card>

      {/* Validation + results */}
      <Card title="Validation & Results">
        <div className="space-y-3">
          {workflow.validation && (
            <div>
              <p className={`text-xs font-medium ${workflow.validation.valid ? "text-emerald-600" : "text-red-600"}`}>
                {workflow.validation.valid ? "Definition is valid." : `Definition invalid — ${workflow.validation.errors.length} error(s).`}
              </p>
              {workflow.validation.errors.length > 0 && (
                <ul className="mt-1 list-disc space-y-0.5 pl-5 text-[11px] text-red-500">
                  {workflow.validation.errors.slice(0, 8).map((err, i) => (
                    <li key={i}>{err}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {workflow.previewError && <p className="text-xs text-red-600">{workflow.previewError}</p>}
          {workflow.preview && (
            <div className="rounded-lg border border-slate-100 bg-slate-50/50 p-3">
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">Signal preview</p>
              <p className="text-xs text-slate-600">
                {workflow.preview.entry_signals} entry / {workflow.preview.exit_signals} exit signal(s) on{" "}
                {workflow.preview.symbol} ({workflow.preview.timeframe}) across {workflow.preview.bars_evaluated} bars.
                {workflow.preview.is_demo ? " Demo data." : ""}
              </p>
            </div>
          )}
          {run && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <Badge tone={run.status === "completed" ? "green" : run.status === "failed" ? "red" : "blue"}>{run.status}</Badge>
                <span className="text-[11px] text-slate-400">
                  {run.config?.start ? `${run.config.start} → ${run.config.end}` : ""} · v{run.version_number} · {run.result_summary?.summary?.timeframe ?? ""}
                </span>
              </div>
              {run.result_summary?.error && <p className="text-xs text-red-600">{run.result_summary.error}</p>}
              {s && (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <MetricCard label="Return" value={`${s.return_pct.toFixed(2)}%`} tone={s.return_pct >= 0 ? "positive" : "negative"} hint="over period" />
                  <MetricCard label="Net P&L" value={`₹${s.net_pnl.toFixed(0)}`} tone={s.net_pnl >= 0 ? "positive" : "negative"} hint={`final equity ₹${s.final_equity.toFixed(0)}`} />
                  <MetricCard label="Win Rate" value={`${s.win_rate.toFixed(1)}%`} hint={`${s.winning_trades}W / ${s.losing_trades}L`} />
                  <MetricCard label="Trades" value={String(s.total_trades)} hint={`PF ${s.profit_factor.toFixed(2)}`} />
                  <MetricCard label="Max Drawdown" value={`${s.max_drawdown_pct.toFixed(2)}%`} tone="negative" hint="peak-to-trough" />
                  <MetricCard label="Sharpe" value={s.sharpe_ratio > 0 ? s.sharpe_ratio.toFixed(2) : "—"} hint="risk-adjusted" />
                  <MetricCard label="Largest Win" value={`₹${s.largest_win.toFixed(0)}`} tone="positive" hint={`avg win ₹${s.avg_win.toFixed(0)}`} />
                  <MetricCard label="Largest Loss" value={`₹${s.largest_loss.toFixed(0)}`} tone="negative" hint={`avg loss ₹${s.avg_loss.toFixed(0)}`} />
                </div>
              )}
              {run.result_summary && run.result_summary.trades.length === 0 && s && (
                <p className="text-[11px] text-slate-400">No trades generated in the selected window. Ingest more history for this symbol via Tools → Data Manager.</p>
              )}
            </div>
          )}
          {!run && (
            <p className="text-[11px] text-slate-400">
              Click <span className="font-medium">Run Backtest</span> to save this strategy and simulate it over the configured duration.
            </p>
          )}
        </div>
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Small sub-components                                               */
/* ------------------------------------------------------------------ */

function FeatureToggle({
  label,
  checked,
  onChange,
  hint,
  input,
}: {
  label: string;
  checked: boolean;
  onChange: (next: boolean) => void;
  hint?: string;
  input?: { value: string; set: (v: string) => void; suffix?: string };
}) {
  return (
    <div className="rounded-lg border border-slate-200 p-3">
      <label className="flex cursor-pointer items-center justify-between gap-2">
        <span className="text-xs font-medium text-slate-700">{label}</span>
        <button
          onClick={() => onChange(!checked)}
          className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${checked ? "bg-blue-600" : "bg-slate-300"}`}
        >
          <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform ${checked ? "translate-x-4.5" : "translate-x-0.5"}`} />
        </button>
      </label>
      {hint && <p className="mt-1 text-[10px] text-slate-400">{hint}</p>}
      {input && (
        <label className="mt-2 flex items-center gap-1 text-[10px] text-slate-500">
          Trail by
          <input
            type="number"
            step="0.1"
            value={input.value}
            onChange={(e) => input.set(e.target.value)}
            className="w-16 rounded border border-slate-300 px-1.5 py-1 text-[11px] text-slate-700"
          />
          {input.suffix && <span>{input.suffix}</span>}
        </label>
      )}
    </div>
  );
}