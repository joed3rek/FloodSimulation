// The workspace (Pass 1 of the professional UI): app bar, ribbon (Site, Analyse, Design, Simulate, Results,
// Export), Contents (layer tree), viewport with overlays, Properties (Properties / Checks / Results) with the guided
// checklist above it, the storm timeline and the status bar; dialogs for Site setup, Targets and Settings; toasts.
// Every control of the old sidebar has a home here; the steps' logic stays in its partial classes.
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using SpongePark.UI;
using UnityEngine;
using UnityEngine.UIElements;
using Tab = SpongePark.UI.Tab;

namespace SpongePark
{
    public partial class SpongeParkApp
    {
        static readonly Color PlanBackground = new Color32(0x1A, 0x1D, 0x21, 0xFF);
        static readonly Color AppBackground = new Color32(0x16, 0x18, 0x1B, 0xFF);

        UiState ui;
        Workspace ws;
        Ribbon ribbon;
        ContentsPanel contentsPanel;
        PropertiesPanel props;
        ChecklistPanel checklist;
        Timeline timeline;
        StatusBar statusBar;
        Toasts toasts;
        Dialog siteSetup, targetsDialog, settingsDialog;
        PanelSettings panelSettings;
        readonly Dictionary<string, Command> commands = new Dictionary<string, Command>();
        bool contentsDirty, lastBusy;
        string contentsKey = "", lastStatus = "";
        Rect viewRect = new Rect(0.3f, 0, 0.7f, 1);
        JObject onboarding;   // the guided project's checklist state (null: not guided)
        Label appProject, appSaved, viewLabelLeft, viewLabelRight, scaleLabel, legendTitle, legendLow, legendHigh;
        VisualElement northArrow, cube, scaleBar, legend, legendRamp;
        DropdownField optionField;
        Button checklistButton;
        Texture2D waterRamp, groundRamp;

        // ------------------------------------------------------------ build
        void BuildUi()
        {
            ui = new UiState();
            ui.Load();
            panelSettings = ScriptableObject.CreateInstance<PanelSettings>();
            panelSettings.themeStyleSheet = Resources.Load<ThemeStyleSheet>("UI/Theme");
            panelSettings.scaleMode = PanelScaleMode.ConstantPixelSize;
            panelSettings.scale = ui.Layout.uiScale;
            doc = gameObject.AddComponent<UIDocument>();
            doc.panelSettings = panelSettings;
            var root = doc.rootVisualElement;
            root.styleSheets.Add(Resources.Load<StyleSheet>("UI/Workspace"));
            root.pickingMode = PickingMode.Ignore;

            // the steps' own controls, placed below
            BuildFlowAndDesignParts();
            BuildSuggestParts();
            compareBox = new VisualElement();
            siteText = Text("", "muted");
            verifyLabel = Text("", "notice");
            videoLabel = Text("", "muted");

            BuildCommands();
            ribbon = new Ribbon(ui, RibbonTabs());
            contentsPanel = new ContentsPanel(ui) { SetAll = SetAllLayers };
            props = new PropertiesPanel(ui);
            checklist = new ChecklistPanel(ui, Stages());
            props.ChecklistSlot.Add(checklist.Root);
            timeline = new Timeline(ui)
            {
                OnPlay = () => playing = !playing,
                OnRestart = () => { simT = 0; if (live) StartCoroutine(StartLive()); },
                OnSpeed = v => speed = v,
                OnScrub = v => { if (!live) { simT = v; left.ShowAt(simT, false, 0); right.ShowAt(simT, false, 0); } },
                OnRp = k => { if (k == rpIdx || returnPeriods.Count == 0) return; rpIdx = k; if (!busy && info != null) StartCoroutine(Run(LoadViews(), "Loading the storm")); },
            };
            statusBar = new StatusBar { OnSnap = () => toasts.Show("Snapping arrives with the drawing tools in Pass 2.", "info") };
            toasts = new Toasts();
            ws = new Workspace(ui, BuildAppBar(), ribbon, contentsPanel, props, timeline, statusBar, toasts);
            root.Add(ws.Root);
            mainApp = ws.Root;
            mainOverlay = new VisualElement();   // the old overlay layer: the workspace has its own
            BuildOverlays(ws.Overlay);
            BuildDialogs(ws.DialogHost);
            BuildProperties();
            ui.PanelRequested += OpenPanel;
            ui.TabChanged += () => { if (ui.ActiveTab == Tab.Analyse && flowData != null) MarkStage("analyse_flow"); };
            CameraRig.BlockInput = () => !PointerInViewport();
        }

        Command C(string id, string label, string icon, string tip, System.Action run, System.Func<bool> enabled = null,
                  System.Func<bool> on = null, System.Func<bool> visible = null, string key = null, bool primary = false)
        {
            var c = new Command
            {
                Id = id, Label = label, Icon = icon, Tooltip = tip, Run = run, Shortcut = key, Primary = primary,
                Enabled = enabled ?? (() => true), On = on ?? (() => false), Visible = visible ?? (() => true),
            };
            commands[id] = c;
            return c;
        }

        bool Engine => engineUp && !busy && !bundle;
        bool HasProject => info != null;
        bool HasGround => HasProject && (bool?)info["has_terrain"] == true;
        bool HasDesign => designFc != null && designFc["features"] is JArray a && a.Count > 0;
        bool WaterShown => live || left.Frames != null || right.Frames != null;

