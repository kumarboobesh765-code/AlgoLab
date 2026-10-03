"""API tests for deployment auto-activation and manual override."""

from app.execution.deploy import DeploymentRegistry

BASE = "/api/v1/execution"


async def _deploy(client, headers, mode="paper", broker="mock") -> dict:
    resp = await client.post(
        f"{BASE}/deploy",
        headers=headers,
        json={
            "strategy_id": "11111111-1111-1111-1111-111111111111",
            "broker": broker,
            "mode": mode,
            "name": "Scheduled Strategy",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_arm_marks_deployment_automatic(client, auth_headers):
    dep = await _deploy(client, auth_headers)
    resp = await client.post(
        f"{BASE}/deployments/{dep['deployment_id']}/arm",
        headers=auth_headers,
        json={"start_time": "09:15", "stop_time": "15:30"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["auto_start"] is True
    assert body["start_time"] == "09:15"
    assert body["stop_time"] == "15:30"
    assert body["schedule_summary"] != "Manual"


async def test_manual_switch_clears_auto(client, auth_headers):
    dep = await _deploy(client, auth_headers)
    await client.post(
        f"{BASE}/deployments/{dep['deployment_id']}/arm",
        headers=auth_headers,
        json={"start_time": "09:15", "stop_time": "15:30"},
    )
    resp = await client.post(
        f"{BASE}/deployments/{dep['deployment_id']}/manual", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["auto_start"] is False
    assert body["running"] is False
    assert body["schedule_summary"] == "Manual"


async def test_start_and_stop_endpoints(client, auth_headers):
    dep = await _deploy(client, auth_headers)
    started = await client.post(
        f"{BASE}/deployments/{dep['deployment_id']}/start", headers=auth_headers
    )
    assert started.status_code == 200, started.text
    assert started.json()["running"] is True

    stopped = await client.post(
        f"{BASE}/deployments/{dep['deployment_id']}/stop", headers=auth_headers
    )
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["running"] is False


async def test_deployment_list_exposes_schedule(client, auth_headers):
    dep = await _deploy(client, auth_headers)
    resp = await client.get(f"{BASE}/deployments", headers=auth_headers)
    assert resp.status_code == 200
    row = next(r for r in resp.json() if r["deployment_id"] == dep["deployment_id"])
    # Fields the UI needs to render a schedule control.
    assert {"auto_start", "start_time", "stop_time", "running", "schedule_summary"} <= set(row)


async def test_unknown_deployment_404(client, auth_headers):
    for path in ("arm", "manual", "start", "stop"):
        body = {"start_time": "09:15", "stop_time": "15:30"} if path == "arm" else None
        resp = await client.post(
            f"{BASE}/deployments/DEP-NOPE/{path}", headers=auth_headers, json=body
        )
        assert resp.status_code == 404, f"{path} -> {resp.status_code}"


async def test_arm_rejects_bad_window(client, auth_headers):
    dep = await _deploy(client, auth_headers)
    resp = await client.post(
        f"{BASE}/deployments/{dep['deployment_id']}/arm",
        headers=auth_headers,
        json={"start_time": "09:15", "stop_time": "09:15"},
    )
    assert resp.status_code == 400
    assert "differ" in resp.json()["detail"]


async def test_arm_rejects_malformed_time(client, auth_headers):
    dep = await _deploy(client, auth_headers)
    resp = await client.post(
        f"{BASE}/deployments/{dep['deployment_id']}/arm",
        headers=auth_headers,
        json={"start_time": "25:99", "stop_time": "15:30"},
    )
    assert resp.status_code == 400


async def test_arm_rejects_non_hhmm_pattern(client, auth_headers):
    """The schema pattern must reject "9:15" before it reaches the registry."""
    dep = await _deploy(client, auth_headers)
    resp = await client.post(
        f"{BASE}/deployments/{dep['deployment_id']}/arm",
        headers=auth_headers,
        json={"start_time": "9:15", "stop_time": "15:30"},
    )
    assert resp.status_code == 422


async def test_deployment_controls_require_auth(client):
    for path in ("manual", "start", "stop"):
        resp = await client.post(f"{BASE}/deployments/DEP-X/{path}")
        assert resp.status_code == 401, f"{path} -> {resp.status_code}"


def test_registry_tick_returns_only_changed_deployments():
    """Scheduler-facing contract: tick reports transitions, not the full set."""
    from datetime import datetime

    reg = DeploymentRegistry()
    armed = reg.deploy("s1", "mock", "paper", "Armed")
    reg.deploy("s2", "mock", "paper", "Manual")
    reg.arm(armed.deployment_id, "00:00", "23:59")
    monday = datetime(2026, 1, 5, 10, 0)
    assert [d.deployment_id for d in reg.tick(monday)] == [armed.deployment_id]
    assert reg.tick(monday) == []
