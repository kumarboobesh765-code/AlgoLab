"""Indian market calendar — NSE/BSE trading holidays.

Static list for 2024-2026 (per NSE circulars). Used by backtests/forward tests
to skip non-trading days, and exposed via /calendar/holidays.
"""

from datetime import date, timedelta

# (month, day) per year — dates NSE was/will be closed for trading
NSE_HOLIDAYS: dict[int, set[date]] = {
    2024: {
        date(2024, 1, 22),   # Special live trading session timing change (partial)
        date(2024, 1, 26),   # Republic Day
        date(2024, 3, 8),    # Mahashivratri
        date(2024, 3, 25),   # Holi
        date(2024, 3, 29),   # Good Friday
        date(2024, 4, 11),   # Id-Ul-Fitr
        date(2024, 4, 17),   # Shri Ram Navami
        date(2024, 5, 1),    # Maharashtra Day
        date(2024, 5, 20),   # Lok Sabha Elections (both sessions merged)
        date(2024, 6, 17),   # Bakri Id
        date(2024, 7, 17),   # Muharram
        date(2024, 8, 15),   # Independence Day
        date(2024, 10, 2),   # Gandhi Jayanti
        date(2024, 11, 1),   # Diwali Laxmi Pujan (special timings; no evening session)
        date(2024, 11, 15),  # Gurunanak Jayanti
        date(2024, 11, 20),  # Maha Panchami
        date(2024, 12, 25),  # Christmas
    },
    2025: {
        date(2025, 2, 26),   # Mahashivratri
        date(2025, 3, 14),   # Holi
        date(2025, 3, 31),   # Id-Ul-Fitr
        date(2025, 4, 10),   # Shri Mahavir Jayanti
        date(2025, 4, 14),   # Dr. Ambedkar Jayanti
        date(2025, 4, 18),   # Good Friday
        date(2025, 5, 1),    # Maharashtra Day
        date(2025, 8, 15),   # Independence Day
        date(2025, 8, 27),   # Ganesh Chaturthi
        date(2025, 10, 2),   # Gandhi Jayanti / Dussehra
        date(2025, 10, 21),  # Diwali Laxmi Pujan (no evening session)
        date(2025, 10, 22),  # Balipratipada
        date(2025, 11, 5),   # Gurunanak Jayanti
        date(2025, 12, 25),  # Christmas
    },
    2026: {
        date(2026, 1, 26),   # Republic Day
        date(2026, 2, 15),   # Mahashivratri (tentative)
        date(2026, 3, 4),    # Holi (tentative)
        date(2026, 3, 21),   # Id-Ul-Fitr (tentative)
        date(2026, 4, 1),    # Shri Mahavir Jayanti (tentative)
        date(2026, 4, 3),    # Good Friday
        date(2026, 4, 14),   # Dr. Ambedkar Jayanti
        date(2026, 5, 1),    # Maharashtra Day
        date(2026, 8, 15),   # Independence Day
        date(2026, 10, 2),   # Gandhi Jayanti
        date(2026, 11, 9),   # Diwali Laxmi Pujan (tentative)
        date(2026, 11, 24),  # Gurunanak Jayanti (tentative)
        date(2026, 12, 25),  # Christmas
    },
}

ALL_HOLIDAYS: set[date] = set().union(*NSE_HOLIDAYS.values()) if NSE_HOLIDAYS else set()


def is_trading_holiday(d: date) -> bool:
    """True when NSE/BSE is fully closed on this calendar date."""
    return d in ALL_HOLIDAYS


def holidays_in_range(start: date, end: date) -> list[date]:
    return sorted(d for d in ALL_HOLIDAYS if start <= d <= end)


# ------------------------------------------------------- transaction costs

def stt_delivery(buy_value: float, sell_value: float, trade_date: date | None = None) -> float:
    """STT on equity delivery: 0.1% both sides (unchanged by Budget 2026)."""
    return (buy_value + sell_value) * 0.001


def stt_intraday(sell_value: float, trade_date: date | None = None) -> float:
    """STT on equity intraday: 0.025% sell side only (unchanged by Budget 2026)."""
    return sell_value * 0.00025


