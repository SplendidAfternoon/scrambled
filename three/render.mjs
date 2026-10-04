// Offline renderer: serves web/ + node_modules, drives headless Chromium frame by frame, writes PNGs,
// then encodes out/quantum_egg.mp4 with ffmpeg.
//   node render.mjs                 full render (1080x1080, 30 fps)
//   node render.mjs --stills 2,10,25,34,39,43   preview frames only (out/stills/)
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FPS = 30;
const args = process.argv.slice(2);
const stillsArg = args.includes('--stills') ? args[args.indexOf('--stills') + 1] : null;
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json' };

const server = http.createServer((req, res) => {
  const url = decodeURIComponent(req.url.split('?')[0]);
  const file = url.startsWith('/node_modules/') ? path.join(HERE, url) : path.join(HERE, 'web', url === '/' ? 'index.html' : url);
  if (!file.startsWith(HERE) || !fs.existsSync(file)) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'Content-Type': MIME[path.extname(file)] || 'application/octet-stream' });
  fs.createReadStream(file).pipe(res);
});
await new Promise((r) => server.listen(0, '127.0.0.1', r));
const base = `http://127.0.0.1:${server.address().port}/`;

const browser = await chromium.launch({
  channel: process.env.PW_CHANNEL || 'msedge',
  args: ['--use-angle=d3d11', '--enable-gpu', '--ignore-gpu-blocklist', '--enable-unsafe-swiftshader'],
});
const page = await browser.newPage({ viewport: { width: 1080, height: 1080 }, deviceScaleFactor: 1 });
page.on('console', (m) => { if (m.type() === 'error') console.error('[page]', m.text()); });
page.on('pageerror', (e) => console.error('[pageerror]', e.message));
await page.goto(base);
await page.waitForFunction(() => window.__ready === true, null, { timeout: 120000 });
const info = await page.evaluate(() => window.__info());
console.log('GL renderer:', info.renderer, '| duration', info.duration, 's | verts', info.verts);

async function shoot(t, file) {
  await page.evaluate((tt) => window.renderAt(tt), t);
  await page.screenshot({ path: file, type: 'png' });
}

if (stillsArg) {
  const dir = path.join(HERE, 'out', 'stills');
  fs.mkdirSync(dir, { recursive: true });
  for (const s of stillsArg.split(',').map(Number)) {
    // replay the timeline up to s so state is identical to the video
    await shoot(s, path.join(dir, `still_${String(s).padStart(5, '0')}.png`));
    console.log('still', s);
  }
} else {
  const dir = path.join(HERE, 'out', 'frames');
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });
  const n = Math.round(info.duration * FPS);
  const t0 = Date.now();
  for (let i = 0; i < n; i++) {
    await shoot(i / FPS, path.join(dir, `f_${String(i).padStart(5, '0')}.png`));
    if (i % 60 === 0) console.log(`frame ${i}/${n}  ${((Date.now() - t0) / 1000).toFixed(0)} s`);
  }
  const out = path.join(HERE, 'out', 'quantum_egg.mp4');
  const r = spawnSync('ffmpeg', ['-y', '-loglevel', 'error', '-framerate', String(FPS), '-i', path.join(dir, 'f_%05d.png'),
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out], { stdio: 'inherit' });
  if (r.status !== 0) throw new Error('ffmpeg failed');
  console.log('wrote', out);
}
await browser.close();
server.close();
