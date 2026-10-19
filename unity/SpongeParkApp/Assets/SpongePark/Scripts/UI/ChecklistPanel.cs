// The guided first project: a checklist docked above Properties. Each stage is done, current or locked; it says in
// one line why it matters (or what is missing while locked) and has a button that opens the right tool.
using System;
using System.Collections.Generic;
using UnityEngine.UIElements;

namespace SpongePark.UI
{
    public enum StageState { Done, Current, Open, Locked }

    public class Stage
    {
        public string Id, Title, Why, Missing, Action;
        public Func<StageState> State;
        public Action Go;
    }

    public class ChecklistPanel
    {
        public readonly VisualElement Root;
        readonly List<(Stage s, VisualElement row, VisualElement mark, Label why, Button go)> items = new List<(Stage, VisualElement, VisualElement, Label, Button)>();
        readonly Label progress;

        public ChecklistPanel(UiState state, List<Stage> stages)
        {
            Root = Kit.Box("panel", "checklist");
            var head = Kit.Box("panel-head");
            head.Add(Kit.Label("PROJECT CHECKLIST", "panel-title"));
            progress = Kit.Label("", "tree-group-count");
            head.Add(progress);
            head.Add(Kit.IconButton("close", "Hide the checklist (reopen it from the app bar)", () => state.ChecklistOpen = false));
            Root.Add(head);
            var list = new ScrollView(ScrollViewMode.Vertical) { horizontalScrollerVisibility = ScrollerVisibility.Hidden };
            list.style.maxHeight = 300;
            Root.Add(list);
            foreach (var s in stages)
            {
                var row = Kit.Box("check-item");
                var mark = Kit.Icon("circle");
                mark.AddToClassList("check-mark");
                row.Add(mark);
                var words = Kit.Box("check-words");
                words.Add(Kit.Label(s.Title, "check-title"));
                var why = Kit.Label(s.Why, "check-why");
                words.Add(why);
                var ss = s;
                var go = new Button(() => ss.Go?.Invoke()) { text = s.Action };
                go.AddToClassList("btn");
                go.AddToClassList("btn--outline");
                go.AddToClassList("check-go");
                words.Add(go);
                row.Add(words);
                list.Add(row);
                items.Add((s, row, mark, why, go));
            }
        }

        public void Refresh()
        {
            int done = 0;
            foreach (var (s, row, mark, why, go) in items)
            {
                var st = s.State();
                if (st == StageState.Done) done++;
                row.EnableInClassList("check-item--done", st == StageState.Done);
                row.EnableInClassList("check-item--current", st == StageState.Current);
                row.EnableInClassList("check-item--locked", st == StageState.Locked);
                Kit.SetIcon(mark, st == StageState.Done ? "check" : st == StageState.Locked ? "locked" : "circle");
                why.text = st == StageState.Locked && !string.IsNullOrEmpty(s.Missing) ? s.Missing : s.Why;
                Kit.Show(go, st == StageState.Current || st == StageState.Open);
            }
            progress.text = $"{done} of {items.Count}";
        }
    }
}
