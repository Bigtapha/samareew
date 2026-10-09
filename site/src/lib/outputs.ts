// Build-time access to ../outputs (the only data source of the site).
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { csvParse } from "d3-dsv";

const OUTPUTS = resolve(process.cwd(), "..", "outputs");
const readJson = (path: string) => JSON.parse(readFileSync(resolve(OUTPUTS, path), "utf8"));
const readCsv = (path: string) => csvParse(readFileSync(resolve(OUTPUTS, path), "utf8"));

export interface City {
  slug: string;
  name: string;
  bounds: [number, number, number, number];
  centre: [number, number];
}

export interface IndicatorSheet {
  slug: string;
  title: string;
  unit: string;
  definition: string;
  period: "year" | "period";
  sources: string[];
  method: string;
  reliability: string;
}

/** One value of the long table; `start` is set for period indicators. */
export type { Row } from "./charts";
import type { Row } from "./charts";

export const manifest = readJson("site/manifest.json");
export const catalogue = readJson("tables/indicators.json");
export const validation = readJson(`site/${manifest.validation}`);

export const cities: City[] = Object.entries(manifest.cities).map(
  ([slug, c]: [string, any]) => ({ slug, ...c }),
);

export const indicators: IndicatorSheet[] = Object.entries(catalogue.indicators).map(
  ([slug, s]: [string, any]) => ({ slug, ...s }),
);

const units = readCsv("tables/units.csv");
const unitKey = (city?: string, type?: string, unit?: string) => `${city}|${type}|${unit}`;
const labels = new Map(units.map((u): [string, string] => [unitKey(u.city, u.unit_type, u.unit), u.label!]));
const orders = new Map(units.map((u, i): [string, number] => [unitKey(u.city, u.unit_type, u.unit), i]));

const allRows = readCsv("tables/indicators.csv");

export function rowsOf(indicator: string, unitTypes?: readonly string[]): Row[] {
  return allRows
    .filter((r) => r.indicator === indicator && (!unitTypes || unitTypes.includes(r.unit_type!)))
    .map((r) => ({
      city: r.city!,
      type: r.unit_type!,
      unit: r.unit!,
      label: labels.get(unitKey(r.city, r.unit_type, r.unit)) ?? r.unit!,
      order: orders.get(unitKey(r.city, r.unit_type, r.unit)) ?? 0,
      start: r.year_start ? Number(r.year_start) : null,
      year: Number(r.year),
      value: Number(r.value),
    }));
}
