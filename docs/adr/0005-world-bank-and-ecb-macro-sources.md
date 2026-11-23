# Macro beyond the US: World Bank WDI for country comparison, the ECB Data Portal for the euro area

**Status:** accepted (ticket #35). Terms checked on 2026-11-23.

The Macro Dashboard compares economies with three annual World Development Indicators (WDI) from the World Bank Indicators API v2 (`api.worldbank.org/v2`, no key): GDP growth (`NY.GDP.MKTP.KD.ZG`), consumer price inflation (`FP.CPI.TOTL.ZG`) and unemployment (`SL.UEM.TOTL.ZS`). Its euro area section shows the three key ECB interest rates and euro area HICP inflation from the ECB Data Portal SDMX API (`data-api.ecb.europa.eu/service/data`, no key).

## World Bank: CC BY 4.0, but only per indicator

Two World Bank documents disagree at first sight:

- The general site **Terms and Conditions** (https://www.worldbank.org/ext/en/legal/terms-conditions) allow only non-commercial use of "Materials" and say "you may not in any event use the APIs to facilitate commercial uses of the Materials".
- The **Terms of Use for Datasets** (https://www.worldbank.org/ext/en/legal/terms-conditions/datasets) say "Where these Dataset Terms conflict with the general Terms and Conditions, these Dataset Terms shall prevail". They license the datasets "Unless specifically labeled otherwise" under CC BY 4.0. They also state "You may use our application programming interfaces ('APIs') to facilitate access to the Datasets". The required attribution format is "The World Bank: Dataset name: Data source (if known)".

The Dataset Terms win for data, so WDI may be republished under CC BY 4.0. The Data Catalog entry for WDI lists "License: Creative Commons Attribution 4.0". The non-obvious part is the Dataset Terms' **"Exceptions for Some Third-Party Data"**: some indicators "may not be redistributed or reused without the consent of the original data provider", and "Where applicable, these conditions are included in the dataset or indicator metadata". Our CPI inflation indicator comes from the IMF's International Financial Statistics, and the spec keeps the IMF out because it requires permission for commercial use. Its WDI metadata (`/v2/sources/2/series/FP.CPI.TOTL.ZG/metadata`), however, says `License_Type: CC BY-4.0`. The same holds for GDP growth (national accounts, OECD) and unemployment (ILO modelled estimates). Because the World Bank labels the indicator CC BY 4.0, we rely on that label.

Each indicator therefore has two checks, in the same way FRED series do:

1. It must be on `CC_BY_INDICATORS` in `data/world_bank/adapter.py` (checked by hand, as above).
2. Its metadata must still say `License_Type: CC BY-4.0` at fetch time. If the label changes, the indicator becomes `NoSuchData` and only its cards go blank.

**What we show.** The footer's `world_bank` attribution reads "The World Bank: World Development Indicators (CC BY 4.0)" and links to the licence and the Dataset Terms. It also says the World Bank does not endorse Sextant, which the "No Endorsement" clause requires. Each indicator's meta block names the original data source (IMF, ILO, national accounts) together with the units, the frequency (Annual) and WDI's `lastupdated` date. Values are shown unmodified, rounded only for display. The site-wide "Not investment advice" notice covers the no-warranty clause. The API publishes no rate limit ("reasonable request volume"), so requests go one at a time. Every request fetches all 17 selectable economies, so changing the selection never hits the API again within the 24-hour TTL.

## ECB: own statistics free to reuse; HICP is Eurostat's

- The ECB statistics **reuse policy** (https://www.ecb.europa.eu/stats/ecb_statistics/governance_and_quality_framework/html/usage_policy.en.html) allows reuse free of charge "irrespective of any subsequent commercial or non-commercial use", provided that "the source is quoted (e.g. 'Source: ECB statistics.')" and that the statistics "are not modified". It "does not apply to third-party data without a prior permission from the originator".
- The ECB site's **Disclaimer & Copyright** (https://www.ecb.europa.eu/services/disclaimer/html/index.en.html) requires the same citation and accuracy. The ECB "accepts no responsibility or liability".
- The Data Portal API docs (https://data.ecb.europa.eu/help/api/overview) state no key, rate limit or further terms. The portal sits behind a bot wall that answers an HTML page to traffic it dislikes, for example wildcard keys. The adapter treats that page as `SourceUnavailable`.

The key rates (deposit facility `FM/B.U2.EUR.4F.KR.DFR.LEV`, main refinancing operations `…MRR_FR.LEV`, marginal lending facility `…MLFR.LEV`) are the ECB's own data. **Euro area HICP is not**: the portal labels it compiled by Eurostat, which makes it third-party data under the ECB policy. The originator's permission is Eurostat's copyright notice (https://ec.europa.eu/eurostat/web/main/help/copyright-notice): "Reuse of statistical data … for commercial or non-commercial purposes is authorised provided the source is acknowledged". Its non-commercial-only exception covers data for non-EU/EFTA countries, and the euro area is not one of them. The adapter allowlists exactly these four series (`ALLOWED_SERIES`).

**Series choice.** The ECB discontinued `ICP/M.U2.N.000000.4.ANR` in February 2026 (its last observation is 2025-12) and replaced it with `HICP/M.U2.N.000000.4D0.ANR`, which carries Eurostat's revised methodology. We use the new series. The key rates are published only on the dates they changed. The API turns each one into a step line and reports the date each rate took effect. The main refinancing rate series (`MRR_FR`, the fixed rate) has a gap from 2000-06 to 2008-10, when tenders were variable rate. The default history starts in 2015, so the gap doesn't show.

**What we show.** The footer's `ecb` attribution reads "Source: ECB statistics. Euro area HICP: Eurostat." and links to the ECB Data Portal and the reuse policy. Each series' meta block shows the compiler (European Central Bank, or Eurostat via the ECB), the units, the frequency and the response's `Last-Modified` time. The portal's data has no revision timestamp, so that header stands in for one.

## Considered options

- **FRED copies** of euro area series (e.g. `ECBDFR`). Rejected: each would need its own copyright tag check on FRED and a place on the public-domain allowlist, and the page would still owe the ECB its credit. Going to the source is simpler.
- **IMF or OECD** for the cross-country data. Out of scope per the spec: IMF needs permission for commercial use, and the OECD licence was not verified.
- **Eurostat's own API** for HICP. Same data and the same terms. The ECB portal serves the rates and HICP through one adapter.

## Consequences

- If a WDI indicator's metadata stops saying CC BY 4.0, its cards show "missing data" until someone re-checks it and updates the allowlist.
- If the ECB renames a series again, the adapter gets a 404 (`NoSuchData`) and only that card goes blank. Re-check the replacement's compiler before adding it.
- Revisit this ADR if either provider changes its terms.
