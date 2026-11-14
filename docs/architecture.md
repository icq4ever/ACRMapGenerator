# Architecture

How the code is organised, how a stage is built, and the rules for extending it.
For the methods themselves (centreline, width, mesh, ...) see [how-it-works.md](how-it-works.md).

## Scope

```
open data (LiDAR, OSM, ...) ──► generator (src/) ──► Stage IR ──► builder (builder/) ──► ACR stage mod
```

- **Generator (`src/`, Python):** fetching open geodata, extracting the road and its profile, building physics
  ground and scenery, writing Stage IR (and the stage package for previews). It never touches game files.
- **Builder (`builder/`, .NET / PowerShell):** everything that touches game files (cooking, baked physics, menu
  tables, paks, install). It is ACR Extra Stages (cherrymcgerry) from our fork, included as a git subtree, and
  reads only the Stage IR from the generator. Keeping the IR as the only interface means the generator only ever
  handles open data.

## Code layout

```
src/acr_map_generator/
  core/
    area.py        Area: WGS84 bbox -> projected grid
    stage.py       stage file schema (pydantic), load/validate/new
    registry.py    data kinds, Provider protocol, provider selection
    manifest.py    data/<stage>/manifest.json: layers, licences, attribution, step fingerprints
    raster.py      bilinear DTM sampling, LayeredRaster, load_terrain()
  sources/<kind>/<provider>.py   one module per data provider, self-registering
    terrain/ign_lidarhd.py       IGN LiDAR HD MNT via Géoplateforme WMS-R
    roads/overpass.py            OSM roads via Overpass
    imagery/ign_bdortho.py       IGN BD ORTHO aerial imagery (20 cm) via Géoplateforme WMS-R
  process/
    route.py       OSM route guide through the waypoints (internal only)
    corridor.py    0.5 m DTM tiles around the route
    vista.py       25 m DTM ~5 km around the route
    imagery.py     aerial imagery tiles around the route (two tiers, projected grid, cached JPEG)
    centreline.py  LiDAR road centreline, width, crossfall, bridges
  export/
    terrain_mesh.py  road-adaptive, tiled, crack-free terrain mesh
    stage_ir.py      Stage IR (stage.json, collision.glb), sections, start rule
    vista.py         distant scenery mesh
    ground_bake.py   ground colour tiles for the IR (render/ground_bake, schema ground_bake/1); dds.py BC1 writer
    package.py       stage package; images.py menu images; gltf.py minimal glb writer
  pipeline.py      ordered build steps with fingerprints (the API for the CLI and a future web UI)
  cli.py           command line
  preview.py       hillshade preview PNG
scripts/blender_view_package.py   Blender viewer (runs inside Blender)
stages/            stage definitions (+ _template.toml, CC BY-SA 4.0)
tests/             offline tests on synthetic data
builder/           IR -> ACR stage mod builder (ACR Extra Stages fork, git subtree; own docs in builder/docs/)
```

## Data kinds and providers

Data is organised by **kind** (terrain, roads, later imagery, vegetation, buildings). Each kind has
interchangeable **providers**, usually one per national open-data service.

To add a provider:
1. Create `sources/<kind>/<id>.py` with a class exposing `info` (`SourceInfo`: id, kind, title, coverage,
   licence, attribution), `covers(area)` (cheap, no network) and `fetch(area, out_dir)`.
   Terrain providers also implement `fetch_bbox(bbox, res, out)`, which the corridor and vista steps use.
2. Call `register(...)` at module level and import the module in `sources/<kind>/__init__.py`.
   The import order sets the auto-selection priority.
3. A new kind goes into `registry.KINDS` first.

A stage can pin a provider per kind in `[terrain] sources = {terrain = "..."}`; otherwise the first
registered provider that covers the area is used. `manifest.record()` stores which provider produced each
layer, with its licence and attribution. Downstream code finds layers through `manifest.layer_path()`,
never through fixed file names.

### Local and own data (planned)

Not everything will come from a public service. Own LiDAR scans (e.g. a vehicle-mounted rig) and other local
files fit the same model:
- A **local provider** reads user-supplied files instead of downloading, e.g. `sources/terrain/local_scan.py`
  that turns a LAZ point cloud into a DTM. Everything downstream (centreline, width, mesh, Stage IR) is unchanged.
