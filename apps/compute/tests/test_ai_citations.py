"""Citation checks on numbers whose sign matters (issue #53).

A number written without a minus sign must not match a negative result, except
for metrics whose name already says the value is a fall or a loss (drawdowns,
VaR/CVaR, losses), where "a drawdown of 35%" is the natural way to write it.
"""

from __future__ import annotations

import pytest

from sextant_compute.ai.citations import check_answer
from sextant_compute.envelope import MetricResult, MetricStatus, ResultEnvelope


def cite(metric: str, actual: float, written: str) -> bool:
    calc = ResultEnvelope.model_construct(
        calculation_id="calc_1",
        tool="risk",
        metrics={metric: MetricResult(value=actual, status=MetricStatus.OK, unit="decimal")},
    )
    [citation] = check_answer(f"[[{written}|calc_1|{metric}]]", {"calc_1": calc})
    return citation.matches


def test_a_negative_alpha_quoted_without_its_sign_is_flagged():
    assert cite("alpha:DEMO-A", -0.02, "2%") is False


@pytest.mark.parametrize("written", ["-2%", "−2%", "-2.0%"])
def test_a_negative_alpha_quoted_with_its_sign_matches(written):
    assert cite("alpha:DEMO-A", -0.02, written) is True


def test_a_positive_value_quoted_with_a_minus_sign_is_flagged():
    assert cite("annualized_return:DEMO-A", 0.02, "-2%") is False


@pytest.mark.parametrize(
    "metric", ["max_drawdown:DEMO-A", "var:DEMO-A", "parametric_cvar:DEMO-A", "max_loss"]
)
@pytest.mark.parametrize(("actual", "written"), [(-0.35, "35%"), (0.35, "35%"), (0.35, "-35%"), (-0.35, "-35%")])
def test_a_fall_or_loss_may_be_quoted_with_or_without_its_sign(metric, actual, written):
    assert cite(metric, actual, written) is True


def test_a_fall_or_loss_still_has_to_be_the_right_size():
    assert cite("max_drawdown:DEMO-A", -0.35, "30%") is False
