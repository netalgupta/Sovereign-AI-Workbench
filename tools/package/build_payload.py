"""Build the offline install payload for Sovereign Workbench.

Run on a machine WITH network access, once, to fill a drive (SSD/HDD) that
installs the whole system on a machine WITHOUT it:

    py -3 tools/package/build_payload.py --out E:/SovereignWorkbench \
        --python-installer C:/Downloads/python-3.13.5-amd64.exe \
        --ollama-installer C:/Downloads/OllamaSetup.exe

What goes on the drive (payload/):

    python/   the Python installer, requirements-lock.txt, and a wheelhouse
              holding every package the backend imports AND everything they
              depend on, at the versions this repo is tested with
    ollama/   OllamaSetup.exe and ONLY the models models.yaml registers
              (manifests + blobs; not every model this machine has pulled)
    app/      backend/, the built frontend (frontend/dist), models/ (the
              embedding, speech, OCR, image caches), the corpora, docs
    manifest.json   every component with its size and SHA-256, so the
              installer can verify what it copies before it copies it

WHY A LOCK FILE AND NOT requirements.txt: requirements.txt lists 28
packages; the backend imports 40 distributions (torch, transformers,
paddleocr, langgraph, neo4j, python-pptx, ... were missing). A fresh install
from it does not start. The lock pins the versions installed where the
tests pass, and `pip download` resolves their dependency closure.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import shutil
import subprocess
import sys
import time
from importlib.metadata import PackageNotFoundError, packages_distributions, version
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP_PARTS = ["backend", "models", "MRPL_RAG_Test_Corpus", "MRPL_Chart_Stress_Corpus", "docs",
             "requirements.txt", "CLAUDE.md", "README.md"]
APP_SKIP = {"__pycache__", ".pytest_cache", "tests", "node_modules", ".workbench"}
APP_SKIP_SUFFIXES = {".pyc", ".db-journal"}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ── python ─────────────────────────────────────────────────────────────────

def backend_distributions() -> dict[str, str]:
    """Every third-party distribution backend/ imports, at its installed version."""
    stdlib = set(sys.stdlib_module_names)
    modules: set[str] = set()
    for f in (REPO / "backend").rglob("*.py"):
        if "tests" in f.parts:
            continue
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                modules.add(node.module.split(".")[0])
    by_module = packages_distributions()
    pins: dict[str, str] = {}
    for module in sorted(m for m in modules if m not in stdlib and m != "backend"):
        for dist in by_module.get(module, []):
            try:
                pins[dist] = version(dist)
            except PackageNotFoundError:
                pass
    # the server itself, and uvicorn's reload-free runner
    for extra in ("uvicorn", "fastapi"):
        try:
            pins.setdefault(extra, version(extra))
        except PackageNotFoundError:
            pass
    return pins


def build_python(out: Path, installer: Path | None) -> dict:
    target = out / "python"
    wheels = target / "wheels"
    wheels.mkdir(parents=True, exist_ok=True)
    pins = backend_distributions()
    lock = target / "requirements-lock.txt"
    lock.write_text("".join(f"{d}=={v}\n" for d, v in sorted(pins.items(), key=lambda kv: kv[0].lower())),
                    encoding="utf-8")
    log(f"lock: {len(pins)} distributions -> {lock}")

    cmd = [sys.executable, "-m", "pip", "download", "-r", str(lock), "-d", str(wheels), "--only-binary=:all:"]
    cuda = sorted({v.split("+", 1)[1] for d, v in pins.items() if d.lower() == "torch" and "+" in v})
    if cuda:  # torch built for CUDA comes from its own index
        cmd += ["--extra-index-url", f"https://download.pytorch.org/whl/{cuda[0]}"]
    if any(d.lower() == "paddlepaddle-gpu" for d in pins):  # and so does Paddle's GPU build
        cmd += ["--extra-index-url",
                f"https://www.paddlepaddle.org.cn/packages/stable/{cuda[0] if cuda else 'cu126'}/"]
    log("downloading wheels (this is the only step that needs network)")
    subprocess.run(cmd, check=True)

    if installer:
        shutil.copy2(installer, target / installer.name)
        log(f"python installer: {installer.name}")
    else:
        log("WARNING: no --python-installer given; put python-3.x-amd64.exe into payload/python/")
    return {"lock": lock.name, "distributions": len(pins), "installer": installer.name if installer else None,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"}


# ── ollama ─────────────────────────────────────────────────────────────────

def registered_ollama_tags() -> list[str]:
    import yaml

    entries = yaml.safe_load((REPO / "models" / "models.yaml").read_text(encoding="utf-8")) or []
    tags = sorted({e["model"] for e in entries if e.get("backend") == "ollama"})
    return [t if ":" in t else f"{t}:latest" for t in tags]


def build_ollama(out: Path, installer: Path | None, models_dir: Path) -> dict:
    target = out / "ollama"
    (target / "models" / "blobs").mkdir(parents=True, exist_ok=True)
    copied, missing = [], []
    for tag in registered_ollama_tags():
        name, ver = tag.split(":", 1)
        manifest = models_dir / "manifests" / "registry.ollama.ai" / "library" / name / ver
        if not manifest.exists():
            missing.append(tag)
            continue
        dest_manifest = target / "models" / manifest.relative_to(models_dir)
        dest_manifest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(manifest, dest_manifest)
        data = json.loads(manifest.read_text(encoding="utf-8"))
        digests = [data["config"]["digest"], *[layer["digest"] for layer in data.get("layers", [])]]
        for digest in digests:
            blob = models_dir / "blobs" / digest.replace(":", "-")
            dest = target / "models" / "blobs" / blob.name
            if not dest.exists():
                shutil.copy2(blob, dest)
        copied.append(tag)
        log(f"ollama model {tag}: {len(digests)} blobs")
    if installer:
        shutil.copy2(installer, target / installer.name)
    else:
        log("WARNING: no --ollama-installer given; put OllamaSetup.exe into payload/ollama/")
    if missing:
        log(f"WARNING: registered but not pulled here: {missing} (run `ollama pull` first)")
    return {"models": copied, "missing": missing, "installer": installer.name if installer else None}


# ── app ────────────────────────────────────────────────────────────────────

def build_app(out: Path) -> dict:
    target = out / "app"
    dist = REPO / "frontend" / "dist"
    if not (dist / "index.html").exists():
        log("building the frontend (npm run build)")
        subprocess.run("npm run build", cwd=REPO / "frontend", shell=True, check=True)
    for part in APP_PARTS:
        src = REPO / part
        if not src.exists():
            continue
        dst = target / part
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            continue
        shutil.copytree(src, dst, dirs_exist_ok=True,
                        ignore=lambda d, names: [n for n in names
                                                 if n in APP_SKIP or Path(n).suffix in APP_SKIP_SUFFIXES])
    shutil.copytree(dist, target / "frontend" / "dist", dirs_exist_ok=True)
    log(f"app copied to {target}")
    return {"parts": [p for p in APP_PARTS if (REPO / p).exists()] + ["frontend/dist"]}


# ── manifest ───────────────────────────────────────────────────────────────

def digest_tree(root: Path) -> tuple[int, int, str]:
    """(files, bytes, sha256 over sorted (path, file sha256)) for a folder."""
    h = hashlib.sha256()
    files = total = 0
    for f in sorted(p for p in root.rglob("*") if p.is_file()):
        fh = hashlib.sha256()
        with f.open("rb") as stream:
            for block in iter(lambda: stream.read(1 << 20), b""):
                fh.update(block)
        h.update(f.relative_to(root).as_posix().encode() + b"\0" + fh.hexdigest().encode() + b"\n")
        files += 1
        total += f.stat().st_size
    return files, total, h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, type=Path, help="the drive folder, e.g. E:/SovereignWorkbench")
    ap.add_argument("--python-installer", type=Path)
    ap.add_argument("--ollama-installer", type=Path)
    ap.add_argument("--ollama-models", type=Path, default=Path.home() / ".ollama" / "models")
    ap.add_argument("--skip", nargs="*", default=[], choices=["python", "ollama", "app"])
    args = ap.parse_args()

    payload = args.out / "payload"
    payload.mkdir(parents=True, exist_ok=True)
    details = {}
    if "python" not in args.skip:
        details["python"] = build_python(payload, args.python_installer)
    if "ollama" not in args.skip:
        details["ollama"] = build_ollama(payload, args.ollama_installer, args.ollama_models)
    if "app" not in args.skip:
        details["app"] = build_app(payload)

    components = []
    for name in ("python", "ollama", "app"):
        folder = payload / name
        if folder.exists():
            files, size, sha = digest_tree(folder)
            components.append({"id": name, "files": files, "bytes": size, "sha256": sha, **details.get(name, {})})
            log(f"{name}: {files} files, {size / 1e9:.2f} GB")
    manifest = {"product": "Sovereign Workbench", "built": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "components": components}
    (payload / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log(f"manifest written: {payload / 'manifest.json'}")


if __name__ == "__main__":
    main()
