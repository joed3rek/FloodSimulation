"""Two-dimensional rain-on-grid surface flow (indicative).

SWMM is one-dimensional: it says how much water leaves, not where it spreads. This model shows
surface ponding and overflow routes on the DEM.

Scheme: local inertial approximation of the shallow water equations (Bates, Horritt & Fewtrell 2010;
de Almeida et al. 2012), on a regular grid, explicit, with an adaptive time step
``dt = alpha dx / sqrt(g h_max)``. Unit-width flows are kept on cell faces:

    q_new = (q - g h_f dt dEta/dx) / (1 + g dt n^2 |q| / h_f^(7/3))

where ``h_f`` is the flow depth at the face (highest water surface minus highest bed). Outgoing
flows are scaled down when a cell would empty below zero, so depths stay non-negative and volume is
conserved exactly. Edges of the domain are open (water leaves over a ghost cell 1 % lower).

Sources and sinks per cell: rainfall; constant-rate infiltration (soil zone rate); NbS element cells
pass surface water into the element's store until its capacity (SWMM element storage) is reached,
and the store empties at the element's infiltration rate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

try:
    from numba import njit
except ImportError:  # pragma: no cover - numba is a dependency; pure Python still works, slowly
    def njit(*a, **k):
        return (lambda f: f) if not a or not callable(a[0]) else a[0]

G = 9.81
INDICATIVE = "indicative: 2D surface model (local inertial), not calibrated; volumes compared with SWMM"


@njit(cache=True, nogil=True)
def _fluxes(z, h, mask, n2, qx, qy, dt, dx, edge_drop, theta):
    nr, nc = z.shape
    side = 0.5 * (1.0 - theta)   # de Almeida et al. 2012: a little of the neighbouring faces' flow damps the checkerboard
    was_x = qx.copy()
    was_y = qy.copy()
    # x faces: qx[r, c] between (r, c-1) and (r, c); positive towards +c
    for r in range(nr):
        for c in range(nc + 1):
            L = c - 1
            R = c
            inL = L >= 0 and mask[r, L]
            inR = R < nc and mask[r, R]
            if not inL and not inR:
                qx[r, c] = 0.0
                continue
            if inL:
                zl = z[r, L]
                hl = h[r, L]
            else:
                zl = z[r, R] - edge_drop
                hl = 0.0
            if inR:
                zr = z[r, R]
                hr = h[r, R]
            else:
                zr = z[r, L] - edge_drop
                hr = 0.0
            el = zl + hl
            er = zr + hr
            hf = max(el, er) - max(zl, zr)
            if hf <= 1e-4:
                qx[r, c] = 0.0
                continue
            nn = n2[r, L] if inL else n2[r, R]
            q = was_x[r, c]
            ql = was_x[r, c - 1] if c > 0 else q
            qr = was_x[r, c + 1] if c < nc else q
            damped = theta * q + side * (ql + qr) if inL and inR else q   # an edge does not borrow its neighbours' flow
            q = (damped - G * hf * dt * (er - el) / dx) / (1.0 + G * dt * nn * abs(q) / hf ** (7.0 / 3.0))
            if not inL and q > 0:
                q = 0.0  # no inflow from outside
            if not inR and q < 0:
                q = 0.0
            qx[r, c] = q
    # y faces: qy[r, c] between (r-1, c) and (r, c); positive towards +r
    for r in range(nr + 1):
        for c in range(nc):
            T = r - 1
            B = r
            inT = T >= 0 and mask[T, c]
            inB = B < nr and mask[B, c]
            if not inT and not inB:
                qy[r, c] = 0.0
                continue
            if inT:
                zt = z[T, c]
                ht = h[T, c]
            else:
                zt = z[B, c] - edge_drop
                ht = 0.0
            if inB:
                zb = z[B, c]
                hb = h[B, c]
            else:
                zb = z[T, c] - edge_drop
                hb = 0.0
            et = zt + ht
            eb = zb + hb
            hf = max(et, eb) - max(zt, zb)
            if hf <= 1e-4:
                qy[r, c] = 0.0
                continue
            nn = n2[T, c] if inT else n2[B, c]
            q = was_y[r, c]
            qt = was_y[r - 1, c] if r > 0 else q
            qb = was_y[r + 1, c] if r < nr else q
            damped = theta * q + side * (qt + qb) if inT and inB else q
            q = (damped - G * hf * dt * (eb - et) / dx) / (1.0 + G * dt * nn * abs(q) / hf ** (7.0 / 3.0))
            if not inT and q > 0:
                q = 0.0
            if not inB and q < 0:
                q = 0.0
            qy[r, c] = q


@njit(cache=True, nogil=True)
def _limit_and_update(h, mask, qx, qy, dt, dx):
    """Scale outgoing flows so no cell goes negative, then update depths. Returns volume out (m3)."""
    nr, nc = h.shape
    scale = np.ones((nr, nc))
    for r in range(nr):
        for c in range(nc):
            if not mask[r, c]:
                continue
            out = max(qx[r, c + 1], 0.0) + max(-qx[r, c], 0.0) + max(qy[r + 1, c], 0.0) + max(-qy[r, c], 0.0)
            v_out = out * dt / dx  # depth leaving (m)
            if v_out > h[r, c] and v_out > 0:
                scale[r, c] = h[r, c] / v_out
    for r in range(nr):
        for c in range(nc + 1):
            q = qx[r, c]
            if q > 0 and c - 1 >= 0 and mask[r, c - 1]:
                qx[r, c] = q * scale[r, c - 1]
            elif q < 0 and c < nc and mask[r, c]:
                qx[r, c] = q * scale[r, c]
    for r in range(nr + 1):
        for c in range(nc):
            q = qy[r, c]
            if q > 0 and r - 1 >= 0 and mask[r - 1, c]:
                qy[r, c] = q * scale[r - 1, c]
            elif q < 0 and r < nr and mask[r, c]:
                qy[r, c] = q * scale[r, c]
    leaving = 0.0
    for r in range(nr):
        for c in range(nc):
            if not mask[r, c]:
                continue
            dh = (qx[r, c] - qx[r, c + 1] + qy[r, c] - qy[r + 1, c]) * dt / dx
            h[r, c] = max(h[r, c] + dh, 0.0)
            # flows across open edges
            if c == 0 or not mask[r, c - 1]:
                leaving += max(-qx[r, c], 0.0) * dt * dx
            if c == nc - 1 or not mask[r, c + 1]:
                leaving += max(qx[r, c + 1], 0.0) * dt * dx
            if r == 0 or not mask[r - 1, c]:
                leaving += max(-qy[r, c], 0.0) * dt * dx
            if r == nr - 1 or not mask[r + 1, c]:
                leaving += max(qy[r + 1, c], 0.0) * dt * dx
    return leaving


@njit(cache=True, nogil=True)
def _sources(h, mask, rain_m, infil_rate, el, cap, store, el_rate, el_area, el_cells, dt, cell_area):
    """Rain, ground infiltration, element capture and element infiltration. Returns (infil m3, el_infil m3).

    Order-independent (the GPU port does the same in parallel): each element cell takes at most an
    equal share of the element's remaining capacity at the start of the step."""
    nr, nc = h.shape
    share = np.zeros(store.shape[0])
    for k in range(store.shape[0]):
        if el_cells[k] > 0:
            share[k] = max(cap[k] - store[k], 0.0) / (el_cells[k] * cell_area)
    taken = np.zeros(store.shape[0])
    infil = 0.0
    for r in range(nr):
        for c in range(nc):
            if not mask[r, c]:
                continue
            h[r, c] += rain_m
            k = el[r, c]
            if k >= 0:
                take = min(h[r, c], share[k])
                h[r, c] -= take
                taken[k] += take * cell_area
            else:
                f = min(h[r, c], infil_rate[r, c] * dt)
                h[r, c] -= f
                infil += f * cell_area
    el_inf = 0.0
    for k in range(store.shape[0]):
        store[k] += taken[k]
        loss = min(store[k], el_rate[k] * dt * el_area[k])
        store[k] -= loss
        el_inf += loss
    return infil, el_inf


