"""End-to-end FUNCTIONAL testing — does each feature actually work when
you use it, across normal, edge and adversarial inputs?

DIFFERENT FROM THE UNIT TESTS, ON PURPOSE. The 307 pytest tests assert
that individual functions behave as designed. This asks a different
question: hand each delivered feature the inputs a real user (or a
confused agent, or a corrupt file) would actually produce, and see what
happens. A system can pass every unit test and still fall over on an
empty file, a 12-word question, or a number written with a comma.

THREE INPUT CLASSES PER FEATURE, and the last two are where the findings
come from:

  NORMAL       what the feature was built for.
  EDGE         legal but unusual — empty input, one item, enormous
               values, unicode, zero, negative, duplicate.
  ADVERSARIAL  actively wrong — corrupt bytes, wrong type, injection-ish
               strings, a payload that contradicts itself. The bar is
               not "handles it gracefully"; it is "fails in a way that
               tells the truth about what went wrong".

WHAT COUNTS AS A PASS. Not "did not raise". A refusal can be a pass (the
confidence gate SHOULD reject an off-topic question) and a silent
success can be a failure (an empty file ingesting to zero chunks with no
signal is worse than an error). Each check states its own expectation,
so the report says what should have happened rather than only what did.

Results are written to FUNCTIONAL_TEST_REPORT.md as the run proceeds, so
a long sweep is readable while it is still going.
"""

import io
import json
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

REPORT_PATH = Path("backend/evaluation/FUNCTIONAL_TEST_REPORT.md")


@dataclass
class Check:
    feature: str
    scenario: str
    input_class: str  # normal | edge | adversarial
    expectation: str
    passed: bool | None = None
    observed: str = ""
    error: str | None = None
    seconds: float = 0.0
    severity: str = "normal"  # normal | high — high = safety-relevant


@dataclass
class Suite:
    checks: list[Check] = field(default_factory=list)

    def run(
        self,
        feature: str,
        scenario: str,
        input_class: str,
        expectation: str,
        fn: Callable[[], tuple[bool, str]],
        severity: str = "normal",
    ) -> Check:
        """Run one check. `fn` returns (passed, observed).

        An exception is a FAILURE with its traceback recorded rather than
        an abort: one broken feature must not hide the state of the other
        twenty, which is the whole reason this exists as a sweep.
        """
        check = Check(feature, scenario, input_class, expectation, severity=severity)
        started = time.time()
        try:
            check.passed, check.observed = fn()
        except Exception as exc:  # noqa: BLE001
            check.passed = False
            check.observed = f"raised {type(exc).__name__}: {exc}"
            check.error = traceback.format_exc(limit=3)
        check.seconds = round(time.time() - started, 2)
        self.checks.append(check)

        mark = "PASS" if check.passed else "FAIL"
        print(f"  [{mark}] {feature} :: {scenario} ({check.seconds}s)", flush=True)
        write_report(self)
        return check

    def skip(self, feature: str, scenario: str, reason: str) -> None:
        check = Check(feature, scenario, "normal", reason, passed=None, observed=reason)
        self.checks.append(check)
        print(f"  [SKIP] {feature} :: {scenario} — {reason}", flush=True)
        write_report(self)


def write_report(suite: Suite) -> None:
    checks = suite.checks
    ran = [c for c in checks if c.passed is not None]
    passed = [c for c in ran if c.passed]
    failed = [c for c in ran if not c.passed]
    skipped = [c for c in checks if c.passed is None]

    out = io.StringIO()

    def p(s=""):
        print(s, file=out)

    p("# Functional test report")
    p()
    p("End-to-end exercise of every delivered feature across normal, edge and "
      "adversarial inputs. This is not the unit suite — it asks whether each feature "
      "actually works when used, not whether its functions behave as designed.")
    p()
    p(f"**{len(passed)} passed · {len(failed)} failed · {len(skipped)} skipped** "
      f"of {len(checks)} checks")
    p()

    if failed:
        p("## Failures")
        p()
        high = [c for c in failed if c.severity == "high"]
        if high:
            p(f"**{len(high)} of these are safety-relevant.**")
            p()
        p("| feature | scenario | expected | observed |")
        p("|---|---|---|---|")
        for c in failed:
            flag = " ⚠️" if c.severity == "high" else ""
            p(f"| {c.feature}{flag} | {c.scenario} | {c.expectation} | {c.observed[:180]} |")
        p()

    p("## All checks")
    p()
    by_feature: dict[str, list[Check]] = {}
    for c in checks:
        by_feature.setdefault(c.feature, []).append(c)

    for feature, group in by_feature.items():
        group_ran = [c for c in group if c.passed is not None]
        group_ok = sum(1 for c in group_ran if c.passed)
        status = "OK" if group_ok == len(group_ran) and group_ran else (
            "SKIPPED" if not group_ran else f"{len(group_ran) - group_ok} FAILED"
        )
        p(f"### {feature} — {status}")
        p()
        p("| # | scenario | input | expected | observed |")
        p("|---|---|---|---|---|")
        for i, c in enumerate(group, start=1):
            mark = "—" if c.passed is None else ("PASS" if c.passed else "**FAIL**")
            p(f"| {mark} | {c.scenario} | `{c.input_class}` | {c.expectation} | "
              f"{c.observed[:200].replace(chr(10), ' ')} |")
        p()

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(out.getvalue(), encoding="utf-8")
