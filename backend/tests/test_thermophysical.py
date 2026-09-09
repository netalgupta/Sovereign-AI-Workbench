"""Tests for CARD 11's lookup_thermophysical_property."""

import pytest

from backend.tools.math.thermophysical import lookup_thermophysical_property


def test_water_enthalpy_lookup_returns_mapped_units():
    result = lookup_thermophysical_property("H", "T", 300, "P", 101325, "Water")

    assert result.fluid == "Water"
    assert result.output_property == "H"
    assert isinstance(result.value, float)
    assert result.units == "J/kg"


def test_unknown_fluid_raises_wrapped_error_preserving_coolprop_detail():
    with pytest.raises(ValueError) as exc_info:
        lookup_thermophysical_property("H", "T", 300, "P", 101325, "NotARealFluid")

    message = str(exc_info.value)
    assert "CoolProp lookup failed for fluid='NotARealFluid'" in message
    assert "output='H'" in message


def test_unmapped_output_property_gets_honest_fallback_not_a_guess():
    # "PRANDTL" (Prandtl number) is dimensionless but isn't in the small
    # fixed mapping table — must fall back honestly, never fabricate a
    # specific unit string for it.
    result = lookup_thermophysical_property("PRANDTL", "T", 300, "P", 101325, "Water")

    assert "not mapped" in result.units
