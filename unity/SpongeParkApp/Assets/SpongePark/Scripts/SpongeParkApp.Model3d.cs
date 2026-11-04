// A new project from a 3D model (Rhino .3dm, COLLADA .dae), for a flow and pooling study: the engine lists the model's
// layers, the designer says what each one is and checks the units and size, and the engine builds the ground from it.
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.UIElements;

namespace SpongePark
{
    public partial class SpongeParkApp
    {
        static readonly (string role, string title)[] ModelRoles =
        {
            ("ground", "Ground"), ("nbs", "Rain garden or bioswale (soaks in at the fact sheet rate)"), ("building", "Building (water goes round it)"), ("barrier", "Low wall or check dam (holds water)"),
            ("boundary_wall", "Boundary wall (the site is inside it)"), ("water", "Water surface (the bed under it is used)"),
            ("boundary", "Site boundary (closed curve)"), ("ignore", "Leave out"),
        };

        JToken modelInfo;
        readonly Dictionary<string, string> modelRoles = new Dictionary<string, string>();
        VisualElement modelDialog;
        Label modelSize, modelStatus;
        Button modelBuild;
        float modelScale = 1f, modelCell = 0.5f;

        // New Project has two modes. Existing site: only the survey; the ground and contours come from it. Proposed design:
        // the survey, the design plan and the 3D model, all three: the model of the design, with proposed contours from its levels.
        string newMode, newSurvey = "", newDesign = "", newModel = "";
        string pendingModel, modelSurvey, modelPlan;
        string newProjectNote;
        VisualElement newProjectDialog;

        // A project from the first model import has no model to draw and no survey behind it: it has to be made again.
        void AskToRemakeModel()
        {
            OpenNewProject();
            newMode = "proposed";
            newProjectNote = "This project came from the earlier 3D import, so it has no model to show and its results can't be used. Make it again from the survey, the design plan and the 3D model.";
            status = "This project has no model to show. Make it again with New project.";
            BuildNewProject();
        }

        void OpenNewProject()
        {
            newMode = null;
            newProjectNote = null;
            newSurvey = newDesign = newModel = "";
            pendingModel = modelSurvey = modelPlan = null;
            BuildNewProject();
        }

        VisualElement FileRow(string title, string hint, string path, string dialogTitle, string label, string ext, System.Action<string> set)
        {
            var box = new VisualElement();
            box.style.marginBottom = 12;
            box.Add(Text(title, "field-label"));
            box.Add(Text(hint, "muted"));
            var line = Row("field-row");
            var name = Text(string.IsNullOrEmpty(path) ? "No file chosen" : System.IO.Path.GetFileName(path), "muted");
            name.style.flexGrow = 1;
            line.Add(name);
            line.Add(Btn("Choose…", () => PickFile(dialogTitle, label, ext, p => { set(p); BuildNewProject(); }), "btn--outline"));
            if (!string.IsNullOrEmpty(path)) line.Add(Btn("Clear", () => { set(""); BuildNewProject(); }, "btn--ghost"));
            box.Add(line);
            return box;
        }