        void BuildCommands()
        {
            // Site
            C("import", "Import survey", "import", "Start a new project from a survey drawing (DXF): link its layers, build the ground",
              () => { EnsureLanding(); PickFile("Choose the site survey (DXF)", "Site survey", "dxf,dwg", p => StartCoroutine(StartIntake(p))); },
              () => engineUp && !busy, visible: () => !bundle, primary: true);
            C("confirm", "Confirm site model", "confirm", "The ground and the survey layers match the site: go on to the analysis",
              () => StartCoroutine(Run(ConfirmSite(true), "Saving")), () => Engine && HasGround, visible: () => !siteConfirmed && !bundle, primary: true);
            C("reopen", "Reopen site model", "confirm", "Go back to checking the site model", () => StartCoroutine(Run(ConfirmSite(false), "Saving")),
              () => Engine && HasGround, visible: () => siteConfirmed && !bundle);
            C("setup", "Site setup", "setup", "Rainfall, the ground (TR-55 questions) and ponds", () => siteSetup.Open(),
              () => HasProject && !bundle, visible: () => !bundle, primary: true);
            C("layers-on", "Show all", "eye", "Show every layer", () => SetAllLayers(true), () => HasGround);
            C("layers-off", "Hide all", "eye-off", "Hide every layer", () => SetAllLayers(false), () => HasGround);
            // Analyse
            foreach (var (k, label, icon) in new[] { (FlowView.Lines, "Flow lines", "flow-lines"), (FlowView.Arrows, "Arrows", "arrows"),
                                                     (FlowView.Ponding, "Ponding", "ponding"), (FlowView.Exits, "Exits", "exits") })
            {
                var key = k;
                C("flow-" + k, label, icon, $"Show or hide the {label.ToLower()} (from the ground alone)", () => SetFlow(key, !FlowOn(key)),
                  () => flowData != null, () => flowData != null && FlowOn(key));
            }
            C("baseline", "Analyse existing", "baseline", "SWMM on the existing park for every storm (needed to compare options)",
              () => StartCoroutine(Run(Baseline(), "Analysing")), () => Engine && siteConfirmed && FloodReady, visible: () => !bundle);
            // Design
            C("select", "Select", "select", "Select, move and reshape elements", () => SetTool(null), () => siteConfirmed && designFc != null, () => tool == null, key: "V");
            foreach (var (t, icon, key) in new[] { ("rain_garden", "rain-garden", "R"), ("bioswale", "bioswale", "B"), ("detention_pond", "detention-pond", "D"),
                                                   ("retention_pond", "retention-pond", "T"), ("recharge_well", "recharge-well", "W") })
            {
                var tt = t;
                C("tool-" + t, ToolNames[t], icon, $"Draw a {ToolNames[t].ToLower()} on the ground", () => SetTool(tt),
                  () => siteConfirmed && designFc != null && !busy, () => tool == tt, key: key);
            }
            C("draw-curve", "Curve", "draw-curve", "Swales and outlines as smooth curves through the points you place (like a CAD spline); with an element selected, smooths it",
              () => SetCurve(true), () => siteConfirmed && designFc != null && !busy, () => DrawCurve);
            C("draw-straight", "Straight", "draw-straight", "Swales and outlines with straight lines between the points you place; with an element selected, straightens it",
              () => SetCurve(false), () => siteConfirmed && designFc != null && !busy, () => !DrawCurve);
            C("delete", "Delete", "delete", "Delete the selected element", DeleteSelected, () => selectedId != null && !busy, key: "Delete");
            C("undo", "Undo", "undo", "Undo the last design change", Undo, () => undoStack.Count > 0 && !busy, key: "Ctrl+Z");
            C("redo", "Redo", "redo", "Redo", Redo, () => redoStack.Count > 0 && !busy, key: "Ctrl+Y");
            C("quick", "Quick layout", "suggest", "Place and size NbS from the flow and the ground, checked in SWMM",
              () => StartCoroutine(Run(Suggest("quick"), "Placing NbS")), () => Engine && siteConfirmed, visible: () => !bundle, primary: true);
            C("optimise-design", "Optimise", "optimise", "Optimiser (about a minute): layouts traded off for storage, area and cost, SWMM-checked",
              () => StartCoroutine(Run(Suggest("optimise"), "Optimising (SWMM-checked)")), () => Engine && siteConfirmed, visible: () => !bundle);
            C("generate", "Generate option", "generate", "An option (not the design): the layout generator, run in SWMM",
              () => StartCoroutine(Run(Generate(false), "Generating")), () => Engine && siteConfirmed, visible: () => !bundle);
            C("optimise-option", "Optimise option", "optimise", "An option from the optimiser (NSGA-II, SWMM-verified)",
              () => StartCoroutine(Run(Generate(true), "Optimising")), () => Engine && siteConfirmed, visible: () => !bundle);
            C("least-area", "Least area", "least-area", "The smallest layout that holds the target storm (optimiser)",
              () => StartCoroutine(Run(Generate(true, "inverse"), "Optimising")), () => Engine && siteConfirmed, visible: () => !bundle);
            C("targets", "Targets", "targets", "Area budget, drawdown and the design storms", () => targetsDialog.Open(), () => HasProject, visible: () => !bundle);
            C("verify", "Check in SWMM", "verify", "Check the design again in SWMM, every storm", CheckAgain, () => Engine && HasDesign, visible: () => !bundle);
            // Simulate
            C("flood", "Run flood simulation", "simulate", "The 2D flood model over the existing ground for the chosen storm",
              () => StartCoroutine(Run(RunFlood(), "Running the flood simulation")), () => Engine && siteConfirmed && FloodReady, visible: () => !bundle, primary: true);
            C("run2d", "Run 2D (option)", "simulate", "The 2D model for the existing site and the chosen option", () => StartCoroutine(Run(Simulate(), "Simulating")),
              () => Engine && options.Any(o => o != "baseline"), visible: () => !bundle);
            C("load", "Load storm", "load", "Load the chosen storm's results into the views", () => StartCoroutine(Run(LoadViews(), "Loading")), () => !busy && (HasProject || bundle));
            C("live", "Live GPU", "gpu", "Run the storm live on the graphics card (indicative)", () => { if (live) live = false; else StartCoroutine(StartLive()); },
              () => !busy && HasGround && FloodReady, () => live, visible: () => !bundle && GpuWaterSim.Supported);
            C("verify-gpu", "Verify GPU", "gpu-check", "Compare the GPU model's volumes with the engine's 2D model (within 1 % of rainfall)",
              () => StartCoroutine(Run(VerifyGpu(), "Verifying")), () => !busy && HasGround, visible: () => !bundle && GpuWaterSim.Supported);
            // Results
            C("split", "Split view", "split", "Existing beside design (cameras linked)", () => { sideBySide = !sideBySide; ApplyViewports(); }, on: () => sideBySide);
            C("swap", "Existing / design", "swap", "In a single view: show the existing site or the design", () => { if (!sideBySide) { showProposed = !showProposed; ApplyViewports(); } },
              () => !sideBySide, () => !sideBySide && showProposed);
            C("show-results", "Results panel", "results", "Open the results in the Properties panel", () => OpenPanel("results"));
            C("table", "Attribute table", "table", "Every element with its sizes and results", () => toasts.Show("The attribute table " + Pass3.Note.ToLower(), "info"));
            // Export
            C("report", "Report, drawings, Rhino", "report", "The report, drawings and a Rhino file for the chosen option", () => StartCoroutine(Run(api.RunJob("POST", api.P($"/options/{CurrentOption}/export"),
                new { out_dir = exportDir }, r => { if (r != null) { status = "Exported to " + exportDir; MarkStage("export"); } }), "Exporting")),
              () => Engine && CurrentOption != null, visible: () => !bundle, primary: true);
            C("bundle", "Web viewer", "web", "A results bundle for the web viewer", () => StartCoroutine(Run(api.RunJob("POST", api.P("/viewer-bundle"),
                new { out_dir = Path.Combine(exportDir, "bundle") }, r => { if (r != null) status = "Bundle written to " + Path.Combine(exportDir, "bundle"); }), "Bundling")),
              () => Engine && HasProject, visible: () => !bundle);
            C("video", "Record video", "video", "Play the storm from the start, touring the park, and record it", () =>
            {
                if (video.Recording) return;
                simT = 0; playing = true; rigLeft.Touring = true;
                video.Begin(Path.Combine(exportDir, "video"));
            }, () => WaterShown && !video.Recording);
            // app bar
            C("home", "Start screen", "home", "Back to the start screen (new, open, recent)", ShowLanding, visible: () => !bundle);
            C("checklist", "Checklist", "checklist", "The project checklist (guided project)", ToggleChecklist, () => HasProject, () => onboarding != null && ui.ChecklistOpen);
            C("settings", "Settings", "settings", "UI scale, guidance for new projects, heights", () => settingsDialog.Open());
            C("max", "Full view", "maximise", "The viewport fills the window (F11)", () => ui.ViewportMax = !ui.ViewportMax, on: () => ui.ViewportMax, key: "F11");
        }

