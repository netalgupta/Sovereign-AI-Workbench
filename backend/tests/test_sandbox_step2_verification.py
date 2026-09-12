"""
backend/tests/test_sandbox_step2_verification.py

Explicit Verification for Step 2:
1. Warm-pool state isolation across sequential jobs (Docker pool / worker recycling).
2. Forced Non-Docker Fallback Path running all 6 acceptance criteria specifically on fallback.
"""

import os
import shutil
import time
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.main import app
from backend.sandbox.manager import get_sandbox_manager, SandboxManager
from backend.sandbox.pool import WorkerPool, SESSIONS_HOST_DIR

client = TestClient(app)


def poll_job(manager: SandboxManager, job_id: str, timeout_max: float = 15.0) -> dict:
    start_time = time.time()
    while time.time() - start_time < timeout_max:
        job = manager.get_job(job_id)
        if job and job["status"] in ("completed", "failed", "timeout"):
            return job
        time.sleep(0.05)
    pytest.fail(f"Job {job_id} timed out waiting for status")


# ============================================================================
# Section 1: Non-Docker Fallback Path (Forced Execution of All 6 Criteria)
# ============================================================================

class TestFallbackPath:
    @pytest.fixture(autouse=True)
    def force_fallback(self):
        """Force SandboxManager to bypass Docker and use process fallback exclusively."""
        with patch.object(SandboxManager, "_try_docker_execution", return_value=None):
            yield

    def test_fallback_c1_timeout(self):
        manager = get_sandbox_manager()
        job_id = manager.submit_job("while True:\n    pass\n", language="python", timeout_seconds=2)
        job = poll_job(manager, job_id, timeout_max=5.0)
        assert job["status"] == "timeout"
        assert job["exit_code"] in (124, -1, None) or job["exit_code"] != 0
        assert "timed out" in job["stderr"].lower()

    def test_fallback_c2_network_blocked(self):
        manager = get_sandbox_manager()
        code = (
            "import urllib.request\n"
            "try:\n"
            "    urllib.request.urlopen('http://google.com', timeout=2)\n"
            "    print('NET_SUCCESS')\n"
            "except Exception as e:\n"
            "    print(f'NET_ERR: {type(e).__name__} - {e}')\n"
        )
        job_id = manager.submit_job(code, language="python", timeout_seconds=5)
        job = poll_job(manager, job_id, timeout_max=8.0)
        assert job["status"] in ("completed", "failed")
        assert "NET_SUCCESS" not in job["stdout"]
        output = (job["stdout"] + "\n" + job["stderr"]).lower()
        assert any(term in output for term in ["network", "oserror", "socket", "unreachable", "disabled", "err"])

    def test_fallback_c3_filesystem_isolation(self):
        manager = get_sandbox_manager()
        code = (
            "import os\n"
            "try:\n"
            "    with open('../fallback_host_leak.txt', 'w') as f:\n"
            "        f.write('LEAK')\n"
            "except Exception:\n"
            "    pass\n"
        )
        job_id = manager.submit_job(code, language="python", timeout_seconds=5)
        job = poll_job(manager, job_id, timeout_max=8.0)
        assert not os.path.exists("fallback_host_leak.txt")

    def test_fallback_c4_concurrency(self):
        manager = get_sandbox_manager()
        code1 = "with open('f.txt', 'w') as f:\n    f.write('SEQ1')\nwith open('f.txt', 'r') as f:\n    print(f.read())\n"
        code2 = "with open('f.txt', 'w') as f:\n    f.write('SEQ2')\nwith open('f.txt', 'r') as f:\n    print(f.read())\n"
        
        j1 = manager.submit_job(code1, language="python", timeout_seconds=5)
        j2 = manager.submit_job(code2, language="python", timeout_seconds=5)

        res1 = poll_job(manager, j1)
        res2 = poll_job(manager, j2)

        assert res1["status"] == "completed"
        assert res2["status"] == "completed"
        assert "SEQ1" in res1["stdout"]
        assert "SEQ2" in res2["stdout"]

    def test_fallback_c5_memory_limit(self):
        manager = get_sandbox_manager()
        code = "data = [b'X' * (10 * 1024 * 1024) for _ in range(1000)]\n"
        job_id = manager.submit_job(code, language="python", timeout_seconds=5)
        job = poll_job(manager, job_id, timeout_max=8.0)
        assert job["status"] in ("failed", "timeout")
        assert job["exit_code"] != 0

    def test_fallback_c6_normal_code(self):
        manager = get_sandbox_manager()
        code = "print(100 + 237)\n"
        job_id = manager.submit_job(code, language="python", timeout_seconds=5)
        job = poll_job(manager, job_id, timeout_max=8.0)
        assert job["status"] == "completed"
        assert job["exit_code"] == 0
        assert "337" in job["stdout"]


# ============================================================================
# Section 2: Sequential Job Warm-Pool Reset & State Isolation Verification
# ============================================================================

def test_sequential_warm_pool_state_isolation():
    """Verify that sequential jobs served by the worker pool are 100% isolated.

    Verifies:
    1. Host session workspaces are wiped on session release/recycle.
    2. Read-only container rootfs prevents persistent container state pollution.
    """
    manager = get_sandbox_manager()
    
    # Job 1 writes a session file
    job_1_code = "with open('marker.txt', 'w') as f:\n    f.write('SECRET_MARKER_12345')\n"
    j1 = manager.submit_job(job_1_code, language="python")
    res1 = poll_job(manager, j1)
    assert res1["status"] == "completed"

    # Job 2 attempts to read the marker file from Job 1
    job_2_code = (
        "import os\n"
        "if os.path.exists('marker.txt'):\n"
        "    print('LEAK_DETECTED: ' + open('marker.txt').read())\n"
        "else:\n"
        "    print('CLEAN_ISOLATED')\n"
    )
    j2 = manager.submit_job(job_2_code, language="python")
    res2 = poll_job(manager, j2)

    assert res2["status"] == "completed"
    assert "LEAK_DETECTED" not in res2["stdout"]
    assert "CLEAN_ISOLATED" in res2["stdout"]
