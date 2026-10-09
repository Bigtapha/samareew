# Data license

The **code** in this repository is released under the MIT License (see `LICENSE`).

The **data produced by this project** — everything in `outputs/`, and the
datasets published in GitHub releases (maps, rasters, tables, indicators, validation
samples) — is released under the
**[Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/)**
license.

You are free to share and adapt these data for any purpose, including commercially, as long
as you give appropriate credit:

> Cisse, M. (2026). SamaReew: urban expansion in Senegalese cities, 2016–2025.
> https://github.com/Bigtapha/samareew, CC BY 4.0.

See also `CITATION.cff`.

## Third-party sources

Produced data are derived from third-party sources that keep their own licenses and
attribution requirements, in particular:

- Contains modified Copernicus Sentinel data (2016–2026).
- ESA WorldCover 2021 (CC BY 4.0) and Google Dynamic World (CC BY 4.0), used as training references.
- Administrative boundaries: FAO GAUL 2015; OCHA COD-AB Senegal 2024 (CC BY-IGO).
- Urban clusters: GHSL GHS-SMOD R2023A, © European Union (CC BY 4.0).
- Population: WorldPop Global 2 (R2025A, doi:10.5258/SOTON/WP00839), CC BY 4.0; census:
  ANSD, RGPH-5 2023, CC BY 4.0.
- Cross-check only: Google Open Buildings Temporal v1 (CC BY 4.0 or ODbL) and GHSL GHS-BUILT-S
  R2023A, © European Union (free reuse with attribution).
- Basemap of the website (in `site-assets.tar.gz`): Protomaps extract of OpenStreetMap,
  © OpenStreetMap contributors (ODbL 1.0); fonts SIL OFL 1.1, icons MIT.

## Exception: communes (ODbL)

`zones/communes.geojson` is derived from OpenStreetMap and is released under the
**[Open Database License (ODbL 1.0)](https://opendatacommons.org/licenses/odbl/1-0/)**:
© OpenStreetMap contributors. See `zones/README.md`.
