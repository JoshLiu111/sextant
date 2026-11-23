# FRED: a series a visitor picks is served only if FRED tags it public domain and its notes have no copyright

**Status:** accepted (ticket #36). FRED docs checked on 2026-11-22.

Visitors can search FRED and add any series to the Macro Dashboard (spec story 78), but Sextant may republish only public-domain FRED series (story 94). The FRED API Terms of Use say series "may be owned by third parties and subject to copyright restrictions", and that "copyrighted series contain the word 'Copyright' in their notes". The spec therefore excludes series whose notes carry a copyright notice. That check alone lets some copyrighted series through. T10Y2Y is tagged "Copyrighted: Citation Required" and its notes never say "Copyright" (sextant-notes research/fred.md). The hand-checked allowlist from ticket #11 cannot cover series that visitors choose.

**Decision.** A series must pass two checks:

1. Its metadata notes (`/fred/series`) must not contain "copyright", in any case. This check runs first, for every series, allowlisted ones included.
2. It must either be on `PUBLIC_DOMAIN_SERIES`, the headline series whose tags were checked by hand, or carry FRED's status tag `public domain: citation requested` (group `cc`) in `/fred/series/tags`. The other two status tags are "copyrighted: citation required" and "copyrighted: pre-approval required". The tag exists on the FRED site and covers about 620,000 series.

A series that fails either check is `NoSuchData`, so its metric is `missing_data` with the reason given. Its data is never fetched. Search (`/fred/series/search`) sends `tag_names=public domain: citation requested`, so FRED returns only public-domain series. Sextant also drops any hit whose notes mention a copyright. Search results are only offers: adding a series runs both checks again.

The publishing agency shown as the series' source comes from the series' `src` tags, using the tag notes without the " (source)" suffix, e.g. "U.S. Bureau of Labor Statistics". For allowlisted series it comes from the allowlist, as before.

## Considered options

- **Notes check only (the spec's wording).** Rejected: it lets T10Y2Y and similar series through.
- **Grow the hand-checked allowlist.** Rejected: visitors can choose any of FRED's series.
- **Release sources (`/fred/series/release` + `/fred/release/sources`) for the agency.** Rejected: that is two extra requests per series. A single tags request gives both the status and the source.

## Consequences

- A non-allowlisted series costs 3 FRED requests on a cold cache (metadata, tags, observations), about 1.5 s at the 2 requests/second throttle. Search costs 1 request and is cached for 24 hours per query.
- The checks depend on FRED tagging series correctly. If FRED renames the status tag, every chosen series becomes `missing_data`, which fails closed, and search returns nothing. The tag name was not verified against the live API, because no key was available when this was written. Verify it once with a real key on a preview: search "payroll" should offer PAYEMS.
