"""Shared building blocks for pipeline/dag/*.py's task_* functions, extracted from dodo.py so the
DAG-wiring modules only contain the DAG itself, not doit-workaround plumbing.

py()/rel() build the two things every task needs (an action command line, and path strings doit
can hash consistently) exactly as dodo.py used to inline them - see rel()'s docstring below for
why the path form matters. cli_param()/tracking_param() and pipeline_task() exist to collapse the
repeated "build a params list, decide whether each param appears in the action string too, remember
to attach TaskOptionsChanged()" shape that used to be hand-written in every task_* function - see
pipeline_task()'s docstring.
"""

import json
import os
import sys
from pathlib import Path

from doit.cmd_base import Globals
from doit.reporter import ConsoleReporter

from lib.pipeline import SCRIPTS_DIR

SCRIPT_DIR = SCRIPTS_DIR  # pipeline/, where dodo.py lives - see rel()'s docstring


def rel(path) -> str:
    """file_dep/targets entries use this instead of a bare str(path): doit's dependency DB keys
    each file's tracked hash by the literal string given here, resolved against doit's own cwd
    (SCRIPT_DIR - pipeline/; both pixi.toml's [tasks] and the README's manual conda flow always run
    doit from there). OSM_DIR/DEM_DIR/PUBLIC_DATA_DIR (lib/pipeline.py) are absolute, .resolve()d
    paths - deliberately, so a worktree's data/ symlink and the main checkout's real data/ dir
    produce identical strings on the SAME machine/OS. But an absolute path is still different text
    on native Windows (C:\\Users\\...) vs WSL (/home/...) for the exact same file, so switching
    between them makes every file_dep look "moved" and forces a full rebuild (seen switching this
    pipeline from native-Windows conda to WSL/pixi - see git history around the pixi migration). A
    path relative to SCRIPT_DIR, normalized to forward slashes, is identical text regardless of OS
    or which machine last ran doit - only the *content* of pipeline.config.json/scripts should
    invalidate a task, not which OS wrote the cache. Actions (subprocess/script CLI args) are
    untouched by this - they still use OSM_DIR/DEM_DIR absolute paths directly, since those are
    just runtime arguments to a fresh process each run, not something doit hashes and compares
    across runs."""
    return os.path.relpath(Path(path).resolve(), SCRIPT_DIR).replace(os.sep, "/")


def py(script, *args) -> str:
    parts = [f'"{sys.executable}"', f'"{SCRIPT_DIR / script}"', *[str(a) for a in args]]
    return " ".join(parts)


class TaskOptionsChanged:
    """uptodate check: rerun a task if its own resolved param values (task.options - the CLI
    flags/defaults doit already parsed for it, e.g. --tile-size-km) changed since its last
    successful run. This is what `config_changed(json.dumps(task.options, sort_keys=True))` is
    meant to do, but doit only registers the "persist this digest after success" hook
    (Task._init_uptodate, doit/task.py) for uptodate items that expose a `configure_task` method -
    a bare `config_changed(...)` instance has one, but wrapping it in
    `lambda task, values: config_changed(...)(task, values)` hides it behind a plain lambda, so the
    digest never gets saved and the task shows "not up to date" on every single future run,
    forever, even immediately after a clean success. That silently defeated caching for
    build_base_graph/build_hub_edges/compute_edge_profiles (add_base_elevation at the time this was
    fixed, later split into sample_base_elevation + compute_edge_profiles) - among the tasks this
    pipeline most needs NOT to rerun by accident (multi-hour rebuilds; see pipeline/CLAUDE.md
    "Timing pipeline phases").

    Second, unrelated bug this class works around: doit only calls Task.init_options() (which
    populates task.options from parsed CLI flags/defaults - see doit/task.py) for tasks named
    directly in the command-line selection (TaskControl._process_filter, doit/control.py). A task
    reached only transitively, as someone else's file_dep/task_dep - e.g. download_extracts when
    you run `doit build_base_graph` - never gets init_options() called, so task.options stays
    None. json.dumps(None) ('null') then never matches the saved digest, so __call__ below would
    return False unconditionally, forcing a full rerun of every upstream task not named on the
    command line, every time - defeating the cache exactly for the deep, expensive tasks
    (downloads, merges) that most need it. init_options() is idempotent (task.py: only acts `if
    self.options is None`), so calling it here is a safe way to guarantee options are populated
    before comparing, regardless of whether doit already did it.

    Only relevant to tasks with real params - a task with no params doesn't need this at all."""

    def configure_task(self, task):
        task.value_savers.append(
            lambda: {"_task_options": json.dumps(task.options, sort_keys=True)}
        )

    def __call__(self, task, values):
        task.init_options()
        return values.get("_task_options") == json.dumps(task.options, sort_keys=True)


