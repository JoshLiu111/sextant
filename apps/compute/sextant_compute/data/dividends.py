"""A company's declared per-share dividends by period, provider-neutral."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Literal

from sextant_compute.data.statements import Company, Filing

PeriodKind = Literal["quarter", "year"]
Basis = Literal["declared", "paid"]


@dataclass(frozen=True)
class DividendPeriod:
    """One fiscal quarter or year. ``value`` is USD per share. ``derived`` marks a
    fourth quarter computed as the year less the first nine months (companies
    report Q4 only inside the annual report); ``filing`` is then the 10-K."""

    kind: PeriodKind
    label: str  # "FY2025", "Q3 FY2025"
    fiscal_year: int
    start: date
    end: date
    value: float
    filing: Filing
    tag: str  # "us-gaap:CommonStockDividendsPerShareDeclared"
    derived: bool = False


@dataclass(frozen=True)
class DividendHistory:
    """Newest first. ``basis`` is None (and ``periods`` empty) for a company whose
    filings report no per-share dividend."""

    company: Company
    basis: Basis | None
    periods: tuple[DividendPeriod, ...]

    def to_json(self) -> dict[str, Any]:
        def period(p: DividendPeriod) -> dict[str, Any]:
            raw = asdict(p)
            raw["start"], raw["end"] = p.start.isoformat(), p.end.isoformat()
            raw["filing"]["filed"] = p.filing.filed.isoformat()
            return raw

        return {"company": asdict(self.company), "basis": self.basis, "periods": [period(p) for p in self.periods]}

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> DividendHistory:
        def period(p: Mapping[str, Any]) -> DividendPeriod:
            filing = Filing(**{**p["filing"], "filed": date.fromisoformat(p["filing"]["filed"])})
            return DividendPeriod(
                **{
                    **p,
                    "start": date.fromisoformat(p["start"]),
                    "end": date.fromisoformat(p["end"]),
                    "filing": filing,
                }
            )

        return cls(
            company=Company(**raw["company"]),
            basis=raw["basis"],
            periods=tuple(period(p) for p in raw["periods"]),
        )
