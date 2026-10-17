import { ButtonHTMLAttributes, forwardRef } from "react";
import { Loader2 } from "lucide-react";
import { cx } from "./cx";

type Variant = "primary" | "clay" | "outline" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-primary text-primary-foreground shadow-soft hover:shadow-soft-hover",
  clay: "bg-secondary text-secondary-foreground shadow-float hover:shadow-soft-hover",
  outline: "border-2 border-secondary text-secondary bg-transparent hover:bg-secondary/10",
  ghost: "text-primary bg-transparent hover:bg-primary/10",
  danger: "border-2 border-destructive/60 text-destructive hover:bg-destructive/10",
};
const SIZES: Record<Size, string> = { sm: "h-10 px-5 text-sm", md: "h-12 px-8 text-base", lg: "h-14 px-10 text-lg" };

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  busy?: boolean;
}

/** Pill button that lifts like a river stone; presses down on click. */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", busy, className, children, disabled, ...rest }, ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || busy}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-full font-bold whitespace-nowrap",
        "transition-all duration-300 ease-natural hover:scale-105 active:scale-95",
        "disabled:opacity-50 disabled:hover:scale-100 disabled:cursor-not-allowed",
        VARIANTS[variant], SIZES[size], className,
      )}
      {...rest}
    >
      {busy && <Loader2 size={18} className="animate-spin" aria-hidden />}
      {children}
    </button>
  );
});
