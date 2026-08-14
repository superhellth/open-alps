# DEM Provider Abstraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded Copernicus GLO-30 download in `data/scripts/07-fetch-dem.py` with a
pluggable DEM-provider system, so higher-resolution regional sources (Austria's BEV DGM, Bavaria's
DGM1/5) can be swapped in — per region, even mixed within one run — without touching
`08-add-elevation.py` or anything downstream.

**Architecture:** Every DEM source becomes a small provider module exposing two functions:
`fetch(provider_config, raw_dir) -> list[Path]` (downloads raw tiles) and
`to_4326_vrt(tile_paths, out_vrt_path) -> Path` (reprojects/mosaics them into one GDAL VRT in
EPSG:4326 — the CRS every hut/trail coordinate in this pipeline is already in). `07-fetch-dem.py`
becomes a thin dispatcher that reads `pipeline.config.json`'s `dem.provider`, looks the provider up
in a registry, and calls those two functions. A `composite` meta-provider stitches per-sub-region
VRTs from *different* providers (e.g. Austria via BEV, Bavaria via DGM5) into one final `dem.vrt`
using `gdalbuildvrt` over VRTs, which GDAL supports natively. Because every provider's contract ends
at "one EPSG:4326 VRT," `08-add-elevation.py` needs **zero changes** — that's the abstraction's
actual payoff, and Task 2 proves it by making the *existing* Copernicus behavior conform to the new
interface with no output change before any new provider is added.

**Tech Stack:** Plain Python (this pipeline has no framework dependencies by design — see
`data/README.md`), `gdalwarp`/`gdalbuildvrt` (already required via `rasterio`/GDAL, see script 07/08
setup), `pytest` (new dev dependency, for the pure-logic pieces only — bbox/tile-ID math and
registry dispatch. Nothing here can meaningfully unit-test a multi-GB download or a GDAL
reprojection without a real environment and real data, so those paths get a documented manual smoke
test per task instead of a fake pytest wrapper around them).

**Spec:** No separate spec doc — the requirements are the conversation that produced this plan:
Copernicus GLO-30 (30m) systematically underestimates ascent/descent on switchback-heavy alpine
trails because it can't resolve terrain features narrower than its grid; Austria's BEV DGM (10m or
1m/50cm ALS) and Bavaria's DGM1/DGM5 are the higher-resolution regional alternatives found via
research (see chat: data.gv.at "Digitales Geländemodell (DGM) Österreich", CC-BY-4.0;
geodaten.bayern.de DGM1/DGM5, CC BY 4.0, Metalink bulk download). The user wants the source
swappable, not a one-time hardcoded replacement.

## Global Constraints

- No bash/Node/Docker in `data/` — plain Python only (`data/README.md`, "Layout").
- Every hyperparameter lives in `pipeline.config.json`, read via `scripts/lib/pipeline.py`'s
  `load_config()` — never hardcode a provider-specific value in a script (`data/README.md`,
  "Config").
- All pipeline scripts run inside the `alpen-osm` conda env (`data/README.md`, "Setup").
- `08-add-elevation.py` must not change in this plan — that's the correctness check for the
  abstraction. If a task finds itself wanting to edit it, the interface is leaking and needs
  fixing instead.
- Providers must not require Docker, WSL, or any tool this repo hasn't already accepted an
  exception for (tippecanoe's WSL fallback in script 09 is the one existing exception, purely
  because it has no Windows conda-forge build — don't add a second one without the same
  justification).
