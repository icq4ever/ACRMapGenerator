"""Provider registry.

Data is organised by *kind* (terrain, roads, ...). Each kind has one or more interchangeable
*providers*, typically one per national/regional open-data service. A provider declares what it
covers and how to fetch it into the area's data directory. Registration order is priority order
for automatic selection, so list the best (highest-resolution) providers first.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .area import Area

KINDS = ("terrain", "roads")

USER_AGENT = "acr-map-generator/0.1"


@dataclass(frozen=True)
class SourceInfo:
    id: str  # stable identifier used in area files and on the CLI, e.g. "ign_lidarhd"
    kind: str  # one of KINDS
    title: str
    coverage: str  # human-readable coverage description
    licence: str
    attribution: str  # text that must accompany derived content
    url: str = ""


class Provider(Protocol):
    info: SourceInfo

    def covers(self, area: Area) -> bool:
        """Cheap check (no network) whether this provider can serve the area."""
        ...

    def fetch(self, area: Area, out_dir: Path) -> Path:
        """Download into out_dir (data/<area>/<kind>/) and return the written file."""
        ...


_REGISTRY: dict[str, dict[str, Provider]] = {k: {} for k in KINDS}
_loaded = False


def register(provider: Provider) -> Provider:
    kind = provider.info.kind
    if kind not in _REGISTRY:
        raise ValueError(f"unknown kind {kind!r}; add it to KINDS")
    _REGISTRY[kind][provider.info.id] = provider
    return provider


def _load() -> None:
    global _loaded
    if not _loaded:
        _loaded = True
        from .. import sources  # noqa: F401  (imports register all providers)


def providers(kind: str | None = None) -> list[Provider]:
    _load()
    kinds = [kind] if kind else list(KINDS)
    return [p for k in kinds for p in _REGISTRY[k].values()]


def get(kind: str, provider_id: str) -> Provider:
    _load()
    try:
        return _REGISTRY[kind][provider_id]
    except KeyError:
        known = ", ".join(_REGISTRY.get(kind, {})) or "none"
        raise KeyError(f"no {kind} provider {provider_id!r} (known: {known})") from None


def select(kind: str, area: Area, provider_id: str | None = None) -> Provider:
    """Explicit id (CLI) > area [sources] entry > first registered provider that covers the area."""
    provider_id = provider_id or area.sources.get(kind)
    if provider_id:
        p = get(kind, provider_id)
        if not p.covers(area):
            raise ValueError(f"{kind} provider {provider_id!r} does not cover area {area.name!r}")
        return p
    for p in providers(kind):
        if p.covers(area):
            return p
    raise LookupError(f"no {kind} provider covers area {area.name!r}")
