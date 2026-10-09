// Site settings. Data settings live in outputs/ (manifest.json, indicators.json).

/** One colour per city, the same on every chart and map (order = display order). */
export const CITY_COLORS: Record<string, string> = {
  dakar: "#2f6db5",
  touba: "#b8466a",
  thies: "#1d8f8a",
  mbour: "#b86e14",
};

/** Methodology links point to the repository until the site has its own method pages. */
export const REPO_URL = "https://github.com/Bigtapha/samareew";
export const METHOD_URL = `${REPO_URL}/blob/main/METHODOLOGIE.md`;
/** Assets of the latest release (step 8): the names never change, so these links stay valid. */
export const DATA_ZIP_URL = `${REPO_URL}/releases/latest/download/samareew-data.zip`;
export const RELEASES_URL = `${REPO_URL}/releases`;
export const AUTHOR = "Moustapha Cisse";

/** Unit types shown in the chart template, in the order of the "Niveau" menu. */
export const TEMPLATE_UNIT_TYPES = ["city", "commune", "sector", "direction", "ring"] as const;

/**
 * Basemap (decided 09/10/2026): OpenStreetMap extract from the Protomaps daily build,
 * served with the site like the data tiles (no third-party server, no key).
 * Rebuilt by `npm run basemap` into public/basemap/ (ignored by git).
 */
export const BASEMAP = {
  /** Protomaps flavours: neutral, so that the data colours stand out. */
  flavors: { light: "white", dark: "black" },
  /** Vector tiles are drawn beyond this zoom from the zoom-14 tiles. */
  maxZoom: 14,
  /** Margin around the union of the cities' bounds, in degrees. */
  marginDeg: 0.05,
  /** Glyph ranges for French and local place names (Latin, diacritics, punctuation, Arabic). */
  glyphRanges: [0, 256, 512, 768, 1536, 1792, 7680, 8192, 64256, 65024],
  fonts: ["Noto Sans Regular", "Noto Sans Medium", "Noto Sans Italic"],
};