- Downloads stay resumable/idempotent where the source supports it (Bavaria's Metalink checksums;
  Copernicus's existing per-tile `if not out_path.exists()` skip) — don't regress that.

---

## File Structure

```
data/
  pipeline.config.json                    # dem.provider / dem.providerConfig (Task 1, 6)
  scripts/
    07-fetch-dem.py                       # becomes a thin dispatcher (Task 2)
    08-add-elevation.py                   # UNCHANGED (proves the abstraction works)
    dem_providers/
      __init__.py                         # registry: get_provider(name) -> module (Task 1)
      base.py                             # Protocol documenting fetch()/to_4326_vrt() (Task 1)
      copernicus.py                       # refactor of current script 07 logic (Task 2)
      at_bev.py                           # Austria BEV DGM 10m provider (Task 3)
      bavaria_dgm.py                      # Bavaria DGM5 provider (Task 4)
      composite.py                        # multi-region meta-provider (Task 5)
    tests/
      __init__.py                         # (Task 1)
      test_dem_providers_registry.py      # (Task 1)
      test_copernicus_tile_naming.py      # (Task 2)
      test_at_bev_bbox.py                 # (Task 3)
      test_bavaria_tile_index.py          # (Task 4)
      test_composite_region_merge.py      # (Task 5)
docs/
  osm-trail-pipeline.md                   # add DEM-provider section (Task 6)
data/README.md                            # update DEM section + provider docs (Task 6)
```

---

## Task 1: Provider interface + registry

**Files:**
- Create: `data/scripts/dem_providers/__init__.py`
- Create: `data/scripts/dem_providers/base.py`
- Create: `data/scripts/tests/__init__.py`
- Create: `data/scripts/tests/test_dem_providers_registry.py`
- Modify: `data/pipeline.config.json` (add `dem.provider`, `dem.providerConfig`)

**Interfaces:**
- Produces: `dem_providers.base.DemProvider` (a `typing.Protocol` with
  `fetch(provider_config: dict, raw_dir: Path) -> list[Path]` and
  `to_4326_vrt(tile_paths: list[Path], out_vrt_path: Path) -> Path`).
- Produces: `dem_providers.get_provider(name: str) -> ModuleType`, raising `KeyError` with a
  message listing valid names on an unknown provider.
- Produces: `dem_providers.PROVIDER_NAMES: list[str]` (for error messages and config validation).

- [ ] **Step 1: Add pytest to the env, write the failing test**

`pytest` isn't installed in `alpen-osm` yet:

```bash
conda install -n alpen-osm -c conda-forge pytest -y
```

```python
# data/scripts/tests/test_dem_providers_registry.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dem_providers import get_provider, PROVIDER_NAMES  # noqa: E402


def test_registry_lists_copernicus_by_default():
    assert "copernicus-glo-30" in PROVIDER_NAMES


def test_get_provider_returns_module_with_fetch_and_to_4326_vrt():
    provider = get_provider("copernicus-glo-30")
    assert hasattr(provider, "fetch")
    assert hasattr(provider, "to_4326_vrt")


def test_get_provider_unknown_name_raises_with_valid_names_listed():
    try:
        get_provider("not-a-real-provider")
        assert False, "expected KeyError"
    except KeyError as e:
        assert "copernicus-glo-30" in str(e)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n alpen-osm python -m pytest data/scripts/tests/test_dem_providers_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dem_providers'`

- [ ] **Step 3: Write `base.py` — the provider contract**

```python
# data/scripts/dem_providers/base.py
"""The contract every DEM provider module must implement. Not an abstract base class - providers
are plain modules (functions, not classes), matching this pipeline's existing style (see
scripts/lib/pipeline.py). This Protocol exists purely so `get_provider()`'s return type is
documented and IDEs/type-checkers can verify a new provider module actually implements it; nothing
here is instantiated.

Every provider's `to_4326_vrt` must return a VRT in EPSG:4326 - that's the one hard requirement
that lets 08-add-elevation.py stay provider-agnostic, since it samples DEM pixels directly at
hut/trail lon/lat coordinates with no reprojection step of its own.
"""

from pathlib import Path
from typing import Protocol


class DemProvider(Protocol):
    def fetch(self, provider_config: dict, raw_dir: Path) -> list[Path]:
        """Downloads whatever raw tiles/files this source needs for provider_config's region
        (bbox, or a named region key - each provider defines its own provider_config shape) into
        raw_dir, skipping any that already exist there. Returns the paths it downloaded or found
        already present, in no particular order."""
        ...

    def to_4326_vrt(self, tile_paths: list[Path], out_vrt_path: Path) -> Path:
        """Builds a single GDAL VRT at out_vrt_path covering all of tile_paths, reprojected to
        EPSG:4326 if the source's native CRS differs. Returns out_vrt_path."""
        ...
```

- [ ] **Step 4: Write `__init__.py` — the registry**

```python
# data/scripts/dem_providers/__init__.py
"""Registry mapping a dem.provider config name to its provider module. See base.py for what every
provider module must implement."""

from . import copernicus

_REGISTRY = {
    "copernicus-glo-30": copernicus,
}

PROVIDER_NAMES = list(_REGISTRY)


def get_provider(name: str):
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"unknown DEM provider {name!r} - valid providers: {PROVIDER_NAMES}"
        ) from None
```

This imports `copernicus` before it exists as a package-conformant module — that's fine, Task 2
creates it as part of the same refactor this task's tests will drive.

- [ ] **Step 5: Stub `copernicus.py` just enough to satisfy the registry test**

```python
# data/scripts/dem_providers/copernicus.py
"""Stub - real implementation lands in Task 2."""

from pathlib import Path


def fetch(provider_config: dict, raw_dir: Path) -> list[Path]:
    raise NotImplementedError


def to_4326_vrt(tile_paths: list[Path], out_vrt_path: Path) -> Path:
    raise NotImplementedError
```

- [ ] **Step 6: Run test to verify it passes**

Run: `conda run -n alpen-osm python -m pytest data/scripts/tests/test_dem_providers_registry.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Add `dem.provider` / `dem.providerConfig` to the config**

```json
{
  "dem": {
    "source": "copernicus-glo-30",
    "provider": "copernicus-glo-30",
    "providerConfig": {},
    "eleNoiseThresholdM": 4,
    "profilePoints": 30
  }
}
```

Leave `source` as-is for now (script 07 currently reads it only informationally, per
`data/README.md`'s "Config" section) — `provider`/`providerConfig` are the new fields the
dispatcher actually reads. `providerConfig` is empty for Copernicus because it just uses the
top-level `bbox`; Tasks 3-5 give other providers their own keys here.

- [ ] **Step 8: Commit**

```bash
git add data/scripts/dem_providers/ data/scripts/tests/ data/pipeline.config.json
git commit -m "feat: add DEM provider registry and interface"
```

---

## Task 2: Copernicus as a conforming provider + 07 becomes a dispatcher

**Files:**
- Modify: `data/scripts/dem_providers/copernicus.py` (replaces the Task 1 stub)
- Modify: `data/scripts/07-fetch-dem.py` (becomes a dispatcher)
- Create: `data/scripts/tests/test_copernicus_tile_naming.py`

**Interfaces:**
- Consumes: `dem_providers.get_provider` (Task 1), `dem_providers.base.DemProvider` shape (Task 1).
- Produces: `copernicus.tile_name(lat: int, lon: int) -> str` (pulled out of the current inline
  function in script 07 so it's independently testable).
- Produces: `copernicus.fetch(provider_config, raw_dir) -> list[Path]`,
  `copernicus.to_4326_vrt(tile_paths, out_vrt_path) -> Path` — same behavior as current script 07,
  just split into the two-function shape.

**Behavior preserved exactly:** current script 07 downloads Copernicus GLO-30 tiles for
`pipeline.config.json`'s top-level `bbox` and runs `gdalbuildvrt`. Copernicus COGs are already
EPSG:4326, so `to_4326_vrt` here is a straight `gdalbuildvrt` call — no `gdalwarp` reprojection
needed. This task is a pure refactor: after it, running `python data/scripts/07-fetch-dem.py`
against an already-fresh `data/dem/raw/` must produce byte-identical `dem.vrt` to before.

- [ ] **Step 1: Write the failing test for tile naming**

```python
# data/scripts/tests/test_copernicus_tile_naming.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dem_providers import copernicus  # noqa: E402


def test_tile_name_positive_lat_lon():
    assert copernicus.tile_name(47, 12) == "Copernicus_DSM_COG_10_N47_00_E012_00_DEM"


def test_tile_name_negative_lat_lon():
    assert copernicus.tile_name(-5, -3) == "Copernicus_DSM_COG_10_S05_00_W003_00_DEM"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n alpen-osm python -m pytest data/scripts/tests/test_copernicus_tile_naming.py -v`
Expected: FAIL — `copernicus.fetch`/`to_4326_vrt` still raise `NotImplementedError`, and
`tile_name` doesn't exist yet on the module.

- [ ] **Step 3: Implement `copernicus.py` for real**

```python
# data/scripts/dem_providers/copernicus.py
"""Copernicus GLO-30 DEM provider (AWS Open Data, no auth) - 30m global coverage, one tile per
whole degree of lat/lon. Already EPSG:4326, so to_4326_vrt is a plain gdalbuildvrt, no reprojection.
See data/README.md's DEM section for why a higher-resolution regional provider (at_bev, bavaria_dgm)
might be preferred where available - this one's the default because it has global coverage and
needs no per-region tile-index lookup."""

import math
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = "https://copernicus-dem-30m.s3.amazonaws.com"


def tile_name(lat: int, lon: int) -> str:
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return f"Copernicus_DSM_COG_10_{ns}{abs(lat):02d}_00_{ew}{abs(lon):03d}_00_DEM"


def fetch(provider_config: dict, raw_dir: Path) -> list[Path]:
    bbox = provider_config["bbox"]
    raw_dir.mkdir(parents=True, exist_ok=True)

    lat_range = range(math.floor(bbox["minLat"]), math.floor(bbox["maxLat"]) + 1)
    lon_range = range(math.floor(bbox["minLng"]), math.floor(bbox["maxLng"]) + 1)

    tile_paths = []
    for lat in lat_range:
        for lon in lon_range:
            name = tile_name(lat, lon)
            url = f"{BASE_URL}/{name}/{name}.tif"
            out_path = raw_dir / f"{name}.tif"
            if not out_path.exists():
                print(f"downloading {name} ...")
                try:
                    urllib.request.urlretrieve(url, out_path)
                except urllib.error.HTTPError as e:
                    if e.code == 404:
                        print(f"  no tile at {name} (likely no land coverage there), skipping")
                        continue
                    raise
            tile_paths.append(out_path)
    return tile_paths


def to_4326_vrt(tile_paths: list[Path], out_vrt_path: Path) -> Path:
    subprocess.run(
        ["gdalbuildvrt", "-overwrite", str(out_vrt_path), *[str(p) for p in tile_paths]],
        check=True,
    )
    return out_vrt_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `conda run -n alpen-osm python -m pytest data/scripts/tests/test_copernicus_tile_naming.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Rewrite `07-fetch-dem.py` as a dispatcher**

```python
#!/usr/bin/env python3
"""
Fetches DEM tiles for the region(s) configured in pipeline.config.json and builds a single
EPSG:4326 GDAL VRT (data/dem/dem.vrt) that 08-add-elevation.py samples - see
data/scripts/dem_providers/base.py for the provider contract, and data/README.md's DEM section
for why this is pluggable (Copernicus GLO-30's global 30m coverage is the default; Austria/Bavaria
have higher-resolution regional alternatives with their own coverage limits).

Usage: python data/scripts/07-fetch-dem.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dem_providers import get_provider  # noqa: E402
from lib.pipeline import DEM_DIR, load_config  # noqa: E402

config = load_config()
dem_config = config["dem"]
provider_name = dem_config.get("provider", "copernicus-glo-30")
provider = get_provider(provider_name)

provider_config = dict(dem_config.get("providerConfig", {}))
provider_config.setdefault("bbox", config["bbox"])

raw_dir = DEM_DIR / "raw"
vrt_path = DEM_DIR / "dem.vrt"

print(f"fetching DEM tiles via provider {provider_name!r} ...")
tile_paths = provider.fetch(provider_config, raw_dir)
print(f"{len(tile_paths)} tiles present, building EPSG:4326 VRT ...")
provider.to_4326_vrt(tile_paths, vrt_path)
print(f"written {vrt_path}")
```

- [ ] **Step 6: Manual smoke test — behavior-preserving refactor check**

Run: `conda run -n alpen-osm python data/scripts/07-fetch-dem.py`
Expected: Since `data/dem/raw/*.tif` and `data/dem/dem.vrt` already exist from the current
pipeline run, this should find all tiles already present (no new downloads) and rebuild an
identical `dem.vrt`. Confirm with:

```bash
gdalinfo data/dem/dem.vrt | grep "Coordinate System"
```

Expected: `EPSG:4326` (unchanged from before this refactor).

- [ ] **Step 7: Commit**

```bash
git add data/scripts/dem_providers/copernicus.py data/scripts/07-fetch-dem.py data/scripts/tests/test_copernicus_tile_naming.py
git commit -m "refactor: make 07-fetch-dem.py a provider dispatcher, Copernicus first"
```

---

## Task 3: Austria BEV DGM provider (10m)

**Files:**
- Create: `data/scripts/dem_providers/at_bev.py`
- Modify: `data/scripts/dem_providers/__init__.py` (register `"at-bev-dgm"`)
- Create: `data/scripts/tests/test_at_bev_bbox.py`

**Interfaces:**
- Consumes: `dem_providers.base.DemProvider` shape (Task 1).
- Produces: `at_bev.fetch(provider_config, raw_dir) -> list[Path]`,
  `at_bev.to_4326_vrt(tile_paths, out_vrt_path) -> Path`.
- Produces: `at_bev.download_url(provider_config: dict) -> str` (isolated so the URL-building
  logic is testable without a network call).

**Source specifics (from research):** BEV/data.gv.at publishes a national 10m DGM as GeoTIFF(s) in
Lambert projection (EPSG:31287), CC-BY-4.0, no auth. `providerConfig` for this provider is:

```json
{ "downloadUrl": "<the exact data.gv.at resource URL for the 10m DGM GeoTIFF/zip>" }
```

The exact resource URL wasn't pinned down in research (data.gv.at's dataset page links to a
resource, not a single stable direct-download URL) — **this task's first step is confirming that
URL by hand** (visit `https://www.data.gv.at/katalog/dataset/b5de6975-417b-4320-afdb-eb2a9e2a1dbf`,
find the 10m GeoTIFF resource, copy its direct download link) before writing `fetch()` against it.
If the resource is a single national file rather than tiles, `fetch()` degenerates to one download
+ unzip; write it that way rather than forcing a multi-tile shape it doesn't have.

- [ ] **Step 1: Confirm the download URL and file shape manually**

Visit the dataset page, download the 10m resource by hand once, and note: is it a single `.tif`,
a `.zip` of one `.tif`, or multiple tiles? Record the answer in this task's commit message — the
rest of this task's code depends on it.

- [ ] **Step 2: Write the failing test for `download_url`**

(Adjust the expected URL/shape to match what Step 1 found — this is illustrative of the pattern,
not a literal final assertion.)

```python
# data/scripts/tests/test_at_bev_bbox.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dem_providers import at_bev  # noqa: E402


def test_download_url_uses_configured_url():
    config = {"downloadUrl": "https://example.data.gv.at/dgm10.zip"}
    assert at_bev.download_url(config) == "https://example.data.gv.at/dgm10.zip"


def test_download_url_missing_key_raises():
    try:
        at_bev.download_url({})
        assert False, "expected KeyError"
    except KeyError:
        pass
```

- [ ] **Step 3: Run test to verify it fails**

Run: `conda run -n alpen-osm python -m pytest data/scripts/tests/test_at_bev_bbox.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dem_providers.at_bev'`

- [ ] **Step 4: Implement `at_bev.py`**

```python
# data/scripts/dem_providers/at_bev.py
"""Austria BEV Digitales Geländemodell (DGM), 10m, Lambert (EPSG:31287), CC-BY-4.0, via
data.gv.at - no auth. Higher resolution than Copernicus GLO-30 (30m), which matters for
switchback-heavy alpine trails a 30m grid can't resolve (see docs/osm-trail-pipeline.md's DEM
section). providerConfig: {"downloadUrl": "<direct link to the 10m GeoTIFF/zip resource>"} -
confirmed by hand against https://www.data.gv.at/katalog/dataset/b5de6975-417b-4320-afdb-eb2a9e2a1dbf,
see this file's git history for which resource shape (single file vs zip vs tiles) was found."""

