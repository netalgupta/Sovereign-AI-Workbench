"""Long-term memory: what stays true across conversations.

WHAT BELONGS HERE, AND WHAT EMPHATICALLY DOES NOT.

BELONGS: things the USER told us about themselves or how they want to
be worked with.

    "I'm the Novolen unit engineer"
    "always give me values in metric"
    "our shift handover is at 06:00"
    "call HCU-2 the hydrocracker, that's what we say here"

DOES NOT BELONG: anything about the CONTENTS of a document.

    "the average MFI for H030SG is 3.4"        <- NO
    "the Hassan incident was on 2026-07-22"    <- NO

That second category is the whole point of the retrieval pipeline, and
storing it here would quietly create a second, uncited source of facts
that never expires and is never re-checked. A document gets revised; a
remembered number does not. The first time the corpus is updated and
this memory is not, the system answers confidently from a stale value
with no citation and no way for anyone to notice.

So this stores PREFERENCES AND IDENTITY, never findings. The
`_looks_like_a_document_fact` guard below enforces it at write time
rather than leaving it to the caller's judgement.

WHY EXTRACTION IS EXPLICIT, NOT AUTOMATIC.

Nothing is written here by watching the conversation and guessing. A
memory system that silently decides what to remember about a person is
one they cannot correct, and on a plant system it could quietly encode
a wrong assumption about someone's role into every future answer.

Facts are written when the user states one in a recognisable form, and
every one is listed, attributable to the turn that created it, and
deletable.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "backend" / "memory" / "long_term.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    fact_id     TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,          -- 'preference' | 'identity' | 'vocabulary'
    content     TEXT NOT NULL,
    source_session TEXT,
    created_at  REAL NOT NULL,
    last_used   REAL,
    use_count   INTEGER NOT NULL DEFAULT 0,
    metadata    TEXT NOT NULL DEFAULT '{}',
    -- What this fact is ABOUT, so a later statement on the same subject
    -- can replace it instead of sitting beside it.
    subject     TEXT,
    -- The fact that replaced this one. Superseded facts are kept, never
    -- deleted: "I used to work on HCU" is a real part of the record,
    -- and a memory that silently rewrites itself is one nobody can audit.
    superseded_by TEXT,
    superseded_at REAL
);
CREATE INDEX IF NOT EXISTS idx_facts_kind ON facts(kind);
"""

# Statements that are about the USER or how they work.
_PREFERENCE = re.compile(
    r"\b(always|never|from now on|going forward|prefer|please use|"
    r"i want you to|remember that i|by default|whenever i ask)\b",
    re.I,
)
_IDENTITY = re.compile(
    r"\b(i am|i'm|my name is|my role is|i work (on|in|at)|i handle|"
    r"i look after|my unit is|i'm the|we are the)\b",
    re.I,
)
_VOCABULARY = re.compile(
    r"\b(we call|we refer to|our term for|internally we say|"
    r"here we call|is known as)\b",
    re.I,
)

# A statement carrying a measurement is almost certainly a document
# finding, not a preference. Blocked at write time.
_DOCUMENT_FACT = re.compile(
    r"\d+(\.\d+)?\s*(g/10min|kg/cm|ppm|%|°c|c/hour|bar|kpa|mpa|hrs?|hours?|"
    r"months?|nm3|m3/h|mg|ml|litres?|liters?)\b",
    re.I,
)
_FINDING_VERB = re.compile(
    r"\b(the (average|value|result|reading|limit|spec|total) (is|was|of)|"
    r"measured at|recorded as|reported as|came out to)\b",
    re.I,
)


# WHAT A FACT IS ABOUT.
#
# Two statements conflict when they answer the same question about the
# same thing. "I work on HCU" and "I moved to CCR" both answer "which
# unit?", so the second replaces the first. "I work on HCU" and "always
# answer in bullet points" answer different questions and both stand.
#
# The subject is the lead-in phrase, normalised -- deliberately crude.
# A cleverer matcher would merge facts that only look similar, and a
# wrongly merged preference is invisible: the user is never told which
# of the two the system kept.
_SUBJECT_PATTERNS = [
    (re.compile(r"\bmy name is\b", re.I), "name"),
    (re.compile(r"\b(i am|i'?m)\s+the\b", re.I), "role"),
    (re.compile(r"\bmy role is\b", re.I), "role"),
    (re.compile(r"\bi work (on|in|at)\b", re.I), "unit"),
    (re.compile(r"\bmy unit is\b", re.I), "unit"),
    (re.compile(r"\bi (handle|look after)\b", re.I), "responsibility"),
    (re.compile(r"\b(we call|we refer to|our term for|here we call)\b", re.I),
     "vocabulary"),
]


