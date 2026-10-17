"""Float32, kernel-by-kernel reference of the Unity GPU water simulation (``WaterSim.compute``).

The compute shader cannot run in the test suite, so this module reproduces its exact structure:
the same kernels in the same order, every kernel reading the state left by the previous one (no
in-place sequential updates), float32 arithmetic on elevations relative to the lowest ground point,
and per-cell / per-element accumulators instead of atomics. Tests check it against the engine's numba model (``model.simulate``); the shader is a line-by-
line transcription of these kernels, and the Unity app verifies the shader against the engine on
the same inputs (``/sim2d/{rp}/inputs``).

Kernel order per step (matches WaterSim.compute):
FluxX, FluxY -> CellScale -> ScaleX, ScaleY -> Update -> ElementShare -> Sources -> ElementUpdate.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

F = np.float32
G = F(9.81)


def _flux_x(z, h, mask, n2, qx, dt, dx, drop):
    nr, nc = z.shape
    f = np.zeros((nr, 1), bool)
    mL = np.hstack([f, mask])
    mR = np.hstack([mask, f])
    zero = np.zeros((nr, 1), F)
    zL, zR = np.hstack([zero, z]), np.hstack([z, zero])
    hL, hR = np.hstack([zero, h]), np.hstack([h, zero])
    nL, nR = np.hstack([zero, n2]), np.hstack([n2, zero])
    zl = np.where(mL, zL, zR - drop)
    hl = np.where(mL, hL, F(0))
    zr = np.where(mR, zR, zL - drop)
    hr = np.where(mR, hR, F(0))
    el, er = zl + hl, zr + hr
    hf = np.maximum(el, er) - np.maximum(zl, zr)
    nn = np.where(mL, nL, nR)
    wet = (hf > F(1e-4)) & (mL | mR)
    hfs = np.where(wet, hf, F(1))
    q = (qx - G * hfs * dt * (er - el) / dx) / (F(1) + G * dt * nn * np.abs(qx) / hfs ** F(7.0 / 3.0))
    q = np.where(wet, q, F(0))
    q = np.where(~mL & (q > 0), F(0), q)
    q = np.where(~mR & (q < 0), F(0), q)
    return q.astype(F)


def _flux_y(z, h, mask, n2, qy, dt, dx, drop):
    return _flux_x(z.T, h.T, mask.T, n2.T, qy.T, dt, dx, drop).T


def step(state: Dict[str, Any], dt: float, rain_mm_hr: float, infil_mm_hr: np.ndarray) -> None:
    """One time step on ``state`` (float32 arrays), in the shader's kernel order."""
    z, h, mask, n2 = state["z"], state["h"], state["mask"], state["n2"]
    dx, drop, ca = state["dx"], state["drop"], state["cell_area"]
    dt = F(dt)
    # FluxX, FluxY
    qx = _flux_x(z, h, mask, n2, state["qx"], dt, dx, drop)
    qy = _flux_y(z, h, mask, n2, state["qy"], dt, dx, drop)
    # CellScale
    out = np.maximum(qx[:, 1:], 0) + np.maximum(-qx[:, :-1], 0) + np.maximum(qy[1:, :], 0) + np.maximum(-qy[:-1, :], 0)
    v_out = out * dt / dx
    scale = np.where(mask & (v_out > h) & (v_out > 0), h / np.where(v_out > 0, v_out, F(1)), F(1)).astype(F)
    # ScaleX, ScaleY: a face takes the scale of the cell its water comes from
    nr, nc = h.shape
    one_c = np.ones((nr, 1), F)
    one_r = np.ones((1, nc), F)
    sL, sR = np.hstack([one_c, scale]), np.hstack([scale, one_c])
    mL, mR = np.hstack([np.zeros((nr, 1), bool), mask]), np.hstack([mask, np.zeros((nr, 1), bool)])
    qx = np.where((qx > 0) & mL, qx * sL, np.where((qx < 0) & mR, qx * sR, qx)).astype(F)
    sT, sB = np.vstack([one_r, scale]), np.vstack([scale, one_r])
    mT, mB = np.vstack([np.zeros((1, nc), bool), mask]), np.vstack([mask, np.zeros((1, nc), bool)])
    qy = np.where((qy > 0) & mT, qy * sT, np.where((qy < 0) & mB, qy * sB, qy)).astype(F)
    # Update (depth and per-cell outflow over open edges)
    dh = (qx[:, :-1] - qx[:, 1:] + qy[:-1, :] - qy[1:, :]) * dt / dx
    h = np.where(mask, np.maximum(h + dh, F(0)), h).astype(F)
    left_out = mask & ~mL[:, :-1]
    right_out = mask & ~mR[:, 1:]
    top_out = mask & ~mT[:-1, :]
    bot_out = mask & ~mB[1:, :]
    leave = (np.where(left_out, np.maximum(-qx[:, :-1], 0), 0) + np.where(right_out, np.maximum(qx[:, 1:], 0), 0)
             + np.where(top_out, np.maximum(-qy[:-1, :], 0), 0) + np.where(bot_out, np.maximum(qy[1:, :], 0), 0))
    state["cell_out"] += (leave * dt * dx).astype(F)
    # ElementShare
    el, store = state["el"], state["store"]
    share = np.where(state["el_cells"] > 0, np.maximum(state["cap"] - store, 0) / (np.maximum(state["el_cells"], 1) * ca), 0).astype(F)
    # Sources
    rain_m = F(rain_mm_hr / 1000.0 / 3600.0) * dt
    h = np.where(mask, h + rain_m, h).astype(F)
    is_el = (el >= 0) & mask
    take = (np.where(is_el, np.minimum(h, share[np.maximum(el, 0)]), F(0)) if share.size else np.zeros_like(h)).astype(F)
    f = np.where(mask & ~is_el, np.minimum(h, (infil_mm_hr / F(1000.0 * 3600.0)).astype(F) * dt), F(0)).astype(F)
    h = (h - take - f).astype(F)
    state["cell_inf"] += (f * ca).astype(F)
    # ElementUpdate
    if store.size:
        taken = np.bincount(el[is_el], weights=(take * ca)[is_el], minlength=store.size).astype(F)
        store = (store + taken).astype(F)
        loss = np.minimum(store, state["el_rate"] * dt * state["el_area"]).astype(F)
        state["store"] = (store - loss).astype(F)
        state["el_inf"] += loss
    state.update(h=h, qx=qx, qy=qy)
    np.maximum(state["hmax"], h, out=state["hmax"])


