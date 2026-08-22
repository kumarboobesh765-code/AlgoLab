export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const TOKEN_KEY = "strategylab_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) {
    window.localStorage.setItem(TOKEN_KEY, token);
  } else {
    window.localStorage.removeItem(TOKEN_KEY);
  }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const resp = await fetch(`${API_URL}/api/v1${path}`, { ...init, headers });

  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* keep statusText */
    }
    throw new ApiError(resp.status, detail);
  }

  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

// ---- shared API types ----

export interface Health {
  status: string;
  app: string;
  env: string;
  database: string;
  market_data_provider: string;
  market_data_is_demo: boolean;
  market_data_provider_configured?: boolean;
  trading_mode: string;
  live_trading_available: boolean;
}

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
  is_active: boolean;
  created_at: string;
}

export interface Strategy {
  id: string;
  name: string;
  description: string | null;
  exchange: string;
  underlying: string;
  instrument: string;
  strategy_type: string;
  status: string;
  tags: string[];
  definition: Record<string, unknown> | null;
  current_version: number;
  created_at: string;
  updated_at: string;
}

export interface Instrument {
  id: string;
  security_id: string;
  exchange: string;
  segment: string;
  exchange_segment: string | null;
  symbol: string;
  name: string | null;
  underlying: string | null;
  instrument_type: string | null;
  expiry_code: number | null;
  expiry: string | null;
  strike: number | null;
  option_type: string | null;
  lot_size: number;
  tick_size: number;
  status: string;
}

// ---- market data ----

export interface Candle {
  timestamp: string;
  instrument_id: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  oi: number | null;
}

export interface OptionChainRow {
  strike: number;
  call_ltp: number;
  put_ltp: number;
  call_iv: number;
  put_iv: number;
  call_oi: number;
  put_oi: number;
  call_volume: number;
  put_volume: number;
  call_delta: number;
  put_delta: number;
}

export interface OptionChain {
  underlying: string;
  spot: number;
  expiry: string;
  strikes: OptionChainRow[];
  provider: string;
  is_demo: boolean;
}

// ---- data manager ----

export interface IngestResult {
  symbol: string;
  interval: string;
  start: string;
  end: string;
  fetched: number;
  inserted_or_updated: number;
  duplicates_in_batch: number;
  issues: DataIssue[];
  coverage: Coverage | null;
}

export interface DataIssue {
  type: string;
  detail: string;
  examples: string[];
}

export interface Coverage {
  expected_bars: number;
  actual_unique_bars: number;
  missing_bars: number;
  missing_pct: number;
  status: "healthy" | "warning" | "critical";
}

export interface QualityReport {
  symbol: string;
  interval: string;
  candles_checked: number;
  first: string | null;
  last: string | null;
  issues: DataIssue[];
  coverage: Coverage | null;
}

export interface DataStatus {
  instruments: number;
  candle_counts: Record<string, number>;
  latest_candle_utc: Record<string, string | null>;
}

// ---- quant engine ----

export interface ParamSpecInfo {
  kind: "int" | "float" | "str";
  default: number | string;
  ge?: number;
  le?: number;
  choices?: string[];
}

export interface IndicatorCatalogEntry {
  type: string;
  description: string;
  outputs: string[];
  params: Record<string, ParamSpecInfo>;
}

export interface QuantCatalog {
  timeframes: string[];
  indicators: IndicatorCatalogEntry[];
}

