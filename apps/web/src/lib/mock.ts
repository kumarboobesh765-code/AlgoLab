// Mock data layer for StrategyLab frontend.
// When mock mode is enabled (see api.ts isMockMode), every api() call is
// served from here so the UI works fully offline with no backend.

import type {
  Health,
  User,
  Strategy,
  StrategyReport,
  VersionCompare,
  StrategyExportPayload,
  BacktestRun,
  BacktestResults,
  BacktestSummary,
  BacktestTrade,
  ReplayCandle,
  ForwardTestRun,
  TickResult,
  OptimizationRun,
  OptimizationResult,
  PaperAccount,
  PaperAccountDetail,
  PaperPosition,
  Instrument,
  OptionChain,
  OptionChainRow,
  DataStatus,
  IngestResult,
  QualityReport,
  QuantCatalog,
  ValidationResponse,
  PreviewResponse,
  PayoffResponse,
  MonteCarloResponse,
  AiDraftResponse,
  ExecutionOrder,
  ExecutionPosition,
  PlaceOrderRequest,
  RegisteredAlgoOut,
  DeploymentOut,
  BracketOut,
} from "./api";

// ---------------------------------------------------------------------------
// deterministic PRNG
// ---------------------------------------------------------------------------
function hashSeed(str: string): number {
  let h = 1779033703 ^ str.length;
  for (let i = 0; i < str.length; i++) {
    h = Math.imul(h ^ str.charCodeAt(i), 3432918353);
    h = (h << 13) | (h >>> 19);
  }
  return h >>> 0;
}

