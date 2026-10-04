/**
 * Same-origin proxy to the Moth Atlas API (Vercel serverless function; also mounted by `npm run dev`).
 *
 * Why: api.mothquantum.com's CORS allowlist only admits http://localhost:3000, so a deployed static site
 * cannot call it from the browser. vercel.json rewrites /api/atlas/<path> -> /api/atlas?path=<path>.
 *
 * Two modes:
 *  - Bring your own key: the caller's "Authorization: Bearer <key>" is forwarded as-is (never logged or stored).
 *    Only otoc-echo-v1 submit and job status/result paths are allowed.
 *  - Lent server key (ALLOW_SERVER_KEY=1 + MOTH_API_KEY): for callers without a key. Submit params are rebuilt
 *    from a whitelist and clamped (aer, exact, n_sites <= 12, depth <= 32); submissions are rate limited per IP
 *    and per day; status/result reads need the HMAC token this proxy returned with the job id, so the server key
 *    can only read jobs it created. The key never leaves the server.
 * Rate-limit counters live in Upstash Redis REST (UPSTASH_REDIS_REST_URL/TOKEN or Vercel KV_REST_API_URL/TOKEN)
 * when configured, otherwise in this instance's memory (resets on cold start; each instance counts separately).
 */
import { createHash, createHmac, timingSafeEqual } from "node:crypto";

export const ATLAS = "https://api.mothquantum.com/api/v1";
const UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
const SUBMIT = /^engines\/otoc-echo-v1\/process$/;
const JOB = new RegExp(`^jobs\\/(${UUID})\\/(status|result)$`);

export type Env = Record<string, string | undefined>;

/* ---------------- params clamp ---------------- */

const clamp = (v: unknown, lo: number, hi: number, dflt: number) => {
  const n = Number(v);
  return Number.isFinite(n) ? Math.min(hi, Math.max(lo, n)) : dflt;
};

export const LIMITS = { n_sites: 12, depth: 32 } as const;

/** Rebuild otoc-echo-v1 params from a whitelist for the lent key: cheap, emulator-only, no secrets passed through. */
export function clampParams(input: unknown) {
  const p = (input ?? {}) as Record<string, unknown>;
  const PI = Math.PI;
  const tzz = clamp(p.theta_zz, -PI + 1e-9, PI, 0.35 * PI);
  return {
    n_sites: Math.round(clamp(p.n_sites, 2, LIMITS.n_sites, 12)),
    depth: Math.round(clamp(p.depth, 1, LIMITS.depth, 32)),
    theta_x: clamp(p.theta_x, 0, PI, 0.3 * PI),
    theta_zz: tzz,
    theta_z: clamp(p.theta_z, 0, PI, 0),
    machine: "aer" as const,
    exact: true,
    include_taps: false,
  };
}

/* ---------------- job tokens ---------------- */

export function secretFor(env: Env): string {
  if (env.PROXY_SECRET) return env.PROXY_SECRET;
  // One-way derivation, so the token reveals nothing about the key.
  return createHash("sha256").update(`scrambled-proxy-v1:${env.MOTH_API_KEY ?? ""}`).digest("hex");
}

export const signJob = (jobId: string, secret: string) => createHmac("sha256", secret).update(`job:${jobId}`).digest("base64url");

export function verifyJob(jobId: string, token: string | undefined, secret: string): boolean {
  if (!token) return false;
  const a = Buffer.from(signJob(jobId, secret));
  const b = Buffer.from(token);
  return a.length === b.length && timingSafeEqual(a, b);
}

/* ---------------- rate limit ---------------- */

export interface Store {
  /** increment key (creating it with ttl seconds) and return the new count */
  incr(key: string, ttlSec: number): Promise<number>;
  get(key: string): Promise<number>;
}

export class MemoryStore implements Store {
  private m = new Map<string, { n: number; exp: number }>();
  constructor(private now: () => number = Date.now) {}
  private live(key: string) {
    const e = this.m.get(key);
    if (e && e.exp <= this.now()) {
      this.m.delete(key);
      return undefined;
    }
    return e;
  }
  async incr(key: string, ttlSec: number) {
    const e = this.live(key) ?? { n: 0, exp: this.now() + ttlSec * 1000 };
    e.n += 1;
    this.m.set(key, e);
    return e.n;
  }
  async get(key: string) {
    return this.live(key)?.n ?? 0;
  }
}

