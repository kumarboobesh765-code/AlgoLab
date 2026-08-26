"""Tests for the zero-dependency /metrics endpoint."""

import pytest

BASE = "/api/v1"


@pytest.mark.asyncio
async def test_metrics_scrape_counts_requests(client):
    # Generate some traffic first
    await client.get(f"{BASE}/health")
    resp = await client.get(f"{BASE}/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    body = resp.text
    assert "# HELP http_requests_total" in body
    assert 'path="/health"' in body


@pytest.mark.asyncio
async def test_metrics_records_status_codes(client, auth_headers):
    await client.get(f"{BASE}/calendar/holidays?year=2025", headers=auth_headers)
    resp = await client.get(f"{BASE}/metrics")
    assert 'status="200"' in resp.text
