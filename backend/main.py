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

import logging
from contextlib import asynccontextmanager

import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router

logger = logging.getLogger("backend.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from backend.sandbox import pool
        pool.start()
    except Exception as exc:
        logger.warning("Could not start sandbox pool: %s", exc)
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


@app.get("/")
def root() -> dict:
    return {
        "name": "Sovereign Workbench API",
        "offline": True,
        "endpoints": [r.path for r in app.routes if getattr(r, "path", "").startswith("/api")],
    }


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


