"""FMP daily prices and key checks: parsing recorded responses and classifying failures."""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from fmp_fixtures import FIRST_DAY, LAST_DAY, FakeFmp, recorded
from sextant_compute.data.context import RequestContext
from sextant_compute.data.errors import KeyRequired, NoSuchData, SourceUnavailable

KEY = "fmp0123456789abcdef0123456789abcd"
ALICE = RequestContext(user_id=None, keys={"fmp": KEY})


@pytest.fixture
def fake() -> FakeFmp:
    return FakeFmp({KEY})


def test_prices_come_oldest_first_with_split_adjusted_dividends_on_their_ex_dates(fake):
    frames = fake.adapter().daily_prices(ALICE, ["AAPL", "SPY", "MSFT"], FIRST_DAY, LAST_DAY)

    aapl = frames["AAPL"]
    assert list(aapl.columns) == ["open", "high", "low", "close", "volume", "dividend"]
    assert aapl.index.name == "date"
    assert aapl.index[0].date() == FIRST_DAY and aapl.index[-1].date() == LAST_DAY
    assert aapl["close"].iloc[0] == pytest.approx(100.0)
    assert aapl.loc["2024-01-16", "close"] == pytest.approx(120.0)
    # The 0.96 paid before the 4:1 split is 0.24 on the split-adjusted price scale;
    # the 2023 dividend is outside the range.
    assert aapl.loc["2024-01-10", "dividend"] == pytest.approx(0.24)
    assert aapl["dividend"].sum() == pytest.approx(0.48)

    spy = frames["SPY"]
    assert spy.loc["2024-01-09", "dividend"] == pytest.approx(1.5)
    assert spy["dividend"].sum() == pytest.approx(1.5)
    assert spy["close"].tolist() == pytest.approx([r["close"] for r in reversed(recorded("historical-price-eod", "spy"))])

    assert frames["MSFT"]["dividend"].sum() == 0.0


def test_requests_carry_the_users_key_in_a_header_and_the_date_range(fake):
    fake.adapter().daily_prices(ALICE, ["MSFT"], date(2024, 1, 3), date(2024, 1, 10))

    prices = next(r for r in fake.requests if r.url.path == "/stable/historical-price-eod/full")
    assert prices.url.params["symbol"] == "MSFT"
    assert prices.url.params["from"] == "2024-01-03"
    assert prices.url.params["to"] == "2024-01-10"
    for request in fake.requests:
        assert request.headers["apikey"] == KEY
        assert KEY not in str(request.url)


def test_unknown_tickers_and_symbols_outside_the_plan_are_no_such_data_per_ticker(fake):
    fake.premium = {"TSLA"}

    with pytest.raises(NoSuchData) as exc:
        fake.adapter().daily_prices(ALICE, ["AAPL", "ZZZZ", "TSLA"], FIRST_DAY, LAST_DAY)

    # A free plan answers both with the same 402, so the message can't tell them apart.
    assert exc.value.missing == {
        "ZZZZ": "FMP has no ZZZZ, or your FMP plan does not include it.",
        "TSLA": "FMP has no TSLA, or your FMP plan does not include it.",
    }


def test_a_range_without_prices_is_no_such_data(fake):
    with pytest.raises(NoSuchData) as exc:
        fake.adapter().daily_prices(ALICE, ["AAPL"], date(2023, 1, 1), date(2023, 6, 30))
    assert "No FMP prices for AAPL" in exc.value.missing["AAPL"]


@pytest.mark.parametrize("status", [503, 500, 429])
def test_outages_and_rate_limits_are_source_unavailable(fake, status):
    fake.status = status

    with pytest.raises(SourceUnavailable):
        fake.adapter().daily_prices(ALICE, ["AAPL"], FIRST_DAY, LAST_DAY)


def test_a_key_fmp_no_longer_accepts_asks_for_a_new_key(fake):
    fake.valid = set()

    with pytest.raises(KeyRequired) as exc:
        fake.adapter().daily_prices(ALICE, ["AAPL"], FIRST_DAY, LAST_DAY)
    assert exc.value.message == "FMP no longer accepts your saved key. Replace it in Settings."


def test_without_a_key_nothing_is_sent(fake):
    with pytest.raises(KeyRequired):
        fake.adapter().daily_prices(RequestContext.anonymous(), ["AAPL"], FIRST_DAY, LAST_DAY)
    assert fake.requests == []


