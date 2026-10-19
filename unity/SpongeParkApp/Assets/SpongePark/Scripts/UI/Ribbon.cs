// The ribbon: one tab per stage (Site, Analyse, Design, Simulate, Results, Export), each showing only that
// stage's tools in labelled groups, large icons for the main actions and small ones for the rest. Collapses to
// the tab names (double-click a tab, or the chevron). Buttons follow their commands' enabled / on / visible state.
using System.Collections.Generic;
using UnityEngine.UIElements;

namespace SpongePark.UI
{
    public class RibbonGroup
    {
        public string Title;
        public readonly List<(Command cmd, bool large)> Items = new List<(Command, bool)>();
        public readonly List<VisualElement> Custom = new List<VisualElement>();
        public RibbonGroup(string title) { Title = title; }
        public RibbonGroup Large(Command c) { Items.Add((c, true)); return this; }
        public RibbonGroup Small(Command c) { Items.Add((c, false)); return this; }
        public RibbonGroup Add(VisualElement e) { Custom.Add(e); return this; }
    }

    public class RibbonTab
    {
        public Tab Tab;
        public string Label;
        public readonly List<RibbonGroup> Groups = new List<RibbonGroup>();
        public RibbonTab(Tab tab, string label) { Tab = tab; Label = label; }
        public RibbonGroup Group(string title) { var g = new RibbonGroup(title); Groups.Add(g); return g; }
    }

    public class Ribbon
    {
        public readonly VisualElement Root;
        readonly UiState state;
        readonly VisualElement body;
        readonly Dictionary<Tab, Button> tabButtons = new Dictionary<Tab, Button>();
        readonly Dictionary<Tab, VisualElement> pages = new Dictionary<Tab, VisualElement>();
        readonly List<(Command cmd, Button b)> buttons = new List<(Command, Button)>();
        readonly Button collapse;

        public Ribbon(UiState state, List<RibbonTab> tabs)
        {
            this.state = state;
            Root = Kit.Box("ribbon");
            var head = Kit.Box("ribbon-tabs");
            Root.Add(head);
            body = Kit.Box("ribbon-body");
            Root.Add(body);
            foreach (var t in tabs)
            {
                var tt = t.Tab;
                var b = new Button(() => Select(tt)) { text = t.Label };
                b.AddToClassList("ribbon-tab");
                b.RegisterCallback<MouseDownEvent>(e => { if (e.clickCount == 2) Toggle(); }, TrickleDown.TrickleDown);
                head.Add(b);
                tabButtons[tt] = b;
                var page = Kit.Box("row");
                page.style.flexWrap = Wrap.NoWrap;
                foreach (var g in t.Groups) page.Add(BuildGroup(g));
                pages[tt] = page;
                body.Add(page);
            }
            var gap = new VisualElement();
            gap.style.flexGrow = 1;
            head.Add(gap);
            collapse = Kit.IconButton("expand-up", "Collapse the ribbon to its tab names (double-click a tab)", Toggle);
            head.Add(collapse);
            state.TabChanged += Sync;
            state.LayoutChanged += Sync;
            Sync();
        }

        VisualElement BuildGroup(RibbonGroup g)
        {
            var box = Kit.Box("ribbon-group");
            var row = Kit.Box("ribbon-buttons");
            box.Add(row);
            VisualElement stack = null;
            int inStack = 0;
            foreach (var (cmd, large) in g.Items)
            {
                var b = new Button(() => { if (cmd.Enabled()) cmd.Run(); });
                b.AddToClassList("rb");
                b.AddToClassList(large ? "rb--large" : "rb--small");
                if (cmd.Primary) b.AddToClassList("rb--primary");
                b.Add(Kit.Icon(cmd.Icon, large));
                b.Add(Kit.Label(cmd.Label, "rb-label"));
                b.tooltip = cmd.Tooltip + (string.IsNullOrEmpty(cmd.Shortcut) ? "" : $"  ({cmd.Shortcut})");
                buttons.Add((cmd, b));
                if (large) { row.Add(b); stack = null; continue; }
                if (stack == null || inStack == 3) { stack = Kit.Box("ribbon-stack"); row.Add(stack); inStack = 0; }
                stack.Add(b);
                inStack++;
            }
            foreach (var c in g.Custom) row.Add(c);
            box.Add(Kit.Label(g.Title, "ribbon-group-title"));
            return box;
        }

        public void Select(Tab t)
        {
            state.ActiveTab = t;
            if (state.Layout.ribbonCollapsed) state.ChangeLayout(l => l.ribbonCollapsed = false);
        }

        void Toggle() => state.ChangeLayout(l => l.ribbonCollapsed = !l.ribbonCollapsed);

        void Sync()
        {
            foreach (var kv in tabButtons) kv.Value.EnableInClassList("ribbon-tab--on", kv.Key == state.ActiveTab);
            foreach (var kv in pages) Kit.Show(kv.Value, kv.Key == state.ActiveTab);
            Root.EnableInClassList("ribbon--collapsed", state.Layout.ribbonCollapsed);
            Kit.SetIcon(collapse.Q(className: "icon"), state.Layout.ribbonCollapsed ? "expand-down" : "expand-up");
        }

        /// Every frame: buttons follow their commands.
        public void Refresh()
        {
            foreach (var (cmd, b) in buttons)
            {
                bool vis = cmd.Visible();
                Kit.Show(b, vis);
                if (!vis) continue;
                b.SetEnabled(cmd.Enabled());
                b.EnableInClassList("rb--on", cmd.On());
            }
        }
    }
}
