"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api, getToken, setToken, type User } from "@/lib/api";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  /** true when the API is unreachable (guest/bootstrap failed) */
  offline: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName?: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function bootstrap() {
      // Single-user deployments report auth_enabled=false: silently obtain a
      // guest token so the app works without any login screen.
      try {
        const health = await api<{ auth_enabled?: boolean }>("/health");
        if (!cancelled) setOffline(false);
        if (health.auth_enabled === false) {
          const tok = await api<{ access_token: string }>("/auth/guest", { method: "POST" });
          setToken(tok.access_token);
          const me = await api<User>("/auth/me");
          if (!cancelled) {
            setUser(me);
            setLoading(false);
          }
          return;
        }
      } catch {
        if (!cancelled) setOffline(true);
        /* fall through to normal token flow */
      }
      if (!getToken()) {
        setLoading(false);
        return;
      }
      try {
        const me = await api<User>("/auth/me");
        if (!cancelled) setUser(me);
      } catch {
        setToken(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const token = await api<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setToken(token.access_token);
    setUser(await api<User>("/auth/me"));
  }, []);

  const register = useCallback(
    async (email: string, password: string, fullName?: string) => {
      await api<User>("/auth/register", {
        method: "POST",
        body: JSON.stringify({ email, password, full_name: fullName ?? null }),
      });
      await login(email, password);
    },
    [login],
  );

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, offline, login, register, logout }),
    [user, loading, offline, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
