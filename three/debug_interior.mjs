// Dev aid: render the raw blur-core-v1 egg meshes (no shell) to out/debug/ for inspection.
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const server = http.createServer((req, res) => {
  const url = decodeURIComponent(req.url.split('?')[0]);
  const file = url.startsWith('/node_modules/') ? path.join(HERE, url) : path.join(HERE, 'web', url === '/' ? 'index.html' : url);
  if (!fs.existsSync(file)) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'Content-Type': file.endsWith('.html') ? 'text/html' : 'text/javascript' });
  fs.createReadStream(file).pipe(res);
});
await new Promise((r) => server.listen(0, '127.0.0.1', r));
const browser = await chromium.launch({ channel: 'msedge', args: ['--use-angle=d3d11', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: 1080, height: 1080 } });
await page.goto(`http://127.0.0.1:${server.address().port}/`);
await page.waitForFunction(() => window.__ready === true);
const dir = path.join(HERE, 'out', 'debug');
fs.mkdirSync(dir, { recursive: true });
for (const name of process.argv.slice(2)) {
  await page.evaluate((n) => window.__debugInterior(n), name);
  await page.screenshot({ path: path.join(dir, `${name}.png`) });
}
await browser.close();
server.close();
