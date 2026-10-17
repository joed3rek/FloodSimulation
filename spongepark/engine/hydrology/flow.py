"""Terrain flow analysis on a DEM: sink filling, D8 flow, accumulation, outlets, watersheds.

Water is assumed to leave the modelled domain wherever flow reaches its edge. For a park with a
compound wall this is optimistic: real exits are gates, wall openings and drain inlets, which must
be confirmed (``outlet_points`` lets the designer pin them).
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

# D8 neighbours (dr, dc) and their distances in cells
D8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
DIST = np.array([np.hypot(dr, dc) for dr, dc in D8])
OUT = -1  # flows out of the domain
NONE = -2  # outside the domain


def _edge_cells(mask: np.ndarray) -> np.ndarray:
    nr, nc = mask.shape
    pad = np.pad(mask, 1, constant_values=False)
    inner = np.ones_like(mask)
    for dr, dc in D8:
        inner &= pad[1 + dr:1 + dr + nr, 1 + dc:1 + dc + nc]
    return mask & ~inner


def fill_sinks(z: np.ndarray, mask: np.ndarray, eps: float = 1e-5, sinks: Optional[np.ndarray] = None) -> np.ndarray:
    """Priority-flood fill (Barnes et al. 2014) with a small gradient so flats drain.

    ``sinks``: cells that take water out of the surface (e.g. NbS elements); they are not filled."""
    nr, nc = z.shape
    filled = np.where(mask, z, np.nan).astype(float)
    done = ~mask.copy()
    heap: List[Tuple[float, int, int]] = []
    seeds = _edge_cells(mask) if sinks is None else (_edge_cells(mask) | (sinks & mask))
    for r, c in zip(*np.nonzero(seeds)):
        heapq.heappush(heap, (filled[r, c], r, c))
        done[r, c] = True
    while heap:
        h, r, c = heapq.heappop(heap)
        for dr, dc in D8:
            rr, cc = r + dr, c + dc
            if 0 <= rr < nr and 0 <= cc < nc and not done[rr, cc]:
                done[rr, cc] = True
                if filled[rr, cc] <= h:
                    filled[rr, cc] = h + eps
                heapq.heappush(heap, (filled[rr, cc], rr, cc))
    return filled


def d8_directions(filled: np.ndarray, mask: np.ndarray, sinks: Optional[np.ndarray] = None) -> np.ndarray:
    """Index (0-7) of the steepest downhill neighbour; OUT at the edge when nothing is lower, and
    always OUT on ``sinks``."""
    nr, nc = filled.shape
    pad = np.pad(np.where(mask, filled, np.inf), 1, constant_values=np.inf)
    drops = np.full((8, nr, nc), -np.inf)
    for k, (dr, dc) in enumerate(D8):
        nb = pad[1 + dr:1 + dr + nr, 1 + dc:1 + dc + nc]
        d = (filled - nb) / DIST[k]
        drops[k] = np.where(np.isfinite(nb), d, -np.inf)
    best = np.argmax(drops, axis=0)
    has = np.take_along_axis(drops, best[None], 0)[0] > 0
    out = np.where(has, best, OUT)
    if sinks is not None:
        out[sinks & mask] = OUT
    out[~mask] = NONE
    # interior cells with no lower neighbour cannot exist after filling; edge cells drain out
    return out


def downstream(dirs: np.ndarray) -> np.ndarray:
    """Flat index of each cell's receiver; -1 if it drains out, -2 outside."""
    nr, nc = dirs.shape
    rows, cols = np.indices(dirs.shape)
    rec = np.full(dirs.shape, -1, dtype=np.int64)
    for k, (dr, dc) in enumerate(D8):
        m = dirs == k
        rec[m] = (rows[m] + dr) * nc + (cols[m] + dc)
    rec[dirs == NONE] = -2
    return rec