@njit(cache=True, nogil=True)
def _max_depth(h, mask):
    nr, nc = h.shape
    top = 0.0
    for r in range(nr):
        for c in range(nc):
            if mask[r, c] and h[r, c] > top:
                top = h[r, c]
    return top


@njit(cache=True, nogil=True)
def _track_max(hmax, h):
    nr, nc = h.shape
    for r in range(nr):
        for c in range(nc):
            if h[r, c] > hmax[r, c]:
                hmax[r, c] = h[r, c]


@njit(cache=True, nogil=True)
def _rates_m_s(out, mask, mm_hr):
    nr, nc = out.shape
    for r in range(nr):
        for c in range(nc):
            out[r, c] = mm_hr[r, c] / 1000.0 / 3600.0 if mask[r, c] else 0.0


@dataclass
class Elements2D:
    label: np.ndarray  # int grid, -1 = none
    ids: List[str]
    capacity_m3: np.ndarray
    rate_m_s: np.ndarray
    area_m2: np.ndarray


@dataclass
class Result2D:
    times_s: np.ndarray
    frames: np.ndarray  # (n_frames, nr, nc) float32 depths, m
    max_depth: np.ndarray
    balance: Dict[str, float]
    element_store_m3: Dict[str, float] = field(default_factory=dict)
    velocity: Optional[np.ndarray] = None   # (n_frames, 2, nr, nc) float16: east and north speed at each cell, m/s