        void BuildNewProject()
        {
            newProjectDialog?.RemoveFromHierarchy();
            newProjectDialog = new VisualElement();
            newProjectDialog.AddToClassList("modal-back");
            var box = new VisualElement();
            box.AddToClassList("modal");
            box.style.height = StyleKeyword.Auto;
            newProjectDialog.Add(box);
            box.Add(Text("New project", "h2"));
            if (newProjectNote != null) box.Add(Text(newProjectNote, "muted"));
            box.Add(Text("What do you want to study?", "muted"));
            var modes = Row("field-row");
            var existing = Btn("Existing site", () => { newMode = "existing"; BuildNewProject(); }, newMode == "existing" ? null : "btn--outline");
            existing.tooltip = "How water runs and pools on the park as it is today";
            var proposed = Btn("Proposed design", () => { newMode = "proposed"; BuildNewProject(); }, newMode == "proposed" ? null : "btn--outline");
            proposed.tooltip = "How water runs and pools in a new design";
            modes.Add(existing);
            modes.Add(proposed);
            box.Add(modes);
            if (newMode != null)
            {
                box.Add(FileRow("Site survey (DXF)", "The park as it is today.", newSurvey, "Choose the site survey (DXF)", "Site survey", "dxf,dwg", p => newSurvey = p));
                if (newMode == "proposed")
                {
                    box.Add(FileRow("Design plan (DXF)", "The new design in plan, with its interventions. Its contours are not used.", newDesign, "Choose the design plan (DXF)", "Design plan", "dxf", p => newDesign = p));
                    box.Add(FileRow("3D model (.dae or .3dm)", "The new design in 3D. Its levels make the proposed contours.", newModel, "Choose the 3D model", "3D model", "dae,3dm", p => newModel = p));
                }
                bool ready = newSurvey != "" && (newMode == "existing" || (newDesign != "" && newModel != ""));
                box.Add(Text(newMode == "existing"
                    ? "This builds the ground and contours from the survey."
                    : ready ? "This lines the three up on the survey's coordinates and builds the model of the design, with its proposed contours."
                            : "A proposed design needs all three files.", "muted"));
            }
            var buttons = Row();
            var go = Btn("Continue", () =>
            {
                newProjectDialog.RemoveFromHierarchy();
                bool design = newMode == "proposed";
                pendingModel = design ? newModel : null;
                modelSurvey = null;
                modelPlan = design ? newDesign : null;
                StartCoroutine(StartIntake(newSurvey));
            });
            go.SetEnabled(newMode != null && newSurvey != "" && (newMode == "existing" || (newDesign != "" && newModel != "")));
            buttons.Add(go);
            buttons.Add(Btn("Cancel", () => newProjectDialog.RemoveFromHierarchy(), "btn--outline"));
            box.Add(buttons);
            doc.rootVisualElement.Add(newProjectDialog);
        }

        /// Step 2 of a proposal: the survey's project is studied; the design is made from it.
        void GoToDesign()
        {
            modelSurvey = (string)info["path"];
            modelPlan = (string)info["proposal"]["design_plan"];
            StartCoroutine(StartModelIntake((string)info["proposal"]["model"]));
        }

        // ------------------------------------------------------------ step 3: before and after, if the designer wants it
        VisualElement compareDialog;

        IEnumerator RunCompare()
        {
            JToken r = null;
            yield return api.RunJob("POST", api.P($"/compare/{returnPeriods[rpIdx]}"), null, x => r = x, s => status = "Before and after: " + s);
            if (r == null) { status = "Before and after failed: " + Plain(api.LastError); yield break; }
            surveyLayers = null;   // the flooded areas are new layers
            yield return LoadViews();
            FillSiteLayers();
            contentsDirty = true;
            ShowCompare(r);
        }

        static string Pct(JToken v) => v == null || v.Type == JTokenType.Null ? "" : $"{(float)v:+0;-0;0}%";

