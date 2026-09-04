"""Shells out to tippecanoe for the two postprocessing tiling scripts (build_edge_tiles.py,
build_trail_tiles.py), natively if it's on PATH (Linux/macOS) or via WSL otherwise - tippecanoe
has no Windows build on conda-forge (linux-64/osx-64 only). See pipeline/README.md's "Setup: the
`alpen-osm` pixi env" section for how the WSL-side micromamba env was created.

Also owns build_pmtiles(), the geojsonseq -> mbtiles -> pmtiles conversion shared by both of
those scripts, so the tippecanoe flags and cleanup step live in one place instead of two."""

import platform
import re
import shlex
import shutil
import subprocess
from pathlib import Path

from pmtiles.convert import mbtiles_to_pmtiles

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


def build_pmtiles(timer, input_path: Path, mbtiles_path: Path, out_path, layer_name: str,
                   min_zoom: int, max_zoom: int) -> None:
    """Tiles a geojsonseq input into an mbtiles archive, repacks it into a flat-file pmtiles
    archive, then deletes both intermediates - the shape build_trail_tiles.py and
    build_edge_tiles.py each used to hand-roll separately (same tippecanoe flags,
    --drop-densest-as-needed thinning dense areas at low zoom rather than failing on tile-size
    limits). `timer` is a lib.timing.StepTimer; the two steps land as "tippecanoe" and
    "mbtiles_to_pmtiles" so a slow run says which one grew."""
    input_path, mbtiles_path = Path(input_path), Path(mbtiles_path)
    with timer.step("tippecanoe"):
        run_tippecanoe([
            "-o", str(mbtiles_path), "-l", layer_name,
            "-Z", str(min_zoom), "-z", str(max_zoom),
            "--drop-densest-as-needed", "--force", str(input_path),
        ])
    with timer.step("mbtiles_to_pmtiles"):
        mbtiles_to_pmtiles(str(mbtiles_path), str(out_path), max_zoom)
    input_path.unlink(missing_ok=True)
    mbtiles_path.unlink(missing_ok=True)