DRY_M = 0.0005     # shallower than this a cell has no speed; sheet flow over a lawn is only a few mm deep
V_CAP = 10.0       # m/s: a speed above this is a numerical spike at a wet-dry edge, not flow


def cell_velocity(q_east: np.ndarray, q_south: np.ndarray, h: np.ndarray) -> np.ndarray:
    """The water's velocity at each cell centre (m/s, east and north, row 0 = north), from the flow per metre width
    across each cell's east edge (``q_east[r, c]``, + to the east) and south edge (``q_south[r, c]``, + to the south):
    the mean of a cell's two edges in each direction over its depth. Dry cells are still."""
    q_west = np.zeros_like(q_east)
    q_west[:, 1:] = q_east[:, :-1]
    q_north = np.zeros_like(q_south)
    q_north[1:, :] = q_south[:-1, :]
    wet = h > DRY_M
    d = np.where(wet, h, 1.0)
    u = np.where(wet, 0.5 * (q_east + q_west) / d, 0.0)
    v = np.where(wet, -0.5 * (q_south + q_north) / d, 0.0)   # north is up the map: against the rows
    speed = np.hypot(u, v)
    k = np.where(speed > V_CAP, V_CAP / np.maximum(speed, 1e-9), 1.0)
    return np.stack([u * k, v * k]).astype(np.float16)


