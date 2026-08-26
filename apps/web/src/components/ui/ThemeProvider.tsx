"use client";

import { useSyncExternalStore } from "react";

export type Theme = "light" | "dark";

const KEY = "sl_theme";

type Listener = () => void;
let listeners: Listener[] = [];

export const themeStore = {
  subscribe(cb: Listener): () => void {
    listeners.push(cb);
    return () => {
      listeners = listeners.filter((l) => l !== cb);
    };
  },
  get(): Theme {
    if (typeof window === "undefined") return "light";
    try {
      const saved = window.localStorage.getItem(KEY);
      if (saved === "light" || saved === "dark") return saved;
      return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    } catch {
      return "light";
    }
  },
  set(theme: Theme): void {
    try {
      window.localStorage.setItem(KEY, theme);
      document.documentElement.classList.toggle("dark", theme === "dark");
    } catch {
      /* private mode */
    }
    listeners.forEach((l) => l());
  },
  toggle(): void {
    themeStore.set(themeStore.get() === "light" ? "dark" : "light");
  },
};

const serverSnapshot = (): Theme => "light";

export function useTheme() {
  const theme = useSyncExternalStore(themeStore.subscribe, themeStore.get, serverSnapshot);
  return { theme, toggleTheme: themeStore.toggle, setTheme: themeStore.set };
}
