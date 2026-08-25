"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { Strategy, StrategyTemplate } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";

export default function StrategyLibraryPage() {
  const auth = useAuth();
  const [templates, setTemplates] = useState<StrategyTemplate[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState<string | null>(null);
  const [created, setCreated] = useState<Record<string, Strategy>>({});

  useEffect(() => {
    if (!auth.user) return;
    api<StrategyTemplate[]>("/strategies/templates")
      .then((t) => {
        setTemplates(t);
      })
      .catch((e: Error) => {
        setError(e.message);
        setTemplates([]);
      });
  }, [auth.user]);

  function createFromTemplate(t: StrategyTemplate) {
    if (creating) return;
    setCreating(t.name);
    setError(null);
    const symbol =
      (t.definition as { instrument?: { symbol?: string } }).instrument?.symbol ?? "NIFTY";
    api<Strategy>("/strategies", {
      method: "POST",
      body: JSON.stringify({
        name: t.name,
        description: t.description,
        underlying: symbol,
        instrument: "index",
        strategy_type: "intraday",
        tags: t.tags,
        definition: t.definition,
      }),
    })
      .then((s) => {
        setCreated((prev) => ({ ...prev, [t.name]: s }));
        setCreating(null);
      })
      .catch((e: Error) => {
        setError(e.message);
        setCreating(null);
      });
  }

  if (!auth.user) {
    return <p className="text-sm text-slate-500">Connecting to the API…</p>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Strategy Library</h2>
        <p className="text-sm text-slate-500">
          Built-in, battle-tested starting points. Create one and it lands on your Strategies page
          ready to edit or backtest.
        </p>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {templates === null ? (
        <p className="text-sm text-slate-500">Loading templates…</p>
      ) : templates.length === 0 ? (
        <Card>
          <p className="py-8 text-center text-sm text-slate-400">No templates available yet.</p>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {templates.map((t) => {
            const saved = created[t.name];
            return (
              <div
                key={t.name}
                className="flex flex-col rounded-xl border border-slate-200 p-4 transition hover:border-indigo-300"
              >
                <div className="flex items-start justify-between gap-2">
                  <h3 className="text-sm font-semibold text-slate-900">{t.name}</h3>
                </div>
                <p className="mt-1 flex-1 text-xs leading-relaxed text-slate-500">
                  {t.description}
                </p>
                <div className="mt-3 flex flex-wrap items-center gap-1.5">
                  {(t.tags ?? []).map((tag) => (
                    <Badge key={tag} tone="slate">
                      {tag}
                    </Badge>
                  ))}
                  <Badge tone="blue">
                    {(t.definition as { timeframe?: string }).timeframe ?? "—"}
                  </Badge>
                </div>
                <div className="mt-3 flex items-center justify-between border-t border-slate-100 pt-3">
                  {saved ? (
                    <span className="flex items-center gap-2 text-xs text-slate-600">
                      Created ✓
                      <Link
                        href={`/backtest?strategy=${saved.id}`}
                        className="font-medium text-indigo-600 hover:underline"
                      >
                        Backtest →
                      </Link>
                    </span>
                  ) : (
                    <>
                      <button
                        onClick={() => createFromTemplate(t)}
                        disabled={creating !== null}
                        className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                      >
                        {creating === t.name ? "Creating…" : "Create strategy"}
                      </button>
                      <Link
                        href="/builder/technical"
                        className="text-xs font-medium text-slate-400 hover:text-slate-600"
                      >
                        View JSON →
                      </Link>
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
