// Smooth curves through the points the designer places, like a CAD spline drawn by fit points: the curve passes
// through every point. Centripetal Catmull-Rom, which does not overshoot or loop between close points.
using System.Collections.Generic;
using System.Linq;
using UnityEngine;

namespace SpongePark
{
    public static class Spline
    {
        /// The curve through pts, as points about step metres apart (the given points included).
        /// closed: back to the first point (an outline; the first point is not repeated at the end).
        public static List<Vector2> Through(IList<Vector2> pts, bool closed, float step = 0.5f)
        {
            var outPts = new List<Vector2>();
            int n = pts.Count;
            if (n < 3) { outPts.AddRange(pts); return outPts; }
            int segs = closed ? n : n - 1;
            for (int i = 0; i < segs; i++)
            {
                Vector2 p1 = pts[i], p2 = pts[(i + 1) % n];
                // the neighbours; an open curve's ends are mirrored so it starts and ends straight on
                Vector2 p0 = closed || i > 0 ? pts[(i - 1 + n) % n] : 2 * p1 - p2;
                Vector2 p3 = closed || i + 2 < n ? pts[(i + 2) % n] : 2 * p2 - p1;
                int k = Mathf.Clamp(Mathf.CeilToInt((p2 - p1).magnitude / step), 1, 400);
                for (int j = 0; j < k; j++) outPts.Add(Point(p0, p1, p2, p3, (float)j / k));
            }
            if (!closed) outPts.Add(pts[n - 1]);
            return outPts;
        }

        static Vector2 Point(Vector2 p0, Vector2 p1, Vector2 p2, Vector2 p3, float u)
        {
            // centripetal parametrisation (alpha 0.5), Barry-Goldman form
            float t0 = 0;
            float t1 = t0 + Knot(p0, p1);
            float t2 = t1 + Knot(p1, p2);
            float t3 = t2 + Knot(p2, p3);
            float t = Mathf.Lerp(t1, t2, u);
            Vector2 a1 = Mix(p0, p1, t0, t1, t), a2 = Mix(p1, p2, t1, t2, t), a3 = Mix(p2, p3, t2, t3, t);
            Vector2 b1 = Mix(a1, a2, t0, t2, t), b2 = Mix(a2, a3, t1, t3, t);
            return Mix(b1, b2, t1, t2, t);
        }

        static float Knot(Vector2 a, Vector2 b) => Mathf.Max(Mathf.Sqrt((b - a).magnitude), 1e-4f);

        // ---- the same curve for lines found on the ground: x, height, z (plan is x and z) and w, a value carried along

        static float Plan(Vector4 d) => Mathf.Sqrt(d.x * d.x + d.z * d.z);

        /// The curve through pts in plan, about step metres apart; height and w follow along.
        public static List<Vector4> Through(IList<Vector4> pts, bool closed, float step)
        {
            var outPts = new List<Vector4>();
            int n = pts.Count;
            if (n < 3) { outPts.AddRange(pts); return outPts; }
            int segs = closed ? n : n - 1;
            for (int i = 0; i < segs; i++)
            {
                Vector4 p1 = pts[i], p2 = pts[(i + 1) % n];
                Vector4 p0 = closed || i > 0 ? pts[(i - 1 + n) % n] : 2 * p1 - p2;
                Vector4 p3 = closed || i + 2 < n ? pts[(i + 2) % n] : 2 * p2 - p1;
                int k = Mathf.Clamp(Mathf.CeilToInt(Plan(p2 - p1) / step), 1, 400);
                for (int j = 0; j < k; j++) outPts.Add(Point(p0, p1, p2, p3, (float)j / k));
            }
            if (!closed) outPts.Add(pts[n - 1]);
            return outPts;
        }

        static Vector4 Point(Vector4 p0, Vector4 p1, Vector4 p2, Vector4 p3, float u)
        {
            float t0 = 0;
            float t1 = t0 + Knot(p0, p1);
            float t2 = t1 + Knot(p1, p2);
            float t3 = t2 + Knot(p2, p3);
            float t = Mathf.Lerp(t1, t2, u);
            Vector4 a1 = Mix(p0, p1, t0, t1, t), a2 = Mix(p1, p2, t1, t2, t), a3 = Mix(p2, p3, t2, t3, t);
            Vector4 b1 = Mix(a1, a2, t0, t2, t), b2 = Mix(a2, a3, t1, t3, t);
            return Mix(b1, b2, t1, t2, t);
        }

        static float Knot(Vector4 a, Vector4 b) => Mathf.Max(Mathf.Sqrt(Plan(b - a)), 1e-4f);

        static Vector4 Mix(Vector4 a, Vector4 b, float ta, float tb, float t) => (tb - t) / (tb - ta) * a + (t - ta) / (tb - ta) * b;

        /// The few points that carry a line's shape (Douglas-Peucker in plan): every point dropped lies within tol of
        /// the line through those kept, like the fit points of a CAD spline. A closed line is split at its farthest point.
        public static List<Vector4> FitPoints(IList<Vector4> pts, float tol, bool closed)
        {
            int n = pts.Count;
            if (n < 3) return new List<Vector4>(pts);
            if (closed)
            {
                int far = 0;
                for (int i = 1; i < n; i++) if (Plan(pts[i] - pts[0]) > Plan(pts[far] - pts[0])) far = i;
                var a = FitPoints(Slice(pts, 0, far), tol, false);
                var b = FitPoints(Slice(pts, far, n).Concat(new[] { pts[0] }).ToList(), tol, false);
                a.RemoveAt(a.Count - 1);
                b.RemoveAt(b.Count - 1);
                a.AddRange(b);
                return a;
            }
            var keep = new bool[n];
            keep[0] = keep[n - 1] = true;
            var todo = new Stack<(int, int)>();
            todo.Push((0, n - 1));
            while (todo.Count > 0)
            {
                var (s, e) = todo.Pop();
                float worst = 0;
                int at = -1;
                for (int i = s + 1; i < e; i++)
                {
                    float d = PlanDistance(pts[i], pts[s], pts[e]);
                    if (d > worst) { worst = d; at = i; }
                }
                if (at < 0 || worst <= tol) continue;
                keep[at] = true;
                todo.Push((s, at));
                todo.Push((at, e));
            }
            var outPts = new List<Vector4>();
            for (int i = 0; i < n; i++) if (keep[i]) outPts.Add(pts[i]);
            return outPts;
        }

        static List<Vector4> Slice(IList<Vector4> pts, int from, int to)
        {
            var r = new List<Vector4>();
            for (int i = from; i <= Mathf.Min(to, pts.Count - 1); i++) r.Add(pts[i]);
            return r;
        }

        static float PlanDistance(Vector4 p, Vector4 a, Vector4 b)
        {
            var ab = new Vector2(b.x - a.x, b.z - a.z);
            var ap = new Vector2(p.x - a.x, p.z - a.z);
            float t = ab.sqrMagnitude > 0 ? Mathf.Clamp01(Vector2.Dot(ap, ab) / ab.sqrMagnitude) : 0;
            return (ap - ab * t).magnitude;
        }

        static Vector2 Mix(Vector2 a, Vector2 b, float ta, float tb, float t) => (tb - t) / (tb - ta) * a + (t - ta) / (tb - ta) * b;
    }
}
