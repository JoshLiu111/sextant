# Reporting currency: every amount converts at the rate of its own date (Frankfurter)

**Status:** accepted (ticket #30).

A saved portfolio may hold and trade in several currencies. The user picks a reporting currency per analysis (`reporting_currency` on `POST /portfolios/{id}/metrics` and `/returns`; default: the first holding's currency), and every amount is shown in it.

We decided:

- **Source: Frankfurter v2 blended rates** (`GET /v2/rates?from&to&base&quotes`), fetched per currency pair and calendar year and kept in the shared cache. Free, no key, commercial use allowed; blended rates are Frankfurter's own calculation, so central-bank terms do not carry over; credit is appreciated, so the My Portfolio footer says "Exchange rates: Frankfurter (frankfurter.dev)." (terms checked on frankfurter.dev on 2026-11-22). v1 is deprecated.
- **Each amount at the rate of its own date, never today's.** A daily value converts at that day's rate (so the value series, the risk metrics and the returns include currency moves). Market value converts at the last close's date. A lot's cost converts at the date the lot was opened. A sell's booked realized P&L (ADR 0004, in the trade's currency) converts at the sell date. A trade's cash converts at its trade date. A date without a rate uses the last rate on or before it.
- **Lots carry their open date.** An imported buy's lot is dated with its trade date. A holding entered or changed by hand is one lot dated with the day it was saved. We do not know when those shares were bought, and the day the user stated their cost is the closest date we have. Lots stored before this ADR have no date, and they convert at the portfolio's creation date.
- **An unsupported currency is `missing_data`, not a request error.** It covers what needs that currency (the position's amounts, totals, weights, the portfolio's risk metrics and chart, the returns), and the reason names the currency. A Frankfurter outage is still a 503. The old 422 `mixed_currencies` is gone.

## Considered options

- **Convert everything at the end date's rate.** Rejected: the ticket asks for historical rates, and the currency's own return would vanish from the value series and returns.
- **Realized P&L as proceeds at the sell date's rate minus cost at the buy date's rate.** More exact in the reporting currency, but it would recompute booked P&L, which ADR 0004 rules out. We convert the booked amount at the sell date instead. So realized + unrealized in the reporting currency can differ slightly from the cash result when rates moved between buy and sell.
- **Ask for a purchase date on hand-entered holdings.** Better data, but more input for every holding. We can add it later: the lot date is already the field that would hold it.

## Consequences

- Cost basis of a hand-entered foreign holding depends on the day it was saved. Re-saving it with a changed quantity, cost or currency re-dates it. A rename keeps it.
- Positions are shown in the reporting currency only. The holding's own currency is not shown next to its amounts yet.
- The benchmark is not converted. Demo tickers have no currency of their own.
