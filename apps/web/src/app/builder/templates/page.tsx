"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Strategy } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  TEMPLATE_HANDOFF_KEY,
  TEMPLATE_HANDOFF_NAME,
  type StrategyDefinitionV1,
} from "@/lib/builders";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";

interface Template {
  name: string;
  description: string;
  tags: string[];
  definition: StrategyDefinitionV1;
}

export default function TemplatesPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [templates, setTemplates] = useState<Template[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [creating, setCreating] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    api<Template[]>("/strategies/templates")
      .then((t) => setTemplates(t))
      .catch((e: Error) => setError(e.message));
  }, [user]);

  function openInTechnical(t: Template) {
    try {
      sessionStorage.setItem(TEMPLATE_HANDOFF_KEY, JSON.stringify(t.definition, null, 2));
      sessionStorage.setItem(TEMPLATE_HANDOFF_NAME, t.name);
      router.push("/builder/technical");
    } catch {
      setError("Could not open the template in the Technical Builder.");
    }
  }

  async function createStrategy(t: Template) {
    setError(null);
    setNotice(null);
    setCreating(t.name);
    try {
      const created = await api<Strategy>("/strategies", {
        method: "POST",
        body: JSON.stringify({
          name: `${t.name} (${new Date().toLocaleDateString("en-IN")})`,
          description: t.description,
          underlying: t.definition.instrument?.symbol ?? "NIFTY",
          exchange: t.definition.instrument?.exchange ?? "NSE",
          tags: t.tags ?? [],
          definition: t.definition,
        }),
      });
      router.push(`/strategies?created=${encodeURIComponent(created.name)}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create strategy from template");
      setCreating(null);
    }
  }

  if (!authLoading && !user) {
    return <p className="text-sm text-slate-500">Connecting to the API…</p>;
  }
  if (error && templates === null)
    return <p className="text-sm text-red-600">{error}</p>;
  if (templates === null)
    return <p className="text-sm text-slate-500">Loading templates…</p>;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Strategy Templates</h2>
        <p className="text-sm text-slate-500">
          Start from proven structures. Open one in the Technical Builder to tweak it, or create a
          strategy directly.
        </p>
      </div>

      {notice && <p className="text-sm text-emerald-600">{notice}</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {templates.map((t) => (
          <Card key={t.name} title={t.name}>
            <div className="flex h-full flex-col justify-between gap-4">
              <div className="space-y-3">
                <p className="text-xs leading-relaxed text-slate-500">{t.description}</p>
                <div className="flex flex-wrap gap-1">
                  <Badge tone="blue">{t.definition.timeframe}</Badge>
                  {(t.definition.instrument?.symbol ?? "NIFTY") !== "NIFTY" && (
                    <Badge tone="slate">{t.definition.instrument.symbol}</Badge>
                  )}
                  {t.tags.map((tag) => (
                    <span
                      key={tag}
                      className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
                <details className="text-xs">
                  <summary className="cursor-pointer text-indigo-600 hover:underline">
                    Definition ({t.definition.indicators.length} indicator(s),{" "}
                    {countConditions(t.definition.entry)} entry / {countConditions(t.definition.exit)} exit
                    condition(s))
                  </summary>
                  <pre className="mt-2 max-h-64 overflow-auto rounded-lg bg-slate-50 p-3 text-[10px] leading-relaxed text-slate-600">
                    {JSON.stringify(t.definition, null, 2)}
                  </pre>
                </details>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => openInTechnical(t)}
                  className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
                >
                  Open in Technical Builder
                </button>
                <button
                  onClick={() => createStrategy(t)}
                  disabled={creating !== null}
                  className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  {creating === t.name ? "Creating…" : "Create strategy"}
                </button>
              </div>
            </div>
          </Card>
        ))}
      </div>

      {templates.length === 0 && (
        <Card>
          <p className="py-8 text-center text-sm text-slate-400">No templates available.</p>
        </Card>
      )}
    </div>
  );
}

function countConditions(group: StrategyDefinitionV1["exit"]): number {
  if (!group) return 0;
  return group.conditions.reduce<number>(
    (n, c) => n + ("conditions" in c ? countConditions(c) : 1),
    0,
  );
}
