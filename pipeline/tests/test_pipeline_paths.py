import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.pipeline import TOURS_DIR  # noqa: E402


def test_tours_dir_is_pipeline_tours():
    assert TOURS_DIR.name == "tours"
    assert TOURS_DIR.parent.name == "pipeline"
    assert (TOURS_DIR / "Kaisertour").is_dir()


from lib import pipeline as p  # noqa: E402


def test_component_dirs_live_under_raw_or_build():
    assert p.RAW_DIR == p.DATA_DIR / "raw"
    assert p.BUILD_DIR == p.DATA_DIR / "build"
    assert p.RAW_OSM_DIR == p.RAW_DIR / "osm"
    assert p.RAW_DEM_DIR == p.RAW_DIR / "dem"
    for name in ("TRAILS_DIR", "HUB_RANGE_DIR", "START_POINTS_DIR", "BASE_GRAPH_DIR", "SNAPPING_DIR",
                 "ROUTE_SUBGRAPHS_DIR", "ACCESS_EDGES_DIR", "HUT_EDGES_DIR", "START_EDGES_DIR",
                 "TOUR_EDGES_DIR"):
        assert getattr(p, name).parent == p.BUILD_DIR, name
    assert p.BASE_GRAPH_DIR.name == "base-graph"
    assert p.TOUR_EDGES_DIR.name == "tour-edges"


def test_edge_layer_dirnames_match_component_dirs():
    assert p.BUILD_DIR / p.EDGE_LAYER_DIRNAMES["hut_edges"] == p.HUT_EDGES_DIR
    assert p.BUILD_DIR / p.EDGE_LAYER_DIRNAMES["start_edges"] == p.START_EDGES_DIR
    assert p.BUILD_DIR / p.EDGE_LAYER_DIRNAMES["tour_edges"] == p.TOUR_EDGES_DIR
