// Simulate > Flow trace: the flood's water coloured by speed, with particles carried by its velocities (FlowParticles),
// and a legend. Works while the storm plays and while it is paused (the particles keep moving on the paused moment).
using System.Collections;
using UnityEngine;
using UnityEngine.UIElements;
using Kit = SpongePark.UI.Kit;

namespace SpongePark
{
    public partial class SpongeParkApp
    {
        bool traceOn;
        VisualElement traceLegend;
        Label traceTop, traceMid, traceNote;
        float traceShownTop = -1;

        bool TraceAvailable => !bundle && !live && (left.Frames != null || right.Frames != null);

        void ToggleTrace()
        {
            if (!traceOn && !TraceAvailable)   // say what it needs instead of a greyed-out button
            {
                status = live ? "The flow trace plays a finished flood run; stop the live simulation first."
                       : $"The flow trace shows the speeds of a flood run, and the {CurrentRp}-year storm has none yet. " +
                         "On the Simulate tab press 'Run flood, all storms', then Flow trace.";
                return;
            }
            StartCoroutine(Run(SetTraceAll(!traceOn), traceOn ? "Turning the flow trace off" : "Loading the flow speeds"));
        }

        IEnumerator SetTraceAll(bool on)
        {
            traceOn = on;
            int rp = CurrentRp;
            yield return left.SetTrace(api, frame, rp, on);
            yield return right.SetTrace(api, frame, rp, on && right.Frames != null);
            if (left.Frames != null) left.ShowAt(simT, false, 0);   // recolour the water at the moment shown
            if (right.Frames != null) right.ShowAt(simT, false, 0);
            var note = left.Trace ? left.TraceNote : right.TraceNote;
            status = !on ? "Flow trace off." : left.Velocity != null || right.Velocity != null
                ? $"Flow trace: the water coloured by speed, particles carried by it ({note}). Press Play to watch it change through the storm."
                : $"Flow trace: {note}.";
            traceShownTop = -1;
        }

        /// Every frame: move the particles on, at the storm time shown.
        void StepTrace()
        {
            bool any = false;
            float width = Mathf.Clamp(rigLeft.Distance * 0.0035f, 0.12f, 1.5f);   // readable zoomed out and in
            foreach (var v in new[] { left, right })
            {
                if (!traceOn || !v.Trace || v.Velocity == null || !v.Particles.Ready) continue;
                if (!v.Particles.gameObject.activeSelf) v.Particles.gameObject.SetActive(true);
                v.Particles.Step(simT, Time.unscaledDeltaTime, width);
                any = true;
            }
            if (traceLegend == null) return;
            Kit.Show(traceLegend, any);
            if (!any) return;
            var shown = left.Velocity != null ? left : right;
            float top = shown.TraceTop;
            if (!Mathf.Approximately(top, traceShownTop))
            {
                traceShownTop = top;
                traceTop.text = $"{top:0.00}+";
                traceMid.text = $"{top / 2:0.00}";
                traceNote.text = $"Fastest in this storm {shown.Velocity.MaxSpeed:0.00} m/s. White streaks ride the flow, shown faster than real.";
            }
        }

        /// The legend: a speed bar (m/s) like a model's velocity map, bottom left of the view.
        void BuildTraceLegend(VisualElement overlay)
        {
            traceLegend = new VisualElement();
            var s = traceLegend.style;
            s.position = Position.Absolute;
            s.left = 12;
            s.bottom = 12;
            s.width = 200;
            s.paddingLeft = s.paddingRight = 10;
            s.paddingTop = s.paddingBottom = 8;
            s.borderTopLeftRadius = s.borderTopRightRadius = s.borderBottomLeftRadius = s.borderBottomRightRadius = 6;
            s.backgroundColor = new Color(0.08f, 0.09f, 0.11f, 0.85f);
            var title = Text("Water speed (m/s)", "muted");
            title.style.color = new Color(0.92f, 0.94f, 0.97f);
            traceLegend.Add(title);
            var bar = new VisualElement();
            bar.style.flexDirection = FlexDirection.Row;
            bar.style.height = 12;
            bar.style.marginTop = 6;
            const int steps = 24;
            for (int i = 0; i < steps; i++)
            {
                var c = new VisualElement();
                c.style.flexGrow = 1;
                c.style.backgroundColor = FlowParticles.SpeedColour(i / (steps - 1f));
                bar.Add(c);
            }
            traceLegend.Add(bar);
            var ticks = new VisualElement();
            ticks.style.flexDirection = FlexDirection.Row;
            ticks.style.justifyContent = Justify.SpaceBetween;
            var zero = Text("0", "muted");
            traceMid = Text("", "muted");
            traceTop = Text("", "muted");
            foreach (var l in new[] { zero, traceMid, traceTop }) { l.style.color = new Color(0.85f, 0.88f, 0.92f); l.style.fontSize = 11; ticks.Add(l); }
            traceLegend.Add(ticks);
            traceNote = Text("", "muted");
            traceNote.style.whiteSpace = WhiteSpace.Normal;
            traceNote.style.fontSize = 11;
            traceNote.style.color = new Color(0.75f, 0.78f, 0.83f);
            traceNote.style.marginTop = 4;
            traceLegend.Add(traceNote);
            Kit.Show(traceLegend, false);
            overlay.Add(traceLegend);
        }
    }
}
