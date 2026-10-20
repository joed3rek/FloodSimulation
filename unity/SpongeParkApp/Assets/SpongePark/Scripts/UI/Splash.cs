// The opening animation, after Unity's own splash: the landscape fades in, its terrain contours sweep in over
// it, the title rises, and the real start-up steps tick off one at a time. It leaves as soon as the app is
// ready (and the animation has had about a second to read); it never stays once ready.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using UnityEngine;
using UnityEngine.UIElements;

namespace SpongePark.UI
{
    public class Splash
    {
        public readonly VisualElement Root;
        public bool Hold;                   // screenshots: stay up
        public float FreezeAt = -1;         // screenshots: show the timeline at this moment
        public bool Gone { get; private set; }
        readonly VisualElement land, contourClip, contours, words, panel, fill;
        readonly Label count;
        readonly List<(string id, VisualElement row, Label text)> rows = new List<(string, VisualElement, Label)>();
        readonly HashSet<string> done = new HashSet<string>();
        int shown;                          // steps ticked on screen: in order, one at a time, each only once really done
        float lastTick = -10;
        float start = -1;                   // the clock starts at the first frames actually shown
        int frames;
        readonly bool still;                // reduced motion (Windows: animations turned off)
        bool leaveAsked;
        float leaving = -1;
        const float MinShow = 1.3f, FadeOut = 0.45f, TickGap = 0.28f;

        public Splash(IEnumerable<(string id, string text)> stages)
        {
            still = ReducedMotion();
            Root = Kit.Box("splash");

            // the landscape, then its contour lines over it (the same picture with contours, revealed by a sweep)
            land = Kit.Box("splash-land");
            land.style.backgroundImage = new StyleBackground(Resources.Load<Texture2D>("UI/Landing/splash"));
            Root.Add(land);
            contourClip = Kit.Box("splash-contour-clip");
            contours = Kit.Box("splash-land", "splash-contours");
            contours.style.backgroundImage = new StyleBackground(Resources.Load<Texture2D>("UI/Landing/splash_contours"));
            contourClip.Add(contours);
            Root.Add(contourClip);

            words = Kit.Box("splash-words");
            var eyebrow = Kit.Box("splash-eyebrow-row");
            eyebrow.Add(Kit.Label(Spaced("NATURE-BASED SOLUTIONS"), "splash-eyebrow"));
            eyebrow.Add(Kit.Box("splash-rule"));
            words.Add(eyebrow);
            words.Add(Kit.Label("Sponge Park", "splash-title"));
            words.Add(Kit.Label("Designer", "splash-title", "splash-title--second"));   // two labels: no line-height in USS
            words.Add(Kit.Label("Plan, design and visualise resilient parks, wetlands and urban landscapes.", "splash-sub"));

            var steps = Kit.Box("splash-steps");
            steps.Add(Kit.Label("Initialising workspace…", "splash-status"));
            var bar = Kit.Box("splash-bar-row");
            var track = Kit.Box("splash-track");
            fill = Kit.Box("splash-fill");
            track.Add(fill);
            bar.Add(track);
            count = Kit.Label("", "splash-count");
            bar.Add(count);
            steps.Add(bar);
            foreach (var (id, text) in stages)
            {
                var row = Kit.Box("splash-step");
                var dot = Kit.Box("splash-dot");
                dot.Add(Kit.Icon("check"));
                row.Add(dot);
                var l = Kit.Label(text, "splash-step-text");
                row.Add(l);
                steps.Add(row);
                rows.Add((id, row, l));
            }
            words.Add(steps);
            Root.Add(words);

            panel = Kit.Box("splash-panel");
            var thumb = Kit.Box("splash-thumb");
            thumb.style.backgroundImage = new StyleBackground(Resources.Load<Texture2D>("UI/Landing/splash_thumb"));
            panel.Add(thumb);
            panel.Add(Kit.Box("splash-divider"));
            var fact = Kit.Box("splash-fact");
            fact.Add(Kit.Label(Spaced("DID YOU KNOW?"), "splash-fact-head"));
            fact.Add(Kit.Label("Sponge parks use natural systems to manage stormwater, restore ecosystems and create healthier cities.", "splash-fact-text"));
            panel.Add(fact);
            Root.Add(panel);

            // laptop screens: the words and the panel shrink with the window's height (designed at 1080); the
            // contour picture keeps the landscape's size so the sweep lines up with it
            words.style.transformOrigin = new TransformOrigin(0, 0);
            panel.style.transformOrigin = new TransformOrigin(0, Length.Percent(100));
            Root.RegisterCallback<GeometryChangedEvent>(ev =>
            {
                float s = Mathf.Clamp(ev.newRect.height / 1080f, 0.6f, 1.15f);
                words.style.scale = new Scale(new Vector3(s, s, 1));
                panel.style.scale = new Scale(new Vector3(s, s, 1));
                words.style.left = 80 * s;
                panel.style.left = 78 * s;
                panel.style.bottom = 84 * s;
                contours.style.width = ev.newRect.width;
                contours.style.height = ev.newRect.height;
            });
            Show();
            Apply(0);
            Root.schedule.Execute(Tick).Every(0);
        }

