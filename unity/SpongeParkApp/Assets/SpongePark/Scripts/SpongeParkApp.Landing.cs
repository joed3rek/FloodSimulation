// Opening screen and survey intake, the same flow as the web app:
// landing (Import a survey) -> intake (questions with the layer highlighted, every link editable)
// -> Clean and build -> the main view with the new project open.
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.UIElements;
using Kit = SpongePark.UI.Kit;

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
            var scroll = new ScrollView(ScrollViewMode.Vertical) { horizontalScrollerVisibility = ScrollerVisibility.Hidden };
            scroll.AddToClassList("landing-scroll");
            landing.Add(scroll);

            // banner: the park picture on the right, fading into the page under the words
            landHero = new VisualElement();
            landHero.AddToClassList("land-hero");
            landHeroImg = new VisualElement { pickingMode = PickingMode.Ignore };
            landHeroImg.AddToClassList("land-hero-img");
            landHero.Add(landHeroImg);
            var words = new VisualElement { pickingMode = PickingMode.Ignore };
            words.AddToClassList("land-hero-text");
            var eyebrow = Text(UI.Splash.Spaced("DESIGN   RESTORE   ADAPT"), "land-eyebrow");
            words.Add(eyebrow);
            landTitle = Text("Nature-based\nsolutions, in your hands.", "land-title");
            words.Add(landTitle);
            landSub = Text("Plan, design and visualise resilient parks, wetlands and urban landscapes.", "land-sub");
            words.Add(landSub);
            landHero.Add(words);
            scroll.Add(landHero);

            // the two ways in: a new project starts from the site survey; or open a saved one
            var actions = new VisualElement();
            actions.AddToClassList("land-actions");
            actions.Add(ActionCard("plus", "New Project", "Start a new park design from its survey (DXF)", true,
                () => PickFile("Choose the site survey (DXF)", "Site survey", "dxf,dwg", f => StartCoroutine(StartIntake(f)))));
            var open = ActionCard("folder", "Open Project", "Browse your files for a .sponge project", false,
                () => PickFile("Open a Sponge Park project", "Sponge Park project", "sponge", f => StartCoroutine(OpenExisting(f))));
            open.AddToClassList("land-action--next");
            actions.Add(open);
            scroll.Add(actions);
            landingStatus = Text("", "land-status");
            scroll.Add(landingStatus);

            // recent projects, as pictures of their sites
            var head = new VisualElement();
            head.AddToClassList("land-recent-head");
            head.Add(Text("Recent Projects", "land-recent-title"));
            var search = new VisualElement();
            search.AddToClassList("land-search");
            search.Add(Kit.Icon("search"));
            var hint = Text("Search projects…", "land-search-hint");
            landSearch = new TextField();
            landSearch.RegisterValueChangedCallback(e => { Kit.Show(hint, string.IsNullOrEmpty(e.newValue)); FillRecent(); });
            search.Add(landSearch);
            search.Add(hint);
            head.Add(search);
            landViewAll = new Button(() => { recentAll = !recentAll; FillRecent(); });
            landViewAll.AddToClassList("land-viewall");
            landViewAllLabel = Text("View all", "");
            landViewAll.Add(landViewAllLabel);
            var arrow = Kit.Icon("arrow-right");
            arrow.AddToClassList("land-arrow");
            landViewAll.Add(arrow);
            head.Add(landViewAll);
            landClear = new Button { text = "Clear list", tooltip = "Empty the recent list (the project files are not touched)" };
            landClear.AddToClassList("land-viewall");
            landClear.AddToClassList("land-clear");
            landClear.clicked += () =>
            {
                if (landClear.text == "Clear list")
                {
                    landClear.text = "Click again to clear";
                    landClear.schedule.Execute(() => landClear.text = "Clear list").StartingIn(3000);
                    return;
                }
                SaveRecent(new List<RecentProject>());
                recentAll = false;
                landClear.text = "Clear list";
                FillRecent();
            };
            head.Add(landClear);
            scroll.Add(head);
            recentGrid = new VisualElement();
            recentGrid.AddToClassList("land-grid");
            recentGrid.RegisterCallback<GeometryChangedEvent>(e => { if (!Mathf.Approximately(e.oldRect.width, e.newRect.width)) LayoutGrid(); });
            scroll.Add(recentGrid);

            // sizes follow the window: banner about a third of the height, as many picture columns as fit
            landing.RegisterCallback<GeometryChangedEvent>(e => LayoutLanding());
        }

        VisualElement landHero, landHeroImg, recentGrid;
        Label landTitle, landSub, landViewAllLabel;
        TextField landSearch;
        Button landViewAll, landClear;
        bool recentAll;
        int recentCols = 3;
        float landW, landH;

        void LayoutLanding()
        {
            var r = landing.layout;
            if (r.width <= 0 || (Mathf.Approximately(r.width, landW) && Mathf.Approximately(r.height, landH))) return;
            landW = r.width;
            landH = r.height;
            float h = Mathf.Clamp(r.height * 0.31f, 220, 400);
            landHero.style.height = h;
            landHeroImg.style.width = r.width * 0.58f;   // cropped to fit; the words sit left of it
            landTitle.style.fontSize = Mathf.Clamp(h * 0.155f, 36, 58);
            landSub.style.fontSize = Mathf.Clamp(h * 0.065f, 17, 22);
        }

        void LayoutGrid()
        {
            float gridW = recentGrid.layout.width;
            if (float.IsNaN(gridW) || gridW <= 0) return;
            int cols = Mathf.Clamp(Mathf.FloorToInt((gridW + 18) / 360f), 2, 5);
            if (cols != recentCols) { recentCols = cols; FillRecent(); }
            else SizeCards();
        }

        void SizeCards()
        {
            float gridW = recentGrid.layout.width, gap = 18;
            if (float.IsNaN(gridW) || gridW <= 0) return;
            float w = Mathf.Floor((gridW - gap * (recentCols - 1)) / recentCols);
            int i = 0;
            foreach (var c in recentGrid.Children())
            {
                if (!c.ClassListContains("land-card")) continue;
                c.style.width = w;
                c.style.marginRight = (i++ % recentCols == recentCols - 1) ? 0 : gap;
                var thumb = c.Q(className: "land-thumb");
                if (thumb != null) thumb.style.height = Mathf.Round(w * 0.38f);
            }
        }

        Button ActionCard(string icon, string title, string text, bool primary, System.Action onClick)
        {
            var b = new Button(onClick);
            b.AddToClassList("land-action");
            if (primary) b.AddToClassList("land-action--primary");
            var box = new VisualElement { pickingMode = PickingMode.Ignore };
            box.AddToClassList("land-action-icon");
            box.Add(Kit.Icon(icon));
            b.Add(box);
            var words = new VisualElement { pickingMode = PickingMode.Ignore };
            words.AddToClassList("land-action-words");
            words.Add(Text(title, "land-action-title"));
            words.Add(Text(text, "land-action-text"));
            b.Add(words);
            var arrow = Kit.Icon("arrow-right");
            arrow.AddToClassList("land-arrow");
            b.Add(arrow);
            return b;
        }

        void FillRecent()
        {
            if (recentGrid == null) return;
            recentGrid.Clear();
            var all = Recent();
            var q = landSearch?.value?.Trim() ?? "";
            var shown = all.Where(r => q.Length == 0 || (r.name ?? "").IndexOf(q, System.StringComparison.OrdinalIgnoreCase) >= 0
                                                    || r.path.IndexOf(q, System.StringComparison.OrdinalIgnoreCase) >= 0).ToList();
            int first = recentCols * 2;   // two rows unless View all
            Kit.Show(landViewAll, shown.Count > first || recentAll);
            Kit.Show(landClear, all.Count > 0);
            landViewAllLabel.text = recentAll ? "Show fewer" : $"View all ({shown.Count})";
            if (all.Count == 0) { recentGrid.Add(Text("Projects you open or create appear here.", "land-empty")); return; }
            if (shown.Count == 0) { recentGrid.Add(Text($"No project matches “{q}”.", "land-empty")); return; }
            foreach (var r in recentAll ? shown : shown.Take(first)) recentGrid.Add(RecentCard(r));
            SizeCards();
        }

        VisualElement RecentCard(RecentProject r)
        {
            bool missing = !System.IO.File.Exists(r.path);
            var card = new Button(() => StartCoroutine(OpenExisting(r.path))) { tooltip = r.path };
            card.AddToClassList("land-card");
            card.EnableInClassList("land-card--missing", missing);
            var thumb = new VisualElement { pickingMode = PickingMode.Ignore };
            thumb.AddToClassList("land-thumb");
            var tex = Contour(r.path);
            if (tex != null) thumb.style.backgroundImage = new StyleBackground(tex);
            card.Add(thumb);
            var info = new VisualElement { pickingMode = PickingMode.Ignore };
            info.AddToClassList("land-card-info");
            var words = new VisualElement { pickingMode = PickingMode.Ignore };
            words.AddToClassList("land-card-words");
            words.Add(Text(string.IsNullOrEmpty(r.name) ? System.IO.Path.GetFileNameWithoutExtension(r.path) : r.name, "land-card-name"));
            words.Add(Text(missing ? "File not found" : r.opened == null ? "" :
                r.opened.Value.ToLocalTime().ToString("MMM d, yyyy", System.Globalization.CultureInfo.InvariantCulture), "land-card-date"));
            info.Add(words);
            var more = new Button { tooltip = "More" };
            more.AddToClassList("land-more");
            more.Add(Kit.Icon("more"));
            more.clicked += () =>
            {
                var menu = new GenericDropdownMenu();
                if (!missing) menu.AddItem("Open", false, () => StartCoroutine(OpenExisting(r.path)));
                if (!missing) menu.AddItem("Show in folder", false, () => Application.OpenURL("file:///" + (System.IO.Path.GetDirectoryName(r.path) ?? "").Replace('\\', '/')));
                menu.AddItem("Remove from this list", false, () => { Forget(r.path); FillRecent(); });
                menu.DropDown(more.worldBound, more, false);
            };
            info.Add(more);
            card.Add(info);
            return card;
        }

        /// Each project's card shows one of the contour maps, always the same one for the same file.
        static Texture2D Contour(string project)
        {
            int h = 17;
            foreach (var ch in FullPath(project).ToLowerInvariant()) h = h * 31 + ch;
            var k = (h & 0x7fffffff) % 6;
            if (!contours.TryGetValue(k, out var t)) contours[k] = t = Resources.Load<Texture2D>("UI/Landing/contour_" + k);
            return t;
        }

        static readonly Dictionary<int, Texture2D> contours = new Dictionary<int, Texture2D>();

        /// While the landing is up: checks the engine every few seconds and starts it once if it is not running.
        void AnimateLanding()
        {
            if (landing == null || landing.style.display == DisplayStyle.None) return;
            float t = Time.unscaledTime;
            if (t > nextEngineCheck) { nextEngineCheck = t + 5; StartCoroutine(EnsureEngine()); }
        }

        IEnumerator EnsureEngine()
        {
            // before the engine is started one quick look is enough; after, allow it time to answer
            if (engineLaunched) yield return CheckEngine();
            else yield return api.Health(ok => engineUp = ok, 1);
            if (!engineUp && !engineLaunched) { engineLaunched = true; if (launcher.Launch()) engineLaunchAt = Time.realtimeSinceStartup; }
        }

        /// Waits (up to 30 s) for the engine, starting it if needed; then runs next. Says why if it never comes up.
        IEnumerator WhenEngineReady(System.Action next)
        {
            landingStatus.text = "Starting the engine…";
            ShowLoading("Starting the engine", "Opening the flood model on this computer", "This takes a few seconds the first time.");
            for (int i = 0; i < 30 && !engineUp; i++)
            {
                yield return EnsureEngine();
                if (!engineUp) yield return new WaitForSecondsRealtime(1);
            }
            HideLoading();
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
            ShowLoading("Opening the project", System.IO.Path.GetFileName(path));
            yield return OpenProject(false);
            HideLoading();
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
        /// The engine's own message from an error ("url: HTTP/1.1 400 Bad Request {"detail": "..."}"), not the address and code.
        static string Plain(string error)
        {
            int i = error?.IndexOf('{') ?? -1;
            if (i >= 0)
                try { var d = JObject.Parse(error.Substring(i))["detail"]; if (d != null && d.Type == JTokenType.String) return (string)d; }
                catch (Newtonsoft.Json.JsonException) { }
            return error;
        }

        IEnumerator StartIntake(string path)
        {
            if (string.IsNullOrEmpty(path)) yield break;
            landingStatus.text = "Reading " + System.IO.Path.GetFileName(path) + "…";
            ShowLoading("Reading the drawing", System.IO.Path.GetFileName(path), "Large drawings can take a minute.");
            JToken r = null;
            yield return api.Send("POST", "/intake/start", new { path }, x => r = x, 600);
            HideLoading();
            if (r == null)
            {
                landingStatus.text = api.LastError.Contains("404")
                    ? "The running engine is older than this app: restart spongepark serve, then try again."
                    : "Could not read the drawing. " + Plain(api.LastError);
                yield break;
            }
            PlayerPrefs.SetString("spongepark.lastsurvey", path);
            landingStatus.text = "";
            intake = r;
            links.Clear();
            foreach (var l in r["layers"])
                if (l["question"] == null || l["question"].Type == JTokenType.Null) links[(string)l["layer"]] = (string)l["proposed"];
            // next to the drawing; only the file name loses its spaces (the folders are kept as they are, e.g.
            // "I:\Shared drives\..." on Google Drive)
            var survey = (string)r["survey"];
            intakeProjectPath = System.IO.Path.Combine(System.IO.Path.GetDirectoryName(survey) ?? "",
                                             System.IO.Path.GetFileNameWithoutExtension(survey).Replace(' ', '_') + ".sponge");
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
            ShowLoading("Cleaning the drawing and building the ground", "Sending the drawing", "This can take a few minutes for a large park.");
            yield return api.RunJob("POST", "/intake/finish", body, x => r = x, s =>
            {
                intakeStatus.text = "Cleaning the drawing and building the ground… " + s;
                loadingStep = s == "running" ? "Removing duplicates, building the ground model" : s;
            });
            if (r == null) { HideLoading(); intakeStatus.text = "The engine reported a problem: " + api.LastError; buildButton.SetEnabled(true); yield break; }
            var qc = r["qc"]?["spot_cross_validation"];
            status = $"Ground model built. {r["cleaning"]["duplicates_removed_total"]} duplicate objects removed" +
                     (qc != null && qc.Type != JTokenType.Null ? $"; spot levels agree to {(float)qc["rmse_m"]:0.000} m." : ".");
            projectPath = (string)r["project"];
            loadingWhat = "Opening the project";
            loadingStep = System.IO.Path.GetFileName(projectPath);
            yield return OpenProject(false);
            HideLoading();
            yield return StartGuide();   // a new project: the checklist guides it (unless turned off in Settings)
            ShowMain();
        }
    }
}
