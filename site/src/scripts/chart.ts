// Chart template (OWID style): tabs Graphique / Carte / Tableau / Sources / Télécharger,
// city selection and state kept in the URL so that every view can be shared.
import { barChart, lineChart, ORDERED_TYPES, type ChartContext, type Row } from "../lib/charts";
import { formatValue, formatWithUnit, periodKey, periodLabel } from "../lib/format";

interface ChartData {
  slug: string;
  title: string;
  unit: string;
  period: "year" | "period";
  rows: Row[];
  cities: { slug: string; name: string; color: string; bounds: [number, number, number, number] }[];
  levels: Level[];
  boundaries: Record<string, string>;
  attribution: Record<string, string>;
}

type Tab = "graphique" | "carte" | "tableau" | "sources" | "telecharger";
type Level = "city" | "commune" | "sector" | "direction" | "ring";

interface State {
  tab: Tab;
  level: Level;
  cities: string[];
  city: string;
  time: string;
}

const LEVEL_PARAM: Record<Level, string> = {
  city: "villes", commune: "communes", sector: "secteurs", direction: "directions", ring: "anneaux",
};
const LEVEL_NOUN: Record<Level, string> = {
  city: "Villes", commune: "Communes", sector: "Secteurs", direction: "Directions", ring: "Anneaux",
};
const TABS: Tab[] = ["graphique", "carte", "tableau", "sources", "telecharger"];
const MAP_LEVELS: Level[] = ["commune", "sector"];
const SEQUENTIAL = ["#fde5c8", "#f8bd84", "#ee8a4c", "#d0592a", "#9a3412"];

const root = document.querySelector<HTMLElement>("[data-chart]")!;
const data: ChartData = JSON.parse(root.querySelector("script[type='application/json']")!.textContent!);
const $ = <T extends Element = HTMLElement>(sel: string) => root.querySelector<T>(sel)!;

const cityName = new Map(data.cities.map((c) => [c.slug, c.name]));
const cityColor = new Map(data.cities.map((c) => [c.slug, c.color]));
const times = [...new Set(data.rows.map((r) => periodKey(r.start, r.year)))].sort(compareTimes);
const mapLevels = data.levels.filter((l) => MAP_LEVELS.includes(l));

function compareTimes(a: string, b: string): number {
  // Years in order; periods by end then by start ("2016-2020", "2020-2025", "2016-2025").
  const [as, ae] = a.includes("-") ? a.split("-").map(Number) : [0, Number(a)];
  const [bs, be] = b.includes("-") ? b.split("-").map(Number) : [0, Number(b)];
  return ae - be || bs - as;
}

const defaultTime = data.period === "year"
  ? times[times.length - 1]
  : times.reduce((best, t) => (span(t) > span(best) ? t : best), times[0]);
function span(t: string): number {
  const [s, e] = t.split("-").map(Number);
  return e - s;
}

const citiesWith = (level: Level) =>
  data.cities.map((c) => c.slug).filter((slug) => data.rows.some((r) => r.type === level && r.city === slug));

// ---------- state <-> URL ----------

function readState(): State {
  const p = new URLSearchParams(window.location.search);
  const tab = TABS.includes(p.get("onglet") as Tab) ? (p.get("onglet") as Tab) : "graphique";
  const levelParam = Object.entries(LEVEL_PARAM).find(([, v]) => v === p.get("niveau"))?.[0] as Level | undefined;
  const level = levelParam && data.levels.includes(levelParam) ? levelParam : data.levels[0];
  const known = new Set(data.cities.map((c) => c.slug));
  const listed = (p.get("villes") ?? "").split(",").filter((c) => known.has(c));
  const cities = listed.length ? listed : citiesWith("city");
  const city = known.has(p.get("ville") ?? "") ? p.get("ville")! : data.cities[0].slug;
  const time = times.includes(p.get("periode") ?? "") ? p.get("periode")! : defaultTime;
  return normalise({ tab: tab === "carte" && !mapLevels.length ? "graphique" : tab, level, cities, city, time });
}

/** Keep the state consistent: a sub-city level needs a city that has data at that level. */
function normalise(s: State): State {
  const level = levelFor(s);
  if (level !== "city") {
    const available = citiesWith(level);
    if (!available.includes(s.city)) s.city = available[0];
  }
  return s;
}

