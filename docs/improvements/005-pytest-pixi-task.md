# Plan 005: Add a discoverable `pixi run test` task and document it

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 3e59f51..HEAD -- pipeline/pixi.toml pipeline/README.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: dx
- **Planned at**: commit `3e59f51`, 2026-08-31

## Why this matters

`pipeline/tests/` has 40 test files and `pytest` is already a listed dependency
(`pipeline/pixi.toml`'s `[pypi-dependencies]`), but there is no documented or scripted one-command
way to run the suite: `pixi.toml`'s `[tasks]` section only defines `doit = "doit"`, and the string
`pytest` appears nowhere in `pipeline/README.md`, `pipeline/CLAUDE.md`, or any `phases/*/README.md`.
Anyone onboarding — human or another agent — has to guess `pixi run pytest` (which does work, since
`pytest` is on the env's PATH via the pypi-dependency, but nothing says so) rather than finding a
documented, one-command verification loop the way `huts/`'s `npm test` is documented in the root
`CLAUDE.md`. This is the cheapest, lowest-risk fix in this batch and should land early since every
other plan in this batch (and any future pipeline change) benefits from a clearly-documented test
command.

## Current state

`pipeline/pixi.toml` (full file, 29 lines):

```toml
[workspace]
name = "alpen-osm"
version = "0.1.0"
description = "Offline hut-to-hut trail graph pipeline (OSM + DEM -> routing graph)"
channels = ["conda-forge"]
platforms = ["linux-64", "osx-64", "osx-arm64"]

[dependencies]
python = "3.11.*"
osmium-tool = "*"
pyosmium = "*"
scipy = "*"
numpy = "*"
python-igraph = "*"
gdal = "*"
rasterio = "*"
orjson = "*"
psutil = "*"
shapely = "*"
tippecanoe = "*"
pip = "*"

[pypi-dependencies]
pmtiles = "*"
doit = "*"
pytest = "*"

[tasks]
doit = "doit"
```

`pipeline/README.md`'s "Setup" section (the doc that already documents `pixi install`/`pixi run
doit`) has no equivalent line for tests. Confirmed via `grep -rn pytest pipeline/README.md
pipeline/CLAUDE.md pipeline/phases/*/README.md` returning nothing.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Run pipeline tests today (before this plan) | `pixi run pytest -q` (from `pipeline/`) | `326 passed` (or more, if other plans in this batch landed first) |
| Confirm the new task works | `pixi run test` (from `pipeline/`) | same result as `pixi run pytest -q` |

## Scope

**In scope** (the only files you should modify):
- `pipeline/pixi.toml`
- `pipeline/README.md`

**Out of scope**:
- Do NOT add a CI workflow file — that's a separate, larger finding not selected for a plan in
  this batch (add `.github/workflows/...` is bigger scope: deciding a runner, caching the pixi
  env, etc.). This plan is scoped to local discoverability only.
- Do NOT add lint/typecheck tasks — no lint tool is currently configured for `pipeline/` (see
  "Maintenance notes"); adding one is out of scope here.
- Do NOT change any test file or test behavior.

## Git workflow

- Branch: stay on the current branch unless the operator says otherwise.
- Commit message style: lowercase, `<module>: <imperative description>`, e.g. `pixi: add a test
  task and document it`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add a `test` task to `pixi.toml`

Change:

```toml
[tasks]
doit = "doit"
```

to:

```toml
[tasks]
doit = "doit"
test = "pytest"
```

**Verify**: `pixi run test` (from `pipeline/`) → same pass count as `pixi run pytest -q` gives
today (run both once to compare output).

### Step 2: Document it in `pipeline/README.md`

Find the "Setup: the `alpen-osm` pixi env" section (it ends with a `pixi run osmium --version`
sanity-check line and a note about `pixi shell`). Immediately after that section's closing
paragraph (the `pixi run <cmd>` / `pixi shell` explanation), add a short new subsection:

```markdown
## Running tests

```bash
pixi run test          # equivalent to: pixi run pytest
```

Fast (a few seconds, no real `data/` outputs needed — every test uses small synthetic
fixtures) and safe to run anytime; unlike the `doit` tasks above, no test touches `data/` or
downloads anything.
```

Adjust wording/placement slightly if the surrounding section headings don't match exactly what's
quoted here (re-read the live file first) — the goal is one clearly-titled, easy-to-find
subsection near the setup instructions, not an exact string match to this plan's wording.

**Verify**: `grep -n "pixi run test" pipeline/README.md` → at least one match.

## Test plan

No new test files — this plan only adds a task runner alias and documentation. The verification is
that the alias produces identical results to the command it wraps.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `pixi run test` (from `pipeline/`) exits 0 with the same pass count as `pixi run pytest -q`
- [ ] `grep -n 'test = "pytest"' pipeline/pixi.toml` matches
- [ ] `grep -n "pixi run test" pipeline/README.md` matches at least once
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- `pixi.toml`'s `[tasks]` section already has a `test` key (name collision) when you go to edit it
  — report what it currently does rather than overwriting.
- `pixi run test` doesn't actually invoke pytest (e.g. some pixi version/config quirk) — report
  the exact output rather than declaring done criteria met without live verification.

## Maintenance notes

- This plan deliberately doesn't add lint/typecheck tooling or CI — those are larger, separate
  decisions (tool choice for lint, e.g. `ruff`; a GitHub Actions workflow) better handled as their
  own follow-up once the operator has decided on a lint tool, per the "considered and rejected /
  deferred" convention in `plans/README.md`.
- If a CI workflow is added later, it should call `pixi run test` (this task) rather than
  `pixi run pytest` directly, so the one canonical command stays in sync between local and CI use.
