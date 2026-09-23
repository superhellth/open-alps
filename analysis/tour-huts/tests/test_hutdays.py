from datetime import date

import pandas as pd

import hutdays

D0 = date(2025, 7, 1)


def rows(frees, status="SERVICED", start_day=1):
    return [{"date": f"{start_day + i:02d}.07.2025", "dayOfWeek": "X", "freePlace": f, "hutStatus": status}
            for i, f in enumerate(frees)]


def days_of(frees, cap=10, status="SERVICED"):
    return hutdays.hut_days(rows(frees, status), cap, 1, date(2025, 5, 1), date(2025, 10, 31))


def test_fully_booked_day_is_occupancy_one_and_sold_out():
    d = days_of([0, 10, 5])
    assert list(d.occupancy) == [1.0, 0.0, 0.5]
    assert list(d.sold_out) == [True, False, False]


def test_closed_day_is_not_open_and_has_no_occupancy():
    d = days_of([10, 3], status="CLOSED")
    assert not d.open.any() and d.occupancy.isna().all()


def test_free_above_capacity_flagged_and_clamped():
    d = days_of([12, 5])
    assert list(d.free_above_capacity) == [True, False]
    assert d.occupancy.iloc[0] == 0.0


def test_sold_out_near_uses_five_percent():
    d = hutdays.hut_days(rows([5, 6]), 100, 1, date(2025, 5, 1), date(2025, 10, 31))
    assert list(d.sold_out_near) == [True, False]


def test_days_outside_season_are_clipped():
    d = hutdays.hut_days(rows([1, 1, 1]), 10, 1, date(2025, 7, 2), date(2025, 7, 2))
    assert len(d) == 1


def test_eligibility_uses_open_day_count_only():
    few = hutdays.hut_season(days_of([0] * 13), "season")
    many = hutdays.hut_season(days_of([0] * 14), "season")
    assert few["eligible"] is False and many["eligible"] is True
    # bookings identical, eligibility differs only by open days
    assert few["occupancy"] == many["occupancy"] == 1.0


def test_no_activity_when_constant_free_place():
    assert hutdays.hut_season(days_of([10] * 20), "season")["no_activity"] is True
    assert hutdays.hut_season(days_of([10] * 19 + [9]), "season")["no_activity"] is False


def test_always_sold_out_hut_is_not_no_activity():
    assert hutdays.hut_season(days_of([0] * 20), "season")["no_activity"] is False


def test_capacity_mismatch_flag():
    assert hutdays.hut_season(days_of([11] + [5] * 19), "season")["capacity_mismatch"] is True


def test_cuts_filter_outcome_but_not_eligibility():
    d = days_of([0] * 31 + [10] * 0)  # 1..31 July, all sold out
    s = hutdays.hut_season(d, "fri_sun")
    assert s["open_days"] == 31 and s["eligible"]
    assert 0 < s["cut_open_days"] < 31
    assert s["sold_out_share"] == 1.0
    aug = hutdays.hut_season(d, "jul_aug")
    assert aug["cut_open_days"] == 31


def test_season_table_excludes_errors_and_shapes_columns():
    huts = [
        {"ohrs_id": 1, "on_tour": True, "elevation": 2000, "capacity": 10, "operator": "DAV",
         "region": "west", "approach_time_min": 30.0, "error": None},
        {"ohrs_id": 2, "on_tour": False, "elevation": None, "capacity": 10, "operator": "OEAV",
         "region": "east", "approach_time_min": None, "error": "self_service"},
    ]
    days = days_of([5] * 20)
    t = hutdays.season_table(huts, days, 2025)
    assert list(t.ohrs_id) == [1] and t.tour.iloc[0] == 1 and t.season.iloc[0] == 2025
    assert t.occupancy.iloc[0] == 0.5
