from datetime import date

import fetch_calendars
import fetch_capacity
import fetch_tours


def test_parse_tours_handles_empty_list_missing_name_and_case():
    payload = {"features": [
        {"attributes": {"Bezeichnung": "A", "Huettenliste": "{abc-1},{DEF-2}"}},
        {"attributes": {"Bezeichnung": "B", "Huettenliste": ""}},
        {"attributes": {"Bezeichnung": None, "Huettenliste": None}},
    ]}
    tours = fetch_tours.parse_tours(payload)
    assert tours[0] == {"name": "A", "guids": ["{ABC-1}", "{DEF-2}"]}
    assert tours[1]["guids"] == []
    assert tours[2] == {"name": None, "guids": []}


def test_calendar_body_and_urls():
    body = fetch_calendars.calendar_body(date(2025, 5, 1), date(2025, 10, 31))
    assert body == {"arrivalDate": "01.05.2025", "departureDate": "31.10.2025",
                    "nextPossibleReservations": False, "numberOfPeople": 1}
    assert fetch_calendars.calendar_url(179).endswith("/api/v1/reservation/availabilityCalendar/179")
    assert fetch_capacity.info_url(179).endswith("/api/v1/reservation/hutInfo/179")
