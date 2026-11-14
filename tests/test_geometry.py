"""Mesh, glTF and profile helpers on synthetic data (no network)."""

import json
import struct

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from acr_map_generator.core.raster import Raster
from acr_map_generator.export.gltf import write_glb
from acr_map_generator.export.terrain_mesh import TILE, ZONES_LIGHT, Frame, build_tiles
from acr_map_generator.process.centreline import _bridge_profile

# Synthetic DTM in Lambert-93 around (1,000,000 E, 6,000,000 N): a tilted plane with gentle waves
OX, OY, W, H = 1_000_000.0, 6_000_000.0, 2600, 1600


def _z(e, n):
    return 500 + 0.05 * (e - OX) + 5 * np.sin((n - OY) / 100.0)


@pytest.fixture(scope="module")
def dtm(tmp_path_factory) -> Raster:
    path = tmp_path_factory.mktemp("dtm") / "dtm.tif"
    x0, y1 = OX - W / 2, OY + H / 2
    cols, rows = np.meshgrid(np.arange(W) + 0.5, np.arange(H) + 0.5)
    z = _z(x0 + cols, y1 - rows).astype(np.float32)
    with rasterio.open(path, "w", driver="GTiff", width=W, height=H, count=1, dtype="float32",
                       crs="EPSG:2154", transform=from_origin(x0, y1, 1.0, 1.0)) as dst:  # fmt: skip
        dst.write(z, 1)
    return Raster(path)


@pytest.fixture(scope="module")
def tiles(dtm):
    frame = Frame(OX, OY)
    x = np.arange(-1100.0, 1100.0, 2.0)
    centre = np.column_stack([x, 30 * np.sin(x / 300.0)])  # stage frame (X east, Y south)
    e, n = frame.to_proj(centre[:, 0], centre[:, 1])
    road_z = _z(e, n)
    return build_tiles(
        dtm, frame, centre, 3.0, "asphalt", road_z=road_z, crossfall=np.zeros(len(x)), verbose=False, zones=ZONES_LIGHT
    ), road_z


def test_tiles_share_edge_vertices(tiles):
    ts, _ = tiles
    by_key = {(t.ix, t.iy): t.positions for t in ts}
    checked = 0
    for (ix, iy), v in by_key.items():
        for dx, dy in ((1, 0), (0, 1)):
            w = by_key.get((ix + dx, iy + dy))
            if w is None:
                continue
            ax, line = (0, (ix + 1) * TILE) if dx else (1, (iy + 1) * TILE)
            a = {tuple(np.round(p, 3)) for p in v[np.isclose(v[:, ax], line)]}
            b = {tuple(np.round(p, 3)) for p in w[np.isclose(w[:, ax], line)]}
            assert a == b, f"crack between tiles {(ix, iy)} and {(ix + dx, iy + dy)}"
            checked += 1
    assert checked > 0


def test_faces_point_up_and_road_is_tagged(tiles):
    ts, _ = tiles
    road = 0
    for t in ts:
        q = np.column_stack([t.positions[:, 0], -t.positions[:, 1], t.positions[:, 2]])  # right-handed E, N, U
        for name, tri in t.materials.items():
            if len(tri) == 0:
                continue
            n = np.cross(q[tri[:, 1]] - q[tri[:, 0]], q[tri[:, 2]] - q[tri[:, 0]])
            assert (n[:, 2] > 0).all(), f"downward faces in {name}"
            road += len(tri) if name == "road_asphalt" else 0
    assert road > 0


def test_road_vertices_on_deck(tiles):
    ts, _ = tiles
    for t in ts:
        tri = t.materials.get("road_asphalt")
        if tri is None or len(tri) == 0:
            continue
        p = t.positions[np.unique(tri)]
        e, n = p[:, 0] + OX, OY - p[:, 1]
        # flat crossfall: the deck equals the terrain only where the plane is level across, so compare loosely
        assert np.median(np.abs(p[:, 2] - _z(e, n))) < 0.2


def test_glb_roundtrip(tmp_path):
    pos = np.array([[0, 0, 0], [1, 0, 0], [0, 0, 1], [1, 0, 1]], dtype=float)
    tris = {"a": np.array([[0, 1, 2]]), "b": np.array([[1, 3, 2]]), "empty": np.zeros((0, 3), int)}
    out = tmp_path / "t.glb"
    write_glb(out, pos, None, None, tris, mesh_name="collision")
    data = out.read_bytes()
    magic, version, length = struct.unpack("<4sII", data[:12])
    assert (magic, version, length) == (b"glTF", 2, len(data))
    n = struct.unpack("<I", data[12:16])[0]
    gltf = json.loads(data[20 : 20 + n])
    prims = gltf["meshes"][0]["primitives"]
    assert gltf["meshes"][0]["name"] == "collision"
    assert [gltf["materials"][p["material"]]["name"] for p in prims] == ["a", "b"]  # empty one dropped
    assert all(list(p["attributes"]) == ["POSITION"] for p in prims)


def test_bridge_profile_fills_dip():
    s = np.arange(0, 200, 2.0)
    z = 100 + 0.03 * s
    z[(s > 90) & (s < 110)] -= 8.0  # bare-earth gap under a bridge
    zf, spans = _bridge_profile(s, z)
    assert len(spans) == 1
    assert spans[0]["depth_m"] == pytest.approx(8.0, abs=0.5)
    assert np.abs(np.diff(zf) / np.diff(s)).max() < 0.1
