"""
backend/sandbox/executor.py

Drop-in replacement for the CARD 04 executor. Same SandboxResult shape
and the same `run_in_sandbox()` name/signature the rest of the
orchestrator (dispatch.py, graph.py) already expects -- only the inside
changed, from "spin up a fresh container" to "exec into a warm one from
the pool". Callers with a live websocket get streamed stdout/stderr as
it's produced; callers without one just get the final result.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Callable, Literal, Optional

from pydantic import BaseModel

from .pool import pool, Worker, SESSIONS_HOST_DIR, SESSIONS_CONTAINER_DIR

ChunkCallback = Callable[[str, str], None]   # (stream_name: "stdout"|"stderr", text)


class SandboxResult(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool


def _write_script(session_id: str, code: str, filename: str = "script.py") -> str:
    workspace = os.path.join(SESSIONS_HOST_DIR, session_id)
    os.makedirs(workspace, exist_ok=True)
    script_path = os.path.join(workspace, filename)
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(code)
    return f"{SESSIONS_CONTAINER_DIR}/{session_id}/{filename}"


def _exec_command(language: Literal["python", "node"], container_script_path: str, timeout_seconds: int) -> list[str]:
    if language == "python":
        return ["timeout", f"{timeout_seconds}s", "python", "-u", container_script_path]
    elif language == "node":
        return ["timeout", f"{timeout_seconds}s", "node", container_script_path]
    raise ValueError(f"unsupported language: {language}")


def run_in_sandbox_streaming(
    worker: Worker,
    code: str,
    language: Literal["python", "node"] = "python",
    timeout_seconds: int = 30,
    on_chunk: Optional[ChunkCallback] = None,
) -> SandboxResult:
    """Synchronous, blocking. Runs inside a thread when called from async
    code (see run_code_step below). Streams stdout/stderr chunks to
    on_chunk as they're produced by docker exec."""
    filename = "script.py" if language == "python" else "script.js"
    container_path = _write_script(worker.session_id or "default", code, filename)
    cmd = _exec_command(language, container_path, timeout_seconds)

    client = pool.client
    exec_id = client.api.exec_create(
        worker.container.id,
        cmd=cmd,
        stdout=True,
        stderr=True,
    )
    stream = client.api.exec_start(exec_id, stream=True, demux=True)

    stdout_parts: list[bytes] = []
    stderr_parts: list[bytes] = []

    for out_chunk, err_chunk in stream:
        if out_chunk:
            stdout_parts.append(out_chunk)
            if on_chunk:
                on_chunk("stdout", out_chunk.decode(errors="replace"))
        if err_chunk:
            stderr_parts.append(err_chunk)
            if on_chunk:
                on_chunk("stderr", err_chunk.decode(errors="replace"))

    exit_code = client.api.exec_inspect(exec_id)["ExitCode"]
    # GNU `timeout` returns 124 when it had to kill the process for
    # exceeding the deadline; -1 covers the (rare) case docker itself
    # reports no exit code (e.g. container died mid-exec).
    timed_out = exit_code in (124, -1)

    return SandboxResult(
        stdout=b"".join(stdout_parts).decode(errors="replace"),
        stderr=b"".join(stderr_parts).decode(errors="replace"),
        exit_code=exit_code if exit_code is not None else -1,
        timed_out=timed_out,
    )


def run_in_sandbox(
    code: str,
    session_id: str = "default",
    language: Literal["python", "node"] = "python",
    timeout_seconds: int = 30,
) -> SandboxResult:
    """Synchronous entry point -- same name/shape as the original CARD 04
    spec. Use this from non-async call sites. Acquires and releases the
    pool worker internally so callers don't need to know the pool exists."""
    worker = pool.acquire(session_id)
    try:
        return run_in_sandbox_streaming(worker, code, language, timeout_seconds)
    finally:
        pool.release(worker)


async def run_code_step(
    code: str,
    session_id: str = "default",
    language: Literal["python", "node"] = "python",
    timeout_seconds: int = 30,
    ws=None,
) -> SandboxResult:
    """Async entry point for the orchestrator. If `ws` is provided
    (a live websocket for this chat session), streams tool_output_chunk
    events as the code runs; otherwise behaves like run_in_sandbox()."""
    loop = asyncio.get_running_loop()
    worker = pool.acquire(session_id)

    def on_chunk(stream_name: str, text: str):
        if ws is None:
            return
        asyncio.run_coroutine_threadsafe(
            ws.send_json({"type": "tool_output_chunk", "stream": stream_name, "text": text}),
            loop,
        )

    try:
        result = await asyncio.to_thread(
            run_in_sandbox_streaming, worker, code, language, timeout_seconds, on_chunk
        )
    finally:
        pool.release(worker)

    if ws is not None:
        await ws.send_json({
            "type": "tool_output_done",
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
        })

    return result
