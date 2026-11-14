# Contributing

Contributions are welcome: new stages, fixes to existing ones, new data providers for other countries,
and improvements to the pipeline.

Read [docs/architecture.md](docs/architecture.md) first. It describes the structure that changes are expected to fit.

## What goes where

| Contribution | Where | Licence |
|---|---|---|
| A new stage, or corrections to one (waypoints, road surfaces, reference notes) | `stages/<id>.toml` | CC BY-SA 4.0 |
| Open data for another country or region | a provider in `src/acr_map_generator/sources/<kind>/` | MIT OR Apache-2.0 |
| A new processing or export step | `src/acr_map_generator/`, registered in `pipeline.STEPS` | MIT OR Apache-2.0 |

By submitting a contribution you agree that it is licensed under the licence of the part you change
(inbound = outbound): code under MIT OR Apache-2.0, stage files under CC BY-SA 4.0.

## Rules

- **Open data only.** Every data source must allow commercial use of derived content. State its licence and the
  required attribution in the provider's `SourceInfo`. No scraping of services whose terms forbid it
  (Street View, Google 3D Tiles, ...).
- **Shipped geometry comes from LiDAR/DEM, not OSM.** OSM may locate the route and suggest attributes. It must not
  end up in exported geometry.
- **No game files, no generated data.** This tool never reads or writes game data. Don't commit game assets, `.pak` /
  `.ucas` / `.utoc` / `.uasset` files, `.usmap` mappings, Oodle libraries, screenshots showing game art, logs with
  personal paths, or anything from `data/` (downloaded geodata, meshes, Stage IR). `scripts/check_repo_content.py`
  enforces this for tracked files.
- **Stops at Stage IR.** Building, packaging and installing game mods is acr-extrastages' job. Don't add tooling here
  that builds, bundles or uploads game paks.
- **Offline, single-player.** Stages are meant for offline, single-player play, the same policy as acr-extrastages.
  Don't add features aimed at multiplayer, leaderboards or competitive modes, or at hiding stages from the game or
  from anti-cheat.
- **Structure first.** New data goes in as a provider of a data kind. New processing goes in as a pipeline step with
  its parameters, dependencies and code files, so fingerprints stay correct.
- **Stage names:** `display_name` uses place names only, never event trademarks.

## AI-assisted contributions

This project itself is developed with AI coding assistants, and contributions made with them are welcome, on the
same terms as any other:

- **You are responsible for what you submit.** Read and understand every change, run the tests, and check the result
  (e.g. build the stage and look at it). Unreviewed generated code or stage data will be declined.
- **Say so in the pull request** when a substantial part was generated (a new module, a large refactor, a new stage
  file). A single line is enough. No commit trailers are needed.
- **Licensing is on you.** Don't submit code or data an assistant reproduced from sources whose licence doesn't allow
  it. Everything must fit the repository's licences (MIT OR Apache-2.0 for code, CC BY-SA 4.0 for stage files).

## Development

```
uv sync
uv run pytest                                # tests run offline on synthetic data
uv run ruff check . && uv run ruff format .
uv run python scripts/check_repo_content.py  # no game data, generated data or big files
```

CI runs the same checks on every push and pull request. User-visible changes go into `CHANGELOG.md`
under `[Unreleased]`.

For a stage contribution, run `uv run acr-map-generator validate <id>` and `build <id>`. In the pull request,
say how you checked the result, e.g. with the Blender viewer or in game.

Larger changes (new formats, schema changes, new data kinds) should start as an issue, so the design can be agreed
before the code is written.
