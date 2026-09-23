"""The approval gate has to gate the real thing, and run the real thing.

Every test here corresponds to a defect found by running the problem
statement's own graded scenario end to end:

    "reading a scanned inspection report, pulling out key findings and
     drafting an approval note as a Word file"
"""

from backend.orchestrator.action_resolver import (
    _title_for,
    is_spreadsheet_request,
    is_pdf_request,
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
# A spreadsheet request must be approved as a spreadsheet.
# ---------------------------------------------------------------------


def test_spreadsheet_requests_are_detected_as_such():
    """An Excel request intercepted by the gate used to resolve to
    draft_docx: the operator approved ".xlsx" and got a Word file. The
    resolver and the schema-narrowing decision must agree on what is a
    spreadsheet."""
    for request in (
        "Draft an Excel comparison of batch MFI values and save it",
        "Build a spreadsheet of the inspection findings",
        "Create a .xlsx export of the maintenance log",
        "Make me a comparison table of the monthly readings",
    ):
        assert is_spreadsheet_request(request) is True, request
    for request in (
        "Draft a report on the Hassan incident and save it",
        "Write a Word memo about the CCR1 findings",
    ):
        assert is_spreadsheet_request(request) is False, request


def test_pdf_requests_are_detected_as_such():
    """A PDF export or drafting request must be recognized so it resolves to generate_pdf."""
    for request in (
        "Draft a PDF report on the Hassan incident and save it",
        "Export the inspection findings to PDF",
        "Create a .pdf summary document",
        "Generate a PDF report for HQ",
    ):
        assert is_pdf_request(request) is True, request
    for request in (
        "Draft an Excel comparison of batch MFI values",
        "Write a Word memo about the CCR1 findings",
    ):
        assert is_pdf_request(request) is False, request


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


# ---------------------------------------------------------------------
# Regressions that arrived with a branch merge. The suite passed at 419
# with all three present, which is why each is pinned here by hand.
# ---------------------------------------------------------------------


def test_the_streaming_approval_payload_describes_the_pending_action():
    """It arrived hardcoded, in the backend, for EVERY intercepted action:

        action_type   DCS_SETPOINT_WRITE
        target        HCU-2 / FFC-201
        current       100% (1,450 m3/h)
        proposed      115% (1,667 m3/h)
        risk_level    CRITICAL

    So "Draft an approval note and save it" asked an operator to
    authorise a feed-rate change on FFC-201. The same defect as 879a8ef,
    and worse: it was removed from ApprovalModal.jsx and moved into the
    backend, so the UI renders invented figures as authoritative data.
    A visible fallback became an invisible claim.
    """
    import os

    os.environ["WORKBENCH_TRACE"] = "off"
    from backend.orchestrator.agent_loop import run_turn

    events = list(run_turn("Increase the HCU-2 feed rate to 115%", session_id="t-appr"))
    required = [e for e in events if e["type"] == "approval_required"]
    assert required, "a setpoint write reached the tool loop ungated"

    action = required[0]["action"]
    invented = [
        field
        for field in ("current_value", "proposed_value", "target", "risk_level",
                      "unit", "parameter", "warning")
        if field in action
    ]
    assert not invented, f"fields the system cannot know were filled in: {invented}"

    # It describes what was actually detected, and says plainly that it
    # cannot be carried out -- at the point of asking, not after consent.
    assert action["action_type"] == "setpoint change"
    assert action["executable"] is False
    assert action["tool_name"] is None
    assert action["reason"]


def test_both_paths_start_the_same_job_for_the_same_request(monkeypatch):
    """Two implementations of one decision is how they drift. Both chat
    paths resolve through action_resolver, so a drafting request must
    start ONE job of the same kind on either -- and neither may file an
    approval before the work exists."""
    import os

    os.environ["WORKBENCH_TRACE"] = "off"
    from backend.orchestrator import output_jobs
    from backend.orchestrator.agent_loop import run_turn
    from backend.orchestrator.graph import run_agent_turn

    started = []

    def fake_start(request, session_id="default", kind="deck"):
        started.append(kind)
        job = output_jobs.OutputJob(job_id=f"{kind}-{len(started)}", request=request,
                                    session_id=session_id, kind=kind)
        output_jobs._jobs[job.job_id] = job
        return job

    monkeypatch.setattr(output_jobs, "start", fake_start)
    request = "Draft an approval note on the CCR1 inspection findings and save it"

    events = list(run_turn(request, session_id="t-both-a"))
    streamed = [e for e in events if e["type"] == "deck_job"][0]["job"]
    assert not [e for e in events if e["type"] == "approval_required"], (
        "an approval before the document exists is consent for something unwritten")

    state = run_agent_turn(request, "t-both-b")

    assert started == ["docx", "docx"]
    assert streamed["kind"] == "docx"
    assert state.deck_job_id == "docx-2"
    assert state.awaiting_human_approval is False


# ---------------------------------------------------------------------
# An approval is a record that a person authorised a SPECIFIC action.
# ---------------------------------------------------------------------


def test_an_approval_cannot_be_manufactured_for_a_request_that_does_not_exist():
    """The merged fallback caught any failure from approve() and, rather
    than reporting it, REGISTERED A NEW REQUEST and approved that --
    returning the caller's request_id with a token belonging to a
    different one.

    approve() fails for exactly the reasons that matter: the request
    expired (the TTL exists because a decision made in a context that is
    gone should not still act), was already used (single-use exists so
    one approval cannot authorise a retry loop), or never existed.
    """
    from fastapi.testclient import TestClient

    from backend.main import app

    client = TestClient(app)
    response = client.post(
        "/api/approvals/resolve",
        json={"request_id": "req-does-not-exist", "confirmed": True, "operator": "t"},
    )
    assert response.status_code in (404, 409), response.text
    assert "approved" not in response.text.lower() or response.status_code >= 400


def test_a_used_approval_cannot_be_approved_again():
    """Single-use is the property that stops one approval authorising a
    retry loop."""
    from fastapi.testclient import TestClient

    from backend.audit.approval_gate import ApprovalGate
    from backend.main import app

    gate = ApprovalGate()
    request = gate.request(
        tool_name="draft_docx",
        arguments={"title": "t", "sections": [], "output_path": "x.docx"},
        effect="test",
    )
    gate.approve(request.request_id, approved_by="first")

    client = TestClient(app)
    response = client.post(
        "/api/approvals/resolve",
        json={"request_id": request.request_id, "confirmed": True, "operator": "second"},
    )
    assert response.status_code >= 400, (
        "an already-approved request was approved a second time: "
        f"{response.text}"
    )


def test_a_refusal_that_was_not_recorded_does_not_report_success():
    """The audit log is the evidence that a person said no. Claiming an
    entry exists when it does not is a false record, and the direction of
    that lie is the dangerous one."""
    from fastapi.testclient import TestClient

    from backend.main import app

    client = TestClient(app)
    response = client.post(
        "/api/approvals/resolve",
        json={"request_id": "req-never-made", "confirmed": False, "operator": "t"},
    )
    assert response.status_code >= 400, response.text


def test_the_audit_endpoint_works_without_a_request_id():
    """My own bug, found by Advay: routes.py called log.entries(), which
    AuditLog does not have -- only all() and for_request(). Every call
    without a request_id was a 500, and nothing in the suite covered it.
    """
    from fastapi.testclient import TestClient

    from backend.main import app

    client = TestClient(app)
    response = client.get("/api/audit?limit=5")
    assert response.status_code == 200, response.text
    assert "entries" in response.json()
