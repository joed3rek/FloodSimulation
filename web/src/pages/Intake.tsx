// Survey intake: the engine has read the drawing; every layer gets linked to a standard title,
// unclear ones are asked, then the drawing is cleaned and the ground model built.
import { useEffect, useMemo, useState } from "react";
import { ArrowRight, Check, CircleHelp, Layers, Sparkles, Wand2 } from "lucide-react";
import { api, Json } from "../lib/api";
import { useProject } from "../lib/project";
import { go } from "../lib/route";
import { Button } from "../components/ui/Button";
import { Card, CardTitle } from "../components/ui/Card";
import { Badge, Empty, JobStatus, Notice, PageHeader } from "../components/ui/Bits";
import { Chip, Field, Input, Select } from "../components/ui/Field";
import { cx } from "../components/ui/cx";

const KEY = "spongepark.intake";
export const saveIntake = (d: unknown) => { try { sessionStorage.setItem(KEY, JSON.stringify(d)); } catch { /* large drawings: keep in memory only */ } (window as Json).__intake = d; };
const loadIntake = (): Json | null => (window as Json).__intake ?? (() => { try { return JSON.parse(sessionStorage.getItem(KEY) || "null"); } catch { return null; } })();

const preview = (survey: string, layer?: string) => `/intake/preview?path=${encodeURIComponent(survey)}${layer ? `&layer=${encodeURIComponent(layer)}` : ""}`;

function contents(l: Json) {
  const parts = Object.entries(l.entities as Record<string, number>).map(([k, v]) => `${v} ${k.toLowerCase()}${v > 1 ? "s" : ""}`);
  if (l.level_range) parts.push(`numbers ${l.level_range[0]}–${l.level_range[1]}`);
  return parts.join(" · ");
}

function ChoiceSelect({ value, choices, onChange, label }: { value: string | undefined; choices: Json[]; onChange: (v: string) => void; label: string }) {
  const groups = useMemo(() => Array.from(new Set(choices.map((c) => c.group))), [choices]);
  return (
    <Select aria-label={label} className="h-10 min-w-[14rem]" value={value ?? "?"} onChange={(e) => onChange(e.target.value)}>
      {value === undefined && <option value="?" disabled>Choose what it is…</option>}
      {groups.map((g) => (
        <optgroup key={g} label={g}>
          {choices.filter((c) => c.group === g).map((c) => <option key={c.name || "none"} value={c.name}>{c.title}</option>)}
        </optgroup>
      ))}
    </Select>
  );
}

