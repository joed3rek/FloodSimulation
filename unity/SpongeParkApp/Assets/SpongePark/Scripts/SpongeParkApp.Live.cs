// What follows each design change, and the pieces of Step 3 around it:
// - live water: the GPU storm restarts on the carved ground (existing beside design), an hour of storm a second;
// - the design's flow lines are redone on the carved ground;
// - SWMM checks the design for every storm in the background (results card);
// - Suggest a layout: the layout generator or the optimiser, each option with its SWMM results, to start from;
// - heights x1 / x3 / x5 (the sky, haze and weather are in SpongeParkApp.Weather.cs).
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.UIElements;

namespace SpongePark
{
    public partial class SpongeParkApp
    {
        VisualElement suggestList, resultsBox;
        Label suggestText, resultsText;
        bool verifying;
        int liveToken;

        float StormDepth(int rp)
        {
            if (rainSaved == null || rp <= 0) return 0;
            var row = rainSaved["rows"].FirstOrDefault(x => (int)x["return_period_yr"] == rp && (float)x["duration_hr"] >= 24);
            return row != null ? (float)row["depth_mm"] : 0;
        }

        bool ReadyToSimulate => (bool?)info?["has_rainfall"] == true && ((bool?)info?["has_ground"] == true || (bool?)info?["has_soils"] == true);

        // ------------------------------------------------------------ view: heights and atmosphere
        void SetHeights(float v)
        {
            if (Mathf.Approximately(v, exaggeration) || busy) return;
            exaggeration = v;
            StartCoroutine(Run(LoadViews(), "Redrawing the heights"));
        }

        void SetupAtmosphere(Light light) => SetupEnvironment(light);   // sky, textures, post-processing, weather

        /// Sky, haze and weather in 3D; a clean paper background in the 2D plan.
        void SyncAtmosphere()
        {
            if (rigLeft == null) return;
            bool plan = rigLeft.Plan;
            camLeft.backgroundColor = PlanBackground;   // the dark workspace's plan (3D sets its sky below)
            camRight.backgroundColor = PlanBackground;
            SyncEnvironment(plan);
        }

        // ------------------------------------------------------------ after each design change
        IEnumerator AfterDesignChange()
        {
            int token = ++liveToken;
            // flow lines on the carved ground
            JToken f = null;
            yield return api.Get(api.P($"/flow?scenario={DesignScenario}"), x => f = x, 120);
            if (token != liveToken) yield break;
            if (f != null) right.Flow.Build(f, frame, layerVisible);
            if (!ReadyToSimulate) { status += " Use the rainfall and answer the ground questions (Step 2) to see the water."; yield break; }
            // live water on both grounds, an hour of storm per second, from dry
            if (GpuWaterSim.Supported)
            {
                yield return left.StartGpu(api, frame, CurrentRp);
                yield return right.StartGpu(api, frame, CurrentRp);
                if (token != liveToken) yield break;
                live = true;
                simT = 0;
                speed = 3600;
                playing = true;
                sideBySide = true;
                ApplyViewports();
            }
            // SWMM on the design, quietly in the background
            StartCoroutine(VerifyQuietly(token));
        }

        IEnumerator VerifyQuietly(int token)
        {
            if (verifying) yield break;
            verifying = true;
            resultsText.text = "Checking the design in SWMM…";
            JToken r = null;
            yield return api.RunJob("POST", api.P($"/design/{DesignScenario}/verify"), null, x => r = x);
            verifying = false;
            if (r == null) { resultsText.text = "SWMM could not check the design: " + api.LastError; yield break; }
            ShowResults(r);
            designVerified = true;
            MarkStage("verify");
        }

        void ShowResults(JToken r)
        {
            resultsBox.Clear();
            resultsText.text = "Kept on site (existing → design) and peak flow cut, from SWMM for every storm:";
            foreach (var x in r["rows"])
            {
                float before = (float)x["existing_retained_pct"], after = (float)x["retained_pct"], peak = (float)x["peak_reduction_pct"];
                var line = Row("result-row");
                line.Add(Text($"{(int)x["return_period_yr"]}-year", "result-rp"));
                var bar = new VisualElement();
                bar.AddToClassList("result-bar");
                var b0 = new VisualElement();
                b0.AddToClassList("result-bar-before");
                b0.style.width = Length.Percent(Mathf.Clamp(before, 0, 100));
                var b1 = new VisualElement();
                b1.AddToClassList("result-bar-after");
                b1.style.width = Length.Percent(Mathf.Clamp(after, 0, 100));
                bar.Add(b1);
                bar.Add(b0);
                line.Add(bar);
                line.Add(Text($"{before:0}% → {after:0}% · peak −{Mathf.Max(0, peak):0}%", "result-num"));
                resultsBox.Add(line);
            }
            var storm = r["design_retention_storm_yr"];
            if (storm != null && storm.Type != JTokenType.Null)
                resultsBox.Add(Text($"Largest storm fully kept on site: {storm}-year.", "muted"));
        }

