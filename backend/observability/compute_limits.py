"""Stop CPU-bound model work from saturating the machine.

THE SYMPTOM. Sustained 99% CPU spikes during ordinary use, bad enough to
make the whole desktop unresponsive.

THE CAUSE. `torch` here is the CPU-only build (2.9.1+cpu), and PyTorch
defaults its intra-op thread pool to EVERY physical core:

    torch.get_num_threads()        -> 24
    torch.get_num_interop_threads()-> 24
    physical cores                 -> 24

So a single embedding call takes the entire CPU. Every query embeds its
text, every ingested document embeds every chunk, and OCR runs through
the same stack. Nothing was limiting any of it.

The default is right for a training box, where the process IS the
workload. It is wrong for a desktop application the user is also trying
to work on, and it is wrong twice over here: the machine is
simultaneously running Ollama, a Vite dev server, a browser and an IDE.

WHAT THIS DOES NOT CLAIM TO FIX. Embeddings and OCR still run on the
CPU, because this torch build has no CUDA. Capping threads bounds the
damage, it does not move the work. Moving it needs a CUDA torch build,
which is a real change with real risk -- see MOVING THIS TO THE GPU
below.

WHY ENVIRONMENT VARIABLES AND NOT JUST torch.set_num_threads().

OMP_NUM_THREADS and MKL_NUM_THREADS are read by OpenMP and MKL when
those libraries LOAD, which happens on `import torch`. Setting them
afterwards is silently ignored. torch.set_num_threads() is called too,
as a belt-and-braces measure for the pools that do respect a late
change, but the environment variables are the ones that matter -- which
is why this module must be imported before anything touches torch.

MOVING THIS TO THE GPU (the actual fix, not yet done).

    pip install torch torchvision --index-url \\
        https://download.pytorch.org/whl/cu121

The repo history records a previous attempt hitting cascading version
conflicts (torch <-> torchvision <-> torchao <-> triton) in this
SHARED, system-wide Python install, which had to be reverted. Doing it
safely means a dedicated virtualenv, so it is a deliberate piece of work
rather than something to slip into an unrelated change.

Ollama is unaffected either way -- it manages its own GPU placement and
already runs the reasoning model at 100% GPU.
"""

from __future__ import annotations

import os

# Leave this many physical cores for everything else on the machine:
# the OS, the browser, the IDE, Ollama's own CPU work. On a 24-core box
# the cap lands at 16, which is still ample for an embedding batch and
# leaves a third of the machine responsive.
RESERVED_CORES = 8

# Never drop below this; a 4-core laptop capped to 1 thread would make
# ingestion unusably slow, which is a different way of breaking it.
MIN_THREADS = 4

# Interop (the pool that runs independent ops in parallel) is capped
# much harder. It multiplies against the intra-op pool, and for the
# single-model, single-batch work this application does it buys almost
# nothing while contributing a great deal of scheduling churn.
MAX_INTEROP_THREADS = 2


def _thread_budget() -> int:
    override = os.environ.get("WORKBENCH_CPU_THREADS")
    if override and override.isdigit() and int(override) > 0:
        return int(override)

    try:
        import psutil

        physical = psutil.cpu_count(logical=False) or os.cpu_count() or 4
    except Exception:  # noqa: BLE001
        physical = os.cpu_count() or 4

    return max(MIN_THREADS, physical - RESERVED_CORES)


def apply() -> dict:
    """Cap CPU thread pools. Call BEFORE importing torch.

    Returns what was applied, so startup can report it rather than
    changing the machine's behaviour invisibly.
    """
    threads = _thread_budget()

    # setdefault, not assignment: an operator who has deliberately set
    # OMP_NUM_THREADS for their own reasons should win.
    for var in (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        os.environ.setdefault(var, str(threads))

    # PaddleOCR / ONNX Runtime read their own variables.
    os.environ.setdefault("FLAGS_use_mkldnn", "1")
    os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")

    return {"threads": threads, "interop": MAX_INTEROP_THREADS}


def apply_to_torch() -> dict | None:
    """Cap torch's pools directly, once it is importable.

    Separate from apply() because importing torch is expensive (seconds)
    and must not happen during the environment-variable phase -- the
    variables have to be set BEFORE the import, so this is necessarily a
    second, later call.

    Returns None when torch is not installed, which is a legitimate
    state: nothing here is required for the API to serve.
    """
    try:
        import torch
    except Exception:  # noqa: BLE001
        return None

    budget = _thread_budget()
    try:
        torch.set_num_threads(budget)
    except Exception:  # noqa: BLE001
        pass
    try:
        # Raises if any parallel work has already started, which is a
        # normal race rather than a failure worth surfacing.
        torch.set_num_interop_threads(MAX_INTEROP_THREADS)
    except Exception:  # noqa: BLE001
        pass

    return {
        "threads": torch.get_num_threads(),
        "interop": torch.get_num_interop_threads(),
        "cuda": bool(getattr(torch, "cuda", None) and torch.cuda.is_available()),
    }
