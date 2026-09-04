"""Config reader plus small shared filesystem helpers used across pipeline scripts
(pipeline.config.json is still the one source of truth for hyperparameters: bbox, regions, tag
filter, graph thresholds)."""

import json
import zipfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SCRIPTS_DIR.parent
# .resolve() so a worktree's data/ symlink and the main checkout's real data/ dir produce
# identical path strings - doit's dependency db is keyed by path text, and a checkout-relative
# (unresolved) path here makes every file_dep look "moved" when run from a worktree, which
# defeats the cache doit relies on for multi-hour tasks (see pipeline/CLAUDE.md "Timing pipeline
# phases" and root CLAUDE.md's pipeline-task warning). This absolute path is still exactly what
# dodo.py's file_dep/targets use as the literal string doit hashes/keys by - which is why dodo.py
# wraps every one of those in its own rel() helper before handing them to doit, converting back to
# a SCRIPT_DIR-relative, forward-slash path: an absolute path is stable across worktrees on the
# SAME machine/OS (that's what this .resolve() buys), but is still different text entirely between
# native Windows and WSL for the identical file, which broke caching across a pixi/WSL migration
# the same way an unresolved worktree path used to. See rel()'s own docstring in dodo.py.
DATA_DIR = (REPO_ROOT / "data").resolve()
OSM_DIR = DATA_DIR / "osm"
DEM_DIR = DATA_DIR / "dem"
CONFIG_PATH = SCRIPTS_DIR / "pipeline.config.json"
PUBLIC_DATA_DIR = REPO_ROOT / "huts" / "public" / "data"
TOURS_DIR = SCRIPTS_DIR / "tours"
QUALITY_DIR = DATA_DIR / "quality"


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def safe_extractall(zf: "zipfile.ZipFile", extract_dir: Path) -> None:
    """Extracts every member of zf into extract_dir, rejecting any member whose resolved path
    would land outside extract_dir (zip-slip: a '../' path segment or an absolute path in a
    malicious/corrupted archive). zipfile.ZipFile.extractall() does not do this itself on the
    Python 3.11 this pipeline's pixi env pins (the filter= guard was added in 3.12) - matters for
    archives fetched from third-party DEM providers."""
    extract_dir = extract_dir.resolve()
    for member in zf.infolist():
        target = (extract_dir / member.filename).resolve()
        if target != extract_dir and extract_dir not in target.parents:
            raise ValueError(
                f"refusing to extract {member.filename!r}: resolves outside {extract_dir}"
            )
    zf.extractall(extract_dir)
