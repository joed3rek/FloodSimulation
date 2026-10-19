// The lawns planted with the low-poly packs' grass, flowers, bushes and rocks, and bushes along the fence, kept off
// paths, roads, buildings, ponds and tree trunks; lily pads on the ponds. Display only: the ground model and the
// flood model do not see them. Each spot is chosen from its position, so a park looks the same every time.
using System.Collections.Generic;
using UnityEngine;

namespace SpongePark
{
    public class LowPolyDressing
    {
        const float Cell = 1f;          // m, the grid that records what is kept clear
        const float Step = 9f;          // m between planting spots on the lawn (sparse: the ground stays readable)
        const float FenceStep = 7f;     // m between bushes along the fence
        readonly SiteFrame frame;
        readonly System.Func<float, float, float> ground;
        readonly System.Func<float, float, bool> inPark;
        readonly HashSet<long> clear = new HashSet<long>();
        readonly List<Vector2> trunks = new List<Vector2>(), fence = new List<Vector2>(), pond = new List<Vector2>();
        float x0 = float.MaxValue, y0 = float.MaxValue, x1 = float.MinValue, y1 = float.MinValue;

        public LowPolyDressing(SiteFrame frame, System.Func<float, float, float> ground, System.Func<float, float, bool> inPark)
        {
            this.frame = frame;
            this.ground = ground;
            this.inPark = inPark;
        }

        static long Key(int i, int j) => ((long)i << 32) ^ (uint)j;
        void Mark(float x, float y) => clear.Add(Key(Mathf.FloorToInt(x / Cell), Mathf.FloorToInt(y / Cell)));
        bool Clear(float x, float y) => clear.Contains(Key(Mathf.FloorToInt(x / Cell), Mathf.FloorToInt(y / Cell)));

        void Grow(float x, float y)
        {
            x0 = Mathf.Min(x0, x); y0 = Mathf.Min(y0, y); x1 = Mathf.Max(x1, x); y1 = Mathf.Max(y1, y);
        }

        /// A surface (triangles over survey xyz) or a closed outline (tri null: buildings, pond edges) to keep clear.
        public void KeepClear(float[] xyz, int[] tri, bool water)
        {
            int n = xyz.Length / 3;
            for (int k = 0; k < n; k++) Grow(xyz[3 * k], xyz[3 * k + 1]);
            if (tri != null)
            {
                for (int t = 0; t + 2 < tri.Length; t += 3)
                {
                    var a = new Vector2(xyz[3 * tri[t]], xyz[3 * tri[t] + 1]);
                    var b = new Vector2(xyz[3 * tri[t + 1]], xyz[3 * tri[t + 1] + 1]);
                    var c = new Vector2(xyz[3 * tri[t + 2]], xyz[3 * tri[t + 2] + 1]);
                    FillTriangle(a, b, c, water);
                }
                return;
            }
            var ring = new List<Vector2>(n);
            for (int k = 0; k < n; k++) ring.Add(new Vector2(xyz[3 * k], xyz[3 * k + 1]));
            if (ring.Count < 3) return;
            float bx0 = float.MaxValue, by0 = float.MaxValue, bx1 = float.MinValue, by1 = float.MinValue;
            foreach (var q in ring) { bx0 = Mathf.Min(bx0, q.x); by0 = Mathf.Min(by0, q.y); bx1 = Mathf.Max(bx1, q.x); by1 = Mathf.Max(by1, q.y); }
            for (float x = bx0 - Cell; x <= bx1 + Cell; x += Cell)
                for (float y = by0 - Cell; y <= by1 + Cell; y += Cell)
                    if (Inside(ring, x, y)) Mark(x, y);
            foreach (var q in ring) Mark(q.x, q.y);
        }

        void FillTriangle(Vector2 a, Vector2 b, Vector2 c, bool water)
        {
            float bx0 = Mathf.Min(a.x, Mathf.Min(b.x, c.x)), bx1 = Mathf.Max(a.x, Mathf.Max(b.x, c.x));
            float by0 = Mathf.Min(a.y, Mathf.Min(b.y, c.y)), by1 = Mathf.Max(a.y, Mathf.Max(b.y, c.y));
            for (float x = Mathf.Floor(bx0 / Cell) * Cell; x <= bx1 + Cell; x += Cell)
                for (float y = Mathf.Floor(by0 / Cell) * Cell; y <= by1 + Cell; y += Cell)
                {
                    var p = new Vector2(x + Cell / 2, y + Cell / 2);
                    if (!InTriangle(p, a, b, c)) continue;
                    Mark(p.x, p.y);
                    if (water && Hash(p.x, p.y, 9) < 0.02f) pond.Add(p);
                }
            Mark(a.x, a.y); Mark(b.x, b.y); Mark(c.x, c.y);
        }

