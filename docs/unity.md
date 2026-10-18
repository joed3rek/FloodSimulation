# Unity app (Phase 7)

`unity/SpongeParkApp` is the client-facing application: import a survey, set targets, generate or
optimise options, compare them with the existing site, simulate and animate storms, and export
drawings, Rhino files, the report and a video. Rhino is not needed.

It is a thin front end: every computation is done by the Python engine through the local API
(`spongepark serve`). The app never computes a reported number. Water animation is the 2D model
(indicative); volumes and litres are SWMM.

## Running it

1. Install the engine (`pip install -e .` in the repository) and start it: `spongepark serve`
   (the app also starts it on its own from the landing page, using `python` on the PATH).
2. Open `unity/SpongeParkApp` with Unity 6 (6000.3) and press Play, or build the player:
   `Unity -batchmode -quit -projectPath unity/SpongeParkApp -executeMethod SpongePark.EditorTools.BuildApp.Windows`
   (`BuildApp.MacOS` and `BuildApp.WebGL` need those build modules installed).
3. The app builds itself in any scene; no scene setup is needed.

The app opens on a landing page in two columns. On the left (the wider one): **New project** (the Windows file dialog
asks for the site survey DXF; on other systems an in-app browser does, answer the layer questions with the highlighted-layer pictures, Clean and
build) or **Open a project** (the file dialog, filtered to `.sponge` files). On the right, **Recently opened** lists
the last 20 projects (newest first, the list scrolls) with their folder and when they were opened; one click reopens
a project, a file that has moved or been deleted is marked "file not found", × removes an entry (the file is not
touched) and "Clear list" empties it. Every successful open or create is added, from the landing or the sidebar.
The landing starts the engine itself if it is not running; a click that needs it waits for it (up to 30 s) and says
why if it does not come up. A `.sponge` passed on the command line (Windows "Open with") opens directly. **Home** at
the top of the sidebar returns to the landing. After that, the left panel walks through the steps:

| Step | Does |
|---|---|
| 1. Site model | Shown as soon as a project opens: the ground model with everything the survey drawing shows on it (compound wall, fences, gates, buildings, trees and palms, paths, roads, drains, manholes, poles, steps), one row per drawing layer with the surveyor's own layer names; click a row to show or hide that layer. Confirm the model to go on |
| 2. Flow and flooding | Shown once the site model is confirmed. Where water runs (flow lines, wider where more ground drains to them, and downhill arrows), where it collects (ponding hotspots, listed with depth and volume; click to go there) and where it leaves the park, from the ground alone. Plan (2D) shows it as a map. The flood simulation (depths, flooded area, the water animation) runs once rainfall and soil infiltration rates are in the project; it uses Itzi when set up |
| 3. Design | Draw NbS on the ground: rain garden, detention pond, retention pond (click the corners, double-click or Enter to finish), bioswale (click along its line), recharge well (one click). Select to move (drag) or change sizes; Delete, Undo/Redo (Ctrl+Z/Y). Each change is carved into the ground by the engine and checked (outside the park, over trees or paths, depth outside the safe range, over the area budget); the budget meter and the checks update. Elements are kept in the project's "design" scenario |
| 4. Targets | Area budget, sizing storm, maximum drawdown, inverse-mode storm (saved as your decisions) |
| 5. Analyse and propose | Existing-site SWMM analysis; generate a layout; optimise (best retention, or least area) |
| 6. Compare | Choose option and storm; retention and peak reduction against the existing site |
| 7. Simulate | Runs the 2D model for existing and proposed; play, restart, speed; live GPU mode; GPU verification |
| 8. View | Side by side or one view, existing/proposed toggle, vertical exaggeration, camera tour |
| 9. Export | Drawings + Rhino file + report; web viewer bundle; video of the storm |

The view shows the storm clock, the rainfall at that moment and a running count of litres kept on
site for each side (from the SWMM time series: rainfall so far minus water that has left).

## Water on the GPU

`Resources/WaterSim.compute` is a kernel-by-kernel port of the engine's 2D model
(`spongepark/engine/sim2d/gpu_reference.py` is the float32 reference of the same kernels, tested
against the engine model). Elevations are stored relative to the lowest ground point because float32
near 900 m resolves only about 0.06 mm, which made flat water surfaces unstable.

Verification on real hardware (`tests/test_unity_gpu.py`, run with `SPONGEPARK_TEST_UNITY=1`): the
shader run in Unity batch mode on an RTX 4060 (Direct3D 12) matched the engine to within 0.003 % of
rainfall on every water-balance term, and final depths within 0.07 mm. The in-app "Verify GPU vs
engine" button repeats the check on the open project (1 % tolerance).

## Video

"Record video of the storm" renders the storm at a fixed frame rate to PNGs and encodes an MP4 with
ffmpeg if it is on the PATH, otherwise through the engine (`/video/encode`, bundled ffmpeg).
Unattended runs for presentations:

```
SpongePark.exe -spProject park.sponge -spOption auto -spRp 25 -spVideo out/video [-spSpeed 3600] [-spEngineUrl http://127.0.0.1:8765]
```

## Web viewer (results only)

`spongepark viewer-bundle PROJECT OUT` writes the terrain, options, comparisons, litres curves and 2D
frames as JSON. Copy it to `Assets/StreamingAssets/bundle` and build WebGL: the viewer shows the
results without an engine (no computation, no editing).

## Not done / to check

- The macOS build and the WebGL build were not produced here (their build modules are not installed
  on this machine); the Windows build was built and run.
- The interface is Unity's immediate-mode GUI: functional, not yet designed.

## The site model

The survey intake builds the ground model and then `site/survey_layers.json`: every physical layer
of the cleaned drawing, placed on the ground (`spongepark site layers park.sponge` rebuilds it).

How things are drawn (display only; the survey gives positions, not heights):

| In the drawing | In the model |
|---|---|
| Compound walls, boundary walls, fences | Metal park fencing, 2 m, on a low stone plinth, with an opening at each gate. A park boundary with no wall or fence drawn along it is fenced the same way |
| Gate symbols (the X or block on plan) | One metal gate per symbol: stone pillars and two barred leaves, as wide as the symbol, set in line with the fence. A "gate" longer than 15 m is not a gate: it is drawn as a faint line and the layer is flagged |
| Buildings | 3 m blocks with flat roofs; outlines drawn as loose lines are joined into footprints |
| Trees and palms | Round crowns; canopy size from the drawn symbol where there is one |
| Roads | Dark grey surface between the kerb lines (loose kerb ends at the survey's break lines are joined across the road) |
| Footpaths | Sand-coloured surface: the narrow bands between path lines |
| Contours | Drawn by the terrain itself from the ground model (interval chosen from the relief), on the park only. The surveyor's contour layers are kept, hidden |

The ground model only covers where the survey has levels. For display, the park's own ground fills the
park boundary; outside it a smooth base (the roads and verges) is kept just below the park edge so it
never shows through the park. The analysis uses the surveyed ground only. Heights are shown true to
scale by default (View: height exaggeration).

**Contours in the ground.** By default the engine decides: with enough spot levels, drawn contours
are left out of the ground when one disagrees with the spot levels around it by more than a quarter
of the contour interval, or when they follow the spot levels closely (generated from them). The
reason is the first line of the survey's quality report. "Always use the drawn contours" in the
intake overrides this.
