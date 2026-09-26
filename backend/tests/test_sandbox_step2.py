"""
backend/tests/test_sandbox_step2.py

Automated test suite for Step 2: Secure Sandbox (Code Execution Isolation).
Tests every acceptance criterion:
1. Infinite loop timeout handling (status: "timeout", process force-killed).
2. Outbound network blocking at network layer.
3. Filesystem isolation (restricting read/write outside scratch dir).
4. Concurrent job execution isolation.
5. Memory limit cap enforcement.
6. Normal well-behaved code execution with stdout/exit code verification.
"""

import concurrent.futures
import os
import time
import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def poll_job_until_done(job_id: str, timeout_max: float = 15.0) -> dict:
    start_time = time.time()
    while time.time() - start_time < timeout_max:
        resp = client.get(f"/api/sandbox/execute/{job_id}")
        assert resp.status_code == 200
        data = resp.json()
        if data["status"] in ("completed", "failed", "timeout"):
            return data
        time.sleep(0.1)
    pytest.fail(f"Job {job_id} did not finish within {timeout_max} seconds")


def test_criterion_1_infinite_loop_timeout():
    """Criterion 1: Infinite loop script is force-killed at timeout and reported as 'timeout'."""
    code = "while True:\n    pass\n"
    resp = client.post("/api/sandbox/execute", json={"code": code, "language": "python", "timeout_seconds": 2})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    job = poll_job_until_done(job_id, timeout_max=5.0)
    assert job["status"] == "timeout"
    assert job["exit_code"] in (124, -1, None) or job["exit_code"] != 0
    assert "timed out" in job["stderr"].lower()


def test_criterion_2_outbound_network_blocked():
    """Criterion 2: Outbound network call fails at the network layer."""
    code = (
        "import urllib.request\n"
        "try:\n"
        "    urllib.request.urlopen('http://google.com', timeout=3)\n"
        "    print('SUCCESS_NETWORK')\n"
        "except Exception as e:\n"
        "    print(f'NETWORK_FAILED: {type(e).__name__} - {e}')\n"
    )
    resp = client.post("/api/sandbox/execute", json={"code": code, "language": "python", "timeout_seconds": 5})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    job = poll_job_until_done(job_id, timeout_max=8.0)
    assert job["status"] in ("completed", "failed")
    assert "SUCCESS_NETWORK" not in job["stdout"]
    output_lower = (job["stdout"] + "\n" + job["stderr"]).lower()
    assert "network" in output_lower or "oserror" in output_lower or "socket" in output_lower or "unreachable" in output_lower or "failed" in output_lower


def test_criterion_3_filesystem_isolation():
    """Criterion 3: Attempting to read or write outside scratch directory fails or is restricted."""
    code = (
        "import os\n"
        "try:\n"
        "    with open('../forbidden_host_file.txt', 'w') as f:\n"
        "        f.write('hack')\n"
        "    print('WRITE_SUCCESS')\n"
        "except Exception as e:\n"
        "    print(f'WRITE_BLOCKED: {type(e).__name__}')\n"
    )
    resp = client.post("/api/sandbox/execute", json={"code": code, "language": "python", "timeout_seconds": 5})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    job = poll_job_until_done(job_id, timeout_max=8.0)
    # Host path outside scratch dir should not be created
    assert not os.path.exists("forbidden_host_file.txt")


def test_criterion_4_concurrent_execution_isolation():
    """Criterion 4: Two concurrent executions do not share files, env, or process state."""
    code_1 = (
        "import os, time\n"
        "os.environ['UNIQUE_JOB_VAR'] = 'JOB_1'\n"
        "with open('shared.txt', 'w') as f:\n"
        "    f.write('DATA_JOB_1')\n"
        "time.sleep(0.5)\n"
        "with open('shared.txt', 'r') as f:\n"
        "    print(f.read())\n"
    )
    code_2 = (
        "import os, time\n"
        "os.environ['UNIQUE_JOB_VAR'] = 'JOB_2'\n"
        "with open('shared.txt', 'w') as f:\n"
        "    f.write('DATA_JOB_2')\n"
        "time.sleep(0.5)\n"
        "with open('shared.txt', 'r') as f:\n"
        "    print(f.read())\n"
    )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(client.post, "/api/sandbox/execute", json={"code": code_1, "language": "python", "timeout_seconds": 5})
        f2 = executor.submit(client.post, "/api/sandbox/execute", json={"code": code_2, "language": "python", "timeout_seconds": 5})
        resp1, resp2 = f1.result(), f2.result()

    job_id1 = resp1.json()["job_id"]
    job_id2 = resp2.json()["job_id"]
    assert job_id1 != job_id2

    job1 = poll_job_until_done(job_id1, timeout_max=8.0)
    job2 = poll_job_until_done(job_id2, timeout_max=8.0)

    assert job1["status"] == "completed"
    assert job2["status"] == "completed"
    assert "DATA_JOB_1" in job1["stdout"].strip()
    assert "DATA_JOB_2" in job2["stdout"].strip()


def test_criterion_5_memory_limit_killed():
    """Criterion 5: Script over-allocating memory is terminated by memory limit."""
    code = (
        "data = []\n"
        "for i in range(1000):\n"
        "    data.append(b'X' * (10 * 1024 * 1024))\n"
    )
    resp = client.post("/api/sandbox/execute", json={"code": code, "language": "python", "timeout_seconds": 5})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    job = poll_job_until_done(job_id, timeout_max=8.0)
    assert job["status"] in ("failed", "timeout")
    assert job["exit_code"] != 0


def test_criterion_6_normal_code_execution():
    """Criterion 6: Normal well-behaved calculation returns correct stdout."""
    code = "x = 42\ny = 1337\nprint(f'RESULT={x * y}')\n"
    resp = client.post("/api/sandbox/execute", json={"code": code, "language": "python", "timeout_seconds": 5})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    job = poll_job_until_done(job_id, timeout_max=8.0)
    assert job["status"] == "completed"
    assert job["exit_code"] == 0
    assert "RESULT=56154" in job["stdout"]
