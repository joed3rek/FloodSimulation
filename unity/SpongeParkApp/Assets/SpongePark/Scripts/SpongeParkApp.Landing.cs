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
        bool engineLaunched;   // the landing starts the engine itself, once
        Label landingStatus;
        JToken intake;
        readonly Dictionary<string, string> links = new Dictionary<string, string>();   // layer -> SP name ("" = not needed)
        PlanView plan;
        VisualElement intakePanel;
        Button panelOpen;
        Label focusCaption, answeredLabel, intakeStatus;
        Button buildButton;
        string intakeProjectPath = "", intakeArea = "";
        bool intakeContours;   // false: the engine decides whether the drawn contours shape the ground
        const string RecentKey = "spongepark.recent";          // before: paths joined with '|' (read once, then replaced)
        const string RecentListKey = "spongepark.recent.v2";   // JSON [{path, name, opened (unix seconds)}]
        const int RecentKeep = 20;
        ScrollView recentList;
        Button recentClear;
        float nextEngineCheck;

        // ------------------------------------------------------------ screens
        void ShowMain()
        {
            Debug.Log("screen: workspace");
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
            Debug.Log("screen: start");
            mainApp.style.display = DisplayStyle.None;
            mainOverlay.style.display = DisplayStyle.None;
            if (intakeView != null) intakeView.style.display = DisplayStyle.None;
            SetScene(false);
            if (landing == null) BuildLanding();
            landingStatus.text = "";
            FillRecent();
            landing.style.display = DisplayStyle.Flex;
        }

        // ------------------------------------------------------------ landing
        void BuildLanding()
        {
            var root = doc.rootVisualElement;
            landing = new VisualElement();
            landing.AddToClassList("landing");
            root.Insert(root.IndexOf(mainApp), landing);

            // two columns under the nav: new / open on the left (wider), recently opened on the right
            var columns = new VisualElement();
            columns.AddToClassList("landing-columns");
            landing.Add(columns);
            var left = new VisualElement();
            left.AddToClassList("landing-left");
            columns.Add(left);
            var right = new VisualElement();
            right.AddToClassList("landing-right");
            columns.Add(right);

            var nav = Row("landing-nav");
            var brand = Row("brand");
            var mark = new VisualElement();
            mark.AddToClassList("brand-mark");
            mark.Add(new Label("s"));
            brand.Add(mark);
            brand.Add(Text("Sponge Park.", "landing-brand"));
            nav.Add(brand);
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
            landingStatus = Text("", "hero-status");
            hero.Add(landingStatus);
            left.Add(hero);

            // right: recently opened projects, newest first; the list scrolls inside its panel
            var recent = new VisualElement();
            recent.AddToClassList("recent");
            var head = Row("recent-head");
            head.Add(Text("RECENTLY OPENED", "recent-title"));
            recentClear = Btn("Clear list", () => { SaveRecent(new List<RecentProject>()); FillRecent(); }, "btn--link");
            head.Add(recentClear);
            recent.Add(head);
            recentList = new ScrollView(ScrollViewMode.Vertical) { horizontalScrollerVisibility = ScrollerVisibility.Hidden };
            recentList.AddToClassList("recent-list");
            recent.Add(recentList);
            right.Add(recent);
        }

        void FillRecent()
        {
            recentList.Clear();
            var all = Recent();
            recentClear.style.display = all.Count > 0 ? DisplayStyle.Flex : DisplayStyle.None;
            if (all.Count == 0)
            {
                recentList.Add(Text("Projects you open or create will appear here.", "recent-empty"));
                return;
            }
            foreach (var r in all) recentList.Add(RecentItem(r));
        }

        VisualElement RecentItem(RecentProject r)
        {
            bool missing = !System.IO.File.Exists(r.path);
            var item = new VisualElement();
            item.AddToClassList("recent-item");
            item.EnableInClassList("recent-item--missing", missing);

            var open = new Button(() => StartCoroutine(OpenExisting(r.path))) { tooltip = r.path };
            open.AddToClassList("recent-open");
            var icon = new VisualElement { pickingMode = PickingMode.Ignore };
            icon.AddToClassList("recent-icon");
            icon.Add(Text("◆", "recent-glyph"));
            open.Add(icon);
            var words = new VisualElement { pickingMode = PickingMode.Ignore };
            words.AddToClassList("recent-words");
            words.Add(Text(string.IsNullOrEmpty(r.name) ? System.IO.Path.GetFileNameWithoutExtension(r.path) : r.name, "recent-name"));
            words.Add(Text(Shorten(System.IO.Path.GetDirectoryName(r.path) ?? "", 48), "recent-path"));
            open.Add(words);
            open.Add(Text(missing ? "file not found" : Ago(r.opened), "recent-when"));
            item.Add(open);

            var remove = new Button(() => { Forget(r.path); FillRecent(); }) { text = "×", tooltip = "Remove from this list (the file is not deleted)" };
            remove.AddToClassList("recent-remove");
            item.Add(remove);
            return item;
        }

        static string Shorten(string s, int max) => s.Length <= max ? s : "…" + s.Substring(s.Length - (max - 1));

        static string Ago(System.DateTime? when)
        {
            if (when == null) return "";
            var d = System.DateTime.UtcNow - when.Value;
            if (d.TotalMinutes < 1) return "just now";
            if (d.TotalHours < 1) return $"{(int)d.TotalMinutes} min ago";
            if (d.TotalDays < 1) return $"{(int)d.TotalHours} h ago";
            if (d.TotalDays < 2) return "yesterday";
            if (d.TotalDays < 7) return $"{(int)d.TotalDays} days ago";
            return when.Value.ToLocalTime().ToString("d MMM yyyy");
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

        /// While the landing is up: checks the engine every few seconds and starts it once if it is not running.
        void AnimateLanding()
        {
            if (landing == null || landing.style.display == DisplayStyle.None) return;
            float t = Time.unscaledTime;
            if (t > nextEngineCheck) { nextEngineCheck = t + 5; StartCoroutine(EnsureEngine()); }
        }

        IEnumerator EnsureEngine()
        {
            yield return CheckEngine();
            if (!engineUp && !engineLaunched) { engineLaunched = true; launcher.Launch(); }
        }

        /// Waits (up to 30 s) for the engine, starting it if needed; then runs next. Says why if it never comes up.
        IEnumerator WhenEngineReady(System.Action next)
        {
            landingStatus.text = "Starting the engine…";
            for (int i = 0; i < 30 && !engineUp; i++)
            {
                yield return EnsureEngine();
                if (!engineUp) yield return new WaitForSecondsRealtime(1);
            }
            if (!engineUp)
            {
                landingStatus.text = "The engine did not start" + (launcher.Message.StartsWith("could not") ? " (" + launcher.Message + ")" : "") +
                                     ". Check that Python and spongepark are installed, or run spongepark serve, then try again.";
                yield break;
            }
            landingStatus.text = "";
            next();
        }

        class RecentProject
        {
            public string path, name;
            public System.DateTime? opened;   // UTC; null for entries carried over from the old list
        }

        static List<RecentProject> Recent()
        {
            var json = PlayerPrefs.GetString(RecentListKey, "");
            if (json.Length == 0)   // first run with this list: carry over the old one
                return PlayerPrefs.GetString(RecentKey, "").Split('|')
                    .Where(x => x.EndsWith(".sponge", System.StringComparison.OrdinalIgnoreCase))
                    .Select(x => new RecentProject { path = x }).ToList();
            try
            {
                return JArray.Parse(json).Select(t => new RecentProject
                {
                    path = (string)t["path"],
                    name = (string)t["name"],
                    opened = t["opened"] != null && t["opened"].Type == JTokenType.Integer
                        ? System.DateTimeOffset.FromUnixTimeSeconds((long)t["opened"]).UtcDateTime : (System.DateTime?)null,
                }).Where(r => !string.IsNullOrEmpty(r.path)).ToList();
            }
            catch (Newtonsoft.Json.JsonException) { return new List<RecentProject>(); }
        }

        static void SaveRecent(List<RecentProject> list)
        {
            var a = new JArray(list.Take(RecentKeep).Select(r => new JObject
            {
                ["path"] = r.path,
                ["name"] = r.name,
                ["opened"] = r.opened == null ? null : (JToken)new System.DateTimeOffset(r.opened.Value).ToUnixTimeSeconds(),
            }));
            PlayerPrefs.SetString(RecentListKey, a.ToString(Newtonsoft.Json.Formatting.None));
            PlayerPrefs.Save();
        }

        static string FullPath(string p)
        {
            try { return System.IO.Path.GetFullPath(p); } catch (System.Exception) { return p; }
        }

        static bool SamePath(string a, string b) => string.Equals(FullPath(a), FullPath(b), System.StringComparison.OrdinalIgnoreCase);

        /// Puts a project at the top of the recently opened list (called whenever one opens).
        static void Remember(string path, string name)
        {
            if (string.IsNullOrEmpty(path)) return;
            var r = Recent();
            r.RemoveAll(x => SamePath(x.path, path));
            r.Insert(0, new RecentProject { path = FullPath(path), name = name, opened = System.DateTime.UtcNow });
            SaveRecent(r);
        }

        static void Forget(string path)
        {
            var r = Recent();
            r.RemoveAll(x => SamePath(x.path, path));
            SaveRecent(r);
        }

        IEnumerator OpenExisting(string path)
        {
            if (!engineUp)
            {
                bool ready = false;
                yield return WhenEngineReady(() => ready = true);
                if (!ready) yield break;
            }
            projectPath = path;
            info = null;   // so a project open before this one does not count as success
            landingStatus.text = "Opening " + System.IO.Path.GetFileName(path) + "…";
            yield return OpenProject(false);
            if (info == null) { landingStatus.text = "Could not open: " + api.LastError; yield break; }
            ShowMain();
        }

        // ------------------------------------------------------------ file browser (the engine lists folders)
        /// The Windows file-open dialog; the in-app browser where the system dialog is not available.
        void PickFile(string title, string label, string extensions, System.Action<string> pick)
        {
            if (!engineUp) { StartCoroutine(WhenEngineReady(() => PickFile(title, label, extensions, pick))); return; }
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
            if (!engineUp) { StartCoroutine(WhenEngineReady(() => OpenBrowser(title, ext, pick))); return; }
            if (!api.Current)
            {
                landingStatus.text = "The running engine is older than this app. In its window press Ctrl+C, run spongepark serve again, then try again.";
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
            var contours = Chip("Always use the drawn contours", null);
            contours.tooltip = "Off: the engine builds the ground from the spot levels when the contours disagree with them or were generated from them, and says so.";
            contours.clicked += () => { intakeContours = !intakeContours; contours.EnableInClassList("chip--on", intakeContours); };
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
                ["contours_in_surface"] = intakeContours ? (object)true : "auto",
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
            yield return StartGuide();   // a new project: the checklist guides it (unless turned off in Settings)
            ShowMain();
        }
    }
}
