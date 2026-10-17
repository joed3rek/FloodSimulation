import { useEffect, useMemo, useRef, useState } from "react";
import { Compass, Pause, Play, RotateCcw, Waves } from "lucide-react";
import { api, decodeF16, decodeF32, fmt, Json } from "../lib/api";
import { useJob, useProject } from "../lib/project";
import { SceneHandle, Side, StormScene } from "../components/StormScene";
import { Button } from "../components/ui/Button";
import { Empty, JobStatus, Notice, PageHeader } from "../components/ui/Bits";
import { Chip, Segmented, Select } from "../components/ui/Field";

type Frames = { times: number[]; n: number; data: Float32Array; meta: Json };
type Curve = { t: number[]; kept: number[]; rain: number[]; area: number };

const grid = (p: Json) => ({ rows: p.rows, cols: p.cols, cell: p.cell_m, ox: p.origin[0], oy: p.origin[1], z: decodeF32(p.z), zmin: p.z_min, zmax: p.z_max });

function sample(f: Frames, t: number, out: Float32Array) {
  let i = f.times.findIndex((x) => x > t) - 1;
  if (i < 0) i = t <= 0 ? 0 : f.times.length - 1;
  const j = Math.min(i + 1, f.times.length - 1);
  const w = j === i ? 0 : Math.min(Math.max((t - f.times[i]) / (f.times[j] - f.times[i]), 0), 1);
  for (let k = 0; k < f.n; k++) out[k] = f.data[i * f.n + k] * (1 - w) + f.data[j * f.n + k] * w;
}

const at = (c: Curve | null, th: number, key: "kept" | "rain") => {
  if (!c) return 0;
  let i = c.t.findIndex((x) => x > th) - 1;
  if (i < 0) i = th <= 0 ? 0 : c.t.length - 1;
  return c[key][i] ?? 0;
};

