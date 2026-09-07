"use client";
import { WebhookConfig } from "@/components/webhooks/WebhookConfig";

const CHARTINK_PAYLOAD_EXAMPLE = `{
  "symbol": "NIFTY",
  "signal_type": "buy",
  "price": 19500,
  "scanner_name": "Bullish momentum"
}`;

export default function ChartinkSignalsPage() {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Chartink Signals</h2>
        <p className="mt-1 text-sm text-slate-500">
          Set up a webhook to forward Chartink screener alerts to StrategyLab.
        </p>
      </div>
      <WebhookConfig
        provider="chartink"
        title="Chartink Webhooks"
        description="Receive webhooks from your Chartink scanners and alerts. Each signal fires a forward test tick on the linked strategy."
        payloadExample={CHARTINK_PAYLOAD_EXAMPLE}
        headerName="X-Chartink-Signature"
      />
    </div>
  );
}
