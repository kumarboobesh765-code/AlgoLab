import { useSyncExternalStore } from "react";

export interface AppSettings {
  defaultCapital: number;
  costsPct: number;
  timeframe: string;
}

const STORAGE_KEY = "strategylab-settings";

export const DEFAULT_SETTINGS: AppSettings = {
  defaultCapital: 1_000_000,
  costsPct: 0.03,
  timeframe: "5m",
};

function parse(raw: string | null): AppSettings {
  if (!raw) return DEFAULT_SETTINGS;
  try {
    return { ...DEFAULT_SETTINGS, ...(JSON.parse(raw) as Partial<AppSettings>) };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

/** SSR-safe read of user settings (falls back to defaults on server/parse errors). */
export function loadSettings(): AppSettings {
  if (typeof window === "undefined") return DEFAULT_SETTINGS;
  return parse(window.localStorage.getItem(STORAGE_KEY));
}

export function saveSettings(settings: AppSettings): void {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
}

export function clearSettings(): void {
  window.localStorage.removeItem(STORAGE_KEY);
}

// ---- reactive store so open pages pick up changes instantly ----

const listeners = new Set<() => void>();
let cachedRaw: string | null | undefined;
let cachedValue: AppSettings = DEFAULT_SETTINGS;

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function getSnapshot(): AppSettings {
  if (typeof window === "undefined") return DEFAULT_SETTINGS;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (raw !== cachedRaw) {
    cachedRaw = raw;
    cachedValue = parse(raw);
  }
  return cachedValue;
}

function getServerSnapshot(): AppSettings {
  return DEFAULT_SETTINGS;
}

export function useAppSettings(): AppSettings {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

/** Persist settings and notify every subscribed component. */
export function updateSettings(settings: AppSettings): void {
  saveSettings(settings);
  cachedRaw = JSON.stringify(settings);
  cachedValue = settings;
  listeners.forEach((l) => l());
}

/** Reset to defaults and notify every subscribed component. */
export function resetSettings(): void {
  clearSettings();
  cachedRaw = null;
  cachedValue = DEFAULT_SETTINGS;
  listeners.forEach((l) => l());
}
