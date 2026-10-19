// Bundles the Activity client into ../eventos_app/activity/web, which the app serves (and the installer ships).
//   node build.mjs            production build (minified, with .gz copies for the server to hand out)
//   node build.mjs --dev      unminified, with source maps (for debugging in a browser)
import { build } from "esbuild";
import { cp, mkdir, readdir, readFile, rm, writeFile } from "node:fs/promises";
import { gzipSync, brotliCompressSync, constants } from "node:zlib";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.resolve(here, "../eventos_app/activity/web");
const dev = process.argv.includes("--dev");

await rm(out, { recursive: true, force: true });
await mkdir(out, { recursive: true });

await build({
  entryPoints: { app: path.join(here, "src/main.jsx") },
  bundle: true,
  minify: !dev,
  sourcemap: dev ? "linked" : false,
  format: "iife",
  target: ["chrome100", "safari15"],
  jsx: "automatic",
  jsxImportSource: "preact",
  loader: { ".woff2": "file" },
  assetNames: "fonts/[name]-[hash]",
  outdir: out,
  logLevel: "info",
});
await cp(path.join(here, "src/index.html"), path.join(out, "index.html"));

// The server hands out the pre-compressed copy when the browser accepts it (a quarter of the bytes through the tunnel).
async function* files(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) yield* files(full);
    else yield full;
  }
}
if (!dev) {
  for await (const file of files(out)) {
    if (!/\.(js|css|html|svg|json)$/.test(file)) continue;
    const body = await readFile(file);
    await writeFile(`${file}.gz`, gzipSync(body, { level: 9 }));
    await writeFile(`${file}.br`, brotliCompressSync(body, { params: { [constants.BROTLI_PARAM_QUALITY]: 11 } }));
  }
}
console.log("Activity client built in", out);
