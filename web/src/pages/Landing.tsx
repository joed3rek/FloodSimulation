// Opening screen: a dark, cinematic hero whose one action is importing a survey drawing.
import { useEffect, useRef, useState } from "react";
import { ArrowDownRight, ArrowUpRight, FileUp, FolderOpen, Layers, Loader2, Sprout } from "lucide-react";
import { api } from "../lib/api";
import { useReveal, useScrollY } from "../lib/motion";
import { recentProjects, useProject } from "../lib/project";
import { go } from "../lib/route";
import { FilePicker, PathField } from "../components/FilePicker";
import { cx } from "../components/ui/cx";
import { saveIntake } from "./Intake";

/** Irregular contour rings, like a survey's hill drawn by hand. */
function ContourArt({ className, tone }: { className?: string; tone: string }) {
  const rings = Array.from({ length: 9 }, (_, i) => i);
  return (
    <svg viewBox="0 0 400 400" className={className} aria-hidden>
      {rings.map((i) => {
        const r = 40 + i * 19, w = 1 + 0.12 * Math.sin(i * 1.7), k = 0.08 + i * 0.01;
        const d = Array.from({ length: 13 }, (_, j) => {
          const a = (j / 12) * Math.PI * 2;
          const rr = r * (1 + k * Math.sin(3 * a + i * 0.9) + 0.05 * Math.cos(5 * a - i));
          return `${j ? "L" : "M"}${200 + rr * Math.cos(a) * w},${200 + rr * Math.sin(a)}`;
        }).join(" ");
        return <path key={i} d={d + "Z"} fill="none" stroke={tone} strokeOpacity={0.55 - i * 0.045} strokeWidth={i % 3 === 0 ? 1.6 : 0.8} strokeLinejoin="round" />;
      })}
    </svg>
  );
}

/** Rain falling into a hollow and staying there. */
function WaterArt({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 400 300" className={className} aria-hidden>
      <defs>
        <linearGradient id="pool" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="rgb(var(--color-water))" stopOpacity="0.55" />
          <stop offset="1" stopColor="rgb(var(--color-water-deep))" stopOpacity="0.9" />
        </linearGradient>
      </defs>
      <path d="M10 170 C 90 160, 120 250, 200 250 S 320 160, 390 175" fill="none" stroke="rgb(var(--color-accent))" strokeOpacity="0.6" strokeWidth="2" />
      <path d="M105 205 C 140 245, 260 245, 295 205 C 250 222, 150 222, 105 205Z" fill="url(#pool)" />
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <line key={i} x1={120 + i * 32} y1={30 + (i % 3) * 22} x2={112 + i * 32} y2={62 + (i % 3) * 22}
          stroke="rgb(var(--color-primary-foreground))" strokeOpacity="0.45" strokeWidth="2" strokeLinecap="round" />
      ))}
      <ellipse cx="200" cy="216" rx="58" ry="6" fill="none" stroke="rgb(var(--color-primary-foreground))" strokeOpacity="0.35" />
    </svg>
  );
}

