"""Lists of SEC filings (latest market-wide, or one company's), provider-neutral."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class FilingEntry:
    form: str  # "10-K", "8-K", "4", "SCHEDULE 13D/A", ...
    title: str
    company: str
    cik: int
    filed: date
    accession: str
    url: str  # the filing index page on sec.gov


@dataclass(frozen=True)
class FilingList:
    """Newest first. ``company`` is set for a one-company list (its SEC name)."""

    filings: tuple[FilingEntry, ...]
    company: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "company": self.company,
            "filings": [{**asdict(f), "filed": f.filed.isoformat()} for f in self.filings],
        }

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> FilingList:
        return cls(
            company=raw["company"],
            filings=tuple(FilingEntry(**{**f, "filed": date.fromisoformat(f["filed"])}) for f in raw["filings"]),
        )
