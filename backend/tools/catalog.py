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
from backend.tools import numeric_stats, plotting  # noqa: F401


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

    from backend.tools.vision.ocr_printed import extract_printed_text
    from backend.tools.vision.chart_understanding import describe_chart_image

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

    # ---- audio -----------------------------------------------------------

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

    # ---- retrieval -------------------------------------------------------

    from backend.retrieval.image_retrieval import select_images_for_request

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


register_all()
