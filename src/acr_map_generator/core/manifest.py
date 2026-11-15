"""data/<area>/manifest.json: which provider produced each layer, with licence and attribution.

Downstream steps locate their inputs through the manifest rather than hard-coded file names,
and attribution for derived content is generated from it.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .area import Area
from .registry import Provider

# Credit for the tool, written into every export next to the data attribution. Not a licence requirement
# (the code licence does not cover output); users may remove it, but the README asks them to keep it.
TOOL_CREDIT = "Made with ACR Map Generator"
TOOL_URL = "https://github.com/icq4ever/ACRMapGenerator"


def _path(area: Area) -> Path:
    return area.data_dir / "manifest.json"


def load(area: Area) -> dict:
    p = _path(area)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"area": area.name, "layers": {}}


def save(area: Area, m: dict) -> None:
    _path(area).write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")


def record(area: Area, provider: Provider, file: Path, kind: str | None = None, extra: dict | None = None) -> None:
    """kind defaults to the provider's kind; pass e.g. "terrain_fine" for a second layer of that kind."""
    m = load(area)
    info = provider.info
    m["layers"][kind or info.kind] = {
        "provider": info.id,
        "title": info.title,
        "file": file.relative_to(area.data_dir).as_posix(),
        "licence": info.licence,
        "attribution": info.attribution,
        "url": info.url,
        "crs": area.crs,
        "bbox_wgs84": [area.west, area.south, area.east, area.north],
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        **(extra or {}),
    }
    _path(area).write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")


def record_derived(
    area: Area,
    kind: str,
    file: Path,
    *,
    inputs: list[str],
    osm_derived: bool,
    stats: dict | None = None,
) -> None:
    """Record a layer computed from other layers (no provider).

    osm_derived marks geometry that is a Derivative Database under ODbL. Such layers are never exported
    (see docs/licensing.md).
    """
    m = load(area)
    m["layers"][kind] = {
        "derived": True,
        "file": file.relative_to(area.data_dir).as_posix(),
        "inputs": inputs,
        "osm_derived": osm_derived,
        "crs": area.crs,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        **({"stats": stats} if stats else {}),
    }
    _path(area).write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")


def layer_path(area: Area, kind: str) -> Path | None:
    layer = load(area)["layers"].get(kind)
    if not layer:
        return None
    p = area.data_dir / layer["file"]
    return p if p.exists() else None


def attributions(area: Area) -> list[str]:
    return sorted({a for layer in load(area)["layers"].values() if (a := layer.get("attribution"))})