import subprocess
import urllib.request
import zipfile
from pathlib import Path


def download_url(provider_config: dict) -> str:
    return provider_config["downloadUrl"]


def fetch(provider_config: dict, raw_dir: Path) -> list[Path]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    url = download_url(provider_config)
    dst = raw_dir / Path(url).name

    if not dst.exists():
        print(f"downloading {url} ...")
        urllib.request.urlretrieve(url, dst)

    if dst.suffix == ".zip":
        extract_dir = raw_dir / dst.stem
        if not extract_dir.exists():
            with zipfile.ZipFile(dst) as zf:
                zf.extractall(extract_dir)
        return sorted(extract_dir.glob("*.tif"))

    return [dst]


def to_4326_vrt(tile_paths: list[Path], out_vrt_path: Path) -> Path:
    # Source is EPSG:31287 (Lambert) - gdalwarp reprojects each tile into a temp VRT in EPSG:4326
    # before the final mosaic, so 08-add-elevation.py never has to know the source CRS.
    warped_dir = out_vrt_path.parent / "at_bev_warped"
    warped_dir.mkdir(exist_ok=True)
    warped_paths = []
    for tile in tile_paths:
        warped = warped_dir / f"{tile.stem}_4326.vrt"
        subprocess.run(
            ["gdalwarp", "-t_srs", "EPSG:4326", "-of", "VRT", "-overwrite",
             str(tile), str(warped)],
            check=True,
        )
        warped_paths.append(warped)

    subprocess.run(
        ["gdalbuildvrt", "-overwrite", str(out_vrt_path), *[str(p) for p in warped_paths]],
        check=True,
    )
    return out_vrt_path
