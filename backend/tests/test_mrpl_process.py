"""Tests for the MRPL-specific process tools — TOOLS.md rows 51-53.

These are assembly over numeric_stats, so the arithmetic is already
covered. What is tested here is the DOMAIN framing, which is the part
that can be confidently wrong: whether a projection is safe to schedule
around, whether a deficit is named as one, and whether a limit is ever
assumed rather than taken from the user's documents.
"""

import pytest

from backend.tools import catalog  # noqa: F401 — registers everything
from backend.tools.registry import call_tool


# ---- row 51: catalyst run length ----------------------------------------


def test_steady_wabt_creep_projects_to_end_of_run_and_is_plannable():
    result = call_tool(
        "catalyst_run_length",
        {"wabt_readings": [408.0, 409.5, 411.0, 412.8, 414.1], "end_of_run_temperature": 425.0},
    )

    assert result.projection.will_cross is True
    assert result.plannable is True
    assert result.degrees_per_reading == pytest.approx(1.55, abs=0.05)
    assert "readings away" in result.interpretation
    # The reading interval is the user's to supply; converting to days
    # here would be inventing a time base.
    assert "reading interval" in result.interpretation


def test_a_noisy_trend_projects_but_is_not_plannable():
    """A weak fit still produces a confident-looking "N readings
    remaining". Acting on that is the failure this flag prevents."""
    result = call_tool(
        "catalyst_run_length",
        {"wabt_readings": [408.0, 415.0, 405.0, 418.0, 404.0, 419.0],
         "end_of_run_temperature": 425.0},
    )

    assert result.plannable is False
    assert "indicative only" in result.interpretation or "not approaching" in result.interpretation


def test_falling_wabt_reports_no_changeout_indicated():
    result = call_tool(
        "catalyst_run_length",
        {"wabt_readings": [418.0, 416.5, 415.0, 413.2], "end_of_run_temperature": 425.0},
    )

    assert result.projection.will_cross is False
    assert result.plannable is False
    assert "No changeout is indicated" in result.interpretation


def test_end_of_run_temperature_is_required_not_defaulted():
    """A default would assert a fact about someone's specific catalyst —
    exactly the confidently-wrong number this system exists to avoid."""
    with pytest.raises(TypeError):
        call_tool("catalyst_run_length", {"wabt_readings": [408.0, 410.0]})


# ---- row 52: hydrogen balance -------------------------------------------


def test_a_deficit_is_named_as_a_deficit_with_what_to_do_about_it():
    result = call_tool(
        "hydrogen_balance", {"produced": [42000.0, 18000.0], "consumed": [35000.0, 29000.0]}
    )

    assert result.is_deficit is True
    assert result.balance == pytest.approx(-4000.0)
    assert "imported hydrogen" in result.interpretation


def test_a_surplus_is_reported_as_available():
    result = call_tool(
        "hydrogen_balance", {"produced": [50000.0], "consumed": [35000.0]}
    )

    assert result.is_deficit is False
    assert result.balance == pytest.approx(15000.0)
    assert "Surplus" in result.interpretation


def test_one_sided_input_is_refused():
    """A balance with no consumption side is a total, and returning it as
    a surplus would be misleading."""
    with pytest.raises(ValueError, match="both a production and a consumption"):
        call_tool("hydrogen_balance", {"produced": [42000.0], "consumed": []})


def test_the_unit_travels_with_the_answer():
    """Row 52 exists to prevent unit-blind arithmetic; a number without
    its unit is what that failure looks like."""
    result = call_tool(
        "hydrogen_balance",
        {"produced": [1000.0], "consumed": [1200.0], "unit": "kg/h"},
    )

    assert result.unit == "kg/h"
    assert "kg/h" in result.interpretation


# ---- row 53: PSA purity compliance --------------------------------------


def test_breaches_are_counted_with_the_worst_reading_named():
    result = call_tool(
        "psa_purity_compliance",
        {"purity_readings": [99.6, 99.4, 99.1, 99.7, 99.9, 99.2], "target_purity": 99.5},
    )

    assert result.readings_below_target == 3
    assert result.worst_reading == pytest.approx(99.1)
    assert result.fraction_compliant == pytest.approx(0.5)
    assert "99.1" in result.interpretation


def test_full_compliance_says_so_plainly():
    result = call_tool(
        "psa_purity_compliance",
        {"purity_readings": [99.91, 99.95, 99.93], "target_purity": 99.9},
    )

    assert result.readings_below_target == 0
    assert result.fraction_compliant == 1.0
    assert "All 3 readings met" in result.interpretation


def test_a_degrading_trend_is_reported_alongside_compliance():
    """"Every reading passed" and "purity is falling steadily" are both
    true at once, and the second is the one worth acting on."""
    result = call_tool(
        "psa_purity_compliance",
        {"purity_readings": [99.95, 99.9, 99.85, 99.8, 99.75, 99.7], "target_purity": 99.5},
    )

    assert result.readings_below_target == 0
    assert result.trend_direction == "decreasing"


def test_target_purity_is_required():
    with pytest.raises(TypeError):
        call_tool("psa_purity_compliance", {"purity_readings": [99.9, 99.8]})


# ---- registry integration ------------------------------------------------


def test_all_three_are_registered_as_computing_real_numbers():
    from backend.tools.registry import get_tool

    for name in ("catalyst_run_length", "hydrogen_balance", "psa_purity_compliance"):
        spec = get_tool(name)
        assert spec is not None, f"{name} is not registered"
        assert spec.computes_numbers is True
        assert spec.is_estimate is False
        assert spec.requires_approval is False
