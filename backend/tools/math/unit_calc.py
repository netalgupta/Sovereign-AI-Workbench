"""Pint unit-aware calculation tool — VIBECODING_SPEC.md CARD 10.

WHY THIS EXISTS: the MRPL-Grounded Dossier calls out unit-conversion
mistakes as "the classic unit-conversion error class" for exactly the
kind of mass-balance math this system will be asked to do (e.g. CCR
hydrogen balance feeding hydrotreating units, TOOLS.md tool #52). A plain
float calculator has no idea that 1500 kg/hr and 2.5 kg/m^3 combine into
a volumetric flow rate, or that you cannot add kilograms to meters at
all — it'll happily produce a wrong number with the same confidence as a
right one. Pint tracks the *dimension* alongside every number, so an
incompatible-unit mistake raises immediately instead of silently
producing a plausible-looking wrong answer.

WHY A MODULE-LEVEL CACHED UnitRegistry: constructing `pint.UnitRegistry()`
parses a full unit-definitions file from disk. Doing that on every call
would make this tool slow for no benefit — the registry is stateless
across calls, so one shared instance is correct and free.
"""

import pint
from pydantic import BaseModel

# One registry for the whole process — see module docstring for why.
_ureg = pint.UnitRegistry()
# Define Normal cubic meter base unit (Nm) commonly used in refinery hydrogen balance
_ureg.define("Nm = meter")


class UnitCalcResult(BaseModel):
    expression: str
    result_magnitude: float
    result_unit: str
    steps: list[str]


def evaluate_unit_expression(
    expression: str,
    target_unit: str | None = None,
) -> UnitCalcResult:
    """Evaluate a unit-aware arithmetic expression, e.g. "1500 kg/hr / (2.5 kg/m**3)".

    Args:
        expression: a Pint-parseable expression combining numbers and
            units, e.g. "5 meter + 3 centimeter".
        target_unit: optional unit to convert the final result into,
            e.g. "m**3/hr". Must be dimensionally compatible with the
            expression's result.

    Returns:
        UnitCalcResult with the evaluated magnitude, the resulting unit
        (after conversion if `target_unit` was given), and the
        intermediate `steps` a human reviewer can check.

    Raises:
        ValueError: with "Incompatible units in expression ..." if the
            expression mixes incompatible dimensions (e.g. mass + length,
            or converting to a target_unit of the wrong dimension) —
            this is the specific error class this tool exists to catch,
            so the message says so explicitly rather than a generic
            parse-failure message.
        ValueError: with "Could not evaluate unit expression ..." for any
            other parse failure (e.g. an undefined unit name).
    """
    # Accept the inline "X to Y" / "X in Y" conversion form as well as
    # the target_unit argument. Found by functional testing: this tool's
    # own registered description tells the model "converting safely
    # between them (bar to kPa, kg/h to t/day)", and a model reading that
    # writes exactly `evaluate_unit_expression("1 bar to kPa")` — which
    # the parser rejected, because conversion was only ever available
    # through a separate argument. The description was leading the model
    # into a call that could not succeed.
    #
    # Meeting the caller where it is, rather than only fixing the
    # description: "1 bar to kPa" is how a person writes it too, and a
    # unit tool that rejects the most natural spelling of a conversion is
    # failing at its one job. An explicit target_unit still wins if both
    # are given, since that is the caller being unambiguous.
    for separator in (" to ", " in "):
        if target_unit is None and separator in expression:
            head, _, tail = expression.rpartition(separator)
            # Only treat the tail as a unit if it actually parses as one;
            # "5 kg in the vessel" must not become a conversion attempt.
            candidate = tail.strip()
            try:
                _ureg.parse_units(candidate)
            except Exception:  # noqa: BLE001 — not a unit; leave the expression alone
                continue
            expression, target_unit = head.strip(), candidate
            break

    try:
        quantity = _ureg.parse_expression(expression)
    except pint.errors.DimensionalityError as exc:
        raise ValueError(f"Incompatible units in expression {expression!r}: {exc}") from exc
    except Exception as exc:
        # Covers UndefinedUnitError, tokenize/syntax failures, etc. — one
        # predictable exception type for callers, same rationale as
        # CARD 08's parse-failure handling.
        raise ValueError(f"Could not evaluate unit expression: {expression!r}") from exc

    steps: list[str] = [str(quantity)]

    if target_unit is not None:
        try:
            quantity = quantity.to(target_unit)
        except pint.errors.DimensionalityError as exc:
            raise ValueError(
                f"Incompatible units in expression {expression!r}: {exc}"
            ) from exc
        steps.append(str(quantity))

    return UnitCalcResult(
        expression=expression,
        result_magnitude=float(quantity.magnitude),
        result_unit=str(quantity.units),
        steps=steps,
    )
