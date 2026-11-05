// After the analysis, on the Analyse tab: pointing at a water path shows the water running along it, arrows moving
// downhill; pointing at a pool shows where its water comes from, running down the ground that drains to it, and the
// pool filling. A click keeps it showing until Esc or a click elsewhere. Everything is built from the flow data already
// loaded, so nothing is asked of the engine and there is nothing to wait for.
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace SpongePark
{
    public partial class SpongeParkApp
    {
        const float ArrowSpacing = 3f, ArrowSpeed = 3.5f, FillSeconds = 6f;

        class FlowPath
        {
            public readonly List<Vector3> Points = new List<Vector3>();
            public readonly List<Vector2> Plan = new List<Vector2>();
            public readonly List<float> Along = new List<float>();
            public float Length => Along.Count > 0 ? Along[Along.Count - 1] : 0f;
        }

        class FlowTarget
        {
            public string Words;
            public readonly List<FlowPath> Paths = new List<FlowPath>();
            public List<Vector2> Ring;              // a pool's edge, in plan
            public float Bottom, Level;             // a pool: from its deepest point to the level this storm fills it to
            public List<Vector3> Catchment;         // a pool: the outline of the ground that drains to it
        }

        readonly List<FlowTarget> flowTargets = new List<FlowTarget>();
        FlowTarget flowHover, flowPinned, flowShownTarget;
        GameObject flowAnimObject;
        Vector3 flowLastPointer, flowDownAt;
        float flowLift;

        /// From the flow data, once for each storm shown: every path and pool, ready to play.
        void PrepareFlowAnim(JToken a, int rp)
        {
            flowTargets.Clear();
            flowHover = flowPinned = flowShownTarget = null;
            HideFlowAnim();
            if (a == null || frame == null) return;
            flowLift = 0.14f + 0.03f * frame.Exaggeration;
            foreach (var f in a["flow_lines"])
            {
                var path = PathFrom(f["xyz"].Values<float>().ToArray());
                var area = f["area_m2"].Values<float>().ToArray();
                if (area.Length > 1 && area[0] > area[area.Length - 1]) path = PathFrom(Reversed(f["xyz"].Values<float>().ToArray()));
                if (path.Length <= 0) continue;
                var t = new FlowTarget { Words = $"Water runs this way: {area.Max():N0} m² of the park drains to the low end of this path." };
                t.Paths.Add(path);
                flowTargets.Add(t);
            }
            foreach (var h in a["hotspots"])
            {
                var fill = FlowView.StormFill(h, rp);
                if (fill != null && (float)fill["volume_m3"] <= 0) continue;
                var o = h["outline"].Values<float>().ToArray();
                if (o.Length < 8) continue;
                var t = new FlowTarget
                {
                    Ring = new List<Vector2>(),
                    Bottom = (float)h["z"],
                    Level = fill != null ? (float)fill["water_level_m"] : (float)h["water_level_m"],
                };
                for (int i = 0; i + 1 < o.Length; i += 2) t.Ring.Add(new Vector2(o[i], o[i + 1]));
                foreach (var feeder in h["feeders"] ?? new JArray())
                    t.Paths.Add(PathFrom(feeder.Values<float>().ToArray()));
                if (h["catchment"] is JArray c && c.Count >= 8)
                {
                    var xy = c.Values<float>().ToArray();
                    t.Catchment = new List<Vector3>();
                    for (int i = 0; i + 1 < xy.Length; i += 2) t.Catchment.Add(frame.World(xy[i], xy[i + 1], GroundZ(xy[i], xy[i + 1])));
                }
                t.Words = $"{h["id"]}: water from {(float)h["draining_area_m2"]:N0} m² runs down to this hollow" +
                          (fill != null ? $" and stands {(float)fill["max_depth_m"] * 100:0} cm deep in the {rp}-year storm." : ".");
                flowTargets.Add(t);
            }
        }

        static float[] Reversed(float[] xyz)
        {
            var r = new float[xyz.Length];
            for (int i = 0; i < xyz.Length / 3; i++)
                for (int k = 0; k < 3; k++) r[3 * i + k] = xyz[xyz.Length - 3 * (i + 1) + k];
            return r;
        }

        FlowPath PathFrom(float[] xyz)
        {
            var p = new FlowPath();
            float along = 0;
            for (int i = 0; i + 2 < xyz.Length; i += 3)
            {
                var w = frame.World(xyz[i], xyz[i + 1], xyz[i + 2]) + Vector3.up * flowLift;
                if (p.Points.Count > 0) along += Vector3.Distance(p.Points[p.Points.Count - 1], w);
                p.Points.Add(w);
                p.Plan.Add(new Vector2(xyz[i], xyz[i + 1]));
                p.Along.Add(along);
            }
            return p;
        }

        /// Hover to play, click to keep; called every frame.
        void FlowAnimInput()
        {
            bool on = flowData != null && flowTargets.Count > 0 && ui.ActiveTab == SpongePark.UI.Tab.Analyse && !live && !playing && !busy && !siteSetup.IsOpen;
            if (!on) { HideFlowAnim(); return; }
            bool blocked = CameraRig.BlockInput != null && CameraRig.BlockInput();
            if (!blocked && Input.mousePosition != flowLastPointer && !Input.GetMouseButton(0))
            {
                flowLastPointer = Input.mousePosition;
                flowHover = PickGround(out var xy, out _) ? FlowTargetAt(xy) : null;
            }
            if (!blocked && Input.GetMouseButtonDown(0)) flowDownAt = Input.mousePosition;
            if (!blocked && Input.GetMouseButtonUp(0) && (Input.mousePosition - flowDownAt).magnitude < 5f)   // not a drag of the view
                flowPinned = PickGround(out var xy, out _) ? FlowTargetAt(xy) : null;
            if (Input.GetKeyDown(KeyCode.Escape)) flowPinned = null;
            var show = flowHover ?? flowPinned;
            if (show == null) { HideFlowAnim(); return; }
            if (show != flowShownTarget) { flowShownTarget = show; status = show.Words; }
            DrawFlowAnim(show);
        }

        FlowTarget FlowTargetAt(Vector2 xy)
        {
            foreach (var t in flowTargets)
                if (t.Ring != null && Inside(t.Ring, xy)) return t;
            FlowTarget best = null;
            float reach = Mathf.Max(1.5f, rigLeft.Distance * 0.012f), nearest = reach;
            foreach (var t in flowTargets)
            {
                if (t.Ring != null) continue;
                var plan = t.Paths[0].Plan;
                for (int i = 0; i + 1 < plan.Count; i++)
                {
                    var d = DistanceToSegment(xy, plan[i], plan[i + 1]);
                    if (d < nearest) { nearest = d; best = t; }
                }
            }
            return best;
        }

        static bool Inside(List<Vector2> ring, Vector2 p)
        {
            bool inside = false;
            for (int i = 0, j = ring.Count - 1; i < ring.Count; j = i++)
                if ((ring[i].y > p.y) != (ring[j].y > p.y) && p.x < (ring[j].x - ring[i].x) * (p.y - ring[i].y) / (ring[j].y - ring[i].y) + ring[i].x)
                    inside = !inside;
            return inside;
        }

        static float DistanceToSegment(Vector2 p, Vector2 a, Vector2 b)
        {
            var ab = b - a;
            float t = ab.sqrMagnitude > 0 ? Mathf.Clamp01(Vector2.Dot(p - a, ab) / ab.sqrMagnitude) : 0;
            return (p - (a + ab * t)).magnitude;
        }

        void DrawFlowAnim(FlowTarget t)
        {
            if (flowAnimObject == null)
            {
                flowAnimObject = new GameObject("flow animation");
                flowAnimObject.AddComponent<MeshFilter>();
                flowAnimObject.AddComponent<MeshRenderer>().sharedMaterial = new Material(Shader.Find("SpongePark/VertexLit"));
            }
            flowAnimObject.SetActive(true);
            flowAnimObject.layer = Mathf.RoundToInt(Mathf.Log(camLeft.cullingMask, 2));   // the layer the main view is showing
            var m = new MeshBuilder();
            float clock = Time.unscaledTime;
            float size = Mathf.Clamp(rigLeft.Distance / 60f, 1f, 4f);   // readable zoomed out as well as in
            var trail = new Color(0.62f, 0.86f, 0.98f);
            var arrow = new Color(1f, 1f, 1f);
            foreach (var path in t.Paths)
            {
                if (path.Points.Count < 2) continue;
                m.Ribbon(path.Points, 0.55f * size, 0, trail);
                float spacing = ArrowSpacing * size;
                for (float s = (clock * ArrowSpeed * size) % spacing; s < path.Length; s += spacing)
                {
                    int i = path.Along.FindIndex(a => a >= s);
                    if (i <= 0) continue;
                    var a0 = path.Points[i - 1];
                    var a1 = path.Points[i];
                    float span = path.Along[i] - path.Along[i - 1];
                    var at = Vector3.Lerp(a0, a1, span > 0 ? (s - path.Along[i - 1]) / span : 0) + Vector3.up * 0.05f;
                    var dir = a1 - a0;
                    dir.y = 0;
                    if (dir.sqrMagnitude > 1e-6f) m.Arrow(at, dir.normalized, 1.1f * size, 0.75f * size, arrow);
                }
            }
            if (t.Catchment != null) m.Ribbon(t.Catchment, 0.3f * size, flowLift, new Color(0.96f, 0.72f, 0.26f));
            if (t.Ring != null)
            {
                float rise = Mathf.SmoothStep(0.05f, 1f, Mathf.Clamp01((clock % FillSeconds) / (FillSeconds * 0.8f)));
                float level = Mathf.Lerp(t.Bottom, t.Level, rise);
                m.Fill(t.Ring.Select(p => frame.World(p.x, p.y, level)).ToList(), flowLift * 0.5f, new Color(0.2f, 0.56f, 0.86f));
            }
            var filter = flowAnimObject.GetComponent<MeshFilter>();
            var old = filter.sharedMesh;
            filter.sharedMesh = m.ToMesh();
            if (old != null) Destroy(old);
        }

        void HideFlowAnim()
        {
            flowShownTarget = null;
            if (flowAnimObject != null) flowAnimObject.SetActive(false);
        }

        /// -spPanel flow-walk (with -spShot and -spOpen): analyse, play a pool and a path with pictures, change storm, flood
        /// every storm; everything logged. It ends the app itself.
        System.Collections.IEnumerator FlowWalk()
        {
            float began = Time.realtimeSinceStartup;
            void Log(string step) => Debug.Log($"flow walk {Time.realtimeSinceStartup - began:0}s {step}: busy {busy}, status '{status}', error '{api.LastError}'");
            void Picture(string name) => ScreenCapture.CaptureScreenshot(Arg("-spShot").Replace(".png", $"-{name}.png"));
            var pause = new WaitForSecondsRealtime(1.5f);
            Log("start");
            yield return Run(AnalyseSite(), "Analysing the site");
            Log("analysed");
            if (flowData == null) { Log("NO FLOW"); Application.Quit(1); yield break; }
            ui.ActiveTab = SpongePark.UI.Tab.Analyse;
            rigLeft.Plan = true;
            var pools = flowTargets.Where(t => t.Ring != null).OrderByDescending(t => t.Paths.Count > 0 ? t.Paths.Max(p => p.Length) : 0f).ToList();
            var lines = flowTargets.Where(t => t.Ring == null).OrderByDescending(t => t.Paths[0].Length).ToList();
            Debug.Log($"flow walk targets: {pools.Count} pools, {pools.Count(p => p.Paths.Count > 0)} with feeders, {pools.Count(p => p.Catchment != null)} with catchments, {lines.Count} lines");
            if (lines.Count > 0)
            {
                var plan = lines[0].Paths[0].Plan;
                var mid = plan[plan.Count / 2];
                Debug.Log($"flow walk pick line: {FlowTargetAt(mid) != null}, length {lines[0].Paths[0].Length:0} m, runs from {lines[0].Paths[0].Points[0].y:0.00} to {lines[0].Paths[0].Points[plan.Count - 1].y:0.00}");
                flowPinned = lines[0];
                FocusOn(mid.x, mid.y, GroundZ(mid.x, mid.y), 60);
                yield return pause;
                var onScreen = camLeft.WorldToScreenPoint(lines[0].Paths[0].Points[plan.Count / 2]);
                Debug.Log($"flow walk hover at the line's screen position {onScreen}: found {(PickAt(onScreen, out var hoverAt, out _) ? FlowTargetAt(hoverAt) == lines[0] : false)}");
                Log("line pinned");
                FlowDiagnosis();
                Picture("line");
                yield return pause;
            }
            if (pools.Count > 0)
            {
                var pool = pools[0];
                var c = new Vector2(pool.Ring.Average(p => p.x), pool.Ring.Average(p => p.y));
                Debug.Log($"flow walk pick pool: {FlowTargetAt(c) == pool}, feeders {pool.Paths.Count}, longest {pool.Paths.Select(p => p.Length).DefaultIfEmpty(0).Max():0} m, bottom {pool.Bottom:0.00} level {pool.Level:0.00}");
                flowPinned = pool;
                FocusOn(c.x, c.y, GroundZ(c.x, c.y), 220);
                yield return new WaitForSecondsRealtime(FillSeconds - (Time.unscaledTime % FillSeconds) + 1f);
                var poolOnScreen = camLeft.WorldToScreenPoint(frame.World(c.x, c.y, pool.Level));
                Debug.Log($"flow walk hover at the pool's screen position {poolOnScreen}: found {(PickAt(poolOnScreen, out var hoverPool, out _) ? FlowTargetAt(hoverPool) == pool : false)}");
                Log("pool pinned");
                FlowDiagnosis();
                Picture("pool-early");
                yield return new WaitForSecondsRealtime(3.5f);
                Picture("pool-late");
                yield return pause;
                float meter = Time.realtimeSinceStartup;
                int frames = 0;
                while (Time.realtimeSinceStartup - meter < 3f) { frames++; yield return null; }
                Debug.Log($"flow walk frame rate while playing: {frames / 3f:0} fps");
            }
            flowPinned = null;
            for (int k = 0; k < returnPeriods.Count; k++)
            {
                float t0 = Time.realtimeSinceStartup;
                PickStorm(k);
                Debug.Log($"flow walk storm {CurrentRp}: {flowTargets.Count} targets ready in {(Time.realtimeSinceStartup - t0) * 1000f:0} ms");
                yield return null;
            }
            Log("storms switched");
            if (System.Environment.GetCommandLineArgs().Contains("-spNoFlood")) { Application.Quit(0); yield break; }
            float floodFrom = Time.realtimeSinceStartup;
            yield return FloodAll();
            Log($"flood all storms took {Time.realtimeSinceStartup - floodFrom:0}s, frames loaded {left.Frames != null}");
            yield return pause;
            Picture("flooded");
            yield return pause;
            Debug.Log("flow walk finished");
            Application.Quit(0);
        }

        void FlowDiagnosis()
        {
            var mesh = flowAnimObject != null ? flowAnimObject.GetComponent<MeshFilter>().sharedMesh : null;
            Debug.Log($"flow walk drawn: pinned {flowPinned != null}, hover {flowHover != null}, object {flowAnimObject != null}, active {flowAnimObject != null && flowAnimObject.activeSelf}, " +
                      $"layer {(flowAnimObject != null ? flowAnimObject.layer : -1)}, camera mask {camLeft.cullingMask}, vertices {(mesh != null ? mesh.vertexCount : -1)}, bounds {(mesh != null ? mesh.bounds.ToString() : "")}, " +
                      $"camera at {camLeft.transform.position}, target {rigLeft.Target}, ortho {camLeft.orthographic} near {camLeft.nearClipPlane} far {camLeft.farClipPlane}, " +
                      $"playing {playing} live {live} tab {ui.ActiveTab} setup {siteSetup.IsOpen} shader {flowAnimObject?.GetComponent<MeshRenderer>().sharedMaterial.shader.name}");
        }

        // ------------------------------------------------------------ Simulate: the flood of every storm
        bool floodRunning;

        /// The 2D flood for every storm, behind the app: the app stays free and each storm appears as it ends.
        System.Collections.IEnumerator FloodAll()
        {
            JToken r = null;
            yield return api.Send("POST", api.P("/flood"), new JObject(), x => r = x);
            if (r == null) yield break;
            floodRunning = true;
            int frameRateWas = Application.targetFrameRate;
            Application.targetFrameRate = 30;   // drawing flat out slows the storms down, on the CPU and the card
            int seen = -1;
            var forProject = projectPath;
            while (forProject == projectPath)
            {
                yield return new WaitForSecondsRealtime(2f);
                JToken i = null;
                yield return api.Get(api.P(""), x => i = x);
                var f = i?["flood"];
                if (f == null || f.Type != JTokenType.Object) break;
                int done = f["done"].Count();
                bool running = (bool)f["running"];
                if (running) status = $"Flood simulation: {done} of {(int)f["total"]} storms done. The app stays free to use.";
                if (done != seen && !busy) { seen = done; if (running && flowData != null) yield return LoadFlow(); }
                if (running) continue;
                floodRunning = false;
                Application.targetFrameRate = frameRateWas;
                if (forProject == projectPath)
                {
                    yield return Refresh();
                    yield return LoadViews();
                    int failed = f["failed"].Count();
                    status = $"Flood simulation of {done} storm{(done == 1 ? "" : "s")} ready" + (failed > 0 ? $", {failed} could not run" : "") + ". Pick a storm and press Play.";
                }
                yield break;
            }
            floodRunning = false;
            Application.targetFrameRate = frameRateWas;
        }
    }
}
