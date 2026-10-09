# CLAUDE.md

SamaReew: open-data atlas comparing Senegalese cities (Dakar, Touba, Thiès, Mbour), first
theme urban expansion 2016–2026, Sentinel-2 + Google Earth Engine + one national Random Forest.

## Start of a session

1. Read `README.md` (status, structure, commands) and `ROADMAP.md` (plan, decisions §2,
   open decisions §8, decision log §9).
2. Check the current branch and `git status`; work on a milestone branch, not on `main`.

## Working with the user

- Talk to the user in **French**. Code, comments, docstrings and `README.md` are in English;
  `ROADMAP.md` and commit messages are in French (style: `J2 : <what>`).
- Open decisions (ROADMAP §8) belong to the user: present the options with a recommendation,
  then wait. Once decided, record it: tick the task, update §2 / §8, add a line to §9.
- Commit only when asked. The user pushes themselves.
- Show results visually when choices are spatial: write control maps (PNG) to `data/`
  (ignored by git) and look at them before reporting.

## Project rules

- **Comparability first**: the same rule for every city (zones, buffer, model, indicators).
  Never tune one city alone without saying so and logging it.
- **Settings in `config/`, not in code**: shared settings in `config/settings.py`, one entry
  per city in `config/cities.py`.
- **Keep `METHODOLOGIE.md` in sync** (French, theory of the method with the actual values):
  update it in the same change whenever a method, setting or result it cites changes, and
  add a section when a new step is built (indicators, cross-check, validation…).
- **Pure functions in `src/` with tests in `tests/`** (no Earth Engine in tests);
  pipeline steps in `pipeline/` stay thin.
- `zones/` is frozen and versioned: re-run step 0 only to change a rule, and check that
  the geometries are otherwise identical.
- `site/` (J5) will read only `outputs/`, never import from `pipeline/` or `src/`. Tools
  (decided 09/10/2026): Astro, Observable Plot, MapLibre GL + PMTiles; mobile first, slow
  connections. Entry points: `outputs/site/manifest.json` and `outputs/tables/indicators.json`.
  The `.pmtiles` archives are ignored by git: rebuild them with step 7 (data layers) and
  `npm run basemap` in `site/` (basemap, needs the `pmtiles` CLI, in `~/.local/bin`). Node 24 via
  nvm (`nvm use` in `site/`, `.nvmrc`); the system Node 20 is too old for Astro 7.
- Large files (GeoTIFF, tiles) never go into git (`*.tif` and `data/` are ignored).
- Licences: code MIT, produced data CC BY 4.0, `zones/communes.geojson` ODbL (OSM-derived).
  Check the licence of any new source before using it (GADM was rejected for that reason).

## Commands

Run from the project root with the venv (`source .venv/bin/activate`, Python 3.12, created
with `uv`; install packages with `uv pip install --python .venv ...` and update
`requirements-lock.txt` with `uv pip freeze --python .venv`):

```bash
python -m pipeline.s0_zones        # zones (cached downloads in data/raw/)
python -m pipeline.s1_train        # samples + national model -> outputs/model/
python -m pipeline.s2_classify     # --city <slug>, --drive
python -m pipeline.s3_postprocess  # --city <slug>
python -m pipeline.s4_indicators   # all cities -> outputs/tables/ (+ data/worldpop_by_commune.csv)
python -m pipeline.s5_validation   # --draw once (sample), accuracy from labels.csv; --cover once (second reading)
python -m pipeline.s6_crosscheck   # Open Buildings, GHSL, census -> outputs/crosscheck/ (after s4)
python -m pipeline.s7_site_data    # map tiles, boundaries, validation -> outputs/site/ (after s4, s5)
pytest

cd site && nvm use        # Node 24
npm run basemap           # basemap -> site/public/basemap/ (once, or to refresh OSM)
npm run dev               # copies outputs/ into site/public/data/, then http://localhost:4321/samareew/
npm run build && npm run check
```

Step numbers follow ROADMAP §4.1 (`s5` validation, `s6` cross-check). The validation is
blind: never show the user `outputs/validation/sample_key.csv` (map class of each point)
while labels are being entered.

Earth Engine project: `tieufmaps` (already authenticated on this machine). Public Overpass
servers are often busy (step 0 tries three mirrors); Nominatim works for single places.

Downloads are cached in `data/` (WorldPop in `data/raw/worldpop/`, census in
`data/raw/rgph5/`, reference roofs in `data/cities/<city>/`). The ANSD server sends an
incomplete certificate: census downloads run with `verify=False`, and WebFetch cannot read
ansd.sn (use `curl -k`). The old Python 3.10 venv `myvenv/` is kept until the user deletes it.
