"""Stage IR v2 export, the input format of acr-extrastages' ACR stage builder (acr-ref stage-build).

Spec: acr-extrastages docs/stage-ir.md (MIT/Apache). The builder reads (StageBuild.Ir.Load): id, name, length_m,
total_distance_m, centreline, gates (one per centreline point: distance, crossing, left, right), timing
(type, gate, distance), optional triggers, and collision {bounds, triangles, meshes[gltf_material, acr_asset_path]}.

Frame: the IR frame is right-handed, +Y up, metres, i.e. glTF's convention. Our stage frame maps to it as
x = X (east), y = Z (up), z = Y (south). The gate `right` point lies at cross(forward, +Y), as the spec requires.

Physics ground (collision.glb) is the same road-adaptive terrain mesh as the stage package, so it carries the
planar road deck, measured width and bridge fill. It is cropped to triangles whose centroid lies within CORRIDOR m
of the exported centreline, with one primitive per surface code. A section of the stage (from_m..to_m) can be
exported on its own. It gets a run-up and a run-out on the real road beyond the start and finish.
"""

from __future__ import annotations

import json
import shutil
from importlib.metadata import version
from pathlib import Path

import numpy as np
from pyproj import Transformer
from scipy.spatial import cKDTree

from ..core import manifest
from ..core.raster import load_terrain
from ..core.stage import Stage
from . import menu_images
from .gltf import write_glb
from .pacenotes import make_pacenotes
from .pacenotes import summary as pacenote_summary
from .terrain_mesh import ZONES_LIGHT, Frame, build_tiles
from .vista import build_vista

SCHEMA, VERSION = "acrxs/stage-ir", 2
CORRIDOR = 250.0  # m, as in the DR2 exporter
GATE_STEP = 10.0  # m between gates (DR2 gates are ~10-15 m apart)
MAX_GRADE = 0.20  # audit threshold for the longitudinal grade between gates
RUN_UP, RUN_OUT = 80.0, 150.0  # m of road kept before the start and after the finish (when the road exists)
# ACR's start procedure (countdown, start trigger) needs the car to stand on a plain stretch: the start is moved
# forward to the first point where START_PLAIN m either side of the line are straight, nearly level and wide enough.
# First in-game test: a start on a 20° bend on a 4.3 m wide road never triggered the countdown.
START_PLAIN = 30.0  # m before and after the line that must be plain
START_MAX_SAG = 0.75  # m max off the straight chord across the plain stretch (60 m chord: radius > ~600 m)
START_MAX_GRADE = 0.05
START_MIN_WIDTH = 5.0  # m
START_SEARCH = 1000.0  # m searched forward from the requested start
PM = "/Game/Data/Gameplay/PhysicalMaterials/"
# Mesh material -> IR surface code -> ACR physical material. Codes and materials as in acr-extrastages
# config/surface-map.toml (the builder accepts only materials registered in DA_PhysMaterialsMappingCommon).
DEFAULT_SURFACES = {
    "road_asphalt": "TSD+",
    "road_gravel": "GD0+",
    "road_gravel_loose": "GM0+",
    "verge": "DB0+",
    "terrain": "GRS+",
}
CODE_TO_PM = {
    "TSD+": "PM_SurfaceTarmacSmooth",
    "GD0+": "PM_SurfaceGravelHard",
    "GM0+": "PM_SurfaceGravelFine",
    "DB0+": "PM_SurfaceGravelHard",
    "GRS+": "PM_SurfaceGrass",
    "ROK+": "PM_SurfaceRock",
}


def _to_ir(v: np.ndarray) -> np.ndarray:
    """Stage frame (X east, Y south, Z up) -> IR (x east, y up, z south)."""
    return v[..., [0, 2, 1]]


