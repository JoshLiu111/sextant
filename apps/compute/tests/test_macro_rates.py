"""Macro Dashboard rates (yield curve, 10Y-2Y spread) on recorded Treasury responses."""

from datetime import date, datetime

import httpx
from fastapi.testclient import TestClient

from data_fixtures import serving
from main import app
from sextant_compute.data.service import default_adapters
from treasury_fixtures import RecordedTreasury, csv_response, recorded_adapter

client = TestClient(app)

ENDPOINT = "/api/compute/macro/rates"


def rates(treasury: RecordedTreasury | None = None, **body):
    body.setdefault("end", "2026-11-22")
    with serving(recorded_adapter(treasury), "treasury"):
        return client.post(ENDPOINT, json=body)


def test_the_latest_curve_lists_every_published_maturity_from_shortest_to_longest():
    response = rates()
    assert response.status_code == 200, response.text
    curve = response.json()["series"]["yield_curve:latest"]

    assert curve["status"] == "ok"
    assert curve["x_unit"] == "years" and curve["y_unit"] == "percent"
    assert curve["details"]["date"] == "2026-11-20"
    # The 11/20/2026 row: 1 Mo, 1.5 Month, 2/3/4/6 Mo, 1/2/3/5/7/10/20/30 Yr.
    assert [(round(p["x"], 4), p["y"]) for p in curve["points"]] == [
        (0.0833, 4.19), (0.125, 4.26), (0.1667, 4.28), (0.25, 4.32), (0.3333, 4.32), (0.5, 4.38),
        (1.0, 4.51), (2.0, 4.63), (3.0, 4.65), (5.0, 4.71), (7.0, 4.80), (10.0, 4.92), (20.0, 5.34), (30.0, 5.31),
    ]


def test_the_curves_from_one_month_and_one_year_before_the_latest_are_overlaid():
    series = rates().json()["series"]

    month_ago, year_ago = series["yield_curve:1m_ago"], series["yield_curve:1y_ago"]
    assert month_ago["details"]["date"] == "2026-10-20"
    assert year_ago["details"]["date"] == "2025-11-20"
    # The 10 Yr column of the 10/20/2026 and 11/20/2025 rows.
    assert {p["x"]: p["y"] for p in month_ago["points"]}[10.0] == 5.12
    assert {p["x"]: p["y"] for p in year_ago["points"]}[10.0] == 4.10


def test_the_latest_curve_is_the_last_business_day_on_or_before_the_end_date():
    body = rates(end="2026-11-08").json()  # a Sunday

    assert body["series"]["yield_curve:latest"]["details"]["date"] == "2026-11-06"
    assert body["meta"]["data_cutoff"] == "2026-11-06"


def test_a_comparison_curve_on_a_weekend_falls_back_to_the_previous_business_day():
    # Latest Tuesday 2026-11-10; a month earlier is Saturday 10/10, so Friday 10/09.
    body = rates(end="2026-11-10").json()

    assert body["series"]["yield_curve:latest"]["details"]["date"] == "2026-11-10"
    assert body["series"]["yield_curve:1m_ago"]["details"]["date"] == "2026-10-09"
    assert body["series"]["yield_curve:1y_ago"]["details"]["date"] == "2025-11-10"


# A hand-made year with known inversions (10 Yr below 2 Yr), newest first like Treasury.
KNOWN_INVERSIONS = """Date,"2 Yr","10 Yr"
06/12/2023,4.00,3.99
06/09/2023,4.00,4.10
06/08/2023,4.00,3.90
06/07/2023,4.00,
06/06/2023,4.00,3.95
06/05/2023,4.00,4.00
06/02/2023,4.10,4.00
06/01/2023,4.00,4.20"""


def known_inversions(year: int):
    return csv_response(KNOWN_INVERSIONS if year == 2023 else "")


def test_inversion_periods_are_the_runs_of_days_with_a_negative_spread():
    body = rates(RecordedTreasury(override=known_inversions), start="2023-01-01", end="2023-12-31").json()
    history = body["series"]["history:spread_10y_2y"]

    assert history["status"] == "ok"
    assert history["x_unit"] == "date" and history["y_unit"] == "percentage_points"
    assert [(p["x"], p["y"]) for p in history["points"]] == [
        ("2023-06-01", 0.2), ("2023-06-02", -0.1), ("2023-06-05", 0.0), ("2023-06-06", -0.05),
        ("2023-06-07", None), ("2023-06-08", -0.1), ("2023-06-09", 0.1), ("2023-06-12", -0.01),
    ]
    # A zero spread is not inverted; a day without a 10 Yr neither ends nor starts
    # a run; a run still open on the last day ends there.
    assert history["bands"] == [
        {"start": "2023-06-02", "end": "2023-06-02", "label": "Inverted"},
        {"start": "2023-06-06", "end": "2023-06-08", "label": "Inverted"},
        {"start": "2023-06-12", "end": "2023-06-12", "label": "Inverted"},
    ]
    assert body["metrics"]["latest:spread_10y_2y"]["value"] == -0.01


