"""
Builds hut-to-hut trail edges directly from data/osm/trails.osm.pbf, without ever materializing
a NetworkX/OSMnx graph object and without the buffer-clip step (06/07/08).

Why this replaces 06-08:
    OSMnx/NetworkX wraps every node/edge in Python dict-of-dicts + shapely geometry objects.
    That overhead is what didn't fit in RAM - not the raw data. 26.5M nodes as plain (lat, lon)
    float32 pairs is ~200MB; as a NetworkX graph it's many GB. Shrinking the *input area* (the
    06 buffer-radius approach) never fixed that, because Alpine huts are packed densely enough
    that any buffer big enough to matter still covers most of the region (see pipeline/README.md).

What this does instead:
    1. Streams trails.osm.pbf once with pyosmium (C-backed, doesn't build Python objects for
       nodes/ways it discards) into flat numpy arrays: node coords + edge list with haversine
       edge weights.
    2. Snaps each hut to its nearest raw trail node via a KDTree (reject if farther than
       --max-snap-m, default 200m - direct-booking-only huts or ones far from any mapped trail
       won't have a graph node and are simply skipped, not force-matched).
    3. Contracts chains: the raw OSM graph has a node at every digitized vertex, so a nearly-
       straight trail segment between two junctions can be dozens of degree-2 nodes in a row -
       pure pass-through with no route choice at them. Only real decision points (junctions,
       dead ends) and hut-snap points matter for shortest-path search; every degree-2 run between
       two such "keep" nodes collapses into a single edge carrying the summed distance/weight and
       the full interior polyline + rolled-up road/SAC/via-ferrata stats, so no information is
       lost - just represented once per chain instead of once per digitized vertex. Measured
       at ~40M raw nodes / ~41M raw edges for AT+Bavaria (data/timings.jsonl); contraction is
       lossless (same shortest-path costs, since a degree-2 node has no alternative route through
       it) and expected to shrink the graph by an order of magnitude or more, since junctions and
       hut-snap points are sparse compared to digitized trail vertices.
    4. Builds an igraph.Graph over the *contracted* node/edge arrays (C-backed, low per-node
       overhead) - this is what pass 1/2 below actually search over.
    5. For each hut, runs igraph's `distances(source=[node], target=candidates, cutoff=...)`
       against only the small set of geographically-nearby candidate huts. This is the part that
       previously used scipy.sparse.csgraph.dijkstra, which - even with a cutoff - always
       allocates and returns a distance array sized to *every* node in the graph on every call;
       1173 calls of that dominated runtime through sheer allocation/copy traffic, not search
       cost. igraph's target-limited query only computes and returns distances to the requested
       targets, so the cutoff actually bounds the work done, not just the traversal.

Output: data/osm/hut-edges.geojson - FeatureCollection of LineStrings, one per kept hut pair,
properties {from_hut_id, to_hut_id, distance_m, road_m, source: "osm"}. Each unordered pair
appears once. Geometry is the real trail polyline walked (hut -> snapped trail node -> ... ->
snapped trail node -> hut), not a straight line - see the "full path" pass below, which now just
concatenates each chosen contracted edge's precomputed interior polyline instead of re-walking
raw OSM edges. Elevation (ascent_m/descent_m) is a separate step, add_elevation.py, since it
needs a DEM (fetch_dem.py) that this script has no reason to depend on.

Road bias: every edge carries both a real distance ("dist") and a routing cost ("weight") that
multiplies vehicle-oriented ways (graph.roadHighwayTags, e.g. residential/service/unclassified/
tertiary) by graph.roadPenaltyFactor. Candidate hut pairs (pass 1) are filtered by --max-edge-km
against real "dist", so the max-length guarantee is unaffected by the penalty. Path selection
(pass 2) runs Dijkstra over the penalized "weight" so it prefers trail-type ways when a
comparably-short road alternative exists; the reported distance_m is the real length of that
chosen path (which can be slightly longer than the shortest possible route), and road_m is the
portion of it that runs over a penalized way (summed per chain during contraction).

Pass 1 (distance-only queries) and pass 2 (full-path fetch) run their per-hut/per-edge igraph
calls across a ThreadPoolExecutor (--workers, default os.cpu_count()). This works because
igraph's C routines release the GIL during the call, so threads - not processes - get real
parallelism without the cost of pickling the graph into worker processes.

Usage:
    pip install osmium scipy numpy python-igraph   # pypi package is "osmium", not "pyosmium"
    python pipeline/build_hut_graph.py
    # or override the pipeline.config.json defaults for one run:
    python pipeline/build_hut_graph.py --max-edge-km 10 --max-snap-m 200 --workers 8

Requires only data/osm/trails.osm.pbf (the already-merged, unclipped file from step 3) and
data/osm/huts.geojson (step 5). No Docker, no OSMnx, no buffer/extract step needed.
"""

