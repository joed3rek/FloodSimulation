import { useEffect, useMemo, useState } from "react";
import { Check, Search, Target } from "lucide-react";
import { api, fmt, Json } from "../lib/api";
import { useJob, useProject } from "../lib/project";
import { Button } from "../components/ui/Button";
import { Card, CardTitle } from "../components/ui/Card";
import { DataTable, JobStatus, Notice, PageHeader, SourceBadge } from "../components/ui/Bits";
import { Field, Input, Segmented, Select } from "../components/ui/Field";

const TARGETS = [
  { key: "layout.max_area_pct", label: "Area budget", unit: "% of site", hint: "Most of the site an NbS layout may take." },
  { key: "layout.design_return_period_yr", label: "Size elements for", unit: "yr storm", hint: "Each element is sized to hold this storm's runoff.", rp: true },
  { key: "nbs.max_drawdown_hr", label: "Maximum drawdown", unit: "hours", hint: "Elements must empty within this (48–72 h typical)." },
  { key: "optimise.target_return_period_yr", label: "Least-area target", unit: "yr storm", hint: "Inverse optimisation retains this storm fully.", rp: true },
];

export function Parameters() {
  const { pid, info, refresh } = useProject();
  const job = useJob();
  const [params, setParams] = useState<Json[]>([]);
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<"all" | "unconfirmed" | "mine">("unconfirmed");
  const [edit, setEdit] = useState<Record<string, string>>({});
  const [soils, setSoils] = useState<Json[]>([]);
  const [arm, setArm] = useState(false); // bulk confirm needs a second, deliberate click

  const load = async () => {
    setParams(await api.get(`/projects/${pid}/parameters`));
    const s = await api.fileJson(pid!, "site/soil_zones.geojson");
    setSoils(s?.features?.map((f: Json) => f.properties) ?? []);
  };
  useEffect(() => { load(); }, [pid]); // eslint-disable-line react-hooks/exhaustive-deps

  const byKey = useMemo(() => Object.fromEntries(params.map((p) => [p.key, p])), [params]);
  const shown = params.filter((p) =>
    (filter === "all" || (filter === "unconfirmed" ? !p.confirmed && ["default", "literature"].includes(p.source) : ["user", "site measured"].includes(p.source)))
    && (!q || p.key.includes(q.toLowerCase()) || (p.note || "").toLowerCase().includes(q.toLowerCase())));

  const save = (key: string, raw: string, unit?: string) => job.run(`Saving ${key}`, async () => {
    let value: unknown = raw;
    try { value = JSON.parse(raw); } catch { /* plain text value */ }
    await api.put(`/projects/${pid}/parameters/${key}`, { value, unit: unit ?? byKey[key]?.unit, source: "user" });
    setEdit((e) => { const n = { ...e }; delete n[key]; return n; });
    await load(); await refresh();
  });

  const confirm = (keys: string[]) => job.run("Confirming", async () => {
    for (const k of keys) await api.post(`/projects/${pid}/parameters/${k}/confirm`);
    await load(); await refresh();
  });

  const unconfirmed = params.filter((p) => !p.confirmed && ["default", "literature"].includes(p.source)).length;

  return (
    <div>
      <PageHeader eyebrow="Step 2" title="Targets and parameters">
        Every value the engine uses is listed with where it came from. Defaults are assumptions until you confirm
        them; reports say so.
      </PageHeader>

      <section className="mb-16 grid gap-8 lg:grid-cols-[1.5fr_1fr]">
        <Card shape={0}>
          <CardTitle eyebrow="Design decisions" title="Targets" />
          <div className="grid gap-6 sm:grid-cols-2">
            {TARGETS.map((t) => {
              const p = byKey[t.key];
              const v = edit[t.key] ?? (p ? String(p.value) : "");
              return (
                <Field key={t.key} label={`${t.label} (${t.unit})`} hint={<>{t.hint} {p && <SourceBadge source={p.source} confirmed={p.confirmed} />}</>}>
                  {(id) => (
                    <div className="flex gap-2">
                      {t.rp ? (
                        <Select id={id} value={v} onChange={(e) => setEdit({ ...edit, [t.key]: e.target.value })}>
                          {(info?.return_periods as number[] ?? []).map((r) => <option key={r} value={r}>{r}-year</option>)}
                        </Select>
                      ) : <Input id={id} inputMode="decimal" value={v} onChange={(e) => setEdit({ ...edit, [t.key]: e.target.value })} />}
                      <Button size="md" variant={edit[t.key] !== undefined ? "primary" : "ghost"} aria-label={`Save ${t.label}`}
                        onClick={() => save(t.key, v)} disabled={edit[t.key] === undefined}><Check size={18} /></Button>
                    </div>
                  )}
                </Field>
              );
            })}
          </div>
        </Card>

        <Card shape={2} tone="stone">
          <CardTitle eyebrow="Site" title="Soil zones" />
          {soils.length === 0 ? (
            <Notice tone="warn" title="No soil zones">Infiltration is never assumed: add soil_zones.geojson with a measured rate per zone (CLI: <code>site import … soils</code>).</Notice>
          ) : (
            <ul className="space-y-4">
              {soils.map((s) => (
                <li key={s.id} className="rounded-3xl rounded-tl-lg bg-card/80 p-4">
                  <p className="flex items-center justify-between font-semibold">{s.id} <SourceBadge source={s.source || "default"} /></p>
                  <p className="mt-1 text-sm tabular">
                    {s.hsg && <>Soil group {s.hsg} · </>}
                    {s.ksat_mm_hr != null ? <>K<sub>sat</sub> {fmt(s.ksat_mm_hr, 2)} mm/h</> : s.min_rate_mm_hr != null ? <>{fmt(s.min_rate_mm_hr, 1)} mm/h</> : "no rate"}
                  </p>
                  {s.note && <p className="mt-1 text-xs text-muted-foreground">{s.note}</p>}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </section>

      <section>
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold">All parameters</h2>
            <p className="text-sm text-muted-foreground">{unconfirmed} defaults not yet confirmed.</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Segmented label="Show" value={filter} onChange={setFilter} options={[
              { value: "unconfirmed", label: "To confirm" }, { value: "mine", label: "Set by you" }, { value: "all", label: "All" }]} />
            <div className="relative">
              <Search size={16} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input aria-label="Search parameters" className="w-64 pl-10" placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
          </div>
        </div>
        <div className="mb-4 flex items-center gap-3">
          <JobStatus running={job.running} error={job.error} />
          {filter === "unconfirmed" && shown.length > 0 && (
            arm ? (
              <span className="inline-flex items-center gap-2">
                <Button variant="clay" size="sm" onClick={() => { setArm(false); confirm(shown.map((p) => p.key)); }}>Yes, I have reviewed all {shown.length}</Button>
                <Button variant="ghost" size="sm" onClick={() => setArm(false)}>Cancel</Button>
              </span>
            ) : <Button variant="outline" size="sm" onClick={() => setArm(true)}><Target size={16} /> Confirm the {shown.length} shown…</Button>
          )}
        </div>
        <DataTable dense caption="Parameters" rows={shown} columns={[
          { key: "key", label: "Parameter", render: (p) => <div><code className="text-xs font-semibold">{p.key}</code><p className="max-w-md text-xs text-muted-foreground">{p.note}</p></div> },
          { key: "value", label: "Value", render: (p) => (
            <div className="flex items-center gap-2">
              <Input aria-label={`Value of ${p.key}`} className="h-10 w-40" value={edit[p.key] ?? (typeof p.value === "object" ? JSON.stringify(p.value) : String(p.value))}
                onChange={(e) => setEdit({ ...edit, [p.key]: e.target.value })} />
              {edit[p.key] !== undefined && <Button size="sm" onClick={() => save(p.key, edit[p.key])}>Save</Button>}
            </div>
          ) },
          { key: "unit", label: "Unit", render: (p) => <span className="text-xs text-muted-foreground">{p.unit}</span> },
          { key: "source", label: "Source", render: (p) => <SourceBadge source={p.source} confirmed={p.confirmed} /> },
          { key: "act", label: "", render: (p) => !p.confirmed && <Button size="sm" variant="ghost" onClick={() => confirm([p.key])}>Confirm</Button> },
        ]} />
      </section>
    </div>
  );
}
