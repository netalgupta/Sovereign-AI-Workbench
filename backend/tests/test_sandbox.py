"""
backend/tests/test_sandbox.py

Run with: pytest backend/tests/test_sandbox.py -v
Requires Docker daemon running locally.
"""

import uuid
import pytest

from backend.sandbox import pool, run_in_sandbox


@pytest.fixture(scope="module", autouse=True)
def _pool_lifecycle():
    try:
        pool.start()
    except Exception as exc:
        pytest.skip(f"Docker sandbox pool could not start: {exc}")
    yield
    try:
        pool.shutdown()
    except Exception:
        pass


def _session_id() -> str:
    return f"test-{uuid.uuid4().hex[:8]}"


def test_standard_execution():
    result = run_in_sandbox('print("hello")', session_id=_session_id())
    assert result.exit_code == 0
    assert result.stdout == "hello\n"
    assert not result.timed_out


def test_error_handling():
    result = run_in_sandbox("raise ValueError('boom')", session_id=_session_id())
    assert result.exit_code != 0
    assert "ValueError" in result.stderr
    assert "boom" in result.stderr


def test_infinite_loop_timeout():
    result = run_in_sandbox("while True:\n    pass\n", session_id=_session_id(), timeout_seconds=3)
    assert result.timed_out is True


def test_zero_network():
    code = (
        "import urllib.request\n"
        "try:\n"
        "    urllib.request.urlopen('http://example.com', timeout=5)\n"
        "    print('NETWORK_REACHABLE')\n"
        "except Exception as e:\n"
        "    print(f'NETWORK_BLOCKED: {type(e).__name__}')\n"
    )
    result = run_in_sandbox(code, session_id=_session_id())
    assert "NETWORK_REACHABLE" not in result.stdout
    assert "NETWORK_BLOCKED" in result.stdout


def test_sticky_session_reuses_same_worker():
    sid = _session_id()
    w1 = pool.acquire(sid)
    name1 = w1.name
    pool.release(w1)

    w2 = pool.acquire(sid)
    name2 = w2.name
    pool.release(w2)

    assert name1 == name2, "same session should get the same warm worker back"
    pool.release_session(sid)


def test_node_execution():
    sid = _session_id()
    w = pool.acquire(sid)
    try:
        check = pool.client.api.exec_create(w.container.id, cmd=["which", "node"])
        out = pool.client.api.exec_start(check)
        if not out.strip():
            pytest.skip("Node.js not installed in current sandbox base image (built with python-slim)")
    finally:
        pool.release(w)

    result = run_in_sandbox('console.log("hi from node")', session_id=sid, language="node")
    assert result.exit_code == 0
    assert "hi from node" in result.stdout


def test_websocket_code_execution_streaming():
    """Verify end-to-end WebSocket streaming of tool_output_chunk and tool_output_done."""
    from fastapi.testclient import TestClient
    from backend.main import app

    sid = _session_id()
    client = TestClient(app)

    with client.websocket_connect(f"/ws/session/{sid}") as ws:
        code = "import sys; print('CHUNK_1_STDOUT'); sys.stderr.write('CHUNK_2_STDERR\\n'); print('CHUNK_3_STDOUT')"
        ws.send_json({"type": "execute_code", "code": code, "language": "python"})

        received_types = []
        stdout_text = ""
        stderr_text = ""
        done_payload = None

        # Collect events until tool_output_done
        for _ in range(10):
            data = ws.receive_json()
            received_types.append(data.get("type"))
            if data.get("type") == "tool_output_chunk":
                if data.get("stream") == "stdout":
                    stdout_text += data.get("text", "")
                elif data.get("stream") == "stderr":
                    stderr_text += data.get("text", "")
            elif data.get("type") == "tool_output_done":
                done_payload = data
                break

        assert "tool_output_chunk" in received_types
        assert "tool_output_done" in received_types
        assert "CHUNK_1_STDOUT" in stdout_text
        assert "CHUNK_3_STDOUT" in stdout_text
        assert "CHUNK_2_STDERR" in stderr_text
        assert done_payload is not None
        assert done_payload["exit_code"] == 0
        assert not done_payload["timed_out"]

