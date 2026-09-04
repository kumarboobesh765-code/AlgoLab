"""Canonical strategy definition — the single source of truth.

Every builder compiles to this JSON shape; backtest and paper engines consume
it unchanged. Versioned: `version: 1`. Extend only in backward-compatible ways
or bump the version.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.quant.conditions import validate_condition_node
from app.quant.formula import parse_formula
from app.quant.indicators import INDICATORS, IndicatorError, validate_params

TIMEFRAMES = ("1m", "5m", "15m", "30m", "1h", "1d")
DIRECTIONS = ("long_only", "short_only", "both")


class InstrumentRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=100)
    exchange: str = Field(default="NSE", min_length=1, max_length=10)
    segment: Literal["index", "equity", "futures", "options"] = "index"


class Variable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-z_][a-z0-9_]*$", min_length=1, max_length=50)
    value: float


class IndicatorDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z_][a-z0-9_]*$", min_length=1, max_length=50)
    type: str = Field(min_length=1, max_length=20)
    params: dict[str, Any] = Field(default_factory=dict)


class Operand(BaseModel):
    """Tagged union via `kind`."""

    model_config = ConfigDict(extra="allow")

    kind: Literal["price", "constant", "variable", "indicator", "formula"]


class Condition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left: dict[str, Any]
    op: str
    right: dict[str, Any]


class ConditionGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    logic: Literal["ALL", "ANY"] = "ALL"
    conditions: list[dict[str, Any]] = Field(min_length=1)


class RiskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stop_loss_pct: float | None = Field(default=None, gt=0, le=100)
    target_pct: float | None = Field(default=None, gt=0, le=1000)
    trailing_sl_pct: float | None = Field(default=None, gt=0, le=100)


class PositionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    direction: Literal["long_only", "short_only", "both"] = "long_only"
    quantity_type: Literal["fixed", "capital_pct"] = "fixed"
    quantity: float = Field(default=1, gt=0)
    capital_pct: float | None = Field(default=None, gt=0, le=100)


class LegwiseSettings(BaseModel):
    """Cross-leg interaction settings (e.g. breakeven trail, square-off propagation)."""

    model_config = ConfigDict(extra="forbid")

    # When any leg's SL hits, move SL to breakeven for:
    trail_sl_to_breakeven: Literal["none", "sl_legs", "all_legs"] = "none"
    # Square-off propagation: if one leg SL hits, square off all legs
    square_off_on_leg_sl: bool = False


class OverallConfig(BaseModel):
    """Strategy-level overall risk management in MTM (mark-to-market) terms."""

    model_config = ConfigDict(extra="forbid")

    overall_sl: float | None = Field(default=None, description="MTM stop loss in ₹")
    overall_target: float | None = Field(default=None, description="MTM target in ₹")
    # Trailing: trail overall SL by Y for every X profit
    overall_trail_sl: float | None = Field(default=None, description="Trail step in ₹")
    overall_trail_every: float | None = Field(default=None, description="Trail trigger every ₹")
    # Lock profit: lock X when profit reaches Y
    lock_profit: float | None = Field(default=None, description="Lock ₹ profit")
    lock_at: float | None = Field(default=None, description="when MTM reaches ₹")
    # Lock and trail: lock X at Y, then trail
    lock_and_trail_profit: float | None = Field(default=None, description="Lock ₹ at threshold")
    lock_and_trail_at: float | None = Field(default=None, description="MTM threshold ₹")
    lock_and_trail_by: float | None = Field(default=None, description="Trail locked profit by ₹")
    # Re-entry on overall SL / Target
    overall_reentry_on_sl: Literal["asap", "asap_reverse", "cost", "cost_reverse", "momentum", "momentum_reverse", "reexecute", "reexecute_reverse"] | None = None
    overall_reentry_on_target: Literal["asap", "asap_reverse", "cost", "cost_reverse", "momentum", "momentum_reverse", "reexecute", "reexecute_reverse"] | None = None


class RangeBreakoutConfig(BaseModel):
    """Range breakout entry configuration."""

    model_config = ConfigDict(extra="forbid")

    start_time: str = Field(default="09:15", description="HH:MM — range start")
    end_time: str = Field(default="09:30", description="HH:MM — range end")
    entry_on: Literal["high", "low"] = "high"
    reentry_on_sl: Literal["asap", "asap_reverse", "cost", "cost_reverse", "momentum", "momentum_reverse", "reexecute", "reexecute_reverse", "range_breakout"] | None = None
    reentry_on_target: Literal["asap", "asap_reverse", "cost", "cost_reverse", "momentum", "momentum_reverse", "reexecute", "reexecute_reverse", "range_breakout"] | None = None


class EntryMomentumConfig(BaseModel):
    """Enter trade only when combined premium moves by X from start."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    direction: Literal["up", "down"] = "up"
    mode: Literal["pts", "%"] = "pts"
    value: float = Field(default=0, ge=0)


