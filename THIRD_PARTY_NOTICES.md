# Third-party notices

ACR Map Generator is licensed under MIT OR Apache-2.0 (see [LICENSE-MIT](LICENSE-MIT) and
[LICENSE-APACHE](LICENSE-APACHE)). This file lists the software it uses and the data it downloads.
Licences were read from the installed packages' metadata for the versions pinned in `uv.lock`, not
from memory.

**This repository contains no game files** (no assets, archives or mappings from *Assetto Corsa Rally* or any
other game) and no downloaded geodata. Data is fetched at run time into the git-ignored `data/` folder. The only
game imagery is three menu screenshots in `builder/docs/media/`, part of the upstream builder documentation.

## Bundled source: `builder/`

`builder/` is **ACR Extra Stages** by cherrymcgerry ([cherrymcgerry/acr-extrastages](https://github.com/cherrymcgerry/acr-extrastages)),
MIT OR Apache-2.0, included as a git subtree from the fork
[icq4ever/acr-extrastages](https://github.com/icq4ever/acr-extrastages) (branch `feature/ir-stages`, which adds
building from a Stage IR). Its own licence files ([builder/LICENSE-MIT](builder/LICENSE-MIT),
[builder/LICENSE-APACHE](builder/LICENSE-APACHE)) and third-party notices
([builder/THIRD_PARTY_NOTICES.md](builder/THIRD_PARTY_NOTICES.md)) apply to everything under `builder/`.

## Python packages (run time)

Installed by `uv` from PyPI; none of their code is copied into this repository.

| Package | Version | Licence | Used for |
|---|---|---|---|
| [NumPy](https://numpy.org) | 2.5.4 | BSD-3-Clause (bundled parts: 0BSD, MIT, Zlib, CC0-1.0) | arrays throughout |
| [SciPy](https://scipy.org) | 1.18.1 | BSD-3-Clause | KD-trees, Delaunay, distance transforms, filters |
| [Matplotlib](https://matplotlib.org) | 3.11.2 | Matplotlib License (PSF-based) | preview and menu images |
| [rasterio](https://github.com/rasterio/rasterio) | 1.5.2 | BSD-3-Clause | GeoTIFF reading and writing |
| [pyproj](https://github.com/pyproj4/pyproj) | 3.8.0 | MIT | coordinate transforms |
| [Requests](https://requests.readthedocs.io) | 2.34.2 | Apache-2.0 | HTTP downloads |
| [pydantic](https://github.com/pydantic/pydantic) (+ pydantic-core 2.50.4) | 2.14.3 | MIT | stage file schema |

Native libraries inside the binary wheels: rasterio's wheels bundle **GDAL 3.12.2** (MIT) and its dependencies;
pyproj's wheels bundle **PROJ 9.8.1** (MIT). Their licence files ship inside the wheels.

## Development tools

| Tool | Version | Licence |
|---|---|---|
| [pytest](https://pytest.org) | 9.2.0 | MIT |
| [Ruff](https://docs.astral.sh/ruff) | 0.17.5 | MIT |
| [uv](https://docs.astral.sh/uv/) / uv_build | – | MIT OR Apache-2.0 |

## Formats and specifications

- **Stage IR** (`acrxs/stage-ir` v2) is defined by [acr-extrastages](https://github.com/cherrymcgerry/acr-extrastages)
  (MIT OR Apache-2.0). This tool writes files in that format. The surface codes and physical material names in
  `export/stage_ir.py` follow its `config/surface-map.toml`. The builder itself is bundled in `builder/` (see above);
  the Python generator in `src/` does not use its code.
- **glTF 2.0** (Khronos Group) is written by our own minimal writer (`export/gltf.py`).

## Data downloaded at run time

| Data | Provider | Licence | Attribution |
|---|---|---|---|
| Terrain (LiDAR HD MNT) | IGN, via the Géoplateforme WMS-R | Etalab Licence Ouverte 2.0 | © IGN – LiDAR HD (Etalab 2.0) |
| Roads | OpenStreetMap, via the Overpass API | ODbL 1.0 | © OpenStreetMap contributors |

See [docs/licensing.md](docs/licensing.md) for what this means for stages you build.

## Optional external programs

- [Blender](https://www.blender.org) (GPL-2.0-or-later) runs `scripts/blender_view_package.py` for previews.
  The script only uses Blender's Python API and is not part of Blender.
