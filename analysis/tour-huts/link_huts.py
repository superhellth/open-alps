"""Joins geojson huts, tours, hutInfo, calendars and approach times into huts.json (one entry per ohrsHutId)."""
from __future__ import annotations

import math
import re

import common
import fetch_tours
from approach_time import approach_minutes

COORD_FLAG_KM = 1.0
OPERATORS = {5: "DAV", 8: "OEAV"}


def operator_of(tenant_code) -> str:
    return OPERATORS.get(tenant_code, "other")


def region_of(lon: float) -> str:
    if lon < 10.5:
        return "west"
    return "central" if lon < 12.5 else "east"


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def parse_hut_info(rec: dict) -> dict:
    """Capacity, category-sum capacity and coordinates from a stored hutInfo record."""
    empty = {"capacity": None, "capacity_sum": None, "lat": None, "lon": None, "error": rec.get("error")}
    if not rec.get("ok"):
        return empty
    b = rec["body"]
    out = dict(empty, error=None)
    try:
        out["capacity"] = int(b["totalBedsInfo"])
    except (KeyError, TypeError, ValueError):
        out["error"] = "totalBedsInfo missing"
    cats = b.get("hutBedCategories") or []
    if cats:
        out["capacity_sum"] = sum(int(c.get("totalSleepingPlaces") or 0) for c in cats)
    m = re.match(r"\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)", b.get("coordinates") or "")
    if m:
        out["lat"], out["lon"] = float(m.group(1)), float(m.group(2))
    return out


def _calendar_error(ohrs_id: int, calendars: dict) -> str | None:
    for season in sorted(calendars):
        rec = calendars[season].get(ohrs_id)
        if rec is None:
            return f"calendar_missing {season}"
        if not rec.get("ok"):
            return f"calendar_error {season}: {rec.get('error')}"
        if not rec["body"]:
            return f"calendar_empty {season}"
    return None


def link(features, tours, info, calendars, approach) -> dict:
    tour_guids = {g for t in tours for g in t["guids"]}
    geojson_guids = {f["properties"]["id"].upper() for f in features}
    by_id: dict[int, list[dict]] = {}
    for f in features:
        if f["properties"].get("ohrsHutId"):
            by_id.setdefault(int(f["properties"]["ohrsHutId"]), []).append(f)
    huts = []
    for ohrs_id in sorted(by_id):
        fs = by_id[ohrs_id]
        props = [f["properties"] for f in fs]
        guids = [p["id"] for p in props]
        lons = [f["geometry"]["coordinates"][0] for f in fs]
        lats = [f["geometry"]["coordinates"][1] for f in fs]
        lon, lat = sum(lons) / len(lons), sum(lats) / len(lats)
        i = info.get(ohrs_id) or parse_hut_info({"ok": False, "error": "hut-info missing"})
        coord_km = (haversine_km(lat, lon, i["lat"], i["lon"])
                    if i["lat"] is not None else None)
        serviced = any(p.get("serviced") for p in props)
        if not serviced:
            error = "self_service"
        elif i["capacity"] is None or i["capacity"] <= 0:
            error = f"no_capacity: {i['error']}"
        else:
            error = _calendar_error(ohrs_id, calendars)
        times = [approach[g.upper()] for g in guids if g.upper() in approach]
        elev = props[0].get("elevation") or None
        huts.append({
            "ohrs_id": ohrs_id, "guids": guids, "names": [p["name"] for p in props],
            "on_tour": any(g.upper() in tour_guids for g in guids),
            "elevation": elev, "operator": operator_of(props[0].get("tenantCode")),
            "serviced": serviced, "lon": lon, "lat": lat,
            "capacity": i["capacity"], "capacity_sum": i["capacity_sum"],
            "coord_km": coord_km, "coord_flag": coord_km is not None and coord_km > COORD_FLAG_KM,
            "region": region_of(lon), "approach_time_min": min(times) if times else None,
            "error": error,
        })
    return {"huts": huts, "unmatched_tour_guids": sorted(tour_guids - geojson_guids)}


def main(argv=None) -> None:
    raw = common.OUT / "raw"
    feats = common.read_json(common.HUTS_GEOJSON)["features"]
    tours_rec = common.read_json(raw / "tours.json")
    tours = fetch_tours.parse_tours(tours_rec["body"])
    info = {}
    for p in (raw / "hut-info").glob("*.json"):
        info[int(p.stem)] = parse_hut_info(common.read_json(p))
    calendars = {}
    for season in common.SEASONS:
        calendars[season] = {int(p.stem): common.read_json(p)
                             for p in (raw / f"calendar-{season}").glob("*.json")}
    data = common.ROOT / "huts" / "public" / "data"
    manifest = common.read_json(data / "approaches.json")
    hut_ids = common.read_json(data / "hut-edge-payload.json")["hut_ids"]
    approach = approach_minutes(manifest, (data / "approaches.bin").read_bytes(), hut_ids)
    out = link(feats, tours, info, calendars, approach)
    common.write_json(common.OUT / "huts.json", out)
    excluded = [h for h in out["huts"] if h["error"]]
    print(f"{len(out['huts'])} huts, {len(excluded)} excluded, "
          f"{len(out['unmatched_tour_guids'])} unmatched tour GUIDs, "
          f"{sum(h['coord_flag'] for h in out['huts'])} coordinate flags")


if __name__ == "__main__":
    main()