        /// A start-up step has finished. Its tick appears in turn, after the ones before it.
        public void Done(string id) => done.Add(id);

        /// A step that is still running when the splash leaves keeps going in the background; say so.
        public void Note(string id, string text)
        {
            foreach (var r in rows) if (r.id == id) r.text.text = text;
        }

        /// Leave once every finished step has been ticked on screen (fades out); never waits for unfinished ones.
        public void Leave() => leaveAsked = true;

        void Show()
        {
            for (int i = 0; i < rows.Count; i++)
            {
                rows[i].row.EnableInClassList("splash-step--done", i < shown);
                rows[i].row.EnableInClassList("splash-step--current", i == shown);
            }
            int pct = Mathf.RoundToInt(100f * shown / Mathf.Max(1, rows.Count));
            fill.style.width = Length.Percent(pct);
            count.text = pct + "%";
        }

        void Tick()
        {
            if (Gone) return;
            float now = Time.realtimeSinceStartup;
            if (start < 0)   // the first frames after start-up are slow (fonts, shaders): the animation waits for them
            {
                if (++frames < 3) return;
                start = now;
            }
            float t = FreezeAt >= 0 ? FreezeAt : now - start;
            Apply(t);
            // the next tick, if its step is done and the last one has had its moment (and the title is up)
            if (shown < rows.Count && done.Contains(rows[shown].id) && now - lastTick >= (still ? 0 : TickGap) && t >= (still ? 0 : 0.7f))
            {
                shown++;
                lastTick = now;
                Show();
            }
            bool ticked = shown >= rows.Count || !done.Contains(rows[shown].id);   // nothing finished is still waiting for its tick
            if (leaveAsked && ticked && leaving < 0) leaving = Mathf.Max(now + (still ? 0 : 0.25f), start + (still ? 0.3f : MinShow));
            if (leaving >= 0 && !Hold && now >= leaving)
            {
                float k = Mathf.Clamp01((now - leaving) / FadeOut);
                Root.style.opacity = 1 - Ease(k);
                if (k >= 1) { Gone = true; Root.RemoveFromHierarchy(); }
            }
        }

        /// The timeline: landscape 0-0.8 s, contours sweep 0.2-1.2 s, title 0.5-1.1 s, panel 0.9-1.4 s.
        void Apply(float t)
        {
            if (still) t = 10;   // reduced motion: everything in place, no movement
            float Phase(float a, float b) => Ease(Mathf.Clamp01((t - a) / (b - a)));
            float l = Phase(0f, 0.8f);
            land.style.opacity = l;
            land.style.translate = new Translate(Length.Pixels((1 - l) * 20), 0);
            float c = Phase(0.2f, 1.2f);
            // the sweep runs ahead of the fade, so its edge stays faint and is off screen before the lines are full
            contourClip.style.width = Length.Percent(Mathf.Min(c * 125, 100));
            contourClip.style.opacity = c * c;
            contours.style.translate = new Translate(Length.Pixels((1 - l) * 20), 0);
            float w = Phase(0.5f, 1.1f);
            words.style.opacity = w;
            words.style.translate = new Translate(0, Length.Pixels((1 - w) * 14));
            float p = Phase(0.9f, 1.4f);
            panel.style.opacity = p;
            panel.style.translate = new Translate(0, Length.Pixels((1 - p) * 12));
        }

        static float Ease(float x) => 1 - Mathf.Pow(1 - x, 3);

        /// Small capitals spread out (thin spaces between letters; USS letter-spacing is not applied to these fonts).
        public static string Spaced(string s) => string.Join(Thin, s.ToCharArray()).Replace(Thin + " " + Thin, Thin + Thin + Thin + " ");
        const string Thin = " ";

        // Windows "Show animations in Windows" off = reduced motion
        [DllImport("user32.dll")] static extern bool SystemParametersInfo(uint action, uint param, ref bool value, uint ini);

        static bool ReducedMotion()
        {
            if (Array.IndexOf(Environment.GetCommandLineArgs(), "-spReducedMotion") >= 0) return true;
#if UNITY_STANDALONE_WIN && !UNITY_EDITOR
            try
            {
                bool on = true;
                if (SystemParametersInfo(0x1042, 0, ref on, 0)) return !on;   // SPI_GETCLIENTAREAANIMATION
            }
            catch (Exception) { }
#endif
            return false;
        }
    }
}
