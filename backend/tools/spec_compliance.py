"""Lab readings against product spec limits — TOOLS.md row 56.

MRPL-specific: the Merox units' sulphur compliance sheets are the
worked example, but nothing here is specific to sulphur.

WHY THIS DOES NOT READ THE "STATUS" COLUMN.

The corpus sheet carries one already:

    Sample Date  Unit         Product  Sulphur (ppm)  Spec Limit  Status
    2026-08-19   Kero Merox   SKO      11.2           10          EXCEEDANCE

A tool that reports what that column says is theatre: it adds nothing a
reader could not see, and it inherits every mistake in it. Real lab
sheets frequently have no status column at all, and the ones that do
have it filled in by a person.

So compliance is COMPUTED from the reading and the limit, and where the
document also states a status, the two are COMPARED. A disagreement is
the finding that matters most -- a sheet marked OK on a reading that
exceeds its limit is a compliance failure that has already passed
somebody's review, and it is invisible to anyone reading the status
column, which is everyone.

UNIT-AWARE, THROUGH PINT (row 29), because this is precisely the error
class row 29 exists to prevent: 10 ppm and 0.001% are the same limit,
and comparing the numbers 11.2 and 0.001 without their units gives a
confident, wrong answer. A reading whose units cannot be reconciled
with its limit is reported as UNCOMPARABLE, never silently compared.

NEAR-LIMIT IS A MARGIN ON THE LIMIT, NOT A JUDGEMENT. The default is
10% of the limit, stated in the result, because "near" is a policy
choice that belongs to the plant rather than to this function. A reading
at 9.4 against 10 is flagged; whether that warrants action is not this
tool's call to make.

NO MODEL IS INVOLVED. Every number here comes from arithmetic on values
read out of the document (hard constraint #3), and the comparison is
deterministic, so the same sheet gives the same answer every run. A
safety artifact whose contents change between runs on identical input
is not one anybody can act on.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# "Near limit" defaults to within this fraction of the limit. A policy
# choice, stated in every result rather than hidden in a constant.
DEFAULT_NEAR_LIMIT_FRACTION = 0.10

OK = "ok"
NEAR_LIMIT = "near_limit"
EXCEEDANCE = "exceedance"
UNCOMPARABLE = "uncomparable"


@dataclass
class ReadingVerdict:
    sample: str
    value: float
    limit: float
    units: str
    status: str
    margin_to_limit: float | None
    note: str = ""
    # Set only when the source document stated a status of its own AND
    # it disagrees with the computed one.
    stated_status: str | None = None
    disagrees_with_document: bool = False


@dataclass
class ComplianceReport:
    verdicts: list[ReadingVerdict] = field(default_factory=list)
    near_limit_fraction: float = DEFAULT_NEAR_LIMIT_FRACTION

    @property
    def exceedances(self) -> list[ReadingVerdict]:
        return [v for v in self.verdicts if v.status == EXCEEDANCE]

    @property
    def near_limits(self) -> list[ReadingVerdict]:
        return [v for v in self.verdicts if v.status == NEAR_LIMIT]

    @property
    def disagreements(self) -> list[ReadingVerdict]:
        """Readings where the document's own status is wrong.

        The most important list here, and the one a status column hides.
        """
        return [v for v in self.verdicts if v.disagrees_with_document]

    @property
    def uncomparable(self) -> list[ReadingVerdict]:
        return [v for v in self.verdicts if v.status == UNCOMPARABLE]

    def summary(self) -> str:
        lines = [
            f"{len(self.verdicts)} reading(s) checked against their spec limits. "
            f"'Near limit' means within {self.near_limit_fraction:.0%} of the limit."
        ]
        if self.exceedances:
            lines.append(
                f"{len(self.exceedances)} EXCEEDANCE(S): "
                + "; ".join(
                    f"{v.sample} at {v.value} {v.units} against a limit of {v.limit}"
                    for v in self.exceedances
                )
            )
        if self.near_limits:
            lines.append(
                f"{len(self.near_limits)} near the limit: "
                + "; ".join(f"{v.sample} at {v.value} {v.units}" for v in self.near_limits)
            )
        if self.disagreements:
            lines.append(
                f"{len(self.disagreements)} reading(s) where the DOCUMENT'S OWN "
                f"status disagrees with the computed one: "
                + "; ".join(
                    f"{v.sample} is marked {v.stated_status!r} but computes as "
                    f"{v.status!r}"
                    for v in self.disagreements
                )
            )
        if self.uncomparable:
            lines.append(
                f"{len(self.uncomparable)} reading(s) could not be compared: "
                + "; ".join(f"{v.sample} ({v.note})" for v in self.uncomparable)
            )
        if not (self.exceedances or self.near_limits or self.disagreements):
            lines.append("No exceedances and nothing near a limit.")
        return "\n".join(lines)


def _to_common_units(value: float, value_units: str, limit: float, limit_units: str):
    """(value, limit) expressed in the limit's units, or None if they
    cannot be reconciled.

    Comparing 11.2 ppm against a limit of 0.001 % without converting
    gives a confident wrong answer in the dangerous direction.
    """
    value_units = (value_units or "").strip()
    limit_units = (limit_units or "").strip()
    if not value_units or not limit_units or value_units == limit_units:
        return value, limit

    try:
        # The one shared registry, so a unit means the same thing here as in
        # the unit calculator (a barrel is the 42-gallon oil barrel).
        from backend.tools.math.unit_calc import _ureg as registry

        converted = (value * registry(value_units)).to(registry(limit_units))
        return float(converted.magnitude), limit
    except Exception:  # noqa: BLE001 - pint raises many types for this
        return None


def check_spec_compliance(
    readings: list[dict],
    near_limit_fraction: float = DEFAULT_NEAR_LIMIT_FRACTION,
) -> ComplianceReport:
    """Compare lab readings against their spec limits.

    Args:
        readings: one dict per reading, with keys:
            sample     a label for the row, e.g. "2026-08-19 Kero Merox SKO"
            value      the measured number
            limit      the spec limit
            units      optional; the reading's units, e.g. "ppm"
            limit_units optional; defaults to `units`
            stated_status optional; the status the document itself gives
                       ("OK", "NEAR LIMIT", "EXCEEDANCE"). Used ONLY to
                       detect disagreement, never as the answer.
        near_limit_fraction: how close to the limit counts as "near".
            A policy choice; it is reported in the result.

    Returns:
        ComplianceReport. Status is computed, never copied from the
        document, and a reading whose units cannot be reconciled with
        its limit is UNCOMPARABLE rather than silently compared.
    """
    report = ComplianceReport(near_limit_fraction=near_limit_fraction)

    for row in readings or []:
        sample = str(row.get("sample") or "unnamed sample")
        units = str(row.get("units") or "")
        limit_units = str(row.get("limit_units") or units)

        try:
            value = float(row["value"])
            limit = float(row["limit"])
        except (KeyError, TypeError, ValueError):
            report.verdicts.append(
                ReadingVerdict(
                    sample=sample, value=float("nan"), limit=float("nan"),
                    units=units, status=UNCOMPARABLE, margin_to_limit=None,
                    note="value or limit missing or not a number",
                )
            )
            continue

        reconciled = _to_common_units(value, units, limit, limit_units)
        if reconciled is None:
            report.verdicts.append(
                ReadingVerdict(
                    sample=sample, value=value, limit=limit, units=units,
                    status=UNCOMPARABLE, margin_to_limit=None,
                    note=f"cannot convert {units!r} to {limit_units!r}",
                )
            )
            continue

        comparable_value, comparable_limit = reconciled

        if comparable_value > comparable_limit:
            status = EXCEEDANCE
        elif comparable_limit and comparable_value >= comparable_limit * (
            1 - near_limit_fraction
        ):
            status = NEAR_LIMIT
        else:
            status = OK

        stated = row.get("stated_status")
        normalised_stated = _normalise_status(stated) if stated else None
        disagrees = bool(normalised_stated and normalised_stated != status)

        report.verdicts.append(
            ReadingVerdict(
                sample=sample,
                value=value,
                limit=limit,
                units=limit_units or units,
                status=status,
                margin_to_limit=round(comparable_limit - comparable_value, 6),
                stated_status=str(stated) if stated else None,
                disagrees_with_document=disagrees,
            )
        )

    return report


_STATUS_WORDS = {
    "ok": OK,
    "pass": OK,
    "within spec": OK,
    "compliant": OK,
    "near limit": NEAR_LIMIT,
    "near-limit": NEAR_LIMIT,
    "marginal": NEAR_LIMIT,
    "watch": NEAR_LIMIT,
    "exceedance": EXCEEDANCE,
    "exceeded": EXCEEDANCE,
    "fail": EXCEEDANCE,
    "out of spec": EXCEEDANCE,
    "non-compliant": EXCEEDANCE,
}


def _normalise_status(stated) -> str | None:
    """Map a document's own wording onto the computed vocabulary.

    Returns None for wording this does not recognise, so an unfamiliar
    label is never reported as a disagreement -- claiming the document
    is wrong because its vocabulary is unfamiliar would be worse than
    saying nothing.
    """
    text = str(stated or "").strip().lower()
    return _STATUS_WORDS.get(text)
