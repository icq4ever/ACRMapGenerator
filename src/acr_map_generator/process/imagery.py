"""Aerial imagery around the route, as square tiles for the ground bake (export/ground_bake.py).

Two tiers: `high` (fine, close to the road) and `low` (coarse, the rest of the collision corridor). Tiles sit on a
grid in the projected CRS, so every Stage IR variant (each with its own origin) reuses the same downloads. A tile's
image covers its `bounds`: the grid square (`assign`, where the builder assigns triangles to it) plus a margin, so
triangles that reach past the square stay inside the texture.

Fetched tiles are cached as JPEG under data/<stage>/imagery/<provider>/; index.json lists them.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from ..core import manifest, registry
from ..core.stage import Stage

FETCH_SLACK = 30.0  # m added to each band here: the OSM route guide is used, not the LiDAR centreline


@dataclass(frozen=True)
class Tier:
    name: str
    res: float  # m per pixel
    px: int  # texture side, pixels
    margin_px: int  # pixels on each side outside the grid square
    band: float  # m from the centreline: grid squares within this distance get a tile of this tier

    @property
    def size(self) -> float:
        return self.px * self.res

    @property
    def step(self) -> float:
        return (self.px - 2 * self.margin_px) * self.res

    def assign(self, i: int, j: int) -> tuple[float, float, float, float]:
        """(min_e, min_n, max_e, max_n) of grid square (i, j)."""
        return i * self.step, j * self.step, (i + 1) * self.step, (j + 1) * self.step

    def bounds(self, i: int, j: int) -> tuple[float, float, float, float]:
        m = self.margin_px * self.res
        a = self.assign(i, j)
        return a[0] - m, a[1] - m, a[2] + m, a[3] + m

    def file(self, i: int, j: int) -> str:
        return f"{self.name}_{round(self.res * 100)}cm_{self.px}_{i}_{j}.jpg"


# high: 25 cm/px within 100 m of the road; low: 1 m/px over the 250 m collision corridor (export/stage_ir.CORRIDOR)
TIERS = (
    Tier("high", 0.25, 1024, 32, 100.0),
    Tier("low", 1.0, 2048, 32, 280.0),
)


def densify(xy: np.ndarray, step: float = 5.0) -> np.ndarray:
    """Polyline points at most `step` m apart."""
    out = [xy[:1]]
    for a, b in zip(xy[:-1], xy[1:], strict=True):
        n = max(1, math.ceil(float(np.hypot(*(b - a))) / step))
        out.append(a + (b - a) * (np.arange(1, n + 1)[:, None] / n))
    return np.vstack(out)


def squares_near(xy: np.ndarray, tier: Tier, band: float) -> set[tuple[int, int]]:
    """Grid squares of the tier within `band` m of the polyline xy (projected E, N)."""
    pts = densify(xy)
    s = tier.step
    found: set[tuple[int, int]] = set()
    for e, n in pts:
        for i in range(math.floor((e - band) / s), math.floor((e + band) / s) + 1):
            dx = max(i * s - e, 0.0, e - (i + 1) * s)
            for j in range(math.floor((n - band) / s), math.floor((n + band) / s) + 1):
                dy = max(j * s - n, 0.0, n - (j + 1) * s)
                if dx * dx + dy * dy <= band * band:
                    found.add((i, j))
    return found


def fetch_imagery(stage: Stage) -> Path:
    area = stage.area
    route = manifest.layer_path(area, "route")
    if route is None:
        raise FileNotFoundError(f"needs the route guide first; run: build {stage.name}")
    xy = np.array(json.loads(route.read_text(encoding="utf-8"))["features"][0]["geometry"]["coordinates"])[:, :2]
    provider = registry.select("imagery", area)
    out_dir = area.kind_dir("imagery") / provider.info.id
    out_dir.mkdir(parents=True, exist_ok=True)
    index = {"provider": provider.info.id, "crs": area.crs, "tiers": [], "tiles": []}
    todo = []
    for tier in TIERS:
        index["tiers"].append({**asdict(tier), "size_m": tier.size, "step_m": tier.step})
        for i, j in sorted(squares_near(xy, tier, tier.band + FETCH_SLACK)):
            f = tier.file(i, j)
            index["tiles"].append({"tier": tier.name, "i": i, "j": j, "file": f, "bounds": tier.bounds(i, j)})
            if not (out_dir / f).exists():
                todo.append((tier, i, j, f))
    print(f"  imagery: {len(index['tiles'])} tiles ({len(todo)} to download) from {provider.info.id}")
    for k, (tier, i, j, f) in enumerate(todo, 1):
        (out_dir / f).write_bytes(provider.fetch_jpeg(tier.bounds(i, j), tier.px))
        if k % 20 == 0 or k == len(todo):
            print(f"    {k}/{len(todo)}")
    path = out_dir / "index.json"
    path.write_text(json.dumps(index, indent=1), encoding="utf-8")
    manifest.record(area, provider, path, extra={"tiers": {t.name: {"res_m": t.res, "band_m": t.band} for t in TIERS}})
    return path
