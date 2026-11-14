"""Command line.

acr-map-generator new <id>                   create stages/<id>.toml from the template
acr-map-generator validate <id>              check a stage file
acr-map-generator build <id> [--to STEP] [--only STEP] [--force]
acr-map-generator status <id> [--json]       per-step state
acr-map-generator list                       all stages
acr-map-generator stage-ir <id> [--fit-host | --from-m A --to-m B] [--id ID]   one-off IR export
acr-map-generator preview <id>               hillshade PNG with roads, route and centreline
acr-map-generator sources [kind]             data providers
"""

from __future__ import annotations

import argparse
import json

from . import pipeline
from .core import registry
from .core.stage import StageError, list_stages, load_stage, new_stage


def _print_event(e: dict) -> None:
    ev = e["event"]
    if ev == "skip":
        print(f"[{e['step']}] up to date")
    elif ev == "start":
        print(f"[{e['step']}] building ({e.get('reason') or 'requested'})")
    elif ev == "done":
        print(f"[{e['step']}] done in {e['seconds']} s")
    elif ev == "error":
        print(f"[{e['step']}] FAILED: {e['error']}")


def cmd_new(args: argparse.Namespace) -> None:
    p = new_stage(args.stage)
    print(f"created {p}")
    print(f"fill in the TODOs, then: validate {args.stage} / build {args.stage}")


def cmd_validate(args: argparse.Namespace) -> None:
    try:
        st = load_stage(args.stage)
    except StageError as e:
        print(e)
        raise SystemExit(1) from None
    c, a = st.config, st.area
    print(f"{st.name}: OK - {c.stage.display_name}, {len(c.route.waypoints)} waypoints, roads {c.route.roads or '-'}")
    print(f"  area {a.west:.4f},{a.south:.4f} .. {a.east:.4f},{a.north:.4f} ({a.crs}, {a.resolution} m)")
    for kind in registry.KINDS:
        try:
            print(f"  {kind}: {registry.select(kind, a).info.id}")
        except LookupError as e:
            print(f"  {kind}: NO PROVIDER ({e})")


def cmd_build(args: argparse.Namespace) -> None:
    res = pipeline.build(args.stage, targets=args.to, only=args.only, force=args.force, on_event=_print_event)
    if any(r["status"] == "failed" for r in res):
        raise SystemExit(1)


def cmd_status(args: argparse.Namespace) -> None:
    rows = pipeline.status(args.stage)
    if args.json:
        print(json.dumps(rows, indent=1))
        return
    for r in rows:
        when = f" (built {r['built_at']}, {r['seconds']} s)" if r.get("built_at") else ""
        why = f": {r['reason']}" if r.get("reason") else ""
        print(f"{r['step']:11} {r['state']:8}{why}{when}")


def cmd_list(args: argparse.Namespace) -> None:
    for sid in list_stages():
        try:
            st = load_stage(sid)
        except (StageError, FileNotFoundError) as e:
            print(f"{sid:40} INVALID ({str(e).splitlines()[0]})")
            continue
        rows = pipeline.status(st)
        ok = sum(r["state"] == "ok" for r in rows)
        total = sum(r["state"] != "n/a" for r in rows)
        print(f"{sid:40} {ok}/{total} steps ok  {st.config.stage.display_name} ({st.config.stage.country})")


def cmd_stage_ir(args: argparse.Namespace) -> None:
    from .export.stage_ir import export_all, export_stage_ir, longest_fitting_section

    stage = load_stage(args.stage)
    if args.from_m is None and args.to_m is None and not args.fit_host and not args.id:
        for p in export_all(stage):  # every configured variant
            print(f"wrote {p}")
        return
    a, b = args.from_m, args.to_m
    if args.fit_host:
        a, b = longest_fitting_section(stage)
        print(f"longest section fitting the host level: {a:.0f}-{b:.0f} m")
    print(f"wrote {export_stage_ir(stage, a, b, args.id)}")


def cmd_preview(args: argparse.Namespace) -> None:
    from .preview import render_preview

    st = load_stage(args.stage)
    print(f"wrote {render_preview(st.area, waypoints=[(w.lon, w.lat) for w in st.waypoints])}")


def cmd_sources(args: argparse.Namespace) -> None:
    for p in registry.providers(args.kind):
        i = p.info
        print(f"{i.kind:8} {i.id:14} {i.title}")
        print(f"{'':23} coverage: {i.coverage} | licence: {i.licence}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="acr-map-generator", description="Rally stages for ACR from open geodata.")
    sub = ap.add_subparsers(dest="command", required=True)
    steps = [s.name for s in pipeline.STEPS]

    p = sub.add_parser("new", help="create stages/<id>.toml from the template")
    p.add_argument("stage")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("validate", help="check a stage file")
    p.add_argument("stage")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("build", help="run every out-of-date step for a stage")
    p.add_argument("stage")
    p.add_argument("--to", action="append", choices=steps, help="stop after this step (with what it needs)")
    p.add_argument("--only", action="append", choices=steps, help="run just this step, even if up to date")
    p.add_argument("--force", action="store_true", help="rebuild every step even if up to date")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("status", help="per-step state of a stage")
    p.add_argument("stage")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)

    sub.add_parser("list", help="all stages and how far they are built").set_defaults(func=cmd_list)

    p = sub.add_parser("stage-ir", help="one-off Stage IR export (sections) outside the configured variants")
    p.add_argument("stage")
    p.add_argument("--from-m", type=float, help="section start (m along the stage)")
    p.add_argument("--to-m", type=float, help="section finish (m along the stage)")
    p.add_argument("--fit-host", action="store_true", help="longest section that fits the host level")
    p.add_argument("--id", help="IR id")
    p.set_defaults(func=cmd_stage_ir)

    p = sub.add_parser("preview", help="hillshade PNG with roads, route and centreline")
    p.add_argument("stage")
    p.set_defaults(func=cmd_preview)

    p = sub.add_parser("sources", help="list data providers")
    p.add_argument("kind", nargs="?", choices=registry.KINDS)
    p.set_defaults(func=cmd_sources)

    args = ap.parse_args()
    args.func(args)
