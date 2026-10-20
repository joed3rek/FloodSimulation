// The loading screen: covers the window while the engine starts or works on a long job, so the user
// sees that something is happening (a turning ring, what is being done, and for how long).
using UnityEngine;
using UnityEngine.UIElements;

namespace SpongePark.UI
{
    public class Loading
    {
        public readonly VisualElement Root;
        readonly VisualElement ring;
        readonly Label title, detail, elapsed, hint;
        float since = -1, angle;

        public Loading()
        {
            Root = Kit.Box("loading");
            var card = Kit.Box("loading-card");
            Root.Add(card);
            ring = Kit.Box("loading-ring");
            card.Add(ring);
            title = Kit.Label("", "loading-title");
            detail = Kit.Label("", "loading-detail");
            elapsed = Kit.Label("", "loading-elapsed");
            hint = Kit.Label("", "loading-hint");
            card.Add(title);
            card.Add(detail);
            card.Add(elapsed);
            card.Add(hint);
            Root.style.display = DisplayStyle.None;
        }

        public bool Visible => since >= 0;

        /// Shows (or updates) the screen; call every frame while the work lasts. Null title hides it.
        public void Set(string what, string step = null, string note = null)
        {
            if (what == null)
            {
                if (since >= 0) { since = -1; Root.style.display = DisplayStyle.None; }
                return;
            }
            if (since < 0) { since = Time.realtimeSinceStartup; Root.style.display = DisplayStyle.Flex; Root.BringToFront(); }
            title.text = what;
            detail.text = step ?? "";
            Kit.Show(detail, !string.IsNullOrEmpty(step));
            hint.text = note ?? "";
            Kit.Show(hint, !string.IsNullOrEmpty(note));
            int s = (int)(Time.realtimeSinceStartup - since);
            elapsed.text = s < 3 ? "The engine is running…" : $"The engine is running · {s / 60}:{s % 60:00}";
            angle = (angle + Time.unscaledDeltaTime * 300) % 360;
            ring.style.rotate = new Rotate(angle);
        }
    }
}