import argparse
import json
import math
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import igraph as ig
import numpy as np
import osmium
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.pipeline import OSM_DIR, load_config  # noqa: E402
from lib.timing import phase  # noqa: E402

SCRIPT_NAME = "build_hut_graph.py"

config = load_config()

parser = argparse.ArgumentParser()
parser.add_argument("--trails", default=str(OSM_DIR / "trails.osm.pbf"))
parser.add_argument("--huts", default=str(OSM_DIR / "huts.geojson"))
parser.add_argument("--out", default=str(OSM_DIR / "hut-edges.geojson"))
parser.add_argument("--max-edge-km", type=float, default=config["graph"]["maxEdgeKm"])
parser.add_argument("--max-snap-m", type=float, default=config["graph"]["maxSnapM"])
parser.add_argument("--road-penalty-factor", type=float, default=config["graph"]["roadPenaltyFactor"])
parser.add_argument("--workers", type=int, default=os.cpu_count(),
                     help="thread pool size for pass 1/2 (igraph C calls release the GIL)")
args = parser.parse_args()


def haversine_m(lon1, lat1, lon2, lat2):
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# Canonical OSM sac_scale values, ordered easiest -> hardest (roughly SAC T1-T6). Ranked so a
# multi-way edge can report the hardest segment walked (see rollup in _path_for below). Free-text
# typos/garbage values (there are ~30 of those in the raw data, e.g. "fixme", "T3", "2") are left
# unranked and simply don't contribute to an edge's max.
SAC_SCALE_RANK = {
    "strolling": 0,
    "hiking": 1,
    "mountain_hiking": 2,
    "demanding_mountain_hiking": 3,
    "alpine_hiking": 4,
    "demanding_alpine_hiking": 5,
    "difficult_alpine_hiking": 6,
}
SAC_SCALE_BY_RANK = {v: k for k, v in SAC_SCALE_RANK.items()}


def haversine_m_vec(lon1, lat1, lon2, lat2):
    """Same formula as haversine_m, batched over numpy arrays - used in the way() hot loop so
    each way's consecutive-node distances are one vectorized call instead of one Python-level
    math.sin/cos/asin/sqrt call per edge."""
    r = 6_371_000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlambda / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


