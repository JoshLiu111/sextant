"""Statements -> the ``Year`` chain the ratio analytics read, annual or quarterly.

Annual: each fiscal year's reported values; ``prior`` (averages, opening
balances) and ``earlier`` (year-over-year models) are the fiscal year before.

Quarterly: ratios are trailing twelve months (TTM). Flows are the sum of the
four quarters to the quarter end; balances are the quarter end; ``prior`` and
``earlier`` are the same quarter a year before. So a TTM ratio at Q4 equals the
fiscal-year ratio. Per-share amounts add up too (TTM EPS = the four quarterly
EPS); weighted-average share counts don't, so they use the quarter's own.

``inputs`` turns a ``Trace`` of a ratio's reads into the statement cells (and
their filings) behind each input: one cell, or a TTM flow's four quarters.
"""

from __future__ import annotations

from dataclasses import dataclass

from sextant_compute.analytics.ratios import PeriodValues, Trace, Year
from sextant_compute.data.statements import FinancialStatements, FiscalPeriod, Frequency, Missing, Reported

TTM_QUARTERS = 4


def _key(p: FiscalPeriod) -> int:
    return p.fiscal_year * 4 + (p.fiscal_quarter or 0)


@dataclass(frozen=True)
class Source:
    """One statement cell behind an input."""

    period: FiscalPeriod
    cell: Reported | Missing


@dataclass(frozen=True)
class Input:
    item_id: str
    label: str
    period: FiscalPeriod
    value: float | None
    reason: str | None  # why the value is missing
    ttm: bool  # a trailing-twelve-month sum of ``sources``
    sources: list[Source]


class Periods:
    """One company's ``Year`` chain for ``frequency``; see the module docstring."""

    def __init__(
        self,
        statements: FinancialStatements,
        frequency: Frequency,
        price: float | None = None,
        trace: Trace | None = None,
    ) -> None:
        self.statements = statements
        self.frequency = frequency
        self.flows = {i.id for i in statements.items if i.statement != "balance"}
        self._summed = {i.id for i in statements.items if i.statement != "balance" and i.unit != "shares"}
        periods = statements.periods
        index = {_key(p): i for i, p in enumerate(periods)}
        labels = {item.id: item.label for item in statements.items}
        self.values = [self._values(i) for i in range(len(periods))]
        self.years: list[Year] = []
        for i, p in enumerate(periods):
            j = (i - 1 if i > 0 else None) if frequency == "annual" else index.get(_key(p) - TTM_QUARTERS)
            self.years.append(
                Year(
                    self.values[i],
                    self.values[j] if j is not None else None,
                    labels,
                    is_latest=i == len(periods) - 1,
                    price=price,
                    earlier=self.years[j] if j is not None else None,
                    trace=trace,
                )
            )

    def ttm(self, item_id: str) -> bool:
        """Whether quarterly ratios read ``item_id`` as a trailing-twelve-month sum."""
        return self.frequency == "quarterly" and item_id in self._summed

    def window(self, i: int) -> list[FiscalPeriod] | None:
        """The four quarters to period ``i`` (oldest first), or None if the data lacks one."""
        periods = self.statements.periods
        if i < TTM_QUARTERS - 1:
            return None
        window = list(periods[i - TTM_QUARTERS + 1 : i + 1])
        if _key(window[-1]) - _key(window[0]) != TTM_QUARTERS - 1:
            return None
        return window

    def _values(self, i: int) -> PeriodValues:
        p = self.statements.periods[i]
        values: dict[str, float] = {}
        missing: dict[str, str] = {}
        for item in self.statements.items:
            cell = self.statements.cell(item.id, p.id)
            if not self.ttm(item.id):
                if isinstance(cell, Missing):
                    missing[item.id] = cell.message
                else:
                    values[item.id] = cell.value
                continue
            window = self.window(i)
            if window is None:
                missing[item.id] = (
                    f"Trailing twelve months of {item.label} need the four quarters to {p.label}, "
                    "and the data has fewer."
                )
                continue
            cells = [self.statements.cell(item.id, q.id) for q in window]
            gap = next((c for c in cells if isinstance(c, Missing)), None)
            if gap is not None:
                missing[item.id] = f"Trailing twelve months to {p.label}: {gap.message}"
            else:
                values[item.id] = sum(c.value for c in cells if isinstance(c, Reported))
        return PeriodValues(label=p.label, values=values, missing=missing, period_id=p.id)

    def inputs(self, trace: Trace) -> list[Input]:
        by_id = {p.id: i for i, p in enumerate(self.statements.periods)}
        out = []
        for period_id, item_id in trace.unique():
            i = by_id[period_id]
            p = self.statements.periods[i]
            values = self.values[i]
            ttm = self.ttm(item_id)
            window = self.window(i) if ttm else [p]
            out.append(
                Input(
                    item_id=item_id,
                    label=self.statements.item(item_id).label,
                    period=p,
                    value=values.values.get(item_id),
                    reason=values.missing.get(item_id),
                    ttm=ttm,
                    sources=[Source(q, self.statements.cell(item_id, q.id)) for q in window or []],
                )
            )
        return out
