// The client-facing application: one window that walks a non-technical user from survey import to a
// before/after video. Every number shown comes from the engine (SWMM, uncalibrated unless calibrated);
// water animation is the 2D model and is labelled indicative.
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace SpongePark
{
    public partial class SpongeParkApp : MonoBehaviour
    {
        const int LayerLeft = 8, LayerRight = 9;

        EngineClient api;
        EngineLauncher launcher;
        VideoCapture video;
        CameraRig rigLeft, rigRight;
        Camera camLeft, camRight;
        SiteView left, right;
        SiteFrame frame;

        // state
        bool engineUp, busy, bundle, siteConfirmed;
        JToken surveyLayers;   // what the survey drawing shows, layer by layer (/site/layers)
        string status = "Start the engine or open a results bundle.";
        string projectPath = "", drawingPath = "", layerMapJson = "", exportDir = "";
        float budgetPct = 10, maxDrawdownHr = 48, exaggeration = 3;   // heights x3 by default (the parks are nearly flat); x1 shows true heights
        int designRp = 5, targetRp = 10;
        List<string> options = new List<string>();
        List<int> returnPeriods = new List<int>();
        int optionIdx, rpIdx;
        JObject info;
        JToken comparison;
        string calibration = "uncalibrated: suitable for scenario comparison, not absolute prediction";
        bool sideBySide, showProposed = true, playing, live;
        float simT, speed = 600;   // simulated seconds per real second
        string verify = "";

        public static void Boot()
        {
            var go = new GameObject("SpongePark");
            go.AddComponent<SpongeParkApp>();
            DontDestroyOnLoad(go);
        }

        void Start()
        {
            // keep polling engine jobs (optimise, SWMM, 2D runs) while the window is behind another one;
            // OnApplicationFocus throttles the frame rate meanwhile
            Application.runInBackground = true;
            api = gameObject.AddComponent<EngineClient>();
            launcher = gameObject.AddComponent<EngineLauncher>();
            exportDir = Path.Combine(Application.persistentDataPath, "exports");
            var light = new GameObject("sun").AddComponent<Light>();
            light.type = LightType.Directional;
            light.transform.rotation = Quaternion.Euler(50, -30, 0);
            SetupAtmosphere(light);
            // the workspace's background behind everything (the panels are outside the scene cameras' viewport)
            var bg = new GameObject("background").AddComponent<Camera>();
            bg.cullingMask = 0;
            bg.depth = -10;
            bg.clearFlags = CameraClearFlags.SolidColor;
            bg.backgroundColor = new Color32(0x16, 0x18, 0x1B, 0xFF);
            camLeft = MakeCamera("camera left", LayerLeft, out rigLeft);
            camRight = MakeCamera("camera right", LayerRight, out rigRight);
            rigRight.Follow = rigLeft;
            MakeRain();
            MakeSky();
            if (Camera.main != null && Camera.main != camLeft && Camera.main != camRight) Camera.main.enabled = false;
            video = camLeft.gameObject.AddComponent<VideoCapture>();
            left = SiteView.Create("existing", transform, LayerLeft);
            right = SiteView.Create("proposed", transform, LayerRight);
            ApplyViewports();
#if UNITY_WEBGL && !UNITY_EDITOR
            bundle = true;
            BuildUi();
            StartCoroutine(OpenBundle());
#else
            BuildUi();
            if (Arg("-spProject") != null) StartCoroutine(Autorun());
            else
            {
                ShowLanding();
                StartCoroutine(CheckEngine());
                if (Arg("-spShot") != null) StartCoroutine(Shot());
                if (System.Environment.GetCommandLineArgs().Contains("-spNewProject")) StartCoroutine(Later(3, NewProjectNow()));
                // "Open with" / double-click: the .sponge file arrives as an argument
                var sponge = System.Environment.GetCommandLineArgs().Skip(1).FirstOrDefault(a => a.EndsWith(".sponge", System.StringComparison.OrdinalIgnoreCase));
                if (sponge != null) StartCoroutine(OpenWhenReady(sponge));
            }
#endif
        }

        // behind another window: a few frames a second are enough to poll jobs (not in screenshot or autorun mode)
        void OnApplicationFocus(bool focused)
        {
            if (Arg("-spShot") != null || Arg("-spProject") != null) return;
            Application.targetFrameRate = focused ? -1 : 10;
        }

        static string Arg(string name)
        {
            var a = System.Environment.GetCommandLineArgs();
            int i = System.Array.IndexOf(a, name);
            return i >= 0 && i + 1 < a.Length ? a[i + 1] : null;
        }

        // Unattended run, e.g. for a presentation video or a smoke test:
        //   SpongePark.exe -spProject park.sponge -spOption auto -spRp 25 -spVideo out/video [-spSpeed 3600]
        //                  [-spPython path/to/python] [-spEngineDir repo/folder] [-spEngineUrl http://127.0.0.1:8765]
        IEnumerator Autorun()
        {
            projectPath = Arg("-spProject");
            if (Arg("-spEngineUrl") != null) api.baseUrl = Arg("-spEngineUrl");
            if (Arg("-spPython") != null) launcher.PythonExe = Arg("-spPython");
            if (Arg("-spEngineDir") != null) launcher.WorkingDir = Arg("-spEngineDir");
            yield return CheckEngine();
            Debug.Log($"autorun: engine at {api.baseUrl} {(engineUp ? "reachable" : "not reachable")}");
            if (!engineUp)
            {
                launcher.Launch();
                for (int i = 0; i < 60 && !engineUp; i++) { yield return new WaitForSecondsRealtime(1); yield return CheckEngine(); }
            }
            if (!engineUp) { Debug.LogError("autorun: engine not reachable"); Application.Quit(2); yield break; }
            yield return OpenProject(false);
            var opt = Arg("-spOption") ?? "auto";
            optionIdx = Mathf.Max(0, options.IndexOf(opt));
            if (int.TryParse(Arg("-spRp"), out var rp)) rpIdx = Mathf.Max(0, returnPeriods.IndexOf(rp));
            if (float.TryParse(Arg("-spSpeed"), out var sp)) speed = sp;
            yield return Simulate();
            if (left.Frames == null || right.Frames == null) { Debug.LogError("autorun: no 2D frames"); Application.Quit(3); yield break; }
            var dir = Arg("-spVideo");
            if (dir != null) { video.Begin(dir); rigLeft.Touring = true; }
            simT = 0;
            playing = true;
            autorunQuit = true;
        }

        bool autorunQuit;

        // test switch: press New project as soon as the engine answers
        IEnumerator NewProjectNow()
        {
            for (int i = 0; i < 20 && !engineUp; i++) { yield return CheckEngine(); yield return new WaitForSecondsRealtime(0.5f); }
            PickFile("Choose the site survey (DXF)", "Site survey", "dxf,dwg", p => StartCoroutine(StartIntake(p)));
        }

        IEnumerator OpenWhenReady(string sponge)
        {
            for (int i = 0; i < 30 && !engineUp; i++) { yield return new WaitForSecondsRealtime(1); yield return CheckEngine(); }
            if (engineUp) yield return OpenExisting(sponge);
        }

        // Screenshot for checks and documentation: -spShot out.png [-spSurvey drawing.dxf] [-spEngineUrl url]
        IEnumerator Shot()
        {
            if (Arg("-spEngineUrl") != null) api.baseUrl = Arg("-spEngineUrl");
            yield return CheckEngine();
            if (Arg("-spSurvey") != null) yield return StartIntake(Arg("-spSurvey"));
            yield return new WaitForSecondsRealtime(float.TryParse(Arg("-spWait"), out var wait) ? wait : 6);   // -spWait s
            // intake plan checks: -spZoomLayer <layer> highlights and zooms to it; -spPanelClosed hides the questions
            if (plan != null && Arg("-spZoomLayer") != null) { Focus(Arg("-spZoomLayer")); plan.ZoomToLayer(Arg("-spZoomLayer")); }
            if (plan != null && System.Environment.GetCommandLineArgs().Contains("-spPanelClosed")) SetPanel(false);
            // site model checks: -spOnly <layer> shows just that survey layer; -spPitch <deg> looks from higher up
            if (Arg("-spOnly") != null) { SetAllLayers(false); SetLayer(Arg("-spOnly"), true); }
            if (float.TryParse(Arg("-spPitch"), out var pitch)) { rigLeft.Pitch = pitch; rigLeft.Plan = false; }
            if (float.TryParse(Arg("-spZoom"), out var zoomBy)) rigLeft.Distance /= zoomBy;
            if (float.TryParse(Arg("-spYaw"), out var yaw)) rigLeft.Yaw = yaw;
            if (System.Environment.GetCommandLineArgs().Contains("-spPlan")) rigLeft.Plan = true;
            var look = Arg("-spLookAt")?.Split(',');   // -spLookAt x,y (survey metres)
            if (look != null && look.Length == 2 && frame != null && float.TryParse(look[0], out var lx) && float.TryParse(look[1], out var ly))
                rigLeft.Target = frame.World(lx, ly, left.Terrain.GroundAt(lx, ly) is var gz && !float.IsNaN(gz) ? gz : frame.ZRef);
            yield return new WaitForSecondsRealtime(1);
            if (Arg("-spDraw") != null) { foreach (var d in Arg("-spDraw").Split('|')) yield return DrawForTest(d); yield return new WaitForSecondsRealtime(2); }   // several: a|b
            // workspace checks: -spPanel <name> opens a panel, tab or dialog, or runs a command (several:
            // -spPanel tab:design,checks,run:live); -spScroll <px> scrolls the open Properties tab
            if (Arg("-spPanel") != null) foreach (var name in Arg("-spPanel").Split(',')) OpenPanel(name.Trim());
            if (float.TryParse(Arg("-spAfter"), out var after)) yield return new WaitForSecondsRealtime(after);   // -spAfter s: let the storm play
            if (float.TryParse(Arg("-spScroll"), out var sc) && props != null) props.Page(ui.PropsTab).scrollOffset = new Vector2(0, sc);
            yield return new WaitForSecondsRealtime(0.5f);
            Debug.Log($"camera: plan {rigLeft.Plan} pitch {rigLeft.Pitch} yaw {rigLeft.Yaw} distance {rigLeft.Distance} ortho {camLeft.orthographic}");
            Debug.Log($"frame rate: {1f / Mathf.Max(1e-4f, Time.smoothDeltaTime):0} fps");
            Debug.Log($"design: confirmed {siteConfirmed}, loaded {designFc != null}, draw tools {(commands["tool-rain_garden"].Enabled() ? "enabled" : "disabled")}, tool {tool ?? "select"}");
            if (plan != null) Debug.Log($"plan zoom {plan.Zoom:0.000} offset {plan.Offset} size {plan.contentRect.size}");
            ScreenCapture.CaptureScreenshot(Arg("-spShot"));
            yield return new WaitForSecondsRealtime(2);
            Application.Quit(0);
        }

        IEnumerator FinishVideo()
        {
            video.End();
            if (video.Result.Contains("not found") || video.Result.Contains("failed"))
                yield return api.Send("POST", "/video/encode", new { folder = video.Folder, fps = video.Fps },
                                      r => video.Result = r != null ? "video: " + r["video"] : video.Result);
            Debug.Log("video: " + video.Result);
            if (autorunQuit) Application.Quit(0);
        }

        Camera MakeCamera(string name, int layer, out CameraRig rig)
        {
            var go = new GameObject(name);
            var cam = go.AddComponent<Camera>();
            cam.cullingMask = 1 << layer;
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = new Color32(0x1A, 0x1D, 0x21, 0xFF);   // the dark workspace's plan
            cam.farClipPlane = 5000;
            rig = go.AddComponent<CameraRig>();
            return cam;
        }

        /// The cameras fill the workspace's viewport (viewRect, set from its layout); split view halves it.
        void ApplyViewports()
        {
            var r = viewRect;
            camLeft.rect = sideBySide ? new Rect(r.x, r.y, r.width / 2, r.height) : r;
            camRight.rect = new Rect(r.x + r.width / 2, r.y, r.width / 2, r.height);
            camRight.enabled = sideBySide;
            if (!sideBySide)
                camLeft.cullingMask = 1 << (showProposed ? LayerRight : LayerLeft);
            else
                camLeft.cullingMask = 1 << LayerLeft;
        }

        IEnumerator CheckEngine()
        {
            yield return api.Health(ok => engineUp = ok);
            status = engineUp ? "Engine connected. Open or create a project." : "Engine not running.";
        }

        IEnumerator OpenBundle()
        {
            bundle = true;
            api.bundleMode = true;
            JObject m = null;
            yield return api.OpenBundle(r => m = r);
            if (m == null) { status = "No results bundle found in StreamingAssets/bundle."; yield break; }
            options = ((JObject)m["options"]).Properties().Select(p => p.Name).ToList();
            calibration = (string)m["calibration"] == "uncalibrated" ? calibration : (string)m["calibration"];
            var first = options.FirstOrDefault(o => o != "baseline");
            returnPeriods = first != null ? m["options"][first]["sim2d"].ToObject<List<int>>() : new List<int>();
            optionIdx = Mathf.Max(0, options.IndexOf(first));
            status = $"Results viewer: {m["project"]}";
            if (returnPeriods.Count > 0) yield return LoadViews();
        }

        // ------------------------------------------------------------ engine actions
        IEnumerator Run(IEnumerator work, string what)
        {
            busy = true;
            api.ClearError();   // only errors from this piece of work are reported
            status = what + "...";
            yield return work;
            busy = false;
            if (!string.IsNullOrEmpty(api.LastError)) status = "Error: " + api.LastError;
        }

        IEnumerator OpenProject(bool create)
        {
            JToken r = null;
            yield return api.Open(projectPath, create, x => r = x);
            if (r == null) yield break;
            surveyLayers = null;
            layerVisible.Clear();
            flowData = null;
            groundFor = null;
            groundSaved = null;
            rainSaved = null;
            planSetFor = false;
            designFc = null;
            designFor = null;
            viewsFor = null;
            selectedId = null;
            tool = null;
            yield return Refresh();
            yield return LoadOnboarding();
            designVerified = false;
            designDirty = false;
            Remember((string)r["path"] ?? projectPath, (string)r["name"]);   // the engine's resolved path
            status = $"Opened {(string)r["name"]}.";
            // show the site straight away: the ground model and what the survey drawing shows
            if (info != null && (bool?)info["has_terrain"] == true) StartCoroutine(Run(LoadViews(), "Loading the site model"));
        }

        IEnumerator ConfirmSite(bool confirmed)
        {
            JToken r = null;
            yield return api.Send("POST", api.P("/site/confirm"), new { confirmed }, x => r = x);
            if (r == null) yield break;
            siteConfirmed = confirmed;
            status = confirmed ? "Site model confirmed. The Analyse tab shows where water runs and collects." : "Site model reopened.";
            if (confirmed) yield return LoadFlow();
        }

        IEnumerator Refresh()
        {
            JToken r = null;
            yield return api.Get(api.P(""), x => r = x);
            if (r == null) yield break;
            info = (JObject)r;
            // the designer's own scenario is worked on in Step 3, not chosen among the options
            options = r["options"].ToObject<List<string>>().Where(o => !o.StartsWith("_") && o != DesignScenario).ToList();
            JToken ps = null;
            yield return api.Get(api.P("/parameters?prefix=project.return_periods"), x => ps = x);
            if (ps != null && ps.Any()) returnPeriods = ps[0]["value"].ToObject<List<int>>();
            siteConfirmed = (bool?)r["site_confirmed"] == true;
            calibration = (string)r["calibration"] == "uncalibrated"
                ? "uncalibrated: suitable for scenario comparison, not absolute prediction" : (string)r["calibration"];
        }

        IEnumerator InspectSurvey()
        {
            JToken r = null;
            yield return api.Send("POST", api.P("/survey/inspect"), new { drawing = drawingPath }, x => r = x);
            if (r != null) layerMapJson = r["suggested_layer_map"].ToString();
            status = "Check the layer map (roles), set \"confirmed\": true, then import.";
        }

        IEnumerator ImportSurvey()
        {
            var map = JObject.Parse(layerMapJson);
            JToken r = null;
            yield return api.RunJob("POST", api.P("/survey/import"), new { drawing = drawingPath, layer_map = map }, x => r = x, s => status = "importing survey: " + s);
            if (r != null) status = $"Terrain built. Spot level RMSE {(float?)r["spot_cross_validation"]?["rmse_m"] ?? 0:0.000} m. Issues: {r["issues"]?.Count() ?? 0}";
        }

        IEnumerator SetTargets()
        {
            yield return api.Send("PUT", api.P("/parameters/layout.max_area_pct"), new { value = budgetPct, unit = "%" }, null);
            yield return api.Send("PUT", api.P("/parameters/layout.design_return_period_yr"), new { value = designRp, unit = "yr" }, null);
            yield return api.Send("PUT", api.P("/parameters/nbs.max_drawdown_hr"), new { value = maxDrawdownHr, unit = "hr" }, null);
            yield return api.Send("PUT", api.P("/parameters/optimise.target_return_period_yr"), new { value = targetRp, unit = "yr" }, null);
            status = "Targets saved as your decisions.";
        }

        IEnumerator Baseline()
        {
            yield return api.RunJob("POST", api.P("/baseline"), null, r => { }, s => status = "existing site analysis: " + s);
            yield return Refresh();
            status = "Existing site analysed (SWMM, all return periods).";
        }

        IEnumerator Generate(bool optimise, string mode = "forward")
        {
            if (optimise)
                yield return api.RunJob("POST", api.P("/optimise"), new { mode }, r => { }, s => status = "optimising (SWMM-verified): " + s);
            else
                yield return api.RunJob("POST", api.P("/options/auto/generate"), new { run = true }, r => { }, s => status = "generating layout: " + s);
            yield return Refresh();
            var o = options.FindIndex(x => x != "baseline");
            optionIdx = Mathf.Max(0, o);
            yield return LoadComparison();
            status = "Options ready.";
        }

        IEnumerator LoadComparison()
        {
            var opt = CurrentOption;
            comparison = null;
            if (opt == null || opt == "baseline" || opt == DesignScenario) yield break;
            if (bundle) yield return api.LoadBundleFile($"comparison_{opt}.json", r => comparison = r);
            else yield return api.Get(api.P($"/options/{opt}/comparison"), r => comparison = r);
        }

        IEnumerator Simulate()
        {
            var rp = CurrentRp;
            foreach (var o in new[] { "baseline", CurrentOption })
                yield return api.RunJob("POST", api.P($"/options/{o}/sim2d/{rp}"), null, r => { }, s => status = $"2D simulation {o}: {s}");
            yield return LoadViews();
        }

        IEnumerator LoadViews()
        {
            var rp = CurrentRp;
            JToken t = null;
            if (bundle) yield return api.LoadBundleFile("terrain_existing.json", r => t = r);
            else yield return api.Get(api.P("/terrain"), r => t = r);
            if (t == null) { status = "no terrain"; yield break; }
            frame = SiteFrame.From(HeightGrid.FromPayload(t), exaggeration);
            viewsFor = projectPath;
            left.Option = "baseline";
            right.Option = CurrentOption ?? "baseline";
            yield return left.Load(api, frame, rp, bundle);
            yield return right.Load(api, frame, rp, bundle);
            if (!bundle && surveyLayers == null && (bool?)info?["has_survey"] == true)
            {
                status = "Placing the survey's walls, trees and paths on the ground (a large drawing can take a minute the first time)…";
                yield return api.Get(api.P("/site/layers"), x => surveyLayers = x, 600);
            }
            FillSiteLayers();
            bool contours = !layerVisible.TryGetValue(ContoursLayer, out var con) || con;
            left.Terrain.SetContours(contours);
            right.Terrain.SetContours(contours);
            left.Survey.Build(surveyLayers, frame, layerVisible, left.Terrain.GroundAt, left.Terrain.InPark);
            right.Survey.Build(surveyLayers, frame, layerVisible, left.Terrain.GroundAt, left.Terrain.InPark);
            if (siteConfirmed && !bundle) yield return LoadFlow();
            yield return LoadComparison();
            if (designFor == projectPath && designFc != null && siteConfirmed) { yield return ShowDesignGround(); RefreshDesign(); }
            // with nothing to compare yet (only the existing site), one full view of it
            if (right.Option == "baseline" && !bundle) { sideBySide = false; showProposed = false; ApplyViewports(); }
            var b = left.Terrain.GetComponent<MeshFilter>().sharedMesh.bounds;
            rigLeft.Frame(b, sideBySide); rigRight.Frame(b, sideBySide);
            simT = 0;
            status = left.Frames != null ? $"{CurrentRp}-yr storm loaded. Press Play."
                : "Site model loaded: drag to orbit, scroll to zoom. Check the layers in Contents.";
        }

        IEnumerator StartLive()
        {
            if (!GpuWaterSim.Supported) { status = "This computer has no compute shader support; use replay."; yield break; }
            yield return left.StartGpu(api, frame, CurrentRp);
            yield return right.StartGpu(api, frame, CurrentRp);
            live = true;
            simT = 0;
        }

        IEnumerator VerifyGpu()
        {
            // the same case as the engine: compare volumes with the engine's 2D summary
            var o = CurrentOption;
            JToken inp = null, eng = null;
            yield return api.Get(api.P($"/options/{o}/sim2d/{CurrentRp}/inputs"), r => inp = r);
            yield return api.Get(api.P($"/options/{o}/sim2d/{CurrentRp}/summary"), r => eng = r);
            if (inp == null || eng == null) { verify = "run the 2D simulation in the engine first"; yield break; }
            using var sim = new GpuWaterSim();
            sim.Init(inp);
            sim.RunToEnd();
            var gpu = sim.Balance();
            var rain = (double)eng["balance"]["rainfall_m3"];
            var lines = new List<string>();
            bool ok = true;
            foreach (var key in gpu.Keys)
            {
                double e = (double)eng["balance"][key], g = gpu[key];
                double diff = 100 * (g - e) / rain;
                ok &= System.Math.Abs(diff) <= 1.0;
                lines.Add($"{key}: engine {e:0.0}, GPU {g:0.0} m3 ({diff:+0.00;-0.00} % of rain)");
            }
            verify = (ok ? "PASS" : "CHECK") + " (tolerance 1 % of rainfall)\n" + string.Join("\n", lines);
        }

        string CurrentOption => options.Count == 0 ? null : options[Mathf.Clamp(optionIdx, 0, options.Count - 1)];
        int CurrentRp => returnPeriods.Count == 0 ? 0 : returnPeriods[Mathf.Clamp(rpIdx, 0, returnPeriods.Count - 1)];

        // ------------------------------------------------------------ frame update
        void Update()
        {
            DesignInput();
            UpdateWeather();
            if (!playing) return;
            float dtSim = Time.deltaTime * speed;
            simT += dtSim;
            float end = Mathf.Max(left.EndTime, right.EndTime);
            if (end > 0 && simT >= end)
            {
                simT = end;
                playing = false;
                if (video.Recording) StartCoroutine(FinishVideo());
                else if (autorunQuit) Application.Quit(0);
            }
            left.ShowAt(simT, live, live ? dtSim : 0);
            right.ShowAt(simT, live, live ? dtSim : 0);
        }

        IEnumerator Later(float s, IEnumerator then)
        {
            yield return new WaitForSecondsRealtime(s);
            yield return then;
        }
    }

    public static class Bootstrap
    {
        // The app builds itself in any scene (no scene editing needed): open the project, press Play.
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Init()
        {
            if (Object.FindFirstObjectByType<SpongeParkApp>() == null) SpongeParkApp.Boot();
        }
    }
}
