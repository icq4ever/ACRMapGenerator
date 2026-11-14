"""Write a stage package (docs/stage_package.md) from the terrain and LiDAR centreline layers."""

from __future__ import annotations

import json
import shutil
from importlib.metadata import version
from pathlib import Path

import numpy as np
from pyproj import Transformer

from ..core import manifest
from ..core.raster import load_terrain
from ..core.stage import Stage
from . import images
from .gltf import write_glb
from .terrain_mesh import TILE, Frame, build_tiles

FORMAT_VERSION = 1


def _to_gltf(v: np.ndarray) -> np.ndarray:
    """Stage frame (X east, Y south, Z up) -> glTF (x = X, y = Z, z = Y)."""
    return v[:, [0, 2, 1]]


def write_package(stage: Stage) -> Path:
    area, info = stage.area, stage.config.stage
    cfg = stage.config.export.package
    if cfg is None:
        raise ValueError(f"{stage.name}: no [export.package] section")
    pid = cfg.id
    road_width = cfg.road_width

    cl_path = manifest.layer_path(area, "centreline")
    dtm_path = manifest.layer_path(area, "terrain")
    if cl_path is None or dtm_path is None:
        raise FileNotFoundError(f"needs terrain + centreline; run: build {stage.name}")
    for kind in ("centreline", "terrain"):
        if manifest.load(area)["layers"][kind].get("osm_derived"):
            raise RuntimeError(f"{kind} layer is OSM-derived; it must not go into a package")
    cl_feat = json.loads(cl_path.read_text(encoding="utf-8"))["features"][0]
    cl = np.array(cl_feat["geometry"]["coordinates"])
    z_corr = np.array(cl_feat["properties"].get("z_correction_m", np.zeros(len(cl))))
    dtm = load_terrain(area)  # base DTM + fine corridor tiles when fetched

    # Stage frame origin: integer metres at the centreline's bbox centre, Z absolute
    ox = float(np.round((cl[:, 0].min() + cl[:, 0].max()) / 2))
    oy = float(np.round((cl[:, 1].min() + cl[:, 1].max()) / 2))
    frame = Frame(ox, oy)
    X, Y = frame.to_stage(cl[:, 0], cl[:, 1])
    spline = np.column_stack([X, Y, cl[:, 2]])

    out = area.kind_dir("package") / pid
    if out.exists():
        shutil.rmtree(out)
    (out / "terrain").mkdir(parents=True)
    (out / "images").mkdir()

    # Terrain tiles
    crossfall = np.array(cl_feat["properties"].get("crossfall", np.zeros(len(cl))))
    # measured half width per vertex (centreline step); the stage's road_width is the fallback
    half_width = np.array(cl_feat["properties"].get("half_width_m", np.full(len(cl), road_width / 2)))
    s_cl = np.r_[0, np.cumsum(np.hypot(*np.diff(cl[:, :2], axis=0).T))]
    surface = stage.surface_at(s_cl)  # per vertex: route.surfaces over stage.surface
    tiles = build_tiles(dtm, frame, spline[:, :2], half_width, surface, z_corr, road_z=cl[:, 2], crossfall=crossfall)
    tile_index = []
    for t in tiles:
        name = f"terrain/tile_{t.ix}_{t.iy}.glb"
        write_glb(
            out / name,
            _to_gltf(t.positions),
            _to_gltf(t.normals),
            t.positions[:, :2],  # planar UVs in metres
            t.materials,
            mesh_name=f"{pid}_tile_{t.ix}_{t.iy}",
        )
        tile_index.append({"file": name, "ix": t.ix, "iy": t.iy})

    # Spline
    s = np.r_[0, np.cumsum(np.hypot(*np.diff(spline[:, :2], axis=0).T))]
    length = float(s[-1])
    splits = [round(length * k / 3 / 100) * 100 for k in (1, 2)]
    (out / "spline.json").write_text(
        json.dumps(
            {
                "points": spline.round(3).tolist(),
                "s": s.round(3).tolist(),
                "width_m": (2 * half_width).round(2).tolist(),
                "markers": {"start": 0.0, "finish": round(length, 3), "splits": splits},
            }
        ),
        encoding="utf-8",
    )

    # Images
    images.map_small(out / "images/map_small.png", spline[:, :2])
    images.elevation(out / "images/elevation.png", s, spline[:, 2])

    # Metadata
    lon, lat = Transformer.from_crs(area.crs, "EPSG:4326", always_xy=True).transform(cl[0, 0], cl[0, 1])
    z = spline[:, 2]
    meta = {
        "format": "acr-stage-package",
        "version": FORMAT_VERSION,
        "id": pid,
        "title": info.display_name,
        "location": {"country": info.country, "region": info.region},
        "origin": {"crs": area.crs, "x": ox, "y": oy, "z": 0.0},
        "start_geo": {"lat": round(lat, 7), "lon": round(lon, 7)},
        "length_m": round(length, 1),
        "elevation_m": {
            "min": round(float(z.min()), 1),
            "max": round(float(z.max()), 1),
            "start": round(float(z[0]), 1),
            "finish": round(float(z[-1]), 1),
        },
        "sectors_m": splits,
        "surfaces": [
            {"from_m": round(r["from_m"], 1), "to_m": round(r["to_m"], 1), "type": r["surface"]}
            for r in stage.surface_runs(0.0, length)
        ],
        "structures": cl_feat["properties"].get("structures", []),  # bridged spans; props may need a deck/railing
        "terrain": {"tile_size_m": TILE, "tiles": tile_index},
        "road": None,
        "images": {"map_small": "images/map_small.png", "elevation": "images/elevation.png"},
        "attribution": manifest.attributions(area),
        "producer": {"name": "acr-map-generator", "version": version("acr-map-generator")},
    }
    (out / "stage.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    n_v = sum(len(t.positions) for t in tiles)
    n_t = sum(sum(len(m) for m in t.materials.values()) for t in tiles)
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    stats = {"id": pid, "tiles": len(tiles), "vertices": n_v, "triangles": n_t, "size_mb": round(size / 1e6, 1)}
    print(f"  {len(tiles)} tiles, {n_v:,} vertices, {n_t:,} triangles, {size / 1e6:.0f} MB")
    manifest.record_derived(
        area, "package", out / "stage.json", inputs=["terrain", "centreline"], osm_derived=False, stats=stats
    )
    return out
