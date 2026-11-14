# Data sources

Survey of open data for real-world rally stages, and the decisions behind what this tool uses.
Currently implemented: IGN LiDAR HD (terrain, France) and OpenStreetMap (route finding).

## Why not Street View / Naver / Kakao Roadview

- All three providers' terms forbid bulk extraction, offline storage and derivative 3D models.
  Google Photorealistic 3D Tiles has the same restriction.
- The data is also technically weak for driving surfaces. Panoramas are about 10 m apart, all shot from the
  road centre, and absent on rural forest roads. Photogrammetry or 3DGS reconstructions smear road camber and
  surface detail.
- **Decision:** street-level imagery is a visual reference at most. Geometry comes from open LiDAR/DEM.

## Open LiDAR sources (WRC-relevant)

| Rally | Country | Source | Notes |
|---|---|---|---|
| Monte-Carlo, Tour de Corse | FR | IGN **LiDAR HD** (cartes.gouv.fr, Géoplateforme) | ~10 pts/m², classified; MNT 50 cm; Etalab 2.0. **Implemented.** |
| Finland | FI | NLS file service | 0.5–5 pts/m², CC BY 4.0 |
| Estonia | EE | Maa-amet geoportal | free |
| Sweden | SE | Lantmäteriet | check licence/coverage |
| Poland | PL | Geoportal GUGiK | nationwide point cloud |
| Latvia | LV | LĢIA | check |
| Catalunya | ES | CNIG (PNOA LiDAR), ICGC | CC BY 4.0 |
| Sardegna | IT | Sardinia regional geoportal | partial, check |
| Central Europe | CZ/AT/DE | ČÚZK DMR 5G, Austrian states, some German states | ~1 m |
| Wales | UK | DataMapWales, Environment Agency | up to 25 cm, OGL |
| Japan | JP | Shizuoka point-cloud DB, GSI 5 m DEM | regional |
| New Zealand | NZ | LINZ / OpenTopography | CC BY 4.0 |

Also: Switzerland swissSURFACE3D, Slovenia, Norway hoydedata.no, Denmark, USGS 3DEP, OpenTopography (global catalogue).
Korea is restricted: NGII LiDAR needs an application or security review, and only a 5 m DEM is generally open.

Point density matters. About 0.5 pts/m² is enough for terrain shape but not road detail. At 10 pts/m² or more,
road edges, ditches and berms are visible.

Other French sources for later detail: IGN BD ORTHO / ORTHO HR aerial imagery (20 cm), LiDAR HD canopy height
(MNH) and classified point clouds (vegetation, buildings), BD TOPO (buildings, walls). All under Etalab 2.0.
Coastal Corsica: Shom "Lidar Corsica 2017–2018" (open, attribution).

Stage routes and elevation profiles for reference: rally-maps.com. It blocks automated fetches, so read it by
hand and take geometry from LiDAR/OSM.

## Prior art

- Assetto Corsa (original): jcrr's Tour de Corse and Muracciole–Vezzani stages (method unknown).
- RBR / RallySimFans: real-world stages, including photogrammetry.
- ACR official: laser-scanned real stages.
- BeamNG: Pikes Peak LIDAR Edition; MapNG (real-world terrain generator); EarthNG.
- acr-extrastages: DiRT Rally 2.0 → ACR stage converter; its Stage IR is our output format.

## Own capture (future, e.g. Korean roads)

- **Vehicle-mounted DIY (recommended):** Livox Mid-360 (~$750, 360°, ~40 m, built-in IMU)
  + u-blox ZED-F9P RTK (~$250) with **NGII VRS NTRIP corrections (free in Korea)** + 360 camera
  + mini PC running ROS2 and FAST-LIO2 / LIO-SAM / GLIM. Roughly ₩2–3M total.
- Handheld: Mandeye (open-source, Mid-360 based), XGRIDS Lixel, FJD Trion, Leica BLK2GO (high-end).
- Phone LiDAR (iPhone Pro) has only ~5 m range, so it suits props and not roads.
- Drones: photogrammetry (DJI consumer) or Zenmuse L2 (expensive). Korean flight and aerial-photo permits are required.
- Post-processing: CloudCompare, PDAL, LAStools, Blender.
