"""Latest-filings feeds: the market-wide ``getcurrent`` Atom feed and a company's
``submissions`` JSON, both parsed into ``FilingEntry`` rows (newest first)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date
from typing import Any
from urllib.parse import urlencode

from sextant_compute.data.filings import FilingEntry

ATOM = "{http://www.w3.org/2005/Atom}"
# "10-K - PTC INC. (0000857005) (Filer)"
_TITLE = re.compile(r"^(?P<form>.+?) - (?P<company>.+) \((?P<cik>\d{10})\) \((?P<role>[\w ]+)\)$")
_FILED = re.compile(r"Filed:\s*</b>\s*(\d{4}-\d{2}-\d{2})|Filed:\s*(\d{4}-\d{2}-\d{2})")
_ACCESSION = re.compile(r"accession-number=(\d{10}-\d{2}-\d{6})")
# Plain names for common forms, used when the filing carries no description.
FORM_NAMES = {
    "10-K": "Annual report",
    "10-Q": "Quarterly report",
    "8-K": "Current report",
    "4": "Statement of changes in beneficial ownership",
    "3": "Initial statement of beneficial ownership",
    "144": "Notice of proposed sale of securities",
    "DEF 14A": "Proxy statement",
    "S-1": "Registration statement",
    "S-3": "Registration statement",
    "S-8": "Registration statement for employee plans",
    "SC 13G": "Beneficial ownership report",
    "SCHEDULE 13G": "Beneficial ownership report",
    "11-K": "Annual report of employee stock plans",
}


def getcurrent_path(form: str, count: int) -> str:
    """The getcurrent query; ``form`` "" means every form type."""
    query = urlencode(
        {
            "action": "getcurrent",
            "type": form,
            "company": "",
            "dateb": "",
            "owner": "include",
            "start": 0,
            "count": count,
            "output": "atom",
        }
    )
    return f"/cgi-bin/browse-edgar?{query}"


def filing_index_url(cik: int, accession: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{accession}-index.htm"


def parse_getcurrent(text: str) -> list[FilingEntry]:
    """Parse the Atom feed. Raises ``ValueError`` if it isn't a feed at all."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"not XML: {exc}") from exc
    if root.tag != f"{ATOM}feed":
        raise ValueError("not an Atom feed")
    out: list[FilingEntry] = []
    for entry in root.iter(f"{ATOM}entry"):
        title = (entry.findtext(f"{ATOM}title") or "").strip()
        m = _TITLE.match(title)
        accession = _ACCESSION.search(entry.findtext(f"{ATOM}id") or "")
        if m is None or accession is None:
            continue
        category = entry.find(f"{ATOM}category")
        form = category.get("term") if category is not None and category.get("term") else m["form"]
        summary = entry.findtext(f"{ATOM}summary") or ""
        filed = _FILED.search(summary)
        updated = (entry.findtext(f"{ATOM}updated") or "")[:10]
        try:
            filed_on = date.fromisoformat(next(g for g in filed.groups() if g) if filed else updated)
        except ValueError:
            continue
        link = entry.find(f"{ATOM}link")
        cik = int(m["cik"])
        url = link.get("href") if link is not None and link.get("href") else filing_index_url(cik, accession[1])
        out.append(
            FilingEntry(
                form=form,
                title=title,
                company=m["company"],
                cik=cik,
                filed=filed_on,
                accession=accession[1],
                url=url,
            )
        )
    return out


def parse_submissions(body: Any) -> tuple[str, list[FilingEntry]]:
    """``submissions/CIK##########.json`` -> (company name, recent filings newest first).
    Raises ``ValueError`` on an unexpected shape."""
    try:
        cik = int(body["cik"])
        name = str(body["name"])
        recent = body["filings"]["recent"]
        columns = zip(
            recent["form"],
            recent["filingDate"],
            recent["accessionNumber"],
            recent.get("primaryDocDescription") or [""] * len(recent["form"]),
            recent.get("items") or [""] * len(recent["form"]),
            strict=True,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"unexpected submissions shape: {exc}") from exc
    out: list[FilingEntry] = []
    for form, filed, accession, description, items in columns:
        try:
            filed_on = date.fromisoformat(filed)
        except (TypeError, ValueError):
            continue
        detail = str(description or "").strip()
        if detail.upper() in (form.upper(), f"FORM {form}".upper()):
            detail = ""
        detail = detail or FORM_NAMES.get(form.split("/")[0], "")
        title = f"{form} - {detail}" if detail else form
        if items:
            title = f"{title} (Items {items.replace(',', ', ')})"
        out.append(
            FilingEntry(
                form=form,
                title=title,
                company=name,
                cik=cik,
                filed=filed_on,
                accession=accession,
                url=filing_index_url(cik, accession),
            )
        )
    out.sort(key=lambda f: f.filed, reverse=True)
    return name, out
