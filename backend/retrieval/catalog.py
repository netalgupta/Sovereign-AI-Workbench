"""Where every indexed document lives: source, folders, neighbours.

The index knows documents by FILE NAME only. The operator thinks in
folders: "the SOPs", "the quality data", "what else is in the inspection
folder". Measured 27 Sep: "Find both sop summary and quality" retrieved
GRAPH_SPEC.md and an incident report -- the corpus's SOPs sit in
01_SOPs_and_Procedures and its quality records in
03_Quality_and_Process_Data, and retrieval could not see either name.

This module maps each indexed document to its place on disk, relative to
the source it came from, and turns that into:

  - location_scores(): how well a question's words match a document's
    folders and name (a ranking signal in hybrid_search);
  - location_label(): "MRPL_RAG_Test_Corpus / 03_Quality_and_Process_Data /
    Novolen_Batch_QA_Report_Aug2026.pdf", shown to the model with every
    passage so it understands where a fact came from;
  - folder_listing(): what a folder holds, for "what is in the SOP folder".

Built by walking the configured sources (the same roots the viewer
trusts) and cached until the index or the source list changes.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

_SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", ".workbench", "dist", "build"}
_lock = threading.Lock()
_cache: dict = {"key": None, "docs": {}}


@dataclass
class DocLocation:
    name: str
    path: str
    source: str                      # the configured source it belongs to
    folders: list[str] = field(default_factory=list)   # folders between source root and file

    @property
    def label(self) -> str:
        return " / ".join([self.source, *self.folders, self.name])

    @property
    def folder_label(self) -> str:
        return " / ".join([self.source, *self.folders])


# ── words ──────────────────────────────────────────────────────────────────

_STOP = frozenset("""
a an the and or of in on at to for from by with is are was were be it its this that these those
find show give list get me my our all both any some each every what which who where how why when
please tell about want need document documents file files doc docs report reports folder folders
summary summarise summarize summaries data record records info information details detail
""".split())


def _stem(word: str) -> str:
    w = word.lower()
    for suffix in ("ies",):
        if w.endswith(suffix) and len(w) > 4:
            return w[:-3] + "y"
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        return w[:-1]
    return w


def _words(text: str) -> set[str]:
    """'01_SOPs_and_Procedures' -> {'sop', 'procedure'}; numbers-only parts dropped."""
    out = set()
    for raw in re.split(r"[^A-Za-z0-9]+", text or ""):
        # split camelCase too: 'BatchQA' -> 'Batch', 'QA'
        for part in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", raw) or [raw]:
            if not part or part.isdigit() or len(part) < 2:
                continue
            w = _stem(part)
            if w not in _STOP:
                out.add(w)
    return out


# Common abbreviations in plant document names, both directions.
_ALIASES = {
    "qa": {"quality"}, "quality": {"qa", "qc"}, "qc": {"quality"},
    "sop": {"procedure"}, "procedure": {"sop"},
    "sap": {"erp"}, "pid": {"diagram"}, "diagram": {"pid", "drawing"},
    "inspection": {"maintenance"}, "correspondence": {"letter", "email", "thread"},
}


def _expand(words: set[str]) -> set[str]:
    out = set(words)
    for w in words:
        out |= _ALIASES.get(w, set())
    return out


# ── the catalog ────────────────────────────────────────────────────────────

def _roots() -> list[tuple[str, Path]]:
    from backend.api import source_config

    named = []
    names = {str(Path(e.get("path", "")).resolve()).lower(): e.get("name") for e in source_config.load()
             if isinstance(e, dict) and e.get("path")}
    for root in source_config.source_roots():
        named.append((names.get(str(root).lower()) or root.name, root))
    return named


def _build(document_names: set[str]) -> dict[str, DocLocation]:
    found: dict[str, DocLocation] = {}
    for source, root in _roots():
        if root.is_file():
            if root.name in document_names and root.name not in found:
                found[root.name] = DocLocation(root.name, str(root), source, [])
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.name not in document_names or path.name in found:
                continue
            rel = path.relative_to(root)
            if any(part in _SKIP_DIRS for part in rel.parts):
                continue
            found[path.name] = DocLocation(path.name, str(path), source, list(rel.parts[:-1]))
    # a file attached in one chat: its "folder" is that chat
    try:
        from backend.retrieval import chat_attachments

        for a_name in document_names - set(found):
            entry = chat_attachments._load().get(a_name)
            if entry:
                found[a_name] = DocLocation(a_name, entry.get("path", ""), "Attached in a chat", [])
    except Exception:  # noqa: BLE001 - attachments are optional here
        pass
    return found


def catalog(store) -> dict[str, DocLocation]:
    """{document name: DocLocation} for every indexed document, cached."""
    from backend.api import source_config

    names = set(store.document_names())
    try:
        generation = store.generation()
    except Exception:  # noqa: BLE001
        generation = len(names)
    key = (generation, len(names), tuple(str(r) for r in source_config.source_roots()))
    with _lock:
        if _cache["key"] != key:
            _cache["docs"] = _build(names)
            _cache["key"] = key
        return _cache["docs"]


def location_label(store, name: str) -> str:
    loc = catalog(store).get(name)
    return loc.label if loc else name


def location_scores(store, query: str, allowed: set[str] | None = None) -> dict[str, float]:
    """How strongly the question's own words name each document's place.

    A word matching one of the document's FOLDERS counts 1.0; one matching
    its file name counts 0.8. Only documents with a match are returned.
    """
    q = _expand(_words(query))
    if not q:
        return {}
    scores: dict[str, float] = {}
    for name, loc in catalog(store).items():
        if allowed is not None and name not in allowed:
            continue
        folder_words = _expand(set().union(*(_words(f) for f in loc.folders))) if loc.folders else set()
        name_words = _expand(_words(Path(name).stem))
        score = len(q & folder_words) * 1.0 + len((q - folder_words) & name_words) * 0.8
        if score:
            scores[name] = score
    return scores


def folder_listing(store, query: str) -> list[tuple[str, list[DocLocation]]]:
    """Folders whose own names the question matches, with the documents in each."""
    q = _expand(_words(query))
    groups: dict[str, list[DocLocation]] = {}
    for loc in catalog(store).values():
        for depth in range(1, len(loc.folders) + 1):
            if q & _expand(_words(loc.folders[depth - 1])):
                key = " / ".join([loc.source, *loc.folders[:depth]])
                groups.setdefault(key, []).append(loc)
    return sorted(groups.items())
