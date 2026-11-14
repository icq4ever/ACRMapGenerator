# ACR Map Generator

Builds rally stages for **Assetto Corsa Rally** from open geodata: airborne LiDAR terrain and
OpenStreetMap roads.

```
open data (LiDAR, OSM) ──► ACR Map Generator ──► Stage IR ──► acr-extrastages ──► ACR mod
                           (this repository)                  (stage builder)
```

This tool turns real roads into a drivable stage. It produces road geometry, physics ground, gates,
timing and distant scenery, written as a **Stage IR**, the intermediate format of
[acr-extrastages](https://github.com/cherrymcgerry/acr-extrastages). acr-extrastages then builds the
IR into an ACR mod. This tool uses only open data and never reads or writes game files.

> Early stage. One stage (Muracciole – Noceta, Corsica, 16.5 km) has been built and driven in game.
> Visual detail (ground textures, trees, buildings) is not done yet.

## Requirements

- [uv](https://docs.astral.sh/uv/) (installs Python 3.12 and the dependencies on first run)
- Optional: [Blender](https://www.blender.org/) to look at a stage, and acr-extrastages to build it into ACR

## Quick start

```
uv run acr-map-generator new my_stage        # stages/my_stage.toml from the template
#   fill in the TODOs: names, country, road refs, waypoints (start, junctions, finish)
uv run acr-map-generator validate my_stage   # check the file
uv run acr-map-generator build my_stage      # download data and run every step
uv run acr-map-generator status my_stage     # what is built, what is out of date
uv run acr-map-generator list                # all stages
```

`build` only reruns what changed. Editing a waypoint rebuilds the route and everything after it.
Editing a road-surface stretch rebuilds only the exports.

Look at the result in Blender, with a drive-through camera (press Space to play):

```
blender --python scripts/blender_view_package.py -- data/<stage>/package/<package id>
```

## Outputs

Everything goes to `data/<stage>/` (not versioned):

| Path | What |
|---|---|
| `stage_ir/<id>/` | **Stage IR** for acr-extrastages: `stage.json`, `collision.glb`, `render/vista.glb` |
| `package/<id>/` | Stage package: tiled terrain glb, spline, metadata, menu images (Blender viewer) |
| `centreline/centreline.geojson` | 3D road centreline measured from LiDAR, with width, crossfall, bridges |
| `terrain*/`, `roads/`, `route/` | Downloaded data and intermediate layers |
| `manifest.json` | Where every layer came from, licences, build state |

## Data sources and attribution

| Data | Source | Licence |
|---|---|---|
| Terrain (0.5–25 m) | IGN LiDAR HD (France incl. Corsica) | Etalab Licence Ouverte 2.0 |
| Roads (route finding only) | OpenStreetMap via Overpass | ODbL |

Credit the sources in anything made with this tool: **© IGN – LiDAR HD (Etalab 2.0)** and
**© OpenStreetMap contributors (ODbL)**. `manifest.json` lists the attribution for each stage.
Shipped road geometry is measured from LiDAR. OSM is used only to find the route.

## Documentation

- [docs/architecture.md](docs/architecture.md): code layout, pipeline, adding data sources, stage files, conventions
- [docs/how-it-works.md](docs/how-it-works.md): centreline, road width and profile, bridges, terrain mesh, vista
- [docs/stage-ir.md](docs/stage-ir.md): the Stage IR export and building it with acr-extrastages
- [docs/stage_package.md](docs/stage_package.md): stage package format
- [docs/data-sources.md](docs/data-sources.md): open LiDAR survey and data decisions
- [docs/roadmap.md](docs/roadmap.md): status and next steps
- [docs/licensing.md](docs/licensing.md): licences of this repo, the source data and built stages
- [CONTRIBUTING.md](CONTRIBUTING.md): how to add stages, data sources and code

## Licence

- Code and docs: MIT OR Apache-2.0, at your option ([LICENSE-MIT](LICENSE-MIT), [LICENSE-APACHE](LICENSE-APACHE)).
- Stage definitions in `stages/`: [CC BY-SA 4.0](stages/LICENSE).
- Stages built with this tool also carry their source data licences. See [docs/licensing.md](docs/licensing.md).

Copyright © 2026 studio42 Yi donghoon.