```

- [ ] **Step 5: Run test to verify it passes**

Run: `conda run -n alpen-osm python -m pytest data/scripts/tests/test_at_bev_bbox.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Register the provider**

```python
# data/scripts/dem_providers/__init__.py
from . import at_bev, copernicus

_REGISTRY = {
    "copernicus-glo-30": copernicus,
    "at-bev-dgm": at_bev,
}

PROVIDER_NAMES = list(_REGISTRY)
```

- [ ] **Step 7: Manual smoke test against a small bbox**

Temporarily point `dem.provider` at `"at-bev-dgm"` with a small test bbox (e.g. one Alpine valley,
~0.2°×0.2°) in a scratch config, run `07-fetch-dem.py` against it, then:

```bash
gdalinfo data/dem/dem.vrt | grep -E "Coordinate System|Pixel Size"
```

Expected: `EPSG:4326`, and a pixel size corresponding to ~10m (roughly 0.00009° at Alpine
latitudes) rather than Copernicus's ~30m.

- [ ] **Step 8: Commit**

```bash
git add data/scripts/dem_providers/at_bev.py data/scripts/dem_providers/__init__.py data/scripts/tests/test_at_bev_bbox.py
git commit -m "feat: add Austria BEV DGM (10m) as a DEM provider"
```

