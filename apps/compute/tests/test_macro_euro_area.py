"""Macro Dashboard euro area section (ECB policy rates, HICP) on recorded ECB responses."""

import httpx
from fastapi.testclient import TestClient

from data_fixtures import serving
from ecb_fixtures import RecordedEcb, recorded_adapter
from main import app

client = TestClient(app)

ENDPOINT = "/api/compute/macro/euro-area"
RATES = ("deposit_facility_rate", "main_refinancing_rate", "marginal_lending_rate")


def euro_area(ecb: RecordedEcb | None = None, **body):
    body.setdefault("end", "2026-11-22")
    with serving(recorded_adapter(ecb), "ecb"):
        return client.post(ENDPOINT, json=body)


def test_the_three_key_ecb_rates_in_force_and_since_when():
    response = euro_area()
    assert response.status_code == 200, response.text
    metrics = response.json()["metrics"]

    assert {k: metrics[f"latest:{k}"]["value"] for k in RATES} == {
        "deposit_facility_rate": 2.5,
        "main_refinancing_rate": 2.65,
        "marginal_lending_rate": 2.9,
    }
    dfr = metrics["latest:deposit_facility_rate"]
    assert dfr["unit"] == "percent"
    assert dfr["details"]["date"] == "2026-09-16"
    assert dfr["details"]["source"] == "European Central Bank"
    assert dfr["details"]["units"] == "Percent per annum"
    assert dfr["details"]["frequency"] == "On change (Governing Council decisions)"
    assert dfr["details"]["last_updated"] == "2026-09-10T14:22:33+00:00"
    assert dfr["details"]["series_id"] == "FM/B.U2.EUR.4F.KR.DFR.LEV"


def test_hicp_inflation_is_the_latest_monthly_annual_rate():
    body = euro_area().json()
    hicp = body["metrics"]["latest:hicp_inflation"]

    assert hicp["value"] == 4.0
    assert hicp["details"]["date"] == "2026-10"
    assert hicp["details"]["source"] == "Eurostat (via the ECB)"
    assert hicp["details"]["frequency"] == "Monthly"
    assert hicp["details"]["seasonal_adjustment"] == "NSA"
    assert body["source"] == {"id": "ecb", "name": "European Central Bank", "is_demo": False}
    assert body["meta"]["data_cutoff"] == "2026-10-31"


def test_rate_history_is_a_step_line_that_holds_each_rate_until_the_next_decision():
    points = euro_area(start="2022-06-01", end="2022-12-31").json()["series"]["history:deposit_facility_rate"]["points"]

    assert [(p["x"], p["y"]) for p in points] == [
        ("2022-06-01", -0.5),  # the rate in force on the start date
        ("2022-07-26", -0.5),
        ("2022-07-27", 0.0),
        ("2022-09-13", 0.0),
        ("2022-09-14", 0.75),
        ("2022-11-01", 0.75),
        ("2022-11-02", 1.5),
        ("2022-12-20", 1.5),
        ("2022-12-21", 2.0),
        ("2022-12-31", 2.0),  # held to the end date
    ]


def test_the_rate_in_force_at_the_start_comes_from_a_decision_before_it():
    body = euro_area(start="2015-01-01").json()
    points = body["series"]["history:deposit_facility_rate"]["points"]

    # Set on 2014-09-10, before the history starts.
    assert points[0] == {"x": "2015-01-01", "y": -0.2}
    assert points[-1] == {"x": "2026-11-22", "y": 2.5}
    assert body["series"]["history:deposit_facility_rate"]["x_unit"] == "date"


def test_hicp_history_runs_monthly_from_the_start():
    series = euro_area(start="2022-06-01", end="2022-12-31").json()["series"]["history:hicp_inflation"]

    assert [(p["x"], p["y"]) for p in series["points"]] == [
        ("2022-06-01", 8.6), ("2022-07-01", 8.9), ("2022-08-01", 9.1), ("2022-09-01", 9.9),
        ("2022-10-01", 10.6), ("2022-11-01", 10.1), ("2022-12-01", 9.2),
    ]  # fmt: skip


def test_an_earlier_end_date_shows_what_was_in_force_then():
    metrics = euro_area(end="2022-08-15").json()["metrics"]

    assert metrics["latest:deposit_facility_rate"]["value"] == 0.0
    assert metrics["latest:deposit_facility_rate"]["details"]["date"] == "2022-07-27"
    assert metrics["latest:hicp_inflation"]["details"]["date"] == "2022-08"


def test_a_series_the_ecb_no_longer_has_only_blanks_that_series():
    def no_hicp(request: httpx.Request):
        return httpx.Response(404, text="{}") if request.url.path.startswith("/service/data/HICP/") else None

    body = euro_area(RecordedEcb(override=no_hicp)).json()

    assert body["metrics"]["latest:hicp_inflation"]["status"] == "missing_data"
    assert body["series"]["history:hicp_inflation"]["status"] == "missing_data"
    assert body["metrics"]["latest:deposit_facility_rate"]["status"] == "ok"


def test_an_ecb_outage_asks_to_retry():
    response = euro_area(RecordedEcb(override=lambda request: httpx.Response(500)))

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "source_unavailable"


def test_rate_histories_are_cached_across_start_dates():
    ecb = RecordedEcb()
    with serving(recorded_adapter(ecb), "ecb"):
        client.post(ENDPOINT, json={"start": "2015-01-01", "end": "2026-11-22"})
        calls = len(ecb.requests)
        client.post(ENDPOINT, json={"start": "2020-01-01", "end": "2026-11-22"})

    rate_paths = [p for p in RecordedEcb.paths(ecb) if p.startswith("/service/data/FM/")]
    assert calls == 4
    assert len(rate_paths) == 3  # the second request reused the rate histories


def test_date_validation():
    for body, field in [
        ({"start": "1998-12-31"}, "start"),
        ({"start": "2020-01-01", "end": "2019-12-31"}, "end"),
    ]:
        response = euro_area(**body)
        assert response.status_code == 422, body
        assert field in response.json()["error"]["fields"]
