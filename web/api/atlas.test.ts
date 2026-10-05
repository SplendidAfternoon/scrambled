import { describe, expect, it } from "vitest";
import { clampParams, route, secretFor, signJob, verifyJob, type Env } from "./atlas";

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
  body: { params },
  ...extra,
});

describe("bring-your-own-key forwarding", () => {
  it("forwards the caller's key and body unchanged for allowed paths", async () => {
    const { f, calls } = fakeAtlas();
    const r = await route(submit({ n_sites: 40, machine: "ibm_fez" }, { auth: "Bearer moth_user" }), LENT, { fetchFn: f });
    expect(r.status).toBe(202);
    expect(calls[0].url).toBe("https://api.mothquantum.com/api/v1/engines/otoc-echo-v1/process");
    expect((calls[0].init.headers as Record<string, string>).Authorization).toBe("Bearer moth_user");
    expect(JSON.parse(calls[0].init.body as string).params.n_sites).toBe(40);
  });
  it("rejects other engines, paths and methods", async () => {
    const d = { fetchFn: fakeAtlas().f };
    expect((await route({ method: "POST", path: "engines/blur-v1/process", auth: "Bearer x" }, {}, d)).status).toBe(403);
    expect((await route({ method: "GET", path: "me", auth: "Bearer x" }, {}, d)).status).toBe(403);
    expect((await route({ method: "GET", path: "engines/otoc-echo-v1/process", auth: "Bearer x" }, {}, d)).status).toBe(405);
    expect((await route({ method: "POST", path: `jobs/${JOB}/result`, auth: "Bearer x" }, {}, d)).status).toBe(405);
  });
  it("401s without a key when the lent key is off", async () => {
    const r = await route(submit({}), { MOTH_API_KEY: "moth_srv" }, { fetchFn: fakeAtlas().f });
    expect(r.status).toBe(401);
  });
});

describe("clampParams", () => {
  it("clamps to emulator runs of up to 16 qubits and drops everything not whitelisted", () => {
    const p = clampParams({ n_sites: 156, depth: 99, theta_x: 9, theta_zz: -9, machine: "ibm_fez", shots: 1e6, allow_high_shots: true, qpu_token: "x", via: "mothbackend" });
    expect(p).toEqual({ n_sites: 16, depth: 32, theta_x: Math.PI, theta_zz: -Math.PI + 1e-9, theta_z: 0, machine: "aer", exact: true, include_taps: false });
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
    const r = await route(submit({ n_sites: 99, theta_x: 1, theta_zz: 1, machine: "ibm_fez" }), LENT, { fetchFn: f });
    expect(r.status).toBe(202);
    const sent = JSON.parse(calls[0].init.body as string).params;
    expect(sent).toMatchObject({ n_sites: 16, machine: "aer", exact: true });
    expect((calls[0].init.headers as Record<string, string>).Authorization).toBe("Bearer moth_srv_secret");
    const b = r.body as Record<string, unknown>;
    expect(b.job_token).toBe(signJob(JOB, "s3cret"));
    expect(b).not.toHaveProperty("remaining");
    expect(JSON.stringify(r.body)).not.toContain("moth_srv_secret");
  });
  it("has no rate limit", async () => {
    const { f, calls } = fakeAtlas();
    for (let i = 0; i < 20; i++) expect((await route(submit({}), LENT, { fetchFn: f })).status).toBe(202);
    expect(calls.length).toBe(20);
  });
  it("reads status/result only with a valid job token", async () => {
    const { f, calls } = fakeAtlas();
    const d = { fetchFn: f };
    const path = `jobs/${JOB}/status`;
    expect((await route({ method: "GET", path }, LENT, d)).status).toBe(403);
    expect((await route({ method: "GET", path, jobToken: "forged" }, LENT, d)).status).toBe(403);
    expect(calls.length).toBe(0);
    const ok = await route({ method: "GET", path: `jobs/${JOB}/result`, jobToken: signJob(JOB, "s3cret") }, LENT, d);
    expect(ok.status).toBe(200);
  });
  it("health says whether the lent key is on and its run size, without leaking the key", async () => {
    const h = await route({ method: "GET", path: "health" }, LENT, {});
    expect(h.body).toEqual({ proxy: true, server_key: true, limits: { n_sites: 16, depth: 32, machine: "aer" } });
    expect(JSON.stringify(h.body)).not.toContain("moth_srv");
    expect((await route({ method: "GET", path: "health" }, {}, {})).body).toEqual({ proxy: true, server_key: false });
  });
});
