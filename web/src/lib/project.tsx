// The open project, shared by every page.
import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { api, Json } from "./api";

type Ctx = {
  pid: string | null;
  info: Json | null;
  engineUp: boolean | null;
  open: (path: string, create?: boolean) => Promise<void>;
  close: () => Promise<void>;
  refresh: () => Promise<void>;
};

const ProjectContext = createContext<Ctx | null>(null);
const RECENT = "spongepark.recent";

export function recentProjects(): string[] {
  try { return JSON.parse(localStorage.getItem(RECENT) || "[]"); } catch { return []; }
}

function remember(path: string) {
  try {
    const r = [path, ...recentProjects().filter((p) => p !== path)].slice(0, 6);
    localStorage.setItem(RECENT, JSON.stringify(r));
  } catch { /* storage unavailable: recents are a convenience only */ }
}

export function ProjectProvider({ children }: { children: ReactNode }) {
  const [pid, setPid] = useState<string | null>(() => sessionStorage.getItem("spongepark.pid"));
  const [info, setInfo] = useState<Json | null>(null);
  const [engineUp, setEngineUp] = useState<boolean | null>(null);

  useEffect(() => {
    api.get("/health").then(() => setEngineUp(true)).catch(() => setEngineUp(false));
    // ?open=<path to .sponge> opens a project directly (links, bookmarks)
    const p = new URLSearchParams(window.location.search).get("open");
    if (p) {
      api.post("/projects/open", { path: p }).then((r) => {
        setPid(r.project); setInfo(r); sessionStorage.setItem("spongepark.pid", r.project); remember(p);
        window.history.replaceState(null, "", window.location.pathname + window.location.hash);
      }).catch(() => undefined);
    }
  }, []);

  const refresh = useCallback(async () => {
    if (!pid) return;
    try { setInfo(await api.get(`/projects/${pid}`)); }
    catch { setPid(null); setInfo(null); sessionStorage.removeItem("spongepark.pid"); }
  }, [pid]);

  useEffect(() => { refresh(); }, [refresh]);

  const open = async (path: string, create = false) => {
    const r = await api.post("/projects/open", { path, create });
    setPid(r.project);
    setInfo(r);
    sessionStorage.setItem("spongepark.pid", r.project);
    remember(path);
  };

  const close = async () => {
    if (pid) await api.post(`/projects/${pid}/close`);
    setPid(null); setInfo(null);
    sessionStorage.removeItem("spongepark.pid");
  };

  return <ProjectContext.Provider value={{ pid, info, engineUp, open, close, refresh }}>{children}</ProjectContext.Provider>;
}

export function useProject() {
  const c = useContext(ProjectContext);
  if (!c) throw new Error("useProject outside ProjectProvider");
  return c;
}

/** Runs an engine job with a status line and error capture. */
export function useJob() {
  const [running, setRunning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = async <T,>(label: string, fn: (status: (s: string) => void) => Promise<T>): Promise<T | undefined> => {
    setError(null);
    setRunning(label);
    try { return await fn((s) => setRunning(`${label} · ${s}`)); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); return undefined; }
    finally { setRunning(null); }
  };
  return { running, error, run, setError };
}
