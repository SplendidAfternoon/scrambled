// Headless browser check of the built-in pages against a running dev server (npm run dev, port 3000).
// Exercises the landing page and the explorer, writes screenshots to web/screenshots/.
//   node scripts/e2e.mjs            cached mode only
//   node scripts/e2e.mjs --live     also runs one live otoc-echo-v1 measurement from the explorer
//                                   (reads MOTH_API_KEY from ../.env; the key is typed into the password field, never printed)
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { chromium } from "playwright";

const BASE = process.env.BASE ?? "http://localhost:3000";
const SHOTS = resolve(import.meta.dirname, "../screenshots");
const live = process.argv.includes("--live");
const errors = [];
const log = (...a) => console.log(...a);

const browser = await chromium.launch();

async function page(ctxOpts) {
  const ctx = await browser.newContext(ctxOpts);
  const p = await ctx.newPage();
  p.on("console", (m) => m.type() === "error" && errors.push(`[console] ${m.text()}`));
  p.on("pageerror", (e) => errors.push(`[pageerror] ${e.message}`));
  return p;
}

const setRange = (p, sel, v) =>
  p.evaluate(([s, val]) => {
    const el = document.querySelector(s);
    el.value = String(val);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }, [sel, v]);

// A page-wide text selection used to make Chrome drag the selection instead of the knob.
async function dragWithSelection(p) {
  await p.evaluate(() => document.getSelection().selectAllChildren(document.body));
  const el = p.locator("#tx");
  const box = await el.boundingBox();
  const v0 = +(await el.inputValue());
  const x0 = box.x + ((v0 - 0.05) / 0.55) * box.width, y = box.y + box.height / 2;
  await p.mouse.move(x0, y);
  await p.mouse.down();
  await p.mouse.move(x0 + 60, y, { steps: 8 });
  await p.mouse.up();
  const v1 = +(await el.inputValue());
  if (!(v1 > v0 + 0.05)) errors.push(`[explorer] slider frozen while text was selected: ${v0} -> ${v1}`);
  await setRange(p, "#tx", v0);
}

async function explorer(p, tag) {
  await p.goto(`${BASE}/explorer.html`);
  await p.waitForFunction(() => document.querySelector("#prov")?.textContent?.includes("job"));
  await p.waitForTimeout(800);
  if (tag === "desktop") await dragWithSelection(p);
  await p.click("#play"); // pause autoplay
  await setRange(p, "#t", 9);
  await p.waitForTimeout(300);
  await p.screenshot({ path: `${SHOTS}/explorer-scrambling-${tag}.png`, fullPage: true });
  await setRange(p, "#tzz", 0.99);
  await setRange(p, "#t", 20);
  await p.waitForTimeout(300);
  const label = await p.textContent("#tzz-val");
  if (!label.includes("Clifford")) errors.push(`[explorer] theta_zz did not snap to Clifford: ${label}`);
  await p.screenshot({ path: `${SHOTS}/explorer-clifford-${tag}.png`, fullPage: true });
  log(`  explorer ${tag}: ${(await p.textContent("#prov")).replace(/\s+/g, " ").slice(0, 160)}`);
}

async function liveMeasure(p) {
  const env = readFileSync(resolve(import.meta.dirname, "../../.env"), "utf-8");
  const key = /MOTH_API_KEY\s*=\s*"?([^"\r\n]+)/.exec(env)?.[1]?.trim();
  if (!key) throw new Error("MOTH_API_KEY missing from .env");
  await p.goto(`${BASE}/explorer.html`);
  await p.waitForFunction(() => document.querySelector("#prov")?.textContent?.includes("job"));
  await setRange(p, "#tx", 0.22);
  await setRange(p, "#tzz", 0.3);
  await p.fill("#key", key);
  await p.click("#measure");
  const t0 = Date.now();
  let status = "";
  while (Date.now() - t0 < 240_000) {
    status = (await p.textContent("#status")) ?? "";
    if (/^Done|failed|HTTP|error/i.test(status)) break;
    await p.waitForTimeout(1000);
  }
  log(`  live status: ${status.replace(key, "<key>")}`);
  await p.fill("#key", "");
  await p.waitForTimeout(600);
  await p.screenshot({ path: `${SHOTS}/explorer-live.png`, fullPage: true });
  return status;
}

try {
  const desktop = { viewport: { width: 1400, height: 900 } };
  const mobile = { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true };
  log("desktop");
  const d = await page(desktop);
  await d.goto(`${BASE}/`);
  await d.waitForTimeout(500);
  await d.screenshot({ path: `${SHOTS}/landing-desktop.png`, fullPage: true });
  await explorer(d, "desktop");
  log("mobile");
  const m = await page(mobile);
  await explorer(m, "mobile");
  if (live) {
    log("live");
    await liveMeasure(await page(desktop));
  }
} catch (e) {
  errors.push(`[e2e] ${e.stack ?? e}`);
} finally {
  await browser.close();
}

if (errors.length) {
  console.error("FAIL\n" + errors.join("\n"));
  process.exit(1);
}
log("PASS");
