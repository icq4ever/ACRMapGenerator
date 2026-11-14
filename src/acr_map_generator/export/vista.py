"""Distant scenery ring (Stage IR render/vista.glb): a coarse terrain mesh far around the route.

The ACR builder draws only the collision corridor near the road. Without a vista the stage floats in the sky,
seen from the service park and the intro cameras. It drops vista triangles in every 100 m cell the corridor
touches and draws the rest with the host's terrain material.

Mesh: one global grid whose spacing grows with distance from the route (ZONES), Delaunay-triangulated in one
piece, plus a vertical skirt SKIRT m deep hanging from the outer edge so its underside never shows sky.
Heights: the base DTM where it exists, the coarse terrain_vista layer beyond.
"""

from __future__ import annotations

import numpy as np
from scipy.spatial import Delaunay, cKDTree

from ..core import manifest
from ..core.raster import LayeredRaster, Raster
from .terrain_mesh import Frame

ZONES = ((750.0, 16), (3000.0, 32), (float("inf"), 64))  # (max distance from route, grid spacing m)
SKIRT = 300.0  # m
MAX_TRIANGLES = 600_000


def build_vista(area, frame: Frame, route_xy: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """route_xy: full centreline in the stage frame. Returns (positions (n, 3) stage frame, triangles (m, 3))."""
    vista_path = manifest.layer_path(area, "terrain_vista")
    base_path = manifest.layer_path(area, "terrain")
    if vista_path is None:
        raise FileNotFoundError(f"no terrain_vista layer; run: build {area.name}")
    far = Raster(vista_path)
    dem = LayeredRaster(far, [Raster(base_path)]) if base_path else far

    g = ZONES[-1][1]
    h, w = far.z.shape
    e0, e1 = far.x0 + far.res, far.x0 + w * far.dx - far.res
    n1, n0 = far.y0 - far.res, far.y0 + h * far.dy + far.res
    (x_lo, x_hi), (y_hi, y_lo) = frame.to_stage(np.array([e0, e1]), np.array([n0, n1]))
    x_lo, y_lo = np.ceil(x_lo / g) * g, np.ceil(y_lo / g) * g
    x_hi, y_hi = np.floor(x_hi / g) * g, np.floor(y_hi / g) * g

    fine = ZONES[0][1]
    gx, gy = np.meshgrid(np.arange(x_lo, x_hi + 1e-9, fine), np.arange(y_lo, y_hi + 1e-9, fine))
    gx, gy = gx.ravel(), gy.ravel()
    seg = np.hypot(*np.diff(route_xy, axis=0).T)
    s = np.r_[0, np.cumsum(seg)]
    t = np.arange(0, s[-1], 10.0)
    tree = cKDTree(np.column_stack([np.interp(t, s, route_xy[:, 0]), np.interp(t, s, route_xy[:, 1])]))
    d, _ = tree.query(np.column_stack([gx, gy]))
    sp = np.full(d.shape, ZONES[-1][1], dtype=np.int64)
    for dmax, spc in reversed(ZONES[:-1]):
        sp[d < dmax] = spc
    edge = (gx == x_lo) | (gx == x_hi) | (gy == y_lo) | (gy == y_hi)
    keep = ((np.round(gx) % sp == 0) & (np.round(gy) % sp == 0)) | (
        edge & (np.round(gx) % g == 0) & (np.round(gy) % g == 0)
    )
    px, py = gx[keep], gy[keep]
    e, n = frame.to_proj(px, py)
    pz = dem.sample(e, n)
    ok = ~np.isnan(pz)
    pts = np.column_stack([px[ok], py[ok], pz[ok]])

    tri = Delaunay(pts[:, :2], qhull_options="QJ Qbb").simplices
    # counter-clockwise from above in (E, N) = (X, -Y)
    a, b, c = pts[tri[:, 0], :2], pts[tri[:, 1], :2], pts[tri[:, 2], :2]
    cross = (b[:, 0] - a[:, 0]) * (-(c[:, 1] - a[:, 1])) - (-(b[:, 1] - a[:, 1])) * (c[:, 0] - a[:, 0])
    tri[cross < 0] = tri[cross < 0][:, [0, 2, 1]]
    tri = tri[np.abs(cross) > 1e-9]

    # Skirt: hang every outer boundary edge down by SKIRT m, facing outward
    ed = np.sort(np.vstack([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]]), axis=1)
    uniq, cnt = np.unique(ed, axis=0, return_counts=True)
    boundary = uniq[cnt == 1]
    low = np.arange(len(pts), len(pts) + len(boundary) * 2).reshape(-1, 2)
    low_pts = (
        np.vstack([pts[boundary[:, 0]], pts[boundary[:, 1]]]).reshape(2, -1, 3).transpose(1, 0, 2).reshape(-1, 3).copy()
    )
    low_pts[:, 2] -= SKIRT
    pts = np.vstack([pts, low_pts])
    sk = np.vstack(
        [
            np.column_stack([boundary[:, 0], boundary[:, 1], low[:, 1]]),
            np.column_stack([boundary[:, 0], low[:, 1], low[:, 0]]),
        ]
    )
    centre = pts[:, :2].mean(axis=0)
    # outward check in a right-handed (E, N, U) frame
    q = np.column_stack([pts[:, 0], -pts[:, 1], pts[:, 2]])
    nrm = np.cross(q[sk[:, 1]] - q[sk[:, 0]], q[sk[:, 2]] - q[sk[:, 0]])
    mid = q[sk].mean(axis=1)
    out = (mid[:, 0] - centre[0]) * nrm[:, 0] + (mid[:, 1] + centre[1]) * nrm[:, 1]
    sk[out < 0] = sk[out < 0][:, [0, 2, 1]]
    tri = np.vstack([tri, sk])
    if len(tri) > MAX_TRIANGLES:
        raise RuntimeError(f"vista has {len(tri):,} triangles (max {MAX_TRIANGLES:,}); coarsen ZONES")
    return pts, tri