export function Intake() {
  const { open } = useProject();
  const [data] = useState<Json | null>(loadIntake);
  const [links, setLinks] = useState<Record<string, string | undefined>>({});
  const [focus, setFocus] = useState<string | undefined>();
  const [projectPath, setProjectPath] = useState("");
  const [area, setArea] = useState("");
  const [scale, setScale] = useState("1");
  const [contoursIn, setContoursIn] = useState(false);   // false: the engine decides
  const [running, setRunning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<Json | null>(null);

  useEffect(() => {
    if (!data) return;
    const init: Record<string, string | undefined> = {};
    for (const l of data.layers) init[l.layer] = l.question ? undefined : l.proposed;
    setLinks(init);
    setProjectPath(data.survey.replace(/\.(dxf|dwg)$/i, "").replace(/ /g, "_") + ".sponge");
  }, [data]);

  if (!data) return <Empty title="No drawing yet"><a className="font-semibold text-primary" href="#/">Import a survey</a> to start.</Empty>;

  const questions: Json[] = data.layers.filter((l: Json) => l.question);
  const linked: Json[] = data.layers.filter((l: Json) => !l.question);
  const answered = questions.filter((q) => links[q.layer] !== undefined).length;
  const byName = Object.fromEntries((data.choices as Json[]).map((c) => [c.name, c]));
  const levelsLinked = Object.values(links).some((v) => v === "SP-LVL-SPOT" || v === "SP-CONT-MAJOR" || v === "SP-CONT-MINOR");
  const ready = answered === questions.length && levelsLinked;

  const finish = async () => {
    setError(null); setRunning("Cleaning the drawing and building the ground");
    try {
      const r = await api.job("POST", "/intake/finish", {
        survey: data.survey, links, project_path: projectPath, park_area_m2: area ? Number(area) : null,
        contours_in_surface: contoursIn ? true : "auto", units_scale_to_m: Number(scale) || 1,
      }, (s) => setRunning(`Cleaning the drawing and building the ground · ${s}`));
      setDone(r);
      await open(r.project);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setRunning(null); }
  };

  return (
    <div>
      <PageHeader eyebrow="Survey intake" title={data.name}>
        The engine read <b className="text-foreground">{data.layers.length} layers</b>. It linked {linked.length} of them to the standard
        on its own{questions.length ? <> and has <b className="text-foreground">{questions.length} question{questions.length > 1 ? "s" : ""}</b> for you</> : ""}.
        Nothing is changed in your file: a cleaned copy is written next to it.
      </PageHeader>

      {/* questions */}
      {questions.length > 0 && (
        <section className="mb-20">
          <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
            <h2 className="flex items-center gap-3 text-2xl font-semibold"><CircleHelp className="text-secondary" /> What is on these layers?</h2>
            <Badge tone={answered === questions.length ? "moss" : "clay"}>{answered} of {questions.length} answered</Badge>
          </div>
          <ol className="grid gap-8 lg:grid-cols-2">
            {questions.map((q, i) => {
              const chosen = links[q.layer];
              const quick: Json[] = q.question.kind === "unclear" ? q.question.answers
                : q.question.kind === "confirm" ? [{ name: q.proposed, title: `Yes, ${byName[q.proposed]?.title.toLowerCase()}` }, { name: "", title: "No, leave it out" }]
                : [{ name: "", title: "Not needed" }];
              return (
                <li key={q.layer}>
                  <Card shape={i} className={cx("h-full transition-shadow duration-500", chosen !== undefined && "ring-2 ring-primary/30")}>
                    <figure className="-mx-2 -mt-2 mb-5 overflow-hidden rounded-[1.5rem] rounded-tl-[3rem] border-4 border-white bg-background shadow-float">
                      <img src={preview(data.survey, q.layer)} alt={`The drawing with layer ${q.layer} highlighted`} loading="lazy" className="aspect-[4/3] w-full object-cover" />
                    </figure>
                    <p className="text-xs font-bold uppercase tracking-[0.14em] text-secondary-ink">Layer · highlighted in clay</p>
                    <h3 className="mt-1 font-mono text-lg font-semibold">{q.layer}</h3>
                    <p className="mt-1 text-xs text-muted-foreground">{contents(q)}</p>
                    <p className="mt-4 text-base font-semibold">{q.question.ask}</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {quick.map((a) => <Chip key={a.name + a.title} checked={chosen === a.name} onChange={() => setLinks({ ...links, [q.layer]: a.name })}>{a.title}</Chip>)}
                    </div>
                    <div className="mt-3 flex items-center gap-3">
                      <span className="text-sm text-muted-foreground">or</span>
                      <ChoiceSelect label={`What is on ${q.layer}`} value={quick.some((a) => a.name === chosen) ? undefined : chosen} choices={data.choices}
                        onChange={(v) => setLinks({ ...links, [q.layer]: v })} />
                    </div>
                  </Card>
                </li>
              );
            })}
          </ol>
        </section>
      )}

      {/* everything the engine linked */}
      <section className="mb-20 grid gap-10 lg:grid-cols-[1.25fr_1fr]">
        <div>
          <h2 className="mb-2 flex items-center gap-3 text-2xl font-semibold"><Sparkles className="text-primary" /> Linked by the engine</h2>
          <p className="mb-6 text-sm text-muted-foreground">Hover a layer to see it in the drawing. Change any link that is wrong.</p>
          <ul className="divide-y divide-border/60 overflow-hidden rounded-[2rem] rounded-tr-[4rem] border border-border/60 bg-white/50">
            {linked.map((l) => (
              <li key={l.layer} onMouseEnter={() => setFocus(l.layer)} onFocus={() => setFocus(l.layer)}
                className={cx("flex flex-wrap items-center gap-3 px-5 py-3 transition-colors", focus === l.layer && "bg-accent/30")}>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-mono text-sm font-semibold">{l.layer}</p>
                  <p className="truncate text-xs text-muted-foreground">{contents(l)}</p>
                </div>
                <ArrowRight size={16} className="text-muted-foreground" aria-hidden />
                <ChoiceSelect label={`Link for ${l.layer}`} value={links[l.layer]} choices={data.choices} onChange={(v) => setLinks({ ...links, [l.layer]: v })} />
              </li>
            ))}
          </ul>
        </div>
        <div className="lg:sticky lg:top-28 lg:self-start">
          <figure className="overflow-hidden rounded-[2rem] rounded-bl-[4rem] border-4 border-white bg-background shadow-float transition-transform duration-700 lg:rotate-[1deg] hover:rotate-0">
            <img src={preview(data.survey, focus)} alt={focus ? `Layer ${focus} highlighted` : "The whole drawing"} className="w-full" />
          </figure>
          <p className="mt-3 text-center text-sm text-muted-foreground">
            {focus ? <>Highlighted: <b className="font-mono text-foreground">{focus}</b> → {byName[links[focus] ?? ""]?.title ?? "not needed"}</> : "The whole drawing"}
          </p>
        </div>
      </section>

      {/* finish */}
      <section className="grid gap-8 lg:grid-cols-[1fr_1.2fr]">
        <Card shape={4} tone="stone">
          <CardTitle eyebrow="Reading" title="How to read it" />
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Drawing units to metres" hint={`Header says: ${data.units}`}>{(id) => <Input id={id} value={scale} onChange={(e) => setScale(e.target.value)} inputMode="decimal" />}</Field>
            <Field label="Park area (m²), optional" hint="Checked against the boundary.">{(id) => <Input id={id} value={area} onChange={(e) => setArea(e.target.value)} inputMode="decimal" />}</Field>
          </div>
          <div className="mt-5">
            <Chip checked={contoursIn} onChange={setContoursIn}>Always use the drawn contours</Chip>
            <p className="mt-2 pl-1 text-xs text-muted-foreground">Turn off when the surveyor drew the contours from the spot levels; the quality check will tell you.</p>
          </div>
        </Card>
        <Card shape={2} tone="sand">
          <CardTitle eyebrow="Done" title="Clean the drawing and build the ground" />
          <Field label="Save the project as">{(id) => <Input id={id} value={projectPath} onChange={(e) => setProjectPath(e.target.value)} />}</Field>
          {!levelsLinked && <div className="mt-4"><Notice tone="warn">Link at least the spot levels or the contours: the ground is built from them.</Notice></div>}
          {answered < questions.length && <p className="mt-4 text-sm text-secondary-ink">Answer the {questions.length - answered} remaining question{questions.length - answered > 1 ? "s" : ""} first.</p>}
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <Button size="lg" onClick={finish} disabled={!ready || !!running} busy={!!running}><Wand2 size={20} /> Clean and build</Button>
            <JobStatus running={running} error={error} />
          </div>
          {done && (
            <div className="mt-6 space-y-3">
              <Notice title="Ground model built">
                Cleaned drawing: {done.cleaned_drawing}. {done.cleaning.duplicates_removed_total} duplicate objects removed, {done.cleaning.layers_removed.length} old layers merged.
                {done.qc.spot_cross_validation && <> Spot levels agree with the surface to {done.qc.spot_cross_validation.rmse_m.toFixed(3)} m (RMSE).</>}
              </Notice>
              <Button onClick={() => go("survey")}><Layers size={18} /> See the quality check <Check size={16} /></Button>
            </div>
          )}
        </Card>
      </section>
    </div>
  );
}
