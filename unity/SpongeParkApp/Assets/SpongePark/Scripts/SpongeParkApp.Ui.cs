// The app's interface in UI Toolkit, styled with the Organic / Natural tokens (Resources/UI/Organic.uss),
// the same design system as the web app. Built from code so any scene works; state lives in
// SpongeParkApp and is reflected here every frame.
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.UIElements;

namespace SpongePark
{
    public partial class SpongeParkApp
    {
        UIDocument doc;
        Label statusLabel, infoLabel, verifyLabel, videoLabel, stormTitle, stormText, litresLeft, litresRight, leftName, rightName;
        VisualElement compareBox, layerBox, litresLeftCard, litresRightCard, engineSection, projectSection, surveySection,
            targetsSection, designSection, simulateGpuRow, exportSection;
        TextField layerMapField;
        VisualElement optionChips, rpChips;
        Button playButton, liveButton, sideButton, tourButton;
        string shownComparison;
        int shownOptionsHash, shownRpHash;
        bool lastBusy;

        void BuildUi()
        {
            var panel = ScriptableObject.CreateInstance<PanelSettings>();
            panel.themeStyleSheet = Resources.Load<ThemeStyleSheet>("UI/Theme");
            panel.scaleMode = PanelScaleMode.ScaleWithScreenSize;
            panel.referenceResolution = new Vector2Int(1440, 900);
            panel.match = 0.5f;
            doc = gameObject.AddComponent<UIDocument>();
            doc.panelSettings = panel;
            var root = doc.rootVisualElement;
            root.styleSheets.Add(Resources.Load<StyleSheet>("UI/Organic"));
            root.pickingMode = PickingMode.Ignore;

            // ambient washes and paper grain, never in the way of the pointer
            root.Add(Blob(new Color(0.36f, 0.44f, 0.32f, 0.16f), -180, -180, 620));
            root.Add(Blob(new Color(0.76f, 0.55f, 0.36f, 0.14f), 1100, 420, 560));

            var app = new VisualElement { pickingMode = PickingMode.Ignore };
            mainApp = app;
            app.AddToClassList("app");
            root.Add(app);
            var sidebar = new VisualElement();
            sidebar.AddToClassList("sidebar");
            app.Add(sidebar);
            BuildSidebar(sidebar);

            var overlay = new VisualElement { pickingMode = PickingMode.Ignore };
            mainOverlay = overlay;
            overlay.AddToClassList("overlay");
            root.Add(overlay);
            BuildOverlays(overlay);

            var grain = new VisualElement { pickingMode = PickingMode.Ignore };
            grain.AddToClassList("grain");
            grain.style.backgroundImage = new StyleBackground(NoiseTexture());
            grain.style.backgroundRepeat = new BackgroundRepeat(Repeat.Repeat, Repeat.Repeat);
            grain.style.backgroundSize = new BackgroundSize(220, 220);
            root.Add(grain);

            CameraRig.BlockInput = () => Input.mousePosition.x < Screen.width * 0.3f;
        }

