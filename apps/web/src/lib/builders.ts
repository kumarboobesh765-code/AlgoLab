import type { IndicatorCatalogEntry, QuantCatalog } from "@/lib/api";

// sessionStorage keys used to hand a definition JSON to the Technical Builder
export const TEMPLATE_HANDOFF_KEY = "strategylab_template_json";
export const TEMPLATE_HANDOFF_NAME = "strategylab_template_name";
// sessionStorage key carrying the strategy id when editing (save = PUT)
export const STRATEGY_EDIT_KEY = "strategylab_edit_id";

// Canonical strategy-definition v1 types (mirrors apps/api/app/quant/schema.py)

export interface Operand {
  kind: "price" | "constant" | "variable" | "indicator" | "formula";
  price?: string;
  value?: number;
  name?: string;
  ref?: string;
  expression?: string;
}

export interface Condition {
  left: Operand;
  op: string;
  right: Operand;
}

export interface ConditionGroup {
  logic: "ALL" | "ANY";
  conditions: (Condition | ConditionGroup)[];
}

export interface Variable {
  name: string;
  value: number;
}

export interface IndicatorDef {
  id: string;
  type: string;
  params: Record<string, number | string | { var: string }>;
}

export interface StrategyDefinitionV1 {
  version: 1;
  timeframe: string;
  instrument: { symbol: string; exchange: string; segment: string };
  variables: Variable[];
  indicators: IndicatorDef[];
  entry: ConditionGroup;
  exit: ConditionGroup | null;
  risk: {
    stop_loss_pct: number | null;
    target_pct: number | null;
    trailing_sl_pct: number | null;
  } | null;
  position: {
    direction: "long_only" | "short_only" | "both";
    quantity_type: "fixed" | "capital_pct";
    quantity: number;
    capital_pct: number | null;
  };
  legs?: OptionLeg[];
  // AlgoTest-parity options fields
  overall?: OverallConfig | null;
  entry_momentum?: EntryMomentumConfig | null;
  time_control?: TimeControlConfig | null;
  legwise?: LegwiseSettings | null;
}

export interface OptionLeg {
  action: "buy" | "sell";
  option_type: "CE" | "PE";
  strike?: number | null;
  strike_offset?: number | null;
  lots?: number;
  expiry?: string | null;
  // Per-leg stop loss
  sl_mode?: "pts" | "%" | "underlying_pts" | "underlying_pct" | null;
  sl_value?: number | null;
  // Per-leg target
  target_mode?: "pts" | "%" | "underlying_pts" | "underlying_pct" | null;
  target_value?: number | null;
  // Per-leg trailing stop
  trail_mode?: "pts" | "%" | null;
  trail_step?: number | null;
  trail_by?: number | null;
  delta_trail?: boolean;
  // Re-entry
  reentry_on_sl?: "asap" | "asap_reverse" | "cost" | "cost_reverse" | "momentum" | "momentum_reverse" | "lazy_leg" | null;
  reentry_on_target?: "asap" | "asap_reverse" | "cost" | "cost_reverse" | "momentum" | "momentum_reverse" | "lazy_leg" | null;
  max_reentries?: number;
  // Lazy leg overrides
  lazy_sl_mode?: "pts" | "%" | null;
  lazy_sl_value?: number | null;
  lazy_target_mode?: "pts" | "%" | null;
  lazy_target_value?: number | null;
  lazy_action?: "buy" | "sell" | null;
  lazy_option_type?: "CE" | "PE" | null;
  lazy_strike_offset?: number | null;
  // Square-off behavior
  square_off?: "partial" | "complete";
}

export interface LegwiseSettings {
  trail_sl_to_breakeven: "none" | "sl_legs" | "all_legs";
  square_off_on_leg_sl: boolean;
}

export interface OverallConfig {
  overall_sl: number | null;
  overall_target: number | null;
  overall_trail_sl: number | null;
  overall_trail_every: number | null;
  lock_profit: number | null;
  lock_at: number | null;
  lock_and_trail_profit: number | null;
  lock_and_trail_at: number | null;
  lock_and_trail_by: number | null;
}

