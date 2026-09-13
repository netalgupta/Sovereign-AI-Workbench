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

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field

from backend.audit.audit_log import AuditEvent, AuditLog


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


class ApprovalGate:
    """Manages human approval requests, single-use tokens, and audited execution."""

    def __init__(
        self,
        requests_file: Path | str | None = None,
        audit_log: AuditLog | None = None,
        ttl_minutes: int = 15,
    ) -> None:
        self.requests_file = Path(requests_file or "backend/audit/requests.jsonl")
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
                except Exception:
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
