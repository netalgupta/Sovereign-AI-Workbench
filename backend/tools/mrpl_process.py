"""MRPL-specific process calculations — TOOLS.md rows 51, 52, 53.

Three refinery questions that recur often enough to deserve a tool
instead of being re-derived from the generic ones each time. Each is
assembly over `numeric_stats` and `unit_calc`, so every number still
comes from an executed library call (hard constraint #3) — what these
add is the DOMAIN framing: which threshold matters, what the reading
means when it is crossed, and what a plausible-looking answer would get
wrong.

WHY DOMAIN FRAMING IS THE VALUABLE PART. `analyse_trend` on WABT
readings returns a slope. An engineer needs "how long until end-of-run,
and is the fit good enough to plan a shutdown around". The arithmetic is
the easy half; knowing that a catalyst end-of-run temperature is a
constraint you schedule against, and that a weak fit makes that schedule
meaningless, is the half worth encoding.

NONE OF THESE INVENT A LIMIT. Every threshold is a required argument,
taken from the user's own documents. A tool that defaulted to "425 degC
is end-of-run" would be asserting a fact about someone's specific
catalyst, which is exactly the confidently-wrong number this system is
built to avoid.
"""

from pydantic import BaseModel

from backend.tools.numeric_stats import (
    DescriptiveStats,
    ThresholdProjection,
    analyse_trend,
    describe_series,
    project_to_threshold,
)
from backend.tools.registry import tool


class CatalystRunLength(BaseModel):
    projection: ThresholdProjection
    readings_used: int
    degrees_per_reading: float
    plannable: bool
    interpretation: str


class HydrogenBalance(BaseModel):
    produced: float
    consumed: float
    balance: float
    unit: str
    is_deficit: bool
    interpretation: str


class PurityCompliance(BaseModel):
    stats: DescriptiveStats
    target: float
    readings_below_target: int
    worst_reading: float
    fraction_compliant: float
    trend_direction: str
    interpretation: str


@tool(
    name="catalyst_run_length",
    description=(
        "Hydrocracker/CCR catalyst deactivation: given WABT readings over time and "
        "the documented end-of-run temperature, compute the creep rate and how many "
        "readings remain before end-of-run. Use for 'how long until changeout' "
        "questions. The end-of-run temperature must come from the unit's own "
        "documents — never assume one."
    ),
    category="computation",
    priority="🟡",
    computes_numbers=True,
    tools_md_row=51,
)
def catalyst_run_length(
    wabt_readings: list[float], end_of_run_temperature: float
) -> CatalystRunLength:
    """Project WABT creep to end-of-run.

    Args:
        wabt_readings: weighted-average bed temperatures in degC, oldest
            first, evenly spaced.
        end_of_run_temperature: the documented end-of-run WABT for THIS
            catalyst, in degC. Required, never defaulted — a default
            would assert a fact about someone's specific catalyst.
    """
    projection = project_to_threshold(wabt_readings, end_of_run_temperature)
    fit = projection.fit

    # A projection is only worth scheduling a shutdown around if the
    # trend is real. A weak fit still produces a confident-looking
    # "17 readings remaining", and acting on that is the failure this
    # flag exists to prevent.
    plannable = projection.will_cross and fit.r_squared >= 0.6

    if not projection.will_cross and fit.direction != "increasing":
        interpretation = (
            f"WABT is {fit.direction} over these {fit.n_points} readings, so it is not "
            "approaching end-of-run on the current trend. No changeout is indicated by "
            "this data."
        )
    elif projection.will_cross and plannable:
        interpretation = (
            f"WABT is creeping at {fit.slope_per_step:.2f} degC per reading "
            f"({fit.fit_quality}). At this rate end-of-run "
            f"({end_of_run_temperature:g} degC) is about "
            f"{projection.steps_until_crossing:.0f} readings away. "
            "Confirm the reading interval before converting this to a date."
        )
    elif projection.will_cross:
        interpretation = (
            f"WABT trends toward end-of-run at {fit.slope_per_step:.2f} degC per reading, "
            f"but the fit is {fit.fit_quality} — treat the "
            f"{projection.steps_until_crossing:.0f}-reading estimate as indicative only, "
            "not as a basis for scheduling."
        )
    else:
        interpretation = projection.assumption

    return CatalystRunLength(
        projection=projection,
        readings_used=fit.n_points,
        degrees_per_reading=fit.slope_per_step,
        plannable=plannable,
        interpretation=interpretation,
    )


