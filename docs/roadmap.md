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

- **Visual detail:**
  1. Aerial imagery (IGN BD ORTHO) as ground colour. acr-extrastages has a ground-bake input.
  2. Trees from LiDAR canopy height / classified points, placed as IR objects with trunk collision.
  3. Buildings in villages from BD TOPO.
  4. 0.5 m mesh vertices near the road (ditches, rock steps).
- **Pacenotes** generated here from the centreline and written into the IR.
- **Build without wrappers:** a non-DR2 switch and IR-driven location/registration in an acr-extrastages fork
  (candidates for upstream PRs).
- **More stages:** other Corsican stages from the template. Other countries need new terrain providers
  (see [data-sources.md](data-sources.md)).
- **Full SS8 in game:** the 16.34 km version (enlarged world ~21 km²) is built but not yet driven.
- Compare our elevation profile with rally-maps.com.
- **Long term: own LiDAR capture.** Roads scanned with a vehicle-mounted LiDAR + RTK GNSS rig (see
  [data-sources.md](data-sources.md#own-capture-future-eg-korean-roads)) come in as local data providers. This
  covers places without open LiDAR and gives road-surface detail far beyond the 0.5 m DTM. See
  [architecture.md](architecture.md#local-and-own-data-planned).
- Later: release bundle per stage (IR + credits, versioned zip), GPX/KML route input, a local web UI on top of
  `pipeline.build/status`.