export function Storm({ arg }: { arg?: string }) {
  const startHours = arg ? Number(arg) || 0 : 0;
  const { pid, info } = useProject();
  const job = useJob();
  const options = ((info?.options ?? []) as string[]).filter((o) => o !== "baseline" && !o.startsWith("_"));
  const rps = (info?.return_periods ?? []) as number[];
  const [opt, setOpt] = useState(options[0] ?? "");
  const [rp, setRp] = useState(rps.includes(25) ? 25 : rps[0]);
  const [both, setBoth] = useState(true);
  const [ex, setEx] = useState(5);
  const [data, setData] = useState<{ left: Side; right?: Side; fl?: Frames; fr?: Frames; cl?: Curve; cr?: Curve } | null>(null);
  const [missing, setMissing] = useState(false);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1800);
  const [tour, setTour] = useState(false);
  const handle = useRef<SceneHandle | null>(null);

  const load = async () => {
    setData(null); setMissing(false); setPlaying(false); setT(startHours * 3600);
    const get = (p: string) => api.get(`/projects/${pid}${p}`).catch(() => null);
    const [te, to, comps, fb, fo, cb, co] = await Promise.all([
      get("/terrain"), opt ? get(`/terrain?option=${opt}`) : null, opt ? get(`/options/${opt}/components`) : null,
      get(`/options/baseline/sim2d/${rp}/frames`), opt ? get(`/options/${opt}/sim2d/${rp}/frames`) : null,
      get(`/options/baseline/retained/${rp}`), opt ? get(`/options/${opt}/retained/${rp}`) : null,
    ]);
    if (!te) return;
    const frames = (f: Json): Frames | undefined => f ? { times: f.times_s, n: f.rows * f.cols, data: decodeF16(f.frames), meta: f } : undefined;
    const curve = (c: Json): Curve | undefined => c ? { t: c.time_hr, kept: c.retained_l, rain: c.rain_l, area: c.site_area_m2 } : undefined;
    const water = (f: Json) => f ? { rows: f.rows, cols: f.cols, cell: f.cell_m, ox: f.origin[0], oy: f.origin[1] } : undefined;
    setMissing(!fb || (!!opt && !fo));
    setData({
      left: { terrain: grid(te), water: water(fb) },
      right: to ? { terrain: grid(to), components: comps, water: water(fo) } : undefined,
      fl: frames(fb), fr: frames(fo), cl: curve(cb), cr: curve(co),
    });
  };
  useEffect(() => { if (pid) load(); }, [pid, opt, rp]); // eslint-disable-line react-hooks/exhaustive-deps

  const simulate = () => job.run("Simulating the storm in 2D", async (st) => {
    await api.job("POST", `/projects/${pid}/options/baseline/sim2d/${rp}`, {}, (s) => st(`existing · ${s}`));
    if (opt) await api.job("POST", `/projects/${pid}/options/${opt}/sim2d/${rp}`, {}, (s) => st(`proposed · ${s}`));
    await load();
  });

  // playback clock
  const end = useMemo(() => Math.max(data?.fl?.times.at(-1) ?? 0, data?.fr?.times.at(-1) ?? 0), [data]);
  useEffect(() => {
    if (!playing) return;
    let raf = 0, last = performance.now();
    const step = (now: number) => {
      setT((x) => { const n = Math.min(x + ((now - last) / 1000) * speed, end); if (n >= end) setPlaying(false); return n; });
      last = now;
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [playing, speed, end]);

  const bufL = useMemo(() => data?.fl ? new Float32Array(data.fl.n) : null, [data]);
  const bufR = useMemo(() => data?.fr ? new Float32Array(data.fr.n) : null, [data]);
  useEffect(() => {
    if (!handle.current || !data) return;
    if (data.fl && bufL) sample(data.fl, t, bufL);
    if (data.fr && bufR) sample(data.fr, t, bufR);
    handle.current.show(bufL, both ? bufR : null);
  }, [t, data, both, bufL, bufR]);
  useEffect(() => handle.current?.setTour(tour), [tour]);

  const th = t / 3600;
  const rainNow = (() => {
    const c = data?.cl; if (!c) return 0;
    let i = c.t.findIndex((x) => x > th) - 1; i = Math.max(0, Math.min(i, c.t.length - 2));
    const dt = c.t[i + 1] - c.t[i]; return dt > 0 ? (c.rain[i + 1] - c.rain[i]) / c.area / dt : 0;
  })();

  if (!info?.has_baseline) return <div><PageHeader eyebrow="Storm viewer" title="Watch a storm" /><Empty title="Analyse the existing site first" /></div>;

  return (
    <div>
      <PageHeader eyebrow="Storm viewer" title="Watch a storm">
        The ground and the water from the 2D model, existing beside proposed. Litres kept come from SWMM.
      </PageHeader>

      <div className="mb-6 flex flex-wrap items-center gap-4">
        <Segmented label="Storm" value={rp} onChange={setRp} options={rps.map((r) => ({ value: r, label: `${r}-yr` }))} />
        {options.length > 0 && (
          <Select aria-label="Option" className="w-48" value={opt} onChange={(e) => setOpt(e.target.value)}>
            {options.map((o) => <option key={o} value={o}>{o}</option>)}
          </Select>
        )}
        <Chip checked={both} onChange={setBoth}>Side by side</Chip>
        <Chip checked={tour} onChange={setTour}><Compass size={16} className="mr-1 inline" />Tour</Chip>
        <label className="flex items-center gap-3 text-sm font-semibold text-accent-foreground">
          Height ×{ex}
          <input type="range" min={1} max={15} value={ex} onChange={(e) => setEx(+e.target.value)} className="accent-[rgb(var(--color-primary))]" />
        </label>
      </div>

      {missing && (
        <div className="mb-6 flex flex-wrap items-center gap-4">
          <Notice tone="info">This storm has not been simulated in 2D yet{opt ? " for both sides" : ""}.</Notice>
          <Button onClick={simulate} busy={!!job.running}><Waves size={18} /> Simulate</Button>
        </div>
      )}
      <div className="mb-4"><JobStatus running={job.running} error={job.error} /></div>

      <div className="relative h-[68vh] min-h-[420px] overflow-hidden rounded-[2.5rem] rounded-tl-[5rem] border border-border/60 shadow-float">
        {data ? (
          <StormScene key={`${opt}-${rp}-${ex}-${both}`} left={data.left} right={both ? data.right : undefined} exaggeration={ex}
            onReady={(h) => { handle.current = h; h.setTour(tour); }} />
        ) : <div className="flex h-full items-center justify-center text-muted-foreground">Loading the ground…</div>}

        {/* overlays */}
        <div className="pointer-events-none absolute left-6 top-6 rounded-full bg-white/75 px-5 py-2 shadow-soft backdrop-blur-md">
          <span className="font-display text-lg font-semibold">{rp}-year storm</span>
          <span className="ml-3 tabular text-sm text-accent-foreground">{th.toFixed(1)} h · {rainNow > 0.05 ? `rain ${fmt(rainNow, 0)} mm/h` : "no rain"}</span>
        </div>
        <div className="pointer-events-none absolute inset-x-0 bottom-0 grid grid-cols-2">
          {[["Existing", data?.cl], ...(both && data?.right ? [[`Proposed · ${opt}`, data?.cr]] : [])].map(([label, c], i) => (
            <div key={i} className={i === 0 && !(both && data?.right) ? "col-span-2 p-6" : "p-6"}>
              <div className="inline-block rounded-[1.5rem] rounded-tr-[2.5rem] bg-white/80 px-5 py-3 shadow-soft backdrop-blur-md">
                <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">{label as string}</p>
                <p className="font-display text-3xl font-bold tabular">{fmt(at(c as Curve, th, "kept"), 0)} <span className="font-sans text-base font-semibold text-muted-foreground">litres kept</span></p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-4">
        <Button onClick={() => { if (t >= end) setT(0); setPlaying(!playing); }} disabled={!data?.fl} aria-label={playing ? "Pause" : "Play"}>
          {playing ? <Pause size={18} /> : <Play size={18} />} {playing ? "Pause" : "Play"}
        </Button>
        <Button variant="ghost" onClick={() => { setPlaying(false); setT(0); }} aria-label="Restart"><RotateCcw size={18} /></Button>
        <input aria-label="Time in the storm" type="range" min={0} max={end || 1} step={60} value={t} onChange={(e) => { setPlaying(false); setT(+e.target.value); }}
          className="min-w-[200px] flex-1 accent-[rgb(var(--color-primary))]" />
        <Select aria-label="Speed" className="w-56" value={speed} onChange={(e) => setSpeed(+e.target.value)}>
          {[600, 1800, 3600, 7200].map((s) => <option key={s} value={s}>{s / 60} min per second</option>)}
        </Select>
      </div>
      <p className="mt-4 text-xs text-muted-foreground">Water: 2D model, indicative (water thinner than 1 cm not drawn). Litres kept: SWMM time series ({info.calibration}).</p>
    </div>
  );
}
