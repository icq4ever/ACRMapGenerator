"""Open a stage package in Blender for a visual check.

    blender --python scripts/blender_view_package.py -- <path/to/package/<id>>

Runs inside Blender (bpy), not in the project venv. Imports all terrain tiles, recolours the
materials (road / verge / terrain), draws the spline as a red line and marks start and finish.
It also animates a **drive-through camera**: the speed comes from road curvature and acceleration
limits. The viewport opens through that camera. Press Space to play in real time, and use the
timeline markers (every km, bridges) to jump. A static `driver_cam` sits at the start line.

    blender -b --python scripts/blender_view_package.py -- <package> out.png [metres]

renders the drive camera at the given distance from the start (default 0) and exits.

Blender's glTF importer converts Y-up to Z-up, so Blender axes are X = East, Y = North, Z = Up
(metres, relative to the package origin, absolute elevation).
"""

import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

COLOURS = {
    "road_asphalt": (0.06, 0.06, 0.07, 1.0),
    "road_gravel": (0.45, 0.40, 0.33, 1.0),
    "verge": (0.33, 0.26, 0.17, 1.0),
    "terrain": (0.20, 0.30, 0.13, 1.0),
}
EYE_HEIGHT = 1.2  # m above the road
LOOK_AHEAD = 40.0  # m along the spline (static driver camera)

# Drive-through: speed limited by curvature and by acceleration/braking, like a rally car on asphalt
FPS = 30
KEY_STEP = 5.0  # m between camera keyframes
V_MAX = 150 / 3.6  # m/s
A_LAT = 9.0  # m/s², lateral grip
A_ACC = 4.0  # m/s², acceleration
A_BRK = 9.0  # m/s², braking
CURV_SMOOTH = 6.0  # m, smoothing of the heading before taking curvature


def speed_profile(s, xy):
    """Speed (m/s) per spline point from curvature + forward/backward acceleration limits."""
    import numpy as np

    s = np.asarray(s)
    xy = np.asarray(xy)
    d = np.gradient(xy, s, axis=0)
    h = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    ds = float(np.median(np.diff(s)))
    r = max(1, int(round(3 * CURV_SMOOTH / ds)))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) * ds / CURV_SMOOTH) ** 2)
    k /= k.sum()
    hs = np.convolve(np.pad(h, r, mode="edge"), k, mode="valid")
    curv = np.abs(np.gradient(hs, s))
    v = np.minimum(V_MAX, np.sqrt(A_LAT / np.maximum(curv, 1e-6)))
    v[0] = 0.0  # standing start
    for i in range(1, len(v)):  # acceleration limit
        v[i] = min(v[i], np.sqrt(v[i - 1] ** 2 + 2 * A_ACC * (s[i] - s[i - 1])))
    for i in range(len(v) - 2, -1, -1):  # braking limit
        v[i] = min(v[i], np.sqrt(v[i + 1] ** 2 + 2 * A_BRK * (s[i + 1] - s[i])))
    return v


