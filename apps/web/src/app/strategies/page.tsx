"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { api, type Strategy } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Card } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/Badge";

const BUILDERS = [
  {
    href: "/builder/visual",
    title: "Visual Builder",
    description: "Guided forms — indicators, conditions, risk. Recommended.",
  },
  {
    href: "/builder/flow",
    title: "Strategy Flow",
    description: "See the strategy as a pipeline, then edit its stages.",
  },
  {
    href: "/builder/technical",
    title: "Technical Builder",
    description: "Write the canonical definition JSON directly.",
  },
];

export default function StrategiesPage() {
  return (
    <Suspense
      fallback={<p className="py-10 text-center text-sm text-slate-400">Loading…</p>}
    >
      <StrategiesContent />
    </Suspense>
  );
}

function StrategiesContent() {
  const { user, loading: authLoading } = useAuth();
  const searchParams = useSearchParams();
  const createdName = searchParams.get("created");
  const [strategies, setStrategies] = useState<Strategy[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [showPicker, setShowPicker] = useState(false);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    api<Strategy[]>("/strategies")
      .then((s) => {
        if (!cancelled) setStrategies(s);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load strategies");
      });
    return () => {
      cancelled = true;
    };
  }, [user]);

  const loading = authLoading || (!!user && strategies === null);

  async function refresh() {
    setError(null);
    try {
      setStrategies(await api<Strategy[]>("/strategies"));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load strategies");
    }
  }

  async function handleDelete(id: string) {
    if (!window.confirm("Delete this strategy and all its versions?")) return;
    try {
      await api(`/strategies/${id}`, { method: "DELETE" });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  if (!authLoading && !user) {
    return (
      <Card>
        <div className="py-10 text-center">
          <p className="text-sm text-slate-500">Sign in to manage your strategies.</p>
          <Link
            href="/login"
            className="mt-4 inline-block rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            Sign in
          </Link>
        </div>
      </Card>
    );
  }

  const filtered = (strategies ?? []).filter((s) =>
    s.name.toLowerCase().includes(query.toLowerCase()),
  );

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <input
          type="search"
          placeholder="Search strategies…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-64 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
        />
        <div className="flex items-center gap-2">
          <button
            disabled
            title="Import ships in Phase 9"
            className="cursor-not-allowed rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-400"
          >
            Import
          </button>
          <button
            onClick={() => setShowPicker(!showPicker)}
            className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            + New Strategy
          </button>
        </div>
      </div>

      {createdName && (
        <p className="rounded-md bg-emerald-50 px-3 py-2 text-xs text-emerald-700 ring-1 ring-inset ring-emerald-200">
          ✓ “{createdName}” saved as v1. Run it through history from the Backtest page.
        </p>
      )}

      {showPicker && (
        <div className="grid gap-3 sm:grid-cols-3">
          {BUILDERS.map((b) => (
            <Link
              key={b.href}
              href={b.href}
              className="group rounded-xl border border-slate-200 bg-white p-4 transition-shadow hover:border-blue-300 hover:shadow-md"
            >
              <p className="text-sm font-semibold text-slate-800 group-hover:text-blue-700">
                {b.title}
              </p>
              <p className="mt-1 text-xs leading-relaxed text-slate-500">{b.description}</p>
            </Link>
          ))}
        </div>
      )}

      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-600 ring-1 ring-inset ring-red-200">
          {error}
        </p>
      )}

      <Card title="Strategy Library" subtitle={`${filtered.length} strategies`}>
        {loading ? (
          <p className="py-10 text-center text-sm text-slate-400">Loading…</p>
        ) : filtered.length === 0 ? (
          <div className="py-12 text-center">
            <p className="text-sm font-medium text-slate-600">No strategies yet</p>
            <p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-slate-400">
              Create your first strategy with the Visual Builder, Strategy Flow or the
              Technical Builder — all three compile to the same canonical definition.
            </p>
            <button
              onClick={() => setShowPicker(true)}
              className="mt-4 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
            >
              + New Strategy
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-left text-[13px]">
              <thead>
                <tr className="border-b border-slate-100 text-[11px] uppercase tracking-wide text-slate-400">
                  <th className="pb-2 pr-3 font-medium">Name</th>
                  <th className="pb-2 pr-3 font-medium">Ver</th>
                  <th className="pb-2 pr-3 font-medium">Market</th>
                  <th className="pb-2 pr-3 font-medium">Type</th>
                  <th className="pb-2 pr-3 font-medium">Status</th>
                  <th className="pb-2 pr-3 font-medium">Tags</th>
                  <th className="pb-2 pr-3 font-medium">Updated</th>
                  <th className="pb-2 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((s) => (
                  <tr key={s.id} className="border-b border-slate-50 last:border-0">
                    <td className="py-2.5 pr-3">
                      <p className="font-medium text-slate-800">{s.name}</p>
                      {s.description && (
                        <p className="max-w-[240px] truncate text-[11px] text-slate-400">
                          {s.description}
                        </p>
                      )}
                    </td>
                    <td className="py-2.5 pr-3 tabular-nums text-slate-500">v{s.current_version}</td>
                    <td className="py-2.5 pr-3 text-slate-600">
                      {s.exchange} · {s.underlying}
                    </td>
                    <td className="py-2.5 pr-3 capitalize text-slate-600">{s.strategy_type}</td>
                    <td className="py-2.5 pr-3">
                      <StatusBadge status={s.status} />
                    </td>
                    <td className="py-2.5 pr-3">
                      <div className="flex flex-wrap gap-1">
                        {s.tags?.slice(0, 3).map((t) => (
                          <span
                            key={t}
                            className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500"
                          >
                            {t}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="py-2.5 pr-3 text-slate-400">
                      {new Date(s.updated_at).toLocaleDateString("en-IN")}
                    </td>
                    <td className="py-2.5">
                      <div className="flex items-center gap-1.5">
                        {s.definition ? (
                          <Link
                            href={`/backtest?strategy=${s.id}`}
                            className="rounded border border-sky-200 px-1.5 py-0.5 text-[11px] text-sky-600 hover:bg-sky-50"
                          >
                            Backtest
                          </Link>
                        ) : (
                          <button
                            disabled
                            title="Add a definition first"
                            className="cursor-not-allowed rounded border border-slate-200 px-1.5 py-0.5 text-[11px] text-slate-400"
                          >
                            Backtest
                          </button>
                        )}
                        <button
                          onClick={() => handleDelete(s.id)}
                          className="rounded border border-red-200 px-1.5 py-0.5 text-[11px] text-red-500 hover:bg-red-50"
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
