"""Human-readable trace of everything one agent turn actually did.

WHY THIS EXISTS. Debugging a grounded-RAG turn from the outside is
guesswork: a wrong answer can come from retrieval picking the wrong
chunks, from the confidence gate refusing something it should have
allowed, from the prompt, from the model, or from citation validation
stripping a marker afterwards. The uvicorn access log says
`POST /api/chat 200 OK` for every one of those.

So this prints the turn as it happens, in order, with the things you
actually need to judge it:

  - the exact request
  - what retrieval returned: every chunk, its score, its source document
    and page, and whether it cleared the grounding threshold
  - the exact prompt sent to the model, in full, including the sources
    block the model saw
  - the raw answer before citation validation, and what validation
    changed
  - the final answer, with its markdown structure identified (tables,
    code blocks, citations) so formatting problems are visible without
    squinting at escaped newlines
  - the verification verdict
  - timings per stage

PRINCIPLE: this logs what HAPPENED, never a summary of what should have
happened. Every value here is read back from the real object after the
step ran. A debug log that reports intentions is how a fake pipeline
goes unnoticed for weeks -- this codebase had a synthesize step that
never called a model, and no log would have caught it, because nothing
logged the model call.

Controlled by WORKBENCH_TRACE:
    off / 0 / unset  - silent (default for tests)
    on / 1           - stage lines, chunk table, answer structure
    full             - adds the COMPLETE prompt and raw model output

Enable in the shell that runs uvicorn:
    set WORKBENCH_TRACE=full        (cmd)
    $env:WORKBENCH_TRACE="full"     (PowerShell)
    export WORKBENCH_TRACE=full     (bash)
"""

from __future__ import annotations

import os
import re
import sys
import time
from contextlib import contextmanager

# ANSI colour, disabled when output is redirected to a file so a captured
# log does not fill with escape codes.
_COLOUR = sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOUR else text


DIM = lambda t: _c("2", t)  # noqa: E731
BOLD = lambda t: _c("1", t)  # noqa: E731
CYAN = lambda t: _c("36", t)  # noqa: E731
GREEN = lambda t: _c("32", t)  # noqa: E731
YELLOW = lambda t: _c("33", t)  # noqa: E731
RED = lambda t: _c("31", t)  # noqa: E731

WIDTH = 100


def level() -> str:
    """Read the env var on every call, so it can be changed without a restart.

    Cached module state would mean flipping the switch required bouncing
    the server, which is precisely when you least want to -- the failure
    you are chasing is in the process you would be killing.
    """
    raw = (os.environ.get("WORKBENCH_TRACE") or "").strip().lower()
    if raw in ("full", "verbose", "2"):
        return "full"
    if raw in ("on", "1", "true", "yes"):
        return "on"
    if raw in ("off", "0", "false", "no", "none", "silent"):
        return "off"

    # UNSET DEFAULTS TO ON, deliberately.
    #
    # This was the opposite, and the result was a debugging tool nobody
    # could see: the server was started the normal way, no variable was
    # set, and the console showed only `POST /api/chat 200 OK` plus
    # library warnings. A diagnostic that requires you to already know
    # its name and re-launch the process is a diagnostic you will not
    # have running at the moment something breaks.
    #
    # The cost of defaulting on is console volume during development,
    # which is the point. Set WORKBENCH_TRACE=off to silence it.
    #
    # Tests are the exception: pytest captures stdout, and hundreds of
    # traced turns would bury the report for no benefit.
    if "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules:
        return "off"
    return "on"


def enabled() -> bool:
    return level() != "off"


def _emit(text: str = "") -> None:
    # print(flush=True) because uvicorn's reloader buffers stdout, and a
    # trace that appears after the thing you are debugging has finished
    # is not a trace.
    #
    # Wrapped because a Windows console is cp1252 and a single unprintable
    # character raises UnicodeEncodeError from print(). That exception
    # propagated out of the retrieval stage and was caught by
    # synthesize_node's except clause, which replaced a correct grounded
    # answer with "I could not complete this analysis" -- the trace
    # silently broke the pipeline it was supposed to explain. Observability
    # must never be able to change the behaviour it observes.
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(text.encode(enc, errors="replace").decode(enc, errors="replace"), flush=True)
    except Exception:  # noqa: BLE001
        pass


def rule(title: str = "", char: str = "-") -> None:
    if not enabled():
        return
    if title:
        pad = max(0, WIDTH - len(title) - 4)
        _emit(DIM(f"{char * 2} {title} {char * pad}"))
    else:
        _emit(DIM(char * WIDTH))


