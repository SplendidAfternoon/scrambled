import { describe, expect, it } from "vitest";
import { ATLAS, AtlasError, measureOtoc, otocParams, pickRoute, serverHealth } from "./atlas";

const ok = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

const result = {
  result: {
    output: {
      data: { series: { F_re: [[1, 0.2], [-1, -1]], F_im: [[0, 0], [0, 0]] } },
      extras: { kick_site: 1, light_cone: [[0, 1], [1, 1]], summary: {} },
      provenance: { backend: "aer" },
    },
  },
};

function fakeFetch(statuses: string[]) {
  const calls: { url: string; init: RequestInit }[] = [];
  let i = 0;
  const f = (async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    if (url.endsWith("/process")) return ok({ job_id: "11111111-2222-3333-4444-555555555555" }, 202);
    if (url.endsWith("/status")) return ok({ status: statuses[Math.min(i++, statuses.length - 1)], error: { type: "engine_timeout", message: "retry" } });
    if (url.endsWith("/result")) return ok(result);
    return ok({}, 404);
  }) as unknown as typeof fetch;
  return { f, calls };
}

describe("pickRoute", () => {
  it("goes direct only on localhost:3000 (the API's CORS allowlist)", () => {
    expect(pickRoute({ host: "localhost:3000", search: "" })).toBe("direct");
    expect(pickRoute({ host: "user.github.io", search: "" })).toBe("proxy");
    expect(pickRoute({ host: "user.github.io", search: "?atlas=direct" })).toBe("direct");
  });
});

describe("measureOtoc", () => {
  const p = otocParams(2, 2, 0.3, 1);
  it("submits, polls, parses, and only sends the key to the chosen base", async () => {
    const { f, calls } = fakeFetch(["queued", "running", "completed"]);
    const seen: string[] = [];
    const run = await measureOtoc(p, { route: "direct", key: "moth_test", fetchFn: f, sleep: async () => {}, onStatus: (s) => seen.push(s.status) });
    expect(run.job_id).toBe("11111111-2222-3333-4444-555555555555");
    expect(run.params.theta_zz_pi).toBeCloseTo(1);
    expect(seen).toEqual(["submitted", "queued", "running", "completed"]);
    expect(calls.every((c) => c.url.startsWith(ATLAS))).toBe(true);
    expect(calls.every((c) => (c.init.headers as Record<string, string>).Authorization === "Bearer moth_test")).toBe(true);
    expect(JSON.parse(calls[0].init.body as string).params.machine).toBe("aer");
  });
  it("uses the relative proxy path when routed via proxy", async () => {
    const { f, calls } = fakeFetch(["completed"]);
    await measureOtoc(p, { route: "proxy", key: "", fetchFn: f, sleep: async () => {} });
    expect(calls[0].url).toBe("./api/atlas/engines/otoc-echo-v1/process");
    expect((calls[0].init.headers as Record<string, string>).Authorization).toBeUndefined();
  });
  it("surfaces failed jobs with the platform error type", async () => {
    const { f } = fakeFetch(["failed"]);
    await expect(measureOtoc(p, { route: "direct", key: "k", fetchFn: f, sleep: async () => {} })).rejects.toThrow(/engine_timeout/);
  });
  it("flags network failures as a CORS/proxy problem", async () => {
    const f = (async () => {
      throw new TypeError("Failed to fetch");
    }) as unknown as typeof fetch;
    const err = await measureOtoc(p, { route: "direct", key: "k", fetchFn: f }).catch((e) => e);
    expect(err).toBeInstanceOf(AtlasError);
    expect(err.cors).toBe(true);
  });
  it("in lent-key mode echoes the job token on reads and uses the server's clamped params", async () => {
    const calls: { url: string; init: RequestInit }[] = [];
    const f = (async (url: string, init: RequestInit) => {
      calls.push({ url, init });
      if (url.endsWith("/process"))
        return ok({ job_id: "11111111-2222-3333-4444-555555555555", job_token: "tok", lent_key: true, params: { ...otocParams(2, 2, 0.3, 0.5) } }, 202);
      if (url.endsWith("/status")) return ok({ status: "completed" });
      return ok(result);
    }) as unknown as typeof fetch;
    let sub: unknown;
    const run = await measureOtoc(otocParams(16, 40, 0.3, 0.5), { route: "proxy", key: "", fetchFn: f, sleep: async () => {}, onSubmitted: (s) => (sub = s) });
    expect(sub).toEqual({ job_id: "11111111-2222-3333-4444-555555555555", lent: true });
    expect((calls[0].init.headers as Record<string, string>)["X-Job-Token"]).toBeUndefined();
    expect(calls.slice(1).every((c) => (c.init.headers as Record<string, string>)["X-Job-Token"] === "tok")).toBe(true);
    expect(run.params.n_sites).toBe(2);
  });
});

describe("serverHealth", () => {
  it("returns the proxy's lent-key status, or null when there is no proxy", async () => {
    const h = { proxy: true, server_key: true, limits: { n_sites: 16, depth: 32 } };
    expect(await serverHealth((async () => ok(h)) as unknown as typeof fetch, "./api/atlas")).toEqual(h);
    expect(await serverHealth((async () => ok({}, 404)) as unknown as typeof fetch, "./api/atlas")).toBeNull();
    expect(await serverHealth((async () => new Response("<html>", { status: 200 })) as unknown as typeof fetch, "./api/atlas")).toBeNull();
    expect(
      await serverHealth((async () => {
        throw new TypeError("x");
      }) as unknown as typeof fetch),
    ).toBeNull();
  });
});
