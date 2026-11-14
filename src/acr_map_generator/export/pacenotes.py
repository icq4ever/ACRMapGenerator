"""Pace notes from the road geometry, in the Stage IR `pacenotes.tokens` format.

The builder (acr-extrastages, `stage-build --pacenote-map`) maps each token to an ACR pace-note row. It places the
corner's row and length from the built road itself, so a token only needs its kind, direction, severity and the
point where a co-driver would read it (`gate_distance`, on the IR's gate-distance scale).

Method:
- **Smoothing**: the LiDAR centreline is smoothed with a Gaussian of SMOOTH_M first. Its ±0.2 m lateral jitter otherwise
  shows up as extra "corners" (SS8 section: 155 corners raw, 97 at 8 m, 84 at 12 m, where short S-bends start to merge).
  The calibration below was made on a smooth driving spline, so this brings the input closer to it.
- **Corners**: on a 2 m resampling of the centreline, runs whose radius over a ±5 m window is below 140 m, with the
  same turn direction, merged across gaps under 10 m, and kept when they turn at least 20°. Direction comes from the
  heading change in plan (counter-clockwise from above = left).
- **Severity**: score = sqrt(turn in degrees) / minimum radius in m. Cut points calibrated against the stock calls
  of one Assetto Corsa Rally tarmac stage (50 corners: 46 % exact, 85 % within one step, mean bias −0.07 step).
  A radius-only rule called corners about one step too open. Hairpin: radius < 8 m and turn > 120°.
  Square: radius < 15 m and turn 60–120° (junctions).
- **Calls**: corners less than LINK m apart form one call (the builder says "into" / "and"), with at most MAX_LINKED
  corners and none starting more than CALL_REACH m past the read point: the builder walks a call's corners along the
  road, so long chains drift onto the wrong bends. A straight of 40 m or
  more after a call is added as a distance subcall. All subcalls of a call share the read point, LEAD m before its
  first corner. A finish token is read 50 m before the finish line.
"""

from __future__ import annotations

import math

import numpy as np

STEP_M = 2.0  # resampling
SMOOTH_M = 8.0  # Gaussian sigma (m along the road) applied to the centreline before measuring curvature
WINDOW_M = 5.0  # curvature window (± m)
MAX_RADIUS = 140.0  # corners: radius below this
MIN_TURN = 20.0  # degrees: smaller turns on the smoothed line are mostly residue, not corners
MERGE_GAP = 10.0  # m between same-direction runs to merge
SCORE_CUTS = [(0.33, "1"), (0.189, "2"), (0.107, "3"), (0.066, "4"), (0.052, "5")]  # else "6"
LEAD = 90.0  # m: read point before a call's first corner
LINK = 40.0  # m: corners closer than this form one call
MAX_LINKED = 4  # corners per call at most
CALL_REACH = 150.0  # m: a call ends before a corner that starts further than this past its read point
MIN_DISTANCE_CALL = 40.0  # m: shorter straights are not called
FINISH_LEAD = 50.0  # m


def _smooth(a: np.ndarray, sigma: float) -> np.ndarray:
    """Gaussian smoothing along axis 0 (sigma in samples), edge-padded so the ends stay put."""
    if sigma <= 0:
        return a
    r = int(np.ceil(3 * sigma))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    pad = np.pad(a, [(r, r), (0, 0)], mode="edge")
    return np.column_stack([np.convolve(pad[:, j], k, mode="valid") for j in range(a.shape[1])])


def severity(turn_deg: float, min_radius: float) -> str:
    turn = abs(turn_deg)
    if min_radius < 8 and turn > 120:
        return "hairpin"
    if min_radius < 15 and 60 <= turn <= 120:
        return "square"
    score = math.sqrt(turn) / max(min_radius, 1.0)
    return next((v for cut, v in SCORE_CUTS if score >= cut), "6")


def find_corners(plan: np.ndarray, s: np.ndarray, i0: int, i1: int) -> list[tuple[int, int, float, float]]:
    """plan: (n, 2) east/north points every STEP_M; s: distances. -> [(i_start, i_end, turn_deg, min_radius_m)]"""
    head = np.unwrap(np.arctan2(np.gradient(plan[:, 1]), np.gradient(plan[:, 0])))
    a = np.clip(np.searchsorted(s, s - WINDOW_M), 0, len(s) - 1)
    b = np.clip(np.searchsorted(s, s + WINDOW_M), 0, len(s) - 1)
    span = s[b] - s[a]
    k = np.where(span > 1, (head[b] - head[a]) / np.maximum(span, 1e-9), 0.0)  # curvature, + = left
    radius = np.where(np.abs(k) > 1e-6, 1 / np.maximum(np.abs(k), 1e-9), 1e9)
    curvy = radius < MAX_RADIUS

    runs, i = [], i0
    while i <= i1:
        if not curvy[i]:
            i += 1
            continue
        j, sign = i, np.sign(k[i])
        while j + 1 <= i1 and curvy[j + 1] and np.sign(k[j + 1]) == sign:
            j += 1
        runs.append([i, j, sign])
        i = j + 1
    merged: list[list] = []
    for r in runs:
        if merged and merged[-1][2] == r[2] and s[r[0]] - s[merged[-1][1]] < MERGE_GAP:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    out = []
    for i, j, _ in merged:
        turn = math.degrees(head[j] - head[i]) if j > i else math.degrees(k[i] * 10)
        if abs(turn) >= MIN_TURN:
            out.append((i, j, turn, float(radius[i : j + 1].min())))
    return out


