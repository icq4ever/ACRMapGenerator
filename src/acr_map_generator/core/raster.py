"""Small raster helper: load a single-band GeoTIFF and sample it bilinearly at world coordinates."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio


class Raster:
    def __init__(self, path: Path):
        with rasterio.open(path) as src:
            self.z = src.read(1).astype(np.float64)
            self.nodata = src.nodata
            t = src.transform
            if t.b != 0 or t.d != 0:
                raise ValueError("rotated rasters are not supported")
            self.x0, self.y0 = t.c, t.f  # top-left corner
            self.dx, self.dy = t.a, t.e  # dy is negative (north-up)
            self.crs = src.crs
        if self.nodata is not None:
            self.z[self.z == self.nodata] = np.nan

    @property
    def res(self) -> float:
        return abs(self.dx)

    def sample(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Bilinear sample at world coordinates; NaN outside the raster or next to nodata."""
        col = (np.asarray(x, dtype=np.float64) - self.x0) / self.dx - 0.5
        row = (np.asarray(y, dtype=np.float64) - self.y0) / self.dy - 0.5
        h, w = self.z.shape
        c0 = np.floor(col).astype(np.int64)
        r0 = np.floor(row).astype(np.int64)
        inside = (c0 >= 0) & (r0 >= 0) & (c0 < w - 1) & (r0 < h - 1)
        c0c = np.clip(c0, 0, w - 2)
        r0c = np.clip(r0, 0, h - 2)
        fc, fr = col - c0c, row - r0c
        z = self.z
        v = (
            z[r0c, c0c] * (1 - fc) * (1 - fr)
            + z[r0c, c0c + 1] * fc * (1 - fr)
            + z[r0c + 1, c0c] * (1 - fc) * fr
            + z[r0c + 1, c0c + 1] * fc * fr
        )
        return np.where(inside, v, np.nan)


class LayeredRaster:
    """A base raster with finer overlay tiles on top: sample() takes the overlay value where one
    covers the point and the base value elsewhere. Other attributes (z, x0, res, ...) are the base's."""

    def __init__(self, base: Raster, overlays: list[Raster]):
        self.base = base
        self.overlays = overlays
        self.bounds = [
            (o.x0 + o.res, o.y0 + o.z.shape[0] * o.dy + o.res, o.x0 + o.z.shape[1] * o.dx - o.res, o.y0 - o.res)
            for o in overlays
        ]

    def __getattr__(self, name):
        return getattr(self.base, name)

    @property
    def fine_res(self) -> float:
        return min((o.res for o in self.overlays), default=self.base.res)

    def sample(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        x = np.asarray(x, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        v = self.base.sample(x, y)
        for o, (x0, y0, x1, y1) in zip(self.overlays, self.bounds):
            k = (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1)
            if k.any():
                f = o.sample(x[k], y[k])
                ok = ~np.isnan(f)
                vk = v[k]
                vk[ok] = f[ok]
                v[k] = vk
        return v


def load_terrain(area) -> Raster | LayeredRaster:
    """Terrain for an area: the base DTM layer, plus the fine corridor tiles if they were fetched."""
    import json

    from . import manifest

    base_path = manifest.layer_path(area, "terrain")
    if base_path is None:
        raise FileNotFoundError(f"no terrain layer for {area.name!r}")
    base = Raster(base_path)
    fine_index = manifest.layer_path(area, "terrain_fine")
    if fine_index is None:
        return base
    tiles = json.loads(fine_index.read_text(encoding="utf-8"))["tiles"]
    return LayeredRaster(base, [Raster(fine_index.parent / t["file"]) for t in tiles])
