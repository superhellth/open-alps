import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.tour_folder import (  # noqa: E402
    load_all_tour_folders, load_tour_folder, parse_leg_gpx,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "tour_folder"


def test_parse_leg_gpx_returns_ordered_lon_lat_ignoring_ele():
    points = parse_leg_gpx(FIXTURES / "GoodTour" / "1.gpx")
    assert points == [(11.1, 47.1), (11.2, 47.2)]


def test_load_tour_folder_orders_legs_by_filename_and_ignores_non_gpx():
    legs = load_tour_folder(FIXTURES / "GoodTour")
    assert [n for n, _ in legs] == [1, 2]
    assert legs[0][1] == [(11.1, 47.1), (11.2, 47.2)]


def test_load_tour_folder_sorts_numerically_not_lexicographically():
    legs = load_tour_folder(FIXTURES / "NumericOrderTour")
    assert [n for n, _ in legs] == [1, 2, 10]  # not [1, 10, 2]


def test_load_tour_folder_raises_on_non_numeric_stem():
    with pytest.raises(ValueError, match="leg-one.gpx"):
        load_tour_folder(FIXTURES / "BadTour")


def test_load_all_tour_folders_sorted_by_name():
    names = [name for name, _ in load_all_tour_folders(FIXTURES)]
    assert names == sorted(names)
    assert "GoodTour" in names