def make_pacenotes(plan: np.ndarray, s: np.ndarray, start_m: float, finish_m: float, gate_origin_m: float) -> dict:
    """plan: (n, 2) centreline east/north; s: its distances (m along the stage).
    start_m / finish_m: the start and finish lines (m along the stage); gate_origin_m: the stage distance of gate 0,
    so that gate_distance = stage distance − gate_origin_m. Returns the IR `pacenotes` object."""
    t = np.arange(0.0, s[-1] + 1e-6, STEP_M)
    p = _smooth(np.column_stack([np.interp(t, s, plan[:, 0]), np.interp(t, s, plan[:, 1])]), SMOOTH_M / STEP_M)
    i0 = int(np.searchsorted(t, start_m))
    i1 = int(np.searchsorted(t, finish_m, side="right") - 1)
    corners = find_corners(p, t, i0, i1)

    groups: list[list] = []
    # The builder places a call's corners by walking the road from the read point, so long chains drift: one missed
    # or extra bend shifts every later subcall. Keep calls short and within reach of their read point.
    for c in corners:
        g = groups[-1] if groups else None
        if g and t[c[0]] - t[g[-1][1]] < LINK and len(g) < MAX_LINKED and t[c[0]] - (t[g[0][0]] - LEAD) <= CALL_REACH:
            groups[-1].append(c)
        else:
            groups.append([c])

    def gate(d: float) -> float:
        return round(float(d - gate_origin_m), 2)

    tokens = []
    for gi, g in enumerate(groups):
        read = max(t[g[0][0]] - LEAD, start_m)
        base = {
            "call": gi + 1,
            "gate_distance": gate(read),
            "distance_m": round(float(read - start_m), 1),
            "modifiers": [],
        }
        sub = 0
        for i, j, turn, rmin in g:
            sub += 1
            tokens.append(
                {
                    **base,
                    "subcall": sub,
                    "kind": "corner",
                    "direction": "left" if turn > 0 else "right",
                    "severity": severity(turn, rmin),
                    "angle": int(round(abs(turn))),
                    "corner_start_m": round(float(t[i] - start_m), 1),
                    "corner_end_m": round(float(t[j] - start_m), 1),
                    "min_radius_m": round(rmin, 1),
                }
            )
        if gi + 1 < len(groups):
            gap = t[groups[gi + 1][0][0]] - t[g[-1][1]]
            if gap >= MIN_DISTANCE_CALL:
                sub += 1
                tokens.append(
                    {**base, "subcall": sub, "kind": "distance", "distance_call_m": float(round(gap / 10) * 10)}
                )
    fin = finish_m - FINISH_LEAD
    tokens.append(
        {"call": len(groups) + 1, "subcall": 1, "kind": "finish", "gate_distance": gate(fin),
         "distance_m": round(float(fin - start_m), 1), "modifiers": []}
    )  # fmt: skip
    return {
        "source": "geometry (acr-map-generator, LiDAR centreline)",
        "distance_origin": "start_line",
        "start_gate_distance": gate(start_m),
        "finish_call_distance_m": round(float(fin - start_m), 1),
        "tokens": tokens,
        "raw": [],
    }


def summary(p: dict) -> str:
    kinds: dict[str, int] = {}
    for tok in p["tokens"]:
        key = f"{tok['direction']}{tok['severity']}" if tok["kind"] == "corner" else tok["kind"]
        kinds[key] = kinds.get(key, 0) + 1
    calls = len({tok["call"] for tok in p["tokens"]})
    linked = sum(1 for tok in p["tokens"] if tok["kind"] == "corner" and tok["subcall"] > 1)
    corners = sum(1 for tok in p["tokens"] if tok["kind"] == "corner")
    return f"{len(p['tokens'])} tokens in {calls} calls: {corners} corners ({linked} linked), {kinds.get('distance', 0)} distances"
