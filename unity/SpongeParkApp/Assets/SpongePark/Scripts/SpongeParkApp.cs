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
    public class SpongeParkApp : MonoBehaviour
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
        bool engineUp, busy, bundle;
        string status = "Start the engine or open a results bundle.";
        string projectPath = "", drawingPath = "", layerMapJson = "", exportDir = "";
        float budgetPct = 10, maxDrawdownHr = 48, exaggeration = 5;
        int designRp = 5, targetRp = 10;
        List<string> options = new List<string>();
        List<int> returnPeriods = new List<int>();
        int optionIdx, rpIdx;
        JObject info;
        JToken comparison;
        string calibration = "uncalibrated: suitable for scenario comparison, not absolute prediction";
        bool sideBySide = true, showProposed = true, playing, live;
        float simT, speed = 600;   // simulated seconds per real second
        Vector2 scroll;
        string verify = "";

        public static void Boot()
        {
            var go = new GameObject("SpongePark");
            go.AddComponent<SpongeParkApp>();
            DontDestroyOnLoad(go);
        }

        void Start()
        {
            api = gameObject.AddComponent<EngineClient>();
            launcher = gameObject.AddComponent<EngineLauncher>();
            exportDir = Path.Combine(Application.persistentDataPath, "exports");
            var light = new GameObject("sun").AddComponent<Light>();
            light.type = LightType.Directional;
            light.transform.rotation = Quaternion.Euler(50, -30, 0);
            camLeft = MakeCamera("camera left", LayerLeft, out rigLeft);
            camRight = MakeCamera("camera right", LayerRight, out rigRight);
            rigRight.Follow = rigLeft;
            if (Camera.main != null && Camera.main != camLeft && Camera.main != camRight) Camera.main.enabled = false;
            video = camLeft.gameObject.AddComponent<VideoCapture>();
            left = SiteView.Create("existing", transform, LayerLeft);
            right = SiteView.Create("proposed", transform, LayerRight);
            ApplyViewports();
#if UNITY_WEBGL && !UNITY_EDITOR
            StartCoroutine(OpenBundle());
#else
            if (Arg("-spProject") != null) StartCoroutine(Autorun());
            else StartCoroutine(CheckEngine());
#endif
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
            cam.backgroundColor = new Color(0.93f, 0.95f, 0.94f);
            cam.farClipPlane = 5000;
            rig = go.AddComponent<CameraRig>();
            return cam;
        }

        void ApplyViewports()
        {
            camLeft.rect = sideBySide ? new Rect(0.28f, 0, 0.36f, 1) : new Rect(0.28f, 0, 0.72f, 1);
            camRight.rect = new Rect(0.64f, 0, 0.36f, 1);
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
            yield return Refresh();
            status = $"Opened {(string)r["name"]}.";
        }

        IEnumerator Refresh()
        {
            JToken r = null;
            yield return api.Get(api.P(""), x => r = x);
            if (r == null) yield break;
            info = (JObject)r;
            options = r["options"].ToObject<List<string>>().Where(o => !o.StartsWith("_")).ToList();
            JToken ps = null;
            yield return api.Get(api.P("/parameters?prefix=project.return_periods"), x => ps = x);
            if (ps != null && ps.Any()) returnPeriods = ps[0]["value"].ToObject<List<int>>();
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
            if (opt == null || opt == "baseline") yield break;
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
            left.Option = "baseline";
            right.Option = CurrentOption ?? "baseline";
            yield return left.Load(api, frame, rp, bundle);
            yield return right.Load(api, frame, rp, bundle);
            yield return LoadComparison();
            var b = left.Terrain.GetComponent<MeshFilter>().sharedMesh.bounds;
            rigLeft.Frame(b); rigRight.Frame(b);
            simT = 0;
            status = $"{CurrentRp}-yr storm loaded. Press Play.";
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

        // ------------------------------------------------------------ UI
        void OnGUI()
        {
            GUILayout.BeginArea(new Rect(8, 8, Screen.width * 0.28f - 16, Screen.height - 16), GUI.skin.box);
            scroll = GUILayout.BeginScrollView(scroll);
            GUILayout.Label("<b>Sponge Park</b>", new GUIStyle(GUI.skin.label) { richText = true, fontSize = 18 });
            GUILayout.Label(status, GUI.skin.textArea);
            GUI.enabled = !busy;

            if (!bundle)
            {
                Section("1. Engine");
                GUILayout.Label(engineUp ? "connected" : "not running " + launcher.Message);
                GUILayout.BeginHorizontal();
                if (GUILayout.Button("Start engine")) { launcher.Launch(); StartCoroutine(Later(4, CheckEngine())); }
                if (GUILayout.Button("Check")) StartCoroutine(CheckEngine());
                if (GUILayout.Button("Results bundle")) StartCoroutine(OpenBundle());
                GUILayout.EndHorizontal();

                Section("2. Project");
                projectPath = Field("Project file (.sponge)", projectPath);
                GUILayout.BeginHorizontal();
                if (GUILayout.Button("Open")) StartCoroutine(Run(OpenProject(false), "opening"));
                if (GUILayout.Button("Create")) StartCoroutine(Run(OpenProject(true), "creating"));
                GUILayout.EndHorizontal();
                if (info != null)
                    GUILayout.Label($"{info["name"]}: terrain {(bool)info["has_terrain"]}, existing site analysed {(bool)info["has_baseline"]}, " +
                                    $"{info["unconfirmed_parameters"]} defaults to confirm");

                Section("3. Survey");
                drawingPath = Field("Survey drawing (.dxf / .dwg)", drawingPath);
                if (GUILayout.Button("Read layers")) StartCoroutine(Run(InspectSurvey(), "reading layers"));
                if (!string.IsNullOrEmpty(layerMapJson))
                {
                    layerMapJson = GUILayout.TextArea(layerMapJson, GUILayout.Height(140));
                    if (GUILayout.Button("Import survey")) StartCoroutine(Run(ImportSurvey(), "importing"));
                }

                Section("4. Targets");
                budgetPct = Slider("Area budget (% of site)", budgetPct, 2, 30);
                designRp = IntField("Size elements for storm (yr)", designRp);
                maxDrawdownHr = Slider("Maximum drawdown (h)", maxDrawdownHr, 12, 96);
                targetRp = IntField("Inverse mode: retain storm (yr)", targetRp);
                if (GUILayout.Button("Save targets")) StartCoroutine(Run(SetTargets(), "saving targets"));

                Section("5. Analyse and design");
                if (GUILayout.Button("Analyse existing site")) StartCoroutine(Run(Baseline(), "analysing"));
                GUILayout.BeginHorizontal();
                if (GUILayout.Button("Generate layout")) StartCoroutine(Run(Generate(false), "generating"));
                if (GUILayout.Button("Optimise")) StartCoroutine(Run(Generate(true), "optimising"));
                if (GUILayout.Button("Least area")) StartCoroutine(Run(Generate(true, "inverse"), "optimising"));
                GUILayout.EndHorizontal();
            }

            Section("6. Compare");
            if (options.Count > 0)
            {
                var newIdx = GUILayout.SelectionGrid(optionIdx, options.ToArray(), 3);
                if (newIdx != optionIdx) { optionIdx = newIdx; StartCoroutine(LoadComparison()); }
            }
            if (returnPeriods.Count > 0)
                rpIdx = GUILayout.SelectionGrid(rpIdx, returnPeriods.Select(r => r + "-yr").ToArray(), 4);
            GUILayout.Label(calibration);
            if (comparison != null)
            {
                GUILayout.Label($"Largest storm fully retained: {(comparison["design_retention_storm_yr"]?.Type == JTokenType.Null ? "none" : comparison["design_retention_storm_yr"] + "-yr")}");
                foreach (var row in comparison["rows"])
                    GUILayout.Label($"{row["return_period_yr"]}-yr: retained {(float)row["option_retained_pct"]:0}% (now {(float)row["baseline_retained_pct"]:0}%), " +
                                    $"peak {(row["peak_reduction_pct"].Type == JTokenType.Null ? 0 : (float)row["peak_reduction_pct"]):0}% lower");
            }

            Section("7. Simulate (2D, indicative)");
            if (!bundle && GUILayout.Button("Run 2D simulation (existing + proposed)")) StartCoroutine(Run(Simulate(), "simulating"));
            if (GUILayout.Button("Load storm")) StartCoroutine(Run(LoadViews(), "loading"));
            GUILayout.BeginHorizontal();
            if (GUILayout.Button(playing ? "Pause" : "Play")) playing = !playing;
            if (GUILayout.Button("Restart")) { simT = 0; if (live) StartCoroutine(StartLive()); }
            GUILayout.EndHorizontal();
            speed = Slider("Speed (sim s per s)", speed, 30, 3600);
            if (!bundle)
            {
                GUILayout.BeginHorizontal();
                if (GUILayout.Button(live ? "Live GPU: on" : "Live GPU: off")) { if (live) live = false; else StartCoroutine(StartLive()); }
                if (GUILayout.Button("Verify GPU vs engine")) StartCoroutine(Run(VerifyGpu(), "verifying"));
                GUILayout.EndHorizontal();
                if (!string.IsNullOrEmpty(verify)) GUILayout.Label(verify, GUI.skin.textArea);
            }
            GUILayout.Label($"Time {simT / 3600f:0.00} h");
            float litres = right.LitresAt(simT / 3600f), before = left.LitresAt(simT / 3600f);
            GUILayout.Label($"<size=16><b>{litres:N0} litres</b> kept in the park</size>\n(existing site: {before:N0} L) - SWMM",
                            new GUIStyle(GUI.skin.label) { richText = true });

            Section("8. View");
            var sbs = GUILayout.Toggle(sideBySide, "Side by side (existing | proposed)");
            var prop = sideBySide || GUILayout.Toggle(showProposed, "Show proposed (else existing)");
            if (sbs != sideBySide || (!sideBySide && prop != showProposed)) { sideBySide = sbs; showProposed = prop; ApplyViewports(); }
            exaggeration = Slider("Vertical exaggeration (applies on Load storm)", exaggeration, 1, 20);
            rigLeft.Touring = GUILayout.Toggle(rigLeft.Touring, "Camera tour");

            Section("9. Export");
            exportDir = Field("Folder", exportDir);
            if (!bundle && GUILayout.Button("Drawings, Rhino file and report"))
                StartCoroutine(Run(api.RunJob("POST", api.P($"/options/{CurrentOption}/export"), new { out_dir = exportDir }, r => status = r?.ToString() ?? status), "exporting"));
            if (!bundle && GUILayout.Button("Results bundle for the web viewer"))
                StartCoroutine(Run(api.RunJob("POST", api.P("/viewer-bundle"), new { out_dir = Path.Combine(exportDir, "bundle") }, r => status = "bundle written"), "bundling"));
            if (!video.Recording && GUILayout.Button("Record video of the storm"))
            {
                simT = 0; playing = true; rigLeft.Touring = true;
                video.Begin(Path.Combine(exportDir, "video"));
            }
            if (!string.IsNullOrEmpty(video.Result)) GUILayout.Label(video.Result);
            GUI.enabled = true;
            GUILayout.EndScrollView();
            GUILayout.EndArea();

            // labels on the views
            var style = new GUIStyle(GUI.skin.label) { fontSize = 14, normal = { textColor = Color.black } };
            if (sideBySide)
            {
                GUI.Label(new Rect(Screen.width * 0.29f, 10, 400, 24), "Existing", style);
                GUI.Label(new Rect(Screen.width * 0.65f, 10, 400, 24), "Proposed: " + (CurrentOption ?? "-"), style);
            }
            GUI.Label(new Rect(Screen.width * 0.29f, Screen.height - 28, 900, 24),
                      "Water animation: 2D model, indicative. Volumes and litres: SWMM, " + calibration, style);
            // headline overlay: time, rain and litres kept, readable in videos
            var big = new GUIStyle(GUI.skin.label) { fontSize = 20, richText = true, normal = { textColor = new Color(0.08f, 0.13f, 0.12f) } };
            float th = simT / 3600f;
            string rainNow = left.RainAt(th) > 0 ? $"rain {left.RainAt(th):0} mm/h" : "no rain";
            GUI.Label(new Rect(Screen.width * 0.29f, 34, 700, 30), $"{CurrentRp}-yr storm   {th:0.0} h   {rainNow}", big);
            if (sideBySide)
            {
                GUI.Label(new Rect(Screen.width * 0.29f, Screen.height - 70, 420, 36), $"<b>{left.LitresAt(th):N0} L</b> kept on site", big);
                GUI.Label(new Rect(Screen.width * 0.65f, Screen.height - 70, 420, 36), $"<b>{right.LitresAt(th):N0} L</b> kept on site", big);
            }
            else
            {
                var v = showProposed ? right : left;
                GUI.Label(new Rect(Screen.width * 0.29f, Screen.height - 70, 600, 36), $"<b>{v.LitresAt(th):N0} L</b> kept on site", big);
            }
        }

        static void Section(string title) => GUILayout.Label($"<b>{title}</b>", new GUIStyle(GUI.skin.label) { richText = true, fontSize = 13 });

        static string Field(string label, string value)
        {
            GUILayout.Label(label);
            return GUILayout.TextField(value ?? "");
        }

        static float Slider(string label, float v, float lo, float hi)
        {
            GUILayout.Label($"{label}: {v:0.#}");
            return GUILayout.HorizontalSlider(v, lo, hi);
        }

        static int IntField(string label, int v)
        {
            GUILayout.BeginHorizontal();
            GUILayout.Label(label);
            int.TryParse(GUILayout.TextField(v.ToString(), GUILayout.Width(50)), out var r);
            GUILayout.EndHorizontal();
            return r == 0 ? v : r;
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
