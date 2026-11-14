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

Verified with acr-extrastages commit `387a4db` (0.1.0-beta.1), unmodified. Our fork,
[icq4ever/acr-extrastages](https://github.com/icq4ever/acr-extrastages), is at the same commit and is where
changes for non-DR2 IRs will go (offered upstream as PRs).


- `acr-ref stage-build --additive --bounds 1`, plus `--visuals-vista 1` when `render/vista.glb` exists.
- The host level is Hafren South. Its physics world is 2.75 × 3.0 km in plan and only **229 m high**. Mountain
  stages exceed that height regardless of length, so `--bounds 1` (enlarged world) is required. It worked in
  game for the 10.6 km Muracciole section, whose world was enlarged to ~2.9 × 4.7 km × 775 m.
- Visual budget: the builder also draws the visible ground from `collision.glb`, with a 3 M triangle limit per
  stage. That is why the IR uses the lighter mesh spacing (SS8 full: 2.16 M + 0.32 M vista).
- The upstream build script enables DR2-only options by default. Building a non-DR2 IR currently needs a wrapper
  that drops them. A switch for this is a candidate change for a fork / upstream PR.
- Known limitation: the builder lays respawn walls by reusing the host's ~830 wall pieces. That covers only part
  of a long stage's contour (12 of 33 km on the full SS8).

## Start line rule

ACR's start procedure did not trigger on a start placed in a 20° bend on a 4.3 m road. The export moves the start
forward to the first spot with 30 m of straight (≤ 0.75 m off the 60 m chord), level (< 5%), wide (≥ 5 m) road on
either side, after at least 80 m of run-up. SS8: full stage start 0 → 210 m; section start 5150 → 5370 m.
