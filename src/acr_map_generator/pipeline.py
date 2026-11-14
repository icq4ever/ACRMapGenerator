"""Stage build pipeline: one ordered list of steps, each skipped when its fingerprint is unchanged.

    build("tdc1998_ss8_muracciole_noceta")            # everything that is out of date
    build(stage_id, targets=["centreline"])            # up to a step (and what it depends on)
    build(stage_id, only=["stage_ir"])                 # just this step, rerun
    status(stage_id)                                   # per step: ok / stale / missing, and why

A step's fingerprint hashes its parameters (from the stage file and the module constants that shape its
output), the fingerprints of the steps it depends on, and, for processing steps, the source of the modules
that compute it. Download steps leave the code out, so editing code never triggers a re-download.
Fingerprints are stored in data/<stage>/manifest.json under "steps".

This module is the programmatic entry point (CLI and a future web API both call it). Progress is reported
through an optional on_event(dict) callback; results are plain dicts.
"""

from __future__ import annotations

import ast
import hashlib
import json
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .core import manifest, registry
from .core.stage import Stage, load_stage

PKG = Path(__file__).resolve().parent
Event = Callable[[dict], None]


@dataclass(frozen=True)
class Step:
    name: str
    deps: tuple[str, ...]
    params: Callable[[Stage], dict]  # what shapes the output (besides deps and code)
    run: Callable[[Stage], object]
    outputs: Callable[[Stage], list[Path | None]]  # must all exist for the step to count as done
    code: tuple[str, ...] = ()  # source files (relative to the package) whose changes invalidate the step
    doc: str = ""
    optional: Callable[[Stage], bool] = field(default=lambda st: True)  # False: step does not apply to this stage


def _layer(kind: str) -> Callable[[Stage], list[Path | None]]:
    return lambda st: [manifest.layer_path(st.area, kind)]


def _fetch(kind: str) -> Callable[[Stage], Path]:
    def run(st: Stage) -> Path:
        p = registry.select(kind, st.area)
        out = p.fetch(st.area, st.area.kind_dir(kind))
        manifest.record(st.area, p, out)
        return out

    return run


def _area_params(kind: str) -> Callable[[Stage], dict]:
    def params(st: Stage) -> dict:
        a = st.area
        return {
            "bbox": [round(v, 7) for v in (a.west, a.south, a.east, a.north)],
            "crs": a.crs,
            "res": a.resolution,
            "provider": registry.select(kind, a).info.id,
        }

    return params


def _route(st: Stage):
    from .process.route import build_route

    return build_route(st)


def _corridor(st: Stage):
    from .process.corridor import fetch_corridor

    return fetch_corridor(st)


def _corridor_params(st: Stage) -> dict:
    from .process import corridor as c

    return {"res": c.FINE_RES, "tile": c.TILE, "buffer": c.BUFFER, "overlap": c.OVERLAP}


def _vista(st: Stage):
    from .process.vista import fetch_vista

    return fetch_vista(st)


def _vista_params(st: Stage) -> dict:
    from .process import vista as v

    return {"margin": v.MARGIN, "res": v.RES}


def _centreline(st: Stage):
    from .process.centreline import extract_centreline

    return extract_centreline(st)


def _package(st: Stage):
    from .export.package import write_package

    return write_package(st)


def _package_outputs(st: Stage) -> list[Path | None]:
    pkg = st.config.export.package
    return [st.area.data_dir / "package" / pkg.id / "stage.json"] if pkg else []


def _stage_ir(st: Stage):
    from .export.stage_ir import export_all

    return export_all(st)


def _stage_ir_outputs(st: Stage) -> list[Path | None]:
    irc = st.config.export.stage_ir
    return [st.area.data_dir / "stage_ir" / irc.variant_id(v) / "stage.json" for v in irc.variants] if irc else []


STEPS: list[Step] = [
    Step(
        "terrain", (), _area_params("terrain"), _fetch("terrain"), _layer("terrain"), doc="base DTM for the stage area"
    ),
    Step("roads", (), _area_params("roads"), _fetch("roads"), _layer("roads"), doc="OSM roads for the stage area"),
    Step(
        "route",
        ("roads",),
        lambda st: st.config.route.model_dump(exclude={"surfaces"}),
        _route,
        _layer("route"),
        code=("process/route.py",),
        doc="OSM route guide through the waypoints",
    ),
    Step("corridor", ("route",), _corridor_params, _corridor, _layer("terrain_fine"), doc="0.5 m DTM around the route"),
    Step("vista", ("route",), _vista_params, _vista, _layer("terrain_vista"), doc="25 m DTM ~5 km around the route"),
    Step(
        "centreline",
        ("terrain", "route", "corridor"),
        lambda st: {},
        _centreline,
        _layer("centreline"),
        code=("process/centreline.py", "core/raster.py"),
        doc="LiDAR road centreline, width, profile",
    ),
    Step(
        "package",
        ("terrain", "corridor", "centreline"),
        lambda st: {
            "stage": st.config.stage.model_dump(),
            "surfaces": [x.model_dump() for x in st.config.route.surfaces],
            "package": st.config.export.package.model_dump(),
        },
        _package,
        _package_outputs,
        code=("export/package.py", "export/terrain_mesh.py", "export/gltf.py", "export/images.py", "core/raster.py"),
        doc="stage package (glb tiles, spline, metadata)",
        optional=lambda st: st.config.export.package is not None,
    ),
    Step(
        "stage_ir",
        ("terrain", "corridor", "vista", "centreline"),
        lambda st: {
            "stage": st.config.stage.model_dump(),
            "surfaces": [x.model_dump() for x in st.config.route.surfaces],
            "stage_ir": st.config.export.stage_ir.model_dump(),
        },
        _stage_ir,
        _stage_ir_outputs,
        code=("export/stage_ir.py", "export/terrain_mesh.py", "export/gltf.py", "export/vista.py", "core/raster.py"),
        doc="Stage IR v2 for the ACR builder",
        optional=lambda st: st.config.export.stage_ir is not None,
    ),
]
BY_NAME = {s.name: s for s in STEPS}