/** The map only shows communes or sectors: "city" falls back to communes. */
function levelFor(s: State): Level {
  if (s.tab === "carte" && !MAP_LEVELS.includes(s.level)) return mapLevels[0];
  return s.level;
}

function writeState(s: State) {
  const p = new URLSearchParams();
  if (s.tab !== "graphique") p.set("onglet", s.tab);
  if (s.level !== data.levels[0]) p.set("niveau", LEVEL_PARAM[s.level]);
  if (s.level === "city" && s.cities.join() !== citiesWith("city").join()) p.set("villes", s.cities.join(","));
  if (levelFor(s) !== "city") p.set("ville", s.city);
  if (s.time !== defaultTime) p.set("periode", s.time);
  const query = p.toString();
  history.replaceState(null, "", query ? `?${query}` : window.location.pathname);
}

let state = readState();

function update(patch: Partial<State>) {
  state = normalise({ ...state, ...patch });
  writeState(state);
  render();
}

// ---------- controls ----------

function renderControls() {
  const level = levelFor(state);
  const showLevels = state.tab === "carte" ? mapLevels : data.levels;

  const levelBox = $("[data-control='level']");
  levelBox.hidden = showLevels.length < 2 || !["graphique", "carte", "tableau"].includes(state.tab);
  const levelSelect = $<HTMLSelectElement>("[data-control='level'] select");
  levelSelect.replaceChildren(...showLevels.map((l) => new Option(LEVEL_NOUN[l], l, false, l === level)));

  const citiesBox = $("[data-control='cities']");
  citiesBox.hidden = level !== "city" || !["graphique", "tableau"].includes(state.tab);
  citiesBox.querySelectorAll<HTMLInputElement>("input").forEach((input) => {
    input.checked = state.cities.includes(input.value);
  });

  const cityBox = $("[data-control='city']");
  const available = level === "city" ? [] : citiesWith(level);
  cityBox.hidden = level === "city" || available.length < 2 || !["graphique", "carte", "tableau"].includes(state.tab);
  const citySelect = $<HTMLSelectElement>("[data-control='city'] select");
  citySelect.replaceChildren(...available.map((c) => new Option(cityName.get(c)!, c, false, c === state.city)));

  // One year (or period) to show, except on the line chart and in the table (all of them).
  const timeBox = $("[data-control='time']");
  const lineChart = state.tab === "graphique" && level === "city" && data.period === "year";
  timeBox.hidden = times.length < 2 || lineChart || !["graphique", "carte"].includes(state.tab);
  $("[data-control='time'] span").textContent = data.period === "year" ? "Année" : "Période";
  const timeSelect = $<HTMLSelectElement>("[data-control='time'] select");
  timeSelect.replaceChildren(...[...times].reverse().map((t) => new Option(periodLabel(t), t, false, t === state.time)));
}

$("[data-control='level'] select").addEventListener("change", (e) =>
  update({ level: (e.target as HTMLSelectElement).value as Level }));
$("[data-control='city'] select").addEventListener("change", (e) =>
  update({ city: (e.target as HTMLSelectElement).value }));
$("[data-control='time'] select").addEventListener("change", (e) =>
  update({ time: (e.target as HTMLSelectElement).value }));
$("[data-control='cities']").addEventListener("change", () => {
  const checked = [...root.querySelectorAll<HTMLInputElement>("[data-control='cities'] input:checked")].map((i) => i.value);
  update({ cities: checked });
});
root.querySelectorAll<HTMLButtonElement>("[role='tab']").forEach((button) => {
  button.addEventListener("click", () => update({ tab: button.dataset.tab as Tab }));
  button.addEventListener("keydown", (e) => {
    const tabs = [...root.querySelectorAll<HTMLButtonElement>("[role='tab']:not([hidden])")];
    const i = tabs.indexOf(button);
    const next = e.key === "ArrowRight" ? tabs[(i + 1) % tabs.length] : e.key === "ArrowLeft" ? tabs[(i - 1 + tabs.length) % tabs.length] : null;
    if (next) {
      next.focus();
      update({ tab: next.dataset.tab as Tab });
    }
  });
});

