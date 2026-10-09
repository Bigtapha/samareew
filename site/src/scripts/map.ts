// MapLibre GL + PMTiles, loaded only when a map is shown (about 250 kB compressed).
import type { Map as MapLibreMap, StyleSpecification } from "maplibre-gl";
import { BASEMAP } from "../config";

let protocolReady = false;

export interface MapOptions {
  bounds: [number, number, number, number];
  /** Extra attribution for the data drawn on top of the basemap. */
  attribution?: string;
}

export function prefersDark(): boolean {
  const forced = document.documentElement.dataset.theme;
  if (forced) return forced === "dark";
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

export async function createMap(container: HTMLElement, options: MapOptions): Promise<MapLibreMap> {
  const [maplibregl, { Protocol }, { default: workerUrl }, style] = await Promise.all([
    import("maplibre-gl"),
    import("pmtiles"),
    // MapLibre 6 runs a module worker: let Vite bundle it with its shared chunk.
    import("maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url"),
    basemapStyle(),
  ]);
  await import("maplibre-gl/dist/maplibre-gl.css");
  if (!protocolReady) {
    maplibregl.setWorkerUrl(workerUrl);
    maplibregl.addProtocol("pmtiles", new Protocol().tile);
    protocolReady = true;
  }
  const map = new maplibregl.Map({
    container,
    style,
    bounds: options.bounds,
    fitBoundsOptions: { padding: 16 },
    attributionControl: false,
    cooperativeGestures: true,
    dragRotate: false,
    pitchWithRotate: false,
    locale: {
      "CooperativeGesturesHandler.WindowsHelpText": "Utilisez Ctrl + molette pour zoomer",
      "CooperativeGesturesHandler.MacHelpText": "Utilisez ⌘ + molette pour zoomer",
      "CooperativeGesturesHandler.MobileHelpText": "Utilisez deux doigts pour déplacer la carte",
      "NavigationControl.ZoomIn": "Zoomer",
      "NavigationControl.ZoomOut": "Dézoomer",
      "AttributionControl.ToggleAttribution": "Afficher les sources",
    },
  });
  map.touchZoomRotate.disableRotation();
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  map.addControl(
    new maplibregl.AttributionControl({ compact: true, customAttribution: options.attribution }),
    "bottom-right",
  );
  await new Promise((resolve) => map.once("load", resolve));
  container.querySelector("[data-map-loading]")?.remove();
  return map;
}

/** Absolute URL of a file in public/ (pmtiles:// and glyph URLs need a full URL). */
function siteUrl(path: string): string {
  return new URL(`${import.meta.env.BASE_URL.replace(/\/$/, "")}/${path}`, window.location.origin).href;
}

/** Absolute URL of a file copied into public/data/ by `npm run sync`. */
export const dataUrl = (path: string) => siteUrl(`data/${path}`);

/** Self-hosted Protomaps basemap (public/basemap/, built by `npm run basemap`). */
async function basemapStyle(): Promise<StyleSpecification> {
  const [{ layers, namedFlavor }, info] = await Promise.all([
    import("@protomaps/basemaps"),
    fetch(siteUrl("basemap/basemap.json")).then((r) => r.json()),
  ]);
  const dark = prefersDark();
  return {
    version: 8,
    // Not through new URL(), which would encode the {tokens}.
    glyphs: `${siteUrl("basemap/fonts")}/{fontstack}/{range}.pbf`,
    sprite: siteUrl(`basemap/sprites/${dark ? "dark" : "light"}`),
    sources: {
      protomaps: {
        type: "vector",
        url: `pmtiles://${siteUrl("basemap/basemap.pmtiles")}`,
        bounds: info.bbox,
        attribution: `<a href="https://protomaps.com">Protomaps</a> © <a href="https://www.openstreetmap.org/copyright">contributeurs OpenStreetMap</a> (${info.build.slice(0, 4)})`,
      },
    },
    layers: layers("protomaps", namedFlavor(dark ? BASEMAP.flavors.dark : BASEMAP.flavors.light), { lang: "fr" }),
  };
}

/** Id of the basemap's first label layer: data layers go below it, so place names stay readable. */
export function firstSymbolLayer(map: MapLibreMap): string | undefined {
  return map.getStyle().layers.find((l) => l.type === "symbol")?.id;
}
