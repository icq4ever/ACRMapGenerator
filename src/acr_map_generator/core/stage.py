"""Stage definitions: stages/<id>.toml, schema "acr-map-generator/stage" version 1.

A stage is a route (ordered waypoints along named roads) plus export settings. The file name is the stage id.
Start a new one with `acr-map-generator new <id>` (copies stages/_template.toml) and check it with
`acr-map-generator validate <id>`. The models below are the single source of truth for the format; the same
models can back a web API later.

A stage's fetch area (core.area.Area) is the waypoint envelope plus a margin.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from pyproj import Transformer

from .area import PROJECT_ROOT, Area

STAGES_DIR = PROJECT_ROOT / "stages"
TEMPLATE = STAGES_DIR / "_template.toml"
SCHEMA, VERSION = "acr-map-generator/stage", 1
STAGE_ID = re.compile(r"^[a-z0-9][a-z0-9_]*$")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Waypoint(_Strict):
    name: str = ""
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


Surface = Literal["asphalt", "gravel", "gravel_loose"]  # gravel = hard-packed, gravel_loose = deep/loose


class SurfaceSegment(_Strict):
    """Road surface over a stretch, in km along the stage centreline (0 = start waypoint)."""

    from_km: float = Field(ge=0)
    to_km: float = Field(gt=0)
    surface: Surface
    note: str = ""

    @model_validator(mode="after")
    def _order(self) -> SurfaceSegment:
        if self.to_km <= self.from_km:
            raise ValueError(f"to_km ({self.to_km}) must be greater than from_km ({self.from_km})")
        return self


class Link(_Strict):
    """A reference page about the real stage (e.g. its rally-maps.com page). Shown with the stage, never fetched."""

    title: str
    url: str = Field(pattern=r"^https?://\S+$")


class StageInfo(_Strict):
    title: str  # internal name, may mention the event
    display_name: str  # product/menu name: places only, no event trademarks
    country: str = Field(pattern=r"^[A-Z]{2}$")  # ISO 3166-1 alpha-2
    region: str = ""
    surface: Surface = "asphalt"  # default for every stretch not covered by route.surfaces
    # menu location id (locations/<id>/ for its logo and tile); default: the region as a slug, e.g. "corsica"
    location: str | None = Field(default=None, pattern=r"^[a-z0-9_]+$")


class RouteConfig(_Strict):
    roads: list[str] = []  # road refs the route follows (OSM `ref`), preferred by the router
    length_km: float | None = Field(default=None, gt=0)  # reference length, checked against the route
    waypoints: list[Waypoint] = Field(min_length=2)  # start, junctions, finish in driving order
    surfaces: list[SurfaceSegment] = []  # mixed stages: stretches that differ from stage.surface

    @model_validator(mode="after")
    def _no_overlap(self) -> RouteConfig:
        segs = sorted(self.surfaces, key=lambda x: x.from_km)
        for a, b in zip(segs, segs[1:]):
            if b.from_km < a.to_km:
                raise ValueError(f"surface segments overlap: {a.from_km}-{a.to_km} and {b.from_km}-{b.to_km} km")
        return self


class TerrainConfig(_Strict):
    crs: str = Field(default="EPSG:2154", pattern=r"^EPSG:\d+$")
    resolution: float = Field(default=1.0, gt=0)  # base DTM cell size (m)
    margin: float = Field(default=1000.0, ge=0)  # m around the waypoints for the fetch area
    sources: dict[str, str] = {}  # pin a provider per data kind, e.g. {terrain = "ign_lidarhd"}


class PackageConfig(_Strict):
    id: str = Field(pattern=r"^[A-Za-z0-9]+$")
    road_width: float = Field(default=6.0, gt=0)  # m; fallback when the width is not measured


class StageIrVariant(_Strict):
    name: str = Field(pattern=r"^[a-z0-9_]+$")
    id: str | None = Field(
        default=None, pattern=r"^[a-z0-9_]+$"
    )  # default: <stage_ir.id>_<name> ("full": <stage_ir.id>)
    from_m: float | None = Field(default=None, ge=0)
    to_m: float | None = Field(default=None, gt=0)
    fit_host: bool = False  # longest section that fits the host level (overrides from_m / to_m)


class StageIrConfig(_Strict):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    surfaces: dict[str, str] = {}  # mesh material -> surface code overrides
    variants: list[StageIrVariant] = [StageIrVariant(name="full")]

    def variant_id(self, v: StageIrVariant) -> str:
        return v.id or (self.id if v.name == "full" else f"{self.id}_{v.name}")


class ExportConfig(_Strict):
    package: PackageConfig | None = None
    stage_ir: StageIrConfig | None = None


class StageConfig(_Strict):
    schema_: Literal["acr-map-generator/stage"] = Field(alias="schema")
    version: Literal[1]
    stage: StageInfo
    route: RouteConfig
    terrain: TerrainConfig = TerrainConfig()
    links: list[Link] = []  # reference pages, carried into the exports
    reference: dict[str, Any] = {}  # free-form notes about the real stage (e.g. rally_maps)
    export: ExportConfig = ExportConfig()

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @model_validator(mode="after")
    def _ids_unique(self) -> StageConfig:
        ir = self.export.stage_ir
        if ir:
            ids = [ir.variant_id(v) for v in ir.variants]
            if len(set(ids)) != len(ids):
                raise ValueError(f"duplicate stage_ir variant ids: {ids}")
        return self

    @field_validator("version", mode="before")
    @classmethod
    def _version(cls, v):
        if v != VERSION:
            raise ValueError(f"stage file version {v} is not supported (expected {VERSION})")
        return v


@dataclass(frozen=True)
class Stage:
    name: str  # stage id = file name
    config: StageConfig
    area: Area
    path: Path

    # shortcuts used by the processing steps
    @property
    def title(self) -> str:
        return self.config.stage.title

    @property
    def roads(self) -> list[str]:
        return self.config.route.roads

    @property
    def length_km(self) -> float | None:
        return self.config.route.length_km

    @property
    def waypoints(self) -> list[Waypoint]:
        return self.config.route.waypoints

    @property
    def location_id(self) -> str:
        info = self.config.stage
        if info.location:
            return info.location
        import unicodedata

        base = info.region or info.country
        ascii_ = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
        return re.sub(r"[^a-z0-9]+", "_", ascii_.lower()).strip("_") or "unknown"

    def surface_at(self, s_m):
        """Surface name per distance (m along the centreline), from route.surfaces over stage.surface."""
        import numpy as np

        s_m = np.asarray(s_m, dtype=np.float64)
        out = np.full(s_m.shape, self.config.stage.surface, dtype=object)
        for seg in self.config.route.surfaces:
            out[(s_m >= seg.from_km * 1000) & (s_m < seg.to_km * 1000)] = seg.surface
        return out

    def surface_runs(self, s0: float, s1: float, step: float = 1.0) -> list[dict]:
        """Contiguous runs [{from_m, to_m, surface}] between s0 and s1 (m along the centreline)."""
        import numpy as np

        t = np.arange(s0, s1, step)
        lab = self.surface_at(t)
        runs, a = [], 0
        for i in range(1, len(t) + 1):
            if i == len(t) or lab[i] != lab[a]:
                runs.append(
                    {"from_m": float(t[a]), "to_m": float(t[i]) if i < len(t) else float(s1), "surface": str(lab[a])}
                )
                a = i
        return runs


def stage_path(name: str) -> Path | None:
    """Path of a stage file for an id or path, or None if there is no such stage."""
    p = Path(name)
    if not p.suffix:
        p = STAGES_DIR / f"{name}.toml"
    return p if p.exists() and p.parent.name == "stages" and not p.name.startswith("_") else None


def list_stages() -> list[str]:
    return sorted(p.stem for p in STAGES_DIR.glob("*.toml") if not p.name.startswith("_"))


class StageError(ValueError):
    pass


def parse_stage(text: str, source: str = "<string>") -> StageConfig:
    """Parse and validate stage TOML text. Raises StageError with readable messages."""
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise StageError(f"{source}: TOML syntax: {e}") from None
    todo = [k for k, v in _walk(raw) if isinstance(v, str) and "TODO" in v]
    if todo:
        raise StageError(f"{source}: fill in the TODO values: {', '.join(todo)}")
    try:
        return StageConfig.model_validate(raw)
    except ValidationError as e:
        lines = [f"{source}: {len(e.errors())} problem(s)"]
        for err in e.errors():
            loc = ".".join(str(x) for x in err["loc"])
            lines.append(f"  {loc}: {err['msg']}")
        raise StageError("\n".join(lines)) from None


def _walk(d, prefix=""):
    if isinstance(d, dict):
        for k, v in d.items():
            yield from _walk(v, f"{prefix}{k}.")
    elif isinstance(d, list):
        for i, v in enumerate(d):
            yield from _walk(v, f"{prefix}{i}.")
    else:
        yield prefix.rstrip("."), d


def load_stage(name: str) -> Stage:
    path = stage_path(name)
    if path is None:
        raise FileNotFoundError(f"no stage {name!r} in {STAGES_DIR}")
    if not STAGE_ID.match(path.stem):
        raise StageError(f"stage id {path.stem!r} must match {STAGE_ID.pattern}")
    cfg = parse_stage(path.read_text(encoding="utf-8"), str(path))
    t = cfg.terrain
    # Envelope in the projected CRS (metres), expanded by the margin, then back to WGS84.
    fwd = Transformer.from_crs("EPSG:4326", t.crs, always_xy=True)
    inv = Transformer.from_crs(t.crs, "EPSG:4326", always_xy=True)
    xs, ys = zip(*(fwd.transform(w.lon, w.lat) for w in cfg.route.waypoints))
    x0, y0, x1, y1 = min(xs) - t.margin, min(ys) - t.margin, max(xs) + t.margin, max(ys) + t.margin
    lons, lats = zip(*(inv.transform(x, y) for x in (x0, x1) for y in (y0, y1)))
    area = Area(
        name=path.stem,
        title=cfg.stage.title,
        west=min(lons),
        south=min(lats),
        east=max(lons),
        north=max(lats),
        crs=t.crs,
        resolution=t.resolution,
        sources=dict(t.sources),
    )
    return Stage(name=path.stem, config=cfg, area=area, path=path)


def new_stage(stage_id: str) -> Path:
    """Create stages/<stage_id>.toml from the template."""
    if not STAGE_ID.match(stage_id):
        raise StageError(f"stage id {stage_id!r} must match {STAGE_ID.pattern}")
    out = STAGES_DIR / f"{stage_id}.toml"
    if out.exists():
        raise FileExistsError(out)
    text = TEMPLATE.read_text(encoding="utf-8").replace("{{stage_id}}", stage_id)
    out.write_text(text, encoding="utf-8")
    return out
