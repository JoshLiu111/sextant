"""ECB adapter on recorded ECB Data Portal responses (no network): parsing,
metadata, the reuse allowlist and error classification."""

from datetime import UTC, date, datetime

import httpx
import pytest

from ecb_fixtures import FIXTURES, RecordedEcb, recorded_adapter
from sextant_compute.data.context import RequestContext
from sextant_compute.data.errors import NoSuchData, SourceUnavailable

CTX = RequestContext.anonymous()
DFR = "FM/B.U2.EUR.4F.KR.DFR.LEV"
HICP = "HICP/M.U2.N.000000.4D0.ANR"


def fetch(series_id=DFR, start=date(1999, 1, 1), ecb=None, **kwargs):
    return recorded_adapter(ecb, **kwargs).economic_series(CTX, series_id, start)


def test_the_deposit_facility_rate_is_its_history_of_changes():
    found = fetch()

    assert found.observations[0] == (date(1999, 1, 1), 2.0)
    assert found.observations[-1] == (date(2026, 9, 16), 2.5)
    assert len(found.observations) == 69
    # The 2022 hiking cycle: out of negative territory in July, then 75 bp steps.
    assert [o for o in found.observations if date(2022, 7, 1) <= o[0] <= date(2022, 12, 31)] == [
        (date(2022, 7, 27), 0.0),
        (date(2022, 9, 14), 0.75),
        (date(2022, 11, 2), 1.5),
        (date(2022, 12, 21), 2.0),
    ]
    assert found.source.id == "ecb" and found.source.is_demo is False


def test_policy_rate_metadata_names_the_ecb_units_frequency_and_last_update():
    meta = fetch().meta

    assert meta.id == DFR
    assert meta.title == "Deposit facility - date of changes (raw data) - Level"
    assert meta.source == "European Central Bank"
    assert meta.units == "Percent per annum"
    assert meta.frequency == "On change (Governing Council decisions)"
    assert meta.last_updated == "2026-09-10T14:22:33+00:00"


def test_monthly_hicp_periods_are_the_first_of_the_month_and_credit_eurostat():
    found = fetch(HICP, start=date(2022, 6, 1))

    assert found.observations[0] == (date(2022, 6, 1), 8.6)
    assert dict(found.observations)[date(2022, 10, 1)] == 10.6
    assert found.latest == (date(2026, 10, 1), 4.0)
    assert found.meta.source == "Eurostat (via the ECB)"
    assert found.meta.units == "Annual rate of change, percent"
    assert found.meta.frequency == "Monthly"
    assert found.meta.seasonal_adjustment == "NSA"
    assert found.meta.last_updated == "2026-11-18T10:32:56+00:00"


def test_observations_before_the_start_are_dropped_and_the_request_asks_from_the_start():
    ecb = RecordedEcb()
    found = fetch(HICP, start=date(2026, 8, 1), ecb=ecb)

    assert found.observations == [(date(2026, 8, 1), 3.2), (date(2026, 9, 1), 3.8), (date(2026, 10, 1), 4.0)]
    (request,) = ecb.requests
    assert request.url.host == "data-api.ecb.europa.eu"
    assert request.url.path == f"/service/data/{HICP}"
    assert request.url.params["format"] == "csvdata"
    assert request.url.params["startPeriod"] == "2026-08-01"


def test_without_a_last_modified_header_the_fetch_time_is_the_last_update():
    body = (FIXTURES / "FM" / "B.U2.EUR.4F.KR.DFR.LEV.csv").read_bytes()
    ecb = RecordedEcb(override=lambda request: httpx.Response(200, content=body, headers={"content-type": "text/csv"}))

    found = fetch(ecb=ecb, now=lambda: datetime(2026, 11, 23, 6, 0, tzinfo=UTC))
    assert found.meta.last_updated == "2026-11-23T06:00:00+00:00"


def test_a_series_outside_the_allowlist_is_refused_before_any_request():
    ecb = RecordedEcb()

    with pytest.raises(NoSuchData) as err:
        fetch("EXR/D.USD.EUR.SP00.A", ecb=ecb)

    assert "EXR/D.USD.EUR.SP00.A" in err.value.missing
    assert ecb.requests == []


def test_only_published_values_are_supported():
    with pytest.raises(ValueError):
        recorded_adapter().economic_series(CTX, DFR, date(2020, 1, 1), units="pc1")


def test_a_series_the_ecb_has_no_data_for_is_no_such_data():
    def missing(request: httpx.Request):
        return httpx.Response(404, text='{"detail":"No Series was returned"}')

    with pytest.raises(NoSuchData) as err:
        fetch(ecb=RecordedEcb(override=missing))
    assert DFR in err.value.missing


def test_server_errors_are_retried_then_reported_as_source_unavailable():
    ecb = RecordedEcb(override=lambda request: httpx.Response(503, text="busy"))

    with pytest.raises(SourceUnavailable):
        fetch(ecb=ecb)
    assert len(ecb.requests) == 3


def test_garbage_and_network_errors_are_source_unavailable():
    def blocked(request: httpx.Request):
        # The portal's bot wall answers an HTML page.
        return httpx.Response(200, text="<html><h1>ECB Data Portal</h1>Your access has been blocked</html>")

    def down(request: httpx.Request):
        raise httpx.ConnectError("refused")

    for override in (blocked, down):
        with pytest.raises(SourceUnavailable):
            fetch(ecb=RecordedEcb(override=override))
