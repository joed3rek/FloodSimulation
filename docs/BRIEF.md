# PROJECT BRIEF: SPONGE PARK DESIGNER
## A Unity desktop application for flood simulation and nature-based solution design

---

## 1. PURPOSE

Build a desktop application for landscape architects and urban designers that:

1. Imports a land survey (DWG or DEM raster) and analyses it.
2. Builds a 3D terrain model of the site automatically.
3. Simulates rainfall and flooding on the site for storms from the 1 year to the 100 year return period.
4. Generates an initial nature-based solution (NbS) proposal using optimisation and machine learning.
5. Lets the designer accept the proposal, edit it, or start from scratch, using dedicated editing tools.
6. Updates the flood simulation live as the designer edits, so they can see water respond to every change.
7. Verifies performance with EPA SWMM and reports a credible water balance.
8. Exports drawings, quantities, reports and simulation videos.

The pilot site is a park in Bengaluru, Karnataka, being designed as a "sponge park": a site that intercepts, slows, infiltrates, stores, recharges and gradually releases rainfall.

The five NbS components are:
1. Bioswale
2. Rain garden
3. Detention pond
4. Retention pond
5. Recharge well

Plus terrain shaping (berms, check dams, regrading).

---

## 2. CORE PRINCIPLES (NON-NEGOTIABLE)

1. Two-speed feedback.
   - Live preview: a GPU 2D flood simulation in Unity updates within about one second of any edit. Labelled "Preview".
   - Verified results: EPA SWMM, run through the Python engine, produces all official numbers. Labelled "Verified".
2. SWMM is the source of truth for every reported figure. Never modify the SWMM core.
3. Machine learning proposes; it never reports. ML is used for the initial proposal and to speed up optimisation. Every proposal is verified by SWMM before it is shown.
4. The designer is in control. Any element can be accepted, moved, resized, locked, deleted or replaced.
5. Non-destructive terrain. The working terrain is always rebuilt from "existing ground + all NbS elements + all terrain edits". Moving or deleting an element restores the ground beneath it.
6. Single project file. All data lives in one .sponge project package shared by Unity and the Python engine.
7. No hidden assumptions. Every parameter records its value, unit and source ("default", "site measured", "literature", "designer"). Reports list them.
8. Mass balance must close. Every simulation reports a continuity error; flag runs above 1 percent.
9. Honest labelling. Uncalibrated results are labelled for scenario comparison only. 2D surface results are labelled indicative.

---

## 3. USERS

| User | Needs |
|---|---|
| Designer (primary) | Fast iteration, intuitive tools, clear feedback |
| Technical reviewer (engineer, BBMP, BWSSB) | Transparent parameters, SWMM files, water balance |
| Funder or CSR partner | Before and after comparison, headline metrics, video |
| Community | Clear visual simulation in plain language |

---

## 4. SYSTEM ARCHITECTURE

| Layer | Technology | Responsibility |
|---|---|---|
| Application | Unity 6 LTS, C#, URP | Interface, 3D view, editing tools, terrain display, project management |
| Live simulation | HLSL compute shaders in Unity | 2D rain-on-grid flood simulation on the GPU |
| Engine | Python 3.11+ package (`spongepark`), bundled with the app | Survey import, terrain generation, hydrological analysis, SWMM, optimisation, ML, exports, reports |
| Bridge | Local FastAPI server started by Unity as a background process | Communication between Unity and Python (JSON over HTTP, large rasters via files in the project folder) |
| Project file | .sponge package (zip of a folder) | Single shared state |

Unity launches the Python engine on startup, checks its health, and shuts it down on exit. The user never sees Python.

---

## 5. TECHNOLOGY STACK

