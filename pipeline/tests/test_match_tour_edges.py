import json
import sys
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from lib import binfmt  # noqa: E402
from graph_building import match_tour_edges as mte  # noqa: E402


def _flat_dem(tmp_path, elevation=1500.0, size=20, origin=(10.5, 47.5), pixel_deg=0.01):
    path = tmp_path / "dem.tif"
    data = np.full((size, size), elevation, dtype=np.float32)
    transform = from_origin(origin[0], origin[1], pixel_deg, pixel_deg)
    with rasterio.open(
        path, "w", driver="GTiff", height=size, width=size, count=1, dtype="float32",
        crs="EPSG:4326", transform=transform,
    ) as dst:
        dst.write(data, 1)
    return path


def _sloped_dem(tmp_path, size=20, origin=(10.5, 47.5), pixel_deg=0.01):
    # elevation rises by 10m per row going south, so a leg walking south gains elevation.
    path = tmp_path / "dem.tif"
    data = np.fromfunction(lambda r, c: 1000.0 + r * 10.0, (size, size), dtype=np.float64).astype(np.float32)
    transform = from_origin(origin[0], origin[1], pixel_deg, pixel_deg)
    with rasterio.open(
        path, "w", driver="GTiff", height=size, width=size, count=1, dtype="float32",
        crs="EPSG:4326", transform=transform,
    ) as dst:
        dst.write(data, 1)
    return path


_SPEED_MODEL = {"v0": 4.013, "k": 3.5, "s0": 0.05}


def test_match_leg_computes_distance_from_raw_trace():
    points = [(11.0, 47.0), (11.0, 47.001), (11.0, 47.002)]
    result = mte.match_leg(
        points, dem_path=None, kernel_m=0, min_slope_segment_m=30, speed_model=_SPEED_MODEL,
        min_speed_ms=0.15, profile_points=5, elevations=np.array([1000.0, 1000.0, 1000.0]),
    )
    # ~0.002deg latitude ~= 222m
    assert result["distance_m"] == pytest.approx(222.4, abs=1.0)


def test_match_leg_ascent_descent_from_flat_profile_is_zero():
    points = [(11.0, 47.0), (11.0, 47.001), (11.0, 47.002)]
    result = mte.match_leg(
        points, dem_path=None, kernel_m=0, min_slope_segment_m=30, speed_model=_SPEED_MODEL,
        min_speed_ms=0.15, profile_points=5, elevations=np.array([1000.0, 1000.0, 1000.0]),
    )
    assert result["ascent_m"] == pytest.approx(0.0)
    assert result["descent_m"] == pytest.approx(0.0)


def test_match_leg_ascent_from_rising_profile():
    points = [(11.0, 47.0), (11.0, 47.001), (11.0, 47.002)]
    result = mte.match_leg(
        points, dem_path=None, kernel_m=0, min_slope_segment_m=30, speed_model=_SPEED_MODEL,
        min_speed_ms=0.15, profile_points=5, elevations=np.array([1000.0, 1020.0, 1050.0]),
    )
    assert result["ascent_m"] == pytest.approx(50.0)
    assert result["descent_m"] == pytest.approx(0.0)
    assert result["max_ele_m"] == pytest.approx(1050.0)


def test_match_leg_duration_is_clamped_by_min_speed_ms():
    points = [(11.0, 47.0), (11.0, 47.5)]  # very long leg
    result = mte.match_leg(
        points, dem_path=None, kernel_m=0, min_slope_segment_m=30, speed_model=_SPEED_MODEL,
        min_speed_ms=1000.0,  # absurdly fast floor
        profile_points=5, elevations=np.array([1000.0, 1000.0]),
    )
    assert result["duration_s"] == pytest.approx(result["distance_m"] / 1000.0, rel=1e-3)


