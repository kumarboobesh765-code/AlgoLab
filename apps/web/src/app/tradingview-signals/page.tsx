"use client";
import { WebhookConfig } from "@/components/webhooks/WebhookConfig";

const TV_PAYLOAD_EXAMPLE = `{
  "ticker": "NIFTY",
  "action": "buy",
  "price": 19500,
  "quantity": 75,
  "comment": "EMA crossover"
}`;

export default function TradingViewSignalsPage() {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">TradingView Signals</h2>
        <p className="mt-1 text-sm text-slate-500">
          Set up a webhook to forward TradingView strategy/indicator alerts to StrategyLab.
        </p>
      </div>
      <WebhookConfig
        provider="tradingview"
        title="TradingView Webhooks"
        description="Receive webhooks from your TradingView alerts, strategies, and Pinescript studies. Each alert fires a forward test tick on the linked strategy."
        payloadExample={TV_PAYLOAD_EXAMPLE}
        headerName="X-TVSignature"
      />
    </div>
  );
}