// ---------- rendering ----------

const rowsAt = (level: Level, city?: string) =>
  data.rows.filter((r) => r.type === level && (city === undefined || r.city === city));

function render() {
  root.querySelectorAll<HTMLButtonElement>("[role='tab']").forEach((b) => {
    const selected = b.dataset.tab === state.tab;
    b.setAttribute("aria-selected", String(selected));
    b.tabIndex = selected ? 0 : -1;
  });
  root.querySelectorAll<HTMLElement>("[role='tabpanel']").forEach((panel) => {
    panel.hidden = panel.dataset.panel !== state.tab;
  });
  renderControls();
  $("[data-caption]").textContent = caption();
  if (state.tab === "graphique") renderChart();
  if (state.tab === "tableau") renderTable();
  if (state.tab === "carte") renderMap();
}

function caption(): string {
  const level = levelFor(state);
  const where = level === "city" ? "" : ` · ${LEVEL_NOUN[level].toLowerCase()} de ${cityName.get(state.city)}`;
  const lineChart = state.tab === "graphique" && level === "city" && data.period === "year";
  const when = state.tab === "tableau" || lineChart ? "" : ` · ${periodLabel(state.time)}`;
  return `${data.unit === "indice" || data.unit === "ratio" ? data.unit : `en ${data.unit}`}${where}${when}`;
}

function chartContext(interactive: boolean): ChartContext {
  const accent = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#b8410e";
  return { unit: data.unit, cityName, cityColor, accent, interactive };
}

/** The chart of the current state, at a given width; null when nothing is selected. */
function chartFigure(width: number, interactive: boolean): Element | null {
  const level = levelFor(state);
  const ctx = chartContext(interactive);
  if (level === "city" && data.period === "year") {
    const rows = rowsAt("city").filter((r) => state.cities.includes(r.city));
    return rows.length ? lineChart(rows, state.cities, width, ctx) : null;
  }
  const rows = (level === "city" ? rowsAt("city").filter((r) => state.cities.includes(r.city)) : rowsAt(level, state.city))
    .filter((r) => periodKey(r.start, r.year) === state.time);
  return rows.length ? barChart(rows, width, ctx) : null;
}

function renderChart() {
  const box = $("[data-panel='graphique'] [data-figure]");
  const figure = chartFigure(Math.max(280, box.clientWidth), true);
  box.replaceChildren(figure ?? message(levelFor(state) === "city"
    ? "Choisissez au moins une ville." : "Pas de valeur pour cette sélection."));
}

function renderTable() {
  const level = levelFor(state);
  const rows = level === "city" ? rowsAt("city").filter((r) => state.cities.includes(r.city)) : rowsAt(level, state.city);
  const box = $("[data-panel='tableau'] [data-figure]");
  if (!rows.length) {
    box.replaceChildren(message("Choisissez au moins une ville."));
    return;
  }
  const columns = times.filter((t) => rows.some((r) => periodKey(r.start, r.year) === t));
  const units = [...new Map(rows.map((r) => [`${r.city}|${r.unit}`, r])).values()];
  if (ORDERED_TYPES.includes(level)) units.sort((a, b) => a.order - b.order);
  else if (level !== "city") units.sort((a, b) => a.label.localeCompare(b.label, "fr"));
  const value = new Map(rows.map((r) => [`${r.city}|${r.unit}|${periodKey(r.start, r.year)}`, r.value]));

  const table = document.createElement("table");
  const head = table.createTHead().insertRow();
  [LEVEL_NOUN[level].replace(/s$/, ""), ...columns.map(periodLabel)].forEach((text) => {
    const th = document.createElement("th");
    th.scope = "col";
    th.textContent = text;
    head.append(th);
  });
  const body = table.createTBody();
  for (const u of units) {
    const tr = body.insertRow();
    const th = document.createElement("th");
    th.scope = "row";
    th.textContent = level === "city" ? cityName.get(u.city)! : u.label;
    tr.append(th);
    for (const t of columns) {
      const v = value.get(`${u.city}|${u.unit}|${t}`);
      tr.insertCell().textContent = v === undefined ? "–" : formatValue(v, data.unit);
    }
  }
  const scroll = document.createElement("div");
  scroll.className = "table-scroll";
  scroll.append(table);
  box.replaceChildren(scroll);
}