def _code_hash(files: tuple[str, ...]) -> str:
    """Hash of the modules' syntax trees: formatting and comments do not invalidate a step, code does."""
    h = hashlib.sha256()
    for f in files:
        h.update(f.encode())
        h.update(ast.dump(ast.parse((PKG / f).read_text(encoding="utf-8"))).encode())
    return h.hexdigest()[:16]


def _fingerprint(st: Stage, step: Step, recorded: dict) -> str:
    deps = {d: (recorded.get(d) or {}).get("fingerprint") for d in step.deps if BY_NAME[d].optional(st)}
    blob = json.dumps(
        {"params": step.params(st), "deps": deps, "code": _code_hash(step.code)}, sort_keys=True, default=str
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _state(st: Stage, step: Step, recorded: dict, fps: dict) -> tuple[str, str]:
    """('ok' | 'stale' | 'missing', reason)."""
    rec = recorded.get(step.name)
    outs = step.outputs(st)
    if rec is None or not outs or any(p is None or not Path(p).exists() for p in outs):
        if rec is None and outs and all(p is not None and Path(p).exists() for p in outs):
            return "stale", "outputs exist but were not built by the pipeline"
        return "missing", "never built" if rec is None else "outputs missing"
    if rec.get("fingerprint") != fps[step.name]:
        stale_deps = [d for d in step.deps if d in fps and fps[d] != (recorded.get(d) or {}).get("fingerprint")]
        return "stale", f"inputs changed: {', '.join(stale_deps)}" if stale_deps else "parameters or code changed"
    return "ok", ""


def _resolve(stage: Stage | str) -> Stage:
    return stage if isinstance(stage, Stage) else load_stage(stage)


def _closure(targets: list[str] | None) -> list[str]:
    if not targets:
        return [s.name for s in STEPS]
    need: set[str] = set()

    def add(n: str) -> None:
        if n not in BY_NAME:
            raise KeyError(f"unknown step {n!r} (steps: {', '.join(BY_NAME)})")
        if n not in need:
            need.add(n)
            for d in BY_NAME[n].deps:
                add(d)

    for t in targets:
        add(t)
    return [s.name for s in STEPS if s.name in need]


def status(stage: Stage | str) -> list[dict]:
    """Per step: name, state (ok / stale / missing / n/a), reason, built_at, seconds."""
    st = _resolve(stage)
    recorded = manifest.load(st.area).get("steps", {})
    # fingerprints as they would be if every step were rebuilt in order from the recorded state
    fps: dict[str, str] = {}
    rows = []
    for step in STEPS:
        if not step.optional(st):
            rows.append({"step": step.name, "state": "n/a", "reason": "not configured", "doc": step.doc})
            continue
        fps[step.name] = _fingerprint(st, step, {**recorded, **{k: {"fingerprint": v} for k, v in fps.items()}})
        state, reason = _state(st, step, recorded, fps)
        rec = recorded.get(step.name) or {}
        rows.append(
            {
                "step": step.name,
                "state": state,
                "reason": reason,
                "doc": step.doc,
                "built_at": rec.get("built_at"),
                "seconds": rec.get("seconds"),
            }
        )
    return rows


def build(
    stage: Stage | str,
    targets: list[str] | None = None,
    only: list[str] | None = None,
    force: bool = False,
    on_event: Event | None = None,
) -> list[dict]:
    """Run the out-of-date steps needed for targets (default: all), or exactly the `only` steps (always rerun,
    their inputs must exist). Stops at the first failure."""
    st = _resolve(stage)
    emit = on_event or (lambda e: None)
    results = []
    names = [s.name for s in STEPS if s.name in set(only)] if only else _closure(targets)
    force = force or bool(only)
    for name in names:
        step = BY_NAME[name]
        if not step.optional(st):
            continue
        m = manifest.load(st.area)
        recorded = m.get("steps", {})
        fp = _fingerprint(st, step, recorded)
        state, reason = _state(st, step, recorded, {**{k: v.get("fingerprint") for k, v in recorded.items()}, name: fp})
        if state == "ok" and not force:
            emit({"step": name, "event": "skip"})
            results.append({"step": name, "status": "skipped"})
            continue
        emit({"step": name, "event": "start", "reason": "forced" if force and state == "ok" else reason})
        t0 = time.perf_counter()
        try:
            out = step.run(st)
        except Exception as e:  # noqa: BLE001 - report and stop
            emit(
                {
                    "step": name,
                    "event": "error",
                    "error": f"{type(e).__name__}: {e}",
                    "traceback": traceback.format_exc(),
                }
            )
            results.append({"step": name, "status": "failed", "error": f"{type(e).__name__}: {e}"})
            break
        secs = round(time.perf_counter() - t0, 1)
        m = manifest.load(st.area)  # the step itself wrote layers
        m.setdefault("steps", {})[name] = {
            "fingerprint": fp,
            "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "seconds": secs,
        }
        manifest.save(st.area, m)
        emit({"step": name, "event": "done", "seconds": secs, "output": str(out)})
        results.append({"step": name, "status": "built", "seconds": secs})
    return results
