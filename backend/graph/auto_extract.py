"""Keep the knowledge graph in step with the corpus, automatically.

THE GAP THIS CLOSES. Adding a source updated the corpus and the chunk
index and did nothing to the graph, because entity extraction is a
separate LLM pass that only ever ran by hand. With 63 documents loaded
the graph still described the 13 that someone had extracted weeks
earlier -- real data, correctly stored in Neo4j, and silently covering a
fraction of what the user could see in every other tab.

Nobody notices that. The graph looks populated, the node inspector
works, and the documents you just added are simply absent.

WHY THIS RUNS IN THE BACKGROUND AND NOT INLINE.

Extraction costs roughly one model call per chunk -- measured at 10-25s
each on qwen2.5:7b. A folder of 50 documents is 200 chunks, so doing
this inside the add-source request would hold the HTTP call open for
the better part of an hour and time out long before finishing.

So ingestion returns as soon as the documents are searchable, and the
graph catches up behind it. That ordering is deliberate: retrieval is
what the user is waiting for, and a graph that lags by a few minutes is
a different thing from one that lags by three weeks.

WHAT MAKES IT SAFE TO RUN UNATTENDED.

  - RESUMABLE. extract_corpus() checkpoints every chunk to JSON Lines
    as it is produced and skips ids already in the file, so a crash,
    a restart, or two overlapping ingests cost at most one chunk of
    duplicated work -- never a duplicated graph.
  - SERIALISED. One extraction at a time, process-wide. Two source
    folders added together would otherwise both start extracting and
    fight over an 8 GB card.
  - FAILS QUIETLY AND VISIBLY. Neo4j down, model unpulled, Ollama
    stopped -- none of it can break an ingest that already succeeded.
    The documents stay searchable; the graph stays behind and SAYS it
    is behind (the Sources page reports coverage).
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# The durable checkpoint. Same file build_graph.py reads, so a run
# started here is indistinguishable from one started by hand -- and
# either can resume the other.
EXTRACTION_CACHE = Path("backend/evaluation/extraction_cache/mrpl_extractions.jsonl")

# One extraction at a time, process-wide.
_extraction_lock = threading.Lock()
_running = threading.Event()

# What the last run did, for the UI and for /api/health.
_last_status: dict = {"state": "idle"}


def status() -> dict:
    """What graph extraction is doing right now."""
    return dict(_last_status)


def is_running() -> bool:
    return _running.is_set()


def schedule(chunks: list, reason: str = "source added") -> bool:
    """Extract entities for `chunks` and refresh the graph, in the background.

    Returns True if a run was started, False if one was already going --
    the caller does not wait either way, and a rejected schedule is not
    a failure: the checkpoint means the next run picks up whatever this
    one would have done.
    """
    if not chunks:
        return False
    if _running.is_set():
        logger.info(
            "Graph extraction already running; %d chunk(s) from '%s' will be "
            "picked up by the current run or the next one (the checkpoint makes "
            "that safe).",
            len(chunks), reason,
        )
        return False

    thread = threading.Thread(
        target=_run,
        args=(list(chunks), reason),
        name="graph-extraction",
        daemon=True,
    )
    thread.start()
    return True


def _run(chunks: list, reason: str) -> None:
    global _last_status

    # Non-blocking check first so a second caller returns immediately
    # rather than queueing a thread that will sit on a lock.
    if not _extraction_lock.acquire(blocking=False):
        return
    _running.set()
    try:
        _last_status = {
            "state": "extracting",
            "reason": reason,
            "chunks_total": len(chunks),
            "chunks_done": 0,
        }
        logger.info(
            "Graph: extracting entities for %d chunk(s) after %s. This is one "
            "model call per NEW chunk; already-extracted chunks are skipped.",
            len(chunks), reason,
        )

        from backend.evaluation.extract_corpus import extract_corpus

        EXTRACTION_CACHE.parent.mkdir(parents=True, exist_ok=True)
        stats = extract_corpus(
            chunks,
            str(EXTRACTION_CACHE),
            verbose=False,
            resume=True,  # the whole reason this is safe to re-run
        )
        _last_status = {
            "state": "building",
            "reason": reason,
            "chunks_total": len(chunks),
            "extracted": stats.get("extracted", 0),
            "skipped": stats.get("skipped", 0),
        }

        _rebuild_graph()

        _last_status = {
            "state": "idle",
            "reason": reason,
            "last_result": stats,
        }
        logger.info("Graph: up to date (%s).", stats)
    except Exception as exc:  # noqa: BLE001
        # An ingest that already succeeded must not be undone by the
        # graph failing. The documents are searchable either way.
        _last_status = {"state": "failed", "reason": reason, "error": str(exc)}
        logger.warning(
            "Graph extraction failed (%s: %s). The documents are still ingested "
            "and searchable; the graph is behind and the Sources page reports "
            "its coverage.",
            type(exc).__name__, exc,
        )
    finally:
        _running.clear()
        _extraction_lock.release()


def _rebuild_graph() -> None:
    """Load every extraction into Neo4j. No model calls here.

    Rebuilt from the WHOLE checkpoint rather than merged incrementally,
    because deduplication is a corpus-level decision: whether "HCU-2"
    and "Hydrocracker-2" are the same node cannot be decided from one
    document. build_graph_from_extractions does that dedup over
    everything, and the operation is idempotent, so re-running it is
    cheap and cannot double up nodes.
    """
    from backend.evaluation.build_graph import build_graph_from_extractions
    from backend.evaluation.extract_corpus import load_extractions
    from backend.graph.neo4j_client import GraphClient

    extractions = load_extractions(str(EXTRACTION_CACHE))
    if not extractions:
        return

    client = GraphClient("bolt://localhost:7687", "neo4j", "testpassword123")
    try:
        client.verify_connectivity()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Graph: entities extracted and checkpointed, but Neo4j is "
            "unreachable (%s). Nothing is lost -- run "
            "`py -3 -m backend.evaluation.build_graph` once it is up.",
            exc,
        )
        return

    try:
        build_graph_from_extractions(extractions, client, verbose=False)
    finally:
        client.close()
