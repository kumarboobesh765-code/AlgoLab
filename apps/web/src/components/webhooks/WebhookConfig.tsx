"use client";

import { useState, useEffect } from "react";
import { useWebhooks } from "@/lib/hooks/useWebhooks";
import { api } from "@/lib/api";
import type { WebhookEndpointOut, WebhookDeliveryLog, Strategy } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";

interface WebhookConfigProps {
  provider: "tradingview" | "chartink";
  title: string;
  description: string;
  payloadExample: string;
  headerName?: string;
}

function copyToClipboard(text: string): Promise<void> {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    return navigator.clipboard.writeText(text).then(() => {});
  }
  window.prompt("Copy to clipboard:", text);
  return Promise.resolve();
}

function LogsModal({
  endpointId,
  endpointName,
  onClose,
}: {
  endpointId: string;
  endpointName: string;
  onClose: () => void;
}) {
  const [logs, setLogs] = useState<WebhookDeliveryLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<WebhookDeliveryLog[]>(`/webhooks/${endpointId}/logs`)
      .then(setLogs)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load logs"))
      .finally(() => setLoading(false));
  }, [endpointId]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-2xl rounded-2xl border border-slate-200 bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <div>
            <h3 className="text-base font-semibold text-slate-900">Delivery Logs</h3>
            <p className="mt-0.5 text-sm text-slate-500">{endpointName}</p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="max-h-96 overflow-y-auto p-5">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <span className="h-5 w-5 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
            </div>
          ) : error ? (
            <p className="text-sm text-red-600">{error}</p>
          ) : logs.length === 0 ? (
            <p className="text-sm text-slate-500">No delivery logs yet.</p>
          ) : (
            <div className="space-y-2">
              {logs.map((log) => (
                <div
                  key={log.id}
                  className="rounded-lg border border-slate-100 bg-slate-50/50 p-3"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-slate-500">
                        {new Date(log.received_at).toLocaleString()}
                      </span>
                      {log.action && (
                        <Badge tone={log.action === "buy" ? "green" : log.action === "sell" ? "red" : "slate"}>
                          {log.action}
                        </Badge>
                      )}
                    </div>
                    <Badge
                      tone={
                        log.status === "success" ? "green" : log.status === "error" ? "red" : "amber"
                      }
                    >
                      {log.status}
                    </Badge>
                  </div>
                  {log.response && (
                    <p className="mt-1.5 text-xs text-slate-600">{log.response}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function SecretModal({
  webhookUrl,
  secret,
  onClose,
}: {
  webhookUrl: string;
  secret: string;
  onClose: () => void;
}) {
  const [copiedUrl, setCopiedUrl] = useState(false);
  const [copiedSecret, setCopiedSecret] = useState(false);

  const handleCopyUrl = async () => {
    await copyToClipboard(webhookUrl);
    setCopiedUrl(true);
    setTimeout(() => setCopiedUrl(false), 2000);
  };

  const handleCopySecret = async () => {
    await copyToClipboard(secret);
    setCopiedSecret(true);
    setTimeout(() => setCopiedSecret(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white shadow-xl">
        <div className="border-b border-slate-100 px-5 py-4">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-emerald-100">
              <svg className="h-4 w-4 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </span>
            <h3 className="text-base font-semibold text-slate-900">Webhook Created</h3>
          </div>
        </div>
        <div className="p-5">
          <p className="mb-4 text-sm text-slate-600">
            Copy your webhook URL and secret. The secret will not be shown again.
          </p>

          <div className="mb-3">
            <label className="mb-1.5 block text-xs font-medium text-slate-500">Webhook URL</label>
            <div className="flex items-center gap-2">
              <input
                readOnly
                value={webhookUrl}
                className="flex-1 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700"
              />
              <button
                onClick={handleCopyUrl}
                className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50"
              >
                {copiedUrl ? "Copied!" : "Copy"}
              </button>
            </div>
          </div>

          <div className="mb-5">
            <label className="mb-1.5 block text-xs font-medium text-red-500">
              Secret (shown only once)
            </label>
            <div className="flex items-center gap-2">
              <input
                readOnly
                value={secret}
                className="flex-1 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-sm text-slate-700 font-mono"
              />
              <button
                onClick={handleCopySecret}
                className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs font-medium text-red-700 hover:bg-red-100"
              >
                {copiedSecret ? "Copied!" : "Copy"}
              </button>
            </div>
          </div>

          <button
            onClick={onClose}
            className="w-full rounded-lg bg-blue-600 py-2.5 text-sm font-semibold text-white hover:bg-blue-700"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}

function DeleteConfirmModal({
  endpointName,
  onConfirm,
  onCancel,
}: {
  endpointName: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white shadow-xl">
        <div className="p-5">
          <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-full bg-red-100">
            <svg className="h-5 w-5 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h3 className="text-base font-semibold text-slate-900">Delete endpoint?</h3>
          <p className="mt-2 text-sm text-slate-500">
            Are you sure you want to delete <strong>{endpointName}</strong>? This action cannot be undone.
          </p>
          <div className="mt-4 flex gap-3">
            <button
              onClick={onCancel}
              className="flex-1 rounded-lg border border-slate-200 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Cancel
            </button>
            <button
              onClick={onConfirm}
              className="flex-1 rounded-lg bg-red-600 py-2.5 text-sm font-semibold text-white hover:bg-red-700"
            >
              Delete
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function EndpointCard({
  endpoint,
  onToggle,
  onDelete,
  onViewLogs,
}: {
  endpoint: WebhookEndpointOut;
  onToggle: (active: boolean) => void;
  onDelete: () => void;
  onViewLogs: () => void;
}) {
  const [recentLogs, setRecentLogs] = useState<WebhookDeliveryLog[]>([]);

  useEffect(() => {
    api<WebhookDeliveryLog[]>(`/webhooks/${endpoint.id}/logs`)
      .then((logs) => setRecentLogs(logs.slice(0, 3)))
      .catch(() => {});
  }, [endpoint.id]);

  return (
    <div className="rounded-xl border border-slate-200 bg-white">
      <div className="flex items-start justify-between gap-4 p-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h4 className="font-medium text-slate-900 truncate">{endpoint.name}</h4>
            <Badge tone={endpoint.active ? "green" : "slate"}>
              {endpoint.active ? "Active" : "Inactive"}
            </Badge>
          </div>
          <p className="mt-1.5 truncate text-xs font-mono text-slate-500">
            /{endpoint.slug}
          </p>
          {endpoint.strategy_id && (
            <p className="mt-1 text-xs text-slate-400">Linked to strategy</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <label className="relative inline-flex cursor-pointer items-center">
            <input
              type="checkbox"
              checked={endpoint.active}
              onChange={(e) => onToggle(e.target.checked)}
              className="peer sr-only"
            />
            <div className="peer-focus:ring-blue-300 h-5 w-9 rounded-full bg-slate-200 transition-colors peer-checked:bg-blue-600"></div>
            <div className="pointer-events-none absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-white transition-transform peer-checked:translate-x-4"></div>
          </label>
          <button
            onClick={onViewLogs}
            className="rounded-lg px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100"
          >
            Logs
          </button>
          <button
            onClick={onDelete}
            className="rounded-lg p-1.5 text-red-500 hover:bg-red-50"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
          </button>
        </div>
      </div>
      {recentLogs.length > 0 && (
        <div className="border-t border-slate-100 bg-slate-50/50 px-4 py-2.5">
          <p className="mb-2 text-[10px] font-medium uppercase tracking-wider text-slate-400">Recent</p>
          <div className="space-y-1">
            {recentLogs.map((log) => (
              <div key={log.id} className="flex items-center gap-2 text-xs">
                <span className="text-slate-400">
                  {new Date(log.received_at).toLocaleDateString()}
                </span>
                {log.action && (
                  <span className="text-slate-600">{log.action}</span>
                )}
                <span
                  className={`${
                    log.status === "success"
                      ? "text-emerald-600"
                      : log.status === "error"
                      ? "text-red-600"
                      : "text-amber-600"
                  }`}
                >
                  {log.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function WebhookConfig({
  provider,
  title,
  description,
  payloadExample,
  headerName,
}: WebhookConfigProps) {
  const { endpoints, loading, error, createEndpoint, updateEndpoint, deleteEndpoint } = useWebhooks(provider);

  const [name, setName] = useState("");
  const [strategyId, setStrategyId] = useState<string>("");
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [createdEndpoint, setCreatedEndpoint] = useState<{ url: string; secret: string } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<WebhookEndpointOut | null>(null);
  const [logsTarget, setLogsTarget] = useState<WebhookEndpointOut | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);

  useEffect(() => {
    api<Strategy[]>("/strategies")
      .then(setStrategies)
      .catch(() => {});
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    setCreating(true);
    setCreateError(null);
    try {
      const created = await createEndpoint({
        name: name.trim(),
        strategy_id: strategyId || null,
      });
      setCreatedEndpoint({
        url: created.webhook_url,
        secret: created.secret,
      });
      setName("");
      setStrategyId("");
      setShowCreateForm(false);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Failed to create endpoint");
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteEndpoint(deleteTarget.id);
      setDeleteTarget(null);
    } catch (err) {
      console.error("Failed to delete:", err);
    }
  };

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-slate-200 bg-white">
        <div className="border-b border-slate-100 px-5 py-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h3 className="text-base font-semibold text-slate-900">{title}</h3>
              <p className="mt-1 text-sm text-slate-500">{description}</p>
            </div>
            <button
              onClick={() => setShowCreateForm(!showCreateForm)}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
            >
              + New Endpoint
            </button>
          </div>
        </div>

        {showCreateForm && (
          <form onSubmit={handleCreate} className="border-b border-slate-100 bg-slate-50/50 px-5 py-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label className="mb-1.5 block text-xs font-medium text-slate-700">Name *</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. TV Alert — EMA Cross"
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  required
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-medium text-slate-700">
                  Link to Strategy (optional)
                </label>
                <select
                  value={strategyId}
                  onChange={(e) => setStrategyId(e.target.value)}
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                >
                  <option value="">None</option>
                  {strategies.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            {createError && <p className="mt-2 text-sm text-red-600">{createError}</p>}
            <div className="mt-4 flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setShowCreateForm(false)}
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={creating || !name.trim()}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {creating ? (
                  <span className="flex items-center gap-2">
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                    Creating...
                  </span>
                ) : (
                  "Generate"
                )}
              </button>
            </div>
          </form>
        )}

        <div className="p-5">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <span className="h-5 w-5 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
            </div>
          ) : error ? (
            <p className="text-sm text-red-600">{error}</p>
          ) : endpoints.length === 0 ? (
            <div className="py-8 text-center">
              <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-slate-100">
                <svg className="h-6 w-6 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                </svg>
              </div>
              <p className="text-sm font-medium text-slate-700">No endpoints yet</p>
              <p className="mt-1 text-xs text-slate-500">Create your first webhook endpoint above.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {endpoints.map((endpoint) => (
                <EndpointCard
                  key={endpoint.id}
                  endpoint={endpoint}
                  onToggle={(active) => updateEndpoint(endpoint.id, { active })}
                  onDelete={() => setDeleteTarget(endpoint)}
                  onViewLogs={() => setLogsTarget(endpoint)}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white">
        <div className="border-b border-slate-100 px-5 py-4">
          <h3 className="text-sm font-semibold text-slate-900">Setup Instructions</h3>
        </div>
        <div className="p-5">
          <div className="space-y-4">
            <div>
              <p className="mb-2 text-xs font-medium uppercase tracking-wider text-slate-400">1. Payload format</p>
              <pre className="overflow-x-auto rounded-lg bg-slate-900 px-4 py-3 text-xs text-slate-100">
                {payloadExample}
              </pre>
            </div>
            {headerName && (
              <div>
                <p className="mb-2 text-xs font-medium uppercase tracking-wider text-slate-400">2. Required header</p>
                <div className="flex items-center gap-2">
                  <code className="rounded bg-slate-100 px-2 py-1 text-xs text-slate-700">{headerName}</code>
                  <span className="text-xs text-slate-500">your-signature-here</span>
                </div>
              </div>
            )}
            <div>
              <p className="mb-2 text-xs font-medium uppercase tracking-wider text-slate-400">
                {headerName ? "3" : "2"}. Copy the URL
              </p>
              <p className="text-xs text-slate-500">
                Add the webhook URL from your endpoint above to TradingView or Chartink alert settings.
              </p>
            </div>
          </div>
        </div>
      </div>

      {createdEndpoint && (
        <SecretModal
          webhookUrl={createdEndpoint.url}
          secret={createdEndpoint.secret}
          onClose={() => setCreatedEndpoint(null)}
        />
      )}

      {deleteTarget && (
        <DeleteConfirmModal
          endpointName={deleteTarget.name}
          onConfirm={handleDelete}
          onCancel={() => setDeleteTarget(null)}
        />
      )}

      {logsTarget && (
        <LogsModal
          endpointId={logsTarget.id}
          endpointName={logsTarget.name}
          onClose={() => setLogsTarget(null)}
        />
      )}
    </div>
  );
}
