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

from sextant_compute.data.service import cache_key, make_data_service
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
    fake.served_by = adapter  # type: ignore[attr-defined]
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


def test_companies_the_provider_cannot_price_are_excluded_with_the_reason(client, alice):
    body = screen(client, alice, criteria=priced({"metric": "from_52w_high", "op": "min", "value": -0.2})).json()

    # Last close over the highest close since 2025-11-21: GOOGL ends on its high,
    # AVGO 300/320, AMZN 240/260, LLY 920/1000, NVDA 150/180, NFLX 900/1100 (-18.2%);
    # META 540/700 (-22.9%) is further than 20% off its high.
    values = {r["ticker"]: r["values"]["from_52w_high"] for r in body["rows"]}
    assert values == pytest.approx(
        {
            "AMZN": 240 / 260 - 1,
            "GOOGL": 0.0,
            "NVDA": 150 / 180 - 1,
            "LLY": 920 / 1000 - 1,
            "AVGO": 300 / 320 - 1,
            "NFLX": 900 / 1100 - 1,
        }
    )
    assert body["matched"] == 6
    price = next(e for e in body["excluded"]["by_criterion"] if e["metric"] == "from_52w_high")
    assert price["label"] == "From 52-week high"
    assert price["count"] == 2
    assert sorted(r["reason"] for r in price["reasons"]) == [
        "No Tiingo prices for MSFT between 2025-11-14 and 2026-11-20.",
        "Tiingo has no ticker ADBE.",
    ]
    assert body["excluded"]["total"] == 9 + 2  # the fundamental exclusions plus the two unpriced companies


def test_results_sort_by_a_price_column(client, alice):
    body = screen(
        client,
        alice,
        criteria=priced({"metric": "change_52w", "op": "min", "value": -1}),
        sort="change_52w",
        direction="asc",
    ).json()

    # META -10%, NFLX -10% (tie, by ticker), LLY +15%, AMZN and AVGO +20%, GOOGL +40%, NVDA +50%.
    assert tickers(body) == ["META", "NFLX", "LLY", "AMZN", "AVGO", "GOOGL", "NVDA"]


def test_screener_prices_fetched_for_one_user_are_never_a_cache_hit_for_another_user_or_a_visitor(
    client, tiingo, alice, db_url
):
    bob = user_with_key(client, "bob", BOB_KEY)
    change = priced({"metric": "change_52w", "op": "min", "value": 0})

    assert screen(client, alice, criteria=change).status_code == 200
    assert screen(client, alice, criteria=change).status_code == 200
    assert tiingo.price_requests[(ALICE_KEY, "nvda")] == 1  # Alice's repeat came from her own cache

    assert screen(client, bob, criteria=change).status_code == 200
    assert tiingo.price_requests[(BOB_KEY, "nvda")] == 1  # Bob missed Alice's entry and used his own key

    anonymous = screen(client, criteria=change)
    assert anonymous.status_code == 403
    assert anonymous.json()["error"]["code"] == "key_required"
    assert "NVDA" not in anonymous.text
    # The 7 priced fundamental matches once each for Alice and Bob, none for the visitor.
    # (MSFT and ADBE have no prices; misses are not cached, so they are asked again.)
    priced_requests = {k: n for k, n in tiingo.price_requests.items() if k[1] not in ("msft", "adbe")}
    assert sorted(priced_requests.values()) == [1] * 14

    service = client.app.state.data_service
    shared_key = cache_key(
        tiingo.served_by,
        "daily_prices",
        {"tickers": ["NVDA"], "start": "2025-11-14", "end": "2026-11-20"},
    )
    assert service.shared_cache.get(shared_key) is None
    with psycopg.connect(db_url) as conn:
        owners = conn.execute("SELECT DISTINCT u.email FROM user_data_cache c JOIN users u ON u.id = c.user_id")
        assert sorted(email for (email,) in owners) == ["alice@example.test", "bob@example.test"]


def test_a_user_without_a_key_is_sent_to_settings_even_when_nothing_would_be_priced(client, tiingo):
    carol = user_with_key(client, "carol", None)
    nothing = [{"metric": "gross_margin", "op": "min", "value": 5}, {"metric": "change_52w", "op": "min", "value": 0}]

    response = screen(client, carol, criteria=nothing)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "key_required"
    assert "Settings" in response.json()["error"]["message"]
    assert tiingo.price_requests == {}


def test_price_criteria_without_my_data_are_flagged_on_the_criterion(client, alice):
    response = screen(
        client, alice, criteria=priced({"metric": "change_52w", "op": "min", "value": 0}), price_source=None
    )

    assert response.status_code == 422
    assert response.json()["error"]["fields"] == {
        "criteria.3.metric": "Price criteria need My data: sign in and add a price data key in Settings."
    }


def test_demo_prices_cannot_back_price_criteria(client, alice):
    response = screen(
        client, alice, criteria=priced({"metric": "change_52w", "op": "min", "value": 0}), price_source="synthetic"
    )

    assert response.status_code == 422
    assert "price_source" in response.json()["error"]["fields"]


def test_a_screen_that_would_price_too_many_companies_asks_to_tighten_the_fundamentals(client, tiingo, alice):
    response = screen(client, alice, criteria=[{"metric": "change_52w", "op": "min", "value": 0}])

    assert response.status_code == 422
    message = response.json()["error"]["fields"]["criteria"]
    assert message.startswith("Price criteria check at most 25 companies, and 36 pass")
    assert tiingo.price_requests == {}


def test_a_screen_without_price_criteria_carries_no_price_source(client, alice):
    body = screen(client, alice).json()

    assert body["price_source"] is None
    assert body["prices_as_of"] is None
    assert len(body["rows"]) == 9
