// Contents: the layer tree. Groups Survey (one row per survey layer), Analysis (contours, flow lines, arrows,
// ponding, exits, water), Design (one row per element, by type) and Results. Each row: visibility eye, colour
// swatch, name, count, a lock on locked design elements. Clicking a design element row selects it in the viewport
// (and selecting it there highlights the row). Collapses to an icon strip; double-click the header for a full view.
using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;

namespace SpongePark.UI
{
    public class ContentsRow
    {
        public string Key, Label, Tooltip, Count;
        public Color Swatch;
        public Func<bool> Visible;        // null: no eye
        public Action<bool> SetVisible;
        public Func<bool> Selected = () => false;
        public Action Select;             // null: not selectable
        public bool Locked, Check;
    }

    public class ContentsGroup
    {
        public string Key, Title, Empty;
        public readonly List<ContentsRow> Rows = new List<ContentsRow>();
    }

    public class ContentsPanel
    {
        public readonly VisualElement Root;
        readonly UiState state;
        readonly ScrollView tree;
        readonly List<(ContentsRow row, Button b, VisualElement eye)> rows = new List<(ContentsRow, Button, VisualElement)>();
        readonly HashSet<string> folded = new HashSet<string>();
        List<ContentsGroup> groups = new List<ContentsGroup>();
        readonly Button collapse;
        public Action<bool> SetAll;

        public ContentsPanel(UiState state)
        {
            this.state = state;
            Root = Kit.Box("panel", "panel--left");
            var head = Kit.Box("panel-head");
            head.Add(Kit.Label("CONTENTS", "panel-title"));
            collapse = Kit.IconButton("collapse-left", "Collapse the panel", () => state.ChangeLayout(l => l.contentsCollapsed = !l.contentsCollapsed));
            head.Add(collapse);
            head.RegisterCallback<MouseDownEvent>(e => { if (e.clickCount == 2) state.ViewportMax = !state.ViewportMax; });
            Root.Add(head);
            var strip = Kit.Box("strip");
            strip.Add(Kit.IconButton("layers", "Contents", () => state.ChangeLayout(l => l.contentsCollapsed = false)));
            Root.Add(strip);
            var body = Kit.Box("panel-body");
            var tools = Kit.Box("tree-tools");
            tools.Add(Kit.IconButton("eye", "Show every layer", () => SetAll?.Invoke(true)));
            tools.Add(Kit.IconButton("eye-off", "Hide every layer", () => SetAll?.Invoke(false)));
            body.Add(tools);
            tree = new ScrollView(ScrollViewMode.Vertical) { horizontalScrollerVisibility = ScrollerVisibility.Hidden };
            tree.style.flexGrow = 1;
            body.Add(tree);
            Root.Add(body);
            state.LayoutChanged += Sync;
            Sync();
        }

        void Sync()
        {
            bool c = state.Layout.contentsCollapsed;
            Root.EnableInClassList("panel--collapsed", c);
            Root.style.width = c ? 36 : state.Layout.contentsWidth;
            Kit.SetIcon(collapse.Q(className: "icon"), c ? "collapse-right" : "collapse-left");
        }

        public void Rebuild(List<ContentsGroup> next)
        {
            groups = next;
            tree.Clear();
            rows.Clear();
            foreach (var g in groups)
            {
                var gg = g;
                var gh = new Button(() => { if (!folded.Remove(gg.Key)) folded.Add(gg.Key); Rebuild(groups); });
                gh.AddToClassList("tree-group-head");
                gh.Add(Kit.Icon(folded.Contains(g.Key) ? "collapse-right" : "expand-down"));
                gh.Add(Kit.Label(g.Title.ToUpper(), "tree-group-title"));
                gh.Add(Kit.Label(g.Rows.Count.ToString(), "tree-group-count"));
                tree.Add(gh);
                if (folded.Contains(g.Key)) continue;
                if (g.Rows.Count == 0 && !string.IsNullOrEmpty(g.Empty)) tree.Add(Kit.Label(g.Empty, "empty"));
                foreach (var r in g.Rows)
                {
                    var rr = r;
                    var b = new Button(() => { if (rr.Select != null) rr.Select(); else if (rr.SetVisible != null) rr.SetVisible(!rr.Visible()); });
                    b.AddToClassList("tree-row");
                    b.tooltip = r.Tooltip;
                    VisualElement eye = null;
                    if (r.Visible != null)
                    {
                        var eb = new Button(() => rr.SetVisible(!rr.Visible()));
                        eb.AddToClassList("tree-eye");
                        eye = Kit.Icon("eye");
                        eb.Add(eye);
                        eb.tooltip = "Show or hide";
                        b.Add(eb);
                    }
                    else
                    {
                        var pad = new VisualElement();
                        pad.style.width = 24;
                        b.Add(pad);
                    }
                    var sw = Kit.Box("tree-swatch");
                    sw.pickingMode = PickingMode.Ignore;
                    sw.style.backgroundColor = r.Swatch;
                    b.Add(sw);
                    b.Add(Kit.Label(r.Label, "tree-label"));
                    if (!string.IsNullOrEmpty(r.Count)) b.Add(Kit.Label(r.Count, "tree-count"));
                    if (r.Locked)
                    {
                        var lk = Kit.Icon("lock");
                        lk.AddToClassList("tree-lock");
                        lk.tooltip = "Your own element: the suggestions leave it as it is";
                        b.Add(lk);
                    }
                    b.EnableInClassList("tree-row--check", r.Check);
                    tree.Add(b);
                    rows.Add((r, b, eye));
                }
            }
            Refresh();
        }

        /// Every frame: eyes and selection follow the app.
        public void Refresh()
        {
            foreach (var (r, b, eye) in rows)
            {
                bool on = r.Visible == null || r.Visible();
                b.EnableInClassList("tree-row--off", !on);
                b.EnableInClassList("tree-row--sel", r.Selected());
                if (eye != null) Kit.SetIcon(eye, on ? "eye" : "eye-off");
            }
        }
    }
}
