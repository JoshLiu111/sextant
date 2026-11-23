"""Screener price criteria (story 84): 52-week change and distance from the
52-week high, on the signed-in user's own Tiingo prices.

Fundamentals come from the recorded EDGAR frames (CY2025: the default screen
matches AMZN, GOOGL, MSFT, NVDA, META, LLY, AVGO, NFLX, ADBE). Prices come from
``FakeTiingo`` (tests/tiingo_fixtures.py), whose weekly 2025-11-14..2026-11-20
files give known 52-week figures as of 2026-11-20 (pinned with
``SCREENER_PRICES_AS_OF``). MSFT's file has no rows in that window and ADBE has
none at all, so both stand for companies the provider can't price.
"""

from __future__ import annotations

import psycopg
import pytest

from sextant_compute.data.service import make_data_service
from sextant_compute.keys.api import get_tiingo
from tests.auth_helpers import bearer, sign_in
from tests.edgar_fixtures import edgar_adapter
from tiingo_fixtures import FakeTiingo

PATH = "/api/compute/screener/screen"
ALICE_KEY = "a1111111111111111111111111111111111111aaa"
BOB_KEY = "b2222222222222222222222222222222222222bbb"
TEST_KEY_SECRET = "test-provider-key-secret-not-for-production-0123456789"
DEFAULT = [
    {"metric": "revenue_growth", "op": "min", "value": 0.10},
    {"metric": "gross_margin", "op": "min", "value": 0.40},
    {"metric": "roe", "op": "min", "value": 0.15},
]


@pytest.fixture
def tiingo(client, monkeypatch) -> FakeTiingo:
    monkeypatch.setenv("PROVIDER_KEY_SECRET", TEST_KEY_SECRET)
    monkeypatch.setenv("SCREENER_PRICES_AS_OF", "2026-11-20")
    fake = FakeTiingo({ALICE_KEY, BOB_KEY})
    adapter = fake.adapter()
    client.app.dependency_overrides[get_tiingo] = lambda: adapter
    client.app.state.data_service = make_data_service(
        client.app.state.db, {"sec_edgar": edgar_adapter(), "tiingo": adapter}
    )
    return fake


def user_with_key(client, name: str, key: str | None) -> dict[str, str]:
    headers = bearer(sign_in(client, f"sub-{name}", email=f"{name}@example.test"))
    if key is not None:
        saved = client.put("/api/compute/keys/tiingo", json={"key": key}, headers=headers)
        assert saved.status_code == 200, saved.text
    return headers


@pytest.fixture
def alice(client, tiingo) -> dict[str, str]:
    return user_with_key(client, "alice", ALICE_KEY)


def screen(client, headers=None, *, criteria=None, **changes):
    body = {"year": 2025, "criteria": criteria if criteria is not None else DEFAULT, "price_source": "tiingo", **changes}
    return client.post(PATH, json=body, headers=headers)


def priced(*extra: dict) -> list[dict]:
    return [*DEFAULT, *extra]


def tickers(body: dict) -> list[str]:
    return [r["ticker"] for r in body["rows"]]


def test_fundamental_and_price_criteria_combine(client, alice):
    response = screen(client, alice, criteria=priced({"metric": "change_52w", "op": "min", "value": 0.18}))

    assert response.status_code == 200, response.text
    body = response.json()
    # Close on 2026-11-20 over the close on 2025-11-21: NVDA 150/100, GOOGL 210/150,
    # AMZN 240/200, AVGO 300/250 (split-adjusted: raw 1000 before its 4:1 split);
    # META 540/600 and NFLX 900/1000 fall, LLY 920/800 = +15% is under 18%.
    assert tickers(body) == ["AMZN", "GOOGL", "NVDA", "AVGO"]
    values = {r["ticker"]: r["values"] for r in body["rows"]}
    assert values["NVDA"]["change_52w"] == pytest.approx(0.5)
    assert values["GOOGL"]["change_52w"] == pytest.approx(0.4)
    assert values["AMZN"]["change_52w"] == pytest.approx(0.2)
    assert values["AVGO"]["change_52w"] == pytest.approx(0.2)
    # Fundamentals still come through unchanged next to the price column.
    assert values["NVDA"]["revenue_growth"] == pytest.approx(215_938 / 130_497 - 1)
    assert [c["id"] for c in body["columns"]] == ["revenue", "revenue_growth", "gross_margin", "roe", "change_52w"]
    assert body["columns"][-1] == {"id": "change_52w", "label": "52-week change", "unit": "decimal"}
    assert body["source"]["id"] == "sec_edgar"
    assert body["price_source"] == {"id": "tiingo", "name": "Tiingo", "is_demo": False}
    assert body["prices_as_of"] == "2026-11-20"
