// Build the self-hosted basemap in public/basemap/ (ignored by git):
// an OpenStreetMap extract of the study zones from the latest Protomaps daily build
// (vector PMTiles, ODbL), with the glyphs (OFL) and sprites (MIT) its style needs.
// Needs the pmtiles CLI (https://github.com/protomaps/go-pmtiles/releases) on the PATH,
// or its path in PMTILES_BIN.
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { BASEMAP } from "../src/config.ts";

const siteRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const target = join(siteRoot, "public", "basemap");
const manifest = JSON.parse(readFileSync(resolve(siteRoot, "..", "outputs", "site", "manifest.json"), "utf8"));
const ASSETS = "https://raw.githubusercontent.com/protomaps/basemaps-assets/main";

// Union of the cities' bounds, plus a margin: adding a city extends the basemap.
const all = Object.values(manifest.cities).map((c) => c.bounds);
const m = BASEMAP.marginDeg;
const bbox = [
  Math.min(...all.map((b) => b[0])) - m,
  Math.min(...all.map((b) => b[1])) - m,
  Math.max(...all.map((b) => b[2])) + m,
  Math.max(...all.map((b) => b[3])) + m,
].map((v) => Number(v.toFixed(3)));

async function download(url, path) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${response.status} ${url}`);
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, Buffer.from(await response.arrayBuffer()));
}

const builds = await (await fetch("https://build-metadata.protomaps.dev/builds.json")).json();
const build = builds.at(-1).key;
console.log(`Protomaps build ${build}, bbox ${bbox.join(",")}, zooms 0-${BASEMAP.maxZoom}`);

rmSync(target, { recursive: true, force: true });
mkdirSync(target, { recursive: true });
execFileSync(process.env.PMTILES_BIN ?? "pmtiles", [
  "extract", `https://build.protomaps.com/${build}`, join(target, "basemap.pmtiles"),
  `--bbox=${bbox.join(",")}`, `--maxzoom=${BASEMAP.maxZoom}`,
], { stdio: "inherit" });

for (const font of BASEMAP.fonts) {
  for (const start of BASEMAP.glyphRanges) {
    const range = `${start}-${start + 255}`;
    await download(`${ASSETS}/fonts/${encodeURIComponent(font)}/${range}.pbf`, join(target, "fonts", font, `${range}.pbf`));
  }
}
await download(`${ASSETS}/fonts/OFL.txt`, join(target, "fonts", "OFL.txt"));
for (const theme of ["light", "dark"]) {
  for (const suffix of ["", "@2x"]) {
    for (const ext of ["json", "png"]) {
      await download(`${ASSETS}/sprites/v4/${theme}${suffix}.${ext}`, join(target, "sprites", `${theme}${suffix}.${ext}`));
    }
  }
}

writeFileSync(join(target, "basemap.json"), JSON.stringify({
  source: `Protomaps daily build ${build} (OpenStreetMap, ODbL)`,
  build: build.replace(".pmtiles", ""),
  bbox,
  max_zoom: BASEMAP.maxZoom,
  licences: { tiles: "ODbL 1.0 (© OpenStreetMap contributors)", fonts: "SIL OFL 1.1", sprites: "MIT (tangrams/icons)" },
}, null, 1));
console.log(`Basemap written to ${target}`);