def stt_futures_sell(sell_value: float, trade_date: date | None = None) -> float:
    """STT on futures sell side: 0.05% from Apr 1 2026 (was 0.02%)."""
    d = trade_date or date.today()
    rate = 0.0005 if d >= date(2026, 4, 1) else 0.0002
    return sell_value * rate


def stt_options_sell(sell_value: float, trade_date: date | None = None) -> float:
    """STT on options sell side (premium): 0.15% from Apr 1 2026 (was 0.10%)."""
    d = trade_date or date.today()
    rate = 0.0015 if d >= date(2026, 4, 1) else 0.001
    return sell_value * rate


def exchange_txn_charges(value: float, segment: str = "equity") -> float:
    """NSE transaction charges by segment."""
    rates = {"equity": 2.97e-5, "futures": 1.73e-5, "options": 3.51e-5}
    return value * rates.get(segment, rates["equity"])


def sebi_charges(value: float) -> float:
    """SEBI turnover fee: Rs 10 per crore."""
    return value * 1e-6


def stamp_duty(value: float, side: str = "buy", segment: str = "equity") -> float:
    """Stamp duty — buy side only."""
    if side != "buy":
        return 0.0
    rates = {"equity": 1e-5, "intraday": 3e-5, "futures": 2e-6, "options": 3e-4}
    cap = {"equity": None, "intraday": None, "futures": None, "options": None}
    duty = value * rates.get(segment, rates["equity"])
    if cap.get(segment):
        duty = min(duty, cap[segment])
    return duty


def gst(charges_taxable: float) -> float:
    """18% GST on brokerage + txn charges + SEBI fees."""
    return charges_taxable * 0.18


def total_trade_cost(
    buy_value: float,
    sell_value: float,
    brokerage_per_order: float = 20.0,
    segment: str = "equity",
    product: str = "delivery",
    trade_date: date | None = None,
) -> dict[str, float]:
    """Full Indian-market cost breakdown for one round-trip trade.

    STT rates are date-aware: Budget 2026 hiked F&O STT effective Apr 1, 2026
    (futures 0.02%→0.05%, options premium 0.10%→0.15%).

    Returns a dict with every statutory component plus the total.
    """
    d = trade_date or date.today()
    brokerage = brokerage_per_order * 2
    txn = exchange_txn_charges(buy_value + sell_value, segment)
    sebi = sebi_charges(buy_value + sell_value)

    if product == "delivery":
        s_tt = stt_delivery(buy_value, sell_value, d)
        sd_buy = stamp_duty(buy_value, "buy", "equity")
        sd_sell = stamp_duty(sell_value, "sell", "equity")
    elif product == "intraday":
        s_tt = stt_intraday(sell_value, d)
        sd_buy = stamp_duty(buy_value, "buy", "intraday")
        sd_sell = 0.0
    elif product == "futures":
        s_tt = stt_futures_sell(sell_value, d)
        sd_buy = stamp_duty(buy_value, "buy", "futures")
        sd_sell = 0.0
    else:  # options
        s_tt = stt_options_sell(sell_value, d)
        sd_buy = stamp_duty(buy_value, "buy", "options")
        sd_sell = 0.0

    g = gst(brokerage + txn + sebi)
    total = brokerage + txn + sebi + s_tt + sd_buy + sd_sell + g
    return {
        "brokerage": round(brokerage, 2),
        "stt": round(s_tt, 2),
        "exchange_transaction": round(txn, 2),
        "sebi": round(sebi, 2),
        "stamp_duty": round(sd_buy + sd_sell, 2),
        "gst": round(g, 2),
        "total": round(total, 2),
    }


# ------------------------------------------------------- index expiries + lot sizes

# Lot sizes per 2025-26 NSE/BSE revisions (contract-value based; verify against
# the latest exchange circular before live use — these change periodically).
LOT_SIZES: dict[str, int] = {
    "NIFTY": 65,
    "BANKNIFTY": 30,
    "FINNIFTY": 60,
    "MIDCPNIFTY": 120,
    "NIFTYNXT50": 25,
    "SENSEX": 20,
    "BANKEX": 30,
    "SENSEX50": 60,
}