class FlushingReporter(ConsoleReporter):
    """Flush the dep-db to disk after every task, not just once at the end of the whole run.

    doit's runner only calls dep_manager.close() (-> one dump() of every task's saved digest)
    in a try/finally around the *entire* task_dispatcher loop (doit/runner.py Runner.finish()) -
    a clean failure or Ctrl-C still hits that finally, but a harder kill (OOM - this pipeline
    materializes multi-GB GeoTIFFs, terminal closed, SIGKILL) skips it, silently losing every
    already-completed task's state from that run, not just the one that was interrupted. That's
    what made fetch_dem/build_dem_vrt look like they never ran even right after they did.

    Requires DOIT_CONFIG["backend"] = "json": JsonDB.dump() just reopens/rewrites the whole file
    each call, safe to call repeatedly. DbmDB/SqliteDB both permanently close their handle/
    connection on the first dump() (doit/dependency.py), so a second call would raise."""

    def add_success(self, task):
        super().add_success(task)
        if Globals.dep_manager is not None:
            Globals.dep_manager.backend.dump()


def cli_param(name, long, type_, default):
    """A param exposed as an actual --flag AND, when passed to pipeline_task()'s `params=`,
    interpolated into the action command line as `--{long} %(name)s`."""
    return {"name": name, "long": long, "type": type_, "default": default}


def tracking_param(name, type_, default):
    """A param that must invalidate the task's cache (via TaskOptionsChanged) when the config
    value it mirrors changes, but isn't itself passed to the script - the script reads that config
    value directly (it's not a sensible CLI flag: a whole dict/list, or a value with no
    corresponding flag on the script). Pass to pipeline_task()'s `tracking_params=`, never
    `params=` - a tracking param must NOT be interpolated into the action string, since nothing on
    the script side consumes it."""
    long = name.replace("_", "-")
    return {"name": name, "long": long, "type": type_, "default": default}


def pipeline_task(script, *, args=(), params=(), tracking_params=(),
                   file_dep=(), targets=(), task_dep=None):
    """Builds one doit task dict for a phase script, collapsing the shape every task_* function
    used to hand-write: an action command line, file_dep/targets normalized through rel(), and -
    if there are any params at all - a params list plus TaskOptionsChanged() so a config-only
    retune (no file_dep change) still reruns the task instead of doit reporting "up to date".

    - script: path to the phase script, relative to pipeline/ (e.g. "phases/downloads/fetch_huts.py")
    - args: literal action-string fragments that come before the params flags (e.g. "--edges-dir
      <path>" for a fixed runtime path, not a tracked config value)
    - params: cli_param(...) entries - each becomes both a real --flag on the action command line
      AND part of the tracked digest
    - tracking_params: cli_param(...)/tracking_param(...) entries that are tracked (so
      TaskOptionsChanged sees them) but NOT interpolated into the action - use this for a config
      value the script reads directly rather than via a CLI flag
    - file_dep/targets: Path objects; rel() is applied automatically
    - task_dep: task names this task must run after (for outputs rewritten in place rather than
      declared as a shared target - doit forbids two tasks sharing one target)
    """
    action_parts = [str(a) for a in args] + [f"--{p['long']} %({p['name']})s" for p in params]
    task = {
        "actions": [py(script, *action_parts)],
        "file_dep": [rel(p) for p in file_dep],
        "targets": [rel(p) for p in targets],
    }
    all_params = [*params, *tracking_params]
    if all_params:
        task["params"] = all_params
        task["uptodate"] = [TaskOptionsChanged()]
    if task_dep:
        task["task_dep"] = list(task_dep)
    return task
