// Build-time look-ups in the indicator table, for key figures and static charts.
import { rowsOf, type Row } from "./outputs";

const cache = new Map<string, Row[]>();
export function rows(indicator: string): Row[] {
  if (!cache.has(indicator)) cache.set(indicator, rowsOf(indicator));
  return cache.get(indicator)!;
}

/** One value: a year (``start`` null) or a period; the city itself unless ``unit`` is given. */
export function value(indicator: string, city: string, year: number, start: number | null = null,
  type = "city", unit = city): number | undefined {
  return rows(indicator).find((r) => r.city === city && r.type === type && r.unit === unit
    && r.year === year && r.start === start)?.value;
}

/** Sum over years of a yearly indicator, by unit of one type (e.g. new built-up area by ring). */
export function sumByUnit(indicator: string, city: string, type: string, from: number, to: number): Row[] {
  const out = new Map<string, Row>();
  for (const r of rows(indicator)) {
    if (r.city !== city || r.type !== type || r.year < from || r.year > to) continue;
    const prev = out.get(r.unit);
    out.set(r.unit, prev ? { ...prev, value: prev.value + r.value } : { ...r, start: from, year: to });
  }
  return [...out.values()];
}
