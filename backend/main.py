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


