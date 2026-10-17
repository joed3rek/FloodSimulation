// Browse the computer's folders through the engine (local only) and pick a file.
import { useEffect, useState } from "react";
import { ArrowUp, File, Folder, X } from "lucide-react";
import { api, Json } from "../lib/api";
import { Button } from "./ui/Button";
import { Input } from "./ui/Field";

interface Props {
  title: string;
  ext: string;               // ".sponge" or ".dxf,.dwg"
  start?: string;
  pickFolder?: boolean;
  onPick: (path: string) => void;
  onClose: () => void;
}

export function FilePicker({ title, ext, start, pickFolder, onPick, onClose }: Props) {
  const [dir, setDir] = useState(start || localStorage.getItem("spongepark.lastdir") || "");
  const [data, setData] = useState<Json | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.get(`/fs/list?ext=${encodeURIComponent(ext)}${dir ? `&dir=${encodeURIComponent(dir)}` : ""}`)
      .then((d) => { setData(d); setErr(null); try { localStorage.setItem("spongepark.lastdir", d.dir); } catch { /* optional */ } })
      .catch((e) => setErr(String(e.message || e)));
  }, [dir, ext]);

  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/20 p-4 backdrop-blur-sm" onClick={onClose}>
      <div role="dialog" aria-modal aria-label={title} onClick={(e) => e.stopPropagation()}
        className="flex max-h-[80vh] w-full max-w-2xl flex-col rounded-[2rem] rounded-tl-[4rem] border border-border/60 bg-card p-6 shadow-lift">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-xl font-semibold">{title}</h2>
          <button aria-label="Close" onClick={onClose} className="rounded-full p-2 text-muted-foreground hover:bg-muted"><X size={20} /></button>
        </div>
        <div className="mb-3 flex gap-2">
          <Button variant="ghost" size="sm" aria-label="Up one folder" onClick={() => data && setDir(data.parent)}><ArrowUp size={18} /></Button>
          <Input aria-label="Folder" value={data?.dir ?? dir} onChange={(e) => setDir(e.target.value)} />
        </div>
        {err && <p className="mb-2 text-sm text-destructive">{err}</p>}
        <ul className="scrollbar-soft -mx-2 flex-1 overflow-y-auto">
          {data?.items.map((it: Json) => (
            <li key={it.path}>
              <button
                onClick={() => (it.kind === "folder" ? setDir(it.path) : onPick(it.path))}
                className="flex w-full items-center gap-3 rounded-2xl px-3 py-2.5 text-left text-sm transition-colors hover:bg-accent/40">
                {it.kind === "folder" ? <Folder size={18} className="text-secondary" /> : <File size={18} className="text-primary" />}
                <span className="flex-1 truncate">{it.name}</span>
                {it.size != null && <span className="text-xs text-muted-foreground">{(it.size / 1e6).toFixed(1)} MB</span>}
              </button>
            </li>
          ))}
          {data && data.items.length === 0 && <li className="px-3 py-6 text-center text-sm text-muted-foreground">Nothing here with {ext}</li>}
        </ul>
        {pickFolder && data && (
          <div className="mt-4 flex justify-end"><Button onClick={() => onPick(data.dir)}>Use this folder</Button></div>
        )}
      </div>
    </div>
  );
}

/** Text field with a Browse button. */
export function PathField({ value, onChange, ext, title, pickFolder, placeholder }: {
  value: string; onChange: (v: string) => void; ext: string; title: string; pickFolder?: boolean; placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex gap-2">
      <Input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} aria-label={title} />
      <Button variant="outline" size="md" type="button" onClick={() => setOpen(true)}>Browse</Button>
      {open && <FilePicker title={title} ext={ext} pickFolder={pickFolder} start={value ? value.replace(/[\\/][^\\/]*$/, "") : undefined}
        onPick={(p) => { onChange(p); setOpen(false); }} onClose={() => setOpen(false)} />}
    </div>
  );
}
