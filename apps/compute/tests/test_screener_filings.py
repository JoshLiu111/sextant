"""Latest SEC filings (P7) API on recorded feeds: the getcurrent Atom feed
(``fixtures/edgar/getcurrent/``, recorded 2026-11-23) and AAPL/MSFT submissions."""

from __future__ import annotations

from fastapi.testclient import TestClient

from main import app
from tests.data_fixtures import serving
from tests.edgar_fixtures import edgar_adapter, edgar_transport

client = TestClient(app)
PATH = "/api/compute/screener/filings"


def filings(body: dict | None = None, adapter=None):
    with serving(adapter or edgar_adapter(), "sec_edgar"):
        return client.post(PATH, json=body or {})


def test_market_wide_lists_the_newest_filings_with_links() -> None:
    res = filings()

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["scope"] == "market"
    assert body["company"] is None
    assert len(body["filings"]) == 40
    first = body["filings"][0]
    assert first == {
        "form": "SCHEDULE 13D/A",
        "title": "SCHEDULE 13D/A - George Matthew Spencer (0002117604) (Filed by)",
        "company": "George Matthew Spencer",
        "cik": 2117604,
        "filed": "2026-11-20",
        "accession": "0002117604-26-000001",
        "url": "https://www.sec.gov/Archives/edgar/data/2117604/000211760426000001/0002117604-26-000001-index.htm",
    }
    assert all(f["url"].startswith("https://www.sec.gov/Archives/edgar/data/") for f in body["filings"])
    assert body["meta"]["data_cutoff"] == "2026-11-20"


def test_market_wide_can_be_filtered_by_form() -> None:
    transport = edgar_transport()
    body = filings({"form": "10-K"}, adapter=edgar_adapter(transport)).json()

    assert len(body["filings"]) == 28
    assert {f["form"] for f in body["filings"]} == {"10-K", "10-K/A"}
    assert body["filings"][1]["title"] == "10-K - PTC INC. (0000857005) (Filer)"
    feed = next(r for r in transport.requests if r.url.path == "/cgi-bin/browse-edgar")
    assert feed.url.params["type"] == "10-K"
    assert feed.url.params["output"] == "atom"
    assert feed.headers["user-agent"] == "Sextant test admin@example.com"


def test_one_company_lists_its_own_filings_newest_first() -> None:
    body = filings({"ticker": " aapl "}).json()

    assert body["scope"] == "company"
    assert body["company"] == "Apple Inc."
    rows = body["filings"]
    assert len(rows) == 40
    assert rows[0]["form"] == "4"
    assert rows[0]["filed"] == "2026-11-19"
    assert rows[0]["accession"] == "0001140361-26-044952"
    assert rows[0]["url"] == (
        "https://www.sec.gov/Archives/edgar/data/320193/000114036126044952/0001140361-26-044952-index.htm"
    )
    dates = [r["filed"] for r in rows]
    assert dates == sorted(dates, reverse=True)
    assert {r["cik"] for r in rows} == {320193}


def test_one_company_filtered_by_form_names_the_filing() -> None:
    annual = filings({"ticker": "AAPL", "form": "10-K"}).json()["filings"]
    assert [(f["form"], f["filed"], f["title"]) for f in annual] == [("10-K", "2026-11-03", "10-K - Annual report")]
    assert annual[0]["url"].endswith("/000032019326000026/0000320193-26-000026-index.htm")

    current = filings({"ticker": "AAPL", "form": "8-K", "limit": 2}).json()["filings"]
    # Item 2.02 is an earnings release.
    assert [f["title"] for f in current] == [
        "8-K - Current report (Items 8.01, 9.01)",
        "8-K - Current report (Items 2.02, 9.01)",
    ]


def test_an_unknown_ticker_is_shown_on_the_ticker_field() -> None:
    res = filings({"ticker": "ZZZZ"})

    assert res.status_code == 422
    assert "Unknown ticker ZZZZ" in res.json()["error"]["fields"]["ticker"]


def test_an_unlisted_form_is_rejected() -> None:
    res = filings({"form": "NOPE"})

    assert res.status_code == 422
    assert res.json()["error"]["fields"] == {"form": "Choose one of the listed options."}


def test_feeds_are_cached_briefly() -> None:
    transport = edgar_transport()
    with serving(edgar_adapter(transport), "sec_edgar"):
        client.post(PATH, json={})
        client.post(PATH, json={})
        client.post(PATH, json={"ticker": "AAPL"})
        client.post(PATH, json={"ticker": "AAPL", "form": "10-K"})

    assert transport.paths().count("/cgi-bin/browse-edgar") == 1
    assert transport.paths().count("/submissions/CIK0000320193.json") == 1


def test_an_edgar_outage_is_a_503() -> None:
    res = filings(adapter=edgar_adapter(edgar_transport(status=503)))

    assert res.status_code == 503
    assert res.json()["error"]["code"] == "source_unavailable"
