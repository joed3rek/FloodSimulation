// Flow trace (Simulate): particles carried by the 2D flood's own velocities, each leaving a fading trail, over the
// water coloured by speed — the way wind maps show the wind. The velocities come from the flood run (the engine
// keeps them with every frame); particles are let go where the water is moving at the time shown and ride its
// surface. On screen they move faster than the water (a fixed multiple of its speed), so the pattern can be read.
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace SpongePark
{
    public class FlowParticles : MonoBehaviour
    {
        public const float MovingFrom = 0.003f;  // m/s: slower water is treated as still (sheet flow over a lawn runs at cm/s)
        const int Trail = 12;                     // points kept per particle
        const float Life = 3.5f;                  // s on screen, more or less

        VelocityFrames field;
        WaterView water;
        TerrainView terrain;
        SiteFrame frame;
        Mesh mesh;
        Vector3[] verts;
        Color[] cols;
        int[] tris;
        Vector2[] pos;                // survey x, y of each particle's head
        Vector2[,] trail;             // its last points, newest at [p, 0]
        float[,] trailY;              // the view height of each, worked out once when the point is added
        int[] filled;                 // how many trail points it has so far
        float[] age, life;
        readonly List<int> moving = new List<int>();   // cells where the water moves, at the frame last looked at
        int movingFrame = -2;
        System.Random rng = new System.Random(7);
        public int Count { get; private set; }

        public static FlowParticles Create(string name, Transform parent, int layer)
        {
            var go = new GameObject(name) { layer = layer };
            go.transform.SetParent(parent, false);
            var p = go.AddComponent<FlowParticles>();
            go.AddComponent<MeshFilter>();
            var mr = go.AddComponent<MeshRenderer>();
            mr.sharedMaterial = new Material(Shader.Find("SpongePark/VertexLitAlpha")) { renderQueue = 3150 };   // over the water
            mr.shadowCastingMode = ShadowCastingMode.Off;
            go.SetActive(false);
            return p;
        }

        /// The speed colour map: red when still, through yellow, green, cyan and blue, to purple and magenta at top (t 1).
        public static Color SpeedColour(float t, float alpha = 1f)
        {
            t = Mathf.Clamp01(t);
            Color[] stops =
            {
                new Color(0.86f, 0.10f, 0.10f), new Color(0.96f, 0.50f, 0.10f), new Color(0.98f, 0.88f, 0.15f),
                new Color(0.35f, 0.85f, 0.25f), new Color(0.15f, 0.85f, 0.85f), new Color(0.15f, 0.45f, 0.95f),
                new Color(0.25f, 0.15f, 0.85f), new Color(0.55f, 0.10f, 0.75f), new Color(0.90f, 0.10f, 0.55f),
            };
            float f = t * (stops.Length - 1);
            int i = Mathf.Min((int)f, stops.Length - 2);
            var c = Color.Lerp(stops[i], stops[i + 1], f - i);
            c.a = alpha;
            return c;
        }

        public void Build(VelocityFrames v, WaterView w, TerrainView t, SiteFrame f)
        {
            field = v; water = w; terrain = t; frame = f;
            movingFrame = -2;
            int cells = v.Rows * v.Cols;
            Count = Mathf.Clamp(cells / 12, 600, 4000);   // more on a bigger site, never so many it is a blur
            pos = new Vector2[Count];
            trail = new Vector2[Count, Trail];
            trailY = new float[Count, Trail];
            filled = new int[Count];
            age = new float[Count];
            life = new float[Count];
            int segs = Count * (Trail - 1);
            verts = new Vector3[segs * 4];
            cols = new Color[segs * 4];
            tris = new int[segs * 6];
            for (int s = 0; s < segs; s++)
            {
                int a = s * 4, b = s * 6;
                tris[b] = a; tris[b + 1] = a + 1; tris[b + 2] = a + 2;
                tris[b + 3] = a; tris[b + 4] = a + 2; tris[b + 5] = a + 3;
            }
            mesh = new Mesh { indexFormat = IndexFormat.UInt32 };
            mesh.MarkDynamic();
            mesh.vertices = verts;
            mesh.colors = cols;
            mesh.normals = Normals(verts.Length);
            mesh.triangles = tris;
            GetComponent<MeshFilter>().sharedMesh = mesh;
            for (int p = 0; p < Count; p++) { life[p] = 0; age[p] = 1; }   // all let go on the first step
        }

        static Vector3[] Normals(int n)
        {
            var a = new Vector3[n];
            for (int i = 0; i < n; i++) a[i] = Vector3.up;
            return a;
        }

        public bool Ready => field != null && mesh != null;

        /// Move the particles on by dt seconds of screen time, at storm time t; width: the trail's width in the view.
        public void Step(float t, float dt, float width)
        {
            if (!Ready) return;
            field.At(t);
            if (field.FrameIndex != movingFrame)   // where to let particles go: the water moving at this time
            {
                movingFrame = field.FrameIndex;
                moving.Clear();
                for (int k = 0; k < field.Speed.Length; k++)
                    if (field.Speed[k] >= MovingFrom) moving.Add(k);
            }
            // a fixed multiple of the water's speed: the faster water (95th percentile) crosses about 6 cells a second
            float scale = 6f * field.Cell / Mathf.Max(field.P95Speed, 0.05f);
            float top = Mathf.Max(field.P95Speed * 1.3f, 0.1f);
            dt = Mathf.Min(dt, 0.05f);
            int seg = 0;
            for (int p = 0; p < Count; p++)
            {
                age[p] += dt;
                bool alive = age[p] < life[p];
                float u = 0, v = 0;
                if (alive && !(field.Sample(pos[p].x, pos[p].y, out u, out v) && u * u + v * v >= MovingFrom * MovingFrom))
                    alive = false;
                if (!alive && !Spawn(p)) { Hide(ref seg, p); continue; }
                if (alive)
                {
                    pos[p] += new Vector2(u, v) * (scale * dt);
                    for (int i = Mathf.Min(filled[p], Trail - 1); i > 0; i--) { trail[p, i] = trail[p, i - 1]; trailY[p, i] = trailY[p, i - 1]; }
                    trail[p, 0] = pos[p];
                    trailY[p, 0] = HeightAt(pos[p]);
                    filled[p] = Mathf.Min(filled[p] + 1, Trail);
                }
                float speed = Mathf.Sqrt(u * u + v * v);
                float fade = Mathf.Clamp01(age[p] / 0.4f) * Mathf.Clamp01((life[p] - age[p]) / 0.6f);   // in and out
                Draw(ref seg, p, width * Mathf.Lerp(0.7f, 1.3f, Mathf.Clamp01(speed / top)), fade);
            }
            mesh.vertices = verts;
            mesh.colors = cols;
            mesh.RecalculateBounds();
        }

        bool Spawn(int p)
        {
            if (moving.Count == 0) return false;
            var c = field.CellCentre(moving[rng.Next(moving.Count)]);
            pos[p] = c + new Vector2((float)rng.NextDouble() - 0.5f, (float)rng.NextDouble() - 0.5f) * field.Cell;
            trail[p, 0] = pos[p];
            trailY[p, 0] = HeightAt(pos[p]);
            filled[p] = 1;
            age[p] = 0;
            life[p] = Life * (0.6f + 0.8f * (float)rng.NextDouble());
            return true;
        }

        void Hide(ref int seg, int p)
        {
            for (int i = 0; i < Trail - 1; i++, seg++)
                for (int k = 0; k < 4; k++) { verts[seg * 4 + k] = Vector3.zero; cols[seg * 4 + k] = Color.clear; }
        }

        /// The trail as a flat strip on the water's surface: bright at the head, fading to nothing at the tail.
        void Draw(ref int seg, int p, float width, float fade)
        {
            int n = filled[p];
            for (int i = 0; i < Trail - 1; i++, seg++)
            {
                int a = seg * 4;
                if (i + 1 >= n) { for (int k = 0; k < 4; k++) { verts[a + k] = Vector3.zero; cols[a + k] = Color.clear; } continue; }
                Vector2 p0 = trail[p, i], p1 = trail[p, i + 1];
                var d = p0 - p1;
                if (d.sqrMagnitude < 1e-8f) d = Vector2.right * 1e-3f;
                var side = new Vector2(-d.y, d.x).normalized;
                float w0 = width * (1f - (float)i / Trail) * 0.5f, w1 = width * (1f - (float)(i + 1) / Trail) * 0.5f;
                float y0 = trailY[p, i], y1 = trailY[p, i + 1];
                verts[a] = At(p0 + side * w0, y0);
                verts[a + 1] = At(p0 - side * w0, y0);
                verts[a + 2] = At(p1 - side * w1, y1);
                verts[a + 3] = At(p1 + side * w1, y1);
                float al0 = fade * (1f - (float)i / (Trail - 1)), al1 = fade * (1f - (float)(i + 1) / (Trail - 1));
                cols[a] = cols[a + 1] = new Color(1f, 1f, 1f, 0.95f * al0);
                cols[a + 2] = cols[a + 3] = new Color(1f, 1f, 1f, 0.95f * al1);
            }
        }

        /// The view height just above the water's surface (or the ground, where it is higher) at a survey point.
        float HeightAt(Vector2 xy)
        {
            float s = water.SurfaceAt(xy.x, xy.y);
            float g = terrain.Grid != null ? terrain.GroundSmooth(xy.x, xy.y) : float.NaN;
            float z = float.IsNaN(s) ? (float.IsNaN(g) ? frame.ZRef : g) : float.IsNaN(g) ? s : Mathf.Max(s, g);
            return (z - frame.ZRef) * frame.Exaggeration + 0.08f + 0.02f * frame.Exaggeration;
        }

        Vector3 At(Vector2 xy, float y)
        {
            var w = frame.World(xy.x, xy.y, frame.ZRef);
            w.y = y;
            return w;
        }

        public void Clear()
        {
            field = null;
            if (mesh != null) { Destroy(mesh); mesh = null; }
            gameObject.SetActive(false);
        }
    }
}
