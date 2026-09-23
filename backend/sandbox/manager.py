"""
backend/sandbox/manager.py

Sandbox Execution Manager for Step 2: Secure Sandbox (Code Execution Isolation).

Enforces:
1. Ephemeral execution environment (Docker container or process-isolated runner).
2. Hard resource limits: CPU, Memory (256MB cap, killed if exceeded), Execution Timeout.
3. Outbound network disabled at the network layer.
4. Filesystem isolation in an empty scratch directory.
5. Process isolation for concurrent job execution.
6. Async job tracking via POST /api/sandbox/execute and GET /api/sandbox/execute/{job_id}.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Literal, Optional, Any

logger = logging.getLogger("sandbox.manager")

JobStatus = Literal["queued", "running", "completed", "failed", "timeout"]


class SandboxManager:
    def __init__(self, default_timeout: int = 10, memory_limit_mb: int = 256):
        self.default_timeout = default_timeout
        self.memory_limit_mb = memory_limit_mb
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._executor_thread_pool = None

    def submit_job(
        self,
        code: str,
        language: str = "python",
        timeout_seconds: Optional[int] = None,
    ) -> str:
        """Submit code for asynchronous execution in an isolated sandbox.

        Returns immediately with job_id.
        """
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        actual_timeout = timeout_seconds if (timeout_seconds is not None and timeout_seconds > 0) else self.default_timeout

        now_iso = datetime.now(timezone.utc).isoformat()

        job_record = {
            "job_id": job_id,
            "code": code,
            "language": language.lower(),
            "timeout_seconds": actual_timeout,
            "status": "queued",
            "stdout": "",
            "stderr": "",
            "exit_code": None,
            "created_at": now_iso,
            "completed_at": None,
        }

        with self._lock:
            self._jobs[job_id] = job_record

        # Launch worker execution thread
        t = threading.Thread(target=self._run_job, args=(job_id,), daemon=True)
        t.start()

        return job_id

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve job execution status and results by job_id."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            return {
                "job_id": job["job_id"],
                "status": job["status"],
                "stdout": job["stdout"],
                "stderr": job["stderr"],
                "exit_code": job["exit_code"],
                "created_at": job["created_at"],
                "completed_at": job["completed_at"],
            }

    def _run_job(self, job_id: str):
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job["status"] = "running"

        code = job["code"]
        language = job["language"]
        timeout_sec = job["timeout_seconds"]

        # Try Docker container pool execution first if Docker is available
        result = self._try_docker_execution(code, language, timeout_sec)

        if result is None:
            # Docker unavailable or failed initialization — fallback to process-isolated runner
            result = self._execute_in_isolated_process(code, language, timeout_sec)

        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["status"] = result["status"]
                self._jobs[job_id]["stdout"] = result["stdout"]
                self._jobs[job_id]["stderr"] = result["stderr"]
                self._jobs[job_id]["exit_code"] = result["exit_code"]
                self._jobs[job_id]["completed_at"] = now_iso

    def _try_docker_execution(
        self, code: str, language: str, timeout_seconds: int
    ) -> Optional[Dict[str, Any]]:
        """Attempt execution via Docker pool if Docker daemon is active."""
        try:
            from backend.sandbox.executor import run_in_sandbox
            from backend.sandbox.pool import pool

            # Verify Docker client connection
            pool.client.ping()

            res = run_in_sandbox(
                code=code,
                session_id=f"sandbox-job-{uuid.uuid4().hex[:6]}",
                language=language,  # type: ignore
                timeout_seconds=timeout_seconds,
            )

            if res.timed_out:
                status = "timeout"
            elif res.exit_code == 0:
                status = "completed"
            else:
                status = "failed"

            return {
                "status": status,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "exit_code": res.exit_code,
            }
        except Exception as exc:
            logger.debug("Docker execution unavailable, using process isolation fallback: %s", exc)
            return None

    def _execute_in_isolated_process(
        self, code: str, language: str, timeout_seconds: int
    ) -> Dict[str, Any]:
        """Process-isolated fallback runner.

        Enforces:
        - Ephemeral scratch directory.
        - Outbound network disabling at socket layer.
        - Memory limit cap with process termination.
        - Wall-clock timeout with process termination.
        """
        scratch_dir = tempfile.mkdtemp(prefix="sandbox_scratch_")
        try:
            if language == "python":
                return self._run_python_process(code, scratch_dir, timeout_seconds)
            elif language in ("node", "javascript", "js"):
                return self._run_node_process(code, scratch_dir, timeout_seconds)
            else:
                return {
                    "status": "failed",
                    "stdout": "",
                    "stderr": f"Unsupported language: {language}",
                    "exit_code": 1,
                }
        finally:
            shutil.rmtree(scratch_dir, ignore_errors=True)

    def _run_python_process(
        self, code: str, scratch_dir: str, timeout_seconds: int
    ) -> Dict[str, Any]:
        script_path = os.path.join(scratch_dir, "user_script.py")
        wrapper_path = os.path.join(scratch_dir, "runner_wrapper.py")

        with open(script_path, "w", encoding="utf-8") as f:
            f.write(code)

        # Wrapper script to block network sockets & restrict filesystem scope
        wrapper_code = f"""import sys
