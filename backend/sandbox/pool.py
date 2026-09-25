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


class SandboxImageMissing(RuntimeError):
    """No usable sandbox image exists LOCALLY.

    Raised instead of letting docker-py's containers.run() fall back
    to pulling the image from a public registry, which is an outbound
    network call this product must never make.
    """

IMAGE = os.environ.get("SANDBOX_IMAGE", "mrpl-sandbox:combined")
def _default_sessions_dir() -> str:
    """Host directory bind-mounted into every worker.

    This was hardcoded "/tmp/sandbox_sessions". On Windows that is not a
    real path, so Docker Desktop created an EMPTY anonymous mount at
    /sandbox/sessions rather than failing: the container started fine,
    the executor wrote script.py to a Windows path, and the container
    saw an empty directory. Every execution then died with

        python: can't open file '/sandbox/sessions/<id>/script.py':
        [Errno 2] No such file or directory

    which reads as a sandbox bug rather than as a mount that silently
    mapped nowhere. Same class as the os.uname() crash already fixed in
    this file: a POSIX assumption that degrades quietly on Windows
    instead of erroring.

    tempfile.gettempdir() resolves under the user profile on Windows,
    which Docker Desktop shares by default, and to /tmp on Linux.
    """
    override = os.environ.get("SANDBOX_SESSIONS_HOST_DIR")
    if override:
        return override
    import tempfile

    return os.path.join(tempfile.gettempdir(), "mrpl_sandbox_sessions")