// ---------- map ----------

let mapReady: Promise<import("maplibre-gl").Map> | null = null;
let mapCity = "";
const geojson = new Map<string, Promise<any>>();

function loadBoundaries(level: Level, url: string): Promise<any> {
  if (!geojson.has(level)) geojson.set(level, fetch(url).then((r) => r.json()));
  return geojson.get(level)!;
}

async function renderMap() {
  const level = levelFor(state);
  const box = $<HTMLElement>("[data-panel='carte'] [data-map]");
  const legend = $("[data-panel='carte'] [data-legend]");
  const { createMap, dataUrl, firstSymbolLayer } = await import("./map");
  const city = data.cities.find((c) => c.slug === state.city)!;
  if (!mapReady) {
    mapReady = createMap(box, { bounds: city.bounds, attribution: data.attribution[level] });
    mapCity = city.slug;
  }
  const map = await mapReady;
  const boundaries = await loadBoundaries(level, dataUrl(data.boundaries[level]));
  const values = rowsAt(level).filter((r) => periodKey(r.start, r.year) === state.time);
  // Same classes for every city so that colours compare across cities.
  const breaks = quantileBreaks(values.map((r) => r.value), SEQUENTIAL.length);
  const byUnit = new Map(values.map((r) => [`${r.city}|${r.unit}`, r.value]));
  const features = boundaries.features
    .filter((f: any) => f.properties.city === state.city)
    .map((f: any) => {
      const v = byUnit.get(`${f.properties.city}|${f.properties.unit}`);
      return { ...f, properties: { ...f.properties, value: v ?? null, color: v === undefined ? null : colorOf(v, breaks) } };
    });
  const fc = { type: "FeatureCollection", features };
  const source = map.getSource("units") as import("maplibre-gl").GeoJSONSource | undefined;
  if (source) source.setData(fc as any);
  else {
    map.addSource("units", { type: "geojson", data: fc as any });
    const labels = firstSymbolLayer(map);
    map.addLayer({
      id: "units-fill",
      type: "fill",
      source: "units",
      paint: { "fill-color": ["coalesce", ["get", "color"], "rgba(0,0,0,0)"], "fill-opacity": 0.8 },
    }, labels);
    map.addLayer({
      id: "units-line",
      type: "line",
      source: "units",
      paint: { "line-color": "#5d5a54", "line-width": 0.6 },
    }, labels);
    addMapTooltip(map);
  }
  if (mapCity !== city.slug) {
    map.fitBounds(city.bounds, { padding: 16, animate: false });
    mapCity = city.slug;
  }
  map.resize();
  renderLegend(legend, breaks, values.length > 0);
}

function quantileBreaks(values: number[], classes: number): number[] {
  const sorted = [...values].sort((a, b) => a - b);
  const breaks: number[] = [];
  for (let k = 1; k < classes; k++) breaks.push(sorted[Math.floor((k / classes) * (sorted.length - 1))]);
  return [...new Set(breaks.map((b) => Number(b.toPrecision(2))))];
}

function colorOf(v: number, breaks: number[]): string {
  const k = breaks.findIndex((b) => v < b);
  return SEQUENTIAL[k === -1 ? breaks.length : k];
}

function renderLegend(el: Element, breaks: number[], any: boolean) {
  if (!any) {
    el.replaceChildren(message("Pas de valeur pour cette sélection."));
    return;
  }
  const items = SEQUENTIAL.slice(0, breaks.length + 1).map((color, k) => {
    const lo = k === 0 ? null : breaks[k - 1];
    const hi = k === breaks.length ? null : breaks[k];
    const text = lo === null ? `moins de ${formatBreak(hi!)}`
      : hi === null ? `${formatBreak(lo)} et plus`
      : `${formatBreak(lo)} à ${formatBreak(hi)}`;
    const li = document.createElement("li");
    li.innerHTML = `<span class="swatch" style="background:${color}"></span>`;
    li.append(text);
    return li;
  });
  const none = document.createElement("li");
  none.innerHTML = `<span class="swatch swatch-none"></span>`;
  none.append("pas de valeur");
  const list = document.createElement("ul");
  list.className = "legend";
  list.append(...items, none);
  el.replaceChildren(list);
}

