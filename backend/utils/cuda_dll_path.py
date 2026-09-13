"""Make the pip-installed CUDA libraries findable on Windows.

WHY THIS EXISTS, AND WHY IT IS NOT A PADDLE BUG.

With `paddlepaddle-gpu` installed, `import paddle` succeeds, reports
`is_compiled_with_cuda() True`, and puts tensors on gpu:0. Then the
first convolution fails:

    OSError: [WinError 127] The specified procedure could not be found.
    Error loading "...\\nvidia\\cudnn\\bin\\cudnn_cnn64_9.dll"
    or one of its dependencies.

The DLL is present and is the exact version paddle pins
(nvidia-cudnn-cu12==9.5.1.17). The failure is "or one of its
dependencies": cudnn_cnn64_9.dll needs cuBLAS and the CUDA runtime,
which pip installs into SIBLING directories --
nvidia/cublas/bin, nvidia/cuda_runtime/bin -- and Windows does not
search a DLL's own folder's siblings.

Torch never hits this because on Windows it bundles its CUDA DLLs inside
torch/lib and adds that one directory itself. Paddle uses the shared
nvidia-* wheels, so the directories must be registered.

WHY THE ERROR IS WORSE THAN IT LOOKS. Everything cheap reports success
-- the import, the device query, tensor placement -- and only the first
real convolution fails. So "PaddleOCR is on the GPU" looks true right up
to the moment OCR runs, which is exactly the kind of half-working state
this repo keeps finding. Hence a function that is called BEFORE paddle
is imported, rather than a note in a README.

IDEMPOTENT AND SILENT ON NON-WINDOWS. os.add_dll_directory does not
exist on Linux or macOS, where the loader resolves these through
RPATH/LD_LIBRARY_PATH already.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_applied = False
_registered: list[str] = []


def ensure_cuda_dll_path() -> list[str]:
    """Register every nvidia/*/bin directory with the Windows loader.

    Returns the directories registered (empty on non-Windows, or when
    the nvidia wheels are not installed). Safe to call repeatedly.
    """
    global _applied
    if _applied:
        return list(_registered)
    _applied = True

    if sys.platform != "win32" or not hasattr(os, "add_dll_directory"):
        return []

    # TORCH FIRST, ALWAYS, AND THE ORDER IS NOT COSMETIC.
    #
    # torch and paddle both need cuDNN 9 and get it from different
    # places: torch from its own torch/lib, paddle from the pip
    # nvidia-cudnn-cu12 wheel. Windows loads ONE DLL per base name per
    # process, so whichever binds `cudnn_graph64_9.dll` first wins and
    # the other gets WinError 127 on a symbol it expected.
    #
    # Measured, both directions:
    #   paddle first -> paddle conv OK, then torch fails on shm.dll
    #   torch first  -> torch conv OK, then paddle conv OK
    #
    # Importing torch here binds torch/lib before the nvidia
    # directories are added, which is the only ordering where both
    # frameworks work. torch is imported by the embedding path anyway,
    # so this costs nothing that was not already being paid.
    #
    # The remaining requirement is a VERSION one, and it is recorded in
    # requirements.txt rather than left to chance: nvidia-cudnn-cu12
    # must match torch's bundled cuDNN (9.10.2). paddle pins 9.5.1.17,
    # which it does not actually require -- verified by running a
    # convolution in both frameworks, in one process, on 9.10.2.21.
    try:
        import torch  # noqa: F401
    except Exception:  # noqa: BLE001 - torch absent is a valid install
        pass

    for site_dir in _site_package_dirs():
        nvidia = Path(site_dir) / "nvidia"
        if not nvidia.is_dir():
            continue
        for package in sorted(nvidia.iterdir()):
            binary_dir = package / "bin"
            if not binary_dir.is_dir():
                continue
            try:
                os.add_dll_directory(str(binary_dir))
                _registered.append(str(binary_dir))
            except OSError:
                # A directory that cannot be registered is skipped
                # rather than fatal: the loader may still find the DLL
                # another way, and refusing to start over it would be
                # worse than trying.
                continue

    return list(_registered)


def _site_package_dirs() -> list[str]:
    paths: list[str] = []
    try:
        import site

        paths.extend(site.getsitepackages())
        user_site = site.getusersitepackages()
        if isinstance(user_site, str):
            paths.append(user_site)
        else:
            paths.extend(user_site)
    except Exception:  # noqa: BLE001
        pass

    # sys.path is the fallback and also the backstop for unusual layouts.
    paths.extend(p for p in sys.path if p and p.endswith("site-packages"))

    seen: set[str] = set()
    unique: list[str] = []
    for path in paths:
        if path and path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def registered_directories() -> list[str]:
    """What was registered, for diagnostics."""
    return list(_registered)
