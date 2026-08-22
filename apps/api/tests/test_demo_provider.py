from datetime import datetime, timedelta

from app.marketdata.demo import DemoProvider


async def test_candles_deterministic():
    provider = DemoProvider()
    start = datetime(2026, 8, 10, 9, 15)
    end = datetime(2026, 8, 10, 10, 0)
    a = await provider.get_historical_data("NIFTY", "5m", start, end)
    b = await provider.get_historical_data("NIFTY", "5m", start, end)
    assert [(c.open, c.high, c.low, c.close) for c in a] == [
        (c.open, c.high, c.low, c.close) for c in b
    ]


async def test_candles_respect_market_hours_and_ohlc():
    provider = DemoProvider()
    start = datetime(2026, 8, 10)  # Monday
    end = start + timedelta(days=2)
    candles = await provider.get_historical_data("NIFTY", "1m", start, end)
    assert candles, "expected demo candles"
    for c in candles:
        assert 9 <= c.timestamp.hour <= 15
        if c.timestamp.hour == 9:
            assert c.timestamp.minute >= 15
        if c.timestamp.hour == 15:
            assert c.timestamp.minute < 30
        assert c.timestamp.weekday() < 5
        assert c.low <= min(c.open, c.close) <= max(c.open, c.close) <= c.high


async def test_interval_aggregation():
    provider = DemoProvider()
    start = datetime(2026, 8, 10, 9, 15)
    end = datetime(2026, 8, 10, 11, 15)
    m1 = await provider.get_historical_data("NIFTY", "1m", start, end)
    m15 = await provider.get_historical_data("NIFTY", "15m", start, end)
    assert len(m1) == 120
    assert len(m15) == 8
    assert abs(m1[0].open - m15[0].open) < 1e-6
    assert abs(max(c.high for c in m1[:15]) - m15[0].high) < 1e-6


async def test_unknown_symbol_rejected():
    provider = DemoProvider()
    try:
        await provider.get_historical_data("FAKE", "5m", datetime(2026, 8, 10), datetime(2026, 8, 11))
        raised = False
    except ValueError:
        raised = True
    assert raised


async def test_option_chain_structure_and_demo_flag():
    provider = DemoProvider()
    chain = await provider.get_option_chain("NIFTY")
    assert chain["is_demo"] is True
    assert chain["provider"] == "demo"
    strikes = chain["strikes"]
    assert len(strikes) == 21
    atm_row = min(strikes, key=lambda r: abs(r["strike"] - chain["spot"]))
    assert -1.0 < atm_row["call_delta"] < 0.0 or 0.4 < atm_row["call_delta"] < 0.6
    assert all(r["call_ltp"] >= 0 and r["put_ltp"] >= 0 for r in strikes)


async def test_instruments_include_major_indices():
    provider = DemoProvider()
    instruments = await provider.get_instruments()
    symbols = {i["symbol"] for i in instruments}
    assert {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"} <= symbols
