"""Road-adaptive terrain mesh, tiled, in the stage frame.

Vertices:
- Road band (|d| <= road half width + verge): rows parallel to the centreline every RIBBON_STEP m,
  at lateral offsets scaled by the local road half width, so road edges are real mesh edges.
- Elsewhere: points of a global integer grid whose spacing grows with distance from the road
  (ZONES). Since the grid is global and the spacing rule depends only on position, two tiles
  produce identical vertices on their shared edge, so the mesh is crack-free across tiles.
- Grid points lying on a tile edge are kept even inside the road band, so the edge is closed there too.

Triangles: 2D Delaunay per tile (joggled so every point is used). Material per triangle by centroid
distance to the centreline: road_<surface> / verge / terrain. The road surface can vary along the stage.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import distance_transform_edt
from scipy.spatial import Delaunay, cKDTree

from ..core.raster import Raster

TILE = 1024.0  # m; multiple of every grid spacing so tile edges fall on grid lines
# (max distance from road, grid spacing m). Spacings must divide TILE and the coarsest one.
ZONES = ((40.0, 1), (200.0, 4), (float("inf"), 16))
# Lighter variant for Stage IR: the ACR builder turns the collision ground into the visible mesh as well,
# with a 3 M triangle budget per stage. SS8 full: 3.15 M -> about 2.4 M.
ZONES_LIGHT = ((15.0, 1), (60.0, 2), (200.0, 4), (float("inf"), 16))
RIBBON_STEP = 1.0  # m between cross rows in the road band
VERGE = 1.5  # m of verge on each side of the road
ROAD_Z_SIGMA = 2.0  # m smoothing of road-band heights along the road
EDGE_CLEAR = 0.5  # m: ribbon points closer than this to a tile edge are dropped


@dataclass
class Frame:
    """Stage frame: X = E - ox, Y = -(N - oy), Z = H. ox, oy are integers so grids align."""

    ox: float
    oy: float

    def to_stage(self, e: np.ndarray, n: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        return e - self.ox, -(n - self.oy)

    def to_proj(self, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        return x + self.ox, self.oy - y


@dataclass
class Tile:
    ix: int
    iy: int
    positions: np.ndarray  # (n, 3) stage frame
    normals: np.ndarray  # (n, 3) stage frame
    materials: dict[str, np.ndarray]  # name -> (m, 3) triangle indices


def _spacing(d: np.ndarray, zones=ZONES) -> np.ndarray:
    sp = np.full(d.shape, zones[-1][1], dtype=np.int64)
    for dmax, s in reversed(zones[:-1]):
        sp[d < dmax] = s
    return sp


def _smooth_rows(z: np.ndarray, sigma: float) -> np.ndarray:
    """Gaussian smoothing along axis 0 (along the road) with edge padding, NaN-safe."""
    r = int(np.ceil(3 * sigma))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    zz = np.where(np.isnan(z), 0.0, z)
    w = (~np.isnan(z)).astype(float)
    pad = lambda a: np.pad(a, [(r, r), (0, 0)], mode="edge")  # noqa: E731
    num = np.column_stack([np.convolve(pad(zz)[:, j], k, "valid") for j in range(z.shape[1])])
    den = np.column_stack([np.convolve(pad(w)[:, j], k, "valid") for j in range(z.shape[1])])
    return np.where(den > 0, num / np.maximum(den, 1e-9), np.nan)


def build_tiles(
    dtm: Raster,
    frame: Frame,
    centre_xy: np.ndarray,
    half_width: np.ndarray | float,
    surface: str | np.ndarray,  # one surface name, or one per centreline vertex (mixed stages)
    z_corr: np.ndarray | None = None,
    road_z: np.ndarray | None = None,
    crossfall: np.ndarray | None = None,
    verbose: bool = True,
    zones=ZONES,
) -> list[Tile]:
    """centre_xy: centreline in the stage frame (X, Y). half_width: road half width per centreline
    vertex (or one value). Per-centreline-vertex road profile:

    road_z: road centre height; crossfall: rise per metre towards the left of travel. Together they
    define a planar road deck; vertices within the road width get exactly that height, which keeps
    the surface flat where the DTM edge is cut slope or drop-off. Without them the DTM is used.
    z_corr: road height minus DTM at the centre (bridge fill), added to verge vertices at the same
    distance along the road so verges follow bridges too.
    """
    # Dense centreline for distances
    seg = np.hypot(*np.diff(centre_xy, axis=0).T)
    s = np.r_[0, np.cumsum(seg)]
    t = np.arange(0, s[-1], 0.5)
    cl = np.column_stack([np.interp(t, s, centre_xy[:, 0]), np.interp(t, s, centre_xy[:, 1])])
    tree = cKDTree(cl)
    hw = np.broadcast_to(np.asarray(half_width, dtype=np.float64), (len(s),))
    half_d = np.interp(t, s, hw)  # per dense centreline sample
    band_d = half_d + VERGE
    band_max = float(band_d.max())
    surf = np.broadcast_to(np.asarray(surface, dtype=object), (len(s),))
    surf_d = surf[np.clip(np.searchsorted(s, t), 0, len(s) - 1)]  # per dense sample
    zc = np.zeros(len(s)) if z_corr is None else np.asarray(z_corr, dtype=np.float64)
    cl_corr = np.interp(t, s, zc)
    cd = np.gradient(cl, axis=0)
    cd /= np.linalg.norm(cd, axis=1, keepdims=True)
    cl_left = np.column_stack([cd[:, 1], -cd[:, 0]])  # left of travel in the stage frame (Y south)
    deck = road_z is not None
    if deck:
        cl_rz = np.interp(t, s, np.asarray(road_z, dtype=np.float64))
        cl_cf = np.interp(t, s, np.zeros(len(s)) if crossfall is None else np.asarray(crossfall, dtype=np.float64))

    def deck_height(p: np.ndarray, j: np.ndarray) -> np.ndarray:
        """Road deck height at points p (n, 2) whose nearest dense centreline index is j."""
        off_left = ((p - cl[j]) * cl_left[j]).sum(axis=1)
        return cl_rz[j] + cl_cf[j] * off_left

    def height(x: np.ndarray, y: np.ndarray) -> np.ndarray:
        e, n = frame.to_proj(x, y)
        return dtm.sample(e, n)

    # Mesh extent: DTM bounds shrunk by 1 m, snapped inward to the coarsest grid
    h, w = dtm.z.shape
    e0, e1 = dtm.x0 + dtm.res, dtm.x0 + w * dtm.dx - dtm.res
    n1, n0 = dtm.y0 - dtm.res, dtm.y0 + h * dtm.dy + dtm.res
    (x_lo, x_hi), (y_hi, y_lo) = frame.to_stage(np.array([e0, e1]), np.array([n0, n1]))
    g = zones[-1][1]
    margin = int(zones[-2][0])  # m of context around a tile for the distance field
    x_lo, y_lo = np.ceil(x_lo / g) * g, np.ceil(y_lo / g) * g
    x_hi, y_hi = np.floor(x_hi / g) * g, np.floor(y_hi / g) * g

    # Road ribbon (global), then filtered where rows from both sides of a hairpin overlap
    st = np.arange(0, s[-1] + 1e-9, RIBBON_STEP)
    rxy = np.column_stack([np.interp(st, s, centre_xy[:, 0]), np.interp(st, s, centre_xy[:, 1])])
    d = np.gradient(rxy, axis=0)
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    nrm = np.column_stack([-d[:, 1], d[:, 0]])
    h_st = np.interp(st, s, hw)[:, None]
    unit = np.array([-1.0, -1.0, -0.5, 0.0, 0.5, 1.0, 1.0])
    verge = np.array([-VERGE, 0, 0, 0, 0, 0, VERGE])
    offs = h_st * unit + verge  # (n_rows, 7): right verge, right edge, ..., left edge, left verge (right-positive)
    road_col = np.abs(unit) <= 1.0
    road_col[[0, -1]] = False
    px = rxy[:, 0:1] + nrm[:, 0:1] * offs
    py = rxy[:, 1:2] + nrm[:, 1:2] * offs
    pz = _smooth_rows(height(px, py) + np.interp(st, s, zc)[:, None], ROAD_Z_SIGMA / RIBBON_STEP)
    rib = np.column_stack([px.ravel(), py.ravel(), pz.ravel()])
    dist_rib, j_rib = tree.query(rib[:, :2])
    if deck:  # road rows (not verges) sit exactly on the planar deck
        on_road = np.tile(road_col, len(rxy))
        rib[on_road, 2] = deck_height(rib[on_road, :2], j_rib[on_road])
    ok = (np.abs(dist_rib - np.abs(offs.ravel())) < 0.25) & ~np.isnan(rib[:, 2])
    ok &= (rib[:, 0] > x_lo) & (rib[:, 0] < x_hi) & (rib[:, 1] > y_lo) & (rib[:, 1] < y_hi)
    rib = rib[ok]
    fx, fy = rib[:, 0] / TILE, rib[:, 1] / TILE
    edge_d = np.minimum(np.abs(fx - np.round(fx)), np.abs(fy - np.round(fy))) * TILE
    rib = rib[edge_d > EDGE_CLEAR]
    rib_tile = np.floor(rib[:, :2] / TILE).astype(np.int64)

    # Centreline raster for distance fields (1 m cells, global integer grid)
    cl_cells = np.unique(np.round(cl).astype(np.int64), axis=0)

    tiles: list[Tile] = []
    for iy in range(int(np.floor(y_lo / TILE)), int(np.ceil(y_hi / TILE))):
        for ix in range(int(np.floor(x_lo / TILE)), int(np.ceil(x_hi / TILE))):
            tx0, ty0 = max(ix * TILE, x_lo), max(iy * TILE, y_lo)
            tx1, ty1 = min((ix + 1) * TILE, x_hi), min((iy + 1) * TILE, y_hi)
            if tx1 <= tx0 or ty1 <= ty0:
                continue
            # distance field over the tile + margin
            ox, oy = int(tx0) - margin, int(ty0) - margin
            W, H = int(tx1 - tx0) + 2 * margin + 1, int(ty1 - ty0) + 2 * margin + 1
            mask = np.ones((H, W), dtype=bool)
            c = cl_cells - [ox, oy]
            inside = (c[:, 0] >= 0) & (c[:, 0] < W) & (c[:, 1] >= 0) & (c[:, 1] < H)
            if inside.any():
                mask[c[inside, 1], c[inside, 0]] = False
                dist = distance_transform_edt(mask)
            else:
                dist = np.full((H, W), np.inf)

            gx, gy = np.meshgrid(np.arange(int(tx0), int(tx1) + 1), np.arange(int(ty0), int(ty1) + 1))
            dd = dist[gy - oy, gx - ox]
            near_i = np.zeros(dd.shape, dtype=np.int64)
            near = dd < band_max + 2.0  # the raster distance is ±0.7 m; use exact distances near the band
            if near.any():
                dd[near], near_i[near] = tree.query(np.column_stack([gx[near], gy[near]]).astype(np.float64))
            sp = _spacing(dd, zones)
            on_edge = (gx % TILE == 0) | (gy % TILE == 0) | (gx == x_lo) | (gx == x_hi) | (gy == y_lo) | (gy == y_hi)
            band_here = np.where(near, band_d[near_i], 0.0)
            keep = (gx % sp == 0) & (gy % sp == 0) & ((dd > band_here + 0.5) | on_edge)
            # tile corners always present so the hull is the full rectangle
            keep[[0, 0, -1, -1], [0, -1, 0, -1]] = True
            gpts = np.column_stack([gx[keep], gy[keep]]).astype(np.float64)
            gz = height(gpts[:, 0], gpts[:, 1])
            in_band = dd[keep] <= band_here[keep] + 0.5  # tile-edge points inside the road band get the bridge fill too
            gz[in_band] += cl_corr[near_i[keep][in_band]]
            if deck:  # ... and those on the road get the deck height; on the verge, blend deck edge -> terrain
                dk, jk = dd[keep], near_i[keep]
                on_road = dk <= half_d[jk]
                gz[on_road] = deck_height(gpts[on_road], jk[on_road])
                vg = (dk > half_d[jk]) & (dk < band_d[jk])
                if vg.any():
                    p, j = gpts[vg], jk[vg]
                    side = np.sign(((p - cl[j]) * cl_left[j]).sum(axis=1))
                    edge_pt = cl[j] + cl_left[j] * (side * half_d[j])[:, None]
                    w_t = (dk[vg] - half_d[j]) / VERGE
                    gz[vg] = (1 - w_t) * deck_height(edge_pt, j) + w_t * gz[vg]

            r = rib[(rib_tile[:, 0] == ix) & (rib_tile[:, 1] == iy)]
            pts = np.vstack([np.column_stack([gpts, gz]), r])
            pts = pts[~np.isnan(pts[:, 2])]

            tri = Delaunay(pts[:, :2], qhull_options="QJ Qbb").simplices
            # counter-clockwise in (E, N) = (X, -Y), i.e. upward-facing
            a, b, cc = pts[tri[:, 0], :2], pts[tri[:, 1], :2], pts[tri[:, 2], :2]
            cross = (b[:, 0] - a[:, 0]) * (-(cc[:, 1] - a[:, 1])) - (-(b[:, 1] - a[:, 1])) * (cc[:, 0] - a[:, 0])
            tri[cross < 0] = tri[cross < 0][:, [0, 2, 1]]
            tri = tri[np.abs(cross) > 1e-9]

            cen = pts[tri].mean(axis=1)
            dc, jc = tree.query(cen[:, :2])
            hc = half_d[jc]
            on_road = dc < hc
            mats = {}
            for name in np.unique(surf_d[jc[on_road]]) if on_road.any() else []:
                mats[f"road_{name}"] = tri[on_road & (surf_d[jc] == name)]
            mats["verge"] = tri[(dc >= hc) & (dc < hc + VERGE)]
            mats["terrain"] = tri[dc >= hc + VERGE]
            tiles.append(Tile(ix, iy, pts, _face_normal_sums(pts, tri), mats))
            if verbose:
                n_road = sum(len(v) for k, v in mats.items() if k.startswith("road_"))
                print(f"  tile {ix:+d},{iy:+d}: {len(pts):,} verts, {len(tri):,} tris, road {n_road:,}")
    _merge_edge_normals(tiles)
    return tiles


def _merge_edge_normals(tiles: list[Tile]) -> None:
    """Sum face-normal contributions of vertices shared by several tiles, then normalise.

    Each tile only sees its own triangles, so edge vertices would get one-sided normals and show a
    shading seam. Shared vertices have identical positions, so they are matched by position.
    """
    acc: dict[tuple[float, float], np.ndarray] = {}
    edges = []
    for t in tiles:
        p = t.positions
        fx, fy = p[:, 0] / TILE, p[:, 1] / TILE
        on = (np.abs(fx - np.round(fx)) < 1e-9) | (np.abs(fy - np.round(fy)) < 1e-9)
        idx = np.where(on)[0]
        keys = [(round(float(x), 3), round(float(y), 3)) for x, y in p[idx, :2]]
        for k, i in zip(keys, idx):
            acc[k] = acc.get(k, 0) + t.normals[i]
        edges.append((idx, keys))
    for t, (idx, keys) in zip(tiles, edges):
        for k, i in zip(keys, idx):
            t.normals[i] = acc[k]
        n = t.normals
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def _face_normal_sums(p: np.ndarray, tri: np.ndarray) -> np.ndarray:
    """Area-weighted (unnormalised) vertex normal sums in the stage frame, pointing up (+Z)."""
    # work in right-handed (E, N, U) = (X, -Y, Z), then map back
    q = np.column_stack([p[:, 0], -p[:, 1], p[:, 2]])
    fn = np.cross(q[tri[:, 1]] - q[tri[:, 0]], q[tri[:, 2]] - q[tri[:, 0]])
    vn = np.zeros_like(q)
    for k in range(3):
        np.add.at(vn, tri[:, k], fn)
    vn[:, 1] *= -1  # back to stage frame (Y south)
    return vn
