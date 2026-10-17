// Small shared pieces: badges, notices, stats, icon boxes, blobs, page header, data table, job status.
import { ReactNode } from "react";
import { AlertTriangle, Info, Leaf, Loader2, LucideIcon } from "lucide-react";
import { Json } from "../../lib/api";
import { cx } from "./cx";

export function Badge({ tone = "stone", children }: { tone?: "moss" | "clay" | "stone" | "sienna" | "water"; children: ReactNode }) {
  const t = {
    moss: "bg-primary/10 text-primary border-primary/25",
    clay: "bg-secondary/15 text-secondary-ink border-secondary/30",
    stone: "bg-muted text-accent-foreground border-border",
    sienna: "bg-destructive/10 text-destructive border-destructive/25",
    water: "bg-water/10 text-water-deep border-water/25",
  }[tone];
  return <span className={cx("inline-flex items-center rounded-full border px-3 py-0.5 text-xs font-bold", t)}>{children}</span>;
}

/** Where a parameter value came from. */
export function SourceBadge({ source, confirmed }: { source: string; confirmed?: boolean }) {
  const tone = source === "site measured" ? "moss" : source === "user" ? "water" : source === "literature" ? "stone" : "clay";
  return <span className="inline-flex items-center gap-1.5"><Badge tone={tone}>{source}</Badge>
    {confirmed === false && <span className="text-xs font-semibold text-secondary-ink">unconfirmed</span>}</span>;
}

export function Notice({ tone = "info", title, children }: { tone?: "info" | "warn" | "error"; title?: string; children: ReactNode }) {
  const s = {
    info: { box: "bg-primary/[0.07] border-primary/20", icon: <Info size={20} className="text-primary" aria-hidden /> },
    warn: { box: "bg-secondary/10 border-secondary/30", icon: <AlertTriangle size={20} className="text-secondary" aria-hidden /> },
    error: { box: "bg-destructive/10 border-destructive/30", icon: <AlertTriangle size={20} className="text-destructive" aria-hidden /> },
  }[tone];
  return (
    <div role={tone === "error" ? "alert" : "note"} className={cx("flex gap-3 rounded-3xl rounded-tl-lg border p-4 text-sm", s.box)}>
      <span className="mt-0.5 shrink-0">{s.icon}</span>
      <div>{title && <p className="font-bold">{title}</p>}<div className="text-accent-foreground">{children}</div></div>
    </div>
  );
}

export function IconBox({ icon: Icon = Leaf, active }: { icon?: LucideIcon; active?: boolean }) {
  return (
    <span className={cx("flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl transition-colors duration-500",
      active ? "bg-primary text-primary-foreground" : "bg-primary/10 text-primary group-hover:bg-primary group-hover:text-primary-foreground")}>
      <Icon size={26} />
    </span>
  );
}

export function Stat({ label, value, unit, note }: { label: string; value: ReactNode; unit?: string; note?: ReactNode }) {
  return (
    <div className="group">
      <p className="text-sm font-semibold text-muted-foreground">{label}</p>
      <p className="mt-1 font-display text-3xl font-semibold tabular transition-transform duration-500 ease-natural group-hover:scale-105 origin-left">
        {value}{unit && <span className="ml-1 font-sans text-base font-semibold text-muted-foreground">{unit}</span>}
      </p>
      {note && <p className="mt-1 text-xs text-muted-foreground">{note}</p>}
    </div>
  );
}

/** Ambient colour wash behind a section. */
export function Blob({ className, shape = 1 }: { className?: string; shape?: 1 | 2 | 3 | 4 }) {
  const r = { 1: "rounded-blob", 2: "rounded-blob-2", 3: "rounded-blob-3", 4: "rounded-blob-4" }[shape];
  return <div aria-hidden className={cx("pointer-events-none absolute blur-3xl", r, className)} />;
}

export function PageHeader({ eyebrow, title, children, action }: { eyebrow: string; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <header className="relative mb-10 flex flex-wrap items-end justify-between gap-6">
      <div className="max-w-2xl">
        <p className="mb-2 text-xs font-bold uppercase tracking-[0.18em] text-secondary-ink">{eyebrow}</p>
        <h1 className="text-3xl font-bold md:text-4xl">{title}</h1>
        {children && <div className="mt-3 text-base text-muted-foreground">{children}</div>}
      </div>
      {action}
    </header>
  );
}

export interface Column { key: string; label: ReactNode; align?: "right"; render?: (row: Json) => ReactNode; className?: string }

export function DataTable({ columns, rows, caption, dense }: {
  columns: Column[]; rows: Json[]; caption?: string; dense?: boolean;
}) {
  return (
    <div className="scrollbar-soft overflow-x-auto rounded-3xl border border-border/60 bg-white/40">
      <table className="w-full border-collapse text-sm tabular">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          <tr className="bg-muted/70">
            {columns.map((c) => (
              <th key={c.key} scope="col" className={cx("px-4 py-3 text-left text-xs font-bold uppercase tracking-wider text-muted-foreground", c.align === "right" && "text-right")}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-border/50 transition-colors hover:bg-accent/20">
              {columns.map((c) => (
                <td key={c.key} className={cx(dense ? "px-4 py-2" : "px-4 py-3", c.align === "right" && "text-right", c.className)}>
                  {c.render ? c.render(r) : String(r[c.key] ?? "–")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function JobStatus({ running, error }: { running: string | null; error: string | null }) {
  if (running)
    return (
      <p role="status" className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-4 py-2 text-sm font-semibold text-primary">
        <Loader2 size={16} className="animate-spin" aria-hidden /> {running}
      </p>
    );
  if (error) return <Notice tone="error" title="The engine reported a problem">{error}</Notice>;
  return null;
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="relative overflow-hidden rounded-[2rem] rounded-tr-[5rem] border border-dashed border-border bg-muted/30 p-10 text-center">
      <Blob shape={2} className="-right-10 -top-10 h-40 w-40 bg-accent/60" />
      <p className="relative font-display text-xl font-semibold">{title}</p>
      {children && <div className="relative mx-auto mt-2 max-w-md text-sm text-muted-foreground">{children}</div>}
    </div>
  );
}