def test_verify_key_accepts_a_valid_key_and_rejects_others(fake):
    adapter = fake.adapter()

    assert adapter.verify_key(KEY) is True
    assert adapter.verify_key("not-a-real-fmp-key") is False


def test_verify_key_raises_when_fmp_cannot_tell(fake):
    fake.status = 503

    with pytest.raises(SourceUnavailable):
        fake.adapter().verify_key(KEY)


def test_latest_close_is_the_newest_close_from_one_dateless_request(fake):
    when, close = fake.adapter().latest_close(ALICE, "MSFT")

    assert (when, close) == (LAST_DAY, pytest.approx(402.0))
    (request,) = fake.requests
    assert request.url.path == "/stable/historical-price-eod/full"
    assert "from" not in request.url.params and "to" not in request.url.params
    assert request.headers["apikey"] == KEY


def test_latest_close_for_an_unknown_or_premium_symbol_is_no_such_data(fake):
    fake.premium = {"TSLA"}
    adapter = fake.adapter()

    with pytest.raises(NoSuchData) as unknown:
        adapter.latest_close(ALICE, "ZZZZ")
    with pytest.raises(NoSuchData) as premium:
        adapter.latest_close(ALICE, "TSLA")

    assert unknown.value.missing == {"ZZZZ": "FMP has no ZZZZ, or your FMP plan does not include it."}
    assert premium.value.missing == {"TSLA": "FMP has no TSLA, or your FMP plan does not include it."}


NEW_YORK = ZoneInfo("America/New_York")


def _at(day: date, hour: int, minute: int = 0):
    moment = datetime(day.year, day.month, day.day, hour, minute, tzinfo=NEW_YORK).astimezone(UTC)
    return lambda: moment


def test_while_the_market_is_open_todays_partial_bar_is_left_out(fake):
    # LAST_DAY is a Monday; FMP already serves its row while it trades (seen live 2026-11-23).
    adapter = fake.adapter(now=_at(LAST_DAY, 11, 0))

    frame = adapter.daily_prices(ALICE, ["MSFT"], FIRST_DAY, LAST_DAY)["MSFT"]
    when, _close = adapter.latest_close(ALICE, "MSFT")

    assert frame.index[-1].date() == date(2024, 2, 9)
    assert when == date(2024, 2, 9)


def test_after_the_evening_settle_todays_bar_counts(fake):
    adapter = fake.adapter(now=_at(LAST_DAY, 18, 0))

    frame = adapter.daily_prices(ALICE, ["MSFT"], FIRST_DAY, LAST_DAY)["MSFT"]
    when, close = adapter.latest_close(ALICE, "MSFT")

    assert frame.index[-1].date() == LAST_DAY
    assert (when, close) == (LAST_DAY, pytest.approx(402.0))


def test_a_range_holding_only_todays_partial_bar_is_no_such_data(fake):
    with pytest.raises(NoSuchData) as exc:
        fake.adapter(now=_at(LAST_DAY, 11, 0)).daily_prices(ALICE, ["MSFT"], LAST_DAY, LAST_DAY)
    assert "No FMP prices for MSFT" in exc.value.missing["MSFT"]


def test_latest_close_without_a_key_sends_nothing(fake):
    with pytest.raises(KeyRequired):
        fake.adapter().latest_close(RequestContext(user_id=None, keys={}), "MSFT")
    assert fake.requests == []


def test_splits_since_a_date_come_oldest_first_as_new_shares_per_old_share(fake):
    adapter = fake.adapter()

    assert adapter.splits(ALICE, "AAPL", date(2014, 1, 1)) == [(date(2014, 6, 9), 7.0), (date(2024, 1, 30), 4.0)]
    assert adapter.splits(ALICE, "AAPL", FIRST_DAY) == [(date(2024, 1, 30), 4.0)]
    assert adapter.splits(ALICE, "AAPL", date(2024, 1, 31)) == []
    assert adapter.splits(ALICE, "MSFT", FIRST_DAY) == []
    request = fake.requests[-1]
    assert request.url.path == "/stable/splits"
    assert request.headers["apikey"] == KEY
    with pytest.raises(NoSuchData) as unknown:
        adapter.splits(ALICE, "ZZZZ", FIRST_DAY)
    assert set(unknown.value.missing) == {"ZZZZ"}
