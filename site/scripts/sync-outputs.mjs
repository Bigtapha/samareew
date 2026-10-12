// Copy the files the browser needs from ../outputs into public/data/.
// The site reads only outputs/ (ROADMAP §2): pages read the tables at build time,
// the browser fetches map tiles, boundaries and downloads from public/data/.
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const siteRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const outputs = resolve(siteRoot, "..", "outputs");
const target = join(siteRoot, "public", "data");

const manifestPath = join(outputs, "site", "manifest.json");
if (!existsSync(manifestPath)) {
  console.error(`Missing ${manifestPath}: run \`python -m pipeline.s7_site_data\` first.`);
  process.exit(1);
}
const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));

const files = [
  ["site/manifest.json", "manifest.json"],
  ["site/" + manifest.validation, manifest.validation],
  ...Object.values(manifest.layers).map((l) => ["site/" + l.file, l.file]),
  ...Object.values(manifest.images ?? {}).map((l) => ["site/" + l.file, l.file]),
  ...Object.values(manifest.footprints?.cities ?? {}).map((f) => ["site/" + f.file, f.file]),
  ...Object.values(manifest.boundaries).map((b) => ["site/" + b.file, b.file]),
  ...(manifest.notes ? [["site/" + manifest.notes.file, manifest.notes.file]] : []),
  ["tables/indicators.json", "tables/indicators.json"],
  ["tables/indicators.csv", "tables/indicators.csv"],
  ["tables/units.csv", "tables/units.csv"],
];

const missing = files.filter(([src]) => !existsSync(join(outputs, src)));
if (missing.length) {
  console.error("Missing in outputs/ (the .pmtiles archives are rebuilt by "
    + "`python -m pipeline.s7_site_data`):\n  " + missing.map(([s]) => s).join("\n  "));
  process.exit(1);
}

rmSync(target, { recursive: true, force: true });
for (const [src, dst] of files) {
  mkdirSync(dirname(join(target, dst)), { recursive: true });
  cpSync(join(outputs, src), join(target, dst));
}
console.log(`Copied ${files.length} files from outputs/ to public/data/`);
