# ACR Map Generator

**English** | [한국어](README.ko.md)

Builds rally stages for **Assetto Corsa Rally** from open geodata: airborne LiDAR terrain and
OpenStreetMap roads.

```
open data (LiDAR, OSM) ──► generator ──► Stage IR ──► builder ──► ACR stage mod ──► installed next to other stage mods
                           (src/)                     (builder/)
```

One repository takes a real road all the way into the game. The **generator** (`src/`, Python) produces road
geometry, physics ground, gates, timing and distant scenery from open data, written as a **Stage IR**. The
**builder** (`builder/`) builds the IR into an ACR stage mod with its own menu entry and installs it alongside other
stage mods. The builder is a fork of [ACR Extra Stages](https://github.com/cherrymcgerry/acr-extrastages) by
cherrymcgerry, included as a git subtree (see [Building into ACR](#building-into-acr)).

The generator uses only open data and never reads or writes game files. The builder runs on your PC with your own
copy of the game. No game files are part of this repository.

> Early stage. One stage (Muracciole – Noceta, Corsica, 16.5 km) has been built and driven in game.
> Visual detail (ground textures, trees, buildings) is not done yet.

This project is developed with the help of AI coding assistants. Every change is reviewed by the maintainer.

## Requirements

- [uv](https://docs.astral.sh/uv/) (installs Python 3.12 and the dependencies on first run)
- Optional: [Blender](https://www.blender.org/) to look at a stage
- To build into ACR (builder): Windows, your own copy of Assetto Corsa Rally, [.NET 10 SDK](https://dotnet.microsoft.com/),
  [PowerShell 7](https://github.com/PowerShell/PowerShell), [Rust](https://rustup.rs/) (for retoc and the mappings
  tool) and git. The builder's work folder must be on the game's drive (see below).

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

## Building into ACR

`builder/` builds a Stage IR into an ACR stage mod on your PC, using your own copy of the game. It is
[ACR Extra Stages](https://github.com/cherrymcgerry/acr-extrastages) by cherrymcgerry (MIT OR Apache-2.0),
included from our fork [icq4ever/acr-extrastages](https://github.com/icq4ever/acr-extrastages), which adds building
from a Stage IR without any DR2 data, menu registration from the IR, pace notes and installing next to other stage
mods. Its licence files and notices are in `builder/`.

One-time setup (details in [builder/docs/ir-stages.md](builder/docs/ir-stages.md#one-time-setup)): the builder reuses
the game's files through hard links, so its work folder must be **on the game's drive**. Set `ACRXS_WORK` to a folder
there, then build retoc, the mappings tool and the usmap for your game build into it.

```powershell
$env:ACR_GAME_DIR = '<ACR dir>'
$env:ACRXS_WORK   = '<folder on the game drive>'
$env:ACR_USMAP    = "$env:ACRXS_WORK\mappings\<build>.usmap"
cd builder
pwsh -File scripts\gen-ir-spec.ps1 -Ir ..\data\<stage>\stage_ir\<id> -Id <AcrId> -ContentRoot AcrMg   # spec from the IR
pwsh -File mods\additive\build.ps1 -Stages $env:ACRXS_WORK\acr\specs-ir -Prefix zz_acrmg -Verify      # build
pwsh -File scripts\install-ir-stages.ps1 -Prefix zz_acrmg                                             # install (game closed)
pwsh -File scripts\install-ir-stages.ps1 -Prefix zz_acrmg -Check                                      # still current?
```

Stages from this tool are packed as `zz_acrmg_*` under `/Game/AcrMg`. Menu name, location, country flag, surface,
length, logo and the route/elevation images come from the IR's `stage.json`. Install stacks our menu tables on top of
every other installed stage mod (e.g. Sando, Thiérache); re-run it after adding, updating or removing another stage
mod, or after a game update.

- **Offline only.** Built stages are for offline, single-player play, not online or leaderboard modes.
- **Trademarked logos stay local.** Logos with event or federation marks go in the git-ignored `local/` folder,
  never in the repository ([docs/menu-images.md](docs/menu-images.md)).

More: [builder/docs/ir-stages.md](builder/docs/ir-stages.md) (setup, spec options, build, install),
[builder/docs/other-mods.md](builder/docs/other-mods.md) (living next to other stage mods),
[builder/docs/stage-ir.md](builder/docs/stage-ir.md#irs-from-other-producers-no-dr2-data) (IR contract, "IRs from
other producers") and [docs/stage-ir.md](docs/stage-ir.md#building-with-acr-extrastages).

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
| Ground colour (20 cm) | IGN BD ORTHO aerial imagery | Etalab Licence Ouverte 2.0 |

Credit the sources in anything made with this tool: **© IGN – LiDAR HD (Etalab 2.0)**,
**© IGN – BD ORTHO (Etalab 2.0)** (when the imagery step ran) and **© OpenStreetMap contributors (ODbL)**.
`manifest.json` lists the attribution for each stage.
Shipped road geometry is measured from LiDAR. OSM is used only to find the route.

**Please credit the tool too.** Exports carry a credit line ("Made with ACR Map Generator", shown in the ACR
location info box) next to the data attribution. When you publish a stage made with this tool, please keep it, or
mention ACR Map Generator with a link to this repository in your release notes. The code licence does not require
this; it is a request.

## Documentation

- [docs/architecture.md](docs/architecture.md): code layout, pipeline, adding data sources, stage files, conventions
- [docs/how-it-works.md](docs/how-it-works.md): centreline, road width and profile, bridges, terrain mesh, vista
- [docs/stage-ir.md](docs/stage-ir.md): the Stage IR export and building it with acr-extrastages
- [docs/stage_package.md](docs/stage_package.md): stage package format
- [docs/data-sources.md](docs/data-sources.md): open LiDAR survey and data decisions
- [docs/roadmap.md](docs/roadmap.md): status and next steps
- [docs/menu-images.md](docs/menu-images.md): menu logo, tile and stage art (format, layout, rights)
- [docs/licensing.md](docs/licensing.md): licences of this repo, the source data and built stages
- [builder/docs/ir-stages.md](builder/docs/ir-stages.md), [builder/docs/other-mods.md](builder/docs/other-mods.md):
  building and installing IR stages with the builder
- [CONTRIBUTING.md](CONTRIBUTING.md): how to add stages, data sources and code
- [CHANGELOG.md](CHANGELOG.md), [SECURITY.md](SECURITY.md), [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)

## Disclaimer

- **Unofficial.** This is a fan-made tool. It is not affiliated with or endorsed by Kunos Simulazioni,
  Supernova Games, 505 Games, the FIA/WRC, or the organisers of any rally. Assetto Corsa Rally and all event
  names are trademarks of their respective owners. Stage files mention events only as factual references.
- **Not for real-world use.** Stages approximate real public roads from open data and may be inaccurate. Do not use
  them for navigation. These roads are open to traffic outside closed rally events, so respect local laws.
- **Game mods at your own risk.** Building and installing a stage uses your own copy of the game. Mods can stop
  working after game updates, and how they may be shared is governed by the game's terms. Back up before installing.
- **Offline, single-player.** Stages are meant for offline, single-player play. Stay out of online, leaderboard and
  competitive modes while modded stages are installed.
- **Be kind to data services.** IGN Géoplateforme and the Overpass API are free public services. The pipeline
  caches everything it downloads; avoid forced re-downloads and large batch runs.
- **No warranty.** The software is provided "as is" (see the licences).

## Support

Your support helps keep this project alive. Sponsorships are greatly appreciated.

- [GitHub Sponsors](https://github.com/sponsors/icq4ever)
- Kakao Pay: <br/>
<img src="assets/kakaoDonation.jpg" alt="Kakao Pay" width="300">

## Licence

- Code and docs: MIT OR Apache-2.0, at your option ([LICENSE-MIT](LICENSE-MIT), [LICENSE-APACHE](LICENSE-APACHE)).
- `builder/`: ACR Extra Stages (cherrymcgerry), MIT OR Apache-2.0, under its own licence files in `builder/`.
- Stage definitions in `stages/`: [CC BY-SA 4.0](stages/LICENSE).
- Stages built with this tool also carry their source data licences. See [docs/licensing.md](docs/licensing.md).
