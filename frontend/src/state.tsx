import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type ConsentState, type User } from "./api/client";

interface AppState {
  user: User | null;
  needsSetup: boolean;
  loading: boolean;
  refreshAuth: () => Promise<void>;
  consent: ConsentState | null;
  refreshConsent: () => Promise<void>;
  sessionId: string | null;
  setSessionId: (id: string | null) => void;
}

const Ctx = createContext<AppState | null>(null);
const SESSION_KEY = "hv.session";

function readSession(): string | null {
  try { return localStorage.getItem(SESSION_KEY); } catch { return null; }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [needsSetup, setNeedsSetup] = useState(false);
  const [loading, setLoading] = useState(true);
  const [consent, setConsent] = useState<ConsentState | null>(null);
  const [sessionId, setSid] = useState<string | null>(readSession());

  const setSessionId = useCallback((id: string | null) => {
    setSid(id);
    try { id ? localStorage.setItem(SESSION_KEY, id) : localStorage.removeItem(SESSION_KEY); } catch { /* ignore */ }
  }, []);

  const refreshConsent = useCallback(async () => {
    try { setConsent(await api.get<ConsentState>("/consent")); } catch { setConsent(null); }
  }, []);

  const refreshAuth = useCallback(async () => {
    const s = await api.get<{ needs_setup: boolean; user: User | null }>("/auth/status");
    setNeedsSetup(s.needs_setup);
    setUser(s.user);
    if (s.user) await refreshConsent();
    setLoading(false);
  }, [refreshConsent]);

  useEffect(() => { refreshAuth().catch(() => setLoading(false)); }, [refreshAuth]);

  return (
    <Ctx.Provider value={{ user, needsSetup, loading, refreshAuth, consent, refreshConsent, sessionId, setSessionId }}>
      {children}
    </Ctx.Provider>
  );
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp outside provider");
  return v;
}

export function granted(consent: ConsentState | null, purpose: "BMI" | "FACE_ANALYSIS" | "RECOGNITION"): boolean {
  return !!consent?.consents.find((c) => c.purpose === purpose)?.granted;
}
