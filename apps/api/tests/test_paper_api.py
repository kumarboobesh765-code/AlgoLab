"""Integration tests for /paper/accounts endpoints (list/detail/delete/guard)."""

from app.core.deps import get_provider_instance
from app.main import app
from app.marketdata.demo import DemoProvider

BASE = "/api/v1/paper/accounts"


def override_demo_provider():
    app.dependency_overrides[get_provider_instance] = lambda: DemoProvider()


async def create_account(client, headers, name="paper-test") -> dict:
    resp = await client.post(
        BASE,
        json={"name": name, "initial_capital": 500_000},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_requires_auth(client):
    assert (await client.get(BASE)).status_code == 401
    assert (await client.post(BASE, json={})).status_code == 401


async def test_create_list_detail(client, auth_headers):
    account = await create_account(client, auth_headers)
    assert account["initial_capital"] == 500_000
    assert account["status"] == "active"

    listed = (await client.get(BASE, headers=auth_headers)).json()
    assert [a["id"] for a in listed] == [account["id"]]

    detail = (
        await client.get(f"{BASE}/{account['id']}", headers=auth_headers)
    ).json()
    assert detail["id"] == account["id"]
    # Fresh account: equity equals initial capital, nothing open or closed.
    assert detail["equity"] == 500_000
    assert detail["open_positions"] == []
    assert detail["closed_positions"] == []


async def test_delete_account(client, auth_headers):
    account = await create_account(client, auth_headers, name="doomed")
    resp = await client.delete(f"{BASE}/{account['id']}", headers=auth_headers)
    assert resp.status_code == 204
    listed = (await client.get(BASE, headers=auth_headers)).json()
    assert all(a["id"] != account["id"] for a in listed)


async def test_delete_unknown_404(client, auth_headers):
    resp = await client.delete(
        f"{BASE}/00000000-0000-0000-0000-000000000001", headers=auth_headers
    )
    assert resp.status_code == 404


async def test_user_isolation(client, auth_headers):
    account = await create_account(client, auth_headers)

    await client.post(
        "/api/v1/auth/register",
        json={"email": "paper-other@example.com", "password": "secret123"},
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "paper-other@example.com", "password": "secret123"},
    )
    other = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assert (await client.get(BASE, headers=other)).json() == []
    assert (
        await client.get(f"{BASE}/{account['id']}", headers=other)
    ).status_code == 404
    assert (
        await client.delete(f"{BASE}/{account['id']}", headers=other)
    ).status_code == 404


async def test_delete_blocked_while_forward_test_running(client, auth_headers):
    """An account backing a running forward test cannot be deleted."""
    override_demo_provider()
    strategy = (
        await client.post(
            "/api/v1/strategies",
            json={
                "name": "Guard SMA",
                "underlying": "NIFTY",
                "instrument": "index",
                "strategy_type": "intraday",
                "definition": {
                    "version": 1,
                    "timeframe": "5m",
                    "instrument": {"symbol": "NIFTY"},
                    "indicators": [
                        {"id": "f", "type": "SMA", "params": {"length": 5}},
                        {"id": "s", "type": "SMA", "params": {"length": 20}},
                    ],
                    "entry": {
                        "logic": "ALL",
                        "conditions": [
                            {"left": {"kind": "indicator", "ref": "f"}, "op": "CROSS_ABOVE", "right": {"kind": "indicator", "ref": "s"}}
                        ],
                    },
                    "exit": {
                        "logic": "ALL",
                        "conditions": [
                            {"left": {"kind": "indicator", "ref": "f"}, "op": "CROSS_BELOW", "right": {"kind": "indicator", "ref": "s"}}
                        ],
                    },
                    "position": {"quantity_type": "fixed", "quantity": 10, "direction": "long_only"},
                },
            },
            headers=auth_headers,
        )
    ).json()
    account = await create_account(client, auth_headers, name="guarded")

    started = await client.post(
        "/api/v1/forward-tests",
        json={"strategy_id": strategy["id"], "account_id": account["id"]},
        headers=auth_headers,
    )
    assert started.status_code == 201, started.text

    resp = await client.delete(f"{BASE}/{account['id']}", headers=auth_headers)
    assert resp.status_code == 409

    # After stopping the run the guard lifts.
    stopped = await client.post(
        f"/api/v1/forward-tests/{started.json()['id']}/stop", headers=auth_headers
    )
    assert stopped.status_code == 200
    resp = await client.delete(f"{BASE}/{account['id']}", headers=auth_headers)
    assert resp.status_code == 204
