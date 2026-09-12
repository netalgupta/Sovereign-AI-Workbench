"""Silence third-party import noise, before anything imports it.

THE PROBLEM. Starting the backend printed this, every time, before a
single useful line:

    UserWarning: Failed to find CUDA.
    WARNING: All log messages before absl::InitializeLog() ... STDERR
    I0000 ... oneDNN custom operations are on. You may see slightly
      different numerical results due to floating-point round-off ...
    FutureWarning: In the future `np.object` will be defined as ...
    NOTE: Redirects are currently not supported in Windows or MacOs.
    WARNING:tensorflow: ... tf.losses.sparse_softmax_cross_entropy is
      deprecated ...

repeated per worker and per reload. None of it is actionable here:

  - "Failed to find CUDA" comes from triton, pulled in by torch. torch
    on this machine is deliberately the CPU build (a GPU build hit
    cascading torch/torchvision/torchao/triton conflicts in the shared
    system Python). Ollama uses the GPU directly and does not care.
  - absl / oneDNN / tf_keras come from PaddleOCR's TensorFlow
    dependency, which is imported for OCR and never trained.
  - np.object and sparse_softmax_cross_entropy are deprecations inside
    those libraries, not in code anyone here can change.

WHY IT MATTERS MORE THAN IT LOOKS. Warnings nobody can act on train
people to skim past the console, and this backend now prints a turn
trace there that is worth reading. Twenty lines of unfixable noise
around each real message is how a genuine error -- the Windows
os.uname() crash, the sandbox image failure -- gets scrolled past.

WHAT IS NOT SUPPRESSED: anything from `backend.*`, every uvicorn access
and error line, and any warning raised by this codebase. The point is
to remove noise that cannot be acted on, never to hide our own
failures. Set WORKBENCH_VERBOSE_IMPORTS=1 to keep all of it.
"""

from __future__ import annotations

import logging
import os
import warnings


def quiet() -> None:
    """Apply the suppressions. Safe to call more than once."""
    if os.environ.get("WORKBENCH_VERBOSE_IMPORTS"):
        return

    # These are read by the C++ layers of TensorFlow and absl AT IMPORT
    # TIME, so they must be set before the import happens -- which is why
    # this module is imported at the very top of backend/main.py, above
    # everything else, rather than tidied in with the other imports.
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")   # fatal only
    os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")  # also stops the oneDNN notice
    os.environ.setdefault("GLOG_minloglevel", "3")
    os.environ.setdefault("ABSL_MIN_LOG_LEVEL", "3")
    os.environ.setdefault("AUTOGRAPH_VERBOSITY", "0")
    os.environ.setdefault("KMP_WARNINGS", "0")
    # triton's "Failed to find CUDA" probe.
    os.environ.setdefault("TRITON_LIBCUDA_PATH", "")

    # Third-party deprecation chatter. Module-scoped so our own
    # DeprecationWarnings and RuntimeWarnings still surface -- the
    # embeddings fallback warning in particular is load-bearing.
    for module in (
        "triton", "tensorflow", "tf_keras", "keras", "torch",
        "paddle", "paddleocr", "absl",
    ):
        warnings.filterwarnings("ignore", category=UserWarning, module=module)
        warnings.filterwarnings("ignore", category=FutureWarning, module=module)
        warnings.filterwarnings("ignore", category=DeprecationWarning, module=module)

    # requests' urllib3/chardet version mismatch notice: real, but a
    # property of the shared system Python install, not of this code.
    warnings.filterwarnings("ignore", message=r".*urllib3.*chardet.*")
    warnings.filterwarnings("ignore", message=r".*Failed to find CUDA.*")
    warnings.filterwarnings("ignore", message=r".*np\.object.*")

    for name in (
        "tensorflow", "tf_keras", "keras", "absl", "paddle", "ppocr",
        "torch.distributed.elastic.multiprocessing.redirects",
    ):
        logging.getLogger(name).setLevel(logging.ERROR)
        logging.getLogger(name).propagate = False
