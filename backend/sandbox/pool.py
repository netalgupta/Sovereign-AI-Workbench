"""
backend/sandbox/pool.py

Manages a fixed pool of warm, already-running Docker containers so that
code execution pays only a process-fork cost (docker exec) instead of a
full container-create cost (docker run) on every call.

Lifecycle:
  - N workers are spawned once, at app startup, from `mrpl-sandbox:combined`.
  - A session is "stickily" bound to one worker for the life of the chat,
    so repeated tool calls (including the code_agent's self-correction
    retries) reuse the same warm container.
  - Idle workers are recycled (workspace wiped) when reassigned to a new
    session, and every worker is hard-recycled (container destroyed +
    respawned) after MAX_EXECS_BEFORE_RECYCLE executions or
    MAX_WORKER_AGE_SECONDS uptime, whichever comes first, to bound any
    long-running-process resource creep.
"""

from __future__ import annotations

import os
import platform
import shutil
import threading
import time
import logging
from dataclasses import dataclass, field

import docker
from docker.models.containers import Container

logger = logging.getLogger("sandbox.pool")

IMAGE = os.environ.get("SANDBOX_IMAGE", "mrpl-sandbox:combined")
SESSIONS_HOST_DIR = os.environ.get("SANDBOX_SESSIONS_HOST_DIR", "/tmp/sandbox_sessions")   # bind-mounted rw into every worker
SESSIONS_CONTAINER_DIR = "/sandbox/sessions"

MAX_EXECS_BEFORE_RECYCLE = 200
MAX_WORKER_AGE_SECONDS = 60 * 60          # 1 hour hard recycle
SESSION_IDLE_TIMEOUT_SECONDS = 15 * 60    # unbind session after 15 min idle


@dataclass
class Worker:
    name: str
    container: Container
    session_id: str | None = None
    busy: bool = False
    exec_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)


class WorkerPoolExhausted(RuntimeError):
    pass