def test_match_leg_profile_has_requested_point_count():
    points = [(11.0, 47.0), (11.0, 47.001), (11.0, 47.002)]
    result = mte.match_leg(
        points, dem_path=None, kernel_m=0, min_slope_segment_m=30, speed_model=_SPEED_MODEL,
        min_speed_ms=0.15, profile_points=7, elevations=np.array([1000.0, 1010.0, 1020.0]),
    )
    assert len(result["profile"]) == 7


def _hut(id_, lon, lat):
    return {"id": id_, "type": binfmt.TYPE_HUT, "lon": lon, "lat": lat, "name": f"hut{id_}"}


def _station(id_, lon, lat):
    return {"id": id_, "type": binfmt.TYPE_STATION, "lon": lon, "lat": lat, "name": ""}


def test_resolve_endpoint_requires_hut_for_interior_endpoints():
    hubs = [_station(1, 11.0, 47.0), _hut(2, 11.0, 47.0)]
    huts_only = [h for h in hubs if h["type"] == binfmt.TYPE_HUT]
    chosen, _, _ = mte._resolve_endpoint(hubs, huts_only, (11.0, 47.0), max_snap_m=50.0, require_hut=True)
    assert chosen["type"] == binfmt.TYPE_HUT


def test_resolve_endpoint_allows_any_type_when_not_required():
    hubs = [_station(1, 11.0, 47.0)]
    huts_only = []
    chosen, _, _ = mte._resolve_endpoint(hubs, huts_only, (11.0, 47.0), max_snap_m=50.0, require_hut=False)
    assert chosen["type"] == binfmt.TYPE_STATION


def test_resolve_endpoint_rejects_non_hut_when_hut_required_even_if_in_range():
    hubs = [_station(1, 11.0, 47.0)]
    huts_only = []
    chosen, nearest, dist = mte._resolve_endpoint(
        hubs, huts_only, (11.0, 47.0), max_snap_m=50.0, require_hut=True,
    )
    assert chosen is None
    assert nearest is None  # huts_only is empty, so no candidate to report as "nearest miss" either


def _write_tour_folder(base_dir: Path, name: str, legs: dict) -> Path:
    """legs: {leg_number: [(lon, lat), ...]}"""
    folder = base_dir / name
    folder.mkdir(parents=True)
    ns = "http://www.topografix.com/GPX/1/1"
    for n, points in legs.items():
        trkpts = "".join(f'<trkpt lat="{lat}" lon="{lon}"></trkpt>' for lon, lat in points)
        gpx = (
            f'<?xml version="1.0"?><gpx xmlns="{ns}"><trk><trkseg>{trkpts}'
            "</trkseg></trk></gpx>"
        )
        (folder / f"{n}.gpx").write_text(gpx, encoding="utf-8")
    return folder


