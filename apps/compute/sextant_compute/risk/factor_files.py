"""Reading a factor file a user uploaded: the Kenneth R. French Data Library CSV layout.

The library's files look like this (``F-F_Research_Data_Factors.CSV``)::

    This file was created by CMPT_ME_BEME_RETS using the 202412 CRSP database.
    The 1-month TBill rate data until 202405 are from Ibbotson Associates.

    ,Mkt-RF,SMB,HML,RF
    192607,    2.89,   -2.55,   -2.39,    0.22
    ...

     Annual Factors: January-December
    ,Mkt-RF,SMB,HML,RF
    1927,   29.47,   -2.46,   -3.75,    3.12
    ...
    Copyright 2024 Eugene F. Fama and Kenneth R. French

Rules: the first row whose first cell is empty and whose other cells are names
is the header; the rows right after it whose first cell is ``YYYYMM`` (monthly)
or ``YYYYMMDD`` (daily) are the table, which ends at the first other row (so
the annual section and the footer are ignored). Values are percent; ``-99.99``
and ``-999`` mark missing values. The momentum file (``F-F_Momentum_Factor``)
has one column, ``Mom``. Other columns (the 5-factor file's RMW, CMA) are dropped.

Pure: text in, a ``FactorFile`` (decimal factors) out, or ``FactorFileUnreadable``
with a message for the user.
"""

from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass
from datetime import date
from typing import Literal

import pandas as pd

Frequency = Literal["daily", "monthly"]
Kind = Literal["three_factor", "momentum"]

THREE_FACTOR_COLUMNS = ("Mkt-RF", "SMB", "HML", "RF")
MOMENTUM = "MOM"
_KNOWN = {"MKT-RF": "Mkt-RF", "SMB": "SMB", "HML": "HML", "RF": "RF", "MOM": MOMENTUM}
_MISSING_MARKERS = (-99.99, -999.0)
PERIODS_PER_YEAR: dict[Frequency, int] = {"daily": 252, "monthly": 12}

_LAYOUT_HINT = (
    "Upload a CSV from the Kenneth R. French Data Library, such as F-F_Research_Data_Factors.CSV "
    "(monthly) or F-F_Research_Data_Factors_daily.CSV, plus F-F_Momentum_Factor.CSV for Carhart."
)


class FactorFileUnreadable(ValueError):
    """The file is not a factor table Sextant can read; ``message`` says why."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class FactorFile:
    kind: Kind
    frequency: Frequency
    frame: pd.DataFrame
    """Decimal factors indexed by date (month ends for monthly files), NaN where missing."""


def _is_header(cells: list[str]) -> bool:
    names = cells[1:]
    return len(cells) >= 2 and cells[0] == "" and all(names) and not any(_is_number(c) for c in names)


def _is_number(cell: str) -> bool:
    try:
        float(cell)
    except ValueError:
        return False
    return True


def _is_date_cell(cell: str) -> bool:
    return cell.isdigit() and len(cell) in (6, 8)


def _parse_date(cell: str, line: int) -> date:
    try:
        if len(cell) == 6:
            year, month = int(cell[:4]), int(cell[4:])
            return (pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0)).date()
        return date(int(cell[:4]), int(cell[4:6]), int(cell[6:]))
    except ValueError:
        what = "month (YYYYMM)" if len(cell) == 6 else "date (YYYYMMDD)"
        raise FactorFileUnreadable(f"Line {line}: {cell} is not a valid {what}.") from None


def _value(cell: str, line: int, column: str) -> float:
    try:
        v = float(cell)
    except ValueError:
        raise FactorFileUnreadable(f"Line {line}: the {column} value {cell!r} is not a number.") from None
    if not math.isfinite(v) or any(abs(v - m) < 1e-9 for m in _MISSING_MARKERS):
        return math.nan
    return v / 100


def parse_factor_file(text: str) -> FactorFile:
    if text.startswith("PK"):
        raise FactorFileUnreadable("This looks like a ZIP archive. Unzip it and upload the CSV inside.")
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    cells = [[c.strip() for c in row] for row in rows]
    start = next((i for i, row in enumerate(cells) if _is_header(row)), None)
    if start is None:
        raise FactorFileUnreadable(f"Could not find a factor table (a header row like ',Mkt-RF,SMB,HML,RF'). {_LAYOUT_HINT}")
    header = cells[start]
    names = [_KNOWN.get(n.upper()) for n in header[1:]]
    found = [n for n in names if n]
    has_three = all(c in found for c in THREE_FACTOR_COLUMNS)
    if not has_three and MOMENTUM not in found:
        raise FactorFileUnreadable(
            f"The factor table has none of the columns Sextant regresses on (found {', '.join(header[1:])}). "
            f"A 3-factor file needs Mkt-RF, SMB, HML and RF; a momentum file needs Mom. {_LAYOUT_HINT}"
        )

    dates: list[date] = []
    values: list[list[float]] = []
    for offset, row in enumerate(cells[start + 1 :]):
        line = start + 2 + offset
        if not row or not _is_date_cell(row[0]):
            break
        if len(row) != len(header):
            raise FactorFileUnreadable(
                f"Line {line} has {len(row) - 1} values but the header names {len(header) - 1} columns."
            )
        if len(row[0]) != len(cells[start + 1][0]):
            raise FactorFileUnreadable(f"Line {line}: the table mixes monthly (YYYYMM) and daily (YYYYMMDD) dates.")
        dates.append(_parse_date(row[0], line))
        values.append([_value(c, line, header[1 + j]) for j, c in enumerate(row[1:])])
    if not dates:
        raise FactorFileUnreadable(
            f"The factor table has a header but no rows dated YYYYMM (monthly) or YYYYMMDD (daily). {_LAYOUT_HINT}"
        )
    frequency: Frequency = "monthly" if len(cells[start + 1][0]) == 6 else "daily"

    index = pd.DatetimeIndex(pd.to_datetime(dates), name="date")
    if index.has_duplicates:
        raise FactorFileUnreadable(f"The factor table lists {index[index.duplicated()][0].date()} twice.")
    if not index.is_monotonic_increasing:
        raise FactorFileUnreadable("The factor table's dates are not in order.")
    frame = pd.DataFrame(values, index=index, columns=[n or f"__{j}" for j, n in enumerate(names)])
    if has_three:
        keep = [*THREE_FACTOR_COLUMNS, *([MOMENTUM] if MOMENTUM in found else [])]
    else:
        keep = [MOMENTUM]
    return FactorFile(kind="three_factor" if has_three else "momentum", frequency=frequency, frame=frame[keep])