        void BuildSidebar(VisualElement sidebar)
        {
            var brand = Row("brand");
            var mark = new VisualElement();
            mark.AddToClassList("brand-mark");
            mark.Add(new Label("s"));
            brand.Add(mark);
            brand.Add(Text("Sponge Park", "brand-name"));
            sidebar.Add(brand);
            statusLabel = Text(status, "status");
            sidebar.Add(statusLabel);

            var scroll = new ScrollView(ScrollViewMode.Vertical) { horizontalScrollerVisibility = ScrollerVisibility.Hidden };
            scroll.style.flexGrow = 1;
            sidebar.Add(scroll);

            if (!bundle)
            {
                engineSection = Section(scroll, "Engine", "Connection");
                var r = Row();
                r.Add(Btn("Start engine", () => { launcher.Launch(); StartCoroutine(Later(4, CheckEngine())); }));
                r.Add(Btn("Check", () => StartCoroutine(CheckEngine()), "btn--ghost"));
                r.Add(Btn("Results bundle", () => StartCoroutine(OpenBundle()), "btn--outline"));
                engineSection.Add(r);

                projectSection = Section(scroll, "Project", "Open a park");
                projectSection.Add(TextInput("Project file (.sponge)", projectPath, v => projectPath = v));
                var pr = Row();
                pr.Add(Btn("Open", () => StartCoroutine(Run(OpenProject(false), "Opening"))));
                pr.Add(Btn("Create", () => StartCoroutine(Run(OpenProject(true), "Creating")), "btn--clay"));
                projectSection.Add(pr);
                infoLabel = Text("", "muted");
                projectSection.Add(infoLabel);

                surveySection = Section(scroll, "Step 1", "Survey");
                surveySection.Add(TextInput("Survey drawing (.dxf / .dwg)", drawingPath, v => drawingPath = v));
                surveySection.Add(Btn("Read layers", () => StartCoroutine(Run(InspectSurvey(), "Reading layers")), "btn--outline"));
                layerBox = new VisualElement();
                layerBox.style.display = DisplayStyle.None;
                layerBox.Add(Text("Check each layer's role, set \"confirmed\": true, then import. (The web app shows this as a table.)", "muted"));
                layerMapField = new TextField { multiline = true };
                layerMapField.AddToClassList("textarea");
                layerMapField.RegisterValueChangedCallback(e => layerMapJson = e.newValue);
                layerBox.Add(layerMapField);
                layerBox.Add(Btn("Import survey", () => StartCoroutine(Run(ImportSurvey(), "Importing"))));
                surveySection.Add(layerBox);

                targetsSection = Section(scroll, "Step 2", "Targets");
                var card = Card("card--stone");
                card.Add(SliderField("Area budget", 2, 30, budgetPct, "% of site", v => budgetPct = v));
                card.Add(SliderField("Maximum drawdown", 12, 96, maxDrawdownHr, "hours", v => maxDrawdownHr = v));
                card.Add(TextInput("Size elements for storm (yr)", designRp.ToString(), v => { if (int.TryParse(v, out var x)) designRp = x; }));
                card.Add(TextInput("Least-area target storm (yr)", targetRp.ToString(), v => { if (int.TryParse(v, out var x)) targetRp = x; }));
                card.Add(Btn("Save targets", () => StartCoroutine(Run(SetTargets(), "Saving targets"))));
                targetsSection.Add(card);

                designSection = Section(scroll, "Steps 3 and 4", "Analyse and design");
                designSection.Add(Btn("Analyse the existing site", () => StartCoroutine(Run(Baseline(), "Analysing")), "btn--wide"));
                var dr = Row();
                dr.Add(Btn("Generate", () => StartCoroutine(Run(Generate(false), "Generating")), "btn--outline"));
                dr.Add(Btn("Optimise", () => StartCoroutine(Run(Generate(true), "Optimising")), "btn--clay"));
                dr.Add(Btn("Least area", () => StartCoroutine(Run(Generate(true, "inverse"), "Optimising")), "btn--ghost"));
                designSection.Add(dr);
            }

            var cmp = Section(scroll, "Compare", "Options and storms");
            optionChips = Row();
            rpChips = Row();
            cmp.Add(optionChips);
            cmp.Add(rpChips);
            compareBox = Card();
            cmp.Add(compareBox);

            var sim = Section(scroll, "Simulate", "Watch the storm");
            sim.Add(Text("Water: 2D model, indicative. Litres: SWMM.", "muted"));
            var sr = Row();
            if (!bundle) sr.Add(Btn("Run 2D", () => StartCoroutine(Run(Simulate(), "Simulating")), "btn--outline"));
            sr.Add(Btn("Load storm", () => StartCoroutine(Run(LoadViews(), "Loading")), "btn--ghost"));
            sim.Add(sr);
            var pr2 = Row();
            playButton = Btn("Play", () => playing = !playing);
            pr2.Add(playButton);
            pr2.Add(Btn("Restart", () => { simT = 0; if (live) StartCoroutine(StartLive()); }, "btn--ghost"));
            sim.Add(pr2);
            sim.Add(SliderField("Speed", 60, 3600, speed, "sim s per s", v => speed = v));
            if (!bundle)
            {
                simulateGpuRow = Row();
                liveButton = Btn("Live GPU", () => { if (live) live = false; else StartCoroutine(StartLive()); }, "btn--outline");
                simulateGpuRow.Add(liveButton);
                simulateGpuRow.Add(Btn("Verify GPU vs engine", () => StartCoroutine(Run(VerifyGpu(), "Verifying")), "btn--ghost"));
                sim.Add(simulateGpuRow);
                verifyLabel = Text("", "notice");
                verifyLabel.style.display = DisplayStyle.None;
                sim.Add(verifyLabel);
            }

            var view = Section(scroll, "View", "Look around");
            var vr = Row();
            sideButton = Chip("Side by side", () => { sideBySide = !sideBySide; ApplyViewports(); });
            tourButton = Chip("Tour", () => rigLeft.Touring = !rigLeft.Touring);
            vr.Add(sideButton);
            vr.Add(tourButton);
            vr.Add(Chip("Existing / proposed", () => { if (!sideBySide) { showProposed = !showProposed; ApplyViewports(); } }));
            view.Add(vr);
            view.Add(SliderField("Height exaggeration", 1, 20, exaggeration, "x (on Load storm)", v => exaggeration = v));

            exportSection = Section(scroll, "Deliverables", "Export");
            exportSection.Add(TextInput("Folder", exportDir, v => exportDir = v));
            if (!bundle)
            {
                exportSection.Add(Btn("Report, drawings and Rhino file", () => StartCoroutine(Run(api.RunJob("POST", api.P($"/options/{CurrentOption}/export"),
                    new { out_dir = exportDir }, r => status = r != null ? "Exported to " + exportDir : status), "Exporting")), "btn--wide"));
                exportSection.Add(Btn("Web viewer bundle", () => StartCoroutine(Run(api.RunJob("POST", api.P("/viewer-bundle"),
                    new { out_dir = Path.Combine(exportDir, "bundle") }, r => status = "Bundle written"), "Bundling")), "btn--outline"));
            }
            exportSection.Add(Btn("Record video of the storm", () =>
            {
                if (video.Recording) return;
                simT = 0; playing = true; rigLeft.Touring = true;
                video.Begin(Path.Combine(exportDir, "video"));
            }, "btn--clay"));
            videoLabel = Text("", "muted");
            exportSection.Add(videoLabel);
        }

