"""Route guide: chain OSM road ways through the stage waypoints.

The result follows OSM geometry, so it is OSM-derived (ODbL) and used internally only, as the
search guide for the LiDAR centreline. Ways whose `ref` is listed in the stage's `roads` are
preferred. Other ways (e.g. untagged roundabouts) cost OFF_ROUTE_PENALTY times their length.
"""

from __future__ import annotations

import heapq
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from pyproj import Transformer

from ..core import manifest
from ..core.stage import Stage

OFF_ROUTE_PENALTY = 8.0
SNAP_WARN_M = 50.0  # warn if a waypoint is further than this from the preferred roads

Node = tuple[float, float]


def _norm_ref(ref: str) -> set[str]:
    return {r.replace(" ", "").upper() for r in ref.split(";") if r.strip()}


def _key(x: float, y: float) -> Node:
    return (round(x, 3), round(y, 3))


def _build_graph(features: list[dict], roads: set[str]):
    adj: dict[Node, list[tuple[Node, float, float]]] = defaultdict(list)  # node -> (nbr, cost, length)
    preferred: set[Node] = set()
    edge_surface: dict[tuple[Node, Node], str] = {}  # OSM surface tag per edge (for suggestions only)
    for f in features:
        on_route = bool(_norm_ref(f["properties"].get("ref", "")) & roads)
        pen = 1.0 if on_route else OFF_ROUTE_PENALTY
        pts = [_key(*c[:2]) for c in f["geometry"]["coordinates"]]
        for a, b in zip(pts, pts[1:]):
            if a == b:
                continue
            d = float(np.hypot(b[0] - a[0], b[1] - a[1]))
            # Stages run on closed roads, so oneway tags are ignored.
            adj[a].append((b, d * pen, d))
            adj[b].append((a, d * pen, d))
            tag = f["properties"].get("surface") or "untagged"
            edge_surface[(a, b)] = edge_surface[(b, a)] = tag
        if on_route:
            preferred.update(pts)
    return adj, preferred, edge_surface


def _dijkstra(adj, src: Node, dst: Node) -> list[Node]:
    dist = {src: 0.0}
    prev: dict[Node, Node] = {}
    pq = [(0.0, src)]
    while pq:
        d, u = heapq.heappop(pq)
        if u == dst:
            break
        if d > dist[u]:
            continue
        for v, c, _ in adj[u]:
            nd = d + c
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    if dst not in dist:
        raise RuntimeError("waypoints are not connected in the road graph")
    path = [dst]
    while path[-1] != src:
        path.append(prev[path[-1]])
    return path[::-1]


def build_route(stage: Stage) -> Path:
    area = stage.area
    roads_path = manifest.layer_path(area, "roads")
    if roads_path is None:
        raise FileNotFoundError(f"no roads layer; run: build {stage.name}")
    features = json.loads(roads_path.read_text(encoding="utf-8"))["features"]
    roads = set().union(*(_norm_ref(r) for r in stage.roads)) if stage.roads else set()

    adj, preferred, edge_surface = _build_graph(features, roads)
    candidates = np.array(sorted(preferred or adj.keys()))
    t = Transformer.from_crs("EPSG:4326", area.crs, always_xy=True)

    snapped: list[Node] = []
    snaps = []
    for w in stage.waypoints:
        x, y = t.transform(w.lon, w.lat)
        d = np.hypot(candidates[:, 0] - x, candidates[:, 1] - y)
        i = int(d.argmin())
        snapped.append((float(candidates[i, 0]), float(candidates[i, 1])))
        snaps.append({"waypoint": w.name, "snap_m": round(float(d[i]), 1)})
        flag = "  <-- check waypoint" if d[i] > SNAP_WARN_M else ""
        print(f"  snap {w.name}: {d[i]:.1f} m{flag}")

    path: list[Node] = [snapped[0]]
    for a, b in zip(snapped, snapped[1:]):
        path += _dijkstra(adj, a, b)[1:]

    xy = np.array(path)
    length = float(np.hypot(*np.diff(xy, axis=0).T).sum())
    stats = {"length_m": round(length, 1), "snaps": snaps}

    # OSM surface tags along the route: a suggestion for [[route.surfaces]] only (OSM-derived, never exported)
    runs, pos = [], 0.0
    for a, b in zip(path, path[1:]):
        seg = float(np.hypot(b[0] - a[0], b[1] - a[1]))
        tag = edge_surface.get((a, b), "untagged")
        if runs and runs[-1]["osm_surface"] == tag:
            runs[-1]["to_km"] = round((pos + seg) / 1000, 2)
        else:
            runs.append({"from_km": round(pos / 1000, 2), "to_km": round((pos + seg) / 1000, 2), "osm_surface": tag})
        pos += seg
    stats["osm_surface_runs"] = runs
    print(
        "  OSM surface tags (suggestion for [[route.surfaces]]): "
        + ", ".join(f"{r['osm_surface']} {r['from_km']}-{r['to_km']} km" for r in runs)
    )
    if stage.length_km:
        ref = stage.length_km * 1000
        stats["reference_length_m"] = ref
        stats["length_diff_pct"] = round((length - ref) / ref * 100, 2)
        print(f"  length {length / 1000:.3f} km (reference {stage.length_km} km, {stats['length_diff_pct']:+.2f}%)")
    else:
        print(f"  length {length / 1000:.3f} km")

    out = area.kind_dir("route") / "guide.geojson"
    fc = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": area.crs}},
        "features": [
            {
                "type": "Feature",
                "properties": {"role": "osm_guide", **stats},
                "geometry": {"type": "LineString", "coordinates": xy.tolist()},
            }
        ],
    }
    out.write_text(json.dumps(fc), encoding="utf-8")
    manifest.record_derived(area, "route", out, inputs=["roads"], osm_derived=True, stats=stats)
    return out
