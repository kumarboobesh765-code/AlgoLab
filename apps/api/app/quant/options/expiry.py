"""Expiry date calculations for options.

Supports weekly/monthly expiry selection with formulas like:
- THIS_WEEK, NEXT_WEEK, THIS_MONTH, NEXT_MONTH
- WEEKLY, MONTHLY (nearest)
"""

import calendar
from datetime import date, datetime, timedelta

from app.quant.options.formulas import ExpiryType


def is_market_holiday(dt: date) -> bool:
    """Check if date is a market holiday (basic weekend + common holidays).
    
    For production, integrate with NSE/BSE holiday calendar.
    """
    if dt.weekday() >= 5:  # Saturday=5, Sunday=6
        return True
    return False


def get_next_trading_day(dt: date) -> date:
    """Get next trading day (skip weekends/holidays)."""
    next_day = dt + timedelta(days=1)
    while is_market_holiday(next_day):
        next_day += timedelta(days=1)
    return next_day


def get_last_thursday(year: int, month: int) -> date:
    """Get last Thursday of the month (monthly expiry for NSE)."""
    last_day = calendar.monthrange(year, month)[1]
    dt = date(year, month, last_day)
    while dt.weekday() != 3:  # Thursday = 3
        dt -= timedelta(days=1)
    return dt


def get_thursday_of_week(year: int, month: int, day: int) -> date:
    """Get Thursday of the week containing the given day."""
    dt = date(year, month, day)
    while dt.weekday() != 3:
        dt += timedelta(days=1)
    return dt


def get_weekly_expiry(reference: date) -> date:
    """Get this week's Thursday expiry."""
    days_ahead = 3 - reference.weekday()  # Thursday = 3
    if days_ahead < 0:
        days_ahead += 7
    expiry = reference + timedelta(days=days_ahead)
    while is_market_holiday(expiry):
        expiry = get_next_trading_day(expiry)
    return expiry


def get_monthly_expiry(reference: date) -> date:
    """Get this month's last Thursday expiry."""
    last_thu = get_last_thursday(reference.year, reference.month)
    if last_thu < reference:
        # Next month
        next_month = reference.month + 1 if reference.month < 12 else 1
        next_year = reference.year if reference.month < 12 else reference.year + 1
        last_thu = get_last_thursday(next_year, next_month)
    while is_market_holiday(last_thu):
        last_thu = get_next_trading_day(last_thu)
    return last_thu


def get_expiry_by_type(
    expiry_type: ExpiryType | str,
    reference: date | None = None,
) -> date:
    """Get expiry date based on type formula.

    Args:
        expiry_type: ExpiryType enum or string formula
        reference: Reference date (defaults to today)

    Returns:
        Expiry date
    """
    if isinstance(expiry_type, str):
        expiry_type = ExpiryType(expiry_type.upper())

    ref = reference or date.today()

    if expiry_type in (ExpiryType.THIS_WEEK, ExpiryType.WEEKLY):
        return get_weekly_expiry(ref)

    if expiry_type == ExpiryType.NEXT_WEEK:
        this_week = get_weekly_expiry(ref)
        next_week = this_week + timedelta(days=7)
        while is_market_holiday(next_week):
            next_week = get_next_trading_day(next_week)
        return next_week

    if expiry_type in (ExpiryType.THIS_MONTH, ExpiryType.MONTHLY):
        return get_monthly_expiry(ref)

    if expiry_type == ExpiryType.NEXT_MONTH:
        next_month = ref.month + 1 if ref.month < 12 else 1
        next_year = ref.year if ref.month < 12 else ref.year + 1
        return get_last_thursday(next_year, next_month)

    return get_weekly_expiry(ref)


def days_to_expiry(reference: date, expiry: date) -> float:
    """Calculate days to expiry including fractional days."""
    if expiry <= reference:
        return 0.0
    delta = expiry - reference
    return float(delta.days)


def parse_expiry_formula(
    formula: str,
    reference: date | None = None,
) -> date:
    """Parse and evaluate an expiry formula string.

    Supported formats:
    - "THIS_WEEK" -> This week's Thursday
    - "NEXT_WEEK" -> Next week's Thursday
    - "THIS_MONTH" -> This month's last Thursday
    - "NEXT_MONTH" -> Next month's last Thursday
    - "WEEKLY" -> Nearest weekly expiry
    - "MONTHLY" -> Nearest monthly expiry
    - "2024-12-26" -> Fixed date (YYYY-MM-DD)

    Args:
        formula: Expiry formula string
        reference: Reference date (defaults to today)

    Returns:
        Expiry date
    """
    formula = formula.strip().upper()
    ref = reference or date.today()

    if formula in ("THIS_WEEK", "WEEKLY"):
        return get_weekly_expiry(ref)

    if formula == "NEXT_WEEK":
        this_week = get_weekly_expiry(ref)
        next_week = this_week + timedelta(days=7)
        while is_market_holiday(next_week):
            next_week = get_next_trading_day(next_week)
        return next_week

    if formula in ("THIS_MONTH", "MONTHLY"):
        return get_monthly_expiry(ref)

    if formula == "NEXT_MONTH":
        next_month = ref.month + 1 if ref.month < 12 else 1
        next_year = ref.year if ref.month < 12 else ref.year + 1
        return get_last_thursday(next_year, next_month)

    try:
        return datetime.strptime(formula, "%Y-%m-%d").date()
    except ValueError:
        pass

    return get_weekly_expiry(ref)


def get_expiry_schedule(year: int) -> list[date]:
    """Get all weekly expiries for a year (for backtesting)."""
    expiries = []
    for month in range(1, 13):
        for week in range(1, 6):
            first_day = date(year, month, 1)
            first_thursday = first_day + timedelta(days=(3 - first_day.weekday()) % 7)
            if first_thursday.month != month:
                continue
            expiry = first_thursday + timedelta(weeks=week - 1)
            if expiry.month != month:
                break
            if not is_market_holiday(expiry):
                expiries.append(expiry)
    return expiries


def get_monthly_expiries(year: int) -> list[date]:
    """Get all monthly expiries for a year."""
    expiries = []
    for month in range(1, 13):
        last_thu = get_last_thursday(year, month)
        if not is_market_holiday(last_thu):
            expiries.append(last_thu)
    return expiries