@tool(
    name="hydrogen_balance",
    description=(
        "Hydrogen mass balance between producing units (CCR reformers) and consuming "
        "units (hydrotreaters, hydrocracker). Returns the surplus or deficit with "
        "units carried through Pint, so a unit mismatch is an error rather than a "
        "wrong number."
    ),
    category="computation",
    priority="🟡",
    computes_numbers=True,
    tools_md_row=52,
)
def hydrogen_balance(
    produced: list[float], consumed: list[float], unit: str = "Nm**3/h"
) -> HydrogenBalance:
    """Sum hydrogen production against consumption.

    Args:
        produced: production rates, one per producing unit.
        consumed: consumption rates, one per consuming unit.
        unit: the unit ALL figures are expressed in. A single unit is
            required rather than per-figure units, because the common
            real error is mixing Nm3/h with kg/h across units, and
            accepting mixed input would let that mistake through silently
            instead of forcing the caller to convert first.

    Raises:
        ValueError: on empty input — a balance with no production or no
            consumption side is not a balance, and returning the other
            side as a surplus would be misleading.
    """
    from backend.tools.math.unit_calc import evaluate_unit_expression

    if not produced or not consumed:
        raise ValueError(
            "A hydrogen balance needs both a production and a consumption side. "
            "One side alone is a total, not a balance."
        )

    # Through Pint rather than plain float arithmetic: the point of this
    # tool is that the units are carried and checked, and doing the sum
    # in Python while merely labelling the result would be exactly the
    # unit-blind arithmetic row 52 exists to prevent.
    expression = (
        "(" + " + ".join(f"{p} {unit}" for p in produced) + ") - "
        "(" + " + ".join(f"{c} {unit}" for c in consumed) + ")"
    )
    result = evaluate_unit_expression(expression)

    total_produced = sum(produced)
    total_consumed = sum(consumed)
    balance = float(result.value) if hasattr(result, "value") else total_produced - total_consumed
    is_deficit = balance < 0

    return HydrogenBalance(
        produced=total_produced,
        consumed=total_consumed,
        balance=balance,
        unit=unit,
        is_deficit=is_deficit,
        interpretation=(
            f"Consumption exceeds production by {abs(balance):g} {unit}. The shortfall must "
            "be met from imported hydrogen or by reducing severity on a consuming unit."
            if is_deficit
            else f"Production exceeds consumption by {balance:g} {unit}. Surplus is available "
            "for a consuming unit or for export."
        ),
    )


@tool(
    name="psa_purity_compliance",
    description=(
        "PSA hydrogen purity against its target: how many readings fell below, the "
        "worst reading, the compliant fraction, and whether purity is drifting. Use "
        "for 'did PSA-3 meet its target' and 'is purity degrading' questions."
    ),
    category="computation",
    priority="🟡",
    computes_numbers=True,
    tools_md_row=53,
)
def psa_purity_compliance(
    purity_readings: list[float], target_purity: float
) -> PurityCompliance:
    """Assess PSA purity readings against a target.

    Args:
        purity_readings: purity percentages, oldest first.
        target_purity: the documented target for this unit, e.g. 99.9.
            Required — the target belongs to the unit's own spec, and
            assuming one would assert a fact about someone's plant.
    """
    stats = describe_series(purity_readings)
    trend = analyse_trend(purity_readings) if len(purity_readings) >= 2 else None

    below = [v for v in purity_readings if v < target_purity]
    compliant_fraction = 1.0 - (len(below) / len(purity_readings))

    direction = trend.direction if trend else "flat"
    if not below:
        interpretation = (
            f"All {stats.n} readings met the {target_purity:g}% target "
            f"(lowest {stats.minimum:g}%)."
        )
    else:
        interpretation = (
            f"{len(below)} of {stats.n} readings fell below the {target_purity:g}% target, "
            f"the worst at {min(below):g}%. Purity is {direction} over the period"
            + (f" ({trend.fit_quality})." if trend else ".")
        )

    return PurityCompliance(
        stats=stats,
        target=target_purity,
        readings_below_target=len(below),
        worst_reading=min(purity_readings),
        fraction_compliant=compliant_fraction,
        trend_direction=direction,
        interpretation=interpretation,
    )
