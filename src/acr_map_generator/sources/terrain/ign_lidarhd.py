"""IGN LiDAR HD terrain model (MNT, 50 cm native) via the Géoplateforme WMS-R.

The service returns raw float32 elevations as GeoTIFF, so no point-cloud processing is
needed for a first terrain. Licence: Etalab Licence Ouverte 2.0 (attribution: IGN).
"""

from __future__ import annotations

import math
import time
from io import BytesIO
from pathlib import Path

import numpy as np
import rasterio
import requests
from rasterio.transform import from_origin

from ...core.area import Area
from ...core.registry import USER_AGENT, SourceInfo, register

WMS_URL = "https://data.geopf.fr/wms-r/wms"
LAYER = "IGNF_LIDAR-HD_MNT_ELEVATION.ELEVATIONGRIDCOVERAGE.LAMB93"
TILE_PX = 2000  # pixels per request side
NODATA = -99999.0
CRS = "EPSG:2154"
# Rough envelope of metropolitan France + Corsica (WGS84). Actual LiDAR HD coverage is checked
# at fetch time: uncovered cells come back as nodata.
ENVELOPE = (-5.5, 41.3, 9.7, 51.2)


def _get_tile(minx: float, miny: float, maxx: float, maxy: float, w: int, h: int) -> np.ndarray:
    params = {
        "SERVICE": "WMS",
        "VERSION": "1.3.0",
        "REQUEST": "GetMap",
        "LAYERS": LAYER,
        "STYLES": "",
        "CRS": CRS,
        "BBOX": f"{minx},{miny},{maxx},{maxy}",
        "WIDTH": w,
        "HEIGHT": h,
        "FORMAT": "image/geotiff",
    }
    for attempt in range(4):
        r = requests.get(WMS_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=120)
        if r.ok and r.headers.get("content-type", "").startswith("image/"):
            with rasterio.open(BytesIO(r.content)) as src:
                return src.read(1).astype(np.float32)
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"WMS request failed ({r.status_code}): {r.text[:300]}")


class IgnLidarHD:
    info = SourceInfo(
        id="ign_lidarhd",
        kind="terrain",
        title="IGN LiDAR HD MNT (50 cm)",
        coverage="France incl. Corsica (progressive national coverage)",
        licence="Etalab Licence Ouverte 2.0",
        attribution="© IGN – LiDAR HD (Etalab 2.0)",
        url="https://geoservices.ign.fr/lidarhd",
    )

    def covers(self, area: Area) -> bool:
        w, s, e, n = ENVELOPE
        return area.crs == CRS and w <= area.west and area.east <= e and s <= area.south and area.north <= n

    def fetch(self, area: Area, out_dir: Path) -> Path:
        if area.crs != CRS:
            raise ValueError(f"IGN LiDAR HD is served in {CRS}; set crs accordingly")
        out = out_dir / f"{self.info.id}.tif"
        self.fetch_bbox(area.projected_bbox(), area.resolution, out)
        return out

    def fetch_bbox(self, bbox: tuple[float, float, float, float], res: float, out: Path, quiet: bool = False) -> Path:
        """Fetch an arbitrary EPSG:2154 bbox (snapped to res) at res metres into a GeoTIFF."""
        minx, miny, maxx, maxy = bbox
        width = round((maxx - minx) / res)
        height = round((maxy - miny) / res)
        dtm = np.full((height, width), NODATA, dtype=np.float32)

        nx, ny = math.ceil(width / TILE_PX), math.ceil(height / TILE_PX)
        if not quiet:
            print(f"DTM {width}x{height} px @ {res} m, {nx * ny} request(s)")
        for j in range(ny):
            for i in range(nx):
                c0, r0 = i * TILE_PX, j * TILE_PX
                w, h = min(TILE_PX, width - c0), min(TILE_PX, height - r0)
                tminx = minx + c0 * res
                tmaxy = maxy - r0 * res
                tile = _get_tile(tminx, tmaxy - h * res, tminx + w * res, tmaxy, w, h)
                dtm[r0 : r0 + h, c0 : c0 + w] = tile
                if not quiet:
                    print(f"  tile {j * nx + i + 1}/{nx * ny}")

        # The service fills areas without coverage with large negative values
        dtm[dtm < -1000] = NODATA
        valid = dtm != NODATA
        if not valid.any():
            raise RuntimeError("no LiDAR HD coverage in this area")
        if not quiet:
            print(f"elevation {dtm[valid].min():.1f} .. {dtm[valid].max():.1f} m, coverage {valid.mean() * 100:.1f}%")

        with rasterio.open(
            out,
            "w",
            driver="GTiff",
            width=width,
            height=height,
            count=1,
            dtype="float32",
            crs=CRS,
            transform=from_origin(minx, maxy, res, res),
            nodata=NODATA,
            compress="deflate",
            predictor=3,
            tiled=True,
        ) as dst:
            dst.write(dtm, 1)
        return out


register(IgnLidarHD())