        void BuildOverlays(VisualElement overlay)
        {
            var pill = new VisualElement { pickingMode = PickingMode.Ignore };
            pill.AddToClassList("pill");
            pill.style.left = Length.Percent(30.5f);
            pill.style.top = 24;
            stormTitle = Text("", "pill-title");
            stormText = Text("", "pill-text");
            pill.Add(stormTitle);
            pill.Add(stormText);
            overlay.Add(pill);

            litresLeftCard = LitresCard(overlay, 30.5f, out leftName, out litresLeft);
            litresRightCard = LitresCard(overlay, 65.5f, out rightName, out litresRight);

            var foot = Text("Water animation: 2D model, indicative. Volumes and litres: SWMM.", "footnote");
            foot.style.left = Length.Percent(30.5f);
            overlay.Add(foot);
        }

        VisualElement LitresCard(VisualElement parent, float leftPct, out Label name, out Label value)
        {
            var card = new VisualElement { pickingMode = PickingMode.Ignore };
            card.AddToClassList("litres");
            card.style.left = Length.Percent(leftPct);
            card.style.bottom = 36;
            name = Text("", "litres-label");
            card.Add(name);
            var r = Row();
            r.style.alignItems = Align.FlexEnd;
            value = Text("0", "litres-value");
            r.Add(value);
            r.Add(Text("litres kept", "litres-unit"));
            card.Add(r);
            parent.Add(card);
            return card;
        }

        // ------------------------------------------------------------ every frame
        void LateUpdate()
        {
            if (doc == null) return;
            AnimateLanding();
            statusLabel.text = status;
            statusLabel.EnableInClassList("status--error", status.StartsWith("Error"));
            if (busy != lastBusy)
            {
                lastBusy = busy;
                doc.rootVisualElement.Query<Button>().ForEach(b => { if (b != playButton) b.SetEnabled(!busy); });
            }
            if (infoLabel != null)
                infoLabel.text = info == null ? "" :
                    $"{info["name"]}: ground model {Yes(info["has_terrain"])}, existing site analysed {Yes(info["has_baseline"])}, {info["unconfirmed_parameters"]} defaults to confirm.";
            if (layerBox != null && !string.IsNullOrEmpty(layerMapJson) && layerBox.style.display == DisplayStyle.None)
            {
                layerBox.style.display = DisplayStyle.Flex;
                layerMapField.SetValueWithoutNotify(layerMapJson);
            }
            SyncChips();
            SyncComparison();
            if (verifyLabel != null && !string.IsNullOrEmpty(verify))
            {
                verifyLabel.style.display = DisplayStyle.Flex;
                verifyLabel.text = verify;
                verifyLabel.EnableInClassList("notice--warn", !verify.StartsWith("PASS"));
            }
            playButton.text = playing ? "Pause" : "Play";
            if (liveButton != null) liveButton.text = live ? "Live GPU: on" : "Live GPU";
            sideButton.EnableInClassList("chip--on", sideBySide);
            tourButton.EnableInClassList("chip--on", rigLeft.Touring);
            videoLabel.text = video.Result;

            float th = simT / 3600f;
            stormTitle.text = CurrentRp > 0 ? $"{CurrentRp}-year storm" : "No storm loaded";
            float rain = left.RainAt(th);
            stormText.text = $"{th:0.0} h · " + (rain > 0.05f ? $"rain {rain:0} mm/h" : "no rain");
            litresLeftCard.style.display = left.RetainedTime != null ? DisplayStyle.Flex : DisplayStyle.None;
            litresRightCard.style.display = sideBySide && right.RetainedTime != null ? DisplayStyle.Flex : DisplayStyle.None;
            var single = !sideBySide;
            leftName.text = single && showProposed ? $"PROPOSED · {CurrentOption?.ToUpper()}" : "EXISTING";
            litresLeft.text = (single && showProposed ? right : left).LitresAt(th).ToString("N0");
            rightName.text = $"PROPOSED · {CurrentOption?.ToUpper()}";
            litresRight.text = right.LitresAt(th).ToString("N0");
        }

