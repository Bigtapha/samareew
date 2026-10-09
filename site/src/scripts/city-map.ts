// City map: the PMTiles layers of outputs/site/ (one raster archive per layer) over the basemap.
import { createMap, dataUrl, firstSymbolLayer } from "./map";

interface CityMapData {
  city: string;
  bounds: [number, number, number, number];
  layers: { id: string; file: string; attribution: string; minZoom: number; maxZoom: number }[];
  image: { id: string; file: string; attribution: string } | null;
  zones: string;
}

/** Opacity of the data layers over the basemap, and over the satellite image by default. */
const OPACITY = 0.9;
const OPACITY_ON_IMAGE = 0.6;

const root = document.querySelector<HTMLElement>("[data-city-map]")!;
const data: CityMapData = JSON.parse(root.querySelector("script[type='application/json']")!.textContent!);
const radios = [...root.querySelectorAll<HTMLInputElement>("input[name='layer']")];
const legends = [...root.querySelectorAll<HTMLElement>("[data-layer-legend]")];

const imageBox = root.querySelector<HTMLInputElement>("input[name='image']");
const opacityBox = root.querySelector<HTMLElement>("[data-opacity]");
const opacityInput = root.querySelector<HTMLInputElement>("[data-opacity] input");

const params = new URLSearchParams(window.location.search);
const initial = params.get("couche");
if (radios.some((r) => r.value === initial)) radios.forEach((r) => (r.checked = r.value === initial));
if (imageBox) imageBox.checked = params.get("image") === "1";

// MapLibre weighs about 430 kB: load it only when the map comes near the screen
// (on a phone, the map is below the key figures).
const container = root.querySelector<HTMLElement>("[data-map]")!;
const observer = new IntersectionObserver((entries) => {
  if (entries.some((e) => e.isIntersecting)) {
    observer.disconnect();
    init();
  }
}, { rootMargin: "200px" });
observer.observe(container);

async function init() {
  const map = await createMap(container, {
    bounds: data.bounds,
    attribution: data.layers[0].attribution,
  });
  const labels = firstSymbolLayer(map);

  // The satellite image is added only when asked for: nothing is downloaded before.
  function showImage(on: boolean) {
    if (!data.image) return;
    if (on && !map.getLayer(data.image.id)) {
      map.addSource(data.image.id, {
        type: "raster",
        url: `pmtiles://${dataUrl(data.image.file)}`,
        tileSize: 256,
        attribution: data.image.attribution,
      });
      map.addLayer({ id: data.image.id, type: "raster", source: data.image.id }, data.layers[0].id);
    }
    if (map.getLayer(data.image.id)) map.setLayoutProperty(data.image.id, "visibility", on ? "visible" : "none");
    opacityBox!.hidden = !on;
    opacityInput!.value = String(Math.round((on ? OPACITY_ON_IMAGE : OPACITY) * 100));
    setOpacity(on ? OPACITY_ON_IMAGE : OPACITY);
  }

  function setOpacity(value: number) {
    for (const layer of data.layers) map.setPaintProperty(layer.id, "raster-opacity", value);
  }

  for (const layer of data.layers) {
    map.addSource(layer.id, {
      type: "raster",
      url: `pmtiles://${dataUrl(layer.file)}`,
      tileSize: 256,
    });
    map.addLayer({
      id: layer.id,
      type: "raster",
      source: layer.id,
      layout: { visibility: "none" },
      // Classes, not a gradient: no blending between pixels when zooming in.
      paint: { "raster-resampling": "nearest", "raster-opacity": OPACITY },
    }, labels);
  }

  const zones = await fetch(dataUrl(data.zones)).then((r) => r.json());
  zones.features = zones.features.filter((f: any) => f.properties.city === data.city);
  map.addSource("zone", { type: "geojson", data: zones });
  map.addLayer({
    id: "zone",
    type: "line",
    source: "zone",
    paint: { "line-color": "#5d5a54", "line-width": 1.2, "line-dasharray": [3, 2] },
  }, labels);

  function show(id: string) {
    for (const layer of data.layers) map.setLayoutProperty(layer.id, "visibility", layer.id === id ? "visible" : "none");
    legends.forEach((l) => (l.hidden = l.dataset.layerLegend !== id));
    writeUrl();
  }

  function writeUrl() {
    const p = new URLSearchParams();
    const layer = radios.find((r) => r.checked)!.value;
    if (layer !== data.layers[0].id) p.set("couche", layer);
    if (imageBox?.checked) p.set("image", "1");
    history.replaceState(null, "", p.size ? `?${p}` : window.location.pathname);
  }

  radios.forEach((r) => r.addEventListener("change", () => show(r.value)));
  imageBox?.addEventListener("change", () => {
    showImage(imageBox.checked);
    writeUrl();
  });
  opacityInput?.addEventListener("input", () => setOpacity(Number(opacityInput.value) / 100));
  show(radios.find((r) => r.checked)!.value);
  showImage(!!imageBox?.checked);
}
