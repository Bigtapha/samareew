// Chart builders shared by the interactive template (browser) and the static pages (build
// time, SVG without JavaScript). Pass `document` from linkedom when rendering on the server.
import * as Plot from "@observablehq/plot";
import { formatValue, formatWithUnit } from "./format";

export interface Row {
  city: string;
  type: string;
  unit: string;
  label: string;
  start: number | null;
  year: number;
  value: number;
  /** Position of the unit in outputs/tables/units.csv (directions N..NO, rings outwards). */
  order: number;
}

export interface ChartContext {
  unit: string;
  cityName: Map<string, string>;
  cityColor: Map<string, string>;
  /** Bar colour when bars are not cities (a colour, not a CSS variable: SVG export). */
  accent: string;
  /** Pointer tooltips (browser only). */
  interactive?: boolean;
  document?: Document;
}

/** Units drawn in their natural order rather than sorted by value. */
export const ORDERED_TYPES = ["direction", "ring"];

/** Lines over the years, one per city, labelled at their end (no legend to decode). */
export function lineChart(rows: Row[], cities: string[], width: number, ctx: ChartContext): SVGSVGElement | HTMLElement {
  const years = rows.map((r) => r.year);
  const height = Math.round(Math.min(420, Math.max(260, width * 0.62)));
  const margin = { top: 16, right: 64, bottom: 28, left: 52 };
  const values = rows.map((r) => r.value);
  const zero = ["ha", "habitants", "%"].includes(ctx.unit);
  const yDomain = [zero ? 0 : Math.min(...values), Math.max(...values)];
  const y = Plot.scale({ y: { domain: yDomain, nice: true, range: [height - margin.bottom, margin.top] } });
  const last = cities
    .map((c) => rows.filter((r) => r.city === c).at(-1))
    .filter((r): r is Row => !!r);
  const labelY = spreadLabels(last.map((r) => y.apply(r.value) as number), 15, [margin.top, height - margin.bottom]);
  return Plot.plot({
    document: ctx.document,
    width,
    height,
    marginTop: margin.top,
    marginRight: margin.right,
    marginBottom: margin.bottom,
    marginLeft: margin.left,
    x: { domain: [Math.min(...years), Math.max(...years)], tickFormat: "d", ticks: width < 480 ? 5 : 10, label: null },
    y: { domain: y.domain, grid: true, label: null, tickFormat: (v: number) => formatValue(v, ctx.unit) },
    color: { domain: [...ctx.cityColor.keys()], range: [...ctx.cityColor.values()] },
    marks: [
      Plot.ruleY(zero ? [0] : []),
      Plot.line(rows, { x: "year", y: "value", z: "city", stroke: "city", strokeWidth: 2 }),
      Plot.dot(rows, { x: "year", y: "value", fill: "city", r: 2.5 }),
      Plot.text(last, {
        x: "year",
        y: (_: Row, i: number) => y.invert!(labelY[i]),
        text: (r: Row) => ctx.cityName.get(r.city),
        fill: "city",
        textAnchor: "start",
        dx: 8,
        fontWeight: 600,
        fontSize: 12,
      }),
      ctx.interactive
        ? Plot.tip(rows, Plot.pointer({
          x: "year",
          y: "value",
          title: (r: Row) => `${ctx.cityName.get(r.city)}, ${r.year}\n${formatWithUnit(r.value, ctx.unit)}`,
        }))
        : null,
    ],
  });
}

/** Push overlapping labels apart, keeping their order (positions in pixels). */
export function spreadLabels(ys: number[], gap: number, [top, bottom]: [number, number]): number[] {
  const order = ys.map((y, i) => ({ y, i })).sort((a, b) => a.y - b.y);
  for (let k = 1; k < order.length; k++) {
    order[k].y = Math.max(order[k].y, order[k - 1].y + gap);
  }
  const overflow = order.length ? order[order.length - 1].y - bottom : 0;
  if (overflow > 0) order.forEach((o) => (o.y -= overflow));
  for (let k = order.length - 2; k >= 0; k--) {
    order[k].y = Math.max(top, Math.min(order[k].y, order[k + 1].y - gap));
  }
  const out = new Array<number>(ys.length);
  order.forEach((o) => (out[o.i] = o.y));
  return out;
}

/**
 * Horizontal bars for one year or period: cities (in their colours), or the units of one
 * city, sorted by value except directions and rings, which keep their natural order.
 */
export function barChart(rows: Row[], width: number, ctx: ChartContext,
  ordered = ORDERED_TYPES.includes(rows[0]?.type)): SVGSVGElement | HTMLElement {
  const sorted = [...rows].sort((a, b) => (ordered ? a.order - b.order : b.value - a.value));
  const longest = Math.max(...sorted.map((r) => r.label.length));
  const marginLeft = Math.min(width * 0.42, 12 + longest * 6.6);
  const negative = Math.min(...sorted.map((r) => r.value)) < 0;
  return Plot.plot({
    document: ctx.document,
    width,
    height: 30 + sorted.length * 24,
    marginLeft,
    marginRight: 56,
    marginTop: 4,
    marginBottom: 24,
    x: { grid: true, label: null, tickFormat: (v: number) => formatValue(v, ctx.unit), ticks: width < 480 ? 3 : 6 },
    y: { domain: sorted.map((r) => r.label), label: null, tickSize: 0 },
    marks: [
      Plot.barX(sorted, {
        x: "value",
        y: "label",
        fill: (r: Row) => (r.type === "city" ? ctx.cityColor.get(r.city) : ctx.accent),
        insetTop: 3,
        insetBottom: 3,
      }),
      Plot.ruleX([0]),
      Plot.text(sorted, {
        x: "value",
        y: "label",
        text: (r: Row) => formatValue(r.value, ctx.unit),
        textAnchor: negative ? "middle" : "start",
        dx: negative ? 0 : 4,
        fontSize: 11,
      }),
    ],
  });
}
