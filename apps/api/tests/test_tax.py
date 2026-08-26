"""Tests for /tax endpoints (STCG/LTCG buckets, F&O turnover, CSV)."""

import uuid
from datetime import UTC, datetime

import pytest

from app.models import PaperAccount, PaperPosition

BASE = "/api/v1/tax"


async def make_account(db_session, user_id) -> PaperAccount:
    acc = PaperAccount(user_id=user_id, name="TaxAcc", initial_capital=100_000, cash_balance=100_000)
    db_session.add(acc)
    await db_session.commit()
    await db_session.refresh(acc)
    return acc


def _user_id_from_token(client) -> tuple:
    return None  # resolved via auth_headers fixture user below


@pytest.mark.asyncio
async def test_report_requires_auth(client):
    resp = await client.get(f"{BASE}/report")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_stcg_ltcg_buckets(client, auth_headers, db_session):
    # Resolve the test user id
    me = (await client.get("/api/v1/auth/me", headers=auth_headers)).json()
    uid = me["id"]
    strategy_resp = await client.post(
        "/api/v1/strategies",
        json={"name": "TaxStrat", "underlying": "NIFTY", "instrument": "index", "strategy_type": "intraday"},
        headers=auth_headers,
    )
    assert strategy_resp.status_code == 201
    strategy_uuid = uuid.UUID(strategy_resp.json()["id"])

    acc = await make_account(db_session, uuid.UUID(uid))

    def mkpos(entry_dt, exit_dt, pnl):
        return PaperPosition(
            account_id=acc.id, strategy_id=strategy_uuid, direction="long",
            quantity=10, entry_price=100, exit_price=100 + pnl / 10,
            entry_time=entry_dt, status="closed",
            exit_time=exit_dt, exit_reason="target", realized_pnl=pnl,
        )

    db_session.add_all([
        mkpos(datetime(2025, 4, 10, tzinfo=UTC), datetime(2025, 6, 1, tzinfo=UTC), 1500.0),   # 52d → STCG
        mkpos(datetime(2024, 3, 1, tzinfo=UTC), datetime(2025, 5, 15, tzinfo=UTC), -800.0),   # 440d → LTCG loss
        mkpos(datetime(2026, 2, 1, tzinfo=UTC), datetime(2026, 2, 20, tzinfo=UTC), 300.0),    # FY25-26 → STCG win
        mkpos(datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 12, 31, tzinfo=UTC), 999.0),   # exits FY23-24 → excluded
    ])
    await db_session.commit()

    resp = await client.get(f"{BASE}/report?fy=2025-26", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["start"] == "2025-04-01"
    assert data["end"] == "2026-03-31"
    assert data["total_trades"] == 3
    stcg = [t for t in data["trades"] if t["category"] == "STCG"]
    ltcg = [t for t in data["trades"] if t["category"] == "LTCG"]
    assert len(stcg) == 2 and len(ltcg) == 1
    assert abs(data["stcg_pnl"] - 1800.0) < 0.01
    assert abs(data["ltcg_pnl"] + 800.0) < 0.01
    # STCG est tax: 20% of positive STCG 1800 = 360
    assert abs(data["est_tax_stcg"] - 360.0) < 0.01


@pytest.mark.asyncio
async def test_fno_turnover_uses_abs_pnl(client, auth_headers, db_session):
    me = (await client.get("/api/v1/auth/me", headers=auth_headers)).json()
    acc = await make_account(db_session, uuid.UUID(me["id"]))
    strat = (await client.post(
        "/api/v1/strategies",
        json={"name": "FnO", "underlying": "NIFTY", "instrument": "index", "strategy_type": "options"},
        headers=auth_headers,
    )).json()

    db_session.add(PaperPosition(
        account_id=acc.id, strategy_id=uuid.UUID(strat["id"]), direction="short",
        quantity=75, entry_price=120, exit_price=90,
        entry_time=datetime(2025, 5, 1, tzinfo=UTC), status="closed",
        exit_time=datetime(2025, 5, 20, tzinfo=UTC), exit_reason="target", realized_pnl=-2250.0,
    ))
    await db_session.commit()

    resp = await client.get(f"{BASE}/report?fy=2025-26&segment=fno", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_trades"] == 1
    assert all(t["category"] == "BUSINESS" for t in data["trades"])
    assert abs(data["fno_turnover_abs_pnl"] - 2250.0) < 0.01


@pytest.mark.asyncio
async def test_csv_download(client, auth_headers, db_session):
    me = (await client.get("/api/v1/auth/me", headers=auth_headers)).json()
    acc = await make_account(db_session, uuid.UUID(me["id"]))
    strat = (await client.post(
        "/api/v1/strategies",
        json={"name": "CsvStrat", "underlying": "NIFTY", "instrument": "index", "strategy_type": "intraday"},
        headers=auth_headers,
    )).json()
    db_session.add(PaperPosition(
        account_id=acc.id, strategy_id=uuid.UUID(strat["id"]), direction="long",
        quantity=10, entry_price=100, exit_price=110,
        entry_time=datetime(2025, 4, 2, tzinfo=UTC), status="closed",
        exit_time=datetime(2025, 4, 30, tzinfo=UTC), exit_reason="target", realized_pnl=100.0,
    ))
    await db_session.commit()

    resp = await client.get(f"{BASE}/report/csv?fy=2025-26", headers=auth_headers)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    body = resp.text
    assert body.startswith("exit_date,underlying,direction")
    assert "2025-04-30" in body


@pytest.mark.asyncio
async def test_invalid_fy_400(client, auth_headers):
    resp = await client.get(f"{BASE}/report?fy=2024-27", headers=auth_headers)
    assert resp.status_code == 400
