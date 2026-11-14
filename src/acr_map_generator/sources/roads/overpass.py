"""OSM road centrelines via the Overpass API, stored as GeoJSON in the working CRS.

Licence: ODbL (attribution: © OpenStreetMap contributors).
"""

from __future__ import annotations

import json
from pathlib import Path

import requests
from pyproj import Transformer

from ...core.area import Area
from ...core.registry import USER_AGENT, SourceInfo, register

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Road classes that can plausibly host a rally stage
HIGHWAYS = "primary|secondary|tertiary|unclassified|residential|track|service|primary_link|secondary_link|tertiary_link"
KEEP_TAGS = ("highway", "name", "ref", "surface", "tracktype", "lanes", "width", "oneway")


class Overpass:
    info = SourceInfo(
        id="overpass",
        kind="roads",
        title="OpenStreetMap roads (Overpass API)",
        coverage="Worldwide",
        licence="ODbL 1.0",
        attribution="© OpenStreetMap contributors (ODbL)",
        url="https://www.openstreetmap.org/copyright",
    )

    def covers(self, area: Area) -> bool:
        return True

    def fetch(self, area: Area, out_dir: Path) -> Path:
        out = out_dir / f"{self.info.id}.geojson"
        query = f"""
[out:json][timeout:120];
way["highway"~"^({HIGHWAYS})$"]({area.south},{area.west},{area.north},{area.east});
out geom tags;
"""
        r = requests.post(OVERPASS_URL, data={"data": query}, headers={"User-Agent": USER_AGENT}, timeout=180)
        r.raise_for_status()
        elements = r.json()["elements"]

        t = Transformer.from_crs("EPSG:4326", area.crs, always_xy=True)
        features = []
        for el in elements:
            geom = el.get("geometry")
            if not geom or len(geom) < 2:
                continue
            coords = [list(t.transform(p["lon"], p["lat"])) for p in geom]
            tags = el.get("tags", {})
            props = {"osm_id": el["id"], **{k: tags[k] for k in KEEP_TAGS if k in tags}}
            features.append(
                {
                    "type": "Feature",
                    "properties": props,
                    "geometry": {"type": "LineString", "coordinates": coords},
                }
            )

        fc = {
            "type": "FeatureCollection",
            "crs": {"type": "name", "properties": {"name": area.crs}},
            "features": features,
        }
        out.write_text(json.dumps(fc), encoding="utf-8")
        print(f"{len(features)} roads")
        return out


register(Overpass())