function mulberry32(seed: number) {
  let a = seed >>> 0;
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function rnd(seed: string) {
  return mulberry32(hashSeed(seed));
}

function pick<T>(r: () => number, arr: T[]): T {
  return arr[Math.floor(r() * arr.length)];
}

function round(n: number, d = 2): number {
  const f = Math.pow(10, d);
  return Math.round(n * f) / f;
}

// ---------------------------------------------------------------------------
// date helpers
// ---------------------------------------------------------------------------
const NOW = new Date("2026-08-23T15:30:00Z");

function daysAgo(n: number): string {
  const d = new Date(NOW);
  d.setDate(d.getDate() - n);
  return d.toISOString();
}

function isoDate(d: Date): string {
  return d.toISOString();
}

function addDays(base: Date, days: number): Date {
  const d = new Date(base);
  d.setDate(d.getDate() + days);
  return d;
}

// ---------------------------------------------------------------------------
// Indian F&O reference data
// ---------------------------------------------------------------------------
const FNO_REF: Record<string, { lot_size: number; strike_step: number; spot: number }> = {
  NIFTY:      { lot_size: 75,  strike_step: 50,  spot: 23860 },
  BANKNIFTY:  { lot_size: 30,  strike_step: 100, spot: 52150 },
  FINNIFTY:   { lot_size: 40,  strike_step: 50,  spot: 23860 },
  MIDCPNIFTY: { lot_size: 75,  strike_step: 75,  spot: 12200 },
  SENSEX:     { lot_size: 10,  strike_step: 100, spot: 79200 },
  BANKEX:     { lot_size: 15,  strike_step: 100, spot: 56200 },
};

function nextWeeklyExpiries(count = 4): string[] {
  const out: string[] = [];
  const d = new Date(NOW);
  d.setHours(0, 0, 0, 0);
  while (d.getDay() !== 4) d.setDate(d.getDate() + 1);
  for (let i = 0; i < count; i++) {
    out.push(isoDate(d));
    d.setDate(d.getDate() + 7);
  }
  return out;
}

function nextMonthlyExpiries(count = 3): string[] {
  const out: string[] = [];
  const d = new Date(NOW);
  d.setHours(0, 0, 0, 0);
  while (d.getDay() !== 4) d.setDate(d.getDate() + 1);
  const last = new Date(d.getFullYear(), d.getMonth() + 1, 0);
  const lastThursday = new Date(last);
  lastThursday.setDate(lastThursday.getDate() - ((lastThursday.getDay() + 3) % 7));
  const base = new Date(Math.max(d.getTime(), lastThursday.getTime()));
  for (let i = 0; i < count; i++) {
    const e = new Date(base);
    e.setMonth(e.getMonth() + i);
    const m = new Date(e.getFullYear(), e.getMonth() + 1, 0);
    const th = new Date(m);
    th.setDate(th.getDate() - ((th.getDay() + 3) % 7));
    out.push(isoDate(th));
  }
  return out;
}

function allExpiries(): string[] {
  const weekly = nextWeeklyExpiries(4);
  const monthly = nextMonthlyExpiries(3);
  const set = new Set<string>(weekly.concat(monthly));
  return Array.from(set).sort();
}

// ---------------------------------------------------------------------------
// mock strategies
// ---------------------------------------------------------------------------
const STRAT_DEFS: Record<string, Record<string, unknown>> = {
  ema: {
    version: 1,
    timeframe: "5m",
    instrument: { symbol: "NIFTY", exchange: "NSE", segment: "index" },
    indicators: [
      { key: "fast", type: "EMA", params: { period: 9 } },
      { key: "slow", type: "EMA", params: { period: 21 } },
    ],
    entry: {
      logic: "ALL",
      conditions: [
        { left: "fast", op: "crosses_above", right: "slow" },
      ],
    },
    exit: {
      logic: "ALL",
      conditions: [
        { left: "fast", op: "crosses_below", right: "slow" },
      ],
    },
    risk: { stop_loss_pct: 0.8, target_pct: 1.6 },
    position: { quantity: 10, direction: "long_only", quantity_type: "fixed" },
  },
  rsi: {
    version: 1,
    timeframe: "15m",
    instrument: { symbol: "NIFTY", exchange: "NSE", segment: "index" },
    indicators: [{ key: "rsi", type: "RSI", params: { period: 14 } }],
    entry: {
      logic: "ALL",
      conditions: [{ left: "rsi", op: "less_than", right: { type: "constant", value: 30 } }],
    },
    exit: {
      logic: "ALL",
      conditions: [{ left: "rsi", op: "greater_than", right: { type: "constant", value: 70 } }],
    },
    risk: { stop_loss_pct: 1.5, target_pct: 3.0 },
    position: { quantity: 10, direction: "long_only", quantity_type: "fixed" },
  },
  macd: {
    version: 1,
    timeframe: "5m",
    instrument: { symbol: "BANKNIFTY", exchange: "NSE", segment: "index" },
    indicators: [{ key: "macd", type: "MACD", params: { fast: 12, slow: 26, signal: 9 } }],
    entry: {
      logic: "ALL",
      conditions: [{ left: "macd", op: "crosses_above", right: "macd_signal" }],
    },
    exit: {
      logic: "ALL",
      conditions: [{ left: "macd", op: "crosses_below", right: "macd_signal" }],
    },
    risk: { trailing_sl_pct: 1.2 },
    position: { quantity: 10, direction: "long_only", quantity_type: "fixed" },
  },
  supertrend: {
    version: 1,
    timeframe: "15m",
    instrument: { symbol: "NIFTY", exchange: "NSE", segment: "index" },
    indicators: [{ key: "st", type: "Supertrend", params: { period: 10, multiplier: 3 } }],
    entry: {
      logic: "ALL",
      conditions: [{ left: "close", op: "greater_than", right: "st" }],
    },
    exit: {
      logic: "ALL",
      conditions: [{ left: "close", op: "less_than", right: "st" }],
    },
    risk: { stop_loss_pct: 1.0 },
    position: { quantity: 10, direction: "long_only", quantity_type: "fixed" },
  },
  bollinger: {
    version: 1,
    timeframe: "15m",
    instrument: { symbol: "NIFTY", exchange: "NSE", segment: "index" },
    indicators: [{ key: "bb", type: "BollingerBands", params: { period: 20, stddev: 2 } }],
    entry: {
      logic: "ALL",
      conditions: [{ left: "close", op: "less_than", right: "bb_lower" }],
    },
    exit: {
      logic: "ALL",
      conditions: [{ left: "close", op: "greater_than", right: "bb_middle" }],
    },
    risk: { stop_loss_pct: 2.0 },
    position: { quantity: 10, direction: "long_only", quantity_type: "fixed" },
  },
  vwap: {
    version: 1,
    timeframe: "5m",
    instrument: { symbol: "NIFTY", exchange: "NSE", segment: "index" },
    indicators: [{ key: "vwap", type: "VWAP", params: {} }],
    entry: {
      logic: "ALL",
      conditions: [{ left: "close", op: "crosses_above", right: "vwap" }],
    },
    exit: {
      logic: "ALL",
      conditions: [{ left: "close", op: "crosses_below", right: "vwap" }],
    },
    risk: { target_pct: 1.0, stop_loss_pct: 0.5 },
    position: { quantity: 10, direction: "long_only", quantity_type: "fixed" },
  },
};

interface SeedStrat {
  id: string;
  name: string;
  desc: string;
  defKey: keyof typeof STRAT_DEFS;
  status: string;
  tags: string[];
}

const SEED_STRATS: SeedStrat[] = [
  { id: "s_ema", name: "EMA Crossover", desc: "Fast EMA crosses above slow EMA — classic trend entry.", defKey: "ema", status: "active", tags: ["trend", "beginner"] },
  { id: "s_rsi", name: "RSI Mean Reversion", desc: "Buy oversold (RSI<30), exit overbought (RSI>70).", defKey: "rsi", status: "active", tags: ["mean-reversion", "oscillator"] },
  { id: "s_macd", name: "MACD Signal Crossover", desc: "Long when MACD crosses above its signal line.", defKey: "macd", status: "draft", tags: ["momentum", "trend"] },
  { id: "s_super", name: "Supertrend Follow", desc: "Follow the Supertrend; long above, exit below.", defKey: "supertrend", status: "active", tags: ["trend", "atr"] },
  { id: "s_boll", name: "Bollinger Reversion", desc: "Buy below lower band, exit at middle band.", defKey: "bollinger", status: "draft", tags: ["volatility", "mean-reversion"] },
  { id: "s_vwap", name: "VWAP Pullback", desc: "Intraday pullback to session VWAP.", defKey: "vwap", status: "paused", tags: ["intraday", "vwap"] },
];

function mockStrategies(): Strategy[] {
  return SEED_STRATS.map((s, i) => ({
    id: s.id,
    name: s.name,
    description: s.desc,
    exchange: "NSE",
    underlying: "NIFTY",
    instrument: "options",
    strategy_type: "intraday",
    status: s.status,
    tags: s.tags,
    definition: STRAT_DEFS[s.defKey],
    current_version: 1,
    created_at: daysAgo(40 - i * 3),
    updated_at: daysAgo(2 + i),
  }));
}

// ---------------------------------------------------------------------------
// backtest generation
// ---------------------------------------------------------------------------
function genEquityCurve(seed: string, points: number, start: number): { time: string; equity: number }[] {
  const r = rnd(seed);
  const out: { time: string; equity: number }[] = [];
  let eq = start;
  const drift = (r() - 0.42) * 0.004; // slight bias
  const d0 = new Date(NOW);
  d0.setDate(d0.getDate() - points);
  for (let i = 0; i < points; i++) {
    const shock = (r() - 0.5) * 0.02;
    eq = eq * (1 + drift + shock);
    const d = addDays(d0, i);
    d.setHours(9, 15 + (i % 6) * 10, 0, 0);
    out.push({ time: isoDate(d), equity: round(eq, 2) });
  }
  return out;
}

function genTrades(seed: string, count: number, capital: number, start: Date, end: Date): BacktestTrade[] {
  const r = rnd(seed + "trades");
  const trades: BacktestTrade[] = [];
  const span = end.getTime() - start.getTime();
  for (let i = 0; i < count; i++) {
    const entryT = new Date(start.getTime() + (span * (i + 0.2)) / (count + 1));
    const held = 2 + Math.floor(r() * 14);
    const exitT = new Date(entryT.getTime() + held * 3600_000 * 6);
    const win = r() > 0.42;
    const pnlPct = win ? 0.3 + r() * 2.4 : -(0.2 + r() * 1.6);
    const qty = 10;
    const entry = round(23800 + r() * 600, 2);
    const pnl = round((capital / 100) * (pnlPct / 100), 2);
    trades.push({
      direction: "long",
      quantity: qty,
      entry_time: isoDate(entryT),
      entry_price: entry,
      exit_time: isoDate(exitT),
      exit_price: round(entry * (1 + pnlPct / 100), 2),
      exit_reason: win ? "target" : pick(r, ["stop_loss", "signal"]),
      pnl,
      pnl_pct: round(pnlPct, 2),
      bars_held: held,
    });
  }
  return trades;
}

function computeSummary(curve: { time: string; equity: number }[], trades: BacktestTrade[], capital: number, costs: number): BacktestSummary {
  const finalEquity = curve.length ? curve[curve.length - 1].equity : capital;
  const net = round(finalEquity - capital, 2);
  const wins = trades.filter((t) => t.pnl > 0);
  const losses = trades.filter((t) => t.pnl <= 0);
  const grossWin = wins.reduce((a, t) => a + t.pnl, 0);
  const grossLoss = Math.abs(losses.reduce((a, t) => a + t.pnl, 0));
  const winRate = trades.length ? round((wins.length / trades.length) * 100, 2) : 0;
  const profitFactor = grossLoss ? round(grossWin / grossLoss, 2) : 0;
  let peak = -Infinity;
  let maxDD = 0;
  for (const p of curve) {
    peak = Math.max(peak, p.equity);
    const dd = (peak - p.equity) / peak;
    if (dd > maxDD) maxDD = dd;
  }
  const rets: number[] = [];
  for (let i = 1; i < curve.length; i++) {
    rets.push((curve[i].equity - curve[i - 1].equity) / curve[i - 1].equity);
  }
  const mean = rets.reduce((a, b) => a + b, 0) / (rets.length || 1);
  const variance = rets.reduce((a, b) => a + (b - mean) ** 2, 0) / (rets.length || 1);
  const std = Math.sqrt(variance) || 1e-9;
  const sharpe = round((mean / std) * Math.sqrt(252), 2);
  const totalCosts = round((costs / 100) * capital, 2);
  const stt = round(totalCosts * 0.35, 2);
  const exchange = round(totalCosts * 0.18, 2);
  const sebi = round(totalCosts * 0.02, 2);
  const stamp = round(totalCosts * 0.12, 2);
  const brokerage = round(totalCosts * 0.18, 2);
  const gst = round(totalCosts * 0.15, 2);
  return {
    initial_capital: capital,
    final_equity: round(finalEquity, 2),
    net_pnl: net,
    return_pct: round((net / capital) * 100, 2),
    total_trades: trades.length,
    winning_trades: wins.length,
    losing_trades: losses.length,
    win_rate: winRate,
    profit_factor: profitFactor,
    avg_win: wins.length ? round(grossWin / wins.length, 2) : 0,
    avg_loss: losses.length ? round(-grossLoss / losses.length, 2) : 0,
    largest_win: wins.length ? round(Math.max(...wins.map((t) => t.pnl)), 2) : 0,
    largest_loss: losses.length ? round(Math.min(...losses.map((t) => t.pnl)), 2) : 0,
    max_drawdown_pct: round(maxDD * 100, 2),
    sharpe_ratio: sharpe,
    total_costs: totalCosts,
    cost_breakdown: { stt, exchange, sebi, stamp, brokerage, gst, total: totalCosts },
    timeframe: "5m",
  };
}

function genBacktestResults(strategyId: string, cfg: Record<string, unknown>): BacktestResults {
  const capital = Number(cfg.initial_capital) || 100000;
  const costs = Number(cfg.costs_pct) ?? 0.05;
  const points = 120;
  const curve = genEquityCurve(strategyId + capital + (cfg.start ?? ""), points, capital);
  const start = new Date(NOW);
  start.setDate(start.getDate() - points);
  const end = new Date(NOW);
  const trades = genTrades(strategyId + capital, 14 + Math.floor(rnd(strategyId)() * 10), capital, start, end);
  const summary = computeSummary(curve, trades, capital, costs);
  return { summary, equity_curve: curve, trades };
}

// ---------------------------------------------------------------------------
// replay candles
// ---------------------------------------------------------------------------
function genCandles(seed: string, count: number, symbol: string): ReplayCandle[] {
  const r = rnd(seed + "candles");
  const d0 = new Date(NOW);
  d0.setDate(d0.getDate() - count);
  let price = symbol.includes("BANK") ? 52000 : 23850;
  const out: ReplayCandle[] = [];
  for (let i = 0; i < count; i++) {
    const o = price;
    const move = (r() - 0.5) * 80;
    const c = round(o + move, 2);
    const hi = round(Math.max(o, c) + r() * 40, 2);
    const lo = round(Math.min(o, c) - r() * 40, 2);
    const vol = Math.floor(50000 + r() * 200000);
    const d = addDays(d0, i);
    d.setHours(9, 15 + (i % 7) * 8, 0, 0);
    out.push({ timestamp: isoDate(d), open: o, high: hi, low: lo, close: c, volume: vol });
    price = c;
  }
  return out;
}

// ---------------------------------------------------------------------------
// instruments + option chain
// ---------------------------------------------------------------------------
function mockInstruments(): Instrument[] {
  const syms = Object.keys(FNO_REF);
  return syms.map((s, i) => {
    const ref = FNO_REF[s];
    return {
      id: `inst_${i}`,
      security_id: `SEC${1000 + i}`,
      exchange: "NSE",
      segment: "index",
      exchange_segment: "NSE_FO",
      symbol: s,
      name: s,
      underlying: s,
      instrument_type: "INDEX",
      expiry_code: 1,
      expiry: daysAgo(-30),
      strike: null,
      option_type: null,
      lot_size: ref.lot_size,
      strike_step: ref.strike_step,
      tick_size: 0.05,
      status: "active",
    };
  });
}

function mockOptionChain(underlying: string, expiry?: string): OptionChain {
  const ref = FNO_REF[underlying] ?? FNO_REF.NIFTY;
  const spot = ref.spot;
  const step = ref.strike_step;
  const lotSize = ref.lot_size;
  const atm = Math.round(spot / step) * step;
  const rows: OptionChainRow[] = [];
  for (let i = -10; i <= 10; i++) {
    const strike = atm + i * step;
    const r = rnd(underlying + strike);
    const dist = Math.abs(strike - atm) / step;
    rows.push({
      strike,
      call_ltp: round(Math.max(0.5, 120 - dist * 9 + r() * 10), 2),
      put_ltp: round(Math.max(0.5, 120 - dist * 9 + r() * 10), 2),
      call_iv: round(14 + r() * 6, 2),
      put_iv: round(14 + r() * 6, 2),
      call_oi: Math.floor(200000 - dist * 12000 + r() * 8000),
      put_oi: Math.floor(200000 - dist * 12000 + r() * 8000),
      call_volume: Math.floor(50000 + r() * 60000),
      put_volume: Math.floor(50000 + r() * 60000),
      call_delta: round(strike < atm ? 0.3 + r() * 0.2 : 0.6 + r() * 0.3, 3),
      put_delta: round(strike < atm ? -0.6 - r() * 0.3 : -0.3 - r() * 0.2, 3),
      call_gamma: round(0.0001 + r() * 0.0015, 4),
      call_theta: round(-1.5 - r() * 4, 3),
      call_vega: round(1 + r() * 6, 3),
      put_gamma: round(0.0001 + r() * 0.0015, 4),
      put_theta: round(-1.5 - r() * 4, 3),
      put_vega: round(1 + r() * 6, 3),
    });
  }
  const exps = allExpiries();
  const chosenExpiry = expiry && exps.includes(expiry) ? expiry : exps[0];
  return { underlying, spot, expiry: chosenExpiry, strikes: rows, provider: "demo", is_demo: true, strike_step: step, lot_size: lotSize, expiries: exps };
}

// ---------------------------------------------------------------------------
// paper accounts
// ---------------------------------------------------------------------------
function mockPaperAccounts(): PaperAccount[] {
  return [
    { id: "pa_1", name: "Growth Book", initial_capital: 500000, cash_balance: 472300.5, status: "active", created_at: daysAgo(30) },
    { id: "pa_2", name: "Conservative", initial_capital: 250000, cash_balance: 250000, status: "active", created_at: daysAgo(15) },
  ];
}

function pos(id: string, idx: number, open: boolean): PaperPosition {
  const r = rnd("pos" + id + idx);
  const entry = round(23800 + r() * 500, 2);
  const last = round(entry * (1 + (r() - 0.4) * 0.02), 2);
  return {
    id: `pos_${id}_${idx}`,
    strategy_id: pick(r, SEED_STRATS).id,
    direction: "long",
    quantity: 10,
    entry_price: entry,
    entry_time: daysAgo(10 - idx),
    stop_price: round(entry * 0.99, 2),
    target_price: round(entry * 1.02, 2),
    status: open ? "open" : "closed",
    last_close: last,
    unrealized_pnl: open ? round((last - entry) * 10, 2) : undefined,
    exit_price: open ? undefined : last,
    exit_time: open ? undefined : daysAgo(8 - idx),
    exit_reason: open ? undefined : "target",
    realized_pnl: open ? undefined : round((last - entry) * 10, 2),
  };
}

function mockPaperDetail(id: string): PaperAccountDetail {
  const base = mockPaperAccounts().find((a) => a.id === id) ?? mockPaperAccounts()[0];
  const open = [pos(id, 1, true), pos(id, 2, true)];
  const closed = [pos(id, 3, false), pos(id, 4, false), pos(id, 5, false)];
  const equity = base.cash_balance + open.reduce((a, p) => a + (p.unrealized_pnl ?? 0), 0);
  const unreal = open.reduce((a, p) => a + (p.unrealized_pnl ?? 0), 0);
  return {
    ...base,
    equity: round(equity, 2),
    unrealized_pnl: round(unreal, 2),
    open_positions: open,
    closed_positions: closed,
    recent_orders: closed.map((p, i) => ({
      id: `ord_${id}_${i}`,
      side: "BUY",
      quantity: p.quantity,
      filled_price: p.entry_price ?? 0,
      reason: "entry",
      signal_time: p.entry_time,
      created_at: p.entry_time,
    })),
  };
}

// ---------------------------------------------------------------------------
// forward tests
// ---------------------------------------------------------------------------
function mockForwardTests(): ForwardTestRun[] {
  return [
    {
      id: "ft_1",
      strategy_id: "s_ema",
      account_id: "pa_1",
      version_number: 1,
      status: "running",
      last_bar_time: daysAgo(0),
      pending_action: "hold",
      last_message: "Holding position (2 open).",
      started_at: daysAgo(3),
      created_at: daysAgo(3),
    },
    {
      id: "ft_2",
      strategy_id: "s_super",
      account_id: "pa_1",
      version_number: 1,
      status: "paused",
      last_bar_time: daysAgo(1),
      pending_action: "none",
      last_message: "Paused by user.",
      started_at: daysAgo(6),
      stopped_at: daysAgo(1),
      created_at: daysAgo(6),
    },
  ];
}

function mockTick(runId: string): TickResult {
  const r = rnd(runId + Date.now());
  const fill = r() > 0.6;
  return {
    run_id: runId,
    bars_processed: 1 + Math.floor(r() * 5),
    fills: fill
      ? [{ side: "BUY", quantity: 10, price: round(23800 + r() * 400, 2), reason: "entry", time: isoDate(new Date()), pnl: round((r() - 0.4) * 500, 2) }]
      : [],
    open_position: fill
      ? { id: "live_pos", direction: "long", quantity: 10, entry_price: round(23800 + r() * 400, 2), status: "open", last_close: round(23900 + r() * 200, 2), unrealized_pnl: round((r() - 0.4) * 300, 2) }
      : undefined,
    message: fill ? "Opened long position." : "No signal this bar.",
  };
}

// ---------------------------------------------------------------------------
// optimizations
// ---------------------------------------------------------------------------
function mockOptimizations(): OptimizationRun[] {
  return [
    {
      id: "opt_1",
      strategy_id: "s_ema",
      method: "grid",
      param_ranges: { fast: [5, 9, 13], slow: [15, 21, 26] },
      start: daysAgo(60),
      end: daysAgo(5),
      train_pct: 0.7,
      target_metric: "sharpe_ratio",
      status: "completed",
      total_combinations: 9,
      completed_combinations: 9,
      best_params: { fast: 9, slow: 21 },
      best_metrics: { net_pnl: 18420.5, return_pct: 18.4, sharpe_ratio: 1.92, max_drawdown_pct: 6.1, win_rate: 58.3 },
      created_at: daysAgo(4),
    },
  ];
}

function mockOptResults(runId: string): OptimizationResult[] {
  const combos = [
    { fast: 5, slow: 15 }, { fast: 5, slow: 21 }, { fast: 5, slow: 26 },
    { fast: 9, slow: 15 }, { fast: 9, slow: 21 }, { fast: 9, slow: 26 },
    { fast: 13, slow: 15 }, { fast: 13, slow: 21 }, { fast: 13, slow: 26 },
  ];
  const r = rnd(runId);
  return combos.map((c, i) => {
    const sharpe = round(0.8 + r() * 1.6, 2);
    const ret = round(4 + r() * 22, 2);
    return {
      id: `ores_${i}`,
      run_id: runId,
      rank: i + 1,
      params: c,
      net_pnl: round(2000 + r() * 20000, 2),
      return_pct: ret,
      win_rate: round(45 + r() * 20, 2),
      profit_factor: round(1 + r() * 1.5, 2),
      max_drawdown_pct: round(3 + r() * 9, 2),
      sharpe_ratio: sharpe,
      total_trades: Math.floor(10 + r() * 30),
      train_sharpe: round(sharpe * (0.9 + r() * 0.2), 2),
      test_sharpe: round(sharpe * (0.7 + r() * 0.3), 2),
      status: "completed",
      created_at: daysAgo(4),
    };
  });
}

// ---------------------------------------------------------------------------
// quant catalog / validate / preview / ai
// ---------------------------------------------------------------------------
const CATALOG_INDICATORS: QuantCatalog["indicators"] = [
  { type: "EMA", description: "Exponential moving average", outputs: ["value"], params: { period: { kind: "int", default: 20, ge: 1, le: 400 } } },
  { type: "SMA", description: "Simple moving average", outputs: ["value"], params: { period: { kind: "int", default: 20, ge: 1, le: 400 } } },
  { type: "RSI", description: "Relative Strength Index", outputs: ["value"], params: { period: { kind: "int", default: 14, ge: 2, le: 100 } } },
  { type: "MACD", description: "Moving Average Convergence Divergence", outputs: ["macd", "signal", "histogram"], params: { fast: { kind: "int", default: 12, ge: 1, le: 100 }, slow: { kind: "int", default: 26, ge: 1, le: 200 }, signal: { kind: "int", default: 9, ge: 1, le: 100 } } },
  { type: "BollingerBands", description: "Bollinger Bands", outputs: ["upper", "middle", "lower"], params: { period: { kind: "int", default: 20, ge: 2, le: 200 }, stddev: { kind: "float", default: 2, ge: 0.5, le: 5 } } },
  { type: "Supertrend", description: "Supertrend trend filter", outputs: ["value"], params: { period: { kind: "int", default: 10, ge: 1, le: 100 }, multiplier: { kind: "float", default: 3, ge: 1, le: 10 } } },
  { type: "VWAP", description: "Volume Weighted Average Price", outputs: ["value"], params: {} },
  { type: "ATR", description: "Average True Range", outputs: ["value"], params: { period: { kind: "int", default: 14, ge: 1, le: 100 } } },
];

function mockCatalog(): QuantCatalog {
  return { timeframes: ["1m", "5m", "15m", "30m", "1h", "1d"], indicators: CATALOG_INDICATORS };
}

function mockValidate(): ValidationResponse {
  return { valid: true, errors: [], warnings: ["No historical data ingested for this symbol in mock mode."] };
}

function mockPreview(): PreviewResponse {
  return {
    symbol: "NIFTY",
    timeframe: "5m",
    bars_evaluated: 500,
    provider: "demo",
    is_demo: true,
    entry_signals: 12,
    exit_signals: 11,
    last_bar_entry_signal: false,
    last_bar_exit_signal: true,
    indicator_tail: { fast: { value: 23920.4 }, slow: { value: 23880.1 } },
  };
}

function mockAiDraft(prompt: string): AiDraftResponse {
  return {
    source: "rules",
    valid: true,
    warnings: [`Mock AI used rule-based fallback for "${prompt.slice(0, 60)}" (no LLM configured).`],
    errors: [],
    definition: {
      version: 1,
      timeframe: "5m",
      instrument: { symbol: "NIFTY", exchange: "NSE", segment: "index" },
      indicators: [{ key: "emaFast", type: "EMA", params: { period: 9 } }, { key: "emaSlow", type: "EMA", params: { period: 21 } }],
      entry: { logic: "ALL", conditions: [{ left: "emaFast", op: "crosses_above", right: "emaSlow" }] },
      exit: { logic: "ALL", conditions: [{ left: "emaFast", op: "crosses_below", right: "emaSlow" }] },
      risk: { stop_loss_pct: 0.8, target_pct: 1.6 },
      position: { quantity: 10, direction: "long_only", quantity_type: "fixed" },
    },
  };
}

// ---------------------------------------------------------------------------
// templates
// ---------------------------------------------------------------------------
function mockTemplates(): { name: string; description: string; tags: string[]; definition: Record<string, unknown> }[] {
  const fnoTemplates = [
    { name: "NIFTY Bull Call Spread", description: "Bullish spread on NIFTY.", tags: ["options", "fno"], definition: { builder: "legs", underlying: "NIFTY", legs: [{ action: "buy", option_type: "CE", strike_offset: 0, lots: 75 }, { action: "sell", option_type: "CE", strike_offset: 1, lots: 75 }], version: 1 } },
    { name: "NIFTY Long Straddle", description: "Long straddle on NIFTY.", tags: ["options", "fno"], definition: { builder: "legs", underlying: "NIFTY", legs: [{ action: "buy", option_type: "CE", strike_offset: 0, lots: 75 }, { action: "buy", option_type: "PE", strike_offset: 0, lots: 75 }], version: 1 } },
    { name: "NIFTY Iron Condor", description: "Iron condor on NIFTY.", tags: ["options", "fno"], definition: { builder: "legs", underlying: "NIFTY", legs: [{ action: "sell", option_type: "CE", strike_offset: 1, lots: 75 }, { action: "sell", option_type: "PE", strike_offset: -1, lots: 75 }, { action: "buy", option_type: "CE", strike_offset: 2, lots: 75 }, { action: "buy", option_type: "PE", strike_offset: -2, lots: 75 }], version: 1 } },
    { name: "BANKNIFTY Short Straddle", description: "Short straddle on BANKNIFTY.", tags: ["options", "fno"], definition: { builder: "legs", underlying: "BANKNIFTY", legs: [{ action: "sell", option_type: "CE", strike_offset: 0, lots: 30 }, { action: "sell", option_type: "PE", strike_offset: 0, lots: 30 }], version: 1 } },
    { name: "BANKNIFTY Bear Put Spread", description: "Bear put spread on BANKNIFTY.", tags: ["options", "fno"], definition: { builder: "legs", underlying: "BANKNIFTY", legs: [{ action: "buy", option_type: "PE", strike_offset: 0, lots: 30 }, { action: "sell", option_type: "PE", strike_offset: -1, lots: 30 }], version: 1 } },
    { name: "NIFTY Iron Butterfly", description: "Iron butterfly on NIFTY.", tags: ["options", "fno"], definition: { builder: "legs", underlying: "NIFTY", legs: [{ action: "sell", option_type: "CE", strike_offset: 0, lots: 75 }, { action: "sell", option_type: "PE", strike_offset: 0, lots: 75 }, { action: "buy", option_type: "CE", strike_offset: 1, lots: 75 }, { action: "buy", option_type: "PE", strike_offset: -1, lots: 75 }], version: 1 } },
  ];
  return [
    { name: "EMA Crossover", description: "Dual EMA trend crossover.", tags: ["trend"], definition: STRAT_DEFS.ema },
    { name: "RSI Reversion", description: "Oversold bounce.", tags: ["mean-reversion"], definition: STRAT_DEFS.rsi },
    { name: "MACD Momentum", description: "MACD signal crossover.", tags: ["momentum"], definition: STRAT_DEFS.macd },
    { name: "Supertrend", description: "ATR-based trend follow.", tags: ["trend"], definition: STRAT_DEFS.supertrend },
    { name: "Bollinger", description: "Band mean reversion.", tags: ["volatility"], definition: STRAT_DEFS.bollinger },
    { name: "VWAP", description: "Intraday VWAP pullback.", tags: ["intraday"], definition: STRAT_DEFS.vwap },
    ...fnoTemplates,
  ];
}

// ---------------------------------------------------------------------------
// options payoff + monte carlo
// ---------------------------------------------------------------------------
function mockPayoff(body: Record<string, unknown>): PayoffResponse {
  const spot = 23860;
  const atm = Math.round(spot / 50) * 50;
  const legs = (body.legs as Array<Record<string, unknown>>) ?? [];
  const curve: { price: number; pnl: number }[] = [];
  for (let p = spot - 500; p <= spot + 500; p += 25) {
    const pnl = round((p - spot) * (legs.length ? legs.length : 1) * 10, 2);
    curve.push({ price: p, pnl });
  }
  return {
    underlying: "NIFTY",
    spot,
    atm_strike: atm,
    expiry: daysAgo(-30),
    dte_days: 21,
    lot_size: 50,
    is_demo: true,
    provider: "demo",
    legs: legs.map((l, i) => ({
      action: (l.action as "buy" | "sell") ?? "buy",
      option_type: (l.option_type as "CE" | "PE") ?? "CE",
      strike_offset: Number(l.strike_offset ?? 0),
      lots: Number(l.lots ?? 1),
      strike: atm + Number(l.strike_offset ?? 0),
      premium: round(80 + rnd("leg" + i)() * 120, 2),
      iv_pct: round(15 + rnd("iv" + i)() * 8, 2),
      delta: round(0.4 + rnd("d" + i)() * 0.4, 3),
      gamma: round(0.001 + rnd("g" + i)() * 0.004, 4),
      theta_per_day: round(-2 - rnd("t" + i)() * 6, 3),
      vega: round(2 + rnd("v" + i)() * 8, 3),
    })),
    curve,
    metrics: { net_premium: round(120, 2), max_profit: 2500, max_loss: -1800, breakevens: [spot - 120, spot + 120], risk_reward: round(2500 / 1800, 2) },
    net_greeks: { delta: round(0.2, 3), gamma: round(0.004, 4), theta_per_day: round(-4.5, 3), vega: round(6, 3) },
  };
}

function mockMonteCarlo(): MonteCarloResponse {
  const r = rnd("mc");
  const bins = [
    { lo: -8000, hi: -6000, count: 4 },
    { lo: -6000, hi: -4000, count: 9 },
    { lo: -4000, hi: -2000, count: 18 },
    { lo: -2000, hi: 0, count: 27 },
    { lo: 0, hi: 2000, count: 25 },
    { lo: 2000, hi: 4000, count: 12 },
    { lo: 4000, hi: 6000, count: 5 },
  ];
  return {
    stats: { mean: round(800 + r() * 400, 2), std: round(2400, 2), median: round(600 + r() * 300, 2), p5: -5200, p95: 6400, worst: -9100, best: 9200, prob_profit: round(0.58 + r() * 0.1, 2), var_95: -5200 },
    bins,
    paths: 1000,
    vol_used_pct: 16.5,
    horizon_days: 21,
  };
}

// ---------------------------------------------------------------------------
// in-memory stores (session lifetime)
// ---------------------------------------------------------------------------
let strategies: Strategy[] = mockStrategies();
let paperAccounts: PaperAccount[] = mockPaperAccounts();
let forwardTests: ForwardTestRun[] = mockForwardTests();
const optRuns = mockOptimizations();

function buildRun(strategyId: string, cfg: Record<string, unknown>, seedBias: string): BacktestRun {
  const results = genBacktestResults(strategyId, cfg);
  const now = isoDate(new Date());
  return {
    id: `bt_${strategyId}_${seedBias}`,
    strategy_id: strategyId,
    version_number: 1,
    status: "completed",
    config: {
      symbol: String(cfg.symbol ?? "NIFTY"),
      timeframe: String(cfg.timeframe ?? "5m"),
      start: cfg.start ? String(cfg.start) : daysAgo(120),
      end: cfg.end ? String(cfg.end) : daysAgo(1),
      initial_capital: Number(cfg.initial_capital) || 100000,
      costs_pct: cfg.costs_pct != null ? Number(cfg.costs_pct) : 0.05,
    },
    result_summary: results,
    started_at: now,
    finished_at: now,
    created_at: now,
  };
}

const seedRuns: BacktestRun[] = [
  buildRun("s_ema", { initial_capital: 100000, costs_pct: 0.05, start: daysAgo(120), end: daysAgo(1) }, "seed1"),
  buildRun("s_rsi", { initial_capital: 150000, costs_pct: 0.05, start: daysAgo(120), end: daysAgo(1) }, "seed2"),
  buildRun("s_macd", { initial_capital: 120000, costs_pct: 0.1, start: daysAgo(90), end: daysAgo(1) }, "seed3"),
];

const createdBacktests: BacktestRun[] = [];

// ---------------------------------------------------------------------------
// strategy report / compare
// ---------------------------------------------------------------------------
function mockReport(id: string): StrategyReport {
  const s = strategies.find((x) => x.id === id) ?? strategies[0];
  const related = seedRuns.filter((r) => r.strategy_id === id);
  return {
    strategy: {
      id: s.id,
      name: s.name,
      status: s.status,
      exchange: s.exchange,
      underlying: s.underlying,
      instrument: s.instrument,
      strategy_type: s.strategy_type,
      tags: s.tags,
      current_version: s.current_version,
      has_definition: !!s.definition,
      created_at: s.created_at,
      updated_at: s.updated_at,
    },
    versions: [
      { version: 1, created_at: s.created_at, changelog: null, has_definition: !!s.definition },
    ],
    latest_backtest: related[0]
      ? { id: related[0].id, created_at: related[0].created_at, config: related[0].config as Record<string, unknown>, summary: related[0].result_summary?.summary ?? null, trades_count: related[0].result_summary?.trades.length ?? 0 }
      : null,
    total_backtests: related.length,
    optimizations: optRuns
      .filter((o) => o.strategy_id === id)
      .map((o) => ({ id: o.id, method: o.method, target_metric: o.target_metric, total_combinations: o.total_combinations, best_params: o.best_params, best_metrics: o.best_metrics, created_at: o.created_at })),
  };
}

function mockCompare(id: string, v1: number, v2: number): VersionCompare {
  const s = strategies.find((x) => x.id === id) ?? strategies[0];
  const run = seedRuns.find((r) => r.strategy_id === id) ?? seedRuns[0];
  return {
    v1_version: v1,
    v2_version: v2,
    v1_definition: s.definition ?? null,
    v2_definition: s.definition ?? null,
    v1_backtest: { summary: run.result_summary?.summary ?? null, created_at: run.created_at },
    v2_backtest: { summary: run.result_summary?.summary ?? null, created_at: run.created_at },
    v1_created: daysAgo(20),
    v2_created: daysAgo(2),
  };
}

// ---------------------------------------------------------------------------
// router
// ---------------------------------------------------------------------------
function ok(body: unknown, status = 200) {
  return Promise.resolve({ status, body });
}
function err(status: number, detail: string) {
  return Promise.resolve({ status, body: { detail } });
}

export interface MockResponse {
  status: number;
  body: unknown;
}

export function mockApi(path: string, init: RequestInit = {}): Promise<MockResponse> {
  const [pathOnly, qs] = path.split("?");
  const method = (init.method ?? "GET").toUpperCase();
  const params = new URLSearchParams(qs ?? "");

  // health
  if (pathOnly === "/health" && method === "GET") {
    const health: Health = {
      status: "ok",
      app: "StrategyLab API (MOCK)",
      env: "mock",
      auth_enabled: false,
      database: "ok",
      market_data_provider: "demo",
      market_data_is_demo: true,
      market_data_provider_configured: true,
      trading_mode: "paper_only",
      live_trading_available: false,
    };
    return ok(health);
  }

  // auth
  if (pathOnly === "/auth/guest" && method === "POST") return ok({ access_token: "mock-guest-token" });
  if (pathOnly === "/auth/login" && method === "POST") return ok({ access_token: "mock-login-token" });
  if (pathOnly === "/auth/me" && method === "GET") {
    const user: User = { id: "u_mock", email: "demo@strategylab.local", full_name: "Demo Trader", role: "admin", is_active: true, created_at: daysAgo(60) };
    return ok(user);
  }
  if (pathOnly === "/auth/register" && method === "POST") {
    const user: User = { id: "u_mock", email: "demo@strategylab.local", full_name: "Demo Trader", role: "admin", is_active: true, created_at: daysAgo(0) };
    return ok(user);
  }

  // strategies
  if (pathOnly === "/strategies" && method === "GET") return ok(strategies);
  if (pathOnly === "/strategies/explore" && method === "GET") {
    // Compact mirror of the backend explore catalog for offline browsing
    const catDefs = [
      { id: "all", label: "All", description: "Every prebuilt algo", count: mockTemplates().length },
      { id: "option-buying", label: "Option Buying", description: "Debit spreads & long gamma plays" },
      { id: "credit-spread", label: "Credit Spread", description: "Range-bound premium collection" },
      { id: "short-straddle", label: "Short Straddle", description: "ATM volatility selling" },
      { id: "short-strangle", label: "Short Strangle", description: "OTM wings, wider breakevens" },
      { id: "expiry-day", label: "Expiry Day", description: "Weekly expiry special situations" },
      { id: "intraday", label: "Intraday", description: "5m–15m index scalping systems" },
      { id: "swing", label: "Swing", description: "Daily-timeframe trend riding" },
    ];
    const catOf = (t: { tags: string[] }): string => {
      if (t.tags.includes("weekly")) return "expiry-day";
      if (t.tags.includes("credit")) return t.tags.includes("range") || t.tags.includes("spread") ? "credit-spread" : "short-straddle";
      return "option-buying";
    };
    const algos = mockTemplates().map((t, i) => ({
      id: `mock-algo-${i}`,
      name: t.name,
      category: t.tags.includes("intraday") ? "intraday" : catOf(t),
      description: t.description,
      tags: t.tags,
      complexity: t.tags.includes("ratio") || t.tags.includes("volatility") ? "advanced" : "intermediate",
      min_capital: 65_000 + i * 5_000,
      underlying: (t.definition as { instrument?: { symbol?: string } })?.instrument?.symbol ?? "NIFTY",
      definition: t.definition,
    }));
    const withCounts = catDefs.map((c) =>
      c.id === "all" ? c : { ...c, count: algos.filter((a) => a.category === c.id).length }
    );
    return ok({ categories: withCounts, algos, total: algos.length });
  }
  if (pathOnly === "/strategies/templates" && method === "GET") return ok(mockTemplates());
  if (pathOnly === "/strategies" && method === "POST") {
    const body = JSON.parse((init.body as string) ?? "{}");
    const created: Strategy = {
      id: `s_${Math.random().toString(36).slice(2, 8)}`,
      name: body.name ?? "Untitled Strategy",
      description: body.description ?? null,
      exchange: body.exchange ?? "NSE",
      underlying: body.underlying ?? "NIFTY",
      instrument: body.instrument ?? "options",
      strategy_type: body.strategy_type ?? "intraday",
      status: "draft",
      tags: body.tags ?? [],
      definition: (body.definition as Record<string, unknown>) ?? null,
      current_version: 1,
      created_at: isoDate(new Date()),
      updated_at: isoDate(new Date()),
    };
    strategies = [created, ...strategies];
    return ok(created);
  }
  let m = pathOnly.match(/^\/strategies\/([^/]+)\/clone$/);
  if (m && method === "POST") {
    const src = strategies.find((s) => s.id === m![1]);
    if (!src) return err(404, "Strategy not found");
    const clone: Strategy = { ...src, id: `s_${Math.random().toString(36).slice(2, 8)}`, name: `${src.name} (copy)`, status: "draft", created_at: isoDate(new Date()), updated_at: isoDate(new Date()) };
    strategies = [clone, ...strategies];
    return ok(clone);
  }
  m = pathOnly.match(/^\/strategies\/([^/]+)\/export$/);
  if (m && method === "GET") {
    const s = strategies.find((x) => x.id === m![1]);
    if (!s) return err(404, "Strategy not found");
    const exp: StrategyExportPayload = { name: s.name, description: s.description, exchange: s.exchange, underlying: s.underlying, instrument: s.instrument, strategy_type: s.strategy_type, tags: s.tags, definition: s.definition ?? null };
    return ok(exp);
  }
  m = pathOnly.match(/^\/strategies\/([^/]+)\/report$/);
  if (m && method === "GET") return ok(mockReport(m[1]));
  m = pathOnly.match(/^\/strategies\/([^/]+)\/compare$/);
  if (m && method === "GET") return ok(mockCompare(m[1], Number(params.get("v1") ?? 1), Number(params.get("v2") ?? 1)));
  m = pathOnly.match(/^\/strategies\/([^/]+)$/);
  if (m && method === "PUT") {
    const body = JSON.parse((init.body as string) ?? "{}");
    strategies = strategies.map((s) => (s.id === m![1] ? { ...s, ...body, updated_at: isoDate(new Date()), current_version: s.current_version + 1 } : s));
    const updated = strategies.find((s) => s.id === m![1]);
    return ok(updated);
  }

  // backtests
  if (pathOnly === "/backtests" && method === "GET") return ok([...createdBacktests, ...seedRuns]);
  if (pathOnly === "/backtests" && method === "POST") {
    const body = JSON.parse((init.body as string) ?? "{}");
    const cfg = {
      symbol: body.symbol,
      timeframe: body.timeframe,
      start: body.start,
      end: body.end,
      initial_capital: body.initial_capital,
      costs_pct: body.costs_pct,
    };
    const run = buildRun(String(body.strategy_id ?? "s_ema"), cfg, Math.random().toString(36).slice(2, 7));
    createdBacktests.unshift(run);
    return ok(run);
  }
  m = pathOnly.match(/^\/backtests\/([^/]+)\/candles$/);
  if (m && method === "GET") {
    const run = [...createdBacktests, ...seedRuns].find((r) => r.id === m![1]);
    const sym = run?.config?.symbol ?? "NIFTY";
    return ok(genCandles(m[1] + sym, 120, sym));
  }
  m = pathOnly.match(/^\/backtests\/([^/]+)$/);
  if (m && method === "GET") {
    const run = [...createdBacktests, ...seedRuns].find((r) => r.id === m![1]);
    return run ? ok(run) : err(404, "Run not found");
  }

  // forward tests
  if (pathOnly === "/forward-tests" && method === "GET") return ok(forwardTests);
  if (pathOnly === "/forward-tests" && method === "POST") {
    const body = JSON.parse((init.body as string) ?? "{}");
    const run: ForwardTestRun = {
      id: `ft_${Math.random().toString(36).slice(2, 7)}`,
      strategy_id: String(body.strategy_id ?? "s_ema"),
      account_id: String(body.account_id ?? "pa_1"),
      version_number: 1,
      status: "running",
      last_bar_time: isoDate(new Date()),
      pending_action: "none",
      last_message: "Started.",
      started_at: isoDate(new Date()),
      created_at: isoDate(new Date()),
    };
    forwardTests = [run, ...forwardTests];
    return ok(run);
  }
  m = pathOnly.match(/^\/forward-tests\/([^/]+)\/tick$/);
  if (m && method === "POST") return ok(mockTick(m[1]));
  m = pathOnly.match(/^\/forward-tests\/([^/]+)\/(\w+)$/);
  if (m && method === "POST") {
    const action = m[2];
    forwardTests = forwardTests.map((r) => (r.id === m![1] ? { ...r, status: action === "stop" ? "stopped" : action === "pause" ? "paused" : "running", last_message: `Action: ${action}` } : r));
    const run = forwardTests.find((r) => r.id === m![1]);
    return run ? ok(run) : err(404, "Run not found");
  }

  // optimizations
  if (pathOnly === "/optimizations" && method === "GET") return ok(optRuns);
  if (pathOnly === "/optimizations" && method === "POST") {
    const body = JSON.parse((init.body as string) ?? "{}");
    const run: OptimizationRun = {
      id: `opt_${Math.random().toString(36).slice(2, 7)}`,
      strategy_id: String(body.strategy_id ?? "s_ema"),
      method: body.method ?? "grid",
      param_ranges: body.param_ranges ?? { fast: [5, 9, 13], slow: [15, 21, 26] },
      start: body.start ?? daysAgo(60),
      end: body.end ?? daysAgo(5),
      train_pct: body.train_pct ?? 0.7,
      target_metric: body.target_metric ?? "sharpe_ratio",
      status: "completed",
      total_combinations: 9,
      completed_combinations: 9,
      best_params: { fast: 9, slow: 21 },
      best_metrics: { net_pnl: 18420.5, return_pct: 18.4, sharpe_ratio: 1.92, max_drawdown_pct: 6.1, win_rate: 58.3 },
      created_at: isoDate(new Date()),
    };
    optRuns.push(run);
    return ok(run);
  }
  m = pathOnly.match(/^\/optimizations\/([^/]+)\/results$/);
  if (m && method === "GET") return ok(mockOptResults(m[1]));
  m = pathOnly.match(/^\/optimizations\/([^/]+)$/);
  if (m && method === "GET") {
    const run = optRuns.find((r) => r.id === m![1]);
    return run ? ok(run) : err(404, "Optimization not found");
  }

  // paper accounts
  if (pathOnly === "/paper/accounts" && method === "GET") return ok(paperAccounts);
  if (pathOnly === "/paper/accounts" && method === "POST") {
    const body = JSON.parse((init.body as string) ?? "{}");
    const acc: PaperAccount = { id: `pa_${Math.random().toString(36).slice(2, 7)}`, name: body.name ?? "New Account", initial_capital: Number(body.initial_capital) || 100000, cash_balance: Number(body.initial_capital) || 100000, status: "active", created_at: isoDate(new Date()) };
    paperAccounts = [acc, ...paperAccounts];
    return ok(acc);
  }
  m = pathOnly.match(/^\/paper\/accounts\/([^/]+)$/);
  if (m && method === "GET") return ok(mockPaperDetail(m[1]));

  // data / market
  if (pathOnly === "/data/instruments" && method === "GET") return ok(mockInstruments());
  if (pathOnly === "/data/instruments/sync" && method === "POST") return ok({ synced: 5, received: 5 });
  if (pathOnly === "/data/status" && method === "GET") {
    const st: DataStatus = { instruments: 5, candle_counts: { NIFTY_5m: 1200, BANKNIFTY_5m: 980 }, latest_candle_utc: { NIFTY_5m: daysAgo(1), BANKNIFTY_5m: daysAgo(1) } };
    return ok(st);
  }
  if (pathOnly === "/data/history/ingest" && method === "POST") {
    const body = JSON.parse((init.body as string) ?? "{}");
    const res: IngestResult = { symbol: body.symbol ?? "NIFTY", interval: body.interval ?? "5m", start: body.start ?? daysAgo(30), end: body.end ?? daysAgo(1), fetched: 1200, inserted_or_updated: 1180, duplicates_in_batch: 20, issues: [], coverage: { expected_bars: 1200, actual_unique_bars: 1180, missing_bars: 20, missing_pct: 1.7, status: "warning" } };
    return ok(res);
  }
  m = pathOnly.match(/^\/data\/quality\/([^/]+)$/);
  if (m && method === "GET") {
    const res: QualityReport = { symbol: decodeURIComponent(m[1]), interval: params.get("interval") ?? "5m", candles_checked: 1180, first: daysAgo(30), last: daysAgo(1), issues: [], coverage: { expected_bars: 1200, actual_unique_bars: 1180, missing_bars: 20, missing_pct: 1.7, status: "warning" } };
    return ok(res);
  }
  if (pathOnly === "/market/option-chain" && method === "GET") return ok(mockOptionChain(params.get("underlying") ?? "NIFTY", params.get("expiry") ?? undefined));
  if (pathOnly === "/market/instruments" && method === "GET") return ok(mockInstruments());

  // options lab
  if (pathOnly === "/options/payoff" && method === "POST") return ok(mockPayoff(JSON.parse((init.body as string) ?? "{}")));
  if (pathOnly === "/options/monte-carlo" && method === "POST") return ok(mockMonteCarlo());

  // quant
  if (pathOnly === "/quant/catalog" && method === "GET") return ok(mockCatalog());
  if (pathOnly === "/quant/validate" && method === "POST") return ok(mockValidate());
  if (pathOnly === "/quant/preview" && method === "POST") return ok(mockPreview());

  // ai
  if (pathOnly === "/ai/draft-strategy" && method === "POST") {
    const body = JSON.parse((init.body as string) ?? "{}");
    return ok(mockAiDraft(body.prompt ?? ""));
  }

  // tax report
  if (pathOnly === "/tax/report" && method === "GET") {
    const res = {
      fy: params.get("fy") ?? "2026-27", start: "2026-04-01", end: "2027-03-31",
      segment: params.get("segment") ?? "equity",
      total_trades: 2, winners: 1, losers: 1,
      stcg_pnl: 1450.0, ltcg_pnl: -320.5, gross_profit: 1450.0, gross_loss: -320.5, net_pnl: 1129.5,
      fno_turnover_abs_pnl: 0, est_tax_stcg: 290.0, est_tax_ltcg: 0.0,
      trades: [
        { exit_date: daysAgo(20), underlying: "NIFTY", direction: "long", quantity: 10, entry_price: 23800, exit_price: 23945, realized_pnl: 1450.0, holding_days: 42, category: "STCG" },
        { exit_date: daysAgo(8), underlying: "BANKNIFTY", direction: "short", quantity: 15, entry_price: 51200, exit_price: 51421.33, realized_pnl: -320.5, holding_days: 12, category: "STCG" },
      ],
    };
    return ok(res);
  }
  if (pathOnly === "/tax/report/csv" && method === "GET") {
    return ok("exit_date,underlying,direction,quantity,entry_price,exit_price,realized_pnl,holding_days,category\n");
  }

  // optimizations — heatmap
  if (pathOnly === "/optimizations/heatmap" && method === "POST") {
    const body = JSON.parse((init.body as string) ?? "{}");
    const xs: number[] = body.x_values ?? [5, 10];
    const ys: number[] = body.y_values ?? [20, 30];
    const cells = xs.flatMap((x: number) =>
      ys.map((y: number) => ({ x, y, value: Math.round((Math.sin(x) + Math.cos(y / 10)) * 100) / 100, trades: Math.max(1, Math.round(x % y)) })),
    );
    const best = cells.reduce((a, b) => ((b.value ?? 0) > (a.value ?? 0) ? b : a), cells[0]);
    const worst = cells.reduce((a, b) => ((b.value ?? 0) < (a.value ?? 0) ? b : a), cells[0]);
    return ok({
      x_key: body.x_key ?? "indicators.f.params.length",
      y_key: body.y_key ?? "indicators.s.params.length",
      x_values: [...new Set(xs)].sort((a: number, b: number) => a - b),
      y_values: [...new Set(ys)].sort((a: number, b: number) => a - b),
      metric: body.metric ?? "sharpe_ratio",
      cells,
      best,
      worst,
    });
  }

  // ---- execution (mock broker session) ----
  const execInit = {
    brokers: ["mock", "zerodha", "fyers", "upstox", "angelone", "dhan"],
    orders: [] as ExecutionOrder[],
    positions: [] as ExecutionPosition[],
    pending: [] as { id: string; req: PlaceOrderRequest; created_at: string }[],
    algos: [] as RegisteredAlgoOut[],
    deployments: [] as DeploymentOut[],
    brackets: [] as BracketOut[],
    confirmRequired: false,
    killSwitch: false,
    seq: 0,
  };
  let mExec = pathOnly.match(/^\/execution\/orders\/([^/]+)\/confirm$/);
  if (mExec && method === "POST") {
    const idx = execInit.pending.findIndex((p) => p.id === mExec![1]);
    if (idx === -1) return err(404, "Unknown pending order");
    const p = execInit.pending.splice(idx, 1)[0];
    execInit.seq += 1;
    const order: ExecutionOrder = {
      order_id: p.id,
      broker_order_id: `MOCK${String(execInit.seq).padStart(6, "0")}`,
      symbol: p.req.symbol, exchange: p.req.exchange, segment: p.req.segment,
      side: p.req.side, order_type: p.req.order_type, product: p.req.product ?? "MIS",
      quantity: p.req.quantity, price: p.req.price ?? 0,
      trigger_price: p.req.trigger_price ?? 0,
      filled_quantity: p.req.quantity, pending_quantity: 0,
      status: "COMPLETE", average_price: p.req.price ?? 100,
      tag: p.req.tag ?? null, rejection_reason: null,
    };
    execInit.orders.unshift(order);
    return ok(order);
  }
  mExec = pathOnly.match(/^\/execution\/orders\/([^/]+)\/discard$/);
  if (mExec && method === "POST") {
    const idx = execInit.pending.findIndex((p) => p.id === mExec![1]);
    if (idx === -1) return err(404, "Unknown pending order");
    execInit.pending.splice(idx, 1);
    return ok({ discarded: true, pending_id: mExec[1] });
  }
  if (pathOnly === "/execution/orders/pending/list" && method === "GET") {
    return ok(execInit.pending.map((p) => ({
      pending_id: p.id, symbol: p.req.symbol, exchange: p.req.exchange,
      segment: p.req.segment, side: p.req.side, order_type: p.req.order_type,
      quantity: p.req.quantity, price: p.req.price ?? 0,
      trigger_price: p.req.trigger_price ?? 0, created_at: p.created_at,
    })));
  }
  if (pathOnly === "/execution/orders/place" && method === "POST") {
    const body = JSON.parse((init.body as string) ?? "{}") as PlaceOrderRequest;
    if (execInit.killSwitch) return err(422, JSON.stringify({ risk_violations: ["Kill switch is engaged"] }));
    if (execInit.confirmRequired) {
      execInit.seq += 1;
      const pid = `PEND_${String(execInit.seq).padStart(6, "0")}`;
      execInit.pending.push({ id: pid, req: body, created_at: isoDate(new Date()) });
      return ok({ order_id: pid, broker_order_id: "", symbol: body.symbol, exchange: body.exchange, segment: body.segment, side: body.side, order_type: body.order_type, product: body.product ?? "MIS", quantity: body.quantity, price: body.price ?? 0, trigger_price: body.trigger_price ?? 0, filled_quantity: 0, pending_quantity: body.quantity, status: "PENDING", average_price: 0, tag: body.tag ?? null, rejection_reason: null });
    }
    execInit.seq += 1;
    const order: ExecutionOrder = {
      order_id: `MOCK${String(execInit.seq).padStart(6, "0")}`,
      broker_order_id: `BRK${String(execInit.seq).padStart(6, "0")}`,
      symbol: body.symbol, exchange: body.exchange, segment: body.segment,
      side: body.side, order_type: body.order_type, product: body.product ?? "MIS",
      quantity: body.quantity, price: body.price ?? 0,
      trigger_price: body.trigger_price ?? 0,
      filled_quantity: body.order_type === "MARKET" ? body.quantity : 0,
      pending_quantity: body.order_type === "MARKET" ? 0 : body.quantity,
      status: body.order_type === "MARKET" ? "COMPLETE" : "OPEN",
      average_price: body.order_type === "MARKET" ? (body.price || 22000) : 0,
      tag: body.tag ?? null, rejection_reason: null,
    };
    execInit.orders.unshift(order);
    return ok(order);
  }
  mExec = pathOnly.match(/^\/execution\/orders\/([^/]+)\/cancel$/);
  if (mExec && method === "POST") {
    const o = execInit.orders.find((x) => x.order_id === mExec![1] || x.broker_order_id === mExec![1]);
    if (!o) return err(404, "Order not found");
    o.status = "CANCELLED";
    return ok(o);
  }
  if (pathOnly === "/execution/risk" && method === "GET") {
    return ok({
      kill_switch: execInit.killSwitch,
      max_order_notional: 1_000_000, max_position_notional: 5_000_000,
      max_orders_per_day: 500, orders_today: execInit.orders.length,
      daily_pnl: 0, max_daily_loss: 200_000,
      ops_limit: 10, ops_current: 0,
      orders_placed: execInit.orders.length, trades_executed: execInit.orders.filter((o) => o.status === "COMPLETE").length,
      order_to_trade_ratio: null,
    });
  }
  mExec = pathOnly.match(/^\/execution\/risk\/kill/);
  if (mExec && method === "POST") {
    execInit.killSwitch = params.get("engaged") === "true";
    return ok({ kill_switch: execInit.killSwitch });
  }
  if (pathOnly === "/execution/risk/confirm-mode" && method === "POST") {
    execInit.confirmRequired = params.get("enabled") === "true";
    return ok({ kill_switch: execInit.killSwitch, confirm_required: execInit.confirmRequired });
  }
  if (pathOnly === "/execution/funds" && method === "GET") {
    return ok({ equity: 1_000_000, commodity: 0, used_margin: 45_000, available_cash: 955_000, collateral: 0 });
  }
  if (pathOnly === "/execution/orders" && method === "GET") return ok(execInit.orders);
  if (pathOnly === "/execution/positions" && method === "GET") {
    return ok(execInit.positions);
  }
  if (pathOnly === "/execution/quotes" && method === "GET") {
    const syms = (params.get("symbols") ?? "").split(",").filter(Boolean);
    return ok(syms.map((s) => ({ symbol: s.toUpperCase(), last_price: 22000 + s.length * 10, bid: 21998, ask: 22002, volume: 120000, oi: 50000, change: 105.5, change_pct: 0.48 })));
  }
  if (pathOnly === "/execution/audit" && method === "GET") {
    return ok(execInit.orders.slice(0, 10).map((o) => ({ timestamp: isoDate(new Date()), action: "ORDER_PLACED", detail: `${o.side} ${o.quantity} ${o.symbol}`, broker_order_id: o.broker_order_id, user: "mock" })));
  }
  mExec = pathOnly.match(/^\/execution\/algo\/register$/);
  if (mExec && method === "POST") {
    const body = JSON.parse((init.body as string) ?? "{}");
    const algo: RegisteredAlgoOut = {
      algo_id: `ALGO_${Math.random().toString(36).slice(2, 8).toUpperCase()}`,
      name: String(body.name ?? "Strategy Algo"), segment: String(body.segment ?? "EQUITY"),
      exchange: String(body.exchange ?? "NSE"), strategy_id: body.strategy_id ?? null,
      active: true, registered_at: isoDate(new Date()),
    };
    execInit.algos.push(algo);
    return ok(algo);
  }
  if (pathOnly === "/execution/algo/registered" && method === "GET") return ok(execInit.algos);
  mExec = pathOnly.match(/^\/execution\/algo\/deactivate$/);
  if (mExec && method === "POST") {
    const body = JSON.parse((init.body as string) ?? "{}");
    const algo = execInit.algos.find((a) => a.algo_id === body.algo_id);
    if (!algo) return err(404, "Algo not found");
    algo.active = false;
    return ok({ deactivated: true });
  }
  if (pathOnly === "/execution/algos" && method === "GET") {
    return ok([]);
  }
  if (pathOnly === "/execution/orders/algo" && method === "POST") {
    return err(400, "Algo parent orders are not simulated in mock mode");
  }
  if (pathOnly === "/execution/orders/bracket" && method === "POST") {
    const body = JSON.parse((init.body as string) ?? "{}");
    const bracket: BracketOut = {
      bracket_id: `BRK_${Math.random().toString(36).slice(2, 8).toUpperCase()}`,
      entry_order_id: `MOCK${String(++execInit.seq).padStart(6, "0")}`,
      target_price: Number(body.target_price ?? 0),
      stop_loss_price: Number(body.stop_loss_price ?? 0),
      armed: true, done: false,
    };
    execInit.brackets.push(bracket);
    return ok(bracket);
  }
  if (pathOnly === "/execution/brackets" && method === "GET") return ok(execInit.brackets);
  if (pathOnly === "/execution/orders/process-fills" && method === "POST") return ok([]);
  if (pathOnly === "/execution/deploy" && method === "POST") {
    const body = JSON.parse((init.body as string) ?? "{}");
    const dep: DeploymentOut = {
      deployment_id: `DEP_${Math.random().toString(36).slice(2, 8).toUpperCase()}`,
      strategy_id: String(body.strategy_id ?? ""), algo_id: `ALGO_${Math.random().toString(36).slice(2, 8).toUpperCase()}`,
      broker: String(body.broker ?? "mock"), mode: String(body.mode ?? "paper"),
      name: String(body.name ?? "Deployment"), segment: String(body.segment ?? "EQUITY"),
      exchange: String(body.exchange ?? "NSE"), active: true,
      created_at: isoDate(new Date()),
    };
    execInit.deployments.push(dep);
    return ok(dep);
  }
  if (pathOnly === "/execution/deployments" && method === "GET") return ok(execInit.deployments);

  // ---- options analytics (derived from the synthetic chain) ----
  if (pathOnly === "/options/analytics" && method === "GET") {
    const chain = mockOptionChain(params.get("underlying") ?? "NIFTY", params.get("expiry") ?? undefined);
    const strikes = chain.strikes;
    const totalCallOi = strikes.reduce((s2, r) => s2 + r.call_oi, 0);
    const totalPutOi = strikes.reduce((s2, r) => s2 + r.put_oi, 0);
    const totalCallVol = strikes.reduce((s2, r) => s2 + r.call_volume, 0);
    const totalPutVol = strikes.reduce((s2, r) => s2 + r.put_volume, 0);
    const strikePcr: Record<string, number> = {};
    for (const r of strikes) strikePcr[String(r.strike)] = r.call_oi > 0 ? Math.round((r.put_oi / r.call_oi) * 100) / 100 : 0;

    // Max pain: strike where total writer payout is minimized
    let maxPainStrike = strikes[0]?.strike ?? chain.spot;
    let minPain = Number.POSITIVE_INFINITY;
    const painByStrike: Record<string, number> = {};
    for (const candidate of strikes) {
      let pain = 0;
      for (const r of strikes) {
        pain += r.call_oi * Math.max(chain.spot - r.strike, 0);
        pain += r.put_oi * Math.max(r.strike - chain.spot, 0);
      }
      painByStrike[String(candidate.strike)] = Math.round(pain);
      if (pain < minPain) { minPain = pain; maxPainStrike = candidate.strike; }
    }
    const byOiDesc = [...strikes].sort((a, b) => b.call_oi + b.put_oi - (a.call_oi + a.put_oi));
    const atmRow = strikes.reduce((best, r) =>
      Math.abs(r.strike - chain.spot) < Math.abs(best.strike - chain.spot) ? r : best, strikes[0]);
    const atmIv = atmRow ? (atmRow.call_iv + atmRow.put_iv) / 2 : 14;
    const avgCe = strikes.reduce((s2, r) => s2 + r.call_iv, 0) / (strikes.length || 1);
    const avgPe = strikes.reduce((s2, r) => s2 + r.put_iv, 0) / (strikes.length || 1);

    return ok({
      underlying: chain.underlying, spot: chain.spot, expiry: chain.expiry,
      pcr: {
        pcr_oi: totalCallOi > 0 ? Math.round((totalPutOi / totalCallOi) * 100) / 100 : 0,
        pcr_volume: totalCallVol > 0 ? Math.round((totalPutVol / totalCallVol) * 100) / 100 : 0,
        total_call_oi: totalCallOi, total_put_oi: totalPutOi,
        total_call_volume: totalCallVol, total_put_volume: totalPutVol,
        strike_pcr: strikePcr,
      },
      max_pain: {
        max_pain_strike: maxPainStrike, min_pain: minPain,
        support_resistance: {
          resistance: byOiDesc.slice(0, 3).map((r) => ({ strike: r.strike, oi: r.call_oi, type: "CALL" })),
          support: byOiDesc.slice(0, 3).map((r) => ({ strike: r.strike, oi: r.put_oi, type: "PUT" })),
        },
        pain_by_strike: painByStrike,
      },
      iv_surface: {
        atm_iv: Math.round(atmIv * 100) / 100,
        skew: Math.round((avgPe - avgCe) * 100) / 100,
        kurtosis: 0.12,
        points: strikes.slice(0, 10).map((r) => ({
          strike: r.strike, expiry: chain.expiry, days_to_expiry: 7,
          iv: (r.call_iv + r.put_iv) / 2,
          delta: (r.call_delta - r.put_delta) / 2,
          moneyness: Math.round(((r.strike / chain.spot) - 1) * 10000) / 10000,
        })),
      },
      greeks_heatmap: {
        net_delta: Math.round(strikes.reduce((s2, r) => s2 + r.call_delta + r.put_delta, 0) * 100) / 100,
        net_gamma: Math.round(strikes.reduce((s2, r) => s2 + r.call_gamma + r.put_gamma, 0) * 100) / 100,
        net_theta: Math.round(strikes.reduce((s2, r) => s2 + r.call_theta + r.put_theta, 0) * 100) / 100,
        net_vega: Math.round(strikes.reduce((s2, r) => s2 + r.call_vega + r.put_vega, 0) * 100) / 100,
        strike_greeks: Object.fromEntries(strikes.slice(0, 10).map((r) => [String(r.strike), {
          call_oi: r.call_oi, put_oi: r.put_oi,
          delta: r.call_delta, gamma: r.call_gamma, theta: r.call_theta, vega: r.call_vega,
          call_delta: r.call_delta, put_delta: r.put_delta,
        }])),
      },
      iv_rank_percentile: {
        iv_rank: 42, iv_percentile: 55,
        current_iv: Math.round(atmIv * 100) / 100,
        iv_52w_high: 26.4, iv_52w_low: 9.8,
      },
    });
  }

  return err(404, `Mock has no handler for ${method} ${path}`);
}

// ---- END PART 3 ----