SESSIONS_HOST_DIR = _default_sessions_dir()   # bind-mounted rw into every worker
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

    def _image_present(self, tag: str) -> bool:
        """Is this image already on this machine?

        images.get() is a purely local lookup. That distinction is the
        whole point of this method existing -- see _resolve_image.
        """
        try:
            self.client.images.get(tag)
            return True
        except (docker.errors.ImageNotFound, docker.errors.APIError):
            return False

    def _resolve_image(self) -> str:
        """The sandbox image, or raise. NEVER reaches the network.

        THE BUG THIS FIXES IS AN EGRESS BUG, NOT A 404.

        This used to fall through and `return self.image` when nothing
        was found locally. The caller then passed that tag to
        `containers.run()`, and docker-py's run() AUTOMATICALLY PULLS an
        image it cannot find. So a missing local image turned into an
        outbound request to Docker Hub:

            404 Client Error for
            http+docker://localnpipe/v1.52/images/create
            ?tag=combined&fromImage=mrpl-sandbox
            "pull access denied for mrpl-sandbox, repository does not
             exist or may require 'docker login'"

        That line reads like a missing-image error. It is the record of
        this backend attempting to contact a public registry -- on a
        product whose first hard constraint is that it makes no outbound
        network calls, ever. It only failed because the repository
        happens not to exist; had someone published a public image under
        that name, it would have SUCCEEDED, and this system would have
        silently downloaded and executed a stranger's container image as
        its code sandbox. The air-gapped deployment would then fail at
        the customer site for reasons nobody could reproduce in dev.

        Presence is now checked explicitly before any run(), and a
        missing image raises with the build command rather than
        resolving to something the Docker client will try to fetch.

        The python:*-slim fallback is kept ONLY if already present
        locally. It is a degraded sandbox -- it lacks the pinned
        scientific stack Dockerfile.sandbox installs -- so it is logged
        as a warning, not as an equivalent.
        """
        configured = os.environ.get("SANDBOX_IMAGE", self.image)

        if self._image_present(configured):
            return configured

        for fallback in ("python:3.12-slim", "python:3.11-slim"):
            if self._image_present(fallback):
                logger.warning(
                    "Sandbox image %r is not built on this machine; falling back to "
                    "%r, which is PRESENT but DEGRADED (no pinned scientific stack). "
                    "Build the real image with: docker build -t %s -f "
                    "backend/sandbox/Dockerfile.sandbox backend/sandbox",
                    configured, fallback, configured,
                )
                return fallback

        raise SandboxImageMissing(
            f"No sandbox image available locally. Wanted {configured!r}, and neither "
            f"python:3.12-slim nor python:3.11-slim is present either.\n"
            f"  Build it:  docker build -t {configured} -f "
            f"backend/sandbox/Dockerfile.sandbox backend/sandbox\n"
            f"  Air-gapped: docker load -i mrpl-sandbox.tar\n"
            f"NOT pulling: this system makes no outbound network calls "
            f"(CLAUDE.md hard constraint #1)."
        )

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
            try:
                img_arch = self.client.images.get(resolved_img).attrs.get("Architecture")
                if img_arch in ("arm64", "aarch64"):
                    extra_kwargs["platform"] = "linux/arm64"
                else:
                    extra_kwargs["platform"] = "linux/amd64"
            except Exception:
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

    @staticmethod
    def _already_gone(exc: Exception) -> bool:
        """Is this exception "the container does not exist"?

        Checked by TYPE first, falling back to the message only if the
        docker package's exception classes cannot be imported. Matching
        on "404" or "No such container" alone would also swallow a 404
        from an unrelated endpoint, and silently succeeding at a removal
        that did not happen leaks a sandbox.
        """
        try:
            from docker.errors import NotFound

            if isinstance(exc, NotFound):
                return True
        except Exception:  # noqa: BLE001
            pass
        return "No such container" in str(exc)

    def _destroy(self, w: Worker):
        """Remove a worker's container. Already-gone is success.

        A container that does not exist is the state this function is
        trying to reach, so Docker's 404 is not an error -- but it was
        logged with logger.exception, which prints a full traceback per
        worker. On shutdown that is four tracebacks in a row, and under
        `uvicorn --reload` it is four per file save:

            ERROR pool.py:259 - failed removing container sandbox-worker-0
            docker.errors.NotFound: 404 Client Error ...
            No such container: 8c5cd984...

        It happens routinely and means nothing -- Docker reaps containers
        on exit, a previous reload already removed them, or the daemon
        restarted. The cost is not the noise itself but what it hides: a
        log where the normal case is a wall of tracebacks is a log where
        nobody notices the real one.

        Anything OTHER than a missing container is still reported in
        full, because failing to remove a container that IS there leaks
        a sandbox.
        """
        try:
            w.container.remove(force=True)
        except Exception as exc:  # noqa: BLE001
            if self._already_gone(exc):
                logger.debug("container %s was already removed", w.name)
                return
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
        with self.lock:
            if not self.workers:
                logger.info("worker pool empty on acquire — auto-starting %d workers", self.size)
                for i in range(self.size):
                    self.workers.append(self._spawn(f"sandbox-worker-{i}"))
                self._reaper_thread = threading.Thread(target=self._reaper_loop, daemon=True)
                self._reaper_thread.start()

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

    def _alive(self, w: Worker) -> bool:
        """Is this worker's container still running?"""
        try:
            w.container.reload()
            return w.container.status == "running"
        except (docker.errors.NotFound, docker.errors.APIError):
            return False

    def _healed(self, w: Worker) -> Worker:
        """The same worker slot, with a running container.

        The pool handed out workers without asking whether their container
        still existed, so one container removed from outside -- a crash, an
        OOM kill, another process's cleanup -- made every later job on that
        slot fail "No such container". It is replaced in place instead.
        """
        if self._alive(w):
            return w
        logger.warning("sandbox worker %s has no running container; respawning it", w.name)
        fresh = self._spawn(w.name)
        fresh.session_id, fresh.busy = w.session_id, w.busy
        self.workers[self.workers.index(w)] = fresh
        return fresh

    def _try_acquire_locked(self, session_id: str) -> Worker | None:
        # 1. sticky: this session already owns a worker and it's free
        for w in self.workers:
            if w.session_id == session_id and not w.busy:
                w.busy = True
                return self._healed(w)

        # 2. an unbound worker is free
        for w in self.workers:
            if w.session_id is None and not w.busy:
                w.session_id = session_id
                w.busy = True
                return self._healed(w)

        # 3. evict the least-recently-used idle worker bound to someone else
        idle = [w for w in self.workers if not w.busy]
        if not idle:
            return None
        victim = min(idle, key=lambda w: w.last_used)
        self._wipe_workspace(victim)
        victim.session_id = session_id
        victim.busy = True
        return self._healed(victim)

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
