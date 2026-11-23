"""Synthetic demo market data: the generator, its published ground-truth parameters,
and the DataService adapter that serves it."""

from sextant_compute.data.synthetic.adapter import SYNTHETIC, SyntheticAdapter

from sextant_compute.data.synthetic.generator import (
    BENCHMARK,
    DEFAULT_SEED,
    FACTOR_COLUMNS,
    FACTORS,
    GENERATOR_VERSION,
    HISTORY_END,
    HISTORY_START,
    PERSONALITIES,
    Crash,
    Personality,
    generate_factors,
    generate_universe,
)

__all__ = [
    "SYNTHETIC",
    "SyntheticAdapter",
    "BENCHMARK",
    "DEFAULT_SEED",
    "FACTOR_COLUMNS",
    "FACTORS",
    "GENERATOR_VERSION",
    "HISTORY_END",
    "HISTORY_START",
    "PERSONALITIES",
    "Crash",
    "Personality",
    "generate_factors",
    "generate_universe",
]
