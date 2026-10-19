// The status bar: survey X and Y under the cursor, the ground level there, the water depth there (while water is
// shown), snapping, units, the area budget (on the Design tab), the latest message or running job, the engine,
// and the calibration status.
using System;
using UnityEngine;
using UnityEngine.UIElements;

namespace SpongePark.UI
{
    public class StatusData
    {
        public string X = "—", Y = "—", Ground = "—", Depth = null, Message = "", Calibration = "uncalibrated";
        public bool Error, Busy, EngineUp, ShowBudget, BudgetOver, Snap;
        public float BudgetUsedPct, BudgetLimitPct;
    }

    public class StatusBar
    {
        public readonly VisualElement Root;
        readonly Label x, y, ground, depth, message, engine, calibration, budget;
        readonly VisualElement engineDot, budgetBox, budgetFill;
        readonly Button snap;
        public Action OnSnap;

        public StatusBar()
        {
            Root = Kit.Box("statusbar");
            x = Item("X —", 80);
            y = Item("Y —", 80);
            ground = Item("Ground —", 110);
            depth = Item("Water —", 100);
            snap = new Button(() => OnSnap?.Invoke());
            snap.AddToClassList("sb-btn");
            snap.Add(Kit.Icon("snap"));
            snap.Add(Kit.Label("Snap", ""));
            snap.tooltip = "Snapping to corners, edges, contours and the grid (the drawing tools use it from Pass 2)";
            Root.Add(snap);
            Root.Add(Item("m", 0));
            budgetBox = Kit.Box("row");
            budgetBox.style.flexWrap = Wrap.NoWrap;
            budget = Kit.Label("", "sb");
            budget.style.borderRightWidth = 0;
            budgetBox.Add(budget);
            var bar = Kit.Box("sb-budget");
            budgetFill = Kit.Box("sb-budget-fill");
            bar.Add(budgetFill);
            budgetBox.Add(bar);
            Root.Add(budgetBox);
            message = Kit.Label("", "sb", "sb--grow");
            Root.Add(message);
            engineDot = Kit.Box("sb-dot");
            Root.Add(engineDot);
            engine = Item("Engine", 0);
            calibration = Item("", 0);
            calibration.style.borderRightWidth = 0;
        }

        Label Item(string text, float width)
        {
            var l = Kit.Label(text, "sb");
            if (width > 0) l.style.width = width;
            Root.Add(l);
            return l;
        }

        public void Refresh(StatusData d)
        {
            x.text = "X " + d.X;
            y.text = "Y " + d.Y;
            ground.text = "Ground " + d.Ground;
            Kit.Show(depth, d.Depth != null);
            depth.text = "Water " + (d.Depth ?? "—");
            snap.EnableInClassList("sb-btn--on", d.Snap);
            Kit.Show(budgetBox, d.ShowBudget);
            budget.text = $"Area {d.BudgetUsedPct:0.0} % of {d.BudgetLimitPct:0.#} %";
            budgetFill.style.width = Length.Percent(Mathf.Clamp01(d.BudgetLimitPct > 0 ? d.BudgetUsedPct / d.BudgetLimitPct : 0) * 100);
            budgetFill.EnableInClassList("sb-budget-fill--over", d.BudgetOver);
            message.text = d.Message;
            message.tooltip = d.Message;
            message.EnableInClassList("sb--error", d.Error);
            engineDot.EnableInClassList("sb-dot--ok", d.EngineUp && !d.Busy);
            engineDot.EnableInClassList("sb-dot--busy", d.Busy);
            engine.text = d.Busy ? "Working…" : d.EngineUp ? "Engine" : "Engine off";
            calibration.text = d.Calibration;
            calibration.tooltip = d.Calibration == "Uncalibrated" ? "Results are for comparing designs, not absolute prediction" : "";
        }
    }

    /// Short notices for finished jobs and errors, bottom right, fading after a few seconds.
    public class Toasts
    {
        public readonly VisualElement Root;
        public Toasts()
        {
            Root = Kit.Box("toasts");
            Root.pickingMode = PickingMode.Ignore;
        }

        public void Show(string text, string kind = "info", float seconds = 5)
        {
            var t = Kit.Box("toast", "toast--" + kind, "toast--hidden");
            t.Add(Kit.Icon(kind == "error" ? "warning" : kind == "ok" ? "check" : "info"));
            var l = Kit.Label(text, "");
            t.Add(l);
            t.RegisterCallback<ClickEvent>(e => t.RemoveFromHierarchy());
            Root.Add(t);
            while (Root.childCount > 4) Root.RemoveAt(0);
            t.schedule.Execute(() => t.RemoveFromClassList("toast--hidden")).StartingIn(20);
            t.schedule.Execute(() => t.AddToClassList("toast--hidden")).StartingIn((long)(seconds * 1000));
            t.schedule.Execute(() => t.RemoveFromHierarchy()).StartingIn((long)(seconds * 1000) + 400);
        }
    }

    /// A modal dialog with optional pages (tabs along the top).
    public class Dialog
    {
        public readonly VisualElement Root;
        readonly VisualElement body;
        readonly System.Collections.Generic.Dictionary<string, (Button tab, VisualElement page)> pages =
            new System.Collections.Generic.Dictionary<string, (Button, VisualElement)>();
        readonly VisualElement tabs;

        public Dialog(string title, VisualElement host)
        {
            Root = Kit.Box("dialog-back");
            Root.RegisterCallback<PointerDownEvent>(e => { if (e.target == Root) Close(); });
            var box = Kit.Box("dialog");
            Root.Add(box);
            var head = Kit.Box("dialog-head");
            head.Add(Kit.Label(title, "dialog-title"));
            head.Add(Kit.IconButton("close", "Close", Close));
            box.Add(head);
            tabs = Kit.Box("dialog-tabs");
            box.Add(tabs);
            Kit.Show(tabs, false);
            var sv = new ScrollView(ScrollViewMode.Vertical) { horizontalScrollerVisibility = ScrollerVisibility.Hidden };
            sv.AddToClassList("dialog-body");
            body = sv;
            box.Add(sv);
            host.Add(Root);
            Kit.Show(Root, false);
        }

        public VisualElement Page(string key, string label)
        {
            var page = new VisualElement();
            var b = new Button(() => ShowPage(key)) { text = label };
            b.AddToClassList("props-tab");
            tabs.Add(b);
            Kit.Show(tabs, true);
            body.Add(page);
            pages[key] = (b, page);
            ShowPage(pages.Count == 1 ? key : null);
            return page;
        }

        public VisualElement Body => body;

        public void ShowPage(string key)
        {
            if (key == null) return;
            foreach (var kv in pages)
            {
                kv.Value.tab.EnableInClassList("props-tab--on", kv.Key == key);
                Kit.Show(kv.Value.page, kv.Key == key);
            }
        }

        public bool IsOpen => Root.style.display != DisplayStyle.None;
        public void Open(string page = null) { Kit.Show(Root, true); Root.BringToFront(); if (page != null) ShowPage(page); }
        public void Close() => Kit.Show(Root, false);
    }
}