def export_variant(stage: Stage, variant) -> Path:
    """Export one [[export.stage_ir.variants]] entry."""
    irc = stage.config.export.stage_ir
    a, b = variant.from_m, variant.to_m
    if variant.fit_host:
        a, b = longest_fitting_section(stage)
        print(f"  {variant.name}: longest section fitting Hafren's safe region {a:.0f}-{b:.0f} m")
    return export_stage_ir(stage, a, b, irc.variant_id(variant))


def export_all(stage: Stage) -> list[Path]:
    irc = stage.config.export.stage_ir
    if irc is None:
        raise ValueError(f"{stage.name}: no [export.stage_ir] section")
    return [export_variant(stage, v) for v in irc.variants]


def export_stage_ir(
    stage: Stage, from_m: float | None = None, to_m: float | None = None, ir_id: str | None = None
) -> Path:
    area, info = stage.area, stage.config.stage
    irc = stage.config.export.stage_ir
    if irc is None:
        raise ValueError(f"{stage.name}: no [export.stage_ir] section")
    pkg = stage.config.export.package
    surfaces = {**DEFAULT_SURFACES, **irc.surfaces}

    cl_path = manifest.layer_path(area, "centreline")
    if cl_path is None:
        raise FileNotFoundError(f"needs a centreline; run: build {stage.name}")
    feat = json.loads(cl_path.read_text(encoding="utf-8"))["features"][0]
    props = feat["properties"]
    cl = np.array(feat["geometry"]["coordinates"])  # projected E, N, Z (road deck height)
    n = len(cl)
    hw = np.array(props.get("half_width_m", np.full(n, (pkg.road_width if pkg else 6.0) / 2)))
    cf = np.array(props.get("crossfall", np.zeros(n)))
    zcorr = np.array(props.get("z_correction_m", np.zeros(n)))
    s = np.r_[0, np.cumsum(np.hypot(*np.diff(cl[:, :2], axis=0).T))]

    requested = 0.0 if from_m is None else float(from_m)
    finish = float(s[-1]) if to_m is None else float(to_m)
    if not 0 <= requested < finish <= s[-1]:
        raise ValueError(f"section {requested}..{finish} m outside the stage (0..{s[-1]:.0f} m)")
    start = _plain_start(s, cl, hw, requested)
    if start != requested:
        print(f"  start moved {requested:.0f} -> {start:.0f} m (straight, level, wide run-up for the start procedure)")
    s0, s1 = max(0.0, start - RUN_UP), min(float(s[-1]), finish + RUN_OUT)

    full = from_m is None and to_m is None
    ir_id = ir_id or (irc.id if full else f"{irc.id}_{int(requested)}_{int(finish)}")
    name = info.display_name + ("" if full else f" ({start / 1000:.1f}-{finish / 1000:.1f} km)")

    # Gate distances: a regular step, plus the timing points exactly
    splits = [start + (finish - start) * k / 3 for k in (1, 2)]
    keys = [start, *splits, finish]
    d = np.arange(s0, s1, GATE_STEP)
    d = d[np.min(np.abs(d[:, None] - np.array(keys)[None, :]), axis=1) > GATE_STEP / 3]
    d = np.unique(np.r_[d, keys, s1])

    # Frame: integer origin at the bbox centre of the exported part, absolute elevation
    sec = (s >= s0) & (s <= s1)
    ox = float(np.round((cl[sec, 0].min() + cl[sec, 0].max()) / 2))
    oy = float(np.round((cl[sec, 1].min() + cl[sec, 1].max()) / 2))
    frame = Frame(ox, oy)
    X, Y = frame.to_stage(cl[:, 0], cl[:, 1])
    st = np.column_stack([X, Y, cl[:, 2]])  # stage frame, all vertices

    def at(dist: np.ndarray, a: np.ndarray) -> np.ndarray:
        return np.interp(dist, s, a)

    c3 = np.column_stack([at(d, st[:, 0]), at(d, st[:, 1]), at(d, st[:, 2])])
    fwd = np.gradient(c3[:, :2], axis=0)
    fwd /= np.linalg.norm(fwd, axis=1, keepdims=True)
    left2 = np.column_stack([fwd[:, 1], -fwd[:, 0]])  # left of travel in the stage frame (Y south)
    h, k = at(d, hw), at(d, cf)
    lp = np.column_stack([c3[:, :2] + left2 * h[:, None], c3[:, 2] + k * h])
    rp = np.column_stack([c3[:, :2] - left2 * h[:, None], c3[:, 2] - k * h])
    crossing, left, right = _to_ir(c3), _to_ir(lp), _to_ir(rp)
    f3 = _to_ir(np.column_stack([fwd, np.zeros(len(fwd))]))
    # handedness check required by the spec: right = cross(forward, +Y)
    rc = np.cross(f3, [0.0, 1.0, 0.0])
    rdir = right - crossing
    rdir /= np.linalg.norm(rdir, axis=1, keepdims=True)
    if np.median((rc * rdir).sum(axis=1)) < 0.99:
        raise AssertionError("gate right side does not match cross(forward, +Y)")

    gd = d - s0  # gate distances from the first gate

    # Pace notes from the full-resolution centreline (plan = east, north)
    pacenotes = make_pacenotes(np.column_stack([st[:, 0], -st[:, 1]]), s, start, finish, s0)
    print(f"  pace notes: {pacenote_summary(pacenotes)}")

    # Grade audit on the exported road (IR y = up): flag anything steeper than MAX_GRADE over 10 m
    zz = crossing[:, 1]
    gr = np.abs(np.diff(zz)) / np.maximum(np.diff(d), 1e-6)
    steep = [{"distance": round(float(gd[i]), 1), "grade": round(float(gr[i]), 3)} for i in np.where(gr > MAX_GRADE)[0]]
    if steep:
        print(f"  WARNING: {len(steep)} gate steps steeper than {MAX_GRADE:.0%}: {steep[:5]}")
    i0 = int(np.argmin(np.abs(d - start)))
    start_check = {
        "grade": round(
            float(
                abs(zz[min(i0 + 3, len(zz) - 1)] - zz[max(i0 - 3, 0)])
                / max(d[min(i0 + 3, len(d) - 1)] - d[max(i0 - 3, 0)], 1e-6)
            ),
            4,
        ),
        "width_m": round(float(2 * at(start, hw)), 2),
    }
    gates = [
        {
            "id": i,
            "distance": round(float(gd[i]), 3),
            "crossing": crossing[i].round(3).tolist(),
            "left": left[i].round(3).tolist(),
            "right": right[i].round(3).tolist(),
            "width": round(float(np.linalg.norm(right[i] - left[i])), 3),
        }
        for i in range(len(d))
    ]

    def gate_at(dist: float) -> int:
        return int(np.argmin(np.abs(d - dist)))

    timing = []
    for typ, dist in (("start", start), ("time", splits[0]), ("time", splits[1]), ("finish", finish)):
        g = gate_at(dist)
        timing.append(
            {
                "type": typ,
                "split_id": len(timing),
                "gate": g,
                "distance": round(float(gd[g]), 3),
                "distance_from_start": round(float(d[g] - start), 3),
                "position": crossing[g].round(3).tolist(),
                "forward": f3[g].round(5).tolist(),
                "left": left[g].round(3).tolist(),
                "right": right[g].round(3).tolist(),
            }
        )

    # Physics ground: the terrain mesh, cropped to the corridor around the exported centreline
    dtm = load_terrain(area)
    surface = stage.surface_at(s)  # per centreline vertex (mixed stages)
    tiles = build_tiles(
        dtm, frame, st[:, :2], hw, surface, zcorr, road_z=cl[:, 2], crossfall=cf, verbose=False, zones=ZONES_LIGHT
    )
    tree = cKDTree(c3[:, :2])
    verts, prims, offset = [], {}, 0
    for t in tiles:
        keep_v = np.zeros(len(t.positions), dtype=bool)
        sel = {}
        for mat, tri in t.materials.items():
            if len(tri) == 0:
                continue
            cen = t.positions[tri].mean(axis=1)
            dist, _ = tree.query(cen[:, :2], distance_upper_bound=CORRIDOR + GATE_STEP)
            tri = tri[dist <= CORRIDOR]
            sel[mat] = tri
            keep_v[tri.ravel()] = True
        if not keep_v.any():
            continue
        remap = np.full(len(t.positions), -1, dtype=np.int64)
        remap[keep_v] = np.arange(keep_v.sum()) + offset
        verts.append(t.positions[keep_v])
        offset += int(keep_v.sum())
        for mat, tri in sel.items():
            code = surfaces.get(mat)
            if code is None:
                raise KeyError(f"no surface code for mesh material {mat!r}")
            prims.setdefault(code, []).append(remap[tri])
    pos = _to_ir(np.vstack(verts))
    prims = {code: np.vstack(v) for code, v in prims.items()}
    prims = {code: v for code, v in prims.items() if len(v)}  # e.g. a gravel stretch outside this section
    tri_total = sum(len(v) for v in prims.values())
    unknown = sorted(set(prims) - set(CODE_TO_PM))
    if unknown:
        raise KeyError(f"surface codes without an ACR material: {unknown}")

    out = area.kind_dir("stage_ir") / ir_id
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    write_glb(out / "collision.glb", pos, None, None, prims, mesh_name="collision")

    # Distant scenery ring (optional: needs the terrain_vista layer)
    render = []
    if manifest.layer_path(area, "terrain_vista") is not None:
        vpts, vtri = build_vista(area, frame, st[:, :2])
        (out / "render").mkdir()
        vpos = _to_ir(vpts)
        write_glb(out / "render" / "vista.glb", vpos, None, None, {"vista": vtri}, mesh_name="vista")
        vd, _ = tree.query(vpts[:, :2])
        render.append(
            {
                "file": "render/vista.glb",
                "kind": "vista",
                "materials": None,
                "source": "acr-map-generator vista (IGN LiDAR HD 25 m + base DTM)",
                "nodes": 1,
                "corridor_m": None,
                "triangles": int(len(vtri)),
                "winding_matches_normals": None,
                "bounds": {"min": vpos.min(axis=0).round(3).tolist(), "max": vpos.max(axis=0).round(3).tolist()},
                "nearest_vertex_to_route_m": round(float(vd.min()), 2),
            }
        )
        print(f"  vista: {len(vtri):,} triangles, {np.ptp(vpts[:, 0]) / 1000:.1f} x {np.ptp(vpts[:, 1]) / 1000:.1f} km")

    # Self-checks (same intent as the DR2 exporter's validation block)
    up = []
    for v in prims.values():
        a, b, c = pos[v[:, 0]], pos[v[:, 1]], pos[v[:, 2]]
        up.append(np.cross(b - a, c - a)[:, 1] > 0)
    ccw = float(np.concatenate(up).mean())

    lon, lat = Transformer.from_crs(area.crs, "EPSG:4326", always_xy=True).transform(
        at(start, cl[:, 0]), at(start, cl[:, 1])
    )
    meshes = [
        {
            "mesh": "collision",
            "gltf_material": code,
            "dr2_surface": None,
            "acr_physical_material": CODE_TO_PM[code],
            "acr_asset_path": PM + CODE_TO_PM[code],
            "triangles": int(len(v)),
        }
        for code, v in prims.items()
    ]
    structures = [x for x in props.get("structures", []) if x["to_m"] >= s0 and x["from_m"] <= s1]
    ir = {
        "schema": SCHEMA,
        "version": VERSION,
        "id": ir_id,
        "name": name,
        "location": {
            "id": stage.name,
            "country": info.country,
            "name": f"{info.region}, {info.country}".strip(", "),
            "archive": None,
            "route_index": None,
        },
        "length_m": round(finish - start, 3),
        "total_distance_m": round(s1 - s0, 3),
        "track_type": "point_to_point",
        "direction": "forwards",
        "coordinates": {
            "frame": f"{area.crs} metres, offset by origin, absolute elevation",
            "origin": {"crs": area.crs, "easting": ox, "northing": oy},
            "axes": "x = east, y = up, z = south (right-handed, +Y up, glTF convention)",
            "start_geo": {"lat": round(lat, 7), "lon": round(lon, 7)},
        },
        "centreline": crossing.round(3).tolist(),
        "gates": gates,
        "timing": timing,
        "pacenotes": pacenotes,
        "triggers": [],
        "respawn": {
            "method": "gates",
            "notes": "use gate crossing / left / right; gates every ~10 m",
            "median_gate_spacing_m": GATE_STEP,
            "resetlines": None,
        },
        "collision": {
            "file": "collision.glb",
            "source": "acr-map-generator terrain mesh (IGN LiDAR HD)",
            "corridor_m": CORRIDOR,
            "triangles": tri_total,
            "bounds": {"min": pos.min(axis=0).round(3).tolist(), "max": pos.max(axis=0).round(3).tolist()},
            "meshes": meshes,
            "flags": None,
        },
        "surfaces": [
            {
                "code": m["gltf_material"],
                "acr_physical_material": m["acr_physical_material"],
                "triangles": m["triangles"],
                "dr2": None,
            }
            for m in meshes
        ],
        "objects": None,
        "render": render,
        "links": [x.model_dump() for x in stage.config.links],  # extension: reference pages about the real stage
        # extension: menu images copied to menu/ and where each came from ("local" ones are never released)
        "menu": menu_images.copy_to(stage, out),
        "structures": structures,  # extension: bridged spans on the road (stage metres), no deck/rail objects yet
        # extension: road surface per stretch, distances on the gates[].distance scale, codes as in collision.meshes
        "surface_segments": [
            {
                "from": round(r["from_m"] - s0, 1),
                "to": round(r["to_m"] - s0, 1),
                "surface": r["surface"],
                "code": surfaces[f"road_{r['surface']}"],
                "from_start_m": round(max(r["from_m"], start) - start, 1),
                "to_start_m": round(min(r["to_m"], finish) - start, 1),
            }
            for r in stage.surface_runs(s0, s1)
        ],
        "validation": {
            "ground_height_at_gates": {
                "checked": len(d),
                "missing": 0,
                "max_abs_dy_m": 0.0,
                "mean_abs_dy_m": 0.0,
                "note": "gates and road deck come from the same profile",
            },
            "collision_ccw_from_above": round(ccw, 4),
            "max_grade": round(float(gr.max()), 4),
            "steep_gate_steps": steep,
            "start_line": start_check,
        },
        "sources": {
            "producer": f"acr-map-generator {version('acr-map-generator')}",
            "stage": stage.name,
            "attribution": manifest.attributions(area),
            "section_m": [start, finish],
            "requested_start_m": requested,
        },
    }
    (out / "stage.json").write_text(json.dumps(ir, ensure_ascii=False), encoding="utf-8")

    yspan = float(pos[:, 1].max() - pos[:, 1].min())
    ext = _rotated_extent(np.vstack([crossing, left, right])[:, [0, 2]])
    print(
        f"  {ir_id}: {(finish - start) / 1000:.2f} km, {len(d)} gates, {tri_total:,} collision triangles "
        f"({', '.join(f'{c} {len(v):,}' for c, v in prims.items())}), ccw {ccw:.3f}"
    )
    print(
        f"  max grade between gates {gr.max():.1%}; start line grade {start_check['grade']:.1%}, width {start_check['width_m']} m"
    )
    print(f"  route extent (best rotation) {ext[0]:.0f} x {ext[1]:.0f} m, collision Y span {yspan:.0f} m")
    manifest.record_derived(
        area,
        f"stage_ir:{ir_id}",
        out / "stage.json",
        inputs=["terrain", "centreline"],
        osm_derived=False,
        stats={
            "length_m": round(finish - start, 1),
            "gates": len(d),
            "triangles": tri_total,
            "extent_m": [round(ext[0]), round(ext[1])],
            "y_span_m": round(yspan),
        },
    )
    return out


