"""Expected, per-metric failures that analytics functions raise.

``sextant_compute.envelope.metric`` turns them into a metric status; any other
exception is a code defect and propagates.
"""


class MissingData(Exception):
    """An input the metric needs is absent. The message names what is missing."""


class MetricError(Exception):
    """The metric cannot be computed for these inputs (e.g. no IV solution)."""