export function Landing() {
  const { open, engineUp } = useProject();
  const y = useScrollY();
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [path, setPath] = useState("");
  const [showPath, setShowPath] = useState(false);
  const [openPicker, setOpenPicker] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const recent = recentProjects().filter((r) => r.toLowerCase().endsWith(".sponge"));
  useReveal([recent.length]);

  const startWith = async (fn: () => Promise<unknown>, label: string) => {
    setErr(null); setBusy(label);
    try { saveIntake(await fn()); go("intake"); }
    catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(null); }
  };

  const upload = (file: File) => startWith(async () => {
    const res = await fetch(`/intake/upload?filename=${encodeURIComponent(file.name)}`, { method: "POST", body: await file.arrayBuffer() });
    const data = await res.json();
    if (!res.ok) throw new Error(data?.detail ?? res.statusText);
    return data;
  }, `Reading ${file.name}`);

  const fromPath = async () => {
    if (path.trim().toLowerCase().endsWith(".sponge")) {
      setBusy("Opening");
      try { await open(path.trim()); go("overview"); } catch (e) { setErr(e instanceof Error ? e.message : String(e)); } finally { setBusy(null); }
    } else startWith(() => api.post("/intake/start", { path }), "Reading the drawing");
  };

  // ?survey=<path on this computer> starts the intake directly (links from other tools)
  useEffect(() => {
    const p = new URLSearchParams(window.location.search).get("survey");
    if (p) {
      window.history.replaceState(null, "", window.location.pathname);
      startWith(() => api.post("/intake/start", { path: p }), "Reading the drawing");
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const prevent = (e: DragEvent) => e.preventDefault();
    window.addEventListener("dragover", prevent);
    window.addEventListener("drop", prevent);
    return () => { window.removeEventListener("dragover", prevent); window.removeEventListener("drop", prevent); };
  }, []);

  const scrolled = y > 50;
  return (
    <div className="min-h-screen bg-night text-primary-foreground selection:bg-secondary selection:text-white">
      {/* navigation: transparent over the hero, frosted once scrolled */}
      <nav className={cx("fixed inset-x-0 top-0 z-50 transition-all duration-500",
        scrolled ? "border-b border-white/5 bg-night/80 py-4 backdrop-blur-md" : "py-8")}>
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6">
          <a href="#" className="flex items-center gap-3 font-display text-2xl font-bold tracking-tight">
            <span className="flex h-10 w-10 items-center justify-center rounded-full bg-primary"><Sprout size={20} /></span>
            Sponge Park.
          </a>
          <div className="hidden items-center gap-8 text-sm md:flex">
            <a href="#how" className="text-primary-foreground/60 transition-colors hover:text-primary-foreground">How it works</a>
            <a href="#parks" className="text-primary-foreground/60 transition-colors hover:text-primary-foreground">Your parks</a>
          </div>
          <button onClick={() => fileRef.current?.click()}
            className="rounded-full bg-primary-foreground px-6 py-3 text-sm font-bold text-night transition-all duration-300 hover:scale-105 active:scale-95">
            New project
          </button>
        </div>
      </nav>

      {/* hero */}
      <section className="relative flex min-h-screen items-center justify-center overflow-hidden pb-20 pt-32">
        <div aria-hidden className="pointer-events-none absolute inset-0">
          <div className="absolute -left-40 -top-40 h-[40rem] w-[40rem] rounded-blob bg-primary/30 blur-3xl" />
          <div className="absolute -bottom-40 -right-32 h-[36rem] w-[36rem] rounded-blob-3 bg-secondary/25 blur-3xl" />
          <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-night" />
        </div>
        <ContourArt tone="rgb(var(--color-accent))" className="pointer-events-none absolute -left-[12%] -top-[12%] w-[55vw] max-w-[760px] animate-drift-a opacity-70 md:-left-[6%]" />
        <WaterArt className="pointer-events-none absolute -bottom-[6%] -right-[8%] w-[48vw] max-w-[680px] animate-drift-b opacity-80" />

        <div className="relative z-10 mx-auto max-w-4xl px-6 text-center"
          style={{ transform: `translateY(${Math.min(y, 1000) * 0.35}px)`, opacity: Math.max(0, 1 - y / 650) }}>
          <h1 data-reveal className="font-display text-5xl font-semibold leading-[1.05] tracking-tight text-primary-foreground md:text-7xl"
            style={{ textShadow: "0 0 24px rgba(243,244,241,0.25)" }}>
            Every park can<br /><em className="font-normal italic text-accent">hold the rain.</em>
          </h1>
          <p data-reveal style={{ transitionDelay: "200ms" }} className="mx-auto mb-12 mt-6 max-w-xl text-lg font-light leading-relaxed text-primary-foreground/80">
            Start with the surveyor's drawing. The engine sorts out its layers, asks you about the ones it is not sure of,
            and builds the ground the water will move over.
          </p>

          {/* two ways in: a new project from a survey, or an existing .sponge project */}
          <div data-reveal style={{ transitionDelay: "400ms" }}>
            <div className="mx-auto grid max-w-3xl gap-5 sm:grid-cols-2">
              <div
                role="button" tabIndex={0} aria-label="New project: import a survey drawing (DXF)"
                onClick={() => !busy && fileRef.current?.click()}
                onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && fileRef.current?.click()}
                onDragEnter={(e) => { e.preventDefault(); setDrag(true); }}
                onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
                onDragLeave={() => setDrag(false)}
                onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f) f.name.toLowerCase().endsWith(".sponge") ? setErr("That is a project: use Open a project.") : upload(f); }}
                className={cx("group relative cursor-pointer rounded-[2.5rem] rounded-tl-[4.5rem] border border-dashed p-8 backdrop-blur-sm transition-all duration-500",
                  drag ? "scale-[1.02] border-accent bg-white/15" : "border-white/25 bg-white/5 hover:border-white/45 hover:bg-white/10")}>
                <div aria-hidden className="absolute inset-0 -z-10 rounded-[inherit] bg-primary/30 opacity-0 blur-2xl transition-opacity duration-500 group-hover:opacity-60" />
                {busy ? (
                  <p className="flex items-center justify-center gap-3 py-8 text-lg"><Loader2 className="animate-spin" /> {busy}…</p>
                ) : (
                  <>
                    <span className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-primary text-primary-foreground transition-transform duration-500 group-hover:scale-110">
                      <FileUp size={28} />
                    </span>
                    <p className="font-display text-2xl font-semibold">New project</p>
                    <p className="mt-1 text-sm text-primary-foreground/60">Drop the survey DXF here, or click to choose it</p>
                  </>
                )}
              </div>
              <button onClick={() => setOpenPicker(true)} aria-label="Open a project (.sponge)"
                className="group relative rounded-[2.5rem] rounded-tr-[4.5rem] border border-white/25 bg-white/5 p-8 backdrop-blur-sm transition-all duration-500 hover:border-white/45 hover:bg-white/10">
                <div aria-hidden className="absolute inset-0 -z-10 rounded-[inherit] bg-secondary/25 opacity-0 blur-2xl transition-opacity duration-500 group-hover:opacity-60" />
                <span className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-secondary text-white transition-transform duration-500 group-hover:scale-110">
                  <FolderOpen size={26} />
                </span>
                <p className="font-display text-2xl font-semibold">Open a project</p>
                <p className="mt-1 text-sm text-primary-foreground/60">A .sponge file you saved before</p>
              </button>
            </div>
            {openPicker && <FilePicker title="Open a project" ext=".sponge" onClose={() => setOpenPicker(false)}
              onPick={async (p) => { setOpenPicker(false); setBusy("Opening"); try { await open(p); go("overview"); } catch (e) { setErr(e instanceof Error ? e.message : String(e)); } finally { setBusy(null); } }} />}
            <input ref={fileRef} type="file" accept=".dxf,.dwg" className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />
            {err && <p role="alert" className="mx-auto mt-5 max-w-xl rounded-2xl bg-destructive/25 px-4 py-3 text-sm">{err}</p>}
            {engineUp === false && <p className="mx-auto mt-5 max-w-xl text-sm text-accent">The engine is not running: start it with <code>spongepark serve</code> and reload.</p>}

            <div className="mt-8 flex flex-col items-center gap-3">
              <button onClick={() => setShowPath(!showPath)} className="text-xs uppercase tracking-[0.2em] text-primary-foreground/50 transition-colors hover:text-primary-foreground">
                or use a file on this computer
              </button>
              {showPath && (
                <div className="w-full max-w-xl rounded-[2rem] bg-white/90 p-3 text-foreground">
                  <PathField value={path} onChange={setPath} ext=".dxf,.dwg,.sponge" title="Choose a survey (.dxf) or a project (.sponge)" placeholder="D:\…\survey.dxf or park.sponge" />
                  <button onClick={fromPath} disabled={!path || !!busy} className="mt-3 h-11 w-full rounded-full bg-primary font-bold text-primary-foreground disabled:opacity-50">{path.toLowerCase().endsWith(".sponge") ? "Open this project" : "Read this drawing"}</button>
                </div>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* statement */}
      <section className="relative py-32">
        <div data-reveal className="mx-auto max-w-4xl px-6 text-center">
          <h2 className="mb-10 font-display text-3xl leading-tight text-primary-foreground/90 md:text-5xl lg:text-6xl">
            Water does not read drawings. It reads the ground.
          </h2>
          <p className="text-xl font-light leading-relaxed text-primary-foreground/50 md:text-2xl">
            So we start from the levels: every contour, every spot height, every hollow where rain already gathers.
          </p>
        </div>
        <div className="mx-auto mt-24 grid max-w-5xl grid-cols-2 gap-8 px-6 text-center md:grid-cols-4">
          {[["Survey", "DXF, any surveyor"], ["Ground", "0.5 m model"], ["SWMM", "every storm"], ["Report", "for reviewers"]].map(([a, b], i) => (
            <div key={a} data-reveal style={{ transitionDelay: `${i * 100}ms` }}>
              <p className="font-display text-2xl tracking-wide text-primary-foreground/80">{a}</p>
              <p className="mt-1 text-xs uppercase tracking-[0.2em] text-primary-foreground/40">{b}</p>
            </div>
          ))}
        </div>
      </section>

      {/* how it works: two offset cards with gentle parallax */}
      <section id="how" className="relative overflow-hidden py-40">
        <div aria-hidden className="pointer-events-none absolute left-1/2 top-1/2 h-[120%] w-[120%] -translate-x-1/2 -translate-y-1/2 opacity-10"
          style={{ backgroundImage: "radial-gradient(circle, rgb(var(--color-accent)) 1px, transparent 1px)", backgroundSize: "40px 40px" }} />
        <div className="relative z-10 mx-auto max-w-5xl px-6">
          <h2 data-reveal className="mb-28 text-center font-display text-5xl md:text-7xl">
            From the drawing<br /><em className="font-normal italic text-accent">to the storm.</em>
          </h2>
          <div className="grid gap-8 md:grid-cols-2">
            <div style={{ transform: `translateY(${y * 0.05}px)` }}>
              <article data-reveal className="group flex aspect-[4/5] flex-col justify-between rounded-[2rem] rounded-tl-[5rem] bg-secondary p-8 text-white shadow-2xl transition-shadow duration-500 hover:shadow-[0_20px_50px_rgba(193,140,93,0.35)] md:p-12">
                <div className="flex items-start justify-between">
                  <span className="flex h-12 w-12 items-center justify-center rounded-full bg-black/10 transition-transform duration-500 group-hover:rotate-45"><Layers size={22} /></span>
                  <span className="rounded-full border border-white/30 px-3 py-1 text-sm font-bold">01</span>
                </div>
                <div>
                  <h3 className="mb-4 font-display text-4xl leading-none text-white md:text-5xl">Read the<br />ground</h3>
                  <p className="text-lg leading-snug text-white/80">Layers renamed to one standard, duplicates cleared, unclear layers put to you as questions, levels turned into a ground model.</p>
                </div>
                <div className="mt-8 h-px w-full bg-white/20" />
              </article>
            </div>
            <div className="md:mt-24" style={{ transform: `translateY(${y * -0.05}px)` }}>
              <article data-reveal style={{ transitionDelay: "150ms" }} className="group flex aspect-[4/5] flex-col justify-between rounded-[2rem] rounded-br-[5rem] border border-white/10 bg-white/[0.04] p-8 shadow-2xl transition-colors duration-500 hover:border-secondary/50 md:p-12">
                <div className="flex items-start justify-between">
                  <span className="flex h-12 w-12 items-center justify-center rounded-full bg-white/5 transition-transform duration-500 group-hover:scale-110"><ArrowUpRight size={22} /></span>
                  <span className="rounded-full border border-white/10 px-3 py-1 text-sm font-bold text-white/50">02</span>
                </div>
                <div>
                  <h3 className="mb-4 font-display text-4xl leading-none md:text-5xl">Shape<br />the water</h3>
                  <p className="text-lg leading-snug text-primary-foreground/60">Ponds, swales and rain gardens carved into the ground and tested in SWMM for every storm, from the 2-year to the 100-year.</p>
                </div>
                <div className="mt-8 h-px w-full bg-white/10" />
              </article>
            </div>
          </div>
        </div>
      </section>

      {/* existing parks */}
      {recent.length > 0 && (
        <section id="parks" className="relative py-24">
          <div className="mx-auto max-w-5xl px-6">
            <h2 data-reveal className="mb-10 font-display text-3xl md:text-4xl">Recent projects</h2>
            <ul className="grid gap-4 md:grid-cols-2">
              {recent.map((r, i) => (
                <li key={r} data-reveal style={{ transitionDelay: `${i * 80}ms` }}>
                  <button onClick={async () => { await open(r); go("overview"); }}
                    className="group flex w-full items-center gap-4 rounded-[1.75rem] rounded-tl-[3rem] border border-white/10 bg-white/[0.04] p-5 text-left transition-all duration-500 hover:-translate-y-1 hover:border-secondary/40">
                    <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-primary/30 text-accent transition-colors group-hover:bg-primary"><FolderOpen size={20} /></span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-display text-xl">{r.split(/[\\/]/).pop()?.replace(".sponge", "")}</span>
                      <span className="block truncate text-xs text-primary-foreground/40">{r}</span>
                    </span>
                    <ArrowDownRight className="text-primary-foreground/40 transition-transform duration-500 group-hover:-rotate-90" />
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

      <footer className="relative overflow-hidden border-t border-white/5 py-20">
        <div className="mx-auto flex max-w-7xl flex-col items-start justify-between gap-12 px-6 md:flex-row md:items-end">
          <p aria-hidden className="select-none font-display text-[10vw] font-bold leading-[0.8] tracking-tighter text-white/10">SPONGE PARK.</p>
          <div className="flex flex-col gap-2 text-right text-sm text-primary-foreground/40">
            <span>Volumes and flows: EPA SWMM 5.2</span>
            <span>Water maps: 2D model, indicative</span>
            <span>Habitat Collective · Bengaluru</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
