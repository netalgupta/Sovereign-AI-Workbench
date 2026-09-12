"""The approval gate has to gate the real thing, and run the real thing.

Every test here corresponds to a defect found by running the problem
statement's own graded scenario end to end:

    "reading a scanned inspection report, pulling out key findings and
     drafting an approval note as a Word file"
"""

from backend.orchestrator.action_resolver import (
    _title_for,
    resolve,
)
from backend.orchestrator.graph import classify_action_request
from backend.retrieval.generation import strip_signature_block


# ---------------------------------------------------------------------
# The gate saw almost none of the requests it exists for.
# ---------------------------------------------------------------------


def test_the_file_write_gate_catches_requests_as_people_write_them():
    """MEASURED: 5 of 7 real drafting requests went ungated.

    The pattern required a noun from a short list to fall within 30
    characters of the verb, so any request naming its subject before its
    format missed -- which is how people write them.
    """
    for request in (
        "Draft an approval note on the CCR1 regeneration cycle inspection "
        "findings and save it",
        "Draft a DOCX report on the Hassan incident and save it",
        "Write an approval note for the CCR1 findings",
        "Prepare a memo for HQ about the sulphur spec",
        "Generate a summary document of the inspection",
        "Create a presentation on the incident",
        "Export the maintenance log to Excel",
        "make me a checklist for the grade changeover",
    ):
        assert classify_action_request(request) is not None, request


def test_reads_are_still_reads():
    """The verb list is production verbs only. A false positive costs a
    click; over-gating every question costs the product."""
    for request in (
        "What is the SOP for catalyst changeout?",
        "Summarise the maintenance log",
        "Show me the inspection report",
        "Give me the average MFI for H030SG",
        "list the documents you have",
        "What does the incident report say about the Hassan segment?",
    ):
        assert classify_action_request(request) is None, request


# ---------------------------------------------------------------------
# Consent must be for something that exists.
# ---------------------------------------------------------------------


def test_a_category_with_no_connector_is_not_offered_as_executable():
    """The gate used to register every intercepted action under the tool
    name "operator_requested_action", which is not a registered tool: the
    modal appeared, the operator approved, and execute_approved() raised
    KeyError. Consent for an effect wired to nothing is the worst shape a
    safety control can take -- the ceremony completes and the authorised
    action cannot happen."""
    for category in (
        "setpoint change",
        "SAP / ERP write",
        "outbound send",
        "destructive change",
    ):
        action = resolve("do the thing", category)
        assert action.executable is False
        assert action.tool_name is None
        assert action.reason, "no reason given for what cannot be done"
        # Said at the point of asking, not discovered after consent.
        assert "connector" in action.reason.lower() or "cannot" in action.reason.lower()


def test_a_document_draft_resolves_to_the_real_tool_with_real_arguments(tmp_path):
    """Approving must run exactly what was displayed, which requires the
    arguments to be concrete before approval is requested -- the gate
    hashes what it showed."""
    from backend.tools import catalog  # noqa: F401
    from backend.tools.registry import all_tools

    action = resolve("Draft a report on the inspection findings and save it", "file write")

    if not action.executable:
        # No corpus in this environment; the refusal must be explicit
        # rather than an empty document.
        assert action.reason
        return

    assert action.tool_name == "draft_docx"
    registry = all_tools()
    names = {t.name for t in registry} if not isinstance(registry, dict) else set(registry)
    assert action.tool_name in names, "approval registered against an unregistered tool"

    assert action.arguments["output_path"].endswith(".docx")
    assert action.arguments["sections"], "a document with no sections"
    for section in action.arguments["sections"]:
        assert section["heading"] and section["body"]
    # The preview is plain language. Being shown draft_docx({...}) is not
    # informed consent.
    assert action.preview and not any("{" in line for line in action.preview)


def test_the_title_is_the_subject_not_the_instruction():
    assert _title_for("Draft a report on the Hassan incident and save it") == (
        "Report on the Hassan incident"
    )
    assert _title_for("please write me a Word memo about the CCR1 findings") == (
        "Memo about the CCR1 findings"
    )
    assert _title_for("draft it") == "Drafted Document"


# ---------------------------------------------------------------------
# A drafted document is held to a stricter standard than a chat answer.
# ---------------------------------------------------------------------


def test_a_drafted_section_must_earn_its_place_individually():
    """MEASURED: the first draft of the flagship scenario produced seven
    sections, of which the first two were an Aromatic Complex benzene
    circular and a Kasargod depot tank-calibration thread -- in a
    document about CCR1, under headings reading "Finding 1" and
    "Finding 2".

    An answer needs the top-k passages that are COLLECTIVELY sufficient;
    the model ignores what does not apply. A document has no such
    filter: every passage becomes a section, and the reader assumes it
    is there because it belongs.
    """
    from backend.orchestrator.action_resolver import _individually_relevant_chunks
    from backend.retrieval.grounded_retrieval import confidence_threshold

    class FakeStore:
        def all_chunk_texts(self):
            return [(0, "ccr regeneration cycle inspection"), (1, "unrelated depot tanks")]

        def dense_search(self, embedding, top_k):
            # One clearly relevant, one clearly not.
            return [(0, confidence_threshold() + 0.10), (1, confidence_threshold() - 0.20)]

        def get_by_faiss_id(self, faiss_id):
            class Stored:
                text = f"chunk {faiss_id}"
                source_document = f"doc{faiss_id}.pdf"
                page_number = 1

            return Stored()

    kept = _individually_relevant_chunks(FakeStore(), "CCR1 inspection findings")
    assert [c.source_document for c in kept] == ["doc0.pdf"], (
        "a passage below the grounding floor became a section"
    )


# ---------------------------------------------------------------------
# The system does not sign things.
# ---------------------------------------------------------------------


def test_an_answer_cannot_carry_a_signature():
    """Asked to draft an approval note while ungated, the model ended it

        Signed,
        R. Kamath
        Marketing Ops Manager, HQ

    That name is a real signatory from an unrelated depot letter in the
    corpus. The model did not invent the person; it took a real one and
    signed a document they had never seen, which is worse than an
    invented name because it is attributable and looks verifiable.

    Citation validation cannot catch it: the block carries no marker, so
    there is nothing to validate.
    """
    for text in (
        "The findings are as follows [1].\n\n**Signed,**\nR. Kamath\nManager, HQ",
        "Findings [1].\n\nSigned,\nR. Kamath",
        "Findings [1].\n\nApproved by: R. Kamath\nHQ",
        "Findings [1].\n\nSd/-\nR. Kamath",
        "Findings [1].\n\nYours sincerely,\nR. Kamath",
    ):
        cleaned, removed = strip_signature_block(text)
        assert removed, f"a signature survived: {text!r}"
        assert "R. Kamath" not in cleaned
        # Reported, not silently dropped: a model trying to sign
        # something is a signal about that answer.
        assert "signature was removed" in cleaned.lower()


def test_ordinary_mentions_of_signing_are_left_alone():
    """Over-stripping would corrupt correct answers. A document that WAS
    signed by someone is a fact the corpus can support."""
    for text in (
        "The MFI is 3.4 g/10min [1].",
        "The report was signed by R. Kamath on 12 March [2].",
        "Step 3: record the reading and have it signed off [1].",
        "The approval was authorised by the shift manager per SOP-140 [3].",
    ):
        cleaned, removed = strip_signature_block(text)
        assert removed is None, f"wrongly stripped: {text!r}"
        assert cleaned == text
