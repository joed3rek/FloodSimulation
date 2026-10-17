/** Tailwind reads every colour, shadow and shape from src/styles/tokens.css. */
const c = (name) => `rgb(var(--color-${name}) / <alpha-value>)`;

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: c("background"),
        foreground: c("foreground"),
        card: c("card"),
        primary: { DEFAULT: c("primary"), foreground: c("primary-foreground") },
        secondary: { DEFAULT: c("secondary"), foreground: c("secondary-foreground"), ink: c("clay-ink") },
        accent: { DEFAULT: c("accent"), foreground: c("accent-foreground") },
        muted: { DEFAULT: c("muted"), foreground: c("muted-foreground") },
        border: c("border"),
        destructive: c("destructive"),
        water: { DEFAULT: c("water"), deep: c("water-deep") },
        night: c("night"),
      },
      fontFamily: {
        display: ['"Fraunces Variable"', "Georgia", "serif"],
        sans: ['"Nunito Variable"', "Nunito", "system-ui", "sans-serif"],
      },
      // 1.25 scale
      fontSize: {
        xs: ["0.8rem", "1.2rem"],
        sm: ["0.875rem", "1.35rem"],
        base: ["1rem", "1.6rem"],
        lg: ["1.25rem", "1.8rem"],
        xl: ["1.563rem", "2.1rem"],
        "2xl": ["1.953rem", "2.4rem"],
        "3xl": ["2.441rem", "2.8rem"],
        "4xl": ["3.052rem", "3.3rem"],
      },
      boxShadow: {
        soft: "var(--shadow-soft)",
        "soft-hover": "var(--shadow-soft-hover)",
        float: "var(--shadow-float)",
        lift: "var(--shadow-lift)",
      },
      borderRadius: {
        blob: "var(--blob-1)",
        "blob-2": "var(--blob-2)",
        "blob-3": "var(--blob-3)",
        "blob-4": "var(--blob-4)",
      },
      transitionTimingFunction: { natural: "var(--ease-natural)" },
      keyframes: {
        "drift-a": { "0%, 100%": { transform: "translateY(0) rotate(0)" }, "50%": { transform: "translateY(-22px) rotate(2deg)" } },
        "drift-b": { "0%, 100%": { transform: "translateY(0) rotate(0)" }, "50%": { transform: "translateY(20px) rotate(-2deg)" } },
      },
      animation: { "drift-a": "drift-a 12s ease-in-out infinite", "drift-b": "drift-b 14s ease-in-out infinite" },
    },
  },
  plugins: [],
};
