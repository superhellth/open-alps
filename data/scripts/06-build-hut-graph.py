"""
Builds hut-to-hut trail edges directly from data/osm/trails.osm.pbf, without ever materializing
a NetworkX/OSMnx graph object and without the buffer-clip step (06/07/08).

Why this replaces 06-08:
    OSMnx/NetworkX wraps every node/edge in Python dict-of-dicts + shapely geometry objects.
    That overhead is what didn't fit in RAM - not the raw data. 26.5M nodes as plain (lat, lon)
    float32 pairs is ~200MB; as a NetworkX graph it's many GB. Shrinking the *input area* (the
    06 buffer-radius approach) never fixed that, because Alpine huts are packed densely enough
    that any buffer big enough to matter still covers most of the region (see data/README.md).

What this does instead:
    1. Streams trails.osm.pbf once with pyosmium (C-backed, doesn't build Python objects for
       nodes/ways it discards) into flat numpy arrays: node coords + edge list with haversine
       edge weights.
    2. Builds an igraph.Graph over those arrays (C-backed, low per-node overhead).
    3. Snaps each hut to its nearest graph node via a KDTree (reject if farther than
       --max-snap-m, default 200m - direct-booking-only huts or ones far from any mapped trail
       won't have a graph node and are simply skipped, not force-matched).
    4. For each hut, runs igraph's `distances(source=[node], target=candidates, cutoff=...)`
       against only the small set of geographically-nearby candidate huts. This is the part that
       previously used scipy.sparse.csgraph.dijkstra, which - even with a cutoff - always
       allocates and returns a distance array sized to *every* node in the graph (26.5M floats)
       on every call; 1173 calls of that dominated runtime through sheer allocation/copy traffic,
       not search cost. igraph's target-limited query only computes and returns distances to the
       requested targets, so the cutoff actually bounds the work done, not just the traversal.

Output: data/osm/hut-edges.geojson - FeatureCollection of LineStrings, one per kept hut pair,
properties {from_hut_id, to_hut_id, distance_m, road_m, source: "osm"}. Each unordered pair
appears once. Geometry is the real trail polyline walked (hut -> snapped trail node -> ... ->
snapped trail node -> hut), not a straight line - see the "full path" pass below. Elevation
(ascent_m/descent_m) is a separate step, 08-add-elevation.py, since it needs a DEM
(07-fetch-dem.py) that this script has no reason to depend on.

Road bias: every edge carries both a real distance ("dist") and a routing cost ("weight") that
multiplies vehicle-oriented ways (graph.roadHighwayTags, e.g. residential/service/unclassified/
tertiary) by graph.roadPenaltyFactor. Candidate hut pairs (pass 1) are filtered by --max-edge-km
against real "dist", so the max-length guarantee is unaffected by the penalty. Path selection
(pass 2) runs Dijkstra over the penalized "weight" so it prefers trail-type ways when a
comparably-short road alternative exists; the reported distance_m is the real length of that
chosen path (which can be slightly longer than the shortest possible route), and road_m is the
portion of it that runs over a penalized way.

Pass 1 (distance-only queries) and pass 2 (full-path fetch) run their per-hut/per-edge igraph
calls across a ThreadPoolExecutor (--workers, default os.cpu_count()). This works because
igraph's C routines release the GIL during the call, so threads - not processes - get real
parallelism without the cost of pickling the graph into worker processes.

Usage:
    pip install osmium scipy numpy python-igraph   # pypi package is "osmium", not "pyosmium"
    python data/scripts/06-build-hut-graph.py
    # or override the ../pipeline.config.json defaults for one run:
    python data/scripts/06-build-hut-graph.py --max-edge-km 10 --max-snap-m 200 --workers 8

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
        is_road = w.tags.get("highway", "") in self.road_tags
        costs = dists * self.road_penalty_factor if is_road else dists
        self.edges_i.extend(idxs[:-1].tolist())
        self.edges_j.extend(idxs[1:].tolist())
        self.edges_dist.extend(dists.tolist())
        self.edges_w.extend(costs.tolist())
        self.edges_road.extend([is_road] * (len(nodes) - 1))


print(f"streaming {args.trails} ...")
handler = WayGraphHandler(config["graph"]["roadHighwayTags"], args.road_penalty_factor)
handler.apply_file(args.trails, locations=True)
n_nodes = len(handler.coords)
n_edges = len(handler.edges_i)
print(f"graph nodes: {n_nodes:,}, edges: {n_edges:,}")

coords = np.array(handler.coords, dtype=np.float64)  # (lon, lat)
i = np.array(handler.edges_i, dtype=np.int32)
j = np.array(handler.edges_j, dtype=np.int32)
dist_arr = np.array(handler.edges_dist, dtype=np.float64)
w = np.array(handler.edges_w, dtype=np.float64)
road_arr = np.array(handler.edges_road, dtype=bool)

print("building igraph graph ...")
graph = ig.Graph(
    n=n_nodes,
    edges=np.column_stack((i, j)),
    edge_attrs={"weight": w, "dist": dist_arr, "is_road": road_arr},
    directed=False,
)

print("building node KDTree for hut snapping ...")
node_tree = cKDTree(coords)

# Component membership per node, computed once. Dijkstra can't know a target is unreachable
# without exhausting the whole connected component it started in - on a graph this size that's
# an expensive way to fail. Filtering candidates to the same component first turns that into an
# O(1) lookup instead of a full traversal per unreachable pair.
print("computing connected components ...")
component_id = np.array(graph.connected_components().membership, dtype=np.int32)

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
snap_dist_deg, snap_idx = node_tree.query(hut_coords, k=1, distance_upper_bound=args.max_snap_m * deg_per_m * 1.5)

snapped_node = np.full(len(hut_ids), -1, dtype=np.int64)
for h, (dist_deg, node_idx) in enumerate(zip(snap_dist_deg, snap_idx)):
    if node_idx >= n_nodes:
        continue
    lon, lat = hut_coords[h]
    nlon, nlat = coords[node_idx]
    if haversine_m(lon, lat, nlon, nlat) <= args.max_snap_m:
        snapped_node[h] = node_idx

n_unsnapped = int((snapped_node == -1).sum())
print(f"snapped {len(hut_ids) - n_unsnapped}/{len(hut_ids)} huts to a trail node "
      f"({n_unsnapped} skipped, no trail within {args.max_snap_m:g}m)")

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
# way as pass 1.
print(f"pass 2: fetching full paths for {len(kept_pairs)} kept edges, {args.workers} worker threads ...")


def _path_for(pair):
    h, c = pair
    src = int(snapped_node[h])
    tgt = int(snapped_node[c])
    distance_m = 0.0
    road_m = 0.0
    if src == tgt:
        trail_coords = [tuple(coords[src])]
    else:
        # output="epath" (not "vpath") so the real distance/road-length reported below is summed
        # over the exact edges Dijkstra picked under the road-penalized "weight" - reconstructing
        # it from just the node sequence would be ambiguous wherever parallel edges exist between
        # the same two nodes (e.g. a path and a road running alongside each other).
        epath = graph.get_shortest_paths(src, to=tgt, weights="weight", output="epath")[0]
        vseq = [src]
        cur = src
        for eid in epath:
            e = graph.es[eid]
            nxt = e.target if e.source == cur else e.source
            vseq.append(nxt)
            distance_m += e["dist"]
            if e["is_road"]:
                road_m += e["dist"]
            cur = nxt
        trail_coords = [tuple(coords[v]) for v in vseq] if len(vseq) >= 2 else [tuple(coords[src]), tuple(coords[tgt])]

    path_coords = [tuple(hut_coords[h]), *trail_coords, tuple(hut_coords[c])]
    return {
        "type": "Feature",
        "properties": {
            "from_hut_id": hut_ids[h],
            "to_hut_id": hut_ids[c],
            "distance_m": round(distance_m, 1),
            "road_m": round(road_m, 1),
            "source": "osm",
        },
        "geometry": {
            "type": "LineString",
            "coordinates": [[float(lon), float(lat)] for lon, lat in path_coords],
        },
    }


features = []
with ThreadPoolExecutor(max_workers=args.workers) as pool:
    for idx, feature in enumerate(pool.map(_path_for, kept_pairs)):
        features.append(feature)
        if idx % 100 == 0:
            print(f"  {idx}/{len(kept_pairs)} paths fetched")

out_fc = {"type": "FeatureCollection", "features": features}
with open(args.out, "w", encoding="utf-8") as f:
    json.dump(out_fc, f)
print(f"written {args.out}")
