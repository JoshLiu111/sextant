"""Per-share dividends from a companyfacts body (``DividendHistory``).

Rules:

- The first tag in ``DIVIDEND_TAGS`` with any fact wins for the whole company
  (declared before paid), so the history has one basis.
- Only 10-K and 10-Q family facts with a duration count. Among duplicates for
  the same (start, end) the earliest filed wins ("as first reported").
- Years span ``ANNUAL_DAYS``; quarters ``QUARTER_DAYS``. Nine-month year-to-date
  facts are used only to derive the fourth quarter (year less nine months),
  because companies report Q4 only inside the annual report.
- Fiscal year number: the year the period ends in, except a year ending in the
  first week of January counts as the year before (52/53-week calendars).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sextant_compute.data.dividends import Basis, DividendHistory, DividendPeriod
from sextant_compute.data.edgar.standardize import filing_url
from sextant_compute.data.statements import Company, Filing

# (taxonomy:tag, basis), in priority order.
DIVIDEND_TAGS: tuple[tuple[str, Basis], ...] = (
    ("us-gaap:CommonStockDividendsPerShareDeclared", "declared"),
    ("us-gaap:CommonStockDividendsPerShareCashPaid", "paid"),
)
UNIT = "USD/shares"
FORMS = frozenset({"10-K", "10-K/A", "10-KT", "10-KT/A", "10-Q", "10-Q/A"})
ANNUAL_DAYS = range(335, 396)
QUARTER_DAYS = range(70, 112)
NINE_MONTH_DAYS = range(250, 290)
SLACK = timedelta(days=7)  # fiscal calendars drift by a few days


@dataclass(frozen=True)
class _Fact:
    start: date
    end: date
    value: float
    filing: Filing

    @property
    def days(self) -> int:
        return (self.end - self.start).days


def _facts(body: dict[str, Any], tag: str, cik: int) -> list[_Fact]:
    taxonomy, name = tag.split(":")
    rows = body.get("facts", {}).get(taxonomy, {}).get(name, {}).get("units", {}).get(UNIT, [])
    first: dict[tuple[date, date], _Fact] = {}
    for row in rows:
        try:
            if row.get("form") not in FORMS or "start" not in row:
                continue
            fact = _Fact(
                start=date.fromisoformat(row["start"]),
                end=date.fromisoformat(row["end"]),
                value=float(row["val"]),
                filing=Filing(
                    accession=row["accn"],
                    form=row["form"],
                    filed=date.fromisoformat(row["filed"]),
                    url=filing_url(cik, row["accn"]),
                ),
            )
        except (KeyError, TypeError, ValueError):
            continue
        key = (fact.start, fact.end)
        if key not in first or fact.filing.filed < first[key].filing.filed:
            first[key] = fact
    return sorted(first.values(), key=lambda f: (f.end, f.start))


def fiscal_year_of(end: date) -> int:
    return end.year - 1 if end.month == 1 and end.day <= 7 else end.year


def dividend_history(body: dict[str, Any], company: Company) -> DividendHistory:
    for tag, basis in DIVIDEND_TAGS:
        facts = _facts(body, tag, company.cik)
        if facts:
            return DividendHistory(company=company, basis=basis, periods=tuple(_periods(facts, tag)))
    return DividendHistory(company=company, basis=None, periods=())


def _periods(facts: list[_Fact], tag: str) -> list[DividendPeriod]:
    years = [f for f in facts if f.days in ANNUAL_DAYS]
    quarters = [f for f in facts if f.days in QUARTER_DAYS]
    nine_months = [f for f in facts if f.days in NINE_MONTH_DAYS]

    def year_of(q: _Fact) -> tuple[int, int] | None:
        """(fiscal year, quarter number) for a quarter, from the fiscal years around it."""
        for y in years:
            if y.start - SLACK <= q.start and q.end <= y.end + SLACK:
                return fiscal_year_of(y.end), _quarter_number(y.start, q.end)
        before = [y for y in years if y.end <= q.start + SLACK]
        if before:
            last = before[-1]
            n = _quarter_number(last.end + timedelta(days=1), q.end)
            if 1 <= n <= 4:
                return fiscal_year_of(last.end) + 1, n
        return None

    out: list[DividendPeriod] = []
    for y in years:
        fy = fiscal_year_of(y.end)
        out.append(DividendPeriod("year", f"FY{fy}", fy, y.start, y.end, y.value, y.filing, tag))
    seen: set[tuple[int, int]] = set()
    for q in quarters:
        where = year_of(q)
        if where is None:
            label, fy = f"Quarter ended {q.end.isoformat()}", q.end.year
        else:
            fy, n = where
            seen.add(where)
            label = f"Q{n} FY{fy}"
        out.append(DividendPeriod("quarter", label, fy, q.start, q.end, q.value, q.filing, tag))
    for y in years:
        fy = fiscal_year_of(y.end)
        if (fy, 4) in seen:
            continue
        nine = next((n for n in nine_months if abs((n.start - y.start).days) <= SLACK.days and n.end < y.end), None)
        if nine is None:
            continue
        value = round(y.value - nine.value, 6)
        start = nine.end + timedelta(days=1)
        out.append(DividendPeriod("quarter", f"Q4 FY{fy}", fy, start, y.end, value, y.filing, tag, derived=True))
    out.sort(key=lambda p: (p.end, p.kind == "year"), reverse=True)
    return out


def _quarter_number(year_start: date, quarter_end: date) -> int:
    return max(1, round((quarter_end - year_start).days / 91.3))
