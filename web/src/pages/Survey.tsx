import { useEffect, useMemo, useState } from "react";
import { ScanSearch, Upload } from "lucide-react";
import { api, fmt, Json } from "../lib/api";
import { useJob, useProject } from "../lib/project";
import { PathField } from "../components/FilePicker";
import { Button } from "../components/ui/Button";
import { Card, CardTitle } from "../components/ui/Card";
import { Badge, DataTable, Empty, JobStatus, Notice, PageHeader, Stat } from "../components/ui/Bits";
import { Chip, Field, Input, Select } from "../components/ui/Field";

const ROLES = [
  ["", "not used"], ["contours", "contours"], ["contour_labels", "contour labels"], ["spot_levels", "spot levels"],
  ["boundary", "park boundary"], ["buildings", "buildings"], ["trees", "trees"], ["drains", "drains"],
  ["roads", "roads"], ["paths", "paths"], ["water", "water"], ["walls", "walls / fences"],
];

export function Survey() {
  const { pid, refresh } = useProject();
  const job = useJob();
  const [drawing, setDrawing] = useState("");
  const [inv, setInv] = useState<Json | null>(null);
  const [roles, setRoles] = useState<Record<string, string>>({});
  const [ask, setAsk] = useState<string[]>([]);
  const [scale, setScale] = useState("1");
  const [contoursInSurface, setContoursInSurface] = useState(true);
  const [area, setArea] = useState("");
  const [checked, setChecked] = useState(false);
  const [qc, setQc] = useState<Json | null>(null);
  const [stamp, setStamp] = useState(0);

  useEffect(() => { if (pid) api.fileJson(pid, "terrain/qc.json").then(setQc); }, [pid, stamp]);

  const inspect = () => job.run("Reading layers", async () => {
    const r = await api.post(`/projects/${pid}/survey/inspect`, { drawing });
    setInv(r.inventory);
    const m = r.suggested_layer_map;
    const map: Record<string, string> = {};
    Object.entries(m.roles as Record<string, string[]>).forEach(([role, layers]) => layers.forEach((l) => (map[l] = role)));
    setRoles(map);
    setAsk(m.needs_decision);
    setScale(String(m.units_scale_to_m));
    setChecked(false);
  });

  const layerMap = useMemo(() => {
    const out: Record<string, string[]> = {};
    Object.entries(roles).forEach(([layer, role]) => { if (role) (out[role] ||= []).push(layer); });
    return {
      confirmed: checked, units_scale_to_m: Number(scale) || 1, contours_in_surface: contoursInSurface, roles: out,
      needs_decision: ask.filter((l) => !roles[l]),
      note: "Edited and confirmed in the Sponge Park web app.",
    };
  }, [roles, checked, scale, contoursInSurface, ask]);

  const doImport = () => job.run("Building the ground model", async (st) => {
    await api.job("POST", `/projects/${pid}/survey/import`, { drawing, layer_map: layerMap, park_area_m2: area ? Number(area) : null }, st);
    setStamp((s) => s + 1);
    await refresh();
  });

  const rows = (inv?.layers ?? []) as Json[];
  const missing = ["spot_levels", "boundary"].filter((r) => !layerMap.roles[r]?.length);

  return (
    <div>
      <PageHeader eyebrow="Step 1" title="Survey and ground model">
        Read the surveyor's drawing, tell the engine what each layer is, and build the ground model. Nothing is guessed:
        unlabelled contours and odd spot levels are reported, not hidden.
      </PageHeader>

      <div className="grid gap-8 lg:grid-cols-[1.4fr_1fr]">
        <Card shape={0}>
          <CardTitle eyebrow="Drawing" title="Survey drawing" />
          <Field label="DXF or DWG file" hint="DWG needs the free ODA File Converter; or save as DXF from AutoCAD.">
            {() => <PathField value={drawing} onChange={setDrawing} ext=".dxf,.dwg" title="Choose the survey drawing" />}
          </Field>
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <Button onClick={inspect} disabled={!drawing} busy={job.running === "Reading layers"}><ScanSearch size={18} /> Read layers</Button>
            <JobStatus running={job.running} error={job.error} />
          </div>
        </Card>

        <Card shape={1} tone="stone">
          <CardTitle eyebrow="Current ground model" title={qc ? "Built" : "Not built yet"} />
          {qc ? (
            <div className="grid grid-cols-2 gap-6">
              <Stat label="Spot levels vs surface" value={fmt(qc.spot_cross_validation?.rmse_m, 3)} unit="m RMSE" note={`${qc.spot_cross_validation?.n ?? "–"} spots, hold-one-out`} />
              <Stat label="Cell size" value={fmt(qc.source?.dem_cell_m, 2)} unit="m" note={`levels ${fmt(qc.elevation_range_m?.[0], 2)}–${fmt(qc.elevation_range_m?.[1], 2)} m`} />
            </div>
          ) : <p className="text-sm text-muted-foreground">Import a drawing to build it.</p>}
        </Card>
      </div>

      {inv && (
        <section className="mt-16">
          <h2 className="mb-2 text-2xl font-semibold">What is on each layer?</h2>
          <p className="mb-6 max-w-3xl text-muted-foreground">
            The roles are suggested from the layer names. Check each one against the drawing. Layers marked
            <Badge tone="clay">decide</Badge> look like levels but their meaning is unclear (for example drain bed levels).
          </p>
          <DataTable caption="Drawing layers" rows={rows} columns={[
            { key: "name", label: "Layer", render: (r) => <span className="font-semibold">{r.name} {ask.includes(r.name) && !roles[r.name] && <Badge tone="clay">decide</Badge>}</span> },
            { key: "entities", label: "Contents", render: (r) => <span className="text-xs text-muted-foreground">{Object.entries(r.entities as Record<string, number>).map(([k, v]) => `${v} ${k.toLowerCase()}`).join(", ")}</span> },
            { key: "levels", label: "Numbers found", render: (r) => r.level_range ? `${r.numeric_texts} · ${fmt(r.level_range[0], 2)}–${fmt(r.level_range[1], 2)}` : "–" },
            { key: "role", label: "Role", render: (r) => (
              <Select aria-label={`Role of ${r.name}`} className="h-10 min-w-[11rem]" value={roles[r.name] ?? ""}
                onChange={(e) => setRoles({ ...roles, [r.name]: e.target.value })}>
                {ROLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </Select>
            ) },
          ]} />

          <div className="mt-8 grid gap-8 lg:grid-cols-2">
            <Card shape={4}>
              <CardTitle eyebrow="Settings" title="How to read it" />
              <div className="grid gap-5 sm:grid-cols-2">
                <Field label="Drawing units to metres" hint={`Header units: ${inv.insunits}`}>{(id) => <Input id={id} value={scale} onChange={(e) => setScale(e.target.value)} inputMode="decimal" />}</Field>
                <Field label="Stated park area (m²)" hint="Optional: checked against the boundary.">{(id) => <Input id={id} value={area} onChange={(e) => setArea(e.target.value)} inputMode="decimal" />}</Field>
              </div>
              <div className="mt-5">
                <Chip checked={contoursInSurface} onChange={setContoursInSurface}>Use contours in the surface</Chip>
                <p className="mt-2 pl-1 text-xs text-muted-foreground">Turn off when the contours were drawn from the spot levels: they are then used only as a check.</p>
              </div>
            </Card>
            <Card shape={5} tone="sand">
              <CardTitle eyebrow="Confirm" title="Build the ground model" />
              {missing.length > 0 && <div className="mb-4"><Notice tone="warn">Still needed: {missing.join(" and ").replace("_", " ")}.</Notice></div>}
              <label className="flex cursor-pointer items-start gap-3 rounded-2xl p-2 hover:bg-white/40">
                <input type="checkbox" className="mt-1 h-5 w-5 accent-[rgb(var(--color-primary))]" checked={checked} onChange={(e) => setChecked(e.target.checked)} />
                <span className="text-sm">I have checked every role against the drawing.</span>
              </label>
              <Button className="mt-4" onClick={doImport} disabled={!checked || missing.length > 0} busy={job.running?.startsWith("Building")}><Upload size={18} /> Import survey</Button>
            </Card>
          </div>
        </section>
      )}

      {qc && (
        <section className="mt-16">
          <h2 className="mb-6 text-2xl font-semibold">Quality check</h2>
          <div className="grid gap-8 lg:grid-cols-[1fr_1.3fr]">
            <div className="space-y-3">
              {(qc.issues as string[]).length === 0 ? <Notice title="No issues found">The surface agrees with the survey.</Notice> :
                (qc.issues as string[]).map((i) => <Notice key={i} tone="warn">{i}</Notice>)}
            </div>
            <figure className="overflow-hidden rounded-[2rem] rounded-tr-[4rem] border-4 border-white shadow-float">
              <img src={`${api.fileUrl(pid!, "terrain/qc.png")}&v=${stamp}`} alt="Ground model with survey contours, spot levels and outliers" className="w-full" />
            </figure>
          </div>
        </section>
      )}
      {!inv && !qc && <div className="mt-16"><Empty title="No drawing read yet">Choose the survey DXF and press Read layers.</Empty></div>}
    </div>
  );
}
