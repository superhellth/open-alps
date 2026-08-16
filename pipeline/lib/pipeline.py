"""Single config reader shared by every pipeline script, so pipeline.config.json is the
one source of truth for hyperparameters (bbox, regions, tag filter, graph thresholds)."""

import json
import platform
import re
import shlex
import shutil
import subprocess
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SCRIPTS_DIR.parent
DATA_DIR = REPO_ROOT / "data"
OSM_DIR = DATA_DIR / "osm"
DEM_DIR = DATA_DIR / "dem"
CONFIG_PATH = SCRIPTS_DIR / "pipeline.config.json"
PUBLIC_DATA_DIR = REPO_ROOT / "huts" / "public" / "data"


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


WSL_MICROMAMBA_ROOT = "~/micromamba"
WSL_MICROMAMBA_BIN = "~/mm/bin/micromamba"
WSL_TIPPECANOE_ENV = "tippecanoe"


def _to_wsl_path(arg: str) -> str:
    """Translates a Windows absolute path (e.g. E:\\foo\\bar) to its WSL /mnt/ mount equivalent
    (/mnt/e/foo/bar). Leaves anything that isn't a drive-letter path (flags, numbers) untouched."""
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", arg)
    if not m:
        return arg
    drive, rest = m.groups()
    return f"/mnt/{drive.lower()}/{rest.replace(chr(92), '/')}"


def materialize_geotiff(vrt_path: Path, out_path: Path) -> Path:
    """Bakes a (possibly lazily-reprojecting) VRT into a real, tiled/compressed GeoTIFF.

    dem.vrt's composite provider chains several layers of on-the-fly `gdalwarp`-built VRTs (each
    region's per-tile reprojection from its native CRS into EPSG:4326) - reading from it, as
    08-add-elevation.py does, re-runs that reprojection math for every pixel touched, every time.
    Timed at ~750s for a read covering AT+Bavaria (data/timings.jsonl, phase read_dem_window) -
    almost all CPU, not I/O, since the underlying GeoTIFF/XYZ tiles are already local. Materializing
    once here means step 07 (already freshness-cached, rarely rerun) pays that reprojection cost
    instead of every step 08 run - and 08 is explicitly the step people rerun repeatedly, to
    retune --ele-noise-threshold-m.

    -a_nodata copies NoDataValue from vrt_path explicitly (see composite.py's
    _normalize_colorinterp for why this isn't left to gdal_translate's implicit passthrough).
    PREDICTOR=3 is the floating-point predictor, which improves DEFLATE's ratio on elevation
    data specifically (vs. the integer predictor default)."""
    import rasterio

    with rasterio.open(vrt_path) as src:
        nodata = src.nodata

    args = [
        "gdal_translate", "-of", "GTiff",
        "-co", "TILED=YES", "-co", "COMPRESS=DEFLATE", "-co", "PREDICTOR=3",
        "-co", "BIGTIFF=IF_SAFER",
        "--config", "GDAL_NUM_THREADS", "ALL_CPUS",
    ]
    if nodata is not None:
        args += ["-a_nodata", str(nodata)]
    args += [str(vrt_path), str(out_path)]
    subprocess.run(args, check=True)
    return out_path


def run_tippecanoe(tippecanoe_args):
    """Shells out to tippecanoe, natively if it's on PATH (Linux/macOS), otherwise via WSL - it
    has no Windows build on conda-forge (linux-64/osx-64 only). See pipeline/README.md's "Displaying
    the raw OSM trails" section for how the WSL-side micromamba env was created."""
    if shutil.which("tippecanoe"):
        subprocess.run(["tippecanoe", *tippecanoe_args], check=True)
        return
    if platform.system() != "Windows":
        raise RuntimeError(
            "tippecanoe not found on PATH. Install it (conda-forge on Linux/macOS) - see "
            "pipeline/README.md."
        )
    inner_cmd = (
        f"{WSL_MICROMAMBA_BIN} run -r {WSL_MICROMAMBA_ROOT} -n {WSL_TIPPECANOE_ENV} tippecanoe "
        + " ".join(shlex.quote(_to_wsl_path(a)) for a in tippecanoe_args)
    )
    subprocess.run(["wsl", "bash", "-lc", inner_cmd], check=True)


def hut_points(huts_path, filter_bbox=None):
    """Returns every [lng, lat] in huts_path (script 05's output), narrowed to filter_bbox if
    given. huts.geojson holds every hut in the pipeline's whole scope (both Austria and Bavaria),
    so filter_bbox picks out the huts that actually belong to one region (e.g. Bavaria's rough
    state boundary)."""
    with open(huts_path, encoding="utf-8") as f:
        huts_fc = json.load(f)

    points = []
    for feat in huts_fc["features"]:
        lng, lat = feat["geometry"]["coordinates"]
        if filter_bbox is not None and not (
            filter_bbox["minLng"] <= lng <= filter_bbox["maxLng"]
            and filter_bbox["minLat"] <= lat <= filter_bbox["maxLat"]
        ):
            continue
        points.append([lng, lat])

    if not points:
        raise ValueError(f"no huts found inside filter_bbox {filter_bbox} in {huts_path}")
    return points


def edge_points(edges_path, filter_bbox=None):
    """Returns every trail-polyline vertex [lng, lat] in edges_path (script 06's hut-edges.geojson
    output), narrowed to filter_bbox if given. Vertices trace the actual trail geometry between
    huts, not just the hut endpoints - this is exactly what 08-add-elevation.py samples, so a
    DEM-tile selection built from these points needs no separate assumption about how far a trail
    can wander from its endpoints (see bufferKm in bavaria_dgm.py's tiles_for_points - no longer
    needs to be sized off graph.maxEdgeKm)."""
    with open(edges_path, encoding="utf-8") as f:
        edges_fc = json.load(f)

    points = []
    for feat in edges_fc["features"]:
        for lng, lat in feat["geometry"]["coordinates"]:
            if filter_bbox is not None and not (
                filter_bbox["minLng"] <= lng <= filter_bbox["maxLng"]
                and filter_bbox["minLat"] <= lat <= filter_bbox["maxLat"]
            ):
                continue
            points.append([lng, lat])

    if not points:
        raise ValueError(f"no edge vertices found inside filter_bbox {filter_bbox} in {edges_path}")
    return points


def bbox_from_huts(huts_path, filter_bbox=None, buffer_deg=0.05):
    """Computes a tight {minLng,maxLng,minLat,maxLat} covering every hut in huts_path, instead of
    a hand-picked political-boundary box. buffer_deg pads the result so DEM coverage doesn't clip
    right at a hut's coordinate; a hut's trail edges (see hut-edges.geojson) extend somewhat past
    the hut point itself, and elevation sampling needs the trail's terrain, not just the
    endpoint's.

    Huts scattered across a wide area (e.g. Bavaria's alpine-fringe cluster plus a few outlying
    non-alpine AV huts up near the Bavarian Forest) make this a poor shape for a per-tile DEM
    fetch: the enclosing rectangle balloons to cover empty terrain between clusters. Callers doing
    a tile-per-request fetch (bavaria_dgm.py) should use hut_points() + a per-point buffer instead
    - this bbox is for providers that only need a coarse fetch extent (e.g. a single bulk
    download)."""
    points = hut_points(huts_path, filter_bbox)
    lngs = [p[0] for p in points]
    lats = [p[1] for p in points]

    return {
        "minLng": min(lngs) - buffer_deg,
        "maxLng": max(lngs) + buffer_deg,
        "minLat": min(lats) - buffer_deg,
        "maxLat": max(lats) + buffer_deg,
    }
