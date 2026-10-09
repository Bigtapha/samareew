// Number formatting shared by pages (build time) and scripts (browser).

const DIGITS: Record<string, number> = { ratio: 2, "%": 1 };

const formatters = new Map<number, Intl.NumberFormat>();

export function formatValue(value: number, unit: string): string {
  const digits = DIGITS[unit] ?? 0;
  let f = formatters.get(digits);
  if (!f) {
    f = new Intl.NumberFormat("fr-FR", { minimumFractionDigits: digits, maximumFractionDigits: digits });
    formatters.set(digits, f);
  }
  return f.format(value);
}

/** Value with its unit, "12 345 ha", "38,2 %"; indices and ratios have no unit. */
export function formatWithUnit(value: number, unit: string): string {
  const v = formatValue(value, unit);
  return unit === "indice" || unit === "ratio" ? v : `${v} ${unit}`;
}

export const periodKey = (start: number | null, end: number) => (start === null ? String(end) : `${start}-${end}`);
export const periodLabel = (key: string) => key.replace("-", "–");
