# Rhino and Grasshopper (Phase 6)

## .3dm export and round trip (no Rhino needed)

```
spongepark rhino export PROJECT OPTION out.3dm
spongepark rhino import PROJECT OPTION edited.3dm      # detects edits, locks them, regrades, reruns SWMM
```

The export uses the brief's layers:

| Layer | Content |
|---|---|
| TERRAIN::Existing, TERRAIN::Graded | Meshes of the existing and graded DEM |
| CONTOURS::Existing, CONTOURS::Proposed | Contours at the finest `layout.contour_intervals_m`, at their level |
| NBS::Bioswale, RainGarden, DetentionPond, RetentionPond, RechargeWell | Element outlines (swales as centrelines, wells as circles) |
| ANALYSIS::FlowPaths, Subcatchments, CutFill, FloodDepth | Main flow lines, option subcatchments, cut depth (coloured mesh), 2D maximum depth (coloured, indicative) |
| CONTEXT::Boundary, Buildings, Trees | Site context |

Every NbS object carries user text with all element fields, the SWMM results per return period
(`rp25.max_depth_m`, `rp25.overflow_m3`, ...) and the geometry it was exported with.

**Editing in Rhino.** Move, scale or reshape an outline, delete it, or draw a new closed curve on an
NBS layer (a circle on NBS::RechargeWell). On import the engine compares each object with the option
by its `id` user text:

- moved (centroid shifts more than 0.1 m), resized (area or length changes more than 1 %), reshaped,
  deleted (missing from the file) or new (no known id; a new id like `RA_D1` is given);
- every edited or new element becomes a designer element and is locked, so later layout generation
  keeps it;
- the option is regraded from the elements as drawn (storage inverts follow the new rims; keep-out
  areas are never regraded), subcatchments are rebuilt, and SWMM is rerun with the comparison.

An unchanged file changes nothing.

## Grasshopper components (Rhino 8, Python 3)

Rhino 8 runs Python 3.9 and the engine needs 3.10+, so the components do not import the engine: they
call the local engine API. Start it once with `spongepark serve` (http://127.0.0.1:8765).

Build the component scripts with `python -m spongepark.rhino.grasshopper.build`. It writes
`spongepark/rhino/grasshopper/components/*.py` with the API client inlined (standard library only, no
`# r:` installs needed). In Grasshopper add a Script component, choose Python 3, paste a file, and
create the inputs and outputs listed at its top.

| Component | Does |
|---|---|
| Load Project | Opens a `.sponge` project on the engine |
| Analyse Baseline | Delineation and the existing-site SWMM run |
| Set Targets | Area budget, design storm, drawdown limit, inverse-mode target (stored as user decisions) |
| Generate Options | One generated layout, or the optimiser's Pareto options |
| Run SWMM | Runs an option and lists retention, peak reduction and lag per return period |
| Show Results | Element outlines coloured by how full they get |
| Play Storm | Depth in every element through the storm, driven by a 0-1 slider |
| Write Back | Sends edited curves; they become locked designer elements; regrade + SWMM rerun |

The components that need no Rhino geometry are tested against a live server in the test suite;
those that build Rhino geometry need checking inside Rhino.
