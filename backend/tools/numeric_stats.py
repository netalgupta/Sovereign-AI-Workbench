from __future__ import annotations

"""Numerical and statistical analysis — TOOLS.md row 28 (🔴).

Trend analysis and curve fitting over real operating data: WABT creep on
a hydrocracker, PSA purity drift against its 99.9% target, sulphur
readings against a spec limit. The questions this answers are the ones
where "roughly, it's going up" is not an acceptable answer and a number
is required.

EVERY NUMBER HERE COMES FROM AN EXECUTED NumPy/SciPy CALL. CLAUDE.md hard
constraint #3 forbids an LLM producing a numeric result by reasoning
about it, and a trend slope is exactly the kind of thing a model will
happily estimate from a list of values if no tool exists to compute it.
That is why this tool is 🔴 rather than a convenience.

WHAT IT DELIBERATELY DOES NOT DO: extrapolate beyond the data without
saying so. `project_to_threshold` returns a projection AND the
assumption it rests on (that the fitted trend continues), because
"catalyst reaches end-of-run in 47 days" read without that caveat is a
maintenance decision made on an unstated assumption.
"""

from typing import Literal

import numpy as np
from pydantic import BaseModel

from backend.tools.registry import tool


class TrendResult(BaseModel):
    slope_per_step: float
    intercept: float
    r_squared: float
    direction: Literal["increasing", "decreasing", "flat"]
    n_points: int
    method: str
    # Plain-language reading of r_squared, so a caller does not have to
    # know what counts as a good fit for this kind of data.
    fit_quality: str


class ThresholdProjection(BaseModel):
    will_cross: bool
    steps_until_crossing: float | None
    projected_value_at_last_step: float
    threshold: float
    assumption: str
    fit: TrendResult


class DescriptiveStats(BaseModel):
    n: int
    mean: float
    median: float
    std_dev: float
    minimum: float
    maximum: float
    p25: float
    p75: float
    # Values more than 1.5 IQR outside the quartiles — flagged rather
    # than removed, since in process data an outlier is usually the
    # interesting reading, not a mistake.
    outliers: list[float]


def _fit_quality(r_squared: float) -> str:
    if r_squared >= 0.9:
        return "strong — the trend explains most of the variation"
    if r_squared >= 0.6:
        return "moderate — a trend is present but the data is noisy"
    if r_squared >= 0.3:
        return "weak — treat the slope as indicative only"
    return "poor — there is no reliable linear trend in this data"


@tool(
    name="analyse_trend",
    description=(
        "Fit a linear trend to a series of numeric readings and report slope, "
        "R-squared and direction. Use for questions like 'is WABT creeping up?' "
        "or 'is PSA purity drifting?'. Every figure is computed by NumPy, never "
        "estimated."
    ),
    category="computation",
    priority="🔴",
    computes_numbers=True,
    tools_md_row=28,
)
def analyse_trend(values: list[float]) -> TrendResult:
    """Fit a least-squares line through evenly-spaced readings.

    Args:
        values: the readings, oldest first. At least two are needed for a
            line to exist at all.

    Raises:
        ValueError: with fewer than 2 points — returning a slope of 0 for
            a single reading would be a fabricated trend, which is worse
            than refusing.
    """
    series = np.asarray(values, dtype=float)
    if series.size < 2:
        raise ValueError(
            f"A trend needs at least 2 readings; got {series.size}. "
            "Reporting a slope for a single point would be inventing one."
        )

    steps = np.arange(series.size, dtype=float)
    slope, intercept = np.polyfit(steps, series, 1)

    predicted = slope * steps + intercept
    ss_residual = float(np.sum((series - predicted) ** 2))
    ss_total = float(np.sum((series - series.mean()) ** 2))
    # A perfectly flat series has zero total variance: the fit is exact,
    # so R-squared is 1.0 rather than 0/0.
    r_squared = 1.0 if ss_total == 0 else 1.0 - ss_residual / ss_total

    # "Flat" needs BOTH tests, and the second one matters more.
    #
    # Magnitude: judged against the spread of the data rather than an
    # absolute epsilon, because a slope of 0.01 is negligible on readings
    # spanning 100 and decisive on readings spanning 0.05.
    spread = float(series.max() - series.min())
    negligible = abs(slope) * series.size < max(spread * 0.05, 1e-12)

    # Confidence: a line fitted through noise still has a slope, and
    # reporting its sign as a direction is asserting a trend the data
    # does not support. Caught by a series oscillating around a constant
    # — the total rise was 80% of the spread, so the magnitude test
    # passed it as "increasing", while the fit was poor enough that
    # _fit_quality called it "no reliable linear trend". The tool was
    # contradicting itself in one return value. Same cutoff as
    # _fit_quality uses, so the two can never disagree again.
    unreliable = r_squared < 0.3

    return TrendResult(
        slope_per_step=float(slope),
        intercept=float(intercept),
        r_squared=float(r_squared),
        direction=(
            "flat" if (negligible or unreliable)
            else ("increasing" if slope > 0 else "decreasing")
        ),
        n_points=int(series.size),
        method="least-squares linear fit (numpy.polyfit, degree 1)",
        fit_quality=_fit_quality(float(r_squared)),
    )


