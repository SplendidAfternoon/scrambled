import { describe, expect, it } from "vitest";
import { clampParams, clientIp, consume, MemoryStore, route, secretFor, signJob, UpstashStore, verifyJob, type Env } from "./atlas";

const JOB = "11111111-2222-3333-4444-555555555555";
const LENT: Env = { ALLOW_SERVER_KEY: "1", MOTH_API_KEY: "moth_srv_secret", PROXY_SECRET: "s3cret" };

function fakeAtlas() {
  const calls: { url: string; init: RequestInit }[] = [];
  const f = (async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    if (url.endsWith("/process")) return new Response(JSON.stringify({ job_id: JOB, status: "queued" }), { status: 202 });
    return new Response(JSON.stringify({ job_id: JOB, status: "completed" }), { status: 200 });
  }) as unknown as typeof fetch;
  return { f, calls };
}

const submit = (params: Record<string, unknown>, extra: Partial<Parameters<typeof route>[0]> = {}) => ({
  method: "POST",
  path: "engines/otoc-echo-v1/process",
  ip: "1.2.3.4",
  body: { params },
  ...extra,
});

describe("bring-your-own-key forwarding", () => {
  it("forwards the caller's key and body unchanged for allowed paths", async () => {
    const { f, calls } = fakeAtlas();
    const r = await route(submit({ n_sites: 40, machine: "ibm_fez" }, { auth: "Bearer moth_user" }), LENT, { fetchFn: f, store: new MemoryStore() });
    expect(r.status).toBe(202);
    expect(calls[0].url).toBe("https://api.mothquantum.com/api/v1/engines/otoc-echo-v1/process");
    expect((calls[0].init.headers as Record<string, string>).Authorization).toBe("Bearer moth_user");
    expect(JSON.parse(calls[0].init.body as string).params.n_sites).toBe(40);
  });
  it("rejects other engines, paths and methods", async () => {
    const d = { fetchFn: fakeAtlas().f, store: new MemoryStore() };
    expect((await route({ method: "POST", path: "engines/blur-v1/process", auth: "Bearer x", ip: "i" }, {}, d)).status).toBe(403);
    expect((await route({ method: "GET", path: "me", auth: "Bearer x", ip: "i" }, {}, d)).status).toBe(403);
    expect((await route({ method: "GET", path: "engines/otoc-echo-v1/process", auth: "Bearer x", ip: "i" }, {}, d)).status).toBe(405);
    expect((await route({ method: "POST", path: `jobs/${JOB}/result`, auth: "Bearer x", ip: "i" }, {}, d)).status).toBe(405);
  });
  it("401s without a key when the lent key is off", async () => {
    const r = await route(submit({}), { MOTH_API_KEY: "moth_srv" }, { fetchFn: fakeAtlas().f, store: new MemoryStore() });
    expect(r.status).toBe(401);
  });
});

describe("clampParams", () => {
  it("clamps to cheap emulator runs and drops everything not whitelisted", () => {
    const p = clampParams({ n_sites: 156, depth: 99, theta_x: 9, theta_zz: -9, machine: "ibm_fez", shots: 1e6, allow_high_shots: true, qpu_token: "x", via: "mothbackend" });
    expect(p).toEqual({ n_sites: 12, depth: 32, theta_x: Math.PI, theta_zz: -Math.PI + 1e-9, theta_z: 0, machine: "aer", exact: true, include_taps: false });
  });
  it("fills defaults for missing or non-numeric values", () => {
    const p = clampParams({ n_sites: "abc" });
    expect(p.n_sites).toBe(12);
    expect(p.depth).toBe(32);
    expect(p.theta_x).toBeCloseTo(0.3 * Math.PI);
    expect(clampParams({ n_sites: 1, depth: 0.4 }).n_sites).toBe(2);
    expect(clampParams({ depth: 0.4 }).depth).toBe(1);
  });
});

describe("job-id signing", () => {
  it("verifies only tokens for the same job and secret", () => {
    const t = signJob(JOB, "a");
    expect(verifyJob(JOB, t, "a")).toBe(true);
    expect(verifyJob(JOB, t, "b")).toBe(false);
    expect(verifyJob("99999999-2222-3333-4444-555555555555", t, "a")).toBe(false);
    expect(verifyJob(JOB, undefined, "a")).toBe(false);
    expect(verifyJob(JOB, t.slice(1), "a")).toBe(false);
  });
  it("derives a secret from the key without containing it", () => {
    const s = secretFor({ MOTH_API_KEY: "moth_abc" });
    expect(s).not.toContain("moth_abc");
    expect(s).toBe(secretFor({ MOTH_API_KEY: "moth_abc" }));
  });
});

