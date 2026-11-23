"""Factor regressions on My data with a factor file the user uploaded (ADR 0003, #43).

Sextant ships no real factor data. A signed-in user uploads a Kenneth R. French
Data Library CSV they downloaded themselves; Sextant parses it, keeps it under
that user only (``user_factor_files``, cascade on account deletion) and
regresses their own tickers' prices on it.

Prices come from a user-scope ``FixtureAdapter`` registered as ``tiingo`` (the
recorded Tiingo responses cover only 30 days, too short for monthly
regressions); the Tiingo key check is ``FakeTiingo``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import psycopg
import pytest

from data_fixtures import FixtureAdapter
from sextant_compute.data.service import make_data_service
from sextant_compute.data.synthetic import SyntheticAdapter
from sextant_compute.envelope import DataSource
from sextant_compute.keys.api import get_tiingo
from tests.auth_helpers import bearer, sign_in
from tiingo_fixtures import FakeTiingo

RISK = "/api/compute/risk/metrics"
FILES = "/api/compute/risk/factor-files"
ALICE_KEY = "a1111111111111111111111111111111111111aaa"
BOB_KEY = "b2222222222222222222222222222222222222bbb"
TEST_KEY_SECRET = "test-provider-key-secret-not-for-production-0123456789"
TIINGO = DataSource(id="tiingo", name="Tiingo", is_demo=False)

# The made-up loadings the fund AAA is built with (monthly), the regression's oracle.
ALPHA_MONTHLY = 0.002
LOADINGS = {"Mkt-RF": 1.2, "SMB": 0.5, "HML": -0.3, "MOM": 0.4}
MONTHS = pd.period_range("2021-01", "2023-12", freq="M")  # 36 months of factors


def monthly_factors(seed: int = 7) -> pd.DataFrame:
    """Percent factors, two decimals, as the library publishes them."""
    rng = np.random.default_rng(seed)
    n = len(MONTHS)
    frame = pd.DataFrame(
        {
            "Mkt-RF": rng.normal(0.8, 4.5, n),
            "SMB": rng.normal(0.2, 3.0, n),
            "HML": rng.normal(0.3, 3.2, n),
            "RF": rng.uniform(0.0, 0.4, n),
            "MOM": rng.normal(0.5, 4.0, n),
        },
        index=MONTHS,
    )
    return frame.round(2)


def ken_french_csv(frame: pd.DataFrame, columns: list[str], *, annual: bool = True) -> str:
    """The library's CSV layout: description lines, a ``,col,col`` header,
    ``YYYYMM`` (or ``YYYYMMDD``) rows, an annual section and a copyright footer."""
    lines = [
        "This file was created by CMPT_ME_BEME_RETS using the 202412 CRSP database.",
        "The 1-month TBill rate data until 202405 are from Ibbotson Associates.",
        "",
        "," + ",".join(f"{c:>8}" for c in columns),
    ]
    for when, row in frame.iterrows():
        stamp = when.strftime("%Y%m") if isinstance(when, pd.Period) else when.strftime("%Y%m%d")
        lines.append(stamp + "," + ",".join(f"{row[c]:8.2f}" for c in columns))
    if annual:
        lines += ["", " Annual Factors: January-December ", "," + ",".join(columns)]
        lines += ["2021," + ",".join("   12.34" for _ in columns)]
    lines += ["", "Copyright 2024 Eugene F. Fama and Kenneth R. French", ""]
    return "\r\n".join(lines)


THREE_FACTOR = ["Mkt-RF", "SMB", "HML", "RF"]


def three_factor_file(frame: pd.DataFrame | None = None) -> dict[str, str]:
    frame = monthly_factors() if frame is None else frame
    return {"filename": "F-F_Research_Data_Factors.CSV", "csv": ken_french_csv(frame, THREE_FACTOR)}


def momentum_file(frame: pd.DataFrame | None = None) -> dict[str, str]:
    frame = (monthly_factors() if frame is None else frame).rename(columns={"MOM": "Mom   "})
    return {"filename": "F-F_Momentum_Factor.CSV", "csv": ken_french_csv(frame, ["Mom   "])}


def daily_closes(month_end_returns: pd.Series, start_close: float = 100.0) -> pd.DataFrame:
    """Business-day closes from 2020-12-01 whose month-end to month-end returns are
    ``month_end_returns`` (indexed by monthly Period); days inside a month move linearly."""
    days = pd.bdate_range("2020-12-01", "2023-12-29", name="date")
    month_end_close = {pd.Period("2020-12", "M"): start_close}
    level = start_close
    for month, r in month_end_returns.items():
        level *= 1 + r
        month_end_close[month] = level
    closes = []
    for day in days:
        month = day.to_period("M")
        last_bday = days[days.to_period("M") == month][-1]
        first_bday = days[days.to_period("M") == month][0]
        if month == pd.Period("2020-12", "M"):
            closes.append(start_close)
            continue
        prev, this = month_end_close[month - 1], month_end_close[month]
        span = max((last_bday - first_bday).days, 1)
        closes.append(prev + (this - prev) * ((day - first_bday).days / span if day != last_bday else 1.0))
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes, "volume": 1000, "dividend": 0.0},
        index=days,
    )


def fund_returns(factors_pct: pd.DataFrame, seed: int = 11) -> pd.Series:
    f = factors_pct / 100
    noise = np.random.default_rng(seed).normal(0, 0.004, len(f))
    excess = ALPHA_MONTHLY + sum(b * f[c] for c, b in LOADINGS.items()) + noise
    return f["RF"] + excess


def market_returns(factors_pct: pd.DataFrame) -> pd.Series:
    f = factors_pct / 100
    return f["Mkt-RF"] + f["RF"]


@pytest.fixture
def prices() -> FixtureAdapter:
    factors = monthly_factors()
    frames = {"AAA": daily_closes(fund_returns(factors)), "MKT": daily_closes(market_returns(factors))}
    return FixtureAdapter(frames, source=TIINGO, scope="user")


@pytest.fixture
def my_data(client, monkeypatch, prices) -> FakeTiingo:
    monkeypatch.setenv("PROVIDER_KEY_SECRET", TEST_KEY_SECRET)
    fake = FakeTiingo({ALICE_KEY, BOB_KEY})
    client.app.dependency_overrides[get_tiingo] = fake.adapter
    client.app.state.data_service = make_data_service(
        client.app.state.db, {"synthetic": SyntheticAdapter(), "tiingo": prices}
    )
    return fake


def user_with_key(client, name: str, key: str) -> dict[str, str]:
    headers = bearer(sign_in(client, f"sub-{name}", email=f"{name}@example.test"))
    saved = client.put("/api/compute/keys/tiingo", json={"key": key}, headers=headers)
    assert saved.status_code == 200, saved.text
    return headers


@pytest.fixture
def alice(client, my_data) -> dict[str, str]:
    return user_with_key(client, "alice", ALICE_KEY)


def upload(client, headers, file: dict[str, str]):
    return client.post(FILES, json=file, headers=headers)


def risk(client, headers, **changes):
    body = {"tickers": ["AAA"], "benchmark": "MKT", "start": "2020-12-01", "end": "2023-12-31", "source": "tiingo"}
    response = client.post(RISK, json={**body, **changes}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["metrics"]


def test_a_ken_french_monthly_file_is_parsed_and_saved_for_the_user(client, alice):
    response = upload(client, alice, three_factor_file())

    assert response.status_code == 200, response.text
    saved = response.json()
    assert {k: saved[k] for k in ("kind", "filename", "frequency", "first", "last", "periods", "columns")} == {
        "kind": "three_factor",
        "filename": "F-F_Research_Data_Factors.CSV",
        "frequency": "monthly",
        "first": "2021-01",
        "last": "2023-12",
        "periods": 36,  # the annual section and the footer are not data
        "columns": ["Mkt-RF", "SMB", "HML", "RF"],
    }
    listed = client.get(FILES, headers=alice).json()
    assert [f["kind"] for f in listed] == ["three_factor"]


def test_a_daily_file_and_a_momentum_file_are_read_too(client, alice):
    days = pd.DataFrame(
        {"Mkt-RF": [0.5, -0.25], "SMB": [0.1, 0.2], "HML": [-0.1, 0.0], "RF": [0.02, 0.02]},
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )
    daily = upload(client, alice, {"filename": "daily.csv", "csv": ken_french_csv(days, THREE_FACTOR, annual=False)})
    assert daily.status_code == 200, daily.text
    assert (daily.json()["frequency"], daily.json()["first"], daily.json()["last"]) == (
        "daily",
        "2024-01-02",
        "2024-01-03",
    )

    client.delete(f"{FILES}/three_factor", headers=alice)
    mom = upload(client, alice, momentum_file())
    assert mom.status_code == 200, mom.text
    assert (mom.json()["kind"], mom.json()["columns"], mom.json()["frequency"]) == ("momentum", ["MOM"], "monthly")


@pytest.mark.parametrize(
    ("csv", "message"),
    [
        ("PK\x03\x04\x14\x00garbage", "ZIP archive"),
        ("date,close\n2024-01-02,100\n", "Could not find a factor table"),
        (",Mkt-RF,SMB,HML,RF\nCopyright 2024\n", "no rows dated YYYYMM"),
        (",Alpha,Beta\n202401,1.0,2.0\n", "found Alpha, Beta"),
        (",Mkt-RF,SMB,HML,RF\n202401,1.0,2.0,3.0\n", "Line 2 has 3 values but the header names 4 columns"),
        (",Mkt-RF,SMB,HML,RF\n202413,1.0,2.0,3.0,0.1\n", "Line 2: 202413 is not a valid month"),
        (",Mkt-RF,SMB,HML,RF\n202401,1.0,2.0,3.0,0.1\n20240201,1.0,2.0,3.0,0.1\n", "mixes monthly"),
        (",Mkt-RF,SMB,HML,RF\n202401,1.0,x,3.0,0.1\n", "the SMB value 'x' is not a number"),
    ],
)
def test_an_unreadable_file_is_rejected_with_a_message_naming_the_problem(client, alice, csv, message):
    response = upload(client, alice, {"filename": "bad.csv", "csv": csv})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "unreadable_factor_file"
    assert message in error["fields"]["file"]
    assert client.get(FILES, headers=alice).json() == []


def test_the_3_factor_and_momentum_files_must_share_a_frequency(client, alice):
    assert upload(client, alice, three_factor_file()).status_code == 200
    days = pd.DataFrame({"MOM": [0.5, -0.25]}, index=pd.to_datetime(["2024-01-02", "2024-01-03"]))

    response = upload(client, alice, {"filename": "mom.csv", "csv": ken_french_csv(days, ["MOM"], annual=False)})

    assert response.status_code == 422
    assert "This momentum file is daily but your 3-factor file is monthly" in response.json()["error"]["message"]


def test_uploading_needs_a_signed_in_user(client, my_data):
    assert upload(client, None, three_factor_file()).status_code == 401
    assert client.get(FILES).status_code == 401


def test_monthly_factors_regress_month_end_returns_and_recover_the_loadings(client, alice):
    upload(client, alice, three_factor_file())
    upload(client, alice, momentum_file())

    metrics = risk(client, alice)

    for model, coefficients in {"ff3": ("market", "smb", "hml"), "carhart": ("market", "smb", "hml", "mom")}.items():
        for coefficient in coefficients:
            result = metrics[f"{model}_{coefficient}:AAA"]
            assert result["status"] == "ok", result
            assert result["details"]["factor_source"] == "user_upload"
        r2 = metrics[f"{model}_r_squared:AAA"]
        # Dec 2020 is the base month; Jan 2021..Dec 2023 are the 36 monthly returns.
        assert r2["details"]["observations"] == 36
        assert r2["details"]["period"] == "monthly"
    carhart = {c: metrics[f"carhart_{c}:AAA"]["value"] for c in ("market", "smb", "hml", "mom")}
    assert carhart == pytest.approx({"market": 1.2, "smb": 0.5, "hml": -0.3, "mom": 0.4}, abs=0.05)
    # Monthly alpha annualizes x12.
    assert metrics["carhart_alpha:AAA"]["value"] == pytest.approx(ALPHA_MONTHLY * 12, abs=0.015)
    # The market fund is Mkt-RF + RF, so it loads one for one on the market factor.
    assert metrics["ff3_market:MKT"]["value"] == pytest.approx(1.0, abs=1e-6)


def test_a_range_that_ends_mid_month_drops_the_partial_month(client, alice):
    upload(client, alice, three_factor_file())

    metrics = risk(client, alice, end="2023-12-15")

    assert metrics["ff3_r_squared:AAA"]["details"]["observations"] == 35


def test_a_monthly_file_regresses_monthly_whatever_return_period_is_chosen(client, alice):
    upload(client, alice, three_factor_file())

    metrics = risk(client, alice, period="weekly")

    r2 = metrics["ff3_r_squared:AAA"]["details"]
    assert (r2["period"], r2["observations"]) == ("monthly", 36)
    assert metrics["ff3_market:AAA"]["value"] == pytest.approx(1.2, abs=0.05)


def test_without_an_upload_the_factor_metrics_say_how_to_get_them(client, alice):
    metrics = risk(client, alice)

    reason = metrics["ff3_alpha:AAA"]["reason"]
    assert metrics["ff3_alpha:AAA"]["status"] == "missing_data"
    assert "upload a factor file" in reason
    # Risk metrics are untouched.
    assert metrics["annualized_volatility:AAA"]["status"] == "ok"


def test_a_3_factor_file_alone_gives_ff3_and_leaves_carhart_missing(client, alice):
    upload(client, alice, three_factor_file())

    metrics = risk(client, alice)

    assert metrics["ff3_smb:AAA"]["status"] == "ok"
    assert metrics["carhart_mom:AAA"]["status"] == "missing_data"
    assert "MOM" in metrics["carhart_mom:AAA"]["reason"]


def test_one_users_factors_are_never_seen_by_another_user_nor_cached(client, alice, db_url):
    bob = user_with_key(client, "bob", BOB_KEY)
    upload(client, alice, three_factor_file())

    assert risk(client, alice)["ff3_market:AAA"]["status"] == "ok"
    assert client.get(FILES, headers=bob).json() == []
    assert "until you upload a factor file" in risk(client, bob)["ff3_market:AAA"]["reason"]
    # Bob deleting "his" file leaves Alice's alone.
    assert client.delete(f"{FILES}/three_factor", headers=bob).status_code == 204
    assert [f["kind"] for f in client.get(FILES, headers=alice).json()] == ["three_factor"]

    assert len(client.app.state.data_service.shared_cache) == 0
    with psycopg.connect(db_url) as conn:
        datasets = {key.split(":")[4] for (key,) in conn.execute("SELECT cache_key FROM user_data_cache")}
    assert datasets <= {"daily_prices"}  # prices only; factors are read from the upload, never cached


def test_removing_the_file_removes_the_regressions(client, alice):
    upload(client, alice, three_factor_file())

    assert client.delete(f"{FILES}/three_factor", headers=alice).status_code == 204

    assert client.get(FILES, headers=alice).json() == []
    assert risk(client, alice)["ff3_market:AAA"]["status"] == "missing_data"


def test_demo_data_still_uses_the_synthetic_factors_after_an_upload(client, alice):
    upload(client, alice, three_factor_file())

    metrics = risk(client, alice, source="synthetic", tickers=["DEMO-H"], benchmark="DEMO-MKT")

    assert metrics["ff3_smb:DEMO-H"]["details"]["factor_source"] == "synthetic"


def test_a_file_that_does_not_overlap_the_price_range_is_rejected_with_both_ranges(client, alice):
    old = monthly_factors()
    old.index = pd.period_range("1926-07", periods=len(old), freq="M")
    upload(client, alice, three_factor_file(old))

    metrics = risk(client, alice)

    result = metrics["ff3_market:AAA"]
    assert result["status"] == "missing_data"
    assert result["reason"] == (
        "Your factor file covers 1926-07 to 1929-06, which does not overlap the price range 2020-12-01 to 2023-12-31."
    )
