// The survey drawing as a zoomable vector plan (UI Toolkit). Linework comes from the engine
// (/intake/geometry), is drawn once in plan space and moved with a transform, so panning and
// zooming are cheap; line widths are re-stroked once the zoom settles so lines stay thin.
// Wheel zooms about the cursor, drag pans, a click without dragging raises Clicked.
using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.UIElements;

namespace SpongePark
{
    public class PlanView : VisualElement
    {
        const float BaseSize = 2048f;          // plan-space size of the drawing's longer side (px at zoom 1)
        const int ChunkVertices = 3000;        // vertices per mesh-drawing element (keeps each mesh small)
        static readonly Color Faint = new Color32(0xC9, 0xC2, 0xB6, 0xFF);
        static readonly Color FaintPoint = new Color32(0xD6, 0xCF, 0xC4, 0xFF);
        static readonly Color Clay = new Color32(0xB5, 0x73, 0x3E, 0xFF);

        class Chunk : VisualElement
        {
            public string Layer;
            public List<Vector2[]> Lines = new List<Vector2[]>();
            public List<Vector2> Points = new List<Vector2>();
            public bool Highlight;
            public Func<float> Zoom;

            public Chunk()
            {
                pickingMode = PickingMode.Ignore;
                style.position = Position.Absolute;
                style.left = 0;
                style.top = 0;
                generateVisualContent += Draw;
            }

            void Draw(MeshGenerationContext ctx)
            {
                var p = ctx.painter2D;
                float z = Mathf.Max(Zoom(), 1e-4f);
                if (Lines.Count > 0)
                {
                    p.strokeColor = Highlight ? Clay : Faint;
                    p.lineWidth = (Highlight ? 2.0f : 0.7f) / z;
                    p.lineJoin = LineJoin.Bevel;
                    p.lineCap = LineCap.Butt;
                    p.BeginPath();
                    foreach (var l in Lines)
                    {
                        p.MoveTo(l[0]);
                        for (int i = 1; i < l.Length; i++) p.LineTo(l[i]);
                    }
                    p.Stroke();
                }
                if (Points.Count > 0)
                {
                    float r = (Highlight ? 3.5f : 1.2f) / z;
                    p.fillColor = Highlight ? Clay : FaintPoint;
                    p.BeginPath();
                    foreach (var q in Points)
                    {
                        p.MoveTo(new Vector2(q.x - r, q.y - r));
                        p.LineTo(new Vector2(q.x + r, q.y - r));
                        p.LineTo(new Vector2(q.x + r, q.y + r));
                        p.LineTo(new Vector2(q.x - r, q.y + r));
                        p.ClosePath();
                    }
                    p.Fill();
                }
            }
        }

        readonly VisualElement content;
        readonly List<Chunk> chunks = new List<Chunk>();
        readonly Dictionary<string, Rect> layerBounds = new Dictionary<string, Rect>();
        float k = 1, w, h;                     // plan px per drawing unit; plan size in px
        float zoom = 1;
        Vector2 offset;                        // screen position of the plan's top-left
        string highlighted;
        bool hasData, fitted, dragging, captured;
        Vector2 downPos, lastPos;
        IVisualElementScheduledItem restroke;

        /// Raised by a click on the plan that was not a drag.
        public event Action Clicked;
        float leftInset;

        /// Left part of the view covered by an overlay (a panel); fits keep clear of it, and changing it
        /// moves the plan so what was in the middle of the free area stays in the middle.
        public float LeftInset
        {
            get => leftInset;
            set
            {
                if (hasData && fitted) { offset.x += (value - leftInset) / 2; Apply(false); }
                leftInset = value;
            }
        }
        public bool HasData => hasData;
        public float Zoom => zoom;
        public Vector2 Offset => offset;

        public PlanView()
        {
            AddToClassList("plan");
            style.overflow = Overflow.Hidden;
            focusable = true;
            content = new VisualElement { pickingMode = PickingMode.Ignore };
            content.style.position = Position.Absolute;
            content.style.left = 0;
            content.style.top = 0;
            content.style.transformOrigin = new TransformOrigin(0, 0);
            Add(content);
            RegisterCallback<WheelEvent>(OnWheel);
            RegisterCallback<PointerDownEvent>(OnDown);
            RegisterCallback<PointerMoveEvent>(OnMove);
            RegisterCallback<PointerUpEvent>(OnUp);
            RegisterCallback<PointerCaptureOutEvent>(_ => captured = false);
            RegisterCallback<GeometryChangedEvent>(_ => { if (hasData && !fitted) ZoomExtents(); });
        }

