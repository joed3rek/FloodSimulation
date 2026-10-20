// Smooth curves through the points the designer places, like a CAD spline drawn by fit points: the curve passes
// through every point. Centripetal Catmull-Rom, which does not overshoot or loop between close points.
using System.Collections.Generic;
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

        static Vector2 Mix(Vector2 a, Vector2 b, float ta, float tb, float t) => (tb - t) / (tb - ta) * a + (t - ta) / (tb - ta) * b;
    }
}