/** Class limits have two significant digits: no trailing ",0". */
function formatBreak(v: number): string {
  return Number.isInteger(v) ? formatValue(v, "") : formatValue(v, data.unit);
}

function addMapTooltip(map: import("maplibre-gl").Map) {
  import("maplibre-gl").then(({ Popup }) => {
    const popup = new Popup({ closeButton: false, closeOnClick: true, maxWidth: "16rem" });
    map.on("click", "units-fill", (e) => {
      const p = e.features?.[0]?.properties;
      if (!p) return;
      const value = p.value === null || p.value === undefined || p.value === "null"
        ? "pas de valeur" : formatWithUnit(Number(p.value), data.unit);
      const strong = document.createElement("strong");
      strong.textContent = p.label;
      const div = document.createElement("div");
      div.append(strong, document.createElement("br"), value);
      popup.setLngLat(e.lngLat).setDOMContent(div).addTo(map);
    });
    map.on("mouseenter", "units-fill", () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", "units-fill", () => (map.getCanvas().style.cursor = ""));
  });
}

// ---------- chart image (SVG, PNG) ----------

const EXPORT_WIDTH = 720;

/** Standalone SVG of the chart with its title, caption and source, light colours. */
function exportSvg(): { svg: string; width: number; height: number } | null {
  const savedTab = state.tab;
  state.tab = "graphique";                      // caption and levels of the chart view
  const figure = chartFigure(EXPORT_WIDTH - 32, false);
  const sub = caption();
  state.tab = savedTab;
  if (!figure) return null;
  const chartHeight = Number(figure.getAttribute("height"));
  const title = escapeXml(data.title);
  const source = escapeXml(`${$("[data-source]").textContent?.replace(/\s+/g, " ").trim()} · ${window.location.href}`);
  const top = 64;
  const height = top + chartHeight + 44;
  figure.setAttribute("x", "16");
  figure.setAttribute("y", String(top));
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${EXPORT_WIDTH}" height="${height}" viewBox="0 0 ${EXPORT_WIDTH} ${height}" style="color:#1d1c1a;font-family:system-ui,sans-serif">`
    + `<rect width="100%" height="100%" fill="#ffffff"/>`
    + `<text x="16" y="30" font-size="20" font-weight="700" fill="#1d1c1a">${title}</text>`
    + `<text x="16" y="52" font-size="13" fill="#5d5a54">${escapeXml(sub)}</text>`
    + new XMLSerializer().serializeToString(figure)
    + `<text x="16" y="${height - 16}" font-size="11" fill="#5d5a54">${source}</text></svg>`;
  return { svg, width: EXPORT_WIDTH, height };
}

function escapeXml(text: string): string {
  return text.replace(/[<>&"]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;" })[c]!);
}

function save(blob: Blob, name: string) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

root.querySelector("[data-export='svg']")?.addEventListener("click", () => {
  const out = exportSvg();
  if (out) save(new Blob([out.svg], { type: "image/svg+xml" }), `${data.slug}.svg`);
});
root.querySelector("[data-export='png']")?.addEventListener("click", () => {
  const out = exportSvg();
  if (!out) return;
  const image = new Image();
  image.onload = () => {
    const canvas = document.createElement("canvas");
    canvas.width = out.width * 2;
    canvas.height = out.height * 2;
    const context = canvas.getContext("2d")!;
    context.scale(2, 2);
    context.drawImage(image, 0, 0);
    canvas.toBlob((blob) => blob && save(blob, `${data.slug}.png`), "image/png");
  };
  image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(out.svg)}`;
});

function message(text: string): Element {
  const p = document.createElement("p");
  p.className = "muted";
  p.textContent = text;
  return p;
}

let lastWidth = 0;
new ResizeObserver(() => {
  const width = $("[data-panel='graphique']").clientWidth;
  if (state.tab === "graphique" && Math.abs(width - lastWidth) > 8) {
    lastWidth = width;
    renderChart();
  }
}).observe(root);

render();
