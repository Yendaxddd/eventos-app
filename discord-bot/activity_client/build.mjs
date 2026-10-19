// Bundles the Activity client into ../eventos_app/activity/web, which the app serves (and the installer ships).
import { build } from "esbuild";
import { cp, mkdir, rm } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.resolve(here, "../eventos_app/activity/web");

await rm(out, { recursive: true, force: true });
await mkdir(out, { recursive: true });
await build({
  entryPoints: [path.join(here, "src/app.js")],
  bundle: true,
  minify: true,
  sourcemap: false,
  format: "iife",
  target: ["chrome100", "safari15"],
  outfile: path.join(out, "app.js"),
  logLevel: "info",
});
await cp(path.join(here, "src/index.html"), path.join(out, "index.html"));
await cp(path.join(here, "src/style.css"), path.join(out, "style.css"));
console.log("Activity client built in", out);
