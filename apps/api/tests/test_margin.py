"""Tests for the F&O margin estimator and /options/margin endpoint."""

import pytest

from app.options.margin import MarginLeg, estimate_margin

BASE = "/api/v1"


def test_long_option_margin_is_premium_only():
    est = estimate_margin(
        "NIFTY", 24000,
        [MarginLeg("buy", "CE", strike=24000, lots=1, premium=180)],
        lot_size=65,
    )
    assert abs(est.total_margin - 180 * 65) < 0.01
    assert est.defined_risk


def test_short_straddle_blocks_span_plus_exposure():
    est = estimate_margin(
        "NIFTY", 24000,
        [
            MarginLeg("sell", "CE", strike=24000, lots=1, premium=150),
            MarginLeg("sell", "PE", strike=24000, lots=1, premium=140),
        ],
        lot_size=65,
    )

    def _block(premium: float) -> float:
        return (
            premium * 65                       # collected
            + (24000 * 65) * 0.032             # span
            + 0.20 * (premium * 65)            # cushion
            + (24000 * 65) * 0.010             # exposure
        )

    assert abs(est.total_margin - (_block(150) + _block(140))) < 1.0
    assert not est.defined_risk
    assert est.hedge_discount == 0.0


def test_hedged_spread_gets_discount():
    unhedged = estimate_margin(
        "NIFTY", 24000,
        [MarginLeg("sell", "CE", strike=24100, lots=1, premium=120)],
        lot_size=65,
    ).total_margin

    hedged = estimate_margin(
        "NIFTY", 24000,
        [
            MarginLeg("sell", "CE", strike=24100, lots=1, premium=120),
            MarginLeg("buy", "CE", strike=24200, lots=1, premium=70),
        ],
        lot_size=65,
    )
    # Long side pays premium only
    assert abs(hedged.premium_outlay - 70 * 65) < 0.01
    # Hedge discount = min(long protection, 90% of short block)
    assert hedged.hedge_discount > 0
    # Total must be strictly cheaper than the naked short plus the long premium
    assert hedged.total_margin < unhedged + 70 * 65
    assert hedged.defined_risk


def test_futures_margin_uses_notional():
    est = estimate_margin(
        "NIFTY", 24000,
        [MarginLeg("sell", "FUT", lots=1)],
        lot_size=65,
    )
    expected = 24000 * 65 * (0.032 + 0.010)
    assert abs(est.total_margin - expected) < 1.0
    assert not est.defined_risk


@pytest.mark.asyncio
async def test_margin_endpoint_roundtrip(client, auth_headers):
    payload = {
        "underlying": "NIFTY",
        "spot": 24000,
        "lot_size": 65,
        "legs": [
            {"action": "sell", "option_type": "CE", "strike": 24100, "lots": 1, "premium": 120},
            {"action": "buy", "option_type": "CE", "strike": 24200, "lots": 1, "premium": 70},
        ],
    }
    resp = await client.post(f"{BASE}/options/margin", json=payload, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_margin"] > 0
    assert data["defined_risk"] is True
    assert "disclaimer" in data


@pytest.mark.asyncio
async def test_margin_endpoint_validates(client, auth_headers):
    resp = await client.post(
        f"{BASE}/options/margin",
        json={"underlying": "NIFTY", "spot": -5, "lot_size": 65, "legs": []},
        headers=auth_headers,
    )
    assert resp.status_code == 422
