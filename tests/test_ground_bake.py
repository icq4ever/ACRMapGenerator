"""BC1/DDS writer and the imagery tile grid (no network)."""

import struct

import numpy as np

from acr_map_generator.export.dds import decode_bc1, encode_bc1, mip_chain, write_bc1_dds
from acr_map_generator.export.ground_bake import _ir_box, _tile_entry
from acr_map_generator.process.imagery import Tier, squares_near


def _photo(n: int = 64) -> np.ndarray:
    """Smooth colour gradients with some noise, like a photo."""
    y, x = np.mgrid[0:n, 0:n] / n
    rng = np.random.default_rng(1)
    img = np.stack([120 + 80 * x, 90 + 60 * y, 60 + 40 * np.sin(6 * x * y)], axis=-1) + rng.normal(0, 4, (n, n, 3))
    return np.clip(img, 0, 255).astype(np.uint8)


def test_bc1_round_trip_is_close():
    img = _photo()
    out = decode_bc1(encode_bc1(img), 64, 64)
    err = np.abs(out.astype(int) - img.astype(int))
    assert len(encode_bc1(img)) == (64 // 4) ** 2 * 8
    assert err.mean() < 4 and np.percentile(err, 99) < 16


def test_bc1_flat_and_tiny_blocks():
    flat = np.full((4, 4, 3), (10, 200, 30), np.uint8)
    out = decode_bc1(encode_bc1(flat), 4, 4)
    assert np.abs(out.astype(int) - flat.astype(int)).max() <= 4  # 565 quantisation
    assert len(encode_bc1(np.zeros((1, 1, 3), np.uint8))) == 8  # padded to one block


def test_dds_header_and_mips(tmp_path):
    img = _photo(64)
    size = write_bc1_dds(tmp_path / "t.dds", img)
    d = (tmp_path / "t.dds").read_bytes()
    assert len(d) == size and d[:4] == b"DDS "
    h, w, linear, _, mips = struct.unpack_from("<5I", d, 12)
    assert (h, w, linear, mips) == (64, 64, 16 * 16 * 8, 7)
    assert d[84:88] == b"DXT1"
    blocks = sum(max(1, s // 4) ** 2 for s in (64, 32, 16, 8, 4, 2, 1))
    assert len(d) == 128 + blocks * 8
    assert [m.shape[0] for m in mip_chain(img)] == [64, 32, 16, 8, 4, 2, 1]


def test_grid_squares_and_ir_bounds():
    tier = Tier("t", 1.0, 128, 4, 50.0)  # 128 m tiles on a 120 m grid
    assert tier.step == 120 and tier.bounds(0, 0) == (-4, -4, 124, 124)
    line = np.array([[10.0, 60.0], [230.0, 60.0]])  # along the first row of squares
    sq = squares_near(line, tier, 50.0)
    assert {(0, 0), (1, 0)} <= sq and (0, 1) not in sq  # (0, 1) starts 60 m north of the line
    assert sq == {(-1, 0), (0, 0), (1, 0), (2, 0)}  # the line ends 10 m from squares -1 and 2; none south
    # IR: x = E - ox, z = oy - N; the image's first row (north) is min_z
    box = _ir_box(tier.bounds(0, 0), ox=100.0, oy=200.0)
    assert box == {"min_x": -104, "min_z": 76, "max_x": 24, "max_z": 204}
    e = _tile_entry(tier, 0, 0, "t_0_0", 100.0, 200.0)
    assert e["size_m"] == box["max_x"] - box["min_x"] == box["max_z"] - box["min_z"]
    assert e["assign_bounds"] == {"min_x": -100, "min_z": 80, "max_x": 20, "max_z": 200}
