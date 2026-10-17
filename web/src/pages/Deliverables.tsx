import { useState } from "react";
import { ExternalLink, FileText, Gauge, Package } from "lucide-react";
import { api, fmt, Json } from "../lib/api";
import { useJob, useProject } from "../lib/project";
import { PathField } from "../components/FilePicker";
import { Button } from "../components/ui/Button";
import { Card, CardTitle } from "../components/ui/Card";
import { Badge, JobStatus, Notice, PageHeader } from "../components/ui/Bits";
import { Chip, Field, Input, Select } from "../components/ui/Field";

const link = (p: string) => `/fs/file?path=${encodeURIComponent(p)}`;

function Files({ files }: { files: Record<string, string> }) {
  return (
    <ul className="mt-5 space-y-2">
      {Object.entries(files).filter(([, v]) => typeof v === "string").map(([k, v]) => (
        <li key={k} className="flex items-center gap-3 rounded-2xl bg-white/60 px-4 py-2.5 text-sm">
          <Badge tone="moss">{k}</Badge>
          <span className="min-w-0 flex-1 truncate text-muted-foreground">{v}</span>
          {/\.(html|pdf|png)$/i.test(v) && <a className="inline-flex items-center gap-1 font-semibold text-primary hover:underline" href={link(v)} target="_blank" rel="noreferrer">Open <ExternalLink size={14} /></a>}
        </li>
      ))}
    </ul>
  );
}

export function Deliverables() {
  const { pid, info, refresh } = useProject();
  const job = useJob();
  const options = ((info?.options ?? []) as string[]).filter((o) => o !== "baseline" && !o.startsWith("_"));
  const defaultDir = (info?.path ?? "").replace(/\.sponge$/i, "") + "_exports";
  const [chosen, setChosen] = useState<string[]>(options);
  const [dir, setDir] = useState(defaultDir);
  const [out, setOut] = useState<Record<string, string> | null>(null);
  const [cal, setCal] = useState({ option: "baseline", rainfall: "", observed: "", target: "outflow_total_cms" });
  const [calRes, setCalRes] = useState<Json | null>(null);

  const report = () => job.run("Writing the report", async (st) => {
    const files: Record<string, string> = {};
    for (const o of chosen) {
      const r = await api.job("POST", `/projects/${pid}/options/${o}/export`, { out_dir: `${dir}/${o}`, formats: ["3dm", "dxf"] }, st);
      Object.entries(r).forEach(([k, v]) => (files[`${o} ${k}`] = v as string));
    }
    const r = await api.job("POST", `/projects/${pid}/report`, { out_dir: dir, options: chosen }, st);
    files.report = r.html;
    if (r.pdf) files["report pdf"] = r.pdf;
    setOut(files);
  });

  const bundle = () => job.run("Writing the web viewer bundle", async (st) => {
    await api.job("POST", `/projects/${pid}/viewer-bundle`, { out_dir: `${dir}/bundle`, options: ["baseline", ...chosen] }, st);
    setOut({ ...(out ?? {}), "viewer bundle": `${dir}/bundle` });
  });

  const calibrate = () => job.run("Calibrating (SWMM in the loop)", async (st) => {
    setCalRes(await api.job("POST", `/projects/${pid}/calibrate`, cal, st));
    await refresh();
  });

  return (
    <div>
      <PageHeader eyebrow="Step 6" title="Deliverables">
        The report for reviewers and funders, drawings for the team, and calibration when observed data arrives.
      </PageHeader>
      <div className="mb-6"><JobStatus running={job.running} error={job.error} /></div>

      <div className="grid gap-8 lg:grid-cols-2">
        <Card shape={0}>
          <CardTitle eyebrow="Report and drawings" title="Write everything" />
          <div className="space-y-5">
            <div>
              <p className="mb-2 pl-1 text-sm font-semibold text-accent-foreground">Options in the report</p>
              <div className="flex flex-wrap gap-2">
                {options.map((o) => <Chip key={o} checked={chosen.includes(o)} onChange={(v) => setChosen(v ? [...chosen, o] : chosen.filter((x) => x !== o))}>{o}</Chip>)}
                {options.length === 0 && <p className="text-sm text-muted-foreground">No options yet: the report will show the existing site.</p>}
              </div>
            </div>
            <Field label="Folder" hint="HTML and PDF report, SWMM input files, Rhino .3dm and design DXF per option.">
              {() => <PathField value={dir} onChange={setDir} ext=".html" pickFolder title="Choose the output folder" />}
            </Field>
            <div className="flex flex-wrap gap-3">
              <Button onClick={report} disabled={!dir} busy={job.running?.startsWith("Writing the report")}><FileText size={18} /> Write report and drawings</Button>
              <Button variant="outline" onClick={bundle} disabled={!dir}><Package size={18} /> Web viewer bundle</Button>
            </div>
            {out && <Files files={out} />}
          </div>
        </Card>

        <Card shape={1} tone="stone">
          <CardTitle eyebrow="Calibration" title={info?.calibration === "uncalibrated" ? "Uncalibrated" : "Calibrated"} />
          <p className="mb-5 text-sm text-accent-foreground">
            With a recorded storm and what was observed on site (flow at the outlet, or water depth in an element),
            the engine adjusts infiltration, roughness, depression storage and imperviousness to match. The model is
            labelled calibrated only when the fit is good (NSE ≥ {fmt(0.5)}).
          </p>
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Model">{(id) => (
                <Select id={id} value={cal.option} onChange={(e) => setCal({ ...cal, option: e.target.value })}>
                  {["baseline", ...options].map((o) => <option key={o} value={o}>{o === "baseline" ? "existing site" : o}</option>)}
                </Select>)}</Field>
              <Field label="Observed series" hint="outflow_total_cms, or depth_<id>_m">{(id) => <Input id={id} value={cal.target} onChange={(e) => setCal({ ...cal, target: e.target.value })} />}</Field>
            </div>
            <Field label="Recorded rainfall (CSV: time_min, intensity_mm_hr)">{() => <PathField value={cal.rainfall} onChange={(v) => setCal({ ...cal, rainfall: v })} ext=".csv" title="Recorded rainfall CSV" />}</Field>
            <Field label="Observations (CSV: time_hr, value)">{() => <PathField value={cal.observed} onChange={(v) => setCal({ ...cal, observed: v })} ext=".csv" title="Observations CSV" />}</Field>
            <Button variant="clay" onClick={calibrate} disabled={!cal.rainfall || !cal.observed}><Gauge size={18} /> Calibrate</Button>
            {calRes && (
              <Notice tone={calRes.accepted ? "info" : "warn"} title={`NSE ${fmt(calRes.nse_uncalibrated, 2)} → ${fmt(calRes.nse_calibrated, 2)}`}>
                {Object.entries(calRes.factors).map(([k, v]) => `${k.replace("_", " ")} ×${fmt(v as number, 2)}`).join(" · ")}. {calRes.note}.
              </Notice>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