class WorkerPool:
    def __init__(self, size: int = 4, image: str = IMAGE):
        self.size = size
        self.image = image
        self._client: docker.DockerClient | None = None
        self.lock = threading.RLock()
        self.workers: list[Worker] = []
        os.makedirs(SESSIONS_HOST_DIR, exist_ok=True)
        self._reaper_stop = threading.Event()
        self._reaper_thread: threading.Thread | None = None

    @property
    def client(self) -> docker.DockerClient:
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    def _resolve_image(self) -> str:
        """Use configured image, or fall back gracefully to local python image if not built yet."""
        if "SANDBOX_IMAGE" in os.environ:
            return os.environ["SANDBOX_IMAGE"]
        try:
            self.client.images.get(self.image)
            return self.image
        except (docker.errors.ImageNotFound, docker.errors.APIError):
            for fallback in ("python:3.12-slim", "python:3.11-slim"):
                try:
                    self.client.images.get(fallback)
                    logger.info("Sandbox image '%s' not found; using fallback '%s'", self.image, fallback)
                    return fallback
                except (docker.errors.ImageNotFound, docker.errors.APIError):
                    continue
            return self.image

    # ---------------------------------------------------------------- boot

    def start(self):
        """Call once at app startup."""
        with self.lock:
            for i in range(self.size):
                self.workers.append(self._spawn(f"sandbox-worker-{i}"))
        self._reaper_thread = threading.Thread(target=self._reaper_loop, daemon=True)
        self._reaper_thread.start()
        logger.info("worker pool started: %d workers from %s", self.size, self.image)

    def shutdown(self):
        """Call once at app shutdown. Not dockerized here, so this just
        needs to run on interpreter exit / SIGTERM handler."""
        self._reaper_stop.set()
        with self.lock:
            for w in self.workers:
                self._destroy(w)
            self.workers.clear()
        logger.info("worker pool shut down")

    def _spawn(self, name: str) -> Worker:
        # remove any stale container left over from a crashed previous run
        try:
            old = self.client.containers.get(name)
            old.remove(force=True)
        except (docker.errors.NotFound, docker.errors.APIError):
            pass

        resolved_img = self._resolve_image()
        extra_kwargs: dict = {}
        # Avoid exec format errors on Apple Silicon when running amd64 images.
        #
        # platform.system() rather than os.uname(): os.uname does not
        # exist on Windows at all, so this raised AttributeError inside
        # pool startup and the sandbox silently never came up —
        # "Could not start sandbox pool: module 'os' has no attribute
        # 'uname'" in the server log, with code execution quietly
        # unavailable for the rest of the session. platform.system()
        # is the portable spelling and returns "Darwin" on macOS just
        # the same.
        if platform.system() == "Darwin" or "DOCKER_DEFAULT_PLATFORM" in os.environ:
            extra_kwargs["platform"] = os.environ.get("DOCKER_DEFAULT_PLATFORM", "linux/amd64")

        # useradd UID 1000 is baked into mrpl-sandbox:combined
        # if using plain python-slim, standard numeric user or root can run
        run_user = "1000:1000" if resolved_img == self.image else None

        container_kwargs = dict(
            command="sleep infinity",
            detach=True,
            name=name,
            network_disabled=True,
            read_only=True,
            tmpfs={"/tmp": "size=64m"},
            mem_limit="512m",
            nano_cpus=1_000_000_000,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges"],
            volumes={SESSIONS_HOST_DIR: {"bind": SESSIONS_CONTAINER_DIR, "mode": "rw"}},
            **extra_kwargs,
        )
        if run_user:
            container_kwargs["user"] = run_user

        container = self.client.containers.run(resolved_img, **container_kwargs)
        return Worker(name=name, container=container)

    def _destroy(self, w: Worker):
        try:
            w.container.remove(force=True)
        except Exception:
            logger.exception("failed removing container %s", w.name)

    def _respawn(self, w: Worker):
        self._destroy(w)
        fresh = self._spawn(w.name)
        w.container = fresh.container
        w.created_at = fresh.created_at
        w.exec_count = 0
        w.session_id = None
        w.busy = False
        w.last_used = time.time()

    # ------------------------------------------------------------ acquire

    def acquire(self, session_id: str, wait_timeout: float = 30.0) -> Worker:
        """Get the worker for this session, blocking briefly if the pool
        is momentarily full. Raises WorkerPoolExhausted if none free up
        in time -- caller should surface this as a "system busy" message,
        not a code error."""
        deadline = time.time() + wait_timeout
        while True:
            with self.lock:
                w = self._try_acquire_locked(session_id)
                if w is not None:
                    return w
            if time.time() >= deadline:
                raise WorkerPoolExhausted(
                    f"no sandbox worker available for session {session_id!r} "
                    f"after {wait_timeout}s"
                )
            time.sleep(0.2)

    def _try_acquire_locked(self, session_id: str) -> Worker | None:
        # 1. sticky: this session already owns a worker and it's free
        for w in self.workers:
            if w.session_id == session_id and not w.busy:
                w.busy = True
                return w

        # 2. an unbound worker is free
        for w in self.workers:
            if w.session_id is None and not w.busy:
                w.session_id = session_id
                w.busy = True
                return w

        # 3. evict the least-recently-used idle worker bound to someone else
        idle = [w for w in self.workers if not w.busy]
        if not idle:
            return None
        victim = min(idle, key=lambda w: w.last_used)
        self._wipe_workspace(victim)
        victim.session_id = session_id
        victim.busy = True
        return victim

    def _wipe_workspace(self, w: Worker):
        if w.session_id:
            path = os.path.join(SESSIONS_HOST_DIR, w.session_id)
            shutil.rmtree(path, ignore_errors=True)

    def release(self, w: Worker):
        with self.lock:
            w.busy = False
            w.last_used = time.time()
            w.exec_count += 1
            if (
                w.exec_count >= MAX_EXECS_BEFORE_RECYCLE
                or (time.time() - w.created_at) >= MAX_WORKER_AGE_SECONDS
            ):
                logger.info("recycling %s (execs=%d age=%.0fs)",
                            w.name, w.exec_count, time.time() - w.created_at)
                self._wipe_workspace(w)
                self._respawn(w)

    def release_session(self, session_id: str):
        """Call on chat/session end (e.g. websocket disconnect). Unbinds
        the worker without destroying it -- it just goes back into the
        free pool for reuse by anyone."""
        with self.lock:
            for w in self.workers:
                if w.session_id == session_id and not w.busy:
                    self._wipe_workspace(w)
                    w.session_id = None

    # -------------------------------------------------------------- reaper

    def _reaper_loop(self):
        """Background thread: unbinds sessions idle past the timeout so
        their worker becomes available to others again."""
        while not self._reaper_stop.wait(60):
            with self.lock:
                now = time.time()
                for w in self.workers:
                    if (
                        w.session_id is not None
                        and not w.busy
                        and (now - w.last_used) > SESSION_IDLE_TIMEOUT_SECONDS
                    ):
                        logger.info("evicting idle session %s from %s", w.session_id, w.name)
                        self._wipe_workspace(w)
                        w.session_id = None


# Module-level singleton -- import this from executor.py / dispatch.py
pool = WorkerPool(size=int(os.environ.get("SANDBOX_POOL_SIZE", 4)))
