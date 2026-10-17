// Shell: floating pill navigation, ambient blobs, page outlet, honest labels in the footer.
import { useState } from "react";
import { BookOpen, Droplets, FileStack, Layers, LayoutGrid, Menu, Mountain, SlidersHorizontal, Sprout, X } from "lucide-react";
import { useProject } from "./lib/project";
import { go, useRoute } from "./lib/route";
import { Blob } from "./components/ui/Bits";
import { cx } from "./components/ui/cx";
import { Home } from "./pages/Home";
import { Overview } from "./pages/Overview";
import { Survey } from "./pages/Survey";
import { Parameters } from "./pages/Parameters";
import { Existing } from "./pages/Existing";
import { Options } from "./pages/Options";
import { Storm } from "./pages/Storm";
import { Deliverables } from "./pages/Deliverables";

const NAV = [
  { page: "overview", label: "Overview", icon: LayoutGrid },
  { page: "survey", label: "Survey", icon: Mountain },
  { page: "parameters", label: "Targets & parameters", icon: SlidersHorizontal },
  { page: "existing", label: "Existing site", icon: Layers },
  { page: "options", label: "Options", icon: Sprout },
  { page: "storm", label: "Storm viewer", icon: Droplets },
  { page: "deliverables", label: "Deliverables", icon: FileStack },
];

export function App() {
  const { pid, info, close } = useProject();
  const route = useRoute();
  const [menu, setMenu] = useState(false);

  const page = !pid ? <Home /> : ({
    overview: <Overview />, survey: <Survey />, parameters: <Parameters />, existing: <Existing />,
    options: <Options arg={route.arg} />, storm: <Storm arg={route.arg} />, deliverables: <Deliverables />,
  } as Record<string, JSX.Element>)[route.page] ?? <Overview />;

  return (
    <div className="relative flex min-h-screen flex-col overflow-x-hidden">
      <Blob shape={1} className="-left-40 -top-40 h-[32rem] w-[32rem] bg-primary/15" />
      <Blob shape={3} className="-right-32 top-[30rem] h-[28rem] w-[28rem] bg-secondary/15" />

      <div className="sticky top-4 z-40 mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <nav aria-label="Main" className="flex items-center gap-3 rounded-full border border-border/50 bg-white/70 p-2 pr-3 shadow-soft backdrop-blur-md">
          <a href="#/overview" className="flex items-center gap-3 rounded-full pr-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-primary text-primary-foreground"><Sprout size={22} /></span>
            <span className="font-display text-lg font-bold leading-none">Sponge Park</span>
          </a>
          {pid && (
            <ul className="ml-2 hidden flex-1 items-center gap-1 xl:flex">
              {NAV.map((n) => (
                <li key={n.page}>
                  <a href={`#/${n.page}`} aria-current={route.page === n.page ? "page" : undefined}
                    className={cx("rounded-full px-4 py-2.5 text-sm font-semibold transition-colors duration-300",
                      route.page === n.page ? "bg-primary/10 text-primary" : "text-accent-foreground hover:bg-muted")}>
                    {n.label}
                  </a>
                </li>
              ))}
            </ul>
          )}
          <div className="ml-auto flex items-center gap-2">
            {pid && info && (
              <button onClick={() => { close(); go("overview"); }} title="Close project"
                className="hidden items-center gap-2 rounded-full border border-border/60 bg-card px-4 py-2 text-sm font-semibold sm:flex hover:border-destructive/40">
                <BookOpen size={16} className="text-primary" /> {info.name} <X size={14} className="text-muted-foreground" />
              </button>
            )}
            {pid && (
              <button className="rounded-full p-2.5 xl:hidden hover:bg-muted" aria-expanded={menu} aria-label="Menu" onClick={() => setMenu(!menu)}>
                {menu ? <X size={22} /> : <Menu size={22} />}
              </button>
            )}
          </div>
        </nav>
        {menu && pid && (
          <ul className="mt-2 grid gap-1 rounded-[2rem] border border-border/50 bg-white/90 p-3 shadow-float backdrop-blur-md xl:hidden">
            {NAV.map((n) => (
              <li key={n.page}>
                <a href={`#/${n.page}`} onClick={() => setMenu(false)}
                  className="flex items-center gap-3 rounded-2xl px-4 py-3 font-semibold hover:bg-muted">
                  <n.icon size={18} className="text-primary" /> {n.label}
                </a>
              </li>
            ))}
          </ul>
        )}
      </div>

      <main className="relative mx-auto w-full max-w-7xl flex-1 px-4 pb-24 pt-14 sm:px-6 lg:px-8">{page}</main>

      <footer className="relative border-t border-border/60 bg-muted/30">
        <div className="mx-auto flex max-w-7xl flex-wrap gap-x-8 gap-y-2 px-4 py-6 text-xs text-muted-foreground sm:px-6 lg:px-8">
          <span>Volumes and flows: EPA SWMM 5.2, unmodified.</span>
          <span>{info?.calibration === "uncalibrated" || !info ? "Uncalibrated: suitable for scenario comparison, not absolute prediction." : info.calibration}</span>
          <span>Water maps and animations: 2D model, indicative.</span>
        </div>
      </footer>
    </div>
  );
}