def _plain_start(s: np.ndarray, cl: np.ndarray, hw: np.ndarray, requested: float) -> float:
    """First start >= requested (and >= RUN_UP, so a run-up exists) with START_PLAIN m of plain road either side."""
    for st in np.arange(max(requested, RUN_UP), min(requested + START_SEARCH, s[-1] - START_PLAIN), 5.0):
        a, b = st - START_PLAIN, st + START_PLAIN
        k = (s >= a) & (s <= b)
        pa = np.array([np.interp(a, s, cl[:, 0]), np.interp(a, s, cl[:, 1])])
        pb = np.array([np.interp(b, s, cl[:, 0]), np.interp(b, s, cl[:, 1])])
        u = (pb - pa) / np.linalg.norm(pb - pa)
        sag = np.abs((cl[k, 0] - pa[0]) * u[1] - (cl[k, 1] - pa[1]) * u[0]).max()
        grade = abs(np.interp(b, s, cl[:, 2]) - np.interp(a, s, cl[:, 2])) / (b - a)
        if sag <= START_MAX_SAG and grade < START_MAX_GRADE and 2 * hw[k].min() >= START_MIN_WIDTH:
            return float(st)
    raise ValueError(f"no plain start within {START_SEARCH:.0f} m after {requested:.0f} m")


