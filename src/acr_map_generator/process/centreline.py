"""LiDAR centreline: locate the road bed in the DTM along the OSM route guide.

The guide only says roughly where to look. At every STEP metres a cross-section of the DTM is
taken perpendicular to the guide (±HALF metres). Each candidate centre offset is scored by how
much a road-wide window around it looks like a road bed: nearly level across (low cross slope)
and planar (low residual). Viterbi then picks the cheapest smooth sequence of offsets along the
whole stage. The output vertices are measured DTM positions, not OSM vertices.

Where the terrain gives no clear road bed (low confidence) the result stays close to the guide;
the share of such samples is reported so they can be reviewed.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ..core import manifest
from ..core.raster import Raster, load_terrain
from ..core.stage import Stage

STEP = 2.0  # m between cross-sections
HALF = 12.0  # m search half-width either side of the guide
D_OFF = 0.5  # m offset resolution
WINDOW = 4.0  # m road-bed window (narrower than the road so it fits inside)
GUIDE_SIGMA = 6.0  # m smoothing of the guide before taking normals
OUT_SIGMA = 3.0  # m smoothing of the final centreline
K_RMS = 5.0  # weight of window planarity residual (1/m) vs cross slope (m/m)
PRIOR = 0.15  # cost at |offset| = HALF, quadratic: keeps ambiguous spots near the guide
SMOOTH = 0.04  # transition cost per (m of offset change)^2 between consecutive sections
MAX_SHIFT = 1.5  # m max offset change between consecutive sections
LOW_CONF_SLOPE = 0.12  # best window cross slope above this = no clear road bed
# Bridges/culverts: the DTM is bare earth, so the road drops into the gap below every bridge.
MAX_GRADE = 0.25  # longitudinal grade no road here exceeds; steeper steps are structures
STRUCT_MERGE = 60.0  # m: steep steps closer than this belong to one structure
STRUCT_PAD = 2.0  # m added on both ends of a detected structure
# Road cross-section: planar deck = centre height + crossfall * lateral offset
ROAD_Z_SIGMA = 3.0  # m smoothing of the centre height along the road
CROSS_OFFS = (-2.0, -1.0, 1.0, 2.0)  # m to the left of travel (negative = right): DTM samples for the crossfall
MAX_CROSSFALL = 0.10  # camber/superelevation never exceeds this
CROSS_SIGMA = 8.0  # m smoothing of the crossfall along the road
# Road width: per side, the first lateral offset where the DTM leaves the road plane
EDGE_SEARCH = 8.0  # m searched on each side
EDGE_STEP = 0.25  # m lateral sampling
EDGE_DEV = 0.10  # m off the road deck = cut slope, ditch or drop-off
EDGE_INNER = 1.0  # m: edges are searched beyond this offset
HALF_MIN, HALF_MAX = 2.0, 4.5  # m per side (4-9 m road)
HALF_DEFAULT = 2.75  # m per side when no edge is found on either side
WIDTH_WINDOW = 21.0  # m along the road for the low-percentile filter
WIDTH_PCT = 25  # percentile: a road is only as wide as its narrow spots (a median spills over them)
WIDTH_SIGMA = 4.0  # m smoothing after the percentile filter
# Tuned on SS8 against "road edge more than 20 cm off the DTM": fixed 6 m = 22% of samples, median
# filter = 27%, this = ~2%.


def _bridge_profile(s: np.ndarray, z: np.ndarray) -> tuple[np.ndarray, list[dict]]:
    """Replace spans where the profile is steeper than MAX_GRADE by a straight line across."""
    grade = np.abs(np.diff(z) / np.maximum(np.diff(s), 1e-6))
    steep = np.where(grade > MAX_GRADE)[0]
    zf = z.copy()
    spans: list[dict] = []
    if len(steep) == 0:
        return zf, spans
    groups = np.split(steep, np.where(np.diff(s[steep]) > STRUCT_MERGE)[0] + 1)
    for g in groups:
        a = np.searchsorted(s, s[g[0]] - STRUCT_PAD, side="right") - 1
        b = np.searchsorted(s, s[g[-1] + 1] + STRUCT_PAD, side="left")
        a, b = max(a, 0), min(b, len(s) - 1)
        line = np.interp(s[a : b + 1], [s[a], s[b]], [z[a], z[b]])
        depth = float((line - z[a : b + 1]).max())
        zf[a : b + 1] = line
        spans.append({"from_m": round(float(s[a]), 1), "to_m": round(float(s[b]), 1), "depth_m": round(depth, 2)})
    return zf, spans


def _resample(xy: np.ndarray, step: float) -> np.ndarray:
    s = np.r_[0, np.cumsum(np.hypot(*np.diff(xy, axis=0).T))]
    t = np.linspace(0, s[-1], max(2, int(round(s[-1] / step)) + 1))
    return np.column_stack([np.interp(t, s, xy[:, 0]), np.interp(t, s, xy[:, 1])])


def _smooth(a: np.ndarray, sigma_samples: float) -> np.ndarray:
    """Gaussian smoothing along axis 0 with edge padding (endpoints stay put)."""
    if sigma_samples <= 0:
        return a
    r = int(np.ceil(3 * sigma_samples))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma_samples) ** 2)
    k /= k.sum()
    pad = np.pad(a, [(r, r)] + [(0, 0)] * (a.ndim - 1), mode="edge")
    if a.ndim == 1:
        return np.convolve(pad, k, mode="valid")
    return np.column_stack([np.convolve(pad[:, j], k, mode="valid") for j in range(a.shape[1])])


def _normals(xy: np.ndarray) -> np.ndarray:
    d = np.gradient(xy, axis=0)
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    return np.column_stack([-d[:, 1], d[:, 0]])  # left of travel direction


def _window_costs(z: np.ndarray, offs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per cross-section and centre offset: (cost, |cross slope|) of a WINDOW-wide linear fit."""
    n, m = z.shape
    half_w = int(round(WINDOW / 2 / D_OFF))
    cost = np.full((n, m), np.inf)
    slope = np.full((n, m), np.inf)
    u = np.arange(-half_w, half_w + 1) * D_OFF
    uu = (u**2).sum()
    for j in range(half_w, m - half_w):
        w = z[:, j - half_w : j + half_w + 1]
        mean = w.mean(axis=1, keepdims=True)
        b = ((w - mean) * u).sum(axis=1) / uu  # least-squares slope across the window
        resid = w - mean - b[:, None] * u
        rms = np.sqrt((resid**2).mean(axis=1))
        slope[:, j] = np.abs(b)
        cost[:, j] = np.abs(b) + K_RMS * rms
    cost[~np.isfinite(cost)] = np.inf  # NaN windows (nodata) are never chosen
    cost += PRIOR * (offs / HALF) ** 2
    return cost, slope