export interface ValidationResponse {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

export interface PreviewResponse {
  symbol: string;
  timeframe: string;
  bars_evaluated: number;
  provider: string;
  is_demo: boolean;
  entry_signals: number;
  exit_signals: number;
  last_bar_entry_signal: boolean;
  last_bar_exit_signal: boolean;
  indicator_tail: Record<string, Record<string, number | null>>;
}

// ---- backtest engine ----

export interface BacktestSummary {
  initial_capital: number;
  final_equity: number;
  net_pnl: number;
  return_pct: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  profit_factor: number;
  avg_win: number;
  avg_loss: number;
  largest_win: number;
  largest_loss: number;
  max_drawdown_pct: number;
  sharpe_ratio: number;
  total_costs: number;
  timeframe: string;
}

export interface BacktestTrade {
  direction: "long" | "short";
  quantity: number;
  entry_time: string;
  entry_price: number;
  exit_time: string;
  exit_price: number;
  exit_reason: string;
  pnl: number;
  pnl_pct: number;
  bars_held: number;
}

export interface BacktestResults {
  summary: BacktestSummary;
  equity_curve: { time: string; equity: number }[];
  trades: BacktestTrade[];
  error?: string;
}

export interface BacktestRun {
  id: string;
  strategy_id: string;
  version_number: number;
  status: string;
  config: {
    symbol?: string;
    timeframe?: string;
    start?: string;
    end?: string;
    initial_capital?: number;
    costs_pct?: number;
    bars?: number;
  } | null;
  result_summary: BacktestResults | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface BacktestRunRequest {
  strategy_id: string;
  start?: string;
  end?: string;
  initial_capital?: number;
  costs_pct?: number;
}

// ---- paper accounts ----

export interface PaperAccount {
  id: string;
  name: string;
  initial_capital: number;
  cash_balance: number;
  status: string;
  created_at: string;
}

export interface PaperAccountDetail extends PaperAccount {
  equity: number;
  unrealized_pnl: number;
  open_positions: PaperPosition[];
  closed_positions: PaperPosition[];
  recent_orders: PaperOrder[];
}

export interface PaperPosition {
  id: string;
  strategy_id?: string;
  direction: string;
  quantity: number;
  entry_price: number;
  entry_time?: string;
  stop_price?: number;
  target_price?: number;
  status: string;
  last_close?: number;
  unrealized_pnl?: number;
  exit_price?: number;
  exit_time?: string;
  exit_reason?: string;
  realized_pnl?: number;
}

export interface PaperOrder {
  id: string;
  side: string;
  quantity: number;
  filled_price: number;
  reason: string;
  signal_time?: string;
  created_at?: string;
}

export interface PaperAccountCreate {
  name: string;
  initial_capital: number;
}

// ---- forward tests ----

export interface ForwardTestRun {
  id: string;
  strategy_id: string;
  account_id: string;
  version_number: number;
  status: string;
  last_bar_time?: string;
  pending_action?: string;
  last_message?: string;
  started_at: string;
  stopped_at?: string;
  created_at: string;
}

export interface ForwardTestCreate {
  strategy_id: string;
  account_id: string;
}

export interface TickResult {
  run_id: string;
  bars_processed: number;
  fills: Array<{
    side: string;
    quantity: number;
    price: number;
    reason: string;
    time: string;
    pnl?: number;
  }>;
  open_position?: PaperPosition;
  message?: string;
}

// ---- optimization ----

export interface OptimizationRun {
  id: string;
  strategy_id: string;
  method: string;
  param_ranges: Record<string, number[]>;
  start: string;
  end: string;
  train_pct: number;
  target_metric: string;
  status: string;
  total_combinations: number;
  completed_combinations: number;
  best_params: Record<string, unknown> | null;
  best_metrics: Record<string, number> | null;
  error?: string;
  started_at?: string;
  finished_at?: string;
  created_at: string;
}

export interface OptimizationResult {
  id: string;
  run_id: string;
  rank: number | null;
  params: Record<string, unknown>;
  net_pnl: number | null;
  return_pct: number | null;
  win_rate: number | null;
  profit_factor: number | null;
  max_drawdown_pct: number | null;
  sharpe_ratio: number | null;
  total_trades: number | null;
  train_sharpe: number | null;
  test_sharpe: number | null;
  status: string;
  error?: string;
  created_at: string;
}

export interface OptimizationCreate {
  strategy_id: string;
  method: "grid" | "walk_forward";
  param_ranges: Record<string, number[]>;
  start: string;
  end: string;
  train_pct?: number;
  target_metric?: string;
  initial_capital?: number;
  costs_pct?: number;
}

// ---- polish: reports, import/export, compare ----

export interface StrategyReport {
  strategy: {
    id: string;
    name: string;
    status: string;
    exchange: string;
    underlying: string;
    instrument: string;
    strategy_type: string;
    tags: string[];
    current_version: number;
    has_definition: boolean;
    created_at: string;
    updated_at: string;
  };
  versions: {
    version: number;
    created_at: string;
    changelog: string | null;
    has_definition: boolean;
  }[];
  latest_backtest: {
    id: string;
    created_at: string;
    config: Record<string, unknown> | null;
    summary: BacktestSummary | null;
    trades_count: number;
  } | null;
  total_backtests: number;
  optimizations: {
    id: string;
    method: string;
    target_metric: string;
    total_combinations: number;
    best_params: Record<string, unknown> | null;
    best_metrics: Record<string, number> | null;
    created_at: string;
  }[];
}

export interface StrategyExportPayload {
  name: string;
  description: string | null;
  exchange: string;
  underlying: string;
  instrument: string;
  strategy_type: string;
  tags: string[];
  definition: Record<string, unknown> | null;
}

export interface VersionCompare {
  v1_version: number;
  v2_version: number;
  v1_definition: Record<string, unknown> | null;
  v2_definition: Record<string, unknown> | null;
  v1_backtest: { summary: BacktestSummary | null; created_at: string | null } | null;
  v2_backtest: { summary: BacktestSummary | null; created_at: string | null } | null;
  v1_created: string;
  v2_created: string;
}

// ---- trade replay ----

export interface ReplayCandle {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}