        // ------------------------------------------------------------ suggest a layout, design results
        /// The suggestions list and the design's SWMM results (Properties > Results); their buttons are on the Design tab.
        VisualElement suggestCard, resultsCard;

        void BuildSuggestParts()
        {
            suggestCard = new VisualElement();
            suggestText = Text("Design > Quick layout or Optimise: the engine places and sizes NbS from the flow and the ground, checked in SWMM. Start from one and change shapes and depths.", "muted");
            suggestCard.Add(suggestText);
            suggestList = new VisualElement();
            suggestList.AddToClassList("layer-list");
            suggestCard.Add(suggestList);

            resultsCard = new VisualElement();
            resultsText = Text("Add NbS to see how much more of each storm the park keeps.", "muted");
            resultsCard.Add(resultsText);
            resultsBox = new VisualElement();
            resultsCard.Add(resultsBox);
        }

        void CheckAgain() => StartCoroutine(VerifyQuietly(liveToken));
        bool designVerified;

        IEnumerator Suggest(string method)
        {
            if (!ReadyToSimulate) { status = "First use the rainfall and answer the ground questions (Step 2)."; yield break; }
            JToken r = null;
            yield return api.RunJob("POST", api.P($"/design/{DesignScenario}/suggest"), new { method, mode = "forward", effort = "normal" },
                x => r = x, s => status = (method == "quick" ? "placing NbS: " : "optimising (SWMM-checked): ") + s);
            if (r == null) yield break;
            suggestList.Clear();
            int n = 0;
            foreach (var p in r["proposals"])
            {
                n++;
                var id = (string)p["id"];
                var rows = p["rows"];
                var key = rows.FirstOrDefault(x => (int)x["return_period_yr"] == 25) ?? rows.Last();
                var types = string.Join(", ", p["types"].Select(t => ToolNames.TryGetValue((string)t, out var nm) ? nm.ToLower() : ((string)t).Replace('_', ' ')));
                var b = new Button(() => StartCoroutine(Run(Accept(id), "Starting from this option")));
                b.AddToClassList("layer-row");
                var w = new VisualElement { pickingMode = PickingMode.Ignore };
                w.AddToClassList("layer-words");
                w.Add(Text($"Option {n}: {(int)p["elements"]} element{((int)p["elements"] == 1 ? "" : "s")} ({types}), {(float)p["area_m2"]:0} m²", "layer-title"));
                w.Add(Text($"{(int)key["return_period_yr"]}-year storm kept: {(float)key["existing_retained_pct"]:0}% → {(float)key["retained_pct"]:0}%, peak −{(float)key["peak_reduction_pct"]:0}%", "layer-source"));
                b.Add(w);
                b.Add(Text("Use", "layer-count"));
                b.tooltip = "Put this option into the design; then change it as you like.";
                suggestList.Add(b);
            }
            status = n == 0 ? "No layout fits: see the checks (soil drainage, space, budget)." : $"{n} option{(n == 1 ? "" : "s")} ready: click one to start from it.";
        }

        IEnumerator Accept(string proposalId)
        {
            JToken r = null;
            yield return api.RunJob("POST", api.P($"/design/{DesignScenario}/accept"), new { proposal_id = proposalId, replace = true }, x => r = x);
            if (r == null) yield break;
            JToken cur = null;
            yield return api.Get(api.P($"/design/{DesignScenario}"), x => cur = x);
            if (cur == null) yield break;
            undoStack.Push(designFc?.ToString() ?? "{\"type\":\"FeatureCollection\",\"features\":[]}");
            redoStack.Clear();
            designFc = (JObject)cur["features"];
            designResult = r;
            selectedId = null;
            yield return ShowDesignGround();
            RefreshDesign();
            status = "Option in the design: select an element to change its shape (drag a corner) or depth.";
            StartCoroutine(AfterDesignChange());
        }

        /// A tree's colour varies a little, by where it stands.
        public static Color Vary(Color c, Vector3 p)
        {
            float h = Mathf.Abs(Mathf.Sin(p.x * 12.9898f + p.z * 78.233f) * 43758.55f) % 1f;
            float k = 0.84f + 0.3f * h;
            return new Color(c.r * k * (0.96f + 0.08f * h), c.g * k, c.b * k * (1.04f - 0.08f * h), 1);
        }
    }
}