def _viterbi(cost: np.ndarray, offs: np.ndarray) -> np.ndarray:
    n, m = cost.shape
    dj = offs[None, :] - offs[:, None]
    trans = SMOOTH * dj**2
    trans[np.abs(dj) > MAX_SHIFT + 1e-9] = np.inf
    acc = cost[0].copy()
    back = np.zeros((n, m), dtype=np.int32)
    for i in range(1, n):
        tot = acc[:, None] + trans  # from (rows) -> to (cols)
        back[i] = tot.argmin(axis=0)
        acc = tot[back[i], np.arange(m)] + cost[i]
    path = np.empty(n, dtype=np.int32)
    path[-1] = int(acc.argmin())
    for i in range(n - 1, 0, -1):
        path[i - 1] = back[i, path[i]]
    return path


def _crossfall(dtm: Raster, xy: np.ndarray, structures: list[dict], s: np.ndarray) -> np.ndarray:
    """Robust crossfall (rise per metre to the left) from DTM samples inside the road, clamped and smoothed."""
    left = _normals(xy)  # left of travel in (E, N)
    offs = np.array(CROSS_OFFS)
    z = dtm.sample(xy[:, 0:1] + left[:, 0:1] * offs, xy[:, 1:2] + left[:, 1:2] * offs)
    z0 = dtm.sample(xy[:, 0], xy[:, 1])[:, None]
    cf = np.nansum((z - z0) * offs, axis=1) / (offs**2).sum()
    for st in structures:  # DTM under a bridge says nothing about the deck
        cf[(s >= st["from_m"]) & (s <= st["to_m"])] = np.nan
    bad = ~np.isfinite(cf)
    if bad.all():
        return np.zeros(len(cf))
    cf[bad] = np.interp(s[bad], s[~bad], cf[~bad])
    return _smooth(np.clip(cf, -MAX_CROSSFALL, MAX_CROSSFALL), CROSS_SIGMA / STEP)


