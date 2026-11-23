"""Load the unified line-item mapping (``line_items.toml``).

The file is the single source of truth for which XBRL tags feed which unified
item; see the header comment in ``line_items.toml`` for the format.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from sextant_compute.data.statements import STATEMENTS, LineItem

MAPPING_FILE = Path(__file__).with_name("line_items.toml")
UNITS = ("USD", "USD/shares", "shares")
_ID = re.compile(r"^[a-z][a-z0-9_]*$")
_TAG = re.compile(r"^[a-z][a-z0-9-]*:[A-Za-z0-9]+$")


@dataclass(frozen=True)
class Tag:
    taxonomy: str  # "us-gaap", "dei", "ifrs-full", ...
    name: str

    def __str__(self) -> str:
        return f"{self.taxonomy}:{self.name}"


@dataclass(frozen=True)
class Derivation:
    """``terms``: (sign, item id) pairs, e.g. ((1, "revenue"), (-1, "cost_of_revenue"))."""

    formula: str
    terms: tuple[tuple[int, str], ...]


@dataclass(frozen=True)
class LineItemSpec:
    item: LineItem
    tags: tuple[Tag, ...]
    derive: Derivation | None = None

    @property
    def id(self) -> str:
        return self.item.id


def _parse_derive(formula: str, where: str) -> Derivation:
    tokens = formula.split()
    if len(tokens) % 2 == 0:
        raise ValueError(f"{where}: derive must be 'a + b - c', got {formula!r}")
    terms = [(1, tokens[0])]
    for op, ref in zip(tokens[1::2], tokens[2::2], strict=True):
        if op not in "+-" or len(op) != 1:
            raise ValueError(f"{where}: derive supports only + and -, got {op!r}")
        terms.append((1 if op == "+" else -1, ref))
    return Derivation(formula, tuple(terms))


def parse_line_items(text: str) -> tuple[LineItemSpec, ...]:
    """Parse and validate the mapping. Raises ``ValueError`` on any mistake."""
    raw = tomllib.loads(text).get("item", [])
    specs: list[LineItemSpec] = []
    for n, entry in enumerate(raw):
        where = f"item #{n + 1} ({entry.get('id', '?')})"
        item_id = entry.get("id", "")
        if not _ID.match(item_id):
            raise ValueError(f"{where}: id must be snake_case")
        if entry.get("statement") not in STATEMENTS:
            raise ValueError(f"{where}: statement must be one of {STATEMENTS}")
        if entry.get("unit") not in UNITS:
            raise ValueError(f"{where}: unit must be one of {UNITS}")
        unknown = set(entry) - {"id", "label", "statement", "unit", "tags", "derive", "display"}
        if unknown:
            raise ValueError(f"{where}: unknown keys {sorted(unknown)}")
        tags = []
        for tag in entry.get("tags", []):
            if not _TAG.match(tag):
                raise ValueError(f"{where}: tag must be '<taxonomy>:<Tag>', got {tag!r}")
            taxonomy, name = tag.split(":")
            tags.append(Tag(taxonomy, name))
        derive = _parse_derive(entry["derive"], where) if "derive" in entry else None
        if not tags and derive is None:
            raise ValueError(f"{where}: needs tags or derive")
        item = LineItem(
            id=item_id,
            label=entry.get("label") or item_id,
            statement=entry["statement"],
            unit=entry["unit"],
            display=bool(entry.get("display", True)),
        )
        specs.append(LineItemSpec(item=item, tags=tuple(tags), derive=derive))

    by_id = {s.id: s for s in specs}
    if len(by_id) != len(specs):
        raise ValueError("duplicate item ids")
    for spec in specs:
        if spec.derive:
            for _, ref in spec.derive.terms:
                if ref not in by_id:
                    raise ValueError(f"{spec.id}: derive refers to unknown item {ref!r}")
                if by_id[ref].derive is not None:
                    raise ValueError(f"{spec.id}: derive inputs must not be derived themselves ({ref})")
    return tuple(specs)


@cache
def line_items() -> tuple[LineItemSpec, ...]:
    """The mapping shipped with the app."""
    return parse_line_items(MAPPING_FILE.read_text())
