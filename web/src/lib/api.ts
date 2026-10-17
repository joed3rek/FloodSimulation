// Client for the local engine API (spongepark serve). Every number the app shows comes from here.
/* eslint-disable @typescript-eslint/no-explicit-any */
export type Json = any;

export class ApiError extends Error {}

async function request(method: string, path: string, body?: unknown): Promise<Json> {
  const res = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) throw new ApiError(data?.detail ? String(data.detail) : `${res.status} ${res.statusText}`);
  return data;
}

export const api = {
  get: (path: string) => request("GET", path),
  post: (path: string, body: unknown = {}) => request("POST", path, body),
  put: (path: string, body: unknown = {}) => request("PUT", path, body),

  /** Start an engine job and poll it to the end. onStatus receives elapsed seconds. */
  async job(method: "POST" | "PUT", path: string, body: unknown, onStatus?: (s: string) => void): Promise<Json> {
    const started = await request(method, path, body);
    if (!started?.job) return started;
    const t0 = Date.now();
    for (;;) {
      await new Promise((r) => setTimeout(r, 1000));
      const s = await request("GET", `/jobs/${started.job}`);
      if (s.status === "done") return s.result;
      if (s.status === "error") throw new ApiError(s.error);
      onStatus?.(`${Math.round((Date.now() - t0) / 1000)} s`);
    }
  },

  fileUrl: (pid: string, path: string) => `/projects/${pid}/file?path=${encodeURIComponent(path)}`,

  async fileJson(pid: string, path: string): Promise<Json | null> {
    const res = await fetch(api.fileUrl(pid, path));
    return res.ok ? res.json() : null;
  },
};

export function decodeF32(b64: string): Float32Array {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Float32Array(bytes.buffer);
}

export function decodeF16(b64: string): Float32Array {
  const bin = atob(b64);
  const n = bin.length / 2;
  const out = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const h = bin.charCodeAt(2 * i) | (bin.charCodeAt(2 * i + 1) << 8);
    const s = h & 0x8000 ? -1 : 1, e = (h >> 10) & 0x1f, f = h & 0x3ff;
    out[i] = e === 0 ? s * 2 ** -14 * (f / 1024) : e === 31 ? (f ? NaN : s * Infinity) : s * 2 ** (e - 15) * (1 + f / 1024);
  }
  return out;
}

export const fmt = (v: unknown, nd = 1): string => {
  if (v === null || v === undefined || (typeof v === "number" && !Number.isFinite(v))) return "–";
  if (typeof v === "number") return v.toLocaleString("en-IN", { maximumFractionDigits: nd, minimumFractionDigits: Number.isInteger(v) ? 0 : nd });
  return String(v);
};