        /// Loads the engine's geometry: {"extent": [w, h], "layers": {name: {"lines": [[x, y, ...]], "points": [x, y, ...]}}}.
        public void SetGeometry(JToken geo)
        {
            content.Clear();
            chunks.Clear();
            layerBounds.Clear();
            float ew = (float)geo["extent"][0], eh = (float)geo["extent"][1];
            k = BaseSize / Mathf.Max(ew, eh, 1e-6f);
            w = ew * k;
            h = eh * k;
            content.style.width = w;
            content.style.height = h;
            foreach (var prop in ((JObject)geo["layers"]).Properties())
            {
                var name = prop.Name;
                var xs = new List<float>();
                var ys = new List<float>();
                Chunk c = NewChunk(name);
                int n = 0;
                foreach (var line in prop.Value["lines"])
                {
                    var a = line.Values<float>().ToArray();
                    var v = new Vector2[a.Length / 2];
                    for (int i = 0; i < v.Length; i++) { v[i] = ToPlan(a[2 * i], a[2 * i + 1]); xs.Add(v[i].x); ys.Add(v[i].y); }
                    if (n + v.Length > ChunkVertices && n > 0) { c = NewChunk(name); n = 0; }
                    c.Lines.Add(v);
                    n += v.Length;
                }
                var pa = prop.Value["points"].Values<float>().ToArray();
                for (int i = 0; i + 1 < pa.Length; i += 2)
                {
                    var q = ToPlan(pa[i], pa[i + 1]);
                    c.Points.Add(q);
                    xs.Add(q.x);
                    ys.Add(q.y);
                }
                if (xs.Count > 0) layerBounds[name] = Bounds(xs, ys);
            }
            chunks.RemoveAll(ch => ch.Lines.Count == 0 && ch.Points.Count == 0);
            hasData = true;
            fitted = false;
            if (contentRect.width > 0) ZoomExtents();
        }

        Chunk NewChunk(string layer)
        {
            var c = new Chunk { Layer = layer, Zoom = () => zoom };
            c.style.width = w;
            c.style.height = h;
            chunks.Add(c);
            content.Add(c);
            return c;
        }

        Vector2 ToPlan(float x, float y) => new Vector2(x * k, h - y * k);

        /// The middle 96% of a layer's points, so a stray far-off object does not set the zoom.
        static Rect Bounds(List<float> xs, List<float> ys)
        {
            xs.Sort();
            ys.Sort();
            int lo = (int)(xs.Count * 0.02f), hi = Mathf.Max(lo, (int)(xs.Count * 0.98f) - 1);
            return Rect.MinMaxRect(xs[lo], ys[lo], xs[hi], ys[hi]);
        }

        // ------------------------------------------------------------ view
        public void Highlight(string layer)
        {
            if (layer == highlighted) return;
            foreach (var c in chunks)
            {
                bool on = layer != null && c.Layer == layer;
                if (on == c.Highlight) continue;
                c.Highlight = on;
                c.MarkDirtyRepaint();
                if (on) c.BringToFront();
            }
            highlighted = layer;
        }

        public void ZoomExtents() => FitRect(new Rect(0, 0, w, h));

        public void ZoomToLayer(string layer)
        {
            if (!layerBounds.TryGetValue(layer, out var r)) return;
            float min = 0.12f * Mathf.Max(w, h);   // keep some of the drawing around a small layer
            FitRect(new Rect(r.center.x - Mathf.Max(r.width, min) / 2, r.center.y - Mathf.Max(r.height, min) / 2,
                             Mathf.Max(r.width, min), Mathf.Max(r.height, min)));
        }

        public void ZoomBy(float factor) => ZoomAbout(new Vector2(LeftInset + (contentRect.width - LeftInset) / 2, contentRect.height / 2), factor);

        void FitRect(Rect r)
        {
            float vw = contentRect.width - LeftInset, vh = contentRect.height;
            if (vw <= 0 || vh <= 0 || !hasData) return;
            zoom = 0.9f * Mathf.Min(vw / Mathf.Max(r.width, 1), vh / Mathf.Max(r.height, 1));
            offset = new Vector2(LeftInset + vw / 2, vh / 2) - r.center * zoom;
            fitted = true;
            Apply(true);
        }

        void ZoomAbout(Vector2 screen, float factor)
        {
            float fit = Mathf.Min((contentRect.width - LeftInset) / Mathf.Max(w, 1), contentRect.height / Mathf.Max(h, 1));
            float z = Mathf.Clamp(zoom * factor, 0.3f * fit, 400f * fit);
            var planPt = (screen - offset) / zoom;
            zoom = z;
            offset = screen - planPt * zoom;
            Apply(true);
        }

        void Apply(bool zoomChanged)
        {
            content.style.translate = new Translate(offset.x, offset.y);
            content.style.scale = new Scale(new Vector3(zoom, zoom, 1));
            if (!zoomChanged) return;
            // re-stroke at the new zoom once it settles, so lines keep their screen width
            restroke?.Pause();
            restroke = schedule.Execute(() => { foreach (var c in chunks) c.MarkDirtyRepaint(); }).StartingIn(120);
        }

        // ------------------------------------------------------------ input
        void OnWheel(WheelEvent e)
        {
            if (!hasData) return;
            ZoomAbout(e.localMousePosition, e.delta.y > 0 ? 1 / 1.2f : 1.2f);
            e.StopPropagation();
        }

        void OnDown(PointerDownEvent e)
        {
            if (e.button != 0 && e.button != 2) return;
            downPos = lastPos = e.localPosition;
            dragging = false;
            captured = true;
            this.CapturePointer(e.pointerId);
        }

        void OnMove(PointerMoveEvent e)
        {
            if (!captured || !this.HasPointerCapture(e.pointerId)) return;
            Vector2 p = e.localPosition;
            if (!dragging && (p - downPos).sqrMagnitude > 16) dragging = true;
            if (dragging)
            {
                offset += p - lastPos;
                Apply(false);
            }
            lastPos = p;
        }

        void OnUp(PointerUpEvent e)
        {
            if (!this.HasPointerCapture(e.pointerId)) return;
            this.ReleasePointer(e.pointerId);
            captured = false;
            if (!dragging) Clicked?.Invoke();
            dragging = false;
        }
    }
}
