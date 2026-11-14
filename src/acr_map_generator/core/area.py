"""Area: a WGS84 bbox with a projected working CRS and grid resolution (a stage's fetch area)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pyproj import Transformer

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"


@dataclass(frozen=True)
class Area:
    name: str
    title: str
    # WGS84 bbox (lon/lat degrees)
    west: float
    south: float
    east: float
    north: float
    crs: str  # projected working CRS, e.g. EPSG:2154 (Lambert-93) for France
    resolution: float  # DTM cell size in metres
    # Explicit provider per data kind, e.g. {"terrain": "ign_lidarhd"}. Missing kinds are auto-selected.
    sources: dict[str, str] = field(default_factory=dict)

    @property
    def data_dir(self) -> Path:
        d = DATA_DIR / self.name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def kind_dir(self, kind: str) -> Path:
        d = self.data_dir / kind
        d.mkdir(parents=True, exist_ok=True)
        return d

    def projected_bbox(self) -> tuple[float, float, float, float]:
        """bbox in working CRS (minx, miny, maxx, maxy), snapped outward to the resolution grid."""
        t = Transformer.from_crs("EPSG:4326", self.crs, always_xy=True)
        xs, ys = [], []
        # sample the edges so curvature of the projection is covered
        n = 16
        for i in range(n + 1):
            f = i / n
            for lon, lat in (
                (self.west + f * (self.east - self.west), self.south),
                (self.west + f * (self.east - self.west), self.north),
                (self.west, self.south + f * (self.north - self.south)),
                (self.east, self.south + f * (self.north - self.south)),
            ):
                x, y = t.transform(lon, lat)
                xs.append(x)
                ys.append(y)
        r = self.resolution
        snap_lo = lambda v: (v // r) * r  # noqa: E731
        snap_hi = lambda v: -((-v) // r) * r  # noqa: E731
        return snap_lo(min(xs)), snap_lo(min(ys)), snap_hi(max(xs)), snap_hi(max(ys))