        public void Tree(float x, float y) { trunks.Add(new Vector2(x, y)); Grow(x, y); }

        /// A fence line (survey xyz): bushes along its inside.
        public void Fence(float[] xyz)
        {
            float carry = 0;
            for (int k = 0; k + 5 < xyz.Length; k += 3)
            {
                var a = new Vector2(xyz[k], xyz[k + 1]);
                var b = new Vector2(xyz[k + 3], xyz[k + 4]);
                float len = (b - a).magnitude;
                var dir = len > 0 ? (b - a) / len : Vector2.right;
                var side = new Vector2(-dir.y, dir.x) * 1.6f;
                for (float s = carry; s < len; s += FenceStep)
                {
                    var p = a + dir * s;
                    fence.Add(inPark(p.x + side.x, p.y + side.y) ? p + side : p - side);   // on the park's side
                }
                carry = Mathf.Repeat(carry - len, FenceStep);
            }
        }

        public void Plant(LowPolyKit kit, Transform parent, int layer)
        {
            if (x0 > x1) return;
            int seed = 0;
            for (float x = Mathf.Floor(x0 / Step) * Step; x <= x1; x += Step)
                for (float y = Mathf.Floor(y0 / Step) * Step; y <= y1; y += Step)
                {
                    float px = x + (Hash(x, y, 1) - 0.5f) * Step * 0.9f, py = y + (Hash(x, y, 2) - 0.5f) * Step * 0.9f;
                    if (!inPark(px, py) || Clear(px, py) || NearTrunk(px, py)) continue;
                    float pick = Hash(px, py, 3);
                    GameObject[] set = pick < 0.10f ? kit.grass : pick < 0.13f ? kit.flowers : pick < 0.15f ? kit.bushes
                                     : pick < 0.16f ? kit.rocks : null;
                    if (!LowPolyKit.Has(set)) continue;
                    float size = set == kit.bushes ? 1.6f : set == kit.rocks ? 0.8f : 0;
                    Put(set, px, py, size, (int)(Hash(px, py, 4) * 1e6f) + seed++, parent, layer);
                }
            if (LowPolyKit.Has(kit.bushes))
                foreach (var p in fence)
                    if (inPark(p.x, p.y) && !Clear(p.x, p.y) && Hash(p.x, p.y, 5) < 0.3f)
                        Put(kit.bushes, p.x, p.y, 1.8f + Hash(p.x, p.y, 6), (int)(Hash(p.x, p.y, 7) * 1e6f), parent, layer);
            if (LowPolyKit.Has(kit.lilypads))
                foreach (var p in pond)
                    Put(kit.lilypads, p.x, p.y, 1.2f, (int)(Hash(p.x, p.y, 8) * 1e6f), parent, layer, 0.05f);
        }

        void Put(GameObject[] set, float x, float y, float size, int seed, Transform parent, int layer, float lift = 0)
        {
            float z = ground(x, y);
            if (float.IsNaN(z)) return;
            var go = LowPolyKit.Place(set, frame.World(x, y, z) + Vector3.up * lift, size, seed, parent, layer);
            foreach (var r in go.GetComponentsInChildren<Renderer>()) r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
        }

        bool NearTrunk(float x, float y)
        {
            foreach (var t in trunks)
                if ((t.x - x) * (t.x - x) + (t.y - y) * (t.y - y) < 2.5f * 2.5f) return true;
            return false;
        }

        static float Hash(float x, float y, int k) => Mathf.Abs(Mathf.Sin(x * 12.9898f + y * 78.233f + k * 37.719f) * 43758.5453f) % 1f;

        static bool InTriangle(Vector2 p, Vector2 a, Vector2 b, Vector2 c)
        {
            float d1 = (p.x - b.x) * (a.y - b.y) - (a.x - b.x) * (p.y - b.y);
            float d2 = (p.x - c.x) * (b.y - c.y) - (b.x - c.x) * (p.y - c.y);
            float d3 = (p.x - a.x) * (c.y - a.y) - (c.x - a.x) * (p.y - a.y);
            bool neg = d1 < 0 || d2 < 0 || d3 < 0, pos = d1 > 0 || d2 > 0 || d3 > 0;
            return !(neg && pos);
        }

        static bool Inside(List<Vector2> ring, float x, float y)
        {
            bool inside = false;
            for (int i = 0, j = ring.Count - 1; i < ring.Count; j = i++)
                if ((ring[i].y > y) != (ring[j].y > y) && x < (ring[j].x - ring[i].x) * (y - ring[i].y) / (ring[j].y - ring[i].y) + ring[i].x)
                    inside = !inside;
            return inside;
        }
    }
}
