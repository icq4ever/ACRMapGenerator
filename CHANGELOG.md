# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). The version is in `pyproject.toml`.

## [Unreleased]

### Added

- Pace notes in the Stage IR (`pacenotes.tokens`), generated from the smoothed LiDAR centreline.
- Docs: menu image format and layout (`docs/menu-images.md`), the acr-extrastages producer contract.
- Tool credit in every export (`sources.credit` / `sources.url` in the Stage IR, `producer.credit` / `producer.url`
  in the package), shown in the ACR location info box; README asks users to keep it.
- Docs: IGN BD ORTHO attribution in the README and `docs/licensing.md`.

## [0.1.0] - Unreleased

First public version. Builds drivable stages for *Assetto Corsa Rally* from open geodata and writes them as
Stage IR for [acr-extrastages](https://github.com/cherrymcgerry/acr-extrastages).

### Added

- Stage files (`stages/<id>.toml`, schema v1) with a template, validation and `new` / `validate` commands.
- A fingerprinted build pipeline (`build`, `status`, `list`): terrain, roads, route, 0.5 m corridor, vista,
  centreline, package, Stage IR. Only steps whose inputs, parameters or code changed are rebuilt.
- Data providers: IGN LiDAR HD terrain (France incl. Corsica) and OpenStreetMap roads (route finding only).
- LiDAR road centreline with measured road width, planar road deck (clamped crossfall) and bridge repair.
- Road-adaptive, crack-free tiled terrain mesh; distant scenery ring.
- Stage IR export: gates with road edges, timing, collision ground by surface code, full stage and sections,
  a plain start line rule, grade audit, mixed tarmac/gravel stretches.
- Stage package and a Blender viewer with a drive-through camera.
- First stage: Muracciole – Noceta (Corsica, 16.5 km). Its 10.6 km section was driven in game via acr-extrastages.
