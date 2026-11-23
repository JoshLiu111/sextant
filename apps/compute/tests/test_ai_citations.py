"""Citation checks on numbers whose sign matters (issue #53).

A number written without a minus sign must not match a negative result, except
for metrics whose name already says the value is a fall or a loss (drawdowns,
VaR/CVaR, losses), where "a drawdown of 35%" is the natural way to write it.
"""

from __future__ import annotations

import pytest

from sextant_compute.ai.citations import check_answer, plain_text
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


# Uncited numbers (issue #56): a number in the prose that cites no calculation is
# not checked against anything, so the answer says so instead of passing it off
# as a checked figure. Dates, years and numbers inside names are not figures.


def uncited(answer: str) -> list[str]:
    return [s.text for s in check_answer(answer, {}) if s.type == "uncited"]


@pytest.mark.parametrize(
    ("answer", "numbers"),
    [
        ("The call is worth about 10.45 per share.", ["10.45"]),
        ("Volatility was 18.3% and alpha -2.1%.", ["18.3%", "-2.1%"]),
        ("Revenue was $391.0B, up from $383 billion.", ["$391.0B", "$383 billion"]),
        ("It trades at 1,234.5, or 3x book.", ["1,234.5", "3x"]),
        ("The 95% VaR is 3 bps (2 of 250 days).", ["95%", "3 bps", "2", "250"]),
    ],
)
def test_numbers_that_cite_no_calculation_are_marked_uncited(answer, numbers):
    assert uncited(answer) == numbers


@pytest.mark.parametrize(
    "answer",
    [
        "Fiscal 2024 ended on 2024-09-28.",
        "DEMO-A and the S&P500 index, Q3 results, a 10-year note, the ff3_alpha.",
    ],
)
def test_dates_years_and_numbers_inside_names_are_not_marked(answer):
    assert uncited(answer) == []


def test_marking_uncited_numbers_keeps_the_text_intact():
    answer = "Vol was 18.3%, and [[10.45|calc_1|call_price]] is cited.\n\nIn 2024 it fell 5%."
    segments = check_answer(answer, {})

    assert [s.type for s in segments] == ["text", "uncited", "text", "citation", "text", "uncited", "text"]
    assert plain_text(segments) == answer.replace("[[10.45|calc_1|call_price]]", "10.45")
