// The timeline: the storm as a bar chart of rain (hyetograph), a scrubber, play / pause / restart, speed, the
// return period, and the litres kept on site so far (existing, and design or option when there is one).
using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;

namespace SpongePark.UI
{
    public class TimelineData
    {
        public string Title = "", Text = "", LeftName = "EXISTING", RightName = "";
        public bool Playing, CanPlay, CanScrub, ShowRight, ShowLeft;
        public float T, End, Speed, LitresLeft, LitresRight;
        public float[] Rain;                 // mm/h per bin over the storm
        public string Empty = "";            // what to do when there is no storm to show
        public List<int> ReturnPeriods = new List<int>();
        public int RpIndex;
    }

    public class Timeline
    {
        public readonly VisualElement Root;
        readonly UiState state;
        readonly Label title, text, speedLabel, leftName, leftValue, rightName, rightValue;
        readonly Button play;
        readonly VisualElement hyeto, rightRow, leftRow;
        readonly Slider scrub, speed;
        readonly DropdownField rp;
        readonly Button collapse;
        readonly List<VisualElement> bars = new List<VisualElement>();
        int rainHash;
        bool syncing;

        public Action OnPlay, OnRestart;
        public Action<float> OnScrub, OnSpeed;
        public Action<int> OnRp;

        public Timeline(UiState state)
        {
            this.state = state;
            Root = Kit.Box("timeline");
            var head = Kit.Box("timeline-head");
            head.Add(Kit.Icon("storm"));
            title = Kit.Label("", "timeline-title");
            head.Add(title);
            text = Kit.Label("", "timeline-text");
            head.Add(text);
            rp = new DropdownField(new List<string> { "—" }, 0);
            rp.AddToClassList("input");
            rp.style.width = 150;
            rp.style.marginBottom = 0;
            rp.style.height = 20;
            rp.style.minHeight = 20;
            rp.tooltip = "Design storm (return period)";
            rp.RegisterValueChangedCallback(e => { if (!syncing) OnRp?.Invoke(rp.index); });
            head.Add(rp);
            collapse = Kit.IconButton("expand-down", "Collapse the timeline", () => state.ChangeLayout(l => l.timelineCollapsed = !l.timelineCollapsed));
            head.Add(collapse);
            Root.Add(head);

            var body = Kit.Box("timeline-body");
            var controls = Kit.Box("timeline-controls");
            play = Kit.IconButton("play", "Play / pause (the storm)", () => OnPlay?.Invoke());
            controls.Add(play);
            controls.Add(Kit.IconButton("restart", "Back to the start of the storm", () => OnRestart?.Invoke()));
            var sp = Kit.Box("speed");
            speedLabel = Kit.Label("", "");
            sp.Add(speedLabel);
            speed = new Slider(60, 3600);
            speed.AddToClassList("slider");
            speed.RegisterValueChangedCallback(e => { if (!syncing) OnSpeed?.Invoke(e.newValue); });
            sp.Add(speed);
            controls.Add(sp);
            body.Add(controls);

            var wrap = Kit.Box("hyeto-wrap");
            hyeto = Kit.Box("hyeto");
            wrap.Add(hyeto);
            scrub = new Slider(0, 1);
            scrub.AddToClassList("scrub");
            scrub.RegisterValueChangedCallback(e => { if (!syncing) OnScrub?.Invoke(e.newValue); });
            wrap.Add(scrub);
            body.Add(wrap);

            var side = Kit.Box("timeline-side");
            leftRow = Kit.Box("kept");
            leftName = Kit.Label("", "");
            leftValue = Kit.Label("", "kept-value");
            leftRow.Add(leftName);
            leftRow.Add(leftValue);
            leftRow.Add(Kit.Label("L kept", ""));
            side.Add(leftRow);
            rightRow = Kit.Box("kept");
            rightName = Kit.Label("", "");
            rightValue = Kit.Label("", "kept-value");
            rightRow.Add(rightName);
            rightRow.Add(rightValue);
            rightRow.Add(Kit.Label("L kept", ""));
            side.Add(rightRow);
            side.Add(Kit.Label("Water: 2D model, indicative. Litres: SWMM.", "foot"));
            body.Add(side);
            Root.Add(body);
            state.LayoutChanged += Sync;
            Sync();
        }

        void Sync()
        {
            Root.EnableInClassList("timeline--collapsed", state.Layout.timelineCollapsed);
            Kit.SetIcon(collapse.Q(className: "icon"), state.Layout.timelineCollapsed ? "expand-up" : "expand-down");
        }

        public void Refresh(TimelineData d)
        {
            syncing = true;
            title.text = d.Title;
            text.text = d.Text;
            Kit.SetIcon(play.Q(className: "icon"), d.Playing ? "pause" : "play");
            play.SetEnabled(d.CanPlay);
            speed.SetValueWithoutNotify(d.Speed);
            speedLabel.text = d.Speed >= 3600 ? "Speed: 1 h of storm a second" : $"Speed: {d.Speed / 60:0} min a second";
            scrub.highValue = Mathf.Max(1, d.End);
            scrub.SetValueWithoutNotify(Mathf.Clamp(d.T, 0, scrub.highValue));
            scrub.SetEnabled(d.CanScrub);
            var labels = new List<string>();
            foreach (var y in d.ReturnPeriods) labels.Add($"{y}-year storm");
            if (labels.Count == 0) labels.Add("No storms yet");
            if (string.Join(",", labels) != string.Join(",", rp.choices)) rp.choices = labels;
            rp.SetValueWithoutNotify(labels[Mathf.Clamp(d.RpIndex, 0, labels.Count - 1)]);
            Kit.Show(leftRow, d.ShowLeft);
            Kit.Show(rightRow, d.ShowRight);
            leftName.text = d.LeftName;
            leftValue.text = d.LitresLeft.ToString("N0");
            rightName.text = d.RightName;
            rightValue.text = d.LitresRight.ToString("N0");
            BuildBars(d.Rain, d.Empty);
            float frac = d.End > 0 ? d.T / d.End : 0;
            for (int i = 0; i < bars.Count; i++) bars[i].EnableInClassList("hyeto-bar--past", (i + 0.5f) / bars.Count <= frac);
            syncing = false;
        }

        void BuildBars(float[] rain, string empty)
        {
            int h = rain == null ? (empty ?? "").GetHashCode() : rain.Length * 31;
            if (rain != null) foreach (var r in rain) h = h * 17 + Mathf.RoundToInt(r * 100);
            if (h == rainHash) return;
            rainHash = h;
            hyeto.Clear();
            bars.Clear();
            if (rain == null || rain.Length == 0)
            {
                hyeto.Add(Kit.Label(empty, "hyeto-empty"));
                return;
            }
            float max = 0;
            foreach (var r in rain) max = Mathf.Max(max, r);
            foreach (var r in rain)
            {
                var b = Kit.Box("hyeto-bar");
                b.style.height = Length.Percent(max > 0 ? Mathf.Max(2, 100 * r / max) : 2);
                b.tooltip = $"{r:0.#} mm/h";
                hyeto.Add(b);
                bars.Add(b);
            }
        }
    }
}
