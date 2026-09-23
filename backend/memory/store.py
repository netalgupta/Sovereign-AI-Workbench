from __future__ import annotations

"""Durable sessions, messages, and per-turn artifacts.

WHY THIS EXISTS. `session_id` was threaded through every request and
stored nowhere. Each turn began from nothing, which produced this,
measured on a real conversation:

    user: "Summarise the maintenance log of Q3..."
    ->    a table of downtime BY FAULT CATEGORY

    user: "U gave the summary for fault category i want for equipments"
    ->    worked, but only because the words "fault category" and
          "equipment" happened to retrieve the same spreadsheet

    user: "Give all columns"
    ->    returned the FAULT CATEGORY table again, and added "the
          downtime for Mechanical and Catalyst-Related are highlighted
          in bold as they were specifically asked to be given in a
          single figure" -- an instruction nobody had given, invented to
          explain a table it could not remember producing

    user: "Also display all the metrics and give proper numbers"
    ->    answered about MFI for Homopolymer H110F. The conversation was
          about PSA hydrogen purity and sulphur compliance.

Every one of those is the same defect: a follow-up is not a standalone
question, and this system treated it as one.

THE SAFETY PROPERTY THAT SHAPES THIS WHOLE PACKAGE.

Memory informs INTERPRETATION. It never supplies FACTS.

Remembering that the last answer was about the Q3 maintenance log is
what lets "give all columns" be understood. It must never become a
licence to answer from that memory: the numbers still come from
retrieval, and still carry citations, every time. A remembered value is
an uncited value, and this product's entire claim is that it does not
produce those.

That line is enforced structurally, not by discipline -- see
`resolver.py`, which rewrites the QUERY and is forbidden from touching
the answer, and `working.py`, whose context block is labelled as
conversational context rather than as sources.

SQLite because it is already a dependency (the vector store uses it),
it survives a restart, and a session that vanishes when uvicorn reloads
is not memory.
"""

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "backend" / "memory" / "sessions.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT PRIMARY KEY,
    title        TEXT,
    created_at   REAL NOT NULL,
    updated_at   REAL NOT NULL,
    turn_count   INTEGER NOT NULL DEFAULT 0,
    metadata     TEXT NOT NULL DEFAULT '{}',
    -- Turns that have fallen out of the live window, condensed. See
    -- digest.py: extractive, never generated, so it cannot invent a
    -- prior answer.
    digest       TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS messages (
    message_id   TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL,
    turn_index   INTEGER NOT NULL,
    role         TEXT NOT NULL,          -- 'user' | 'assistant'
    content      TEXT NOT NULL,
    created_at   REAL NOT NULL,
    -- Everything the turn actually did, so a later turn can be
    -- interpreted against what really happened rather than against a
    -- summary of it.
    route        TEXT,
    citations    TEXT NOT NULL DEFAULT '[]',
    documents    TEXT NOT NULL DEFAULT '[]',
    tool_calls   TEXT NOT NULL DEFAULT '[]',
    -- Equipment tags, units and pipeline segments this turn touched.
    -- Kept apart from `documents` because the thing a follow-up names
    -- is more often "the Hassan segment" than a filename.
    entities     TEXT NOT NULL DEFAULT '[]',
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_session
    ON messages(session_id, turn_index);
"""


@dataclass
class Message:
    message_id: str
    session_id: str
    turn_index: int
    role: str
    content: str
    created_at: float
    route: str | None = None
    citations: list = field(default_factory=list)
    documents: list = field(default_factory=list)
    tool_calls: list = field(default_factory=list)
    entities: list = field(default_factory=list)


@dataclass
class Session:
    session_id: str
    title: str | None
    created_at: float
    updated_at: float
    turn_count: int
    metadata: dict = field(default_factory=dict)


class SessionStore:
    """Sessions and their messages, on disk.

    One connection guarded by a lock rather than a pool: writes here are
    a handful per turn against a local file, and a pool would add a
    failure mode (a leaked connection holding a write lock) for no
    measurable gain at this volume.
    """

    def __init__(self, db_path: Path | str = DB_PATH) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._migrate()
            self._conn.commit()

    def _migrate(self) -> None:
        """Add columns that a database created by an earlier build lacks.

        CREATE TABLE IF NOT EXISTS does nothing to a table that already
        exists, so a schema change is invisible to every developer who
        already has the file -- and the failure arrives later as
        "no such column", from a query, at the moment someone is using
        it. The database is gitignored, so this affects exactly the
        people whose sessions are worth keeping.
        """
        wanted = {
            "messages": {
                "route": "TEXT",
                "citations": "TEXT NOT NULL DEFAULT '[]'",
                "documents": "TEXT NOT NULL DEFAULT '[]'",
                "tool_calls": "TEXT NOT NULL DEFAULT '[]'",
                "entities": "TEXT NOT NULL DEFAULT '[]'",
            },
            "sessions": {
                "metadata": "TEXT NOT NULL DEFAULT '{}'",
                "digest": "TEXT NOT NULL DEFAULT '{}'",
            },
        }
        for table, columns in wanted.items():
            existing = {
                row["name"]
                for row in self._conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if not existing:
                continue
            for column, decl in columns.items():
                if column not in existing:
                    self._conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN {column} {decl}"
                    )

    # ---------------------------------------------------------- sessions

    def ensure_session(self, session_id: str | None = None, title: str | None = None) -> str:
        """Return an existing session id, or create one.

        Accepts the id the caller already has -- the frontend generates a
        UUID per conversation and has been sending it all along. Ignoring
        it and minting a new one would orphan every message the client
        thinks it owns.
        """
        session_id = session_id or f"s-{uuid.uuid4().hex[:12]}"
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO sessions "
                "(session_id, title, created_at, updated_at, turn_count) "
                "VALUES (?, ?, ?, ?, 0)",
                (session_id, title, now, now),
            )
            self._conn.commit()
        return session_id

    def get_session(self, session_id: str) -> Session | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None:
            return None
        return Session(
            session_id=row["session_id"],
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            turn_count=row["turn_count"],
            metadata=json.loads(row["metadata"] or "{}"),
        )

    def list_sessions(self, limit: int = 50) -> list[Session]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            Session(
                session_id=r["session_id"],
                title=r["title"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                turn_count=r["turn_count"],
                metadata=json.loads(r["metadata"] or "{}"),
            )
            for r in rows
        ]

    def set_title(self, session_id: str, title: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET title = ?, updated_at = ? WHERE session_id = ?",
                (title[:120], time.time(), session_id),
            )
            self._conn.commit()

    def delete_session(self, session_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            self._conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            self._conn.commit()

    # ---------------------------------------------------------- messages

    def append(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        route: str | None = None,
        citations: list | None = None,
        documents: list | None = None,
        tool_calls: list | None = None,
        entities: list | None = None,
    ) -> Message:
        """Record one message and return it.

        `documents` is stored separately from `citations` deliberately.
        Citations are what the answer cited; documents are what the turn
        LOOKED AT. A follow-up like "give all columns" needs the second:
        the table it refers to may have come from a chunk the answer
        never explicitly cited.
        """
        self.ensure_session(session_id)
        now = time.time()
        with self._lock:
            turn_index = self._conn.execute(
                "SELECT COALESCE(MAX(turn_index), -1) + 1 FROM messages WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]
            message = Message(
                message_id=f"m-{uuid.uuid4().hex[:12]}",
                session_id=session_id,
                turn_index=turn_index,
                role=role,
                content=content,
                created_at=now,
                route=route,
                citations=citations or [],
                documents=documents or [],
                tool_calls=tool_calls or [],
                entities=entities or [],
            )
            self._conn.execute(
                "INSERT INTO messages (message_id, session_id, turn_index, role, "
                "content, created_at, route, citations, documents, tool_calls, "
                "entities) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    message.message_id, session_id, turn_index, role, content, now,
                    route,
                    json.dumps(message.citations)[:200000],
                    json.dumps(message.documents),
                    json.dumps(message.tool_calls)[:200000],
                    json.dumps(message.entities),
                ),
            )
            self._conn.execute(
                "UPDATE sessions SET updated_at = ?, "
                "turn_count = turn_count + (CASE WHEN ? = 'user' THEN 1 ELSE 0 END) "
                "WHERE session_id = ?",
                (now, role, session_id),
            )
            self._conn.commit()
        return message

    def recent(self, session_id: str, limit: int = 10) -> list[Message]:
        """The last `limit` messages, oldest first."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE session_id = ? "
                "ORDER BY turn_index DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [_row_to_message(r) for r in reversed(rows)]

    def messages_before(
        self, session_id: str, turn_index: int | None, after: int = -1
    ) -> list[Message]:
        """Messages that have fallen out of the live window, oldest first.

        `after` is the highest turn already folded into the digest, so
        repeated calls hand back only what is new. Returns [] when the
        window still covers everything.
        """
        if turn_index is None:
            return []
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE session_id = ? "
                "AND turn_index < ? AND turn_index > ? ORDER BY turn_index",
                (session_id, turn_index, after),
            ).fetchall()
        return [_row_to_message(r) for r in rows]

    def get_digest(self, session_id: str) -> dict:
        with self._lock:
            row = self._conn.execute(
                "SELECT digest FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if not row or not row["digest"]:
            return {}
        try:
            return json.loads(row["digest"])
        except json.JSONDecodeError:
            return {}

    def set_digest(self, session_id: str, digest: dict) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET digest = ? WHERE session_id = ?",
                (json.dumps(digest)[:200000], session_id),
            )
            self._conn.commit()

    def all_messages(self, session_id: str) -> list[Message]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY turn_index",
                (session_id,),
            ).fetchall()
        return [_row_to_message(r) for r in rows]


def _column(row: sqlite3.Row, name: str):
    """A column's value, or None when this row predates the column."""
    try:
        return row[name]
    except (IndexError, KeyError):
        return None


def _row_to_message(row: sqlite3.Row) -> Message:
    return Message(
        message_id=row["message_id"],
        session_id=row["session_id"],
        turn_index=row["turn_index"],
        role=row["role"],
        content=row["content"],
        created_at=row["created_at"],
        route=row["route"],
        citations=json.loads(row["citations"] or "[]"),
        documents=json.loads(row["documents"] or "[]"),
        tool_calls=json.loads(row["tool_calls"] or "[]"),
        # A row written before the column existed reads as absent,
        # not as an error.
        entities=json.loads(_column(row, "entities") or "[]"),
    )


_store: SessionStore | None = None
_store_lock = threading.Lock()


def get_store() -> SessionStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = SessionStore()
        return _store


def reset_store_for_tests(db_path: Path | str) -> SessionStore:
    """Point the singleton at a temp database. Tests only."""
    global _store
    with _store_lock:
        _store = SessionStore(db_path)
        return _store
