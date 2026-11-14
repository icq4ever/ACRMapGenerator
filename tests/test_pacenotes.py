"""Pace notes on synthetic roads: corners found, direction and severity, robust to centreline jitter."""

import numpy as np

from acr_map_generator.export.pacenotes import make_pacenotes, severity


def _road(segments, step=0.5):
    """segments: [("straight", length) | ("arc", radius, degrees_left_positive)] -> (plan points, distances)"""
    pts, h = [np.zeros(2)], 0.0
    for seg in segments:
        if seg[0] == "straight":
            for _ in range(int(seg[1] / step)):
                pts.append(pts[-1] + step * np.array([np.cos(h), np.sin(h)]))
        else:
            r, deg = seg[1], seg[2]
            n = int(abs(np.radians(deg)) * r / step)
            dh = np.radians(deg) / n
            for _ in range(n):
                h += dh
                pts.append(pts[-1] + step * np.array([np.cos(h), np.sin(h)]))
    p = np.array(pts)
    return p, np.r_[0, np.cumsum(np.hypot(*np.diff(p, axis=0).T))]


ROAD = [("straight", 300), ("arc", 40, 90), ("straight", 250), ("arc", 6, -170), ("straight", 300)]


def _corners(p, s):
    pn = make_pacenotes(p, s, 100.0, s[-1] - 100.0, 0.0)
    return [t for t in pn["tokens"] if t["kind"] == "corner"], pn


def test_two_corners_direction_and_severity():
    corners, pn = _corners(*_road(ROAD))
    assert [c["direction"] for c in corners] == ["left", "right"]
    assert corners[1]["severity"] == "hairpin"
    assert pn["tokens"][-1]["kind"] == "finish"
    # read points come before their corners, on the gate scale (origin 0 here)
    assert all(c["gate_distance"] <= 100 + c["corner_start_m"] for c in corners)


def test_jitter_adds_no_corners():
    p, s = _road(ROAD)
    rng = np.random.default_rng(1)
    noisy = p + rng.normal(0, 0.2, p.shape)  # LiDAR-like lateral jitter
    assert len(_corners(noisy, s)[0]) == len(_corners(p, s)[0])


def test_severity_scale():
    assert severity(90, 200) == "6"
    assert severity(90, 20) in {"2", "1"}
    assert severity(170, 6) == "hairpin"
    assert severity(90, 12) == "square"


def test_long_chains_are_split():
    # eight short S-bends 30 m apart: one call would drift, so they must be split
    segs = [("straight", 300)]
    for i in range(8):
        segs += [("arc", 30, 60 if i % 2 else -60), ("straight", 30)]
    segs += [("straight", 300)]
    p, s = _road(segs)
    corners, _ = _corners(p, s)
    per_call = {}
    for c in corners:
        per_call.setdefault(c["call"], []).append(c)
    assert len(corners) >= 6
    assert max(len(v) for v in per_call.values()) <= 4
