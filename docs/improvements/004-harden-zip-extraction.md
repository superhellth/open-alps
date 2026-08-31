# Plan 004: Validate zip member paths before extracting DEM archives

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 3e59f51..HEAD -- pipeline/phases/downloads/dem_providers pipeline/lib/pipeline.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `3e59f51`, 2026-08-31

## Why this matters

Two DEM provider scripts download a zip archive from a third-party URL and extract it with
`zipfile.ZipFile(...).extractall(extract_dir)`, with no validation of the member paths inside the
archive:

- `phases/downloads/dem_providers/at_bev.py:37-38` — one ~1.9GB national zip from
  `gis.ktn.gv.at` (Austria's BEV DGM)
- `phases/downloads/dem_providers/bavaria_dgm.py:221-222` — one small zip per 1km tile from
  `download1.bayernwolke.de` (Bavaria's DGM5), potentially thousands of tiles per run

`zipfile.extractall` does not sanitize member names by default: a crafted zip entry with a `../`
path segment, or an absolute path, can write outside `extract_dir` onto whatever machine runs the
pipeline (classic "zip-slip"). The pixi env here pins Python 3.11 (`pipeline/pixi.toml`'s
`python = "3.11.*"`), so `zipfile`'s newer `extractall(path, filter="data")` guard (added in
Python 3.12) isn't available — this needs an explicit member-path check.

Both source hosts are legitimate government open-data providers over HTTPS, so the realistic
threat here is narrow (a compromised host, a mis-configured redirect, or a TLS-interception setup
that trusts a locally-added root certificate) — this is defense-in-depth, not a response to a
known live exploit. It's cheap to close and worth doing because the pipeline runs with the
operator's own filesystem permissions and no sandboxing.

## Current state

`phases/downloads/dem_providers/at_bev.py:24-38` (full `fetch` function):

```python
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
        return sorted(extract_dir.rglob("*.tif"))

    return [dst]
```

`phases/downloads/dem_providers/bavaria_dgm.py`'s per-tile fetch (around lines 199-222, the
relevant tail):

```python
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extract_dir)

    grids = sorted(extract_dir.rglob("*.txt"))
    return grids[0] if grids else None
```

`lib/pipeline.py` (full file today, 30 lines) holds shared path constants (`OSM_DIR`, `DEM_DIR`,
`PUBLIC_DATA_DIR`, ...) and `load_config()` — its docstring currently says "Single config reader
shared by every pipeline script." Adding one small, generically-useful helper here (rather than
duplicating the check in both provider files) is a reasonable, narrow extension of what this
module already does in practice (it already holds more than just the config reader, per its own
`SCRIPTS_DIR`/`DATA_DIR`/etc. constants) — update its docstring's first line to reflect the
broadened scope as part of this change (see Step 1).

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Run pipeline tests | `pixi run pytest -q` (from `pipeline/`) | all pass |
| Run just the new/affected tests | `pixi run pytest tests/test_at_bev_bbox.py tests/test_bavaria_tile_grid.py tests/test_pipeline_lib.py -q` (last file may not exist yet — see Step 3) | all pass |

## Scope

