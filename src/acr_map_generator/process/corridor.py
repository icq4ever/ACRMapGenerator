"""Fine terrain corridor: fetch a higher-resolution DTM only around the stage route.

A full stage area at 0.5 m would be ~200 M cells. The corridor is a set of TILE-sized tiles (on a
global grid in the projected CRS) that intersect the centreline buffered by BUFFER metres. Each tile
is fetched with a small overlap so bilinear sampling never falls back to the base DTM at tile edges.
core.raster.load_terrain() layers these tiles over the base DTM.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ..core import manifest, registry
from ..core.stage import Stage

FINE_RES = 0.5  # m
TILE = 256.0  # m
BUFFER = 60.0  # m either side of the centreline
OVERLAP = 2.0  # m fetched beyond each tile edge


def fetch_corridor(stage: Stage, res: float = FINE_RES) -> Path:
    area = stage.area
    # The OSM route guide, not the centreline: the centreline is within a few metres of it (well inside BUFFER),
    # and using the guide lets the centreline be computed once, on the fine terrain.
    cl_path = manifest.layer_path(area, "route")
    if cl_path is None:
        raise FileNotFoundError(f"needs the route guide first; run: build {stage.name}")
    cl = np.array(json.loads(cl_path.read_text(encoding="utf-8"))["features"][0]["geometry"]["coordinates"])[:, :2]

    provider = registry.select("terrain", area)
    if not hasattr(provider, "fetch_bbox"):
        raise NotImplementedError(f"terrain provider {provider.info.id!r} cannot fetch a bbox")

    # Tiles touched by the buffered centreline: sample the buffer as a dense point cloud
    seg = np.hypot(*np.diff(cl, axis=0).T)
    s = np.r_[0, np.cumsum(seg)]
    t = np.arange(0, s[-1], 10.0)
    pts = np.column_stack([np.interp(t, s, cl[:, 0]), np.interp(t, s, cl[:, 1])])
    ring = np.array([[dx, dy] for dx in (-BUFFER, 0, BUFFER) for dy in (-BUFFER, 0, BUFFER)])
    cloud = (pts[:, None, :] + ring[None, :, :]).reshape(-1, 2)
    keys = sorted({(int(k[0]), int(k[1])) for k in np.floor(cloud / TILE)})

    out_dir = area.kind_dir("terrain_fine")
    tiles = []
    print(f"  {len(keys)} tiles of {TILE:.0f} m at {res} m ({len(keys) * (TILE / res) ** 2 / 1e6:.0f} M cells)")
    for n, (ix, iy) in enumerate(keys, 1):
        f = out_dir / f"tile_{ix}_{iy}.tif"
        if not f.exists():
            bbox = (ix * TILE - OVERLAP, iy * TILE - OVERLAP, (ix + 1) * TILE + OVERLAP, (iy + 1) * TILE + OVERLAP)
            provider.fetch_bbox(bbox, res, f, quiet=True)
        tiles.append({"file": f.name, "ix": ix, "iy": iy})
        if n % 10 == 0 or n == len(keys):
            print(f"  {n}/{len(keys)}")

    index = out_dir / "index.json"
    index.write_text(
        json.dumps({"res": res, "tile_m": TILE, "overlap_m": OVERLAP, "buffer_m": BUFFER, "tiles": tiles}, indent=1),
        encoding="utf-8",
    )
    manifest.record(area, provider, index, kind="terrain_fine", extra={"resolution_m": res, "tiles": len(tiles)})
    return index
