# Factors: demo mode uses synthetic factors; real factor data only comes from the user's own upload

**Status:** accepted (ticket #26). Terms checked on 2026-11-22.

Fama-French 3-factor and Carhart 4-factor regressions in Risk & Performance work in two ways:

- **Demo data.** The deterministic synthetic generator also produces a set of factor series (Mkt-RF, SMB, HML, MOM, RF). Some demo tickers are built with known loadings on those factors, so the regression recovers them and the known loadings double as test oracles. Regressing synthetic tickers on real factors would show nothing (loadings and R² near zero), because the synthetic prices have no relationship to real market history.
- **My data.** Sextant ships no real factor data. A signed-in user who wants real-factor regressions on their own tickers uploads a factor file they downloaded themselves (e.g. from the Kenneth R. French Data Library). Sextant computes with it for that user only. It is shown only to that user, never goes into the shared cache, and is stored, if at all, under that user (cascade convention).

**Why Sextant does not fetch or display real factors itself.** On 2026-11-22 we checked the primary sources:

- The Kenneth R. French Data Library (https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html) and the factor CSVs carry only "Copyright 2026 Eugene F. Fama and Kenneth R. French". The pages' HTML source also has a hidden comment: "All images and code are property of Ken French. Use in part or whole is illegal -- except by permission of Ken French or Dimensional Fund Advisors". None of these pages or files states a licence, terms of use, redistribution permission or citation request, and no Tuck or Dartmouth terms cover them. Silence is not permission.
- The factors are built from CRSP data, which comes under its own commercial licence. The T-bill rate comes from Ibbotson Associates and ICE BofA. Permission from Fama and French alone would not settle third-party rights.
- AQR's data sets, the obvious alternative, are explicitly restricted (https://www.aqr.com/Terms-of-Use): "You may not reproduce, modify, copy, alter in any way, distribute, sell, resell, transmit, transfer, license, assign or publish any information obtained from this Website without AQR's express prior written consent."

The spec's rule is that a data source whose terms we cannot verify is not connected. User-supplied factors follow the same reasoning as bring-your-own price keys: the user obtains the data under their own relationship with the provider, and Sextant only computes for that user.

## Considered options

- **Fetch the Ken French factors and show them publicly.** Rejected: there is no grant of permission, and CRSP rights sit underneath.
- **Ask Ken French for written permission.** Not pursued: it would not cover the CRSP and ICE inputs.
- **Build our own factors from EDGAR fundamentals plus prices.** Rejected: public display needs prices, which no free source allows us to republish, and the factor construction is a project in itself.

## Consequences

- Visitors see factor regressions on demo data only, with the Demo badge.
- The upload path has to parse the Ken French CSV layout (monthly and daily files, percent units, header and footer text) and reject files it cannot read with a clear error. Built in #43: uploads are stored per user in `user_factor_files` (cascades on account deletion), read per request and never cached.
- If the library ever publishes a licence that permits public display, revisit this ADR.
