// One side of the comparison: terrain (existing or an option's graded ground), its water, the replayed
// engine frames or a live GPU simulation, and the SWMM litres-retained curve.
using System.Collections;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace SpongePark
{
    public class SiteView : MonoBehaviour
    {
        public string Option = "baseline";   // "baseline" shows existing ground
        public TerrainView Terrain;
        public WaterView Water;
        public DepthFrames Frames;
        public GpuWaterSim Gpu;
        public SurveyLayersView Survey;
        public FlowView Flow;
        public DesignOverlay Design;
        public FlowParticles Particles;
        public VelocityFrames Velocity;   // the storm's velocities, loaded while the flow trace is on
        public bool Trace;                // the flow trace: particles and the water coloured by speed
        public string TraceNote = "";
        int velocityRp = -1;
        public float[] RetainedTime, RetainedLitres, RainLitres;
        float siteArea;
        public string Status = "";
        float[] depth;

        public static SiteView Create(string name, Transform parent, int layer)
        {
            var go = new GameObject(name) { layer = layer };
            go.transform.SetParent(parent, false);
            var v = go.AddComponent<SiteView>();
            v.Terrain = TerrainView.Create("terrain", go.transform, layer);
            v.Water = WaterView.Create("water", go.transform, layer);
            v.Survey = SurveyLayersView.Create("survey layers", go.transform, layer);
            v.Flow = FlowView.Create("flow", go.transform, layer);
            v.Design = DesignOverlay.Create("design", go.transform, layer);
            v.Particles = FlowParticles.Create("flow trace", go.transform, layer);
            return v;
        }

        /// The flow trace for storm rp: its velocities from the flood run, the particles let go on them, the water
        /// coloured by speed. Off: the water by depth again.
        public IEnumerator SetTrace(EngineClient api, SiteFrame frame, int rp, bool on)
        {
            Trace = on;
            if (!on || Frames == null)
            {
                Velocity = null;
                velocityRp = -1;
                Particles.Clear();
                Water.ColourBySpeed(null, 1);
                TraceNote = on ? "no flood run for this storm yet" : "";
                yield break;
            }
            if (Velocity == null || velocityRp != rp)
            {
                JToken t = null;
                yield return api.Get(api.P($"/options/{Option}/sim2d/{rp}/velocity"), r => t = r);
                if (t == null)
                {
                    TraceNote = (api.LastError ?? "").Contains("before velocities") ? "this storm's flood was run before speeds were kept: run it again"
                                                                                   : "no speeds for this storm";
                    api.ClearError();
                    Velocity = null;
                    Particles.Clear();
                    Water.ColourBySpeed(null, 1);
                    yield break;
                }
                Velocity = VelocityFrames.FromPayload(t);
                velocityRp = rp;
            }
            if (Velocity.Rows != Frames.Rows || Velocity.Cols != Frames.Cols) { TraceNote = "the speeds do not match the flood's grid"; yield break; }
            Particles.Build(Velocity, Water, Terrain, frame);
            Particles.gameObject.SetActive(true);
            TraceNote = $"fastest {Velocity.MaxSpeed:0.00} m/s; most moving water under {Velocity.P95Speed:0.00} m/s";
        }

        /// The speed the colour map's top colour stands for.
        public float TraceTop => Velocity != null ? Mathf.Max(Velocity.P95Speed * 1.3f, 0.1f) : 1f;

        public IEnumerator Load(EngineClient api, SiteFrame frame, int rp, bool bundle)
        {
            Status = "loading terrain";
            JToken terrain = null, comps = null;
            string opt = Option == "baseline" ? null : Option;
            if (bundle)
            {
                yield return api.LoadBundleFile(opt == null ? "terrain_existing.json" : $"terrain_{opt}.json", r => terrain = r);
                if (opt != null) yield return api.LoadBundleFile($"components_{opt}.json", r => comps = r);
            }
            else
            {
                yield return api.Get(api.P("/terrain" + (opt == null ? "" : "?option=" + opt)), r => terrain = r);
                if (opt != null) yield return api.Get(api.P($"/options/{opt}/components"), r => comps = r);
            }
            if (terrain == null) { Status = "no terrain: " + api.LastError; yield break; }
            Terrain.Build(HeightGrid.FromPayload(terrain), frame, comps);
            yield return LoadStorm(api, frame, rp, bundle);
        }

        readonly System.Collections.Generic.Dictionary<int, float[]> peaks = new System.Collections.Generic.Dictionary<int, float[]>();
        int peakCells;

        /// Each storm's highest water (2D flood run), kept here so that changing the storm shows it at once.
        public IEnumerator LoadPeaks(EngineClient api, SiteFrame frame, System.Collections.Generic.IEnumerable<int> rps)
        {
            peaks.Clear();
            foreach (var rp in rps)
            {
                JToken t = null;
                yield return api.Get(api.P($"/options/{Option}/sim2d/{rp}/peak"), r => t = r);
                if (t == null) continue;
                var f = DepthFrames.FromPayload(t);
                var d = new float[f.Rows * f.Cols];
                f.Sample(0, d);
                if (peaks.Count == 0) Water.Build(f.Rows, f.Cols, f.Cell, f.Origin, Terrain, frame);
                peakCells = d.Length;
                peaks[rp] = d;
            }
            api.ClearError();   // a storm without a run is not an error
        }

        public void ClearPeaks()
        {
            if (peaks.Count > 0) Water.Show(new float[peakCells]);
            peaks.Clear();
        }

        /// The highest water of storm rp, or none when it has no 2D run or the layer is off.
        public void ShowPeak(int rp, bool on)
        {
            if (peaks.Count == 0) return;
            Water.Show(on && peaks.TryGetValue(rp, out var d) ? d : new float[peakCells]);
        }

        /// This view's water for storm rp; the ground and everything else stay as they are.
        public IEnumerator LoadStorm(EngineClient api, SiteFrame frame, int rp, bool bundle)
        {
            JToken frames = null, retained = null;
            if (bundle)
            {
                yield return api.LoadBundleFile($"frames_{Option}_rp{rp}.json", r => frames = r);
                yield return api.LoadBundleFile($"retained_{Option}_rp{rp}.json", r => retained = r);
            }
            else
            {
                yield return api.Get(api.P($"/options/{Option}/sim2d/{rp}/frames"), r => frames = r);
                yield return api.Get(api.P($"/options/{Option}/retained/{rp}"), r => retained = r);
            }
            api.ClearError();   // storm frames and results are optional: none yet is not an error
            Velocity = null;   // a new storm: its own speeds (SetTrace loads them)
            velocityRp = -1;
            Particles.Clear();
            Water.ColourBySpeed(null, 1);
            if (frames != null)
            {
                Frames = DepthFrames.FromPayload(frames);
                Water.Build(Frames.Rows, Frames.Cols, Frames.Cell, Frames.Origin, Terrain, frame);
                depth = new float[Frames.Rows * Frames.Cols];
                Status = $"{Frames.Count} engine frames (indicative)";
            }
            else
            {
                // no run for this storm: drop the last storm's water, or it would be shown as this one's
                if (Frames != null) { Water.Show(new float[Frames.Rows * Frames.Cols]); Frames = null; }
                Status = "no 2D run yet for this storm";
            }
            if (retained != null)
            {
                RetainedTime = retained["time_hr"].ToObject<float[]>();
                RetainedLitres = retained["retained_l"].ToObject<float[]>();
                RainLitres = retained["rain_l"].ToObject<float[]>();
                siteArea = (float)retained["site_area_m2"];
            }
            else RetainedTime = RetainedLitres = RainLitres = null;
            if (Trace && !bundle) yield return SetTrace(api, frame, rp, true);   // the trace stays on through a change of storm
        }

        /// After a design edit: only the carved ground and the element footprints change. The survey objects
        /// and flow lines stay; the storm frames no longer belong to this ground, so they are dropped.
        public IEnumerator ReloadGround(EngineClient api, SiteFrame frame)
        {
            JToken terrain = null, comps = null;
            string opt = Option == "baseline" ? null : Option;
            yield return api.Get(api.P("/terrain" + (opt == null ? "" : "?option=" + opt)), r => terrain = r);
            if (opt != null) yield return api.Get(api.P($"/options/{opt}/components"), r => comps = r);
            if (terrain == null) yield break;
            api.ClearError();
            Terrain.Build(HeightGrid.FromPayload(terrain), frame, comps);
            if (Frames != null) { Water.Show(new float[Frames.Rows * Frames.Cols]); Frames = null; }
            Velocity = null;
            velocityRp = -1;
            Particles.Clear();
            Water.ColourBySpeed(null, 1);
            RetainedTime = RetainedLitres = RainLitres = null;
            Status = "no 2D run yet for this design";
        }

        public IEnumerator StartGpu(EngineClient api, SiteFrame frame, int rp)
        {
            JToken inp = null;
            Status = "loading 2D inputs";
            yield return api.Get(api.P($"/options/{Option}/sim2d/{rp}/inputs"), r => inp = r);
            if (inp == null) { Status = "inputs unavailable: " + api.LastError; yield break; }
            Gpu?.Dispose();
            Gpu = new GpuWaterSim();
            Gpu.Init(inp);
            Water.Build(Gpu.Rows, Gpu.Cols, Gpu.Cell, Gpu.Origin, Terrain, frame);
            Status = "live GPU simulation (indicative)";
        }

        /// Show the water at simulated time t (s).
        public void ShowAt(float t, bool live, float advanceS)
        {
            if (live && Gpu != null && Gpu.Ready)
            {
                if (advanceS > 0) Gpu.Advance(advanceS);
                Water.Show(Gpu.Depth());
            }
            else if (Frames != null)
            {
                Frames.Sample(t, depth);
                if (Trace && Velocity != null)
                {
                    Velocity.At(t);
                    Water.ColourBySpeed(Velocity.Speed, TraceTop);
                }
                Water.Show(depth);
            }
        }

        public float LitresAt(float tHours)
        {
            if (RetainedTime == null || RetainedTime.Length == 0) return 0;
            int i = System.Array.BinarySearch(RetainedTime, tHours);
            if (i < 0) i = Mathf.Clamp(~i - 1, 0, RetainedTime.Length - 1);
            return RetainedLitres[i];
        }

        /// Rainfall intensity (mm/h) at tHours, from the cumulative rain curve.
        public float RainAt(float tHours)
        {
            if (RetainedTime == null || RetainedTime.Length < 2 || siteArea <= 0) return 0;
            int i = System.Array.BinarySearch(RetainedTime, tHours);
            if (i < 0) i = ~i - 1;
            i = Mathf.Clamp(i, 0, RetainedTime.Length - 2);
            float dl = RainLitres[i + 1] - RainLitres[i], dt = RetainedTime[i + 1] - RetainedTime[i];
            return dt > 0 ? dl / siteArea / dt : 0;   // L / m2 / h = mm/h
        }

        /// Rainfall now (mm/h) at simulated time t (s): the live storm's own series, else the replay's.
        public float RainNow(float t, bool live) =>
            live && Gpu != null && Gpu.Ready ? Gpu.RainAt(t) : RainAt(t / 3600f);

        public float EndTime => Frames != null && Frames.Count > 0 ? Frames.Times[Frames.Count - 1] : Gpu?.Duration ?? 0;

        void OnDestroy() => Gpu?.Dispose();
    }
}