        List<RibbonTab> RibbonTabs()
        {
            var site = new RibbonTab(Tab.Site, "Site");
            site.Group("Survey").Large(commands["import"]);
            site.Group("Model").Large(commands["confirm"]).Large(commands["reopen"]);
            site.Group("Setup").Large(commands["setup"]);
            site.Group("Layers").Small(commands["layers-on"]).Small(commands["layers-off"]);

            var analyse = new RibbonTab(Tab.Analyse, "Analyse");
            analyse.Group("Flow from the ground").Large(commands["flow-lines"]).Large(commands["flow-arrows"]).Large(commands["flow-ponding"]).Large(commands["flow-exits"]);
            analyse.Group("Existing site (SWMM)").Large(commands["baseline"]);

            var design = new RibbonTab(Tab.Design, "Design");
            var draw = design.Group("Draw");
            draw.Large(commands["select"]);
            foreach (var t in ToolTypes) draw.Large(commands["tool-" + t]);
            design.Group("Lines").Small(commands["draw-curve"]).Small(commands["draw-straight"]);
            design.Group("Edit").Small(commands["delete"]).Small(commands["undo"]).Small(commands["redo"]);
            design.Group("Suggest layout").Large(commands["quick"]).Large(commands["optimise-design"]);
            design.Group("Options").Small(commands["generate"]).Small(commands["optimise-option"]).Small(commands["least-area"]);
            design.Group("Targets").Large(commands["targets"]);
            design.Group("Verify").Large(commands["verify"]);

            var sim = new RibbonTab(Tab.Simulate, "Simulate");
            sim.Group("Flood").Large(commands["flood"]).Small(commands["run2d"]).Small(commands["load"]);
            sim.Group("Live").Large(commands["live"]).Small(commands["verify-gpu"]);

            var res = new RibbonTab(Tab.Results, "Results");
            optionField = new DropdownField(new List<string> { "No options yet" }, 0);
            optionField.AddToClassList("input");
            optionField.AddToClassList("ribbon-field");
            optionField.tooltip = "The option to compare with the existing site";
            optionField.RegisterValueChangedCallback(e =>
            {
                int k = optionField.index;
                if (k >= 0 && k < options.Count && k != optionIdx) { optionIdx = k; StartCoroutine(LoadComparison()); }
            });
            var og = res.Group("Option");
            og.Add(optionField);
            res.Group("View").Large(commands["split"]).Large(commands["swap"]);
            res.Group("Tables").Large(commands["show-results"]).Large(commands["table"]);

            var exp = new RibbonTab(Tab.Export, "Export");
            var folder = new TextField { value = exportDir };
            folder.AddToClassList("input");
            folder.style.width = 300;
            folder.tooltip = "Folder the deliverables are written to";
            folder.RegisterValueChangedCallback(e => exportDir = e.newValue);
            exp.Group("Folder").Add(folder);
            exp.Group("Deliverables").Large(commands["report"]).Large(commands["bundle"]).Large(commands["video"]);
            return new List<RibbonTab> { site, analyse, design, sim, res, exp };
        }

        VisualElement BuildAppBar()
        {
            var bar = Kit.Box("appbar");
            var logo = new Button(() => commands["home"].Run()) { tooltip = "Back to the start screen" };
            logo.AddToClassList("appbar-logo");
            var mark = Kit.Box("logo-mark");
            mark.Add(new Label("S"));
            logo.Add(mark);
            logo.Add(Kit.Label("Sponge Park", "appbar-title"));
            bar.Add(logo);
            bar.Add(Kit.Box("appbar-sep"));
            appProject = Kit.Label("", "appbar-project");
            bar.Add(appProject);
            appSaved = Kit.Label("", "appbar-saved");
            bar.Add(appSaved);
            bar.Add(Kit.Box("appbar-sep"));
            bar.Add(Kit.IconButton("undo", "Undo (Ctrl+Z)", () => commands["undo"].Run()));
            bar.Add(Kit.IconButton("redo", "Redo (Ctrl+Y)", () => commands["redo"].Run()));
            bar.Add(Kit.Box("appbar-gap"));
            var search = Kit.Box("search");
            search.Add(Kit.Icon("search"));
            search.Add(Kit.Label("Search commands", ""));
            search.Add(Kit.Label("Ctrl+K", "kbd"));
            search.RegisterCallback<ClickEvent>(e => toasts.Show("Command search " + Pass3.Note.ToLower(), "info"));
            bar.Add(search);
            var seg = Kit.Box("seg");
            var designMode = new Button(() => { }) { text = "Design" };
            designMode.AddToClassList("seg-btn");
            designMode.AddToClassList("seg-btn--on");
            var present = new Button(() => toasts.Show("Present mode " + Pass3.Note.ToLower(), "info")) { text = "Present" };
            present.AddToClassList("seg-btn");
            seg.Add(designMode);
            seg.Add(present);
            bar.Add(seg);
            bar.Add(Kit.Box("appbar-gap"));
            bar.Add(AppButton("max"));
            checklistButton = AppButton("checklist");
            bar.Add(checklistButton);
            bar.Add(AppButton("settings"));
            return bar;
        }

        Button AppButton(string id)
        {
            var c = commands[id];
            var b = Kit.IconButton(c.Icon, c.Tooltip + (c.Shortcut != null ? $" ({c.Shortcut})" : ""), () => { if (c.Enabled()) c.Run(); });
            appButtons.Add((c, b));
            return b;
        }

        readonly List<(Command c, Button b)> appButtons = new List<(Command, Button)>();

