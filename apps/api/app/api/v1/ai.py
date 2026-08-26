"""AI-assisted strategy drafting.

POST /ai/draft-strategy turns a plain-English prompt into a canonical
definition v1. When AI_API_KEY is configured an OpenAI-compatible chat
completion is attempted first; on any failure (or with no key) the built-in
deterministic rule-based parser drafts the definition instead.
"""

import json
import logging

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.deps import CurrentUser
from app.quant.schema import validate_definition
from app.services.nl_strategy import draft_definition

logger = logging.getLogger("strategylab.ai")

router = APIRouter(prefix="/ai", tags=["ai"])


class DraftRequest(BaseModel):
    prompt: str = Field(min_length=4, max_length=2000)


class DraftResponse(BaseModel):
    definition: dict
    source: str  # "llm" | "rules"
    valid: bool
    warnings: list[str]
    errors: list[str]
    compliance: str = (
        "White-box draft: the full rule set is disclosed and replicable in the "
        "definition above. Under SEBI's retail algo framework (CIR/2025/0000013), "
        "white-box strategies can be registered with an exchange via your broker "
        "without a Research Analyst license. Keep the logic transparent if you "
        "deploy this to other users."
    )


_LLM_SYSTEM_PROMPT = """You convert trading-strategy descriptions into a strict JSON "strategy definition".

Output ONLY JSON, no prose. Shape:
{
  "version": 1,
  "timeframe": "1m|5m|15m|30m|1h|1d",
  "instrument": {"symbol": "NIFTY"},
  "variables": [],
  "indicators": [{"id": "short_id", "type": "SMA|EMA|WMA|RSI|MACD|BBANDS|ATR|SUPERTREND|STOCH|ADX|VWAP|ROC", "params": {...}}],
  "entry": {"logic": "ALL", "conditions": [{"left": <operand>, "op": "GT|GTE|LT|LTE|CROSS_ABOVE|CROSS_BELOW", "right": <operand>}]},
  "exit": null | {"logic": "ALL", "conditions": [...]},
  "risk": {"stop_loss_pct": number|null, "target_pct": number|null, "trailing_sl_pct": number|null},
  "position": {"direction": "long_only|short_only|both", "quantity_type": "fixed|capital_pct", "quantity": number>0, "capital_pct": number|null}
}
Operands:
- price: {"kind": "price", "price": "close|open|high|low|volume"}
- constant: {"kind": "constant", "value": number}
- variable: {"kind": "variable", "name": "..."}   (must exist in variables)
- indicator: {"kind": "indicator", "ref": "<id>.<output>"} — output is required when the indicator has several outputs:
  MACD outputs macd/signal/histogram; BBANDS upper/middle/lower; SUPERTREND supertrend/direction;
  STOCH k/d; ADX adx/plus_di/minus_di. Single-output indicators may use just "<id>".
Rules: entry.conditions must have >= 1 item; ids unique; timeframe must match the user's intent (default 5m);
symbol defaults to NIFTY."""


async def _llm_draft(prompt: str) -> dict | None:
    """Ask an OpenAI-compatible API for a definition. Returns None on any failure."""
    settings = get_settings()
    if not settings.AI_API_KEY:
        return None
    try:
        base = settings.AI_BASE_URL.rstrip("/")
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {settings.AI_API_KEY}"},
                json={
                    "model": settings.AI_MODEL,
                    "temperature": 0,
                    "messages": [
                        {"role": "system", "content": _LLM_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            resp.raise_for_status()
            content: str = resp.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.strip("`")
            if content.lower().startswith("json"):
                content = content[4:]
        data = json.loads(content)
        return data.get("definition", data)
    except Exception as exc:  # noqa: BLE001 - any LLM failure falls back to rules
        logger.warning("LLM draft failed (%s); falling back to rule-based parser", exc)
        return None


@router.post("/draft-strategy", response_model=DraftResponse)
async def draft_strategy(payload: DraftRequest, user: CurrentUser) -> DraftResponse:
    warnings: list[str] = []
    definition = await _llm_draft(payload.prompt)
    if definition is not None:
        source = "llm"
    else:
        source = "rules"
        if get_settings().AI_API_KEY:
            warnings.append("LLM call failed — used the built-in rule-based parser.")
        definition, notes = draft_definition(payload.prompt)
        warnings.extend(notes)

    errors, schema_warnings = validate_definition(definition)
    return DraftResponse(
        definition=definition,
        source=source,
        valid=not errors,
        errors=errors,
        warnings=[*warnings, *schema_warnings],
    )
