"""Ground colour tiles for the Stage IR from aerial imagery (render/ground_bake/, schema ground_bake/1).

Same layout as the builder's DR2 ground bake (builder/docs/stage-ir.md, "ground_bake"), so the builder maps them the
same way: each terrain triangle goes to the high tile whose `assign_bounds` holds its centroid, else to such a low tile;
inside a tile u = (x - bounds.min_x) / size_m, v = (z - bounds.min_z) / size_m, v = 0 being the first DDS row.

IR x = easting - origin, z = origin - northing, so a north-up image has its first row at min_z.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ..core import manifest
from ..core.area import Area
from ..process.imagery import TIERS, Tier, squares_near
from ..sources.imagery.ign_bdortho import read_rgb
from .dds import write_bc1_dds

SCHEMA = "ground_bake/1"


def _ir_box(b: tuple[float, float, float, float], ox: float, oy: float) -> dict:
    min_e, min_n, max_e, max_n = b
    return {"min_x": min_e - ox, "min_z": oy - max_n, "max_x": max_e - ox, "max_z": oy - min_n}


def write_ground_bake(area: Area, out: Path, ox: float, oy: float, centre_en: np.ndarray) -> dict | None:
    """Writes out/render/ground_bake/ for the tiles near centre_en (projected E, N of the exported centreline).

    Returns the stage.json summary, or None when the imagery layer is missing."""
    index_path = manifest.layer_path(area, "imagery")
    if index_path is None:
        return None
    index = json.loads(index_path.read_text(encoding="utf-8"))
    layer = manifest.load(area)["layers"]["imagery"]
    cached = {(t["tier"], t["i"], t["j"]): index_path.parent / t["file"] for t in index["tiles"]}
    bake = out / "render" / "ground_bake"
    bake.mkdir(parents=True, exist_ok=True)
    tiles, missing, total = [], 0, 0
    for tier in TIERS:
        for i, j in sorted(squares_near(centre_en, tier, tier.band)):
            src = cached.get((tier.name, i, j))
            if src is None or not src.exists():
                missing += 1
                continue
            name = f"{tier.name}_{i}_{j}"
            img = read_rgb(src.read_bytes())
            if img.shape[:2] != (tier.px, tier.px):
                raise ValueError(f"{src}: {img.shape[1]} x {img.shape[0]} px, expected {tier.px}")
            total += write_bc1_dds(bake / f"{name}.dds", img)
            tiles.append(_tile_entry(tier, i, j, name, ox, oy))
    if not tiles:
        return None
    m = {
        "schema": SCHEMA,
        "source": {"provider": layer["provider"], "title": layer["title"], "attribution": layer["attribution"]},
        "formula": "aerial imagery, north up, BC1 sRGB with full mips",
        "tiers": [{"name": t.name, "m_per_px": t.res, "tile_px": t.px, "band_m": t.band} for t in TIERS],
        "dds_bytes": total,
        "tiles": tiles,
    }
    (bake / "manifest.json").write_text(json.dumps(m, indent=1), encoding="utf-8")
    counts = {t.name: sum(1 for x in tiles if x["tier"] == t.name) for t in TIERS}
    print(
        f"  ground bake: {', '.join(f'{n} {c}' for n, c in counts.items())} tiles, {total / 2**20:.0f} MB"
        + (f" ({missing} not in the imagery cache)" if missing else "")
    )
    return {
        "manifest": "render/ground_bake/manifest.json",
        "source": layer["provider"],
        "tiles": counts,
        "dds_bytes": total,
        "missing_tiles": missing,
    }


def _tile_entry(tier: Tier, i: int, j: int, name: str, ox: float, oy: float) -> dict:
    return {
        "name": name,
        "tier": tier.name,
        "dds": f"{name}.dds",
        "px": tier.px,
        "m_per_px": tier.res,
        "size_m": tier.size,
        "bounds": _ir_box(tier.bounds(i, j), ox, oy),
        "assign_bounds": _ir_box(tier.assign(i, j), ox, oy),
    }
