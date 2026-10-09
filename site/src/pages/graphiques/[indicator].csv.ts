// One CSV per chart, built at compile time from outputs/tables/.
import type { APIRoute } from "astro";
import { csvFormat } from "d3-dsv";
import { indicators, rowsOf } from "../../lib/outputs";
import { TEMPLATE_UNIT_TYPES } from "../../config";

export function getStaticPaths() {
  return indicators.map((sheet) => ({ params: { indicator: sheet.slug } }));
}

export const GET: APIRoute = ({ params }) => {
  const rows = rowsOf(params.indicator!, TEMPLATE_UNIT_TYPES).map((r) => ({
    indicator: params.indicator,
    city: r.city,
    unit_type: r.type,
    unit: r.unit,
    label: r.label,
    year_start: r.start ?? "",
    year: r.year,
    value: r.value,
  }));
  return new Response(csvFormat(rows), { headers: { "Content-Type": "text/csv; charset=utf-8" } });
};
