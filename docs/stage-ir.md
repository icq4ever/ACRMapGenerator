# Stage IR export

The hand-off to ACR. A Stage IR is one folder per stage in the intermediate format defined by
[acr-extrastages](https://github.com/cherrymcgerry/acr-extrastages) (`docs/stage-ir.md` there, schema
`acrxs/stage-ir` version 2). acr-extrastages' builder (`acr-ref stage-build`) turns it into an ACR mod:
baked physics (ACR's car physics reads a pre-baked collision asset, not mesh collision), gameplay cell,
menu registration and pak.

```
uv run acr-map-generator build <stage>                     # includes the stage_ir step
uv run acr-map-generator stage-ir <stage>                  # every configured variant
uv run acr-map-generator stage-ir <stage> --fit-host       # one-off: longest section fitting the host level
uv run acr-map-generator stage-ir <stage> --from-m A --to-m B
```

Output: `data/<stage>/stage_ir/<id>/` with `stage.json`, `collision.glb` and `render/vista.glb`.

## What we write

The builder reads (`StageBuild.Ir.Load`): `id`, `name`, `length_m`, `total_distance_m`, `centreline` with one gate
per point, `timing` (type, gate, distance), optional `triggers`, and `collision` {bounds, triangles, meshes}.

| Field | Our source |
|---|---|
| frame | stage frame converted to x east, y up, z south (right-handed, metres, glTF convention), absolute elevation |
| `centreline`, `gates[]` | LiDAR centreline every 10 m (plus exact timing points). `left`/`right` from the measured width and crossfall; `right` = cross(forward, +Y), checked on export |
| `timing[]` | start (moved to a plain stretch, see below), two splits at thirds, finish |
| `respawn` | gate based (`method: gates`) |
| `collision.glb` | the terrain mesh (light spacing) within 250 m of the exported centreline, positions only, one primitive per surface code |
| `render/vista.glb` | distant scenery ring (when the `vista` step has run), listed in `render[]` as kind `vista` |
| `pacenotes` | `null` for now (generated on the builder side from geometry) |
| `objects`, `triggers` | `null` / empty for now |

Surface codes and ACR physical materials (codes as in acr-extrastages `config/surface-map.toml`):

| Mesh material | Code | ACR physical material |
|---|---|---|
| road_asphalt | `TSD+` | PM_SurfaceTarmacSmooth |
| road_gravel | `GD0+` | PM_SurfaceGravelHard |
| road_gravel_loose | `GM0+` | PM_SurfaceGravelFine |
| verge | `DB0+` | PM_SurfaceGravelHard |
| terrain | `GRS+` | PM_SurfaceGrass |

Override per stage in `[export.stage_ir] surfaces`. The builder rejects materials that are not registered in ACR.

Extensions (ignored by the builder, kept for the record and later use):
- `structures`: bridged spans on the road.
- `surface_segments`: road surface per stretch, on the gate-distance scale and from the start line.
- `validation`: max grade between gates, steep steps (> 20%), start-line grade and width, CCW ratio.

## Sections and variants

`[[export.stage_ir.variants]]` defines what to export: the full stage (`name = "full"`), a section
(`from_m`/`to_m`), or `fit_host = true`, the longest section whose gates fit the host level's safe region.
A section gets 80 m of run-up and 150 m of run-out on the real road.

## Building with acr-extrastages

```
generator (src/)                  builder (builder/, run from that folder)
build <stage> ──► stage_ir/<id>/ ──► scripts/gen-ir-spec.ps1 -Ir <IR folder> -Id <AcrId>      → stage spec (.json)
                                 ──► mods/additive/build.ps1 -Stages <specs> -Prefix zz_acrmg  → zz_acrmg_* paks
                                 ──► scripts/install-ir-stages.ps1 -Prefix zz_acrmg            → game's ~mods
```

The building happens on the player's PC, because it needs the player's own copy of the game. The builder in
`builder/` is ACR Extra Stages, which upstream builds DiRT Rally 2.0 stages only. Our fork
([icq4ever/acr-extrastages](https://github.com/icq4ever/acr-extrastages), included here as a git subtree) adds an IR
mode for IRs from other producers. A stage spec with `IrDir` is built without the DR2-only options, and
`scripts/gen-ir-spec.ps1` writes that spec from the IR's `stage.json`. `-Id` is the ACR row/package name: letters
and digits, starting with a letter (e.g. `AmgMurNoc01`). Stages from this producer go under `/Game/AcrMg` in
`zz_acrmg_*` containers, and install stacks their menu tables on top of other installed stage mods. Setup, options
and install: [builder/docs/ir-stages.md](../builder/docs/ir-stages.md), [builder/docs/other-mods.md](../builder/docs/other-mods.md).

Status (2026-11-15): the Muracciole–Noceta 10.6 km section builds as `AmgMurNoc01` with all offline checks passing.
The menu shows location "Corsica" (France flag, Tarmac), the IR name, 10.58 km, elevations 561–910 m and
generated route map / height profile. It is installed and drove start to finish in game with pace notes.

### The producer contract

The authoritative contract is [builder/docs/stage-ir.md](../builder/docs/stage-ir.md#irs-from-other-producers-no-dr2-data),
section **"IRs from other producers (no DR2 data)"**.
Summary for this producer:

| IR key | Used for | We write |
|---|---|---|
| `schema`, `version` | must be `acrxs/stage-ir`, ≥ 2 | yes |
| `name` | track and stage name in the menu | `display_name` (+ section range) |
| `length_m` | menu length | yes |
| `coordinates`, `y` | placement; `y` is **absolute elevation** for the menu's min / max / start elevation | yes |
| `centreline`, `gates`, `timing` | placement, splines, start / splits / finish, respawn, menu maps and height profile | yes |
| `collision` + `collision.glb`, `surfaces[]` | physics ground; material names are surface codes mapped to `PM_*` | yes |
| `location.name` | menu location: the text before the first comma ("Corsica, FR" → "Corsica") | `"<region>, <country>"` |
| `location.country` | flag (ISO 3166 alpha-2) | yes |
| `surface_segments[]` | the longest `surface` picks the menu surface and the vanilla location copied for it | yes (our extension) |
| `sources.attribution[]` | the location's info-box text ("Corsica. Built from …") | from the manifest |
| `render/vista.glb` | distant terrain ring | when the `vista` step ran |
| `pacenotes.tokens[]` | co-driver calls (format below); **without them the stage has no calls** | yes (from the centreline) |
| `objects` | object collision | not yet |

Ignored by the build (kept for our own use): `structures`, `links`, `validation`, `triggers`, `sources` beyond
`attribution`, `location.id` / `archive` / `route_index`.

### Pace notes format

`pacenotes.tokens[]`, one object per call, in driving order:

| field | meaning |
|---|---|
| `call`, `subcall` | ordering: `call` increases along the route, `subcall` orders the parts of one call (from 1) |
| `gate_distance` | where the call is read, on the **`gates[].distance` scale** (not from the start line), typically 50–150 m before the corner |
| `kind` | `corner`, `distance` or `finish` |
| `direction`, `severity` | corners: `left` / `right`; `"6"` (fastest) … `"1"`, `"square"`, `"hairpin"` |
| `distance_call_m` | distances: the spoken distance (20 / 30 become "And", 40+ become DistNN) |
| `modifiers` | optional, only `"dont_cut"` is mapped |
| `distance_m` | optional, metres from the start line (report only) |
| `corner_start_gate`, `corner_end_gate` | corners: the corner's span on the gate scale. The fork places the row there instead of searching the geometry; without them it walks the road from the read point |
| `corner_start_m`, `corner_end_m`, `angle`, `min_radius_m` | corners: the same span from the start line, and the measured turn and radius (report only) |

Without spans, the builder finds each corner by walking the built road from the read point. A corner it doesn't see
then shifts every later call by one bend (seen on SS8). With the spans, each corner row is placed exactly.

### Menu images (planned)

Optional files the builder will pick up when present (any size, cover-cropped): `menu/logo.png` (location plate,
485 × 218, transparent), `menu/tile.png` (portrait location tile, 406 × 737), `menu/art.png` (landscape ≥ 1920 × 1080,
no text near the edges; cropped to backdrop, banner and lobby thumbnail). Stages sharing a location should ship the
same logo and tile. Where they come from in this repository: [menu-images.md](menu-images.md).

### Constraints

- The host level is Hafren South. Its physics world is 2.75 × 3.0 km in plan and only **229 m high**. Mountain
  stages exceed that height regardless of length, so the builder always runs with `--bounds 1` (enlarged world).
  It worked in game for the 10.6 km Muracciole section, whose world was enlarged to ~2.9 × 4.7 km × 775 m.
- Visual budget: the builder also draws the visible ground from `collision.glb`, with a 3 M triangle limit per
  stage. That is why the IR uses the lighter mesh spacing (SS8 full: 2.16 M + 0.32 M vista).
- Known limitation: the builder lays respawn walls by reusing the host's ~830 wall pieces. That covers only part
  of a long stage's contour (12 of 33 km on the full SS8).

Verified so far with upstream commit `387a4db` (0.1.0-beta.1) through an external wrapper. The fork's IR mode replaces
that wrapper.

## Start line rule

ACR's start procedure did not trigger on a start placed in a 20° bend on a 4.3 m road. The export moves the start
forward to the first spot with 30 m of straight (≤ 0.75 m off the 60 m chord), level (< 5%), wide (≥ 5 m) road on
either side, after at least 80 m of run-up. SS8: full stage start 0 → 210 m; section start 5150 → 5370 m.
