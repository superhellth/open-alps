"""doit task wiring for phases/elevation/ - materializes the DEM and derives per-edge time/ascent/
descent on the base graph.

sample_base_elevation/compute_edge_profiles are two tasks, not one, because only
sample_base_elevation needs to read the DEM: compute_edge_profiles only reacts to
--smoothing-kernel-m/speed-model retunes, and used to force a full DEM resample on every retune
when this was a single task (add_base_elevation, since removed - see pipeline/CLAUDE.md "Timing
pipeline phases" for the ~750s read_dem_window cost that motivated the split). Neither is
force-rerun for the same reason build_base_graph/build_hub_edges aren't (see graph_building.py).

build_profiles is meant to stay cheap - retuning --profile-points must not force a re-route or a
DEM read (spec B4) - so its file_dep excludes the DEM and it never depends on sample_base_elevation.
"""

from lib.doit_support import cli_param, pipeline_task
from lib.pipeline import DEM_DIR, OSM_DIR, load_config

CONFIG = load_config()


def task_build_dem_vrt():
    return pipeline_task(
        "phases/elevation/build_dem_vrt.py",
        file_dep=[DEM_DIR / "fetch_manifest.json"],
        targets=[DEM_DIR / "dem.vrt", DEM_DIR / "dem.tif"],
    )


def task_sample_base_elevation():
    return pipeline_task(
        "phases/elevation/sample_base_elevation.py",
        # spec B5: the elevation pass genuinely needs the DEM, so declare it - the previous
        # numbering-convention-only ordering let a stale dem.tif through silently.
        file_dep=[OSM_DIR / "base_graph" / "manifest.json", DEM_DIR / "dem.tif"],
        targets=[OSM_DIR / "base_graph" / "node_ele.npy", OSM_DIR / "base_graph" / "interior_ele.npy"],
    )


def task_compute_edge_profiles():
    speed = CONFIG["graph"]["speedModel"]
    return pipeline_task(
        "phases/elevation/compute_edge_profiles.py",
        params=[
            cli_param("smoothing_kernel_m", "smoothing-kernel-m", float,
                      CONFIG["dem"]["smoothingKernelM"]),
            # every value compute_edge_profiles.py's time_s computation reads from speedModel must
            # be its own tracked param, or a routing_probe.py recalibration that touches only
            # speedModel would leave TaskOptionsChanged() reporting "up to date".
            cli_param("speed_v0", "speed-v0", float, speed["v0"]),
            cli_param("speed_k", "speed-k", float, speed["k"]),
            cli_param("speed_s0", "speed-s0", float, speed["s0"]),
        ],
        task_dep=["sample_base_elevation"],
        file_dep=[OSM_DIR / "base_graph" / "node_ele.npy", OSM_DIR / "base_graph" / "interior_ele.npy"],
        # edges.npy is rewritten in place but can't be this task's target (build_base_graph already
        # owns it, and doit forbids two tasks sharing one target) - this stamp is the completion
        # signal downstream tasks key off of instead.
        targets=[OSM_DIR / "base_graph" / "edge_profiles.stamp"],
    )


def task_build_profiles():
    # Genuinely was seconds until start_edges grew to ~235k records / ~200M geometry points
    # (2026-08-27), at which point the point-at-a-time _fill_unmatched loop dominated the runtime
    # (~800s of an ~830s run, data/timings.jsonl) - fixed by vectorizing it. Check
    # timings.jsonl's hut_edges_s/start_edges_s split before assuming this stays cheap.
    return pipeline_task(
        "phases/elevation/build_profiles.py",
        params=[cli_param("profile_points", "profile-points", int,
                          CONFIG["dem"].get("profilePoints", 30))],
        task_dep=["build_hub_edges", "match_tour_edges"],  # same files they mutate in place
        file_dep=[
            OSM_DIR / "base_graph" / "interior_ele.npy",
            OSM_DIR / "hut_edges" / "records.npy", OSM_DIR / "start_edges" / "records.npy",
            OSM_DIR / "tour_edges" / "records.npy",
        ],
        # records.npy is rewritten in place (profile_offset/profile_count filled) but not listed as
        # a target - build_hub_edges/match_tour_edges already own it. profiles.npy is the only
        # file this task alone produces; downstream tile builders declare an explicit task_dep on
        # this task rather than relying on a shared target/file_dep link to wait for the in-place
        # rewrite.
        targets=[
            OSM_DIR / "hut_edges" / "profiles.npy", OSM_DIR / "start_edges" / "profiles.npy",
            OSM_DIR / "tour_edges" / "profiles.npy",
        ],
    )
