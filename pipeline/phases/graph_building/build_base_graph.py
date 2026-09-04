#!/usr/bin/env python3
"""Streams trails.osm.pbf once and contracts it structurally (lib/contraction.py) into the
persisted mmap base graph (lib/binfmt.py), partitioned by lib/grid.py's cell grid. Depends only
on trails.osm.pbf - not on any hub set (huts/stations/parking) - so it's cached across hub-set
changes and downstream hyperparameter retuning; build_hub_edges.py (which does depend on hub
sets) loads this output instead of re-streaming/re-contracting every run. See
docs/superpowers/specs/2026-08-19-pipeline-v2-design.md.

Usage: python pipeline/phases/graph_building/build_base_graph.py [--tile-size-km 60]
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import osmium

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib import binfmt, grading  # noqa: E402
from lib.contraction import contract_structural  # noqa: E402
from lib.geo import haversine_m_vec_pairs as haversine_m_vec  # noqa: E402
from lib.grid import Grid  # noqa: E402
from lib.memtrace import rss_sampler  # noqa: E402
from lib.pipeline import OSM_DIR, load_config  # noqa: E402
from lib.timing import StepTimer, phase  # noqa: E402

SCRIPT_NAME = "build_base_graph.py"

config = load_config()


class WayGraphHandler(osmium.SimpleHandler):
    """Identical streaming shape to build_hut_graph.py's old handler - kept unchanged since
    nothing about hub sets affects how raw ways are turned into raw node/edge arrays."""

    def __init__(self, road_tags, progress_every=100_000):
        super().__init__()
        self.road_tags = set(road_tags)
        self.node_id_to_idx = {}
        self.coords = []
        self.edges_i, self.edges_j = [], []
        self.edges_dist = []
        self.edges_road, self.edges_ungraded, self.edges_inferred = [], [], []
        self.edges_sac_rank, self.edges_via_ferrata, self.edges_constrained_ok = [], [], []
        self.progress_every = progress_every
        self.n_ways = 0

    def _idx_for(self, node_id, lon, lat):
        idx = self.node_id_to_idx.get(node_id)
        if idx is None:
            idx = len(self.coords)
            self.node_id_to_idx[node_id] = idx
            self.coords.append((lon, lat))
        return idx

    def way(self, w):
        tags = dict(w.tags)
        if grading.is_impassable(tags):
            return
        nodes = [n for n in w.nodes if n.location.valid()]
        if len(nodes) < 2:
            return
        lons = np.empty(len(nodes))
        lats = np.empty(len(nodes))
        idxs = np.empty(len(nodes), dtype=np.int64)
        for k, n in enumerate(nodes):
            lon, lat = n.location.lon, n.location.lat
            idxs[k] = self._idx_for(n.ref, lon, lat)
            lons[k], lats[k] = lon, lat
        dists = haversine_m_vec(lons[:-1], lats[:-1], lons[1:], lats[1:])
        highway = tags.get("highway", "")
        is_road = highway in self.road_tags
        grade = grading.classify_way(tags)
        is_via_ferrata = highway == "via_ferrata" or "via_ferrata_scale" in tags
        constrained_ok = (
            grade.tier != grading.TIER_UNGRADED
            and not is_via_ferrata
            and not grading.excluded_from_constrained(tags)
        )
        n_edges = len(nodes) - 1
        zeros = [0.0] * n_edges
        ungraded = dists.tolist() if grade.tier == grading.TIER_UNGRADED else zeros
        inferred = dists.tolist() if grade.tier == grading.TIER_INFERRED else zeros
        self.edges_i.extend(idxs[:-1].tolist())
        self.edges_j.extend(idxs[1:].tolist())
        self.edges_dist.extend(dists.tolist())
        self.edges_road.extend([is_road] * n_edges)
        self.edges_ungraded.extend(ungraded)
        self.edges_inferred.extend(inferred)
        self.edges_sac_rank.extend([grade.sac_rank] * n_edges)
        self.edges_via_ferrata.extend([is_via_ferrata] * n_edges)
        self.edges_constrained_ok.extend([constrained_ok] * n_edges)

        self.n_ways += 1
        if self.progress_every and self.n_ways % self.progress_every == 0:
            print(f"  stream_osm: {self.n_ways:,} ways -> {len(self.coords):,} nodes, "
                  f"{len(self.edges_i):,} edges so far", flush=True)


def stream_osm(trails_path, config):
    print(f"streaming {trails_path} ...", flush=True)
    handler = WayGraphHandler(config["graph"]["roadHighwayTags"])
    with phase(SCRIPT_NAME, "stream_osm") as meta:
        with rss_sampler() as sample:
            handler.apply_file(trails_path, locations=True)
        meta.update(sample.as_meta())  # outside rss_sampler: its finally fills the peak
    print(f"raw graph nodes: {len(handler.coords):,}, edges: {len(handler.edges_i):,}", flush=True)
    return handler


def handler_to_arrays(handler, timer: StepTimer = None):
    """The ten numpy arrays contract_structural takes, in order. Split out from contract() so
    main() can drop the handler - and with it ~12 GB of now-dead raw Python lists (40M coord
    tuples, 41M-element int/float lists) - BEFORE contraction starts rather than after. See
    docs/superpowers/plans/2026-08-20-contraction-measurement-spike.md."""
    timer = timer if timer is not None else StepTimer()
    with timer.step("handler_to_arrays"):
        return (
            np.array(handler.coords, dtype=np.float64),
            np.array(handler.edges_i, dtype=np.int64),
            np.array(handler.edges_j, dtype=np.int64),
            np.array(handler.edges_dist, dtype=np.float64),
            np.array(handler.edges_road, dtype=bool),
            np.array(handler.edges_ungraded, dtype=np.float64),
            np.array(handler.edges_inferred, dtype=np.float64),
            np.array(handler.edges_sac_rank, dtype=np.int8),
            np.array(handler.edges_via_ferrata, dtype=bool),
            np.array(handler.edges_constrained_ok, dtype=bool),
        )


def contract(*raw_args, progress_every: int = 20_000):
    with phase(SCRIPT_NAME, "contract_structural") as meta:
        with rss_sampler() as sample:
            contracted = contract_structural(*raw_args, progress_every=progress_every)
        meta.update(sample.as_meta())  # outside rss_sampler: its finally fills the peak
        meta["n_isolated_cycles"] = contracted.n_isolated_cycles
    print(f"contracted to {len(contracted.coords):,} nodes / "
          f"{len(contracted.edges_u):,} edges", flush=True)
    return contracted


def pack_and_write(contracted, bbox, tile_size_km, out_dir, timer: StepTimer = None):
    timer = timer if timer is not None else StepTimer()
    # --- assign cell ids, re-sort nodes by cell so cell_index.npy addresses a contiguous slice ---
    # Steps below never nest, so StepTimer.summary()'s percentages stay a real split of the run.
    with timer.step("pack_nodes"):
        grid = Grid(bbox, tile_size_km)
        cell_ids = grid.cell_ids_for_points(contracted.coords[:, 0], contracted.coords[:, 1])
        sort_order, cell_index = binfmt.build_csr_index(cell_ids, n_groups=len(grid.all_cell_ids()))

        old_to_new = np.empty(len(contracted.coords), dtype=np.int64)
        old_to_new[sort_order] = np.arange(len(sort_order))

        nodes_arr = np.zeros(len(contracted.coords), dtype=binfmt.NODE_DTYPE)
        nodes_arr["lon"] = contracted.coords[sort_order, 0]
        nodes_arr["lat"] = contracted.coords[sort_order, 1]
        nodes_arr["cell_id"] = cell_ids[sort_order]

    # --- remap edge endpoints through the node reorder, pack interior polylines ---
    n_edges = len(contracted.edges_u)
    interior_offsets = np.zeros(n_edges, dtype=np.int64)
    interior_counts = np.zeros(n_edges, dtype=np.int32)
    flat_interior = []
    cursor = 0
    # The one remaining Python-level loop in this script after contraction - over every contracted
    # edge's interior polyline, so it scales with raw (uncontracted) vertex count, not edge count.
    with timer.step("pack_interior"):
        for i, pts in enumerate(contracted.interior_coords):
            interior_offsets[i] = cursor
            interior_counts[i] = len(pts)
            flat_interior.extend(pts)
            cursor += len(pts)

        interior_arr = np.zeros(len(flat_interior), dtype=binfmt.COORD_DTYPE)
        if flat_interior:
            interior_arr["lon"] = [p[0] for p in flat_interior]
            interior_arr["lat"] = [p[1] for p in flat_interior]

    with timer.step("pack_edges"):
        edges_arr = np.zeros(n_edges, dtype=binfmt.EDGE_DTYPE)
        edges_arr["u"] = old_to_new[contracted.edges_u]
        edges_arr["v"] = old_to_new[contracted.edges_v]
        edges_arr["dist"] = contracted.edges_dist
        edges_arr["road_m"] = contracted.edges_road_m
        edges_arr["ungraded_m"] = contracted.edges_ungraded_m
        edges_arr["inferred_m"] = contracted.edges_inferred_m
        edges_arr["time_s"] = binfmt.UNSET
        edges_arr["ascent_m"] = binfmt.UNSET
        edges_arr["descent_m"] = binfmt.UNSET
        edges_arr["sac_rank"] = contracted.edges_sac_rank
        edges_arr["via_ferrata"] = contracted.edges_via_ferrata
        edges_arr["constrained_ok"] = contracted.edges_constrained_ok
        edges_arr["interior_offset"] = interior_offsets
        edges_arr["interior_count"] = interior_counts
        edges_arr["edge_id"] = np.arange(n_edges, dtype=np.int64)  # stable: row position == edge_id

        # --- node -> incident edge ids CSR (built on FINAL node ids, after the cell-sort remap) ---
        doubled_nodes = np.concatenate([edges_arr["u"], edges_arr["v"]])
        doubled_edge_ids = np.concatenate([edges_arr["edge_id"], edges_arr["edge_id"]])
        ne_order, node_edge_index = binfmt.build_csr_index(doubled_nodes, n_groups=len(nodes_arr))
        node_edge_ids = doubled_edge_ids[ne_order]

    out_dir = Path(out_dir)
    with timer.step("write_arrays"):
        # edges_arr's time_s/ascent_m/descent_m are binfmt.UNSET above, so any edge_profiles.stamp
        # from a previous base graph is about to become a lie - and that stamp is the only thing
        # dodo's compute_edge_profiles keys "already done" off (dag/elevation.py's targets; it
        # can't take edges.npy as a file_dep, since it rewrites that file in place). Dropped BEFORE
        # edges.npy is written, so a crash mid-write still leaves the stamp gone rather than
        # vouching for sentinel weights.
        (out_dir / "edge_profiles.stamp").unlink(missing_ok=True)
        binfmt.save_array(out_dir / "nodes.npy", nodes_arr)
        binfmt.save_array(out_dir / "cell_index.npy", cell_index)
        binfmt.save_array(out_dir / "node_edge_index.npy", node_edge_index)
        binfmt.save_array(out_dir / "node_edge_ids.npy", node_edge_ids)
        binfmt.save_array(out_dir / "edges.npy", edges_arr)
        binfmt.save_array(out_dir / "interior.npy", interior_arr)
    binfmt.save_manifest(out_dir / "manifest.json", {
        "bbox": bbox,
        "tile_size_km": tile_size_km,
        "n_cols": grid.n_cols,
        "n_rows": grid.n_rows,
        "n_nodes": len(nodes_arr),
        "n_edges": n_edges,
    })
    print(f"written {out_dir}", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--trails", default=str(OSM_DIR / "trails.osm.pbf"),
                        help="merged trails.osm.pbf to stream and contract into the base graph")
    parser.add_argument("--out-dir", default=str(OSM_DIR / "base_graph"),
                        help="directory to write the persisted base graph arrays into")
    parser.add_argument("--tile-size-km", type=float, default=config["graph"]["tileSizeKm"],
                        help="grid cell size (km) each node is assigned to, for later per-cell lookup by build_hub_edges.py (see pipeline.config.json's graph.tileSizeKm)")
    args = parser.parse_args(argv)

    # stream_osm and contract keep their own phase() records (with rss_sampler meta) - they are
    # the long-running historical series in data/timings.jsonl. The StepTimer adds the parts
    # between them, which nothing measured before: turning the handler's Python lists into numpy
    # arrays, and packing/writing the output arrays.
    timer = StepTimer()
    with phase(SCRIPT_NAME, "build_base_graph", tile_size_km=args.tile_size_km) as meta:
        with timer.step("stream_osm"):
            handler = stream_osm(args.trails, config)
        raw_args = handler_to_arrays(handler, timer=timer)
        del handler  # ~12 GB of raw Python lists, dead once copied into the arrays above
        with timer.step("contract"):
            contracted = contract(*raw_args)
        del raw_args
        pack_and_write(contracted, config["bbox"], args.tile_size_km, args.out_dir,
                       timer=timer)
        meta.update(timer.as_meta())
    print(f"step totals: {timer.summary()}", flush=True)


if __name__ == "__main__":
    main()
