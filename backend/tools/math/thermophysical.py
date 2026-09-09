"""CoolProp thermophysical property lookup — VIBECODING_SPEC.md CARD 11.

WHY THIS EXISTS: TOOLS.md tool #30 backs tool #53 (PSA hydrogen purity
trend dashboard) and any steam/fluid-property lookup an engineer would
otherwise do by hand from a printed steam table. CoolProp is a real
equation-of-state library (same physics a process engineer's steam
tables encode) running fully locally — no Wolfram Alpha, no cloud API,
per REQUIREMENTS.md §5 / DEPENDENCIES.md §5's explicit ban on exactly
that class of dependency.

WHY THE FIXED UNITS TABLE INSTEAD OF ALWAYS SAYING "SI": CoolProp's
PropsSI interface always returns SI units, but "SI" isn't itself a unit —
callers need to know it's specifically Kelvin, or specifically J/kg, to
use the number correctly in a downstream calculation. Guessing a unit for
a property this table doesn't explicitly know would be worse than not
labeling it at all, so the fallback is an honest "not mapped" string
instead of a fabricated guess (same anti-hallucination discipline as
every other tool in this catalog — a wrong unit is a wrong number wearing
a confident label).
"""

import CoolProp.CoolProp as CP
from pydantic import BaseModel

# CoolProp's PropsSI is SI-only. This maps the property codes this system
# actually queries to their SI unit string. Deliberately not exhaustive —
# see module docstring for why an honest "not mapped" beats a guess.
_KNOWN_SI_UNITS: dict[str, str] = {
    "T": "K",
    "P": "Pa",
    "D": "kg/m^3",
    "H": "J/kg",
    "S": "J/kg/K",
    "U": "J/kg",
    "Q": "dimensionless (0-1)",
    "C": "J/kg/K",
    "CONDUCTIVITY": "W/m/K",
    "VISCOSITY": "Pa*s",
}

_UNMAPPED_UNITS_FALLBACK = "SI (CoolProp PropsSI convention — not mapped for this property, see CoolProp docs)"


class ThermophysicalResult(BaseModel):
    fluid: str
    output_property: str
    value: float
    units: str


def lookup_thermophysical_property(
    output_property: str,
    input1_property: str,
    input1_value: float,
    input2_property: str,
    input2_value: float,
    fluid: str,
) -> ThermophysicalResult:
    """Look up a thermophysical property via CoolProp's PropsSI interface.

    Example: lookup_thermophysical_property("H", "T", 300, "P", 101325, "Water")
    returns the specific enthalpy of water at 300 K, 101325 Pa.

    Raises:
        ValueError: f"CoolProp lookup failed for fluid={fluid!r}, "
            f"output={output_property!r}: {original CoolProp message}"
            on any invalid fluid name, property code, or input
            combination — CoolProp's own ValueError detail is preserved,
            not discarded, just wrapped in a consistent message shape.
    """
    try:
        value = CP.PropsSI(
            output_property,
            input1_property,
            input1_value,
            input2_property,
            input2_value,
            fluid,
        )
    except ValueError as exc:
        raise ValueError(
            f"CoolProp lookup failed for fluid={fluid!r}, output={output_property!r}: {exc}"
        ) from exc

    return ThermophysicalResult(
        fluid=fluid,
        output_property=output_property,
        value=float(value),
        units=_KNOWN_SI_UNITS.get(output_property, _UNMAPPED_UNITS_FALLBACK),
    )