**In scope** (the only files you should modify):
- `pipeline/lib/pipeline.py` — add `safe_extractall(zf, extract_dir)`
- `pipeline/phases/downloads/dem_providers/at_bev.py` — use it
- `pipeline/phases/downloads/dem_providers/bavaria_dgm.py` — use it
- `pipeline/tests/test_pipeline_lib.py` (new file, or an existing test file for `lib/pipeline.py`
  if one already exists — check `tests/` first; none was found as of this plan's writing)

**Out of scope**:
- Do NOT add checksum/hash verification of downloaded archives — that's a separate, lower-priority
  finding (not selected for a plan) given these Geofabrik/government sources don't publish stable
  checksums for regenerating extracts.
- Do NOT touch `phases/downloads/dem_providers/copernicus.py` or `composite.py` — neither extracts
  zip archives (confirm by grepping `zipfile` in those files before assuming; if either does
  extract a zip and this plan's excerpts are stale, treat that as a STOP condition, not silent
  extra scope).
- Do NOT change retry/timeout/download logic in either provider file — only the extraction step.

## Git workflow

- Branch: stay on the current branch unless the operator says otherwise.
- Commit message style: lowercase, `<module>: <imperative description>`, e.g. `downloads: validate
  zip member paths before extracting DEM archives`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add `safe_extractall` to `lib/pipeline.py`

Add this function and the `zipfile` import:

```python
import zipfile

def safe_extractall(zf: "zipfile.ZipFile", extract_dir: Path) -> None:
    """Extracts every member of zf into extract_dir, rejecting any member whose resolved path
    would land outside extract_dir (zip-slip: a '../' path segment or an absolute path in a
    malicious/corrupted archive). zipfile.ZipFile.extractall() does not do this itself on the
    Python 3.11 this pipeline's pixi env pins (the filter= guard was added in 3.12) - see
    docs/superpowers/specs/... (link the finding/plan here is unnecessary; this docstring is
    enough) for why this matters for archives fetched from third-party DEM providers."""
    extract_dir = extract_dir.resolve()
    for member in zf.infolist():
        target = (extract_dir / member.filename).resolve()
        if target != extract_dir and extract_dir not in target.parents:
            raise ValueError(
                f"refusing to extract {member.filename!r}: resolves outside {extract_dir}"
            )
    zf.extractall(extract_dir)
```

Update the module docstring's first line from "Single config reader shared by every pipeline
script..." to something like "Config reader plus small shared filesystem helpers used across
pipeline scripts (pipeline.config.json is still the one source of truth for hyperparameters)." —
keep the rest of the existing docstring content (the `bbox`/`regions`/etc. mention) unchanged.

**Verify**: `pixi run python -c "import sys; sys.path.insert(0, '.'); from lib.pipeline import safe_extractall; print('ok')"` (from `pipeline/`) → prints `ok`.

### Step 2: Use it in both DEM provider scripts

In `at_bev.py`, change:

```python
    if dst.suffix == ".zip":
        extract_dir = raw_dir / dst.stem
        if not extract_dir.exists():
            with zipfile.ZipFile(dst) as zf:
                zf.extractall(extract_dir)
        return sorted(extract_dir.rglob("*.tif"))
```

to:

```python
    if dst.suffix == ".zip":
        extract_dir = raw_dir / dst.stem
        if not extract_dir.exists():
            with zipfile.ZipFile(dst) as zf:
                safe_extractall(zf, extract_dir)
        return sorted(extract_dir.rglob("*.tif"))
```

adding `from lib.pipeline import safe_extractall` to its imports (check how the file currently
imports from `lib` — it may need a `sys.path.insert` similar to other phase scripts; look at a
neighboring provider file like `composite.py` or `copernicus.py` for the existing import pattern
in this subpackage and match it).

In `bavaria_dgm.py`, change:

```python
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extract_dir)
```

to:

```python
    with zipfile.ZipFile(zip_path) as zf:
        safe_extractall(zf, extract_dir)
```

with the same import addition.

**Verify**: `pixi run pytest tests/test_at_bev_bbox.py tests/test_bavaria_tile_grid.py -q` → all
pass (these existing tests don't exercise `fetch()`'s network/extraction path directly per their
names — confirm by reading them; if they do call `fetch()`, this verifies the change didn't break
extraction for any fixture zip they already use).

### Step 3: Add tests for `safe_extractall`

Create `pipeline/tests/test_pipeline_lib.py` (or add to an existing `lib/pipeline.py` test file if
you find one that this plan's recon missed — check `tests/` for a `test_pipeline.py` first):

```python
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from lib.pipeline import safe_extractall  # noqa: E402


def _make_zip(path: Path, entries: dict) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)


def test_safe_extractall_extracts_well_formed_archive(tmp_path):
    zip_path = tmp_path / "good.zip"
    _make_zip(zip_path, {"a.txt": "hello", "sub/b.txt": "world"})
    extract_dir = tmp_path / "out"
    with zipfile.ZipFile(zip_path) as zf:
        safe_extractall(zf, extract_dir)
    assert (extract_dir / "a.txt").read_text() == "hello"
    assert (extract_dir / "sub" / "b.txt").read_text() == "world"


def test_safe_extractall_rejects_path_traversal(tmp_path):
    zip_path = tmp_path / "evil.zip"
    _make_zip(zip_path, {"../../evil.txt": "pwned"})
    extract_dir = tmp_path / "out"
    with zipfile.ZipFile(zip_path) as zf:
        with pytest.raises(ValueError):
            safe_extractall(zf, extract_dir)
    assert not (tmp_path.parent.parent / "evil.txt").exists()


def test_safe_extractall_rejects_absolute_path(tmp_path):
    zip_path = tmp_path / "evil_abs.zip"
    # zipfile normally strips a leading "/" on extractall, but ZipInfo can still carry one -
    # writestr with an absolute-looking name to exercise the check regardless of that stripping.
    _make_zip(zip_path, {"/etc/evil.txt": "pwned"})
    extract_dir = tmp_path / "out"
    with zipfile.ZipFile(zip_path) as zf:
        with pytest.raises(ValueError):
            safe_extractall(zf, extract_dir)
```

Run these first to confirm they fail against a naive `extractall` call (temporarily, mentally or
by testing) and pass against `safe_extractall` — the point is they must actually exercise the
rejection path, not just check the happy path.

**Verify**: `pixi run pytest tests/test_pipeline_lib.py -v` → all 3 pass.

## Test plan

- New tests in `tests/test_pipeline_lib.py`: well-formed extraction still works; `../` traversal
  raises `ValueError` and doesn't write outside `extract_dir`; an absolute-path member also raises.
- Existing tests: `tests/test_at_bev_bbox.py`, `tests/test_bavaria_tile_grid.py` must still pass —
  they test bbox/tile-grid math independent of extraction, per their names, so they should be
  unaffected; running them confirms no import/wiring breakage from the new import in the provider
  files.
- Verification: `pixi run pytest -q` (from `pipeline/`) → all pass.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `pixi run pytest -q` (from `pipeline/`) → all pass, same or greater count than baseline
- [ ] `grep -n "extractall" pipeline/phases/downloads/dem_providers/at_bev.py pipeline/phases/downloads/dem_providers/bavaria_dgm.py` shows only calls to `safe_extractall`, not a bare `zf.extractall`
- [ ] New tests in `tests/test_pipeline_lib.py` exist and pass, including the two rejection cases
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- Either provider script's `fetch`/extraction code differs materially from the excerpts above.
- `copernicus.py` or `composite.py` turns out to also call `zipfile.extractall` directly — report
  rather than silently expanding scope to cover it (it may warrant its own plan, or may already be
  covered by a shared helper this plan's author didn't see).
- The import pattern in `at_bev.py`/`bavaria_dgm.py` for pulling in names from `lib/` isn't a
  simple `from lib.pipeline import ...` (e.g. requires a `sys.path.insert` boilerplate this plan
  didn't anticipate) — adapt to match the file's existing pattern rather than guessing; if truly
  unclear, report and ask.

## Maintenance notes

- Any future DEM provider (or other pipeline script) that extracts a downloaded archive should use
  `lib.pipeline.safe_extractall` from the start rather than calling `zipfile.extractall` directly.
- If the pixi env's pinned Python version is ever bumped to 3.12+, a reviewer could consider
  replacing this hand-rolled check with `zf.extractall(extract_dir, filter="data")`
  (stdlib-native) — not required now, just a simplification available later.
