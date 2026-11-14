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
ACR Map Generator                 acr-extrastages (fork, branch feature/ir-stages)
build <stage> ──► stage_ir/<id>/ ──► scripts/gen-ir-spec.ps1 -Ir <IR folder> -Id <AcrId>   → stage spec (.json)
                                 ──► mods/additive/build.ps1 -Stages <spec> [-Verify]      → zz_acrxs_* paks
                                 ──► install into the game's ~mods (acr-extrastages installer)
```

The building happens on the player's PC, because it needs the player's own copy of the game. Upstream
acr-extrastages builds DiRT Rally 2.0 stages only. Our fork,
[icq4ever/acr-extrastages](https://github.com/icq4ever/acr-extrastages), adds a non-DR2 mode for IRs made by other
producers (branch `feature/ir-stages`, in progress, meant for upstream PRs):

- A stage spec with `IrDir` (a Stage IR v2 folder) is built without the DR2-only options (DR2 render ground,
  canopies, ground LOD, default sky). Specs without `IrDir` build exactly as before.
- `scripts/gen-ir-spec.ps1 -Ir <folder> -Id <AcrId>` writes that spec from the IR's `stage.json`. `-Id` is the ACR
  row/package name: letters and digits, starting with a letter (e.g. `AmgMurNoc01`).

### What the builder reads from our IR

| IR field | Used for |
|---|---|
| `name` | stage name in the menu |
| `location.name` (`"<region>, <country>"`) | location name, up to the first comma, e.g. "Corsica" |
| `location.country` (ISO 3166 code) | country and flag (DT_Countries row) |
| `surface_segments` (our extension) | menu surface: the longest one (asphalt → Tarmac, gravel → Gravel); the new location copies a vanilla location of that surface (Tarmac: Alsace, Gravel: Wales, Snow: Livigno) |
| `length_m` | menu length |
| `centreline` + elevations | menu route map, track map and elevation profile (absolute elevations) |
| `collision.glb` | baked physics and the visible ground |
| `render/vista.glb` | distant scenery (`--visuals-vista 1` when present) |
| `pacenotes.tokens` | co-driver calls **only when present**. Without them the host's calls are emptied, so the stage has none. |
| `objects` | object collision only when present |

All of it can be overridden per spec (location name and row, country, surface, logo, sky, ground offset).
A generated rally-plate logo is used unless one is given.

### Constraints

- The host level is Hafren South. Its physics world is 2.75 × 3.0 km in plan and only **229 m high**. Mountain
  stages exceed that height regardless of length, so the builder always runs with `--bounds 1` (enlarged world).
  It worked in game for the 10.6 km Muracciole section, whose world was enlarged to ~2.9 × 4.7 km × 775 m.
- Visual budget: the builder also draws the visible ground from `collision.glb`, with a 3 M triangle limit per
  stage. That is why the IR uses the lighter mesh spacing (SS8 full: 2.16 M + 0.32 M vista).
- Container names are still `zz_acrxs_*`; a configurable prefix is a candidate change.
- Known limitation: the builder lays respawn walls by reusing the host's ~830 wall pieces. That covers only part
  of a long stage's contour (12 of 33 km on the full SS8).

Verified so far with upstream commit `387a4db` (0.1.0-beta.1) through an external wrapper. The fork's IR mode replaces
that wrapper.

## Start line rule

ACR's start procedure did not trigger on a start placed in a 20° bend on a 4.3 m road. The export moves the start
forward to the first spot with 30 m of straight (≤ 0.75 m off the 60 m chord), level (< 5%), wide (≥ 5 m) road on
either side, after at least 80 m of run-up. SS8: full stage start 0 → 210 m; section start 5150 → 5370 m.
