"""Occupancy grids derived from continuous environments.

Rasterization is *conservative*: a cell is marked occupied if any part of the
square cell, grown by the robot radius, touches an obstacle. Consequently, a
polyline through the centers of free, adjacent cells is collision-free in the
continuous world as well, so grid planners and sampling-based planners can be
compared on equal footing.
"""

from __future__ import annotations

import base64
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
from numpy.typing import NDArray

from .geometry import Circle, FloatArray, Point

if TYPE_CHECKING:
    from .environment import Environment

Cell = tuple[int, int]

SQRT2 = math.sqrt(2.0)


@dataclass(frozen=True, eq=False)
class OccupancyGrid:
    """A boolean occupancy grid.

    Attributes:
        origin: World coordinates of the lower-left corner of cell ``(0, 0)``.
        resolution: Side length of a cell in world units.
        occupied: Array of shape ``(nx, ny)``; ``occupied[i, j]`` refers to the
            cell in column ``i`` (x) and row ``j`` (y).
    """

    origin: Point
    resolution: float
    occupied: NDArray[np.bool_]

    @property
    def nx(self) -> int:
        return int(self.occupied.shape[0])

    @property
    def ny(self) -> int:
        return int(self.occupied.shape[1])

    @property
    def shape(self) -> tuple[int, int]:
        return (self.nx, self.ny)

    def blocked_bytes(self) -> bytes:
        """Occupancy flattened as ``index = i * ny + j`` (fast pure-Python lookups)."""
        return self.occupied.astype(np.uint8).tobytes(order="C")

    # ------------------------------------------------------------------ coordinates

    def cell_of(self, p: Point) -> Cell | None:
        """Cell containing world point ``p`` (``None`` if outside the grid)."""
        i = math.floor((p[0] - self.origin[0]) / self.resolution)
        j = math.floor((p[1] - self.origin[1]) / self.resolution)
        if 0 <= i < self.nx and 0 <= j < self.ny:
            return (i, j)
        return None

    def center(self, i: int, j: int) -> Point:
        return (
            self.origin[0] + (i + 0.5) * self.resolution,
            self.origin[1] + (j + 0.5) * self.resolution,
        )

    def is_free(self, cell: Cell) -> bool:
        i, j = cell
        return 0 <= i < self.nx and 0 <= j < self.ny and not bool(self.occupied[i, j])

    # ------------------------------------------------------------------ line of sight

    def line_of_sight(self, a: Cell, b: Cell) -> bool:
        """Whether the segment between the centers of cells ``a`` and ``b`` only crosses free cells.

        Uses an exact grid traversal (Amanatides & Woo). When the segment passes
        exactly through a cell corner, both side cells must be free, matching
        the "no corner cutting" rule of the 8-connected planners.
        """
        occ = self.occupied
        i, j = a
        i1, j1 = b
        if occ[i, j] or occ[i1, j1]:
            return False
        di, dj = i1 - i, j1 - j
        si = (di > 0) - (di < 0)
        sj = (dj > 0) - (dj < 0)
        adi, adj = abs(di), abs(dj)
        # Segment parameterized over t in [0, 1]; centers sit mid-cell, so the
        # first boundary in each axis is half a cell away.
        t_dx = 1.0 / adi if adi else math.inf
        t_dy = 1.0 / adj if adj else math.inf
        t_mx = 0.5 * t_dx
        t_my = 0.5 * t_dy
        eps = 1e-9
        for _ in range(adi + adj + 1):
            if i == i1 and j == j1:
                return True
            if abs(t_mx - t_my) < eps:
                if occ[i + si, j] or occ[i, j + sj]:
                    return False
                i += si
                j += sj
                t_mx += t_dx
                t_my += t_dy
            elif t_mx < t_my:
                i += si
                t_mx += t_dx
            else:
                j += sj
                t_my += t_dy
            if (i - i1) * si > 0 or (j - j1) * sj > 0:
                return False  # overshot the target (numerical drift); be conservative
            if occ[i, j]:
                return False
        return i == i1 and j == j1

    # ------------------------------------------------------------------ serialization

    def to_dict(self) -> dict[str, Any]:
        """JSON form; occupancy is base64-encoded ``uint8`` in row-major order ``j * nx + i``."""
        data = np.ascontiguousarray(self.occupied.T.astype(np.uint8))
        return {
            "origin": list(self.origin),
            "resolution": self.resolution,
            "shape": [self.nx, self.ny],
            "occupancy": base64.b64encode(data.tobytes()).decode("ascii"),
        }

    # ------------------------------------------------------------------ construction

    @classmethod
    def from_environment(cls, env: Environment, resolution: float | None = None) -> OccupancyGrid:
        from .environment import MAX_GRID_CELLS

        res = float(resolution or env.resolution)
        xmin, ymin, xmax, ymax = env.bounds
        nx = max(1, math.ceil((xmax - xmin) / res - 1e-9))
        ny = max(1, math.ceil((ymax - ymin) / res - 1e-9))
        if nx * ny > MAX_GRID_CELLS:
            raise ValueError(
                f"grid of {nx}x{ny} cells exceeds the limit of {MAX_GRID_CELLS}; "
                "increase the resolution (cell size)"
            )
        r = env.robot_radius
        h = res / 2.0
        cx = xmin + (np.arange(nx) + 0.5) * res
        cy = ymin + (np.arange(ny) + 0.5) * res

        occ = np.zeros((nx, ny), dtype=bool)
        # The robot center must stay at least r away from the walls.
        occ |= ((cx < xmin + r) | (cx > xmax - r))[:, None]
        occ |= ((cy < ymin + r) | (cy > ymax - r))[None, :]

        def index_range(lo: float, hi: float, origin: float, n: int) -> tuple[int, int]:
            first = max(0, math.ceil((lo - origin) / res - 0.5 - 1e-9))
            last = min(n - 1, math.floor((hi - origin) / res - 0.5 + 1e-9))
            return first, last + 1

        for shape in env.obstacles:
            bx0, by0, bx1, by1 = shape.bbox()
            grow = h + r
            i0, i1 = index_range(bx0 - grow, bx1 + grow, xmin, nx)
            j0, j1 = index_range(by0 - grow, by1 + grow, ymin, ny)
            if i0 >= i1 or j0 >= j1:
                continue
            gx, gy = np.meshgrid(cx[i0:i1], cy[j0:j1], indexing="ij")
            if isinstance(shape, Circle):
                dx = np.maximum(np.abs(gx - shape.center[0]) - h, 0.0)
                dy = np.maximum(np.abs(gy - shape.center[1]) - h, 0.0)
                hit = np.hypot(dx, dy) <= shape.radius + r
            else:
                hit = _polygon_hits_boxes(shape.vertices(), gx.ravel(), gy.ravel(), grow)
                hit = hit.reshape(gx.shape)
            occ[i0:i1, j0:j1] |= hit
        return cls(origin=(xmin, ymin), resolution=res, occupied=occ)


