"""BC1 (DXT1) DDS writer with a full mip chain, numpy only.

The encoder fits each 4x4 block's colours to a line (principal axis), takes the extreme projections as the two
endpoints, quantises them to RGB565 and picks the nearest of the four palette colours per pixel. Good enough for
photographic ground colour; the builder reads the legacy "DXT1" FourCC as sRGB BC1.
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np


def mip_chain(img: np.ndarray) -> list[np.ndarray]:
    """img (H x W x 3 uint8, square power of two) and its 2x2 box-filtered mips down to 1 x 1."""
    h, w = img.shape[:2]
    if h != w or h & (h - 1):
        raise ValueError(f"mips need a square power-of-two image, got {w} x {h}")
    mips = [img]
    cur = img.astype(np.float32)
    while cur.shape[0] > 1:
        cur = cur.reshape(cur.shape[0] // 2, 2, cur.shape[1] // 2, 2, 3).mean(axis=(1, 3))
        mips.append(np.clip(np.rint(cur), 0, 255).astype(np.uint8))
    return mips


def _to565(c: np.ndarray) -> np.ndarray:
    r = np.rint(c[..., 0] * 31 / 255).astype(np.uint32)
    g = np.rint(c[..., 1] * 63 / 255).astype(np.uint32)
    b = np.rint(c[..., 2] * 31 / 255).astype(np.uint32)
    return (r << 11) | (g << 5) | b


def _from565(v: np.ndarray) -> np.ndarray:
    r, g, b = (v >> 11) & 31, (v >> 5) & 63, v & 31
    return np.stack([(r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)], axis=-1).astype(np.float32)


def encode_bc1(img: np.ndarray) -> bytes:
    """BC1 blocks (row-major) of an H x W x 3 uint8 image; sides below 4 are padded by edge repetition."""
    h, w = img.shape[:2]
    ph, pw = max(4, (h + 3) // 4 * 4), max(4, (w + 3) // 4 * 4)
    if (ph, pw) != (h, w):
        img = np.pad(img, ((0, ph - h), (0, pw - w), (0, 0)), mode="edge")
    bh, bw = ph // 4, pw // 4
    px = img.reshape(bh, 4, bw, 4, 3).transpose(0, 2, 1, 3, 4).reshape(-1, 16, 3).astype(np.float32)
    mean = px.mean(axis=1, keepdims=True)
    d = px - mean
    cov = np.einsum("bki,bkj->bij", d, d)
    axis = np.ones((len(px), 3), np.float32) / np.sqrt(3)
    for _ in range(6):  # power iteration
        axis = np.einsum("bij,bj->bi", cov, axis)
        norm = np.linalg.norm(axis, axis=1, keepdims=True)
        axis = np.where(norm > 1e-6, axis / np.maximum(norm, 1e-12), np.ones_like(axis) / np.sqrt(3))
    t = np.einsum("bki,bi->bk", d, axis)
    c0 = np.clip(mean[:, 0] + axis * t.max(axis=1, keepdims=True), 0, 255)
    c1 = np.clip(mean[:, 0] + axis * t.min(axis=1, keepdims=True), 0, 255)
    e0, e1 = _to565(c0), _to565(c1)
    swap = e0 < e1
    e0, e1 = np.where(swap, e1, e0), np.where(swap, e0, e1)
    p0, p1 = _from565(e0), _from565(e1)
    pal = np.stack([p0, p1, (2 * p0 + p1) / 3, (p0 + 2 * p1) / 3], axis=1)  # 4-colour mode (e0 > e1)
    idx = ((px[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(axis=-1).argmin(axis=-1).astype(np.uint32)
    idx[e0 == e1] = 0  # flat block: e0 == e1 selects 3-colour mode, index 0 is still colour 0
    bits = (idx << (2 * np.arange(16, dtype=np.uint32))).sum(axis=1, dtype=np.uint64).astype(np.uint32)
    out = np.empty(len(px), dtype=[("c0", "<u2"), ("c1", "<u2"), ("idx", "<u4")])
    out["c0"], out["c1"], out["idx"] = e0, e1, bits
    return out.tobytes()


def decode_bc1(data: bytes, w: int, h: int) -> np.ndarray:
    """H x W x 3 uint8 from BC1 blocks (4-colour mode only, as written by encode_bc1); for tests and previews."""
    bh, bw = max(1, (h + 3) // 4), max(1, (w + 3) // 4)
    blk = np.frombuffer(data, dtype=[("c0", "<u2"), ("c1", "<u2"), ("idx", "<u4")], count=bh * bw)
    e0, e1 = blk["c0"].astype(np.uint32), blk["c1"].astype(np.uint32)
    p0, p1 = _from565(e0), _from565(e1)
    pal = np.stack([p0, p1, (2 * p0 + p1) / 3, (p0 + 2 * p1) / 3], axis=1)
    idx = (blk["idx"][:, None] >> (2 * np.arange(16, dtype=np.uint32))) & 3
    px = np.take_along_axis(pal, idx[:, :, None].astype(np.int64), axis=1)
    img = px.reshape(bh, bw, 4, 4, 3).transpose(0, 2, 1, 3, 4).reshape(bh * 4, bw * 4, 3)
    return np.clip(np.rint(img[:h, :w]), 0, 255).astype(np.uint8)


def write_bc1_dds(path: Path, img: np.ndarray) -> int:
    """BC1 DDS with the full mip chain (legacy header, FourCC DXT1). Returns the file size in bytes."""
    mips = mip_chain(img)
    blobs = [encode_bc1(m) for m in mips]
    h, w = img.shape[:2]
    flags = 0x1 | 0x2 | 0x4 | 0x1000 | 0x20000 | 0x80000  # caps, height, width, pixelformat, mipmapcount, linearsize
    header = struct.pack(
        "<4s7I44x8I5I",
        b"DDS ",
        124,
        flags,
        h,
        w,
        len(blobs[0]),
        0,
        len(mips),
        32,  # pixel format: size
        0x4,  # DDPF_FOURCC
        int.from_bytes(b"DXT1", "little"),
        0,
        0,
        0,
        0,
        0,
        0x401008,  # caps: complex, texture, mipmap
        0,
        0,
        0,
        0,
    )
    data = header + b"".join(blobs)
    path.write_bytes(data)
    return len(data)
