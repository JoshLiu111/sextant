"""The World Bank adapter: ``country_indicator`` from the World Development
Indicators (WDI) through the Indicators API v2 on api.worldbank.org. No key.

Terms (ADR 0005): the World Bank's Terms of Use for Datasets license datasets
under CC BY 4.0 "unless specifically labeled otherwise", and say third-party
restrictions are stated in the indicator metadata. So an indicator must be on
``CC_BY_INDICATORS`` (each checked by hand) **and** its WDI metadata must say
``License_Type: CC BY-4.0`` when fetched; otherwise it is ``NoSuchData``.
Pages using the data credit "The World Bank: World Development Indicators:
<original source>" (web: the ``world_bank`` attribution and each chart's meta).

Requests: per indicator, one metadata request
(``/v2/sources/2/series/<ID>/metadata``) and one data request
(``/v2/country/<A;B;C>/indicator/<ID>?date=<from>:<to>``, more pages if
``pages`` > 1). No rate limit is published ("reasonable request volume"), so
requests go one at a time and 429/5xx are retried twice with backoff.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from sextant_compute.data.adapters import CountryIndicator, CountrySeries, Scope, SeriesMeta
from sextant_compute.data.context import RequestContext
from sextant_compute.data.errors import NoSuchData, SourceUnavailable
from sextant_compute.data.retry import get_with_retries
from sextant_compute.envelope import DataSource

WORLD_BANK = DataSource(id="world_bank", name="World Bank", is_demo=False)

BASE_URL = "https://api.worldbank.org"
WDI_SOURCE_ID = "2"
DATASET = "World Development Indicators"
CC_BY = "CC BY-4.0"
PER_PAGE = 1000
USER_AGENT = "Mozilla/5.0 (compatible; Sextant/0.1; open-source finance tools)"

ATTEMPTS = 3
BACKOFF = 1.0  # seconds, doubled per retry


@dataclass(frozen=True)
class AllowedIndicator:
    source: str
    """The original data provider, short form (WDI metadata "Source" is long)."""
    units: str


# WDI indicators whose metadata said License_Type "CC BY-4.0" on 2026-11-23.
CC_BY_INDICATORS: Mapping[str, AllowedIndicator] = {
    "NY.GDP.MKTP.KD.ZG": AllowedIndicator(
        "World Bank and OECD national accounts data", "Percent change from a year earlier (constant prices)"
    ),
    "FP.CPI.TOTL.ZG": AllowedIndicator(
        "International Monetary Fund, International Financial Statistics", "Percent change from a year earlier"
    ),
    "SL.UEM.TOTL.ZS": AllowedIndicator(
        "International Labour Organization, ILO modelled estimates", "Percent of total labor force"
    ),
}


class WorldBankAdapter:
    source = WORLD_BANK
    scope: Scope = "shared"
    # WDI is revised a few times a year; a day is plenty fresh.
    ttl = {"country_indicator": 24 * 3600}
    version = "1"

    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._sleep = sleep
        self._client = httpx.Client(transport=transport, timeout=20.0, headers={"User-Agent": USER_AGENT})

    @classmethod
    def from_env(cls) -> WorldBankAdapter:
        """``WORLD_BANK_BASE_URL`` (optional; e2e tests point it at a fake)."""
        return cls(base_url=os.environ.get("WORLD_BANK_BASE_URL") or BASE_URL)

    def country_indicator(
        self, ctx: RequestContext, indicator_id: str, countries: Sequence[str], start_year: int, end_year: int
    ) -> CountryIndicator:
        allowed = CC_BY_INDICATORS.get(indicator_id)
        if allowed is None:
            raise NoSuchData(
                WORLD_BANK.id,
                f"{indicator_id} is not on Sextant's list of CC BY 4.0 World Bank indicators.",
                {indicator_id: "Not a World Bank indicator Sextant may republish."},
            )
        fields = self._metadata(indicator_id)
        if fields.get("License_Type") != CC_BY:
            raise NoSuchData(
                WORLD_BANK.id,
                f"{indicator_id} is not licensed CC BY 4.0.",
                {indicator_id: f"World Bank lists its license as {fields.get('License_Type') or 'unknown'}."},
            )
        wanted = sorted({c.strip().upper() for c in countries})
        header, rows = self._data(indicator_id, wanted, start_year, end_year)

        by_country: dict[str, tuple[str, dict[int, float | None]]] = {}
        try:
            for row in rows:
                code = row["countryiso3code"]
                year = int(row["date"])
                if code not in wanted or not start_year <= year <= end_year:
                    continue
                value = row["value"]
                name, values = by_country.setdefault(code, (row["country"]["value"], {}))
                values[year] = None if value is None else float(value)
        except (KeyError, TypeError, ValueError) as exc:
            raise SourceUnavailable(WORLD_BANK.id, "World Bank returned unexpected data.") from exc

        meta = SeriesMeta(
            id=indicator_id,
            title=fields.get("IndicatorName") or indicator_id,
            source=allowed.source,
            units=allowed.units,
            frequency=fields.get("Periodicity") or "Annual",
            seasonal_adjustment="",
            last_updated=str(header.get("lastupdated") or ""),
        )
        return CountryIndicator(
            source=WORLD_BANK,
            meta=meta,
            countries={
                code: CountrySeries(code, by_country[code][0], sorted(by_country[code][1].items()))
                for code in wanted
                if code in by_country
            },
        )

    def _metadata(self, indicator_id: str) -> dict[str, str]:
        body = self._get_json(f"/v2/sources/{WDI_SOURCE_ID}/series/{indicator_id}/metadata", {"format": "json"})
        try:
            variable = body["source"][0]["concept"][0]["variable"][0]
            return {item["id"]: str(item["value"]) for item in variable["metatype"]}
        except (KeyError, IndexError, TypeError) as exc:
            raise SourceUnavailable(WORLD_BANK.id, "World Bank returned unexpected metadata.") from exc

    def _data(
        self, indicator_id: str, countries: Sequence[str], start_year: int, end_year: int
    ) -> tuple[Mapping[str, Any], list[Any]]:
        path = f"/v2/country/{';'.join(countries)}/indicator/{indicator_id}"
        params = {"format": "json", "date": f"{start_year}:{end_year}", "per_page": str(PER_PAGE)}
        rows: list[Any] = []
        page, pages = 1, 1
        header: Mapping[str, Any] = {}
        while page <= pages:
            body = self._get_json(path, params if page == 1 else {**params, "page": str(page)})
            if isinstance(body, list) and body and isinstance(body[0], dict) and "message" in body[0]:
                raise NoSuchData(
                    WORLD_BANK.id,
                    f"World Bank has no indicator {indicator_id}.",
                    {indicator_id: "Unknown World Bank indicator."},
                )
            try:
                header, chunk = body[0], body[1] or []
                pages = int(header.get("pages") or 1)
            except (IndexError, KeyError, TypeError, ValueError) as exc:
                raise SourceUnavailable(WORLD_BANK.id, "World Bank returned unexpected data.") from exc
            rows.extend(chunk)
            page += 1
        return header, rows

    def _get_json(self, path: str, params: Mapping[str, str]) -> Any:
        url = f"{self._base_url}{path}"
        try:
            response = get_with_retries(
                lambda: self._client.get(url, params=params), attempts=ATTEMPTS, backoff=BACKOFF, sleep=self._sleep
            )
        except httpx.HTTPError as exc:
            raise SourceUnavailable(WORLD_BANK.id, f"World Bank request failed ({type(exc).__name__}).") from None
        if response.status_code != 200:
            raise SourceUnavailable(WORLD_BANK.id, f"World Bank answered HTTP {response.status_code}.")
        try:
            return response.json()
        except ValueError:
            raise SourceUnavailable(WORLD_BANK.id, "World Bank returned something other than JSON.") from None