export class UpstashStore implements Store {
  constructor(private url: string, private token: string, private fetchFn: typeof fetch = fetch) {}
  private async pipe(cmds: (string | number)[][]) {
    const r = await this.fetchFn(`${this.url.replace(/\/$/, "")}/pipeline`, {
      method: "POST",
      headers: { Authorization: `Bearer ${this.token}`, "Content-Type": "application/json" },
      body: JSON.stringify(cmds),
    });
    if (!r.ok) throw new Error(`upstash ${r.status}`);
    return (await r.json()) as { result: unknown }[];
  }
  async incr(key: string, ttlSec: number) {
    const out = await this.pipe([["INCR", key], ["EXPIRE", key, ttlSec, "NX"]]);
    return Number(out[0].result);
  }
  async get(key: string) {
    const out = await this.pipe([["GET", key]]);
    return Number(out[0].result ?? 0);
  }
}

let memStore: MemoryStore | null = null;
export function storeFor(env: Env): { store: Store; kind: "upstash" | "memory" } {
  const url = env.UPSTASH_REDIS_REST_URL ?? env.KV_REST_API_URL;
  const token = env.UPSTASH_REDIS_REST_TOKEN ?? env.KV_REST_API_TOKEN;
  if (url && token) return { store: new UpstashStore(url, token), kind: "upstash" };
  memStore ??= new MemoryStore();
  return { store: memStore, kind: "memory" };
}

export function limitsFor(env: Env) {
  return {
    perIpHourly: Math.max(0, Math.floor(clamp(env.SERVER_KEY_PER_IP_HOURLY, 0, 1000, 3))),
    daily: Math.max(0, Math.floor(clamp(env.SERVER_KEY_DAILY_CAP, 0, 100000, 60))),
  };
}

const dayKey = (now: number) => `scr:day:${new Date(now).toISOString().slice(0, 10)}`;
const ipKey = (ip: string, now: number) => `scr:ip:${createHash("sha256").update(ip).digest("hex").slice(0, 16)}:${Math.floor(now / 3_600_000)}`;

export async function quota(store: Store, env: Env, ip: string, now: number) {
  const lim = limitsFor(env);
  const [d, i] = await Promise.all([store.get(dayKey(now)), store.get(ipKey(ip, now))]);
  return { ip: Math.max(0, lim.perIpHourly - i), daily: Math.max(0, lim.daily - d), perIpHourly: lim.perIpHourly, dailyCap: lim.daily };
}

/** Consume one submission. Checks before incrementing so refused calls don't burn quota. */
export async function consume(store: Store, env: Env, ip: string, now: number): Promise<{ ok: boolean; reason?: string }> {
  const q = await quota(store, env, ip, now);
  if (q.daily <= 0) return { ok: false, reason: `daily cap of ${q.dailyCap} lent-key runs reached; try again tomorrow or use your own key` };
  if (q.ip <= 0) return { ok: false, reason: `limit of ${q.perIpHourly} lent-key runs per hour reached; try again later or use your own key` };
  await Promise.all([store.incr(dayKey(now), 26 * 3600), store.incr(ipKey(ip, now), 3600)]);
  return { ok: true };
}

/* ---------------- routing ---------------- */

export interface ProxyRequest {
  method: string;
  path: string;
  auth?: string;
  jobToken?: string;
  ip: string;
  body?: unknown;
}

export interface ProxyResult {
  status: number;
  body: unknown;
}

export interface Deps {
  fetchFn?: typeof fetch;
  store?: Store;
  storeKind?: string;
  now?: () => number;
}

const serverKeyOn = (env: Env) => env.ALLOW_SERVER_KEY === "1" && !!env.MOTH_API_KEY;

async function upstream(fetchFn: typeof fetch, url: string, init: RequestInit): Promise<ProxyResult> {
  try {
    const r = await fetchFn(url, init);
    const text = await r.text();
    let body: unknown = text;
    try {
      body = text ? JSON.parse(text) : null;
    } catch {
      /* keep text */
    }
    return { status: r.status, body };
  } catch (e) {
    return { status: 502, body: { error: `upstream unreachable: ${(e as Error).message}` } };
  }
}

