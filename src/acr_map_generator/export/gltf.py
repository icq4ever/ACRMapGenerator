"""Minimal binary glTF 2.0 (.glb) writer: one mesh, shared vertex attributes, one primitive per material."""

from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

FLOAT, UINT32 = 5126, 5125
ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER = 34962, 34963


def write_glb(
    path: Path,
    positions: np.ndarray,  # (n, 3) float, glTF frame (Y-up, metres)
    normals: np.ndarray | None,  # (n, 3) float, unit; None = positions only
    uvs: np.ndarray | None,  # (n, 2) float; None = none
    primitives: dict[str, np.ndarray],  # material name -> (m, 3) uint32 triangle indices
    mesh_name: str = "mesh",
) -> None:
    blobs: list[bytes] = []
    views: list[dict] = []
    accessors: list[dict] = []
    offset = 0

    def add(arr: np.ndarray, target: int, acc: dict) -> int:
        nonlocal offset
        data = arr.tobytes()
        pad = (-len(data)) % 4
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(data), "target": target})
        blobs.append(data + b"\0" * pad)
        offset += len(data) + pad
        accessors.append({"bufferView": len(views) - 1, **acc})
        return len(accessors) - 1

    pos = positions.astype(np.float32)
    a_pos = add(
        pos,
        ARRAY_BUFFER,
        {
            "componentType": FLOAT,
            "count": len(pos),
            "type": "VEC3",
            "min": pos.min(axis=0).tolist(),
            "max": pos.max(axis=0).tolist(),
        },
    )
    attrs = {"POSITION": a_pos}
    if normals is not None:
        attrs["NORMAL"] = add(
            normals.astype(np.float32), ARRAY_BUFFER, {"componentType": FLOAT, "count": len(pos), "type": "VEC3"}
        )
    if uvs is not None:
        attrs["TEXCOORD_0"] = add(
            uvs.astype(np.float32), ARRAY_BUFFER, {"componentType": FLOAT, "count": len(pos), "type": "VEC2"}
        )

    materials, prims = [], []
    for name, tris in primitives.items():
        if len(tris) == 0:
            continue
        idx = tris.astype(np.uint32).ravel()
        a_idx = add(
            idx,
            ELEMENT_ARRAY_BUFFER,
            {
                "componentType": UINT32,
                "count": len(idx),
                "type": "SCALAR",
                "min": [int(idx.min())],
                "max": [int(idx.max())],
            },
        )
        materials.append({"name": name, "pbrMetallicRoughness": {"metallicFactor": 0.0, "roughnessFactor": 1.0}})
        prims.append(
            {
                "attributes": dict(attrs),
                "indices": a_idx,
                "material": len(materials) - 1,
                "mode": 4,
            }
        )

    gltf = {
        "asset": {"version": "2.0", "generator": "acr-map-generator"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": mesh_name, "mesh": 0}],
        "meshes": [{"name": mesh_name, "primitives": prims}],
        "materials": materials,
        "buffers": [{"byteLength": offset}],
        "bufferViews": views,
        "accessors": accessors,
    }
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * ((-len(js)) % 4)
    bin_ = b"".join(blobs)
    total = 12 + 8 + len(js) + 8 + len(bin_)
    with open(path, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, total))
        f.write(struct.pack("<I4s", len(js), b"JSON") + js)
        f.write(struct.pack("<I4s", len(bin_), b"BIN\0") + bin_)