        // ------------------------------------------------------------ viewport overlays
        void BuildOverlays(VisualElement overlay)
        {
            var tl = Kit.Box("vp-tl");
            var views = Kit.Box("seg");
            var b2 = new Button(() => rigLeft.Plan = true) { text = "2D" };
            var b3 = new Button(() => rigLeft.Plan = false) { text = "3D" };
            foreach (var b in new[] { b2, b3 }) { b.AddToClassList("seg-btn"); views.Add(b); }
            overlayToggles.Add((b2, () => rigLeft.Plan));
            overlayToggles.Add((b3, () => !rigLeft.Plan));
            tl.Add(views);
            var heights = Kit.Box("seg");
            foreach (var x in new[] { 1f, 3f, 5f })
            {
                var v = x;
                var b = new Button(() => SetHeights(v)) { text = $"×{v:0}", tooltip = v == 1 ? "True heights" : $"Heights shown {v:0} times (display only)" };
                b.AddToClassList("seg-btn");
                heights.Add(b);
                overlayToggles.Add((b, () => Mathf.Approximately(exaggeration, v)));
            }
            tl.Add(heights);
            overlay.Add(tl);

            var tc = Kit.Box("vp-tc");
            tc.Add(drawHint);
            overlay.Add(tc);

            var tr = Kit.Box("vp-tr");
            tr.style.flexDirection = FlexDirection.Column;
            tr.style.alignItems = Align.FlexEnd;
            var tools = Kit.Box("vp-box");
            tools.Add(OverlayButton("extents", "Zoom to the whole site (Home)", ZoomExtents, null));
            tools.Add(OverlayButton("split", "Split view: existing beside design", () => commands["split"].Run(), () => sideBySide));
            tools.Add(OverlayButton("swap", "Existing or design (single view)", () => commands["swap"].Run(), () => !sideBySide && showProposed));
            tools.Add(OverlayButton("tour", "Tour: the camera circles the park", () => rigLeft.Touring = !rigLeft.Touring, () => rigLeft.Touring));
            tools.Add(OverlayButton("maximise", "Full view (F11)", () => ui.ViewportMax = !ui.ViewportMax, () => ui.ViewportMax));
            tr.Add(tools);
            var nb = Kit.Box("vp-box", "north");
            nb.style.marginTop = 6;
            nb.style.marginRight = 0;
            northArrow = Kit.Icon("north");
            nb.Add(northArrow);
            nb.tooltip = "North";
            tr.Add(nb);
            cube = Kit.Box("vp-box", "cube");
            cube.style.marginTop = 6;
            cube.style.marginRight = 0;
            var top = new Button(() => { rigLeft.Plan = false; rigLeft.Pitch = 85; }) { text = "TOP" };
            top.AddToClassList("cube-btn");
            top.AddToClassList("cube-btn--top");
            cube.Add(top);
            var dirs = Kit.Box("cube-row");
            foreach (var (label, yaw) in new[] { ("N", 0f), ("E", 90f), ("S", 180f), ("W", 270f) })
            {
                var y = yaw;
                var b = new Button(() => rigLeft.Yaw = y) { text = label, tooltip = $"Look from the {label switch { "N" => "south, facing north", "E" => "west, facing east", "S" => "north, facing south", _ => "east, facing west" }}" };
                b.AddToClassList("cube-btn");
                dirs.Add(b);
            }
            cube.Add(dirs);
            tr.Add(cube);
            overlay.Add(tr);

            var bl = Kit.Box("vp-bl");
            scaleBar = Kit.Box("scalebar");
            var bar = Kit.Box("scalebar-bar");
            scaleBar.Add(bar);
            scaleLabel = Kit.Label("", "");
            scaleBar.Add(scaleLabel);
            bl.Add(scaleBar);
            overlay.Add(bl);

            var br = Kit.Box("vp-br");
            legend = Kit.Box("legend");
            legendTitle = Kit.Label("", "legend-title");
            legend.Add(legendTitle);
            legendRamp = Kit.Box("legend-ramp");
            legend.Add(legendRamp);
            var ends = Kit.Box("legend-ends");
            legendLow = Kit.Label("", "");
            legendHigh = Kit.Label("", "");
            ends.Add(legendLow);
            ends.Add(legendHigh);
            legend.Add(ends);
            br.Add(legend);
            overlay.Add(br);

            viewLabelLeft = Kit.Label("EXISTING", "vp-hint");
            viewLabelRight = Kit.Label("DESIGN", "vp-hint");
            foreach (var l in new[] { viewLabelLeft, viewLabelRight })
            {
                l.style.position = Position.Absolute;
                l.style.bottom = 44;
                overlay.Add(l);
            }
            viewLabelLeft.style.left = Length.Percent(2);
            viewLabelRight.style.left = Length.Percent(52);
            waterRamp = Ramp(new Color(0.55f, 0.78f, 0.95f), new Color(0.08f, 0.32f, 0.72f));
            groundRamp = Ramp3(new Color(0.30f, 0.50f, 0.44f), new Color(0.50f, 0.62f, 0.34f), new Color(0.80f, 0.70f, 0.47f));
        }

        readonly List<(Button b, System.Func<bool> on)> overlayToggles = new List<(Button, System.Func<bool>)>();

        Button OverlayButton(string icon, string tip, System.Action run, System.Func<bool> on)
        {
            var b = Kit.IconButton(icon, tip, run);
            if (on != null) overlayButtons.Add((b, on));
            return b;
        }

        readonly List<(Button b, System.Func<bool> on)> overlayButtons = new List<(Button, System.Func<bool>)>();

        static Texture2D Ramp(Color a, Color b) => Ramp3(a, Color.Lerp(a, b, 0.5f), b);

        static Texture2D Ramp3(Color a, Color m, Color b)
        {
            var t = new Texture2D(64, 1) { wrapMode = TextureWrapMode.Clamp };
            for (int i = 0; i < 64; i++)
            {
                float f = i / 63f;
                t.SetPixel(i, 0, f < 0.5f ? Color.Lerp(a, m, f * 2) : Color.Lerp(m, b, (f - 0.5f) * 2));
            }
            t.Apply();
            return t;
        }

        void ZoomExtents()
        {
            var mf = left.Terrain.GetComponent<MeshFilter>();
            if (mf == null || mf.sharedMesh == null) return;
            rigLeft.Frame(mf.sharedMesh.bounds, sideBySide);
            rigRight.Frame(mf.sharedMesh.bounds, sideBySide);
        }

