"""Tests for CARD 10's evaluate_unit_expression."""

import pytest

from backend.tools.math.unit_calc import evaluate_unit_expression


def test_mass_flow_divided_by_density_converts_to_volumetric_flow():
    # 1500 kg/hr of a fluid at 2.5 kg/m^3 is a volumetric flow rate —
    # the whole point of the tool is getting exactly this kind of
    # dimensional conversion right without a human doing it by hand.
    result = evaluate_unit_expression(
        "1500 kg/hr / (2.5 kg/m**3)", target_unit="m**3/hr"
    )

    assert result.result_magnitude == pytest.approx(600.0)
    assert result.result_unit == "meter ** 3 / hour"
    assert len(result.steps) == 2  # pre-conversion step, then converted step


def test_expression_without_target_unit_keeps_natural_units():
    result = evaluate_unit_expression("5 meter + 300 centimeter")

    assert result.result_magnitude == pytest.approx(8.0)
    assert result.result_unit == "meter"


def test_incompatible_dimensions_raise_with_explicit_message():
    with pytest.raises(ValueError, match="Incompatible units in expression"):
        evaluate_unit_expression("5 meter + 3 second")


def test_incompatible_target_unit_raises_explicit_message():
    with pytest.raises(ValueError, match="Incompatible units in expression"):
        evaluate_unit_expression("5 meter", target_unit="second")


def test_undefined_unit_raises_could_not_evaluate_message():
    with pytest.raises(ValueError, match="Could not evaluate unit expression"):
        evaluate_unit_expression("5 fakeunitxyz")