def test_the_recorded_history_shows_the_2019_and_2022_to_2024_inversions():
    bands = rates().json()["series"]["history:spread_10y_2y"]["bands"]

    # Late August 2019: the 10Y-2Y spread closed below zero for a few days.
    assert {"start": "2019-08-27", "end": "2019-08-29", "label": "Inverted"} in bands
    # The longest inversion on record ran from July 2022 to late August 2024, with
    # a few inverted days still following into early September 2024.
    longest = max(bands, key=lambda b: date.fromisoformat(b["end"]) - date.fromisoformat(b["start"]))
    assert longest["start"].startswith("2022-07") and longest["end"].startswith("2024-08")
    assert bands[-1]["end"].startswith("2024-09")
    assert all(not b["start"].startswith(("2018", "2020", "2021", "2025", "2026")) for b in bands)


def test_the_spread_is_the_10_year_minus_the_2_year_yield_in_percentage_points():
    metrics = rates().json()["metrics"]

    # 11/20/2026: 10 Yr 4.92, 2 Yr 4.63.
    assert metrics["latest:yield_10y"]["value"] == 4.92
    assert metrics["latest:yield_2y"]["value"] == 4.63
    spread = metrics["latest:spread_10y_2y"]
    assert spread["unit"] == "percentage_points"
    assert spread["value"] == 0.29
    assert spread["details"]["date"] == "2026-11-20"


def test_each_series_carries_its_source_units_frequency_and_last_update():
    body = rates().json()

    assert body["source"] == {"id": "treasury", "name": "U.S. Department of the Treasury", "is_demo": False}
    details = body["metrics"]["latest:yield_10y"]["details"]
    assert details["source"] == "U.S. Department of the Treasury"
    assert details["title"] == "Daily Treasury Par Yield Curve Rates"
    assert details["units"] == "Percent"
    assert details["frequency"] == "Daily (business days)"
    assert datetime.fromisoformat(str(details["last_updated"])).tzinfo is not None
    assert body["metrics"]["latest:spread_10y_2y"]["details"]["units"] == "Percentage points"


def test_maturities_are_parsed_by_column_name_whatever_the_year_publishes():
    # 2019 has no 4 Mo and no 1.5 Month column.
    body = rates(start="2019-01-01", end="2019-12-31").json()

    curve = body["series"]["yield_curve:latest"]
    assert curve["details"]["date"] == "2019-12-31"
    # 12/31/2019: 1 Mo 1.48, 2 Mo 1.51, 3 Mo 1.55, 6 Mo 1.60, 1 Yr 1.59, 2 Yr 1.58, ... 30 Yr 2.39.
    xs = [p["x"] for p in curve["points"]]
    assert xs == sorted(xs) and len(xs) == 12
    assert [(round(p["x"], 4), p["y"]) for p in curve["points"][:4]] == [
        (0.0833, 1.48), (0.1667, 1.51), (0.25, 1.55), (0.5, 1.60)
    ]
    assert curve["points"][-1] == {"x": 30.0, "y": 2.39}


def test_each_year_is_fetched_once_and_then_served_from_the_cache():
    treasury = RecordedTreasury()
    with serving(recorded_adapter(treasury), "treasury"):
        client.post(ENDPOINT, json={"start": "2024-01-01", "end": "2026-11-22"})
        assert sorted(treasury.years()) == [2024, 2025, 2026]
        client.post(ENDPOINT, json={"start": "2023-01-01", "end": "2026-11-22"})

    assert sorted(treasury.years()) == [2023, 2024, 2025, 2026]


def test_a_year_with_no_data_yet_is_simply_empty():
    body = rates(end="2027-01-01").json()  # Treasury answers 2027 with an empty body

    assert body["series"]["yield_curve:latest"]["details"]["date"] == "2026-11-20"


def test_a_treasury_outage_is_a_503_asking_to_retry():
    treasury = RecordedTreasury(override=lambda year: httpx.Response(500))

    response = rates(treasury)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "source_unavailable"
    assert len(treasury.requests) == 3  # retried, then gave up on the first year


def test_a_response_that_is_not_the_yield_curve_csv_is_a_503():
    treasury = RecordedTreasury(override=lambda year: csv_response("<html>Access denied</html>"))

    assert rates(treasury).status_code == 503


def test_a_start_before_the_treasury_series_is_a_field_error():
    response = rates(start="1985-01-01")

    assert response.status_code == 422
    assert response.json()["error"]["fields"] == {"start": "Treasury yield curve data starts on 1990-01-02."}


def test_treasury_is_a_registered_source():
    assert default_adapters()["treasury"].source.id == "treasury"