        // ------------------------------------------------------------ dialogs
        void BuildDialogs(VisualElement host)
        {
            siteSetup = new Dialog("Site setup", host);
            var rainPage = siteSetup.Page("rainfall", "Rainfall");
            var groundPage = siteSetup.Page("ground", "Ground");
            var pondPage = siteSetup.Page("ponds", "Ponds");
            var wellPage = siteSetup.Page("wells", "Wells");
            if (!bundle) BuildGroundAndRain(rainPage, groundPage, pondPage, wellPage);

            targetsDialog = new Dialog("Targets", host);
            var tb = targetsDialog.Body;
            tb.Add(Text("What the suggestions aim for. Saved as your decisions in the project.", "muted"));
            tb.Add(SliderField("Area budget", 2, 30, budgetPct, "% of site", v => budgetPct = v));
            tb.Add(SliderField("Maximum drawdown", 12, 96, maxDrawdownHr, "hours", v => maxDrawdownHr = v));
            tb.Add(TextInput("Size elements for storm (yr)", designRp.ToString(), v => { if (int.TryParse(v, out var x)) designRp = x; }));
            tb.Add(TextInput("Least-area target storm (yr)", targetRp.ToString(), v => { if (int.TryParse(v, out var x)) targetRp = x; }));
            tb.Add(Btn("Save targets", () => StartCoroutine(Run(SetTargets(), "Saving targets"))));

            settingsDialog = new Dialog("Settings", host);
            var sb = settingsDialog.Body;
            sb.Add(Text("UI SCALE", "eyebrow"));
            var scaleRow = Row();
            foreach (var s in new[] { 0.9f, 1f, 1.15f })
            {
                var v = s;
                var b = Chip($"{v * 100:0} %", () => SetUiScale(v));
                scaleRow.Add(b);
                overlayToggles.Add((b, () => Mathf.Approximately(ui.Layout.uiScale, v)));
            }
            sb.Add(scaleRow);
            sb.Add(Text("For laptop screens with larger or smaller text settings.", "muted"));
            sb.Add(Text("GUIDANCE", "eyebrow"));
            var guide = new Toggle("Guide me through new projects (checklist)") { value = ui.Layout.guideNewProjects };
            guide.RegisterValueChangedCallback(e => ui.ChangeLayout(l => l.guideNewProjects = e.newValue));
            sb.Add(guide);
            sb.Add(Btn("Show the checklist for this project", () => { settingsDialog.Close(); if (onboarding == null) ToggleChecklist(); else ui.ChecklistOpen = true; }, "btn--outline"));
            sb.Add(Text("HEIGHTS", "eyebrow"));
            sb.Add(SliderField("Height exaggeration (display only)", 1, 20, exaggeration, "x", v => pendingHeights = v));
            sb.Add(Btn("Apply heights", () => SetHeights(Mathf.Round(pendingHeights * 2) / 2), "btn--outline"));
        }

        float pendingHeights = 3;

        void SetUiScale(float v)
        {
            ui.ChangeLayout(l => l.uiScale = v);
            panelSettings.scale = v;
        }

        // ------------------------------------------------------------ Properties
        void BuildProperties()
        {
            props.Section("properties", "Selected element", propsBox, () => selectedId != null && propsBox.childCount > 0);
            props.Section("properties", "Site", siteText, () => selectedId == null);
            props.Section("properties", "Flow from the ground", flowText, () => selectedId == null && siteConfirmed);
            props.Section("properties", "Flood simulation", floodText, () => selectedId == null && siteConfirmed && !bundle);
            props.Section("properties", "Rainfall and ground", setupSummary = Text("", "muted"), () => selectedId == null && HasProject && !bundle);
            var cal = Text("", "muted");
            calibrationText = cal;
            props.Section("properties", "Results are", cal, () => selectedId == null && HasProject);

            var budget = new VisualElement();
            budget.Add(budgetLabel);
            budget.Add(budgetBar);
            props.Section("checks", "Area budget", budget, () => designResult != null);
            props.Section("checks", "Design checks", warnBox, () => warnBox.childCount > 0);
            props.EmptyText("checks", () => designResult == null ? "Checks appear once the design has elements (Design tab)." : "No checks to show: every element is within its limits.");

            props.Section("results", "Where water collects", hotspotList, () => hotspotList.childCount > 0);
            props.Section("results", "Design results (SWMM)", resultsCard, () => HasDesign || resultsBox.childCount > 0);
            props.Section("results", "Suggested layouts", suggestCard, () => suggestList.childCount > 0);
            props.Section("results", "Option against the existing site", compareBox, () => comparison != null);
            props.Section("results", "GPU check", verifyLabel, () => !string.IsNullOrEmpty(verify));
            props.Section("results", "Video", videoLabel, () => !string.IsNullOrEmpty(video.Result));
            props.EmptyText("results", () => !siteConfirmed ? "Results appear after the site model is confirmed (Site tab)."
                : "No results yet: Analyse shows where water collects; Simulate runs the flood; Design checks NbS in SWMM.");
            props.EmptyText("properties", () => "Open a project to see its properties.");
        }

        Label setupSummary, calibrationText;

        string SetupSummary()
        {
            var lines = new List<string>();
            if (rainSaved != null)
                lines.Add("Rainfall: " + string.Join(" · ", rainSaved["rows"].Where(x => (float)x["duration_hr"] >= 24).Select(x => $"{(int)x["return_period_yr"]} yr {(float)x["depth_mm"]:0} mm")));
            else lines.Add("Rainfall: not set (Site > Site setup > Rainfall).");
            if (groundSaved != null) lines.Add($"Ground: curve number {(float)groundSaved["curve_number"]:0.#}, soil group {groundSaved["hsg"]}.");
            else lines.Add("Ground: not answered (Site > Site setup > Ground).");
            return string.Join("\n", lines);
        }

