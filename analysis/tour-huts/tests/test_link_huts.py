import link_huts


def feat(guid, name, ohrs, tenant=8, elev=2000, serviced=True, lon=11.0, lat=47.0):
    return {"properties": {"id": guid, "name": name, "ohrsHutId": ohrs, "tenantCode": tenant,
                           "elevation": elev, "serviced": serviced},
            "geometry": {"coordinates": [lon, lat]}}


def cal(n=20):
    return {"ok": True, "body": [{"date": "01.07.2025", "dayOfWeek": "TUESDAY",
                                   "freePlace": 3, "hutStatus": "SERVICED"}] * n}


INFO_OK = {"ok": True, "body": {"totalBedsInfo": "60", "coordinates": "47.0, 11.0",
                                "hutBedCategories": [{"totalSleepingPlaces": 37}, {"totalSleepingPlaces": 23}]}}


def run(features, tours=None, info=None, calendars=None, approach=None):
    tours = tours if tours is not None else []
    return link_huts.link(features, tours, info or {}, calendars or {2025: {}, 2026: {}}, approach or {})


def test_shared_ohrs_id_is_one_hut_and_tour_if_either_guid_on_tour():
    feats = [feat("{A}", "Eingang", "73"), feat("{B}", "Anger", "73")]
    out = run(feats, tours=[{"name": "T", "guids": ["{B}"]}],
              info={73: link_huts.parse_hut_info(INFO_OK)},
              calendars={2025: {73: cal()}, 2026: {73: cal()}})
    assert len(out["huts"]) == 1
    h = out["huts"][0]
    assert h["guids"] == ["{A}", "{B}"] and h["on_tour"] is True and h["error"] is None
    assert h["capacity"] == 60 and h["capacity_sum"] == 60


def test_unmatched_tour_guids_are_listed_and_tour_matching_is_case_insensitive():
    feats = [feat("{a1}", "X", "1")]
    out = run(feats, tours=[{"name": "T", "guids": ["{A1}", "{ZZ}"]}])
    assert out["unmatched_tour_guids"] == ["{ZZ}"]
    assert out["huts"][0]["on_tour"] is True


def test_errors_exclude_hut_with_reason():
    feats = [feat("{A}", "self", "1", serviced=False), feat("{B}", "nocap", "2"),
             feat("{C}", "calerr", "3"), feat("{D}", "calmissing", "4"), feat("{E}", "empty", "5")]
    info = {i: link_huts.parse_hut_info(INFO_OK) for i in (1, 3, 4, 5)}
    info[2] = link_huts.parse_hut_info({"ok": False, "error": "HTTP 404"})
    cals = {2025: {1: cal(), 3: {"ok": False, "error": "HTTP 500"}, 5: {"ok": True, "body": []}},
            2026: {1: cal(), 3: cal(), 4: cal(), 5: cal()}}
    err = {h["ohrs_id"]: h["error"] for h in run(feats, info=info, calendars=cals)["huts"]}
    assert err[1] == "self_service"
    assert err[2].startswith("no_capacity")
    assert err[3].startswith("calendar_error 2025")
    assert err[4] == "calendar_missing 2025"
    assert err[5] == "calendar_empty 2025"


def test_elevation_zero_is_missing_operator_and_region():
    feats = [feat("{A}", "a", "1", tenant=5, elev=0, lon=9.0), feat("{B}", "b", "2", tenant=3, lon=13.0)]
    hs = {h["ohrs_id"]: h for h in run(feats)["huts"]}
    assert hs[1]["elevation"] is None and hs[1]["operator"] == "DAV" and hs[1]["region"] == "west"
    assert hs[2]["operator"] == "other" and hs[2]["region"] == "east"
    assert link_huts.operator_of(8) == "OEAV"
    assert link_huts.region_of(11.0) == "central"


def test_coord_check_flags_over_1km():
    far = {"ok": True, "body": {"totalBedsInfo": "10", "coordinates": "47.1, 11.0", "hutBedCategories": []}}
    h = run([feat("{A}", "a", "1")], info={1: link_huts.parse_hut_info(far)})["huts"][0]
    assert h["coord_flag"] is True and h["coord_km"] > 10
    near = link_huts.parse_hut_info(INFO_OK)
    h = run([feat("{A}", "a", "1")], info={1: near})["huts"][0]
    assert h["coord_flag"] is False


def test_approach_time_is_min_over_guids():
    feats = [feat("{a}", "a", "73"), feat("{b}", "b", "73")]
    h = run(feats, approach={"{A}": 90.0, "{B}": 45.0})["huts"][0]
    assert h["approach_time_min"] == 45.0


def test_parse_hut_info_error_record():
    assert link_huts.parse_hut_info({"ok": False, "error": "x"})["capacity"] is None