def subject_of(text: str) -> str | None:
    """The thing a fact is about, or None when it is not on a known axis.

    None means "cannot supersede anything and cannot be superseded",
    which is the safe direction: an unrecognised statement is kept
    alongside whatever came before rather than silently replacing it.
    """
    for pattern, subject in _SUBJECT_PATTERNS:
        if pattern.search(text or ""):
            return subject
    return None


# How long a durable fact keeps applying without being restated or used.
# Not a guess dressed as a constant: the cost of expiring too early is
# the user repeating themselves once, and the cost of never expiring is
# a stale preference shaping every answer forever with no signal that it
# is doing so.
DEFAULT_TTL_DAYS = 180
_SECONDS_PER_DAY = 86400.0


@dataclass
class Fact:
    fact_id: str
    kind: str
    content: str
    source_session: str | None
    created_at: float
    last_used: float | None
    use_count: int
    subject: str | None = None
    superseded_by: str | None = None
    superseded_at: float | None = None

    @property
    def is_active(self) -> bool:
        return self.superseded_by is None

    def is_stale(self, now: float, ttl_days: int = DEFAULT_TTL_DAYS) -> bool:
        """Not used and not restated for a long time.

        Measured from last USE, not from creation: a preference that
        keeps being applied is evidently still wanted.
        """
        reference = self.last_used or self.created_at
        return (now - reference) > ttl_days * _SECONDS_PER_DAY


def _looks_like_a_document_fact(text: str) -> bool:
    """Would storing this create an uncited, non-expiring source of truth?

    Conservative on purpose: a preference wrongly rejected costs the
    user one repetition, while a document finding wrongly stored becomes
    a permanent uncited fact that survives the document being revised.
    """
    return bool(_DOCUMENT_FACT.search(text) or _FINDING_VERB.search(text))


def classify(text: str) -> str | None:
    """The kind of durable fact this is, or None if it is not one."""
    if not text or len(text.strip()) < 8:
        return None
    if _looks_like_a_document_fact(text):
        return None
    if _VOCABULARY.search(text):
        return "vocabulary"
    if _IDENTITY.search(text):
        return "identity"
    if _PREFERENCE.search(text):
        return "preference"
    return None


