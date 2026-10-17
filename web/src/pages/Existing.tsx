import { useEffect, useState } from "react";
import { Play } from "lucide-react";
import { api, fmt, Json } from "../lib/api";
import { useJob, useProject } from "../lib/project";
import { WaterBalance } from "../components/WaterBalance";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { DataTable, Empty, JobStatus, Notice, PageHeader, Stat } from "../components/ui/Bits";

export function Existing() {
  const { pid, info, refresh } = useProject();
  const job = useJob();
  const [summary, setSummary] = useState<Json | null>(null);
  const [flow, setFlow] = useState<Json | null>(null);
  const [stamp, setStamp] = useState(0);

  useEffect(() => {
    api.get(`/projects/${pid}/options/baseline/summary`).then(setSummary).catch(() => setSummary(null));
    api.fileJson(pid!, "terrain/flow/report.json").then(setFlow);
  }, [pid, stamp]);

  const analyse = () => job.run("Analysing the existing site", async (st) => {
    await api.job("POST", `/projects/${pid}/baseline?delineate_first=true`, {}, st);
    setStamp((s) => s + 1);
    await refresh();
  });

  const rows = summary ? Object.entries(summary.return_periods).sort(([a], [b]) => +a - +b).map(([rp, v]: [string, Json]) => ({
    rp, rain: v.storm.depth_mm, leaving: v.water_balance.outflow_total_m3 + v.water_balance.flooding_m3,
    kept: v.water_balance.retained_pct, peak: v.hydrograph.peak_cms * 1000, cont: v.water_balance.closure_error_pct,
  })) : [];

  return (
    <div>
      <PageHeader eyebrow="Step 3" title="The existing site"
        action={<Button onClick={analyse} busy={!!job.running} disabled={!info?.has_terrain || !info?.has_soils || !info?.has_rainfall}><Play size={18} /> {summary ? "Analyse again" : "Analyse"}</Button>}>
        How water moves and leaves the park today, for every storm. This is what every design is compared with.
      </PageHeader>
      <div className="mb-6"><JobStatus running={job.running} error={job.error} /></div>
      {(!info?.has_soils || !info?.has_rainfall) && <div className="mb-8"><Notice tone="warn">Needs soil zones and a rainfall table first (Targets & parameters).</Notice></div>}

      {!summary ? <Empty title="Not analysed yet">Analysis traces water over the ground model, divides the park into drainage areas and runs SWMM for every storm.</Empty> : (
        <>
          {flow && (
            <Card shape={2} className="mb-16 grid grid-cols-2 gap-8 md:grid-cols-4 md:gap-12">
              <Stat label="Drainage areas" value={flow.subcatchments.length} />
              <Stat label="Modelled area" value={fmt(flow.domain_area_m2, 0)} unit="m²" note={flow.unmodelled_area_m2 > 1 ? `${fmt(flow.unmodelled_area_m2, 0)} m² of the boundary has no survey data` : undefined} />
              <Stat label="Natural hollows" value={fmt(flow.depression_total_m3, 1)} unit="m³" note="water the ground already holds" />
              <Stat label="Places water leaves" value={flow.subcatchments.length} note="to confirm on site: gates, gaps, drains" />
            </Card>
          )}
          <div className="grid gap-10 lg:grid-cols-[1.1fr_1fr]">
            <figure className="relative">
              <img src={`${api.fileUrl(pid!, "terrain/flow/flow.png")}&v=${stamp}`} alt="Drainage areas, main flow paths and where water leaves"
                className="w-full rotate-[-1deg] rounded-[2rem] rounded-tl-[4rem] border-4 border-white shadow-float transition-transform duration-700 hover:rotate-0" />
              <figcaption className="mt-4 text-sm text-muted-foreground">Drainage areas (shaded), main flow paths (blue), where water leaves (triangles), natural hollows (red circles).</figcaption>
            </figure>
            <div className="space-y-10">
              <div>
                <h2 className="mb-4 text-2xl font-semibold">Where the rain goes</h2>
                <WaterBalance summary={summary} />
              </div>
            </div>
          </div>
          <section className="mt-16">
            <h2 className="mb-4 text-2xl font-semibold">Every storm</h2>
            <DataTable caption="Existing site results" rows={rows} columns={[
              { key: "rp", label: "Storm", render: (r) => <b>{r.rp}-year</b> },
              { key: "rain", label: "Rain (mm)", align: "right", render: (r) => fmt(r.rain, 0) },
              { key: "leaving", label: "Leaves the site (m³)", align: "right", render: (r) => fmt(r.leaving, 0) },
              { key: "kept", label: "Kept on site (%)", align: "right", render: (r) => fmt(r.kept, 0) },
              { key: "peak", label: "Peak outflow (L/s)", align: "right", render: (r) => fmt(r.peak, 0) },
              { key: "cont", label: "Continuity error (%)", align: "right", render: (r) => <span className={Math.abs(r.cont) > 1 ? "font-bold text-destructive" : ""}>{fmt(r.cont, 2)}</span> },
            ]} />
          </section>
        </>
      )}
    </div>
  );
}
