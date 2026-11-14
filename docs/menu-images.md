# Menu images

The images a stage shows in the game's menus. The format follows what the acr-extrastages fork will read from a
Stage IR (`menu/logo.png`, `menu/tile.png`, `menu/art.png`). Status: **planned.** The builder implements them after the
first in-game test of the IR mode. Until then it uses a generated logo plate and the template location's pictures.

## What belongs to what

ACR groups stages under a **location** (e.g. "Wales", "Alsace"). A location has a logo and a tile; each stage has its
own artwork. Route map, track map and height profile are always drawn by the builder from the centreline, so they need
no files.

| Image | Belongs to | Menu use | Target size | Notes |
|---|---|---|---|---|
| **logo** | location | logo plate (main menu, track select) | 485 × 218, PNG with transparency | text and emblem only, readable small |
| **tile** | location | portrait card on the main menu | 406 × 737, PNG | key art for the area |
| **art** | stage | stage backdrop 1325 × 922, variant banner 1720 × 448, lobby thumbnail 170 × 100, all cropped from one image | at least 1920 × 1080, landscape PNG | keep the subject centred; no text or logos near the edges |

Any size is accepted. The builder cover-crops each image (centred, aspect kept) to its targets, so leave margins.
Use 8-bit RGB or RGBA PNG, under 1 MB each.

## Where the files live

```
locations/<location_id>.toml        name (menu text), country (ISO 3166 alpha-2), description
locations/<location_id>/logo.png
locations/<location_id>/tile.png
stages/<stage_id>.toml              [stage] location = "<location_id>"
stages/<stage_id>/art.png
```

`<location_id>` is `[stage] location` in the stage file, or the region as a slug ("Corsica" → `corsica`).

The Stage IR export copies them into `menu/` in each IR folder (implemented). The builder reads `menu/logo.png`
today; tile and art come later. stage.json `menu` records each file's origin. Stages that share a location ship the same logo and
tile. When a file is missing:
- **art**: ACR Map Generator renders one from the stage's terrain (a lit 3D view of the road, later with aerial
  imagery), so every stage has artwork.
- **logo / tile**: the builder's defaults (generated "RALLY <location>" plate, the template location's tile).

## Local-only images

Images you may use privately but not publish, such as an event's real rally plate with its organiser and
federation marks, go in the git-ignored `local/` folder with the same layout:

```
local/locations/<location_id>/logo.png
local/locations/<location_id>/tile.png
local/stages/<stage_id>/art.png
```

`local/` wins over the repository's files. The IR marks such images with `"origin": "local"`, so a public release
bundle leaves them out. Never move them into `locations/` or `stages/`; the content guard only accepts images that
can be shared under CC BY-SA.

## Locations and events

A location can be a region ("Corsica") or an event-style grouping ("Japan 2026"). Name it after **places and years
only**. Event names and logos such as "Rally Japan", "Tour de Corse" or "WRC" are trademarks. Don't use their names as
location names, and never their official logos or artwork. A generated plate or your own design in the event's spirit
is fine.

## Rights

Images in `locations/` and `stages/` are stage data, licensed **CC BY-SA 4.0** like the stage files. Only submit images
you may license that way:
- your own drawings, renders and photos;
- renders made with this tool from open data (credit the data: IGN, OSM; see [licensing.md](licensing.md));
- openly licensed images that allow CC BY-SA reuse, with their credit in the location/stage file.

Not allowed: game art or screenshots of game assets, official event or manufacturer logos, photos from the web without
a compatible licence.
