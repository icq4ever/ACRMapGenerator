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
- **Visual detail:**
  1. Aerial imagery (IGN BD ORTHO) as ground colour. acr-extrastages has a ground-bake input.
  2. Trees from LiDAR canopy height / classified points, placed as IR objects with trunk collision.
  3. Buildings in villages from BD TOPO.
  4. 0.5 m mesh vertices near the road (ditches, rock steps).
- **Pacenotes** generated here from the centreline and written into the IR.
- **Build without wrappers:** a non-DR2 switch and IR-driven location/registration in an acr-extrastages fork
  (candidates for upstream PRs).
- **More stages:** other Corsican stages from the template. Other countries need new terrain providers
  (see [data-sources.md](data-sources.md)). Example: Croatia Rally's organisers share Google My Maps of their stages,
  but Croatian terrain needs a provider first (check the national geodetic administration, DGU, for open LiDAR/DEM).
- **Full SS8 in game:** the 16.34 km version (enlarged world ~21 km²) is built but not yet driven.
- Compare elevation profiles with rally-maps.com automatically. Checked by hand for SS8: 543–919 m there,
  544–910 m ours.
- **Long term: own LiDAR capture.** Roads scanned with a vehicle-mounted LiDAR + RTK GNSS rig (see
  [data-sources.md](data-sources.md#own-capture-future-eg-korean-roads)) come in as local data providers. This
  covers places without open LiDAR and gives road-surface detail far beyond the 0.5 m DTM. See
  [architecture.md](architecture.md#local-and-own-data-planned).
- Later: a local web UI on top of `pipeline.build/status`, then the platform (shared catalogue, web detail
  editing, downloads).
