import { CheckCircle2, CircleDashed, Droplets, FileStack, Layers, Mountain, SlidersHorizontal, Sprout } from "lucide-react";
import { useProject } from "../lib/project";
import { Card } from "../components/ui/Card";
import { Badge, IconBox, PageHeader, Stat } from "../components/ui/Bits";
import { cx } from "../components/ui/cx";

export function Overview() {
  const { info } = useProject();
  if (!info) return null;
  const options = (info.options as string[]).filter((o) => o !== "baseline");
  const steps = [
    { page: "survey", icon: Mountain, title: "Survey", done: info.has_terrain, text: "Import the drawing, check the layers, build the ground model." },
    { page: "parameters", icon: SlidersHorizontal, title: "Soils, rain and targets", done: info.has_soils && info.has_rainfall, text: "Infiltration per zone, rainfall table, area budget and storms." },
    { page: "existing", icon: Layers, title: "Existing site", done: info.has_baseline, text: "Where water flows and leaves today, for every storm." },
    { page: "options", icon: Sprout, title: "Design options", done: options.length > 0, text: "Generate or optimise ponds, swales, rain gardens and wells." },
    { page: "storm", icon: Droplets, title: "Storm viewer", done: false, text: "Watch a storm on the existing and proposed ground." },
    { page: "deliverables", icon: FileStack, title: "Deliverables", done: false, text: "Report, drawings, Rhino file, calibration." },
  ];
  const next = steps.find((s) => !s.done);

  return (
    <div>
      <PageHeader eyebrow="Project" title={info.name}>
        <span className="text-sm">{info.path}</span>
      </PageHeader>

      <Card shape={2} className="mb-16 grid grid-cols-2 gap-8 md:grid-cols-4 md:gap-12">
        <Stat label="Design options" value={options.length} />
        <Stat label="Defaults to confirm" value={info.unconfirmed_parameters} note="assumed until you confirm them" />
        <Stat label="Storms analysed" value={(info.return_periods as number[]).length} note={(info.return_periods as number[]).map((r) => `${r}`).join(" · ") + " yr"} />
        <div>
          <p className="text-sm font-semibold text-muted-foreground">Model status</p>
          <p className="mt-3"><Badge tone={info.calibration === "uncalibrated" ? "clay" : "moss"}>{info.calibration === "uncalibrated" ? "uncalibrated" : "calibrated"}</Badge></p>
          <p className="mt-2 text-xs text-muted-foreground">CRS {info.crs}</p>
        </div>
      </Card>

      <h2 className="mb-2 text-2xl font-semibold">The way through</h2>
      <p className="mb-10 text-muted-foreground">{next ? <>Next: <a className="font-semibold text-primary underline-offset-4 hover:underline" href={`#/${next.page}`}>{next.title.toLowerCase()}</a>.</> : "Every step has results."}</p>

      <div className="relative">
        {/* hand-drawn connector behind the steps (large screens) */}
        <svg aria-hidden className="pointer-events-none absolute inset-x-0 top-14 hidden h-40 w-full lg:block" viewBox="0 0 1000 160" preserveAspectRatio="none">
          <path d="M60 40 C 220 -10, 300 120, 500 70 S 820 10, 940 110" fill="none" stroke="rgb(var(--color-secondary))" strokeOpacity="0.45"
            strokeWidth="2" strokeDasharray="6 10" strokeLinecap="round" />
        </svg>
        <ol className="relative grid gap-8 md:grid-cols-2 lg:grid-cols-3">
          {steps.map((s, i) => (
            <li key={s.page}>
              <a href={`#/${s.page}`} className="group block">
                <Card shape={i} lift className={cx("h-full", s === next && "ring-2 ring-primary/30")}>
                  <div className="flex items-start gap-4">
                    <IconBox icon={s.icon} active={s.done} />
                    <div className="min-w-0">
                      <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-muted-foreground">
                        Step {i + 1} {s.done ? <CheckCircle2 size={15} className="text-primary" aria-label="done" /> : <CircleDashed size={15} aria-label="to do" />}
                      </p>
                      <h3 className="mt-1 text-lg font-semibold">{s.title}</h3>
                      <p className="mt-1 text-sm text-muted-foreground">{s.text}</p>
                    </div>
                  </div>
                </Card>
              </a>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}