        void ShowCompare(JToken r)
        {
            compareDialog?.RemoveFromHierarchy();
            compareDialog = new VisualElement();
            compareDialog.AddToClassList("modal-back");
            var box = new VisualElement();
            box.AddToClassList("modal");
            box.style.width = 680;
            box.style.height = Length.Percent(90);
            compareDialog.Add(box);
            box.Add(Text($"Before and after: {(int)r["rp"]}-year storm", "h2"));
            JToken a = r["before"], b = r["after"], ch = r["change_pct"];
            var list = new ScrollView { horizontalScrollerVisibility = ScrollerVisibility.Hidden };
            list.AddToClassList("modal-list");
            box.Add(list);
            void Line(string name, string x, string y, string z, bool head = false)
            {
                var row = new VisualElement();
                row.style.flexDirection = FlexDirection.Row;
                row.style.flexWrap = Wrap.NoWrap;
                row.style.marginBottom = 6;
                var cells = new[] { Text(name, head ? "field-label" : "muted"), Text(x, head ? "field-label" : "muted"), Text(y, head ? "field-label" : "muted"), Text(z, head ? "field-label" : "muted") };
                cells[0].style.width = Length.Percent(47);
                cells[0].style.whiteSpace = WhiteSpace.Normal;
                foreach (var c in cells.Skip(1)) { c.style.width = Length.Percent(16); c.style.flexShrink = 0; }
                foreach (var c in cells) row.Add(c);
                list.Add(row);
            }
            string M(JToken t, string key, string unit, string f = "N0") => $"{((float)t[key]).ToString(f)} {unit}";
            Line("", "Before", "After", "Change", true);
            Line("Rain on the site", M(a, "rain_m3", "m³"), M(b, "rain_m3", "m³"), "");
            Line("Soaked in", M(a, "soaked_in_m3", "m³"), M(b, "soaked_in_m3", "m³"), "");
            Line("Runoff (did not soak in)", M(a, "runoff_m3", "m³"), M(b, "runoff_m3", "m³"), Pct(ch["runoff_m3"]));
            Line("Runoff depth over the site", M(a, "runoff_mm", "mm"), M(b, "runoff_mm", "mm"), Pct(ch["runoff_mm"]));
            Line("Left the site", M(a, "left_site_m3", "m³"), M(b, "left_site_m3", "m³"), "");
            Line("Still standing at the end", M(a, "standing_at_end_m3", "m³"), M(b, "standing_at_end_m3", "m³"), "");
            Line("Flooded ground, including the basins", M(a, "flood_m2", "m²"), M(b, "flood_m2", "m²"), Pct(ch["flood_m2"]));
            Line("Flood not collected: area", M(a, "not_collected_m2", "m²"), M(b, "not_collected_m2", "m²"), Pct(ch["not_collected_m2"]));
            Line("Flood not collected: most at one time", M(a, "not_collected_peak_m3", "m³"), M(b, "not_collected_peak_m3", "m³"), Pct(ch["not_collected_peak_m3"]));
            Line("Held in rain gardens and swales: most at one time", M(a, "collected_peak_m3", "m³"), M(b, "collected_peak_m3", "m³"), "");
            Line("Deepest water", M(a, "deepest_m", "m", "0.00"), M(b, "deepest_m", "m", "0.00"), Pct(ch["deepest_m"]));
            Line("Pooling points on the ground", $"{(int)a["pooling_points"]}", $"{(int)b["pooling_points"]}", "");
            list.Add(Text($"Flood depth here is {(float)r["flood_depth_m"] * 100:0} cm. {(string)r["label"]}", "muted"));
            list.Add(Text("WHERE RUNOFF IS NOT BEING COLLECTED (AFTER)", "eyebrow"));
            var patches = b["patches"].Take(12).ToList();
            if (patches.Count == 0) list.Add(Text("Nowhere: all of it is held in the rain gardens and swales in this storm.", "muted"));
            foreach (var pa in patches)
            {
                float x = (float)pa["x"], y = (float)pa["y"];
                var row = Row("field-row");
                row.Add(Text($"{(float)pa["area_m2"]:N0} m², up to {(float)pa["max_depth_m"] * 100:0} cm deep", "muted"));
                row.Add(Btn("Show", () => { compareDialog.RemoveFromHierarchy(); FocusOn(x, y, GroundZ(x, y), 30); }, "btn--ghost"));
                list.Add(row);
            }
            var buttons = Row();
            buttons.Add(Btn("See after on the map", () => { compareDialog.RemoveFromHierarchy(); SetLayer((string)r["after_layer"], true); SetLayer((string)r["before_layer"], false); }));
            buttons.Add(Btn("See before on the map", () => { compareDialog.RemoveFromHierarchy(); SetLayer((string)r["before_layer"], true); SetLayer((string)r["after_layer"], false); }, "btn--outline"));
            if (r["image"] != null) buttons.Add(Btn("Open the picture", () => Application.OpenURL("file:///" + ((string)r["image"]).Replace('\\', '/')), "btn--outline"));
            buttons.Add(Btn("Close", () => compareDialog.RemoveFromHierarchy(), "btn--ghost"));
            box.Add(buttons);
            doc.rootVisualElement.Add(compareDialog);
        }

