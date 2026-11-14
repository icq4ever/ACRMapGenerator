"""Repository content guard: fail if tracked files include game data, generated outputs or large blobs.

    uv run python scripts/check_repo_content.py

Run before opening a pull request; CI runs it on every push.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import PurePosixPath

MAX_BYTES = 1_000_000
# Game data, mappings, engine libraries, generated geodata and meshes: never tracked.
FORBIDDEN_EXT = {
    ".pak", ".ucas", ".utoc", ".uasset", ".uexp", ".umap", ".ubulk", ".usmap", ".jmap",  # Unreal / ACR
    ".nefs", ".dat", ".pssg", ".dds", ".bnk",  # other game formats
    ".tif", ".tiff", ".laz", ".las", ".glb", ".gltf", ".obj", ".fbx", ".npy", ".npz",  # generated data / meshes
}  # fmt: skip
FORBIDDEN_NAME_PARTS = ("oo2core",)  # Oodle libraries
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
IMAGE_DIRS = ("assets/", "docs/media/")  # images allowed only here (no game art)
FORBIDDEN_DIRS = ("data/", "private/")


def main() -> int:
    files = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True).stdout.decode().split("\0")
    problems = []
    for f in filter(None, files):
        p = PurePosixPath(f)
        ext = p.suffix.lower()
        if any(f.startswith(d) for d in FORBIDDEN_DIRS):
            problems.append(f"{f}: generated or private folder")
        if ext in FORBIDDEN_EXT:
            problems.append(f"{f}: forbidden file type {ext}")
        if any(part in p.name.lower() for part in FORBIDDEN_NAME_PARTS):
            problems.append(f"{f}: forbidden library")
        if ext in IMAGE_EXT and not f.startswith(IMAGE_DIRS):
            problems.append(f"{f}: images only in {', '.join(IMAGE_DIRS)}")
        try:
            size = len(subprocess.run(["git", "cat-file", "-p", f":{f}"], capture_output=True, check=True).stdout)
        except subprocess.CalledProcessError:
            continue  # deleted in the working tree
        if size > MAX_BYTES and f != "uv.lock":
            problems.append(f"{f}: {size / 1e6:.1f} MB (limit {MAX_BYTES / 1e6:.0f} MB)")
    for line in problems:
        print(line)
    print(f"checked {len([f for f in files if f])} files: {'FAIL' if problems else 'OK'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
