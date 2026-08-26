"""Indian tax reporting for closed paper trades.

Equity delivery view: STCG (< 365 days held) vs LTCG (>= 366 days).
F&O view: business-income turnover = sum of absolute P&L + sell-side turnover.
"""

from datetime import date, timedelta

from pydantic import BaseModel


class TaxTrade(BaseModel):
    exit_date: str
    underlying: str
    direction: str
    quantity: float
    entry_price: float
    exit_price: float
    realized_pnl: float
    holding_days: int
    category: str  # STCG | LTCG | BUSINESS


class TaxSummary(BaseModel):
    segment: str
    total_trades: int
    winners: int
    losers: int
    stcg_pnl: float
    ltcg_pnl: float
    gross_profit: float
    gross_loss: float
    net_pnl: float
    # F&O-only fields (0.0 for equity)
    fno_turnover_abs_pnl: float = 0.0
    stcg_rate_pct: float = 20.0
    ltcg_rate_pct: float = 12.5
    ltcg_exempt_limit: float = 125_000.0
    est_tax_stcg: float = 0.0
    est_tax_ltcg: float = 0.0


def parse_fy(fy: str) -> tuple[date, date]:
    """'2025-26' → (2025-04-01, 2026-03-31)."""
    parts = fy.split("-")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        raise ValueError("Financial year must look like '2025-26'")
    start_year = int(parts[0])
    end_short = int(parts[1])
    expected_end = (start_year + 1) % 100
    if end_short != expected_end:
        raise ValueError(f"FY end '{parts[1]}' does not follow start '{parts[0]}' (expected {expected_end:02d})")
    return date(start_year, 4, 1), date(start_year + 1, 3, 31)


def classify(holding_days: int, segment: str) -> str:
    if segment == "fno":
        return "BUSINESS"
    return "LTCG" if holding_days >= 366 else "STCG"


def build_summary(trades: list[TaxTrade], segment: str) -> TaxSummary:
    stcg = sum(t.realized_pnl for t in trades if t.category == "STCG")
    ltcg = sum(t.realized_pnl for t in trades if t.category == "LTCG")
    gross_profit = sum(t.realized_pnl for t in trades if t.realized_pnl > 0)
    gross_loss = sum(t.realized_pnl for t in trades if t.realized_pnl < 0)

    taxable_ltcg = max(0.0, ltcg - TaxSummary.model_fields["ltcg_exempt_limit"].default)
    est_tax_stcg = max(0.0, stcg) * (TaxSummary.model_fields["stcg_rate_pct"].default / 100)
    est_tax_ltcg = taxable_ltcg * (TaxSummary.model_fields["ltcg_rate_pct"].default / 100)

    return TaxSummary(
        segment=segment,
        total_trades=len(trades),
        winners=sum(1 for t in trades if t.realized_pnl > 0),
        losers=sum(1 for t in trades if t.realized_pnl <= 0),
        stcg_pnl=round(stcg, 2),
        ltcg_pnl=round(ltcg, 2),
        gross_profit=round(gross_profit, 2),
        gross_loss=round(gross_loss, 2),
        net_pnl=round(stcg + ltcg, 2),
        fno_turnover_abs_pnl=round(sum(abs(t.realized_pnl) for t in trades), 2) if segment == "fno" else 0.0,
        est_tax_stcg=round(est_tax_stcg, 2),
        est_tax_ltcg=round(est_tax_ltcg, 2),
    )


def trades_to_csv(trades: list[TaxTrade]) -> str:
    header = ["exit_date", "underlying", "direction", "quantity", "entry_price", "exit_price", "realized_pnl", "holding_days", "category"]
    lines = [",".join(header)]
    for t in trades:
        lines.append(",".join([
            t.exit_date, t.underlying.replace(",", ""), t.direction,
            f"{t.quantity:g}", f"{t.entry_price:.2f}", f"{t.exit_price:.2f}",
            f"{t.realized_pnl:.2f}", str(t.holding_days), t.category,
        ]))
    return "\n".join(lines) + "\n"


def holding_days(entry: date, exit_: date) -> int:
    return max(0, (exit_ - entry).days)


def next_day(d: date) -> date:
    return d + timedelta(days=1)
