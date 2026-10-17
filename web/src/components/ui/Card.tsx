import { HTMLAttributes } from "react";
import { CARD_SHAPES, cx } from "./cx";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /** index into the organic shape set; neighbours should differ */
  shape?: number;
  lift?: boolean;
  tone?: "paper" | "stone" | "sand" | "moss";
}

const TONES = {
  paper: "bg-card border-border/50",
  stone: "bg-muted/60 border-border/40",
  sand: "bg-accent/40 border-accent",
  moss: "bg-primary text-primary-foreground border-primary",
};

export function Card({ shape = 3, lift, tone = "paper", className, ...rest }: CardProps) {
  return (
    <div
      className={cx(
        "relative border shadow-soft p-6 sm:p-8",
        CARD_SHAPES[shape % CARD_SHAPES.length], TONES[tone],
        lift && "transition-all duration-500 ease-natural hover:-translate-y-1 hover:shadow-lift",
        className,
      )}
      {...rest}
    />
  );
}

export function CardTitle({ eyebrow, title, action }: { eyebrow?: string; title: string; action?: React.ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        {eyebrow && <p className="text-xs font-bold uppercase tracking-[0.14em] text-secondary-ink">{eyebrow}</p>}
        <h3 className="text-xl font-semibold">{title}</h3>
      </div>
      {action}
    </div>
  );
}