        IEnumerator StartModelIntake(string path)
        {
            if (string.IsNullOrEmpty(path)) yield break;
            if (landingStatus != null) landingStatus.text = "Reading " + System.IO.Path.GetFileName(path) + "…";
            ShowLoading("Reading the model", System.IO.Path.GetFileName(path), "Large models can take a minute.");
            JToken r = null;
            yield return api.Send("POST", "/intake/model/inspect", new { path }, x => r = x, 600);
            HideLoading();
            if (r == null)
            {
                if (landingStatus != null)
                    landingStatus.text = api.LastError.Contains("404")
                        ? "The running engine is older than this app: restart spongepark serve, then try again."
                        : "Could not read the model. " + Plain(api.LastError);
                yield break;
            }
            if (landingStatus != null) landingStatus.text = "";
            modelInfo = r;
            modelRoles.Clear();
            foreach (var L in r["layers"]) modelRoles[(string)L["layer"]] = (string)L["role"];
            modelScale = (float)r["scale_to_m"];
            modelCell = (float)r["cell_m"];
            BuildModelDialog();
        }

        void BuildModelDialog()
        {
            modelDialog?.RemoveFromHierarchy();
            modelDialog = new VisualElement();
            modelDialog.AddToClassList("modal-back");
            var box = new VisualElement();
            box.AddToClassList("modal");
            box.style.height = Length.Percent(90);
            modelDialog.Add(box);
            box.Add(Text("New project from " + System.IO.Path.GetFileName((string)modelInfo["model"]), "h2"));
            box.Add(Text((bool?)modelInfo["by_material"] == true
                ? "This model has no layers, so it is sorted by colour. Check what each colour is: the suggestions come from their shapes."
                : "Say what each layer is. Anything marked ground, building or wall shapes the flow.", "muted"));
            foreach (var note in modelInfo["notes"])
            {
                var n = Text((string)note, "land-status");
                n.style.marginLeft = 0;
                n.style.marginRight = 0;
                box.Add(n);
            }

            var list = new ScrollView { horizontalScrollerVisibility = ScrollerVisibility.Hidden };
            list.AddToClassList("modal-list");
            box.Add(list);
            var titles = ModelRoles.Select(x => x.title).ToList();
            foreach (var L in modelInfo["layers"])
            {
                var name = (string)L["layer"];
                int tris = (int)L["triangles"], curves = (int)L["closed_curves"], unmeshed = (int)L["unmeshed"];
                var parts = new List<string>();
                if (tris > 0) parts.Add($"{tris:N0} triangles");
                if (curves > 0) parts.Add($"{curves} closed curve{(curves > 1 ? "s" : "")}");
                if (unmeshed > 0) parts.Add($"{unmeshed} surface{(unmeshed > 1 ? "s" : "")} with no mesh");
                var row = new VisualElement();
                row.style.marginBottom = 8;
                var head = new VisualElement();
                head.style.flexDirection = FlexDirection.Row;
                head.style.alignItems = Align.Center;
                if (L["color"] != null && L["color"].Type == JTokenType.String && ColorUtility.TryParseHtmlString((string)L["color"], out var swatchColor))
                {
                    var swatch = new VisualElement();
                    swatch.style.width = 14;
                    swatch.style.height = 14;
                    swatch.style.marginRight = 6;
                    swatch.style.backgroundColor = swatchColor;
                    head.Add(swatch);
                }
                head.Add(Text(parts.Count > 0 ? name + " · " + string.Join(" · ", parts) : name + " · nothing to read", "muted"));
                row.Add(head);
                var dd = new DropdownField(titles,
                                           System.Array.FindIndex(ModelRoles, x => x.role == modelRoles[name]));
                dd.AddToClassList("input");
                dd.RegisterValueChangedCallback(e =>
                {
                    modelRoles[name] = ModelRoles[dd.index].role;
                    UpdateModelSummary();
                });
                row.Add(dd);
                list.Add(row);
            }

            var choices = modelInfo["unit_choices"].ToList();
            float start = modelScale;
            int at = choices.FindIndex(c => Mathf.Abs((float)c["to_m"] - start) < 1e-6f * Mathf.Max(start, 1e-6f));
            var units = new DropdownField((bool?)modelInfo["units_known"] == true ? "Units" : "Units (not stated in the file)",
                                          choices.Select(c => (string)c["name"]).ToList(), Mathf.Max(0, at));
            units.AddToClassList("input");
            units.AddToClassList("field-stack");
            units.RegisterValueChangedCallback(e =>
            {
                modelScale = (float)choices[units.index]["to_m"];
                UpdateModelSummary();
            });
            box.Add(units);
            var cell = new TextField("Ground cell size (m)") { value = modelCell.ToString("0.##", CultureInfo.InvariantCulture) };
            cell.AddToClassList("input");
            cell.AddToClassList("field-stack");
            cell.RegisterValueChangedCallback(e =>
            {
                modelCell = float.TryParse(e.newValue, NumberStyles.Float, CultureInfo.InvariantCulture, out var v) ? v : 0f;
                UpdateModelSummary();
            });
            box.Add(cell);
            modelSize = Text("", "muted");
            box.Add(modelSize);
            modelStatus = Text("", "land-status");
            modelStatus.style.marginLeft = 0;
            box.Add(modelStatus);
            var buttons = Row();
            modelBuild = Btn("Build the ground", () => StartCoroutine(FinishModelIntake()));
            buttons.Add(modelBuild);
            buttons.Add(Btn("Cancel", () => modelDialog.RemoveFromHierarchy(), "btn--outline"));
            box.Add(buttons);
            doc.rootVisualElement.Add(modelDialog);
            UpdateModelSummary();
        }

