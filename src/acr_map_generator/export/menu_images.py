"""Menu images for a stage (docs/menu-images.md): location logo and tile, stage art.

Lookup, first match wins:
1. `local/` (git-ignored): personal-use images, e.g. ones carrying third-party marks. Never committed or released.
2. the repository (`locations/`, `stages/`): images licensed CC BY-SA 4.0 like the stage files.

The Stage IR export copies what it finds to `<IR>/menu/<kind>.png`, where acr-extrastages picks it up, and records
each file's origin in stage.json `menu` so that a public release can leave local-only images out.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from ..core.area import PROJECT_ROOT
from ..core.stage import Stage

LOCAL = PROJECT_ROOT / "local"
KINDS = (
    ("logo", "locations/{location}/logo.png"),
    ("tile", "locations/{location}/tile.png"),
    ("art", "stages/{stage}/art.png"),
)


def find(stage: Stage) -> dict[str, tuple[Path, str]]:
    """kind -> (path, origin) for every menu image that exists; origin is "local" or "repo"."""
    found = {}
    for kind, pattern in KINDS:
        rel = pattern.format(location=stage.location_id, stage=stage.name)
        for root, origin in ((LOCAL, "local"), (PROJECT_ROOT, "repo")):
            p = root / rel
            if p.is_file():
                found[kind] = (p, origin)
                break
    return found


def fingerprint(stage: Stage) -> dict[str, str]:
    """kind -> origin:sha256 prefix, for the pipeline: changing an image re-exports the IR."""
    return {k: f"{o}:{hashlib.sha256(p.read_bytes()).hexdigest()[:16]}" for k, (p, o) in find(stage).items()}


def copy_to(stage: Stage, ir_dir: Path) -> dict[str, dict]:
    """Copy found images to <ir_dir>/menu/<kind>.png; returns the stage.json `menu` extension."""
    found = find(stage)
    menu = {}
    if found:
        (ir_dir / "menu").mkdir(exist_ok=True)
    for kind, (src, origin) in found.items():
        dst = ir_dir / "menu" / f"{kind}.png"
        shutil.copyfile(src, dst)
        menu[kind] = {"file": f"menu/{kind}.png", "origin": origin}
    return menu
