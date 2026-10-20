// Site setup (a dialog from the Site tab, pages Rainfall, Ground and Ponds): the design rainfall and the ground
// questionnaire, before the flood simulation.
// Rainfall: the IMD 24-hour design depths (a preset kept with its source) become the design storms.
// Ground: soil type, what covers the open park and in what condition, and the footpaths; the engine looks up
// the TR-55 curve numbers (with their table and page) and shows a runoff check per storm.
// Ponds: each pond in the park needs its depth and how deep the water usually stands; the room between is cut
// into the ground model, so the flow analysis, the 2D flood model and SWMM store water in it.
// Wells: the recharge wells on the survey are part of the existing site once their depth, diameter and the
// strata's infiltration rate are given (for all of them, or well by well); nothing is assumed.
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
        VisualElement rainCard, groundCard, coverRows, pondCard, pondRows;
        Label pondText;
        Button pondSave;
        class PondRow { public string Id; public TextField Depth, Water; }
        readonly List<PondRow> pondFields = new List<PondRow>();
        VisualElement wellCard, wellCommon, wellRows;
        Label wellText;
        Button wellSave;
        TextField wellDepth, wellDia, wellRate;
        Foldout wellSingles;
        class WellRow { public string Id; public TextField Depth, Diameter; }
        readonly List<WellRow> wellFields = new List<WellRow>();
        Label rainText, groundResult;
        Button rainButton;
        DropdownField soilField, pathsField;
        JToken groundQuestions, rainPresets, groundSaved, rainSaved;
        string groundFor;
        bool planSetFor;

        class CoverRow { public DropdownField Cover, Condition; public TextField Share; public VisualElement Root; }
        readonly List<CoverRow> covers = new List<CoverRow>();

        /// The three pages of Site setup.
        void BuildGroundAndRain(VisualElement rainPage, VisualElement groundPage, VisualElement pondPage, VisualElement wellPage)
        {
            rainCard = new VisualElement();
            rainCard.Add(Text("DESIGN RAINFALL", "eyebrow"));
            rainText = Text("", "muted");
            rainCard.Add(rainText);
            rainButton = Btn("Use this rainfall", () => StartCoroutine(Run(UsePresetRain(), "Making the design storms")), "btn--wide");
            rainCard.Add(rainButton);
            rainPage.Add(rainCard);

            groundCard = new VisualElement();
            groundCard.Add(Text("THE GROUND (TR-55 QUESTIONNAIRE)", "eyebrow"));
            groundCard.Add(Text("How much rain soaks in depends on the soil and what covers it. Answer for the open park; buildings and paved paths are counted as hard surfaces.", "muted"));
            soilField = new DropdownField("What is the soil like?", new List<string> { "…" }, 0);
            soilField.AddToClassList("input");
            soilField.AddToClassList("field-stack");
            groundCard.Add(soilField);
            groundCard.Add(Text("What covers the open park? (add more than one with their shares)", "field-label"));
            coverRows = new VisualElement();
            groundCard.Add(coverRows);
            var cr = Row();
            cr.Add(Btn("+ Another cover", () => { AddCoverRow(null, null, 0); }, "btn--ghost"));
            groundCard.Add(cr);
            pathsField = new DropdownField("The footpaths are", new List<string> { "…" }, 0);
            pathsField.AddToClassList("input");
            pathsField.AddToClassList("field-stack");
            groundCard.Add(pathsField);
            groundCard.Add(Btn("Save the answers", () => StartCoroutine(Run(SaveGround(), "Looking up the curve numbers")), "btn--wide"));
            groundResult = Text("", "muted");
            groundCard.Add(groundResult);
            groundPage.Add(groundCard);

            pondCard = new VisualElement();
            pondCard.Add(Text("PONDS", "eyebrow"));
            pondText = Text("", "muted");
            pondCard.Add(pondText);
            pondRows = new VisualElement();
            pondCard.Add(pondRows);
            pondSave = Btn("Save the ponds", () => StartCoroutine(Run(SavePonds(), "Cutting the ponds into the ground model")), "btn--wide");
            pondCard.Add(pondSave);
            pondPage.Add(pondCard);

            wellCard = new VisualElement();
            wellCard.Add(Text("EXISTING RECHARGE WELLS", "eyebrow"));
            wellText = Text("", "muted");
            wellCard.Add(wellText);
            wellCommon = Row();
            wellCommon.AddToClassList("field-row");
            wellDepth = Field("Depth (m)");
            wellDia = Field("Diameter (m)");
            wellRate = Field("Strata infiltration (mm/h)");
            wellRate.tooltip = "How fast the permeable strata at the wells take water, from a borehole log or a percolation test";
            wellCommon.Add(wellDepth);
            wellCommon.Add(wellDia);
            wellCommon.Add(wellRate);
            wellCard.Add(wellCommon);
            wellSingles = new Foldout { text = "Change single wells", value = false };
            wellRows = new VisualElement();
            wellSingles.Add(wellRows);
            wellCard.Add(wellSingles);
            wellSave = Btn("Save the wells", () => StartCoroutine(Run(SaveWells(), "Adding the wells to the flood model")), "btn--wide");
            wellCard.Add(wellSave);
            wellPage.Add(wellCard);
        }

        static TextField Field(string label, string value = "")
        {
            var f = new TextField(label) { value = value };
            f.AddToClassList("input");
            f.AddToClassList("field-stack");
            return f;
        }

        static string Fmt(JToken v) =>
            v == null || v.Type == JTokenType.Null ? "" : ((float)v).ToString("0.##", System.Globalization.CultureInfo.InvariantCulture);

        static float? Num(TextField f) =>
            float.TryParse(f.value, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var v) ? v : (float?)null;

        void SyncGroundAndRain()
        {
            if (rainCard == null) return;
            if (siteConfirmed && info != null && groundFor != projectPath && !busy) StartCoroutine(LoadGroundAndRain());
        }

        IEnumerator LoadGroundAndRain()
        {
            groundFor = projectPath;
            if (bundle) yield break;
            if (groundQuestions == null) yield return api.Get("/ground/questions", x => groundQuestions = x);
            if (rainPresets == null) yield return api.Get("/rainfall/presets", x => rainPresets = x);
            JToken g = null, r = null;
            yield return api.Get(api.P("/site/ground"), x => g = x);
            yield return api.Get(api.P("/rainfall"), x => r = x);
            groundSaved = g != null && g.HasValues ? g : null;
            rainSaved = r != null && r.HasValues ? r : null;
            FillGround();
            FillRain();
            JToken ponds = null;
            yield return api.Get(api.P("/site/ponds"), x => ponds = x);
            FillPonds(ponds?["ponds"]);
            JToken wells = null;
            yield return api.Get(api.P("/site/wells"), x => wells = x);
            FillWells(wells);
        }

        // ------------------------------------------------------------ existing recharge wells
        void FillWells(JToken st)
        {
            wellRows.Clear();
            wellFields.Clear();
            int count = (int?)st?["count"] ?? 0;
            foreach (var e in new VisualElement[] { wellCommon, wellSingles, wellSave }) SpongePark.UI.Kit.Show(e, count > 0);
            if (count == 0)
            {
                wellText.text = "The survey shows no recharge wells in this park. Nothing to answer here; add new wells on the Design tab.";
                return;
            }
            int inModel = (int?)st["in_model"] ?? 0;
            var drawn = st["drawn_diameters_m"]?.Select(x => ((float)x).ToString("0.##")).ToList() ?? new List<string>();
            wellText.text = $"The survey shows {count} recharge well{(count == 1 ? "" : "s")} in the park. They are part of the park today, so they count in " +
                            "the existing site and in every design; a design gets credit only for the wells you add. The drawing gives where they are" +
                            (drawn.Count > 0 ? $" and, for some, the diameter ({string.Join(", ", drawn)} m, used where drawn)" : "") +
                            ", not how deep they are or how fast the strata take water: give these for all of them (single wells can differ, below)." +
                            (inModel < count ? $"\nCheck: {count - inModel} of {count} not in the flood model until answered." : $"\nAll {count} are in the flood model.");
            var a = st["answers"];
            wellDepth.value = Fmt(a?["depth_m"]);
            wellDia.value = Fmt(a?["diameter_m"]);
            wellRate.value = Fmt(a?["infiltration_rate_mm_hr"]);
            foreach (var w in st["wells"])
            {
                var row = new WellRow { Id = (string)w["id"], Depth = Field("Depth (m)", Fmt(w["depth_m"])), Diameter = Field("Diameter (m)", Fmt(w["diameter_m"])) };
                var box = new VisualElement();
                box.AddToClassList("cover-row");
                var miss = w["missing"]?.Select(x => (string)x).ToList() ?? new List<string>();
                var drawnDia = w["drawn_diameter_m"] != null && w["drawn_diameter_m"].Type != JTokenType.Null ? $", drawn {(float)w["drawn_diameter_m"]:0.##} m" : "";
                box.Add(Text($"{row.Id}, ground {(float)w["ground_m"]:0.00} m{drawnDia}" + ((bool?)w["in_model"] == true ? "" : $": needs {string.Join(", ", miss)}"), "field-label"));
                var line = Row("field-row");
                line.Add(row.Depth);
                line.Add(row.Diameter);
                box.Add(line);
                wellRows.Add(box);
                wellFields.Add(row);
            }
        }

        IEnumerator SaveWells()
        {
            var body = new JObject
            {
                ["depth_m"] = Num(wellDepth), ["diameter_m"] = Num(wellDia), ["infiltration_rate_mm_hr"] = Num(wellRate),
                ["wells"] = new JArray(wellFields.Select(r => new JObject { ["id"] = r.Id, ["depth_m"] = Num(r.Depth), ["diameter_m"] = Num(r.Diameter) })),
            };
            JToken r2 = null;
            yield return api.Send("PUT", api.P("/site/wells"), body, x => r2 = x);
            if (r2 == null) yield break;
            siteSetup.Close();   // saved: the dialog closes; the result shows as a toast
            FillWells(r2);
            status = $"Wells saved: {(int)r2["in_model"]} of {(int)r2["count"]} in the flood model of the existing site and every design; the drainage is redone around them.";
            yield return LoadViews();
        }

        // ------------------------------------------------------------ ponds
        void FillPonds(JToken ponds)
        {
            pondRows.Clear();
            pondFields.Clear();
            bool any = ponds is JArray a && a.Count > 0;
            pondSave.style.display = any ? DisplayStyle.Flex : DisplayStyle.None;
            if (!any)
            {
                pondText.text = "The survey shows no ponds in this park (closed outlines on its water layer). Nothing to answer here.";
                return;
            }
            int missing = ponds.Count(x => (bool?)x["in_model"] != true);
            pondText.text = "A pond holds rain until it overflows. The survey has its outline but not its bottom, so give, for each pond, " +
                            "how deep it is from its edge to the bottom and how deep the water usually stands (0 if dry). " +
                            "The room between them is its storage in the flood model." +
                            (missing > 0 ? $"\nCheck: {missing} pond{(missing == 1 ? " is" : "s are")} not in the flood model until answered." : "");
            foreach (var p in ponds)
            {
                var row = new PondRow { Id = (string)p["id"] };
                row.Depth = new TextField("Depth (m)") { value = p["depth_m"]?.Type == JTokenType.Null || p["depth_m"] == null ? "" : ((float)p["depth_m"]).ToString("0.##") };
                row.Water = new TextField("Water usually (m)") { value = p["water_m"]?.Type == JTokenType.Null || p["water_m"] == null ? "" : ((float)p["water_m"]).ToString("0.##") };
                foreach (var f in new[] { row.Depth, row.Water }) { f.AddToClassList("input"); f.AddToClassList("field-stack"); }
                var box = new VisualElement();
                box.AddToClassList("cover-row");
                var storage = (bool?)p["in_model"] == true ? $": stores {(float)p["storage_m3"]:0} m³ in a storm" : ": not in the flood model yet";
                box.Add(Text($"{row.Id}, {(float)p["area_m2"]:0} m², edge at {(float)p["edge_level_m"]:0.00} m{storage}", "field-label"));
                var line = Row("field-row");
                line.Add(row.Depth);
                line.Add(row.Water);
                box.Add(line);
                pondRows.Add(box);
                pondFields.Add(row);
            }
        }

        IEnumerator SavePonds()
        {
            var answers = new JArray(pondFields.Select(r => new JObject { ["id"] = r.Id, ["depth_m"] = Num(r.Depth), ["water_m"] = Num(r.Water) }));
            JToken r2 = null;
            yield return api.Send("PUT", api.P("/site/ponds"), new JObject { ["answers"] = answers }, x => r2 = x);
            if (r2 == null) yield break;
            siteSetup.Close();   // saved: the dialog closes; the result shows as a toast
            FillPonds(r2["ponds"]);
            status = $"Ponds saved: {(float)r2["room_m3"]:0} m³ of room cut into the ground model; the flow lines are redone on it.";
            yield return LoadViews();
        }

        // ------------------------------------------------------------ rainfall
        void FillRain()
        {
            var preset = rainPresets?["hsr_imd_24h"];
            if (rainSaved != null)
            {
                var rows = rainSaved["rows"].Where(x => (float)x["duration_hr"] >= 24).Select(x => $"{(int)x["return_period_yr"]} yr {(float)x["depth_mm"]:0} mm");
                rainText.text = $"In use: {string.Join(" · ", rows)}.\nDesign storms for {string.Join(", ", rainSaved["return_periods"].Select(x => (string)x))} years ({rainSaved["method"]?.ToString().Replace('_', ' ')}, 24 h).\nSource: {rainSaved["source"]}";
                rainButton.text = "Use the HSR rainfall again";
                rainButton.EnableInClassList("btn--ghost", true);
            }
            else if (preset != null)
            {
                var rows = preset["rows"].Select(x => $"{(int)x["return_period_yr"]} yr {(float)x["depth_mm"]:0} mm");
                rainText.text = $"{preset["label"]}: {string.Join(" · ", rows)}.\nSource: {preset["source"]} {preset["note"]}";
                rainButton.text = "Use this rainfall";
                rainButton.EnableInClassList("btn--ghost", false);
            }
        }

        IEnumerator UsePresetRain()
        {
            JToken r = null;
            yield return api.Send("PUT", api.P("/rainfall"), new { preset = "hsr_imd_24h" }, x => r = x);
            if (r == null) yield break;
            siteSetup.Close();   // saved: the dialog closes; the result shows as a toast
            yield return Refresh();
            yield return LoadGroundAndRain();
            var peak = r["storms"].Last();
            status = $"Design storms made for {string.Join(", ", r["return_periods"].Select(x => (string)x))} years " +
                     $"(the {peak["return_period_yr"]}-year storm: {peak["depth_mm"]} mm in 24 h, peak {peak["peak_mm_hr"]} mm/h over 5 min).";
        }

        // ------------------------------------------------------------ ground questionnaire
        static List<string> Labels(JToken list) => list?.Select(x => (string)x["label"]).ToList() ?? new List<string>();
        static string IdOf(JToken list, string label) => list?.FirstOrDefault(x => (string)x["label"] == label)?["id"]?.ToString();
        static string LabelOf(JToken list, string id) => list?.FirstOrDefault(x => (string)x["id"] == id)?["label"]?.ToString();

        void FillGround()
        {
            if (groundQuestions == null) return;
            soilField.choices = Labels(groundQuestions["soils"]);
            pathsField.choices = Labels(groundQuestions["paths"]);
            var a = groundSaved?["answers"];
            soilField.SetValueWithoutNotify(LabelOf(groundQuestions["soils"], (string)a?["soil"] ?? "unknown") ?? soilField.choices.Last());
            pathsField.SetValueWithoutNotify(LabelOf(groundQuestions["paths"], (string)a?["paths"] ?? "paved") ?? pathsField.choices[0]);
            coverRows.Clear();
            covers.Clear();
            if (a?["covers"] is JArray saved && saved.Count > 0)
                foreach (var c in saved) AddCoverRow((string)c["cover"], (string)c["condition"], (float)c["share_pct"]);
            else AddCoverRow("grass", "good", 100);
            ShowGroundResult();
        }

        void AddCoverRow(string cover, string condition, float share)
        {
            if (groundQuestions == null || covers.Count >= 4) return;
            var row = new CoverRow { Root = new VisualElement() };
            row.Root.AddToClassList("cover-row");
            row.Cover = new DropdownField(Labels(groundQuestions["covers"]), 0);
            row.Condition = new DropdownField(Labels(groundQuestions["conditions"]), 0);
            row.Share = new TextField { value = share > 0 ? share.ToString("0") : "" };
            foreach (var f in new VisualElement[] { row.Cover, row.Condition, row.Share }) f.AddToClassList("input");
            row.Share.AddToClassList("cover-share");
            if (cover != null) row.Cover.SetValueWithoutNotify(LabelOf(groundQuestions["covers"], cover) ?? row.Cover.value);
            if (condition != null) row.Condition.SetValueWithoutNotify(LabelOf(groundQuestions["conditions"], condition) ?? row.Condition.value);
            var line = Row();
            line.Add(row.Share);
            line.Add(Text("% of the open park", "muted"));
            var remove = Btn("Remove", () => { covers.Remove(row); row.Root.RemoveFromHierarchy(); }, "btn--ghost");
            line.Add(remove);
            row.Root.Add(row.Cover);
            row.Root.Add(row.Condition);
            row.Root.Add(line);
            coverRows.Add(row.Root);
            covers.Add(row);
        }

        IEnumerator SaveGround()
        {
            var answers = new JObject
            {
                ["soil"] = IdOf(groundQuestions["soils"], soilField.value),
                ["paths"] = IdOf(groundQuestions["paths"], pathsField.value),
                ["covers"] = new JArray(covers.Select(c => new JObject
                {
                    ["cover"] = IdOf(groundQuestions["covers"], c.Cover.value),
                    ["condition"] = IdOf(groundQuestions["conditions"], c.Condition.value),
                    ["share_pct"] = float.TryParse(c.Share.value, out var s) ? s : (covers.Count == 1 ? 100 : 0),
                })),
            };
            JToken r = null;
            yield return api.Send("PUT", api.P("/site/ground"), answers, x => r = x);
            if (r == null) yield break;
            siteSetup.Close();   // saved: the dialog closes; the result shows as a toast
            groundSaved = r;
            ShowGroundResult();
            yield return Refresh();
            status = $"Ground saved: curve number {(float)r["curve_number"]:0.#} (TR-55). The flood simulation can run.";
        }

        void ShowGroundResult()
        {
            if (groundSaved == null) { groundResult.text = "Not answered yet: the flood simulation needs these answers."; return; }
            var g = groundSaved;
            var lines = new List<string>
            {
                $"Curve number {(float)g["curve_number"]:0.#} for the open park (soil group {g["hsg"]}{((bool?)g["soil_assumed"] == true ? ", assumed until a percolation test" : "")}):",
            };
            foreach (var c in g["covers"])
                lines.Add($"  {(float)c["share_pct"]:0} % {c["tr55_label"]}: CN {(float)c["cn"]:0} ({c["citation"]})");
            if (g["runoff_check"] is JArray rc && rc.Count > 0)
                lines.Add("Runoff from the open park (TR-55): " + string.Join(" · ", rc.Where(x => (int)x["return_period_yr"] <= 100)
                    .Select(x => $"{(int)x["return_period_yr"]} yr {(float)x["runoff_mm"]:0.#} of {(float)x["rain_mm"]:0} mm")));
            if ((string)g["paths"] == "paved") lines.Add($"Paved footpaths: {(float)g["paved_path_share"] * 100:0} % of the park, counted as hard surface.");
            groundResult.text = string.Join("\n", lines);
        }

        /// The flow step opens as a 2D plan the first time (3D is a switch away).
        void PlanFirst()
        {
            if (planSetFor) return;
            planSetFor = true;
            rigLeft.Plan = true;
        }
    }
}
