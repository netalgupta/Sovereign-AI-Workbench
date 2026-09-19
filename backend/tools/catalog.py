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
# retrieval_tools registers search_documents and list_documents.
# Until it existed the registry had a "retrieval" category containing
# only find_contradictions and select_images_for_request -- so the
# category looked populated while the agent had no way to SEARCH the
# corpus at all. Given the full registry and asked for a value that is
# printed in the corpus, the model reached for find_contradictions, got
# an empty list, and reported that no documents contained it.
from backend.tools import mrpl_process, netal_tools, numeric_stats, retrieval_tools  # noqa: F401
try:
    from backend.tools import plotting  # noqa: F401
except BaseException:
    plotting = None
from backend.tools.documents import draft_docx, draft_xlsx  # noqa: F401


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

    try:
        from backend.tools.math.symbolic_calc import evaluate_expression

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
    except Exception:
        pass

    try:
        from backend.tools.math.unit_calc import evaluate_unit_expression

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
    except Exception:
        pass

    try:
        from backend.tools.math.thermophysical import lookup_thermophysical_property

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
    except Exception:
        pass

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
    except Exception:
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
    except Exception:
        pass

    try:
        from backend.tools.vision.defect_detection import detect_defects

        tool(
            name="detect_defects",
            # THE DESCRIPTION IS WHAT THE MODEL BELIEVES. It said "Detect
            # defect/anomaly regions", so asked to find defects in a photo the
            # agent would report pump nameplates as defects. It does not
            # detect defects: it returns where the printed text is.
            description=(
                "Return the regions of PRINTED TEXT on an inspection image, as "
                "overlay-ready boxes with the text and its OCR confidence. THIS IS "
                "NOT A DEFECT DETECTOR: no model here recognises corrosion, cracks or "
                "leaks yet. Never describe these regions as defects or anomalies; if "
                "asked to find defects, say that defect detection is not available. "
                "Fully offline."
            ),
            category="vision",
            priority="🟡",
            tools_md_row=7,
        )(detect_defects)
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
    except Exception:
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

    # ---- compliance (MRPL-specific, TOOLS.md row 56) --------------------

    from backend.tools.spec_compliance import check_spec_compliance

    tool(
        name="check_spec_compliance",
        description=(
            "Compare lab readings against their product spec limits and flag "
            "exceedances and near-limit readings. Status is COMPUTED from the "
            "reading and the limit, unit-aware, never copied from a status "
            "column the document already carries -- and where the document "
            "states a status of its own, a disagreement is reported, because a "
            "sheet marked OK on a reading that exceeds its limit is a failure "
            "that already passed review. A reading whose units cannot be "
            "reconciled with its limit is reported as uncomparable rather than "
            "compared."
        ),
        category="mrpl",
        priority="🟡",
        computes_numbers=True,
        tools_md_row=56,
    )(check_spec_compliance)

    # ---- ingestion routing (FR-7, TOOLS.md row 9) -----------------------

    from backend.ingestion.document_classifier import classify_document

    tool(
        name="classify_document",
        description=(
            "Identify what KIND of document this is -- SOP, inspection report, "
            "maintenance log, lab/quality data, SAP export, correspondence, "
            "engineering diagram, or scanned form -- and the processing pipeline "
            "it needs. Distinct from file format: a P&ID and a scanned checklist "
            "are both PNGs and need opposite handling. Returns the evidence that "
            "decided it, and returns 'unknown' rather than guessing when nothing "
            "matches."
        ),
        category="ingestion",
        priority="🔴",
        tools_md_row=9,
    )(classify_document)

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

    # ---- presentation generation (PPTX_AGENT_SPEC.md, TOOLS.md row 40) ----
    from backend.orchestrator.slide_agent import generate_deck

    tool(
        name="generate_deck",
        description=(
            "Render an approved deck spec (from prepare_deck) to a PowerPoint (.pptx) "
            "file, designed by the deck design system. WRITES A FILE, so it requires human "
            "approval before it runs, like draft_docx."
        ),
        category="documents",
        priority="🔴",
        # Hard constraint #4. Decks were exempted as "safe deliverables";
        # a presentation that leaves the building carrying refinery figures
        # is exactly the kind of file the gate exists for.
        requires_approval=True,
        tools_md_row=40,
    )(generate_deck)


register_all()

