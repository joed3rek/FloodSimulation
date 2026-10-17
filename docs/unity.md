# Unity app (Phase 7)

`unity/SpongeParkApp` is the client-facing application: import a survey, set targets, generate or
optimise options, compare them with the existing site, simulate and animate storms, and export
drawings, Rhino files, the report and a video. Rhino is not needed.

It is a thin front end: every computation is done by the Python engine through the local API
(`spongepark serve`). The app never computes a reported number. Water animation is the 2D model
(indicative); volumes and litres are SWMM.

## Running it

1. Install the engine (`pip install -e .` in the repository) and start it: `spongepark serve`
   (the app can also start it: "Start engine", using `python` on the PATH).
2. Open `unity/SpongeParkApp` with Unity 6 (6000.3) and press Play, or build the player:
   `Unity -batchmode -quit -projectPath unity/SpongeParkApp -executeMethod SpongePark.EditorTools.BuildApp.Windows`
   (`BuildApp.MacOS` and `BuildApp.WebGL` need those build modules installed).
3. The app builds itself in any scene; no scene setup is needed.

The app opens on the same landing page as the web app: **New project** (the Windows file dialog
asks for the site survey DXF; on other systems an in-app browser does, answer the layer questions with the highlighted-layer pictures, Clean and
build) or **Open a project** (the file dialog, filtered to `.sponge` files). A `.sponge` passed on the command line (Windows
"Open with") opens directly. After that, the left panel walks through the steps:

| Step | Does |
|---|---|
| 1. Engine | Connects to (or starts) the engine |
| 2. Project | Opens or creates a `.sponge` project |
| 3. Survey | Reads the drawing's layers, shows the suggested layer map to check, imports it |
| 4. Targets | Area budget, sizing storm, maximum drawdown, inverse-mode storm (saved as your decisions) |
| 5. Analyse and design | Existing-site analysis; generate a layout; optimise (best retention, or least area) |
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
