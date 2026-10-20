// The right column: the guided-project checklist (when guided) above Properties, which has three tabs:
// Properties (the selected element, or the site summary when nothing is selected), Checks (the design's checks and
// budget) and Results (flow hotspots, suggested layouts, SWMM results, comparisons). Sections are the app's own
// controls, shown when they have something to say; an empty tab says what to do next.
using System;
using System.Collections.Generic;
using UnityEngine.UIElements;

namespace SpongePark.UI
{
    public class PropertiesPanel
    {
        public readonly VisualElement Root;          // the whole right column
        public readonly VisualElement ChecklistSlot;
        readonly UiState state;
        readonly VisualElement panel;
        readonly Dictionary<string, Button> tabs = new Dictionary<string, Button>();
        readonly Dictionary<string, ScrollView> pages = new Dictionary<string, ScrollView>();
        readonly Dictionary<string, Label> empties = new Dictionary<string, Label>();
        readonly List<(string tab, VisualElement box, Func<bool> visible)> sections = new List<(string, VisualElement, Func<bool>)>();
        readonly Dictionary<string, Func<string>> emptyText = new Dictionary<string, Func<string>>();
        readonly Button collapse;

        public ScrollView Page(string tab) => pages[tab];

        public PropertiesPanel(UiState state)
        {
            this.state = state;
            Root = Kit.Box("right-col");
            // the checklist keeps its height; Properties takes the rest and scrolls (on a 768 px screen too)
            ChecklistSlot = new VisualElement();
            ChecklistSlot.style.flexShrink = 0;
            Root.Add(ChecklistSlot);
            panel = Kit.Box("panel", "panel--right");
            panel.style.flexGrow = 1;
            panel.style.flexShrink = 1;
            panel.style.minHeight = 120;
            Root.Add(panel);
            var head = Kit.Box("panel-head");
            collapse = Kit.IconButton("collapse-right", "Collapse the panel", () => state.ChangeLayout(l => l.propsCollapsed = !l.propsCollapsed));
            head.Add(collapse);
            var tabRow = Kit.Box("props-tabs");
            tabRow.style.borderBottomWidth = 0;
            foreach (var (key, label) in new[] { ("properties", "Properties"), ("checks", "Checks"), ("results", "Results") })
            {
                var k = key;
                var b = new Button(() => state.PropsTab = k) { text = label };
                b.AddToClassList("props-tab");
                tabs[key] = b;
                tabRow.Add(b);
            }
            tabRow.style.flexGrow = 1;
            head.Insert(0, tabRow);
            head.style.paddingLeft = 0;
            head.RegisterCallback<MouseDownEvent>(e => { if (e.clickCount == 2) state.ViewportMax = !state.ViewportMax; });
            panel.Add(head);
            var strip = Kit.Box("strip");
            strip.Add(Kit.IconButton("info", "Properties", () => { state.PropsTab = "properties"; state.ChangeLayout(l => l.propsCollapsed = false); }));
            strip.Add(Kit.IconButton("warning", "Checks", () => { state.PropsTab = "checks"; state.ChangeLayout(l => l.propsCollapsed = false); }));
            strip.Add(Kit.IconButton("results", "Results", () => { state.PropsTab = "results"; state.ChangeLayout(l => l.propsCollapsed = false); }));
            panel.Add(strip);
            var body = Kit.Box("panel-body");
            panel.Add(body);
            foreach (var key in tabs.Keys)
            {
                var sv = new ScrollView(ScrollViewMode.Vertical) { horizontalScrollerVisibility = ScrollerVisibility.Hidden };
                sv.AddToClassList("props-scroll");
                var empty = Kit.Label("", "empty");
                sv.Add(empty);
                empties[key] = empty;
                pages[key] = sv;
                body.Add(sv);
            }
            state.PropsTabChanged += Sync;
            state.LayoutChanged += Sync;
            Sync();
        }

        /// A section on a tab: a title and the app's own control, shown while visible() says so.
        public VisualElement Section(string tab, string title, VisualElement content, Func<bool> visible = null)
        {
            var box = Kit.Box("props-section");
            if (!string.IsNullOrEmpty(title)) box.Add(Kit.Label(title.ToUpper(), "props-section-title"));
            box.Add(content);
            pages[tab].Add(box);
            sections.Add((tab, box, visible ?? (() => true)));
            return box;
        }

        public void EmptyText(string tab, Func<string> text) => emptyText[tab] = text;

        void Sync()
        {
            foreach (var kv in tabs) kv.Value.EnableInClassList("props-tab--on", kv.Key == state.PropsTab);
            foreach (var kv in pages) Kit.Show(kv.Value, kv.Key == state.PropsTab);
            bool c = state.Layout.propsCollapsed;
            panel.EnableInClassList("panel--collapsed", c);
            Root.style.width = c ? 36 : state.Layout.propsWidth;
            Kit.Show(ChecklistSlot, !c);
            Kit.SetIcon(collapse.Q(className: "icon"), c ? "collapse-left" : "collapse-right");
        }

        public void Refresh()
        {
            var any = new Dictionary<string, bool>();
            foreach (var (tab, box, visible) in sections)
            {
                bool v = visible();
                Kit.Show(box, v);
                if (v) any[tab] = true;
            }
            foreach (var kv in empties)
            {
                bool show = !any.ContainsKey(kv.Key);
                Kit.Show(kv.Value, show);
                if (show && emptyText.TryGetValue(kv.Key, out var t)) kv.Value.text = t();
            }
        }
    }
}