Unity side:
- Unity 6 LTS, Universal Render Pipeline
- UI Toolkit for the interface
- Unity Splines package for linear features
- Compute shaders (HLSL) for simulation and terrain carving
- Newtonsoft JSON for serialisation
- Custom mesh terrain generated from a heightmap texture (do not depend on Unity's built-in Terrain system, which restricts heightmap sizes)

Python side:
- ezdxf (DXF reading), ODA File Converter (DWG to DXF, external, detect and guide installation)
- rasterio, shapely, geopandas, scipy, numpy, numba
- pysheds or WhiteboxTools (sink filling, flow direction, accumulation, watersheds)
- swmmio and a custom .inp writer, pyswmm (SWMM execution)
- pymoo (NSGA-II multi-objective optimisation)
- scikit-learn and PyTorch (surrogate models)
- rhino3dm (optional .3dm export)
- FastAPI, pydantic, uvicorn
- matplotlib, Jinja2 (reports)
- pytest
- PyInstaller (bundle the engine for distribution)

---

## 6. APPLICATION WORKFLOW (USER JOURNEY)

### Stage A: Project and survey
1. New project: name, city (default Bengaluru), coordinate system (default UTM Zone 43N, EPSG:32643), units (metres, mm, hours).
2. Import survey: DWG or DEM (GeoTIFF).
3. Layer mapping screen (for DWG): the user confirms which layers contain contours, spot levels, site boundary, buildings, paths, trees, drains, water bodies. The engine suggests mappings from layer names.
4. Terrain review: the engine generates the DEM; Unity displays it in 3D with contours; the user approves or adjusts cell size.

### Stage B: Site data
5. Soil zones with infiltration rates (mm/hr), soil depth, rock depth.
6. Land cover: impervious, lawn, planted, paved, roof.
7. Trees: position, canopy radius, species (for canopy interception).
8. Rainfall: depths or intensities for 1, 2, 5, 10, 25, 50, 100 year return periods; design storm pattern (see Section 9).
9. External catchment: areas outside the site that drain into it.
10. No-go zones: existing trees with root protection, play areas, paths, structures, utilities.

### Stage C: Baseline
11. Engine runs flow analysis: flow paths, sinks, contributing areas, outlets.
12. Unity runs the live flood simulation on existing terrain for any chosen storm.
13. Engine runs baseline SWMM for all return periods (verified existing condition).

### Stage D: Targets
14. Area budget: percentage of site area for interventions (for example 15 to 20 percent).
15. Mode: "maximise retention within budget" or "retain a target storm with minimum area".
16. Maximum ponding depth per component, maximum drawdown time (default 48 to 72 hours), setbacks, cut and fill preference, permitted overflow outlet.

### Stage E: Proposal
17. User clicks "Generate proposal".
18. Engine runs placement, sizing, grading, optimisation (with ML surrogate) and SWMM verification; returns three to five options on a Pareto front.
19. Unity shows options side by side with key metrics.
20. User chooses one of three paths:
    - Accept: the proposal becomes editable elements.
    - Accept and edit: accept, then modify with tools.
    - Start from scratch: proposal hidden but kept for comparison.

### Stage F: Design
21. Designer uses editing tools (Section 8).
22. Every edit updates the terrain and the live flood preview.
23. Live water balance panel updates (preview figures).
24. Designer clicks "Verify" (or verification runs automatically after a pause): engine runs SWMM for all return periods and returns verified metrics.
25. Designer compares options and saves scenarios.

### Stage G: Communicate
26. Side-by-side simulation: existing against proposed for the same storm.
27. Export: drawings, schedules, earthwork, report, video.

---

## 7. PROJECT FILE (.sponge)

| Item | Format | Content |
|---|---|---|
| manifest.json | JSON | Schema version, project name, city, CRS, units, dates, app and engine versions |
| parameters.json | JSON | All parameters with value, unit, source, note |
| survey/ | DXF, GeoTIFF | Original inputs and layer mapping |
| terrain/existing.tif | GeoTIFF | Existing DEM |
| terrain/edits.json | JSON | Terrain brush strokes and shaping operations |
| site/*.geojson | GeoJSON | Boundary, buildings, paths, trees, drains, soil zones, land cover, no-go zones, external catchment |
| rainfall/ | CSV | Return period table and design storm hyetographs |
| scenarios/<id>/elements.json | JSON | NbS elements (Section 8.3) |
| scenarios/<id>/terrain.tif | GeoTIFF | Rebuilt terrain for the scenario |
| scenarios/<id>/swmm/model.inp | SWMM | Generated model |
| scenarios/<id>/results/ | parquet, JSON | Verified time series and summaries per return period |
| proposals/ | JSON | ML proposals retained for comparison |
| edit_log.json | JSON | Designer edits relative to proposals (future ML training data) |
| history.json | JSON | Run and change log |

C# data classes in Unity and pydantic models in Python must mirror this schema exactly. Write a shared JSON Schema and generate or validate both sides against it.

---

## 8. UNITY APPLICATION

### 8.1 Folder structure
Assets/
  Core/Data          # Project, Terrain, NbsElement, Scenario, Results classes
  Core/Commands      # Command pattern: every edit is a reversible command (undo, redo)
  Core/Events        # Event bus for edits, simulation updates, engine responses
  Engine/Bridge      # Python process management and HTTP client
  Terrain/           # Heightmap textures, mesh generation, GPU carving, contour overlay
  Simulation/        # Compute shaders, rainfall scheduler, water rendering
  Tools/             # One class per editing tool, plus tool manager
  UI/                # UI Toolkit documents and controllers
  Export/            # Screenshot, video frame capture, export requests
  Tests/             # Edit mode and play mode tests

### 8.2 Terrain system
- Heightmap stored as a float render texture at DEM resolution.
- Working terrain = existing heightmap, then terrain edits, then NbS carving, computed on the GPU in that order.
- Mesh generated in chunks for large sites, with level of detail.
- Overlays: contours (shader based), slope, flow accumulation, soil zones, cut and fill, no-go zones.

### 8.3 NbS element model
Every element stores: id, type, geometry (spline or polygon or point, in metres), parameters (width, depth, side slope, ponding depth, soil media depth, permanent pool depth, outlet type and size, diameter, seepage rate), infiltration rate, storage volume, contributing area, connections (inflow from, outflow to, overflow to), locked flag, source ("proposal" or "designer"), and verified results per return period.

### 8.4 Editing tools
| Tool | Interaction | Terrain effect | Simulation effect |
|---|---|---|---|
| Bioswale | Draw spline on ground; set width, depth, side slope, check dam spacing | Carves channel profile along spline | Increased infiltration, roughness slows flow |
| Rain garden | Draw polygon; set ponding depth, media depth | Carves shallow basin | High infiltration zone with storage |
| Detention pond | Draw polygon; set depth, side slopes, outlet | Carves basin | Storage with controlled outlet release |
| Retention pond | Draw polygon; set permanent pool depth, safety bench | Carves basin with bench | Permanent storage plus overflow |
| Recharge well | Click to place; set diameter, depth | Small marker | Point sink with seepage rate |
| Terrain brushes | Raise, lower, smooth, flatten, berm | Edits heightmap via edits.json | Redirects flow |
| Select and transform | Move, rotate, resize with handles | Recarves | Updates |
| Lock, delete, duplicate | Standard | As expected | As expected |

Tool requirements:
- Snap to ground surface; show slope and depth while drawing.
- Real-time validation: warn if outside site, in a no-go zone, exceeding depth limits, over the area budget, or with drawdown time beyond the limit.
- Area budget meter always visible.
- Full undo and redo through the command system.

### 8.5 Live GPU flood simulation
Textures: ground height, water depth (double-buffered), flow (x and y), infiltration capacity, infiltration remaining, sink map, NbS mask.

Each time step:
1. Add rainfall (from the current storm hyetograph; reduced beneath tree canopy until interception capacity is full).
2. Compute flow between neighbouring cells using a local inertial (simplified shallow water) formulation.
3. Apply infiltration losses (soil rate, higher inside NbS elements).
4. Apply sinks (recharge wells, pond outlets).
5. Update water depth.
6. Reduce totals with a parallel sum: rainfall, infiltrated, stored, outflow at boundaries.

Requirements:
- Stable time step (CFL condition), adaptive.
- Playback controls: play, pause, speed, scrub, storm selection.
- Water rendering by depth, optional flow arrows and velocity colouring.
- Mass balance check every run.
- Restart automatically after edits.

### 8.6 Live and verified panels
- Live panel (preview): retained percentage, ponded area, outflow, per element fill level.
- Verified panel (SWMM): full water balance, peak reduction, lag time, overflow, drawdown, design retention storm, for all return periods.
- Show the difference between live and verified volumes so the designer knows the preview accuracy.

### 8.7 Interface screens
Home and projects; survey import and layer mapping; terrain review; site data; baseline; targets; proposals comparison; design workspace (3D view, tool bar, properties panel, live panel, verified panel, timeline); scenario comparison; export.

---

## 9. PYTHON ENGINE

### 9.1 API endpoints (FastAPI)
- POST /project/create, /project/open, /project/save
- POST /survey/inspect (list layers), /survey/import (with layer mapping)
- POST /terrain/build
- POST /analysis/baseline (flow paths, sinks, subcatchments)
- POST /swmm/baseline, /swmm/verify (scenario id, return periods)
- POST /proposal/generate (targets and constraints)
- POST /export/dxf, /export/3dm, /export/report, /export/schedules
- GET /health, /job/{id} (long tasks run asynchronously with progress)

Large data (rasters, results) is written to the project folder; the API returns file paths.

### 9.2 Survey import
- DWG to DXF via ODA File Converter; read with ezdxf.
- Handle typical Indian survey problems: contours at Z = 0 with text labels (match labels to contours), spot levels as text or blocks (parse and check units), inconsistent layer names, local coordinates.
- Report unmatched contours and suspicious levels.

### 9.3 Terrain generation
- TIN from contours and spot levels; interpolate to grid (default 0.5 m).
- Quality checks: RMSE against spot levels, spikes, pits, flat areas.
- Warn if source resolution is coarser than 1 m.

### 9.4 Rainfall and design storms
- Return period table: 1, 2, 5, 10, 25, 50, 100 years.
- Determine whether input is 24 hour depth or IDF intensities.
- Hyetograph methods: alternating block (from IDF), Huff curves, or user CSV (for example KSNDMC or IMD gauge records).
- Time step default 5 minutes. State clearly that peak results depend on the hyetograph choice.

### 9.5 Canopy interception
- SWMM does not model tree canopy. Compute interception from canopy area and interception capacity per species or default; subtract from rainfall beneath canopy; report as a separate water balance term.

### 9.6 Baseline analysis
- Fill sinks (recording sink locations and volumes as candidate storage), flow direction, flow accumulation, watersheds, outlets, slope.

### 9.7 SWMM model builder
- Subcatchments from delineation of the working terrain, with area, width, slope, imperviousness, infiltration (Horton or Green-Ampt), depression storage.
- NbS mapping:
  - Bioswale: LID Vegetative Swale
  - Rain garden: LID Rain Garden or Bio-Retention Cell
  - Detention pond: storage node with orifice or weir outlet
  - Retention pond: storage node with permanent pool and overflow weir
  - Recharge well: storage node with seepage loss (document the method)
- Rain gauges and time series for each return period; external catchment as inflow.
- Run with pyswmm; store time series and summaries; report continuity errors.

### 9.8 Metrics
Water balance for each scenario and return period:
Rainfall = Canopy interception + Depression storage + Infiltration + Recharge + Storage remaining + Evaporation + Overflow leaving site

Report: retained percentage, peak outflow reduction, lag time, volumes infiltrated, recharged and stored, overflow volume and timing, drawdown time per element, largest return period fully retained, flooded locations, cut and fill, intervention area percentage.

Performance curve: intervention area (5, 10, 15, 20, 25 percent) against largest storm fully retained.

### 9.9 Proposal generation (optimisation and machine learning)
Placement:
- Suitability score per grid cell per component, from flow accumulation, slope, soil infiltration, distance to impervious surfaces, sink depth, no-go zones.
- Candidate locations per component; connect into a treatment train (rain gardens and swales upstream, ponds downstream, recharge wells taking overflow).

Sizing and grading:
- Size from contributing area and target storm within the area budget and depth limits; check drawdown; carve the terrain; rebuild subcatchments.

Optimisation:
- pymoo NSGA-II. Variables: inclusion, location, footprint, depth of each component, allocation of area budget. Objectives: maximise retained volume across return periods, minimise peak outflow, minimise earthwork, minimise area (inverse mode). Constraints: budget, depths, drawdown, no-go zones, locks.

Machine learning:
- Surrogate model: trained on SWMM results from sampled layouts (Latin hypercube) to predict key metrics quickly, so the optimiser can evaluate thousands of layouts. Gradient boosting first; neural network if needed.
- Validate on hold-out data; refuse to use the surrogate if error exceeds a configurable threshold.
- Active learning: verify top candidates with SWMM and add them to the training set.
- Learning from designers: store accepted, edited and rejected proposals in edit_log.json; later train a ranking model that improves placement suggestions.
- All proposals shown to the user are SWMM verified.

### 9.10 Calibration
- If observed data exist (gauge rainfall with observed ponding depths, timestamped flood photos), adjust infiltration, roughness, depression storage and imperviousness to match.
- Also calibrate GPU simulation parameters against SWMM on test terrains so live and verified results agree.
- Mark projects as calibrated or uncalibrated.

### 9.11 Exports
- Graded contours and NbS layout: DXF; optional .3dm via rhino3dm with named layers and element attributes.
- Component schedule, earthwork quantities, water balance tables, performance curve, hydrographs.
- Parameter table with sources.
- SWMM .inp files for independent engineering review.
- HTML and PDF report in plain professional English.
- Video (frames captured in Unity, assembled by the engine).

---

## 10. BENGALURU CONTEXT AND DEFAULTS
- CRS: UTM Zone 43N (EPSG:32643).
- Rainfall sources: the user's return period table first; support IMD and KSNDMC data.
- Soils: red lateritic and sandy loam with variable infiltration; shallow weathered rock and sheet rock in places. Require infiltration per zone; never assume one site-wide value.
- Controlled overflow to storm water drains and the lake network is acceptable; full retention of the 100 year storm is not a default target. Report the largest storm fully retained.
- All defaults require user confirmation before appearing in reports.

---

## 11. TESTING
- Python unit tests per module; Unity edit mode and play mode tests.
- Synthetic terrains (plane, V valley, bowl) with analytical checks.
- SWMM generated models compared with a hand built model.
- Mass balance tests for SWMM and the GPU simulation.
- Live against verified volume tolerance tests.
- DWG import problem cases.
- Undo and redo tests for every tool.
- End to end example project: survey import to exported report.

---

## 12. CODING STANDARDS
- C#: clear namespaces, no logic in MonoBehaviours beyond wiring, data and logic separated, async engine calls with progress and cancellation.
- Python: type hints, pydantic models, docstrings with units, logging, seeded randomness, no hardcoded paths.
- Every pipeline stage callable independently (engine CLI) for testing.
- Documentation: README, architecture overview, and a plain English method note per module for designers.

---

## 13. QUESTIONS TO ASK ME BEFORE PHASE 1
1. Site area in hectares; DEM cell size and source.
2. DWG contents: contours with true Z, contours at Z = 0 with labels, or spot levels only.
3. Rainfall format: 24 hour depths or short duration intensities; any gauge time series.
4. Infiltration figure: rate in mm/hr or runoff coefficient; does it vary by zone.
5. External catchment draining into the park, and its extent.
6. Rock depth or borehole data.
7. Observed flooding records for calibration.
8. Area budget and target return period.
9. Maximum safe ponding depth per component.
10. Target platforms (Windows only, or also macOS) and minimum GPU.

---

## 14. KNOWN LIMITATIONS TO SHOW IN THE APP
- SWMM is one dimensional; surface spread comes from the 2D simulation and is indicative.
- Uncalibrated results are for comparing scenarios.
- Results are sensitive to the design storm pattern and infiltration values.
- Recharge well performance depends on subsurface data.

---

## 15. PHASED DELIVERY

| Phase | Scope | Acceptance criteria |
|---|---|---|
| 0. Foundations | Repos, shared JSON Schema, .sponge read and write in C# and Python, engine CLI, synthetic terrains | Project created in Python opens in Unity and round trips without loss |
| 1. Engine core | Rainfall and hyetographs, manual NbS from JSON, SWMM builder and runner, water balance, metrics | All seven return periods run on a synthetic site; continuity below 1 percent; matches hand built model |
| 2. Unity shell and terrain | Engine process management, DEM to mesh terrain, camera, overlays | Pilot DEM displays correctly with contours |
| 3. GPU flood simulation | Compute shader simulation, rendering, playback, live balance | Bowl terrain fills correctly; mass balance closes |
| 4. Survey import and baseline | DWG import, layer mapping UI, terrain review, baseline analysis and SWMM | DWG to terrain to baseline flood inside the app |
| 5. Editing tools | All tools, carving, validation, budget meter, undo and redo | Placing and moving elements updates terrain and live flood correctly |
| 6. Verification loop | Verify button, verified panel, live against verified comparison, GPU calibration | Live and SWMM volumes within agreed tolerance |
| 7. Proposal and ML | Placement, sizing, grading, NSGA-II, surrogate, Pareto options, accept, edit or start from scratch | Proposals generated, verified and editable |
| 8. Exports and reports | DXF, .3dm, schedules, report, video | Complete outputs for the pilot site |
| 9. Calibration and packaging | Calibration routine, PyInstaller bundle, installers | Installs and runs on a clean machine |

Start with Phase 0 and Phase 1 only. At the end of each phase, summarise what was built and tested, list assumptions made, and state what you need from me next.
