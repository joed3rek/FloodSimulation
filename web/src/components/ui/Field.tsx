import { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, useId } from "react";
import { cx } from "./cx";

const CONTROL =
  "h-12 rounded-full border border-border bg-white/50 px-5 text-sm text-foreground placeholder:text-muted-foreground " +
  "transition-shadow duration-300 focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2";

/** a width class given by the caller replaces the default full width */
const HAS_WIDTH = /(^|\s)(min-)?w-/;

interface FieldProps {
  label: string;
  hint?: ReactNode;
  children: (id: string) => ReactNode;
  className?: string;
}

/** Label + control + hint, wired for screen readers. */
export function Field({ label, hint, children, className }: FieldProps) {
  const id = useId();
  return (
    <div className={cx("flex flex-col gap-1.5", className)}>
      <label htmlFor={id} className="pl-4 text-sm font-semibold text-accent-foreground">{label}</label>
      {children(id)}
      {hint && <p id={`${id}-hint`} className="pl-4 text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cx(CONTROL, !HAS_WIDTH.test(className ?? "") && "w-full", className)} {...rest} />;
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cx(CONTROL, !HAS_WIDTH.test(className ?? "") && "w-full", "appearance-none bg-[length:12px] bg-[right_1.25rem_center] bg-no-repeat pr-10", className)}
      style={{ backgroundImage: "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 8'><path d='M1 1.5l5 5 5-5' fill='none' stroke='%235D7052' stroke-width='1.6' stroke-linecap='round'/></svg>\")" }}
      {...rest}>
      {children}
    </select>
  );
}

/** Rounded check chip (multi-choice). */
export function Chip({ checked, onChange, children }: { checked: boolean; onChange: (v: boolean) => void; children: ReactNode }) {
  return (
    <button type="button" role="checkbox" aria-checked={checked} onClick={() => onChange(!checked)}
      className={cx(
        "h-10 rounded-full border-2 px-5 text-sm font-semibold transition-all duration-300 ease-natural active:scale-95",
        checked ? "border-primary bg-primary text-primary-foreground shadow-soft" : "border-border bg-white/50 text-accent-foreground hover:border-primary/50",
      )}>
      {children}
    </button>
  );
}

/** Pill segmented control. */
export function Segmented<T extends string | number>({ value, options, onChange, label }: {
  value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex flex-wrap gap-1 rounded-full border border-border/60 bg-muted/60 p-1">
      {options.map((o) => (
        <button key={String(o.value)} type="button" role="radio" aria-checked={o.value === value} onClick={() => onChange(o.value)}
          className={cx("h-10 rounded-full px-4 text-sm font-semibold transition-all duration-300 ease-natural",
            o.value === value ? "bg-card text-primary shadow-soft" : "text-muted-foreground hover:text-foreground")}>
          {o.label}
        </button>
      ))}
    </div>
  );
}