def _rotated_extent(xz: np.ndarray) -> tuple[float, float]:
    """Smallest-area rotated bounding box (1° steps) of 2D points, as (w, h) with w >= h."""
    best = (np.inf, 0.0, 0.0)
    c = xz - xz.mean(axis=0)
    for deg in range(180):
        r = np.radians(deg)
        rot = c @ np.array([[np.cos(r), -np.sin(r)], [np.sin(r), np.cos(r)]])
        w, h = np.ptp(rot[:, 0]), np.ptp(rot[:, 1])
        if w * h < best[0]:
            best = (w * h, max(w, h), min(w, h))
    return best[1], best[2]


# Hafren South's safe XZ region in acr-ref (StageBuild.SafeMin/Max) minus its 30 m minimum slack on each side
HOST_FIT = (802 - -1950 - 60, 2048 - -964 - 60)


def longest_fitting_section(
    stage: Stage, box: tuple[float, float] = HOST_FIT, step: float = 50.0
) -> tuple[float, float]:
    """Longest start..finish (m) whose gates incl. run-up/run-out fit box (w, h) at some rotation."""
    feat = json.loads(manifest.layer_path(stage.area, "centreline").read_text(encoding="utf-8"))["features"][0]
    cl = np.array(feat["geometry"]["coordinates"])[:, :2]
    pad = float(np.max(feat["properties"].get("half_width_m", [3.0])))
    s = np.r_[0, np.cumsum(np.hypot(*np.diff(cl, axis=0).T))]
    W, H = box[0] - 2 * pad, box[1] - 2 * pad
    rots = [np.array([[np.cos(r), -np.sin(r)], [np.sin(r), np.cos(r)]]) for r in np.radians(np.arange(180))]

    def fits(a: float, b: float) -> bool:
        k = (s >= max(0.0, a - RUN_UP)) & (s <= min(s[-1], b + RUN_OUT))
        p = cl[k] - cl[k].mean(axis=0)
        for R in rots:
            q = p @ R
            w, h = np.ptp(q[:, 0]), np.ptp(q[:, 1])
            if (w <= W and h <= H) or (w <= H and h <= W):
                return True
        return False

    marks = np.arange(0.0, s[-1] + 1e-9, step)
    best, j = (0.0, 0.0), 0
    for i, a in enumerate(marks):
        j = max(j, i)
        while j + 1 < len(marks) and fits(a, marks[j + 1]):
            j += 1
        if marks[j] - a > best[1] - best[0]:
            best = (float(a), float(marks[j]))
    return best
