"""FastAPI entrypoint for the Sovereign Workbench backend.

Run with:  python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

BOUND TO LOOPBACK BY DEFAULT, deliberately. CLAUDE.md hard constraint #1
is that this system makes no outbound network calls; binding the server
to 0.0.0.0 would not violate that literally, but it would put an
unauthenticated API that reads the user's filesystem on every interface
of a machine that may sit on a plant network. Loopback is the correct
default for a desktop workbench, and anything else should be a
deliberate, argued change.

CORS is restricted to the Vite dev server's local origins for the same
reason: the frontend and backend run on the same machine, so there is
never a legitimate cross-origin caller from anywhere else.
"""

# Run from the repository root, whatever directory the server was started
# in: many paths below are repo-relative (backend/paths.py says why).
import os as _os

from backend.paths import REPO_ROOT as _REPO_ROOT

_os.chdir(_REPO_ROOT)

# FIRST, before anything that might import torch/tensorflow/paddle.
# TF_CPP_MIN_LOG_LEVEL and friends are read by those libraries' C++
# layers AT IMPORT TIME, so this cannot be tidied in with the imports
# below -- moving it down silently stops it working.
from backend.observability.quiet_startup import quiet as _quiet_startup

_quiet_startup()

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router

logger = logging.getLogger("backend.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # IS THE EMBEDDING MODEL ACTUALLY HERE?
    #
    # models/embeddings/ is gitignored (1.3 GB), so a teammate who
    # clones or pulls has the code and NOT the model. require_cached
    # then raises, embeddings fall back to hash vectors, and everything
    # keeps working -- badly, and silently.
    #
    # This happened on a teammate's machine and produced a completely
    # wrong answer that looked entirely normal: asked for one person's
    # assignments, retrieval returned two other people's files and the
    # answer described a third. Right-shaped vectors, results for every
    # search, citations on every answer. The only evidence was one trace
    # line reading "embedding backend: deterministic-hash".
    #
    # Checked at startup and stated in the terms that matter -- what is
    # broken, what it costs, and the one command that fixes it.
    try:
        from backend.ingestion.model_cache import local_cache_dir

        _emb = local_cache_dir("embeddings", "BAAI/bge-large-en-v1.5")
        if not _emb.exists() or not any(_emb.iterdir()):
            logger.error(
                "\n"
                "  =============================================================\n"
                "  EMBEDDING MODEL IS MISSING. RETRIEVAL WILL BE MEANINGLESS.\n"
                "\n"
                "  models/embeddings/ is gitignored (1.3 GB), so it does not\n"
                "  arrive with a git pull. Without it the system falls back to\n"
                "  hash vectors, which carry NO semantic meaning: searches\n"
                "  return results, answers carry citations, and the content is\n"
                "  wrong.\n"
                "\n"
                "  Fetch it once (needs internet, then never again):\n"
                "      py -3 -m backend.ingestion.fetch_models\n"
                "  =============================================================\n"
            )
    except Exception:  # noqa: BLE001 - a check that breaks startup is worse
        pass

    try:
        from backend.sandbox import pool
        pool.start()
    except Exception as exc:
        # Actionable, and explicit that the rest of the system is fine.
        # This previously printed a raw docker-py 404 URL, which looked
        # like a crash and told nobody what to do about it.
        try:
            from backend.sandbox.pool import SandboxImageMissing
            is_missing = isinstance(exc, SandboxImageMissing)
        except Exception:
            is_missing = False

        if is_missing:
            logger.warning(
                "Sandbox DISABLED - no local image.\n%s\n"
                "Everything else (chat, retrieval, graph, tools) works normally; "
                "only the code-execution agent is unavailable.",
                exc,
            )
        else:
            logger.warning("Could not start sandbox pool: %s: %s", type(exc).__name__, exc)

    # WARM-UP, off the request path. The first question after a restart
    # took 14.7 s against 4.8-7.0 s warm: the corpus load, the keyword
    # index build and the embedding model's first use all landed on it.
    # Done here in a background thread, the server is up at once and the
    # first question finds everything ready. Ends by loading the chat
    # model at the standard context, so no request pays a load or a
    # context-size reload (ollama_client.STANDARD_NUM_CTX).
    import threading

    def _warm() -> None:
        import time as _t

        t0 = _t.time()
        try:
            from backend.api.state import get_state
            from backend.retrieval.grounded_retrieval import retrieve_with_grounding_check

            store, _chunks = get_state().ensure_corpus()
            retrieve_with_grounding_check(store, "warm-up query for the keyword index", 1)
        except Exception as exc:  # noqa: BLE001 - warming must never break startup
            logger.warning("Warm-up: retrieval not warmed (%s)", exc)
        try:
            from backend.models.ollama_client import STANDARD_NUM_CTX, generate
            from backend.models.registry import resolve_model_name

            generate(resolve_model_name("reasoning-model"), "Reply with OK.", timeout=300,
                     options={"num_ctx": STANDARD_NUM_CTX, "num_predict": 2})
        except Exception as exc:  # noqa: BLE001
            logger.warning("Warm-up: chat model not preloaded (%s)", exc)
        logger.warning("Warm-up finished in %.1fs: corpus, keyword index and chat model ready", _t.time() - t0)

    threading.Thread(target=_warm, name="warm-up", daemon=True).start()
    yield
    try:
        from backend.sandbox import pool
        pool.shutdown()
    except Exception:
        pass


app = FastAPI(
    title="Sovereign Workbench",
    description=(
        "On-premise agentic AI workbench for MRPL (PS26117). "
        "Fully offline: every route reads local state only."
    ),
    version="0.1.0",
    lifespan=lifespan,
    # Docs are served from FastAPI's own bundled assets rather than the
    # default CDN-hosted Swagger UI -- the default pulls JS from
    # cdn.jsdelivr.net at page load, which is exactly the phone-home
    # hard constraint #1 forbids. Disabled rather than half-working.
    docs_url=None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://127.0.0.1:5173",
        "http://localhost:4173",  # Vite preview
        "http://127.0.0.1:4173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)

# ---------------------------------------------------------------------
# Quiet the poll endpoints in the access log.
#
# The frontend polls /api/network/status about once a second for the
# zero-egress monitor bar, and /api/ingestion/{id} several times a second
# while a folder is being indexed. At one access-log line each, they bury
# every line that actually matters -- a failing ingest, a 403 from the
# approval gate, a 503 from a dead Neo4j -- under thousands of 200s.
#
# Filtered at the LOG layer, not by making the endpoints quieter: the
# requests are legitimate and should still happen, and anything that is
# not a 2xx still comes through, because a poll endpoint that starts
# failing is exactly when you want to see it.
class _QuietPolls(logging.Filter):
    NOISY_PATHS = ("/api/network/status", "/api/ingestion")

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if not any(path in message for path in self.NOISY_PATHS):
            return True
        # Keep anything that is not a plain success.
        return not any(f'" {code}' in message for code in ("200", "304"))


logging.getLogger("uvicorn.access").addFilter(_QuietPolls())

app.include_router(router)


# ── The desktop app is served from here ─────────────────────────────────────
# The Electron shell (and any browser on this machine) opens
# http://127.0.0.1:8000/. Loading the build from file:// instead would break
# every relative /api call and every route, and would need a second router.
# From here: one origin, loopback only, and /chat/<id> survives a refresh
# because any non-API path answers with the app shell.
_DIST = (_REPO_ROOT / "frontend" / "dist").resolve()


def _api_description() -> dict:
    return {
        "name": "Sovereign Workbench API",
        "offline": True,
        "endpoints": [r.path for r in app.routes if getattr(r, "path", "").startswith("/api")],
    }


@app.get("/", include_in_schema=False)
def root():
    from fastapi.responses import FileResponse

    index = _DIST / "index.html"
    return FileResponse(index) if index.exists() else _api_description()


@app.get("/{path:path}", include_in_schema=False)
def app_shell(path: str):
    """A built file if it exists, else the app shell (client-side routes)."""
    from fastapi import HTTPException
    from fastapi.responses import FileResponse

    if path.startswith("api/") or path == "api":
        raise HTTPException(status_code=404, detail=f"No API route: /{path}")
    index = _DIST / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="The frontend is not built (npm run build in frontend/).")
    candidate = (_DIST / path).resolve()
    if candidate.is_file() and candidate.is_relative_to(_DIST):
        return FileResponse(candidate)
    return FileResponse(index)


@app.websocket("/ws/session/{session_id}")
async def session_ws(websocket: WebSocket, session_id: str):
    """Session websocket for live tool streaming and chat interaction."""
    await websocket.accept()
    from backend.sandbox import pool
    try:
        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type")
            if msg_type == "user_message":
                from backend.orchestrator.graph import run_orchestrator_turn
                result = run_orchestrator_turn(msg.get("text", ""), session_id=session_id)
                await websocket.send_json({
                    "type": "agent_reply",
                    "reply": result.get("reply", ""),
                    "citations": result.get("citations", []),
                    "plan": result.get("plan", []),
                    "session_id": session_id,
                })
            elif msg_type in ("execute_code", "run_code"):
                from backend.sandbox.executor import run_code_step
                code = msg.get("code", "")
                language = msg.get("language", "python")
                timeout_seconds = int(msg.get("timeout_seconds", msg.get("timeout", 30)))
                await run_code_step(
                    code=code,
                    session_id=session_id,
                    language=language,
                    timeout_seconds=timeout_seconds,
                    ws=websocket,
                )
    except WebSocketDisconnect:
        pool.release_session(session_id)