class WayGraphHandler(osmium.SimpleHandler):
    """Streams ways, keeping only node coords/edges actually used by a hiking way."""

    def __init__(self, road_tags, road_penalty_factor):
        super().__init__()
        self.road_tags = set(road_tags)
        self.road_penalty_factor = road_penalty_factor
        self.node_id_to_idx = {}
        self.coords = []  # index -> (lon, lat)
        self.edges_i = []
        self.edges_j = []
        self.edges_dist = []  # real haversine meters
        self.edges_w = []  # routing cost: dist, penalized on road-type ways
        self.edges_road = []  # bool, one per edge - is this a penalized (road-type) way
        self.edges_sac_rank = []  # int, one per edge - SAC_SCALE_RANK value, or -1 if unrated
        self.edges_via_ferrata = []  # bool, one per edge - via_ferrata_scale tag or highway=via_ferrata
        self.way_count = 0

    def _idx_for(self, node_id, lon, lat):
        idx = self.node_id_to_idx.get(node_id)
        if idx is None:
            idx = len(self.coords)
            self.node_id_to_idx[node_id] = idx
            self.coords.append((lon, lat))
        return idx

    def way(self, w):
        self.way_count += 1
        if self.way_count % 200_000 == 0:
            print(f"  {self.way_count:,} ways streamed, {len(self.coords):,} nodes so far")
        nodes = [n for n in w.nodes if n.location.valid()]
        if len(nodes) < 2:
            return
        lons = np.empty(len(nodes))
        lats = np.empty(len(nodes))
        idxs = np.empty(len(nodes), dtype=np.int64)
        for k, n in enumerate(nodes):
            lon, lat = n.location.lon, n.location.lat
            idxs[k] = self._idx_for(n.ref, lon, lat)
            lons[k] = lon
            lats[k] = lat
        dists = haversine_m_vec(lons[:-1], lats[:-1], lons[1:], lats[1:])
        highway = w.tags.get("highway", "")
        is_road = highway in self.road_tags
        costs = dists * self.road_penalty_factor if is_road else dists
        sac_rank = SAC_SCALE_RANK.get(w.tags.get("sac_scale", ""), -1)
        is_via_ferrata = highway == "via_ferrata" or "via_ferrata_scale" in w.tags
        n_edges = len(nodes) - 1
        self.edges_i.extend(idxs[:-1].tolist())
        self.edges_j.extend(idxs[1:].tolist())
        self.edges_dist.extend(dists.tolist())
        self.edges_w.extend(costs.tolist())
        self.edges_road.extend([is_road] * n_edges)
        self.edges_sac_rank.extend([sac_rank] * n_edges)
        self.edges_via_ferrata.extend([is_via_ferrata] * n_edges)


print(f"streaming {args.trails} ...")
handler = WayGraphHandler(config["graph"]["roadHighwayTags"], args.road_penalty_factor)
with phase(SCRIPT_NAME, "stream_osm"):
    handler.apply_file(args.trails, locations=True)
n_raw_nodes = len(handler.coords)
n_raw_edges = len(handler.edges_i)
print(f"raw graph nodes: {n_raw_nodes:,}, edges: {n_raw_edges:,}")

raw_coords = np.array(handler.coords, dtype=np.float64)  # (lon, lat)
raw_i = np.array(handler.edges_i, dtype=np.int64)
raw_j = np.array(handler.edges_j, dtype=np.int64)
raw_dist = np.array(handler.edges_dist, dtype=np.float64)
raw_w = np.array(handler.edges_w, dtype=np.float64)
raw_road = np.array(handler.edges_road, dtype=bool)
raw_sac_rank = np.array(handler.edges_sac_rank, dtype=np.int8)
raw_via_ferrata = np.array(handler.edges_via_ferrata, dtype=bool)
del handler

print("building raw-node KDTree for hut snapping ...")
with phase(SCRIPT_NAME, "build_kdtree", nodes=n_raw_nodes):
    raw_node_tree = cKDTree(raw_coords)

with open(args.huts, encoding="utf-8") as f:
    huts_fc = json.load(f)

hut_ids = []
hut_coords = []
for feat in huts_fc["features"]:
    hut_ids.append(feat["properties"]["id"])
    lon, lat = feat["geometry"]["coordinates"]
    hut_coords.append((lon, lat))
hut_coords = np.array(hut_coords, dtype=np.float64)
print(f"huts: {len(hut_ids)}")

# KDTree works in raw lon/lat degrees, so convert the meter threshold to a rough degree
# threshold for the query, then verify with real haversine distance below.
deg_per_m = 1 / 111_320.0
snap_dist_deg, snap_idx = raw_node_tree.query(
    hut_coords, k=1, distance_upper_bound=args.max_snap_m * deg_per_m * 1.5
)

snapped_raw_node = np.full(len(hut_ids), -1, dtype=np.int64)
for h, (dist_deg, node_idx) in enumerate(zip(snap_dist_deg, snap_idx)):
    if node_idx >= n_raw_nodes:
        continue
    lon, lat = hut_coords[h]
    nlon, nlat = raw_coords[node_idx]
    if haversine_m(lon, lat, nlon, nlat) <= args.max_snap_m:
        snapped_raw_node[h] = node_idx