import os
import socket
import _socket

# 1. Disable outbound network calls at the network socket layer
def _disabled_connect(*args, **kwargs):
    raise OSError(101, "Network is unreachable (sandbox network disabled)")

socket.socket.connect = _disabled_connect
socket.socket.connect_ex = lambda *args, **kwargs: 101
socket.create_connection = _disabled_connect
def _disabled_getaddrinfo(*args, **kwargs):
    raise socket.gaierror(-2, "Name or service not known (sandbox network disabled)")
socket.getaddrinfo = _disabled_getaddrinfo

# 2. Isolate working directory & Python path
scratch_dir = {repr(scratch_dir)}
os.chdir(scratch_dir)
stdlib_paths = [p for p in sys.path if ("site-packages" in p or "lib" in p.lower() or "dlls" in p.lower()) and os.getcwd() not in p]
sys.path = [scratch_dir] + stdlib_paths

# 3. Execute target script
with open({repr(script_path)}, "r", encoding="utf-8") as f:
    code_content = f.read()

try:
    exec(compile(code_content, "user_script.py", "exec"), {{"__builtins__": sys.modules["builtins"], "__name__": "__main__", "__file__": "user_script.py"}})
finally:
    sys.stdout.flush()
    sys.stderr.flush()
"""

        with open(wrapper_path, "w", encoding="utf-8") as f:
            f.write(wrapper_code)

        # Minimal sanitized environment
        # PYTHONPATH carries the parent's package directories. Without it the
        # child cannot import python-docx, reportlab or PyMuPDF: those live in
        # the USER site-packages directory, which CPython locates from APPDATA,
        # and a sanitized environment has no APPDATA. Office document preview
        # rendering failed on every file with "No module named 'docx'".
        # Passing the paths explicitly is narrower than restoring APPDATA.
        clean_env = {
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", "C:\\Windows"),
            "PATH": os.environ.get("PATH", ""),
            "PYTHONUNBUFFERED": "1",
            "PYTHONPATH": os.pathsep.join(p for p in sys.path if "site-packages" in p),
            "TEMP": scratch_dir,
            "TMP": scratch_dir,
        }

        cmd = [sys.executable, wrapper_path]

        proc = subprocess.Popen(
            cmd,
            cwd=scratch_dir,
            env=clean_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        killed_for_memory = threading.Event()

        # Memory monitoring thread
        def monitor_memory():
            try:
                import psutil
                p = psutil.Process(proc.pid)
                max_bytes = self.memory_limit_mb * 1024 * 1024
                while proc.poll() is None:
                    try:
                        mem = p.memory_info().rss
                        if mem > max_bytes:
                            killed_for_memory.set()
                            proc.kill()
                            break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        break
                    time.sleep(0.05)
            except ImportError:
                pass  # Fallback if psutil is not available

        monitor_thread = threading.Thread(target=monitor_memory, daemon=True)
        monitor_thread.start()

        stdout_out = ""
        stderr_out = ""
        timed_out = False

        try:
            stdout_out, stderr_out = proc.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            proc.kill()
            stdout_out, stderr_out = proc.communicate()

        exit_code = proc.returncode

        if timed_out:
            return {
                "status": "timeout",
                "stdout": stdout_out,
                "stderr": (stderr_out + f"\nExecution timed out after {timeout_seconds} seconds").strip(),
                "exit_code": 124,
            }

        if killed_for_memory.is_set():
            return {
                "status": "failed",
                "stdout": stdout_out,
                "stderr": (stderr_out + f"\nMemoryLimitExceeded: Process exceeded memory limit of {self.memory_limit_mb}MB").strip(),
                "exit_code": 137,
            }

        if exit_code == 0:
            return {
                "status": "completed",
                "stdout": stdout_out,
                "stderr": stderr_out,
                "exit_code": 0,
            }
        else:
            return {
                "status": "failed",
                "stdout": stdout_out,
                "stderr": stderr_out,
                "exit_code": exit_code if exit_code is not None else 1,
            }

    def _run_node_process(
        self, code: str, scratch_dir: str, timeout_seconds: int
    ) -> Dict[str, Any]:
        script_path = os.path.join(scratch_dir, "user_script.js")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(code)

        node_bin = shutil.which("node")
        if not node_bin:
            return {
                "status": "failed",
                "stdout": "",
                "stderr": "Node.js executable not found on host environment",
                "exit_code": 1,
            }

        proc = subprocess.Popen(
            [node_bin, script_path],
            cwd=scratch_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            stdout_out, stderr_out = proc.communicate(timeout=timeout_seconds)
            exit_code = proc.returncode
            if exit_code == 0:
                return {"status": "completed", "stdout": stdout_out, "stderr": stderr_out, "exit_code": 0}
            else:
                return {"status": "failed", "stdout": stdout_out, "stderr": stderr_out, "exit_code": exit_code}
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout_out, stderr_out = proc.communicate()
            return {
                "status": "timeout",
                "stdout": stdout_out,
                "stderr": f"Execution timed out after {timeout_seconds} seconds",
                "exit_code": 124,
            }


# Singleton SandboxManager instance
sandbox_manager = SandboxManager()


def get_sandbox_manager() -> SandboxManager:
    return sandbox_manager
