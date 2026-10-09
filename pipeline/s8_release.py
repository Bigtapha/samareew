"""Step 8 - Release: the two assets of a GitHub release (J6).

1. samareew-data.zip: the downloadable data (tables, rasters by city, full-resolution
   boundaries, validation, cross-check), with a README, the licence and the citation;
2. site-assets.tar.gz: the map archives ignored by git (step 7 tiles and the basemap of
   `npm run basemap`), which the deployment workflow downloads before building the site;
3. SHA256SUMS for both.

The assets keep the same names from one release to the next, so that
<REPO_URL>/releases/latest/download/<asset> stays a valid link. Publishing the release is
done by hand, with the command printed at the end (tag v<RELEASE_VERSION>).

Inputs : outputs/ (steps 3-7), zones/ (step 0), site/public/basemap/ (npm run basemap)
Outputs: data/release/samareew-data.zip, data/release/site-assets.tar.gz,
         data/release/SHA256SUMS

Usage
    python -m pipeline.s8_release
"""
import argparse
import hashlib
import subprocess
import tarfile
import zipfile
from datetime import date

import config as cfg
from src import release as rl


def git(*args) -> str:
    return subprocess.run(["git", *args], cwd=cfg.ROOT, capture_output=True, text=True,
                          check=True).stdout.strip()


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def check_sources(pairs: list, hint: str):
    missing = [src for src, _ in pairs if not src.exists()]
    if missing:
        raise SystemExit(f"Missing files ({hint}):\n  "
                         + "\n  ".join(str(p.relative_to(cfg.ROOT)) for p in missing))


def main():
    if git("status", "--porcelain"):
        print("Warning: uncommitted changes, the release will not match the commit it names.")
    commit = git("rev-parse", "--short", "HEAD")
    cities = {slug: c["name"] for slug, c in cfg.CITIES.items()}

    data = rl.data_package_files(cfg.ROOT, list(cities), cfg.GROWTH_PERIODS)
    check_sources(data, "run the pipeline steps first")
    site = rl.site_asset_files(cfg.ROOT, cfg.SITE_TILES_DIR, cfg.SITE_BASEMAP_DIR)
    if not any(a.endswith(".pmtiles") and "basemap" not in a for _, a in site):
        raise SystemExit("No map tiles: run `python -m pipeline.s7_site_data` first.")
    if not any(a.endswith("basemap.pmtiles") for _, a in site):
        raise SystemExit("No basemap: run `npm run basemap` in site/ first.")

    cfg.RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    readme = rl.data_readme(cfg.RELEASE_VERSION, date.today().isoformat(), commit, cities,
                            cfg.PUBLISHED_YEARS, cfg.GROWTH_PERIODS, cfg.REPO_URL)
    data_zip = cfg.RELEASE_DIR / cfg.RELEASE_DATA_ZIP
    with zipfile.ZipFile(data_zip, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{rl.DATA_PREFIX}/README.md", readme)
        for src, arc in data:
            z.write(src, arc)
    site_tar = cfg.RELEASE_DIR / cfg.RELEASE_SITE_ASSETS
    with tarfile.open(site_tar, "w:gz") as t:
        for src, arc in site:
            t.add(src, arc)

    sums = cfg.RELEASE_DIR / "SHA256SUMS"
    sums.write_text("".join(f"{sha256(p)}  {p.name}\n" for p in (data_zip, site_tar)))
    for p in (data_zip, site_tar):
        print(f"{p.relative_to(cfg.ROOT)}: {p.stat().st_size / 1e6:.1f} MB")
    print(f"{len(data)} data files, {len(site)} site files, commit {commit}")
    tag = f"v{cfg.RELEASE_VERSION}"
    print("\nPublish (after pushing the commit):\n"
          f"  gh release create {tag} {data_zip.relative_to(cfg.ROOT)} "
          f"{site_tar.relative_to(cfg.ROOT)} {sums.relative_to(cfg.ROOT)} "
          f"--title \"SamaReew {cfg.RELEASE_VERSION}\" --notes-file <notes.md>")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.parse_args()
    main()
