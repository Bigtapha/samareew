# Study zones (frozen)

Produced by `python 00_zones.py`, then frozen: every indicator is computed inside these
zones, so they only change when the rule changes (log it in ROADMAP §9).

| File | Content |
|---|---|
| `urban_clusters.geojson` | GHSL urban cluster of each city (GHS-SMOD R2023A, epoch 2025, class ≥ 21, 1 km grid) |
| `zones.geojson` | Study zone of each city: urban cluster + 2 km buffer, land only |
| `communes.geojson` | OpenStreetMap communes (admin_level 8) clipped to land and to the zones |

## Rule

The same for every city, so that cities can be compared:

1. **Urban cluster**: the GHSL degree-of-urbanisation cluster (class ≥ 21) that contains the city.
2. **Buffer of 2 km**, leaving room for growth beyond the 2025 cluster.
3. **Neighbouring cities**: where two buffers overlap, each point goes to the nearest urban
   cluster (no overlap with the current 2 km buffer).
4. **Land only**: clipped to the national boundary (OCHA COD-AB, 2024).

## Communes

No open dataset of Senegal's communes exists: OCHA COD-AB and geoBoundaries stop at the
arrondissements. Communes are taken from OpenStreetMap and corrected automatically:

- names without the pre-2013 prefix ("Communauté rurale de Fandène" → "Fandène");
- overlaps removed: the smallest commune keeps the disputed area (urban communes are
  drawn more precisely than the rural ones around them);
- clipped to land, since OSM boundaries often run out to sea.

Fields: `city`, `commune`, `osm_name`, `osm_id`, `area_km2` (inside the zone),
`share_of_commune` (share of the commune's land inside the zone), `osm_date`.

**Known limitations**: OSM boundaries are not official. Around Thiès, the urban communes
(Thiès Nord, Est, Ouest) are small and the built-up area spills into Fandène; Touba Mosquée
is a single very large commune, to be split into sectors.

## Licences

- `urban_clusters.geojson`, `zones.geojson`: CC BY 4.0 (derived from GHSL, © European Union,
  CC BY 4.0, and OCHA COD-AB, CC BY-IGO).
- `communes.geojson`: **ODbL 1.0**, © OpenStreetMap contributors. It is a derivative of the
  OSM database and must stay under the same licence.