def simulate_gpu_reference(z, mask, cell, rain_mm_hr, rain_dt_s, duration_s, n_manning, infil_mm_hr,
                           elements=None, alpha=0.7, dt_max=10.0, edge_drop_fraction=0.01,
                           infil_fn=None) -> Dict[str, Any]:
    nr, nc = z.shape
    # elevations relative to the lowest ground: float32 near 900 m resolves only ~6e-5 m, which makes
    # flat water surfaces noisy; relative to the datum the resolution is ~1e-7 m (the shader does the same)
    datum = float(np.min(z[mask])) if mask.any() else 0.0
    st: Dict[str, Any] = {
        "z": np.where(mask, z - datum, 0).astype(F), "h": np.zeros((nr, nc), F), "mask": mask.astype(bool),
        "n2": (np.asarray(n_manning, float) ** 2 * np.ones((nr, nc))).astype(F), "qx": np.zeros((nr, nc + 1), F),
        "qy": np.zeros((nr + 1, nc), F), "dx": F(cell), "drop": F(edge_drop_fraction * cell), "cell_area": F(cell * cell),
        "cell_out": np.zeros((nr, nc), F), "cell_inf": np.zeros((nr, nc), F), "hmax": np.zeros((nr, nc), F),
    }
    if elements is not None and len(elements.ids):
        el = elements.label.astype(np.int64)
        st.update(el=el, cap=elements.capacity_m3.astype(F), store=np.zeros(len(elements.ids), F),
                  el_rate=elements.rate_m_s.astype(F), el_area=elements.area_m2.astype(F),
                  el_cells=np.array([((el == k) & mask).sum() for k in range(len(elements.ids))], F),
                  el_inf=np.zeros(len(elements.ids), F))
    else:
        st.update(el=-np.ones((nr, nc), np.int64), cap=np.zeros(0, F), store=np.zeros(0, F), el_rate=np.zeros(0, F),
                  el_area=np.zeros(0, F), el_cells=np.zeros(0, F), el_inf=np.zeros(0, F))
    f_const = np.where(mask, np.asarray(infil_mm_hr, float), 0).astype(F)
    t, cum, rain_tot = 0.0, 0.0, 0.0
    while t < duration_s - 1e-9:
        hm = float(st["h"][mask].max()) if mask.any() else 0.0
        dt = dt_max if hm < 1e-3 else min(dt_max, alpha * cell / np.sqrt(9.81 * hm))
        i = int(t // rain_dt_s)
        dt = min(dt, (i + 1) * rain_dt_s - t, duration_s - t)
        rate = float(rain_mm_hr[i]) if i < len(rain_mm_hr) else 0.0
        f = np.where(mask, infil_fn(t, rate, cum), 0).astype(F) if infil_fn is not None else f_const
        cum += rate * dt / 3600
        step(st, dt, rate, f)
        rain_tot += rate / 1000 / 3600 * dt * cell * cell * mask.sum()
        t += dt
    return {"h": st["h"], "hmax": st["hmax"], "rainfall_m3": rain_tot, "outflow_m3": float(st["cell_out"].sum()),
            "infiltration_ground_m3": float(st["cell_inf"].sum()), "infiltration_elements_m3": float(st["el_inf"].sum()),
            "element_storage_remaining_m3": float(st["store"].sum()),
            "surface_remaining_m3": float(st["h"][mask].sum() * cell * cell)}
