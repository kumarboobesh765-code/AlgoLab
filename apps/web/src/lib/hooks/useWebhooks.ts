"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import type {
  WebhookEndpointOut,
  WebhookEndpointCreatedOut,
  WebhookDeliveryLog,
  WebhookProvider,
  WebhookEndpointCreate,
  WebhookEndpointUpdate,
} from "@/lib/api";

export function useWebhooks(provider: WebhookProvider) {
  const [endpoints, setEndpoints] = useState<WebhookEndpointOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const all = await api<WebhookEndpointOut[]>("/webhooks");
      setEndpoints(all.filter((e) => e.provider === provider));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load endpoints");
    } finally {
      setLoading(false);
    }
  }, [provider]);

  useEffect(() => {
    // Initial load: setState happens inside async .then() callbacks in refetch()
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refetch();
  }, [refetch]);

  const createEndpoint = async (data: Omit<WebhookEndpointCreate, "provider">): Promise<WebhookEndpointCreatedOut> => {
    const created = await api<WebhookEndpointCreatedOut>("/webhooks", {
      method: "POST",
      body: JSON.stringify({ ...data, provider }),
    });
    setEndpoints((prev) => [...prev, created]);
    return created;
  };

  const updateEndpoint = async (id: string, data: WebhookEndpointUpdate): Promise<void> => {
    const updated = await api<WebhookEndpointOut>(`/webhooks/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
    setEndpoints((prev) => prev.map((e) => (e.id === id ? updated : e)));
  };

  const deleteEndpoint = async (id: string): Promise<void> => {
    await api<void>(`/webhooks/${id}`, { method: "DELETE" });
    setEndpoints((prev) => prev.filter((e) => e.id !== id));
  };

  const fetchLogs = async (endpointId: string): Promise<WebhookDeliveryLog[]> => {
    return api<WebhookDeliveryLog[]>(`/webhooks/${endpointId}/logs`);
  };

  return {
    endpoints,
    loading,
    error,
    createEndpoint,
    updateEndpoint,
    deleteEndpoint,
    fetchLogs,
    refetch,
  };
}