export async function route(req: ProxyRequest, env: Env, deps: Deps = {}): Promise<ProxyResult> {
  const fetchFn = deps.fetchFn ?? fetch;
  const now = (deps.now ?? Date.now)();
  const { store, kind } = deps.store ? { store: deps.store, kind: deps.storeKind ?? "custom" } : storeFor(env);
  const path = (req.path || "").replace(/^\/+/, "");

  if (path === "health") {
    if (req.method !== "GET") return { status: 405, body: { error: "method not allowed" } };
    if (!serverKeyOn(env)) return { status: 200, body: { proxy: true, server_key: false } };
    const q = await quota(store, env, req.ip, now);
    return {
      status: 200,
      body: { proxy: true, server_key: true, remaining: { ip_hour: q.ip, today: q.daily }, limits: { per_ip_hourly: q.perIpHourly, daily: q.dailyCap, n_sites: LIMITS.n_sites, depth: LIMITS.depth, machine: "aer" }, counter: kind },
    };
  }

  const isSubmit = SUBMIT.test(path);
  const job = JOB.exec(path);
  if (!isSubmit && !job) return { status: 403, body: { error: `path not allowed: ${path}` } };
  if (isSubmit !== (req.method === "POST") || !["GET", "POST"].includes(req.method)) return { status: 405, body: { error: "method not allowed" } };

  const userAuth = req.auth && /^Bearer \S+$/.test(req.auth) ? req.auth : "";
  const headers: Record<string, string> = { "User-Agent": "scrambled-web-proxy/1.1" };

  if (userAuth) {
    headers.Authorization = userAuth;
    const init: RequestInit = { method: req.method, headers };
    if (isSubmit) {
      headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(req.body ?? {});
    }
    return upstream(fetchFn, `${ATLAS}/${path}`, init);
  }

  if (!serverKeyOn(env)) return { status: 401, body: { error: "no API key: paste your Atlas key in the app" } };
  headers.Authorization = `Bearer ${env.MOTH_API_KEY}`;
  const secret = secretFor(env);

  if (job) {
    if (!verifyJob(job[1], req.jobToken, secret)) return { status: 403, body: { error: "the lent key can only read jobs this proxy submitted" } };
    return upstream(fetchFn, `${ATLAS}/${path}`, { method: "GET", headers });
  }

  const c = await consume(store, env, req.ip, now);
  if (!c.ok) return { status: 429, body: { error: c.reason } };
  const params = clampParams(((req.body ?? {}) as { params?: unknown }).params);
  headers["Content-Type"] = "application/json";
  const res = await upstream(fetchFn, `${ATLAS}/${path}`, { method: "POST", headers, body: JSON.stringify({ params }) });
  const b = res.body as { job_id?: string } | null;
  if (res.status < 300 && b && typeof b === "object" && b.job_id && new RegExp(`^${UUID}$`).test(b.job_id)) {
    const q = await quota(store, env, req.ip, now);
    return { status: res.status, body: { ...b, job_token: signJob(b.job_id, secret), lent_key: true, params, remaining: { ip_hour: q.ip, today: q.daily } } };
  }
  return res;
}

/* ---------------- Vercel / Node adapter ---------------- */

interface VReq {
  method?: string;
  query?: Record<string, string | string[] | undefined>;
  headers: Record<string, string | string[] | undefined>;
  body?: unknown;
  socket?: { remoteAddress?: string };
}
interface VRes {
  status(code: number): VRes;
  setHeader(k: string, v: string): void;
  send(body: string): void;
}

const first = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);

export function clientIp(req: VReq): string {
  const xff = first(req.headers["x-forwarded-for"]);
  return (xff?.split(",")[0].trim() || first(req.headers["x-real-ip"]) || req.socket?.remoteAddress || "unknown").slice(0, 64);
}

export default async function handler(req: VReq, res: VRes) {
  const q = req.query?.path;
  const path = Array.isArray(q) ? q.join("/") : q ?? "";
  let body = req.body;
  if (typeof body === "string") {
    try {
      body = JSON.parse(body);
    } catch {
      body = {};
    }
  }
  const out = await route(
    {
      method: req.method ?? "GET",
      path,
      auth: first(req.headers.authorization),
      jobToken: first(req.headers["x-job-token"]),
      ip: clientIp(req),
      body,
    },
    process.env,
  );
  res.setHeader("Cache-Control", "no-store");
  res.setHeader("Content-Type", "application/json");
  res.status(out.status).send(typeof out.body === "string" ? out.body : JSON.stringify(out.body));
}
