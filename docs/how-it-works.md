# How it works

The methods behind each step, with the numbers measured on the first stage
(Muracciole – Noceta, Corsica, 16.5 km). For code structure see [architecture.md](architecture.md).

## Route guide (OSM)

The stage file lists waypoints (start, each junction where the route changes road, finish) and the road
refs it follows. The route step snaps the waypoints to OSM roads and chains them with Dijkstra. Ways with a
listed ref cost their length; other ways (e.g. untagged roundabouts) cost 8 × their length. The result is
only a **search guide**. It is OSM-derived and never exported. The step also prints the OSM surface tags along
the route as a suggestion for `[[route.surfaces]]`.

## Centreline (LiDAR)

Every 2 m the DTM is cut perpendicular to the guide (±12 m, 0.5 m steps). Each candidate centre is scored by
how much a 4 m window around it looks like a road bed: level across (low cross slope) and planar (low residual).
A Viterbi pass picks the cheapest smooth sequence of offsets over the whole stage (max 1.5 m change per 2 m).

On SS8 the centreline sits on average 0.9 m from the OSM line (p95 2.5 m). The OSM line had >10% cross slope on
15% of samples, i.e. it often lay on the verge or the cut slope. The LiDAR centreline has 2.6%.

## Road width

The road deck (below) is extended sideways. On each side, the edge is the first offset where the DTM leaves it
by more than 10 cm on two consecutive samples (cut slope, ditch or drop-off). A side without an edge mirrors
the other side. The width is filtered along the road with a **25th percentile over 21 m**, then lightly smoothed,
because a road is only as wide as its narrow spots. A median filter spread narrow sections and was worse than a
fixed width. The centreline then moves to the middle of the measured road.

SS8: median 5.8 m (4.7–7.0 m). Road edges more than 20 cm off the 0.5 m DTM: 18% with a fixed 6 m, 2.9% measured.

## Road profile: planar deck

The road surface is a plane per cross-section: **centre height + crossfall × lateral offset**.
- Centre height: DTM at the centreline, bridged (below), smoothed over 3 m along the road.
- Crossfall: least-squares slope of the DTM within ±2 m of the centre, clamped to ±10%, smoothed over 8 m.

Sampling each road row from the DTM independently left 30% of 10 m sections with road vertices >25 cm off a
flat cross-section (edges on cut slopes or drop-offs). With the deck: none, apart from one 4 m-radius hairpin
where the metric does not apply. Crossfall median 2.7%, p95 7%.

## Bridges and culverts

The DTM is bare earth: bridges are removed, so the road drops into the gap below them (up to 8.8 m on SS8).
Wherever the longitudinal grade between samples exceeds 25%, nearby steep steps are merged into one structure
and the profile is replaced by a straight span. Spans are recorded as `structures` (10 on SS8), and the same
height fill is applied to the road band of the terrain mesh. Max grade after repair: 10%.

## Fine terrain corridor

The base DTM (1 m) covers the stage area. The corridor step fetches 0.5 m DTM tiles (256 m, 2 m overlap) within
60 m of the route; `load_terrain()` layers them over the base. Centreline, width and mesh heights all sample
through it. SS8: 105 tiles, 28 M cells, ~6 min to fetch, cached afterwards.

## Terrain mesh

Vertices:
- **Road band** (road + 1.5 m verge each side): 7 rows parallel to the centreline every 1 m, at offsets
  scaled by the local half width, so road edges are real mesh edges. Road rows take the deck height. Verge rows
  take the terrain height, so the verge blends from the deck edge into the terrain.
- **Elsewhere:** a global integer grid whose spacing grows with distance from the road. Package: 1 m within 40 m,
  4 m to 200 m, 16 m beyond. Stage IR (lighter, see below): 1 m to 15 m, 2 m to 60 m, 4 m to 200 m, 16 m beyond.

The grid is global and tiles are 1024 m (a multiple of every spacing), so neighbouring tiles produce identical
edge vertices and the mesh is crack-free. Normals of shared edge vertices are summed across tiles, so there are no
shading seams. Each tile is Delaunay-triangulated (joggled so every point is used). Triangles are classified by
centroid distance to the centreline: `road_<surface>` (per surface stretch), `verge`, `terrain`.

SS8 package: 56 tiles, 1.75 M vertices, 3.47 M triangles. Road |mesh − DTM| median 1.5 cm, p95 7 cm.

## Distant scenery (vista)

A 25 m DTM ~5 km around the route (one WMS request) feeds one mesh. It uses a global grid of 16 m within 750 m of
the route, 32 m to 3 km and 64 m beyond, the base DTM where it exists, one Delaunay piece, and a 300 m
outward-facing skirt on the outer edge so its underside never shows sky. SS8: 15 × 13 km, ~318 k triangles,
peaks up to 2,196 m. The builder drops it where the drawn corridor is.

## Start line

ACR's start procedure (countdown, start trigger) failed on a start placed in a 20° bend on a 4.3 m wide road.
Exports move the start forward to the first spot with 30 m of road on either side that is straight (≤ 0.75 m off
the 60 m chord), level (< 5%) and wide (≥ 5 m), with at least 80 m of run-up behind it.

## Pace notes

Corners come from the centreline, smoothed with an 8 m Gaussian first: the LiDAR line's ±0.2 m jitter otherwise reads
as extra corners. Runs with a radius under 140 m over a ±5 m window that turn at least 10° become corners. Severity
comes from sqrt(turn°) / min radius, with cut points calibrated against stock ACR calls; hairpins and squares are
detected separately. Corners less than 40 m apart are linked into one call. A straight of 40 m or more adds a
distance call, and calls are read 90 m before the corner. SS8 section: 49 calls, 97 corners (49 linked),
47 distances. The builder places each call on the built road and reports any call that disagrees with the geometry.

## Road surfaces

`[stage] surface` is the default and `[[route.surfaces]]` stretches override it (km along the centreline).
Road triangles are split into `road_asphalt` / `road_gravel` / `road_gravel_loose` per stretch, which map to IR
surface codes `TSD+` / `GD0+` / `GM0+`. The verge is `DB0+`, the terrain `GRS+`.
