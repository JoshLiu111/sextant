# Rates: the yield curve and 10Y-2Y spread come from the US Treasury par yield curve CSV

**Status:** accepted (ticket #12). Terms checked on 2026-11-22.

The Macro Dashboard's yield curve and its 10Y-2Y term spread history both come from the US Treasury's **Daily Treasury Par Yield Curve Rates**, fetched as one CSV per calendar year from `home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/<year>/all?type=daily_treasury_yield_curve&field_tdr_date_value=<year>&page&_format=csv` (no key). Sextant computes the spread itself as the 10-year minus the 2-year par yield. Inversion periods are runs of days with a spread below zero. A day missing either yield neither starts nor ends a run.

**Why it may be republished.** These rates are produced by a federal agency as part of its official duties, which makes them a US Government work. Under 17 U.S.C. §105, US Government works are not subject to copyright. On 2026-11-22 we re-checked every Treasury page that might carry terms. None states a copyright, licence, terms of use, rate limit or attribution requirement for the data:

- the feed documentation, https://home.treasury.gov/treasury-daily-interest-rate-xml-feed
- Site Policies and Notices, https://home.treasury.gov/subfooter/site-policies-and-notices
- Privacy Policy (the footer's "Privacy and Legal Notices" link), https://home.treasury.gov/subfooter/privacy-policy

The only legal text is in the Privacy Policy's disclaimers. Treasury "does not endorse any commercial product, service, process, or enterprise". It also "makes no warranty, express or implied" and "assumes no legal liability or responsibility for the accuracy, completeness, or usefulness of any information". The spec flagged the Treasury terms as unverified (spec, last section). This ADR records that check. The yields come from market quotes that the New York Fed collects, and none of the pages above mentions a third-party claim on them.

**What we show.** The macro page footer carries the `treasury` attribution: "Source: U.S. Department of the Treasury, Daily Treasury Par Yield Curve Rates. Not endorsed by the U.S. Treasury." It links to Treasury's yield curve page. Next to each rates chart, the page shows the source, the units (Percent, or Percentage points for the spread), the frequency (Daily, business days), the latest date and when Sextant last fetched the data. Treasury publishes no revision timestamp, so the fetch time is the "last updated" value. The site-wide "Not investment advice" notice covers the no-warranty disclaimer.

## Considered options

- **FRED `T10Y2Y`** for the spread. Rejected: FRED tags it "Copyrighted: Citation Required", so we may not republish it (see the FRED allowlist in `data/fred/adapter.py`).
- **FRED `DGS*` series** (public domain) for the curve and `DGS10 − DGS2` for the spread. Rejected as the primary source. It needs a key and is rate limited to 2 requests per second, which means about 22 requests for a full curve on a cold cache. FRED has no 1.5-, 2- or 4-month tenors, and pages using it must also show FRED's notice. It is still a fallback if we ever need history before 1990: DGS10 starts in 1962 and DGS2 in 1976.
- **Treasury XML (OData) feed.** Same data and same terms. The CSV is simpler to parse, and one request per year returns every tenor.

## Consequences

- The CSV's columns change over the years: `4 Mo` was added in late 2022 and `1.5 Month` in 2025. The adapter therefore parses columns by header name. A year with no data yet returns an empty body. The cache holds one entry per year (TTL 6 hours). The default spread history starts in 2018, so a cold cache costs about 9 requests.
- No rate limit is published. The adapter sends its requests one at a time and retries a 429 or 5xx twice with backoff.
- If Treasury ever publishes terms for this data, revisit this ADR.
