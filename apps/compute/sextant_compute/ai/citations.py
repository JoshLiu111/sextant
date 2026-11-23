"""Numbers in an AI Analyst answer, checked against the calculations they cite.

The model writes every number it takes from a result as
``[[<number as written>|<calculation_id>|<metric id>]]``, e.g.
``[[18.3%|calc_ab12...|annualized_volatility:DEMO-A]]``. ``check_answer`` splits
the answer into text and citation segments and checks each cited number against
the cited calculation's actual value, at the precision it was written: "10.45"
matches 10.4506, "10.4" does not. Percentages are read against the metric's
unit (``decimal`` metrics hold fractions, ``percent`` metrics hold percents).
The sign must match too ("2%" does not match an alpha of -0.02), except for
metrics whose name says the value is a fall or a loss (drawdowns, VaR/CVaR,
losses): those may be written with or without a minus sign ("a drawdown of 35%").
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Literal, NamedTuple

from pydantic import BaseModel

from sextant_compute.envelope import ResultEnvelope

CITATION = re.compile(r"\[\[([^\[\]|]*)\|([^\[\]|]*)\|([^\[\]|]*)\]\]")

_NUMBER = re.compile(
    r"^(?P<sign>[-+−])?\s*\$?\s*(?P<sign2>[-+−])?\s*"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)\s*"
    r"(?P<suffix>%|pp|percentage points?|bps?|basis points?|[kmbt]|bn|thousand|million|billion|trillion|x|×)?"
    r"\s*(?:usd)?$",
    re.IGNORECASE,
)

_MULTIPLIERS = {
    "k": 1e3, "thousand": 1e3,
    "m": 1e6, "million": 1e6,
    "b": 1e9, "bn": 1e9, "billion": 1e9,
    "t": 1e12, "trillion": 1e12,
}  # fmt: skip
_PERCENT_UNITS = {"percent", "percentage_points"}
_LOSS_WORDS = {"drawdown", "var", "cvar", "loss"}
"""A metric whose name has one of these words states its sign by name."""


class Citable(NamedTuple):
    value: float | None
    unit: str | None


class TextSegment(BaseModel):
    type: Literal["text"] = "text"
    text: str


class Citation(BaseModel):
    type: Literal["citation"] = "citation"
    text: str
    """The number as the model wrote it."""
    calculation_id: str
    metric: str
    actual: float | None
    """The cited metric's value in the calculation (None if there is no such value)."""
    unit: str | None
    matches: bool
    reason: str | None
    """Why the citation does not check out (None when it matches)."""


Segment = TextSegment | Citation


class Written(NamedTuple):
    value: float
    tolerance: float


def citable_values(result: ResultEnvelope) -> dict[str, Citable]:
    """The numbers a calculation offers for citing: its metrics, plus screener rows."""
    values = {mid: Citable(m.value, m.unit) for mid, m in result.metrics.items()}
    rows = getattr(result, "rows", None)
    columns = {c.id: c.unit for c in getattr(result, "columns", [])}
    for row in rows or []:
        for col, v in row.values.items():
            values.setdefault(f"{col}:{row.ticker}", Citable(v, columns.get(col)))
    return values


def read_number(text: str, unit: str | None) -> Written | None:
    """The value ``text`` states in ``unit``, with half a unit of its last written digit as tolerance."""
    m = _NUMBER.match(text.strip())
    if m is None or (m["sign"] and m["sign2"]):
        return None
    num = m["num"].replace(",", "")
    decimals = len(num.split(".")[1]) if "." in num else 0
    scale = 1.0
    suffix = (m["suffix"] or "").lower()
    if suffix in _MULTIPLIERS:
        scale = _MULTIPLIERS[suffix]
    elif suffix in ("%", "pp") or suffix.startswith("percentage point"):
        scale = 1.0 if unit in _PERCENT_UNITS else 0.01
    elif suffix.startswith("bp") or suffix.startswith("basis point"):
        scale = 0.01 if unit in _PERCENT_UNITS else 0.0001
    sign = m["sign"] or m["sign2"] or ""
    value = float(num) * scale * (-1 if sign in ("-", "−") else 1)
    return Written(value, 0.5 * 10**-decimals * scale)


def _sign_in_name(metric_id: str) -> bool:
    """Whether the metric's name says its value is a fall or a loss, e.g. ``max_drawdown:DEMO-A``."""
    return not _LOSS_WORDS.isdisjoint(metric_id.split(":")[0].lower().split("_"))


def _close(written: Written, actual: float, *, magnitude_only: bool) -> bool:
    slack = written.tolerance + 1e-9 * max(abs(actual), 1.0)
    if magnitude_only:
        return abs(abs(written.value) - abs(actual)) <= slack
    return abs(written.value - actual) <= slack


def check_citation(text: str, calculation_id: str, metric_id: str, calculations: Mapping[str, ResultEnvelope]) -> Citation:
    def cite(actual: float | None, unit: str | None, reason: str | None) -> Citation:
        return Citation(
            text=text,
            calculation_id=calculation_id,
            metric=metric_id,
            actual=actual,
            unit=unit,
            matches=reason is None,
            reason=reason,
        )

    result = calculations.get(calculation_id)
    if result is None:
        return cite(None, None, "No calculation with this id was run for this answer.")
    found = citable_values(result).get(metric_id)
    if found is None:
        return cite(None, None, f"This calculation has no metric {metric_id}.")
    if found.value is None or not math.isfinite(found.value):
        return cite(None, found.unit, f"{metric_id} has no value in this calculation.")
    written = read_number(text, found.unit)
    if written is None:
        return cite(found.value, found.unit, "Could not read a number in this citation.")
    if not _close(written, found.value, magnitude_only=_sign_in_name(metric_id)):
        return cite(found.value, found.unit, "The number does not match the calculation's result.")
    return cite(found.value, found.unit, None)


def check_answer(answer: str, calculations: Mapping[str, ResultEnvelope]) -> list[Segment]:
    segments: list[Segment] = []
    at = 0
    for m in CITATION.finditer(answer):
        if m.start() > at:
            segments.append(TextSegment(text=answer[at : m.start()]))
        text, calc, metric_id = (part.strip() for part in m.groups())
        segments.append(check_citation(text, calc, metric_id, calculations))
        at = m.end()
    if at < len(answer):
        segments.append(TextSegment(text=answer[at:]))
    return segments


def plain_text(segments: list[Segment]) -> str:
    return "".join(s.text for s in segments)