- Dense mobile scans may justify a **`pointcloud` kind** (classified points, road-surface detail) next to
  `terrain`, used where present and falling back to the DTM elsewhere, like the 0.5 m corridor today.
- Stage files would point at the files through provider options (e.g. a path under `[terrain]`). That is a
  schema extension to add when the first local provider exists.
- The licence of own data is the owner's choice. The provider states it in `SourceInfo` like any other source,
  so attribution keeps working.

## Stage files

`stages/<id>.toml`, schema `acr-map-generator/stage` version 1. The models in `core/stage.py` are the single
source of truth. Start from `stages/_template.toml` (`new <id>`).

| Section | Contents |
|---|---|
| `[stage]` | title (internal), display_name (product, no event trademarks), country, region, default surface |
| `[route]` | road refs, reference length, waypoints in driving order, optional `[[route.surfaces]]` stretches |
| `[terrain]` | CRS, base resolution, margin, provider pins |
| `[reference]` | free-form notes about the real stage (e.g. `rally_maps`); never used for geometry |
| `[export.package]` | package id, fallback road width |
| `[export.stage_ir]` | IR id, surface-code overrides, `[[variants]]` (e.g. full and host-fit) |

Unknown keys and leftover `TODO` values are rejected. Bump the schema version for breaking changes.

## Pipeline

`pipeline.py` runs these steps in order:

| Step | Depends on | Output |
|---|---|---|
| terrain | – | base DTM for the stage area |
| roads | – | OSM roads for the stage area |
| route | roads | OSM route guide (`route/guide.geojson`) |
| corridor | route | 0.5 m DTM tiles within 60 m of the route |
| vista | route | 25 m DTM ~5 km around the route |
| centreline | terrain, route, corridor | LiDAR centreline with width, crossfall, bridges |
| package | terrain, corridor, centreline | stage package |
| stage_ir | terrain, corridor, vista, centreline | Stage IR, one folder per variant |

Each step's **fingerprint** hashes its parameters (stage-file sections and module constants), the fingerprints
of its dependencies, and, for processing steps, the source of the modules that compute it. A step is skipped
when its fingerprint and outputs are unchanged. Download steps leave the code out, so code edits never trigger
re-downloads. Fingerprints live in `manifest.json` under `steps`.

API: `pipeline.build(stage_id, targets=None, force=False, on_event=callback)`, `pipeline.status(stage_id)`.
Results are plain dicts and progress is reported through `on_event`, so a web front end can call the same functions.

A new processing step goes into `pipeline.STEPS` with its params, deps and code files, otherwise fingerprints go stale.

## Conventions

- **Shipped geometry comes from LiDAR, not OSM.** OSM-derived layers are flagged `osm_derived: true` in the
  manifest (e.g. `route`) and must not end up in exports. OSM attributes (e.g. surface tags) are suggestions only.
- **Structure first.** New open data goes in as a provider of a data kind, never as a one-off fetch script.
- **Licences.** Code is MIT OR Apache-2.0, stage files CC BY-SA 4.0 ([licensing.md](licensing.md)).
  Every provider must allow commercial use of derived content and states its terms in `SourceInfo`.
  IGN: Etalab 2.0 (attribute IGN). OSM: ODbL (attribute OpenStreetMap contributors).
- **Privacy.** HTTP clients send a generic `User-Agent: acr-map-generator/0.1`. No personal data in requests.
- **Units and frames.** Metres throughout. Working CRS for France/Corsica: EPSG:2154 (Lambert-93).
  Stage frame: X east, Y south, Z up (UE's left-handed frame). Stage IR / glTF: x east, y up, z south.
- **Python** via `uv` (3.12). On Windows the system `python` is the Store stub, so don't use it.
- **Git.** No AI attribution trailers (`Co-Authored-By`) in commits or PR descriptions.
- **`builder/` is a subtree.** Never mix `builder/` changes and other changes in one commit, so builder fixes can be
  split out (`git subtree split --prefix=builder`) and sent upstream as PRs from the fork
  [icq4ever/acr-extrastages](https://github.com/icq4ever/acr-extrastages). Merge PRs that touch `builder/` with a
  merge commit (no squash or rebase). Upstream changes:
  `git subtree pull --prefix=builder https://github.com/cherrymcgerry/acr-extrastages main`.