class LongTermMemory:
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
        """Add columns a database from an earlier build lacks."""
        existing = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(facts)").fetchall()
        }
        if not existing:
            return
        for column, decl in (
            ("subject", "TEXT"),
            ("superseded_by", "TEXT"),
            ("superseded_at", "REAL"),
        ):
            if column not in existing:
                self._conn.execute(f"ALTER TABLE facts ADD COLUMN {column} {decl}")

    def remember(
        self, content: str, kind: str | None = None, source_session: str | None = None
    ) -> Fact | None:
        """Store a durable fact. Returns None if it does not qualify.

        Returning None rather than raising: the caller offers every user
        message, and most are not facts. That is the normal case, not an
        error.
        """
        content = (content or "").strip()
        kind = kind or classify(content)
        if kind is None:
            return None
        if _looks_like_a_document_fact(content):
            # Explicit kind does not override the guard. A caller
            # insisting is exactly when this matters.
            return None

        subject = subject_of(content)
        with self._lock:
            existing = self._conn.execute(
                "SELECT fact_id FROM facts WHERE content = ? AND superseded_by IS NULL",
                (content,),
            ).fetchone()
            if existing:
                return self.get(existing["fact_id"])

            now_ts = time.time()
            fact = Fact(
                fact_id=f"f-{uuid.uuid4().hex[:12]}",
                kind=kind,
                content=content[:500],
                source_session=source_session,
                created_at=now_ts,
                last_used=None,
                use_count=0,
                subject=subject,
            )
            self._conn.execute(
                "INSERT INTO facts (fact_id, kind, content, source_session, "
                "created_at, last_used, use_count, metadata, subject) "
                "VALUES (?, ?, ?, ?, ?, NULL, 0, '{}', ?)",
                (fact.fact_id, fact.kind, fact.content, fact.source_session,
                 fact.created_at, subject),
            )

            # A NEW STATEMENT ON THE SAME AXIS REPLACES THE OLD ONE.
            #
            # Without this, "I work on HCU" and "I moved to CCR" both
            # persist and both get injected into every future prompt,
            # and the model is handed a contradiction about the user
            # with no way to tell which is current. Dedup was
            # exact-string only, which catches a repetition and misses
            # every actual change.
            #
            # The old fact is MARKED, not deleted. "I used to work on
            # HCU" is a real part of the record, and a memory that
            # quietly rewrites itself is one nobody can audit.
            if subject:
                self._conn.execute(
                    "UPDATE facts SET superseded_by = ?, superseded_at = ? "
                    "WHERE subject = ? AND fact_id != ? AND superseded_by IS NULL",
                    (fact.fact_id, now_ts, subject, fact.fact_id),
                )
            self._conn.commit()
        return fact

    def get(self, fact_id: str) -> Fact | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM facts WHERE fact_id = ?", (fact_id,)
            ).fetchone()
        return _row_to_fact(row) if row else None

    def all_facts(
        self, limit: int = 100, include_superseded: bool = False
    ) -> list[Fact]:
        """Durable facts, newest first.

        Superseded ones are excluded by default and available on
        request: they must not shape an answer, and they must still be
        inspectable, which are different requirements.
        """
        clause = "" if include_superseded else "WHERE superseded_by IS NULL "
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM facts {clause}ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row_to_fact(r) for r in rows]

    def expire_stale(self, ttl_days: int = DEFAULT_TTL_DAYS) -> list[Fact]:
        """Retire facts nothing has used or restated in a long time.

        Retired the same way as superseded ones -- marked, never
        deleted -- so "this stopped applying in March" remains
        answerable.
        """
        now_ts = time.time()
        retired = [
            f for f in self.all_facts(limit=1000) if f.is_stale(now_ts, ttl_days)
        ]
        if retired:
            with self._lock:
                self._conn.executemany(
                    "UPDATE facts SET superseded_by = 'expired', superseded_at = ? "
                    "WHERE fact_id = ?",
                    [(now_ts, f.fact_id) for f in retired],
                )
                self._conn.commit()
        return retired

    def forget(self, fact_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM facts WHERE fact_id = ?", (fact_id,))
            self._conn.commit()
            return cur.rowcount > 0

    def context_block(self, max_facts: int = 12) -> str:
        """Durable facts, formatted for a prompt and labelled.

        Labelled the same way conversation context is, and for the same
        reason: these are things the user said about themselves, not
        evidence about the plant.
        """
        facts = self.all_facts(limit=max_facts)
        if not facts:
            return ""
        lines = [
            "",
            "WHAT YOU KNOW ABOUT THIS USER (context only — NOT a source):",
            "Preferences and identity they have told you. Apply them to HOW "
            "you answer. They are never evidence about the plant; every "
            "factual claim still comes from the SOURCES section.",
            "",
        ]
        lines += [f"- {f.content}" for f in facts]
        lines.append("")

        with self._lock:
            now = time.time()
            self._conn.executemany(
                "UPDATE facts SET last_used = ?, use_count = use_count + 1 "
                "WHERE fact_id = ?",
                [(now, f.fact_id) for f in facts],
            )
            self._conn.commit()
        return "\n".join(lines)


def _column(row: sqlite3.Row, name: str):
    """A column's value, or None when the row predates the column."""
    try:
        return row[name]
    except (IndexError, KeyError):
        return None


def _row_to_fact(row: sqlite3.Row) -> Fact:
    return Fact(
        fact_id=row["fact_id"],
        kind=row["kind"],
        content=row["content"],
        source_session=row["source_session"],
        created_at=row["created_at"],
        last_used=row["last_used"],
        use_count=row["use_count"],
        subject=_column(row, "subject"),
        superseded_by=_column(row, "superseded_by"),
        superseded_at=_column(row, "superseded_at"),
    )


_memory: LongTermMemory | None = None
_memory_lock = threading.Lock()


def get_long_term() -> LongTermMemory:
    global _memory
    with _memory_lock:
        if _memory is None:
            _memory = LongTermMemory()
        return _memory


def reset_for_tests(db_path: Path | str) -> LongTermMemory:
    global _memory
    with _memory_lock:
        _memory = LongTermMemory(db_path)
        return _memory
