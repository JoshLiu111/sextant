"""What AI Explain tells the model, and the guard on its answer.

The model only ever sees a result envelope the compute service produced itself,
plus a short per-tool guide to the metric ids and units.
"""

from __future__ import annotations

import json
import re

from sextant_compute.envelope import ResultEnvelope

SYSTEM = """\
You explain the result of one calculation from Sextant, a suite of finance tools, \
to a non-expert in plain English.

Rules:
- Use only the numbers in the result below. Do not invent, estimate or look up other figures.
- Say what the main numbers mean for this case and how they relate to each other.
- If a metric has a status other than "ok", say briefly why it could not be computed.
- If the result's source has "is_demo": true, the numbers come from Sextant's synthetic \
demo data for fictional tickers (DEMO-A, DEMO-MKT, ...). Say plainly that this is demo \
data, and never describe it as a real company's or the real market's history.
- Write 2 to 4 short paragraphs of plain text: no headings, no lists, no Markdown.
- This is not investment advice. Never recommend buying, selling or holding anything. \
If you mention buying or selling at all, say clearly that this is only a reading of \
the calculation, not advice.
"""

ADVICE_NOTICE = (
    "This is only a reading of the calculation, not investment advice "
    "or a recommendation to buy or sell anything."
)

_TRADING_WORDS = re.compile(
    r"\b(buy|buys|buying|bought|sell|sells|selling|sold|purchas\w*|short(?:ing|ed)?|"
    r"hold(?:ing)?|invest\w*|trad(?:e|es|ing)|recommend\w*)\b",
    re.IGNORECASE,
)

SAMPLE_POINTS = 11


def advice_notice(explanation: str) -> str | None:
    """The not-advice notice when an answer touches on buying or selling, else None."""
    return ADVICE_NOTICE if _TRADING_WORDS.search(explanation) else None


def _sampled(points: list, n: int = SAMPLE_POINTS) -> list:
    if len(points) <= n:
        return points
    step = (len(points) - 1) / (n - 1)
    return [points[round(i * step)] for i in range(n)]


def result_payload(result: ResultEnvelope) -> dict:
    """The envelope as the model sees it: chart series are thinned to a few points."""
    data = result.model_dump(mode="json")
    for s in data["series"].values():
        s["points"] = _sampled(s["points"])
    return data


DEMO_NOTE = (
    "Note: this result uses synthetic demo data (fictional tickers, generated prices), "
    "not real market data. Explain it as demo data."
)


def user_prompt(guide: str, result: ResultEnvelope) -> str:
    demo = f"{DEMO_NOTE}\n\n" if result.source.is_demo else ""
    return (
        f"Tool guide:\n{guide.strip()}\n\n"
        f"{demo}"
        "Result (JSON):\n"
        f"{json.dumps(result_payload(result), indent=1)}\n\n"
        "Explain this result."
    )
