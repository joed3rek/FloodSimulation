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
            return v;
        }

        public IEnumerator Load(EngineClient api, SiteFrame frame, int rp, bool bundle)
        {
            Status = "loading terrain";
            JToken terrain = null, comps = null, frames = null, retained = null;
            string opt = Option == "baseline" ? null : Option;
            if (bundle)
            {
                yield return api.LoadBundleFile(opt == null ? "terrain_existing.json" : $"terrain_{opt}.json", r => terrain = r);
                if (opt != null) yield return api.LoadBundleFile($"components_{opt}.json", r => comps = r);
                yield return api.LoadBundleFile($"frames_{Option}_rp{rp}.json", r => frames = r);
                yield return api.LoadBundleFile($"retained_{Option}_rp{rp}.json", r => retained = r);
            }
            else
            {
                yield return api.Get(api.P("/terrain" + (opt == null ? "" : "?option=" + opt)), r => terrain = r);
                if (opt != null) yield return api.Get(api.P($"/options/{opt}/components"), r => comps = r);
                yield return api.Get(api.P($"/options/{Option}/sim2d/{rp}/frames"), r => frames = r);
                yield return api.Get(api.P($"/options/{Option}/retained/{rp}"), r => retained = r);
            }
            if (terrain == null) { Status = "no terrain: " + api.LastError; yield break; }
            Terrain.Build(HeightGrid.FromPayload(terrain), frame, comps);
            if (frames != null)
            {
                Frames = DepthFrames.FromPayload(frames);
                Water.Build(Frames.Rows, Frames.Cols, Frames.Cell, Frames.Origin, Terrain, frame);
                depth = new float[Frames.Rows * Frames.Cols];
                Status = $"{Frames.Count} engine frames (indicative)";
            }
            else Status = "no 2D run yet for this storm";
            if (retained != null)
            {
                RetainedTime = retained["time_hr"].ToObject<float[]>();
                RetainedLitres = retained["retained_l"].ToObject<float[]>();
                RainLitres = retained["rain_l"].ToObject<float[]>();
                siteArea = (float)retained["site_area_m2"];
            }
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

        public float EndTime => Frames != null && Frames.Count > 0 ? Frames.Times[Frames.Count - 1] : Gpu?.Duration ?? 0;

        void OnDestroy() => Gpu?.Dispose();
    }
}