def section(title: str) -> None:
    if not enabled():
        return
    _emit()
    rule(BOLD(title), "=")


def kv(key: str, value) -> None:
    if not enabled():
        return
    _emit(f"  {DIM(key + ':'):<28} {value}")


def note(text: str) -> None:
    if not enabled():
        return
    _emit(f"  {text}")


def warn(text: str) -> None:
    if not enabled():
        return
    _emit(f"  {YELLOW('! ' + text)}")


def error(text: str) -> None:
    if not enabled():
        return
    _emit(f"  {RED('x ' + text)}")


def block(title: str, body: str, only_full: bool = False) -> None:
    """Print a multi-line body inside a labelled, indented frame."""
    if not enabled():
        return
    if only_full and level() != "full":
        note(DIM(f"[{title}: {len(body)} chars - set WORKBENCH_TRACE=full to print]"))
        return
    _emit(f"  {CYAN('+- ' + title)}")
    for line in (body or "").split("\n"):
        _emit(f"  {CYAN('|')} {line}")
    _emit(f"  {CYAN('+' + '-' * 40)}")


@contextmanager
def stage(name: str):
    """Time one stage and report how it ended, including on exception.

    The failure path prints too. A stage that logs only on success turns
    an exception into silence, which reads identically to the stage
    never having run.
    """
    if not enabled():
        yield
        return
    t0 = time.perf_counter()
    _emit(f"  {DIM('>')} {name} ...")
    try:
        yield
    except Exception as exc:  # noqa: BLE001
        error(f"{name} FAILED after {time.perf_counter() - t0:.2f}s: "
              f"{type(exc).__name__}: {exc}")
        raise
    else:
        _emit(f"  {GREEN('OK')} {name} {DIM(f'({time.perf_counter() - t0:.2f}s)')}")


def chunks_table(chunks, threshold: float | None = None) -> None:
    """Every retrieved chunk: score, source, page, and a text preview.

    Printed in full rather than top-3, because the chunk that explains a
    wrong answer is usually the one that ALMOST won.
    """
    if not enabled():
        return
    if not chunks:
        warn("retrieval returned NO chunks")
        return

    _emit(f"  {DIM('#   score    source document                          page  preview')}")
    for i, ch in enumerate(chunks, 1):
        score = getattr(ch, "score", None)
        src = str(getattr(ch, "source_document", "?"))[:40]
        page = getattr(ch, "page_number", None)
        text = re.sub(r"\s+", " ", (getattr(ch, "text", "") or "")).strip()[:46]
        score_s = f"{score:.4f}" if isinstance(score, (int, float)) else "  -   "
        mark = ""
        if threshold is not None and isinstance(score, (int, float)):
            mark = GREEN(" >=thr") if score >= threshold else DIM(" <thr")
        _emit(f"  {i:<3} {score_s:<8} {src:<40} {str(page or '-'):<5} {text}{mark}")


_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$", re.M)
_FENCE = re.compile(r"^```", re.M)
_CITATION = re.compile(r"\[(\d+)\]")
_HEADING = re.compile(r"^#{1,6}\s", re.M)


def answer_structure(text: str) -> None:
    """What markdown the answer actually contains.

    The frontend renders GFM tables and highlighted code blocks, and the
    common formatting bug is a table the model ALMOST produced -- a
    missing separator row renders as run-together text rather than a
    table, and looks like a styling problem in the browser when it is a
    generation problem here. Counting the pieces makes that obvious from
    the server console.
    """
    if not enabled():
        return
    rows = _TABLE_ROW.findall(text or "")
    fences = len(_FENCE.findall(text or ""))
    cites = sorted({int(n) for n in _CITATION.findall(text or "")})

    kv("length", f"{len(text or '')} chars")
    kv("headings", len(_HEADING.findall(text or "")))
    kv("table rows", len(rows))
    if rows:
        # A GFM table needs a |---|---| separator directly under the
        # header. Without it the whole thing renders as paragraph text.
        has_sep = any(re.match(r"^\s*\|[\s:|-]+\|\s*$", r) for r in rows)
        if has_sep:
            note(GREEN("  table separator row present - will render as a table"))
        else:
            warn("table-like rows WITHOUT a |---| separator - this renders as "
                 "plain text, not a table")
    kv("code fences", f"{fences} ({'balanced' if fences % 2 == 0 else RED('UNBALANCED')})")
    kv("citations", cites or "none")
