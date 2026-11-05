"""The built-in 2D model of :mod:`.model` on an NVIDIA graphics card (Taichi, CUDA, double precision): the same scheme in
the same order, so it gives the same water. Used for a storm of Simulate when the card is there (``engine='gpu'``).
"""

import math

import numpy as np

from .model import Result2D

G = 9.81


def available() -> bool:
    """Taichi is installed and finds the card."""
    try:
        import taichi as ti

        ti.init(arch=ti.cuda, log_level=ti.ERROR)
        ok = ti.lang.impl.current_cfg().arch == ti.cuda
        ti.reset()
        return ok
    except Exception:   # no Taichi, no NVIDIA card or no driver: the CPU runs the storm
        return False


def can_run(inp) -> bool:
    """The cases this port covers: curve number or constant infiltration, no inlets from outside the site."""
    return inp.infil_params.get("kind") in ("curve_number", "constant") and not inp.inlets


def simulate_gpu(inp, frame_every_s: float, edge_drop_fraction: float = 0.01) -> Result2D:
    import taichi as ti

    ti.init(arch=ti.cuda, default_fp=ti.f64, default_ip=ti.i32, log_level=ti.WARN, offline_cache=True)
    g, mask = inp.dem, inp.mask
    nr, nc = g.z.shape
    cell = float(g.cell_size)
    cell_area = cell * cell
    edge = edge_drop_fraction * cell
    side = 0.5 * (1.0 - inp.theta)
    theta = inp.theta
    els = inp.elements
    n_el = len(els.ids) if els is not None else 0
    size = max(n_el, 1)

    grid = lambda shape: ti.field(ti.f64, shape=shape)   # noqa: E731
    z, h, n2, scale, s_mm, base, hmax, inf_cum, out_cum = [grid((nr, nc)) for _ in range(9)]
    qx, was_x = grid((nr, nc + 1)), grid((nr, nc + 1))
    qy, was_y = grid((nr + 1, nc)), grid((nr + 1, nc))
    cap, rate_el, area, cells, store, taken, share = [grid(size) for _ in range(7)]
    el_inf, top = grid(()), grid(())
    mk, el = ti.field(ti.i32, shape=(nr, nc)), ti.field(ti.i32, shape=(nr, nc))
    z.from_numpy(np.where(mask, g.z, 0.0).astype(np.float64))
    n2.from_numpy((np.asarray(inp.n, float) ** 2) * np.ones((nr, nc)))
    params = inp.infil_params
    base.from_numpy(np.asarray(params["base_mm_hr"], float) * np.ones((nr, nc)))
    s_mm.from_numpy(np.asarray(params.get("S_mm", 0.0), float) * np.ones((nr, nc)))
    mk.from_numpy(mask.astype(np.int32))
    el.from_numpy(els.label.astype(np.int32) if els is not None else -np.ones((nr, nc), np.int32))
    if n_el:
        cap.from_numpy(els.capacity_m3.astype(float))
        rate_el.from_numpy(els.rate_m_s.astype(float))
        area.from_numpy(els.area_m2.astype(float))
        cells.from_numpy(np.array([float(((els.label == k) & mask).sum()) for k in range(n_el)]))
    power = 7.0 / 3.0

    @ti.kernel
    def step(dt: float, rain_m: float, rate: float, cum: float) -> float:
        for r, c in ti.ndrange(nr, nc + 1):
            was_x[r, c] = qx[r, c]
        for r, c in ti.ndrange(nr + 1, nc):
            was_y[r, c] = qy[r, c]
        for r, c in ti.ndrange(nr, nc + 1):
            a, b = c - 1, c
            in_a = a >= 0 and mk[r, a] == 1
            in_b = b < nc and mk[r, b] == 1
            q = 0.0
            if in_a or in_b:
                za = z[r, a] if in_a else z[r, b] - edge
                ha = h[r, a] if in_a else 0.0
                zb = z[r, b] if in_b else z[r, a] - edge
                hb = h[r, b] if in_b else 0.0
                ea, eb = za + ha, zb + hb
                hf = max(ea, eb) - max(za, zb)
                if hf > 1e-4:
                    nn = n2[r, a] if in_a else n2[r, b]
                    q0 = was_x[r, c]
                    ql = was_x[r, c - 1] if c > 0 else q0
                    qr = was_x[r, c + 1] if c < nc else q0
                    damped = theta * q0 + side * (ql + qr) if in_a and in_b else q0
                    q = (damped - G * hf * dt * (eb - ea) / cell) / (1.0 + G * dt * nn * abs(q0) / hf ** power)
                    if not in_a and q > 0:
                        q = 0.0
                    if not in_b and q < 0:
                        q = 0.0
            qx[r, c] = q
        for r, c in ti.ndrange(nr + 1, nc):
            a, b = r - 1, r
            in_a = a >= 0 and mk[a, c] == 1
            in_b = b < nr and mk[b, c] == 1
            q = 0.0
            if in_a or in_b:
                za = z[a, c] if in_a else z[b, c] - edge
                ha = h[a, c] if in_a else 0.0
                zb = z[b, c] if in_b else z[a, c] - edge
                hb = h[b, c] if in_b else 0.0
                ea, eb = za + ha, zb + hb
                hf = max(ea, eb) - max(za, zb)
                if hf > 1e-4:
                    nn = n2[a, c] if in_a else n2[b, c]
                    q0 = was_y[r, c]
                    qt = was_y[r - 1, c] if r > 0 else q0
                    qb = was_y[r + 1, c] if r < nr else q0
                    damped = theta * q0 + side * (qt + qb) if in_a and in_b else q0
                    q = (damped - G * hf * dt * (eb - ea) / cell) / (1.0 + G * dt * nn * abs(q0) / hf ** power)
                    if not in_a and q > 0:
                        q = 0.0
                    if not in_b and q < 0:
                        q = 0.0
            qy[r, c] = q
        for r, c in ti.ndrange(nr, nc):
            v = 1.0
            if mk[r, c] == 1:
                o = max(qx[r, c + 1], 0.0) + max(-qx[r, c], 0.0) + max(qy[r + 1, c], 0.0) + max(-qy[r, c], 0.0)
                w = o * dt / cell
                if w > h[r, c] and w > 0:
                    v = h[r, c] / w
            scale[r, c] = v
        for r, c in ti.ndrange(nr, nc + 1):
            q = qx[r, c]
            if q > 0 and c - 1 >= 0 and mk[r, c - 1] == 1:
                qx[r, c] = q * scale[r, c - 1]
            elif q < 0 and c < nc and mk[r, c] == 1:
                qx[r, c] = q * scale[r, c]
        for r, c in ti.ndrange(nr + 1, nc):
            q = qy[r, c]
            if q > 0 and r - 1 >= 0 and mk[r - 1, c] == 1:
                qy[r, c] = q * scale[r - 1, c]
            elif q < 0 and r < nr and mk[r, c] == 1:
                qy[r, c] = q * scale[r, c]
        for k in range(size):
            share[k] = max(cap[k] - store[k], 0.0) / (cells[k] * cell_area) if cells[k] > 0 else 0.0
            taken[k] = 0.0
        top[None] = 0.0
        for r, c in ti.ndrange(nr, nc):
            if mk[r, c] == 1:
                d = max(h[r, c] + (qx[r, c] - qx[r, c + 1] + qy[r, c] - qy[r + 1, c]) * dt / cell, 0.0)
                leaving = 0.0
                if c == 0 or mk[r, c - 1] == 0:
                    leaving += max(-qx[r, c], 0.0)
                if c == nc - 1 or mk[r, c + 1] == 0:
                    leaving += max(qx[r, c + 1], 0.0)
                if r == 0 or mk[r - 1, c] == 0:
                    leaving += max(-qy[r, c], 0.0)
                if r == nr - 1 or mk[r + 1, c] == 0:
                    leaving += max(qy[r + 1, c], 0.0)
                out_cum[r, c] += leaving * dt * cell
                d += rain_m
                k = el[r, c]
                if k >= 0:
                    t = min(d, share[k])
                    d -= t
                    taken[k] += t * cell_area
                else:
                    s = s_mm[r, c]
                    f = max(base[r, c], rate * (s / (cum + s)) ** 2 if cum + s > 0 else 0.0) / 3600000.0
                    f = min(d, f * dt)
                    d -= f
                    inf_cum[r, c] += f * cell_area
                h[r, c] = d
                hmax[r, c] = max(hmax[r, c], d)
                ti.atomic_max(top[None], d)
        for k in range(size):
            store[k] += taken[k]
            loss = min(store[k], rate_el[k] * dt * area[k])
            store[k] -= loss
            el_inf[None] += loss
        return top[None]

    wet_area = cell_area * float(mask.sum())
    t, cum, hm, rain_tot = 0.0, 0.0, 0.0, 0.0
    next_frame = frame_every_s
    frames, times = [np.zeros((nr, nc), np.float32)], [0.0]
    rain, rain_dt, dur = inp.rain_mm_hr, inp.rain_dt_s, inp.duration_s
    while t < dur - 1e-9:
        dt = inp.dt_max if hm < 1e-3 else min(inp.dt_max, inp.alpha * cell / math.sqrt(G * hm))
        i = int(t // rain_dt)
        dt = min(dt, (i + 1) * rain_dt - t, dur - t, max(next_frame - t, 1e-6))
        rate = float(rain[i]) if i < len(rain) else 0.0
        rain_m = rate / 1000 / 3600 * dt
        hm = step(dt, rain_m, rate, cum)
        cum += rate * dt / 3600
        rain_tot += rain_m * wet_area
        t += dt
        if t >= next_frame - 1e-9 or t >= dur - 1e-9:
            frames.append(h.to_numpy().astype(np.float32))
            times.append(t)
            next_frame += frame_every_s
    depth = h.to_numpy()
    stored_each = store.to_numpy()[:n_el]
    infil, out, ein = float(inf_cum.to_numpy().sum()), float(out_cum.to_numpy().sum()), float(el_inf[None])
    surface, stored = float(depth[mask].sum() * cell_area), float(stored_each.sum())
    err = rain_tot - (infil + ein + out + surface + stored)
    balance = {"rainfall_m3": rain_tot, "inlet_m3": 0.0, "infiltration_ground_m3": infil, "infiltration_elements_m3": ein,
               "outflow_m3": out, "surface_remaining_m3": surface, "element_storage_remaining_m3": stored,
               "continuity_error_m3": err, "continuity_error_pct": 100 * err / rain_tot if rain_tot else 0.0}
    ids = els.ids if els is not None else []
    return Result2D(np.array(times), np.stack(frames), hmax.to_numpy(), balance, {i: float(s) for i, s in zip(ids, stored_each)})
