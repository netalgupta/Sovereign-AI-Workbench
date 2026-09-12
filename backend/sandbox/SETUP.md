# Sandbox worker pool — setup

## 1. Backend dependencies

Add to your requirements file:

```
docker>=7.1.0
pydantic>=2.0
```

`docker` is the `docker-py` SDK — talks to the local Docker daemon over
`/var/run/docker.sock` (Linux) or the named pipe on Windows. Since your
backend is **not** dockerized, this works out of the box: no socket
mount, no extra permissions beyond your user being in the `docker` group
(or running as a user with daemon access).

## 2. Build the image (on a machine with internet)

```bash
docker build -t mrpl-sandbox:combined -f Dockerfile.sandbox .
```

## 3. Export for air-gapped transfer

```bash
docker save mrpl-sandbox:combined -o mrpl-sandbox.tar
```

Transfer `mrpl-sandbox.tar` into the facility via your approved process
(USB, secure file transfer, whatever MRPL's policy dictates).

## 4. Load on the production host

```bash
docker load -i mrpl-sandbox.tar
docker images | grep mrpl-sandbox   # sanity check it's there
```

From this point on, the pool never needs network access to fetch or
install anything — `pool.py` runs `mrpl-sandbox:combined` entirely
against the local image cache.

## 5. Environment variables

```
SANDBOX_POOL_SIZE=4     # optional, defaults to 4 -- number of warm workers
```

## 6. Wire into your app

Copy `backend/sandbox/` into your existing `backend/` directory as-is —
it's self-contained and only imports `docker` and `pydantic`. Then apply
the changes shown in `dispatch_integration.py`:

1. `dispatch.py` — swap the placeholder `run_code_step()` for the import
   from `backend.sandbox`.
2. Your FastAPI app entrypoint — add the `lifespan` context manager so
   `pool.start()` / `pool.shutdown()` run at boot/exit.
3. Your session websocket handler — call `pool.release_session(session_id)`
   on disconnect so idle workers free up for other sessions.

## 7. Verify

```bash
pytest backend/tests/test_sandbox.py -v
```

The `test_zero_network` case is your NFR-5 / security-model proof —
worth screenshotting for the hackathon writeup. `test_sticky_session_reuses_same_worker`
proves the pooling actually works as intended (no cold start on the
second call).

## Notes on the two knobs you'll want to tune later

- `MAX_EXECS_BEFORE_RECYCLE` / `MAX_WORKER_AGE_SECONDS` in `pool.py` —
  bounds how long a single container stays alive before being torn down
  and respawned, regardless of activity. 200 execs / 1 hour are
  reasonable hackathon defaults; tighten if you see any memory creep in
  a long demo session.
- `SESSION_IDLE_TIMEOUT_SECONDS` — how long an inactive chat session
  keeps its worker reserved before it's freed for someone else. 15
  minutes is a reasonable default for an operator workbench; shorten if
  you expect many concurrent operators and only 4 workers.
