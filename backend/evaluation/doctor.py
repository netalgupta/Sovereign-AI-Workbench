"""Why is it broken on my machine? Answered in one command.

    py -3 -m backend.evaluation.doctor

WHY THIS EXISTS. "Someone did something that broke everything" followed
by "add source broke too" is not a diagnosis, and the failure is almost
never where it is felt. The Sources page is a worked example of that:

    the frontend's vite dev server DEFERS /api/sources and /api/corpus
    to the real backend WHEN IT IS UP, and serves its own fallback
    implementation when it is not -- and that fallback still POSTs to
    127.0.0.1:8000/api/sources/ingest.

So a backend that fails to start does not look like a backend problem.
It looks like "add source is broken" and "my documents disappeared",
two layers away, with no error naming the cause.

Every check below prints what it found, not just pass/fail, because the
value is in the detail: "embedding backend: deterministic-hash" is the
answer to a week of confusing results, and "OK" is not.

Checks are ordered so the FIRST failure is usually the real one. Stop
reading at the first FAIL.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

OK = "OK  "
WARN = "WARN"
FAIL = "FAIL"


def _line(status: str, name: str, detail: str) -> None:
    print(f"  {status}  {name}")
    if detail:
        print(f"        {detail}")


def check_working_directory() -> None:
    """The one that silently empties the Sources page.

    routes.py resolves configured_sources.json against Path.cwd(), so
    starting uvicorn from anywhere other than the repo root means the
    watched-folder list is not found and the corpus comes back empty --
    with no error, because an absent config file is a legitimate state
    for a fresh install.
    """
    cwd = Path.cwd().resolve()
    if cwd == ROOT:
        _line(OK, "working directory", str(cwd))
        return
    _line(
        FAIL,
        "working directory",
        f"you are in {cwd}\n        the repo root is {ROOT}\n"
        f"        Source configuration is resolved against the CURRENT directory, so "
        f"starting the backend from anywhere else gives you an empty corpus and no error. "
        f"cd to the repo root and start it again.",
    )


def check_source_config() -> None:
    config = ROOT / "backend" / "evaluation" / "configured_sources.json"
    if not config.exists():
        _line(
            WARN,
            "configured sources",
            f"{config.name} does not exist. This is normal on a fresh clone -- it is "
            f"gitignored per-machine state -- and it means NO folders are being watched "
            f"yet. Add one in the Sources panel.",
        )
        return
    try:
        import json

        entries = json.loads(config.read_text(encoding="utf-8"))
        _line(OK, "configured sources", f"{len(entries)} folder(s) configured")
    except Exception as exc:  # noqa: BLE001
        _line(FAIL, "configured sources", f"{config.name} is unreadable: {exc}")


def check_embeddings() -> None:
    """The failure that produces confident, wrong answers.

    Without the 1.3 GB model, retrieval silently uses hash vectors:
    searches return results, answers carry citations, and the content is
    wrong. It cost a teammate a full session.
    """
    try:
        from backend.ingestion.embeddings import active_backend, degraded_reason

        backend_name = active_backend()
        reason = degraded_reason()
        if "hash" in (backend_name or "").lower():
            _line(
                FAIL,
                "embedding backend",
                f"{backend_name} -- RETRIEVAL IS MEANINGLESS. Searches still return "
                f"results and answers still carry citations; the content is wrong.\n"
                f"        {reason or ''}\n"
                f"        Fix: py -3 -m backend.ingestion.fetch_models",
            )
        else:
            _line(OK, "embedding backend", backend_name)
    except Exception as exc:  # noqa: BLE001
        _line(FAIL, "embedding backend", f"could not be determined: {exc}")


def check_ollama() -> None:
    try:
        import requests

        from backend.models.ollama_client import OLLAMA_HOST

        res = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=4)
        res.raise_for_status()
        pulled = {m["name"] for m in res.json().get("models", [])}
        _line(OK, "ollama", f"{OLLAMA_HOST}, {len(pulled)} model(s) pulled")
        _check_registry_against(pulled)
    except Exception as exc:  # noqa: BLE001
        _line(
            FAIL,
            "ollama",
            f"{type(exc).__name__}: {exc}\n"
            f"        Nothing that needs a model will work. Start Ollama.",
        )


def _check_registry_against(pulled: set[str]) -> None:
    """A registry entry naming a tag nobody pulled is a 404 at use time.

    Two tags in this repo never existed and were found only when
    something tried to use them; one had been 404ing the router and the
    verifier for weeks.
    """
    try:
        from backend.models.registry import _DEFAULT_REGISTRY_PATH, load_registry

        registry = load_registry(_DEFAULT_REGISTRY_PATH)
    except Exception as exc:  # noqa: BLE001
        _line(FAIL, "model registry", f"unreadable: {exc}")
        return

    missing = [
        f"{model_id} -> {cfg.model}"
        for model_id, cfg in registry.items()
        if cfg.model not in pulled and f"{cfg.model}:latest" not in pulled
    ]
    if missing:
        _line(
            WARN,
            "model registry",
            f"{len(registry)} entries, {len(missing)} naming a tag that is NOT pulled:\n"
            + "\n".join(f"          {m}" for m in missing)
            + "\n        Each is a 404 the moment something routes to it.",
        )
    else:
        _line(OK, "model registry", f"all {len(registry)} tags are pulled")


def check_corpus() -> None:
    try:
        from backend.api.state import get_state

        store, _ = get_state().ensure_corpus()
        chunks = len(store.all_chunk_texts())
        if chunks == 0:
            _line(
                WARN,
                "corpus",
                "0 chunks indexed. Every document question will refuse. Add a folder "
                "under Sources, or check the working-directory line above.",
            )
        else:
            documents = {r["source_document"] for r in store.all_chunk_records()}
            _line(OK, "corpus", f"{chunks} chunks from {len(documents)} document(s)")
    except Exception as exc:  # noqa: BLE001
        _line(FAIL, "corpus", f"{type(exc).__name__}: {exc}")


def check_backend_port() -> None:
    """Whether something is already listening, and whether it is ours.

    Two servers on 8000 is a confusing state: the second fails to bind
    and dies, the first keeps serving, and the code you just changed is
    not the code that is running.
    """
    import socket

    probe = socket.socket()
    probe.settimeout(1.0)
    listening = probe.connect_ex(("127.0.0.1", 8000)) == 0
    probe.close()

    if not listening:
        _line(
            WARN,
            "backend on :8000",
            "nothing is listening. The frontend's dev server falls back to its OWN "
            "implementation of /api/sources and /api/corpus when the backend is down, "
            "and that fallback still needs the backend to ingest -- which is why 'add "
            "source is broken' is usually 'the backend is not running'.",
        )
        return

    try:
        import requests

        res = requests.get("http://127.0.0.1:8000/api/health", timeout=4)
        if res.ok:
            health = res.json()
            _line(
                OK,
                "backend on :8000",
                f"healthy -- embeddings: {health.get('embedding_backend')}, "
                f"ocr: {health.get('ocr_device')}, "
                f"documents: {health.get('documents_registered')}",
            )
        else:
            _line(FAIL, "backend on :8000", f"responded {res.status_code} to /api/health")
    except Exception as exc:  # noqa: BLE001
        _line(
            FAIL,
            "backend on :8000",
            f"something is listening but it is not answering /api/health: {exc}\n"
            f"        An older server from a previous branch may still be running. "
            f"Kill it and start again -- the code you changed is not the code serving.",
        )


def check_git_state() -> None:
    import subprocess

    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=ROOT, timeout=10,
        ).stdout.strip()
        head = subprocess.run(
            ["git", "log", "-1", "--format=%h %s"],
            capture_output=True, text=True, cwd=ROOT, timeout=10,
        ).stdout.strip()
        conflicts = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=U"],
            capture_output=True, text=True, cwd=ROOT, timeout=10,
        ).stdout.strip()
        if conflicts:
            _line(
                FAIL,
                "git state",
                f"{branch} has UNRESOLVED MERGE CONFLICTS:\n"
                + "\n".join(f"          {c}" for c in conflicts.splitlines())
                + "\n        Python will not import a file with conflict markers in it.",
            )
        else:
            _line(OK, "git state", f"{branch} @ {head}")
    except Exception as exc:  # noqa: BLE001
        _line(WARN, "git state", f"could not be read: {exc}")


def check_frontend_build() -> None:
    """A frontend that does not compile serves the last good bundle in
    dev, so a broken page can look like a backend problem."""
    node_modules = ROOT / "frontend" / "node_modules"
    if not node_modules.exists():
        _line(
            FAIL,
            "frontend deps",
            "frontend/node_modules is missing. Run `npm install` in frontend/.",
        )
    else:
        _line(OK, "frontend deps", "node_modules present")


def main() -> None:
    print()
    print("  Sovereign Workbench -- startup doctor")
    print("  " + "-" * 62)
    print(f"  python {sys.version.split()[0]}   platform {sys.platform}")
    print()

    check_git_state()
    check_working_directory()
    check_backend_port()
    check_source_config()
    check_embeddings()
    check_ollama()
    check_corpus()
    check_frontend_build()

    print()
    print("  Read top to bottom and stop at the first FAIL -- the checks are")
    print("  ordered so the first failure is usually the real one.")
    print()


if __name__ == "__main__":
    main()
