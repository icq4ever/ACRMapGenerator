# Roadmap

## Done

1. **Data pipeline.** IGN LiDAR HD + OSM fetching as pluggable providers per data kind, provenance manifest,
   hillshade preview.
2. **First stage.** Tour de Corse 1998 SS8 Muracciole → Noceta via Vezzani (16.53 km, D343 → D243 → D43),
   `stages/tdc1998_ss8_muracciole_noceta.toml`.
3. **LiDAR centreline.** OSM used only as a search guide; road bed found in DTM cross-sections + Viterbi.
4. **Road profile.** Bridged structures (10 on SS8), planar deck with clamped crossfall, measured width
   (median 5.8 m), 0.5 m DTM corridor.
5. **Terrain mesh.** Road-adaptive, tiled, crack-free, seamless normals.
6. **Exports.** Stage package (Blender viewer with drive-through camera) and **Stage IR** for acr-extrastages,
   with sections/variants, plain start rule, grade audit, distant scenery ring, mixed surfaces.
7. **In game.** The 10.6 km SS8 section was built with acr-extrastages (`--bounds 1`) and driven start to finish
   (2026-11-15). Terrain collision works everywhere, including off-road slopes.
8. **Structure.** Stage template + schema v1, fingerprinted `build` pipeline, `status` / `list`.

## Next

- **Easier stage creation:**
  1. **Route import** from KML / KMZ / GPX files and from shared **Google My Maps** links (their KML export,
     `maps/d/kml?mid=...`). Organisers and fans often publish stage maps this way. A file can hold several stages
     and transit routes, so `--pick <name>` chooses one. Start/finish come from named points ("Start", "Finish")
     when present. The line is snapped to OSM roads, which fills in waypoints at road changes, the road list and
     the length. The line is only a route hint; geometry still comes from LiDAR/OSM, and the source map goes into
     `[[links]]`.
  2. **rally-maps.com paste import**: paste the stage page text to fill name, event, date, length, elevation,
     surface and related stages. rally-maps.com blocks automated access, so it is read by hand only.
  3. Helpers: a junction finder (OSM nodes where the route changes road) and a finish placed at the reference length.
  4. `release <id>`: a versioned zip per stage (Stage IR, stage file, attribution, licence, build instructions)
     as the unit for sharing and for the platform.
  5. A step-by-step guide, `docs/creating-a-stage.md`.
- **More stages from the same roads:**
  1. **Reverse variants**: the same centreline driven the other way (e.g. 2000 SS9 Noceta → Muracciole),
     as `reverse = true` on a Stage IR variant. Start rule, gates, timing and surfaces flipped accordingly.
  2. **Stage families**: stages sharing roads (Muracciole – Rospigliani 12.5 km, – Noceta 16.5 km,
     – Pont de Noceta 21 km, – Col de Sorba 48 km) cut from one road network, so the terrain is fetched once.
- **Road realism:**
  1. **Side-road stubs** at junctions: the first tens of metres of each side road as road surface, so junctions
     don't look buried in the terrain.
  2. **Track limits / respawn boundary** generated from the measured road edges and written into the IR, instead of
     relying on the host level's ~830 wall pieces (which cover only part of a long stage).
  3. **Bridge decks and railings** on the bridged `structures`.
- **Event metadata**: the real date and start time (e.g. 1998-05-05 08:43) as time-of-day / weather hints for the
  builder.
- **Stage quality report** per build (Markdown/HTML): length and elevation against the reference, width
  distribution, low-confidence stretches, bridges, grade audit, map thumbnails. Used for contribution review and,
  later, the platform's stage pages.
- **Visual detail:**
  1. Aerial imagery (IGN BD ORTHO) as ground colour. acr-extrastages has a ground-bake input.
  2. Trees from LiDAR canopy height / classified points, placed as IR objects with trunk collision.
  3. Buildings in villages from BD TOPO.
  4. 0.5 m mesh vertices near the road (ditches, rock steps).
- **Pacenotes** generated here from the centreline and written into the IR.
- **Build without wrappers:** a non-DR2 switch and IR-driven location/registration in an acr-extrastages fork
  (candidates for upstream PRs).
- **More countries** (terrain providers, see [data-sources.md](data-sources.md)), in this order: Spain / Catalunya
  (CNIG PNOA, ICGC; CC BY 4.0), Wales (DataMapWales / Environment Agency, up to 25 cm; OGL), Finland (NLS; CC BY 4.0),
  Estonia (Maa-amet). Plus a **global fallback** (Copernicus GLO-30) for places without open LiDAR, clearly marked as
  lower quality.
- **More stages:** other Corsican stages from the template. Example: Croatia Rally's organisers share Google My Maps of their stages,
  but Croatian terrain needs a provider first (check the national geodetic administration, DGU, for open LiDAR/DEM).
- **Full SS8 in game:** the 16.34 km version (enlarged world ~21 km²) is built but not yet driven.
- Compare elevation profiles with rally-maps.com automatically. Checked by hand for SS8: 543–919 m there,
  544–910 m ours.
- **Long term: own LiDAR capture.** Roads scanned with a vehicle-mounted LiDAR + RTK GNSS rig (see
  [data-sources.md](data-sources.md#own-capture-future-eg-korean-roads)) come in as local data providers. This
  covers places without open LiDAR and gives road-surface detail far beyond the 0.5 m DTM. See
  [architecture.md](architecture.md#local-and-own-data-planned).
- **Docs for newcomers:** a getting-started guide with screenshots and short clips. Korean: README.ko.md is done;
  translate user-facing docs (stage creation guide, licensing) as they settle.
- Later: a local web UI on top of `pipeline.build/status`, then the platform (shared catalogue, web detail
  editing, downloads).