def test_main_writes_records_geometry_profiles_tours_and_gaps(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    raw.mkdir()
    sp = tmp_path / "start-points"
    sp.mkdir()
    out = tmp_path / "tour-edges"
    tours_dir = tmp_path / "tours"

    huts = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"name": "Start Hut"}, "geometry": {"type": "Point", "coordinates": [11.0, 47.0]}},
            {"type": "Feature", "properties": {"name": "Mid Hut"}, "geometry": {"type": "Point", "coordinates": [11.0, 47.01]}},
            {"type": "Feature", "properties": {"name": "End Hut"}, "geometry": {"type": "Point", "coordinates": [11.0, 47.02]}},
        ],
    }
    (raw / "huts.geojson").write_text(json.dumps(huts), encoding="utf-8")
    binfmt.save_array(sp / "start-points.npy", np.zeros(0, dtype=np.dtype(
        [("osm_id", "i8"), ("type", "u1"), ("lon", "f8"), ("lat", "f8")]
    )))

    _write_tour_folder(tours_dir, "OneTour", {
        1: [(11.0, 47.0), (11.0, 47.005), (11.0, 47.01)],
        2: [(11.0, 47.01), (11.0, 47.015), (11.0, 47.02)],
    })

    # covers the tour's own points (lon ~11.0, lat 47.0-47.02) with margin: each leg samples a DEM
    # window around its own trace.
    dem_path = _flat_dem(tmp_path, elevation=1500.0, origin=(10.9, 47.1), size=300, pixel_deg=0.001)

    import lib.pipeline as pipeline_lib
    monkeypatch.setattr(pipeline_lib, "TOURS_DIR", tours_dir)
    monkeypatch.setattr(mte, "TOURS_DIR", tours_dir)

    mte.main([
        "--dem", str(dem_path), "--huts", str(raw / "huts.geojson"),
        "--start-points", str(sp / "start-points.npy"), "--out-dir", str(out), "--max-snap-m", "100",
        "--smoothing-kernel-m", "0", "--min-slope-segment-m", "10", "--profile-points", "5",
        "--speed-v0", "4.013", "--speed-k", "3.5", "--speed-s0", "0.05", "--min-speed-ms", "0.15",
    ])

    records = binfmt.load_array(out / "records.npy", mmap=False)
    geometry = binfmt.load_array(out / "geometry.npy", mmap=False)
    profiles = binfmt.load_array(out / "profiles.npy", mmap=False)
    assert len(records) == 2
    assert records[0]["from_type"] == binfmt.TYPE_HUT
    assert records[0]["to_type"] == binfmt.TYPE_HUT
    assert records[0]["distance_m"] > 0
    assert len(geometry) == sum(int(r["geom_count"]) for r in records)
    assert len(profiles) == sum(int(r["profile_count"]) for r in records)

    with open(out / "tours.json", encoding="utf-8") as f:
        tours = json.load(f)
    assert tours[0]["numDays"] == 2
    assert len(tours[0]["legs"]) == 2
    assert tours[0]["legs"][0]["from"]["type"] == "hut"
    assert "distanceM" in tours[0]["legs"][0]

    with open(out / "tour-match-gaps.json", encoding="utf-8") as f:
        gaps = json.load(f)
    assert gaps == []


def test_main_records_a_gap_for_an_unresolvable_interior_endpoint(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    raw.mkdir()
    sp = tmp_path / "start-points"
    sp.mkdir()
    out = tmp_path / "tour-edges"
    tours_dir = tmp_path / "tours"

    huts = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"name": "Start Hut"}, "geometry": {"type": "Point", "coordinates": [11.0, 47.0]}},
            {"type": "Feature", "properties": {"name": "End Hut"}, "geometry": {"type": "Point", "coordinates": [11.0, 47.02]}},
        ],
    }
    (raw / "huts.geojson").write_text(json.dumps(huts), encoding="utf-8")
    binfmt.save_array(sp / "start-points.npy", np.zeros(0, dtype=np.dtype(
        [("osm_id", "i8"), ("type", "u1"), ("lon", "f8"), ("lat", "f8")]
    )))

    # leg 1 ends far from any hut - no hut within max_snap_m at the shared midpoint
    _write_tour_folder(tours_dir, "GapTour", {
        1: [(11.0, 47.0), (11.0, 47.005), (12.0, 48.0)],
        2: [(12.0, 48.0), (11.0, 47.015), (11.0, 47.02)],
    })

    dem_path = _flat_dem(tmp_path, elevation=1500.0, origin=(10.0, 49.0), size=400, pixel_deg=0.005)

    import lib.pipeline as pipeline_lib
    monkeypatch.setattr(pipeline_lib, "TOURS_DIR", tours_dir)
    monkeypatch.setattr(mte, "TOURS_DIR", tours_dir)

    mte.main([
        "--dem", str(dem_path), "--huts", str(raw / "huts.geojson"),
        "--start-points", str(sp / "start-points.npy"), "--out-dir", str(out), "--max-snap-m", "100",
        "--smoothing-kernel-m", "0", "--min-slope-segment-m", "10", "--profile-points", "5",
        "--speed-v0", "4.013", "--speed-k", "3.5", "--speed-s0", "0.05", "--min-speed-ms", "0.15",
    ])

    with open(out / "tour-match-gaps.json", encoding="utf-8") as f:
        gaps = json.load(f)
    assert len(gaps) == 2  # leg 1's "to" and leg 2's "from" both fail the same shared midpoint
    assert all(g["reason"] == "leg_endpoint_unsnapped" for g in gaps)
    with open(out / "tours.json", encoding="utf-8") as f:
        assert json.load(f) == []