n_unsnapped = int((snapped_raw_node == -1).sum())
print(f"snapped {len(hut_ids) - n_unsnapped}/{len(hut_ids)} huts to a trail node "
      f"({n_unsnapped} skipped, no trail within {args.max_snap_m:g}m)")

# ---- Chain contraction ----
# Collapses every run of degree-2 raw nodes between two "keep" nodes (real junctions/dead-ends,
# or a hut-snap point - a hut can be a valid path endpoint mid-chain even at degree 2) into one
# edge. Lossless: a degree-2 node has exactly one way through it, so summing distance/weight
# along the chain gives the same shortest-path cost as walking the raw nodes one at a time: the
# only thing that changes is how many graph nodes/edges igraph and Dijkstra have to touch.
print("contracting degree-2 chains ...")
with phase(SCRIPT_NAME, "contract_chains", raw_nodes=n_raw_nodes, raw_edges=n_raw_edges):
    edge_ids = np.arange(n_raw_edges, dtype=np.int64)
    # CSR-style adjacency (neighbor, edge_id) per node, built via one sort over the doubled
    # (undirected) endpoint list - avoids a 40M-entry Python dict of adjacency lists.
    end_node = np.concatenate([raw_i, raw_j])
    end_other = np.concatenate([raw_j, raw_i])
    end_edge = np.concatenate([edge_ids, edge_ids])
    order = np.argsort(end_node, kind="stable")
    end_other = end_other[order]
    end_edge = end_edge[order]
    degree = np.bincount(end_node, minlength=n_raw_nodes)
    offsets = np.zeros(n_raw_nodes + 1, dtype=np.int64)
    np.cumsum(degree, out=offsets[1:])

    keep = degree != 2
    snapped_set = np.unique(snapped_raw_node[snapped_raw_node != -1])
    keep[snapped_set] = True

    def _neighbors(node):
        s, e = offsets[node], offsets[node + 1]
        return end_other[s:e].tolist(), end_edge[s:e].tolist()

    visited_edge = np.zeros(n_raw_edges, dtype=bool)
    c_u, c_v = [], []
    c_dist, c_weight, c_road_m = [], [], []
    c_sac_rank, c_via_ferrata = [], []
    c_interior = []  # interior polyline coords (excludes both endpoints), ordered u -> v

    keep_idxs = np.flatnonzero(keep)
    for count, k in enumerate(keep_idxs.tolist()):
        if count % 500_000 == 0:
            print(f"  {count:,}/{len(keep_idxs):,} keep-nodes processed")
        nbrs, edges_here = _neighbors(k)
        for nb, e in zip(nbrs, edges_here):
            if visited_edge[e]:
                continue
            visited_edge[e] = True
            d_sum = float(raw_dist[e])
            w_sum = float(raw_w[e])
            road_sum = d_sum if raw_road[e] else 0.0
            sac_max = int(raw_sac_rank[e])
            vf_any = bool(raw_via_ferrata[e])
            interior = []
            cur = nb
            prev_edge = e
            while not keep[cur]:
                interior.append((float(raw_coords[cur, 0]), float(raw_coords[cur, 1])))
                cnbrs, cedges = _neighbors(cur)
                nxt = None
                for nb2, e2 in zip(cnbrs, cedges):
                    if e2 != prev_edge:
                        nxt = (nb2, e2)
                        break
                if nxt is None:
                    break  # dead-end self-loop artifact - stop the chain here
                nb2, e2 = nxt
                visited_edge[e2] = True
                d_sum += raw_dist[e2]
                w_sum += raw_w[e2]
                if raw_road[e2]:
                    road_sum += raw_dist[e2]
                if raw_sac_rank[e2] > sac_max:
                    sac_max = int(raw_sac_rank[e2])
                if raw_via_ferrata[e2]:
                    vf_any = True
                prev_edge, cur = e2, nb2
            c_u.append(k)
            c_v.append(cur)
            c_dist.append(d_sum)
            c_weight.append(w_sum)
            c_road_m.append(road_sum)
            c_sac_rank.append(sac_max)
            c_via_ferrata.append(vf_any)
            c_interior.append(interior)

    new_index = np.full(n_raw_nodes, -1, dtype=np.int64)
    new_index[keep_idxs] = np.arange(len(keep_idxs))
    coords = raw_coords[keep_idxs]
    n_nodes = len(keep_idxs)
    edges_uv = np.column_stack((new_index[np.array(c_u)], new_index[np.array(c_v)]))
    n_edges = len(c_u)

    mask = snapped_raw_node != -1
    snapped_node = np.full(len(hut_ids), -1, dtype=np.int64)
    snapped_node[mask] = new_index[snapped_raw_node[mask]]

