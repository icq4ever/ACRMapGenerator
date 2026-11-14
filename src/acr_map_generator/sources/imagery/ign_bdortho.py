"""IGN BD ORTHO aerial imagery (20 cm, RGB) via the Géoplateforme WMS-R.

Used as ground colour for the stage (export/ground_bake.py). The imagery is fetched tile by tile around the route
(process/imagery.py), not for the whole stage area. Licence: Etalab Licence Ouverte 2.0 (attribution: IGN).
"""

from __future__ import annotations

import time
import warnings
from pathlib import Path

import numpy as np
import requests
from rasterio.errors import NotGeoreferencedWarning
from rasterio.io import MemoryFile

from ...core.area import Area
from ...core.registry import USER_AGENT, SourceInfo, register

WMS_URL = "https://data.geopf.fr/wms-r/wms"
LAYER = "ORTHOIMAGERY.ORTHOPHOTOS"
CRS = "EPSG:2154"
NATIVE_RES = 0.2  # m; finer requests are upsampled by the service
MAX_PX = 4096  # pixels per request side
# Metropolitan France + Corsica (WGS84), as for the LiDAR HD terrain
ENVELOPE = (-5.5, 41.3, 9.7, 51.2)


class IgnBdOrtho:
    info = SourceInfo(
        id="ign_bdortho",
        kind="imagery",
        title="IGN BD ORTHO (20 cm)",
        coverage="France incl. Corsica",
        licence="Etalab Licence Ouverte 2.0",
        attribution="© IGN – BD ORTHO (Etalab 2.0)",
        url="https://geoservices.ign.fr/bdortho",
    )

    def covers(self, area: Area) -> bool:
        w, s, e, n = ENVELOPE
        return area.crs == CRS and w <= area.west and area.east <= e and s <= area.south and area.north <= n

    def fetch(self, area: Area, out_dir: Path) -> Path:
        raise NotImplementedError("imagery is fetched per tile around the route: see process/imagery.py")

    def fetch_jpeg(self, bbox: tuple[float, float, float, float], px: int) -> bytes:
        """JPEG of an EPSG:2154 bbox (minx, miny, maxx, maxy) at px x px; north up."""
        if px > MAX_PX:
            raise ValueError(f"{px} px per side is over the request limit {MAX_PX}")
        minx, miny, maxx, maxy = bbox
        params = {
            "SERVICE": "WMS",
            "VERSION": "1.3.0",
            "REQUEST": "GetMap",
            "LAYERS": LAYER,
            "STYLES": "",
            "CRS": CRS,
            "BBOX": f"{minx},{miny},{maxx},{maxy}",
            "WIDTH": px,
            "HEIGHT": px,
            "FORMAT": "image/jpeg",
        }
        r = None
        for attempt in range(4):
            r = requests.get(WMS_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=120)
            if r.ok and r.headers.get("content-type", "").startswith("image/"):
                return r.content
            time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"WMS request failed ({r.status_code if r else '-'}): {r.text[:300] if r else ''}")


def read_rgb(jpeg: bytes) -> np.ndarray:
    """H x W x 3 uint8 from JPEG bytes."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)  # a plain JPEG: the tile's bounds are known
        with MemoryFile(jpeg) as mf, mf.open() as src:
            return np.moveaxis(src.read([1, 2, 3]), 0, -1).copy()


register(IgnBdOrtho())
