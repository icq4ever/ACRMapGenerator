# Stage package format (v1, draft)

A stage package is an engine-neutral export of a stage: tiled terrain meshes with the road built in,
the driving spline and metadata, in a UE-ready frame. It is what the Blender viewer
(`scripts/blender_view_package.py`) opens, and a possible input for a direct UE import.

The route into ACR is the **Stage IR** ([stage-ir.md](stage-ir.md)), not this package. The package was the
first hand-off format, kept for previews and engine-neutral use.

Status: draft. Fields marked **(TBD)** were never confirmed against a UE import.
Bump `version` on any breaking change.

## Layout

```
<stage_id>/
  stage.json          metadata, origin, file index (required)
  spline.json         driving line + markers (required)
  terrain/
    tile_<ix>_<iy>.glb  terrain mesh tiles (required)
  road.glb            road surface mesh (optional in v1: the road may be part of the terrain tiles)
  images/
    map_small.png     top-down route map for the menu
    elevation.png     elevation profile for the menu
```

`stage_id` is `[A-Za-z0-9]+` (no separators). It becomes the UE level and table row name.
ACR level cloning (`acr_clone_level.py`) needs a name **as long as the source level's name**.
The importer pads or abbreviates. Producers do not need to care.

## Coordinate frame

All geometry is in one **stage frame**:

| Axis | Direction | Unit |
|---|---|---|
| X | East | metre |
| Y | **South** | metre |
| Z | Up | metre |

This is UE's left-handed frame (X forward, Y right, Z up) laid on the map with X = East.
The importer only multiplies by 100 (m → cm). Producers convert:

- Projected CRS (e.g. Lambert-93 E, N, H): `X = E - origin.x`, `Y = -(N - origin.y)`, `Z = H - origin.z`

**glTF files** use glTF's own convention (right-handed, Y-up, metres). They map to the stage frame as:

| glTF | Stage frame |
|---|---|
| +x | +X (East) |
| +y | +Z (Up) |
| +z | +Y (South) |

So a glTF vertex `(x, y, z)` is the stage point `(X, Y, Z) = (x, z, y)`. **(TBD)** Confirm that UE's
glTF/Interchange importer lands this as expected and record the import settings here.

Keep `|X|, |Y| < 20 km` from the origin so float32 vertex positions stay at mm precision.

## stage.json

```jsonc
{
  "format": "acr-stage-package",
  "version": 1,
  "id": "MuraccioleNoceta",
  "title": "Muracciole – Noceta",            // display name; avoid event trademarks
  "location": { "country": "FR", "region": "Corsica" },
  "origin": {                                // stage frame origin in the source CRS
    "crs": "EPSG:2154",
    "x": 1218400.0, "y": 6140700.0, "z": 0.0
  },
  "start_geo": { "lat": 42.16898, "lon": 9.18296 },   // WGS84
  "length_m": 16521.4,                        // along the spline, start → finish, 2D
  "elevation_m": { "min": 542.1, "max": 910.3, "start": 618.0, "finish": 544.2 },
  "sectors_m": [5500.0, 11000.0],             // split distances from start; sectors = splits + 1
  "surfaces": [                               // contiguous ranges covering 0..length_m
    { "from_m": 0.0, "to_m": 16521.4, "type": "asphalt" }
  ],
  "structures": [                             // bridges/culverts: road height filled over a gap below
    { "from_m": 856.0, "to_m": 872.0, "depth_m": 8.8 }
  ],
  "terrain": {
    "tile_size_m": 1000.0,
    "tiles": [ { "file": "terrain/tile_0_0.glb", "ix": 0, "iy": 0 } ]
  },
  "road": "road.glb",                         // or null
  "images": { "map_small": "images/map_small.png", "elevation": "images/elevation.png" },
  "attribution": ["© IGN – LiDAR HD (Etalab 2.0)"],
  "producer": { "name": "acr-map-generator", "version": "0.1.0" }
}
```

- `surfaces[].type`: one of `asphalt`, `gravel` (hard-packed), `gravel_loose`. They come from the stage's
  `[[route.surfaces]]` stretches, with `stage.surface` covering the rest. The road material in the terrain glbs is
  `road_<type>` per stretch. The importer maps types to ACR physical materials and `DBTrackVariant.SurfaceTypes`.
  **(TBD)** the exact ACR enum.
- `structures`: spans where the road crosses a gap (the producer already raised the road surface).
  The importer or a later prop pass may add a deck, railings or walls there. Deep spans without them
  look like a road floating over a ravine.
- Values for `DBTrackVariant` (Length, Elevation, ElevationAtStart, StartLocation, Sectors) are derived
  by the importer from `length_m`, `elevation_m`, `start_geo` and `sectors_m`. **(TBD)** units and
  `StartLocation` integer encoding as read from stock rows.

## spline.json

```jsonc
{
  "points": [[X, Y, Z], ...],     // stage frame, metres, ordered start → finish, spacing ≤ 2 m
  "s":      [0.0, 2.0, ...],      // 2D arc length per point, metres (same length as points)
  "width_m": [6.0, ...],          // optional: road width per point
  "markers": {
    "start": 0.0,                 // arc-length positions (metres)
    "finish": 16521.4,
    "splits": [5500.0, 11000.0]
  }
}
```

The spline is the driving line used for timing, the route map, and reset/recovery positions.
It is the road centre, not a racing line.

## Terrain tiles

- One glb per tile on a square grid of `tile_size_m` in the stage frame. Tile `(ix, iy)` covers
  `X ∈ [ix·T, (ix+1)·T)`, `Y ∈ [iy·T, (iy+1)·T)`. Indices may be negative.
- Triangle meshes with normals. Vertex density may vary inside a tile (dense near the road, sparse far
  away). Adjacent tiles must share edge vertices (no cracks).
- Material names carry intent: `terrain`, `road_<surface>`, `verge`. The importer assigns real materials.
- LODs: optional extra meshes named `LOD1`, `LOD2`, ... inside the same glb. **(TBD)**
- UV0: planar in metres (`u = X`, `v = Y`). The importer scales them per material.

## road.glb

Road surface as its own mesh, slightly above or conforming to the terrain, materials `road_<surface>`.
Optional in v1. If absent, the road surface is part of the terrain tiles under a `road_<surface>` material.

## Images

PNG, transparent background. **(TBD)** pixel sizes and style from stock `MapSmall` / `ElevationMap` textures.

## Producer notes (this repo)

- Never put OSM-derived geometry into a package (manifest `osm_derived: true`). Use the LiDAR
  centreline for the spline and road.
- `attribution` is copied from `data/<stage>/manifest.json`.
- v1 output: `road` is null and the road is built into the terrain tiles (`road_<surface>`, `verge`).
  Tiles are 1024 m. Normals of shared edge vertices are merged across tiles, so there are no shading seams.
