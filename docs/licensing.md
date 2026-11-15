# Licences and attribution

What applies to this repository and to stages built with it. This is a summary, not legal advice.

## This repository

| Part | Licence |
|---|---|
| Code (`src/`, `scripts/`, `tests/`) | MIT OR Apache-2.0, at your option ([LICENSE-MIT](../LICENSE-MIT), [LICENSE-APACHE](../LICENSE-APACHE)) |
| Stage definitions (`stages/*.toml`) | CC BY-SA 4.0 ([stages/LICENSE](../stages/LICENSE)) |
| Documentation (`docs/`, README) | MIT OR Apache-2.0, like the code |

The licence of a program does not cover what it produces. Stages built with this tool carry the obligations of
their **source data** and of the **stage definition** they were built from.

## Source data

| Source | Licence | Obligation |
|---|---|---|
| IGN LiDAR HD (terrain) | Etalab Licence Ouverte 2.0 | attribute "© IGN – LiDAR HD (Etalab 2.0)"; commercial use allowed |
| IGN BD ORTHO (ground colour) | Etalab Licence Ouverte 2.0 | attribute "© IGN – BD ORTHO (Etalab 2.0)"; commercial use allowed |
| OpenStreetMap (route finding only) | ODbL 1.0 | attribute "© OpenStreetMap contributors"; OSM-derived *data* must stay ODbL |

OSM is used only to locate the route; shipped geometry is measured from LiDAR, and layers derived from OSM are
flagged `osm_derived` in the manifest and never exported. So a built stage is a produced work that needs the OSM
attribution but does not have to be released under ODbL. `data/<stage>/manifest.json` lists the attribution per
stage.

## Crediting the tool

Exports carry a tool credit next to the data attribution: `sources.credit` / `sources.url` in the Stage IR
(appended to the ACR location info box by the builder) and `producer.credit` / `producer.url` in the package. The
code licence does not cover output, so this is a request, not an obligation: please keep the credit, or name
ACR Map Generator with a link to the repository when you publish a stage made with it.

## Stage definitions (CC BY-SA 4.0)

A stage file is a small dataset (route, surfaces, notes). If you publish a stage built from it, credit the stage
file and its contributors. If you publish a modified stage file, share it under CC BY-SA 4.0.

## Built mods

Building a Stage IR into Assetto Corsa Rally (acr-extrastages) uses assets from your own copy of the game.
Whether and how such mods may be distributed is governed by the game's terms, not by this repository.

## Names

`display_name` uses place names only. Event names such as "Tour de Corse", "WRC" or "Rallye de France" are
trademarks. Stage files may mention them as factual references (e.g. which event used a road), but not as product names.
