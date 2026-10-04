// Exercise the Vercel handler (api/atlas.ts) in-process against the real API: a forwarded GET of a job status,
// a blocked path, and a missing key. Run: npx vite-node scripts/proxy_check.ts <job_id>  (reads ../.env; never prints the key)
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import handler from "../api/atlas";

const env = readFileSync(resolve(__dirname, "../../.env"), "utf-8");
const key = /MOTH_API_KEY\s*=\s*"?([^"\r\n]+)/.exec(env)?.[1]?.trim();
const job = process.argv[2];

async function call(method: string, path: string, auth?: string) {
  let code = 0;
  let body = "";
  const res = {
    status(c: number) {
      code = c;
      return res;
    },
    setHeader() {},
    send(b: string) {
      body = b;
    },
  };
  await handler({ method, query: { path }, headers: auth ? { authorization: auth } : {} }, res);
  return `${code} ${body.slice(0, 160)}`;
}

console.log("status  :", await call("GET", `jobs/${job}/status`, `Bearer ${key}`));
console.log("blocked :", await call("GET", "me", `Bearer ${key}`));
console.log("no key  :", await call("GET", `jobs/${job}/status`));
