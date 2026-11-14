"""Menu images for a stage package: top-down route map and elevation profile (transparent PNG)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


def map_small(path: Path, xy: np.ndarray, px: int = 512) -> None:
    """xy: stage frame (X east, Y south). Drawn north-up."""
    fig = plt.figure(figsize=(1, 1), dpi=px)
    ax = fig.add_axes((0.06, 0.06, 0.88, 0.88))
    x, y = xy[:, 0], -xy[:, 1]
    ax.plot(x, y, color="black", lw=2.6, solid_capstyle="round")
    ax.plot(x, y, color="white", lw=1.4, solid_capstyle="round")
    ax.plot(x[0], y[0], "o", ms=3.5, mfc="#2ca02c", mec="black", mew=0.5)
    ax.plot(x[-1], y[-1], "o", ms=3.5, mfc="#d62728", mec="black", mew=0.5)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.savefig(path, transparent=True)
    plt.close(fig)


def elevation(path: Path, s: np.ndarray, z: np.ndarray, size: tuple[int, int] = (1024, 256)) -> None:
    w, h = size
    fig = plt.figure(figsize=(w / 100, h / 100), dpi=100)
    ax = fig.add_axes((0.0, 0.0, 1.0, 1.0))
    lo = z.min() - 0.1 * (z.max() - z.min())
    ax.fill_between(s / 1000, z, lo, color="white", alpha=0.35, lw=0)
    ax.plot(s / 1000, z, color="white", lw=2)
    ax.set_xlim(0, s[-1] / 1000)
    ax.set_ylim(lo, z.max() + 0.05 * (z.max() - z.min()))
    ax.axis("off")
    fig.savefig(path, transparent=True)
    plt.close(fig)
