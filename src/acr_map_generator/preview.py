"""Render a hillshade of the DTM with OSM roads on top, to eyeball data quality and alignment."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from pyproj import Transformer  # noqa: E402

from .core import manifest  # noqa: E402
from .core.area import Area  # noqa: E402

ROAD_COLORS = {
    "primary": "#d62728",
    "secondary": "#ff7f0e",
    "tertiary": "#e6c229",
    "unclassified": "#1f77b4",
    "track": "#8c564b",
}


def hillshade(z: np.ndarray, res: float, azimuth: float = 315.0, altitude: float = 45.0) -> np.ndarray:
    dy, dx = np.gradient(z, res)
    slope = np.arctan(np.hypot(dx, dy))
    aspect = np.arctan2(-dx, dy)
    az, alt = np.radians(azimuth), np.radians(altitude)
    hs = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    return np.clip(hs, 0, 1)


def render_preview(
    area: Area,
    out: Path | None = None,
    max_px: int = 4000,
    waypoints: list[tuple[float, float]] | None = None,  # WGS84 (lon, lat), drawn as numbered markers
) -> Path:
    out = out or area.data_dir / "preview.png"
    dtm_path = manifest.layer_path(area, "terrain")
    if dtm_path is None:
        raise FileNotFoundError(f"no terrain layer for {area.name!r}; run: build {area.name}")
    with rasterio.open(dtm_path) as src:
        step = max(1, int(np.ceil(max(src.width, src.height) / max_px)))
        z = src.read(1)[::step, ::step].astype(np.float64)
        nodata = src.nodata
        b = src.bounds
        res = src.res[0] * step
    mask = z == nodata
    z[mask] = np.nan
    fill = np.nanmean(z)
    hs = hillshade(np.where(mask, fill, z), res)
    hs[mask] = np.nan

    extent = (b.left, b.right, b.bottom, b.top)
    h, w = hs.shape
    fig, ax = plt.subplots(figsize=(w / 200, h / 200), dpi=200)
    ax.imshow(hs, cmap="gray", extent=extent, interpolation="bilinear")

    roads_path = manifest.layer_path(area, "roads")
    if roads_path is not None:
        for f in json.loads(roads_path.read_text(encoding="utf-8"))["features"]:
            hw = f["properties"].get("highway", "")
            color = ROAD_COLORS.get(hw.removesuffix("_link"), "#2ca02c")
            xy = np.array(f["geometry"]["coordinates"])
            ax.plot(xy[:, 0], xy[:, 1], color=color, linewidth=0.6, alpha=0.8)

    for kind, color, lw in (("route", "#1f77b4", 0.8), ("centreline", "#ff00ff", 0.8)):
        lp = manifest.layer_path(area, kind)
        if lp is not None:
            xy = np.array(json.loads(lp.read_text(encoding="utf-8"))["features"][0]["geometry"]["coordinates"])
            ax.plot(xy[:, 0], xy[:, 1], color=color, linewidth=lw, alpha=0.9)

    if waypoints:
        t = Transformer.from_crs("EPSG:4326", area.crs, always_xy=True)
        for k, (lon, lat) in enumerate(waypoints):
            x, y = t.transform(lon, lat)
            ax.plot(x, y, "o", ms=6, mfc="white", mec="black", mew=0.8)
            ax.annotate(str(k), (x, y), fontsize=4, ha="center", va="center")

    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_axis_off()
    ax.text(
        0.005,
        0.005,
        " · ".join(manifest.attributions(area)),
        transform=ax.transAxes,
        fontsize=5,
        color="black",
        ha="left",
        va="bottom",
        bbox={"facecolor": "white", "alpha": 0.7, "edgecolor": "none", "pad": 1.5},
    )
    fig.subplots_adjust(0, 0, 1, 1)
    fig.savefig(out, dpi=200)
    plt.close(fig)
    print(f"wrote {out}")
    return out
