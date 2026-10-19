// Small building blocks for the workspace: icons (Lucide, white PNGs tinted by the theme), icon buttons, labels.
using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;

namespace SpongePark.UI
{
    public static class Kit
    {
        static readonly Dictionary<string, Texture2D> icons = new Dictionary<string, Texture2D>();

        public static Texture2D IconTexture(string name)
        {
            if (string.IsNullOrEmpty(name)) return null;
            if (!icons.TryGetValue(name, out var t)) icons[name] = t = Resources.Load<Texture2D>("UI/Icons/" + name);
            return t;
        }

        public static VisualElement Icon(string name, bool large = false)
        {
            var i = new VisualElement { pickingMode = PickingMode.Ignore };
            i.AddToClassList("icon");
            if (large) i.AddToClassList("icon--lg");
            SetIcon(i, name);
            return i;
        }

        public static void SetIcon(VisualElement i, string name)
        {
            var t = IconTexture(name);
            i.style.backgroundImage = t != null ? new StyleBackground(t) : StyleKeyword.None;
        }

        public static Button IconButton(string icon, string tooltip, Action onClick)
        {
            var b = new Button(onClick) { tooltip = tooltip };
            b.AddToClassList("ib");
            b.Add(Icon(icon));
            return b;
        }

        public static Label Label(string text, params string[] classes)
        {
            var l = new Label(text) { pickingMode = PickingMode.Ignore };
            foreach (var c in classes) l.AddToClassList(c);
            return l;
        }

        public static VisualElement Box(params string[] classes)
        {
            var e = new VisualElement();
            foreach (var c in classes) e.AddToClassList(c);
            return e;
        }

        public static void Show(VisualElement e, bool on) => e.style.display = on ? DisplayStyle.Flex : DisplayStyle.None;
    }
}
