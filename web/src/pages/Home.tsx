import { useState } from "react";
import { ArrowRight, FolderOpen, Plus, Sprout } from "lucide-react";
import { recentProjects, useProject } from "../lib/project";
import { go } from "../lib/route";
import { PathField } from "../components/FilePicker";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Blob, Notice } from "../components/ui/Bits";
import { Field, Input } from "../components/ui/Field";

export function Home() {
  const { open, engineUp } = useProject();
  const [path, setPath] = useState("");
  const [newPath, setNewPath] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const recent = recentProjects();

  const doOpen = async (p: string, create = false) => {
    setBusy(true); setErr(null);
    try { await open(p, create); go("overview"); } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  };

  return (
    <div className="grid gap-16 lg:grid-cols-2 lg:items-center">
      <section className="relative">
        <Blob shape={2} className="-left-10 top-10 h-72 w-72 bg-accent/70" />
        <p className="relative mb-4 text-xs font-bold uppercase tracking-[0.18em] text-secondary-ink">Habitat Collective · sponge parks</p>
        <h1 className="relative text-4xl font-bold leading-[1.05] md:text-[4.2rem]">
          Let the park <em className="font-semibold not-italic text-primary">hold the rain.</em>
        </h1>
        <p className="relative mt-6 max-w-xl text-lg text-muted-foreground">
          Read the survey, see where water goes today, shape ponds, swales and rain gardens into the ground, and
          check every storm from the 2-year to the 100-year in SWMM.
        </p>
        <div className="relative mt-8">
          {engineUp === false && (
            <Notice tone="warn" title="The engine is not running">
              Start it in a terminal with <code className="rounded bg-muted px-1.5">spongepark serve</code>, then reload this page.
            </Notice>
          )}
        </div>
      </section>

      <div className="relative space-y-8">
        <Card shape={0} className="space-y-5">
          <h2 className="flex items-center gap-3 text-xl font-semibold"><FolderOpen className="text-primary" /> Open a park</h2>
          <PathField value={path} onChange={setPath} ext=".sponge" title="Choose a .sponge project" placeholder="D:\…\park.sponge" />
          <Button onClick={() => doOpen(path)} disabled={!path} busy={busy}>Open <ArrowRight size={18} /></Button>
          {recent.length > 0 && (
            <div>
              <p className="mb-2 pl-1 text-sm font-semibold text-muted-foreground">Recently opened</p>
              <ul className="space-y-1">
                {recent.map((r) => (
                  <li key={r}>
                    <button onClick={() => doOpen(r)} className="group flex w-full items-center gap-3 rounded-2xl px-3 py-2.5 text-left transition-colors hover:bg-accent/40">
                      <span className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/10 text-primary transition-colors group-hover:bg-primary group-hover:text-primary-foreground"><Sprout size={16} /></span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-semibold">{r.split(/[\\/]/).pop()?.replace(".sponge", "")}</span>
                        <span className="block truncate text-xs text-muted-foreground">{r}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>

        <Card shape={1} tone="stone" className="space-y-4">
          <h2 className="flex items-center gap-3 text-xl font-semibold"><Plus className="text-secondary" /> Start a new park</h2>
          <Field label="Save the new project as" hint="A .sponge file holds everything: survey, parameters, options and results.">
            {(id) => <Input id={id} value={newPath} onChange={(e) => setNewPath(e.target.value)} placeholder="D:\Parks\new-park.sponge" />}
          </Field>
          <Button variant="clay" onClick={() => doOpen(newPath.endsWith(".sponge") ? newPath : newPath + ".sponge", true)} disabled={!newPath} busy={busy}>
            Create project
          </Button>
        </Card>
        {err && <Notice tone="error">{err}</Notice>}
      </div>
    </div>
  );
}
