"""Tests for the AI Builder endpoint (/ai/draft-strategy) and NL parser."""

from types import SimpleNamespace

from app.services.nl_strategy import draft_definition

BASE = "/api/v1/ai"


# ---------------------------------------------------------------- parser units


def test_rsi_prompt():
    defn, notes = draft_definition("Buy NIFTY when RSI goes below 30 on 15m chart, sell above 70")
    assert defn["timeframe"] == "15m"
    assert defn["instrument"]["symbol"] == "NIFTY"
    assert defn["indicators"][0]["type"] == "RSI"
    assert defn["entry"]["conditions"][0]["op"] == "LT"
    assert defn["entry"]["conditions"][0]["right"]["value"] == 30
    assert defn["exit"]["conditions"][0]["right"]["value"] == 70


def test_rsi_custom_length_and_threshold():
    defn, _ = draft_definition("rsi(7) strategy buy below 25")
    assert defn["indicators"][0]["params"]["length"] == 7
    assert defn["entry"]["conditions"][0]["right"]["value"] == 25


def test_macd_prompt():
    defn, _ = draft_definition("macd histogram crosses above zero intraday")
    assert defn["indicators"][0]["type"] == "MACD"
    ref = defn["entry"]["conditions"][0]["left"]["ref"]
    assert ref == "macd.histogram"
    assert defn["entry"]["conditions"][0]["op"] == "CROSS_ABOVE"


def test_ma_crossover_with_lengths():
    defn, _ = draft_definition("sma crossover 20 and 50 daily")
    assert [i["type"] for i in defn["indicators"]] == ["SMA", "SMA"]
    lengths = sorted(i["params"]["length"] for i in defn["indicators"])
    assert lengths == [20, 50]
    assert defn["entry"]["conditions"][0]["op"] == "CROSS_ABOVE"


def test_defaults_when_nothing_detected():
    defn, notes = draft_definition("something that trades a lot please")
    # always produces a valid EMA crossover skeleton
    assert defn["indicators"]
    assert any("default" in n.lower() for n in notes)


def test_stoploss_target_extraction():
    defn, _ = draft_definition("ema crossover 9 and 21, stop loss 0.5%, target 1%")
    assert defn["risk"]["stop_loss_pct"] == 0.5
    assert defn["risk"]["target_pct"] == 1.0


def test_symbol_detection():
    defn, _ = draft_definition("trade banknifty supertrend")
    assert defn["instrument"]["symbol"] == "BANKNIFTY"
    assert defn["indicators"][0]["type"] == "SUPERTREND"


# ------------------------------------------------------------------- endpoint


async def test_requires_auth(client):
    assert (
        await client.post(BASE + "/draft-strategy", json={"prompt": "ema crossover"})
    ).status_code == 401


async def test_draft_valid_rules(client, auth_headers):
    resp = await client.post(
        BASE + "/draft-strategy",
        json={"prompt": "Buy NIFTY when RSI below 30 on 5m"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "rules"
    assert body["valid"] is True
    assert body["errors"] == []
    assert body["definition"]["indicators"][0]["type"] == "RSI"


async def test_draft_prompt_too_short(client, auth_headers):
    resp = await client.post(BASE + "/draft-strategy", json={"prompt": "abc"}, headers=auth_headers)
    assert resp.status_code == 422


async def test_llm_failure_falls_back_to_rules(client, auth_headers, monkeypatch):
    """Configured-but-broken LLM must degrade to the rule-based parser, not error."""
    fake = SimpleNamespace(
        AI_API_KEY="test-key",
        AI_BASE_URL="http://127.0.0.1:9",  # nothing listens here
        AI_MODEL="test-model",
    )
    monkeypatch.setattr("app.api.v1.ai.get_settings", lambda: fake)

    resp = await client.post(
        BASE + "/draft-strategy",
        json={"prompt": "ema crossover 9 and 21"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "rules"
    assert any("LLM" in w or "rule-based" in w for w in body["warnings"])
    assert body["valid"] is True


async def test_llm_success_path(client, auth_headers, monkeypatch):
    """A compliant LLM response is used verbatim (validated) with source='llm'."""

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"definition": {"version": 1, "timeframe": "5m", '
                                '"instrument": {"symbol": "NIFTY"}, '
                                '"indicators": [{"id": "e", "type": "EMA", "params": {"length": 10}}], '
                                '"entry": {"logic": "ALL", "conditions": [{"left": {"kind": "price", "price": "close"}, '
                                '"op": "GT", "right": {"kind": "indicator", "ref": "e"}}]}, '
                                '"exit": null}}'
                            )
                        }
                    }
                ]
            }

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            return FakeResponse()

    fake_settings = SimpleNamespace(
        AI_API_KEY="k", AI_BASE_URL="http://llm.local/v1", AI_MODEL="m"
    )
    monkeypatch.setattr("app.api.v1.ai.get_settings", lambda: fake_settings)
    monkeypatch.setattr("app.api.v1.ai.httpx.AsyncClient", FakeClient)

    resp = await client.post(
        BASE + "/draft-strategy",
        json={"prompt": "close above ema10"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "llm"
    assert body["valid"] is True