@tool(
    name="project_to_threshold",
    description=(
        "Given a series of readings and a threshold, compute whether the fitted "
        "trend crosses it and after how many further steps. Use for end-of-run "
        "and spec-limit questions. Returns the assumption the projection rests on."
    ),
    category="computation",
    priority="🔴",
    computes_numbers=True,
    tools_md_row=28,
)
def project_to_threshold(values: list[float], threshold: float) -> ThresholdProjection:
    """Project a fitted trend forward to a threshold.

    Args:
        values: the readings, oldest first.
        threshold: the limit of interest — a spec limit, an end-of-run
            temperature, a purity target.
    """
    fit = analyse_trend(values)
    series = np.asarray(values, dtype=float)
    last_step = series.size - 1
    projected_now = fit.slope_per_step * last_step + fit.intercept

    steps_until: float | None = None
    will_cross = False
    if fit.direction != "flat" and fit.slope_per_step != 0:
        steps_at_threshold = (threshold - fit.intercept) / fit.slope_per_step
        remaining = steps_at_threshold - last_step
        # Only a crossing in the FUTURE is a projection. A threshold the
        # data already passed is a fact about the readings, and reporting
        # it as "will cross in -12 steps" reads as a countdown.
        if remaining > 0:
            will_cross = True
            steps_until = float(remaining)

    already_past = (
        projected_now >= threshold if fit.slope_per_step > 0 else projected_now <= threshold
    )

    return ThresholdProjection(
        will_cross=will_cross,
        steps_until_crossing=steps_until,
        projected_value_at_last_step=float(projected_now),
        threshold=float(threshold),
        assumption=(
            "Already past the threshold at the most recent reading."
            if already_past
            else (
                f"Assumes the current {fit.direction} trend continues unchanged "
                f"({fit.fit_quality})."
                if will_cross
                else "The fitted trend does not reach this threshold."
            )
        ),
        fit=fit,
    )


@tool(
    name="describe_series",
    description=(
        "Descriptive statistics for a series of readings: mean, median, standard "
        "deviation, quartiles, and any outliers beyond 1.5 IQR. Computed by NumPy."
    ),
    category="computation",
    priority="🔴",
    computes_numbers=True,
    tools_md_row=28,
)
def describe_series(values: list[float]) -> DescriptiveStats:
    """Summarise a series of readings.

    Args:
        values: the readings. Order does not matter for these statistics.
    """
    series = np.asarray(values, dtype=float)
    if series.size == 0:
        raise ValueError("Cannot describe an empty series.")

    p25, p50, p75 = (float(x) for x in np.percentile(series, [25, 50, 75]))
    iqr = p75 - p25
    low, high = p25 - 1.5 * iqr, p75 + 1.5 * iqr

    return DescriptiveStats(
        n=int(series.size),
        mean=float(series.mean()),
        median=p50,
        # ddof=1: these are samples of a process, not the whole
        # population, and the population formula understates the spread.
        std_dev=float(series.std(ddof=1)) if series.size > 1 else 0.0,
        minimum=float(series.min()),
        maximum=float(series.max()),
        p25=p25,
        p75=p75,
        outliers=[float(v) for v in series[(series < low) | (series > high)]],
    )