export interface EntryMomentumConfig {
  enabled: boolean;
  direction: "up" | "down";
  mode: "pts" | "%";
  value: number;
}

export interface TimeControlConfig {
  no_entry_after: string | null;
  no_reentry_after: string | null;
  time_exit: string | null;
}

export const OPERATORS = [
  { value: "GT", label: "is above (>)" },
  { value: "GTE", label: "is at or above (≥)" },
  { value: "LT", label: "is below (<)" },
  { value: "LTE", label: "is at or below (≤)" },
  { value: "CROSS_ABOVE", label: "crosses above ↑" },
  { value: "CROSS_BELOW", label: "crosses below ↓" },
] as const;

export const PRICE_SOURCES = [
  "close",
  "open",
  "high",
  "low",
  "volume",
  "hl2",
  "hlc3",
  "ohlc4",
] as const;

export const TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "1d"] as const;

export function emptyDefinition(timeframe: string = "5m"): StrategyDefinitionV1 {
  return {
    version: 1,
    timeframe,
    instrument: { symbol: "NIFTY", exchange: "NSE", segment: "index" },
    variables: [],
    indicators: [],
    entry: { logic: "ALL", conditions: [] },
    exit: null,
    risk: { stop_loss_pct: null, target_pct: null, trailing_sl_pct: null },
    position: {
      direction: "long_only",
      quantity_type: "fixed",
      quantity: 1,
      capital_pct: null,
    },
  };
}

export function defaultOperand(): Operand {
  return { kind: "price", price: "close" };
}

export function defaultCondition(): Condition {
  return { left: defaultOperand(), op: "GT", right: { kind: "constant", value: 0 } };
}

/** A readable one-line summary of an operand for lists/flow views. */
export function operandLabel(op: Operand): string {
  switch (op.kind) {
    case "price":
      return op.price ?? "close";
    case "constant":
      return String(op.value ?? 0);
    case "variable":
      return `\${${op.name ?? "?"}}`;
    case "indicator":
      return op.ref ?? "?";
    case "formula":
      return `= ${op.expression ?? "?"}`;
    default:
      return "?";
  }
}

export function operatorLabel(op: string): string {
  return OPERATORS.find((o) => o.value === op)?.label ?? op;
}

export function uniqueIndicatorId(base: string, existing: string[]): string {
  let candidate = base.toLowerCase();
  let n = 2;
  while (existing.includes(candidate)) {
    candidate = `${base.toLowerCase()}_${n}`;
    n += 1;
  }
  return candidate;
}

export function addIndicatorFromCatalog(
  def: StrategyDefinitionV1,
  entry: IndicatorCatalogEntry,
): StrategyDefinitionV1 {
  const id = uniqueIndicatorId(entry.type, def.indicators.map((i) => i.id));
  const params: IndicatorDef["params"] = {};
  for (const [name, spec] of Object.entries(entry.params)) {
    params[name] = spec.default;
  }
  return {
    ...def,
    indicators: [...def.indicators, { id, type: entry.type, params }],
  };
}

export function isCondition(node: Condition | ConditionGroup): node is Condition {
  return !("logic" in node);
}

/** Client-side sanity check before hitting /quant/validate. */
export function quickIssues(def: StrategyDefinitionV1): string[] {
  const issues: string[] = [];
  if (!def.instrument.symbol.trim()) issues.push("Symbol is required");
  if (def.entry.conditions.length === 0)
    issues.push("Entry needs at least one condition");
  const ids = new Set<string>();
  for (const ind of def.indicators) {
    if (ids.has(ind.id)) issues.push(`Duplicate indicator id "${ind.id}"`);
    ids.add(ind.id);
  }
  return issues;
}

export function catalogEntry(
  catalog: QuantCatalog | null,
  type: string,
): IndicatorCatalogEntry | undefined {
  return catalog?.indicators.find((i) => i.type === type);
}
