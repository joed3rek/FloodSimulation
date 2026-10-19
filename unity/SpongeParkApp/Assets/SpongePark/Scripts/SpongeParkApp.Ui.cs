// Shared interface pieces of the app: element helpers (labels, rows, cards, buttons, fields), the survey layers'
// visibility, and the comparison of options. The workspace itself (app bar, ribbon, panels, timeline, status bar)
// is built in SpongeParkApp.Shell.cs; the steps' own controls are built in their partial classes and placed there.
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.UIElements;

namespace SpongePark
{
    public partial class SpongeParkApp
    {
        UIDocument doc;
        Label siteText, verifyLabel, videoLabel;
        VisualElement compareBox;
        string shownComparison;

        // ------------------------------------------------------------ survey layers (Contents > Survey)
        readonly System.Collections.Generic.Dictionary<string, bool> layerVisible = new System.Collections.Generic.Dictionary<string, bool>();
        const string ContoursLayer = "__contours";

        bool LayerOn(string name) => !layerVisible.TryGetValue(name, out var on) || on;

        void SetLayer(string name, bool on)
        {
            layerVisible[name] = on;
            if (name == ContoursLayer) { left.Terrain.SetContours(on); right.Terrain.SetContours(on); }
            left.Survey.SetVisible(name, on);
            right.Survey.SetVisible(name, on);
        }

        void SetAllLayers(bool on)
        {
            SetLayer(ContoursLayer, on);
            if (surveyLayers != null) foreach (var L in surveyLayers["layers"]) SetLayer((string)L["name"], on);
        }

        /// After the survey layers load: each layer starts as the engine says (visible or not), contours on.
        void FillSiteLayers()
        {
            if (!layerVisible.ContainsKey(ContoursLayer)) layerVisible[ContoursLayer] = true;
            if (surveyLayers != null)
                foreach (var L in surveyLayers["layers"])
                {
                    var name = (string)L["name"];
                    if (!layerVisible.ContainsKey(name)) layerVisible[name] = (bool?)L["visible"] ?? true;
                }
            contentsDirty = true;
        }

        string SiteSummary()
        {
            bool hasProject = info != null, ground = hasProject && (bool?)info["has_terrain"] == true;
            return !hasProject ? "Open a project to see its site model."
                : !ground ? "This project has no ground model yet: start a new project from its survey (Site > Import survey)."
                : surveyLayers == null ? "The ground model is shown. This project has no survey layers (it was not made from a survey drawing)."
                : siteConfirmed ? "Site model confirmed. Switch layers on and off in Contents; reopen it from the Site tab."
                : "Look over the ground and what the survey shows (Contents switches layers on and off). When it matches the site, Site > Confirm site model.";
        }

        // ------------------------------------------------------------ comparison (Properties > Results)
        void SyncComparison()
        {
            var key = comparison?.ToString(Newtonsoft.Json.Formatting.None) ?? "";
            if (key == shownComparison) return;
            shownComparison = key;
            compareBox.Clear();
            if (comparison == null)
            {
                compareBox.Add(Text("Choose an option that has been run (Results tab).", "muted"));
                return;
            }
            var ds = comparison["design_retention_storm_yr"];
            compareBox.Add(Text("Largest storm fully retained", "muted"));
            compareBox.Add(Text(ds == null || ds.Type == JTokenType.Null ? "none" : $"{ds}-year", "stat-value"));
            foreach (var row in comparison["rows"])
            {
                var r = new VisualElement();
                r.AddToClassList("result-row");
                r.Add(Text($"{row["return_period_yr"]}-year", "result-rp"));
                var peak = row["peak_reduction_pct"].Type == JTokenType.Null ? 0f : (float)row["peak_reduction_pct"];
                r.Add(Text($"kept {(float)row["baseline_retained_pct"]:0} → {(float)row["option_retained_pct"]:0} %   peak −{peak:0} %"));
                compareBox.Add(r);
            }
        }

        // ------------------------------------------------------------ element helpers
        static Label Text(string text, params string[] classes)
        {
            var l = new Label(text) { pickingMode = PickingMode.Ignore };
            foreach (var c in classes) l.AddToClassList(c);
            return l;
        }

        static VisualElement Row(string cls = "row")
        {
            var r = new VisualElement();
            r.AddToClassList("row");
            if (cls != "row") r.AddToClassList(cls);
            return r;
        }

        static VisualElement Card(string variant = null)
        {
            var c = new VisualElement();
            c.AddToClassList("card");
            if (variant != null) c.AddToClassList(variant);
            return c;
        }

        static Button Btn(string text, System.Action onClick, string variant = null)
        {
            var b = new Button(onClick) { text = text };
            b.AddToClassList("btn");
            if (variant != null) foreach (var v in variant.Split(' ')) b.AddToClassList(v);
            return b;
        }

        static Button Chip(string text, System.Action onClick)
        {
            var b = new Button(onClick) { text = text };
            b.AddToClassList("chip");
            return b;
        }

        static VisualElement TextInput(string label, string value, System.Action<string> onChange)
        {
            var box = new VisualElement();
            box.Add(Text(label, "field-label"));
            var f = new TextField { value = value ?? "" };
            f.AddToClassList("input");
            f.RegisterValueChangedCallback(e => onChange(e.newValue));
            box.Add(f);
            return box;
        }

        static VisualElement SliderField(string label, float lo, float hi, float value, string unit, System.Action<float> onChange)
        {
            var box = new VisualElement();
            var l = Text($"{label}: {value:0.#} {unit}", "field-label");
            box.Add(l);
            var s = new Slider(lo, hi) { value = value };
            s.AddToClassList("slider");
            s.RegisterValueChangedCallback(e => { onChange(e.newValue); l.text = $"{label}: {e.newValue:0.#} {unit}"; });
            box.Add(s);
            return box;
        }
    }
}