# Freeze quantities — orders above this are rejected by the exchange
FREEZE_QTY: dict[str, int] = {
    "NIFTY": 1800,
    "BANKNIFTY": 900,
    "FINNIFTY": 1800,
    "MIDCPNIFTY": 2800,
    "NIFTYNXT50": 2500,
    "SENSEX": 1000,
    "BANKEX": 1500,
}

# Weekly-expiry indices (SEBI rationalization): only NIFTY on NSE (Tuesday)
# and SENSEX on BSE (Thursday) retain weekly contracts. Everything else is
# monthly-only, expiring on the LAST weekday of the month.
WEEKLY_EXPIRY_INDICES = {"NIFTY", "SENSEX"}
BSE_INDICES = {"SENSEX", "BANKEX", "SENSEX50"}


def _exchange_expiry_weekday(symbol: str) -> int:
    """NSE derivatives expire Tuesday (1), BSE Thursday (3) since Sep 2025."""
    return 3 if symbol in BSE_INDICES else 1


def _last_weekday(year: int, month: int, weekday: int) -> date:
    """Monthly F&O expiry convention: last given weekday of the month."""
    if month == 12:
        last_day = date(year, 12, 31)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)
    offset = (last_day.weekday() - weekday) % 7
    return last_day - timedelta(days=offset)


def _next_weekday(d: date, weekday: int) -> date:
    days_ahead = (weekday - d.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return d + timedelta(days=days_ahead)


def upcoming_expiries(symbol: str, from_date: date, count: int = 4) -> list[date]:
    """Next `count` expiry dates for an index (holiday-adjusted).

    Rules (post Sep-2025): NIFTY weekly on Tuesdays, SENSEX weekly on
    Thursdays; all other NSE indices monthly on the last Tuesday, BSE
    indices monthly on the last Thursday. Holidays shift expiry to the
    previous trading day.
    """
    symbol = symbol.upper()
    out: list[date] = []
    cursor = from_date
    year = cursor.year

    if symbol in WEEKLY_EXPIRY_INDICES:
        weekly_day = _exchange_expiry_weekday(symbol)
        while len(out) < count:
            candidate = _next_weekday(cursor, weekly_day)
            while is_trading_holiday(candidate):
                candidate = date.fromordinal(candidate.toordinal() - 1)
            out.append(candidate)
            cursor = candidate + timedelta(days=1)
        return sorted(out)[:count]

    # Monthly-only index: last expiry-weekday of each month
    wd = _exchange_expiry_weekday(symbol)
    while len(out) < count:
        candidate = _last_weekday(year, cursor.month, wd)
        if candidate <= cursor:
            nxt_m = cursor.month % 12 + 1
            nxt_y = cursor.year + (1 if cursor.month == 12 else 0)
            candidate = _last_weekday(nxt_y, nxt_m, wd)
        while is_trading_holiday(candidate):
            candidate = date.fromordinal(candidate.toordinal() - 1)
        out.append(candidate)
        nxt_m = candidate.month % 12 + 1
        nxt_y = candidate.year + (1 if candidate.month == 12 else 0)
        cursor = date(nxt_y, nxt_m, 1)
        year = nxt_y
    return sorted(out)[:count]


def validate_order_quantity(symbol: str, quantity: int) -> list[str]:
    """Lot-size + freeze-quantity validation warnings for an F&O order."""
    issues: list[str] = []
    sym = symbol.upper()
    lot = LOT_SIZES.get(sym)
    freeze = FREEZE_QTY.get(sym)
    if lot and quantity % lot != 0:
        issues.append(
            f"{sym} trades in lots of {lot}: quantity {quantity} is not a multiple of the lot size"
        )
    if freeze and quantity > freeze:
        issues.append(
            f"Quantity {quantity} exceeds the {sym} freeze limit of {freeze} — split the order"
        )
    return issues
