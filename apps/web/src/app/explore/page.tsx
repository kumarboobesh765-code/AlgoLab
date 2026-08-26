"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, type Strategy } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useToast } from "@/components/ui/Toast";
import { Card } from "@/components/ui/Card";

interface ExploreAlgo {
  id: string;
  name: string;
  category: string;
  description: string;
  tags: string[];
  complexity: string;
  min_capital: number;
  underlying: string;
  definition: Record<string, unknown>;
}

interface ExploreResponse {
  categories: { id: string; label: string; description: string; count: number }[];
  algos: ExploreAlgo[];
  total: number;
}

const COMPLEXITY_TONE: Record<string, string> = {
  beginner: "bg-green-50 text-green-700",
  intermediate: "bg-amber-50 text-amber-700",
  advanced: "bg-red-50 text-red-700",
};

const inr = (v: number) => `₹${v.toLocaleString("en-IN")}`;

export default function ExplorePage() {
  const { user } = useAuth();
  const router = useRouter();
  const { showToast } = useToast();
  const [data, setData] = useState<ExploreResponse | null>(null);
  const [category, setCategory] = useState("all");
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [cloningId, setCloningId] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    api<ExploreResponse>("/strategies/explore")
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [user]);

  const visible = useMemo(() => {
    if (!data) return [];
    const q = query.trim().toLowerCase();
    return data.algos.filter((a) => {
      if (category !== "all" && a.category !== category) return false;
      if (!q) return true;
      return (
        a.name.toLowerCase().includes(q) ||
        a.description.toLowerCase().includes(q) ||
        a.tags.some((t) => t.toLowerCase().includes(q)) ||
        a.underlying.toLowerCase().includes(q)
      );
    });
  }, [data, category, query]);

  async function clone(algo: ExploreAlgo): Promise<Strategy | null> {
    setCloningId(algo.id);
    setError(null);
    try {
      const created = await api<Strategy>("/strategies", {
        method: "POST",
        body: JSON.stringify({
          name: algo.name,
          description: algo.description,
          underlying: algo.underlying,
          exchange: (algo.definition.instrument as { exchange?: string })?.exchange ?? "NSE",
          instrument: (algo.definition.instrument as { segment?: string })?.segment ?? "index",
          strategy_type: algo.definition.builder === "legs" ? "options" : "intraday",
          tags: [...algo.tags, `explore:${algo.id}`],
          definition: algo.definition,
        }),
      });
      showToast({ type: "success", title: "Added to your library", message: `${algo.name} is ready.` });
      return created;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Clone failed");
      showToast({ type: "error", title: "Clone failed", message: e instanceof Error ? e.message : undefined });
      return null;
    } finally {
      setCloningId(null);
    }
  }

  async function cloneAndEdit(algo: ExploreAlgo) {
    const s = await clone(algo);
    if (s) router.push(`/strategies?created=${encodeURIComponent(s.name)}`);
  }

  async function cloneAndBacktest(algo: ExploreAlgo) {
    const s = await clone(algo);
    if (s) router.push(`/backtest?strategy=${s.id}`);
  }

  const catLabel = (id: string) =>
    data?.categories.find((c) => c.id === id)?.label ?? id;

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Explore Prebuilt Algos</h2>
        <p className="mt-0.5 text-sm text-slate-500">
          Battle-tested Indian-market structures. Clone one into your library and backtest it on your own data.
        </p>
      </div>

      {/* Category chips */}
      <div className="flex flex-wrap gap-2">
        {(data?.categories ?? [{ id: "all", label: "All", count: data?.total ?? 0, description: "" }]).map((c) => (
          <button
            key={c.id}
            onClick={() => setCategory(c.id)}
            title={c.description || undefined}
            className={`rounded-full px-3 py-1.5 text-xs font-medium ring-1 ring-inset transition-colors ${
              category === c.id
                ? "bg-blue-600 text-white ring-blue-600"
                : "bg-white text-slate-600 ring-slate-200 hover:bg-slate-50 hover:text-blue-700"
            }`}
          >
            {c.label}{typeof c.count === "number" && c.id !== "all" ? ` (${c.count})` : ""}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <input
          type="search"
          placeholder="Search by name, tag or underlying…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-72 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
        />
        <span className="text-xs text-slate-400">{visible.length} algos</span>
      </div>

      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-600 ring-1 ring-inset ring-red-200">{error}</p>
      )}

      {!data && !error && <p className="py-10 text-center text-sm text-slate-400">Loading catalogue…</p>}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {visible.map((a) => (
          <div
            key={a.id}
            className="flex flex-col rounded-xl border border-slate-200 bg-white p-4 transition-shadow hover:border-blue-300 hover:shadow-md"
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="text-sm font-semibold text-slate-800">{a.name}</p>
                <p className="mt-0.5 text-[11px] uppercase tracking-wide text-slate-400">
                  {catLabel(a.category)} · {a.underlying}
                </p>
              </div>
              <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold capitalize ${COMPLEXITY_TONE[a.complexity] ?? ""}`}>
                {a.complexity}
              </span>
            </div>

            <p className="mt-2 flex-1 text-xs leading-relaxed text-slate-500">{a.description}</p>

            <div className="mt-3 flex flex-wrap gap-1">
              {a.tags.slice(0, 4).map((t) => (
                <span key={t} className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500">{t}</span>
              ))}
            </div>

            <p className="mt-3 text-[11px] text-slate-400">
              Est. capital needed: <span className="font-semibold text-slate-600">{inr(a.min_capital)}</span>
            </p>

            <div className="mt-3 flex items-center gap-2 border-t border-slate-100 pt-3">
              <button
                onClick={() => cloneAndEdit(a)}
                disabled={cloningId === a.id}
                className="flex-1 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {cloningId === a.id ? "Adding…" : "Clone to Library"}
              </button>
              <button
                onClick={() => cloneAndBacktest(a)}
                disabled={cloningId === a.id}
                className="flex-1 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:border-blue-300 hover:text-blue-700 disabled:opacity-50"
              >
                Clone &amp; Backtest
              </button>
            </div>
          </div>
        ))}
      </div>

      {data && visible.length === 0 && !error && (
        <Card>
          <p className="py-8 text-center text-sm text-slate-400">No algos match that filter.</p>
        </Card>
      )}

      <p className="text-[11px] text-slate-400">
        These are structural templates for research — not recommendations. Always backtest on your own data before trading anything.
      </p>

      <Link href="/builder/visual" className="inline-block text-xs font-medium text-blue-600 hover:underline">
        Or build your own from scratch →
      </Link>
    </div>
  );
}
