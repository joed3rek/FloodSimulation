import { useEffect, useState } from "react";
import { ArrowLeft, Download, Droplets, Play, RefreshCw, Sparkles, Upload, Wand2 } from "lucide-react";
import { api, fmt, Json } from "../lib/api";
import { useJob, useProject } from "../lib/project";
import { go } from "../lib/route";
import { PathField } from "../components/FilePicker";
import { WaterBalance } from "../components/WaterBalance";
import { Button } from "../components/ui/Button";
import { Card, CardTitle } from "../components/ui/Card";
import { Badge, DataTable, Empty, JobStatus, Notice, PageHeader, Stat } from "../components/ui/Bits";
import { Chip, Field, Input, Segmented } from "../components/ui/Field";

const TYPES = [
  ["detention_pond", "Detention ponds"], ["retention_pond", "Retention ponds"], ["bioswale", "Bioswales"],
  ["rain_garden", "Rain gardens"], ["recharge_well", "Recharge wells"],
];
const typeLabel = (t: string) => t.replace(/_/g, " ");

export function Options({ arg }: { arg?: string }) {
  return arg ? <OptionDetail oid={arg} /> : <OptionList />;
}

function OptionList() {
  const { pid, info, refresh } = useProject();
  const job = useJob();
  const [cards, setCards] = useState<Record<string, Json>>({});
  const [name, setName] = useState("auto");
  const [types, setTypes] = useState<string[]>(["detention_pond", "bioswale", "rain_garden", "recharge_well"]);
  const [budget, setBudget] = useState("");
  const [mode, setMode] = useState<"forward" | "inverse">("forward");
  const options = ((info?.options ?? []) as string[]).filter((o) => o !== "baseline" && !o.startsWith("_"));

  useEffect(() => {
    options.forEach((o) => api.get(`/projects/${pid}/options/${o}/comparison`).then((c) => setCards((x) => ({ ...x, [o]: c }))).catch(() => undefined));
  }, [pid, info]); // eslint-disable-line react-hooks/exhaustive-deps

  const generate = () => job.run("Placing, sizing and grading", async (st) => {
    const overrides: Record<string, number> = budget ? { "layout.max_area_pct": Number(budget) } : {};
    await api.job("POST", `/projects/${pid}/options/${name}/generate`, { types, overrides, run: true }, st);
    await refresh();
    go("options", name);
  });

  const optimise = () => job.run(mode === "forward" ? "Searching for the best layouts" : "Searching for the least area", async (st) => {
    await api.job("POST", `/projects/${pid}/optimise`, { mode }, st);
    await refresh();
  });

  return (
    <div>
      <PageHeader eyebrow="Step 4" title="Design options">
        The engine proposes; you decide. Every option is graded into the ground and run in SWMM for every storm.
      </PageHeader>
      {!info?.has_baseline && <div className="mb-8"><Notice tone="warn">Analyse the existing site first: options are sized from it and compared with it.</Notice></div>}

      <div className="grid gap-8 lg:grid-cols-2">
        <Card shape={0}>
          <CardTitle eyebrow="Generate" title="One layout from the ground" />
          <div className="space-y-5">
            <div className="flex flex-wrap gap-2">
              {TYPES.map(([t, l]) => <Chip key={t} checked={types.includes(t)} onChange={(v) => setTypes(v ? [...types, t] : types.filter((x) => x !== t))}>{l}</Chip>)}
            </div>
            <div className="grid gap-5 sm:grid-cols-2">
              <Field label="Option name">{(id) => <Input id={id} value={name} onChange={(e) => setName(e.target.value.replace(/[^\w-]/g, ""))} />}</Field>
              <Field label="Area budget (% of site)" hint="Empty: use your target.">{(id) => <Input id={id} inputMode="decimal" value={budget} onChange={(e) => setBudget(e.target.value)} />}</Field>
            </div>
            <Button onClick={generate} disabled={!info?.has_baseline || !types.length || !name} busy={job.running?.startsWith("Placing")}><Wand2 size={18} /> Generate and run</Button>
          </div>
        </Card>
        <Card shape={1} tone="sand">
          <CardTitle eyebrow="Optimise" title="Search many layouts" />
          <p className="mb-5 text-sm text-accent-foreground">NSGA-II searches the generator's settings; a learned model picks which layouts to run, and every option shown is verified in SWMM.</p>
          <Segmented label="Goal" value={mode} onChange={setMode} options={[
            { value: "forward", label: "Most retention in the budget" }, { value: "inverse", label: "Least area for the target storm" }]} />
          <div className="mt-5"><Button variant="clay" onClick={optimise} disabled={!info?.has_baseline} busy={job.running?.startsWith("Searching")}><Sparkles size={18} /> Optimise</Button></div>
          <p className="mt-3 text-xs text-muted-foreground">Takes several minutes: dozens of layouts are graded and run.</p>
        </Card>
      </div>
      <div className="mt-6"><JobStatus running={job.running} error={job.error} /></div>

      <section className="mt-16">
        <h2 className="mb-6 text-2xl font-semibold">Options</h2>
        {options.length === 0 ? <Empty title="No options yet">Generate a layout or run the optimiser.</Empty> : (
          <ul className="grid gap-8 md:grid-cols-2 lg:grid-cols-3">
            {options.map((o, i) => {
              const c = cards[o];
              const r2 = c?.rows?.[0];
              return (
                <li key={o}>
                  <a href={`#/options/${o}`} className="group block h-full">
                    <Card shape={i + 2} lift className="h-full">
                      <p className="text-xs font-bold uppercase tracking-wider text-secondary-ink">Option</p>
                      <h3 className="mt-1 text-2xl font-semibold">{o}</h3>
                      {c ? (
                        <div className="mt-6 grid grid-cols-2 gap-6">
                          <Stat label="Site used" value={fmt(c.intervention_area_pct, 1)} unit="%" />
                          <Stat label="Fully retains" value={c.design_retention_storm_yr ? `${c.design_retention_storm_yr}-yr` : "none"} />
                          {r2 && <Stat label={`${r2.return_period_yr}-yr kept`} value={fmt(r2.option_retained_pct, 0)} unit="%" note={`now ${fmt(r2.baseline_retained_pct, 0)} %`} />}
                          {r2 && <Stat label={`${r2.return_period_yr}-yr peak`} value={`−${fmt(r2.peak_reduction_pct, 0)}`} unit="%" />}
                        </div>
                      ) : <p className="mt-4 text-sm text-muted-foreground">Not run yet.</p>}
                    </Card>
                  </a>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}

function OptionDetail({ oid }: { oid: string }) {
  const { pid, refresh } = useProject();
  const job = useJob();
  const [summary, setSummary] = useState<Json | null>(null);
  const [cmp, setCmp] = useState<Json | null>(null);
  const [layout, setLayout] = useState<Json | null>(null);
  const [stamp, setStamp] = useState(0);
  const [rhinoIn, setRhinoIn] = useState("");
  const [rhinoOut, setRhinoOut] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    api.get(`/projects/${pid}/options/${oid}/summary`).then(setSummary).catch(() => setSummary(null));
    api.get(`/projects/${pid}/options/${oid}/comparison`).then(setCmp).catch(() => setCmp(null));
    api.fileJson(pid!, `options/${oid}/layout_report.json`).then(setLayout);
  }, [pid, oid, stamp]);

  const after = async () => { setStamp((s) => s + 1); await refresh(); };
  const rerun = () => job.run("Running SWMM", async (st) => { await api.job("POST", `/projects/${pid}/options/${oid}/run`, {}, st); await after(); });
  const exportRhino = () => job.run("Writing the Rhino file", async (st) => {
    const r = await api.job("POST", `/projects/${pid}/options/${oid}/export`, { out_dir: rhinoOut, formats: ["3dm", "dxf"] }, st);
    setMessage(`Written: ${Object.values(r).join(" · ")}`);
  });
  const importRhino = () => job.run("Reading your edits", async (st) => {
    const r = await api.job("POST", `/projects/${pid}/options/${oid}/import-3dm`, { path: rhinoIn }, st);
    const ch = r.changes;
    setMessage(["moved", "resized", "reshaped", "new", "deleted"].filter((k) => ch[k].length).map((k) => `${k}: ${ch[k].join(", ")}`).join(" · ")
      || "No changes found in the Rhino file.");
    await after();
  });

  const elements: Json[] = summary?.elements ?? [];
  const lastRp = summary ? Object.keys(summary.return_periods).sort((a, b) => +a - +b).pop()! : "";
  const res = summary ? Object.fromEntries(summary.return_periods[lastRp].elements.map((e: Json) => [e.id, e])) : {};

  return (
    <div>
      <a href="#/options" className="mb-6 inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-sm font-semibold text-primary hover:bg-primary/10"><ArrowLeft size={16} /> All options</a>
      <PageHeader eyebrow="Option" title={oid}
        action={<div className="flex flex-wrap gap-3">
          <Button variant="ghost" onClick={rerun} busy={job.running === "Running SWMM"}><RefreshCw size={18} /> Run SWMM</Button>
          <Button onClick={() => go("storm")}><Droplets size={18} /> Watch a storm</Button>
        </div>}>
        {summary?.calibration}
      </PageHeader>
      <div className="mb-6 space-y-3"><JobStatus running={job.running} error={job.error} />{message && <Notice title="Rhino">{message}</Notice>}</div>

      {!summary ? <Empty title="Not run yet"><Button className="mt-4" onClick={rerun}><Play size={18} /> Run SWMM</Button></Empty> : (
        <>
          {cmp && (
            <Card shape={2} className="mb-16 grid grid-cols-2 gap-8 md:grid-cols-4 md:gap-12">
              <Stat label="Site used" value={fmt(cmp.intervention_area_pct, 1)} unit="%" />
              <Stat label="Largest storm fully retained" value={cmp.design_retention_storm_yr ? `${cmp.design_retention_storm_yr}-year` : "none"} />
              <Stat label="Earthworks" value={fmt(layout?.cut_total_m3, 0)} unit="m³ cut" note="exported; no fill designed" />
              <Stat label="Elements" value={elements.length} note={Object.entries(elements.reduce((a: Record<string, number>, e) => ({ ...a, [e.type]: (a[e.type] || 0) + 1 }), {})).map(([t, n]) => `${n} ${typeLabel(t)}`).join(", ")} />
            </Card>
          )}

          <div className="grid gap-10 lg:grid-cols-[1.1fr_1fr]">
            <figure>
              <img src={`${api.fileUrl(pid!, `options/${oid}/layout.png`)}&v=${stamp}`} alt={`Layout of option ${oid}`}
                className="w-full rotate-[1deg] rounded-[2rem] rounded-br-[4rem] border-4 border-white shadow-float transition-transform duration-700 hover:rotate-0"
                onError={(e) => ((e.target as HTMLImageElement).style.display = "none")} />
              {layout?.skipped?.length > 0 && <div className="mt-6 space-y-3">{layout.skipped.map((s: string) => <Notice key={s} tone="warn">{s}</Notice>)}</div>}
            </figure>
            <div>
              <h2 className="mb-4 text-2xl font-semibold">Where the rain goes</h2>
              <WaterBalance summary={summary} />
            </div>
          </div>

          {cmp && (
            <section className="mt-16">
              <h2 className="mb-4 text-2xl font-semibold">Against the existing site</h2>
              <DataTable caption="Comparison" rows={cmp.rows} columns={[
                { key: "rp", label: "Storm", render: (r) => <b>{r.return_period_yr}-year</b> },
                { key: "kept", label: "Kept on site", align: "right", render: (r) => <>{fmt(r.baseline_retained_pct, 0)} → <b>{fmt(r.option_retained_pct, 0)} %</b></> },
                { key: "litres", label: "Water kept (L)", align: "right", render: (r) => fmt((r.rainfall_total_m3 - r.option_outflow_m3) * 1000, 0) },
                { key: "peak", label: "Peak outflow", align: "right", render: (r) => <b>−{fmt(r.peak_reduction_pct, 0)} %</b> },
                { key: "lag", label: "Peak later by", align: "right", render: (r) => `${fmt(r.lag_hr, 2)} h` },
                { key: "full", label: "Fully retained", render: (r) => r.fully_retained ? <Badge tone="moss">yes</Badge> : <Badge>no</Badge> },
              ]} />
            </section>
          )}

          <section className="mt-16">
            <h2 className="mb-4 text-2xl font-semibold">Component schedule</h2>
            <DataTable caption="Components" rows={elements} columns={[
              { key: "id", label: "Element", render: (e) => <span className="font-semibold">{e.id} {e.source === "designer" && <Badge tone="water">yours</Badge>}</span> },
              { key: "type", label: "Type", render: (e) => typeLabel(e.type) },
              { key: "area", label: "Area (m²)", align: "right", render: (e) => fmt(e.area_m2, 0) },
              { key: "depth", label: "Depth (m)", align: "right", render: (e) => fmt(e.max_ponding_depth_m ?? e.well_depth_m, 2) },
              { key: "storage", label: "Storage (m³)", align: "right", render: (e) => fmt(e.storage_volume_m3, 1) },
              { key: "inf", label: "Infiltration (mm/h)", align: "right", render: (e) => fmt(e.infiltration_rate_mm_hr, 2) },
              { key: "dd", label: `Drawdown (h), ${lastRp}-yr`, align: "right", render: (e) => fmt(res[e.id]?.drawdown_hr, 0) },
              { key: "to", label: "Sends water to", render: (e) => e.outflow_to || e.overflow_to },
            ]} />
          </section>

          <section className="mt-16 grid gap-8 lg:grid-cols-2">
            <Card shape={4} tone="stone">
              <CardTitle eyebrow="Rhino" title="Edit in Rhino" />
              <Field label="Export to folder">{() => <PathField value={rhinoOut} onChange={setRhinoOut} ext=".3dm" pickFolder title="Choose a folder for the Rhino and DXF files" />}</Field>
              <Button className="mt-4" variant="outline" onClick={exportRhino} disabled={!rhinoOut}><Download size={18} /> Export .3dm and DXF</Button>
            </Card>
            <Card shape={5} tone="sand">
              <CardTitle eyebrow="Rhino" title="Bring your edits back" />
              <Field label="Edited .3dm" hint="Moved, resized, deleted and new elements are detected and locked as yours; the ground is regraded and SWMM rerun.">
                {() => <PathField value={rhinoIn} onChange={setRhinoIn} ext=".3dm" title="Choose the edited Rhino file" />}
              </Field>
              <Button className="mt-4" onClick={importRhino} disabled={!rhinoIn}><Upload size={18} /> Apply edits</Button>
            </Card>
          </section>
        </>
      )}
    </div>
  );
}
