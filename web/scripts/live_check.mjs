// One live otoc-echo-v1 measurement from the explorer page in headless Chromium (direct route on localhost:3000,
// or the proxy route with BASE=http://localhost:4173 ... ?atlas=proxy). Reads MOTH_API_KEY from ../.env and types it
// into the password field; the key is never printed. Writes screenshots/explorer-live[-proxy].png.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { chromium } from "playwright";

const BASE = process.env.BASE ?? "http://localhost:3000";
const QUERY = process.env.QUERY ?? "";
const TAG = process.env.TAG ?? "";
const env = readFileSync(resolve(import.meta.dirname, "../../.env"), "utf-8");
const key = /MOTH_API_KEY\s*=\s*"?([^"\r\n]+)/.exec(env)?.[1]?.trim();
if (!key) throw new Error("MOTH_API_KEY missing from .env");

const browser = await chromium.launch();
const p = await browser.newPage({ viewport: { width: 1400, height: 900 } });
const net = [];
p.on("request", (r) => r.url().includes("/engines/") || r.url().includes("/jobs/") ? net.push(`${r.method()} ${r.url()}`) : 0);
p.on("console", (m) => m.type() === "error" && console.log("[console]", m.text().replace(key, "<key>")));
await p.goto(`${BASE}/explorer.html${QUERY}`);
await p.waitForFunction(() => document.querySelector("#prov")?.textContent?.includes("job"));
const setRange = (sel, v) => p.evaluate(([s, val]) => {
  const el = document.querySelector(s);
  el.value = String(val);
  el.dispatchEvent(new Event("input", { bubbles: true }));
}, [sel, v]);
await setRange("#tx", Number(process.env.TX ?? 0.22));
await setRange("#tzz", Number(process.env.TZZ ?? 0.3));
if (process.env.LENT === "1") {
  // Judge path: empty key field, the dev server lends its key (ALLOW_SERVER_KEY=1).
  await p.waitForFunction(() => /demo key/.test(document.querySelector("#measure")?.textContent ?? ""), null, { timeout: 15000 });
  console.log("button:", await p.textContent("#measure"));
  console.log("lent note:", await p.textContent("#lent"));
  p.on("request", (r) => r.url().includes("/jobs/") && net.push(`token=${r.headers()["x-job-token"] ? "yes" : "no"} auth=${r.headers().authorization ? "yes" : "no"}`));
  p.on("response", async (r) => {
    if (r.url().includes("/api/atlas/")) {
      const t = await r.text().catch(() => "");
      if (t.includes(key)) console.log("LEAK: key in response body of", r.url());
    }
  });
} else {
  await p.fill("#key", key);
}
await p.click("#measure");
const t0 = Date.now();
let status = "";
while (Date.now() - t0 < 300_000) {
  status = (await p.textContent("#status")) ?? "";
  if (/^Done|failed|HTTP|error|CORS/i.test(status)) break;
  await p.waitForTimeout(1000);
}
await p.fill("#key", "");
await p.waitForTimeout(1500);
await p.screenshot({ path: resolve(import.meta.dirname, `../screenshots/explorer-live${TAG}.png`), fullPage: true });
console.log("requests:", [...new Set(net.map((u) => u.replace(/[0-9a-f-]{36}/, "<job>")))].join(" | "));
console.log("status:", status.replace(key, "<key>"));
console.log("mode tag:", await p.textContent("#mode-tag"));
console.log("button after:", await p.textContent("#measure"));
console.log("prov:", (await p.textContent("#prov")).replace(/\s+/g, " ").trim());
await browser.close();
process.exit(/^Done/.test(status) ? 0 : 2);
