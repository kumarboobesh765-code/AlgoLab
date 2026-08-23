import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  api,
  type PreviewResponse,
  type QuantCatalog,
  type Strategy,
  type ValidationResponse,
} from "@/lib/api";
import type { StrategyDefinitionV1 } from "@/lib/builders";

export interface StrategyMeta {
  name: string;
  description: string;
  strategy_type: string;
  tags: string;
}

export const EMPTY_META: StrategyMeta = {
  name: "",
  description: "",
  strategy_type: "intraday",
  tags: "",
};

export function useBuilderWorkflow() {
  const [catalog, setCatalog] = useState<QuantCatalog | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [validation, setValidation] = useState<ValidationResponse | null>(null);
  const [validating, setValidating] = useState(false);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api<QuantCatalog>("/quant/catalog")
      .then((c) => {
        if (!cancelled) {
          setCatalog(c);
          setCatalogError(null);
        }
      })
      .catch((e: Error) => {
        if (!cancelled) {
          setCatalog(null);
          setCatalogError(
            e instanceof ApiError && e.status === 401
              ? "Not authenticated — reload the page to get a new session."
              : `Indicator catalog unavailable — ${e.message}. Is the API server running?`,
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const validate = useCallback(
    async (definition: StrategyDefinitionV1): Promise<ValidationResponse> => {
      setValidating(true);
      try {
        const result = await api<ValidationResponse>("/quant/validate", {
          method: "POST",
          body: JSON.stringify(definition),
        });
        setValidation(result);
        return result;
      } finally {
        setValidating(false);
      }
    },
    [],
  );

  const runPreview = useCallback(
    async (definition: StrategyDefinitionV1): Promise<ValidationResponse | null> => {
      setPreviewError(null);
      setPreviewing(true);
      setPreview(null);
      try {
        const v = await validate(definition);
        if (!v.valid) return v;
        let p: PreviewResponse;
        try {
          p = await api<PreviewResponse>("/quant/preview?bars=500", {
            method: "POST",
            body: JSON.stringify(definition),
          });
        } catch (e) {
          // Fresh databases have no instrument master — sync once and retry so
          // "Preview signals" works out of the box instead of dead-ending on a 404.
          if (
            e instanceof ApiError &&
            e.status === 404 &&
            /unknown symbol/i.test(e.message)
          ) {
            setPreviewError("Instrument master not synced — syncing now and retrying…");
            await api<{ received: number; upserted: number }>("/data/instruments/sync", {
              method: "POST",
            });
            setPreviewError(null);
            p = await api<PreviewResponse>("/quant/preview?bars=500", {
              method: "POST",
              body: JSON.stringify(definition),
            });
          } else {
            throw e;
          }
        }
        setPreview(p);
        return v;
      } catch (e) {
        setPreviewError(
          e instanceof Error
            ? `${e.message}${/unknown symbol/i.test(e.message) ? " — open Tools → Data Manager, sync instruments and ingest history for this symbol." : ""}`
            : "Preview failed",
        );
        return null;
      } finally {
        setPreviewing(false);
      }
    },
    [validate],
  );

  const save = useCallback(
    async (
      meta: StrategyMeta,
      definition: StrategyDefinitionV1,
      editingId?: string,
    ): Promise<Strategy> => {
      setSaveError(null);
      setSaving(true);
      try {
        const v = await validate(definition);
        if (!v.valid) {
          throw new Error(`Definition has ${v.errors.length} error(s) — fix them before saving`);
        }
        const body = JSON.stringify({
          name: meta.name,
          description: meta.description || null,
          underlying: definition.instrument.symbol,
          exchange: definition.instrument.exchange,
          strategy_type: meta.strategy_type,
          tags: meta.tags
            .split(",")
            .map((t) => t.trim())
            .filter(Boolean),
          definition,
        });
        return editingId
          ? await api<Strategy>(`/strategies/${editingId}`, { method: "PUT", body })
          : await api<Strategy>("/strategies", { method: "POST", body });
      } catch (e) {
        const message = e instanceof Error ? e.message : "Save failed";
        setSaveError(message);
        throw e;
      } finally {
        setSaving(false);
      }
    },
    [validate],
  );

  return {
    catalog,
    catalogError,
    validation,
    validating,
    validate,
    preview,
    previewing,
    previewError,
    runPreview,
    saving,
    saveError,
    save,
  };
}
