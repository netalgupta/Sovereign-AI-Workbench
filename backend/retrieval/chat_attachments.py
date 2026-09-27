"""Chat attachments: sources that belong to ONE chat.

A file attached in a chat is indexed like any source -- same extraction,
chunking, embedding -- but it is not global. It is searchable from the chat
it was attached to and from nowhere else: not other chats, not new chats,
not the Sources list.

WHY. A temporary attachment used to travel only with the message it was
attached to. The follow-up ("List all schools", about the same workbook)
was answered without the file -- "the sources do not mention schools".
As a source of that chat, it is there for every later question.

HOW THE SCOPE IS ENFORCED (fail closed). Retrieval without an explicit
document list never searches chat attachments (grounded_retrieval). The
owning chat names its own attachments explicitly (scope_documents), so a
code path that forgets the chat can only fail to find the file -- never
show one chat's file in another.

Files live under storage/chat_attachments/<session_id>/; registry.json maps
each indexed document name to its chat.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path

from backend.paths import REPO_ROOT

ROOT = REPO_ROOT / "storage" / "chat_attachments"
_REGISTRY = "registry.json"
_lock = threading.RLock()

_SAFE_SESSION = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


def _registry_path() -> Path:
    return ROOT / _REGISTRY


def _load() -> dict:
    try:
        data = json.loads(_registry_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data: dict) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    tmp = _registry_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, _registry_path())


def session_dir(session_id: str) -> Path:
    if not _SAFE_SESSION.match(session_id or ""):
        raise ValueError(f"Not a chat id: {session_id!r}")
    return ROOT / session_id


def register(session_id: str, path: Path) -> str:
    """Record `path` (already saved under session_dir) as this chat's. Returns its document name."""
    name = Path(path).name
    with _lock:
        data = _load()
        data[name] = {"session_id": session_id, "path": str(Path(path).resolve()), "added_at": time.time()}
        _save(data)
    return name


def retire(session_id: str, name: str) -> dict | None:
    """Remove an attachment from its chat.

    RETIRED, not deleted from the registry: the index has no document
    removal, so the chunks stay in it -- and a name missing from the
    registry would read as a GLOBAL document. A retired name stays hidden
    from every chat and is listed by none.
    """
    with _lock:
        data = _load()
        entry = data.get(name)
        if not entry or entry.get("session_id") != session_id or entry.get("retired"):
            return None
        entry["retired"] = True
        _save(data)
        return entry


def all_names() -> set[str]:
    """Every chat attachment's document name, whichever chat owns it (retired included)."""
    return set(_load())


def for_session(session_id: str | None) -> list[dict]:
    if not session_id:
        return []
    return [
        {"name": name, **entry}
        for name, entry in sorted(_load().items(), key=lambda kv: kv[1].get("added_at", 0))
        if entry.get("session_id") == session_id and not entry.get("retired")
    ]


def unique_name(session_id: str, filename: str) -> str:
    """A document name no other source or chat attachment already uses.

    Documents are identified by name in the index, so two chats attaching
    "report.pdf" must not collide -- nor may an attachment shadow a
    corpus document of the same name.
    """
    base = Path(filename).name or "attachment"
    stem, suffix = Path(base).stem, Path(base).suffix
    taken = all_names()
    try:
        from backend.api.state import get_state

        taken |= set(get_state().ensure_corpus()[0].document_names())
    except Exception:  # noqa: BLE001 - no store yet: nothing indexed to collide with
        pass
    if base not in taken:
        return base
    tag = session_id.split("-")[0][:8]
    candidate = f"{stem} ({tag}){suffix}"
    n = 2
    while candidate in taken:
        candidate = f"{stem} ({tag} {n}){suffix}"
        n += 1
    return candidate


def scope_documents(session_id: str | None, active_documents: list[str] | None, store) -> list[str] | None:
    """The document list a chat's question may search.

    None (no filter) stays None when this chat has no attachments: every
    global source, and -- by the retrieval default -- no chat's attachments.
    A chat WITH attachments gets an explicit list: the global sources it
    has on (all of them for None) plus its own attachments, minus any it
    switched off (the frontend sends those names only when on).
    """
    mine = [a["name"] for a in for_session(session_id)]
    if not mine:
        return active_documents
    if active_documents is not None:
        # the frontend lists this chat's attachments it has switched ON
        return list(active_documents)
    hidden = all_names()
    everything = [d for d in store.document_names() if d not in hidden]
    return everything + mine
