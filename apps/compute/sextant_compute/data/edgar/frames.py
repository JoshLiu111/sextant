"""XBRL frames -> cross-sections of unified line items.

``GET data.sec.gov/api/xbrl/frames/{taxonomy}/{tag}/{unit}/{period}.json`` returns
one value per company for one tag and one calendar-aligned period: ``CY2025`` for
a flow (income, cash flow), ``CY2025Q4I`` for a balance-sheet instant. A unified
item lists several candidate tags (``line_items.toml``); as in the statements, the
first tag a company has a value for wins, per company and year, and ``derive``
is the fallback when none has.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import date
from typing import Any

from sextant_compute.data.cross_section import CompanyValue, CrossSection
from sextant_compute.data.edgar.mapping import LineItemSpec, Tag

# One frames row as kept: (value, end, accession).
Row = tuple[float, date, str]
FrameKey = tuple[str, str, str, int]  # (tag "taxonomy:Name", unit, statement, year)


def frame_period(statement: str, year: int) -> str:
    return f"CY{year}Q4I" if statement == "balance" else f"CY{year}"


def frame_path(tag: Tag, unit: str, statement: str, year: int) -> str:
    unit_part = unit.replace("/", "-per-")
    return f"/api/xbrl/frames/{tag.taxonomy}/{tag.name}/{unit_part}/{frame_period(statement, year)}.json"


def specs_needed(item_ids: Iterable[str], mapping: Sequence[LineItemSpec]) -> list[LineItemSpec]:
    """The requested items plus the inputs of their derive formulas, in mapping order."""
    by_id = {s.id: s for s in mapping}
    wanted: set[str] = set()
    for item_id in item_ids:
        spec = by_id.get(item_id)
        if spec is None:
            raise ValueError(f"Unknown line item {item_id!r}")
        wanted.add(item_id)
        if spec.derive:
            wanted.update(ref for _, ref in spec.derive.terms)
    return [s for s in mapping if s.id in wanted]


def frame_keys(specs: Iterable[LineItemSpec], year: int) -> list[FrameKey]:
    keys: dict[FrameKey, None] = {}
    for spec in specs:
        for tag in spec.tags:
            keys[(str(tag), spec.item.unit, spec.item.statement, year)] = None
    return list(keys)


def parse_frame(body: Any) -> dict[int, Row]:
    """Frames JSON -> {cik: (value, end, accession)}. Malformed rows are skipped."""
    rows: dict[int, Row] = {}
    data = body.get("data") if isinstance(body, dict) else None
    for r in data or []:
        try:
            rows[int(r["cik"])] = (float(r["val"]), date.fromisoformat(r["end"]), str(r["accn"]))
        except (KeyError, TypeError, ValueError):
            continue
    return rows


def unify(
    item_ids: Iterable[str],
    mapping: Sequence[LineItemSpec],
    year: int,
    frames: Mapping[FrameKey, Mapping[int, Row]],
    company: Callable[[int], tuple[str, str] | None],
) -> dict[str, CrossSection]:
    """Build one cross-section per item from the fetched tag frames.

    ``company(cik)`` gives (ticker, name), or None for a company without a ticker
    (not listed); those are left out, since tools address companies by ticker.
    """
    by_id = {s.id: s for s in mapping}

    def from_tags(spec: LineItemSpec) -> dict[int, CompanyValue]:
        out: dict[int, CompanyValue] = {}
        for tag in spec.tags:
            rows = frames.get((str(tag), spec.item.unit, spec.item.statement, year), {})
            for cik, (value, end, accession) in rows.items():
                if cik in out:
                    continue
                who = company(cik)
                if who is not None:
                    out[cik] = CompanyValue(cik, who[0], who[1], value, end, accession, tag=str(tag))
        return out

    tagged = {s.id: from_tags(s) for s in specs_needed(item_ids, mapping)}
    result: dict[str, CrossSection] = {}
    for item_id in item_ids:
        spec = by_id[item_id]
        values = dict(tagged[item_id])
        if spec.derive:
            inputs = [(sign, tagged[ref]) for sign, ref in spec.derive.terms]
            first = inputs[0][1]
            for cik, head in first.items():
                if cik in values or not all(cik in vals for _, vals in inputs):
                    continue
                total = sum(sign * vals[cik].value for sign, vals in inputs)
                values[cik] = CompanyValue(
                    cik, head.ticker, head.name, total, head.end, head.accession, derived_from=spec.derive.formula
                )
        result[item_id] = CrossSection(item_id=item_id, label=spec.item.label, year=year, values=values)
    return result
