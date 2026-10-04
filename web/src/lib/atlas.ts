/**
 * Browser client for the Moth Atlas API (otoc-echo-v1 only).
 *
 * The API's CORS allowlist only admits http://localhost:3000, so:
 *  - on localhost:3000 (npm run dev) the browser calls api.mothquantum.com directly;
 *  - everywhere else it calls the same-origin proxy at ./api/atlas (Vercel function in web/api/atlas.ts,
 *    or the Vite preview proxy), which forwards to api.mothquantum.com.
 * The key the user types is kept in memory (and sessionStorage only if they tick "remember for this tab")
 * and is sent only in the Authorization header of these requests.
 */
import { fromAtlasResult, type Run } from "./otoc";

export const ATLAS = "https://api.mothquantum.com/api/v1";
const KEY_SLOT = "scrambled.atlasKey";

export type Route = "direct" | "proxy";

export function pickRoute(loc: { host: string; search: string }): Route {
  const forced = new URLSearchParams(loc.search).get("atlas");
  if (forced === "direct" || forced === "proxy") return forced;
  return loc.host === "localhost:3000" ? "direct" : "proxy";
}

export function baseFor(route: Route): string {
  if (route === "direct") return ATLAS;
  const env = (import.meta as { env?: Record<string, string | undefined> }).env;
  return env?.VITE_ATLAS_PROXY || "./api/atlas";
}

let memKey = "";

export const keyStore = {
  get(): string {
    if (memKey) return memKey;
    try {
      return sessionStorage.getItem(KEY_SLOT) ?? "";
    } catch {
      return "";
    }
  },
  set(key: string, remember: boolean) {
    memKey = key.trim();
    try {
      if (remember && memKey) sessionStorage.setItem(KEY_SLOT, memKey);
      else sessionStorage.removeItem(KEY_SLOT);
    } catch {
      /* storage disabled: memory only */
    }
  },
  remembered(): boolean {
    try {
      return !!sessionStorage.getItem(KEY_SLOT);
    } catch {
      return false;
    }
  },
};

export interface OtocParams {
  n_sites: number;
  depth: number;
  theta_x: number;
  theta_zz: number;
  machine: "aer";
  exact: true;
  include_taps: false;
}

export function otocParams(n: number, d: number, txPi: number, tzzPi: number): OtocParams {
  return {
    n_sites: Math.round(n),
    depth: Math.round(d),
    theta_x: txPi * Math.PI,
    theta_zz: tzzPi * Math.PI,
    machine: "aer",
    exact: true,
    include_taps: false,
  };
}

export class AtlasError extends Error {
  constructor(message: string, public status?: number, public cors = false) {
    super(message);
  }
}

type Fetch = typeof fetch;

async function call(fetchFn: Fetch, base: string, key: string, path: string, init: RequestInit = {}) {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
  if (key) headers.Authorization = `Bearer ${key}`;
  if (init.body) headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetchFn(`${base}${path}`, { ...init, headers });
  } catch (e) {
    throw new AtlasError(
      `Network/CORS error reaching ${base}. Atlas only allows browser calls from http://localhost:3000; elsewhere use the proxy. (${(e as Error).message})`,
      undefined,
      true,
    );
  }
  const text = await res.text();
  if (!res.ok) {
    const hint = res.status === 401 ? " (check your API key)" : res.status === 404 && base !== ATLAS ? " (no proxy on this host)" : "";
    throw new AtlasError(`HTTP ${res.status}${hint}: ${text.slice(0, 300)}`, res.status);
  }
  return text ? JSON.parse(text) : null;
}

export interface MeasureOpts {
  route: Route;
  key: string;
  fetchFn?: Fetch;
  signal?: AbortSignal;
  onStatus?: (s: { job_id?: string; status: string; elapsed: number }) => void;
  onSubmitted?: (s: { job_id: string; lent: boolean; remaining?: { ip_hour: number; today: number } }) => void;
  timeoutMs?: number;
  sleep?: (ms: number) => Promise<void>;
}

const defaultSleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/** Submit otoc-echo-v1, poll until done, return the parsed run. */
export async function measureOtoc(params: OtocParams, o: MeasureOpts): Promise<Run> {
  const f = o.fetchFn ?? fetch.bind(globalThis);
  const base = baseFor(o.route);
  const sleep = o.sleep ?? defaultSleep;
  const t0 = Date.now();
  const timeout = o.timeoutMs ?? 180_000;
  const job = await call(f, base, o.key, "/engines/otoc-echo-v1/process", {
    method: "POST",
    body: JSON.stringify({ params }),
    signal: o.signal,
  });
  const jobId: string = job.job_id;
  const tokenHeader: Record<string, string> = job.job_token ? { "X-Job-Token": job.job_token } : {};
  const sent = (job.params as OtocParams | undefined) ?? params;
  o.onSubmitted?.({ job_id: jobId, lent: !!job.lent_key, remaining: job.remaining });
  o.onStatus?.({ job_id: jobId, status: "submitted", elapsed: 0 });
  let delay = 1500;
  for (;;) {
    if (o.signal?.aborted) throw new AtlasError("cancelled");
    const st = await call(f, base, o.key, `/jobs/${jobId}/status`, { signal: o.signal, headers: tokenHeader });
    o.onStatus?.({ job_id: jobId, status: st.status, elapsed: Date.now() - t0 });
    if (st.status === "completed") break;
    if (st.status === "failed" || st.status === "cancelled") {
      const err = st.error ?? {};
      throw new AtlasError(`job ${jobId} ${st.status}: ${err.type ?? ""} ${err.message ?? ""}`.trim());
    }
    if (Date.now() - t0 > timeout) throw new AtlasError(`job ${jobId} still ${st.status} after ${Math.round(timeout / 1000)} s`);
    await sleep(delay);
    delay = Math.min(delay * 1.3, 6000);
  }
  const body = await call(f, base, o.key, `/jobs/${jobId}/result`, { signal: o.signal, headers: tokenHeader });
  return fromAtlasResult(body, jobId, sent as unknown as Record<string, unknown>);
}

export interface Quota {
  ip_hour: number;
  today: number;
}

export interface ServerHealth {
  proxy: boolean;
  server_key: boolean;
  remaining?: Quota;
  limits?: { per_ip_hourly: number; daily: number; n_sites: number; depth: number };
}

/** Ask the same-origin proxy whether it will lend its key (no key is ever returned). Null when there is no proxy. */
export async function serverHealth(fetchFn: Fetch = fetch.bind(globalThis), base = baseFor("proxy")): Promise<ServerHealth | null> {
  try {
    const res = await fetchFn(`${base}/health`, { headers: { Accept: "application/json" } });
    if (!res.ok) return null;
    const j = (await res.json()) as ServerHealth;
    return j && j.proxy === true ? j : null;
  } catch {
    return null;
  }
}