del raw_coords, raw_i, raw_j, raw_dist, raw_w, raw_road, raw_sac_rank, raw_via_ferrata
del end_node, end_other, end_edge, order, degree, offsets, visited_edge, snapped_raw_node

print(f"contracted {n_raw_nodes:,} raw nodes / {n_raw_edges:,} raw edges -> "
      f"{n_nodes:,} kept nodes / {n_edges:,} chain edges")

print("building igraph graph ...")
with phase(SCRIPT_NAME, "build_igraph", nodes=n_nodes, edges=n_edges):
    graph = ig.Graph(
        n=n_nodes,
        edges=edges_uv,
        edge_attrs={
            "weight": c_weight,
            "dist": c_dist,
            "road_m": c_road_m,
            "sac_rank": c_sac_rank,
            "via_ferrata": c_via_ferrata,
            "interior_coords": c_interior,
        },
        directed=False,
    )

# Component membership per node, computed once. Dijkstra can't know a target is unreachable
# without exhausting the whole connected component it started in - on a graph this size that's
# an expensive way to fail. Filtering candidates to the same component first turns that into an
# O(1) lookup instead of a full traversal per unreachable pair.
print("computing connected components ...")
with phase(SCRIPT_NAME, "connected_components"):
    component_id = np.array(graph.connected_components().membership, dtype=np.int32)

max_edge_m = args.max_edge_km * 1000
hut_tree = cKDTree(hut_coords)

# Pass 1: distance-only, target-limited queries (cheap even against the full graph - see
# module docstring). Only decides *which* pairs are edges; doesn't touch path geometry.
#
# The per-hut candidate lookup (KDTree, cheap pure-Python) stays on the main thread; only the
# expensive part - graph.distances(), a compiled igraph/C call that releases the GIL - goes to
# a thread pool. Dedup bookkeeping (seen_pairs) also stays serial so it needs no locking.
def _candidates_for(h, node):
    # candidate huts within a generous beeline radius, to avoid running dijkstra against
    # huts that can't possibly be in range even via a winding trail
    candidate_idxs = hut_tree.query_ball_point(hut_coords[h], r=args.max_edge_km * 3 * 1000 * deg_per_m)
    src_component = component_id[node]
    candidates = [
        c for c in candidate_idxs
        if c != h and snapped_node[c] != -1 and component_id[int(snapped_node[c])] == src_component
    ]
    if not candidates:
        return None
    # igraph rejects duplicate targets, and several huts can snap to the same trail node
    unique_target_nodes = sorted({int(snapped_node[c]) for c in candidates})
    return candidates, unique_target_nodes


work_items = []  # (h, node, candidates, unique_target_nodes)
for h, node in enumerate(snapped_node):
    if node == -1:
        continue
    prepared = _candidates_for(h, node)
    if prepared is None:
        continue
    candidates, unique_target_nodes = prepared
    work_items.append((h, int(node), candidates, unique_target_nodes))

print(f"pass 1: {len(work_items)} huts to query, {args.workers} worker threads ...")


def _distances_for(item):
    _, node, _, unique_target_nodes = item
    # target-limited query: only computes/returns distances to these specific nodes, unlike
    # scipy's dijkstra(..., limit=) which still allocates a full n_nodes-length array per call
    # weights="dist" (real distance, not the road-penalized "weight") so max-edge-km stays a
    # guarantee about actual trail length, unaffected by the road penalty applied in pass 2.
    return graph.distances(source=[node], target=unique_target_nodes, weights="dist")[0]


