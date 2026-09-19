import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import restructure_data_dir as rdd  # noqa: E402


def _touch(path: Path, content: bytes = b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _make_old_tree(data: Path):
    _touch(data / "osm" / "raw" / "austria-latest.osm.pbf", b"pbf")
    _touch(data / "osm" / "huts.geojson", b"huts")
    _touch(data / "osm" / "base_graph" / "node_ele.npy", b"ele")
    _touch(data / "osm" / "hut_edges" / "edge_ids.npy", b"ids")
    _touch(data / "osm" / "hut-edge-stats.json", b"stats")
    _touch(data / "osm" / "hut-edges.pmtiles", b"tiles")
    _touch(data / "osm" / "route_subgraphs" / "manifest.json", b"m")
    _touch(data / "osm" / "route_subgraphs" / "cell_1" / "local_node_ele.npy", b"l")
    _touch(data / "osm" / "austria-parking.osm.pbf", b"orphan")
    _touch(data / "osm" / "tour_edges" / "tour_meta.npy", b"orphan")
    _touch(data / "dem" / "dem.tif", b"dem")
    _touch(data / "dem" / "raw" / "tile.tif", b"tile")


def _make_db(path: Path):
    def entry(*keys):
        d = {k: [1.0, 2, "md5-" + k] for k in keys}
        d["deps:"] = list(keys)
        d["_values_:"] = {"opt": 1}
        d["result:"] = "r"
        d["checker:"] = "md5"
        return d

    db = {
        "sample_base_elevation": entry("../data/osm/base_graph/node_ele.npy", "../data/dem/dem.tif"),
        "build_hut_edge_tiles": entry("../data/osm/hut_edges/edge_ids.npy", "tours/Kaisertour/1.gpx"),
        "build_tour_edge_payload": entry("../data/osm/tour-edge-payload.bin"),
    }
    path.write_text(json.dumps(db), encoding="utf-8")
    return db


def test_map_path_renames_and_regroups():
    assert rdd.map_path("osm/base_graph/node_ele.npy") == "build/base-graph/node-ele.npy"
    assert rdd.map_path("osm/hut_edges/edge_ids.npy") == "build/hut-edges/edge-ids.npy"
    assert rdd.map_path("osm/hut-edges.pmtiles") == "build/hut-edges/edges.pmtiles"
    assert rdd.map_path("osm/hut-edge-stats.json") == "build/hut-edges/stats.json"
    assert rdd.map_path("osm/unsnapped_huts.json") == "build/snapping/unsnapped-huts.json"
    assert rdd.map_path("osm/verify_trails.stamp") == "build/trails/verify-trails.stamp"
    assert rdd.map_path("osm/approaches.bin") == "build/start-edges/approaches.bin"
    assert rdd.map_path("osm/tours.json") == "build/tour-edges/tours.json"
    assert rdd.map_path("osm/hubs.json") == "build/tour-edges/hubs.json"
    assert rdd.map_path("osm/raw/bayern.poly") == "raw/osm/bayern.poly"
    assert rdd.map_path("osm/huts.geojson") == "raw/huts.geojson"
    assert rdd.map_path("dem/raw/tile.tif") == "raw/dem/raw/tile.tif"
    assert rdd.map_path("osm/route_subgraphs/cell_1/x.npy") == "build/route-subgraphs/cell_1/x.npy"
    assert rdd.map_path("osm/never-heard-of-it.bin") is None


def test_run_moves_files_deletes_orphans_and_rewrites_db(tmp_path):
    data = tmp_path / "data"
    _make_old_tree(data)
    db_path = data / ".doit.json.db"
    old_db = _make_db(db_path)

    rdd.run(data, db_path)

    assert (data / "raw" / "osm" / "austria-latest.osm.pbf").read_bytes() == b"pbf"
    assert (data / "raw" / "huts.geojson").read_bytes() == b"huts"
    assert (data / "build" / "base-graph" / "node-ele.npy").read_bytes() == b"ele"
    assert (data / "build" / "hut-edges" / "edge-ids.npy").read_bytes() == b"ids"
    assert (data / "build" / "hut-edges" / "stats.json").read_bytes() == b"stats"
    assert (data / "build" / "hut-edges" / "edges.pmtiles").read_bytes() == b"tiles"
    assert (data / "build" / "route-subgraphs" / "cell_1" / "local_node_ele.npy").read_bytes() == b"l"
    assert (data / "raw" / "dem" / "raw" / "tile.tif").read_bytes() == b"tile"
    assert not (data / "osm").exists()
    assert not (data / "dem").exists()

    new_db = json.loads(db_path.read_text(encoding="utf-8"))
    entry = new_db["sample_base_elevation"]
    assert entry["../data/build/base-graph/node-ele.npy"] == old_db["sample_base_elevation"]["../data/osm/base_graph/node_ele.npy"]
    assert entry["../data/raw/dem/dem.tif"] == old_db["sample_base_elevation"]["../data/dem/dem.tif"]
    assert entry["deps:"] == ["../data/build/base-graph/node-ele.npy", "../data/raw/dem/dem.tif"]
    assert entry["_values_:"] == {"opt": 1}
    assert entry["result:"] == "r" and entry["checker:"] == "md5"
    # keys outside data/ are untouched
    assert "tours/Kaisertour/1.gpx" in new_db["build_hut_edge_tiles"]
    # tasks that no longer exist in dodo.py are dropped
    assert "build_tour_edge_payload" not in new_db
    assert (data / ".doit.json.db.pre-restructure").exists()


def test_second_run_is_a_noop(tmp_path):
    data = tmp_path / "data"
    _make_old_tree(data)
    db_path = data / ".doit.json.db"
    _make_db(db_path)
    rdd.run(data, db_path)
    first = db_path.read_text(encoding="utf-8")
    backup = (data / ".doit.json.db.pre-restructure").read_text(encoding="utf-8")

    rdd.run(data, db_path)

    assert db_path.read_text(encoding="utf-8") == first
    assert (data / ".doit.json.db.pre-restructure").read_text(encoding="utf-8") == backup


def test_dry_run_changes_nothing(tmp_path):
    data = tmp_path / "data"
    _make_old_tree(data)
    db_path = data / ".doit.json.db"
    _make_db(db_path)
    before = db_path.read_text(encoding="utf-8")

    rdd.run(data, db_path, dry_run=True)

    assert (data / "osm" / "huts.geojson").exists()
    assert not (data / "raw").exists()
    assert db_path.read_text(encoding="utf-8") == before
    assert not (data / ".doit.json.db.pre-restructure").exists()


def test_unmapped_db_key_aborts_before_any_move(tmp_path):
    data = tmp_path / "data"
    _make_old_tree(data)
    db_path = data / ".doit.json.db"
    db_path.write_text(json.dumps({"t": {"../data/osm/mystery.bin": [1.0, 2, "m"], "deps:": []}}),
                       encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        rdd.run(data, db_path)

    assert "mystery.bin" in str(exc.value)
    assert (data / "osm" / "huts.geojson").exists()
    assert not (data / "raw").exists()


def test_unmapped_file_on_disk_aborts_before_any_move(tmp_path):
    data = tmp_path / "data"
    _make_old_tree(data)
    _touch(data / "osm" / "stray.tmp")
    db_path = data / ".doit.json.db"
    _make_db(db_path)

    with pytest.raises(SystemExit) as exc:
        rdd.run(data, db_path)

    assert "stray.tmp" in str(exc.value)
    assert (data / "osm" / "huts.geojson").exists()


def test_destination_collision_aborts(tmp_path):
    data = tmp_path / "data"
    _make_old_tree(data)
    _touch(data / "raw" / "huts.geojson", b"other")
    db_path = data / ".doit.json.db"
    _make_db(db_path)

    with pytest.raises(SystemExit) as exc:
        rdd.run(data, db_path)

    assert "huts.geojson" in str(exc.value)
    assert (data / "osm" / "huts.geojson").read_bytes() == b"huts"


def test_every_destination_is_unique_and_under_raw_or_build():
    dests = list(rdd.EXACT_MOVES.values())
    assert len(dests) == len(set(dests))
    assert all(d.startswith(("raw/", "build/")) for d in dests)
    assert not set(rdd.DELETE) & set(rdd.EXACT_MOVES)
