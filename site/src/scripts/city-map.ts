// City map: the PMTiles layers of outputs/site/ (one raster archive per layer) over the basemap.
import { createMap, dataUrl, firstSymbolLayer } from "./map";

interface CityMapData {
  city: string;
  bounds: [number, number, number, number];
  layers: { id: string; file: string; attribution: string; minZoom: number; maxZoom: number }[];
  image: { id: string; file: string; attribution: string } | null;
  zones: string;
  /** Known errors of the map, outlined and explained (step 7). */
  notes: { file: string; items: MapNote[] } | null;
}

interface MapNote { id: string; kindLabel: string; title: string; text: string; lon: number; lat: number }

/** Below this zoom a note is too small to see: a ring marks the place. */
const NOTE_RING_MAX_ZOOM = 12;
const NOTE_ZOOM = 13.5;

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

  if (data.notes) await addNotes(map, data.notes);

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

/** Outline of the known errors, above the place names; the explanation opens on tap or hover. */
async function addNotes(map: Awaited<ReturnType<typeof createMap>>, notes: NonNullable<CityMapData["notes"]>) {
  const [{ Popup }, all] = await Promise.all([
    import("maplibre-gl"),
    fetch(dataUrl(notes.file)).then((r) => r.json()),
  ]);
  const byId = new Map(notes.items.map((n) => [n.id, n]));
  all.features = all.features.filter((f: any) => byId.has(f.properties.id));
  map.addSource("notes", { type: "geojson", data: all });
  map.addSource("note-points", {
    type: "geojson",
    data: {
      type: "FeatureCollection",
      features: notes.items.map((n) => ({
        type: "Feature", properties: { id: n.id }, geometry: { type: "Point", coordinates: [n.lon, n.lat] },
      })),
    },
  });
  // White under black: readable on the light and dark basemaps and on the satellite image.
  map.addLayer({ id: "notes-fill", type: "fill", source: "notes", paint: { "fill-color": "#000", "fill-opacity": 0.01 } });
  map.addLayer({ id: "notes-casing", type: "line", source: "notes", paint: { "line-color": "#fff", "line-width": 4.5 } });
  map.addLayer({ id: "notes-line", type: "line", source: "notes", paint: { "line-color": "#111", "line-width": 2 } });
  map.addLayer({
    id: "notes-ring", type: "circle", source: "note-points", maxzoom: NOTE_RING_MAX_ZOOM,
    paint: { "circle-radius": 13, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": "#111", "circle-stroke-width": 2 },
  });
  map.addLayer({
    id: "notes-ring-casing", type: "circle", source: "note-points", maxzoom: NOTE_RING_MAX_ZOOM,
    paint: { "circle-radius": 15.5, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": "#fff", "circle-stroke-width": 1.5 },
  });

  const popup = new Popup({ maxWidth: "min(20rem, 80vw)", className: "note-popup" });
  function open(id: string) {
    const note = byId.get(id);
    if (!note) return;
    const box = document.createElement("div");
    const head = document.createElement("strong");
    head.textContent = note.kindLabel;
    const body = document.createElement("p");
    body.textContent = `${note.title}. ${note.text}`;
    box.append(head, body);
    popup.setLngLat([note.lon, note.lat]).setDOMContent(box).addTo(map);
  }
  for (const layer of ["notes-fill", "notes-ring"]) {
    map.on("click", layer, (e) => open(e.features![0].properties.id));
    map.on("mouseenter", layer, (e) => {
      map.getCanvas().style.cursor = "pointer";
      open(e.features![0].properties.id);
    });
    map.on("mouseleave", layer, () => (map.getCanvas().style.cursor = ""));
  }
  root.querySelectorAll<HTMLButtonElement>("button[data-note]").forEach((button) =>
    button.addEventListener("click", () => {
      const note = byId.get(button.dataset.note!);
      if (!note) return;
      map.flyTo({ center: [note.lon, note.lat], zoom: NOTE_ZOOM });
      open(note.id);
      root.querySelector<HTMLElement>("[data-map]")!.scrollIntoView({ block: "nearest" });
    }));
}