def _order(filled: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Flat indices of domain cells from highest to lowest (upstream first)."""
    idx = np.flatnonzero(mask)
    return idx[np.argsort(-filled.ravel()[idx], kind="stable")]


def accumulation(filled: np.ndarray, mask: np.ndarray, dirs: np.ndarray,
                 weight: Optional[np.ndarray] = None) -> np.ndarray:
    """Number of cells (or sum of ``weight``) draining through each cell, itself included."""
    rec = downstream(dirs).ravel()
    acc = np.where(mask, 1.0 if weight is None else weight, 0.0).astype(float).ravel()
    for i in _order(filled, mask):
        j = rec[i]
        if j >= 0:
            acc[j] += acc[i]
    return acc.reshape(filled.shape)


def outlet_of(filled: np.ndarray, mask: np.ndarray, dirs: np.ndarray) -> np.ndarray:
    """Flat index of the domain-exit cell each cell drains to (-2 outside the domain)."""
    rec = downstream(dirs).ravel()
    out = np.full(rec.shape, -2, dtype=np.int64)
    for i in _order(filled, mask)[::-1]:  # lowest first: receivers resolved before donors
        j = rec[i]
        out[i] = i if j == -1 else out[j]
    return out.reshape(filled.shape)


def flow_length(filled: np.ndarray, mask: np.ndarray, dirs: np.ndarray, cell: float) -> np.ndarray:
    """Distance along the D8 path from each cell to where it leaves the domain (m)."""
    rec = downstream(dirs).ravel()
    d = dirs.ravel()
    L = np.zeros(rec.shape)
    for i in _order(filled, mask)[::-1]:
        j = rec[i]
        if j >= 0:
            L[i] = L[j] + DIST[d[i]] * cell
        elif j == -1:
            L[i] = 0.5 * cell
    return L.reshape(filled.shape)


@dataclass
class Depression:
    id: int
    area_m2: float
    max_depth_m: float
    volume_m3: float
    centroid: Tuple[float, float]


def reaches(filled: np.ndarray, mask: np.ndarray, dirs: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Cells whose flow path passes through ``target`` (target cells included)."""
    rec = downstream(dirs).ravel()
    t = target.ravel()
    hit = np.zeros(rec.shape, bool)
    for i in _order(filled, mask)[::-1]:  # receivers first
        j = rec[i]
        hit[i] = t[i] or (j >= 0 and hit[j])
    return hit.reshape(filled.shape)


def depressions(z: np.ndarray, filled: np.ndarray, mask: np.ndarray, cell: float, X: np.ndarray, Y: np.ndarray,
                min_depth_m: float = 0.02) -> Tuple[List[Depression], np.ndarray]:
    """Connected areas where filling raised the surface by at least ``min_depth_m`` (natural ponding)."""
    from scipy import ndimage

    depth = np.where(mask, filled - z, 0.0)
    wet = depth >= min_depth_m
    lab, n = ndimage.label(wet, structure=np.ones((3, 3)))
    out = []
    for k in range(1, n + 1):
        m = lab == k
        out.append(Depression(k, float(m.sum() * cell ** 2), float(depth[m].max()),
                              float(depth[m].sum() * cell ** 2), (float(X[m].mean()), float(Y[m].mean()))))
    return out, np.where(wet, depth, 0.0)


def group_outlets(out_cell: np.ndarray, mask: np.ndarray, cell: float, min_area_m2: float) -> np.ndarray:
    """Label image of drainage areas, one per exit, with exits adjacent along the edge merged and
    drainage areas smaller than ``min_area_m2`` absorbed into the neighbour they share most border with."""
    from scipy import ndimage

    nr, nc = mask.shape
    exits = np.zeros(mask.shape, bool)
    flat = out_cell[mask]
    exits.ravel()[np.unique(flat[flat >= 0])] = True
    ex_lab, n = ndimage.label(exits, structure=np.ones((3, 3)))
    lab = np.zeros(mask.shape, np.int64)
    lab[mask] = ex_lab.ravel()[out_cell[mask]]
    min_cells = min_area_m2 / cell ** 2
    for _ in range(50):
        ids, counts = np.unique(lab[mask], return_counts=True)
        small = [i for i, c in zip(ids, counts) if c < min_cells]
        if not small or len(ids) == 1:
            break
        changed = False
        for s in small:
            m = lab == s
            ring = ndimage.binary_dilation(m, structure=np.ones((3, 3))) & ~m & mask
            if not ring.any():
                continue
            nb, c = np.unique(lab[ring], return_counts=True)
            lab[m] = nb[np.argmax(c)]
            changed = True
        if not changed:
            break
    # renumber 1..k
    ids = np.unique(lab[mask])
    remap = {old: new for new, old in enumerate(ids, start=1)}
    out = np.zeros_like(lab)
    for old, new in remap.items():
        out[lab == old] = new
    return out