def test_write_hubs_json_matches_hub_list(tmp_path):
    hubs = [
        {"id": 3, "type": binfmt.TYPE_HUT, "lon": 11.0, "lat": 47.0, "name": "Hütte"},
        {"id": 8, "type": binfmt.TYPE_PARKING, "lon": 11.1, "lat": 47.1, "name": ""},
    ]
    path = mte.write_hubs_json(hubs, tmp_path)
    assert path == tmp_path / "hubs.json"
    assert json.loads(path.read_text(encoding="utf-8")) == [
        {"id": 3, "type": "hut", "lon": 11.0, "lat": 47.0, "name": "Hütte"},
        {"id": 8, "type": "parking", "lon": 11.1, "lat": 47.1, "name": ""},
    ]


def _run_main(tmp_path, monkeypatch, huts_coords, legs, dem_kwargs, extra_tours=None):
    """huts_coords: [(lon, lat), ...] as huts; legs: {leg_number: [(lon, lat), ...]}. Returns the tour-edges output dir."""
    raw = tmp_path / "raw"
    raw.mkdir()
    sp = tmp_path / "start-points"
    sp.mkdir()
    out = tmp_path / "tour-edges"
    tours_dir = tmp_path / "tours"
    huts = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": f"Hut {i}"},
         "geometry": {"type": "Point", "coordinates": list(c)}}
        for i, c in enumerate(huts_coords)
    ]}
    (raw / "huts.geojson").write_text(json.dumps(huts), encoding="utf-8")
    binfmt.save_array(sp / "start-points.npy", np.zeros(0, dtype=np.dtype(
        [("osm_id", "i8"), ("type", "u1"), ("lon", "f8"), ("lat", "f8")])))
    _write_tour_folder(tours_dir, "T", legs)
    for name, extra_legs in (extra_tours or {}).items():
        _write_tour_folder(tours_dir, name, extra_legs)
    dem_path = _flat_dem(tmp_path, **dem_kwargs)

    import lib.pipeline as pipeline_lib
    monkeypatch.setattr(pipeline_lib, "TOURS_DIR", tours_dir)
    monkeypatch.setattr(mte, "TOURS_DIR", tours_dir)
    mte.main([
        "--dem", str(dem_path), "--huts", str(raw / "huts.geojson"),
        "--start-points", str(sp / "start-points.npy"), "--out-dir", str(out), "--max-snap-m", "100",
        "--smoothing-kernel-m", "0", "--min-slope-segment-m", "10", "--profile-points", "5",
        "--speed-v0", "4.013", "--speed-k", "3.5", "--speed-s0", "0.05", "--min-speed-ms", "0.15",
    ])
    return out


_DEM = dict(elevation=1500.0, origin=(10.9, 47.1), size=300, pixel_deg=0.001)
_WIDE_DEM = dict(elevation=1500.0, origin=(10.9, 47.6), size=700, pixel_deg=0.001)


