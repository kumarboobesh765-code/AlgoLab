"""Paper execution engine.

Processes newly completed candles for one forward test and returns the virtual
fills to apply. Semantics are identical to the backtest engine:

- signals evaluated on bar close, filled at the NEXT bar's open;
- a signal decided at the last processed bar is carried across ticks via the
  run's `pending_action` column, so nothing is lost or double-executed;
- risk exits (stop/target/trailing) fill intrabar with gap-aware prices,
  stop assumed before target, trailing ratchet after the exit check;
- `direction: both` runs stop-and-reverse (`reverse_long` / `reverse_short`
  close the current position and open the opposite one on the same open).

Pure functions only — the API layer owns DB reads/writes and Decimal
conversion.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from app.marketdata.base import Candle
from app.quant.engine import evaluate_definition
from app.quant.schema import StrategyDefinition


@dataclass(slots=True)
class Fill:
    side: str  # BUY | SELL
    quantity: float
    price: float
    reason: str  # entry | exit_signal | stop_loss | trailing_stop | target | end
    time: object  # bar timestamp of the fill
    position_state: dict | None = None  # entry fills: full new-position state
    pnl: float | None = None  # closing fills: realized P&L net of all costs


@dataclass(slots=True)
class PaperStepResult:
    actions: list[Fill] = field(default_factory=list)
    position: dict | None = None  # final open-position state (None = flat)
    pending_action: str | None = None  # carried to the next tick
    realized_pnl: float = 0.0
    last_bar_time: object | None = None


def _pos_dir(position: dict) -> int:
    return 1 if position["direction"] == "long" else -1


def _new_position(
    dir_sign: int,
    qty: float,
    price: float,
    bar: Candle,
    definition: StrategyDefinition,
) -> dict:
    risk = definition.risk
    stop = target = trail = None
    if risk is not None:
        if risk.stop_loss_pct is not None:
            stop = price * (1 - dir_sign * risk.stop_loss_pct / 100.0)
        if risk.target_pct is not None:
            target = price * (1 + dir_sign * risk.target_pct / 100.0)
        if risk.trailing_sl_pct is not None:
            trail = risk.trailing_sl_pct / 100.0
            base_stop = price * (1 - dir_sign * trail)
            if stop is None:
                stop = base_stop
            elif dir_sign == 1:
                stop = max(stop, base_stop)
            else:
                stop = min(stop, base_stop)
    return {
        "direction": "long" if dir_sign == 1 else "short",
        "quantity": qty,
        "entry_price": price,
        "entry_time": bar.timestamp.isoformat(),
        "stop_price": stop,
        "target_price": target,
        "trail_pct": trail,
        "trailed": False,
        "extreme": bar.high if dir_sign == 1 else bar.low,
    }


def required_warmup(definition: StrategyDefinition) -> int:
    """Bars of history needed before incremental signal evaluation is reliable."""
    longest = 5
    for ind in definition.indicators:
        for val in ind.params.values():
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                longest = max(longest, int(val))
    return min(longest * 3, 500)


def step_paper(
    definition: StrategyDefinition,
    history: Sequence[Candle],
    new_candles: Sequence[Candle],
    position_state: dict | None,
    pending_action: str | None,
    cash: float,
    costs_pct: float,
) -> PaperStepResult:
    """Process `new_candles` with `history` as indicator context.

    Indicators are evaluated over history + new bars so crosses that span a
    tick boundary are detected; only the new bars are acted upon.
    """
    candles = [*history, *new_candles]
    start_idx = len(history)
    result = PaperStepResult(
        position=position_state, pending_action=pending_action, last_bar_time=None
    )
    if not new_candles:
        return result

    evaluation = evaluate_definition(definition, candles)
    entry_signals = evaluation.entry_signals
    exit_signals = evaluation.exit_signals

    pos_cfg = definition.position
    direction_mode = pos_cfg.direction
    risk = definition.risk

    position = dict(position_state) if position_state else None
    pending = pending_action
    realized = 0.0

    def size_quantity(price: float) -> float:
        if pos_cfg.quantity_type == "capital_pct":
            pct = pos_cfg.capital_pct if pos_cfg.capital_pct is not None else 100.0
            return max((cash + realized) * pct / 100.0 / price, 0.0)
        return max(pos_cfg.quantity, 0.0)

    def close(index: int, price: float, reason: str) -> None:
        nonlocal position, realized
        assert position is not None
        dir_sign = _pos_dir(position)
        gross = (price - position["entry_price"]) * position["quantity"] * dir_sign
        cost = price * position["quantity"] * costs_pct / 100.0
        pnl = gross - cost - float(position.get("entry_cost") or 0.0)
        realized += pnl
        if reason == "stop_loss" and position.get("trailed"):
            reason = "trailing_stop"
        result.actions.append(
            Fill(
                side="SELL" if dir_sign == 1 else "BUY",
                quantity=position["quantity"],
                price=price,
                reason=reason,
                time=candles[index].timestamp,
                pnl=pnl,
            )
        )
        position = None

    def open_pos(index: int, dir_sign: int) -> None:
        nonlocal position, realized
        price = candles[index].open
        qty = size_quantity(price)
        if qty <= 0:
            return
        entry_cost = price * qty * costs_pct / 100.0
        state = _new_position(dir_sign, qty, price, candles[index], definition)
        state["entry_cost"] = entry_cost
        realized -= entry_cost
        position = state
        result.actions.append(
            Fill(
                side="BUY" if dir_sign == 1 else "SELL",
                quantity=qty,
                price=price,
                reason="entry",
                time=candles[index].timestamp,
                position_state=dict(state),
            )
        )

    for i in range(start_idx, len(candles)):
        bar = candles[i]
        # 1. Execute the action decided at the previous bar's close / tick.
        if pending in ("exit", "reverse_long", "reverse_short"):
            if position is not None:
                close(i, bar.open, "signal")
            if pending.startswith("reverse_"):
                open_pos(i, 1 if pending == "reverse_long" else -1)
        elif pending in ("entry_long", "entry_short") and position is None:
            open_pos(i, 1 if pending == "entry_long" else -1)
        pending = None

        # 2. Manage the open position through this bar.
        if position is not None:
            dir_sign = _pos_dir(position)
            stop = position.get("stop_price")
            target = position.get("target_price")
            if dir_sign == 1:
                if stop is not None and bar.low <= stop:
                    close(i, min(bar.open, stop), "stop_loss")
                elif target is not None and bar.high >= target:
                    close(i, max(bar.open, target), "target")
            else:
                if stop is not None and bar.high >= stop:
                    close(i, max(bar.open, stop), "stop_loss")
                elif target is not None and bar.low <= target:
                    close(i, min(bar.open, target), "target")

            # Trailing ratchet AFTER the exit check (mirrors the backtest engine).
            if position is not None and position.get("trail_pct") is not None:
                trail = position["trail_pct"]
                if _pos_dir(position) == 1:
                    position["extreme"] = max(position["extreme"], bar.high)
                    trailed = position["extreme"] * (1 - trail)
                    if position["stop_price"] is None or trailed > position["stop_price"]:
                        position["stop_price"] = trailed
                        position["trailed"] = True
                else:
                    position["extreme"] = min(position["extreme"], bar.low)
                    trailed = position["extreme"] * (1 + trail)
                    if position["stop_price"] is None or trailed < position["stop_price"]:
                        position["stop_price"] = trailed
                        position["trailed"] = True

        # 3. Read signals at this bar's close → carry to the next bar/tick.
        if position is None and pending is None and entry_signals[i]:
            if direction_mode == "short_only":
                pending = "entry_short"
            elif direction_mode in ("long_only", "both"):
                pending = "entry_long"
        elif position is not None and pending is None and exit_signals[i]:
            if direction_mode == "both":
                pending = "reverse_short" if _pos_dir(position) == 1 else "reverse_long"
            else:
                pending = "exit"

        result.last_bar_time = bar.timestamp

    result.position = position
    result.pending_action = pending
    result.realized_pnl = realized
    return result