def _road_edges(dtm: Raster, xy: np.ndarray, structures: list[dict], s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Left/right distance (m) from xy to the road edges, measured from the DTM, filtered along the road.

    The road deck (centre height + crossfall, as used for the mesh) is extended sideways. Walking
    outward, the edge is the first offset where the DTM departs from the deck by more than EDGE_DEV on
    two consecutive samples. A side without an edge (open ground) takes the other side's width.
    """
    from scipy.ndimage import percentile_filter

    left = _normals(xy)
    offs = np.arange(-EDGE_SEARCH, EDGE_SEARCH + 1e-9, EDGE_STEP)
    z = dtm.sample(xy[:, 0:1] + left[:, 0:1] * offs, xy[:, 1:2] + left[:, 1:2] * offs)
    z0 = dtm.sample(xy[:, 0], xy[:, 1])
    cf = _crossfall(dtm, xy, structures, s)
    dev = np.abs(z - (z0[:, None] + cf[:, None] * offs))
    off_road = dev > EDGE_DEV
    off_road = off_road & np.roll(off_road, -1, axis=1) | np.isnan(dev)  # two in a row (or no data)

    def first_edge(cols: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        hit = off_road[:, cols]
        found = hit.any(axis=1)
        k = hit.argmax(axis=1)
        return np.where(found, np.abs(offs[cols][k]) - EDGE_STEP / 2, np.nan), found

    wl, fl = first_edge(np.where(offs > EDGE_INNER)[0])
    wr, fr = first_edge(np.where(offs < -EDGE_INNER)[0][::-1])
    wl = np.where(fl, wl, np.where(fr, wr, HALF_DEFAULT))  # open side mirrors the other side
    wr = np.where(fr, wr, np.where(fl, wl, HALF_DEFAULT))
    for st in structures:  # the DTM under a bridge says nothing about the deck width
        k = (s >= st["from_m"]) & (s <= st["to_m"])
        wl[k] = wr[k] = np.nan
    out = []
    for w in (wl, wr):
        bad = ~np.isfinite(w)
        if bad.all():
            w = np.full_like(w, HALF_DEFAULT)
        elif bad.any():
            w[bad] = np.interp(s[bad], s[~bad], w[~bad])
        w = percentile_filter(w, WIDTH_PCT, size=int(WIDTH_WINDOW / STEP) | 1, mode="nearest")
        out.append(_smooth(np.clip(w, HALF_MIN, HALF_MAX), WIDTH_SIGMA / STEP))
    return out[0], out[1]


def extract_centreline(stage: Stage) -> Path:
    area = stage.area
    guide_path = manifest.layer_path(area, "route")
    dtm_path = manifest.layer_path(area, "terrain")
    if guide_path is None or dtm_path is None:
        raise FileNotFoundError(f"needs terrain + route; run: build {stage.name}")
    guide = np.array(json.loads(guide_path.read_text(encoding="utf-8"))["features"][0]["geometry"]["coordinates"])
    dtm = load_terrain(area)  # base DTM + fine corridor tiles when fetched

    base = _smooth(_resample(guide[:, :2], STEP), GUIDE_SIGMA / STEP)
    nrm = _normals(base)
    offs = np.arange(-HALF, HALF + 1e-9, D_OFF)
    px = base[:, 0:1] + nrm[:, 0:1] * offs[None, :]
    py = base[:, 1:2] + nrm[:, 1:2] * offs[None, :]
    z = dtm.sample(px, py)

    cost, slope = _window_costs(z, offs)
    path = _viterbi(cost, offs)
    off = offs[path]
    best_slope = slope[np.arange(len(path)), path]
    low = best_slope > LOW_CONF_SLOPE

    xy = _smooth(base + nrm * off[:, None], OUT_SIGMA / STEP)

    # Road width: measure both edges, move the centreline to the middle of the road bed
    s0 = np.r_[0, np.cumsum(np.hypot(*np.diff(xy, axis=0).T))]
    _, pre_structures = _bridge_profile(s0, dtm.sample(xy[:, 0], xy[:, 1]))
    wl, wr = _road_edges(dtm, xy, pre_structures, s0)
    shift = (wl - wr) / 2
    xy = xy + _normals(xy) * shift[:, None]
    half_width = (wl + wr) / 2
    print(
        f"  road width median {np.median(half_width) * 2:.1f} m (p5 {np.percentile(half_width, 5) * 2:.1f}, "
        f"p95 {np.percentile(half_width, 95) * 2:.1f}), centre moved mean {np.abs(shift).mean():.2f} m"
    )

    zc = dtm.sample(xy[:, 0], xy[:, 1])
    if np.isnan(zc).any():
        raise RuntimeError("centreline leaves the DTM coverage; enlarge the stage margin")

    seg = np.hypot(*np.diff(xy, axis=0).T)
    s_along = np.r_[0, np.cumsum(seg)]
    z_dtm = zc
    zc, structures = _bridge_profile(s_along, z_dtm)
    zc = _smooth(zc, ROAD_Z_SIGMA / STEP)
    crossfall = _crossfall(dtm, xy, structures, s_along)
    for st in structures:
        print(f"  structure {st['from_m']:.0f}-{st['to_m']:.0f} m: bridged {st['depth_m']:.1f} m dip")
    length = float(seg.sum())
    length_3d = float(np.sqrt(seg**2 + np.diff(zc) ** 2).sum())
    stats = {
        "length_m": round(length, 1),
        "length_3d_m": round(length_3d, 1),
        "samples": len(xy),
        "offset_mean_abs_m": round(float(np.abs(off).mean()), 2),
        "offset_p95_abs_m": round(float(np.percentile(np.abs(off), 95)), 2),
        "low_confidence_pct": round(float(low.mean() * 100), 1),
        "elevation_m": [round(float(zc.min()), 1), round(float(zc.max()), 1)],
        "start_elevation_m": round(float(zc[0]), 1),
        "finish_elevation_m": round(float(zc[-1]), 1),
        "structures": structures,  # bridged spans (bare-earth DTM dips under bridges/culverts)
        "width_m": {
            "median": round(float(np.median(half_width) * 2), 2),
            "p5": round(float(np.percentile(half_width, 5) * 2), 2),
            "p95": round(float(np.percentile(half_width, 95) * 2), 2),
        },
    }
    print(
        f"  {length / 1000:.3f} km ({length_3d / 1000:.3f} km 3D), "
        f"offset from guide mean {stats['offset_mean_abs_m']} m / p95 {stats['offset_p95_abs_m']} m, "
        f"low confidence {stats['low_confidence_pct']}%"
    )
    print(f"  elevation {zc[0]:.0f} m -> {zc[-1]:.0f} m (range {zc.min():.0f}..{zc.max():.0f} m)")
    print(
        f"  crossfall |median| {np.median(np.abs(crossfall)) * 100:.1f}%, p95 {np.percentile(np.abs(crossfall), 95) * 100:.1f}%"
    )

    out = area.kind_dir("centreline") / "centreline.geojson"
    coords = np.column_stack([xy, zc]).round(3)
    fc = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": area.crs}},
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "role": "lidar_centreline",
                    **stats,
                    # per-vertex diagnostics, same order as the coordinates
                    "offset_m": off.round(2).tolist(),
                    "z_correction_m": (zc - z_dtm).round(3).tolist(),  # road height minus DTM (bridge fill + smoothing)
                    # road surface rise per metre towards the LEFT of the driving direction:
                    # z(offset_left) = z_centre + crossfall * offset_left
                    "crossfall": crossfall.round(4).tolist(),
                    "low_confidence": low.astype(int).tolist(),
                    "half_width_m": half_width.round(2).tolist(),  # road half width (centred, symmetric)
                },
                "geometry": {"type": "LineString", "coordinates": coords.tolist()},
            }
        ],
    }
    out.write_text(json.dumps(fc), encoding="utf-8")
    manifest.record_derived(area, "centreline", out, inputs=["terrain", "route"], osm_derived=False, stats=stats)
    return out
