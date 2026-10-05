import { resolve } from "node:path";
import { defineConfig, loadEnv, type Plugin } from "vite";

// `vite preview`: plain forwarder /api/atlas/* -> api.mothquantum.com/api/v1/* (bring-your-own-key only).
const atlasProxy = {
  "/api/atlas": {
    target: "https://api.mothquantum.com",
    changeOrigin: true,
    rewrite: (p: string) => p.replace(/^\/api\/atlas/, "/api/v1"),
    headers: { "User-Agent": "scrambled-web-dev-proxy/1.0" },
  },
};

// `vite dev`: mount the real Vercel function (api/atlas.ts) so dev and production share one code path.
// The lent-key mode stays off unless ALLOW_SERVER_KEY=1 is set in the shell; MOTH_API_KEY is then read from ../.env.
function atlasFunction(): Plugin {
  return {
    name: "atlas-function",
    configureServer(server) {
      if (process.env.ALLOW_SERVER_KEY === "1" && !process.env.MOTH_API_KEY) {
        const k = loadEnv("development", resolve(__dirname, ".."), "MOTH_API_KEY").MOTH_API_KEY;
        if (k) process.env.MOTH_API_KEY = k;
      }
      server.middlewares.use("/api/atlas", async (req, res) => {
        const chunks: Buffer[] = [];
        for await (const c of req) chunks.push(c as Buffer);
        const url = new URL(req.url ?? "/", "http://dev");
        const mod = (await server.ssrLoadModule("/api/atlas.ts")) as { default: (q: unknown, s: unknown) => Promise<void> };
        await mod.default(
          { method: req.method, headers: req.headers, socket: req.socket, query: { path: url.pathname.replace(/^\/+/, "") }, body: chunks.length ? Buffer.concat(chunks).toString("utf8") : undefined },
          {
            status(code: number) {
              res.statusCode = code;
              return this;
            },
            setHeader: (k: string, v: string) => res.setHeader(k, v),
            send: (b: string) => res.end(b),
          },
        );
      });
    },
  };
}

export default defineConfig({
  base: "./",
  plugins: [atlasFunction()],
  preview: { proxy: atlasProxy },
  build: {
    outDir: "dist",
    rollupOptions: {
      input: {
        index: resolve(__dirname, "index.html"),
        explorer: resolve(__dirname, "explorer.html"),
      },
    },
  },
  test: {
    include: ["src/**/*.test.ts", "api/**/*.test.ts"],
  },
} as never);