def _polygon_hits_boxes(
    verts: FloatArray, cx: FloatArray, cy: FloatArray, half: float
) -> NDArray[np.bool_]:
    """Whether the polygon intersects axis-aligned boxes centered at ``(cx, cy)``."""
    a = verts
    b = np.roll(verts, -1, axis=0)
    # Box center inside polygon (covers boxes fully inside the polygon).
    ax, ay = a[None, :, 0], a[None, :, 1]
    bx, by = b[None, :, 0], b[None, :, 1]
    px, py = cx[:, None], cy[:, None]
    straddles = (ay > py) != (by > py)
    dy = np.where(straddles, by - ay, 1.0)
    x_cross = ax + (bx - ax) * (py - ay) / dy
    inside = np.count_nonzero(straddles & (px < x_cross), axis=1) % 2 == 1

    # Any polygon edge intersecting a box (Liang-Barsky clipping).
    ddx = bx - ax
    ddy = by - ay
    t0 = np.zeros((len(cx), len(a)))
    t1 = np.ones((len(cx), len(a)))
    ok = np.ones((len(cx), len(a)), dtype=bool)
    for p, q in (
        (-ddx, ax - (px - half)),
        (ddx, (px + half) - ax),
        (-ddy, ay - (py - half)),
        (ddy, (py + half) - ay),
    ):
        p = np.broadcast_to(p, t0.shape)
        q = np.broadcast_to(q, t0.shape)
        parallel = p == 0
        ok &= ~(parallel & (q < 0))
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(parallel, 0.0, q / np.where(parallel, 1.0, p))
        t0 = np.where(~parallel & (p < 0), np.maximum(t0, ratio), t0)
        t1 = np.where(~parallel & (p > 0), np.minimum(t1, ratio), t1)
    edge_hit = np.any(ok & (t0 <= t1), axis=1)
    return np.asarray(inside | edge_hit)