        /// The site's size at the chosen units, from the ground and building layers: a wrong scale shows here.
        void UpdateModelSummary()
        {
            var used = modelInfo["layers"].Where(L => L["min"].Type != JTokenType.Null && modelRoles[(string)L["layer"]] is var role && (role == "ground" || role == "nbs" || role == "building" || role == "barrier" || role == "boundary_wall")).ToList();
            bool hasGround = modelInfo["layers"].Any(L => L["min"].Type != JTokenType.Null && (modelRoles[(string)L["layer"]] == "ground" || modelRoles[(string)L["layer"]] == "nbs"));
            string why = !hasGround ? "Mark a layer holding a mesh as Ground." : modelCell <= 0 ? "Enter a cell size above zero." : "";
            modelBuild.SetEnabled(why == "");
            modelStatus.text = why;
            if (!used.Any()) { modelSize.text = ""; return; }
            float Lo(int i) => used.Min(L => (float)L["min"][i]) * modelScale;
            float Hi(int i) => used.Max(L => (float)L["max"][i]) * modelScale;
            float w = Hi(0) - Lo(0), d = Hi(1) - Lo(1);
            modelSize.text = $"The model is {w:N1} × {d:N1} m ({w * d / 10000:0.##} ha), levels {Lo(2):0.##} to {Hi(2):0.##} m. Check this matches the real site"
                              + (modelRoles.Values.Contains("boundary") ? " (the boundary curve then sets the site inside it)." : ".");
        }

        IEnumerator FinishModelIntake()
        {
            modelBuild.SetEnabled(false);
            var body = new Dictionary<string, object>
            {
                ["model"] = (string)modelInfo["model"], ["roles"] = modelRoles, ["scale_to_m"] = modelScale, ["cell_m"] = modelCell,
            };
            if (!string.IsNullOrEmpty(modelSurvey)) body["survey_project"] = modelSurvey;
            if (!string.IsNullOrEmpty(modelPlan)) body["design_plan"] = modelPlan;
            JToken r = null;
            ShowLoading("Building the ground from the model", "Reading the layers", "This can take a few minutes for a large model.");
            yield return api.RunJob("POST", "/intake/model/finish", body, x => r = x, s => loadingStep = s == "running" ? "Turning the model into a ground grid" : s);
            if (r == null)
            {
                HideLoading();
                modelStatus.text = "The engine reported a problem: " + Plain(api.LastError);
                modelBuild.SetEnabled(true);
                yield break;
            }
            modelDialog.RemoveFromHierarchy();
            var issues = r["qc"]?["issues"]?.Select(x => (string)x).ToList() ?? new List<string>();
            status = "Ground built from the model. " + string.Join(" ", issues);
            projectPath = (string)r["project"];
            loadingWhat = "Opening the project";
            loadingStep = System.IO.Path.GetFileName(projectPath);
            yield return OpenProject(false);
            HideLoading();
            yield return StartGuide();
            ShowMain();
            yield return LoadOpenings();
            AskOpenings();   // the question this project cannot go on without
        }
    }
}
