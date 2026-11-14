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
- **No game files.** This tool never reads or writes game data. Anything game-side belongs in acr-extrastages.
- **Structure first.** New data goes in as a provider of a data kind. New processing goes in as a pipeline step with
  its parameters, dependencies and code files, so fingerprints stay correct.
- **Stage names:** `display_name` uses place names only, never event trademarks.

## Development

```
uv sync
uv run pytest            # tests run offline on synthetic data
uv run ruff check . && uv run ruff format .
```

For a stage contribution, run `uv run acr-map-generator validate <id>` and `build <id>`. In the pull request,
say how you checked the result, e.g. with the Blender viewer or in game.

Larger changes (new formats, schema changes, new data kinds) should start as an issue, so the design can be agreed
before the code is written.