        // ------------------------------------------------------------ Contents
        void SyncContents()
        {
            var els = designResult?["elements"] as JArray;
            var key = $"{surveyLayers?["layers"]?.Count()}|{flowData != null}|{WaterShown}|{(els == null ? "" : string.Join(",", els.Select(e => (string)e["id"] + (e["locked"]?.ToString() ?? ""))))}|{comparison != null}|{HasProject}";
            if (!contentsDirty && key == contentsKey) { contentsPanel.Refresh(); return; }
            contentsDirty = false;
            contentsKey = key;
            var groups = new List<ContentsGroup>();
            var survey = new ContentsGroup { Key = "survey", Title = "Survey", Empty = HasProject ? "No survey layers in this project." : "Open or create a project." };
            if (HasGround)
                survey.Rows.Add(new ContentsRow
                {
                    Key = ContoursLayer, Label = "Contours (ground model)", Count = $"{left.Terrain.ContourInterval:0.##} m",
                    Swatch = new Color(0.55f, 0.38f, 0.22f), Visible = () => LayerOn(ContoursLayer), SetVisible = on => SetLayer(ContoursLayer, on),
                    Tooltip = $"Drawn from the ground model the engine built, every {left.Terrain.ContourInterval:0.##} m (stronger every {left.Terrain.ContourInterval * 5:0.##} m)",
                });
            if (surveyLayers != null)
                foreach (var L in surveyLayers["layers"])
                {
                    var name = (string)L["name"];
                    ColorUtility.TryParseHtmlString((string)L["color"], out var col);
                    var src = L["source_layers"]?.Values<string>().ToList() ?? new List<string>();
                    var note = (string)L["note"];
                    survey.Rows.Add(new ContentsRow
                    {
                        Key = name, Label = (string)L["title"] ?? name, Count = $"{(int)L["count"]}", Swatch = col,
                        Visible = () => LayerOn(name), SetVisible = on => SetLayer(name, on), Check = !string.IsNullOrEmpty(note),
                        Tooltip = $"{name} (from {(src.Count > 0 ? string.Join(", ", src) : name)}): {(int)L["count"]} objects" + (string.IsNullOrEmpty(note) ? "" : " · " + note),
                    });
                }
            groups.Add(survey);

            var analysis = new ContentsGroup { Key = "analysis", Title = "Analysis", Empty = siteConfirmed ? "Working out the flow…" : "Confirm the site model (Site tab) to see where water runs." };
            if (flowData != null)
                foreach (var (k, label, col) in new[] { (FlowView.Lines, "Flow lines", new Color(0.29f, 0.61f, 0.79f)), (FlowView.Arrows, "Flow arrows", new Color(0.17f, 0.35f, 0.5f)),
                                                         (FlowView.Ponding, "Ponding hotspots", new Color(0.36f, 0.55f, 0.85f)), (FlowView.Exits, "Exits", new Color(0.76f, 0.29f, 0.23f)) })
                {
                    var kk = k;
                    analysis.Rows.Add(new ContentsRow { Key = "flow:" + k, Label = label, Swatch = col, Visible = () => FlowOn(kk), SetVisible = on => SetFlow(kk, on) });
                }
            if (WaterShown)
                analysis.Rows.Add(new ContentsRow
                {
                    Key = "water", Label = "Flood depth (water)", Swatch = new Color(0.08f, 0.32f, 0.72f),
                    Visible = () => left.Water.gameObject.activeSelf, SetVisible = on => { left.Water.gameObject.SetActive(on); right.Water.gameObject.SetActive(on); },
                    Tooltip = "The storm's water, from the 2D model (indicative)",
                });
            groups.Add(analysis);

            var design = new ContentsGroup { Key = "design", Title = "Design", Empty = siteConfirmed ? "No elements yet: Design tab, choose a tool and draw." : "Design opens after the site model is confirmed." };
            if (els != null)
                foreach (var e in els.OrderBy(e => (string)e["type"]).ThenBy(e => (string)e["id"]))
                {
                    var id = (string)e["id"];
                    var type = (string)e["type"];
                    var size = e["length_m"] != null && e["length_m"].Type != JTokenType.Null ? $"{(float)e["length_m"]:0} m" : $"{(float)e["area_m2"]:0} m²";
                    var f = Feature(id);
                    bool locked = f?["properties"]?["locked"] != null && f["properties"]["locked"].Type == JTokenType.Boolean && (bool)f["properties"]["locked"];
                    design.Rows.Add(new ContentsRow
                    {
                        Key = id, Label = $"{id} · {(ToolNames.TryGetValue(type, out var n) ? n : type)}", Count = size, Swatch = DesignOverlay.TypeColour(type),
                        Selected = () => selectedId == id, Select = () => { Select(id, true); OpenPanel("properties"); }, Locked = locked,
                        Tooltip = $"Stores about {(float)e["storage_m3"]:0.#} m³",
                    });
                }
            groups.Add(design);

            var results = new ContentsGroup { Key = "results", Title = "Results", Empty = "No results yet." };
            if (flowData != null)
                results.Rows.Add(new ContentsRow { Key = "r-flow", Label = "Where water collects", Swatch = new Color(0.36f, 0.55f, 0.85f), Select = () => OpenPanel("results"), Count = $"{flowData["hotspots"]?.Count() ?? 0}" });
            if (HasDesign)
                results.Rows.Add(new ContentsRow { Key = "r-design", Label = "Design results (SWMM)", Swatch = new Color(0.31f, 0.64f, 0.88f), Select = () => OpenPanel("results") });
            if (comparison != null)
                results.Rows.Add(new ContentsRow { Key = "r-option", Label = $"Option {CurrentOption} against existing", Swatch = new Color(0.6f, 0.6f, 0.6f), Select = () => OpenPanel("results") });
            groups.Add(results);
            contentsPanel.Rebuild(groups);
        }

        // ------------------------------------------------------------ guided project (checklist)
        List<Stage> Stages() => new List<Stage>
        {
            new Stage { Id = "import_survey", Title = "Import survey", Why = "The survey drawing gives the ground, the paths, trees and walls.", Action = "Import survey",
                        State = () => HasGround ? StageState.Done : StageState.Current, Go = () => commands["import"].Run() },
            new Stage { Id = "confirm_site", Title = "Confirm site model", Why = "Everything after this is worked out on this ground: check it in 3D first.",
                        Missing = "Needs a survey with a ground model.", Action = "Go to the Site tab",
                        State = () => siteConfirmed ? StageState.Done : HasGround ? StageState.Current : StageState.Locked, Go = () => ui.ActiveTab = Tab.Site },
            new Stage { Id = "site_setup", Title = "Site setup (rainfall, ground, ponds)", Why = "How much rain falls, and how much of it soaks in, decide everything that follows.",
                        Missing = "Confirm the site model first.", Action = "Open Site setup",
                        State = () => FloodReady ? StageState.Done : siteConfirmed ? Next("site_setup") : StageState.Locked, Go = () => siteSetup.Open() },
            new Stage { Id = "analyse_flow", Title = "Analyse flow", Why = "Where water runs and collects shows where NbS will catch it.",
                        Missing = "Confirm the site model first.", Action = "Open the Analyse tab",
                        State = () => StageDone("analyse_flow") ? StageState.Done : siteConfirmed ? Next("analyse_flow") : StageState.Locked,
                        Go = () => { ui.ActiveTab = Tab.Analyse; rigLeft.Plan = true; } },
            new Stage { Id = "flood_simulation", Title = "Run the flood simulation", Why = "Shows how deep the existing park floods in the design storm.",
                        Missing = "Needs the rainfall and the ground answers (Site setup).", Action = "Run it",
                        State = () => left.Frames != null || StageDone("flood_simulation") ? StageState.Done : siteConfirmed && FloodReady ? Next("flood_simulation") : StageState.Locked,
                        Go = () => { ui.ActiveTab = Tab.Simulate; if (commands["flood"].Enabled()) commands["flood"].Run(); } },
            new Stage { Id = "design_nbs", Title = "Design NbS", Why = "Rain gardens, swales, ponds and wells where the water collects.",
                        Missing = "Confirm the site model first.", Action = "Open the Design tab",
                        State = () => HasDesign ? StageState.Done : siteConfirmed ? Next("design_nbs") : StageState.Locked, Go = () => ui.ActiveTab = Tab.Design },
            new Stage { Id = "verify", Title = "Verify in SWMM", Why = "SWMM checks how much of each storm the design keeps on site.",
                        Missing = "Add NbS to the design first.", Action = "Check in SWMM",
                        State = () => designVerified || StageDone("verify") ? StageState.Done : HasDesign ? Next("verify") : StageState.Locked,
                        Go = () => { OpenPanel("results"); if (commands["verify"].Enabled()) commands["verify"].Run(); } },
            new Stage { Id = "export", Title = "Export", Why = "The report, drawings and Rhino file for the team and the client.",
                        Missing = "Verify the design first.", Action = "Open the Export tab",
                        State = () => StageDone("export") ? StageState.Done : designVerified || StageDone("verify") ? Next("export") : StageState.Locked,
                        Go = () => ui.ActiveTab = Tab.Export },
        };