def test_geometry_equals_raw_gpx_points_exactly(tmp_path, monkeypatch):
    leg1 = [(11.0, 47.0), (11.0003, 47.004), (11.0, 47.01)]
    leg2 = [(11.0, 47.01), (11.0002, 47.015), (11.0, 47.02)]
    out = _run_main(tmp_path, monkeypatch, [(11.0, 47.0), (11.0, 47.01), (11.0, 47.02)],
                        {1: leg1, 2: leg2}, _DEM)
    records = binfmt.load_array(out / "records.npy", mmap=False)
    geometry = binfmt.load_array(out / "geometry.npy", mmap=False)
    for r, expected in zip(records, (leg1, leg2)):
        sl = geometry[int(r["geom_offset"]):int(r["geom_offset"]) + int(r["geom_count"])]
        assert list(zip(sl["lon"].tolist(), sl["lat"].tolist())) == expected


def test_tours_json_scalars_match_records_via_edge_id(tmp_path, monkeypatch):
    out = _run_main(
        tmp_path, monkeypatch, [(11.0, 47.0), (11.0, 47.01), (11.0, 47.02)],
        {1: [(11.0, 47.0), (11.0, 47.005), (11.0, 47.01)],
         2: [(11.0, 47.01), (11.0, 47.015), (11.0, 47.02)]}, _DEM)
    records = binfmt.load_array(out / "records.npy", mmap=False)
    tours = json.loads((out / "tours.json").read_text(encoding="utf-8"))
    legs = tours[0]["legs"]
    assert tours[0]["numDays"] == len(legs) == 2
    for leg in legs:
        r = records[leg["edgeId"]]
        assert leg["distanceM"] == pytest.approx(float(r["distance_m"]), rel=1e-6)
        assert leg["ascentM"] == pytest.approx(float(r["ascent_m"]), abs=1e-3)
        assert leg["descentM"] == pytest.approx(float(r["descent_m"]), abs=1e-3)
        assert leg["durationS"] == pytest.approx(float(r["duration_s"]), rel=1e-6)
        assert leg["maxEleM"] == pytest.approx(float(r["max_ele_m"]), rel=1e-6)
        assert leg["from"]["type"] == "hut" and leg["to"]["type"] == "hut"


def test_tour_with_an_unsnappable_endpoint_is_dropped_entirely(tmp_path, monkeypatch):
    # leg 1's end / leg 2's start (11.5, 47.5) is far from every hut.
    out = _run_main(
        tmp_path, monkeypatch, [(11.0, 47.0), (11.0, 47.02)],
        {1: [(11.0, 47.0), (11.2, 47.2), (11.5, 47.5)],
         2: [(11.5, 47.5), (11.2, 47.3), (11.0, 47.02)]}, _WIDE_DEM)
    assert json.loads((out / "tours.json").read_text(encoding="utf-8")) == []
    assert len(binfmt.load_array(out / "records.npy", mmap=False)) == 0
    gaps = json.loads((out / "tour-match-gaps.json").read_text(encoding="utf-8"))
    assert {(g["legIndex"], g["detail"]["endpoint"]) for g in gaps} == {(0, "to"), (1, "from")}


def test_dropped_tour_does_not_consume_edge_ids_or_shift_tour_ids(tmp_path, monkeypatch):
    # tour "T" has unsnappable legs 1-2 and is dropped; tour "U" (sorted second, tourId 1) is complete.
    out = _run_main(
        tmp_path, monkeypatch, [(11.0, 47.0), (11.0, 47.02), (11.0, 47.03)],
        {1: [(11.0, 47.0), (11.2, 47.2), (11.5, 47.5)],
         2: [(11.5, 47.5), (11.2, 47.3), (11.0, 47.02)],
         3: [(11.0, 47.02), (11.0, 47.025), (11.0, 47.03)]}, _WIDE_DEM,
        extra_tours={"U": {1: [(11.0, 47.02), (11.0, 47.025), (11.0, 47.03)]}})
    tours = json.loads((out / "tours.json").read_text(encoding="utf-8"))
    assert [t["tourId"] for t in tours] == [1]
    assert [leg["edgeId"] for leg in tours[0]["legs"]] == [0]
    assert len(binfmt.load_array(out / "records.npy", mmap=False)) == 1
