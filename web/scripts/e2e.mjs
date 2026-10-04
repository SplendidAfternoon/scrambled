// Headless browser check of the built-in pages against a running dev server (npm run dev, port 3000).
// Plays the game start -> finish, exercises the explorer, writes screenshots to web/screenshots/.
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

const currentT = async (p) => parseFloat((await p.textContent("#k-t")).replace("t = ", ""));

async function serveAt(p, target) {
  for (;;) {
    if (!(await p.isVisible("#s-cook"))) return;
    if ((await currentT(p)) >= target) break;
    await p.waitForTimeout(25);
  }
  await p.keyboard.press("Space");
}

// Winning pan index and serve time per level (from the measured windows checked in levels.test.ts).
const PLAN = [
  { choice: 0, t: 8 },
  { choice: 1, t: 9 },
  { choice: 2, t: 24 },
  { choice: 0, t: 20 },
  { choice: 2, t: 20 },
];

async function playThrough(p, tag) {
  await p.goto(`${BASE}/game.html`);
  await p.waitForSelector("#start");
  await p.waitForTimeout(500);
  await p.screenshot({ path: `${SHOTS}/game-title-${tag}.png` });
  await p.click("#start");
  for (let i = 0; i < PLAN.length; i++) {
    await p.waitForSelector("#s-choose:not([hidden]) .choice");
    await p.waitForTimeout(300);
    if (i === 0 || i === 2) await p.screenshot({ path: `${SHOTS}/game-choose-L${i + 1}-${tag}.png`, fullPage: true });
    await p.locator(".choice").nth(PLAN[i].choice).click();
    await p.waitForSelector("#s-cook:not([hidden])");
    if (i === 3) {
      await serveAt(p, 17.2);
      // keep cooking a moment for a mid-cook shot? no: served already
    } else {
      if (i === 1) {
        // grab a mid-cook frame before serving
        for (; (await currentT(p)) < 7; ) await p.waitForTimeout(25);
        await p.screenshot({ path: `${SHOTS}/game-cook-${tag}.png` });
      }
      await serveAt(p, PLAN[i].t);
    }
    await p.waitForSelector("#s-result:not([hidden])", { timeout: 15000 });
    const verdict = await p.textContent("#r-verdict");
    log(`  L${i + 1}: ${verdict} ${await p.textContent("#r-score")}`);
    if (i === 3) await p.screenshot({ path: `${SHOTS}/game-result-${tag}.png`, fullPage: true });
    if (!/SERVED|PERFECT/.test(verdict)) errors.push(`[game ${tag}] level ${i + 1} not won: ${verdict}`);
    await p.click("#r-next");
  }
  await p.waitForSelector("#s-end:not([hidden])");
  await p.waitForTimeout(400);
  log(`  end: ${await p.textContent("#e-title")} · ${await p.textContent("#e-score")}`);
  await p.screenshot({ path: `${SHOTS}/game-end-${tag}.png`, fullPage: true });
}

async function lossPath(p, tag) {
  await p.goto(`${BASE}/game.html`);
  await p.click("#start");
  await p.locator(".choice").first().click();
  await p.waitForSelector("#s-cook:not([hidden])");
  await p.waitForTimeout(300);
  await p.locator("#serve").click();
  await p.waitForTimeout(250);
  await p.screenshot({ path: `${SHOTS}/game-raw-stamp-${tag}.png` });
  await p.waitForSelector("#s-result:not([hidden])");
  const v = await p.textContent("#r-verdict");
  log(`  early serve -> ${v}`);
  if (v !== "RAW!") errors.push(`[game ${tag}] early serve gave ${v}`);
}

async function explorer(p, tag) {
  await p.goto(`${BASE}/explorer.html`);
  await p.waitForFunction(() => document.querySelector("#prov")?.textContent?.includes("job"));
  await p.waitForTimeout(800);
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
  await playThrough(d, "desktop");
  log("mobile");
  const m = await page(mobile);
  await explorer(m, "mobile");
  await playThrough(m, "mobile");
  await lossPath(m, "mobile");
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
