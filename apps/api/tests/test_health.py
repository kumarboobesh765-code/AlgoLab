async def test_health_reports_paper_mode(client):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["trading_mode"] == "paper_only"
    assert body["live_trading_available"] is False
    assert body["market_data_provider"] == "demo"
    assert body["market_data_is_demo"] is True