kept_pairs = []  # (h, c)
seen_pairs = set()
with phase(SCRIPT_NAME, "pass1_distances", huts=len(work_items)):
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for done, (item, dists) in enumerate(zip(work_items, pool.map(_distances_for, work_items))):
            h, _, candidates, unique_target_nodes = item
            dists_by_node = dict(zip(unique_target_nodes, dists))
            for c in candidates:
                d = dists_by_node[int(snapped_node[c])]
                pair = tuple(sorted((h, c)))
                if pair in seen_pairs:
                    continue
                if not np.isfinite(d) or d > max_edge_m:
                    continue
                seen_pairs.add(pair)
                kept_pairs.append((h, c))

            if done % 100 == 0:
                print(f"  {done}/{len(work_items)} huts processed, {len(kept_pairs)} edges so far")

print(f"total edges: {len(kept_pairs)}")

# Pass 2: for kept pairs only (far fewer than the candidates checked above), fetch the actual
# vertex path walked so the output geometry is the real trail, not a straight line. igraph has
# no batched multi-target path query (unlike distances()), so this is one call per edge - but
# get_shortest_paths is also a compiled call that releases the GIL, so it parallelizes the same
# way as pass 1. Each hop in the returned path is now a *contracted* chain edge, so distance_m/
# road_m/sac_scale/via_ferrata and the interior polyline are just read off the edge attrs computed
# during contraction, not re-derived by walking raw OSM edges one at a time.
print(f"pass 2: fetching full paths for {len(kept_pairs)} kept edges, {args.workers} worker threads ...")


def _path_for(pair):
    h, c = pair
    src = int(snapped_node[h])
    tgt = int(snapped_node[c])
    distance_m = 0.0
    road_m = 0.0
    max_sac_rank = -1  # -1 = no rated segment on this edge
    has_via_ferrata = False
    if src == tgt:
        trail_coords = [tuple(coords[src])]
    else:
        # output="epath" (not "vpath") so the real distance/road-length reported below is summed
        # over the exact edges Dijkstra picked under the road-penalized "weight" - reconstructing
        # it from just the node sequence would be ambiguous wherever parallel edges exist between
        # the same two nodes (e.g. a path and a road running alongside each other).
        epath = graph.get_shortest_paths(src, to=tgt, weights="weight", output="epath")[0]
        trail_coords = []
        cur = src
        for eid in epath:
            e = graph.es[eid]
            forward = e.source == cur
            nxt = e.target if forward else e.source
            interior = e["interior_coords"] if forward else list(reversed(e["interior_coords"]))
            trail_coords.append(tuple(coords[cur]))
            trail_coords.extend(interior)
            distance_m += e["dist"]
            road_m += e["road_m"]
            # An edge's overall grade is the hardest segment walked along it, same logic as
            # road_m - one demanding stretch makes the whole hut-to-hut route that grade,
            # regardless of how easy the rest is.
            if e["sac_rank"] > max_sac_rank:
                max_sac_rank = e["sac_rank"]
            if e["via_ferrata"]:
                has_via_ferrata = True
            cur = nxt
        trail_coords.append(tuple(coords[cur]))
        if len(trail_coords) < 2:
            trail_coords = [tuple(coords[src]), tuple(coords[tgt])]

    path_coords = [tuple(hut_coords[h]), *trail_coords, tuple(hut_coords[c])]
    return {
        "type": "Feature",
        "properties": {
            "from_hut_id": hut_ids[h],
            "to_hut_id": hut_ids[c],
            "distance_m": round(distance_m, 1),
            "road_m": round(road_m, 1),
            "sac_scale": SAC_SCALE_BY_RANK.get(max_sac_rank),
            "via_ferrata": has_via_ferrata,
            "source": "osm",
        },
        "geometry": {
            "type": "LineString",
            "coordinates": [[float(lon), float(lat)] for lon, lat in path_coords],
        },
    }


features = []
with phase(SCRIPT_NAME, "pass2_paths", edges=len(kept_pairs)):
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for idx, feature in enumerate(pool.map(_path_for, kept_pairs)):
            features.append(feature)
            if idx % 100 == 0:
                print(f"  {idx}/{len(kept_pairs)} paths fetched")

out_fc = {"type": "FeatureCollection", "features": features}
with open(args.out, "w", encoding="utf-8") as f:
    json.dump(out_fc, f)
print(f"written {args.out}")