        void SyncChips()
        {
            int oh = string.Join(",", options).GetHashCode() ^ optionIdx;
            if (oh != shownOptionsHash)
            {
                shownOptionsHash = oh;
                optionChips.Clear();
                for (int i = 0; i < options.Count; i++)
                {
                    int k = i;
                    var c = Chip(options[i] == "baseline" ? "existing" : options[i], () => { optionIdx = k; StartCoroutine(LoadComparison()); });
                    c.EnableInClassList("chip--on", i == optionIdx);
                    optionChips.Add(c);
                }
            }
            int rh = string.Join(",", returnPeriods).GetHashCode() ^ (rpIdx * 7919);
            if (rh != shownRpHash)
            {
                shownRpHash = rh;
                rpChips.Clear();
                for (int i = 0; i < returnPeriods.Count; i++)
                {
                    int k = i;
                    var c = Chip($"{returnPeriods[i]}-yr", () => rpIdx = k);
                    c.EnableInClassList("chip--on", i == rpIdx);
                    rpChips.Add(c);
                }
            }
        }

        void SyncComparison()
        {
            var key = comparison?.ToString(Newtonsoft.Json.Formatting.None) ?? "";
            if (key == shownComparison) return;
            shownComparison = key;
            compareBox.Clear();
            if (comparison == null)
            {
                compareBox.Add(Text("Choose an option that has been run.", "muted"));
                return;
            }
            var ds = comparison["design_retention_storm_yr"];
            compareBox.Add(Text("Largest storm fully retained", "muted"));
            compareBox.Add(Text(ds == null || ds.Type == JTokenType.Null ? "none" : $"{ds}-year", "stat-value"));
            foreach (var row in comparison["rows"])
            {
                var r = new VisualElement();
                r.AddToClassList("result-row");
                r.Add(Text($"{row["return_period_yr"]}-year", "strong"));
                var peak = row["peak_reduction_pct"].Type == JTokenType.Null ? 0f : (float)row["peak_reduction_pct"];
                r.Add(Text($"kept {(float)row["baseline_retained_pct"]:0} → {(float)row["option_retained_pct"]:0} %   peak −{peak:0} %"));
                compareBox.Add(r);
            }
        }

        static string Yes(JToken t) => t != null && (bool)t ? "ready" : "not yet";

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

        static VisualElement Section(VisualElement parent, string eyebrow, string title)
        {
            var s = new VisualElement();
            s.AddToClassList("section");
            s.Add(Text(eyebrow.ToUpper(), "eyebrow"));
            s.Add(Text(title, "h2"));
            parent.Add(s);
            return s;
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

        static VisualElement Blob(Color c, float x, float y, float size)
        {
            var b = new VisualElement { pickingMode = PickingMode.Ignore };
            b.AddToClassList("blob");
            b.style.left = x; b.style.top = y; b.style.width = size; b.style.height = size * 0.85f;
            b.style.backgroundImage = new StyleBackground(SoftDisc(c));
            return b;
        }

        static Texture2D SoftDisc(Color c)
        {
            const int n = 128;
            var t = new Texture2D(n, n, TextureFormat.RGBA32, false) { wrapMode = TextureWrapMode.Clamp };
            for (int y = 0; y < n; y++)
            for (int x = 0; x < n; x++)
            {
                float dx = (x - n / 2f) / (n / 2f), dy = (y - n / 2f) / (n / 2f);
                float d = Mathf.Sqrt(dx * dx + dy * dy);
                t.SetPixel(x, y, new Color(c.r, c.g, c.b, c.a * Mathf.SmoothStep(1, 0, d)));
            }
            t.Apply();
            return t;
        }

        static Texture2D NoiseTexture()
        {
            const int n = 220;
            var t = new Texture2D(n, n, TextureFormat.RGBA32, false) { wrapMode = TextureWrapMode.Repeat, filterMode = FilterMode.Point };
            var rnd = new System.Random(7);
            var px = new Color32[n * n];
            for (int i = 0; i < px.Length; i++)
            {
                byte v = (byte)rnd.Next(0, 90);
                px[i] = new Color32(v, v, (byte)(v * 0.9f), (byte)rnd.Next(80, 255));
            }
            t.SetPixels32(px);
            t.Apply();
            return t;
        }
    }
}