        /// Current for the first open stage, open for the rest.
        StageState Next(string id)
        {
            foreach (var s in stageOrder)
            {
                if (s == id) return StageState.Current;
                if (!StageCompleted(s)) return StageState.Open;
            }
            return StageState.Open;
        }

        static readonly string[] stageOrder = { "import_survey", "confirm_site", "site_setup", "analyse_flow", "flood_simulation", "design_nbs", "verify", "export" };

        bool StageCompleted(string id) => id switch
        {
            "import_survey" => HasGround,
            "confirm_site" => siteConfirmed,
            "site_setup" => FloodReady,
            "analyse_flow" => StageDone("analyse_flow"),
            "flood_simulation" => left.Frames != null || StageDone("flood_simulation"),
            "design_nbs" => HasDesign,
            "verify" => designVerified || StageDone("verify"),
            _ => StageDone(id),
        };

        bool StageDone(string id) => onboarding?["done"] is JArray d && d.Any(x => (string)x == id);

        /// A stage only the app sees (flow looked at, design verified, exported): recorded in the project.
        void MarkStage(string id)
        {
            if (onboarding == null || StageDone(id)) return;
            ((JArray)onboarding["done"]).Add(id);
            StartCoroutine(SaveOnboarding());
        }

        IEnumerator LoadOnboarding()
        {
            onboarding = null;
            if (bundle) yield break;
            JToken r = null;
            yield return api.Get(api.P("/onboarding"), x => r = x);
            if (r is JObject o && o.HasValues && (bool?)o["guided"] == true) onboarding = o;
            if (onboarding != null && onboarding["done"] == null) onboarding["done"] = new JArray();
            if (onboarding != null) ui.ChecklistOpen = true;
        }

        IEnumerator SaveOnboarding()
        {
            if (onboarding == null) yield break;
            yield return api.Send("PUT", api.P("/onboarding"), onboarding, null);
        }

        /// A new project (from a survey): guided when the user has not turned guidance off.
        IEnumerator StartGuide()
        {
            if (!ui.Layout.guideNewProjects) yield break;
            onboarding = new JObject { ["guided"] = true, ["done"] = new JArray(), ["coach_seen"] = new JArray() };
            ui.ChecklistOpen = true;
            yield return SaveOnboarding();
        }

        void ToggleChecklist()
        {
            if (!HasProject) return;
            if (onboarding == null)
            {
                onboarding = new JObject { ["guided"] = true, ["done"] = new JArray(), ["coach_seen"] = new JArray() };
                StartCoroutine(SaveOnboarding());
                ui.ChecklistOpen = true;
                return;
            }
            ui.ChecklistOpen = !ui.ChecklistOpen;
        }

        // ------------------------------------------------------------ panels by name (-spPanel, checklist buttons)
        void OpenPanel(string name)
        {
            if (string.IsNullOrEmpty(name)) return;
            var parts = name.Split(':');
            switch (parts[0])
            {
                case "tab":
                    if (parts.Length > 1 && System.Enum.TryParse<Tab>(parts[1], true, out var t)) ribbon.Select(t);
                    break;
                case "properties": case "checks": case "results":
                    ui.PropsTab = parts[0];
                    if (ui.Layout.propsCollapsed) ui.ChangeLayout(l => l.propsCollapsed = false);
                    break;
                case "contents":
                    if (ui.Layout.contentsCollapsed) ui.ChangeLayout(l => l.contentsCollapsed = false);
                    break;
                case "checklist": if (onboarding == null) ToggleChecklist(); else ui.ChecklistOpen = true; break;
                case "site-setup": siteSetup.Open(parts.Length > 1 ? parts[1] : null); break;
                case "targets": targetsDialog.Open(); break;
                case "settings": settingsDialog.Open(); break;
                case "max": ui.ViewportMax = true; break;
                case "run":   // a ribbon command by id, e.g. run:live (when it is enabled)
                    if (parts.Length > 1 && commands.TryGetValue(parts[1], out var cmd) && cmd.Enabled()) cmd.Run();
                    break;
            }
        }

        // ------------------------------------------------------------ every frame
        void LateUpdate()
        {
            if (doc == null) return;
            AnimateLanding();
            if (Input.GetKeyDown(KeyCode.F11)) ui.ViewportMax = !ui.ViewportMax;
            SyncFlowAndDesign();
            SyncAtmosphere();
            SyncComparison();
            SyncOptions();
            ribbon.Refresh();
            foreach (var (c, b) in appButtons)
            {
                Kit.Show(b, c.Visible());
                b.SetEnabled(c.Enabled());
                b.EnableInClassList("ib--on", c.On());
            }
            foreach (var (b, on) in overlayToggles) b.EnableInClassList(b.ClassListContains("chip") ? "chip--on" : "seg-btn--on", on());
            foreach (var (b, on) in overlayButtons) b.EnableInClassList("ib--on", on());
            SyncContents();
            siteText.text = SiteSummary();
            setupSummary.text = SetupSummary();
            calibrationText.text = calibration.StartsWith("uncalibrated")
                ? "Uncalibrated: suitable for comparing designs, not absolute prediction. Water animation: 2D model, indicative; litres: SWMM."
                : calibration;
            if (!string.IsNullOrEmpty(verify))
            {
                verifyLabel.text = verify;
                verifyLabel.EnableInClassList("notice--warn", !verify.StartsWith("PASS"));
            }
            videoLabel.text = video.Result;
            props.Refresh();
            bool guided = onboarding != null && ui.ChecklistOpen && HasProject;
            Kit.Show(checklist.Root, guided);
            if (guided) checklist.Refresh();
            timeline.Refresh(TimelineNow());
            statusBar.Refresh(StatusNow());
            SyncOverlays();
            SyncViewRect();
            appProject.text = HasProject ? (string)info["name"] ?? Path.GetFileNameWithoutExtension(projectPath) : bundle ? "Results viewer" : "No project";
            appSaved.text = !HasProject ? "" : busy ? "saving…" : "saved";
            Toast();
        }

        void SyncOptions()
        {
            var labels = options.Count == 0 ? new List<string> { "No options yet" } : options.Select(o => o == "baseline" ? "existing" : o).ToList();
            if (string.Join(",", labels) != string.Join(",", optionField.choices)) optionField.choices = labels;
            optionField.SetValueWithoutNotify(labels[Mathf.Clamp(optionIdx, 0, labels.Count - 1)]);
        }

