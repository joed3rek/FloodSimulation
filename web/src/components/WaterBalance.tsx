// Where the rain goes, per storm: one bar per return period, shares of rainfall (SWMM water balance).
import { fmt, Json } from "../lib/api";

const TERMS = [
  { label: "Soaks into the ground", color: "rgb(var(--color-primary))", get: (w: Json) => w.infiltration_surfaces_m3 },
  { label: "Soaks in through NbS", color: "rgb(var(--color-primary) / 0.55)", get: (w: Json) => w.infiltration_nbs_m3 + (w.recharge_m3 || 0) },
  { label: "Held on the ground / in NbS", color: "rgb(var(--color-accent-foreground) / 0.35)", get: (w: Json) =>
      w.storage_change_surface_m3 + w.storage_change_lid_m3 + w.storage_change_nodes_m3 + w.interception_m3 + w.evaporation_m3 },
  { label: "Released slowly (outlet)", color: "rgb(var(--color-secondary))", get: (w: Json) => w.outflow_controlled_m3 },
  { label: "Leaves the site", color: "rgb(var(--color-water))", get: (w: Json) => w.outflow_runoff_m3 + w.outflow_overflow_m3 + w.flooding_m3 },
];

export function WaterBalance({ summary }: { summary: Json }) {
  const rps = Object.keys(summary.return_periods).sort((a, b) => +a - +b);
  return (
    <figure>
      <div className="space-y-3">
        {rps.map((rp) => {
          const w = summary.return_periods[rp].water_balance;
          const rain = w.rainfall_total_m3 || 1;
          const parts = TERMS.map((t) => Math.max(0, t.get(w) || 0) / rain);
          return (
            <div key={rp} className="grid grid-cols-[4.5rem_1fr_4.5rem] items-center gap-3">
              <span className="text-sm font-semibold tabular">{rp}-year</span>
              <div className="flex h-7 overflow-hidden rounded-full bg-muted" role="img"
                aria-label={`${rp}-year storm: ` + TERMS.map((t, i) => `${t.label} ${Math.round(parts[i] * 100)} %`).join(", ")}>
                {parts.map((p, i) => p > 0.002 && (
                  <span key={i} title={`${TERMS[i].label}: ${Math.round(p * 100)} %`} className="h-full border-r-2 border-card last:border-r-0 transition-[width] duration-700 ease-natural"
                    style={{ width: `${p * 100}%`, background: TERMS[i].color }} />
                ))}
              </div>
              <span className="text-right text-xs text-muted-foreground tabular">{fmt(w.rainfall_total_m3, 0)} m³</span>
            </div>
          );
        })}
      </div>
      <figcaption className="mt-5 flex flex-wrap gap-x-5 gap-y-2 text-xs text-accent-foreground">
        {TERMS.map((t) => (
          <span key={t.label} className="inline-flex items-center gap-2">
            <span className="h-3 w-3 rounded-full" style={{ background: t.color }} aria-hidden />{t.label}
          </span>
        ))}
      </figcaption>
    </figure>
  );
}
