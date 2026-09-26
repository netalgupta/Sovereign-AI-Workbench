from __future__ import annotations

"""Human approval gate — CLAUDE.md hard constraint #4, NFR-6, TOOLS.md row 67.

"No file write, send, or SAP write action without a human-approval-gate check."

Enforces:
1. Bound to a hash of the exact arguments — payload tampering is refused.
2. Single-use token — one approval cannot authorize a retry loop.
3. Expiration — requests expire after ttl_minutes (default 15). Expiry is
   evaluated dynamically on read so it survives application restarts.
4. Plain-language effect shown to the operator rather than raw function calls.
5. Append-only audit trail integration.
"""

import logging
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field

from backend.audit.audit_log import AuditEvent, AuditLog

logger = logging.getLogger(__name__)


class ApprovalState(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    EXECUTED = "executed"
    REFUSED = "refused"
    EXPIRED = "expired"


class ApprovalDenied(Exception):
    """Execution was denied because approval is missing, invalid, expired, or tampered."""


def hash_arguments(arguments: dict[str, Any]) -> str:
    """Compute a deterministic, order-independent SHA-256 hash of tool arguments."""
    serialized = json.dumps(arguments, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class ApprovalRequest(BaseModel):
    request_id: str
    tool_name: str
    arguments: dict[str, Any]
    arguments_hash: str
    effect: str
    state: ApprovalState = ApprovalState.PENDING
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    expires_at: str
    approved_by: str | None = None
    approved_at: str | None = None
    refused_by: str | None = None
    refusal_reason: str | None = None
    token: str | None = None


class ApprovedRequest(ApprovalRequest):
    token: str



# Argument values large enough to be document content rather than a
# parameter. A tag, a filename or a setpoint is short; a drafted
# section body is not.
_CONTENT_CHARS = 200


def _redact_content(arguments: dict[str, Any]) -> dict[str, Any]:
    """Replace document text with a description of what was there.

    WHY A TERMINAL REQUEST STOPS CARRYING THE DOCUMENT.

    A draft_docx approval stores its full `sections` so that executing
    it runs exactly what was approved -- that is the point of hashing
    the arguments. But once the request is EXECUTED, REFUSED or EXPIRED
    it will never run again, and the text stays on disk forever.

    Measured on this machine: requests.jsonl held 191 records, the
    largest 11,344 characters, containing seven full document sections
    -- one of them headed "Classification: Confidential - Internal Use".
    The corpus is already on this disk, so this is not a leak. It IS a
    second copy of confidential text, in a file with a different
    lifecycle and no expiry, which is precisely what an InfoSec reviewer
    is looking for under NFR-3 (STAKEHOLDERS.md puts IT/InfoSec against
    exactly that requirement).

    THE HASH IS NOT TOUCHED. arguments_hash still proves what was
    approved, so the audit record remains verifiable after the content
    is gone -- you can still show that the executed call matched the
    approved one, you just cannot re-read the document out of the
    approval file.

    Short values are kept: they are parameters, and an audit entry
    reading "redacted" where the filename used to be is worse than
    useless.
    """
    redacted: dict[str, Any] = {}
    for key, value in (arguments or {}).items():
        if isinstance(value, str) and len(value) > _CONTENT_CHARS:
            redacted[key] = f"<{len(value)} characters of document content, redacted>"
        elif isinstance(value, (list, tuple)):
            rendered = str(value)
            if len(rendered) > _CONTENT_CHARS:
                redacted[key] = (
                    f"<{len(value)} item(s), {len(rendered)} characters of "
                    f"document content, redacted>"
                )
            else:
                redacted[key] = value
        elif isinstance(value, dict):
            rendered = str(value)
            if len(rendered) > _CONTENT_CHARS:
                redacted[key] = f"<{len(rendered)} characters of content, redacted>"
            else:
                redacted[key] = value
        else:
            redacted[key] = value
    return redacted


# Tool names the interceptor uses for an instruction it could not resolve
# to a real, registered tool (no SAP, DCS or send connector exists here).
_UNWIRED_TOOLS = {"operator_requested_action", "unsupported_action"}


class ApprovalGate:
    """Manages human approval requests, single-use tokens, and audited execution."""

    def __init__(
        self,
        requests_file: Path | str | None = None,
        audit_log: AuditLog | None = None,
        ttl_minutes: int = 15,
    ) -> None:
        from backend.paths import REPO_ROOT

        # Anchored to the repository, not the working directory.
        self.requests_file = Path(requests_file or REPO_ROOT / "backend" / "audit" / "requests.jsonl")
        self.requests_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.requests_file.exists():
            self.requests_file.touch()

        self.audit = audit_log or AuditLog(self.requests_file.parent / "audit.jsonl")
        self.ttl_minutes = ttl_minutes

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _read_all(self) -> dict[str, ApprovalRequest]:
        requests: dict[str, ApprovalRequest] = {}
        if not self.requests_file.exists():
            return requests

        with open(self.requests_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    req = ApprovalRequest.model_validate_json(line)
                    # Check expiration dynamically
                    if req.state == ApprovalState.PENDING:
                        exp = datetime.fromisoformat(req.expires_at)
                        if self._now() >= exp:
                            req.state = ApprovalState.EXPIRED
                    requests[req.request_id] = req
                except Exception as exc:  # noqa: BLE001
                    logger.warning('Unreadable line in the approval ledger, skipped (a request on it cannot be approved)' + ": %s: %s", type(exc).__name__, exc)
                    continue
        return requests

    def _write_all(self, requests: dict[str, ApprovalRequest]) -> None:
        with open(self.requests_file, "w", encoding="utf-8") as f:
            for req in requests.values():
                f.write(req.model_dump_json() + "\n")
            f.flush()

    def request(self, tool_name: str, arguments: dict[str, Any], effect: str = "") -> ApprovalRequest:
        """Create a new approval request and record it in the audit log."""
        request_id = f"req-{uuid.uuid4().hex[:10]}"
        now = self._now()
        expires_at = (now + timedelta(minutes=self.ttl_minutes)).isoformat(timespec="seconds")
        arg_hash = hash_arguments(arguments)

        req = ApprovalRequest(
            request_id=request_id,
            tool_name=tool_name,
            arguments=arguments,
            arguments_hash=arg_hash,
            effect=effect or f"Execute {tool_name}",
            state=ApprovalState.PENDING,
            created_at=now.isoformat(timespec="seconds"),
            expires_at=expires_at,
        )

        all_reqs = self._read_all()
        all_reqs[request_id] = req
        self._write_all(all_reqs)

        self.audit.log(
            event=AuditEvent.APPROVAL_REQUESTED,
            request_id=request_id,
            actor="system",
            summary=f"Approval requested for {tool_name}: {effect or tool_name}",
            details={"arguments_hash": arg_hash, "effect": effect},
        )
        return req

    def approve(self, request_id: str, approved_by: str) -> ApprovedRequest:
        """Approve a pending request and issue a single-use authorization token."""
        all_reqs = self._read_all()
        req = all_reqs.get(request_id)
        if not req:
            raise ApprovalDenied(f"Approval request {request_id!r} does not exist.")

        now = self._now()
        if req.state == ApprovalState.EXPIRED or now >= datetime.fromisoformat(req.expires_at):
            req.state = ApprovalState.EXPIRED
            self._write_all(all_reqs)
            raise ApprovalDenied("Approval request has expired.")

        if req.state == ApprovalState.REFUSED:
            raise ApprovalDenied("Approval request was already refused.")
        if req.state == ApprovalState.EXECUTED:
            raise ApprovalDenied("Approval request has already been executed.")
        if req.state == ApprovalState.APPROVED:
            raise ApprovalDenied("Approval request has already been approved.")

        token = f"tok-{uuid.uuid4().hex}"
        req.state = ApprovalState.APPROVED
        req.approved_by = approved_by
        req.approved_at = now.isoformat(timespec="seconds")
        req.token = token

        all_reqs[request_id] = req
        self._write_all(all_reqs)

        self.audit.log(
            event=AuditEvent.APPROVAL_GRANTED,
            request_id=request_id,
            actor=approved_by,
            summary=f"Approval granted for {req.tool_name} by {approved_by}",
            details={"approved_at": req.approved_at},
        )

        return ApprovedRequest.model_validate(req.model_dump())

    def refuse(self, request_id: str, refused_by: str, reason: str = "") -> ApprovalRequest:
        """Refuse a pending request and record the refusal reason."""
        all_reqs = self._read_all()
        req = all_reqs.get(request_id)
        if not req:
            raise ApprovalDenied(f"Approval request {request_id!r} does not exist.")

        if req.state == ApprovalState.EXPIRED:
            raise ApprovalDenied("Approval request has expired.")
        if req.state == ApprovalState.EXECUTED:
            raise ApprovalDenied("Approval request has already been executed.")

        req.state = ApprovalState.REFUSED
        req.refused_by = refused_by
        req.refusal_reason = reason
        # Refused means it will never run. Same reasoning as execution:
        # the hash stays, the document text does not.
        req.arguments = _redact_content(req.arguments)
        req.token = None

        all_reqs[request_id] = req
        self._write_all(all_reqs)

        self.audit.log(
            event=AuditEvent.APPROVAL_REFUSED,
            request_id=request_id,
            actor=refused_by,
            summary=f"Approval refused for {req.tool_name}: {reason}",
            details={"refusal_reason": reason},
        )
        return req

    def execute_approved(
        self, request_id: str, token: str, arguments: dict[str, Any] | None = None
    ) -> Any:
        """Execute a tool authorized by a valid single-use token and verified payload."""
        from backend.tools import catalog  # noqa: F401 — ensure tools are registered
        from backend.tools.registry import call_tool

        all_reqs = self._read_all()
        req = all_reqs.get(request_id)
        if not req:
            raise ApprovalDenied(f"Approval request {request_id!r} does not exist.")

        if req.state == ApprovalState.EXPIRED:
            raise ApprovalDenied("Approval request has expired.")

        if req.state == ApprovalState.EXECUTED:
            raise ApprovalDenied("Approval token has already been used.")

        if req.state != ApprovalState.APPROVED:
            raise ApprovalDenied(f"Request {request_id} is not approved (current state: {req.state.value}).")

        if not req.token or req.token != token:
            raise ApprovalDenied("Invalid approval token.")

        args_to_use = arguments if arguments is not None else req.arguments
        if arguments is not None:
            passed_hash = hash_arguments(arguments)
            if passed_hash != req.arguments_hash:
                raise ApprovalDenied(
                    "Execution arguments differ from what was approved (payload hash mismatch)."
                )

        # Single-use: invalidate token immediately before executing
        req.state = ApprovalState.EXECUTED
        req.token = None
        all_reqs[request_id] = req
        self._write_all(all_reqs)

        try:
            if req.tool_name not in ("generate_deck",) and req.tool_name in _UNWIRED_TOOLS:
                # An action with no connector in this build. Approving it
                # RECORDS the operator's authorisation; it cannot cause the
                # action, and must not claim it did.
                #
                # THIS REPLACED A FABRICATED DOCUMENT. The merged branch
                # wrote a fixed "Hydrocracker Unit Inspection Report" here
                # -- invented feed rate (1,450 m3/h), invented valve tags
                # (QFC-18, BDV-201), invented sources -- for ANY approved
                # instruction containing "draft", "report" or "document".
                # A refinery report nobody measured, written to disk, over
                # a signed approval record. Review rule 4: fields the
                # system cannot know are absent, never plausible.
                result = {
                    "executed": False,
                    "authorisation_recorded": True,
                    "effect": req.effect,
                    "reason": ("No connector in this build can carry this out. Your authorisation "
                               "is recorded in the audit log; nothing was performed."),
                }
            else:
                result = call_tool(req.tool_name, args_to_use, approved=True)
        except Exception as exc:
            self.audit.log(
                event=AuditEvent.TOOL_FAILED,
                request_id=request_id,
                actor=req.approved_by or "operator",
                summary=f"Tool {req.tool_name} failed: {type(exc).__name__}: {exc}",
                details={"error": str(exc)},
            )
            raise

        self.audit.log(
            event=AuditEvent.TOOL_EXECUTED,
            request_id=request_id,
            actor=req.approved_by or "operator",
            summary=f"Tool {req.tool_name} executed successfully",
            details={"effect": req.effect},
        )

        # The request is terminal and will never run again. Drop the
        # document content, keep the hash that proves what ran.
        terminal = self._read_all()
        if request_id in terminal:
            terminal[request_id].arguments = _redact_content(
                terminal[request_id].arguments
            )
            self._write_all(terminal)

        return result

    def get(self, request_id: str) -> ApprovalRequest:
        """Fetch request by ID, evaluating expiration dynamically."""
        all_reqs = self._read_all()
        req = all_reqs.get(request_id)
        if not req:
            raise ApprovalDenied(f"Request {request_id!r} does not exist.")
        return req

    def pending(self) -> list[ApprovalRequest]:
        """List currently active pending requests with tokens masked."""
        all_reqs = self._read_all()
        return [
            req.model_copy(update={"token": None})
            for req in all_reqs.values()
            if req.state == ApprovalState.PENDING
        ]