def add_drive(scene, spline, structures):
    """Keyframe a camera driving the spline; returns (camera, total seconds)."""
    import numpy as np

    pts = np.array(spline["points"], dtype=float)
    s = np.array(spline["s"], dtype=float)
    bl = np.column_stack([pts[:, 0], -pts[:, 1], pts[:, 2]])  # Blender frame
    v = speed_profile(s, bl[:, :2])
    # time at each point (trapezoid on 1/v, first segment from standing start)
    vm = np.maximum((v[1:] + v[:-1]) / 2, 0.5)
    t = np.r_[0.0, np.cumsum(np.diff(s) / vm)]

    cam_data = bpy.data.cameras.new("drive")
    cam_data.lens = 18
    cam_data.clip_start = 0.1
    cam_data.clip_end = 20000
    cam = bpy.data.objects.new("drive_cam", cam_data)
    cam.rotation_mode = "QUATERNION"
    scene.collection.objects.link(cam)

    def at(dist):
        return Vector([float(np.interp(dist, s, bl[:, j])) for j in range(3)])

    prev_q = None
    edit = bpy.context.preferences.edit
    old_interp = edit.keyframe_new_interpolation_type
    edit.keyframe_new_interpolation_type = "LINEAR"
    try:
        for dist in np.arange(0.0, s[-1], KEY_STEP).tolist() + [float(s[-1])]:
            frame = 1 + float(np.interp(dist, s, t)) * FPS
            vel = float(np.interp(dist, s, v))
            ahead = min(s[-1], dist + 8.0 + 0.8 * vel)  # look further ahead at speed
            eye = at(dist) + Vector((0, 0, EYE_HEIGHT))
            tgt = at(ahead) + Vector((0, 0, EYE_HEIGHT * 0.7))
            if (tgt - eye).length < 1e-3:
                tgt = eye + (at(dist) - at(max(0.0, dist - 5.0)))
            q = (tgt - eye).to_track_quat("-Z", "Y")
            if prev_q is not None and prev_q.dot(q) < 0:
                q.negate()
            prev_q = q
            cam.location = eye
            cam.rotation_quaternion = q
            cam.keyframe_insert("location", frame=frame)
            cam.keyframe_insert("rotation_quaternion", frame=frame)
    finally:
        edit.keyframe_new_interpolation_type = old_interp

    scene.render.fps = FPS
    scene.frame_start = 1
    scene.frame_end = int(np.ceil(1 + t[-1] * FPS))
    scene.sync_mode = "FRAME_DROP"  # play in real time
    for km in range(1, int(s[-1] // 1000) + 1):
        scene.timeline_markers.new(f"{km} km", frame=int(1 + np.interp(km * 1000, s, t) * FPS))
    for st in structures:
        scene.timeline_markers.new(f"bridge {st['depth_m']:.0f}m", frame=int(1 + np.interp(st["from_m"], s, t) * FPS))
    scene.timeline_markers.new("FINISH", frame=scene.frame_end)
    print(
        f"[acr-map-generator] drive: {int(t[-1] // 60)}:{t[-1] % 60:04.1f} "
        f"(avg {s[-1] / t[-1] * 3.6:.0f} km/h, max {v.max() * 3.6:.0f} km/h)"
    )
    return cam, float(t[-1])


def stage_to_blender(p):
    """Stage frame (X east, Y south, Z up) -> Blender (X east, Y north, Z up)."""
    return Vector((p[0], -p[1], p[2]))


def material(name, rgba, emission=False):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = rgba  # solid viewport colour
    if m.node_tree is None:  # Blender < 5 creates materials without nodes
        m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = rgba
        bsdf.inputs["Roughness"].default_value = 0.9
        if emission and "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = rgba
            bsdf.inputs["Emission Strength"].default_value = 2.0
    return m


def main():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if not argv:
        raise SystemExit("usage: blender --python blender_view_package.py -- <package dir>")
    pkg = Path(argv[0])
    meta = json.loads((pkg / "stage.json").read_text(encoding="utf-8"))
    spline = json.loads((pkg / "spline.json").read_text(encoding="utf-8"))

    # Empty the default scene (cube, light, camera)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    terrain_col = bpy.data.collections.new("terrain")
    bpy.context.scene.collection.children.link(terrain_col)

    # Import tiles; glTF import creates material copies (terrain.001, ...) per file
    for t in meta["terrain"]["tiles"]:
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(pkg / t["file"]))
        for obj in set(bpy.data.objects) - before:
            for c in obj.users_collection:
                c.objects.unlink(obj)
            terrain_col.objects.link(obj)

    # One shared material per name, recoloured
    shared = {name: material(name, rgba) for name, rgba in COLOURS.items()}
    for obj in terrain_col.objects:
        for slot in obj.material_slots:
            if slot.material:
                base = slot.material.name.split(".")[0]
                if base in shared:
                    slot.material = shared[base]
    for m in list(bpy.data.materials):
        if m.users == 0:
            bpy.data.materials.remove(m)

    # Spline as a thin red line on the road
    pts = [stage_to_blender(p) + Vector((0, 0, 0.08)) for p in spline["points"]]
    cd = bpy.data.curves.new("spline", "CURVE")
    cd.dimensions = "3D"
    cd.bevel_depth = 0.06  # thin centre line, readable from the driver camera
    poly = cd.splines.new("POLY")
    poly.points.add(len(pts) - 1)
    for sp, p in zip(poly.points, pts):
        sp.co = (p.x, p.y, p.z, 1.0)
    cobj = bpy.data.objects.new("spline", cd)
    cobj.data.materials.append(material("spline", (0.9, 0.05, 0.05, 1.0), emission=True))
    bpy.context.scene.collection.objects.link(cobj)

    # Start / finish gates: a 5 m post on each side of the road
    s = spline["s"]
    half = spline.get("width_m", [6.0])[0] / 2 + 1.5
    for name, colour, idx in (("START", (0.1, 0.8, 0.1, 1.0), 0), ("FINISH", (0.9, 0.1, 0.1, 1.0), len(pts) - 1)):
        j = min(idx + 1, len(pts) - 1) if idx == 0 else idx - 1
        fwd = (pts[j] - pts[idx]) * (1 if idx == 0 else -1)
        side = Vector((-fwd.y, fwd.x, 0)).normalized()
        mat = material(name.lower(), colour, emission=True)
        for sign in (-1, 1):
            bpy.ops.mesh.primitive_cylinder_add(
                radius=0.3, depth=5.0, location=pts[idx] + side * half * sign + Vector((0, 0, 2.2))
            )
            post = bpy.context.active_object
            post.name = f"{name}_{'L' if sign > 0 else 'R'}"
            post.data.materials.append(mat)

    # Driver camera at the start, looking LOOK_AHEAD metres down the road
    ahead = next(i for i, v in enumerate(s) if v >= LOOK_AHEAD)
    eye = stage_to_blender(spline["points"][0]) + Vector((0, 0, EYE_HEIGHT))
    target = stage_to_blender(spline["points"][ahead]) + Vector((0, 0, EYE_HEIGHT * 0.6))
    cam_data = bpy.data.cameras.new("driver")
    cam_data.lens = 18
    cam_data.clip_start = 0.1
    cam_data.clip_end = 20000
    cam = bpy.data.objects.new("driver_cam", cam_data)
    cam.location = eye
    cam.rotation_euler = (target - eye).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.collection.objects.link(cam)

    # Drive-through camera is the active one: press Space to play
    drive_cam, _ = add_drive(bpy.context.scene, spline, meta.get("structures", []))
    bpy.context.scene.camera = drive_cam

    # Sun + sky
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.rotation_euler = (0.9, 0.3, 2.4)
    bpy.context.scene.collection.objects.link(sun)
    world = bpy.context.scene.world or bpy.data.worlds.new("world")
    bpy.context.scene.world = world
    world.color = (0.55, 0.65, 0.8)

    # Viewport: long clip range, material colours, view the start from above
    screen = bpy.context.screen  # None in background mode (-b)
    for area in screen.areas if screen else []:
        if area.type != "VIEW_3D":
            continue
        space = area.spaces.active
        space.clip_start = 0.5
        space.clip_end = 30000
        space.shading.type = "SOLID"
        space.shading.color_type = "MATERIAL"
        space.shading.light = "STUDIO"
        r3d = space.region_3d
        r3d.view_location = pts[0]
        r3d.view_distance = 400
        # behind the start, looking down the road from ~40° above
        r3d.view_rotation = ((eye - target).normalized() + Vector((0, 0, 0.8))).to_track_quat("Z", "Y")
        r3d.view_perspective = "CAMERA"  # through the drive camera; Space plays the drive

    # Optional: render the drive camera to a PNG (useful with -b for a quick check),
    # at the frame where the drive reaches argv[2] metres (default: the start)
    if len(argv) > 1:
        scene = bpy.context.scene
        if len(argv) > 2:
            target_m = float(argv[2])
            # find the frame by bisection on the camera's distance from the start along the spline
            import numpy as np

            sp_s = np.array(spline["s"])
            sp_xy = np.array(spline["points"])[:, :2] * [1, -1]
            lo, hi = scene.frame_start, scene.frame_end
            while hi - lo > 1:
                mid = (lo + hi) // 2
                scene.frame_set(mid)
                loc = np.array(scene.camera.matrix_world.translation[:2])
                i = int(np.argmin(np.hypot(*(sp_xy - loc).T)))
                lo, hi = (mid, hi) if sp_s[i] < target_m else (lo, mid)
            scene.frame_set(lo)
        else:
            scene.frame_set(scene.frame_start)
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.display.shading.color_type = "MATERIAL"
        scene.display.shading.light = "STUDIO"
        scene.render.resolution_x, scene.render.resolution_y = 1600, 900
        scene.render.filepath = str(Path(argv[1]).resolve())
        bpy.ops.render.render(write_still=True)

    print(
        f"[acr-map-generator] {meta['title']}: {len(meta['terrain']['tiles'])} tiles, "
        f"{meta['length_m'] / 1000:.2f} km. Numpad 0 = driver camera."
    )


main()