        /// A toast when a job finishes (and for every error).
        void Toast()
        {
            if (status != lastStatus && status.StartsWith("Error")) toasts.Show(status.Substring(6).Trim(), "error", 8);
            else if (lastBusy && !busy && !status.StartsWith("Error") && !string.IsNullOrEmpty(status)) toasts.Show(status, "ok");
            lastStatus = status;
            lastBusy = busy;
        }

        TimelineData TimelineNow()
        {
            float end = Mathf.Max(left.EndTime, right.EndTime);
            float th = simT / 3600f;
            float depth = StormDepth(CurrentRp);
            var d = new TimelineData
            {
                Title = CurrentRp > 0 ? $"{CurrentRp}-year storm" + (depth > 0 ? $" · {depth:0} mm in 24 h" : "") : "No storm yet",
                Playing = playing, CanPlay = WaterShown, CanScrub = !live && end > 0, T = simT, End = end, Speed = speed,
                ReturnPeriods = returnPeriods, RpIndex = rpIdx,
            };
            float rain = end > 0 ? left.RainNow(simT, live) : 0;
            d.Text = depth <= 0 ? "Site > Site setup: use the design rainfall"
                : !WaterShown ? "Simulate > Run flood simulation, or add an NbS, to watch the storm"
                : !playing && simT <= 0 ? "Ready: press Play"
                : $"{th:0.0} h of {end / 3600f:0} · " + (rain > 0.05f ? $"rain {rain:0} mm/h" : "no rain now");
            d.Empty = depth <= 0 ? "No storm yet: Site > Site setup > Rainfall makes the design storms."
                : "The storm's rain shows here once there is water to watch (Simulate > Run flood simulation, or add an NbS).";
            if (end > 0)
            {
                const int bins = 48;
                d.Rain = new float[bins];
                for (int i = 0; i < bins; i++) d.Rain[i] = left.RainNow((i + 0.5f) * end / bins, live);
            }
            var rightLabel = right.Option == DesignScenario ? "DESIGN" : $"OPTION {CurrentOption?.ToUpper()}";
            bool single = !sideBySide;
            d.ShowLeft = left.RetainedTime != null;
            d.ShowRight = sideBySide && right.RetainedTime != null;
            d.LeftName = single && showProposed ? rightLabel : "EXISTING";
            d.LitresLeft = (single && showProposed ? right : left).LitresAt(th);
            d.RightName = rightLabel;
            d.LitresRight = right.LitresAt(th);
            return d;
        }

        StatusData StatusNow()
        {
            var d = new StatusData
            {
                Message = status, Error = status.StartsWith("Error"), Busy = busy, EngineUp = engineUp || bundle,
                Calibration = calibration.StartsWith("uncalibrated") ? "Uncalibrated" : calibration,
                ShowBudget = ui.ActiveTab == Tab.Design && designResult != null, BudgetUsedPct = budgetUsed, BudgetLimitPct = budgetLimit,
                BudgetOver = budgetUsed > budgetLimit,
            };
            if (frame != null && PointerInViewport() && PickGround(out var xy, out _))
            {
                d.X = $"{xy.x:0.00}";
                d.Y = $"{xy.y:0.00}";
                var view = !sideBySide && showProposed ? right : left;
                float z = view.Terrain.GroundAt(xy.x, xy.y);
                d.Ground = float.IsNaN(z) ? "—" : $"{z:0.00} m";
                if (WaterShown)
                {
                    float w = view.Water.DepthAt(xy.x, xy.y);
                    d.Depth = float.IsNaN(w) ? "—" : $"{w * 100:0.0} cm";
                }
            }
            return d;
        }

        void SyncOverlays()
        {
            northArrow.style.rotate = new Rotate(-rigLeft.Yaw);
            Kit.Show(cube, !rigLeft.Plan);
            Kit.Show(drawHint, !string.IsNullOrEmpty(drawHint.text));
            Kit.Show(viewLabelLeft, sideBySide);
            Kit.Show(viewLabelRight, sideBySide);
            viewLabelRight.text = right.Option == DesignScenario ? "DESIGN" : $"OPTION {CurrentOption?.ToUpper()}";
            // scale bar: about 100 points long, a round number of metres
            var cam = camLeft;
            float scale = panelSettings.scale;
            float mpp = cam.orthographic ? 2 * cam.orthographicSize / Mathf.Max(1, cam.pixelHeight)
                : 2 * rigLeft.Distance * Mathf.Tan(cam.fieldOfView * 0.5f * Mathf.Deg2Rad) / Mathf.Max(1, cam.pixelHeight);
            bool show = frame != null && mpp > 0;
            Kit.Show(scaleBar, show);
            if (show)
            {
                float want = 100 * scale * mpp, nice = 1;
                foreach (var s in new[] { 1f, 2f, 5f, 10f, 20f, 25f, 50f, 100f, 200f, 250f, 500f, 1000f }) if (s <= want) nice = s;
                scaleBar.style.width = nice / mpp / scale + 16;
                scaleLabel.text = nice >= 1000 ? $"{nice / 1000:0.#} km" : $"{nice:0} m" + (cam.orthographic ? "" : " (at the centre)");
            }
            // legend for the layer that colours the view
            if (WaterShown)
            {
                legendTitle.text = "Water depth";
                legendRamp.style.backgroundImage = waterRamp;
                legendLow.text = "1 cm";
                legendHigh.text = "30 cm +";
                Kit.Show(legend, true);
            }
            else if (rigLeft.Plan && HasGround)
            {
                legendTitle.text = "Ground level (park)";
                legendRamp.style.backgroundImage = groundRamp;
                legendLow.text = $"{left.Terrain.ParkLow:0.00} m";
                legendHigh.text = $"{left.Terrain.ParkHigh:0.00} m";
                Kit.Show(legend, true);
            }
            else Kit.Show(legend, false);
        }

        /// The scene cameras draw into the viewport's rectangle (panel points to screen pixels).
        void SyncViewRect()
        {
            var wb = ws.Viewport.worldBound;
            if (float.IsNaN(wb.width) || wb.width <= 0 || Screen.width <= 0) return;
            float s = panelSettings.scale;
            var r = new Rect(wb.x * s / Screen.width, 1 - wb.yMax * s / Screen.height, wb.width * s / Screen.width, wb.height * s / Screen.height);
            if ((r.position - viewRect.position).sqrMagnitude < 1e-8f && (r.size - viewRect.size).sqrMagnitude < 1e-8f) return;
            viewRect = r;
            ApplyViewports();
        }

        bool PointerInViewport()
        {
            if (ws == null || mainApp.style.display == DisplayStyle.None) return false;
            var m = Input.mousePosition;
            var p = RuntimePanelUtils.ScreenToPanel(doc.rootVisualElement.panel, new Vector2(m.x, Screen.height - m.y));
            var picked = doc.rootVisualElement.panel.Pick(p);
            return picked == ws.Viewport;
        }

        void EnsureLanding()
        {
            if (landing != null) return;
            BuildLanding();
            landing.style.display = DisplayStyle.None;
        }
    }
}
