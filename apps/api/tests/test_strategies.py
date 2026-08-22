BASE = "/api/v1/strategies"


async def test_create_list_get_update_delete(client, auth_headers):
    payload = {
        "name": "NIFTY Intraday Short Straddle",
        "description": "Demo sample strategy",
        "underlying": "NIFTY",
        "strategy_type": "intraday",
        "tags": ["straddle", "nifty"],
    }
    resp = await client.post(BASE, json=payload, headers=auth_headers)
    assert resp.status_code == 201
    strategy = resp.json()
    assert strategy["status"] == "draft"
    assert strategy["current_version"] == 1
    sid = strategy["id"]

    resp = await client.get(BASE, headers=auth_headers)
    assert len(resp.json()) == 1

    resp = await client.get(f"{BASE}/{sid}", headers=auth_headers)
    assert resp.status_code == 200

    resp = await client.put(
        f"{BASE}/{sid}",
        json={"description": "Updated", "definition": _valid_definition()},
        headers=auth_headers,
    )
    body = resp.json()
    assert body["description"] == "Updated"
    # definition change bumps the version automatically (spec #55)
    assert body["current_version"] == 2

    resp = await client.delete(f"{BASE}/{sid}", headers=auth_headers)
    assert resp.status_code == 204
    resp = await client.get(BASE, headers=auth_headers)
    assert resp.json() == []


def _valid_definition() -> dict:
    return {
        "version": 1,
        "timeframe": "5m",
        "instrument": {"symbol": "NIFTY"},
        "indicators": [{"id": "ema_fast", "type": "EMA", "params": {"length": 9}}],
        "entry": {
            "logic": "ALL",
            "conditions": [
                {
                    "left": {"kind": "indicator", "ref": "ema_fast"},
                    "op": "CROSS_ABOVE",
                    "right": {"kind": "price", "price": "close"},
                }
            ],
        },
    }


async def test_invalid_definition_rejected(client, auth_headers):
    bad = _valid_definition()
    bad["entry"]["conditions"][0]["op"] = "MAGICAL"
    resp = await client.post(
        BASE,
        json={"name": "Broken", "definition": bad},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["errors"]

    # create without definition is still allowed (draft strategies)
    resp = await client.post(BASE, json={"name": "Draft only"}, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json()["definition"] is None


async def test_versions_and_clone(client, auth_headers):
    resp = await client.post(BASE, json={"name": "Strat A"}, headers=auth_headers)
    sid = resp.json()["id"]

    resp = await client.post(f"{BASE}/{sid}/versions", json={"changelog": "tightened SL"}, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json()["version_number"] == 2

    resp = await client.get(f"{BASE}/{sid}/versions", headers=auth_headers)
    versions = resp.json()
    assert [v["version_number"] for v in versions] == [2, 1]

    resp = await client.post(f"{BASE}/{sid}/clone", headers=auth_headers)
    clone = resp.json()
    assert clone["name"] == "Strat A (Copy)"
    assert clone["id"] != sid


async def test_user_isolation(client):
    """User B must never see or mutate User A's strategies."""
    for email in ("a@example.com", "b@example.com"):
        await client.post("/api/v1/auth/register", json={"email": email, "password": "secret123"})
    token_a = (
        await client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "secret123"})
    ).json()["access_token"]
    token_b = (
        await client.post("/api/v1/auth/login", json={"email": "b@example.com", "password": "secret123"})
    ).json()["access_token"]

    resp = await client.post(
        BASE, json={"name": "A private"}, headers={"Authorization": f"Bearer {token_a}"}
    )
    sid = resp.json()["id"]

    resp = await client.get(BASE, headers={"Authorization": f"Bearer {token_b}"})
    assert resp.json() == []

    resp = await client.get(f"{BASE}/{sid}", headers={"Authorization": f"Bearer {token_b}"})
    assert resp.status_code == 404

    resp = await client.delete(f"{BASE}/{sid}", headers={"Authorization": f"Bearer {token_b}"})
    assert resp.status_code == 404