class TimeControlConfig(BaseModel):
    """Time-based entry and exit controls."""

    model_config = ConfigDict(extra="forbid")

    no_entry_after: str | None = Field(default=None, description="HH:MM — no new entries after")
    no_reentry_after: str | None = Field(default=None, description="HH:MM — no re-entries after")
    time_exit: str | None = Field(default=None, description="HH:MM — force exit all at")


class OptionLeg(BaseModel):
    """A single F&O option leg (used by the Leg Builder / options strategies)."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["buy", "sell"] = "buy"
    option_type: Literal["CE", "PE"] = "CE"
    strike: float | None = None
    strike_offset: int | None = None
    strike_formula: str | None = None  # e.g., "ATM+200", "SPOT-5%", "DELTA:0.20", "PREMIUM>=50", "CLOSEST_PREMIUM:50", "DELTA_RANGE:0.10:0.30", "STRADDLE_WIDTH:2", "ATM_STRADDLE_PREMIUM_PCT:20"
    strike_selection: Literal[
        "strike_type",
        "premium_ge",
        "premium_le",
        "premium_range",
        "closest_premium",
        "delta_range",
        "straddle_width",
        "atm_straddle_premium_pct",
        "closest_delta",
        "synthetic_future",
        "pct_of_atm",
    ] | None = None
    strike_selection_value: float | None = None  # primary value (e.g., premium threshold, delta target)
    strike_selection_value_2: float | None = None  # secondary value (e.g., range high, delta high)
    lots: int = Field(default=1, ge=1)
    lots_formula: str | None = None  # e.g., "DELTA_NEUTRAL", "CAPITAL_PCT:10"
    expiry: str | None = None
    expiry_formula: str | None = None  # e.g., "THIS_WEEK", "NEXT_WEEK", "THIS_MONTH", "NEXT_MONTH"

    # Simple Momentum — entry delayed until premium/underlying moves by X
    momentum_mode: Literal[
        "none",
        "pts_up", "pts_down",
        "pct_up", "pct_down",
        "underlying_pts_up", "underlying_pts_down",
        "underlying_pct_up", "underlying_pct_down",
    ] = "none"
    momentum_value: float = Field(default=0, ge=0)

    # Per-leg stop loss
    sl_mode: Literal["pts", "%", "underlying_pts", "underlying_pct", "delta"] | None = None
    sl_value: float | None = None

    # Per-leg target
    target_mode: Literal["pts", "%", "underlying_pts", "underlying_pct"] | None = None
    target_value: float | None = None

    # Per-leg trailing stop loss
    trail_mode: Literal["pts", "%"] | None = None
    trail_step: float | None = None  # move SL by this much
    trail_by: float | None = None  # for every this much favor
    delta_trail: bool = False  # trail when delta moves in favor

    # Re-entry after SL / Target
    reentry_on_sl: Literal["asap", "asap_reverse", "cost", "cost_reverse", "momentum", "momentum_reverse", "lazy_leg", "reexecute", "reexecute_reverse", "range_breakout"] | None = None
    reentry_on_target: Literal["asap", "asap_reverse", "cost", "cost_reverse", "momentum", "momentum_reverse", "lazy_leg", "reexecute", "reexecute_reverse", "range_breakout"] | None = None
    max_reentries: int = Field(default=0, ge=0, le=20)

    # Lazy leg override params (when reentry mode is "lazy_leg")
    lazy_sl_mode: Literal["pts", "%"] | None = None
    lazy_sl_value: float | None = None
    lazy_target_mode: Literal["pts", "%"] | None = None
    lazy_target_value: float | None = None
    lazy_action: Literal["buy", "sell"] | None = None
    lazy_option_type: Literal["CE", "PE"] | None = None
    lazy_strike_offset: int | None = None

    # Square-off behavior when this leg's SL/Target hits
    square_off: Literal["partial", "complete"] = "partial"


class OptionGreeks(BaseModel):
    """Option Greeks for a single leg at a point in time."""

    model_config = ConfigDict(extra="forbid")

    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    rho: float = 0.0
    iv: float = 0.0
    price: float = 0.0


class OptionPosition(BaseModel):
    """An option position with current Greeks and P&L."""

    model_config = ConfigDict(extra="forbid")

    leg_index: int
    symbol: str
    action: str
    option_type: str
    strike: float
    expiry: str
    lots: int
    entry_price: float
    current_price: float
    greeks: OptionGreeks
    unrealized_pnl: float = 0.0
    day_pnl: float = 0.0


class OptionsStrategy(BaseModel):
    """A multi-leg options strategy (straddle, strangle, iron condor, etc.)."""

    model_config = ConfigDict(extra="forbid")

    name: str = ""
    legs: list[OptionLeg] = Field(default_factory=list, max_length=12)
    underlying: InstrumentRef | None = None
    strategy_type: Literal["custom", "straddle", "strangle", "iron_condor", "butterfly", "calendar", "vertical_spread", "ratio_spread"] = "custom"
    target_delta: float | None = None  # For delta-neutral strategies
    auto_adjust: bool = False  # Auto-roll/hedge


class StrategyDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    timeframe: str
    instrument: InstrumentRef
    builder: str | None = None  # e.g. "legs" for options-leg strategies
    variables: list[Variable] = Field(default_factory=list, max_length=50)
    indicators: list[IndicatorDef] = Field(default_factory=list, max_length=50)
    legs: list[OptionLeg] = Field(default_factory=list, max_length=8)
    entry: ConditionGroup
    exit: ConditionGroup | None = None
    risk: RiskConfig | None = None
    position: PositionConfig = Field(default_factory=PositionConfig)
    # AlgoTest-parity options fields
    overall: OverallConfig | None = None
    entry_momentum: EntryMomentumConfig | None = None
    time_control: TimeControlConfig | None = None
    legwise: LegwiseSettings | None = None
    range_breakout: RangeBreakoutConfig | None = None
    # Strategy-level settings
    strategy_type: Literal["intraday", "intraday_same_day", "btst", "positional"] = "intraday"
    skip_initial_candles: int = Field(default=0, ge=0, le=50, description="Skip first N candles before evaluating")
    max_position_in_a_day: int = Field(default=0, ge=0, le=100, description="Max entries per day (0 = unlimited)")
    cash_or_futures: Literal["cash", "futures"] = "cash"
    reentry_time_restriction: Literal["none", "after_time", "before_time"] = "none"

    @field_validator("timeframe")
    @classmethod
    def _timeframe(cls, v: str) -> str:
        if v not in TIMEFRAMES:
            raise ValueError(f"timeframe must be one of {list(TIMEFRAMES)}")
        return v


# ------------------------------------------------------- deep validation


def validate_definition(data: Any) -> tuple[list[str], list[str]]:
    """Full validation of a raw JSON definition.

    Returns `(errors, warnings)`. Errors make the definition invalid; warnings
    are advisory (unused indicators/variables).
    """
    errors: list[str] = []
    warnings: list[str] = []

    try:
        definition = StrategyDefinition.model_validate(data)
    except Exception as exc:  # noqa: BLE001 - report instead of raise
        return [f"Schema error: {exc}"], []

    variable_names = {v.name for v in definition.variables}
    duplicate_vars = len(variable_names) != len(definition.variables)
    if duplicate_vars:
        errors.append("Duplicate variable names are not allowed")

    indicator_ids: set[str] = set()
    for ind in definition.indicators:
        if ind.id in indicator_ids:
            errors.append(f"Duplicate indicator id {ind.id!r}")
        indicator_ids.add(ind.id)
        if ind.type not in INDICATORS:
            errors.append(
                f"Indicator {ind.id!r}: unknown type {ind.type!r}; "
                f"available: {sorted(INDICATORS)}"
            )
            continue
        # Resolve numeric params that reference variables.
        resolved_params: dict[str, float | str] = {}
        for pname, pvalue in ind.params.items():
            if isinstance(pvalue, dict) and set(pvalue) == {"var"}:
                var_name = pvalue["var"]
                if var_name not in variable_names:
                    errors.append(
                        f"Indicator {ind.id!r}.{pname} references unknown variable {var_name!r}"
                    )
                    continue
                value = next(v.value for v in definition.variables if v.name == var_name)
                pspec = INDICATORS[ind.type].params.get(pname)
                if (
                    pspec is not None
                    and pspec.kind == "int"
                    and isinstance(value, float)
                    and value.is_integer()
                ):
                    value = int(value)
                resolved_params[pname] = value
            else:
                resolved_params[pname] = pvalue
        try:
            validate_params(ind.type, resolved_params)
        except IndicatorError as exc:
            errors.append(f"Indicator {ind.id!r}: {exc}")

    for side, group in (("entry", definition.entry), ("exit", definition.exit)):
        if group is None:
            continue
        node_errors = validate_condition_node(group.model_dump(), variable_names)
        errors.extend(f"{side}.{e}" for e in node_errors)

    # Formula operands must parse at validation time.
    _validate_formulas_parse(definition, errors)

    used_refs = _collect_indicator_refs(definition.entry.model_dump())
    if definition.exit is not None:
        used_refs |= _collect_indicator_refs(definition.exit.model_dump())
    for ind_id in sorted(indicator_ids - used_refs):
        warnings.append(f"Indicator {ind_id!r} is defined but never referenced")

    used_vars = _collect_variable_names(definition)
    for var_name in sorted(variable_names - used_vars):
        warnings.append(f"Variable {var_name!r} is defined but never used")

    return errors, warnings


def _walk_condition_nodes(node: dict):
    if "logic" in node:
        for child in node.get("conditions", []):
            yield from _walk_condition_nodes(child)
    else:
        yield node


def _collect_indicator_refs(node: dict) -> set[str]:
    refs: set[str] = set()
    for cond in _walk_condition_nodes(node):
        for side in ("left", "right"):
            operand = cond.get(side) or {}
            if operand.get("kind") == "indicator":
                refs.add(operand.get("ref", "").partition(".")[0])
            elif operand.get("kind") == "formula":
                text = operand.get("expression", "")
                import re

                for match in re.findall(r"[A-Za-z_][A-Za-z0-9_.]*", text):
                    if "." in match or not match.isupper():
                        refs.add(match.partition(".")[0])
    return refs


def _collect_variable_names(definition: StrategyDefinition) -> set[str]:
    names: set[str] = set()
    nodes = [definition.entry.model_dump()]
    if definition.exit is not None:
        nodes.append(definition.exit.model_dump())
    for node in nodes:
        for cond in _walk_condition_nodes(node):
            for side in ("left", "right"):
                operand = cond.get(side) or {}
                if operand.get("kind") == "variable":
                    names.add(operand.get("name"))
                elif operand.get("kind") == "formula":
                    import re

                    text = operand.get("expression", "")
                    for match in re.findall(r"[a-z_][a-z0-9_]*", text):
                        names.add(match)
    for ind in definition.indicators:
        for pvalue in ind.params.values():
            if isinstance(pvalue, dict) and "var" in pvalue:
                names.add(pvalue["var"])
    return names


def _validate_formulas_parse(definition: StrategyDefinition, errors: list[str]) -> None:
    """Parse every formula operand so syntax errors surface at validation time."""
    nodes = [definition.entry.model_dump()]
    if definition.exit is not None:
        nodes.append(definition.exit.model_dump())
    for node in nodes:
        for cond in _walk_condition_nodes(node):
            for side in ("left", "right"):
                operand = cond.get(side) or {}
                if operand.get("kind") == "formula":
                    try:
                        parse_formula(operand.get("expression", ""))
                    except Exception as exc:  # noqa: BLE001
                        errors.append(f"Formula parse error: {exc}")
