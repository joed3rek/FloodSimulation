// Opening screen and survey intake, the same flow as the web app:
// landing (Import a survey) -> intake (questions with the layer highlighted, every link editable)
// -> Clean and build -> the main view with the new project open.
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
        VisualElement mainApp, mainOverlay, landing, intakeView, browser;
        VisualElement contourArt, rainArt;
        Label landingStatus, engineChip;
        JToken intake;
        readonly Dictionary<string, string> links = new Dictionary<string, string>();   // layer -> SP name ("" = not needed)
        PlanView plan;
        VisualElement intakePanel;
        Button panelOpen;
        Label focusCaption, answeredLabel, intakeStatus;
        Button buildButton;
        string intakeProjectPath = "", intakeArea = "";
        bool intakeContours = true;
        const string RecentKey = "spongepark.recent";
        float nextEngineCheck;

        // ------------------------------------------------------------ screens
        void ShowMain()
        {
            if (landing != null) landing.style.display = DisplayStyle.None;
            if (intakeView != null) intakeView.style.display = DisplayStyle.None;
            mainApp.style.display = DisplayStyle.Flex;
            mainOverlay.style.display = DisplayStyle.Flex;
            SetScene(true);
        }

        void SetScene(bool on)
        {
            camLeft.enabled = on;
            camRight.enabled = on && sideBySide;
        }

        void ShowLanding()
        {
            mainApp.style.display = DisplayStyle.None;
            mainOverlay.style.display = DisplayStyle.None;
            if (intakeView != null) intakeView.style.display = DisplayStyle.None;
            SetScene(false);
            if (landing == null) BuildLanding();
            landing.style.display = DisplayStyle.Flex;
        }

        // ------------------------------------------------------------ landing
        void BuildLanding()
        {
            var root = doc.rootVisualElement;
            landing = new VisualElement();
            landing.AddToClassList("landing");
            root.Insert(root.IndexOf(mainApp), landing);

            var glowA = Blob(new Color(0.36f, 0.44f, 0.32f, 0.45f), -260, -260, 820);
            var glowB = Blob(new Color(0.76f, 0.55f, 0.36f, 0.32f), 1000, 520, 760);
            landing.Add(glowA);
            landing.Add(glowB);
            contourArt = new VisualElement { pickingMode = PickingMode.Ignore };
            contourArt.AddToClassList("contour-art");
            contourArt.generateVisualContent += DrawContours;
            landing.Add(contourArt);
            rainArt = new VisualElement { pickingMode = PickingMode.Ignore };
            rainArt.AddToClassList("rain-art");
            rainArt.generateVisualContent += DrawRain;
            landing.Add(rainArt);

            var nav = Row("landing-nav");
            var brand = Row("brand");
            var mark = new VisualElement();
            mark.AddToClassList("brand-mark");
            mark.Add(new Label("s"));
            brand.Add(mark);
            brand.Add(Text("Sponge Park.", "landing-brand"));
            nav.Add(brand);
            var spacer = new VisualElement();
            spacer.style.flexGrow = 1;
            nav.Add(spacer);
            engineChip = Text("checking the engine…", "engine-chip");
            nav.Add(engineChip);
            nav.Add(Btn("Start engine", () => { launcher.Launch(); StartCoroutine(Later(4, CheckEngine())); }, "btn--light"));
            landing.Add(nav);

            var hero = new VisualElement();
            hero.AddToClassList("hero");
            hero.Add(Text("Every park can", "hero-title"));
            hero.Add(Text("hold the rain.", "hero-title", "hero-accent"));
            hero.Add(Text("Start with the surveyor's drawing. The engine sorts out its layers, asks you about the ones it is not sure of, and builds the ground the water will move over.", "hero-text"));

            // two ways in: start a new project from a survey, or open a .sponge project
            var choices = Row("choice-row");
            choices.Add(ChoiceCard("+", "New project", "Choose the site survey (DXF)",
                () => PickFile("Choose the site survey (DXF)", "Site survey", "dxf,dwg", p => StartCoroutine(StartIntake(p))), true));
            choices.Add(ChoiceCard("◆", "Open a project", "A .sponge file you saved before",
                () => PickFile("Open a Sponge Park project", "Sponge Park project", "sponge", p => StartCoroutine(OpenExisting(p))), false));
            hero.Add(choices);

            hero.Add(Text("OR PASTE A PATH (.DXF OR .SPONGE)", "hero-small"));
            var pathRow = Row("path-row");
            var pathField = new TextField { value = PlayerPrefs.GetString("spongepark.lastsurvey", "") };
            pathField.AddToClassList("input");
            pathField.AddToClassList("path-input");
            pathRow.Add(pathField);
            pathRow.Add(Btn("Go", () =>
            {
                var path = pathField.value.Trim('"', ' ');
                if (path.EndsWith(".sponge", System.StringComparison.OrdinalIgnoreCase)) StartCoroutine(OpenExisting(path));
                else StartCoroutine(StartIntake(path));
            }, "btn--light"));
            hero.Add(pathRow);
            landingStatus = Text("", "hero-status");
            hero.Add(landingStatus);

            var recent = Recent();
            if (recent.Count > 0)
            {
                hero.Add(Text("RECENT PROJECTS", "hero-small"));
                var list = Row("recent-row");
                foreach (var r in recent.Where(x => x.EndsWith(".sponge", System.StringComparison.OrdinalIgnoreCase)).Take(4))
                {
                    var path = r;
                    var b = Btn(System.IO.Path.GetFileNameWithoutExtension(r), () => StartCoroutine(OpenExisting(path)), "btn--recent");
                    b.tooltip = r;
                    list.Add(b);
                }
                hero.Add(list);
            }
            landing.Add(hero);
            landing.Add(Text("SPONGE PARK.", "wordmark"));
        }

        VisualElement ChoiceCard(string glyph, string title, string text, System.Action onClick, bool primary)
        {
            var card = new Button(onClick);
            card.AddToClassList("drop");
            card.AddToClassList(primary ? "drop--new" : "drop--open");
            var icon = new VisualElement();
            icon.AddToClassList("drop-icon");
            if (!primary) icon.AddToClassList("drop-icon--clay");
            icon.Add(Text(glyph, "drop-arrow"));
            card.Add(icon);
            card.Add(Text(title, "drop-title"));
            card.Add(Text(text, "drop-text"));
            return card;
        }

        void DrawContours(MeshGenerationContext ctx)
        {
            var p = ctx.painter2D;
            var c = new Color(0.90f, 0.86f, 0.80f);
            float w = contourArt.contentRect.width, h = contourArt.contentRect.height, cx = w / 2, cy = h / 2;
            for (int i = 0; i < 9; i++)
            {
                float r = (0.1f + i * 0.048f) * Mathf.Min(w, h), k = 0.08f + i * 0.01f;
                p.strokeColor = new Color(c.r, c.g, c.b, 0.5f - i * 0.045f);
                p.lineWidth = i % 3 == 0 ? 1.6f : 0.8f;
                p.BeginPath();
                for (int j = 0; j <= 12; j++)
                {
                    float a = j / 12f * Mathf.PI * 2;
                    float rr = r * (1 + k * Mathf.Sin(3 * a + i * 0.9f) + 0.05f * Mathf.Cos(5 * a - i));
                    var pt = new Vector2(cx + rr * Mathf.Cos(a), cy + rr * Mathf.Sin(a));
                    if (j == 0) p.MoveTo(pt); else p.LineTo(pt);
                }
                p.ClosePath();
                p.Stroke();
            }
        }

        void DrawRain(MeshGenerationContext ctx)
        {
            var p = ctx.painter2D;
            float w = rainArt.contentRect.width, h = rainArt.contentRect.height;
            p.strokeColor = new Color(0.90f, 0.86f, 0.80f, 0.6f);
            p.lineWidth = 2;
            p.BeginPath();
            p.MoveTo(new Vector2(0, h * 0.55f));
            p.BezierCurveTo(new Vector2(w * 0.25f, h * 0.5f), new Vector2(w * 0.3f, h * 0.85f), new Vector2(w * 0.5f, h * 0.85f));
            p.BezierCurveTo(new Vector2(w * 0.7f, h * 0.85f), new Vector2(w * 0.78f, h * 0.52f), new Vector2(w, h * 0.58f));
            p.Stroke();
            p.fillColor = new Color(0.29f, 0.49f, 0.59f, 0.8f);
            p.BeginPath();
            p.MoveTo(new Vector2(w * 0.27f, h * 0.68f));
            p.BezierCurveTo(new Vector2(w * 0.36f, h * 0.83f), new Vector2(w * 0.64f, h * 0.83f), new Vector2(w * 0.73f, h * 0.68f));
            p.BezierCurveTo(new Vector2(w * 0.62f, h * 0.74f), new Vector2(w * 0.38f, h * 0.74f), new Vector2(w * 0.27f, h * 0.68f));
            p.Fill();
            p.strokeColor = new Color(0.95f, 0.96f, 0.94f, 0.45f);
            for (int i = 0; i < 6; i++)
            {
                p.BeginPath();
                float x = w * (0.3f + i * 0.08f), y = h * (0.1f + (i % 3) * 0.07f);
                p.MoveTo(new Vector2(x, y));
                p.LineTo(new Vector2(x - 8, y + 34));
                p.Stroke();
            }
        }

        void AnimateLanding()
        {
            if (landing == null || landing.style.display == DisplayStyle.None) return;
            float t = Time.unscaledTime;
            if (t > nextEngineCheck) { nextEngineCheck = t + 5; StartCoroutine(CheckEngine()); }   // notice a (re)started engine
            contourArt.style.translate = new Translate(0, 22 * Mathf.Sin(t * 2 * Mathf.PI / 12f));
            contourArt.style.rotate = new Rotate(2 * Mathf.Sin(t * 2 * Mathf.PI / 12f));
            rainArt.style.translate = new Translate(0, -20 * Mathf.Sin(t * 2 * Mathf.PI / 14f));
            bool ok = engineUp && api.Current;
            engineChip.text = !engineUp ? "engine not running" : ok ? "engine connected" : "engine out of date: restart spongepark serve";
            engineChip.EnableInClassList("engine-chip--off", !ok);
        }

        static List<string> Recent()
        {
            var s = PlayerPrefs.GetString(RecentKey, "");
            return s.Split('|').Where(x => x.Length > 0).ToList();
        }

        static void Remember(string path)
        {
            var r = Recent();
            r.Remove(path);
            r.Insert(0, path);
            PlayerPrefs.SetString(RecentKey, string.Join("|", r.Take(6)));
        }

        IEnumerator OpenExisting(string path)
        {
            projectPath = path;
            landingStatus.text = "Opening…";
            yield return OpenProject(false);
            if (info == null) { landingStatus.text = "Could not open: " + api.LastError; yield break; }
            Remember(path);
            ShowMain();
        }

        // ------------------------------------------------------------ file browser (the engine lists folders)
        /// The Windows file-open dialog; the in-app browser where the system dialog is not available.
        void PickFile(string title, string label, string extensions, System.Action<string> pick)
        {
            if (!engineUp) { landingStatus.text = "Start the engine first (button at the top)."; return; }
            if (!api.Current)
            {
                landingStatus.text = "The running engine is older than this app. In its window press Ctrl+C, run spongepark serve again, then try again.";
                return;
            }
            if (!NativeFileDialog.Supported)
            {
                OpenBrowser(title, string.Join(",", extensions.Split(',').Select(e => "." + e)), pick);
                return;
            }
            var path = NativeFileDialog.Open(title, label, extensions, PlayerPrefs.GetString("spongepark.lastdir", ""));
            if (string.IsNullOrEmpty(path)) return;   // cancelled
            PlayerPrefs.SetString("spongepark.lastdir", System.IO.Path.GetDirectoryName(path));
            pick(path);
        }

        string browserExt = ".dxf,.dwg";
        System.Action<string> browserPick;

        void OpenBrowser(string title, string ext, System.Action<string> pick)
        {
            if (!engineUp) { landingStatus.text = "Start the engine first (button at the top)."; return; }
            if (!api.Current)
            {
                landingStatus.text = "The running engine is older than this app. In its window press Ctrl+C, run spongepark serve again, then click Check or try again.";
                StartCoroutine(CheckEngine());
                return;
            }
            browserExt = ext;
            browserPick = pick;
            browser?.RemoveFromHierarchy();
            browser = new VisualElement();
            browser.AddToClassList("modal-back");
            var box = new VisualElement();
            box.AddToClassList("modal");
            browser.Add(box);
            box.Add(Text(title, "h2"));
            var where = Text("", "muted");
            box.Add(where);
            var list = new ScrollView { horizontalScrollerVisibility = ScrollerVisibility.Hidden };
            list.AddToClassList("modal-list");
            box.Add(list);
            var row = Row();
            row.Add(Btn("Up one folder", () => StartCoroutine(ListDir(where, list, "..")), "btn--ghost"));
            row.Add(Btn("Cancel", () => browser.RemoveFromHierarchy(), "btn--outline"));
            box.Add(row);
            doc.rootVisualElement.Add(browser);
            StartCoroutine(ListDir(where, list, PlayerPrefs.GetString("spongepark.lastdir", "")));
        }

        string browserDir = "", browserParent = "";

        IEnumerator ListDir(Label where, ScrollView list, string dir)
        {
            if (dir == "..") dir = browserParent;
            JToken r = null;
            var q = "/fs/list?ext=" + browserExt + (string.IsNullOrEmpty(dir) ? "" : "&dir=" + UnityEngine.Networking.UnityWebRequest.EscapeURL(dir));
            yield return api.Get(q, x => r = x);
            if (r == null) { where.text = api.LastError; yield break; }
            browserDir = (string)r["dir"];
            browserParent = (string)r["parent"];
            PlayerPrefs.SetString("spongepark.lastdir", browserDir);
            where.text = browserDir;
            list.Clear();
            foreach (var it in r["items"])
            {
                var path = (string)it["path"];
                bool folder = (string)it["kind"] == "folder";
                var b = new Button(() =>
                {
                    if (folder) StartCoroutine(ListDir(where, list, path));
                    else { browser.RemoveFromHierarchy(); browserPick?.Invoke(path); }
                }) { text = (folder ? "▸  " : "◆  ") + (string)it["name"] };
                b.AddToClassList("file-item");
                if (!folder) b.AddToClassList("file-item--file");
                list.Add(b);
            }
            if (!r["items"].Any()) list.Add(Text("Nothing here: no folders or matching files.", "muted"));
        }

        // ------------------------------------------------------------ intake
        IEnumerator StartIntake(string path)
        {
            if (string.IsNullOrEmpty(path)) yield break;
            landingStatus.text = "Reading " + System.IO.Path.GetFileName(path) + "…";
            JToken r = null;
            yield return api.Send("POST", "/intake/start", new { path }, x => r = x, 600);
            if (r == null)
            {
                landingStatus.text = api.LastError.Contains("404")
                    ? "The running engine is older than this app: restart spongepark serve, then try again."
                    : "Could not read the drawing: " + api.LastError;
                yield break;
            }
            PlayerPrefs.SetString("spongepark.lastsurvey", path);
            landingStatus.text = "";
            intake = r;
            links.Clear();
            foreach (var l in r["layers"])
                if (l["question"] == null || l["question"].Type == JTokenType.Null) links[(string)l["layer"]] = (string)l["proposed"];
            intakeProjectPath = System.Text.RegularExpressions.Regex.Replace((string)r["survey"], @"\.(dxf|dwg)$", "", System.Text.RegularExpressions.RegexOptions.IgnoreCase).Replace(' ', '_') + ".sponge";
            BuildIntake();
            landing.style.display = DisplayStyle.None;
            intakeView.style.display = DisplayStyle.Flex;
        }

        List<JToken> Choices => intake["choices"].ToList();

        string TitleOf(string name) => Choices.FirstOrDefault(c => (string)c["name"] == name)?["title"]?.ToString() ?? "Not needed";

        static string Contents(JToken l)
        {
            var parts = ((JObject)l["entities"]).Properties().Select(p => $"{p.Value} {p.Name.ToLower()}{((int)p.Value > 1 ? "s" : "")}").ToList();
            if (l["level_range"] != null && l["level_range"].Type != JTokenType.Null) parts.Add($"numbers {l["level_range"][0]}–{l["level_range"][1]}");
            return string.Join(" · ", parts);
        }

        void BuildIntake()
        {
            intakeView?.RemoveFromHierarchy();
            intakeView = new VisualElement();
            intakeView.AddToClassList("intake");
            doc.rootVisualElement.Insert(doc.rootVisualElement.IndexOf(mainApp), intakeView);

            // the plan fills the screen; the questions sit in a panel on the left that slides away
            plan = new PlanView();
            plan.Clicked += () => SetPanel(false);
            intakeView.Add(plan);
            focusCaption = Text("The whole drawing · loading the linework…", "plan-caption");
            intakeView.Add(focusCaption);
            var tools = new VisualElement();
            tools.AddToClassList("plan-tools");
            var zin = Btn("+", () => plan.ZoomBy(1.4f), "plan-btn");
            zin.tooltip = "Zoom in (or scroll)";
            var zout = Btn("−", () => plan.ZoomBy(1 / 1.4f), "plan-btn");
            zout.tooltip = "Zoom out (or scroll)";
            var fit = Btn("Fit", () => plan.ZoomExtents(), "plan-btn plan-btn--fit");
            fit.tooltip = "Zoom to the whole plan";
            tools.Add(zin);
            tools.Add(zout);
            tools.Add(fit);
            intakeView.Add(tools);
            intakeView.Add(Text("Scroll to zoom · drag to move · click the plan to hide the questions", "plan-hint"));
            panelOpen = Btn("Questions ›", () => SetPanel(true), "plan-open");
            intakeView.Add(panelOpen);

            intakePanel = new VisualElement();
            intakePanel.AddToClassList("intake-panel");
            intakeView.Add(intakePanel);
            var left = new ScrollView { horizontalScrollerVisibility = ScrollerVisibility.Hidden };
            left.AddToClassList("intake-scroll");
            intakePanel.Add(left);

            var layers = intake["layers"].ToList();
            var questions = layers.Where(l => l["question"] != null && l["question"].Type != JTokenType.Null).ToList();
            var linked = layers.Where(l => l["question"] == null || l["question"].Type == JTokenType.Null).ToList();

            var top = Row("panel-top");
            top.Add(Btn("← Back", () => { intakeView.style.display = DisplayStyle.None; landing.style.display = DisplayStyle.Flex; }, "btn--ghost btn--back"));
            top.Add(Btn("‹ Hide", () => SetPanel(false), "btn--ghost btn--back"));
            left.Add(top);
            left.Add(Text("SURVEY INTAKE", "eyebrow"));
            left.Add(Text((string)intake["name"], "page-title"));
            left.Add(Text($"The engine read {layers.Count} layers. It linked {linked.Count} of them on its own" +
                          (questions.Count > 0 ? $" and has {questions.Count} question{(questions.Count > 1 ? "s" : "")} for you." : ".") +
                          " Your file is not changed: a cleaned copy is written next to it.", "lead"));

            if (questions.Count > 0)
            {
                var qh = Row("q-head");
                qh.Add(Text("What is on these layers?", "h2"));
                answeredLabel = Text("", "badge");
                qh.Add(answeredLabel);
                left.Add(qh);
                int i = 0;
                foreach (var q in questions) left.Add(QuestionCard(q, i++));
            }

            left.Add(Text("Linked by the engine", "h2"));
            left.Add(Text("Point at a layer to see it in clay on the plan; Show zooms to it. Change any link that is wrong.", "muted"));
            var listBox = new VisualElement();
            listBox.AddToClassList("link-list");
            foreach (var l in linked) listBox.Add(LinkRow(l));
            left.Add(listBox);

            var fin = Card("card--sand");
            fin.Add(Text("DONE", "eyebrow"));
            fin.Add(Text("Clean the drawing and build the ground", "h2"));
            fin.Add(TextInput("Save the project as", intakeProjectPath, v => intakeProjectPath = v));
            fin.Add(TextInput("Park area (m²), optional", "", v => intakeArea = v));
            var contours = Chip("Use contours in the ground model", null);
            contours.clicked += () => { intakeContours = !intakeContours; contours.EnableInClassList("chip--on", intakeContours); };
            contours.EnableInClassList("chip--on", true);
            fin.Add(contours);
            buildButton = Btn("Clean and build", () => StartCoroutine(FinishIntake()), "btn--wide");
            fin.Add(buildButton);
            intakeStatus = Text("", "muted");
            fin.Add(intakeStatus);
            left.Add(fin);
            SetPanel(true);
            UpdateIntakeState();
            focused = "\u0000";
            StartCoroutine(LoadPlan());
        }

        const float PanelWidth = 500;   // .intake-panel width plus its left margin

        void SetPanel(bool open)
        {
            intakePanel.EnableInClassList("intake-panel--closed", !open);
            panelOpen.style.display = open ? DisplayStyle.None : DisplayStyle.Flex;
            plan.LeftInset = open ? PanelWidth : 0;
        }

        IEnumerator LoadPlan()
        {
            JToken geo = null;
            yield return api.Get("/intake/geometry?path=" + UnityEngine.Networking.UnityWebRequest.EscapeURL((string)intake["survey"]), x => geo = x, 300);
            if (geo == null)
            {
                focusCaption.text = api.LastError.Contains("404")
                    ? "The running engine is older than this app: restart spongepark serve to see the plan."
                    : "Could not draw the plan: " + api.LastError;
                yield break;
            }
            plan.SetGeometry(geo);
            focusCaption.text = "The whole drawing";
        }

        VisualElement QuestionCard(JToken q, int index)
        {
            var layer = (string)q["layer"];
            var question = q["question"];
            var card = Card(index % 2 == 0 ? null : "card--alt");
            card.AddToClassList("q-card");
            var head = Row("q-card-head");
            var nm = new VisualElement();
            nm.style.flexGrow = 1;
            nm.style.flexShrink = 1;
            nm.Add(Text("LAYER · HIGHLIGHTED IN CLAY", "eyebrow"));
            nm.Add(Text(layer, "mono"));
            head.Add(nm);
            head.Add(ShowButton(layer));
            card.Add(head);
            card.Add(Text(Contents(q), "muted"));
            card.Add(Text((string)question["ask"], "q-ask"));

            var quick = new List<(string name, string title)>();
            var kind = (string)question["kind"];
            if (kind == "unclear") quick.AddRange(question["answers"].Select(a => ((string)a["name"], (string)a["title"])));
            else if (kind == "confirm") { quick.Add(((string)q["proposed"], "Yes, " + TitleOf((string)q["proposed"]).ToLower())); quick.Add(("", "No, leave it out")); }
            else quick.Add(("", "Not needed"));

            var chips = Row();
            var all = new List<(Button b, string name)>();
            DropdownField dd = null;
            void Pick(string name)
            {
                links[layer] = name;
                foreach (var (b, n) in all) b.EnableInClassList("chip--on", n == name);
                card.EnableInClassList("q-card--done", true);
                if (dd != null && quick.Any(x => x.name == name)) dd.SetValueWithoutNotify("Something else…");
                UpdateIntakeState();
                focused = "\u0000";
                Focus(layer);
            }
            foreach (var (name, title) in quick)
            {
                var n = name;
                var b = Chip(title, () => Pick(n));
                all.Add((b, n));
                chips.Add(b);
            }
            card.Add(chips);
            var titles = new List<string> { "Something else…" };
            titles.AddRange(Choices.Select(c => (string)c["title"]));
            dd = new DropdownField(titles, 0);
            dd.AddToClassList("input");
            dd.RegisterValueChangedCallback(e =>
            {
                var c = Choices.FirstOrDefault(x => (string)x["title"] == e.newValue);
                if (c != null) Pick((string)c["name"]);
            });
            card.Add(dd);
            card.RegisterCallback<PointerEnterEvent>(_ => Focus(layer));
            return card;
        }

        VisualElement LinkRow(JToken l)
        {
            var layer = (string)l["layer"];
            var row = new VisualElement();
            row.AddToClassList("link-row");
            var names = new VisualElement();
            names.style.flexGrow = 1;
            names.style.flexShrink = 1;
            names.Add(Text(layer, "mono"));
            names.Add(Text(Contents(l), "muted"));
            row.Add(names);
            row.Add(ShowButton(layer));
            var titles = Choices.Select(c => (string)c["title"]).ToList();
            var dd = new DropdownField(titles, Mathf.Max(0, titles.IndexOf(TitleOf(links[layer]))));
            dd.AddToClassList("input");
            dd.AddToClassList("link-dropdown");
            dd.RegisterValueChangedCallback(e =>
            {
                var c = Choices.FirstOrDefault(x => (string)x["title"] == e.newValue);
                if (c != null) { links[layer] = (string)c["name"]; UpdateIntakeState(); focused = "\u0000"; Focus(layer); }
            });
            row.Add(dd);
            row.RegisterCallback<PointerEnterEvent>(_ => Focus(layer));
            return row;
        }

        string focused = "\u0000";

        Button ShowButton(string layer)
        {
            var b = Btn("Show", () => { Focus(layer); plan.ZoomToLayer(layer); }, "btn--ghost btn--show");
            b.tooltip = "Zoom the plan to this layer";
            return b;
        }

        /// Highlights a layer on the plan (null: none) and names it in the caption.
        void Focus(string layer)
        {
            if (layer == focused) return;
            focused = layer;
            focusCaption.text = layer == null ? "The whole drawing" : $"Highlighted: {layer}  →  {(links.TryGetValue(layer, out var n) ? TitleOf(n) : "not answered yet")}";
            plan.Highlight(layer);
        }

        void UpdateIntakeState()
        {
            var questions = intake["layers"].Where(l => l["question"] != null && l["question"].Type != JTokenType.Null).Select(l => (string)l["layer"]).ToList();
            int answered = questions.Count(links.ContainsKey);
            if (answeredLabel != null) answeredLabel.text = $"{answered} of {questions.Count} answered";
            bool levels = links.Values.Any(v => v == "SP-LVL-SPOT" || v == "SP-CONT-MAJOR" || v == "SP-CONT-MINOR");
            bool ready = answered == questions.Count && levels;
            buildButton.SetEnabled(ready);
            intakeStatus.text = !levels ? "Link at least the spot levels or the contours: the ground is built from them."
                : answered < questions.Count ? $"Answer the {questions.Count - answered} remaining question{(questions.Count - answered > 1 ? "s" : "")} first." : "";
        }

        IEnumerator FinishIntake()
        {
            buildButton.SetEnabled(false);
            intakeStatus.text = "Cleaning the drawing and building the ground…";
            float.TryParse(intakeArea, out var area);
            var body = new Dictionary<string, object>
            {
                ["survey"] = (string)intake["survey"], ["links"] = links, ["project_path"] = intakeProjectPath,
                ["contours_in_surface"] = intakeContours,
            };
            if (area > 0) body["park_area_m2"] = area;
            JToken r = null;
            yield return api.RunJob("POST", "/intake/finish", body, x => r = x, s => intakeStatus.text = "Cleaning the drawing and building the ground… " + s);
            if (r == null) { intakeStatus.text = "The engine reported a problem: " + api.LastError; buildButton.SetEnabled(true); yield break; }
            var qc = r["qc"]?["spot_cross_validation"];
            status = $"Ground model built. {r["cleaning"]["duplicates_removed_total"]} duplicate objects removed" +
                     (qc != null && qc.Type != JTokenType.Null ? $"; spot levels agree to {(float)qc["rmse_m"]:0.000} m." : ".");
            projectPath = (string)r["project"];
            yield return OpenProject(false);
            Remember(projectPath);
            ShowMain();
        }
    }
}