---

## Task 4: Bavaria DGM provider (5m, tile-index based)

**Files:**
- Create: `data/scripts/dem_providers/bavaria_dgm.py`
- Modify: `data/scripts/dem_providers/__init__.py` (register `"bavaria-dgm5"`)
- Create: `data/scripts/tests/test_bavaria_tile_index.py`

**Interfaces:**
- Consumes: `dem_providers.base.DemProvider` shape (Task 1).
- Produces: `bavaria_dgm.tiles_for_bbox(tile_index: list[dict], bbox: dict) -> list[str]` (pure
  function: given a parsed tile-index and a bbox, returns matching tile IDs — testable without a
  network call using a small synthetic tile-index fixture).
- Produces: `bavaria_dgm.metalink_url(tile_id: str) -> str`.
- Produces: `bavaria_dgm.fetch(provider_config, raw_dir) -> list[Path]`,
  `bavaria_dgm.to_4326_vrt(tile_paths, out_vrt_path) -> Path`.

**Source specifics (from research):** geodaten.bayern.de publishes DGM1 (1m) and DGM5 (5m) on a
1km×1km administrative tile grid, CC BY 4.0. Bulk download is via Metalink:
`https://geodaten.bayern.de/odd/a/dgm/dgm1/meta/metalink/<tile_id>.meta4` (swap `dgm1` for `dgm5`
for the lower-resolution product this plan recommends — 5m is already well past
switchback-resolving resolution at a fraction of DGM1's storage). **This task needs the tile-index
resource confirmed by hand first** (same caveat as Task 3): geodaten.bayern.de's OpenData portal
page (`https://geodaten.bayern.de/opengeodata/OpenDataDetail.html?pn=dgm1`) should link a tile-index
shapefile/geojson — find and note its URL before writing `fetch()`.

- [ ] **Step 1: Confirm the tile-index resource URL manually**

Visit the OpenData portal page, find the tile-index download (shapefile or GeoJSON covering all of
Bavaria's 1km tiles with their IDs), download it once by hand, and note its URL and the field name
holding the tile ID. Record both in this task's commit message.

- [ ] **Step 2: Write the failing test for bbox→tile-ID matching**

```python
# data/scripts/tests/test_bavaria_tile_index.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dem_providers import bavaria_dgm  # noqa: E402


def test_tiles_for_bbox_returns_intersecting_tiles_only():
    # Synthetic 1km-tile index: three tiles in a row, IDs and (minLng, minLat, maxLng, maxLat)
    # bounds in EPSG:4326 for simplicity - real index may be in EPSG:25832, see Step 1's findings.
    tile_index = [
        {"tile_id": "32_680_5340", "bounds": (11.00, 47.90, 11.01, 47.91)},
        {"tile_id": "32_681_5340", "bounds": (11.01, 47.90, 11.02, 47.91)},
        {"tile_id": "32_682_5340", "bounds": (11.02, 47.90, 11.03, 47.91)},
    ]
    bbox = {"minLng": 11.005, "maxLng": 11.015, "minLat": 47.90, "maxLat": 47.91}

    result = bavaria_dgm.tiles_for_bbox(tile_index, bbox)

    assert result == ["32_680_5340", "32_681_5340"]


def test_metalink_url_uses_dgm5_by_default():
    assert bavaria_dgm.metalink_url("32_680_5340") == (
        "https://geodaten.bayern.de/odd/a/dgm/dgm5/meta/metalink/32_680_5340.meta4"
    )
```

- [ ] **Step 3: Run test to verify it fails**

Run: `conda run -n alpen-osm python -m pytest data/scripts/tests/test_bavaria_tile_index.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dem_providers.bavaria_dgm'`

- [ ] **Step 4: Implement `bavaria_dgm.py`**

```python
# data/scripts/dem_providers/bavaria_dgm.py
"""Bavaria DGM5 (5m grid, Bayerische Vermessungsverwaltung, CC BY 4.0) via geodaten.bayern.de -
tiled on a 1km x 1km administrative grid (not simple lat/lon cells like Copernicus), so this
provider needs a tile-index lookup before it can download anything for a bbox. 5m rather than
DGM1's 1m: already well past the resolution needed to resolve trail switchbacks (see
docs/osm-trail-pipeline.md), at a fraction of DGM1's storage/download volume.

providerConfig: {"tileIndexUrl": "<confirmed in Task 4 Step 1>", "bbox": {...}} (bbox falls back
to the top-level pipeline.config.json bbox if omitted, same as every other provider)."""

import json
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

METALINK_BASE = "https://geodaten.bayern.de/odd/a/dgm/dgm5/meta/metalink"


def metalink_url(tile_id: str) -> str:
    return f"{METALINK_BASE}/{tile_id}.meta4"


def tiles_for_bbox(tile_index: list[dict], bbox: dict) -> list[str]:
    """tile_index entries: {"tile_id": str, "bounds": (minLng, minLat, maxLng, maxLat)}. Returns
    tile_ids whose bounds intersect bbox, in tile_index order."""
    result = []
    for entry in tile_index:
        min_lng, min_lat, max_lng, max_lat = entry["bounds"]
        intersects = (
            min_lng < bbox["maxLng"] and max_lng > bbox["minLng"]
            and min_lat < bbox["maxLat"] and max_lat > bbox["minLat"]
        )
        if intersects:
            result.append(entry["tile_id"])
    return result


def _load_tile_index(tile_index_path: Path) -> list[dict]:
    with open(tile_index_path, encoding="utf-8") as f:
        raw = json.load(f)
    # Adjust to the real tile-index schema found in Task 4 Step 1 - this assumes a GeoJSON
    # FeatureCollection with a tile-id property and a polygon bounds-derivable geometry.
    entries = []
    for feat in raw["features"]:
        lngs = [c[0] for c in feat["geometry"]["coordinates"][0]]
        lats = [c[1] for c in feat["geometry"]["coordinates"][0]]
        entries.append({
            "tile_id": feat["properties"]["tile_id"],
            "bounds": (min(lngs), min(lats), max(lngs), max(lats)),
        })
    return entries


def _download_metalink(tile_id: str, raw_dir: Path) -> Path:
    """Parses the Metalink XML for its file URL(s) and downloads via urllib - avoids adding aria2
    as a new binary dependency for what's usually a single-file-per-tile metalink."""
    meta_path = raw_dir / f"{tile_id}.meta4"
    urllib.request.urlretrieve(metalink_url(tile_id), meta_path)

    ns = {"m": "urn:ietf:params:xml:ns:metalink"}
    tree = ET.parse(meta_path)
    file_elem = tree.getroot().find("m:file", ns)
    url_elem = file_elem.find("m:url", ns)
    tile_url = url_elem.text

    dst = raw_dir / Path(tile_url).name
    if not dst.exists():
        print(f"downloading {tile_url} ...")
        urllib.request.urlretrieve(tile_url, dst)
    return dst


def fetch(provider_config: dict, raw_dir: Path) -> list[Path]:
    raw_dir.mkdir(parents=True, exist_ok=True)

    tile_index_path = raw_dir / "tile_index.geojson"
    if not tile_index_path.exists():
        urllib.request.urlretrieve(provider_config["tileIndexUrl"], tile_index_path)
    tile_index = _load_tile_index(tile_index_path)

    tile_ids = tiles_for_bbox(tile_index, provider_config["bbox"])
    print(f"{len(tile_ids)} Bavaria DGM5 tiles intersect the configured bbox")

    return [_download_metalink(tile_id, raw_dir) for tile_id in tile_ids]


def to_4326_vrt(tile_paths: list[Path], out_vrt_path: Path) -> Path:
    # Source is EPSG:25832 (UTM 32N) - same warp-then-mosaic pattern as at_bev.py.
    warped_dir = out_vrt_path.parent / "bavaria_dgm_warped"
    warped_dir.mkdir(exist_ok=True)
    warped_paths = []
    for tile in tile_paths:
        warped = warped_dir / f"{tile.stem}_4326.vrt"
        subprocess.run(
            ["gdalwarp", "-t_srs", "EPSG:4326", "-of", "VRT", "-overwrite",
             str(tile), str(warped)],
            check=True,
        )
        warped_paths.append(warped)

    subprocess.run(
        ["gdalbuildvrt", "-overwrite", str(out_vrt_path), *[str(p) for p in warped_paths]],
        check=True,
    )
    return out_vrt_path
```

- [ ] **Step 5: Run test to verify it passes**

Run: `conda run -n alpen-osm python -m pytest data/scripts/tests/test_bavaria_tile_index.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Register the provider**

```python
# data/scripts/dem_providers/__init__.py
from . import at_bev, bavaria_dgm, copernicus

_REGISTRY = {
    "copernicus-glo-30": copernicus,
    "at-bev-dgm": at_bev,
    "bavaria-dgm5": bavaria_dgm,
}

PROVIDER_NAMES = list(_REGISTRY)
```

- [ ] **Step 7: Manual smoke test against a small Bavarian bbox**

Same pattern as Task 3 Step 7, `dem.provider` = `"bavaria-dgm5"`, a small bbox inside Bavaria.
Confirm `_load_tile_index`'s assumed GeoJSON schema actually matches what Task 4 Step 1 found —
adjust if the real tile index uses a different property name or a non-GeoJSON format (e.g.
shapefile, needing `fiona`/`geopandas` instead of plain `json`).

- [ ] **Step 8: Commit**

```bash
git add data/scripts/dem_providers/bavaria_dgm.py data/scripts/dem_providers/__init__.py data/scripts/tests/test_bavaria_tile_index.py
git commit -m "feat: add Bavaria DGM5 as a DEM provider"
```

---

## Task 5: Composite multi-region provider

**Files:**
- Create: `data/scripts/dem_providers/composite.py`
- Modify: `data/scripts/dem_providers/__init__.py` (register `"composite"`)
- Modify: `data/scripts/07-fetch-dem.py` (composite needs its sub-region configs, not a flat
  `providerConfig`)
- Create: `data/scripts/tests/test_composite_region_merge.py`

**Interfaces:**
- Consumes: `dem_providers.get_provider` (Task 1), every other provider's `fetch`/`to_4326_vrt`
  (Tasks 2-4).
- Produces: `composite.fetch_and_build(provider_config: dict, dem_dir: Path) -> Path` — composite
  doesn't fit the plain `fetch`/`to_4326_vrt` split (it needs to call *other* providers' full
  pipelines per sub-region, not just download raw tiles), so it exposes one combined function
  instead. `07-fetch-dem.py` special-cases `provider_name == "composite"` to call this instead of
  the two-step `fetch()`/`to_4326_vrt()` sequence.

**Config shape:**

```json
{
  "dem": {
    "provider": "composite",
    "providerConfig": {
      "regions": [
        { "provider": "at-bev-dgm", "bbox": { "minLng": 8.9, "maxLng": 13.0, "minLat": 46.3, "maxLat": 49.0 }, "downloadUrl": "..." },
        { "provider": "bavaria-dgm5", "bbox": { "minLng": 8.9, "maxLng": 13.9, "minLat": 47.2, "maxLat": 50.6 }, "tileIndexUrl": "..." }
      ]
    }
  }
}
```

Overlapping sub-region bboxes are allowed — `gdalbuildvrt` takes the first-listed source for
overlapping pixels, so region order in the list is meaningful (list the higher-priority/
higher-resolution source first where two regions overlap).

- [ ] **Step 1: Write the failing test**

```python
# data/scripts/tests/test_composite_region_merge.py
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dem_providers import composite  # noqa: E402


def test_fetch_and_build_calls_each_region_provider_and_merges(tmp_path, monkeypatch):
    calls = []

    fake_provider = MagicMock()
    fake_provider.fetch.side_effect = lambda cfg, raw_dir: calls.append(("fetch", cfg)) or [
        raw_dir / "tile.tif"
    ]
    fake_provider.to_4326_vrt.side_effect = lambda paths, out: calls.append(
        ("to_4326_vrt", paths, out)
    ) or out

    monkeypatch.setattr(composite, "get_provider", lambda name: fake_provider)

    merge_calls = []
    monkeypatch.setattr(
        composite.subprocess, "run",
        lambda args, **kwargs: merge_calls.append(args)
    )

    provider_config = {
        "regions": [
            {"provider": "at-bev-dgm", "bbox": {"minLng": 0, "maxLng": 1, "minLat": 0, "maxLat": 1}},
            {"provider": "bavaria-dgm5", "bbox": {"minLng": 1, "maxLng": 2, "minLat": 0, "maxLat": 1}},
        ]
    }

    out_vrt = tmp_path / "dem.vrt"
    result = composite.fetch_and_build(provider_config, tmp_path)

    assert result == out_vrt
    assert sum(1 for c in calls if c[0] == "fetch") == 2
    assert sum(1 for c in calls if c[0] == "to_4326_vrt") == 2
    assert len(merge_calls) == 1  # final gdalbuildvrt over the two regional VRTs
    assert merge_calls[0][0] == "gdalbuildvrt"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n alpen-osm python -m pytest data/scripts/tests/test_composite_region_merge.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dem_providers.composite'`

- [ ] **Step 3: Implement `composite.py`**

```python
# data/scripts/dem_providers/composite.py
"""Meta-provider that stitches per-sub-region VRTs from different providers into one final
dem.vrt, e.g. Austria via at-bev-dgm + Bavaria via bavaria-dgm5. Doesn't fit the plain
fetch()/to_4326_vrt() split every other provider uses (it needs to run each region's *entire*
fetch+reproject pipeline, not just download raw tiles) - see fetch_and_build below, which
07-fetch-dem.py calls directly for provider == "composite" instead of the usual two-step
sequence.

gdalbuildvrt takes the first-listed source for overlapping pixels, so region order in
providerConfig.regions is meaningful where two regions' bboxes overlap - list the
higher-resolution/higher-priority source first."""

import subprocess
from pathlib import Path

from . import get_provider


def fetch_and_build(provider_config: dict, dem_dir: Path) -> Path:
    region_vrts = []
    for i, region_config in enumerate(provider_config["regions"]):
        provider = get_provider(region_config["provider"])
        raw_dir = dem_dir / "raw" / f"region_{i}_{region_config['provider']}"
        region_vrt = dem_dir / f"region_{i}_{region_config['provider']}.vrt"

        print(f"composite region {i}: {region_config['provider']} ...")
        tile_paths = provider.fetch(region_config, raw_dir)
        provider.to_4326_vrt(tile_paths, region_vrt)
        region_vrts.append(region_vrt)

    out_vrt_path = dem_dir / "dem.vrt"
    subprocess.run(
        ["gdalbuildvrt", "-overwrite", str(out_vrt_path), *[str(v) for v in region_vrts]],
        check=True,
    )
    return out_vrt_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `conda run -n alpen-osm python -m pytest data/scripts/tests/test_composite_region_merge.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Register composite and special-case it in the dispatcher**

```python
# data/scripts/dem_providers/__init__.py
from . import at_bev, bavaria_dgm, composite, copernicus

_REGISTRY = {
    "copernicus-glo-30": copernicus,
    "at-bev-dgm": at_bev,
    "bavaria-dgm5": bavaria_dgm,
    "composite": composite,
}

PROVIDER_NAMES = list(_REGISTRY)
```

```python
# data/scripts/07-fetch-dem.py — replace the fetch/to_4326_vrt calls at the bottom with:
if provider_name == "composite":
    from dem_providers.composite import fetch_and_build
    vrt_path = fetch_and_build(provider_config, DEM_DIR)
    print(f"written {vrt_path}")
else:
    print(f"fetching DEM tiles via provider {provider_name!r} ...")
    tile_paths = provider.fetch(provider_config, raw_dir)
    print(f"{len(tile_paths)} tiles present, building EPSG:4326 VRT ...")
    provider.to_4326_vrt(tile_paths, vrt_path)
    print(f"written {vrt_path}")
```

- [ ] **Step 6: Manual smoke test — full composite run against small bboxes**

Configure `providerConfig.regions` with two small non-overlapping test bboxes (one Austria, one
Bavaria, each a fraction of a degree), run `07-fetch-dem.py`, and confirm `dem.vrt` covers both:

```bash
gdalinfo data/dem/dem.vrt | grep -E "Coordinate System|Size is"
```

- [ ] **Step 7: Commit**

```bash
git add data/scripts/dem_providers/composite.py data/scripts/dem_providers/__init__.py data/scripts/07-fetch-dem.py data/scripts/tests/test_composite_region_merge.py
git commit -m "feat: add composite multi-region DEM provider"
```

---

## Task 6: Docs + full-bbox rebuild verification

**Files:**
- Modify: `data/README.md` (DEM section, Config section)
- Modify: `docs/osm-trail-pipeline.md` (DEM provider rationale)

**Interfaces:**
- Consumes: everything from Tasks 1-5. This task adds no new code, only documentation and the
  final full-scale verification.

- [ ] **Step 1: Update `data/README.md`'s Config section**

Add a `dem.provider` / `dem.providerConfig` entry alongside the existing `dem.eleNoiseThresholdM`/
`dem.profilePoints` documentation (same file, same section that documents `dem.source`/
`eleNoiseThresholdM` today) — document each registered provider name, what `providerConfig` keys
it needs, and point to `data/scripts/dem_providers/base.py` for the interface contract.

- [ ] **Step 2: Update `docs/osm-trail-pipeline.md`**

Add a short section explaining *why* the provider is pluggable: Copernicus GLO-30's 30m grid
can't resolve alpine switchbacks, which is why `ascent_m`/`descent_m` reads low compared to
sources like alpenvereinaktiv that use finer regional DEMs or recorded GPS/barometric tracks —
and that Austria/Bavaria's regional DEMs (Tasks 3-4) exist as a fix, selectable via
`pipeline.config.json`'s `dem.provider` without touching `08-add-elevation.py`.

- [ ] **Step 3: Decide and set the production `dem.provider` value**

This plan doesn't decide *which* provider AT+Bayern should actually run with day to day — that's
a call for after Tasks 3-5 land and their manual smoke tests are in, weighing accuracy gain against
the larger download/storage/runtime cost of the regional sources. Set `pipeline.config.json`'s
`dem.provider` to whichever was chosen (likely `"composite"` with Austria + Bavaria regions, given
the pipeline already covers exactly those two areas per `data/README.md`'s existing `regions`
list) and record the reasoning in the commit message.

- [ ] **Step 4: Full-bbox rebuild and re-run of step 08**

```bash
conda run -n alpen-osm python data/scripts/run_all.py --only 7,8
```

Confirm `data/osm/hut-edges.geojson`'s `ascent_m`/`descent_m` values shift upward relative to the
Copernicus-derived baseline (expected direction, per this plan's premise) and spot-check one or two
edges' `elevation_profile` against a known route on alpenvereinaktiv for a sanity comparison.

- [ ] **Step 5: Commit**

```bash
git add data/README.md docs/osm-trail-pipeline.md data/pipeline.config.json
git commit -m "docs: document DEM provider abstraction, switch production provider"
```

---

## Self-Review Notes

- **Spec coverage:** pluggable/swappable DEM source ✅ (Task 1 interface + registry), Austria
  provider ✅ (Task 3), Bavaria provider ✅ (Task 4), "interoperable" / mixed-region use ✅ (Task 5
  composite), `08-add-elevation.py` untouched ✅ (Global Constraints + Task 2's behavior-preserving
  refactor proves it), docs ✅ (Task 6).
- **Known gap, called out explicitly rather than hidden:** the exact data.gv.at and
  geodaten.bayern.de download/tile-index URLs weren't resolved by automated research — Task 3
  Step 1 and Task 4 Step 1 require a human to visit the portal pages once and confirm the real
  resource URL/shape before the rest of those tasks' code (written against the *expected* shape)
  can be trusted as more than a best guess. This is flagged in-line in both tasks rather than
  papered over with a placeholder URL.
- **Type consistency:** `fetch(provider_config: dict, raw_dir: Path) -> list[Path]` and
  `to_4326_vrt(tile_paths: list[Path], out_vrt_path: Path) -> Path` are identical across
  `base.py`, `copernicus.py`, `at_bev.py`, `bavaria_dgm.py` — checked.
