"""Vista terrain: a coarse DTM far around the stage, for the distant scenery ring (render only).

The stage area (waypoints + margin) is too small to reach the horizon from the road. This fetches the
centreline bbox grown by MARGIN metres at RES metres, as manifest layer `terrain_vista`. The vista
mesh samples the base DTM where it exists and this layer beyond it.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ..core import manifest, registry
from ..core.stage import Stage

MARGIN = 5000.0  # m around the centreline bbox
RES = 25.0  # m


def fetch_vista(stage: Stage, margin: float = MARGIN, res: float = RES) -> Path:
    area = stage.area
    cl_path = manifest.layer_path(area, "route")  # the OSM route guide is close enough for a 5 km margin
    if cl_path is None:
        raise FileNotFoundError(f"needs the route guide first; run: build {stage.name}")
    cl = np.array(json.loads(cl_path.read_text(encoding="utf-8"))["features"][0]["geometry"]["coordinates"])[:, :2]
    provider = registry.select("terrain", area)
    if not hasattr(provider, "fetch_bbox"):
        raise NotImplementedError(f"terrain provider {provider.info.id!r} cannot fetch a bbox")
    lo, hi = cl.min(axis=0) - margin, cl.max(axis=0) + margin
    bbox = (
        np.floor(lo[0] / res) * res,
        np.floor(lo[1] / res) * res,
        np.ceil(hi[0] / res) * res,
        np.ceil(hi[1] / res) * res,
    )
    out = area.kind_dir("terrain_vista") / f"{provider.info.id}_{int(res)}m.tif"
    provider.fetch_bbox(bbox, res, out)
    manifest.record(area, provider, out, kind="terrain_vista", extra={"resolution_m": res, "margin_m": margin})
    return out