def simulate(z: np.ndarray, mask: np.ndarray, cell: float, rain_mm_hr: np.ndarray, rain_dt_s: float,
             duration_s: float, n_manning: np.ndarray, infil_mm_hr: np.ndarray,
             elements: Optional[Elements2D] = None, frame_every_s: float = 300.0, alpha: float = 0.7,
             dt_max: float = 10.0, edge_drop_fraction: float = 0.01, infil_fn=None, inlets=None,
             theta: float = 0.9) -> Result2D:   # theta 1 is the undamped scheme of the Unity preview shader
    """Run the 2D model. ``rain_mm_hr[i]`` applies from ``i * rain_dt_s``; depths start dry.

    ``infil_fn(t_s, rain_mm_hr, cum_rain_mm) -> mm/hr grid`` replaces the constant rates when given
    (curve number or Horton, to match the SWMM infiltration method). ``inlets``: (row, col, area m2) cells where the
    rain on an area outside the site arrives."""
    nr, nc = z.shape
    z = np.where(mask, z, 0.0).astype(np.float64)
    h = np.zeros((nr, nc))
    qx = np.zeros((nr, nc + 1))
    qy = np.zeros((nr + 1, nc))
    n2 = (np.asarray(n_manning, float) ** 2) * np.ones((nr, nc))
    f_rate = np.where(mask, np.asarray(infil_mm_hr, float) / 1000 / 3600, 0.0) * np.ones((nr, nc))
    if elements is None:
        elements = Elements2D(-np.ones((nr, nc), np.int64), [], np.zeros(0), np.zeros(0), np.zeros(0))
    el = elements.label.astype(np.int64)
    store = np.zeros(len(elements.ids))
    cap, el_rate, el_area = (elements.capacity_m3.astype(float), elements.rate_m_s.astype(float),
                             elements.area_m2.astype(float))
    cell_area = cell * cell
    wet_area = cell_area * mask.sum()
    el_cells = np.array([float(((el == k) & mask).sum()) for k in range(len(elements.ids))])
    t = 0.0
    rain_tot = infil_tot = el_inf_tot = out_tot = inlet_tot = 0.0
    frames, times = [h.astype(np.float32)], [0.0]
    vel = [np.zeros((2, nr, nc), np.float16)]
    hmax = np.zeros((nr, nc))
    next_frame = frame_every_s
    edge_drop = edge_drop_fraction * cell
    cum_rain_mm = 0.0
    while t < duration_s - 1e-9:
        hm = _max_depth(h, mask)
        dt = dt_max if hm < 1e-3 else min(dt_max, alpha * cell / math.sqrt(G * hm))
        i = int(t // rain_dt_s)
        t_next_rain = (i + 1) * rain_dt_s
        dt = min(dt, t_next_rain - t, duration_s - t, max(next_frame - t, 1e-6))
        rate = rain_mm_hr[i] if i < len(rain_mm_hr) else 0.0
        rain_m = rate / 1000 / 3600 * dt
        if infil_fn is not None:
            _rates_m_s(f_rate, mask, infil_fn(t, rate, cum_rain_mm))
        cum_rain_mm += rate * dt / 3600
        _fluxes(z, h, mask, n2, qx, qy, dt, cell, edge_drop, theta)
        out_tot += _limit_and_update(h, mask, qx, qy, dt, cell)
        inf, ein = _sources(h, mask, rain_m, f_rate, el, cap, store, el_rate, el_area, el_cells, dt, cell_area)
        rain_tot += rain_m * wet_area
        for r_in, c_in, area_in in inlets or ():
            h[r_in, c_in] += rain_m * area_in / cell_area
            inlet_tot += rain_m * area_in
        infil_tot += inf
        el_inf_tot += ein
        _track_max(hmax, h)
        t += dt
        if t >= next_frame - 1e-9 or t >= duration_s - 1e-9:
            frames.append(h.astype(np.float32))
            vel.append(cell_velocity(qx[:, 1:], qy[1:, :], h))
            times.append(t)
            next_frame += frame_every_s
    surface = float(h[mask].sum() * cell_area)
    stored = float(store.sum())
    err = rain_tot + inlet_tot - (infil_tot + el_inf_tot + out_tot + surface + stored)
    balance = {
        "rainfall_m3": rain_tot, "inlet_m3": inlet_tot, "infiltration_ground_m3": infil_tot, "infiltration_elements_m3": el_inf_tot,
        "outflow_m3": out_tot, "surface_remaining_m3": surface, "element_storage_remaining_m3": stored,
        "continuity_error_m3": err, "continuity_error_pct": 100 * err / (rain_tot + inlet_tot) if rain_tot + inlet_tot else 0.0,
    }
    return Result2D(np.array(times), np.stack(frames), hmax, balance,
                    {i: float(s) for i, s in zip(elements.ids, store)}, np.stack(vel))
