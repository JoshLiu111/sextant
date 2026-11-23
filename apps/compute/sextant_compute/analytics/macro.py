"""Macro analytics: policy rates published as a list of changes.

A *change list* is ``[(date the rate took effect, rate), ...]`` ascending, as the
ECB publishes its key interest rates. The rate holds until the next change.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta

Changes = Sequence[tuple[date, float | None]]


def in_force(changes: Changes, day: date) -> tuple[date, float] | None:
    """The latest change on or before ``day`` (when it took effect, the rate), or
    None if the first change comes later. Changes without a value are skipped."""
    found = None
    for when, value in changes:
        if when > day:
            break
        if value is not None:
            found = (when, value)
    return found


def step_path(changes: Changes, start: date, end: date) -> list[tuple[date, float]]:
    """Points that draw the rate in force each day in [start, end] as a step line:
    the rate on ``start``; for each later change, the old rate on the day before
    and the new rate on the day itself; and the rate held to ``end``."""
    current = in_force(changes, start)
    points: list[tuple[date, float]] = [(start, current[1])] if current else []
    for when, value in changes:
        if value is None or when <= start or when > end:
            continue
        if points:
            before = when - timedelta(days=1)
            if before > points[-1][0]:
                points.append((before, points[-1][1]))
        points.append((when, value))
    if points and points[-1][0] < end:
        points.append((end, points[-1][1]))
    return points
