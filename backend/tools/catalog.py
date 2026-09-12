"""Registers every tool the agent can call, in one place.

WHY REGISTRATION LIVES HERE rather than as a decorator on each tool.
Most of these tools were written before the registry existed and are
imported directly by the evaluation harnesses, the API, and their own
tests. Decorating them in place would mean every one of those importers
pulls in the registry, and a tool module would stop being independently
usable. Registering them here keeps each tool a plain function that
happens to also be exposed to the agent — importing
`ocr_printed.extract_printed_text` still costs nothing but PaddleOCR.

It also gives one file to read to answer "what can the agent actually
do?", which is the question TOOLS.md answers for humans and this answers
for the orchestrator. The two must agree; the row numbers below are the
link between them.

The descriptions are written FOR THE MODEL, not for a developer. They say
when to reach for the tool and what not to use it for, because a model
choosing between `evaluate_expression` and `analyse_trend` has only these
sentences to go on.
"""

from backend.tools.registry import tool

# Importing these modules is what registers the tools defined with the
# decorator inline (numeric_stats, plotting).
from backend.tools import mrpl_process, numeric_stats, plotting  # noqa: F401
from backend.tools.documents import draft_docx  # noqa: F401


def register_all() -> None:
    """Wrap and register the pre-existing tools.

    Idempotent: the registry rejects duplicate names, and this module is
    imported from several places, so registration is guarded rather than
    left to import order.
    """
    from backend.tools.registry import get_tool

    if get_tool("evaluate_expression") is not None:
        return

    # ---- computation (hard constraint #3: real libraries, not the LLM) ----

    from backend.tools.math.symbolic_calc import evaluate_expression
    from backend.tools.math.unit_calc import evaluate_unit_expression
    from backend.tools.math.thermophysical import lookup_thermophysical_property

    tool(
        name="evaluate_expression",
        description=(
            "Evaluate a mathematical expression exactly using SymPy — arithmetic, "
            "algebra, solving, differentiation, integration. Use this for ANY "
            "calculation. Never compute a numeric answer yourself."
        ),
        category="computation",
        priority="🔴",
        computes_numbers=True,
        tools_md_row=26,
    )(evaluate_expression)

    tool(
        name="evaluate_unit_expression",
        description=(
            "Evaluate an expression with physical units using Pint, converting "
            "safely between them (bar to kPa, kg/h to t/day). Use whenever units "
            "appear — it makes a unit mismatch an error rather than a wrong number."
        ),
        category="computation",
        priority="🔴",
        computes_numbers=True,
        tools_md_row=29,
    )(evaluate_unit_expression)

    tool(
        name="lookup_thermophysical_property",
        description=(
            "Look up a thermophysical property of a fluid (density, enthalpy, "
            "viscosity, boiling point) at a given state using CoolProp. Use for "
            "steam tables and process fluid properties instead of recalling values."
        ),
        category="computation",
        priority="🟡",
        computes_numbers=True,
        tools_md_row=30,
    )(lookup_thermophysical_property)

    # ---- vision ----------------------------------------------------------

    try:
        from backend.tools.vision.ocr_printed import extract_printed_text

        tool(
            name="extract_printed_text",
            description=(
                "Read printed text from an image or scan using local OCR. Use for "
                "scanned documents, equipment nameplates, and printed labels. Not for "
                "handwriting — accuracy on handwritten text is poor and unmarked."
            ),
            category="vision",
            priority="🔴",
            tools_md_row=1,
        )(extract_printed_text)
    except ImportError:
        pass

    try:
        from backend.tools.vision.chart_understanding import describe_chart_image

        tool(
            name="describe_chart_image",
            description=(
                "Describe what a chart IMAGE shows using a vision model. The output is "
                "an ESTIMATE, never a measurement: on charts with no printed numbers "
                "this model has been measured stating specific figures that were not "
                "there. Never present its numbers as data. If the chart came from a "
                "spreadsheet, use the exact cached values instead."
            ),
            category="vision",
            priority="🟡",
            is_estimate=True,
            tools_md_row=62,
        )(describe_chart_image)
    except ImportError:
        pass

    # ---- audio -----------------------------------------------------------

    try:
        from backend.tools.audio.voice_transcription import transcribe_voice_note

        tool(
            name="transcribe_voice_note",
            description=(
                "Transcribe a spoken audio file to text using local speech-to-text. "
                "Use for voice notes and recorded handover briefings."
            ),
            category="audio",
            priority="🟡",
            tools_md_row=61,
        )(transcribe_voice_note)
    except ImportError:
        pass

    # ---- retrieval -------------------------------------------------------

    from backend.retrieval.image_retrieval import select_images_for_request

    from backend.retrieval.contradiction import find_contradictions

    tool(
        name="find_contradictions",
        description=(
            "Check a set of retrieved chunks for documents that state DIFFERENT "
            "values for the same limit or quantity. Use before relying on a limit "
            "that appears in more than one document. Returns high severity when the "
            "disagreement is about a limit, because someone will operate to "
            "whichever one they read. Comparison is deterministic and unit-aware; "
            "readings, dated values and different equipment are not contradictions."
        ),
        category="retrieval",
        priority="🟡",
        tools_md_row=15,
    )(find_contradictions)

    tool(
        name="select_images_for_request",
        description=(
            "Given a user's request and candidate image ids from retrieved chunks, "
            "pick the image they are asking for and return it with its provenance. "
            "Use when the user asks to SEE something — a diagram, a chart, a scan. "
            "Returns nothing when no image matches, which is a valid answer."
        ),
        category="retrieval",
        priority="🟡",
        tools_md_row=64,
    )(select_images_for_request)

    # ---- code & sandbox (FR-13, TOOLS.md row 34) ------------------------

    from backend.sandbox.executor import run_in_sandbox

    tool(
        name="run_in_sandbox",
        description=(
            "Execute Python or Node.js code inside an isolated Docker container with "
            "--network none, strict resource limits, and timeout protection. Use for "
            "data processing, engineering calculations, parsing, and running verification code."
        ),
        category="code",
        priority="🔴",
        tools_md_row=34,
    )(run_in_sandbox)


register_all()

