"""Single config reader shared by every pipeline script, so pipeline.config.json is the
one source of truth for hyperparameters (bbox, regions, tag filter, graph thresholds)."""

import json
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


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)