describe("lent server key", () => {
  it("submits clamped params with the server key and returns a job token, never the key", async () => {
    const { f, calls } = fakeAtlas();
    const r = await route(submit({ n_sites: 99, theta_x: 1, theta_zz: 1, machine: "ibm_fez" }), LENT, { fetchFn: f, store: new MemoryStore() });
    expect(r.status).toBe(202);
    const sent = JSON.parse(calls[0].init.body as string).params;
    expect(sent).toMatchObject({ n_sites: 12, machine: "aer", exact: true });
    expect((calls[0].init.headers as Record<string, string>).Authorization).toBe("Bearer moth_srv_secret");
    const b = r.body as Record<string, unknown>;
    expect(b.job_token).toBe(signJob(JOB, "s3cret"));
    expect(b.remaining).toEqual({ ip_hour: 2, today: 59 });
    expect(JSON.stringify(r.body)).not.toContain("moth_srv_secret");
  });
  it("reads status/result only with a valid job token", async () => {
    const { f, calls } = fakeAtlas();
    const d = { fetchFn: f, store: new MemoryStore() };
    const path = `jobs/${JOB}/status`;
    expect((await route({ method: "GET", path, ip: "i" }, LENT, d)).status).toBe(403);
    expect((await route({ method: "GET", path, ip: "i", jobToken: "forged" }, LENT, d)).status).toBe(403);
    expect(calls.length).toBe(0);
    const ok = await route({ method: "GET", path: `jobs/${JOB}/result`, ip: "i", jobToken: signJob(JOB, "s3cret") }, LENT, d);
    expect(ok.status).toBe(200);
  });
});

describe("rate limit", () => {
  it("allows 3 lent-key submits per IP per hour, then 429 without calling Atlas", async () => {
    const { f, calls } = fakeAtlas();
    const store = new MemoryStore(() => t);
    let t = Date.UTC(2026, 9, 4, 10, 0, 0);
    const d = { fetchFn: f, store, now: () => t };
    for (let i = 0; i < 3; i++) expect((await route(submit({}), LENT, d)).status).toBe(202);
    const blocked = await route(submit({}), LENT, d);
    expect(blocked.status).toBe(429);
    expect(calls.length).toBe(3);
    expect((await route(submit({}, { ip: "5.6.7.8" }), LENT, d)).status).toBe(202);
    t += 3_600_000;
    expect((await route(submit({}), LENT, d)).status).toBe(202);
  });
  it("enforces the global daily cap from SERVER_KEY_DAILY_CAP across IPs", async () => {
    const env = { ...LENT, SERVER_KEY_DAILY_CAP: "2", SERVER_KEY_PER_IP_HOURLY: "10" };
    const store = new MemoryStore();
    expect((await consume(store, env, "a", 0)).ok).toBe(true);
    expect((await consume(store, env, "b", 0)).ok).toBe(true);
    const third = await consume(store, env, "c", 0);
    expect(third.ok).toBe(false);
    expect(third.reason).toMatch(/daily cap of 2/);
    expect((await consume(store, env, "c", 27 * 3600 * 1000)).ok).toBe(true);
  });
  it("BYOK calls are not rate limited", async () => {
    const d = { fetchFn: fakeAtlas().f, store: new MemoryStore() };
    for (let i = 0; i < 6; i++) expect((await route(submit({}, { auth: "Bearer u" }), LENT, d)).status).toBe(202);
  });
  it("health reports remaining quota without consuming it", async () => {
    const d = { fetchFn: fakeAtlas().f, store: new MemoryStore() };
    const h1 = await route({ method: "GET", path: "health", ip: "i" }, LENT, d);
    const h2 = await route({ method: "GET", path: "health", ip: "i" }, LENT, d);
    expect(h1.body).toEqual(h2.body);
    expect(h1.body).toMatchObject({ server_key: true, remaining: { ip_hour: 3, today: 60 } });
    expect(JSON.stringify(h1.body)).not.toContain("moth_srv");
    expect((await route({ method: "GET", path: "health", ip: "i" }, {}, d)).body).toEqual({ proxy: true, server_key: false });
  });
});

describe("helpers", () => {
  it("takes the first x-forwarded-for hop as the client IP", () => {
    expect(clientIp({ headers: { "x-forwarded-for": "9.9.9.9, 10.0.0.1" } })).toBe("9.9.9.9");
    expect(clientIp({ headers: {}, socket: { remoteAddress: "::1" } })).toBe("::1");
  });
  it("UpstashStore speaks the REST pipeline protocol", async () => {
    const bodies: unknown[] = [];
    const f = (async (_u: string, init: RequestInit) => {
      bodies.push(JSON.parse(init.body as string));
      return new Response(JSON.stringify([{ result: 4 }, { result: 1 }]));
    }) as unknown as typeof fetch;
    const s = new UpstashStore("https://x.upstash.io/", "tok", f);
    expect(await s.incr("k", 60)).toBe(4);
    expect(bodies[0]).toEqual([["INCR", "k"], ["EXPIRE", "k", 60, "NX"]]);
  });
});
