import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phases"))

from downloads.fetch_huts import classify_hut, split_features  # noqa: E402


def test_biwak_under_oeav_is_av_and_unserviced():
    # kategorie_nr 20 = Biwak, verein_nr 8 = ÖAV
    assert classify_hut(kategorie_nr=20, verein_nr=8) == ("av", False)


def test_biwak_under_slovenia_is_sonstige_and_unserviced():
    # kategorie_nr 20 = Biwak, verein_nr 20 = Alpine Association of Slovenia (not AV/DAV/AVS)
    assert classify_hut(kategorie_nr=20, verein_nr=20) == ("sonstige", False)


def test_jugendherberge_is_unserviced_too():
    # kategorie_nr 60 = Jugendherberge/Jugendheim, same Selbstversorger bucket as Biwak
    assert classify_hut(kategorie_nr=60, verein_nr=5) == ("av", False)


def test_dav_hut_is_av_and_serviced():
    assert classify_hut(kategorie_nr=40, verein_nr=5) == ("av", True)


def test_oeav_and_avs_are_also_av():
    assert classify_hut(kategorie_nr=30, verein_nr=8)[0] == "av"
    assert classify_hut(kategorie_nr=30, verein_nr=3)[0] == "av"


def test_bergsteigerdoerfer_partner_is_partner_with_no_serviced_flag():
    assert classify_hut(kategorie_nr=100, verein_nr=19) == ("partner", None)


def test_oeav_vertragshaus_is_also_partner():
    assert classify_hut(kategorie_nr=1, verein_nr=9) == ("partner", None)


def test_unrecognized_club_is_sonstige_and_serviced():
    # e.g. Privat (verein_nr 14), Club Alpino Italiano (4), Schweizer Alpenclub (10)
    assert classify_hut(kategorie_nr=30, verein_nr=14) == ("sonstige", True)


def test_split_features_routes_partner_to_second_list_with_minimal_properties():
    features = [
        {"attributes": {"id": "{GUID-1}", "OBJECTID": 501, "name": "Bielefelder Hütte",
                         "kategorie_nr": 40, "verein_nr": 5, "meereshoehe": 2112,
                         "ohrs_hut_id": "179"},
         "geometry": {"x": 10.9, "y": 47.2}},
        {"attributes": {"id": "{GUID-2}", "OBJECTID": 502, "name": "Gasthof Alpenrose",
                         "kategorie_nr": 100, "verein_nr": 19, "meereshoehe": 1150,
                         "ohrs_hut_id": None},
         "geometry": {"x": 11.5, "y": 47.3}},
    ]

    huts, partners = split_features(features)

    assert len(huts) == 1 and len(partners) == 1
    assert huts[0]["properties"] == {
        "id": "{GUID-1}", "name": "Bielefelder Hütte", "hutType": "av",
        "serviced": True, "elevation": 2112, "ohrsHutId": "179", "tenantCode": 5,
    }
    assert partners[0]["properties"] == {"id": 502, "name": "Gasthof Alpenrose"}
    assert partners[0]["geometry"] == {"type": "Point", "coordinates": [11.5, 47.3]}


def test_split_features_hut_with_no_ohrs_id_gets_null_ohrs_hut_id():
    # Direct-booking-only hut: the ArcGIS layer returns ohrs_hut_id: null for these (spec §1).
    features = [
        {"attributes": {"id": "{GUID-3}", "OBJECTID": 503, "name": "Almhütte Privat",
                         "kategorie_nr": 30, "verein_nr": 14, "meereshoehe": 1600,
                         "ohrs_hut_id": None},
         "geometry": {"x": 11.0, "y": 47.4}},
    ]

    huts, _ = split_features(features)

    assert huts[0]["properties"]["ohrsHutId"] is None
    assert huts[0]["properties"]["tenantCode"] == 14


def test_split_features_hut_missing_ohrs_hut_id_field_entirely_gets_null():
    # Defensive: a record missing the key outright (not just null-valued) must not KeyError.
    features = [
        {"attributes": {"id": "{GUID-4}", "OBJECTID": 504, "name": "Alte Hütte",
                         "kategorie_nr": 30, "verein_nr": 8, "meereshoehe": 1900},
         "geometry": {"x": 11.2, "y": 47.5}},
    ]

    huts, _ = split_features(features)

    assert huts[0]["properties"]["ohrsHutId"] is None
    assert huts[0]["properties"]["tenantCode"] == 8


def test_out_fields_requests_ohrs_hut_id():
    from downloads.fetch_huts import OUT_FIELDS
    assert "ohrs_hut_id" in OUT_FIELDS.split(",")


def test_split_features_preserves_input_order_within_each_list():
    features = [
        {"attributes": {"id": "a", "OBJECTID": 1, "name": "Hut A", "kategorie_nr": 30,
                         "verein_nr": 5, "meereshoehe": 2000},
         "geometry": {"x": 10.0, "y": 47.0}},
        {"attributes": {"id": "b", "OBJECTID": 2, "name": "Partner B", "kategorie_nr": 100,
                         "verein_nr": 19, "meereshoehe": 1000},
         "geometry": {"x": 10.1, "y": 47.1}},
        {"attributes": {"id": "c", "OBJECTID": 3, "name": "Hut C", "kategorie_nr": 30,
                         "verein_nr": 8, "meereshoehe": 2200},
         "geometry": {"x": 10.2, "y": 47.2}},
    ]

    huts, partners = split_features(features)

    assert [h["properties"]["name"] for h in huts] == ["Hut A", "Hut C"]
    assert [p["properties"]["name"] for p in partners] == ["Partner B"]
